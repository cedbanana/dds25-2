import uuid
import logging
from flask import Blueprint, jsonify, abort, Response
from msgspec import msgpack
from config import db
from .database.models import StockValue
from .db.client import DatabaseError

# Initialize the Blueprint
stock_blueprint = Blueprint("stock", __name__)

DB_ERROR_STR = "DB error"


def get_item_from_db(item_id: str) -> StockValue:
    try:
        entry = db.get(item_id)
    except DatabaseError:
        abort(400, DB_ERROR_STR)

    if not entry:
        abort(400, f"Item: {item_id} not found!")

    try:
        return msgpack.decode(entry, type=StockValue)
    except msgpack.DecodeError:
        abort(400, "Invalid item data format")


@stock_blueprint.post("/item/create/<price>")
def create_item(price: int):
    key = str(uuid.uuid4())
    logging.debug(f"Item: {key} created")
    value = msgpack.encode(StockValue(stock=0, price=int(price)))
    try:
        db.set(key, value)
    except DatabaseError:
        abort(400, DB_ERROR_STR)
    return jsonify({"item_id": key})


@stock_blueprint.post("/batch_init/<n>/<starting_stock>/<item_price>")
def batch_init_items(n: int, starting_stock: int, item_price: int):
    n = int(n)
    starting_stock = int(starting_stock)
    item_price = int(item_price)
    kv_pairs = {
        f"{i}": msgpack.encode(StockValue(stock=starting_stock, price=item_price))
        for i in range(n)
    }
    try:
        db.mset(kv_pairs)
    except DatabaseError:
        abort(400, DB_ERROR_STR)
    return jsonify({"msg": "Batch init for stock successful"})


@stock_blueprint.get("/find/<item_id>")
def find_item(item_id: str):
    item_entry = get_item_from_db(item_id)
    return jsonify({"stock": item_entry.stock, "price": item_entry.price})


@stock_blueprint.post("/add/<item_id>/<amount>")
def add_stock(item_id: str, amount: int):
    item_entry = get_item_from_db(item_id)
    item_entry.stock += int(amount)
    try:
        db.set(item_id, msgpack.encode(item_entry))
    except DatabaseError:
        abort(400, DB_ERROR_STR)
    return Response(f"Item: {item_id} stock updated to: {item_entry.stock}", status=200)


@stock_blueprint.post("/subtract/<item_id>/<amount>")
def remove_stock(item_id: str, amount: int):
    item_entry = get_item_from_db(item_id)
    item_entry.stock -= int(amount)
    logging.debug(f"Item: {item_id} stock updated to: {item_entry.stock}")

    if item_entry.stock < 0:
        abort(400, f"Item: {item_id} stock cannot get reduced below zero!")

    try:
        db.set(item_id, msgpack.encode(item_entry))
    except DatabaseError:
        abort(400, DB_ERROR_STR)
    return Response(f"Item: {item_id} stock updated to: {item_entry.stock}", status=200)
