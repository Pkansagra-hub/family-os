# st_hipp_events Column Reference

Authoritative working reference for the live `st_hipp_events` table as used by P03 discovery and phase hardening.

- Contract source: `k0/contracts/schemas/st_hipp_events_v2.columns.yaml`
- Live source: `information_schema.columns` from `k0-postgres` on 2026-03-06
- Purpose: make every available P02/P03 signal explicit before phase-by-phase consolidation work

## Notes

- This reference is grouped by the contract schema because that is the cleanest signal organization for P03 work.
- The live table currently has 150 columns. The YAML contract currently describes 144 of them.
- The six live-only columns are documented in a final drift section so P03 phase discovery can use them safely until the contract file is updated.

## identity_trace

| Column | Type | Nullable | Source | Description |
| ------ | ---- | -------- | ------ | ----------- |
| event_id | text | no | envelope.cognitive_trace_id | Primary key. Set to cognitive_trace_id per P02 dossier. |
| wal_pos | bigint | no | envelope.wal_pos | Write-ahead log position for ordering and replay. |
| cognitive_trace_id | text | no | envelope.cognitive_trace_id | Unique trace identifier from K1 envelope. |
| tenant_id | text | no | envelope.tenant_id | Multi-tenant isolation key. |
| space_id | text | no | envelope.space_id | Logical space within tenant. |
| effective_space_id | text | yes | M05.effective_space_id | Resolved space after M05 space resolution. |
| topic | text | no | envelope.topic | Bus topic that routed this envelope. |
| uow_id | text | yes | envelope.uow_id | Unit of work identifier for transactional grouping. |
| schema_version | text | no | envelope.schema_version | Envelope schema version for forward compatibility. |

## integrity_audit

| Column | Type | Nullable | Source | Description |
| ------ | ---- | -------- | ------ | ----------- |
| envelope_sha256 | text | no | envelope.envelope_sha256 | SHA-256 hash of the raw envelope for integrity verification. |
| sig_alg | text | no | envelope.sig_alg | Signature algorithm used (e.g., NONE, ED25519). |
| sig_kid | text | no | envelope.sig_kid | Key identifier for signature verification. |
| idem_key | text | no | envelope.idem_key | Idempotency key to prevent duplicate processing. |
| ingested_at | bigint | no | envelope.ingested_at | Unix epoch seconds when envelope was ingested by K0. |
| clock_skew_ms | integer | yes | envelope.clock_skew_ms | Detected clock skew between client and server in milliseconds. |

## policy_visibility

| Column | Type | Nullable | Source | Description |
| ------ | ---- | -------- | ------ | ----------- |
| policy_decision | text | no | envelope.policy_stamp.decision | K1 policy gate decision for this envelope. |
| policy_band | text | no | envelope.band | K1 envelope-level safety/policy band. |
| policy_version | text | no | envelope.policy_stamp.version | Version of policy rules that produced this decision. |
| obligations_json | text | yes | M03.obligations | Policy obligations attached to this event (JSON array). |
| visible_to_json | text | yes | M05.visible_to_json | List of actor IDs who can see this event. |
| visibility_scope | text | yes | M05.visibility_scope | Visibility scope classification from M05 space resolver. |
| owner_id | text | no | M05.owner_id | Primary owner of this event (actor who created it). |
| co_owners_json | text | yes | M05.co_owners_json | Co-owners with shared ownership rights (JSON array of actor IDs). |
| retention_policy_id | text | no | M11.retention_policy_id | Retention policy governing this event lifecycle. |
| retention_bucket | text | no | M11.retention_bucket | Retention classification for lifecycle management. |

## actor_device

| Column | Type | Nullable | Source | Description |
| ------ | ---- | -------- | ------ | ----------- |
| actor_id | text | no | envelope.actor | Identity of the actor who produced this event. |
| actor_role | text | yes | envelope.actor_role | Role of the actor producing this event. |
| device_id | text | no | envelope.device_id | Device identifier that generated this event. |
| device_kind | text | no | M09.device_kind | Device type classification (phone, tablet, desktop, etc.). |
| device_os | text | yes | M09.device_os | Device operating system (iOS, Android, etc.). |
| ingress_channel | text | yes | M10.ingress_topic | Ingress channel through which this event entered (write, import, etc.). |

