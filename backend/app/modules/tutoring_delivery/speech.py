import asyncio
import io
import json
import logging
import math
import uuid
import wave
from dataclasses import dataclass
from typing import Sequence
from xml.sax.saxutils import escape

from app.core.config import settings
from app.models.schemas import AudioMarker, DeliveryStep

logger = logging.getLogger(__name__)


@dataclass
class SpeechSynthesisResult:
    clip_id: str
    audio_bytes: bytes
    media_type: str
    audio_duration_ms: int
    markers: list[AudioMarker]
    provider: str


def _step_word_count(step: DeliveryStep) -> int:
    text = step.spoken_text or step.display_text or ""
    return max(1, len(text.split()))


def _estimate_marker_times(steps: Sequence[DeliveryStep]) -> tuple[list[AudioMarker], int]:
    markers: list[AudioMarker] = []
    cursor = 0

    for step in steps:
        markers.append(AudioMarker(name=step.step_id, time_ms=cursor))
        if step.kind == "pause":
            duration = 500
        else:
            duration = max(700, _step_word_count(step) * 320)
        cursor += duration

    return markers, max(cursor, 1200)


def _build_ssml(steps: Sequence[DeliveryStep]) -> str:
    parts = ["<speak>"]
    for step in steps:
        if not step.spoken_text:
            if step.kind == "pause":
                parts.append('<break time="500ms"/>')
            continue
        parts.append(f'<mark name="{escape(step.step_id)}"/>')
        parts.append(f"<p>{escape(step.spoken_text)}</p>")
    parts.append("</speak>")
    return "".join(parts)


def _render_silent_wav(duration_ms: int) -> bytes:
    sample_rate = 22050
    frame_count = max(1, math.ceil(sample_rate * (duration_ms / 1000)))
    silence = b"\x00\x00" * frame_count
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(silence)
    return buffer.getvalue()


class MockSpeechProvider:
    provider_name = "mock"

    async def synthesize(self, steps: Sequence[DeliveryStep]) -> SpeechSynthesisResult:
        markers, duration_ms = _estimate_marker_times(steps)
        return SpeechSynthesisResult(
            clip_id=str(uuid.uuid4()),
            audio_bytes=_render_silent_wav(duration_ms),
            media_type="audio/wav",
            audio_duration_ms=duration_ms,
            markers=markers,
            provider=self.provider_name,
        )


class PollySpeechProvider:
    provider_name = "polly"

    def __init__(self) -> None:
        try:
            import boto3  # type: ignore
        except ImportError as exc:
            raise RuntimeError("boto3 is required for Polly speech synthesis") from exc

        client_kwargs = {"region_name": settings.aws_region}
        if settings.aws_access_key_id and settings.aws_secret_access_key:
            client_kwargs["aws_access_key_id"] = settings.aws_access_key_id
            client_kwargs["aws_secret_access_key"] = settings.aws_secret_access_key
        if settings.aws_session_token:
            client_kwargs["aws_session_token"] = settings.aws_session_token

        self._client = boto3.client("polly", **client_kwargs)

    async def synthesize(self, steps: Sequence[DeliveryStep]) -> SpeechSynthesisResult:
        ssml = _build_ssml(steps)
        return await asyncio.to_thread(self._synthesize_blocking, ssml)

    def _synthesize_blocking(self, ssml: str) -> SpeechSynthesisResult:
        audio_response = self._client.synthesize_speech(
            VoiceId=settings.tts_voice_id,
            OutputFormat="mp3",
            TextType="ssml",
            Text=ssml,
        )
        marks_response = self._client.synthesize_speech(
            VoiceId=settings.tts_voice_id,
            OutputFormat="json",
            TextType="ssml",
            Text=ssml,
            SpeechMarkTypes=["ssml", "word"],
        )

        audio_bytes = audio_response["AudioStream"].read()
        marks_text = marks_response["AudioStream"].read().decode("utf-8")

        markers: list[AudioMarker] = []
        last_time = 0
        for line in marks_text.splitlines():
            line = line.strip()
            if not line:
                continue
            payload = json.loads(line)
            mark_time = int(payload.get("time", 0))
            last_time = max(last_time, mark_time)
            if payload.get("type") == "ssml":
                markers.append(AudioMarker(name=payload["value"], time_ms=mark_time))

        return SpeechSynthesisResult(
            clip_id=str(uuid.uuid4()),
            audio_bytes=audio_bytes,
            media_type="audio/mpeg",
            audio_duration_ms=max(last_time + 600, 1200),
            markers=markers,
            provider=self.provider_name,
        )


async def synthesize_package_audio(steps: Sequence[DeliveryStep]) -> SpeechSynthesisResult:
    if settings.tts_provider == "polly":
        try:
            return await PollySpeechProvider().synthesize(steps)
        except Exception as exc:
            logger.warning("Polly synthesis failed; falling back to mock audio: %s", exc)

    return await MockSpeechProvider().synthesize(steps)
