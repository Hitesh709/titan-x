"""Application logging configuration.

Configures *structured* logging for both application code (via ``structlog``)
and third-party libraries (via the standard ``logging`` integration). Every line
is rendered as a JSON object by default (one object per line, ideal for log
aggregation), or as a plain console line when ``log_format="console"``.

A ``request_id`` / ``correlation_id`` bound through
:func:`structlog.contextvars.bind_contextvars` is automatically included in
every log line for the surrounding context.
"""
from __future__ import annotations

import logging
import sys
from typing import Any

import structlog
from structlog.types import Processor


def configure_logging(log_level: str = "INFO", log_format: str = "json") -> None:
    """Configure structured logging for the whole process.

    Args:
        log_level: Standard logging level name (``DEBUG``, ``INFO``,
            ``WARNING``, ``ERROR``, ``CRITICAL``).
        log_format: ``"json"`` for machine-readable lines (default, best for
            production aggregation) or ``"console"`` for human-readable output
            (useful in local development).
    """
    level = logging.getLevelName(log_level.upper()) if isinstance(log_level, str) else log_level
    if not isinstance(level, int):
        level = logging.INFO

    use_json = (log_format or "json").lower() != "console"
    renderer: Processor = (
        structlog.processors.JSONRenderer()
        if use_json
        else structlog.dev.ConsoleRenderer(colors=False)
    )

    # Processor chain shared by structlog-native and foreign (stdlib) records.
    shared_pre_chain: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
    ]

    # Native structlog logs are wrapped so the stdlib ProcessorFormatter below
    # can render them; foreign stdlib logs flow through ``foreign_pre_chain``.
    structlog.configure(
        processors=[
            *shared_pre_chain,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Route the standard library logging (uvicorn, sqlalchemy, httpx, ...) through
    # structlog so that all output is uniformly structured.
    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_pre_chain,
        processors=[
            structlog.processors.StackInfoRenderer(),
            structlog.processors.dict_tracebacks,
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)

    # Keep noisy libraries quiet unless we are debugging.
    if level > logging.DEBUG:
        logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
        logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
        logging.getLogger("sqlalchemy.pool").setLevel(logging.WARNING)
        logging.getLogger("httpx").setLevel(logging.WARNING)

    structlog.get_logger(__name__).info(
        "logging_configured",
        format="json" if use_json else "console",
        log_level=log_level.upper(),
    )