## temporal

| Column | Type | Nullable | Source | Description |
| ------ | ---- | -------- | ------ | ----------- |
| event_time_utc | bigint | no | M08.event_time_utc | When the event occurred, Unix epoch seconds. |
| write_time_utc | bigint | no | M08.write_time_utc | When the event was written to K0, Unix epoch seconds. |
| write_lag_ms | integer | yes | M08.write_lag_ms | Delay between event_time_utc and write_time_utc in milliseconds. |
| local_date | text | yes | M08.local_date | Local date string (YYYY-MM-DD) in the actor timezone. |
| local_time | text | yes | M08.local_time | Local time string (HH:MM:SS) in the actor timezone. |
| day_of_week | text | yes | M08.day_of_week | Day of week name (Monday, Tuesday, etc.). |
| is_weekend | boolean | yes | M08.is_weekend | Whether event occurred on Saturday or Sunday. |
| time_of_day_bucket | text | yes | M08.time_of_day_bucket | Coarse time bucket (MORNING, AFTERNOON, EVENING, NIGHT). |
| circadian_slot | text | yes | M08.circadian_slot | Fine-grained circadian slot for pattern analysis. |
| is_backdated | boolean | yes | M08.is_backdated | Whether the event was backdated (event_time significantly before write_time). |
| created_at | bigint | no | system.time | Row creation timestamp, Unix epoch seconds. |
| temporal_mentioned_time | text | yes | body.temporal.mentioned_time | Raw temporal reference from user text ('yesterday evening', 'last Tuesday'). |
| temporal_resolved_epoch_ms | bigint | yes | body.temporal.resolved_epoch_ms | K1-resolved epoch milliseconds for mentioned_time. Used by M08 for backdating. |
| temporal_orientation | text | yes | body.temporal.orientation | Temporal orientation of the memory atom. |
| conversation_anchor_ms | bigint | yes | body.conversation_anchor_ms | K1 MW turn timestamp (ms). The actual moment the user chatted. Drives R2 episode formation when present. |
| temporal_source | text | yes | M08.normalize_timestamp.conv_source | Chain A provenance tag: conversation_anchor/event_time/envelope_ts/now. |
| temporal_links_json | text | yes | M08.parse_temporal_links | JSON array of TemporalLink objects {mentioned_time, resolved_epoch_ms, uncertainty_window_ms, link_type, confidence}. Max 5 per atom. |
| extraction_sequence | integer | yes | envelope.body.extraction_sequence | 0-based ordinal of this atom within the K1 turn extraction batch. |

## spatial_place

| Column | Type | Nullable | Source | Description |
| ------ | ---- | -------- | ------ | ----------- |
| location_name | text | yes | M15.location_name \| M12.location_name | Human-readable location name. |
| location_type | text | yes | M15.location_type \| M12.location_type | Location category (home, work, park, restaurant, etc.). |
| geohash_6 | text | yes | M15.geohash_6 \| M12.geohash_6 | 6-character geohash for spatial proximity queries (~1.2km precision). |
| place_id | text | yes | envelope.body.place_id | Stable place identity from K1 PlaceResolver. Pattern: place_<slug>. |
| location_hierarchy_json | text | yes | envelope.body.location_hierarchy | JSON array of spatial hierarchy levels, most specific to most general. Max 5 levels. |
| spatial_context_json | text | yes | envelope.body.transition_from_place + envelope.body.transition_mode | Bundled spatial transition context JSON: {transition_from_place, transition_mode}. |
| spatial_familiarity | text | yes | M15.spatial_familiarity | K0 familiarity band computed from historical visit count by (tenant_id, place_id). |
| geo_precision_external | text | yes | M12.geo_precision_external | Precision level of external geolocation source. |
| geo_masking_reason | text | yes | M12.geo_masking_reason | Reason geo data was masked or omitted (privacy, no_gps, etc.). |

## social_relationships

