from database.stream import StreamProcessor
from config import db, STREAM_KEY, CONSUMER_GROUP, NUM_STREAM_CONSUMERS
import logging
import json

import sys

root = logging.getLogger()
root.setLevel(logging.DEBUG)

handler = logging.StreamHandler(sys.stdout)
handler.setLevel(logging.DEBUG)
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
handler.setFormatter(formatter)
root.addHandler(handler)


class StockDeductionConsumer(StreamProcessor):
    stream_key = STREAM_KEY

    def callback(self, items="", tid=""):
        items = json.loads(items)
        try:
            if not db.m_gte_decrement(items, "stock"):
                logging.error("Insufficient stock for items")
                ## TODO Initiate SAGA Rollback from Payment
            return
        except Exception as e:
            logging.exception("Error in RemoveStock")


if __name__ == "__main__":
    consumer = db.initialize_stream_processor(StockDeductionConsumer)
    consumer.start_workers(CONSUMER_GROUP, NUM_STREAM_CONSUMERS)
