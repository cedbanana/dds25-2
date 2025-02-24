import logging
from models import Stock
from prometheus_client.core import GaugeMetricFamily
from prometheus_client.registry import Collector
from config import db

logger = logging.getLogger(__name__)

class AvailableStockCollector(Collector):
    def collect(self):
        available_stock = self.get_remaining_stock()

        available_stock_gauge = GaugeMetricFamily('available_stock', 'Total stock available in the system')
        available_stock_gauge.add_metric([], available_stock)

        yield available_stock_gauge


    def get_remaining_stock(self):
        try:
            stock_keys = db.keys("model:*:stock")

            if not stock_keys:
                return 0 

            logger.error(f"Number of individual stock categories: {len(stock_keys)}")

            stock_ids = [key.split(":")[1] for key in stock_keys]

            stock_quantities = db.m_get_attr(stock_ids, "stock", Stock)

            total_stock = 0

            for stock_id, value in stock_quantities.items():
                
                if value is not None:
                    try:
                        item_stock = int(value)  
                        total_stock += item_stock
                    except ValueError:
                        continue
                # else:
                #     logger.error(f"No credit value found for {user_id}, skipping.")

        except Exception as e:
            logger.error(f"Error fetching all stock keys: {e}")
            return 0

        logger.error(f"Total stock remaining: {total_stock}")
        return total_stock
