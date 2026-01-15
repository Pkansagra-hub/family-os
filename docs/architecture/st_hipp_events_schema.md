# st_hipp_events Schema Reference

**Generated**: 2026-01-08 from live Docker database (k0_kernel)

## Overview

`st_hipp_events` is the primary event storage table written by P02 (Ingress Pipeline) and consumed by P03 (Consolidation Pipeline). It contains **107 columns** covering:

- Event identification & metadata
- Policy & security
- Temporal profiling
- Social/participant context
- Content & text
- UltraBERT NLP outputs
- Consolidation tracking

---

## Column Inventory (107 Total)

### 1. Identification & Metadata (13 columns)

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `event_id` | text | NOT NULL | - | Primary key (UUID) |
| `wal_pos` | bigint | NOT NULL | - | Write-ahead log position (unique) |
| `cognitive_trace_id` | text | NOT NULL | - | Trace ID for observability |
| `tenant_id` | text | NOT NULL | - | Multi-tenant isolation |
| `space_id` | text | NOT NULL | - | Memory space |
| `effective_space_id` | text | nullable | - | Resolved space |
| `topic` | text | NOT NULL | - | Event topic/channel |
| `uow_id` | text | nullable | - | Unit of work ID |
| `schema_version` | text | NOT NULL | '1.0.0' | Schema version |
| `envelope_sha256` | text | NOT NULL | - | Envelope hash |
| `sig_alg` | text | NOT NULL | - | Signature algorithm |
| `sig_kid` | text | NOT NULL | - | Signature key ID |
| `idem_key` | text | NOT NULL | - | Idempotency key |

### 2. Policy & Security (12 columns)

| Column | Type | Nullable | Default | Check Constraint |
|--------|------|----------|---------|------------------|
| `ingested_at` | bigint | NOT NULL | - | |
| `clock_skew_ms` | integer | nullable | - | |
| `policy_decision` | text | NOT NULL | - | `['ALLOW', 'DENY']` |
| `policy_band` | text | NOT NULL | - | `['GREEN', 'AMBER', 'RED']` |
| `policy_version` | text | NOT NULL | - | |
| `obligations_json` | text | nullable | - | |
| `visible_to_json` | text | nullable | - | |
| `visibility_scope` | text | nullable | - | `['OWNER_ONLY', 'SPACE_DEFAULT', 'HOUSEHOLD_ALL', 'CUSTOM_SUBSET', 'EXTERNAL_SHARE']` |
| `owner_id` | text | NOT NULL | - | |
| `co_owners_json` | text | nullable | - | |
| `retention_policy_id` | text | NOT NULL | - | |
| `retention_bucket` | text | NOT NULL | - | `['STANDARD', 'SENSITIVE', 'EPHEMERAL']` |

### 3. Actor & Device (7 columns)

| Column | Type | Nullable | Default | Check Constraint |
|--------|------|----------|---------|------------------|
| `actor_id` | text | NOT NULL | - | |
| `actor_role` | text | nullable | - | `['SELF', 'AGENT', 'SYSTEM', 'DELEGATE']` |
| `device_id` | text | NOT NULL | - | |
| `device_kind` | text | NOT NULL | - | |
| `device_os` | text | nullable | - | |
| `ingress_channel` | text | nullable | - | |

### 4. Temporal Profile (11 columns)

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `event_time_utc` | bigint | NOT NULL | - | Event occurrence time (ms) |
| `write_time_utc` | bigint | NOT NULL | - | Write time (ms) |
| `write_lag_ms` | integer | nullable | - | Lag between event and write |
| `local_date` | text | nullable | - | e.g., "2026-01-08" |
| `local_time` | text | nullable | - | e.g., "14:30" |
| `day_of_week` | text | nullable | - | e.g., "Monday" |
| `is_weekend` | boolean | nullable | - | |
| `time_of_day_bucket` | text | nullable | - | e.g., "morning", "afternoon" |
| `circadian_slot` | text | nullable | - | Circadian rhythm slot |
| `is_backdated` | boolean | nullable | - | Was event backdated? |
| `created_at` | bigint | NOT NULL | - | Row creation time |

