# K0 Affect Module - Implementation Plan (5-Gate Process)

**Status**: Planning Phase
**Start Date**: 2025-11-13
**Target Completion**: TBD
**Owner**: @K0-Architecture

---

## Overview

Complete end-to-end implementation of the K0 Affect Module following the **5-Gate Gated Workflow** as specified in `.github/copilot-instructions.md`.

**Module Type**: **Shared Library/Utility Module** (used by K0 services, not standalone deployment)

**Architecture Reference**: ADR-0012 (k003a-k003i)

**Consumer Services**:

- P02 Write Pipeline (event ingestion → affect annotation)
- Memory Steward (affect-aware memory consolidation)
- Policy Engine (P18 affect-based policy decisions)
- K1 Planner & Concierge (behavior mode adaptation)
- Workspace Service (household affect state)

**Performance Targets**:

- Tier-0 Classifier: <2ms P95
- Tier-1 Classifier: <60ms P95 (optional)
- Policy Banding: <5ms P95
- Total E2E: <70ms P95 (with Tier-1)

---

## 🚦 5-Gate Process Overview

Each component follows these gates:

1. **GATE 1: ADR Discovery & Validation** - Verify ADR exists, understand requirements
2. **GATE 2: Contract Discovery & Validation** - Create/validate JSON schemas, FlatBuffers
3. **GATE 3: Implementation with Contract Compliance** - Write production code
4. **GATE 4: Test Implementation** - Integration + unit tests
5. **GATE 5: Memory Documentation** - Document decisions, update diagrams

---

## Phase 1: Contracts & Storage Foundation (Week 1)

### 🎯 **Component 1.1: JSON Schema Contracts**

**Reference**: ADR-0012a (Affect Contracts & Storage Mapping)

#### GATE 2: Contract Discovery ✅

- [x] Added `k0/contracts/jsonschema/affect/modality_score.json` plus example payload under `k0/contracts/jsonschema/examples/affect/modality_score.json`.
- [x] Added `k0/contracts/jsonschema/affect/calibration_params.json` plus example payload under `k0/contracts/jsonschema/examples/affect/calibration_params.json`.
- [x] Updated `k0/contracts/VERSION` with new SHA256 entries and revalidated via `python k0/automation/lint_schemas.py` (0 errors).
  - SHA256: 0fd7a0386614fd2299331e735b26aad9545efe366641789e6fc6114a232cecf5

#### GATE 3: Implementation ✅

- [x] **Contract 2.2**: `affect_ema_state.json` schema
- [x] Built `k0/modules/affect/fusion/engine.py` implementing confidence-weighted late fusion, dual EMA smoothing (fast α configurable per calibration, slow α=0.1), calibration transforms, TTL-backed EMA cache, and calibration cache.
- [x] Added calibration update API + trend helper for downstream consumers; optional storage persistence hook ready for `AffectStorage` integration.
  - Optional P18 PolicyAction mapping (allowed_spaces, sharing_delay, rollup_half_life)

#### GATE 4: Test Implementation ✅

- [x] Added `tests/k0/modules/affect/fusion/test_engine.py` covering fusion math, EMA warm/cold updates, cache expiry, calibration bias/temp, trend detection, and invalid score handling.
- [x] Pytest: `python -m pytest tests/k0/modules/affect/fusion/test_engine.py -v` (6/6 passing).
  - SHA256: 1a91151ccc2c225545720c9ed2acd92f4462eb199fa3602932093e8d7480244e

- [x] **Contract 2.5**: `affect_summary.json` schema (for K1)
  - Lightweight K1 bridge contract with mood labels (calm, happy, excited, stressed, sad, frustrated)
  - Trend detection (improving/declining/stable)
  - Behavior mode suggestions (slow, gentle, quiet, wind_down, opportunity)
  - Optional household context
  - SHA256: 7154eb40c0aa3016fc931fbc0e7d5a7ff8219a3764cc401619ea5eac283fe054

- [x] **Contract 2.6**: `counterfactual_input.json` + `counterfactual_result.json` schemas
  - Input: action_type (share/notify/recall/suggest), content, recipients, current_affect_states
  - Result: per-recipient impact predictions (valence_delta, arousal_delta, predicted_band)
  - Safety rules: [PUSH_INTO_RED, AMPLIFY_DISTRESS, SPIKE_AROUSAL_DURING_CONFLICT, AROUSAL_OVERFLOW, PUSH_INTO_BLACK]
  - Blocking decisions with confidence scores
  - SHA256 (input): 44397ba7d809526957118a6002362f784ef33c7680c55e1b598b83d958e43fb7
  - SHA256 (result): 92a589451ae50c2f185b14efac22a5a084534f29259142d8d745a20a5e5434cd

- [x] Validate all schemas: `python k0/automation/lint_schemas.py --verbose` (0 errors, 4 warnings - orphaned schemas unrelated to affect)
- [x] Update `k0/contracts/VERSION` with new contract versions (v1.1.0, 2025-11-13)

#### GATE 3: Implementation ✅

- [x] Implement `k0/modules/affect/models.py` dataclasses to match schemas
  - AffectAnnotation (matches affect_annotation.json) - Pydantic with field validation
  - AffectEMAState (matches affect_ema_state.json) - Pydantic with field validation
  - BandingResult (matches banding_result.json) - Pydantic with field validation
  - HouseholdAffectState (matches household_affect_state.json) - Pydantic with nested models
  - AffectSummary (matches affect_summary.json) - Pydantic with field validation
  - CounterfactualInput (matches counterfactual_input.json) - Pydantic with nested models
  - CounterfactualResult (matches counterfactual_result.json) - Pydantic with nested models
