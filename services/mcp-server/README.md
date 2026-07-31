# mcp-server

Python service wrapping the caspian-sdk to expose an MCP interface for the hiring agent.

## Dev setup

```bash
uv sync
uv run python -m src.server
```

## Layout

- `src/server.py` — MCP server entrypoint and tool definitions
- `src/caspian_client.py` — wraps `CommClient` from caspian-sdk
- `src/storage.py` — conversation/candidate store (SQLite, encrypted at rest)
- `src/logging_config.py` — structlog JSON logging setup
- `tests/` — pytest suite
