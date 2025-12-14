# K0 Developer Quickstart Guide

**Version:** 1.0.0
**Date:** 2025-11-10
**Audience:** Developers integrating with K0

## Overview

This guide walks you through setting up K0, submitting your first envelope, and querying results. By the end, you'll have:

- K0 running locally with SQLite backend
- Verified envelope submission and receipt
- Working query integration
- Understanding of async workers (embedding & FTS)

**Time to complete:** 30-45 minutes

---

## 1. Prerequisites

### 1.1 System Requirements

| Requirement | Version | Notes |
|-------------|---------|-------|
| Python | 3.12+ | 3.13 recommended |
| SQLite | 3.45+ | Included with Python |
| Operating System | Windows/Linux/macOS | Windows PowerShell examples shown |
| Memory | 2GB+ RAM | 4GB recommended for embedding workers |
| Disk | 500MB free | For SQLite database and dependencies |

### 1.2 Required Tools

- **Python 3.12+**: `python --version`
- **Git**: For cloning K0 repository (optional if using package)
- **Virtual Environment**: `venv` or `conda`
- **Code Editor**: VS Code, PyCharm, or similar

### 1.3 Optional (for Production)

- **Docker**: For containerized deployment
- **Prometheus**: For metrics collection
- **Grafana**: For observability dashboards

---

## 2. Installation

### 2.1 Clone K0 Repository

```powershell
# Clone repository
git clone https://github.com/familyos/k0.git
cd k0

# Or download release package
# wget https://releases.k0.example.com/k0-v1.0.0.tar.gz
# tar -xzf k0-v1.0.0.tar.gz
# cd k0-v1.0.0
```

### 2.2 Create Virtual Environment

```powershell
# Create virtual environment
python -m venv .venv

# Activate (Windows PowerShell)
.\.venv\Scripts\Activate.ps1

# Activate (Linux/macOS)
# source .venv/bin/activate

# Verify activation
python --version  # Should show Python 3.12+
```

### 2.3 Install Dependencies

```powershell
# Install K0 core dependencies
python -m pip install -r requirements.txt

# Install development dependencies (optional)
# python -m pip install -r requirements-dev.txt

# Verify installation
python -c "import fastapi, uvicorn; print('FastAPI + Uvicorn OK')"
python -c "import nltk, sentence_transformers; print('NLP + Embeddings OK')"
```

### 2.4 Download NLTK Data

```powershell
# Required for FTS worker
python -c "import nltk; nltk.download('punkt'); nltk.download('punkt_tab'); nltk.download('stopwords'); nltk.download('wordnet')"

# Verify NLTK data
python -c "from nltk.corpus import stopwords; print(f'NLTK stopwords: {len(stopwords.words(\"english\"))} English')"
# Expected: NLTK stopwords: 179 English
```

---

## 3. Configuration

### 3.1 Database Setup

K0 uses SQLite with WAL mode for durability:

```powershell
# Create database directory
mkdir -p data

# Initialize database (applies migrations)
python -m k0.cli.k0ctl migrate

# Verify database created
ls data/k0_kernel.db
# Expected: k0_kernel.db, k0_kernel.db-shm, k0_kernel.db-wal
```

**Database Schema:**

- `st_wal` - Write-Ahead Log (append-only)
- `st_receipts` - Commit receipts with signatures
- `st_outbox` - Async work queue (embeddings, FTS)
- `st_offsets` - SSE subscriber cursors
- `idem_ledger` - Idempotency keys (24-hour window)
- `schema_registry` - Schema versions and status

### 3.2 Configuration Files

K0 uses YAML configuration files in `k0/config/`:

**`k0/config/kernel.yaml`** (Core configuration):

```yaml
server:
  host: "127.0.0.1"  # Local development
  port: 8080
  log_level: "info"  # Options: debug, info, warning, error
  timeout_graceful_shutdown: 30

database:
  path: "data/k0_kernel.db"
  wal_mode: true
  synchronous: "FULL"  # Durability guarantee

gate_caps:
  max_envelope_bytes: 64000  # 64 KB
  max_body_bytes: 4194304    # 4 MB

signature_budget:
  per_tenant_per_sec: 500
  burst: 1000
```

**`k0/config/embeddings.yml`** (Embedding backends):

