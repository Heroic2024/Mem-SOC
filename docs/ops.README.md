# MemSOC Operations README

## 1. Overview

MemSOC is operated as a Dockerized cybersecurity workflow consisting of:

1. Docker infrastructure startup
2. Interactive controller
3. Network log generation
4. Live capture through the Detection API
5. Security report generation using the report pipeline and Groq
6. Dashboard visualization

Normal workflow:

```text
Start Docker
    ↓
Run Controller
    ↓
Enter number of logs
    ↓
Generate logs
    ↓
Choose Y for live capture
    ↓
Capture flows through Detection API
    ↓
Press ENTER
    ↓
Generate security report
    ↓
Open Dashboard
    ↓
Finish
    ↓
Stop Docker
```

## 2. Prerequisites

- Docker Desktop is installed and running.
- PowerShell is opened in the MemSOC project root.
- The NF-UNSW-NB15-v3 dataset is available at:

```text
final_ml_model_v1\data\raw\NF-UNSW-NB15-v3.csv
```

- The root `.env` file contains the required `GROQ_API_KEY`.

## 3. Open the Project

```powershell
cd "C:\Users\Aadit\Desktop\Git Repository\Mem Soc\Mem-SOC"
```

## 4. Set the Dataset Variable

At the beginning of a new PowerShell session:

```powershell
$env:MEMSOC_HOST_DATA="..\final_ml_model_v1\data\raw"
```

This allows Docker to access:

```text
/data/NF-UNSW-NB15-v3.csv
```

The variable is session-specific, so set it again when opening a new PowerShell window.

## 5. Start MemSOC

```powershell
docker compose -f .\Deployment\docker-compose.yml up -d
```

Check status:

```powershell
docker compose -f .\Deployment\docker-compose.yml ps
```

| Service | Purpose | Port |
|---|---|---:|
| `memsoc-detection` | ML detection API | 8000 |
| `memsoc-report` | Report generation/API | 8001 |
| `memsoc-dashboard` | Web dashboard | 8081 |
| `memsoc-log-generation` | Log-generation service | One-shot |
| `memsoc-controller` | Interactive workflow controller | Run when needed |

The dashboard uses host port **8081** because port 8080 is occupied on the current system.

## 6. Run the MemSOC Controller

```powershell
docker compose -f .\Deployment\docker-compose.yml run --rm controller
```

The controller asks:

```text
How many logs do you want to generate?
```

Enter the required number, for example:

```text
1000
```

It then asks:

```text
Start live capture? (Y/N):
```

Enter:

```text
Y
```

to send the generated flows through the Detection API.

If `N` is selected, the workflow stops after log generation.

## 7. Live Capture

Generated logs are written inside Docker to:

```text
/artifacts/generated_logs.jsonl
```

The live-capture process sends each flow to:

```text
http://detection:8000/api/logs
```

Results are written to:

```text
LLMTriage/model_outputs/live_results.jsonl
```

The controller uses `--reset` before capture, so each workflow starts with a fresh `live_results.jsonl`.

## 8. Generate the Security Report

After live capture finishes, the controller displays:

```text
Press ENTER to generate the security report...
```

Press **ENTER**.

Reports are stored under:

```text
LLMTriage/reports/
```

The report service is available at:

```text
http://localhost:8001
```

## 9. Open the Dashboard

After:

```text
MemSOC WORKFLOW COMPLETE
```

open:

```text
http://localhost:8081
```

## 10. Complete Normal Operation

### Step 1 — Open project

```powershell
cd "C:\Users\Aadit\Desktop\Git Repository\Mem Soc\Mem-SOC"
```

### Step 2 — Set dataset path

```powershell
$env:MEMSOC_HOST_DATA="..\final_ml_model_v1\data\raw"
```

### Step 3 — Start Docker

```powershell
docker compose -f .\Deployment\docker-compose.yml up -d
```

### Step 4 — Check services

```powershell
docker compose -f .\Deployment\docker-compose.yml ps
```

### Step 5 — Run controller

```powershell
docker compose -f .\Deployment\docker-compose.yml run --rm controller
```

### Step 6 — Follow controller prompts

```text
How many logs do you want to generate?
→ Enter number

Start live capture? (Y/N):
→ Y

Press ENTER to generate the security report...
→ Press ENTER
```

### Step 7 — Open dashboard

```text
http://localhost:8081
```

