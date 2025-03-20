import os
import time
import sys

# Add common to path if it is not already there
if not os.path.isdir("common"):
    sys.path.append(os.path.join(os.path.dirname(__file__), "..", "common"))

from dotenv import load_dotenv
from database import RedisClient, IgniteClient
from utils import hosttotup, wait_for_ignite
from models import User

import grpc.aio
import grpc
from proto.stock_pb2_grpc import StockServiceStub

load_dotenv()


if os.environ.get("DB_TYPE", "redis") == "redis":
    db = RedisClient(
        host=os.environ["REDIS_HOST"],
        port=int(os.environ["REDIS_PORT"]),
        password=os.environ["REDIS_PASSWORD"],
        db=int(os.environ["REDIS_DB"]),
    )
else:
    print(list(map(hosttotup, os.environ["IGNITE_HOSTS"].split(","))))
    wait_for_ignite()
    db = IgniteClient(
        list(map(hosttotup, os.environ["IGNITE_HOSTS"].split(","))), model_class=User
    )

PROFILING = os.environ.get("PROFILING", "false") == "true"

STREAM_KEY = "transactions"
CONSUMER_GROUP = "pula"
NUM_STREAM_CONSUMERS = int(os.environ.get("NUM_STREAM_CONSUMERS", "1"))


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
