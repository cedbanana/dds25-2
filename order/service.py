import logging
import random
import uuid
import asyncio
import uuid
from collections import defaultdict
from quart import Blueprint, jsonify, abort, Response, current_app
from config import db, AsyncPaymentClient, AsyncStockClient
from models import Order, Stock
from redis.exceptions import WatchError
from database import TransactionConfig
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
async def create_order(user_id: str):
    order_id = str(uuid.uuid4())
    order = Order(id=order_id, paid=0, items=[], user_id=user_id, total_cost=0)
    try:
        db.save(order)
        current_app.logger.info("Order created: %s for user %s", order_id, user_id)
    except Exception as e:
        current_app.logger.exception("Failed to save order: %s", order_id)
        abort(400, DB_ERROR_STR)
    return jsonify({"order_id": order_id})


@order_blueprint.get("/find_order/<order_id>")
async def find_order(order_id: str):
    order = get_order_from_db(order_id)

    items = defaultdict(int)

    for item in order.items:
        item_id, qty = item.split(":")
        items[item_id] += int(qty)

    return jsonify(
        {
            "order_id": order.id,
            "paid": order.paid,  # Number of times order has been paid
            "items": items,
            "user_id": order.user_id,
            "total_cost": order.total_cost,
        }
    )


@order_blueprint.post("/addItem/<order_id>/<item_id>/<quantity>")
async def add_item(order_id: str, item_id: str, quantity: int):
    async with AsyncStockClient() as stock_client:
        
        with db.transaction(
            TransactionConfig(begin={"watch": [(order_id, "items"), (order_id, "total_cost")]})
            ) as transaction:
            
            items = get_order_field_from_db(order_id, "items")

            try:
                item_response = await stock_client.FindItem(ItemRequest(item_id=item_id))
            except Exception as e:
                current_app.logger.exception(
                    "Error calling StockService for item %s", item_id
                )
                abort(400, "Error communicating with stock service")
            if not item_response.id:
                current_app.logger.error("Item not found: %s", item_id)
                abort(400, f"Item {item_id} not found")

            # Append a tuple (item_id, quantity) to the order.
            items.append(f"{item_id}:{int(quantity)}")

            try:
                transaction.increment(order_id, "total_cost", item_response.price)
                transaction.set_attr(order_id, "items", items, Order)
                current_app.logger.info(
                    "Added item %s (qty %s) to order %s", item_id, quantity, order_id
                )
            except WatchError as watch_err: 
                current_app.logger.exception("Watch error 2024: %s", str(watch_err))
                return await add_item(order_id = order_id, item_id = item_id, quantity = quantity)
            except Exception as e:
                current_app.logger.exception("Failed to update order: %s", order_id)
                abort(400, DB_ERROR_STR)
            return Response(
                f"Item {item_id} added. Total item count: {len(items)}", status=200
            )


@order_blueprint.post("/batch_init/<n>/<n_items>/<n_users>/<item_price>")
async def batch_init_orders(n: str, n_items: str, n_users: str, item_price: str):
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
            paid=0,
            items=items,
            user_id=user_id,
            total_cost=2 * item_price,
        )

    # Generate and save all orders
    orders = []
    for i in range(n):
        order = generate_order(str(i))
        orders.append(order)

    try:
        db.save_all(orders)
    except Exception as e:
        current_app.logger.exception("Failed to save batch orders")
        abort(400, DB_ERROR_STR)

    current_app.logger.info(f"Successfully initialized {n} random orders")
    return jsonify({"msg": "Batch init for orders successful"})


