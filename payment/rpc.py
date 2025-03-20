import logging
from concurrent import futures
import grpc
import grpc.aio
from config import STREAM_KEY, db
from models import User, Transaction, TransactionStatus
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

stream_producer = db.get_stream_producer(STREAM_KEY)


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

            transaction = Transaction(
                request.tid,
                TransactionStatus.PENDING,
                {request.user_id: request.amount},
            )
            db.save(transaction)
            stream_producer.push(tid=request.tid)

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

    async def VibeCheckTransactionStatus(self, request, context):
        try:
            count_retries = 0
            transaction = None
            while transaction is None and count_retries < 10:
                context.abort(
                    grpc.StatusCode.NOT_FOUND, f"Transaction: {request.tid} not found, retry!"
                )

                transaction = db.get(request.tid, Transaction)
                count_retries += 1
                await asyncio.sleep(0.1)

                stale_transaction = Transaction(
                    request.tid,
                    TransactionStatus.STALE,
                )

                if transaction is None:
                    db.save(stale_transaction)
                    return stale_transaction.to_proto()

            # Revert here
            if request.success == False and transaction.status == TransactionStatus.SUCCESS:
                try:
                    for k, v in transaction.details.items():
                        db.increment(k, "credit", v)
                except Exception as e:
                    logging.exception("Error in reverting payment")
                    context.abort(grpc.StatusCode.INTERNAL, str(e))
                    return common_pb2.TransactionStatus(
                        tid=request.tid, success=False
                    )

            # Successful
            return transaction.to_proto()
        except Exception as e:
            logging.exception("Error in trying to check transaction status.")
            context.abort(grpc.StatusCode.INTERNAL, str(e))


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
