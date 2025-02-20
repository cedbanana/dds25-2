import logging
from concurrent import futures
import grpc

from config import db
from models import Stock
from proto import stock_pb2_grpc, common_pb2


class StockServiceServicer(stock_pb2_grpc.StockServiceServicer):
    def FindItem(self, request, context):
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

    def AddStock(self, request, context):
        try:
            stock_model = db.get(request.item_id, Stock)
            if stock_model is None:
                context.abort(
                    grpc.StatusCode.NOT_FOUND, f"Item: {request.item_id} not found!"
                )
            stock_model.stock += request.quantity
            db.save(stock_model)
            logging.info(
                "Added %s to item %s; new stock: %s",
                request.quantity,
                request.item_id,
                stock_model.stock,
            )
            return common_pb2.Empty()
        except Exception as e:
            logging.exception("Error in AddStock")
            context.abort(grpc.StatusCode.INTERNAL, str(e))

    def RemoveStock(self, request, context):
        try:
            stock_model = db.get(request.item_id, Stock)
            if stock_model is None:
                context.abort(
                    grpc.StatusCode.NOT_FOUND, f"Item: {request.item_id} not found!"
                )
            stock_model.stock -= request.quantity
            if stock_model.stock < 0:
                context.abort(grpc.StatusCode.FAILED_PRECONDITION, "Insufficient stock")
            db.save(stock_model)
            logging.info(
                "Removed %s from item %s; new stock: %s",
                request.quantity,
                request.item_id,
                stock_model.stock,
            )
            return common_pb2.Empty()
        except Exception as e:
            logging.exception("Error in RemoveStock")
            context.abort(grpc.StatusCode.INTERNAL, str(e))


def grpc_server():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    stock_pb2_grpc.add_StockServiceServicer_to_server(StockServiceServicer(), server)
    server.add_insecure_port("[::]:50051")
    server.start()
    logging.info("gRPC Stock Service started on port 50051")
    server.wait_for_termination()
