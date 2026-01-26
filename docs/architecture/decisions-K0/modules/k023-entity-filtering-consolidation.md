---
adr_number: 'K023'
affected_layers:
- P03
- modules
affected_modules:
- consolidation/algorithms/entity_extractor
- pipelines/p03/phases/r4_kg_consolidator
authors:
- K0 Architecture Team
concerns:
- architecture
- maintainability
- separation-of-concerns
- code-duplication
date_created: '2025-01-19'
date_updated: '2025-01-19'
implementation_date: null
implementation_phase: M5
implementation_status: PROPOSED
propagation:
  affected_adrs:
  - k010-p03-consolidation-architecture
  affected_contracts:
  - k0/contracts/modules/entity_extractor.yaml
  affected_tests:
  - tests/k0/modules/consolidation/test_entity_extractor.py
  - tests/k0/pipelines/p03/test_r4_kg_consolidator.py
  triggers:
  - Entity filtering logic changes
  - NER processing updates
related_adrs:
- k010-p03-consolidation-architecture
- k003-inline-embedding-ultrabert
related_contracts:
- k0/contracts/pipelines/p03.yaml
related_diagrams:
- architecture_diagrams/k0/p03_consolidation.mmd
research_citations: []
status: PROPOSED
superseded_by: []
supersedes: []
title: Entity Filtering Consolidation - Single Source of Truth
---

# ADR-K023: Entity Filtering Consolidation - Single Source of Truth

**Status**: Proposed

**Date**: 2025-01-19

**Authors**: K0 Architecture Team

## Context

### Current Problem

Entity filtering logic for R4 KG consolidation is **scattered across two files** with duplicated and inconsistent implementations:

1. **r4_kg_consolidator.py** (2950 lines) - Phase orchestrator containing inline algorithm logic:
   - Lowercase entity filter (line ~927)
   - Short entity filter (line ~933)
   - Time fragment filter (line ~937)
   - Verb suffix filter (line ~943)
   - Garbage word check using `GARBAGE_ENTITY_WORDS` (line ~948)
   - Word boundary validation (line ~955)
   - ORG to LOCATION reclassification (line ~962)

2. **entity_extractor.py** (1060 lines) - Algorithm module with its own filtering:
   - `GARBAGE_ENTITY_WORDS` frozenset (~150 hardcoded words)
   - `LOCATION_AFFORDANCES` frozenset (~80 keywords)
   - `_is_valid_ner_family_entity()` with hardcoded keyword validation
   - `is_complete_word()` word boundary check
   - `_has_location_affordance()` for type reclassification

### Architectural Violations

| Violation | Description |
|-----------|-------------|
| **Separation of Concerns** | R4 phase contains algorithm logic that should be in modules |
| **Code Duplication** | Same filtering concepts implemented in two places |
| **Single Responsibility** | R4 phase does orchestration AND entity processing |
| **Maintainability** | Changes require updating multiple files |
| **Testability** | Filtering logic in phase file is harder to unit test |

### Filter Location Matrix (Current State)

| Filter Type | In R4 | In entity_extractor | Problem |
|-------------|-------|---------------------|---------|
| Lowercase check | Yes (line 927) | No | Logic in wrong file |
| Short entity check | Yes (line 933) | No | Logic in wrong file |
| Time fragment | Yes (line 937) | No | Logic in wrong file |
| Verb suffix | Yes (line 943) | No | Logic in wrong file |
| Garbage words | Yes (line 948) | Yes (frozenset) | Duplicated |
| Word boundary | Yes (line 955) | Yes (method) | Duplicated |
| ORG->LOC reclassify | Yes (line 962) | Yes (method) | Duplicated |
| Keyword validation | No | Yes (method) | Should be unified |

## Decision

### Consolidate All Entity Filtering into entity_extractor.py

**R4 phase will call a single method**: `entity_extractor.filter_and_normalize(raw_entities, source_text)` that returns clean, validated entities.

### New Architecture

