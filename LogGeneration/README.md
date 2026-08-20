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
`final_ml_model_v1`; the legacy path predates the detector integration and is
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
`final_ml_model_v1/src/features/feature_engineering.py` drops **7** of them,
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

## Usage

```powershell
# 1. Generate the log stream + ground truth sidecar
python nfv3_log_generator.py

# 2. Start the API -- see the note below on why cwd is src/
cd ..\final_ml_model_v1\src
$env:PYTHONPATH = "..\..\final_ml_model_v1"
python -m uvicorn src.api.server:app

# 3. Replay the stream into the API (from LogGeneration/)
python replay_to_api.py
```

> **Why not just `python -m uvicorn src.api.server:app` from
> `final_ml_model_v1/`?** `InferencePipeline.__init__` defaults to
> `models/binary_lightgbm.pkl`, but the `.pkl` files actually live in
> `final_ml_model_v1/src/models/`. Running from `src/` makes the relative model
> path resolve; `PYTHONPATH` keeps the `src.api.server` import working. This is
> a path bug in `final_ml_model_v1`, not in log generation — worked around here,
> not fixed.

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
# Start the API first (see the cwd/PYTHONPATH note above)
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

## Files

| File | Role |
|---|---|
| `nfv3_log_generator.py` | NF-UNSW-NB15-v3 CSV → `generated_logs.jsonl` + `ground_truth.csv` |
| `replay_to_api.py` | `generated_logs.jsonl` → `POST /api/logs`, reports status and verdict |
| `stream_to_api.py` | Continuous sensor-style stream → `POST /api/logs`, resumable |

## Requirements

```bash
pip install pandas numpy requests
```

No API keys, no LLM calls. Pure pandas/numpy.

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
