# ADR-0081c: Episodic Memory â†’ Knowledge Graph Integration

**Status:** Proposed
**Date:** 2025-10-22
**Parent ADR:** ADR-0081 (K0 Knowledge Graph Architecture)
**Implements:** Pipeline for converting episodic memories to KG entities and relationships

## Context

From **ADR-0081**, the Knowledge Graph needs **automated population** from episodic memories:

**Current K0 Pipeline (D4):**
- **P03 Consolidation:** Episodic â†’ Semantic memory transformation
- **Missing:** Episodic â†’ Knowledge Graph transformation

**Use Cases:**

1. **Conversation Parsing:** "Alice visited last Tuesday" â†’ Entity(Alice, Person), Event(visit, 2024-01-16)
2. **Relationship Extraction:** "My sister Alice works at Microsoft" â†’ Edge(User, sister_of, Alice), Edge(Alice, employed_by, Microsoft)
3. **Entity Resolution:** Multiple mentions of "Alice" â†’ single Entity(node-alice)
4. **Temporal Extraction:** "Bob got married in 2020" â†’ Edge(Bob, married_to, Carol, valid_from=2020-01-01)

**From K0 Architecture Diagrams:**

- **D3 (project_architecture_part3.mmd):** P03 Consolidation pipeline for episodic â†’ semantic transformation
- **D4 (project_architecture_part4.mmd):** `KG_RELATION_DISCOVERY` for relationship discovery, `KG_CONCEPT_EVOLUTION` for entity evolution
- **Missing:** Pipeline handler for episodic â†’ KG

**Key Requirements:**

- **Automated Extraction:** No manual entity tagging required
- **Confidence Scoring:** Entity resolution confidence (0.0-1.0) for disambiguation
- **Incremental Updates:** New conversations update existing entities
- **Performance:** <500ms P95 for conversation processing (100-500 words)

## Decision

Implement **K0 P03 Consolidation â†’ KG pipeline** with 4-stage extraction:

### Stage 1: Entity Extraction (NER)

**Named Entity Recognition (NER)** to identify entities in conversation text.

```python
# k0/kg/entity_extractor.py
from typing import List, Dict, Tuple
from dataclasses import dataclass
import spacy  # Or other NER model

@dataclass
class ExtractedEntity:
    """Entity extracted from text."""
    text: str                    # Original text mention ("Alice", "Microsoft")
    entity_type: str             # Person, Location, Event, Organization, Thing
    start_char: int              # Character offset in text
    end_char: int                # Character offset in text
    confidence: float            # 0.0 to 1.0
    properties: Dict             # Extracted properties

class EntityExtractor:
    """Extract entities from episodic memory text."""

    def __init__(self, model_name: str = "en_core_web_sm"):
        """Initialize NER model.

        Args:
            model_name: spaCy model name (en_core_web_sm, en_core_web_md, en_core_web_lg)
        """
        self.nlp = spacy.load(model_name)

    async def extract(self, text: str) -> List[ExtractedEntity]:
        """Extract entities from text.

        Args:
            text: Conversation text from episodic memory

        Returns:
            List of extracted entities

        Performance: <200ms P95 (100-500 words)

        Example:
            text = "My sister Alice works at Microsoft in Seattle."
            entities = await extractor.extract(text)
            # Returns:
            # [
            #   ExtractedEntity(text="Alice", entity_type="Person", confidence=0.95),
            #   ExtractedEntity(text="Microsoft", entity_type="Organization", confidence=0.98),
            #   ExtractedEntity(text="Seattle", entity_type="Location", confidence=0.97)
            # ]
        """
        doc = self.nlp(text)
        entities = []

        for ent in doc.ents:
            # Map spaCy entity labels to K0 entity types
            entity_type = self._map_entity_type(ent.label_)

            # Extract properties (if available)
            properties = self._extract_properties(ent, doc)

            entities.append(ExtractedEntity(
                text=ent.text,
                entity_type=entity_type,
                start_char=ent.start_char,
                end_char=ent.end_char,
                confidence=0.9,  # spaCy doesn't provide confidence, use default
                properties=properties
            ))

        return entities

    def _map_entity_type(self, spacy_label: str) -> str:
        """Map spaCy entity labels to K0 entity types.

        spaCy labels: PERSON, ORG, GPE, LOC, DATE, TIME, EVENT, PRODUCT, etc.
        K0 types: Person, Location, Event, Organization, Thing
        """
        mapping = {
            "PERSON": "Person",
            "ORG": "Organization",
            "GPE": "Location",  # Geo-political entity
            "LOC": "Location",
            "FAC": "Location",  # Facility
            "DATE": "Event",    # Temporal event
            "TIME": "Event",
            "EVENT": "Event",
            "PRODUCT": "Thing",
            "WORK_OF_ART": "Thing"
        }
        return mapping.get(spacy_label, "Thing")

    def _extract_properties(self, entity: spacy.tokens.Span, doc: spacy.tokens.Doc) -> Dict:
        """Extract additional properties for entity.

        Example: "Dr. Alice Smith" â†’ {"title": "Dr.", "full_name": "Alice Smith"}
        """
        properties = {}

        # Extract title (Dr., Mr., Ms., etc.)
        if entity[0].text in ["Dr", "Dr.", "Mr", "Mr.", "Ms", "Ms.", "Mrs", "Mrs."]:
            properties["title"] = entity[0].text

        # Extract full name (for PERSON entities)
        if entity.label_ == "PERSON":
            properties["full_name"] = entity.text

        return properties
```

