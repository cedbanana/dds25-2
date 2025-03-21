import logging
from concurrent import futures
import grpc
import grpc.aio
import asyncio

from config import STREAM_KEY, db
from models import Stock, Transaction, TransactionStatus
from proto import stock_pb2, stock_pb2_grpc, common_pb2

import sys
import requests

ORDER_URL = "http://gateway:8000/orders"

root = logging.getLogger()
root.setLevel(logging.DEBUG)

handler = logging.StreamHandler(sys.stdout)
handler.setLevel(logging.DEBUG)
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
handler.setFormatter(formatter)
root.addHandler(handler)

stream_producer = db.get_stream_producer(STREAM_KEY)


class StockServiceServicer(stock_pb2_grpc.StockServiceServicer):
    async def FindItem(self, request, context):
        stock_model = db.get(request.item_id, Stock)
        if stock_model is None:
            await context.abort(
                grpc.StatusCode.NOT_FOUND, f"Item: {request.item_id} not found!"
            )
        return stock_model.to_proto()

    async def AddStock(self, request, context):
        try:
            stock_model = db.get(request.item_id, Stock)
            if stock_model is None:
                return stock_pb2.StockAdjustmentResponse(
                    status=common_pb2.OperationResponse(
                        success=False, error=f"Item: {request.item_id} not found!"
                    ),
                    price=-1,
                )
            db.increment(request.item_id, "stock", request.quantity)
            logging.info(
                "Added %s to item %s; new stock: %s",
                request.quantity,
                request.item_id,
                stock_model.stock,
            )
            return stock_pb2.StockAdjustmentResponse(
                status=common_pb2.OperationResponse(success=True),
                price=stock_model.price * request.quantity,
            )
        except Exception as e:
            logging.exception("Error in AddStock")
            await context.abort(grpc.StatusCode.INTERNAL, str(e))

    async def RemoveStock(self, request, context):
        try:
            item_id = request.item_id

            status = db.get_attr(request.tid, "status", Transaction)

            if status == TransactionStatus.STALE:
                logging.error("Payment failed: transaction is stale")
                return stock_pb2.StockAdjustmentResponse(
                    status=common_pb2.OperationResponse(
                        success=False, error="Transaction is stale!"
                    ),
                    price=-1,
                )

            transaction = Transaction(
                request.tid,
                TransactionStatus.PENDING,
                {item_id: request.quantity},
            )
            db.save(transaction)
            stream_producer.push(tid=request.tid)

            if not db.lte_decrement(item_id, "stock", request.quantity, request.tid):
                logging.error("Insufficient stock for item: %s", request.item_id)
                return stock_pb2.StockAdjustmentResponse(
                    status=common_pb2.OperationResponse(
                        success=False, error="Insufficient stock"
                    ),
                    price=-1,
                )

            logging.info(
                "Removed %s from item %s.",
                request.quantity,
                request.item_id,
            )

            price = db.get_attr(item_id, "price", Stock)

            return stock_pb2.StockAdjustmentResponse(
                status=common_pb2.OperationResponse(success=True),
                price=price * request.quantity,
            )
        except Exception as e:
            logging.exception("Error in RemoveStock")
            await context.abort(grpc.StatusCode.INTERNAL, str(e))

    async def BulkOrder(self, request, context):
        try:
            items = request.items

            status = db.get_attr(request.tid, "status", Transaction)

            if status == TransactionStatus.STALE:
                logging.error("Payment failed: transaction is stale")
                return stock_pb2.StockAdjustmentResponse(
                    status=common_pb2.OperationResponse(
                        success=False, error="Transaction is stale!"
                    ),
                    price=-1,
                )

            transaction = Transaction(
                request.tid,
                TransactionStatus.PENDING,
                {item.id: item.stock for item in items},
            )
            db.save(transaction)
            stream_producer.push(tid=request.tid)

            if not db.m_gte_decrement(
                {item.id: item.stock for item in items}, "stock", request.tid
            ):
                logging.error("Insufficient stock for items")
                return stock_pb2.BulkStockAdjustmentResponse(
                    status=common_pb2.OperationResponse(
                        success=False, error="Insufficient stock for some items"
                    ),
                    total_cost=-1,
                )

            return stock_pb2.BulkStockAdjustmentResponse(
                status=common_pb2.OperationResponse(success=True), total_cost=0
            )
        except Exception as e:
            logging.exception("Error in RemoveStock")
            await context.abort(grpc.StatusCode.INTERNAL, str(e))

    async def BulkRefund(self, request, context):
        try:
            items = request.items

            for item in items:
                stock_model = db.get(item.id, Stock)
                if stock_model is None:
                    return stock_pb2.BulkStockAdjustmentResponse(
                        status=common_pb2.OperationResponse(
                            success=False, error=f"Item: {item.id} not found!"
                        ),
                        total_cost=-1,
                    )

                stock_model.stock = db.increment(item.id, "stock", item.stock)

                logging.info(
                    "Added %s to item %s; new stock: %s",
                    item.stock,
                    item.id,
                    stock_model.stock,
                )

            return stock_pb2.BulkStockAdjustmentResponse(
                status=common_pb2.OperationResponse(success=True), total_cost=-1
            )
        except Exception as e:
            logging.exception("Error in RemoveStock")
            await context.abort(grpc.StatusCode.INTERNAL, str(e))

    async def VibeCheckTransactionStatus(self, request, context):
        count_retries = 0
        transaction = None
        while transaction is None and count_retries < 10:
            logging.warning(
                f"Transaction: {request.tid} not found, retry!",
            )

            transaction = db.get(request.tid, Transaction)
            count_retries += 1
            await asyncio.sleep(0.1)

        if transaction is None:
            stale_transaction = Transaction(
                request.tid,
                TransactionStatus.STALE,
            )
            db.save(stale_transaction)
            logging.warning(
                "Transaction %s marked stale, count: %s", request.tid, count_retries
            )
            return stale_transaction.to_proto()

        unlocked = db.compare_and_set(request.tid, "locked", False, True)

        if not unlocked:
            logging.error("VibeCheck %s failed, transaction is locked", request.tid)
            await context.abort(
                grpc.StatusCode.FAILED_PRECONDITION,
                f"Transaction: {request.tid} is locked!",
            )

        db.delete(transaction)
        # Revert here
        try:
            if not request.success and transaction.status == TransactionStatus.SUCCESS:
                logging.info(
                    "Transaction %s rolling back due to VibeCheck", request.tid
                )
                for k, v in transaction.details.items():
                    db.increment(k, "stock", v)
            elif transaction.status == TransactionStatus.SUCCESS:
                logging.info(
                    "Transaction %s committing thanks to VibeCheck", request.tid
                )
                for k, v in transaction.details.items():
                    db.decrement(k, "committed_stock", v)
        except Exception as e:
            logging.exception("Error in reverting stock")
            await context.abort(grpc.StatusCode.INTERNAL, str(e))
            return common_pb2.TransactionStatus(tid=request.tid, success=False)

        # Successful
        return transaction.to_proto()


async def serve():
    print("Starting gRPC Stock Service")
    # interceptor = PromServerInterceptor()
    server = grpc.aio.server()
    stock_pb2_grpc.add_StockServiceServicer_to_server(StockServiceServicer(), server)
    server.add_insecure_port("[::]:50051")
    await server.start()
    logging.info("gRPC Stock Service started on port 50051")
    await server.wait_for_termination()


if __name__ == "__main__":
    asyncio.run(serve())
    print("Stock Service exiting")
