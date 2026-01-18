# K0 Memory Tables Export

**Generated**: 2026-01-15 22:27:40
**Database**: k0_kernel

## Table of Contents

- [Episodic Memory (Hippocampus)](#episodic-memory-hippocampus)
- [Semantic Memory (Knowledge Graph)](#semantic-memory-knowledge-graph)
- [Social Memory](#social-memory)
- [Procedural Memory](#procedural-memory)
- [Prospective Memory](#prospective-memory)
- [Learning & Feedback](#learning-&-feedback)
- [Entity Resolution](#entity-resolution)
- [Pipeline State](#pipeline-state)
- [Infrastructure](#infrastructure)
- [Core Tables](#core-tables)

## Summary

| Layer | Table | Row Count |
|-------|-------|-----------|
| Episodic Memory (Hippocampus) | `st_hipp_events` | 56 |
| Episodic Memory (Hippocampus) | `st_epi` | 8 |
| Episodic Memory (Hippocampus) | `st_vec` | 56 |
| Episodic Memory (Hippocampus) | `st_embedding_queue` | 0 |
| Semantic Memory (Knowledge Graph) | `st_kg_dom` | 73 |
| Semantic Memory (Knowledge Graph) | `st_kg_edges` | 4 |
| Semantic Memory (Knowledge Graph) | `st_sem` | 66 |
| Social Memory | `st_social` | 22 |
| Social Memory | `st_relationships` | 0 |
| Social Memory | `st_anchors` | 0 |
| Social Memory | `st_anchor_observations` | 0 |
| Procedural Memory | `st_procedural` | 0 |
| Prospective Memory | `st_prospective` | 9 |
| Learning & Feedback | `st_learning_queue` | 18 |
| Learning & Feedback | `st_learned_weights` | 0 |
| Learning & Feedback | `st_learned_weights_history` | 0 |
| Learning & Feedback | `st_feedback_signals` | 0 |
| Learning & Feedback | `st_feedback_quarantine` | 0 |
| Learning & Feedback | `st_decay_feedback` | 0 |
| Learning & Feedback | `st_golden_dataset_pairs` | 0 |
| Entity Resolution | `st_entity_merges` | 0 |
| Entity Resolution | `st_entity_resolutions` | 0 |
| Entity Resolution | `st_pruned_entities` | 0 |
| Pipeline State | `st_offsets` | 1 |
| Pipeline State | `st_pipeline_status` | 0 |
| Pipeline State | `st_pipeline_watermarks` | 0 |
| Pipeline State | `st_pipeline_processed` | 4,952 |
| Pipeline State | `st_consolidation_audit` | 0 |
| Infrastructure | `st_devices` | 2 |
| Infrastructure | `st_device_keys` | 2 |
| Infrastructure | `st_acl` | 0 |
| Infrastructure | `st_retention_policy` | 0 |
| Infrastructure | `st_outbox` | 132 |
| Infrastructure | `st_dlq` | 0 |
| Infrastructure | `st_wal` | 6,982 |
| Infrastructure | `st_receipts` | 6,982 |
| Infrastructure | `st_validation_results` | 0 |
| Infrastructure | `st_archive_manifest` | 0 |
| Infrastructure | `st_obligation_log` | 0 |
| Infrastructure | `st_crdt_merge_log` | 0 |
| Infrastructure | `st_mcts_decisions` | 0 |
| Infrastructure | `st_mcts_shadow_log` | 0 |
| Infrastructure | `idem_ledger` | 6,982 |
| Core Tables | `households` | 0 |
| Core Tables | `people` | 0 |
| **TOTAL** | | **26,347** |

## Episodic Memory (Hippocampus)

### st_hipp_events

**Row Count**: 56

**Schema**:
```
column_name         |     data_type     | is_nullable 
-----------------------------+-------------------+-------------
 event_id                    | text              | NO
 wal_pos                     | bigint            | NO
 cognitive_trace_id          | text              | NO
 tenant_id                   | text              | NO
 space_id                    | text              | NO
 effective_space_id          | text              | YES
 topic                       | text              | NO
 uow_id                      | text              | YES
 schema_version              | text              | NO
 envelope_sha256             | text              | NO
 sig_alg                     | text              | NO
 sig_kid                     | text              | NO
 idem_key                    | text              | NO
 ingested_at                 | bigint            | NO
 clock_skew_ms               | integer           | YES
 policy_decision             | text              | NO
 policy_band                 | text              | NO
 policy_version              | text              | NO
 obligations_json            | text              | YES
 visible_to_json             | text              | YES
 visibility_scope            | text              | YES
 owner_id                    | text              | NO
 co_owners_json              | text              | YES
 retention_policy_id         | text              | NO
 retention_bucket            | text              | NO
 actor_id                    | text              | NO
 actor_role                  | text              | YES
 device_id                   | text              | NO
 device_kind                 | text              | NO
 device_os                   | text              | YES
 ingress_channel             | text              | YES
 event_time_utc              | bigint            | NO
 write_time_utc              | bigint            | NO
 write_lag_ms                | integer           | YES
 local_date                  | text              | YES
 local_time                  | text              | YES
 day_of_week                 | text              | YES
 is_weekend                  | boolean           | YES
 time_of_day_bucket          | text              | YES
 circadian_slot              | text              | YES
 is_backdated                | boolean           | YES
 created_at                  | bigint            | NO
 location_name               | text              | YES
 location_type               | text              | YES
 geohash_6                   | text              | YES
 geo_precision_external      | text              | YES
 geo_masking_reason          | text              | YES
 participants_json           | text              | YES
 num_participants            | integer           | YES
 has_partner_present         | boolean           | YES
 has_parent_present          | boolean           | YES
 is_solo_event               | boolean           | YES
 participant_roles_json      | text              | YES
 social_context              | text              | YES
 social_intimacy             | text              | YES
 text                        | text              | YES
 text_normalized             | text              | YES
 char_count                  | integer           | YES
 token_count                 | integer           | YES
 language                    | text              | YES
 activity_type               | text              | YES
 activity_category           | text              | YES
 is_meal                     | boolean           | YES
 is_outing                   | boolean           | YES
 ingress_source              | text              | YES
 simhash_hex                 | text              | NO
 minhash32                   | text              | NO
 novelty_score               | double precision  | YES
 near_duplicates_json        | text              | YES
 is_near_duplicate           | boolean           | YES
 episode_cluster_id          | text              | YES
 cluster_confidence          | double precision  | YES
 clustering_version          | text              | YES
 embedding_id                | text              | NO
 embedding_status            | text              | NO
 entities_json               | text              | YES
 kg_triples_json             | text              | YES
 sentiment_score             | double precision  | YES
 sentiment_label             | text              | YES
 dominant_emotions_json      | text              | YES
 affect_valence              | double precision  | YES
 affect_arousal              | double precision  | YES
 affect_band                 | text              | YES
 salience_score              | double precision  | NO
 salience_reasons_json       | text              | YES
 salience_band               | text              | YES
 hippocampus_api_version     | text              | YES
 space_resolver_version      | text              | YES
 schema_uri                  | text              | YES
 updated_at                  | bigint            | NO
 consolidation_status        | text              | YES
 consolidation_cycle_id      | text              | YES
 consolidated_at             | bigint            | YES
 reconciliation_decision     | text              | YES
 truth_match_id              | text              | YES
 truth_match_similarity      | double precision  | YES
 ner_entities_json           | text              | YES
 temporal_json               | text              | YES
 intent_category             | text              | YES
 ingress_category            | text              | YES
 ultrabert_version           | text              | YES
 merge_cascade_id            | character varying | YES
 archival_status             | text              | YES
 reconciliation_action       | text              | YES
 best_match_id               | text              | YES
 best_match_layer            | text              | YES
 similarity_score            | double precision  | YES
 confidence                  | double precision  | YES
 reconciliation_reason       | text              | YES
 consolidated_at_ms          | bigint            | YES
 extracted_relations_json    | text              | YES
 safety_familyos_band        | text              | YES
 safety_familyos_subcategory | text              | YES
 effective_safety_band       | text              | YES
 nli_label                   | text              | YES
 nli_confidence              | double precision  | YES
 sentiment_confidence        | double precision  | YES
 activity_type_ultrabert     | text              | YES
 activity_type_confidence    | double precision  | YES
 intent_ultrabert            | text              | YES
 intent_confidence           | double precision  | YES
(121 rows)
```

**Sample Data** (showing 10 of 56 rows):
```

```

---

### st_epi

**Row Count**: 8

**Schema**:
```
column_name       |     data_type     | is_nullable 
------------------------+-------------------+-------------
 episode_id             | text              | NO
 tenant_id              | text              | NO
 space_id               | text              | NO
 version                | integer           | NO
 supersedes_id          | text              | YES
 is_canonical           | boolean           | YES
 episode_summary        | text              | YES
 episode_type           | text              | YES
 start_time_utc         | bigint            | NO
 end_time_utc           | bigint            | NO
 duration_minutes       | integer           | YES
 temporal_bucket        | text              | YES
 day_of_week            | text              | YES
 is_recurring           | boolean           | YES
 recurrence_pattern     | text              | YES
 source_events_json     | text              | NO
 source_event_count     | integer           | NO
 primary_location       | text              | YES
 location_type          | text              | YES
 participants_json      | text              | YES
 participant_count      | integer           | YES
 embedding_id           | text              | YES
 cluster_id             | text              | YES
 cluster_confidence     | double precision  | YES
 consolidation_cycle_id | text              | YES
 observation_count      | integer           | YES
 confidence_score       | double precision  | YES
 last_observed_at       | bigint            | YES
 decay_factor           | double precision  | YES
 archival_status        | text              | YES
 created_at             | bigint            | NO
 updated_at             | bigint            | NO
 valid_from             | bigint            | NO
 valid_to               | bigint            | YES
 merge_cascade_id       | character varying | YES
 source_texts_json      | text              | YES
 embedding_text         | text              | YES
 embedding_vector       | bytea             | YES
 embedding_model        | text              | YES
(39 rows)
```

**Data**:
```
episode_id            |  tenant_id  |  space_id  | version | supersedes_id | is_canonical |      episode_summary       | episode_type | start_time_utc | end_time_utc  | duration_minutes | temporal_bucket | day_of_week | is_recurring | recurrence_pattern |                                                                                                                                                                                                                                                                                                                        source_events_json                                                                                                                                                                                                                                                                                                                        | source_event_count |  primary_location  | location_type |                                      participants_json                                       | participant_count |             embedding_id             |           cluster_id            | cluster_confidence | consolidation_cycle_id | observation_count | confidence_score | last_observed_at | decay_factor | archival_status |  created_at   |  updated_at   |  valid_from   | valid_to | merge_cascade_id | source_texts_json | embedding_text | embedding_vector | embedding_model  
---------------------------------+-------------+------------+---------+---------------+--------------+----------------------------+--------------+----------------+---------------+------------------+-----------------+-------------+--------------+--------------------+------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+--------------------+--------------------+---------------+----------------------------------------------------------------------------------------------+-------------------+--------------------------------------+---------------------------------+--------------------+------------------------+-------------------+------------------+------------------+--------------+-----------------+---------------+---------------+---------------+----------+------------------+-------------------+----------------+------------------+------------------
 weak-e8e719820b3043fa9427d2892c | tenant-test | space-home |       1 |               | t            | Routine at Home            | routine      |  1768537469000 | 1768537472000 |                  |                 |             |              |                    | ["c0326faa-4a8c-4050-9f86-4d1bd5677fd9", "aaf6b89a-6e1e-44ca-8fc8-f209a5a23d08", "6cbc22a6-66dd-4b55-8814-dc1893f2c75f", "c474b007-99c7-4d97-be4c-f693cfe7c73b", "f1803fb3-5a72-4d29-91ce-845d32a403f2", "200177cb-55f6-4d4b-9ad3-45e164bae4ba", "42062809-af31-494b-9a1f-e4b2bf90ee21", "4e9c3301-e997-4bb4-97ce-5cf7ca6f6bbb", "f1f2bd40-62a5-45fb-835d-7a7305ff65e7", "25b20eca-893f-4ce2-b96d-e643ac0da540", "24ecb90e-98cb-40cf-9a5e-854be3a9ac6b", "9503ffdc-f768-425f-a2c0-4761c5499c95", "06172f82-8e8d-49e7-9047-337a3f542ebc", "064ff8f1-bcc2-4cb4-b0cd-c0e8be10361c", "b97d985b-9181-491f-9306-ce15f718ab0f", "19a33cd5-267e-4546-96e2-ed9b5a1e5df6"] |                 16 | Home               |               | ["Alex", "Chris", "Emma", "Jake", "Kevin", "Maria", "Mom", "Sofia", "Tom"]                   |                 9 | aa489b33-68ae-4d5c-a9b0-3a9277278a3b | weak-e8e719820b3043fa9427d2892c | 0.9905267468455258 |                        |                 1 |              0.5 |                  |            1 | ACTIVE          | 1768537490615 | 1768537490615 | 1768537490615 |          |                  |                   |                |                  | ultrabert-v2.1.0
 weak-5cc8ce7be5e04fbda3d3966c26 | tenant-test | space-home |       1 |               | t            | Work at Starbucks Downtown | work         |  1768537469000 | 1768537471000 |                  |                 |             |              |                    | ["fd987ef5-cd1f-4aa0-ba4b-248ad3130db1", "f2f6fb5c-1bd5-4a60-bd15-77f151b1a07c", "cb298f1e-4ff5-4599-acbd-113ff0b952d3", "156562eb-446d-4650-be23-17d48f221931", "ed8c6ab6-db0b-4b39-8026-91102bba6506", "a5139b36-eceb-4845-bb6a-53fd68f89bf5", "3b0376a3-e949-450e-aff0-b7e873b67650", "2bc3990d-1856-4cf2-8db5-bc18dfc420c3", "48ee259d-cbc3-43b7-83bc-5dc5a65154c6", "28a49aa7-0f30-45f4-a33a-2e79afd813a2"]                                                                                                                                                                                                                                                 |                 10 | Starbucks Downtown |               | ["Alex", "Andrew Ng", "Chris", "Jennifer", "John", "Lisa", "Mike", "Rachel", "Sam", "Sarah"] |                10 | b285b2b5-407f-4a2a-9596-baeb5e8de19e | weak-5cc8ce7be5e04fbda3d3966c26 | 0.9947591234164959 |                        |                 1 |              0.5 |                  |            1 | ACTIVE          | 1768537490615 | 1768537490615 | 1768537490615 |          |                  |                   |                |                  | ultrabert-v2.1.0
 weak-d765f05914514cd69172f89b6c | tenant-test | space-home |       1 |               | t            | Work at Home               | work         |  1768537469000 | 1768537472000 |                  |                 |             |              |                    | ["fee16c26-9a44-4124-9b85-cb0782d2416f", "9cf28272-dd70-49d7-8a84-8ef4900fce4c", "f8807d34-659d-4fac-98b1-cc389900a73d", "2e70e513-f36e-417c-9dc3-db59d7cd0e9c", "135f16c4-e742-4244-9b51-0e392b298224", "3d421163-a6fb-4455-b001-8b8a57f5ecff"]                                                                                                                                                                                                                                                                                                                                                                                                                 |                  6 | Home               |               | ["David", "Emma", "Jake", "Sarah", "Team"]                                                   |                 5 | a1256757-e2be-42d3-abed-5f92c794f9f8 | weak-d765f05914514cd69172f89b6c | 0.9949503856463546 |                        |                 1 |              0.5 |                  |            1 | ACTIVE          | 1768537490615 | 1768537490615 | 1768537490615 |          |                  |                   |                |                  | ultrabert-v2.1.0
 weak-482df092a3434c4a817a39e14e | tenant-test | space-home |       1 |               | t            | Routine at Home            | routine      |  1768537470000 | 1768537472000 |                  |                 |             |              |                    | ["5d1504b0-c807-490a-b0c9-964e219faca3", "d0458fd9-3821-4fa6-93eb-4db070b2ff90", "feb734b6-c304-4713-ba80-ec99a8031599", "99221dd6-8664-4a57-991f-bf189a60c41d", "75b706da-fc8f-4fc3-a752-865cd4398e59"]                                                                                                                                                                                                                                                                                                                                                                                                                                                         |                  5 | Home               |               | ["Dr. Johnson", "Dr. Smith"]                                                                 |                 2 | 217806fe-bc0e-4bc2-85d1-af8aae72c63d | weak-482df092a3434c4a817a39e14e | 0.9937070558648694 |                        |                 1 |              0.5 |                  |            1 | ACTIVE          | 1768537490615 | 1768537490615 | 1768537490615 |          |                  |                   |                |                  | ultrabert-v2.1.0
 weak-8a248b42ac4b47c886c556d865 | tenant-test | space-home |       1 |               | t            | Routine at Home            | routine      |  1768537470000 | 1768537472000 |                  |                 |             |              |                    | ["f7a41a92-312d-49e4-b77c-ed689114a889", "258c7dc9-b6dd-46e9-858f-675500879df1", "f21051c2-4ee8-4e5d-8164-44058c0a630a", "3974c8b8-7008-4a07-8c6e-a1f937d7a978", "d6cc87ea-d6fc-4321-9852-0230f8822496", "e68f10ba-3379-4f1d-9741-f03120147160"]                                                                                                                                                                                                                                                                                                                                                                                                                 |                  6 | Home               |               | ["Emma", "Jake", "Rachel"]                                                                   |                 3 | 276d7864-3960-4fd7-ab6d-3814553acb6a | weak-8a248b42ac4b47c886c556d865 | 0.9930671904712473 |                        |                 1 |              0.5 |                  |            1 | ACTIVE          | 1768537490615 | 1768537490615 | 1768537490615 |          |                  |                   |                |                  | ultrabert-v2.1.0
 weak-17509ddd3f644ac88aaa38bcb0 | tenant-test | space-home |       1 |               | t            | Routine at Home            | routine      |  1768537470000 | 1768537472000 |                  |                 |             |              |                    | ["c9ca2793-eaa2-4c9f-9463-9d8d29d575ed", "d2a159ce-6434-47dc-a1cb-70c7e7ece866", "5b0f71f3-8611-4b94-96ed-28983614fe5d", "01bb7622-b3af-44d5-8bf0-9f4a3f8be996", "e38d9d59-5926-4d9b-a0c6-f98f1c8f5158", "2ff88357-adf8-4a2f-96f7-97c4dad89c83", "136ca894-317f-4fe6-b3c1-3796796fde5c", "0b34ae98-cfbd-43e1-aeb6-a02c7b9eb31a"]                                                                                                                                                                                                                                                                                                                                 |                  8 | Home               |               | ["David", "Jennifer", "John", "Mike"]                                                        |                 4 | 1457b088-457c-4fc7-8ade-0a1ea146630b | weak-17509ddd3f644ac88aaa38bcb0 | 0.9878504500331318 |                        |                 1 |              0.5 |                  |            1 | ACTIVE          | 1768537490615 | 1768537490615 | 1768537490615 |          |                  |                   |                |                  | ultrabert-v2.1.0
 weak-f4ac23b9ba9940e484725a4ede | tenant-test | space-home |       1 |               | t            | Routine at Home            | routine      |  1768537471000 | 1768537471000 |                  |                 |             |              |                    | ["7b730108-9882-40e8-957d-498eb376c83d", "7869ff59-50b2-4f61-9e12-7740234bd24b", "2d7705ff-df15-42a8-9323-065e6869ee23"]                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |                  3 | Home               |               | ["Emma", "Mom"]                                                                              |                 2 | ab8e6ce8-e4e1-4543-8a2f-b6de16e45954 | weak-f4ac23b9ba9940e484725a4ede | 0.9973619390068097 |                        |                 1 |              0.5 |                  |            1 | ACTIVE          | 1768537490615 | 1768537490615 | 1768537490615 |          |                  |                   |                |                  | ultrabert-v2.1.0
 962bcb7d92f3475c9c230ec9ef      | tenant-test | space-home |       1 |               | t            | Milestone at Starbucks     | milestone    |  1768537472000 | 1768537472000 |                  |                 |             |              |                    | ["d96c6408-d41e-4def-8df4-170b43010d62", "14a17d97-aaae-481a-95c2-c1022d2ea4d5"]                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |                  2 | Starbucks          |               | ["Jake", "Rachel", "Sophie", "Tom"]                                                          |                 4 | 48c3e195-16dd-47e8-829b-df37271f36bb | 962bcb7d92f3475c9c230ec9ef      | 0.9994123494989546 |                        |                 1 |              0.5 |                  |            1 | ACTIVE          | 1768537490615 | 1768537490615 | 1768537490615 |          |                  |                   |                |                  | ultrabert-v2.1.0
(8 rows)
```

---

### st_vec

**Row Count**: 56

**Schema**:
```
column_name     |     data_type     | is_nullable 
--------------------+-------------------+-------------
 embedding_id       | text              | NO
 event_id           | text              | NO
 tenant_id          | text              | NO
 space_id           | text              | NO
 vector             | bytea             | NO
 vector_dim         | integer           | NO
 model_id           | text              | NO
 status             | text              | NO
 cognitive_trace_id | text              | YES
 created_at         | bigint            | NO
 updated_at         | bigint            | NO
 faiss_id           | integer           | YES
 indexed_at         | bigint            | YES
 merge_cascade_id   | character varying | YES
(14 rows)
```

**Sample Data** (showing 10 of 56 rows):
```

```

---

### st_embedding_queue

**Row Count**: 0

**Schema**:
```
column_name   | data_type | is_nullable 
-----------------+-----------+-------------
 job_id          | bigint    | NO
 wal_pos         | bigint    | NO
 event_id        | text      | NO
 embedding_id    | text      | NO
 tenant_id       | text      | NO
 space_id        | text      | NO
 vector_kind     | text      | NO
 model_id        | text      | NO
 priority        | text      | NO
 status          | text      | NO
 attempt_count   | integer   | NO
 max_attempts    | integer   | NO
 next_attempt_ts | bigint    | YES
 last_error      | text      | YES
 vector_json     | text      | YES
 created_at      | bigint    | NO
 updated_at      | bigint    | NO
(17 rows)
```

*No data*

---

## Semantic Memory (Knowledge Graph)

### st_kg_dom

**Row Count**: 73

**Schema**:
```
column_name        |     data_type     | is_nullable 
--------------------------+-------------------+-------------
 entity_id                | text              | NO
 tenant_id                | text              | NO
 space_id                 | text              | NO
 version                  | integer           | NO
 supersedes_id            | text              | YES
 is_canonical             | boolean           | YES
 entity_type              | text              | NO
 entity_subtype           | text              | YES
 canonical_name           | text              | NO
 aliases_json             | text              | YES
 attributes_json          | text              | YES
 embedding_id             | text              | YES
 source_episodes_json     | text              | YES
 first_mentioned_event_id | text              | YES
 observation_count        | integer           | YES
 confidence_score         | double precision  | YES
 last_observed_at         | bigint            | YES
 decay_factor             | double precision  | YES
 archival_status          | text              | YES
 created_at               | bigint            | NO
 updated_at               | bigint            | NO
 valid_from               | bigint            | NO
 valid_to                 | bigint            | YES
 merged_into              | character varying | YES
 merged_at                | bigint            | YES
 merged_by                | character varying | YES
 query_count              | integer           | NO
 last_queried_at          | bigint            | YES
 milestones_json          | text              | YES
 source_texts_json        | text              | YES
 embedding_text           | text              | YES
 embedding_vector         | bytea             | YES
 embedding_model          | text              | YES
(33 rows)
```

**Data**:
```
entity_id                |  tenant_id  |  space_id  | version | supersedes_id | is_canonical |  entity_type  | entity_subtype |   canonical_name    |             aliases_json             | attributes_json | embedding_id |                                                                                                                                                                           source_episodes_json                                                                                                                                                                           | first_mentioned_event_id | observation_count |  confidence_score  | last_observed_at | decay_factor | archival_status |  created_at   |  updated_at   |  valid_from   | valid_to | merged_into | merged_at | merged_by | query_count | last_queried_at |                                                                                                                                                                                                                                                                                                                                                                                                                                                   milestones_json                                                                                                                                                                                                                                                                                                                                                                                                                                                   | source_texts_json | embedding_text | embedding_vector | embedding_model  
-----------------------------------------+-------------+------------+---------+---------------+--------------+---------------+----------------+---------------------+--------------------------------------+-----------------+--------------+--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+--------------------------+-------------------+--------------------+------------------+--------------+-----------------+---------------+---------------+---------------+----------+-------------+-----------+-----------+-------------+-----------------+---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+-------------------+----------------+------------------+------------------
 cluster_LOCATION_city sports complex    | tenant-test | space-home |       1 |               | t            | LOCATION      |                | City Sports Complex | ['City Sports Complex']              |                 |              | ["c0326faa-4a8c-4050-9f86-4d1bd5677fd9"]                                                                                                                                                                                                                                                                                                                                 |                          |                 1 | 0.8500000000000001 |                  |            1 | ACTIVE          | 1768537490617 | 1768537490617 | 1768537490617 |          |             |           |           |           0 |                 |                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |                   |                |                  | ultrabert-v2.1.0
 cluster_PERSON_emma                     | tenant-test | space-home |       1 |               | t            | PERSON        |                | Emma                | ['Emma']                             |                 |              | ["f1f2bd40-62a5-45fb-835d-7a7305ff65e7", "6cbc22a6-66dd-4b55-8814-dc1893f2c75f", "258c7dc9-b6dd-46e9-858f-675500879df1", "c474b007-99c7-4d97-be4c-f693cfe7c73b", "7869ff59-50b2-4f61-9e12-7740234bd24b", "aaf6b89a-6e1e-44ca-8fc8-f209a5a23d08", "c0326faa-4a8c-4050-9f86-4d1bd5677fd9", "06172f82-8e8d-49e7-9047-337a3f542ebc", "b97d985b-9181-491f-9306-ce15f718ab0f"] |                          |                 9 | 0.8499999999999999 |                  |            1 | ACTIVE          | 1768537490617 | 1768537490617 | 1768537490617 |          |             |           |           |           0 |                 |                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |                   |                |                  | ultrabert-v2.1.0
 cluster_LOCATION_lincoln school         | tenant-test | space-home |       1 |               | t            | LOCATION      |                | Lincoln School      | ['Lincoln School']                   |                 |              | ["aaf6b89a-6e1e-44ca-8fc8-f209a5a23d08", "b97d985b-9181-491f-9306-ce15f718ab0f"]                                                                                                                                                                                                                                                                                         |                          |                 2 | 0.8500000000000001 |                  |            1 | ACTIVE          | 1768537490617 | 1768537490617 | 1768537490617 |          |             |           |           |           0 |                 |                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |                   |                |                  | ultrabert-v2.1.0
 cluster_CONCEPT_fur elise               | tenant-test | space-home |       1 |               | t            | CONCEPT       |                | Fur Elise           | ['Fur Elise']                        |                 |              | ["aaf6b89a-6e1e-44ca-8fc8-f209a5a23d08"]                                                                                                                                                                                                                                                                                                                                 |                          |                 1 |               0.65 |                  |            1 | ACTIVE          | 1768537490617 | 1768537490617 | 1768537490617 |          |             |           |           |           0 |                 |                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |                   |                |                  | ultrabert-v2.1.0
 cluster_LOCATION_home                   | tenant-test | space-home |       1 |               | t            | LOCATION      |                | home                | ['home']                             |                 |              | ["6cbc22a6-66dd-4b55-8814-dc1893f2c75f"]                                                                                                                                                                                                                                                                                                                                 |                          |                 1 |                0.9 |                  |            1 | ACTIVE          | 1768537490617 | 1768537490617 | 1768537490617 |          |             |           |           |           0 |                 |                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |                   |                |                  | ultrabert-v2.1.0
 cluster_PERSON_jake                     | tenant-test | space-home |       1 |               | t            | PERSON        |                | Jake                | ['Jake']                             |                 |              | ["6cbc22a6-66dd-4b55-8814-dc1893f2c75f", "14a17d97-aaae-481a-95c2-c1022d2ea4d5"]                                                                                                                                                                                                                                                                                         |                          |                 2 |               0.85 |                  |            1 | ACTIVE          | 1768537490617 | 1768537490617 | 1768537490617 |          |             |           |           |           0 |                 |                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |                   |                |                  | ultrabert-v2.1.0
 cluster_EVENT_birthday party            | tenant-test | space-home |       1 |               | t            | EVENT         |                | Birthday party      | ['Birthday party', 'birthday party'] |                 |              | ["c474b007-99c7-4d97-be4c-f693cfe7c73b", "42062809-af31-494b-9a1f-e4b2bf90ee21"]                                                                                                                                                                                                                                                                                         |                          |                 2 |                0.9 |                  |            1 | ACTIVE          | 1768537490617 | 1768537490617 | 1768537490617 |          |             |           |           |           0 |                 |                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |                   |                |                  | ultrabert-v2.1.0
 cluster_PERSON_sofia                    | tenant-test | space-home |       1 |               | t            | PERSON        |                | Sofia               | ['Sofia']                            |                 |              | ["c474b007-99c7-4d97-be4c-f693cfe7c73b"]                                                                                                                                                                                                                                                                                                                                 |                          |                 1 |               0.85 |                  |            1 | ACTIVE          | 1768537490617 | 1768537490617 | 1768537490617 |          |             |           |           |           0 |                 |                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |                   |                |                  | ultrabert-v2.1.0
 cluster_ORGANIZATION_chuck e cheese     | tenant-test | space-home |       1 |               | t            | ORGANIZATION  |                | Chuck E Cheese      | ['Chuck E Cheese']                   |                 |              | ["c474b007-99c7-4d97-be4c-f693cfe7c73b"]                                                                                                                                                                                                                                                                                                                                 |                          |                 1 |                0.8 |                  |            1 | ACTIVE          | 1768537490617 | 1768537490617 | 1768537490617 |          |             |           |           |           0 |                 |                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |                   |                |                  | ultrabert-v2.1.0
 cluster_PERSON_john                     | tenant-test | space-home |       1 |               | t            | PERSON        |                | John                | ['John']                             |                 |              | ["fd987ef5-cd1f-4aa0-ba4b-248ad3130db1"]                                                                                                                                                                                                                                                                                                                                 |                          |                 1 |               0.85 |                  |            1 | ACTIVE          | 1768537490617 | 1768537490617 | 1768537490617 |          |             |           |           |           0 |                 |                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |                   |                |                  | ultrabert-v2.1.0
 cluster_PERSON_lisa                     | tenant-test | space-home |       1 |               | t            | PERSON        |                | Lisa                | ['Lisa']                             |                 |              | ["fd987ef5-cd1f-4aa0-ba4b-248ad3130db1"]                                                                                                                                                                                                                                                                                                                                 |                          |                 1 |               0.85 |                  |            1 | ACTIVE          | 1768537490617 | 1768537490617 | 1768537490617 |          |             |           |           |           0 |                 |                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |                   |                |                  | ultrabert-v2.1.0
 cluster_PERSON_mike                     | tenant-test | space-home |       1 |               | t            | PERSON        |                | Mike                | ['Mike']                             |                 |              | ["fd987ef5-cd1f-4aa0-ba4b-248ad3130db1", "cb298f1e-4ff5-4599-acbd-113ff0b952d3"]                                                                                                                                                                                                                                                                                         |                          |                 2 |               0.85 |                  |            1 | ACTIVE          | 1768537490617 | 1768537490617 | 1768537490617 |          |             |           |           |           0 |                 |                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |                   |                |                  | ultrabert-v2.1.0
 cluster_PERSON_sarah                    | tenant-test | space-home |       1 |               | t            | PERSON        |                | Sarah               | ['Sarah']                            |                 |              | ["f2f6fb5c-1bd5-4a60-bd15-77f151b1a07c"]                                                                                                                                                                                                                                                                                                                                 |                          |                 1 |               0.85 |                  |            1 | ACTIVE          | 1768537490617 | 1768537490617 | 1768537490617 |          |             |           |           |           0 |                 |                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |                   |                |                  | ultrabert-v2.1.0
 cluster_PERSON_david                    | tenant-test | space-home |       1 |               | t            | PERSON        |                | David               | ['David']                            |                 |              | ["fee16c26-9a44-4124-9b85-cb0782d2416f"]                                                                                                                                                                                                                                                                                                                                 |                          |                 1 |               0.85 |                  |            1 | ACTIVE          | 1768537490617 | 1768537490617 | 1768537490617 |          |             |           |           |           0 |                 |                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |                   |                |                  | ultrabert-v2.1.0
 cluster_FAMILY_MEMBER_coworkers         | tenant-test | space-home |       1 |               | t            | FAMILY_MEMBER |                | coworkers           | ['coworkers']                        |                 |              | ["156562eb-446d-4650-be23-17d48f221931"]                                                                                                                                                                                                                                                                                                                                 |                          |                 1 |               0.95 |                  |            1 | ACTIVE          | 1768537490617 | 1768537490617 | 1768537490617 |          |             |           |           |           0 |                 |                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |                   |                |                  | ultrabert-v2.1.0
 cluster_LOCATION_central park           | tenant-test | space-home |       1 |               | t            | LOCATION      |                | Central Park        | ['Central Park']                     |                 |              | ["f1803fb3-5a72-4d29-91ce-845d32a403f2"]                                                                                                                                                                                                                                                                                                                                 |                          |                 1 |                0.8 |                  |            1 | ACTIVE          | 1768537490617 | 1768537490617 | 1768537490617 |          |             |           |           |           0 |                 |                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |                   |                |                  | ultrabert-v2.1.0
 cluster_PERSON_smith                    | tenant-test | space-home |       1 |               | t            | PERSON        |                | Smith               | ['Smith']                            |                 |              | ["5d1504b0-c807-490a-b0c9-964e219faca3", "75b706da-fc8f-4fc3-a752-865cd4398e59"]                                                                                                                                                                                                                                                                                         |                          |                 2 |               0.85 |                  |            1 | ACTIVE          | 1768537490617 | 1768537490617 | 1768537490617 |          |             |           |           |           0 |                 |                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |                   |                |                  | ultrabert-v2.1.0
 cluster_PERSON_maria                    | tenant-test | space-home |       1 |               | t            | PERSON        |                | Maria               | ['Maria']                            |                 |              | ["200177cb-55f6-4d4b-9ad3-45e164bae4ba"]                                                                                                                                                                                                                                                                                                                                 |                          |                 1 |               0.85 |                  |            1 | ACTIVE          | 1768537490617 | 1768537490617 | 1768537490617 |          |             |           |           |           0 |                 |                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |                   |                |                  | ultrabert-v2.1.0
 cluster_PERSON_johnson                  | tenant-test | space-home |       1 |               | t            | PERSON        |                | Johnson             | ['Johnson']                          |                 |              | ["d0458fd9-3821-4fa6-93eb-4db070b2ff90"]                                                                                                                                                                                                                                                                                                                                 |                          |                 1 |               0.85 |                  |            1 | ACTIVE          | 1768537490617 | 1768537490617 | 1768537490617 |          |             |           |           |           0 |                 |                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |                   |                |                  | ultrabert-v2.1.0
 cluster_PERSON_rachel                   | tenant-test | space-home |       1 |               | t            | PERSON        |                | Rachel              | ['Rachel']                           |                 |              | ["2bc3990d-1856-4cf2-8db5-bc18dfc420c3", "48ee259d-cbc3-43b7-83bc-5dc5a65154c6", "d96c6408-d41e-4def-8df4-170b43010d62", "ed8c6ab6-db0b-4b39-8026-91102bba6506"]                                                                                                                                                                                                         |                          |                 4 |               0.85 |                  |            1 | ACTIVE          | 1768537490617 | 1768537490617 | 1768537490617 |          |             |           |           |           0 |                 |                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |                   |                |                  | ultrabert-v2.1.0
 cluster_ORGANIZATION_starbucks          | tenant-test | space-home |       1 |               | t            | ORGANIZATION  |                | Starbucks           | ['Starbucks']                        |                 |              | ["2bc3990d-1856-4cf2-8db5-bc18dfc420c3", "48ee259d-cbc3-43b7-83bc-5dc5a65154c6", "ed8c6ab6-db0b-4b39-8026-91102bba6506"]                                                                                                                                                                                                                                                 |                          |                 3 | 0.8000000000000002 |                  |            1 | ACTIVE          | 1768537490617 | 1768537490617 | 1768537490617 |          |             |           |           |           0 |                 |                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |                   |                |                  | ultrabert-v2.1.0
 cluster_ORGANIZATION_google             | tenant-test | space-home |       1 |               | t            | ORGANIZATION  |                | Google              | ['Google']                           |                 |              | ["2bc3990d-1856-4cf2-8db5-bc18dfc420c3", "48ee259d-cbc3-43b7-83bc-5dc5a65154c6", "5b0f71f3-8611-4b94-96ed-28983614fe5d", "ed8c6ab6-db0b-4b39-8026-91102bba6506"]                                                                                                                                                                                                         |                          |                 4 |                0.8 |                  |            1 | ACTIVE          | 1768537490617 | 1768537490617 | 1768537490617 |          |             |           |           |           0 |                 |                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |                   |                |                  | ultrabert-v2.1.0
 cluster_PERSON_tom                      | tenant-test | space-home |       1 |               | t            | PERSON        |                | Tom                 | ['Tom']                              |                 |              | ["42062809-af31-494b-9a1f-e4b2bf90ee21", "d96c6408-d41e-4def-8df4-170b43010d62"]                                                                                                                                                                                                                                                                                         |                          |                 2 |               0.85 |                  |            1 | ACTIVE          | 1768537490617 | 1768537490617 | 1768537490617 |          |             |           |           |           0 |                 |                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |                   |                |                  | ultrabert-v2.1.0
 cluster_CONCEPT_italian                 | tenant-test | space-home |       1 |               | t            | CONCEPT       |                | Italian             | ['Italian']                          |                 |              | ["a5139b36-eceb-4845-bb6a-53fd68f89bf5"]                                                                                                                                                                                                                                                                                                                                 |                          |                 1 |               0.65 |                  |            1 | ACTIVE          | 1768537490617 | 1768537490617 | 1768537490617 |          |             |           |           |           0 |                 |                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |                   |                |                  | ultrabert-v2.1.0
 cluster_ORGANIZATION_bella notte        | tenant-test | space-home |       1 |               | t            | ORGANIZATION  |                | Bella Notte         | ['Bella Notte']                      |                 |              | ["a5139b36-eceb-4845-bb6a-53fd68f89bf5"]                                                                                                                                                                                                                                                                                                                                 |                          |                 1 |                0.8 |                  |            1 | ACTIVE          | 1768537490617 | 1768537490617 | 1768537490617 |          |             |           |           |           0 |                 |                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |                   |                |                  | ultrabert-v2.1.0
 cluster_CONCEPT_inception               | tenant-test | space-home |       1 |               | t            | CONCEPT       |                | Inception           | ['Inception']                        |                 |              | ["4e9c3301-e997-4bb4-97ce-5cf7ca6f6bbb"]                                                                                                                                                                                                                                                                                                                                 |                          |                 1 |               0.65 |                  |            1 | ACTIVE          | 1768537490617 | 1768537490617 | 1768537490617 |          |             |           |           |           0 |                 |                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |                   |                |                  | ultrabert-v2.1.0
 cluster_PERSON_kevin                    | tenant-test | space-home |       1 |               | t            | PERSON        |                | Kevin               | ['Kevin']                            |                 |              | ["4e9c3301-e997-4bb4-97ce-5cf7ca6f6bbb"]                                                                                                                                                                                                                                                                                                                                 |                          |                 1 |               0.85 |                  |            1 | ACTIVE          | 1768537490617 | 1768537490617 | 1768537490617 |          |             |           |           |           0 |                 |                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |                   |                |                  | ultrabert-v2.1.0
 cluster_CONCEPT_atomic habits           | tenant-test | space-home |       1 |               | t            | CONCEPT       |                | Atomic Habits       | ['Atomic Habits']                    |                 |              | ["f7a41a92-312d-49e4-b77c-ed689114a889"]                                                                                                                                                                                                                                                                                                                                 |                          |                 1 |               0.65 |                  |            1 | ACTIVE          | 1768537490617 | 1768537490617 | 1768537490617 |          |             |           |           |           0 |                 |                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |                   |                |                  | ultrabert-v2.1.0
 cluster_PERSON_james clear              | tenant-test | space-home |       1 |               | t            | PERSON        |                | James Clear         | ['James Clear']                      |                 |              | ["f7a41a92-312d-49e4-b77c-ed689114a889"]                                                                                                                                                                                                                                                                                                                                 |                          |                 1 |               0.85 |                  |            1 | ACTIVE          | 1768537490617 | 1768537490617 | 1768537490617 |          |             |           |           |           0 |                 |                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |                   |                |                  | ultrabert-v2.1.0
 cluster_CONCEPT_python                  | tenant-test | space-home |       1 |               | t            | CONCEPT       |                | Python              | ['Python']                           |                 |              | ["9cf28272-dd70-49d7-8a84-8ef4900fce4c"]                                                                                                                                                                                                                                                                                                                                 |                          |                 1 |               0.65 |                  |            1 | ACTIVE          | 1768537490617 | 1768537490617 | 1768537490617 |          |             |           |           |           0 |                 |                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |                   |                |                  | ultrabert-v2.1.0
 cluster_ORGANIZATION_coursera           | tenant-test | space-home |       1 |               | t            | ORGANIZATION  |                | Coursera            | ['Coursera']                         |                 |              | ["9cf28272-dd70-49d7-8a84-8ef4900fce4c"]                                                                                                                                                                                                                                                                                                                                 |                          |                 1 |                0.8 |                  |            1 | ACTIVE          | 1768537490617 | 1768537490617 | 1768537490617 |          |             |           |           |           0 |                 |                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |                   |                |                  | ultrabert-v2.1.0
 cluster_CONCEPT_ai                      | tenant-test | space-home |       1 |               | t            | CONCEPT       |                | AI                  | ['AI']                               |                 |              | ["3b0376a3-e949-450e-aff0-b7e873b67650"]                                                                                                                                                                                                                                                                                                                                 |                          |                 1 |               0.65 |                  |            1 | ACTIVE          | 1768537490617 | 1768537490617 | 1768537490617 |          |             |           |           |           0 |                 |                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |                   |                |                  | ultrabert-v2.1.0
 cluster_ORGANIZATION_stanford           | tenant-test | space-home |       1 |               | t            | ORGANIZATION  |                | Stanford            | ['Stanford']                         |                 |              | ["3b0376a3-e949-450e-aff0-b7e873b67650"]                                                                                                                                                                                                                                                                                                                                 |                          |                 1 |                0.8 |                  |            1 | ACTIVE          | 1768537490617 | 1768537490617 | 1768537490617 |          |             |           |           |           0 |                 |                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |                   |                |                  | ultrabert-v2.1.0
 cluster_PERSON_andrew ng                | tenant-test | space-home |       1 |               | t            | PERSON        |                | Andrew Ng           | ['Andrew Ng']                        |                 |              | ["3b0376a3-e949-450e-aff0-b7e873b67650"]                                                                                                                                                                                                                                                                                                                                 |                          |                 1 |               0.85 |                  |            1 | ACTIVE          | 1768537490617 | 1768537490617 | 1768537490617 |          |             |           |           |           0 |                 |                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |                   |                |                  | ultrabert-v2.1.0
 cluster_LOCATION_brooklyn               | tenant-test | space-home |       1 |               | t            | LOCATION      |                | Brooklyn            | ['Brooklyn']                         |                 |              | ["01bb7622-b3af-44d5-8bf0-9f4a3f8be996", "c9ca2793-eaa2-4c9f-9463-9d8d29d575ed"]                                                                                                                                                                                                                                                                                         |                          |                 2 | 0.8500000000000001 |                  |            1 | ACTIVE          | 1768537490617 | 1768537490617 | 1768537490617 |          |             |           |           |           0 |                 |                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |                   |                |                  | ultrabert-v2.1.0
 cluster_ORGANIZATION_lincoln elementary | tenant-test | space-home |       1 |               | t            | ORGANIZATION  |                | Lincoln Elementary  | ['Lincoln Elementary']               |                 |              | ["f1f2bd40-62a5-45fb-835d-7a7305ff65e7"]                                                                                                                                                                                                                                                                                                                                 |                          |                 1 |                0.8 |                  |            1 | ACTIVE          | 1768537490617 | 1768537490617 | 1768537490617 |          |             |           |           |           0 |                 |                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |                   |                |                  | ultrabert-v2.1.0
 cluster_LOCATION_san francisco          | tenant-test | space-home |       1 |               | t            | LOCATION      |                | San Francisco       | ['San Francisco']                    |                 |              | ["d2a159ce-6434-47dc-a1cb-70c7e7ece866", "19a33cd5-267e-4546-96e2-ed9b5a1e5df6"]                                                                                                                                                                                                                                                                                         |                          |                 2 |                0.8 |                  |            1 | ACTIVE          | 1768537490617 | 1768537490617 | 1768537490617 |          |             |           |           |           0 |                 |                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |                   |                |                  | ultrabert-v2.1.0
 cluster_LOCATION_alcatraz               | tenant-test | space-home |       1 |               | t            | LOCATION      |                | Alcatraz            | ['Alcatraz']                         |                 |              | ["25b20eca-893f-4ce2-b96d-e643ac0da540"]                                                                                                                                                                                                                                                                                                                                 |                          |                 1 | 0.8500000000000001 |                  |            1 | ACTIVE          | 1768537490617 | 1768537490617 | 1768537490617 |          |             |           |           |           0 |                 |                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |                   |                |                  | ultrabert-v2.1.0
 cluster_LOCATION_golden gate bridge     | tenant-test | space-home |       1 |               | t            | LOCATION      |                | Golden Gate Bridge  | ['Golden Gate Bridge']               |                 |              | ["25b20eca-893f-4ce2-b96d-e643ac0da540"]                                                                                                                                                                                                                                                                                                                                 |                          |                 1 |                0.8 |                  |            1 | ACTIVE          | 1768537490617 | 1768537490617 | 1768537490617 |          |             |           |           |           0 |                 |                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |                   |                |                  | ultrabert-v2.1.0
 cluster_LOCATION_boston                 | tenant-test | space-home |       1 |               | t            | LOCATION      |                | Boston              | ['Boston']                           |                 |              | ["24ecb90e-98cb-40cf-9a5e-854be3a9ac6b"]                                                                                                                                                                                                                                                                                                                                 |                          |                 1 | 0.8500000000000001 |                  |            1 | ACTIVE          | 1768537490617 | 1768537490617 | 1768537490617 |          |             |           |           |           0 |                 |                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |                   |                |                  | ultrabert-v2.1.0
 cluster_FAMILY_MEMBER_family            | tenant-test | space-home |       1 |               | t            | FAMILY_MEMBER |                | family              | ['family']                           |                 |              | ["135f16c4-e742-4244-9b51-0e392b298224", "24ecb90e-98cb-40cf-9a5e-854be3a9ac6b"]                                                                                                                                                                                                                                                                                         |                          |                 2 |               0.95 |                  |            1 | ACTIVE          | 1768537490617 | 1768537490617 | 1768537490617 |          |             |           |           |           0 |                 |                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |                   |                |                  | ultrabert-v2.1.0
 cluster_CONCEPT_freedom trail           | tenant-test | space-home |       1 |               | t            | CONCEPT       |                | Freedom Trail       | ['Freedom Trail']                    |                 |              | ["24ecb90e-98cb-40cf-9a5e-854be3a9ac6b"]                                                                                                                                                                                                                                                                                                                                 |                          |                 1 |               0.65 |                  |            1 | ACTIVE          | 1768537490617 | 1768537490617 | 1768537490617 |          |             |           |           |           0 |                 |                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |                   |                |                  | ultrabert-v2.1.0
 cluster_PERSON_jennifer                 | tenant-test | space-home |       1 |               | t            | PERSON        |                | Jennifer            | ['Jennifer']                         |                 |              | ["28a49aa7-0f30-45f4-a33a-2e79afd813a2"]                                                                                                                                                                                                                                                                                                                                 |                          |                 1 |               0.85 |                  |            1 | ACTIVE          | 1768537490617 | 1768537490617 | 1768537490617 |          |             |           |           |           0 |                 |                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |                   |                |                  | ultrabert-v2.1.0
 cluster_LOCATION_manhattan              | tenant-test | space-home |       1 |               | t            | LOCATION      |                | Manhattan           | ['Manhattan']                        |                 |              | ["01bb7622-b3af-44d5-8bf0-9f4a3f8be996"]                                                                                                                                                                                                                                                                                                                                 |                          |                 1 | 0.8500000000000001 |                  |            1 | ACTIVE          | 1768537490617 | 1768537490617 | 1768537490617 |          |             |           |           |           0 |                 |                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |                   |                |                  | ultrabert-v2.1.0
 cluster_PERSON_alex                     | tenant-test | space-home |       1 |               | t            | PERSON        |                | Alex                | ['Alex']                             |                 |              | ["9503ffdc-f768-425f-a2c0-4761c5499c95"]                                                                                                                                                                                                                                                                                                                                 |                          |                 1 |               0.85 |                  |            1 | ACTIVE          | 1768537490617 | 1768537490617 | 1768537490617 |          |             |           |           |           0 |                 |                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |                   |                |                  | ultrabert-v2.1.0
 cluster_PERSON_chris                    | tenant-test | space-home |       1 |               | t            | PERSON        |                | Chris               | ['Chris']                            |                 |              | ["9503ffdc-f768-425f-a2c0-4761c5499c95"]                                                                                                                                                                                                                                                                                                                                 |                          |                 1 |               0.85 |                  |            1 | ACTIVE          | 1768537490617 | 1768537490617 | 1768537490617 |          |             |           |           |           0 |                 |                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |                   |                |                  | ultrabert-v2.1.0
 cluster_FAMILY_MEMBER_brother           | tenant-test | space-home |       1 |               | t            | FAMILY_MEMBER |                | brother             | ['brother']                          |                 |              | ["14a17d97-aaae-481a-95c2-c1022d2ea4d5"]                                                                                                                                                                                                                                                                                                                                 |                          |                 1 |               0.95 |                  |            1 | ACTIVE          | 1768537490617 | 1768537490617 | 1768537490617 |          |             |           |           |           0 |                 |                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |                   |                |                  | ultrabert-v2.1.0
 cluster_PERSON_sophie                   | tenant-test | space-home |       1 |               | t            | PERSON        |                | Sophie              | ['Sophie']                           |                 |              | ["14a17d97-aaae-481a-95c2-c1022d2ea4d5"]                                                                                                                                                                                                                                                                                                                                 |                          |                 1 |               0.85 |                  |            1 | ACTIVE          | 1768537490617 | 1768537490617 | 1768537490617 |          |             |           |           |           0 |                 |                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |                   |                |                  | ultrabert-v2.1.0
 cluster_LOCATION_london                 | tenant-test | space-home |       1 |               | t            | LOCATION      |                | London              | ['London']                           |                 |              | ["0b34ae98-cfbd-43e1-aeb6-a02c7b9eb31a"]                                                                                                                                                                                                                                                                                                                                 |                          |                 1 | 0.8500000000000001 |                  |            1 | ACTIVE          | 1768537490617 | 1768537490617 | 1768537490617 |          |             |           |           |           0 |                 |                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |                   |                |                  | ultrabert-v2.1.0
 Emma                                    | default     | default    |       1 |               | t            | PERSON        |                | Emma                |                                      |                 |              |                                                                                                                                                                                                                                                                                                                                                                          |                          |                 1 |                0.5 |                  |            1 | ACTIVE          | 1768537490657 | 1768537490617 | 1768537490657 |          |             |           |           |           2 |   1768537490617 | [{"milestone_type": "ANNOUNCEMENT", "description": "Picked up Emma from soccer practice at City Sports Complex. She scored 2 goals today!", "source_event_id": "c0326faa-4a8c-4050-9f86-4d1bd5677fd9", "recorded_at_ms": 1768537490617}, {"milestone_type": "ACHIEVEMENT", "description": "Exciting news! Emma got accepted into the gifted program at school!", "source_event_id": "06172f82-8e8d-49e7-9047-337a3f542ebc", "recorded_at_ms": 1768537490617}]                                                                                                                                                                                                                                                                                                                                                                                                                                                       |                   |                |                  | ultrabert-v2.1.0
 Emma's                                  | default     | default    |       1 |               | t            | PERSON        |                | Emma's              |                                      |                 |              |                                                                                                                                                                                                                                                                                                                                                                          |                          |                 1 |                0.5 |                  |            1 | ACTIVE          | 1768537490660 | 1768537490617 | 1768537490660 |          |             |           |           |           0 |   1768537490617 | [{"milestone_type": "ANNOUNCEMENT", "description": "Emma's piano recital at Lincoln School. She played Fur Elise beautifully.", "source_event_id": "aaf6b89a-6e1e-44ca-8fc8-f209a5a23d08", "recorded_at_ms": 1768537490617}]                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        |                   |                |                  | ultrabert-v2.1.0
 John                                    | default     | default    |       1 |               | t            | PERSON        |                | John                |                                      |                 |              |                                                                                                                                                                                                                                                                                                                                                                          |                          |                 1 |                0.5 |                  |            1 | ACTIVE          | 1768537490662 | 1768537490617 | 1768537490662 |          |             |           |           |           0 |   1768537490617 | [{"milestone_type": "ANNOUNCEMENT", "description": "Team standup meeting with John, Lisa, and Mike. Discussed Q2 roadmap priorities.", "source_event_id": "fd987ef5-cd1f-4aa0-ba4b-248ad3130db1", "recorded_at_ms": 1768537490617}]                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |                   |                |                  | ultrabert-v2.1.0
 Sarah                                   | default     | default    |       1 |               | t            | PERSON        |                | Sarah               |                                      |                 |              |                                                                                                                                                                                                                                                                                                                                                                          |                          |                 1 |                0.5 |                  |            1 | ACTIVE          | 1768537490663 | 1768537490617 | 1768537490663 |          |             |           |           |           0 |   1768537490617 | [{"milestone_type": "ANNOUNCEMENT", "description": "One-on-one with manager Sarah about promotion timeline and career goals.", "source_event_id": "f2f6fb5c-1bd5-4a60-bd15-77f151b1a07c", "recorded_at_ms": 1768537490617}]                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |                   |                |                  | ultrabert-v2.1.0
 David                                   | default     | default    |       1 |               | t            | PERSON        |                | David               |                                      |                 |              |                                                                                                                                                                                                                                                                                                                                                                          |                          |                 1 |                0.5 |                  |            1 | ACTIVE          | 1768537490665 | 1768537490617 | 1768537490665 |          |             |           |           |           0 |   1768537490617 | [{"milestone_type": "ANNOUNCEMENT", "description": "Presented quarterly results to the executive team. CEO David was impressed.", "source_event_id": "fee16c26-9a44-4124-9b85-cb0782d2416f", "recorded_at_ms": 1768537490617}]                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |                   |                |                  | ultrabert-v2.1.0
 Mike                                    | default     | default    |       1 |               | t            | PERSON        |                | Mike                |                                      |                 |              |                                                                                                                                                                                                                                                                                                                                                                          |                          |                 1 |                0.5 |                  |            1 | ACTIVE          | 1768537490666 | 1768537490617 | 1768537490666 |          |             |           |           |           0 |   1768537490617 | [{"milestone_type": "ANNOUNCEMENT", "description": "Code review session with Mike. Fixed critical bug in authentication module.", "source_event_id": "cb298f1e-4ff5-4599-acbd-113ff0b952d3", "recorded_at_ms": 1768537490617}]                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |                   |                |                  | ultrabert-v2.1.0
 Johnson                                 | default     | default    |       1 |               | t            | PERSON        |                | Johnson             |                                      |                 |              |                                                                                                                                                                                                                                                                                                                                                                          |                          |                 1 |                0.5 |                  |            1 | ACTIVE          | 1768537490668 | 1768537490617 | 1768537490668 |          |             |           |           |           0 |   1768537490617 | [{"milestone_type": "ANNOUNCEMENT", "description": "Dentist checkup with Dr. Johnson. No cavities, scheduled cleaning for next month.", "source_event_id": "d0458fd9-3821-4fa6-93eb-4db070b2ff90", "recorded_at_ms": 1768537490617}]                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |                   |                |                  | ultrabert-v2.1.0
 Rachel                                  | default     | default    |       1 |               | t            | PERSON        |                | Rachel              |                                      |                 |              |                                                                                                                                                                                                                                                                                                                                                                          |                          |                 1 |                0.5 |                  |            1 | ACTIVE          | 1768537490669 | 1768537490617 | 1768537490669 |          |             |           |           |           0 |   1768537490617 | [{"milestone_type": "TRANSITION", "description": "Coffee with best friend Rachel at Starbucks. She's excited about her new job at Google.", "source_event_id": "ed8c6ab6-db0b-4b39-8026-91102bba6506", "recorded_at_ms": 1768537490617}, {"milestone_type": "ANNOUNCEMENT", "description": "Had coffee with Rachel at Starbucks. She mentioned her new position at Google.", "source_event_id": "2bc3990d-1856-4cf2-8db5-bc18dfc420c3", "recorded_at_ms": 1768537490617}, {"milestone_type": "ANNOUNCEMENT", "description": "Met Rachel for coffee at the Starbucks downtown. Talked about her Google job.", "source_event_id": "48ee259d-cbc3-43b7-83bc-5dc5a65154c6", "recorded_at_ms": 1768537490617}, {"milestone_type": "TRANSITION", "description": "Rachel just told me she's getting married to Tom in June!", "source_event_id": "d96c6408-d41e-4def-8df4-170b43010d62", "recorded_at_ms": 1768537490617}] |                   |                |                  | ultrabert-v2.1.0
 Birthday party                          | default     | default    |       1 |               | t            | EVENT         |                | Birthday party      |                                      |                 |              |                                                                                                                                                                                                                                                                                                                                                                          |                          |                 1 |                0.5 |                  |            1 | ACTIVE          | 1768537490670 | 1768537490617 | 1768537490670 |          |             |           |           |           0 |   1768537490617 | [{"milestone_type": "CELEBRATION", "description": "Birthday party for Tom at his apartment. About 20 people showed up.", "source_event_id": "42062809-af31-494b-9a1f-e4b2bf90ee21", "recorded_at_ms": 1768537490617}]                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |                   |                |                  | ultrabert-v2.1.0
 Italian                                 | default     | default    |       1 |               | t            | PERSON        |                | Italian             |                                      |                 |              |                                                                                                                                                                                                                                                                                                                                                                          |                          |                 1 |                0.5 |                  |            1 | ACTIVE          | 1768537490672 | 1768537490617 | 1768537490672 |          |             |           |           |           0 |   1768537490617 | [{"milestone_type": "ANNOUNCEMENT", "description": "Dinner with college friends at Italian restaurant Bella Notte. Great pasta!", "source_event_id": "a5139b36-eceb-4845-bb6a-53fd68f89bf5", "recorded_at_ms": 1768537490617}]                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |                   |                |                  | ultrabert-v2.1.0
 Python                                  | default     | default    |       1 |               | t            | CONCEPT       |                | Python              |                                      |                 |              |                                                                                                                                                                                                                                                                                                                                                                          |                          |                 1 |                0.5 |                  |            1 | ACTIVE          | 1768537490673 | 1768537490617 | 1768537490673 |          |             |           |           |           0 |   1768537490617 | [{"milestone_type": "ACHIEVEMENT", "description": "Online Python course on Coursera. Completed module on machine learning basics.", "source_event_id": "9cf28272-dd70-49d7-8a84-8ef4900fce4c", "recorded_at_ms": 1768537490617}]                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    |                   |                |                  | ultrabert-v2.1.0
 Stanford                                | default     | default    |       1 |               | t            | ORGANIZATION  |                | Stanford            |                                      |                 |              |                                                                                                                                                                                                                                                                                                                                                                          |                          |                 1 |                0.5 |                  |            1 | ACTIVE          | 1768537490675 | 1768537490617 | 1768537490675 |          |             |           |           |           0 |   1768537490617 | [{"milestone_type": "ANNOUNCEMENT", "description": "Attended webinar on AI and the future of work by Stanford professor Andrew Ng.", "source_event_id": "3b0376a3-e949-450e-aff0-b7e873b67650", "recorded_at_ms": 1768537490617}]                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   |                   |                |                  | ultrabert-v2.1.0
 Brooklyn                                | default     | default    |       1 |               | t            | LOCATION      |                | Brooklyn            |                                      |                 |              |                                                                                                                                                                                                                                                                                                                                                                          |                          |                 1 |                0.5 |                  |            1 | ACTIVE          | 1768537490677 | 1768537490617 | 1768537490677 |          |             |           |           |           0 |   1768537490617 | [{"milestone_type": "ANNOUNCEMENT", "description": "Signed lease for new apartment in Brooklyn. Moving in next month.", "source_event_id": "c9ca2793-eaa2-4c9f-9463-9d8d29d575ed", "recorded_at_ms": 1768537490617}]                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |                   |                |                  | ultrabert-v2.1.0
 Alcatraz                                | default     | default    |       1 |               | t            | LOCATION      |                | Alcatraz            |                                      |                 |              |                                                                                                                                                                                                                                                                                                                                                                          |                          |                 1 |                0.5 |                  |            1 | ACTIVE          | 1768537490678 | 1768537490617 | 1768537490678 |          |             |           |           |           0 |   1768537490617 | [{"milestone_type": "ANNOUNCEMENT", "description": "Visited Golden Gate Bridge. Amazing views of the bay and Alcatraz.", "source_event_id": "25b20eca-893f-4ce2-b96d-e643ac0da540", "recorded_at_ms": 1768537490617}]                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |                   |                |                  | ultrabert-v2.1.0
 student                                 | default     | default    |       1 |               | t            | UNKNOWN       |                | student             |                                      |                 |              |                                                                                                                                                                                                                                                                                                                                                                          |                          |                 1 |                0.5 |                  |            1 | ACTIVE          | 1768537490679 | 1768537490617 | 1768537490679 |          |             |           |           |           0 |   1768537490617 | [{"milestone_type": "ANNOUNCEMENT", "description": "Paid off student loans! 10 years of payments finally done.", "source_event_id": "2e70e513-f36e-417c-9dc3-db59d7cd0e9c", "recorded_at_ms": 1768537490617}]                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |                   |                |                  | ultrabert-v2.1.0
 Jennifer                                | default     | default    |       1 |               | t            | PERSON        |                | Jennifer            |                                      |                 |              |                                                                                                                                                                                                                                                                                                                                                                          |                          |                 1 |                0.5 |                  |            1 | ACTIVE          | 1768537490681 | 1768537490617 | 1768537490681 |          |             |           |           |           0 |   1768537490617 | [{"milestone_type": "ANNOUNCEMENT", "description": "Met with financial advisor Jennifer about retirement planning and 401k.", "source_event_id": "28a49aa7-0f30-45f4-a33a-2e79afd813a2", "recorded_at_ms": 1768537490617}]                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          |                   |                |                  | ultrabert-v2.1.0
 brother                                 | default     | default    |       1 |               | t            | FAMILY_MEMBER |                | brother             |                                      |                 |              |                                                                                                                                                                                                                                                                                                                                                                          |                          |                 1 |                0.5 |                  |            1 | ACTIVE          | 1768537490683 | 1768537490617 | 1768537490683 |          |             |           |           |           0 |   1768537490617 | [{"milestone_type": "ANNOUNCEMENT", "description": "My brother Jake just had his first baby - a girl named Sophie!", "source_event_id": "14a17d97-aaae-481a-95c2-c1022d2ea4d5", "recorded_at_ms": 1768537490617}]                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   |                   |                |                  | ultrabert-v2.1.0
 London                                  | default     | default    |       1 |               | t            | LOCATION      |                | London              |                                      |                 |              |                                                                                                                                                                                                                                                                                                                                                                          |                          |                 1 |                0.5 |                  |            1 | ACTIVE          | 1768537490685 | 1768537490617 | 1768537490685 |          |             |           |           |           0 |   1768537490617 | [{"milestone_type": "ANNOUNCEMENT", "description": "The company announced we're expanding to London next year!", "source_event_id": "0b34ae98-cfbd-43e1-aeb6-a02c7b9eb31a", "recorded_at_ms": 1768537490617}]                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |                   |                |                  | ultrabert-v2.1.0
 Mom                                     | default     | default    |       1 |               | t            | FAMILY_MEMBER |                | Mom                 |                                      |                 |              |                                                                                                                                                                                                                                                                                                                                                                          |                          |                 1 |                0.5 |                  |            1 | ACTIVE          | 1768537490686 | 1768537490617 | 1768537490686 |          |             |           |           |           1 |   1768537490617 |                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |                   |                |                  | ultrabert-v2.1.0
 Thanksgiving                            | default     | default    |       1 |               | t            | PERSON        |                | Thanksgiving        |                                      |                 |              |                                                                                                                                                                                                                                                                                                                                                                          |                          |                 1 |                0.5 |                  |            1 | ACTIVE          | 1768537490688 | 1768537490617 | 1768537490688 |          |             |           |           |           1 |   1768537490617 |                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |                   |                |                  | ultrabert-v2.1.0
 piano                                   | default     | default    |       1 |               | t            | UNKNOWN       |                | piano               |                                      |                 |              |                                                                                                                                                                                                                                                                                                                                                                          |                          |                 1 |                0.5 |                  |            1 | ACTIVE          | 1768537490689 | 1768537490617 | 1768537490689 |          |             |           |           |           2 |   1768537490617 |                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |                   |                |                  | ultrabert-v2.1.0
 recital                                 | default     | default    |       1 |               | t            | EVENT         |                | recital             |                                      |                 |              |                                                                                                                                                                                                                                                                                                                                                                          |                          |                 1 |                0.5 |                  |            1 | ACTIVE          | 1768537490690 | 1768537490617 | 1768537490690 |          |             |           |           |           1 |   1768537490617 |                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |                   |                |                  | ultrabert-v2.1.0
 Lincoln School                          | default     | default    |       1 |               | t            | LOCATION      |                | Lincoln School      |                                      |                 |              |                                                                                                                                                                                                                                                                                                                                                                          |                          |                 1 |                0.5 |                  |            1 | ACTIVE          | 1768537490692 | 1768537490617 | 1768537490692 |          |             |           |           |           2 |   1768537490617 |                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |                   |                |                  | ultrabert-v2.1.0
 San Francisco trip                      | default     | default    |       1 |               | t            | LOCATION      |                | San Francisco trip  |                                      |                 |              |                                                                                                                                                                                                                                                                                                                                                                          |                          |                 1 |                0.5 |                  |            1 | ACTIVE          | 1768537490693 | 1768537490617 | 1768537490693 |          |             |           |           |           1 |   1768537490617 |                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |                   |                |                  | ultrabert-v2.1.0
(73 rows)
```

---

### st_kg_edges

**Row Count**: 4

**Schema**:
```
column_name      |     data_type     | is_nullable 
----------------------+-------------------+-------------
 edge_id              | text              | NO
 tenant_id            | text              | NO
 space_id             | text              | NO
 source_entity_id     | text              | NO
 target_entity_id     | text              | NO
 version              | integer           | NO
 supersedes_id        | text              | YES
 is_canonical         | boolean           | YES
 relation_type        | text              | NO
 relation_subtype     | text              | YES
 properties_json      | text              | YES
 edge_weight          | double precision  | YES
 confidence_score     | double precision  | YES
 source_episodes_json | text              | YES
 co_occurrence_count  | integer           | YES
 observation_count    | integer           | YES
 last_observed_at     | bigint            | YES
 decay_factor         | double precision  | YES
 archival_status      | text              | YES
 valid_from           | bigint            | NO
 valid_to             | bigint            | YES
 created_at           | bigint            | NO
 updated_at           | bigint            | NO
 merge_cascade_id     | character varying | YES
 query_count          | integer           | NO
 last_queried_at      | bigint            | YES
 sentiment_avg        | double precision  | YES
(27 rows)
```

**Data**:
```
edge_id                             |  tenant_id  |  space_id  |        source_entity_id         |        target_entity_id        | version | supersedes_id | is_canonical | relation_type | relation_subtype | properties_json |     edge_weight     |  confidence_score   | source_episodes_json | co_occurrence_count | observation_count | last_observed_at | decay_factor | archival_status |  valid_from   | valid_to |  created_at   |  updated_at   | merge_cascade_id | query_count | last_queried_at | sentiment_avg 
-----------------------------------------------------------------+-------------+------------+---------------------------------+--------------------------------+---------+---------------+--------------+---------------+------------------+-----------------+---------------------+---------------------+----------------------+---------------------+-------------------+------------------+--------------+-----------------+---------------+----------+---------------+---------------+------------------+-------------+-----------------+---------------
 edge_cluster_LOCATION_lincoln school_cluster_PERSON_emma        | tenant-test | space-home | cluster_LOCATION_lincoln school | cluster_PERSON_emma            |       1 |               | t            | RELATED_TO    |                  |                 | 0.21766162500000003 | 0.21766162500000003 | []                   |                   1 |                 1 |                  |            1 | ACTIVE          | 1768537490617 |          | 1768537490617 | 1768537490617 |                  |           0 |                 |              
 edge_cluster_ORGANIZATION_starbucks_cluster_PERSON_rachel       | tenant-test | space-home | cluster_ORGANIZATION_starbucks  | cluster_PERSON_rachel          |       1 |               | t            | RELATED_TO    |                  |                 | 0.26859796089843757 | 0.26859796089843757 | []                   |                   1 |                 1 |                  |            1 | ACTIVE          | 1768537490617 |          | 1768537490617 | 1768537490617 |                  |           0 |                 |              
 edge_cluster_ORGANIZATION_google_cluster_PERSON_rachel          | tenant-test | space-home | cluster_ORGANIZATION_google     | cluster_PERSON_rachel          |       1 |               | t            | RELATED_TO    |                  |                 |  0.2685979608984375 |  0.2685979608984375 | []                   |                   1 |                 1 |                  |            1 | ACTIVE          | 1768537490617 |          | 1768537490617 | 1768537490617 |                  |           0 |                 |              
 edge_cluster_ORGANIZATION_google_cluster_ORGANIZATION_starbucks | tenant-test | space-home | cluster_ORGANIZATION_google     | cluster_ORGANIZATION_starbucks |       1 |               | t            | RELATED_TO    |                  |                 | 0.26147584000000007 | 0.26147584000000007 | []                   |                   1 |                 1 |                  |            1 | ACTIVE          | 1768537490617 |          | 1768537490617 | 1768537490617 |                  |           0 |                 |              
(4 rows)
```

---

### st_sem

**Row Count**: 66

**Schema**:
```
column_name       |     data_type     | is_nullable 
-------------------------+-------------------+-------------
 pattern_id              | text              | NO
 tenant_id               | text              | NO
 space_id                | text              | NO
 actor_id                | text              | YES
 version                 | integer           | NO
 supersedes_id           | text              | YES
 is_canonical            | boolean           | YES
 pattern_type            | text              | NO
 pattern_subtype         | text              | YES
 pattern_name            | text              | NO
 pattern_description     | text              | YES
 pattern_attributes_json | text              | YES
 temporal_regularity     | double precision  | YES
 temporal_pattern_json   | text              | YES
 source_episodes_json    | text              | NO
 source_episode_count    | integer           | NO
 embedding_id            | text              | YES
 observation_count       | integer           | YES
 confidence_score        | double precision  | YES
 last_observed_at        | bigint            | YES
 first_observed_at       | bigint            | YES
 decay_factor            | double precision  | YES
 archival_status         | text              | YES
 created_at              | bigint            | NO
 updated_at              | bigint            | NO
 valid_from              | bigint            | NO
 valid_to                | bigint            | YES
 merge_cascade_id        | character varying | YES
 source_texts_json       | text              | YES
 embedding_text          | text              | YES
 embedding_vector        | bytea             | YES
 embedding_model         | text              | YES
(32 rows)
```

**Sample Data** (showing 10 of 66 rows):
```
pattern_id                |  tenant_id  |  space_id  | actor_id | version | supersedes_id | is_canonical | pattern_type | pattern_subtype |                         pattern_name                          | pattern_description | pattern_attributes_json | temporal_regularity | temporal_pattern_json |           source_episodes_json           | source_episode_count |             embedding_id             | observation_count | confidence_score | last_observed_at | first_observed_at | decay_factor | archival_status |  created_at   |  updated_at   |  valid_from   | valid_to | merge_cascade_id | source_texts_json | embedding_text | embedding_vector | embedding_model  
------------------------------------------+-------------+------------+----------+---------+---------------+--------------+--------------+-----------------+---------------------------------------------------------------+---------------------+-------------------------+---------------------+-----------------------+------------------------------------------+----------------------+--------------------------------------+-------------------+------------------+------------------+-------------------+--------------+-----------------+---------------+---------------+---------------+----------+------------------+-------------------+----------------+------------------+------------------
 sem_c0326faa-4a8c-4050-9f86-4d1bd5677fd9 | tenant-test | space-home |          |       1 |               | t            | THEME        |                 | Social with ner_family, ner_general at City Sports Complex    |                     |                         |                     |                       | ["c0326faa-4a8c-4050-9f86-4d1bd5677fd9"] |                    1 | aa489b33-68ae-4d5c-a9b0-3a9277278a3b |                 1 |            0.545 |    1768537490615 |     1768537490615 |            1 | ACTIVE          | 1768537490615 | 1768537490615 | 1768537490615 |          |                  |                   |                |                  | ultrabert-v2.1.0
 sem_aaf6b89a-6e1e-44ca-8fc8-f209a5a23d08 | tenant-test | space-home |          |       1 |               | t            | THEME        |                 | Social with ner_family, ner_general at Lincoln School         |                     |                         |                     |                       | ["aaf6b89a-6e1e-44ca-8fc8-f209a5a23d08"] |                    1 | 0efdf56a-1d20-4746-839c-3ec2f7abcc6c |                 1 |            0.545 |    1768537490615 |     1768537490615 |            1 | ACTIVE          | 1768537490615 | 1768537490615 | 1768537490615 |          |                  |                   |                |                  | ultrabert-v2.1.0
 sem_6cbc22a6-66dd-4b55-8814-dc1893f2c75f | tenant-test | space-home |          |       1 |               | t            | THEME        |                 | Social with ner_family, ner_general at Home                   |                     |                         |                     |                       | ["6cbc22a6-66dd-4b55-8814-dc1893f2c75f"] |                    1 | aea968c6-064f-436e-aeae-d950936285d9 |                 1 |            0.545 |    1768537490615 |     1768537490615 |            1 | ACTIVE          | 1768537490615 | 1768537490615 | 1768537490615 |          |                  |                   |                |                  | ultrabert-v2.1.0
 sem_c474b007-99c7-4d97-be4c-f693cfe7c73b | tenant-test | space-home |          |       1 |               | t            | THEME        |                 | Social with ner_family, ner_general at Chuck E Cheese         |                     |                         |                     |                       | ["c474b007-99c7-4d97-be4c-f693cfe7c73b"] |                    1 | 7be8c915-7c3b-44a6-8945-c11c12d9904e |                 1 |            0.545 |    1768537490615 |     1768537490615 |            1 | ACTIVE          | 1768537490615 | 1768537490615 | 1768537490615 |          |                  |                   |                |                  | ultrabert-v2.1.0
 sem_fd987ef5-cd1f-4aa0-ba4b-248ad3130db1 | tenant-test | space-home |          |       1 |               | t            | THEME        |                 | Work with ner_family, ner_general at Office Conference Room B |                     |                         |                     |                       | ["fd987ef5-cd1f-4aa0-ba4b-248ad3130db1"] |                    1 | b285b2b5-407f-4a2a-9596-baeb5e8de19e |                 1 |            0.545 |    1768537490615 |     1768537490615 |            1 | ACTIVE          | 1768537490615 | 1768537490615 | 1768537490615 |          |                  |                   |                |                  | ultrabert-v2.1.0
 sem_f2f6fb5c-1bd5-4a60-bd15-77f151b1a07c | tenant-test | space-home |          |       1 |               | t            | THEME        |                 | Work with ner_family, ner_general at Sarah's Office           |                     |                         |                     |                       | ["f2f6fb5c-1bd5-4a60-bd15-77f151b1a07c"] |                    1 | bb09bde9-ace6-4196-be05-52a406973af9 |                 1 |            0.545 |    1768537490615 |     1768537490615 |            1 | ACTIVE          | 1768537490615 | 1768537490615 | 1768537490615 |          |                  |                   |                |                  | ultrabert-v2.1.0
 sem_fee16c26-9a44-4124-9b85-cb0782d2416f | tenant-test | space-home |          |       1 |               | t            | THEME        |                 | Work with ner_family, ner_general at Main Boardroom           |                     |                         |                     |                       | ["fee16c26-9a44-4124-9b85-cb0782d2416f"] |                    1 | a1256757-e2be-42d3-abed-5f92c794f9f8 |                 1 |            0.545 |    1768537490616 |     1768537490616 |            1 | ACTIVE          | 1768537490616 | 1768537490616 | 1768537490616 |          |                  |                   |                |                  | ultrabert-v2.1.0
 sem_cb298f1e-4ff5-4599-acbd-113ff0b952d3 | tenant-test | space-home |          |       1 |               | t            | THEME        |                 | Work with ner_family, ner_general at Office                   |                     |                         |                     |                       | ["cb298f1e-4ff5-4599-acbd-113ff0b952d3"] |                    1 | 9c9a728c-6c24-4275-8445-98436d7b7bff |                 1 |            0.545 |    1768537490616 |     1768537490616 |            1 | ACTIVE          | 1768537490616 | 1768537490616 | 1768537490616 |          |                  |                   |                |                  | ultrabert-v2.1.0
 sem_156562eb-446d-4650-be23-17d48f221931 | tenant-test | space-home |          |       1 |               | t            | THEME        |                 | Work with ner_family, ner_general at Chipotle                 |                     |                         |                     |                       | ["156562eb-446d-4650-be23-17d48f221931"] |                    1 | 3799a12c-0390-4bf4-ac49-af049344e241 |                 1 |            0.545 |    1768537490616 |     1768537490616 |            1 | ACTIVE          | 1768537490616 | 1768537490616 | 1768537490616 |          |                  |                   |                |                  | ultrabert-v2.1.0
 sem_f1803fb3-5a72-4d29-91ce-845d32a403f2 | tenant-test | space-home |          |       1 |               | t            | THEME        |                 | Routine with ner_family, ner_general at Central Park          |                     |                         |                     |                       | ["f1803fb3-5a72-4d29-91ce-845d32a403f2"] |                    1 | ac1ede4c-85ad-4b8c-a6ae-0997a40d1e55 |                 1 |            0.545 |    1768537490616 |     1768537490616 |            1 | ACTIVE          | 1768537490616 | 1768537490616 | 1768537490616 |          |                  |                   |                |                  | ultrabert-v2.1.0
(10 rows)
```

---

## Social Memory

### st_social

**Row Count**: 22

**Schema**:
```
column_name         |     data_type     | is_nullable 
-----------------------------+-------------------+-------------
 relationship_id             | text              | NO
 tenant_id                   | text              | NO
 space_id                    | text              | NO
 actor_a_id                  | text              | NO
 actor_b_id                  | text              | NO
 version                     | integer           | NO
 supersedes_id               | text              | YES
 is_canonical                | boolean           | YES
 relationship_type           | text              | NO
 relationship_subtype        | text              | YES
 relationship_label          | text              | YES
 interaction_count           | integer           | YES
 avg_sentiment               | double precision  | YES
 relationship_strength       | double precision  | YES
 intimacy_level              | text              | YES
 first_interaction_at        | bigint            | YES
 last_interaction_at         | bigint            | YES
 interaction_frequency       | text              | YES
 source_episodes_json        | text              | YES
 observation_count           | integer           | YES
 confidence_score            | double precision  | YES
 decay_factor                | double precision  | YES
 archival_status             | text              | YES
 created_at                  | bigint            | NO
 updated_at                  | bigint            | NO
 valid_from                  | bigint            | NO
 valid_to                    | bigint            | YES
 merge_cascade_id            | character varying | YES
 ultrabert_relation_types    | text              | YES
 emotional_role              | text              | YES
 emotional_valence_avg       | double precision  | YES
 emotional_valence_trend     | double precision  | YES
 relationship_phase          | text              | YES
 interaction_modalities_json | text              | YES
 typical_activities_json     | text              | YES
 sentiment_trajectory_json   | text              | YES
 emotions_json               | text              | YES
 dominant_emotion            | text              | YES
 canonical_entity_id         | text              | YES
 source_texts_json           | text              | YES
 embedding_text              | text              | YES
 embedding_vector            | bytea             | YES
 embedding_model             | text              | YES
(43 rows)
```

**Sample Data** (showing 10 of 22 rows):
```
relationship_id     |  tenant_id  |  space_id  | actor_a_id | actor_b_id | version | supersedes_id | is_canonical | relationship_type | relationship_subtype | relationship_label | interaction_count | avg_sentiment | relationship_strength | intimacy_level | first_interaction_at | last_interaction_at | interaction_frequency |                                                                                                                                                                                                                                       source_episodes_json                                                                                                                                                                                                                                       | observation_count | confidence_score | decay_factor | archival_status |  created_at   |  updated_at   |  valid_from   | valid_to | merge_cascade_id | ultrabert_relation_types | emotional_role | emotional_valence_avg | emotional_valence_trend | relationship_phase | interaction_modalities_json |      typical_activities_json       |                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         sentiment_trajectory_json                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          |                                                                         emotions_json                                                                         | dominant_emotion | canonical_entity_id  | source_texts_json | embedding_text | embedding_vector | embedding_model  
-------------------------+-------------+------------+------------+------------+---------+---------------+--------------+-------------------+----------------------+--------------------+-------------------+---------------+-----------------------+----------------+----------------------+---------------------+-----------------------+--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+-------------------+------------------+--------------+-----------------+---------------+---------------+---------------+----------+------------------+--------------------------+----------------+-----------------------+-------------------------+--------------------+-----------------------------+------------------------------------+--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+---------------------------------------------------------------------------------------------------------------------------------------------------------------+------------------+----------------------+-------------------+----------------+------------------+------------------
 social_a2ca0d40a0e46681 | tenant-test | space-home | Prince     | Emma       |       1 |               | t            | FRIEND            |                      | Emma               |                12 |             0 |                   0.8 | LOW            |        1768537490616 |       1768537490616 |                       | ["c0326faa-4a8c-4050-9f86-4d1bd5677fd9", "aaf6b89a-6e1e-44ca-8fc8-f209a5a23d08", "6cbc22a6-66dd-4b55-8814-dc1893f2c75f", "c474b007-99c7-4d97-be4c-f693cfe7c73b", "f1f2bd40-62a5-45fb-835d-7a7305ff65e7", "24ecb90e-98cb-40cf-9a5e-854be3a9ac6b", "7869ff59-50b2-4f61-9e12-7740234bd24b", "258c7dc9-b6dd-46e9-858f-675500879df1", "e68f10ba-3379-4f1d-9741-f03120147160", "135f16c4-e742-4244-9b51-0e392b298224", "06172f82-8e8d-49e7-9047-337a3f542ebc", "b97d985b-9181-491f-9306-ce15f718ab0f"] |                 1 |              0.8 |            1 | ACTIVE          | 1768537490616 | 1768537490616 | 1768537490616 |          |                  | []                       | ENERGY_SOURCE  |                     0 |                       0 | STABLE             | ["in_person"]               | ["social", "milestone", "routine"] | [{"event_id": "6cbc22a6-66dd-4b55-8814-dc1893f2c75f", "sentiment": "neutral", "valence": 0.0, "confidence": 0.5, "timestamp": 0}, {"event_id": "c474b007-99c7-4d97-be4c-f693cfe7c73b", "sentiment": "neutral", "valence": 0.0, "confidence": 0.5, "timestamp": 0}, {"event_id": "f1f2bd40-62a5-45fb-835d-7a7305ff65e7", "sentiment": "neutral", "valence": 0.0, "confidence": 0.5, "timestamp": 0}, {"event_id": "24ecb90e-98cb-40cf-9a5e-854be3a9ac6b", "sentiment": "neutral", "valence": 0.0, "confidence": 0.5, "timestamp": 0}, {"event_id": "7869ff59-50b2-4f61-9e12-7740234bd24b", "sentiment": "neutral", "valence": 0.0, "confidence": 0.5, "timestamp": 0}, {"event_id": "258c7dc9-b6dd-46e9-858f-675500879df1", "sentiment": "neutral", "valence": 0.0, "confidence": 0.5, "timestamp": 0}, {"event_id": "e68f10ba-3379-4f1d-9741-f03120147160", "sentiment": "neutral", "valence": 0.0, "confidence": 0.5, "timestamp": 0}, {"event_id": "135f16c4-e742-4244-9b51-0e392b298224", "sentiment": "neutral", "valence": 0.0, "confidence": 0.5, "timestamp": 0}, {"event_id": "06172f82-8e8d-49e7-9047-337a3f542ebc", "sentiment": "neutral", "valence": 0.0, "confidence": 0.5, "timestamp": 0}, {"event_id": "b97d985b-9181-491f-9306-ce15f718ab0f", "sentiment": "neutral", "valence": 0.0, "confidence": 0.5, "timestamp": 0}] | {"joy": 7, "excitement": 5, "pride": 4, "contentment": 3, "togetherness": 1, "neutral": 3, "caring": 1, "hope": 1, "love": 1, "gratitude": 1, "nostalgia": 1} | joy              | cluster_PERSON_emma  |                   |                |                  | ultrabert-v2.1.0
 social_f85e9c0735e716dc | tenant-test | space-home | Prince     | Jake       |       1 |               | t            | FRIEND            |                      | Jake               |                 5 |             0 |                  0.75 | LOW            |        1768537490616 |       1768537490616 |                       | ["6cbc22a6-66dd-4b55-8814-dc1893f2c75f", "24ecb90e-98cb-40cf-9a5e-854be3a9ac6b", "e68f10ba-3379-4f1d-9741-f03120147160", "135f16c4-e742-4244-9b51-0e392b298224", "14a17d97-aaae-481a-95c2-c1022d2ea4d5"]                                                                                                                                                                                                                                                                                         |                 1 |             0.75 |            1 | ACTIVE          | 1768537490616 | 1768537490616 | 1768537490616 |          |                  | []                       | ENERGY_SOURCE  |                     0 |                       0 | STABLE             | ["in_person"]               | ["social", "milestone", "routine"] | [{"event_id": "6cbc22a6-66dd-4b55-8814-dc1893f2c75f", "sentiment": "neutral", "valence": 0.0, "confidence": 0.5, "timestamp": 0}, {"event_id": "24ecb90e-98cb-40cf-9a5e-854be3a9ac6b", "sentiment": "neutral", "valence": 0.0, "confidence": 0.5, "timestamp": 0}, {"event_id": "e68f10ba-3379-4f1d-9741-f03120147160", "sentiment": "neutral", "valence": 0.0, "confidence": 0.5, "timestamp": 0}, {"event_id": "135f16c4-e742-4244-9b51-0e392b298224", "sentiment": "neutral", "valence": 0.0, "confidence": 0.5, "timestamp": 0}, {"event_id": "14a17d97-aaae-481a-95c2-c1022d2ea4d5", "sentiment": "neutral", "valence": 0.0, "confidence": 0.5, "timestamp": 0}]                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      | {"joy": 3, "contentment": 3, "togetherness": 1, "excitement": 2, "neutral": 1, "love": 1, "gratitude": 1, "pride": 1}                                         | joy              | cluster_PERSON_jake  |                   |                |                  | ultrabert-v2.1.0
 social_4fd00dbab586f9de | tenant-test | space-home | Prince     | Sofia      |       1 |               | t            | FRIEND            |                      | Sofia              |                 1 |             0 |                  0.55 | LOW            |        1768537490616 |       1768537490616 |                       | ["c474b007-99c7-4d97-be4c-f693cfe7c73b"]                                                                                                                                                                                                                                                                                                                                                                                                                                                         |                 1 |             0.55 |            1 | ACTIVE          | 1768537490616 | 1768537490616 | 1768537490616 |          |                  | []                       | ENERGY_SOURCE  |                     0 |                       0 | FORMING            | ["in_person"]               | ["social"]                         | [{"event_id": "c474b007-99c7-4d97-be4c-f693cfe7c73b", "sentiment": "neutral", "valence": 0.0, "confidence": 0.5, "timestamp": 0}]                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          | {"joy": 1}                                                                                                                                                    | joy              | cluster_PERSON_sofia |                   |                |                  | ultrabert-v2.1.0
 social_d62eafb707088373 | tenant-test | space-home | Prince     | John       |       1 |               | t            | FRIEND            |                      | John               |                 3 |             0 |                  0.65 | LOW            |        1768537490616 |       1768537490616 |                       | ["fd987ef5-cd1f-4aa0-ba4b-248ad3130db1", "156562eb-446d-4650-be23-17d48f221931", "136ca894-317f-4fe6-b3c1-3796796fde5c"]                                                                                                                                                                                                                                                                                                                                                                         |                 1 |             0.65 |            1 | ACTIVE          | 1768537490616 | 1768537490616 | 1768537490616 |          |                  | []                       |                |                     0 |                       0 | STABLE             | ["in_person"]               | ["work"]                           | [{"event_id": "fd987ef5-cd1f-4aa0-ba4b-248ad3130db1", "sentiment": "neutral", "valence": 0.0, "confidence": 0.5, "timestamp": 0}, {"event_id": "156562eb-446d-4650-be23-17d48f221931", "sentiment": "neutral", "valence": 0.0, "confidence": 0.5, "timestamp": 0}, {"event_id": "136ca894-317f-4fe6-b3c1-3796796fde5c", "sentiment": "neutral", "valence": 0.0, "confidence": 0.5, "timestamp": 0}]                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        | {"neutral": 2, "annoyance": 1, "disappointment": 1, "frustration": 1}                                                                                         | neutral          | cluster_PERSON_john  |                   |                |                  | ultrabert-v2.1.0
 social_727f20506d459852 | tenant-test | space-home | Prince     | Lisa       |       1 |               | t            | FRIEND            |                      | Lisa               |                 2 |             0 |                   0.6 | LOW            |        1768537490616 |       1768537490616 |                       | ["fd987ef5-cd1f-4aa0-ba4b-248ad3130db1", "156562eb-446d-4650-be23-17d48f221931"]                                                                                                                                                                                                                                                                                                                                                                                                                 |                 1 |              0.6 |            1 | ACTIVE          | 1768537490616 | 1768537490616 | 1768537490616 |          |                  | []                       |                |                     0 |                       0 | FORMING            | ["in_person"]               | ["work"]                           | [{"event_id": "fd987ef5-cd1f-4aa0-ba4b-248ad3130db1", "sentiment": "neutral", "valence": 0.0, "confidence": 0.5, "timestamp": 0}, {"event_id": "156562eb-446d-4650-be23-17d48f221931", "sentiment": "neutral", "valence": 0.0, "confidence": 0.5, "timestamp": 0}]                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         | {"neutral": 2}                                                                                                                                                | neutral          | cluster_PERSON_lisa  |                   |                |                  | ultrabert-v2.1.0
 social_2fdf7b19a69d8535 | tenant-test | space-home | Prince     | Mike       |       1 |               | t            | FRIEND            |                      | Mike               |                 3 |             0 |                  0.65 | LOW            |        1768537490616 |       1768537490616 |                       | ["fd987ef5-cd1f-4aa0-ba4b-248ad3130db1", "cb298f1e-4ff5-4599-acbd-113ff0b952d3", "136ca894-317f-4fe6-b3c1-3796796fde5c"]                                                                                                                                                                                                                                                                                                                                                                         |                 1 |             0.65 |            1 | ACTIVE          | 1768537490616 | 1768537490616 | 1768537490616 |          |                  | []                       | CONFIDANT      |                     0 |                       0 | STABLE             | ["in_person"]               | ["work"]                           | [{"event_id": "fd987ef5-cd1f-4aa0-ba4b-248ad3130db1", "sentiment": "neutral", "valence": 0.0, "confidence": 0.5, "timestamp": 0}, {"event_id": "cb298f1e-4ff5-4599-acbd-113ff0b952d3", "sentiment": "neutral", "valence": 0.0, "confidence": 0.5, "timestamp": 0}, {"event_id": "136ca894-317f-4fe6-b3c1-3796796fde5c", "sentiment": "neutral", "valence": 0.0, "confidence": 0.5, "timestamp": 0}]                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        | {"neutral": 1, "relief": 1, "annoyance": 1, "disappointment": 1, "frustration": 1}                                                                            | neutral          | cluster_PERSON_mike  |                   |                |                  | ultrabert-v2.1.0
 social_be1253db38b9451e | tenant-test | space-home | Prince     | Sarah      |       1 |               | t            | FRIEND            |                      | Sarah              |                 2 |             0 |                   0.6 | LOW            |        1768537490616 |       1768537490616 |                       | ["f2f6fb5c-1bd5-4a60-bd15-77f151b1a07c", "3d421163-a6fb-4455-b001-8b8a57f5ecff"]                                                                                                                                                                                                                                                                                                                                                                                                                 |                 1 |              0.6 |            1 | ACTIVE          | 1768537490616 | 1768537490616 | 1768537490616 |          |                  | []                       | ENERGY_SOURCE  |                     0 |                       0 | FORMING            | ["in_person"]               | ["work"]                           | [{"event_id": "f2f6fb5c-1bd5-4a60-bd15-77f151b1a07c", "sentiment": "neutral", "valence": 0.0, "confidence": 0.5, "timestamp": 0}, {"event_id": "3d421163-a6fb-4455-b001-8b8a57f5ecff", "sentiment": "neutral", "valence": 0.0, "confidence": 0.5, "timestamp": 0}]                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         | {"neutral": 1, "joy": 1, "excitement": 1, "pride": 1}                                                                                                         | neutral          | cluster_PERSON_sarah |                   |                |                  | ultrabert-v2.1.0
 social_d2f6c81ae0766042 | tenant-test | space-home | Prince     | David      |       1 |               | t            | FRIEND            |                      | David              |                 2 |             0 |                   0.6 | LOW            |        1768537490616 |       1768537490616 |                       | ["fee16c26-9a44-4124-9b85-cb0782d2416f", "0b34ae98-cfbd-43e1-aeb6-a02c7b9eb31a"]                                                                                                                                                                                                                                                                                                                                                                                                                 |                 1 |              0.6 |            1 | ACTIVE          | 1768537490616 | 1768537490616 | 1768537490616 |          |                  | []                       | ENERGY_SOURCE  |                     0 |                       0 | FORMING            | ["in_person"]               | ["work", "routine"]                | [{"event_id": "fee16c26-9a44-4124-9b85-cb0782d2416f", "sentiment": "neutral", "valence": 0.0, "confidence": 0.5, "timestamp": 0}, {"event_id": "0b34ae98-cfbd-43e1-aeb6-a02c7b9eb31a", "sentiment": "neutral", "valence": 0.0, "confidence": 0.5, "timestamp": 0}]                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         | {"joy": 2, "pride": 1, "excitement": 1}                                                                                                                       | joy              | cluster_PERSON_david |                   |                |                  | ultrabert-v2.1.0
 social_f1e364a3a19521fa | tenant-test | space-home | Prince     | Dr. Smith  |       1 |               | t            | FRIEND            |                      | Dr. Smith          |                 2 |             0 |                   0.6 | LOW            |        1768537490616 |       1768537490616 |                       | ["5d1504b0-c807-490a-b0c9-964e219faca3", "75b706da-fc8f-4fc3-a752-865cd4398e59"]                                                                                                                                                                                                                                                                                                                                                                                                                 |                 1 |              0.6 |            1 | ACTIVE          | 1768537490616 | 1768537490616 | 1768537490616 |          |                  | []                       | SUPPORT_GIVER  |                     0 |                       0 | FORMING            | ["in_person"]               | ["routine", "unknown"]             | [{"event_id": "5d1504b0-c807-490a-b0c9-964e219faca3", "sentiment": "neutral", "valence": 0.0, "confidence": 0.5, "timestamp": 0}, {"event_id": "75b706da-fc8f-4fc3-a752-865cd4398e59", "sentiment": "neutral", "valence": 0.0, "confidence": 0.5, "timestamp": 0}]                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         | {"neutral": 2, "worry": 1}                                                                                                                                    | neutral          |                      |                   |                |                  | ultrabert-v2.1.0
 social_f9c2bf662684c3db | tenant-test | space-home | Prince     | Maria      |       1 |               | t            | FRIEND            |                      | Maria              |                 1 |             0 |                  0.55 | LOW            |        1768537490616 |       1768537490616 |                       | ["200177cb-55f6-4d4b-9ad3-45e164bae4ba"]                                                                                                                                                                                                                                                                                                                                                                                                                                                         |                 1 |             0.55 |            1 | ACTIVE          | 1768537490616 | 1768537490616 | 1768537490616 |          |                  | []                       |                |                     0 |                       0 | FORMING            | ["in_person"]               | ["routine"]                        | [{"event_id": "200177cb-55f6-4d4b-9ad3-45e164bae4ba", "sentiment": "neutral", "valence": 0.0, "confidence": 0.5, "timestamp": 0}]                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          | {"neutral": 1}                                                                                                                                                | neutral          | cluster_PERSON_maria |                   |                |                  | ultrabert-v2.1.0
(10 rows)
```

---

### st_relationships

**Row Count**: 0

**Schema**:
```
column_name    | data_type | is_nullable 
-------------------+-----------+-------------
 id                | bigint    | NO
 household_id      | text      | NO
 person_id         | text      | NO
 related_person_id | text      | NO
 relationship_type | text      | NO
 properties_json   | text      | YES
 source_version    | text      | NO
 hydrated_at       | text      | NO
 ttl_seconds       | integer   | NO
(9 rows)
```

*No data*

---

### st_anchors

**Row Count**: 0

**Schema**:
```
column_name     |    data_type     | is_nullable 
---------------------+------------------+-------------
 entity_id           | text             | NO
 attribute           | text             | NO
 tenant_id           | text             | NO
 space_id            | text             | NO
 alpha               | double precision | NO
 beta                | double precision | NO
 confidence          | double precision | YES
 uncertainty         | double precision | YES
 observation_count   | integer          | NO
 first_observed_at   | bigint           | YES
 last_updated_at     | bigint           | NO
 decay_rate          | double precision | NO
 half_life_days      | integer          | NO
 last_drift_check_at | bigint           | YES
 drift_detected      | boolean          | NO
 drift_magnitude     | double precision | YES
 status              | text             | NO
(17 rows)
```

*No data*

---

### st_anchor_observations

**Row Count**: 0

**Schema**:
```
column_name     |    data_type     | is_nullable 
---------------------+------------------+-------------
 id                  | text             | NO
 entity_id           | text             | NO
 attribute           | text             | NO
 tenant_id           | text             | NO
 observed_at         | bigint           | NO
 event_id            | text             | YES
 supports_anchor     | boolean          | NO
 observation_weight  | double precision | NO
 observation_context | text             | YES
(9 rows)
```

*No data*

---

## Procedural Memory

### st_procedural

**Row Count**: 0

**Schema**:
```
column_name        |     data_type     | is_nullable 
--------------------------+-------------------+-------------
 routine_id               | text              | NO
 tenant_id                | text              | NO
 space_id                 | text              | NO
 actor_id                 | text              | NO
 version                  | integer           | NO
 supersedes_id            | text              | YES
 is_canonical             | boolean           | YES
 routine_name             | text              | NO
 routine_category         | text              | YES
 temporal_anchor          | text              | YES
 day_pattern              | text              | YES
 frequency                | text              | YES
 regularity_score         | double precision  | YES
 action_sequence_json     | text              | YES
 typical_duration_minutes | integer           | YES
 source_episodes_json     | text              | NO
 source_episode_count     | integer           | NO
 observation_count        | integer           | YES
 confidence_score         | double precision  | YES
 last_observed_at         | bigint            | YES
 streak_count             | integer           | YES
 streak_broken_at         | bigint            | YES
 decay_factor             | double precision  | YES
 archival_status          | text              | YES
 created_at               | bigint            | NO
 updated_at               | bigint            | NO
 valid_from               | bigint            | NO
 valid_to                 | bigint            | YES
 merge_cascade_id         | character varying | YES
 source_texts_json        | text              | YES
 embedding_text           | text              | YES
 embedding_vector         | bytea             | YES
 embedding_model          | text              | YES
(33 rows)
```

*No data*

---

## Prospective Memory

### st_prospective

**Row Count**: 9

**Schema**:
```
column_name      |    data_type     | is_nullable 
-----------------------+------------------+-------------
 intention_id          | text             | NO
 tenant_id             | text             | NO
 space_id              | text             | NO
 actor_id              | text             | NO
 version               | integer          | NO
 supersedes_id         | text             | YES
 is_canonical          | boolean          | YES
 intention_type        | text             | NO
 intention_description | text             | NO
 target_date           | bigint           | YES
 target_context        | text             | YES
 status                | text             | YES
 inferred_from_json    | text             | YES
 inference_confidence  | double precision | YES
 observation_count     | integer          | YES
 confidence_score      | double precision | YES
 decay_factor          | double precision | YES
 archival_status       | text             | YES
 created_at            | bigint           | NO
 updated_at            | bigint           | NO
 valid_from            | bigint           | NO
 valid_to              | bigint           | YES
 source_texts_json     | text             | YES
 embedding_text        | text             | YES
 embedding_vector      | bytea            | YES
 embedding_model       | text             | YES
(26 rows)
```

**Data**:
```
intention_id                  |  tenant_id  |  space_id  | actor_id | version | supersedes_id | is_canonical | intention_type |                              intention_description                               | target_date |                                  target_context                                  | status |                                                                                                                     inferred_from_json                                                                                                                     | inference_confidence | observation_count | confidence_score | decay_factor | archival_status |  created_at   |  updated_at   |  valid_from   | valid_to | source_texts_json | embedding_text | embedding_vector | embedding_model  
-----------------------------------------------+-------------+------------+----------+---------+---------------+--------------+----------------+----------------------------------------------------------------------------------+-------------+----------------------------------------------------------------------------------+--------+------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+----------------------+-------------------+------------------+--------------+-----------------+---------------+---------------+---------------+----------+-------------------+----------------+------------------+------------------
 reminder_7b730108-9882-40e8-957d-498eb376c83d | tenant-test | space-home | system   |       1 |               | t            | REMINDER       | call Mom                                                                         |             | Remind me to call Mom tomorrow at 3pm for her birthday.                          | ACTIVE | ["7b730108-9882-40e8-957d-498eb376c83d"]                                                                                                                                                                                                                   |                  0.8 |                 1 |              0.8 |            1 | ACTIVE          | 1768537490617 | 1768537490617 | 1768537490617 |          |                   |                |                  | ultrabert-v2.1.0
 reminder_feb734b6-c304-4713-ba80-ec99a8031599 | tenant-test | space-home | system   |       1 |               | t            | REMINDER       | remember to submit the quarterly report by Friday at 5pm                         |             | Need to remember to submit the quarterly report by Friday at 5pm.                | ACTIVE | ["feb734b6-c304-4713-ba80-ec99a8031599"]                                                                                                                                                                                                                   |                  0.8 |                 1 |              0.8 |            1 | ACTIVE          | 1768537490617 | 1768537490617 | 1768537490617 |          |                   |                |                  | ultrabert-v2.1.0
 reminder_7869ff59-50b2-4f61-9e12-7740234bd24b | tenant-test | space-home | system   |       1 |               | t            | REMINDER       | to pick up Emma from soccer practice                                             |             | Set a reminder to pick up Emma from soccer practice at 4:30pm.                   | ACTIVE | ["7869ff59-50b2-4f61-9e12-7740234bd24b"]                                                                                                                                                                                                                   |                  0.8 |                 1 |              0.8 |            1 | ACTIVE          | 1768537490617 | 1768537490617 | 1768537490617 |          |                   |                |                  | ultrabert-v2.1.0
 reminder_2d7705ff-df15-42a8-9323-065e6869ee23 | tenant-test | space-home | system   |       1 |               | t            | REMINDER       | Don't let me forget to water the plants in 2 hours.                              |             | Don't let me forget to water the plants in 2 hours.                              | ACTIVE | ["2d7705ff-df15-42a8-9323-065e6869ee23"]                                                                                                                                                                                                                   |                  0.8 |                 1 |              0.8 |            1 | ACTIVE          | 1768537490617 | 1768537490617 | 1768537490617 |          |                   |                |                  | ultrabert-v2.1.0
 reminder_99221dd6-8664-4a57-991f-bf189a60c41d | tenant-test | space-home | system   |       1 |               | t            | REMINDER       | Remind me next Monday to schedule the dentist appointment.                       |             | Remind me next Monday to schedule the dentist appointment.                       | ACTIVE | ["99221dd6-8664-4a57-991f-bf189a60c41d"]                                                                                                                                                                                                                   |                  0.8 |                 1 |              0.8 |            1 | ACTIVE          | 1768537490617 | 1768537490617 | 1768537490617 |          |                   |                |                  | ultrabert-v2.1.0
 decision_5b0f71f3-8611-4b94-96ed-28983614fe5d | tenant-test | space-home | system   |       1 |               | t            | DECISION       | Should I take the new job offer from Google or stay at my current company?       |             | Should I take the new job offer from Google or stay at my current company?       | ACTIVE | {"decision_options": ["take the new job offer from Google", "stay at my current company"], "decision_context": "Should I take the new job offer from Google or stay at my current company?", "source_event_ids": ["5b0f71f3-8611-4b94-96ed-28983614fe5d"]} |                  0.8 |                 1 |              0.8 |            1 | ACTIVE          | 1768537490617 | 1768537490617 | 1768537490617 |          |                   |                |                  | ultrabert-v2.1.0
 decision_01bb7622-b3af-44d5-8bf0-9f4a3f8be996 | tenant-test | space-home | system   |       1 |               | t            | DECISION       | I'm trying to decide between buying a house in Brooklyn or renting in Manhattan. |             | I'm trying to decide between buying a house in Brooklyn or renting in Manhattan. | ACTIVE | {"decision_options": [], "decision_context": "I'm trying to decide between buying a house in Brooklyn or renting in Manhattan.", "source_event_ids": ["01bb7622-b3af-44d5-8bf0-9f4a3f8be996"]}                                                             |                  0.8 |                 1 |              0.8 |            1 | ACTIVE          | 1768537490617 | 1768537490617 | 1768537490617 |          |                   |                |                  | ultrabert-v2.1.0
 decision_258c7dc9-b6dd-46e9-858f-675500879df1 | tenant-test | space-home | system   |       1 |               | t            | DECISION       | What do you think - should Emma switch from soccer to basketball?                |             | What do you think - should Emma switch from soccer to basketball?                | ACTIVE | {"decision_options": [], "decision_context": "What do you think - should Emma switch from soccer to basketball?", "source_event_ids": ["258c7dc9-b6dd-46e9-858f-675500879df1"]}                                                                            |                  0.8 |                 1 |              0.8 |            1 | ACTIVE          | 1768537490617 | 1768537490617 | 1768537490617 |          |                   |                |                  | ultrabert-v2.1.0
 decision_e38d9d59-5926-4d9b-a0c6-f98f1c8f5158 | tenant-test | space-home | system   |       1 |               | t            | DECISION       | I need advice on whether to invest in stocks or bonds right now.                 |             | I need advice on whether to invest in stocks or bonds right now.                 | ACTIVE | {"decision_options": ["invest in stocks", "bonds right now"], "decision_context": "I need advice on whether to invest in stocks or bonds right now.", "source_event_ids": ["e38d9d59-5926-4d9b-a0c6-f98f1c8f5158"]}                                        |                  0.8 |                 1 |              0.8 |            1 | ACTIVE          | 1768537490617 | 1768537490617 | 1768537490617 |          |                   |                |                  | ultrabert-v2.1.0
(9 rows)
```

---

## Learning & Feedback

### st_learning_queue

**Row Count**: 18

**Schema**:
```
column_name       |    data_type     | is_nullable 
------------------------+------------------+-------------
 id                     | text             | NO
 tenant_id              | text             | NO
 space_id               | text             | NO
 gap_type               | text             | NO
 entity_id              | text             | YES
 related_event_id       | text             | YES
 related_truth_id       | text             | YES
 confidence_score       | double precision | YES
 entropy_score          | double precision | YES
 importance_score       | double precision | YES
 context_json           | text             | YES
 status                 | text             | NO
 created_at             | bigint           | NO
 expires_at             | bigint           | YES
 ready_at               | bigint           | YES
 asked_at               | bigint           | YES
 answered_at            | bigint           | YES
 attempts               | integer          | NO
 max_attempts           | integer          | NO
 last_attempt_at        | bigint           | YES
 resolution_type        | text             | YES
 resolution_data_json   | text             | YES
 consolidation_cycle_id | text             | YES
(23 rows)
```

**Sample Data** (showing 10 of 18 rows):
```

```

---

### st_learned_weights

**Row Count**: 0

**Schema**:
```
column_name    |    data_type     | is_nullable 
-------------------+------------------+-------------
 param_id          | text             | NO
 param_key         | text             | NO
 param_scope       | text             | NO
 scope_id          | text             | YES
 space_id          | text             | NO
 current_value     | double precision | NO
 prior_value       | double precision | NO
 confidence        | double precision | NO
 sample_count      | integer          | NO
 last_updated_at   | bigint           | NO
 version           | integer          | NO
 previous_value    | double precision | YES
 quality_at_update | double precision | YES
 rollback_eligible | boolean          | NO
 created_at        | bigint           | NO
 updated_at        | bigint           | NO
(16 rows)
```

*No data*

---

### st_learned_weights_history

**Row Count**: 0

**Schema**:
```
column_name   |    data_type     | is_nullable 
----------------+------------------+-------------
 history_id     | text             | NO
 param_id       | text             | NO
 space_id       | text             | NO
 version        | integer          | NO
 value          | double precision | NO
 confidence     | double precision | NO
 sample_count   | integer          | NO
 quality_metric | double precision | YES
 created_at     | bigint           | NO
 reason         | text             | YES
(10 rows)
```

*No data*

---

### st_feedback_signals

**Row Count**: 0

**Schema**:
```
column_name        |        data_type         | is_nullable 
---------------------------+--------------------------+-------------
 feedback_id               | text                     | NO
 pipeline_id               | text                     | NO
 tenant_id                 | text                     | NO
 space_id                  | text                     | NO
 signal_class              | text                     | NO
 signal_subtype            | text                     | YES
 source                    | text                     | YES
 source_component          | text                     | YES
 session_id                | text                     | YES
 trace_id                  | text                     | NO
 correlation               | jsonb                    | NO
 provenance                | jsonb                    | NO
 payload                   | jsonb                    | NO
 payload_hash              | text                     | NO
 metadata                  | jsonb                    | NO
 payload_validation_status | text                     | NO
 payload_validation_error  | text                     | YES
 priority                  | double precision         | NO
 received_at               | timestamp with time zone | NO
 event_timestamp           | timestamp with time zone | YES
 processing_status         | text                     | NO
 processed_at              | timestamp with time zone | YES
 consumed_at               | bigint                   | YES
 consumed_by               | text                     | YES
(24 rows)
```

*No data*

---

### st_feedback_quarantine

**Row Count**: 0

**Schema**:
```
column_name     |    data_type     | is_nullable 
---------------------+------------------+-------------
 quarantine_id       | text             | NO
 space_id            | text             | NO
 tenant_id           | text             | NO
 signal_id           | text             | NO
 signal_type         | text             | NO
 signal_payload_json | text             | NO
 quarantine_reason   | text             | NO
 anomaly_score       | double precision | YES
 created_at          | bigint           | NO
 auto_release_at     | bigint           | YES
 decision            | text             | YES
 decided_by          | text             | YES
 decided_at          | bigint           | YES
 decision_reason     | text             | YES
 updated_at          | bigint           | NO
(15 rows)
```

*No data*

---

### st_decay_feedback

**Row Count**: 0

**Schema**:
```
column_name      |    data_type     | is_nullable 
-----------------------+------------------+-------------
 feedback_id           | text             | NO
 memory_id             | text             | NO
 layer                 | text             | NO
 space_id              | text             | NO
 tenant_id             | text             | NO
 event_type            | text             | NO
 inter_access_interval | double precision | YES
 decay_factor_at_event | double precision | YES
 expected_decay        | double precision | YES
 resurrection_needed   | boolean          | YES
 archival_premature    | boolean          | YES
 created_at            | bigint           | NO
 observed_at           | bigint           | NO
(13 rows)
```

*No data*

---

### st_golden_dataset_pairs

**Row Count**: 0

**Schema**:
```
column_name      | data_type | is_nullable 
----------------------+-----------+-------------
 pair_id              | text      | NO
 space_id             | text      | NO
 entity_type          | text      | NO
 input_json           | text      | NO
 expected_output_json | text      | NO
 ground_truth_source  | text      | NO
 is_active            | boolean   | NO
 difficulty           | text      | YES
 tags_json            | text      | YES
 created_at           | bigint    | NO
 updated_at           | bigint    | NO
 created_by           | text      | NO
(12 rows)
```

*No data*

---

## Entity Resolution

### st_entity_merges

**Row Count**: 0

**Schema**:
```
column_name     |     data_type     | is_nullable 
---------------------+-------------------+-------------
 merge_id            | character varying | NO
 tenant_id           | character varying | NO
 space_id            | character varying | NO
 primary_entity_id   | character varying | NO
 secondary_entity_id | character varying | NO
 primary_snapshot    | jsonb             | NO
 secondary_snapshot  | jsonb             | NO
 cascade_counts      | jsonb             | NO
 merge_reason        | character varying | NO
 initiated_by        | character varying | NO
 merged_at           | bigint            | NO
 reversed_at         | bigint            | YES
 reversed_by         | character varying | YES
 schema_version      | smallint          | NO
(14 rows)
```

*No data*

---

### st_entity_resolutions

**Row Count**: 0

**Schema**:
```
column_name     |     data_type     | is_nullable 
---------------------+-------------------+-------------
 resolution_id       | character varying | NO
 tenant_id           | character varying | NO
 space_id            | character varying | NO
 mention             | character varying | NO
 selected_entity_id  | character varying | YES
 confidence          | double precision  | NO
 outcome             | character varying | NO
 breakdown_json      | text              | YES
 candidates_count    | integer           | NO
 session_id          | character varying | YES
 event_id            | character varying | YES
 feedback_received   | boolean           | NO
 corrected_entity_id | character varying | YES
 feedback_at_ms      | bigint            | YES
 created_at          | bigint            | NO
 updated_at          | bigint            | YES
(16 rows)
```

*No data*

---

### st_pruned_entities

**Row Count**: 0

**Schema**:
```
column_name      |    data_type     | is_nullable 
-----------------------+------------------+-------------
 prune_id              | text             | NO
 entity_id             | text             | NO
 entity_type           | text             | NO
 canonical_name        | text             | NO
 embedding             | text             | NO
 space_id              | text             | NO
 layer_table           | text             | NO
 decay_factor_at_prune | double precision | NO
 lambda_at_prune       | double precision | NO
 pruned_at             | bigint           | NO
 matched_query_id      | text             | YES
 matched_at            | bigint           | YES
 match_type            | text             | YES
 match_confidence      | double precision | YES
(14 rows)
```

*No data*

---

## Pipeline State

### st_offsets

**Row Count**: 1

**Schema**:
```
column_name  | data_type | is_nullable 
---------------+-----------+-------------
 subscriber_id | text      | NO
 topic         | text      | NO
 space_id      | text      | NO
 tenant_id     | text      | NO
 offset        | bigint    | NO
 updated_ts    | text      | NO
(6 rows)
```

**Data**:
```
subscriber_id |      topic      |  space_id  |  tenant_id  |        offset        |            updated_ts            
---------------+-----------------+------------+-------------+----------------------+----------------------------------
 p03           | p02.hipp_events | space-home | tenant-test | -1335237491063049721 | 2026-01-16T04:24:51.172071+00:00
(1 row)
```

---

### st_pipeline_status

**Row Count**: 0

**Schema**:
```
column_name | data_type | is_nullable 
-------------+-----------+-------------
 pipeline_id | text      | NO
 wal_pos     | bigint    | NO
 status      | text      | NO
 duration_ms | integer   | YES
 error_kind  | text      | YES
 error_msg   | text      | YES
 updated_at  | bigint    | NO
(7 rows)
```

*No data*

---

### st_pipeline_watermarks

**Row Count**: 0

**Schema**:
```
column_name | data_type | is_nullable 
-------------+-----------+-------------
 pipeline_id | text      | NO
 space_id    | text      | NO
 watermark   | bigint    | NO
 updated_at  | bigint    | NO
(4 rows)
```

*No data*

---

### st_pipeline_processed

**Row Count**: 4,952

**Schema**:
```
column_name  | data_type | is_nullable 
--------------+-----------+-------------
 pipeline_id  | text      | NO
 space_id     | text      | NO
 wal_pos      | bigint    | NO
 processed_at | bigint    | NO
(4 rows)
```

**Sample Data** (showing 10 of 4,952 rows):
```
pipeline_id |  space_id  | wal_pos | processed_at 
-------------+------------+---------+--------------
 P02_WRITE   | space-home |    2031 |   1768291374
 P02_WRITE   | space-home |    2032 |   1768291374
 P02_WRITE   | space-home |    2033 |   1768291374
 P02_WRITE   | space-home |    2034 |   1768291375
 P02_WRITE   | space-home |    2035 |   1768291375
 P02_WRITE   | space-home |    2036 |   1768291375
 P02_WRITE   | space-home |    2037 |   1768291375
 P02_WRITE   | space-home |    2038 |   1768291375
 P02_WRITE   | space-home |    2039 |   1768291375
 P02_WRITE   | space-home |    2040 |   1768291375
(10 rows)
```

---

### st_consolidation_audit

**Row Count**: 0

**Schema**:
```
column_name    |    data_type     | is_nullable 
-------------------+------------------+-------------
 audit_id          | text             | NO
 memory_id         | text             | NO
 source_table      | text             | NO
 action            | text             | NO
 formula_used      | text             | YES
 formula_version   | text             | YES
 inputs_json       | text             | YES
 outputs_json      | text             | YES
 explanation       | text             | YES
 decision_id       | text             | YES
 space_id          | text             | NO
 tenant_id         | text             | NO
 cycle_id          | text             | YES
 confidence        | double precision | YES
 created_at        | bigint           | NO
 threshold_used    | double precision | YES
 threshold_name    | text             | YES
 outcome_evaluated | boolean          | YES
 outcome_success   | boolean          | YES
 evaluated_at      | bigint           | YES
(20 rows)
```

*No data*

---

## Infrastructure

### st_devices

**Row Count**: 2

**Schema**:
```
column_name   | data_type | is_nullable 
----------------+-----------+-------------
 device_id      | text      | NO
 tenant_id      | text      | NO
 space_id       | text      | NO
 mls_group_id   | text      | NO
 provisioned_ts | text      | NO
 hmac_secret    | bytea     | YES
(6 rows)
```

**Data**:
```
device_id     |  tenant_id  |  space_id  | mls_group_id |          provisioned_ts          |                            hmac_secret                             
-------------------+-------------+------------+--------------+----------------------------------+--------------------------------------------------------------------
 device-reallife-1 | tenant-test | space-home | mls-group-1  | 2026-01-15T17:08:53.248961+00:00 | \x822d5b0ad6299c0b07ff54c0d0f0fae9e82711451e94d7715ec7fb482953b125
 device-test-1     | tenant-test | space-home | mls-group-1  | 2026-01-16T04:24:24.476665+00:00 | \xfb5d4edf814e959e8d269cdcdef6fc4529d24b8cfac7d350d9f0281d0d4d2606
(2 rows)
```

---

### st_device_keys

**Row Count**: 2

**Schema**:
```
column_name    | data_type | is_nullable 
-------------------+-----------+-------------
 device_id         | text      | NO
 key_version       | text      | NO
 verify_key        | text      | NO
 key_state         | text      | NO
 registered_ts     | text      | NO
 activated_ts      | text      | YES
 rotated_ts        | text      | YES
 revoked_ts        | text      | YES
 grace_expires_ts  | text      | YES
 revocation_reason | text      | YES
(10 rows)
```

**Data**:
```
device_id     | key_version |                 verify_key                  | key_state |          registered_ts           |           activated_ts           | rotated_ts | revoked_ts | grace_expires_ts | revocation_reason 
-------------------+-------------+---------------------------------------------+-----------+----------------------------------+----------------------------------+------------+------------+------------------+-------------------
 device-reallife-1 | 1           | Qj2xg0985y8_rDZD8B7LDeFddvuh4-ToTCLXAUu4Glw | ACTIVE    | 2026-01-15T17:08:53.248961+00:00 | 2026-01-15T17:08:53.248961+00:00 |            |            |                  | 
 device-test-1     | 1           | QLBkMpHquaWgWRXgLTOKO2vwJbjsi5IofwoSqjnrV6Y | ACTIVE    | 2026-01-16T04:24:24.476665+00:00 | 2026-01-16T04:24:24.476665+00:00 |            |            |                  | 
(2 rows)
```

---

### st_acl

**Row Count**: 0

**Schema**:
```
column_name   | data_type | is_nullable 
----------------+-----------+-------------
 acl_id         | text      | NO
 resource_type  | text      | NO
 resource_id    | text      | NO
 principal_type | text      | NO
 principal_id   | text      | NO
 permission     | text      | NO
 privacy_band   | text      | YES
 granted_at     | text      | NO
 granted_by     | text      | NO
 expires_at     | text      | YES
 revoked_at     | text      | YES
(11 rows)
```

*No data*

---

### st_retention_policy

**Row Count**: 0

**Schema**:
```
column_name     | data_type | is_nullable 
--------------------+-----------+-------------
 policy_id          | text      | NO
 policy_name        | text      | NO
 resource_type      | text      | NO
 privacy_band       | text      | YES
 retention_days     | integer   | NO
 archive_enabled    | boolean   | YES
 archive_after_days | integer   | YES
 created_at         | text      | NO
 created_by         | text      | NO
 updated_at         | text      | YES
 enabled            | boolean   | YES
(11 rows)
```

*No data*

---

### st_outbox

**Row Count**: 132

**Schema**:
```
column_name   | data_type | is_nullable 
-----------------+-----------+-------------
 id              | bigint    | NO
 wal_pos         | bigint    | NO
 tenant_id       | text      | NO
 space_id        | text      | NO
 driver          | text      | NO
 op_kind         | text      | NO
 payload         | bytea     | NO
 fingerprint     | text      | NO
 requeue_seq     | integer   | NO
 retries         | integer   | NO
 last_error      | text      | YES
 backoff_exp     | integer   | YES
 status          | text      | YES
 next_attempt_ts | bigint    | YES
(14 rows)
```

**Sample Data** (showing 10 of 132 rows):
```
id   | wal_pos |  tenant_id  |  space_id  | driver |            op_kind            |                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          payload                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           |        fingerprint         | requeue_seq | retries | last_error | backoff_exp | status  | next_attempt_ts 
-------+---------+-------------+------------+--------+-------------------------------+------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+----------------------------+-------------+---------+------------+-------------+---------+-----------------
 57746 |       0 | tenant-test | space-home | p03    | p03.consolidation.complete.v1 | \x7b226379636c655f6964223a202230314b463247525a353343535156314242425033394b4e314848222c202274656e616e745f6964223a202274656e616e742d74657374222c202273706163655f6964223a202273706163652d686f6d65222c202274696d657374616d705f6d73223a20313736383533373439303631372c202273756d6d617279223a207b22746f74616c5f6576656e7473223a2035362c2022636f6e736f6c6964617465645f636f756e74223a2035362c20226475706c69636174655f636f756e74223a20302c20227072756e65645f636f756e74223a20302c202270656e64696e675f7265766965775f636f756e74223a20302c2022616374696f6e5f627265616b646f776e223a207b22435245415445223a2035367d2c20226c617965725f77726974655f636f756e7473223a207b2273745f657069223a20382c202273745f6b675f646f6d223a2037332c202273745f6b675f6564676573223a20342c202273745f70726f7370656374697665223a20392c202273745f73656d223a2036362c202273745f736f6369616c223a2032327d2c20226b675f656e746974795f636f756e74223a2037332c20226b675f656467655f636f756e74223a20342c20226761705f636f756e74223a20302c2022696e73696768745f636f756e74223a20302c2022636f756e7465726661637475616c5f636f756e74223a20302c2022726f7574696e655f6f7074696d697a6174696f6e5f636f756e74223a20302c2022746f74616c5f777269746573223a203138322c20226379636c655f6475726174696f6e5f6d73223a20323037307d2c202270686173655f6475726174696f6e73223a207b7d2c2022746f74616c5f6576656e7473223a2035362c2022746f74616c5f777269746573223a203138322c2022636f6e736f6c6964617465645f636f756e74223a2035362c20226475706c69636174655f636f756e74223a20302c20227072756e65645f636f756e74223a20302c20226761705f636f756e74223a20307d | 01KF2GS15S1XVXGHGJ2Y28N6J5 |           0 |       0 |            |           0 | PENDING |                
 57747 |       0 | tenant-test | space-home | p03    | p03.truth.created.v1          | \x7b226379636c655f6964223a202230314b463247525a353343535156314242425033394b4e314848222c202274656e616e745f6964223a202274656e616e742d74657374222c202273706163655f6964223a202273706163652d686f6d65222c202274696d657374616d705f6d73223a20313736383533373439303631372c20226576656e745f6964223a202263303332366661612d346138632d343035302d396638362d346431626435363737666439222c2022636f6e74656e745f74797065223a2022657069736f646963222c2022696d706f7274616e63655f73636f7265223a20302e32372c2022636c75737465725f6964223a20227765616b2d6538653731393832306233303433666139343237643238393263222c2022726561736f6e223a20224e6f2063616e6469646174657320666f756e6420696e207472757468206c61796572733b206372656174696e67206e6577207265636f7264227d                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         | 01KF2GS15SPSZVDSXMJY102JRR |           0 |       0 |            |           0 | PENDING |                
 57748 |       0 | tenant-test | space-home | p03    | p03.pattern.detected.v1       | \x7b226379636c655f6964223a202230314b463247525a353343535156314242425033394b4e314848222c202274656e616e745f6964223a202274656e616e742d74657374222c202273706163655f6964223a202273706163652d686f6d65222c202274696d657374616d705f6d73223a20313736383533373439303631372c20226576656e745f6964223a202263303332366661612d346138632d343035302d396638362d346431626435363737666439222c20227061747465726e5f6964223a202273656d5f63303332366661612d346138632d343035302d396638362d346431626435363737666439222c2022636f6e74656e745f74797065223a2022657069736f646963222c2022636f6e666964656e6365223a20302e3534357d                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             | 01KF2GS15SHT09EW9HCQVVH928 |           0 |       0 |            |           0 | PENDING |                
 57749 |       0 | tenant-test | space-home | p03    | p03.truth.created.v1          | \x7b226379636c655f6964223a202230314b463247525a353343535156314242425033394b4e314848222c202274656e616e745f6964223a202274656e616e742d74657374222c202273706163655f6964223a202273706163652d686f6d65222c202274696d657374616d705f6d73223a20313736383533373439303631372c20226576656e745f6964223a202261616636623839612d366531652d343463612d386663382d663230396135613233643038222c2022636f6e74656e745f74797065223a2022657069736f646963222c2022696d706f7274616e63655f73636f7265223a20302e32372c2022636c75737465725f6964223a20227765616b2d6538653731393832306233303433666139343237643238393263222c2022726561736f6e223a20224e6f2063616e6469646174657320666f756e6420696e207472757468206c61796572733b206372656174696e67206e6577207265636f7264227d                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         | 01KF2GS15SKE16YDRQYZPRS3F2 |           0 |       0 |            |           0 | PENDING |                
 57750 |       0 | tenant-test | space-home | p03    | p03.pattern.detected.v1       | \x7b226379636c655f6964223a202230314b463247525a353343535156314242425033394b4e314848222c202274656e616e745f6964223a202274656e616e742d74657374222c202273706163655f6964223a202273706163652d686f6d65222c202274696d657374616d705f6d73223a20313736383533373439303631372c20226576656e745f6964223a202261616636623839612d366531652d343463612d386663382d663230396135613233643038222c20227061747465726e5f6964223a202273656d5f61616636623839612d366531652d343463612d386663382d663230396135613233643038222c2022636f6e74656e745f74797065223a2022657069736f646963222c2022636f6e666964656e6365223a20302e3534357d                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             | 01KF2GS15SSRW9Y3HTG43KA111 |           0 |       0 |            |           0 | PENDING |                
 57751 |       0 | tenant-test | space-home | p03    | p03.truth.created.v1          | \x7b226379636c655f6964223a202230314b463247525a353343535156314242425033394b4e314848222c202274656e616e745f6964223a202274656e616e742d74657374222c202273706163655f6964223a202273706163652d686f6d65222c202274696d657374616d705f6d73223a20313736383533373439303631372c20226576656e745f6964223a202236636263323261362d363664642d346235352d383831342d646331383933663263373566222c2022636f6e74656e745f74797065223a2022657069736f646963222c2022696d706f7274616e63655f73636f7265223a20302e3232352c2022636c75737465725f6964223a20227765616b2d6538653731393832306233303433666139343237643238393263222c2022726561736f6e223a20224e6f2063616e6469646174657320666f756e6420696e207472757468206c61796572733b206372656174696e67206e6577207265636f7264227d                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       | 01KF2GS15SP7VZDESQJ4071TGM |           0 |       0 |            |           0 | PENDING |                
 57752 |       0 | tenant-test | space-home | p03    | p03.pattern.detected.v1       | \x7b226379636c655f6964223a202230314b463247525a353343535156314242425033394b4e314848222c202274656e616e745f6964223a202274656e616e742d74657374222c202273706163655f6964223a202273706163652d686f6d65222c202274696d657374616d705f6d73223a20313736383533373439303631372c20226576656e745f6964223a202236636263323261362d363664642d346235352d383831342d646331383933663263373566222c20227061747465726e5f6964223a202273656d5f36636263323261362d363664642d346235352d383831342d646331383933663263373566222c2022636f6e74656e745f74797065223a2022657069736f646963222c2022636f6e666964656e6365223a20302e3534357d                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             | 01KF2GS15S944NTWNJWCF1C862 |           0 |       0 |            |           0 | PENDING |                
 57753 |       0 | tenant-test | space-home | p03    | p03.truth.created.v1          | \x7b226379636c655f6964223a202230314b463247525a353343535156314242425033394b4e314848222c202274656e616e745f6964223a202274656e616e742d74657374222c202273706163655f6964223a202273706163652d686f6d65222c202274696d657374616d705f6d73223a20313736383533373439303631372c20226576656e745f6964223a202263343734623030372d393963372d346439372d626534632d663639336366653763373362222c2022636f6e74656e745f74797065223a2022657069736f646963222c2022696d706f7274616e63655f73636f7265223a20302e3232352c2022636c75737465725f6964223a20227765616b2d6538653731393832306233303433666139343237643238393263222c2022726561736f6e223a20224e6f2063616e6469646174657320666f756e6420696e207472757468206c61796572733b206372656174696e67206e6577207265636f7264227d                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       | 01KF2GS15S9HES36014TFREYFV |           0 |       0 |            |           0 | PENDING |                
 57754 |       0 | tenant-test | space-home | p03    | p03.pattern.detected.v1       | \x7b226379636c655f6964223a202230314b463247525a353343535156314242425033394b4e314848222c202274656e616e745f6964223a202274656e616e742d74657374222c202273706163655f6964223a202273706163652d686f6d65222c202274696d657374616d705f6d73223a20313736383533373439303631372c20226576656e745f6964223a202263343734623030372d393963372d346439372d626534632d663639336366653763373362222c20227061747465726e5f6964223a202273656d5f63343734623030372d393963372d346439372d626534632d663639336366653763373362222c2022636f6e74656e745f74797065223a2022657069736f646963222c2022636f6e666964656e6365223a20302e3534357d                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             | 01KF2GS15S7JC79T6KQ4A9B9S8 |           0 |       0 |            |           0 | PENDING |                
 57755 |       0 | tenant-test | space-home | p03    | p03.truth.created.v1          | \x7b226379636c655f6964223a202230314b463247525a353343535156314242425033394b4e314848222c202274656e616e745f6964223a202274656e616e742d74657374222c202273706163655f6964223a202273706163652d686f6d65222c202274696d657374616d705f6d73223a20313736383533373439303631382c20226576656e745f6964223a202266643938376566352d636431662d346161302d626134622d323438616433313330646231222c2022636f6e74656e745f74797065223a2022657069736f646963222c2022696d706f7274616e63655f73636f7265223a20302e31352c2022636c75737465725f6964223a20227765616b2d3563633863653762653565303466626461336433393636633236222c2022726561736f6e223a20224e6f2063616e6469646174657320666f756e6420696e207472757468206c61796572733b206372656174696e67206e6577207265636f7264227d                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         | 01KF2GS15TCXWE4EWNRGCE47A3 |           0 |       0 |            |           0 | PENDING |                
(10 rows)
```

---

### st_dlq

**Row Count**: 0

**Schema**:
```
column_name    | data_type | is_nullable 
-------------------+-----------+-------------
 id                | bigint    | NO
 wal_pos           | bigint    | YES
 tenant_id         | text      | NO
 space_id          | text      | NO
 driver            | text      | NO
 op_kind           | text      | NO
 fingerprint       | text      | NO
 payload           | bytea     | NO
 reason            | text      | NO
 retries           | integer   | NO
 requeue_seq       | integer   | NO
 first_failure_ts  | text      | NO
 last_failure_ts   | text      | NO
 state             | text      | NO
 next_attempt_ts   | text      | YES
 backoff_exp       | integer   | YES
 error_kind        | text      | YES
 error_fingerprint | text      | YES
 pipeline_id       | text      | YES
 phase             | text      | YES
 event_id          | text      | YES
 entity_id         | text      | YES
 error_type        | text      | YES
 error_code        | text      | YES
 stack_trace       | text      | YES
 max_attempts      | integer   | YES
 resolved_at       | bigint    | YES
 resolved_by       | text      | YES
 resolution_notes  | text      | YES
 updated_at        | bigint    | YES
(30 rows)
```

*No data*

---

### st_wal

**Row Count**: 6,982

**Schema**:
```
column_name      | data_type | is_nullable 
----------------------+-----------+-------------
 pos                  | bigint    | NO
 tenant_id            | text      | NO
 space_id             | text      | NO
 topic                | text      | NO
 envelope_json        | text      | NO
 body                 | bytea     | YES
 payload_sha256       | text      | YES
 schema_uri           | text      | NO
 schema_version       | text      | NO
 idem_key             | text      | YES
 device_id            | text      | NO
 commit_ts            | text      | NO
 redacted_body_json   | text      | YES
 envelope_id          | text      | YES
 content_type         | text      | YES
 encryption_scheme    | text      | YES
 envelope_sha256      | text      | YES
 ingested_at          | text      | YES
 clock_skew_ms        | integer   | YES
 policy_stamp_json    | text      | YES
 location_geohash     | text      | YES
 location_precision_m | integer   | YES
(22 rows)
```

**Sample Data** (showing 10 of 6,982 rows):
```
pos |  tenant_id  |  space_id  |    topic     |                                                                                                                                                                                                                                                                                                                                                                                                                                                           envelope_json                                                                                                                                                                                                                                                                                                                                                                                                                                                            |                                                                                                                                                                                                                                                                                                                                                                                      body                                                                                                                                                                                                                                                                                                                                                                                      |                          payload_sha256                          |      schema_uri       | schema_version |               idem_key                |   device_id   |          commit_ts          | redacted_body_json | envelope_id | content_type | encryption_scheme | envelope_sha256 | ingested_at | clock_skew_ms |                                                                policy_stamp_json                                                                | location_geohash | location_precision_m 
-----+-------------+------------+--------------+------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+------------------------------------------------------------------+-----------------------+----------------+---------------------------------------+---------------+-----------------------------+--------------------+-------------+--------------+-------------------+-----------------+-------------+---------------+-------------------------------------------------------------------------------------------------------------------------------------------------+------------------+----------------------
   1 | tenant-test | space-home | memory.delta | {"actor":"actor-test-1","band":"GREEN","cognitive_trace_id":"262112b7-0722-4d8d-be36-9644e844e8a5","device_id":"device-test-1","envelope_sha256":"1c82a19c1be58784e557599cf1df0ef38252781920f984f67e5d496f6de1aa9d","idem_key":"idem:2942cb3d1cde91e9431a321f79c0a766","payload_bytes":362,"payload_sha256":"b766ead0583a877d7bc775bbe1e6f310fd9463b3f974b998f51cf4a0d689aa18","policy":{"abac":{"roles":["guest"]}},"policy_stamp":{"band":"GREEN","decision":"ALLOW","obligations":[],"policy_version":"2beecb087a8c0bed806352bf3b575a7e0eb04bd6736ef569b6fa541f107d66ec"},"policy_version":"2025-09-28","schema_uri":"schema://memory.delta","schema_version":"1.0","sig":"ZzWh_HhyW3qjtrLWniiWXrXnm_xc6BgbMUamVm70-wRbrlp2dHPmEs9EKjfWzYTof4FqLgbl6f7VRK0EmLHQCQ","sig_alg":"Ed25519SHA512","sig_kid":"device-test-1#1","space_id":"space-home","tenant_id":"tenant-test","topic":"memory.delta","ts":"2026-01-09T07:31:51Z"}  | \x7b2261637469766974795f74797065223a2246414d494c59222c226576656e745f74696d65223a22323032362d30312d30395430373a32323a31332e3639353233322b30303a3030222c226576656e745f74696d655f757463223a22323032362d30312d30395430373a32323a31332e3639353233322b30303a3030222c226c6f636174696f6e5f6e616d65223a22436974792053706f72747320436f6d706c6578222c226f7065726174696f6e223a22555053455254222c227061727469636970616e7473223a5b22456d6d61225d2c2274657874223a225069636b656420757020456d6d612066726f6d20736f6363657220707261637469636520617420436974792053706f72747320436f6d706c65782e205368652073636f726564203220676f616c7320746f64617921222c2274696d657374616d70223a22323032362d30312d30395430373a32323a31332e3639353233322b30303a3030222c2276616c7565223a31307d                         | b766ead0583a877d7bc775bbe1e6f310fd9463b3f974b998f51cf4a0d689aa18 | schema://memory.delta | 1.0            | idem:2942cb3d1cde91e9431a321f79c0a766 | device-test-1 | 2026-01-09T07:31:51.291867Z |                    |             |              |                   |                 |             |               | {"band": "GREEN", "obligations": [], "decision": "ALLOW", "policy_version": "2beecb087a8c0bed806352bf3b575a7e0eb04bd6736ef569b6fa541f107d66ec"} |                  |                     
   2 | tenant-test | space-home | memory.delta | {"actor":"actor-test-2","band":"GREEN","cognitive_trace_id":"64dd7371-0867-4170-9748-b871e3f152e3","device_id":"device-test-1","envelope_sha256":"2e4a76785660b46cb4d86bbf591148b9f960f239e6d1f9345308576b87814de5","idem_key":"idem:22e7e2805c5e67c54a1e13eb8be9332b","payload_bytes":345,"payload_sha256":"f884a653fc18d683f2ff70e6b2bdfe45e6d057cbdabfb149864ace87a32d2f3b","policy":{"abac":{"roles":["guest"]}},"policy_stamp":{"band":"GREEN","decision":"ALLOW","obligations":[],"policy_version":"2beecb087a8c0bed806352bf3b575a7e0eb04bd6736ef569b6fa541f107d66ec"},"policy_version":"2025-09-28","schema_uri":"schema://memory.delta","schema_version":"1.0","sig":"ZJjz7blCQmBpbrjKLuFgRlduL-rt1Afasqfy5BY4k2onuOnI1S9ELtuVM0UJO6uLdDO4M37l9Q26xQfIiUIxBg","sig_alg":"Ed25519SHA512","sig_kid":"device-test-1#1","space_id":"space-home","tenant_id":"tenant-test","topic":"memory.delta","ts":"2026-01-09T07:31:51Z"}  | \x7b2261637469766974795f74797065223a2246414d494c59222c226576656e745f74696d65223a22323032362d30312d30395430373a33303a35332e3434303634302b30303a3030222c226576656e745f74696d655f757463223a22323032362d30312d30395430373a33303a35332e3434303634302b30303a3030222c226c6f636174696f6e5f6e616d65223a224c696e636f6c6e205363686f6f6c222c226f7065726174696f6e223a22555053455254222c227061727469636970616e7473223a5b22456d6d61225d2c2274657874223a22456d6d612773207069616e6f207265636974616c206174204c696e636f6c6e205363686f6f6c2e2053686520706c617965642046757220456c6973652062656175746966756c6c792e222c2274696d657374616d70223a22323032362d30312d30395430373a33303a35332e3434303634302b30303a3030222c2276616c7565223a32307d                                                           | f884a653fc18d683f2ff70e6b2bdfe45e6d057cbdabfb149864ace87a32d2f3b | schema://memory.delta | 1.0            | idem:22e7e2805c5e67c54a1e13eb8be9332b | device-test-1 | 2026-01-09T07:31:51.349807Z |                    |             |              |                   |                 |             |               | {"band": "GREEN", "obligations": [], "decision": "ALLOW", "policy_version": "2beecb087a8c0bed806352bf3b575a7e0eb04bd6736ef569b6fa541f107d66ec"} |                  |                     
   3 | tenant-test | space-home | memory.delta | {"actor":"actor-test-3","band":"GREEN","cognitive_trace_id":"2d739ff5-5797-4c58-981b-51075d4e33a1","device_id":"device-test-1","envelope_sha256":"6e1de9379d82637ae11932a0597e2c9af53391565f80dd38eeede487b410d383","idem_key":"idem:6da3b088ebc294c40558bc525b29b8d2","payload_bytes":333,"payload_sha256":"41df2c6343c944a6a9a7b25a2c9c9604551855b5bf15fb474137f051ef2ebffe","policy":{"abac":{"roles":["guest"]}},"policy_stamp":{"band":"GREEN","decision":"ALLOW","obligations":[],"policy_version":"2beecb087a8c0bed806352bf3b575a7e0eb04bd6736ef569b6fa541f107d66ec"},"policy_version":"2025-09-28","schema_uri":"schema://memory.delta","schema_version":"1.0","sig":"j8ISsdnTj62_ZQST_NayIGEUvZM6F0EDHtWSVRCN7qneJhO01XuF7GfRkTSuJDtuhUZVG0TQJL-3kBAhAFSwCA","sig_alg":"Ed25519SHA512","sig_kid":"device-test-1#1","space_id":"space-home","tenant_id":"tenant-test","topic":"memory.delta","ts":"2026-01-09T07:31:51Z"}  | \x7b2261637469766974795f74797065223a2246414d494c59222c226576656e745f74696d65223a22323032362d30312d30395430373a32353a35302e3933393434382b30303a3030222c226576656e745f74696d655f757463223a22323032362d30312d30395430373a32353a35302e3933393434382b30303a3030222c226c6f636174696f6e5f6e616d65223a22486f6d65222c226f7065726174696f6e223a22555053455254222c227061727469636970616e7473223a5b22456d6d61222c224a616b65225d2c2274657874223a2246616d696c792064696e6e6572207769746820456d6d6120616e64204a616b6520617420686f6d652e204d616465206c617361676e6120746f6765746865722e222c2274696d657374616d70223a22323032362d30312d30395430373a32353a35302e3933393434382b30303a3030222c2276616c7565223a33307d                                                                                   | 41df2c6343c944a6a9a7b25a2c9c9604551855b5bf15fb474137f051ef2ebffe | schema://memory.delta | 1.0            | idem:6da3b088ebc294c40558bc525b29b8d2 | device-test-1 | 2026-01-09T07:31:51.402755Z |                    |             |              |                   |                 |             |               | {"band": "GREEN", "obligations": [], "decision": "ALLOW", "policy_version": "2beecb087a8c0bed806352bf3b575a7e0eb04bd6736ef569b6fa541f107d66ec"} |                  |                     
   4 | tenant-test | space-home | memory.delta | {"actor":"actor-test-4","band":"GREEN","cognitive_trace_id":"f628988f-b865-492b-bf7d-2dca8c4d4f12","device_id":"device-test-1","envelope_sha256":"7b9d5942ee4796d66fc5dcfab0300fa5f17aa49a7d5d8c56fc2271d8aab9b630","idem_key":"idem:0d9235af3af2eca794b0c28f60ea6fce","payload_bytes":346,"payload_sha256":"d8d2760100bf303ad8be238d4bde4c0cecba76f816be773a050eaf2c53dd94b6","policy":{"abac":{"roles":["guest"]}},"policy_stamp":{"band":"GREEN","decision":"ALLOW","obligations":[],"policy_version":"2beecb087a8c0bed806352bf3b575a7e0eb04bd6736ef569b6fa541f107d66ec"},"policy_version":"2025-09-28","schema_uri":"schema://memory.delta","schema_version":"1.0","sig":"WgAD-3VithN3W4-d-Z9DUqBqsOl8oOD2I4m22FbHcF7zGDYuiG2c_2ni_RJIeWHtP66dZ_-Y7fBBf_AmedxvAg","sig_alg":"Ed25519SHA512","sig_kid":"device-test-1#1","space_id":"space-home","tenant_id":"tenant-test","topic":"memory.delta","ts":"2026-01-09T07:31:51Z"}  | \x7b2261637469766974795f74797065223a2246414d494c59222c226576656e745f74696d65223a22323032362d30312d30395430373a31373a30332e3938383634382b30303a3030222c226576656e745f74696d655f757463223a22323032362d30312d30395430373a31373a30332e3938383634382b30303a3030222c226c6f636174696f6e5f6e616d65223a22436875636b204520436865657365222c226f7065726174696f6e223a22555053455254222c227061727469636970616e7473223a5b22456d6d61222c22536f666961225d2c2274657874223a2244726f766520456d6d6120746f2068657220667269656e6420536f666961277320626972746864617920706172747920617420436875636b2045204368656573652e222c2274696d657374616d70223a22323032362d30312d30395430373a31373a30332e3938383634382b30303a3030222c2276616c7565223a34307d                                                         | d8d2760100bf303ad8be238d4bde4c0cecba76f816be773a050eaf2c53dd94b6 | schema://memory.delta | 1.0            | idem:0d9235af3af2eca794b0c28f60ea6fce | device-test-1 | 2026-01-09T07:31:51.456302Z |                    |             |              |                   |                 |             |               | {"band": "GREEN", "obligations": [], "decision": "ALLOW", "policy_version": "2beecb087a8c0bed806352bf3b575a7e0eb04bd6736ef569b6fa541f107d66ec"} |                  |                     
   5 | tenant-test | space-home | memory.delta | {"actor":"actor-test-5","band":"GREEN","cognitive_trace_id":"c14c9b17-5fd9-4279-8684-66d06121e1f6","device_id":"device-test-1","envelope_sha256":"7b01772896552532ed7c7d788b9287b760546160a5d11547c6eaf612c4541bc5","idem_key":"idem:fb54cda1327d71a916d4b57bee791ab5","payload_bytes":374,"payload_sha256":"2efa3551c97ee62f3133a0e9ca96c002ea188b2225b4c44ce6ce8bf861e626cb","policy":{"abac":{"roles":["guest"]}},"policy_stamp":{"band":"GREEN","decision":"ALLOW","obligations":[],"policy_version":"2beecb087a8c0bed806352bf3b575a7e0eb04bd6736ef569b6fa541f107d66ec"},"policy_version":"2025-09-28","schema_uri":"schema://memory.delta","schema_version":"1.0","sig":"22npEocU3z-ybHc9f1lcm6oZvvVVxYVeoVq9tuw35CZXmhMPc3_mUJt0xfKlv5R2itBK7JYyQ2DAADmutdzaCg","sig_alg":"Ed25519SHA512","sig_kid":"device-test-1#1","space_id":"space-home","tenant_id":"tenant-test","topic":"memory.delta","ts":"2026-01-09T07:31:51Z"}  | \x7b2261637469766974795f74797065223a22574f524b222c226576656e745f74696d65223a22323032362d30312d30395430373a30303a31322e3032303932392b30303a3030222c226576656e745f74696d655f757463223a22323032362d30312d30395430373a30303a31322e3032303932392b30303a3030222c226c6f636174696f6e5f6e616d65223a224f666669636520436f6e666572656e636520526f6f6d2042222c226f7065726174696f6e223a22555053455254222c227061727469636970616e7473223a5b224a6f686e222c224c697361222c224d696b65225d2c2274657874223a225465616d207374616e647570206d656574696e672077697468204a6f686e2c204c6973612c20616e64204d696b652e2044697363757373656420513220726f61646d6170207072696f7269746965732e222c2274696d657374616d70223a22323032362d30312d30395430373a30303a31322e3032303932392b30303a3030222c2276616c7565223a35307d | 2efa3551c97ee62f3133a0e9ca96c002ea188b2225b4c44ce6ce8bf861e626cb | schema://memory.delta | 1.0            | idem:fb54cda1327d71a916d4b57bee791ab5 | device-test-1 | 2026-01-09T07:31:51.510606Z |                    |             |              |                   |                 |             |               | {"band": "GREEN", "obligations": [], "decision": "ALLOW", "policy_version": "2beecb087a8c0bed806352bf3b575a7e0eb04bd6736ef569b6fa541f107d66ec"} |                  |                     
   6 | tenant-test | space-home | memory.delta | {"actor":"actor-test-6","band":"GREEN","cognitive_trace_id":"1277280d-dacc-4114-9a96-861e897edb50","device_id":"device-test-1","envelope_sha256":"aa539c336740a1e9649001a1842c97b9e27826153415eca56430812820edfa99","idem_key":"idem:ed9a0207eda9535ef6c95ffb97c4a1ac","payload_bytes":343,"payload_sha256":"8f7f1e2c0426c8d57b04aa1dcc9068de869bd4ecf609f59da0b6fc1795d2f4a7","policy":{"abac":{"roles":["guest"]}},"policy_stamp":{"band":"GREEN","decision":"ALLOW","obligations":[],"policy_version":"2beecb087a8c0bed806352bf3b575a7e0eb04bd6736ef569b6fa541f107d66ec"},"policy_version":"2025-09-28","schema_uri":"schema://memory.delta","schema_version":"1.0","sig":"63tAVu4gCSFH5TS3OfltSS07lf9BmIoB208mB1U1t8I9BvD2aeapFT_05PL8IM_38XaLIxZFRXFMbIXOr4oaBA","sig_alg":"Ed25519SHA512","sig_kid":"device-test-1#1","space_id":"space-home","tenant_id":"tenant-test","topic":"memory.delta","ts":"2026-01-09T07:31:51Z"}  | \x7b2261637469766974795f74797065223a22574f524b222c226576656e745f74696d65223a22323032362d30312d30395430363a35383a35322e3634373133372b30303a3030222c226576656e745f74696d655f757463223a22323032362d30312d30395430363a35383a35322e3634373133372b30303a3030222c226c6f636174696f6e5f6e616d65223a2253617261682773204f6666696365222c226f7065726174696f6e223a22555053455254222c227061727469636970616e7473223a5b225361726168225d2c2274657874223a224f6e652d6f6e2d6f6e652077697468206d616e616765722053617261682061626f75742070726f6d6f74696f6e2074696d656c696e6520616e642063617265657220676f616c732e222c2274696d657374616d70223a22323032362d30312d30395430363a35383a35322e3634373133372b30303a3030222c2276616c7565223a36307d                                                               | 8f7f1e2c0426c8d57b04aa1dcc9068de869bd4ecf609f59da0b6fc1795d2f4a7 | schema://memory.delta | 1.0            | idem:ed9a0207eda9535ef6c95ffb97c4a1ac | device-test-1 | 2026-01-09T07:31:51.562690Z |                    |             |              |                   |                 |             |               | {"band": "GREEN", "obligations": [], "decision": "ALLOW", "policy_version": "2beecb087a8c0bed806352bf3b575a7e0eb04bd6736ef569b6fa541f107d66ec"} |                  |                     
   7 | tenant-test | space-home | memory.delta | {"actor":"actor-test-7","band":"GREEN","cognitive_trace_id":"3654234d-091d-4f83-8a27-33477d53b731","device_id":"device-test-1","envelope_sha256":"62fe9fb7c1aa55dd7caf55118af246d0b41b9a0d2b7f99ad52de7492d612c398","idem_key":"idem:1009b900da3a42f198b2da4cedcf16d9","payload_bytes":346,"payload_sha256":"6d6df3686f1a801e26a25afb97528dddf3770de1124f2d7fcd028b21d1e6003b","policy":{"abac":{"roles":["guest"]}},"policy_stamp":{"band":"GREEN","decision":"ALLOW","obligations":[],"policy_version":"2beecb087a8c0bed806352bf3b575a7e0eb04bd6736ef569b6fa541f107d66ec"},"policy_version":"2025-09-28","schema_uri":"schema://memory.delta","schema_version":"1.0","sig":"0ekmORvpj6wYg3HO2h_CqV7MRXymx0b9m0ZrGWfi23zoNybsmuCMIhhKKKhvsmS372X70orS8xpNDhsf3huGCw","sig_alg":"Ed25519SHA512","sig_kid":"device-test-1#1","space_id":"space-home","tenant_id":"tenant-test","topic":"memory.delta","ts":"2026-01-09T07:31:51Z"}  | \x7b2261637469766974795f74797065223a22574f524b222c226576656e745f74696d65223a22323032362d30312d30395430363a35353a30322e3632333535352b30303a3030222c226576656e745f74696d655f757463223a22323032362d30312d30395430363a35353a30322e3632333535352b30303a3030222c226c6f636174696f6e5f6e616d65223a224d61696e20426f617264726f6f6d222c226f7065726174696f6e223a22555053455254222c227061727469636970616e7473223a5b224461766964225d2c2274657874223a2250726573656e74656420717561727465726c7920726573756c747320746f2074686520657865637574697665207465616d2e2043454f2044617669642077617320696d707265737365642e222c2274696d657374616d70223a22323032362d30312d30395430363a35353a30322e3632333535352b30303a3030222c2276616c7565223a37307d                                                         | 6d6df3686f1a801e26a25afb97528dddf3770de1124f2d7fcd028b21d1e6003b | schema://memory.delta | 1.0            | idem:1009b900da3a42f198b2da4cedcf16d9 | device-test-1 | 2026-01-09T07:31:51.613744Z |                    |             |              |                   |                 |             |               | {"band": "GREEN", "obligations": [], "decision": "ALLOW", "policy_version": "2beecb087a8c0bed806352bf3b575a7e0eb04bd6736ef569b6fa541f107d66ec"} |                  |                     
   8 | tenant-test | space-home | memory.delta | {"actor":"actor-test-8","band":"GREEN","cognitive_trace_id":"8c5effc6-caa6-4d0b-be83-49593b677b82","device_id":"device-test-1","envelope_sha256":"2eb6f69a3eae15d2f6c611cdea42a4e397fd1b4b0314f129a03bc9f68f8a534d","idem_key":"idem:8bea2a9a7fa29a48319780c15de8b886","payload_bytes":337,"payload_sha256":"339d1db3593b03c2fd510e3f92e33c247cf7a12bd161459c98790b3f91add564","policy":{"abac":{"roles":["guest"]}},"policy_stamp":{"band":"GREEN","decision":"ALLOW","obligations":[],"policy_version":"2beecb087a8c0bed806352bf3b575a7e0eb04bd6736ef569b6fa541f107d66ec"},"policy_version":"2025-09-28","schema_uri":"schema://memory.delta","schema_version":"1.0","sig":"cXpRFMgOMtwYfO7WkEG5-dHabnR7L_kcRlqwFIVEK8BmtZ2SHABUdRYSCRpB0W3tt4lhLBWocVNldPg-hMBCBw","sig_alg":"Ed25519SHA512","sig_kid":"device-test-1#1","space_id":"space-home","tenant_id":"tenant-test","topic":"memory.delta","ts":"2026-01-09T07:31:51Z"}  | \x7b2261637469766974795f74797065223a22574f524b222c226576656e745f74696d65223a22323032362d30312d30395430363a35313a35302e3937373431342b30303a3030222c226576656e745f74696d655f757463223a22323032362d30312d30395430363a35313a35302e3937373431342b30303a3030222c226c6f636174696f6e5f6e616d65223a224f6666696365222c226f7065726174696f6e223a22555053455254222c227061727469636970616e7473223a5b224d696b65225d2c2274657874223a22436f6465207265766965772073657373696f6e2077697468204d696b652e20466978656420637269746963616c2062756720696e2061757468656e7469636174696f6e206d6f64756c652e222c2274696d657374616d70223a22323032362d30312d30395430363a35313a35302e3937373431342b30303a3030222c2276616c7565223a38307d                                                                           | 339d1db3593b03c2fd510e3f92e33c247cf7a12bd161459c98790b3f91add564 | schema://memory.delta | 1.0            | idem:8bea2a9a7fa29a48319780c15de8b886 | device-test-1 | 2026-01-09T07:31:51.665783Z |                    |             |              |                   |                 |             |               | {"band": "GREEN", "obligations": [], "decision": "ALLOW", "policy_version": "2beecb087a8c0bed806352bf3b575a7e0eb04bd6736ef569b6fa541f107d66ec"} |                  |                     
   9 | tenant-test | space-home | memory.delta | {"actor":"actor-test-9","band":"GREEN","cognitive_trace_id":"f3576973-0ca6-47e9-9c61-3acbac845e5b","device_id":"device-test-1","envelope_sha256":"bda72020afa10bbdce632d010a6416312f88ecaaacafcc4e7b67b329781545a6","idem_key":"idem:b79aacddb3496261e9aa010ec3945720","payload_bytes":340,"payload_sha256":"899b0606cfdea1cd6c0f46d0f66b637ca1f6ae122b0898e5c474ce173c0c4d55","policy":{"abac":{"roles":["guest"]}},"policy_stamp":{"band":"GREEN","decision":"ALLOW","obligations":[],"policy_version":"2beecb087a8c0bed806352bf3b575a7e0eb04bd6736ef569b6fa541f107d66ec"},"policy_version":"2025-09-28","schema_uri":"schema://memory.delta","schema_version":"1.0","sig":"hKyRygMqEw_RSffQZF0_ARkTW2zV5CGAjNpjA5bJU1MN-ClFThL14oR_zdlg1YxyuwAlgr4A2k3wbFiFiPsEAQ","sig_alg":"Ed25519SHA512","sig_kid":"device-test-1#1","space_id":"space-home","tenant_id":"tenant-test","topic":"memory.delta","ts":"2026-01-09T07:31:51Z"}  | \x7b2261637469766974795f74797065223a22574f524b222c226576656e745f74696d65223a22323032362d30312d30395430373a30313a33342e3031363732322b30303a3030222c226576656e745f74696d655f757463223a22323032362d30312d30395430373a30313a33342e3031363732322b30303a3030222c226c6f636174696f6e5f6e616d65223a22436869706f746c65222c226f7065726174696f6e223a22555053455254222c227061727469636970616e7473223a5b224a6f686e222c224c697361225d2c2274657874223a224c756e6368207769746820636f776f726b65727320617420436869706f746c652e2044697363757373656420746865206e65772070726f6a65637420646561646c696e652e222c2274696d657374616d70223a22323032362d30312d30395430373a30313a33342e3031363732322b30303a3030222c2276616c7565223a39307d                                                                     | 899b0606cfdea1cd6c0f46d0f66b637ca1f6ae122b0898e5c474ce173c0c4d55 | schema://memory.delta | 1.0            | idem:b79aacddb3496261e9aa010ec3945720 | device-test-1 | 2026-01-09T07:31:51.717211Z |                    |             |              |                   |                 |             |               | {"band": "GREEN", "obligations": [], "decision": "ALLOW", "policy_version": "2beecb087a8c0bed806352bf3b575a7e0eb04bd6736ef569b6fa541f107d66ec"} |                  |                     
  10 | tenant-test | space-home | memory.delta | {"actor":"actor-test-10","band":"GREEN","cognitive_trace_id":"7feae595-c3c8-4715-a367-b8835120eec7","device_id":"device-test-1","envelope_sha256":"4958ba5e5c4df9dfff0ca964c8fb963983179f1848af2a1188580a213b7ff996","idem_key":"idem:e1248a43b40c6032a30f459e76161199","payload_bytes":331,"payload_sha256":"b166a285fec97a0b8da36459dbd861ded115816aa9c7ba5642611361f0842a74","policy":{"abac":{"roles":["guest"]}},"policy_stamp":{"band":"GREEN","decision":"ALLOW","obligations":[],"policy_version":"2beecb087a8c0bed806352bf3b575a7e0eb04bd6736ef569b6fa541f107d66ec"},"policy_version":"2025-09-28","schema_uri":"schema://memory.delta","schema_version":"1.0","sig":"4Te0x1oXNriTw_w7SM1UfLdKXBkoEgc7J9Q6pU3C4XxjkipBHER_5CkMrEbwzgOMYwiyTjIwSTqif7wfLS0RBw","sig_alg":"Ed25519SHA512","sig_kid":"device-test-1#1","space_id":"space-home","tenant_id":"tenant-test","topic":"memory.delta","ts":"2026-01-09T07:31:51Z"} | \x7b2261637469766974795f74797065223a224845414c5448222c226576656e745f74696d65223a22323032362d30312d30395430363a33303a30342e3535313837382b30303a3030222c226576656e745f74696d655f757463223a22323032362d30312d30395430363a33303a30342e3535313837382b30303a3030222c226c6f636174696f6e5f6e616d65223a2243656e7472616c205061726b222c226f7065726174696f6e223a22555053455254222c227061727469636970616e7473223a5b5d2c2274657874223a224d6f726e696e672072756e2061742043656e7472616c205061726b2e2035206d696c657320696e203432206d696e757465732c206665656c696e6720677265617421222c2274696d657374616d70223a22323032362d30312d30395430363a33303a30342e3535313837382b30303a3030222c2276616c7565223a3130307d                                                                                       | b166a285fec97a0b8da36459dbd861ded115816aa9c7ba5642611361f0842a74 | schema://memory.delta | 1.0            | idem:e1248a43b40c6032a30f459e76161199 | device-test-1 | 2026-01-09T07:31:51.768761Z |                    |             |              |                   |                 |             |               | {"band": "GREEN", "obligations": [], "decision": "ALLOW", "policy_version": "2beecb087a8c0bed806352bf3b575a7e0eb04bd6736ef569b6fa541f107d66ec"} |                  |                     
(10 rows)
```

---

### st_receipts

**Row Count**: 6,982

**Schema**:
```
column_name      | data_type | is_nullable 
----------------------+-----------+-------------
 receipt_id           | text      | NO
 idem_key             | text      | NO
 wal_pos              | bigint    | NO
 commit_ts            | text      | NO
 tenant_id            | text      | NO
 space_id             | text      | NO
 device_id            | text      | NO
 mls_group_id         | text      | NO
 key_version          | text      | NO
 device_sig           | text      | NO
 manifest_fingerprint | text      | YES
(11 rows)
```

**Sample Data** (showing 10 of 6,982 rows):
```
receipt_id              |               idem_key                | wal_pos |          commit_ts          |  tenant_id  |  space_id  |   device_id   | mls_group_id | key_version |                                       device_sig                                       | manifest_fingerprint 
--------------------------------------+---------------------------------------+---------+-----------------------------+-------------+------------+---------------+--------------+-------------+----------------------------------------------------------------------------------------+----------------------
 8cc76d5b-997f-4518-b695-7c74154b5367 | idem:2942cb3d1cde91e9431a321f79c0a766 |       1 | 2026-01-09T07:31:51.291867Z | tenant-test | space-home | device-test-1 | mls-group-1  | 1           | lMnV_4hnCfzAtFWYDb9b9LWT_pEV1hQ_XhSXDWhFGGvWhsd1o2ebCsRiTUPa-1F-o1MEkkcNxME2_sNo7IFkAg | 
 121d674d-0973-4941-8d14-7f6a83d4d0bb | idem:22e7e2805c5e67c54a1e13eb8be9332b |       2 | 2026-01-09T07:31:51.349807Z | tenant-test | space-home | device-test-1 | mls-group-1  | 1           | Utp_U0EXd4s5dt5dYsOBYiNuZIryMUzraK8FvPVaUhz18QGbQgORzqaUiP_4AEO_-rAt-sfCgW_r4MT687PbAQ | 
 9c419466-80a1-4fa8-b0e0-47e348df8a21 | idem:6da3b088ebc294c40558bc525b29b8d2 |       3 | 2026-01-09T07:31:51.402755Z | tenant-test | space-home | device-test-1 | mls-group-1  | 1           | MDlJzlKhwe-1hOqyLGNWRxwVdmgtou7NiIuUyq71utST9FdCfXHTMPlV-DzJJlu5YzVwJ1H1WJn3lonQNuiPCw | 
 f09763fb-fa96-40d5-bdc8-39ace9ab5209 | idem:0d9235af3af2eca794b0c28f60ea6fce |       4 | 2026-01-09T07:31:51.456302Z | tenant-test | space-home | device-test-1 | mls-group-1  | 1           | hXHnFU-cIg7-fKN_TE377kZKixi6czRzel8D3_TysDguLdcPyZycNb280UceySb7fiWONLLmIHUxprV2xE7aAg | 
 630ac4b5-3889-4a09-ad99-7f2e9b0b014f | idem:fb54cda1327d71a916d4b57bee791ab5 |       5 | 2026-01-09T07:31:51.510606Z | tenant-test | space-home | device-test-1 | mls-group-1  | 1           | z_35a1jMtElXs1tOaQLmADquVwRv3Ot_tzPor8Z5FmpQQsVh2ibbo30dGd6VH8uremj_EvjbbRFIGSPNdEnnDQ | 
 b117e66d-5feb-4e16-a054-d954fb647b39 | idem:ed9a0207eda9535ef6c95ffb97c4a1ac |       6 | 2026-01-09T07:31:51.562690Z | tenant-test | space-home | device-test-1 | mls-group-1  | 1           | 4aG7l1yIx9ca1A1HWTDxHWkjC8i4V1q1E41uTnzkZEmE-B3_TrMiP5M3zXBDk31RJInmtKL4FL1x0b1doGJ9AQ | 
 068b7b06-e62a-427e-b7d6-14c1b4b50646 | idem:1009b900da3a42f198b2da4cedcf16d9 |       7 | 2026-01-09T07:31:51.613744Z | tenant-test | space-home | device-test-1 | mls-group-1  | 1           | vkxffm_xfZZx8fO5xmHeLK7zMnXDXlBi0x3uT_BEO_IgzLOcvLnhDnbWfQUjkfiQOy76IeOIcVq8mT32dLufDg | 
 751cb600-07fb-462a-8c6d-88e35d83fe76 | idem:8bea2a9a7fa29a48319780c15de8b886 |       8 | 2026-01-09T07:31:51.665783Z | tenant-test | space-home | device-test-1 | mls-group-1  | 1           | fXkr8vMwEOqHgLctlIr81Sl3X3dpghHXvcmu-M4V22RRyuMisIw172i6ApE6duGu7h3MVBgV3stPQ3_Bb-wUDQ | 
 f39621c2-59c4-41e5-bdab-e91f8a04cfd7 | idem:b79aacddb3496261e9aa010ec3945720 |       9 | 2026-01-09T07:31:51.717211Z | tenant-test | space-home | device-test-1 | mls-group-1  | 1           | h-3s-6qIad0X_eJ6V0A32IofJfGTXoIcSABOM_YuWXDwnfdqlY4WQcDXScxK0yqbnwF7fx6X6Gh_nuWCGLOoBA | 
 d85f39c7-cceb-49fe-a047-6f19231efaa6 | idem:e1248a43b40c6032a30f459e76161199 |      10 | 2026-01-09T07:31:51.768761Z | tenant-test | space-home | device-test-1 | mls-group-1  | 1           | vl6xlkff491mPEVXzfak8wLQzYBK__HddZT7jN5Yf2ZgPsnHNZfAmNUeSf5Qhlsnj5RYUH70HY01NSDy_d3JBA | 
(10 rows)
```

---

### st_validation_results

**Row Count**: 0

**Schema**:
```
column_name     |    data_type     | is_nullable 
---------------------+------------------+-------------
 result_id           | text             | NO
 space_id            | text             | NO
 pair_id             | text             | NO
 actual_output_json  | text             | NO
 is_correct          | boolean          | NO
 similarity_score    | double precision | YES
 error_type          | text             | YES
 error_details_json  | text             | YES
 model_version       | text             | NO
 param_snapshot_json | text             | YES
 created_at          | bigint           | NO
 duration_ms         | integer          | YES
(12 rows)
```

*No data*

---

### st_archive_manifest

**Row Count**: 0

**Schema**:
```
column_name     | data_type | is_nullable 
---------------------+-----------+-------------
 archive_id          | text      | NO
 resource_type       | text      | NO
 resource_id         | text      | NO
 archived_at         | text      | NO
 archive_location    | text      | NO
 archive_size_bytes  | bigint    | YES
 archive_checksum    | text      | YES
 retention_policy_id | text      | YES
 delete_after        | text      | YES
(9 rows)
```

*No data*

---

### st_obligation_log

**Row Count**: 0

**Schema**:
```
column_name  | data_type | is_nullable 
--------------+-----------+-------------
 id           | bigint    | NO
 wal_pos      | bigint    | NO
 obligation   | text      | NO
 details_json | text      | YES
 commit_ts    | text      | NO
 tenant_id    | text      | NO
 space_id     | text      | NO
(7 rows)
```

*No data*

---

### st_crdt_merge_log

**Row Count**: 0

**Schema**:
```
column_name     | data_type | is_nullable 
---------------------+-----------+-------------
 merge_id            | text      | NO
 resource_type       | text      | NO
 resource_id         | text      | NO
 merge_strategy      | text      | NO
 winner_device_id    | text      | NO
 loser_device_id     | text      | YES
 winner_vector_clock | text      | NO
 loser_vector_clock  | text      | YES
 merged_at           | text      | NO
 conflict_reason     | text      | YES
(10 rows)
```

*No data*

---

### st_mcts_decisions

**Row Count**: 0

**Schema**:
```
column_name        |    data_type     | is_nullable 
---------------------------+------------------+-------------
 decision_id               | text             | NO
 cycle_id                  | text             | NO
 decision_type             | text             | NO
 context_json              | jsonb            | YES
 rollouts_allocated        | integer          | YES
 rollouts_executed         | integer          | YES
 early_termination         | boolean          | NO
 termination_reason        | text             | YES
 chosen_action             | text             | YES
 value_estimate            | double precision | YES
 confidence_interval_width | double precision | YES
 compute_ms                | integer          | YES
 created_at                | bigint           | NO
(13 rows)
```

*No data*

---

### st_mcts_shadow_log

**Row Count**: 0

**Schema**:
```
column_name    |    data_type     | is_nullable 
-------------------+------------------+-------------
 decision_id       | text             | NO
 cycle_id          | text             | NO
 decision_type     | text             | NO
 heuristic_choice  | text             | NO
 mcts_choice       | text             | NO
 choices_differ    | boolean          | NO
 context_json      | jsonb            | YES
 applied_choice    | text             | NO
 outcome_heuristic | double precision | YES
 outcome_mcts      | double precision | YES
 mcts_better       | boolean          | YES
 evaluated_at      | bigint           | YES
 created_at        | bigint           | NO
(13 rows)
```

*No data*

---

### idem_ledger

**Row Count**: 6,982

**Schema**:
```
column_name  | data_type | is_nullable 
---------------+-----------+-------------
 idem_key      | text      | NO
 receipt_id    | text      | NO
 first_seen_ts | text      | NO
 state         | text      | NO
 expiry_ts     | text      | YES
(5 rows)
```

**Sample Data** (showing 10 of 6,982 rows):
```
idem_key                |              receipt_id              |        first_seen_ts        |   state   | expiry_ts 
---------------------------------------+--------------------------------------+-----------------------------+-----------+-----------
 idem:2942cb3d1cde91e9431a321f79c0a766 | 8cc76d5b-997f-4518-b695-7c74154b5367 | 2026-01-09T07:31:51.291867Z | COMMITTED | 
 idem:22e7e2805c5e67c54a1e13eb8be9332b | 121d674d-0973-4941-8d14-7f6a83d4d0bb | 2026-01-09T07:31:51.349807Z | COMMITTED | 
 idem:6da3b088ebc294c40558bc525b29b8d2 | 9c419466-80a1-4fa8-b0e0-47e348df8a21 | 2026-01-09T07:31:51.402755Z | COMMITTED | 
 idem:0d9235af3af2eca794b0c28f60ea6fce | f09763fb-fa96-40d5-bdc8-39ace9ab5209 | 2026-01-09T07:31:51.456302Z | COMMITTED | 
 idem:fb54cda1327d71a916d4b57bee791ab5 | 630ac4b5-3889-4a09-ad99-7f2e9b0b014f | 2026-01-09T07:31:51.510606Z | COMMITTED | 
 idem:ed9a0207eda9535ef6c95ffb97c4a1ac | b117e66d-5feb-4e16-a054-d954fb647b39 | 2026-01-09T07:31:51.562690Z | COMMITTED | 
 idem:1009b900da3a42f198b2da4cedcf16d9 | 068b7b06-e62a-427e-b7d6-14c1b4b50646 | 2026-01-09T07:31:51.613744Z | COMMITTED | 
 idem:8bea2a9a7fa29a48319780c15de8b886 | 751cb600-07fb-462a-8c6d-88e35d83fe76 | 2026-01-09T07:31:51.665783Z | COMMITTED | 
 idem:b79aacddb3496261e9aa010ec3945720 | f39621c2-59c4-41e5-bdab-e91f8a04cfd7 | 2026-01-09T07:31:51.717211Z | COMMITTED | 
 idem:e1248a43b40c6032a30f459e76161199 | d85f39c7-cceb-49fe-a047-6f19231efaa6 | 2026-01-09T07:31:51.768761Z | COMMITTED | 
(10 rows)
```

---

## Core Tables

### households

**Row Count**: 0

**Schema**:
```
column_name        |    data_type     | is_nullable 
---------------------------+------------------+-------------
 household_id              | text             | NO
 cognitive_trace_id        | text             | NO
 label                     | text             | NO
 household_type            | text             | YES
 address                   | text             | YES
 timezone                  | text             | YES
 member_count              | integer          | YES
 adult_count               | integer          | YES
 child_count               | integer          | YES
 primary_contact_person_id | text             | YES
 policy_profile            | text             | YES
 retention_defaults        | text             | YES
 privacy_defaults          | text             | YES
 rate_limits               | text             | YES
 storage_quota_gb          | integer          | YES
 storage_used_gb           | double precision | YES
 subscription_tier         | text             | YES
 subscription_status       | text             | YES
 subscription_expires_at   | text             | YES
 billing_email             | text             | YES
 features_enabled          | text             | YES
 experimental_features     | text             | YES
 connected_services        | text             | YES
 connector_count           | integer          | YES
 tenant_id                 | text             | NO
 privacy_band              | text             | NO
 visible_to                | text             | NO
 crdt_vector_clock         | text             | NO
 crdt_tombstone            | integer          | YES
 crdt_lamport              | bigint           | NO
 created_at                | text             | NO
 updated_at                | text             | NO
 onboarded_at              | text             | YES
 last_active_at            | text             | YES
 deactivated_at            | text             | YES
(35 rows)
```

*No data*

---

### people

**Row Count**: 0

**Schema**:
```
column_name     | data_type | is_nullable 
---------------------+-----------+-------------
 person_id           | text      | NO
 cognitive_trace_id  | text      | NO
 label               | text      | NO
 full_name           | text      | YES
 nicknames           | text      | YES
 birth_date          | text      | YES
 relationships       | text      | YES
 household_id        | text      | YES
 household_role      | text      | YES
 visibility_default  | text      | YES
 band_default        | text      | YES
 consent_status      | text      | YES
 merge_keys          | text      | YES
 canonical_person_id | text      | YES
 merged_from         | text      | YES
 primary_device_id   | text      | YES
 registered_devices  | text      | YES
 timezone            | text      | YES
 language            | text      | YES
 contact_preferences | text      | YES
 tenant_id           | text      | NO
 space_id            | text      | NO
 privacy_band        | text      | NO
 owner_id            | text      | NO
 visible_to          | text      | NO
 crdt_vector_clock   | text      | NO
 crdt_tombstone      | integer   | YES
 crdt_lamport        | bigint    | NO
 created_at          | text      | NO
 updated_at          | text      | NO
 onboarded_at        | text      | YES
 last_active_at      | text      | YES
 deactivated_at      | text      | YES
(33 rows)
```

*No data*

---
