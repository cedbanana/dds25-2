import os
import sys

# Add common to path if it is not already there
if not os.path.isdir("common"):
    sys.path.append(os.path.join(os.path.dirname(__file__), "..", "common"))


import grpc.aio
import grpc
from proto.payment_pb2_grpc import PaymentServiceStub
from proto.stock_pb2_grpc import StockServiceStub

from dotenv import load_dotenv

load_dotenv()

PAYMENT_RPC_ADDR = os.environ["PAYMENT_RPC_ADDR"]
STOCK_RPC_ADDR = os.environ["STOCK_RPC_ADDR"]
GATEWAY_ADDR = os.environ["GATEWAY_ADDR"]
ORDER_ADDR = GATEWAY_ADDR + "/order"

class AsyncPaymentClient:
    def __init__(self):
        self._payment_channel = None
        self._payment_client = None

    async def __aenter__(self):
        # Create the gRPC channel and client asynchronously
        self._payment_channel = grpc.aio.insecure_channel(
            PAYMENT_RPC_ADDR,
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
            STOCK_RPC_ADDR,
            options=(("grpc.lb_policy_name", "round_robin"),),
        )
        self._stock_client = StockServiceStub(self._stock_channel)
        return self._stock_client

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        # Close the channel asynchronously
        await self._stock_channel.close()
