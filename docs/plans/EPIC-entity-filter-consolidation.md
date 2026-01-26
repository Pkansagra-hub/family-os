# Epic: Entity Filtering Consolidation (EFC)

**Epic ID**: ENTITY-FILTER-CONSOLIDATION
**Status**: IMPLEMENTED
**Created**: 2025-01-19
**Completed**: 2025-01-19
**ADR**: [K023 - Entity Filtering Consolidation](../architecture/decisions-K0/modules/k023-entity-filtering-consolidation.md)
**Priority**: P1 (Technical Debt - Blocking Future Development)
**Estimated Effort**: 6-8 hours
**Actual Effort**: ~2 hours

---

## Problem Statement

Entity filtering logic is **scattered across two files** with duplicated implementations:

| File | Lines | Problem |
|------|-------|---------|
| `r4_kg_consolidator.py` | 2950 | Contains 200+ lines of inline entity filtering (lines 860-1000) |
| `entity_extractor.py` | 1060 | Has its own filtering with hardcoded word lists |

**Result**: Same filtering concepts implemented twice, violating DRY and separation of concerns.

---

## Success Criteria

- [x] ALL entity filtering logic lives in `entity_extractor.py`
- [x] R4 phase calls `filter_and_normalize()` instead of inline filtering
- [ ] Unit tests exist for each filter method
- [ ] Existing R4 integration tests still pass
- [x] No duplicate filter logic exists

---

## Milestone Summary

| Milestone | Title | Issues | Status |
|-----------|-------|--------|--------|
| M1 | Create Consolidated Filter API | 2 | DONE |
| M2 | Migrate R4 Inline Filters | 3 | DONE |
| M3 | Testing & Validation | 1 | PENDING |

---

## Milestone 1: Create Consolidated Filter API

**Goal**: Add `filter_and_normalize()` method to entity_extractor.py with all filter logic.

### Issue EFC-001: Create filter_and_normalize() Method

| Field | Value |
|-------|-------|
| **Title** | Create consolidated filter_and_normalize() method in entity_extractor |
| **Priority** | P1 |
| **Estimate** | 2h |
| **Status** | NOT STARTED |
| **Assignee** | - |
| **File** | `k0/modules/consolidation/algorithms/entity_extractor.py` |

**Description**:

