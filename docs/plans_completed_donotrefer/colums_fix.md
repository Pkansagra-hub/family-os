## Column population check ✅

I ran an exact NULL-coverage scan across the real tables. Here’s what’s populated vs empty in the **current data**.

### `st_epi` (37 rows)

**Populated:** ids, tenant/space, episode_summary/type, start/end_time, primary_location, participants, embeddings, observation_count, confidence, decay, timestamps.
**Empty:** `duration_minutes`, `temporal_bucket`, `day_of_week`, `is_recurring`, `recurrence_pattern`, `location_type`, `cluster_confidence`, `consolidation_cycle_id`, `last_observed_at`, `valid_to`, `merge_cascade_id`.

**Why these st_epi columns are empty (current code paths):**

- `duration_minutes`: only computed when both `start_time_utc` and `end_time_utc` are anchored and ordered; otherwise left NULL to avoid guessing.
- `temporal_bucket`, `day_of_week`: not derived in R2 or `TruthWriteAssembler._build_epi_record_data()`; only `start_time_utc`/`end_time_utc` are set.
- `is_recurring`, `recurrence_pattern`: no recurrence detection in R2 and no fields mapped in truth write assembly.
- `location_type`: set only if `P03EventState.location_type` is populated; R2 reads per-event `location_type`, which is often missing in inputs.
- `cluster_confidence`: computed in `TruthWriteAssembler._build_epi_record_data()` but **not inserted** by `EpisodicLayerWriter._insert()` (the SQL INSERT omits the `cluster_confidence` column).
- `consolidation_cycle_id`, `last_observed_at`, `valid_to`, `merge_cascade_id`: not written by the st_epi writer or any staging updates; only `created_at`, `updated_at`, and `valid_from` are set.

**Populated by (writers):**

- `k0/modules/consolidation/truth_writer/layers/episodic.py`
  - `EpisodicLayerWriter._insert()` writes core fields, summary/type/location/participants, embeddings, and observation_count.
  - `EpisodicLayerWriter._update_reinforce()` appends `source_events_json`, increments `source_event_count` + `observation_count`, and extends time bounds.

**Populated by (algorithms & phases):**

- `k0/pipelines/p03/phases/r2_episodic_integrator.py`
  - Builds `EpisodeCluster` (temporal bounds, participants, activity_type, location hints).
  - Uses `EpisodeSplitter`, `EpisodicDBSCAN`, `EpisodicHDBSCAN`, `CentroidCalculator`, and quality/parameter adjusters.
- `k0/modules/consolidation/algorithms/episodic_dbscan.py` and `episodic_hdbscan.py`
  - Cluster events into episodes using composite distance (semantic + temporal).
- `k0/modules/consolidation/algorithms/text_generators/episodic.py`
  - Generates `embedding_text` and `source_texts_json` for st_epi.
- `k0/pipelines/p03/phase_outputs.py`
  - Defines `EpisodeCluster` structure consumed by staging/writer.

### `st_sem` (121 rows)

**Populated:** ids, pattern_type/name, source_episodes, observation_count, confidence, last_observed_at, embeddings (text/vector/model).
**Empty:** `actor_id`, `supersedes_id`, `pattern_description`, `pattern_attributes_json`, `temporal_regularity`, `temporal_pattern_json`, `embedding_id`, `first_observed_at`, `valid_to`, `merge_cascade_id`.

**Why these st_sem columns are empty (current code paths):**

- `actor_id`: now populated from `P03EventState.actor_id` when available; remains NULL for actor-agnostic patterns.
- `supersedes_id`: set on EVOLVE inserts for the new canonical pattern; legacy EVOLVE updates did not create a new record.
- `pattern_description`, `pattern_attributes_json`: now derived in `TruthWriteAssembler._create_sem_insert()` from pattern type/name, entities, activity, location, sentiment, and intent.
- `temporal_regularity`, `temporal_pattern_json`: now derived from temporal expressions and day/time context when available; remains NULL if no temporal signal is present.
- `embedding_id`: computed in `_create_sem_insert()` and now inserted by `SemanticLayerWriter._insert()` (was previously omitted).
- `first_observed_at`: set in `_create_sem_insert()` and now inserted by `SemanticLayerWriter._insert()` (was previously omitted).
- `valid_to`: now set on ARCHIVE/TOMBSTONE updates; still NULL for active records.
- `merge_cascade_id`: never written by the st_sem writer or any staging updates.

