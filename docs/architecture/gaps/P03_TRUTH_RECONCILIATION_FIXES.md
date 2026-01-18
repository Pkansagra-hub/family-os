# P03 Truth Reconciliation Fixes

**Status**: Ready for Implementation
**Created**: 2025-01-16
**Updated**: 2025-01-17
**Phase Ordering**: R0 → R1 → R2 → R3 → R4 → R5 → R6 → R7 → R8 (IMMUTABLE)

---

## Executive Summary

P03's "truth-first" philosophy requires phases to query existing memory layers before creating new entries. This document addresses **8 critical issues** with practical fixes that respect the immutable phase ordering.

### Core Principles (Civilizational Scale)

| Principle | Implication |
|-----------|-------------|
| **Every Memory is Time-Bound** | No temporal expression without anchor resolution |
| **Confidence-Driven Disambiguation** | Low confidence → GAP → Human resolution → Learning |
| **Incremental Memory Formation** | Events → Episodes → Patterns → Routines (temporally aligned) |
| **Holistic Life View** | Cross-day, cross-month, cross-year pattern extraction |

### The Three Foundational Gaps

| Gap | Problem | Solution |
|-----|---------|----------|
| **Temporal Grounding** | "next week" has no meaning without anchor time | P02 resolves relative → absolute using `event_ts` |
| **Entity Disambiguation** | 100 Jeels in life, which one? | Confidence routing: HIGH→auto, MEDIUM→GAP, LOW→create |
| **Incremental Episodes** | Lunch today vs lunch patterns over year | Temporal alignment enables life pattern queries |

---

## Issue 1: R1 Novelty Component Always Zero

**Severity**: HIGH (25% of importance formula is dead)

**Root Cause**:

- R1 importance formula expects `novelty_score` as input
- But `novelty_score` is computed by R3 (runs AFTER R1)
- P03EventState has no `novelty_score` field
- Result: `getattr(event, "novelty_score", 0.0)` always returns 0.0

**Code Location**: `k0/modules/consolidation/algorithms/importance_scorer.py` line 617

```python
# Current (broken):
novelty_score = getattr(event, "novelty_score", 0.0) or 0.0
```

**Fix Option A - Use P02's salience_score (RECOMMENDED)**:

The dossier Section 6.2.1 says R1 should use `salience_score`, not `novelty_score`. P02 already computes `salience_score` (0.50×social + 0.40×affect + 0.10×recency).

```python
# Fixed:
# P02's salience_score serves as a proxy for "interestingness"
# which is what novelty was trying to capture
salience_proxy = getattr(event, "salience_score", 0.0) or 0.0
```

**Fix Option B - Set novelty_weight to zero**:

If novelty should only be computed in R3 (per dossier Section 6.2.1), remove it from R1:

```python
# In importance weights config:
novelty_weight = 0.0  # Novelty handled by R3, not R1

# Redistribute weight to other components:
# emotional_weight: 0.25 → 0.35
# affect_weight: 0.30 → 0.35
# social_weight: 0.20 → 0.30
```

**Files to Change**:

- `k0/modules/consolidation/algorithms/importance_scorer.py`
- `k0/pipelines/p03/phases/r1_importance_scorer.py`

---

## Issue 2: R2 Creates Duplicate Episodes

**Severity**: MEDIUM

**Root Cause**:

- R2 clusters events using DBSCAN on embeddings
- Does NOT query st_epi for existing episodes first
- Creates new episode clusters even when similar episodes exist

**Code Location**: `k0/pipelines/p03/phases/r2_episode_clusterer.py`

**Fix - Query st_epi Before Clustering**:

Before running DBSCAN, query st_epi for existing episodes that overlap with the current batch's time window and embedding similarity.

```python
async def run(self, envelope: P03Envelope) -> P03Envelope:
    events = envelope.phases.r1_scored_events

    # NEW: Query existing episodes for this time window
    existing_episodes = await self._query_existing_episodes(
        space_id=envelope.space_id,
        time_start=min(e.event_time_utc for e in events),
        time_end=max(e.event_time_utc for e in events),
        embedding_ids=[e.embedding_id for e in events]
    )

    # NEW: For each event, check if it matches existing episode
    for event in events:
        match = await self._find_matching_episode(event, existing_episodes)
        if match and match.similarity > 0.85:
            # REINFORCE existing episode instead of clustering
            event.episode_cluster_id = match.episode_id
            event.reconciliation_decision = "REINFORCE"
        else:
            # Proceed to DBSCAN clustering for novel events
            pass

    # Run DBSCAN only on events without existing episode match
    novel_events = [e for e in events if not e.episode_cluster_id]
    clusters = self._run_dbscan(novel_events)
    # ...
```

**Files to Change**:

- `k0/pipelines/p03/phases/r2_episode_clusterer.py`
- `k0/pipelines/p03/event_state.py` (add reconciliation_decision field)

---

## Issue 3: R4 Entities Always CREATE, Never UPDATE

**Severity**: HIGH (causes "PANDA IS MY WIFE" x7)

**Root Cause**:

- R4 entity processing assumes all entities are new
- Comment in code: "For now, assume all are new"
- Does NOT query st_kg_dom for existing entities
- Contrast: Edge processing correctly queries existing edges

**Code Location**: `k0/pipelines/p03/phases/r4_kg_consolidator.py` lines 1478-1520

**Fix - Query st_kg_dom Before Creating Entities**:

