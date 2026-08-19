from fastapi import FastAPI, HTTPException

from src.inference.inference_pipeline import InferencePipeline
from src.utils.logger import logger


app = FastAPI(
    title="MemSOC API",
    description="MemSOC network-flow inference API",
    version="1.0.0"
)


logger.info("Initializing MemSOC API...")

pipeline = InferencePipeline()

logger.info("MemSOC API initialized successfully.")


@app.get("/")
def root():

    logger.info("Root endpoint accessed.")

    return {
        "status": "running",
        "service": "MemSOC API"
    }


@app.get("/health")
def health():

    logger.info("Health endpoint accessed.")

    return {
        "status": "healthy"
    }


@app.post("/api/logs")
def process_log(log: dict):

    logger.info(
        "Network flow received through /api/logs."
    )

    try:

        result = pipeline.predict(
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

    except Exception as e:

        logger.exception(
            "Inference processing failed."
        )

        raise HTTPException(
            status_code=500,
            detail="Inference processing failed."
        )