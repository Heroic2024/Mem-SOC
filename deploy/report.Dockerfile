# MemSOC report service -- Layer 4, read-only report API.
#
# Serves the JSON that generate_report.py already wrote. It loads no model
# and reads no dataset, which is why it installs neither.

FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements/triage.txt ./requirements/triage.txt
RUN pip install --no-cache-dir -r requirements/triage.txt

COPY src/ ./src/

ENV MEMSOC_ROOT=/app \
    MEMSOC_ARTIFACTS_DIR=/artifacts \
    MEMSOC_LOG_DIR=/app/logs \
    MEMSOC_REPORT_PORT=8001 \
    PYTHONPATH=/app/src

RUN mkdir -p /artifacts /app/logs

EXPOSE 8001

HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=5 \
    CMD curl -fsS http://127.0.0.1:8001/health || exit 1

CMD ["python", "-m", "uvicorn", "memsoc.api.app_reports:app", \
     "--host", "0.0.0.0", "--port", "8001"]
