import asyncio
from collections import Counter

import aiohttp
from params import (
    NUMBER_OF_USERS,
    USER_STARTING_CREDIT,
    ITEM_STARTING_STOCK,
    ITEM_PRICE,
    PAYMENT_URL,
    STOCK_URL,
)
from populate import populate_databases
from checkout import run_transactions, get_final_order_statuses
from testlogger import setup_logger

logger = setup_logger(__name__)


async def fetch_user_credit(session, user_id: str) -> int:
    url = f"{PAYMENT_URL}/find_user/{user_id}"
    async with session.get(url) as resp:
        data = await resp.json()
        return data["credit"]


async def fetch_item_stock(session, item: str) -> int:
    url = f"{STOCK_URL}/find/{item}"
    async with session.get(url) as resp:
        data = await resp.json()
        return data["stock"]


async def fetch_streamsize(session, base_url: str) -> int:
    url = f"{base_url}/streamsize"
    async with session.get(url) as resp:
        data = await resp.json()
        return data.get("size", 0)


async def verify_consistency(checkout_results, user_ids, item_ids):
    successful_checkouts = [order["paid"] for order in checkout_results]
    success_count = sum(successful_checkouts)
    logger.debug(
        f"Total successful checkouts: {success_count}", extra={"test_stage": "validate"}
    )

    # Expected total user funds: initial funds minus cost of all successful checkouts.
    expected_total_credit = (NUMBER_OF_USERS * USER_STARTING_CREDIT) - (
        success_count * ITEM_PRICE
    )

    # Count successful checkouts per item.
    item_success_count = Counter()
    for order in checkout_results:
        for item in order["items"]:
            item_success_count[item] += order["paid"]
    logger.debug(f"Items sold: {item_success_count}", extra={"test_stage": "validate"})

    async with aiohttp.ClientSession() as session:
        # Fetch and log streamsize for payment and stock microservices.
        payment_streamsize, stock_streamsize = await asyncio.gather(
            fetch_streamsize(session, PAYMENT_URL), fetch_streamsize(session, STOCK_URL)
        )
        logger.debug(
            f"Stream sizes : Payment:{payment_streamsize}, Stock:{stock_streamsize}",
            extra={"test_stage": "validate"},
        )

        consistent = True
        if payment_streamsize > 0 or stock_streamsize > 0:
            logger.error(
                "Streams are not depleted!",
                extra={
                    "microservice": "Rollback",
                    "expected": 0,
                    "real": stock_streamsize + payment_streamsize,
                },
            )
            consistent = False

        # Verify user funds.
        user_credits = await asyncio.gather(
            *(fetch_user_credit(session, user) for user in user_ids)
        )
        actual_total_credit = sum(user_credits)

        if actual_total_credit != expected_total_credit:
            logger.error(
                "",
                extra={
                    "microservice": "UserFunds",
                    "expected": expected_total_credit,
                    "real": actual_total_credit,
                },
            )
            consistent = False
        else:
            logger.info(
                "",
                extra={
                    "microservice": "UserFunds",
                    "expected": expected_total_credit,
                    "real": actual_total_credit,
                },
            )

        # Verify stock for each item.
        for item in item_ids:
            current_stock = await fetch_item_stock(session, item)
            expected_stock = ITEM_STARTING_STOCK - item_success_count.get(item, 0)
            if current_stock != expected_stock:
                logger.error(
                    "",
                    extra={
                        "microservice": f"Stock-{item}",
                        "expected": expected_stock,
                        "real": current_stock,
                    },
                )
                consistent = False
            else:
                logger.info(
                    "",
                    extra={
                        "microservice": f"Stock-{item}",
                        "expected": expected_stock,
                        "real": current_stock,
                    },
                )

        return consistent


async def main():
    # Populate the databases first.
    item_ids, user_ids = await populate_databases()
    # Execute transactions and track each order.
    orders = await run_transactions(item_ids, user_ids)
    # Log list of all created order IDs.
    order_ids = [order["order_id"] for order in orders]
    logger.debug(
        f"Total orders processed: {len(order_ids)}", extra={"test_stage": "checkout"}
    )

    consistent = False
    while not consistent:
        print("")
        checkout_results = await get_final_order_statuses(orders)
        # Verify if any money or stock was lost, and print streamsize info.
        consistent = await verify_consistency(checkout_results, user_ids, item_ids)
        input("--> Press Enter to re-check consistency...")


if __name__ == "__main__":
    asyncio.run(main())
