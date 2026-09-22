"""
Configuration for the memory-layer case-ranking/compaction component.

Input is the live-results hand-off file -- the model's own captured
output (written by memsoc.triage.live_capture), never the raw log
stream (artifacts/generated_logs.jsonl). This component is an
independent second reader of that same hand-off file; it does not
modify memsoc.triage in any way.
"""

import os
from pathlib import Path

from memsoc import paths

LIVE_RESULTS_PATH = Path(paths.LIVE_RESULTS)

OUTPUT_DIR = Path(
    os.environ.get(
        "MEMSOC_CASE_RANKER_DIR",
        os.path.join(paths.ARTIFACTS_DIR, "case_ranker"),
    )
)

# Matches sentence-transformers/all-MiniLM-L6-v2's max sequence length
# (docs/memory-layer/05-configuration.md) -- the candidate embedding
# model named for the memory layer. This is the hard cap this
# component enforces on its own output.
TOKEN_BUDGET = 256

# A real WordPiece tokenizer reserves a couple of positions for
# [CLS]/[SEP] special tokens, and estimate_tokens() is a heuristic, not
# an exact count (see token_estimator.py) -- so pack to a slightly
# smaller effective budget rather than the nominal cap exactly.
SAFETY_MARGIN = 4

# How many SHAP features to include per selected case.
SHAP_TOP_K = 3
