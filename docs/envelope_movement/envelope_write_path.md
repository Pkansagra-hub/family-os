# Envelope Write Path - Complete Transformation Journey

**Document Purpose:** Track envelope structure and field changes through K0 write pipeline
**Date:** 2025-11-10
**Source:** Actual architecture from memoryOS_frozen + whiteboard_schema.md

---

## Overview: Write Path Stages

```
1. K1 Orchestrator → Forms envelope
2. Command Port (/k0/command.submit) → Receives envelope
3. MinimalGate → Validates envelope
4. Policy Evaluator (PEP) → Checks permissions
5. Memory Steward → Orchestrates write
6. Hippocampus API → Pattern separation
7. st_hipp_store → Staging database
```

---

## Stage 1: K1 Orchestrator Forms Envelope

**Location:** K1 orchestration kernel (external to K0)
**Responsibility:** K1 has LLMs + hardware access, pre-processes content

### What K1 Does:
- Calls mobile/desktop **location services** (GPS)
- Runs **LLM analysis** on user input (topics, sentiment, participants)
- Calls **hardware APIs** for device context
- Forms standardized envelope with body schema

### Envelope at K1 Output (Before K0):

```json
{
  "_comment": "ENVELOPE METADATA (Required by envelope.schema.json)",
  "cognitive_trace_id": "11111111-2222-3333-4444-555555555555",
  "tenant_id": "family-smith",
  "space_id": "personal:dad",
  "topic": "memory.episodic.formation",
  "schema_uri": "https://contracts.family-ai.dev/schemas/memory.episodic.json",
  "schema_version": "1.0.0",
  "actor": "person_dad",
  "device_id": "device-dad-phone",
  "band": "AMBER",
  "policy_version": "2025-11-01",
  "ts": "2025-11-10T18:00:00Z",
  "sig": "MEUCIQD1lF8Qvf9wG0Cjd8nYQ0BfJ4ZC2x7Lrv3N5YFhV6t9WgIgS5n4xv7QzSp6Yjpm3zDR6hccgZL4z6hA1Pd1yEi8Zv8=",
  "payload_sha256": "4f2a6b7c0d9e1f2a3b4c5d6e7f8091a2b3c4d5e6f708192a3b4c5d6e7f8091a2",
  "idem_key": "family-smith:personal:dad:memory.episodic.formation:evt-20251110-abc123",

  "_comment": "ENVELOPE BODY (Flexible schema, varies by schema_uri)",
  "body": {
    "_comment": "K1 LLM ANALYSIS (Pre-processed)",
    "text": "We had dinner at Olive Garden with Mom and it was great",
    "topics": ["family", "dining", "social"],
    "sentiment": 0.8,
    "sentiment_label": "positive",
    "emotion_tags": ["joy", "contentment"],
    "categories": ["social", "meal"],
    "activity_type": "dinner",
    "activity_category": "dining",

    "_comment": "K1 HARDWARE (GPS from mobile device)",
    "location_name": "Olive Garden, Market St",
    "location_type": "restaurant",
    "location_lat": 37.7749,
    "location_lon": -122.4194,

    "_comment": "K1 CONTEXT (Orchestrator provides)",
    "participants": ["person_dad", "person_mom"],
    "event_time": "2025-11-10T18:00:00Z",
    "session_id": "session-abc123",
    "conversation_turn": 5,
    "language": "en"
  }
}
```

**Key Points (V1):**
- ✅ K1 already did LLM analysis (topics, sentiment, emotions)
- ✅ K1 already got location from hardware (GPS)
- ✅ **NEW**: Full envelope signature (sig covers entire envelope, not just body)
- ✅ **NEW**: `sig_alg`, `sig_kid` specify signature algorithm and key
- ✅ **NEW**: `envelope_sha256` replaces `payload_sha256` (covers full envelope)
- ✅ **NEW**: `idem_key` is HMAC-derived (prevents replay attacks)
- ✅ Body schema flexible (varies by schema_uri)
- ✅ Envelope is complete and ready for K0

---

## Stage 2: Command Port Receives Envelope

**Location:** `k0/ports/command.py`
**Entry Point:** `POST /k0/command.submit`
**Responsibility:** HTTP handler, Pydantic validation

### What Happens:
1. HTTP POST receives JSON payload
2. Pydantic model validates against `envelope.schema.json`
3. Creates internal `Envelope` object
4. Passes to MinimalGate

### Envelope After Command Port (No Changes) - V1:

```json
{
  "_comment": "IDENTICAL TO K1 OUTPUT - Command Port only validates structure",
  "cognitive_trace_id": "11111111-2222-3333-4444-555555555555",
  "tenant_id": "family-smith",
  "space_id": "personal:dad",
  "topic": "memory.episodic.formation",
  "schema_uri": "https://contracts.family-ai.dev/schemas/memory.episodic.json",
  "schema_version": "1.0.0",
  "actor": "person_dad",
  "device_id": "device-dad-phone",
  "band": "AMBER",
  "policy_version": "2025-11-01",
  "ts": "2025-11-10T18:00:00Z",
  "sig_alg": "ECDSA_P256_SHA256",
  "sig_kid": "did:device:dad-phone#2025-10-01",
  "envelope_sha256": "4f2a6b7c0d9e1f2a3b4c5d6e7f8091a2b3c4d5e6f708192a3b4c5d6e7f8091a2",
  "sig": "MEUCIQD1lF8Qvf9wG0Cjd8nYQ0BfJ4ZC2x7Lrv3N5YFhV6t9WgIgS5n4xv7QzSp6Yjpm3zDR6hccgZL4z6hA1Pd1yEi8Zv8=",
  "idem_key": "idem:7c3e8f2a9b4d6e1f3c5a7b9d2e4f6a8c",
  "body": {
    "text": "We had dinner at Olive Garden with Mom and it was great",
    "topics": ["family", "dining", "social"],
    "sentiment": 0.8,
    "sentiment_label": "positive",
    "emotion_tags": ["joy", "contentment"],
    "categories": ["social", "meal"],
    "activity_type": "dinner",
    "activity_category": "dining",
    "location_name": "Olive Garden, Market St",
    "location_type": "restaurant",
    "location_lat": 37.7749,
    "location_lon": -122.4194,
    "participants": ["person_dad", "person_mom"],
    "event_time": "2025-11-10T18:00:00Z",
    "session_id": "session-abc123",
    "conversation_turn": 5,
    "language": "en"
  }
}
```

