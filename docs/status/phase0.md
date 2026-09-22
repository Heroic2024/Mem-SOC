# Work Summary — Log Generation → Inference Pipeline

Covers three pieces of work: a one-command pipeline runner, path centralization,
and Docker packaging.

---

## Verification status — read this first

| Piece | Status |
|---|---|
| Pipeline runner (`run_pipeline.py`) | **Verified** on the host, repeatedly |
| Test suite (`test_pipeline.py`) | **Verified** — 13/13 pass with the API up |
| Path centralization (`paths.py`) | **Verified** — runs correctly from any working directory |
| Docker image | **Built and fully verified once**, then the image was deleted |
| `docker-compose.yml` after the last fix | **NOT re-verified** — see below |

**What happened with Docker.** The image built and passed every check listed
under "Docker verification" below. To prove the Dockerfile worked from nothing, I
deleted the image and rebuilt from scratch. During that rebuild I found a real
defect in `docker-compose.yml` and fixed it — but the rebuild then stalled in
`pip install`, and I could not confirm the fix at runtime.

The stall is **not a Dockerfile problem**. A bare
`docker run python:3.13 pip download requests` — one small wheel, nothing to do
with this project — took over 300 seconds on this machine. Container networking
to PyPI is failing here, the same fault that made `deb.debian.org` unreachable
earlier. On a working network the build should complete normally.

So: **`docker compose build` needs to be run once and confirmed.** Steps are in
[`DOCKER.md`](./DOCKER.md).

---

## 1. One-command pipeline runner

**`src/memsoc/logstream/run_pipeline.py`** — replaced the three-terminal sequence
(generate → start API → replay) with a single command.

Four stages:

| Stage | Does |
|---|---|
| 0 Preflight | Checks both `.pkl` models and the dataset/log artifact exist, and fails with a named cause instead of a traceback |
| 1 Generate | Optional (`--regenerate`) |
| 2 Serve | Starts uvicorn, polls `/health` until the models load, tears it down in a `finally` |
| 3–4 Classify + report | Status codes, acceptance rate, mean/p95 latency, verdict and attack-category distributions |

It **reimplements nothing**. It imports `nfv3_log_generator`, `replay_to_api` and
`stream_to_api` and overrides their module-level config, so the 48-feature
contract and the seeded ordering keep exactly one definition. Like the scripts it
drives, it computes no metrics against ground truth — scoring belongs to the
frozen evaluation harness.

```powershell
python src\memsoc\logstream\run_pipeline.py --flows 500
python src\memsoc\logstream\run_pipeline.py --mode stream --flows 20 --delay 1.0
python src\memsoc\logstream\run_pipeline.py --no-api          # reuse a running API
python src\memsoc\logstream\run_pipeline.py --paths           # show resolved paths
```

### One behavioural fix

`MAX_FLOWS` in `stream_to_api.py` is a **lifetime** cap measured against the
resumable cursor, so `--flows 4` on a cursor already at 27 emitted nothing. I left
the stream's semantics alone — they are correct for a resumable cursor — and
offset it in the runner, so `--flows` means "emit this many now".

---

## 2. Test suite

**`tests/test_pipeline.py`** — stdlib `unittest`, no new dependencies,
13 tests in three self-skipping tiers.

| Tier | Needs | Guards |
|---|---|---|
| Schema (3) | nothing | `DROP_COLUMNS` still equals the list in `feature_engineering.py` — **parsed from that source file with `ast`, not copied**; 7 drops including `DNS_QUERY_ID`; 55 columns → 48 features |
| Artifact (6) | `generated_logs.jsonl` | All 48 features present and flat; **no `Label`/`Attack` leakage**; every value finite; uids unique; ground-truth sidecar joins 1:1 |
| Live (4) | a healthy API | Every record accepted 200; binary verdict present; attack rows carry multiclass + SHAP + alert; **negative control** — dropping one feature must return 400 |

The schema tier is the one that matters long-term: it fails if the model's
preprocessing changes and the generator silently drifts away from it — the
failure mode that would corrupt results without ever throwing.

---

## 3. Path centralization — `paths.py`

Every path now resolves through **`paths.py` at the repo root**. It anchors on its
own file location, not the working directory, so commands behave identically
wherever they run. Every value is overridable by environment variable, which is
how the container reaches a dataset that cannot live in the image.

| Variable | Default |
|---|---|
| `MEMSOC_ROOT` | the file's own directory |
| `MEMSOC_DATA_DIR` | `<root>/data` |
| `MEMSOC_DATASET_CSV` | discovered |
| `MEMSOC_MODELS_DIR` | `models` |
| `MEMSOC_ARTIFACTS_DIR` | `src/memsoc/logstream/` |
| `MEMSOC_LOG_DIR` | `<root>/logs` |
| `MEMSOC_API_HOST` / `MEMSOC_API_BIND` / `MEMSOC_API_PORT` | `127.0.0.1` / same / `8000` |

The dataset is **discovered, not hardcoded** — `find_dataset()` walks
`MEMSOC_DATA_DIR` for `NF-UNSW-NB15-v3.csv`, so the opaque
`f7546561558c07c5_NFV3DATA-A11964_A11964/` folder name is in no script, and a
bind mount can put the file at any depth.

### What this replaced

- `InferencePipeline.__init__` defaulted to `models/binary_lightgbm.pkl`,
  relative to the working directory — which is why the API only started from
  `src/memsoc/detection/`. **The `cd src` workaround is gone.**
- `logger.py` used `LOG_DIR = "logs"`, also relative — which is why log folders
  exist under both `src/memsoc/detection/` and `src/memsoc/detection/`.
