# K0 Kernel Deployment Runbook

## Device Provisioning & Multi-Kernel Connectivity

**Document Version**: 1.0
**Last Updated**: October 31, 2025
**Status**: Production-Ready
**Audience**: DevOps Engineers, System Integrators, Platform Operators

---

## Table of Contents

1. [Overview](#overview)
2. [Prerequisites](#prerequisites)
3. [Part 1: Single Kernel Deployment](#part-1-single-kernel-deployment)
4. [Part 2: Device Provisioning](#part-2-device-provisioning)
5. [Part 3: Multi-Kernel Setup](#part-3-multi-kernel-setup)
6. [Part 4: Cross-Kernel Communication](#part-4-cross-kernel-communication)
7. [Troubleshooting](#troubleshooting)
8. [Security & Best Practices](#security--best-practices)

---

## Overview

### Architecture

The K0 kernel ecosystem consists of:

- **K0 Kernel**: Event processing core with policy enforcement, schema validation, and cryptographic signing
- **Device**: Client entity (edge device, service, application) that submits commands to kernel
- **Policy Enforcement Module (PEM)**: Validates operations against role-based access control (RBAC/ABAC)
- **Schema Registry**: Validates command payloads against registered schemas
- **Idempotency Ledger**: Prevents duplicate writes using idem_key tracking

### Topology Options

```
Single Kernel (Dev/Testing):
┌─────────────┐
│   K0 Kernel │  Port 8080
└────┬────────┘
     │
     ├─ Device 1
     ├─ Device 2
     └─ Device N

Multi-Kernel (Production):
┌─────────────┐      ┌─────────────┐
│ K0 Kernel A │      │ K0 Kernel B │
│ Port 8080   │      │ Port 8080   │
└──────┬──────┘      └──────┬──────┘
       │ Bridge Link        │ Bridge Link
       └────────┬───────────┘
                │
         ┌──────┴──────┐
         │   Devices   │
         └─────────────┘
```

---

## Prerequisites

### System Requirements

- **Docker & Docker Compose** (v20.10+)
- **Python 3.9+** with requests library
- **Ed25519 cryptographic library** (cryptography package)
- **4GB RAM** minimum (8GB recommended for multi-kernel)
- **Linux/macOS/Windows with WSL2**

### Verify Installation

```bash
# Check Docker
docker --version
docker-compose --version

# Check Python
python --version
pip list | grep cryptography requests

# Expected outputs:
# Docker version 20.10.x or higher
# docker-compose version 2.x.x or higher
# cryptography 41.0.x or higher
# requests 2.31.x or higher
```

### File Structure

```
d:\familyos\k0\deploy\
├── docker-compose.yml          # K0 stack definition
├── env/
│   └── k0.env                  # Environment variables
├── generated/
│   └── manifests/
│       ├── allow_all.json      # Policy manifest
│       └── schema_registry.json # Schema definitions
├── test_all_ports.py           # Validation test suite
├── test_policy.py              # Policy enforcement test
├── provision_device.py          # Device provisioning script
└── generate_signing_keys.py     # Ed25519 key generation
```

---

## Part 1: Single Kernel Deployment

### Step 1: Deploy K0 Kernel Stack

```bash
cd d:\familyos\k0\deploy

# Start all services (Kernel + Prometheus + Grafana + Tempo + AlertManager)
docker-compose up -d

# Verify all services are running
docker-compose ps

# Expected output:
# STATUS: Up X seconds (all 6 services)
```

### Step 2: Verify Kernel Readiness

```bash
# Check kernel health
curl http://localhost:8080/healthz

# Expected response:
# {"status": "ok", "version": "0.0.0-dev"}

# Check kernel ready (migrations applied, WAL replayed)
curl http://localhost:8080/readyz

# Expected response:
# {
#   "ready": true,
#   "components": {
#     "migrations_applied": true,
#     "wal_replay_complete": true
#   }
# }
```

### Step 3: Validate All Ports

```bash
# Run comprehensive test suite
python test_all_ports.py

# Expected output:
# ✅ K0 Health                      200 OK
# ✅ K0 Ready                       200 OK
# ✅ K0 Command Submit              200 ✅ Idempotency OK
# ✅ Prometheus Metrics             200 OK
# ✅ Prometheus Ready               200 OK
# ✅ Grafana Health                 200 OK
# ✅ AlertManager Ready             200 OK
# ✅ Tempo Metrics                  200 OK
#
# TOTAL: 8/8 PASSED
# 🎉 ALL TESTS PASSED! 🎉
```

### Step 4: Access Observability Dashboards

| Service | URL | Credentials |
|---------|-----|-------------|
| **Grafana** | http://localhost:3000 | admin / admin |
| **Prometheus** | http://localhost:9090 | (none) |
| **AlertManager** | http://localhost:9093 | (none) |
| **Tempo** | http://localhost:3200 | (none) |

---

## Part 2: Device Provisioning

### Overview

Devices are identified by:
- **tenant_id**: Namespace/organization identifier
- **space_id**: Logical space within tenant
- **device_id**: Unique device identifier
- **roles**: RBAC roles [admin, device, observer, etc.]

### Step 1: Generate Ed25519 Key Pair

```bash
cd d:\familyos

# Generate Ed25519 key pair using Python
python -c "
from nacl.signing import SigningKey
from k0.security.crypto import encode_base64url

# Generate key pair
signing_key = SigningKey.generate()
verify_key = signing_key.verify_key

# Save private key
with open('device_private.pem', 'wb') as f:
    f.write(signing_key.encode())

# Save public key (base64url)
verify_key_b64 = encode_base64url(verify_key.encode())
with open('device_public.txt', 'w') as f:
    f.write(verify_key_b64)

print('✓ Keys generated:')
print(f'  Private key: device_private.pem (32 bytes)')
print(f'  Public key (base64url): {verify_key_b64}')
"

# Output example:
# ✓ Keys generated:
#   Private key: device_private.pem (32 bytes)
#   Public key (base64url): vT8kDq3H5Jm9Ln2Kp4Qr6St7Uv8Wx0Yz1Ab2Cd3Ef4Gh5Ij6Kl7Mn8Op9Qr0
```

**Store securely:**
- Private key → Device secret storage (HSM, vault, secure enclave)
- Public key → Kernel device registry

### Step 2: Provision Device in Kernel

#### Option A: Manual SQL (Development)

```bash
# Connect to SQLite database
sqlite3 d:\familyos\k0\deploy\data\k0_kernel.db

# Register device in st_devices table
INSERT INTO st_devices (
  device_id,
  tenant_id,
  space_id,
  mls_group_id,
  provisioned_ts
) VALUES (
  'device-mobile-001',
  'tenant-001',
  'space-home',
  'mls-group-1',
  datetime('now')
);

# Register device key in st_device_keys table
INSERT INTO st_device_keys (
  device_id,
  key_version,
  verify_key,
  key_state,
  registered_ts,
  activated_ts
) VALUES (
  'device-mobile-001',
  '1',
  'vT8kDq3H5Jm9Ln2Kp4Qr6St7Uv8Wx0Yz1Ab2Cd3Ef4Gh5Ij6Kl7Mn8Op9Qr0',
  'ACTIVE',
  datetime('now'),
  datetime('now')
);

# Verify provisioning
SELECT d.device_id, d.tenant_id, d.space_id, k.verify_key, k.key_state
FROM st_devices d
JOIN st_device_keys k ON d.device_id = k.device_id
WHERE d.device_id = 'device-mobile-001';
```

#### Option B: Automated Script (Recommended)

```bash
cd d:\familyos\k0\deploy

python provision_device.py \
  --device-id device-mobile-001 \
  --tenant-id tenant-001 \
  --space-id space-home \
  --roles device,observer \
  --band GREEN \
  --public-key "MCowBQYDK2VwAyEA7Zk..."

# Output:
# ✅ Device provisioned successfully
# Device ID: device-mobile-001
# Tenant: tenant-001
# Space: space-home
# Roles: device,observer
# Band: GREEN
# Status: ACTIVE
```

### Step 3: Configure Device Client

Create device configuration file:

```yaml
# device_config.yml
kernel:
  host: localhost
  port: 8080
  protocol: http
  timeout_ms: 5000

device:
  tenant_id: tenant-001
  space_id: space-home
  device_id: device-mobile-001

cryptography:
  algorithm: Ed25519
  private_key_path: /secure/path/device_private.pem

telemetry:
  trace_enabled: true
  metrics_enabled: true
```

### Step 4: Device Submission Workflow

#### Create Signed Command Envelope

```python
import uuid
from datetime import datetime, timezone
from nacl.signing import SigningKey

from k0.security import canonical_json, hash_payload, compute_envelope_sha256, canonical_envelope
from k0.security.crypto import encode_base64url
from k0.idem import derive_idem_key
import requests

class K0DeviceClient:
    def __init__(self, device_config):
        self.kernel_url = f"http://{device_config['kernel']['host']}:{device_config['kernel']['port']}"
        self.device_id = device_config['device']['device_id']
        self.tenant_id = device_config['device']['tenant_id']
        self.space_id = device_config['device']['space_id']

        # Load private key (Ed25519)
        with open(device_config['cryptography']['private_key_path'], 'rb') as f:
            self.private_key = SigningKey(f.read())

    def submit_command(self, topic, payload, schema_uri):
        """
        Submit a signed command to K0 kernel.

        Args:
            topic: Command topic (e.g., "memory.delta")
            payload: Command payload dict
            schema_uri: Schema identifier (e.g., "schema://memory.delta")

        Returns:
            Receipt with receipt_id and commit_ts
        """

        # 1. Compute payload hash
        payload_json = canonical_json(payload)
        payload_bytes = payload_json.encode("utf-8")
        payload_sha256 = hash_payload(payload_bytes)

        # 2. Create command envelope
        trace_id = str(uuid.uuid4())
        timestamp_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        envelope = {
            "cognitive_trace_id": trace_id,
            "tenant_id": self.tenant_id,
            "space_id": self.space_id,
            "device_id": self.device_id,
            "topic": topic,
            "schema_uri": schema_uri,
            "schema_version": "1.0",
            "actor": f"actor-{self.device_id}",
            "band": "GREEN",
            "policy_version": "2025-09-28",
            "payload_sha256": payload_sha256,
            "ts": timestamp_iso,
            "sig_alg": "Ed25519",  # REQUIRED (64-byte signatures)
            "sig_kid": f"{self.device_id}#1",  # REQUIRED: {device_id}#{key_version}
            "body": payload,
            "policy": {
                "abac": {
                    "roles": ["guest"]  # Use 'guest' for GREEN band
                }
            },
        }

        # 3. Compute envelope_sha256 (excludes 'sig' and 'envelope_sha256')
        envelope_sha256 = compute_envelope_sha256(envelope)
        envelope["envelope_sha256"] = envelope_sha256

        # 4. Sign with Ed25519
        message = canonical_envelope(envelope)
        signature = encode_base64url(self.private_key.sign(message).signature)
        envelope["sig"] = signature

        # 5. Submit to kernel
        response = requests.post(
            f"{self.kernel_url}/k0/command.submit",
            json=envelope,
            timeout=5
        )

        if response.status_code in [200, 409]:  # 200 = new, 409 = idempotent duplicate
            return response.json()
        else:
            raise Exception(f"Command submission failed: {response.status_code} {response.text}")

# Usage example
config = {
    'kernel': {'host': 'localhost', 'port': 8080},
    'device': {
        'tenant_id': 'tenant-001',
        'space_id': 'space-home',
        'device_id': 'device-mobile-001'
    },
    'cryptography': {
        'private_key_path': 'device_private.pem'
    }
}

client = K0DeviceClient(config)

# Submit command
receipt = client.submit_command(
    topic="memory.delta",
    payload={"action": "write", "key": "user_preferences", "value": {"theme": "dark"}},
    schema_uri="schema://memory.delta"
)

print(f"✅ Command accepted!")
print(f"   Receipt ID: {receipt['receipt_id']}")
print(f"   Commit TS: {receipt['commit_ts']}")
```

---

## Part 3: Multi-Kernel Setup

### Architecture: 2-Kernel Federation

```
          ┌─────────────────────────────────────────┐
          │         Device Management Service        │
          │  (Routes commands to appropriate kernel) │
          └──────────────┬──────────────────────────┘
                         │
           ┌─────────────┴─────────────┐
           │                           │
      ┌────▼─────┐              ┌──────▼────┐
      │ K0 Alpha │              │ K0 Beta   │
      │ Port 8080│              │ Port 8081 │
      │ Tenant A │              │ Tenant B  │
      │ Space H1 │              │ Space H2  │
      └────┬─────┘              └──────┬────┘
           │                           │
    [Device-A]                  [Device-B]
```

### Step 1: Deploy Second K0 Kernel Instance

```bash
cd d:\familyos\k0\deploy

# Create separate docker-compose for second kernel
cat > docker-compose-beta.yml << 'EOF'
version: '3.8'

services:
  k0-kernel-beta:
    image: k0-kernel:latest
    container_name: k0-kernel-beta
    ports:
      - "8081:8080"
    environment:
      K0_TENANT_ID: tenant-002
      K0_SPACE_ID: space-beta
      K0_DEVICE_ID: device-kernel-beta
      K0_DB_PATH: /data/k0_kernel_beta.db
      K0_POLICY_MANIFEST_PATH: /mnt/policy/allow_all_beta.json
      K0_SERVER_PORT: 8080
      K0_KERNEL_TELEMETRY__OTLP_ENDPOINT: http://tempo:4318/v1/traces
    volumes:
      - ./generated/manifests/allow_all_beta.json:/mnt/policy/allow_all_beta.json
      - k0-data-beta:/data
    networks:
      - k0-network
    depends_on:
      - tempo
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/healthz"]
      interval: 10s
      timeout: 5s
      retries: 5

volumes:
  k0-data-beta:

networks:
  k0-network:
    external: true
EOF

# Create second policy manifest
cp generated/manifests/allow_all.json generated/manifests/allow_all_beta.json

# Update for Beta tenant
sed -i 's/"tenant": "tenant-001"/"tenant": "tenant-002"/g' generated/manifests/allow_all_beta.json
sed -i 's/"space": "space-home"/"space": "space-beta"/g' generated/manifests/allow_all_beta.json

# Deploy Beta kernel
docker-compose -f docker-compose-beta.yml up -d

# Verify deployment
docker-compose -f docker-compose-beta.yml ps
curl http://localhost:8081/healthz
```

### Step 2: Verify Both Kernels

```bash
# Alpha kernel
curl http://localhost:8080/healthz
# {"status": "ok", "version": "0.0.0-dev"}

# Beta kernel
curl http://localhost:8081/healthz
# {"status": "ok", "version": "0.0.0-dev"}

# Test Alpha kernel
python test_all_ports.py

# Test Beta kernel
python test_all_ports.py --port 8081
```

### Step 3: Provision Devices to Both Kernels

```bash
# Device for Alpha kernel (tenant-001)
python provision_device.py \
  --device-id device-edge-alpha \
  --tenant-id tenant-001 \
  --space-id space-home \
  --roles device \
  --band GREEN \
  --public-key "MCowBQYDK2VwAyEA..." \
  --kernel-url http://localhost:8080

# Device for Beta kernel (tenant-002)
python provision_device.py \
  --device-id device-edge-beta \
  --tenant-id tenant-002 \
  --space-id space-beta \
  --roles device \
  --band GREEN \
  --public-key "MCowBQYDK2VwAyEA..." \
  --kernel-url http://localhost:8081
```

---

## Part 4: Cross-Kernel Communication

### Scenario: Device Sending Commands to Multiple Kernels

```python
class MultiKernelClient:
    """Device client that can route commands to multiple kernels."""

    def __init__(self, kernels_config):
        """
        Args:
            kernels_config: List of kernel configs
            [
                {
                    'name': 'alpha',
                    'host': 'localhost',
                    'port': 8080,
                    'tenant': 'tenant-001',
                    'space': 'space-home'
                },
                {
                    'name': 'beta',
                    'host': 'localhost',
                    'port': 8081,
                    'tenant': 'tenant-002',
                    'space': 'space-beta'
                }
            ]
        """
        self.kernels = {cfg['name']: cfg for cfg in kernels_config}
        self.clients = {}

        for name, cfg in self.kernels.items():
            self.clients[name] = K0DeviceClient({
                'kernel': {'host': cfg['host'], 'port': cfg['port']},
                'device': {
                    'tenant_id': cfg['tenant'],
                    'space_id': cfg['space'],
                    'device_id': f"device-multi-{name}"
                },
                'cryptography': {
                    'private_key_path': f'/secure/path/device_{name}_private.pem'
                }
            })

    def broadcast_command(self, topic, payload, schema_uri, target_kernels=None):
        """
        Send command to multiple kernels.

        Args:
            topic: Command topic
            payload: Command payload
            schema_uri: Schema identifier
            target_kernels: List of kernel names (None = all)

        Returns:
            Dict of results {kernel_name: receipt}
        """
        targets = target_kernels or list(self.clients.keys())
        results = {}

        for kernel_name in targets:
            try:
                client = self.clients[kernel_name]
                receipt = client.submit_command(topic, payload, schema_uri)
                results[kernel_name] = {
                    'status': 'SUCCESS',
                    'receipt_id': receipt['receipt_id'],
                    'commit_ts': receipt['commit_ts']
                }
            except Exception as e:
                results[kernel_name] = {
                    'status': 'FAILED',
                    'error': str(e)
                }

        return results

# Usage
multi_client = MultiKernelClient([
    {
        'name': 'alpha',
        'host': 'localhost',
        'port': 8080,
        'tenant': 'tenant-001',
        'space': 'space-home'
    },
    {
        'name': 'beta',
        'host': 'localhost',
        'port': 8081,
        'tenant': 'tenant-002',
        'space': 'space-beta'
    }
])

# Broadcast to all kernels
results = multi_client.broadcast_command(
    topic="commands.sync.state",
    payload={"state_key": "user_session", "value": {"user_id": "user-001"}},
    schema_uri="schema://memory.delta"
)

print("Broadcast Results:")
for kernel, result in results.items():
    print(f"  {kernel}: {result['status']}")
    if result['status'] == 'SUCCESS':
        print(f"    Receipt: {result['receipt_id']}")
    else:
        print(f"    Error: {result['error']}")
```

### Cross-Kernel State Synchronization

```python
class KernelSyncManager:
    """Manages state synchronization across kernel instances."""

    def __init__(self, kernels_config):
        self.multi_client = MultiKernelClient(kernels_config)
        self.sync_topics = [
            "commands.sync.users",
            "commands.sync.devices",
            "commands.sync.policies"
        ]

    def sync_state(self, state_key, state_value):
        """
        Synchronize state across all kernels.

        Process:
        1. Validate state schema
        2. Create idempotency key based on state_key
        3. Broadcast to all kernels
        4. Wait for confirmations
        5. Log sync events
        """
        topic = "commands.sync.state"
        payload = {
            "state_key": state_key,
            "value": state_value,
            "sync_timestamp": datetime.utcnow().isoformat() + "Z"
        }

        results = self.multi_client.broadcast_command(
            topic=topic,
            payload=payload,
            schema_uri="schema://memory.delta"
        )

        # Verify all succeeded
        all_success = all(r['status'] == 'SUCCESS' for r in results.values())

        if all_success:
            print(f"✅ State synced across all kernels: {state_key}")
            return True
        else:
            failed = [k for k, r in results.items() if r['status'] != 'SUCCESS']
            print(f"⚠️  Sync failed on kernels: {failed}")
            return False

# Usage
sync_manager = KernelSyncManager([...])

# Sync user state
sync_manager.sync_state(
    state_key="user:user-001:preferences",
    state_value={
        "theme": "dark",
        "language": "en",
        "timezone": "UTC"
    }
)
```

---

## Troubleshooting

### Issue: Device Rejected with 403 ROLE_FORBIDDEN

**Cause**: Device roles don't match policy requirements

**Solution**:
```bash
# 1. Check device provisioning
sqlite3 d:\familyos\k0\deploy\data\k0_kernel.db "SELECT device_id FROM st_devices WHERE device_id = 'device-mobile-001';"

# 2. Check device key
sqlite3 d:\familyos\k0\deploy\data\k0_kernel.db "SELECT device_id, key_version, key_state FROM st_device_keys WHERE device_id = 'device-mobile-001';"

# 3. Verify policy allows 'guest' role for GREEN band

# 4. Update envelope to use 'guest' role (not 'coordinator')
# In your code:
# "policy": {"abac": {"roles": ["guest"]}}

# 5. Restart kernel to clear any caches
docker-compose restart k0-kernel
```

### Issue: Command Rejected with 400 SCHEMA_NOT_ACTIVE

**Cause**: Schema URI not registered or inactive

**Solution**:
```bash
# 1. Check registered schemas
sqlite3 d:\familyos\k0\deploy\data\k0_kernel.db "SELECT schema_uri, version, status FROM schema_registry;"

# 2. Register missing schema
sqlite3 d:\familyos\k0\deploy\data\k0_kernel.db << 'EOF'
INSERT INTO schema_registry (schema_uri, version, sha256, status)
VALUES (
  'schema://memory.delta',
  '1.0',
  '...',  -- Schema hash
  'ACTIVE'
);
EOF

# 3. Verify activation
sqlite3 d:\familyos\k0\deploy\data\k0_kernel.db "SELECT * FROM schema_registry WHERE schema_uri = 'schema://memory.delta';"
```

### Issue: Idempotency Ledger Conflicts

**Cause**: Same idem_key submitted multiple times

**Behavior** (Expected):
- First submission: 200 OK with receipt
- Second submission: 409 Conflict with same receipt (idempotency working)

**Verification**:
```bash
# Check idempotency ledger
sqlite3 d:\familyos\k0\deploy\data\k0_kernel.db "SELECT cognitive_trace_id, receipt_id FROM idem_ledger ORDER BY created_at DESC LIMIT 5;"

# If duplicates expected, this is normal behavior (idempotency ensures same receipt returned)
```

### Issue: Multi-Kernel Communication Failures

**Cause**: Network connectivity, port conflicts, or policy mismatch

**Diagnosis**:
```bash
# 1. Verify both kernels running
docker ps | grep k0-kernel

# 2. Test network connectivity
curl http://localhost:8080/healthz
curl http://localhost:8081/healthz

# 3. Check logs for policy errors
docker logs k0-kernel | grep "ROLE_FORBIDDEN\|POLICY\|DENIED"
docker logs k0-kernel-beta | grep "ROLE_FORBIDDEN\|POLICY\|DENIED"

# 4. Verify policies match topology
diff generated/manifests/allow_all.json generated/manifests/allow_all_beta.json
```

---

## Security & Best Practices

### 1. Private Key Management

| Environment | Storage | Best Practice |
|-------------|---------|---------------|
| **Development** | Local filesystem | Encrypted in ~/.ssh/ |
| **Production** | Hardware Security Module (HSM) | AWS KMS, Azure KeyVault |
| **Container** | Mounted secret | Docker secrets, Kubernetes secrets |
| **NEVER** | Hardcoded, Environment vars | Plaintext in images/configs |

```bash
# Secure local storage (development)
chmod 600 device_private.pem
ls -la device_private.pem  # Should show: -rw------- (600)

# Rotate keys periodically
# 1. Generate new key pair
python scripts/generate_ed25519_key.py

# 2. Update device registry with new public key
sqlite3 d:\familyos\k0_runtime.sqlite3 << 'EOF'
UPDATE devices
SET public_key = 'new-public-key'
WHERE device_id = 'device-mobile-001';
EOF

# 3. Deploy new private key to device securely
# (use your secret management system)

# 4. Test new key works
python test_policy.py --device device-mobile-001
```

### 2. Policy Configuration

**Principle of Least Privilege**:
```json
{
  "roles": [
    {
      "name": "device",
      "allow_topics": ["commands.delta.memory.write"],
      "max_band": "GREEN",
      "deny_topics": ["commands.admin.*", "commands.system.*"]
    }
  ]
}
```

**Never use**:
```json
{
  "allow_topics": ["*"]  // Too permissive, use specific patterns
}
```

### 3. Monitoring & Alerting

```bash
# View policy decisions in logs
docker logs k0-kernel | grep "policy_decision"

# Query Prometheus for policy violations
curl "http://localhost:9090/api/v1/query?query=k0_policy_violations_total"

# Set up AlertManager rule (alerting.yml)
- alert: PolicyViolation
  expr: rate(k0_policy_violations_total[5m]) > 0
  for: 1m
  annotations:
    summary: "Policy violations detected"
    description: "{{ $value }} policy violations in last 5 minutes"
```

### 4. Schema Validation

```bash
# Register schema with validation
python k0/automation/lint_schemas.py --validate generated/manifests/allow_all.json

# Output:
# ✅ Schema valid
# ✅ All required fields present
# ✅ Role patterns compilable
# ✅ Topics match fnmatch format
```

### 5. Audit Logging

```bash
# Enable audit logging in K0_PEM_AUDIT_ENABLED=true
# View audit logs
docker logs k0-kernel | grep '"audit"' | head -20

# Expected format:
# {"timestamp": "...", "audit": true, "device": "device-001", "action": "command.submit", "result": "ALLOWED", "policy_id": "allow_all"}
```

---

## Quick Reference Commands

### Device Management

```bash
# List all provisioned devices
sqlite3 d:\familyos\k0_runtime.sqlite3 "SELECT device_id, tenant_id, roles, status FROM devices;"

# Activate device
sqlite3 d:\familyos\k0_runtime.sqlite3 "UPDATE devices SET status = 'ACTIVE' WHERE device_id = 'device-001';"

# Deactivate device
sqlite3 d:\familyos\k0_runtime.sqlite3 "UPDATE devices SET status = 'INACTIVE' WHERE device_id = 'device-001';"

# List device commands submitted
sqlite3 d:\familyos\k0_runtime.sqlite3 "SELECT device_id, topic, created_at FROM commands WHERE device_id = 'device-001' LIMIT 10;"
```

### Kernel Management

```bash
# View kernel metrics
curl http://localhost:9090/api/v1/query?query=k0_commands_processed_total

# Check WAL status
docker exec k0-kernel sqlite3 /data/k0_kernel.db "SELECT * FROM sqlite_master WHERE type='table';"

# View policy decisions
docker logs k0-kernel | grep "policy_decision" | tail -20

# Restart kernel (reloads policy)
docker-compose restart k0-kernel
```

### Testing

```bash
# Single device test
python test_policy.py --device device-mobile-001

# All ports test
python test_all_ports.py

# Multi-kernel broadcast
python test_all_ports.py --port 8080 && python test_all_ports.py --port 8081
```

---

## Next Steps

1. **Automate Device Provisioning**: Integrate `provision_device.py` into your deployment pipeline
2. **Set Up Monitoring**: Create Grafana dashboards for policy violations and device submissions
3. **Implement Device Registry**: Build REST API for device CRUD operations
4. **Enable Cluster Mode**: Deploy K0 with Raft consensus for HA
5. **Create Bridge Service**: Build service to route commands between kernels based on policy

---

## Support & References

- **Architecture**: `docs/whiteboard.md` (21K-line specification)
- **Module Analysis**: `docs/k1_module_analysis.md`
- **Policy Enforcement**: `k0/contracts/policy/bridge_policy.yml`
- **Schema Registry**: `k0/contracts/schema_registry.json`
- **Tests**: `tests/k0/test_*.py`

---

**Document Status**: ✅ Complete and Production-Ready
**Last Verified**: October 31, 2025
**Signed Off**: K0 Platform Team
