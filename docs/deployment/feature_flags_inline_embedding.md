# Feature Flags for P02/P08 Inline Embedding Migration

This document describes feature flags for the P02/P08 inline embedding architecture migration (Epic 4.2 Issue 4.2.1).

## Overview

Feature flags allow gradual rollout of inline embedding functionality with safe fallback to legacy behavior.

## Environment Variables

### `K0_EMBEDDING_INLINE`

**Purpose**: Enable/disable inline embedding generation in P02

**Values**:
- `1` or `true` - Enable inline embedding (M22/M23 active)
- `0` or `false` - Disable inline embedding, fallback to legacy M14

**Default**: `true` (after migration complete)

**Usage**:
```bash
# Enable inline embedding (production default)
export K0_EMBEDDING_INLINE=1

# Disable for rollback (emergency fallback)
export K0_EMBEDDING_INLINE=0
```

**Impact**:
- When **enabled**: P02 uses M22 (extract_from_cache) → M23 (embedding_write) → writes to st_vec
- When **disabled**: P02 uses legacy M14 (embedding_queue_write) → writes to st_embedding_queue

---

### `K0_EMBEDDING_BACKFILL_ENABLED`

**Purpose**: Enable/disable automatic backfill of PENDING embeddings

**Values**:
- `1` or `true` - Enable automatic backfill via P08 M25
- `0` or `false` - Disable automatic backfill (manual only)

**Default**: `true`

**Usage**:
```bash
# Enable automatic backfill
export K0_EMBEDDING_BACKFILL_ENABLED=1

# Disable for controlled backfill
export K0_EMBEDDING_BACKFILL_ENABLED=0
```

---

### `K0_FAISS_INDEXING_ENABLED`

**Purpose**: Enable/disable automatic FAISS indexing

**Values**:
- `1` or `true` - Enable automatic FAISS indexing via P08 M24
- `0` or `false` - Disable automatic indexing (manual rebuild only)

**Default**: `true`

**Usage**:
```bash
# Enable automatic FAISS indexing
export K0_FAISS_INDEXING_ENABLED=1

# Disable during index rebuild
export K0_FAISS_INDEXING_ENABLED=0
```

---

## Implementation Pattern

Feature flags should be checked at pipeline entry points:

### P02 Pipeline (Stage 22 - M22 Extract from Cache)

```python
# In k0/modules/embedding/extract_from_cache.py
import os

async def run(envelope, enriched, context):
    # Check feature flag
    embedding_inline_enabled = os.getenv("K0_EMBEDDING_INLINE", "1").lower() in ("1", "true")

    if not embedding_inline_enabled:
        # Feature disabled, skip inline embedding
        return {
            "embedding": None,
            "embedding_id": None,
            "model_id": None,
            "feature_flag": "K0_EMBEDDING_INLINE=0 (disabled)",
        }

    # Feature enabled, proceed with inline embedding
    # ... rest of implementation ...
```

### P02 Pipeline (Stage 61 - M23 Embedding Write)

```python
# In k0/modules/builders/embedding_write.py
import os

async def run(envelope, enriched, context):
    # Check feature flag
    embedding_inline_enabled = os.getenv("K0_EMBEDDING_INLINE", "1").lower() in ("1", "true")

    if not embedding_inline_enabled:
        # Feature disabled, skip st_vec write
        return {"skipped": True, "reason": "K0_EMBEDDING_INLINE=0"}

    # Feature enabled, proceed with st_vec write
    # ... rest of implementation ...
```

### P08 Pipeline (M24 FAISS Indexer)

```python
# In k0/modules/embedding/faiss_indexer.py
import os

async def run(envelope, enriched, context):
    # Check feature flag
    faiss_indexing_enabled = os.getenv("K0_FAISS_INDEXING_ENABLED", "1").lower() in ("1", "true")

    if not faiss_indexing_enabled:
        # Feature disabled, skip FAISS indexing
        return {"indexed": False, "reason": "K0_FAISS_INDEXING_ENABLED=0"}

    # Feature enabled, proceed with FAISS indexing
    # ... rest of implementation ...
```

### P08 Pipeline (M25 Backfill)

```python
# In k0/modules/embedding/backfill.py
import os

async def run(envelope, enriched, context):
    # Check feature flag
    backfill_enabled = os.getenv("K0_EMBEDDING_BACKFILL_ENABLED", "1").lower() in ("1", "true")

    if not backfill_enabled:
        # Feature disabled, skip backfill
        return {"backfilled_count": 0, "reason": "K0_EMBEDDING_BACKFILL_ENABLED=0"}

    # Feature enabled, proceed with backfill
    # ... rest of implementation ...
```

---

## Rollout Strategy

### Phase 1: Initial Rollout (Epic 4.1 Complete)
```bash
# Enable inline embedding, keep legacy fallback available
K0_EMBEDDING_INLINE=1
K0_EMBEDDING_BACKFILL_ENABLED=1
K0_FAISS_INDEXING_ENABLED=1
```

**Monitoring**:
- Track embedding_status=READY vs PENDING ratio
- Monitor P08 backfill success rate
- Validate FAISS index quality

### Phase 2: Validation Period (1 week)
```bash
# Continue with inline embedding enabled
K0_EMBEDDING_INLINE=1
K0_EMBEDDING_BACKFILL_ENABLED=1
K0_FAISS_INDEXING_ENABLED=1
```

