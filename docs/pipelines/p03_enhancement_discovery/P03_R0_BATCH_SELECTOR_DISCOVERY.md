# P03 R0 Batch Selector — Registry-Derived Discovery

This document is a code-derived snapshot of the R0 loader contract in [k0/pipelines/p03/phases/r0_batch_selector.py](k0/pipelines/p03/phases/r0_batch_selector.py).

## Metadata

| Field | Value |
| ----- | ----- |
| Pipeline ID | P03 |
| Phase | R0 Batch Selector |
| Source of truth | `get_r0_field_registry_for_discovery()` |
| Grouping source | `get_r0_field_registry_grouped_for_discovery()` |
| Snapshot date | 2026-03-06 |
| Purpose | Describe the actual R0 field-loading contract from code, grouped by signal family and annotated with downstream phase consumers. |

## Scope

- This file covers only the declarative R0 field registry.
- It reflects the SQL select list and default row-to-state mapping owned by `R0_FIELD_SPECS`.
- It does not attempt to restate the whole P03 architecture or the gap auto-resolver internals.

## Special Cases Outside The Registry

These behaviors are still explicit code paths and are not represented as plain one-row field mappings:

- `timestamp`: derived from `conversation_anchor_ms -> event_time_utc -> created_at -> now()`.
- `hipp_event_id`: set from `event_id` in the current schema.
- `intent_label`: derived from `intent_ultrabert` with fallback to `intent_category`.
- `temporal_source`: loaded from the row when present, otherwise inferred from `temporal_resolved_epoch_ms` fallback behavior.

## Family Summary

| Signal Family | Purpose | Consumer Phases |
| ------------- | ------- | --------------- |
| `routing_identity` | Cursoring, batch identity, event identity, trace propagation | `R0`, `R1`, `R2`, `R3`, `R4`, `R6`, `R7`, `R8` |
| `content_semantic` | Raw content, activity labels, semantic classification, NER payload inputs | `R0`, `R2`, `R3`, `R4`, `R8` |
| `embedding_vector` | Embedding presence and vector lookup references | `R0`, `R2`, `R3` |
| `affect_salience` | Affect and salience features used primarily by importance scoring | `R0`, `R1` |
| `social_context` | Participants and relationship context for scoring, KG, and emission | `R0`, `R1`, `R4`, `R8` |
| `spatial_context` | Place and spatial hierarchy inputs for clustering and emission | `R0`, `R2`, `R8` |
| `temporal_context` | Timestamp, temporal reference, extraction-order, and anchor signals | `R0`, `R2`, `R8` |
| `modality_context` | Communication mode and day/time descriptors for downstream outputs | `R0`, `R8` |
| `narrative_cognitive` | Narrative, novelty, identity, and source-trust signals | `R0`, `R1`, `R2`, `R3`, `R4`, `R8` |

## Registry Export Shape

Each field exported by `get_r0_field_registry_for_discovery()` currently exposes:

| Key | Meaning |
| --- | ------- |
| `select_sql` | SQL expression in the generated `SELECT` list |
| `row_key` | Key used to read the raw row value |
| `state_field` | `P03EventState` field populated by the default mapping, if any |
| `default` | Default value used when the row value is `NULL` |
| `has_converter` | Whether the registry applies a typed converter |
| `signal_family` | Grouping dimension for discovery-doc generation |
| `phase_consumers` | Downstream phases expected to consume the loaded signal |

## Grouped Registry Snapshot

### routing_identity

| Row Key | SQL | State Field | Default | Converter | Consumer Phases |
| ------- | --- | ----------- | ------- | --------- | --------------- |
| `event_id` | `event_id` | - | `None` | no | `R0,R1,R2,R3,R4,R6,R7,R8` |
| `wal_pos` | `wal_pos` | - | `None` | no | `R0` |
| `cognitive_trace_id` | `cognitive_trace_id` | `cognitive_trace_id` | `""` | no | `R0,R8` |
| `tenant_id` | `tenant_id` | - | `None` | no | `R0` |
| `space_id` | `space_id` | - | `None` | no | `R0` |
| `topic` | `topic` | `channel_id` | `""` | no | `R0,R8` |

### content_semantic

