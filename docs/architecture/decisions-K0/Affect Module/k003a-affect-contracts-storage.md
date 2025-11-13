---
adr_number: '0012a'
parent_adr: '0012'
affected_layers:
  - K0 Memory Kernel
  - Cognitive Services
affected_modules:
  - affect
  - modules/affect
  - contracts
authors:
  - '@K0-Architecture'
concerns:
  - architecture
  - contracts
  - storage
date_created: '2025-11-13'
date_updated: '2025-11-13'
implementation_status: ACCEPTED
status: ACCEPTED
title: 'ADR-0012a: Affect Contracts & Storage Mapping'
---

# ADR-0012a: Affect Contracts & Storage Mapping

**Status**: Accepted  
**Parent ADR**: ADR-0012 (Affect Module)  
**Date**: 2025-11-13  
**Authors**: @K0-Architecture

---

## Context

ADR-0012 defines the Affect Module for on-device valence/arousal sensing. We need to specify:

1. **JSON contracts** for affect data structures used across K0/K1
2. **Storage mapping** to existing K0 tables (specifically `st_hipp_store`)
3. **State management** for per-person×space EMA tracking

**Key Insight**: We do NOT need separate `st_affect_events` or `st_affect_state` tables because:
- Per-event affect is stored in `st_hipp_store` (6 affect columns added in migration 0013)
- Per-person×space EMA state can be computed in-memory or cached by the affect module

---

## Decision

### 1. Affect Contracts (JSON Schemas)

#### 1.1 AffectAnnotation (Per-Event)

**Purpose**: Represent affect analysis for a single memory event

**Schema**: `k0/contracts/jsonschema/affect/affect_annotation.json`

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "AffectAnnotation",
  "type": "object",
  "required": [
    "event_id",
    "space_id",
    "valence",
    "arousal",
    "tags",
    "confidence",
    "model_version",
    "ts"
  ],
  "properties": {
    "event_id": {
      "type": "string",
      "description": "Reference to st_hipp_store event_id",
      "pattern": "^evt-[0-9]{4}-[0-9]{2}-[0-9]{2}-[0-9]{5}$"
    },
    "space_id": {
      "type": "string",
      "description": "Memory space (personal:*, shared:*)",
      "pattern": "^(personal|shared):.+$"
    },
    "valence": {
      "type": "number",
      "description": "Emotional valence: -1.0 (negative) to 1.0 (positive)",
      "minimum": -1.0,
      "maximum": 1.0
    },
    "arousal": {
      "type": "number",
      "description": "Emotional arousal: 0.0 (calm) to 1.0 (excited/agitated)",
      "minimum": 0.0,
      "maximum": 1.0
    },
    "tags": {
      "type": "array",
      "description": "Semantic affect tags (urgent, toxic_light, calming, etc.)",
      "items": {
        "type": "string",
        "enum": [
          "urgent",
          "toxic_light",
          "toxic_moderate",
          "toxic_severe",
          "calming",
          "exciting",
          "distressing",
          "celebratory",
          "conflict",
          "affectionate"
        ]
      },
      "uniqueItems": true
    },
    "confidence": {
      "type": "number",
      "description": "Confidence in affect classification: 0.0 to 1.0",
      "minimum": 0.0,
      "maximum": 1.0
    },
    "model_version": {
      "type": "string",
      "description": "Affect model version (e.g., k0-affect-v1.0, tier0-v1.0)",
      "pattern": "^[a-z0-9-]+:[a-z0-9]+:[vV][0-9]+\\.[0-9]+$"
    },
    "ts": {
      "type": "string",
      "description": "ISO8601 timestamp when affect was computed",
      "format": "date-time"
    },
    "tier": {
      "type": "string",
      "description": "Classifier tier used (tier0, tier1)",
      "enum": ["tier0", "tier1"]
    },
    "sources": {
      "type": "array",
      "description": "Data sources used (text, behavior, prosody, face_au, hrv)",
      "items": {
        "type": "string",
        "enum": ["text", "behavior", "prosody", "face_au", "hrv"]
      }
    }
  }
}
```

**Example**:

```json
{
  "event_id": "evt-2025-11-13-00123",
  "space_id": "shared:household",
  "valence": 0.1,
  "arousal": 0.4,
  "tags": ["urgent"],
  "confidence": 0.72,
  "model_version": "k0-affect:tier0:v1.0",
  "ts": "2025-11-13T14:23:46.050Z",
  "tier": "tier0",
  "sources": ["text", "behavior"]
}
```

#### 1.2 AffectState (Per-Person×Space EMA)

**Purpose**: Rolling affect state for a person in a specific space

**Schema**: `k0/contracts/jsonschema/affect/affect_state.json`

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "AffectState",
  "type": "object",
  "required": [
    "person_id",
    "space_id",
    "v_ema",
    "a_ema",
    "confidence",
    "updated_at"
  ],
  "properties": {
    "person_id": {
      "type": "string",
      "description": "Neo4j :Person node ID",
      "pattern": "^person-.+$"
    },
    "space_id": {
      "type": "string",
      "description": "Memory space",
      "pattern": "^(personal|shared):.+$"
    },
    "v_ema": {
      "type": "number",
      "description": "Exponential moving average of valence",
      "minimum": -1.0,
      "maximum": 1.0
    },
    "a_ema": {
      "type": "number",
      "description": "Exponential moving average of arousal",
      "minimum": 0.0,
      "maximum": 1.0
    },
    "confidence": {
      "type": "number",
      "description": "Confidence in EMA estimates",
      "minimum": 0.0,
      "maximum": 1.0
    },
    "updated_at": {
      "type": "string",
      "description": "Last update timestamp",
      "format": "date-time"
    },
    "sample_count": {
      "type": "integer",
      "description": "Number of events contributing to EMA",
      "minimum": 0
    },
    "alpha": {
      "type": "number",
      "description": "EMA smoothing factor (0.0 to 1.0)",
      "minimum": 0.0,
      "maximum": 1.0
    },
    "v_ema_fast": {
      "type": "number",
      "description": "Fast EMA for valence (higher alpha, tracks recent changes)",
      "minimum": -1.0,
      "maximum": 1.0
    },
    "a_ema_fast": {
      "type": "number",
      "description": "Fast EMA for arousal",
      "minimum": 0.0,
      "maximum": 1.0
    }
  }
}
```