**Validation Checks (V1):**
- ✅ JSON schema validation (envelope.schema.json V1)
- ✅ Required fields present (including sig_alg, sig_kid, envelope_sha256)
- ✅ Topic pattern matches: `^(memory|events|ui|policy|infra\.sanitized|privacy|intelligence\.advisory)\..+`
- ✅ Band enum: GREEN/AMBER/RED
- ✅ Timestamp format: ISO 8601
- ✅ `sig_alg` is valid algorithm (ECDSA_P256_SHA256, etc.)
- ✅ `sig_kid` format valid (DID or key identifier)

---

## Stage 3: MinimalGate Validation

**Location:** `k0/gate/minimal_gate.py`
**Responsibility:** Schema, signature, hash validation

### What Happens (V1 Enhanced):
1. **Schema Validation:** Verify envelope structure against V1 schema
2. **Signature Validation:** Verify `sig` covers FULL envelope (not just body)
   - Compute canonical envelope (exclude `sig` field)
   - Compute SHA256 hash
   - Verify computed hash matches `envelope_sha256`
   - Verify ECDSA signature using `sig_kid` public key
3. **Time Validation:** Reject if `abs(now - ts) > 10 minutes`
4. **Idempotency Check:** Query `idem_key` in ledger AND check `envelope_sha256` in WAL
5. **Clock Metadata:** Add `ingested_at` (server time) and `clock_skew_ms`

### Envelope After MinimalGate (With Time Metadata Added) - V1:

```json
{
  "_comment": "TIME METADATA ADDED - MinimalGate validates and adds server timestamps",
  "cognitive_trace_id": "11111111-2222-3333-4444-555555555555",
  "tenant_id": "family-smith",
  "space_id": "personal:dad",
  "topic": "memory.episodic.formation",
  "schema_uri": "https://contracts.family-ai.dev/schemas/memory.episodic.json",
  "schema_version": "1.0.0",
  "actor": "person_dad",
  "device_id": "device-dad-phone",
  "band": "AMBER",
  "policy_version": "2025-11-01",
  "ts": "2025-11-10T18:00:00Z",

  "_comment": "V1 SECURITY FIELDS",
  "sig_alg": "ECDSA_P256_SHA256",
  "sig_kid": "did:device:dad-phone#2025-10-01",
  "envelope_sha256": "4f2a6b7c0d9e1f2a3b4c5d6e7f8091a2b3c4d5e6f708192a3b4c5d6e7f8091a2",
  "sig": "MEUCIQD1lF8Qvf9wG0Cjd8nYQ0BfJ4ZC2x7Lrv3N5YFhV6t9WgIgS5n4xv7QzSp6Yjpm3zDR6hccgZL4z6hA1Pd1yEi8Zv8=",
  "idem_key": "idem:7c3e8f2a9b4d6e1f3c5a7b9d2e4f6a8c",

  "_comment": "V1 TIME VALIDATION (Added by MinimalGate)",
  "ingested_at": "2025-11-10T18:00:10Z",
  "clock_skew_ms": 10000,
  "body": {
    "text": "We had dinner at Olive Garden with Mom and it was great",
    "topics": ["family", "dining", "social"],
    "sentiment": 0.8,
    "sentiment_label": "positive",
    "emotion_tags": ["joy", "contentment"],
    "categories": ["social", "meal"],
    "activity_type": "dinner",
    "activity_category": "dining",
    "location_name": "Olive Garden, Market St",
    "location_type": "restaurant",
    "location_lat": 37.7749,
    "location_lon": -122.4194,
    "participants": ["person_dad", "person_mom"],
    "event_time": "2025-11-10T18:00:00Z",
    "session_id": "session-abc123",
    "conversation_turn": 5,
    "language": "en"
  }
}
```

**Validation Results (V1):**
- ✅ Schema valid (V1 envelope.schema.json)
- ✅ **Full envelope signature valid** (sig covers headers + body)
- ✅ **envelope_sha256 matches** computed hash
- ✅ **Clock skew acceptable** (10 seconds < 10 minutes)
- ✅ **Time metadata added:** `ingested_at`, `clock_skew_ms`
- ✅ **Not duplicate** (idem_key not in ledger, envelope_sha256 not in WAL)

---

## Stage 4: Policy Evaluator (PEP)

**Location:** `k0/policy/decision.py`
**Responsibility:** Check space access, privacy band, ABAC/RBAC rules

### What Happens (V1 Enhanced):
1. **Space Resolution:** Verify actor can write to space_id
2. **Privacy Band Check:** AMBER requires redaction + location masking obligations
3. **ABAC/RBAC:** Check attribute-based and role-based policies
4. **Safety Check:** Content safety policies
5. **Policy Stamp Creation:** Attach policy_stamp to envelope (V1 NEW)

### Envelope After PEP (Policy Stamp Added) - V1:

