from abc import ABC, abstractmethod
from typing import TypeVar, Generic, Type, Optional, Dict, Any, cast, get_origin
from dataclasses import dataclass, asdict, fields
from contextlib import contextmanager
from enum import Enum
import redis
import json
from pyignite import Client as IgniteClient
from pyignite.datatypes import TransactionConcurrency, TransactionIsolation

T = TypeVar("T")


class TransactionConfig:
    def __init__(
        self,
        extra_begin_args: Optional[Dict[str, Any]] = None,
        extra_commit_args: Optional[Dict[str, Any]] = None,
        extra_rollback_args: Optional[Dict[str, Any]] = None,
    ):
        self.extra_begin_args = extra_begin_args or {}
        self.extra_commit_args = extra_commit_args or {}
        self.extra_rollback_args = extra_rollback_args or {}


class TransactionError(Exception):
    pass


class OptimisticLockError(Exception):
    pass


class DatabaseClient(ABC, Generic[T]):
    def __init__(self, transaction_config: Optional[TransactionConfig] = None):
        self.transaction_config = transaction_config or TransactionConfig()

    def _serialize_value(self, value: Any, field_type: Type) -> str:
        """Serialize a value based on its type"""
        if get_origin(field_type) is list:
            return json.dumps(value)
        return str(value)

    def _deserialize_value(self, value: str, field_type: Type) -> Any:
        """Deserialize a value based on its type"""
        if value is None:
            return None

        if get_origin(field_type) is list:
            return json.loads(value)
        elif field_type is int:
            return int(value)
        elif field_type is float:
            return float(value)
        elif field_type is bool:
            return value.lower() == "true"
        return value

    @abstractmethod
    def get(self, id: str, model_class: Type[T]) -> Optional[T]:
        pass

    @abstractmethod
    def save(self, model: T) -> None:
        pass

    @abstractmethod
    def delete(self, id: str) -> bool:
        pass

    @abstractmethod
    def increment(self, id: str, attribute: str, amount: int = 1) -> int:
        pass

    @abstractmethod
    def decrement(self, id: str, attribute: str, amount: int = 1) -> int:
        pass

    @abstractmethod
    def compare_and_set(
        self, id: str, attribute: str, expected_value: Any, new_value: Any
    ) -> bool:
        pass

    @abstractmethod
    def list_append(self, id: str, attribute: str, value: Any) -> int:
        """
        Append a value to a list attribute.
        Returns the new length of the list.
        """
        pass

    @abstractmethod
    def list_remove(self, id: str, attribute: str, value: Any) -> bool:
        """
        Remove a value from a list attribute.
        Returns True if the value was removed.
        """
        pass

    @abstractmethod
    def list_get(self, id: str, attribute: str, index: int) -> Any:
        """
        Get a value from a list attribute at the specified index.
        """
        pass

    @abstractmethod
    def list_set(self, id: str, attribute: str, index: int, value: Any) -> bool:
        """
        Set a value in a list attribute at the specified index.
        Returns True if successful.
        """
        pass

    @contextmanager
    def transaction(
        self,
        config: TransactionConfig = TransactionConfig(),
    ):
        """
        Context manager for atomic transactions with configurable isolation and concurrency.

        Args:
            isolation: Override default transaction isolation level
            concurrency: Override default transaction concurrency mode
        """
        try:
            self._begin_transaction(**config.extra_begin_args)
            yield
            self._commit_transaction(**config.extra_commit_args)
        except Exception as e:
            self._rollback_transaction(**config.extra_rollback_args)
            raise TransactionError(f"Transaction failed: {str(e)}")

    @abstractmethod
    def close(self):
        """Close the database client connection"""
        pass

    @abstractmethod
    def _begin_transaction(
        self,
        isolation: Optional[TransactionIsolation],
        concurrency: Optional[TransactionConcurrency],
    ) -> None:
        pass

    @abstractmethod
    def _commit_transaction(self) -> None:
        pass

    @abstractmethod
    def _rollback_transaction(self) -> None:
        pass


