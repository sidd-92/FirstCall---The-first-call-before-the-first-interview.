"""Shared server-status state, read by the plain `/status` HTTP endpoint.

`src.agents.agent1.register` updates channel state as it connects Email and
Discord at startup; `src.server.main` flips the overall server state to
"running" once the listener thread is confirmed alive (or "error" if nothing
connected / the listener never came up). Kept as simple module state guarded
by a lock since it's written from the startup thread and the listener thread,
and read from request-handling tasks.
"""

import threading

_lock = threading.Lock()
_server_state = "starting"
_channels: dict[str, str] = {"email": "disconnected", "discord": "disconnected"}


def set_channel(channel: str, state: str) -> None:
    with _lock:
        _channels[channel] = state


def set_server_state(state: str) -> None:
    global _server_state
    with _lock:
        _server_state = state


def snapshot() -> dict:
    with _lock:
        return {"status": _server_state, "channels": dict(_channels)}