```python
async def _process_entity(
    self,
    entity: ExtractedEntity,
    envelope: P03Envelope
) -> EntityResult:
    """Process entity with truth-first reconciliation."""

    # NEW: Query existing entity by canonical name
    existing = await self._query_existing_entity(
        space_id=envelope.space_id,
        entity_name=entity.canonical_name,
        entity_type=entity.entity_type
    )

    if existing:
        similarity = await self._compute_entity_similarity(entity, existing)

        if similarity > 0.90:
            # REINFORCE: Same entity, boost confidence
            return EntityResult(
                decision="REINFORCE",
                entity_id=existing.entity_id,
                updates={
                    "observation_count": existing.observation_count + 1,
                    "confidence": min(0.99, existing.confidence + 0.01),
                    "last_observed_at": envelope.cycle_start_time
                }
            )
        elif similarity > 0.70:
            # EXTEND: Add new attributes to existing entity
            return EntityResult(
                decision="EXTEND",
                entity_id=existing.entity_id,
                extensions=self._extract_new_attributes(entity, existing)
            )
        else:
            # Different entity with similar name - disambiguate
            return EntityResult(
                decision="CREATE",
                entity=entity,
                canonical_name=f"{entity.canonical_name}_{entity.context_hash[:8]}"
            )
    else:
        # Truly new entity
        return EntityResult(
            decision="CREATE",
            entity=entity
        )
```

**Files to Change**:

- `k0/pipelines/p03/phases/r4_kg_consolidator.py`

---

## Issue 4: Weight Learning Lacks Batch Protection

**Severity**: MEDIUM

**Root Cause**:

- `ImportanceWeightLearner.train_step()` updates weights without checking batch size
- A small noisy batch can corrupt weights calibrated over thousands of samples
- Only protection: rollback after 3 consecutive loss increases (too late)

**Code Location**: `k0/modules/consolidation/algorithms/importance_weight_learner.py`

**Fix - Add Batch Protection**:

```python
def train_step(self, batch: TrainingBatch) -> TrainingResult:
    """Training step with batch protection."""

    # Protection 1: Minimum batch size
    if len(batch) < 50:
        return TrainingResult(
            skipped=True,
            reason="BATCH_TOO_SMALL",
            weights=self.get_weights()
        )

    # Protection 2: Sample ratio check
    if self.sample_count > 500:
        ratio = len(batch) / self.sample_count
        if ratio < 0.05:
            # Small batch relative to existing - reduce learning rate
            effective_lr = self.learning_rate * ratio * 10
        else:
            effective_lr = self.learning_rate
    else:
        effective_lr = self.learning_rate

    # Protection 3: Snapshot for potential rollback
    weights_snapshot = self.get_weights().copy()

    # Proceed with gradient descent using effective_lr
    # ...

    # Protection 4: Check for excessive drift
    drift = self._compute_drift(weights_snapshot, self.get_weights())
    if drift > 0.15:  # >15% change is suspicious
        self.logger.warning(f"Weight drift {drift:.2%} exceeds threshold")
        # Emit alert but don't block (monitoring will catch systemic issues)

    return TrainingResult(
        skipped=False,
        weights=self.get_weights(),
        drift=drift
    )
```

**Files to Change**:

- `k0/modules/consolidation/algorithms/importance_weight_learner.py`

---

## Issue 5: R5 Outputs Not Deduplicated (LOW PRIORITY)

**Severity**: LOW

**Root Cause**:

- R5 correctly queries accumulated KG for exploration inputs
- But does NOT check if generated insights/routines already exist
- Could create duplicate insights

**Fix - Deferred**: This is low priority. R5's primary function (dream-like exploration) works correctly. Deduplication can be added in a future iteration.

---

## Issue 6: Entity Disambiguation (CONFIDENCE-DRIVEN GAP ROUTING)

**Severity**: CRITICAL (Core intelligence problem)

**Problem Statement**:

- "There can be 100 Jeels in a person's life with different relations"
- "Jeel at work" vs "Jeel at home" — same person or different?
- "Dad's colleague Jeel" vs "My fiancee Jeel" — definitely 2 different people
- "Jeel" (friend) → "Jeel" (fiancee) — same person, relationship evolved

**The Core Insight**: When confidence is NOT HIGH, don't guess. **Emit a GAP** and let the human resolve it. The system learns from that resolution.

**Current System Limitations**:

- R4 matches entities by `canonical_name` only
- No relationship-aware disambiguation
- No alias tracking (Jeel = Jilu = babe = fiancee)
- No context clustering (co-occurrence patterns)
- **No GAP emission for uncertain matches**

**Why This Is Hard**:

| Scenario | Challenge | Correct Handling |
|----------|-----------|------------------|
| Same name, same person | "Jeel" (friend) + "Jeel" (fiancee) = 1 entity | EVOLVE relationship |
| Same name, different person | "My Jeel" vs "Dad's colleague Jeel" = 2 entities | CREATE separate |
| Different name, same person | "Jeel" = "babe" = "Jilu" = 1 entity | MERGE aliases |
| **Uncertain match** | Confidence 0.60-0.85 | **GAP → P06 → Human** |

**Confidence-Based Routing Protocol**:

```
┌─────────────────────────────────────────────────────────────────┐
│                 ENTITY DISAMBIGUATION FLOW                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  New Entity Mention: "Jeel"                                     │
│           │                                                      │
│           ▼                                                      │
│  ┌─────────────────────────────────────────┐                    │
│  │  Query candidates from st_kg_dom        │                    │
│  │  WHERE name ILIKE '%jeel%'              │                    │
│  │     OR aliases_json ? 'jeel'            │                    │
│  └─────────────────────────────────────────┘                    │
│           │                                                      │
│           ▼                                                      │
│  ┌─────────────────────────────────────────┐                    │
│  │  Score each candidate (5 signals):      │                    │
│  │  • Name similarity (20%)                │                    │
│  │  • Relationship context (25%)           │                    │
│  │  • Co-occurrence patterns (20%)         │                    │
│  │  • Temporal proximity (10%)             │                    │
│  │  • Embedding similarity (25%)           │                    │
│  └─────────────────────────────────────────┘                    │
│           │                                                      │
│           ▼                                                      │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │                                                              ││
│  │  Confidence ≥ 0.85  ─────────▶  AUTO-MATCH                  ││
│  │  │                              (same entity, high conf)     ││
│  │  │                                                           ││
│  │  │  Confidence 0.60-0.84 ────▶  GAP → P06 → HUMAN           ││
│  │  │                              (uncertain, ask user)        ││
│  │  │                                                           ││
│  │  │  Confidence < 0.60  ──────▶  CREATE NEW ENTITY           ││
│  │  │                              (different person)           ││
│  │                                                              ││
│  └─────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
```

