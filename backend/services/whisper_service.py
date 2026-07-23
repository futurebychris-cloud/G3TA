"""Proxy recorded speech to a local multilingual Whisper service."""

from __future__ import annotations

import json
import os
import secrets
import urllib.error
import urllib.parse
import urllib.request


WHISPER_ASR_URL = os.getenv("WHISPER_ASR_URL", "http://127.0.0.1:9000/asr")
WHISPER_TIMEOUT_SECONDS = 120
MAX_AUDIO_BYTES = 15 * 1024 * 1024

LANGUAGE_NAMES = {
    "ar": "Arabic",
    "de": "German",
    "en": "English",
    "es": "Spanish",
    "fr": "French",
    "hi": "Hindi",
    "id": "Indonesian",
    "it": "Italian",
    "ja": "Japanese",
    "ko": "Korean",
    "nl": "Dutch",
    "pl": "Polish",
    "pt": "Portuguese",
    "ru": "Russian",
    "th": "Thai",
    "tr": "Turkish",
    "uk": "Ukrainian",
    "vi": "Vietnamese",
    "zh": "Chinese",
}


def _multipart_audio(audio: bytes, content_type: str) -> tuple[bytes, str]:
    boundary = f"g3ta-{secrets.token_hex(16)}"
    extension = "mp4" if "mp4" in content_type or "aac" in content_type else "webm"
    body = b"".join([
        f"--{boundary}\r\n".encode(),
        (
            f'Content-Disposition: form-data; name="audio_file"; '
            f'filename="speech.{extension}"\r\n'
        ).encode(),
        f"Content-Type: {content_type}\r\n\r\n".encode(),
        audio,
        f"\r\n--{boundary}--\r\n".encode(),
    ])
    return body, boundary


def transcribe_speech(audio: bytes, content_type: str = "audio/webm", task: str = "transcribe") -> dict[str, str]:
    """Transcribe (or translate-to-English) recorded speech via the local Whisper service.

    task="translate" uses Whisper's built-in translation mode: it auto-detects the
    spoken language same as "transcribe", but returns English text regardless of
    the source language. `language`/`language_name` in the result still report the
    ORIGINAL spoken language, so the caller can show "heard in Spanish, shown in
    English" even though `text` itself is already English.
    """
    if not audio:
        raise ValueError("Recorded audio is empty.")
    if len(audio) > MAX_AUDIO_BYTES:
        raise ValueError("Recorded audio is too large.")
    if task not in ("transcribe", "translate"):
        task = "transcribe"

    body, boundary = _multipart_audio(audio, content_type or "audio/webm")
    query = urllib.parse.urlencode({
        "encode": "true",
        "task": task,
        "output": "json",
    })
    request = urllib.request.Request(
        f"{WHISPER_ASR_URL}?{query}",
        data=body,
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=WHISPER_TIMEOUT_SECONDS) as response:
            raw = response.read(2 * 1024 * 1024)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(
            "Automatic language detection is unavailable. Start the local Whisper service and try again."
        ) from exc

    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise RuntimeError("Whisper returned an invalid transcription response.") from exc

    text = str(payload.get("text") or "").strip()
    language = str(payload.get("language") or "").strip().casefold()
    if not text:
        raise ValueError("No speech was detected. Please try again.")
    return {
        "text": text,
        "language": language,
        "language_name": LANGUAGE_NAMES.get(language, language.upper() or "Unknown"),
        "translated": task == "translate" and language not in ("", "en"),
    }
