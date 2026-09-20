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