**Example**:

```json
{
  "person_id": "person-alice",
  "space_id": "shared:household",
  "v_ema": 0.15,
  "a_ema": 0.35,
  "confidence": 0.68,
  "updated_at": "2025-11-13T14:23:46.100Z",
  "sample_count": 42,
  "alpha": 0.3,
  "v_ema_fast": 0.2,
  "a_ema_fast": 0.45
}
```

#### 1.3 PolicyRecommendation

**Purpose**: Policy band recommendation based on affect analysis

**Schema**: `k0/contracts/jsonschema/affect/policy_recommendation.json`

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "PolicyRecommendation",
  "type": "object",
  "required": [
    "band",
    "reasons",
    "confidence"
  ],
  "properties": {
    "band": {
      "type": "string",
      "description": "Recommended privacy band",
      "enum": ["GREEN", "AMBER", "RED", "BLACK"]
    },
    "reasons": {
      "type": "array",
      "description": "Explainable reasons for band recommendation",
      "items": {
        "type": "object",
        "required": ["rule", "signal", "weight"],
        "properties": {
          "rule": {
            "type": "string",
            "description": "Rule ID (e.g., high_arousal_negative_valence)"
          },
          "signal": {
            "type": "string",
            "description": "Human-readable explanation"
          },
          "weight": {
            "type": "number",
            "description": "Contribution to decision (0.0 to 1.0)"
          }
        }
      }
    },
    "confidence": {
      "type": "number",
      "description": "Confidence in band recommendation",
      "minimum": 0.0,
      "maximum": 1.0
    },
    "original_band": {
      "type": "string",
      "description": "Original band before affect downshift",
      "enum": ["GREEN", "AMBER", "RED", "BLACK"]
    },
    "downshift_applied": {
      "type": "boolean",
      "description": "Whether band was downshifted due to affect"
    }
  }
}
```

**Example**:

```json
{
  "band": "AMBER",
  "reasons": [
    {
      "rule": "high_arousal_negative_valence",
      "signal": "High arousal (0.75) with negative valence (-0.6) detected",
      "weight": 0.8
    },
    {
      "rule": "toxic_light_detected",
      "signal": "Light toxicity markers in text",
      "weight": 0.4
    }
  ],
  "confidence": 0.7,
  "original_band": "GREEN",
  "downshift_applied": true
}
```

---

### 2. Storage Mapping

#### 2.1 Per-Event Affect → `st_hipp_store`

**Location**: K0 kernel table created in migration `0006_phase1_core_memory_foundation.sql`  
**Enhancement**: Migration `0013_p02_write_pipeline_enhancements.sql` adds 6 affect columns

**Mapping**:

| AffectAnnotation Field | st_hipp_store Column | Type | Notes |
|------------------------|----------------------|------|-------|
| `valence` | `affect_valence` | REAL | -1.0 to 1.0 |
| `arousal` | `affect_arousal` | REAL | 0.0 to 1.0 |
| `tags` | `affect_tags` | TEXT | JSON array |
| `confidence` | `affect_confidence` | REAL | 0.0 to 1.0 |
| `model_version` | `affect_model_version` | TEXT | Version string |
| `ts` | `affect_computed_at` | TEXT | ISO8601 timestamp |

**Index**: Partial index on `affect_valence` for affect-based queries

```sql
CREATE INDEX idx_hipp_affect_valence ON st_hipp_store(affect_valence)
  WHERE affect_valence IS NOT NULL;
