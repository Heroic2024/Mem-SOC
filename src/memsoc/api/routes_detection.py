"""
Layer 2 detection routes -- GET /, GET /health, POST /api/logs.

Was final_ml_model_v1/src/api/server.py. The route bodies are unchanged;
what moved is where they live and how the pipeline is obtained. The
pipeline used to be constructed at import time as a module global, which
meant importing this module for any reason -- a test, a docs build --
loaded 37MB of pickles. It is now built once on first use by
`get_pipeline()`, and the app's lifespan hook warms it at startup so the
first real request is not the one that pays for the load.
"""

from fastapi import APIRouter, HTTPException

from memsoc.api import schemas
from memsoc.detection.inference.inference_pipeline import InferencePipeline
from memsoc.detection.utils.logger import logger

router = APIRouter()

_pipeline = None


def get_pipeline() -> InferencePipeline:
    """The process-wide InferencePipeline, built on first use."""

    global _pipeline

    if _pipeline is None:
        logger.info("Initializing MemSOC detection pipeline...")
        _pipeline = InferencePipeline()
        logger.info("MemSOC detection pipeline initialized successfully.")

    return _pipeline


@router.get("/", response_model=schemas.Root)
def root():

    logger.info("Root endpoint accessed.")

    return {
        "status": "running",
        "service": "MemSOC API"
    }


@router.get("/health", response_model=schemas.DetectionHealth)
def health():

    logger.info("Health endpoint accessed.")

    return {
        "status": "healthy"
    }


@router.post("/api/logs")
def process_log(log: dict):

    logger.info(
        "Network flow received through /api/logs."
    )

    try:

        result = get_pipeline().predict(
            log
        )

        logger.info(
            "Network flow processed successfully."
        )

        return result

    except ValueError as e:

        logger.warning(
            f"Input validation failed: {e}"
        )

        raise HTTPException(
            status_code=400,
            detail=str(e)
        )

    except Exception:

        logger.exception(
            "Inference processing failed."
        )

        raise HTTPException(
            status_code=500,
            detail="Inference processing failed."
        )
