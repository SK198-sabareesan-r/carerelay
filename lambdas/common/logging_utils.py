"""Structured JSON logging helper.

NOTE ON PHI: never pass raw patient identifiers, insurance numbers, or
document contents into log_event. Log only ids, booleans, and rule
names/outcomes. See docs/ARCHITECTURE.md "PHI handling".
"""
import json
import logging
import sys

from . import config

_configured = False


def get_logger(name: str) -> logging.Logger:
    global _configured
    logger = logging.getLogger(name)
    if not _configured:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter("%(message)s"))
        root = logging.getLogger()
        if not root.handlers:
            root.addHandler(handler)
        root.setLevel(getattr(logging, config.LOG_LEVEL, logging.INFO))
        _configured = True
    logger.setLevel(getattr(logging, config.LOG_LEVEL, logging.INFO))
    return logger


def log_event(logger: logging.Logger, level: str, msg: str, **fields) -> None:
    """Emit a single structured log line."""
    payload = {"msg": msg, **fields}
    getattr(logger, level.lower(), logger.info)(json.dumps(payload, default=str))
