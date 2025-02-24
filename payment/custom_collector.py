import logging
from models import User
from prometheus_client.core import GaugeMetricFamily
from prometheus_client.registry import Collector
from config import db

logger = logging.getLogger(__name__)

class PaymentCollector(Collector):
    def collect(self):
        total_credit = self.get_total_credit()
        logger.error(f"Total credit calculated: {total_credit}")

        credit_gauge = GaugeMetricFamily('total_user_credit', 'Total credit held by all users')
        credit_gauge.add_metric([], total_credit)

        yield credit_gauge


    def get_total_credit(self):
        try:
            user_keys = db.keys("model:*:credit")

            if not user_keys:
                return 0 

            logger.error(f"Number of users found: {len(user_keys)}")

            user_ids = [key.split(":")[1] for key in user_keys]

            credit_values = db.m_get_attr(user_ids, "credit", User)

            total_credit = 0

            for user_id, value in credit_values.items():
                
                if value is not None:
                    try:
                        credit_value_int = int(value)  
                        total_credit += credit_value_int
                    except ValueError:
                        continue
                # else:
                #     logger.error(f"No credit value found for {user_id}, skipping.")

        except Exception as e:
            logger.error(f"Error fetching all user keys: {e}")
            return 0

        logger.error(f"Total credit across all users: {total_credit}")
        return total_credit