# MemSOC Operations Guide

This guide explains how to operate the complete MemSOC Docker pipeline from startup to shutdown.

---

## 1. MemSOC Pipeline Overview

MemSOC runs as three Docker services:

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
LLMTriage/model_outputs/live_results.jsonl
        |
        v
Report API / Report Generator :8001
        |
        | Groq API
        v
LLMTriage/reports/
        |
        v
Dashboard :8080
```

### Services

| Service | Port | Purpose |
|---|---:|---|
| Detection | 8000 | Performs ML-based network-flow detection |
| Report | 8001 | Generates and serves security reports |
| Dashboard | 8080 | Displays the generated security reports |

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

Start all three services:

```powershell
docker compose -f .\Deployment\docker-compose.yml up -d
```

### What this command does

- Creates the Docker Compose network if required.
- Starts the Detection container.
- Starts the Report container.
- Starts the Dashboard container.
- Runs them in the background because of `-d`.

Expected services:

```text
memsoc-detection
memsoc-report
memsoc-dashboard
```

---

# 4. Check Whether Everything Is Running

Run:

```powershell
docker compose -f .\Deployment\docker-compose.yml ps
```

All three services should show:

```text
Up
```

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
LLMTriage/live_capture.py
```

It reads:

```text
log_generation/generated_logs.jsonl
```

and sends each flow to:

```text
http://127.0.0.1:8000/api/logs
```

The Detection API processes each flow and returns the ML prediction.

The results are appended to:

```text
LLMTriage/model_outputs/live_results.jsonl
```

## Normal one-pass capture

Run:

```powershell
python .\LLMTriage\live_capture.py
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

# 10. Reset Results Before a New Run

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
python .\LLMTriage\live_capture.py --reset
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
LLMTriage/model_outputs/live_results.jsonl
```

It does not delete:

```text
log_generation/generated_logs.jsonl
```

and it does not delete existing reports.

---

# 11. Run Capture Continuously

To repeatedly process the generated stream:

```powershell
python .\LLMTriage\live_capture.py --loop
```

### What `--loop` does

After the stream reaches the end, the program starts again from the beginning.

It continues until you stop it with:

```text
Ctrl + C
```

Because results are append-only, each loop adds more results to `live_results.jsonl`.

---

# 12. Add a Delay Between Flows

To process approximately one flow per second:

```powershell
python .\LLMTriage\live_capture.py --interval 1.0
```

The value is in seconds.

Examples:

```powershell
python .\LLMTriage\live_capture.py --interval 0.5
```

Approximately 0.5 seconds between flows.

```powershell
python .\LLMTriage\live_capture.py --interval 2.0
```

Approximately 2 seconds between flows.

For the fastest processing allowed by the API:

```powershell
python .\LLMTriage\live_capture.py
```

The default interval is `0`.

---

# 13. Generate a Security Report

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
LLMTriage/reports/
```

The host directory is shared with the Report container.

---

# 14. Generate a Small/Test Report

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

# 15. Limit the Number of Findings

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

# 16. Verify Generated Results

Check the model-output file:

```powershell
Get-Item .\LLMTriage\model_outputs\live_results.jsonl |
    Select-Object FullName, Length
```

Count result lines:

```powershell
(Get-Content .\LLMTriage\model_outputs\live_results.jsonl).Count
```

Check reports:

```powershell
Get-ChildItem .\LLMTriage\reports -File |
    Select-Object Name, Length
```

---

# 17. Verify the Shared Files from Inside Docker

Check model outputs from the Report container:

```powershell
docker exec memsoc-report sh -c "ls -lh /app/LLMTriage/model_outputs"
```

Check reports:

```powershell
docker exec memsoc-report sh -c "ls -lh /app/LLMTriage/reports"
```

The Report container should see the same files that exist in:

```text
LLMTriage/model_outputs/
LLMTriage/reports/
```

on the Windows host.

---

# 18. Refresh the Dashboard After Generating a Report

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

# 19. Full Normal Operating Procedure

For a normal clean run, use this sequence.

### Step 1 — Start Docker

```powershell
docker compose -f .\Deployment\docker-compose.yml up -d
```

### Step 2 — Check containers

```powershell
docker compose -f .\Deployment\docker-compose.yml ps
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
python .\LLMTriage\live_capture.py --reset
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

# 20. Running 10,000 Flows

If `generated_logs.jsonl` contains 10,000 flows and you want a clean 10,000-flow run:

```powershell
python .\LLMTriage\live_capture.py --reset
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

# 21. Stop the Capture Program

If `live_capture.py` is running in the foreground:

```text
Ctrl + C
```

The script catches the interrupt and exits.

If it is running with `--loop`, `Ctrl + C` stops the loop.

---

# 22. Stop the Docker Pipeline

To stop all MemSOC Compose services:

```powershell
docker compose -f .\Deployment\docker-compose.yml stop
```

This stops the containers but keeps them available for restarting.

Start them again with:

```powershell
docker compose -f .\Deployment\docker-compose.yml start
```

---

# 23. Stop and Remove the Compose Containers

To stop and remove the containers and Compose network:

```powershell
docker compose -f .\Deployment\docker-compose.yml down
```

This does not delete the host directories mounted into the containers.

Your:

```text
LLMTriage/model_outputs/
LLMTriage/reports/
```

remain on the Windows host.

Start the complete deployment again with:

```powershell
docker compose -f .\Deployment\docker-compose.yml up -d
```

---

# 24. Check Container Logs

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

# 25. Rebuild Images After Code Changes

If Detection code or its Dockerfile changes:

```powershell
docker build -f .\Deployment\detection\Dockerfile -t memsoc-detection:latest .\Deployment\detection
```

If Report code or its Dockerfile changes:

```powershell
docker build -f .\Deployment\report\Dockerfile -t memsoc-report:latest .\Deployment\report
```

If Dashboard code or its Dockerfile changes:

```powershell
docker build -f .\Deployment\dashboard\Dockerfile -t memsoc-dashboard:latest .\Deployment\dashboard
```

Then recreate the affected Compose services:

```powershell
docker compose -f .\Deployment\docker-compose.yml up -d
```

---

# 26. Important Docker Build Rule

Build each service using its own deployment directory.

Detection:

```powershell
docker build -f .\Deployment\detection\Dockerfile -t memsoc-detection:latest .\Deployment\detection
```

Report:

```powershell
docker build -f .\Deployment\report\Dockerfile -t memsoc-report:latest .\Deployment\report
```

Dashboard:

```powershell
docker build -f .\Deployment\dashboard\Dockerfile -t memsoc-dashboard:latest .\Deployment\dashboard
```

Do not use the repository root as the build context for the Detection image.

Using the deployment-specific context keeps the Docker build small and prevents the multi-GB project dataset and unrelated files from being sent to Docker.

---

# 27. Common Problems

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
```

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
docker compose -f .\Deployment\docker-compose.yml down
docker compose -f .\Deployment\docker-compose.yml up -d
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
Get-ChildItem .\LLMTriage\reports -File |
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

# 28. Recommended Daily/Normal Workflow

For a clean new experiment:

```powershell
# 1. Start services
docker compose -f .\Deployment\docker-compose.yml up -d

# 2. Verify services
docker compose -f .\Deployment\docker-compose.yml ps

# 3. Verify Detection
Invoke-RestMethod http://localhost:8000/health

# 4. Run a fresh capture
python .\LLMTriage\live_capture.py --reset

# 5. Generate report
docker exec memsoc-report python generate_report.py

# 6. Open dashboard
# http://localhost:8080

# 7. When finished, stop services
docker compose -f .\Deployment\docker-compose.yml stop
```

---

# 29. Quick Command Reference

| Action | Command |
|---|---|
| Start all services | `docker compose -f .\Deployment\docker-compose.yml up -d` |
| Check services | `docker compose -f .\Deployment\docker-compose.yml ps` |
| Stop services | `docker compose -f .\Deployment\docker-compose.yml stop` |
| Remove Compose containers | `docker compose -f .\Deployment\docker-compose.yml down` |
| Restart stopped services | `docker compose -f .\Deployment\docker-compose.yml start` |
| Detection health | `Invoke-RestMethod http://localhost:8000/health` |
| Report health | `Invoke-RestMethod http://localhost:8001/health` |
| List reports | `Invoke-RestMethod http://localhost:8001/api/reports` |
| Open dashboard | `http://localhost:8080` |
| Normal capture | `python .\LLMTriage\live_capture.py` |
| Clean capture | `python .\LLMTriage\live_capture.py --reset` |
| Continuous capture | `python .\LLMTriage\live_capture.py --loop` |
| Capture with delay | `python .\LLMTriage\live_capture.py --interval 1.0` |
| Generate report | `docker exec memsoc-report python generate_report.py` |
| Test report | `docker exec memsoc-report python generate_report.py --limit 10` |
| Detection logs | `docker logs memsoc-detection --tail 100` |
| Report logs | `docker logs memsoc-report --tail 100` |
| Dashboard logs | `docker logs memsoc-dashboard --tail 100` |

---

# 30. Final Operational Sequence

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
