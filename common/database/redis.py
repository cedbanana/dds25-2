from typing import List, TypeVar, Type, Optional, Dict, Any
from dataclasses import MISSING, asdict, fields
from contextlib import contextmanager
from redis.sentinel import Sentinel
import redis
import copy
from .database import (
    DatabaseClient,
    TransactionConfig,
    TransactionError,
)


T = TypeVar("T")

LTE_DECREMENT_SCRIPT = """
local current = tonumber(redis.call('get', KEYS[2]))
if current == nil then
    redis.call('set', KEYS[1], 1)
    return -1
end
if tonumber(ARGV[1]) <= current then
    redis.call('set', KEYS[1], 2)
    return redis.call('decrby', KEYS[2], ARGV[1])
end
redis.call('set', KEYS[1], 1)
return -1
"""

M_GTE_DECREMENT_SCRIPT = """
local all_valid = true

-- First check all values
for i, key in ipairs(KEYS) do
    if i > 1 then
        local current = tonumber(redis.call('get', key))
        if current == nil or tonumber(ARGV[i - 1]) > current then
            all_valid = false
            break
        end
    end
end

if all_valid then
    for i, key in ipairs(KEYS) do
        if i > 1 then
            redis.call('decrby', key, ARGV[i - 1])
        end
    end
    redis.call('set', KEYS[1], 2)
    return 1
else
    redis.call('set', KEYS[1], 1)
end

return -1
"""

COMPARE_AND_SET_SCRIPT = """
local current = redis.call('get', KEYS[1])
if current == ARGV[1] then
    redis.call('set', KEYS[1], ARGV[2])
    return 1
else
    return 0
end
"""


