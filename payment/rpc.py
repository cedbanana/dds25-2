import logging
from concurrent import futures
from database import TransactionConfig
import grpc
import grpc.aio
from config import db
from models import User
from proto import payment_pb2, payment_pb2_grpc, common_pb2
from py_grpc_prometheus.prometheus_server_interceptor import PromServerInterceptor


class PaymentServiceServicer(payment_pb2_grpc.PaymentServiceServicer):
    def AddFunds(self, request, context):
        try:
            user_model = db.get(request.user_id, User)
            if user_model is None:
                # Instead of aborting, return an error response.
                return common_pb2.OperationResponse(
                    success=False, error=f"User: {request.user_id} not found!"
                )

            user_model.credit = db.increment(request.user_id, "credit", request.amount)
            logging.info(
                "Added funds: %s to user %s; new credit: %s",
                request.amount,
                request.user_id,
                user_model.credit,
            )
            return common_pb2.OperationResponse(success=True)
        except Exception as e:
            logging.exception("Error in AddFunds")
            context.abort(grpc.StatusCode.INTERNAL, str(e))

    def ProcessPayment(self, request, context):
        try:
            user_id = request.user_id

            # temp fix until scripts fixed
            if not db.lte_decrement(user_id, "credit", request.amount):
                logging.error(
                    "Payment failed for user %s: insufficient credit",
                    request.user_id,
                )
                return payment_pb2.PaymentResponse(
                    success=False, error="Insufficient funds"
                )

            return payment_pb2.PaymentResponse(success=True)
        
            # with db.transaction() as client:
            #     client.lte_decrement(user_id, "credit", request.amount)

            #     if not test:
            #         logging.error(
            #             "Payment failed for user %s: insufficient credit",
            #             request.user_id,
            #         )
            #         return payment_pb2.PaymentResponse(
            #             success=False, error="Insufficient funds"
            #         )

            #     return payment_pb2.PaymentResponse(success=True)
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

    def UpdateTransactionStatus(self, request, context):
        pass


async def grpc_server():
    #interceptor = PromServerInterceptor()
    server = grpc.aio.server(
        futures.ThreadPoolExecutor(max_workers=10)
    )
    payment_pb2_grpc.add_PaymentServiceServicer_to_server(
        PaymentServiceServicer(), server
    )
    server.add_insecure_port("[::]:50052")
    await server.start()
    logging.info("gRPC Payment Service started on port 50052")
    await server.wait_for_termination()
