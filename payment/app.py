import os
import atexit
import logging
import threading
from flask import Flask
from .endpoints import user_blueprint
from .config import db
from .service import grpc_server

app = Flask("payment-service")

# Register the Blueprint
app.register_blueprint(user_blueprint, url_prefix="/api")


@atexit.register
def cleanup():
    db.close()


atexit.register(db.close)

if __name__ == "__main__":
    grpc_thread = threading.Thread(target=grpc_server, daemon=True)
    grpc_thread.start()
    app.run(host="0.0.0.0", port=8000, debug=True)
else:
    gunicorn_logger = logging.getLogger("gunicorn.error")
    app.logger.handlers = gunicorn_logger.handlers
    app.logger.setLevel(gunicorn_logger.level)