# Does individual stock adjustments
@order_blueprint.post("/checkout/<order_id>")
async def checkout_individual(order_id: str):
    async def revert_items(items):
        for item_id, qty in items.items():
            try:
                await stock_client.AddStock(
                    StockAdjustment(item_id=item_id, quantity=qty)
                )
            except Exception as e:
                current_app.logger.exception(
                    "Error calling AddStock for item %s during order revert: %s",
                    item_id,
                    str(e),
                )
                abort(400, "Error communicating with stock service")
            current_app.logger.info("Reverted stock for item %s: %s", item_id, qty)

    async with AsyncStockClient() as stock_client, AsyncPaymentClient() as payment_client:
        order = get_order_from_db(order_id)
        items = defaultdict(int)
        tid = str(uuid.uuid4())

        for item in order.items:
            item_id, qty = item.split(":")
            items[item_id] += int(qty)

        # Process payment.

        stock_ids = []
        stock_futures = []

        for item_id, total_qty in items.items():
            stock_futures.append(
                stock_client.RemoveStock(
                    StockAdjustment(item_id=item_id, quantity=total_qty, tid=tid)
                )
            )
            stock_ids.append(item_id)

        payment_rpc = payment_client.ProcessPayment(
            PaymentRequest(user_id=order.user_id, amount=order.total_cost, tid=tid)
        )

        stock_tasks = asyncio.gather(*stock_futures)
        payment_response = await payment_rpc
        stock_responses = await stock_tasks

        deducted_items = {}

        for i in range(len(stock_responses)):
            resp = stock_responses[i]
            if not resp.status.success:
                current_app.logger.error(
                    "Stock deduction failed for item %s.", stock_ids[i]
                )
            else:
                deducted_items[stock_ids[i]] = items[stock_ids[i]]

        if not payment_response.success:
            err_msg = payment_response.error or "Payment failed"
            current_app.logger.error(
                "Payment failed for order %s: %s", order_id, err_msg
            )
            abort(400, err_msg)

        if len(deducted_items) != len(items):
            current_app.logger.error(
                "Insufficient stock for some of the items: %s", stock_ids
            )
            abort(400, "Insufficient stock for some items")

    db.increment(order_id, "paid", 1)  # Increment the number of times it is paid
    current_app.logger.info("Checkout successful for order %s.", order_id)
    return Response("Checkout successful", status=200)


# Uses bulk stock adjustments
# (Uncomment to use this endpoint)
# @order_blueprint.post("/checkout/<order_id>")
async def checkout_bulk(order_id: str):
    async with AsyncStockClient() as stock_client, AsyncPaymentClient() as payment_client:

        async def revert_items(items):
            try:
                await stock_client.BulkRefund(BulkStockAdjustment(items=items))
            except Exception as e:
                current_app.logger.exception(
                    "Error calling AddStock for items during order revert"
                )
                abort(400, "Error communicating with stock service")

        # unpaid = db.compare_and_set(order_id, "paid", False, True)
        #
        # if not unpaid:
        #     current_app.logger.error("Order already paid: %s", order_id)
        #     return Response(f"Order {order_id} already paid", status=200)

        order = get_order_from_db(order_id)
        items = defaultdict(int)

        for item in order.items:
            item_id, qty = item.split(":")
            if item_id not in items:
                items[item_id] = Stock(id=item_id, stock=0, price=0)

            items[item_id].stock += int(qty)

        deducted_items = [x.to_proto() for x in items.values()]

        try:
            stock_response = await stock_client.BulkOrder(
                BulkStockAdjustment(items=deducted_items)
            )
        except Exception as e:
            current_app.logger.exception(
                "Error calling RemoveStock for item %s", item_id
            )
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
            payment_response = await payment_client.ProcessPayment(
                PaymentRequest(user_id=order.user_id, amount=order.total_cost)
            )
        except Exception as e:
            current_app.logger.exception(
                "Error calling ProcessPayment for user %s", order.user_id
            )
            await revert_items(deducted_items)
            db.set_attr(order_id, "paid", False, Order)
            abort(400, "Error communicating with payment service")
        if not payment_response.success:
            err_msg = payment_response.error or "Payment failed"
            current_app.logger.error(
                "Payment failed for order %s: %s", order_id, err_msg
            )
            await revert_items(deducted_items)
            db.set_attr(order_id, "paid", False, Order)
            abort(400, err_msg)

        return Response("Checkout successful", status=200)
