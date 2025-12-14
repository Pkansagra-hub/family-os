# K0 Policy Enforcement Point (PEP)

**Purpose**: Policy enforcement, privacy compliance (GDPR/CCPA), ACL management, redaction, retention, and location privacy for K0 kernel operations.

**Layer**: Security & Privacy (Cross-cutting)
**Category**: Policy evaluation and enforcement
**Related ADRs**: ADR-0089 (Redaction), ADR-0091 (Privacy Bands), ADR-0095 (Location Privacy), ADR-0099 (Retention Policies)

---

## Overview

The policy module implements **Policy Enforcement Point (PEP)** functionality that evaluates every kernel operation against:

1. **Privacy bands** (GREEN/AMBER/RED) with cascading obligations
2. **ABAC (Attribute-Based Access Control)** with role-based topic filtering
3. **Capability-based QoS** (fanout, throughput, payload size limits)
4. **Schema sunset windows** (deprecation warnings and hard blocks)
5. **Device posture rules** (security compliance checks)
6. **Location privacy** (geohash masking for GDPR/CCPA compliance)
7. **Data retention policies** (automated archival and deletion)
8. **Row-level ACLs** (st_acl table for resource-level permissions)

**Decision Flow**: `evaluate_envelope()` → `PolicyDecision{admit, obligations, deny_reason}` → `attach_policy_stamp()` → WAL/receipts

---

## Repository Files & Functions

### 1. `pep_syscall.py`

**Purpose**: Core policy evaluation engine executed for every kernel syscall with manifest-driven rules.

#### Classes & Functions

```python
@dataclass(slots=True)
class Obligation:
    name: str
    details: dict[str, str]
```

- **Purpose**: Policy obligation emitted by PEP (e.g., `kernel.redact.field`, `kernel.qos.throttle`)
- **Details**: Key-value metadata for obligation execution (fields to redact, throttle ratio, etc.)

```python
@dataclass(slots=True)
class PolicyDecision:
    admit: bool
    obligations: Sequence[Obligation]
    deny_reason: str | None
```

- **Purpose**: PEP evaluation outcome (ALLOW or DENY with obligations/reason)
- **Usage**: Returned by `evaluate_envelope()`, consumed by command/query/SSE ports

```python
def evaluate_envelope(envelope: dict[str, object]) -> PolicyDecision
```

- **Core evaluation engine**: 6-phase policy evaluation
  1. **Device posture guard rails**: Check device compliance (jailbroken, trusted OS)
  2. **Band blocking**: Short-circuit if band is explicitly denied
  3. **Capability checks**: Validate fanout, throughput, payload size against band limits
  4. **Payload size**: Enforce `max_payload_bytes` per band
  5. **Schema sunsets**: Warn or deny based on `sunset_windows` for deprecated schemas
  6. **Role-based access**: Check ABAC roles against topic patterns

- **Policy manifest**: Loaded from `k0/contracts/policy/pep.schema.json` or `K0_POLICY_MANIFEST_PATH`
- **Graceful degradation (Gap 36)**: Corrupted manifest → fail-safe DENY with reason `POLICY_MANIFEST_CORRUPTED`
- **Logging**: Structured logs with decision outcome, band, roles, obligations

**Example**:

```python
decision = evaluate_envelope({
    "band": "AMBER",
    "topic": "family.photos",
    "tenant_id": "tenant_123",
    "space_id": "space_456",
    "actor": "device_abc",
    "policy": {
        "abac": {"roles": ["parent"]},
        "caps": {"fanout": {"requested": 10}}
    }
})

if decision.admit:
    # Apply obligations (redact fields, throttle QoS, etc.)
    for obligation in decision.obligations:
        apply_obligation(obligation)
else:
    # Deny request
    return 403, {"reason": decision.deny_reason}
```

```python
def create_policy_stamp(
    decision: PolicyDecision,
    band: str,
    visible_to: list[str] | None = None,
    policy_version: str | None = None,
) -> dict[str, Any]
```

