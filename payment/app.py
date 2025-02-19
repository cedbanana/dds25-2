import os
import atexit
import logging
from flask import Flask
from endpoints import user_blueprint
from .config import db

app = Flask("payment-service")

# Register the Blueprint
app.register_blueprint(user_blueprint, url_prefix="/api")


atexit.register(db.close)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
else:
    gunicorn_logger = logging.getLogger("gunicorn.error")
    app.logger.handlers = gunicorn_logger.handlers
    app.logger.setLevel(gunicorn_logger.level)
