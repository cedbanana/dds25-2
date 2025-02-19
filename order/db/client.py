from abc import ABC, abstractmethod
import redis


class DatabaseError(Exception):
    pass


class DatabaseClient(ABC):
    @abstractmethod
    def get(self, key: str) -> bytes | None: ...

    @abstractmethod
    def set(self, key: str, value: bytes) -> None: ...

    @abstractmethod
    def mset(self, kv_pairs: dict[str, bytes]) -> None: ...

    @abstractmethod
    def close(self) -> None: ...


class RedisDatabaseClient(DatabaseClient):
    def __init__(self, host: str, port: int, password: str, db: int):
        self.connection = redis.Redis(
            host=host, port=port, password=password, db=db, decode_responses=False
        )

    def get(self, key: str) -> bytes | None:
        try:
            return self.connection.get(key)
        except redis.RedisError as e:
            raise DatabaseError(f"Redis error: {e}") from e

    def set(self, key: str, value: bytes) -> None:
        try:
            self.connection.set(key, value)
        except redis.RedisError as e:
            raise DatabaseError(f"Redis error: {e}") from e

    def mset(self, kv_pairs: dict[str, bytes]) -> None:
        try:
            self.connection.mset(kv_pairs)
        except redis.RedisError as e:
            raise DatabaseError(f"Redis error: {e}") from e

    def close(self) -> None:
        self.connection.close()