- **Purpose**: Create immutable audit trail stamp attached to envelopes
- **Fields**:
  - `band`: Privacy band (GREEN/AMBER/RED)
  - `obligations`: List of obligation names (compact representation)
  - `decision`: ALLOW/DENY
  - `visible_to`: Actor IDs with access (optional)
  - `policy_version`: Manifest fingerprint (SHA-256) for audit
  - `deny_reason`: If denied, reason code

- **Propagation**: Policy stamp travels through WAL → outbox → downstream drivers → receipts
- **Audit trail**: Enables post-hoc compliance verification (GDPR Article 30 record-keeping)

```python
def get_manifest_fingerprint() -> str | None
```

- **Purpose**: Get SHA-256 fingerprint of current policy manifest
- **Caching**: In-memory cache for performance (`_cached_manifest_fingerprint`)
- **Usage**: Included in policy stamps for version tracking

**Policy Manifest Structure**:

```json
{
  "bands": {
    "GREEN": {
      "deny": false,
      "max_fanout": 50,
      "max_payload_bytes": 10485760,
      "obligations": ["kernel.log.detailed"]
    },
    "AMBER": {
      "deny": false,
      "max_fanout": 10,
      "max_payload_bytes": 1048576,
      "obligations": ["kernel.redact.pii", "kernel.qos.throttle"]
    },
    "RED": {
      "deny": false,
      "max_fanout": 1,
      "max_payload_bytes": 262144,
      "obligations": ["kernel.redact.strict", "kernel.location.mask"]
    }
  },
  "roles": [
    {
      "name": "parent",
      "max_band": "RED",
      "allow_topics": ["family.*", "health.*"],
      "obligations": []
    },
    {
      "name": "child",
      "max_band": "GREEN",
      "allow_topics": ["family.photos", "family.calendar"],
      "obligations": ["kernel.qos.rate_limit"]
    }
  ],
  "device_postures": {
    "jailbroken": {
      "deny": true,
      "obligations": ["kernel.log.security_violation"]
    }
  },
  "sunset_windows": {
    "family.v1/1.0.0": {
      "warn_after": "2025-09-01T00:00:00Z",
      "deny_after": "2026-01-01T00:00:00Z",
      "obligation": "kernel.schema.deprecated"
    }
  }
}
```

---

### 2. `policy_stamp.py`

**Purpose**: Policy stamp data structure and serialization (V1.3 feature).

#### Classes

```python
@dataclass
class PolicyStamp:
    policy_version: str
    band: Literal["GREEN", "AMBER", "RED"]
    obligations: list[str]
    visible_to: list[str]
    decision: Literal["ALLOW", "DENY", "CONDITIONAL"]
    applied_at: str | None
```

- **Immutable audit trail**: Attached post-PEP evaluation
- **Serialization**: `to_dict()`, `to_json()`, `from_dict()`, `from_json()`
- **Timestamp**: Auto-set `applied_at` to UTC ISO8601 if not provided

#### Functions

```python
def attach_policy_stamp_to_envelope(envelope: dict[str, Any], policy_stamp: PolicyStamp) -> dict[str, Any]
def extract_policy_stamp(envelope: dict[str, Any]) -> PolicyStamp | None
```

- **Purpose**: Attach/extract policy stamps from envelopes
- **Mutation**: `attach_policy_stamp_to_envelope()` mutates envelope in-place
- **Usage**: Called by command port after `evaluate_envelope()`

---

### 3. `redaction.py`

**Purpose**: Obligation-driven field redaction with path traversal and location privacy masking (GDPR/CCPA).

#### Classes & Functions

```python
@dataclass(slots=True)
class RedactionDirective:
    obligation: str  # "kernel.redact.field"
    fields: Sequence[str] | str  # Fields to redact (e.g., ["ssn", "credit_card"])
    target: str | Sequence[str] | None  # Base path (e.g., "user.profile")
    mask: object  # Mask value (default: "***REDACTED***")
```

```python
def apply_redactions(body: Mapping[str, object], directives: Iterable[RedactionDirective]) -> dict[str, object]
```

