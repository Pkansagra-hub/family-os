# ADR-0084c: Knowledge Graph Consolidation — Entity Extraction & Relationship Inference

**Status:** Proposed 🔄
**Parent ADR:** ADR-0084 (K0 Memory Consolidation Pipeline)
**Last Updated:** 2025-01-22

---

## Context

**From ADR-0084:** K0 P03 Consolidation Pipeline requires **knowledge graph enrichment** that extracts entities, infers relationships, and evolves schemas from consolidated episodic memories.

**Knowledge Graph Architecture (from K0 diagrams):**

- **K0::st_kg** (`drivers/sqlite_kg.py`) — Knowledge graph storage (nodes, edges, temporal)
- **KG_TEMPORAL_ENGINE** (`kg/temporal.py`) — Time-aware graph queries
- **KG_CAUSAL_GRAPH** (`kg/causal_graph.py`) — Causal relationship inference
- **KG_RELATION_DISCOVERY** (`kg/relation_discovery.py`) — Pattern-based relationship discovery
- **KG_CONCEPT_EVOLUTION** (`kg/concept_evolution.py`) — Schema updates & version control
- **KG_INCONSISTENCY_RESOLUTION** (`kg/inconsistency_resolution.py`) — Consistency enforcement

**Integration Points:**

- **CA3_RECURRENT** provides associative patterns for relationship inference
- **Episodic-to-semantic** pipeline feeds entity candidates
- **Grounding systems** link entities to sensory/linguistic/procedural data

---

## Decision

Implement **four-stage knowledge graph consolidation** during NREM Phase 2:

### Stage 1: Entity Extraction (identify people, places, concepts)
### Stage 2: Relationship Inference (causal, temporal, associative)
### Stage 3: Schema Evolution (concept updates, version control)
### Stage 4: Temporal Reasoning (time-aware queries, historical analysis)

---

## Stage 1: Entity Extraction

**Goal:** Extract structured entities from consolidated episodic memories.

### Entity Types

```python
class EntityType(Enum):
    """Entity categories for knowledge graph."""
    PERSON = "PERSON"           # People, family members, contacts
    PLACE = "PLACE"             # Locations, rooms, addresses
    ORGANIZATION = "ORGANIZATION"  # Companies, institutions
    CONCEPT = "CONCEPT"         # Abstract ideas, topics, themes
    EVENT = "EVENT"             # Meetings, appointments, occasions
    TEMPORAL = "TEMPORAL"       # Time markers, durations, schedules
    OBJECT = "OBJECT"           # Physical items, tools, belongings
```

### Extraction Algorithm

