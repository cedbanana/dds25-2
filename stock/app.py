import sys
import os

# Add common to path if it is not already there
if not os.path.isdir("common"):
    sys.path.append(os.path.join(os.path.dirname(__file__), "..", "common"))

import atexit
import logging
import threading
from flask import Flask
from prometheus_flask_exporter import PrometheusMetrics
from werkzeug.middleware.profiler import ProfilerMiddleware

from service import stock_blueprint
from config import db
from rpc import grpc_server

app = Flask("stock-service")


app.register_blueprint(stock_blueprint)
app.wsgi_app = ProfilerMiddleware(
    app.wsgi_app, profile_dir="profiles/flask", stream=None
)


@atexit.register
def cleanup():
    db.close()


metrics = PrometheusMetrics(app)
grpc_thread = threading.Thread(target=grpc_server, daemon=True)
grpc_thread.start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
else:
    gunicorn_logger = logging.getLogger("gunicorn.error")
    app.logger.handlers = gunicorn_logger.handlers
    app.logger.setLevel(gunicorn_logger.level)
