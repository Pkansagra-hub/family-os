# K0 Memory Kernel - Production Container Image
# FamilyOS - Privacy-first, hardware-independent, no vendor lock-in

FROM python:3.11-slim

# Metadata
LABEL org.opencontainers.image.title="K0 Memory Kernel"
LABEL org.opencontainers.image.description="FamilyOS Memory Kernel - Family AI with Memory-Centric Architecture"
LABEL org.opencontainers.image.vendor="FamilyOS"
LABEL org.opencontainers.image.source="https://github.com/Pkansagra-hub/memory_kernel"

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    curl \
    sqlite3 \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy minimal kernel requirements (no ML/NLP libraries)
# Note: requirements.kernel.txt includes -r requirements.base.txt, so both files needed
COPY k0/deploy/requirements.base.txt k0/deploy/requirements.kernel.txt ./
RUN pip install --no-cache-dir -r requirements.kernel.txt && \
    python -m spacy download en_core_web_sm

# Copy application code
COPY k0/ k0/

# Create non-root user
RUN groupadd -r k0user -g 1000 && \
    useradd -r -u 1000 -g k0user k0user && \
    mkdir -p /data /secrets /config /logs && \
    chown -R k0user:k0user /app /data /secrets /config /logs

# Switch to non-root user
USER k0user

# Expose ports
# 8080: Main HTTP API (all routes: command, query, sse, observe, metrics)
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=5s --retries=3 --start-period=30s \
    CMD curl -f http://localhost:8080/healthz || exit 1

# Environment defaults
ENV K0_LOG_LEVEL=INFO \
    K0_DB_PATH=/data/k0_kernel.db \
    K0_DB_WAL_MODE=true \
    PYTHONUNBUFFERED=1

# Run the kernel
CMD ["python", "-m", "k0.kernel.main"]