### 5. Location & Geo (5 columns)

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `location_name` | text | nullable | - | e.g., "home", "Olive Garden" |
| `location_type` | text | nullable | - | e.g., "HOME", "RESTAURANT" |
| `geohash_6` | text | nullable | - | 6-char geohash |
| `geo_precision_external` | text | nullable | - | |
| `geo_masking_reason` | text | nullable | - | |

### 6. Social Context (9 columns) ⭐ KEY FOR st_social

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `participants_json` | text | nullable | - | **JSON array of person IDs** |
| `num_participants` | integer | nullable | - | Count of participants |
| `has_partner_present` | boolean | nullable | - | |
| `has_parent_present` | boolean | nullable | - | |
| `is_solo_event` | boolean | nullable | - | |
| `participant_roles_json` | text | nullable | - | Role mappings |
| `social_context` | text | nullable | - | e.g., "nuclear_family", "solo", "work" |
| `social_intimacy` | text | nullable | - | "HIGH", "LOW" |

### 7. Content & Text (6 columns)

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `text` | text | nullable | - | Raw event text |
| `text_normalized` | text | nullable | - | Normalized text |
| `char_count` | integer | nullable | - | |
| `token_count` | integer | nullable | - | |
| `language` | text | nullable | - | |

### 8. Activity Classification (5 columns)

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `activity_type` | text | nullable | - | e.g., "MEAL", "OUTING" |
| `activity_category` | text | nullable | - | Higher-level category |
| `is_meal` | boolean | nullable | - | |
| `is_outing` | boolean | nullable | - | |
| `ingress_source` | text | nullable | - | |

### 9. Deduplication (5 columns)

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `simhash_hex` | text | NOT NULL | - | 64-bit SimHash |
| `minhash32` | text | NOT NULL | - | MinHash signature |
| `novelty_score` | float | nullable | - | |
| `near_duplicates_json` | text | nullable | - | |
| `is_near_duplicate` | boolean | nullable | - | |

### 10. Clustering (3 columns)

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `episode_cluster_id` | text | nullable | - | Episode cluster ID |
| `cluster_confidence` | float | nullable | - | |
| `clustering_version` | text | nullable | - | |

### 11. Embedding (2 columns)

| Column | Type | Nullable | Default | Check Constraint |
|--------|------|----------|---------|------------------|
| `embedding_id` | text | NOT NULL | - | Unique, FK to st_vec |
| `embedding_status` | text | NOT NULL | 'PENDING' | `['PENDING', 'IN_PROGRESS', 'READY', 'FAILED']` |

### 12. UltraBERT NLP Output (13 columns) ⭐ KEY FOR P03

| Column | Type | Nullable | Default | Description | Populated? |
|--------|------|----------|---------|-------------|------------|
| `entities_json` | text | nullable | - | **Resolved entities** (KG format) | ✅ 79/79 |
| `kg_triples_json` | text | nullable | - | **KG triples** from event | ✅ 79/79 |
| `ner_entities_json` | text | nullable | - | Raw UltraBERT NER output | ✅ 77/79 |
| `temporal_json` | text | nullable | - | Temporal expressions | ✅ 77/79 |
| `intent_category` | text | nullable | - | User intent | ✅ 72/79 |
| `ingress_category` | text | nullable | - | Ingress routing | partial |
| `ultrabert_version` | text | nullable | - | Model version | partial |
| `sentiment_score` | float | nullable | - | Sentiment [-1, 1] | ✅ |
| `sentiment_label` | text | nullable | - | positive/neutral/negative | ✅ |
| `dominant_emotions_json` | text | nullable | - | **Emotion array** | ✅ |
| `affect_valence` | float | nullable | - | Valence score | ✅ |
| `affect_arousal` | float | nullable | - | Arousal score | ✅ |
| `affect_band` | text | nullable | - | `['GREEN', 'AMBER', 'RED']` | ✅ |

