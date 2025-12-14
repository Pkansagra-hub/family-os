# P03 Memory Layers - Complete Schema Reference

## Overview
P03 consolidation pipeline outputs to **8 memory layers**, each storing different types of consolidated memories transformed from hippocampal events (st_hipp_events).

---

## 1. **st_epi** — Episodic Memory Layer
**Purpose**: Stores discrete episodes/events with rich context
**Phase**: R7.1 (Memory Writers)
**Brain Analog**: Hippocampus → Neocortex transfer

### Columns

| Column | Type | Purpose | Notes |
|--------|------|---------|-------|
| **Identity** | | | |
| `episode_id` | TEXT PRIMARY KEY | Unique episode identifier | |
| `event_id` | TEXT NOT NULL | Reference to source hippocampal event | FK → st_hipp_events |
| `tenant_id` | TEXT NOT NULL | Multi-tenant isolation | |
| `space_id` | TEXT NOT NULL | User/workspace isolation | |
| `actor_id` | TEXT NOT NULL | Who experienced the event | |
| **Temporal** | | | |
| `event_time_utc` | TEXT NOT NULL | When the event occurred | ISO 8601 |
| `first_observed_at` | TEXT NOT NULL | When first recorded | |
| `last_observed_at` | TEXT NOT NULL | When last seen (if recurring) | |
| `observation_count` | INTEGER | How many times observed | Default: 1 |
| `temporal_bucket` | TEXT | Time bucket (hour, day, week) | For grouping |
| `is_weekend` | INTEGER | Boolean flag | Default: 0 |
| `recency_weight` | REAL | Recency decay factor | Default: 1.0 |
| **Content** | | | |
| `text` | TEXT NOT NULL | Episode description/narrative | |
| `participants_json` | TEXT | JSON array of people involved | |
| `location_name` | TEXT | Where the event occurred | |
| `activity_type` | TEXT | Type of activity (work, social, etc.) | |
| **Affect** | | | |
| `sentiment_score` | REAL | Emotional valence (-1 to +1) | From P02 sentiment |
| `salience_score` | REAL | Importance/salience measure | From R1 scoring |
| **Quality** | | | |
| `confidence_score` | REAL | Confidence in episode reconstruction | |
| `source_count` | INTEGER | Number of sources merged | Default: 1 |
| `source_quality` | TEXT | Quality level of source | Default: 'raw' |
| `ambiguity_score` | REAL | Uncertainty in details | Default: 0.0 |
| **Fusion** | | | |
| `modalities_json` | TEXT | Multimodal sources (text, image, audio) | JSON array |
| `fusion_method` | TEXT | How sources were combined | |
| `fusion_confidence` | REAL | Confidence in fusion | |
| `source_events_json` | TEXT | Original event IDs that formed this | JSON array |
| **Promotion** | | | |
| `promoted_to_semantic_id` | TEXT | Link to semantic if generalized | FK → st_sem |
| `promoted_to_routine_id` | TEXT | Link to routine if procedural | FK → st_procedural |
| **Lifecycle** | | | |
| `decay_factor` | REAL | Memory decay/forgetting rate | Default: 1.0 |
| `archival_status` | TEXT | ACTIVE, ARCHIVED, DELETED | Default: 'ACTIVE' |
| `access_count` | INTEGER | How many times accessed | Default: 0 |
| **Versioning** | | | |
| `version` | INTEGER | Version number for updates | Default: 1 |
| `is_canonical` | INTEGER | Whether this is the canonical version | Default: 1 |
| `supersedes_episode_id` | TEXT | ID of episode this replaces | |
| **Timestamps** | | | |
| `created_at` | TEXT NOT NULL | When inserted into st_epi | |
| `updated_at` | TEXT NOT NULL | Last update time | |

### Indexes
```sql
CREATE INDEX idx_epi_tenant_time ON st_epi(tenant_id, event_time_utc);
CREATE INDEX idx_epi_space_actor ON st_epi(space_id, actor_id);
CREATE INDEX idx_epi_activity ON st_epi(activity_type, event_time_utc);
CREATE INDEX idx_epi_salience ON st_epi(salience_score DESC);
CREATE INDEX idx_epi_canonical ON st_epi(is_canonical) WHERE is_canonical = 1;
CREATE INDEX idx_epi_archival ON st_epi(archival_status);
```

