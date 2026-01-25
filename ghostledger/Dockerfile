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
# Stage 1: Builder - Install dependencies
# =============================================================================
FROM python:3.9-slim AS builder

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment for clean dependency isolation
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# =============================================================================
# Stage 2: Runtime - Minimal production image
# =============================================================================
FROM python:3.9-slim

# OCI Labels for Umbrel app store
LABEL org.opencontainers.image.title="GhostLedger"
LABEL org.opencontainers.image.description="Local-first Bitcoin tax calculator for Canada"
LABEL org.opencontainers.image.version="1.2.5"
LABEL org.opencontainers.image.source="https://github.com/ghostledger/ghostledger"
LABEL org.opencontainers.image.licenses="MIT"

# Environment configuration
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH"

# Create non-root user (UID 1000 matches Umbrel convention)
RUN useradd --uid 1000 --create-home --shell /bin/bash ghostledger

# Set up application directory
WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv

# Copy application code
COPY --chown=ghostledger:ghostledger *.py ./

# Switch to non-root user
USER ghostledger

# Expose Streamlit port
EXPOSE 8501

# Health check for Umbrel's monitoring
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health')" || exit 1

# Start Streamlit with Umbrel-compatible settings
ENTRYPOINT ["streamlit", "run", "app.py", \
    "--server.headless=true", \
    "--server.address=0.0.0.0", \
    "--server.port=8501", \
    "--server.enableCORS=false", \
    "--server.enableXsrfProtection=false", \
    "--browser.gatherUsageStats=false"]
