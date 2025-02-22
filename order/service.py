import logging
import random
import uuid
from collections import defaultdict
from flask import Blueprint, jsonify, abort, Response, current_app
from config import db, payment_client, stock_client
from models import Order, Stock
from proto.payment_pb2 import PaymentRequest
from proto.stock_pb2 import ItemRequest, StockAdjustment, BulkStockAdjustment

order_blueprint = Blueprint("order", __name__)
DB_ERROR_STR = "DB error"


def get_order_from_db(order_id: str) -> Order:
    try:
        order = db.get(order_id, Order)
        if order is None:
            current_app.logger.error("Order not found: %s", order_id)
            abort(400, f"Order: {order_id} not found!")
        return order
    except Exception as e:
        current_app.logger.exception("Failed to get order: %s", order_id)
        abort(400, DB_ERROR_STR)


def get_order_field_from_db(order_id: str, field: str) -> Order:
    try:
        order = db.get_attr(order_id, field, Order)
        if order is None:
            current_app.logger.error("Order not found: %s", order_id)
            abort(400, f"Order: {order_id} not found!")
        return order
    except Exception as e:
        current_app.logger.exception("Failed to get order: %s", order_id)
        abort(400, DB_ERROR_STR)


@order_blueprint.post("/create/<user_id>")
def create_order(user_id: str):
    order_id = str(uuid.uuid4())
    order = Order(id=order_id, paid=False, items=[], user_id=user_id, total_cost=0)
    try:
        db.save(order)
        current_app.logger.info("Order created: %s for user %s", order_id, user_id)
    except Exception as e:
        current_app.logger.exception("Failed to save order: %s", order_id)
        abort(400, DB_ERROR_STR)
    return jsonify({"order_id": order_id})


@order_blueprint.post("/addItem/<order_id>/<item_id>/<quantity>")
def add_item(order_id: str, item_id: str, quantity: int):
    items = get_order_field_from_db(order_id, "items")
    try:
        # Call the Stock service (gRPC client) to get item details.
        item_response = stock_client.FindItem(ItemRequest(item_id=item_id))
    except Exception as e:
        current_app.logger.exception("Error calling StockService for item %s", item_id)
        abort(400, "Error communicating with stock service")
    if not item_response.id:
        current_app.logger.error("Item not found: %s", item_id)
        abort(400, f"Item {item_id} not found")

    # Append a tuple (item_id, quantity) to the order.
    items.append(f"{item_id}:{int(quantity)}")

    try:
        db.set_attr(order_id, "items", items, Order)
        current_app.logger.info(
            "Added item %s (qty %s) to order %s", item_id, quantity, order_id
        )
    except Exception as e:
        current_app.logger.exception("Failed to update order: %s", order_id)
        abort(400, DB_ERROR_STR)
    return Response(f"Item {item_id} added. Total item count: {len(items)}", status=200)


@order_blueprint.post("/batch_init/<n>/<n_items>/<n_users>/<item_price>")
def batch_init_orders(n: str, n_items: str, n_users: str, item_price: str):
    """
    Initialize a batch of random orders for testing purposes.

    Args:
        n: Number of orders to create
        n_items: Range of possible item IDs (0 to n_items-1)
        n_users: Range of possible user IDs (0 to n_users-1)
        item_price: Price per item
    """
    try:
        n = int(n)
        n_items = int(n_items)
        n_users = int(n_users)
        item_price = int(item_price)
    except ValueError:
        current_app.logger.error("Invalid numeric parameters provided")
        abort(400, "All parameters must be valid integers")

    def generate_order(order_id) -> Order:
        user_id = str(random.randint(0, n_users - 1))

        # Generate two random items with quantity 1
        item1_id = str(random.randint(0, n_items - 1))
        item2_id = str(random.randint(0, n_items - 1))

        # Format items as they are in the existing code: "item_id:quantity"
        items = [f"{item1_id}:1", f"{item2_id}:1"]

        return Order(
            id=order_id,
            paid=False,
            items=items,
            user_id=user_id,
            total_cost=2 * item_price,  # Two items at item_price each
        )

    # Generate and save all orders
    for i in range(n):
        order = generate_order(str(i))
        try:
            db.save(order)
        except Exception as e:
            current_app.logger.exception("Failed to save batch orders")
            abort(400, DB_ERROR_STR)

    current_app.logger.info(f"Successfully initialized {n} random orders")
    return jsonify({"msg": "Batch init for orders successful"})


### TODO: BIIIIIIIIIIG TODO Here to actually implement proper distributed
### ACID transactions. This is the only place we need them.
###
### Oh and, here is a small list of other things we could add (overengineering):
### 1. Caching of item ids, stock ids and usernames in redis so that we don't have to ask the microservice every-time
### 2. I have reason to believe the load-balancing works pretty well, but it should be double checked
### 3. I am certain some endpoints don't use the optimal operations and transaction settings in Ignite. We need to read the docs, go over
###    the code and optimize accordingly
### 4. Let's get some logging and dashboards going with Grafana and Prometheus???
### 5. We need to extensively test the performance/consistency. Imo we can do the following
###       - More locust stress testing, we could write our own profiles
###       - After we connect up grafana and prometheus, we can add a connector to measure
###         the total money and items over time, so that we can track it over time (awesome benchmark for consistency)
### 6. KUBERNETES!!!
### 7. Idk we will come up with something if we get bored


