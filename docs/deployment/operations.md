# MemSOC Operations Guide

This guide explains how to operate the complete MemSOC Docker pipeline from startup to shutdown.

---

## 1. MemSOC Pipeline Overview

MemSOC runs as four Docker services. Three are long-running daemons
(Detection, Report, Dashboard); the fourth, `logstream`, is a
one-shot container that generates flows from the NF-UNSW-NB15 dataset
and can feed them to Detection on its own, without the host-side
`live_capture.py` script.

```text
Generated network flows
        |
        v
live_capture.py
        |
        | HTTP POST
        v
Detection API :8000
        |
        | ML prediction
        v
artifacts/model_outputs/live_results.jsonl
        |
        v
Report API / Report Generator :8001
        |
        | Groq API
        v
artifacts/reports/
        |
        v
Dashboard :8080
```

The containerized `logstream` service is a separate, self-contained
path that talks to Detection directly over the Docker network -- see
Section 10. It does not write to `live_results.jsonl` and does not feed
Report or Dashboard.

### Services

| Service | Port | Purpose |
|---|---:|---|
| Detection | 8000 | Performs ML-based network-flow detection |
| Report | 8001 | Generates and serves security reports |
| Dashboard | 8080 | Displays the generated security reports |
| logstream | -- | Generates flows from the dataset and classifies them against Detection (one-shot, no published port) |

---

# 2. Prerequisites

Before starting MemSOC:

- Docker Desktop must be running.
- The repository should be open at the Mem-SOC root.
- The Groq API key must be available through the root `.env` file.

Expected location:

```text
Mem-SOC/
└── .env
```

The `.env` file should contain:

```text
GROQ_API_KEY=your_actual_groq_api_key
```

The `.env` file must remain excluded from Git.

### Check the API key

Run:

```powershell
if ($env:GROQ_API_KEY) {
    Write-Host "GROQ_API_KEY is set"
} else {
    Write-Host "GROQ_API_KEY is NOT set"
}
```

The Compose configuration also reads `GROQ_API_KEY` from the environment.

---

# 3. Start the Docker Pipeline

Open PowerShell in the repository root:

```text
C:\Users\<username>\Desktop\Git Repository\Mem Soc\Mem-SOC
```

Start all services:

```powershell
docker compose -f .\deploy\docker-compose.yml up -d
```

### What this command does

- Creates the Docker Compose network if required.
- Starts the Detection container.
- Starts the Report container.
- Starts the Dashboard container.
- Builds and runs the `logstream` container once, then lets it
  exit -- it has no long-running process (see Section 10). On a fresh
  artifacts volume this first run will fail until you run it with
  `--regenerate`; that failure is expected and does not affect the other
  three services.
- Runs them in the background because of `-d`.

Expected services:

```text
memsoc-detection
memsoc-report
memsoc-dashboard
memsoc-logstream
```

---

# 4. Check Whether Everything Is Running

Run:

```powershell
docker compose -f .\deploy\docker-compose.yml ps
```

Detection, Report and Dashboard should show:

```text
Up
```

`logstream` (`memsoc-logstream`) is not a daemon -- it shows
`Exited (0)` after a successful run. `Exited (1)` on the very first run
is expected too, if the artifacts volume was still empty (see the
`--regenerate` note in Section 10); rerun it with `--regenerate` and it
will exit 0. A non-Up/Exited state on Detection, Report or Dashboard is
the only thing here that indicates a real problem.

Expected ports:

```text
Detection  -> 8000
Report     -> 8001
Dashboard  -> 8080
```

---

# 5. Check Detection API

Run:

```powershell
Invoke-RestMethod http://localhost:8000/health
```

Expected:

```text
status
------
healthy
```

This only checks that the Detection API is alive.

---

# 6. Check Report API

Run:

```powershell
Invoke-RestMethod http://localhost:8001/health
```

Expected response contains:

```text
status: ok
```

To list available reports:

```powershell
Invoke-RestMethod http://localhost:8001/api/reports
```

Important:

```text
/api/reports
```

is the correct report-list endpoint.

---

# 7. Check Detection-to-Report Networking

The Report container communicates with Detection using the Docker Compose service name:

```text
http://detection:8000
```

Test the connection:

```powershell
docker exec memsoc-report python -c "import requests; r=requests.get('http://detection:8000/health', timeout=10); print(r.status_code); print(r.text)"
```

Expected:

```text
200
{"status":"healthy"}
```

If this succeeds, Docker's internal networking between Report and Detection is working.

---

# 8. Open the Dashboard

Open:

```text
http://localhost:8080
```

The dashboard is served by Nginx inside the Dashboard container.

