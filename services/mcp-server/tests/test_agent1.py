"""Tests for Agent 1's single on_message handler (src/agents/agent1.py).

caspian-sdk 0.6.1 ships no offline fake providers (no fake-email/fake-discord
test utilities -- confirmed by inspecting the installed package: the only
"test" surface is `CommClient.test_email`, which sends a real email through
the hosted gateway). So instead of a fake gateway, these tests construct the
SDK's real `Message` dataclass directly and pass a minimal hand-rolled fake
`_client` (just `.reply()`, which is all `Message.reply()` delegates to) --
this exercises Agent 1's actual logic with zero network calls.
"""

from dataclasses import dataclass, field

from caspian_sdk import Message

from src.agents import agent1
from tests.conftest import (
    seed_business,
    seed_candidate,
    seed_job_posting,
    seed_pipeline_stage,
)

FAQ_JSON = (
    '{"faq": [{"question": "What is the salary range?", '
    '"answer": "$20-24/hr depending on experience."}], '
    '"screening_questions": ['
    '"Can you tell me a bit about your relevant experience?", '
    '"What are your salary expectations?"]}'
)


@dataclass
class FakeClient:
    """Stands in for CommClient: only .reply() is exercised, since
    Message.reply() forwards straight to it."""

    replies: list[dict] = field(default_factory=list)

    def reply(self, message_id, text=None, html=None, blocks=None, media=None):
        self.replies.append({"message_id": message_id, "text": text})
        return {"id": "reply-1"}


def make_message(**overrides) -> Message:
    defaults = {
        'id': "msg-1",
        'conversation_id': "ext-conv-1",
        'connection_id': "conn-1",
        'customer_id': "cust-1",
        'agent_id': "agent-1",
        'channel': "email",
        'sender': None,
        'subject': None,
        'text': None,
        'html': None,
        '_client': FakeClient(),
    }
    defaults.update(overrides)
    return Message(**defaults)


def setup_job(db):
    seed_business(db)
    seed_job_posting(db, faq_json=FAQ_JSON)


# -- Email ---------------------------------------------------------------


def test_email_answers_from_fixed_faq_without_llm(db, monkeypatch):
    setup_job(db)
    seed_candidate(db, email="jamie@example.com")

    def fail_if_called(*args, **kwargs):
        raise AssertionError("should not fall back to the LLM for a matched FAQ entry")

    monkeypatch.setattr(agent1.faq, "ask_faq_fallback", fail_if_called)

    message = make_message(
        channel="email",
        subject="Question [JOB-1]",
        sender={"email": "jamie@example.com"},
        text="What is the salary range?",
    )
    agent1.handle_message(message)

    assert len(message._client.replies) == 1
    assert "20-24" in message._client.replies[0]["text"]


def test_email_falls_back_to_llm_for_uncovered_question(db, monkeypatch):
    setup_job(db)
    seed_candidate(db, email="jamie@example.com")

    monkeypatch.setattr(
        agent1.faq, "ask_faq_fallback", lambda *a, **k: "We're flexible on start date."
    )

    message = make_message(
        channel="email",
        subject="Question [JOB-1]",
        sender={"email": "jamie@example.com"},
        text="Can I start next month?",
    )
    agent1.handle_message(message)

    assert message._client.replies[0]["text"] == "We're flexible on start date."


def test_email_missing_job_tag_gets_generic_reply(db):
    message = make_message(channel="email", subject="Hello there", sender={"email": "a@b.com"})
    agent1.handle_message(message)

    assert len(message._client.replies) == 1
    assert "couldn't tell which role" in message._client.replies[0]["text"]


def test_email_unknown_candidate_gets_generic_reply(db):
    setup_job(db)

    message = make_message(
        channel="email",
        subject="Question [JOB-1]",
        sender={"email": "stranger@example.com"},
        text="What is the salary?",
    )
    agent1.handle_message(message)

    assert "couldn't match this email" in message._client.replies[0]["text"]


# -- Discord ---------------------------------------------------------------


def test_discord_holding_message_when_screening_not_assigned(db):
    setup_job(db)
    seed_candidate(db, discord_user_id="disc-1")
    seed_pipeline_stage(db, stage="applied")

    message = make_message(
        channel="discord", sender={"id": "disc-1"}, text="hi", conversation_id="ext-conv-discord-1"
    )
    agent1.handle_message(message)

    assert "still being reviewed" in message._client.replies[0]["text"]


def test_discord_asks_first_screening_question_once_assigned(db):
    setup_job(db)
    seed_candidate(db, discord_user_id="disc-1")
    seed_pipeline_stage(db, stage="screening_assigned")

    message = make_message(
        channel="discord", sender={"id": "disc-1"}, text="hi", conversation_id="ext-conv-discord-1"
    )
    agent1.handle_message(message)

    assert message._client.replies[0]["text"] == (
        "Can you tell me a bit about your relevant experience?"
    )


def test_discord_asks_second_question_on_next_turn(db):
    setup_job(db)
    seed_candidate(db, discord_user_id="disc-1")
    seed_pipeline_stage(db, stage="screening_assigned")

    conv_id = "ext-conv-discord-1"
    agent1.handle_message(
        make_message(channel="discord", sender={"id": "disc-1"}, text="hi", conversation_id=conv_id)
    )
    second = make_message(
        channel="discord",
        sender={"id": "disc-1"},
        text="I worked at a cafe for 2 years.",
        conversation_id=conv_id,
    )
    agent1.handle_message(second)

    assert second._client.replies[0]["text"] == "What are your salary expectations?"


def test_discord_sends_closing_message_after_last_question(db, monkeypatch):
    setup_job(db)
    seed_candidate(db, discord_user_id="disc-1")
    seed_pipeline_stage(db, stage="screening_assigned")

    notified = []
    monkeypatch.setattr(
        agent1.agent2,
        "notify_screening_completed",
        lambda client, candidate_id: notified.append(candidate_id),
    )

    conv_id = "ext-conv-discord-1"
    texts = ["hi", "answer one", "answer two"]
    last_message = None
    for text in texts:
        last_message = make_message(
            channel="discord", sender={"id": "disc-1"}, text=text, conversation_id=conv_id
        )
        agent1.handle_message(last_message)

    assert "that's everything for now" in last_message._client.replies[0]["text"]
    assert db.get_pipeline_stage(1) == "screening_completed"
    assert notified == [1]


def test_discord_unresolved_candidate_gets_generic_reply(db):
    message = make_message(
        channel="discord", sender={"id": "unknown-disc-user"}, text="hi", conversation_id="ext-x"
    )
    agent1.handle_message(message)

    assert "couldn't match this" in message._client.replies[0]["text"]


def test_unhandled_channel_does_not_raise(db):
    message = make_message(channel="slack", text="hi")
    agent1.handle_message(message)  # should just log a warning, not raise