**Populated by (writers):**

- `k0/modules/consolidation/truth_writer/layers/semantic.py`
  - `SemanticLayerWriter._insert()` writes core pattern fields plus embedding fields (`source_texts_json`, `embedding_text`, `embedding_vector`, `embedding_model`) via `TextVectorCoordinator`.
  - `SemanticLayerWriter._update()` action handlers:
    - `REINFORCE` updates confidence, observation_count, and last_observed_at.
    - `EXTEND` appends to `source_episodes_json`.
    - `EVOLVE` flips `is_canonical` and links parent.
    - `ARCHIVE` / `TOMBSTONE` set archival status fields.

**Populated by (algorithms & phases):**

- `k0/modules/consolidation/staging/truth_write_assembler.py`
  - `assemble_sem_writes()` creates st_sem inserts/updates/archives from R3 reconciliation actions (CREATE/REINFORCE/EXTEND/EVOLVE/PRUNE).
  - `_create_sem_insert()` sets `pattern_type`, `pattern_subtype` (via subtype classifier), `pattern_name`, `source_episodes_json`, and timestamps.
  - `assemble_insight_writes()` writes R5 insights with `pattern_type='INSIGHT'` plus semantic scores.
- `k0/modules/consolidation/staging/intent_signal_assembler.py`
  - Routes `LessonSignal` → st_sem `pattern_type='LESSON'` and `EmotionalSignal` → st_sem `pattern_type='EMOTIONAL_TREND'`.
- `k0/modules/consolidation/algorithms/text_generators/semantic.py`
  - Generates `embedding_text` (template) and `source_texts_json` for st_sem.
- `k0/modules/consolidation/dream/intent_signals.py`
  - Defines intent signals and intent→layer mapping (reflect → LESSON, express_feeling → EMOTIONAL_TREND).

### `st_kg_dom` (34 rows)

**Populated:** ids, entity_type/name, attributes, source_episodes, observation_count, confidence, embeddings (text/vector/model).
**Empty:** `aliases_json`, `embedding_id`, `first_mentioned_event_id`, `last_observed_at`, `merged_*`, `milestones_json`, `last_queried_at`.
**Partially empty:** `entity_subtype` (15/34 NULL).

**Why these st_kg_dom columns are empty (current code paths):**

- `aliases_json`: assembled in `_create_entity_insert()` but **not inserted** by `KGLayerWriter._insert_entity()` (INSERT omits `aliases_json`).
- `embedding_id`: set in `_create_entity_insert()` but **not inserted** by `KGLayerWriter._insert_entity()` (only inline text/vector fields are stored).
- `first_mentioned_event_id`: never set in `KGWriteAssembler` or writer paths.
- `last_observed_at`: not written by the st_kg_dom writer; only `created_at`, `updated_at`, and `valid_from` are set.
- `merged_*`: merges are tracked in `st_entity_merges`, but st_kg_dom merge fields are not written in any update path.
- `milestones_json`: only appended in `_update_entity_milestone()` (intent signals); no milestones emitted in current data.
- `last_queried_at`: only updated via `query_count_increment` (intent signals); no query-boost signals in current data.
- `entity_subtype` partial: subtype classifier can return `None` for some entities (no fine-grained subtype inferred).

**Populated by (writers):**

- `k0/modules/consolidation/truth_writer/layers/kg.py`
  - `KGLayerWriter._insert_entity()` writes core entity fields plus embeddings (`source_texts_json`, `embedding_text`, `embedding_vector`, `embedding_model`) via `TextVectorCoordinator`.
  - `KGLayerWriter._update_entity()` handlers:
    - `query_count_increment` → `query_count` + `last_queried_at`.
    - `milestone_append` → appends `milestones_json`.
    - `observation_count_increment` → reinforces `observation_count` + `source_episodes_json`/`aliases_json` merges.
    - `_action` EXTEND/EVOLVE → attribute merge + temporal validity.
    - `ARCHIVE` / `TOMBSTONE` set lifecycle fields.

**Populated by (algorithms & phases):**

