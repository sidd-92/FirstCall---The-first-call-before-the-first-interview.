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

import pytest
from caspian_sdk import Message

from src.agents import agent1
from tests.conftest import (
    seed_business,
    seed_candidate,
    seed_conversation,
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


@pytest.fixture(autouse=True)
def _reset_discord_module_state():
    """`agent1._discord_connection` is a plain module-level dict (see
    agent1.py) -- reset around every test so state from one test can never
    leak into the next."""
    agent1._discord_connection["id"] = None
    yield
    agent1._discord_connection["id"] = None


@dataclass
class FakeClient:
    """Stands in for CommClient: `.reply()`, `.initiate()`, `.send_message()`,
    and `.list_messages()` are exercised -- everything Agent 1's Discord flow
    (including the DM-invite path and chat_type-based DM detection) actually
    calls.

    `initiate_response` lets tests control whether `initiate()` "confirms" a
    DM (a dict with a `conversation_id`/`id` key -- the default) or leaves it
    unconfirmed (e.g. `{}` or a dict with neither key) -- this is now purely
    a best-effort delivery nicety in agent1.py and no longer determines
    `is_dm` (see `conversation_messages` below, which does).

    `conversation_messages` stands in for the real gateway's
    `list_messages(conversation_id)` response (verified live against the
    actual gateway -- see agent1.py's module docstring): a dict keyed by
    conversation id, each value a list of `{"id": ..., "chat_type": ...}`
    dicts, mirroring the real response shape. Defaults to empty, i.e. the
    fake gateway confirms nothing as a DM unless a test explicitly says so
    -- matching agent1.py's fail-closed default.

    `list_messages_error`, if set, makes `list_messages()` raise instead of
    returning -- simulates a gateway lookup failure/timeout."""

    replies: list[dict] = field(default_factory=list)
    initiates: list[dict] = field(default_factory=list)
    sent_messages: list[dict] = field(default_factory=list)
    initiate_response: dict = field(default_factory=lambda: {"id": "conv-cold-1"})
    conversation_messages: dict[str, list[dict]] = field(default_factory=dict)
    list_messages_error: Exception | None = None
    list_messages_calls: list[str] = field(default_factory=list)

    def reply(self, message_id, text=None, html=None, blocks=None, media=None):
        self.replies.append({"message_id": message_id, "text": text})
        return {"id": "reply-1"}

    def initiate(self, connection_id, recipient=None, text=None):
        self.initiates.append(
            {"connection_id": connection_id, "recipient": recipient, "text": text}
        )
        return self.initiate_response

    def send_message(self, conversation_id, text=None, html=None, blocks=None, media=None):
        self.sent_messages.append({"conversation_id": conversation_id, "text": text})
        return {"id": "msg-out-1"}

    def list_messages(self, conversation_id):
        self.list_messages_calls.append(conversation_id)
        if self.list_messages_error is not None:
            raise self.list_messages_error
        return self.conversation_messages.get(conversation_id, [])


def dm_messages(*message_ids: str) -> list[dict]:
    """Builds a fake `list_messages()` response confirming each id as a DM
    (`chat_type: "dm"`), mirroring the real gateway's response shape."""
    return [{"id": message_id, "chat_type": "dm"} for message_id in message_ids]


def make_message(**overrides) -> Message:
    defaults = {
        "id": "msg-1",
        "conversation_id": "ext-conv-1",
        "connection_id": "conn-1",
        "customer_id": "cust-1",
        "agent_id": "agent-1",
        "channel": "email",
        "sender": None,
        "subject": None,
        "text": None,
        "html": None,
        "_client": FakeClient(),
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
    message = make_message(
        channel="email", subject="Hello there", sender={"email": "a@b.com"}
    )
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
        channel="discord",
        sender={"address": "disc-1"},
        text="hi",
        conversation_id="ext-conv-discord-1",
    )
    agent1.handle_message(message)

    assert "still being reviewed" in message._client.replies[0]["text"]


def test_discord_asks_first_screening_question_once_assigned(db):
    """`is_dm` is now determined by looking up THIS message's `chat_type`
    via `list_messages()` (see agent1._is_dm_message), not by a pre-seeded
    DB row -- the fake client's `conversation_messages` stands in for the
    gateway confirming `chat_type == "dm"` for this exact message id."""
    setup_job(db)
    seed_candidate(db, discord_user_id="disc-1")
    seed_pipeline_stage(db, stage="screening_assigned")

    client = FakeClient(conversation_messages={"dm-conv-1": dm_messages("msg-1")})
    message = make_message(
        channel="discord",
        sender={"address": "disc-1"},
        text="hi",
        conversation_id="dm-conv-1",
        _client=client,
    )
    agent1.handle_message(message)

    assert client.list_messages_calls == ["dm-conv-1"]
    assert message._client.replies[0]["text"] == (
        "Can you tell me a bit about your relevant experience?"
    )


def test_discord_asks_second_question_on_next_turn(db):
    setup_job(db)
    seed_candidate(db, discord_user_id="disc-1")
    seed_pipeline_stage(db, stage="screening_assigned")

    conv_id = "dm-conv-1"
    # Same conversation, two distinct messages -- each turn's chat_type is
    # looked up fresh (see agent1.py's module docstring: never cached or
    # reused from an earlier message), so both ids must be confirmed here.
    client = FakeClient(conversation_messages={conv_id: dm_messages("msg-1", "msg-2")})
    agent1.handle_message(
        make_message(
            channel="discord",
            sender={"address": "disc-1"},
            text="hi",
            conversation_id=conv_id,
            id="msg-1",
            _client=client,
        )
    )
    second = make_message(
        channel="discord",
        sender={"address": "disc-1"},
        text="I worked at a cafe for 2 years.",
        conversation_id=conv_id,
        id="msg-2",
        _client=client,
    )
    agent1.handle_message(second)

    assert second._client.replies[-1]["text"] == "What are your salary expectations?"


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

    conv_id = "dm-conv-1"
    ids = ["msg-1", "msg-2", "msg-3"]
    client = FakeClient(conversation_messages={conv_id: dm_messages(*ids)})
    texts = ["hi", "answer one", "answer two"]
    last_message = None
    for message_id, text in zip(ids, texts):
        last_message = make_message(
            channel="discord",
            sender={"address": "disc-1"},
            text=text,
            conversation_id=conv_id,
            id=message_id,
            _client=client,
        )
        agent1.handle_message(last_message)

    assert "that's everything for now" in last_message._client.replies[-1]["text"]
    assert db.get_pipeline_stage(1) == "screening_completed"
    assert notified == [1]


def test_discord_unresolved_candidate_gets_generic_reply(db):
    message = make_message(
        channel="discord",
        sender={"address": "unknown-disc-user"},
        text="hi",
        conversation_id="ext-x",
    )
    agent1.handle_message(message)

    assert "couldn't match this" in message._client.replies[0]["text"]


def test_discord_valid_link_code_links_candidate(db):
    setup_job(db)
    seed_candidate(db, discord_link_code="ABC123")
    seed_pipeline_stage(db, stage="applied")

    message = make_message(
        channel="discord",
        sender={"address": "disc-99"},
        text="ABC123",
        conversation_id="ext-conv-link-1",
    )
    agent1.handle_message(message)

    assert "You're linked" in message._client.replies[0]["text"]
    candidate = db.find_candidate_by_discord_user_id("disc-99")
    assert candidate is not None
    assert candidate["id"] == 1


def test_discord_public_message_during_active_screening_is_redirected_not_answered(db):
    """The core privacy fix: a candidate's Discord identity gets linked (and
    resolved on later messages) via whatever channel they happen to type in
    -- historically that channel could be a shared/public one. Once
    screening is assigned, a message on that same non-DM conversation must
    NEVER receive screening question/answer content -- only a generic
    DM-redirect. (Without `_discord_connection["id"]` configured here,
    linking's DM-invite attempt is a no-op -- see
    test_discord_linking_opens_a_dm_invite_when_configured for that half.)
    """
    setup_job(db)
    seed_candidate(db, discord_link_code="ABC123")
    seed_pipeline_stage(db, stage="screening_assigned")

    conv_id = "ext-conv-link-2"
    agent1.handle_message(
        make_message(
            channel="discord",
            sender={"address": "disc-99"},
            text="ABC123",
            conversation_id=conv_id,
        )
    )
    second = make_message(
        channel="discord",
        sender={"address": "disc-99"},
        text="hi again",
        conversation_id=conv_id,
    )
    agent1.handle_message(second)

    reply_text = second._client.replies[0]["text"]
    assert reply_text == agent1.screening.DM_REDIRECT_MESSAGE
    assert "experience" not in reply_text.lower()
    assert "salary" not in reply_text.lower()


def test_discord_linking_opens_a_dm_invite_when_configured(db):
    """When a Discord connection is available (set by `register()` at
    startup), linking must immediately try to open a DM -- the earliest
    point this code can act, since caspian-sdk has no join-time hook (see
    module docstring). This is purely a best-effort delivery nicety now --
    it does NOT determine `is_dm` for anything (see
    `test_discord_reply_with_confirmed_chat_type_gets_real_screening_content`
    and `test_discord_linking_message_itself_can_be_confirmed_as_dm` for
    what does)."""
    setup_job(db)
    seed_candidate(db, discord_link_code="ABC123")
    agent1._discord_connection["id"] = "conn-discord-1"

    message = make_message(
        channel="discord",
        sender={"address": "disc-99"},
        text="ABC123",
        conversation_id="ext-conv-link-1",
    )
    agent1.handle_message(message)

    assert len(message._client.initiates) == 1
    assert message._client.initiates[0]["connection_id"] == "conn-discord-1"
    assert message._client.initiates[0]["recipient"] == "disc-99"
    # No list_messages() confirmation was configured on this client -- fails
    # closed, same as any other unconfirmed message.
    assert db.find_discord_dm_conversation(1) is None


def test_discord_linking_message_itself_can_be_confirmed_as_dm(db):
    """If the gateway's `list_messages()` confirms `chat_type == "dm"` for
    the very first (linking) message, it's recorded as the candidate's DM
    immediately -- `is_dm` comes from the chat_type lookup, not from
    `initiate()`."""
    setup_job(db)
    seed_candidate(db, discord_link_code="ABC123")

    client = FakeClient(conversation_messages={"ext-conv-link-1": dm_messages("msg-1")})
    message = make_message(
        channel="discord",
        sender={"address": "disc-99"},
        text="ABC123",
        conversation_id="ext-conv-link-1",
        _client=client,
    )
    agent1.handle_message(message)

    dm_conversation = db.find_discord_dm_conversation(1)
    assert dm_conversation is not None
    assert dm_conversation["external_conversation_id"] == "ext-conv-link-1"


def test_discord_reply_with_confirmed_chat_type_gets_real_screening_content(db):
    """The gateway's own `chat_type` field (fetched fresh via
    `list_messages()` for THIS message) is the sole source of truth for
    `is_dm` -- when it positively confirms "dm", the message is safe for
    real screening content."""
    setup_job(db)
    seed_candidate(db, discord_link_code="ABC123")
    seed_pipeline_stage(db, stage="screening_assigned")
    agent1._discord_connection["id"] = "conn-discord-1"

    link_client = FakeClient()
    agent1.handle_message(
        make_message(
            channel="discord",
            sender={"address": "disc-99"},
            text="ABC123",
            conversation_id="ext-conv-link-1",
            _client=link_client,
        )
    )

    dm_client = FakeClient(conversation_messages={"conv-real-dm": dm_messages("msg-1")})
    dm_reply = make_message(
        channel="discord",
        sender={"address": "disc-99"},
        text="hi again",
        conversation_id="conv-real-dm",
        _client=dm_client,
    )
    agent1.handle_message(dm_reply)

    assert dm_client.list_messages_calls == ["conv-real-dm"]
    assert dm_reply._client.replies[0]["text"] == (
        "Can you tell me a bit about your relevant experience?"
    )


def test_discord_repeat_message_after_linking_with_failed_lookup_is_never_trusted(db):
    """Regression test for the live bug: a candidate's first message (their
    link code) was correctly recognized, but their SECOND message in the
    exact same DM thread got the generic redirect because nothing had ever
    positively confirmed it as a DM. Reproduces that shape here: linking
    succeeds, then a later message on the same conversation has its
    `list_messages()` lookup fail outright (simulating a gateway
    error/timeout) -- fail-closed means it still gets the redirect, not real
    screening content, never a crash."""
    setup_job(db)
    seed_candidate(db, discord_link_code="ABC123")
    seed_pipeline_stage(db, stage="screening_assigned")
    agent1._discord_connection["id"] = "conn-discord-1"

    conv_id = "conv-real-dm"
    agent1.handle_message(
        make_message(
            channel="discord",
            sender={"address": "disc-99"},
            text="ABC123",
            conversation_id="ext-conv-link-1",
            _client=FakeClient(),
        )
    )

    failing_client = FakeClient(list_messages_error=RuntimeError("gateway timeout"))
    second = make_message(
        channel="discord",
        sender={"address": "disc-99"},
        text="Any update?",
        conversation_id=conv_id,
        _client=failing_client,
    )
    agent1.handle_message(second)

    reply_text = second._client.replies[0]["text"]
    assert reply_text == agent1.screening.DM_REDIRECT_MESSAGE
    assert "experience" not in reply_text.lower()


@pytest.mark.parametrize(
    "conversation_messages",
    [
        pytest.param({}, id="message_not_found_in_response"),
        pytest.param(
            {"conv-real-dm": [{"id": "msg-1", "chat_type": "channel"}]}, id="non_dm_chat_type"
        ),
        pytest.param({"conv-real-dm": [{"id": "msg-1", "chat_type": None}]}, id="null_chat_type"),
        pytest.param({"conv-real-dm": "not-a-list"}, id="malformed_response"),
    ],
)
def test_discord_reply_with_non_dm_chat_type_is_never_trusted(db, conversation_messages):
    """Anything other than a positively-returned `chat_type == "dm"` --
    including the message simply not appearing in the response, a
    non-"dm"/null chat_type, or a malformed response shape -- fails closed
    exactly like a lookup that raises."""
    setup_job(db)
    seed_candidate(db, discord_link_code="ABC123")
    seed_pipeline_stage(db, stage="screening_assigned")
    agent1._discord_connection["id"] = "conn-discord-1"

    agent1.handle_message(
        make_message(
            channel="discord",
            sender={"address": "disc-99"},
            text="ABC123",
            conversation_id="ext-conv-link-1",
            _client=FakeClient(),
        )
    )

    client = FakeClient(conversation_messages=conversation_messages)
    second = make_message(
        channel="discord",
        sender={"address": "disc-99"},
        text="Any update?",
        conversation_id="conv-real-dm",
        _client=client,
    )
    agent1.handle_message(second)

    assert second._client.replies[0]["text"] == agent1.screening.DM_REDIRECT_MESSAGE


def test_discord_dm_invite_with_unconfirmable_response_does_not_crash(db):
    """If `initiate()` succeeds but its response has no recognizable
    conversation id (the gateway equivalent of "we can't tell you whether
    this landed in a DM"), that's a no-op for `is_dm` -- it's purely a
    best-effort delivery nicety now (see module docstring) -- and doesn't
    crash the handler or affect how any message is classified."""
    setup_job(db)
    seed_candidate(db, discord_link_code="ABC123")
    seed_pipeline_stage(db, stage="screening_assigned")
    agent1._discord_connection["id"] = "conn-discord-1"

    unconfirmable_client = FakeClient(initiate_response={"status": "queued"})
    agent1.handle_message(
        make_message(
            channel="discord",
            sender={"address": "disc-99"},
            text="ABC123",
            conversation_id="ext-conv-link-1",
            _client=unconfirmable_client,
        )
    )

    assert len(unconfirmable_client.initiates) == 1
    assert db.find_discord_dm_conversation(1) is None

    follow_up = make_message(
        channel="discord",
        sender={"address": "disc-99"},
        text="hi again",
        conversation_id="ext-conv-link-1",
    )
    agent1.handle_message(follow_up)

    assert follow_up._client.replies[0]["text"] == agent1.screening.DM_REDIRECT_MESSAGE


def test_discord_wrong_code_still_gets_generic_reply(db):
    setup_job(db)
    seed_candidate(db, discord_link_code="ABC123")

    message = make_message(
        channel="discord",
        sender={"address": "disc-99"},
        text="WRONGCODE",
        conversation_id="ext-x",
    )
    agent1.handle_message(message)

    assert "couldn't match this" in message._client.replies[0]["text"]


def test_discord_link_code_already_used_cannot_relink(db):
    setup_job(db)
    seed_candidate(db, discord_user_id="disc-1", discord_link_code="ABC123")

    # candidate is already linked to disc-1 -- a different Discord user
    # sending the same code must not be able to steal the link.
    message = make_message(
        channel="discord",
        sender={"address": "disc-2"},
        text="ABC123",
        conversation_id="ext-y",
    )
    agent1.handle_message(message)

    assert "couldn't match this" in message._client.replies[0]["text"]
    candidate = db.find_candidate_by_discord_user_id("disc-2")
    assert candidate is None


# -- start_discord_screening (proactive invite from the dashboard) --------
#
# No test simulates a Discord "member joined the server" event on purpose:
# the installed caspian-sdk (0.6.1) dispatches exactly three event types
# (message.received, interaction.received, reaction.received -- see
# CommClient._dispatch_event) and exposes no join-time hook at all, so there
# is nothing in this codebase that could fire such an event even in a test.
# The earliest point Agent 1 can act is a candidate's first message (see
# test_discord_linking_opens_a_dm_invite_when_configured above); closing the
# gap before that would need a different integration (e.g. discord.py's
# on_member_join) alongside caspian-sdk.


def test_start_discord_screening_sends_dm_with_first_question(db):
    setup_job(db)
    seed_candidate(db, discord_user_id="disc-1")
    seed_pipeline_stage(db, stage="screening_assigned")
    client = FakeClient()

    result = agent1.start_discord_screening(client, candidate_id=1)

    assert result == {"status": "dm_send_failed"}  # no discord connection configured yet
    agent1._discord_connection["id"] = "conn-discord-1"

    result = agent1.start_discord_screening(client, candidate_id=1)

    assert result == {"status": "sent"}
    assert len(client.initiates) == 1
    assert client.initiates[0]["connection_id"] == "conn-discord-1"
    assert client.initiates[0]["recipient"] == "disc-1"
    assert client.initiates[0]["text"] == "Can you tell me a bit about your relevant experience?"


def test_start_discord_screening_not_linked_returns_status(db):
    setup_job(db)
    seed_candidate(db)  # no discord_user_id
    seed_pipeline_stage(db, stage="screening_assigned")
    agent1._discord_connection["id"] = "conn-discord-1"
    client = FakeClient()

    result = agent1.start_discord_screening(client, candidate_id=1)

    assert result == {"status": "not_linked"}
    assert client.initiates == []


def test_start_discord_screening_sends_into_existing_dm_conversation(db):
    """If the candidate already has a DM on file (e.g. linked earlier),
    reuse it via send_message rather than opening a second DM."""
    setup_job(db)
    seed_candidate(db, discord_user_id="disc-1")
    seed_pipeline_stage(db, stage="screening_assigned")
    seed_conversation(db, channel="discord", external_conversation_id="dm-conv-1", is_dm=True)
    agent1._discord_connection["id"] = "conn-discord-1"
    client = FakeClient()

    result = agent1.start_discord_screening(client, candidate_id=1)

    assert result == {"status": "sent"}
    assert client.initiates == []
    assert len(client.sent_messages) == 1
    assert client.sent_messages[0]["conversation_id"] == "dm-conv-1"


def test_unhandled_channel_does_not_raise(db):
    message = make_message(channel="slack", text="hi")
    agent1.handle_message(message)  # should just log a warning, not raise
