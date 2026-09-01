# MemSOC Docker Deployment

This directory contains the Docker deployment configuration for the MemSOC system.

## Architecture

MemSOC is deployed as three Docker services:

```text
                         ┌──────────────────────┐
                         │      Dashboard       │
                         │  React + Nginx :8080 │
                         └──────────┬───────────┘
                                    │
                                    ▼
                         ┌──────────────────────┐
                         │      Report API      │
                         │ FastAPI + Groq :8001 │
                         └──────────┬───────────┘
                                    │
                         Docker network / HTTP
                                    │
                                    ▼
                         ┌──────────────────────┐
                         │    Detection API     │
                         │ LightGBM + FastAPI   │
                         │        :8000         │
                         └──────────────────────┘

Host bind mounts:
  LLMTriage/model_outputs  <->  /app/LLMTriage/model_outputs
  LLMTriage/reports        <->  /app/LLMTriage/reports
```

## Services

| Service | Container | Host Port | Purpose |
|---|---|---:|---|
| detection | `memsoc-detection` | 8000 | ML-based network-flow detection |
| report | `memsoc-report` | 8001 | Stage 4 report generation and API |
| dashboard | `memsoc-dashboard` | 8080 | Web dashboard served by Nginx |

## Deployment layout

```text
Deployment/
├── README.md
├── docker-compose.yml
├── detection/
│   ├── Dockerfile
│   ├── paths.py
│   ├── requirements-runtime.txt
│   └── final_ml_model_v1/
│       └── src/
│           ├── api/
│           ├── alerts/
│           ├── explain/
│           ├── features/
│           ├── inference/
│           ├── models/
│           │   ├── binary_lightgbm.pkl
│           │   └── multiclass_lightgbm.pkl
│           └── utils/
├── report/
│   ├── Dockerfile
│   ├── config.py
│   ├── generate_report.py
│   ├── live_capture.py
│   ├── llm_client.py
│   ├── report_prompt.py
│   ├── report_server.py
│   └── stats_engine.py
└── dashboard/
    ├── Dockerfile
    ├── package.json
    ├── package-lock.json
    ├── vite.config.js
    ├── index.html
    ├── src/
    └── public/
```

## Prerequisites

- Docker Desktop with Linux containers enabled
- Docker Compose
- A valid Groq API key for report generation
- The MemSOC repository and required ML model files

Verify Docker:

```powershell
docker version
docker compose version
```

## Environment configuration

Keep the Groq API key outside Git and outside Docker images.

Create `.env` in the repository root:

```text
GROQ_API_KEY=your_actual_groq_api_key
```

The repository `.gitignore` must contain:

```text
.env
```

Verify the variable without printing its value:

```powershell
if ($env:GROQ_API_KEY) {
    Write-Host "GROQ_API_KEY is set"
} else {
    Write-Host "GROQ_API_KEY is NOT set"
}
```

Compose passes the key to the report service through `${GROQ_API_KEY}`.

## Build images

Build each service using its small deployment directory as the build context:

```powershell
docker build -f .\Deployment\detection\Dockerfile -t memsoc-detection:latest .\Deployment\detection

docker build -f .\Deployment\report\Dockerfile -t memsoc-report:latest .\Deployment\report

docker build -f .\Deployment\dashboard\Dockerfile -t memsoc-dashboard:latest .\Deployment\dashboard
```

This is important: **do not use the repository root as the build context for the detection image**. The repository contains large datasets and generated files. The dedicated `Deployment\detection` context keeps the build context small while still including the model files required by the detection image.

Check images:

```powershell
docker images | Select-String "memsoc"
```

## Start the complete deployment

From the repository root:

```powershell
docker compose -f .\Deployment\docker-compose.yml up -d
```

Check status:

```powershell
docker compose -f .\Deployment\docker-compose.yml ps
```

Expected services:

```text
memsoc-detection   Up
memsoc-report      Up
memsoc-dashboard   Up
```

## Health checks

Detection:

```powershell
Invoke-RestMethod http://localhost:8000/health
```

Expected:

```text
status
------
healthy
```

Report:

```powershell
Invoke-RestMethod http://localhost:8001/health
```

Report list:

```powershell
Invoke-RestMethod http://localhost:8001/api/reports
```

Dashboard:

```text
http://localhost:8080
```

## Container-to-container networking

The report container reaches the detection container by Compose service name:

```text
http://detection:8000/api/logs
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

## Stage 4 capture

`LLMTriage/live_capture.py` runs on the host and sends generated flows to the Detection API. The default host endpoint is:

```text
http://127.0.0.1:8000/api/logs
```

Normal capture:

```powershell
python .\LLMTriage\live_capture.py
```

Continuous capture:

```powershell
python .\LLMTriage\live_capture.py --loop
```

Paced capture:

```powershell
python .\LLMTriage\live_capture.py --interval 1.0
```

Explicitly reset previous captured results:

```powershell
python .\LLMTriage\live_capture.py --reset
```

Results are appended to:

```text
LLMTriage/model_outputs/live_results.jsonl
```

## Report generation

Generate a report from captured results inside the Report container:

```powershell
docker exec memsoc-report python generate_report.py
```

For a small test snapshot:

```powershell
docker exec memsoc-report python generate_report.py --limit 10
```

Limit detailed findings:

```powershell
docker exec memsoc-report python generate_report.py --max-findings 25
```

Reports are written to:

```text
LLMTriage/reports/
```

The Report API exposes them through:

```text
GET /api/reports
GET /api/reports/{name}
```

## End-to-end workflow

```text
Generated network flows
        ↓
LLMTriage/live_capture.py
        ↓
Detection API :8000
        ↓
LightGBM inference
        ↓
LLMTriage/model_outputs/live_results.jsonl
        ↓
Report container
        ↓
Groq analysis
        ↓
LLMTriage/reports/
        ↓
Report API :8001
        ↓
Dashboard :8080
```

## Data and volumes

The large generated dataset is kept outside the Docker images. The Report service uses host bind mounts for persistent Stage 4 output:

```text
LLMTriage/model_outputs -> /app/LLMTriage/model_outputs
LLMTriage/reports       -> /app/LLMTriage/reports
```

The detection image contains the ML models it needs at runtime.

## Stop and restart

Stop and remove the Compose containers/network:

```powershell
docker compose -f .\Deployment\docker-compose.yml down
```

Start again:

```powershell
docker compose -f .\Deployment\docker-compose.yml up -d
```

## Logs

```powershell
docker logs memsoc-detection --tail 100
docker logs memsoc-report --tail 100
docker logs memsoc-dashboard --tail 100
```

Follow Report logs:

```powershell
docker logs -f memsoc-report
```

## Rebuild after changes

Rebuild only the service that changed, then recreate the Compose service:

```powershell
docker build -f .\Deployment\detection\Dockerfile -t memsoc-detection:latest .\Deployment\detection
docker build -f .\Deployment\report\Dockerfile -t memsoc-report:latest .\Deployment\report
docker build -f .\Deployment\dashboard\Dockerfile -t memsoc-dashboard:latest .\Deployment\dashboard

docker compose -f .\Deployment\docker-compose.yml up -d
```

## GitHub and Docker images

The Docker images are local Docker artifacts. They are **not uploaded to GitHub** simply because the repository is pushed.

Git should contain deployment source/configuration such as:

- Dockerfiles
- `docker-compose.yml`
- application source files
- runtime requirements
- required model files intended to be tracked

Do not commit:

- `.env` or real API keys
- Python virtual environments
- `node_modules`
- generated datasets
- runtime logs
- temporary test streams/backups
- Docker image layers

Before committing:

```powershell
git status
git status --ignored
```

## Troubleshooting

### `libgomp.so.1` error

The detection Dockerfile installs `libgomp1`, which is required by LightGBM. Rebuild the detection image if the Dockerfile was changed.

### Docker context/build-context problem

Build from the dedicated deployment directory as shown above. This prevents the multi-GB repository dataset from being sent to Docker during the detection build.

### Container name conflict

Inspect old containers:

```powershell
docker ps -a
```

Remove obsolete test containers:

```powershell
docker rm -f memsoc-detection-test memsoc-report-test memsoc-dashboard-test
```

### Dashboard does not show reports

Check the Report API:

```powershell
Invoke-RestMethod http://localhost:8001/api/reports
```

Check the shared files:

```powershell
docker exec memsoc-report sh -c "ls -lh /app/LLMTriage/model_outputs && echo '--- reports ---' && ls -lh /app/LLMTriage/reports"
```

## Deployment validation

The deployment has been validated with:

- Detection health check
- Real ML inference through the Dockerized Detection API
- Report health check
- Report-to-Detection Docker networking
- Shared `model_outputs` bind mount
- Shared `reports` bind mount
- Groq report generation from inside the Report container
- Dashboard served by Nginx
- Dashboard retrieving a newly generated report through the Report API
- End-to-end 10-flow capture test

A successful deployment should expose the three services on ports **8000, 8001, and 8080** and allow a newly generated report to appear in the dashboard.

## Security note

Never commit a real Groq API key. Keep secrets in the local `.env` file or another runtime secret mechanism, and keep `.env` excluded by `.gitignore`.
