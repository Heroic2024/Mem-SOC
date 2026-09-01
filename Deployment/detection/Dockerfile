FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-runtime.txt .
RUN pip install --no-cache-dir -r requirements-runtime.txt

COPY paths.py .
COPY final_ml_model_v1/ ./final_ml_model_v1/

ENV MEMSOC_ROOT=/app
ENV MEMSOC_MODELS_DIR=/app/final_ml_model_v1/src/models
ENV MEMSOC_API_HOST=127.0.0.1
ENV MEMSOC_API_BIND=0.0.0.0
ENV MEMSOC_API_PORT=8000
ENV PYTHONPATH=/app:/app/final_ml_model_v1

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "src.api.server:app", "--host", "0.0.0.0", "--port", "8000"]