**Entity Type Mapping:**

| spaCy Label | K0 Entity Type | Examples |
|-------------|----------------|----------|
| PERSON | Person | Alice, Bob, Dr. Smith |
| ORG | Organization | Microsoft, Harvard, NASA |
| GPE | Location | Seattle, USA, Europe |
| LOC, FAC | Location | Pike Place, Office, Home |
| DATE, TIME, EVENT | Event | 2024, last Tuesday, wedding |
| PRODUCT, WORK_OF_ART | Thing | iPhone, Mona Lisa, Tesla |

### Stage 2: Relationship Extraction

**Extract relationships** between entities using dependency parsing.

```python
# k0/kg/relationship_extractor.py
from typing import List, Dict, Tuple
from dataclasses import dataclass
import spacy

@dataclass
class ExtractedRelationship:
    """Relationship extracted from text."""
    source_entity: str           # Entity text ("Alice")
    target_entity: str           # Entity text ("Microsoft")
    rel_type: str                # Relationship type (employed_by, sister_of, etc.)
    confidence: float            # 0.0 to 1.0
    valid_from: int | None       # Unix timestamp (ms), None = unknown
    valid_to: int | None         # Unix timestamp (ms), None = ongoing

class RelationshipExtractor:
    """Extract relationships from episodic memory text."""

    def __init__(self):
        self.nlp = spacy.load("en_core_web_sm")

        # Relationship patterns (verb â†’ relationship type)
        self.patterns = {
            # Employment
            "work": "employed_by",
            "works": "employed_by",
            "worked": "employed_by",
            "employee": "employed_by",

            # Family
            "sister": "sister_of",
            "brother": "brother_of",
            "parent": "parent",
            "child": "child",
            "mother": "parent",
            "father": "parent",
            "son": "child",
            "daughter": "child",
            "spouse": "married_to",
            "married": "married_to",
            "husband": "married_to",
            "wife": "married_to",

            # Location
            "live": "lives_in",
            "lives": "lives_in",
            "lived": "lives_in",
            "born": "born_in",
            "visit": "visits",
            "visited": "visits",

            # Social
            "friend": "friend",
            "colleague": "colleague",
            "knows": "acquaintance",

            # Affiliation
            "member": "member_of",
            "attend": "attends",
            "attended": "attended",
            "graduated": "graduated_from"
        }

    async def extract(
        self,
        text: str,
        entities: List[ExtractedEntity]
    ) -> List[ExtractedRelationship]:
        """Extract relationships between entities.

        Args:
            text: Conversation text from episodic memory
            entities: Entities extracted by EntityExtractor

        Returns:
            List of extracted relationships

        Performance: <200ms P95 (100-500 words, 10 entities)

        Example:
            text = "My sister Alice works at Microsoft in Seattle."
            entities = [Entity(Alice, Person), Entity(Microsoft, Org), Entity(Seattle, Loc)]
            relationships = await extractor.extract(text, entities)
            # Returns:
            # [
            #   Relationship(source="Alice", target="Microsoft", rel_type="employed_by"),
            #   Relationship(source="Alice", target="Seattle", rel_type="lives_in")
            # ]
        """
        doc = self.nlp(text)
        relationships = []

        # Build entity lookup
        entity_lookup = {ent.text: ent for ent in entities}

        # Extract relationships using dependency parsing
        for token in doc:
            # Look for relationship patterns
            for pattern, rel_type in self.patterns.items():
                if pattern in token.lemma_:
                    # Find subject and object
                    subject = self._find_subject(token)
                    obj = self._find_object(token)

                    if subject and obj:
                        source_ent = entity_lookup.get(subject.text)
                        target_ent = entity_lookup.get(obj.text)

                        if source_ent and target_ent:
                            relationships.append(ExtractedRelationship(
                                source_entity=source_ent.text,
                                target_entity=target_ent.text,
                                rel_type=rel_type,
                                confidence=0.8,  # Default confidence
                                valid_from=None,  # Extract from temporal mentions
                                valid_to=None
                            ))

        # Extract temporal information
        relationships = await self._extract_temporal_info(doc, relationships)

        return relationships

    def _find_subject(self, token: spacy.tokens.Token) -> spacy.tokens.Token | None:
        """Find subject of verb using dependency tree."""
        for child in token.children:
            if child.dep_ in ["nsubj", "nsubjpass"]:
                return child
        return None

    def _find_object(self, token: spacy.tokens.Token) -> spacy.tokens.Token | None:
        """Find object of verb using dependency tree."""
        for child in token.children:
            if child.dep_ in ["dobj", "pobj", "attr"]:
                return child
        return None

    async def _extract_temporal_info(
        self,
        doc: spacy.tokens.Doc,
        relationships: List[ExtractedRelationship]
    ) -> List[ExtractedRelationship]:
        """Extract temporal information (valid_from/valid_to) from text.

        Example: "Bob married Carol in 2020" â†’ valid_from=2020-01-01
        """
        # Look for DATE entities near relationships
        for rel in relationships:
            for ent in doc.ents:
                if ent.label_ == "DATE":
                    # Parse date text to Unix timestamp
                    timestamp = self._parse_date(ent.text)
                    if timestamp:
                        rel.valid_from = timestamp

        return relationships

    def _parse_date(self, date_text: str) -> int | None:
        """Parse date text to Unix timestamp.

        Examples:
        - "2020" â†’ 1577836800000 (2020-01-01)
        - "last Tuesday" â†’ calculate from today
        - "in June" â†’ calculate from today
        """
        import dateutil.parser
        try:
            dt = dateutil.parser.parse(date_text)
            return int(dt.timestamp() * 1000)
        except:
            return None
```