- `k0/modules/consolidation/staging/kg_write_assembler.py`
  - `assemble_entity_writes()` maps R4 `KGEntity`/`KGEntityUpdate` outputs to st_kg_dom inserts/updates.
  - `_create_entity_insert()` sets `entity_type`, `entity_subtype`, `canonical_name`, `aliases_json`, `source_episodes_json`, and timestamps.
  - `_create_entity_update()` handles `observation_count_increment` and new aliases/source events.
- `k0/modules/consolidation/algorithms/text_generators/kg_entity.py`
  - Generates `embedding_text` (template) and `source_texts_json` for st_kg_dom entities.
- `k0/modules/consolidation/staging/intent_signal_assembler.py`
  - Routes `MilestoneSignal` → st_kg_dom `milestones_json` append and `QueryBoostSignal` → `query_count` increment.
- `k0/modules/consolidation/dream/intent_signals.py`
  - Defines intent signals and intent→layer mapping (share_news → milestone, query_memory → query boost).

### `st_kg_edges` (207 rows)

**Populated:** ids, source/target ids, relation_type, edge_weight, confidence, co_occurrence_count, observation_count, decay, created/updated, source_algorithm, evidence_event_ids.
**Empty:** `relation_subtype`, `source_episodes_json`, `last_observed_at`, `valid_to`, `merge_cascade_id`, `last_queried_at`, `sentiment_avg`, `evidence_episode_ids`, `inference_chain_json`.
**Partially empty:** `properties_json` (18/207 NULL), `algorithm_params_json` (18/207 NULL).

**Why these st_kg_edges columns are empty (current code paths):**

- `relation_subtype`: never set in `KGWriteAssembler` or `KGLayerWriter` (no subtype inference for edges).
- `source_episodes_json`: assembled in `_create_edge_insert()` but **not inserted** by `KGLayerWriter._insert_edge()` (INSERT omits this column).
- `last_observed_at`: not written by the st_kg_edges writer; only `created_at`/`updated_at` are set.
- `valid_to`: only set on EVOLVE paths; edge updates never set `valid_to_ms`.
- `merge_cascade_id`: never written for edges.
- `last_queried_at`: only updated via query-boost intent signals; none observed in current data.
- `sentiment_avg`: no sentiment aggregation for edges in R4 or enrichers.
- `evidence_episode_ids`: not populated in R4 outputs and not set by KGWriteAssembler; writer just passes through.
- `inference_chain_json`: only populated by transitive-closure enricher; empty when that enricher doesn’t emit it.
- `properties_json` / `algorithm_params_json` partial: only certain enrichers set these; many edges don’t carry enrichment metadata.

**Populated by (writers):**

- `k0/modules/consolidation/truth_writer/layers/kg.py`
  - `KGLayerWriter._insert_edge()` writes edge core fields and GAP-007 provenance fields (`source_algorithm`, `evidence_event_ids`, `algorithm_params_json`, `inference_chain_json`).
  - `KGLayerWriter._update_edge()` handles:
    - `query_count_increment` → `query_count` + `last_queried_at`.
    - `observation_count_increment` → `observation_count` + `co_occurrence_count`.
    - `new_weight` → absolute `edge_weight` (weight normalization).
    - appends evidence arrays and updates `source_algorithm`.
  - `ARCHIVE` / `TOMBSTONE` set lifecycle fields.

**Populated by (algorithms & phases):**

- `k0/pipelines/p03/phases/r4_kg_consolidator.py`
  - Builds `KGEdge`, `KGEdgeUpdate`, and `CausalEdge` from entity co-occurrence and Granger causality.
  - Uses `HebbianLearner`, `GrangerCausalityInference`, and adaptive thresholds for edge weights/confidence.
  - Runs edge enrichment pipeline and emits enriched edges/updates.
- `k0/modules/consolidation/staging/kg_write_assembler.py`
  - `assemble_edge_writes()` maps R4 `KGEdge`/`KGEdgeUpdate`/`CausalEdge` to st_kg_edges inserts/updates.
  - `_create_edge_insert()` sets `relation_type`, `edge_weight`, `confidence_score`, `evidence_event_ids`, and enrichment fields.
  - `_create_edge_update()` applies deltas and normalization updates.
