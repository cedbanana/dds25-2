import atexit
import logging
from flask import Flask
import threading
from .config import db
from .endpoints import stock_blueprint
from .service import grpc_server

app = Flask("stock-service")

# Register the Blueprint
app.register_blueprint(stock_blueprint, url_prefix="/api")


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