### Stage 3: Entity Resolution & Disambiguation

**Resolve multiple mentions** of same entity and **disambiguate** ambiguous mentions.

```python
# k0/kg/entity_resolver.py
from typing import List, Dict, Tuple
from dataclasses import dataclass
from k0.drivers.sqlite_kg import SQLiteKGDriver

@dataclass
class ResolvedEntity:
    """Entity resolved to existing KG node or new node."""
    extracted_entity: ExtractedEntity
    node_id: str | None          # Existing node ID (None = new entity)
    confidence: float            # Resolution confidence (0.0-1.0)
    is_new: bool                 # True if new entity, False if existing

class EntityResolver:
    """Resolve entities to existing KG nodes or create new ones."""

    def __init__(self, kg_driver: SQLiteKGDriver):
        self.kg_driver = kg_driver

    async def resolve(
        self,
        entities: List[ExtractedEntity],
        context: Dict  # User context (family members, known entities)
    ) -> List[ResolvedEntity]:
        """Resolve entities to KG nodes.

        Args:
            entities: Entities extracted by EntityExtractor
            context: User context (e.g., {"user_id": "node-user", "family": [...]})

        Returns:
            List of resolved entities

        Performance: <100ms P95 (10 entities, 1000 existing nodes)

        Resolution Strategy:
        1. Exact label match (high confidence): "Alice" â†’ existing node-alice (conf=0.95)
        2. Fuzzy match (medium confidence): "Alicia" â†’ node-alice (conf=0.7)
        3. Context match (medium confidence): "Mom" â†’ node-mother (conf=0.8 if in family)
        4. No match (new entity): "Bob" â†’ new node (conf=1.0 for new creation)
        """
        resolved = []

        for entity in entities:
            # Strategy 1: Exact label match
            existing = await self.kg_driver.find_entities(
                entity_type=entity.entity_type,
                label_pattern=entity.text
            )

            if existing:
                resolved.append(ResolvedEntity(
                    extracted_entity=entity,
                    node_id=existing[0].node_id,
                    confidence=0.95,
                    is_new=False
                ))
                continue

            # Strategy 2: Fuzzy match (using Levenshtein distance)
            fuzzy_matches = await self._fuzzy_match(entity)
            if fuzzy_matches:
                best_match = fuzzy_matches[0]
                if best_match.confidence > 0.7:
                    resolved.append(ResolvedEntity(
                        extracted_entity=entity,
                        node_id=best_match.node_id,
                        confidence=best_match.confidence,
                        is_new=False
                    ))
                    continue

            # Strategy 3: Context match (e.g., "Mom" â†’ user's mother)
            context_match = await self._context_match(entity, context)
            if context_match:
                resolved.append(ResolvedEntity(
                    extracted_entity=entity,
                    node_id=context_match.node_id,
                    confidence=context_match.confidence,
                    is_new=False
                ))
                continue

            # Strategy 4: New entity
            resolved.append(ResolvedEntity(
                extracted_entity=entity,
                node_id=None,
                confidence=1.0,  # High confidence for new creation
                is_new=True
            ))

        return resolved

    async def _fuzzy_match(
        self,
        entity: ExtractedEntity
    ) -> List[Tuple[str, float]]:
        """Fuzzy match entity label to existing nodes.

        Uses Levenshtein distance for string similarity.
        """
        import Levenshtein

        existing = await self.kg_driver.find_entities(
            entity_type=entity.entity_type,
            limit=100
        )

        matches = []
        for existing_entity in existing:
            similarity = Levenshtein.ratio(entity.text, existing_entity.label)
            if similarity > 0.7:  # Threshold for fuzzy match
                matches.append((existing_entity.node_id, similarity))

        return sorted(matches, key=lambda x: x[1], reverse=True)

    async def _context_match(
        self,
        entity: ExtractedEntity,
        context: Dict
    ) -> ResolvedEntity | None:
        """Match entity using user context.

        Example: "Mom" â†’ user's mother (if in family context)
        """
        # Common family terms
        family_terms = {
            "mom": "mother",
            "dad": "father",
            "sis": "sister",
            "bro": "brother"
        }

        term = entity.text.lower()
        if term in family_terms:
            # Look for user's family member with this relationship
            user_id = context.get("user_id")
            if user_id:
                family = await self.kg_driver.get_relationships(
                    source_id=user_id,
                    rel_type=family_terms[term],
                    direction="outgoing"
                )
                if family:
                    return ResolvedEntity(
                        extracted_entity=entity,
                        node_id=family[0].target_id,
                        confidence=0.8,
                        is_new=False
                    )

        return None
```

