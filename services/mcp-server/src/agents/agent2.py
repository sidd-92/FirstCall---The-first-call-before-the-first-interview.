"""Agent 2 (ops-facing): notifies the business owner of pipeline events.

Deliberately NOT on_message-driven -- unlike Agent 1, this agent only ever
sends notifications, so it doesn't need (and shouldn't share) an inbound
handler. It's just a plain function, called directly from the code that
observes the event:

- screening completed: called from Agent 1's Discord handler
  (src/agents/agent1.py), the moment the fixed question sequence finishes.
- new candidate applies: that event happens in a different process
  entirely (services/backend's apply endpoint), so it has its own minimal
  sender instead -- see services/backend/src/notifications.py.
"""

from functools import lru_cache

from caspian_sdk import CommClient

from src import db
from src.logging_config import get_logger

log = get_logger()


@lru_cache(maxsize=1)
def _email_connection_id(client: CommClient) -> str:
    result = client.connect_email()
    # The connection resource returned by `_connect()` (verified directly
    # against the live gateway) keys the connection's own id as `"id"`, not
    # `"connection_id"` -- there is no `"connection_id"` key on this
    # response at all. Using the wrong key here previously raised a
    # KeyError on every call, silently swallowed by the broad except below.
    return result["id"]


def notify_screening_completed(client: CommClient, candidate_id: int) -> None:
    """Best-effort: a failed notification must never break Agent 1's reply
    to the candidate, so every error here is caught and logged, not raised."""
    notify_log = log.bind(candidate_id=candidate_id, notification_type="screening_completed")

    candidate = db.get_candidate(candidate_id)
    if candidate is None:
        notify_log.warning("notification_skipped", reason="candidate_not_found")
        return

    business = db.get_business(candidate["business_id"])
    if business is None or not business["owner_email"]:
        notify_log.warning("notification_skipped", reason="no_owner_email")
        return

    try:
        connection_id = _email_connection_id(client)
        result = client.initiate(
            connection_id,
            recipient=business["owner_email"],
            text=(
                f"{candidate['name']} has completed the screening questions. "
                "Review the transcript and screen with AI in the FirstCall dashboard."
            ),
        )
        notify_log.info("notification_sent", raw_response=result)
    except Exception:  # noqa: BLE001 -- best-effort by design, see docstring
        notify_log.warning("notification_failed", exc_info=True)
