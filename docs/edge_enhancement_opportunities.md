# Knowledge Graph Edge Enhancement Opportunities

## Current Signals from st_hipp_events Used for Edges

The R0 batch selector extracts these signals from `st_hipp_events`:

**Currently Used by Edge Enrichers:**

- `activity_type_ultrabert` → `ingress_category` (UltraBERT 12-class: DIARY/TASK/HEALTH/etc.)
- `sentiment_score`, `sentiment_label`
- `affect_valence`, `affect_arousal`
- `salience_score`, `salience_band`, `novelty_score`
- `location_name`, `location_type`, `geohash_6`
- `social_context`, `social_intimacy`, `is_solo_event`, `num_participants`
- `time_of_day_bucket`, `circadian_slot`, `is_weekend`, `day_of_week`
- `ingress_channel`, `ingress_source`, `device_kind`

**Available but Not Yet Used for Edges:**

- `dominant_emotions_json` (detailed emotion breakdown)
- `extracted_relations_json` (UltraBERT relationship types)
- `temporal_json` (temporal expressions)
- `ner_entities_json` (named entities)
- `intent_ultrabert`, `intent_confidence` (8-type intent classification)
- `activity_type_confidence` (confidence in ingress classification)

## Current Edge Enrichers

1. **ContextualEdgeEnricher**: Uses weighted Jaccard similarity on shared context features (location, social, time, sentiment, ingress_category)

2. **SemanticSimilarityEnricher**: Cosine similarity on entity embeddings

3. **TemporalProximityEnricher**: Co-occurrence within time windows

4. **BayesianCausalEnricher**: Temporal precedence patterns for causal inference

5. **TransitiveClosureEnricher**: 2-hop path inference

6. **EdgeWeightNormalizer**: Prevents hub dominance

## How Edge Enrichers Work in This Codebase

**Pattern:**

1. **Enricher Class**: Async class with `enrich()` method taking `(entity_contexts, existing_edges)` → returns `(List[KGEdge], List[KGEdgeUpdate])`
2. **Config Class**: Dataclass with settings (enabled, thresholds, relation_type, etc.)
3. **Integration**: Added to `EdgeEnrichmentConfig` in `r4_config.py`, instantiated in `R4KGConsolidator._initialize_components()`, called in enrichment phase
4. **Data Sources**: Uses `ObservationContext` objects (populated from `st_hipp_events` via R0 batch selector)
5. **Testing**: Unit tests in `tests/k0/modules/consolidation/algorithms/edge_enrichers/`

**Data Flow:**

```text
st_hipp_events → R0 Batch Selector → P03EventState → ObservationContext.from_event() → Entity Contexts → Enrichers → KG Edges
```

## Opportunities for More Robust Edges

### 1. **Emotion-Based Edges**

**Implementation:**

- **File**: `k0/modules/consolidation/algorithms/edge_enrichers/emotion_similarity.py`
- **Config**: `EmotionSimilarityConfig` in `r4_config.py`
- **Algorithm**: Parse `dominant_emotions_json` from `ObservationContext`, compute emotion vector similarity using cosine distance
- **Features**: Compare emotion distributions (joy, sadness, anger, fear, etc.) between entities
- **Weighting**: Use `affect_arousal` as intensity multiplier
- **Relation Type**: `"EMOTIONALLY_RELATED"`
- **Threshold**: 0.6 similarity for meaningful emotional connections

### 2. **Intent-Based Edges**

**Implementation:**

- **File**: `k0/modules/consolidation/algorithms/edge_enrichers/intent_similarity.py`
- **Config**: `IntentSimilarityConfig` in `r4_config.py`
- **Algorithm**: Use `intent_ultrabert` (8-type: log_memory/query_memory/set_reminder/express_feeling/seek_advice/share_news/reflect/other)
- **Features**: Create complementary intent mappings (seek_advice ↔ express_feeling, set_reminder ↔ log_memory)
- **Weighting**: Use `intent_confidence` as edge weight modifier
- **Relation Type**: `"INTENT_RELATED"`
- **Logic**: Connect entities with complementary intents rather than similar ones

