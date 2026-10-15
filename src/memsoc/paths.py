"""
Single source of truth for every path in MemSOC.

Before this module, paths were relative to the current working directory,
so the same command behaved differently depending on where you ran it.
Everything here is anchored to the repo root (two levels above this file),
so it resolves identically from any working directory, and every value can
be overridden by an environment variable, which is how the container points
at a bind-mounted dataset.

    MEMSOC_ROOT           repo root (default: two levels above this file)
    MEMSOC_DATA_DIR       dataset search root
    MEMSOC_DATASET_CSV    exact CSV path, skips discovery
    MEMSOC_MODELS_DIR     directory holding the .pkl files
    MEMSOC_ARTIFACTS_DIR  where generated logs and stream state are written
    MEMSOC_REPORTS_DIR    where generate_report.py writes reports
    MEMSOC_LOG_DIR        application log directory
    MEMSOC_API_HOST       default 127.0.0.1
    MEMSOC_API_PORT       default 8000
    MEMSOC_REPORT_PORT    default 8001

Importing from anywhere -- the package lives under src/, so src/ needs to
be on sys.path (the containers set PYTHONPATH=/app/src):

    from memsoc import paths

Run `python -m memsoc.paths` to print the resolved layout and what is missing.
"""

import os

# ---------------------------------------------------------------------
# Anchor
# ---------------------------------------------------------------------
# This file is src/memsoc/paths.py, so the repo root is two levels up.
_PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
_DEFAULT_ROOT = os.path.dirname(os.path.dirname(_PACKAGE_DIR))

ROOT = os.path.abspath(os.environ.get("MEMSOC_ROOT", _DEFAULT_ROOT))


def _env(name: str, default: str) -> str:
    """Environment override, resolved to an absolute path."""

    return os.path.abspath(os.environ.get(name, default))


# ---------------------------------------------------------------------
# Project tree
# ---------------------------------------------------------------------
SRC_DIR = os.path.join(ROOT, "src")
PACKAGE_DIR = os.path.join(SRC_DIR, "memsoc")

DETECTION_DIR = os.path.join(PACKAGE_DIR, "detection")
LOGSTREAM_DIR = os.path.join(PACKAGE_DIR, "logstream")
TRIAGE_DIR = os.path.join(PACKAGE_DIR, "triage")
MEMORY_DIR = os.path.join(PACKAGE_DIR, "memory")
API_DIR = os.path.join(PACKAGE_DIR, "api")

FEATURE_ENGINEERING = os.path.join(
    DETECTION_DIR, "features", "feature_engineering.py"
)

# ---------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------
# One copy, at the repo root. Previously three byte-identical copies lived
# under final_ml_model_v1/models/, final_ml_model_v1/src/models/ and
# Deployment/detection/final_ml_model_v1/src/models/.
MODELS_DIR = _env("MEMSOC_MODELS_DIR", os.path.join(ROOT, "models"))

BINARY_MODEL = os.path.join(MODELS_DIR, "binary_lightgbm.pkl")
MULTICLASS_MODEL = os.path.join(MODELS_DIR, "multiclass_lightgbm.pkl")

# ---------------------------------------------------------------------
# Dataset
# ---------------------------------------------------------------------
DATA_DIR = _env("MEMSOC_DATA_DIR", os.path.join(ROOT, "data"))

DATASET_NAME = "NF-UNSW-NB15-v3.csv"


def find_dataset(data_dir: str = None) -> str:
    """
    Locate NF-UNSW-NB15-v3.csv.

    The vendored copy sits under an opaque hash directory, and a
    bind-mounted copy in the container may sit anywhere under the mount
    point. Rather than hardcoding either, search the tree for the filename.

    Returns the expected default path if nothing is found, so callers can
    report a useful "missing" message instead of handling None.
    """

    override = os.environ.get("MEMSOC_DATASET_CSV")

    if override:
        return os.path.abspath(override)

    root = data_dir or DATA_DIR

    direct = os.path.join(root, DATASET_NAME)

    if os.path.exists(direct):
        return direct

    if os.path.isdir(root):
        for dirpath, _dirnames, filenames in os.walk(root):
            if DATASET_NAME in filenames:
                return os.path.join(dirpath, DATASET_NAME)

    return direct


DATASET_CSV = find_dataset()

