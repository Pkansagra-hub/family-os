# Milestone 2: SummaryGenerator Module — Template-Based Text Generation

> **GAP Reference**: [GAP_001_CROSS_LAYER_VECTOR_LINKING.md](../architecture/gaps/GAP_001_CROSS_LAYER_VECTOR_LINKING.md) Section 4
> **Effort**: 2 days
> **Priority**: P0 (Critical)
> **Dependencies**: Milestone 1 (Schema Migration)

---

## Overview

Create a `SummaryGenerator` module that generates embeddable text for each truth layer WITHOUT using LLMs. This text will be:

1. Stored in `embedding_text` column
2. Fed to UltraBERT to create `embedding_vector`

---

## Epic: Create Text Summary Generation Module

### Strategy Summary (from GAP Section 4)

| Strategy | Best For | Complexity |
| -------- | -------- | ---------- |
| **Template-Based** | Structured data (patterns, routines, relationships) | Low |
| **Concatenation + Dedup** | Episodes with few source events | Low |
| **TextRank Extractive** | Episodes with many source events (>5) | Medium |
| **Narrative Arc** | Long episodes (first/peak/last) | Low |

---

## Issues

### Issue 2.1: Create EmbeddingTextGenerator Base Class

**Priority**: P0
**Effort**: 2 hours

**Description**:
Create the base abstract class and interface for text generation across all layers.

**Files to Create**:

- `k0/modules/consolidation/algorithms/embedding_text_generator.py` (NEW)

**Code Structure**:

```python
"""
EmbeddingTextGenerator — GAP-001 Implementation

Generates embeddable text for truth layers without LLM.
Uses template-based and extractive summarization strategies.

GAP Reference: GAP_001_CROSS_LAYER_VECTOR_LINKING.md §4
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from enum import Enum


class TextGenerationStrategy(str, Enum):
    """Strategy for generating embedding text."""
    TEMPLATE = "template"           # Fill placeholders from columns
    CONCATENATE = "concatenate"     # Join source texts with dedup
    TEXTRANK = "textrank"           # Extractive summarization
    NARRATIVE_ARC = "narrative_arc" # First + peak + last


@dataclass
class GeneratedText:
    """Result of text generation."""
    embedding_text: str              # Text to embed with UltraBERT
    source_texts_json: str           # JSON array of original texts
    strategy_used: TextGenerationStrategy
    token_count: int                 # Approximate token count


class EmbeddingTextGenerator(ABC):
    """Abstract base for layer-specific text generators."""

    @abstractmethod
    def generate(
        self,
        record_data: Dict[str, Any],
        source_texts: Optional[List[str]] = None,
    ) -> GeneratedText:
        """Generate embedding text for a record."""
        ...

    @property
    @abstractmethod
    def layer(self) -> str:
        """Target layer name (st_epi, st_sem, etc.)."""
        ...
```

**References**:

