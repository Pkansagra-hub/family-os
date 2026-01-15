# Milestone 3: R7 Writer Updates — Populate Text + Vector During Consolidation

> **GAP Reference**: [GAP_001_CROSS_LAYER_VECTOR_LINKING.md](../architecture/gaps/GAP_001_CROSS_LAYER_VECTOR_LINKING.md) Section 6
> **Effort**: 3 days
> **Priority**: P0 (Critical)
> **Dependencies**: Milestone 1 (Schema), Milestone 2 (SummaryGenerator)

---

## Overview

Update R7 Truth Writers to:

1. **Fetch source texts** from st_hipp_events BEFORE they decay (20 days)
2. **Generate embedding_text** using SummaryGenerator (Milestone 2)
3. **Create embedding_vector** using UltraBERT
4. **Single atomic INSERT** with all fields (data + texts + vector)

---

## Epic: Integrate Text + Vector Generation into R7 Writers

### Critical Timing Constraint

```
┌──────────────────────────────────────────────────────────────┐
│                    TIMING CONSTRAINT                          │
├──────────────────────────────────────────────────────────────┤
│                                                               │
│  st_hipp_events.text DECAYS in 20 days!                       │
│                                                               │
│  R7 MUST:                                                     │
│  1. Fetch source_events_json → get event_ids                  │
│  2. Query st_hipp_events for each event_id → get .text        │
│  3. Store texts in source_texts_json BEFORE decay             │
│  4. Generate embedding_text from source texts                 │
│  5. Create embedding_vector with UltraBERT                    │
│                                                               │
│  AFTER R7: Truth layer is SELF-CONTAINED                      │
│  (No dependency on st_hipp_events)                            │
│                                                               │
└──────────────────────────────────────────────────────────────┘
```

---

## Issues

### Issue 3.1: Create SourceTextFetcher Service

**Priority**: P0
**Effort**: 3 hours

**Description**:
Create a service to fetch source event texts from st_hipp_events given event IDs.

**Files to Create**:

- `k0/modules/consolidation/truth_writer/source_text_fetcher.py` (NEW)

**Code Structure**:

```python
"""
SourceTextFetcher — GAP-001 Implementation

Fetches source event texts from st_hipp_events before decay.
Used by R7 writers to populate source_texts_json.

GAP Reference: GAP_001 Section 1.1 (Text Preservation)
"""

from typing import Dict, List, Optional
from dataclasses import dataclass

@dataclass
class FetchedSourceTexts:
    """Result of fetching source texts."""
    texts: List[str]                    # Ordered list of texts
    event_ids: List[str]                # Corresponding event IDs
    missing_count: int                  # Events not found (already decayed)
    texts_json: str                     # Pre-serialized JSON array


class SourceTextFetcher:
    """Fetches source texts from st_hipp_events."""

    async def fetch_for_events(
        self,
        event_ids: List[str],
        conn,  # asyncpg connection
    ) -> FetchedSourceTexts:
        """
        Fetch texts for given event IDs.

        Args:
            event_ids: List of st_hipp_events.event_id values
            conn: Database connection

        Returns:
            FetchedSourceTexts with texts and metadata
        """
        if not event_ids:
            return FetchedSourceTexts([], [], 0, "[]")

        rows = await conn.fetch(
            """
            SELECT event_id, text
            FROM st_hipp_events
            WHERE event_id = ANY($1)
              AND text IS NOT NULL
              AND archival_status IS NULL
            ORDER BY created_at ASC
            """,
            event_ids,
        )

        texts = [row["text"] for row in rows]
        found_ids = [row["event_id"] for row in rows]
        missing = len(event_ids) - len(found_ids)

        return FetchedSourceTexts(
            texts=texts,
            event_ids=found_ids,
            missing_count=missing,
            texts_json=json.dumps(texts),
        )
```

**References**:

- GAP Section 1.1: [The Solution: Copy Source Texts Before Decay](../architecture/gaps/GAP_001_CROSS_LAYER_VECTOR_LINKING.md#11-the-solution-copy-source-texts-before-decay)
- R0 Deep Dive §4: [Step 2: FETCH ELIGIBLE EVENTS](../pipelines/R0_BATCH_SELECTOR_DEEP_DIVE.md#4-step-by-step-execution-flow)
- Schema: [0022_st_hipp_events.py](../../k0/db/alembic/versions/0022_st_hipp_events.py)

**Acceptance Criteria**:

- [ ] Fetches texts for list of event_ids
- [ ] Handles missing events gracefully (already decayed)
- [ ] Returns pre-serialized JSON for storage
- [ ] Preserves temporal order
- [ ] Unit tests

---

### Issue 3.2: Create EmbeddingGenerator Service

**Priority**: P0
**Effort**: 3 hours

**Description**:
Create a service that wraps UltraBERT to generate embeddings from text.

**Files to Create**:

- `k0/modules/consolidation/truth_writer/embedding_generator.py` (NEW)

**Code Structure**:

```python
"""
EmbeddingGenerator — GAP-001 Implementation

Generates 768-dim embeddings using UltraBERT.
Returns BYTEA-compatible bytes for inline storage.

GAP Reference: GAP_001 Section 5.5 (Inline Vectors)
"""

from typing import Optional
from dataclasses import dataclass
import numpy as np


@dataclass
class GeneratedEmbedding:
    """Result of embedding generation."""
    vector_bytes: bytes              # 768 × 4 = 3072 bytes (float32)
    model_id: str                    # "ultrabert-v2.1.0"
    dimension: int                   # 768


class EmbeddingGenerator:
    """Generates embeddings using UltraBERT."""

    MODEL_ID = "ultrabert-v2.1.0"
    DIMENSION = 768

    def __init__(self, ultrabert_client=None):
        """
        Initialize with UltraBERT client.

        Args:
            ultrabert_client: Optional pre-configured client
        """
        self._client = ultrabert_client

    async def generate(self, text: str) -> Optional[GeneratedEmbedding]:
        """
        Generate embedding for text.

        Args:
            text: Text to embed (max ~512 tokens for BERT)

        Returns:
            GeneratedEmbedding with vector bytes, or None on failure
        """
        if not text or not text.strip():
            return None

        # Truncate if too long (BERT max ~512 tokens)
        if len(text) > 2000:
            text = text[:2000]

        # Call UltraBERT
        vector = await self._client.embed(text)  # Returns np.ndarray

        # Convert to bytes
        vector_bytes = vector.astype(np.float32).tobytes()

        return GeneratedEmbedding(
            vector_bytes=vector_bytes,
            model_id=self.MODEL_ID,
            dimension=self.DIMENSION,
        )

    def vector_to_bytes(self, vector: np.ndarray) -> bytes:
        """Convert numpy array to BYTEA-compatible bytes."""
        return vector.astype(np.float32).tobytes()

    def bytes_to_vector(self, data: bytes) -> np.ndarray:
        """Convert BYTEA bytes back to numpy array."""
        return np.frombuffer(data, dtype=np.float32)
```

**References**:

- GAP Section 5.5: [Inline Vectors in Truth Layers](../architecture/gaps/GAP_001_CROSS_LAYER_VECTOR_LINKING.md#55-solution-c-inline-vectors-in-truth-layers--accepted)
- GAP Section 3: [Embedding Model Analysis](../architecture/gaps/GAP_001_CROSS_LAYER_VECTOR_LINKING.md#3-embedding-model-analysis) - UltraBERT 768-dim
- Existing: `k0/modules/embedding/ultrabert_client.py` (if exists)

**Acceptance Criteria**:

- [ ] Wraps UltraBERT client
- [ ] Returns bytes for BYTEA storage
- [ ] Handles empty/None text
- [ ] Truncates long text appropriately
- [ ] Unit tests with mock client

---

### Issue 3.3: Create R7 Text+Vector Coordinator

**Priority**: P0
**Effort**: 3 hours

**Description**:
Create a coordinator that orchestrates source text fetching, text generation, and embedding creation.

**Files to Create**:

- `k0/modules/consolidation/truth_writer/text_vector_coordinator.py` (NEW)

**Code Structure**:

```python
"""
TextVectorCoordinator — GAP-001 Implementation

Coordinates the full flow:
1. Fetch source texts from st_hipp_events
2. Generate embedding_text using layer-specific generator
3. Create embedding_vector using UltraBERT

Called by each layer writer during INSERT.
"""

from dataclasses import dataclass
from typing import Dict, Any, List, Optional

from k0.modules.consolidation.algorithms.text_generators import get_generator
from .source_text_fetcher import SourceTextFetcher
from .embedding_generator import EmbeddingGenerator


@dataclass
class TextVectorResult:
    """Result of text + vector generation."""
    source_texts_json: str           # JSON array of source texts
    embedding_text: str              # Generated text for embedding
    embedding_vector: Optional[bytes]  # 768-dim as bytes
    embedding_model: str             # Model version


class TextVectorCoordinator:
    """Coordinates text fetching, generation, and embedding."""

    def __init__(
        self,
        text_fetcher: SourceTextFetcher,
        embedding_gen: EmbeddingGenerator,
    ):
        self._fetcher = text_fetcher
        self._embedder = embedding_gen

    async def process(
        self,
        layer: str,
        record_data: Dict[str, Any],
        source_event_ids: List[str],
        conn,
    ) -> TextVectorResult:
        """
        Full flow: fetch → generate text → create embedding.

        Args:
            layer: Target layer (st_epi, st_sem, etc.)
            record_data: Record fields for template generation
            source_event_ids: Event IDs to fetch texts from
            conn: Database connection

        Returns:
            TextVectorResult with all generated fields
        """
        # 1. Fetch source texts
        fetched = await self._fetcher.fetch_for_events(source_event_ids, conn)

        # 2. Get layer-specific generator
        generator = get_generator(layer)

        # 3. Generate embedding text
        generated = generator.generate(record_data, fetched.texts)

        # 4. Create embedding vector
        embedding = await self._embedder.generate(generated.embedding_text)

        return TextVectorResult(
            source_texts_json=fetched.texts_json,
            embedding_text=generated.embedding_text,
            embedding_vector=embedding.vector_bytes if embedding else None,
            embedding_model=embedding.model_id if embedding else None,
        )
```

**References**:

- GAP Section 6: [Recommended Architecture](../architecture/gaps/GAP_001_CROSS_LAYER_VECTOR_LINKING.md#6-recommended-architecture-inline-vectors--entity-graph)
- R7 Deep Dive §4: [Step-by-Step Execution Flow](../pipelines/R7_TRUTH_WRITER_DEEP_DIVE.md#4-step-by-step-execution-flow)

**Acceptance Criteria**:

- [ ] Coordinates all three components
- [ ] Returns complete TextVectorResult
- [ ] Handles empty source events
- [ ] Handles embedding failures gracefully
- [ ] Unit tests with mocks

---

### Issue 3.4: Update EpisodicLayerWriter

**Priority**: P0
**Effort**: 3 hours

**Description**:
Update `EpisodicLayerWriter` to include new fields in INSERT.

**Files to Modify**:

- `k0/modules/consolidation/truth_writer/layers/episodic.py` (MODIFY)

**Changes Required**:

1. Add `TextVectorCoordinator` dependency
2. Call coordinator in `_insert()` method
3. Include new columns in INSERT SQL
4. Handle case where embedding fails

**Updated INSERT SQL**:

```python
async def _insert(self, uow: UnitOfWork, write: StagedWrite) -> None:
    data = write.record_data
    now = _now_ms()

    # NEW: Get source event IDs and generate text + vector
    source_event_ids = json.loads(data.get("source_events_json", "[]"))
    tv_result = await self._coordinator.process(
        layer=self.LAYER,
        record_data=data,
        source_event_ids=source_event_ids,
        conn=uow.connection,
    )

    await uow.connection.execute(
        """
        INSERT INTO st_epi (
            episode_id, tenant_id, space_id, cluster_id,
            source_events_json, started_at, ended_at,
            temporal_spread_ms, confidence, observation_count,
            created_at, version,
            -- NEW COLUMNS:
            source_texts_json, embedding_text, embedding_vector, embedding_model
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, 1, $12, $13, $14, $15)
        ON CONFLICT (episode_id) DO NOTHING
        """,
        data["episode_id"],
        data["tenant_id"],
        data["space_id"],
        data.get("cluster_id"),
        data.get("source_events_json", "[]"),
        data.get("started_at", now),
        data.get("ended_at", now),
        data.get("temporal_spread_ms", 0),
        data.get("confidence", 1.0),
        data.get("observation_count", 1),
        data.get("created_at", now),
        # NEW COLUMNS:
        tv_result.source_texts_json,
        tv_result.embedding_text,
        tv_result.embedding_vector,
        tv_result.embedding_model,
    )
```

**References**:

- Current implementation: [episodic.py](../../k0/modules/consolidation/truth_writer/layers/episodic.py)
- R7 Deep Dive §8: [EpisodicLayerWriter](../pipelines/R7_TRUTH_WRITER_DEEP_DIVE.md#layer-writers)
- Schema: [0027_st_epi.py](../../k0/db/alembic/versions/0027_st_epi.py)

**Acceptance Criteria**:

- [ ] INSERT includes 4 new columns
- [ ] Coordinator called before insert
- [ ] Handles missing source events
- [ ] Handles embedding failure
- [ ] Integration test passes

---

### Issue 3.5: Update SemanticLayerWriter

**Priority**: P0
**Effort**: 3 hours

**Description**:
Update `SemanticLayerWriter` to include new fields in INSERT.

**Files to Modify**:

- `k0/modules/consolidation/truth_writer/layers/semantic.py` (MODIFY)

**Changes Required**:

1. Add coordinator dependency
2. Update `_insert()` to include new columns
3. For patterns, source_events come from `source_episodes_json` → need to resolve to event IDs

**Important Note**:
st_sem uses `source_episodes_json` (episode IDs, not event IDs). Need to:

1. Get episode IDs from `source_episodes_json`
2. Look up `st_epi.source_events_json` for each episode
3. Flatten to get original event IDs
4. Then fetch texts

**References**:

- Current implementation: [semantic.py](../../k0/modules/consolidation/truth_writer/layers/semantic.py)
- Schema: [0028_st_sem.py](../../k0/db/alembic/versions/0028_st_sem.py)

**Acceptance Criteria**:

- [ ] Resolves episode IDs → event IDs
- [ ] INSERT includes 4 new columns
- [ ] Pattern-type-specific text generation works
- [ ] Integration test passes

---

### Issue 3.6: Update ProceduralLayerWriter

**Priority**: P0
**Effort**: 2 hours

**Description**:
Update `ProceduralLayerWriter` to include new fields.

**Files to Modify**:

- `k0/modules/consolidation/truth_writer/layers/procedural.py` (MODIFY)

**References**:

- Schema: [0029_st_procedural.py](../../k0/db/alembic/versions/0029_st_procedural.py)

**Acceptance Criteria**:

- [ ] INSERT includes 4 new columns
- [ ] Uses action_sequence_json for text generation
- [ ] Integration test passes

---

### Issue 3.7: Update SocialLayerWriter

**Priority**: P0
**Effort**: 2 hours

**Description**:
Update `SocialLayerWriter` to include new fields.

**Files to Modify**:

- `k0/modules/consolidation/truth_writer/layers/social.py` (MODIFY)

**Special Consideration**:
Social layer has `source_episodes_json` but also needs entity names resolved from `st_kg_dom`.

**References**:

- Schema: [0030_st_social.py](../../k0/db/alembic/versions/0030_st_social.py)

**Acceptance Criteria**:

- [ ] INSERT includes 4 new columns
- [ ] Entity names resolved for text generation
- [ ] Integration test passes

---

### Issue 3.8: Update ProspectiveLayerWriter

**Priority**: P0
**Effort**: 2 hours

**Description**:
Update `ProspectiveLayerWriter` to include new fields.

**Files to Modify**:

- `k0/modules/consolidation/truth_writer/layers/prospective.py` (MODIFY)

**Note**: This layer already has `intention_description` which is the main text.

**References**:

- Schema: [0031_st_prospective.py](../../k0/db/alembic/versions/0031_st_prospective.py)

**Acceptance Criteria**:

- [ ] INSERT includes 4 new columns
- [ ] Uses intention_description as primary text
- [ ] Integration test passes

---

### Issue 3.9: Update KGLayerWriter

**Priority**: P0
**Effort**: 2 hours

**Description**:
Update `KGLayerWriter` to include new fields for st_kg_dom.

**Files to Modify**:

- `k0/modules/consolidation/truth_writer/layers/kg.py` (MODIFY)

**Note**: st_kg_edges does NOT get embedding (uses TransE-style graph embeddings, future work).

**References**:

- Schema: [0032_st_kg_dom.py](../../k0/db/alembic/versions/0032_st_kg_dom.py)
- GAP Section 3.3: [Multi-Model Strategy](../architecture/gaps/GAP_001_CROSS_LAYER_VECTOR_LINKING.md#33-recommended-multi-model-strategy) - Graph-aware models for KG

**Acceptance Criteria**:

- [ ] st_kg_dom INSERT includes 4 new columns
- [ ] st_kg_edges unchanged (no inline vectors)
- [ ] Entity description generated from attributes
- [ ] Integration test passes

---

### Issue 3.10: Update TruthWriteAssembler

**Priority**: P0
**Effort**: 2 hours

**Description**:
Update `TruthWriteAssembler` to pass source event IDs to layer writers.

**Files to Modify**:

- `k0/modules/consolidation/staging/truth_write_assembler.py` (MODIFY)

**Changes Required**:

1. Ensure `source_events_json` is properly passed in record_data
2. For st_sem, ensure `source_episodes_json` is included
3. Add helper to resolve episode_ids → event_ids if needed

**References**:

- Current implementation: [truth_write_assembler.py](../../k0/modules/consolidation/staging/truth_write_assembler.py)

**Acceptance Criteria**:

- [ ] source_events_json passed for all layers
- [ ] Episode-to-event resolution helper created
- [ ] Existing tests still pass

---

### Issue 3.11: Update R7 Phase to Initialize Coordinator

**Priority**: P0
**Effort**: 2 hours

**Description**:
Update R7 phase entry point to initialize and inject the TextVectorCoordinator.

**Files to Modify**:

- `k0/pipelines/p03/phases/r7_truth_writer.py` (MODIFY)

**Changes Required**:

1. Create TextVectorCoordinator at phase start
2. Inject into all layer writers
3. Handle coordinator initialization failure

**References**:

- R7 Deep Dive §4: [Step-by-Step Execution Flow](../pipelines/R7_TRUTH_WRITER_DEEP_DIVE.md#4-step-by-step-execution-flow)

**Acceptance Criteria**:

- [ ] Coordinator created and injected
- [ ] All writers receive coordinator
- [ ] Pipeline runs end-to-end

---

### Issue 3.12: Integration Tests

**Priority**: P1
**Effort**: 4 hours

**Description**:
Create integration tests for the full R7 flow with text + vector generation.

**Files to Create**:

- `tests/k0/pipelines/p03/phases/test_r7_text_vector_integration.py` (NEW)

**Test Cases**:

1. Episode INSERT with source texts → verify source_texts_json populated
2. Episode INSERT with embedding → verify embedding_vector is 3072 bytes
3. Pattern INSERT with type-specific text → verify embedding_text format
4. Missing source events (already decayed) → verify graceful handling
5. UltraBERT failure → verify record created without vector
6. Full R0-R8 run with new columns

**References**:

- Existing tests: `tests/k0/modules/consolidation/staging/test_r6_integration.py`

**Acceptance Criteria**:

- [ ] All test cases pass
- [ ] Tests run in <30s
- [ ] No regressions in existing tests

---

## Dependency Graph

```
┌──────────────────────────────────────────────────────────────┐
│                    ISSUE DEPENDENCIES                         │
├──────────────────────────────────────────────────────────────┤
│                                                               │
│  3.1 SourceTextFetcher ──┐                                    │
│                          ├──▶ 3.3 TextVectorCoordinator       │
│  3.2 EmbeddingGenerator ─┘              │                     │
│                                         │                     │
│  Milestone 2 (Generators) ──────────────┘                     │
│                                         │                     │
│                                         ▼                     │
│              ┌──────────────────────────────────────┐         │
│              │     3.4  3.5  3.6  3.7  3.8  3.9     │         │
│              │  Layer Writers (parallel updates)    │         │
│              └──────────────────────────────────────┘         │
│                                         │                     │
│                                         ▼                     │
│                    3.10 TruthWriteAssembler                   │
│                                         │                     │
│                                         ▼                     │
│                    3.11 R7 Phase Integration                  │
│                                         │                     │
│                                         ▼                     │
│                    3.12 Integration Tests                     │
│                                                               │
└──────────────────────────────────────────────────────────────┘
```

---

## Verification Checklist

After completing all issues:

- [ ] All 6 layer writers updated
- [ ] TextVectorCoordinator functional
- [ ] Source texts fetched before decay window
- [ ] Embeddings generated inline
- [ ] Single atomic INSERT per record
- [ ] Full P03 pipeline runs successfully
- [ ] All tests pass (unit + integration)
- [ ] No performance regression (target: <50ms per record)

---

## Files Modified/Created Summary

| File | Action | Issue |
|------|--------|-------|
| `k0/modules/consolidation/truth_writer/source_text_fetcher.py` | CREATE | 3.1 |
| `k0/modules/consolidation/truth_writer/embedding_generator.py` | CREATE | 3.2 |
| `k0/modules/consolidation/truth_writer/text_vector_coordinator.py` | CREATE | 3.3 |
| `k0/modules/consolidation/truth_writer/layers/episodic.py` | MODIFY | 3.4 |
| `k0/modules/consolidation/truth_writer/layers/semantic.py` | MODIFY | 3.5 |
| `k0/modules/consolidation/truth_writer/layers/procedural.py` | MODIFY | 3.6 |
| `k0/modules/consolidation/truth_writer/layers/social.py` | MODIFY | 3.7 |
| `k0/modules/consolidation/truth_writer/layers/prospective.py` | MODIFY | 3.8 |
| `k0/modules/consolidation/truth_writer/layers/kg.py` | MODIFY | 3.9 |
| `k0/modules/consolidation/staging/truth_write_assembler.py` | MODIFY | 3.10 |
| `k0/pipelines/p03/phases/r7_truth_writer.py` | MODIFY | 3.11 |
| `tests/.../test_r7_text_vector_integration.py` | CREATE | 3.12 |

---

## Related Milestones

**Downstream Dependencies:**

- **Milestone 4: P08 FAISS Union Index** — Build unified index from all 6 truth layers
- **Milestone 7: Intent-Aware Prospective Writer** — Uses SourceTextFetcher (Issue 3.1) for reminder flows

> **Note**: Milestone 7 extends ProspectiveLayerWriter (Issue 3.8) with intent-based routing.
> When implementing Issue 3.8, ensure the `write_reminder()` extension point is considered.
> See [GAP_001_MILESTONE_7_INTENT_PROSPECTIVE_WRITER.md](GAP_001_MILESTONE_7_INTENT_PROSPECTIVE_WRITER.md).