```yaml
# Default backend for embeddings
default_backend: "sentence-transformers"

backends:
  sentence-transformers:
    model: "all-mpnet-base-v2"  # 768 dimensions
    device: "cpu"  # or "cuda" for GPU
    batch_size: 32
    normalize_embeddings: true

  openai:
    model: "text-embedding-3-small"  # Requires OPENAI_API_KEY
    rate_limit_rpm: 3000
    timeout_sec: 30

  fake:
    model: "fake-minilm-l6"  # Testing only
    dimension: 384

worker:
  batch_size: 10
  poll_interval_sec: 1.0
  max_retries: 3
```

### 3.3 Environment Variables

```powershell
# Required
$env:K0_KERNEL_DATABASE__PATH = "data/k0_kernel.db"

# Optional (for OpenAI embeddings)
# $env:OPENAI_API_KEY = "sk-..."

# Optional (logging level override)
# $env:K0_KERNEL_SERVER__LOG_LEVEL = "debug"

# Verify environment
python -c "import os; print(f'DB Path: {os.getenv(\"K0_KERNEL_DATABASE__PATH\", \"default\")}')"
```

---

## 4. Start K0 Server

### 4.1 Start Kernel

```powershell
# Start K0 server (foreground)
python -m k0.cli.k0ctl serve --host 127.0.0.1 --log-level info

# Expected output:
# INFO: Started server process [12345]
# INFO: Waiting for application startup.
# INFO: Application startup complete.
# INFO: Uvicorn running on http://127.0.0.1:8080 (Press CTRL+C to quit)
```

**Verify Server Running:**
```powershell
# Health check (in new terminal)
curl http://localhost:8080/healthz

# Expected response:
# {"status":"healthy","version":"1.0.0","timestamp_ms":1699660800000}
```

### 4.2 Start Async Workers (Optional)

K0 V1 includes async workers for embeddings and FTS indexing. Start them in separate terminals:

**Embedding Worker:**

```powershell
# Terminal 2: Start embedding worker
python -m k0.workers.embedding_worker

# Expected output:
# [INFO] EmbeddingWorker started (backend=sentence-transformers, model=all-mpnet-base-v2)
# [INFO] Loading sentence-transformers model...
# [INFO] Model loaded (768 dimensions)
# [INFO] Polling Outbox for embedding work...
```

**FTS Indexing Worker:**

```powershell
# Terminal 3: Start FTS indexing worker
python -m k0.workers.fts_worker

# Expected output:
# [INFO] FtsIndexingWorker started (batch_size=50)
# [INFO] NLTK initialized (179 English stop words, Porter stemmer)
# [INFO] Polling Outbox for FTS work...
```

---

## 5. Your First Envelope

### 5.1 Generate Signing Key

K0 requires Ed25519 signatures (industry-standard Ed25519 algorithm). Generate keys using Python:

```python
# generate_keys.py
from nacl.signing import SigningKey
from k0.security.crypto import encode_base64url

# Generate Ed25519 key pair
signing_key = SigningKey.generate()
verify_key = signing_key.verify_key

# Save private key (keep secure)
with open("private_key.pem", "wb") as f:
    f.write(signing_key.encode())
print("Private key saved to private_key.pem")

# Save public key (base64url encoded)
verify_key_b64 = encode_base64url(verify_key.encode())
with open("public_key.txt", "w") as f:
    f.write(verify_key_b64)
print(f"Public key (base64url): {verify_key_b64}")
```

```powershell
# Run the key generation script
python generate_keys.py
# Expected: Keys saved to private_key.pem and public_key.txt
```

### 5.2 Create Python Client Script

Create `submit_envelope.py`:

