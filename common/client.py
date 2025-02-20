from proto.payment_pb2 import PaymentRequest
from proto.stock_pb2 import ItemRequest, StockAdjustment
from proto.payment_pb2_grpc import PaymentServiceStub
import grpc


def run():
    with grpc.insecure_channel("localhost:50054") as channel:
        stub = PaymentServiceStub(channel)
        response = stub.ProcessPayment(PaymentRequest(user_id="aaa", amount=2))
        print(response)


run()
