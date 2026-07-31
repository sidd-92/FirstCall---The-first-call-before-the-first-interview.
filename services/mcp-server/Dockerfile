FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1

COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev

COPY src ./src

# Listens via MCP streamable-http transport (see src/server.py) -- not
# published to the host by default, only reachable from other containers
# on the compose network.
EXPOSE 8100

CMD ["uv", "run", "python", "-m", "src.server"]
