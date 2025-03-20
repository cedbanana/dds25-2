import os
import sys

# Add common to path if it is not already there
if not os.path.isdir("common"):
    sys.path.append(os.path.join(os.path.dirname(__file__), "..", "common"))


import time
from dotenv import load_dotenv
from database import RedisClient, IgniteClient
from utils import hosttotup, wait_for_ignite
from models import Stock


import grpc.aio
import grpc
from proto.payment_pb2_grpc import PaymentServiceStub

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
        list(map(hosttotup, os.environ["IGNITE_HOSTS"].split(","))), model_class=Stock
    )


PROFILING = os.environ.get("PROFILING", "false") == "true"

STREAM_KEY = "transactions"
CONSUMER_GROUP = "pula"
NUM_STREAM_CONSUMERS = int(os.environ.get("NUM_STREAM_CONSUMERS", "1"))


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
