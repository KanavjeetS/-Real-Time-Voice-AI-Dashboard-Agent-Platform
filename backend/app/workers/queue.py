"""Redis-backed job queue (RQ/Celery-compatible pattern, lightweight)."""
import json
import uuid
from enum import Enum
from typing import Any

import structlog

from app.core.config import settings

log = structlog.get_logger()

QUEUE_KEY = "vahanai:jobs"


class JobType(str, Enum):
    POST_CALL_SUMMARY = "post_call_summary"
    LEAD_SCORE_SYNC = "lead_score_sync"
    SLACK_ALERT = "slack_alert"
    CRM_SYNC = "crm_sync"


async def enqueue(job_type: JobType, payload: dict[str, Any]) -> str:
    """Push a job to Redis. Returns job_id."""
    job_id = uuid.uuid4().hex
    job = {
        "id": job_id,
        "type": job_type.value,
        "payload": payload,
    }
    try:
        from app.db.redis_client import get_redis
        redis = await get_redis()
        await redis.lpush(QUEUE_KEY, json.dumps(job))
        log.info("queue.enqueued", job_id=job_id, type=job_type.value)
    except Exception as e:
        log.warning("queue.enqueue_failed", error=str(e), job_type=job_type.value)
    return job_id


async def dequeue(timeout: int = 5) -> dict | None:
    """Blocking pop for worker process."""
    from app.db.redis_client import get_redis
    redis = await get_redis()
    result = await redis.brpop(QUEUE_KEY, timeout=timeout)
    if not result:
        return None
    _, raw = result
    return json.loads(raw)
