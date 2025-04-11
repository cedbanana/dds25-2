import sys
import os
import time
import requests
import asyncio

from config import AsyncPaymentClient, AsyncStockClient
from proto.common_pb2 import Empty
# Add common to path if it is not already there
if not os.path.isdir("common"):
    sys.path.append(os.path.join(os.path.dirname(__file__), "..", "common"))


from config import PAYMENT_RPC_ADDR, STOCK_RPC_ADDR, ORDER_ADDR

async def prepare_snapshot():
    print("preparing snapshot")
    sys.stdout.flush()
    # ORDER 
    requests.post(ORDER_ADDR + "/prepare_rollback")
    async with AsyncStockClient() as stock_client, AsyncPaymentClient() as payment_client: 
        await stock_client.PrepareSnapshot(Empty())
        await payment_client.PrepareSnapshot(Empty())


async def check_ready():
    print("checking if microservices be ready for the snapshot...")
    sys.stdout.flush()
    async with AsyncStockClient() as stock_client, AsyncPaymentClient() as payment_client: 
       
        stock_finished = False 
        payment_finished = False

        while not stock_finished or not payment_finished:
            time.sleep(0.1)

            if not stock_finished:
                stock_resp = await stock_client.CheckSnapshotReady(Empty())
                if stock_resp.success:
                    stock_finished = True
                else:
                    print("stock not ready yet")
                    sys.stdout.flush()
            if not payment_finished:
                payment_resp = await payment_client.CheckSnapshotReady(Empty())
                if payment_resp.success:
                    payment_finished = True
                else:
                    print("payment not ready yet")
                    sys.stdout.flush()

    print("microservices finally ready for snapshot!")


async def snapshot():
    print("sending requests for snapshots...")
    sys.stdout.flush()

    requests.post(ORDER_ADDR + "/snapshot")
    async with AsyncStockClient() as stock_client, AsyncPaymentClient() as payment_client: 
        await stock_client.Snapshot(Empty())
        await payment_client.Snapshot(Empty())
    
    print("snapshot taken :)")
    sys.stdout.flush()

async def finish_snapshot():
    print("restoring microservice freedom")
    sys.stdout.flush()

    requests.post(ORDER_ADDR + "/continue")

    async with AsyncStockClient() as stock_client, AsyncPaymentClient() as payment_client: 
        await stock_client.ContinueConsuming(Empty())
        await payment_client.ContinueConsuming(Empty())

    print("restored microservice freedom!")
    sys.stdout.flush()

async def start_scheduler():
    while True:
        try:
            await prepare_snapshot()
            await check_ready()
            await snapshot()
            await finish_snapshot()
            await asyncio.sleep(10) # seconds 
        except Exception as e:
            print(f"Error: {e}")
            sys.stdout.flush()

skull_art = r"""
              .                                                      .
        .n                   .                 .                  n.
  .   .dP                  dP                   9b                 9b.    .
 4    qXb         .       dX                     Xb       .        dXp     t
dX.    9Xb      .dXb    __                         __    dXb.     dXP     .Xb
9XXb._       _.dXXXXb dXXXXbo.                 .odXXXXb dXXXXb._       _.dXXP
 9XXXXXXXXXXXXXXXXXXXVXXXXXXXXOo.           .oOXXXXXXXXVXXXXXXXXXXXXXXXXXXXP
  `9XXXXXXXXXXXXXXXXXXXXX'~   ~`OOO8b   d8OOO'~   ~`XXXXXXXXXXXXXXXXXXXXXP'
    `9XXXXXXXXXXXP' `9XX'   DIE    `98v8P'  HUMAN   `XXP' `9XXXXXXXXXXXP'
        ~~~~~~~       9X.          .db|db.          .XP       ~~~~~~~
                        )b.  .dbo.dP'`v'`9b.odb.  .dX(
                      ,dXXXXXXXXXXXb     dXXXXXXXXXXXb.
                     dXXXXXXXXXXXP'   .   `9XXXXXXXXXXXb
                    dXXXXXXXXXXXXb   d|b   dXXXXXXXXXXXXb
                    9XXb'   `XXXXXb.dX|Xb.dXXXXX'   `dXXP
                     `'      9XXXXXX(   )XXXXXXP      `'
                              XXXX X.`v'.X XXXX
                              XP^X'`b   d'`X^XX
                              X. 9  `   '  P )X
                              `b  `       '  d'
                               `             '
"""

if __name__ == "__main__":
    print(skull_art)
    print("STARTING THE CRON JOB....................... (SNAPSHOTS)")
    time.sleep(5)
    sys.stdout.flush()
    asyncio.run(start_scheduler())