| Column | Type | Nullable | Source | Description |
| ------ | ---- | -------- | ------ | ----------- |
| participants_json | text | yes | body.participants \| M07.participants_json | List of participant identifiers in this event. |
| num_participants | integer | yes | M07.num_participants | Count of participants in this event. |
| has_partner_present | boolean | yes | M07.has_partner_present | Whether the user's partner/spouse was a participant. |
| has_parent_present | boolean | yes | M07.has_parent_present | Whether a parent was a participant. |
| is_solo_event | boolean | yes | M07.is_solo_event | Whether this event involved only the actor (no other participants). |
| participant_roles_json | text | yes | M07.participant_roles_json | Map of participant IDs to their roles in this event. |
| social_context | text | yes | M07.social_context | Social context classification (solo, family, friends, work, etc.). |
| social_intimacy | text | yes | M07.social_intimacy | Intimacy level of the social interaction (LOW, MED, HIGH). |
| participant_relationships_json | text | no | body.participant_relationships | Typed relationships from MW v2 ({person, relationship_type, confidence}). |

## semantic_activity

| Column | Type | Nullable | Source | Description |
| ------ | ---- | -------- | ------ | ----------- |
| text | text | yes | body.text | Raw text content of the memory atom. |
| text_normalized | text | yes | computed(body.text.lower().strip()) | Lowercased, stripped text for deduplication comparison. |
| char_count | integer | yes | computed(len(body.text)) | Character count of raw text. |
| token_count | integer | yes | computed(len(body.text.split())) | Whitespace-delimited token count of raw text. |
| language | text | yes | body.language | ISO 639-1 language code (en, es, etc.). |
| activity_type | text | yes | M10.activity_type | Legacy 7-type activity classification (meal, conversation, routine, milestone, social, work, unknown). |
| activity_category | text | yes | M10.activity_category | High-level content category (episodic, procedural, semantic). |
| is_meal | boolean | yes | body.is_meal | Whether this event involves a meal. |
| is_outing | boolean | yes | body.is_outing | Whether this event involves an outing/excursion. |
| ingress_source | text | yes | M10.ingress_source | Source application or interface (mobile_app, web, voice, import). |
| activity_type_ultrabert | text | yes | M10.activity_type_ultrabert | UltraBERT INGRESS head 12-type classification. Richer than legacy 7-type. |
| activity_type_confidence | double precision | yes | M10.activity_type_confidence | Confidence score for UltraBERT activity classification. |
| intent_ultrabert | text | yes | M10.intent_ultrabert | UltraBERT INTENT head 8-type classification. |
| intent_confidence | double precision | yes | M10.intent_confidence | Confidence score for UltraBERT intent classification. |

## hippocampus_pattern

| Column | Type | Nullable | Source | Description |
| ------ | ---- | -------- | ------ | ----------- |
| simhash_hex | text | no | M01.simhash_hex | SimHash fingerprint (hex) for near-duplicate detection. |
| minhash32 | text | no | M01.minhash32 | MinHash signature (JSON array of 32 ints) for LSH similarity. |
| novelty_score | double precision | yes | P03_CA3.novelty_score | Continuous novelty score [0.0-1.0] computed by P03 CA3 phase. |
| near_duplicates_json | text | yes | P03_CA3.near_duplicates | List of near-duplicate event IDs found by P03. |
| is_near_duplicate | boolean | yes | P03_CA3.is_near_duplicate | Whether this event was flagged as near-duplicate by P03. |
| episode_cluster_id | text | yes | P03_CA3.episode_cluster_id | Episode cluster assignment from P03 clustering. |
| cluster_confidence | double precision | yes | P03_CA3.cluster_confidence | Confidence of cluster assignment [0.0-1.0]. |
| clustering_version | text | yes | P03_CA3.clustering_version | Version of clustering algorithm that produced the assignment. |

## embeddings_kg