Create a new public method that consolidates ALL entity filtering:

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
    """
```

**Acceptance Criteria**:
- [ ] Method exists with correct signature
- [ ] All filters from R4 are implemented as private methods
- [ ] Logging shows which filter rejected each entity
- [ ] Returns `list[ExtractedEntity]` matching R4's current output format

---

### Issue EFC-002: Refactor Existing Filter Methods

| Field | Value |
|-------|-------|
| **Title** | Refactor existing filter methods to private API |
| **Priority** | P1 |
| **Estimate** | 1h |
| **Status** | NOT STARTED |
| **Assignee** | - |
| **File** | `k0/modules/consolidation/algorithms/entity_extractor.py` |

**Description**:

Refactor existing methods to be called from `filter_and_normalize()`:

| Current Method | New Private Method |
|----------------|-------------------|
| `is_complete_word()` | `_validate_word_boundaries()` |
| `_has_location_affordance()` | `_reclassify_org_to_location()` |
| `_is_valid_ner_family_entity()` | Keep, called from filter pipeline |

Add NEW private methods for R4 inline filters:
- `_filter_lowercase_single_words(text: str) -> bool`
- `_filter_short_entities(normalized: str) -> bool`
- `_filter_time_fragments(normalized: str) -> bool`
- `_filter_verb_suffixes(normalized: str) -> bool`
- `_filter_garbage_words(normalized: str) -> bool`

**Acceptance Criteria**:
- [ ] All filters are private methods with consistent naming
- [ ] Each filter returns `bool` (True = keep, False = reject)
- [ ] Filters log rejection reason at DEBUG level

---

## Milestone 2: Migrate R4 Inline Filters

**Goal**: Remove inline filtering from R4, call entity_extractor instead.

### Issue EFC-003: Extract R4 Filter Constants

| Field | Value |
|-------|-------|
| **Title** | Move R4 filter patterns to entity_extractor constants |
| **Priority** | P1 |
| **Estimate** | 30m |
| **Status** | NOT STARTED |
| **Assignee** | - |
| **Files** | `r4_kg_consolidator.py`, `entity_extractor.py` |

**Description**:

R4 has inline regex patterns that should be constants in entity_extractor:

```python
# R4 line 937 - move to entity_extractor
TIME_FRAGMENT_PATTERN = re.compile(r"^\d{1,2}(?:am|pm|AM|PM)$")

# R4 line 943 - move to entity_extractor
VERB_SUFFIX_PATTERN = re.compile(r"^[a-z]+(?:ed|ing|ized|ised)$")
```

**Acceptance Criteria**:
- [ ] Patterns are class-level constants in entity_extractor
- [ ] Patterns are compiled once (not per-call)
- [ ] R4 no longer has inline regex patterns

---

### Issue EFC-004: Replace R4 Inline Filters with Method Call

| Field | Value |
|-------|-------|
| **Title** | Replace R4 inline filtering loop with filter_and_normalize() call |
| **Priority** | P1 |
| **Estimate** | 1.5h |
| **Status** | NOT STARTED |
| **Assignee** | - |
| **File** | `k0/pipelines/p03/phases/r4_kg_consolidator.py` |

**Description**:

Replace R4 lines ~860-1000 (inline filtering) with:

```python
# BEFORE: ~140 lines of inline filtering
for ent_data in entities_list:
    # ... inline filters ...

# AFTER: Single method call
filtered_entities = self._entity_extractor.filter_and_normalize(
    raw_entities=entities_list,
    source_text=event.content_text or "",
    source_head=source_head,
    min_confidence=self.config.min_entity_priority,
)
for entity in filtered_entities:
    entities.append(entity)
```

**Acceptance Criteria**:
- [ ] R4 entity extraction loop uses filter_and_normalize()
- [ ] No inline filter logic remains in R4
- [ ] R4 still handles span deduplication (family vs general)
- [ ] Existing R4 tests pass without modification

---

### Issue EFC-005: Remove Dead Code from R4

| Field | Value |
|-------|-------|
| **Title** | Remove unused imports and dead filter code from R4 |
| **Priority** | P2 |
| **Estimate** | 30m |
| **Status** | NOT STARTED |
| **Assignee** | - |
| **File** | `k0/pipelines/p03/phases/r4_kg_consolidator.py` |

**Description**:

After EFC-004, clean up R4:

1. Remove unused `re` import if no longer needed
2. Remove any commented-out filter code
3. Remove unused local variables from filtering
4. Update module docstring to reflect orchestration-only role

**Acceptance Criteria**:
- [ ] No dead code related to filtering
- [ ] Imports are minimal
- [ ] Docstring reflects current architecture

---

## Milestone 3: Testing & Validation

**Goal**: Ensure refactoring doesn't change behavior.

### Issue EFC-006: Add Unit Tests for Filter Methods

| Field | Value |
|-------|-------|
| **Title** | Add unit tests for entity_extractor filter methods |
| **Priority** | P1 |
| **Estimate** | 1.5h |
| **Status** | NOT STARTED |
| **Assignee** | - |
| **File** | `tests/k0/modules/consolidation/test_entity_extractor.py` |

**Description**:

Add unit tests for each filter method:

```python
class TestEntityFilters:
    def test_filter_lowercase_single_words(self):
        """Reject 'afternoon' but accept 'Afternoon' and 'good afternoon'"""

    def test_filter_short_entities(self):
        """Reject single-char entities"""

    def test_filter_time_fragments(self):
        """Reject '10am', '3pm' but accept 'morning'"""

    def test_filter_verb_suffixes(self):
        """Reject 'learned', 'working' but accept 'Springfield'"""

    def test_filter_garbage_words(self):
        """Reject 'the', 'afternoon', 'email' etc."""

    def test_word_boundary_validation(self):
        """Reject 'Fur' from 'Fur Elise' (sub-word fragment)"""

    def test_org_to_location_reclassify(self):
        """ORG 'Lincoln School' -> LOCATION"""

    def test_filter_and_normalize_integration(self):
        """Full pipeline test with real UltraBERT output"""
```

**Acceptance Criteria**:
- [ ] Each filter has at least 2 test cases (accept + reject)
- [ ] Integration test covers full pipeline
- [ ] Edge cases: empty text, unicode, very long entities
- [ ] Tests pass in CI

---

## Implementation Order

```
EFC-001 → EFC-002 → EFC-003 → EFC-004 → EFC-005 → EFC-006
   │         │         │         │         │         │
   └─────────┴─────────┴─────────┴─────────┴─────────┘
                           │
                     All sequential
```

**Rationale**: Each issue depends on the previous one. Cannot parallelize.

---

## Files Changed

| File | Change Type | Issues |
|------|-------------|--------|
| `k0/modules/consolidation/algorithms/entity_extractor.py` | MODIFY | EFC-001, EFC-002, EFC-003 |
| `k0/pipelines/p03/phases/r4_kg_consolidator.py` | MODIFY | EFC-004, EFC-005 |
| `tests/k0/modules/consolidation/test_entity_extractor.py` | MODIFY | EFC-006 |

---

## Rollback Plan

If issues arise after deployment:

1. Revert `entity_extractor.py` to previous version
2. Revert `r4_kg_consolidator.py` to previous version
3. Both files are stateless - no data migration needed

---

## Related

- **ADR**: [K023 - Entity Filtering Consolidation](../architecture/decisions-K0/modules/k023-entity-filtering-consolidation.md)
- **Pipeline Dossier**: [P03 Write Dossier](../pipelines/P03_write_dossier.md)
- **Module**: `k0/modules/consolidation/algorithms/entity_extractor.py`

Read [](file:///d%3A/familyos/k0/pipelines/p03/phases/r4_kg_consolidator.py#1-1), lines 1 to 200

Read [](file:///d%3A/familyos/k0/modules/consolidation/algorithms/entity_extractor.py#1-1), lines 1 to 400

Read [](file:///d%3A/familyos/k0/pipelines/p03/phases/r4_kg_consolidator.py#800-800), lines 800 to 1000

Read [](file:///d%3A/familyos/k0/modules/consolidation/algorithms/entity_extractor.py#400-400), lines 400 to 800

Summarized conversation historyNow I can see the violations clearly. Let me read more of R4 to see the full extent of inline algorithm logic:

Read [](file:///d%3A/familyos/k0/pipelines/p03/phases/r4_kg_consolidator.py#1-1), lines 1 to 100

Read [](file:///d%3A/familyos/k0/modules/consolidation/algorithms/entity_extractor.py#1-1), lines 1 to 200

Now I have the complete picture. Here's the analysis:

---

## Architecture Violations Analysis

### 🚨 **VIOLATION 1: R4 Phase Contains Inline Algorithm Logic**

r4_kg_consolidator.py is **2950 lines** - a phase orchestrator should be ~200-300 lines max.

**Lines 860-1000** contain inline entity filtering that should be in algorithm modules:

```
# PRODUCTION ENTITY FILTER: Algorithmic approach, not manual lists
# 1. Reject single words that start lowercase (line ~927)
# 2. Reject short entities < 2 chars (line ~933)
# 3. Filter time fragments (line ~937)
# 4. Reject verb suffix entities (line ~943)
# 5. Reject garbage words using GARBAGE_ENTITY_WORDS (line ~948)
# 6. Word boundary validation (line ~955)
# 7. Reclassify ORG → LOCATION (line ~962)
```

This is **algorithm logic** living inside a phase orchestrator. The phase should call `entity_extractor.filter_entities(raw_entities)` and get clean entities back - not implement its own filtering pipeline.

---

### 🚨 **VIOLATION 2: Hardcoded Rule-Based Word Lists**

entity_extractor.py has **massive hardcoded frozensets**:

| Constant | Size | Problem |
|----------|------|---------|
| `GARBAGE_ENTITY_WORDS` | ~150 words | Hardcoded English words |
| `LOCATION_AFFORDANCES` | ~80 words | Hardcoded location keywords |
| `NICKNAME_MAP` | ~20 entries | Hardcoded nickname mappings |
| `milestone_keywords` | ~18 keywords | Hardcoded in `_is_valid_ner_family_entity()` |
| `heirloom_keywords` | ~25 keywords | Hardcoded in `_is_valid_ner_family_entity()` |
| `pet_keywords` | ~20 keywords | Hardcoded in `_is_valid_ner_family_entity()` |

**Why this breaks for other users:**

1. **Non-English speakers**: "the", "a", "our" are in GARBAGE but "el", "la", "notre" aren't
2. **Names that match common words**: "Will", "Faith", "Hope", "Joy" are valid names but may match garbage words
3. **Domain-specific**: "manager", "email", "afternoon" are garbage for YOUR usage but "Manager Williams" or "Morning Star" could be valid
4. **Cultural nicknames**: "Nana" means grandmother in US, but it's a common given name in other cultures

---

### 🚨 **VIOLATION 3: Duplicated Logic Between Phase and Module**

R4 and entity_extractor **both** implement entity filtering:

| Logic | In R4 (lines) | In entity_extractor |
|-------|---------------|---------------------|
| Lowercase filter | 926-928 | Not present |
| Short entity filter | 932-935 | Not present |
| Time fragment filter | 937-940 | Not present |
| Verb suffix filter | 943-948 | Not present |
| Garbage word check | 950-953 | Line 200-350 GARBAGE_ENTITY_WORDS |
| Word boundary validation | 955-960 | `is_complete_word()` method |
| ORG→LOCATION reclassify | 962-966 | `_has_location_affordance()` method |
| Keyword validation | Not present | `_is_valid_ner_family_entity()` |

**This is architectural chaos** - filtering logic scattered across 2 files, 1000+ lines apart.

---

### 🛠️ **Proper Architecture Should Be:**

```
┌────────────────────────────────────────────────────────────────┐
│  R4 Phase Orchestrator (~200 lines)                            │
│  ─────────────────────────────────────────────────────────────  │
│  1. Call entity_extractor.extract_and_filter(events)           │
│  2. Call disambiguator.resolve(entities)                       │
│  3. Call merger.merge_duplicates(entities)                     │
│  4. Call hebbian_learner.discover_relations()                  │
│  5. Populate envelope outputs                                  │
└────────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌────────────────────────────────────────────────────────────────┐
│  entity_extractor.py - ALL filtering logic here                │
│  ─────────────────────────────────────────────────────────────  │
│  - extract_from_ultrabert()                                    │
│  - filter_entities() ← consolidate ALL filter logic            │
│  - normalize_name()                                            │
│  - is_complete_word()                                          │
└────────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌────────────────────────────────────────────────────────────────┐
│  Learned/Adaptive Filtering (NOT hardcoded)                    │
│  ─────────────────────────────────────────────────────────────  │
│  - Confidence thresholds from UltraBERT (✅ fixed)             │
│  - Language-agnostic POS tagging                               │
│  - User feedback loop → learn good/bad entities                │
│  - Space-adaptive patterns (not global word lists)             │
└────────────────────────────────────────────────────────────────┘
```

---

### 📋 **Refactoring Required:**

1. **Move R4's inline filters to entity_extractor**:
   - Lowercase check
   - Short entity check
   - Time fragment check
   - Verb suffix check
   - All should be in `entity_extractor.filter_entities()`

2. **Replace hardcoded word lists with learned patterns**:
   - `GARBAGE_ENTITY_WORDS` → POS tagging (reject verbs, conjunctions, prepositions)
   - `milestone_keywords` → WordNet hypernym check ("is_event", "is_artifact")
   - `heirloom_keywords` → WordNet hypernym check ("is_physical_object")

3. **Add user feedback loop**:
   - Track entities user corrects (P06 gaps)
   - Learn space-specific patterns
   - Adaptive thresholds per entity type

4. **Shrink R4 to orchestration only**:
   - Target: 200-300 lines
   - Just method calls, no algorithm logic

---