## Uses bulk stock adjustments
# @order_blueprint.post("/checkout/<order_id>")
def checkout_bulk(order_id: str):
    def revert_items(items):
        try:
            stock_client.BulkRefund(BulkStockAdjustment(items=items))
        except Exception as e:
            current_app.logger.exception(
                "Error calling AddStock for items during order revert",
            )
            abort(400, "Error communicating with stock service")

    unpaid = db.compare_and_set(order_id, "paid", False, True)

    if not unpaid:
        current_app.logger.error("Order already paid: %s", order_id)
        abort(400, f"Order {order_id} already paid")

    order = get_order_from_db(order_id)
    items = defaultdict(int)

    for item in order.items:
        item_id, qty = item.split(":")
        if item_id not in items:
            items[item_id] = Stock(id=item_id, stock=0, price=0)

        items[item_id].stock += int(qty)

    deducted_items = [x.to_proto() for x in items.values()]

    try:
        stock_response = stock_client.BulkOrder(
            BulkStockAdjustment(items=deducted_items)
        )
    except Exception as e:
        current_app.logger.exception("Error calling RemoveStock for item %s", item_id)
        db.set_attr(order_id, "paid", False, Order)
        abort(400, "Error communicating with stock service")

    if not stock_response.status.success:
        err_msg = stock_response.status.error or f"Insufficient stock for {item_id}"
        current_app.logger.error(
            "Stock deduction failed for item %s: %s", item_id, err_msg
        )
        db.set_attr(order_id, "paid", False, Order)
        abort(400, err_msg)
    else:
        order.total_cost = stock_response.total_cost

    logging.error("Checking out order with total cost: %s", order)

    # Process payment.
    try:
        payment_response = payment_client.ProcessPayment(
            PaymentRequest(user_id=order.user_id, amount=order.total_cost)
        )
    except Exception as e:
        current_app.logger.exception(
            "Error calling ProcessPayment for user %s", order.user_id
        )
        revert_items(deducted_items)
        db.set_attr(order_id, "paid", False, Order)
        abort(400, "Error communicating with payment service")
    if not payment_response.success:
        err_msg = payment_response.error or "Payment failed"
        current_app.logger.error("Payment failed for order %s: %s", order_id, err_msg)
        revert_items(deducted_items)
        db.set_attr(order_id, "paid", False, Order)
        abort(400, err_msg)

    order.paid = True
    try:
        db.save(order)
    except Exception as e:
        current_app.logger.exception(
            "Failed to update order after checkout: %s", order_id
        )
        abort(400, DB_ERROR_STR)

    return Response("Checkout successful", status=200)


## Does individual stock adjustments
@order_blueprint.post("/checkout/<order_id>")
def checkout_individual(order_id: str):
    def revert_items(items):
        for item_id, qty in items.items():
            try:
                stock_client.AddStock(StockAdjustment(item_id=item_id, quantity=qty))
            except Exception as e:
                current_app.logger.exception(
                    "Error calling AddStock for item %s during order revert", item_id
                )
                abort(400, "Error communicating with stock service")
            current_app.logger.info("Reverted stock for item %s: %s", item_id, qty)

    order = get_order_from_db(order_id)
    order.total_cost = 0
    items = defaultdict(int)

    for item in order.items:
        item_id, qty = item.split(":")
        items[item_id] += int(qty)

    deducted_items = {}

    # Deduct stock for each item.
    for item_id, total_qty in items.items():
        try:
            stock_response = stock_client.RemoveStock(
                StockAdjustment(item_id=item_id, quantity=total_qty)
            )
        except Exception as e:
            current_app.logger.exception(
                "Error calling RemoveStock for item %s", item_id
            )
            revert_items(deducted_items)
            abort(400, "Error communicating with stock service")
        if not stock_response.status.success:
            err_msg = stock_response.status.error or f"Insufficient stock for {item_id}"
            current_app.logger.error(
                "Stock deduction failed for item %s: %s", item_id, err_msg
            )
            revert_items(deducted_items)
            abort(400, err_msg)
        else:
            deducted_items[item_id] = total_qty
            order.total_cost += stock_response.price

    # Process payment.
    try:
        payment_response = payment_client.ProcessPayment(
            PaymentRequest(user_id=order.user_id, amount=order.total_cost)
        )
    except Exception as e:
        current_app.logger.exception(
            "Error calling ProcessPayment for user %s", order.user_id
        )
        revert_items(deducted_items)
        abort(400, "Error communicating with payment service")
    if not payment_response.success:
        err_msg = payment_response.error or "Payment failed"
        current_app.logger.error("Payment failed for order %s: %s", order_id, err_msg)
        revert_items(deducted_items)
        abort(400, err_msg)

    order.paid = True
    try:
        db.save(order)
        current_app.logger.info("Checkout successful for order %s", order_id)
    except Exception as e:
        current_app.logger.exception(
            "Failed to update order after checkout: %s", order_id
        )
        abort(400, DB_ERROR_STR)

    return Response("Checkout successful", status=200)