The dashboard reads report information from the Stage 4 Report API.

It does not start capture or generate reports itself.

---

# 9. Run the Live Capture Pipeline

The capture program is:

```text
src/memsoc/triage/live_capture.py
```

It reads:

```text
artifacts/generated_logs.jsonl
```

and sends each flow to:

```text
http://127.0.0.1:8000/api/logs
```

The Detection API processes each flow and returns the ML prediction.

The results are appended to:

```text
artifacts/model_outputs/live_results.jsonl
```

## Normal one-pass capture

Run:

```powershell
python .\src\memsoc\triage\live_capture.py
```

### What it does

- Reads every flow in `generated_logs.jsonl`.
- Sends flows one-by-one to the Detection API.
- Prints whether each flow is benign or an attack.
- Appends each successful result to `live_results.jsonl`.
- Stops after the complete input stream has been processed.

Example:

```text
[1] uid=... -> benign
[2] uid=... -> ATTACK/...
...
Pass complete: 10000/10000 flows captured.
```

---

# 10. Run Log Generation (Containerized Alternative)

There is a fourth Compose service, `logstream`, that is a separate
path from Section 9's `live_capture.py`. It does not write to
`live_results.jsonl` and it does not feed the Report or Dashboard
services -- it is a self-contained way to generate flows from the
NF-UNSW-NB15 dataset and classify them straight against the Detection
container, entirely inside Docker.

Use it when you want to exercise Detection without first generating
`artifacts/generated_logs.jsonl` on the host.

```text
NF-UNSW-NB15-v3.csv (mounted at /data)
        |
        v
logstream container
        |
        | HTTP POST (Docker network: http://detection:8000)
        v
Detection API :8000
        |
        v
Console summary (verdict counts, latency, HTTP status)
```

### One-time setup

Point `MEMSOC_HOST_DATA` at the directory holding `NF-UNSW-NB15-v3.csv`
(any depth -- the container walks the mount). From the repository root:

```powershell
$env:MEMSOC_HOST_DATA = "$PWD\data"
```

### Build the image

```powershell
docker compose -f .\deploy\docker-compose.yml build logstream
```

### First run -- build the flow log from the CSV

The container's own artifacts volume starts empty, so the first run must
regenerate `generated_logs.jsonl` from the dataset:

```powershell
docker compose -f .\deploy\docker-compose.yml --profile tools run --rm logstream --regenerate --sample-size 5000 --flows 100
```

This can take a minute or two -- it scans the full 2.36M-row CSV twice.

### Later runs -- reuse the generated log

Once `generated_logs.jsonl` exists in the artifacts volume, skip
`--regenerate` and just classify more flows:

```powershell
docker compose -f .\deploy\docker-compose.yml --profile tools run --rm logstream --flows 500
```

### What happens automatically

- `logstream` waits for the Detection container's `/health` endpoint
  before sending anything, so it is safe to run right after starting the
  stack even while the multiclass model is still loading.
- The container never loads a model itself -- it only sends HTTP requests
  to Detection, the same as `live_capture.py` does from the host.

### Important

Because `logstream` has no long-running process, plain
`docker compose -f .\deploy\docker-compose.yml up -d` will also build
and run it once alongside Detection, Report and Dashboard, then let it
exit. On a brand-new artifacts volume that run will fail with
`generated_logs.jsonl not found -- run with --regenerate` (see Section 28
Common Problems); this is expected the first time, not a broken
deployment. Run `docker compose --profile tools run --rm logstream --regenerate ...`
once beforehand, or just use `--profile tools run --rm logstream` on demand instead
of relying on `up -d` to populate it.

---

# 11. Reset Results Before a New Run

`live_capture.py` is append-only by default.

For example, if:

```text
live_results.jsonl
```

already contains 5,010 results and you run another 10,000-flow capture normally, the file will contain approximately:

```text
5,010 + 10,000 = 15,010 results
```

If you want the new run to start from an empty result file, use:

```powershell
python .\src\memsoc\triage\live_capture.py --reset
```

### What `--reset` does

It:

1. Deletes the existing `live_results.jsonl`.
2. Starts a fresh capture.
3. Writes only the results from the new run.

Use this when you want a clean experiment/run.

### Important

`--reset` affects:

```text
artifacts/model_outputs/live_results.jsonl
```

It does not delete:

```text
artifacts/generated_logs.jsonl
```

and it does not delete existing reports.

---

# 12. Run Capture Continuously

To repeatedly process the generated stream:

```powershell
python .\src\memsoc\triage\live_capture.py --loop
```

### What `--loop` does

After the stream reaches the end, the program starts again from the beginning.

