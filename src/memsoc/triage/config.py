"""
Configuration for the Stage 4 (Layer 4) report-generation pipeline.

Reads the Groq API key from the GROQ_API_KEY environment variable if it is
set; otherwise falls back to the placeholder below. The environment
variable always takes priority, so setting it is the safe way to supply a
real key without ever writing it into a file that could be committed.
"""

import os
from pathlib import Path

from memsoc import paths

# ----------------------------------------------------------------------
# Single placeholder for the API key. Do not commit a real key here --
# prefer setting the GROQ_API_KEY environment variable instead.
# ----------------------------------------------------------------------
GROQ_API_KEY_PLACEHOLDER = "YOUR_GROQ_API_KEY_HERE"

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", GROQ_API_KEY_PLACEHOLDER)
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"

# llama-3.1-8b-instant and llama-3.3-70b-versatile were both deprecated
# for free/developer-tier accounts on 2026-08-16. openai/gpt-oss-20b is
# Groq's documented replacement for llama-3.1-8b-instant.
# https://console.groq.com/docs/deprecations
GROQ_MODEL = "openai/gpt-oss-20b"
TEMPERATURE = 0

# The aggregate security report has several narrative sections, so it
# needs more headroom than a one-alert response did.
MAX_RESPONSE_TOKENS = 3000
GROQ_REASONING_EFFORT = "low"

# The existing, unmodified detection API from final_ml_model_v1.
DETECTION_API_URL = os.environ.get("DETECTION_API_URL", paths.API_URL)

# How many of the highest-risk findings to show the LLM in the prompt
# (keeps the prompt compact) versus how many to list in the report itself
# (the report can afford to be more complete -- that table is rendered
# directly from computed data, not written by the LLM).
FINDINGS_IN_PROMPT = 10
FINDINGS_IN_REPORT = 25

# ----------------------------------------------------------------------
# The hand-off point between live_capture.py and generate_report.py.
# live_capture.py appends the model's full response for every flow it
# processes to this file; generate_report.py only ever reads it. Neither
# script talks to the other directly -- this file is the entire
# interface between "run the model" and "generate the report."
# ----------------------------------------------------------------------
# Resolved by paths.py (MEMSOC_MODEL_OUTPUTS_DIR / MEMSOC_ARTIFACTS_DIR) so
# runtime output no longer lands inside the source tree.
MODEL_OUTPUTS_DIR = Path(paths.MODEL_OUTPUTS_DIR)
LIVE_RESULTS_PATH = Path(paths.LIVE_RESULTS)

# Default pacing for live_capture.py --loop mode (seconds between flows).
DEFAULT_CAPTURE_INTERVAL = 0.0

# Reports are generated repeatedly as capture progresses; only the most
# recent REPORTS_TO_KEEP survive on disk. Older report_*.json/.md pairs
# are deleted automatically by generate_report.py after each new one is
# written. This is an explicit, documented retention policy, not an
# incidental side effect.
REPORTS_TO_KEEP = 10

# ----------------------------------------------------------------------
# Phase 1 per-alert triage (Arm A -- the memoryless baseline).
#
# triage_runner.py appends one verdict per alert to VERDICTS_PATH and
# reads it back on startup to skip alerts already triaged, so a crashed
# or repeated run costs no additional API requests.
#
# GROUND_TRUTH_PATH is read ONLY by score_verdicts.py, after a run.
# Nothing on the triage path may open it -- ground-truth labels are the
# evaluation oracle (PROJECT_BRIEF.md section 5) and must never reach
# the prompt.
# ----------------------------------------------------------------------

# Headroom for one per-alert triage verdict.
#
# This is not a cosmetic setting. Groq counts prompt tokens plus the
# *requested* max_tokens against the tokens-per-minute quota, whatever
# the model actually returns, so an oversized reservation throttles
# throughput for nothing.
#
# It cannot simply be set to the size of the answer, either. gpt-oss-20b
# is a reasoning model and spends completion tokens thinking before it
# emits content -- caps of 500, 1500, 2500 and 4000 were all observed to
# truncate on at least one alert. C1424253008630-11300-119, a large HTTP
# flow with heavy retransmission, spent 3998 tokens reasoning without
# emitting content.
#
# 6000 is near the practical ceiling: the feature-rich prompt runs about
# 1200 tokens, and prompt + max_tokens must stay under the 8000 TPM
# quota or every request is rejected outright. That leaves roughly one
# request per minute.
#
# From 2026-10-16 the same cap applied to EVERY triage model, Gemini
# included (it was 16384 there), so no model was given more room to think
# than another. 6000 is the most Groq's 8000 TPM allows beside the
# largest memory-arm prompt (~1850 tokens), so it stays the default.
TRIAGE_MAX_RESPONSE_TOKENS = 6000

