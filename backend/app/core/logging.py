import logging
import logging.config
from typing import Any

from app.core.config import settings


LOGGING_CONFIG: dict[str, Any] = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "format": "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        }
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "default",
            "stream": "ext://sys.stdout",
        }
    },
    "root": {"handlers": ["console"], "level": settings.log_level.upper()},
    "loggers": {
        "uvicorn": {"handlers": ["console"], "level": settings.log_level.upper(), "propagate": False},
        "uvicorn.error": {"handlers": ["console"], "level": settings.log_level.upper(), "propagate": False},
        "uvicorn.access": {"handlers": ["console"], "level": settings.log_level.upper(), "propagate": False},
    },
}


def configure_logging() -> None:
    logging.config.dictConfig(LOGGING_CONFIG)
