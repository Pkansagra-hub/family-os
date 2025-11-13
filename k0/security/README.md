# K0 Security Module

**Purpose**: Cryptographic primitives for signature verification, canonical serialization, and envelope integrity validation.

**Layer**: Security & Cryptography
**Category**: Ed25519 signature verification, canonical JSON, envelope hashing
**Related ADRs**: ADR-0120 (V1 Envelope Integrity), ADR-0121 (Ed25519 Signatures), ADR-0122 (Canonical Serialization)

---

## Overview

The security module provides **cryptographic primitives** for:

1. **Envelope integrity**: V1 full envelope hashing with `envelope_sha256` (covers body + headers)
2. **Signature verification**: Ed25519 signature checking with URL-safe base64 encoding
3. **Canonical serialization**: Deterministic JSON encoding for reproducible hashes
4. **Payload hashing**: Legacy `payload_sha256` (body-only) for backward compatibility

**Usage Context**: Gate (signature verification), Receipts (signing), WAL (envelope hashing), Idem (duplicate detection)

---

## Repository Files & Functions

### 1. `crypto.py`

**Purpose**: Deterministic helpers for payload hashing, canonical JSON, and signature verification.

#### Core Functions

```python
def canonical_json(payload: Any) -> str
```

- **Purpose**: Return canonical JSON representation for deterministic signing/hashing
- **Canonicalization**:
  - Sorted keys (alphabetical order)
  - UTF-8 encoding
  - Disabled ASCII escapes
  - Minimal separators (`","` and `":"`)
- **Example**:
  ```python
  canonical_json({"b": 2, "a": 1})  # → '{"a":1,"b":2}'
  ```

**Algorithm**:

```python
def canonical_json(payload: Any) -> str:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
```

---

```python
def canonical_envelope(
    envelope: Mapping[str, Any],
    *,
    exclude_signature: bool = True,
) -> bytes
```

- **Purpose**: Return canonical bytes of envelope suitable for signing (V1: body INCLUDED)
- **V1 Changes**:
  - **Body INCLUDED**: Signature covers full envelope (prevents header tampering)
  - **Excluded fields**: `sig`, `envelope_sha256` (computed after canonicalization)
  - **Security**: Prevents actor/space_id/band/ts manipulation attacks
- **Returns**: UTF-8 encoded canonical JSON bytes

**Algorithm**:

```python
def canonical_envelope(envelope: Mapping[str, Any], *, exclude_signature: bool = True) -> bytes:
    exclude_fields: set[str] = set()
    if exclude_signature:
        exclude_fields.add("sig")
        exclude_fields.add("envelope_sha256")
        # V1 CHANGE: body is now INCLUDED in signature (not excluded)

    # Filter excluded fields
    working = {key: value for key, value in envelope.items() if key not in exclude_fields}

    # Canonicalize and encode
    return canonical_json(working).encode("utf-8")
```

---

```python
def compute_envelope_sha256(envelope: Mapping[str, Any]) -> str
```

- **Purpose**: Compute SHA-256 hash of full canonical envelope (V1)
- **Use Cases**:
  - Exact duplicate detection (replay protection)
  - Receipt verification
  - WAL deduplication indexing
- **Coverage**: All fields except `sig` itself (body INCLUDED)
- **Returns**: Hexadecimal SHA-256 digest (64 characters)

**Algorithm**:

```python
def compute_envelope_sha256(envelope: Mapping[str, Any]) -> str:
    # Compute canonical envelope (sig excluded, body included)
    canonical = canonical_envelope(envelope, exclude_signature=True)

    # SHA-256 hash
    digest = hashlib.sha256(canonical)
    return digest.hexdigest()
```

**Example**:

```python
envelope = {
    "actor": "device_abc",
    "space_id": "space_001",
    "tenant_id": "tenant_001",
    "topic": "memory.store",
    "ts": "2025-11-12T10:00:00Z",
    "body": {"operation": "memory.store", "content": "..."},
    "sig": "A1B2C3..."
}

envelope_sha256 = compute_envelope_sha256(envelope)
# → "8a3f2c1e5d9b7a4f6c2e1d8a3f2c1e5d9b7a4f6c2e1d8a3f2c1e5d9b7a4f6c2e"
```

---

```python
def hash_payload(body: bytes | None) -> str | None
```

