import os
import sys

# Add common to path if it is not already there
if not os.path.isdir("common"):
    sys.path.append(os.path.join(os.path.dirname(__file__), "..", "common"))

import atexit
import logging
import threading
from flask import Flask
from service import payment_blueprint
from config import db
from rpc import grpc_server

app = Flask("payment-service")

# Register the Blueprint
app.register_blueprint(payment_blueprint)


@atexit.register
def cleanup():
    db.close()


if __name__ == "__main__":
    grpc_thread = threading.Thread(target=grpc_server, daemon=True)
    grpc_thread.start()
    app.run(host="0.0.0.0", port=8000, debug=True)
else:
    grpc_thread = threading.Thread(target=grpc_server, daemon=True)
    grpc_thread.start()

    gunicorn_logger = logging.getLogger("gunicorn.error")
    app.logger.handlers = gunicorn_logger.handlers
    app.logger.setLevel(gunicorn_logger.level)
