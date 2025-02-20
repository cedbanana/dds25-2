import logging
from concurrent import futures
import grpc

from config import db
from models import User
from proto import payment_pb2, payment_pb2_grpc, common_pb2


class PaymentServiceServicer(payment_pb2_grpc.PaymentServiceServicer):
    def AddFunds(self, request, context):
        try:
            user_model = db.get(request.user_id, User)
            if user_model is None:
                context.abort(
                    grpc.StatusCode.NOT_FOUND, f"User: {request.user_id} not found!"
                )
            user_model.credit += request.amount
            db.save(user_model)
            logging.info(
                "Added funds: %s to user %s; new credit: %s",
                request.amount,
                request.user_id,
                user_model.credit,
            )
            return common_pb2.Empty()
        except Exception as e:
            logging.exception("Error in AddFunds")
            context.abort(grpc.StatusCode.INTERNAL, str(e))

    def ProcessPayment(self, request, context):
        print("AAAAAAAAAAAAA")
        try:
            user_model = db.get(request.user_id, User)
            if user_model is None:
                context.abort(
                    grpc.StatusCode.NOT_FOUND, f"User: {request.user_id} not found!"
                )
            if user_model.credit < request.amount:
                logging.error(
                    "Payment failed for user %s: insufficient credit", request.user_id
                )
                return payment_pb2.PaymentResponse(success=False)
            user_model.credit -= request.amount
            db.save(user_model)
            logging.info(
                "Processed payment for user %s; new credit: %s",
                request.user_id,
                user_model.credit,
            )
            return payment_pb2.PaymentResponse(success=True)
        except Exception as e:
            logging.exception("Error in ProcessPayment")
            context.abort(grpc.StatusCode.INTERNAL, str(e))

    def FindUser(self, request, context):
        try:
            user_model = db.get(request.user_id, User)
            if user_model is None:
                context.abort(
                    grpc.StatusCode.NOT_FOUND, f"User: {request.user_id} not found!"
                )
            return payment_pb2.FindUserResponse(user=user_model.to_proto())
        except Exception as e:
            logging.exception("Error in FindUser")
            context.abort(grpc.StatusCode.INTERNAL, str(e))


def grpc_server():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    payment_pb2_grpc.add_PaymentServiceServicer_to_server(
        PaymentServiceServicer(), server
    )
    server.add_insecure_port("[::]:50052")
    server.start()
    logging.info("gRPC Payment Service started on port 50052")
    server.wait_for_termination()