```python
class EntityExtractor:
    """
    Extract entities from consolidated episodic memories.

    Inputs:
    - Episodic memories (from K0::st_sqlite[episodic_memories])
    - Semantic patterns (from Neocortical Integration, ADR-0084a)
    - Linguistic grounding (entity mentions, noun phrases)

    Outputs:
    - Entity nodes in K0::st_kg[nodes]
    - Entity embeddings in K0::st_vector
    """

    async def extract_entities(self, consolidated_memories: List[EpisodicMemory]) -> List[Entity]:
        """
        Extract entities from consolidated memories.

        Process:
        1. Scan memory sequences for entity mentions
        2. Cluster mentions by similarity (embedding cosine ≥0.85)
        3. Create canonical entity nodes
        4. Link entities to source memories
        """
        entity_mentions = []

        # Scan memories for entity mentions
        for memory in consolidated_memories:
            mentions = await self.scan_for_entities(memory)
            entity_mentions.extend(mentions)

        # Cluster mentions by similarity
        entity_clusters = await self.cluster_mentions(entity_mentions)

        # Create canonical entities
        entities = []
        for cluster in entity_clusters:
            entity = await self.create_canonical_entity(cluster)
            entities.append(entity)

        return entities

    async def scan_for_entities(self, memory: EpisodicMemory) -> List[EntityMention]:
        """
        Scan memory for entity mentions.

        Techniques:
        - Named Entity Recognition (NER) via linguistic_mapping
        - Noun phrase extraction
        - Reference resolution (pronouns → entities)
        """
        mentions = []

        # Extract text from memory sequence
        text = memory.sequence.to_text()

        # Named Entity Recognition
        ner_mentions = await self.ner_extractor.extract(text)

        # Noun phrase extraction
        noun_phrases = await self.noun_phrase_extractor.extract(text)

        # Combine mentions
        mentions.extend(ner_mentions)
        mentions.extend(noun_phrases)

        return mentions

    async def cluster_mentions(self, mentions: List[EntityMention]) -> List[List[EntityMention]]:
        """
        Cluster entity mentions by embedding similarity.

        Algorithm:
        1. Compute embeddings for each mention (via P08 Embeddings)
        2. Compute pairwise cosine similarity
        3. Cluster mentions with similarity ≥0.85
        4. Return clusters (each cluster → one canonical entity)
        """
        # Compute embeddings
        embeddings = []
        for mention in mentions:
            emb = await compute_embedding(mention.text)
            embeddings.append(emb)

        # Hierarchical clustering
        from scipy.cluster.hierarchy import fclusterdata
        clusters = fclusterdata(
            embeddings,
            t=0.85,  # Similarity threshold
            criterion='distance',
            metric='cosine'
        )

        # Group mentions by cluster
        clustered_mentions = defaultdict(list)
        for mention, cluster_id in zip(mentions, clusters):
            clustered_mentions[cluster_id].append(mention)

        return list(clustered_mentions.values())

    async def create_canonical_entity(self, cluster: List[EntityMention]) -> Entity:
        """
        Create canonical entity from mention cluster.

        Canonical form:
        - Name: Most frequent mention text
        - Type: Majority vote across mentions
        - Embedding: Centroid of mention embeddings
        - Aliases: All unique mention texts
        - Source memories: All memories containing mentions
        """
        # Canonical name (most frequent)
        name_counts = Counter([m.text for m in cluster])
        canonical_name = name_counts.most_common(1)[0][0]

        # Entity type (majority vote)
        type_counts = Counter([m.entity_type for m in cluster])
        canonical_type = type_counts.most_common(1)[0][0]

        # Embedding (centroid)
        embeddings = [m.embedding for m in cluster]
        canonical_embedding = np.mean(embeddings, axis=0)

        # Aliases
        aliases = list(set([m.text for m in cluster]))

        # Source memories
        source_memories = list(set([m.memory_id for m in cluster]))

        # Create entity
        entity = Entity(
            id=generate_entity_id(),
            name=canonical_name,
            entity_type=canonical_type,
            embedding=canonical_embedding,
            aliases=aliases,
            source_memories=source_memories
        )

        # Store in K0::st_kg[nodes]
        await store_entity_node(entity)

        return entity
```

---

## Stage 2: Relationship Inference

**Goal:** Infer relationships between entities based on co-occurrence patterns and causal reasoning.

### Relationship Types

```python
class RelationType(Enum):
    """Relationship categories for knowledge graph edges."""
    CAUSAL = "CAUSAL"           # X causes Y (e.g., "coffee → alertness")
    TEMPORAL = "TEMPORAL"       # X before/after Y (e.g., "morning → breakfast")
    ASSOCIATIVE = "ASSOCIATIVE" # X co-occurs with Y (e.g., "laptop → desk")
    HIERARCHICAL = "HIERARCHICAL"  # X is-a Y (e.g., "poodle → dog")
    POSSESSIVE = "POSSESSIVE"   # X owns Y (e.g., "Alice → car")
    SOCIAL = "SOCIAL"           # X relates-to Y (e.g., "Alice → friend → Bob")
```

### Inference Algorithm