### Stage 4: KG Update (Insert/Update)

**Insert new entities** and **update existing entities** in K0::st_kg.

```python
# k0/kg/episodic_integration.py
from k0.drivers.sqlite_kg import SQLiteKGDriver
from k0.kg.entity_extractor import EntityExtractor
from k0.kg.relationship_extractor import RelationshipExtractor
from k0.kg.entity_resolver import EntityResolver

@dataclass
class KGUpdateResult:
    """Result of KG update from episodic memory."""
    entities_created: int
    entities_updated: int
    relationships_created: int
    relationships_updated: int
    processing_time_ms: float

async def consolidate_episodic_to_kg(
    episodic_memory: EpisodicMemory,
    kg_driver: SQLiteKGDriver,
    user_context: Dict
) -> KGUpdateResult:
    """Convert episodic memory to KG entities and relationships.

    Triggered by K0 P03 Consolidation pipeline (D4).

    Args:
        episodic_memory: Episodic memory from K0::st_sqlite
        kg_driver: K0::st_kg driver
        user_context: User context for entity resolution

    Returns:
        KG update result with counts

    Performance: <500ms P95 (100-500 words, 10 entities, 5 relationships)

    Example:
        episodic = EpisodicMemory(
            text="My sister Alice works at Microsoft in Seattle.",
            timestamp=1704067200000
        )
        result = await consolidate_episodic_to_kg(episodic, kg_driver, user_context)
        # Result:
        # entities_created=2 (Alice, Microsoft),
        # relationships_created=2 (sister_of, employed_by)
    """
    import time
    start = time.perf_counter()

    # Stage 1: Extract entities
    extractor = EntityExtractor()
    entities = await extractor.extract(episodic_memory.text)

    # Stage 2: Extract relationships
    rel_extractor = RelationshipExtractor()
    relationships = await rel_extractor.extract(episodic_memory.text, entities)

    # Stage 3: Resolve entities
    resolver = EntityResolver(kg_driver)
    resolved_entities = await resolver.resolve(entities, user_context)

    # Stage 4: Insert/update entities
    entities_created = 0
    entities_updated = 0
    entity_id_map = {}  # Map extracted entity text â†’ node_id

    for resolved in resolved_entities:
        if resolved.is_new:
            # Create new entity
            node_id = await kg_driver.insert_node(
                entity_type=resolved.extracted_entity.entity_type,
                label=resolved.extracted_entity.text,
                properties=resolved.extracted_entity.properties
            )
            entity_id_map[resolved.extracted_entity.text] = node_id
            entities_created += 1
        else:
            # Update existing entity
            await kg_driver.update_node(
                node_id=resolved.node_id,
                properties=resolved.extracted_entity.properties
            )
            entity_id_map[resolved.extracted_entity.text] = resolved.node_id
            entities_updated += 1

    # Stage 5: Insert/update relationships
    relationships_created = 0
    relationships_updated = 0

    for rel in relationships:
        source_id = entity_id_map.get(rel.source_entity)
        target_id = entity_id_map.get(rel.target_entity)

        if source_id and target_id:
            # Check if relationship already exists
            existing = await kg_driver.find_relationship(
                source_id=source_id,
                target_id=target_id,
                rel_type=rel.rel_type
            )

            if existing:
                # Update existing relationship
                await kg_driver.update_edge(
                    edge_id=existing.edge_id,
                    confidence=rel.confidence,
                    valid_from=rel.valid_from,
                    valid_to=rel.valid_to
                )
                relationships_updated += 1
            else:
                # Create new relationship
                await kg_driver.insert_edge(
                    source_id=source_id,
                    target_id=target_id,
                    rel_type=rel.rel_type,
                    confidence=rel.confidence,
                    valid_from=rel.valid_from,
                    valid_to=rel.valid_to
                )
                relationships_created += 1

    processing_time_ms = (time.perf_counter() - start) * 1000

    return KGUpdateResult(
        entities_created=entities_created,
        entities_updated=entities_updated,
        relationships_created=relationships_created,
        relationships_updated=relationships_updated,
        processing_time_ms=processing_time_ms
    )
```

