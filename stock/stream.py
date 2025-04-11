from database.stream import StreamProcessor
from config import (
    db,
    STREAM_KEY,
    CONSUMER_GROUP,
    PAYMENT_SERVICE_ADDR,
    dlm,
)
import logging
import json

import grpc
from utils import randsleep
from proto.payment_pb2_grpc import PaymentServiceStub
from models import Transaction, TransactionStatus, Flag

import requests
import sys


root = logging.getLogger()
root.setLevel(logging.DEBUG)

handler = logging.StreamHandler(sys.stdout)
handler.setLevel(logging.DEBUG)
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
handler.setFormatter(formatter)
root.addHandler(handler)

ORDER_URL = "http://gateway:8000/orders"


def commit_order(tid: str, max_retry=10):
    url = f"{ORDER_URL}/commit_checkout/{tid}"
    count = 0

    while count < max_retry:
        try:
            response = requests.post(url)
            response.raise_for_status()
            logging.info(
                f"Sent request to commit order for transaction {tid}, url {url}."
            )
            return response.text
        except Exception as e:
            logging.error(f"Failed to commit order for transaction {tid}: {e}.")
            count += 1
            randsleep()

    return None


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

    def pre_xread(self):
        flag = db.get("HALTED", Flag)
        if flag is not None and flag.enabled:
            # lock = dlm.lock("consumer_lock", 3000)
            db.increment("halted_consumers_counter", "count", 1)

            lock = db.redis.lock("snapshot_lock")

            if lock.acquire(blocking=True):
                logging.warning("GOT'EM")
                lock.release()

    def callback(self, id, tid=""):
        transaction = db.get(tid, Transaction)

        if transaction is None or transaction.status == TransactionStatus.STALE:
            logging.info("Transaction %s is None | STALE", tid)
            return

        unlocked = db.compare_and_set(tid, "locked", False, True)
        if not unlocked:
            logging.info("Transaction %s is locked, pushing back", tid)
            randsleep()
            self._stream_producer.push(tid=tid)
            return

        if transaction.status == TransactionStatus.PENDING:
            logging.info("Transaction %s is still pending", tid)

            # if transaction.pending_count > 10000000000:
            #     transaction.status = TransactionStatus.FAILURE
            #     db.save(transaction)
            #
            db.increment(tid, "pending_count", 1)
            db.set_attr(tid, "locked", False, Transaction)
            randsleep()
            self._stream_producer.push(tid=tid)

            return

        try:
            response = self._payment_client.VibeCheckTransactionStatus(
                transaction.to_proto()
            )
        except grpc.RpcError as e:
            if e.code() == grpc.StatusCode.FAILED_PRECONDITION:
                logging.warning("Transaction %s locked remotely", tid)
            else:
                logging.exception("Error in VibeCheckTransactionStatus")
            db.set_attr(tid, "locked", False, Transaction)
            randsleep()
            self._stream_producer.push(tid=tid)
            return
        except Exception:
            logging.exception("Error in VibeCheckTransactionStatus")
            db.set_attr(tid, "locked", False, Transaction)
            randsleep()
            self._stream_producer.push(tid=tid)
            return

        t_payment = Transaction.from_proto(response)
        db.delete(transaction)

        if (
            transaction.status == TransactionStatus.SUCCESS
            and t_payment.status == TransactionStatus.FAILURE
        ):  # If remote is failed, and we are successful, we need to roll back
            logging.info("Rolling %s back!", tid)
            for k, v in transaction.details.items():
                db.increment(k, "stock", v)
        elif transaction.status == TransactionStatus.SUCCESS:
            logging.info("Transaction %s committing", tid)
            for k, v in transaction.details.items():
                db.decrement(k, "committed_stock", v)
            commit_order(transaction.id)


if __name__ == "__main__":
    consumer = db.initialize_stream_processor(VibeCheckerTransactionStatus)
    consumer.start_worker(CONSUMER_GROUP, f"vibe_checker_{STREAM_KEY}_consumer")
