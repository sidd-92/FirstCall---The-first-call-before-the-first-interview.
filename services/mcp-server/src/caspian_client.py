"""Thin wrapper around caspian-sdk's `CommClient`.

Points at the hosted Caspian gateway by default: `CommClient(api_key=...)`
reads `CASPIAN_API_KEY` from the environment when no key is passed, and the
SDK defaults `base_url` to the hosted gateway when it isn't overridden. We
deliberately never set `CASPIAN_BASE_URL` here -- self-hosting the gateway is
out of scope for FirstCall.
"""

import os
import queue
import threading

from caspian_sdk import CommClient, Message

from src import status
from src.logging_config import get_logger

log = get_logger()


class CaspianClient:
    """Wraps `CommClient` and adapts its blocking `listen()` loop for use
    from request/response MCP tools.
    """

    def __init__(self, api_key: str | None = None) -> None:
        self._client = CommClient(api_key=api_key or os.environ.get("CASPIAN_API_KEY"))
        self._inbox: queue.Queue[Message] = queue.Queue()
        self._listener_thread: threading.Thread | None = None

    # -- lifecycle ---------------------------------------------------------

    def start_listener(self) -> None:
        """Start `CommClient.listen()` in a background daemon thread.

        TODO(listener-thread): `CommClient.listen()` blocks forever and invokes
        the `on_message` handler synchronously per inbound message -- it is
        designed for long-running processes, not request/response calls. MCP
        tools, however, are invoked one at a time and must return promptly.
        To bridge the two models we run `listen()` on its own thread at
        startup; the `on_message` handler just pushes each `Message` onto an
        in-memory `queue.Queue` (self._inbox) instead of processing it
        inline. The `get_new_messages` MCP tool then drains that queue on
        demand. This keeps the SDK's blocking loop alive for the lifetime of
        the process while every tool call itself stays non-blocking.
        """
        if self._listener_thread is not None:
            return

        self._client.on_message(self._inbox.put)

        def _run() -> None:
            log.info("caspian_listener_starting")
            self._client.listen()

        self._listener_thread = threading.Thread(
            target=_run, name="caspian-listener", daemon=True
        )
        self._listener_thread.start()

    def close(self) -> None:
        self._client.close()

    def listener_alive(self) -> bool:
        """Whether the background `listen()` thread is up and running."""
        return self._listener_thread is not None and self._listener_thread.is_alive()

    @property
    def raw_client(self) -> CommClient:
        """The underlying `CommClient`, for callers (e.g. src/agents) that need
        to register their own `on_message` handler or connect channels."""
        return self._client

    # -- channels ------------------------------------------------------------

    def list_channels(self) -> list[dict]:
        """List configured channels/connections and their capabilities."""
        return self._client.channels()

    def connect_channel(self, channel: str, **kwargs) -> dict:
        """Connect a channel (currently "email" or "discord", matching what
        `src.agents.agent1.register` connects at startup) and track its
        connection state for the `/status` endpoint."""
        status.set_channel(channel, "connecting")
        try:
            if channel == "email":
                result = self._client.connect_email(**kwargs)
            elif channel == "discord":
                result = self._client.connect_discord(**kwargs)
            else:
                raise ValueError(f"unsupported channel: {channel!r}")
        except Exception:
            status.set_channel(channel, "disconnected")
            raise
        status.set_channel(channel, "connected")
        return result

    # -- messaging -----------------------------------------------------------

    def send_message(self, conversation_id: str, text: str) -> dict:
        """Send a new outbound message on an existing conversation."""
        return self._client.send_message(conversation_id, text=text)

    def reply(self, message_id: str, text: str) -> dict:
        """Reply to a specific inbound message."""
        return self._client.reply(message_id, text=text)

    def initiate(self, connection_id: str, recipient: str, text: str) -> dict:
        """Cold-start a conversation on a connection that hasn't received any
        inbound message yet (needs Capability.INITIATE)."""
        return self._client.initiate(connection_id, recipient, text)

    def get_new_messages(self, max_messages: int = 50) -> list[Message]:
        """Drain up to `max_messages` buffered inbound messages from the
        in-memory inbox populated by the background listener thread."""
        drained: list[Message] = []
        while len(drained) < max_messages:
            try:
                drained.append(self._inbox.get_nowait())
            except queue.Empty:
                break
        return drained

    # get_conversation is intentionally not wrapped here: per the module
    # docstring, "conversation" history for the hiring workflow is our own
    # encrypted-at-rest record (src/storage.py's `messages` table, keyed by
    # local conversation id), not the gateway's own message list. See
    # `src.server.get_conversation`, which wraps `src.storage.get_conversation`
    # directly.