**Disambiguation Signals Available**:

| Signal | Source | How It Helps |
|--------|--------|--------------|
| **Relationship type** | st_social.relationship_type | SPOUSE/FIANCEE implies close personal connection |
| **Co-occurrence** | st_kg_edges | Entities that appear together often likely same context |
| **Temporal proximity** | st_hipp_events.event_time | Mentions close in time = likely same person |
| **Spatial context** | st_hipp_events.location | "Jeel at home" vs "Jeel at office" |
| **Actor context** | st_hipp_events.actor_id | Who mentioned Jeel? Prince? Dad? |
| **Embedding similarity** | st_vec | Semantic similarity of entity descriptions |

**Smart Pipeline Solution - Multi-Signal Entity Resolution**:

```python
async def resolve_entity(
    self,
    extracted_entity: ExtractedEntity,
    space_id: str,
    context: EntityContext
) -> ResolvedEntity:
    """
    Smart entity resolution using multiple signals.

    The key insight: Don't just match on name.
    Use relationship context, co-occurrence, and embeddings.
    """

    # 1. Query existing entities with same/similar name
    candidates = await self._query_entity_candidates(
        space_id=space_id,
        name=extracted_entity.name,
        aliases=extracted_entity.possible_aliases,
        entity_type=extracted_entity.entity_type
    )

    if not candidates:
        # Truly new entity
        return ResolvedEntity(
            decision="CREATE",
            entity=extracted_entity,
            confidence=0.9
        )

    # 2. Score each candidate using multiple signals
    scored_candidates = []
    for candidate in candidates:
        score = 0.0

        # Signal A: Name match (basic)
        name_sim = self._compute_name_similarity(
            extracted_entity.name,
            candidate.canonical_name,
            candidate.aliases
        )
        score += name_sim * 0.20

        # Signal B: Relationship context (critical for your case)
        # If "Jeel" is mentioned as "my fiancee" and existing Jeel has
        # relationship_type=FRIEND, check if they should merge
        rel_score = await self._relationship_compatibility(
            extracted_entity.relationship_context,
            candidate.entity_id,
            space_id
        )
        score += rel_score * 0.25

        # Signal C: Co-occurrence with same entities
        # Does new "Jeel" appear with same people as existing "Jeel"?
        cooccur_score = await self._cooccurrence_similarity(
            extracted_entity.cooccurring_entities,
            candidate.entity_id,
            space_id
        )
        score += cooccur_score * 0.20

        # Signal D: Temporal proximity
        # Was existing Jeel mentioned around same time?
        temporal_score = self._temporal_proximity(
            extracted_entity.event_time,
            candidate.last_observed_at
        )
        score += temporal_score * 0.10

        # Signal E: Embedding similarity
        # Semantic similarity of entity descriptions
        embed_score = await self._embedding_similarity(
            extracted_entity.embedding,
            candidate.embedding_id
        )
        score += embed_score * 0.25

        scored_candidates.append((candidate, score))

    # 3. Make decision based on scores
    best_match, best_score = max(scored_candidates, key=lambda x: x[1])

    if best_score > 0.85:
        # High confidence match - same entity
        return ResolvedEntity(
            decision="MATCH",
            entity_id=best_match.entity_id,
            confidence=best_score,
            updates={
                "aliases": self._merge_aliases(
                    best_match.aliases,
                    [extracted_entity.name]
                ),
                "relationship_context": self._merge_relationships(
                    best_match.relationships,
                    extracted_entity.relationship_context
                )
            }
        )
    elif best_score > 0.60:
        # Medium confidence - might be same, ask if uncertain
        return ResolvedEntity(
            decision="UNCERTAIN",
            candidate_id=best_match.entity_id,
            confidence=best_score,
            gap_question=f"Is '{extracted_entity.name}' the same as '{best_match.canonical_name}'?"
        )
    else:
        # Low confidence - different entity with similar name
        return ResolvedEntity(
            decision="CREATE",
            entity=extracted_entity,
            confidence=0.8,
            disambiguation_suffix=self._generate_suffix(context)
        )
```

**Relationship Evolution Detection**:

For "Jeel is my friend" → "Jeel is my fiancee":

