import logging
import os
import sys

from memsoc import paths


# Was "logs" relative to the CWD, which scattered log files into whichever
# directory the process happened to start in.
LOG_DIR = paths.LOG_DIR

os.makedirs(
    LOG_DIR,
    exist_ok=True
)


def create_logger(
    name,
    log_file
):

    logger = logging.getLogger(
        name
    )

    logger.setLevel(
        logging.INFO
    )
    logger.propagate = False

    # Prevent duplicate handlers
    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Console
    console_handler = logging.StreamHandler(
        sys.stdout
    )

    console_handler.setFormatter(
        formatter
    )

    # File
    file_handler = logging.FileHandler(
        os.path.join(
            LOG_DIR,
            log_file
        ),
        encoding="utf-8"
    )

    file_handler.setFormatter(
        formatter
    )

    logger.addHandler(
        console_handler
    )

    logger.addHandler(
        file_handler
    )

    return logger


# General application logger
logger = create_logger(
    "MemSOC",
    "application.log"
)


# Inference-specific logger
inference_logger = create_logger(
    "MemSOC.inference",
    "inference.log"
)


# Alert-specific logger
alert_logger = create_logger(
    "MemSOC.alerts",
    "alerts.log"
)