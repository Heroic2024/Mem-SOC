# MemSOC log-generation container.
#
# Generates the 48-feature NetFlow records used throughout the project and
# replays them against the `detection` service's API (--no-api: this
# container never loads a model itself). The dataset (multi-GB
# NF-UNSW-NB15-v3.csv) is not baked into the image -- bind-mount it at
# /data (see ../docker-compose.yml). The model pickles are only ever
# stat()'d by preflight, never loaded, so they are bind-mounted read-only
# from detection's own copy instead of duplicating ~37MB into this image.

FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements-runtime.txt .
RUN pip install --no-cache-dir -r requirements-runtime.txt

COPY paths.py .
COPY wait_for_detection.py .
COPY log_generation/ ./log_generation/

ENV MEMSOC_ROOT=/app
ENV MEMSOC_DATA_DIR=/data
ENV MEMSOC_ARTIFACTS_DIR=/artifacts
ENV MEMSOC_MODELS_DIR=/app/final_ml_model_v1/src/models
ENV MEMSOC_API_HOST=detection
ENV MEMSOC_API_PORT=8000
ENV PYTHONPATH=/app

RUN mkdir -p /data /artifacts /app/final_ml_model_v1/src/models

# Wait for detection to finish loading its models, then run the pipeline.
# CMD's args land after `--` and are re-assembled as "$@" ahead of --no-api.
ENTRYPOINT ["sh", "-c", "python wait_for_detection.py && exec python log_generation/run_pipeline.py --no-api \"$@\"", "--"]
CMD ["--flows", "100"]
