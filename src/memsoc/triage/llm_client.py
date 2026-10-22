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

from pathlib import Path

import requests

from memsoc import paths
from memsoc.triage import config


class GroqAPIKeyMissing(RuntimeError):
    pass


class DailyBudgetExhausted(RuntimeError):
    """
    A per-day quota is used up. `retry_after` is the provider's own wait
    in seconds when it gave one (Groq's daily windows roll), else None.
    """

    def __init__(self, message, retry_after=None):

        super().__init__(message)
        self.retry_after = retry_after


# Token usage of the last successful call, as the provider reported it.
# Read by protocol_run.py to log tokens per verdict; the free tiers' daily
# token caps make this the number that sets how long a run takes.
LAST_USAGE = {}


def _default_model(provider):
    """The model a budget question refers to when the caller names none."""

    if provider == config.TRIAGE_PROVIDER:
        return config.TRIAGE_MODEL

    return config.GROQ_MODEL if provider == "groq" else config.GEMINI_MODEL


def _budget(provider, model=None):
    """
    (state file, daily limit, reserve) for one model's quota.

    Per model, not per provider (BL-121): the free tiers meter each model
    separately, and one shared tally stopped a 14,400-a-day model at 480.
    """

    model = model or _default_model(provider)

    limit = config.DAILY_REQUEST_LIMITS.get(model, config.DEFAULT_DAILY_REQUEST_LIMIT)

    reserve = (
        config.GEMINI_DAILY_REQUEST_RESERVE
        if provider == "gemini"
        else config.DAILY_REQUEST_RESERVE
    )

    # Never hold back more than 5% of a model's allowance: a fixed reserve
    # of 20 against a 20-a-day model would forbid every request.
    reserve = min(reserve, limit // 20)

    return (
        Path(paths.request_budget(provider, model)),
        limit,
        reserve,
    )


def _budget_state(provider="groq", model=None):
    """
    Today's request count, reset automatically at UTC midnight.

    Dates are UTC because that is when the provider's quota rolls over;
    using local time would reset the counter at the wrong moment and
    silently overshoot.
    """

    path, _, _ = _budget(provider, model)

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


def budget_remaining(provider="groq", model=None) -> int:
    """
    Requests left before the reserve is reached.

    Prefers the provider's own remaining count, recorded from the last
    response's headers, and falls back to the local tally only before
    any response has been seen.
    """

    _, limit, reserve = _budget(provider, model)

    state = _budget_state(provider, model)

    if "provider_remaining" in state:
        return state["provider_remaining"] - reserve

    return limit - reserve - state["count"]


def _charge_request(provider="groq", model=None) -> None:
    """
    Record one request against today's budget, before it is sent.

    Charged up front rather than on success: a 429 or a truncated
    response consumes the provider's quota just as a useful answer does,
    so counting only successes would undercount exactly the failures
    that make a run expensive.
    """

    path, limit, reserve = _budget(provider, model)

    state = _budget_state(provider, model)

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
            f"Daily {provider} request budget for {model or _default_model(provider)} "
            f"reached: {state['count']} of "
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

    # On Windows the swap is refused while another arm has the file open
    # for reading (observed 2026-10-16: WinError 5). Readers hold it for
    # microseconds, so a short retry clears it. If it never clears, the
    # increment is dropped with a warning rather than crashing the run:
    # this count is only a backstop, and the provider's per-day 429
    # remains the authority.
    for _ in range(50):
        try:
            os.replace(temporary, path)
            return
        except PermissionError:
            time.sleep(0.02)

    os.remove(temporary)

    print(
        f"  WARNING: could not update {path.name}; one {provider} request "
        "went uncounted locally",
        file=sys.stderr,
    )


def _record_quota(response, model=None) -> None:
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

    path, _, _ = _budget("groq", model)

    state = _budget_state("groq", model)
    state["provider_remaining"] = remaining
    state["provider_reset"] = response.headers.get(
        "x-ratelimit-reset-requests", ""
    )

    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w", encoding="utf-8") as f:
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

    wait = _quoted_wait(response.text)

    return config.RATE_LIMIT_FALLBACK_WAIT if wait is None else wait


def _quoted_wait(text):
    """
    Seconds in "try again in 48m10.08s" / "1h2m3s" / "20.22s" / "250ms",
    or None. Groq quotes daily-window waits in minutes and hours, which a
    seconds-only pattern silently misread.
    """

    match = re.search(
        r"try again in ((?:[0-9.]+h)?(?:[0-9.]+m(?!s))?(?:[0-9.]+s)?(?:[0-9.]+ms)?)",
        text,
    )

    if not match or not match.group(1):
        return None

    seconds = 0.0

    for value, unit in re.findall(r"([0-9.]+)(ms|h|m|s)", match.group(1)):
        seconds += float(value) * {"h": 3600, "m": 60, "s": 1, "ms": 0.001}[unit]

    return seconds


def _groq_is_daily(response) -> bool:
    """True when a Groq 429 names a per-day limit (TPD or RPD)."""

    try:
        message = response.json().get("error", {}).get("message", "")
    except ValueError:
        message = response.text

    return "per day" in message.lower()


# Distinguishes "caller said nothing about reasoning effort" from
# "caller explicitly wants the parameter omitted". The report path relies
# on the first, the triage path on the second, and None cannot express
# both.
_EFFORT_UNSET = object()


def call_groq(prompt: str, max_tokens: int = None,
              reasoning_effort=_EFFORT_UNSET, model: str = None,
              json_mode: bool = False):
    """
    Send `prompt` to Groq and return (response_text, latency_ms).

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

    `model` defaults to config.GROQ_MODEL (the report model); the triage
    path passes config.TRIAGE_MODEL. `json_mode` asks for a JSON-only
    answer (response_format json_object), as the Gemini path does.

    HTTP 429 is retried up to config.RATE_LIMIT_MAX_RETRIES times,
    waiting as long as the server asks -- unless it names a per-day
    limit, which raises DailyBudgetExhausted carrying the quoted wait.
    500/502/503 are retried like Gemini's (config.SERVER_ERROR_*). Every
    other non-2xx status raises immediately -- a 401 or a 400 will not
    fix itself, and retrying it would waste the budget.

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

    model = model or config.GROQ_MODEL

    payload = {
        "model": model,
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

    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    # Two independent retry budgets. A run that waits out several rate
    # limits has not used up its tolerance for truncated reasoning, and
    # vice versa -- sharing one counter between them would let a burst
    # of 429s cause an unrelated alert to be abandoned.
    rate_limits = 0
    truncations = 0
    server_errors = 0

    while True:

        _charge_request("groq", model)

        start = time.time()

        response = requests.post(
            config.GROQ_API_URL,
            headers=headers,
            json=payload,
            timeout=120,
        )

        latency_ms = (time.time() - start) * 1000

        _record_quota(response, model)

        if response.status_code == 429 and _groq_is_daily(response):
            raise DailyBudgetExhausted(
                "Groq reports a per-day limit is used up. Completed "
                "verdicts are durable and the run resumes where it "
                f"stopped.\n{response.text[:800]}",
                retry_after=_quoted_wait(response.text),
            )

        if (response.status_code in (500, 502, 503)
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

            # HTTPError for the same reason as the Gemini side: the
            # driver's bounded API retry covers it, and both providers
            # must treat an answerless response the same way.
            raise requests.HTTPError(
                "Groq returned an empty response. "
                f"finish_reason={choice.get('finish_reason')}, "
                f"reasoning_chars={len(reasoning or '')}."
            )

        usage = body.get("usage", {})

        LAST_USAGE.clear()
        LAST_USAGE.update({
            "prompt_tokens": usage.get("prompt_tokens"),
            "output_tokens": usage.get("completion_tokens"),
            "reasoning_tokens": (usage.get("completion_tokens_details") or {}).get("reasoning_tokens"),
            "total_tokens": usage.get("total_tokens"),
        })

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


def call_gemini(prompt: str, max_tokens: int = None, model: str = None,
                json_mode: bool = True):
    """
    Send `prompt` to Gemini and return (response_text, latency_ms).

    Mirrors call_groq(): charged before sending, 429 retried as long as
    the server asks up to config.RATE_LIMIT_MAX_RETRIES, a per-day quota
    raises DailyBudgetExhausted, a response cut off at the token cap is
    retried config.TRUNCATION_MAX_RETRIES times and then raises. Nothing
    is ever defaulted or repaired.

    The thinking level is left at the model's default, as the Groq
    triage path leaves reasoning_effort unset.

    `model` defaults to config.TRIAGE_MODEL: Gemini is used for triage
    only. `json_mode` sets responseMimeType to application/json.
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

    model = model or config.TRIAGE_MODEL
    url = f"{config.GEMINI_API_BASE}{model}:generateContent"

    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": config.GEMINI_TEMPERATURE,
            "maxOutputTokens": (
                config.GEMINI_MAX_RESPONSE_TOKENS if max_tokens is None else max_tokens
            ),
        },
    }

    if json_mode:
        payload["generationConfig"]["responseMimeType"] = "application/json"

    rate_limits = 0
    truncations = 0
    server_errors = 0

    while True:

        _charge_request("gemini", model)

        start = time.time()

        response = requests.post(
            url,
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

        if (response.status_code in (500, 502, 503)
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
            # HTTPError, not RuntimeError, so the protocol driver's
            # bounded API retry covers it: an answerless 200 is no more
            # final than a truncated one, and it used to be the only
            # response shape that stopped a run on its first occurrence.
            # Nothing is defaulted -- if every attempt comes back empty
            # the run still halts.
            raise requests.HTTPError(
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
            raise requests.HTTPError(
                f"Gemini returned an empty response. finishReason={finish}."
            )

        usage = body.get("usageMetadata", {})

        LAST_USAGE.clear()
        LAST_USAGE.update({
            "prompt_tokens": usage.get("promptTokenCount"),
            "output_tokens": (usage.get("candidatesTokenCount") or 0) + (usage.get("thoughtsTokenCount") or 0),
            "reasoning_tokens": usage.get("thoughtsTokenCount"),
            "total_tokens": usage.get("totalTokenCount"),
        })

        return text, latency_ms


def triage_model_id() -> str:
    """The model the triage path calls, as recorded in every verdict row."""

    return config.TRIAGE_MODEL


def call_triage_llm(prompt: str):
    """
    The per-alert triage call, for every arm.

    The one place the triage provider is chosen. Arms differ only in the
    prompt they pass, never in how it is sent.
    """

    if config.TRIAGE_PROVIDER == "gemini":
        return call_gemini(
            prompt,
            max_tokens=config.max_response_tokens(config.TRIAGE_MODEL),
            model=config.TRIAGE_MODEL,
            json_mode=config.TRIAGE_JSON_MODE,
        )

    return call_groq(
        prompt,
        max_tokens=config.max_response_tokens(config.TRIAGE_MODEL),
        reasoning_effort=config.TRIAGE_REASONING_EFFORT,
        model=config.TRIAGE_MODEL,
        json_mode=config.TRIAGE_JSON_MODE,
    )