It continues until you stop it with:

```text
Ctrl + C
```

Because results are append-only, each loop adds more results to `live_results.jsonl`.

---

# 13. Add a Delay Between Flows

To process approximately one flow per second:

```powershell
python .\src\memsoc\triage\live_capture.py --interval 1.0
```

The value is in seconds.

Examples:

```powershell
python .\src\memsoc\triage\live_capture.py --interval 0.5
```

Approximately 0.5 seconds between flows.

```powershell
python .\src\memsoc\triage\live_capture.py --interval 2.0
```

Approximately 2 seconds between flows.

For the fastest processing allowed by the API:

```powershell
python .\src\memsoc\triage\live_capture.py
```

The default interval is `0`.

---

# 14. Generate a Security Report

After capture results exist, generate a report inside the Report container:

```powershell
docker exec memsoc-report python generate_report.py
```

### What it does

The Report container:

1. Reads `live_results.jsonl`.
2. Calculates verified statistics.
3. Builds findings.
4. Sends the report-analysis prompt to Groq.
5. Receives the LLM analysis.
6. Writes a JSON report.
7. Writes a Markdown report.

Reports are stored in:

```text
artifacts/reports/
```

The host directory is shared with the Report container.

---

# 15. Generate a Small/Test Report

To generate a report using only the 10 most recently captured flows:

```powershell
docker exec memsoc-report python generate_report.py --limit 10
```

This is useful for testing without generating a report from the complete capture.

For example:

```text
10 captured flows
        |
        v
statistics
        |
        v
Groq analysis
        |
        v
JSON + Markdown report
```

---

# 16. Limit the Number of Findings

To limit detailed findings to 25:

```powershell
docker exec memsoc-report python generate_report.py --max-findings 25
```

You can combine options:

```powershell
docker exec memsoc-report python generate_report.py --limit 100 --max-findings 25
```

This means:

- Use the latest 100 captured flows.
- Include at most 25 detailed findings.

---

# 17. Verify Generated Results

Check the model-output file:

```powershell
Get-Item .\artifacts\model_outputs\live_results.jsonl |
    Select-Object FullName, Length
```

Count result lines:

```powershell
(Get-Content .\artifacts\model_outputs\live_results.jsonl).Count
```

Check reports:

```powershell
Get-ChildItem .\artifacts\reports -File |
    Select-Object Name, Length
```

---

# 18. Verify the Shared Files from Inside Docker

Check model outputs from the Report container:

```powershell
docker exec memsoc-report sh -c "ls -lh /app/artifacts/model_outputs"
```

Check reports:

```powershell
docker exec memsoc-report sh -c "ls -lh /app/artifacts/reports"
```

The Report container should see the same files that exist in:

```text
artifacts/model_outputs/
artifacts/reports/
```

on the Windows host.

---

# 19. Refresh the Dashboard After Generating a Report

After generating a new report:

1. Open:

```text
http://localhost:8080
```

2. Refresh the page with:

```text
Ctrl + R
```

3. Select the newest report from the report selector.

The dashboard should display the new flow count, attack count, attack rate, risk level, findings, recommendations, and trends contained in the report.

---

# 20. Full Normal Operating Procedure

For a normal clean run, use this sequence.

### Step 1 — Start Docker

```powershell
docker compose -f .\deploy\docker-compose.yml up -d
```

### Step 2 — Check containers

```powershell
docker compose -f .\deploy\docker-compose.yml ps
```

All three should be `Up`.

### Step 3 — Check Detection

```powershell
Invoke-RestMethod http://localhost:8000/health
```

Expected:

```text
healthy
```

### Step 4 — Run a clean capture

If you want the new run to contain only the current capture:

```powershell
python .\src\memsoc\triage\live_capture.py --reset
```

### Step 5 — Wait for capture to finish

You should eventually see:

```text
Pass complete: X/X flows captured.
```

### Step 6 — Generate the report

```powershell
docker exec memsoc-report python generate_report.py
```

### Step 7 — Open the dashboard

```text
http://localhost:8080
```

### Step 8 — Refresh the dashboard

```text
Ctrl + R
```

### Step 9 — Select the newest report

The newest report should appear in the dashboard.

---

# 21. Running 10,000 Flows

If `generated_logs.jsonl` contains 10,000 flows and you want a clean 10,000-flow run:

```powershell
python .\src\memsoc\triage\live_capture.py --reset
```

The program will process all 10,000 records.

After completion:

```powershell
docker exec memsoc-report python generate_report.py
```

Then refresh:

```text
http://localhost:8080
```

### Important

Do not manually modify the Docker containers for a larger dataset.