- **Purpose**: Apply redaction directives to envelope body (field masking)
- **Path traversal**: Supports nested paths (`user.profile.ssn`) and array indices (`addresses.0.street`)
- **Non-mutating**: Returns sanitized copy, preserves original for audit trail
- **Error handling**: Silently ignores missing paths (PEM logs at higher level)

**Example**:

```python
body = {
    "user": {
        "name": "Alice",
        "profile": {
            "ssn": "123-45-6789",
            "email": "alice@example.com"
        }
    }
}

directives = [
    RedactionDirective(
        obligation="kernel.redact.field",
        fields=["ssn"],
        target="user.profile",
        mask="***REDACTED***"
    )
]

sanitized = apply_redactions(body, directives)
# sanitized["user"]["profile"]["ssn"] == "***REDACTED***"
```

```python
def directives_from_obligations(obligations: Iterable[Any], *, default_mask: object = "***REDACTED***") -> list[RedactionDirective]
```

- **Purpose**: Convert policy obligations to redaction directives
- **Filter**: Only processes `kernel.redact.field` obligations
- **Details extraction**: Reads `fields`, `target`, `mask` from obligation details

```python
def mask_location_for_band(body: dict[str, Any], band: str, lat_field: str = "location_lat", lon_field: str = "location_lon") -> dict[str, Any]
```

- **Purpose**: GDPR/CCPA-compliant location masking via geohash
- **Precision levels**:
  - **GREEN**: No masking (exact lat/lon preserved, geohash-12, precision=1m)
  - **AMBER**: Geohash-6 (5km precision, ~0.7 km² box) - exact coords cleared
  - **RED**: Geohash-4 (25km precision, ~500 km² box) - exact coords cleared

- **Algorithm**: Geohash2 library (requires `pip install geohash2`)
- **Output**: Adds `location_geohash`, `location_precision_m` fields; clears exact coords for AMBER/RED
- **Compliance**: GDPR Article 25 (privacy by design), CCPA reasonable accuracy requirements

**Example**:

```python
body = {"location_lat": 37.7749, "location_lon": -122.4194}

# AMBER band: 5km precision
masked = mask_location_for_band(body, "AMBER")
# {
#   "location_lat": None,
#   "location_lon": None,
#   "location_geohash": "9q8yy9",  # 6-char geohash
#   "location_precision_m": 5000
# }
```

**Error handling**:
- Raises `RedactionError` if:
  - Only one coordinate provided (lat without lon)
  - Invalid coordinates (lat not in [-90, 90], lon not in [-180, 180])
  - Geohash2 library not installed

---

### 4. `location_privacy.py`

**Purpose**: Geohash-based location masking implementation (V1.3 feature).

#### Functions

```python
def lat_lon_to_geohash(lat: float, lon: float, precision: int = 12) -> str
```

- **Purpose**: Convert lat/lon to geohash string
- **Algorithm**: Binary geohash encoding with base-32 alphabet
- **Precision levels**: 1-12 characters (1 ≈ 2,500km, 12 ≈ 0.6m)
- **Validation**: Raises `ValueError` if lat/lon out of range or precision invalid

```python
def get_geohash_precision_for_band(band: Literal["GREEN", "AMBER", "RED"]) -> int
```

- **Mapping**:
  - GREEN → 12 (full precision, ~0.6m)
  - AMBER → 6 (~2.4km, conservative 5km for GDPR)
  - RED → 4 (~39km, conservative 25km for high-sensitivity)

```python
def mask_location_for_band(lat: float | None, lon: float | None, band: Literal["GREEN", "AMBER", "RED"]) -> tuple[str | None, int | None]
```

- **Purpose**: Mask coordinates to band-appropriate precision
- **Returns**: `(geohash, precision_meters)` tuple
- **None handling**: If lat/lon are None, returns `(None, None)`

```python
def apply_location_privacy(envelope: dict[str, Any], band: Literal["GREEN", "AMBER", "RED"]) -> dict[str, Any]
```

- **Purpose**: Apply location masking to envelope (mutates envelope)
- **Extraction**: Reads `location_lat`, `location_lon` from `envelope["body"]`
- **Updates**: Sets `location_geohash`, `location_precision_m` on envelope
- **Privacy protection**: Clears exact coords from body for AMBER/RED bands

