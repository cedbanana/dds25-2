import uuid
import os
import random
from collections import defaultdict
from flask import Blueprint, jsonify, abort, Response
from msgspec import msgpack
import requests
from .config import db
from .db.models import OrderValue
from .db.client import DatabaseError

order_blueprint = Blueprint("order", __name__)
DB_ERROR_STR = "DB error"
REQ_ERROR_STR = "Requests error"


def get_order_from_db(order_id: str) -> OrderValue:
    try:
        if (entry := db.get(order_id)) is None:
            abort(400, f"Order: {order_id} not found!")
        return msgpack.decode(entry, type=OrderValue)
    except DatabaseError:
        abort(400, DB_ERROR_STR)
    except msgpack.DecodeError:
        abort(400, "Invalid order data format")


def send_request(method: str, url: str):
    try:
        return requests.request(method, url)
    except requests.exceptions.RequestException:
        abort(400, REQ_ERROR_STR)


@order_blueprint.post("/create/<user_id>")
def create_order(user_id: str):
    order_id = str(uuid.uuid4())
    order = OrderValue(paid=False, items=[], user_id=user_id, total_cost=0)
    try:
        db.set(order_id, msgpack.encode(order))
    except DatabaseError:
        abort(400, DB_ERROR_STR)
    return jsonify({"order_id": order_id})


@order_blueprint.post("/batch_init/<n>/<n_items>/<n_users>/<item_price>")
def batch_init_orders(n: int, n_items: int, n_users: int, item_price: int):
    def generate_order():
        user_id = random.randint(0, n_users - 1)
        items = [(str(random.randint(0, n_items - 1)), 1) for _ in range(2)]
        return OrderValue(
            paid=False, items=items, user_id=str(user_id), total_cost=2 * item_price
        )

    orders = {str(i): msgpack.encode(generate_order()) for i in range(int(n))}
    try:
        db.mset(orders)
    except DatabaseError:
        abort(400, DB_ERROR_STR)
    return jsonify({"msg": "Batch init for orders successful"})


@order_blueprint.get("/find/<order_id>")
def find_order(order_id: str):
    order = get_order_from_db(order_id)
    return jsonify(
        {
            "order_id": order_id,
            "paid": order.paid,
            "items": order.items,
            "user_id": order.user_id,
            "total_cost": order.total_cost,
        }
    )


@order_blueprint.post("/addItem/<order_id>/<item_id>/<quantity>")
def add_item(order_id: str, item_id: str, quantity: int):
    order = get_order_from_db(order_id)
    response = send_request("GET", f"{os.environ['GATEWAY_URL']}/stock/find/{item_id}")

    if response.status_code != 200:
        abort(400, f"Item {item_id} not found")

    price = response.json()["price"]
    order.items.append((item_id, int(quantity)))
    order.total_cost += int(quantity) * price

    try:
        db.set(order_id, msgpack.encode(order))
    except DatabaseError:
        abort(400, DB_ERROR_STR)
    return Response(f"Item {item_id} added. Total: {order.total_cost}", status=200)


def rollback_stock(items: list[tuple[str, int]]):
    for item_id, qty in items:
        send_request("POST", f"{os.environ['GATEWAY_URL']}/stock/add/{item_id}/{qty}")


@order_blueprint.post("/checkout/<order_id>")
def checkout(order_id: str):
    order = get_order_from_db(order_id)
    items = defaultdict(int)
    for item_id, qty in order.items:
        items[item_id] += qty

    subtracted = []
    for item_id, total_qty in items.items():
        response = send_request(
            "POST", f"{os.environ['GATEWAY_URL']}/stock/subtract/{item_id}/{total_qty}"
        )
        if response.status_code != 200:
            rollback_stock(subtracted)
            abort(400, f"Insufficient stock for {item_id}")
        subtracted.append((item_id, total_qty))

    payment_response = send_request(
        "POST",
        f"{os.environ['GATEWAY_URL']}/payment/pay/{order.user_id}/{order.total_cost}",
    )

    if payment_response.status_code != 200:
        rollback_stock(subtracted)
        abort(400, "Payment failed")

    order.paid = True
    try:
        db.set(order_id, msgpack.encode(order))
    except DatabaseError:
        rollback_stock(subtracted)
        abort(400, DB_ERROR_STR)

    return Response("Checkout successful", status=200)
