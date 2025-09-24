## Optimized multi-stage image keeping pandas, trimming build toolchain and extras
# syntax=docker/dockerfile:1.7-labs
ARG PYTHON_VERSION=3.11

### ---- Builder stage ----
FROM python:${PYTHON_VERSION}-slim AS builder
ENV PYTHONUNBUFFERED=1 UV_LINK_MODE=copy PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app

# Build dependencies for compiling wheels (numpy/pandas may need them) + strip utility
RUN --mount=type=cache,target=/var/cache/apt \
    --mount=type=cache,target=/var/lib/apt/lists \
    apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    ca-certificates \
    binutils

RUN --mount=type=cache,target=/root/.cache/pip pip install uv

COPY pyproject.toml uv.lock ./
# Ensure uv.lock exists explicitly (COPY with wildcard may pass depending on context)
RUN test -f uv.lock

# Place config files next to uv.lock so runtime lookup works
COPY config.yaml workflow.yaml ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-install-project --python ${PYTHON_VERSION}

# Remove typical junk (tests, pyc) early to reduce copy size
RUN find .venv/lib/python3.11/site-packages -type d \( -name tests -o -name test \) -prune -exec rm -rf {} + \
    && find .venv -name '*.so' -exec strip --strip-unneeded {} + || true

# Optional: remove build tools from venv to save space (skip if you need them at runtime)
# Keep venv tooling intact to avoid breaking _virtualenv.pth and imports

COPY app app
COPY mcp mcp
COPY main.py .

# Prune project caches to reduce final size
RUN find /app -type d -name '__pycache__' -prune -exec rm -rf {} + \
    && rm -rf /app/.pytest_cache /app/.mypy_cache || true


### ---- Runtime stage ----
FROM python:${PYTHON_VERSION}-slim AS runtime
ENV PYTHONUNBUFFERED=1
WORKDIR /app

# Optional prune of manpages / locales / docs to save space
RUN rm -rf /usr/share/man/* /usr/share/doc/* /usr/share/locale/* /var/lib/apt/lists/* || true

# Copy trimmed virtualenv and only the necessary application files
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/main.py /app/main.py
COPY --from=builder /app/app /app/app
COPY --from=builder /app/mcp /app/mcp
COPY --from=builder /app/config.yaml /app/config.yaml
COPY --from=builder /app/workflow.yaml /app/workflow.yaml
COPY --from=builder /app/uv.lock /app/uv.lock
ENV PATH=/app/.venv/bin:$PATH

EXPOSE 8002
ENTRYPOINT ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8002", "--workers", "2"]
