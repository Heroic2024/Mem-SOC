# MemSOC detection service -- Layer 2, the frozen LightGBM classifier.
#
# Build context is the REPO ROOT (see deploy/docker-compose.yml), so every
# image copies from the same single source tree. There is no per-service
# copy of the code any more.
#
#   docker compose -f deploy/docker-compose.yml build detection

FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# libgomp1 is LightGBM's OpenMP runtime -- import fails without it.
# curl is used by the healthcheck below.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 curl \
    && rm -rf /var/lib/apt/lists/*

# Dependencies first so code edits do not invalidate the install layer.
COPY requirements/detection.txt ./requirements/detection.txt
RUN pip install --no-cache-dir -r requirements/detection.txt

# Application code and the model pickles. models/ is the ONE copy of the
# weights in the repo; it used to be three byte-identical copies.
COPY src/ ./src/
COPY models/ ./models/

ENV MEMSOC_ROOT=/app \
    MEMSOC_MODELS_DIR=/app/models \
    MEMSOC_ARTIFACTS_DIR=/artifacts \
    MEMSOC_LOG_DIR=/app/logs \
    MEMSOC_API_HOST=127.0.0.1 \
    MEMSOC_API_BIND=0.0.0.0 \
    MEMSOC_API_PORT=8000 \
    PYTHONPATH=/app/src

RUN mkdir -p /artifacts /app/logs

EXPOSE 8000

# start-period covers the model load: the app's lifespan hook unpickles
# ~37MB before it will answer, so /health is a true readiness signal.
HEALTHCHECK --interval=15s --timeout=5s --start-period=120s --retries=10 \
    CMD curl -fsS http://127.0.0.1:8000/health || exit 1

CMD ["python", "-m", "uvicorn", "memsoc.api.app_detection:app", \
     "--host", "0.0.0.0", "--port", "8000"]