### 3. **Entity Co-Mention Edges**

**Implementation:**

- **File**: `k0/modules/consolidation/algorithms/edge_enrichers/named_entity.py`
- **Config**: `NamedEntityConfig` in `r4_config.py`
- **Algorithm**: Parse `ner_entities_json` from `ObservationContext`, find shared named entities
- **Features**: Group by entity type (PERSON, ORG, GPE, etc.), weight by frequency and type importance
- **Weighting**: Higher weight for PERSON/ORG co-mentions than generic locations
- **Relation Type**: `"CO_MENTIONED"`
- **Threshold**: Require 2+ co-mentions for edge creation

### 4. **Relationship Type Edges**

**Implementation:**

- **File**: `k0/modules/consolidation/algorithms/edge_enrichers/relationship_type.py`
- **Config**: `RelationshipTypeConfig` in `r4_config.py`
- **Algorithm**: Parse `extracted_relations_json` from `ObservationContext` for UltraBERT relationship types
- **Features**: Create directed edges for relationships (parent_of, spouse_of, friend_of, colleague_of, etc.)
- **Directionality**: Use relationship semantics to determine edge direction
- **Relation Type**: Use the specific relationship type (e.g., `"PARENT_OF"`, `"FRIEND_OF"`)
- **Confidence**: Use extraction confidence scores

### 5. **Enhanced Contextual Features**

**Implementation:**

- **Modify**: `ContextualEdgeEnricher._build_feature_map()` in `contextual.py`
- **Add Features**:
  - `device_kind`: `"device_kind:{ctx.device_kind}"` (phone/desktop/tablet/speaker)
  - `social_intimacy`: `"social_intimacy:{ctx.social_intimacy}"` (HIGH/LOW ratings)
  - `circadian_slot`: `"circadian_slot:{ctx.circadian_slot}"` (WAKE/ACTIVE/WIND_DOWN/SLEEP)
  - `geohash_6`: `"geohash:{ctx.geohash_6[:4]}"` (coarse geospatial proximity)
- **Update Config**: Add weights to `ContextualEdgeConfig.context_weights`
- **Benefits**: More granular context matching beyond location/social/time

### 6. **Multi-Modal Fusion Edges**

**Implementation:**

- **File**: `k0/modules/consolidation/algorithms/edge_enrichers/multi_modal.py`
- **Config**: `MultiModalSimilarityConfig` in `r4_config.py`
- **Algorithm**: Combine multiple similarity scores (text embeddings + emotion vectors + temporal patterns)
- **Fusion**: Weighted average with confidence scores from each modality
- **Features**: Normalize and combine heterogeneous similarity measures
- **Relation Type**: `"MULTI_MODAL_RELATED"`
- **Robustness**: More reliable than single-signal approaches

### 7. **Confidence-Weighted Fusion**

**Implementation:**

- **Modify**: `fusion.py` functions and `EdgeFusionConfig`
- **Algorithm**: Track historical accuracy of each enricher algorithm
- **Adaptive Weights**: Adjust algorithm weights based on validation feedback
- **Confidence Intervals**: Use statistical confidence bounds instead of point estimates
- **Algorithm Selection**: Route entities to best-performing enrichers by type/category

### 8. **Domain-Specific Edges**

**Implementation:**

- **Files**: Multiple enrichers (health_edges.py, work_edges.py, social_edges.py)
- **Routing**: Use `activity_type_ultrabert` to route to domain-specific enrichers
- **Examples**:
  - **Health**: Connect symptoms → treatments → appointments
  - **Work**: Connect projects → meetings → deadlines
  - **Social**: Connect people → relationships → gatherings
- **Config**: `DomainSpecificConfig` with per-domain settings

### 9. **Temporal Pattern Edges**

