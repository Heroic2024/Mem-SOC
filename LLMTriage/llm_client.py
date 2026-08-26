"""
Groq API client for the Stage 4 report-generation pipeline.

Uses `requests` directly against Groq's OpenAI-compatible chat-completions
endpoint -- no extra SDK dependency, consistent with what the rest of this
repo already uses (log_generation/replay_to_api.py,
final_ml_model_v1/test_api.py both call the `requests` library directly).
"""

import time

import requests

import config


class GroqAPIKeyMissing(RuntimeError):
    pass


def call_groq(prompt: str):
    """
    Send `prompt` to Groq and return (response_text, latency_ms).

    Raises GroqAPIKeyMissing if config.GROQ_API_KEY is still the
    placeholder. Raises requests.HTTPError on a non-2xx response.
    """

    if config.GROQ_API_KEY == config.GROQ_API_KEY_PLACEHOLDER:
        raise GroqAPIKeyMissing(
            "GROQ_API_KEY is not set. Either set the GROQ_API_KEY "
            "environment variable, or replace the placeholder in "
            "LLMTriage/config.py with your real key."
        )

    headers = {
        "Authorization": f"Bearer {config.GROQ_API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": config.GROQ_MODEL,
        "temperature": config.TEMPERATURE,
        "max_tokens": config.MAX_RESPONSE_TOKENS,
        "messages": [
            {"role": "user", "content": prompt}
        ],
    }

    start = time.time()

    response = requests.post(
        config.GROQ_API_URL,
        headers=headers,
        json=payload,
        timeout=120,
    )

    latency_ms = (time.time() - start) * 1000

    try:
        response.raise_for_status()
    except requests.HTTPError as e:
        raise requests.HTTPError(
            f"{e}\nGroq response body: {response.text[:1000]}"
        ) from e

    body = response.json()

    text = body["choices"][0]["message"]["content"]

    return text, latency_ms
