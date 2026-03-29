# Milestone 1: Schema Migration — Inline Vector + Text Columns

> **GAP Reference**: [GAP_001_CROSS_LAYER_VECTOR_LINKING.md](../architecture/gaps/GAP_001_CROSS_LAYER_VECTOR_LINKING.md)
> **Effort**: 1 day
> **Priority**: P0 (Critical)
> **Dependencies**: None
> **Status**: ✅ COMPLETE (2026-01-15)

---

## Completion Summary

All 8 issues completed on 2026-01-15:

| Issue | Status | Files |
|-------|--------|-------|
| 1.1 st_epi migration | ✅ | `0061_st_epi_inline_vectors.py` |
| 1.2 st_sem migration | ✅ | `0062_st_sem_inline_vectors.py` |
| 1.3 st_procedural migration | ✅ | `0063_st_procedural_inline_vectors.py` |
| 1.4 st_social migration | ✅ | `0064_st_social_inline_vectors.py` |
| 1.5 st_prospective migration | ✅ | `0065_st_prospective_inline_vectors.py` |
| 1.6 st_kg_dom migration | ✅ | `0066_st_kg_dom_inline_vectors.py` |
| 1.7 Update dataclasses | ✅ | 6 layer writer files updated |
| 1.8 Tests | ✅ | 3327 P03 tests pass, 283 truth writer tests pass |

**Note**: Migration revisions updated from 0055-0060 to 0061-0066 due to existing migrations.

---

## Overview

Add inline vector and text preservation columns to all 6 truth layers to enable:

1. **Text Preservation**: Copy source event texts before st_hipp_events decays (20 days)
2. **Inline Vectors**: Store embedding vectors directly in truth layers (no st_vec dependency)
3. **Model Versioning**: Track which embedding model generated each vector

---

## Epic: Add Inline Vector + Text Columns to Truth Layers

### New Columns Per Layer

| Column | Type | Purpose |
|--------|------|---------|
| `source_texts_json` | TEXT | JSON array of original source event texts |
| `embedding_text` | TEXT | Generated text used for UltraBERT embedding |
| `embedding_vector` | BYTEA | 768-dim float32 vector (3072 bytes) |
| `embedding_model` | TEXT | Model version (e.g., "ultrabert-v2.1.0") |

---

## Issues

### Issue 1.1: Create Alembic Migration for st_epi

**Priority**: P0
**Effort**: 2 hours

**Description**:
Add 4 new columns to `st_epi` table for inline vector storage and text preservation.

**Files to Touch**:

- `k0/db/alembic/versions/0055_st_epi_inline_vectors.py` (NEW)

**Schema Changes**:

```sql
ALTER TABLE st_epi ADD COLUMN source_texts_json TEXT;
ALTER TABLE st_epi ADD COLUMN embedding_text TEXT;
ALTER TABLE st_epi ADD COLUMN embedding_vector BYTEA;
ALTER TABLE st_epi ADD COLUMN embedding_model TEXT DEFAULT 'ultrabert-v2.1.0';
```

**References**:

- Base schema: [0027_st_epi.py](../../k0/db/alembic/versions/0027_st_epi.py)
- GAP Section 5.5: [Solution C: Inline Vectors](../architecture/gaps/GAP_001_CROSS_LAYER_VECTOR_LINKING.md#55-solution-c-inline-vectors-in-truth-layers--accepted)
- R7 Deep Dive §6: [Database Tables Accessed](../plans/R7_TRUTH_WRITER_DEEP_DIVE.md#6-database-tables-accessed)

**Acceptance Criteria**:

- [ ] Migration file created with revision 0055
- [ ] `down_revision` points to latest migration (0054)
- [ ] All 4 columns added with correct types
- [ ] `embedding_model` has default value
- [ ] Migration runs without errors: `alembic upgrade head`
- [ ] Rollback works: `alembic downgrade -1`

---

### Issue 1.2: Create Alembic Migration for st_sem

**Priority**: P0
**Effort**: 2 hours

**Description**:
Add 4 new columns to `st_sem` table. Note: st_sem already has `pattern_description` but it's currently NULL (see GAP Pain Point 4).

**Files to Touch**:

- `k0/db/alembic/versions/0056_st_sem_inline_vectors.py` (NEW)

**Schema Changes**:

```sql
ALTER TABLE st_sem ADD COLUMN source_texts_json TEXT;
ALTER TABLE st_sem ADD COLUMN embedding_text TEXT;
ALTER TABLE st_sem ADD COLUMN embedding_vector BYTEA;
ALTER TABLE st_sem ADD COLUMN embedding_model TEXT DEFAULT 'ultrabert-v2.1.0';
```

**References**:

- Base schema: [0028_st_sem.py](../../k0/db/alembic/versions/0028_st_sem.py)
- GAP Section 2.4: [st_sem Analysis](../architecture/gaps/GAP_001_CROSS_LAYER_VECTOR_LINKING.md#24-st_sem-0028--semantic-patterns-26-columns)
- GAP Pain Point 4: Schema columns exist but writers don't populate them

**Acceptance Criteria**:

- [ ] Migration file created with revision 0056
- [ ] `down_revision` points to 0055
- [ ] All 4 columns added
- [ ] Migration and rollback work

---

### Issue 1.3: Create Alembic Migration for st_procedural

**Priority**: P0
**Effort**: 2 hours

**Description**:
Add 4 new columns to `st_procedural` table. This table currently has NO embedding support.

**Files to Touch**:

- `k0/db/alembic/versions/0057_st_procedural_inline_vectors.py` (NEW)

**Schema Changes**:

```sql
ALTER TABLE st_procedural ADD COLUMN source_texts_json TEXT;
ALTER TABLE st_procedural ADD COLUMN embedding_text TEXT;
ALTER TABLE st_procedural ADD COLUMN embedding_vector BYTEA;
ALTER TABLE st_procedural ADD COLUMN embedding_model TEXT DEFAULT 'ultrabert-v2.1.0';
```

**References**:

- Base schema: [0029_st_procedural.py](../../k0/db/alembic/versions/0029_st_procedural.py)
- GAP Section 2.5: [st_procedural Analysis](../architecture/gaps/GAP_001_CROSS_LAYER_VECTOR_LINKING.md#25-st_procedural-0029--habits--routines-27-columns)

**Acceptance Criteria**:

- [ ] Migration file created with revision 0057
- [ ] `down_revision` points to 0056
- [ ] All 4 columns added
- [ ] Migration and rollback work

---

### Issue 1.4: Create Alembic Migration for st_social

**Priority**: P0
**Effort**: 2 hours

**Description**:
Add 4 new columns to `st_social` table. This table currently has NO embedding support and NO text content.

**Files to Touch**:

- `k0/db/alembic/versions/0058_st_social_inline_vectors.py` (NEW)

**Schema Changes**:

```sql
ALTER TABLE st_social ADD COLUMN source_texts_json TEXT;
ALTER TABLE st_social ADD COLUMN embedding_text TEXT;
ALTER TABLE st_social ADD COLUMN embedding_vector BYTEA;
ALTER TABLE st_social ADD COLUMN embedding_model TEXT DEFAULT 'ultrabert-v2.1.0';
```

**References**:

- Base schema: [0030_st_social.py](../../k0/db/alembic/versions/0030_st_social.py)
- GAP Section 2.6: [st_social Analysis](../architecture/gaps/GAP_001_CROSS_LAYER_VECTOR_LINKING.md#26-st_social-0030--relationships-27-columns)
- Recent enrichment: [0054_st_social_ultrabert_enrichment.py](../../k0/db/alembic/versions/0054_st_social_ultrabert_enrichment.py)

**Acceptance Criteria**:

- [ ] Migration file created with revision 0058
- [ ] `down_revision` points to 0057
- [ ] All 4 columns added
- [ ] Migration and rollback work

---

### Issue 1.5: Create Alembic Migration for st_prospective

**Priority**: P0
**Effort**: 2 hours

**Description**:
Add 4 new columns to `st_prospective` table. This table already has `intention_description` which can be used as embedding source.

**Files to Touch**:

- `k0/db/alembic/versions/0059_st_prospective_inline_vectors.py` (NEW)

**Schema Changes**:

```sql
ALTER TABLE st_prospective ADD COLUMN source_texts_json TEXT;
ALTER TABLE st_prospective ADD COLUMN embedding_text TEXT;
ALTER TABLE st_prospective ADD COLUMN embedding_vector BYTEA;
ALTER TABLE st_prospective ADD COLUMN embedding_model TEXT DEFAULT 'ultrabert-v2.1.0';
```

**References**:

- Base schema: [0031_st_prospective.py](../../k0/db/alembic/versions/0031_st_prospective.py)
- GAP Section 2.7: [st_prospective Analysis](../architecture/gaps/GAP_001_CROSS_LAYER_VECTOR_LINKING.md#27-st_prospective-0031--intentions--goals-23-columns)

**Acceptance Criteria**:

- [ ] Migration file created with revision 0059
- [ ] `down_revision` points to 0058
- [ ] All 4 columns added
- [ ] Migration and rollback work

---

### Issue 1.6: Create Alembic Migration for st_kg_dom

**Priority**: P0
**Effort**: 2 hours

**Description**:
Add 4 new columns to `st_kg_dom` table. This table already has `embedding_id` (disconnected) and `canonical_name`.

**Files to Touch**:

- `k0/db/alembic/versions/0060_st_kg_dom_inline_vectors.py` (NEW)

**Schema Changes**:

```sql
-- st_kg_dom already has embedding_id, add inline columns
ALTER TABLE st_kg_dom ADD COLUMN source_texts_json TEXT;
ALTER TABLE st_kg_dom ADD COLUMN embedding_text TEXT;       -- Generated entity description
ALTER TABLE st_kg_dom ADD COLUMN embedding_vector BYTEA;
ALTER TABLE st_kg_dom ADD COLUMN embedding_model TEXT DEFAULT 'ultrabert-v2.1.0';
```

**References**:

- Base schema: [0032_st_kg_dom.py](../../k0/db/alembic/versions/0032_st_kg_dom.py)
- GAP Section 2.8: [st_kg_dom Analysis](../architecture/gaps/GAP_001_CROSS_LAYER_VECTOR_LINKING.md#28-st_kg_dom-0032--kg-entities-23-columns)
- GAP Section 5.6: [Entity Graph as Cross-Layer Linking](../architecture/gaps/GAP_001_CROSS_LAYER_VECTOR_LINKING.md#56-cross-layer-linking-entity-graph-st_kg_dom)

**Acceptance Criteria**:

- [ ] Migration file created with revision 0060
- [ ] `down_revision` points to 0059
- [ ] All 4 columns added (note: embedding_id already exists)
- [ ] Migration and rollback work

---

### Issue 1.7: Update Models & Repository Classes

**Priority**: P0
**Effort**: 2 hours

**Description**:
Update dataclasses/models to include new columns so layer writers can populate them in Milestone 3.

**Files to Touch**:

- `k0/modules/consolidation/truth_writer/layers/episodic.py` — Add fields to EpisodicRecord
- `k0/modules/consolidation/truth_writer/layers/semantic.py` — Add fields to SemanticRecord
- `k0/modules/consolidation/truth_writer/layers/procedural.py` — Add fields to ProceduralRecord
- `k0/modules/consolidation/truth_writer/layers/social.py` — Add fields to SocialRecord
- `k0/modules/consolidation/truth_writer/layers/prospective.py` — Add fields to ProspectiveRecord
- `k0/modules/consolidation/truth_writer/layers/kg.py` — Add fields to KGEntityRecord

**New Fields Per Model**:

```python
@dataclass
class <Layer>Record:
    # ... existing fields ...

    # NEW: Inline vector + text fields
    source_texts_json: Optional[str] = None     # JSON array of source texts
    embedding_text: Optional[str] = None        # Text used for embedding
    embedding_vector: Optional[bytes] = None    # 768-dim as BYTEA
    embedding_model: Optional[str] = None       # Model version
```

**References**:

- R7 Deep Dive §8: [DecisionRouter & Layer Writers](../plans/R7_TRUTH_WRITER_DEEP_DIVE.md#8-decisionrouter--layer-writers)
- Layer writer module structure: `k0/modules/consolidation/truth_writer/layers/`

**Acceptance Criteria**:

- [ ] All 6 layer record dataclasses updated with 4 new fields
- [ ] Fields are Optional (nullable) for backward compatibility
- [ ] Type hints correct (bytes for vector, str for text/json)
- [ ] No breaking changes to existing code

---

### Issue 1.8: Add Unit Tests for Migration

**Priority**: P1
**Effort**: 1 hour

**Description**:
Add tests to verify migrations apply correctly and columns have expected types.

**Files to Touch**:

- `tests/k0/db/test_migrations.py` (UPDATE or NEW)

**Test Cases**:

```python
def test_st_epi_has_inline_vector_columns():
    """Verify st_epi has all 4 new columns after migration."""
    columns = get_table_columns("st_epi")
    assert "source_texts_json" in columns
    assert "embedding_text" in columns
    assert "embedding_vector" in columns
    assert "embedding_model" in columns
    assert columns["embedding_vector"]["type"] == "BYTEA"

# Repeat for all 6 tables
```

**References**:

- Existing migration tests in `tests/k0/db/`
- GAP Section 5.5: Column specifications

**Acceptance Criteria**:

- [ ] Test verifies all 6 tables have new columns
- [ ] Test verifies column types are correct
- [ ] Tests pass in CI

---

## Verification Checklist

After completing all issues:

- [ ] All 6 migrations created (0055-0060)
- [ ] `alembic upgrade head` runs successfully
- [ ] `alembic downgrade -6` reverts all changes
- [ ] All 6 layer record models updated
- [ ] Unit tests pass
- [ ] No regressions in existing P03 pipeline tests

---

## Files Created/Modified Summary

| File | Action | Issue |
|------|--------|-------|
| `k0/db/alembic/versions/0055_st_epi_inline_vectors.py` | CREATE | 1.1 |
| `k0/db/alembic/versions/0056_st_sem_inline_vectors.py` | CREATE | 1.2 |
| `k0/db/alembic/versions/0057_st_procedural_inline_vectors.py` | CREATE | 1.3 |
| `k0/db/alembic/versions/0058_st_social_inline_vectors.py` | CREATE | 1.4 |
| `k0/db/alembic/versions/0059_st_prospective_inline_vectors.py` | CREATE | 1.5 |
| `k0/db/alembic/versions/0060_st_kg_dom_inline_vectors.py` | CREATE | 1.6 |
| `k0/modules/consolidation/truth_writer/layers/episodic.py` | MODIFY | 1.7 |
| `k0/modules/consolidation/truth_writer/layers/semantic.py` | MODIFY | 1.7 |
| `k0/modules/consolidation/truth_writer/layers/procedural.py` | MODIFY | 1.7 |
| `k0/modules/consolidation/truth_writer/layers/social.py` | MODIFY | 1.7 |
| `k0/modules/consolidation/truth_writer/layers/prospective.py` | MODIFY | 1.7 |
| `k0/modules/consolidation/truth_writer/layers/kg.py` | MODIFY | 1.7 |
| `tests/k0/db/test_migrations.py` | MODIFY | 1.8 |

---

## Next Milestone

After Milestone 1 is complete, proceed to:

- **Milestone 2: SummaryGenerator Module** — Template-based text generation for all layer types
