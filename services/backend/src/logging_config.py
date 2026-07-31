"""structlog setup for the backend service.

Logging policy (matches services/mcp-server):
- Structured JSON to stdout only (container-friendly, no file handlers).
- Every log call should thread a `correlation_id` (and/or `conversation_id`,
  `business_id`) through `bind()` or as a kwarg so logs for a single
  request/conversation can be joined downstream.
- Never log message content or other PII directly -- log identifiers
  (business_id, candidate_id, conversation_id) instead.
- This is operational logging only -- the append-only business audit trail
  (who did what to which candidate) lives in the `AuditLogEntry` table, not
  in these logs.
"""

import logging
import sys

import structlog


def configure_logging(level: int = logging.INFO) -> None:
    """Configure structlog to emit JSON-formatted logs to stdout."""
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )


def get_logger(**initial_values):
    """Return a structlog logger, optionally bound with initial context.

    Example (structural only -- do not bind raw PII here):
        log = get_logger(business_id=business_id)
        log.info("candidate_created", candidate_id=candidate_id)
    """
    return structlog.get_logger().bind(**initial_values)
