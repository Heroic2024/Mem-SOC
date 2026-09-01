FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PIP_NO_CACHE_DIR=1

WORKDIR /app/LLMTriage

RUN pip install --no-cache-dir \
    requests==2.32.3 \
    fastapi==0.115.12 \
    uvicorn==0.44.0

COPY . .

ENV PYTHONPATH=/app

EXPOSE 8001

CMD ["python", "-m", "uvicorn", "report_server:app", "--host", "0.0.0.0", "--port", "8001"]