```python
class RelationshipInferencer:
    """
    Infer relationships between entities from consolidated memories.

    Inputs:
    - Entities (from Entity Extraction)
    - CA3_RECURRENT associations (recurrent patterns)
    - Episodic sequences (temporal co-occurrence)
    - Causal graph (from KG_CAUSAL_GRAPH)

    Outputs:
    - Relationship edges in K0::st_kg[edges]
    """

    async def infer_relationships(self, entities: List[Entity]) -> List[Relationship]:
        """
        Infer relationships between entity pairs.

        Process:
        1. Identify entity co-occurrences in episodic sequences
        2. Compute association strength (PMI, co-occurrence count)
        3. Classify relationship type (causal, temporal, associative)
        4. Create relationship edges
        """
        relationships = []

        # Identify co-occurring entity pairs
        entity_pairs = await self.find_cooccurring_pairs(entities)

        # For each pair, infer relationship
        for (entity_a, entity_b), cooccurrence_data in entity_pairs.items():
            relationship = await self.classify_relationship(
                entity_a,
                entity_b,
                cooccurrence_data
            )

            if relationship:
                relationships.append(relationship)

        return relationships

    async def find_cooccurring_pairs(self, entities: List[Entity]) -> Dict[Tuple[Entity, Entity], Dict]:
        """
        Find entity pairs that co-occur in episodic sequences.

        Co-occurrence criteria:
        - Both entities mentioned in same memory sequence
        - Temporal proximity <5 minutes
        - Minimum co-occurrence count: 3
        """
        cooccurrence_counts = defaultdict(lambda: {'count': 0, 'contexts': []})

        # Query episodic memories
        memories = await query_episodic_memories()

        for memory in memories:
            # Find entities mentioned in this memory
            mentioned_entities = [
                e for e in entities
                if memory.id in e.source_memories
            ]

            # Generate pairs
            for i, entity_a in enumerate(mentioned_entities):
                for entity_b in mentioned_entities[i+1:]:
                    pair = (entity_a, entity_b)
                    cooccurrence_counts[pair]['count'] += 1
                    cooccurrence_counts[pair]['contexts'].append(memory)

        # Filter by minimum count
        return {
            pair: data
            for pair, data in cooccurrence_counts.items()
            if data['count'] >= 3
        }

    async def classify_relationship(
        self,
        entity_a: Entity,
        entity_b: Entity,
        cooccurrence_data: Dict
    ) -> Optional[Relationship]:
        """
        Classify relationship type between entity pair.

        Classification rules:
        1. Causal: Check KG_CAUSAL_GRAPH for causal patterns
        2. Temporal: Check temporal ordering in sequences
        3. Associative: Default for co-occurrence without causal/temporal structure
        """
        # Check for causal relationship
        if await self.is_causal(entity_a, entity_b, cooccurrence_data):
            return Relationship(
                source=entity_a,
                target=entity_b,
                relation_type=RelationType.CAUSAL,
                strength=self.compute_strength(cooccurrence_data)
            )

        # Check for temporal relationship
        if await self.is_temporal(entity_a, entity_b, cooccurrence_data):
            return Relationship(
                source=entity_a,
                target=entity_b,
                relation_type=RelationType.TEMPORAL,
                strength=self.compute_strength(cooccurrence_data)
            )

        # Default: Associative
        return Relationship(
            source=entity_a,
            target=entity_b,
            relation_type=RelationType.ASSOCIATIVE,
            strength=self.compute_strength(cooccurrence_data)
        )

    async def is_causal(self, entity_a: Entity, entity_b: Entity, data: Dict) -> bool:
        """
        Check if relationship is causal (A causes B).

        Causal indicators:
        - A consistently precedes B (temporal ordering)
        - B rarely occurs without A (dependence)
        - Causal pattern in KG_CAUSAL_GRAPH
        """
        # Query KG_CAUSAL_GRAPH
        causal_graph = await query_causal_graph()

        if causal_graph.has_edge(entity_a.id, entity_b.id):
            return True

        # Check temporal ordering
        contexts = data['contexts']
        a_before_b_count = 0

        for memory in contexts:
            if self.entity_precedes(entity_a, entity_b, memory):
                a_before_b_count += 1

        # Causal if A precedes B in >70% of contexts
        return (a_before_b_count / len(contexts)) >= 0.70

    def compute_strength(self, cooccurrence_data: Dict) -> float:
        """
        Compute relationship strength (0.0 - 1.0).

        Factors:
        - Co-occurrence count (more co-occurrences → stronger)
        - Temporal proximity (closer in time → stronger)
        - Embedding similarity (semantically related → stronger)
        """
        count = cooccurrence_data['count']

        # Normalize by max count (assume max 20 co-occurrences)
        count_score = min(count / 20.0, 1.0)

        return count_score
```