---

## 2. **st_sem** — Semantic Pattern Layer
**Purpose**: Stores recurring patterns, themes, and generalized concepts
**Phase**: R7.2 (Memory Writers)
**Brain Analog**: Cortical consolidation of repeated patterns

### Columns

| Column | Type | Purpose | Notes |
|--------|------|---------|-------|
| **Identity** | | | |
| `semantic_id` | TEXT PRIMARY KEY | Unique pattern identifier | |
| `tenant_id` | TEXT NOT NULL | Multi-tenant isolation | |
| `space_id` | TEXT NOT NULL | User/workspace isolation | |
| `actor_id` | TEXT NOT NULL | Who established the pattern | |
| **Pattern Definition** | | | |
| `pattern_type` | TEXT NOT NULL | routine, preference, theme, relationship | |
| `pattern_name` | TEXT NOT NULL | Human-readable name | e.g., "Morning Coffee Ritual" |
| `pattern_description` | TEXT | Detailed description | |
| `common_elements_json` | TEXT NOT NULL | Invariant elements across instances | JSON array |
| **Temporal** | | | |
| `temporal_context` | TEXT | When pattern occurs (morning, weekday) | |
| `first_observed_at` | TEXT NOT NULL | When pattern first detected | |
| `last_observed_at` | TEXT NOT NULL | When last observed | |
| `observation_count` | INTEGER | Total instances seen | Default: 1 |
| `temporal_bucket` | TEXT | Time bucket (hour, day, week) | |
| `is_weekend` | INTEGER | Boolean: weekend-specific? | Default: 0 |
| `recency_weight` | REAL | Recency factor | Default: 1.0 |
| **Recurrence** | | | |
| `pattern_frequency` | TEXT | daily, weekly, monthly, irregular | |
| `recurrence_interval_days` | REAL | Days between occurrences | e.g., 7.0 for weekly |
| `pattern_last_occurrence` | TEXT | Timestamp of last occurrence | |
| `next_predicted_time` | TEXT | When pattern expected next | |
| **Quality** | | | |
| `frequency_score` | REAL | How consistent/frequent | 0.0-1.0 |
| `confidence_score` | REAL NOT NULL | Confidence in pattern existence | 0.0-1.0 |
| `source_count` | INTEGER | Episodes that define this | Default: 1 |
| `source_quality` | TEXT | Quality of source data | Default: 'derived' |
| `ambiguity_score` | REAL | Fuzziness of pattern boundaries | Default: 0.0 |
| **Source Tracking** | | | |
| `modalities_json` | TEXT | Modalities present in pattern | JSON array |
| `source_episodes_json` | TEXT NOT NULL | Episode IDs forming this pattern | JSON array |
| `invariants_json` | TEXT | Elements that must be present | JSON object |
| `variations_json` | TEXT | Acceptable variations | JSON object |
| **Lifecycle** | | | |
| `decay_factor` | REAL | Forgetting rate | Default: 1.0 |
| `archival_status` | TEXT | ACTIVE, ARCHIVED, DELETED | Default: 'ACTIVE' |
| **Versioning** | | | |
| `version` | INTEGER | Version number | Default: 1 |
| `is_canonical` | INTEGER | Canonical version? | Default: 1 |
| `valid_from` | TEXT NOT NULL | When pattern started | |
| `valid_to` | TEXT | When pattern ended (NULL = active) | |
| `supersedes_semantic_id` | TEXT | Pattern this replaces | |
| **Timestamps** | | | |
| `created_at` | TEXT NOT NULL | When inserted | |
| `updated_at` | TEXT NOT NULL | Last update time | |