```json
{
  "_comment": "POLICY STAMP ATTACHED - V1 propagates obligations through pipeline",
  "cognitive_trace_id": "11111111-2222-3333-4444-555555555555",
  "tenant_id": "family-smith",
  "space_id": "personal:dad",
  "topic": "memory.episodic.formation",
  "schema_uri": "https://contracts.family-ai.dev/schemas/memory.episodic.json",
  "schema_version": "1.0.0",
  "actor": "person_dad",
  "device_id": "device-dad-phone",
  "band": "AMBER",
  "policy_version": "2025-11-01",
  "ts": "2025-11-10T18:00:00Z",
  "sig_alg": "ECDSA_P256_SHA256",
  "sig_kid": "did:device:dad-phone#2025-10-01",
  "envelope_sha256": "4f2a6b7c0d9e1f2a3b4c5d6e7f8091a2b3c4d5e6f708192a3b4c5d6e7f8091a2",
  "sig": "MEUCIQD1lF8Qvf9wG0Cjd8nYQ0BfJ4ZC2x7Lrv3N5YFhV6t9WgIgS5n4xv7QzSp6Yjpm3zDR6hccgZL4z6hA1Pd1yEi8Zv8=",
  "idem_key": "idem:7c3e8f2a9b4d6e1f3c5a7b9d2e4f6a8c",
  "ingested_at": "2025-11-10T18:00:10Z",
  "clock_skew_ms": 10000,

  "_comment": "V1 POLICY STAMP (Added by PEP)",
  "policy_stamp": {
    "policy_version": "2025-11-01",
    "band": "AMBER",
    "obligations": ["mask.location.precision"],
    "visible_to": ["person_dad"],
    "decision": "ALLOW"
  },
  "body": {
    "text": "We had dinner at Olive Garden with Mom and it was great",
    "topics": ["family", "dining", "social"],
    "sentiment": 0.8,
    "sentiment_label": "positive",
    "emotion_tags": ["joy", "contentment"],
    "categories": ["social", "meal"],
    "activity_type": "dinner",
    "activity_category": "dining",
    "location_name": "Olive Garden, Market St",
    "location_type": "restaurant",
    "location_lat": 37.7749,
    "location_lon": -122.4194,
    "participants": ["person_dad", "person_mom"],
    "event_time": "2025-11-10T18:00:00Z",
    "session_id": "session-abc123",
    "conversation_turn": 5,
    "language": "en"
  }
}
```

**V1 Change: Policy Stamp Now Attached to Envelope**

**OLD (V0):** PEP created separate PolicyDecision object (could be dropped downstream)
**NEW (V1):** PEP attaches `policy_stamp` directly to envelope (guaranteed propagation)

```json
"policy_stamp": {
  "policy_version": "2025-11-01",
  "band": "AMBER",
  "obligations": ["mask.location.precision"],
  "visible_to": ["person_dad"],
  "decision": "ALLOW"
}
```

**Key Benefits:**
- ✅ Obligations cannot be dropped downstream
- ✅ All consumers read from single source of truth
- ✅ Persisted in WAL and Outbox for audit trail

---

## Stage 5: Memory Steward - Space Resolution

**Location:** `memory_steward/__init__.py` (585-line orchestrator)
**Component:** SpaceResolver
**Responsibility:** Determine WHERE memory belongs, WHO can access

### What Happens:
1. **Space Policy Lookup:** Get policy for "personal:dad"
2. **Ownership Check:** Verify person_dad owns space
3. **Visibility Computation:** Calculate visible_to list
4. **Co-owners:** Check if space has co-owners

### Envelope After Space Resolution (No Changes Yet):

```json
{
  "_comment": "ENVELOPE STILL UNCHANGED - Memory Steward tracks internally",
  "cognitive_trace_id": "11111111-2222-3333-4444-555555555555",
  "tenant_id": "family-smith",
  "space_id": "personal:dad",
  "topic": "memory.episodic.formation",
  "schema_uri": "https://contracts.family-ai.dev/schemas/memory.episodic.json",
  "schema_version": "1.0.0",
  "actor": "person_dad",
  "device_id": "device-dad-phone",
  "band": "AMBER",
  "policy_version": "2025-11-01",
  "ts": "2025-11-10T18:00:00Z",
  "sig": "MEUCIQD1lF8Qvf9wG0Cjd8nYQ0BfJ4ZC2x7Lrv3N5YFhV6t9WgIgS5n4xv7QzSp6Yjpm3zDR6hccgZL4z6hA1Pd1yEi8Zv8=",
  "payload_sha256": "4f2a6b7c0d9e1f2a3b4c5d6e7f8091a2b3c4d5e6f708192a3b4c5d6e7f8091a2",
  "idem_key": "family-smith:personal:dad:memory.episodic.formation:evt-20251110-abc123",
  "body": {
    "text": "We had dinner at Olive Garden with Mom and it was great",
    "topics": ["family", "dining", "social"],
    "sentiment": 0.8,
    "sentiment_label": "positive",
    "emotion_tags": ["joy", "contentment"],
    "categories": ["social", "meal"],
    "activity_type": "dinner",
    "activity_category": "dining",
    "location_name": "Olive Garden, Market St",
    "location_type": "restaurant",
    "location_lat": 37.7749,
    "location_lon": -122.4194,
    "participants": ["person_dad", "person_mom"],
    "event_time": "2025-11-10T18:00:00Z",
    "session_id": "session-abc123",
    "conversation_turn": 5,
    "language": "en"
  }
}
```

**Memory Steward Internal State:**
```python
{
    "space_resolution": {
        "owner_id": "person_dad",
        "visible_to": ["person_dad"],
        "co_owners": [],
        "space_type": "personal",
        "policy": "private"
    },
    "emit_event": "cognitive.memory.write.space_resolved"
}
```

---

## Stage 6: Memory Steward - PII Redaction

**Location:** `memory_steward/__init__.py`
**Component:** RedactionCoordinator
**Responsibility:** Remove sensitive data based on privacy_band

### What Happens:
1. **Check band:** AMBER = standard redaction
2. **Scan text:** Look for PII patterns (phone, email, SSN)
3. **Redact if found:** Replace with placeholders
4. **Log redactions:** Audit trail

### Envelope After Redaction (Location Masked for AMBER) - V1:

```json
{
  "_comment": "LOCATION MASKED - V1 applies mask.location.precision obligation",
  "cognitive_trace_id": "11111111-2222-3333-4444-555555555555",
  "tenant_id": "family-smith",
  "space_id": "personal:dad",
  "topic": "memory.episodic.formation",
  "schema_uri": "https://contracts.family-ai.dev/schemas/memory.episodic.json",
  "schema_version": "1.0.0",
  "actor": "person_dad",
  "device_id": "device-dad-phone",
  "band": "AMBER",
  "policy_version": "2025-11-01",
  "ts": "2025-11-10T18:00:00Z",
  "sig_alg": "ECDSA_P256_SHA256",
  "sig_kid": "did:device:dad-phone#2025-10-01",
  "envelope_sha256": "4f2a6b7c0d9e1f2a3b4c5d6e7f8091a2b3c4d5e6f708192a3b4c5d6e7f8091a2",
  "sig": "MEUCIQD1lF8Qvf9wG0Cjd8nYQ0BfJ4ZC2x7Lrv3N5YFhV6t9WgIgS5n4xv7QzSp6Yjpm3zDR6hccgZL4z6hA1Pd1yEi8Zv8=",
  "idem_key": "idem:7c3e8f2a9b4d6e1f3c5a7b9d2e4f6a8c",
  "ingested_at": "2025-11-10T18:00:10Z",
  "clock_skew_ms": 10000,
  "policy_stamp": {
    "policy_version": "2025-11-01",
    "band": "AMBER",
    "obligations": ["mask.location.precision"],
    "visible_to": ["person_dad"],
    "decision": "ALLOW"
  },
  "body": {
    "text": "We had dinner at Olive Garden with Mom and it was great",
    "topics": ["family", "dining", "social"],
    "sentiment": 0.8,
    "sentiment_label": "positive",
    "emotion_tags": ["joy", "contentment"],
    "categories": ["social", "meal"],
    "activity_type": "dinner",
    "activity_category": "dining",

    "_comment": "V1 LOCATION MASKING (Applied by RedactionCoordinator)",
    "location_name": "Olive Garden, Market St",
    "location_type": "restaurant",
    "location_geohash": "9q8yy9",
    "location_precision_m": 5000,
    "location_lat": null,
    "location_lon": null,

    "participants": ["person_dad", "person_mom"],
    "event_time": "2025-11-10T18:00:00Z",
    "session_id": "session-abc123",
    "conversation_turn": 5,
    "language": "en"
  }
}
```

**V1 Changes Applied by RedactionCoordinator:**

1. **Location Masking (AMBER band):**
   - `location_lat` 37.7749 → `null` (cleared)
   - `location_lon` -122.4194 → `null` (cleared)
   - `location_geohash` → `"9q8yy9"` (6-char precision ≈ 5km)
   - `location_precision_m` → `5000` (5km radius)

2. **PII Redaction (if found):**
   - `text` → Phone numbers replaced with `[PHONE_REDACTED]`
   - `text` → Emails replaced with `[EMAIL_REDACTED]`
   - `text` → SSNs replaced with `[SSN_REDACTED]`

**Memory Steward Internal State:**
```python
{
    "redaction_result": {
        "pii_found": False,
        "redactions": [],
        "text_modified": False,
        "location_masked": True,
        "obligations_applied": ["mask.location.precision"]
    },
    "emit_event": "cognitive.memory.write.obligations_applied"
}
```

**V1 Privacy Compliance:**
- ✅ AMBER band: 5km precision (geohash-6)
- ✅ RED band would use: 25km precision (geohash-4)
- ✅ GREEN band: No masking (exact lat/lon preserved)
- ✅ Exact coordinates: Cleared (could be stored in encrypted side table if needed)

---

## Stage 7: Hippocampus API - Pattern Separation (DG)

**Location:** `hippocampus/api.py` → `hippocampus/separator.py`
**Component:** DG (Dentate Gyrus)
**Responsibility:** Pattern separation using SimHash/MinHash

### What Happens:
1. **Tokenize text:** Create k-grams (k=3 shingles)
2. **Compute SimHash:** 512-bit binary code
3. **Compute MinHash:** 64 Jaccard sketches
4. **Novelty Score:** Compare with existing memories
5. **Near-duplicates:** Find similar events

### Input to Hippocampus:

```python
{
    "space_id": "personal:dad",
    "event_id": "evt-20251110-abc123",
    "text": "We had dinner at Olive Garden with Mom and it was great",
    "ts": "2025-11-10T18:00:00Z",
    "meta": {
        "author": "person_dad",
        "mentions": ["person_mom"],
        "topics": ["family", "dining", "social"]
    },
    "embed": True,
    "store_vectors": True
}
```

### Output from Hippocampus DG:

```python
{
    "space_id": "personal:dad",
    "event_id": "evt-20251110-abc123",
    "simhash_hex": "3a41f7e2c8b5d9a6e1f3c7b2d8a4e6f1",
    "bits": 512,
    "minhash32": [123, 456, 789, 234, 567, 890, ...],  # 64 values
    "novelty": 0.82,
    "near_duplicates": [
        ["evt-20251103-xyz789", 0.12],  # Last week's dinner
        ["evt-20251027-def456", 0.18]   # Earlier restaurant visit
    ],
    "length": 58,
    "ts": "2025-11-10T18:00:00Z"
}
```

**Key Computations:**
- SimHash: 512-bit hash for duplicate detection
- MinHash: Jaccard similarity sketches
- Novelty: 0.82 (fairly novel, not a duplicate)
- Near-duplicates: Found 2 similar past events

---

## Stage 8: Hippocampus API - Semantic Bridge (CA1)

**Location:** `hippocampus/bridge.py`
**Component:** CA1 (Bridge to cortex/semantics)
**Responsibility:** Extract entities, relations, temporal hints

### What Happens:
1. **Extract time:** Parse event_time
2. **Extract topics:** From K1 analysis
3. **Extract mentions:** Person entities
4. **Project to KG:** Create semantic triples

### Output from Hippocampus CA1:

```python
{
    "facts": [
        ["event:evt-20251110-abc123", "has_time", "2025-11-10T18:00:00Z"],
        ["event:evt-20251110-abc123", "has_topic", "family"],
        ["event:evt-20251110-abc123", "has_topic", "dining"],
        ["event:evt-20251110-abc123", "mentions", "person_mom"],
        ["event:evt-20251110-abc123", "has_location", "loc_olive_garden"],
        ["event:evt-20251110-abc123", "has_activity", "dinner"],
        ["event:evt-20251110-abc123", "has_sentiment", "positive"]
    ],
    "temporal_hints": {
        "bucket": "2025-11-10-evening"
    }
}
```

---

## Stage 9: Memory Steward - Build st_hipp_store Row

**Location:** `memory_steward/__init__.py`
**Component:** CommitManager
**Responsibility:** Combine envelope + Hippocampus output into database row

### What Happens:
1. **Generate event_id:** UUID for database
2. **Copy envelope fields:** Direct mapping
3. **Copy Hippocampus outputs:** SimHash, MinHash, novelty
4. **Compute additional fields:** Length, language, defaults
5. **Build complete row:** Ready for database

### Database Row for st_hipp_store:

```python
{
    # IDENTITY & TRACING
    "event_id": "evt-20251110-abc123",
    "cognitive_trace_id": "11111111-2222-3333-4444-555555555555",
    "hipp_version": "v1.0",

    # CONTENT (REQUIRED)
    "text": "We had dinner at Olive Garden with Mom and it was great",
    "length": 58,
    "language": "en",

    # EXTRACTED METADATA (from K1 LLM analysis)
    "topics": '["family", "dining", "social"]',  # JSON string
    "categories": '["social", "meal"]',
    "activity_type": "dinner",
    "activity_category": "dining",
    "activity_metadata": None,

    # PATTERN SEPARATION (from Hippocampus DG)
    "simhash_hex": "3a41f7e2c8b5d9a6e1f3c7b2d8a4e6f1",
    "simhash_bits": 512,
    "minhash32": '[123, 456, 789, 234, 567, 890, ...]',  # JSON string
    "novelty": 0.82,
    "near_duplicates": '[["evt-20251103-xyz789", 0.12], ["evt-20251027-def456", 0.18]]',

    # WHO (REQUIRED)
    "author_id": "person_dad",
    "author_role": None,  # Could be enriched later
    "participants": '["person_dad", "person_mom"]',  # JSON string
    "participant_roles": '{}',  # JSON string (empty for now)
    "mentions": '["person_mom"]',  # JSON string
    "mention_contexts": '{}',  # JSON string

    # V1 WHERE (Location masked for AMBER)
    "location_name": "Olive Garden, Market St",
    "location_type": "restaurant",
    "location_geohash": "9q8yy9",  # V1: Geohash for privacy
    "location_precision_m": 5000,   # V1: 5km precision
    "location_lat": None,            # V1: Cleared for AMBER
    "location_lon": None,            # V1: Cleared for AMBER

    # WHEN (REQUIRED)
    "ts": "2025-11-10T18:00:00Z",
    "temporal_reference": "present",
    "temporal_target": None,

    # SENTIMENT (from K1 LLM analysis)
    "sentiment_score": 0.8,
    "sentiment_label": "positive",
    "emotion_tags": '["joy", "contentment"]',  # JSON string

    # V1 MULTI-STORE (Async processing)
    "embedding_id": None,  # V1: Generated asynchronously
    "embedding_vector_dims": 768,
    "embedding_model": "text-embedding-ada-002",
    "embedding_generated_at": None,  # V1: Set when async worker completes
    "embedding_status": "PENDING",  # V1: NEW status tracking
    "fts_indexed": 0,
    "fts_table_name": "st_hipp_fts",
    "fts_last_indexed": None,
    "fts_status": "PENDING",  # V1: NEW status tracking

    # ACCESS CONTROL (REQUIRED)
    "tenant_id": "family-smith",
    "space_id": "personal:dad",
    "privacy_band": "AMBER",
    "owner_id": "person_dad",
    "co_owners": '[]',  # JSON string
    "visible_to": '["person_dad"]',  # JSON string

    # METADATA (REQUIRED)
    "created_at": "2025-11-10T18:00:10Z",
    "device_id": "device-dad-phone",
    "session_id": "session-abc123",

    # SYNC (CRDT)
    "crdt_vector_clock": '{"device-dad-phone": 1}',  # JSON string
    "crdt_tombstone": 0,
    "crdt_lamport": 1
}
```

**Field Sources Summary:**

| Field | Source |
|-------|--------|
| **From K1 Envelope Metadata** | cognitive_trace_id, tenant_id, space_id, actor, device_id, band, ts |
| **From K1 Body (LLM Analysis)** | topics, sentiment, emotion_tags, categories, activity_type, participants |
| **From K1 Body (GPS)** | location_name, location_type |
| **V1 Location Masking** | location_geohash, location_precision_m (lat/lon cleared for AMBER) |
| **From Hippocampus DG** | simhash_hex, simhash_bits, minhash32, novelty, near_duplicates |
| **From Hippocampus CA1** | (semantic triples stored separately in KG) |
| **From Memory Steward** | event_id, owner_id, visible_to, created_at, hipp_version |
| **Generated by K0** | crdt_vector_clock |
| **V1 Async Processing** | embedding_status, fts_status (embedding_id generated by worker) |
| **V1 Time Tracking** | ingested_at, clock_skew_ms |
| **V1 Security** | envelope_sha256 |

---

## Stage 10: UnitOfWork Transaction Commit

**Location:** `k0/uow/unit_of_work.py`
**Responsibility:** ACID transaction (all or nothing)

### What Happens:
1. **WAL Append:** Write original envelope to Write-Ahead Log
2. **st_hipp_store INSERT:** Write row to staging database
3. **Outbox INSERT:** Stage event for bus dispatch
4. **Receipt INSERT:** Generate receipt for client
5. **Commit:** SQLite transaction commit (all 4 writes atomic)

