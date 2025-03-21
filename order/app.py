import sys
import os
import time
import logging
import atexit

from quart import Quart, request
from config import db, PROFILING
from service import order_blueprint

from prometheus_flask_exporter import (
    PrometheusMetrics,
)
from werkzeug.middleware.profiler import ProfilerMiddleware
from metrics import REQUEST_IN_PROGRESS, REQUEST_COUNT, REQUEST_LATENCY

app = Quart("order-service")
app.register_blueprint(order_blueprint)

from prometheus_client.core import REGISTRY
from custom_collector import RevenueAndSoldStockCollector

REGISTRY.register(RevenueAndSoldStockCollector())

if PROFILING:
    app.asgi_app = ProfilerMiddleware(
        app.asgi_app, profile_dir="profiles/quart", stream=None
    )


# @app.before_request
# async def before_request():
#     request.start_time = time.time()
#     REQUEST_IN_PROGRESS.labels(method=request.method, path=request.path).inc()
#
#
# @app.after_request
# async def after_request(response):
#     request_latency = time.time() - request.start_time
#     REQUEST_COUNT.labels(
#         method=request.method, status=response.status_code, path=request.path
#     ).inc()
#     REQUEST_LATENCY.labels(
#         method=request.method, status=response.status_code, path=request.path
#     ).observe(request_latency)
#     REQUEST_IN_PROGRESS.labels(method=request.method, path=request.path).dec()
#     return response


@atexit.register
def cleanup():
    db.close()
    # payment_channel.close()
    # stock_channel.close()


# metrics = PrometheusMetrics(app)

if __name__ == "__main__":
    app.logger.setLevel(logging.DEBUG)
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    handler.setFormatter(formatter)
    app.logger.addHandler(handler)

    app.run(host="0.0.0.0", port=8000, debug=True)
else:
    gunicorn_logger = logging.getLogger("gunicorn.error")
    app.logger.handlers = gunicorn_logger.handlers
    app.logger.setLevel(gunicorn_logger.level)
    app.logger.setLevel(logging.DEBUG)
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    handler.setFormatter(formatter)
    app.logger.addHandler(handler)
