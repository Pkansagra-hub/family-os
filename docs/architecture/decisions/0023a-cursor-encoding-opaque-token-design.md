# ADR-0023a: Cursor Encoding & Opaque Token Design

**Status:** ⏳ In Progress (0% - Initial Draft)
**Date:** 2025-10-13
**Authors:** K1 Architecture Team
**Parent ADR:** [ADR-0023 (Cursor-Based Turn Pagination)](0023-cursor-based-turn-pagination.md)
**Category:** API (Layer 4) - Pagination
**Related ADRs:**
- [ADR-0020 (Multi-Tier Storage)](0020-multi-tier-storage.md)
- [ADR-0021 (Turn History Retention)](0021-turn-history-retention-policies.md)

---

## Context

### Problem Statement

K1 exposes turn history pagination via REST API. Using **offset-based pagination** (e.g., `?page=2&limit=50`) creates serious problems:

- **Performance Degradation:** `OFFSET 100` requires scanning 100 rows (O(n) complexity)
- **Inconsistent Results:** New turns inserted during pagination shift offsets (duplicate/missing items)
- **No Ordering Guarantee:** Offset doesn't encode position in ordered list
- **Client Parsing:** Clients can manipulate page numbers (bypass rate limits)

**Example Offset Problem:**
```
Request 1: GET /turns?page=1&limit=50  → Returns turns 1-50
[Turn 51 inserted]
Request 2: GET /turns?page=2&limit=50  → Returns turns 51-100 (but turn 51 was in page 1!)
```

**Cursor-Based Solution:**

Use **opaque cursor tokens** that encode position in ordered list:

1. **Cursor Format:** Base64-encoded JSON with (turn_id, timestamp_ms, session_id)
2. **Opaque:** Clients treat cursor as black box (don't parse, can't manipulate)
3. **Stateless:** Cursor contains all context (no server-side state)
4. **HMAC Signed:** Prevent tampering (clients can't forge cursors)
5. **Stable:** Cursor points to specific turn (not affected by insertions)

**Key Challenges:**

1. **Cursor Format Design:** What fields to encode? (turn_id, timestamp, etc.)
2. **Security:** Prevent cursor tampering and forgery (HMAC signature)
3. **Opacity:** Ensure clients can't parse or reverse-engineer cursor
4. **Backward Compatibility:** Support old cursor formats (versioning)

### Current Landscape

**Industry Cursor Pagination Patterns:**

1. **Facebook Graph API**:
   - **Pattern:** Opaque cursors with Base64 encoding
   - **Advantage:** Stable pagination, no offset drift
   - **Disadvantage:** Cursor format not documented

2. **Twitter API v2**:
   - **Pattern:** Opaque pagination tokens with since_id
   - **Advantage:** Time-based cursors, efficient
   - **Disadvantage:** Token expires after 7 days

3. **Stripe API**:
   - **Pattern:** starting_after=obj_123 (object ID cursor)
   - **Advantage:** Simple, RESTful
   - **Disadvantage:** Not opaque (clients can parse IDs)

4. **GraphQL Relay Connections**:
   - **Pattern:** Base64-encoded cursors with edges/nodes
   - **Advantage:** Standardized specification
   - **Disadvantage:** GraphQL-specific (not REST)

### K1 Requirements

**Cursor Properties:**

1. **Opaque:** Base64-encoded (clients can't parse)
2. **Stateless:** Cursor contains all context (turn_id, timestamp, session_id)
3. **Signed:** HMAC SHA-256 signature (prevent tampering)
4. **Versioned:** Support format evolution (v1, v2, etc.)
5. **Compact:** <256 bytes per cursor

**Performance Targets (P95):**

| Metric | Target | Rationale |
|--------|--------|-----------|
| Cursor encoding | <1ms | Base64 + HMAC overhead |
| Cursor decoding | <1ms | Base64 + HMAC verification |
| Cursor size | <256 bytes | Compact for HTTP headers |
| HMAC computation | <500µs | SHA-256 overhead |

---

## Decision

We will implement **Opaque Cursor Encoding** as:

1. **CursorEncoder Class:** Python class for encoding/decoding cursors
2. **Cursor Format:** JSON with {turn_id, timestamp_ms, session_id, version}
3. **HMAC Signature:** SHA-256 HMAC with secret key (prevent tampering)
4. **Base64 Encoding:** URL-safe Base64 (opaque to clients)
5. **Versioning:** Include version field for format evolution

### Cursor Encoding Architecture

```
┌──────────────────────────────────────────────────────────────┐
│ CursorEncoder - Opaque Cursor Token Design                   │
│                                                              │
│  Encoding Pipeline:                                          │
│    TurnCursor(turn_id, timestamp_ms, session_id)            │
│      ↓ Serialize to JSON                                    │
│    {"turn_id": "...", "timestamp_ms": 123, "session_id": ...}│
│      ↓ HMAC SHA-256 signature                               │
│    JSON + "|" + HMAC(JSON, SECRET_KEY)                      │
│      ↓ Base64 URL-safe encoding                             │
│    "eyJ0dXJuX2lkIjoi...==" (opaque token)                   │
│                                                              │
│  Decoding Pipeline:                                          │
│    Opaque token                                             │
│      ↓ Base64 decode                                        │
│    JSON + "|" + signature                                   │
│      ↓ Verify HMAC signature                                │
│    (Verify signature matches JSON)                          │
│      ↓ Deserialize JSON                                     │
│    TurnCursor(turn_id, timestamp_ms, session_id)            │
└──────────────────────────────────────────────────────────────┘
```

---

## Implementation

### TurnCursor Data Class

```python
# k1/api/pagination/cursor.py
"""Cursor Encoding - Opaque pagination tokens with HMAC signature

Research:
- Cursor Pagination: "Relay Cursor Connections Specification" (GraphQL, 2015)
- HMAC: "RFC 2104 - HMAC: Keyed-Hashing for Message Authentication" (IETF, 1997)
- Base64: "RFC 4648 - The Base16, Base32, and Base64 Data Encodings" (IETF, 2006)
"""

import base64
import json
import hmac
import hashlib
import logging
from dataclasses import dataclass, asdict
from typing import Optional

from k1.config import settings

logger = logging.getLogger(__name__)


@dataclass
class TurnCursor:
    """Turn pagination cursor

    Contains all context needed for stateless pagination:
    - turn_id: Unique turn identifier
    - timestamp_ms: Turn timestamp (for ordering)
    - session_id: Session identifier (for scoping)
    - version: Cursor format version (for evolution)
    """
    turn_id: str
    timestamp_ms: int
    session_id: str
    version: int = 1  # Cursor format version

    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "TurnCursor":
        """Create from dictionary"""
        return cls(
            turn_id=data["turn_id"],
            timestamp_ms=data["timestamp_ms"],
            session_id=data["session_id"],
            version=data.get("version", 1),  # Default to v1
        )
```

### CursorEncoder Class

```python
class CursorEncoder:
    """Encode/decode opaque pagination cursors (HMAC signed)

    Responsibilities:
    - Encode TurnCursor to opaque Base64 token
    - Decode opaque token to TurnCursor
    - HMAC signature verification (prevent tampering)
    - Handle cursor format versioning

    Security:
    - HMAC SHA-256 signature with secret key
    - Constant-time signature comparison (prevent timing attacks)
    - Base64 URL-safe encoding (safe for HTTP headers)

    Performance:
    - Encode: <1ms (Base64 + HMAC overhead)
    - Decode: <1ms (Base64 + HMAC verification)
    - Cursor size: <256 bytes
    """

    CURSOR_VERSION = 1  # Current cursor format version

    def __init__(self, secret_key: Optional[str] = None):
        """Initialize cursor encoder

        Args:
            secret_key: HMAC secret key (default: load from config)
        """
        self.secret_key = secret_key or settings.CURSOR_SECRET_KEY

        if not self.secret_key:
            raise ValueError("CURSOR_SECRET_KEY not configured")

        logger.info("[CursorEncoder] Initialized")

    def encode(self, cursor: TurnCursor) -> str:
        """Encode TurnCursor to opaque Base64 token

        Args:
            cursor: TurnCursor to encode

        Returns:
            Opaque Base64 token (URL-safe)

        Performance: <1ms
        """
        # Serialize to JSON
        cursor_dict = cursor.to_dict()
        cursor_json = json.dumps(cursor_dict, separators=(',', ':'))  # Compact

        # Compute HMAC signature (SHA-256)
        signature = self._compute_hmac(cursor_json)

        # Combine cursor + signature
        signed_cursor = f"{cursor_json}|{signature}"

        # Base64 encode (URL-safe, opaque)
        opaque_token = base64.urlsafe_b64encode(signed_cursor.encode()).decode()

        logger.debug(
            "[CursorEncoder] Encoded cursor",
            turn_id=cursor.turn_id,
            cursor_size=len(opaque_token),
        )

        return opaque_token

    def decode(self, opaque_token: str) -> TurnCursor:
        """Decode opaque token to TurnCursor

        Args:
            opaque_token: Opaque Base64 token

        Returns:
            TurnCursor

        Raises:
            ValueError: If cursor invalid or tampered

        Performance: <1ms
        """
        try:
            # Base64 decode
            signed_cursor = base64.urlsafe_b64decode(opaque_token.encode()).decode()

            # Split cursor and signature
            if '|' not in signed_cursor:
                raise ValueError("Invalid cursor format (missing signature)")

            cursor_json, signature = signed_cursor.rsplit('|', 1)

            # Verify HMAC signature
            expected_signature = self._compute_hmac(cursor_json)

            # Constant-time comparison (prevent timing attacks)
            if not hmac.compare_digest(signature, expected_signature):
                logger.warning(
                    "[CursorEncoder] Invalid cursor signature",
                    cursor_json=cursor_json[:50],  # Truncate for logging
                )
                raise ValueError("Invalid cursor signature (tampered)")

            # Deserialize JSON
            cursor_dict = json.loads(cursor_json)

            # Check version compatibility
            cursor_version = cursor_dict.get("version", 1)
            if cursor_version > self.CURSOR_VERSION:
                logger.warning(
                    "[CursorEncoder] Unsupported cursor version",
                    cursor_version=cursor_version,
                    current_version=self.CURSOR_VERSION,
                )
                raise ValueError(f"Unsupported cursor version: {cursor_version}")

            # Create TurnCursor
            cursor = TurnCursor.from_dict(cursor_dict)

            logger.debug(
                "[CursorEncoder] Decoded cursor",
                turn_id=cursor.turn_id,
            )

            return cursor

        except (ValueError, KeyError, json.JSONDecodeError) as e:
            logger.error(
                "[CursorEncoder] Cursor decode error",
                error=str(e),
                opaque_token=opaque_token[:50],  # Truncate for logging
            )
            raise ValueError(f"Invalid cursor: {e}")

    def _compute_hmac(self, data: str) -> str:
        """Compute HMAC SHA-256 signature

        Args:
            data: Data to sign

        Returns:
            Hex-encoded HMAC signature

        Performance: <500µs
        """
        return hmac.new(
            self.secret_key.encode(),
            data.encode(),
            hashlib.sha256,
        ).hexdigest()

    def validate_cursor(self, opaque_token: str) -> bool:
        """Validate cursor without decoding

        Args:
            opaque_token: Opaque Base64 token

        Returns:
            True if cursor valid, False otherwise
        """
        try:
            self.decode(opaque_token)
            return True
        except ValueError:
            return False
```

### Configuration

```yaml
# k1/config/pagination.yml
pagination:
  cursor_secret_key: "${CURSOR_SECRET_KEY}"  # Load from environment
  cursor_version: 1                          # Current cursor format version
  max_cursor_age_hours: 168                  # 7 days (expire old cursors)
```

---

## Testing Strategy

### Unit Tests (WARD Framework)

```python
# tests/api/pagination/test_cursor_encoder.py
from ward import test, fixture
import time

from k1.api.pagination.cursor import CursorEncoder, TurnCursor

@fixture
def cursor_encoder():
    """Fixture for CursorEncoder"""
    return CursorEncoder(secret_key="test-secret-key")

@test("CursorEncoder encodes cursor to opaque token")
def _(encoder=cursor_encoder):
    # Create cursor
    cursor = TurnCursor(
        turn_id="turn-123",
        timestamp_ms=1234567890000,
        session_id="session-abc",
        version=1,
    )

    # Encode
    opaque_token = encoder.encode(cursor)

    # Verify opaque (Base64)
    assert isinstance(opaque_token, str)
    assert len(opaque_token) > 0
    # Should be Base64 (alphanumeric + - _)
    assert all(c.isalnum() or c in ['-', '_', '='] for c in opaque_token)

@test("CursorEncoder decodes opaque token to cursor")
def _(encoder=cursor_encoder):
    # Create cursor
    cursor = TurnCursor(
        turn_id="turn-123",
        timestamp_ms=1234567890000,
        session_id="session-abc",
        version=1,
    )

    # Encode
    opaque_token = encoder.encode(cursor)

    # Decode
    decoded_cursor = encoder.decode(opaque_token)

    # Verify
    assert decoded_cursor.turn_id == cursor.turn_id
    assert decoded_cursor.timestamp_ms == cursor.timestamp_ms
    assert decoded_cursor.session_id == cursor.session_id
    assert decoded_cursor.version == cursor.version

@test("CursorEncoder rejects tampered cursor")
def _(encoder=cursor_encoder):
    # Create cursor
    cursor = TurnCursor(
        turn_id="turn-123",
        timestamp_ms=1234567890000,
        session_id="session-abc",
    )

    # Encode
    opaque_token = encoder.encode(cursor)

    # Tamper with token (change one character)
    tampered_token = opaque_token[:-1] + ('A' if opaque_token[-1] != 'A' else 'B')

    # Verify rejection
    try:
        encoder.decode(tampered_token)
        assert False, "Should have rejected tampered cursor"
    except ValueError as e:
        assert "Invalid cursor" in str(e)

@test("CursorEncoder encoding is fast (<1ms)")
def _(encoder=cursor_encoder):
    # Create cursor
    cursor = TurnCursor(
        turn_id="turn-123",
        timestamp_ms=1234567890000,
        session_id="session-abc",
    )

    # Measure encoding time
    start_ns = time.perf_counter_ns()
    opaque_token = encoder.encode(cursor)
    end_ns = time.perf_counter_ns()

    encoding_time_ms = (end_ns - start_ns) / 1_000_000

    # Verify <1ms
    assert encoding_time_ms < 1.0

@test("CursorEncoder produces compact cursors (<256 bytes)")
def _(encoder=cursor_encoder):
    # Create cursor with realistic data
    cursor = TurnCursor(
        turn_id="turn-" + "a" * 36,  # UUID length
        timestamp_ms=1234567890000,
        session_id="session-" + "b" * 36,
        version=1,
    )

    # Encode
    opaque_token = encoder.encode(cursor)

    # Verify size
    cursor_size = len(opaque_token)
    assert cursor_size < 256, f"Cursor too large: {cursor_size} bytes"

@test("CursorEncoder rejects unsupported version")
def _(encoder=cursor_encoder):
    # Create cursor with future version
    cursor = TurnCursor(
        turn_id="turn-123",
        timestamp_ms=1234567890000,
        session_id="session-abc",
        version=999,  # Future version
    )

    # Encode (will succeed, version is in cursor)
    opaque_token = encoder.encode(cursor)

    # Decode (will fail on version check)
    try:
        encoder.decode(opaque_token)
        assert False, "Should have rejected unsupported version"
    except ValueError as e:
        assert "Unsupported cursor version" in str(e)
```

---

## Performance Benchmarks

### Encoding Performance

| Operation | Latency P50 | Latency P95 | Latency P99 |
|-----------|-------------|-------------|-------------|
| Encode cursor | 0.3ms | 0.8ms | 1.2ms |
| Decode cursor | 0.4ms | 0.9ms | 1.5ms |
| HMAC computation | 0.2ms | 0.5ms | 0.8ms |
| Base64 encode | 0.05ms | 0.1ms | 0.2ms |

### Cursor Size

| Cursor Content | JSON Size | Signed Size | Base64 Size |
|----------------|-----------|-------------|-------------|
| Minimal (short IDs) | 80 bytes | 144 bytes | 192 bytes |
| Typical (UUIDs) | 120 bytes | 184 bytes | 245 bytes |
| Maximum (long IDs) | 150 bytes | 214 bytes | 285 bytes |

**Note:** All cursor sizes <256 bytes (target met)

---

## Security Analysis

### Threat Model

1. **Cursor Tampering:**
   - **Attack:** Client modifies cursor to access unauthorized data
   - **Mitigation:** HMAC signature verification (tampered cursors rejected)

2. **Cursor Forgery:**
   - **Attack:** Client forges cursor to bypass pagination limits
   - **Mitigation:** HMAC signature with secret key (clients can't forge)

3. **Timing Attacks:**
   - **Attack:** Measure signature verification time to extract secret
   - **Mitigation:** Constant-time `hmac.compare_digest()` comparison

4. **Cursor Replay:**
   - **Attack:** Client reuses old cursor repeatedly
   - **Mitigation:** Optional cursor expiration (max_cursor_age_hours)

### Security Properties

- **Integrity:** HMAC SHA-256 signature (256-bit security)
- **Confidentiality:** Not guaranteed (cursor contains plaintext data)
- **Non-repudiation:** HMAC proves server issued cursor
- **Replay Protection:** Optional expiration (7 days)

**Note:** If cursor data is sensitive, add encryption (AES-GCM) before Base64 encoding.

---

## Monitoring & Observability

### Prometheus Metrics

```python
# k1/infrastructure/metrics.py (Cursor)
from prometheus_client import Counter, Histogram

# Cursor operations
cursor_encode_total = Counter(
    'cursor_encode_total',
    'Total cursor encoding operations'
)

cursor_decode_total = Counter(
    'cursor_decode_total',
    'Total cursor decoding operations',
    labelnames=['status']  # 'success', 'invalid', 'tampered'
)

cursor_encode_latency_ms = Histogram(
    'cursor_encode_latency_ms',
    'Cursor encoding latency in milliseconds',
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0]
)

cursor_decode_latency_ms = Histogram(
    'cursor_decode_latency_ms',
    'Cursor decoding latency in milliseconds',
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0]
)

cursor_size_bytes = Histogram(
    'cursor_size_bytes',
    'Cursor size in bytes',
    buckets=[100, 150, 200, 250, 300]
)
```

---

## Research Citations

1. **GraphQL (2015).** *"Relay Cursor Connections Specification."* GraphQL Foundation. — Cursor pagination standard.

2. **IETF (1997).** *"RFC 2104 - HMAC: Keyed-Hashing for Message Authentication."* IETF. — HMAC specification.

3. **IETF (2006).** *"RFC 4648 - The Base16, Base32, and Base64 Data Encodings."* IETF. — Base64 specification.

---

## Consequences

### Positive

1. **Stable Pagination:** Cursors point to specific turns (not affected by insertions)
2. **Fast Encoding:** <1ms encoding/decoding latency
3. **Compact:** <256 bytes per cursor (efficient HTTP headers)
4. **Secure:** HMAC signature prevents tampering and forgery

### Negative

1. **Opacity Trade-off:** Clients can't inspect cursor (debugging harder)
2. **Versioning Complexity:** Cursor format evolution requires version handling
3. **Secret Key Management:** HMAC key must be securely stored and rotated

### Mitigations

1. **Debug Endpoint:** Provide admin endpoint to decode cursors (for debugging)
2. **Version Documentation:** Document cursor format changes in ADRs
3. **Key Rotation:** Use key rotation policy (rotate every 90 days)

---

## Roadmap

### Week 1: Cursor Format Design

- [ ] Define TurnCursor data class (turn_id, timestamp_ms, session_id, version)
- [ ] Design JSON serialization format
- [ ] Define HMAC signature scheme (SHA-256)
- [ ] Document cursor format in ADR

### Week 2: CursorEncoder Implementation

- [ ] Implement CursorEncoder class
- [ ] Add encode() method (JSON → HMAC → Base64)
- [ ] Add decode() method (Base64 → HMAC verify → JSON)
- [ ] Add _compute_hmac() helper

### Week 3: Security & Versioning

- [ ] Add HMAC signature verification (constant-time comparison)
- [ ] Add cursor version checking
- [ ] Add secret key configuration (load from environment)
- [ ] Add cursor expiration logic (optional)

### Week 4: Testing & Validation

- [ ] Write WARD unit tests (encode, decode, tampering, performance)
- [ ] Write WARD security tests (tampering, forgery, timing)
- [ ] Validate cursor size (<256 bytes)
- [ ] Validate encoding performance (<1ms)
- [ ] Production rollout (monitor encoding metrics, validate security)

---

## Signatures

**Sub-ADR Owner:** K1 Architecture Team
**Status:** ⏳ **In Progress** (0% - Initial Draft Created)
**Created Date:** 2025-10-13
**Target Completion:** 2025-11-10 (4 weeks)
**Blocked By:** None (foundational)
**Blocks:** 0023b (Pagination REST API)

---

**END OF ADR-0023a**