- [x] Add JSON serialization/deserialization methods using Pydantic
  - All models inherit from `pydantic.BaseModel` with `.model_dump()`, `.model_dump_json()`, `.model_validate()`
  - JSON schema export via `.model_json_schema()`
- [x] Add Pydantic validators for range checks (valence [-1, 1], arousal [0, 1])
  - `valence: Field(..., ge=-1.0, le=1.0)` - enforced at validation
  - `arousal: Field(..., ge=0.0, le=1.0)` - enforced at validation
  - Custom validators for tags (unique, max 50 chars), rule_ids (pattern matching)
- [x] Add docstrings with ADR references (ADR-0012a/k003a)
  - All models include contract references and ADR links
  - Usage examples in `model_config` JSON schema extras
- [x] Added 8 Enum types for type safety: PolicyBand, MoodLabel, Trend, ActionType, Recommendation, SafetyRule, BehaviorMode
- [x] Added 7 nested models: HouseholdAggregates, ConflictDetails, FamilyMomentDetails, ContagionDetails, CounterfactualContent, RecipientImpact
- [x] Internal models: Relationship, LifecycleContext (Pydantic with validation)

#### GATE 4: Test Implementation ✅

- [x] `tests/k0/modules/affect/test_models.py`
  - **37 tests implemented, all passing (0.29s execution time)**
  - Schema validation tests (valid/invalid inputs)
    - AffectAnnotation: 9 tests (creation, valence range, arousal range, confidence, band enum, model_version pattern, tags validation, JSON/dict serialization)
    - AffectEMAState: 5 tests (creation, valence range, arousal range, n_observations, JSON serialization)
    - BandingResult: 4 tests (creation, rule_ids pattern, reasons validation, JSON serialization)
    - HouseholdAffectState: 5 tests (creation with nested models, aggregates validation, conflict details validation, optional fields, JSON serialization)
    - AffectSummary: 4 tests (creation, enum validation, behavior_modes list, JSON serialization)
    - Counterfactual models: 4 tests (input creation, result creation, recipient impact validation, JSON serialization)
    - Relationship: 2 tests (creation, relationship_type pattern validation)
    - LifecycleContext: 2 tests (creation, time_of_day pattern validation)
    - Schema export: 2 tests (AffectAnnotation schema export, all models schema export)
  - Serialization round-trip tests
    - All 7 contract models tested: JSON serialization (.model_dump_json() → .model_validate_json())
    - Dict serialization tested: .model_dump() → .model_validate()
  - Range validation tests (out-of-bounds valence/arousal)
    - Valence: [-1.0, 1.0] enforced (tested upper/lower bounds)
    - Arousal: [0.0, 1.0] enforced (tested upper/lower bounds)
    - Confidence: [0.0, 1.0] enforced
    - EMA states: Dual EMA ranges validated (v_fast, a_fast, v_slow, a_slow)
  - Enum validation tests
    - PolicyBand: BLACK/RED/AMBER/GREEN (invalid values rejected)
    - MoodLabel: calm/happy/excited/stressed/sad/frustrated
    - Trend: improving/declining/stable
    - ActionType: share/notify/recall/suggest
    - Recommendation: PROCEED/PROCEED_PARTIAL/DELAY/BLOCK_ALL
    - SafetyRule: 5 rules validated
    - BehaviorMode: slow/gentle/quiet/wind_down/opportunity
  - Custom validator tests
    - tags validator: uniqueness enforced, max 20 tags, max 50 chars per tag
    - rule_ids validator: pattern matching "^(BLACK|RED|AMBER|GREEN)_RULE_[0-9]+$"
    - relationship_type validator: 6 valid types (parent-child, partner, sibling, friend, caregiver-dependent, extended-family)
    - time_of_day validator: 4 valid periods (morning, afternoon, evening, night)
  - Nested model tests
    - HouseholdAggregates: 8 fields (valence_mean, valence_std, valence_min, valence_max, arousal_mean, arousal_std, arousal_min, arousal_max) - all validated
    - ConflictDetails: severity [0, 1], participants ≥ 2, duration_seconds ≥ 0
    - RecipientImpact: predicted_valence_delta [-2, 2], predicted_arousal_delta [-2, 2]
    - CounterfactualContent: nested in CounterfactualInput
  - Test execution: `python -m pytest tests/k0/modules/affect/test_models.py -v`
    - Result: 37/37 tests PASSED ✅
    - Execution time: 0.29s
    - No test failures, no import errors
    - **Code coverage: 98% (180 statements, 2 missed)**

  **Key Findings:**
  - Pydantic validation working correctly (range checks, pattern matching, custom validators)
  - JSON serialization/deserialization working (round-trip preserves data)
  - Enum type safety enforced (invalid values rejected at runtime)
  - Nested models validated recursively (HouseholdAffectState with 4 nested models)
  - Schema export working (all models export valid JSON schemas)
  - 2 uncovered lines: defensive empty list checks in custom validators (expected)

**Status**: GATE 4 COMPLETE ✅ — All model validation tests passing, 98% coverage

#### GATE 5: Memory Documentation

- [ ] Document contract decisions in memory
- [ ] Link to ADR-0012a
- [ ] Update contract changelog

**Estimated Time**: 2 days

---

### 🎯 **Component 1.2: Storage Integration**

**Reference**: ADR-0012a (Storage Mapping), P02 Write Pipeline Integration

**CRITICAL INSIGHT FROM P02:** The affect module does NOT need separate storage. P02 Write Pipeline writes affect analysis results directly to `st_hipp_store` (6 affect columns already exist). This component focuses on:

1. **Integration point with P02** - How affect module is called
2. **EMA state caching** - In-memory cache for fast EMA lookups (optional optimization)
3. **Public API** - Interface for P02 to call affect analysis