### Indexes
```sql
CREATE INDEX idx_sem_tenant ON st_sem(tenant_id, space_id);
CREATE INDEX idx_sem_actor ON st_sem(actor_id);
CREATE INDEX idx_sem_pattern_type ON st_sem(pattern_type);
CREATE INDEX idx_sem_confidence ON st_sem(confidence_score DESC);
CREATE INDEX idx_sem_frequency ON st_sem(pattern_frequency);
CREATE INDEX idx_sem_valid ON st_sem(valid_from, valid_to);
CREATE INDEX idx_sem_canonical ON st_sem(is_canonical) WHERE is_canonical = 1;
```

---

## 3. **st_procedural** — Routines/Skills Layer
**Purpose**: Stores learned procedures, habits, and skill sequences
**Phase**: R7.3 (Memory Writers)
**Brain Analog**: Cerebellar/Basal Ganglia procedural memory

### Columns

| Column | Type | Purpose | Notes |
|--------|------|---------|-------|
| **Identity** | | | |
| `routine_id` | TEXT PRIMARY KEY | Unique routine identifier | |
| `tenant_id` | TEXT NOT NULL | Multi-tenant isolation | |
| `space_id` | TEXT NOT NULL | User/workspace isolation | |
| `actor_id` | TEXT NOT NULL | Who performs routine | |
| **Routine Definition** | | | |
| `routine_category` | TEXT NOT NULL | morning, evening, work, exercise, meal | |
| `routine_name` | TEXT NOT NULL | e.g., "Morning Shower" | |
| `description` | TEXT | Full description | |
| `trigger_conditions_json` | TEXT | What initiates the routine | JSON object |
| `action_sequence_json` | TEXT NOT NULL | Step-by-step actions | JSON array of steps |
| **Temporal** | | | |
| `temporal_context` | TEXT | When routine occurs | |
| `first_observed_at` | TEXT NOT NULL | When first learned | |
| `last_observed_at` | TEXT NOT NULL | When last executed | |
| `observation_count` | INTEGER | How many times performed | Default: 1 |
| `execution_count` | INTEGER | Successful executions | Default: 0 |
| **Performance** | | | |
| `completion_rate` | REAL | % times successfully completed | 0.0-1.0 |
| `avg_duration_minutes` | REAL | Average time to complete | |
| `frequency_score` | REAL | How regularly performed | |
| `consistency_score` | REAL | How consistent execution | 0.0-1.0 |
| `streak_count` | INTEGER | Consecutive successful executions | Default: 0 |
| **Quality** | | | |
| `confidence_score` | REAL NOT NULL | Confidence in routine knowledge | 0.0-1.0 |
| `skill_level` | TEXT | novice, intermediate, expert | Default: 'novice' |
| `optimization_score` | REAL | How optimized/efficient | |
| `bottleneck_analysis_json` | TEXT | Steps that slow execution | JSON object |
| **Source Tracking** | | | |
| `source_episodes_json` | TEXT | Episodes forming this routine | JSON array |
| **Lifecycle** | | | |
| `decay_factor` | REAL | Skill decay rate | Default: 1.0 |
| `archival_status` | TEXT | ACTIVE, ARCHIVED, DELETED | Default: 'ACTIVE' |
| **Versioning** | | | |
| `version` | INTEGER | Version number | Default: 1 |
| `is_canonical` | INTEGER | Canonical version? | Default: 1 |
| `valid_from` | TEXT NOT NULL | When routine became valid | |
| `valid_to` | TEXT | When routine ended (NULL = active) | |
| **Timestamps** | | | |
| `created_at` | TEXT NOT NULL | When inserted | |
| `updated_at` | TEXT NOT NULL | Last update time | |

### Indexes
```sql
CREATE INDEX idx_proc_tenant ON st_procedural(tenant_id, space_id);
CREATE INDEX idx_proc_actor ON st_procedural(actor_id);
CREATE INDEX idx_proc_category ON st_procedural(routine_category);
CREATE INDEX idx_proc_confidence ON st_procedural(confidence_score DESC);
CREATE INDEX idx_proc_canonical ON st_procedural(is_canonical) WHERE is_canonical = 1;
```

---

