import os
import sys
import time

# Add common to path if it is not already there
if not os.path.isdir("common"):
    sys.path.append(os.path.join(os.path.dirname(__file__), "..", "common"))

import atexit
import logging
from flask import Flask, request
from prometheus_flask_exporter import PrometheusMetrics  # New import
from werkzeug.middleware.profiler import ProfilerMiddleware
from metrics import REQUEST_IN_PROGRESS, REQUEST_COUNT, REQUEST_LATENCY

from models import Flag, Counter

from service import payment_blueprint
from config import db, PROFILING

app = Flask("payment-service")
app.register_blueprint(payment_blueprint)

from prometheus_client.core import REGISTRY
from custom_collector import PaymentCollector

REGISTRY.register(PaymentCollector())

metrics = PrometheusMetrics(app)

if PROFILING:
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
    REQUEST_COUNT.labels(
        method=request.method, status=response.status_code, path=request.path
    ).inc()
    REQUEST_LATENCY.labels(
        method=request.method, status=response.status_code, path=request.path
    ).observe(request_latency)
    REQUEST_IN_PROGRESS.labels(method=request.method, path=request.path).dec()
    return response


@atexit.register
def cleanup():
    db.close()


if __name__ == "__main__":
    counter = db.get("halted_consumers_counter", Counter)
    if counter is None:
        counter = Counter(id="halted_consumers_counter", count = 0)
        db.save(counter)

    flag = db.get("HALTED", Flag)
    if flag is None:
        flag = Flag(id="HALTED", enabled=False)
        db.save(flag)
        
    app.logger.setLevel(logging.DEBUG)  # Set level to DEBUG to capture all logs
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.DEBUG)  # Log level to DEBUG to capture detailed logs
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    handler.setFormatter(formatter)
    app.logger.addHandler(handler)

    app.run(host="0.0.0.0", port=8000, debug=True)
else:
    counter = db.get("halted_consumers_counter", Counter)
    if counter is None:
        counter = Counter(id="halted_consumers_counter", count = 0)
        db.save(counter)

    flag = db.get("HALTED", Flag)
    if flag is None:
        flag = Flag(id="HALTED", enabled=False)
        db.save(flag)

    gunicorn_logger = logging.getLogger("gunicorn.error")
    app.logger.handlers = gunicorn_logger.handlers
    app.logger.setLevel(gunicorn_logger.level)
    app.logger.setLevel(logging.DEBUG)  # Set level to DEBUG to capture all logs
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.DEBUG)  # Log level to DEBUG to capture detailed logs
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    handler.setFormatter(formatter)
    app.logger.addHandler(handler)