---

### 5. `acl_enforcer.py`

**Purpose**: Row-level access control using `st_acl` table (Migration 0004).

#### Classes

```python
@dataclass(frozen=True)
class ACLEntry:
    acl_id: str
    resource_type: str  # st_epi, st_sem, etc.
    resource_id: str
    principal_type: str  # user, device, service
    principal_id: str
    permission: str  # read, write, delete, share
    privacy_band: Optional[str]
    granted_at: str
    granted_by: str
    expires_at: Optional[str]
    revoked_at: Optional[str]
```

```python
class ACLEnforcer:
    def check_permission(self, resource_type: str, resource_id: str, principal_id: str, permission: str, *, principal_type: str = "user", connection: Optional[sqlite3.Connection] = None) -> bool
```

- **Performance**: <2ms P95 (indexed query on `st_acl`)
- **Query**: Checks `resource_type`, `resource_id`, `principal_id`, `permission` + `revoked_at IS NULL` + `expires_at > now()`
- **Fallback**: If `st_acl` table missing (Migration 0004 not applied), returns `True` (permissive default)

**Example**:

```python
enforcer = ACLEnforcer()

# Check read permission
if enforcer.check_permission("st_epi", "evt_123", "usr_alice", "read"):
    return memory_content
else:
    return 403, {"error": "ACCESS_DENIED"}
```

```python
def grant_permission(self, acl_id: str, resource_type: str, resource_id: str, principal_type: str, principal_id: str, permission: str, granted_by: str, *, privacy_band: Optional[str] = None, expires_at: Optional[str] = None, connection: Optional[sqlite3.Connection] = None) -> None
```

- **Purpose**: Insert ACL entry into `st_acl`
- **ULID/UUID**: Requires external ID generation (e.g., `ulid.ulid()`)
- **Expiry**: Optional ISO8601 timestamp for time-limited permissions
- **Privacy band filter**: Optional band constraint (GREEN/AMBER/RED)

```python
def revoke_permission(self, acl_id: str, *, connection: Optional[sqlite3.Connection] = None) -> None
```

- **Soft delete**: Sets `revoked_at` timestamp (preserves audit trail)
- **Immediate effect**: Check queries filter `revoked_at IS NULL`

```python
def list_permissions(self, *, resource_type: Optional[str] = None, resource_id: Optional[str] = None, principal_id: Optional[str] = None, include_revoked: bool = False, connection: Optional[sqlite3.Connection] = None) -> List[ACLEntry]
```

- **Purpose**: Query ACL entries with filters
- **Default**: Excludes revoked entries unless `include_revoked=True`
- **Usage**: Admin UI, audit logs, permission reviews

---

### 6. `retention_enforcer.py`

**Purpose**: Data lifecycle management with retention policies and archival (Migration 0004).

#### Classes

```python
@dataclass(frozen=True)
class RetentionPolicy:
    policy_id: str
    resource_type: str  # st_epi, st_sem, etc.
    retention_days: int
    archive_enabled: bool
    privacy_band_filter: Optional[str]
    tenant_id_filter: Optional[str]
    enabled: bool
```

```python
@dataclass(frozen=True)
class ArchiveManifest:
    manifest_id: str
    resource_type: str
    resource_id: str
    archive_location: str  # Blob storage path
    checksum: Optional[str]
    compressed_size_bytes: Optional[int]
    archived_at: str
    delete_after: Optional[str]
    tenant_id: Optional[str]
```

```python
class RetentionEnforcer:
    def apply_policies(self, *, dry_run: bool = False, connection: Optional[sqlite3.Connection] = None) -> dict
```

- **Purpose**: Execute all enabled retention policies (nightly job)
- **Workflow**:
  1. Load enabled policies from `st_retention_policy`
  2. For each policy:
     - Query expired resources (`created_at < now() - retention_days`)
     - If `archive_enabled=True`: Archive to blob storage → Record in `st_archive_manifest` → Delete from source
     - Else: Hard delete
  3. Return stats: `{"archived": int, "deleted": int, "errors": int}`

