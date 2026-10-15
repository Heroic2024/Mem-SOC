# Log Generation

Turns NetFlow v3 datasets into replayable network-flow logs for MemSOC.

There are **two paths** in this directory:

| Path | Dataset | Output | Status |
|---|---|---|---|
| **NF-UNSW-NB15 → 48 features** | NF-UNSW-NB15-v3 | 48-feature JSONL the inference API accepts | **Current** |
| CICIDS → Zeek `conn.log` | NF-CICIDS2018-v3 | 15-field Zeek-style JSONL | Legacy |

The current path runs in two modes, sharing one seed and one feature contract:

- **Batch** — `nfv3_log_generator.py` + `replay_to_api.py`: a fixed-size, fully reproducible
  sample written to disk, then replayed. Use for controlled runs.
- **Continuous** — `stream_to_api.py`: a never-ending sensor-style stream, resumable across
  restarts. Use for live demos.

They are independent. The current path is the one that feeds
`src/memsoc/detection`; the legacy path predates the detector integration and is
kept for reference. Do not mix their outputs — the field sets differ and
`log_to_jsonl.py` will reject 48-feature input.

---

# Current path — NF-UNSW-NB15 → 48 features

## Pipeline

```
   NF-UNSW-NB15-v3.csv
   55 columns, 2,365,424 rows
            |
            |  drop non-finite rows
            |  seeded selection (SEED)
            |  seeded shuffle
            v   nfv3_log_generator.py
   generated_logs.jsonl        ground_truth.csv
   envelope + 48 features      uid,label,attack
            |                        |
            |                        +--> evaluation oracle,
            |                             joined back on uid
            v   replay_to_api.py
      POST /api/logs
            |
            v
   FastAPI -> InferencePipeline
   binary -> multiclass -> SHAP -> alert
```

## The 48 features

`NF-UNSW-NB15-v3.csv` has **55** columns.
`src/memsoc/detection/features/feature_engineering.py` drops **7** of them,
leaving exactly 48 model inputs.

| Dropped column | Why |
|---|---|
| `Label` | Target — ground truth |
| `Attack` | Target — ground truth |
| `IPV4_SRC_ADDR` | Identifier, not a feature |
| `IPV4_DST_ADDR` | Identifier, not a feature |
| `FLOW_START_MILLISECONDS` | Timestamp, not a feature |
| `FLOW_END_MILLISECONDS` | Timestamp, not a feature |
| `DNS_QUERY_ID` | **Easy to miss** — sits between `ICMP_IPV4_TYPE` and `DNS_QUERY_TYPE` and reads like a feature, but it is a per-query identifier |

55 − 7 = 48. That is **2 targets + 5 metadata columns**. The generator asserts
this count at startup and refuses to run if the dataset schema changes.

## Record shape

Each line of `generated_logs.jsonl` is one JSON object with **55 keys**:
a 7-field Zeek-style envelope followed by the 48 model features, all flat at
top level.

```json
{
  "uid": "C1424244486534-39220-1",
  "ts": 1424244486.534,
  "id.orig_h": "59.166.0.4",
  "id.orig_p": 39220,
  "id.resp_h": "149.171.126.6",
  "id.resp_p": 21,
  "proto": "tcp",

  "L4_SRC_PORT": 39220,
  "L4_DST_PORT": 21,
  "PROTOCOL": 6,
  "...": "... 45 more model features ..."
}
```

**The envelope is safe to include.** `validate_input()` in
`inference_pipeline.py` only checks that no required feature is *missing*, and
`prepare_dataframe()` selects strictly by the model's own feature names. Extra
keys are ignored by the model, so the log can carry realistic identifiers
without contaminating inference.

**The 48 features must stay flat at top level** — not nested under a sub-object.
That is where `validate_input()` looks for them.

### `uid` format

`C{FLOW_START_MILLISECONDS}-{L4_SRC_PORT}-{sequence}`

The separators matter. The legacy path concatenated milliseconds and port with
no delimiter, so timestamp `…705` + port `53` and timestamp `…70` + port `553`
produce the same string. The sequence suffix makes uniqueness structural rather
than incidental.

## Determinism and randomization