# Per-model override, read through max_response_tokens() below. Same
# shape as DAILY_REQUEST_LIMITS: a provider limit is a property of the
# model, not of the experiment, and one number cannot fit both.
#
# gemma-4-26b-a4b-it is here because 6000 stopped two protocol runs
# (BL-126). Measured over 666 Gemma verdicts: the median answer is 1084
# output tokens and 99% are under 5000, but the tail is close to the
# cap -- the highest answer that finished was 5944, and alert
# C1424232646440-35469-9087 spends 4399 tokens in Arm A alone, with no
# precedents in the prompt. On 2026-10-17 the same alert's oracle prompt
# returned 2087 tokens in the morning and then ran away past the cap on
# nine consecutive attempts in the afternoon, so the margin is not
# something a rerun can be relied on to clear.
#
# 16384 is not a new number: it is what Gemini models ran under before
# 2026-10-16. Gemma is served by AI Studio, whose free tier limits input
# tokens per minute rather than output, so the Groq TPM ceiling that
# fixes 6000 does not apply to it.
#
# This is a declared divergence between models and it is stated in the
# protocol document. Every arm of a given model shares that model's cap,
# so the A / B-self / B-oracle comparison is unaffected; what it
# qualifies is the comparison BETWEEN models.
TRIAGE_MAX_RESPONSE_TOKENS_BY_MODEL = {
    "gemma-4-26b-a4b-it": 16384,
}


def max_response_tokens(model: str) -> int:
    """The output cap for one model, falling back to the shared default."""

    return TRIAGE_MAX_RESPONSE_TOKENS_BY_MODEL.get(
        model, TRIAGE_MAX_RESPONSE_TOKENS
    )

# The triage path sends NO reasoning_effort parameter, which is what the
# 2026-08-30 baseline run did. The report path above sets "low"; adopting
# that here would change how hard the model thinks, which is part of what
# this experiment measures, and would make new verdicts incomparable with
# the 40 already recorded. None means the key is omitted from the payload.
TRIAGE_REASONING_EFFORT = None

# A response truncated mid-reasoning is retried this many times before
# the run stops. Retrying is not the same as skipping the alert: no
# verdict is ever fabricated or defaulted, and if every attempt
# truncates the run halts so the alert can be dealt with explicitly.
TRUNCATION_MAX_RETRIES = 2

# Bounded retry for HTTP 429. Groq's rate-limit response states how long
# to wait, so the retry honours that rather than guessing. Retries are
# capped: a persistent 429 means the budget is genuinely exhausted and
# the run should stop rather than spin.
RATE_LIMIT_MAX_RETRIES = 5
RATE_LIMIT_FALLBACK_WAIT = 20.0

# ----------------------------------------------------------------------
# Daily request budget.
#
# The Groq free tier allows 1000 requests per day, and a rate-limited
# (429) response still consumes one. Every HTTP call is counted, retries
# included, and the run stops before the cap rather than discovering it
# mid-experiment -- Arm B needs its share of the same day's budget, and
# an Arm A that eats the whole allowance leaves the comparison
# half-finished.
#
# The reserve is deliberate headroom: it leaves room to re-triage a
# handful of alerts without waiting for the quota to reset.
# ----------------------------------------------------------------------
DAILY_REQUEST_LIMIT = 1000
DAILY_REQUEST_RESERVE = 100

# Seconds to wait between triage calls.
#
# Pacing is cheaper than retrying. At roughly 7200 tokens per request
# against an 8000 tokens-per-minute quota, sending faster than one call
# per minute guarantees a 429 -- and a 429 costs a request from the
# daily budget while returning nothing. Measured over one run, retries
# cost 33 requests to obtain 14 verdicts.
#
# 60 since 2026-10-16: prompt + the 6000-token reservation is 7100-7850
# tokens, so one request a minute is all the 8000 TPM allows.
TRIAGE_PACE_SECONDS = 60.0

# Stratified subsample of the alerts, so a run fits in about an hour
# instead of three at the ~1 alert/minute the TPM quota allows.
#
# Capped per detector category rather than sampled uniformly: the rare
# categories are where the detector's category errors concentrate
# (Exploits->Fuzzers, Reconnaissance->Fuzzers), so uniform sampling
# would thin out exactly the alerts the primary metric depends on.
# Categories at or below the cap are taken whole.
SAMPLE_PER_CATEGORY = 12
SAMPLE_SEED = 20260830

# The raw flow stream. Read by triage_runner.py to join the 48 NetFlow
# v3 feature values onto each alert: live_results.jsonl carries only the
# detector's output and its SHAP attributions, and SHAP contributions
# without the underlying feature values are not something an analyst --
# human or model -- can reason from.
#
# Read-only, and for feature values only. This file carries no Label or
# Attack column, so joining it introduces no oracle.
STREAM_PATH = Path(paths.GENERATED_LOGS)

VERDICTS_PATH = Path(paths.TRIAGE_VERDICTS)

