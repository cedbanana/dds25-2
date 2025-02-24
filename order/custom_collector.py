import logging
from models import Order
from prometheus_client.core import GaugeMetricFamily
from prometheus_client.registry import Collector
from config import db

logger = logging.getLogger(__name__)

class RevenueAndSoldStockCollector(Collector):
    def collect(self):
        order_ids = self.get_order_ids()

        revenue, sold_stock = self.get_revenue_and_sold_stock(order_ids)

        revenue_gauge = GaugeMetricFamily('total_revenue', 'Total money fed into the system through successful order checkouts')
        revenue_gauge.add_metric([], revenue)

        sold_stock_gauge = GaugeMetricFamily('sold_stock', 'Total amount of stock sold in succesful checkouts')
        sold_stock_gauge.add_metric([], sold_stock)

        yield revenue_gauge
        yield sold_stock_gauge

    def get_revenue_and_sold_stock(self, order_ids):
        try:
            sold_stock = 0
            revenue = 0
            for order_id in order_ids:
                order = db.get(order_id, Order)

                revenue += self.get_order_cost(order)
                sold_stock += self.get_order_stock(order)
                # else:
                #     logger.error(f"Skipping invalid or unpaid order {order_id}")
        except Exception as e:
            logger.error(f"Error fetching orders or  costs: {e}")
        

        logger.error(f"Aggregate of received monetary resources ($$$): {revenue}")
        logger.error(f"Aggregate of successfully sold inventory resources ($$$): {sold_stock}")
        return revenue, sold_stock



    def get_order_ids(self):
        try:
            order_keys = db.keys("model:*:paid")
            
            if not order_keys:
                logger.error("No orders found!")
                return []  

            logger.error(f"Number of orders found: {len(order_keys)}")

            order_ids = [key.split(":")[1] for key in order_keys]

            return order_ids
        except Exception as e:
            logger.error(f"Error fetching orders: {e}")
            return []  

    def get_order_cost(self, order):
        if order.total_cost is not None and order.paid:
            return order.total_cost
        else: 
            return 0

    def get_order_stock(self, order):
        quantity = 0
        if order.items is not None and order.paid:
            for item in order.items:
                quantity += (int) (item.split(":")[1])
            return quantity
        else: 
            return 0

    