| Column | Type | Nullable | Source | Description |
| ------ | ---- | -------- | ------ | ----------- |
| embedding_id | text | no | M22.embedding_id \| M02.embedding_id | Unique identifier for the vector embedding (ADR-K003). |
| embedding_status | text | no | computed(M22.embedding != null -> READY else PENDING) | Embedding generation status. READY when M22 returns embedding. |
| entities_json | text | yes | M02.entities_json | Resolved/processed entities in KG format (JSON array). |
| kg_triples_json | text | yes | M02.kg_triples_json | Knowledge graph triples extracted from text (JSON array). |
| ner_entities_json | text | yes | M02.ner_entities_json | Raw UltraBERT 3-head NER output ({ner_family: [], ner_general: []}). |
| temporal_json | text | yes | M02.temporal_json | Raw temporal expressions from UltraBERT temporal head ({temporal: []}). |
| intent_category | text | yes | M02.intent_category | User intent from UltraBERT intent head (log_memory, share_news, etc.). |
| ingress_category | text | yes | M02.ingress_category | UltraBERT ingress routing category (CELEBRATION, MEAL, ROUTINE, etc.). |
| ultrabert_version | text | yes | M02.ultrabert_version | UltraBERT model version used for NER extraction. |
| extracted_relations_json | text | yes | M02.extracted_relations_json | Relationship types from UltraBERT relations head (['parent_of'], etc.). |
| safety_familyos_band | text | yes | M02.safety_familyos_band | UltraBERT 4-band safety classification. Distinct from K1 policy_band. |
| safety_familyos_subcategory | text | yes | M02.safety_familyos_subcategory | Detailed safety subcategory (none, stress, self_harm_ideation, etc.). |
| effective_safety_band | text | yes | computed(arbitrate(policy_band, safety_familyos_band)) | Arbitrated safety band. Most restrictive of K1 policy_band vs UltraBERT safety_familyos_band. |
| nli_label | text | yes | M02.nli_label | Natural language inference result from UltraBERT NLI head. |
| nli_confidence | double precision | yes | M02.nli_confidence | Confidence score for NLI classification. |
| sentiment_confidence | double precision | yes | M02.sentiment_confidence | Confidence score for UltraBERT sentiment analysis. |

## affect_salience

| Column | Type | Nullable | Source | Description |
| ------ | ---- | -------- | ------ | ----------- |
| sentiment_score | double precision | yes | M04.valence | Sentiment score mapped from affect valence. -1.0 (negative) to 1.0 (positive). |
| sentiment_label | text | yes | computed(valence >= 0.6 -> positive, <= 0.4 -> negative, else neutral) | Categorical sentiment derived from valence score. |
| dominant_emotions_json | text | yes | M04.dominant_emotions | Dominant emotions detected (JSON array of emotion strings). |
| affect_valence | double precision | yes | M04.valence | Valence dimension of affect (pleasantness). Trust-then-fill: MW v2 -> UltraBERT -> VADER. |
| affect_arousal | double precision | yes | M04.arousal | Arousal dimension of affect (activation). Trust-then-fill: MW v2 -> UltraBERT -> VADER. |
| affect_band | text | yes | M04.affect_band | Clinical affect safety band. Overridden to RED/AMBER if clinical risk detected. |
| salience_score | double precision | no | M06.salience_score | Importance score [0.0-1.0]. Boosted for clinical safety content. |
| salience_reasons_json | text | yes | M06.salience_reasons | Reasons for salience score (JSON array of reason strings). |
| salience_band | text | yes | M06.salience_band | Categorical salience band derived from score. |
| affect_dominance | double precision | yes | body.affect.dominance | 3rd VAD dimension (dominance/control). Trust-then-fill: MW v2 -> UltraBERT -> null. |
| entity_salience_json | text | no | body.entity_salience | Per-entity salience map from MW v2 ({entity_name: score, ...}). |

## consolidation_lifecycle