#### GATE 1: ADR Discovery ✅

- [x] Requirements CLARIFIED after P02 review:
  - ✅ st_hipp_store already has 6 affect columns (affect_valence, affect_arousal, affect_tags, affect_confidence, affect_model_version, affect_computed_at)
  - ✅ P02 writes affect results to st_hipp_store (no separate affect storage needed)
  - ⚠️ Optional: In-memory EMA cache for performance (can defer to Phase 2)

#### GATE 2: Contract Discovery ✅ _(Component 2.2)_

- [x] Verify st_hipp_store schema supports 6 affect columns
  - **VERIFIED**: Schema exists in `k0/contracts/sql/migrations/0006_phase1_core_memory_foundation.sql` (lines 365-370)
  - **VERIFIED**: P02 Write Pipeline documents field mapping (Section 4.2)

- [x] Define P02 integration contract
  - **Input**: `AffectAnnotation` (from k0/modules/affect/models.py)
  - **Output**: Dict with 6 fields for st_hipp_store insertion
  - **Call site**: P02 Step 7 (after redaction, before Hippocampus)

- [ ] OPTIONAL: Define cache key format: `(person_id, space_id) → AffectEMAState`
- [ ] OPTIONAL: Define TTL policy: 5 minutes, LRU eviction

**Status**: Core integration contract COMPLETE ✅, EMA cache DEFERRED (optional optimization)

#### GATE 3: Implementation

**Phase 1: P02 Integration (CRITICAL PATH)**

- [ ] Implement `k0/modules/affect/service.py` (public API for P02)
  - `analyze_text(text, context) → AffectAnnotation`
  - Convert AffectAnnotation → dict for st_hipp_store
  - Reference implementation: P02 Step 7 (line ~1089)

**Phase 2: Optional EMA Cache (DEFERRED)**

- [ ] OPTIONAL: Implement `k0/modules/affect/storage/ema_cache.py`
  - `get_ema_state()`: Read from in-memory cache
  - `update_ema_state()`: Update cache with TTL
  - `evict_stale_states()`: LRU eviction logic
- [ ] OPTIONAL: Integrate EMA cache with Tier-1 classifier for smoothing

**Note**: EMA cache can be deferred to Phase 2 (Classification Pipeline) when EMA smoothing is actually implemented.

#### GATE 4: Test Implementation

**Phase 1: P02 Integration Tests**

- [ ] `tests/k0/modules/affect/test_service.py`
  - Test `analyze_text()` returns valid AffectAnnotation
  - Test conversion to st_hipp_store dict format
  - Test field mapping matches P02 schema
  - Integration test: Mock P02 calling affect module

**Phase 2: Optional EMA Cache Tests (DEFERRED)**

- [ ] OPTIONAL: `tests/k0/modules/affect/storage/test_ema_cache.py`
  - EMA cache hit/miss tests
  - TTL expiration tests (mock time)
  - LRU eviction tests (fill cache to capacity)

#### GATE 5: Memory Documentation

- [ ] Document P02 integration point
  - Update P02 Write Pipeline doc (Section 5: Affect Analysis Integration)
  - Document call sequence: P02 Step 7 → affect.analyze_text() → st_hipp_store
- [ ] Update architecture diagram showing P02 → Affect → st_hipp_store flow
- [ ] OPTIONAL: Document EMA cache design (if implemented)

**Estimated Time**: 1 day (P02 integration only), +1 day if EMA cache included

**DECISION RATIONALE**:

- P02 analysis shows affect module is a **utility library** called by P02, not a standalone storage service
- st_hipp_store already has affect columns - no need for duplicate storage
- EMA cache is a **performance optimization** for Tier-1 classifier (Phase 2) - can defer
- Focus Phase 1 on **P02 integration** to unblock memory formation pipeline

---

## Phase 2: Classification Pipeline (Week 2-3)

### 🎯 **Component 2.1: Tier-0 Realtime Classifier**

**Reference**: ADR-0012b (Tier-0 Realtime Classifier)

#### GATE 1: ADR Discovery ✅

- [x] Requirements: Lexicon-based, <2ms P95, ~2000 words, behavioral arousal

#### GATE 2: Contract Discovery

