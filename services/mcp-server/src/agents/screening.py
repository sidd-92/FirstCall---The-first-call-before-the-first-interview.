"""Fixed-sequence screening question state machine.

Deliberately no LLM call here -- "which question is next" is derived purely
from how many screening_question messages we've already sent in this
conversation (see src/db.py's `count_messages_by_kind`), never from a model.
Scoring/summarizing the candidate's answers at the end is a separate concern
left to a later agent (per the plan).
"""

from dataclasses import dataclass

HOLDING_MESSAGE = (
    "Thanks for reaching out! Your application is still being reviewed -- "
    "we'll follow up here once you're invited to the next step."
)

UNRECOGNIZED_MESSAGE = (
    "Thanks for the message! We couldn't match this to an application on file -- "
    "please make sure you applied with the email tied to this account, or reach "
    "out via the application email thread. If you have a Discord link code from "
    "your application confirmation, send just that code here to connect."
)

LINKED_MESSAGE = (
    "You're linked! We'll follow up here once there's an update on your application."
)

DM_REDIRECT_MESSAGE = (
    "Check your Discord DMs -- that's where we follow up on applications, "
    "never in this channel."
)

SEQUENCE_COMPLETE_MESSAGE = (
    "Thanks, that's everything for now -- our team will review your responses "
    "and follow up soon."
)

SCREENING_QUESTION_KIND = "screening_question"


@dataclass
class ScreeningTurn:
    reply_text: str
    kind: str | None
    """Tag to store the outbound reply under. `screening_question` entries are
    what `question_index` counts -- anything else (holding/closing messages)
    must use a different tag so it isn't mistaken for a question already asked."""


def next_screening_turn(questions: list[str], question_index: int) -> ScreeningTurn:
    """Given the fixed question list and how many have been asked already,
    return the next thing to say."""
    if question_index < len(questions):
        return ScreeningTurn(reply_text=questions[question_index], kind=SCREENING_QUESTION_KIND)
    return ScreeningTurn(reply_text=SEQUENCE_COMPLETE_MESSAGE, kind="screening_complete_ack")
