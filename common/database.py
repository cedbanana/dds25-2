from abc import ABC, abstractmethod
import logging
from typing import TypeVar, Generic, Type, Optional, Dict, Any, cast, get_origin
from dataclasses import MISSING, asdict, fields
from contextlib import contextmanager
import random
import redis
import json
import copy
from pyignite import Client
from pyignite.datatypes.cache_config import CacheAtomicityMode
from pyignite.datatypes import TransactionConcurrency, TransactionIsolation
from pyignite.datatypes.prop_codes import PROP_CACHE_ATOMICITY_MODE, PROP_NAME
import pyignite.datatypes.primitive_objects as itypes_primitive
import pyignite.datatypes.standard as itypes_standard

T = TypeVar("T")


class TransactionConfig:
    def __init__(
        self,
        init: Optional[Dict[str, Any]] = None,
        begin: Optional[Dict[str, Any]] = None,
        commit: Optional[Dict[str, Any]] = None,
        rollback: Optional[Dict[str, Any]] = None,
        end: Optional[Dict[str, Any]] = None,
    ):
        self.init = init or {}
        self.begin = begin or {}
        self.commit = commit or {}
        self.rollback = rollback or {}
        self.end = rollback or {}


class TransactionError(Exception):
    pass


class OptimisticLockError(Exception):
    pass


class DatabaseClient(ABC, Generic[T]):
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
    def get_attribute(self, id: str, attribute: str, model_class: Type[T]) -> Any:
        pass

    @abstractmethod
    def set_attribute(
        self, id: str, attribute: str, value: Any, model_class: Type[T]
    ) -> None:
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

    @contextmanager
    @abstractmethod
    def transaction(
        self,
        config: TransactionConfig = TransactionConfig(),
    ):
        pass

    @abstractmethod
    def close(self):
        """Close the database client connection"""
        pass


class RedisClient(DatabaseClient[T]):
    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        password: str = "",
        db: int = 0,
        pipeline=None,
    ):
        if pipeline:
            self.pipeline = pipeline
        else:
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

    def _prepare_for_changes(self) -> None:
        if self.pipeline is None:
            return
        else:
            self.pipeline.multi()

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
                if field.default is not MISSING:
                    converted_data[field_name] = field.default
                elif field.default_factory is not MISSING:
                    converted_data[field_name] = field.default_factory()
                continue

            converted_data[field_name] = self._deserialize_value(
                value, annotations[field_name]
            )

        return model_class(**converted_data)

    def save(self, model: T) -> None:
        if not hasattr(model, "id"):
            raise ValueError("Model must have an id attribute")

        self._prepare_for_changes()

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

    def delete(self, id: str) -> bool:
        client = self._get_client()
        # Get all keys for this model
        keys = self.redis.keys(self._get_model_keys_pattern(id))
        if not keys:
            return False

        # Delete all keys in a single operation
        client.delete(*keys)
        return True

    def get_attribute(self, id: str, attribute: str, model_class: Type[T]) -> Any:
        client = self._get_client()
        key = self._get_key(id, attribute)
        value = client.get(key)

        if value is None:
            field = next((f for f in fields(model_class) if f.name == attribute), None)
            if field is not None:
                if field.default is not MISSING:
                    return field.default
                elif field.default_factory is not MISSING:
                    return field.default_factory()
            return None

        field_type = model_class.__annotations__.get(attribute)
        return self._deserialize_value(value, field_type)

    def set_attribute(
        self, id: str, attribute: str, value: Any, model_class: Type[T]
    ) -> None:
        self._prepare_for_changes()

        client = self._get_client()
        key = self._get_key(id, attribute)
        field_type = model_class.__annotations__.get(attribute)

        field_type = model_class.__annotations__.get(attribute)
        serialized_value = self._serialize_value(value, field_type)

        client.set(key, serialized_value)

    def increment(self, id: str, attribute: str, amount: int = 1) -> int:
        self._prepare_for_changes()
        client = self._get_client()
        try:
            result = client.incrby(self._get_key(id, attribute), amount)
            if self.pipeline is None:
                return int(result)

            return result

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

    @contextmanager
    def transaction(self, config: TransactionConfig = TransactionConfig()):
        pipeline = self._get_client().pipeline()
        try:
            for id, attr in config.begin.get("watch", []):
                pipeline.watch(self._get_key(id, attr))

            client = copy.copy(self)
            client.pipeline = pipeline

            yield client
            pipeline.execute()
            pipeline.unwatch()

        except Exception as e:
            pipeline.unwatch()
            pipeline.reset()
            raise TransactionError(e)


