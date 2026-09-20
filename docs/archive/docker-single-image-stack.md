> **ARCHIVED — describes a stack that no longer exists.**
>
> This documented the single-image `memsoc:latest` build driven by a
> root `Dockerfile` and `docker-compose.yml`. Both were deleted in the
> 2026-09-20 restructure in favour of the multi-service stack in
> `deploy/docker-compose.yml`. Its useful one-shot commands survive as
> the `paths`, `generate` and `tests` services behind `--profile tools`.
>
> Kept for history. **Do not follow these instructions.**
> Current guide: [`docs/deployment/operations.md`](../deployment/operations.md).

---

# Running MemSOC in Docker

Build the image, run the pipeline, run the tests. Six steps.

The image contains the code and both trained models. It does **not** contain the
NF-UNSW-NB15-v3 CSV — that file is too large to commit, so you point Docker at
your local copy.

---

## Step 1 — Start Docker Desktop

Open it and wait until the bottom-left corner says **Engine running**.

Check it from a terminal:

```powershell
docker version
```

If that errors, Docker is not running yet.

---

## Step 2 — Open a terminal in the repo root

```powershell
cd "C:\Users\Aryan Mhatre\Mem-SOC"
```

Everything below is run from here.

---

## Step 3 — Tell Docker where the dataset is

```powershell
$env:MEMSOC_HOST_DATA = "$PWD\data"
```

Point it at the folder that holds `NF-UNSW-NB15-v3.csv`. The file is found at
any depth inside that folder, so the parent folder is fine — you do **not** need
to name the `f7546561558c07c5_.../data/` subfolder.

> This variable only lasts for the current terminal window. If you open a new
> terminal, set it again.

---

## Step 4 — Build the image

```powershell
docker compose build
```

**Expect this to take 5–15 minutes the first time.** It downloads Python
packages (lightgbm, shap, scikit-learn, pandas, numpy). Later builds reuse the
cache and finish in seconds.

You are done when you see `Successfully installed ...` followed by the build
completing with no `ERROR` lines.

### If the build hangs or fails

Almost always a network problem reaching PyPI from inside the container, not a
problem with the Dockerfile.

| Symptom | What to do |
|---|---|
| Stops for minutes at `pip install`, no progress | Check your internet. If you use a VPN or corporate proxy, Docker needs it configured in **Docker Desktop → Settings → Resources → Proxies** |
| `Temporary failure resolving 'pypi.org'` | Docker Desktop → Settings → Resources → Network, then Restart Docker Desktop |
| `failed to fetch ... deb.debian.org` | Should not happen — this image installs no system packages. If it does, you edited the Dockerfile |

To watch what it is actually doing:

```powershell
docker compose build --progress plain
```

---

## Step 5 — Check Docker can see everything

```powershell
docker compose run --rm paths
```

Expected output:

```
  ok   ROOT                 /app
  ok   DATA_DIR             /data
  ok   DATASET_CSV          /data/.../NF-UNSW-NB15-v3.csv
  ok   MODELS_DIR           /app/models
  ok   BINARY_MODEL         /app/models/binary_lightgbm.pkl
  ok   MULTICLASS_MODEL     /app/models/multiclass_lightgbm.pkl
  ok   FEATURE_ENGINEERING  /app/src/memsoc/detection/features/feature_engineering.py
       ARTIFACTS_DIR        /artifacts
```

**Every line starting with a checked name must say `ok`.**

- `DATASET_CSV  MISSING` → Step 3 points at the wrong folder. Fix and rerun.
- `BINARY_MODEL  MISSING` → the `.pkl` files are not in
  `src\memsoc\detection\models\`. Put them there and rebuild (Step 4).

Do not continue until this is clean.

---

## Step 6 — Generate the logs (once)

```powershell
docker compose run --rm generate
```

This reads the CSV and writes 5,000 flow records, then classifies 10 of them as
a smoke test. **It takes a few minutes** — it scans all 2.36 million rows twice.

You are done when you see:

```
  RESULT: PIPELINE OK -- every flow classified
