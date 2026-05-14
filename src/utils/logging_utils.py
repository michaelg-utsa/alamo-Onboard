"""Centralized structured logging with request_id propagation.

Every log entry is emitted as a JSON line with fields:
    timestamp, level, module, request_id, message

request_id is threaded through each user turn via a ContextVar so that
all components (orchestrator, LLM client, tools, retriever) that log
during a single handle_user_message() call share the same ID.
"""

from __future__ import annotations

import contextvars
import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

_CONFIGURED = False

# Context variable holding the current request ID.
# Defaults to "-" when no request is active.
_request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")


class _JsonFormatter(logging.Formatter):
    """Emit each log record as a single JSON line."""

    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(
                timespec="milliseconds"
            ),
            "level": record.levelname,
            "module": record.name,
            "request_id": _request_id_var.get("-"),
            "message": record.getMessage(),
        }
        if record.exc_info:
            entry["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(entry, ensure_ascii=False)


def setup_logging(level: int = logging.INFO, log_file: Path | None = None) -> None:
    """Configure root logging once with JSON output. Idempotent."""
    global _CONFIGURED
    if _CONFIGURED:
        return

    formatter = _JsonFormatter()

    handlers: list[logging.Handler] = []

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    handlers.append(stream_handler)

    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(formatter)
        handlers.append(file_handler)

    logging.basicConfig(level=level, handlers=handlers, force=True)

    # Quiet chatty third-party loggers
    for noisy in ("urllib3", "httpx", "httpcore", "sentence_transformers"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """Return a named logger, initializing JSON logging on first call."""
    setup_logging()
    return logging.getLogger(name)


def set_request_id(request_id: str) -> None:
    """Bind a request_id to the current execution context.

    Call this once at the start of each handle_user_message() turn.
    All subsequent log calls in the same thread/coroutine will include
    this ID automatically via _request_id_var.
    """
    _request_id_var.set(request_id)


def get_request_id() -> str:
    """Return the current request_id, or '-' if none is set."""
    return _request_id_var.get("-")
