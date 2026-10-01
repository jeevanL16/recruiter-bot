"""Structured logging configuration for Recruiter Bot."""

import logging
import sys


def setup_logging(log_level: str = "INFO") -> None:
    """Configure root logger with a clean, structured format."""
    level = getattr(logging, log_level.upper(), logging.INFO)

    log_format = "[%(asctime)s] [%(levelname)s] [%(name)s] [%(filename)s:%(lineno)d] - %(message)s"

    formatter = logging.Formatter(fmt=log_format, datefmt="%Y-%m-%d %H:%M:%S")

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Avoid duplicate handlers on re-init
    root_logger.handlers = [handler]

    # Silence overly verbose external loggers if needed
    logging.getLogger("uvicorn.access").setLevel(logging.INFO)