## 4. **st_social** — Social Relationships Layer
**Purpose**: Stores relationship models and social connections
**Phase**: R7.4 (Memory Writers)
**Brain Analog**: Social brain networks (fusiform, STS, MPFC)

### Columns

| Column | Type | Purpose | Notes |
|--------|------|---------|-------|
| **Identity** | | | |
| `relationship_id` | TEXT PRIMARY KEY | Unique relationship identifier | |
| `tenant_id` | TEXT NOT NULL | Multi-tenant isolation | |
| `space_id` | TEXT NOT NULL | User/workspace isolation | |
| `actor_id` | TEXT NOT NULL | Primary person | |
| `related_person_id` | TEXT NOT NULL | Related person | |
| **Relationship Definition** | | | |
| `relationship_type` | TEXT NOT NULL | family, friend, colleague, acquaintance | |
| `relationship_label` | TEXT | Custom label | e.g., "Mom", "Boss" |
| **Interaction Metrics** | | | |
| `interaction_count` | INTEGER | Total interactions | Default: 0 |
| `first_interaction_at` | TEXT NOT NULL | When relationship started | |
| `last_interaction_at` | TEXT NOT NULL | Most recent interaction | |
| `interaction_frequency_days` | REAL | Average days between interactions | |
| **Communication** | | | |
| `communication_channels_json` | TEXT | Channels used (phone, email, in-person) | JSON array |
| `dominant_channel` | TEXT | Primary channel | |
| **Strength Metrics** | | | |
| `relationship_strength` | REAL | Overall closeness/importance | 0.0-1.0 |
| `sentiment_avg` | REAL | Average sentiment in interactions | -1.0 to +1.0 |
| `sentiment_trend` | TEXT | improving, stable, declining | |
| `trust_score` | REAL | Trust level | 0.0-1.0 |
| `reciprocity_score` | REAL | Reciprocal nature of relationship | 0.0-1.0 |
| **Shared Context** | | | |
| `shared_activities_json` | TEXT | Common activities | JSON array |
| `shared_locations_json` | TEXT | Places they're together | JSON array |
| **Source Tracking** | | | |
| `source_episodes_json` | TEXT | Episodic memories involved | JSON array |
| `source_kg_edges_json` | TEXT | Knowledge graph edges | JSON array |
| **Lifecycle** | | | |
| `decay_factor` | REAL | Relationship decay rate | Default: 1.0 |
| `archival_status` | TEXT | ACTIVE, ARCHIVED, DELETED | Default: 'ACTIVE' |
| **Versioning** | | | |
| `version` | INTEGER | Version number | Default: 1 |
| `is_canonical` | INTEGER | Canonical version? | Default: 1 |
| `valid_from` | TEXT NOT NULL | When relationship became known | |
| `valid_to` | TEXT | When relationship ended | |
| **Timestamps** | | | |
| `created_at` | TEXT NOT NULL | When inserted | |
| `updated_at` | TEXT NOT NULL | Last update time | |
| **Constraints** | | | |
| UNIQUE | (tenant_id, space_id, actor_id, related_person_id, is_canonical) | | |

### Indexes
```sql
CREATE INDEX idx_social_tenant ON st_social(tenant_id, space_id);
CREATE INDEX idx_social_actor ON st_social(actor_id);
CREATE INDEX idx_social_related ON st_social(related_person_id);
CREATE INDEX idx_social_type ON st_social(relationship_type);
CREATE INDEX idx_social_strength ON st_social(relationship_strength DESC);
```

---

## 5. **st_prospective** — Intentions/Goals Layer
**Purpose**: Stores goals, predictions, reminders, and future-oriented thoughts
**Phase**: R7.5 (Memory Writers)
**Brain Analog**: Prospective memory (prefrontal cortex, medial parietal)

### Columns

