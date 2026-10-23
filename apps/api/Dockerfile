# syntax=docker/dockerfile:1
# DocFlow API image (API + worker + MCP in one process, ROLE=all on Render).
# Build from the repo root:  docker build -f apps/api/Dockerfile .

# ---------------------------------------------------------------- builder
FROM ghcr.io/astral-sh/uv:0.13.5-python3.12-trixie-slim AS builder
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app

# Dependencies first, so code changes don't invalidate this layer.
COPY apps/api/pyproject.toml apps/api/uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev --no-install-project

COPY apps/api/ ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev

# ---------------------------------------------------------------- runtime
FROM python:3.12-slim-trixie AS runtime
RUN groupadd --system app && useradd --system --gid app --no-create-home app
WORKDIR /app

COPY --from=builder --chown=app:app /app /app
# Document JSON Schemas (schemas/README.md); validation reads them at runtime from F5 on.
COPY --chown=app:app schemas /schemas

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    ROLE=all \
    PORT=10000

USER app
EXPOSE 10000
CMD ["./start.sh"]