- **Dry-run mode**: Returns stats without making changes (testing/validation)
- **Error handling**: Continues on individual errors, tracks count in stats

**Example**:

```python
enforcer = RetentionEnforcer(archive_callback=upload_to_s3)

# Nightly job
stats = enforcer.apply_policies()
# {"archived": 150, "deleted": 20, "errors": 0}

# Check expired resources for policy
expired = enforcer.get_expired_resources(policy_id="policy_001")
# [{"id": "evt_123", "age_days": 395}, ...]
```

```python
def get_expired_resources(self, policy_id: str, *, connection: Optional[sqlite3.Connection] = None) -> List[dict]
```

- **Purpose**: Get resources exceeding retention period
- **Returns**: List of dicts with `id`, `created_at`, `age_days`, `id_column` (for deletion)
- **Usage**: Preview what will be archived/deleted before running `apply_policies()`

---

## Connections & Integration Points

### Upstream Dependencies

1. **Policy manifest** (`k0/contracts/policy/pep.schema.json`):
   - Loaded on-demand with `lru_cache(maxsize=4)`
   - Fingerprinted with SHA-256 for version tracking
   - Can override with `K0_POLICY_MANIFEST_PATH` env var

2. **Geohash2 library**: Optional for location privacy (install: `pip install geohash2`)

3. **Migration 0004**: Creates `st_acl`, `st_retention_policy`, `st_archive_manifest` tables

### Downstream Consumers

1. **`k0.ports.command`**: Calls `evaluate_envelope()` → creates policy stamp → applies redactions
2. **`k0.ports.query`**: Calls `evaluate_envelope()` → checks role-based topic access
3. **`k0.ports.sse`**: Calls `evaluate_envelope()` → enforces subscription policies
4. **`k0.storage.wal`**: Stores `policy_stamp_json` and `redacted_body_json` fields
5. **`k0.receipts`**: Includes obligations + policy stamp in receipts
6. **`k0.workers.retention`**: Background job calling `RetentionEnforcer.apply_policies()` nightly

### Data Flow

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. Request Ingress                                               │
│    HTTP POST /k0/command.submit → FastAPI port handler          │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│ 2. Policy Evaluation                                             │
│    pep_syscall.evaluate_envelope(envelope) →                     │
│    - Check device posture (jailbroken, trusted)                  │
│    - Check band blocking                                         │
│    - Check capabilities (fanout, throughput, payload size)       │
│    - Check schema sunsets                                        │
│    - Check ABAC roles vs. topic patterns                         │
│    → PolicyDecision{admit, obligations, deny_reason}             │
└────────────────────────┬────────────────────────────────────────┘
                         │
                 ┌───────┴───────┐
                 │               │
           ✓ ALLOW          ✗ DENY
                 │               │
                 ▼               ▼
