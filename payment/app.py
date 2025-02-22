import os
import sys
import time

# Add common to path if it is not already there
if not os.path.isdir("common"):
    sys.path.append(os.path.join(os.path.dirname(__file__), "..", "common"))

import atexit
import logging
import threading
from flask import Flask, request
from prometheus_flask_exporter import PrometheusMetrics  # New import
from werkzeug.middleware.profiler import ProfilerMiddleware
from metrics import REQUEST_COUNT, REQUEST_LATENCY, REQUEST_IN_PROGRESS

from service import payment_blueprint
from config import db
from rpc import grpc_server

app = Flask("payment-service")

metrics = PrometheusMetrics(app)

app.register_blueprint(payment_blueprint)
app.wsgi_app = ProfilerMiddleware(
    app.wsgi_app, profile_dir="profiles/flask", stream=None
)

@app.before_request
def before_request():
    request.start_time = time.time()
    REQUEST_IN_PROGRESS.labels(method=request.method, path=request.path).inc()

@app.after_request
def after_request(response):
    request_latency = time.time() - request.start_time
    REQUEST_COUNT.labels(method=request.method, status=response.status_code, path=request.path).inc()
    REQUEST_LATENCY.labels(method=request.method, status=response.status_code, path=request.path).observe(request_latency)
    REQUEST_IN_PROGRESS.labels(method=request.method, path=request.path).dec()
    return response


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
