"""
Configuration for the Stage 4 (Layer 4) report-generation pipeline.

Reads the Groq API key from the GROQ_API_KEY environment variable if it is
set; otherwise falls back to the placeholder below. The environment
variable always takes priority, so setting it is the safe way to supply a
real key without ever writing it into a file that could be committed.
"""

import os
from pathlib import Path

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
MAX_RESPONSE_TOKENS = 4000

# Headroom for one per-alert triage verdict.
#
# This is not a cosmetic setting. Groq counts prompt tokens plus the
# *requested* max_tokens against the tokens-per-minute quota, whatever
# the model actually returns, so an oversized reservation throttles
# throughput for nothing: at the report's 4000 the 8000 TPM free tier
# allows about 1.7 alerts/minute.
#
# It cannot simply be set to the size of the answer, either. gpt-oss-20b
# is a reasoning model and spends completion tokens thinking before it
# emits content -- measured alerts used 755 and 1447+ reasoning tokens
# for a ~75 token verdict, and caps of 500 and 1500 both truncated
# mid-reasoning and returned empty content.
#
# Caps of 500, 1500, 2500 and 4000 were all observed to truncate on at
# least one alert -- C1424253008630-11300-119, a large HTTP flow with
# heavy retransmission, spent 3998 tokens reasoning without emitting
# content. Nothing is malformed about it; it is simply ambiguous enough
# to provoke extended deliberation.
#
# 6000 is near the practical ceiling: the feature-rich prompt runs about
# 1200 tokens, and prompt + max_tokens must stay under the 8000 TPM
# quota or every request is rejected outright. That leaves roughly one
# request per minute.
#
# Reasoning length varies between identical calls even at temperature 0,
# so a truncated response is retried before being treated as fatal --
# see RATE_LIMIT/TRUNCATION retries below.
#
# The alternative -- Groq's reasoning_effort parameter -- would be
# cheaper and far more predictable, but it changes how hard the model
# thinks, and how well the model reasons is part of what this experiment
# measures. Paying in wall-clock time rather than in altered model
# behaviour is the defensible trade: at roughly 1.5 alerts/minute a
# 194-alert arm takes a little over two hours.
TRIAGE_MAX_RESPONSE_TOKENS = 6000

# A response truncated mid-reasoning is retried this many times before
# the run stops. Retrying is not the same as skipping the alert: no
# verdict is ever fabricated or defaulted, and if every attempt
# truncates the run halts so the alert can be dealt with explicitly.
TRUNCATION_MAX_RETRIES = 2

# The raw flow stream. Read by triage_runner.py to join the 48 NetFlow
# v3 feature values onto each alert: live_results.jsonl carries only the
# detector's output and its SHAP attributions, and SHAP contributions
# without the underlying feature values are not something an analyst --
# human or model -- can reason from.
#
# Read-only, and for feature values only. This file carries no Label or
# Attack column, so joining it introduces no oracle; ground truth stays
# confined to score_verdicts.py.
STREAM_PATH = (
    Path(__file__).resolve().parents[1] / "log_generation" / "generated_logs.jsonl"
)

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
# (429) response still consumes one. Every HTTP call is counted here,
# retries included, and the run stops before the cap rather than
# discovering it mid-experiment -- Arm B needs its share of the same
# day's budget, and an Arm A that eats the whole allowance leaves the
# comparison half-finished.
#
# The reserve is deliberate headroom, not superstition: it leaves room
# to re-triage a handful of alerts without waiting for the quota to
# reset at UTC midnight.
# ----------------------------------------------------------------------
DAILY_REQUEST_LIMIT = 1000
DAILY_REQUEST_RESERVE = 100
# REQUEST_BUDGET_PATH is defined with the other Phase 1 paths below,
# once MODEL_OUTPUTS_DIR exists.

# Seconds to wait between triage calls.
#
# Pacing is cheaper than retrying. At roughly 7200 tokens per request
# against an 8000 tokens-per-minute quota, sending faster than one call
# per minute guarantees a 429 -- and a 429 costs a request from the
# daily budget while returning nothing. Measured over one run, retries
# cost 33 requests to obtain 14 verdicts. Waiting instead makes that
# closer to one request per verdict, at no extra wall-clock cost, since
# the quota forces the same pace either way.
TRIAGE_PACE_SECONDS = 55.0

# The existing, unmodified detection API from final_ml_model_v1.
DETECTION_API_URL = "http://127.0.0.1:8000/api/logs"

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
MODEL_OUTPUTS_DIR = Path(__file__).resolve().parent / "model_outputs"
LIVE_RESULTS_PATH = MODEL_OUTPUTS_DIR / "live_results.jsonl"

# Default pacing for live_capture.py --loop mode (seconds between flows).
DEFAULT_CAPTURE_INTERVAL = 0.0

# ----------------------------------------------------------------------
# Phase 1 per-alert triage (Arm A).
#
# triage_runner.py appends one verdict per alert to VERDICTS_PATH and
# reads it back on startup to skip alerts already triaged, so a crashed
# or repeated run costs no additional API requests.
#
# GROUND_TRUTH_PATH is read ONLY by score_verdicts.py, after a run.
# Nothing on the triage path may open it -- ground-truth labels are the
# evaluation oracle (PROJECT_BRIEF.md section 5) and must never reach the
# prompt.
# ----------------------------------------------------------------------
VERDICTS_PATH = MODEL_OUTPUTS_DIR / "triage_verdicts.jsonl"

# Stratified subsample of the 194 alerts, so a run fits in about an hour
# instead of three at the ~1 alert/minute the TPM quota allows.
#
# Capped per detector category rather than sampled uniformly: the rare
# categories are where the detector's 23 category errors concentrate
# (Exploits->Fuzzers, Reconnaissance->Fuzzers), so uniform sampling
# would thin out exactly the alerts the primary metric depends on.
# Categories at or below the cap are taken whole.
SAMPLE_PER_CATEGORY = 12
SAMPLE_SEED = 20260830

# The chosen uids are written here on first use and reused thereafter,
# so both arms are guaranteed the identical alert set even if the cap or
# seed is later changed. Delete it only to deliberately redefine the
# sample -- which invalidates comparison with any run that preceded it.
SAMPLE_MANIFEST_PATH = MODEL_OUTPUTS_DIR / "sample_manifest.json"

# Running count of API requests made today, against DAILY_REQUEST_LIMIT
# above. Resets automatically at UTC midnight.
REQUEST_BUDGET_PATH = MODEL_OUTPUTS_DIR / "request_budget.json"
GROUND_TRUTH_PATH = (
    Path(__file__).resolve().parents[1] / "log_generation" / "ground_truth.csv"
)

# Reports are generated repeatedly as capture progresses; only the most
# recent REPORTS_TO_KEEP survive on disk. Older report_*.json/.md pairs
# are deleted automatically by generate_report.py after each new one is
# written. This is an explicit, documented retention policy, not an
# incidental side effect.
REPORTS_TO_KEEP = 5