## Integration with K0 P03 Pipeline

```python
# k0/kernel/pipeline_handlers.py (add to P03 handlers)
from k0.kg.episodic_integration import consolidate_episodic_to_kg

async def handle_p03_consolidation(event: PipelineEvent):
    """K0 P03 Consolidation handler with KG integration."""

    episodic_memory = event.payload

    # Existing: Episodic â†’ Semantic
    await consolidate_episodic_to_semantic(episodic_memory)

    # NEW: Episodic â†’ KG
    kg_result = await consolidate_episodic_to_kg(
        episodic_memory,
        kg_driver=event.drivers["kg"],
        user_context=event.context
    )

    # Log metrics
    logger.info(
        "kg_consolidation_complete",
        entities_created=kg_result.entities_created,
        relationships_created=kg_result.relationships_created,
        processing_time_ms=kg_result.processing_time_ms
    )
```

## Confidence Scoring & Disambiguation

### Confidence Calculation

```python
def calculate_entity_confidence(
    entity: ExtractedEntity,
    resolution: ResolvedEntity,
    context: Dict
) -> float:
    """Calculate overall confidence for entity resolution.

    Factors:
    1. NER confidence (spaCy): 0.9 default
    2. Resolution confidence (exact/fuzzy/context match): 0.7-0.95
    3. Context confirmation (user feedback): +0.1 boost

    Formula: confidence = (ner_conf + resolution_conf) / 2
    """
    ner_confidence = entity.confidence
    resolution_confidence = resolution.confidence

    # Context boost (if user previously confirmed this entity)
    context_boost = 0.1 if context.get("confirmed_entities", {}).get(entity.text) else 0.0

    return min((ner_confidence + resolution_confidence) / 2 + context_boost, 1.0)
```

### Disambiguation UI (User Confirmation)

```python
async def request_user_disambiguation(
    entity: ExtractedEntity,
    candidates: List[ResolvedEntity]
) -> str:
    """Request user to disambiguate between multiple candidates.

    Example:
        Entity: "Alice"
        Candidates:
        1. Alice Smith (sister, confidence=0.75)
        2. Alice Johnson (colleague, confidence=0.70)

        User selects: 1
        Returns: node-alice-smith
    """
    # Send disambiguation request via K0 SSE Port
    # User responds via UI
    pass
```

## Consequences

### Positive

