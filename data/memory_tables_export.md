  # K0 Memory Tables Export

  **Generated**: 2026-01-13 13:08:28
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
  | Semantic Memory (Knowledge Graph) | `st_kg_dom` | 88 |
  | Semantic Memory (Knowledge Graph) | `st_kg_edges` | 58 |
  | Semantic Memory (Knowledge Graph) | `st_sem` | 66 |
  | Social Memory | `st_social` | 22 |
  | Social Memory | `st_relationships` | 0 |
  | Social Memory | `st_anchors` | 0 |
  | Social Memory | `st_anchor_observations` | 0 |
  | Procedural Memory | `st_procedural` | 0 |
  | Prospective Memory | `st_prospective` | 9 |
  | Learning & Feedback | `st_learning_queue` | 28 |
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
  | Pipeline State | `st_pipeline_processed` | 784 |
  | Pipeline State | `st_consolidation_audit` | 0 |
  | Infrastructure | `st_devices` | 1 |
  | Infrastructure | `st_device_keys` | 1 |
  | Infrastructure | `st_acl` | 0 |
  | Infrastructure | `st_retention_policy` | 0 |
  | Infrastructure | `st_outbox` | 142 |
  | Infrastructure | `st_dlq` | 0 |
  | Infrastructure | `st_wal` | 2,814 |
  | Infrastructure | `st_receipts` | 2,814 |
  | Infrastructure | `st_validation_results` | 0 |
  | Infrastructure | `st_archive_manifest` | 0 |
  | Infrastructure | `st_obligation_log` | 0 |
  | Infrastructure | `st_crdt_merge_log` | 0 |
  | Infrastructure | `st_mcts_decisions` | 0 |
  | Infrastructure | `st_mcts_shadow_log` | 0 |
  | Infrastructure | `idem_ledger` | 2,814 |
  | Core Tables | `households` | 0 |
  | Core Tables | `people` | 0 |
  | **TOTAL** | | **9,762** |

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
  (35 rows)
  ```

  **Data**:

  ```
  episode_id            |  tenant_id  |  space_id  | version | supersedes_id | is_canonical |      episode_summary       | episode_type | start_time_utc | end_time_utc  | duration_minutes | temporal_bucket | day_of_week | is_recurring | recurrence_pattern |                                                                                                                                                                                                                                                                                                                        source_events_json                                                                                                                                                                                                                                                                                                                        | source_event_count |  primary_location  | location_type |                                      participants_json                                       | participant_count |             embedding_id             |           cluster_id            | cluster_confidence | consolidation_cycle_id | observation_count | confidence_score | last_observed_at | decay_factor | archival_status |  created_at   |  updated_at   |  valid_from   | valid_to | merge_cascade_id
  ---------------------------------+-------------+------------+---------+---------------+--------------+----------------------------+--------------+----------------+---------------+------------------+-----------------+-------------+--------------+--------------------+------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+--------------------+--------------------+---------------+----------------------------------------------------------------------------------------------+-------------------+--------------------------------------+---------------------------------+--------------------+------------------------+-------------------+------------------+------------------+--------------+-----------------+---------------+---------------+---------------+----------+------------------
  weak-16ed876e70714a7181a362f3da | tenant-test | space-home |       1 |               | t            | Routine at Home            | routine      |  1768331247000 | 1768331255000 |                  |                 |             |              |                    | ["fb5dae74-9a59-4cfa-b331-2368651e0332", "4127bec2-100e-4de0-97a0-4fff1fb854e1", "f0d38122-25fe-45c4-a124-6d61d0ac5c18", "f7ee02e0-b217-4d38-8b34-32da9e49cd58", "afb69564-97fa-4bfd-85d0-76b29937f85a", "a8a074c8-2322-47fe-a590-676c26514737", "0e109e59-8cad-4bd7-a9e3-afc25fe6f72a", "36dbc9b0-ecce-4777-ace0-6865e20a1f63", "92c4461c-1f97-419d-bec0-a676a08f2d5b", "a049243e-a117-45e0-9ba8-f82d703baebd", "06f9739c-1ba0-4ba1-a605-9c7ca8d26a7a", "418ed532-b1ae-401c-a49a-f093977726a8", "1f801366-e663-4aa7-b887-1a59b7c1a996", "781254f2-df68-465e-8b9c-fa4b07b2db6d", "d8043681-a460-43fd-979b-eb905a11b4ec", "c9d6c42f-1be1-407c-b163-d454f2fb993b"] |                 16 | Home               |               | ["Alex", "Chris", "Emma", "Jake", "Kevin", "Maria", "Mom", "Sofia", "Tom"]                   |                 9 | 09dd86a5-a500-4b7f-a4b4-ebf0b5de4721 | weak-16ed876e70714a7181a362f3da |  0.990524790487421 |                        |                 1 |              0.5 |                  |            1 | ACTIVE          | 1768331273553 | 1768331273553 | 1768331273553 |          |
  weak-19404d1ad13944c6b8b8f916b2 | tenant-test | space-home |       1 |               | t            | Work at Starbucks Downtown | work         |  1768331247000 | 1768331254000 |                  |                 |             |              |                    | ["363171c8-397f-4950-8bfd-92d9a0d12180", "aa6baef3-021b-4891-a8a8-3acdc28541e8", "8f9b3a32-43aa-48a6-85ad-0954ef90e9e1", "708a1763-3516-4702-bdf9-9d9301bf7807", "eeb2e5ac-f550-49ed-9213-1d393e8803df", "a24adfdc-fc5b-4ba6-9650-07b844c30421", "a96d11a3-78b3-43f3-8e29-cddf0fa399e4", "c1f38640-d148-45b4-b5a6-4583df81abe7", "72abd141-8e0f-4e21-a1f9-4722691d0fba", "ed57f299-da14-4bab-9fb3-ed69e08cc9a9"]                                                                                                                                                                                                                                                 |                 10 | Starbucks Downtown |               | ["Alex", "Andrew Ng", "Chris", "Jennifer", "John", "Lisa", "Mike", "Rachel", "Sam", "Sarah"] |                10 | d0786d09-fdda-4cad-bf8b-f09dd2088c2a | weak-19404d1ad13944c6b8b8f916b2 | 0.9947654289496675 |                        |                 1 |              0.5 |                  |            1 | ACTIVE          | 1768331273553 | 1768331273553 | 1768331273553 |          |
  weak-1440e69e45264687a4249be948 | tenant-test | space-home |       1 |               | t            | Work at Home               | work         |  1768331247000 | 1768331255000 |                  |                 |             |              |                    | ["1dc23260-e4e7-418a-9564-98857591b926", "e0a07485-776e-40ea-8885-f4acef71d000", "12745278-8fea-4625-82c2-8050924999d4", "0b765d06-3557-4dd5-9958-2563736d481d", "432d77ac-b58d-48d6-a71c-efb1e68b2804", "ca87f8b3-f1c3-43b9-9345-4070cffd53bc"]                                                                                                                                                                                                                                                                                                                                                                                                                 |                  6 | Home               |               | ["David", "Emma", "Jake", "Sarah", "Team"]                                                   |                 5 | f4c9df38-fb94-4c56-9b95-69ad136a12bf | weak-1440e69e45264687a4249be948 | 0.9950168112972801 |                        |                 1 |              0.5 |                  |            1 | ACTIVE          | 1768331273553 | 1768331273553 | 1768331273553 |          |
  weak-f8df020a3d7e4c3683556774f1 | tenant-test | space-home |       1 |               | t            | Routine at Home            | routine      |  1768331253000 | 1768331255000 |                  |                 |             |              |                    | ["f2e418ac-859e-4930-97f1-6e645ce43d00", "02d067f0-c76f-4b45-b2ed-4501d5c1adf2", "b2cf0660-778a-49e3-9760-0faa085e8a8c", "87e9655a-84a3-4fb3-845e-2a97d68d5b3e", "7c7bad91-1f21-41a0-b16a-c9a621fbf79f"]                                                                                                                                                                                                                                                                                                                                                                                                                                                         |                  5 | Home               |               | ["Dr. Johnson", "Dr. Smith"]                                                                 |                 2 | a14326cc-c941-4b1f-9169-7467a2305fd0 | weak-f8df020a3d7e4c3683556774f1 | 0.9936677801409318 |                        |                 1 |              0.5 |                  |            1 | ACTIVE          | 1768331273553 | 1768331273553 | 1768331273553 |          |
  weak-8145865ab94643a2bf27972804 | tenant-test | space-home |       1 |               | t            | Routine at Home            | routine      |  1768331253000 | 1768331255000 |                  |                 |             |              |                    | ["bafdb87f-9980-4138-9a05-162202253947", "6623cb1b-e485-43ad-8153-45c0714a72ff", "d9b9f946-d889-47c8-98ff-6e6b83340e30", "c4c14a70-c441-4321-b328-e6f396e948b2", "07c33a2b-e8ab-4138-8ddc-fc741728c0bc", "664f2a14-4cba-4b80-ba6b-b8b75c31b2fe"]                                                                                                                                                                                                                                                                                                                                                                                                                 |                  6 | Home               |               | ["Emma", "Jake", "Rachel"]                                                                   |                 3 | ffaf1ff0-7962-499c-8c65-ffce90f05ccb | weak-8145865ab94643a2bf27972804 |   0.99307168173149 |                        |                 1 |              0.5 |                  |            1 | ACTIVE          | 1768331273553 | 1768331273553 | 1768331273553 |          |
  weak-dd93ba64904e4f94814265b134 | tenant-test | space-home |       1 |               | t            | Routine at Home            | routine      |  1768331254000 | 1768331255000 |                  |                 |             |              |                    | ["5ec36138-ec81-4bc2-9f68-24c8dbc575c5", "d7b43c90-7505-4312-8d11-5c222d17e61f", "150f0a08-46ca-44ce-a1b4-2789b5cc0859", "ad9da1ef-8783-4294-9747-2df8d5336a58", "ad3e227c-db90-45e5-b9e5-8ee100ccc65c", "2e6b4c2b-6cf2-4df0-951b-44a135acda26", "98ef5b83-2e0e-4d82-b744-acba3b4ef136", "c3e80979-e1ad-4313-b1f5-b7d144803d03"]                                                                                                                                                                                                                                                                                                                                 |                  8 | Home               |               | ["David", "Jennifer", "John", "Mike"]                                                        |                 4 | 4f2a447d-0ee4-4442-9e8d-ff071cf9b208 | weak-dd93ba64904e4f94814265b134 |  0.988160063554301 |                        |                 1 |              0.5 |                  |            1 | ACTIVE          | 1768331273553 | 1768331273553 | 1768331273553 |          |
  weak-f84ca9e696b84f4e8a1d845e1b | tenant-test | space-home |       1 |               | t            | Routine at Home            | routine      |  1768331254000 | 1768331254000 |                  |                 |             |              |                    | ["594c7e01-a373-4e41-bd1b-631eb1a33dbd", "60b68a4b-56da-4374-94d8-74350ccd1b3d", "6fae7292-07e6-4f5e-b066-aea01a8dea7d"]                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |                  3 | Home               |               | ["Emma", "Mom"]                                                                              |                 2 | 5e1d7290-d8f4-4f1d-8298-bb5e71ff1d6e | weak-f84ca9e696b84f4e8a1d845e1b | 0.9973681383848235 |                        |                 1 |              0.5 |                  |            1 | ACTIVE          | 1768331273553 | 1768331273553 | 1768331273553 |          |
  f7bfd06db2fb42d0bc7bdc4b5e      | tenant-test | space-home |       1 |               | t            | Milestone at Starbucks     | milestone    |  1768331255000 | 1768331255000 |                  |                 |             |              |                    | ["a94a6a0a-8ee4-48aa-b8c3-a6614f8975b1", "f1206aec-da79-470f-8daf-b06854ae805d"]                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |                  2 | Starbucks          |               | ["Jake", "Rachel", "Sophie", "Tom"]                                                          |                 4 | 9e048794-3e5d-441b-b521-38c19601b9f2 | f7bfd06db2fb42d0bc7bdc4b5e      | 0.9994123494989546 |                        |                 1 |              0.5 |                  |            1 | ACTIVE          | 1768331273553 | 1768331273553 | 1768331273553 |          |
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

  **Row Count**: 88

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
  (29 rows)
  ```

  **Data**:

  ```
  entity_id                |   tenant_id    |   space_id    | version | supersedes_id | is_canonical |  entity_type  | entity_subtype |   canonical_name    |             aliases_json             |                        attributes_json                         | embedding_id |                                                                                                                                                                           source_episodes_json                                                                                                                                                                           | first_mentioned_event_id | observation_count |  confidence_score  | last_observed_at | decay_factor | archival_status |  created_at   |  updated_at   |  valid_from   | valid_to | merged_into | merged_at | merged_by | query_count | last_queried_at |                                                                                                                                                                                                                                                                                                                                                                                                                                                   milestones_json
  -----------------------------------------+----------------+---------------+---------+---------------+--------------+---------------+----------------+---------------------+--------------------------------------+----------------------------------------------------------------+--------------+--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+--------------------------+-------------------+--------------------+------------------+--------------+-----------------+---------------+---------------+---------------+----------+-------------+-----------+-----------+-------------+-----------------+---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
  cluster_LOCATION_city sports complex    | tenant-test    | space-home    |       1 |               | t            | LOCATION      |                | city sports complex | ['City Sports Complex']              |                                                                |              | ["fb5dae74-9a59-4cfa-b331-2368651e0332"]                                                                                                                                                                                                                                                                                                                                 |                          |                 1 | 0.8500000000000001 |                  |            1 | ACTIVE          | 1768331273555 | 1768331273555 | 1768331273555 |          |             |           |           |           0 |                 |
  cluster_PERSON_emma                     | tenant-test    | space-home    |       1 |               | t            | PERSON        |                | emma                | ['Emma']                             |                                                                |              | ["92c4461c-1f97-419d-bec0-a676a08f2d5b", "4127bec2-100e-4de0-97a0-4fff1fb854e1", "fb5dae74-9a59-4cfa-b331-2368651e0332", "f7ee02e0-b217-4d38-8b34-32da9e49cd58", "1f801366-e663-4aa7-b887-1a59b7c1a996", "f0d38122-25fe-45c4-a124-6d61d0ac5c18", "d8043681-a460-43fd-979b-eb905a11b4ec", "60b68a4b-56da-4374-94d8-74350ccd1b3d", "6623cb1b-e485-43ad-8153-45c0714a72ff"] |                          |                 9 | 0.8499999999999999 |                  |            1 | ACTIVE          | 1768331273555 | 1768331273555 | 1768331273555 |          |             |           |           |           0 |                 |
  cluster_LOCATION_lincoln school         | tenant-test    | space-home    |       1 |               | t            | LOCATION      |                | lincoln school      | ['Lincoln School']                   |                                                                |              | ["d8043681-a460-43fd-979b-eb905a11b4ec", "4127bec2-100e-4de0-97a0-4fff1fb854e1"]                                                                                                                                                                                                                                                                                         |                          |                 2 | 0.8500000000000001 |                  |            1 | ACTIVE          | 1768331273555 | 1768331273555 | 1768331273555 |          |             |           |           |           0 |                 |
  cluster_CONCEPT_fur elise               | tenant-test    | space-home    |       1 |               | t            | CONCEPT       |                | fur elise           | ['Fur Elise']                        |                                                                |              | ["4127bec2-100e-4de0-97a0-4fff1fb854e1"]                                                                                                                                                                                                                                                                                                                                 |                          |                 1 |               0.65 |                  |            1 | ACTIVE          | 1768331273555 | 1768331273555 | 1768331273555 |          |             |           |           |           0 |                 |
  cluster_LOCATION_home                   | tenant-test    | space-home    |       1 |               | t            | LOCATION      |                | home                | ['home']                             |                                                                |              | ["f0d38122-25fe-45c4-a124-6d61d0ac5c18"]                                                                                                                                                                                                                                                                                                                                 |                          |                 1 |                0.9 |                  |            1 | ACTIVE          | 1768331273555 | 1768331273555 | 1768331273555 |          |             |           |           |           0 |                 |
  cluster_PERSON_jake                     | tenant-test    | space-home    |       1 |               | t            | PERSON        |                | jake                | ['Jake']                             |                                                                |              | ["f1206aec-da79-470f-8daf-b06854ae805d", "f0d38122-25fe-45c4-a124-6d61d0ac5c18"]                                                                                                                                                                                                                                                                                         |                          |                 2 |               0.85 |                  |            1 | ACTIVE          | 1768331273555 | 1768331273555 | 1768331273555 |          |             |           |           |           0 |                 |
  cluster_EVENT_birthday party            | tenant-test    | space-home    |       1 |               | t            | EVENT         |                | birthday party      | ['Birthday party', 'birthday party'] |                                                                |              | ["f7ee02e0-b217-4d38-8b34-32da9e49cd58", "0e109e59-8cad-4bd7-a9e3-afc25fe6f72a"]                                                                                                                                                                                                                                                                                         |                          |                 2 |                0.9 |                  |            1 | ACTIVE          | 1768331273555 | 1768331273555 | 1768331273555 |          |             |           |           |           0 |                 |
  cluster_PERSON_sofia                    | tenant-test    | space-home    |       1 |               | t            | PERSON        |                | sofia               | ['Sofia']                            |                                                                |              | ["f7ee02e0-b217-4d38-8b34-32da9e49cd58"]                                                                                                                                                                                                                                                                                                                                 |                          |                 1 |               0.85 |                  |            1 | ACTIVE          | 1768331273555 | 1768331273555 | 1768331273555 |          |             |           |           |           0 |                 |
  cluster_ORGANIZATION_chuck e cheese     | tenant-test    | space-home    |       1 |               | t            | ORGANIZATION  |                | chuck e cheese      | ['Chuck E Cheese']                   |                                                                |              | ["f7ee02e0-b217-4d38-8b34-32da9e49cd58"]                                                                                                                                                                                                                                                                                                                                 |                          |                 1 |                0.8 |                  |            1 | ACTIVE          | 1768331273555 | 1768331273555 | 1768331273555 |          |             |           |           |           0 |                 |
  cluster_PERSON_john                     | tenant-test    | space-home    |       1 |               | t            | PERSON        |                | john                | ['John']                             |                                                                |              | ["363171c8-397f-4950-8bfd-92d9a0d12180"]                                                                                                                                                                                                                                                                                                                                 |                          |                 1 |               0.85 |                  |            1 | ACTIVE          | 1768331273555 | 1768331273555 | 1768331273555 |          |             |           |           |           0 |                 |
  cluster_PERSON_lisa                     | tenant-test    | space-home    |       1 |               | t            | PERSON        |                | lisa                | ['Lisa']                             |                                                                |              | ["363171c8-397f-4950-8bfd-92d9a0d12180"]                                                                                                                                                                                                                                                                                                                                 |                          |                 1 |               0.85 |                  |            1 | ACTIVE          | 1768331273555 | 1768331273555 | 1768331273555 |          |             |           |           |           0 |                 |
  cluster_PERSON_mike                     | tenant-test    | space-home    |       1 |               | t            | PERSON        |                | mike                | ['Mike']                             |                                                                |              | ["363171c8-397f-4950-8bfd-92d9a0d12180", "8f9b3a32-43aa-48a6-85ad-0954ef90e9e1"]                                                                                                                                                                                                                                                                                         |                          |                 2 |               0.85 |                  |            1 | ACTIVE          | 1768331273555 | 1768331273555 | 1768331273555 |          |             |           |           |           0 |                 |
  cluster_PERSON_sarah                    | tenant-test    | space-home    |       1 |               | t            | PERSON        |                | sarah               | ['Sarah']                            |                                                                |              | ["aa6baef3-021b-4891-a8a8-3acdc28541e8"]                                                                                                                                                                                                                                                                                                                                 |                          |                 1 |               0.85 |                  |            1 | ACTIVE          | 1768331273555 | 1768331273555 | 1768331273555 |          |             |           |           |           0 |                 |
  cluster_PERSON_david                    | tenant-test    | space-home    |       1 |               | t            | PERSON        |                | david               | ['David']                            |                                                                |              | ["1dc23260-e4e7-418a-9564-98857591b926"]                                                                                                                                                                                                                                                                                                                                 |                          |                 1 |               0.85 |                  |            1 | ACTIVE          | 1768331273555 | 1768331273555 | 1768331273555 |          |             |           |           |           0 |                 |
  cluster_FAMILY_MEMBER_coworkers         | tenant-test    | space-home    |       1 |               | t            | FAMILY_MEMBER |                | coworkers           | ['coworkers']                        |                                                                |              | ["708a1763-3516-4702-bdf9-9d9301bf7807"]                                                                                                                                                                                                                                                                                                                                 |                          |                 1 |               0.95 |                  |            1 | ACTIVE          | 1768331273555 | 1768331273555 | 1768331273555 |          |             |           |           |           0 |                 |
  cluster_LOCATION_central park           | tenant-test    | space-home    |       1 |               | t            | LOCATION      |                | central park        | ['Central Park']                     |                                                                |              | ["afb69564-97fa-4bfd-85d0-76b29937f85a"]                                                                                                                                                                                                                                                                                                                                 |                          |                 1 |                0.8 |                  |            1 | ACTIVE          | 1768331273555 | 1768331273555 | 1768331273555 |          |             |           |           |           0 |                 |
  cluster_PERSON_smith                    | tenant-test    | space-home    |       1 |               | t            | PERSON        |                | smith               | ['Smith']                            |                                                                |              | ["f2e418ac-859e-4930-97f1-6e645ce43d00", "7c7bad91-1f21-41a0-b16a-c9a621fbf79f"]                                                                                                                                                                                                                                                                                         |                          |                 2 |               0.85 |                  |            1 | ACTIVE          | 1768331273555 | 1768331273555 | 1768331273555 |          |             |           |           |           0 |                 |
  cluster_PERSON_maria                    | tenant-test    | space-home    |       1 |               | t            | PERSON        |                | maria               | ['Maria']                            |                                                                |              | ["a8a074c8-2322-47fe-a590-676c26514737"]                                                                                                                                                                                                                                                                                                                                 |                          |                 1 |               0.85 |                  |            1 | ACTIVE          | 1768331273555 | 1768331273555 | 1768331273555 |          |             |           |           |           0 |                 |
  cluster_PERSON_johnson                  | tenant-test    | space-home    |       1 |               | t            | PERSON        |                | johnson             | ['Johnson']                          |                                                                |              | ["02d067f0-c76f-4b45-b2ed-4501d5c1adf2"]                                                                                                                                                                                                                                                                                                                                 |                          |                 1 |               0.85 |                  |            1 | ACTIVE          | 1768331273555 | 1768331273555 | 1768331273555 |          |             |           |           |           0 |                 |
  cluster_PERSON_rachel                   | tenant-test    | space-home    |       1 |               | t            | PERSON        |                | rachel              | ['Rachel']                           |                                                                |              | ["c1f38640-d148-45b4-b5a6-4583df81abe7", "eeb2e5ac-f550-49ed-9213-1d393e8803df", "72abd141-8e0f-4e21-a1f9-4722691d0fba", "a94a6a0a-8ee4-48aa-b8c3-a6614f8975b1"]                                                                                                                                                                                                         |                          |                 4 |               0.85 |                  |            1 | ACTIVE          | 1768331273555 | 1768331273555 | 1768331273555 |          |             |           |           |           0 |                 |
  cluster_ORGANIZATION_starbucks          | tenant-test    | space-home    |       1 |               | t            | ORGANIZATION  |                | starbucks           | ['Starbucks']                        |                                                                |              | ["c1f38640-d148-45b4-b5a6-4583df81abe7", "eeb2e5ac-f550-49ed-9213-1d393e8803df", "72abd141-8e0f-4e21-a1f9-4722691d0fba"]                                                                                                                                                                                                                                                 |                          |                 3 | 0.8000000000000002 |                  |            1 | ACTIVE          | 1768331273555 | 1768331273555 | 1768331273555 |          |             |           |           |           0 |                 |
  cluster_ORGANIZATION_google             | tenant-test    | space-home    |       1 |               | t            | ORGANIZATION  |                | google              | ['Google']                           |                                                                |              | ["c1f38640-d148-45b4-b5a6-4583df81abe7", "eeb2e5ac-f550-49ed-9213-1d393e8803df", "72abd141-8e0f-4e21-a1f9-4722691d0fba", "150f0a08-46ca-44ce-a1b4-2789b5cc0859"]                                                                                                                                                                                                         |                          |                 4 |                0.8 |                  |            1 | ACTIVE          | 1768331273555 | 1768331273555 | 1768331273555 |          |             |           |           |           0 |                 |
  cluster_PERSON_tom                      | tenant-test    | space-home    |       1 |               | t            | PERSON        |                | tom                 | ['Tom']                              |                                                                |              | ["0e109e59-8cad-4bd7-a9e3-afc25fe6f72a", "a94a6a0a-8ee4-48aa-b8c3-a6614f8975b1"]                                                                                                                                                                                                                                                                                         |                          |                 2 |               0.85 |                  |            1 | ACTIVE          | 1768331273555 | 1768331273555 | 1768331273555 |          |             |           |           |           0 |                 |
  cluster_CONCEPT_italian                 | tenant-test    | space-home    |       1 |               | t            | CONCEPT       |                | italian             | ['Italian']                          |                                                                |              | ["a24adfdc-fc5b-4ba6-9650-07b844c30421"]                                                                                                                                                                                                                                                                                                                                 |                          |                 1 |               0.65 |                  |            1 | ACTIVE          | 1768331273555 | 1768331273555 | 1768331273555 |          |             |           |           |           0 |                 |
  cluster_ORGANIZATION_bella notte        | tenant-test    | space-home    |       1 |               | t            | ORGANIZATION  |                | bella notte         | ['Bella Notte']                      |                                                                |              | ["a24adfdc-fc5b-4ba6-9650-07b844c30421"]                                                                                                                                                                                                                                                                                                                                 |                          |                 1 |                0.8 |                  |            1 | ACTIVE          | 1768331273555 | 1768331273555 | 1768331273555 |          |             |           |           |           0 |                 |
  cluster_CONCEPT_inception               | tenant-test    | space-home    |       1 |               | t            | CONCEPT       |                | inception           | ['Inception']                        |                                                                |              | ["36dbc9b0-ecce-4777-ace0-6865e20a1f63"]                                                                                                                                                                                                                                                                                                                                 |                          |                 1 |               0.65 |                  |            1 | ACTIVE          | 1768331273555 | 1768331273555 | 1768331273555 |          |             |           |           |           0 |                 |
  cluster_PERSON_kevin                    | tenant-test    | space-home    |       1 |               | t            | PERSON        |                | kevin               | ['Kevin']                            |                                                                |              | ["36dbc9b0-ecce-4777-ace0-6865e20a1f63"]                                                                                                                                                                                                                                                                                                                                 |                          |                 1 |               0.85 |                  |            1 | ACTIVE          | 1768331273555 | 1768331273555 | 1768331273555 |          |             |           |           |           0 |                 |
  cluster_CONCEPT_atomic habits           | tenant-test    | space-home    |       1 |               | t            | CONCEPT       |                | atomic habits       | ['Atomic Habits']                    |                                                                |              | ["bafdb87f-9980-4138-9a05-162202253947"]                                                                                                                                                                                                                                                                                                                                 |                          |                 1 |               0.65 |                  |            1 | ACTIVE          | 1768331273555 | 1768331273555 | 1768331273555 |          |             |           |           |           0 |                 |
  cluster_PERSON_james clear              | tenant-test    | space-home    |       1 |               | t            | PERSON        |                | james clear         | ['James Clear']                      |                                                                |              | ["bafdb87f-9980-4138-9a05-162202253947"]                                                                                                                                                                                                                                                                                                                                 |                          |                 1 |               0.85 |                  |            1 | ACTIVE          | 1768331273555 | 1768331273555 | 1768331273555 |          |             |           |           |           0 |                 |
  cluster_CONCEPT_python                  | tenant-test    | space-home    |       1 |               | t            | CONCEPT       |                | python              | ['Python']                           |                                                                |              | ["e0a07485-776e-40ea-8885-f4acef71d000"]                                                                                                                                                                                                                                                                                                                                 |                          |                 1 |               0.65 |                  |            1 | ACTIVE          | 1768331273555 | 1768331273555 | 1768331273555 |          |             |           |           |           0 |                 |
  cluster_ORGANIZATION_coursera           | tenant-test    | space-home    |       1 |               | t            | ORGANIZATION  |                | coursera            | ['Coursera']                         |                                                                |              | ["e0a07485-776e-40ea-8885-f4acef71d000"]                                                                                                                                                                                                                                                                                                                                 |                          |                 1 |                0.8 |                  |            1 | ACTIVE          | 1768331273555 | 1768331273555 | 1768331273555 |          |             |           |           |           0 |                 |
  cluster_CONCEPT_ai                      | tenant-test    | space-home    |       1 |               | t            | CONCEPT       |                | ai                  | ['AI']                               |                                                                |              | ["a96d11a3-78b3-43f3-8e29-cddf0fa399e4"]                                                                                                                                                                                                                                                                                                                                 |                          |                 1 |               0.65 |                  |            1 | ACTIVE          | 1768331273555 | 1768331273555 | 1768331273555 |          |             |           |           |           0 |                 |
  cluster_ORGANIZATION_stanford           | tenant-test    | space-home    |       1 |               | t            | ORGANIZATION  |                | stanford            | ['Stanford']                         |                                                                |              | ["a96d11a3-78b3-43f3-8e29-cddf0fa399e4"]                                                                                                                                                                                                                                                                                                                                 |                          |                 1 |                0.8 |                  |            1 | ACTIVE          | 1768331273555 | 1768331273555 | 1768331273555 |          |             |           |           |           0 |                 |
  cluster_PERSON_andrew ng                | tenant-test    | space-home    |       1 |               | t            | PERSON        |                | andrew ng           | ['Andrew Ng']                        |                                                                |              | ["a96d11a3-78b3-43f3-8e29-cddf0fa399e4"]                                                                                                                                                                                                                                                                                                                                 |                          |                 1 |               0.85 |                  |            1 | ACTIVE          | 1768331273555 | 1768331273555 | 1768331273555 |          |             |           |           |           0 |                 |
  cluster_LOCATION_brooklyn               | tenant-test    | space-home    |       1 |               | t            | LOCATION      |                | brooklyn            | ['Brooklyn']                         |                                                                |              | ["5ec36138-ec81-4bc2-9f68-24c8dbc575c5", "ad9da1ef-8783-4294-9747-2df8d5336a58"]                                                                                                                                                                                                                                                                                         |                          |                 2 | 0.8500000000000001 |                  |            1 | ACTIVE          | 1768331273555 | 1768331273555 | 1768331273555 |          |             |           |           |           0 |                 |
  cluster_ORGANIZATION_lincoln elementary | tenant-test    | space-home    |       1 |               | t            | ORGANIZATION  |                | lincoln elementary  | ['Lincoln Elementary']               |                                                                |              | ["92c4461c-1f97-419d-bec0-a676a08f2d5b"]                                                                                                                                                                                                                                                                                                                                 |                          |                 1 |                0.8 |                  |            1 | ACTIVE          | 1768331273555 | 1768331273555 | 1768331273555 |          |             |           |           |           0 |                 |
  cluster_LOCATION_san francisco          | tenant-test    | space-home    |       1 |               | t            | LOCATION      |                | san francisco       | ['San Francisco']                    |                                                                |              | ["d7b43c90-7505-4312-8d11-5c222d17e61f", "c9d6c42f-1be1-407c-b163-d454f2fb993b"]                                                                                                                                                                                                                                                                                         |                          |                 2 |                0.8 |                  |            1 | ACTIVE          | 1768331273555 | 1768331273555 | 1768331273555 |          |             |           |           |           0 |                 |
  cluster_LOCATION_alcatraz               | tenant-test    | space-home    |       1 |               | t            | LOCATION      |                | alcatraz            | ['Alcatraz']                         |                                                                |              | ["a049243e-a117-45e0-9ba8-f82d703baebd"]                                                                                                                                                                                                                                                                                                                                 |                          |                 1 | 0.8500000000000001 |                  |            1 | ACTIVE          | 1768331273555 | 1768331273555 | 1768331273555 |          |             |           |           |           0 |                 |
  cluster_LOCATION_golden gate bridge     | tenant-test    | space-home    |       1 |               | t            | LOCATION      |                | golden gate bridge  | ['Golden Gate Bridge']               |                                                                |              | ["a049243e-a117-45e0-9ba8-f82d703baebd"]                                                                                                                                                                                                                                                                                                                                 |                          |                 1 |                0.8 |                  |            1 | ACTIVE          | 1768331273555 | 1768331273555 | 1768331273555 |          |             |           |           |           0 |                 |
  cluster_LOCATION_boston                 | tenant-test    | space-home    |       1 |               | t            | LOCATION      |                | boston              | ['Boston']                           |                                                                |              | ["06f9739c-1ba0-4ba1-a605-9c7ca8d26a7a"]                                                                                                                                                                                                                                                                                                                                 |                          |                 1 | 0.8500000000000001 |                  |            1 | ACTIVE          | 1768331273555 | 1768331273555 | 1768331273555 |          |             |           |           |           0 |                 |
  cluster_FAMILY_MEMBER_family            | tenant-test    | space-home    |       1 |               | t            | FAMILY_MEMBER |                | family              | ['family']                           |                                                                |              | ["432d77ac-b58d-48d6-a71c-efb1e68b2804", "06f9739c-1ba0-4ba1-a605-9c7ca8d26a7a"]                                                                                                                                                                                                                                                                                         |                          |                 2 |               0.95 |                  |            1 | ACTIVE          | 1768331273555 | 1768331273555 | 1768331273555 |          |             |           |           |           0 |                 |
  cluster_CONCEPT_freedom trail           | tenant-test    | space-home    |       1 |               | t            | CONCEPT       |                | freedom trail       | ['Freedom Trail']                    |                                                                |              | ["06f9739c-1ba0-4ba1-a605-9c7ca8d26a7a"]                                                                                                                                                                                                                                                                                                                                 |                          |                 1 |               0.65 |                  |            1 | ACTIVE          | 1768331273555 | 1768331273555 | 1768331273555 |          |             |           |           |           0 |                 |
  cluster_PERSON_jennifer                 | tenant-test    | space-home    |       1 |               | t            | PERSON        |                | jennifer            | ['Jennifer']                         |                                                                |              | ["ed57f299-da14-4bab-9fb3-ed69e08cc9a9"]                                                                                                                                                                                                                                                                                                                                 |                          |                 1 |               0.85 |                  |            1 | ACTIVE          | 1768331273555 | 1768331273555 | 1768331273555 |          |             |           |           |           0 |                 |
  cluster_LOCATION_manhattan              | tenant-test    | space-home    |       1 |               | t            | LOCATION      |                | manhattan           | ['Manhattan']                        |                                                                |              | ["ad9da1ef-8783-4294-9747-2df8d5336a58"]                                                                                                                                                                                                                                                                                                                                 |                          |                 1 | 0.8500000000000001 |                  |            1 | ACTIVE          | 1768331273555 | 1768331273555 | 1768331273555 |          |             |           |           |           0 |                 |
  cluster_PERSON_alex                     | tenant-test    | space-home    |       1 |               | t            | PERSON        |                | alex                | ['Alex']                             |                                                                |              | ["418ed532-b1ae-401c-a49a-f093977726a8"]                                                                                                                                                                                                                                                                                                                                 |                          |                 1 |               0.85 |                  |            1 | ACTIVE          | 1768331273555 | 1768331273555 | 1768331273555 |          |             |           |           |           0 |                 |
  cluster_PERSON_chris                    | tenant-test    | space-home    |       1 |               | t            | PERSON        |                | chris               | ['Chris']                            |                                                                |              | ["418ed532-b1ae-401c-a49a-f093977726a8"]                                                                                                                                                                                                                                                                                                                                 |                          |                 1 |               0.85 |                  |            1 | ACTIVE          | 1768331273555 | 1768331273555 | 1768331273555 |          |             |           |           |           0 |                 |
  cluster_FAMILY_MEMBER_brother           | tenant-test    | space-home    |       1 |               | t            | FAMILY_MEMBER |                | brother             | ['brother']                          |                                                                |              | ["f1206aec-da79-470f-8daf-b06854ae805d"]                                                                                                                                                                                                                                                                                                                                 |                          |                 1 |               0.95 |                  |            1 | ACTIVE          | 1768331273555 | 1768331273555 | 1768331273555 |          |             |           |           |           0 |                 |
  cluster_PERSON_sophie                   | tenant-test    | space-home    |       1 |               | t            | PERSON        |                | sophie              | ['Sophie']                           |                                                                |              | ["f1206aec-da79-470f-8daf-b06854ae805d"]                                                                                                                                                                                                                                                                                                                                 |                          |                 1 |               0.85 |                  |            1 | ACTIVE          | 1768331273555 | 1768331273555 | 1768331273555 |          |             |           |           |           0 |                 |
  cluster_LOCATION_london                 | tenant-test    | space-home    |       1 |               | t            | LOCATION      |                | london              | ['London']                           |                                                                |              | ["c3e80979-e1ad-4313-b1f5-b7d144803d03"]                                                                                                                                                                                                                                                                                                                                 |                          |                 1 | 0.8500000000000001 |                  |            1 | ACTIVE          | 1768331273555 | 1768331273555 | 1768331273555 |          |             |           |           |           0 |                 |
  Emma                                    | default        | default       |       1 |               | t            | PERSON        |                | Emma                |                                      |                                                                |              |                                                                                                                                                                                                                                                                                                                                                                          |                          |                 1 |                0.5 |                  |            1 | ACTIVE          | 1768331273589 | 1768331273554 | 1768331273589 |          |             |           |           |           2 |   1768331273554 | [{"milestone_type": "ANNOUNCEMENT", "description": "Picked up Emma from soccer practice at City Sports Complex. She scored 2 goals today!", "source_event_id": "fb5dae74-9a59-4cfa-b331-2368651e0332", "recorded_at_ms": 1768331273554}, {"milestone_type": "ACHIEVEMENT", "description": "Exciting news! Emma got accepted into the gifted program at school!", "source_event_id": "1f801366-e663-4aa7-b887-1a59b7c1a996", "recorded_at_ms": 1768331273554}]
  Emma's                                  | default        | default       |       1 |               | t            | PERSON        |                | Emma's              |                                      |                                                                |              |                                                                                                                                                                                                                                                                                                                                                                          |                          |                 1 |                0.5 |                  |            1 | ACTIVE          | 1768331273592 | 1768331273554 | 1768331273592 |          |             |           |           |           0 |   1768331273554 | [{"milestone_type": "ANNOUNCEMENT", "description": "Emma's piano recital at Lincoln School. She played Fur Elise beautifully.", "source_event_id": "4127bec2-100e-4de0-97a0-4fff1fb854e1", "recorded_at_ms": 1768331273554}]
  John                                    | default        | default       |       1 |               | t            | PERSON        |                | John                |                                      |                                                                |              |                                                                                                                                                                                                                                                                                                                                                                          |                          |                 1 |                0.5 |                  |            1 | ACTIVE          | 1768331273593 | 1768331273554 | 1768331273593 |          |             |           |           |           0 |   1768331273554 | [{"milestone_type": "ANNOUNCEMENT", "description": "Team standup meeting with John, Lisa, and Mike. Discussed Q2 roadmap priorities.", "source_event_id": "363171c8-397f-4950-8bfd-92d9a0d12180", "recorded_at_ms": 1768331273554}]
  Sarah                                   | default        | default       |       1 |               | t            | PERSON        |                | Sarah               |                                      |                                                                |              |                                                                                                                                                                                                                                                                                                                                                                          |                          |                 1 |                0.5 |                  |            1 | ACTIVE          | 1768331273594 | 1768331273554 | 1768331273594 |          |             |           |           |           0 |   1768331273554 | [{"milestone_type": "ANNOUNCEMENT", "description": "One-on-one with manager Sarah about promotion timeline and career goals.", "source_event_id": "aa6baef3-021b-4891-a8a8-3acdc28541e8", "recorded_at_ms": 1768331273554}]
  David                                   | default        | default       |       1 |               | t            | PERSON        |                | David               |                                      |                                                                |              |                                                                                                                                                                                                                                                                                                                                                                          |                          |                 1 |                0.5 |                  |            1 | ACTIVE          | 1768331273596 | 1768331273554 | 1768331273596 |          |             |           |           |           0 |   1768331273554 | [{"milestone_type": "ANNOUNCEMENT", "description": "Presented quarterly results to the executive team. CEO David was impressed.", "source_event_id": "1dc23260-e4e7-418a-9564-98857591b926", "recorded_at_ms": 1768331273554}]
  Mike                                    | default        | default       |       1 |               | t            | PERSON        |                | Mike                |                                      |                                                                |              |                                                                                                                                                                                                                                                                                                                                                                          |                          |                 1 |                0.5 |                  |            1 | ACTIVE          | 1768331273597 | 1768331273554 | 1768331273597 |          |             |           |           |           0 |   1768331273554 | [{"milestone_type": "ANNOUNCEMENT", "description": "Code review session with Mike. Fixed critical bug in authentication module.", "source_event_id": "8f9b3a32-43aa-48a6-85ad-0954ef90e9e1", "recorded_at_ms": 1768331273554}]
  Johnson                                 | default        | default       |       1 |               | t            | PERSON        |                | Johnson             |                                      |                                                                |              |                                                                                                                                                                                                                                                                                                                                                                          |                          |                 1 |                0.5 |                  |            1 | ACTIVE          | 1768331273598 | 1768331273554 | 1768331273598 |          |             |           |           |           0 |   1768331273554 | [{"milestone_type": "ANNOUNCEMENT", "description": "Dentist checkup with Dr. Johnson. No cavities, scheduled cleaning for next month.", "source_event_id": "02d067f0-c76f-4b45-b2ed-4501d5c1adf2", "recorded_at_ms": 1768331273554}]
  Rachel                                  | default        | default       |       1 |               | t            | PERSON        |                | Rachel              |                                      |                                                                |              |                                                                                                                                                                                                                                                                                                                                                                          |                          |                 1 |                0.5 |                  |            1 | ACTIVE          | 1768331273600 | 1768331273554 | 1768331273600 |          |             |           |           |           0 |   1768331273554 | [{"milestone_type": "TRANSITION", "description": "Coffee with best friend Rachel at Starbucks. She's excited about her new job at Google.", "source_event_id": "eeb2e5ac-f550-49ed-9213-1d393e8803df", "recorded_at_ms": 1768331273554}, {"milestone_type": "ANNOUNCEMENT", "description": "Had coffee with Rachel at Starbucks. She mentioned her new position at Google.", "source_event_id": "c1f38640-d148-45b4-b5a6-4583df81abe7", "recorded_at_ms": 1768331273554}, {"milestone_type": "ANNOUNCEMENT", "description": "Met Rachel for coffee at the Starbucks downtown. Talked about her Google job.", "source_event_id": "72abd141-8e0f-4e21-a1f9-4722691d0fba", "recorded_at_ms": 1768331273554}, {"milestone_type": "TRANSITION", "description": "Rachel just told me she's getting married to Tom in June!", "source_event_id": "a94a6a0a-8ee4-48aa-b8c3-a6614f8975b1", "recorded_at_ms": 1768331273554}]
  Birthday party                          | default        | default       |       1 |               | t            | EVENT         |                | Birthday party      |                                      |                                                                |              |                                                                                                                                                                                                                                                                                                                                                                          |                          |                 1 |                0.5 |                  |            1 | ACTIVE          | 1768331273601 | 1768331273554 | 1768331273601 |          |             |           |           |           0 |   1768331273554 | [{"milestone_type": "CELEBRATION", "description": "Birthday party for Tom at his apartment. About 20 people showed up.", "source_event_id": "0e109e59-8cad-4bd7-a9e3-afc25fe6f72a", "recorded_at_ms": 1768331273554}]
  Italian                                 | default        | default       |       1 |               | t            | PERSON        |                | Italian             |                                      |                                                                |              |                                                                                                                                                                                                                                                                                                                                                                          |                          |                 1 |                0.5 |                  |            1 | ACTIVE          | 1768331273602 | 1768331273554 | 1768331273602 |          |             |           |           |           0 |   1768331273554 | [{"milestone_type": "ANNOUNCEMENT", "description": "Dinner with college friends at Italian restaurant Bella Notte. Great pasta!", "source_event_id": "a24adfdc-fc5b-4ba6-9650-07b844c30421", "recorded_at_ms": 1768331273554}]
  Python                                  | default        | default       |       1 |               | t            | CONCEPT       |                | Python              |                                      |                                                                |              |                                                                                                                                                                                                                                                                                                                                                                          |                          |                 1 |                0.5 |                  |            1 | ACTIVE          | 1768331273604 | 1768331273554 | 1768331273604 |          |             |           |           |           0 |   1768331273554 | [{"milestone_type": "ACHIEVEMENT", "description": "Online Python course on Coursera. Completed module on machine learning basics.", "source_event_id": "e0a07485-776e-40ea-8885-f4acef71d000", "recorded_at_ms": 1768331273554}]
  Stanford                                | default        | default       |       1 |               | t            | ORGANIZATION  |                | Stanford            |                                      |                                                                |              |                                                                                                                                                                                                                                                                                                                                                                          |                          |                 1 |                0.5 |                  |            1 | ACTIVE          | 1768331273605 | 1768331273554 | 1768331273605 |          |             |           |           |           0 |   1768331273554 | [{"milestone_type": "ANNOUNCEMENT", "description": "Attended webinar on AI and the future of work by Stanford professor Andrew Ng.", "source_event_id": "a96d11a3-78b3-43f3-8e29-cddf0fa399e4", "recorded_at_ms": 1768331273554}]
  Brooklyn                                | default        | default       |       1 |               | t            | LOCATION      |                | Brooklyn            |                                      |                                                                |              |                                                                                                                                                                                                                                                                                                                                                                          |                          |                 1 |                0.5 |                  |            1 | ACTIVE          | 1768331273606 | 1768331273554 | 1768331273606 |          |             |           |           |           0 |   1768331273554 | [{"milestone_type": "ANNOUNCEMENT", "description": "Signed lease for new apartment in Brooklyn. Moving in next month.", "source_event_id": "5ec36138-ec81-4bc2-9f68-24c8dbc575c5", "recorded_at_ms": 1768331273554}]
  Alcatraz                                | default        | default       |       1 |               | t            | LOCATION      |                | Alcatraz            |                                      |                                                                |              |                                                                                                                                                                                                                                                                                                                                                                          |                          |                 1 |                0.5 |                  |            1 | ACTIVE          | 1768331273607 | 1768331273554 | 1768331273607 |          |             |           |           |           0 |   1768331273554 | [{"milestone_type": "ANNOUNCEMENT", "description": "Visited Golden Gate Bridge. Amazing views of the bay and Alcatraz.", "source_event_id": "a049243e-a117-45e0-9ba8-f82d703baebd", "recorded_at_ms": 1768331273554}]
  student                                 | default        | default       |       1 |               | t            | UNKNOWN       |                | student             |                                      |                                                                |              |                                                                                                                                                                                                                                                                                                                                                                          |                          |                 1 |                0.5 |                  |            1 | ACTIVE          | 1768331273608 | 1768331273554 | 1768331273608 |          |             |           |           |           0 |   1768331273554 | [{"milestone_type": "ANNOUNCEMENT", "description": "Paid off student loans! 10 years of payments finally done.", "source_event_id": "0b765d06-3557-4dd5-9958-2563736d481d", "recorded_at_ms": 1768331273554}]
  Jennifer                                | default        | default       |       1 |               | t            | PERSON        |                | Jennifer            |                                      |                                                                |              |                                                                                                                                                                                                                                                                                                                                                                          |                          |                 1 |                0.5 |                  |            1 | ACTIVE          | 1768331273610 | 1768331273554 | 1768331273610 |          |             |           |           |           0 |   1768331273554 | [{"milestone_type": "ANNOUNCEMENT", "description": "Met with financial advisor Jennifer about retirement planning and 401k.", "source_event_id": "ed57f299-da14-4bab-9fb3-ed69e08cc9a9", "recorded_at_ms": 1768331273554}]
  brother                                 | default        | default       |       1 |               | t            | FAMILY_MEMBER |                | brother             |                                      |                                                                |              |                                                                                                                                                                                                                                                                                                                                                                          |                          |                 1 |                0.5 |                  |            1 | ACTIVE          | 1768331273611 | 1768331273554 | 1768331273611 |          |             |           |           |           0 |   1768331273554 | [{"milestone_type": "ANNOUNCEMENT", "description": "My brother Jake just had his first baby - a girl named Sophie!", "source_event_id": "f1206aec-da79-470f-8daf-b06854ae805d", "recorded_at_ms": 1768331273554}]
  London                                  | default        | default       |       1 |               | t            | LOCATION      |                | London              |                                      |                                                                |              |                                                                                                                                                                                                                                                                                                                                                                          |                          |                 1 |                0.5 |                  |            1 | ACTIVE          | 1768331273612 | 1768331273554 | 1768331273612 |          |             |           |           |           0 |   1768331273554 | [{"milestone_type": "ANNOUNCEMENT", "description": "The company announced we're expanding to London next year!", "source_event_id": "c3e80979-e1ad-4313-b1f5-b7d144803d03", "recorded_at_ms": 1768331273554}]
  Mom                                     | default        | default       |       1 |               | t            | FAMILY_MEMBER |                | Mom                 |                                      |                                                                |              |                                                                                                                                                                                                                                                                                                                                                                          |                          |                 1 |                0.5 |                  |            1 | ACTIVE          | 1768331273614 | 1768331273554 | 1768331273614 |          |             |           |           |           1 |   1768331273554 |
  Thanksgiving                            | default        | default       |       1 |               | t            | PERSON        |                | Thanksgiving        |                                      |                                                                |              |                                                                                                                                                                                                                                                                                                                                                                          |                          |                 1 |                0.5 |                  |            1 | ACTIVE          | 1768331273615 | 1768331273554 | 1768331273615 |          |             |           |           |           1 |   1768331273554 |
  piano                                   | default        | default       |       1 |               | t            | UNKNOWN       |                | piano               |                                      |                                                                |              |                                                                                                                                                                                                                                                                                                                                                                          |                          |                 1 |                0.5 |                  |            1 | ACTIVE          | 1768331273616 | 1768331273554 | 1768331273616 |          |             |           |           |           2 |   1768331273554 |
  recital                                 | default        | default       |       1 |               | t            | EVENT         |                | recital             |                                      |                                                                |              |                                                                                                                                                                                                                                                                                                                                                                          |                          |                 1 |                0.5 |                  |            1 | ACTIVE          | 1768331273617 | 1768331273554 | 1768331273617 |          |             |           |           |           1 |   1768331273554 |
  Lincoln School                          | default        | default       |       1 |               | t            | LOCATION      |                | Lincoln School      |                                      |                                                                |              |                                                                                                                                                                                                                                                                                                                                                                          |                          |                 1 |                0.5 |                  |            1 | ACTIVE          | 1768331273619 | 1768331273554 | 1768331273619 |          |             |           |           |           2 |   1768331273554 |
  San Francisco trip                      | default        | default       |       1 |               | t            | LOCATION      |                | San Francisco trip  |                                      |                                                                |              |                                                                                                                                                                                                                                                                                                                                                                          |                          |                 1 |                0.5 |                  |            1 | ACTIVE          | 1768331273621 | 1768331273554 | 1768331273621 |          |             |           |           |           1 |   1768331273554 |
  entity_PERSON_prince_2077e4a6           | tenant_default | space_default |       1 |               | t            | PERSON        |                | Prince              | ["me", "self", "user"]               | {"role": "self", "is_user": true}                              |              |                                                                                                                                                                                                                                                                                                                                                                          |                          |                 1 |                  1 |                  |            1 | ACTIVE          | 1768331240955 | 1768331240955 | 1768331240955 |          |             |           |           |           0 |                 |
  entity_PERSON_jeel_a8bf48ca             | tenant_default | space_default |       1 |               | t            | PERSON        |                | Jeel                | ["jeel", "wifey"]                    | {"role": "spouse", "intimacy": "HIGH"}                         |              |                                                                                                                                                                                                                                                                                                                                                                          |                          |                 1 |                  1 |                  |            1 | ACTIVE          | 1768331240955 | 1768331240955 | 1768331240955 |          |             |           |           |           0 |                 |
  entity_PERSON_sharvi_2d3f3352           | tenant_default | space_default |       1 |               | t            | PERSON        |                | Sharvi              | ["sharvi", "baby"]                   | {"role": "daughter", "intimacy": "HIGH", "age": "child"}       |              |                                                                                                                                                                                                                                                                                                                                                                          |                          |                 1 |                  1 |                  |            1 | ACTIVE          | 1768331240955 | 1768331240955 | 1768331240955 |          |             |           |           |           0 |                 |
  entity_PERSON_nayna_8529b937            | tenant_default | space_default |       1 |               | t            | PERSON        |                | Nayna               | ["nayna", "mom"]                     | {"role": "mother", "intimacy": "HIGH", "side": "maternal"}     |              |                                                                                                                                                                                                                                                                                                                                                                          |                          |                 1 |                  1 |                  |            1 | ACTIVE          | 1768331240955 | 1768331240955 | 1768331240955 |          |             |           |           |           0 |                 |
  entity_PERSON_kansagra_7bf4062f         | tenant_default | space_default |       1 |               | t            | PERSON        |                | Kansagra            | ["kansagra", "dad"]                  | {"role": "father", "intimacy": "HIGH", "side": "paternal"}     |              |                                                                                                                                                                                                                                                                                                                                                                          |                          |                 1 |                  1 |                  |            1 | ACTIVE          | 1768331240955 | 1768331240955 | 1768331240955 |          |             |           |           |           0 |                 |
  entity_PERSON_jayshree_01c14aac         | tenant_default | space_default |       1 |               | t            | PERSON        |                | Jayshree            | ["jayshree", "mother-in-law"]        | {"role": "mother-in-law", "intimacy": "MED", "side": "spouse"} |              |                                                                                                                                                                                                                                                                                                                                                                          |                          |                 1 |                  1 |                  |            1 | ACTIVE          | 1768331240955 | 1768331240955 | 1768331240955 |          |             |           |           |           0 |                 |
  entity_PERSON_jitendra_ff997e97         | tenant_default | space_default |       1 |               | t            | PERSON        |                | Jitendra            | ["jitendra", "father-in-law"]        | {"role": "father-in-law", "intimacy": "MED", "side": "spouse"} |              |                                                                                                                                                                                                                                                                                                                                                                          |                          |                 1 |                  1 |                  |            1 | ACTIVE          | 1768331240955 | 1768331240955 | 1768331240955 |          |             |           |           |           0 |                 |
  entity_PERSON_parth_04788c4f            | tenant_default | space_default |       1 |               | t            | PERSON        |                | Parth               | ["parth", "bro"]                     | {"role": "brother", "intimacy": "HIGH"}                        |              |                                                                                                                                                                                                                                                                                                                                                                          |                          |                 1 |                  1 |                  |            1 | ACTIVE          | 1768331240955 | 1768331240955 | 1768331240955 |          |             |           |           |           0 |                 |
  entity_PERSON_dada_b01abf84             | tenant_default | space_default |       1 |               | t            | PERSON        |                | Dada                | ["dada"]                             | {"role": "grandfather", "side": "paternal"}                    |              |                                                                                                                                                                                                                                                                                                                                                                          |                          |                 1 |                  1 |                  |            1 | ACTIVE          | 1768331240955 | 1768331240955 | 1768331240955 |          |             |           |           |           0 |                 |
  entity_PERSON_dadi_11cce4cb             | tenant_default | space_default |       1 |               | t            | PERSON        |                | Dadi                | ["dadi"]                             | {"role": "grandmother", "side": "paternal"}                    |              |                                                                                                                                                                                                                                                                                                                                                                          |                          |                 1 |                  1 |                  |            1 | ACTIVE          | 1768331240955 | 1768331240955 | 1768331240955 |          |             |           |           |           0 |                 |
  entity_PERSON_alex_534b44a1             | tenant_default | space_default |       1 |               | t            | PERSON        |                | Alex                | ["alex"]                             | {"context": "college", "intimacy": "MED"}                      |              |                                                                                                                                                                                                                                                                                                                                                                          |                          |                 1 |                  1 |                  |            1 | ACTIVE          | 1768331240955 | 1768331240955 | 1768331240955 |          |             |           |           |           0 |                 |
  entity_PERSON_sarah_9e9d7a08            | tenant_default | space_default |       1 |               | t            | PERSON        |                | Sarah               | ["sarah"]                            | {"context": "work", "intimacy": "MED"}                         |              |                                                                                                                                                                                                                                                                                                                                                                          |                          |                 1 |                  1 |                  |            1 | ACTIVE          | 1768331240955 | 1768331240955 | 1768331240955 |          |             |           |           |           0 |                 |
  entity_PERSON_mike_18126e7b             | tenant_default | space_default |       1 |               | t            | PERSON        |                | Mike                | ["mike"]                             | {"context": "neighborhood", "intimacy": "LOW"}                 |              |                                                                                                                                                                                                                                                                                                                                                                          |                          |                 1 |                  1 |                  |            1 | ACTIVE          | 1768331240955 | 1768331240955 | 1768331240955 |          |             |           |           |           0 |                 |
  entity_PERSON_rachel_8e73b275           | tenant_default | space_default |       1 |               | t            | PERSON        |                | Rachel              | ["rachel"]                           | {"context": "work", "department": "engineering"}               |              |                                                                                                                                                                                                                                                                                                                                                                          |                          |                 1 |                  1 |                  |            1 | ACTIVE          | 1768331240955 | 1768331240955 | 1768331240955 |          |             |           |           |           0 |                 |
  entity_PERSON_tom_34b7da76              | tenant_default | space_default |       1 |               | t            | PERSON        |                | Tom                 | ["tom"]                              | {"context": "work", "department": "product"}                   |              |                                                                                                                                                                                                                                                                                                                                                                          |                          |                 1 |                  1 |                  |            1 | ACTIVE          | 1768331240955 | 1768331240955 | 1768331240955 |          |             |           |           |           0 |                 |
  (88 rows)
  ```

  ---

  ### st_kg_edges

  **Row Count**: 58

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
  edge_id                                |   tenant_id    |   space_id    |            source_entity_id             |          target_entity_id           | version | supersedes_id | is_canonical | relation_type | relation_subtype |                     properties_json                     |     edge_weight     |  confidence_score   | source_episodes_json | co_occurrence_count | observation_count | last_observed_at | decay_factor | archival_status |  valid_from   | valid_to |  created_at   |  updated_at   | merge_cascade_id | query_count | last_queried_at | sentiment_avg
  -----------------------------------------------------------------------+----------------+---------------+-----------------------------------------+-------------------------------------+---------+---------------+--------------+---------------+------------------+---------------------------------------------------------+---------------------+---------------------+----------------------+---------------------+-------------------+------------------+--------------+-----------------+---------------+----------+---------------+---------------+------------------+-------------+-----------------+---------------
  edge_cluster_LOCATION_city sports complex_cluster_PERSON_emma         | tenant-test    | space-home    | cluster_LOCATION_city sports complex    | cluster_PERSON_emma                 |       1 |               | t            | RELATED_TO    |                  |                                                         | 0.15427500000000002 | 0.15427500000000002 | []                   |                   1 |                 1 |                  |            1 | ACTIVE          | 1768331273555 |          | 1768331273555 | 1768331273555 |                  |           0 |                 |
  edge_cluster_LOCATION_lincoln school_cluster_PERSON_emma              | tenant-test    | space-home    | cluster_LOCATION_lincoln school         | cluster_PERSON_emma                 |       1 |               | t            | RELATED_TO    |                  |                                                         | 0.21766162500000003 | 0.21766162500000003 | []                   |                   1 |                 1 |                  |            1 | ACTIVE          | 1768331273555 |          | 1768331273555 | 1768331273555 |                  |           0 |                 |
  edge_cluster_CONCEPT_fur elise_cluster_LOCATION_lincoln school        | tenant-test    | space-home    | cluster_CONCEPT_fur elise               | cluster_LOCATION_lincoln school     |       1 |               | t            | RELATED_TO    |                  |                                                         | 0.13687500000000002 | 0.13687500000000002 | []                   |                   1 |                 1 |                  |            1 | ACTIVE          | 1768331273555 |          | 1768331273555 | 1768331273555 |                  |           0 |                 |
  edge_cluster_CONCEPT_fur elise_cluster_PERSON_emma                    | tenant-test    | space-home    | cluster_CONCEPT_fur elise               | cluster_PERSON_emma                 |       1 |               | t            | RELATED_TO    |                  |                                                         | 0.13687500000000002 | 0.13687500000000002 | []                   |                   1 |                 1 |                  |            1 | ACTIVE          | 1768331273555 |          | 1768331273555 | 1768331273555 |                  |           0 |                 |
  edge_cluster_LOCATION_home_cluster_PERSON_emma                        | tenant-test    | space-home    | cluster_LOCATION_home                   | cluster_PERSON_emma                 |       1 |               | t            | RELATED_TO    |                  |                                                         |          0.15859375 |          0.15859375 | []                   |                   1 |                 1 |                  |            1 | ACTIVE          | 1768331273555 |          | 1768331273555 | 1768331273555 |                  |           0 |                 |
  edge_cluster_LOCATION_home_cluster_PERSON_jake                        | tenant-test    | space-home    | cluster_LOCATION_home                   | cluster_PERSON_jake                 |       1 |               | t            | RELATED_TO    |                  |                                                         |          0.15859375 |          0.15859375 | []                   |                   1 |                 1 |                  |            1 | ACTIVE          | 1768331273555 |          | 1768331273555 | 1768331273555 |                  |           0 |                 |
  edge_cluster_PERSON_emma_cluster_PERSON_jake                          | tenant-test    | space-home    | cluster_PERSON_emma                     | cluster_PERSON_jake                 |       1 |               | t            | RELATED_TO    |                  |                                                         |            0.154275 |            0.154275 | []                   |                   1 |                 1 |                  |            1 | ACTIVE          | 1768331273555 |          | 1768331273555 | 1768331273555 |                  |           0 |                 |
  edge_cluster_EVENT_birthday party_cluster_PERSON_emma                 | tenant-test    | space-home    | cluster_EVENT_birthday party            | cluster_PERSON_emma                 |       1 |               | t            | RELATED_TO    |                  |                                                         |          0.15859375 |          0.15859375 | []                   |                   1 |                 1 |                  |            1 | ACTIVE          | 1768331273555 |          | 1768331273555 | 1768331273555 |                  |           0 |                 |
  edge_cluster_EVENT_birthday party_cluster_PERSON_sofia                | tenant-test    | space-home    | cluster_EVENT_birthday party            | cluster_PERSON_sofia                |       1 |               | t            | RELATED_TO    |                  |                                                         |          0.15859375 |          0.15859375 | []                   |                   1 |                 1 |                  |            1 | ACTIVE          | 1768331273555 |          | 1768331273555 | 1768331273555 |                  |           0 |                 |
  edge_cluster_EVENT_birthday party_cluster_ORGANIZATION_chuck e cheese | tenant-test    | space-home    | cluster_EVENT_birthday party            | cluster_ORGANIZATION_chuck e cheese |       1 |               | t            | RELATED_TO    |                  |                                                         | 0.15427500000000002 | 0.15427500000000002 | []                   |                   1 |                 1 |                  |            1 | ACTIVE          | 1768331273555 |          | 1768331273555 | 1768331273555 |                  |           0 |                 |
  edge_cluster_PERSON_emma_cluster_PERSON_sofia                         | tenant-test    | space-home    | cluster_PERSON_emma                     | cluster_PERSON_sofia                |       1 |               | t            | RELATED_TO    |                  |                                                         |            0.154275 |            0.154275 | []                   |                   1 |                 1 |                  |            1 | ACTIVE          | 1768331273555 |          | 1768331273555 | 1768331273555 |                  |           0 |                 |
  edge_cluster_ORGANIZATION_chuck e cheese_cluster_PERSON_emma          | tenant-test    | space-home    | cluster_ORGANIZATION_chuck e cheese     | cluster_PERSON_emma                 |       1 |               | t            | RELATED_TO    |                  |                                                         |          0.14994375 |          0.14994375 | []                   |                   1 |                 1 |                  |            1 | ACTIVE          | 1768331273555 |          | 1768331273555 | 1768331273555 |                  |           0 |                 |
  edge_cluster_ORGANIZATION_chuck e cheese_cluster_PERSON_sofia         | tenant-test    | space-home    | cluster_ORGANIZATION_chuck e cheese     | cluster_PERSON_sofia                |       1 |               | t            | RELATED_TO    |                  |                                                         |          0.14994375 |          0.14994375 | []                   |                   1 |                 1 |                  |            1 | ACTIVE          | 1768331273555 |          | 1768331273555 | 1768331273555 |                  |           0 |                 |
  edge_cluster_PERSON_john_cluster_PERSON_lisa                          | tenant-test    | space-home    | cluster_PERSON_john                     | cluster_PERSON_lisa                 |       1 |               | t            | RELATED_TO    |                  |                                                         | 0.15427500000000002 | 0.15427500000000002 | []                   |                   1 |                 1 |                  |            1 | ACTIVE          | 1768331273555 |          | 1768331273555 | 1768331273555 |                  |           0 |                 |
  edge_cluster_PERSON_john_cluster_PERSON_mike                          | tenant-test    | space-home    | cluster_PERSON_john                     | cluster_PERSON_mike                 |       1 |               | t            | RELATED_TO    |                  |                                                         | 0.15427500000000002 | 0.15427500000000002 | []                   |                   1 |                 1 |                  |            1 | ACTIVE          | 1768331273555 |          | 1768331273555 | 1768331273555 |                  |           0 |                 |
  edge_cluster_PERSON_lisa_cluster_PERSON_mike                          | tenant-test    | space-home    | cluster_PERSON_lisa                     | cluster_PERSON_mike                 |       1 |               | t            | RELATED_TO    |                  |                                                         | 0.15427500000000002 | 0.15427500000000002 | []                   |                   1 |                 1 |                  |            1 | ACTIVE          | 1768331273555 |          | 1768331273555 | 1768331273555 |                  |           0 |                 |
  edge_cluster_ORGANIZATION_starbucks_cluster_PERSON_rachel             | tenant-test    | space-home    | cluster_ORGANIZATION_starbucks          | cluster_PERSON_rachel               |       1 |               | t            | RELATED_TO    |                  |                                                         | 0.26859796089843757 | 0.26859796089843757 | []                   |                   1 |                 1 |                  |            1 | ACTIVE          | 1768331273555 |          | 1768331273555 | 1768331273555 |                  |           0 |                 |
  edge_cluster_ORGANIZATION_google_cluster_PERSON_rachel                | tenant-test    | space-home    | cluster_ORGANIZATION_google             | cluster_PERSON_rachel               |       1 |               | t            | RELATED_TO    |                  |                                                         |  0.2685979608984375 |  0.2685979608984375 | []                   |                   1 |                 1 |                  |            1 | ACTIVE          | 1768331273555 |          | 1768331273555 | 1768331273555 |                  |           0 |                 |
  edge_cluster_ORGANIZATION_google_cluster_ORGANIZATION_starbucks       | tenant-test    | space-home    | cluster_ORGANIZATION_google             | cluster_ORGANIZATION_starbucks      |       1 |               | t            | RELATED_TO    |                  |                                                         | 0.26147584000000007 | 0.26147584000000007 | []                   |                   1 |                 1 |                  |            1 | ACTIVE          | 1768331273555 |          | 1768331273555 | 1768331273555 |                  |           0 |                 |
  edge_cluster_EVENT_birthday party_cluster_PERSON_tom                  | tenant-test    | space-home    | cluster_EVENT_birthday party            | cluster_PERSON_tom                  |       1 |               | t            | RELATED_TO    |                  |                                                         |          0.15859375 |          0.15859375 | []                   |                   1 |                 1 |                  |            1 | ACTIVE          | 1768331273555 |          | 1768331273555 | 1768331273555 |                  |           0 |                 |
  edge_cluster_CONCEPT_italian_cluster_ORGANIZATION_bella notte         | tenant-test    | space-home    | cluster_CONCEPT_italian                 | cluster_ORGANIZATION_bella notte    |       1 |               | t            | RELATED_TO    |                  |                                                         | 0.13249375000000002 | 0.13249375000000002 | []                   |                   1 |                 1 |                  |            1 | ACTIVE          | 1768331273555 |          | 1768331273555 | 1768331273555 |                  |           0 |                 |
  edge_cluster_CONCEPT_inception_cluster_PERSON_kevin                   | tenant-test    | space-home    | cluster_CONCEPT_inception               | cluster_PERSON_kevin                |       1 |               | t            | RELATED_TO    |                  |                                                         | 0.13687500000000002 | 0.13687500000000002 | []                   |                   1 |                 1 |                  |            1 | ACTIVE          | 1768331273555 |          | 1768331273555 | 1768331273555 |                  |           0 |                 |
  edge_cluster_CONCEPT_atomic habits_cluster_PERSON_james clear         | tenant-test    | space-home    | cluster_CONCEPT_atomic habits           | cluster_PERSON_james clear          |       1 |               | t            | RELATED_TO    |                  |                                                         | 0.13687500000000002 | 0.13687500000000002 | []                   |                   1 |                 1 |                  |            1 | ACTIVE          | 1768331273555 |          | 1768331273555 | 1768331273555 |                  |           0 |                 |
  edge_cluster_CONCEPT_python_cluster_ORGANIZATION_coursera             | tenant-test    | space-home    | cluster_CONCEPT_python                  | cluster_ORGANIZATION_coursera       |       1 |               | t            | RELATED_TO    |                  |                                                         | 0.13249375000000002 | 0.13249375000000002 | []                   |                   1 |                 1 |                  |            1 | ACTIVE          | 1768331273555 |          | 1768331273555 | 1768331273555 |                  |           0 |                 |
  edge_cluster_CONCEPT_ai_cluster_ORGANIZATION_stanford                 | tenant-test    | space-home    | cluster_CONCEPT_ai                      | cluster_ORGANIZATION_stanford       |       1 |               | t            | RELATED_TO    |                  |                                                         | 0.13249375000000002 | 0.13249375000000002 | []                   |                   1 |                 1 |                  |            1 | ACTIVE          | 1768331273555 |          | 1768331273555 | 1768331273555 |                  |           0 |                 |
  edge_cluster_CONCEPT_ai_cluster_PERSON_andrew ng                      | tenant-test    | space-home    | cluster_CONCEPT_ai                      | cluster_PERSON_andrew ng            |       1 |               | t            | RELATED_TO    |                  |                                                         | 0.13687500000000002 | 0.13687500000000002 | []                   |                   1 |                 1 |                  |            1 | ACTIVE          | 1768331273555 |          | 1768331273555 | 1768331273555 |                  |           0 |                 |
  edge_cluster_ORGANIZATION_stanford_cluster_PERSON_andrew ng           | tenant-test    | space-home    | cluster_ORGANIZATION_stanford           | cluster_PERSON_andrew ng            |       1 |               | t            | RELATED_TO    |                  |                                                         |          0.14994375 |          0.14994375 | []                   |                   1 |                 1 |                  |            1 | ACTIVE          | 1768331273555 |          | 1768331273555 | 1768331273555 |                  |           0 |                 |
  edge_cluster_ORGANIZATION_lincoln elementary_cluster_PERSON_emma      | tenant-test    | space-home    | cluster_ORGANIZATION_lincoln elementary | cluster_PERSON_emma                 |       1 |               | t            | RELATED_TO    |                  |                                                         |          0.14994375 |          0.14994375 | []                   |                   1 |                 1 |                  |            1 | ACTIVE          | 1768331273555 |          | 1768331273555 | 1768331273555 |                  |           0 |                 |
  edge_cluster_LOCATION_alcatraz_cluster_LOCATION_golden gate bridge    | tenant-test    | space-home    | cluster_LOCATION_alcatraz               | cluster_LOCATION_golden gate bridge |       1 |               | t            | RELATED_TO    |                  |                                                         | 0.14994375000000004 | 0.14994375000000004 | []                   |                   1 |                 1 |                  |            1 | ACTIVE          | 1768331273555 |          | 1768331273555 | 1768331273555 |                  |           0 |                 |
  edge_cluster_FAMILY_MEMBER_family_cluster_LOCATION_boston             | tenant-test    | space-home    | cluster_FAMILY_MEMBER_family            | cluster_LOCATION_boston             |       1 |               | t            | RELATED_TO    |                  |                                                         | 0.16290000000000004 | 0.16290000000000004 | []                   |                   1 |                 1 |                  |            1 | ACTIVE          | 1768331273555 |          | 1768331273555 | 1768331273555 |                  |           0 |                 |
  edge_cluster_CONCEPT_freedom trail_cluster_LOCATION_boston            | tenant-test    | space-home    | cluster_CONCEPT_freedom trail           | cluster_LOCATION_boston             |       1 |               | t            | RELATED_TO    |                  |                                                         | 0.13687500000000002 | 0.13687500000000002 | []                   |                   1 |                 1 |                  |            1 | ACTIVE          | 1768331273555 |          | 1768331273555 | 1768331273555 |                  |           0 |                 |
  edge_cluster_CONCEPT_freedom trail_cluster_FAMILY_MEMBER_family       | tenant-test    | space-home    | cluster_CONCEPT_freedom trail           | cluster_FAMILY_MEMBER_family        |       1 |               | t            | RELATED_TO    |                  |                                                         | 0.14560000000000003 | 0.14560000000000003 | []                   |                   1 |                 1 |                  |            1 | ACTIVE          | 1768331273555 |          | 1768331273555 | 1768331273555 |                  |           0 |                 |
  edge_cluster_LOCATION_brooklyn_cluster_LOCATION_manhattan             | tenant-test    | space-home    | cluster_LOCATION_brooklyn               | cluster_LOCATION_manhattan          |       1 |               | t            | RELATED_TO    |                  |                                                         | 0.15427500000000002 | 0.15427500000000002 | []                   |                   1 |                 1 |                  |            1 | ACTIVE          | 1768331273555 |          | 1768331273555 | 1768331273555 |                  |           0 |                 |
  edge_cluster_PERSON_alex_cluster_PERSON_chris                         | tenant-test    | space-home    | cluster_PERSON_alex                     | cluster_PERSON_chris                |       1 |               | t            | RELATED_TO    |                  |                                                         | 0.15427500000000002 | 0.15427500000000002 | []                   |                   1 |                 1 |                  |            1 | ACTIVE          | 1768331273555 |          | 1768331273555 | 1768331273555 |                  |           0 |                 |
  edge_cluster_PERSON_rachel_cluster_PERSON_tom                         | tenant-test    | space-home    | cluster_PERSON_rachel                   | cluster_PERSON_tom                  |       1 |               | t            | RELATED_TO    |                  |                                                         | 0.15427500000000002 | 0.15427500000000002 | []                   |                   1 |                 1 |                  |            1 | ACTIVE          | 1768331273555 |          | 1768331273555 | 1768331273555 |                  |           0 |                 |
  edge_cluster_FAMILY_MEMBER_brother_cluster_PERSON_jake                | tenant-test    | space-home    | cluster_FAMILY_MEMBER_brother           | cluster_PERSON_jake                 |       1 |               | t            | RELATED_TO    |                  |                                                         |              0.1629 |              0.1629 | []                   |                   1 |                 1 |                  |            1 | ACTIVE          | 1768331273555 |          | 1768331273555 | 1768331273555 |                  |           0 |                 |
  edge_cluster_FAMILY_MEMBER_brother_cluster_PERSON_sophie              | tenant-test    | space-home    | cluster_FAMILY_MEMBER_brother           | cluster_PERSON_sophie               |       1 |               | t            | RELATED_TO    |                  |                                                         |              0.1629 |              0.1629 | []                   |                   1 |                 1 |                  |            1 | ACTIVE          | 1768331273555 |          | 1768331273555 | 1768331273555 |                  |           0 |                 |
  edge_cluster_PERSON_jake_cluster_PERSON_sophie                        | tenant-test    | space-home    | cluster_PERSON_jake                     | cluster_PERSON_sophie               |       1 |               | t            | RELATED_TO    |                  |                                                         | 0.15427500000000002 | 0.15427500000000002 | []                   |                   1 |                 1 |                  |            1 | ACTIVE          | 1768331273555 |          | 1768331273555 | 1768331273555 |                  |           0 |                 |
  edge_spouse_of_090f7439ca98                                           | tenant_default | space_default | entity_PERSON_prince_2077e4a6           | entity_PERSON_jeel_a8bf48ca         |       1 |               | t            | SPOUSE_OF     | spouse           | {"seed": true, "source": "onboarding"}                  |                   1 |                   1 |                      |                   1 |                 1 |                  |            1 | ACTIVE          | 1768331240955 |          | 1768331240955 | 1768331240955 |                  |           0 |                 |
  edge_spouse_of_61d95e5129df                                           | tenant_default | space_default | entity_PERSON_jeel_a8bf48ca             | entity_PERSON_prince_2077e4a6       |       1 |               | t            | SPOUSE_OF     | spouse           | {"seed": true, "source": "onboarding", "reverse": true} |                   1 |                   1 |                      |                   1 |                 1 |                  |            1 | ACTIVE          | 1768331240955 |          | 1768331240955 | 1768331240955 |                  |           0 |                 |
  edge_parent_of_7e3ff3340051                                           | tenant_default | space_default | entity_PERSON_prince_2077e4a6           | entity_PERSON_sharvi_2d3f3352       |       1 |               | t            | PARENT_OF     | daughter         | {"seed": true, "source": "onboarding"}                  |                   1 |                   1 |                      |                   1 |                 1 |                  |            1 | ACTIVE          | 1768331240955 |          | 1768331240955 | 1768331240955 |                  |           0 |                 |
  edge_child_of_026400909cf4                                            | tenant_default | space_default | entity_PERSON_prince_2077e4a6           | entity_PERSON_nayna_8529b937        |       1 |               | t            | CHILD_OF      | mother           | {"seed": true, "source": "onboarding"}                  |                   1 |                   1 |                      |                   1 |                 1 |                  |            1 | ACTIVE          | 1768331240955 |          | 1768331240955 | 1768331240955 |                  |           0 |                 |
  edge_child_of_7ab6085d6955                                            | tenant_default | space_default | entity_PERSON_prince_2077e4a6           | entity_PERSON_kansagra_7bf4062f     |       1 |               | t            | CHILD_OF      | father           | {"seed": true, "source": "onboarding"}                  |                   1 |                   1 |                      |                   1 |                 1 |                  |            1 | ACTIVE          | 1768331240955 |          | 1768331240955 | 1768331240955 |                  |           0 |                 |
  edge_child_of_5c97751a65ee                                            | tenant_default | space_default | entity_PERSON_prince_2077e4a6           | entity_PERSON_jayshree_01c14aac     |       1 |               | t            | CHILD_OF      | mother-in-law    | {"seed": true, "source": "onboarding"}                  |                   1 |                   1 |                      |                   1 |                 1 |                  |            1 | ACTIVE          | 1768331240955 |          | 1768331240955 | 1768331240955 |                  |           0 |                 |
  edge_child_of_058150d309e3                                            | tenant_default | space_default | entity_PERSON_prince_2077e4a6           | entity_PERSON_jitendra_ff997e97     |       1 |               | t            | CHILD_OF      | father-in-law    | {"seed": true, "source": "onboarding"}                  |                   1 |                   1 |                      |                   1 |                 1 |                  |            1 | ACTIVE          | 1768331240955 |          | 1768331240955 | 1768331240955 |                  |           0 |                 |
  edge_sibling_of_f389cc759c52                                          | tenant_default | space_default | entity_PERSON_prince_2077e4a6           | entity_PERSON_parth_04788c4f        |       1 |               | t            | SIBLING_OF    | brother          | {"seed": true, "source": "onboarding"}                  |                   1 |                   1 |                      |                   1 |                 1 |                  |            1 | ACTIVE          | 1768331240955 |          | 1768331240955 | 1768331240955 |                  |           0 |                 |
  edge_sibling_of_e2f55adce586                                          | tenant_default | space_default | entity_PERSON_parth_04788c4f            | entity_PERSON_prince_2077e4a6       |       1 |               | t            | SIBLING_OF    | brother          | {"seed": true, "source": "onboarding", "reverse": true} |                   1 |                   1 |                      |                   1 |                 1 |                  |            1 | ACTIVE          | 1768331240955 |          | 1768331240955 | 1768331240955 |                  |           0 |                 |
  edge_grandchild_of_cf12180c7c83                                       | tenant_default | space_default | entity_PERSON_prince_2077e4a6           | entity_PERSON_dada_b01abf84         |       1 |               | t            | GRANDCHILD_OF | grandfather      | {"seed": true, "source": "onboarding"}                  |                   1 |                   1 |                      |                   1 |                 1 |                  |            1 | ACTIVE          | 1768331240955 |          | 1768331240955 | 1768331240955 |                  |           0 |                 |
  edge_grandchild_of_4322761954a0                                       | tenant_default | space_default | entity_PERSON_prince_2077e4a6           | entity_PERSON_dadi_11cce4cb         |       1 |               | t            | GRANDCHILD_OF | grandmother      | {"seed": true, "source": "onboarding"}                  |                   1 |                   1 |                      |                   1 |                 1 |                  |            1 | ACTIVE          | 1768331240955 |          | 1768331240955 | 1768331240955 |                  |           0 |                 |
  edge_friend_of_e302fb83c549                                           | tenant_default | space_default | entity_PERSON_prince_2077e4a6           | entity_PERSON_alex_534b44a1         |       1 |               | t            | FRIEND_OF     |                  | {"seed": true, "source": "onboarding"}                  |                   1 |                   1 |                      |                   1 |                 1 |                  |            1 | ACTIVE          | 1768331240955 |          | 1768331240955 | 1768331240955 |                  |           0 |                 |
  edge_friend_of_3bb7bf9e442e                                           | tenant_default | space_default | entity_PERSON_alex_534b44a1             | entity_PERSON_prince_2077e4a6       |       1 |               | t            | FRIEND_OF     |                  | {"seed": true, "source": "onboarding", "reverse": true} |                   1 |                   1 |                      |                   1 |                 1 |                  |            1 | ACTIVE          | 1768331240955 |          | 1768331240955 | 1768331240955 |                  |           0 |                 |
  edge_friend_of_c485a239d5e4                                           | tenant_default | space_default | entity_PERSON_prince_2077e4a6           | entity_PERSON_sarah_9e9d7a08        |       1 |               | t            | FRIEND_OF     |                  | {"seed": true, "source": "onboarding"}                  |                   1 |                   1 |                      |                   1 |                 1 |                  |            1 | ACTIVE          | 1768331240955 |          | 1768331240955 | 1768331240955 |                  |           0 |                 |
  edge_friend_of_2588f1fb594d                                           | tenant_default | space_default | entity_PERSON_sarah_9e9d7a08            | entity_PERSON_prince_2077e4a6       |       1 |               | t            | FRIEND_OF     |                  | {"seed": true, "source": "onboarding", "reverse": true} |                   1 |                   1 |                      |                   1 |                 1 |                  |            1 | ACTIVE          | 1768331240955 |          | 1768331240955 | 1768331240955 |                  |           0 |                 |
  edge_friend_of_589c1d6a64d8                                           | tenant_default | space_default | entity_PERSON_prince_2077e4a6           | entity_PERSON_mike_18126e7b         |       1 |               | t            | FRIEND_OF     |                  | {"seed": true, "source": "onboarding"}                  |                   1 |                   1 |                      |                   1 |                 1 |                  |            1 | ACTIVE          | 1768331240955 |          | 1768331240955 | 1768331240955 |                  |           0 |                 |
  edge_friend_of_684e75ac6c7a                                           | tenant_default | space_default | entity_PERSON_mike_18126e7b             | entity_PERSON_prince_2077e4a6       |       1 |               | t            | FRIEND_OF     |                  | {"seed": true, "source": "onboarding", "reverse": true} |                   1 |                   1 |                      |                   1 |                 1 |                  |            1 | ACTIVE          | 1768331240955 |          | 1768331240955 | 1768331240955 |                  |           0 |                 |
  edge_colleague_of_45a945c9a414                                        | tenant_default | space_default | entity_PERSON_prince_2077e4a6           | entity_PERSON_rachel_8e73b275       |       1 |               | t            | COLLEAGUE_OF  |                  | {"seed": true, "source": "onboarding"}                  |                   1 |                   1 |                      |                   1 |                 1 |                  |            1 | ACTIVE          | 1768331240955 |          | 1768331240955 | 1768331240955 |                  |           0 |                 |
  edge_colleague_of_b30672ef7d26                                        | tenant_default | space_default | entity_PERSON_prince_2077e4a6           | entity_PERSON_tom_34b7da76          |       1 |               | t            | COLLEAGUE_OF  |                  | {"seed": true, "source": "onboarding"}                  |                   1 |                   1 |                      |                   1 |                 1 |                  |            1 | ACTIVE          | 1768331240955 |          | 1768331240955 | 1768331240955 |                  |           0 |                 |
  edge_parent_of_0f0036266fd2                                           | tenant_default | space_default | entity_PERSON_jeel_a8bf48ca             | entity_PERSON_sharvi_2d3f3352       |       1 |               | t            | PARENT_OF     | mother           | {"seed": true, "derived": true}                         |                   1 |                   1 |                      |                   1 |                 1 |                  |            1 | ACTIVE          | 1768331240955 |          | 1768331240955 | 1768331240955 |                  |           0 |                 |
  (58 rows)
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
  (28 rows)
  ```

  **Sample Data** (showing 10 of 66 rows):

  ```
  pattern_id                |  tenant_id  |  space_id  | actor_id | version | supersedes_id | is_canonical | pattern_type | pattern_subtype |                   pattern_name                    | pattern_description | pattern_attributes_json | temporal_regularity | temporal_pattern_json |           source_episodes_json           | source_episode_count |             embedding_id             | observation_count | confidence_score | last_observed_at | first_observed_at | decay_factor | archival_status |  created_at   |  updated_at   |  valid_from   | valid_to | merge_cascade_id
  ------------------------------------------+-------------+------------+----------+---------+---------------+--------------+--------------+-----------------+---------------------------------------------------+---------------------+-------------------------+---------------------+-----------------------+------------------------------------------+----------------------+--------------------------------------+-------------------+------------------+------------------+-------------------+--------------+-----------------+---------------+---------------+---------------+----------+------------------
  sem_fb5dae74-9a59-4cfa-b331-2368651e0332 | tenant-test | space-home |          |       1 |               | t            | THEME        |                 | Pattern from fb5dae74-9a59-4cfa-b331-2368651e0332 |                     |                         |                     |                       | ["fb5dae74-9a59-4cfa-b331-2368651e0332"] |                    1 | 09dd86a5-a500-4b7f-a4b4-ebf0b5de4721 |                 1 |            0.545 |    1768331273553 |     1768331273553 |            1 | ACTIVE          | 1768331273553 | 1768331273553 | 1768331273553 |          |
  sem_4127bec2-100e-4de0-97a0-4fff1fb854e1 | tenant-test | space-home |          |       1 |               | t            | THEME        |                 | Pattern from 4127bec2-100e-4de0-97a0-4fff1fb854e1 |                     |                         |                     |                       | ["4127bec2-100e-4de0-97a0-4fff1fb854e1"] |                    1 | aa463cbb-f9c0-4105-b1c8-0b337a2f3010 |                 1 |            0.545 |    1768331273553 |     1768331273553 |            1 | ACTIVE          | 1768331273553 | 1768331273553 | 1768331273553 |          |
  sem_f0d38122-25fe-45c4-a124-6d61d0ac5c18 | tenant-test | space-home |          |       1 |               | t            | THEME        |                 | Pattern from f0d38122-25fe-45c4-a124-6d61d0ac5c18 |                     |                         |                     |                       | ["f0d38122-25fe-45c4-a124-6d61d0ac5c18"] |                    1 | 2f80bf8d-ecf5-42e7-9e09-375592e5dd08 |                 1 |            0.545 |    1768331273553 |     1768331273553 |            1 | ACTIVE          | 1768331273553 | 1768331273553 | 1768331273553 |          |
  sem_f7ee02e0-b217-4d38-8b34-32da9e49cd58 | tenant-test | space-home |          |       1 |               | t            | THEME        |                 | Pattern from f7ee02e0-b217-4d38-8b34-32da9e49cd58 |                     |                         |                     |                       | ["f7ee02e0-b217-4d38-8b34-32da9e49cd58"] |                    1 | 451ba581-7993-49b1-b849-477d5a3547b2 |                 1 |            0.545 |    1768331273553 |     1768331273553 |            1 | ACTIVE          | 1768331273553 | 1768331273553 | 1768331273553 |          |
  sem_363171c8-397f-4950-8bfd-92d9a0d12180 | tenant-test | space-home |          |       1 |               | t            | THEME        |                 | Pattern from 363171c8-397f-4950-8bfd-92d9a0d12180 |                     |                         |                     |                       | ["363171c8-397f-4950-8bfd-92d9a0d12180"] |                    1 | d0786d09-fdda-4cad-bf8b-f09dd2088c2a |                 1 |            0.545 |    1768331273553 |     1768331273553 |            1 | ACTIVE          | 1768331273553 | 1768331273553 | 1768331273553 |          |
  sem_aa6baef3-021b-4891-a8a8-3acdc28541e8 | tenant-test | space-home |          |       1 |               | t            | THEME        |                 | Pattern from aa6baef3-021b-4891-a8a8-3acdc28541e8 |                     |                         |                     |                       | ["aa6baef3-021b-4891-a8a8-3acdc28541e8"] |                    1 | c0eb279e-7b5d-4f3c-a962-40e63d004bc8 |                 1 |            0.545 |    1768331273553 |     1768331273553 |            1 | ACTIVE          | 1768331273553 | 1768331273553 | 1768331273553 |          |
  sem_1dc23260-e4e7-418a-9564-98857591b926 | tenant-test | space-home |          |       1 |               | t            | THEME        |                 | Pattern from 1dc23260-e4e7-418a-9564-98857591b926 |                     |                         |                     |                       | ["1dc23260-e4e7-418a-9564-98857591b926"] |                    1 | f4c9df38-fb94-4c56-9b95-69ad136a12bf |                 1 |            0.545 |    1768331273553 |     1768331273553 |            1 | ACTIVE          | 1768331273553 | 1768331273553 | 1768331273553 |          |
  sem_8f9b3a32-43aa-48a6-85ad-0954ef90e9e1 | tenant-test | space-home |          |       1 |               | t            | THEME        |                 | Pattern from 8f9b3a32-43aa-48a6-85ad-0954ef90e9e1 |                     |                         |                     |                       | ["8f9b3a32-43aa-48a6-85ad-0954ef90e9e1"] |                    1 | 2dc2a451-0e76-4525-9915-bc492ffb2858 |                 1 |            0.545 |    1768331273553 |     1768331273553 |            1 | ACTIVE          | 1768331273553 | 1768331273553 | 1768331273553 |          |
  sem_708a1763-3516-4702-bdf9-9d9301bf7807 | tenant-test | space-home |          |       1 |               | t            | THEME        |                 | Pattern from 708a1763-3516-4702-bdf9-9d9301bf7807 |                     |                         |                     |                       | ["708a1763-3516-4702-bdf9-9d9301bf7807"] |                    1 | b5deb20e-242c-401d-83ce-2ec6637556f7 |                 1 |            0.545 |    1768331273553 |     1768331273553 |            1 | ACTIVE          | 1768331273553 | 1768331273553 | 1768331273553 |          |
  sem_afb69564-97fa-4bfd-85d0-76b29937f85a | tenant-test | space-home |          |       1 |               | t            | THEME        |                 | Pattern from afb69564-97fa-4bfd-85d0-76b29937f85a |                     |                         |                     |                       | ["afb69564-97fa-4bfd-85d0-76b29937f85a"] |                    1 | dd079f2b-088a-4b5e-aa43-b6eb78d1913e |                 1 |            0.545 |    1768331273553 |     1768331273553 |            1 | ACTIVE          | 1768331273553 | 1768331273553 | 1768331273553 |          |
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
  (39 rows)
  ```

  **Sample Data** (showing 10 of 22 rows):

  ```
  relationship_id     |  tenant_id  |  space_id  | actor_a_id | actor_b_id | version | supersedes_id | is_canonical | relationship_type | relationship_subtype | relationship_label | interaction_count | avg_sentiment | relationship_strength | intimacy_level | first_interaction_at | last_interaction_at | interaction_frequency |                                                                                                                                                                                                                                       source_episodes_json                                                                                                                                                                                                                                       | observation_count | confidence_score | decay_factor | archival_status |  created_at   |  updated_at   |  valid_from   | valid_to | merge_cascade_id | ultrabert_relation_types | emotional_role | emotional_valence_avg | emotional_valence_trend | relationship_phase | interaction_modalities_json |      typical_activities_json       |                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         sentiment_trajectory_json                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          |                                                                         emotions_json                                                                         | dominant_emotion | canonical_entity_id
  -------------------------+-------------+------------+------------+------------+---------+---------------+--------------+-------------------+----------------------+--------------------+-------------------+---------------+-----------------------+----------------+----------------------+---------------------+-----------------------+--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+-------------------+------------------+--------------+-----------------+---------------+---------------+---------------+----------+------------------+--------------------------+----------------+-----------------------+-------------------------+--------------------+-----------------------------+------------------------------------+--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+---------------------------------------------------------------------------------------------------------------------------------------------------------------+------------------+----------------------
  social_a2ca0d40a0e46681 | tenant-test | space-home | Prince     | Emma       |       1 |               | t            | FRIEND            |                      | Emma               |                12 |             0 |                   0.8 | LOW            |        1768331273554 |       1768331273554 |                       | ["fb5dae74-9a59-4cfa-b331-2368651e0332", "4127bec2-100e-4de0-97a0-4fff1fb854e1", "f0d38122-25fe-45c4-a124-6d61d0ac5c18", "f7ee02e0-b217-4d38-8b34-32da9e49cd58", "92c4461c-1f97-419d-bec0-a676a08f2d5b", "06f9739c-1ba0-4ba1-a605-9c7ca8d26a7a", "60b68a4b-56da-4374-94d8-74350ccd1b3d", "6623cb1b-e485-43ad-8153-45c0714a72ff", "664f2a14-4cba-4b80-ba6b-b8b75c31b2fe", "432d77ac-b58d-48d6-a71c-efb1e68b2804", "1f801366-e663-4aa7-b887-1a59b7c1a996", "d8043681-a460-43fd-979b-eb905a11b4ec"] |                 1 |              0.8 |            1 | ACTIVE          | 1768331273554 | 1768331273554 | 1768331273554 |          |                  | []                       | ENERGY_SOURCE  |                     0 |                       0 | STABLE             | ["in_person"]               | ["milestone", "social", "routine"] | [{"event_id": "f0d38122-25fe-45c4-a124-6d61d0ac5c18", "sentiment": "neutral", "valence": 0.0, "confidence": 0.5, "timestamp": 0}, {"event_id": "f7ee02e0-b217-4d38-8b34-32da9e49cd58", "sentiment": "neutral", "valence": 0.0, "confidence": 0.5, "timestamp": 0}, {"event_id": "92c4461c-1f97-419d-bec0-a676a08f2d5b", "sentiment": "neutral", "valence": 0.0, "confidence": 0.5, "timestamp": 0}, {"event_id": "06f9739c-1ba0-4ba1-a605-9c7ca8d26a7a", "sentiment": "neutral", "valence": 0.0, "confidence": 0.5, "timestamp": 0}, {"event_id": "60b68a4b-56da-4374-94d8-74350ccd1b3d", "sentiment": "neutral", "valence": 0.0, "confidence": 0.5, "timestamp": 0}, {"event_id": "6623cb1b-e485-43ad-8153-45c0714a72ff", "sentiment": "neutral", "valence": 0.0, "confidence": 0.5, "timestamp": 0}, {"event_id": "664f2a14-4cba-4b80-ba6b-b8b75c31b2fe", "sentiment": "neutral", "valence": 0.0, "confidence": 0.5, "timestamp": 0}, {"event_id": "432d77ac-b58d-48d6-a71c-efb1e68b2804", "sentiment": "neutral", "valence": 0.0, "confidence": 0.5, "timestamp": 0}, {"event_id": "1f801366-e663-4aa7-b887-1a59b7c1a996", "sentiment": "neutral", "valence": 0.0, "confidence": 0.5, "timestamp": 0}, {"event_id": "d8043681-a460-43fd-979b-eb905a11b4ec", "sentiment": "neutral", "valence": 0.0, "confidence": 0.5, "timestamp": 0}] | {"joy": 7, "excitement": 5, "pride": 4, "contentment": 3, "togetherness": 1, "neutral": 3, "caring": 1, "hope": 1, "love": 1, "gratitude": 1, "nostalgia": 1} | joy              | cluster_PERSON_emma
  social_f85e9c0735e716dc | tenant-test | space-home | Prince     | Jake       |       1 |               | t            | FRIEND            |                      | Jake               |                 5 |             0 |                  0.75 | LOW            |        1768331273554 |       1768331273554 |                       | ["f0d38122-25fe-45c4-a124-6d61d0ac5c18", "06f9739c-1ba0-4ba1-a605-9c7ca8d26a7a", "664f2a14-4cba-4b80-ba6b-b8b75c31b2fe", "432d77ac-b58d-48d6-a71c-efb1e68b2804", "f1206aec-da79-470f-8daf-b06854ae805d"]                                                                                                                                                                                                                                                                                         |                 1 |             0.75 |            1 | ACTIVE          | 1768331273554 | 1768331273554 | 1768331273554 |          |                  | []                       | ENERGY_SOURCE  |                     0 |                       0 | STABLE             | ["in_person"]               | ["milestone", "social", "routine"] | [{"event_id": "f0d38122-25fe-45c4-a124-6d61d0ac5c18", "sentiment": "neutral", "valence": 0.0, "confidence": 0.5, "timestamp": 0}, {"event_id": "06f9739c-1ba0-4ba1-a605-9c7ca8d26a7a", "sentiment": "neutral", "valence": 0.0, "confidence": 0.5, "timestamp": 0}, {"event_id": "664f2a14-4cba-4b80-ba6b-b8b75c31b2fe", "sentiment": "neutral", "valence": 0.0, "confidence": 0.5, "timestamp": 0}, {"event_id": "432d77ac-b58d-48d6-a71c-efb1e68b2804", "sentiment": "neutral", "valence": 0.0, "confidence": 0.5, "timestamp": 0}, {"event_id": "f1206aec-da79-470f-8daf-b06854ae805d", "sentiment": "neutral", "valence": 0.0, "confidence": 0.5, "timestamp": 0}]                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      | {"joy": 3, "contentment": 3, "togetherness": 1, "excitement": 2, "neutral": 1, "love": 1, "gratitude": 1, "pride": 1}                                         | joy              | cluster_PERSON_jake
  social_4fd00dbab586f9de | tenant-test | space-home | Prince     | Sofia      |       1 |               | t            | FRIEND            |                      | Sofia              |                 1 |             0 |                  0.55 | LOW            |        1768331273554 |       1768331273554 |                       | ["f7ee02e0-b217-4d38-8b34-32da9e49cd58"]                                                                                                                                                                                                                                                                                                                                                                                                                                                         |                 1 |             0.55 |            1 | ACTIVE          | 1768331273554 | 1768331273554 | 1768331273554 |          |                  | []                       | ENERGY_SOURCE  |                     0 |                       0 | FORMING            | ["in_person"]               | ["social"]                         | [{"event_id": "f7ee02e0-b217-4d38-8b34-32da9e49cd58", "sentiment": "neutral", "valence": 0.0, "confidence": 0.5, "timestamp": 0}]                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          | {"joy": 1}                                                                                                                                                    | joy              | cluster_PERSON_sofia
  social_d62eafb707088373 | tenant-test | space-home | Prince     | John       |       1 |               | t            | FRIEND            |                      | John               |                 3 |             0 |                  0.65 | LOW            |        1768331273554 |       1768331273554 |                       | ["363171c8-397f-4950-8bfd-92d9a0d12180", "708a1763-3516-4702-bdf9-9d9301bf7807", "98ef5b83-2e0e-4d82-b744-acba3b4ef136"]                                                                                                                                                                                                                                                                                                                                                                         |                 1 |             0.65 |            1 | ACTIVE          | 1768331273554 | 1768331273554 | 1768331273554 |          |                  | []                       |                |                     0 |                       0 | STABLE             | ["in_person"]               | ["work"]                           | [{"event_id": "363171c8-397f-4950-8bfd-92d9a0d12180", "sentiment": "neutral", "valence": 0.0, "confidence": 0.5, "timestamp": 0}, {"event_id": "708a1763-3516-4702-bdf9-9d9301bf7807", "sentiment": "neutral", "valence": 0.0, "confidence": 0.5, "timestamp": 0}, {"event_id": "98ef5b83-2e0e-4d82-b744-acba3b4ef136", "sentiment": "neutral", "valence": 0.0, "confidence": 0.5, "timestamp": 0}]                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        | {"neutral": 2, "annoyance": 1, "disappointment": 1, "frustration": 1}                                                                                         | neutral          | cluster_PERSON_john
  social_727f20506d459852 | tenant-test | space-home | Prince     | Lisa       |       1 |               | t            | FRIEND            |                      | Lisa               |                 2 |             0 |                   0.6 | LOW            |        1768331273554 |       1768331273554 |                       | ["363171c8-397f-4950-8bfd-92d9a0d12180", "708a1763-3516-4702-bdf9-9d9301bf7807"]                                                                                                                                                                                                                                                                                                                                                                                                                 |                 1 |              0.6 |            1 | ACTIVE          | 1768331273554 | 1768331273554 | 1768331273554 |          |                  | []                       |                |                     0 |                       0 | FORMING            | ["in_person"]               | ["work"]                           | [{"event_id": "363171c8-397f-4950-8bfd-92d9a0d12180", "sentiment": "neutral", "valence": 0.0, "confidence": 0.5, "timestamp": 0}, {"event_id": "708a1763-3516-4702-bdf9-9d9301bf7807", "sentiment": "neutral", "valence": 0.0, "confidence": 0.5, "timestamp": 0}]                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         | {"neutral": 2}                                                                                                                                                | neutral          | cluster_PERSON_lisa
  social_2fdf7b19a69d8535 | tenant-test | space-home | Prince     | Mike       |       1 |               | t            | FRIEND            |                      | Mike               |                 3 |             0 |                  0.65 | LOW            |        1768331273554 |       1768331273554 |                       | ["363171c8-397f-4950-8bfd-92d9a0d12180", "8f9b3a32-43aa-48a6-85ad-0954ef90e9e1", "98ef5b83-2e0e-4d82-b744-acba3b4ef136"]                                                                                                                                                                                                                                                                                                                                                                         |                 1 |             0.65 |            1 | ACTIVE          | 1768331273554 | 1768331273554 | 1768331273554 |          |                  | []                       | CONFIDANT      |                     0 |                       0 | STABLE             | ["in_person"]               | ["work"]                           | [{"event_id": "363171c8-397f-4950-8bfd-92d9a0d12180", "sentiment": "neutral", "valence": 0.0, "confidence": 0.5, "timestamp": 0}, {"event_id": "8f9b3a32-43aa-48a6-85ad-0954ef90e9e1", "sentiment": "neutral", "valence": 0.0, "confidence": 0.5, "timestamp": 0}, {"event_id": "98ef5b83-2e0e-4d82-b744-acba3b4ef136", "sentiment": "neutral", "valence": 0.0, "confidence": 0.5, "timestamp": 0}]                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        | {"neutral": 1, "relief": 1, "annoyance": 1, "disappointment": 1, "frustration": 1}                                                                            | neutral          | cluster_PERSON_mike
  social_be1253db38b9451e | tenant-test | space-home | Prince     | Sarah      |       1 |               | t            | FRIEND            |                      | Sarah              |                 2 |             0 |                   0.6 | LOW            |        1768331273554 |       1768331273554 |                       | ["aa6baef3-021b-4891-a8a8-3acdc28541e8", "ca87f8b3-f1c3-43b9-9345-4070cffd53bc"]                                                                                                                                                                                                                                                                                                                                                                                                                 |                 1 |              0.6 |            1 | ACTIVE          | 1768331273554 | 1768331273554 | 1768331273554 |          |                  | []                       | ENERGY_SOURCE  |                     0 |                       0 | FORMING            | ["in_person"]               | ["work"]                           | [{"event_id": "aa6baef3-021b-4891-a8a8-3acdc28541e8", "sentiment": "neutral", "valence": 0.0, "confidence": 0.5, "timestamp": 0}, {"event_id": "ca87f8b3-f1c3-43b9-9345-4070cffd53bc", "sentiment": "neutral", "valence": 0.0, "confidence": 0.5, "timestamp": 0}]                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         | {"neutral": 1, "joy": 1, "excitement": 1, "pride": 1}                                                                                                         | neutral          | cluster_PERSON_sarah
  social_d2f6c81ae0766042 | tenant-test | space-home | Prince     | David      |       1 |               | t            | FRIEND            |                      | David              |                 2 |             0 |                   0.6 | LOW            |        1768331273554 |       1768331273554 |                       | ["1dc23260-e4e7-418a-9564-98857591b926", "c3e80979-e1ad-4313-b1f5-b7d144803d03"]                                                                                                                                                                                                                                                                                                                                                                                                                 |                 1 |              0.6 |            1 | ACTIVE          | 1768331273554 | 1768331273554 | 1768331273554 |          |                  | []                       | ENERGY_SOURCE  |                     0 |                       0 | FORMING            | ["in_person"]               | ["work", "routine"]                | [{"event_id": "1dc23260-e4e7-418a-9564-98857591b926", "sentiment": "neutral", "valence": 0.0, "confidence": 0.5, "timestamp": 0}, {"event_id": "c3e80979-e1ad-4313-b1f5-b7d144803d03", "sentiment": "neutral", "valence": 0.0, "confidence": 0.5, "timestamp": 0}]                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         | {"joy": 2, "pride": 1, "excitement": 1}                                                                                                                       | joy              | cluster_PERSON_david
  social_f1e364a3a19521fa | tenant-test | space-home | Prince     | Dr. Smith  |       1 |               | t            | FRIEND            |                      | Dr. Smith          |                 2 |             0 |                   0.6 | LOW            |        1768331273554 |       1768331273554 |                       | ["f2e418ac-859e-4930-97f1-6e645ce43d00", "7c7bad91-1f21-41a0-b16a-c9a621fbf79f"]                                                                                                                                                                                                                                                                                                                                                                                                                 |                 1 |              0.6 |            1 | ACTIVE          | 1768331273554 | 1768331273554 | 1768331273554 |          |                  | []                       | SUPPORT_GIVER  |                     0 |                       0 | FORMING            | ["in_person"]               | ["unknown", "routine"]             | [{"event_id": "f2e418ac-859e-4930-97f1-6e645ce43d00", "sentiment": "neutral", "valence": 0.0, "confidence": 0.5, "timestamp": 0}, {"event_id": "7c7bad91-1f21-41a0-b16a-c9a621fbf79f", "sentiment": "neutral", "valence": 0.0, "confidence": 0.5, "timestamp": 0}]                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         | {"neutral": 2, "worry": 1}                                                                                                                                    | neutral          |
  social_f9c2bf662684c3db | tenant-test | space-home | Prince     | Maria      |       1 |               | t            | FRIEND            |                      | Maria              |                 1 |             0 |                  0.55 | LOW            |        1768331273554 |       1768331273554 |                       | ["a8a074c8-2322-47fe-a590-676c26514737"]                                                                                                                                                                                                                                                                                                                                                                                                                                                         |                 1 |             0.55 |            1 | ACTIVE          | 1768331273554 | 1768331273554 | 1768331273554 |          |                  | []                       |                |                     0 |                       0 | FORMING            | ["in_person"]               | ["routine"]                        | [{"event_id": "a8a074c8-2322-47fe-a590-676c26514737", "sentiment": "neutral", "valence": 0.0, "confidence": 0.5, "timestamp": 0}]                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          | {"neutral": 1}                                                                                                                                                | neutral          | cluster_PERSON_maria
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
  (29 rows)
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
  (22 rows)
  ```

  **Data**:

  ```
  intention_id                  |  tenant_id  |  space_id  | actor_id | version | supersedes_id | is_canonical | intention_type |                              intention_description                               | target_date |                                  target_context                                  | status |                                                                                                                     inferred_from_json                                                                                                                     | inference_confidence | observation_count | confidence_score | decay_factor | archival_status |  created_at   |  updated_at   |  valid_from   | valid_to
  -----------------------------------------------+-------------+------------+----------+---------+---------------+--------------+----------------+----------------------------------------------------------------------------------+-------------+----------------------------------------------------------------------------------+--------+------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+----------------------+-------------------+------------------+--------------+-----------------+---------------+---------------+---------------+----------
  reminder_594c7e01-a373-4e41-bd1b-631eb1a33dbd | tenant-test | space-home | system   |       1 |               | t            | REMINDER       | call Mom                                                                         |             | Remind me to call Mom tomorrow at 3pm for her birthday.                          | ACTIVE | ["594c7e01-a373-4e41-bd1b-631eb1a33dbd"]                                                                                                                                                                                                                   |                  0.8 |                 1 |              0.8 |            1 | ACTIVE          | 1768331273554 | 1768331273554 | 1768331273554 |
  reminder_b2cf0660-778a-49e3-9760-0faa085e8a8c | tenant-test | space-home | system   |       1 |               | t            | REMINDER       | remember to submit the quarterly report by Friday at 5pm                         |             | Need to remember to submit the quarterly report by Friday at 5pm.                | ACTIVE | ["b2cf0660-778a-49e3-9760-0faa085e8a8c"]                                                                                                                                                                                                                   |                  0.8 |                 1 |              0.8 |            1 | ACTIVE          | 1768331273554 | 1768331273554 | 1768331273554 |
  reminder_60b68a4b-56da-4374-94d8-74350ccd1b3d | tenant-test | space-home | system   |       1 |               | t            | REMINDER       | to pick up Emma from soccer practice                                             |             | Set a reminder to pick up Emma from soccer practice at 4:30pm.                   | ACTIVE | ["60b68a4b-56da-4374-94d8-74350ccd1b3d"]                                                                                                                                                                                                                   |                  0.8 |                 1 |              0.8 |            1 | ACTIVE          | 1768331273554 | 1768331273554 | 1768331273554 |
  reminder_6fae7292-07e6-4f5e-b066-aea01a8dea7d | tenant-test | space-home | system   |       1 |               | t            | REMINDER       | Don't let me forget to water the plants in 2 hours.                              |             | Don't let me forget to water the plants in 2 hours.                              | ACTIVE | ["6fae7292-07e6-4f5e-b066-aea01a8dea7d"]                                                                                                                                                                                                                   |                  0.8 |                 1 |              0.8 |            1 | ACTIVE          | 1768331273554 | 1768331273554 | 1768331273554 |
  reminder_87e9655a-84a3-4fb3-845e-2a97d68d5b3e | tenant-test | space-home | system   |       1 |               | t            | REMINDER       | Remind me next Monday to schedule the dentist appointment.                       |             | Remind me next Monday to schedule the dentist appointment.                       | ACTIVE | ["87e9655a-84a3-4fb3-845e-2a97d68d5b3e"]                                                                                                                                                                                                                   |                  0.8 |                 1 |              0.8 |            1 | ACTIVE          | 1768331273554 | 1768331273554 | 1768331273554 |
  decision_150f0a08-46ca-44ce-a1b4-2789b5cc0859 | tenant-test | space-home | system   |       1 |               | t            | DECISION       | Should I take the new job offer from Google or stay at my current company?       |             | Should I take the new job offer from Google or stay at my current company?       | ACTIVE | {"decision_options": ["take the new job offer from Google", "stay at my current company"], "decision_context": "Should I take the new job offer from Google or stay at my current company?", "source_event_ids": ["150f0a08-46ca-44ce-a1b4-2789b5cc0859"]} |                  0.8 |                 1 |              0.8 |            1 | ACTIVE          | 1768331273554 | 1768331273554 | 1768331273554 |
  decision_ad9da1ef-8783-4294-9747-2df8d5336a58 | tenant-test | space-home | system   |       1 |               | t            | DECISION       | I'm trying to decide between buying a house in Brooklyn or renting in Manhattan. |             | I'm trying to decide between buying a house in Brooklyn or renting in Manhattan. | ACTIVE | {"decision_options": [], "decision_context": "I'm trying to decide between buying a house in Brooklyn or renting in Manhattan.", "source_event_ids": ["ad9da1ef-8783-4294-9747-2df8d5336a58"]}                                                             |                  0.8 |                 1 |              0.8 |            1 | ACTIVE          | 1768331273554 | 1768331273554 | 1768331273554 |
  decision_6623cb1b-e485-43ad-8153-45c0714a72ff | tenant-test | space-home | system   |       1 |               | t            | DECISION       | What do you think - should Emma switch from soccer to basketball?                |             | What do you think - should Emma switch from soccer to basketball?                | ACTIVE | {"decision_options": [], "decision_context": "What do you think - should Emma switch from soccer to basketball?", "source_event_ids": ["6623cb1b-e485-43ad-8153-45c0714a72ff"]}                                                                            |                  0.8 |                 1 |              0.8 |            1 | ACTIVE          | 1768331273554 | 1768331273554 | 1768331273554 |
  decision_ad3e227c-db90-45e5-b9e5-8ee100ccc65c | tenant-test | space-home | system   |       1 |               | t            | DECISION       | I need advice on whether to invest in stocks or bonds right now.                 |             | I need advice on whether to invest in stocks or bonds right now.                 | ACTIVE | {"decision_options": ["invest in stocks", "bonds right now"], "decision_context": "I need advice on whether to invest in stocks or bonds right now.", "source_event_ids": ["ad3e227c-db90-45e5-b9e5-8ee100ccc65c"]}                                        |                  0.8 |                 1 |              0.8 |            1 | ACTIVE          | 1768331273554 | 1768331273554 | 1768331273554 |
  (9 rows)
  ```

  ---

  ## Learning & Feedback

  ### st_learning_queue

  **Row Count**: 28

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

  **Sample Data** (showing 10 of 28 rows):

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
  subscriber_id |      topic      |  space_id  |  tenant_id  |       offset        |            updated_ts
  ---------------+-----------------+------------+-------------+---------------------+----------------------------------
  p03           | p02.hipp_events | space-home | tenant-test | 6974803523590336874 | 2026-01-13T19:07:54.065762+00:00
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

  **Row Count**: 784

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

  **Sample Data** (showing 10 of 784 rows):

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

  **Row Count**: 1

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
  device_id   |  tenant_id  |  space_id  | mls_group_id |          provisioned_ts          |                            hmac_secret
  ---------------+-------------+------------+--------------+----------------------------------+--------------------------------------------------------------------
  device-test-1 | tenant-test | space-home | mls-group-1  | 2026-01-13T19:07:26.075147+00:00 | \x94c59d43bbad6fea9d73c7e33a7846f0bb736a37039ec004d5dbb4eedc81c6f0
  (1 row)
  ```

  ---

  ### st_device_keys

  **Row Count**: 1

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
  device_id   | key_version |                 verify_key                  | key_state |          registered_ts           |           activated_ts           | rotated_ts | revoked_ts | grace_expires_ts | revocation_reason
  ---------------+-------------+---------------------------------------------+-----------+----------------------------------+----------------------------------+------------+------------+------------------+-------------------
  device-test-1 | 1           | QLBkMpHquaWgWRXgLTOKO2vwJbjsi5IofwoSqjnrV6Y | ACTIVE    | 2026-01-13T19:07:26.075147+00:00 | 2026-01-13T19:07:26.075147+00:00 |            |            |                  |
  (1 row)
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

  **Row Count**: 142

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

  **Sample Data** (showing 10 of 142 rows):

  ```
  id   | wal_pos |  tenant_id  |  space_id  | driver |            op_kind            |                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            payload                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |        fingerprint         | requeue_seq | retries | last_error | backoff_exp | status  | next_attempt_ts
  -------+---------+-------------+------------+--------+-------------------------------+----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+----------------------------+-------------+---------+------------+-------------+---------+-----------------
  22759 |       0 | tenant-test | space-home | p03    | p03.consolidation.complete.v1 | \x7b226379636c655f6964223a202230314b4557433351364d315153514b30535032564a3741304351222c202274656e616e745f6964223a202274656e616e742d74657374222c202273706163655f6964223a202273706163652d686f6d65222c202274696d657374616d705f6d73223a20313736383333313237333535352c202273756d6d617279223a207b22746f74616c5f6576656e7473223a2035362c2022636f6e736f6c6964617465645f636f756e74223a2035362c20226475706c69636174655f636f756e74223a20302c20227072756e65645f636f756e74223a20302c202270656e64696e675f7265766965775f636f756e74223a20302c2022616374696f6e5f627265616b646f776e223a207b22435245415445223a2035367d2c20226c617965725f77726974655f636f756e7473223a207b2273745f657069223a20382c202273745f6b675f646f6d223a2037332c202273745f6b675f6564676573223a2033382c202273745f70726f7370656374697665223a20392c202273745f73656d223a2036362c202273745f736f6369616c223a2032327d2c20226b675f656e746974795f636f756e74223a2037332c20226b675f656467655f636f756e74223a2033382c20226761705f636f756e74223a20302c2022696e73696768745f636f756e74223a20302c2022636f756e7465726661637475616c5f636f756e74223a20302c2022726f7574696e655f6f7074696d697a6174696f6e5f636f756e74223a20302c2022746f74616c5f777269746573223a203231362c20226379636c655f6475726174696f6e5f6d73223a20323137357d2c202270686173655f6475726174696f6e73223a207b7d2c2022746f74616c5f6576656e7473223a2035362c2022746f74616c5f777269746573223a203231362c2022636f6e736f6c6964617465645f636f756e74223a2035362c20226475706c69636174655f636f756e74223a20302c20227072756e65645f636f756e74223a20302c20226761705f636f756e74223a20307d | 01KEWC3SAKCDSM81ZJQA9XEQK5 |           0 |       0 |            |           0 | PENDING |
  22760 |       0 | tenant-test | space-home | p03    | p03.truth.created.v1          | \x7b226379636c655f6964223a202230314b4557433351364d315153514b30535032564a3741304351222c202274656e616e745f6964223a202274656e616e742d74657374222c202273706163655f6964223a202273706163652d686f6d65222c202274696d657374616d705f6d73223a20313736383333313237333535352c20226576656e745f6964223a202266623564616537342d396135392d346366612d623333312d323336383635316530333332222c2022636f6e74656e745f74797065223a2022657069736f646963222c2022696d706f7274616e63655f73636f7265223a20302e3232352c2022636c75737465725f6964223a20227765616b2d3136656438373665373037313461373138316133363266336461222c2022726561736f6e223a20224e6f2063616e6469646174657320666f756e6420696e207472757468206c61796572733b206372656174696e67206e6577207265636f7264227d                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           | 01KEWC3SAKWYW9CAAY678EHNSG |           0 |       0 |            |           0 | PENDING |
  22761 |       0 | tenant-test | space-home | p03    | p03.pattern.detected.v1       | \x7b226379636c655f6964223a202230314b4557433351364d315153514b30535032564a3741304351222c202274656e616e745f6964223a202274656e616e742d74657374222c202273706163655f6964223a202273706163652d686f6d65222c202274696d657374616d705f6d73223a20313736383333313237333535352c20226576656e745f6964223a202266623564616537342d396135392d346366612d623333312d323336383635316530333332222c20227061747465726e5f6964223a202273656d5f66623564616537342d396135392d346366612d623333312d323336383635316530333332222c2022636f6e74656e745f74797065223a2022657069736f646963222c2022636f6e666964656e6365223a20302e3534357d                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 | 01KEWC3SAKN018KBYFPAEY7W1W |           0 |       0 |            |           0 | PENDING |
  22762 |       0 | tenant-test | space-home | p03    | p03.truth.created.v1          | \x7b226379636c655f6964223a202230314b4557433351364d315153514b30535032564a3741304351222c202274656e616e745f6964223a202274656e616e742d74657374222c202273706163655f6964223a202273706163652d686f6d65222c202274696d657374616d705f6d73223a20313736383333313237333535352c20226576656e745f6964223a202234313237626563322d313030652d346465302d393761302d346666663166623835346531222c2022636f6e74656e745f74797065223a2022657069736f646963222c2022696d706f7274616e63655f73636f7265223a20302e3232352c2022636c75737465725f6964223a20227765616b2d3136656438373665373037313461373138316133363266336461222c2022726561736f6e223a20224e6f2063616e6469646174657320666f756e6420696e207472757468206c61796572733b206372656174696e67206e6577207265636f7264227d                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           | 01KEWC3SAKJTPA6QSVA19JWGHR |           0 |       0 |            |           0 | PENDING |
  22763 |       0 | tenant-test | space-home | p03    | p03.pattern.detected.v1       | \x7b226379636c655f6964223a202230314b4557433351364d315153514b30535032564a3741304351222c202274656e616e745f6964223a202274656e616e742d74657374222c202273706163655f6964223a202273706163652d686f6d65222c202274696d657374616d705f6d73223a20313736383333313237333535352c20226576656e745f6964223a202234313237626563322d313030652d346465302d393761302d346666663166623835346531222c20227061747465726e5f6964223a202273656d5f34313237626563322d313030652d346465302d393761302d346666663166623835346531222c2022636f6e74656e745f74797065223a2022657069736f646963222c2022636f6e666964656e6365223a20302e3534357d                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 | 01KEWC3SAK1CDK7GNKGW762XDP |           0 |       0 |            |           0 | PENDING |
  22764 |       0 | tenant-test | space-home | p03    | p03.truth.created.v1          | \x7b226379636c655f6964223a202230314b4557433351364d315153514b30535032564a3741304351222c202274656e616e745f6964223a202274656e616e742d74657374222c202273706163655f6964223a202273706163652d686f6d65222c202274696d657374616d705f6d73223a20313736383333313237333535352c20226576656e745f6964223a202266306433383132322d323566652d343563342d613132342d366436316430616335633138222c2022636f6e74656e745f74797065223a2022657069736f646963222c2022696d706f7274616e63655f73636f7265223a20302e3232352c2022636c75737465725f6964223a20227765616b2d3136656438373665373037313461373138316133363266336461222c2022726561736f6e223a20224e6f2063616e6469646174657320666f756e6420696e207472757468206c61796572733b206372656174696e67206e6577207265636f7264227d                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           | 01KEWC3SAK4GB7YKC9N1TQ582E |           0 |       0 |            |           0 | PENDING |
  22765 |       0 | tenant-test | space-home | p03    | p03.pattern.detected.v1       | \x7b226379636c655f6964223a202230314b4557433351364d315153514b30535032564a3741304351222c202274656e616e745f6964223a202274656e616e742d74657374222c202273706163655f6964223a202273706163652d686f6d65222c202274696d657374616d705f6d73223a20313736383333313237333535352c20226576656e745f6964223a202266306433383132322d323566652d343563342d613132342d366436316430616335633138222c20227061747465726e5f6964223a202273656d5f66306433383132322d323566652d343563342d613132342d366436316430616335633138222c2022636f6e74656e745f74797065223a2022657069736f646963222c2022636f6e666964656e6365223a20302e3534357d                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 | 01KEWC3SAKRPJXP2NNEH4Q6881 |           0 |       0 |            |           0 | PENDING |
  22766 |       0 | tenant-test | space-home | p03    | p03.truth.created.v1          | \x7b226379636c655f6964223a202230314b4557433351364d315153514b30535032564a3741304351222c202274656e616e745f6964223a202274656e616e742d74657374222c202273706163655f6964223a202273706163652d686f6d65222c202274696d657374616d705f6d73223a20313736383333313237333535352c20226576656e745f6964223a202266376565303265302d623231372d346433382d386233342d333264613965343963643538222c2022636f6e74656e745f74797065223a2022657069736f646963222c2022696d706f7274616e63655f73636f7265223a20302e3232352c2022636c75737465725f6964223a20227765616b2d3136656438373665373037313461373138316133363266336461222c2022726561736f6e223a20224e6f2063616e6469646174657320666f756e6420696e207472757468206c61796572733b206372656174696e67206e6577207265636f7264227d                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           | 01KEWC3SAKS8EV2MZA2C8JCMZ9 |           0 |       0 |            |           0 | PENDING |
  22767 |       0 | tenant-test | space-home | p03    | p03.pattern.detected.v1       | \x7b226379636c655f6964223a202230314b4557433351364d315153514b30535032564a3741304351222c202274656e616e745f6964223a202274656e616e742d74657374222c202273706163655f6964223a202273706163652d686f6d65222c202274696d657374616d705f6d73223a20313736383333313237333535352c20226576656e745f6964223a202266376565303265302d623231372d346433382d386233342d333264613965343963643538222c20227061747465726e5f6964223a202273656d5f66376565303265302d623231372d346433382d386233342d333264613965343963643538222c2022636f6e74656e745f74797065223a2022657069736f646963222c2022636f6e666964656e6365223a20302e3534357d                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 | 01KEWC3SAKCY3FCPZW1JXNADY8 |           0 |       0 |            |           0 | PENDING |
  22768 |       0 | tenant-test | space-home | p03    | p03.truth.created.v1          | \x7b226379636c655f6964223a202230314b4557433351364d315153514b30535032564a3741304351222c202274656e616e745f6964223a202274656e616e742d74657374222c202273706163655f6964223a202273706163652d686f6d65222c202274696d657374616d705f6d73223a20313736383333313237333535352c20226576656e745f6964223a202233363331373163382d333937662d343935302d386266642d393264396130643132313830222c2022636f6e74656e745f74797065223a2022657069736f646963222c2022696d706f7274616e63655f73636f7265223a20302e3132352c2022636c75737465725f6964223a20227765616b2d3139343034643161643133393434633662386238663931366232222c2022726561736f6e223a20224e6f2063616e6469646174657320666f756e6420696e207472757468206c61796572733b206372656174696e67206e6577207265636f7264227d                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           | 01KEWC3SAK8RVDTRFQDWD2H57D |           0 |       0 |            |           0 | PENDING |
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

  **Row Count**: 2,814

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

  **Sample Data** (showing 10 of 2,814 rows):

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

  **Row Count**: 2,814

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

  **Sample Data** (showing 10 of 2,814 rows):

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

  **Row Count**: 2,814

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

  **Sample Data** (showing 10 of 2,814 rows):

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