| Column | Type | Nullable | Source | Description |
| ------ | ---- | -------- | ------ | ----------- |
| consolidation_status | text | yes | P03.R0_batch_select | Consolidation pipeline processing status. |
| consolidation_cycle_id | text | yes | P03.R0_batch_select | ID of the consolidation cycle processing this event. |
| consolidated_at | bigint | yes | P03.R8_finalize | Timestamp when consolidation completed, Unix epoch seconds. |
| reconciliation_decision | text | yes | P03.R3_reconcile | High-level reconciliation decision from P03 R3. |
| truth_match_id | text | yes | P03.R3_reconcile | ID of matched truth record in reconciliation. |
| truth_match_similarity | double precision | yes | P03.R3_reconcile | Cosine similarity score of truth match. |
| archival_status | text | yes | P03.lifecycle | Archival status for filtering archived events from consolidation. |
| reconciliation_action | text | yes | P03.R3_R4_reconcile | Specific action type from R3/R4 reconciliation. |
| best_match_id | text | yes | P03.R3_reconcile | ID of best-matched truth record (episodic/semantic). |
| best_match_layer | text | yes | P03.R3_reconcile | Which truth table the best match resides in. |
| similarity_score | double precision | yes | P03.R3_reconcile | Cosine similarity to best match [0.0-1.0]. |
| confidence | double precision | yes | P03.R3_reconcile | Overall decision confidence [0.0-1.0]. |
| reconciliation_reason | text | yes | P03.R3_reconcile | Human-readable explanation of reconciliation decision. |
| consolidated_at_ms | bigint | yes | P03.R8_finalize | Timestamp when consolidation completed, milliseconds precision. |

## metadata_versioning

| Column | Type | Nullable | Source | Description |
| ------ | ---- | -------- | ------ | ----------- |
| hippocampus_api_version | text | yes | system.api_version | Hippocampus API version that processed this event. |
| space_resolver_version | text | yes | M05.version | Space resolver module version. |
| schema_uri | text | yes | system.schema_uri | URI reference to the schema version for this row. |
| updated_at | bigint | no | system.time | Row last-updated timestamp, Unix epoch seconds. |
| k1_signal_version | text | no | body.k1_signal_version | MW version that produced this atom. '2.0' for M3 trust-then-fill atoms. |

## narrative_context

| Column | Type | Nullable | Source | Description |
| ------ | ---- | -------- | ------ | ----------- |
| narrative_thread_id | text | yes | body.narrative.thread_id | Conversation thread UUID from MW v2 narrative_active section. |
| narrative_arc_position | text | yes | body.narrative.arc_position | Position within narrative arc from MW v2. |
| narrative_is_goal_event | boolean | no | body.narrative.is_goal_event | Whether this atom represents a goal event in its narrative thread. |

## cognitive_dimensions

| Column | Type | Nullable | Source | Description |
| ------ | ---- | -------- | ------ | ----------- |
| intent_type | text | yes | body.intent_type | K1 primary intent classification (distinct from UltraBERT intent_ultrabert). |
| goal_context | text | yes | body.goal_context | Goal/intention context from MW v2. |
| source_type | text | yes | body.source_type | Provenance of the information in this atom. |
| novelty | text | yes | body.novelty | Categorical novelty from MW (distinct from novelty_score FLOAT set by P03 CA3). |
| elaboration_depth | text | yes | body.elaboration_depth | How deeply the user engaged with this topic. |
| identity_domains_json | text | no | body.identity_domains | Identity domains this atom touches (['parent', 'professional', 'health_self']). |

## live_only_drift

Columns present in the live table but not yet described in `st_hipp_events_v2.columns.yaml`.

| Column | Type | Nullable | Source | Description |
| ------ | ---- | -------- | ------ | ----------- |
| merge_cascade_id | character varying | yes | P03 merge cascade tracking | Cascade merge batch identifier used by P03 merge and undo workflows to track rows affected by a merge cascade. |
| surprise_level | real | yes | envelope.body.surprise_level | MW cognitive surprise or unexpectedness score in [0.0, 1.0]. |
| identity_relevance | real | yes | envelope.body.identity_relevance | How strongly this event relates to the user's self-identity in [0.0, 1.0]. |
| source_reliability | real | yes | envelope.body.source_reliability | Trustworthiness of the source signal in [0.0, 1.0]; defaults high unless MW lowers it. |
| memory_tier | character varying | yes | envelope.body.memory_tier | Memory-tier classification carried from MW signals, currently using routine/notable/significant/landmark semantics on st_hipp_events. |
| temporal_anchor_json | text | yes | envelope.body.temporal_anchor | Resolved temporal anchor object from MW v2a, stored as JSON for downstream episode-boundary logic. |