The stream is **randomized in order but fully reproducible**.

- `SEED = 42` drives both the row selection (`numpy.default_rng`) and the final
  shuffle (`DataFrame.sample(random_state=SEED)`).
- The same seed always produces byte-identical `generated_logs.jsonl` and
  `ground_truth.csv`. Verified by running twice and diffing.
- **Feature values are never perturbed.** Every record is a real dataset row.
  Jittering values would sever the row from its ground-truth label and
  invalidate any later evaluation.

This satisfies the "deterministic and reproducible alert stream" constraint in
`CLAUDE.md` while still presenting the detector with an unpredictable ordering
rather than the dataset's natural attack-clustered sequence.

To change the sample, edit `SEED` or `SAMPLE_SIZE` at the top of
`nfv3_log_generator.py` — and record the values used, since they define the run.

## Ground truth is held out

`Label` and `Attack` are written to `ground_truth.csv`, never into
`generated_logs.jsonl`.

A real sensor cannot know in advance whether a flow is malicious; it records
only what it observes. Embedding the answer in the model's input would leak
ground truth and inflate results. `PROJECT_BRIEF.md` §5 holds these labels as
the **evaluation oracle only** — they score verdicts after the fact, joined
back on `uid`.

> The separate open question in §5 — whether ground-truth labels may also feed
> the memory store as confirmed verdicts — is **not** decided by this module and
> remains open.

## Known caveat — 5.18% of the dataset is excluded

122,493 of 2,365,424 rows (**5.18%**) carry non-finite values in two features:

| Column | `NaN` | `inf` |
|---|---|---|
| `SRC_TO_DST_SECOND_BYTES` | 63,425 | 59,068 |
| `DST_TO_SRC_SECOND_BYTES` | — | 122,493 |

`prepare_dataframe()` in the inference pipeline coerces features with
`pd.to_numeric(errors="coerce")` and raises `ValueError` on any resulting
`NaN`, which the API surfaces as **HTTP 400**. So these rows are rejected by
the deployed detector.

The generator therefore filters them out **before** sampling and reports the
excluded count on every run, rather than emitting records that would fail
mid-replay.

**What this means:** the generated stream is drawn from the 94.82% of flows
the pipeline can currently process, not from the whole dataset. Whether the
detector *should* reject these flows is a question for the pipeline, not for
log generation — LightGBM handles `NaN` natively, so the rejection comes from
the validation layer rather than the model. Flagged here; not worked around by
altering any value.

## Usage — one command

`run_pipeline.py` is the demo entry point. It runs preflight, starts the API
with the correct working directory, waits for the models to load, replays the
flows, prints a summary, and shuts the API down again.

```powershell
python run_pipeline.py                  # 100 flows, batch
python run_pipeline.py --flows 500
python run_pipeline.py --mode stream --flows 20 --delay 1.0
python run_pipeline.py --regenerate --sample-size 5000
python run_pipeline.py --no-api         # reuse an API you started yourself
```

| Flag | Default | Meaning |
|---|---|---|
| `--mode` | `batch` | `batch` replays `generated_logs.jsonl`; `stream` emulates a live sensor |
| `--flows` | `100` | Flows to classify (batch) or emit this run (stream) |
| `--unbounded` | off | Stream mode: run until Ctrl+C |
| `--regenerate` | off | Rebuild `generated_logs.jsonl` from the CSV (slow — two full scans) |
| `--sample-size` | `5000` | Records to write when regenerating |
| `--delay` | `0` | Seconds between requests (batch); flow interval (stream) |
| `--no-api` | off | Do not start uvicorn; require one already healthy |

The runner **does not reimplement any stage**. It imports `nfv3_log_generator`,
`replay_to_api` and `stream_to_api` and overrides their module-level config, so
the 48-feature contract and the seeded ordering keep exactly one definition. Like
the scripts it drives, it never scores against ground truth.

If an API is already healthy on port 8000 it is reused and left running;
otherwise the runner owns the process and stops it on exit. uvicorn output goes
to `api_server.log`, not the console.

Sample output:

