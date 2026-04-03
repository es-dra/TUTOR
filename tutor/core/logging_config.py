"""Logging configuration for TutorClaw."""

from __future__ import annotations

import logging
import logging.config
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

try:
    from pythonjsonlogger import jsonlogger
    HAS_JSON_LOGGER = True
except ImportError:
    HAS_JSON_LOGGER = False

logger = logging.getLogger(__name__)


def setup_logging(
    level: str = "INFO",
    json_format: bool = False,
    log_file: str | None = None,
) -> None:
    """
    Setup logging configuration for TutorClaw.

    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        json_format: If True, use JSON format for logs
        log_file: Optional path to log file. If provided, logs will be written to file.
    """
    log_level = getattr(logging, level.upper(), logging.INFO)

    if json_format and HAS_JSON_LOGGER:
        formatter = jsonlogger.JsonFormatter(
            "%(asctime)s %(name)s %(levelname)s %(message)s",
            timestamp=True,
        )
    elif json_format:
        # Manual JSON formatting if python-json-logger not available
        formatter = ManualJsonFormatter()
    else:
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    handlers: Dict[str, Dict[str, Any]] = {
        "console": {
            "class": "logging.StreamHandler",
            "level": log_level,
            "formatter": "default",
            "stream": "ext://sys.stdout",
        },
    }

    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handlers["file"] = {
            "class": "logging.handlers.RotatingFileHandler",
            "level": log_level,
            "formatter": "default",
            "filename": str(log_path),
            "maxBytes": 10 * 1024 * 1024,  # 10MB
            "backupCount": 5,
        }

    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "default": {
                    "()": "lambda: formatter",
                },
            },
            "handlers": handlers,
            "root": {
                "level": log_level,
                "handlers": list(handlers.keys()),
            },
        },
    )


class ManualJsonFormatter(logging.Formatter):
    """Manual JSON formatter when python-json-logger is not available."""

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON string."""
        log_obj: Dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)

        import json

        return json.dumps(log_obj)


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance with the specified name.

    Args:
        name: Logger name (typically __name__)

    Returns:
        Logger instance
    """
    return logging.getLogger(name)
