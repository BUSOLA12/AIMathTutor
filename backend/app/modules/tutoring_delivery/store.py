import base64
import json
from typing import Optional

from app.models.schemas import DeliveryPackage
from app.session.manager import SESSION_TTL, get_redis


def _package_key(session_id: str, package_id: str) -> str:
    return f"delivery:package:{session_id}:{package_id}"


def _prefetch_key(session_id: str, section_index: int) -> str:
    return f"delivery:prefetch:{session_id}:{section_index}"


def _audio_key(session_id: str, clip_id: str) -> str:
    return f"delivery:audio:{session_id}:{clip_id}"


async def save_delivery_package(
    session_id: str,
    package: DeliveryPackage,
    *,
    section_index: Optional[int] = None,
) -> None:
    redis = await get_redis()
    await redis.setex(
        _package_key(session_id, package.package_id),
        SESSION_TTL,
        package.model_dump_json(),
    )
    if section_index is not None:
        await redis.setex(
            _prefetch_key(session_id, section_index),
            SESSION_TTL,
            package.package_id,
        )


async def get_delivery_package(session_id: str, package_id: str) -> Optional[DeliveryPackage]:
    redis = await get_redis()
    raw = await redis.get(_package_key(session_id, package_id))
    if raw is None:
        return None
    return DeliveryPackage(**json.loads(raw))


async def get_prefetched_package(session_id: str, section_index: int) -> Optional[DeliveryPackage]:
    redis = await get_redis()
    package_id = await redis.get(_prefetch_key(session_id, section_index))
    if package_id is None:
        return None
    return await get_delivery_package(session_id, package_id)


async def pop_prefetched_package(session_id: str, section_index: int) -> Optional[DeliveryPackage]:
    redis = await get_redis()
    package_id = await redis.get(_prefetch_key(session_id, section_index))
    if package_id is None:
        return None
    await redis.delete(_prefetch_key(session_id, section_index))
    return await get_delivery_package(session_id, package_id)


async def save_audio_clip(
    session_id: str,
    clip_id: str,
    *,
    media_type: str,
    audio_bytes: bytes,
    provider: str,
) -> None:
    redis = await get_redis()
    payload = {
        "media_type": media_type,
        "provider": provider,
        "audio_base64": base64.b64encode(audio_bytes).decode("ascii"),
    }
    await redis.setex(_audio_key(session_id, clip_id), SESSION_TTL, json.dumps(payload))


async def get_audio_clip(session_id: str, clip_id: str) -> Optional[dict]:
    redis = await get_redis()
    raw = await redis.get(_audio_key(session_id, clip_id))
    if raw is None:
        return None

    payload = json.loads(raw)
    return {
        "media_type": payload["media_type"],
        "provider": payload.get("provider", "unknown"),
        "audio_bytes": base64.b64decode(payload["audio_base64"]),
    }
