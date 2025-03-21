import asyncio
from typing import List

import aiohttp
from params import (
    NUMBER_OF_ITEMS,
    ITEM_STARTING_STOCK,
    ITEM_PRICE,
    NUMBER_OF_USERS,
    USER_STARTING_CREDIT,
    PAYMENT_URL,
    STOCK_URL,
)
from testlogger import setup_logger

logger = setup_logger(__name__)


async def post_and_get_status(session, url: str) -> int:
    async with session.post(url) as resp:
        return resp.status


async def post_and_get_field(session, url: str, field: str):
    async with session.post(url) as resp:
        data = await resp.json()
        return data[field]


async def create_items(session: aiohttp.ClientSession) -> List[str]:
    logger.debug("Starting creation of items", extra={"test_stage": "populate"})
    # Create items.
    tasks = [
        post_and_get_field(session, f"{STOCK_URL}/item/create/{ITEM_PRICE}", "item_id")
        for _ in range(NUMBER_OF_ITEMS)
    ]
    item_ids = await asyncio.gather(*tasks)
    # Add stock for each item.
    tasks = [
        post_and_get_status(session, f"{STOCK_URL}/add/{item_id}/{ITEM_STARTING_STOCK}")
        for item_id in item_ids
    ]
    await asyncio.gather(*tasks)
    logger.debug("Finished creation of items", extra={"test_stage": "populate"})
    return item_ids


async def create_users(session: aiohttp.ClientSession) -> List[str]:
    logger.debug("Starting creation of users", extra={"test_stage": "populate"})
    # Create users.
    tasks = [
        post_and_get_field(session, f"{PAYMENT_URL}/create_user", "user_id")
        for _ in range(NUMBER_OF_USERS)
    ]
    user_ids = await asyncio.gather(*tasks)
    # Add funds to each user.
    tasks = [
        post_and_get_status(
            session, f"{PAYMENT_URL}/add_funds/{user_id}/{USER_STARTING_CREDIT}"
        )
        for user_id in user_ids
    ]
    await asyncio.gather(*tasks)
    logger.debug("Finished creation of users", extra={"test_stage": "populate"})
    return user_ids


async def populate_databases():
    async with aiohttp.ClientSession() as session:
        logger.debug("Populating items...", extra={"test_stage": "populate"})
        item_ids = await create_items(session)
        logger.debug("Populating users...", extra={"test_stage": "populate"})
        user_ids = await create_users(session)
    return item_ids, user_ids


if __name__ == "__main__":
    asyncio.run(populate_databases())