# ---------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------
# Generated logs, ground truth, stream index and cursor. These used to be
# written next to the generation code, which mixed runtime output into the
# source tree; they now live in one artifacts/ directory that the container
# mounts as a volume.
ARTIFACTS_DIR = _env("MEMSOC_ARTIFACTS_DIR", os.path.join(ROOT, "artifacts"))

GENERATED_LOGS = os.path.join(ARTIFACTS_DIR, "generated_logs.jsonl")
GROUND_TRUTH = os.path.join(ARTIFACTS_DIR, "ground_truth.csv")

# The rows the frozen detector never trained on, as raw CSV row numbers, plus
# the manifest recording how they were derived and whether the derivation
# reproduced the published model fingerprint. Written by
# detection/training/heldout_split.py; read by the log generator so a replayed
# stream can be restricted to genuinely unseen flows. Distinct from
# STREAM_INDEX below, which is a replay cursor and means something else.
HELD_OUT_ROWS = os.path.join(ARTIFACTS_DIR, "heldout_rows.npy")
HELD_OUT_MANIFEST = os.path.join(ARTIFACTS_DIR, "heldout_manifest.json")

STREAM_INDEX = os.path.join(ARTIFACTS_DIR, "stream_index.npy")
STREAM_STATE = os.path.join(ARTIFACTS_DIR, "stream_state.json")
STREAM_LOG = os.path.join(ARTIFACTS_DIR, "stream_log.jsonl")
STREAM_GROUND_TRUTH = os.path.join(ARTIFACTS_DIR, "stream_ground_truth.csv")

API_SERVER_LOG = os.path.join(ARTIFACTS_DIR, "api_server.log")

# Layer 4 hand-off: live_capture.py appends here, generate_report.py reads it.
MODEL_OUTPUTS_DIR = _env(
    "MEMSOC_MODEL_OUTPUTS_DIR", os.path.join(ARTIFACTS_DIR, "model_outputs")
)
LIVE_RESULTS = os.path.join(MODEL_OUTPUTS_DIR, "live_results.jsonl")

# Phase 1 per-alert triage (Layer 4). triage_runner.py appends one verdict
# per alert here and reads it back on startup to skip alerts already
# triaged, which is what makes an interrupted run resume at no API cost.
# score_verdicts.py joins this file to GROUND_TRUTH after the run.
TRIAGE_VERDICTS = os.path.join(MODEL_OUTPUTS_DIR, "triage_verdicts.jsonl")

# The pinned stratified alert sample. Both arms must triage the identical
# set, so the chosen uids are written once and reused thereafter.
SAMPLE_MANIFEST = os.path.join(MODEL_OUTPUTS_DIR, "sample_manifest.json")

# Running count of API requests made today, so a run stops before the
# provider's daily cap rather than discovering it mid-experiment.
REQUEST_BUDGET = os.path.join(MODEL_OUTPUTS_DIR, "request_budget.json")

# The same count for the Gemini triage path. A separate file because the two
# providers have separate quotas, and one tally would let a Groq report run
# spend the Gemini allowance on paper, or the reverse.
GEMINI_REQUEST_BUDGET = os.path.join(MODEL_OUTPUTS_DIR, "request_budget_gemini.json")

# Layer 3, the memory layer: the on-disk ChromaDB store. Run-scoped, because
# a scored run must not inherit another run's cases -- carrying memory across
# runs makes run 2 a continuation rather than a repeat, which destroys both
# the variance range and the paired test (decisions.md C6/C7).
#
# The memory-layer docs previously specified data/memory/<run_id>/ in 13
# places. That was wrong -- the store is runtime output, CLAUDE.md requires
# all runtime output under artifacts/, and data/ is the gitignored dataset
# mount. The docs were corrected to match this in the same change (BL-101).
#
# A fresh store is a NEW DIRECTORY, never a cleared one. Nothing here deletes
# a store: the case store is a protected component.
MEMORY_STORE_DIR = _env(
    "MEMSOC_MEMORY_STORE_DIR", os.path.join(ARTIFACTS_DIR, "memory")
)


def memory_store(run_id):
    """
    The ChromaDB directory for one run.

    run_id is required and not defaulted. A default would let two runs
    share a store by accident, which is the one failure mode in this layer
    that produces plausible-looking results rather than an error.
    """

    if not run_id:
        raise ValueError(
            "run_id is required: a memory store is always scoped to one run"
        )

    return os.path.join(MEMORY_STORE_DIR, str(run_id))


