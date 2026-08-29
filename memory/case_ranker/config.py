"""
Configuration for the memory-layer case-ranking/compaction component.

Input is LLMTriage/model_outputs/live_results.jsonl -- the model's own
captured output (written by LLMTriage/live_capture.py), never the raw
log stream (log_generation/generated_logs.jsonl). This component is an
independent second reader of that same hand-off file; it does not
modify LLMTriage/ in any way.
"""

from pathlib import Path

# memory/case_ranker/config.py -> memory/case_ranker -> memory -> Mem-SOC
REPO_ROOT = Path(__file__).resolve().parents[2]

LIVE_RESULTS_PATH = REPO_ROOT / "LLMTriage" / "model_outputs" / "live_results.jsonl"

OUTPUT_DIR = Path(__file__).resolve().parent / "outputs"

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