| Column | Type | Purpose | Notes |
|--------|------|---------|-------|
| **Identity** | | | |
| `prospective_id` | TEXT PRIMARY KEY | Unique intention identifier | |
| `tenant_id` | TEXT NOT NULL | Multi-tenant isolation | |
| `space_id` | TEXT NOT NULL | User/workspace isolation | |
| `actor_id` | TEXT NOT NULL | Who has the intention | |
| **Intention Definition** | | | |
| `intention_type` | TEXT NOT NULL | reminder, goal, prediction, scenario, insight | |
| `intention_text` | TEXT NOT NULL | Description of intention | |
| **Trigger Conditions** | | | |
| `trigger_conditions_json` | TEXT | Conditions to trigger (context-dependent) | JSON object |
| `trigger_time_utc` | TEXT | Absolute time trigger | ISO 8601 |
| `trigger_location` | TEXT | Location trigger | |
| `trigger_context` | TEXT | Context trigger | |
| **Priority & Confidence** | | | |
| `priority` | REAL | Priority level | 0.0-1.0 |
| `confidence` | REAL | Confidence in the intention | 0.0-1.0 |
| **Predictions** | | | |
| `predicted_outcome` | TEXT | Expected outcome | From R5.2 TPN-MCTS |
| `predicted_outcome_confidence` | REAL | Confidence in prediction | 0.0-1.0 |
| `alternative_scenarios_json` | TEXT | Alternative possible outcomes | JSON array |
| **Insights** | | | |
| `insight_category` | TEXT | opportunity, warning, optimization | From R5.4 BGT-SM |
| `surprise_score` | REAL | Unexpectedness of insight | 0.0-1.0 |
| **Source Tracking** | | | |
| `source_episodes_json` | TEXT | Episodic sources | JSON array |
| `source_semantics_json` | TEXT | Semantic pattern sources | JSON array |
| `created_from_pipeline` | TEXT | Which pipeline created (R5 for insights) | |
| **Status** | | | |
| `status` | TEXT | PENDING, TRIGGERED, COMPLETED, EXPIRED | Default: 'PENDING' |
| `triggered_at` | TEXT | When intention triggered | |
| `completed_at` | TEXT | When intention fulfilled | |
| **Versioning** | | | |
| `version` | INTEGER | Version number | Default: 1 |
| `is_canonical` | INTEGER | Canonical version? | Default: 1 |
| **Timestamps** | | | |
| `created_at` | TEXT NOT NULL | When inserted | |
| `updated_at` | TEXT NOT NULL | Last update time | |

### Indexes
```sql
CREATE INDEX idx_prosp_tenant ON st_prospective(tenant_id, space_id);
CREATE INDEX idx_prosp_actor ON st_prospective(actor_id);
CREATE INDEX idx_prosp_type ON st_prospective(intention_type);
CREATE INDEX idx_prosp_trigger ON st_prospective(trigger_time_utc);
CREATE INDEX idx_prosp_status ON st_prospective(status);
CREATE INDEX idx_prosp_priority ON st_prospective(priority DESC);
```

---

## 6. **st_kg_dom** — Knowledge Graph Nodes
**Purpose**: Entity nodes in the knowledge graph (people, places, concepts, events)
**Phase**: R7.6 (Memory Writers) / R4 (KG Construction)
**Brain Analog**: Conceptual/semantic entity representations

### Columns

