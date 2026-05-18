"""AI Calling Agent — Redis Client"""
import structlog
import redis.asyncio as aioredis
from app.core.config import settings

log = structlog.get_logger()

redis_client: aioredis.Redis | None = None


async def get_redis() -> aioredis.Redis:
    global redis_client
    if redis_client is None:
        redis_client = aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
            max_connections=50,
        )
        await redis_client.ping()
        log.info("redis.connected")
    return redis_client


async def close_redis():
    global redis_client
    if redis_client:
        await redis_client.close()
        redis_client = None
