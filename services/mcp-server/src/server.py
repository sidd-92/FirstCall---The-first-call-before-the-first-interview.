"""MCP server entrypoint for FirstCall's Caspian integration.

Exposes hiring-channel messaging (Slack, email, SMS, etc., via caspian-sdk)
as MCP tools so an LLM agent can list/connect channels and send, reply to,
and read messages during the hiring workflow.
"""

import os

from dotenv import load_dotenv
from mcp.server.mcpserver import MCPServer
from starlette.requests import Request
from starlette.responses import JSONResponse

from src import status, storage
from src.agents.agent1 import register as register_agent1
from src.caspian_client import CaspianClient
from src.logging_config import configure_logging, get_logger

load_dotenv()
configure_logging()
log = get_logger()

mcp = MCPServer(name="firstcall-mcp-server")

caspian = CaspianClient()


def _message_to_dict(message) -> dict:
    return {
        "id": message.id,
        "conversation_id": message.conversation_id,
        "connection_id": message.connection_id,
        "customer_id": message.customer_id,
        "agent_id": message.agent_id,
        "channel": message.channel,
        "sender": message.sender,
        "subject": message.subject,
        "text": message.text,
        "html": message.html,
        "media": message.media,
    }


@mcp.tool()
def list_channels() -> list[dict]:
    """List all channels/connections currently configured on the Caspian
    account (e.g. Slack, email, SMS)."""
    return caspian.list_channels()


@mcp.tool()
def connect_channel(
    channel: str,
    bot_token: str | None = None,
    username: str | None = None,
    domain: str | None = None,
) -> dict:
    """Connect a new channel ("email" or "discord", matching what Agent 1
    connects at startup) so the hiring agent can send and receive messages
    on it. `bot_token` is required for discord; `username`/`domain` are
    optional for email."""
    kwargs = {}
    if bot_token is not None:
        kwargs["bot_token"] = bot_token
    if username is not None:
        kwargs["username"] = username
    if domain is not None:
        kwargs["domain"] = domain
    return caspian.connect_channel(channel, **kwargs)


@mcp.tool()
def send_message(conversation_id: str, text: str) -> dict:
    """Send a new outbound message on an existing conversation (not a reply
    to a specific inbound message -- see `reply` for that)."""
    return caspian.send_message(conversation_id, text)


@mcp.tool()
def reply(message_id: str, text: str) -> dict:
    """Reply directly to a specific inbound message."""
    return caspian.reply(message_id, text)


@mcp.tool()
def initiate(connection_id: str, recipient: str, text: str) -> dict:
    """Cold-start a conversation on a connection -- unlike `send_message`,
    this doesn't need an existing conversation_id from a prior inbound
    message; pass the connection_id from `connect_channel`/`list_channels`
    and the recipient address (e.g. an email address, or a Discord user id)
    directly. Requires Capability.INITIATE on the connection."""
    return caspian.initiate(connection_id, recipient, text)


@mcp.tool()
def get_new_messages(max_messages: int = 50) -> list[dict]:
    """Drain and return inbound messages buffered since the last call.

    Messages arrive via an in-memory queue populated by the background
    listener thread (`CommClient.listen()`) -- see `CaspianClient.start_listener`
    for why -- so this call is what actually surfaces them to an MCP client.
    """
    return [_message_to_dict(message) for message in caspian.get_new_messages(max_messages)]


@mcp.tool()
def get_conversation(conversation_id: int) -> list[dict]:
    """Fetch the full, decrypted message history for a conversation from our
    own encrypted-at-rest storage (src/storage.py), keyed by the local
    conversation id (not the gateway's external conversation id)."""
    return [
        {
            "id": message.id,
            "conversation_id": message.conversation_id,
            "direction": message.direction,
            "content": message.content,
            "kind": message.kind,
            "created_at": message.created_at.isoformat() if message.created_at else None,
        }
        for message in storage.get_conversation(conversation_id)
    ]


@mcp.custom_route("/status", methods=["GET"])
async def get_status(request: Request) -> JSONResponse:
    """Plain HTTP status endpoint -- not part of the MCP protocol itself --
    so orchestration tooling (docker-compose healthchecks, etc.) can poll
    startup/connection state without speaking MCP."""
    return JSONResponse(status.snapshot())


def main() -> None:
    # Connect Email + Discord and register Agent 1's handler before the
    # listener starts pulling events, so nothing arrives un-handled.
    register_agent1(caspian.raw_client)

    # `listen()` blocks and fires `on_message` synchronously per inbound
    # message, which is incompatible with MCP tools being request/response --
    # see `CaspianClient.start_listener` for the full design note. Messages
    # land in an in-memory queue that `get_new_messages` drains on demand.
    caspian.start_listener()

    channels = status.snapshot()["channels"]
    if caspian.listener_alive() and any(state == "connected" for state in channels.values()):
        status.set_server_state("running")
    else:
        status.set_server_state("error")

    # Runs as a long-lived container (see Dockerfile / docker-compose.yml),
    # not spawned per-client -- stdio transport won't work here since there's
    # no parent process piping its stdin/stdout to us. Use streamable-http so
    # other services in the compose network can reach it as a normal server.
    port = int(os.environ.get("MCP_SERVER_PORT", "8100"))
    log.info("mcp_server_starting", port=port)
    mcp.run(transport="streamable-http", host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
