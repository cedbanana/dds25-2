from prometheus_client import Gauge, Counter, Histogram

TOTAL_MONEY = Gauge(
    "total_money_in_system", "Total amount of money in the system"
)

REQUEST_COUNT = Counter('http_request_total', 'Total HTTP Requests', ['method', 'status', 'path'])
REQUEST_LATENCY = Histogram('http_request_latency', 'HTTP Request Latency', ['method', 'status', 'path'])
REQUEST_IN_PROGRESS = Gauge('http_requests_in_progress', 'HTTP Requests in progress', ['method', 'path'])