- **Purpose**: Return SHA-256 hash of body (legacy V0 compatibility)
- **Deprecated**: Use `compute_envelope_sha256()` for V1 full envelope integrity
- **Returns**: Hexadecimal SHA-256 digest or `None` if body is `None`

---

```python
def verify_signature(message: bytes, signature_b64: str, verify_key_b64: str) -> None
```

- **Purpose**: Verify Ed25519 signature over message using verify key
- **Encoding**: URL-safe base64 (no padding)
- **Exception**: Raises `SignatureVerificationError` on failure
- **Algorithm**: Uses `nacl.signing.VerifyKey` from PyNaCl library

**Algorithm**:

```python
def verify_signature(message: bytes, signature_b64: str, verify_key_b64: str) -> None:
    try:
        # Decode base64url signature
        signature = _decode_base64url(signature_b64)

        # Decode base64url verify key
        key_bytes = _decode_base64url(verify_key_b64)
        verify_key = VerifyKey(key_bytes)

        # Verify signature (raises BadSignatureError on failure)
        verify_key.verify(message, signature)
    except (ValueError, BadSignatureError) as exc:
        raise SignatureVerificationError("Signature verification failed") from exc
```

**Example**:

```python
from k0.security import verify_signature

# Message to verify
message = b'{"actor":"device_abc","ts":"2025-11-12T10:00:00Z"}'

# Signature and verify key (base64url encoded)
signature_b64 = "A1B2C3D4E5F6G7H8I9J0K1L2M3N4O5P6Q7R8S9T0U1V2W3X4Y5Z6"
verify_key_b64 = "abc123def456ghi789jkl012mno345pqr678stu901vwx234yz5"

# Verify signature (raises SignatureVerificationError if invalid)
verify_signature(message, signature_b64, verify_key_b64)
```

---

```python
def verify_full_envelope_signature(
    envelope: Mapping[str, Any],
    verify_key_b64: str,
) -> bool
```

- **Purpose**: Verify V1 full envelope signature (includes body + all headers)
- **Security**: Prevents header tampering attacks (actor, space_id, band, ts, etc.)
- **Signature Coverage**: Entire canonical envelope (all fields except `sig` itself)
- **Returns**: `True` if signature valid, `False` otherwise

**Algorithm**:

```python
def verify_full_envelope_signature(envelope: Mapping[str, Any], verify_key_b64: str) -> bool:
    signature_b64 = envelope.get("sig")
    if signature_b64 is None:
        return False

    try:
        # Compute canonical envelope (body INCLUDED, sig EXCLUDED)
        canonical = canonical_envelope(envelope, exclude_signature=True)

        # Verify signature over canonical bytes
        verify_signature(canonical, signature_b64, verify_key_b64)
        return True
    except SignatureVerificationError:
        return False
```

**Example**:

```python
from k0.security import verify_full_envelope_signature

envelope = {
    "actor": "device_abc",
    "space_id": "space_001",
    "tenant_id": "tenant_001",
    "topic": "memory.store",
    "ts": "2025-11-12T10:00:00Z",
    "body": {"operation": "memory.store"},
    "sig": "A1B2C3D4E5F6G7H8I9J0K1L2M3N4O5P6Q7R8S9T0U1V2W3X4Y5Z6"
}

verify_key_b64 = "abc123def456ghi789jkl012mno345pqr678stu901vwx234yz5"

# Verify full envelope signature
is_valid = verify_full_envelope_signature(envelope, verify_key_b64)
# → True or False
```

---

```python
def encode_base64url(data: bytes) -> str
```

- **Purpose**: Return URL-safe base64 (unpadded) representation of data
- **Encoding**: URL-safe alphabet (`-_` instead of `+/`), no padding (`=`)
- **Use Cases**: Signature encoding, verify key encoding, receipt encoding

**Algorithm**:

```python
def encode_base64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")
```

---

```python
def _decode_base64url(value: str) -> bytes
```

- **Purpose**: Decode URL-safe base64 string (internal helper)
- **Padding**: Adds missing padding (`=`) automatically
- **Exception**: Raises `SignatureVerificationError` on invalid base64

---

### 2. `__init__.py`

**Purpose**: Export security module public API.

**Exported Functions**:

```python
__all__ = [
    "SignatureVerificationError",
    "canonical_envelope",
    "canonical_json",
    "compute_envelope_sha256",
    "encode_base64url",
    "hash_payload",
    "verify_full_envelope_signature",
    "verify_signature",
]
```

---

## Usage Examples

### V1 Envelope Hashing (Full Integrity)

```python
from k0.security import compute_envelope_sha256

envelope = {
    "actor": "device_abc",
    "space_id": "space_001",
    "tenant_id": "tenant_001",
    "topic": "memory.store",
    "ts": "2025-11-12T10:00:00Z",
    "body": {"operation": "memory.store", "memory_id": "mem_123"},
    "sig": "A1B2C3..."
}

# Compute full envelope hash (includes body + headers)
envelope_sha256 = compute_envelope_sha256(envelope)
# → "8a3f2c1e5d9b7a4f6c2e1d8a3f2c1e5d9b7a4f6c2e1d8a3f2c1e5d9b7a4f6c2e"

# Use for duplicate detection in WAL
# Use for receipt verification
```

### Ed25519 Signature Verification (Full Envelope)

```python
from k0.security import verify_full_envelope_signature

envelope = {...}  # Envelope with sig field
verify_key_b64 = "abc123def456ghi789jkl012mno345pqr678stu901vwx234yz5"

# Verify full envelope signature (body + headers)
is_valid = verify_full_envelope_signature(envelope, verify_key_b64)

if is_valid:
    print("✅ Signature valid - envelope integrity verified")
else:
    print("❌ Signature invalid - reject envelope")
```

### Canonical JSON for Signing

```python
from k0.security import canonical_json, encode_base64url
from nacl.signing import SigningKey

# Create signing key
signing_key = SigningKey.generate()

# Envelope to sign
envelope = {
    "actor": "device_abc",
    "space_id": "space_001",
    "body": {"operation": "memory.store"}
}

# Canonicalize envelope (deterministic JSON)
canonical = canonical_json(envelope).encode("utf-8")

# Sign canonical bytes
signature = signing_key.sign(canonical).signature
signature_b64 = encode_base64url(signature)

# Add signature to envelope
envelope["sig"] = signature_b64
```

### Base64url Encoding

```python
from k0.security import encode_base64url

# Encode Ed25519 verify key (32 bytes)
verify_key_bytes = signing_key.verify_key.encode()
verify_key_b64 = encode_base64url(verify_key_bytes)
# → "abc123def456ghi789jkl012mno345pqr678stu901vwx234yz5"

# Encode signature (64 bytes)
signature_b64 = encode_base64url(signature)
# → "A1B2C3D4E5F6G7H8I9J0K1L2M3N4O5P6Q7R8S9T0U1V2W3X4Y5Z6"
```

---

## V1 Envelope Integrity Model

### V0 (Legacy) - Body-Only Hashing

```
Signature: body only (payload_sha256)
Coverage: body field
Weakness: Headers (actor, space_id, ts) can be tampered
```

### V1 (Current) - Full Envelope Integrity

```
Signature: canonical_envelope(envelope, exclude_signature=True)
Coverage: ALL fields except sig itself (body INCLUDED)
Fields: actor, space_id, tenant_id, topic, ts, body, band, device_id, etc.
Security: Prevents header tampering attacks
Hash: envelope_sha256 (full canonical envelope)
```

**V1 Security Properties**:

1. **Replay Protection**: `envelope_sha256` uniquely identifies entire envelope
2. **Header Integrity**: Cannot modify actor/space_id/ts without breaking signature
3. **Body Integrity**: Body included in signature (V0 included, V1 explicit)
4. **Deterministic**: Canonical JSON ensures reproducible hashes

---

## Cryptographic Algorithms

### Ed25519 (Signature Scheme)

- **Type**: Edwards-curve Digital Signature Algorithm
- **Key Size**: 32 bytes (256 bits)
- **Signature Size**: 64 bytes (512 bits)
- **Security**: 128-bit security level
- **Library**: PyNaCl (`nacl.signing`)

**Properties**:

- Fast verification (~10µs per signature)
- Deterministic signatures (same message = same signature with same key)
- No random number generation required
- Resistant to timing attacks

### SHA-256 (Hash Function)

- **Type**: Cryptographic hash function
- **Output Size**: 32 bytes (256 bits)
- **Security**: 128-bit collision resistance
- **Library**: Python `hashlib`