```
  Accepted   25/25 (100.0%)
  Latency    mean   34.0 ms   p95  111.1 ms

  Verdict distribution
    Benign             23  ##########################..
    Attack              2  ##..........................

  Attack categories
    Exploits            2  ############################

  RESULT: PIPELINE OK -- every flow classified
```

One note on stream mode: `MAX_FLOWS` inside `stream_to_api.py` is a **lifetime**
cap measured against the resumable cursor, so setting it to 20 on a cursor that
has already emitted 27 flows does nothing. `--flows` in the runner means "emit
this many now" and is offset by the cursor automatically.

### Running the stages by hand

```powershell
# 1. Generate the log stream + ground truth sidecar
python nfv3_log_generator.py

# 2. Start the API -- from src/memsoc/detection/, any working directory works
cd ..
$env:PYTHONPATH = "$PWD;$PWD\.."
python -m uvicorn src.api.server:app

# 3. Replay the stream into the API
python ..\src\memsoc\logstream\replay_to_api.py
```

> **This used to require `cd src`.** `InferencePipeline.__init__` defaulted to
> `models/binary_lightgbm.pkl` — a path relative to the current directory — so
> the API only found its models when started from `src/memsoc/detection/`, and
> `logger.py` wrote its `logs/` directory wherever the process happened to
> start. Both now resolve through `paths.py`, so the working directory no
> longer changes behaviour. `PYTHONPATH` still needs `src/memsoc/detection/` for
> the `src.api.server` import and the repo root for `paths`.

Set `LIMIT` in `replay_to_api.py` to an integer for a short smoke run before
replaying all 5,000 records.

`replay_to_api.py` reports HTTP status and the verdict returned per record. It
deliberately **does not compute accuracy or any metric** — scoring predictions
against `ground_truth.csv` belongs to the evaluation harness, which is frozen
per `CLAUDE.md`. This script proves acceptance only.

---

## Continuous streaming — `stream_to_api.py`

The two scripts above are **batch**: generate a fixed sample, replay it, exit. For a live SOC
demo you want a sensor that never stops. `stream_to_api.py` is one long-running process that
emits a flow every `FLOW_INTERVAL` seconds, POSTs it, and keeps going indefinitely.

```
NF-UNSW-NB15-v3.csv
        |
        |  stream_index.npy   (byte offset of every eligible row)
        |  seeded permutation (SEED)
        |  stream_state.json  (cursor)
        v
   one flow per interval  ->  POST /api/logs  ->  verdict printed
        |
        +--> stream_log.jsonl           (append-only, what was emitted)
        +--> stream_ground_truth.csv    (append-only, uid,label,attack)
```

### The index cache

A live stream needs the *next* flow in shuffled order without rescanning a 2.36M-row CSV each
time. On first run the script scans the file once, records the byte offset of every eligible row,
and saves them to `stream_index.npy` (~18MB). After that, fetching any flow is a `seek()` plus a
`readline()` — constant time, flat memory.

**The first run takes a few minutes** while the index builds. Every run afterwards starts in about
a second. Delete `stream_index.npy` to force a rebuild.

**NOTE: if you change the dataset `stream_index.py` will fail, a new one needs to be made.**

The index applies the same finiteness rule as the batch generator and lands on the same
2,242,931 eligible rows, via an independent implementation.

### Determinism and resume

The emission order is **derived, never stored**:

```python
order = np.random.default_rng(SEED).permutation(len(index))
```

Same `SEED` ⇒ same sequence, always. `stream_state.json` only records how far along that fixed
sequence the stream has walked:

```json
{ "seed": 42, "position": 1487, "emitted": 1487, "wraps": 0 }
```

- **Resume:** just run it again — it picks up at the saved position.
- **Restart clean:** delete `stream_state.json`.
- **Seed guard:** if `stream_state.json` was written under a different `SEED`, the script refuses
  to start rather than silently splicing two different sequences together.
- **Wrap:** on reaching the end of the eligible pool it returns to position 0, increments `wraps`,
  and continues. The stream never dies.

`seq` is a lifetime counter, so `uid` (`C{ms}-{port}-{seq}`) stays unique across restarts and
wraps.

### Config