---

## Stage 3: Schema Evolution

**Goal:** Update knowledge graph schema to reflect new concepts and evolving relationships.

**Module:** `kg/concept_evolution.py` (KG_CONCEPT_EVOLUTION)

### Schema Evolution Algorithm

```python
class SchemaEvolutionEngine:
    """
    Evolve knowledge graph schema as new concepts emerge.

    Evolution operations:
    1. Add new entity types (e.g., "HOBBY" if hobby entities frequent)
    2. Add new relationship types (e.g., "MENTORS" for mentor relationships)
    3. Merge similar concepts (e.g., "laptop" + "computer" → "computing_device")
    4. Split overly broad concepts (e.g., "work" → "meeting", "email", "coding")
    """

    async def evolve_schema(self, entities: List[Entity], relationships: List[Relationship]):
        """
        Evolve schema based on new entities and relationships.

        Process:
        1. Identify candidate schema changes
        2. Validate changes (consistency checks)
        3. Apply changes with version control
        4. Migrate existing data to new schema
        """
        # Identify candidate changes
        candidates = await self.identify_schema_changes(entities, relationships)

        # Validate changes
        valid_changes = await self.validate_changes(candidates)

        # Apply changes
        for change in valid_changes:
            await self.apply_schema_change(change)

    async def identify_schema_changes(
        self,
        entities: List[Entity],
        relationships: List[Relationship]
    ) -> List[SchemaChange]:
        """
        Identify candidate schema changes.

        Heuristics:
        - New entity type: ≥10 entities with same custom type
        - New relationship type: ≥5 relationships with same custom relation
        - Concept merge: ≥2 concepts with embedding similarity ≥0.90
        - Concept split: Single concept with ≥50 instances and high variance
        """
        changes = []

        # Check for new entity types
        type_counts = Counter([e.entity_type for e in entities if e.entity_type == EntityType.CONCEPT])
        for entity_type, count in type_counts.items():
            if count >= 10:
                changes.append(SchemaChange(
                    change_type="ADD_ENTITY_TYPE",
                    entity_type=entity_type
                ))

        # Check for new relationship types
        relation_counts = Counter([r.relation_type for r in relationships])
        for relation_type, count in relation_counts.items():
            if count >= 5:
                changes.append(SchemaChange(
                    change_type="ADD_RELATION_TYPE",
                    relation_type=relation_type
                ))

        return changes

    async def apply_schema_change(self, change: SchemaChange):
        """
        Apply schema change with version control.

        Version control:
        - Store schema version in K0::st_kg[schema_versions]
        - Log change in K0::st_sqlite[schema_log]
        - Support rollback if inconsistencies detected
        """
        # Increment schema version
        current_version = await get_schema_version()
        new_version = current_version + 1

        # Apply change
        if change.change_type == "ADD_ENTITY_TYPE":
            await add_entity_type(change.entity_type)
        elif change.change_type == "ADD_RELATION_TYPE":
            await add_relation_type(change.relation_type)

        # Store new version
        await store_schema_version(new_version, change)

        logger.info(
            "schema_evolved",
            change_type=change.change_type,
            old_version=current_version,
            new_version=new_version
        )
```

---

## Stage 4: Temporal Reasoning

**Goal:** Enable time-aware queries and historical analysis of knowledge graph.