class RedisClient(DatabaseClient[T]):
    def __init__(
        self, host: str = "localhost", port: int = 6379, password: str = "", db: int = 0
    ):
        self.redis = redis.Redis(
            host=host, port=port, password=password, db=db, decode_responses=True
        )
        self.pipeline: Optional[redis.client.Pipeline] = None

    def _get_client(self):
        return self.pipeline if self.pipeline is not None else self.redis

    def _get_key(self, id: str, attribute: str) -> str:
        return f"model:{id}:{attribute}"

    def _get_model_keys_pattern(self, id: str) -> str:
        return f"model:{id}:*"

    def get(self, id: str, model_class: Type[T]) -> Optional[T]:
        client = self._get_client()

        keys = self.redis.keys(self._get_model_keys_pattern(id))
        if not keys:
            return None

        values = client.mget(keys)
        attributes = {key.split(":")[-1]: value for key, value in zip(keys, values)}

        converted_data = {"id": id}
        annotations = model_class.__annotations__

        for field in fields(model_class):
            field_name = field.name
            if field_name == "id":
                continue

            value = attributes.get(field_name)
            if value is None:
                if field.default is not dataclass.MISSING:
                    converted_data[field_name] = field.default
                elif field.default_factory is not dataclass.MISSING:
                    converted_data[field_name] = field.default_factory()
                continue

            converted_data[field_name] = self._deserialize_value(
                value, annotations[field_name]
            )

        return model_class(**converted_data)

    def save(self, model: T) -> None:
        if not hasattr(model, "id"):
            raise ValueError("Model must have an id attribute")

        client = self._get_client()
        model_dict = asdict(model)

        # Get model class to check types
        model_class = type(model)

        pipe = client.pipeline() if self.pipeline is None else client

        for attr, value in model_dict.items():
            if attr != "id":
                field_type = model_class.__annotations__[attr]
                serialized_value = self._serialize_value(value, field_type)
                pipe.set(self._get_key(model.id, attr), serialized_value)

        if self.pipeline is None:
            pipe.execute()

    def list_append(self, id: str, attribute: str, value: Any) -> int:
        key = self._get_key(id, attribute)
        with self.redis.pipeline() as pipe:
            while True:
                try:
                    pipe.watch(key)
                    current_list = json.loads(pipe.get(key) or "[]")
                    current_list.append(value)

                    pipe.multi()
                    pipe.set(key, json.dumps(current_list))
                    pipe.execute()
                    return len(current_list)
                except redis.WatchError:
                    continue

    def list_remove(self, id: str, attribute: str, value: Any) -> bool:
        key = self._get_key(id, attribute)
        with self.redis.pipeline() as pipe:
            while True:
                try:
                    pipe.watch(key)
                    current_list = json.loads(pipe.get(key) or "[]")
                    if value not in current_list:
                        pipe.unwatch()
                        return False

                    current_list.remove(value)
                    pipe.multi()
                    pipe.set(key, json.dumps(current_list))
                    pipe.execute()
                    return True
                except redis.WatchError:
                    continue

    def list_get(self, id: str, attribute: str, index: int) -> Any:
        key = self._get_key(id, attribute)
        current_list = json.loads(self.redis.get(key) or "[]")
        if 0 <= index < len(current_list):
            return current_list[index]
        raise IndexError("List index out of range")

    def list_set(self, id: str, attribute: str, index: int, value: Any) -> bool:
        key = self._get_key(id, attribute)
        with self.redis.pipeline() as pipe:
            while True:
                try:
                    pipe.watch(key)
                    current_list = json.loads(pipe.get(key) or "[]")
                    if not (0 <= index < len(current_list)):
                        pipe.unwatch()
                        return False

                    current_list[index] = value
                    pipe.multi()
                    pipe.set(key, json.dumps(current_list))
                    pipe.execute()
                    return True
                except redis.WatchError:
                    continue

    def delete(self, id: str) -> bool:
        client = self._get_client()
        # Get all keys for this model
        keys = self.redis.keys(self._get_model_keys_pattern(id))
        if not keys:
            return False

        # Delete all keys in a single operation
        client.delete(*keys)
        return True

    def increment(self, id: str, attribute: str, amount: int = 1) -> int:
        client = self._get_client()
        try:
            result = client.incrby(self._get_key(id, attribute), amount)
            return int(result)
        except redis.ResponseError:
            raise ValueError(f"Attribute {attribute} is not numeric")

    def decrement(self, id: str, attribute: str, amount: int = 1) -> int:
        return self.increment(id, attribute, -amount)

    def compare_and_set(
        self, id: str, attribute: str, expected_value: Any, new_value: Any
    ) -> bool:
        key = self._get_key(id, attribute)
        with self.redis.pipeline() as pipe:
            while True:
                try:
                    # Watch the key for changes
                    pipe.watch(key)

                    # Get current value
                    current_value = pipe.get(key)

                    # Convert values to strings for comparison
                    expected_str = str(expected_value)

                    if current_value != expected_str:
                        pipe.unwatch()
                        return False

                    # Start transaction
                    pipe.multi()

                    # Set new value
                    pipe.set(key, str(new_value))

                    # Execute transaction
                    pipe.execute()
                    return True

                except redis.WatchError:
                    # Another client modified the key while we were working
                    continue

    def close(self):
        """Close the Redis client connection"""
        self.redis.close()

    def _begin_transaction(self) -> None:
        self.pipeline = self.redis.pipeline()

    def _commit_transaction(self) -> None:
        if self.pipeline:
            self.pipeline.execute()
            self.pipeline = None

    def _rollback_transaction(self) -> None:
        if self.pipeline:
            self.pipeline.reset()
            self.pipeline = None