| Constant | Default | Purpose |
|---|---|---|
| `FLOW_INTERVAL` | `1.0` | Seconds between flows. `0` for maximum rate. |
| `MAX_FLOWS` | `None` | Stop after N flows. Leave `None` to run until Ctrl+C. |
| `API_URL` | `http://127.0.0.1:8000/api/logs` | Target endpoint |
| `INDEX_FILE` | `stream_index.npy` | Byte-offset cache |
| `STATE_FILE` | `stream_state.json` | Cursor |
| `STREAM_LOG` | `stream_log.jsonl` | Append-only emitted records |
| `STREAM_GROUND_TRUTH` | `stream_ground_truth.csv` | Append-only oracle |

`SEED` is inherited from `nfv3_log_generator.py` — both modes share one seed.

### Running

```powershell
# Start the API first (see "Running the stages by hand" above)
python stream_to_api.py
```

Output is one line per flow:

```
[35] uid=C1424241966327-6011-35 HTTP 200 -> Benign (1.000)
[36] uid=C1424223489736-31904-36 HTTP 200 -> Attack/Fuzzers (0.592) +shap+alert
```

Ctrl+C stops it cleanly: state is saved and a summary prints (flows emitted, position, wraps,
status-code counts, benign/attack split). Rerun to continue.

### Behaviour worth knowing

- **The API going down does not kill the stream.** Connection failures are logged and counted as
  `error`, and the loop continues. Restart the API and flows resume returning 200. Verified by
  stopping the server mid-run.
- **`stream_log.jsonl` grows without bound.** There is no rotation. On a long soak, truncate it
  yourself or point `STREAM_LOG` somewhere disposable.
- Attacks are ~4.2% of the stream, so short runs are often all benign. Run 50+ flows to reliably
  see the attack path with SHAP and alert.

---

## Paths — one source of truth

Every path in the project resolves through **`paths.py` at the repo root**. It
anchors on its own file location, not the working directory, so the same
command behaves identically wherever you run it.

```powershell
python paths.py                      # print the resolved layout + what is missing
python src\memsoc\logstream\run_pipeline.py --paths    # same, via the runner
```

```
  ok   ROOT                 C:\Users\...\Mem-SOC
  ok   DATASET_CSV          C:\...\f7546561558c07c5_NFV3DATA-A11964_A11964\data\NF-UNSW-NB15-v3.csv
  ok   BINARY_MODEL         C:\...\models\binary_lightgbm.pkl
       ARTIFACTS_DIR        C:\...\artifacts
```

Every value is overridable by environment variable — which is how the container
points at a dataset that cannot live in the image:

| Variable | Default | Purpose |
|---|---|---|
| `MEMSOC_ROOT` | this file's directory | Repo root |
| `MEMSOC_DATA_DIR` | `<root>/data` | Dataset search root |
| `MEMSOC_DATASET_CSV` | discovered | Exact CSV path, skips discovery |
| `MEMSOC_MODELS_DIR` | `models` | `.pkl` location |
| `MEMSOC_ARTIFACTS_DIR` | `src/memsoc/logstream/` | Generated logs, ground truth, stream index + cursor |
| `MEMSOC_LOG_DIR` | `<root>/logs` | Application logs |
| `MEMSOC_API_HOST` / `MEMSOC_API_BIND` / `MEMSOC_API_PORT` | `127.0.0.1` / same / `8000` | Connect address vs. bind interface |

The dataset is **discovered, not hardcoded** — `find_dataset()` walks
`MEMSOC_DATA_DIR` looking for `NF-UNSW-NB15-v3.csv`, so the opaque
`f7546561558c07c5_NFV3DATA-A11964_A11964/` directory name is not baked into any
script, and a bind mount can place the file at any depth.

### What this replaced

- `InferencePipeline.__init__` defaulted to `models/binary_lightgbm.pkl`,
  relative to the CWD, so the API only started from `src/memsoc/detection/`.
- `logger.py` used `LOG_DIR = "logs"`, also CWD-relative, which is why log
  directories appeared under both `src/memsoc/detection/` and
  `src/memsoc/detection/`.
- `nfv3_log_generator.py` reached the dataset via `..\data\...`, so it only ran
  from `src/memsoc/logstream/`.