```python
"""
K0 Envelope Submission Example
Demonstrates signing and submitting envelopes to K0.
"""

import uuid
from datetime import datetime, timezone
from pathlib import Path

import requests
from nacl.signing import SigningKey

from k0.idem import derive_idem_key
from k0.security import canonical_json, hash_payload, compute_envelope_sha256, canonical_envelope
from k0.security.crypto import encode_base64url


class K0Client:
    """Simple K0 client for envelope submission."""

    def __init__(self, base_url="http://localhost:8080"):
        self.base_url = base_url.rstrip("/")
        self.headers = {
            "Content-Type": "application/json",
        }

    def create_envelope(
        self,
        cognitive_trace_id,
        tenant_id,
        space_id,
        topic,
        schema_uri,
        device_id,
        body,
        actor="actor-default",
        band="GREEN",
    ):
        """Create envelope with all required V1 fields (except signature and hashes)."""
        timestamp_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        # Compute payload hash
        body_json = canonical_json(body)
        body_bytes = body_json.encode("utf-8")
        payload_sha256 = hash_payload(body_bytes)

        envelope = {
            "cognitive_trace_id": cognitive_trace_id,
            "tenant_id": tenant_id,
            "space_id": space_id,
            "topic": topic,
            "schema_uri": schema_uri,
            "schema_version": "1.0",
            "actor": actor,
            "device_id": device_id,
            "band": band,
            "policy_version": "2025-09-28",
            "ts": timestamp_iso,
            "payload_sha256": payload_sha256,
            "sig_alg": "Ed25519",  # V1 REQUIRED (64-byte signatures)
            "sig_kid": f"{device_id}#1",  # V1 REQUIRED: device_id#key_version
            "body": body,
            "policy": {
                "abac": {
                    "roles": ["guest"],  # Use 'guest' role for GREEN band
                }
            },
        }

        return envelope

    def sign_envelope(self, envelope, private_key_path="private_key.pem"):
        """Sign envelope with Ed25519."""
        # Load Ed25519 private key
        with open(private_key_path, "rb") as f:
            signing_key = SigningKey(f.read())

        # Compute envelope_sha256 (excludes 'sig' and 'envelope_sha256' itself)
        envelope_sha256 = compute_envelope_sha256(envelope)
        envelope["envelope_sha256"] = envelope_sha256

        # Compute idem_key
        idem_key = derive_idem_key(envelope, payload_hash=envelope["payload_sha256"])

        # Sign canonical envelope (excludes 'sig' only)
        message = canonical_envelope(envelope)
        signature = encode_base64url(signing_key.sign(message).signature)

        # Add signature to envelope
        envelope["sig"] = signature

        return envelope

    def submit(self, envelope):
        """Submit signed envelope to K0."""
        response = requests.post(
            f"{self.base_url}/k0/command.submit",
            headers=self.headers,
            json=envelope,
            timeout=10,
        )

        if response.status_code == 200:
            return response.json()
        elif response.status_code == 409:
            print(f"⚠️ Duplicate envelope detected: {response.json()}")
            return response.json()
        else:
            print(f"Error: {response.status_code} - {response.text}")
            response.raise_for_status()


def main():
    """Submit a test envelope to K0."""
    # Initialize client
    client = K0Client(base_url="http://localhost:8080")

    # Create envelope
    envelope = client.create_envelope(
        cognitive_trace_id=str(uuid.uuid4()),
        tenant_id="tenant-test",
        space_id="space-home",
        topic="memory.delta",
        schema_uri="schema://memory.delta",
        device_id="device-test-1",
        body={
            "operation": "UPSERT",
            "payload": {
                "text": "Hello, K0! This is my first envelope.",
                "value": 42,
            },
        },
    )

    # Sign envelope
    signed_envelope = client.sign_envelope(envelope, private_key_path="private_key.pem")

    print("📤 Submitting envelope to K0...")
    print(f"   Trace ID: {signed_envelope['cognitive_trace_id']}")
    print(f"   Envelope SHA256: {signed_envelope['envelope_sha256'][:32]}...")

    # Submit to K0
    receipt = client.submit(signed_envelope)

    print("\n✅ Envelope submitted successfully!")
    print(f"   Receipt ID: {receipt['receipt_id']}")
    print(f"   Commit TS: {receipt['commit_ts']}")
    print(f"   Offsets: {receipt['offsets']}")


if __name__ == "__main__":
    main()
```

### 5.3 Run Client Script

```powershell
# Submit envelope
python submit_envelope.py

# Expected output:
# 📤 Submitting envelope to K0...
#    Trace ID: a3c8f9b2-e4d1-4c7f-8a9b-0c1d2e3f4a5b
#    Envelope SHA256: d8f2a1b3c5e4f7d9a0b1c2d3e4f5...
#
# ✅ Envelope submitted successfully!
#    Receipt ID: rcpt-1234567890abcdef
#    Commit TS: 2025-11-11T14:32:00Z
#    Offsets: {'wal_pos': 1}
```

**Verify in Database:**
```powershell
# Query WAL
sqlite3 k0/deploy/data/k0_kernel.db "SELECT wal_pos, cognitive_trace_id, tenant_id, space_id, topic FROM st_wal LIMIT 5;"

# Expected output:
# 1|a3c8f9b2-e4d1-4c7f-8a9b-0c1d2e3f4a5b|tenant-test|space-home|memory.delta
```

---

## 6. Query Envelopes

### 6.1 Query by Space