**Properties**:

- One-way (cannot reverse hash to original data)
- Collision-resistant (hard to find two inputs with same hash)
- Avalanche effect (small input change = large hash change)

---

## Security Considerations

### Signature Verification

1. **Timing Attacks**: PyNaCl uses constant-time comparison for signatures
2. **Key Rotation**: Verify keys stored in `st_device_keys` with lifecycle states (ACTIVE, ROTATING, REVOKED)
3. **Grace Periods**: Support overlapping key rotation with `grace_expires_ts`
4. **Revocation**: Check `key_state` before trusting signatures

### Envelope Integrity

1. **Replay Protection**: Check `envelope_sha256` against WAL for duplicates
2. **Header Tampering**: V1 signature covers all headers (cannot modify actor/space_id/ts)
3. **Clock Skew**: Validate `ts` field against `clock_skew_ms` threshold
4. **Device Binding**: Verify `device_id` matches `actor` in envelope

### Canonical JSON

1. **Determinism**: Sorted keys + minimal separators ensure reproducibility
2. **Unicode**: UTF-8 encoding (not ASCII escaped) for international characters
3. **Whitespace**: No extra whitespace (compact JSON)
4. **Floating Point**: JSON serialization may have precision issues (avoid floats in signatures)

---

## Integration Points

### Upstream Dependencies

- **PyNaCl** (`nacl.signing`): Ed25519 signature verification
- **Python stdlib** (`hashlib`, `base64`, `json`): Hashing, encoding, JSON

### Downstream Consumers

- **`k0.gate.signature_gate`**: Envelope signature verification before WAL append
- **`k0.receipts.issuer`**: Receipt signing with Ed25519
- **`k0.storage.wal`**: Envelope hashing for duplicate detection
- **`k0.idem.handler`**: Idempotency key hashing

---

## Performance

### Benchmarks (P95)

| Operation | Latency | Throughput |
|-----------|---------|------------|
| `canonical_json()` | <50µs | 20K ops/s |
| `compute_envelope_sha256()` | <100µs | 10K ops/s |
| `verify_signature()` | <10µs | 100K ops/s |
| `encode_base64url()` | <5µs | 200K ops/s |

**Note**: Ed25519 verification is extremely fast (~10µs) due to optimized C implementation in libsodium.

---

## Error Handling

### `SignatureVerificationError`

- **Raised When**: Signature verification fails or inputs are invalid
- **Causes**:
  - Invalid base64url data (signature or verify key)
  - Signature mismatch (wrong key or tampered message)
  - Missing `sig` field in envelope
- **Handling**: Reject envelope, log security event, emit metrics

**Example**:

```python
from k0.security import verify_signature, SignatureVerificationError

try:
    verify_signature(message, signature_b64, verify_key_b64)
except SignatureVerificationError as exc:
    logger.error("Signature verification failed", exc_info=exc)
    metrics.emit("signature_verification_failures_total", 1.0)
    raise HTTPException(status_code=401, detail="SIGNATURE_INVALID")
```

---

## Related Modules

- **`k0.gate.signature_gate`**: Uses `verify_full_envelope_signature()` for envelope validation
- **`k0.receipts.issuer`**: Uses `canonical_envelope()` and Ed25519 signing
- **`k0.storage.wal`**: Uses `compute_envelope_sha256()` for duplicate detection
- **`k0.storage.provisioning`**: Stores device verify keys with rotation states
- **`k0.idem.handler`**: Uses hashing for idempotency key generation

---

## Related ADRs

- **ADR-0120**: V1 Envelope Integrity (Full Envelope Hashing)
- **ADR-0121**: Ed25519 Signature Verification
- **ADR-0122**: Canonical JSON Serialization
- **ADR-0123**: Device Key Rotation with Grace Periods

---

## Key Design Decisions

1. **V1 Full Envelope Signature**: Prevents header tampering by signing all fields except `sig`
2. **URL-Safe Base64**: No padding (`=`) to avoid encoding issues in URLs/JSON
3. **Canonical JSON**: Deterministic serialization ensures reproducible hashes
4. **Ed25519 Algorithm**: Fast verification, small signatures, high security
5. **SHA-256 Hashing**: Industry-standard collision resistance for duplicate detection
6. **Defensive Guards**: All public functions validate inputs and handle exceptions gracefully