┌────────────────────────┐  ┌────────────────────────────────────┐
│ 3a. Apply Obligations  │  │ 3b. Reject + Audit                 │
│ For each obligation:   │  │ - Create policy stamp (DENY)       │
│ - kernel.redact.field  │  │ - Log admission decision           │
│   → apply_redactions() │  │ - Return 403 with deny_reason      │
│ - kernel.qos.throttle  │  │                                    │
│   → apply_qos_oblig()  │  └────────────────────────────────────┘
│ - kernel.location.mask │
│   → mask_location()    │
└────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────────┐
│ 4. Create Policy Stamp                                           │
│    create_policy_stamp(decision, band, visible_to) →            │
│    {                                                             │
│      "band": "AMBER",                                            │
│      "obligations": ["kernel.redact.pii"],                       │
│      "decision": "ALLOW",                                        │
│      "policy_version": "a7f3c2e8...",                            │
│      "visible_to": ["usr_alice"]                                 │
│    }                                                             │
│    attach_policy_stamp_to_envelope(envelope, policy_stamp)       │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│ 5. Persistence                                                   │
│    - WAL: Write envelope + sanitized body + policy_stamp_json   │
│    - Receipt: Include obligations + policy stamp                │
│    - Outbox: Forward to drivers with policy context             │
└─────────────────────────────────────────────────────────────────┘
```

### ACL Enforcement Flow

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. Query Request (SSE or Recall)                                 │
│    /k0/sse.subscribe?topics=family.photos&space_id=space_123    │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│ 2. Check ACL Permissions                                         │
│    For each envelope in result:                                  │
│      enforcer.check_permission(                                  │
│        resource_type="st_epi",                                   │
│        resource_id=envelope.event_id,                            │
│        principal_id=subscriber_id,                               │
│        permission="read"                                         │
│      )                                                           │
└────────────────────────┬────────────────────────────────────────┘
                         │
                 ┌───────┴───────┐
                 │               │
           ✓ Permitted      ✗ Denied
                 │               │
                 ▼               ▼
┌────────────────────────┐  ┌────────────────────────────────────┐
│ 3a. Include Envelope   │  │ 3b. Filter Out Envelope            │
│ Add to SSE stream or   │  │ Skip envelope (silent filter)      │
│ recall response        │  │ OR return 403 if explicit query    │
└────────────────────────┘  └────────────────────────────────────┘
```

### Retention Policy Flow

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. Nightly Job Trigger (Cron: 2 AM UTC)                          │
│    retention_worker.py → RetentionEnforcer.apply_policies()     │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│ 2. Load Policies                                                 │
│    SELECT * FROM st_retention_policy WHERE enabled = 1           │
│    Example:                                                      │
│    - policy_001: st_epi, 365 days, archive_enabled=true         │
│    - policy_002: st_sem, 90 days, archive_enabled=false         │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│ 3. Find Expired Resources                                        │
│    For each policy:                                              │
│      SELECT * FROM {resource_type}                               │
│      WHERE created_at < now() - retention_days                   │
│        AND (tenant_id = filter OR filter IS NULL)                │
│        AND (privacy_band = filter OR filter IS NULL)             │
└────────────────────────┬────────────────────────────────────────┘
                         │
                 ┌───────┴───────┐
                 │               │
      archive_enabled=True   archive_enabled=False
                 │               │
                 ▼               ▼
┌────────────────────────┐  ┌────────────────────────────────────┐
│ 4a. Archive to Blob    │  │ 4b. Hard Delete                    │
│ - Fetch full row data  │  │ DELETE FROM {resource_type}        │
│ - Upload to S3/GCS     │  │ WHERE id = resource_id             │
│ - Record manifest      │  └────────────────────────────────────┘
│   (st_archive_manifest)│
│ - Delete from source   │
└────────────────────────┘
```

---

## Testing

### Unit Tests

```python
# tests/k0/policy/test_pep_syscall.py
def test_evaluate_envelope_green_band_allows():
    decision = evaluate_envelope({"band": "GREEN", "topic": "family.photos"})
    assert decision.admit is True
    assert len(decision.obligations) > 0

def test_evaluate_envelope_red_band_fanout_exceeded():
    decision = evaluate_envelope({
        "band": "RED",
        "topic": "health.records",
        "policy": {"caps": {"fanout": {"requested": 100}}}
    })
    assert decision.admit is False
    assert decision.deny_reason == "CAP_FANOUT_EXCEEDED"

# tests/k0/policy/test_redaction.py
def test_apply_redactions_nested_paths():
    body = {"user": {"profile": {"ssn": "123-45-6789"}}}
    directives = [RedactionDirective(obligation="kernel.redact.field", fields=["ssn"], target="user.profile")]
    sanitized = apply_redactions(body, directives)
    assert sanitized["user"]["profile"]["ssn"] == "***REDACTED***"

# tests/k0/policy/test_location_privacy.py
def test_mask_location_amber_band():
    body = {"location_lat": 37.7749, "location_lon": -122.4194}
    masked = mask_location_for_band(body, "AMBER")
    assert masked["location_lat"] is None
    assert masked["location_geohash"].startswith("9q8yy")  # 6-char geohash
    assert masked["location_precision_m"] == 5000