**Metrics to Monitor**:
- P02 latency (target: no regression)
- st_vec write success rate (target: >99%)
- FAISS indexing latency (target: <50ms P95)
- Backfill throughput (target: 100 events/batch <5s)

### Phase 3: Legacy Deprecation (Epic 4.2.3)
```bash
# Inline embedding stable, deprecate legacy
K0_EMBEDDING_INLINE=1
K0_EMBEDDING_BACKFILL_ENABLED=1
K0_FAISS_INDEXING_ENABLED=1
```

**Actions**:
- Add deprecation warnings to M14 (embedding_queue_write)
- Mark st_embedding_queue table as deprecated
- Remove legacy P08 v1 pipeline from active pipelines

### Phase 4: Emergency Rollback (if needed)
```bash
# Rollback to legacy behavior
K0_EMBEDDING_INLINE=0
K0_EMBEDDING_BACKFILL_ENABLED=0
K0_FAISS_INDEXING_ENABLED=0
```

**Triggers**:
- P02 latency spike >20%
- st_vec write failure rate >5%
- FAISS indexing errors >10%
- UltraBERT unavailability

---

## Configuration File Alternative

Instead of environment variables, feature flags can be managed via `k0/config/feature_flags.yaml`:

```yaml
# k0/config/feature_flags.yaml
feature_flags:
  embedding:
    inline_enabled: true
    backfill_enabled: true
    faiss_indexing_enabled: true

  # Rollout percentage (0-100)
  rollout:
    inline_embedding_percentage: 100

  # Emergency circuit breaker
  circuit_breaker:
    enabled: false
    max_consecutive_failures: 10
    cooldown_seconds: 300
```

**Advantages**:
- Centralized configuration
- Version control friendly
- Supports gradual rollout percentages
- Can include circuit breaker logic

**Disadvantages**:
- Requires config file reload mechanism
- Slower to toggle in emergency

---

## Testing

### Feature Flag Tests

Create tests to verify feature flag behavior:

```python
# tests/k0/modules/embedding/test_feature_flags.py
import os
import pytest

@pytest.mark.asyncio
async def test_inline_embedding_disabled_via_flag(mock_context):
    """Test M22 skips when K0_EMBEDDING_INLINE=0"""
    os.environ["K0_EMBEDDING_INLINE"] = "0"

    from k0.modules.embedding.extract_from_cache import run

    result = await run(envelope={}, enriched={}, context=mock_context)

    assert result["embedding"] is None
    assert "feature_flag" in result

    del os.environ["K0_EMBEDDING_INLINE"]

@pytest.mark.asyncio
async def test_faiss_indexing_disabled_via_flag(mock_context):
    """Test M24 skips when K0_FAISS_INDEXING_ENABLED=0"""
    os.environ["K0_FAISS_INDEXING_ENABLED"] = "0"

    from k0.modules.embedding.faiss_indexer import run

    result = await run(envelope={}, enriched={}, context=mock_context)

    assert result["indexed"] is False
    assert "reason" in result

    del os.environ["K0_FAISS_INDEXING_ENABLED"]
```

---

## Monitoring & Observability

### Metrics to Track

**P02 Inline Embedding**:
- `k0.p02.embedding.inline.enabled` (gauge: 0 or 1)
- `k0.p02.embedding.inline.requests` (counter)
- `k0.p02.embedding.inline.failures` (counter)
- `k0.p02.embedding.inline.latency` (histogram)

**P08 Backfill**:
- `k0.p08.backfill.enabled` (gauge: 0 or 1)
- `k0.p08.backfill.batches_processed` (counter)
- `k0.p08.backfill.embeddings_backfilled` (counter)
- `k0.p08.backfill.failures` (counter)

**P08 FAISS Indexing**:
- `k0.p08.faiss.indexing.enabled` (gauge: 0 or 1)
- `k0.p08.faiss.vectors_indexed` (counter)
- `k0.p08.faiss.indexing_failures` (counter)
- `k0.p08.faiss.indexing_latency` (histogram)

### Dashboard Panels

**Feature Flag Status Panel**:
```
K0_EMBEDDING_INLINE: [ENABLED/DISABLED]
K0_EMBEDDING_BACKFILL_ENABLED: [ENABLED/DISABLED]
K0_FAISS_INDEXING_ENABLED: [ENABLED/DISABLED]
```

**Inline Embedding Health Panel**:
```
Requests: 12,345 /hour
Failures: 12 (0.1%)
Latency P95: 45ms
Status: HEALTHY
```

---

## References

- **ADR-K003**: Inline Embedding via UltraBERT
- **Epic 4.2 Issue 4.2.1**: Feature Flag for Inline Embedding
- **P02/P08 Implementation Plan**: `docs/plans/P02_P08_inline_embedding_implementation_plan.md`
- **Migration Scripts**:
  - `k0/scripts/backfill_pending_embeddings.py`
  - `k0/scripts/rebuild_faiss_index.py`

---

## Status

**Current Status**: ⚠️ **DOCUMENTATION COMPLETE** - Implementation deferred to module code

**Next Steps**:
1. Add feature flag checks to M22, M23, M24, M25 modules
2. Create feature flag unit tests
3. Update observability to track feature flag state
4. Document rollout/rollback procedures
5. Test emergency rollback scenario
