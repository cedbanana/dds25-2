import os
from dotenv import load_dotenv

import grpc
from proto.payment_pb2_grpc import PaymentServiceStub
from proto.stock_pb2_grpc import StockServiceStub

from database import RedisClient

load_dotenv()

db = RedisClient(
    host=os.environ["REDIS_HOST"],
    port=int(os.environ["REDIS_PORT"]),
    password=os.environ["REDIS_PASSWORD"],
    db=int(os.environ["REDIS_DB"]),
)

# Initialize gRPC clients
payment_channel = grpc.insecure_channel(os.environ["PAYMENT_SERVICE_ADDR"])
payment_client = PaymentServiceStub(payment_channel)

stock_channel = grpc.insecure_channel(os.environ["STOCK_SERVICE_ADDR"])
stock_client = StockServiceStub(stock_channel)