| Column | Type | Purpose | Notes |
|--------|------|---------|-------|
| **Identity** | | | |
| `node_id` | TEXT PRIMARY KEY | Unique node identifier | |
| `tenant_id` | TEXT NOT NULL | Multi-tenant isolation | |
| `space_id` | TEXT NOT NULL | User/workspace isolation | |
| **Entity Definition** | | | |
| `entity_type` | TEXT NOT NULL | Person, Place, Organization, Activity, Topic, Event | |
| `entity_name` | TEXT NOT NULL | Primary name | e.g., "Alice" |
| `entity_aliases_json` | TEXT | Alternative names | JSON array |
| `entity_description` | TEXT | Detailed description | |
| **Observation Metrics** | | | |
| `first_observed_at` | TEXT NOT NULL | When first mentioned | |
| `last_observed_at` | TEXT NOT NULL | When last mentioned | |
| `observation_count` | INTEGER | How many times observed | Default: 1 |
| **Quality** | | | |
| `confidence_score` | REAL | Confidence in entity identification | 0.0-1.0 |
| **Properties** | | | |
| `node_properties_json` | TEXT | Entity attributes | JSON object |
| **Temporal Validity** | | | |
| `valid_from` | TEXT NOT NULL | When entity became relevant | |
| `valid_to` | TEXT | When entity ended (NULL = current) | |
| **Source Tracking** | | | |
| `source_episodes_json` | TEXT | Episodes mentioning this entity | JSON array |
| **Lifecycle** | | | |
| `decay_factor` | REAL | Entity decay/relevance fade | Default: 1.0 |
| `archival_status` | TEXT | ACTIVE, ARCHIVED, DELETED | Default: 'ACTIVE' |
| **Versioning** | | | |
| `version` | INTEGER | Version number | Default: 1 |
| `is_canonical` | INTEGER | Canonical version? | Default: 1 |
| `canonical_node_id` | TEXT | If not canonical, points to canonical | FK → st_kg_dom |
| `supersedes_node_id` | TEXT | Node this replaces | FK → st_kg_dom |
| **Timestamps** | | | |
| `created_at` | TEXT NOT NULL | When inserted | |
| `updated_at` | TEXT NOT NULL | Last update time | |

### Indexes
```sql
CREATE INDEX idx_kg_dom_tenant ON st_kg_dom(tenant_id, space_id);
CREATE INDEX idx_kg_dom_entity_type ON st_kg_dom(entity_type);
CREATE INDEX idx_kg_dom_entity_name ON st_kg_dom(entity_name);
CREATE INDEX idx_kg_dom_canonical ON st_kg_dom(is_canonical, canonical_node_id);
CREATE INDEX idx_kg_dom_valid ON st_kg_dom(valid_from, valid_to);
CREATE INDEX idx_kg_dom_observation ON st_kg_dom(observation_count DESC);
```

---

## 7. **st_kg_edges** — Knowledge Graph Edges/Relationships
**Purpose**: Relationships between KG nodes
**Phase**: R7.6 (Memory Writers) / R4 (KG Construction)
**Brain Analog**: Associative connections in semantic network

### Columns

| Column | Type | Purpose | Notes |
|--------|------|---------|-------|
| **Identity** | | | |
| `edge_id` | TEXT PRIMARY KEY | Unique edge identifier | |
| `tenant_id` | TEXT NOT NULL | Multi-tenant isolation | |
| `space_id` | TEXT NOT NULL | User/workspace isolation | |
| **Relationship Definition** | | | |
| `source_node_id` | TEXT NOT NULL | From node | FK → st_kg_dom |
| `target_node_id` | TEXT NOT NULL | To node | FK → st_kg_dom |
| `edge_type` | TEXT NOT NULL | co_occurs_with, causes, enables, conflicts_with, part_of | |
| `edge_label` | TEXT | Custom label | e.g., "married_to" |
| **Strength Metrics** | | | |
| `relationship_strength` | REAL | Weight of relationship | Default: 1.0 |
| `observation_count` | INTEGER | Times relationship observed | Default: 1 |
| **Quality** | | | |
| `confidence_score` | REAL | Confidence in relationship | 0.0-1.0 |
| **Temporal Validity** | | | |
| `first_observed_at` | TEXT NOT NULL | When relationship first seen | |
| `last_observed_at` | TEXT NOT NULL | When relationship last seen | |
| `valid_from` | TEXT NOT NULL | When relationship became valid | |
| `valid_to` | TEXT | When relationship ended | |
| **Causal Properties** | | | |
| `is_causal` | INTEGER | Whether relationship is causal | Default: 0 |
| `causal_confidence` | REAL | Confidence in causality | 0.0-1.0 |
| `temporal_lag_seconds` | REAL | Time lag between cause/effect | |
| **Properties** | | | |
| `edge_properties_json` | TEXT | Additional attributes | JSON object |
| **Source Tracking** | | | |
| `source_episodes_json` | TEXT | Episodes supporting this relationship | JSON array |
| **Lifecycle** | | | |
| `decay_factor` | REAL | Relationship decay rate | Default: 1.0 |
| `archival_status` | TEXT | ACTIVE, ARCHIVED, DELETED | Default: 'ACTIVE' |
| **Versioning** | | | |
| `version` | INTEGER | Version number | Default: 1 |
| `is_canonical` | INTEGER | Canonical version? | Default: 1 |
| **Timestamps** | | | |
| `created_at` | TEXT NOT NULL | When inserted | |
| `updated_at` | TEXT NOT NULL | Last update time | |