```

**Query Example** (Find high-arousal memories):

```sql
SELECT event_id, text, affect_valence, affect_arousal, affect_tags
FROM st_hipp_store
WHERE tenant_id = ?
  AND space_id = ?
  AND affect_arousal > 0.7
  AND crdt_tombstone = 0
ORDER BY affect_arousal DESC, ts DESC
LIMIT 50;
```

#### 2.2 Per-Person×Space EMA → In-Memory Cache

**Storage Strategy**: NO dedicated table. EMA state is:

1. **Computed on-demand** from `st_hipp_store` affect columns
2. **Cached in-memory** by `k0/modules/affect/state.py` (LRU cache, TTL 5 minutes)
3. **Reconstructed** from recent events if cache miss

**Rationale**:
- EMA is fast to compute (running average)
- Avoids schema complexity and additional writes
- Cache invalidation is straightforward (TTL-based)
- Can always reconstruct from source of truth (`st_hipp_store`)

**Implementation**: `k0/modules/affect/state.py`

```python
from functools import lru_cache
from datetime import datetime, timedelta

class AffectStateManager:
    def __init__(self, syscalls, cache_ttl_seconds=300):
        self.syscalls = syscalls
        self.cache_ttl = cache_ttl_seconds
        self._cache = {}  # (person_id, space_id) -> (AffectState, timestamp)
    
    def get_state(self, person_id: str, space_id: str) -> AffectState:
        """Get cached or compute EMA state for person×space."""
        cache_key = (person_id, space_id)
        now = datetime.utcnow()
        
        # Check cache
        if cache_key in self._cache:
            state, cached_at = self._cache[cache_key]
            if (now - cached_at).total_seconds() < self.cache_ttl:
                return state
        
        # Cache miss or expired → compute from st_hipp_store
        state = self._compute_ema(person_id, space_id)
        self._cache[cache_key] = (state, now)
        return state
    
    def _compute_ema(self, person_id: str, space_id: str, 
                     lookback_hours: int = 72, alpha: float = 0.3) -> AffectState:
        """Compute EMA from recent events in st_hipp_store."""
        cutoff = datetime.utcnow() - timedelta(hours=lookback_hours)
        
        # Query recent events
        events = self.syscalls.query_affect_history(
            person_id=person_id,
            space_id=space_id,
            since=cutoff.isoformat(),
            limit=500
        )
        
        if not events:
            # No data → neutral baseline
            return AffectState(
                person_id=person_id,
                space_id=space_id,
                v_ema=0.0,
                a_ema=0.0,
                confidence=0.0,
                updated_at=datetime.utcnow().isoformat(),
                sample_count=0,
                alpha=alpha
            )
        
        # Compute EMA (slow and fast)
        v_ema = 0.0
        a_ema = 0.0
        v_ema_fast = 0.0
        a_ema_fast = 0.0
        
        for event in sorted(events, key=lambda e: e['affect_computed_at']):
            v = event['affect_valence']
            a = event['affect_arousal']
            c = event['affect_confidence']
            
            # Slow EMA (alpha=0.3)
            v_ema = alpha * v + (1 - alpha) * v_ema
            a_ema = alpha * a + (1 - alpha) * a_ema
            
            # Fast EMA (alpha=0.7)
            v_ema_fast = 0.7 * v + 0.3 * v_ema_fast
            a_ema_fast = 0.7 * a + 0.3 * a_ema_fast
        
        # Average confidence
        avg_confidence = sum(e['affect_confidence'] for e in events) / len(events)
        
        return AffectState(
            person_id=person_id,
            space_id=space_id,
            v_ema=v_ema,
            a_ema=a_ema,
            confidence=avg_confidence,
            updated_at=datetime.utcnow().isoformat(),
            sample_count=len(events),
            alpha=alpha,
            v_ema_fast=v_ema_fast,
            a_ema_fast=a_ema_fast
        )