- Edge enrichment algorithms (GAP-007), all under `k0/modules/consolidation/algorithms/edge_enrichers/`:
  - `semantic_similarity.py` (semantic similarity edges)
  - `temporal_proximity.py` (temporal co-occurrence)
  - `contextual.py` (contextual signals)
  - `transitive_closure.py` (closure-based edges)
  - `bayesian_causal.py` (bayesian causal inference)
  - `weight_normalization.py` (normalizes edge weights across a node)
- `k0/modules/consolidation/algorithms/edge_demotion.py`
  - Demotes/archives causal edges based on feedback accuracy and staleness.
- `k0/modules/consolidation/staging/intent_signal_assembler.py`
  - Routes `QueryBoostSignal` → st_kg_edges `query_count` increment.
- `k0/modules/consolidation/dream/intent_signals.py`
  - Defines intent signals and intent→layer mapping (query_memory → query boost).

### `st_social` (25 rows)

**Populated:** ids, relationship_type/label, interaction_count, avg_sentiment, relationship_strength, intimacy_level, first/last interaction, observation_count, confidence, decay, dominant_emotion, source_texts.
**Empty:** `interaction_frequency`, `valid_to`, `merge_cascade_id`.
**Partially empty:** `emotional_role` (4/25 NULL), `canonical_entity_id` (9/25 NULL).

**Why these st_social columns are empty (current code paths):**

- `interaction_frequency`: set to `None` in `TruthWriteAssembler.assemble_social_writes()` and not computed anywhere else.
- `valid_to`: always inserted as `NULL` in `SocialLayerWriter._insert()`; no EVOLVE/close-out path sets it.
- `merge_cascade_id`: never written for st_social.
- `emotional_role` partial: derived in R4 `_extract_social_relationships()` and missing when UltraBERT relation/context signals are weak or absent.
- `canonical_entity_id` partial: only populated when social relationship is linked to a KG entity; many relations have no resolved KG entity mapping.

**Populated by (writers):**

- `k0/modules/consolidation/truth_writer/layers/social.py`
  - `SocialLayerWriter._insert()` writes relationship core fields plus UltraBERT-enriched fields and embeddings (`source_texts_json`, `embedding_text`, `embedding_vector`, `embedding_model`) via `TextVectorCoordinator`.
  - `SocialLayerWriter._update()` action handlers:
    - `REINFORCE` updates strength, interaction_count, sentiment/emotion trajectory fields.
    - `EXTEND` appends `interaction_types_json`.
    - `DECAY` applies decay factor.
    - `ARCHIVE` / `TOMBSTONE` set lifecycle fields.

**Populated by (algorithms & phases):**

- `k0/pipelines/p03/phases/r4_kg_consolidator.py`
  - `_extract_social_relationships()` derives `SocialRelationship` records from UltraBERT relations, sentiment/emotions, participants, and context.
  - Computes relationship_type/subtype, emotional role/valence, phase, modalities, and confidence.
- `k0/modules/consolidation/staging/truth_write_assembler.py`
  - `assemble_social_writes()` maps R4 `SocialRelationship` outputs to st_social inserts.
- `k0/modules/consolidation/algorithms/text_generators/social.py`
  - Generates `embedding_text` (template) and `source_texts_json` for st_social relationships.

### `st_prospective` (12 rows)

**Populated:** ids, type, description, status, inference fields, observation_count, confidence, decay, timestamps, source_texts, embeddings.
**Partially empty:** `target_date` (5/12 NULL).
**Empty:** `supersedes_id`, `valid_to`.

**Why these st_prospective columns are empty (current code paths):**

- `target_date`: only set when intent signals or R5 prospective memories include `deadline_ts`/`trigger_time_ms`; many inputs don’t provide a target.
- `target_time`: no field is set in `TruthWriteAssembler.assemble_prospective_writes()` or `ProspectiveLayerWriter._insert()`; only `target_date` is mapped.
- `supersedes_id`: not set by any prospective writer/update path.
- `valid_to`: never set for intentions; inserts always set `valid_from` only.

**Populated by (writers):**

- `k0/modules/consolidation/truth_writer/layers/prospective.py`
  - `ProspectiveLayerWriter._insert()` writes intention core fields plus embeddings (`source_texts_json`, `embedding_text`, `embedding_vector`, `embedding_model`) via `TextVectorCoordinator`.
  - `ProspectiveLayerWriter._update()` action handlers:
    - `EXTEND` updates goal inference + trigger context.
    - `COMPLETE` marks status completed.
    - `COUNTERFACTUAL` stores CPN output.
    - `ARCHIVE` / `TOMBSTONE` set lifecycle fields.

