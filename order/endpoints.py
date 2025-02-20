from collections import defaultdict
import uuid
from flask import Blueprint, jsonify, abort, Response
from msgspec import msgpack
from config import db, payment_client, stock_client
from .db.models import OrderValue
from .db.client import DatabaseError
from .proto.common_pb2 import Empty
from .proto.payment_pb2 import PaymentRequest
from .proto.stock_pb2 import ItemRequest, StockAdjustment

order_blueprint = Blueprint("order", __name__)
DB_ERROR_STR = "DB error"


def get_order_from_db(order_id: str) -> OrderValue:
    try:
        if (entry := db.get(order_id)) is None:
            abort(400, f"Order: {order_id} not found!")
        return msgpack.decode(entry, type=OrderValue)
    except DatabaseError:
        abort(400, DB_ERROR_STR)
    except msgpack.DecodeError:
        abort(400, "Invalid order data format")


@order_blueprint.post("/create/<user_id>")
def create_order(user_id: str):
    order_id = str(uuid.uuid4())
    order = OrderValue(paid=False, items=[], user_id=user_id, total_cost=0)
    try:
        db.set(order_id, msgpack.encode(order))
    except DatabaseError:
        abort(400, DB_ERROR_STR)
    return jsonify({"order_id": order_id})


@order_blueprint.post("/addItem/<order_id>/<item_id>/<quantity>")
def add_item(order_id: str, item_id: str, quantity: int):
    order = get_order_from_db(order_id)

    # Call StockService to get item price
    item_response = stock_client.FindItem(ItemRequest(item_id=item_id))
    if not item_response.item_id:
        abort(400, f"Item {item_id} not found")

    order.items.append((item_id, int(quantity)))
    order.total_cost += int(quantity) * item_response.price

    try:
        db.set(order_id, msgpack.encode(order))
    except DatabaseError:
        abort(400, DB_ERROR_STR)
    return Response(f"Item {item_id} added. Total: {order.total_cost}", status=200)


@order_blueprint.post("/checkout/<order_id>")
def checkout(order_id: str):
    order = get_order_from_db(order_id)
    items = defaultdict(int)
    for item_id, qty in order.items:
        items[item_id] += qty

    # Call StockService to subtract stock
    for item_id, total_qty in items.items():
        stock_response = stock_client.RemoveStock(
            StockAdjustment(item_id=item_id, quantity=total_qty)
        )
        if not stock_response.success:
            abort(400, f"Insufficient stock for {item_id}")

    # Call PaymentService to process payment
    payment_response = payment_client.ProcessPayment(
        PaymentRequest(user_id=order.user_id, amount=order.total_cost)
    )
    if not payment_response.success:
        abort(400, "Payment failed")

    order.paid = True
    try:
        db.set(order_id, msgpack.encode(order))
    except DatabaseError:
        abort(400, DB_ERROR_STR)

    return Response("Checkout successful", status=200)
