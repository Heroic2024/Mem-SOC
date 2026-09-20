# MemSOC log-generation service -- Layer 1.
#
# Generates the 48-feature NetFlow records and replays them against the
# `detection` service over HTTP (--no-api: it never loads a model itself).
# The dataset (multi-GB NF-UNSW-NB15-v3.csv) is not baked into the image --
# bind-mount it at /data, see deploy/docker-compose.yml.
#
# The model pickles are only ever stat()'d by preflight, never loaded, so
# they are bind-mounted read-only from the host's models/ directory rather
# than duplicating ~37MB into this image.

FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements/logstream.txt ./requirements/logstream.txt
RUN pip install --no-cache-dir -r requirements/logstream.txt

COPY src/ ./src/

ENV MEMSOC_ROOT=/app \
    MEMSOC_DATA_DIR=/data \
    MEMSOC_ARTIFACTS_DIR=/artifacts \
    MEMSOC_MODELS_DIR=/app/models \
    MEMSOC_LOG_DIR=/app/logs \
    MEMSOC_API_HOST=detection \
    MEMSOC_API_PORT=8000 \
    PYTHONPATH=/app/src

RUN mkdir -p /data /artifacts /app/models /app/logs

# Wait for detection to finish loading its models, then run the pipeline.
# CMD's args land after `--` and are re-assembled as "$@" ahead of --no-api.
ENTRYPOINT ["sh", "-c", \
  "python -m memsoc.logstream.wait_for_detection && exec python -m memsoc.logstream.run_pipeline --no-api \"$@\"", \
  "--"]
CMD ["--flows", "100"]