- GAP Section 4.1: [Strategy Overview](../architecture/gaps/GAP_001_CROSS_LAYER_VECTOR_LINKING.md#41-strategy-overview)
- GAP Section 4.8: [SummaryGenerator Module Interface](../architecture/gaps/GAP_001_CROSS_LAYER_VECTOR_LINKING.md#48-summarygenerator-module-interface)

**Acceptance Criteria**:

- [ ] Base class created with abstract methods
- [ ] `GeneratedText` dataclass defined
- [ ] `TextGenerationStrategy` enum defined
- [ ] Type hints complete

---

### Issue 2.2: Implement EpisodicTextGenerator

**Priority**: P0
**Effort**: 3 hours

**Description**:
Generate embedding text for `st_epi` episodes using template header + source text summarization.

**Files to Create**:

- `k0/modules/consolidation/algorithms/text_generators/episodic.py` (NEW)

**Generation Logic**:

```python
def generate(self, record_data: Dict, source_texts: List[str]) -> GeneratedText:
    """
    Episode embedding text = template header + summarized source texts.

    Template: "{day_of_week} {temporal_bucket} at {primary_location} with {participants}"
    Example: "Friday evening at Thai Palace with Mom, Dad"

    If source_texts:
        ≤3 events → Concatenate all
        ≤10 events → TextRank top 3
        >10 events → TextRank top 5
    """
```

**Template Fields** (from [0027_st_epi.py](../../k0/db/alembic/versions/0027_st_epi.py)):

- `temporal_bucket`: MORNING, AFTERNOON, EVENING, NIGHT
- `day_of_week`: Monday-Sunday
- `primary_location`: Location name
- `participants_json`: JSON array of entity names

**References**:

- GAP Section 4.2: [Template-Based Generation](../architecture/gaps/GAP_001_CROSS_LAYER_VECTOR_LINKING.md#42-template-based-generation)
- GAP Section 4.4: [TextRank Extractive Summarization](../architecture/gaps/GAP_001_CROSS_LAYER_VECTOR_LINKING.md#44-textrank-extractive-summarization)
- R7 Deep Dive §8: [EpisodicLayerWriter](../pipelines/R7_TRUTH_WRITER_DEEP_DIVE.md#layer-writers)
- Schema: [0027_st_epi.py](../../k0/db/alembic/versions/0027_st_epi.py)

**Acceptance Criteria**:

- [ ] Template header generation from structured fields
- [ ] TextRank summarization for >5 source texts
- [ ] Smart concatenation for ≤3 source texts
- [ ] Handles missing fields gracefully
- [ ] Unit tests with sample episodes

---

### Issue 2.3: Implement SemanticTextGenerator

**Priority**: P0
**Effort**: 2 hours

**Description**:
Generate embedding text for `st_sem` semantic patterns using pattern type + name + description.

**Files to Create**:

- `k0/modules/consolidation/algorithms/text_generators/semantic.py` (NEW)

**Generation Logic**:

```python
def generate(self, record_data: Dict, source_texts: List[str]) -> GeneratedText:
    """
    Pattern embedding text based on pattern_type.

    ROUTINE: "{pattern_name} happens {temporal_pattern}"
    PREFERENCE: "{actor} likes/dislikes {value} ({domain})"
    THEME: "Theme: {pattern_name} (observed {count} times)"
    """
```

**Template Fields** (from [0028_st_sem.py](../../k0/db/alembic/versions/0028_st_sem.py)):

- `pattern_type`: ROUTINE, PREFERENCE, THEME, RELATIONSHIP, GOAL, VALUE
- `pattern_name`: Human-readable name
- `pattern_description`: Longer description (often NULL!)
- `actor_id`: Whose pattern
- `temporal_pattern_json`: Frequency/timing info

**References**:

- GAP Section 4.2: Template for patterns
- GAP Pain Point 4: `pattern_description` is often NULL
- Schema: [0028_st_sem.py](../../k0/db/alembic/versions/0028_st_sem.py)
- Writer: [semantic.py](../../k0/modules/consolidation/truth_writer/layers/semantic.py)

**Acceptance Criteria**:

- [ ] Per-type template generation
- [ ] Handles NULL `pattern_description`
- [ ] Falls back to `pattern_name` if needed
- [ ] Unit tests for each pattern type

---

### Issue 2.4: Implement ProceduralTextGenerator

**Priority**: P0
**Effort**: 2 hours

**Description**:
Generate embedding text for `st_procedural` habits/routines by flattening action sequences.

**Files to Create**:

- `k0/modules/consolidation/algorithms/text_generators/procedural.py` (NEW)

**Generation Logic**:

```python
def generate(self, record_data: Dict, source_texts: List[str]) -> GeneratedText:
    """
    Routine embedding text = name + first 3 actions.

    Template: "{routine_name}: {action1}, {action2}, {action3}, and {N} more steps"
    Example: "Morning coffee routine: wake up, grind beans, brew espresso"
    """
```

**Template Fields** (from [0029_st_procedural.py](../../k0/db/alembic/versions/0029_st_procedural.py)):

- `routine_name`: Human-readable name
- `routine_category`: MORNING, EXERCISE, etc.
- `action_sequence_json`: JSON array of action steps
- `temporal_anchor`: Time of day (e.g., "07:30")
- `frequency`: DAILY, WEEKLY, MONTHLY

**References**:

- GAP Section 4.2: Template for routines
- Schema: [0029_st_procedural.py](../../k0/db/alembic/versions/0029_st_procedural.py)

**Acceptance Criteria**:

- [ ] Flattens action_sequence_json to text
- [ ] Limits to first 3 actions + count
- [ ] Includes temporal info if available
- [ ] Unit tests

---

### Issue 2.5: Implement SocialTextGenerator

**Priority**: P0
**Effort**: 2 hours

**Description**:
Generate embedding text for `st_social` relationships using actor names and relationship type.

**Files to Create**:

- `k0/modules/consolidation/algorithms/text_generators/social.py` (NEW)

**Generation Logic**:

```python
def generate(self, record_data: Dict, source_texts: List[str]) -> GeneratedText:
    """
    Relationship embedding text from structured fields.

    Template: "{actor_a} is {relationship_type} with {actor_b} ({label}) - {closeness}"
    Example: "User is family with Sarah (Mom) - close relationship"
    """
```

**Template Fields** (from [0030_st_social.py](../../k0/db/alembic/versions/0030_st_social.py)):

- `actor_a_id`, `actor_b_id`: Entity IDs
- `relationship_type`: FAMILY, FRIEND, COLLEAGUE
- `relationship_subtype`: SPOUSE, SIBLING, PARENT
- `relationship_label`: Custom label
- `relationship_strength`: 0.0-1.0

**Entity Resolution**:
Must resolve `actor_a_id` → human-readable name via `st_kg_dom.canonical_name`.

**References**:

- GAP Section 4.2: Template for relationships
- Schema: [0030_st_social.py](../../k0/db/alembic/versions/0030_st_social.py)

**Acceptance Criteria**:

- [ ] Resolves entity IDs to names
- [ ] Describes relationship strength qualitatively
- [ ] Unit tests

---

### Issue 2.6: Implement ProspectiveTextGenerator

**Priority**: P0
**Effort**: 1 hour

**Description**:
Generate embedding text for `st_prospective` intentions/goals. This layer already has `intention_description` so mostly pass-through.

**Files to Create**:

- `k0/modules/consolidation/algorithms/text_generators/prospective.py` (NEW)

**Generation Logic**:

```python
def generate(self, record_data: Dict, source_texts: List[str]) -> GeneratedText:
    """
    Intention embedding text = type + description + context.

    Template: "{intention_type}: {intention_description} (triggered by: {target_context}) by {date}"
    Example: "GOAL: Visit mom for Mother's Day (triggered by: calendar reminder) by 2025-05-11"
    """
```

**Template Fields** (from [0031_st_prospective.py](../../k0/db/alembic/versions/0031_st_prospective.py)):

- `intention_type`: GOAL, PLAN, REMINDER, COMMITMENT, WISH
- `intention_description`: The actual intention text ✅
- `target_context`: Triggering context
- `target_date`: Target completion date

**References**:

- GAP Section 4.2: Template for intentions
- Schema: [0031_st_prospective.py](../../k0/db/alembic/versions/0031_st_prospective.py)

**Acceptance Criteria**:

- [ ] Uses `intention_description` as base
- [ ] Adds context and date if present
- [ ] Unit tests

---

### Issue 2.7: Implement KGEntityTextGenerator

**Priority**: P0
**Effort**: 2 hours

**Description**:
Generate embedding text for `st_kg_dom` entities by creating a descriptive sentence from attributes.

**Files to Create**:

- `k0/modules/consolidation/algorithms/text_generators/kg_entity.py` (NEW)

**Generation Logic**:

```python
def generate(self, record_data: Dict, source_texts: List[str]) -> GeneratedText:
    """
    Entity embedding text = name + type + aliases + key attributes.

    Template: "{canonical_name} ({entity_type}) also known as {aliases} [{key_attrs}]"
    Example: "Thai Palace (restaurant) also known as TP [cuisine: Thai, location: Market St]"
    """
```

**Template Fields** (from [0032_st_kg_dom.py](../../k0/db/alembic/versions/0032_st_kg_dom.py)):

- `canonical_name`: Primary display name
- `entity_type`: PERSON, PLACE, ORG, THING, EVENT
- `entity_subtype`: More specific type
- `aliases_json`: Alternative names
- `attributes_json`: Structured attributes

**References**:

- GAP Section 3.4: Description-based approach for entities
- GAP Section 4.2: Template for entities
- Schema: [0032_st_kg_dom.py](../../k0/db/alembic/versions/0032_st_kg_dom.py)

**Acceptance Criteria**:

- [ ] Parses `aliases_json` and `attributes_json`
- [ ] Generates descriptive sentence
- [ ] Unit tests

---

### Issue 2.8: Create TextRank Helper Module

**Priority**: P0
**Effort**: 2 hours

**Description**:
Implement TextRank extractive summarization for episodes with many source texts.

**Files to Create**:

- `k0/modules/consolidation/algorithms/text_generators/textrank.py` (NEW)

**Algorithm** (from GAP Section 4.4):

```python
def textrank_summarize(texts: List[str], num_sentences: int = 3) -> str:
    """
    TextRank-based extractive summarization.

    1. Vectorize all sentences with TF-IDF
    2. Build similarity graph
    3. PageRank-style scoring
    4. Select top sentences (preserve temporal order)
    """
```

**Dependencies**:

- `scikit-learn` for TfidfVectorizer
- `numpy` for matrix operations

**References**:

- GAP Section 4.4: [TextRank Extractive Summarization](../architecture/gaps/GAP_001_CROSS_LAYER_VECTOR_LINKING.md#44-textrank-extractive-summarization)
- Paper: Mihalcea & Tarau (2004) - TextRank

**Acceptance Criteria**:

- [ ] TF-IDF vectorization
- [ ] Cosine similarity graph
- [ ] PageRank scoring
- [ ] Returns top N sentences in original order
- [ ] Unit tests with sample texts

---

### Issue 2.9: Create Generator Registry & Factory

**Priority**: P0
**Effort**: 1 hour

**Description**:
Create a registry to get the appropriate generator for each layer.

**Files to Create**:

- `k0/modules/consolidation/algorithms/text_generators/__init__.py` (NEW)

**Code Structure**:

```python
from typing import Dict
from .episodic import EpisodicTextGenerator
from .semantic import SemanticTextGenerator
from .procedural import ProceduralTextGenerator
from .social import SocialTextGenerator
from .prospective import ProspectiveTextGenerator
from .kg_entity import KGEntityTextGenerator

GENERATOR_REGISTRY: Dict[str, type] = {
    "st_epi": EpisodicTextGenerator,
    "st_sem": SemanticTextGenerator,
    "st_procedural": ProceduralTextGenerator,
    "st_social": SocialTextGenerator,
    "st_prospective": ProspectiveTextGenerator,
    "st_kg_dom": KGEntityTextGenerator,
}

def get_generator(layer: str) -> EmbeddingTextGenerator:
    """Get text generator for a layer."""
    cls = GENERATOR_REGISTRY.get(layer)
    if cls is None:
        raise ValueError(f"No text generator for layer: {layer}")
    return cls()
```

**References**:

- GAP Section 4.7: [Per-Layer Strategy Recommendation](../architecture/gaps/GAP_001_CROSS_LAYER_VECTOR_LINKING.md#47-per-layer-strategy-recommendation)

**Acceptance Criteria**:

- [ ] Registry maps layer → generator class
- [ ] Factory function returns instance
- [ ] All 6 generators registered

---

### Issue 2.10: Unit Tests for All Generators

**Priority**: P1
**Effort**: 3 hours

**Description**:
Comprehensive unit tests for all text generators.

**Files to Create**:

- `tests/k0/modules/consolidation/algorithms/text_generators/test_episodic.py`
- `tests/k0/modules/consolidation/algorithms/text_generators/test_semantic.py`
- `tests/k0/modules/consolidation/algorithms/text_generators/test_procedural.py`
- `tests/k0/modules/consolidation/algorithms/text_generators/test_social.py`
- `tests/k0/modules/consolidation/algorithms/text_generators/test_prospective.py`
- `tests/k0/modules/consolidation/algorithms/text_generators/test_kg_entity.py`
- `tests/k0/modules/consolidation/algorithms/text_generators/test_textrank.py`

**Test Cases Per Generator**:

1. Happy path with all fields populated
2. Missing optional fields (graceful degradation)
3. Empty source_texts
4. Large source_texts (>10) triggers TextRank
5. Edge cases (empty strings, None values)

**Acceptance Criteria**:

- [ ] All generators have test coverage
- [ ] Edge cases handled
- [ ] Tests pass in CI

---

## Verification Checklist

After completing all issues:

- [ ] All 6 layer generators created
- [ ] TextRank helper module created
- [ ] Generator registry functional
- [ ] All unit tests pass
- [ ] Generators handle missing data gracefully
- [ ] Generated text is suitable for UltraBERT embedding

---

## Files Created Summary

| File | Action | Issue |
|------|--------|-------|
| `k0/modules/consolidation/algorithms/embedding_text_generator.py` | CREATE | 2.1 |
| `k0/modules/consolidation/algorithms/text_generators/__init__.py` | CREATE | 2.9 |
| `k0/modules/consolidation/algorithms/text_generators/episodic.py` | CREATE | 2.2 |
| `k0/modules/consolidation/algorithms/text_generators/semantic.py` | CREATE | 2.3 |
| `k0/modules/consolidation/algorithms/text_generators/procedural.py` | CREATE | 2.4 |
| `k0/modules/consolidation/algorithms/text_generators/social.py` | CREATE | 2.5 |
| `k0/modules/consolidation/algorithms/text_generators/prospective.py` | CREATE | 2.6 |
| `k0/modules/consolidation/algorithms/text_generators/kg_entity.py` | CREATE | 2.7 |
| `k0/modules/consolidation/algorithms/text_generators/textrank.py` | CREATE | 2.8 |
| `tests/.../text_generators/*.py` | CREATE | 2.10 |

---

## Next Milestone

After Milestone 2 is complete, proceed to:

- **Milestone 3: R7 Writer Updates** — Integrate generators into truth layer writers