# [Previous Redis implementation remains the same, but updated to handle transaction config]


class IgniteClient(DatabaseClient[T]):
    def __init__(
        self,
        hosts: list[tuple[str, int]] = [("127.0.0.1", 10800)],
        transaction_config: Optional[TransactionConfig] = None,
    ):
        super().__init__(transaction_config)
        self.client = IgniteClient()
        self.client.connect(hosts)
        # Create cache for storing model attributes
        self.cache = self.client.get_or_create_cache(
            {
                "name": "model_cache",
                "atomicity_mode": "TRANSACTIONAL",
                "cache_mode": "PARTITIONED",
                "backups": 1,
            }
        )
        self.transaction = None

    def _get_key(self, id: str, attribute: str) -> str:
        return f"model:{id}:{attribute}"

    def get(self, id: str, model_class: Type[T]) -> Optional[T]:
        # Get all fields from model class
        field_names = [f.name for f in fields(model_class) if f.name != "id"]

        # Get all attributes in one batch operation
        keys = [self._get_key(id, field) for field in field_names]
        values = self.cache.get_all(keys)

        if not values:
            return None

        # Convert values based on model annotations
        converted_data = {"id": id}
        annotations = model_class.__annotations__

        for field_name in field_names:
            key = self._get_key(id, field_name)
            value = self._deserialize_(values.get(key))

            if value is None:
                field = next(f for f in fields(model_class) if f.name == field_name)
                if field.default is not dataclass.MISSING:
                    converted_data[field_name] = field.default
                elif field.default_factory is not dataclass.MISSING:
                    converted_data[field_name] = field.default_factory()
                continue

            # Type conversion
            if annotations[field_name] is int:
                converted_data[field_name] = int(value)
            elif annotations[field_name] is float:
                converted_data[field_name] = float(value)
            elif annotations[field_name] is bool:
                converted_data[field_name] = value.lower() == "true"
            else:
                converted_data[field_name] = value

        return model_class(**converted_data)

    def save(self, model: T) -> None:
        if not hasattr(model, "id"):
            raise ValueError("Model must have an id attribute")

        model_dict = asdict(model)
        updates = {
            self._get_key(model.id, attr): self._serialize_value(value)
            for attr, value in model_dict.items()
            if attr != "id"
        }

        self.cache.put_all(updates)

    def list_append(self, id: str, attribute: str, value: Any) -> int:
        key = self._get_key(id, attribute)
        while True:
            try:
                with self.transaction(
                    isolation=TransactionIsolation.SERIALIZABLE,
                    concurrency=TransactionConcurrency.PESSIMISTIC,
                ):
                    current_list = json.loads(self.cache.get(key) or "[]")
                    current_list.append(value)
                    self.cache.put(key, json.dumps(current_list))
                    return len(current_list)
            except OptimisticLockError:
                continue

    def list_remove(self, id: str, attribute: str, value: Any) -> bool:
        key = self._get_key(id, attribute)
        with self.transaction(
            isolation=TransactionIsolation.SERIALIZABLE,
            concurrency=TransactionConcurrency.PESSIMISTIC,
        ):
            current_list = json.loads(self.cache.get(key) or "[]")
            if value not in current_list:
                return False
            current_list.remove(value)
            self.cache.put(key, json.dumps(current_list))
            return True

    def list_get(self, id: str, attribute: str, index: int) -> Any:
        key = self._get_key(id, attribute)
        current_list = json.loads(self.cache.get(key) or "[]")
        if 0 <= index < len(current_list):
            return current_list[index]
        raise IndexError("List index out of range")

    def list_set(self, id: str, attribute: str, index: int, value: Any) -> bool:
        key = self._get_key(id, attribute)
        with self.transaction(
            isolation=TransactionIsolation.SERIALIZABLE,
            concurrency=TransactionConcurrency.PESSIMISTIC,
        ):
            current_list = json.loads(self.cache.get(key) or "[]")
            if not (0 <= index < len(current_list)):
                return False
            current_list[index] = value
            self.cache.put(key, json.dumps(current_list))
            return True

    def delete(self, id: str) -> bool:
        # Get all keys for this model
        keys = [key for key in self.cache.keys() if key.startswith(f"model:{id}:")]

        if not keys:
            return False

        self.cache.remove_all(keys)
        return True

    def increment(self, id: str, attribute: str, amount: int = 1) -> int:
        key = self._get_key(id, attribute)

        while True:
            try:
                with self.transaction(
                    isolation=TransactionIsolation.SERIALIZABLE,
                    concurrency=TransactionConcurrency.PESSIMISTIC,
                ):
                    current = self.cache.get(key)
                    if current is None:
                        raise ValueError(f"Attribute {attribute} not found")

                    new_value = int(current) + amount
                    self.cache.put(key, str(new_value))
                    return new_value
            except OptimisticLockError:
                continue

    def decrement(self, id: str, attribute: str, amount: int = 1) -> int:
        return self.increment(id, attribute, -amount)

    def compare_and_set(
        self, id: str, attribute: str, expected_value: Any, new_value: Any
    ) -> bool:
        key = self._get_key(id, attribute)

        with self.transaction(
            isolation=TransactionIsolation.SERIALIZABLE,
            concurrency=TransactionConcurrency.OPTIMISTIC,
        ):
            current = self.cache.get(key)
            if str(current) != str(expected_value):
                return False

            self.cache.put(key, str(new_value))
            return True

    def close(self):
        """Close the Ignite client connection"""
        self.client.close()

    def _begin_transaction(
        self,
        isolation: Optional[TransactionIsolation] = None,
        concurrency: Optional[TransactionConcurrency] = None,
    ) -> None:
        if self.transaction is not None:
            raise TransactionError("Transaction already in progress")

        isolation = isolation or self.transaction_config.isolation
        concurrency = concurrency or self.transaction_config.concurrency

        self.transaction = self.client.transactions().start(
            concurrency=concurrency, isolation=isolation
        )

    def _commit_transaction(self) -> None:
        if self.transaction:
            self.transaction.commit()
            self.transaction = None

    def _rollback_transaction(self) -> None:
        if self.transaction:
            self.transaction.rollback()
            self.transaction = None

    def close(self):
        """Close the Ignite client connection"""
        self.client.close()
