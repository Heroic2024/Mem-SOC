"""
Single source of truth for every path in MemSOC.

Before this module, paths were relative to the current working directory,
so the same command behaved differently depending on where you ran it:
the API only found its models when started from final_ml_model_v1/src/,
log generation only found the dataset when started from log_generation/,
and logs landed in whichever directory happened to be current. Docker made
that worse, since the dataset lives outside the image entirely.

Everything here is anchored to this file's own location, so it resolves
identically from any working directory, and every value can be overridden
by an environment variable, which is how the container points at a
bind-mounted dataset.

    MEMSOC_ROOT           repo root (default: this file's directory)
    MEMSOC_DATA_DIR       dataset search root
    MEMSOC_DATASET_CSV    exact CSV path, skips discovery
    MEMSOC_MODELS_DIR     directory holding the .pkl files
    MEMSOC_ARTIFACTS_DIR  where generated logs and stream state are written
    MEMSOC_LOG_DIR        application log directory
    MEMSOC_API_HOST       default 127.0.0.1
    MEMSOC_API_PORT       default 8000

Importing from anywhere:

    import os, sys
    sys.path.insert(0, <repo root>)
    import paths

Run `python paths.py` to print the resolved layout and what is missing.
"""

import os

# ---------------------------------------------------------------------
# Anchor
# ---------------------------------------------------------------------
ROOT = os.path.abspath(os.environ.get(
    "MEMSOC_ROOT",
    os.path.dirname(os.path.abspath(__file__)),
))


def _env(name: str, default: str) -> str:
    """Environment override, resolved to an absolute path."""

    return os.path.abspath(os.environ.get(name, default))


# ---------------------------------------------------------------------
# Project tree
# ---------------------------------------------------------------------
ML_ROOT = os.path.join(ROOT, "final_ml_model_v1")
ML_SRC = os.path.join(ML_ROOT, "src")

LOGGEN_DIR = os.path.join(ROOT, "log_generation")

FEATURE_ENGINEERING = os.path.join(
    ML_SRC, "features", "feature_engineering.py"
)

# ---------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------
MODELS_DIR = _env("MEMSOC_MODELS_DIR", os.path.join(ML_SRC, "models"))

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

    The vendored copy sits under an opaque hash directory
    (f7546561558c07c5_NFV3DATA-A11964_A11964/data/), and a bind-mounted
    copy in the container may sit anywhere under the mount point. Rather
    than hardcoding either, search the tree for the filename.

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
# Generated logs, ground truth, stream index and cursor. Kept next to the
# generation code by default; redirected to a volume in the container.
ARTIFACTS_DIR = _env("MEMSOC_ARTIFACTS_DIR", LOGGEN_DIR)

GENERATED_LOGS = os.path.join(ARTIFACTS_DIR, "generated_logs.jsonl")
GROUND_TRUTH = os.path.join(ARTIFACTS_DIR, "ground_truth.csv")

STREAM_INDEX = os.path.join(ARTIFACTS_DIR, "stream_index.npy")
STREAM_STATE = os.path.join(ARTIFACTS_DIR, "stream_state.json")
STREAM_LOG = os.path.join(ARTIFACTS_DIR, "stream_log.jsonl")
STREAM_GROUND_TRUTH = os.path.join(ARTIFACTS_DIR, "stream_ground_truth.csv")

API_SERVER_LOG = os.path.join(ARTIFACTS_DIR, "api_server.log")

# Application logging. Was "logs" relative to CWD, which scattered log
# files across final_ml_model_v1/ and final_ml_model_v1/src/.
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


# ---------------------------------------------------------------------
# Introspection
# ---------------------------------------------------------------------
def ensure_dirs() -> None:
    """Create the directories this project writes into."""

    for directory in (ARTIFACTS_DIR, LOG_DIR):
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
        ("LOG_DIR", LOG_DIR, False),
        ("API_BASE", API_BASE, False),
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