1. **âœ… Automated KG Population:** No manual entity tagging required
2. **âœ… Incremental Updates:** New conversations update existing entities
3. **âœ… Confidence Scoring:** Handles ambiguous entities with confidence levels
4. **âœ… Temporal Extraction:** Extracts valid_from/valid_to from conversation text
5. **âœ… Context-Aware Resolution:** Uses user context (family members) for disambiguation
6. **âœ… Performance:** <500ms P95 for conversation processing

### Negative

1. **âŒ NER Accuracy:** spaCy NER has ~85-90% accuracy (F1 score), may miss entities
2. **âŒ Relationship Extraction Complexity:** Dependency parsing may miss complex relationships
3. **âŒ Entity Disambiguation:** Ambiguous names (multiple "Alice") require user confirmation
4. **âŒ Temporal Extraction Accuracy:** Date parsing may fail for vague dates ("last week")
5. **âŒ Processing Latency:** 500ms may be too slow for real-time conversations

### Mitigations

1. **NER Accuracy:** Use larger spaCy model (en_core_web_lg) for better accuracy
2. **Relationship Extraction:** Add rule-based patterns + ML model for complex cases
3. **Entity Disambiguation:** Request user confirmation for low-confidence matches (<0.7)
4. **Temporal Extraction:** Use dateutil.parser + heuristics for relative dates
5. **Processing Latency:** Run P03 consolidation asynchronously (not blocking user)

## Implementation Notes

### Dependencies

```python
# requirements.txt
spacy>=3.7.0
python-Levenshtein>=0.21.0
dateutil>=2.8.2
```

### spaCy Model Installation

```bash
python -m spacy download en_core_web_sm  # 13 MB (fast, lower accuracy)
python -m spacy download en_core_web_md  # 43 MB (medium, better accuracy)
python -m spacy download en_core_web_lg  # 560 MB (slow, best accuracy)
```

### Testing Strategy

```python
# tests/k0/kg/test_episodic_integration.py
import ward
from k0.kg.episodic_integration import consolidate_episodic_to_kg

async def test_entity_extraction():
    text = "My sister Alice works at Microsoft in Seattle."
    extractor = EntityExtractor()
    entities = await extractor.extract(text)

    assert len(entities) == 3
    assert entities[0].text == "Alice"
    assert entities[0].entity_type == "Person"
    assert entities[1].text == "Microsoft"
    assert entities[1].entity_type == "Organization"

async def test_relationship_extraction():
    text = "My sister Alice works at Microsoft."
    entities = [Entity("Alice", "Person"), Entity("Microsoft", "Organization")]

    rel_extractor = RelationshipExtractor()
    relationships = await rel_extractor.extract(text, entities)

    assert len(relationships) >= 1
    assert relationships[0].rel_type == "employed_by"
    assert relationships[0].source_entity == "Alice"
    assert relationships[0].target_entity == "Microsoft"

async def test_entity_resolution():
    # Setup: Existing entity "Alice"
    kg_driver = SQLiteKGDriver(":memory:")
    await kg_driver.insert_node("Person", "Alice", {})

    # Test: Resolve extracted "Alice" to existing node
    entities = [ExtractedEntity("Alice", "Person", 0, 5, 0.9, {})]
    resolver = EntityResolver(kg_driver)
    resolved = await resolver.resolve(entities, {})

    assert resolved[0].is_new == False
    assert resolved[0].confidence > 0.9
```

## References

**Research:**
- Named Entity Recognition: spaCy Documentation
- Dependency Parsing: Stanford NLP
- Entity Resolution: Survey (ACM Computing Surveys)
- Temporal Information Extraction: SUTime, HeidelTime

**Related ADRs:**
- ADR-0081: K0 Knowledge Graph Architecture (parent)
- ADR-0081a: Temporal Graph Schema Design
- ADR-0081b: Query API & Traversal Algorithms
- ADR-00XX: K0 P03 Consolidation Pipeline

**Implementation Files:**
- `k0/kg/episodic_integration.py`: Main pipeline handler
- `k0/kg/entity_extractor.py`: NER entity extraction
- `k0/kg/relationship_extractor.py`: Relationship extraction
- `k0/kg/entity_resolver.py`: Entity resolution & disambiguation

---

**Status:** Proposed (2025-10-22)
**Next Steps:**
1. Implement entity extraction with spaCy
2. Implement relationship extraction with dependency parsing
3. Implement entity resolution & disambiguation
4. Integrate with K0 P03 Consolidation pipeline
5. Write extraction tests
6. Write performance tests