### 13. Salience (3 columns)

| Column | Type | Nullable | Default | Check Constraint |
|--------|------|----------|---------|------------------|
| `salience_score` | float | NOT NULL | 0 | |
| `salience_reasons_json` | text | nullable | - | |
| `salience_band` | text | nullable | - | `['HIGH', 'MED', 'LOW']` |

### 14. P03 Consolidation Tracking (12 columns)

| Column | Type | Nullable | Default | Check Constraint |
|--------|------|----------|---------|------------------|
| `consolidation_status` | text | nullable | - | `['PENDING', 'IN_PROGRESS', 'CONSOLIDATED', 'DUPLICATE', 'PRUNED', 'PENDING_REVIEW']` |
| `consolidation_cycle_id` | text | nullable | - | |
| `consolidated_at` | bigint | nullable | - | |
| `consolidated_at_ms` | bigint | nullable | - | |
| `reconciliation_decision` | text | nullable | - | |
| `reconciliation_action` | text | nullable | - | |
| `reconciliation_reason` | text | nullable | - | |
| `truth_match_id` | text | nullable | - | |
| `truth_match_similarity` | float | nullable | - | |
| `best_match_id` | text | nullable | - | |
| `best_match_layer` | text | nullable | - | |
| `similarity_score` | float | nullable | - | |
| `confidence` | float | nullable | - | |

### 15. Maintenance (4 columns)

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `hippocampus_api_version` | text | nullable | - | |
| `space_resolver_version` | text | nullable | - | |
| `schema_uri` | text | nullable | - | |
| `updated_at` | bigint | NOT NULL | - | |
| `merge_cascade_id` | varchar(36) | nullable | - | R4 entity merge tracking |
| `archival_status` | text | nullable | - | |

---

## Sample Records

### Record 1: Nuclear Family Dinner

```
text: "Had dinner with mom and dad at Olive Garden to celebrate Emma's birthday. We had a great time!"

participants_json: ["person_mom","person_dad","person_emma"]
num_participants: 3
social_context: "nuclear_family"
social_intimacy: "HIGH"

entities_json: ["person_mom", "person_dad", "person_emma", "org_olive_garden"]
kg_triples_json: [...]

sentiment_label: "positive"
dominant_emotions_json: ["joy","love","togetherness"]

intent_category: NULL (older record)
ingress_category: NULL
```

### Record 2: Breakfast with Family

```
text: "Breakfast with family: pancakes and fruit, everyone at the table."

participants_json: ["person_mom","person_dad"]
num_participants: 2
social_context: "nuclear_family"
social_intimacy: "HIGH"

entities_json: ["person_family"]
kg_triples_json: [
  ["actor-test-123", "had_meal_at", "home_kitchen"],
  ["actor-test-123", "had_meal_with", "person_mom"],
  ["actor-test-123", "had_meal_with", "person_dad"],
  ["{event_id}", "occurred_at", "home_kitchen"],
  ["{event_id}", "mentions", "person_family"]
]

sentiment_label: "positive"
dominant_emotions_json: ["optimism","contentment"]

intent_category: "log_memory"
ingress_category: "CELEBRATION"
```

### Record 3: Solo Morning Routine

```
text: "Morning log: Woke up at 7:10, made coffee, feeling focused."

participants_json: []
num_participants: 1
social_context: "solo"
social_intimacy: "LOW"

entities_json: []
ner_entities_json: {"ner_family": [], "ner_general": []}
temporal_json: {"temporal": []}

sentiment_label: "positive"
dominant_emotions_json: ["optimism","contentment"]

intent_category: "log_memory"
ingress_category: "DIARY"
```

---

## Key Observations

### ✅ What P02 ALREADY Provides

1. **Social Context (9 columns)**
   - `participants_json` - WHO is present (person IDs)
   - `social_context` - nuclear_family, solo, work
   - `social_intimacy` - HIGH/LOW

