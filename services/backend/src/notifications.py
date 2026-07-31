"""Agent 2 (ops-facing), application-event half.

Notifies the business owner by email when a new candidate applies. The
"screening completed" half lives in services/mcp-server/src/agents/agent2.py
instead, because that event is only observable there (inside Agent 1's
Discord handler) -- these two processes don't share memory, so each side
sends its own notification for the event it actually witnesses rather than
one calling into the other.

Deliberately NOT on_message-driven and not part of Agent 1's handler: this
module only ever sends, never listens, so it doesn't need to satisfy the
"2 channels, 1 handler" rule.
"""

import os
from functools import lru_cache

from caspian_sdk import CommClient

from src.logging_config import get_logger
from src.models import Business, Candidate, JobPosting

log = get_logger()


@lru_cache(maxsize=1)
def _client() -> CommClient:
    return CommClient(api_key=os.environ.get("CASPIAN_API_KEY"))


@lru_cache(maxsize=1)
def _email_connection_id() -> str:
    result = _client().connect_email()
    return result["connection_id"]


def notify_new_application(
    candidate: Candidate, job_posting: JobPosting, business: Business
) -> None:
    """Best-effort: a failed notification must never fail the candidate's
    application submission, so every error here is caught and logged, not
    raised."""
    notify_log = log.bind(candidate_id=candidate.id, business_id=business.id)

    try:
        if not business.owner_email:
            notify_log.warning(
                "notification_skipped",
                notification_type="new_application",
                reason="no_owner_email",
            )
            return

        connection_id = _email_connection_id()
        _client().initiate(
            connection_id,
            recipient=business.owner_email,
            text=(
                f"New application received: {candidate.name} applied for "
                f"'{job_posting.title}'. Review it in the FirstCall dashboard."
            ),
        )
        notify_log.info("notification_sent", notification_type="new_application")
    except Exception:  # noqa: BLE001 -- best-effort by design, see docstring
        notify_log.warning(
            "notification_failed", notification_type="new_application", exc_info=True
        )
