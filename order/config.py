import os
from dotenv import load_dotenv
import time

import grpc
from proto.payment_pb2_grpc import PaymentServiceStub
from proto.stock_pb2_grpc import StockServiceStub

from database import RedisClient, IgniteClient
from utils import hosttotup, wait_for_ignite

from models import Order

load_dotenv()

if os.environ.get("DB_TYPE", "redis") == "redis":
    db = RedisClient(
        host=os.environ["REDIS_HOST"],
        port=int(os.environ["REDIS_PORT"]),
        password=os.environ["REDIS_PASSWORD"],
        db=int(os.environ["REDIS_DB"]),
    )
else:
    wait_for_ignite()
    db = IgniteClient(
        list(map(hosttotup, os.environ["IGNITE_HOSTS"].split(","))), model_class=Order
    )

cache = RedisClient(
    host=os.environ["REDIS_HOST"],
    port=int(os.environ["REDIS_PORT"]),
    password=os.environ["REDIS_PASSWORD"],
    db=int(time.time()) + hash(__name__),
)

# Initialize gRPC clients
payment_channel = grpc.insecure_channel(
    os.environ["PAYMENT_SERVICE_ADDR"],
    options=(("grpc.lb_policy_name", "round_robin"),),
)
payment_client = PaymentServiceStub(payment_channel)

stock_channel = grpc.insecure_channel(
    os.environ["STOCK_SERVICE_ADDR"],
    options=(("grpc.lb_policy_name", "round_robin"),),
)
stock_client = StockServiceStub(stock_channel)
