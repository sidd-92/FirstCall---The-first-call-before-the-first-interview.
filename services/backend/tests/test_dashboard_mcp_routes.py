"""Tests for the /mcp-server/* dashboard routes (routes/dashboard.py).

These exercise the real MCP protocol (initialize, tools/list, tools/call)
against a live MCPServer instance running on an actual localhost socket (see
tests/conftest.py's `mcp_test_server` fixture) -- not a mocked response
shape. The unreachable-server case uses a real closed port, so the
"disconnected" path is exercised by a genuine connection failure too.
"""

import json
import socket

import pytest
from fastapi.testclient import TestClient

import src.routes.dashboard as dashboard_routes
from src import mcp_client
from src.auth import get_current_business
from src.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


def _authorize(business_id: int = 1) -> None:
    app.dependency_overrides[get_current_business] = lambda: business_id


def _closed_port_url() -> str:
    """A URL nothing is listening on, for a real (not mocked) connection failure."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    return f"http://127.0.0.1:{port}"


# -- status ---------------------------------------------------------------


def test_status_passes_through_running_body(mcp_test_server, monkeypatch):
    base_url, status_holder = mcp_test_server
    status_holder["value"] = {
        "status": "running",
        "channels": {"email": "connected", "discord": "connected"},
    }
    monkeypatch.setattr(dashboard_routes, "MCP_STATUS_URL", f"{base_url}/status")
    _authorize()

    response = client.get("/mcp-server/status")

    assert response.status_code == 200
    assert response.json() == {
        "status": "running",
        "channels": {"email": "connected", "discord": "connected"},
    }


def test_status_passes_through_error_body_not_collapsed(mcp_test_server, monkeypatch):
    base_url, status_holder = mcp_test_server
    status_holder["value"] = {
        "status": "error",
        "channels": {"email": "disconnected", "discord": "disconnected"},
    }
    monkeypatch.setattr(dashboard_routes, "MCP_STATUS_URL", f"{base_url}/status")
    _authorize()

    response = client.get("/mcp-server/status")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "error"
    # must stay distinct from the "server unreachable" case
    assert body != {"status": "disconnected", "channels": {}}


def test_status_reports_disconnected_when_unreachable(monkeypatch):
    monkeypatch.setattr(dashboard_routes, "MCP_STATUS_URL", f"{_closed_port_url()}/status")
    _authorize()

    response = client.get("/mcp-server/status")

    assert response.status_code == 200
    assert response.json() == {"status": "disconnected", "channels": {}}


def test_status_requires_auth() -> None:
    response = client.get("/mcp-server/status")
    assert response.status_code in (401, 403)


# -- tools/list -------------------------------------------------------------


def test_tools_list_returns_the_eight_real_tools(mcp_test_server, monkeypatch):
    base_url, _ = mcp_test_server
    monkeypatch.setattr(mcp_client, "MCP_SERVER_URL", f"{base_url}/mcp")
    _authorize()

    response = client.get("/mcp-server/tools")

    assert response.status_code == 200
    tools = response.json()
    names = {tool["name"] for tool in tools}
    assert names == {
        "list_channels",
        "connect_channel",
        "send_message",
        "reply",
        "initiate",
        "start_discord_screening",
        "get_new_messages",
        "get_conversation",
    }
    for tool in tools:
        assert tool["description"]
        assert tool["input_schema"]["type"] == "object"

    send_message_tool = next(t for t in tools if t["name"] == "send_message")
    assert set(send_message_tool["input_schema"]["properties"]) == {"conversation_id", "text"}


def test_tools_list_requires_auth() -> None:
    response = client.get("/mcp-server/tools")
    assert response.status_code in (401, 403)


# -- tools/call ---------------------------------------------------------------


def test_tools_call_list_channels_returns_real_result(mcp_test_server, monkeypatch):
    base_url, _ = mcp_test_server
    monkeypatch.setattr(mcp_client, "MCP_SERVER_URL", f"{base_url}/mcp")
    _authorize()

    response = client.post("/mcp-server/tools/list_channels/call", json={"arguments": {}})

    assert response.status_code == 200
    body = response.json()
    assert body["is_error"] is False
    # one text content block per list item
    assert [json.loads(block) for block in body["content"]] == [
        {"channel": "email", "status": "active"},
        {"channel": "discord", "status": "active"},
    ]


def test_tools_call_passes_through_arguments(mcp_test_server, monkeypatch):
    base_url, _ = mcp_test_server
    monkeypatch.setattr(mcp_client, "MCP_SERVER_URL", f"{base_url}/mcp")
    _authorize()

    response = client.post(
        "/mcp-server/tools/connect_channel/call",
        json={"arguments": {"channel": "discord", "bot_token": "tok-123"}},
    )

    assert response.status_code == 200
    body = response.json()
    assert json.loads(body["content"][0]) == {"id": "conn-discord", "status": "active"}


def test_tools_call_unreachable_server_returns_502(monkeypatch):
    monkeypatch.setattr(mcp_client, "MCP_SERVER_URL", f"{_closed_port_url()}/mcp")
    _authorize()

    response = client.post("/mcp-server/tools/list_channels/call", json={"arguments": {}})

    assert response.status_code == 502


def test_tools_call_requires_auth() -> None:
    response = client.post("/mcp-server/tools/list_channels/call", json={"arguments": {}})
    assert response.status_code in (401, 403)
