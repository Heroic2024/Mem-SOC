"""
Groq API client for the Stage 4 report-generation pipeline.

Uses `requests` directly against Groq's OpenAI-compatible chat-completions
endpoint. No extra Groq SDK dependency is required.
"""

import time

import requests

from memsoc.triage import config


class GroqAPIKeyMissing(RuntimeError):
    pass


def call_groq(prompt: str):
    """
    Send `prompt` to Groq and return (response_text, latency_ms).

    Raises GroqAPIKeyMissing if the configured API key is still the
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
        "reasoning_effort": config.GROQ_REASONING_EFFORT,
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

    try:
        text = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as e:
        raise RuntimeError(
            "Groq response did not contain message content. "
            f"Response: {body}"
        ) from e

    if not text or not text.strip():
        finish_reason = None
        reasoning_chars = 0

        try:
            choice = body["choices"][0]
            finish_reason = choice.get("finish_reason")
            reasoning = choice.get("message", {}).get("reasoning_content")
            reasoning_chars = len(reasoning or "")
        except (KeyError, IndexError, TypeError):
            pass

        raise RuntimeError(
            "Groq returned an empty response. "
            f"finish_reason={finish_reason}, "
            f"reasoning_chars={reasoning_chars}. "
            "The model may have exhausted its completion budget "
            "before producing the requested report."
        )

    return text, latency_ms