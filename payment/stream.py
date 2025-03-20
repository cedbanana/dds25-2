from database.stream import StreamProcessor
from config import db, STREAM_KEY, CONSUMER_GROUP, NUM_STREAM_CONSUMERS
import logging

import sys

root = logging.getLogger()
root.setLevel(logging.DEBUG)

handler = logging.StreamHandler(sys.stdout)
handler.setLevel(logging.DEBUG)
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
handler.setFormatter(formatter)
root.addHandler(handler)


class CreditDeductionConsumer(StreamProcessor):
    stream_key = STREAM_KEY

    def callback(self, user_id=None, amount=0, tid=""):
        logging.info((user_id, amount), tid)
        try:
            user_id = user_id

            if not db.lte_decrement(user_id, "credit", amount):
                logging.error(
                    "Payment failed for user %s: insufficient credit",
                    user_id,
                )
                ## TODO: SAGA Rollback / Rollback transaction from order

        except Exception as e:
            logging.exception("Error in ProcessPayment")
            ## TODO: SAGA Rollback / Rollback transaction from order


if __name__ == "__main__":
    consumer = db.initialize_stream_processor(CreditDeductionConsumer)
    consumer.start_workers(CONSUMER_GROUP, NUM_STREAM_CONSUMERS)
