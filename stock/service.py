import uuid
import logging
from concurrent import futures

import grpc
from msgspec import msgpack

from config import db
from db.models import StockValue
from db.client import DatabaseError

from proto import stock_pb2, stock_pb2_grpc
from proto import common_pb2


class StockService(stock_pb2_grpc.StockServiceServicer):
    def CreateItem(self, request, context):
        try:
            # Create a unique item id and initialize with zero stock.
            item_id = str(uuid.uuid4())
            stock_value = StockValue(stock=0, price=request.price)
            encoded_value = msgpack.encode(stock_value)
            db.set(item_id, encoded_value)
            logging.debug(f"Created item with id: {item_id}")
            return stock_pb2.CreateItemResponse(item_id=item_id)
        except DatabaseError as e:
            context.abort(grpc.StatusCode.INTERNAL, f"Database error: {e}")

    def FindItem(self, request, context):
        try:
            entry = db.get(request.item_id)
            if entry is None:
                context.abort(
                    grpc.StatusCode.NOT_FOUND, f"Item: {request.item_id} not found"
                )
            try:
                stock_value = msgpack.decode(entry, type=StockValue)
            except Exception:
                context.abort(grpc.StatusCode.INTERNAL, "Failed to decode item data")
            return stock_pb2.Item(
                item_id=request.item_id,
                stock=stock_value.stock,
                price=stock_value.price,
            )
        except DatabaseError as e:
            context.abort(grpc.StatusCode.INTERNAL, f"Database error: {e}")

    def AddStock(self, request, context):
        try:
            entry = db.get(request.item_id)
            if entry is None:
                context.abort(
                    grpc.StatusCode.NOT_FOUND, f"Item: {request.item_id} not found"
                )
            try:
                stock_value = msgpack.decode(entry, type=StockValue)
            except Exception:
                context.abort(grpc.StatusCode.INTERNAL, "Failed to decode item data")
            stock_value.stock += request.quantity
            try:
                db.set(request.item_id, msgpack.encode(stock_value))
            except DatabaseError as e:
                context.abort(grpc.StatusCode.INTERNAL, f"Database error: {e}")
            return common_pb2.Empty()
        except DatabaseError as e:
            context.abort(grpc.StatusCode.INTERNAL, f"Database error: {e}")

    def RemoveStock(self, request, context):
        try:
            entry = db.get(request.item_id)
            if entry is None:
                context.abort(
                    grpc.StatusCode.NOT_FOUND, f"Item: {request.item_id} not found"
                )
            try:
                stock_value = msgpack.decode(entry, type=StockValue)
            except Exception:
                context.abort(grpc.StatusCode.INTERNAL, "Failed to decode item data")
            new_stock = stock_value.stock - request.quantity
            if new_stock < 0:
                context.abort(
                    grpc.StatusCode.INVALID_ARGUMENT,
                    f"Item: {request.item_id} stock cannot be reduced below zero",
                )
            stock_value.stock = new_stock
            try:
                db.set(request.item_id, msgpack.encode(stock_value))
            except DatabaseError as e:
                context.abort(grpc.StatusCode.INTERNAL, f"Database error: {e}")
            return common_pb2.Empty()
        except DatabaseError as e:
            context.abort(grpc.StatusCode.INTERNAL, f"Database error: {e}")

    def BatchInitItems(self, request, context):
        try:
            kv_pairs = {}
            for i in range(request.num_items):
                key = str(i)
                stock_value = StockValue(
                    stock=request.starting_stock, price=request.item_price
                )
                kv_pairs[key] = msgpack.encode(stock_value)
            try:
                db.mset(kv_pairs)
            except DatabaseError as e:
                context.abort(grpc.StatusCode.INTERNAL, f"Database error: {e}")
            return common_pb2.Empty()
        except Exception as e:
            context.abort(grpc.StatusCode.INTERNAL, f"Unexpected error: {e}")


def grpc_server():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    stock_pb2_grpc.add_StockServiceServicer_to_server(StockService(), server)
    server.add_insecure_port("[::]:50051")
    server.start()
    logging.info("gRPC Stock Service started on port 50051")
    server.wait_for_termination()
