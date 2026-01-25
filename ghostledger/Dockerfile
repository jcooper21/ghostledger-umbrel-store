# GhostLedger Dockerfile for Umbrel
# ==================================
# Multi-architecture build supporting ARM64 (Raspberry Pi) and AMD64 (x86)
#
# Build for Umbrel:
#   docker buildx build --platform linux/arm64,linux/amd64 \
#     --tag ghostledger/ghostledger:v1.0.0 --push .
#
# Following Umbrel best practices:
# - Uses slim base image (pre-cached on Umbrel devices)
# - Multi-stage build for minimal image size
# - Non-root user for security
# - Deterministic builds with pinned versions

# =============================================================================
# Stage 1: Builder
FROM python:3.11-slim AS builder

# Install specific system dependencies needed for Pandas/Numpy on ARM
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libopenblas-dev \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Stage 2: Runtime
FROM python:3.11-slim

# Metadata
LABEL org.opencontainers.image.title="GhostLedger"
LABEL org.opencontainers.image.version="1.2.9"

# Fix locale (prevent crash on emoji)
ENV LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

# Runtime dependencies (libopenblas for numpy, procps for health checks if needed)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libopenblas0 \
    procps \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --uid 1000 --create-home --shell /bin/bash ghostledger
WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY --chown=ghostledger:ghostledger . ./

# Switch to non-root user
USER ghostledger

# Expose Streamlit port
EXPOSE 8501

# Health check for Umbrel's monitoring
# Healthcheck removed for stability on slow devices
# HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 ...

# Start Streamlit with Umbrel-compatible settings
ENTRYPOINT ["streamlit", "run", "app.py", \
    "--server.headless=true", \
    "--server.address=0.0.0.0", \
    "--server.port=8501", \
    "--server.enableCORS=false", \
    "--server.enableXsrfProtection=false", \
    "--browser.gatherUsageStats=false"]
