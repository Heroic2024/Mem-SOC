"""
Detection ASGI app -- Layer 2, default port 8000.

    python -m uvicorn memsoc.api.app_detection:app --host 0.0.0.0 --port 8000

The lifespan hook warms the InferencePipeline at startup rather than on the
first request, so the container's healthcheck only reports healthy once the
LightGBM pickles are actually loaded. Without this, log_generation could
race a "healthy" detection service that was still unpickling 37MB.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from memsoc.api.routes_detection import get_pipeline, router


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_pipeline()
    yield


app = FastAPI(
    title="MemSOC Detection API",
    description="MemSOC network-flow inference API (Layer 2)",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(router)