**Implementation:**

- **File**: `k0/modules/consolidation/algorithms/edge_enrichers/temporal_pattern.py`
- **Config**: `TemporalPatternConfig` in `r4_config.py`
- **Algorithm**: Detect recurring patterns using `temporal_json` expressions
- **Features**: Identify weekly meetings, daily routines, seasonal patterns
- **Pattern Matching**: Use sequence alignment on temporal trajectories
- **Relation Type**: `"TEMPORALLY_PATTERNED"`
- **Threshold**: Require 3+ occurrences of same pattern

### 10. **Uncertainty-Aware Edges**

**Implementation:**

- **Modify**: `KGEdge` and `KGEdgeUpdate` classes to include uncertainty metadata
- **Edge Types**:
  - `"POSSIBLY_RELATED"` for low-confidence connections
  - `"CONTEXTUALLY_SIMILAR"` vs `"SEMANTICALLY_SIMILAR"`
- **Metadata**: Add uncertainty bounds, confidence intervals, alternative hypotheses
- **Query Interface**: Allow filtering by confidence levels in downstream processing

## Implementation Priority

1. **High Priority** (Immediate impact):
   - Enhanced Contextual Features (expand existing enricher)
   - Emotion-Based Edges (new enricher)
   - Intent-Based Edges (new enricher)

2. **Medium Priority** (Semantic depth):
   - Entity Co-Mention Edges
   - Relationship Type Edges
   - Domain-Specific Edges

3. **Lower Priority** (Advanced features):
   - Multi-Modal Fusion Edges
   - Temporal Pattern Edges
   - Confidence-Weighted Fusion
   - Uncertainty-Aware Edges

## Next Steps

These enhancements would create much more robust and meaningful knowledge graph edges by leveraging the rich signal set already available in `st_hipp_events`, moving beyond simple co-occurrence to semantic, emotional, and relational connections.

## Required st_hipp_events Columns & Data Formats

Based on the complete schema analysis, here are the specific columns needed for each edge enhancement, with their data types and expected formats:

### Core Columns (Used by Multiple Enrichers)

- `event_id`: `text` - UUID string (e.g., `"d899512a-62eb-462a-aa24-15a5f9a8f98d"`)
- `activity_type_ultrabert`: `text` - UltraBERT 12-class: `"DIARY"`, `"GRATITUDE"`, `"HEALTH"`, `"WORK"`, `"TASK"`, `"CELEBRATION"`, `"PLANNING"`, `"MEMORY"`, `"RELATIONSHIP"`, `"FINANCE"`, `"META"`
- `activity_type_confidence`: `double precision` - 0.0-1.0 confidence score (e.g., `0.8`)
- `ingress_category`: `text` - Same 12-class as activity_type_ultrabert
- `location_name`: `text` - String location (e.g., `"Home"`, `"Home Office"`)
- `social_context`: `text` - `"solo"`, `"family"`, `"friends"`, `"work"`, `"public"`
- `time_of_day_bucket`: `text` - `"morning"`, `"afternoon"`, `"evening"`, `"night"`
- `day_of_week`: `text` - `"Monday"`, `"Tuesday"`, etc.
- `is_weekend`: `boolean` - `true`/`false`

### Enhanced Contextual Features

- `device_kind`: `text` - `"phone"`, `"desktop"`, `"tablet"`, `"speaker"`
- `social_intimacy`: `text` - `"HIGH"`, `"MED"`, `"LOW"`
- `circadian_slot`: `text` - `"WAKE"`, `"ACTIVE"`, `"WIND_DOWN"`, `"SLEEP"` (currently `null`)
- `geohash_6`: `text` - 6-character geohash string (currently `null`)

### Emotion-Based Edges

- `dominant_emotions_json`: `text` - JSON array of emotion strings (e.g., `["relief","contentment"]`, `["gratitude","relief","contentment"]`)
- `affect_valence`: `double precision` - 0.0-1.0 emotional valence (e.g., `0.5`, `0.9`)
- `affect_arousal`: `double precision` - 0.0-1.0 emotional arousal (e.g., `0.2`, `0.3`)