### WAL Entry:

```json
{
    "wal_id": "wal-20251110-180010-001",
    "tenant_id": "family-smith",
    "space_id": "personal:dad",
    "envelope_id": "evt-20251110-abc123",
    "content_type": "application/json",
    "encryption_scheme": "none",
    "ts": "2025-11-10T18:00:10Z",
    "payload": "<original envelope JSON>",
    "checksum": "sha256:4f2a6b7c0d9e1f2a3b4c5d6e7f8091a2..."
}
```

### Outbox Entry (V1 with Policy Stamp and Async Actions):

```json
{
    "outbox_id": "out-20251110-180010-001",
    "topic": "cognitive.memory.write.committed.v1",
    "payload": {
        "event_id": "evt-20251110-abc123",
        "envelope_sha256": "4f2a6b7c0d9e1f2a3b4c5d6e7f8091a2b3c4d5e6f708192a3b4c5d6e7f8091a2",
        "cognitive_trace_id": "11111111-2222-3333-4444-555555555555",
        "space_id": "personal:dad",
        "novelty": 0.82,
        "near_duplicates": ["evt-20251103-xyz789", "evt-20251027-def456"],

        "_comment": "V1 POLICY STAMP (Propagated to all consumers)",
        "policy_stamp": {
            "policy_version": "2025-11-01",
            "band": "AMBER",
            "obligations": ["mask.location.precision"],
            "visible_to": ["person_dad"],
            "decision": "ALLOW"
        },

        "_comment": "V1 ASYNC WORK QUEUE",
        "next_actions": [
            "embedding.enqueue",
            "fts.enqueue",
            "kg.project"
        ]
    },
    "status": "PENDING",
    "retries": 0,
    "next_attempt_ts": "2025-11-10T18:00:10Z",
    "created_at": "2025-11-10T18:00:10Z"
}
```

### Receipt Entry (V1 with Audit Fields):

```json
{
    "receipt_id": "rcpt-20251110-180010-001",
    "envelope_id": "evt-20251110-abc123",
    "cognitive_trace_id": "11111111-2222-3333-4444-555555555555",
    "tenant_id": "family-smith",
    "space_id": "personal:dad",
    "status": "ok",
    "policy_band": "AMBER",

    "_comment": "V1 AUDIT FIELDS (Enhanced for verification)",
    "envelope_sha256": "4f2a6b7c0d9e1f2a3b4c5d6e7f8091a2b3c4d5e6f708192a3b4c5d6e7f8091a2",
    "obligations_applied": ["mask.location.precision"],

    "hash": "sha256:4f2a6b7c0d9e1f2a3b4c5d6e7f8091a2...",
    "issued_at": "2025-11-10T18:00:10Z"
}
```

**V1 Receipt Enhancements:**
- ✅ `envelope_sha256` allows client to verify exact envelope received
- ✅ `obligations_applied` confirms privacy obligations were enforced
- ✅ Client can audit that AMBER band → location masking occurred

**Transaction Result:**
```
✅ WAL written
✅ st_hipp_store row inserted
✅ Outbox event staged
✅ Receipt issued
✅ COMMIT successful
```

---

## Stage 11: Working Memory Cache Update

**Location:** `working_memory/manager.py`
**Responsibility:** Update L1/L2/L3 cache hierarchy

### What Happens:
1. **L1 Cache (In-Memory):** Add to immediate context (100ms TTL)
2. **L2 Cache (Session):** Add to session-local cache (5min TTL)
3. **L3 Cache (Persistent):** Add to 24hr+ working memory

### Working Memory L1 Entry (V1 with Fixed TTL):

```python
{
    "ctx_id": "ctx-20251110-180010-001",
    "episode_id": "evt-20251110-abc123",
    "entities": ["person_mom", "Olive Garden"],
    "salience": 0.85,
    "expires_at": "2025-11-10T18:01:50Z",  # V1: 100 seconds (was 100ms BUG)
    "thread_id": "session-abc123",
    "dialog_slots": {
        "last_activity": "dinner",
        "last_location": "Olive Garden",
        "last_participants": ["person_dad", "person_mom"]
    }
}
```

**V1 Cache Levels (TTL Fixed):**
- L1: Ultra-fast (**100 seconds** - FIXED from 100ms bug) - Immediate conversation context
- L2: Session-local (5 minutes) - Recent dialogue turns
- L3: Persistent (24 hours+) - Long-term working memory

**V1 Bug Fix:**
- ❌ V0: L1 TTL = 100ms (cache thrashing, unusable)
- ✅ V1: L1 TTL = 100 seconds (proper conversation context)

---

## Final State: st_hipp_store (Queryable Immediately!)

**Location:** SQLite database `st_hipp_store` table
**Status:** ✅ **IMMEDIATELY QUERYABLE BY P01 RETRIEVAL**

### Complete Row in Database:

