FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /build
COPY pyproject.toml uv.lock* ./
RUN uv sync --frozen --no-dev --no-install-project || uv sync --no-dev

COPY src ./src
RUN uv sync --frozen --no-dev


FROM python:3.12-slim

RUN useradd -m -u 1000 miniagent && \
    apt-get update && apt-get install -y --no-install-recommends git && \
    rm -rf /var/lib/apt/lists/*

COPY --from=builder --chown=miniagent:miniagent /build/.venv /app/.venv
COPY --from=builder --chown=miniagent:miniagent /build/src /app/src

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app/src" \
    PYTHONUNBUFFERED=1

WORKDIR /workspace
USER miniagent

ENTRYPOINT ["miniagent"]
