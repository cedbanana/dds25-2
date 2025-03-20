import json
from abc import ABC, abstractmethod
from contextlib import contextmanager
from typing import Any, Dict, Generic, List, Optional, Type, TypeVar, get_origin


from .stream import RedisStreamProducer

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
        elif get_origin(field_type) is dict:
            return json.dumps(value)
        return str(value)

    def _deserialize_value(self, value: str, field_type: Type) -> Any:
        """Deserialize a value based on its type"""
        if value is None:
            return None

        if get_origin(field_type) is list:
            return json.loads(value)
        elif get_origin(field_type) is dict:
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
    def get_all(self, ids: List[str], model_class: Type[T]) -> List[Optional[T]]:
        pass

    @abstractmethod
    def save_all(self, models: List[T]) -> None:
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
    def m_gte_decrement(self, changes: Dict[str, int], attribute: str) -> bool:
        pass

    @abstractmethod
    def close(self):
        """Close the database client connection"""
        pass

    def get_stream_producer(self, stream_key):
        return RedisStreamProducer(self.redis, stream_key)

    def initialize_stream_processor(self, processor_class):
        return processor_class(self.redis)
