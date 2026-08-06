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
from datetime import UTC, datetime
from functools import lru_cache

from caspian_sdk import CommClient

from src.logging_config import get_logger
from src.models import Business, Candidate, JobPosting

log = get_logger()

# Single admin address for this hackathon showcase (see routes/admin.py and
# auth.py's require_admin) -- supporting multiple admins is a future
# enhancement, not needed now.
PLATFORM_ADMIN_EMAIL = os.environ.get("PLATFORM_ADMIN_EMAIL", "")


@lru_cache(maxsize=1)
def _client() -> CommClient:
    return CommClient(api_key=os.environ.get("CASPIAN_API_KEY"))


@lru_cache(maxsize=1)
def _email_connection_id() -> str:
    result = _client().connect_email()
    # The connection resource returned by `_connect()` (verified directly
    # against the live gateway) keys the connection's own id as `"id"`, not
    # `"connection_id"` -- there is no `"connection_id"` key on this
    # response at all. Using the wrong key here previously raised a
    # KeyError on every call, silently swallowed by the broad except below.
    return result["id"]


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
        result = _client().initiate(
            connection_id,
            recipient=business.owner_email,
            text=(
                f"New application received: {candidate.name} applied for "
                f"'{job_posting.title}'. Review it in the FirstCall dashboard."
            ),
        )
        notify_log.info(
            "notification_sent", notification_type="new_application", raw_response=result
        )
    except Exception:  # noqa: BLE001 -- best-effort by design, see docstring
        notify_log.warning(
            "notification_failed", notification_type="new_application", exc_info=True
        )


def notify_access_requested(business: Business, requester_email: str | None) -> None:
    """Best-effort: notify the platform admin that a business wants its
    self-service signup reviewed (POST /business/request-access). Same
    CommClient/`initiate()` path as `notify_new_application` above -- not a
    separate ad hoc email integration.

    The body leads with a subject-like summary line rather than relying on
    an actual `Subject:` header: caspian-sdk 0.6.1 gives `initiate()` no way
    to set one at all (verified against the SDK source and the live
    gateway's own OpenAPI schema -- see mcp-server's agent1.py module
    docstring), so every agent-sent email shows as "(no subject)" in Gmail
    regardless. This at least keeps the summary visible in the inbox
    preview line."""
    notify_log = log.bind(business_id=business.id, notification_type="access_requested")

    if not PLATFORM_ADMIN_EMAIL:
        notify_log.warning("notification_skipped", reason="no_platform_admin_email")
        return

    try:
        connection_id = _email_connection_id()
        requested_at = datetime.now(UTC).isoformat()
        result = _client().initiate(
            connection_id,
            recipient=PLATFORM_ADMIN_EMAIL,
            text=(
                f"New access request: {business.name}\n\n"
                f"Business id: {business.id}. "
                f"Requesting user: {requester_email or 'unknown'}. "
                f"Requested at {requested_at}. "
                "Review it in the FirstCall admin panel."
            ),
        )
        notify_log.info("notification_sent", raw_response=result)
    except Exception:  # noqa: BLE001 -- best-effort by design, see docstring
        notify_log.warning("notification_failed", exc_info=True)