# tests/k0/policy/test_acl_enforcer.py
def test_check_permission_granted():
    enforcer = ACLEnforcer()
    # Setup: Grant permission
    enforcer.grant_permission("acl_001", "st_epi", "evt_123", "user", "usr_alice", "read", "usr_admin")
    assert enforcer.check_permission("st_epi", "evt_123", "usr_alice", "read") is True

# tests/k0/policy/test_retention_enforcer.py
def test_apply_policies_archives_expired(mocker):
    archive_callback = mocker.Mock(return_value="s3://archive/evt_123.gz")
    enforcer = RetentionEnforcer(archive_callback=archive_callback)
    stats = enforcer.apply_policies()
    assert stats["archived"] > 0
    archive_callback.assert_called()
```

### Integration Tests

```python
# tests/integration/test_policy_enforcement.py
def test_command_with_redaction_obligation(kernel_client):
    response = kernel_client.post("/api/v1/submit", json={
        "band": "AMBER",
        "topic": "health.records",
        "body": {"ssn": "123-45-6789", "diagnosis": "diabetes"}
    })
    assert response.status_code == 202
    wal_entry = db.query("SELECT redacted_body_json FROM st_wal ORDER BY wal_pos DESC LIMIT 1")
    sanitized = json.loads(wal_entry["redacted_body_json"])
    assert sanitized["ssn"] == "***REDACTED***"
```

---

## Performance & Observability

### Metrics

- `k0_pep_decisions_total{decision, band, schema_uri, lane}` (counter): PEP decisions (allow/deny)
- `k0_pep_obligations_total{obligation, decision, band}` (counter): Obligations emitted
- `k0_pep_evaluation_latency_ms{band, schema_uri, lane}` (histogram): Evaluation latency (buckets: 1, 5, 10, 25, 50, 100, 250ms)
- `policy_stamp_attached_total{tenant, band}` (counter): Policy stamps attached (Gap 42)
- `wal_policy_stamp_present_total{tenant, band}` (counter): WAL entries with policy stamps

### Traces

- Span: `pep.evaluate_envelope` (band, topic, admit)
- Span: `pep.redact_fields` (directive count, sanitized bytes)
- Span: `pep.mask_location` (band, precision_m)

### Logging

```json
{
  "event": "PEP allow",
  "band": "AMBER",
  "topic": "family.photos",
  "tenant": "tenant_123",
  "space": "space_456",
  "roles": ["parent"],
  "obligations": ["kernel.redact.pii"],
  "deny_reason": null
}
```

---

## Related Modules

- **`k0.ports.command`**: Command submission with policy enforcement
- **`k0.ports.query`**: Query recall with role-based access
- **`k0.ports.sse`**: SSE streaming with ACL filtering
- **`k0.storage.wal`**: Stores policy stamps and redacted bodies
- **`k0.receipts`**: Includes policy context in receipts
- **`k0.qos`**: Applies QoS obligations from policy decisions

---

## Related ADRs

- **ADR-0089**: Redaction Obligation Implementation
- **ADR-0091**: Privacy Band Architecture
- **ADR-0095**: Location Privacy with Geohash Masking
- **ADR-0099**: Retention Policies and Archival
- **ADR-0102**: ACL Row-Level Security
- **ADR-0104**: Policy Stamp Propagation

---

## Key Design Decisions

1. **Fail-safe DENY**: Corrupted manifest → deny all operations (Gap 36)
2. **Geohash masking**: GDPR/CCPA compliance via coarse location (5km AMBER, 25km RED)
3. **Policy stamps**: Immutable audit trail through entire pipeline (WAL → outbox → receipts)
4. **Non-mutating redaction**: Preserves original body for audit, returns sanitized copy
5. **Soft-delete ACLs**: `revoked_at` timestamp preserves audit trail
6. **Nightly retention**: Batch archival at 2 AM UTC to minimize production impact
7. **Capability-based limits**: Band-specific fanout/throughput/payload constraints
8. **Schema sunsets**: Warn-then-deny windows for graceful deprecation
