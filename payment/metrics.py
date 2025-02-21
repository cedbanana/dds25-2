from prometheus_client import Gauge

# Define a Gauge metric to track the total amount of money in the system
total_money_metric = Gauge(
    "total_money_in_system", "Total amount of money in the system"
)