```python
async def _relationship_compatibility(
    self,
    new_relationship: str,
    existing_entity_id: str,
    space_id: str
) -> float:
    """
    Score relationship compatibility.

    Key insight: Relationships EVOLVE.
    Friend → Dating → Fiancee → Spouse is NATURAL progression.
    Friend → Parent is IMPOSSIBLE (different entity).
    """

    existing_rels = await self._get_entity_relationships(
        existing_entity_id, space_id
    )

    # Relationship evolution matrix
    COMPATIBLE_EVOLUTIONS = {
        ("FRIEND", "DATING"): 0.95,
        ("FRIEND", "FIANCEE"): 0.90,
        ("DATING", "FIANCEE"): 0.98,
        ("FIANCEE", "SPOUSE"): 0.99,
        ("FRIEND", "SPOUSE"): 0.85,  # Skipped stages but possible
        ("COLLEAGUE", "FRIEND"): 0.90,
        ("ACQUAINTANCE", "FRIEND"): 0.95,
    }

    INCOMPATIBLE = {
        ("FRIEND", "PARENT"): 0.0,
        ("SPOUSE", "SIBLING"): 0.0,
        ("CHILD", "GRANDPARENT"): 0.0,
    }

    for existing_rel in existing_rels:
        key = (existing_rel.relationship_type, new_relationship)

        if key in INCOMPATIBLE:
            return INCOMPATIBLE[key]

        if key in COMPATIBLE_EVOLUTIONS:
            return COMPATIBLE_EVOLUTIONS[key]

        # Same relationship type
        if existing_rel.relationship_type == new_relationship:
            return 1.0

    # Unknown combination - moderate score
    return 0.5
```

**Alias Management**:

```python
# st_kg_dom already has aliases_json column
# Use it properly:

async def _merge_aliases(
    self,
    existing_aliases: List[str],
    new_names: List[str]
) -> List[str]:
    """
    Merge alias lists, avoiding duplicates.

    When "Jeel" is also called "babe" or "fiancee",
    add those to the alias list.
    """
    combined = set(existing_aliases)
    for name in new_names:
        normalized = self._normalize_name(name)
        combined.add(normalized)
    return list(combined)

# Example result in st_kg_dom:
# canonical_name: "Jeel"
# aliases_json: ["jilu", "babe", "fiancee", "my love"]
# entity_type: "PERSON"
# relationship_context: "Prince's fiancee, close relationship"
```

**Gap Detection for Uncertain Cases**:

When the system can't decide, emit a gap for P06 Active Learning:

```python
# If score is between 0.60-0.85, emit gap:
gap = GapRecord(
    gap_type="ENTITY_DISAMBIGUATION",
    entity_type="PERSON",
    entity_ids=[extracted_entity.temp_id, best_match.entity_id],
    question=f"Is '{extracted_entity.name}' the same person as '{best_match.canonical_name}'?",
    context={
        "new_mention": extracted_entity.source_text,
        "existing_description": best_match.description,
        "confidence": best_score,
        "actor_id": context.actor_id,  # Who mentioned this entity?
        "relationship_hint": extracted_entity.relationship_context
    },
    priority="HIGH"  # Disambiguation affects KG quality
)

# Emit to P06 via outbox
await self._emit_gap(gap)

# Meanwhile, create PROVISIONAL entity (can be merged later)
provisional_entity = await self._create_provisional(
    entity=extracted_entity,
    pending_disambiguation=gap.gap_id
)
```

**Human Resolution → System Learning**:

When human resolves the GAP:

```python
async def handle_gap_resolution(
    self,
    gap_id: str,
    resolution: GapResolution
) -> None:
    """
    Human resolved the disambiguation.
    Learn from their decision for future cases.
    """
    gap = await self._get_gap(gap_id)

    if resolution.answer == "SAME_ENTITY":
        # Merge the provisional entity into existing
        await self._merge_entities(
            source_id=gap.entity_ids[0],  # provisional
            target_id=gap.entity_ids[1],  # existing
            merge_aliases=True
        )

        # Learn: This context pattern means SAME entity
        await self._learn_disambiguation_pattern(
            features=gap.context,
            outcome="MERGE",
            confidence_adjustment=+0.05
        )

    elif resolution.answer == "DIFFERENT_ENTITY":
        # Keep provisional as separate entity
        await self._confirm_provisional(gap.entity_ids[0])

        # Learn: This context pattern means DIFFERENT entity
        await self._learn_disambiguation_pattern(
            features=gap.context,
            outcome="SEPARATE",
            confidence_adjustment=-0.05
        )
```

**Files to Change**:

- `k0/pipelines/p03/phases/r4_kg_consolidator.py` - Add smart entity resolution with GAP emission
- `k0/modules/consolidation/algorithms/entity_resolver.py` (NEW) - Entity disambiguation algorithm
- `k0/modules/consolidation/algorithms/relationship_evolution.py` (NEW) - Relationship compatibility matrix
- `k0/modules/consolidation/algorithms/disambiguation_learner.py` (NEW) - Learn from human resolutions

---

## Issue 7: Temporal Anchoring (EVERY MEMORY IS TIME-BOUND)

**Severity**: CRITICAL (Foundational intelligence problem)

**Problem Statement**:

- "Remind me to pay rent next week" — But what IS next week?
- "I was having fever last weekend" — Which weekend?
- "Tomorrow I have a meeting" — Tomorrow from WHEN?

**The Core Insight**:
Memories are NOT temporally agnostic. Every memory episode needs data of **specific time** to enable:

1. **Pattern extraction** across days/months/years
2. **Life history queries** ("What did I eat for lunch last summer?")
3. **Trend analysis** ("Am I sleeping better this month?")
4. **Routine detection** ("What's my typical Tuesday?")

**Without temporal anchoring, relative expressions are MEANINGLESS.**

**Current System Gaps**:

| Gap | Problem |
|-----|---------|
| **No anchor time** | TemporalParser uses `datetime.now()` if `reference_time` not passed |
| **LLM doesn't know current time** | LLM sees "next week" but doesn't know current date |
| **Event ingestion time not used** | `st_hipp_events.event_time_utc` exists but not passed to parser |
| **Memories stored without temporal context** | st_epi has `start_time_utc` but relative expressions lost |

**Current TemporalParser Behavior**:

```python
# In temporal_parser.py line 264:
ref = datetime.fromtimestamp((ref_time or int(datetime.now().timestamp() * 1000)) / 1000)
```