2. **UltraBERT NLP (13 columns)**
   - `ner_entities_json` - Raw NER (ner_family + ner_general)
   - `entities_json` - Resolved entities
   - `kg_triples_json` - Knowledge graph triples
   - `dominant_emotions_json` - Emotion array
   - `sentiment_score` / `sentiment_label`
   - `intent_category` - log_memory, share_news, etc.
   - `ingress_category` - DIARY, CELEBRATION, WORK

3. **Salience & Affect**
   - `salience_score`, `salience_band`
   - `affect_valence`, `affect_arousal`, `affect_band`

### ❌ What's MISSING (UltraBERT provides but not stored)

| UltraBERT Capability | Column Exists? | Example Output |
|---------------------|----------------|----------------|
| `relations` | ❌ **NO** | `['parent_of']`, `['spouse_of']` |
| `safety` band | ❌ NO (only affect_band) | `GREEN`, `AMBER`, `CRISIS` |
| `nli` | ❌ NO | `entailment`, `neutral`, `contradiction` |

### 📊 Column Population Stats (79 records)

| Column | Populated | Notes |
|--------|-----------|-------|
| entities_json | 79/79 (100%) | ✅ Always populated |
| kg_triples_json | 79/79 (100%) | ✅ Always populated |
| ner_entities_json | 77/79 (97%) | ✅ Most populated |
| temporal_json | 77/79 (97%) | ✅ Most populated |
| intent_category | 72/79 (91%) | Some older records NULL |
| participants_json | varies | Depends on event type |
| social_context | varies | Depends on event type |

---

## Indexes

| Index | Columns | Condition |
|-------|---------|-----------|
| `st_hipp_events_pkey` | event_id | PRIMARY KEY |
| `st_hipp_events_wal_pos_key` | wal_pos | UNIQUE |
| `st_hipp_events_embedding_id_key` | embedding_id | UNIQUE |
| `idx_hipp_events_consolidation` | (consolidation_status, event_time_utc) | WHERE status IS NULL OR 'PENDING' |
| `idx_hipp_events_space_time` | (space_id, event_time_utc DESC) | |
| `idx_hipp_events_tenant_time` | (tenant_id, event_time_utc DESC) | |
| `idx_hipp_events_ner_pending` | (event_time_utc DESC) | WHERE ner_entities_json IS NULL |
| `idx_hipp_events_cluster_id` | (episode_cluster_id) | WHERE NOT NULL |
| `idx_hipp_events_best_match_id` | (best_match_id) | WHERE NOT NULL |
| `idx_hipp_events_simhash` | (simhash_hex) | |
| `idx_hipp_events_band_time` | (policy_band, event_time_utc DESC) | |

---

## Foreign Key Relationships

| Table | FK Column | On Delete |
|-------|-----------|-----------|
| st_vec | event_id | CASCADE |
| st_embedding_queue | event_id, embedding_id | - |
| st_anchor_observations | event_id | SET NULL |
| st_learning_queue | related_event_id | SET NULL |

---

## Recommendations for P03 Enhancement

### For st_social Population

**Option A: Use existing columns (Immediate)**

- `participants_json` → actor_a_id, actor_b_id pairs
- `social_context` → relationship_type inference (nuclear_family → family relations)
- `social_intimacy` → intimacy_level
- `sentiment_score` → avg_sentiment
- `dominant_emotions_json` → emotional context

**Option B: Add UltraBERT `relations` column (Recommended)**

- Add `extracted_relations_json` column to st_hipp_events
- P02 writes UltraBERT `relations` output: `['parent_of']`, `['spouse_of']`
- R4 reads directly without inference

### For st_procedural Population

**Available signals:**

- `activity_type` - MEAL, OUTING, etc.
- `time_of_day_bucket` - morning, afternoon, evening
- `day_of_week` - routine detection
- `circadian_slot` - sleep/wake patterns
- `intent_category` - log_memory patterns
- `is_meal` / `is_outing` - activity flags

---

## Version History

| Date | Change |
|------|--------|
| 2026-01-08 | Initial extraction from Docker (107 columns) |