```sql
INSERT INTO st_hipp_store (
    event_id,
    cognitive_trace_id,
    hipp_version,
    text,
    length,
    language,
    topics,
    categories,
    activity_type,
    activity_category,
    simhash_hex,
    simhash_bits,
    minhash32,
    novelty,
    near_duplicates,
    author_id,
    participants,
    mentions,
    location_name,
    location_type,
    location_geohash,        -- V1: Masked location
    location_precision_m,     -- V1: Privacy precision
    location_lat,             -- V1: NULL for AMBER
    location_lon,             -- V1: NULL for AMBER
    ts,
    temporal_reference,
    sentiment_score,
    sentiment_label,
    emotion_tags,
    embedding_id,             -- V1: NULL (async)
    embedding_vector_dims,
    embedding_model,
    embedding_generated_at,   -- V1: NULL (async)
    embedding_status,         -- V1: PENDING
    fts_indexed,
    fts_table_name,
    fts_last_indexed,
    fts_status,               -- V1: PENDING
    tenant_id,
    space_id,
    privacy_band,
    owner_id,
    visible_to,
    created_at,
    ingested_at,              -- V1: Server timestamp
    clock_skew_ms,            -- V1: Time difference
    envelope_sha256,          -- V1: Integrity hash
    device_id,
    session_id,
    crdt_vector_clock,
    crdt_tombstone,
    crdt_lamport
) VALUES (
    'evt-20251110-abc123',
    '11111111-2222-3333-4444-555555555555',
    'v1.0',
    'We had dinner at Olive Garden with Mom and it was great',
    58,
    'en',
    '["family", "dining", "social"]',
    '["social", "meal"]',
    'dinner',
    'dining',
    '3a41f7e2c8b5d9a6e1f3c7b2d8a4e6f1',
    512,
    '[123, 456, 789, ...]',
    0.82,
    '[["evt-20251103-xyz789", 0.12]]',
    'person_dad',
    '["person_dad", "person_mom"]',
    '["person_mom"]',
    'Olive Garden, Market St',
    'restaurant',
    '9q8yy9',                 -- V1: Geohash (5km precision)
    5000,                     -- V1: 5km radius
    NULL,                     -- V1: Cleared for AMBER
    NULL,                     -- V1: Cleared for AMBER
    '2025-11-10T18:00:00Z',
    'present',
    0.8,
    'positive',
    '["joy", "contentment"]',
    NULL,                     -- V1: Generated by async worker
    768,
    'text-embedding-ada-002',
    NULL,                     -- V1: Set when worker completes
    'PENDING',                -- V1: Async status
    0,
    'st_hipp_fts',
    NULL,
    'PENDING',                -- V1: Async status
    'family-smith',
    'personal:dad',
    'AMBER',
    'person_dad',
    '["person_dad"]',
    '2025-11-10T18:00:10Z',
    '2025-11-10T18:00:10Z',   -- V1: Server time
    10000,                    -- V1: 10 second skew
    '4f2a6b7c0d9e1f2a3b4c5d6e7f8091a2b3c4d5e6f708192a3b4c5d6e7f8091a2',  -- V1: Envelope hash
    'device-dad-phone',
    'session-abc123',
    '{"device-dad-phone": 1}',
    0,
    1
);
```

**V1 SQL Changes:**
- ✅ 8 new columns added (geohash, precision, ingested_at, clock_skew_ms, envelope_sha256, embedding_status, fts_status)
- ✅ location_lat/lon now nullable (NULL for AMBER/RED bands)
- ✅ embedding_id now nullable (generated asynchronously)
- ✅ Status tracking for async processing

---

## What Happens Next (Async Background)

### Tonight at 2AM (P03 Consolidation):

```
P03 Reads st_hipp_store (yesterday's memories)
    ↓
Classifier Model → Predicts EPISODIC
    ↓
Transfer to st_epi table
    ↓
Build Knowledge Graph (CA1 semantic triples)
    ↓
Keep in st_hipp_store (7-30 days retention)
```

### Memory Remains Queryable:

```python
# User query 5 minutes later: "What did I do today?"

P01 Retrieval Service queries:
├─ st_hipp_store (recent memories) ✅ FOUND HERE
├─ st_epi (permanent episodic) ❌ Not yet (consolidates tonight)
└─ Working Memory L2 cache ✅ FOUND HERE TOO

Result: Memory is immediately accessible!
```

---

## Summary: Envelope Transformation Stages (V1)

| Stage | Component | Transformation | Key Fields Added/Changed (V1) |
|-------|-----------|----------------|-------------------------------|
| 1 | K1 Orchestrator | Forms envelope | **V1:** sig_alg, sig_kid, envelope_sha256, HMAC idem_key |
| 2 | Command Port | Validates | None (validation only) |
| 3 | MinimalGate | Validates + time tracking | **V1:** ingested_at, clock_skew_ms (verifies full envelope sig) |
| 4 | Policy Evaluator | Checks access + stamps | **V1:** policy_stamp (band, obligations, visible_to) |
| 5 | Memory Steward (Space) | Resolves space | Internal state (owner_id, visible_to) |
| 6 | Memory Steward (Obligations) | Applies obligations | **V1:** location_geohash, location_precision_m (clears lat/lon), redacts PII |
| 7 | Hippocampus DG | Pattern separation | simhash_hex, minhash32, novelty, near_duplicates |
| 8 | Hippocampus CA1 | Semantic bridge | facts (semantic triples for KG) |
| 9 | Memory Steward (Commit) | Builds database row | event_id, created_at, **V1:** embedding_status=PENDING, fts_status=PENDING |
| 10 | UnitOfWork | ACID transaction | **V1:** WAL with policy_stamp, Outbox with async actions, Receipt with audit |
| 11 | Working Memory | Cache update | **V1:** L1 TTL fixed to 100s (was 100ms) |
| FINAL | st_hipp_store | Queryable staging | **V1:** 78 fields (8 new: geohash, precision, status, time, hash) |
| ASYNC | Embedding Worker | Generate embedding | **V1:** embedding_id, embedding_status=DONE |
| ASYNC | FTS Worker | Index for search | **V1:** fts_indexed=1, fts_status=DONE |

---

## Key Insights (V1 Updates)

1. **K1 Signs Full Envelope:** V1 requires signature over ENTIRE envelope (not just body) - prevents header tampering
2. **K1 Does Heavy Lifting:** LLM analysis, GPS location BEFORE K0
3. **V1 Enforces Privacy:** AMBER/RED bands automatically mask location to geohash (5km/25km precision)
4. **Policy Obligations Propagate:** V1 attaches `policy_stamp` to envelope - guaranteed enforcement through pipeline
5. **Async Processing:** V1 moves embeddings/FTS to background workers - 150ms → 80-100ms P95 latency improvement
6. **Hippocampus Adds Hashes:** SimHash/MinHash for deduplication
7. **Memory Steward Orchestrates:** Combines all sources into database row, applies obligations
8. **Immediately Queryable:** st_hipp_store is NOT locked staging (can query while embedding_status=PENDING)
9. **Dual Storage:** Memory in BOTH st_hipp_store AND working memory cache (L1 TTL fixed to 100s)
10. **P03 Consolidates Later:** Nightly (2AM) moves to permanent tables
11. **Full Audit Trail:** V1 tracks ingested_at, clock_skew_ms, envelope_sha256, obligations_applied in receipt