```

You only repeat this if you want a different sample. The records are kept in a
Docker volume and survive between runs.

---

## Step 7 — Run the pipeline

```powershell
docker compose run --rm pipeline
```

This starts the API, classifies 100 flows, prints the results, and shuts down.

Expected ending:

```
  Accepted   100/100 (100.0%)
  Latency    mean   30.1 ms   p95  115.0 ms

  Verdict distribution
    Benign             95  ##########################..
    Attack              5  #...........................

  RESULT: PIPELINE OK -- every flow classified
```

**`RESULT: PIPELINE OK` means the whole chain works** — log generation, the
48-feature contract, the API, both models, SHAP, and alerting.

---

# Testing

## Run the test suite

```powershell
docker compose run --rm tests
```

Expected:

```
Ran 9 tests in 0.8s

OK (skipped=1)
```

The suite has three tiers. Tiers skip cleanly when their input is missing, so
skips are normal — they are not failures:

| Tier | Needs | Skips if |
|---|---|---|
| Schema (3 tests) | nothing | never |
| Artifact (6 tests) | the generated logs | you have not run Step 6 |
| Live (4 tests) | a running API | the API is not up |

So:

- **Before Step 6** → `Ran 3 tests ... OK (skipped=2)` — correct.
- **After Step 6** → `Ran 9 tests ... OK (skipped=1)` — correct, live tier skipped.
- **With the API running** (see below) → `Ran 13 tests ... OK` — everything.

Any line saying `FAIL` or `ERROR` is a real problem. Skips are not.

## Run all 13 tests including the live tier

Terminal 1:

```powershell
docker compose up api
```

Wait for `Application startup complete.` (about 10–20 seconds — it loads a 35 MB
model).

Terminal 2:

```powershell
$env:MEMSOC_HOST_DATA = "$PWD\data"
docker compose run --rm tests
```

Then stop the API in Terminal 1 with `Ctrl+C`, and clean up:

```powershell
docker compose down
```

## Test the API by hand

With `docker compose up api` running, from another terminal:

```powershell
curl http://localhost:8000/health
```

Expected: `{"status":"healthy"}`

---

# Other things you can run

```powershell
docker compose run --rm stream              # live sensor emulation, Ctrl+C to stop
docker compose run --rm pipeline --flows 500  # classify more flows
docker compose up api                       # API only, on localhost:8000
docker compose down                         # stop the API
```

Note: arguments after the service name **replace** the default ones, so
`docker compose run --rm pipeline --flows 500` runs 500 flows instead of 100.

---

# Cleaning up

```powershell
docker compose down          # stop containers
docker compose down -v       # also delete the generated logs and stream cursor
```

After `down -v` you must run Step 6 again before Step 7 works.

To remove the image entirely:

```powershell
docker rmi memsoc:latest
```

---

# Quick reference

| Command | What it does |
|---|---|
| `docker compose build` | Build the image |
| `docker compose run --rm paths` | Show what Docker can and cannot find |
| `docker compose run --rm generate` | Create the 5,000 flow records (run once) |
| `docker compose run --rm pipeline` | Full demo — the one to show people |
| `docker compose run --rm tests` | Contract tests |
| `docker compose run --rm stream` | Continuous flow stream |
| `docker compose up api` | API only, on `localhost:8000` |
| `docker compose down -v` | Stop everything and wipe generated data |

---

# Troubleshooting

| Message | Cause | Fix |
|---|---|---|
| `DATASET_CSV  MISSING` | Wrong dataset folder | Redo Step 3 |
| `generated_logs.jsonl not found -- run with --regenerate` | Never generated | Run Step 6 |
| `port is already allocated` | Something else uses 8000 | `docker compose down`, or stop your local uvicorn |
| `image memsoc:latest not found` | Not built yet | Run Step 4 |
| Build hangs at `pip install` | Network / proxy | See "If the build hangs or fails" in Step 4 |
| Code changes have no effect | Image is stale | `docker compose build` again |
| `Cannot connect to the Docker daemon` | Docker Desktop not running | Start it, wait for *Engine running* |

---

# Running without Docker

Everything works natively too:

```powershell
python src\memsoc\logstream\run_pipeline.py --paths     # check paths
python src\memsoc\logstream\run_pipeline.py --flows 100 # full demo
python log_generation\test_pipeline.py            # tests
```

This needs `pandas numpy requests fastapi uvicorn lightgbm shap joblib
scikit-learn` installed locally. It was verified working — see `SUMMARY.md`.