The capture script processes the input line-by-line, so the same pipeline can process 10, 5,000, or 10,000 flows as long as the records have the expected schema.

---

# 22. Stop the Capture Program

If `live_capture.py` is running in the foreground:

```text
Ctrl + C
```

The script catches the interrupt and exits.

If it is running with `--loop`, `Ctrl + C` stops the loop.

---

# 23. Stop the Docker Pipeline

To stop all MemSOC Compose services:

```powershell
docker compose -f .\deploy\docker-compose.yml stop
```

This stops the containers but keeps them available for restarting.

Start them again with:

```powershell
docker compose -f .\deploy\docker-compose.yml start
```

---

# 24. Stop and Remove the Compose Containers

To stop and remove the containers and Compose network:

```powershell
docker compose -f .\deploy\docker-compose.yml down
```

This does not delete the host directories mounted into the containers.

Your:

```text
artifacts/model_outputs/
artifacts/reports/
```

remain on the Windows host.

`logstream`'s own output (`generated_logs.jsonl`, `ground_truth.csv`)
lives in a named Docker volume, not a host directory. Plain `down` leaves
that volume alone; `docker compose down -v` deletes it, and the next
`logstream` run will need `--regenerate` again (see Section 10).

Start the complete deployment again with:

```powershell
docker compose -f .\deploy\docker-compose.yml up -d
```

---

# 25. Check Container Logs

Detection logs:

```powershell
docker logs memsoc-detection --tail 100
```

Report logs:

```powershell
docker logs memsoc-report --tail 100
```

Dashboard logs:

```powershell
docker logs memsoc-dashboard --tail 100
```

Follow Report logs continuously:

```powershell
docker logs -f memsoc-report
```

Press:

```text
Ctrl + C
```

to stop following the logs.

---

# 26. Rebuild Images After Code Changes

If Detection code or its Dockerfile changes:

```powershell
docker build -f .\Dockerfile -t memsoc-detection:latest .
```

If Report code or its Dockerfile changes:

```powershell
docker build -f .\Dockerfile -t memsoc-report:latest .
```

If Dashboard code or its Dockerfile changes:

```powershell
docker build -f .\Dockerfile -t memsoc-dashboard:latest .
```

If `logstream` code or its Dockerfile changes:

```powershell
docker build -f .\deploy\deploy\logstream.Dockerfile -t memsoc-logstream:latest .
```

Then recreate the affected Compose services:

```powershell
docker compose -f .\deploy\docker-compose.yml up -d
```

---

# 27. Important Docker Build Rule

Build each service using its own deployment directory.

Detection:

```powershell
docker build -f .\Dockerfile -t memsoc-detection:latest .
```

Report:

```powershell
docker build -f .\Dockerfile -t memsoc-report:latest .
```

Dashboard:

```powershell
docker build -f .\Dockerfile -t memsoc-dashboard:latest .
```

logstream:

```powershell
docker build -f .\deploy\deploy\logstream.Dockerfile -t memsoc-logstream:latest .
```

Do not use the repository root as the build context for the Detection image.

Using the deployment-specific context keeps the Docker build small and prevents the multi-GB project dataset and unrelated files from being sent to Docker.

---

# 28. Common Problems

## Detection container exits

Check:

```powershell
docker logs memsoc-detection --tail 100
```

If the error mentions:

```text
libgomp.so.1
```

the Detection image must contain the `libgomp1` runtime package. Rebuild the Detection image.

---

## Container name conflict

Check:

```powershell
docker ps -a
```

For old test containers, remove them if they are no longer needed:

```powershell
docker rm -f memsoc-detection-test
docker rm -f memsoc-report-test
docker rm -f memsoc-dashboard-test
```

The normal Compose containers are:

```text
memsoc-detection
memsoc-report
memsoc-dashboard
memsoc-logstream
```

---

## logstream exits with "generated_logs.jsonl not found"

Check:

```powershell
docker logs memsoc-logstream --tail 50
```

This means the artifacts volume has no generated flow log yet -- expected
on the very first run, or after `docker compose down -v` removed the
`logstream` artifacts volume. Fix it by regenerating once:

```powershell
docker compose -f .\deploy\docker-compose.yml --profile tools run --rm logstream --regenerate --sample-size 5000 --flows 100
```

See Section 10 for the full explanation.

---

## logstream exits with "FAIL: ... not healthy"

`wait_for_detection.py` gave up waiting for `http://detection:8000/health`
(default timeout 180s). Check that Detection actually started:

```powershell
docker logs memsoc-detection --tail 100
```