### Step 8 — Stop Docker after completion

```powershell
docker compose -f .\Deployment\docker-compose.yml down
```

## 11. Stop MemSOC

For a complete shutdown:

```powershell
docker compose -f .\Deployment\docker-compose.yml down
```

This stops and removes the containers but does not remove the Docker images.

Do not run `down` while the controller is actively generating logs, capturing flows, or generating the report. Wait until `MemSOC WORKFLOW COMPLETE` appears.

## 12. Temporary Stop and Restart

To pause the services:

```powershell
docker compose -f .\Deployment\docker-compose.yml stop
```

To start the stopped containers again:

```powershell
docker compose -f .\Deployment\docker-compose.yml start
```

## 13. Start After Complete Shutdown

After `docker compose down`:

```powershell
docker compose -f .\Deployment\docker-compose.yml up -d
```

Then:

```powershell
docker compose -f .\Deployment\docker-compose.yml run --rm controller
```

No image rebuild is required for normal operation.

## 14. Health Checks

### Detection API

```powershell
Invoke-RestMethod http://localhost:8000/health
```

### Report API

```powershell
Invoke-RestMethod http://localhost:8001/health
```

### List reports

```powershell
Invoke-RestMethod http://localhost:8001/api/reports
```

### Docker status

```powershell
docker compose -f .\Deployment\docker-compose.yml ps
```

## 15. Useful Docker Commands

View all service logs:

```powershell
docker compose -f .\Deployment\docker-compose.yml logs
```

Follow logs:

```powershell
docker compose -f .\Deployment\docker-compose.yml logs -f
```

Detection logs:

```powershell
docker compose -f .\Deployment\docker-compose.yml logs detection
```

Report logs:

```powershell
docker compose -f .\Deployment\docker-compose.yml logs report
```

Dashboard logs:

```powershell
docker compose -f .\Deployment\docker-compose.yml logs dashboard
```

## 16. When to Rebuild Docker Images

Normal start/stop does **not** require rebuilding images.

Rebuild when:

- Application source code used by an image changes.
- Dockerfiles change.
- Python dependencies change.
- Model files baked into an image change.

For example, after changing the controller or `LLMTriage/live_capture.py`:

```powershell
docker build --no-cache -t memsoc-controller:latest -f .\Deployment\controller\Dockerfile .
```

## 17. Important Operational Notes

- Set `MEMSOC_HOST_DATA` again in every new PowerShell session.
- Use dashboard port **8081**, not 8080.
- The controller is a temporary interactive container launched with `run --rm`.
- Generated logs are accessed through the Docker named volume at `/artifacts/generated_logs.jsonl`.
- The latest capture results are stored in `LLMTriage/model_outputs/live_results.jsonl`.
- The controller resets `live_results.jsonl` before a new capture.
- Security reports are stored in `LLMTriage/reports/`.

## 18. Quick Reference

| Action | Command |
|---|---|
| Set dataset path | `$env:MEMSOC_HOST_DATA="..\final_ml_model_v1\data\raw"` |
| Start Docker | `docker compose -f .\Deployment\docker-compose.yml up -d` |
| Check status | `docker compose -f .\Deployment\docker-compose.yml ps` |
| Run MemSOC | `docker compose -f .\Deployment\docker-compose.yml run --rm controller` |
| Temporary stop | `docker compose -f .\Deployment\docker-compose.yml stop` |
| Temporary restart | `docker compose -f .\Deployment\docker-compose.yml start` |
| Complete shutdown | `docker compose -f .\Deployment\docker-compose.yml down` |
| Detection health | `Invoke-RestMethod http://localhost:8000/health` |
| Report health | `Invoke-RestMethod http://localhost:8001/health` |
| Dashboard | `http://localhost:8081` |

## 19. Recommended Daily Workflow

```text
1. Open PowerShell
        ↓
2. Go to MemSOC project root
        ↓
3. Set MEMSOC_HOST_DATA
        ↓
4. docker compose up -d
        ↓
5. docker compose ps
        ↓
6. docker compose run --rm controller
        ↓
7. Enter number of logs
        ↓
8. Select Y for live capture
        ↓
9. Press ENTER for report generation
        ↓
10. Open http://localhost:8081
        ↓
11. Review dashboard/report
        ↓
12. docker compose down
```

This is the standard operating procedure for the current MemSOC Docker deployment.
