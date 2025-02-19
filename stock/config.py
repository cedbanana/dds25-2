import os
from .db.client import RedisDatabaseClient

# Initialize the database client
db = RedisDatabaseClient(
    host=os.environ["REDIS_HOST"],
    port=int(os.environ["REDIS_PORT"]),
    password=os.environ["REDIS_PASSWORD"],
    db=int(os.environ["REDIS_DB"]),
)