**Module:** `kg/temporal.py` (KG_TEMPORAL_ENGINE)

### Temporal Storage

```python
class TemporalKnowledgeGraph:
    """
    Time-aware knowledge graph storage.

    Storage schema (K0::st_kg[temporal]):
    - Node snapshots: (node_id, timestamp, properties)
    - Edge snapshots: (edge_id, timestamp, properties)
    - Retention: 365 days (configurable)
    """

    async def store_temporal_snapshot(self, entity: Entity, timestamp: datetime):
        """
        Store time-stamped snapshot of entity.

        Use case:
        - Track entity property changes over time
        - Query historical states (e.g., "What were Alice's interests last month?")
        """
        snapshot = {
            'node_id': entity.id,
            'timestamp': timestamp,
            'properties': entity.to_dict()
        }

        await store_in_kg_temporal(snapshot)
```

### Temporal Queries

```python
async def query_historical_state(self, entity_id: str, timestamp: datetime) -> Entity:
    """
    Query entity state at specific time.

    Algorithm:
    1. Find latest snapshot before timestamp
    2. Reconstruct entity from snapshot
    """
    snapshot = await query_kg_temporal(
        node_id=entity_id,
        timestamp_lte=timestamp,
        order_by='timestamp DESC',
        limit=1
    )

    if snapshot:
        return Entity.from_snapshot(snapshot)

    return None

async def query_temporal_range(
    self,
    entity_id: str,
    start_time: datetime,
    end_time: datetime
) -> List[Entity]:
    """
    Query entity state changes over time range.

    Use case:
    - Track concept evolution ("How did 'AI' concept evolve over 6 months?")
    - Relationship lifecycle ("When did Alice and Bob's friendship start?")
    """
    snapshots = await query_kg_temporal(
        node_id=entity_id,
        timestamp_gte=start_time,
        timestamp_lte=end_time,
        order_by='timestamp ASC'
    )

    return [Entity.from_snapshot(s) for s in snapshots]
```

---

## Performance Characteristics

### Consolidation Timing

| Operation | Target Duration (P95) | Notes |
|-----------|----------------------|-------|
| Entity extraction | <30 seconds | Process 100-200 consolidated memories |
| Relationship inference | <45 seconds | Infer 50-100 relationships |
| Schema evolution | <15 seconds | Identify + apply 1-2 changes |
| Temporal snapshot | <10 seconds | Store 100-200 snapshots |
| **Total KG consolidation** | **<2 minutes** | Per NREM Phase 2 cycle |

### Storage

- **Nodes:** ~1000-5000 entities (typical family KG)
- **Edges:** ~5000-20000 relationships (5-10 edges per entity)
- **Temporal snapshots:** ~10000-50000 snapshots (365-day retention)
- **Storage footprint:** ~50-200 MB (SQLite with FTS5 indexes)

---

## Observability

### Metrics

```python
# Prometheus metrics
kg_entities_extracted_total = Counter(
    'consolidation_kg_entities_extracted_total',
    'Total entities extracted',
    ['entity_type']
)

kg_relationships_inferred_total = Counter(
    'consolidation_kg_relationships_inferred_total',
    'Total relationships inferred',
    ['relation_type']
)

kg_schema_evolutions_total = Counter(
    'consolidation_kg_schema_evolutions_total',
    'Total schema evolutions',
    ['change_type']
)
```

### Events

```
infra.consolidation.kg_extract     — Entity extraction complete
infra.consolidation.kg_infer       — Relationship inference complete
infra.consolidation.kg_evolve      — Schema evolution applied
```

---

## Related ADRs

- **ADR-0084:** K0 Memory Consolidation Pipeline (parent)
- **ADR-0084a:** Sleep-Cycle Memory Replay Algorithms (CA3_RECURRENT associations)
- **ADR-0084b:** Offline Consolidation Scheduler (NREM Phase 2 timing)
- **ADR-0084d:** Dream-Like Exploration & Reflection (KG traversal for insights)

---

## End of ADR-0084c