# The chosen uids are written here on first use and reused thereafter,
# so both arms are guaranteed the identical alert set even if the cap or
# seed is later changed. Delete it only to deliberately redefine the
# sample -- which invalidates comparison with any run that preceded it.
SAMPLE_MANIFEST_PATH = Path(paths.SAMPLE_MANIFEST)

REQUEST_BUDGET_PATH = Path(paths.REQUEST_BUDGET)

# The evaluation oracle. score_verdicts.py is the only reader.
GROUND_TRUTH_PATH = Path(paths.GROUND_TRUTH)

# ----------------------------------------------------------------------
# The per-alert triage LLM (both arms).
#
# decisions.md B5 (answered 2026-10-14): gemini-3.8-flash at temperature
# 0. The provider is chosen here, once, and triage_runner.py calls the
# same function for every arm -- the LLM is held constant by
# construction. The aggregate report path above stays on Groq.
#
# "groq" remains selectable so the 2026-08-30 pilot setup can still be
# reproduced, but a comparison between arms is only valid when both ran
# under the same provider and model.
#
# TRIAGE_PROVIDER and TRIAGE_MODEL in the environment select both for one
# run; protocol_run.py sets them from its --model flag, so testers never
# type a model id (docs/status/testing-protocol-v1.md).
# ----------------------------------------------------------------------
TRIAGE_PROVIDER = os.environ.get("TRIAGE_PROVIDER", "gemini")

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
# The decided model is the default. GEMINI_MODEL in the environment
# overrides it for one run -- used 2026-10-14, when every Flash model was
# returning 503 "high demand" and the run went to gemini-3.5-flash-lite
# (BL-117). The model actually called is recorded in every verdict row,
# so runs under different models can never be mistaken for each other.
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")
GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models/"
GEMINI_API_URL = f"{GEMINI_API_BASE}{GEMINI_MODEL}:generateContent"
GEMINI_TEMPERATURE = 0

# Kept for any non-triage Gemini use. The triage path uses
# TRIAGE_MAX_RESPONSE_TOKENS for every provider (below).
GEMINI_MAX_RESPONSE_TOKENS = 16384

# The model the triage path calls. Defaults to the provider's own setting,
# so a run that sets neither variable behaves exactly as before.
TRIAGE_MODEL = os.environ.get("TRIAGE_MODEL") or (
    GEMINI_MODEL if TRIAGE_PROVIDER == "gemini" else GROQ_MODEL
)

# Ask the provider for a JSON-only answer (Gemini responseMimeType, Groq
# response_format json_object). The same setting for every triage model,
# so no model gets help formatting that another does not.
TRIAGE_JSON_MODE = True

# ----------------------------------------------------------------------
# Free-tier requests per day, PER MODEL (BL-121). Read from AI Studio's
# rate-limit page and Groq's published limits on 2026-10-16. The client
# counts each model separately against its own line; the provider's 429
# stays the authority. Unlisted models get the most restrictive limit seen.
# ----------------------------------------------------------------------
DAILY_REQUEST_LIMITS = {
    "gemma-4-26b-a4b-it": 14400,
    "gemma-4-31b-it": 14400,
    "gemini-3.5-flash-lite": 500,
    "gemini-3.1-flash-lite": 500,
    "openai/gpt-oss-20b": 1000,
    "qwen/qwen3.8-27b": 1000,
}
DEFAULT_DAILY_REQUEST_LIMIT = 20

# Measured 2026-10-15 from the provider's own 429 (BL-117): the free tier
# allows 500 generate requests per day PER MODEL
# (generate_content_free_tier_requests, gemini-3.5-flash-lite), and a
# per-minute limit that returned a handful of retryable 429s at three
# concurrent runs paced 6 s apart. Measured 2026-10-16 the same way:
# gemini-3.8-flash allows only 20 requests per day on the free tier.
# Other models' limits are in DAILY_REQUEST_LIMITS above.
# Gemini's per-day 429 stays the authority and stops every run cleanly.
# Arms are run side by side so that the stop leaves them all on the same
# prefix of the stream -- the purpose the Groq-era reserve served.
#
# GEMINI_DAILY_REQUEST_LIMIT is no longer read by the client; each model's
# own line in DAILY_REQUEST_LIMITS is (BL-121). Kept as the record of the
# figure the 2026-10-15 run was budgeted under.
GEMINI_DAILY_REQUEST_LIMIT = 500
GEMINI_DAILY_REQUEST_RESERVE = 20
GEMINI_PACE_SECONDS = 6.0

GEMINI_REQUEST_BUDGET_PATH = Path(paths.GEMINI_REQUEST_BUDGET)

# Gemini answers 503 "model is currently experiencing high demand" during
# load spikes (observed 2026-10-14). Transient, so retried with a growing
# wait -- but bounded: a persistent 503 stops the run like any other
# error, and nothing is defaulted.
SERVER_ERROR_MAX_RETRIES = 6
SERVER_ERROR_BASE_WAIT = 15.0
