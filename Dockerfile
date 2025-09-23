## Optimized multi-stage image keeping pandas, trimming build toolchain and extras
ARG PYTHON_VERSION=3.11

### ---- Builder stage ----
FROM python:${PYTHON_VERSION}-slim AS builder
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 UV_LINK_MODE=copy
WORKDIR /app

# Build dependencies for compiling wheels (numpy/pandas may need them) + strip utility
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    ca-certificates \
    binutils \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

COPY pyproject.toml uv.lock* ./
RUN uv sync --frozen --no-install-project --python ${PYTHON_VERSION}

# Remove uv cache & typical junk (tests, pyc) early to reduce copy size
RUN rm -rf /root/.cache/uv \
    && find .venv -type d -name '__pycache__' -prune -exec rm -rf {} + \
    && find .venv -type f -name '*.pyc' -delete \
    && find .venv/lib/python3.11/site-packages -type d \( -name tests -o -name test \) -prune -exec rm -rf {} + \
    && find .venv -name '*.so' -exec strip --strip-unneeded {} + || true

COPY app app
COPY mcp mcp
COPY main.py .

### ---- Runtime stage ----
FROM python:${PYTHON_VERSION}-slim AS runtime
ENV PYTHONUNBUFFERED=1
WORKDIR /app

# Optional prune of manpages / locales / docs to save space
RUN rm -rf /usr/share/man/* /usr/share/doc/* /usr/share/locale/* || true

# Copy trimmed virtualenv and application
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app /app
ENV PATH=/app/.venv/bin:$PATH

EXPOSE 8002
ENTRYPOINT ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8002", "--workers", "2"]
