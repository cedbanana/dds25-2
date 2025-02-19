import atexit
import logging
from flask import Flask
from .config import db
from .endpoints import order_blueprint

app = Flask("order-service")
app.register_blueprint(order_blueprint, url_prefix="/api")


@atexit.register
def close_db_connection():
    db.close()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
else:
    gunicorn_logger = logging.getLogger("gunicorn.error")
    app.logger.handlers = gunicorn_logger.handlers
    app.logger.setLevel(gunicorn_logger.level)
