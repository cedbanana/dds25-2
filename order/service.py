import uuid
from collections import defaultdict
from flask import Blueprint, jsonify, abort, Response, current_app
from config import db, payment_client, stock_client
from models import Order
from proto.payment_pb2 import PaymentRequest
from proto.stock_pb2 import ItemRequest, StockAdjustment

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
    order = get_order_from_db(order_id)
    try:
        # Call the Stock service (gRPC client) to get item price.
        item_response = stock_client.FindItem(ItemRequest(item_id=item_id))
    except Exception as e:
        current_app.logger.exception("Error calling StockService for item %s", item_id)
        abort(400, "Error communicating with stock service")
    if not item_response.item_id:
        current_app.logger.error("Item not found: %s", item_id)
        abort(400, f"Item {item_id} not found")

    # Append a tuple (item_id, quantity) to the order.
    order.items.append((item_id, int(quantity)))
    order.total_cost += int(quantity) * item_response.price

    try:
        db.save(order)
        current_app.logger.info(
            "Added item %s (qty %s) to order %s", item_id, quantity, order_id
        )
    except Exception as e:
        current_app.logger.exception("Failed to update order: %s", order_id)
        abort(400, DB_ERROR_STR)
    return Response(f"Item {item_id} added. Total: {order.total_cost}", status=200)


@order_blueprint.post("/checkout/<order_id>")
def checkout(order_id: str):
    order = get_order_from_db(order_id)
    items = defaultdict(int)
    for item_id, qty in order.items:
        items[item_id] += qty

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
            abort(400, "Error communicating with stock service")
        if not stock_response.success:
            current_app.logger.error("Insufficient stock for item: %s", item_id)
            abort(400, f"Insufficient stock for {item_id}")

    # Process payment.
    try:
        payment_response = payment_client.ProcessPayment(
            PaymentRequest(user_id=order.user_id, amount=order.total_cost)
        )
    except Exception as e:
        current_app.logger.exception(
            "Error calling ProcessPayment for user %s", order.user_id
        )
        abort(400, "Error communicating with payment service")
    if not payment_response.success:
        current_app.logger.error("Payment failed for order %s", order_id)
        abort(400, "Payment failed")

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
