# MemSOC interactive controller.
#
# Drives the complete workflow: generate flows -> live capture against the
# detection API -> generate the security report. Run it attached:
#
#   docker compose -f deploy/docker-compose.yml run --rm controller

FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements/controller.txt ./requirements/controller.txt
RUN pip install --no-cache-dir -r requirements/controller.txt

COPY src/ ./src/

ENV MEMSOC_ROOT=/app \
    MEMSOC_DATA_DIR=/data \
    MEMSOC_ARTIFACTS_DIR=/artifacts \
    MEMSOC_MODELS_DIR=/app/models \
    MEMSOC_LOG_DIR=/app/logs \
    MEMSOC_API_HOST=detection \
    MEMSOC_API_PORT=8000 \
    MEMSOC_REPORT_HOST=report \
    MEMSOC_REPORT_PORT=8001 \
    PYTHONPATH=/app/src

RUN mkdir -p /data /artifacts /app/models /app/logs

CMD ["python", "-u", "-m", "memsoc.controller"]
