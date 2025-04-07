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
from redlock import Redlock

load_dotenv()


if os.environ.get("DB_TYPE", "redis") == "redis":
    db = RedisClient(
        sentinel_hosts=os.environ.get(
            "SENTINEL_HOSTS", None
        ),  # e.g., "sentinel1:26379,sentinel2:26379,sentinel3:26379"
        master_name=os.environ.get(
            "REDIS_MASTER_NAME", None),  # e.g., "order-master"
        host=os.environ.get("REDIS_HOST", None),
        port=int(os.environ.get("REDIS_PORT", None)),
        password=os.environ["REDIS_PASSWORD"],
        db=int(os.environ["REDIS_DB"]),
    )

    dlm = Redlock([{"host":os.environ.get("REDIS_HOST", None), "port":int(os.environ.get("REDIS_PORT", None)), "db":int(os.environ["REDIS_DB"]), "password":os.environ["REDIS_PASSWORD"],},])

else:
    wait_for_ignite()
    db = IgniteClient(
        list(map(hosttotup, os.environ["IGNITE_HOSTS"].split(","))), model_class=Stock
    )


PROFILING = os.environ.get("PROFILING", "false") == "true"

STREAM_KEY = "transactions"
CONSUMER_GROUP = "transaction_consumer_group"
NUM_STREAM_CONSUMERS = int(os.environ.get("NUM_STREAM_CONSUMERS", "1"))
NUM_STREAM_CONSUMER_REPLICAS = int(os.environ["NUM_STREAM_CONSUMER_REPLICAS"])
PAYMENT_SERVICE_ADDR = os.environ["PAYMENT_SERVICE_ADDR"]