If Detection is healthy but this still happens, confirm both containers
are on the same Compose network by running `docker compose ps` from the
same `docker-compose.yml` -- `logstream` resolves `detection` by
Compose service name, which only works within that network.

---

## Report API returns 404

Use:

```powershell
Invoke-RestMethod http://localhost:8001/api/reports
```

The report-list endpoint is:

```text
/api/reports
```

not:

```text
/reports
```

---

## Report generation says the API key is missing

Check:

```powershell
if ($env:GROQ_API_KEY) {
    Write-Host "GROQ_API_KEY is set"
} else {
    Write-Host "GROQ_API_KEY is NOT set"
}
```

Then verify the `.env` file contains the key and restart Compose:

```powershell
docker compose -f .\deploy\docker-compose.yml down
docker compose -f .\deploy\docker-compose.yml up -d
```

Never place the real key directly in source code or commit it to Git.

---

## Dashboard does not show a newly generated report

Check the Report API:

```powershell
Invoke-RestMethod http://localhost:8001/api/reports
```

Check the report files:

```powershell
Get-ChildItem .\artifacts\reports -File |
    Select-Object Name, Length
```

Then refresh:

```text
http://localhost:8080
```

with:

```text
Ctrl + R
```

---

# 29. Recommended Daily/Normal Workflow

For a clean new experiment:

```powershell
# 1. Start services
docker compose -f .\deploy\docker-compose.yml up -d

# 2. Verify services
docker compose -f .\deploy\docker-compose.yml ps

# 3. Verify Detection
Invoke-RestMethod http://localhost:8000/health

# 4. Run a fresh capture
python .\src\memsoc\triage\live_capture.py --reset

# 5. Generate report
docker exec memsoc-report python generate_report.py

# 6. Open dashboard
# http://localhost:8080

# 7. When finished, stop services
docker compose -f .\deploy\docker-compose.yml stop
```

---

# 30. Quick Command Reference

| Action | Command |
|---|---|
| Start all services | `docker compose -f .\deploy\docker-compose.yml up -d` |
| Check services | `docker compose -f .\deploy\docker-compose.yml ps` |
| Stop services | `docker compose -f .\deploy\docker-compose.yml stop` |
| Remove Compose containers | `docker compose -f .\deploy\docker-compose.yml down` |
| Restart stopped services | `docker compose -f .\deploy\docker-compose.yml start` |
| Detection health | `Invoke-RestMethod http://localhost:8000/health` |
| Report health | `Invoke-RestMethod http://localhost:8001/health` |
| List reports | `Invoke-RestMethod http://localhost:8001/api/reports` |
| Open dashboard | `http://localhost:8080` |
| Normal capture | `python .\src\memsoc\triage\live_capture.py` |
| Clean capture | `python .\src\memsoc\triage\live_capture.py --reset` |
| Continuous capture | `python .\src\memsoc\triage\live_capture.py --loop` |
| Capture with delay | `python .\src\memsoc\triage\live_capture.py --interval 1.0` |
| Generate report | `docker exec memsoc-report python generate_report.py` |
| Test report | `docker exec memsoc-report python generate_report.py --limit 10` |
| Detection logs | `docker logs memsoc-detection --tail 100` |
| Report logs | `docker logs memsoc-report --tail 100` |
| Dashboard logs | `docker logs memsoc-dashboard --tail 100` |
| Build logstream image | `docker compose -f .\deploy\docker-compose.yml build logstream` |
| Regenerate flows from CSV (first run) | `docker compose -f .\deploy\docker-compose.yml --profile tools run --rm logstream --regenerate --sample-size 5000 --flows 100` |
| Classify more flows (containerized) | `docker compose -f .\deploy\docker-compose.yml --profile tools run --rm logstream --flows 500` |
| logstream logs | `docker logs memsoc-logstream --tail 100` |

---

# 31. Final Operational Sequence

The complete MemSOC operation can be remembered as:

```text
START
  |
  v
docker compose up -d
  |
  v
Check containers
  |
  v
Check Detection health
  |
  v
Run live_capture.py
  |
  v
Detection performs ML inference
  |
  v
Results appended to live_results.jsonl
  |
  v
Generate report in Report container
  |
  v
JSON + Markdown report created
  |
  v
Open/refresh Dashboard
  |
  v
Review security report
  |
  v
STOP
  |
  v
docker compose stop
```

For a fresh experiment, use `live_capture.py --reset` before capture.

For a repeated/continuous simulation, use `live_capture.py --loop`.

For a test without processing the entire captured result set, use `generate_report.py --limit N`.

The Docker deployment itself does not need to be rebuilt when only the generated dataset changes; rebuild images when application code, dependencies, Dockerfiles, or image-baked model files change.
