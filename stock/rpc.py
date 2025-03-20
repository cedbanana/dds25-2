import logging
from concurrent import futures
import grpc
import grpc.aio
from database import TransactionConfig
from pyignite.datatypes import TransactionConcurrency, TransactionIsolation

from config import db
from models import Stock
from proto import stock_pb2, stock_pb2_grpc, common_pb2
from py_grpc_prometheus.prometheus_server_interceptor import PromServerInterceptor


class StockServiceServicer(stock_pb2_grpc.StockServiceServicer):
    async def FindItem(self, request, context):
        try:
            stock_model = db.get(request.item_id, Stock)
            if stock_model is None:
                context.abort(
                    grpc.StatusCode.NOT_FOUND, f"Item: {request.item_id} not found!"
                )
            return stock_model.to_proto()
        except Exception as e:
            logging.exception("Error in FindItem")
            context.abort(grpc.StatusCode.INTERNAL, str(e))

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
            context.abort(grpc.StatusCode.INTERNAL, str(e))

    async def RemoveStock(self, request, context):
        try:
            item_id = request.item_id

            if not db.lte_decrement(item_id, "stock", request.quantity):
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
            context.abort(grpc.StatusCode.INTERNAL, str(e))

    async def BulkOrder(self, request, context):
        try:
            items = request.items
            cost = 0

            prices = db.m_get_attr([item.id for item in items], "price", Stock)
            if prices is None:
                return stock_pb2.BulkStockAdjustmentResponse(
                    status=common_pb2.OperationResponse(
                        success=False, error="Item not found!"
                    ),
                    total_cost=-1,
                )

            cost = sum([prices[item.id] * item.stock for item in items])

            if not db.m_gte_decrement({item.id: item.stock for item in items}, "stock"):
                logging.error("Insufficient stock for items")
                return stock_pb2.BulkStockAdjustmentResponse(
                    status=common_pb2.OperationResponse(
                        success=False, error="Insufficient stock for some items"
                    ),
                    total_cost=-1,
                )

            return stock_pb2.BulkStockAdjustmentResponse(
                status=common_pb2.OperationResponse(success=True), total_cost=cost
            )
        except Exception as e:
            logging.exception("Error in RemoveStock")
            context.abort(grpc.StatusCode.INTERNAL, str(e))

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
            context.abort(grpc.StatusCode.INTERNAL, str(e))


async def grpc_server():
    #interceptor = PromServerInterceptor()
    server = grpc.aio.server(
        futures.ThreadPoolExecutor(max_workers=10), 
    )
    stock_pb2_grpc.add_StockServiceServicer_to_server(StockServiceServicer(), server)
    server.add_insecure_port("[::]:50051")
    await server.start()
    logging.info("gRPC Stock Service started on port 50051")
    await server.wait_for_termination()
