"""
LLM API clients: Groq for the Stage 4 report-generation pipeline, and
Groq or Gemini for per-alert triage, chosen once by
config.TRIAGE_PROVIDER and identical for every arm.

Uses `requests` directly against Groq's OpenAI-compatible chat-completions
endpoint -- no extra SDK dependency, consistent with what the rest of this
repo already uses (src/memsoc/logstream/replay_to_api.py calls the
`requests` library directly too).
"""

import json
import os
import re
import sys
import time
from datetime import datetime, timezone

import requests

from memsoc.triage import config


class GroqAPIKeyMissing(RuntimeError):
    pass


class DailyBudgetExhausted(RuntimeError):
    pass


def _budget(provider):
    """(state file, daily limit, reserve) for one provider's quota."""

    if provider == "gemini":
        return (
            config.GEMINI_REQUEST_BUDGET_PATH,
            config.GEMINI_DAILY_REQUEST_LIMIT,
            config.GEMINI_DAILY_REQUEST_RESERVE,
        )

    return (
        config.REQUEST_BUDGET_PATH,
        config.DAILY_REQUEST_LIMIT,
        config.DAILY_REQUEST_RESERVE,
    )


def _budget_state(provider="groq"):
    """
    Today's request count, reset automatically at UTC midnight.

    Dates are UTC because that is when the provider's quota rolls over;
    using local time would reset the counter at the wrong moment and
    silently overshoot.
    """

    path, _, _ = _budget(provider)

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                state = json.load(f)
            if state.get("date") == today:
                return state
        except (json.JSONDecodeError, OSError):
            pass

    return {"date": today, "count": 0}


def budget_remaining(provider="groq") -> int:
    """
    Requests left before the reserve is reached.

    Prefers the provider's own remaining count, recorded from the last
    response's headers, and falls back to the local tally only before
    any response has been seen.
    """

    _, limit, reserve = _budget(provider)

    state = _budget_state(provider)

    if "provider_remaining" in state:
        return state["provider_remaining"] - reserve

    return limit - reserve - state["count"]


def _charge_request(provider="groq") -> None:
    """
    Record one request against today's budget, before it is sent.

    Charged up front rather than on success: a 429 or a truncated
    response consumes the provider's quota just as a useful answer does,
    so counting only successes would undercount exactly the failures
    that make a run expensive.
    """

    path, limit, reserve = _budget(provider)

    state = _budget_state(provider)

    if "provider_remaining" in state:
        if state["provider_remaining"] <= reserve:
            raise DailyBudgetExhausted(
                f"Provider reports {state['provider_remaining']} requests "
                f"remaining, at or below the {reserve} "
                f"reserve (quota resets in {state.get('provider_reset', '?')}). "
                "Completed verdicts are durable and the run resumes where "
                "it stopped."
            )

    if state["count"] >= limit - reserve:
        raise DailyBudgetExhausted(
            f"Daily {provider} request budget reached: {state['count']} of "
            f"{limit} used "
            f"(reserve {reserve} held back). "
            "The quota resets at UTC midnight; completed verdicts are "
            "durable and the run resumes where it stopped."
        )

    state["count"] += 1

    path.parent.mkdir(parents=True, exist_ok=True)

    # Written to a temporary file and swapped in, so a concurrent reader
    # (one process per arm) never sees a half-written file -- which
    # _budget_state() would treat as unreadable and reset to zero.
    temporary = path.with_name(f"{path.name}.{os.getpid()}.tmp")

    with open(temporary, "w", encoding="utf-8") as f:
        json.dump(state, f)

    os.replace(temporary, path)


def _record_quota(response) -> None:
    """
    Store the provider's own remaining-request count from the response
    headers.

    This supersedes the locally counted total. The local counter has to
    guess at anything spent outside this process and cannot know the
    provider's refill schedule -- Groq's request quota resets on a
    rolling window, not at midnight, so a local daily tally drifts in
    both directions. The header is authoritative; the local count stays
    only as a fallback for the first call of a run, before any header
    has been seen.
    """

    remaining = response.headers.get("x-ratelimit-remaining-requests")

    if remaining is None:
        return

    try:
        remaining = int(remaining)
    except ValueError:
        return

    state = _budget_state()
    state["provider_remaining"] = remaining
    state["provider_reset"] = response.headers.get(
        "x-ratelimit-reset-requests", ""
    )

    with open(config.REQUEST_BUDGET_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f)


