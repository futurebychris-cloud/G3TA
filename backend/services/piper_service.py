"""Proxy arbitrary text to the local G3TA Piper speech service."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

PIPER_TTS_URL = os.getenv("PIPER_TTS_URL", "http://127.0.0.1:8083/synthesize")
PIPER_TIMEOUT_SECONDS = 45
MAX_AUDIO_BYTES = 25 * 1024 * 1024


def synthesize_speech(text: str, language: str = "en", speed: float = 1.0) -> bytes:
    payload = json.dumps({
        "text": text,
        "language": language,
        "speed": speed,
    }).encode("utf-8")
    request = urllib.request.Request(
        PIPER_TTS_URL,
        data=payload,
        headers={"Content-Type": "application/json", "Accept": "audio/wav"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=PIPER_TIMEOUT_SECONDS) as response:
            content_type = response.headers.get_content_type()
            audio = response.read(MAX_AUDIO_BYTES + 1)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(
            "Piper voice is unavailable. Start the local g3ta-piper container and try again."
        ) from exc
    if content_type not in {"audio/wav", "audio/x-wav"} or len(audio) <= 44:
        raise RuntimeError("Piper returned an invalid audio response.")
    if len(audio) > MAX_AUDIO_BYTES:
        raise RuntimeError("Piper audio response exceeded the safety limit.")
    return audio
