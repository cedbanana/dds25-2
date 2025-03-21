import random

from locust import SequentialTaskSet, constant, task, events
from locust.contrib.fasthttp import FastHttpUser

from params import *
from init_orders import populate_databases
import asyncio


# This function will run once, before the test starts
@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    print("Running setup script before the test starts...")
    asyncio.run(populate_databases())


class CreateAndCheckoutOrder(SequentialTaskSet):
    @task
    def user_checks_out_order(self):
        order_id = random.randint(0, NUMBER_OF_ORDERS - 1)
        with self.client.post(
            f"{ORDER_URL}/checkout/{order_id}",
            name="/orders/checkout/[order_id]",
            catch_response=True,
        ) as response:
            if 400 <= response.status_code < 500:
                response.failure(response.text)
            else:
                response.success()


class MicroservicesUser(FastHttpUser):
    # Time to wait (in seconds) after each task set execution before the next run
    wait_time = constant(1)
    # Assign your SequentialTaskSet(s) to this user class
    tasks = {CreateAndCheckoutOrder: 100}