def _retry_after_seconds(response) -> float:
    """
    How long Groq says to wait before retrying a rate-limited request.

    Prefers the standard Retry-After header, falls back to the delay
    quoted in the error body ("Please try again in 20.22s"), and finally
    to a fixed wait. Honouring the server's own number avoids both
    hammering it and sleeping far longer than required.
    """

    header = response.headers.get("Retry-After")

    if header:
        try:
            return float(header)
        except ValueError:
            pass

    match = re.search(r"try again in ([0-9.]+)s", response.text)

    if match:
        return float(match.group(1))

    return config.RATE_LIMIT_FALLBACK_WAIT


# Distinguishes "caller said nothing about reasoning effort" from
# "caller explicitly wants the parameter omitted". The report path relies
# on the first, the triage path on the second, and None cannot express
# both.
_EFFORT_UNSET = object()


def call_groq(prompt: str, max_tokens: int = None,
              reasoning_effort=_EFFORT_UNSET, model: str = None):
    """
    Send `prompt` to Groq and return (response_text, latency_ms).

    `model` defaults to config.GROQ_MODEL, the report model. The triage
    path passes config.GROQ_TRIAGE_MODEL so the two can differ.

    `reasoning_effort` defaults to config.GROQ_REASONING_EFFORT, which the
    aggregate report path uses. Pass None to omit the parameter entirely,
    as the per-alert triage path does: the parameter changes how hard the
    model thinks, and the 2026-08-30 baseline verdicts were produced
    without it.

    `max_tokens` defaults to config.MAX_RESPONSE_TOKENS, which is sized
    for the aggregate report. Callers producing short structured output
    should pass a smaller value: Groq bills the *requested* max_tokens
    against the tokens-per-minute quota regardless of how much the model
    actually returns, so an oversized reservation throttles throughput
    for no benefit.

    HTTP 429 is retried up to config.RATE_LIMIT_MAX_RETRIES times,
    waiting as long as the server asks. Every other non-2xx status
    raises immediately -- a 401 or a 400 will not fix itself, and
    retrying it would waste the budget.

    Raises GroqAPIKeyMissing if config.GROQ_API_KEY is still the
    placeholder. Raises requests.HTTPError on a non-2xx response, or
    after the retry budget for 429 is exhausted.
    """

    if config.GROQ_API_KEY == config.GROQ_API_KEY_PLACEHOLDER:
        raise GroqAPIKeyMissing(
            "GROQ_API_KEY is not set. Either set the GROQ_API_KEY "
            "environment variable, or replace the placeholder in "
            "src/memsoc/triage/config.py with your real key."
        )

    headers = {
        "Authorization": f"Bearer {config.GROQ_API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": config.GROQ_MODEL if model is None else model,
        "temperature": config.TEMPERATURE,
        "max_tokens": (
            config.MAX_RESPONSE_TOKENS if max_tokens is None else max_tokens
        ),
        "messages": [
            {"role": "user", "content": prompt}
        ],
    }

    effort = (
        config.GROQ_REASONING_EFFORT
        if reasoning_effort is _EFFORT_UNSET
        else reasoning_effort
    )

    if effort is not None:
        payload["reasoning_effort"] = effort

    # Two independent retry budgets. A run that waits out several rate
    # limits has not used up its tolerance for truncated reasoning, and
    # vice versa -- sharing one counter between them would let a burst
    # of 429s cause an unrelated alert to be abandoned.
    rate_limits = 0
    truncations = 0

    while True:

        _charge_request()

        start = time.time()

        response = requests.post(
            config.GROQ_API_URL,
            headers=headers,
            json=payload,
            timeout=120,
        )

        latency_ms = (time.time() - start) * 1000

        _record_quota(response)

        if (response.status_code == 429
                and rate_limits < config.RATE_LIMIT_MAX_RETRIES):

            rate_limits += 1
            wait = _retry_after_seconds(response)

            print(
                f"  rate limited, waiting {wait:.0f}s "
                f"({rate_limits}/{config.RATE_LIMIT_MAX_RETRIES})",
                file=sys.stderr,
            )

            time.sleep(wait)
            continue

        try:
            response.raise_for_status()
        except requests.HTTPError as e:
            raise requests.HTTPError(
                f"{e}\nGroq response body: {response.text[:1000]}"
            ) from e

        body = response.json()

        choice = body["choices"][0]

        # A reasoning model can exhaust max_tokens while still thinking
        # and return empty content with finish_reason "length". Reported
        # here rather than downstream, where it surfaces as a confusing
        # "response was not valid JSON" against an empty string.
        if choice.get("finish_reason") == "length":

            reasoning = (
                body.get("usage", {})
                .get("completion_tokens_details", {})
                .get("reasoning_tokens")
            )
            detail = (
                f"{payload['max_tokens']}-token cap"
                + (f", {reasoning} spent reasoning" if reasoning else "")
            )

            # Reasoning length varies between identical calls, so one
            # truncation is not proof the alert is untriageable. Retry
            # before giving up -- but never substitute a default
            # verdict, which would be indistinguishable downstream from
            # one the model actually reached.
            if truncations < config.TRUNCATION_MAX_RETRIES:

                truncations += 1

                print(
                    f"  truncated ({detail}), retrying "
                    f"{truncations}/{config.TRUNCATION_MAX_RETRIES}",
                    file=sys.stderr,
                )
                continue

            raise requests.HTTPError(
                f"Response hit the {detail} on "
                f"{config.TRUNCATION_MAX_RETRIES + 1} consecutive attempts. "
                "This alert needs an explicit decision -- raise max_tokens "
                "further, or exclude it from both arms and document the "
                "exclusion."
            )

        text = choice["message"]["content"]

        # Content can come back empty under a finish_reason other than
        # "length" as well. Reported here rather than downstream, where it
        # surfaces as a confusing "response was not valid JSON" against an
        # empty string.
        if not text or not text.strip():

            reasoning = choice.get("message", {}).get("reasoning_content")

            raise RuntimeError(
                "Groq returned an empty response. "
                f"finish_reason={choice.get('finish_reason')}, "
                f"reasoning_chars={len(reasoning or '')}."
            )

        return text, latency_ms