```python
"""Query envelopes from K0."""

import requests


def query_envelopes(space_id, limit=10):
    """Query envelopes for a space."""
    response = requests.get(
        f"http://localhost:8080/v1/query/spaces/{space_id}/envelopes",
        headers={"X-K0-API-Key": "dev-api-key-12345"},
        params={
            "limit": limit,
            "order": "desc",  # Most recent first
        },
        timeout=10,
    )

    response.raise_for_status()
    return response.json()


# Query envelopes
result = query_envelopes("space-quickstart", limit=10)

print(f"📊 Found {result['total']} envelope(s):")
for envelope in result["envelopes"]:
    print(f"   - {envelope['event_id']} (WAL pos: {envelope['wal_pos']})")
```

### 6.2 Get Receipt by ID

```python
"""Get receipt details."""

import requests


def get_receipt(receipt_id):
    """Get receipt by ID."""
    response = requests.get(
        f"http://localhost:8080/v1/query/receipts/{receipt_id}",
        headers={"X-K0-API-Key": "dev-api-key-12345"},
        timeout=10,
    )

    response.raise_for_status()
    return response.json()


# Get receipt
receipt = get_receipt("rcpt-1234567890abcdef")

print(f"📝 Receipt Details:")
print(f"   Receipt ID: {receipt['receipt_id']}")
print(f"   Event ID: {receipt['event_id']}")
print(f"   WAL Position: {receipt['wal_pos']}")
print(f"   Embedding Status: {receipt['embedding_status']}")
print(f"   FTS Status: {receipt['fts_status']}")
```

---

## 7. Common Patterns

### 7.1 Batch Submission

```python
"""Submit multiple envelopes in sequence."""


def submit_batch(client, envelopes):
    """Submit batch of envelopes."""
    receipts = []

    for envelope in envelopes:
        signed_envelope = client.sign_envelope(envelope)
        receipt = client.submit(signed_envelope)
        receipts.append(receipt)

    return receipts


# Create batch
envelopes = [
    client.create_envelope(
        event_id=f"evt-batch-{i:03d}",
        tenant_id="tenant-dev",
        space_id="space-quickstart",
        body={"text": f"Batch message {i}", "index": i},
    )
    for i in range(10)
]

# Submit batch
receipts = submit_batch(client, envelopes)
print(f"✅ Submitted {len(receipts)} envelopes")
```

### 7.2 Error Handling with Retries

```python
"""Error handling with exponential backoff."""

import time
from requests.exceptions import HTTPError, Timeout


def submit_with_retry(client, envelope, max_retries=3):
    """Submit envelope with retry logic."""
    for attempt in range(max_retries):
        try:
            receipt = client.submit(envelope)
            return receipt

        except HTTPError as e:
            if e.response.status_code == 429:  # Rate limit
                wait_seconds = 2 ** attempt  # Exponential backoff
                print(f"⚠️ Rate limited. Retrying in {wait_seconds}s...")
                time.sleep(wait_seconds)
            elif e.response.status_code == 409:  # Duplicate
                print(f"⚠️ Duplicate envelope (idempotency)")
                return e.response.json()
            else:
                raise

        except Timeout:
            if attempt < max_retries - 1:
                print(f"⚠️ Timeout. Retrying (attempt {attempt + 1}/{max_retries})...")
                time.sleep(1)
            else:
                raise

    raise Exception(f"Failed after {max_retries} attempts")
```

### 7.3 Async Worker Monitoring

```python
"""Monitor async worker status."""

import sqlite3


def check_async_status(db_path="data/k0_kernel.db"):
    """Check async worker status."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Count pending work
    pending = cursor.execute(
        "SELECT COUNT(*) FROM st_outbox WHERE status='PENDING'"
    ).fetchone()[0]

    # Count completed embeddings
    done_embeddings = cursor.execute(
        "SELECT COUNT(*) FROM st_wal WHERE embedding_status='DONE'"
    ).fetchone()[0]

    # Count completed FTS
    done_fts = cursor.execute("SELECT COUNT(*) FROM st_wal WHERE fts_status='DONE'").fetchone()[
        0
    ]

    conn.close()

    print(f"📊 Async Worker Status:")
    print(f"   Pending work: {pending}")
    print(f"   Embeddings completed: {done_embeddings}")
    print(f"   FTS completed: {done_fts}")


check_async_status()
```

---

## 8. Troubleshooting

### 8.1 Common Issues

#### Issue: "Signature verification failed"

**Cause:** Incorrect canonical JSON, wrong signing algorithm, or envelope_sha256 not excluded from hash

**Solution:**

1. Use Ed25519 algorithm (industry-standard name; SHA-512 is internal)
2. Ensure `envelope_sha256` is excluded when computing the hash
3. Use PyNaCl library for Ed25519 signing (produces 64-byte signatures)
4. Verify `sig_alg` is exactly "Ed25519"
5. Verify `sig_kid` format is "{device_id}#{key_version}"

