# MemSOC -- NF-UNSW-NB15 flow triage pipeline
#
# What is in the image:  code + the two LightGBM pickles.
# What is not:           the NF-UNSW-NB15-v3 CSV. It is multi-GB and cannot be
#                        committed, so it is bind-mounted at /data instead.
#
# Every path is resolved by paths.py from the MEMSOC_* environment variables
# set below, which is why the same code runs unchanged here and on the host.
#
# Build:
#   docker build -t memsoc .
#
# Run (see docker-compose.yml for the ergonomic version):
#   docker run --rm -v "/host/path/to/data:/data:ro" memsoc --paths

# The full image rather than -slim on purpose: it already ships libgomp1
# (LightGBM's OpenMP runtime -- import fails without it) and curl (used by
# the healthcheck below). -slim needs an apt-get layer for both, which is
# the one step in this build that depends on reaching deb.debian.org.
FROM python:3.13

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Dependencies first so code edits do not invalidate the install layer.
COPY requirements-runtime.txt .
RUN pip install --no-cache-dir -r requirements-runtime.txt

# Application code and the model pickles.
COPY paths.py ./
COPY final_ml_model_v1/ ./final_ml_model_v1/
COPY log_generation/ ./log_generation/

# Path layout inside the container.
#   MEMSOC_DATA_DIR     bind-mounted, read-only; paths.py walks it to find
#                       NF-UNSW-NB15-v3.csv wherever it sits under the mount
#   MEMSOC_ARTIFACTS_DIR generated logs, ground truth, stream index + cursor;
#                       mount a volume here to keep them across runs
#   MEMSOC_API_BIND     0.0.0.0 so a published port reaches uvicorn, while
#                       MEMSOC_API_HOST stays 127.0.0.1 for the in-container
#                       client
ENV MEMSOC_ROOT=/app \
    MEMSOC_DATA_DIR=/data \
    MEMSOC_ARTIFACTS_DIR=/artifacts \
    MEMSOC_LOG_DIR=/app/logs \
    MEMSOC_API_HOST=127.0.0.1 \
    MEMSOC_API_BIND=0.0.0.0 \
    MEMSOC_API_PORT=8000 \
    PYTHONPATH=/app:/app/final_ml_model_v1

RUN mkdir -p /artifacts /data /app/logs

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=90s --retries=5 \
    CMD curl -fsS http://127.0.0.1:8000/health || exit 1

# Default: the full demo. Override the arguments for other modes,
# or the entrypoint entirely to serve the API on its own.
ENTRYPOINT ["python", "/app/log_generation/run_pipeline.py"]
CMD ["--flows", "100"]
