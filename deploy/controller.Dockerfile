FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN pip install --no-cache-dir \
    pandas==2.2.3 \
    numpy==2.2.6 \
    requests==2.32.3

COPY Deployment/controller/controller.py /app/controller.py

COPY Deployment/log_generation/ /app/log_generation/
COPY LLMTriage/ /app/LLMTriage/

ENV MEMSOC_ROOT=/app
ENV MEMSOC_DATA_DIR=/data
ENV MEMSOC_ARTIFACTS_DIR=/artifacts
ENV MEMSOC_API_HOST=detection
ENV MEMSOC_API_PORT=8000
ENV DETECTION_API_URL=http://detection:8000/api/logs
ENV PYTHONPATH=/app:/app/LLMTriage

CMD ["python", "-u", "/app/controller.py"]