- `nfv3_log_generator.py` reached the dataset via `..\data\...`, so it only ran
  from `src/memsoc/logstream/`.

### Files changed outside `src/memsoc/logstream/`

Flagged before editing, per `CLAUDE.md`:

- `src/memsoc/detection/inference/inference_pipeline.py` — **two default path
  arguments only**
- `src/memsoc/detection/utils/logger.py` — `LOG_DIR` only

**No model weights, thresholds, feature logic, prompt text, seeds, or metric
definitions were changed.**

---

## 4. Docker

- `Dockerfile` — image carries code + both pickles
- `docker-compose.yml` — six services, one shared volume
- `.dockerignore` — excludes the dataset, keeps the models
- `requirements-runtime.txt` — minimal pinned runtime deps

The CSV is bind-mounted read-only at `/data` since it cannot be committed.

Base image is `python:3.13`, **not `-slim`, on purpose**: it already ships
`libgomp1` (LightGBM's OpenMP runtime, without which the import fails) and `curl`
for the healthcheck. `-slim` needs an `apt-get` layer for both, and that step
failed on this machine's network.

`requirements-runtime.txt` is separate from `requirements/research-lock.txt`,
which is a 121-package UTF-16 `pip freeze` of the Jupyter research environment.
`CLAUDE.md` forbids modifying lockfiles, so it was left untouched. The runtime
list is pinned to the versions the models were validated against — joblib
unpickles LightGBM and scikit-learn objects, so version drift is a correctness
risk, not just a compatibility one.

### Defect found and fixed

Every compose service inherited `build:` from the YAML anchor, so
`docker compose build` built the same image **six times in parallel**. Now only
`pipeline` declares `build:`; the rest reuse `memsoc:latest`. Confirmed
structurally — build contexts went from 6 to 1 — but **not yet confirmed at
runtime**.

---

## Verification results

### Host

- Run from repo root: 20/20 HTTP 200
- Run from `src/memsoc/logstream/`: 60/60 HTTP 200, mean 28.8 ms / p95 114.5 ms
- Full suite with API up: **13/13 pass**
- Suite from an unrelated working directory: 9 pass, live tier skips correctly
- API loads from `src/memsoc/detection/` with no `cd src`

### Docker (before the image was deleted)

- `paths` — dataset discovered under the mounted hash folder
- `generate` — fresh volume, 5,000 records written from the mounted CSV, 10/10 classified
- `pipeline` — 20/20 HTTP 200
- `tests` — 3 pass / 2 skip on an empty volume, then 9 pass once populated
- `api` — healthcheck green in 7s, driven from the host with `--no-api`, 15/15
- **Cross-platform determinism: container uids byte-identical to host uids**
  (`C1424244486534-39220-1`, …) — the seeded order survives the OS change

That last one matters for the experiment: the alert stream is reproducible across
platforms, which `CLAUDE.md` requires.

---

## Known issues — reported, not fixed

- **`docker compose build` is unverified since the compose fix.** Run it once.
- **Container networking to PyPI is failing on this machine.** Not project code;
  affects any Docker build here.
- `generated_logs.jsonl` (6.9 MB) and `stream_index.npy` (18 MB) are not covered
  by `.gitignore`. **I did not modify `.gitignore`** — `CLAUDE.md` forbids it as a
  side effect of a feature task. Your own edit removed `*.pkl`, so
  `multiclass_lightgbm.pkl` (35 MB) will now commit — under GitHub's 100 MB limit
  but past its 50 MB warning.
- `stream_log.jsonl` grows without bound on a long soak. No rotation.
- Remaining working-directory-relative paths in `main.py`, `test_api.py`,
  `test_inference.py`, `train_*.py`, `test_external_*.py`, and
  `shap_explainer.py`'s default argument. All are training or offline-test
  scripts, none on the serving path — `SHAPExplainer` receives its path
  explicitly from the pipeline (`inference_pipeline.py:104`), so its default is
  dead code there.
- `test_api.py` and `test_inference.py` point at `data/raw/NF-UNSW-NB15-v3.csv`,
  which is not the real on-disk path.
- The inference pipeline's validation layer rejects `NaN` even though LightGBM
  handles it natively. This is why 5.18% of the dataset is excluded from log
  generation — the rejection comes from validation, not the model.

---

## Files

### New

| File | Role |
|---|---|
| `paths.py` | Single source of truth for every path |
| `DOCKER.md` | Build, run and test instructions |
| `SUMMARY.md` | This file |
| `Dockerfile` | Image definition |
| `docker-compose.yml` | Service and volume wiring |
| `.dockerignore` | Build context exclusions |
| `requirements-runtime.txt` | Minimal pinned runtime deps |
| `src/memsoc/logstream/run_pipeline.py` | Pipeline entry point |
| `tests/test_pipeline.py` | Contract tests |

### Modified

| File | Change |
|---|---|
| `src/memsoc/logstream/nfv3_log_generator.py` | Paths from `paths.py` |
| `src/memsoc/logstream/replay_to_api.py` | Paths from `paths.py` |
| `src/memsoc/logstream/stream_to_api.py` | Paths from `paths.py` |
| `src/memsoc/logstream/README.md` | Runner, tests, paths and Docker sections |
| `README.md` | Pointer to `DOCKER.md` |
| `src/memsoc/detection/inference/inference_pipeline.py` | Two default path arguments |
| `src/memsoc/detection/utils/logger.py` | `LOG_DIR` |

### Not modified

`.gitignore`, `requirements/research-lock.txt`, model weights, thresholds,
prompt templates, seeds, the evaluation harness, and metric definitions.
