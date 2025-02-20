import uuid
import grpc
from msgspec import msgpack

from .db.client import DatabaseError
from .db.models import UserValue
from .config import db

from proto import payment_pb2
from proto import payment_pb2_grpc
from proto import common_pb2

from concurrent import futures
from proto import order_pb2_grpc
from .service import PaymentService


class PaymentServicer(payment_pb2_grpc.PaymentServiceServicer):
    def CreateUser(self, request, context):
        """
        Creates a new user with zero credit.
        """
        try:
            user_id = str(uuid.uuid4())
            value = msgpack.encode(UserValue(credit=0))
            db.set(user_id, value)
        except DatabaseError:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details("DB error during user creation")
            return payment_pb2.CreateUserResponse()
        return payment_pb2.CreateUserResponse(user_id=user_id)

    def AddFunds(self, request, context):
        """
        Adds funds to an existing user's credit.
        """
        try:
            entry = db.get(request.user_id)
        except DatabaseError:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details("DB error")
            return common_pb2.Empty()
        if not entry:
            context.set_code(grpc.StatusCode.NOT_FOUND)
            context.set_details(f"User: {request.user_id} not found")
            return common_pb2.Empty()
        try:
            user = msgpack.decode(entry, type=UserValue)
        except msgpack.DecodeError:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details("Invalid user data format")
            return common_pb2.Empty()

        user.credit += request.amount

        try:
            db.set(request.user_id, msgpack.encode(user))
        except DatabaseError:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details("DB error")
            return common_pb2.Empty()

        return common_pb2.Empty()

    def ProcessPayment(self, request, context):
        """
        Processes a payment by subtracting the specified amount from the user's credit.
        Fails if the user does not have enough funds.
        """
        try:
            entry = db.get(request.user_id)
        except DatabaseError:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details("DB error")
            return payment_pb2.PaymentResponse(success=False)
        if not entry:
            context.set_code(grpc.StatusCode.NOT_FOUND)
            context.set_details(f"User: {request.user_id} not found")
            return payment_pb2.PaymentResponse(success=False)
        try:
            user = msgpack.decode(entry, type=UserValue)
        except msgpack.DecodeError:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details("Invalid user data format")
            return payment_pb2.PaymentResponse(success=False)

        if user.credit < request.amount:
            context.set_code(grpc.StatusCode.FAILED_PRECONDITION)
            context.set_details("Insufficient funds")
            return payment_pb2.PaymentResponse(success=False)

        user.credit -= request.amount

        try:
            db.set(request.user_id, msgpack.encode(user))
        except DatabaseError:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details("DB error")
            return payment_pb2.PaymentResponse(success=False)

        return payment_pb2.PaymentResponse(success=True)

    def BatchInitUsers(self, request, context):
        """
        Batch initializes users by creating `num_users` with a given starting credit.
        """
        kv_pairs = {
            str(i): msgpack.encode(UserValue(credit=request.starting_credit))
            for i in range(request.num_users)
        }
        try:
            db.mset(kv_pairs)
        except DatabaseError:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details("DB error during batch initialization")
            return common_pb2.Empty()
        return common_pb2.Empty()


def grpc_server():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    order_pb2_grpc.add_OrderServiceServicer_to_server(PaymentService(), server)
    server.add_insecure_port("[::]:50051")
    print("Starting OrderService gRPC server on port 50051...")
    server.start()
    server.wait_for_termination()
