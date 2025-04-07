import redis
import logging
import threading
import time
from typing import Callable


class RedisStreamProducer:
    def __init__(self, redis_client, stream_key):
        """
        Initialize the RedisStreamProducer.

        Args:
            redis_host (str): Redis host (default: 'localhost').
            redis_port (int): Redis port (default: 6379).
        """
        self.redis_client = redis_client
        self.stream_key = stream_key

    def push(self, id="*", **data):
        """
        Push a message to a Redis stream.

        Args:
            stream_key (str): The key of the Redis stream.
            data (dict): The data to push to the stream (will be serialized as JSON).
        """
        # Serialize the data as JSON
        # Push the message to the stream
        self.redis_client.xadd(self.stream_key, data, id=id)

    def size(self):
        """
        Get the number of entries in the Redis stream.

        Returns:
            int: The number of entries in the stream.
        """
        return self.redis_client.xlen(self.stream_key)


class RedisStreamConsumer:
    def __init__(
        self, redis_client, stream_key: str, consumer_group: str, consumer_name: str
    ):
        self.redis_client = redis_client
        self.stream_key = stream_key
        self.consumer_group = consumer_group
        self.consumer_name = consumer_name
        self._ensure_consumer_group_exists()

    def _ensure_consumer_group_exists(self):
        """Ensure the consumer group exists, create it if it doesn't."""
        try:
            self.redis_client.xgroup_create(
                self.stream_key, self.consumer_group, id="0", mkstream=True
            )
        except redis.exceptions.ResponseError as e:
            if "BUSYGROUP" not in str(e):
                raise

    def pre_xread(self):
        pass

    def consume(self, callback: Callable):
        """Continuously consume messages from the stream and pass them to the callback."""
        logging.error(
            "Starting consumer %s on stream key %s", self.consumer_name, self.stream_key
        )
        while True:
            self.pre_xread()
            try:
                # Read messages from the stream
                messages = self.redis_client.xreadgroup(
                    self.consumer_group,
                    self.consumer_name,
                    {self.stream_key: ">"},
                    count=1
                )

                if messages:
                    for stream, message_list in messages:
                        for message_id, data in message_list:
                            # Parse the message value as JSON
                            try:
                                # Pass the data as kwargs to the callback
                                callback(message_id, **data)
                                # Acknowledge the message
                                self.redis_client.xack(
                                    self.stream_key, self.consumer_group, message_id
                                )
                                self.redis_client.xdel(self.stream_key, message_id)
                            except Exception as e:
                                logging.exception("Error processing message")
            except Exception as e:
                logging.error(f"[REDIS:] {self.redis_client.ping()}")
                logging.exception("Error reading from strem")
                time.sleep(5)  # Wait before retrying


class StreamProcessor:
    stream_key = None

    def __init__(self, redis_client):
        ## TODO BS
        self.redis_client = redis_client
        assert self.stream_key is not None

    def callback(self, *args, **kwargs):
        raise NotImplementedError()

    def start_worker(self, consumer_group: str, consumer_name: str):
        """Start a worker to consume messages from a specific stream."""
        consumer = RedisStreamConsumer(
            self.redis_client, self.stream_key, consumer_group, consumer_name
        )
        consumer.consume(self.callback)

    def start_workers(self, consumer_group: str, num_workers: int = 1):
        """Start multiple workers for a specific stream."""
        for i in range(num_workers):
            consumer_name = f"consumer_{i+1}"
            print("Starting worker", consumer_name)
            thread = threading.Thread(
                target=self.start_worker,
                args=(consumer_group, consumer_name),
                daemon=True,
            )
            thread.start()
