# P02: Write / Hippocampus - Development Dossier

**Status**: ✅ Step 1 Discovery (CORRECTED - Final Dossier Review Completed)
**Last Updated**: 2025-11-15
**Key Changes**:

- ✅ Fixed two-phase architecture (Command Port hot path → WAL, P02 background from Outbox)
- ✅ Replaced `st_hipp_store` → `st_hipp_events` (NEW TABLE, st_hipp_store deprecated)
- ✅ Replaced `st_embedding_jobs` → `st_embedding_queue` (NEW TABLE, never existed)
- ✅ Restored `st_relationships` (undeprecate from migration 0021, family graph from 0018 seeds)
- ✅ Extended relationship types from 3 to 5 (added CHILD_OF, SIBLING_OF in migration 0024)
- ✅ Fixed table references (`idem_ledger` not `st_idem_ledger`, read from `st_wal`)
- ✅ Inline modules pattern (DGService, AffectService, SpaceResolver, NOT separate pipelines)
- ✅ Removed non-existent geo tables (st_geo_city, st_geo_brand_lexicon, st_geo_geofence)
- ✅ PipelineProtocol contract (required_caps, declared_topics, BusDispatcher integration)
- ✅ Minimal geo enrichment (use envelope location_geohash, defer complex geo to P09)
- ✅ Basic social graph (SPOUSE_OF, PARENT_OF, CHILD_OF, CARETAKER_OF, SIBLING_OF from st_relationships)

---

## Purpose

P02 is the **background episodic memory formation pipeline inside K0** for memory events.

P02 runs **AFTER the hot path Command Port has committed to WAL**:

1. Command Port (Phase 1 ~93ms):
   - PEP validation → idempotency check → policy enforcement
   - Atomic write to 4 tables: `st_wal` (primary), `idem_ledger`, `st_outbox`, `st_receipts`
   - Client receives 202 Accepted

2. P02 Background Processing (Phase 2 ~50-100ms):
   - Subscribes to `cognitive.memory.write.committed.v1` topic via BusDispatcher
   - Dequeues from `st_outbox` (batch of 128 events)
   - Reads envelope from `st_wal` via `wal_pos`
   - Enriches with hippocampus DG, affect classification, space resolution
   - Writes to `st_hipp_events` (NEW TABLE - replaces deprecated `st_hipp_store`)
   - Emits completion events for downstream pipelines

**Architecture Note**: P02 is ASYNC background processing, NOT part of hot path. From **P02's point of view**, the hot path's durable source is `st_wal`. The Command Port actually commits to `st_wal`, `idem_ledger`, `st_outbox`, and `st_receipts`, but P02 only reads from `st_wal` (plus `st_outbox` as its work queue).

> P02 = "From WAL-committed envelope → hippocampus enrichment → `st_hipp_events` table."

---

## Scope & Assumptions

- **PEP and policy enforcement happen in Command Port hot path** (before P02).
- P02 subscribes to topic AFTER WAL commit (event: `cognitive.memory.write.committed.v1`).
- **Only ALLOW envelopes reach WAL** (DENY envelopes never enter P02).
- P02 uses **inline modules** (DGService, AffectService, SpaceResolver), NOT separate pipelines.
- P02 reads from `st_wal`, does NOT manage hot path UnitOfWork (Command Port does that).
- CA3 clustering (novelty, dedup) is **deferred to P03** for global structure decisions.

---

## Inputs/Outputs

