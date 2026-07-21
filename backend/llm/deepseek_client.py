"""Thin DeepSeek client (OpenAI-compatible).

All agents and the orchestrator go through `chat_json` so there's exactly one
place that talks to the LLM. Uses the OpenAI SDK pointed at DeepSeek's endpoint.
"""
import json
import os

from openai import OpenAI

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        api_key = os.getenv("DEEPSEEK_API_KEY")
        if not api_key:
            raise RuntimeError(
                "DEEPSEEK_API_KEY is not set. Copy .env.example to .env and add your "
                "DeepSeek key, then restart the backend. See README.md > Setup."
            )
        base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
        _client = OpenAI(api_key=api_key, base_url=base_url)
    return _client


def model_name() -> str:
    return os.getenv("DEEPSEEK_MODEL", "deepseek-chat")


def chat_json(system_prompt: str, user_prompt: str, temperature: float = 0.4) -> dict:
    """Send one system+user turn and parse the reply as a JSON object.

    Relies on DeepSeek's JSON output mode. Raises RuntimeError if the key is
    missing; raises json.JSONDecodeError if the model returns non-JSON (callers
    that want robustness should catch and fall back).
    """
    client = _get_client()
    resp = client.chat.completions.create(
        model=model_name(),
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=temperature,
        response_format={"type": "json_object"},
    )
    content = resp.choices[0].message.content or "{}"
    return json.loads(content)