class RedisClient(DatabaseClient[T]):
    def __init__(
        self,
        sentinel_hosts: str = None,  # e.g., "sentinel1:26379,sentinel2:26379,sentinel3:26379"
        master_name: str = None,
        host: str = "localhost",
        port: int = 6379,
        password: str = "",
        db: int = 0,
        pipeline=None,
    ):
        if pipeline:
            self.pipeline = pipeline

        elif sentinel_hosts and master_name:
            # Initialize with Sentinel
            sentinel = Sentinel(
                [(h.split(":")[0], int(h.split(":")[1]))
                 for h in sentinel_hosts.split(",")],
                socket_timeout=1,
            )
            self.redis = sentinel.master_for(
                service_name=master_name,
                password=password,
                db=db,
                decode_responses=True,
                retry_on_timeout=True,  # Retry if the connection times out
            )
            self.pipeline: Optional[redis.client.Pipeline] = None
            self._register_scripts()

        else:
            self.redis = redis.Redis(
                host=host, port=port, password=password, db=db, decode_responses=True
            )
            self.pipeline: Optional[redis.client.Pipeline] = None

            # Register Lua scripts when initializing the client
            self._register_scripts()

    def _register_scripts(self):
        """Register all Lua scripts and store their SHA1 digests"""
        if hasattr(self, "redis"):
            self._gte_decrement = self.redis.register_script(
                LTE_DECREMENT_SCRIPT)
            self._m_gte_decrement = self.redis.register_script(
                M_GTE_DECREMENT_SCRIPT)
            self._compare_and_set_script = self.redis.register_script(
                COMPARE_AND_SET_SCRIPT
            )

    def _get_client(self):
        return self.pipeline if self.pipeline is not None else self.redis

    def _get_key(self, id: str, attribute: str) -> str:
        return f"model:{id}:{attribute}"

    def _get_model_keys_pattern(self, id: str) -> str:
        return f"model:{id}:*"

    def _prepare_for_changes(self) -> None:
        if self.pipeline is None:
            return
        elif not self.pipeline.explicit_transaction:
            self.pipeline.multi()

    def get(self, id: str, model_class: Type[T]) -> Optional[T]:
        client = self._get_client()

        keys = [
            self._get_key(id, field.name)
            for field in fields(model_class)
            if field.name != "id"
        ]
        if not keys:
            return None

        values = client.mget(keys)
        attributes = {key.split(":")[-1]: value for key,
                      value in zip(keys, values)}

        converted_data = {"id": id}
        annotations = model_class.__annotations__

        if any(v is None for v in values):
            return None

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

    def snapshot(self):
        response = self.save()
        return response

    def save(self, model: T) -> None:
        if not hasattr(model, "id"):
            raise ValueError("Model must have an id attribute")

        self._prepare_for_changes()

        client = self._get_client()
        model_dict = asdict(model)

        # Get model class to check types
        model_class = type(model)

        client = client if self.pipeline is None else self.pipeline

        kvs = {}

        for attr, value in model_dict.items():
            if attr != "id":
                field_type = model_class.__annotations__[attr]
                serialized_value = self._serialize_value(value, field_type)
                kvs[self._get_key(model.id, attr)] = serialized_value

        client.mset(kvs)

    def get_all(self, ids: List[str], model_class: Type[T]) -> List[Optional[T]]:
        client = self._get_client()

        result = []
        annotations = model_class.__annotations__

        for id in ids:
            keys = [self._get_key(id, field.name)
                    for field in fields(model_class)]
            values = client.mget(keys)

            if all(v is None for v in values):
                result.append(None)
                continue

            attributes = {
                key.split(":")[-1]: value for key, value in zip(keys, values)}
            converted_data = {"id": id}

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

            result.append(model_class(**converted_data))

        return result

    def save_all(self, models: List[T]) -> None:
        if not models:
            return

        self._prepare_for_changes()
        client = self._get_client()
        kvs = {}

        for model in models:
            if not hasattr(model, "id"):
                raise ValueError("Each model must have an id attribute")

            model_dict = asdict(model)
            model_class = type(model)

            for attr, value in model_dict.items():
                if attr != "id":
                    field_type = model_class.__annotations__[attr]
                    serialized_value = self._serialize_value(value, field_type)
                    kvs[self._get_key(model.id, attr)] = serialized_value

        client.mset(kvs)

    def keys(self, match: str = "*") -> List[str]:
        client = self._get_client()

        keys = client.keys(match)

        return keys

    def delete(self, obj: T) -> bool:
        client = self._get_client()

        id = obj.id

        keys = [self._get_key(id, field.name) for field in fields(type(obj))]

        client.delete(*keys)
        return True

    def get_attr(self, id: str, attribute: str, model_class: Type[T]) -> Any:
        client = self._get_client()
        key = self._get_key(id, attribute)
        value = client.get(key)

        if value is None:
            field = next((f for f in fields(model_class)
                         if f.name == attribute), None)
            if field is not None:
                if field.default is not MISSING:
                    return field.default
                elif field.default_factory is not MISSING:
                    return field.default_factory()
            return None

        field_type = model_class.__annotations__.get(attribute)
        return self._deserialize_value(value, field_type)

    def set_attr(
        self, id: str, attribute: str, value: Any, model_class: Type[T]
    ) -> None:
        self._prepare_for_changes()

        client = self._get_client()
        key = self._get_key(id, attribute)
        field_type = model_class.__annotations__.get(attribute)

        field_type = model_class.__annotations__.get(attribute)
        serialized_value = self._serialize_value(value, field_type)

        client.set(key, serialized_value)

    def m_get_attr(self, ids: List[str], attribute: str, model_class: Type[T]):
        client = self._get_client()
        keys = [self._get_key(id, attribute) for id in ids]

        values = client.mget(keys)

        result = {}

        for i, id in enumerate(ids):
            value = values[i]
            if value is None:
                field = next(
                    (f for f in fields(model_class) if f.name == attribute), None
                )
                if field is not None:
                    if field.default is not MISSING:
                        result[id] = field.default
                    elif field.default_factory is not MISSING:
                        result[id] = field.default_factory()
                return None

            field_type = model_class.__annotations__.get(attribute)
            result[id] = self._deserialize_value(value, field_type)

        return result

    def m_set_attr(self, values: Dict[str, Any], attribute: str, model_class: Type[T]):
        client = self._get_client()
        field_type = model_class.__annotations__.get(attribute)
        writes = {
            self._get_key(id, attribute): self._serialize_value(value, field_type)
            for id, value in values.items()
        }

        client.mset(writes)

    # Not sure if lua scripts work with EVALSHA in pipelines. For now fall back to EVAL
    def lte_decrement(self, id: str, attribute: str, amount: int, tid: str) -> bool:
        self._prepare_for_changes()
        client = self._get_client()
        key = self._get_key(id, attribute)
        tidk = self._get_key(tid, "status")

        try:
            if self.pipeline is None:
                result = self._gte_decrement(keys=[tidk, key], args=[amount])
            else:
                result = client.eval(
                    self.LTE_DECREMENT_SCRIPT, 2, tidk, key, amount)
        except redis.exceptions.NoScriptError:
            if self.pipeline is None:
                self._register_scripts()
                result = self._gte_decrement(keys=[tidk, key], args=[amount])
            else:
                result = client.eval(
                    self.LTE_DECREMENT_SCRIPT, 2, tidk, key, amount)

        return result != -1

    def m_gte_decrement(
        self, changes: Dict[str, int], attribute: str, tid: str
    ) -> bool:
        if not changes:
            return False

        self._prepare_for_changes()
        client = self._get_client()

        tidk = self._get_key(tid, "status")

        keys = []
        values = []

        for k, v in changes.items():
            keys.append(self._get_key(k, attribute))
            values.append(v)

        try:
            if self.pipeline is None:
                result = self._m_gte_decrement(keys=[tidk] + keys, args=values)
            else:
                # For pipelines, we need to use the original script
                result = client.eval(
                    self.M_GTE_DECREMENT_SCRIPT,
                    len(keys) + 1,
                    tidk,
                    *(keys + values),
                )
        except redis.exceptions.NoScriptError:
            # If script is not found (e.g., Redis was restarted), reload and try again
            if self.pipeline is None:
                self._register_scripts()
                result = self._m_gte_decrement(keys=[tidk] + keys, args=values)
            else:
                result = client.eval(
                    self.M_GTE_DECREMENT_SCRIPT, len(
                        keys) + 1, tidk, *(keys + values)
                )

        return result != -1

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
        client = self._get_client()

        # Convert expected_value and new_value to strings for comparison
        expected_str = str(expected_value)
        new_str = str(new_value)

        try:
            if self.pipeline is None:
                result = self._compare_and_set_script(
                    keys=[key], args=[expected_str, new_str]
                )
            else:
                result = client.eval(
                    COMPARE_AND_SET_SCRIPT, 1, key, expected_str, new_str
                )
        except redis.exceptions.NoScriptError:
            if self.pipeline is None:
                self._register_scripts()
                result = self._compare_and_set_script(
                    keys=[key], args=[expected_str, new_str]
                )
            else:
                result = client.eval(
                    COMPARE_AND_SET_SCRIPT, 1, key, expected_str, new_str
                )

        return result == 1

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

    def pipeline(self):
        pipeline = self._get_client().pipeline()
        client = copy.copy(self)
        client.pipeline = pipeline

        return client

    def execute_pipeline(self):
        if self.pipeline is None:
            raise ValueError("No pipeline to execute")

        return self.pipeline.execute()
