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
# 2026-10-17: lowered to 1000 for qwen/qwen3.8-27b (GROQ_TRIAGE_MODEL),
# which answers the triage prompt without visible reasoning: a probe on
# the first stream alert used 1135 prompt + 122 completion tokens. 1000
# is 8x that answer, and leaves room for ~3 requests a minute under the
# same 8000 TPM. A truncated answer is still retried, never defaulted.
TRIAGE_MAX_RESPONSE_TOKENS = 1000

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
# 2026-10-17: 40 s for qwen/qwen3.8-27b at TRIAGE_MAX_RESPONSE_TOKENS =
# 1000, about 2,100-2,600 counted tokens a request. Sized so that TWO runs
# side by side on one key (Arm A and Arm B-self, sharing its 8000 TPM)
# send about 3 requests a minute between them.
TRIAGE_PACE_SECONDS = 40.0

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
# 2026-10-17: switched by the team to Groq, qwen/qwen3.8-27b, temperature
# 0 (BL-121) -- gemini-3.8-flash stayed unreachable and the free tier
# could not carry the run (BL-117). Gemini remains selectable. A
# comparison between arms is only valid when both ran under the same
# provider and model; every verdict row records model_id.
# ----------------------------------------------------------------------
TRIAGE_PROVIDER = "groq"

# The per-alert triage model on Groq. Separate from GROQ_MODEL, which the
# aggregate report path uses, so changing one never changes the other.
GROQ_TRIAGE_MODEL = "qwen/qwen3.8-27b"

# Which wording of the triage prompt produced a verdict. Written into
# every verdict row so that verdicts from different wordings can never be
# pooled into one comparison (BL-018, BL-106).
#
# Bump it whenever triage_prompt.render() output changes. The value is
# tied to a hash of the rendered Arm A prompt in
# tests/test_triage_memory.py, so a prompt edit without a bump fails the
# tests. "label-hypothesis" is the current framing: the detector's label
# is shown as a hypothesis the analyst may overrule (BL-018).
PROMPT_VARIANT = "label-hypothesis-v1"

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
# The decided model is the default. GEMINI_MODEL in the environment
# overrides it for one run -- used 2026-10-14, when every Flash model was
# returning 503 "high demand" and the run went to gemini-3.5-flash-lite
# (BL-117). The model actually called is recorded in every verdict row,
# so runs under different models can never be mistaken for each other.
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")
GEMINI_API_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    f"{GEMINI_MODEL}:generateContent"
)
GEMINI_TEMPERATURE = 0

# Gemini counts thinking tokens against maxOutputTokens, and does not
# reserve the cap against a per-minute token quota the way Groq does, so
# a generous cap costs nothing and avoids truncating mid-thought.
GEMINI_MAX_RESPONSE_TOKENS = 16384

# Measured 2026-10-15 from the provider's own 429 (BL-117): the free tier
# allows 500 generate requests per day PER MODEL
# (generate_content_free_tier_requests, gemini-3.5-flash-lite), and a
# per-minute limit that returned a handful of retryable 429s at three
# concurrent runs paced 6 s apart. Other models' limits are unmeasured.
# Gemini's per-day 429 stays the authority and stops every run cleanly.
# Arms are run side by side so that the stop leaves them all on the same
# prefix of the stream -- the purpose the Groq-era reserve served.
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