### Indexes
```sql
CREATE INDEX idx_kg_edges_tenant ON st_kg_edges(tenant_id, space_id);
CREATE INDEX idx_kg_edges_source ON st_kg_edges(source_node_id);
CREATE INDEX idx_kg_edges_target ON st_kg_edges(target_node_id);
CREATE INDEX idx_kg_edges_type ON st_kg_edges(edge_type);
CREATE INDEX idx_kg_edges_strength ON st_kg_edges(relationship_strength DESC);
CREATE INDEX idx_kg_edges_causal ON st_kg_edges(is_causal) WHERE is_causal = 1;
CREATE INDEX idx_kg_edges_valid ON st_kg_edges(valid_from, valid_to);
```

---

## 8. **st_vec** — Vector Embeddings
**Purpose**: Dense vector embeddings for semantic search and similarity
**Phase**: R7.7 (Memory Writers) / P08 (Embedding Pipeline)
**Brain Analog**: Distributed neural representations

### Columns

| Column | Type | Purpose | Notes |
|--------|------|---------|-------|
| **Identity** | | | |
| `embedding_id` | TEXT PRIMARY KEY | Unique embedding identifier | |
| `tenant_id` | TEXT NOT NULL | Multi-tenant isolation | |
| `space_id` | TEXT NOT NULL | User/workspace isolation | |
| **Source Reference** | | | |
| `source_layer` | TEXT NOT NULL | st_epi, st_sem, st_kg_dom, st_prospective | |
| `source_id` | TEXT NOT NULL | ID in source table | |
| **Embedding Definition** | | | |
| `embedding_type` | TEXT | text, image, audio | Default: 'text' |
| `text_to_embed` | TEXT NOT NULL | Text representation to embed | |
| **Vector Data** | | | |
| `vector_dimensions` | INTEGER | Embedding vector size | Default: 768 |
| `embedding_model` | TEXT | Model used (e.g., 'mpnet-base-v2') | Default: 'mpnet-base-v2' |
| `vector_data` | BLOB | Actual embedding vector (768-dim) | NULL until P08 fills |
| **Status** | | | |
| `embedding_status` | TEXT | PENDING, READY, FAILED | Default: 'PENDING' |
| **Timestamps** | | | |
| `created_at` | TEXT NOT NULL | When placeholder created | |
| `updated_at` | TEXT NOT NULL | When embedding completed | |

### Indexes
```sql
CREATE INDEX idx_vec_tenant ON st_vec(tenant_id, space_id);
CREATE INDEX idx_vec_source ON st_vec(source_layer, source_id);
CREATE INDEX idx_vec_status ON st_vec(embedding_status);
CREATE INDEX idx_vec_model ON st_vec(embedding_model);
```

### Related: st_embedding_queue
P03 creates **placeholders** in st_vec, then P08 reads from st_embedding_queue:

| Column | Type | Purpose |
|--------|------|---------|
| `job_id` | TEXT PRIMARY KEY | Job identifier |
| `embedding_id` | TEXT NOT NULL | FK → st_vec |
| `text_to_embed` | TEXT NOT NULL | Text to embed |
| `embedding_model` | TEXT NOT NULL | Model to use |
| `priority` | TEXT | HIGH, MEDIUM, LOW |
| `status` | TEXT | PENDING, PROCESSING, COMPLETE, FAILED |
| `retries` | INTEGER | Retry count |
| `created_at` | TEXT | When queued |
| `started_at` | TEXT | When processing started |
| `completed_at` | TEXT | When completed |
| `error_message` | TEXT | Error if failed |

