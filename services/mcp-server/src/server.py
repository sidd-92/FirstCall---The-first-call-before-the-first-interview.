"""MCP server entrypoint for FirstCall's Caspian integration.

Exposes hiring-channel messaging (Slack, email, SMS, etc., via caspian-sdk)
as MCP tools so an LLM agent can list/connect channels and send, reply to,
and read messages during the hiring workflow.
"""

import os

from dotenv import load_dotenv
from mcp.server.mcpserver import MCPServer

from src.caspian_client import CaspianClient
from src.logging_config import configure_logging, get_logger

load_dotenv()
configure_logging()
log = get_logger()

mcp = MCPServer(name="firstcall-mcp-server")

caspian = CaspianClient()


@mcp.tool()
def list_channels() -> list[dict]:
    """List all channels/connections currently configured on the Caspian
    account (e.g. Slack, email, SMS).

    TODO: call `caspian.list_channels()` and return the result.
    """
    raise NotImplementedError


@mcp.tool()
def connect_channel(channel: str) -> dict:
    """Connect a new channel (e.g. "slack", "email", "telegram") so the
    hiring agent can send and receive messages on it.

    TODO: call `caspian.connect_channel(channel, **kwargs)` with whatever
    channel-specific credentials/config this tool ends up accepting.
    """
    raise NotImplementedError


@mcp.tool()
def send_message(conversation_id: str, text: str) -> dict:
    """Send a new outbound message on an existing conversation.

    TODO: call `caspian.send_message(conversation_id, text)`.
    """
    raise NotImplementedError


@mcp.tool()
def reply(message_id: str, text: str) -> dict:
    """Reply directly to a specific inbound message.

    TODO: call `caspian.reply(message_id, text)`.
    """
    raise NotImplementedError


@mcp.tool()
def get_new_messages(max_messages: int = 50) -> list[dict]:
    """Drain and return inbound messages buffered since the last call.

    TODO: call `caspian.get_new_messages(max_messages)`. See the TODO on
    `CaspianClient.start_listener` for why messages arrive via an in-memory
    queue instead of a direct synchronous fetch.
    """
    raise NotImplementedError


@mcp.tool()
def get_conversation(conversation_id: str) -> list[dict]:
    """Fetch the full message history for a conversation.

    TODO: call `caspian.get_conversation(conversation_id)`.
    """
    raise NotImplementedError


def main() -> None:
    # TODO(listener-thread): start the background thread that runs
    # `CommClient.listen()` for the lifetime of this process. `listen()`
    # blocks and fires `on_message` synchronously per inbound message, which
    # is incompatible with MCP tools being request/response -- see
    # `CaspianClient.start_listener` for the full design note. Messages land
    # in an in-memory queue that `get_new_messages` drains on demand.
    caspian.start_listener()

    # Runs as a long-lived container (see Dockerfile / docker-compose.yml),
    # not spawned per-client -- stdio transport won't work here since there's
    # no parent process piping its stdin/stdout to us. Use streamable-http so
    # other services in the compose network can reach it as a normal server.
    port = int(os.environ.get("MCP_SERVER_PORT", "8100"))
    log.info("mcp_server_starting", port=port)
    mcp.run(transport="streamable-http", host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