- **Entry Topic (post-WAL-commit):**
  `cognitive.memory.write.committed.v1`

  **Entry Mechanism**: BusDispatcher calls `P02EpisodicWrite.handle(BusMessage)` after WAL commit event.

  **NOT**: Direct Command Port ingress (that's Phase 1 hot path).

  **In practice**: P02 is driven by the **outbox worker**: the Command Port enqueues work into `st_outbox`, and the pipeline runner / bus driver calls `P02EpisodicWrite.handle(...)` for each dequeued entry. The logical topic label is `cognitive.memory.write.committed.v1`, but the *work queue* is `st_outbox`.

- **Exit Topics:**
  - `workspace.wm.updated.v1` — Working memory update (for P04)
  - `core.affect.analyzed.v1` — Affect classification result (for P06)
  - `space.resolution.complete.v1` — Space resolution result (for P07)
  - `embedding.enqueue.v1` — Embedding job enqueue (for P08)
  - `p02.hippocampus.pattern_separated.v1` — DG fingerprints (for P03)
  - `p02.write.complete.v1` — P02 completion signal (for observability)

- **Storage Reads:**
  - `st_wal` — Read envelope via `wal_pos` from outbox entry (PRIMARY READ)
  - `st_outbox` — Dequeue batch of 128 events (work queue)
  - `st_pipeline_processed` — P02 idempotency/offset tracking (NOT `idem_ledger`)
  - `st_relationships` — Family graph (5 types: SPOUSE_OF, PARENT_OF, CHILD_OF, CARETAKER_OF, SIBLING_OF) - **RESTORED in migration 0024**
  - `households` — Household metadata (35 columns)
  - `people` — People directory (33 columns, basic info only)
  - `st_devices` — Device registry (device_kind, device_os, primary-device flags)
  - `st_retention_policy` — Retention matrix (band × topic × device_kind)
  - Tenant config — Timezone, retention defaults

- **Storage Writes:**
  - `st_hipp_events` — **NEW TABLE** (replaces deprecated `st_hipp_store`) - hippocampus staging
  - `st_embedding_queue` — **NEW TABLE** (replaces non-existent `st_embedding_jobs`) - embedding queue for P08
  - `st_outbox` — Emit downstream events (via BusDispatcher)
  - `st_pipeline_processed` — Offset tracking for P02 progress

**Architecture Note**:

- Hot path (Command Port) writes to: `st_wal`, `idem_ledger`, `st_outbox`, `st_receipts`
- P02 (background) reads from: `st_wal`, `st_outbox`
- P02 writes to: `st_hipp_events`, `st_embedding_queue`, `st_outbox` (events)

---

## Example Input Envelope (post-PEP, pre-P02)

```json
{
  "cognitive_trace_id": "11111111-2222-3333-4444-555555555555",
  "tenant_id": "family-smith",
  "space_id": "personal:dad",
  "topic": "memory.episodic.formation",
  "schema_uri": "https://contracts.family-ai.dev/schemas/memory.episodic.json",
  "schema_version": "1.0.0",
  "actor_id": "person_dad",
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
    "location_name": "Olive Garden, Market St",
    "location_type": "restaurant",
    "location_geohash": "9q8yy",
    "participants": ["person_dad", "person_mom"],
    "event_time": "2025-11-10T18:00:00Z",
    "session_id": "session-abc123",
    "conversation_turn": 5,
    "language": "en"
  }
}
```

> **Note**: For AMBER/RED bands, raw `location_lat`/`location_lon` are removed by the hot path (Gate Stage 3). P02 only sees the pre-masked `location_geohash` via `st_wal`.

Hippocampus outputs produced inside P02 before writing to `st_hipp_events`: fingerprints (simhash_hex, minhash32), entities, KG triples, embedding ID, salience. Novelty/dedup/clustering are **deferred to P03**.

---

## Responsibilities (P02 Only — Background Processing from WAL)

### R0 – Parse Outbox Entry & Read from WAL

- [ ] **Dequeue from `st_outbox`**: Batch of 128 events ordered by `wal_pos`.
- [ ] **Read envelope from `st_wal`**: Using `wal_pos` from outbox entry.
  - Parse `envelope_json` column (full envelope structure)
  - Extract `body` (text, participants, location, etc.)
  - Extract `policy_stamp` (already validated by Command Port)
- [ ] **P02 Idempotency check**: Lookup `st_pipeline_processed` by `(pipeline_id='P02_EPISODIC_WRITE', space_id, wal_pos)`.
  - If found: Skip enrichment but still mark the outbox entry as completed/deleted to avoid reprocessing loops.
  - If not found: Proceed to enrichment.
  - Use `self.syscalls.pipeline_processed_upsert()` to record `(pipeline_id, space_id, wal_pos)` after successful write.
- [ ] Assert `policy_stamp.decision == "ALLOW"` (defensive check).

**Architecture Note**: P02 uses `st_pipeline_processed` for its own idempotency (per-pipeline offset tracking). Command Port uses `idem_ledger` for hot-path idempotency. These are separate concerns.

---

### R1 – Hippocampus Processing (DG / CA1) — Inline Modules

**Module Pattern**: P02 uses **inline service classes** (Pattern 1 from whiteboard):

```python
# k0/pipelines/p02_episodic_write.py
class P02EpisodicWrite:
    def __init__(self):
        self._hippocampus_dg = DGService()        # Inline import
        self._affect = AffectService()             # Inline import
        self._space = SpaceResolver()              # Inline import
```

#### R1.1 Pattern Separation (DG) — Fingerprints Only (via DGService)

- [ ] Call `DGService.encode_fast(HippInput)` with:
  - `event_id` (from WAL)
  - `text` (from envelope body)
  - `entities` (extracted from body)
  - `timestamp` (from envelope ts)
  - `participants` (from envelope body)
  - `place` (from envelope body location_name)
  - `activity_type` (from envelope body)
- [ ] Compute **local fingerprints** (no neighbor queries):
  - `simhash_hex` (64-bit SimHash over text + participants + place + activity_type + date)
  - `minhash32` (MinHash signature for LSH buckets, 32 permutations)
- [ ] Do **not** query neighbors or assign novelty/cluster here.
  - `novelty_score`, `near_duplicates`, `episode_cluster_id` are left **NULL**.
  - P03 (Consolidation) will populate those after analyzing the global event space.
- [ ] **Performance**: DG encoding ≤15ms P95 (target per whiteboard)

#### R1.2 Clustering (CA3) — Deferred to P03

- [ ] **P02 does not cluster.** Leave as NULL:
  - `episode_cluster_id` = NULL
  - `cluster_confidence` = NULL
- [ ] P03 (Consolidation) will read fingerprints from `st_hipp_events`, compute global clusters, and update these columns.

#### R1.3 Semantic Projection (CA1)

- [ ] Extract entities and facts:
  - `entities` (e.g., `Olive_Garden_Market_St`, `person_mom`)
  - `kg_triples`:
    - `(person_dad, had_dinner_with, person_mom)`
    - `(event, occurred_at, Olive_Garden_Market_St)`
- [ ] Embedding hook:
  - Allocate `embedding_id` (UUID)
  - Enqueue to `st_embedding_queue` for P08 (vector generation)
  - P02 only stores `embedding_id`, not the vector itself.

#### R1.4 Affect Classification — Inline Module (via AffectService)

- [ ] Call `AffectService.classify_text(text, context)` with:
  - `text` (from envelope body)
  - `context` (person_id, space_id, behavior)
- [ ] Get `AffectAnnotation`:
  - `valence` (0–1, negative to positive)
  - `arousal` (0–1, calm to excited)
  - `tags` (e.g., `["joy", "contentment"]`)
  - `band` (GREEN/AMBER/RED based on affect risk)
  - `band_reasons` (e.g., `["positive_family_event"]`)
  - `model_version` (e.g., `"affect_v1.2"`)
- [ ] **Performance**: Affect classification <70ms P95 (Tier-0: <2ms, Tier-1: <60ms optional)

#### R1.5 Salience Scoring (Write-Path, No Novelty)

- [ ] Compute **write-path salience** (does **not** depend on novelty, which isn't computed yet):
  - `salience_score` = 0.50 × social_importance + 0.40 × affect_intensity + 0.10 × recency_score
  - `salience_reasons` (e.g. `["social_family", "positive_affect", "meal_outside_home"]`)
  - `salience_band` (HIGH / MED / LOW)
- [ ] Note: P03 may refine salience using novelty for long-term views; P02 salience is immediate/cheap.

---

### R2 – Context & Privacy Enrichment

#### R2.1 Space Resolution — Inline Module (via SpaceResolver)

- [ ] Call `SpaceResolver.resolve(SpaceResolutionRequest)` with:
  - `actor_id` (from envelope)
  - `space_id` (from envelope)
  - `policy_stamp` (from envelope)
- [ ] Get `SpaceResolution`:
  - `owner_id` — primary owner of the space
  - `co_owners` — list of co-owners with access
  - `author_role` (OWNER / CO_OWNER / GUEST)
  - `visible_to` = **INTERSECTION** of `policy_stamp.visible_to` AND space visibility rules
    - P02 never expands visibility beyond policy; can only narrow.
    - Safety guarantee: actual visibility ≤ policy-allowed visibility.
- [ ] **Performance**: Space resolution <3ms P95 (cache lookup)
- [ ] **Note**: Family relationship roles (e.g., `{"person_dad": "SPOUSE", "person_mom": "CO_OWNER"}`) are resolved separately in R2.5 (Social Graph), not here.

#### R2.2 Privacy & PII Profile

- [ ] **Band-based coordinate metadata** (read-only):
  - Read `location_geohash` from WAL envelope (already masked by Command Port/Gate Stage 3)
  - Store geo metadata in `st_hipp_events`:
    - `geo_precision_external` = band-based precision from `policy_stamp.obligations` (GREEN=full, AMBER=geohash-6, RED=geohash-4)
    - `geo_masking_reason` = obligation name from policy_stamp (e.g., `"mask.location.precision"`)
  - **Note**: P02 does NOT re-mask coordinates or access raw lat/lon.
    - Hot path (Gate Stage 3) already applied geo masking before WAL write.
    - For AMBER/RED bands, raw `location_lat`/`location_lon` are already stripped from envelope.
    - P02 only reads the pre-masked `location_geohash` and stores precision metadata.
- [ ] **Retention policy attachment**:
  - Lookup `st_retention_policy` by `(band, topic, device_kind)`
  - Attach `retention_policy_id`, `retention_bucket` (STANDARD / SENSITIVE)
  - Note: P02 resolves `retention_policy_id` at write time; retention workers use the stored `retention_policy_id` (no recomputation from band/topic/device_kind).

#### R2.3 Temporal & Circadian

- [ ] From `body.event_time` + `ingested_at` + tenant timezone:
  - `event_time_utc` = normalized from `body.event_time` (or fallback to envelope `ts`)
  - `write_time_utc` = actual UnitOfWork commit timestamp (when P02 writes to DB)
  - `ingested_at` = when envelope hit K0 ingress (pre-PEP, from envelope)
  - `write_lag_ms` = `write_time_utc - event_time_utc` (how long until DB commit)
  - `local_date`, `local_time` = event time in tenant's timezone
  - `day_of_week`, `is_weekend`
  - `time_of_day_bucket` (morning/afternoon/evening/night)
  - `circadian_slot` (e.g., `dinner_window`)
  - `is_backdated` = true if `write_lag_ms > threshold` (e.g., >24h)

#### R2.4 Spatial & Place (Minimal - No Geo Enrichment)

- [ ] From `location_*` in envelope (already processed by hot path):
  - `geohash_6` = copy from `location_geohash` in WAL envelope (already computed/masked by Gate Stage 3)
  - `location_name` = from envelope `body.location_name`
  - `location_type` = from envelope `body.location_type`
- [ ] **Note**: NO geo city lookup, place chain detection, or geofence resolution (those tables don't exist).
  - Defer complex geo enrichment to P09 (Connector Ingestion) if needed.
  - P02 uses pre-computed `location_geohash` from Command Port write.
  - For AMBER/RED bands, raw `location_lat`/`location_lon` are unavailable (already stripped by Gate).

#### R2.5 Social & Relationship Graph (via st_relationships)

- [ ] From `participants` + `st_relationships` + `people` + `households`:
  - `num_participants`
  - `participant_roles` relative to `actor_id` (self / mother / partner / etc.)
  - `has_partner_present`, `has_parent_present`, `is_solo_event`
  - Query `st_relationships` for family graph (SPOUSE_OF, PARENT_OF, CHILD_OF, CARETAKER_OF, SIBLING_OF)
  - **Note**: `st_relationships` was RESTORED in migration 0024 (previously deprecated in 0021)
  - Lookup `people` table for basic person info (33 columns)
  - Lookup `households` table for household membership (35 columns)
  - Derive:
    - `participant_roles_json` (e.g., `{"person_dad": "OWNER", "person_mom": "SPOUSE"}`)
    - `social_context` (nuclear_family / extended_family / friends / work)
    - `social_intimacy` (LOW / MED / HIGH based on relationship type)
  - **Graph scope**: Basic family relationships only (5 types: SPOUSE_OF, PARENT_OF, CHILD_OF, CARETAKER_OF, SIBLING_OF; seeded from migration 0018, extended in 0024).
    - No complex social graph traversal (defer to P06/P19 if needed).

---

### R3 – Build `st_hipp_events` Row (NEW TABLE)

- [ ] Combine:
  - Raw envelope headers + `policy_stamp`
  - Hippocampus DG/CA1 outputs (fingerprints, entities, KG)
  - Temporal, device, social, privacy, affect, salience
  - Leave dedup/cluster columns (CA3 outputs) NULL for P03
- [ ] Map to `st_hipp_events` schema (see migration 0024 below).
- [ ] Use JSON columns for flexible structures:
  - `obligations_json`, `participants_json`, `entities_json`, `kg_triples_json`,
  - `near_duplicates_json`, `salience_reasons_json`, etc.

**Note**: `st_hipp_events` replaces deprecated `st_hipp_store` (migration 0024).

---

### R4 – Storage Write & Event Emission (via Syscalls)

- [ ] **P02 UnitOfWork** (separate from Command Port UnitOfWork):
  - Insert into `st_hipp_events` (enriched hippocampus data)
  - Insert into `st_embedding_queue` (status=PENDING, wal_pos, event_id, attempt_count=0)
  - Update `st_pipeline_processed` (offset tracking for P02 progress)
- [ ] **Event Emission** (via BusDispatcher):
  - Emit `workspace.wm.updated.v1` (working memory update for P04)
  - Emit `core.affect.analyzed.v1` (affect result for P06)
  - Emit `space.resolution.complete.v1` (space result for P07)
  - Emit `embedding.enqueue.v1` (embedding job enqueue for P08)
  - Emit `p02.hippocampus.pattern_separated.v1` (DG fingerprints for P03)
  - Emit `p02.write.complete.v1` (completion signal for observability)
- [ ] **Mark Outbox Complete**:
  - Delete from `st_outbox` (mark_applied) OR update status=COMPLETED
- [ ] **Capability Enforcement**:
  - Use `self.syscalls.hipp_events_upsert()` (capability: `st_hipp_events.write`)
  - Use `self.syscalls.embedding_queue_insert()` (capability: `st_embedding_queue.write`)
  - Use `self.syscalls.pipeline_processed_upsert()` (capability: `st_pipeline_processed.write`)
  - Use `self.syscalls.outbox_emit()` (capability: `st_outbox.write`)

**Architecture Note**:

- Command Port (hot path) writes: `st_wal`, `idem_ledger`, `st_outbox`, `st_receipts`
- P02 (background) writes: `st_hipp_events`, `st_embedding_queue`, `st_pipeline_processed`
- **Separation of concerns**: WAL/idem/receipts are hot-path only; st_hipp_events/st_embedding_queue/st_pipeline_processed are P02-only. `st_outbox` is intentionally shared as the bus backing store.

---

## Draft Module Mapping (P02) — Aligned to Background Processing

| Responsibility              | Module ID | Implementation / Service            | Location / ADR | Notes                                                                                           |
| --------------------------- | --------- | ----------------------------------- | -------------- | ------------------------------------------------------------------------------------------------|
| Parse Outbox & read WAL     | - | **Inline:** `P02EpisodicWrite.handle` + `WalReader` | `k0/pipelines/p02_episodic_write.py` | Dequeue from `st_outbox` (batch 128), read envelope JSON from `st_wal` via `wal_pos`.           |
| P02 idempotency / offset    | - | **Inline:** `P02EpisodicWrite._check_processed` | `k0/pipelines/p02_episodic_write.py` | Check `st_pipeline_processed(pipeline_id='P02_EPISODIC_WRITE', space_id, wal_pos)`; if found, skip enrichment but still mark outbox entry completed to avoid reprocessing loops. |
| DG pattern separation (DG)  | **M01** | **Inline:** `DGService` | `k0/modules/hippocampus/dg_service.py` • [ADR K003.1](../../docs/architecture/decisions-K0/modules/k003.1-dg-pattern-separation.md) | Compute `simhash_hex`, `minhash32` from text + participants + place + time. No neighbor queries, no novelty. Performance: ≤15ms P95. |
| CA3 clustering              | **M03** | *(none in P02)* | `k0/modules/hippocampus/ca3_service.py` • [ADR K003.3](../../docs/architecture/decisions-K0/modules/k003.3-ca3-clustering-service.md) | Implemented in P03 using `st_hipp_events`; P02 leaves dedup/cluster columns NULL.               |
| CA1 semantic projection     | **M02** | **External:** `hippocampus.bridge` or `SemanticProjector` | `k0/modules/hippocampus/ca1_bridge.py` • [ADR K003.2](../../docs/architecture/decisions-K0/modules/k003.2-ca1-semantic-bridge.md) | Extract entities + KG triples; allocate `embedding_id` and prepare embedding job payload.       |
| Affect classification       | **M04** | **Inline:** `AffectService` | `k0/modules/affect/affect_service.py` • [ADR K004.1](../../docs/architecture/decisions-K0/modules/k004.1-tier0-fast-affect.md) | Classify text → valence, arousal, tags, affect_band, band_reasons, model_version. Performance: <70ms P95. |
| Salience scoring            | **M06** | **External:** `SalienceScorer` | `k0/modules/salience/salience_scorer.py` • [ADR K006.1](../../docs/architecture/decisions-K0/modules/k006.1-write-path-salience.md) | Compute write-path salience: 0.50×social_importance + 0.40×affect_intensity + 0.10×recency_score. No novelty. |
| Space resolution            | **M05** | **Inline:** `SpaceResolver` | `k0/modules/space/space_resolver.py` • [ADR K005.1](../../docs/architecture/decisions-K0/modules/k005.1-acl-resolution.md) | Resolve `owner_id`, `co_owners`, `author_role`, `visible_to` (intersection with policy). Performance: <3ms P95. |
| Band-based geo metadata     | **M12** | **External:** `GeoMetadataLookup` | `k0/modules/context/geo_metadata.py` • [ADR K007.5](../../docs/architecture/decisions-K0/modules/k007.5-geo-metadata.md) | Read `location_geohash` from WAL (already masked by Gate). Store geo metadata: `geo_precision_external`, `geo_masking_reason` from `policy_stamp.obligations`. P02 does NOT re-mask. |
| Retention resolution        | **M11** | **External:** `RetentionLookup` | `k0/modules/context/retention_lookup.py` • [ADR K007.4](../../docs/architecture/decisions-K0/modules/k007.4-retention-lookup.md) | Lookup `(band, topic, device_kind)` → `retention_policy_id`, `retention_bucket`.                |
| Device profiling            | **M09** | **External:** `DeviceProfiler` | `k0/modules/context/device_profiler.py` • [ADR K007.2](../../docs/architecture/decisions-K0/modules/k007.2-device-profiler.md) | Read `st_devices` → `device_kind`, `device_os`, `is_primary_device_for_actor`.          |
| Ingress classification      | **M10** | **External:** `IngressClassifier` | `k0/modules/context/ingress_classifier.py` • [ADR K007.3](../../docs/architecture/decisions-K0/modules/k007.3-ingress-classifier.md) | Derive `ingress_channel`, `ingress_source` (e.g. `k1.conversation`).                            |
| Temporal buckets            | **M08** | **External:** `TemporalProfiler` | `k0/modules/context/temporal_profiler.py` • [ADR K007.1](../../docs/architecture/decisions-K0/modules/k007.1-temporal-profiler.md) | Compute `event_time_utc`, `write_time_utc`, `write_lag_ms`, local date/time, `time_of_day_bucket`, `circadian_slot`, `is_backdated`. |
| Minimal spatial fields      | - | **Inline:** in `P02EpisodicWrite` | `k0/pipelines/p02_episodic_write.py` | Copy `location_name`, `location_type`, `location_geohash` → `geohash_6` (or drop for RED band). No city/place_chain/is_home. |
| Social enrichment (family)  | **M07** | **External:** `FamilyGraphResolver` | `k0/modules/social/family_graph_resolver.py` • [ADR K008.1](../../docs/architecture/decisions-K0/modules/k008.1-family-graph-resolver.md) | Use `st_relationships` + `people` + `households` → `participant_roles_json`, `social_context`, `social_intimacy`. |
| Build hippo row             | **M13** | **Inline:** `HippEventsRowBuilder` | `k0/modules/builders/hipp_events_row_builder.py` • [ADR K009.1](../../docs/architecture/decisions-K0/modules/k009.1-hipp-events-builder.md) | Assemble full `st_hipp_events` row from envelope + DG/CA1 + affect + space + temporal + social. |
| Enqueue embedding job       | **M14** | **Inline:** `EmbeddingQueueWriter` | `k0/modules/builders/embedding_queue_writer.py` • [ADR K009.2](../../docs/architecture/decisions-K0/modules/k009.2-embedding-queue-writer.md) | Insert `st_embedding_queue` row (`status='PENDING'`, `attempt_count=0`), tied to `wal_pos` + `event_id`. |
| Commit P02 writes           | - | **Inline:** `HippEventsWriter` / `P02EpisodicWrite._commit` | `k0/pipelines/p02_episodic_write.py` | Single UnitOfWork: insert into `st_hipp_events`, `st_embedding_queue`, `st_pipeline_processed`. |
| Emit downstream events      | - | **Inline:** `EventEmitter` + `syscalls.outbox_emit` | `k0/pipelines/p02_episodic_write.py` | Emit `workspace.wm.updated.v1`, `core.affect.analyzed.v1`, `embedding.enqueue.v1`, `p02.hippocampus.pattern_separated.v1`, `p02.write.complete.v1` into `st_outbox`. |

> **Note**: No "Build WAL entry", no writes to `idem_ledger` or `st_receipts`. Those belong entirely to the Command Port / hot-path pipeline. No `services.geo_resolver` (defer complex geo to P09). No `policy.pii_profiler` (defer full PII detection to P10).

**Module References**:


- **Module Registry**: See [k0/pipelines/k0_architecture_master.md](../../k0/pipelines/k0_architecture_master.md) Part 3.1 for module details (M01-M14)
- **Module ADRs**: See [docs/architecture/decisions-K0/modules/README.md](../../docs/architecture/decisions-K0/modules/README.md) for complete ADR catalog

---

## Storage Schema Design (Step 2 - NEW TABLES REQUIRED)

### Migration 0024: P02 Episodic Write Tables

**Purpose**: Create tables for P02 hippocampus staging and embedding queue. Restore st_relationships for family graph.

**Note**: `st_pipeline_processed` already exists (created in migration 0012 - Pipeline Infrastructure). P02 uses it for idempotency/offset tracking: `(pipeline_id='P02_EPISODIC_WRITE', space_id, wal_pos)`.

**Tables to Create**:

#### 1. `st_hipp_events` (replaces deprecated `st_hipp_store`)

**Purpose**: Hippocampus staging table for P02 enriched events. P03 reads from here for consolidation.

**Schema Column Groups** (estimated 60-70 columns):

- **identity & trace**
  `event_id` (PK), `wal_pos` (FK to st_wal), `cognitive_trace_id`, `tenant_id`, `space_id`, `effective_space_id`, `topic`, `uow_id`

- **integrity**
  `envelope_sha256`, `sig_alg`, `sig_kid`, `idem_key`, `ingested_at`, `clock_skew_ms`

- **policy & visibility**
  `policy_decision`, `policy_band`, `policy_version`, `obligations_json`, `visible_to_json` (final ACL), `visibility_scope` (pattern), `owner_id`, `co_owners_json`, `retention_policy_id`, `retention_bucket`

**Semantics Clarification**:

- `visible_to_json`: Final explicit subject list **after PEP + SpaceResolver** (actual ACL enforcement). E.g. `["person_dad"]`, `["person_dad","person_mom"]`, or `["person_dad","person_mom","person_son1"]`
- `visibility_scope`: High-level **pattern** describing relationship to space defaults (not for ACL). Values: `OWNER_ONLY` (owner only), `SPACE_DEFAULT` (uses space rules), `HOUSEHOLD_ALL` (whole household), `CUSTOM_SUBSET` (arbitrary subset), `EXTERNAL_SHARE` (external principals included).

- **actor & device**
  `actor_id`, `actor_role`, `device_id`, `device_kind`, `device_os`, `ingress_channel`

- **temporal**
  `event_time_utc`, `write_time_utc`, `write_lag_ms`, `local_date`, `local_time`, `day_of_week`, `is_weekend`, `time_of_day_bucket`, `circadian_slot`, `is_backdated`

- **spatial (minimal - no geo enrichment tables)**
  `location_name`, `location_type`, `geohash_6` (from envelope `location_geohash` or computed), `geo_precision_external`, `geo_masking_reason`

- **social (via st_relationships)**
  `participants_json`, `num_participants`, `has_partner_present`, `has_parent_present`, `is_solo_event`, `participant_roles_json`, `social_context`, `social_intimacy`

- **semantic/activity**
  `text`, `text_normalized`, `char_count`, `token_count`, `language`, `activity_type`, `activity_category`, `is_meal`, `is_outing`

- **hippocampus (DG/CA3)**
  `simhash_hex` (64-bit SimHash from DGService), `minhash32` (MinHash signature JSON, 32 permutations), `novelty_score` (NULL in P02, populated by P03), `near_duplicates_json` (NULL in P02), `is_near_duplicate` (NULL in P02), `episode_cluster_id` (NULL in P02), `cluster_confidence` (NULL in P02)

- **embeddings/KG (CA1)**
  `embedding_id` (UUID), `embedding_status` (PENDING/READY/FAILED), `entities_json`, `kg_triples_json`

- **affect/salience**
  `sentiment_score`, `sentiment_label`, `dominant_emotions_json`, `affect_valence`, `affect_arousal`, `affect_band`, `salience_score`, `salience_reasons_json`, `salience_band`

- **ops & versions**
  `ingress_source`, `hippocampus_api_version`, `space_resolver_version`, `created_at`, `updated_at`

**Indexes**:

- PRIMARY KEY (`event_id`)
- FOREIGN KEY (`wal_pos`) REFERENCES `st_wal(wal_pos)`
- INDEX `idx_hipp_events_tenant_time` (`tenant_id`, `event_time_utc`)
- INDEX `idx_hipp_events_space` (`space_id`, `event_time_utc`)
- INDEX `idx_hipp_events_simhash` (`simhash_hex`) -- for P03 novelty queries
- INDEX `idx_hipp_events_embedding` (`embedding_id`)

**Notes**:

- P02 writes to this table (INSERT only, no updates)
- P03 reads from this table (SELECT for novelty/clustering)
- P03 may UPDATE dedup/cluster columns (novelty_score, episode_cluster_id, etc.)
- Retention workers use `event_time_utc + retention_policy_id` for tombstoning

#### 2. `st_embedding_queue` (replaces non-existent `st_embedding_jobs`)

**Purpose**: Queue for P08 vector generation. P02 enqueues, P08 processes.

**Schema**:

```sql
CREATE TABLE st_embedding_queue (
  job_id INTEGER PRIMARY KEY AUTOINCREMENT,
  wal_pos INTEGER NOT NULL,
  event_id TEXT NOT NULL,
  embedding_id TEXT NOT NULL,
  tenant_id TEXT NOT NULL,
  space_id TEXT NOT NULL,
  vector_kind TEXT NOT NULL,  -- e.g., 'memory.body.text'
  model_id TEXT NOT NULL,     -- e.g., 'embed-mini-001'
  priority TEXT NOT NULL,     -- 'NORMAL', 'HIGH', 'LOW'
  status TEXT NOT NULL CHECK(status IN ('PENDING','IN_PROGRESS','READY','FAILED_RETRYABLE','FAILED_PERMANENT')),
  attempt_count INTEGER DEFAULT 0,
  max_attempts INTEGER DEFAULT 5,
  next_attempt_ts INTEGER,
  last_error TEXT,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,
  FOREIGN KEY (wal_pos) REFERENCES st_wal(wal_pos),
  FOREIGN KEY (event_id) REFERENCES st_hipp_events(event_id)
);

CREATE INDEX idx_embedding_queue_status ON st_embedding_queue(status, next_attempt_ts);
CREATE INDEX idx_embedding_queue_event ON st_embedding_queue(event_id);
CREATE INDEX idx_embedding_queue_embedding_id ON st_embedding_queue(embedding_id);
```

**Notes**:

- P02 inserts with `status='PENDING'`, `attempt_count=0`
- P08 polls this table, updates `status='IN_PROGRESS'` → `'READY'` or `'FAILED_*'`
- Exponential backoff: `next_attempt_ts = now + 2^attempt_count * 60` (1min, 2min, 4min, 8min, 16min)
- DLQ: After 5 attempts, status becomes `'FAILED_PERMANENT'`, route to DLQ

#### 3. Restore `st_relationships` (UNDEPRECATE from migration 0021)

**Purpose**: Family graph cache (replicated from Neo4j). Seeds exist in migration 0018.

**Schema** (from migration 0017):

```sql
CREATE TABLE st_relationships (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  household_id TEXT NOT NULL,
  person_id TEXT NOT NULL,
  related_person_id TEXT NOT NULL,
  relationship_type TEXT NOT NULL,  -- 'SPOUSE_OF', 'PARENT_OF', 'CHILD_OF', 'CARETAKER_OF', 'SIBLING_OF' (5 types, extended in 0024)
  properties_json TEXT,             -- e.g., '{"delegated_by": "person_prince_001"}'
  source_version TEXT NOT NULL,     -- e.g., 'migration_0018', 'neo4j_sync_v1.2'
  hydrated_at TEXT NOT NULL,        -- ISO timestamp when cached
  ttl_seconds INTEGER NOT NULL,     -- Cache TTL (3600 = 1 hour)
  FOREIGN KEY (household_id) REFERENCES households(household_id),
  FOREIGN KEY (person_id) REFERENCES people(person_id),
  FOREIGN KEY (related_person_id) REFERENCES people(person_id)
);

CREATE INDEX idx_relationships_household ON st_relationships(household_id);
CREATE INDEX idx_relationships_person ON st_relationships(person_id);
CREATE INDEX idx_relationships_type ON st_relationships(relationship_type);
```

**Notes**:

- Table was created in migration 0017, seeded in 0018, deprecated in 0021 (renamed to `_deprecated_st_relationships`), dropped in 0022.
- **Migration 0024 RESTORES this table** (un-deprecate, recreate from 0017 schema, re-seed from 0018 data).
- Seeds from migration 0018 provide: Prince↔Jeel (SPOUSE_OF), Prince→Sharvi (PARENT_OF), Jeel→Sharvi (PARENT_OF), grandparents→Sharvi (CARETAKER_OF).
- Migration 0024 extends enum to 5 types (CHILD_OF, SIBLING_OF added for future expansion).
- P02 reads from this table for social graph lookup.
- Cache refresh: External sync worker periodically updates from Neo4j (out of scope for P02).

---

## Design Decisions (Locked)

**Dedup / Clustering Split:**

- **P02 responsibility:** Compute fingerprints only (`simhash_hex`, `minhash32`). Write to `st_hipp_events`.
- **P03 responsibility:** Query neighbors in `st_hipp_events`, compute novelty/near-duplicates/clusters, update dedup columns.
- **Rationale:** Write path stays cheap (one-pass, no reads). Global structure decisions moved to P03 (consolidation pipeline).

**Salience:**

- **P02 salience formula:** 0.50 × social_importance + 0.40 × affect_intensity + 0.10 × recency_score (no novelty dependency).
- **P03 refinement:** Optional; P03 may recompute salience using novelty for long-term analytics.

**Geo Enrichment:**

- **P02 approach:** Minimal. Use envelope's `location_geohash` from Command Port write. NO geo city lookup, place chain detection, or geofence resolution (those tables don't exist).
- **Defer to P09:** Complex geo enrichment (city IDs, place chains, geofences) deferred to P09 (Connector Ingestion) if needed.
- **Privacy**: Band-based coordinate minimization using `policy_stamp.obligations` (GREEN=full, AMBER=geohash-6, RED=geohash-4).

**Social Graph:**

- **P02 approach:** Basic family relationships only (5 types: SPOUSE_OF, PARENT_OF, CHILD_OF, CARETAKER_OF, SIBLING_OF) via `st_relationships` table.
- **Scope**: Nuclear + extended family from migration 0018 seeds (Prince, Jeel, Sharvi, grandparents).
- **No complex traversal**: Deep social graph queries deferred to P06 (Learning) or P19 (Personalization) if needed.

---

## Locked Decisions (P02 Integration Points)

### ✅ Embedding queue contract with P08 (statuses, retries, backoff)

**Decision:**

- **P02** only creates an embedding job in `st_embedding_queue` + emits an enqueue event.
- **P08** owns vector generation, retries, and backoff.
- **P03** uses `embedding_id` / `embedding_status` when fanning out into the 6 memory layers.

**Event:** `embedding.enqueue.v1`

```json
{
  "embedding_id": "emb-<uuid>",
  "tenant_id": "family-smith",
  "space_id": "personal:dad",
  "event_id": "evt-<uuid>",
  "vector_kind": "memory.body.text",
  "model_id": "embed-mini-001",
  "priority": "NORMAL",
  "attempt": 0,
  "max_attempt": 5,
  "created_at": "2025-11-10T18:00:11Z"
}
```

**Job table:** `st_embedding_queue` (NEW TABLE - see migration 0024)

- `job_id` (PK, AUTOINCREMENT)
- `wal_pos`, `event_id`, `embedding_id`, `tenant_id`, `space_id`
- `vector_kind`, `model_id`, `priority`
- `status` ∈ `PENDING | IN_PROGRESS | READY | FAILED_RETRYABLE | FAILED_PERMANENT`
- `attempt_count`, `max_attempts`, `next_attempt_ts`
- `last_error`, `created_at`, `updated_at`

**Hipp events fields (`st_hipp_events`):**

- `embedding_id` (UUID)
- `embedding_status` ∈ `PENDING | IN_PROGRESS | READY | FAILED`

**Lifecycle:**

#### P02 (write path)

- Allocates `embedding_id` (UUID).
- Inserts `st_embedding_queue` row with `status='PENDING'`, `attempt_count=0`.
- Emits `embedding.enqueue.v1` event.
- Sets `embedding_status='PENDING'` in `st_hipp_events`.

#### P08 (vector generation pipeline)

- Picks jobs with `status='PENDING'` or `FAILED_RETRYABLE` whose `next_attempt_ts <= now`.
- Sets `status='IN_PROGRESS'`, increments `attempt_count`.
- On success: Stores vector in vec store; sets `status='READY'` and updates `st_hipp_events.embedding_status='READY'`.
- On failure (retryable): `status='FAILED_RETRYABLE'`, compute `next_attempt_ts` by exponential backoff.
- On failure (permanent or max attempts): `status='FAILED_PERMANENT'`, set `embedding_status='FAILED'`.

**Backoff:** attempt 1 → +1 min; attempt 2 → +2 min; attempt 3 → +4 min; attempt 4 → +8 min; attempt 5 → +16 min → FAILED_PERMANENT.

---

### ✅ Retention policy matrix ownership (band × topic × device_kind)

**Decision:**

The retention matrix is policy config, owned by the global policy module, editable only via Control plane. P02/P03 read it; P03 + retention workers enforce it via tombstones.

**Config table:** `st_retention_policy`

- `policy_id` (PK), `band`, `topic`, `device_kind`, `jurisdiction` (opt)
- `retention_bucket` (`STANDARD` / `SENSITIVE` / `EPHEMERAL`)
- `ttl_days`, `min_ttl_days`, `max_ttl_days`
- `updated_by`, `updated_at`

**Tenant overrides (optional):** `st_tenant_retention_override`

- Tenant can shorten `ttl_days` or move to stricter bucket.
- Tenant cannot exceed `max_ttl_days` or downgrade bucket.

**Enforcement (via P03 + retention worker, tombstones):**

- Retention worker finds rows where `now >= event_time + ttl_days`.
- For each: Write tombstone into `st_tombstone` (with `deleted_by=SYSTEM_RETENTION`).
- Mark row tombstoned in relevant stores; emit `TOMBSTONE_APPLIED` event.
- Same mechanism used for DSAR (but `deleted_by=USER_DSAR`).

---

### ✅ P03 update strategy: in-place update `st_hipp_events` vs. separate dedup/cluster tables?

**Decision:**

P02 (write path):

- Inserts hippo row into `st_hipp_events` with full per-event signals + fingerprints (`simhash_hex`, `minhash32`).
- Dedup-related columns initially NULL: `novelty_score`, `near_duplicates_json`, `is_near_duplicate`, `episode_cluster_id`, `cluster_confidence`.

P03 (consolidation/forgetting):

- Treats `st_hipp_events` as its input queue.
- For each hippo row: uses fingerprints + time window to find neighbors; computes dedup/cluster metrics; **updates those columns in `st_hipp_events` in-place**.
- Uses enriched hippo row to write/update 6 memory layers: episodic, semantic, procedural, social, prospective, KG/vec.
- Marks consolidation state and schedules GC per retention matrix.

Optional secondary tables (for history only):

- `st_event_canon_map(event_id, canonical_event_id, created_at, source)`
- `st_event_cluster_history(event_id, cluster_id, assigned_at, confidence)`

Invariant:

- P02: insert-only into `st_hipp_events`.
- P03: allowed to mutate dedup/cluster + state columns in `st_hipp_events` and create/update 6 long-term layers.
- All hard forgetting via tombstones, driven by retention matrix + DSAR.

---

## PipelineProtocol Contract (Step 6 - Implementation Reference)

**File**: `k0/pipelines/p02_episodic_write.py`

```python
from k0.bus import BusMessage
from k0.pipelines.protocol import PipelineContext, PipelineProtocol
from k0.modules.hippocampus.dg_service import DGService
from k0.modules.affect.affect_service import AffectService
from k0.modules.space.space_resolver import SpaceResolver

class P02EpisodicWrite:
    """
    P02 - Episodic Memory Formation (Background Processing)

    Subscribes to: cognitive.memory.write.committed.v1
    Reads from: st_wal (via wal_pos from outbox)
    Writes to: st_hipp_events, st_embedding_queue
    Emits: workspace.wm.updated.v1, core.affect.analyzed.v1, p02.write.complete.v1
    """

    # PipelineProtocol class-level properties
    pipeline_id = "P02_EPISODIC_WRITE"
    contract_version = 1
    declared_topics = ["cognitive.memory.write.committed.v1"]
    concurrency = 1  # Sequential processing
    max_queue = 512
    required_caps = [
        "st_wal.read",                        # Read event from WAL
        "st_hipp_events.write",               # Write hippocampus staging
        "st_embedding_queue.write",           # Enqueue embedding job
        "st_outbox.write",                    # Emit downstream events
        "st_pipeline_processed.read",         # P02 idempotency check
        "st_pipeline_processed.write",        # Record processed offset
        "st_relationships.read",              # Social graph lookup
        "people.read",                        # People directory
        "households.read",                    # Household directory
        "st_devices.read",                    # Device registry for retention matrix
        "st_retention_policy.read",           # Retention policy
    ]

    async def on_startup(self, ctx: PipelineContext) -> None:
        """Initialize pipeline with syscalls, logger, modules"""
        self.syscalls = ctx.syscalls  # Capability-gated storage
        self.logger = ctx.logger
        self.config = ctx.config

        # Initialize inline modules (Pattern 1)
        self._hippocampus_dg = DGService()
        self._affect = AffectService()
        self._space = SpaceResolver()

        self.logger.info("P02_EPISODIC_WRITE started")

    async def on_shutdown(self) -> None:
        """Cleanup resources"""
        self.logger.info("P02_EPISODIC_WRITE shutdown")

    async def handle(self, msg: BusMessage) -> None:
        """
        Process WAL-committed event:
        1. Read from st_wal via wal_pos
        2. Hippocampus DG (SimHash/MinHash)
        3. Affect classification
        4. Space resolution
        5. Write to st_hipp_events
        6. Enqueue embedding job
        7. Emit completion events
        """
        # Implementation in Step 7
        pass
```

**Notes**:

- P02 uses **inline modules** (Pattern 1 from whiteboard), NOT separate pipelines.
- Syscalls provides capability-gated storage access.
- BusDispatcher calls `handle()` after WAL commit event.
- Performance target: <150ms P95 per event, batch 128 events from Outbox.

---

## Status

**Current Phase**: Step 1 Discovery (Dossier Corrected)

### ✅ Cosmetic Improvements (COMPLETED)

- [x] **Terminology consistency**: All references use `simhash_hex` + `minhash32` (verified throughout dossier)
- [x] **SpaceResolver scope clarification**: SpaceResolver narrowed to `owner_id`, `co_owners`, `author_role`, `visible_to` only. Family relationship roles moved to R2.5 Social Graph section.
- [x] **Module naming pattern labels**: Added **Inline:** vs **External:** labels in module mapping table to clearly distinguish Pattern 1 service classes (DGService, AffectService, SpaceResolver, HippEventsRowBuilder, etc.) from external policy/context/api/temporal modules

---

- [x] Step 1: Discovery (this doc) → 📘 Update Master Doc: Part 2.1 (Pipeline Registry) ✅ COMPLETE
- [ ] Step 2: Data design → **CREATE MIGRATION 0024** (st_hipp_events, st_embedding_queue, restore st_relationships)
  - [x] create P02_data_schema.md (data design spec) → `docs/pipelines/P02_data_schema.md` ✅ COMPLETE
  - [x] Create Contract Document for P02 Tables Schema → `k0/contracts/pipelines/P02_tables_schema.yaml` ✅ COMPLETE
  - [x] Write migration SQL file: `k0/contracts/sql/migrations/0024_p02_episodic_write_tables.sql`
  - [x] Apply migration and verify schema
  - [x] 📘 Update Master Doc: Part 5.3 (Storage Contracts)
- [x] Step 3: Module list frozen → 📘 Update Master Doc: Part 3.1 (Module Registry) - COMPLETE (14 modules M01-M14)
- [ ] Step 4: ADRs written → 📘 Update Master Doc: Part 7.1 (ADR Index), Part 2.1, Part 3.1
- [ ] Step 5: Contracts created → 📘 Update Master Doc: Part 5.1 (Contract Registry), Part 7.1
- [ ] Step 6: Pipeline spec YAML → 📘 Update Master Doc: Part 4.1 (Event Topics), Part 4.4 (DAG), Part 5.1
- [ ] Step 7: Modules implemented → ❌ No Master Doc update needed
- [ ] Step 8: Syscalls derived → 📘 Update Master Doc: Part 5.2 (Syscall Matrix), Part 5.4, Part 5.7
- [ ] Step 9: PipelineRunner wired → ❌ No Master Doc update needed
- [ ] Step 10: Kernel integrated → 📘 Update Master Doc: Part 2.1, Part 3.1 (Status → ⚠️ Implementation)
- [ ] Step 11: End-to-end tested → 📘 Update Master Doc: Part 2.1, Part 3.1, Part 6.4, Part 8.1 (Status → ✅ Production)