---

## Version 1 Implementation Requirements

**Status:** ACCEPTED (2025-11-10)
**Reference:** See `docs/envelope_movement/v1_requirements_analysis.md` for complete analysis

### Critical Changes Required for V1 Launch

#### 1. Security Hardening (BLOCKER)

**Signature Scope:**
- Current: Only `body` is signed
- Required: Sign full canonicalized envelope
- Add fields: `sig_alg`, `sig_kid`, `envelope_sha256`
- Update: `k0/gate/minimal_gate.py`, `envelope.schema.json`

**Idempotency:**
- Current: Human-readable `idem_key`
- Required: `idem_key = HMAC(device_secret, envelope_sha256 || 60s_bucket)`
- Add: WAL lookup by `envelope_sha256` to detect replays

**Time & Replay Protection:**
- Add: Reject if `abs(now - ts) > 10 minutes`
- Add fields: `ingested_at` (server clock), `clock_skew_ms`

#### 2. Privacy Compliance (BLOCKER)

**Policy Stamp Propagation:**
- Required: Attach `policy_stamp` after PEP to envelope
- Include: `band`, `obligations[]`, `visible_to[]`, `decision`
- Persist in: WAL, Outbox, all downstream consumers

**Location Privacy (AMBER/RED):**
- Current: Raw `location_lat`, `location_lon` stored
- Required: Store `location_geohash` (5km precision for AMBER/RED)
- Add fields: `location_geohash`, `location_precision_m`
- Keep exact coordinates: Encrypted side table (if needed)

#### 3. Performance Optimization (HIGH)

**Async Embeddings/FTS:**
- Current: Blocks commit (~50ms overhead)
- Required: Move to async workers (Outbox topics)
- Add fields: `embedding_status`, `fts_status` (PENDING/DONE/FAILED)
- Target: P95 <100ms (down from 150ms)

#### 4. Data Safety (BLOCKER)

**SQLite Durability:**
```sql
PRAGMA journal_mode=WAL;
PRAGMA synchronous=FULL;
PRAGMA foreign_keys=ON;
PRAGMA temp_store=MEMORY;
PRAGMA busy_timeout=5000;
```

#### 5. Bug Fixes (HIGH)

**Working Memory TTL:**
- Current: L1 = 100ms (unusable)
- Required: L1 = 100 seconds
- Update: `working_memory/manager.py`

**Receipt Enhancement:**
- Add: `envelope_sha256`, `obligations_applied[]`
- Update: `k0/receipts/generator.py`

### Updated Architecture Flow (V1)

```
K1 → [Full Envelope Signature] → Command Port
  ↓
MinimalGate [Verify Envelope Hash + Sig]
  ↓
PEP [Attach Policy Stamp]
  ↓
Memory Steward [Apply Obligations: Location Masking, Redaction]
  ↓
Hippocampus [Pattern Separation]
  ↓
UnitOfWork [WAL + st_hipp_store + Outbox + Receipt]
  ↓
Working Memory [L1: 100s, L2: 5min, L3: 24h]
  ↓
[Async] Embedding Worker → embedding_status = DONE
[Async] FTS Worker → fts_status = DONE
```

### Schema Changes for V1

**Envelope Header (ADD):**
```json
"sig_alg": "ECDSA_P256_SHA256",
"sig_kid": "did:device:dad-phone#2025-10-01",
"envelope_sha256": "sha256:...",
"ingested_at": "2025-11-10T18:00:10Z",
"clock_skew_ms": 10000,
"policy_stamp": {
  "band": "AMBER",
  "obligations": ["mask.location.precision"],
  "visible_to": ["person_dad"]
}
```

**st_hipp_store Columns (ADD):**
```sql
-- Security
ingested_at TEXT NOT NULL,
clock_skew_ms INTEGER,
envelope_sha256 TEXT NOT NULL UNIQUE,

-- Privacy
location_geohash TEXT,
location_precision_m INTEGER,

-- Async processing
embedding_status TEXT DEFAULT 'PENDING',
fts_status TEXT DEFAULT 'PENDING'
```

### V1 Performance Targets

| Metric | V0 (Current) | V1 (Target) | Change |
|--------|-------------|-------------|--------|
| P95 Latency | 150ms | <100ms | -33% (async embeddings) |
| Security | Body-only sig | Full envelope | ✅ Hardened |
| Privacy | Raw location | Geohash (AMBER/RED) | ✅ Compliant |
| Durability | Default SQLite | WAL + FULL sync | ✅ Safe |
| Working Memory L1 | 100ms | 100s | ✅ Fixed |

### Implementation Effort

**Total:** 48-58 hours (1.5-2 weeks for one developer)

**Week 1 (Security & Privacy):** 30-40 hours
- Signature scope, idempotency, policy stamp, location masking, SQLite, time hygiene

**Week 2 (Performance & Operations):** 15-25 hours
- Async embeddings/FTS, TTL fix, receipt enhancement, basic observability

**Related Documents:**
- Full analysis: `docs/envelope_movement/v1_requirements_analysis.md`
- ADR: `docs/architecture/decisions-K0/k001-write-pipeline-v1-hardening.md`

---

**Total Write Path Latency (V0):** ~150ms P95 (Command Port → st_hipp_store)
**Total Write Path Latency (V1):** ~80-100ms P95 (with async embeddings)
**Queryable After:** Immediately (P01 can query st_hipp_store)
**Consolidated After:** Next day 2AM (P03 moves to st_epi)
**Deleted From Staging:** 7-30 days after consolidation
