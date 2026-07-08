"""Voice provider abstraction (STT + TTS), swappable like the LLM provider.

Default is **browser** mode: the client uses the Web Speech API for both
speech-to-text and text-to-speech, so the voice channel works with zero keys in
Chrome. When DEEPGRAM_API_KEY / ELEVENLABS_API_KEY are set, the server can do
server-side transcription/synthesis instead — `voice_config()` tells the client
which mode to use, and `synthesize()` returns audio bytes when ElevenLabs is
configured. Either way it's the *same* agent brain behind the channel.
"""
from __future__ import annotations

import logging

import httpx

from app.config import get_settings

logger = logging.getLogger("northwind.voice")


def voice_config() -> dict:
    """Which STT/TTS backend the client should use, based on configured keys."""
    s = get_settings()
    return {
        "stt": "deepgram" if getattr(s, "deepgram_api_key", None) else "browser",
        "tts": "elevenlabs" if getattr(s, "elevenlabs_api_key", None) else "browser",
        "server_audio": bool(getattr(s, "elevenlabs_api_key", None)),
    }


def synthesize(text: str) -> bytes | None:
    """Synthesize speech with ElevenLabs when configured; else None (browser TTS).

    Streaming, low-latency voice id is used; callers degrade to browser TTS when
    this returns None so a missing key never breaks the channel.
    """
    s = get_settings()
    key = getattr(s, "elevenlabs_api_key", None)
    if not key:
        return None
    try:  # pragma: no cover - exercised only when a key is configured
        voice_id = "21m00Tcm4TlvDq8ikWAM"  # a default ElevenLabs voice
        r = httpx.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream",
            headers={"xi-api-key": key, "accept": "audio/mpeg"},
            json={"text": text, "model_id": "eleven_turbo_v2"},
            timeout=30,
        )
        r.raise_for_status()
        return r.content
    except Exception as e:
        logger.warning("ElevenLabs synthesis failed (%s); falling back to browser TTS.", e)
        return None