class GeminiAPIKeyMissing(RuntimeError):
    pass


def _gemini_retry(response):
    """
    (seconds to wait, is_daily) for a Gemini 429.

    Gemini reports which quota tripped in the error details. A per-day
    quota will not clear by waiting a minute, so it stops the run --
    retrying it would only spend requests learning the same thing.
    """

    try:
        details = response.json().get("error", {}).get("details", [])
    except ValueError:
        details = []

    wait = config.RATE_LIMIT_FALLBACK_WAIT
    daily = False

    for detail in details:

        kind = detail.get("@type", "")

        if kind.endswith("RetryInfo"):
            delay = str(detail.get("retryDelay", "")).rstrip("s")
            try:
                wait = float(delay) + 1.0
            except ValueError:
                pass

        if kind.endswith("QuotaFailure"):
            for violation in detail.get("violations", []):
                if "PerDay" in violation.get("quotaId", ""):
                    daily = True

    return wait, daily


def call_gemini(prompt: str, max_tokens: int = None):
    """
    Send `prompt` to Gemini and return (response_text, latency_ms).

    Mirrors call_groq(): charged before sending, 429 retried as long as
    the server asks up to config.RATE_LIMIT_MAX_RETRIES, a per-day quota
    raises DailyBudgetExhausted, a response cut off at the token cap is
    retried config.TRUNCATION_MAX_RETRIES times and then raises. Nothing
    is ever defaulted or repaired.

    The thinking level is left at the model's default, as the Groq
    triage path leaves reasoning_effort unset.
    """

    if not config.GEMINI_API_KEY:
        raise GeminiAPIKeyMissing(
            "GEMINI_API_KEY is not set. Export it from .env into the "
            "environment before running triage."
        )

    headers = {
        "x-goog-api-key": config.GEMINI_API_KEY,
        "Content-Type": "application/json",
    }

    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": config.GEMINI_TEMPERATURE,
            "maxOutputTokens": (
                config.GEMINI_MAX_RESPONSE_TOKENS if max_tokens is None else max_tokens
            ),
            "responseMimeType": "application/json",
        },
    }

    rate_limits = 0
    truncations = 0
    server_errors = 0

    while True:

        _charge_request("gemini")

        start = time.time()

        response = requests.post(
            config.GEMINI_API_URL,
            headers=headers,
            json=payload,
            timeout=180,
        )

        latency_ms = (time.time() - start) * 1000

        if response.status_code == 429:

            wait, daily = _gemini_retry(response)

            if daily:
                raise DailyBudgetExhausted(
                    "Gemini reports the per-day request quota is used up. "
                    "Completed verdicts are durable and the run resumes "
                    f"where it stopped.\n{response.text[:800]}"
                )

            if rate_limits < config.RATE_LIMIT_MAX_RETRIES:

                rate_limits += 1

                print(
                    f"  rate limited, waiting {wait:.0f}s "
                    f"({rate_limits}/{config.RATE_LIMIT_MAX_RETRIES})",
                    file=sys.stderr,
                )

                time.sleep(wait)
                continue

        if (response.status_code in (500, 503)
                and server_errors < config.SERVER_ERROR_MAX_RETRIES):

            server_errors += 1
            wait = config.SERVER_ERROR_BASE_WAIT * server_errors

            print(
                f"  server busy ({response.status_code}), waiting {wait:.0f}s "
                f"({server_errors}/{config.SERVER_ERROR_MAX_RETRIES})",
                file=sys.stderr,
            )

            time.sleep(wait)
            continue

        try:
            response.raise_for_status()
        except requests.HTTPError as e:
            raise requests.HTTPError(
                f"{e}\nGemini response body: {response.text[:1000]}"
            ) from e

        body = response.json()

        candidates = body.get("candidates") or []

        if not candidates:
            raise RuntimeError(
                "Gemini returned no candidates. "
                f"promptFeedback={body.get('promptFeedback')}"
            )

        candidate = candidates[0]
        finish = candidate.get("finishReason")

        if finish == "MAX_TOKENS":

            usage = body.get("usageMetadata", {})
            detail = (
                f"{payload['generationConfig']['maxOutputTokens']}-token cap, "
                f"{usage.get('thoughtsTokenCount', '?')} spent thinking"
            )

            if truncations < config.TRUNCATION_MAX_RETRIES:

                truncations += 1

                print(
                    f"  truncated ({detail}), retrying "
                    f"{truncations}/{config.TRUNCATION_MAX_RETRIES}",
                    file=sys.stderr,
                )
                continue

            raise requests.HTTPError(
                f"Response hit the {detail} on "
                f"{config.TRUNCATION_MAX_RETRIES + 1} consecutive attempts. "
                "This alert needs an explicit decision."
            )

        # Thought summaries, if any come back, are flagged and are not
        # part of the answer.
        parts = (candidate.get("content") or {}).get("parts") or []
        text = "".join(
            part.get("text", "") for part in parts if not part.get("thought")
        )

        if not text.strip():
            raise RuntimeError(
                f"Gemini returned an empty response. finishReason={finish}."
            )

        return text, latency_ms


def triage_model_id() -> str:
    """The model the triage path calls, as recorded in every verdict row."""

    if config.TRIAGE_PROVIDER == "gemini":
        return config.GEMINI_MODEL

    return config.GROQ_TRIAGE_MODEL


def call_triage_llm(prompt: str):
    """
    The per-alert triage call, for every arm.

    The one place the triage provider is chosen. Arms differ only in the
    prompt they pass, never in how it is sent.
    """

    if config.TRIAGE_PROVIDER == "gemini":
        return call_gemini(prompt)

    return call_groq(
        prompt,
        max_tokens=config.TRIAGE_MAX_RESPONSE_TOKENS,
        reasoning_effort=config.TRIAGE_REASONING_EFFORT,
        model=config.GROQ_TRIAGE_MODEL,
    )
