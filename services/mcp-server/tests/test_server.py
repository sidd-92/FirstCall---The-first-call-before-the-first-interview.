"""Tests for the MCP tools in src/server.py.

Each tool is exercised as a thin wrapper: we monkeypatch the underlying
`caspian_sdk.CommClient` methods (or seed the real, encrypted-at-rest
storage) and assert the tool both calls through correctly and returns real
data -- not just that it no longer raises NotImplementedError.
"""


import pytest
from caspian_sdk import Message
from starlette.testclient import TestClient

from src import server, status, storage
from tests.conftest import (
    seed_business,
    seed_candidate,
    seed_conversation,
    seed_job_posting,
)


@pytest.fixture(autouse=True)
def reset_status():
    """status is process-global module state; keep tests isolated."""
    status.set_server_state("starting")
    status.set_channel("email", "disconnected")
    status.set_channel("discord", "disconnected")
    yield
    status.set_server_state("starting")
    status.set_channel("email", "disconnected")
    status.set_channel("discord", "disconnected")


def make_message(**overrides) -> Message:
    defaults = {
        "id": "msg-1",
        "conversation_id": "ext-conv-1",
        "connection_id": "conn-1",
        "customer_id": "cust-1",
        "agent_id": "agent-1",
        "channel": "email",
        "sender": {"email": "a@example.com"},
        "subject": "hello",
        "text": "hi there",
        "html": None,
        "_client": None,
    }
    defaults.update(overrides)
    return Message(**defaults)


def test_list_channels_reflects_connected_state(monkeypatch):
    fake_channels = [
        {"channel": "email", "status": "active"},
        {"channel": "discord", "status": "active"},
    ]
    monkeypatch.setattr(server.caspian._client, "channels", lambda: fake_channels)

    result = server.list_channels()

    assert result == fake_channels


def test_connect_channel_email_wraps_connect_email(monkeypatch):
    calls = []

    def fake_connect_email(**kwargs):
        calls.append(kwargs)
        return {"id": "conn-email", "status": "active"}

    monkeypatch.setattr(server.caspian._client, "connect_email", fake_connect_email)

    result = server.connect_channel("email")

    assert result == {"id": "conn-email", "status": "active"}
    assert calls == [{}]
    assert status.snapshot()["channels"]["email"] == "connected"


def test_connect_channel_discord_wraps_connect_discord_with_bot_token(monkeypatch):
    calls = []

    def fake_connect_discord(**kwargs):
        calls.append(kwargs)
        return {"id": "conn-discord", "status": "active"}

    monkeypatch.setattr(server.caspian._client, "connect_discord", fake_connect_discord)

    result = server.connect_channel("discord", bot_token="tok-123")

    assert result == {"id": "conn-discord", "status": "active"}
    assert calls == [{"bot_token": "tok-123"}]
    assert status.snapshot()["channels"]["discord"] == "connected"


def test_connect_channel_failure_marks_channel_disconnected(monkeypatch):
    def fake_connect_discord(**kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(server.caspian._client, "connect_discord", fake_connect_discord)

    with pytest.raises(RuntimeError):
        server.connect_channel("discord", bot_token="tok-123")

    assert status.snapshot()["channels"]["discord"] == "disconnected"


def test_send_message_wraps_commclient_send(monkeypatch):
    calls = []

    def fake_send_message(conversation_id, **kwargs):
        calls.append((conversation_id, kwargs))
        return {"id": "msg-out-1"}

    monkeypatch.setattr(server.caspian._client, "send_message", fake_send_message)

    result = server.send_message("ext-conv-1", "hello there")

    assert result == {"id": "msg-out-1"}
    assert calls == [("ext-conv-1", {"text": "hello there"})]


def test_reply_wraps_message_reply_semantics(monkeypatch):
    calls = []

    def fake_reply(message_id, **kwargs):
        calls.append((message_id, kwargs))
        return {"id": "reply-1"}

    monkeypatch.setattr(server.caspian._client, "reply", fake_reply)

    result = server.reply("msg-1", "thanks for reaching out")

    assert result == {"id": "reply-1"}
    assert calls == [("msg-1", {"text": "thanks for reaching out"})]


def test_get_new_messages_drains_real_inbox_queue():
    msg1 = make_message(id="msg-1", text="first")
    msg2 = make_message(id="msg-2", text="second")
    server.caspian._inbox.put(msg1)
    server.caspian._inbox.put(msg2)

    result = server.get_new_messages(max_messages=50)

    assert [m["id"] for m in result] == ["msg-1", "msg-2"]
    assert [m["text"] for m in result] == ["first", "second"]
    # queue is drained, not just peeked
    assert server.caspian._inbox.empty()


def test_get_new_messages_respects_max_messages():
    for i in range(5):
        server.caspian._inbox.put(make_message(id=f"msg-{i}"))

    result = server.get_new_messages(max_messages=2)

    assert len(result) == 2
    assert server.caspian._inbox.qsize() == 3


def test_get_conversation_returns_real_decrypted_content(db):
    seed_business(db)
    seed_job_posting(db)
    seed_candidate(db)
    seed_conversation(db, conversation_id=1, candidate_id=1)

    storage.save_message(1, "inbound", "What's the salary range?")
    storage.save_message(1, "outbound", "$20-24/hr.", kind="faq_answer")

    result = server.get_conversation(1)

    assert [m["content"] for m in result] == ["What's the salary range?", "$20-24/hr."]
    assert [m["direction"] for m in result] == ["inbound", "outbound"]
    assert result[1]["kind"] == "faq_answer"
    # the row on disk is ciphertext, not plaintext
    with db.engine.connect() as conn:
        from sqlalchemy import select

        row = conn.execute(select(db.messages).where(db.messages.c.id == result[0]["id"])).first()
    assert b"salary" not in row.content_encrypted


def test_status_endpoint_reports_snapshot():
    status.set_server_state("running")
    status.set_channel("email", "connected")
    status.set_channel("discord", "connecting")

    app = server.mcp.streamable_http_app()
    client = TestClient(app)
    resp = client.get("/status")

    assert resp.status_code == 200
    assert resp.json() == {
        "status": "running",
        "channels": {"email": "connected", "discord": "connecting"},
    }


def test_status_endpoint_starts_in_starting_state():
    app = server.mcp.streamable_http_app()
    client = TestClient(app)
    resp = client.get("/status")

    assert resp.json()["status"] == "starting"
