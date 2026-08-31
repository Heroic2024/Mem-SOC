"""
Groq API client for the Stage 4 report-generation pipeline.

Uses `requests` directly against Groq's OpenAI-compatible chat-completions
endpoint -- no extra SDK dependency, consistent with what the rest of this
repo already uses (log_generation/replay_to_api.py,
final_ml_model_v1/test_api.py both call the `requests` library directly).
"""

import json
import re
import sys
import time
from datetime import datetime, timezone

import requests

import config


class GroqAPIKeyMissing(RuntimeError):
    pass


class DailyBudgetExhausted(RuntimeError):
    pass


def _budget_state():
    """
    Today's request count, reset automatically at UTC midnight.

    Dates are UTC because that is when the provider's quota rolls over;
    using local time would reset the counter at the wrong moment and
    silently overshoot.
    """

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    if config.REQUEST_BUDGET_PATH.exists():
        try:
            with open(config.REQUEST_BUDGET_PATH, "r", encoding="utf-8") as f:
                state = json.load(f)
            if state.get("date") == today:
                return state
        except (json.JSONDecodeError, OSError):
            pass

    return {"date": today, "count": 0}


def budget_remaining() -> int:
    """
    Requests left before the reserve is reached.

    Prefers the provider's own remaining count, recorded from the last
    response's headers, and falls back to the local tally only before
    any response has been seen.
    """

    state = _budget_state()

    if "provider_remaining" in state:
        return state["provider_remaining"] - config.DAILY_REQUEST_RESERVE

    usable = config.DAILY_REQUEST_LIMIT - config.DAILY_REQUEST_RESERVE

    return usable - state["count"]


def _charge_request() -> None:
    """
    Record one request against today's budget, before it is sent.

    Charged up front rather than on success: a 429 or a truncated
    response consumes the provider's quota just as a useful answer does,
    so counting only successes would undercount exactly the failures
    that make a run expensive.
    """

    state = _budget_state()

    if "provider_remaining" in state:
        if state["provider_remaining"] <= config.DAILY_REQUEST_RESERVE:
            raise DailyBudgetExhausted(
                f"Provider reports {state['provider_remaining']} requests "
                f"remaining, at or below the {config.DAILY_REQUEST_RESERVE} "
                f"reserve (quota resets in {state.get('provider_reset', '?')}). "
                "Completed verdicts are durable and the run resumes where "
                "it stopped."
            )

    usable = config.DAILY_REQUEST_LIMIT - config.DAILY_REQUEST_RESERVE

    if state["count"] >= usable:
        raise DailyBudgetExhausted(
            f"Daily request budget reached: {state['count']} of "
            f"{config.DAILY_REQUEST_LIMIT} used "
            f"(reserve {config.DAILY_REQUEST_RESERVE} held back). "
            "The quota resets at UTC midnight; completed verdicts are "
            "durable and the run resumes where it stopped."
        )

    state["count"] += 1

    config.REQUEST_BUDGET_PATH.parent.mkdir(parents=True, exist_ok=True)

    with open(config.REQUEST_BUDGET_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f)


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


def call_groq(prompt: str, max_tokens: int = None):
    """
    Send `prompt` to Groq and return (response_text, latency_ms).

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
            "LLMTriage/config.py with your real key."
        )

    headers = {
        "Authorization": f"Bearer {config.GROQ_API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": config.GROQ_MODEL,
        "temperature": config.TEMPERATURE,
        "max_tokens": (
            config.MAX_RESPONSE_TOKENS if max_tokens is None else max_tokens
        ),
        "messages": [
            {"role": "user", "content": prompt}
        ],
    }

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

        return choice["message"]["content"], latency_ms
