# K0 Production Deployment Guide

**Version:** 1.0.0
**Date:** 2025-11-10
**Audience:** DevOps/SRE teams deploying K0 in production

## Overview

This guide covers deploying K0 to production environments with high availability, observability, and operational best practices. K0 is a production-ready microkernel designed for envelope processing with:

- **ACID guarantees** via SQLite WAL mode
- **Async worker architecture** (embedding, FTS indexing)
- **Full observability** (Prometheus, OpenTelemetry, Grafana)
- **Policy enforcement** (PEM with manifest validation)
- **Zero data loss** (WAL-based durability, crash recovery)
- **Ed25519 signatures** for envelope authentication (64-byte signatures)

**Target Audience:** DevOps engineers, SREs, infrastructure teams

**Database Location:** K0 uses SQLite at `k0/deploy/data/k0_kernel.db` (bind mount in Docker)

**Time to deploy:** 2-4 hours (single-node), 4-8 hours (distributed)

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Deployment Models](#2-deployment-models)
3. [Prerequisites](#3-prerequisites)
4. [Docker Compose Deployment](#4-docker-compose-deployment)
5. [Kubernetes Deployment](#5-kubernetes-deployment)
6. [Configuration Management](#6-configuration-management)
7. [Security Hardening](#7-security-hardening)
8. [Monitoring & Observability](#8-monitoring--observability)
9. [Backup & Disaster Recovery](#9-backup--disaster-recovery)
10. [Performance Tuning](#10-performance-tuning)
11. [Operations Runbook](#11-operations-runbook)
12. [Troubleshooting](#12-troubleshooting)

---

## 1. Architecture Overview

### 1.1 K0 Component Stack

```
┌──────────────────────────────────────────────────────────┐
│                    K0 Kernel (FastAPI)                   │
│  - Command Port: /k0/command.submit                      │
│  - Query Port: /k0/query.recall                          │
│  - SSE Port: /k0/sse.subscribe                           │
│  - Observability Port: /k0/obs.emit                      │
│  - Health: /healthz, /readyz, /metrics                   │
└───────────────────┬──────────────────────────────────────┘
                    │
       ┌────────────┼────────────┐
       │            │            │
       ▼            ▼            ▼
┌──────────┐ ┌──────────┐ ┌──────────┐
│Embedding │ │   FTS    │ │  Neo4j   │
│ Worker   │ │ Worker   │ │ Knowledge│
│          │ │          │ │  Graph   │
└──────────┘ └──────────┘ └──────────┘
       │            │            │
       └────────────┼────────────┘
                    │
                    ▼
            ┌───────────────┐
            │ SQLite WAL DB │
            │  (ACID Core)  │
            └───────────────┘
```

### 1.2 Data Flow

1. **Ingest**: Envelope arrives at Command Port → MinimalGate validation
2. **Durability**: WAL write (FULL sync, ~3ms P95) → Receipt issued
3. **Async Processing**: Outbox entries for embedding/FTS workers
4. **Query**: Query Port reads from WAL/receipts tables
5. **Streaming**: SSE Port streams events with cursor tracking

### 1.3 Key Characteristics

| Characteristic | Implementation | Production Impact |
|----------------|----------------|-------------------|
| **Durability** | SQLite WAL + FULL sync | Zero data loss on crash |
| **Latency** | P95 <100ms (submit→receipt) | Real-time envelope processing |
| **Throughput** | 10k+ events/s replay | High-volume batch ingestion |
| **Scalability** | Read replicas, outbox workers | Horizontal worker scaling |
| **Observability** | Prometheus + OpenTelemetry | Full-stack tracing/metrics |

---

## 2. Deployment Models

### 2.1 Single-Node (Development/Small Production)

**Use Case:** <10k envelopes/day, single-tenant, development/staging

**Architecture:**

```
┌──────────────────────────────────────┐
│         Docker Host                  │
│  ┌──────────────────────────┐        │
│  │   k0-kernel container    │        │
│  │   - Port 8080            │        │
│  │   - SQLite volume        │        │
│  └──────────────────────────┘        │
│  ┌──────────────────────────┐        │
│  │ Embedding Worker         │        │
│  └──────────────────────────┘        │
│  ┌──────────────────────────┐        │
│  │ FTS Worker               │        │
│  └──────────────────────────┘        │
│  ┌──────────────────────────┐        │
│  │ Neo4j (optional)         │        │
│  └──────────────────────────┘        │
│  ┌──────────────────────────┐        │
│  │ Observability Stack      │        │
│  │ - Prometheus             │        │
│  │ - Grafana                │        │
│  │ - Tempo (tracing)        │        │
│  └──────────────────────────┘        │
└──────────────────────────────────────┘
```

**Pros:**

- Simple deployment (Docker Compose)
- Low operational overhead
- Cost-effective (<$50/month)

**Cons:**

- Single point of failure
- Limited scalability
- No high availability

**Performance:**

- Throughput: ~1k envelopes/second
- Latency: P95 <10ms (command), P95 <50ms (query)
- Storage: SQLite handles 100GB+ databases

### 2.2 Multi-Node (High Availability)

**Use Case:** >100k envelopes/day, multi-tenant, SLA requirements

**Architecture:**

```
┌──────────────────────────────────────────────────────────┐
│                    Load Balancer (NGINX)                 │
│              - TLS termination                           │
│              - Rate limiting                             │
└───────────┬──────────────────────────────────────────────┘
            │
   ┌────────┼────────┐
   │        │        │
   ▼        ▼        ▼
┌─────┐  ┌─────┐  ┌─────┐
│ K0  │  │ K0  │  │ K0  │  (Read replicas for queries)
│ RO  │  │ RO  │  │ RO  │
└─────┘  └─────┘  └─────┘
   │        │        │
   └────────┼────────┘
            │
            ▼
      ┌──────────┐
      │   K0     │  (Primary for writes)
      │ Primary  │
      │  (WAL)   │
      └──────────┘
            │
      ┌─────┴─────┐
      │           │
      ▼           ▼
┌──────────┐  ┌──────────┐
│ Embedding│  │   FTS    │  (Horizontal scaling)
│  Worker  │  │  Worker  │
│  Pool    │  │  Pool    │
└──────────┘  └──────────┘
```

**Pros:**

- High availability (99.9% SLA)
- Horizontal scaling (workers)
- Read replicas for query load

**Cons:**

- Complex deployment (Kubernetes recommended)
- Higher cost ($500-1000/month)
- Requires orchestration

**Performance:**

- Throughput: 10k+ envelopes/second
- Latency: P95 <100ms (command), P95 <250ms (query)
- Storage: Distributed via replicas

### 2.3 Deployment Comparison

| Aspect | Single-Node | Multi-Node |
|--------|-------------|------------|
| **Availability** | ~99% (single host) | 99.9% (replicas) |
| **Scalability** | Vertical only | Horizontal workers |
| **Cost** | $50-100/month | $500-1000/month |
| **Complexity** | Low (Docker Compose) | High (Kubernetes) |
| **Throughput** | 1k events/s | 10k+ events/s |
| **Recovery Time** | 5-15 minutes | <1 minute (failover) |

---

## 3. Prerequisites

### 3.1 Infrastructure Requirements

**Single-Node:**

| Resource | Minimum | Recommended | Notes |
|----------|---------|-------------|-------|
| CPU | 2 cores | 4 cores | Embedding models CPU-intensive |
| Memory | 4GB RAM | 8GB RAM | sentence-transformers requires ~2GB |
| Storage | 20GB SSD | 100GB SSD | SQLite WAL + model cache |
| Network | 100 Mbps | 1 Gbps | For envelope ingestion |

**Multi-Node (per K0 instance):**

| Resource | Minimum | Recommended | Notes |
|----------|---------|-------------|-------|
| CPU | 4 cores | 8 cores | Higher throughput |
| Memory | 8GB RAM | 16GB RAM | Multiple workers |
| Storage | 50GB SSD | 200GB SSD | Replica lag consideration |
| Network | 1 Gbps | 10 Gbps | Multi-node replication |

### 3.2 Software Requirements

**Operating System:**

- Ubuntu 22.04 LTS (recommended)
- Debian 11+
- RHEL 8+
- Windows Server 2019+ (Docker Desktop)

**Container Runtime:**

- Docker 24.0+ with Compose V2
- Kubernetes 1.28+ (for multi-node)

**Database:**

- SQLite 3.45+ (bundled with Python 3.12+)

**Python:**

- Python 3.12+ (3.13 recommended)

**External Services (Optional):**

- Neo4j 5.20+ (for knowledge graph features)
- Prometheus 2.45+
- Grafana 10.0+
- Tempo 2.2+ (distributed tracing)

### 3.3 Network Requirements

**Inbound Ports:**

| Port | Service | Protocol | Access |
|------|---------|----------|--------|
| 8080 | K0 Kernel | HTTP | Public/Private |
| 9090 | Prometheus | HTTP | Internal |
| 3000 | Grafana | HTTP | Internal/VPN |
| 7687 | Neo4j Bolt | TCP | Internal |
| 4317 | OTLP gRPC | gRPC | Internal |

**Outbound:**

- HTTPS (443) for OpenAI API (if using OpenAI embeddings)
- NTP (123) for time synchronization

### 3.4 TLS/SSL Certificates

**Production Requirements:**

- Valid TLS certificate (Let's Encrypt or commercial CA)
- Certificate rotation automation
- mTLS for inter-service communication (optional)

**Certificate Locations:**

- `/secrets/tls.crt` - Server certificate
- `/secrets/tls.key` - Private key
- `/secrets/ca.crt` - CA bundle (for mTLS)

---

## 4. Docker Compose Deployment

### 4.1 Directory Structure

```
k0/deploy/
├── docker-compose.yml               # Core services
├── local-single-node-telemetry.yml  # Observability stack
├── env/
│   └── k0.env                       # Environment variables
├── data/
│   └── k0_kernel.db                # SQLite database (auto-created)
├── secrets/
│   ├── tls.crt                     # TLS certificate
│   ├── tls.key                     # TLS private key
│   └── signing_key.pem             # Envelope signing key
├── config/
│   └── kernel.yaml                 # K0 configuration
├── generated/
│   ├── dashboards/                 # Grafana dashboards
│   └── rules/                      # Prometheus alert rules
└── telemetry/
    ├── prometheus.yml              # Prometheus config
    ├── grafana/                    # Grafana provisioning
    └── tempo.yaml                  # Tempo tracing config
```

### 4.2 Configuration Files

**`docker-compose.yml`** (production-ready):

```yaml
version: "3.8"

services:
  k0-kernel:
    image: k0-kernel:1.0.0
    container_name: k0-kernel
    restart: unless-stopped

    env_file:
      - ./env/k0.env

    environment:
      - K0_KERNEL_DATABASE__PATH=/data/k0_kernel.db
      - K0_KERNEL_SERVER__LOG_LEVEL=info
      - K0_KERNEL_SERVER__PORT=8080
      - K0_KERNEL_TELEMETRY__OTLP_ENDPOINT=http://tempo:4317
      - K0_KERNEL_TELEMETRY__PROMETHEUS_ENABLED=true

    volumes:
      - ./data:/data
      - ./secrets:/secrets:ro
      - ./config/kernel.yaml:/app/k0/config/kernel.yaml:ro

    ports:
      - "8080:8080"

    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/healthz"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 60s

    networks:
      - k0-network

    deploy:
      resources:
        limits:
          cpus: '4'
          memory: 4G
        reservations:
          cpus: '2'
          memory: 2G

  embedding-worker:
    image: k0-kernel:1.0.0
    container_name: k0-embedding-worker
    restart: unless-stopped
    command: ["python", "-m", "k0.workers.embedding_worker"]

    env_file:
      - ./env/k0.env

    environment:
      - K0_KERNEL_DATABASE__PATH=/data/k0_kernel.db
      - K0_EMBEDDING_BACKEND=sentence-transformers

    volumes:
      - ./data:/data:ro
      - ./config/embeddings.yml:/app/k0/config/embeddings.yml:ro

    depends_on:
      k0-kernel:
        condition: service_healthy

    networks:
      - k0-network

    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 4G
        reservations:
          cpus: '1'
          memory: 2G

  fts-worker:
    image: k0-kernel:1.0.0
    container_name: k0-fts-worker
    restart: unless-stopped
    command: ["python", "-m", "k0.workers.fts_worker"]

    env_file:
      - ./env/k0.env

    environment:
      - K0_KERNEL_DATABASE__PATH=/data/k0_kernel.db

    volumes:
      - ./data:/data:ro

    depends_on:
      k0-kernel:
        condition: service_healthy

    networks:
      - k0-network

    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 2G
        reservations:
          cpus: '1'
          memory: 1G

  neo4j:
    image: neo4j:5.20.0
    container_name: k0-neo4j
    restart: unless-stopped

    environment:
      - NEO4J_AUTH=neo4j/${NEO4J_PASSWORD}
      - NEO4J_dbms_memory_heap_initial__size=512M
      - NEO4J_dbms_memory_heap_max__size=2G
      - NEO4J_dbms_memory_pagecache_size=1G
      - NEO4J_ACCEPT_LICENSE_AGREEMENT=yes

    volumes:
      - neo4j-data:/data
      - neo4j-logs:/logs

    ports:
      - "7474:7474"
      - "7687:7687"

    healthcheck:
      test: ["CMD-SHELL", "wget --spider http://localhost:7474 || exit 1"]
      interval: 30s
      timeout: 10s
      retries: 5
      start_period: 60s

    networks:
      - k0-network

volumes:
  neo4j-data:
  neo4j-logs:

networks:
  k0-network:
    driver: bridge
```

**`local-single-node-telemetry.yml`** (observability stack):

```yaml
version: "3.8"

services:
  prometheus:
    image: prom/prometheus:v2.45.0
    container_name: k0-prometheus
    restart: unless-stopped

    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.path=/prometheus'
      - '--storage.tsdb.retention.time=30d'
      - '--web.enable-lifecycle'

    volumes:
      - ./telemetry/prometheus.yml:/etc/prometheus/prometheus.yml:ro
      - ./generated/rules:/etc/prometheus/rules:ro
      - prometheus-data:/prometheus

    ports:
      - "9090:9090"

    networks:
      - k0-network

    depends_on:
      - k0-kernel

  grafana:
    image: grafana/grafana:10.0.0
    container_name: k0-grafana
    restart: unless-stopped

    environment:
      - GF_SECURITY_ADMIN_PASSWORD=${GRAFANA_ADMIN_PASSWORD:-ChangeMe!}
      - GF_SERVER_ROOT_URL=https://grafana.yourdomain.com
      - GF_INSTALL_PLUGINS=grafana-piechart-panel

    volumes:
      - ./telemetry/grafana/provisioning:/etc/grafana/provisioning:ro
      - ./generated/dashboards:/var/lib/grafana/dashboards:ro
      - grafana-data:/var/lib/grafana

    ports:
      - "3000:3000"

    networks:
      - k0-network

    depends_on:
      - prometheus

  tempo:
    image: grafana/tempo:2.2.0
    container_name: k0-tempo
    restart: unless-stopped
    command: ["-config.file=/etc/tempo.yaml"]

    volumes:
      - ./telemetry/tempo.yaml:/etc/tempo.yaml:ro
      - tempo-data:/tmp/tempo

    ports:
      - "4317:4317"  # OTLP gRPC
      - "4318:4318"  # OTLP HTTP
      - "3200:3200"  # Tempo HTTP API

    networks:
      - k0-network

  alertmanager:
    image: prom/alertmanager:v0.26.0
    container_name: k0-alertmanager
    restart: unless-stopped

    command:
      - '--config.file=/etc/alertmanager/config.yml'
      - '--storage.path=/alertmanager'

    volumes:
      - ./telemetry/alertmanager.yml:/etc/alertmanager/config.yml:ro
      - alertmanager-data:/alertmanager

    ports:
      - "9093:9093"

    networks:
      - k0-network

    depends_on:
      - prometheus

volumes:
  prometheus-data:
  grafana-data:
  tempo-data:
  alertmanager-data:

networks:
  k0-network:
    external: true
```

### 4.3 Deployment Steps

**Step 1: Prepare Environment**

```bash
# Clone K0 repository
git clone https://github.com/familyos/k0.git
cd k0/deploy

# Create required directories
mkdir -p data secrets config generated/dashboards generated/rules

# Set file permissions
chmod 700 secrets
chmod 755 data generated
```

**Step 2: Configure Environment Variables**

Create `env/k0.env`:

```bash
# K0 Kernel Configuration
K0_KERNEL_DATABASE__PATH=/data/k0_kernel.db
K0_KERNEL_SERVER__HOST=0.0.0.0
K0_KERNEL_SERVER__PORT=8080
K0_KERNEL_SERVER__LOG_LEVEL=info
K0_KERNEL_SERVER__TIMEOUT_GRACEFUL_SHUTDOWN=30

# Database Configuration
K0_DATABASE_WAL_MODE=true
K0_DATABASE_SYNCHRONOUS=FULL

# QoS Configuration
K0_QOS_SCHEDULER_PROFILE=balanced

# Telemetry Configuration
K0_KERNEL_TELEMETRY__OTLP_ENDPOINT=http://tempo:4317
K0_KERNEL_TELEMETRY__PROMETHEUS_ENABLED=true

# Embedding Worker Configuration
K0_EMBEDDING_BACKEND=sentence-transformers
K0_EMBEDDING_MODEL=all-mpnet-base-v2
K0_EMBEDDING_BATCH_SIZE=10
K0_EMBEDDING_POLL_INTERVAL_SEC=1.0

# Neo4j Configuration (if using knowledge graph)
NEO4J_PASSWORD=YourSecurePassword123!
K0_NEO4J_URI=bolt://neo4j:7687
K0_NEO4J_USER=neo4j

# OpenAI Configuration (if using OpenAI embeddings)
# OPENAI_API_KEY=sk-...

# Security Configuration
K0_SECURITY_KEY_ROTATION_GRACE_WINDOW_HOURS=24
K0_SECURITY_KEY_ROTATION_MAX_GRACE_HOURS=168

# Production Flags
K0_PEM_REDACTION_ENABLED=true
K0_PEM_AUDIT_ENABLED=true
K0_PEM_METRICS_ENABLED=true
```

**Step 3: Generate TLS Certificates**

```bash
# Using Let's Encrypt (recommended)
certbot certonly --standalone -d k0.yourdomain.com
cp /etc/letsencrypt/live/k0.yourdomain.com/fullchain.pem secrets/tls.crt
cp /etc/letsencrypt/live/k0.yourdomain.com/privkey.pem secrets/tls.key
chmod 600 secrets/tls.key

# Or self-signed for testing
openssl req -x509 -newkey rsa:4096 -keyout secrets/tls.key -out secrets/tls.crt -days 365 -nodes -subj "/CN=k0.local"
```

**Step 4: Initialize Database**

```bash
# Create Docker network
docker network create k0-network

# Run database migrations
docker run --rm \
  -v "$(pwd)/data:/data" \
  k0-kernel:1.0.0 \
  python -m k0.cli.k0ctl migrate

# Verify database created
ls -lh data/k0_kernel.db
# Expected: k0_kernel.db, k0_kernel.db-wal, k0_kernel.db-shm
```

**Step 5: Deploy Services**

```bash
# Start K0 kernel and workers
docker compose up -d

# Verify services running
docker compose ps

# Expected output:
# k0-kernel              running (healthy)
# k0-embedding-worker    running
# k0-fts-worker          running
# k0-neo4j               running (healthy)

# Check logs
docker compose logs -f k0-kernel
```

**Step 6: Deploy Observability Stack**

```bash
# Start Prometheus, Grafana, Tempo
docker compose -f local-single-node-telemetry.yml up -d

# Verify telemetry services
docker compose -f local-single-node-telemetry.yml ps

# Expected output:
# k0-prometheus    running
# k0-grafana       running
# k0-tempo         running
# k0-alertmanager  running
```

**Step 7: Verify Deployment**

```bash
# Health checks
curl -f http://localhost:8080/healthz
# Expected: {"status":"healthy","version":"1.0.0"}

curl -f http://localhost:8080/readyz
# Expected: {"status":"ready","checks":{"database":"ok","workers":"ok"}}

# Metrics endpoint
curl http://localhost:8080/metrics | grep k0_commands

# Grafana dashboard
open http://localhost:3000
# Login: admin / ChangeMe!
```

### 4.4 Production Hardening

**Enable TLS:**

Add NGINX reverse proxy:

```yaml
# nginx.conf
upstream k0_backend {
    server localhost:8080;
}

server {
    listen 443 ssl http2;
    server_name k0.yourdomain.com;

    ssl_certificate /secrets/tls.crt;
    ssl_certificate_key /secrets/tls.key;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    location / {
        proxy_pass http://k0_backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

**Enable Rate Limiting:**

```yaml
# Add to docker-compose.yml
    environment:
      - K0_KERNEL_RATE_LIMIT_PER_TENANT_PER_SEC=500
      - K0_KERNEL_RATE_LIMIT_BURST=1000
```

---

## 5. Kubernetes Deployment

### 5.1 Architecture

```
┌─────────────────────────────────────────────────────┐
│              Kubernetes Cluster                     │
│                                                     │
│  ┌────────────────────────────────────────────┐   │
│  │         Ingress (NGINX)                     │   │
│  │  - TLS termination                          │   │
│  │  - Rate limiting                            │   │
│  └────────────┬───────────────────────────────┘   │
│               │                                    │
│  ┌────────────┴───────────────────────────────┐   │
│  │  K0 Service (ClusterIP)                     │   │
│  │  - Load balancing                           │   │
│  └────────────┬───────────────────────────────┘   │
│               │                                    │
│  ┌────────────┴───────────────────────────────┐   │
│  │  K0 Deployment (3 replicas)                 │   │
│  │  ┌──────┐  ┌──────┐  ┌──────┐              │   │
│  │  │ K0-1 │  │ K0-2 │  │ K0-3 │              │   │
│  │  └──────┘  └──────┘  └──────┘              │   │
│  └────────────────────────────────────────────┘   │
│                                                     │
│  ┌────────────────────────────────────────────┐   │
│  │  Worker Deployments                         │   │
│  │  ┌──────────────┐  ┌──────────────┐        │   │
│  │  │ Embedding    │  │    FTS       │        │   │
│  │  │ (5 replicas) │  │ (3 replicas) │        │   │
│  │  └──────────────┘  └──────────────┘        │   │
│  └────────────────────────────────────────────┘   │
│                                                     │
│  ┌────────────────────────────────────────────┐   │
│  │  StatefulSet                                │   │
│  │  ┌──────────┐                               │   │
│  │  │  Neo4j   │                               │   │
│  │  │ (1 replica)                              │   │
│  │  └──────────┘                               │   │
│  └────────────────────────────────────────────┘   │
│                                                     │
│  ┌────────────────────────────────────────────┐   │
│  │  PVC (Persistent Volume Claim)              │   │
│  │  - SQLite database storage                  │   │
│  │  - 100Gi SSD                                │   │
│  └────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────┘
```

### 5.2 Kubernetes Manifests

**`k8s/namespace.yaml`:**

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: k0-system
  labels:
    name: k0-system
```

**`k8s/configmap.yaml`:**

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: k0-config
  namespace: k0-system
data:
  kernel.yaml: |
    version: 1.0.0
    environment: production
    server:
      host: "0.0.0.0"
      port: 8080
      log_level: info
      timeout_graceful_shutdown: 30
    retention:
      default:
        wal_days: 30
        wal_max_events: 50000000
    qos:
      scheduler_profile: balanced
    security:
      key_rotation_grace_window_hours: 24
    telemetry:
      otlp_endpoint: "http://tempo.k0-system.svc.cluster.local:4317"
      prometheus_enabled: true

  embeddings.yml: |
    default_backend: "sentence-transformers"
    backends:
      sentence-transformers:
        model: "all-mpnet-base-v2"
        device: "cpu"
        batch_size: 32
        normalize_embeddings: true
    worker:
      batch_size: 10
      poll_interval_sec: 1.0
      max_retries: 3
```

**`k8s/secret.yaml`:**

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: k0-secrets
  namespace: k0-system
type: Opaque
data:
  # Base64-encoded values
  NEO4J_PASSWORD: <base64-encoded-password>
  OPENAI_API_KEY: <base64-encoded-key>
  TLS_CRT: <base64-encoded-cert>
  TLS_KEY: <base64-encoded-key>
```

**`k8s/pvc.yaml`:**

```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: k0-data
  namespace: k0-system
spec:
  accessModes:
    - ReadWriteOnce
  storageClassName: fast-ssd
  resources:
    requests:
      storage: 100Gi
```

**`k8s/deployment.yaml`:**

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: k0-kernel
  namespace: k0-system
  labels:
    app: k0-kernel
spec:
  replicas: 3
  selector:
    matchLabels:
      app: k0-kernel
  template:
    metadata:
      labels:
        app: k0-kernel
      annotations:
        prometheus.io/scrape: "true"
        prometheus.io/port: "8080"
        prometheus.io/path: "/metrics"
    spec:
      containers:
      - name: k0-kernel
        image: k0-kernel:1.0.0
        imagePullPolicy: Always

        ports:
        - containerPort: 8080
          name: http
          protocol: TCP

        env:
        - name: K0_KERNEL_DATABASE__PATH
          value: "/data/k0_kernel.db"
        - name: K0_KERNEL_SERVER__LOG_LEVEL
          value: "info"
        - name: K0_KERNEL_TELEMETRY__OTLP_ENDPOINT
          value: "http://tempo.k0-system.svc.cluster.local:4317"
        - name: NEO4J_PASSWORD
          valueFrom:
            secretKeyRef:
              name: k0-secrets
              key: NEO4J_PASSWORD

        volumeMounts:
        - name: k0-data
          mountPath: /data
        - name: config
          mountPath: /app/k0/config
        - name: secrets
          mountPath: /secrets
          readOnly: true

        livenessProbe:
          httpGet:
            path: /healthz
            port: 8080
          initialDelaySeconds: 60
          periodSeconds: 30
          timeoutSeconds: 5
          failureThreshold: 3

        readinessProbe:
          httpGet:
            path: /readyz
            port: 8080
          initialDelaySeconds: 30
          periodSeconds: 10
          timeoutSeconds: 5
          failureThreshold: 3

        resources:
          requests:
            cpu: "2000m"
            memory: "4Gi"
          limits:
            cpu: "4000m"
            memory: "8Gi"

      volumes:
      - name: k0-data
        persistentVolumeClaim:
          claimName: k0-data
      - name: config
        configMap:
          name: k0-config
      - name: secrets
        secret:
          secretName: k0-secrets
```

**`k8s/service.yaml`:**

```yaml
apiVersion: v1
kind: Service
metadata:
  name: k0-kernel
  namespace: k0-system
  labels:
    app: k0-kernel
spec:
  type: ClusterIP
  selector:
    app: k0-kernel
  ports:
  - port: 8080
    targetPort: 8080
    protocol: TCP
    name: http
```

**`k8s/ingress.yaml`:**

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: k0-ingress
  namespace: k0-system
  annotations:
    cert-manager.io/cluster-issuer: "letsencrypt-prod"
    nginx.ingress.kubernetes.io/rate-limit: "500"
    nginx.ingress.kubernetes.io/ssl-redirect: "true"
spec:
  ingressClassName: nginx
  tls:
  - hosts:
    - k0.yourdomain.com
    secretName: k0-tls
  rules:
  - host: k0.yourdomain.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: k0-kernel
            port:
              number: 8080
```

### 5.3 Worker Deployments

**`k8s/worker-embedding.yaml`:**

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: k0-embedding-worker
  namespace: k0-system
spec:
  replicas: 5
  selector:
    matchLabels:
      app: k0-embedding-worker
  template:
    metadata:
      labels:
        app: k0-embedding-worker
    spec:
      containers:
      - name: embedding-worker
        image: k0-kernel:1.0.0
        command: ["python", "-m", "k0.workers.embedding_worker"]

        env:
        - name: K0_KERNEL_DATABASE__PATH
          value: "/data/k0_kernel.db"
        - name: K0_EMBEDDING_BACKEND
          value: "sentence-transformers"

        volumeMounts:
        - name: k0-data
          mountPath: /data
          readOnly: true
        - name: config
          mountPath: /app/k0/config

        resources:
          requests:
            cpu: "1000m"
            memory: "2Gi"
          limits:
            cpu: "2000m"
            memory: "4Gi"

      volumes:
      - name: k0-data
        persistentVolumeClaim:
          claimName: k0-data
      - name: config
        configMap:
          name: k0-config
```

**`k8s/worker-fts.yaml`:**

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: k0-fts-worker
  namespace: k0-system
spec:
  replicas: 3
  selector:
    matchLabels:
      app: k0-fts-worker
  template:
    metadata:
      labels:
        app: k0-fts-worker
    spec:
      containers:
      - name: fts-worker
        image: k0-kernel:1.0.0
        command: ["python", "-m", "k0.workers.fts_worker"]

        env:
        - name: K0_KERNEL_DATABASE__PATH
          value: "/data/k0_kernel.db"

        volumeMounts:
        - name: k0-data
          mountPath: /data
          readOnly: true

        resources:
          requests:
            cpu: "500m"
            memory: "1Gi"
          limits:
            cpu: "1000m"
            memory: "2Gi"

      volumes:
      - name: k0-data
        persistentVolumeClaim:
          claimName: k0-data
```

### 5.4 Deployment Commands

```bash
# Create namespace
kubectl apply -f k8s/namespace.yaml

# Create secrets (encode values first)
echo -n "YourSecurePassword123!" | base64
kubectl apply -f k8s/secret.yaml

# Create ConfigMap
kubectl apply -f k8s/configmap.yaml

# Create PVC
kubectl apply -f k8s/pvc.yaml

# Deploy K0 kernel
kubectl apply -f k8s/deployment.yaml

# Create Service
kubectl apply -f k8s/service.yaml

# Deploy workers
kubectl apply -f k8s/worker-embedding.yaml
kubectl apply -f k8s/worker-fts.yaml

# Create Ingress
kubectl apply -f k8s/ingress.yaml

# Verify deployment
kubectl get pods -n k0-system
kubectl get svc -n k0-system
kubectl get ingress -n k0-system

# Check logs
kubectl logs -n k0-system -l app=k0-kernel --tail=100
```

---

## 6. Configuration Management

### 6.1 Environment Variables

**Core K0 Variables:**

| Variable | Default | Description |
|----------|---------|-------------|
| `K0_KERNEL_DATABASE__PATH` | `/data/k0_kernel.db` | SQLite database path |
| `K0_KERNEL_SERVER__HOST` | `0.0.0.0` | Bind address |
| `K0_KERNEL_SERVER__PORT` | `8080` | HTTP port |
| `K0_KERNEL_SERVER__LOG_LEVEL` | `info` | Logging level |
| `K0_DATABASE_WAL_MODE` | `true` | Enable WAL mode |
| `K0_DATABASE_SYNCHRONOUS` | `FULL` | Durability level |

**Worker Variables:**

| Variable | Default | Description |
|----------|---------|-------------|
| `K0_EMBEDDING_BACKEND` | `sentence-transformers` | Backend type |
| `K0_EMBEDDING_MODEL` | `all-mpnet-base-v2` | Model name |
| `K0_EMBEDDING_BATCH_SIZE` | `10` | Batch size |
| `K0_EMBEDDING_POLL_INTERVAL_SEC` | `1.0` | Poll interval |

**Telemetry Variables:**

| Variable | Default | Description |
|----------|---------|-------------|
| `K0_KERNEL_TELEMETRY__OTLP_ENDPOINT` | `null` | OTLP gRPC endpoint |
| `K0_KERNEL_TELEMETRY__PROMETHEUS_ENABLED` | `true` | Expose /metrics |

### 6.2 Configuration Hot Reload

K0 supports hot reload for configuration changes without restart:

```bash
# Using k0ctl CLI
k0ctl config reload

# Using Docker Compose
docker compose exec k0-kernel kill -SIGHUP 1

# Using Kubernetes
kubectl exec -n k0-system <pod-name> -- kill -SIGHUP 1
```

**Hot-Reloadable Settings:**

- Log level
- QoS scheduler profile
- Telemetry endpoints
- Rate limits

**Requires Restart:**

- Database path
- Server port
- TLS certificates

---

## 7. Security Hardening

### 7.1 TLS/mTLS

**Configure TLS in NGINX:**

```nginx
server {
    listen 443 ssl http2;
    server_name k0.yourdomain.com;

    ssl_certificate /secrets/tls.crt;
    ssl_certificate_key /secrets/tls.key;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers 'ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256';
    ssl_prefer_server_ciphers on;

    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;

    location / {
        proxy_pass http://k0-kernel:8080;
    }
}
```

**Enable mTLS for Worker Communication:**

```yaml
# Add to docker-compose.yml
    environment:
      - K0_MTLS_ENABLED=true
      - K0_MTLS_CA_CERT=/secrets/ca.crt
      - K0_MTLS_CLIENT_CERT=/secrets/client.crt
      - K0_MTLS_CLIENT_KEY=/secrets/client.key
```

### 7.2 Secrets Management

**Using Kubernetes Secrets:**

```bash
# Create secret from files
kubectl create secret generic k0-secrets \
  --from-file=tls.crt=secrets/tls.crt \
  --from-file=tls.key=secrets/tls.key \
  --from-literal=neo4j-password=YourSecurePassword123! \
  -n k0-system
```

**Using HashiCorp Vault:**

```yaml
# vault-secrets-operator.yaml
apiVersion: secrets.hashicorp.com/v1beta1
kind: VaultAuth
metadata:
  name: k0-vault-auth
  namespace: k0-system
spec:
  method: kubernetes
  mount: kubernetes
  kubernetes:
    role: k0-role
    serviceAccount: k0-sa
```

### 7.3 Network Policies

**Restrict Pod Communication:**

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: k0-network-policy
  namespace: k0-system
spec:
  podSelector:
    matchLabels:
      app: k0-kernel
  policyTypes:
  - Ingress
  - Egress
  ingress:
  - from:
    - podSelector:
        matchLabels:
          app: nginx-ingress
    ports:
    - protocol: TCP
      port: 8080
  egress:
  - to:
    - podSelector:
        matchLabels:
          app: neo4j
    ports:
    - protocol: TCP
      port: 7687
  - to:
    - podSelector:
        matchLabels:
          app: tempo
    ports:
    - protocol: TCP
      port: 4317
```

---

## 8. Monitoring & Observability

### 8.1 Key Metrics

**Kernel Metrics (Prometheus):**

```
# Command metrics
k0_commands_submitted_total{tenant, space}
k0_commands_successful_total{tenant, space}
k0_commands_failed_total{tenant, space, reason}
k0_command_latency_ms_bucket{tenant, space}

# Query metrics
k0_queries_total{tenant, space}
k0_query_latency_ms_bucket{tenant, space}

# SSE metrics
k0_sse_connections_active{tenant, space}
k0_sse_events_delivered_total{tenant, space, topic}

# Worker metrics
k0_embedding_worker_processed_total{status}
k0_embedding_worker_latency_ms_bucket
k0_fts_worker_processed_total{status}
k0_fts_worker_latency_ms_bucket

# Database metrics
k0_wal_size_bytes
k0_wal_checkpoints_total
k0_receipts_total
k0_outbox_pending_count
```

**Alert Rules (`generated/rules/slo_alerts.yaml`):**

```yaml
groups:
- name: k0_slo_alerts
  interval: 30s
  rules:
  - alert: K0HighCommandLatency
    expr: histogram_quantile(0.95, rate(k0_command_latency_ms_bucket[5m])) > 150
    for: 5m
    labels:
      severity: warning
    annotations:
      summary: "K0 command latency P95 exceeds 150ms"
      description: "P95 latency is {{ $value }}ms for {{ $labels.tenant }}/{{ $labels.space }}"

  - alert: K0HighErrorRate
    expr: rate(k0_commands_failed_total[5m]) / rate(k0_commands_submitted_total[5m]) > 0.05
    for: 5m
    labels:
      severity: critical
    annotations:
      summary: "K0 error rate exceeds 5%"

  - alert: K0WorkerBacklogGrowing
    expr: k0_outbox_pending_count > 1000
    for: 10m
    labels:
      severity: warning
    annotations:
      summary: "K0 worker backlog exceeds 1000 entries"
```

### 8.2 Grafana Dashboards

**K0 Kernel Overview Dashboard:**

- **Command Throughput**: Commands/second (submit, success, failure)
- **Latency Heatmap**: P50/P95/P99 latency distribution
- **Worker Status**: Embedding/FTS processed, queue depth
- **Database Health**: WAL size, checkpoint frequency
- **Error Rate**: Failure rate by reason

**Access Grafana:**

```bash
# Port-forward for local access
kubectl port-forward -n k0-system svc/grafana 3000:3000

# Open browser
open http://localhost:3000
```

### 8.3 Distributed Tracing

**Tempo Configuration:**

```yaml
# telemetry/tempo.yaml
server:
  http_listen_port: 3200

distributor:
  receivers:
    otlp:
      protocols:
        grpc:
          endpoint: 0.0.0.0:4317
        http:
          endpoint: 0.0.0.0:4318

storage:
  trace:
    backend: local
    local:
      path: /tmp/tempo/traces

querier:
  frontend_worker:
    frontend_address: localhost:9095
```

**Query Traces in Grafana:**

- Navigate to Explore → Tempo
- Search by trace ID or service name: `k0-kernel`
- Visualize end-to-end request flow

---

## 9. Backup & Disaster Recovery

### 9.1 Database Backup Strategy

**SQLite WAL Backup:**

```bash
# Create backup script (backup_k0.sh)
#!/bin/bash
BACKUP_DIR="/backups/k0"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
DB_PATH="/data/k0_kernel.db"

# Create backup directory
mkdir -p "$BACKUP_DIR"

# SQLite backup with WAL checkpoint
sqlite3 "$DB_PATH" <<EOF
PRAGMA wal_checkpoint(TRUNCATE);
.backup '$BACKUP_DIR/k0_kernel_${TIMESTAMP}.db'
EOF

# Compress backup
gzip "$BACKUP_DIR/k0_kernel_${TIMESTAMP}.db"

# Retain last 30 days
find "$BACKUP_DIR" -name "k0_kernel_*.db.gz" -mtime +30 -delete

echo "Backup complete: k0_kernel_${TIMESTAMP}.db.gz"
```

**Automated Backup (Cron):**

```bash
# Add to crontab
0 2 * * * /usr/local/bin/backup_k0.sh >> /var/log/k0_backup.log 2>&1
```

**Kubernetes CronJob:**

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: k0-backup
  namespace: k0-system
spec:
  schedule: "0 2 * * *"
  jobTemplate:
    spec:
      template:
        spec:
          containers:
          - name: backup
            image: k0-kernel:1.0.0
            command: ["/bin/bash", "-c"]
            args:
            - |
              TIMESTAMP=$(date +%Y%m%d_%H%M%S)
              sqlite3 /data/k0_kernel.db <<EOF
              PRAGMA wal_checkpoint(TRUNCATE);
              .backup '/backups/k0_kernel_${TIMESTAMP}.db'
              EOF
              gzip /backups/k0_kernel_${TIMESTAMP}.db
            volumeMounts:
            - name: k0-data
              mountPath: /data
            - name: backups
              mountPath: /backups
          restartPolicy: OnFailure
          volumes:
          - name: k0-data
            persistentVolumeClaim:
              claimName: k0-data
          - name: backups
            persistentVolumeClaim:
              claimName: k0-backups
```

### 9.2 Disaster Recovery

**Recovery Procedure:**

```bash
# Step 1: Stop K0 services
docker compose down

# Step 2: Restore database from backup
gunzip -c /backups/k0_kernel_20250110_020000.db.gz > data/k0_kernel.db

# Step 3: Verify database integrity
sqlite3 data/k0_kernel.db "PRAGMA integrity_check;"
# Expected: ok

# Step 4: Restart services
docker compose up -d

# Step 5: Verify health
curl http://localhost:8080/healthz
```

**Recovery Time Objective (RTO):**

- Single-node: 5-15 minutes
- Multi-node: <1 minute (failover to replica)

**Recovery Point Objective (RPO):**

- Hourly backups: 1 hour data loss max
- Continuous WAL: Zero data loss (crash recovery)

---

## 10. Performance Tuning

### 10.1 SQLite Optimization

**WAL Mode Settings:**

```sql
-- Apply at runtime
PRAGMA journal_mode=WAL;
PRAGMA synchronous=FULL;
PRAGMA cache_size=10000;
PRAGMA temp_store=memory;
PRAGMA mmap_size=30000000000;
PRAGMA page_size=4096;
```

**Checkpoint Tuning:**

```bash
# Add to k0.env
K0_WAL_AUTOCHECKPOINT=1000  # Checkpoint every 1000 pages
K0_WAL_CHECKPOINT_TIMEOUT_MS=5000
```

### 10.2 Worker Scaling

**Horizontal Scaling:**

```yaml
# Increase embedding worker replicas
replicas: 10

# Tune batch size for throughput
environment:
  - K0_EMBEDDING_BATCH_SIZE=50
  - K0_EMBEDDING_POLL_INTERVAL_SEC=0.5
```

**Performance Matrix:**

| Worker Count | Throughput | Latency (P95) | CPU | Memory |
|--------------|------------|---------------|-----|--------|
| 1 | 100/s | 200ms | 1 core | 2GB |
| 5 | 500/s | 150ms | 5 cores | 10GB |
| 10 | 1000/s | 100ms | 10 cores | 20GB |

### 10.3 Load Testing

**Using k6:**

```javascript
// load_test.js
import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  stages: [
    { duration: '2m', target: 100 },  // Ramp up
    { duration: '5m', target: 100 },  // Steady state
    { duration: '2m', target: 0 },    // Ramp down
  ],
  thresholds: {
    http_req_duration: ['p(95)<150'],  // P95 <150ms
    http_req_failed: ['rate<0.05'],    // <5% error rate
  },
};

export default function () {
  const envelope = {
    tenant_id: 'tenant-001',
    space_id: 'space-load-test',
    event_id: `evt-${__VU}-${__ITER}`,
    body: { text: 'Load test envelope' },
  };

  const res = http.post(
    'http://k0.yourdomain.com/k0/command.submit',
    JSON.stringify(envelope),
    { headers: { 'Content-Type': 'application/json' } }
  );

  check(res, {
    'status is 201': (r) => r.status === 201,
    'latency < 150ms': (r) => r.timings.duration < 150,
  });

  sleep(1);
}
```

**Run Load Test:**

```bash
k6 run --vus 100 --duration 10m load_test.js
```

---

## 11. Operations Runbook

### 11.1 Common Tasks

**Restart K0 Kernel:**

```bash
# Docker Compose
docker compose restart k0-kernel

# Kubernetes
kubectl rollout restart deployment/k0-kernel -n k0-system
```

**Scale Workers:**

```bash
# Docker Compose
docker compose up -d --scale embedding-worker=10

# Kubernetes
kubectl scale deployment/k0-embedding-worker --replicas=10 -n k0-system
```

**View Logs:**

```bash
# Docker Compose
docker compose logs -f k0-kernel --tail=100

# Kubernetes
kubectl logs -n k0-system -l app=k0-kernel --tail=100 -f
```

**Database Maintenance:**

```bash
# Checkpoint WAL
sqlite3 k0/deploy/data/k0_kernel.db "PRAGMA wal_checkpoint(TRUNCATE);"

# Vacuum database
sqlite3 k0/deploy/data/k0_kernel.db "VACUUM;"

# Check integrity
sqlite3 k0/deploy/data/k0_kernel.db "PRAGMA integrity_check;"
```

**Code Changes & Docker:**

```bash
# After modifying k0/security/crypto.py or other code files:
# 1. Rebuild Docker image (restart is NOT sufficient)
docker-compose build k0-kernel

# 2. Restart with new image
docker-compose up -d k0-kernel

# 3. Verify new code loaded
docker-compose logs k0-kernel | grep "crypto.py" | head -5
```

### 11.2 Incident Response

**High Latency:**

1. Check worker backlog: `k0_outbox_pending_count`
2. Scale workers: `kubectl scale deployment/k0-embedding-worker --replicas=15`
3. Review slow queries: `kubectl logs -n k0-system -l app=k0-kernel | grep "slow query"`

**Database Corruption:**

1. Stop K0: `docker compose down`
2. Restore from backup: `gunzip -c backup.db.gz > k0/deploy/data/k0_kernel.db`
3. Integrity check: `sqlite3 k0/deploy/data/k0_kernel.db "PRAGMA integrity_check;"`
4. Restart: `docker compose up -d`

**Signature Verification Failures:**

1. Verify signature algorithm is Ed25519 (industry-standard; SHA-512 is internal to Ed25519)
2. Check device keys: `SELECT verify_key FROM st_device_keys WHERE device_id = ? AND key_state = 'ACTIVE'`
3. Ensure `envelope_sha256` excluded from hash computation
4. Restart kernel to clear key cache: `docker compose restart k0-kernel`
5. Check `k0/security/crypto.py` excludes both `sig` and `envelope_sha256` from canonical envelope

**Memory Leak:**

1. Check memory usage: `docker stats k0-kernel`
2. Review logs: `docker compose logs k0-kernel | grep "MemoryError"`
3. Restart container: `docker compose restart k0-kernel`
4. Monitor: `kubectl top pod -n k0-system`

---

## 12. Troubleshooting

### 12.1 Common Issues

**Issue: "Database is locked"**

**Cause:** Multiple writers without WAL mode

**Solution:**

```bash
# Verify WAL mode enabled
sqlite3 /data/k0_kernel.db "PRAGMA journal_mode;"
# Expected: wal

# If not, enable WAL
sqlite3 /data/k0_kernel.db "PRAGMA journal_mode=WAL;"
```

**Issue: "Workers not processing"**

**Cause:** Outbox queue stalled

**Solution:**

```bash
# Check outbox table
sqlite3 /data/k0_kernel.db "SELECT COUNT(*) FROM st_outbox WHERE status='PENDING';"

# Restart workers
docker compose restart embedding-worker fts-worker
```

**Issue: "High memory usage"**

**Cause:** Embedding model cached in memory

**Solution:**

```bash
# Check memory
docker stats k0-kernel

# Reduce batch size
K0_EMBEDDING_BATCH_SIZE=5

# Restart with new settings
docker compose restart embedding-worker
```

### 12.2 Debug Mode

**Enable Debug Logging:**

```bash
# Set log level
K0_KERNEL_SERVER__LOG_LEVEL=debug

# Restart
docker compose restart k0-kernel

# View debug logs
docker compose logs -f k0-kernel | grep DEBUG
```

### 12.3 Health Check Failures

**Verify Health Endpoints:**

```bash
# Liveness (dependencies ready)
curl http://localhost:8080/healthz
# Expected: {"status":"healthy","version":"1.0.0"}

# Readiness (accepting requests)
curl http://localhost:8080/readyz
# Expected: {"status":"ready","checks":{"database":"ok","workers":"ok"}}

# Metrics (Prometheus)
curl http://localhost:8080/metrics | grep k0_commands
```

---

## Additional Resources

- **K0 README**: `k0/README.md` (2294 lines, complete architecture)
- **Integration Spec**: `docs/integration/k0_v1_integration_spec.md`
- **Quickstart Guide**: `docs/integration/quickstart.md`
- **Docker Compose**: `k0/deploy/docker-compose.yml`
- **Deployment README**: `k0/deploy/readme.md`
- **Performance Tests**: `tests/k0/integration/test_v1_performance.py`

**Support:**

- **GitHub Issues**: <https://github.com/familyos/k0/issues>
- **Documentation**: `docs/`
- **License**: Apache 2.0

---

**Congratulations!** You now have K0 deployed to production with:

- ✅ High availability architecture
- ✅ Full observability (Prometheus, Grafana, Tempo)
- ✅ Security hardening (TLS, mTLS, secrets management)
- ✅ Automated backups and disaster recovery
- ✅ Performance tuning and load testing
- ✅ Operational runbooks and troubleshooting guides

**Next**: Integrate external systems using `docs/integration/k0_v1_integration_spec.md`
