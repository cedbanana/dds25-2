import asyncio
import os
import random
import shutil

import aiohttp
from params import TMP_FOLDER_PATH, NUMBER_OF_ORDERS, ORDER_URL
from populate import populate_databases
from testlogger import setup_logger

logger = setup_logger(__name__)


async def create_order(session, user_id: str) -> str:
    url = f"{ORDER_URL}/create/{user_id}"
    async with session.post(url) as resp:
        data = await resp.json()
        return data["order_id"]


async def add_item_to_order(session, order_id: str, item_id) -> None:
    url = f"{ORDER_URL}/addItem/{order_id}/{item_id}/1"
    async with session.post(url) as resp:
        return resp.status


async def checkout_order(session, order_id: str, user_id: str, log_file):
    url = f"{ORDER_URL}/checkout/{order_id}"
    async with session.post(url) as resp:
        status = resp.status
        result = "SUCCESS" if status < 400 else "FAIL"
        log_file.write(f"Order {order_id} for user {user_id}: {result}\n")
        return status


async def run_transactions(item_ids, user_ids):
    orders = []
    async with aiohttp.ClientSession() as session:
        logger.debug(
            "Creating orders and adding items...", extra={"test_stage": "checkout"}
        )
        for _ in range(NUMBER_OF_ORDERS):
            user = random.choice(user_ids)
            order_id = await create_order(session, user)
            chosen_item = random.choice(item_ids)
            await add_item_to_order(session, order_id, chosen_item)
            orders.append({"order_id": order_id, "user": user, "item": chosen_item})
        logger.debug(f"Created {len(orders)} orders.", extra={"test_stage": "checkout"})
        logger.debug("Performing checkouts...", extra={"test_stage": "checkout"})
        # Fire checkout requests concurrently.
        await asyncio.gather(
            *(
                session.post(f"{ORDER_URL}/checkout/{order['order_id']}")
                for order in orders
            )
        )
        logger.debug("Checkout requests sent.", extra={"test_stage": "checkout"})
    return orders


async def get_final_order_statuses(orders):
    async with aiohttp.ClientSession() as session:
        logger.debug(
            "Fetching final order statuses...", extra={"test_stage": "validate"}
        )

        # For each order, fetch its status using the find_order endpoint.
        async def fetch_order_status(order):
            order_id = order["order_id"]
            url = f"{ORDER_URL}/find_order/{order_id}"
            async with session.get(url) as resp:
                try: 
                    data = await resp.json()
                    order["paid"] = data.get("paid", 0)
                    order["total_cost"] = data.get("total_cost", 0)
                    order["items"] = data.get("items", [])
                    return order
                except Exception as e:
                    print(e)
                    print(resp)

        checkout_results = await asyncio.gather(
            *(fetch_order_status(order) for order in orders)
        )
    return checkout_results


async def main():
    item_ids, user_ids = await populate_databases()
    await run_transactions(item_ids, user_ids)
    if os.path.exists(TMP_FOLDER_PATH):
        shutil.rmtree(TMP_FOLDER_PATH)
    logger.status("Test completed.", extra={"test_stage": "complete"})


if __name__ == "__main__":
    asyncio.run(main())