```

---

### 3. Retention & Replication Rules

#### 3.1 Per-Event Affect in `st_hipp_store`

**Retention**:
- **Short-term**: 7-30 days in `st_hipp_store` (staging area)
- **Long-term**: Consolidated to 8 memory layers by P03 pipeline
- **Affect columns preserved** during consolidation

**Replication**:
- Follows existing `st_hipp_store` replication rules (CRDT-based multi-device sync)
- Affect columns included in replication payload

**Privacy**:
- Affect data scoped by `space_id` (personal:*, shared:*)
- Subject to same MLS key encryption as memory content
- No cross-space leakage

#### 3.2 Per-Person×Space EMA (In-Memory)

**Retention**:
- **Cache TTL**: 5 minutes (configurable)
- **No persistent storage** (reconstructed on-demand)

**Replication**:
- Not replicated (ephemeral cache)
- Each device computes its own EMA from local `st_hipp_store`

**Privacy**:
- Cache isolated per-device
- No network transmission of EMA state
- Cleared on app restart or user logout

---

### 4. MLS Scoping Rules

**Multi-Level Security (MLS)** applies to affect data:

1. **GREEN band**: Full affect data readable by all household members with access to space
2. **AMBER band**: Affect data readable, but location redacted (geohash)
3. **RED band**: Affect data readable, but content heavily redacted
4. **BLACK band**: Affect data suppressed (NULL values)

**Key Hierarchy**:
```
tenant_master_key
  └─ space_key (shared:household)
      └─ affect_data_key (derived from space_key)
          └─ encrypts: affect_valence, affect_arousal, affect_tags
```

**Enforcement**:
- K0 policy engine checks MLS key hierarchy before returning affect data
- Queries automatically filter based on caller's MLS clearance

---

## Consequences

### Positive

✅ **No redundant storage**: Affect data lives in `st_hipp_store` with memory events  
✅ **Simple queries**: Single table for event + affect + consolidation data  
✅ **Fast EMA**: In-memory cache with 5-minute TTL  
✅ **Consistent contracts**: JSON schemas for K0/K1 integration  
✅ **Privacy-preserving**: MLS encryption + space scoping  

### Negative

❌ **EMA reconstruction cost**: Cache miss requires query + computation  
❌ **No historical EMA**: Can't query "what was Alice's affect state 3 days ago?" without recomputing  
❌ **Cache memory**: Per-person×space state consumes RAM (mitigated by LRU + TTL)  

### Risks

- **Cache invalidation bugs**: Stale EMA if events written but cache not invalidated
- **Query performance**: Affect queries on `st_hipp_store` could be slow if not indexed

**Mitigation**:
- Partial index on `affect_valence` (already in migration 0013)
- LRU cache with bounded size (max 1000 person×space entries)
- Cache invalidation on affect write (event bus notification)

---

## Alternatives Considered

### Alternative 1: Dedicated `st_affect_events` Table

**Why rejected**: Redundant with `st_hipp_store`. Every event already has affect columns.

### Alternative 2: Persistent `st_affect_state` Table

**Why rejected**: EMA is cheap to compute on-demand. Persistent storage adds schema complexity without clear benefit.

### Alternative 3: Redis Cache for EMA

**Why rejected**: Adds dependency. In-memory LRU cache is sufficient for single-device/edge deployment.

---

## Implementation Checklist

- [x] Migration 0013 adds 6 affect columns to `st_hipp_store`
- [ ] Create JSON schema files in `k0/contracts/jsonschema/affect/`
- [ ] Implement `AffectStateManager` in `k0/modules/affect/state.py`
- [ ] Add `query_affect_history()` syscall for EMA computation
- [ ] Unit tests for EMA computation (fast/slow, confidence weighting)
- [ ] Integration tests: P02 → affect columns → EMA cache → policy band

---

## References

- **Parent ADR**: ADR-0012 (Affect Module)
- **Migration**: `k0/contracts/sql/migrations/0013_p02_write_pipeline_enhancements.sql`
- **P02 Implementation Plan**: `docs/versioning_documents/pipeline_implementation/p02_implementation_plan.md`
- **Module Location**: `k0/modules/affect/`

---

## Revision History

- 2025-11-13: Initial draft (@K0-Architecture)
