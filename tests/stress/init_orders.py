import asyncio
import json
import logging

import aiohttp

from params import *

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s - %(asctime)s - %(name)s - %(message)s",
    datefmt="%I:%M:%S",
)
logger = logging.getLogger(__name__)


async def populate_databases():
    async with aiohttp.ClientSession() as session:
        logger.info("Batch creating users ...")
        url: str = (
            f"{PAYMENT_URL}/batch_init/" f"{NUMBER_OF_USERS}/{USER_STARTING_CREDIT}"
        )
        async with session.post(url) as resp:
            await resp.json()
        logger.info("Users created")
        logger.info("Batch creating items ...")
        url: str = (
            f"{STOCK_URL}/batch_init/"
            f"{NUMBER_0F_ITEMS}/{ITEM_STARTING_STOCK}/{ITEM_PRICE}"
        )
        async with session.post(url) as resp:
            await resp.json()
        logger.info("Items created")
        logger.info("Batch creating orders ...")
        url: str = (
            f"{ORDER_URL}/batch_init/"
            f"{NUMBER_OF_ORDERS}/{NUMBER_0F_ITEMS}/{NUMBER_OF_USERS}/{ITEM_PRICE}"
        )
        async with session.post(url) as resp:
            await resp.json()
        logger.info("Orders created")


if __name__ == "__main__":
    asyncio.run(populate_databases())
