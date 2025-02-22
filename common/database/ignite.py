from abc import ABC, abstractmethod
import logging
from typing import List, TypeVar, Generic, Type, Optional, Dict, Any, cast, get_origin
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
from .database import (
    DatabaseClient,
    TransactionConfig,
    TransactionError,
    OptimisticLockError,
)


T = TypeVar("T")


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

    def get_attr(self, id: str, attribute: str, model_class: Type[T]) -> Any:
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

    def set_attr(
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

            with self.transaction(
                TransactionConfig(
                    init={
                        "isolation": TransactionIsolation.SERIALIZABLE,
                        "concurrency": TransactionConcurrency.PESSIMISTIC,
                    }
                )
            ):
                return self._simple_increment(id, attribute, amount)

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

    def m_get_attr(
        self, ids: List[str], attribute: str, model_class: Type[T]
    ) -> Dict[str, Any]:
        if not ids:
            return {}

        # Create keys for all IDs
        keys = [self._get_key(id, attribute) for id in ids]

        # Get all values in one batch operation
        values = self.cache.get_all(keys)

        result = {}

        # Process each ID
        for id in ids:
            key = self._get_key(id, attribute)
            value = values.get(key)

            if value is None:
                # Handle default values
                field = next(
                    (f for f in fields(model_class) if f.name == attribute), None
                )
                if field is not None:
                    if field.default is not MISSING:
                        result[id] = field.default
                    elif field.default_factory is not MISSING:
                        result[id] = field.default_factory()
                    else:
                        result[id] = None
                else:
                    result[id] = None
            else:
                result[id] = value

        return result

    def m_set_attr(
        self, values: Dict[str, Any], attribute: str, model_class: Type[T]
    ) -> None:
        if not values:
            return

        updates = {}
        to_remove = []
        value_hint = self._value_hint(model_class, attribute)

        # Prepare updates and removals
        for id, value in values.items():
            key = self._get_key(id, attribute)
            if isinstance(value, list) and len(value) == 0:
                to_remove.append(key)
            else:
                updates[key] = (value, value_hint)

        # Apply updates in batch
        if updates:
            self.cache.put_all(updates)

        # Remove empty lists in batch
        if to_remove:
            self.cache.remove_all(to_remove)

    def _lte_decrement_transaction(self, id: str, attribute: str, amount: int) -> bool:
        key = self._get_key(id, attribute)
        current = self.cache.get(key)

        if current is None:
            return False

        try:
            current_int = int(current)
        except (ValueError, TypeError):
            return False

        if current_int >= amount:
            new_value = current_int - amount
            self.cache.put(key, new_value, value_hint=itypes_primitive.IntObject)
            return True

        return False

    def lte_decrement(self, id: str, attribute: str, amount: int) -> bool:
        if self.tx is not None:
            return self._lte_decrement_transaction(id, attribute, amount)

        with self.transaction(
            TransactionConfig(
                init={
                    "isolation": TransactionIsolation.SERIALIZABLE,
                    "concurrency": TransactionConcurrency.PESSIMISTIC,
                }
            )
        ) as tx_client:
            return tx_client._lte_decrement_transaction(id, attribute, amount)

    def _m_lte_decrement_transaction(
        self, changes: Dict[str, int], attribute: str
    ) -> bool:
        keys = {id: self._get_key(id, attribute) for id in changes}
        values = self.cache.get_all(keys)

        if len(values) != len(keys):
            return False

        for i, amount in changes.items():
            value = values.get(keys[i])
            try:
                if int(value) < amount:
                    return False
            except (ValueError, TypeError):
                return False

        updates = {}
        for i, amount in changes.items():
            key = keys[i]
            value = values.get(keys[i])

            amount = changes.get(key)
            new_value = int(value) - amount
            updates[key] = (new_value, itypes_primitive.IntObject)

        self.cache.put_all(updates)
        return True

    def m_lte_decrement(self, changes: Dict[str, int], attribute: str) -> bool:
        if not changes:
            return False

        # If already in a transaction, just perform the operation
        if self.tx is not None:
            return self._m_lte_decrement_transaction(changes, attribute)

        # Otherwise, create a new transaction for this operation
        with self.transaction(
            TransactionConfig(
                init={
                    "isolation": TransactionIsolation.SERIALIZABLE,
                    "concurrency": TransactionConcurrency.PESSIMISTIC,
                }
            )
        ) as tx_client:
            return tx_client._m_lte_decrement_transaction(changes, attribute)

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