- [ ] Create `k0/modules/affect/resources/lexicons/affect_lexicon_v1.json`

  ```json
  {
    "happy": {"valence": 0.8, "arousal": 0.5},

- [ ] Define behavioral signal contract:

  ```json
  {
    "typing_speed": "float (chars/sec)",
    "pause_duration": "float (seconds)",
    "backspace_rate": "float (deletions/sec)"
  }
  ```

#### GATE 3: Implementation

- [ ] Load lexicon: `k0/modules/affect/classifiers/tier0/lexicon.py`
  - Load ~2000 words from JSON
  - Build lookup dictionary (word → (valence, arousal))
- [ ] Implement classifier: `k0/modules/affect/classifiers/tier0/classifier.py`
  - Tokenization (lowercase, strip punctuation)
  - Negation handling ("not happy" → flip valence)
  - Intensity modifiers ("very happy" → amplify 1.5x)
  - Behavioral arousal detection (typing speed → arousal boost)
  - Aggregate valence/arousal (mean of matched words)
  - Generate tags ("distress", "celebratory", "conflict")
- [ ] Add `cognitive_trace_id` to all operations
- [ ] Performance optimization: Target <2ms P95

#### GATE 4: Test Implementation

- [ ] `tests/k0/modules/affect/classifiers/tier0/test_classifier.py`
  - Lexicon loading tests
  - Basic classification tests (positive/negative/neutral text)
  - Negation handling tests ("not happy", "never sad")
  - Intensity modifier tests ("very stressed", "slightly happy")
  - Behavioral arousal tests (high typing speed → high arousal)
  - Performance tests (<2ms P95 with py-spy profiling)
- [ ] Integration tests with real text samples

#### GATE 5: Memory Documentation

- [ ] Document lexicon source and curation process
- [ ] Record performance benchmarks
- [ ] Update architecture diagram

**Estimated Time**: 4 days

---

### 🎯 **Component 2.2: Tier-1 Enhanced Classifier (Optional)**

**Reference**: ADR-0012c (Tier-1 Enhanced Classifier & ONNX)

#### GATE 1: ADR Discovery ✅

- [x] Requirements: VADER + TextBlob + ONNX, <60ms P95, int8 quantization

#### GATE 2: Contract Discovery ✅

- [x] Download/prepare ONNX model (DistilBERT int8, ~8MB) — pulled quantified SST-2 DistilBERT (`onnx/model_int8.onnx`).
- [x] Store in `k0/modules/affect/resources/models/distilbert_affect_int8.onnx`.
- [x] Define model I/O contract:

  ```
  Input: text (string) → {input_ids:int64[1,128], attention_mask:int64[1,128]}
  Output: logits (float32[1,2]) → mapped to valence/arousal/confidence
  ```

#### GATE 3: Implementation ✅ _(Component 2.2)_

- [x] Implement `k0/modules/affect/classifiers/tier1/classifier.py`
  - VADER: compound score → valence
  - TextBlob: polarity → valence
  - ONNX: inference with int8 model → logits mapped to valence/arousal
  - Confidence-weighted ensemble (VADER 0.2, TextBlob 0.2, ONNX 0.6)
  - Graceful degradation (8 fallback scenarios if components fail)
- [x] Add model warmup on initialization
- [x] Performance optimization: Target <60ms P95 (observed ~9ms average / <15ms P95 on local CPU)

#### GATE 4: Test Implementation ✅ _(Component 2.2)_

- [x] `tests/k0/modules/affect/classifiers/tier1/test_classifier.py`
  - VADER tests (sentiment scoring)
  - TextBlob tests (polarity extraction)
  - ONNX inference tests (model loading, inference)
  - Ensemble tests (weighted aggregation)
  - Graceful degradation tests (disable ONNX → fallback to VADER+TextBlob)
  - Performance spot-check (<60ms P95)

#### GATE 5: Memory Documentation

- [ ] Document model selection and quantization process
- [ ] Record accuracy vs Tier-0 baseline
- [ ] Update architecture diagram

**Estimated Time**: 5 days (parallel with 2.3)

---

### 🎯 **Component 2.3: Multi-Modal Fusion & EMA**

**Reference**: ADR-0012d (Multi-Modal Fusion, EMA & Calibration)

#### GATE 1: ADR Discovery ✅

- [x] Requirements: Confidence-weighted fusion, dual EMA (α=0.5/0.1), calibration

#### GATE 2: Contract Discovery

- [ ] Define `ModalityScore` contract:

  ```json
  {
    "valence": "float",
    "arousal": "float",
    "confidence": "float [0, 1]",
    "source": "enum[tier0, tier1, behavior]"
  }
  ```

- [ ] Define calibration params schema

#### GATE 3: Implementation

- [ ] Implement `k0/modules/affect/fusion/engine.py`
  - Confidence-weighted fusion: `Σ(score * confidence) / Σ(confidence)`
  - Dual EMA update:
    - Fast: `v_fast = α_fast * v_new + (1 - α_fast) * v_fast_old` (α=0.5)
    - Slow: `v_slow = α_slow * v_new + (1 - α_slow) * v_slow_old` (α=0.1)
  - Per-person calibration: bias correction + temperature scaling
  - EMA cache integration (load/update/store)
- [ ] Add P06 feedback integration for calibration updates

#### GATE 4: Test Implementation

- [ ] `tests/k0/modules/affect/fusion/test_engine.py`
  - Fusion tests (single modality, multi-modality, confidence weighting)
  - EMA tests (cold start, warm update, dual EMA divergence)
  - Calibration tests (bias correction, temperature scaling)
  - Cache tests (hit/miss, TTL expiration)
  - Integration tests (full pipeline: Tier-0 → Tier-1 → Fusion → EMA)

#### GATE 5: Memory Documentation

- [ ] Document fusion algorithm decisions
- [ ] Record EMA stability tests
- [ ] Update architecture diagram

**Estimated Time**: 4 days

---

## Phase 3: Policy Engine (Week 4)

### 🎯 **Component 3.1: Policy Band Rules**

**Reference**: ADR-0012e (Policy Band Rules & P18 Integration)

#### GATE 1: ADR Discovery ✅

- [x] Requirements: 27+ rules, 4 bands (BLACK/RED/AMBER/GREEN), <5ms P95

#### GATE 2: Contract Discovery

- [ ] Review P18 policy schema: `k0/contracts/policy/pep.schema.json`
- [ ] Define PolicyAction mapping schema

#### GATE 3: Implementation

- [ ] Implement `k0/modules/affect/policy/rules.py`
  - **6 BLACK rules**: toxic_severe, self-harm, violence, explicit_content, illegal_activity, severe_threat
  - **8 RED rules**: minor_distress, parent_child_conflict, toxic_moderate, extreme_negative, bedtime_arousal_minor, school_hours_distress, conflict_without_supervision, distress_without_parent
  - **7 AMBER rules**: high_arousal, moderately_negative, low_confidence, urgent_context, household_conflict, social_context_conflict, lifecycle_stress
  - **6 GREEN rules**: positive_calm, celebratory, affectionate, family_moment, safe_social, positive_lifecycle
- [ ] Implement `k0/modules/affect/policy/engine.py`
  - Hierarchical evaluation: BLACK → RED → AMBER → GREEN
  - Rule evaluation with context (person metadata, household state)
  - Explanation generation (27 reason templates)
  - P18 PolicyAction mapping (allowed_spaces, sharing_delay, rollup_half_life, notify_guardian)
- [ ] Performance optimization: Target <5ms P95

#### GATE 4: Test Implementation

- [ ] `tests/k0/modules/affect/policy/test_rules.py`
  - Individual rule tests (all 27 rules with valid/invalid inputs)
  - Hierarchical evaluation tests (BLACK overrides RED, RED overrides AMBER)
  - Explanation generation tests (validate reason templates)
  - Edge case tests (multiple rules firing, no rules firing)
- [ ] `tests/k0/modules/affect/policy/test_engine.py`
  - Full banding pipeline tests
  - P18 integration tests
  - Performance tests (<5ms P95)

#### GATE 5: Memory Documentation

- [ ] Document rule design rationale
- [ ] Record false positive/negative rates (if validation data available)
- [ ] Update architecture diagram

**Estimated Time**: 5 days

---

## Phase 4: Social Context & Household Dynamics (Week 5)

### 🎯 **Component 4.1: Social Cognition**

**Reference**: ADR-0012h (Social Cognition & Relationship Context Modifiers)

#### GATE 1: ADR Discovery ✅

- [x] Requirements: Relationship graph, social modifiers, developmental stages, lifecycle context

#### GATE 2: Contract Discovery

- [ ] Create relationship graph schema: `k0/contracts/jsonschema/affect/relationship.json`

  ```json
  {
    "person_a": "string",
    "person_b": "string",
    "relationship_type": "enum[parent-child, partner, sibling, friend, caregiver-dependent, extended-family]",
    "direction": "string?",
    "strength": "float [0, 1]"
  }
  ```

- [ ] Create developmental stage schema
- [ ] Create lifecycle context schema

#### GATE 3: Implementation

- [ ] Implement `k0/modules/affect/social/relationship_graph.py`
  - RelationshipGraph data structure
  - Lookup helpers (get_relationship, get_related_people, is_parent_child)
  - Encrypted storage integration (MLS household key)
- [ ] Implement `k0/modules/affect/social/engine.py`
  - Social context modifiers:
    - Parent-child conflict: amplify valence × 1.3
    - Sibling conflict: amplify valence × 1.15
    - Partner conflict: amplify valence × 1.25
    - Alone: reduce arousal × 0.9
  - Developmental stage thresholds (4 stages: toddler, child, teen, adult)
  - Lifecycle context modifiers (school hours, bedtime, weekend, special events)
- [ ] Implement `k0/modules/affect/social/lifecycle.py`
  - get_lifecycle_context() function
  - Time-of-day detection
  - School hours detection (8am-3pm weekdays for minors)
  - Bedtime detection (age-dependent)

#### GATE 4: Test Implementation

- [ ] `tests/k0/modules/affect/social/test_relationship_graph.py`
  - Graph construction tests
  - Lookup tests (all helper methods)
  - Privacy tests (encrypted storage)
- [ ] `tests/k0/modules/affect/social/test_engine.py`
  - Social modifier tests (all relationship types)
  - Developmental stage tests (age-appropriate thresholds)
  - Lifecycle modifier tests (time-of-day, school, bedtime)
  - Integration tests (full social context pipeline)

#### GATE 5: Memory Documentation

- [ ] Document relationship graph design
- [ ] Record privacy audit results
- [ ] Update architecture diagram

**Estimated Time**: 4 days

---

### 🎯 **Component 4.2: Household Dynamics**

**Reference**: ADR-0012g (Household-Level Affect Dynamics)

#### GATE 1: ADR Discovery ✅

- [x] Requirements: Conflict detection, family moments, emotional contagion, household modifiers

#### GATE 2: Contract Discovery

- [ ] Review `household_affect_state.json` schema (from Phase 1)
- [ ] Define aggregation rules contract

#### GATE 3: Implementation

- [ ] Implement `k0/modules/affect/household/engine.py`
  - Compute household aggregates (mean, min, max, std for valence/arousal)
  - Conflict detection: ≥2 members with (valence<-0.3, arousal>0.6) within 5min
  - Conflict severity scoring: `0.3×participants + 0.3×arousal + 0.2×valence + 0.2×variance`
  - Family moment detection: ≥3 members with valence>0.3 within 10min
  - Celebration detection: ≥3 members with (valence>0.5, arousal>0.6) within 10min
  - Emotional contagion: detect source (most aroused) + magnitude (fraction affected)
  - Household policy modifiers: conflict severity>0.6 → downshift bands, family moment → upgrade bands
  - Privacy-preserving aggregation (no individual person_ids exposed)

#### GATE 4: Test Implementation

- [ ] `tests/k0/modules/affect/household/test_engine.py`
  - Aggregation tests (mean, std, min, max)
  - Conflict detection tests (various scenarios: 2, 3, 4 participants)
  - Conflict severity tests (score calculation validation)
  - Family moment tests (3, 4, 5 participants)
  - Emotional contagion tests (source detection, magnitude)
  - Household modifier tests (conflict→downshift, family moment→upgrade)
  - Privacy tests (validate no individual data leaked)

#### GATE 5: Memory Documentation

- [ ] Document household pattern detection algorithms
- [ ] Record false positive rates for conflict detection
- [ ] Update architecture diagram

**Estimated Time**: 4 days

---

## Phase 5: Counterfactual Safety & K1 Integration (Week 6)

### 🎯 **Component 5.1: Counterfactual Simulator**

**Reference**: ADR-0012i (Counterfactual Emotional Safety & Sharing)

#### GATE 1: ADR Discovery ✅

- [x] Requirements: "What if?" simulation, <10ms P95, multi-recipient blocking

#### GATE 2: Contract Discovery

- [ ] Review `counterfactual_input.json` and `counterfactual_result.json` schemas (from Phase 1)
- [ ] Define action type enum: `[share, notify, recall, suggest]`

#### GATE 3: Implementation

- [ ] Implement `k0/modules/affect/counterfactual/simulator.py`
  - `predict_affect_change()`: Linear impact model (content affect → Δvalence, Δarousal)
  - `predict_band()`: Simplified band prediction
  - `check_recipient_safety()`: 5 safety rules
    1. Don't push into RED band
    2. Don't amplify distress
    3. Don't spike arousal during conflict
    4. Don't push arousal >0.85
    5. Don't push into BLACK band
  - `simulate_affect_impact()`: Multi-recipient simulation with blocking decisions
  - Confidence scoring
- [ ] Integration with sharing policy, notification timing, recall filter, K1 planning

#### GATE 4: Test Implementation

- [ ] `tests/k0/modules/affect/counterfactual/test_simulator.py`
  - Impact prediction tests (positive/negative content, various recipient states)
  - Safety rule tests (all 5 rules with edge cases)
  - Multi-recipient tests (partial blocking scenarios)
  - Performance tests (<10ms P95)
  - Integration tests (sharing, notifications, recall, K1 planning)

#### GATE 5: Memory Documentation

- [ ] Document counterfactual reasoning approach
- [ ] Record blocking accuracy (validate with user feedback)
- [ ] Update architecture diagram

**Estimated Time**: 4 days

---

### 🎯 **Component 5.2: K1 Bridge**

**Reference**: ADR-0012f (Affect → K1 Planner & Concierge Bridge)

#### GATE 1: ADR Discovery ✅

- [x] Requirements: AffectSummary, 5 behavior modes, mood mapping, content bias

#### GATE 2: Contract Discovery

- [ ] Review `affect_summary.json` schema (from Phase 1)
- [ ] Define behavior mode contracts (slow, gentle, quiet, wind-down, opportunity)

#### GATE 3: Implementation

- [ ] Implement `k0/modules/affect/bridge/bridge.py`
  - `get_affect_summary()`: Generate AffectSummary for K1
  - Mood label mapping (Circumplex Model): calm, happy, excited, stressed, sad, frustrated
  - Trend detection: fast EMA vs slow EMA (improving/declining/stable)
  - Household context integration (HouseholdAffectSummary)
- [ ] Implement behavior mode logic:
  - **Slow mode** (arousal>0.7 OR RED/AMBER): +2s delay, confirm all, 2-3 choices
  - **Gentle mode** (valence<-0.5 OR sad/frustrated): empathetic tone, calming suggestions
  - **Quiet mode** (household conflict): no proactive, urgent only
  - **Wind-down mode** (minor + night + arousal>0.5): calming content, dim notifications
  - **Opportunity mode** (valence>0.5 + arousal<0.6 + GREEN): frequent proactive

#### GATE 4: Test Implementation

- [ ] `tests/k0/modules/affect/bridge/test_bridge.py`
  - AffectSummary generation tests
  - Mood mapping tests (all 6 moods)
  - Trend detection tests (improving/declining/stable)
  - Behavior mode activation tests (all 5 modes)
  - K1 integration tests (mock K1 Planner/Concierge)

#### GATE 5: Memory Documentation

- [ ] Document behavior mode design decisions
- [ ] Record user feedback on mode appropriateness
- [ ] Update architecture diagram

**Estimated Time**: 3 days

---

## Phase 6: Service Integration (Week 7)

### 🎯 **Component 6.1: AffectService API (Shared Library Interface)**

#### GATE 1: ADR Discovery ✅

- [x] All 9 sub-ADRs validated
- [x] Module is shared library, not standalone service

#### GATE 2: Contract Discovery

- [x] All contracts created in Phase 1-5
- [ ] Define public API contract for consumer services

#### GATE 3: Implementation

- [ ] Implement `k0/modules/affect/service.py` (library interface)
  - `classify_text()`: Full pipeline
    1. Tier-0 classification
    2. Tier-1 classification (if enabled)
    3. Behavioral signal integration
    4. Multi-modal fusion
    5. EMA smoothing
    6. Social context modifiers
    7. Lifecycle modifiers
    8. Policy banding
    9. Household modifiers
    10. Storage (annotation + EMA state)
  - `get_ema_state()`: Retrieve from cache
  - `get_household_state()`: Compute household dynamics
  - `get_affect_summary()`: Generate K1 summary
- [ ] Add comprehensive logging with `cognitive_trace_id`
- [ ] Add Prometheus metrics (latency, band distribution, cache hit rate)
- [ ] Add thread-safety for concurrent usage by multiple services

#### GATE 4: Test Implementation

- [ ] `tests/k0/modules/affect/test_service.py`
  - Full E2E pipeline tests (happy path)
  - Error handling tests (component failures, graceful degradation)
  - Performance tests (E2E <70ms P95 with Tier-1)
  - Cache behavior tests (cold start, warm state)
  - Thread-safety tests (concurrent access from multiple services)
- [ ] `tests/k0/modules/affect/integration/`
  - Multi-service concurrent usage tests
  - Multi-user household tests

#### GATE 5: Memory Documentation

- [ ] Document public API for consumer services
- [ ] Record performance benchmarks
- [ ] Update all architecture diagrams

**Estimated Time**: 5 days

---

### 🎯 **Component 6.2: Consumer Service Integration Examples**

**Note**: These integrations happen in the consumer services' repositories/modules, not in affect module itself. This section provides guidance and example integration code.

#### GATE 1: ADR Discovery

- [ ] Review consumer service architectures:
  - P02 Write Pipeline
  - Memory Steward
  - Policy Engine (P18)
  - K1 Planner/Concierge
  - Workspace Service

#### GATE 2: Contract Discovery

- [ ] Validate affect contracts match consumer event schemas
- [ ] Document integration patterns for each consumer

#### GATE 3: Implementation (Example Integration Code)

- [ ] Create example integration for **P02 Write Pipeline**:

  ```python
  # In P02 pipeline (not in affect module)
  from k0.modules.affect import AffectService

  affect_service = AffectService()

  # After event ingestion
  affect_annotation = affect_service.classify_text(
      text=event.content,
      context={
          "person_id": event.person_id,
          "space_id": event.space_id,
          "other_actors": event.other_actors,
          "behavior": event.behavioral_signals
      }
  )

  # Store annotation with event in st_hipp_store
  event.affect_valence = affect_annotation.valence
  event.affect_arousal = affect_annotation.arousal
  # ... (6 affect columns)
  ```

- [ ] Create example integration for **K1 Planner**:

  ```python
  # In K1 Planner (not in affect module)
  from k0.modules.affect import AffectService

  affect_service = AffectService()

  # Before generating plan
  affect_summary = affect_service.get_affect_summary(
      person_id=session.person_id,
      space_id=session.space_id
  )

  # Adapt behavior based on affect
  if affect_summary.band == "RED" or affect_summary.arousal > 0.7:
      enable_slow_mode()
  if affect_summary.mood_label in ["sad", "frustrated"]:
      enable_gentle_mode()
  ```

- [ ] Create example integration for **Policy Engine**:

  ```python
  # In Policy Engine (not in affect module)
  from k0.modules.affect import AffectService

  affect_service = AffectService()

  # Before sharing decision
  household_state = affect_service.get_household_state(space_id)

  if household_state.conflict_active:
      # Apply stricter sharing rules
      policy_action.sharing_delay = 900  # 15 min delay
  ```

- [ ] Document integration patterns in `k0/modules/affect/docs/INTEGRATION_GUIDE.md`

#### GATE 4: Test Implementation

- [ ] `tests/k0/modules/affect/examples/` (example integration tests)
  - Mock P02 pipeline integration
  - Mock K1 planner integration
  - Mock policy engine integration
  - Performance validation (affect module overhead <5%)

#### GATE 5: Memory Documentation

- [ ] Document integration patterns for all consumers
- [ ] Create sequence diagrams showing affect module usage
- [ ] Update consumer service documentation (in their repos)

**Estimated Time**: 3 days (for examples + documentation)

---

## Phase 7: Performance Optimization & Validation (Week 8)

### 🎯 **Component 7.1: Performance Benchmarking**

#### Tasks

- [ ] Set up py-spy profiling for all components
- [ ] Run latency benchmarks (1000+ samples per component)
- [ ] Identify bottlenecks
- [ ] Optimize hot paths
- [ ] Validate all performance budgets met:
  - Tier-0: <2ms P95 ✅
  - Tier-1: <60ms P95 ✅
  - Fusion: <1ms P95 ✅
  - Policy: <5ms P95 ✅
  - Counterfactual: <10ms P95 ✅
  - Total E2E: <70ms P95 ✅

**Estimated Time**: 3 days

---

### 🎯 **Component 7.2: Accuracy Validation**

#### Tasks

- [ ] Create validation dataset (100+ labeled samples)
- [ ] Measure classification accuracy (Tier-0, Tier-1, policy bands)
- [ ] Calculate false positive/negative rates for safety rules
- [ ] A/B test counterfactual simulation (with/without blocking)
- [ ] Validate household pattern detection (conflict, family moments)
- [ ] Collect user feedback on behavior modes

**Estimated Time**: 4 days

---

## Phase 8: Documentation & Library Release (Week 9)

### 🎯 **Component 8.1: Library Documentation**

#### Tasks

- [ ] Update `k0/modules/affect/README.md` with complete API documentation
- [ ] Create `k0/modules/affect/docs/API_REFERENCE.md`
  - All public methods with signatures, params, returns
  - Usage examples for each method
  - Performance characteristics
  - Thread-safety guarantees
- [ ] Create `k0/modules/affect/docs/INTEGRATION_GUIDE.md`
  - How to integrate into consumer services
  - Example code for P02, K1, Policy Engine, etc.
  - Best practices and common patterns
  - Error handling strategies
- [ ] Create `k0/modules/affect/docs/ARCHITECTURE.md`
  - Component diagram
  - Data flow diagrams
  - Performance budgets
  - Calibration process (P06 feedback integration)
- [ ] Create `k0/modules/affect/docs/TROUBLESHOOTING.md`
  - Common issues and solutions
  - Performance debugging
  - Cache tuning
  - Lexicon updates
- [ ] Update all architecture diagrams in `architecture_diagrams/`
  - Affect module internal architecture
  - Integration with consumer services

**Estimated Time**: 3 days

---

### 🎯 **Component 8.2: Library Release Preparation**

#### Tasks

- [ ] **Version Management**:
  - Define semantic versioning strategy (v1.0.0)
  - Create CHANGELOG.md for module
  - Tag release in version control

- [ ] **Monitoring & Observability** (for consumer services):
  - Document Prometheus metrics exported by module
  - Create example Grafana dashboard for consumers
  - Define alerting rules (latency, accuracy, cache hit rate)
  - Add OpenTelemetry tracing support

- [ ] **Security & Privacy Audits**:
  - Security audit (relationship graph encryption, PII protection)
  - Privacy audit (data minimization, retention policies)
  - Document security requirements for consumers
  - Verify no sensitive data in logs/metrics

- [ ] **Integration Testing Harness**:
  - Create mock/stub implementations for unit testing consumers
  - Provide test fixtures and example data
  - Document testing strategies for consumers

- [ ] **Gradual Rollout Strategy** (for consumer services):
  - Feature flags integration pattern
  - A/B testing guidance
  - Rollback procedures for consumers
  - Backward compatibility guarantees

**Estimated Time**: 2 days

---

## Summary: Timeline & Effort

| Phase | Duration | Components | Estimated Effort |
|-------|----------|------------|------------------|
| **Phase 1: Contracts & Storage** | Week 1 | Schemas + Storage | 4 days |
| **Phase 2: Classification** | Week 2-3 | Tier-0, Tier-1, Fusion | 13 days |
| **Phase 3: Policy Engine** | Week 4 | Band Rules | 5 days |
| **Phase 4: Social & Household** | Week 5 | Social Context, Household Dynamics | 8 days |
| **Phase 5: Safety & K1** | Week 6 | Counterfactual, K1 Bridge | 7 days |
| **Phase 6: Service Integration** | Week 7 | API + Integration Examples | 8 days |
| **Phase 7: Validation** | Week 8 | Performance, Accuracy | 7 days |
| **Phase 8: Library Release** | Week 9 | Docs, Release Prep | 5 days |
| **TOTAL** | **9 weeks** | **17 components** | **~57 days** |

**Team Size**: 2-3 engineers (parallel work possible)

**Deployment Note**: This is a **shared library module**. Actual deployment happens when consumer services (P02, K1, Policy Engine, etc.) integrate and deploy the affect module. Each consumer service will have its own deployment timeline.

---

## Dependencies & Risks

### External Dependencies (Module Requirements)

- [ ] st_hipp_store schema supports 6 affect columns
- [ ] P06 feedback system operational for calibration
- [ ] MLS encryption available for relationship graph storage

### Consumer Service Dependencies (Integration Requirements)

- [ ] P02 Write Pipeline ready to integrate affect classification
- [ ] K1 Planner/Concierge ready to consume AffectSummary
- [ ] Policy Engine (P18) ready to use household affect state
- [ ] Memory Steward ready for affect-aware consolidation
- [ ] Workspace Service ready to expose household affect API

### Technical Risks

1. **Performance Budget**: Tier-1 ONNX inference may exceed 60ms
   - **Mitigation**: Make Tier-1 optional, fallback to Tier-0
2. **Lexicon Coverage**: ~2000 words may miss domain-specific terms
   - **Mitigation**: Iterative lexicon expansion, P06 feedback loop
3. **Household Pattern Accuracy**: Conflict detection may have false positives
   - **Mitigation**: Tune thresholds with validation data, allow user overrides
4. **Relationship Graph Staleness**: Outdated relationships lead to incorrect modifiers
   - **Mitigation**: Periodic sync with household profile, user-managed relationships

---

## Success Criteria

### Functional

- ✅ All 27+ policy rules implemented and tested
- ✅ Full E2E pipeline operational (Event → Classification → Policy → Storage → K1)
- ✅ Graceful degradation (Tier-1 failure → Tier-0 fallback)
- ✅ Privacy-preserving (relationship graph encrypted, no PII leaks)

### Performance

- ✅ Tier-0: <2ms P95
- ✅ Tier-1: <60ms P95
- ✅ Policy: <5ms P95
- ✅ E2E: <70ms P95

### Accuracy

- ✅ Classification accuracy >80% (vs validation dataset)
- ✅ Policy band accuracy >85%
- ✅ Conflict detection precision >75%, recall >70%
- ✅ Counterfactual blocking false positive rate <10%

### Integration (Library Ready for Consumers)

- ✅ Public API stable and documented
- ✅ Integration examples provided for all consumer services
- ✅ Thread-safe for concurrent usage
- ✅ Prometheus metrics exported
- ✅ Mock/stub implementations for consumer testing
- ✅ Backward compatibility guarantees documented

---

## Next Actions

1. **Immediate** (This Week):
   - [ ] Review and approve this plan
   - [ ] Assign Phase 1 to engineers
   - [ ] Create GitHub issues for all components
   - [ ] Set up project board with 5-gate checkpoints
   - [ ] **Coordinate with consumer service teams** (P02, K1, Policy, etc.) for integration timeline

2. **Phase 1 Kickoff** (Next Week):
   - [ ] Create JSON schema contracts
   - [ ] Implement storage integration
   - [ ] Run first round of tests

3. **Weekly Checkpoints**:
   - [ ] Monday: Review previous week's progress
   - [ ] Wednesday: Mid-week check-in on blockers
   - [ ] Friday: Phase gate review (pass/fail decision for proceeding)
   - [ ] **Bi-weekly sync with consumer service teams** (alignment on API changes)

4. **Consumer Service Integration** (Post-Release):
   - [ ] **P02 Team**: Integrate affect classification into write pipeline
   - [ ] **K1 Team**: Consume AffectSummary for behavior modes
   - [ ] **Policy Team**: Use household affect state for policy decisions
   - [ ] **Memory Team**: Affect-aware memory consolidation
   - [ ] **Workspace Team**: Expose household affect API

---

## References

- **ADRs**: `docs/architecture/decisions-K0/Affect Module/k003a-k003i.md`
- **5-Gate Workflow**: `.github/copilot-instructions.md`
- **Module Structure**: `k0/modules/affect/README.md`
- **Performance Budgets**: ADR-0012 (Section 3)
- **Contract Standards**: `.github/instructions/documentation-standards.instructions.md`

---

**Last Updated**: 2025-11-13
**Status**: Ready for Review
