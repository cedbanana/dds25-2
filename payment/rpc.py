import logging
from concurrent import futures
import grpc
import grpc.aio
from config import STREAM_KEY, db, NUM_STREAM_CONSUMER_REPLICAS
from models import User, Transaction, TransactionStatus, Counter, Flag
from proto import payment_pb2, payment_pb2_grpc, common_pb2
import asyncio
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


class PaymentServiceServicer(payment_pb2_grpc.PaymentServiceServicer):
    async def AddFunds(self, request, context):
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

    async def ProcessPayment(self, request, context):
        status = db.get_attr(request.tid, "status", Transaction)

        if status == TransactionStatus.STALE:
            logging.error("Payment failed: transaction is stale")
            return payment_pb2.PaymentResponse(
                success=False, error="Transaction is stale"
            )

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

    async def FindUser(self, request, context):
        user_model = db.get(request.user_id, User)
        if user_model is None:
            await context.abort(
                grpc.StatusCode.NOT_FOUND, f"User: {request.user_id} not found!"
            )
        return payment_pb2.FindUserResponse(user=user_model.to_proto())

    async def VibeCheckTransactionStatus(self, request, context):
        count_retries = 0
        transaction = None

        while transaction is None and count_retries < 10:
            logging.warning(
                f"Transaction: {request.tid} not found, retry!",
            )

            transaction = db.get(request.tid, Transaction)
            count_retries += 1
            await asyncio.sleep(0.5)

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
            logging.error("Payment failed: transaction is locked")
            await context.abort(
                grpc.StatusCode.FAILED_PRECONDITION,
                f"Transaction: {request.tid} is locked!",
            )

        db.delete(transaction)

        try:
            if not request.success and transaction.status == TransactionStatus.SUCCESS:
                logging.info(
                    "Transaction %s rolling back due to VibeCheck", request.tid
                )
                for k, v in transaction.details.items():
                    db.increment(k, "credit", v)
            elif transaction.status == TransactionStatus.SUCCESS:
                logging.info(
                    "Transaction %s committing thanks to VibeCheck", request.tid
                )
                for k, v in transaction.details.items():
                    db.decrement(k, "committed_credit", v)
        except Exception as e:
            logging.exception("Error in reverting payment")
            await context.abort(grpc.StatusCode.INTERNAL, str(e))
            return common_pb2.TransactionStatus(tid=request.tid, success=False)

        return transaction.to_proto()

    async def PrepareSnapshot(self, request, context):
        lock = db.redis.lock("snapshot_lock", timeout=5)

        if lock.acquire(blocking=False):
            response = common_pb2.OperationResponse(success=True)
            flag = db.get("HALTED", Flag)
            flag.enabled = True
            db.save(flag)

            return response
        else:
            response = common_pb2.OperationResponse(success=False)
            return response

    async def CheckSnapshotReady(self, request, context):
        count = db.get_attr("halted_consumers_counter", "count", Counter)
        # print(f"count: {count} ; needed: {NUM_STREAM_CONSUMER_REPLICAS}")
        sys.stdout.flush()
        if count >= NUM_STREAM_CONSUMER_REPLICAS:
            response = common_pb2.OperationResponse(success=True)
            return response
        else:
            response = common_pb2.OperationResponse(success=False)
            return response

    async def Snapshot(self, request, context):
        db.snapshot()

        response = common_pb2.OperationResponse(success=True)
        return response

    async def Rollback(self, request, context):
        # rollback logic

        response = common_pb2.OperationResponse(success=True)
        return response

    async def ContinueConsuming(self, request, context):
        lock = db.redis.lock("snapshot_lock", timeout=60)

        if lock:
            flag = db.get("HALTED", Flag)
            flag.enabled = False
            db.save(flag)

            counter = db.get("halted_consumers_counter", Counter)
            counter.count = 0
            db.save(counter)

            lock.release()
            response = common_pb2.OperationResponse(success=True)
            return response
        else:
            response = common_pb2.OperationResponse(success=False)
            return response


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