```python
# Debug: Verify signature algorithm
print(f"sig_alg: {envelope['sig_alg']}")  # Must be "Ed25519"
print(f"sig_kid: {envelope['sig_kid']}")  # Must be "device-id#1"

# Debug: Check envelope_sha256 exclusion
from k0.security import canonical_envelope
canonical_bytes = canonical_envelope(envelope, exclude_signature=True)
print(f"Canonical envelope excludes: sig, envelope_sha256")
```

#### Issue: "Rate limit exceeded (429)"

**Cause:** Too many requests per minute

**Solution:** Implement exponential backoff (see Section 7.2)

#### Issue: "Database locked"

**Cause:** Multiple writers accessing SQLite without WAL mode

**Solution:**

```powershell
# Verify WAL mode enabled
sqlite3 data/k0_kernel.db "PRAGMA journal_mode;"
# Expected: wal

# If not enabled, restart K0 server
python -m k0.cli.k0ctl serve
```

#### Issue: "Embedding worker not processing"

**Cause:** Worker not running or model not loaded

**Solution:**

```powershell
# Check if worker is running
# ps | findstr python  # Windows
# ps aux | grep python  # Linux

# Verify model loaded
python -c "from sentence_transformers import SentenceTransformer; model = SentenceTransformer('all-mpnet-base-v2'); print('Model loaded')"

# Restart worker with debug logging
$env:K0_KERNEL_SERVER__LOG_LEVEL = "debug"
python -m k0.workers.embedding_worker
```

### 8.2 Debug Mode

Enable debug logging:

```powershell
# Set log level
$env:K0_KERNEL_SERVER__LOG_LEVEL = "debug"

# Restart K0
python -m k0.cli.k0ctl serve --log-level debug

# Expected: Verbose logging of all requests
# [DEBUG] Received envelope: event_id=evt-001
# [DEBUG] Canonical JSON: {"body":...}
# [DEBUG] Signature verification: OK
# [DEBUG] WAL write: pos=1
```

### 8.3 Performance Validation

Verify performance targets:

```powershell
# Run performance tests
python -m pytest tests/k0/integration/test_v1_performance.py -v

# Expected output:
# test_p95_latency_under_100ms PASSED
# test_async_workers_process_backlog PASSED
# test_zero_data_loss_crash_recovery PASSED
#
# P95: 3.32ms (target: <100ms) ✅
# P99: 4.05ms (target: <150ms) ✅
```

---

## 9. Next Steps

### 9.1 Production Deployment

- Read: `docs/deployment/k0_production_guide.md`
- Configure: TLS/mTLS for secure communication
- Setup: Monitoring with Prometheus + Grafana
- Deploy: Docker Compose or Kubernetes

### 9.2 Client Libraries

**Python:**

```powershell
# Install K0 Python client (when available)
# pip install k0-client

# from k0_client import K0Client
# client = K0Client(base_url="https://k0.example.com", api_key="...")
```

**JavaScript/TypeScript:**

```bash
# Install K0 JS client (when available)
# npm install @k0/client

# import { K0Client } from '@k0/client';
# const client = new K0Client({baseUrl: '...', apiKey: '...'});
```

### 9.3 Advanced Features

- **SSE Streaming**: Subscribe to real-time events
- **Policy Enforcement**: Configure GREEN/AMBER/RED bands
- **Multi-tenancy**: Separate databases per tenant
- **Schema Registry**: Version control for envelope schemas

### 9.4 Learning Resources

- **Integration Spec**: `docs/integration/k0_v1_integration_spec.md`
- **Architecture**: `k0/README.md` (complete kernel design)
- **Performance**: `tests/k0/integration/test_v1_performance.py`
- **Examples**: `examples/` (coming soon)

---

## 10. Support

**Documentation**: `docs/`
**GitHub**: <https://github.com/familyos/k0>
**Issues**: <https://github.com/familyos/k0/issues>
**License**: Apache 2.0

**Quick Links:**

- Integration Spec: `docs/integration/k0_v1_integration_spec.md`
- Production Guide: `docs/deployment/k0_production_guide.md`
- API Reference: `docs/api/`
- ADRs: `docs/architecture/decisions/`

---

**Congratulations!** You've successfully:

- ✅ Installed K0 and dependencies
- ✅ Configured database and workers
- ✅ Submitted your first envelope
- ✅ Queried envelopes and receipts
- ✅ Understood async worker pipeline

**Next**: Deploy to production with `docs/deployment/k0_production_guide.md`
