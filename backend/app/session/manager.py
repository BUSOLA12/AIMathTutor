import asyncio
import json
import logging
from typing import Optional

import redis.asyncio as aioredis
from redis.exceptions import ConnectionError as RedisConnectionError, TimeoutError as RedisTimeoutError

from app.core.config import settings
from app.models.schemas import SessionState

logger = logging.getLogger(__name__)

_redis: Optional[aioredis.Redis] = None
SESSION_TTL = 60 * 60 * 4  # 4 hours
_RETRY_ATTEMPTS = 3
_RETRY_BACKOFF = 0.5  # seconds


async def get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    return _redis


async def _redis_op(op):
    """Run a Redis operation with retry on transient connection errors."""
    global _redis
    last_exc = None
    for attempt in range(_RETRY_ATTEMPTS):
        try:
            r = await get_redis()
            return await op(r)
        except (RedisConnectionError, RedisTimeoutError, OSError) as exc:
            last_exc = exc
            logger.warning("Redis connection error (attempt %d/%d): %s", attempt + 1, _RETRY_ATTEMPTS, exc)
            _redis = None  # force reconnect on next attempt
            if attempt < _RETRY_ATTEMPTS - 1:
                await asyncio.sleep(_RETRY_BACKOFF * (attempt + 1))
    raise last_exc


async def save_session_state(state: SessionState) -> None:
    await _redis_op(lambda r: r.setex(f"session:{state.session_id}", SESSION_TTL, state.model_dump_json()))


async def get_session_state(session_id: str) -> Optional[SessionState]:
    raw = await _redis_op(lambda r: r.get(f"session:{session_id}"))
    if raw is None:
        return None
    return SessionState(**json.loads(raw))


async def update_session_phase(session_id: str, phase: str) -> None:
    state = await get_session_state(session_id)
    if state:
        state.phase = phase
        await save_session_state(state)


async def delete_session_state(session_id: str) -> None:
    await _redis_op(lambda r: r.delete(f"session:{session_id}"))


def _question_batch_key(session_id: str) -> str:
    return f"session:{session_id}:diagnosis_question_batch_id"


async def save_diagnosis_question_batch_ref(session_id: str, batch_id: int) -> None:
    await _redis_op(lambda r: r.setex(_question_batch_key(session_id), SESSION_TTL, str(batch_id)))


async def get_diagnosis_question_batch_ref(session_id: str) -> Optional[int]:
    raw = await _redis_op(lambda r: r.get(_question_batch_key(session_id)))
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


async def delete_diagnosis_question_batch_ref(session_id: str) -> None:
    await _redis_op(lambda r: r.delete(_question_batch_key(session_id)))
