from flask import Blueprint, jsonify, Response, abort
from msgspec import msgpack
import uuid
from .db.client import DatabaseError
from .db.models import UserValue
from .config import db

user_blueprint = Blueprint("user", __name__)

DB_ERROR_STR = "DB error"


def get_user_from_db(user_id: str) -> UserValue:
    try:
        entry = db.get(user_id)
    except DatabaseError:
        abort(400, DB_ERROR_STR)

    if not entry:
        abort(400, f"User: {user_id} not found!")

    try:
        return msgpack.decode(entry, type=UserValue)
    except msgpack.DecodeError:
        abort(400, "Invalid user data format")


@user_blueprint.post("/create_user")
def create_user():
    key = str(uuid.uuid4())
    value = msgpack.encode(UserValue(credit=0))
    try:
        db.set(key, value)
    except DatabaseError:
        abort(400, DB_ERROR_STR)
    return jsonify({"user_id": key})


@user_blueprint.post("/batch_init/<n>/<starting_money>")
def batch_init_users(n: int, starting_money: int):
    n = int(n)
    starting_money = int(starting_money)
    kv_pairs = {
        f"{i}": msgpack.encode(UserValue(credit=starting_money)) for i in range(n)
    }
    try:
        db.mset(kv_pairs)
    except DatabaseError:
        abort(400, DB_ERROR_STR)
    return jsonify({"msg": "Batch init for users successful"})


@user_blueprint.get("/find_user/<user_id>")
def find_user(user_id: str):
    user_entry = get_user_from_db(user_id)
    return jsonify({"user_id": user_id, "credit": user_entry.credit})


@user_blueprint.post("/add_funds/<user_id>/<amount>")
def add_credit(user_id: str, amount: int):
    user_entry = get_user_from_db(user_id)
    user_entry.credit += int(amount)
    try:
        db.set(user_id, msgpack.encode(user_entry))
    except DatabaseError:
        abort(400, DB_ERROR_STR)
    return Response(
        f"User: {user_id} credit updated to: {user_entry.credit}", status=200
    )


@user_blueprint.post("/pay/<user_id>/<amount>")
def remove_credit(user_id: str, amount: int):
    user_entry = get_user_from_db(user_id)
    user_entry.credit -= int(amount)

    if user_entry.credit < 0:
        abort(400, f"User: {user_id} credit cannot get reduced below zero!")

    try:
        db.set(user_id, msgpack.encode(user_entry))
    except DatabaseError:
        abort(400, DB_ERROR_STR)
    return Response(
        f"User: {user_id} credit updated to: {user_entry.credit}", status=200
    )