### Intent-Based Edges

- `intent_ultrabert`: `text` - 8-type classification: `"share_news"`, `"log_memory"`, `"express_feeling"`, `"seek_advice"`, `"query_memory"`, `"set_reminder"`, `"reflect"`, `"other"`
- `intent_confidence`: `double precision` - 0.0-1.0 confidence score (e.g., `0.3433`, `0.5182`)

### Entity Co-Mention Edges

- `ner_entities_json`: `text` - JSON object with family/general NER results (e.g., `{"ner_family": {"entities": []}, "ner_general": {"entities": []}}`)

### Relationship Type Edges

- `extracted_relations_json`: `text` - JSON array of extracted relationships (currently `[]`)

### Temporal Pattern Edges

- `temporal_json`: `text` - JSON object with temporal expressions (currently `{"entities": []}`)
- `local_date`: `text` - ISO date string (e.g., `"2026-01-24"`)
- `local_time`: `text` - Time string (e.g., `"22:47:09"`)

### Multi-Modal Fusion Edges

- `sentiment_score`: `double precision` - 0.0-1.0 sentiment intensity
- `sentiment_label`: `text` - `"positive"`, `"neutral"`, `"negative"`
- `salience_score`: `double precision` - 0.0-1.0 salience score (e.g., `0.428`)
- `novelty_score`: `double precision` - Novelty score (e.g., `0.0875`)

### Domain-Specific Edges

- `text`: `text` - Original event text
- `text_normalized`: `text` - Normalized text for processing
- `language`: `text` - Language code (e.g., `"en"`)

### Data Format Notes

- **JSON Fields**: All JSON fields are stored as text strings and need `json.loads()` parsing
- **Null Handling**: Many fields may be `null` - always check before processing
- **Array Fields**: `dominant_emotions_json` is a JSON array of strings
- **Numeric Fields**: All floating-point fields use `double precision` (Python `float`)
- **Boolean Fields**: `is_weekend` is standard SQL boolean
- **Text Fields**: All text fields are standard strings, may contain unicode

### Sample Data Patterns

```python
# Emotion data structure
dominant_emotions_json = ["relief", "contentment"]  # List[str]

# NER data structure
ner_entities_json = {
    "ner_family": {"entities": []},
    "ner_general": {"entities": []}
}  # Dict with nested structure

# Temporal data structure
temporal_json = {"entities": []}  # Dict with entities array

# Relationship data structure
extracted_relations_json = []  # List (currently empty)
```

## Required Updates for New Relationship Types

When implementing the new edge enrichers, update the `VALID_RELATIONSHIP_TYPES` constant in `k0/modules/consolidation/staging/kg_write_assembler.py` to document the expanded relationship type vocabulary:

```python
VALID_RELATIONSHIP_TYPES = frozenset({
    # Existing types
    "KNOWS", "LOCATED_AT", "PART_OF", "CAUSES", "RELATED_TO",
    "WORKS_AT", "LIVES_IN", "OWNS", "CREATES", "USES",

    # New enricher types (from enhancement plan)
    "EMOTIONALLY_RELATED",      # EmotionSimilarityEnricher
    "INTENT_RELATED",           # IntentSimilarityEnricher
    "CO_MENTIONED",             # NamedEntityEnricher
    "PARENT_OF", "FRIEND_OF",   # RelationshipTypeEnricher
    "CONTEXTUALLY_RELATED",     # Enhanced ContextualEdgeEnricher
    "MULTI_MODAL_RELATED",      # MultiModalSimilarityEnricher
    "TEMPORALLY_PATTERNED",     # TemporalPatternEnricher
})
```

**Note**: This constant is currently unused for validation but serves as documentation. The database schema and R6/R7 phases already support arbitrary relationship types without code changes.
