import uuid
from flask import Blueprint, jsonify, abort, Response, current_app
from config import db
from models import Stock
from database import TransactionConfig

stock_blueprint = Blueprint("stock", __name__)
DB_ERROR_STR = "DB error"


def get_item_from_db(id: str, db=db) -> Stock:
    try:
        item = db.get(id, Stock)
        if item is None:
            current_app.logger.error("Item not found: %s", id)
            abort(400, f"Item: {id} not found!")
        return item
    except Exception as e:
        current_app.logger.exception("Failed to get item: %s", id)
        abort(400, DB_ERROR_STR)


def get_item_field_from_db(id: str, field: str, db=db) -> Stock:
    try:
        value = db.get_attr(id, field, Stock)
        if value is None:
            current_app.logger.error("Item not found: %s", id)
            abort(400, f"Item: {id} not found!")
        return value
    except Exception as e:
        current_app.logger.exception("Failed to get item: %s", id)
        abort(400, DB_ERROR_STR)


@stock_blueprint.post("/item/create/<price>")
def create_item(price: int):
    key = str(uuid.uuid4())
    current_app.logger.info("Creating new item with id: %s", key)
    stock_item = Stock(id=key, stock=0, price=int(price), reserved = 0)
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
            stock_item = Stock(id=str(i), stock=starting_stock, price=item_price)
            db.save(stock_item)
        current_app.logger.info("Batch init for stock successful with %s items", n)
    except Exception as e:
        current_app.logger.exception("Batch initialization failed for stock")
        abort(400, DB_ERROR_STR)
    return jsonify({"msg": "Batch init for stock successful"})


@stock_blueprint.get("/find/<id>")
def find_item(id: str):
    item_entry = get_item_from_db(id)
    return jsonify({"stock": item_entry.stock, "price": item_entry.price})


@stock_blueprint.post("/add/<id>/<int:amount>")
def add_stock(id: str, amount: int):
    item_entry = get_item_from_db(id)

    try:
        item_entry.stock = db.increment(id, "stock", amount)
        current_app.logger.info(
            "Added %s to item %s; new stock: %s", amount, id, item_entry.stock
        )
    except Exception as e:
        current_app.logger.exception("Failed to update stock for item: %s", id)
        abort(400, DB_ERROR_STR)
    return Response(f"Item: {id} stock updated to: {item_entry.stock}", status=200)


@stock_blueprint.post("/subtract/<id>/<int:amount>")
def remove_stock(id: str, amount: int):
    with db.transaction(
        TransactionConfig(begin={"watch": [(id, "stock")]})
    ) as transaction:
        stock = get_item_field_from_db(id, "stock", db=transaction)

        current_app.logger.info(
            "Subtracting %s from item %s; new stock: %s", amount, id, stock - amount
        )
        if stock < amount:
            current_app.logger.error("Item %s stock cannot be reduced below zero!", id)
            abort(400, f"Item: {id} stock cannot get reduced below zero!")
        try:
            transaction.decrement(id, "stock", amount)
            current_app.logger.info("Updated stock for item %s", id)
        except Exception as e:
            current_app.logger.exception(
                "Failed to save updated stock for item: %s", id
            )
            abort(400, DB_ERROR_STR)
        return Response(f"Item: {id} stock updated to: {stock - amount}", status=200)