# Per-run triage output for memory runs: this run's verdicts, kept apart from
# the Arm A file so runs never mix. Scoped like memory_store(), and for the
# same reason run_id is required.
RUNS_DIR = _env("MEMSOC_RUNS_DIR", os.path.join(ARTIFACTS_DIR, "runs"))


def run_dir(run_id):
    """The output directory for one triage run."""

    if not run_id:
        raise ValueError("run_id is required: run output is always scoped to one run")

    return os.path.join(RUNS_DIR, str(run_id))


# Charts saved by the analysis notebooks in notebooks/. Generated output,
# so under artifacts/ with everything else.
FIGURES_DIR = _env("MEMSOC_FIGURES_DIR", os.path.join(ARTIFACTS_DIR, "figures"))

# Generated security reports, served read-only by the report API.
REPORTS_DIR = _env("MEMSOC_REPORTS_DIR", os.path.join(ARTIFACTS_DIR, "reports"))

# Application logging.
LOG_DIR = _env("MEMSOC_LOG_DIR", os.path.join(ROOT, "logs"))

# ---------------------------------------------------------------------
# API
# ---------------------------------------------------------------------
# Host clients connect TO.
API_HOST = os.environ.get("MEMSOC_API_HOST", "127.0.0.1")

# Interface uvicorn binds ON. Differs from API_HOST in the container, where
# the server must listen on 0.0.0.0 for the published port to reach it but
# the in-container client still talks to 127.0.0.1.
API_BIND = os.environ.get("MEMSOC_API_BIND", API_HOST)

API_PORT = int(os.environ.get("MEMSOC_API_PORT", "8000"))

API_BASE = f"http://{API_HOST}:{API_PORT}"
API_URL = f"{API_BASE}/api/logs"
API_HEALTH = f"{API_BASE}/health"

# The report API is a second app in the same api/ package, on its own port.
REPORT_HOST = os.environ.get("MEMSOC_REPORT_HOST", API_HOST)
REPORT_PORT = int(os.environ.get("MEMSOC_REPORT_PORT", "8001"))

REPORT_BASE = f"http://{REPORT_HOST}:{REPORT_PORT}"
REPORT_HEALTH = f"{REPORT_BASE}/health"


# ---------------------------------------------------------------------
# Introspection
# ---------------------------------------------------------------------
def ensure_dirs() -> None:
    """Create the directories this project writes into."""

    for directory in (
        ARTIFACTS_DIR,
        MODEL_OUTPUTS_DIR,
        REPORTS_DIR,
        LOG_DIR,
    ):
        os.makedirs(directory, exist_ok=True)


def describe() -> str:

    entries = [
        ("ROOT", ROOT, True),
        ("DATA_DIR", DATA_DIR, True),
        ("DATASET_CSV", DATASET_CSV, True),
        ("MODELS_DIR", MODELS_DIR, True),
        ("BINARY_MODEL", BINARY_MODEL, True),
        ("MULTICLASS_MODEL", MULTICLASS_MODEL, True),
        ("FEATURE_ENGINEERING", FEATURE_ENGINEERING, True),
        ("ARTIFACTS_DIR", ARTIFACTS_DIR, False),
        ("GENERATED_LOGS", GENERATED_LOGS, False),
        ("HELD_OUT_ROWS", HELD_OUT_ROWS, True),
        ("HELD_OUT_MANIFEST", HELD_OUT_MANIFEST, True),
        ("MEMORY_STORE_DIR", MEMORY_STORE_DIR, False),
        ("MODEL_OUTPUTS_DIR", MODEL_OUTPUTS_DIR, False),
        ("TRIAGE_VERDICTS", TRIAGE_VERDICTS, False),
        ("REPORTS_DIR", REPORTS_DIR, False),
        ("RUNS_DIR", RUNS_DIR, False),
        ("FIGURES_DIR", FIGURES_DIR, False),
        ("LOG_DIR", LOG_DIR, False),
        ("API_BASE", API_BASE, False),
        ("REPORT_BASE", REPORT_BASE, False),
    ]

    lines = []

    for name, value, check in entries:
        if check:
            mark = "ok " if os.path.exists(value) else "MISSING"
        else:
            mark = "   "

        lines.append(f"  {mark}  {name:<20} {value}")

    return "\n".join(lines)


if __name__ == "__main__":
    print("\nMemSOC resolved paths\n")
    print(describe())
    print()