This defaults to `now()` which is WRONG for historical events.

**Correct Temporal Anchoring**:

Every memory and event MUST have TWO timestamps:

1. **event_time_utc** — When the event happened (the anchor)
2. **ingestion_time_utc** — When we recorded it (for audit)

When user says "last weekend", we need:

- `event_time_utc` (when they told us) to calculate "last weekend" relative to THAT moment

**Fix - Temporal Anchor Protocol**:

```python
@dataclass
class TemporalAnchor:
    """
    Every temporal expression MUST be anchored.

    Without this, "next week" is meaningless.
    """
    # The anchor time - when the statement was made
    anchor_time_utc: int  # Unix ms

    # The resolved absolute time
    resolved_time_utc: int  # Unix ms

    # The original relative expression
    original_expression: str  # "next week", "last weekend", "tomorrow"

    # Confidence in resolution
    confidence: float  # 0.0-1.0

    # Resolution method
    method: str  # "relative_date", "absolute_date", "duration"


async def parse_with_anchor(
    self,
    temporal_json: str,
    anchor_time_utc: int,  # REQUIRED - not optional!
) -> TemporalAnchor:
    """
    Parse temporal expression with explicit anchor.

    The anchor is typically:
    - For user input: The event_time_utc when user spoke
    - For reminders: The ingestion_time_utc
    - For historical: The date being discussed
    """
    # Use anchor, NOT datetime.now()
    ref = datetime.fromtimestamp(anchor_time_utc / 1000)

    # Parse the expression relative to anchor
    resolved_ms = self._parse_temporal_text(
        text=temporal_json,
        ref_time=anchor_time_utc
    )

    return TemporalAnchor(
        anchor_time_utc=anchor_time_utc,
        resolved_time_utc=resolved_ms,
        original_expression=temporal_json,
        confidence=0.9,
        method="relative_date"
    )
```

**Temporal Context for Memory Storage**:

```python
# When storing in st_epi, st_sem, st_prospective:

# BAD: Loses temporal relativity
episode = {
    "start_time_utc": 1705536000000,  # Some timestamp
    "description": "User had fever last weekend"  # WHICH weekend??
}

# GOOD: Preserves temporal context
episode = {
    "start_time_utc": 1705536000000,  # Resolved "last weekend"
    "anchor_time_utc": 1705708800000,  # When user told us
    "original_temporal_expr": "last weekend",  # What they said
    "description": "User had fever",  # Clean description
    "temporal_confidence": 0.95
}
```

**LLM Context Injection**:

When LLM processes input, inject current temporal context:

```python
async def build_llm_context(self, event: HippEvent) -> str:
    """
    Build temporal context for LLM.

    LLM doesn't know what time it is - tell it!
    """
    anchor_dt = datetime.fromtimestamp(event.event_time_utc / 1000)

    return f"""
Current context:
- Date: {anchor_dt.strftime('%A, %B %d, %Y')}
- Time: {anchor_dt.strftime('%I:%M %p')}
- Day of week: {anchor_dt.strftime('%A')}
- Week of year: {anchor_dt.isocalendar().week}

When user says:
- "tomorrow" = {(anchor_dt + timedelta(days=1)).strftime('%B %d, %Y')}
- "next week" = Week of {(anchor_dt + timedelta(weeks=1)).strftime('%B %d')}
- "last weekend" = {(anchor_dt - timedelta(days=anchor_dt.weekday() + 2)).strftime('%B %d-%d')}
"""
```

**Retroactive Temporal Resolution**:

For past events where we didn't capture anchor:

```python
async def backfill_temporal_anchors(
    self,
    space_id: str,
    episode_id: str
) -> None:
    """
    Backfill temporal anchors for episodes that lack them.

    Use created_at as anchor if event_time_utc not available.
    """
    episode = await self._get_episode(episode_id)

    if episode.anchor_time_utc is None:
        # Fallback: use created_at as anchor
        anchor = episode.created_at

        # Re-resolve any temporal expressions in description
        if self._has_temporal_expression(episode.description):
            resolved = await self._resolve_temporals(
                text=episode.description,
                anchor=anchor
            )
            await self._update_episode_temporals(episode_id, resolved)
```

**Files to Change**:

- `k0/modules/consolidation/algorithms/temporal_parser.py` - Make anchor_time REQUIRED
- `k0/pipelines/p02/phases/temporal_enrichment.py` - Inject temporal context
- `k0/modules/builders/hipp_events_row.py` - Ensure event_time_utc always passed

**Schema Changes**:

- Add `anchor_time_utc` column to st_epi, st_sem, st_prospective
- Add `original_temporal_expr` column to store original relative expression
- Add `temporal_confidence` column for resolution confidence

---

### Incremental Memory Formation: The Lunch Example

**The Key Insight**: When we form memory daily, we add time/place/participants incrementally. Over time, this enables pattern extraction for a holistic life view.

**Day-by-Day Accumulation**:

```
Day 1 (Monday):
  st_hipp_events: "Had lunch at cafeteria"
  → Resolved: 12:30pm, office cafeteria
  → st_epi: lunch_2026_01_13 {time: 12:30, place: cafeteria, food: unknown}

Day 2 (Tuesday):
  st_hipp_events: "Grabbed a sandwich at my desk"
  → Resolved: 1:00pm, desk
  → st_epi: lunch_2026_01_14 {time: 13:00, place: desk, food: sandwich}

Day 3 (Wednesday):
  st_hipp_events: "Had pizza with Jeel"
  → Resolved: 12:45pm, with Jeel
  → st_epi: lunch_2026_01_15 {time: 12:45, participants: [Jeel], food: pizza}

...365 days later...
```

**Pattern Extraction from Temporal Data**:

| Query | How System Answers |
|-------|-------------------|
| "What do I usually eat for lunch?" | Aggregate `food` from 365 lunch episodes → frequency map |
| "When do I usually have lunch?" | Cluster `time` from 365 episodes → "12:30-1:00pm range" |
| "Who do I lunch with most often?" | Aggregate `participants` → "Jeel (40%), alone (60%)" |
| "How has my diet changed?" | Time-series analysis of `food` categories |
| "What did I eat last summer?" | Filter episodes by `start_time_utc` in June-Aug range |

**Memory Layer Progression**:

```
┌─────────────────────────────────────────────────────────────────┐
│                 INCREMENTAL MEMORY FORMATION                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  RAW EVENTS (st_hipp_events)                                    │
│  ├── "Had lunch" (Day 1, 12:30pm)                               │
│  ├── "Having sandwich" (Day 2, 1:00pm)                          │
│  ├── "Pizza with Jeel" (Day 3, 12:45pm)                         │
│  └── ... (365 events)                                           │
│           │                                                      │
│           ▼ P03 (daily consolidation)                           │
│                                                                  │
│  EPISODES (st_epi) - One per distinct lunch event               │
│  ├── lunch_2026_01_13 {time, place, food, mood, ...}           │
│  ├── lunch_2026_01_14 {time, place, food, mood, ...}           │
│  └── ... (365 episodes)                                         │
│           │                                                      │
│           ▼ P03 R3 (pattern detection over weeks)               │
│                                                                  │
│  PATTERNS (st_sem) - Extracted from episode clusters            │
│  ├── "weekday_lunch_pattern" {                                  │
│  │     typical_time: "12:30-1:00pm",                            │
│  │     typical_location: "office",                              │
│  │     typical_duration: 30min,                                 │
│  │     typical_companions: {Jeel: 40%, alone: 60%},             │
│  │     source_episodes: [365 episode IDs]                       │
│  │   }                                                          │
│  └── "weekend_brunch_pattern" { ... }                           │
│           │                                                      │
│           ▼ P03 R3 (routine detection over months)              │
│                                                                  │
│  ROUTINES (st_procedural)                                       │
│  └── "lunch_routine" {                                          │
│        steps: ["check time ~12:30", "decide location", "eat"],  │
│        execution_count: 365,                                    │
│        temporal_regularity: 0.85                                │
│      }                                                          │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**Same Pattern Applies To**:

| Routine | Episodes → Patterns → Insights |
|---------|-------------------------------|
| **Night Routine** | Sleep time, pre-bed activities → Sleep quality trends |
| **Morning Routine** | Wake time, first activity → Energy pattern analysis |
| **Work Patterns** | Tasks, breaks, meetings → Productivity insights |
| **Relationship Patterns** | Conversations with Jeel → Relationship health |
| **Health Patterns** | Meals, exercise, symptoms → Wellness tracking |

**Why Temporal Grounding is Critical**:

Without resolved timestamps, we CANNOT:

- Cluster episodes by time of day
- Detect weekly patterns (weekday vs weekend)
- Analyze trends over months/years
- Answer "What was I doing last summer?"

---

## Issue 8: Smart Memory Layers (st_epi, st_sem, st_procedural)

**Severity**: HIGH (Consistency across all memory types)

**Problem Statement**:
Issue 6 covers entity disambiguation for st_kg_dom. But the SAME problems exist for:

- **st_epi** (Episodic Memory): Duplicate episodes of same event
- **st_sem** (Semantic Memory): Duplicate facts about same concept
- **st_procedural** (Procedural Memory): Duplicate procedures for same task

**Current Gaps**:

| Layer | Problem | Example |
|-------|---------|---------|
| **st_epi** | Same episode created multiple times | "Dinner with Panda" x3 from different mentions |
| **st_sem** | Same fact stored multiple times | "Earth orbits Sun" with slight wording variations |
| **st_procedural** | Same routine duplicated | "Morning coffee routine" x5 |

**Episode Disambiguation (st_epi)**:

```python
async def resolve_episode(
    self,
    new_episode: EpisodeCandidate,
    space_id: str
) -> EpisodeResolution:
    """
    Smart episode resolution - don't create duplicates.

    Key signals:
    - Temporal overlap (same time period)
    - Participant overlap (same people)
    - Location match (same place)
    - Semantic similarity (same topic)
    """

    # Query existing episodes in overlapping time window
    existing = await self._query_episodes(
        space_id=space_id,
        time_start=new_episode.start_time_utc - timedelta(hours=2).total_seconds() * 1000,
        time_end=new_episode.end_time_utc + timedelta(hours=2).total_seconds() * 1000
    )

    for candidate in existing:
        score = 0.0

        # Signal A: Temporal overlap
        overlap = self._compute_temporal_overlap(new_episode, candidate)
        score += overlap * 0.30

        # Signal B: Participant match
        participant_match = self._participant_similarity(
            new_episode.participants_json,
            candidate.participants_json
        )
        score += participant_match * 0.25

        # Signal C: Location match
        if new_episode.primary_location == candidate.primary_location:
            score += 0.20

        # Signal D: Semantic similarity
        embed_sim = await self._embedding_similarity(
            new_episode.embedding_id,
            candidate.embedding_id
        )
        score += embed_sim * 0.25

        if score > 0.85:
            return EpisodeResolution(
                decision="MATCH",
                episode_id=candidate.episode_id,
                updates={
                    "observation_count": candidate.observation_count + 1,
                    "source_events_json": self._merge_events(
                        candidate.source_events_json,
                        new_episode.source_events_json
                    )
                }
            )

    return EpisodeResolution(decision="CREATE", episode=new_episode)
