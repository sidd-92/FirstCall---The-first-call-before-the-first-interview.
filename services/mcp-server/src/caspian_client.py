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

    @property
    def raw_client(self) -> CommClient:
        """The underlying `CommClient`, for callers (e.g. src/agents) that need
        to register their own `on_message` handler or connect channels."""
        return self._client

    # -- channels ------------------------------------------------------------

    def list_channels(self) -> list[dict]:
        """List configured channels/connections. TODO: map to `channels()`."""
        raise NotImplementedError

    def connect_channel(self, channel: str, **kwargs) -> dict:
        """Connect a channel (e.g. slack, telegram, email).

        TODO: dispatch to the matching `CommClient.connect_<channel>` method.
        """
        raise NotImplementedError

    # -- messaging -----------------------------------------------------------

    def send_message(self, conversation_id: str, text: str) -> dict:
        """Send a new outbound message. TODO: map to `send_message()`."""
        raise NotImplementedError

    def reply(self, message_id: str, text: str) -> dict:
        """Reply to a specific inbound message. TODO: map to `reply()`."""
        raise NotImplementedError

    def get_new_messages(self, max_messages: int = 50) -> list[Message]:
        """Drain up to `max_messages` buffered inbound messages from the
        in-memory inbox populated by the background listener thread.

        TODO: implement draining logic against `self._inbox`.
        """
        raise NotImplementedError

    def get_conversation(self, conversation_id: str) -> list[dict]:
        """Fetch full message history for a conversation.

        TODO: map to `list_messages(conversation_id)` / `backfill()`.
        """
        raise NotImplementedError
