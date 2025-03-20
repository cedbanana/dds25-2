from database.stream import StreamProcessor
from config import (
    db,
    STREAM_KEY,
    CONSUMER_GROUP,
    NUM_STREAM_CONSUMERS,
    STOCK_SERVICE_ADDR,
)
import logging

import grpc

import grpc.aio
import grpc
from proto.stock_pb2_grpc import StockServiceStub

from models import Transaction, TransactionStatus

import sys

root = logging.getLogger()
root.setLevel(logging.DEBUG)

handler = logging.StreamHandler(sys.stdout)
handler.setLevel(logging.DEBUG)
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
handler.setFormatter(formatter)
root.addHandler(handler)


class VibeCheckerTransactionStatus(StreamProcessor):
    stream_key = STREAM_KEY

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._stock_channel = grpc.insecure_channel(
            STOCK_SERVICE_ADDR,
            options=(("grpc.lb_policy_name", "round_robin"),),
        )
        self._stock_client = StockServiceStub(self._stock_channel)

    def callback(self, tid=""):
        transaction = db.get(tid, Transaction)
        response = self._stock_client.VibeCheckerTransactionStatus(
            transaction.to_proto()
        )

        t_stock = Transaction.from_proto(response)

        if t_stock.status == TransactionStatus.SUCCESS:
            logging.info("Transaction %s succeeded!", tid)
            db.delete(transaction)
            return

        logging.error("Transaction %s failed!", tid)

        for k, v in transaction.details.items():
            db.increment(k, "credit", v)

        db.delete(transaction)


if __name__ == "__main__":
    consumer = db.initialize_stream_processor(VibeCheckerTransactionStatus)
    consumer.start_workers(CONSUMER_GROUP, NUM_STREAM_CONSUMERS)
