"""Test-session setup: point the app at a throwaway SQLite file instead of
the real DATABASE_URL, before src.main (and therefore src.db) ever gets
imported by a test module. python-dotenv's load_dotenv() (called in
src.main) never overrides an already-set env var, so setting these here
first keeps tests isolated from a real local .env.
"""

import os
import tempfile

from cryptography.fernet import Fernet

_tmp_dir = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp_dir}/test.db"
os.environ["RESUME_STORAGE_DIR"] = f"{_tmp_dir}/resumes"
os.environ.setdefault("AUTH0_DOMAIN", "test.auth0.com")
os.environ.setdefault("AUTH0_AUDIENCE", "https://test-audience")
os.environ.setdefault("ENCRYPTION_KEY", Fernet.generate_key().decode())
os.environ.setdefault("CASPIAN_API_KEY", "test-caspian-key")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-anthropic-key")

import socket
import threading
import time

import pytest
import uvicorn
from mcp.server.mcpserver import MCPServer
from starlette.requests import Request
from starlette.responses import JSONResponse

from src.db import engine
from src.models import Base

Base.metadata.create_all(bind=engine)


@pytest.fixture
def db_session():
    from src.db import SessionLocal

    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _build_test_mcp_app(status_holder: dict) -> MCPServer:
    """A real MCPServer instance exposing the same seven tools (name,
    description, input schema) as services/mcp-server/src/server.py, plus
    the same plain GET /status route -- so backend tests exercise the real
    MCP protocol (initialize/tools-list/tools-call, real JSON Schema) without
    depending on mcp-server's separate uv project/venv."""
    app = MCPServer(name="firstcall-mcp-server-test")

    @app.tool()
    def list_channels() -> list[dict]:
        """List all channels/connections currently configured on the Caspian
        account (e.g. Slack, email, SMS)."""
        return [
            {"channel": "email", "status": "active"},
            {"channel": "discord", "status": "active"},
        ]

    @app.tool()
    def connect_channel(
        channel: str,
        bot_token: str | None = None,
        username: str | None = None,
        domain: str | None = None,
    ) -> dict:
        """Connect a new channel ("email" or "discord")."""
        return {"id": f"conn-{channel}", "status": "active"}

    @app.tool()
    def send_message(conversation_id: str, text: str) -> dict:
        """Send a new outbound message on an existing conversation."""
        return {"id": "msg-out-1"}

    @app.tool()
    def reply(message_id: str, text: str) -> dict:
        """Reply directly to a specific inbound message."""
        return {"id": "reply-1"}

    @app.tool()
    def initiate(connection_id: str, recipient: str, text: str) -> dict:
        """Cold-start a conversation on a connection."""
        return {"id": "conv-cold-1", "status": "active"}

    @app.tool()
    def get_new_messages(max_messages: int = 50) -> list[dict]:
        """Drain and return inbound messages buffered since the last call."""
        return []

    @app.tool()
    def get_conversation(conversation_id: int) -> list[dict]:
        """Fetch the full, decrypted message history for a conversation."""
        return []

    @app.custom_route("/status", methods=["GET"])
    async def get_status(request: Request) -> JSONResponse:
        return JSONResponse(status_holder["value"])

    return app


class _UvicornThreadServer:
    """Runs an ASGI app on a real localhost socket in a background thread,
    for tests that need an actual HTTP peer (not a mock)."""

    def __init__(self, app) -> None:
        self.port = _free_port()
        config = uvicorn.Config(app, host="127.0.0.1", port=self.port, log_level="warning")
        self.server = uvicorn.Server(config)
        self._thread = threading.Thread(target=self.server.run, daemon=True)

    def start(self) -> None:
        self._thread.start()
        while not self.server.started:
            time.sleep(0.01)

    def stop(self) -> None:
        self.server.should_exit = True
        self._thread.join(timeout=5)

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"


@pytest.fixture
def mcp_test_server():
    """A live, real mcp-server-shaped MCP server (see `_build_test_mcp_app`)
    listening on an actual localhost port for the duration of the test.
    Yields (base_url, status_holder) -- mutate status_holder["value"] to
    change what GET /status returns."""
    status_holder = {"value": {"status": "starting", "channels": {}}}
    app = _build_test_mcp_app(status_holder)
    server = _UvicornThreadServer(app.streamable_http_app())
    server.start()
    try:
        yield server.base_url, status_holder
    finally:
        server.stop()
