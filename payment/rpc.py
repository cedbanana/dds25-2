import logging
from concurrent import futures
import grpc
import grpc.aio
from config import db
from models import User
from proto import payment_pb2, payment_pb2_grpc, common_pb2
import asyncio

import sys

root = logging.getLogger()
root.setLevel(logging.DEBUG)

handler = logging.StreamHandler(sys.stdout)
handler.setLevel(logging.DEBUG)
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
handler.setFormatter(formatter)
root.addHandler(handler)


class PaymentServiceServicer(payment_pb2_grpc.PaymentServiceServicer):
    async def AddFunds(self, request, context):
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

    async def ProcessPayment(self, request, context):
        try:
            user_id = request.user_id

            if not db.lte_decrement(user_id, "credit", request.amount, request.tid):
                logging.error(
                    "Payment failed for user %s: insufficient credit",
                    request.user_id,
                )
                return payment_pb2.PaymentResponse(
                    success=False, error="Insufficient funds"
                )

            return payment_pb2.PaymentResponse(success=True)
        except Exception as e:
            logging.exception("Error in ProcessPayment")
            context.abort(grpc.StatusCode.INTERNAL, str(e))

    async def FindUser(self, request, context):
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

    async def UpdateTransactionStatus(self, request, context):
        pass


async def serve():
    print("Starting gRPC Payment Service")
    server = grpc.aio.server()
    payment_pb2_grpc.add_PaymentServiceServicer_to_server(
        PaymentServiceServicer(), server
    )
    server.add_insecure_port("[::]:50052")
    await server.start()
    logging.info("gRPC Payment Service started on port 50052")
    await server.wait_for_termination()


if __name__ == "__main__":
    asyncio.run(serve())
    print("Payment Service exiting")
