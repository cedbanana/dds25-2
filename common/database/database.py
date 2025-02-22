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
    def get_attr(self, id: str, attribute: str, model_class: Type[T]) -> Any:
        pass

    @abstractmethod
    def set_attr(
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
    def m_get_attr(self, ids: List[str], attribute: str, model_class: Type[T]):
        pass

    @abstractmethod
    def m_set_attr(self, values: Dict[str, Any], attribute: str, model_class: Type[T]):
        pass

    @abstractmethod
    def lte_decrement(self, id: str, attribute: str, amount: int) -> bool:
        pass

    @abstractmethod
    def m_lte_decrement(self, changes: Dict[str, int], attribute: str) -> bool:
        pass

    @abstractmethod
    def close(self):
        """Close the database client connection"""
        pass
