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
COPY config.yaml mcp.yaml ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-install-project --python ${PYTHON_VERSION}

# Remove typical junk (tests, pyc) early to reduce copy size
RUN find .venv/lib/python3.11/site-packages -type d \( -name tests -o -name test \) -prune -exec rm -rf {} + \
    && find .venv -name '*.so' -exec strip --strip-unneeded {} + || true

# Optional: remove build tools from venv to save space (skip if you need them at runtime)
# Keep venv tooling intact to avoid breaking _virtualenv.pth and imports

COPY app app
COPY mcp mcp
COPY skills_bqm skills
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
# Install util-linux for nsenter to allow host command execution
RUN apt-get update && apt-get install -y util-linux curl && rm -rf /var/lib/apt/lists/*

# Copy trimmed virtualenv and only the necessary application files
# COPY --from=builder /app/.venv /app/.venv     <-- 注释掉旧的

# 将 builder 阶段生成的 site-packages 直接复制到系统 python 目录
COPY --from=builder /app/.venv/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
# 同时复制 bin 目录下的脚本（如 uvicorn）到系统 bin
COPY --from=builder /app/.venv/bin/* /usr/local/bin/

COPY --from=builder /app/main.py /app/main.py
COPY --from=builder /app/app /app/app
COPY --from=builder /app/mcp /app/mcp
COPY --from=builder /app/config.yaml /app/config.yaml
COPY --from=builder /app/mcp.yaml /app/mcp.yaml
COPY --from=builder /app/uv.lock /app/uv.lock
COPY --from=builder /app/skills /app/skills
# ENV PATH=/app/.venv/bin:$PATH                  <-- 不再需要
# ENV PYTHONPATH=/app/.venv/lib/python3.11/site-packages  <-- 不再需要

EXPOSE 8002
# 使用 python -m uvicorn 确保使用系统 Python 解释器启动，避免依赖 venv 中硬编码路径的 uvicorn 脚本
ENTRYPOINT ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8002", "--workers", "2"]