```

**Semantic Fact Disambiguation (st_sem)**:

```python
async def resolve_semantic_fact(
    self,
    new_fact: SemanticFact,
    space_id: str
) -> SemanticResolution:
    """
    Smart semantic fact resolution.

    Key insight: Same fact can be stated many ways.
    "Earth orbits Sun" = "Sun is center of solar system" = "Earth revolves around Sun"
    """

    # Query by embedding similarity (semantic match)
    candidates = await self._query_similar_facts(
        space_id=space_id,
        embedding=new_fact.embedding,
        similarity_threshold=0.85
    )

    for candidate in candidates:
        # Check if facts are equivalent (not just similar)
        equivalence = await self._check_fact_equivalence(
            new_fact.statement,
            candidate.statement
        )

        if equivalence.is_equivalent:
            # Same fact, different wording
            return SemanticResolution(
                decision="REINFORCE",
                fact_id=candidate.fact_id,
                updates={
                    "observation_count": candidate.observation_count + 1,
                    "confidence": min(0.99, candidate.confidence + 0.01),
                    "alternative_phrasings": self._merge_phrasings(
                        candidate.alternative_phrasings,
                        [new_fact.statement]
                    )
                }
            )
        elif equivalence.is_related:
            # Related but different fact - link them
            return SemanticResolution(
                decision="CREATE_LINKED",
                new_fact=new_fact,
                links=[{
                    "target_id": candidate.fact_id,
                    "relationship": "RELATED_TO",
                    "confidence": equivalence.relatedness_score
                }]
            )

    return SemanticResolution(decision="CREATE", fact=new_fact)
```

**Procedural Routine Disambiguation (st_procedural)**:

```python
async def resolve_procedure(
    self,
    new_procedure: ProceduralCandidate,
    space_id: str
) -> ProceduralResolution:
    """
    Smart procedural memory resolution.

    Key insight: Same routine might be described differently.
    "Morning coffee routine" = "How I make coffee in the morning"
    """

    # Query by action type and context
    candidates = await self._query_procedures(
        space_id=space_id,
        action_type=new_procedure.action_type,
        context_keywords=new_procedure.context_keywords
    )

    for candidate in candidates:
        # Check step similarity
        step_match = self._compare_steps(
            new_procedure.steps_json,
            candidate.steps_json
        )

        if step_match > 0.80:
            # Same procedure, possibly updated
            return ProceduralResolution(
                decision="EVOLVE",
                procedure_id=candidate.procedure_id,
                updates={
                    "steps_json": self._merge_steps(
                        candidate.steps_json,
                        new_procedure.steps_json,
                        strategy="PREFER_RECENT"
                    ),
                    "last_executed_at": new_procedure.observed_at,
                    "execution_count": candidate.execution_count + 1
                }
            )

    return ProceduralResolution(decision="CREATE", procedure=new_procedure)
```

**Cross-Layer Consistency**:

When the same information exists in multiple layers, keep them consistent:

```python
async def ensure_cross_layer_consistency(
    self,
    space_id: str,
    entity_id: str
) -> None:
    """
    When an entity changes, propagate to all layers.

    Example: "Jeel" relationship changes from FRIEND to FIANCEE
    - st_kg_dom: Update entity
    - st_social: Update relationship
    - st_epi: Update participant references in episodes
    - st_sem: Update semantic facts about Jeel
    """

    entity = await self._get_entity(entity_id)

    # Update st_social relationships
    await self._update_social_relationships(space_id, entity)

    # Update st_epi participant references
    await self._update_episode_participants(space_id, entity)

    # Update st_sem facts referencing this entity
    await self._update_semantic_references(space_id, entity)
