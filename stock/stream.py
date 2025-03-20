from database.stream import StreamProcessor
from config import (
    db,
    STREAM_KEY,
    CONSUMER_GROUP,
    NUM_STREAM_CONSUMERS,
    PAYMENT_SERVICE_ADDR,
)
import logging
import json

import grpc
from proto.payment_pb2_grpc import PaymentServiceStub
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
        self._payment_channel = grpc.insecure_channel(
            PAYMENT_SERVICE_ADDR,
            options=(("grpc.lb_policy_name", "round_robin"),),
        )
        self._payment_client = PaymentServiceStub(self._payment_channel)
        self._stream_producer = db.get_stream_producer(STREAM_KEY)

    def callback(self, id, tid=""):
        transaction = db.get(tid, Transaction)

        if transaction is None:
            return

        if transaction.status == TransactionStatus.PENDING:
            logging.info("Transaction %s is still pending", tid)
            self._stream_producer.push(tid=tid)
            return

        response = self._payment_client.VibeCheckTransactionStatus(
            transaction.to_proto()
        )

        t_payment = Transaction.from_proto(response)

        if t_payment.status == TransactionStatus.SUCCESS:
            logging.info("Transaction %s succeeded!", tid)
            db.delete(transaction)
            return

        logging.error("Transaction %s failed!", tid)

        if transaction.status == TransactionStatus.FAILURE:
            for k, v in transaction.details.items():
                db.increment(k, "stock", v)

        db.delete(transaction)


if __name__ == "__main__":
    consumer = db.initialize_stream_processor(VibeCheckerTransactionStatus)
    consumer.start_worker(CONSUMER_GROUP, f"vibe_checker_{STREAM_KEY}_consumer")
