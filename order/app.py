import sys
import os

# Add common to path if it is not already there
if not os.path.isdir("common"):
    sys.path.append(os.path.join(os.path.dirname(__file__), "..", "common"))

import atexit
import logging
from flask import Flask
from config import db, payment_channel, stock_channel
from service import order_blueprint

from prometheus_flask_exporter import PrometheusMetrics  # New import


app = Flask("order-service")
app.register_blueprint(order_blueprint)


@atexit.register
def cleanup():
    db.close()
    payment_channel.close()
    stock_channel.close()


metrics = PrometheusMetrics(app)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
else:
    gunicorn_logger = logging.getLogger("gunicorn.error")
    app.logger.handlers = gunicorn_logger.handlers
    app.logger.setLevel(gunicorn_logger.level)