---

## Summary Table: Memory Layer Characteristics

| Layer | Table | Brain Region | Purpose | # Columns | Key Features |
|-------|-------|--------------|---------|-----------|--------------|
| **1** | `st_epi` | Hippocampus→Neocortex | Discrete episodes with context | 50+ | Multimodal fusion, decay, versioning |
| **2** | `st_sem` | Cortex | Recurring patterns/themes | 40+ | Frequency tracking, recurrence prediction |
| **3** | `st_procedural` | Basal Ganglia/Cerebellum | Learned procedures/skills | 40+ | Execution tracking, skill level, optimization |
| **4** | `st_social` | STS/MPFC/Fusiform | Social relationships | 35+ | Interaction metrics, sentiment trends |
| **5** | `st_prospective` | Prefrontal/Medial Parietal | Goals, predictions, reminders | 30+ | Trigger conditions, outcome predictions |
| **6** | `st_kg_dom` | Semantic network | Knowledge entities | 25+ | Entity types, aliases, confidence scoring |
| **7** | `st_kg_edges` | Semantic network | Entity relationships | 30+ | Causal links, temporal lags, edge types |
| **8** | `st_vec` | Distributed cortex | Vector embeddings | 12+ | 768-dim embeddings, async P08 coordination |

---

## Data Flow: st_hipp_events → 8 Memory Layers

```
st_hipp_events (from P02)
    │
    ├─→ R0: Trigger
    ├─→ R1: Importance Scoring
    ├─→ R2: Episodic Clustering → st_epi + st_sem
    ├─→ R3: Dedup/Novelty → update st_epi
    ├─→ R4: KG Construction → st_kg_dom + st_kg_edges
    ├─→ R5: Dream Phase → st_prospective (optional)
    ├─→ R6: Update st_hipp_events with consolidation results
    ├─→ R7: Write to 8 layers
    │   ├─→ R7.1: st_epi
    │   ├─→ R7.2: st_sem
    │   ├─→ R7.3: st_procedural
    │   ├─→ R7.4: st_social
    │   ├─→ R7.5: st_prospective
    │   ├─→ R7.6a: st_kg_dom
    │   ├─→ R7.6b: st_kg_edges
    │   └─→ R7.7: st_vec (placeholders) + st_embedding_queue
    └─→ R8: Emit events
```

---

## Total Column Count by Layer

| Layer | Columns |
|-------|---------|
| st_epi | ~50 |
| st_sem | ~40 |
| st_procedural | ~40 |
| st_social | ~35 |
| st_prospective | ~30 |
| st_kg_dom | ~25 |
| st_kg_edges | ~30 |
| st_vec | ~12 |
| **TOTAL** | **~262 columns** |

---

## Query Examples

### Find all active episodes for a person on a date
```sql
SELECT episode_id, text, salience_score
FROM st_epi
WHERE actor_id = ? AND date(event_time_utc) = ? AND archival_status = 'ACTIVE'
ORDER BY salience_score DESC;
```

### Find all routines and their consistency
```sql
SELECT routine_name, consistency_score, last_observed_at, execution_count
FROM st_procedural
WHERE actor_id = ? AND archival_status = 'ACTIVE'
ORDER BY consistency_score DESC;
```

### Find all relationships with a person
```sql
SELECT r.related_person_id, k.entity_name, r.relationship_type, r.relationship_strength
FROM st_social r
JOIN st_kg_dom k ON r.related_person_id = k.node_id
WHERE r.actor_id = ? AND r.archival_status = 'ACTIVE';
```

### Semantic search with embeddings
```sql
SELECT source_layer, source_id, distance
FROM st_vec v
WHERE tenant_id = ? AND embedding_status = 'READY'
ORDER BY vec_distance(v.vector_data, ?)
LIMIT 10;
```

---

**Document Version**: 1.0
**Last Updated**: 2025-12-14
**Related**: [P03_implementation_plan_v2.md](../P03_implementation_plan_v2.md)
