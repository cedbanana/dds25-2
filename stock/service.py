import uuid
from flask import Blueprint, jsonify, abort, Response, current_app
from config import db
from models import Stock

stock_blueprint = Blueprint("stock", __name__)
DB_ERROR_STR = "DB error"


def get_item_from_db(item_id: str) -> Stock:
    try:
        item = db.get(item_id, Stock)
        if item is None:
            current_app.logger.error("Item not found: %s", item_id)
            abort(400, f"Item: {item_id} not found!")
        return item
    except Exception as e:
        current_app.logger.exception("Failed to get item: %s", item_id)
        abort(400, DB_ERROR_STR)


@stock_blueprint.post("/item/create/<price>")
def create_item(price: int):
    key = str(uuid.uuid4())
    current_app.logger.info("Creating new item with id: %s", key)
    stock_item = Stock(item_id=key, stock=0, price=int(price))
    try:
        db.save(stock_item)
        current_app.logger.info("Item created: %s", key)
    except Exception as e:
        current_app.logger.exception("Failed to save new item: %s", key)
        abort(400, DB_ERROR_STR)
    return jsonify({"item_id": key})


@stock_blueprint.post("/batch_init/<n>/<starting_stock>/<item_price>")
def batch_init_items(n: int, starting_stock: int, item_price: int):
    try:
        n = int(n)
        starting_stock = int(starting_stock)
        item_price = int(item_price)
        for i in range(n):
            stock_item = Stock(item_id=str(i), stock=starting_stock, price=item_price)
            db.save(stock_item)
        current_app.logger.info("Batch init for stock successful with %s items", n)
    except Exception as e:
        current_app.logger.exception("Batch initialization failed for stock")
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
        db.save(item_entry)
        current_app.logger.info(
            "Added %s to item %s; new stock: %s", amount, item_id, item_entry.stock
        )
    except Exception as e:
        current_app.logger.exception("Failed to update stock for item: %s", item_id)
        abort(400, DB_ERROR_STR)
    return Response(f"Item: {item_id} stock updated to: {item_entry.stock}", status=200)


@stock_blueprint.post("/subtract/<item_id>/<amount>")
def remove_stock(item_id: str, amount: int):
    item_entry = get_item_from_db(item_id)
    item_entry.stock -= int(amount)
    current_app.logger.info(
        "Subtracting %s from item %s; new stock: %s", amount, item_id, item_entry.stock
    )
    if item_entry.stock < 0:
        current_app.logger.error("Item %s stock cannot be reduced below zero!", item_id)
        abort(400, f"Item: {item_id} stock cannot get reduced below zero!")
    try:
        db.save(item_entry)
        current_app.logger.info("Updated stock for item %s", item_id)
    except Exception as e:
        current_app.logger.exception(
            "Failed to save updated stock for item: %s", item_id
        )
        abort(400, DB_ERROR_STR)
    return Response(f"Item: {item_id} stock updated to: {item_entry.stock}", status=200)
