from typing import Any
import uuid
from flask import Blueprint, jsonify, Response, abort, current_app
from database import TransactionConfig
from config import db
from models import User

payment_blueprint = Blueprint("payment", __name__)
DB_ERROR_STR = "DB error"


def get_user_from_db(user_id: str, db=db) -> User:
    try:
        user = db.get(user_id, User)
        if user is None:
            current_app.logger.error("User not found: %s", user_id)
            abort(400, f"User: {user_id} not found!")
        return user
    except Exception as e:
        current_app.logger.exception("Failed to retrieve user: %s", user_id)
        abort(400, DB_ERROR_STR)


def get_user_field_from_db(user_id: str, field: str, db=db) -> Any:
    try:
        field = db.get_attr(user_id, field, User)
        if field is None:
            current_app.logger.error("User not found: %s", user_id)
            abort(400, f"User: {user_id} not found!")
        return field
    except Exception as e:
        current_app.logger.exception("Failed to retrieve user: %s", user_id)
        abort(400, DB_ERROR_STR)


@payment_blueprint.post("/create_user")
def create_user():
    key = str(uuid.uuid4())
    user = User(id=key, credit=0)
    try:
        db.save(user)
        current_app.logger.info("Created new user: %s", key)
    except Exception as e:
        current_app.logger.exception("Failed to save new user: %s", key)
        abort(400, DB_ERROR_STR)
    return jsonify({"user_id": key})


@payment_blueprint.post("/batch_init/<n>/<starting_money>")
def batch_init_users(n: int, starting_money: int):
    try:
        n = int(n)
        starting_money = int(starting_money)
        users = []
        for i in range(n):
            user = User(id=str(i), credit=starting_money)
            users.append(user)
        db.save_all(users)
        current_app.logger.info("Batch init for users successful with %s users", n)
    except Exception as e:
        current_app.logger.exception("Batch initialization failed for users")
        abort(400, DB_ERROR_STR)
    return jsonify({"msg": "Batch init for users successful"})


@payment_blueprint.get("/find_user/<user_id>")
def find_user(user_id: str):
    user_entry = get_user_from_db(user_id)
    return jsonify({"user_id": user_entry.id, "credit": user_entry.credit})


@payment_blueprint.post("/add_funds/<user_id>/<int:amount>")
def add_credit(user_id: str, amount: int):
    user_entry = get_user_from_db(user_id)
    try:
        user_entry.credit = db.increment(user_id, "credit", amount)
        current_app.logger.info(
            "Added funds to user %s; new credit: %s", user_id, user_entry.credit
        )
    except Exception as e:
        current_app.logger.exception("Failed to update funds for user: %s", user_id)
        abort(400, DB_ERROR_STR)
    return Response(
        f"User: {user_id} credit updated to: {user_entry.credit}", status=200
    )


@payment_blueprint.post("/pay/<user_id>/<int:amount>")
def remove_credit(user_id: str, amount: int):
    with db.transaction(
        TransactionConfig(begin={"watch": [(user_id, "credit")]})
    ) as transaction:
        user_credit = get_user_field_from_db(user_id, "credit", db=transaction)
        if user_credit < amount:
            current_app.logger.error(
                "User %s credit cannot be reduced below zero", user_id
            )
            abort(400, f"User: {user_id} credit cannot get reduced below zero!")
        try:
            transaction.decrement(user_id, "credit", amount)
            current_app.logger.info(
                "Processed payment for user %s; new credit: %s",
                user_id,
                user_credit - amount,
            )
        except Exception as e:
            current_app.logger.exception(
                "Failed to update credit for user: %s", user_id
            )
            abort(400, DB_ERROR_STR)
        return Response(
            f"User: {user_id} credit updated to: {user_credit - amount}", status=200
        )
