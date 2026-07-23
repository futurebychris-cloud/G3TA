#!/usr/bin/env python3
"""Small local Piper HTTP service for G3TA.

English requests can use an authorized custom model mounted at runtime through
PIPER_CUSTOM_MODEL. Mandarin retains its bundled model unless separately
configured. Generated WAV files are cached by text, language, speed, and model.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import threading
from pathlib import Path

from flask import Flask, abort, request, send_file

PIPER_BIN = os.getenv("PIPER_BIN", "/opt/piper/piper")
CACHE_DIR = Path(os.getenv("PIPER_CACHE_DIR", "/cache"))
CACHE_DIR.mkdir(parents=True, exist_ok=True)
MAX_TEXT_LENGTH = 12_000

DEFAULT_MODELS = {
    "en": "/models/en_US-lessac-medium.onnx",
    "zh": "/models/zh_CN-huayan-medium.onnx",
}
MODELS = {
    "en": os.getenv("PIPER_CUSTOM_MODEL") or os.getenv("PIPER_EN_MODEL") or DEFAULT_MODELS["en"],
    "zh": os.getenv("PIPER_ZH_MODEL") or DEFAULT_MODELS["zh"],
}

app = Flask(__name__)
_render_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def _language(value: object) -> str:
    return "zh" if str(value or "").casefold().startswith("zh") else "en"


def _speed(value: object) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = 1.0
    return min(1.5, max(0.6, parsed))


def _model_for(language: str) -> Path:
    model = Path(MODELS[language])
    config = Path(f"{model}.json")
    if not model.is_file() or not config.is_file():
        app.logger.error("Piper model or config is missing: %s", model)
        abort(503, description=f"Piper {language} voice is not installed.")
    return model


def _lock_for(cache_key: str) -> threading.Lock:
    with _locks_guard:
        return _render_locks.setdefault(cache_key, threading.Lock())


def synthesize(text: str, language: str, speed: float) -> Path:
    model = _model_for(language)
    cache_key = hashlib.sha256(
        f"{model}|{language}|{speed:.2f}|{text}".encode("utf-8")
    ).hexdigest()
    output = CACHE_DIR / f"{cache_key}.wav"
    if output.exists() and output.stat().st_size > 44:
        return output

    with _lock_for(cache_key):
        if output.exists() and output.stat().st_size > 44:
            return output
        temporary = output.with_suffix(".tmp.wav")
        command = [
            PIPER_BIN,
            "--model",
            str(model),
            "--output_file",
            str(temporary),
            "--length_scale",
            f"{1 / speed:.4f}",
        ]
        process = subprocess.run(
            command,
            input=text.encode("utf-8"),
            capture_output=True,
            check=False,
        )
        if process.returncode != 0 or not temporary.exists() or temporary.stat().st_size <= 44:
            temporary.unlink(missing_ok=True)
            app.logger.error(
                "Piper synthesis failed: %s",
                process.stderr.decode("utf-8", "replace"),
            )
            abort(502, description="Piper could not synthesize this text.")
        temporary.replace(output)
    return output


@app.post("/synthesize")
def synthesize_endpoint():
    payload = request.get_json(silent=True) or {}
    text = str(payload.get("text") or "").strip()
    if not text:
        abort(400, description="Text is required.")
    if len(text) > MAX_TEXT_LENGTH:
        abort(413, description=f"Text must be {MAX_TEXT_LENGTH} characters or fewer.")
    language = _language(payload.get("language"))
    speed = _speed(payload.get("speed"))
    wav = synthesize(text, language, speed)
    response = send_file(wav, mimetype="audio/wav", conditional=True)
    response.headers["Cache-Control"] = "private, max-age=86400"
    response.headers["X-Piper-Voice"] = Path(MODELS[language]).stem
    return response


@app.get("/health")
def health():
    voices = {
        language: {
            "ready": Path(model).is_file() and Path(f"{model}.json").is_file(),
            "name": Path(model).stem,
            "custom": language == "en" and bool(os.getenv("PIPER_CUSTOM_MODEL")),
        }
        for language, model in MODELS.items()
    }
    ready = all(voice["ready"] for voice in voices.values())
    return ({"status": "ok" if ready else "missing_model", "voices": voices}, 200 if ready else 503)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, threaded=True)