**Populated by (algorithms & phases):**

- `k0/modules/consolidation/staging/truth_write_assembler.py`
  - `assemble_prospective_writes()` maps R5 `ProspectiveMemory` outputs to st_prospective inserts.
  - `assemble_counterfactual_writes()` writes R5 counterfactual scenarios into st_prospective.
- `k0/modules/consolidation/staging/intent_signal_assembler.py`
  - Routes `ReminderSignal` → st_prospective `intention_type='REMINDER'` and `DecisionSignal` → `intention_type='DECISION'`.
- `k0/modules/consolidation/algorithms/text_generators/prospective.py`
  - Generates `embedding_text` (template) and `source_texts_json` for st_prospective intentions.
- `k0/modules/consolidation/dream/intent_signals.py`
  - Defines intent signals and intent→layer mapping (set_reminder → REMINDER, seek_advice → DECISION).

### `st_procedural`

**Why many st_procedural columns are empty (current code paths):**

- `supersedes_id`, `merge_cascade_id`, `valid_to`: never set in any procedural insert/update path.
- `is_canonical`: only set by `assemble_routine_candidate_writes()`; legacy `assemble_procedural_writes()` does not set it.
- `routine_category`, `temporal_anchor`, `streak_count`, `streak_broken_at`: only present on `RoutineCandidate` outputs; legacy routine writes don’t populate them.
- `day_pattern`, `frequency`, `regularity_score`, `action_sequence_json`, `typical_duration_minutes`: populated only when `RoutineDetector` emits candidates; otherwise remain NULL.
- `observation_count`, `last_observed_at`: only updated on REINFORCE/EXTEND; no updates means they stay NULL.
- `decay_factor`: no decay logic writes it for st_procedural.

**Populated by (writers):**

- `k0/modules/consolidation/truth_writer/layers/procedural.py`
  - `ProceduralLayerWriter._insert()` writes routine core fields plus embeddings (`source_texts_json`, `embedding_text`, `embedding_vector`, `embedding_model`) via `TextVectorCoordinator`.
  - `ProceduralLayerWriter._update()` action handlers:
    - `REINFORCE` updates confidence and `temporal_regularity`.
    - `EXTEND` appends `action_sequence_json`.
    - `ARCHIVE` / `TOMBSTONE` set lifecycle fields.

**Populated by (algorithms & phases):**

- `k0/modules/consolidation/staging/truth_write_assembler.py`
  - `assemble_procedural_writes()` maps legacy R5 routine outputs to st_procedural inserts.
  - `assemble_routine_candidate_writes()` writes GAP-003 `RoutineCandidate` outputs from `RoutineDetector`.
  - `assemble_routine_optimization_writes()` writes R5 routine optimizations (TDL-HCO) into st_procedural.
- `k0/modules/consolidation/algorithms/routine_detector.py`
  - Detects recurring routines from st_epi and emits `RoutineCandidate` objects for st_procedural.
- `k0/modules/consolidation/algorithms/text_generators/procedural.py`
  - Generates `embedding_text` (template) and `source_texts_json` for st_procedural routines.

### `st_observations` (436 rows)

**Fully populated:** `observation_id`, `tenant_id`, `layer`, `record_id`, `observed_at`, `observation_type`, `observation_weight`.
**Empty:** `anchor_time_utc`, `original_temporal_expr` (100% NULL).
**Partially empty (~25% NULL):** sentiment/emotion/salience/modality/physical/social/temporal context fields (each 110/436 NULL).

**Why these st_observations columns are empty (current code paths):**

- `anchor_time_utc`, `original_temporal_expr`: only set when prospective writes attach these fields; most observations come from non-prospective layers and `ObservationContext.from_event()` doesn’t populate them.
- Partially empty context fields: `ObservationContext.from_event()` pulls from `P03EventState`; when upstream event fields (location, temporal buckets, social context, device, salience) are missing, those columns remain NULL.

**Populated by (writers):**

- `k0/modules/consolidation/truth_writer/observation_recorder.py`
  - `ObservationRecorder.record()` inserts st_observations rows for truth-layer INSERT/REINFORCE actions.

