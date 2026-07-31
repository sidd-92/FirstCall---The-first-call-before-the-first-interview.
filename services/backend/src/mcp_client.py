"""Real MCP client for the HR dashboard's live tool-runner page
(routes/dashboard.py's /mcp-server/* routes).

Uses the official Python MCP SDK's client side -- the same `mcp` package
family services/mcp-server/src/server.py uses to serve tools, just the
client half here -- talking real MCP protocol (initialize, tools/list,
tools/call) over Streamable HTTP to the mcp-server container.

One short-lived `ClientSession` per call: simpler and safer than holding a
persistent MCP connection open across unrelated dashboard HTTP requests.
"""

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.types import CallToolResult, Tool

MCP_SERVER_PORT = os.environ.get("MCP_SERVER_PORT", "8100")
# `mcp-server` is the Docker Compose service name (see docker-compose.yml) --
# reachable by that name from any other container on the compose network.
MCP_SERVER_URL = os.environ.get("MCP_SERVER_URL", f"http://mcp-server:{MCP_SERVER_PORT}/mcp")


@asynccontextmanager
async def mcp_session() -> AsyncIterator[ClientSession]:
    """Open one real MCP session against mcp-server: connect, initialize,
    yield the session, tear down on exit."""
    async with (
        streamable_http_client(MCP_SERVER_URL) as (read_stream, write_stream),
        ClientSession(read_stream, write_stream) as session,
    ):
        await session.initialize()
        yield session


async def list_tools() -> list[Tool]:
    """Real `tools/list` MCP call. Returns the tools mcp-server actually
    has registered (see src/server.py there)."""
    async with mcp_session() as session:
        result = await session.list_tools()
        return result.tools


async def call_tool(name: str, arguments: dict[str, Any]) -> CallToolResult:
    """Real `tools/call` MCP call."""
    async with mcp_session() as session:
        return await session.call_tool(name, arguments)
