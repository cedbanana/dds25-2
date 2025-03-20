import os
from dotenv import load_dotenv
import time

import grpc.aio
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


PROFILING = os.environ.get("PROFILING", "false") == "true"

cache = RedisClient(
    host=os.environ["REDIS_HOST"],
    port=int(os.environ["REDIS_PORT"]),
    password=os.environ["REDIS_PASSWORD"],
    db=int(time.time()) + hash(__name__),
)


class AsyncPaymentClient:
    def __init__(self):
        self._payment_channel = None
        self._payment_client = None

    async def __aenter__(self):
        # Create the gRPC channel and client asynchronously
        self._payment_channel = grpc.aio.insecure_channel(
            os.environ["PAYMENT_SERVICE_ADDR"],
            options=(("grpc.lb_policy_name", "round_robin"),),
        )
        self._payment_client = PaymentServiceStub(self._payment_channel)
        return self._payment_client

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        # Close the channel asynchronously
        await self._payment_channel.close()


class AsyncStockClient:
    def __init__(self):
        self._stock_channel = None
        self._stock_client = None

    async def __aenter__(self):
        # Create the gRPC channel and client asynchronously
        self._stock_channel = grpc.aio.insecure_channel(
            os.environ["STOCK_SERVICE_ADDR"],
            options=(("grpc.lb_policy_name", "round_robin"),),
        )
        self._stock_client = StockServiceStub(self._stock_channel)
        return self._stock_client

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        # Close the channel asynchronously
        await self._stock_channel.close()
