import logging
import sys


def setup_logger(name: str = "MemSOC") -> logging.Logger:
    """
    Configure and return a logger for the MemSOC project.

    Parameters
    ----------
    name : str
        Name of the logger.

    Returns
    -------
    logging.Logger
        Configured logger instance.
    """

    logger = logging.getLogger(name)

    # Prevent duplicate handlers
    if logger.hasHandlers():
        return logger

    logger.setLevel(logging.INFO)

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)

    logger.addHandler(console_handler)

    return logger


# Global logger instance
logger = setup_logger()