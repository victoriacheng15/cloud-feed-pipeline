# Stage 1: Build dependency virtual environment using uv on Alpine
FROM python:3.12-alpine AS builder

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1

COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

# Stage 2: Minimal runtime image without build tooling or uv binary
FROM python:3.12-alpine AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Least-privilege runtime user
RUN addgroup -S extractorgroup && adduser -S extractoruser -G extractorgroup

# Copy isolated virtual environment and application code
COPY --from=builder /app/.venv /app/.venv
COPY src/extractor.py .

RUN chown -R extractoruser:extractorgroup /app
USER extractoruser

ENTRYPOINT ["python", "extractor.py"]
