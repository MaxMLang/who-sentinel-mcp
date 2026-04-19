# who-sentinel-mcp (stdio MCP server)
# Build:  docker build -t who-sentinel-mcp .
# Run:    docker run -i --rm who-sentinel-mcp
FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim

WORKDIR /app
COPY pyproject.toml uv.lock README.md LICENSE ./
COPY src ./src

RUN uv sync --frozen --no-dev

ENV PYTHONUNBUFFERED=1
CMD ["uv", "run", "who-sentinel-mcp"]