class IgniteClient(DatabaseClient[T]):
    def __init__(
        self,
        hosts: list[tuple[str, int]] = [("127.0.0.1", 10800)],
        model_class: Type[T] = None,
        additional_conf: dict = {},
    ):
        self.config = {
            "hosts": hosts,
            "model_class": model_class,
            "additional_conf": additional_conf,
        }
        self.client = Client()
        self.client.connect(hosts)
        self.tx = None

        cache_conf = {
            PROP_NAME: model_class.__name__
            if model_class
            else "model_cache_" + str(random.randint(1, 10000)),
            PROP_CACHE_ATOMICITY_MODE: CacheAtomicityMode.TRANSACTIONAL,
        }

        cache_conf.update(additional_conf)

        # Create cache for storing model attributes
        self.cache = self.client.get_or_create_cache(cache_conf)

    def _value_hint(self, model_class: Type[T], field: str) -> str:
        field_type = model_class.__annotations__.get(field)

        if field_type is int:
            return itypes_primitive.IntObject
        elif field_type is float:
            return itypes_primitive.FloatObject
        elif field_type is bool:
            return itypes_primitive.BoolObject
        elif get_origin(field_type) is list:
            return itypes_standard.StringArrayObject
        elif field_type is None:
            return None
        return itypes_standard.String

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

        for field_name in field_names:
            key = self._get_key(id, field_name)
            value = values.get(key)

            if value is None:
                field = next(f for f in fields(model_class) if f.name == field_name)
                if field.default is not MISSING:
                    converted_data[field_name] = field.default
                elif field.default_factory is not MISSING:
                    converted_data[field_name] = field.default_factory()
                continue

            converted_data[field_name] = value

        return model_class(**converted_data)

    def save(self, model: T) -> None:
        if not hasattr(model, "id"):
            raise ValueError("Model must have an id attribute")

        model_dict = asdict(model)
        model_class = type(model)

        updates = {
            self._get_key(model.id, attr): (value, self._value_hint(model_class, attr))
            for attr, value in model_dict.items()
            if attr != "id" and (not isinstance(value, list) or len(value) > 0)
        }

        self.cache.put_all(updates)

    def delete(self, id: str) -> bool:
        # Get all keys for this model
        keys = [key for key in self.cache.keys() if key.startswith(f"model:{id}:")]

        if not keys:
            return False

        self.cache.remove_all(keys)
        return True

    def get_attribute(self, id: str, attribute: str, model_class: Type[T]) -> Any:
        key = self._get_key(id, attribute)
        value = self.cache.get(key, key_hint=itypes_standard.String)

        if value is None:
            field = next((f for f in fields(model_class) if f.name == attribute), None)
            if field is not None:
                if field.default is not MISSING:
                    return field.default
                elif field.default_factory is not MISSING:
                    return field.default_factory()
            return None

        return value

    def set_attribute(
        self, id: str, attribute: str, value: Any, model_class: Type[T]
    ) -> None:
        key = self._get_key(id, attribute)

        if isinstance(value, list) and len(value) == 0:
            self.cache.remove(key)
        else:
            self.cache.put(
                key, value, value_hint=self._value_hint(model_class, attribute)
            )

    def _simple_increment(self, id: str, attribute: str, amount: int) -> int:
        key = self._get_key(id, attribute)
        current = self.cache.get(key)

        if current is None:
            raise ValueError(f"Attribute {attribute} not found")

        new_value = int(current) + amount
        self.cache.put(key, new_value, value_hint=itypes_primitive.IntObject)
        return new_value

    def increment(self, id: str, attribute: str, amount: int = 1) -> int:
        if self.tx is not None:
            val = self._simple_increment(id, attribute, amount)
            return val

        while True:
            try:
                with self.transaction(
                    TransactionConfig(
                        init={
                            "isolation": TransactionIsolation.SERIALIZABLE,
                            "concurrency": TransactionConcurrency.PESSIMISTIC,
                        }
                    )
                ):
                    return self._simple_increment(id, attribute, amount)
            except OptimisticLockError:
                continue

    def decrement(self, id: str, attribute: str, amount: int = 1) -> int:
        return self.increment(id, attribute, -amount)

    def compare_and_set(
        self, id: str, attribute: str, expected_value: Any, new_value: Any
    ) -> bool:
        key = self._get_key(id, attribute)

        with self.transaction(
            TransactionConfig(
                init={
                    "isolation": TransactionIsolation.SERIALIZABLE,
                    "concurrency": TransactionConcurrency.PESSIMISTIC,
                }
            )
        ):
            current = self.cache.get(key)
            if str(current) != str(expected_value):
                return False

            self.cache.put(key, str(new_value))
            return True

    @contextmanager
    def transaction(
        self,
        config: TransactionConfig = TransactionConfig(),
    ):
        txclient = IgniteClient(**self.config)

        try:
            with txclient.client.tx_start(
                isolation=config.init.get(
                    "isolation", TransactionIsolation.SERIALIZABLE
                ),
                concurrency=config.init.get(
                    "concurrency", TransactionConcurrency.PESSIMISTIC
                ),
            ) as tx:
                txclient.tx = tx
                yield txclient
                tx.commit()
        except Exception as e:
            raise TransactionError(e)
        finally:
            txclient.close()

    def close(self):
        """Close the Ignite client connection"""
        self.client.close()

    def _create_transactional_client(self) -> "DatabaseClient[T]":
        pass