```

**Files to Change**:

- `k0/pipelines/p03/phases/r2_episode_clusterer.py` - Episode disambiguation
- `k0/modules/consolidation/algorithms/episode_resolver.py` (NEW)
- `k0/modules/consolidation/algorithms/semantic_resolver.py` (NEW)
- `k0/modules/consolidation/algorithms/procedural_resolver.py` (NEW)
- `k0/modules/consolidation/algorithms/cross_layer_sync.py` (NEW)

---

## Implementation Order (Revised)

**Foundational Fixes First** — These enable everything else:

| Order | Issue | Effort | Impact | Reason |
|-------|-------|--------|--------|--------|
| 1 | **Issue 7: Temporal Anchoring** | 4-6 hours | CRITICAL | Every memory needs time-binding first |
| 2 | R1 novelty_score fix | 30 min | HIGH | 25% of formula dead |
| 3 | **Issue 6: Entity Disambiguation + GAP** | 6-8 hours | CRITICAL | Confidence routing + human learning |
| 4 | R4 entity deduplication | 2-3 hours | HIGH | Stops "PANDA x7" problem |
| 5 | R2 episode deduplication | 2-3 hours | HIGH | Prevents duplicate episodes |
| 6 | Weight learning protection | 1 hour | MEDIUM | Prevents calibration corruption |
| 7 | Issue 8: Smart Memory Layers | 4-6 hours | HIGH | st_epi, st_sem, st_procedural smart |
| 8 | R5 output deduplication | Deferred | LOW | Low priority |

**Why This Order**:

1. **Temporal Anchoring First**: Without resolved timestamps, we cannot cluster episodes by time, detect patterns, or answer life history queries. This is foundational.

2. **Entity Disambiguation Second**: The 100-Jeels problem requires confidence-based GAP routing. Human resolutions teach the system.

3. **Everything Else**: Once temporal and entity foundation is solid, the rest becomes easier.

---

## Testing Checklist

### Issue 7: Temporal Anchoring

- [ ] `test_relative_date_uses_event_ts` - "next week" resolved using event_time_utc, NOT datetime.now()
- [ ] `test_anchor_time_stored` - st_epi stores anchor_time_utc column
- [ ] `test_temporal_confidence_stored` - st_epi stores temporal_confidence
- [ ] `test_original_expression_preserved` - "last weekend" stored in original_temporal_expr
- [ ] `test_llm_receives_temporal_context` - LLM prompt includes current date/time

### Issue 6: Entity Disambiguation

- [ ] `test_high_confidence_auto_match` - Score ≥0.85 auto-merges entities
- [ ] `test_medium_confidence_emits_gap` - Score 0.60-0.84 emits GAP to P06
- [ ] `test_low_confidence_creates_new` - Score <0.60 creates separate entity
- [ ] `test_gap_resolution_merges_entities` - Human "SAME" answer merges provisional
- [ ] `test_gap_resolution_confirms_separate` - Human "DIFFERENT" confirms provisional
- [ ] `test_disambiguation_learning` - System adjusts confidence thresholds from human feedback

### R1 Fix

- [ ] `test_importance_uses_salience_score` - Verifies salience_score used instead of novelty_score
- [ ] `test_importance_nonzero` - Verifies importance > 0 for emotional events

### R4 Fix

- [ ] `test_entity_reinforce_existing` - Same entity boosts confidence, doesn't create duplicate
- [ ] `test_entity_extend_existing` - New attributes added to existing entity
- [ ] `test_entity_create_novel` - Truly new entity creates new record

### R2 Fix

- [ ] `test_episode_reinforce_existing` - Event matching existing episode uses that cluster
- [ ] `test_episode_create_novel` - Novel events form new clusters
- [ ] `test_episode_temporal_alignment` - Episodes clustered by resolved time, not raw event_ts

### Weight Learning Fix

- [ ] `test_small_batch_skipped` - Batch < 50 does not update weights
- [ ] `test_drift_detection` - >15% drift emits warning

### Incremental Memory Formation

- [ ] `test_pattern_extraction_from_episodes` - 30 lunch episodes → lunch_pattern in st_sem
- [ ] `test_routine_detection_from_patterns` - Pattern repetition → routine in st_procedural
- [ ] `test_life_query_across_time` - "What did I eat last summer?" returns correct episodes

---

## Architecture Alignment

This fix aligns with P03 Dossier v2 philosophy and **civilizational scale** requirements:

| Principle | Implementation |
|-----------|----------------|
| "Every memory is time-bound" | Temporal anchoring with resolved timestamps |
| "Confidence-driven disambiguation" | HIGH→auto, MEDIUM→GAP→human, LOW→create |
| "Incremental memory formation" | Events → Episodes → Patterns → Routines |
| "8 Memory Layers = TRUTH" | R2, R4 query truth before creating |
| "REINFORCE, EXTEND, CREATE, EVOLVE" | All phases support reconciliation decisions |
| "Query truth before writing" | Added to R2, R4 |
| "Protect learned parameters" | Weight learning has batch protection |
| "Human-in-the-loop learning" | GAP resolution teaches disambiguation |

---

## Files Summary

| File | Changes |
|------|---------|
| **Temporal Anchoring** | |
| `k0/modules/consolidation/algorithms/temporal_parser.py` | Make anchor_time REQUIRED, never use datetime.now() |
| `k0/pipelines/p02/phases/temporal_enrichment.py` | Resolve relative→absolute in P02 |
| `k0/modules/builders/hipp_events_row.py` | Ensure event_time_utc always passed |
| `governance/k0/schemas/st_epi.yaml` | Add anchor_time_utc, original_temporal_expr columns |
| **Entity Disambiguation** | |
| `k0/pipelines/p03/phases/r4_kg_consolidator.py` | Add confidence-based routing + GAP emission |
| `k0/modules/consolidation/algorithms/entity_resolver.py` (NEW) | Multi-signal entity disambiguation |
| `k0/modules/consolidation/algorithms/relationship_evolution.py` (NEW) | Compatible/incompatible evolution matrix |
| `k0/modules/consolidation/algorithms/disambiguation_learner.py` (NEW) | Learn from human GAP resolutions |
| **Core Fixes** | |
| `k0/modules/consolidation/algorithms/importance_scorer.py` | Use salience_score or set novelty_weight=0 |
| `k0/pipelines/p03/phases/r2_episode_clusterer.py` | Query st_epi before clustering |
| `k0/modules/consolidation/algorithms/importance_weight_learner.py` | Add batch protection |
| `k0/pipelines/p03/event_state.py` | Add reconciliation_decision field |
| **Smart Memory Layers** | |
| `k0/modules/consolidation/algorithms/episode_resolver.py` (NEW) | Episode disambiguation |
| `k0/modules/consolidation/algorithms/semantic_resolver.py` (NEW) | Semantic fact disambiguation |
| `k0/modules/consolidation/algorithms/procedural_resolver.py` (NEW) | Procedural routine disambiguation |
| `k0/modules/consolidation/algorithms/cross_layer_sync.py` (NEW) | Cross-layer consistency |

---

## UltraBERT Integration Note

**Temporal Head (#9) Output** (from UltraBERT reference):

```json
{
  "entities": [
    {"text": "yesterday", "label": "DATE_REL", "start_token": 10, "end_token": 11}
  ]
}
```

**Key Insight**: UltraBERT **tags** temporal expressions but does **NOT resolve** them. Resolution must happen in P02 Enrichment using the `event_ts` anchor:

```
UltraBERT: "next week" → {text: "next week", label: "DATE_REL"}
P02 Temporal Enrichment: → {start_ms: 1737417600000, end_ms: 1738022400000, anchor_ms: event_ts}
P03 Consolidation: Uses resolved absolute times for clustering and pattern extraction
```