**Populated by (algorithms & phases):**

- `k0/modules/consolidation/algorithms/observation_context.py`
  - `ObservationContext.from_event()` maps P03 event context into st_observations fields.
  - `ObservationContext.from_episode_cluster()` supplies minimal context for episode-derived observations.
- Truth layer writers attach context on writes (examples):
  - `k0/modules/consolidation/truth_writer/layers/episodic.py` (`ObservationContext` from cluster/event)
  - `k0/modules/consolidation/truth_writer/layers/semantic.py` (via staged writes)
  - `k0/modules/consolidation/truth_writer/layers/kg.py` (entity/edge writes)
  - `k0/modules/consolidation/truth_writer/layers/social.py` (relationship writes)
  - `k0/modules/consolidation/truth_writer/layers/prospective.py` (intention writes)
- `k0/pipelines/p03/staged_writes.py`
  - `StagedWrite.observation_context` carries context into truth writers for recording.

### `st_hipp_events` (112 rows)

**Fully populated:** most ingestion + emotion + salience fields.
**Empty:** `circadian_slot`, `location_type`, `geohash_6`, `cluster_confidence`, `clustering_version`, `hippocampus_api_version`, `space_resolver_version`, `schema_uri`, truth_match fields, `merge_cascade_id`, `archival_status`, `reconciliation_action`, `best_match_*`, `consolidated_at_ms`.
**Partially empty:** `novelty_score`, `near_duplicates_json`, `is_near_duplicate`, `episode_cluster_id`, `consolidation_*` (12/112 NULL), `device_os` (1/112 NULL).

**Populated by (writers):**

- `k0/modules/builders/hipp_events_row.py`
  - `run()` assembles the full 60–70 column st_hipp_events row from P02 enrichments.
  - Maps identity/integrity/policy/device/temporal/spatial/social/semantic/hippocampus/embeddings/affect groups.
  - Sets CA3 deferred columns (`is_near_duplicate`, `novelty_score`, `episode_cluster_id`, `cluster_confidence`, `clustering_version`) to NULL for P03 to fill.
- `k0/modules/core/hipp_events_writer.py`
  - `run()` writes the assembled row via `context.syscalls.hipp_events_upsert()`.
  - Handles embedding writes to `st_vec` and pipeline tracking in `st_pipeline_processed`.

**Populated by (algorithms & phases):**

- P02 enrichment modules (via M13 builder inputs):
  - M01 pattern separation → `simhash_hex`, `minhash32`
  - M02 semantic projection → `entities_json`, `kg_triples_json`, UltraBERT NER/temporal/safety fields
  - M04 affect analysis → `valence`, `arousal`, `dominant_emotions`, safety band inputs
  - M06 salience scoring → `salience_score`, `salience_reasons`, `salience_band`
  - M07 family graph resolve → participants/roles/social context
  - M08 temporal profile → `event_time_utc`, `local_date`, `circadian_slot`, etc.
  - M09 device profile → `device_kind`, `device_os`
  - M10 ingress classify → activity/intent classifications
  - M11 retention lookup → `retention_policy_id`, `retention_bucket`
  - M12 geo metadata + M15 spatial minimal → `geohash_6`, `location_name`
  - M22 extract_from_cache → `embedding_id`, embedding payload (drives `embedding_status`)
- `k0/pipelines/p03/phases/r6_staging.py`
  - Stages `st_hipp_events` UPDATEs via `st_hipp_events_updates` for P03 consolidation outputs.
  - R2/R3 dedup + clustering outputs flow into these updates (CA3 deferred columns and reconciliation/consolidation fields).

---

## Key takeaways (what’s “wrong”)

1. **`st_observations.anchor_time_utc` + `original_temporal_expr` are 100% empty** → prospective anchor context not being recorded yet.
2. **`st_hipp_events.circadian_slot`, `location_type`, `geohash_6` are all empty** → temporal/physical enrichment not flowing.
3. **`st_kg_edges.sentiment_avg`, `inference_chain_json`, `evidence_episode_ids` are empty** → evidence tracking incomplete.
4. **`st_sem.pattern_description` and `pattern_attributes_json` are empty** → semantic detail not materialized.

If you want, I can **generate a clean report** (grouped by table with percent-null and examples) or drill into one table to identify the exact writer that’s skipping those columns.

---
