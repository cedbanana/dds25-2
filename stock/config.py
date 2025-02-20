import os
from dotenv import load_dotenv
from database import RedisClient

load_dotenv()

db = RedisClient(
    host=os.environ["REDIS_HOST"],
    port=int(os.environ["REDIS_PORT"]),
    password=os.environ["REDIS_PASSWORD"],
    db=int(os.environ["REDIS_DB"]),
)