| Row Key | SQL | State Field | Default | Converter | Consumer Phases |
| ------- | --- | ----------- | ------- | --------- | --------------- |
| `text` | `text` | `content_text` | `""` | no | `R0,R4,R8` |
| `simhash_hex` | `simhash_hex` | `simhash_hex` | `""` | no | `R0,R3` |
| `content_type` | `activity_category as content_type` | `content_type` | `""` | no | `R0,R2,R8` |
| `activity_type` | `activity_type` | `activity_type` | `""` | no | `R0,R2,R4` |
| `activity_type_ultrabert` | `activity_type_ultrabert` | `activity_type_ultrabert` | `""` | no | `R0,R2,R4` |
| `activity_type_confidence` | `activity_type_confidence` | `activity_type_confidence` | `0.0` | yes | `R0,R2` |
| `intent_ultrabert` | `intent_ultrabert` | `intent_ultrabert` | `""` | no | `R0,R4` |
| `intent_confidence` | `intent_confidence` | `intent_confidence` | `0.0` | yes | `R0,R4` |
| `intent_category` | `intent_category` | - | `None` | no | `R0` |
| `ner_entities_json` | `ner_entities_json` | `ner_entities_json` | `"[]"` | no | `R0,R4` |

### embedding_vector

| Row Key | SQL | State Field | Default | Converter | Consumer Phases |
| ------- | --- | ----------- | ------- | --------- | --------------- |
| `embedding_id` | `embedding_id` | `embedding_id` | `""` | no | `R0,R2,R3` |
| `embedding_status` | `embedding_status` | - | `None` | no | `R0` |

### affect_salience

| Row Key | SQL | State Field | Default | Converter | Consumer Phases |
| ------- | --- | ----------- | ------- | --------- | --------------- |
| `sentiment_score` | `sentiment_score` | `sentiment_score` | `0.0` | yes | `R0,R1` |
| `sentiment_label` | `sentiment_label` | `sentiment_label` | `"neutral"` | no | `R0,R1` |
| `emotions_json` | `dominant_emotions_json as emotions_json` | `emotions_json` | `"[]"` | no | `R0,R1` |
| `salience_score` | `salience_score` | `salience_score` | `0.0` | yes | `R0,R1` |
| `salience_band` | `salience_band` | `salience_band` | `""` | no | `R0,R1` |
| `novelty_score` | `novelty_score` | `novelty_score` | `0.0` | yes | `R0,R1,R3` |
| `affect_valence` | `affect_valence` | `affect_valence` | `0.0` | yes | `R0,R1` |
| `affect_arousal` | `affect_arousal` | `affect_arousal` | `0.0` | yes | `R0,R1` |
| `affect_dominance` | `affect_dominance` | `affect_dominance` | `0.0` | yes | `R0,R1` |

### social_context

| Row Key | SQL | State Field | Default | Converter | Consumer Phases |
| ------- | --- | ----------- | ------- | --------- | --------------- |
| `participants_json` | `participants_json` | `participants_json` | `"[]"` | no | `R0,R1,R4` |
| `num_participants` | `num_participants` | `num_participants` | `0` | yes | `R0,R1,R4` |
| `social_context` | `social_context` | `social_context` | `""` | no | `R0,R1,R4` |
| `social_intimacy` | `social_intimacy` | `social_intimacy` | `""` | no | `R0,R1,R4` |
| `is_solo_event` | `is_solo_event` | `is_solo_event` | `None` | no | `R0,R1,R4` |
| `actor_id` | `actor_id` | `actor_id` | `""` | no | `R0,R4` |
| `extracted_relations_json` | `extracted_relations_json` | `extracted_relations_json` | `"[]"` | no | `R0,R4` |
| `participant_relationships_json` | `participant_relationships_json` | `participant_relationships_json` | `"[]"` | no | `R0,R4,R8` |

### spatial_context

| Row Key | SQL | State Field | Default | Converter | Consumer Phases |
| ------- | --- | ----------- | ------- | --------- | --------------- |
| `location_name` | `location_name` | `location_name` | `""` | no | `R0,R2,R8` |
| `location_type` | `location_type` | `location_type` | `""` | no | `R0,R2` |
| `geohash_6` | `geohash_6` | `geohash_6` | `""` | no | `R0,R2` |
| `place_id` | `place_id` | `place_id` | `""` | no | `R0,R2,R8` |
| `location_hierarchy_json` | `location_hierarchy_json` | `location_hierarchy_json` | `"[]"` | no | `R0,R2,R8` |
| `spatial_context_json` | `spatial_context_json` | `spatial_context_json` | `"{}"` | no | `R0,R2,R8` |

### temporal_context