All three now read from `paths.py`. Two files outside `src/memsoc/logstream/` were
touched to do it — `src/inference/inference_pipeline.py` (two default path
arguments) and `src/utils/logger.py` (`LOG_DIR`). **No model weights,
thresholds, feature logic, or prompt text were changed.**

---

## Docker

The image carries the code and both LightGBM pickles. It does **not** carry the
NF-UNSW-NB15-v3 CSV — that is multi-GB and cannot be committed, so it is
bind-mounted read-only at `/data` and located by discovery.

**Step-by-step instructions are in [`DOCKER.md`](../DOCKER.md).**
What follows is the design reference behind them.

### Layout

| Container path | What | Backed by |
|---|---|---|
| `/app` | Code + model pickles | The image |
| `/data` | NF-UNSW-NB15-v3 CSV | Bind mount, read-only |
| `/artifacts` | Generated logs, ground truth, 18MB stream index, stream cursor | Named volume `memsoc-artifacts` |
| `/app/logs` | Application logs | Container filesystem |

The artifacts volume is what makes the stream resumable across container
restarts — the seeded cursor in `stream_state.json` survives, so
`docker compose run --rm stream` twice continues the same sequence rather than
replaying it.

### Notes

- Base image is `python:3.13` rather than `-slim` **on purpose**: it already
  ships `libgomp1` (LightGBM's OpenMP runtime, without which the import fails)
  and `curl` for the healthcheck. `-slim` needs an `apt-get` layer for both,
  which is the one build step that depends on reaching `deb.debian.org`.
- `requirements-runtime.txt` is separate from
  `requirements/research-lock.txt`, which is a 121-package UTF-16 `pip
  freeze` of the Jupyter research environment. That file is left untouched;
  the runtime list is the minimal set actually imported, pinned to the versions
  the models were validated against — joblib unpickles LightGBM and
  scikit-learn objects, so version drift here is a correctness risk.
- The `api` service publishes port 8000 and declares a healthcheck with a 90s
  start period, since loading the 35MB multiclass model takes ~10s.
- Host and container share nothing but the mounts, so you can run
  `docker compose up api` and drive it from the host with
  `python src\memsoc\logstream\run_pipeline.py --no-api`.

---

## Tests

```powershell
python -m unittest test_pipeline -v
```

Stdlib `unittest`, no new dependencies. Three tiers, each skipping cleanly when
its input is missing — so the suite runs on a fresh clone and is complete on a
fully set-up machine.

| Tier | Needs | Guards |
|---|---|---|
| Schema | nothing | `DROP_COLUMNS` still equals the list in `feature_engineering.py` — **parsed from that source file, not copied**; 7 drops including `DNS_QUERY_ID`; 55 columns → 48 features |
| Artifact | `generated_logs.jsonl` | All 48 features present and flat at top level; **no `Label`/`Attack` leakage**; every value finite; uids unique; ground-truth sidecar joins 1:1 |
| Live | a healthy API | Every record accepted with 200; response carries a binary verdict; attack rows carry multiclass + SHAP + alert; **negative control** — dropping one feature must return 400 |

The schema tier is the one that matters long-term. It fails if the model's
preprocessing changes and the generator silently drifts away from it — the
failure mode that would corrupt results without ever throwing.

The live tier skips unless something is healthy on port 8000, so run
`run_pipeline.py --no-api` against a server you started by hand, or start one
first, to exercise it.

## Files

| File | Role |
|---|---|
| `run_pipeline.py` | **Entry point.** Orchestrates generate → serve → classify → report |
| `nfv3_log_generator.py` | NF-UNSW-NB15-v3 CSV → `generated_logs.jsonl` + `ground_truth.csv` |
| `replay_to_api.py` | `generated_logs.jsonl` → `POST /api/logs`, reports status and verdict |
| `stream_to_api.py` | Continuous sensor-style stream → `POST /api/logs`, resumable |
| `test_pipeline.py` | Contract tests — schema, artifact, live acceptance |

Repo-root files this directory depends on:

| File | Role |
|---|---|
| `paths.py` | **Single source of truth for every path.** Env-overridable |
| `Dockerfile` | Image: code + model pickles, dataset bind-mounted |
| `docker-compose.yml` | Service definitions and volume wiring |
| `requirements-runtime.txt` | Minimal pinned runtime deps for the image |

## Requirements

```bash
pip install pandas numpy requests
```

No API keys, no LLM calls for log generation itself.

`run_pipeline.py` additionally starts the inference API as a subprocess, so
`requirements/research-lock.txt` (fastapi, uvicorn, lightgbm, shap, joblib)
must be installed in the same interpreter.

---

# Legacy path — NF-CICIDS2018 → Zeek `conn.log`

Predates the detector integration. Produces 15 Zeek-style fields, **not** the
48 the inference API requires, and reads NF-CICIDS2018 rather than
NF-UNSW-NB15. Kept for reference; not part of the current deployment.

## Pipeline

```
full CICIDS CSV
      |
      v   template_convert_fast.py
generated_conn.log     (Zeek-style, space-separated text)
      |
      v   log_to_jsonl.py
generated_logs.jsonl   (JSON Lines)
```

> **Naming collision:** this path's final output shares the filename
> `generated_logs.jsonl` with the current path. Running both overwrites one
> with the other.

### `template_convert_fast.py`

Reads the source CSV in chunks (default 200,000 rows) and converts each row to
one Zeek `conn.log`-style text line using vectorized pandas operations rather
than a row loop, so it stays fast on large files. Prints progress per chunk.

- **Input:** `full_dataset.csv` (edit `INPUT_CSV`)
- **Output:** `generated_conn.log`

Field mapping:

| CICIDS column | Log field | Notes |
|---|---|---|
| `FLOW_START_MILLISECONDS` | `ts` | ms → seconds |
| `FLOW_START_MILLISECONDS` + `L4_SRC_PORT` | `uid` | synthetic ID (see `uid` caveat above) |
| `IPV4_SRC_ADDR` | `id.orig_h` | |
| `L4_SRC_PORT` | `id.orig_p` | |
| `IPV4_DST_ADDR` | `id.resp_h` | |
| `L4_DST_PORT` | `id.resp_p` | |
| `PROTOCOL` | `proto` | `6`→`tcp`, `17`→`udp`, `1`→`icmp` |
| `FLOW_DURATION_MILLISECONDS` | `duration` | ms → seconds |
| `IN_BYTES` / `OUT_BYTES` | `orig_bytes` / `resp_bytes` | |
| `IN_PKTS` / `OUT_PKTS` | `orig_pkts` / `resp_pkts` | |
| `TCP_FLAGS` | `tcp_flags` | |
| `MIN_TTL` / `MAX_TTL` | `min_ttl` / `max_ttl` | |

### `log_to_jsonl.py`

Re-parses `generated_conn.log` (does **not** touch the original CSV) and
rewrites each line as one JSON object per line, casting each field to the
correct type.

- **Input:** `generated_conn.log`
- **Output:** `generated_logs.jsonl`

```json
{"ts": 1518611287.705, "uid": "C151861128770553", "id.orig_h": "172.31.0.2", "id.orig_p": 53, "id.resp_h": "172.31.66.58", "id.resp_p": 63593, "proto": "udp", "duration": 0.001, "orig_bytes": 156, "resp_bytes": 0, "orig_pkts": 1, "resp_pkts": 0, "tcp_flags": 0, "min_ttl": 0, "max_ttl": 0}
```

If it reports `[SKIP] line N: expected 15 fields, got X`, a field in that line
contained an unexpected space — or the input came from one of the labelled
variants below, which emit 17 fields.

### Superseded variants

| File | Why it is not used |
|---|---|
| `template_convert_with Label.py` | Same template conversion but **includes** `label`/`attack` in the log line (17 fields), which leaks ground truth. Row-by-row loop, so also much slower. |
| `structured_intermediate.jsonl` | Stale 10-row artifact from a since-deleted LLM-rendering experiment. Still contains `label`/`attack`. |

### Dev helpers

| File | Role |
|---|---|
| `test.py` | Writes the first 10 data rows of a CSV to `first_10_rows.csv` |
| `testRead.py` | Prints `first_10_rows.csv` with all columns untruncated |