```
R4 Phase (Orchestration Only)
├── Extract raw entities from NER JSON
├── Call entity_extractor.filter_and_normalize()  ← ALL filtering here
├── Call disambiguator.resolve()
├── Call merger.merge_duplicates()
└── Populate envelope outputs

entity_extractor.py (Single Source of Truth)
├── extract_from_ultrabert()
├── filter_and_normalize()  ← NEW: consolidated filtering
│   ├── _filter_lowercase_single_words()
│   ├── _filter_short_entities()
│   ├── _filter_time_fragments()
│   ├── _filter_verb_suffixes()
│   ├── _filter_garbage_words()
│   ├── _validate_word_boundaries()
│   ├── _reclassify_org_to_location()
│   └── _validate_ner_family_entity()
├── normalize_name()
└── is_complete_word()
```

### Filter Method Signature

```python
def filter_and_normalize(
    self,
    raw_entities: list[dict],
    source_text: str,
    source_head: str,
    min_confidence: float = 0.5,
) -> list[ExtractedEntity]:
    """
    Apply all entity filters and return validated entities.

    Filters applied in order:
    1. Confidence threshold (from NER model)
    2. Text normalization
    3. Lowercase single-word rejection
    4. Short entity rejection (< 2 chars)
    5. Time fragment rejection
    6. Verb suffix rejection
    7. Garbage word rejection
    8. Word boundary validation
    9. Type reclassification (ORG -> LOCATION)
    10. NER family keyword validation

    Returns:
        Filtered, normalized ExtractedEntity list
    """
```

### R4 Simplified Loop

```python
# BEFORE: 200+ lines of inline filtering
for ent_data in entities_list:
    # ... 50 lines of inline filtering ...

# AFTER: Single method call
entities = self._entity_extractor.filter_and_normalize(
    raw_entities=entities_list,
    source_text=event.content_text or "",
    source_head=source_head,
    min_confidence=self.config.min_entity_priority,
)
```

## Consequences

### Positive

- **Single Source of Truth**: All filtering logic in one file
- **Testability**: Filter logic can be unit tested independently
- **Maintainability**: One place to update when filters change
- **Readability**: R4 phase becomes clear orchestration code
- **Consistency**: Same filters applied everywhere

### Negative

- **Migration Effort**: ~2-4 hours of refactoring
- **Test Updates**: Existing R4 tests may need adjustment
- **Breaking Change**: If external code depends on R4 internals (unlikely)

### Risks

| Risk | Mitigation |
|------|------------|
| Behavior change during refactor | Run before/after comparison tests |
| Performance regression | Filter order optimized for early rejection |
| Missing edge cases | Existing test coverage + new unit tests |

## Alternatives Considered

### Alternative 1: Keep Filters in R4, Remove from entity_extractor

- **Rejected**: Violates separation of concerns - phases should orchestrate, not implement algorithms

### Alternative 2: Create New filter_service.py Module

- **Rejected**: Over-engineering - entity_extractor already exists and is the right home

### Alternative 3: Leave As-Is (Status Quo)

- **Rejected**: Technical debt accumulates, maintenance burden increases

## Implementation Notes

### Phase 1: Move Filters to entity_extractor

1. Create `filter_and_normalize()` method in entity_extractor.py
2. Move each R4 filter to private methods
3. Update R4 to call consolidated method
4. Verify behavior with existing tests

### Phase 2: Clean Up R4

1. Remove inline filtering code from R4
2. Simplify entity extraction loop
3. Update R4 tests to use mocked entity_extractor

### Phase 3: Add Filter Unit Tests

1. Add unit tests for each filter method
2. Test filter order and early rejection
3. Test edge cases (empty text, unicode, etc.)

### Testing Strategy

```bash
# Before refactor: capture baseline
python -c "from tests.fixtures import run_r4_test; run_r4_test()" > before.json

# After refactor: verify identical output
python -c "from tests.fixtures import run_r4_test; run_r4_test()" > after.json

# Diff should be empty
diff before.json after.json
```

## Related

- Epic: ENTITY-FILTER-CONSOLIDATION
- Issues: EFC-001 through EFC-006
- Pipeline: P03 KG Consolidation
- Module: consolidation/algorithms/entity_extractor