| Row Key | SQL | State Field | Default | Converter | Consumer Phases |
| ------- | --- | ----------- | ------- | --------- | --------------- |
| `event_time_utc` | `event_time_utc` | - | `None` | no | `R0,R2` |
| `created_at` | `created_at` | - | `None` | no | `R0` |
| `temporal_json` | `temporal_json` | `temporal_expressions_json` | `"[]"` | no | `R0,R2,R8` |
| `temporal_mentioned_time` | `temporal_mentioned_time` | `temporal_mentioned_time` | `""` | no | `R0,R2,R8` |
| `temporal_resolved_epoch_ms` | `temporal_resolved_epoch_ms` | `temporal_resolved_epoch_ms` | `0.0` | yes | `R0,R2,R8` |
| `temporal_orientation` | `temporal_orientation` | `temporal_orientation` | `""` | no | `R0,R2,R8` |
| `conversation_anchor_ms` | `conversation_anchor_ms` | - | `None` | no | `R0,R2` |
| `temporal_source` | `temporal_source` | - | `None` | no | `R0,R2,R8` |
| `temporal_links_json` | `temporal_links_json` | `temporal_links_json` | `"[]"` | no | `R0,R2,R8` |
| `extraction_sequence` | `extraction_sequence` | `extraction_sequence` | `0` | yes | `R0,R2` |
| `temporal_anchor_json` | `temporal_anchor_json` | `temporal_anchor_json` | `"{}"` | no | `R0,R2,R8` |

### modality_context

| Row Key | SQL | State Field | Default | Converter | Consumer Phases |
| ------- | --- | ----------- | ------- | --------- | --------------- |
| `time_of_day_bucket` | `time_of_day_bucket` | `time_of_day_bucket` | `""` | no | `R0,R8` |
| `circadian_slot` | `circadian_slot` | `circadian_slot` | `""` | no | `R0,R8` |
| `is_weekend` | `is_weekend` | `is_weekend` | `None` | no | `R0,R8` |
| `day_of_week` | `day_of_week` | `day_of_week` | `""` | no | `R0,R8` |
| `ingress_channel` | `ingress_channel` | `ingress_channel` | `""` | no | `R0,R8` |
| `ingress_source` | `ingress_source` | `ingress_source` | `""` | no | `R0,R8` |
| `device_kind` | `device_kind` | `device_kind` | `""` | no | `R0,R8` |

### narrative_cognitive

| Row Key | SQL | State Field | Default | Converter | Consumer Phases |
| ------- | --- | ----------- | ------- | --------- | --------------- |
| `narrative_thread_id` | `narrative_thread_id` | `narrative_thread_id` | `""` | no | `R0,R2,R8` |
| `narrative_arc_position` | `narrative_arc_position` | `narrative_arc_position` | `""` | no | `R0,R2,R8` |
| `narrative_is_goal_event` | `narrative_is_goal_event` | `narrative_is_goal_event` | `False` | yes | `R0,R2,R8` |
| `intent_type` | `intent_type` | `intent_type` | `""` | no | `R0,R4,R8` |
| `goal_context` | `goal_context` | `goal_context` | `""` | no | `R0,R2,R8` |
| `source_type` | `source_type` | `source_type` | `""` | no | `R0,R8` |
| `novelty` | `novelty` | `novelty` | `""` | no | `R0,R1,R8` |
| `elaboration_depth` | `elaboration_depth` | `elaboration_depth` | `""` | no | `R0,R2,R8` |
| `identity_domains_json` | `identity_domains_json` | `identity_domains_json` | `"[]"` | no | `R0,R1,R8` |
| `entity_salience_json` | `entity_salience_json` | `entity_salience_json` | `"{}"` | no | `R0,R4` |
| `k1_signal_version` | `k1_signal_version` | `k1_signal_version` | `"2.0"` | no | `R0,R8` |
| `surprise_level` | `surprise_level` | `surprise_level` | `0.0` | yes | `R0,R1` |
| `identity_relevance` | `identity_relevance` | `identity_relevance` | `0.0` | yes | `R0,R1` |
| `source_reliability` | `source_reliability` | `source_reliability` | `1.0` | yes | `R0,R3,R8` |
| `memory_tier` | `memory_tier` | `memory_tier` | `"routine"` | no | `R0,R1,R8` |

## What This Replaced

This file supersedes older stale claims that R0 was still missing fields such as `narrative_thread_id`, `surprise_level`, `identity_relevance`, `memory_tier`, `source_reliability`, and `elaboration_depth`. Those fields are already in the loader registry and are now documented directly from the code-owned export.
