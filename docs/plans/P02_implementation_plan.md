# P02 Write Pipeline - Implementation Plan

**Status**: 🎯 Planning Phase
**Version**: 1.0.0
**Created**: 2025-11-16
**Owner**: Development Team
**Related Dossier**: [P02_write_dossier.md](../pipelines/P02_write_dossier.md)
**Data Schema**: [P02_data_schema.md](../pipelines/P02_data_schema.md)
**Master Tracking**: [k0_architecture_master.md](../../k0/pipelines/k0_architecture_master.md)

---

## Executive Summary

### Overview

This plan implements P02 (Episodic Memory Formation Pipeline) using Phase 2 declarative architecture. P02 processes WAL-committed memory events through a multi-stage enrichment DAG, producing hippocampus-enriched events ready for consolidation.

### Timeline

- **Milestone 1**: Module Contracts (YAML) - 3-4 days (17 contracts)
- **Milestone 2**: ADRs (Architectural Decisions) - 4-5 days (17 ADRs)
- **Total for M1+M2**: ~2 weeks

### Current Blockers

- ✅ **RESOLVED**: Runtime infrastructure complete (k0/runtime/)
- ✅ **RESOLVED**: Phase 2 dossier aligned to declarative architecture
- ✅ **RESOLVED**: Storage schema designed (migration 0024)
- ⚠️ **ACTIVE**: Need to create module contracts (Step 4)

### Dependencies

```
Milestone 1 (Contracts) → Milestone 2 (ADRs) → Milestone 3 (Pipeline YAML) →
Milestone 4 (Implementation) → Milestone 5 (Syscalls) → Milestone 6 (Integration) →
Milestone 7 (Testing)
```

---

## Milestone 1: Module Contracts (YAML)

**Goal**: Create 17 module contract YAML files that define interfaces, capabilities, and performance budgets for all P02 modules.

**Status**: 📝 Not Started
**Duration**: 3-4 days
**Effort**: ~24-32 hours (17 contracts × 1.5-2h each)
**Prerequisites**:

- ✅ P02 dossier complete
- ✅ Runtime schemas defined (k0/runtime/schemas.py)
- ✅ Module development guidelines available

### Epic 1.1: Hippocampus Module Contracts (M01-M03)

**Focus**: Core memory encoding modules (DG pattern separation, CA1 semantic projection)

---

#### Issue 1.1.1: Create hippocampus.pattern_separate.v1.yaml (M01)

**Priority**: 🔴 Critical (blocks all downstream work)
**Size**: M (2-3 hours)
**Assignee**: TBD

##### Context References

**Primary Sources**:

- **P02 Dossier**: `docs/pipelines/P02_write_dossier.md`
  - Lines 383-386 (module mapping table entry for M01)
  - Lines 195-221 (R1.1 Pattern Separation responsibilities)
  - Lines 850-868 (P02 YAML pipeline spec - stage_10_dg_pattern_separate)
- **Data Schema**: `docs/pipelines/P02_data_schema.md`
  - Lines 160-167 (hippocampus fingerprint columns in st_hipp_events)
- **Runtime Guide**: `k0/runtime/README.md`
  - Lines 150-230 (Module contract specification format)
- **Module Guidelines**: `k0/modules/module_development_guidelines.md`
  - Lines 300-450 (Module contract YAML structure)
- **Related ADR**: `docs/architecture/decisions-K0/modules/k003.1-dg-pattern-separation.md` (to be created in M2)

**Supporting Context**:

- **Migration Plan**: `k0/pipelines/MIGRATION_PLAN.md` (Week 3 timeline)
- **Example Contracts**: Check existing ADRs in `docs/architecture/decisions-K0/modules/` for pattern references

##### Master Document Tracking (MANDATORY)

**Update Locations**:

1. **Part 5.1: Global Contract Registry**
   - File: `k0/pipelines/k0_architecture_master.md` (search for "Part 5.1")
   - Action: Add row to contract registry table:

     ```markdown
     | hippocampus.pattern_separate:v1 | Module | M01 | DG pattern separation | YAML | ✅ Created | k0/contracts/modules/hippocampus.pattern_separate.v1.yaml |
     ```

2. **Part 3.1: Module Master Registry**
   - File: `k0/pipelines/k0_architecture_master.md` (search for "Part 3.1")
   - Action: Update M01 row status from "📝 Design" to "🎯 Planning" and add contract link:

     ```markdown
     | M01 | hippocampus.pattern_separate | 🎯 Planning | ... | Contract: ✅ | hippocampus.pattern_separate.v1.yaml |
     ```

##### Deliverables

- [x] Create file: `k0/contracts/modules/hippocampus.pattern_separate.v1.yaml`
- [x] Update Master Doc Part 5.1 (Contract Registry)
- [x] Update Master Doc Part 3.1 (Module Registry - M01 status)
- [x] Validate YAML syntax with Pydantic schema
- [x] Create contracts directory structure if needed

##### Acceptance Criteria

**Contract Completeness**:

- [x] `module_id: hippocampus.pattern_separate` (matches import path `k0.modules.hippocampus.pattern_separate`)
- [x] `version: v1` (follows semantic versioning)
- [x] `input_event_types`: List entry topic `cognitive.memory.write.committed.v1`
- [x] `output_event_types`: List `p02.hippocampus.pattern_separated.v1`
- [x] `latency_budget_ms: 15` (from dossier line 221: "≤15ms P95")
- [x] `side_effects` array includes:
  - `read:st_hipp_events` (for neighbor queries in future, though P02 doesn't use)
  - No writes (fingerprints computed in-memory only)
- [x] `idempotent: true` (pure computation)
- [x] `failure_modes` defined:
  - `FINGERPRINT_COMPUTATION_FAILED` with policy `retry`
- [x] `description` field explains DG pattern separation purpose

**Master Document Validation**:

- [x] Contract appears in Part 5.1 registry with ✅ status
- [x] Module M01 in Part 3.1 shows contract created
- [x] Cross-references are valid (file paths exist)

**Schema Validation**:

- [x] YAML parses without errors
- [x] Validates against `ModuleContract` Pydantic schema (k0/runtime/schemas.py)
- [x] Module ID pattern matches `^[a-z_]+\.[a-z_]+$`
- [x] Version pattern matches `^v\d+$`
- [x] Latency budget in range 1-10000ms

##### Implementation Steps

1. **Prepare Environment**

   ```powershell
   # Create contracts directory structure
   New-Item -ItemType Directory -Force -Path "k0\contracts\modules"
   ```

2. **Read Context Files**
   - Review dossier lines 195-221 for DG responsibilities
   - Check runtime README lines 150-230 for YAML format
   - Review module guidelines lines 300-450 for required fields

3. **Create Contract YAML**

   ```yaml
   # k0/contracts/modules/hippocampus.pattern_separate.v1.yaml
   module_id: hippocampus.pattern_separate
   version: v1

   input_event_types:
     - cognitive.memory.write.committed.v1

   output_event_types:
     - p02.hippocampus.pattern_separated.v1

   latency_budget_ms: 15

   side_effects:
     - read:st_hipp_events  # Future: neighbor queries for novelty

   idempotent: true

   failure_modes:
     - code: FINGERPRINT_COMPUTATION_FAILED
       policy: retry
       max_retries: 3
     - code: INVALID_INPUT_TEXT
       policy: drop

   description: |
     DG (Dentate Gyrus) Pattern Separation Module

     Computes local fingerprints for episodic memory encoding:
     - SimHash (64-bit) for coarse similarity detection
     - MinHash (32 permutations) for LSH bucket assignment

     Does NOT perform neighbor queries or novelty scoring in P02.
     Those operations are deferred to P03 (Consolidation) for global analysis.

     Performance target: ≤15ms P95 per event
     Input: Envelope with text, participants, place, activity_type
     Output: simhash_hex, minhash32 fingerprints

   config_schema:
     type: object
     properties:
       novelty_threshold:
         type: number
         default: 0.7
         description: Threshold for novelty detection (used in P03, not P02)
       hash_seed:
         type: integer
         default: 42
         description: Seed for reproducible fingerprint generation
   ```

4. **Update Master Document**
   - Open `k0/pipelines/k0_architecture_master.md`
   - Search for "Part 5.1: Global Contract Registry"
   - Add contract row to registry table
   - Search for "Part 3.1: Module Master Registry"
   - Update M01 status and add contract link
   - Save file

5. **Validate Contract**

   ```powershell
   # Validate YAML syntax
   python -c "import yaml; yaml.safe_load(open('k0/contracts/modules/hippocampus.pattern_separate.v1.yaml'))"

   # Validate against Pydantic schema (future: add validation script)
   # python k0/runtime/validate_contract.py k0/contracts/modules/hippocampus.pattern_separate.v1.yaml
   ```

##### Estimated Effort

- **Contract Creation**: 1.5 hours (research + YAML writing)
- **Master Doc Updates**: 30 minutes (find sections + update tables)
- **Validation**: 30 minutes (syntax check + cross-reference verification)
- **Total**: 2.5 hours

##### Dependencies

- **Blocks**: Issue 1.1.2 (CA1 semantic projection contract)
- **Blocked By**: None (first contract)

##### Notes

- This is the **first contract** - sets the pattern for remaining 16
- Keep fingerprint computation logic simple (no neighbor queries)
- Remember: P02 computes fingerprints, P03 analyzes novelty
- Contract specifies interface only, not implementation details

---

#### Issue 1.1.2: Create hippocampus.semantic_project.v1.yaml (M02)

**Priority**: 🔴 Critical
**Size**: M (2-3 hours)
**Assignee**: TBD

##### Context References

**Primary Sources**:

- **P02 Dossier**: `docs/pipelines/P02_write_dossier.md`
  - Lines 387-390 (module mapping table entry for M02)
  - Lines 223-235 (R1.3 Semantic Projection responsibilities)
  - Lines 853-856 (P02 YAML pipeline spec - stage reference)
- **Data Schema**: `docs/pipelines/P02_data_schema.md`
  - Lines 168-171 (embeddings/KG columns in st_hipp_events)
- **Runtime Guide**: `k0/runtime/README.md`
  - Lines 150-230 (Module contract specification format)
- **Related ADR**: `docs/architecture/decisions-K0/modules/k003.2-ca1-semantic-bridge.md` (to be created in M2)

##### Master Document Tracking (MANDATORY)

**Update Locations**:

1. **Part 5.1: Global Contract Registry**
   - Add row: `hippocampus.semantic_project:v1 | Module | M02 | CA1 semantic projection | YAML | ✅ Created | k0/contracts/modules/hippocampus.semantic_project.v1.yaml`

2. **Part 3.1: Module Master Registry**
   - Update M02: Status to "🎯 Planning", add contract link

##### Deliverables

- [x] Create file: `k0/contracts/modules/hippocampus.semantic_project.v1.yaml`
- [x] Update Master Doc Part 5.1 (Contract Registry)
- [x] Update Master Doc Part 3.1 (Module Registry - M02 status)
- [x] Validate YAML syntax

##### Acceptance Criteria

**Contract Completeness**:

- [x] `module_id: hippocampus.semantic_project`
- [x] `version: v1`
- [x] `latency_budget_ms: 20` (entity extraction + KG triples)
- [x] `side_effects`:
  - `write:st_embedding_queue` (enqueue job)
- [x] `idempotent: true` (deterministic entity extraction)
- [x] `output_event_types`: Include embedding enqueue event
- [x] `description`: Explains CA1 semantic bridge role

**Key Outputs**:

- [x] Allocates `embedding_id` (UUID)
- [x] Extracts entities (people, places, organizations)
- [x] Generates KG triples (subject, predicate, object)
- [x] Prepares embedding job payload for P08

**Master Document Validation**:

- [x] Contract in Part 5.1 with ✅ status
- [x] M02 in Part 3.1 shows contract created

##### Implementation Steps

1. Read context from dossier lines 223-235
2. Create YAML with entity extraction focus
3. Specify side effects for embedding queue write
4. Update master document sections
5. Validate YAML syntax

##### Estimated Effort

- **Contract Creation**: 2 hours
- **Master Doc Updates**: 30 minutes
- **Total**: 2.5 hours

##### Dependencies

- **Blocks**: Issue 1.2.1 (affect.analyze contract)
- **Blocked By**: Issue 1.1.1 (pattern for contract creation established)

---

#### Issue 1.1.3: Document M03 (CA3 Clustering) - P03 Scope Note

**Priority**: 🟡 Medium (documentation only)
**Size**: S (30 minutes)
**Assignee**: TBD

##### Context References

- **P02 Dossier**: Lines 388 (M03 listed but marked as P03 scope)
- **Data Schema**: Lines 160-167 (dedup/cluster columns NULL in P02)

##### Master Document Tracking (MANDATORY)

**Update Locations**:

1. **Part 3.1: Module Master Registry**
   - Update M03 row: Add note "⚠️ P03 Scope - No contract in P02"
   - Status remains "📝 Design" (not part of P02)

##### Deliverables

- [ ] Update Master Doc Part 3.1 with P03 scope note
- [ ] Add comment in M01/M02 contracts explaining M03 deferred

##### Acceptance Criteria

- [ ] M03 clearly marked as P03 scope in registry
- [ ] No contract file created for M03 in this milestone
- [ ] Cross-references to P03 added where relevant

##### Implementation Steps

1. Open master document Part 3.1
2. Update M03 entry with P03 scope warning
3. Add brief explanation of why deferred

##### Estimated Effort

- **Documentation**: 30 minutes

##### Dependencies

- **Blocks**: None (documentation only)
- **Blocked By**: None

---

### Epic 1.2: Cognition Module Contracts (M04-M06)

**Focus**: Affect classification, space resolution, salience scoring

---

#### Issue 1.2.1: Create affect.analyze.v1.yaml (M04)

**Priority**: 🔴 Critical
**Size**: M (2 hours)
**Assignee**: TBD

##### Context References

**Primary Sources**:

- **P02 Dossier**: Lines 391-394 (M04 mapping), Lines 237-248 (R1.4 Affect Classification)
- **Data Schema**: Lines 172-178 (affect columns)
- **Related ADR**: `k004.1-tier0-fast-affect.md` (to be created in M2)

##### Master Document Tracking (MANDATORY)

**Update Locations**:

1. **Part 5.1**: Add `affect.analyze:v1` contract entry
2. **Part 3.1**: Update M04 status to "🎯 Planning"

##### Deliverables

- [x] Create: `k0/contracts/modules/affect.analyze.v1.yaml`
- [x] Update Master Doc Part 5.1 and 3.1
- [x] Validate YAML

##### Acceptance Criteria

- [x] `module_id: affect.analyze`
- [x] `latency_budget_ms: 70` (Tier-0: <2ms, Tier-1: <60ms)
- [x] Output fields: `valence`, `arousal`, `tags`, `affect_band`, `band_reasons`
- [x] `side_effects`: No storage access (pure classification)
- [x] `idempotent: true`

##### Implementation Steps

1. Read affect responsibilities from dossier
2. Create YAML with tier-based latency budgets
3. Specify output schema (valence 0-1, arousal 0-1)
4. Update master document
5. Validate

##### Estimated Effort

- **Total**: 2.5 hours

##### Dependencies

- **Blocks**: Issue 1.2.2 (space resolution)
- **Blocked By**: Issue 1.1.2 (pattern established)

---

#### Issue 1.2.2: Create space.resolve_visibility.v1.yaml (M05)

**Priority**: 🔴 Critical
**Size**: M (2 hours)
**Assignee**: TBD

##### Context References

**Primary Sources**:

- **P02 Dossier**: Lines 395-398 (M05 mapping), Lines 252-264 (R2.1 Space Resolution)
- **Data Schema**: Lines 120-129 (policy & visibility columns)
- **Related ADR**: `k005.1-acl-resolution.md` (to be created in M2)

##### Master Document Tracking (MANDATORY)

**Update Locations**:

1. **Part 5.1**: Add `space.resolve_visibility:v1` entry
2. **Part 3.1**: Update M05 status

##### Deliverables

- [x] Create: `k0/contracts/modules/space.resolve_visibility.v1.yaml`
- [x] Update Master Doc sections
- [x] Validate YAML

##### Acceptance Criteria

- [x] `module_id: space.resolve_visibility`
- [x] `latency_budget_ms: 3` (cache lookup)
- [x] Output: `owner_id`, `co_owners`, `author_role`, `visible_to` (intersection)
- [x] `side_effects`: `read:spaces` or similar (space metadata lookup)
- [x] Safety guarantee: never expand visibility beyond policy

##### Implementation Steps

1. Read space resolution logic from dossier
2. Create contract with cache-optimized latency
3. Specify intersection semantics
4. Update master document
5. Validate

##### Estimated Effort

- **Total**: 2.5 hours

##### Dependencies

- **Blocks**: Issue 1.3.1 (temporal profile)
- **Blocked By**: Issue 1.2.1

---

#### Issue 1.2.3: Create salience.score.v1.yaml (M06)

**Priority**: 🟡 Medium
**Size**: S (1.5 hours)
**Assignee**: TBD

##### Context References

**Primary Sources**:

- **P02 Dossier**: Lines 399-402 (M06 mapping), Lines 250-256 (R1.5 Salience Scoring)
- **Related ADR**: `k006.1-write-path-salience.md` (to be created in M2)

##### Master Document Tracking (MANDATORY)

**Update Locations**:

1. **Part 5.1**: Add `salience.score:v1` entry
2. **Part 3.1**: Update M06 status

##### Deliverables

- [x] Create: `k0/contracts/modules/salience.score.v1.yaml`
- [x] Update Master Doc sections
- [x] Validate YAML

##### Acceptance Criteria

- [x] `module_id: salience.score`
- [x] `latency_budget_ms: 5` (formula-based, no queries)
- [x] Formula: `0.50×social + 0.40×affect + 0.10×recency`
- [x] No novelty dependency (deferred to P03)
- [x] Output: `salience_score`, `salience_reasons`, `salience_band`
- [x] `idempotent: true`

##### Implementation Steps

1. Read salience formula from dossier
2. Create contract with formula in description
3. Specify pure computation (no side effects)
4. Update master document
5. Validate

##### Estimated Effort

- **Total**: 2 hours

##### Dependencies

- **Blocks**: Issue 1.4.1 (hipp events builder)
- **Blocked By**: Issue 1.2.2

---

### Epic 1.3: Context Enrichment Contracts (M08-M12, M15)

**Focus**: Temporal, device, ingress, retention, geo, spatial modules

---

#### Issue 1.3.1: Create context.temporal_profile.v1.yaml (M08)

**Priority**: 🔴 Critical
**Size**: M (2 hours)
**Assignee**: TBD

##### Context References

**Primary Sources**:

- **P02 Dossier**: Lines 407-410 (M08 mapping), Lines 266-278 (R2.3 Temporal)
- **Data Schema**: Lines 130-140 (temporal columns)
- **Related ADR**: `k007.1-temporal-profiler.md` (to be created in M2)

##### Master Document Tracking (MANDATORY)

**Update Locations**:

1. **Part 5.1**: Add `context.temporal_profile:v1` entry
2. **Part 3.1**: Update M08 status

##### Deliverables

- [ ] Create: `k0/contracts/modules/context.temporal_profile.v1.yaml`
- [ ] Update Master Doc sections
- [ ] Validate YAML

##### Acceptance Criteria

- [ ] `module_id: context.temporal_profile`
- [ ] `latency_budget_ms: 5` (timezone math)
- [ ] Output fields: `event_time_utc`, `write_time_utc`, `write_lag_ms`, `local_date`, `local_time`, `day_of_week`, `is_weekend`, `time_of_day_bucket`, `circadian_slot`, `is_backdated`
- [ ] `side_effects`: `read:tenant_config` (for timezone lookup)
- [ ] `idempotent: true`

##### Implementation Steps

1. Read temporal responsibilities from dossier
2. List all 11 output fields from data schema
3. Specify timezone config as side effect
4. Update master document
5. Validate

##### Estimated Effort

- **Total**: 2.5 hours

##### Dependencies

- **Blocks**: Issue 1.3.5 (spatial minimal)
- **Blocked By**: Issue 1.2.2

---

#### Issue 1.3.2: Create context.device_profile.v1.yaml (M09)

**Priority**: 🟡 Medium
**Size**: S (1.5 hours)
**Assignee**: TBD

##### Context References

**Primary Sources**:

- **P02 Dossier**: Lines 405-408 (M09 mapping)
- **Related ADR**: `k007.2-device-profiler.md` (to be created in M2)

##### Master Document Tracking (MANDATORY)

**Update Locations**:

1. **Part 5.1**: Add `context.device_profile:v1` entry
2. **Part 3.1**: Update M09 status

##### Deliverables

- [ ] Create: `k0/contracts/modules/context.device_profile.v1.yaml`
- [ ] Update Master Doc sections
- [ ] Validate YAML

##### Acceptance Criteria

- [ ] `module_id: context.device_profile`
- [ ] `latency_budget_ms: 3` (cache lookup)
- [ ] Output: `device_kind`, `device_os`, `is_primary_device_for_actor`
- [ ] `side_effects`: `read:st_devices`
- [ ] `idempotent: true`

##### Estimated Effort

- **Total**: 2 hours

##### Dependencies

- **Blocks**: None (parallel with other context modules)
- **Blocked By**: Issue 1.3.1 (pattern established)

---

#### Issue 1.3.3: Create context.ingress_classify.v1.yaml (M10)

**Priority**: 🟡 Medium
**Size**: S (1.5 hours)
**Assignee**: TBD

##### Context References

**Primary Sources**:

- **P02 Dossier**: Lines 409-412 (M10 mapping)
- **Related ADR**: `k007.3-ingress-classifier.md` (to be created in M2)

##### Master Document Tracking (MANDATORY)

**Update Locations**:

1. **Part 5.1**: Add `context.ingress_classify:v1` entry
2. **Part 3.1**: Update M10 status

##### Deliverables

- [ ] Create: `k0/contracts/modules/context.ingress_classify.v1.yaml`
- [ ] Update Master Doc sections
- [ ] Validate YAML

##### Acceptance Criteria

- [ ] `module_id: context.ingress_classify`
- [ ] `latency_budget_ms: 2` (rule-based)
- [ ] Output: `ingress_channel`, `ingress_source` (e.g., "k1.conversation")
- [ ] No side effects (pure classification from envelope)
- [ ] `idempotent: true`

##### Estimated Effort

- **Total**: 2 hours

##### Dependencies

- **Blocks**: None
- **Blocked By**: Issue 1.3.1

---

#### Issue 1.3.4: Create context.retention_lookup.v1.yaml (M11) + context.geo_metadata.v1.yaml (M12)

**Priority**: 🟡 Medium
**Size**: M (2.5 hours for both)
**Assignee**: TBD

##### Context References

**Primary Sources**:

- **P02 Dossier**: Lines 403-406 (M11, M12 mapping), Lines 266-278 (R2.2 Privacy)
- **Related ADRs**: `k007.4-retention-lookup.md`, `k007.5-geo-metadata.md` (to be created in M2)

##### Master Document Tracking (MANDATORY)

**Update Locations**:

1. **Part 5.1**: Add both contract entries
2. **Part 3.1**: Update M11, M12 status

##### Deliverables

- [ ] Create: `k0/contracts/modules/context.retention_lookup.v1.yaml`
- [ ] Create: `k0/contracts/modules/context.geo_metadata.v1.yaml`
- [ ] Update Master Doc sections (both)
- [ ] Validate both YAMLs

##### Acceptance Criteria - M11 (Retention)

- [ ] `module_id: context.retention_lookup`
- [ ] `latency_budget_ms: 3`
- [ ] Input: `(band, topic, device_kind)`
- [ ] Output: `retention_policy_id`, `retention_bucket`
- [ ] `side_effects`: `read:st_retention_policy`

##### Acceptance Criteria - M12 (Geo Metadata)

- [ ] `module_id: context.geo_metadata`
- [ ] `latency_budget_ms: 2`
- [ ] Output: `geo_precision_external`, `geo_masking_reason`
- [ ] Read-only (no re-masking)
- [ ] `side_effects`: None (reads from envelope `policy_stamp`)

##### Estimated Effort

- **M11**: 1.5 hours
- **M12**: 1 hour
- **Total**: 2.5 hours

##### Dependencies

- **Blocks**: Issue 1.4.1
- **Blocked By**: Issue 1.3.1

---

#### Issue 1.3.5: Create context.spatial_minimal.v1.yaml (M15)

**Priority**: 🟡 Medium
**Size**: S (1 hour)
**Assignee**: TBD

##### Context References

**Primary Sources**:

- **P02 Dossier**: Lines 411-414 (M15 mapping), Lines 280-288 (R2.4 Spatial)

##### Master Document Tracking (MANDATORY)

**Update Locations**:

1. **Part 5.1**: Add `context.spatial_minimal:v1` entry
2. **Part 3.1**: Update M15 status

##### Deliverables

- [ ] Create: `k0/contracts/modules/context.spatial_minimal.v1.yaml`
- [ ] Update Master Doc sections
- [ ] Validate YAML

##### Acceptance Criteria

- [ ] `module_id: context.spatial_minimal`
- [ ] `latency_budget_ms: 1` (copy fields)
- [ ] Output: `location_name`, `location_type`, `geohash_6`
- [ ] No geo enrichment (defer to P09)
- [ ] Pure copy from envelope

##### Estimated Effort

- **Total**: 1.5 hours

##### Dependencies

- **Blocks**: Issue 1.4.1
- **Blocked By**: Issue 1.3.1

---

### Epic 1.4: Social & Builder Contracts (M07, M13-M14)

**Focus**: Family graph, row builder, embedding queue writer

---

#### Issue 1.4.1: Create social.resolve_family.v1.yaml (M07)

**Priority**: 🔴 Critical
**Size**: M (2 hours)
**Assignee**: TBD

##### Context References

**Primary Sources**:

- **P02 Dossier**: Lines 415-418 (M07 mapping), Lines 290-304 (R2.5 Social Graph)
- **Data Schema**: Lines 141-147 (social columns), Lines 375-445 (st_relationships table)
- **Related ADR**: `k008.1-family-graph-resolver.md` (to be created in M2)

##### Master Document Tracking (MANDATORY)

**Update Locations**:

1. **Part 5.1**: Add `social.resolve_family:v1` entry
2. **Part 3.1**: Update M07 status

##### Deliverables

- [ ] Create: `k0/contracts/modules/social.resolve_family.v1.yaml`
- [ ] Update Master Doc sections
- [ ] Validate YAML

##### Acceptance Criteria

- [ ] `module_id: social.resolve_family`
- [ ] `latency_budget_ms: 10` (graph lookup)
- [ ] Output: `num_participants`, `participant_roles_json`, `social_context`, `social_intimacy`, `has_partner_present`, `has_parent_present`, `is_solo_event`
- [ ] `side_effects`: `read:st_relationships`, `read:people`, `read:households`
- [ ] Relationship types: SPOUSE_OF, PARENT_OF, CHILD_OF, CARETAKER_OF, SIBLING_OF
- [ ] `idempotent: true`

##### Estimated Effort

- **Total**: 2.5 hours

##### Dependencies

- **Blocks**: Issue 1.4.2
- **Blocked By**: Issue 1.3.1

---

#### Issue 1.4.2: Create builders.hipp_events_row.v1.yaml (M13)

**Priority**: 🔴 Critical
**Size**: L (3 hours)
**Assignee**: TBD

##### Context References

**Primary Sources**:

- **P02 Dossier**: Lines 419-422 (M13 mapping), Lines 306-314 (R3 Build Row)
- **Data Schema**: Lines 45-185 (complete st_hipp_events schema - 60-70 columns)
- **Related ADR**: `k009.1-hipp-events-builder.md` (to be created in M2)

##### Master Document Tracking (MANDATORY)

**Update Locations**:

1. **Part 5.1**: Add `builders.hipp_events_row:v1` entry
2. **Part 3.1**: Update M13 status

##### Deliverables

- [ ] Create: `k0/contracts/modules/builders.hipp_events_row.v1.yaml`
- [ ] Update Master Doc sections
- [ ] Validate YAML

##### Acceptance Criteria

- [ ] `module_id: builders.hipp_events_row`
- [ ] `latency_budget_ms: 10` (assembly only, no I/O)
- [ ] Combines outputs from all upstream modules (M01-M12, M15)
- [ ] Maps to st_hipp_events 60-70 column schema
- [ ] Output: Complete row dict ready for INSERT
- [ ] No side effects (pure data transformation)
- [ ] `idempotent: true`

##### Estimated Effort

- **Total**: 3.5 hours (complex mapping)

##### Dependencies

- **Blocks**: Issue 1.5.1 (writer)
- **Blocked By**: Issues 1.2.3, 1.3.5, 1.4.1 (needs all upstream outputs)

---

#### Issue 1.4.3: Create builders.embedding_queue.v1.yaml (M14)

**Priority**: 🔴 Critical
**Size**: M (2 hours)
**Assignee**: TBD

##### Context References

**Primary Sources**:

- **P02 Dossier**: Lines 423-426 (M14 mapping)
- **Data Schema**: Lines 250-280 (st_embedding_queue schema)
- **Related ADR**: `k009.2-embedding-queue-writer.md` (to be created in M2)

##### Master Document Tracking (MANDATORY)

**Update Locations**:

1. **Part 5.1**: Add `builders.embedding_queue:v1` entry
2. **Part 3.1**: Update M14 status

##### Deliverables

- [ ] Create: `k0/contracts/modules/builders.embedding_queue.v1.yaml`
- [ ] Update Master Doc sections
- [ ] Validate YAML

##### Acceptance Criteria

- [ ] `module_id: builders.embedding_queue`
- [ ] `latency_budget_ms: 5`
- [ ] Output: Job row dict with `status='PENDING'`, `attempt_count=0`
- [ ] Links: `wal_pos`, `event_id`, `embedding_id`
- [ ] No side effects (builder only)
- [ ] `idempotent: true`

##### Estimated Effort

- **Total**: 2.5 hours

##### Dependencies

- **Blocks**: Issue 1.5.1 (writer needs both row builders)
- **Blocked By**: Issue 1.1.2 (needs embedding_id from M02)

---

### Epic 1.5: Core Writer & Emitter Contracts (M16-M17)

**Focus**: Database commit and event emission

---

#### Issue 1.5.1: Create core.hipp_events_writer.v1.yaml (M16)

**Priority**: 🔴 Critical (blocks P02 completion)
**Size**: M (2.5 hours)
**Assignee**: TBD

##### Context References

**Primary Sources**:

- **P02 Dossier**: Lines 427-430 (M16 mapping), Lines 316-336 (R4 Storage Write)
- **Data Schema**: Lines 447-485 (UnitOfWork transaction pattern)

##### Master Document Tracking (MANDATORY)

**Update Locations**:

1. **Part 5.1**: Add `core.hipp_events_writer:v1` entry
2. **Part 3.1**: Update M16 status

##### Deliverables

- [ ] Create: `k0/contracts/modules/core.hipp_events_writer.v1.yaml`
- [ ] Update Master Doc sections
- [ ] Validate YAML

##### Acceptance Criteria

- [ ] `module_id: core.hipp_events_writer`
- [ ] `latency_budget_ms: 50` (database transaction)
- [ ] `side_effects`:
  - `write:st_hipp_events`
  - `write:st_embedding_queue`
  - `write:st_pipeline_processed`
- [ ] Atomic UnitOfWork (all 3 writes succeed or fail together)
- [ ] `idempotent: true` (can retry on failure)

##### Estimated Effort

- **Total**: 3 hours

##### Dependencies

- **Blocks**: Issue 1.5.2 (emitter)
- **Blocked By**: Issues 1.4.2, 1.4.3 (needs both row builders)

---

#### Issue 1.5.2: Create core.event_emitter.v1.yaml (M17)

**Priority**: 🔴 Critical (last contract)
**Size**: M (2 hours)
**Assignee**: TBD

##### Context References

**Primary Sources**:

- **P02 Dossier**: Lines 431-434 (M17 mapping), Lines 320-326 (Event Emission)

##### Master Document Tracking (MANDATORY)

**Update Locations**:

1. **Part 5.1**: Add `core.event_emitter:v1` entry
2. **Part 3.1**: Update M17 status

##### Deliverables

- [ ] Create: `k0/contracts/modules/core.event_emitter.v1.yaml`
- [ ] Update Master Doc sections
- [ ] Validate YAML

##### Acceptance Criteria

- [ ] `module_id: core.event_emitter`
- [ ] `latency_budget_ms: 10`
- [ ] `output_event_types`: List all 6 exit topics:
  - `workspace.wm.updated.v1`
  - `core.affect.analyzed.v1`
  - `space.resolution.complete.v1`
  - `embedding.enqueue.v1`
  - `p02.hippocampus.pattern_separated.v1`
  - `p02.write.complete.v1`
- [ ] `side_effects`: `write:st_outbox` (via syscalls.outbox_emit)
- [ ] `idempotent: true`

##### Estimated Effort

- **Total**: 2.5 hours

##### Dependencies

- **Blocks**: Milestone 2 (ADRs can start after all contracts created)
- **Blocked By**: Issue 1.5.1

---

### Milestone 1 Summary

**Total Contracts**: 17 YAML files
**Total Effort**: ~35-40 hours (3-4 days for 1 developer)
**Critical Path**: Issue 1.1.1 → 1.1.2 → 1.2.1 → 1.2.2 → 1.3.1 → 1.4.1 → 1.4.2 → 1.5.1 → 1.5.2

**Completion Criteria**:

- [ ] All 17 YAML files created in `k0/contracts/modules/`
- [ ] Part 5.1 (Contract Registry) has 17 entries with ✅ status
- [ ] Part 3.1 (Module Registry) shows all modules at "🎯 Planning" status
- [ ] All YAMLs validate against Pydantic schema
- [ ] No broken cross-references in master document

**Next**: Proceed to Milestone 2 (ADRs) after all contracts complete

---

## Milestone 2: Architectural Decision Records (ADRs)

**Goal**: Create 17 ADR documents that explain design rationale, alternatives considered, and consequences for all P02 modules.

**Status**: 📝 Not Started
**Duration**: 4-5 days
**Effort**: ~30-35 hours (17 ADRs × 1.5-2h each)
**Prerequisites**:

- ✅ Milestone 1 complete (all contracts defined)
- ✅ ADR template available (docs/architecture/decisions-K0/template.md)
- ✅ Master document structure understood

### Epic 2.1: Hippocampus ADRs (M01-M02)

**Status**: ✅ COMPLETE (2025-11-16)

---

#### Issue 2.1.0: Create Parent ADR - k003-hippocampus-architecture.md

**Priority**: 🔴 Critical (foundational ADR)
**Size**: XL (6 hours)
**Status**: ✅ COMPLETE (2025-11-16)

##### Deliverables

- [x] Create file: `docs/architecture/decisions-K0/modules/k003-hippocampus-architecture.md` (954 lines)
- [x] Comprehensive ADR with neuroscience grounding (10 research citations)
- [x] 5 alternatives analyzed with detailed pros/cons
- [x] Performance analysis and consequences documented
- [x] Testing strategy with code examples
- [x] Implementation roadmap (4 phases, 6 weeks)

##### Acceptance Criteria

- [x] **Title**: "k003 - Hippocampus Architecture - Episodic Memory Encoding System"
- [x] **Status**: Accepted
- [x] **Context**: Neuroscience insights, biological principles, performance constraints
- [x] **Decision**: DG + CA1 + CA3 architecture with detailed algorithms
- [x] **Alternatives**: 5 alternatives (embedding-only, hash-only, database dedup, LLM-based, no pattern separation)
- [x] **Consequences**: Positive and negative impacts with mitigations
- [x] **Research Citations**: 10 papers (Marr 1971, McClelland 1995, Broder 1997, etc.)
- [x] Approved by user

---

#### Issue 2.1.1: Create ADR - k003.1-dg-pattern-separation.md (M01)

**Priority**: 🔴 Critical (first ADR sets pattern)
**Size**: L (3 hours)
**Status**: ✅ COMPLETE (2025-11-16)

##### Context References

**Primary Sources**:

- **Contract Created**: `k0/contracts/modules/hippocampus.pattern_separate.v1.yaml` (from Issue 1.1.1)
- **P02 Dossier**: Lines 195-221 (R1.1 Pattern Separation full spec)
- **Data Schema**: Lines 160-167 (hippocampus columns)
- **ADR Template**: `docs/architecture/decisions-K0/template.md`
- **Existing ADRs**: Browse `docs/architecture/decisions-K0/modules/` for format examples

**Supporting Context**:

- **SimHash Algorithm**: Research LSH, MinHash, SimHash trade-offs
- **Novelty Scoring**: Why deferred to P03 (not in P02 write path)
- **Performance Target**: 15ms P95 justification

##### Master Document Tracking (MANDATORY)

**Update Locations**:

1. **Part 7.1: ADR Registry**
   - File: `k0/pipelines/k0_architecture_master.md` (search for "Part 7.1")
   - Action: Add row:

     ```markdown
     | k003.1 | DG Pattern Separation | k003.1-dg-pattern-separation.md | M01 | ✅ Accepted | 2025-11-16 | Defines SimHash+MinHash fingerprinting for write path |
     ```

2. **Part 2.1: Pipeline Registry**
   - File: `k0/pipelines/k0_architecture_master.md` (search for "Part 2.1")
   - Action: Update P02 row ADR count: Increment from 0 to 1
   - Add ADR link in P02 supporting ADRs list

3. **Part 3.1: Module Master Registry**
   - Update M01: Status to "📋 ADR Complete", link to k003.1

##### Deliverables

- [x] Create file: `docs/architecture/decisions-K0/modules/k003.1-dg-pattern-separation.md` (650 lines)
- [x] Comprehensive sub-ADR with SimHash + MinHash algorithms
- [x] 4 alternatives analyzed (embedding-only, hash-only, database trigram, perceptual hashing)
- [x] Performance budget breakdown (15ms P95)
- [x] Testing strategy with unit/integration tests
- [ ] Update Master Doc Part 7.1 (ADR Registry)
- [ ] Update Master Doc Part 2.1 (Pipeline ADR count)
- [ ] Update Master Doc Part 3.1 (Module M01 status)

##### Acceptance Criteria

**ADR Structure** (follows template):

- [x] **Title**: "k003.1 - DG Pattern Separation - SimHash and MinHash Implementation"
- [x] **Status**: Accepted
- [x] **Date**: 2025-11-16
- [x] **Context**: Comprehensive explanation with:
  - Pattern separation problem, biological inspiration (DG sparsity)
  - Performance requirements (≤15ms P95)
  - Why novelty deferred to P03
  - SimHash + MinHash properties
- [x] **Decision**: Hybrid SimHash (64-bit) + MinHash (32 permutations)
- [x] **Alternatives Considered**: 4 alternatives:
  1. Full embedding comparison (rejected: 200-500ms latency)
  2. SimHash only (rejected: O(n) neighbor queries)
  3. Database trigram indexing (rejected: exact match only)
  4. Perceptual hashing (rejected: not applicable to text)
- [x] **Consequences**: Positive and negative impacts:
  - ✅ Fast write path (<15ms P95)
  - ✅ Scalable P03 queries (O(log n) LSH)
  - ✅ Deterministic & idempotent
  - ✅ Storage efficient (146× smaller than embeddings)
  - ⚠️ 8-10% false positive rate
  - ⚠️ Delayed novelty scoring
  - ⚠️ Text-only (no multi-modal)
- [x] **Implementation Notes**: Links to contract, research citations
- [x] **Related Decisions**: Links to k003, k003.2, k003.3

**Technical Depth**:

- [x] SimHash algorithm explained (3-gram shingles, MurmurHash3, bit vectors)
- [x] MinHash permutation count justified (32 = 92% recall, 8% collision rate)
- [x] Performance budget breakdown: 15ms total (canonicalization 1ms, tokenization 2ms, SimHash 5ms, MinHash 7ms)
- [x] Idempotency guarantee explained (deterministic hashing)

**Master Document Validation**:

- [ ] ADR appears in Part 7.1 registry with ✅ Accepted status
- [ ] P02 pipeline in Part 2.1 shows ADR count = 1
- [ ] M01 in Part 3.1 shows status "📋 ADR Complete"
- [ ] All file paths valid (ADR file exists)

##### Implementation Steps

1. **Read Context**

   ```powershell
   # Review contract created in M1
   Get-Content k0\contracts\modules\hippocampus.pattern_separate.v1.yaml

   # Read dossier section
   Get-Content docs\pipelines\P02_write_dossier.md | Select-Object -Skip 194 -First 27

   # Check ADR template
   Get-Content docs\architecture\decisions-K0\template.md
   ```

2. **Research Alternatives**
   - Document why embeddings too slow for write path
   - Explain SimHash vs. MinHash trade-offs
   - Justify 32-permutation choice for MinHash

3. **Write ADR**
   - Use template structure
   - Include code snippets if helpful (pseudocode for hash computation)
   - Link to contract YAML
   - Explain P02/P03 separation clearly

4. **Update Master Document**
   - Open `k0/pipelines/k0_architecture_master.md`
   - Add row to Part 7.1 (ADR Registry)
   - Update Part 2.1 (P02 ADR count)
   - Update Part 3.1 (M01 status + link)
   - Save file

5. **Validate**
   - Ensure all links valid
   - Check ADR follows template structure
   - Verify master document tables updated correctly

##### Estimated Effort

- **Research**: 1 hour (SimHash/MinHash algorithms)
- **ADR Writing**: 1.5 hours (full sections)
- **Master Doc Updates**: 30 minutes (3 sections)
- **Review**: 30 minutes (peer review + revisions)
- **Total**: 3.5 hours

##### Dependencies

- **Blocks**: Issue 2.1.2 (CA1 semantic ADR)
- **Blocked By**: Issue 1.1.1 (contract must exist first)

##### Notes

- **First ADR** in this milestone - sets quality bar
- Keep technical depth high (this is architecture documentation)
- Explain P02/P03 separation clearly (common confusion point)
- SimHash collision rate acceptable for write path (P03 handles fine-grained matching)

---

#### Issue 2.1.2: Create ADR - k003.2-ca1-semantic-bridge.md (M02)

**Status**: ✅ COMPLETE (2025-11-16)
**Priority**: 🔴 Critical
**Size**: L (3 hours)
**Assignee**: TBD

##### Context References

**Primary Sources**:

- **Contract**: `k0/contracts/modules/hippocampus.semantic_project.v1.yaml` (Issue 1.1.2)
- **P02 Dossier**: Lines 223-235 (R1.3 Semantic Projection)
- **Data Schema**: Lines 168-171 (embeddings, KG columns), Lines 250-280 (st_embedding_queue)
- **ADR Template**: `docs/architecture/decisions-K0/template.md`

##### Master Document Tracking (MANDATORY)

**Update Locations**:

1. **Part 7.1**: Add `k003.2 | CA1 Semantic Bridge | k003.2-ca1-semantic-bridge.md | M02 | ✅ Accepted`
2. **Part 2.1**: P02 ADR count = 3 (updated from 2)
3. **Part 3.1**: M02 status to "📋 ADR Complete"

##### Deliverables

- [x] Create: `docs/architecture/decisions-K0/modules/k003.2-ca1-semantic-bridge.md` (700 lines)
- [ ] Update Master Doc Parts 7.1, 2.1, 3.1 (pending)
- [x] Comprehensive sub-ADR with spaCy NER + KG templates
- [x] 4 alternatives analyzed (LLM-based, regex-based, external NER, immediate embeddings)
- [x] Performance budget defined (20ms P95)
- [x] Testing strategy with code examples

##### Acceptance Criteria

**ADR Structure**:

- [x] **Title**: "k003.2 - CA1 Semantic Bridge (Semantic Projection)"
- [x] **Status**: ACCEPTED
- [x] **Date**: 2025-11-16
- [x] **Context**: Explains:
  - Why P02 extracts entities (people, places, orgs) synchronously
  - Why embeddings deferred to P08 (async job queue)
  - Entity extraction vs. full NLP pipeline trade-off
  - KG triple format (subject, predicate, object)
  - Biological inspiration (CA1 neocortex bridge)
- [x] **Decision**: Entity extraction in write path, embeddings async
- [x] **Alternatives Considered**: 4 alternatives with detailed pros/cons:
  1. LLM-based extraction (GPT-4) - rejected: 200-500ms latency
  2. Regex-based extraction - rejected: brittle, low accuracy
  3. External NER service - rejected: network latency + privacy
  4. Immediate embeddings - rejected: blocks write path
- [x] **Consequences**:
  - ✅ Fast write path (<20ms for entity extraction)
  - ✅ Structured KG data available immediately
  - ✅ Privacy-preserving (local spaCy model)
  - ✅ Embedding decoupling (P08 handles GPU inference)
  - ⚠️ 80% accuracy (spaCy NER limitations)
  - ⚠️ Embeddings delayed (eventual consistency)
  - ⚠️ Template brittleness (hardcoded rules)
- [x] **Implementation Notes**: Includes roadmap with 3 phases over 3 weeks
- [x] **Related Decisions**: Links to k003 parent ADR

**Technical Depth**:

- [x] **Entity extraction algorithm**: spaCy `en_core_web_sm` model with 5-step process (load model → parse → filter entities → resolve → format)
- [x] **KG triple schema**: Activity templates, participant templates, location templates with subject-predicate-object structure
- [x] **Embedding job payload**: st_embedding_queue table with event_id, text, created_at, processed_at columns
- [x] **Latency budget breakdown**: 20ms P95 (10ms NER + 5ms KG generation + 5ms queue insertion)
- [x] **Idempotency**: Guaranteed via deduplication on event_id before queue insertion

**Master Document Validation**:

- [ ] ADR in Part 7.1 with ✅ status (pending)
- [ ] P02 ADR count = 3 in Part 2.1 (pending)
- [ ] M02 status updated in Part 3.1 (pending)

##### Implementation Steps

1. Read contract + dossier sections
2. Research entity extraction options (spaCy, custom, LLM-based)
3. Write ADR with focus on sync/async split
4. Update master document (3 sections)
5. Peer review

##### Estimated Effort

- **Total**: 3.5 hours

##### Dependencies

- **Blocks**: Issue 2.2.0 (affect parent ADR)
- **Blocked By**: Issue 2.1.1 (pattern established)

---

#### Issue 2.1.3: Create ADR - k003.3-ca3-clustering-service.md (M03)

**Status**: ✅ COMPLETE (2025-11-16)
**Priority**: 🔴 Critical
**Size**: L (3 hours)
**Assignee**: TBD

##### Context References

**Primary Sources**:

- **Contract**: `k0/contracts/modules/hippocampus.ca3_cluster.v1.yaml`
- **P02 Dossier**: Lines 220-222 (R1.2 Clustering - Deferred to P03)
- **Parent ADR**: k003 (Hippocampus Architecture)

##### Master Document Tracking (MANDATORY)

**Update Locations**:

1. **Part 7.1**: Add `k003.3 | CA3 Clustering Service | k003.3-ca3-clustering-service.md | M03 | ✅ Accepted`
2. **Part 2.1**: P03 ADR count (CA3 is P03 scope, not P02)
3. **Part 3.1**: M03 status to "📋 ADR Complete"

##### Deliverables

- [x] Create: `docs/architecture/decisions-K0/modules/k003.3-ca3-clustering-service.md` (650 lines)
- [ ] Update Master Doc Parts 7.1, 3.1 (pending)
- [x] Comprehensive sub-ADR with LSH indexing, Hamming distance, Jaccard similarity
- [x] Greedy agglomerative clustering algorithm (upgradeable to DBSCAN)
- [x] 4 alternatives analyzed (cluster in P02, embedding-based, no clustering, DBSCAN)
- [x] Performance analysis for background processing (10K events/day, <500MB memory)
- [x] Testing strategy with code examples

##### Acceptance Criteria

**ADR Structure**:

- [x] **Title**: "k003.3 - CA3 Clustering Service (Pattern Discovery)"
- [x] **Status**: ACCEPTED
- [x] **Date**: 2025-11-16
- [x] **Context**: Explains:
  - Episode clustering problem (near-duplicates, pattern discovery)
  - Biological inspiration (CA3 autoassociative network)
  - Background processing (no strict P95 latency)
  - Why not cluster in P02 write path
- [x] **Decision**: Three-phase clustering (Hamming distance ≤4 bits, Jaccard >0.8, greedy agglomerative)
- [x] **Alternatives Considered**: 4 alternatives with detailed pros/cons:
  1. Cluster in P02 write path - rejected: O(n) queries block write path
  2. Embedding-based clustering - rejected: blocks on P08, 73× larger storage
  3. No clustering (flat storage) - rejected: no novelty detection, poor UX
  4. DBSCAN clustering - deferred to v2 (greedy simpler, deterministic)
- [x] **Consequences**:
  - ✅ Background processing eliminates write-path latency
  - ✅ LSH indexing enables O(log n) neighbor queries
  - ✅ Novelty scoring enables smart consolidation (P03)
  - ✅ Deterministic clustering (greedy algorithm)
  - ⚠️ Eventual consistency (cluster IDs NULL until P03 runs)
  - ⚠️ Greedy clustering order-dependent
  - ⚠️ Fixed threshold (0.8 Jaccard) may miss boundaries
  - ⚠️ No hierarchical clustering (flat clusters only)
- [x] **Implementation Notes**: 3-phase roadmap (near-duplicates, clustering, P03 integration)
- [x] **Related Decisions**: Links to k003, k003.1 (provides fingerprints)

**Technical Depth**:

- [x] **Hamming distance neighbor queries**: ≤4 bits threshold, LSH bucketing for O(log n)
- [x] **Jaccard similarity via MinHash**: 32 permutations, >0.8 threshold for clustering
- [x] **Greedy agglomerative clustering**: Chronological processing, assign to first cluster >0.8 similarity
- [x] **Novelty scoring**: 1.0 - max_similarity (0.0 = duplicate, 1.0 = novel)
- [x] **Performance budget**: 10K events/day, <500MB memory, no strict P95 (background)
- [x] **LSH indexing**: 16 buckets using 4-bit prefix, 100-1000× speedup

**Master Document Validation**:

- [ ] ADR in Part 7.1 with ✅ status (pending)
- [ ] M03 status updated in Part 3.1 (pending)

---

### Epic 2.2: Cognition ADRs (M04-M06)

**Status**: ✅ COMPLETE (2025-11-16)

---

#### Issue 2.2.0: Create Parent ADR - k004-affect-service.md (M04)

**Status**: ✅ COMPLETE (2025-11-16)
**Priority**: 🔴 Critical (foundational ADR)
**Size**: XL (6 hours)

##### Deliverables

- [x] Create file: `docs/architecture/decisions-K0/modules/k004-affect-service.md` (850 lines)
- [x] Comprehensive parent ADR with Russell's circumplex model, two-tier strategy
- [x] 4 alternatives analyzed with detailed pros/cons
- [x] Performance budget breakdown (Tier-0 <2ms, Tier-1 <60ms, overall 70ms P95)
- [x] Testing strategy with code examples
- [x] Implementation roadmap (3 phases, 5 weeks)

##### Acceptance Criteria

- [x] **Title**: "k004 - Affect Service Architecture (Emotional Classification System)"
- [x] **Status**: Accepted
- [x] **Context**: Russell's circumplex model (valence × arousal), two-tier latency strategy, biological inspiration (dual-process emotion)
- [x] **Decision**: Two-tier strategy (Tier-0 lexicon <2ms, Tier-1 ML <60ms), affect band classification (GREEN/AMBER/RED)
- [x] **Alternatives**: 4 alternatives (full transformer, lexicon-only, no affect, emoji-based) rejected
- [x] **Consequences**: Positive and negative impacts with mitigations
- [x] **Research Citations**: 5 papers (Russell 1980, Ekman 1992, LeDoux 2000, Barrett 2017, Hutto 2014)
- [x] **Sub-ADRs**: Links to k004.1, k004.2, k004.3
- [x] Approved

---

#### Issue 2.2.1: Create ADR - k004.1-tier0-fast-affect.md (M04)

**Status**: ✅ COMPLETE (2025-11-16)
**Priority**: 🔴 Critical
**Size**: L (3 hours)
**Assignee**: TBD

##### Context References

**Primary Sources**:

- **Contract**: `k0/contracts/modules/affect.analyze.v1.yaml` (Issue 1.2.1)
- **P02 Dossier**: Lines 237-248 (R1.4 Affect Classification)
- **Data Schema**: Lines 172-178 (affect columns)

##### Master Document Tracking (MANDATORY)

**Update Locations**:

1. **Part 7.1**: Add `k004.1 | Tier-0 Fast Affect Classification | k004.1-tier0-fast-affect.md | M04 | ✅ Accepted`
2. **Part 2.1**: P02 ADR count = 3
3. **Part 3.1**: M04 status to "📋 ADR Complete"

##### Deliverables

- [x] Create: `docs/architecture/decisions-K0/modules/k004.1-tier0-fast-affect.md` (600 lines)
- [ ] Update Master Doc sections (pending)
- [x] Comprehensive sub-ADR with VADER lexicon approach
- [x] 3 alternatives analyzed (TextBlob, AFINN, custom lexicon)
- [x] Performance budget <2ms P99
- [x] Testing strategy with code examples

##### Acceptance Criteria

**ADR Structure**:

- [x] **Title**: "k004.1 - Tier-0 Fast Affect Classification (Lexicon-Based)"
- [x] **Status**: ACCEPTED
- [x] **Date**: 2025-11-16
- [x] **Context**: Explains:
  - Two-tier affect model (Tier-0 <2ms, Tier-1 <60ms)
  - VADER algorithm (7,500 word lexicon, intensity boosters, negation handling)
  - Valence/arousal mapping from compound score
  - Complexity detection (fallback to Tier-1)
- [x] **Decision**: VADER lexicon-based sentiment for 90% of events (<2ms latency)
- [x] **Alternatives Considered**:
  1. TextBlob - rejected: lower accuracy on social media text, slower (~3ms)
  2. AFINN lexicon - rejected: smaller lexicon (2,477 words), no negation handling
  3. Custom family lexicon - deferred to v2
- [x] **Consequences**:
  - ✅ <2ms latency keeps write path fast
  - ✅ Deterministic and reproducible
  - ✅ No GPU dependency (cost savings)
  - ✅ 73% accuracy sufficient for salience scoring
  - ⚠️ Lower accuracy than ML (73% vs 87%)
  - ⚠️ Poor handling of sarcasm/irony
  - ⚠️ Negation edge cases
  - ⚠️ No contextual understanding

**Technical Details**:

- [x] **Valence/arousal mapping**: (compound + 1.0) / 2.0 → valence; pos + neg → arousal
- [x] **Affect band thresholds**: valence ≥0.5 = GREEN, 0.3-0.5 = AMBER, <0.3 = RED
- [x] **Complexity detection**: >50 words, mixed emotions, sarcasm, complex negation → Tier-1 fallback
- [x] **Latency budget**: <2ms P99 (0.3ms preprocessing + 1.0ms VADER + 0.5ms mapping)
- [x] **Event coverage**: 90% Tier-0, 10% Tier-1 fallback

**Master Document Validation**:

- [ ] ADR in Part 7.1 with ✅ (pending)
- [ ] M04 status updated in Part 3.1 (pending)

---

#### Issue 2.2.2: Create ADR - k004.2-multimodal-affect.md (M04 Future)

**Status**: ✅ COMPLETE (2025-11-16)
**Priority**: 🗳️ Low (future work)
**Size**: L (3 hours)
**Assignee**: TBD

##### Context References

**Primary Sources**:

- **Parent ADR**: k004 (Affect Service Architecture)
- **Future Pipeline**: P08 (Multimodal Processing)

##### Master Document Tracking (MANDATORY)

**Update Locations**:

1. **Part 7.1**: Add `k004.2 | Multi-Modal Affect Classification | k004.2-multimodal-affect.md | M04 | ✅ Accepted`
2. **Part 3.1**: M04 notes section to mention multimodal future extension

##### Deliverables

- [x] Create: `docs/architecture/decisions-K0/modules/k004.2-multimodal-affect.md` (600 lines)
- [ ] Update Master Doc Parts 7.1, 3.1 (pending)
- [x] Comprehensive future-focused ADR with facial expression, voice tone, biometric analysis
- [x] Late fusion architecture (attention-weighted averaging)
- [x] 3 alternatives analyzed (early fusion, hierarchical fusion, immediate P02 fusion)
- [x] Implementation roadmap (3 phases, Q2-Q4 2026)

##### Acceptance Criteria

**ADR Structure**:

- [x] **Title**: "k004.2 - Multi-Modal Affect Classification (Future Extension)"
- [x] **Status**: PROPOSED (future work)
- [x] **Date**: 2025-11-16
- [x] **Context**: Explains:
  - Why multimodal affect (facial expressions, voice tone, biometrics)
  - Why not in P02 (500ms latency too high for write path)
  - Deferred to P08 background processing
  - Biological inspiration (multi-sensory emotion integration)
- [x] **Decision**: Late fusion architecture (text + image + audio + biometric)
- [x] **Alternatives Considered**:
  1. Early fusion (feature-level) - rejected: cannot handle missing modalities
  2. Hierarchical fusion - rejected: order-dependent, no clear hierarchy
  3. Immediate P02 fusion - rejected: 500ms blocks write path
- [x] **Consequences**:
  - ✅ Richer emotional context (facial + voice + biometric)
  - ✅ Late fusion handles missing modalities gracefully
  - ✅ Deferred to P08 (no write-path blocking)
  - ✅ Cross-modal consistency flags deception/masking
  - ⚠️ High latency (500ms) limits to background processing
  - ⚠️ Low coverage (30-60% events have images/audio)
  - ⚠️ Accuracy lower than text (70% facial, 60% voice)
  - ⚠️ Cultural and contextual biases
- [x] **Implementation Notes**: 3-phase roadmap (PoC Q2 2026, unimodal models Q3 2026, P08 integration Q4 2026)
- [x] **Related Decisions**: Links to k004, k004.1

**Technical Depth**:

- [x] **Facial expression CNN**: ResNet-50 on FER2013/AffectNet, 200-300ms latency
- [x] **Voice tone prosody**: RNN on RAVDESS, pitch/energy/tempo features, 150-250ms latency
- [x] **Biometric arousal**: Heart rate mapping (60-100 BPM → 0-1 arousal), <50ms
- [x] **Late fusion**: Attention-weighted averaging, modality confidence scores
- [x] **Cross-modal consistency**: Std deviation of valence/arousal scores across modalities
- [x] **Research citations**: Ekman 1978, Picard 1997, Baltrusaitis 2018, Poria 2017, Zadeh 2017

**Master Document Validation**:

- [ ] ADR in Part 7.1 with ✅ status (pending)

---

#### Issue 2.2.3: Create ADR - k005.1-acl-resolution.md (M05)

**Priority**: 🔴 Critical
**Size**: M (2.5 hours)
**Assignee**: TBD

##### Context References

**Primary Sources**:

- **Contract**: `k0/contracts/modules/space.resolve_visibility.v1.yaml` (Issue 1.2.2)
- **P02 Dossier**: Lines 252-264 (R2.1 Space Resolution)
- **Data Schema**: Lines 120-129 (policy columns)

##### Master Document Tracking (MANDATORY)

**Update Locations**:

1. **Part 7.1**: Add `k005.1 | ACL Resolution for Write Path | k005.1-acl-resolution.md | M05 | ✅ Accepted`
2. **Part 2.1**: P02 ADR count = 4
3. **Part 3.1**: M05 status to "📋 ADR Complete"

##### Deliverables

- [ ] Create: `docs/architecture/decisions-K0/modules/k005.1-acl-resolution.md`
- [ ] Update Master Doc sections
- [ ] Peer review

##### Acceptance Criteria

**ADR Content**:

- [ ] **Title**: "k005.1 - ACL Resolution and Visibility Intersection"
- [ ] **Context**: Explains:
  - Space-based ownership model (owner, co-owners)
  - Author role resolution (is author also owner/co-owner?)
  - Visibility intersection semantics (never expand beyond policy)
  - Cache-first design (<3ms target)
- [ ] **Decision**: Cache-optimized lookup with intersection logic
- [ ] **Alternatives**:
  1. Database join every event (rejected: too slow)
  2. No ACL in write path (rejected: security requirement)
  3. Expand visibility to all space members (rejected: violates least privilege)
  4. Chosen: Cache lookup + intersection
- [ ] **Consequences**:
  - ✅ <3ms P95 (cache hit)
  - ✅ Security guarantee: visibility ⊆ policy
  - ⚠️ Cache invalidation complexity
  - ⚠️ Cold cache penalty (10-20ms)

**Technical Details**:

- [ ] Intersection algorithm (set intersection of policy + space members)
- [ ] Cache key structure (space_id → members list)
- [ ] Role resolution (author_is_owner, author_is_co_owner flags)

**Master Document Validation**:

- [ ] ADR in Part 7.1
- [ ] P02 ADR count = 4
- [ ] M05 status updated

##### Implementation Steps

1. Read contract + space resolution logic
2. Design intersection semantics (never expand)
3. Write ADR with security focus
4. Update master document
5. Peer review

##### Estimated Effort

- **Total**: 3 hours

##### Dependencies

- **Blocks**: Issue 2.2.3 (salience ADR)
- **Blocked By**: Issue 2.2.1

---

#### Issue 2.2.3: Create ADR - k006.1-write-path-salience.md (M06)

**Priority**: 🟡 Medium
**Size**: M (2 hours)
**Assignee**: TBD

##### Context References

**Primary Sources**:

- **Contract**: `k0/contracts/modules/salience.score.v1.yaml` (Issue 1.2.3)
- **P02 Dossier**: Lines 250-256 (R1.5 Salience Scoring)

##### Master Document Tracking (MANDATORY)

**Update Locations**:

1. **Part 7.1**: Add `k006.1 | Write Path Salience Scoring | k006.1-write-path-salience.md | M06 | ✅ Accepted`
2. **Part 2.1**: P02 ADR count = 5
3. **Part 3.1**: M06 status to "📋 ADR Complete"

##### Deliverables

- [ ] Create: `docs/architecture/decisions-K0/modules/k006.1-write-path-salience.md`
- [ ] Update Master Doc sections
- [ ] Peer review

##### Acceptance Criteria

**ADR Content**:

- [ ] **Title**: "k006.1 - Salience Scoring Without Novelty"
- [ ] **Context**: Explains:
  - Salience formula: `0.50×social + 0.40×affect + 0.10×recency`
  - Why novelty excluded from P02 (deferred to P03)
  - Social signal = num_participants + intimacy score
  - Affect signal = arousal (0-1)
  - Recency signal = time-based decay
- [ ] **Decision**: 3-factor formula without novelty
- [ ] **Alternatives**:
  1. Include novelty in P02 (rejected: requires neighbor queries, too slow)
  2. Affect-only salience (rejected: misses social context)
  3. Machine learning model (rejected: latency + complexity)
  4. Chosen: Weighted formula with social + affect + recency
- [ ] **Consequences**:
  - ✅ <5ms P95 (pure computation)
  - ✅ Interpretable (weighted factors)
  - ⚠️ Novelty boost deferred to P03 (recompute salience later)
  - ⚠️ Formula weights may need tuning

**Technical Details**:

- [ ] Formula breakdown with examples
- [ ] Band thresholds (e.g., >0.7 = HIGH, 0.4-0.7 = MEDIUM, <0.4 = LOW)
- [ ] Reason generation (e.g., "High social intimacy", "Strong emotional arousal")

**Master Document Validation**:

- [ ] ADR in Part 7.1
- [ ] P02 ADR count = 5
- [ ] M06 status updated

##### Implementation Steps

1. Read contract + salience formula
2. Justify weight selection (0.50/0.40/0.10)
3. Write ADR with examples
4. Update master document
5. Peer review

##### Estimated Effort

- **Total**: 2.5 hours

##### Dependencies

- **Blocks**: Issue 2.3.1 (temporal ADR)
- **Blocked By**: Issue 2.2.2

---

### Epic 2.3: Context Enrichment ADRs (M08-M12, M15)

---

#### Issue 2.3.1: Create ADR - k007.1-temporal-profiler.md (M08)

**Status**: ✅ COMPLETE (2025-11-16)
**Priority**: 🔴 Critical
**Size**: M (2.5 hours)
**Assignee**: K0 Architecture Team

##### Context References

**Primary Sources**:

- **Contract**: `k0/contracts/modules/context.temporal_profile.v1.yaml` (Issue 1.3.1)
- **P02 Dossier**: Lines 266-278 (R2.3 Temporal Profiling)
- **Data Schema**: Lines 130-140 (11 temporal columns)

##### Master Document Tracking (MANDATORY)

**Update Locations**:

1. **Part 7.1**: Add `k007.1 | Temporal Profiler | k007.1-temporal-profiler.md | M08 | ✅ Accepted`
2. **Part 2.1**: P02 ADR count = 6
3. **Part 3.1**: M08 status to "📋 ADR Complete"

##### Deliverables

- [ ] Create: `docs/architecture/decisions-K0/modules/k007.1-temporal-profiler.md`
- [ ] Update Master Doc sections
- [ ] Peer review

##### Acceptance Criteria

**ADR Content**:

- [ ] **Title**: "k007.1 - Temporal Profiling for Query Optimization"
- [ ] **Context**: Explains:
  - 11 temporal dimensions (UTC, local date/time, day_of_week, etc.)
  - Timezone resolution from tenant config
  - Circadian slot bucketing (morning/afternoon/evening/night)
  - Write lag detection (event_time vs. write_time)
  - Backdating flag (write_lag > 60 seconds)
- [ ] **Decision**: Precompute all 11 temporal fields in write path
- [ ] **Alternatives**:
  1. Compute temporal fields on query (rejected: slow, repeated computation)
  2. Store only UTC, derive rest (rejected: loses precomputed indexes)
  3. Store only local time (rejected: loses UTC for global queries)
  4. Chosen: Precompute all dimensions for fast queries
- [ ] **Consequences**:
  - ✅ <5ms P95 (timezone math only)
  - ✅ Indexed columns for fast date range queries
  - ✅ Circadian analysis ready (for future mood tracking)
  - ⚠️ Storage overhead (11 columns per event)

**Technical Details**:

- [ ] Timezone lookup strategy (tenant config cache)
- [ ] Circadian slot boundaries (e.g., 06:00-12:00 = morning)
- [ ] Write lag threshold (60 seconds for backdating)
- [ ] Day of week calculation (ISO 8601 standard)

**Master Document Validation**:

- [ ] ADR in Part 7.1
- [ ] P02 ADR count = 6
- [ ] M08 status updated

##### Implementation Steps

1. Read contract + temporal responsibilities
2. Research query optimization patterns
3. Write ADR justifying 11-column overhead
4. Update master document
5. Peer review

##### Estimated Effort

- **Total**: 3 hours

##### Dependencies

- **Blocks**: Issue 2.3.2 (device profiler ADR)
- **Blocked By**: Issue 2.2.3

---

#### Issue 2.3.2: Create ADR - k007.2-device-profiler.md (M09)

**Status**: ✅ COMPLETE (2025-11-16)
**Priority**: 🟡 Medium
**Size**: S (1.5 hours)
**Assignee**: K0 Architecture Team

##### Context References

**Primary Sources**:

- **Contract**: `k0/contracts/modules/context.device_profile.v1.yaml` (Issue 1.3.2)
- **P02 Dossier**: Lines 268-270 (device context mention)

##### Master Document Tracking (MANDATORY)

**Update Locations**:

1. **Part 7.1**: Add `k007.2 | Device Profiler | k007.2-device-profiler.md | M09 | ✅ Accepted`
2. **Part 2.1**: P02 ADR count = 7
3. **Part 3.1**: M09 status to "📋 ADR Complete"

##### Deliverables

- [ ] Create: `docs/architecture/decisions-K0/modules/k007.2-device-profiler.md`
- [ ] Update Master Doc sections
- [ ] Peer review

##### Acceptance Criteria

**ADR Content**:

- [ ] **Title**: "k007.2 - Device Profiling for Multi-Device Families"
- [ ] **Context**: Explains:
  - Device kind classification (mobile, tablet, desktop, wearable, hub)
  - Primary device flag (actor's most-used device)
  - Device OS tracking (iOS, Android, Windows, etc.)
  - Use cases (device switching patterns, notification routing)
- [ ] **Decision**: Cache-based device lookup with primary device flag
- [ ] **Alternatives**:
  1. No device tracking (rejected: loses context for multi-device users)
  2. Query device table every event (rejected: adds latency)
  3. Chosen: Cache lookup from st_devices
- [ ] **Consequences**:
  - ✅ <3ms P95 (cache hit)
  - ✅ Enables device-switching analysis
  - ⚠️ Cache invalidation on device registration

**Master Document Validation**:

- [ ] ADR in Part 7.1
- [ ] P02 ADR count = 7
- [ ] M09 status updated

##### Implementation Steps

1. Read contract + device context
2. Design device kind taxonomy
3. Write ADR (shorter, simpler than temporal)
4. Update master document
5. Peer review

##### Estimated Effort

- **Total**: 2 hours

##### Dependencies

- **Blocks**: Issue 2.3.3
- **Blocked By**: Issue 2.3.1

---

#### Issue 2.3.3: Create ADR - k007.3-ingress-classifier.md (M10)

**Status**: ✅ COMPLETE (2025-11-16)
**Priority**: 🟡 Medium
**Size**: S (1.5 hours)
**Assignee**: K0 Architecture Team

##### Context References

**Primary Sources**:

- **Contract**: `k0/contracts/modules/context.ingress_classify.v1.yaml` (Issue 1.3.3)
- **P02 Dossier**: Lines 268-270 (ingress channel)

##### Master Document Tracking (MANDATORY)

**Update Locations**:

1. **Part 7.1**: Add `k007.3 | Ingress Classifier | k007.3-ingress-classifier.md | M10 | ✅ Accepted`
2. **Part 2.1**: P02 ADR count = 8
3. **Part 3.1**: M10 status to "📋 ADR Complete"

##### Deliverables

- [ ] Create: `docs/architecture/decisions-K0/modules/k007.3-ingress-classifier.md`
- [ ] Update Master Doc sections
- [ ] Peer review

##### Acceptance Criteria

**ADR Content**:

- [ ] **Title**: "k007.3 - Ingress Channel Classification"
- [ ] **Context**: Explains:
  - Channel types (k1.conversation, k1.journal, sms, email, calendar, etc.)
  - Source attribution (which pipeline/module created event)
  - Use cases (analytics, channel-specific queries)
- [ ] **Decision**: Rule-based classification from envelope metadata
- [ ] **Alternatives**:
  1. No ingress tracking (rejected: loses provenance)
  2. Infer from text content (rejected: unreliable)
  3. Chosen: Explicit envelope field + fallback rules
- [ ] **Consequences**:
  - ✅ <2ms P99 (no I/O)
  - ✅ Clear provenance for debugging
  - ⚠️ Requires envelope consistency

**Master Document Validation**:

- [ ] ADR in Part 7.1
- [ ] P02 ADR count = 8
- [ ] M10 status updated

##### Implementation Steps

1. Read contract + ingress logic
2. List all known channel types
3. Write ADR (short, simple classification)
4. Update master document
5. Peer review

##### Estimated Effort

- **Total**: 2 hours

##### Dependencies

- **Blocks**: Issue 2.3.4
- **Blocked By**: Issue 2.3.2

---

#### Issue 2.3.4: Create ADR - k007.4-retention-lookup.md (M11) + k007.5-geo-metadata.md (M12)

**Status**: ✅ COMPLETE (2025-11-16)
**Priority**: 🟡 Medium
**Size**: M (2.5 hours for both)
**Assignee**: K0 Architecture Team

##### Context References

**Primary Sources**:

- **Contracts**:
  - `k0/contracts/modules/context.retention_lookup.v1.yaml` (Issue 1.3.4)
  - `k0/contracts/modules/context.geo_metadata.v1.yaml` (Issue 1.3.4)
- **P02 Dossier**: Lines 266-278 (R2.2 Privacy + Retention)
- **Data Schema**: Lines 120-129 (retention, geo columns)

##### Master Document Tracking (MANDATORY)

**Update Locations**:

1. **Part 7.1**: Add 2 rows:
   - `k007.4 | Retention Policy Lookup | k007.4-retention-lookup.md | M11 | ✅ Accepted`
   - `k007.5 | Geo Metadata Passthrough | k007.5-geo-metadata.md | M12 | ✅ Accepted`
2. **Part 2.1**: P02 ADR count = 10
3. **Part 3.1**: M11, M12 status to "📋 ADR Complete"

##### Deliverables

- [ ] Create: `docs/architecture/decisions-K0/modules/k007.4-retention-lookup.md`
- [ ] Create: `docs/architecture/decisions-K0/modules/k007.5-geo-metadata.md`
- [ ] Update Master Doc sections (both ADRs)
- [ ] Peer review

##### Acceptance Criteria - M11 (Retention)

**ADR Content**:

- [ ] **Title**: "k007.4 - Retention Policy Lookup"
- [ ] **Context**: Explains:
  - Retention policy table (st_retention_policy)
  - Lookup key: (band, topic, device_kind)
  - Retention bucket assignment (e.g., "90_days", "forever")
  - Use cases (GDPR compliance, storage management)
- [ ] **Decision**: Cached lookup with default fallback
- [ ] **Alternatives**:
  1. Fixed retention per band (rejected: not flexible enough)
  2. User-configurable retention (rejected: too complex for MVP)
  3. Chosen: Policy table with (band, topic, device) key
- [ ] **Consequences**:
  - ✅ <3ms P95 (cache hit)
  - ✅ GDPR-ready architecture
  - ⚠️ Cache invalidation on policy updates

##### Acceptance Criteria - M12 (Geo Metadata)

**ADR Content**:

- [ ] **Title**: "k007.5 - Geo Metadata Passthrough (No Re-Masking)"
- [ ] **Context**: Explains:
  - Geo masking happens at ingress (K1 boundary)
  - P02 only reads existing geo precision level
  - No re-computation or coordinate access
  - Respects policy_stamp masking decisions
- [ ] **Decision**: Read-only passthrough of masked geo data
- [ ] **Alternatives**:
  1. Re-compute geo precision in P02 (rejected: violates single responsibility)
  2. Store raw coordinates (rejected: security/privacy risk)
  3. Chosen: Trust ingress masking, read masked fields only
- [ ] **Consequences**:
  - ✅ <2ms P99 (field copy only)
  - ✅ No duplicate masking logic
  - ⚠️ Relies on K1 ingress correctness

**Master Document Validation**:

- [ ] Both ADRs in Part 7.1
- [ ] P02 ADR count = 10
- [ ] M11, M12 status updated

##### Implementation Steps

1. Read both contracts + privacy section
2. Write M11 ADR (retention lookup)
3. Write M12 ADR (geo passthrough)
4. Update master document (2 rows + status updates)
5. Peer review

##### Estimated Effort

- **M11 ADR**: 1.5 hours
- **M12 ADR**: 1 hour
- **Total**: 2.5 hours

##### Dependencies

- **Blocks**: Issue 2.3.5
- **Blocked By**: Issue 2.3.3

---

#### Issue 2.3.5: Create ADR - k007.6-spatial-minimal.md (M15)

**Priority**: 🟡 Medium
**Size**: S (1 hour)
**Assignee**: TBD

##### Context References

**Primary Sources**:

- **Contract**: `k0/contracts/modules/context.spatial_minimal.v1.yaml` (Issue 1.3.5)
- **P02 Dossier**: Lines 280-288 (R2.4 Spatial)

##### Master Document Tracking (MANDATORY)

**Update Locations**:

1. **Part 7.1**: Add `k007.6 | Spatial Minimal (No Enrichment) | k007.6-spatial-minimal.md | M15 | ✅ Accepted`
2. **Part 2.1**: P02 ADR count = 11
3. **Part 3.1**: M15 status to "📋 ADR Complete"

##### Deliverables

- [ ] Create: `docs/architecture/decisions-K0/modules/k007.6-spatial-minimal.md`
- [ ] Update Master Doc sections
- [ ] Peer review

##### Acceptance Criteria

**ADR Content**:

- [ ] **Title**: "k007.6 - Spatial Minimal (Defer Enrichment to P09)"
- [ ] **Context**: Explains:
  - P02 only copies existing spatial fields (location_name, location_type, geohash_6)
  - No reverse geocoding or POI lookup
  - P09 handles full spatial enrichment (deferred for latency)
  - Geohash_6 sufficient for coarse queries (~1km precision)
- [ ] **Decision**: Copy spatial fields without enrichment
- [ ] **Alternatives**:
  1. Full spatial enrichment in P02 (rejected: adds 50-100ms latency)
  2. No spatial data in P02 (rejected: loses basic location context)
  3. Chosen: Minimal copy, defer enrichment to P09
- [ ] **Consequences**:
  - ✅ <1ms P99 (field copy)
  - ✅ Maintains write path speed
  - ⚠️ Limited spatial queries until P09 runs

**Master Document Validation**:

- [ ] ADR in Part 7.1
- [ ] P02 ADR count = 11
- [ ] M15 status updated

##### Implementation Steps

1. Read contract + spatial responsibilities
2. Write ADR explaining P02/P09 split
3. Update master document
4. Peer review

##### Estimated Effort

- **Total**: 1.5 hours

##### Dependencies

- **Blocks**: Issue 2.4.1 (family graph ADR)
- **Blocked By**: Issue 2.3.4

---

### Epic 2.4: Social & Builder ADRs (M07, M13-M14)

---

#### Issue 2.4.1: Create ADR - k008.1-family-graph-resolver.md (M07)

**Status**: ✅ COMPLETE (2025-11-16)
**Priority**: 🔴 Critical
**Size**: L (3 hours)
**Assignee**: K0 Architecture Team

##### Context References

**Primary Sources**:

- **Contract**: `k0/contracts/modules/social.resolve_family.v1.yaml` (Issue 1.4.1)
- **P02 Dossier**: Lines 290-304 (R2.5 Social Graph)
- **Data Schema**: Lines 141-147 (social columns), Lines 375-445 (st_relationships)

##### Master Document Tracking (MANDATORY)

**Update Locations**:

1. **Part 7.1**: Add `k008.1 | Family Graph Resolver | k008.1-family-graph-resolver.md | M07 | ✅ Accepted`
2. **Part 2.1**: P02 ADR count = 12
3. **Part 3.1**: M07 status to "📋 ADR Complete"

##### Deliverables

- [ ] Create: `docs/architecture/decisions-K0/modules/k008.1-family-graph-resolver.md`
- [ ] Update Master Doc sections
- [ ] Peer review

##### Acceptance Criteria

**ADR Content**:

- [ ] **Title**: "k008.1 - Family Graph Resolution for Social Context"
- [ ] **Context**: Explains:
  - Relationship types (SPOUSE_OF, PARENT_OF, CHILD_OF, CARETAKER_OF, SIBLING_OF)
  - Social context classification (solo, partner, nuclear family, extended family)
  - Social intimacy scoring (based on relationship strength)
  - Role resolution (who are the participants?)
  - Use cases (salience scoring, memory prioritization, privacy)
- [ ] **Decision**: Graph traversal with cached relationships
- [ ] **Alternatives**:
  1. No social context (rejected: loses family dynamics)
  2. Query social graph every event (rejected: too slow)
  3. Precompute all relationships (rejected: storage explosion)
  4. Chosen: Cache relationships, compute context on write
- [ ] **Consequences**:
  - ✅ <10ms P95 (cached graph lookup)
  - ✅ Rich social context for salience
  - ⚠️ Graph cache invalidation on relationship changes
  - ⚠️ Privacy: never expose relationships outside visibility scope

**Technical Details**:

- [ ] Relationship graph schema (st_relationships table)
- [ ] Intimacy scoring formula (e.g., SPOUSE_OF = 1.0, SIBLING_OF = 0.7)
- [ ] Social context rules (e.g., has_partner_present = any SPOUSE_OF relationship)
- [ ] Cache key structure (actor_id → relationship list)

**Master Document Validation**:

- [ ] ADR in Part 7.1
- [ ] P02 ADR count = 12
- [ ] M07 status updated

##### Implementation Steps

1. Read contract + social graph responsibilities
2. Research graph traversal patterns
3. Write ADR with privacy focus (never leak relationships)
4. Update master document
5. Peer review

##### Estimated Effort

- **Total**: 3.5 hours

##### Dependencies

- **Blocks**: Issue 2.4.2 (row builder ADR)
- **Blocked By**: Issue 2.3.5

---

#### Issue 2.4.2: Create ADR - k009.1-hipp-events-builder.md (M13)

**Status**: ✅ COMPLETE (2025-11-16)
**Priority**: 🔴 Critical
**Size**: L (3 hours)
**Assignee**: K0 Architecture Team

##### Context References

**Primary Sources**:

- **Contract**: `k0/contracts/modules/builders.hipp_events_row.v1.yaml` (Issue 1.4.2)
- **P02 Dossier**: Lines 306-314 (R3 Build Row)
- **Data Schema**: Lines 45-185 (60-70 column schema)

##### Master Document Tracking (MANDATORY)

**Update Locations**:

1. **Part 7.1**: Add `k009.1 | Hipp Events Row Builder | k009.1-hipp-events-builder.md | M13 | ✅ Accepted`
2. **Part 2.1**: P02 ADR count = 13
3. **Part 3.1**: M13 status to "📋 ADR Complete"

##### Deliverables

- [ ] Create: `docs/architecture/decisions-K0/modules/k009.1-hipp-events-builder.md`
- [ ] Update Master Doc sections
- [ ] Peer review

##### Acceptance Criteria

**ADR Content**:

- [ ] **Title**: "k009.1 - Hippocampus Events Row Builder"
- [ ] **Context**: Explains:
  - Purpose: Assemble complete st_hipp_events row from 12 module outputs
  - Column mapping (60-70 columns from M01-M12, M15)
  - No I/O (pure data transformation)
  - Validation (ensure no NULL for NOT NULL columns)
- [ ] **Decision**: Single builder module after all enrichment complete
- [ ] **Alternatives**:
  1. Incremental row building per module (rejected: too complex)
  2. Direct database writes per module (rejected: no transactionality)
  3. Chosen: Collect all outputs, build once, validate
- [ ] **Consequences**:
  - ✅ Clean separation of concerns
  - ✅ Single validation point
  - ✅ Easy to test (deterministic mapping)
  - ⚠️ Large dict structure (60-70 keys)

**Technical Details**:

- [ ] Column mapping table (module output → st_hipp_events column)
- [ ] Validation rules (e.g., text NOT NULL, salience_score 0-1)
- [ ] Default value handling (e.g., dedup_cluster_id = NULL in P02)

**Master Document Validation**:

- [ ] ADR in Part 7.1
- [ ] P02 ADR count = 13
- [ ] M13 status updated

##### Implementation Steps

1. Read contract + row building responsibilities
2. Map all 60-70 columns to source modules
3. Write ADR with validation focus
4. Update master document
5. Peer review

##### Estimated Effort

- **Total**: 3.5 hours

##### Dependencies

- **Blocks**: Issue 2.5.1 (writer ADR)
- **Blocked By**: Issue 2.4.1

---

#### Issue 2.4.3: Create ADR - k009.2-embedding-queue-writer.md (M14)

**Priority**: 🔴 Critical
**Size**: M (2 hours)
**Assignee**: TBD

##### Context References

**Primary Sources**:

- **Contract**: `k0/contracts/modules/builders.embedding_queue.v1.yaml` (Issue 1.4.3)
- **P02 Dossier**: Lines 320-326 (Embedding enqueue)
- **Data Schema**: Lines 250-280 (st_embedding_queue)

##### Master Document Tracking (MANDATORY)

**Update Locations**:

1. **Part 7.1**: Add `k009.2 | Embedding Queue Row Builder | k009.2-embedding-queue-writer.md | M14 | ✅ Accepted`
2. **Part 2.1**: P02 ADR count = 14
3. **Part 3.1**: M14 status to "📋 ADR Complete"

##### Deliverables

- [ ] Create: `docs/architecture/decisions-K0/modules/k009.2-embedding-queue-writer.md`
- [ ] Update Master Doc sections
- [ ] Peer review

##### Acceptance Criteria

**ADR Content**:

- [ ] **Title**: "k009.2 - Embedding Queue Job Builder"
- [ ] **Context**: Explains:
  - P02 enqueues embedding jobs for P08
  - Job payload links (wal_pos, event_id, embedding_id)
  - Initial status = PENDING, attempt_count = 0
  - Retry logic (P08 responsibility, not P02)
- [ ] **Decision**: Builder creates job row, writer commits atomically
- [ ] **Alternatives**:
  1. Inline embedding in P02 (rejected: too slow)
  2. Separate transaction for queue write (rejected: loses atomicity)
  3. Chosen: Include queue write in st_hipp_events UnitOfWork
- [ ] **Consequences**:
  - ✅ Atomic commit (event + embedding job)
  - ✅ Fast write path (no embedding compute)
  - ⚠️ P08 must handle PENDING jobs
  - ⚠️ Queue may grow if P08 slow

**Technical Details**:

- [ ] Job payload schema (text, embedding_id, metadata)
- [ ] Status lifecycle (PENDING → IN_PROGRESS → COMPLETE)
- [ ] Retry policy (max 3 attempts in P08)

**Master Document Validation**:

- [ ] ADR in Part 7.1
- [ ] P02 ADR count = 14
- [ ] M14 status updated

##### Implementation Steps

1. Read contract + queue responsibilities
2. Design job payload structure
3. Write ADR explaining P02/P08 split
4. Update master document
5. Peer review

##### Estimated Effort

- **Total**: 2.5 hours

##### Dependencies

- **Blocks**: Issue 2.5.1 (writer needs both builders)
- **Blocked By**: Issue 2.4.2

---

### Epic 2.5: Core Writer & Emitter ADRs (M16-M17)

---

#### Issue 2.5.1: Create ADR - k010.1-atomic-uow-writer.md (M16)

**Priority**: 🔴 Critical (last backend ADR)
**Size**: L (3 hours)
**Assignee**: K0 Architecture Team
**Status**: ✅ COMPLETE (2025-11-16)

##### Context References

**Primary Sources**:

- **Contract**: `k0/contracts/modules/core.hipp_events_writer.v1.yaml` (Issue 1.5.1)
- **P02 Dossier**: Lines 316-336 (R4 Storage Write), Lines 447-485 (UnitOfWork)
- **Data Schema**: Lines 447-485 (UnitOfWork pattern)

##### Master Document Tracking (MANDATORY)

**Update Locations**:

1. **Part 7.1**: Add `k010.1 | Atomic UnitOfWork Writer | k010.1-atomic-uow-writer.md | M16 | ✅ Accepted`
2. **Part 2.1**: P02 ADR count = 15
3. **Part 3.1**: M16 status to "📋 ADR Complete"

##### Deliverables

- [ ] Create: `docs/architecture/decisions-K0/modules/k010.1-atomic-uow-writer.md`
- [ ] Update Master Doc sections
- [ ] Peer review

##### Acceptance Criteria

**ADR Content**:

- [ ] **Title**: "k010.1 - Atomic UnitOfWork for P02 Write Path"
- [ ] **Context**: Explains:
  - 3-table atomic write (st_hipp_events, st_embedding_queue, st_pipeline_processed)
  - UnitOfWork pattern (all succeed or all fail)
  - Transaction isolation level (READ COMMITTED for PostgreSQL)
  - Idempotency (can retry on failure without duplicates)
  - Write latency target (<50ms P95 for all 3 writes)
- [ ] **Decision**: Single database transaction with explicit commit
- [ ] **Alternatives**:
  1. Separate transactions per table (rejected: no atomicity)
  2. Write st_hipp_events first, queue later (rejected: orphaned events if queue write fails)
  3. Eventual consistency (rejected: breaks P02 contract)
  4. Chosen: Atomic UnitOfWork with explicit commit
- [ ] **Consequences**:
  - ✅ Atomicity guarantee (all or nothing)
  - ✅ Idempotent retry on failure
  - ✅ Consistent state (no orphaned rows)
  - ⚠️ Write latency includes all 3 INSERTs (~30-50ms)
  - ⚠️ Blocking on database connection

**Technical Details**:

- [ ] UnitOfWork lifecycle (begin → add → commit/rollback)
- [ ] Error handling (deadlock retry, constraint violations)
- [ ] Latency budget breakdown (10ms hipp_events + 5ms queue + 5ms processed + 30ms buffer)
- [ ] Connection pooling strategy (reuse from runtime syscalls)

**Master Document Validation**:

- [ ] ADR in Part 7.1
- [ ] P02 ADR count = 15
- [ ] M16 status updated

##### Implementation Steps

1. Read contract + UnitOfWork pattern
2. Research PostgreSQL transaction isolation
3. Write ADR with failure scenarios (deadlock, constraint violation, timeout)
4. Update master document
5. Peer review

##### Estimated Effort

- **Total**: 3.5 hours

##### Dependencies

- **Blocks**: Issue 2.5.2 (emitter ADR)
- **Blocked By**: Issue 2.4.3

---

#### Issue 2.5.2: Create ADR - k011.1-outbox-emitter.md (M17)

**Priority**: 🔴 Critical (final ADR!)
**Size**: M (2.5 hours)
**Assignee**: K0 Architecture Team
**Status**: ✅ COMPLETE (2025-11-16)

##### Context References

**Primary Sources**:

- **Contract**: `k0/contracts/modules/core.event_emitter.v1.yaml` (Issue 1.5.2)
- **P02 Dossier**: Lines 320-326 (Event Emission), Lines 630-650 (Exit topics)

##### Master Document Tracking (MANDATORY)

**Update Locations**:

1. **Part 7.1**: Add `k011.1 | Outbox Event Emitter | k011.1-outbox-emitter.md | M17 | ✅ Accepted`
2. **Part 2.1**: P02 ADR count = 16
3. **Part 3.1**: M17 status to "📋 ADR Complete"

##### Deliverables

- [ ] Create: `docs/architecture/decisions-K0/modules/k011.1-outbox-emitter.md`
- [ ] Update Master Doc sections
- [ ] Peer review

##### Acceptance Criteria

**ADR Content**:

- [ ] **Title**: "k011.1 - Outbox Pattern for P02 Event Emission"
- [ ] **Context**: Explains:
  - 6 exit topics emitted (workspace.wm.updated, core.affect.analyzed, etc.)
  - Outbox pattern (write to st_outbox, relay worker publishes)
  - Why not direct publish (atomicity with database writes)
  - Relay worker polling strategy (separate from P02)
- [ ] **Decision**: Outbox pattern via syscalls.outbox_emit
- [ ] **Alternatives**:
  1. Direct NATS publish (rejected: no transactional guarantee)
  2. Two-phase commit (rejected: too complex, slow)
  3. Saga pattern (rejected: overkill for write path)
  4. Chosen: Outbox table + relay worker
- [ ] **Consequences**:
  - ✅ Atomic event emission (part of UnitOfWork)
  - ✅ Guaranteed delivery (relay worker retries)
  - ⚠️ Eventual consistency (events published after commit)
  - ⚠️ Relay worker becomes critical path

**Technical Details**:

- [ ] Outbox schema (topic, payload, status, retry_count)
- [ ] Emission latency budget (<10ms for 6 INSERT calls)
- [ ] Relay worker responsibilities (poll, publish, mark sent)
- [ ] Topic mapping (which modules trigger which topics)

**Master Document Validation**:

- [ ] ADR in Part 7.1 with ✅ Accepted status
- [ ] P02 ADR count = 16 (all ADRs complete!)
- [ ] M17 status updated in Part 3.1

##### Implementation Steps

1. Read contract + outbox pattern docs
2. Design topic-to-module mapping
3. Write ADR explaining outbox vs. direct publish
4. Update master document (final updates!)
5. Peer review

##### Estimated Effort

- **Total**: 3 hours

##### Dependencies

- **Blocks**: Milestone 3 (Pipeline YAML - can start after ADRs)
- **Blocked By**: Issue 2.5.1 (writer ADR must exist first)

---

### Milestone 2 Summary

**Total ADRs**: 16 ADR documents (M03 skipped as P03 scope)
**Total Effort**: ~40-45 hours (4-5 days for 1 developer)
**Critical Path**: Issue 2.1.1 → 2.1.2 → 2.2.1 → 2.2.2 → 2.2.3 → 2.3.1 → 2.4.1 → 2.4.2 → 2.5.1 → 2.5.2

**Completion Criteria**:

- [ ] All 16 ADR files created in `docs/architecture/decisions-K0/modules/`
- [ ] Part 7.1 (ADR Registry) has 16 entries with ✅ Accepted status
- [ ] Part 2.1 (Pipeline Registry) shows P02 ADR count = 16
- [ ] Part 3.1 (Module Registry) shows all modules at "📋 ADR Complete" status
- [ ] All ADRs peer-reviewed and approved
- [ ] No broken links between ADRs and contracts

**Quality Gates**:

- [ ] Each ADR follows template structure (7 sections minimum)
- [ ] Alternatives section has ≥3 options considered
- [ ] Consequences include both positive and negative impacts
- [ ] Technical details sufficient for implementation
- [ ] Cross-references valid (contracts, dossier, data schema)

**Next**: Proceed to Milestone 3 (Pipeline YAML) after all ADRs complete

---

## Milestone 3: Pipeline YAML Specification

**Goal**: Create the declarative P02 pipeline YAML specification that orchestrates all 17 modules in the correct DAG execution order.

**Status**: 📝 Not Started
**Duration**: 2-3 days
**Effort**: ~12-16 hours
**Prerequisites**:

- ✅ Milestone 1 complete (all contracts defined)
- ✅ Milestone 2 complete (all ADRs approved)
- ✅ Runtime YAML parser ready (k0/runtime/)
- ✅ DAG execution engine exists

### Epic 3.1: Pipeline Definition & Validation

---

#### Issue 3.1.1: Create p02_write.v1.yaml ✅ COMPLETE

**Priority**: 🔴 Critical (defines entire pipeline)
**Size**: L (8-10 hours)
**Assignee**: Completed 2025-11-16
**Status**: ✅ COMPLETE - Pipeline YAML created and validated
**Performance**: 171ms P95 accepted for v1; M04 optimization (target ≤50ms) tracked separately
**Deliverable**: `k0/contracts/pipelines/p02_write.v1.yaml` (220 lines, 18 stages, 16 modules)

##### Context References

**Primary Sources**:

- **P02 Dossier**:
  - Lines 580-680 (Phase 2 YAML Architecture - complete example)
  - Lines 850-920 (Pipeline YAML spec with all stages)
  - Lines 383-434 (Module mapping table - 17 modules)
- **All 17 Contracts**: `k0/contracts/modules/*.yaml` (from Milestone 1)
- **Runtime Guide**: `k0/runtime/README.md`
  - Lines 50-120 (Pipeline YAML schema)
  - Lines 230-280 (Stage execution model)
- **Existing Pipeline Examples**: Check `k0/pipelines/` for other pipeline YAMLs

**Supporting Context**:

- **DAG Stages**: 8 stages from dossier (stage_10 → stage_90)
- **Module Dependencies**: Explicit in dossier module mapping table
- **Entry Topic**: `cognitive.memory.write.committed.v1`
- **Exit Topics**: 6 topics listed in dossier lines 630-650

##### Master Document Tracking (MANDATORY)

**Update Locations**:

1. **Part 2.1: Pipeline Registry**
   - File: `k0/pipelines/k0_architecture_master.md` (search for "Part 2.1")
   - Action: Update P02 row:

     ```markdown
     | P02 | Episodic Memory Formation | 🎯 Implementation | p02_episodic_write.pipeline.yaml | ✅ Spec Created | 17 modules, 8 stages | Lines 50-150 |
     ```

2. **Part 4.1: Topic Registry**
   - Update entry topic `cognitive.memory.write.committed.v1`:
     - Consumer: P02 (add if not already listed)
   - Update 6 exit topics with P02 as producer:
     - `workspace.wm.updated.v1` → Producer: P02
     - `core.affect.analyzed.v1` → Producer: P02
     - `space.resolution.complete.v1` → Producer: P02
     - `embedding.enqueue.v1` → Producer: P02
     - `p02.hippocampus.pattern_separated.v1` → Producer: P02
     - `p02.write.complete.v1` → Producer: P02

3. **Part 6.4: Pipeline-Module Matrix**
   - Add P02 column to matrix
   - Mark all 17 modules (M01-M17 excluding M03) as used by P02

##### Deliverables

- [ ] Create file: `k0/pipelines/p02_episodic_write.pipeline.yaml`
- [ ] Update Master Doc Part 2.1 (Pipeline Registry)
- [ ] Update Master Doc Part 4.1 (Topic Registry - 7 topics)
- [ ] Update Master Doc Part 6.4 (Pipeline-Module Matrix)
- [ ] Validate YAML syntax
- [ ] Validate against runtime schema (Pydantic)

##### Acceptance Criteria

**Pipeline Header**:

- [ ] `pipeline_id: p02_episodic_write` (matches file naming convention)
- [ ] `version: v1` (initial version)
- [ ] `description`: Clear summary of P02 purpose
- [ ] `owner: k0.pipelines` (ownership metadata)
- [ ] `latency_budget_ms: 150` (total P95 budget from dossier)

**Entry & Exit Points**:

- [ ] `entry_topic: cognitive.memory.write.committed.v1` (WAL committed events)
- [ ] `exit_topics` array with 6 topics:

  ```yaml
  exit_topics:
    - workspace.wm.updated.v1
    - core.affect.analyzed.v1
    - space.resolution.complete.v1
    - embedding.enqueue.v1
    - p02.hippocampus.pattern_separated.v1
    - p02.write.complete.v1
  ```

**Stage Definitions** (8 stages total):

- [ ] **Stage 10: DG Pattern Separation**
  - `stage_id: stage_10_dg_pattern_separate`
  - `modules: [hippocampus.pattern_separate:v1]`
  - `depends_on: []` (first stage)
  - `max_parallelism: 1` (single module)

- [ ] **Stage 20: CA1 Semantic Projection**
  - `stage_id: stage_20_ca1_semantic_project`
  - `modules: [hippocampus.semantic_project:v1]`
  - `depends_on: [stage_10_dg_pattern_separate]`
  - `max_parallelism: 1`

- [ ] **Stage 30: Parallel Cognition** (3 modules)
  - `stage_id: stage_30_cognition`
  - `modules`:
    - `affect.analyze:v1`
    - `space.resolve_visibility:v1`
    - `salience.score:v1` (depends on affect output)
  - `depends_on: [stage_20_ca1_semantic_project]`
  - `max_parallelism: 3` (affect and space parallel, salience after affect)

- [ ] **Stage 40: Parallel Context Enrichment** (6 modules)
  - `stage_id: stage_40_context_enrichment`
  - `modules`:
    - `context.temporal_profile:v1`
    - `context.device_profile:v1`
    - `context.ingress_classify:v1`
    - `context.retention_lookup:v1`
    - `context.geo_metadata:v1`
    - `context.spatial_minimal:v1`
  - `depends_on: [stage_30_cognition]`
  - `max_parallelism: 6` (all parallel, cache-optimized)

- [ ] **Stage 50: Social Graph Resolution**
  - `stage_id: stage_50_social_graph`
  - `modules: [social.resolve_family:v1]`
  - `depends_on: [stage_40_context_enrichment]`
  - `max_parallelism: 1`

- [ ] **Stage 60: Row Builders** (2 modules)
  - `stage_id: stage_60_build_rows`
  - `modules`:
    - `builders.hipp_events_row:v1`
    - `builders.embedding_queue:v1`
  - `depends_on: [stage_50_social_graph]`
  - `max_parallelism: 2` (both builders can run in parallel)

- [ ] **Stage 70: Atomic Write**
  - `stage_id: stage_70_atomic_write`
  - `modules: [core.hipp_events_writer:v1]`
  - `depends_on: [stage_60_build_rows]`
  - `max_parallelism: 1` (single transaction)

- [ ] **Stage 90: Event Emission**
  - `stage_id: stage_90_emit_events`
  - `modules: [core.event_emitter:v1]`
  - `depends_on: [stage_70_atomic_write]`
  - `max_parallelism: 1` (emit after commit)

**Error Handling**:

- [ ] `failure_policy: stop` (halt pipeline on any module failure)
- [ ] `retry_policy`:
  - `max_retries: 3`
  - `backoff: exponential`
  - `base_delay_ms: 100`

**Observability**:

- [ ] `tracing_enabled: true`
- [ ] `emit_stage_metrics: true`
- [ ] `emit_module_metrics: true`

**Master Document Validation**:

- [ ] P02 in Part 2.1 shows "🎯 Implementation" status
- [ ] All 7 topics updated in Part 4.1
- [ ] Part 6.4 matrix shows P02 column with 16 modules marked (excluding M03)
- [ ] Cross-references valid (all module IDs exist in contracts)

##### Implementation Steps

1. **Read Full Context**

   ```powershell
   # Read dossier YAML section
   Get-Content docs\pipelines\P02_write_dossier.md | Select-Object -Skip 579 -First 100

   # Check all contracts created in M1
   Get-ChildItem k0\contracts\modules\*.yaml | Select-Object Name

   # Read runtime YAML schema
   Get-Content k0\runtime\README.md | Select-Object -Skip 49 -First 70
   ```

2. **Create Pipeline YAML Structure**
   - Start with header (pipeline_id, version, description)
   - Add entry_topic and exit_topics
   - Define latency_budget_ms: 150

3. **Define 8 Stages in Order**
   - Stage 10: DG pattern separation (depends_on: [])
   - Stage 20: CA1 semantic projection (depends_on: [stage_10])
   - Stage 30: Cognition (3 modules, depends_on: [stage_20])
   - Stage 40: Context enrichment (6 modules, depends_on: [stage_30])
   - Stage 50: Social graph (depends_on: [stage_40])
   - Stage 60: Builders (2 modules, depends_on: [stage_50])
   - Stage 70: Atomic write (depends_on: [stage_60])
   - Stage 90: Event emission (depends_on: [stage_70])

4. **Add Error Handling & Observability**
   - failure_policy, retry_policy, tracing settings

5. **Update Master Document**
   - Open `k0/pipelines/k0_architecture_master.md`
   - Update Part 2.1: P02 status to "🎯 Implementation"
   - Update Part 4.1: Add P02 to 7 topic entries
   - Update Part 6.4: Add P02 column to matrix, mark 16 modules
   - Save file

6. **Validate YAML**

   ```powershell
   # Syntax validation
   python -c "import yaml; yaml.safe_load(open('k0/pipelines/p02_episodic_write.pipeline.yaml'))"

   # Schema validation (future: add validation script)
   # python k0/runtime/validate_pipeline.py k0/pipelines/p02_episodic_write.pipeline.yaml
   ```

##### Estimated Effort

- **Context Reading**: 1 hour (dossier + contracts review)
- **YAML Writing**: 4 hours (8 stages with dependencies)
- **Module Mapping**: 2 hours (ensure all 17 modules correctly placed)
- **Master Doc Updates**: 1.5 hours (3 sections, topic registry updates)
- **Validation**: 1 hour (syntax + schema + cross-reference checks)
- **Total**: 9.5 hours

##### Dependencies

- **Blocks**: Issue 3.1.2 (pipeline validation tests)
- **Blocked By**: Milestone 2 complete (all ADRs must exist)

##### Notes

- **Critical artifact** - this YAML is the execution contract for P02
- Stage dependencies form strict DAG (no cycles)
- max_parallelism hints for runtime optimizer
- Module version pinning (all :v1 for initial release)
- Keep aligned with dossier lines 850-920 (reference YAML spec)

---

#### Issue 3.1.2: Create Pipeline Validation Tests

**Priority**: 🔴 Critical
**Size**: M (4-5 hours)
**Assignee**: TBD

##### Context References

**Primary Sources**:

- **Pipeline YAML**: `k0/pipelines/p02_episodic_write.pipeline.yaml` (from Issue 3.1.1)
- **Runtime Guide**: `k0/runtime/README.md` (validation logic)
- **Test Guidelines**: `docs/development/testing-guide.md`
- **Existing Pipeline Tests**: Check `tests/k0/pipelines/` for examples

##### Master Document Tracking (MANDATORY)

**Update Locations**:

1. **Part 8.1: Test Coverage Registry**
   - File: `k0/pipelines/k0_architecture_master.md` (search for "Part 8.1")
   - Action: Add row:

     ```markdown
     | P02 Pipeline Validation | Integration | tests/k0/pipelines/test_p02_pipeline_yaml.py | ✅ Created | YAML schema, DAG validation, module references |
     ```

2. **Part 2.1: Pipeline Registry**
   - Update P02 row: Add test coverage indicator
   - `Tests: ✅ YAML Validation`

##### Deliverables

- [ ] Create file: `tests/k0/pipelines/test_p02_pipeline_yaml.py`
- [ ] Update Master Doc Part 8.1 (Test Coverage Registry)
- [ ] Update Master Doc Part 2.1 (P02 test status)
- [ ] All tests pass

##### Acceptance Criteria

**Test Coverage**:

- [ ] **Test 1: YAML Syntax Validation**
  - Loads pipeline YAML without errors
  - Parses to Python dict
  - No YAML syntax errors

- [ ] **Test 2: Schema Validation**
  - Validates against `PipelineSpec` Pydantic schema
  - All required fields present (pipeline_id, version, entry_topic, stages)
  - Field types correct (latency_budget_ms is int, etc.)

- [ ] **Test 3: DAG Acyclicity**
  - Stage dependencies form valid DAG (no cycles)
  - Topological sort produces valid execution order
  - No stage depends on itself

- [ ] **Test 4: Module References**
  - All 16 module IDs reference existing contracts
  - Module versions match contract versions (all :v1)
  - No dangling module references

- [ ] **Test 5: Topic Validation**
  - Entry topic exists in topic registry
  - All 6 exit topics exist in topic registry
  - Topics follow naming convention (domain.action.status.version)

- [ ] **Test 6: Latency Budget**
  - Total latency budget (150ms) >= sum of module budgets
  - Warn if budget <90% consumed (too loose)
  - Fail if budget exceeded (impossible to meet)

- [ ] **Test 7: Stage Dependencies**
  - Stage 10 has no dependencies (entry point)
  - All other stages have valid depends_on references
  - No missing stage IDs in depends_on arrays

**Master Document Validation**:

- [ ] Test file added to Part 8.1
- [ ] P02 shows test coverage in Part 2.1

##### Implementation Steps

1. **Create Test File Structure**

   ```python
   # tests/k0/pipelines/test_p02_pipeline_yaml.py
   import pytest
   import yaml
   from pathlib import Path
   from k0.runtime.schemas import PipelineSpec

   PIPELINE_PATH = Path("k0/pipelines/p02_episodic_write.pipeline.yaml")

   @pytest.fixture
   def pipeline_yaml():
       with open(PIPELINE_PATH) as f:
           return yaml.safe_load(f)
   ```

2. **Write Validation Tests**
   - test_yaml_syntax_valid
   - test_schema_validation
   - test_dag_no_cycles
   - test_all_modules_exist
   - test_topics_valid
   - test_latency_budget_reasonable
   - test_stage_dependencies_valid

3. **Update Master Document**
   - Add test entry to Part 8.1
   - Update P02 test status in Part 2.1

4. **Run Tests**

   ```powershell
   pytest tests/k0/pipelines/test_p02_pipeline_yaml.py -v
   ```

##### Estimated Effort

- **Test Writing**: 3 hours (7 test functions)
- **Master Doc Updates**: 30 minutes
- **Debugging**: 1 hour (fix any YAML issues found)
- **Total**: 4.5 hours

##### Dependencies

- **Blocks**: Milestone 4 (Module Implementation - can start after YAML validated)
- **Blocked By**: Issue 3.1.1 (pipeline YAML must exist)

---

### Milestone 3 Summary

**Total Issues**: 2 (pipeline YAML + validation tests)
**Total Effort**: ~14 hours (2 days for 1 developer)
**Critical Path**: Issue 3.1.1 → 3.1.2

**Completion Criteria**:

- [ ] `k0/pipelines/p02_episodic_write.pipeline.yaml` created
- [ ] Pipeline YAML validates against Pydantic schema
- [ ] DAG execution order deterministic and acyclic
- [ ] All 16 module references valid (contracts exist)
- [ ] All 7 topics registered in Part 4.1
- [ ] Master Doc updated (Parts 2.1, 4.1, 6.4, 8.1)
- [ ] Pipeline validation tests pass

**Quality Gates**:

- [ ] YAML parses without syntax errors
- [ ] Schema validation passes (Pydantic)
- [ ] DAG topological sort succeeds
- [ ] No module version mismatches
- [ ] Latency budget reasonable (sum of modules ≤ 150ms)

**Next**: Proceed to Milestone 4 (Module Implementation) after pipeline YAML validated

---

## Milestone 4: Module Implementation

**Goal**: Implement all 17 P02 modules according to their contracts and ADRs, with full test coverage.

**Status**: 📝 Not Started
**Duration**: 12-15 days (parallelizable across team)
**Effort**: ~160-200 hours (17 modules × 8-12h each)
**Prerequisites**:

- ✅ Milestone 1 complete (all contracts)
- ✅ Milestone 2 complete (all ADRs)
- ✅ Milestone 3 complete (pipeline YAML validated)
- ✅ Runtime infrastructure ready (k0/runtime/)

### Epic 4.1: Hippocampus Module Implementation (M01-M02)

---

#### Issue 4.1.1: Implement hippocampus.pattern_separate (M01)

**Priority**: 🔴 Critical (first implementation sets pattern)
**Size**: L (10-12 hours)
**Assignee**: TBD

##### Context References

**Primary Sources**:

- **Contract**: `k0/contracts/modules/hippocampus.pattern_separate.v1.yaml`
- **ADR**: `docs/architecture/decisions-K0/modules/k003.1-dg-pattern-separation.md`
- **P02 Dossier**: Lines 195-221 (R1.1 Pattern Separation detailed spec)
- **Data Schema**: Lines 160-167 (hippocampus columns: simhash_hex, minhash32)
- **Module Guidelines**: `k0/modules/module_development_guidelines.md` (lines 100-200 for implementation patterns)

**Supporting Context**:

- **SimHash Algorithm**: Research Charikar's SimHash (2002 paper)
- **MinHash Algorithm**: Research Broder's MinHash for LSH
- **Runtime Module Interface**: `k0/runtime/module_base.py` (base class to inherit)

##### Master Document Tracking (MANDATORY)

**Update Locations**:

1. **Part 3.1: Module Master Registry**
   - Update M01 row:

     ```markdown
     | M01 | hippocampus.pattern_separate | ✅ Implemented | ... | Impl: ✅ | Tests: ✅ | k0/modules/hippocampus/pattern_separate.py |
     ```

2. **Part 8.1: Test Coverage Registry**
   - Add row:

     ```markdown
     | M01 Pattern Separation | Unit + Integration | tests/k0/modules/hippocampus/test_pattern_separate.py | ✅ Created | SimHash/MinHash correctness, latency <15ms |
     ```

##### Deliverables

- [ ] Create: `k0/modules/hippocampus/pattern_separate.py`
- [ ] Create: `tests/k0/modules/hippocampus/test_pattern_separate.py`
- [ ] Update Master Doc Part 3.1 (Module status)
- [ ] Update Master Doc Part 8.1 (Test coverage)
- [ ] All tests pass (unit + integration)
- [ ] Performance validated (≤15ms P95)

##### Acceptance Criteria

**Module Structure**:

- [ ] Class `DGPatternSeparate` inherits from `ModuleBase`
- [ ] Implements `async def process(envelope: Envelope) -> Dict[str, Any]`
- [ ] Configuration loaded from contract YAML
- [ ] Logging with structured context (tenant_id, event_id, trace_id)

**Core Functionality**:

- [ ] **SimHash Computation**:
  - Extract text from envelope (body + participants + place + activity_type)
  - Generate word shingles (3-grams recommended)
  - Hash each shingle using stable hash function
  - Build 64-bit fingerprint via bit vector accumulation
  - Return as hex string (16 characters)

- [ ] **MinHash Computation**:
  - Use 32 hash permutations (from ADR)
  - Generate MinHash signature (32 integers)
  - Serialize as JSON array: `[h1, h2, ..., h32]`
  - Deterministic (same text → same MinHash)

- [ ] **Output Schema**:

  ```python
  {
      "simhash_hex": "a1b2c3d4e5f67890",  # 64-bit hex
      "minhash32": [123, 456, ...],        # 32-element array
      "fingerprint_computed_at_utc": "2025-11-16T10:30:00Z"
  }
  ```

- [ ] **Performance**:
  - Latency ≤15ms P95 (per contract)
  - No database queries (pure computation)
  - Idempotent (same input → same output)

**Error Handling**:

- [ ] Handle empty text (return default fingerprint or raise INVALID_INPUT_TEXT)
- [ ] Handle malformed envelope (log error, emit failure event)
- [ ] Retry logic: 3 attempts with exponential backoff
- [ ] Emit metrics (latency, success/failure counts)

**Test Coverage**:

- [ ] **Unit Tests** (8-10 tests):
  - test_simhash_deterministic (same text → same hash)
  - test_simhash_similarity (similar text → similar hashes)
  - test_minhash_deterministic
  - test_minhash_collision_rate (different texts → different signatures)
  - test_empty_text_handling
  - test_unicode_text_handling
  - test_performance_under_15ms (100 iterations)
  - test_output_schema_valid

- [ ] **Integration Tests** (3-5 tests):
  - test_module_loads_from_contract
  - test_process_full_envelope (end-to-end)
  - test_idempotency (process same envelope twice)
  - test_error_metrics_emitted
  - test_trace_context_propagated

**Master Document Validation**:

- [ ] M01 in Part 3.1 shows "✅ Implemented" status
- [ ] Test entry in Part 8.1 with ✅ status
- [ ] File paths valid (module and test files exist)

##### Implementation Steps

1. **Setup Module Structure**

   ```powershell
   # Create directory
   New-Item -ItemType Directory -Force -Path "k0\modules\hippocampus"

   # Create __init__.py
   New-Item -ItemType File -Path "k0\modules\hippocampus\__init__.py"
   ```

2. **Implement SimHash**

   ```python
   # k0/modules/hippocampus/pattern_separate.py
   import hashlib
   from typing import Dict, Any, List
   from k0.runtime.module_base import ModuleBase
   from k0.runtime.schemas import Envelope

   class DGPatternSeparate(ModuleBase):
       def __init__(self, config: Dict[str, Any]):
           super().__init__(config)
           self.hash_seed = config.get("hash_seed", 42)

       async def process(self, envelope: Envelope) -> Dict[str, Any]:
           # Extract text
           text = self._extract_text(envelope)

           # Compute SimHash
           simhash = self._compute_simhash(text)

           # Compute MinHash
           minhash = self._compute_minhash(text)

           return {
               "simhash_hex": simhash,
               "minhash32": minhash,
               "fingerprint_computed_at_utc": self._now_utc()
           }

       def _compute_simhash(self, text: str) -> str:
           # Implementation: shingles → hash → bit vector
           shingles = self._generate_shingles(text, k=3)
           bit_vector = [0] * 64

           for shingle in shingles:
               h = int(hashlib.sha256(shingle.encode()).hexdigest(), 16)
               for i in range(64):
                   if h & (1 << i):
                       bit_vector[i] += 1
                   else:
                       bit_vector[i] -= 1

           # Threshold and convert to hex
           fingerprint = 0
           for i in range(64):
               if bit_vector[i] > 0:
                   fingerprint |= (1 << i)

           return f"{fingerprint:016x}"

       def _compute_minhash(self, text: str, num_perms: int = 32) -> List[int]:
           # Implementation: 32 hash permutations
           shingles = set(self._generate_shingles(text, k=3))
           signature = []

           for i in range(num_perms):
               min_hash = float('inf')
               for shingle in shingles:
                   h = hash((i, shingle, self.hash_seed))
                   min_hash = min(min_hash, h)
               signature.append(min_hash if min_hash != float('inf') else 0)

           return signature
   ```

3. **Write Tests**

   ```python
   # tests/k0/modules/hippocampus/test_pattern_separate.py
   import pytest
   from k0.modules.hippocampus.pattern_separate import DGPatternSeparate

   @pytest.fixture
   def module():
       return DGPatternSeparate(config={"hash_seed": 42})

   def test_simhash_deterministic(module):
       envelope1 = create_test_envelope("Hello world")
       envelope2 = create_test_envelope("Hello world")

       result1 = await module.process(envelope1)
       result2 = await module.process(envelope2)

       assert result1["simhash_hex"] == result2["simhash_hex"]

   def test_performance_under_15ms(module):
       envelope = create_test_envelope("Sample text" * 100)

       import time
       times = []
       for _ in range(100):
           start = time.perf_counter()
           await module.process(envelope)
           times.append((time.perf_counter() - start) * 1000)

       p95 = sorted(times)[94]
       assert p95 < 15, f"P95 latency {p95:.2f}ms exceeds 15ms budget"
   ```

4. **Update Master Document**
   - Update Part 3.1: M01 status to "✅ Implemented", add file path
   - Add Part 8.1: Test coverage entry
   - Save file

5. **Run Tests**

   ```powershell
   pytest tests/k0/modules/hippocampus/test_pattern_separate.py -v
   ```

##### Estimated Effort

- **SimHash Implementation**: 3 hours (algorithm + testing)
- **MinHash Implementation**: 3 hours (32 permutations + testing)
- **Module Scaffolding**: 2 hours (base class integration, config)
- **Unit Tests**: 2 hours (8-10 tests)
- **Integration Tests**: 1.5 hours (3-5 tests)
- **Performance Validation**: 1 hour (benchmark + optimization)
- **Master Doc Updates**: 30 minutes
- **Total**: 12 hours

##### Dependencies

- **Blocks**: Issue 4.1.2 (CA1 semantic projection)
- **Blocked By**: Milestone 3 complete (pipeline YAML validated)

##### Notes

- **First implementation** - establishes code patterns for remaining 16 modules
- Use `hashlib.sha256` for stable hashing (reproducible across runs)
- Consider caching shingles if text preprocessing expensive
- Emit detailed metrics (simhash_latency_ms, minhash_latency_ms separate)
- Keep algorithm simple (defer optimizations to P03 if needed)

---

#### Issue 4.1.2: Implement hippocampus.semantic_project (M02)

**Priority**: 🔴 Critical
**Size**: L (12-14 hours)
**Assignee**: TBD

##### Context References

**Primary Sources**:

- **Contract**: `k0/contracts/modules/hippocampus.semantic_project.v1.yaml`
- **ADR**: `docs/architecture/decisions-K0/modules/k003.2-ca1-semantic-bridge.md`
- **P02 Dossier**: Lines 223-235 (R1.3 Semantic Projection)
- **Data Schema**: Lines 168-171 (embeddings, KG columns), Lines 250-280 (st_embedding_queue)

##### Master Document Tracking (MANDATORY)

**Update Locations**:

1. **Part 3.1**: Update M02 to "✅ Implemented"
2. **Part 8.1**: Add test coverage entry for M02

##### Deliverables

- [ ] Create: `k0/modules/hippocampus/semantic_project.py`
- [ ] Create: `tests/k0/modules/hippocampus/test_semantic_project.py`
- [ ] Update Master Doc Parts 3.1, 8.1
- [ ] All tests pass
- [ ] Performance ≤20ms P95

##### Acceptance Criteria

**Module Structure**:

- [ ] Class `CA1SemanticProject` inherits from `ModuleBase`
- [ ] Implements `async def process(envelope: Envelope) -> Dict[str, Any]`

**Core Functionality**:

- [ ] **Entity Extraction**:
  - Extract people (from participants field)
  - Extract places (from location field)
  - Extract organizations (from text via NER or rules)
  - Return structured list: `[{type: "PERSON", name: "Alice", confidence: 0.9}, ...]`

- [ ] **KG Triple Generation**:
  - Generate triples: `(subject, predicate, object)`
  - Examples:
    - `("Alice", "PARTICIPATED_IN", "event_id")`
    - `("event_id", "OCCURRED_AT", "Home")`
    - `("Alice", "INTERACTED_WITH", "Bob")`
  - Return as JSON array

- [ ] **Embedding ID Allocation**:
  - Generate UUID for embedding job
  - Link to envelope's event_id and wal_pos
  - Prepare payload for st_embedding_queue

- [ ] **Output Schema**:

  ```python
  {
      "embedding_id": "uuid-string",
      "entities_extracted": [{...}],
      "kg_triples": [["Alice", "PARTICIPATED_IN", "event_123"], ...],
      "embedding_job_enqueued": True,
      "semantic_projection_complete_at_utc": "2025-11-16T10:30:00Z"
  }
  ```

- [ ] **Performance**: ≤20ms P95

**Error Handling**:

- [ ] Handle missing text (extract entities from available fields)
- [ ] Handle NER failures (fallback to rule-based extraction)
- [ ] Retry logic for transient failures

**Test Coverage**:

- [ ] **Unit Tests** (10-12 tests):
  - test_entity_extraction_people
  - test_entity_extraction_places
  - test_kg_triple_generation
  - test_embedding_id_unique
  - test_performance_under_20ms
  - test_empty_text_handling
  - test_output_schema_valid

- [ ] **Integration Tests** (3-5 tests):
  - test_full_envelope_processing
  - test_embedding_job_payload_correct
  - test_idempotency

**Master Document Validation**:

- [ ] M02 in Part 3.1 shows "✅ Implemented"
- [ ] Test entry in Part 8.1

##### Implementation Steps

1. Read contract + ADR
2. Implement entity extraction (spaCy NER or rule-based)
3. Implement KG triple generation
4. Generate embedding_id (UUID4)
5. Write unit tests (10-12 tests)
6. Write integration tests
7. Update master document
8. Run tests and validate performance

##### Estimated Effort

- **Entity Extraction**: 4 hours (NER integration or rules)
- **KG Triple Generation**: 3 hours (relationship extraction)
- **Module Scaffolding**: 2 hours
- **Unit Tests**: 2 hours
- **Integration Tests**: 1.5 hours
- **Performance Validation**: 1 hour
- **Master Doc Updates**: 30 minutes
- **Total**: 14 hours

##### Dependencies

- **Blocks**: Issue 4.2.1 (affect.analyze)
- **Blocked By**: Issue 4.1.1 (pattern established)

##### Notes

- Consider lightweight NER (spaCy small model or rule-based for speed)
- KG triples deferred to P03 for full graph analysis
- Embedding job payload includes text for P08 processing
- Keep entity extraction fast (<10ms) to meet 20ms budget

---

### Epic 4.2: Cognition Module Implementation (M04-M06)

(Detailed issues for M04-M06: affect.analyze, space.resolve_visibility, salience.score - similar structure to 4.1.1/4.1.2, ~10-12 hours each)

### Epic 4.3: Context Enrichment Implementation (M08-M12, M15)

(Detailed issues for 6 context modules - ~6-10 hours each)

### Epic 4.4: Social & Builder Implementation (M07, M13-M14)

(Detailed issues for social.resolve_family, builders.hipp_events_row, builders.embedding_queue - ~10-14 hours each)

### Epic 4.5: Core Writer & Emitter Implementation (M16-M17)

(Detailed issues for core.hipp_events_writer, core.event_emitter - ~12-14 hours each)

---

### Milestone 4 Summary (Abbreviated)

**Total Issues**: 17 implementation issues (one per module)
**Total Effort**: ~170-200 hours (can parallelize across 3-4 developers)
**Duration**: 12-15 days (with 4-person team)
**Critical Path**: M01 → M02 → M04 → M05 → M06 → M08-M15 (parallel) → M07 → M13 → M14 → M16 → M17

**Completion Criteria**:

- [ ] All 17 modules implemented in `k0/modules/`
- [ ] All 17 test suites passing (unit + integration)
- [ ] Performance budgets met (per-module latency targets)
- [ ] Part 3.1: All modules show "✅ Implemented" status
- [ ] Part 8.1: All test coverage entries added
- [ ] Code review completed for all modules
- [ ] No lint errors or type violations

**Quality Gates**:

- [ ] Each module passes contract validation
- [ ] Test coverage ≥80% per module
- [ ] Performance validated (automated benchmarks)
- [ ] Error handling tested (failure injection tests)
- [ ] Observability validated (traces + metrics emitted)

**Parallelization Strategy**:

- **Week 1**: M01, M02, M04, M05 (4 devs)
- **Week 2**: M06, M08-M12, M15 (parallel - 7 modules)
- **Week 3**: M07, M13, M14, M16, M17 (sequential dependencies)

**Next**: Proceed to Milestone 5 (Syscalls Integration) after all modules implemented

---

## Milestone 5: Syscalls Integration & Runtime Glue

**Goal**: Implement the 4 missing syscall methods that P02 modules depend on, and integrate runtime infrastructure with pipeline executor.

**Status**: 📝 Not Started
**Duration**: 4-5 days
**Effort**: ~30-35 hours
**Prerequisites**:

- ✅ Milestone 4 complete (all modules implemented)
- ✅ Runtime infrastructure exists (k0/runtime/)
- ⚠️ Syscalls partially complete (4 methods missing)

**Context**: The P02 dossier (lines 880-920) identifies 4 syscall methods that modules depend on but are not yet implemented in the runtime layer.

### Epic 5.1: Storage Syscalls Implementation

---

#### Issue 5.1.1: Implement syscalls.storage_read_hipp_events()

**Priority**: 🔴 Critical (M01 may need for novelty checks in future)
**Size**: M (6-8 hours)
**Assignee**: TBD

##### Context References

**Primary Sources**:

- **P02 Dossier**: Lines 880-895 (Syscall Inventory - storage_read_hipp_events)
- **Data Schema**: Lines 45-185 (st_hipp_events table schema)
- **Runtime Syscalls**: `k0/runtime/syscalls.py` (existing syscall patterns)
- **Storage Layer**: `k0/storage/` (database connection patterns)

**Supporting Context**:

- **Use Case**: M01 (DG pattern separation) may query for similar fingerprints (though P02 defers to P03)
- **Query Pattern**: Fetch events by simhash/minhash for novelty detection
- **Performance**: Must support efficient fingerprint lookups (<10ms P95)

##### Master Document Tracking (MANDATORY)

**Update Locations**:

1. **Part 5.2: Syscall Registry**
   - File: `k0/pipelines/k0_architecture_master.md` (search for "Part 5.2")
   - Action: Add row:

     ```markdown
     | storage_read_hipp_events | Read | Fetch hippocampus events by fingerprint | k0/runtime/syscalls.py:storage_read_hipp_events | ✅ Implemented | M01, P03 |
     ```

2. **Part 3.1: Module Master Registry**
   - Update M01 dependencies: Add syscall reference
   - Note: "Uses storage_read_hipp_events (future P03 usage)"

##### Deliverables

- [ ] Implement: `k0/runtime/syscalls.py::storage_read_hipp_events()`
- [ ] Create: `tests/k0/runtime/test_syscalls_storage.py`
- [ ] Update Master Doc Part 5.2 (Syscall Registry)
- [ ] Update Master Doc Part 3.1 (M01 dependencies)
- [ ] All tests pass

##### Acceptance Criteria

**Function Signature**:

```python
async def storage_read_hipp_events(
    tenant_id: str,
    simhash_hex: Optional[str] = None,
    minhash32: Optional[List[int]] = None,
    event_ids: Optional[List[str]] = None,
    limit: int = 100,
    offset: int = 0
) -> List[Dict[str, Any]]:
    """
    Query st_hipp_events table with flexible filters.

    Args:
        tenant_id: Tenant isolation key
        simhash_hex: Filter by exact SimHash match (16-char hex)
        minhash32: Filter by MinHash similarity (Jaccard threshold)
        event_ids: Fetch specific events by ID
        limit: Max rows to return
        offset: Pagination offset

    Returns:
        List of event dicts (60-70 columns from st_hipp_events)

    Raises:
        StorageError: Database query failed
        ValidationError: Invalid filter parameters
    """
```

**Core Functionality**:

- [ ] **Exact SimHash Query**:
  - WHERE simhash_hex = $1
  - Uses index on simhash_hex column
  - Fast exact match (<5ms)

- [ ] **MinHash Similarity Query**:
  - Calculate Jaccard similarity between input minhash32 and stored hashes
  - Use PostgreSQL array operators or custom function
  - Return events above similarity threshold (e.g., >0.7)
  - Warn if slow (>50ms) - may need LSH bucketing in P03

- [ ] **Event ID Lookup**:
  - WHERE event_id = ANY($1)
  - Bulk fetch by primary key
  - Very fast (<5ms)

- [ ] **Tenant Isolation**:
  - Always filter by tenant_id (security)
  - Never leak events across tenants

- [ ] **Pagination**:
  - LIMIT and OFFSET for large result sets
  - Return empty list if no matches

**Error Handling**:

- [ ] Handle connection failures (retry 3x)
- [ ] Handle query timeout (abort after 10s)
- [ ] Log query parameters (structured logging)
- [ ] Emit metrics (query_latency_ms, rows_returned)

**Test Coverage**:

- [ ] **Unit Tests** (6-8 tests):
  - test_simhash_exact_match
  - test_minhash_similarity_query
  - test_event_id_bulk_lookup
  - test_tenant_isolation (no cross-tenant leaks)
  - test_pagination
  - test_empty_result_handling
  - test_connection_retry
  - test_query_timeout

- [ ] **Integration Tests** (3-4 tests):
  - test_query_with_real_database
  - test_performance_under_10ms (for event_id lookup)
  - test_concurrent_queries (thread safety)

**Master Document Validation**:

- [ ] Syscall entry in Part 5.2 with ✅ status
- [ ] M01 dependencies updated in Part 3.1

##### Implementation Steps

1. **Read Context**

   ```powershell
   # Review existing syscalls
   Get-Content k0\runtime\syscalls.py | Select-String "async def"

   # Check data schema
   Get-Content docs\pipelines\P02_data_schema.md | Select-Object -Skip 44 -First 140
   ```

2. **Implement Function**

   ```python
   # k0/runtime/syscalls.py (add to existing file)

   async def storage_read_hipp_events(
       tenant_id: str,
       simhash_hex: Optional[str] = None,
       minhash32: Optional[List[int]] = None,
       event_ids: Optional[List[str]] = None,
       limit: int = 100,
       offset: int = 0
   ) -> List[Dict[str, Any]]:
       """Query st_hipp_events with flexible filters."""

       # Validation
       if not tenant_id:
           raise ValidationError("tenant_id required")

       # Build query
       query = "SELECT * FROM st_hipp_events WHERE tenant_id = $1"
       params = [tenant_id]

       if simhash_hex:
           query += " AND simhash_hex = $2"
           params.append(simhash_hex)

       if event_ids:
           query += f" AND event_id = ANY($${len(params)+1})"
           params.append(event_ids)

       # MinHash similarity (if provided)
       if minhash32:
           # Use Jaccard similarity calculation
           # (This may be slow - consider LSH bucketing in P03)
           query += " AND calculate_minhash_jaccard(minhash32, $3) > 0.7"
           params.append(minhash32)

       query += f" LIMIT {limit} OFFSET {offset}"

       # Execute
       async with get_db_connection() as conn:
           rows = await conn.fetch(query, *params)
           return [dict(row) for row in rows]
   ```

3. **Write Tests**

   ```python
   # tests/k0/runtime/test_syscalls_storage.py

   @pytest.mark.asyncio
   async def test_simhash_exact_match():
       # Insert test event with known simhash
       test_simhash = "a1b2c3d4e5f67890"

       result = await storage_read_hipp_events(
           tenant_id="test_tenant",
           simhash_hex=test_simhash,
           limit=10
       )

       assert len(result) > 0
       assert result[0]["simhash_hex"] == test_simhash
   ```

4. **Update Master Document**
   - Add syscall to Part 5.2
   - Update M01 in Part 3.1

5. **Run Tests**

   ```powershell
   pytest tests/k0/runtime/test_syscalls_storage.py -v
   ```

##### Estimated Effort

- **Function Implementation**: 3 hours (query building + pagination)
- **MinHash Similarity Logic**: 2 hours (Jaccard calculation or PostgreSQL extension)
- **Unit Tests**: 2 hours (6-8 tests)
- **Integration Tests**: 1.5 hours (real DB tests)
- **Master Doc Updates**: 30 minutes
- **Total**: 9 hours

##### Dependencies

- **Blocks**: Issue 5.1.2 (writer syscall)
- **Blocked By**: Milestone 4 (modules need this for queries)

##### Notes

- MinHash similarity calculation may be slow (>50ms) without LSH indexes
- Consider PostgreSQL extension for efficient Jaccard similarity
- Defer full LSH bucketing to P03 (not critical for P02 write path)
- Keep query simple for P02 - optimize in P03 if needed

---

#### Issue 5.1.2: Implement syscalls.storage_write_hipp_events()

**Priority**: 🔴 Critical (M16 depends on this)
**Size**: M (6-8 hours)
**Assignee**: TBD

##### Context References

**Primary Sources**:

- **P02 Dossier**: Lines 880-895 (Syscall Inventory - storage_write_hipp_events)
- **Data Schema**: Lines 45-185 (st_hipp_events schema), Lines 447-485 (UnitOfWork)
- **M16 Contract**: `k0/contracts/modules/core.hipp_events_writer.v1.yaml`
- **Runtime Syscalls**: `k0/runtime/syscalls.py`

##### Master Document Tracking (MANDATORY)

**Update Locations**:

1. **Part 5.2**: Add `storage_write_hipp_events | Write | Insert enriched event row | k0/runtime/syscalls.py:storage_write_hipp_events | ✅ Implemented | M16`
2. **Part 3.1**: Update M16 dependencies

##### Deliverables

- [ ] Implement: `k0/runtime/syscalls.py::storage_write_hipp_events()`
- [ ] Create: `tests/k0/runtime/test_syscalls_storage.py::test_write_hipp_events_*`
- [ ] Update Master Doc Parts 5.2, 3.1
- [ ] All tests pass

##### Acceptance Criteria

**Function Signature**:

```python
async def storage_write_hipp_events(
    uow: UnitOfWork,
    event_row: Dict[str, Any]
) -> str:
    """
    Insert a single row into st_hipp_events within a UnitOfWork transaction.

    Args:
        uow: Active UnitOfWork context (manages transaction)
        event_row: Complete row dict (60-70 columns)

    Returns:
        event_id (UUID string)

    Raises:
        ValidationError: Missing required columns
        StorageError: Database insert failed
        UniqueConstraintViolation: event_id already exists
    """
```

**Core Functionality**:

- [ ] **Row Validation**:
  - Check all NOT NULL columns present
  - Validate data types (UUID strings, timestamps, numeric ranges)
  - Check text field not empty
  - Check salience_score in [0, 1]

- [ ] **UnitOfWork Integration**:
  - Add INSERT to uow.operations list
  - Do NOT commit (caller commits after all 3 writes)
  - Support rollback on failure

- [ ] **SQL Generation**:
  - Dynamic INSERT based on event_row keys
  - Use parameterized query (prevent SQL injection)
  - Return RETURNING event_id

- [ ] **Idempotency**:
  - Handle UniqueConstraintViolation on event_id
  - Return existing event_id if duplicate (no error)

**Error Handling**:

- [ ] ValidationError for missing required fields
- [ ] StorageError for database failures
- [ ] Log full row on error (for debugging)
- [ ] Emit metrics (insert_latency_ms, row_size_bytes)

**Test Coverage**:

- [ ] **Unit Tests** (6-8 tests):
  - test_insert_complete_row
  - test_validation_missing_required_field
  - test_validation_invalid_data_type
  - test_idempotent_duplicate_insert
  - test_uow_integration
  - test_rollback_on_failure
  - test_performance_under_30ms

- [ ] **Integration Tests** (3-4 tests):
  - test_insert_with_real_database
  - test_transaction_commit_success
  - test_transaction_rollback_on_error

**Master Document Validation**:

- [ ] Syscall in Part 5.2 with ✅
- [ ] M16 dependencies updated

##### Implementation Steps

1. Read M16 contract + UnitOfWork pattern
2. Implement validation logic (check NOT NULL columns)
3. Build dynamic INSERT query
4. Integrate with UnitOfWork (add operation, don't commit)
5. Write unit tests (6-8 tests)
6. Write integration tests
7. Update master document
8. Run tests

##### Estimated Effort

- **Function Implementation**: 3 hours (validation + SQL generation)
- **UnitOfWork Integration**: 2 hours (transaction management)
- **Unit Tests**: 2 hours
- **Integration Tests**: 1.5 hours
- **Master Doc Updates**: 30 minutes
- **Total**: 9 hours

##### Dependencies

- **Blocks**: Issue 5.2.1 (outbox syscall)
- **Blocked By**: Issue 5.1.1 (pattern established)

---

### Epic 5.2: Event Bus Syscalls Implementation

---

#### Issue 5.2.1: Implement syscalls.outbox_emit()

**Priority**: 🔴 Critical (M17 depends on this)
**Size**: M (5-6 hours)
**Assignee**: TBD

##### Context References

**Primary Sources**:

- **P02 Dossier**: Lines 896-910 (Syscall Inventory - outbox_emit)
- **M17 Contract**: `k0/contracts/modules/core.event_emitter.v1.yaml`
- **Outbox Pattern**: Research transactional outbox pattern (ensure at-least-once delivery)
- **Runtime Syscalls**: `k0/runtime/syscalls.py`

##### Master Document Tracking (MANDATORY)

**Update Locations**:

1. **Part 5.2**: Add `outbox_emit | Write | Enqueue event for relay worker | k0/runtime/syscalls.py:outbox_emit | ✅ Implemented | M17`
2. **Part 3.1**: Update M17 dependencies

##### Deliverables

- [ ] Implement: `k0/runtime/syscalls.py::outbox_emit()`
- [ ] Create: `tests/k0/runtime/test_syscalls_outbox.py`
- [ ] Update Master Doc Parts 5.2, 3.1
- [ ] All tests pass

##### Acceptance Criteria

**Function Signature**:

```python
async def outbox_emit(
    uow: UnitOfWork,
    topic: str,
    payload: Dict[str, Any],
    tenant_id: str,
    trace_id: Optional[str] = None
) -> str:
    """
    Enqueue an event to st_outbox for relay worker to publish.

    Args:
        uow: Active UnitOfWork (transaction context)
        topic: NATS topic (e.g., "workspace.wm.updated.v1")
        payload: Event payload (JSON-serializable dict)
        tenant_id: Tenant ID for routing
        trace_id: Optional trace ID for observability

    Returns:
        outbox_id (UUID string)

    Raises:
        ValidationError: Invalid topic or payload
        StorageError: Database insert failed
    """
```

**Core Functionality**:

- [ ] **Outbox Row Creation**:
  - `outbox_id`: UUID4
  - `topic`: Validated (matches `^[a-z_]+\.[a-z_]+\.[a-z_]+\.v\d+$`)
  - `payload`: JSON-serialized dict
  - `status`: "PENDING"
  - `retry_count`: 0
  - `created_at_utc`: Current timestamp
  - `tenant_id`: For routing

- [ ] **UnitOfWork Integration**:
  - Add INSERT to uow.operations
  - Do NOT publish directly (relay worker handles)
  - Atomic with other writes (hipp_events + embedding_queue)

- [ ] **Validation**:
  - Topic format valid
  - Payload serializable to JSON
  - Tenant ID not empty

**Error Handling**:

- [ ] ValidationError for invalid inputs
- [ ] StorageError for database failures
- [ ] Emit metrics (outbox_enqueue_latency_ms)

**Test Coverage**:

- [ ] **Unit Tests** (5-7 tests):
  - test_outbox_enqueue_success
  - test_topic_validation
  - test_payload_serialization
  - test_uow_integration
  - test_idempotent_enqueue
  - test_performance_under_5ms

- [ ] **Integration Tests** (2-3 tests):
  - test_outbox_row_created_in_database
  - test_relay_worker_picks_up_pending_events (future)

**Master Document Validation**:

- [ ] Syscall in Part 5.2 with ✅
- [ ] M17 dependencies updated

##### Implementation Steps

1. Read M17 contract + outbox pattern
2. Implement validation (topic format, JSON serialization)
3. Build INSERT query for st_outbox
4. Integrate with UnitOfWork
5. Write unit tests (5-7 tests)
6. Write integration tests
7. Update master document
8. Run tests

##### Estimated Effort

- **Function Implementation**: 2 hours (validation + INSERT)
- **UnitOfWork Integration**: 1.5 hours
- **Unit Tests**: 1.5 hours
- **Integration Tests**: 1 hour
- **Master Doc Updates**: 30 minutes
- **Total**: 6.5 hours

##### Dependencies

- **Blocks**: Issue 5.3.1 (embedding queue syscall)
- **Blocked By**: Issue 5.1.2 (UnitOfWork pattern established)

---

#### Issue 5.2.2: Implement syscalls.embedding_enqueue()

**Priority**: 🔴 Critical (M14 depends on this)
**Size**: M (5-6 hours)
**Assignee**: TBD

##### Context References

**Primary Sources**:

- **P02 Dossier**: Lines 896-910 (Syscall Inventory - embedding_enqueue)
- **M14 Contract**: `k0/contracts/modules/builders.embedding_queue.v1.yaml`
- **Data Schema**: Lines 250-280 (st_embedding_queue schema)
- **Runtime Syscalls**: `k0/runtime/syscalls.py`

##### Master Document Tracking (MANDATORY)

**Update Locations**:

1. **Part 5.2**: Add `embedding_enqueue | Write | Enqueue embedding job for P08 | k0/runtime/syscalls.py:embedding_enqueue | ✅ Implemented | M14`
2. **Part 3.1**: Update M14 dependencies

##### Deliverables

- [ ] Implement: `k0/runtime/syscalls.py::embedding_enqueue()`
- [ ] Create: `tests/k0/runtime/test_syscalls_embedding.py`
- [ ] Update Master Doc Parts 5.2, 3.1
- [ ] All tests pass

##### Acceptance Criteria

**Function Signature**:

```python
async def embedding_enqueue(
    uow: UnitOfWork,
    job_row: Dict[str, Any]
) -> str:
    """
    Enqueue an embedding job to st_embedding_queue for P08 processing.

    Args:
        uow: Active UnitOfWork
        job_row: Job dict with required fields:
            - embedding_id (UUID)
            - wal_pos (int64)
            - event_id (UUID)
            - text (str)
            - status ("PENDING")
            - attempt_count (0)

    Returns:
        embedding_id (UUID string)

    Raises:
        ValidationError: Missing required fields
        StorageError: Database insert failed
    """
```

**Core Functionality**:

- [ ] **Row Validation**:
  - Check required fields (embedding_id, wal_pos, event_id, text)
  - status must be "PENDING"
  - attempt_count must be 0 (initial job)

- [ ] **UnitOfWork Integration**:
  - Add INSERT to uow.operations
  - Atomic with hipp_events write

- [ ] **SQL Generation**:
  - INSERT INTO st_embedding_queue
  - RETURNING embedding_id

**Error Handling**:

- [ ] ValidationError for missing fields
- [ ] StorageError for database failures
- [ ] Emit metrics (embedding_enqueue_latency_ms)

**Test Coverage**:

- [ ] **Unit Tests** (5-6 tests):
  - test_enqueue_job_success
  - test_validation_missing_fields
  - test_uow_integration
  - test_idempotent_enqueue
  - test_performance_under_5ms

- [ ] **Integration Tests** (2-3 tests):
  - test_job_row_created_in_database
  - test_p08_worker_picks_up_pending (future)

**Master Document Validation**:

- [ ] Syscall in Part 5.2 with ✅
- [ ] M14 dependencies updated

##### Implementation Steps

1. Read M14 contract + embedding queue schema
2. Implement validation (check required fields)
3. Build INSERT query
4. Integrate with UnitOfWork
5. Write unit tests (5-6 tests)
6. Write integration tests
7. Update master document
8. Run tests

##### Estimated Effort

- **Function Implementation**: 2 hours (validation + INSERT)
- **UnitOfWork Integration**: 1.5 hours
- **Unit Tests**: 1.5 hours
- **Integration Tests**: 1 hour
- **Master Doc Updates**: 30 minutes
- **Total**: 6.5 hours

##### Dependencies

- **Blocks**: Milestone 6 (Integration Testing)
- **Blocked By**: Issue 5.2.1 (pattern established)

---

### Milestone 5 Summary

**Total Issues**: 4 syscall implementations
**Total Effort**: ~31 hours (4-5 days for 1 developer)
**Critical Path**: Issue 5.1.1 → 5.1.2 → 5.2.1 → 5.2.2

**Completion Criteria**:

- [ ] All 4 syscalls implemented in `k0/runtime/syscalls.py`
- [ ] Part 5.2 (Syscall Registry) has 4 entries with ✅ status
- [ ] All syscall tests pass (unit + integration)
- [ ] UnitOfWork integration validated (atomic transactions)
- [ ] Performance budgets met (<10ms for reads, <30ms for writes)
- [ ] M01, M14, M16, M17 dependencies satisfied

**Quality Gates**:

- [ ] All syscalls follow consistent error handling patterns
- [ ] Metrics emitted for all operations
- [ ] Trace context propagated through syscalls
- [ ] Transaction safety validated (rollback tests)
- [ ] No cross-tenant data leaks (tenant isolation tests)

**Next**: Proceed to Milestone 6 (Integration Testing) after all syscalls implemented

---

## Milestone 6: Integration Testing & End-to-End Validation

**Goal**: Validate P02 pipeline with full end-to-end integration tests, including DAG execution, module orchestration, and data flow verification.

**Status**: 📝 Not Started
**Duration**: 5-7 days
**Effort**: ~40-50 hours
**Prerequisites**:

- ✅ Milestone 4 complete (all modules implemented)
- ✅ Milestone 5 complete (all syscalls implemented)
- ✅ Pipeline YAML validated (Milestone 3)
- ✅ Runtime executor ready (k0/runtime/)

### Epic 6.1: Pipeline Integration Tests

---

#### Issue 6.1.1: Create P02 End-to-End Integration Test Suite

**Priority**: 🔴 Critical (validates entire pipeline)
**Size**: XL (15-18 hours)
**Assignee**: TBD

##### Context References

**Primary Sources**:

- **Pipeline YAML**: `k0/pipelines/p02_episodic_write.pipeline.yaml`
- **P02 Dossier**: Lines 580-680 (Phase 2 architecture), Lines 933-983 (Workflow validation)
- **All Module Contracts**: `k0/contracts/modules/*.yaml` (16 contracts)
- **Test Guidelines**: `docs/development/testing-guide.md`
- **Runtime Executor**: `k0/runtime/executor.py` (pipeline execution engine)

**Supporting Context**:

- **Entry Topic**: `cognitive.memory.write.committed.v1`
- **Exit Topics**: 6 topics (workspace.wm.updated, affect.analyzed, etc.)
- **DAG Stages**: 8 stages (stage_10 → stage_90)

##### Master Document Tracking (MANDATORY)

**Update Locations**:

1. **Part 8.1: Test Coverage Registry**
   - Add row:

     ```markdown
     | P02 End-to-End Integration | Integration | tests/integration/test_p02_e2e.py | ✅ Created | Full pipeline execution, DAG validation, data flow verification |
     ```

2. **Part 2.1: Pipeline Registry**
   - Update P02 row: Add integration test indicator
   - `Tests: ✅ E2E Integration`

##### Deliverables

- [ ] Create: `tests/integration/test_p02_e2e.py`
- [ ] Create: `tests/integration/fixtures/p02_test_envelopes.json` (test data)
- [ ] Update Master Doc Part 8.1 (Test Coverage)
- [ ] Update Master Doc Part 2.1 (P02 test status)
- [ ] All tests pass

##### Acceptance Criteria

**Test Suite Structure**:

- [ ] **Test 1: Happy Path - Complete Pipeline Execution**
  - Input: Single envelope (cognitive.memory.write.committed.v1)
  - Output: Event row in st_hipp_events, embedding job in queue, 6 exit events
  - Validation:
    - All 8 stages execute successfully
    - All 16 modules process envelope
    - Database transaction commits (hipp_events + embedding_queue + outbox)
    - Exit events emitted to correct topics
    - Total latency <150ms P95

- [ ] **Test 2: Module Failure Handling**
  - Inject failure in Stage 30 (affect.analyze)
  - Validation:
    - Pipeline halts (failure_policy: stop)
    - No database writes (transaction rolled back)
    - Error event emitted
    - Retry logic attempted (3 retries)
    - Failure logged with trace context

- [ ] **Test 3: DAG Stage Ordering**
  - Validation:
    - Stage 10 executes first (no dependencies)
    - Stage 20 waits for Stage 10 completion
    - Stage 30 modules execute in parallel (affect, space)
    - Stage 40 (context enrichment) runs after Stage 30
    - Stage 60 builders execute after all enrichment
    - Stage 70 writer executes after builders
    - Stage 90 emitter executes after writer commit

- [ ] **Test 4: Data Flow Validation**
  - Input: Envelope with known text ("Family dinner at home")
  - Validation:
    - M01 outputs: simhash_hex (16 chars), minhash32 (32 ints)
    - M02 outputs: embedding_id, entities (people, places)
    - M04 outputs: valence, arousal, affect_band
    - M05 outputs: visible_to list
    - M07 outputs: social_context, num_participants
    - M13 outputs: Complete row dict (60-70 columns)
    - M16 outputs: event_id (inserted row)
    - M17 outputs: 6 exit events in st_outbox

- [ ] **Test 5: Performance Under Load**
  - Input: 100 envelopes (parallel processing)
  - Validation:
    - P95 latency <150ms per envelope
    - P99 latency <250ms per envelope
    - Throughput >6 events/sec (single worker)
    - No memory leaks (stable memory after 100 runs)
    - No database connection leaks

- [ ] **Test 6: Idempotency Validation**
  - Input: Same envelope processed twice
  - Validation:
    - First run: Inserts event row
    - Second run: Detects duplicate (event_id exists)
    - No duplicate rows in st_hipp_events
    - Exit events emitted only once

- [ ] **Test 7: Tenant Isolation**
  - Input: Envelopes from 2 different tenants
  - Validation:
    - Tenant A events isolated from Tenant B
    - Visibility resolution respects tenant boundaries
    - No cross-tenant data leaks
    - Database queries always filter by tenant_id

- [ ] **Test 8: Trace Context Propagation**
  - Input: Envelope with trace_id
  - Validation:
    - Trace ID propagated through all 16 modules
    - Logged in all structured logs
    - Emitted in all exit events
    - Visible in observability dashboards

**Test Utilities**:

- [ ] **Fixture: create_test_envelope()**
  - Generates valid WAL-committed envelope
  - Configurable: tenant_id, text, participants, location, etc.
  - Returns typed Envelope object

- [ ] **Fixture: mock_database()**
  - In-memory SQLite or test PostgreSQL
  - Initializes st_hipp_events, st_embedding_queue, st_outbox tables
  - Cleans up after tests

- [ ] **Fixture: pipeline_executor()**
  - Loads P02 pipeline YAML
  - Initializes all 16 modules
  - Returns executor instance

- [ ] **Helper: assert_row_in_database()**
  - Validates row exists in st_hipp_events
  - Checks column values match expectations

- [ ] **Helper: assert_exit_events_emitted()**
  - Checks all 6 exit topics have events in st_outbox
  - Validates payload structure

**Master Document Validation**:

- [ ] Test suite entry in Part 8.1 with ✅
- [ ] P02 in Part 2.1 shows E2E test status

##### Implementation Steps

1. **Setup Test Infrastructure**

   ```powershell
   # Create integration test directory
   New-Item -ItemType Directory -Force -Path "tests\integration"

   # Create fixtures directory
   New-Item -ItemType Directory -Force -Path "tests\integration\fixtures"
   ```

2. **Create Test Fixtures**

   ```python
   # tests/integration/fixtures/p02_fixtures.py

   @pytest.fixture
   async def mock_database():
       """In-memory test database."""
       db = await create_test_database()
       await db.execute("""
           CREATE TABLE st_hipp_events (
               event_id UUID PRIMARY KEY,
               tenant_id TEXT NOT NULL,
               text TEXT NOT NULL,
               -- ... 60-70 columns
           )
       """)
       yield db
       await db.close()

   @pytest.fixture
   def create_test_envelope():
       """Factory for test envelopes."""
       def _create(text="Test event", tenant_id="test_tenant"):
           return Envelope(
               event_id=str(uuid.uuid4()),
               tenant_id=tenant_id,
               body={"text": text},
               # ... other fields
           )
       return _create

   @pytest.fixture
   async def pipeline_executor():
       """Load P02 pipeline."""
       yaml_path = "k0/pipelines/p02_episodic_write.pipeline.yaml"
       executor = PipelineExecutor.from_yaml(yaml_path)
       await executor.initialize_modules()
       yield executor
       await executor.shutdown()
   ```

3. **Write Test 1: Happy Path**

   ```python
   # tests/integration/test_p02_e2e.py

   @pytest.mark.asyncio
   async def test_p02_happy_path_complete_execution(
       pipeline_executor,
       create_test_envelope,
       mock_database
   ):
       """Test complete P02 pipeline execution."""

       # Arrange
       envelope = create_test_envelope(text="Family dinner at home")

       # Act
       start = time.perf_counter()
       result = await pipeline_executor.execute(envelope)
       latency_ms = (time.perf_counter() - start) * 1000

       # Assert - Execution Success
       assert result.status == "SUCCESS"
       assert len(result.stage_results) == 8  # All 8 stages

       # Assert - Database Writes
       event_row = await mock_database.fetch_one(
           "SELECT * FROM st_hipp_events WHERE event_id = $1",
           envelope.event_id
       )
       assert event_row is not None
       assert event_row["text"] == "Family dinner at home"
       assert event_row["simhash_hex"] is not None
       assert len(event_row["minhash32"]) == 32

       # Assert - Embedding Job
       job_row = await mock_database.fetch_one(
           "SELECT * FROM st_embedding_queue WHERE event_id = $1",
           envelope.event_id
       )
       assert job_row is not None
       assert job_row["status"] == "PENDING"

       # Assert - Exit Events
       outbox_events = await mock_database.fetch_all(
           "SELECT * FROM st_outbox WHERE status = 'PENDING'"
       )
       assert len(outbox_events) == 6  # All 6 exit topics
       topics = {e["topic"] for e in outbox_events}
       assert "workspace.wm.updated.v1" in topics
       assert "p02.write.complete.v1" in topics

       # Assert - Performance
       assert latency_ms < 150, f"Latency {latency_ms:.2f}ms exceeds 150ms budget"
   ```

4. **Write Tests 2-8** (similar structure, different validations)

5. **Update Master Document**
   - Add test suite to Part 8.1
   - Update P02 E2E test status in Part 2.1

6. **Run Tests**

   ```powershell
   pytest tests/integration/test_p02_e2e.py -v --log-level=DEBUG
   ```

##### Estimated Effort

- **Test Infrastructure Setup**: 3 hours (fixtures, database mocks)
- **Test 1 (Happy Path)**: 3 hours (full validation)
- **Test 2 (Failure Handling)**: 2 hours
- **Test 3 (DAG Ordering)**: 2 hours
- **Test 4 (Data Flow)**: 3 hours (validate all module outputs)
- **Test 5 (Performance)**: 2 hours (load testing)
- **Test 6 (Idempotency)**: 1.5 hours
- **Test 7 (Tenant Isolation)**: 1.5 hours
- **Test 8 (Trace Propagation)**: 1 hour
- **Master Doc Updates**: 30 minutes
- **Total**: 19.5 hours

##### Dependencies

- **Blocks**: Issue 6.2.1 (data validation tests)
- **Blocked By**: Milestone 5 complete (all syscalls ready)

##### Notes

- **Critical milestone** - validates entire P02 pipeline
- Use real database (test PostgreSQL) for accurate integration testing
- Consider CI/CD integration (run on every commit)
- Monitor test execution time (should complete in <5 minutes)
- Keep test data representative (realistic envelopes, edge cases)

---

#### Issue 6.1.2: Create Contract Compliance Tests

**Priority**: 🔴 Critical
**Size**: L (10-12 hours)
**Assignee**: TBD

##### Context References

**Primary Sources**:

- **All 16 Module Contracts**: `k0/contracts/modules/*.yaml`
- **Runtime Contract Validator**: `k0/runtime/contract_validator.py`
- **Test Guidelines**: `docs/development/testing-guide.md`

##### Master Document Tracking (MANDATORY)

**Update Locations**:

1. **Part 8.1**: Add `P02 Contract Compliance | Integration | tests/integration/test_p02_contract_compliance.py | ✅ Created | Validates all modules honor contracts`
2. **Part 2.1**: Update P02 test indicators

##### Deliverables

- [ ] Create: `tests/integration/test_p02_contract_compliance.py`
- [ ] Update Master Doc Parts 8.1, 2.1
- [ ] All tests pass

##### Acceptance Criteria

**Test Coverage** (16 tests, one per module):

- [ ] **Test: M01 Contract Compliance**
  - Validate output schema matches contract
  - Check latency_budget_ms <= 15ms
  - Verify side_effects declared (read:st_hipp_events)
  - Confirm idempotency (same input → same output)

- [ ] **Test: M02-M17 Contract Compliance** (similar structure)
  - Output schema validation
  - Latency budget compliance
  - Side effects declared
  - Idempotency guarantee

**Validation Points Per Module**:

- [ ] Output keys match contract output_event_types
- [ ] No undeclared side effects (no unexpected DB queries)
- [ ] Performance within budget (measured over 100 runs)
- [ ] Error codes match failure_modes in contract
- [ ] Retry logic follows contract retry_policy

**Test Structure**:

```python
@pytest.mark.parametrize("module_id,contract_path", [
    ("hippocampus.pattern_separate", "k0/contracts/modules/hippocampus.pattern_separate.v1.yaml"),
    # ... 15 more modules
])
@pytest.mark.asyncio
async def test_module_contract_compliance(module_id, contract_path):
    # Load contract
    contract = load_contract_yaml(contract_path)

    # Initialize module
    module = load_module(module_id, contract.config_schema)

    # Execute with test envelope
    envelope = create_test_envelope()
    result = await module.process(envelope)

    # Validate output schema
    assert validate_output_schema(result, contract.output_event_types)

    # Validate latency
    latency = measure_latency(module, envelope, iterations=100)
    assert latency.p95 <= contract.latency_budget_ms

    # Validate side effects
    observed_side_effects = track_side_effects(module, envelope)
    assert observed_side_effects <= set(contract.side_effects)

    # Validate idempotency
    result2 = await module.process(envelope)
    assert result == result2
```

**Master Document Validation**:

- [ ] Test entry in Part 8.1
- [ ] P02 contract compliance indicator added

##### Implementation Steps

1. Create test file with parameterized tests
2. Implement contract loader (parse YAML)
3. Implement output schema validator
4. Implement side effect tracker (monitor DB queries)
5. Write 16 parameterized test cases
6. Update master document
7. Run tests

##### Estimated Effort

- **Test Infrastructure**: 3 hours (contract loader, validators)
- **Parameterized Tests**: 4 hours (16 modules)
- **Side Effect Tracking**: 2 hours (query monitoring)
- **Performance Measurement**: 2 hours (latency validation)
- **Master Doc Updates**: 30 minutes
- **Total**: 11.5 hours

##### Dependencies

- **Blocks**: Milestone 7 (Production Testing)
- **Blocked By**: Issue 6.1.1 (E2E tests establish patterns)

---

### Epic 6.2: Data Validation Tests

(Additional issues for data schema validation, row completeness checks, etc. - ~10-15 hours)

---

### Milestone 6 Summary

**Total Issues**: 4-5 integration test suites
**Total Effort**: ~45-50 hours (5-7 days for 1 developer)
**Critical Path**: Issue 6.1.1 → 6.1.2 → 6.2.1 → 6.2.2

**Completion Criteria**:

- [ ] P02 E2E integration tests passing (8 test scenarios)
- [ ] All 16 modules pass contract compliance tests
- [ ] Data validation tests pass (schema, constraints, relationships)
- [ ] Performance benchmarks pass (<150ms P95 end-to-end)
- [ ] Part 8.1 shows all integration test entries with ✅
- [ ] Part 2.1 shows P02 fully tested

**Quality Gates**:

- [ ] Test coverage ≥90% for integration tests
- [ ] No flaky tests (100% pass rate over 10 runs)
- [ ] Performance regression tests automated
- [ ] Failure injection tests validate error handling
- [ ] Tenant isolation validated (no cross-tenant leaks)

**Next**: Proceed to Milestone 7 (Production Testing & Deployment) after integration tests pass

---

## Milestone 7: Production Testing & Deployment Readiness

**Goal**: Validate P02 pipeline under production-like conditions, complete observability instrumentation, create deployment artifacts, and establish operational runbooks.

**Status**: 📝 Not Started
**Duration**: 6-8 days
**Effort**: ~45-55 hours
**Prerequisites**:

- ✅ Milestone 6 complete (all integration tests passing)
- ✅ Observability infrastructure ready (tracing, metrics, logging)
- ✅ Deployment infrastructure ready (k0/deploy/)
- ✅ Production database migration ready (migration 0024)

### Epic 7.1: Production Testing & Performance Validation

---

#### Issue 7.1.1: Load Testing & Performance Benchmarking

**Priority**: 🔴 Critical (production readiness gate)
**Size**: L (10-12 hours)
**Assignee**: TBD

##### Context References

**Primary Sources**:

- **P02 Dossier**: Lines 690-750 (Performance Targets), Lines 933-983 (Workflow Step 11: Production Testing)
- **Performance Requirements**:
  - Total latency: <150ms P95, <250ms P99
  - Throughput: >10 events/sec (single worker)
  - Memory: <500MB per worker
  - Database connections: <10 concurrent per worker
- **Load Testing Tools**: Locust, k6, or custom Python scripts
- **Performance Guide**: `docs/development/testing-guide.md` (performance testing section)

##### Master Document Tracking (MANDATORY)

**Update Locations**:

1. **Part 8.1: Test Coverage Registry**
   - Add row:

     ```markdown
     | P02 Load Testing | Performance | tests/performance/test_p02_load.py | ✅ Created | 1000 events, latency P95/P99, throughput, resource usage |
     ```

2. **Part 2.1: Pipeline Registry**
   - Update P02 row: Add performance test indicator
   - `Tests: ✅ E2E Integration, ✅ Load Testing`

##### Deliverables

- [ ] Create: `tests/performance/test_p02_load.py`
- [ ] Create: `tests/performance/load_test_scenarios.yaml` (test scenarios)
- [ ] Create: `docs/runbooks/p02_performance_baseline.md` (benchmark results)
- [ ] Update Master Doc Part 8.1 (Test Coverage)
- [ ] Update Master Doc Part 2.1 (P02 test status)
- [ ] Performance report generated

##### Acceptance Criteria

**Load Test Scenarios**:

- [ ] **Scenario 1: Steady State Load**
  - Input: 1000 envelopes over 100 seconds (10 events/sec)
  - Validation:
    - P95 latency <150ms
    - P99 latency <250ms
    - 0% error rate
    - Memory stable (<500MB)
    - No connection leaks

- [ ] **Scenario 2: Burst Load**
  - Input: 500 envelopes in 10 seconds (50 events/sec burst)
  - Validation:
    - P95 latency <200ms (acceptable degradation)
    - P99 latency <400ms
    - Error rate <1%
    - Queue depth recovers after burst

- [ ] **Scenario 3: Sustained High Load**
  - Input: 5000 envelopes over 300 seconds (16-17 events/sec)
  - Validation:
    - Throughput sustained (no degradation over time)
    - Memory stable (no leaks)
    - Database connection pool healthy
    - No worker crashes

- [ ] **Scenario 4: Large Event Payloads**
  - Input: 100 envelopes with 10KB text each
  - Validation:
    - P95 latency <200ms (larger payload acceptable)
    - No memory spikes (streaming processing)
    - Database write performance stable

- [ ] **Scenario 5: Concurrent Workers**
  - Input: 1000 envelopes processed by 4 workers in parallel
  - Validation:
    - Linear throughput scaling (4x single worker)
    - No database contention (connection pooling works)
    - No race conditions or duplicate writes

**Metrics Collected**:

- [ ] Latency histogram (P50, P75, P90, P95, P99)
- [ ] Throughput (events/sec)
- [ ] Error rate (%)
- [ ] Memory usage (MB over time)
- [ ] CPU usage (% over time)
- [ ] Database connection count
- [ ] Database query latency
- [ ] Module-level latency breakdown (which module is slowest?)

**Performance Report**:

- [ ] Create `docs/runbooks/p02_performance_baseline.md` with:
  - Test environment description (hardware, database config)
  - Test scenarios and results (tables, graphs)
  - Latency percentiles per scenario
  - Throughput metrics
  - Resource usage trends
  - Bottleneck analysis (which modules need optimization?)
  - Recommendations for production tuning

**Master Document Validation**:

- [ ] Load test entry in Part 8.1 with ✅
- [ ] P02 shows load testing status in Part 2.1

##### Implementation Steps

1. **Setup Load Testing Infrastructure**

   ```powershell
   # Create performance test directory
   New-Item -ItemType Directory -Force -Path "tests\performance"

   # Install load testing tools
   pip install locust pytest-benchmark psutil
   ```

2. **Create Load Test Script**

   ```python
   # tests/performance/test_p02_load.py

   import time
   import psutil
   from typing import List
   from locust import HttpUser, task, between

   class P02LoadTest:
       """Load testing for P02 pipeline."""

       def __init__(self, pipeline_executor, database):
           self.executor = pipeline_executor
           self.db = database
           self.metrics = []

       async def run_scenario_1_steady_state(self):
           """1000 events at 10 events/sec."""
           envelopes = [create_test_envelope() for _ in range(1000)]
           latencies = []

           start_time = time.time()
           for i, envelope in enumerate(envelopes):
               # Throttle to 10 events/sec
               target_time = start_time + (i * 0.1)
               sleep_time = max(0, target_time - time.time())
               await asyncio.sleep(sleep_time)

               # Execute pipeline
               t0 = time.perf_counter()
               result = await self.executor.execute(envelope)
               latency_ms = (time.perf_counter() - t0) * 1000
               latencies.append(latency_ms)

               # Record metrics
               self.metrics.append({
                   "event_num": i,
                   "latency_ms": latency_ms,
                   "memory_mb": psutil.Process().memory_info().rss / 1024 / 1024,
                   "cpu_percent": psutil.Process().cpu_percent(),
                   "status": result.status
               })

           # Calculate percentiles
           p50 = np.percentile(latencies, 50)
           p95 = np.percentile(latencies, 95)
           p99 = np.percentile(latencies, 99)

           # Assertions
           assert p95 < 150, f"P95 latency {p95:.2f}ms exceeds 150ms"
           assert p99 < 250, f"P99 latency {p99:.2f}ms exceeds 250ms"

           return {
               "scenario": "steady_state",
               "events": 1000,
               "p50": p50,
               "p95": p95,
               "p99": p99,
               "throughput": 1000 / (time.time() - start_time)
           }
   ```

3. **Create Test Scenarios YAML**

   ```yaml
   # tests/performance/load_test_scenarios.yaml
   scenarios:
     - name: steady_state
       events: 1000
       duration_sec: 100
       rate_per_sec: 10
       payload_size_kb: 1
       expected_p95_ms: 150
       expected_p99_ms: 250

     - name: burst_load
       events: 500
       duration_sec: 10
       rate_per_sec: 50
       payload_size_kb: 1
       expected_p95_ms: 200
       expected_p99_ms: 400

     # ... scenarios 3-5
   ```

4. **Run Load Tests**

   ```powershell
   # Run all scenarios
   pytest tests/performance/test_p02_load.py -v --benchmark-only

   # Generate performance report
   python tests/performance/generate_report.py > docs/runbooks/p02_performance_baseline.md
   ```

5. **Create Performance Baseline Document**

   ```markdown
   # P02 Performance Baseline

   ## Test Environment
   - Hardware: 4-core CPU, 16GB RAM
   - Database: PostgreSQL 14, default config
   - Workers: 1 (single worker baseline)

   ## Results

   ### Scenario 1: Steady State (10 events/sec)
   | Metric | Result | Target | Status |
   |--------|--------|--------|--------|
   | P50 | 85ms | <100ms | ✅ |
   | P95 | 132ms | <150ms | ✅ |
   | P99 | 198ms | <250ms | ✅ |
   | Throughput | 10.2 events/sec | >10 | ✅ |
   | Memory | 420MB | <500MB | ✅ |

   ### Bottleneck Analysis
   - **Slowest module**: M16 (hipp_events_writer) - 35ms avg (database write)
   - **Second slowest**: M02 (semantic_project) - 18ms avg (entity extraction)
   - **Fastest modules**: M08-M12 (context enrichment) - <5ms avg (cache hits)

   ### Recommendations
   1. Optimize M16: Use batch writes for multiple events
   2. Consider async entity extraction in M02 (defer to background job)
   3. Increase database connection pool size for multi-worker scenarios
   ```

6. **Update Master Document**
   - Add load test entry to Part 8.1
   - Update P02 load testing status in Part 2.1

##### Estimated Effort

- **Load Test Infrastructure**: 2 hours (setup, tooling)
- **Scenario 1-3 Implementation**: 4 hours (steady, burst, sustained)
- **Scenario 4-5 Implementation**: 2 hours (large payloads, concurrent workers)
- **Metrics Collection**: 2 hours (resource monitoring)
- **Performance Report**: 2 hours (analyze results, write baseline doc)
- **Master Doc Updates**: 30 minutes
- **Total**: 12.5 hours

##### Dependencies

- **Blocks**: Issue 7.1.2 (chaos testing)
- **Blocked By**: Milestone 6 complete (integration tests passing)

##### Notes

- **Critical gate** - P02 must meet performance SLAs before production
- Run load tests on production-like hardware for accuracy
- Monitor database query plans (identify slow queries)
- Consider profiling slowest modules (cProfile, py-spy)
- Establish performance regression CI/CD checks (run on every commit)

---

#### Issue 7.1.2: Chaos Testing & Failure Resilience

**Priority**: 🔴 Critical
**Size**: L (8-10 hours)
**Assignee**: TBD

##### Context References

**Primary Sources**:

- **P02 Dossier**: Lines 933-983 (Workflow Step 11: Production Testing - failure scenarios)
- **Chaos Module**: `k0/chaos/` (if exists - failure injection framework)
- **ADR - Error Handling**: Check for ADRs on retry policies and failure modes
- **Test Guidelines**: `docs/development/testing-guide.md` (chaos testing section)

##### Master Document Tracking (MANDATORY)

**Update Locations**:

1. **Part 8.1**: Add `P02 Chaos Testing | Resilience | tests/chaos/test_p02_chaos.py | ✅ Created | Database failures, network timeouts, module failures`
2. **Part 2.1**: Update P02 test indicators

##### Deliverables

- [ ] Create: `tests/chaos/test_p02_chaos.py`
- [ ] Create: `docs/runbooks/p02_failure_scenarios.md` (failure playbook)
- [ ] Update Master Doc Parts 8.1, 2.1
- [ ] All chaos tests pass

##### Acceptance Criteria

**Chaos Test Scenarios**:

- [ ] **Test 1: Database Connection Failure**
  - Inject: Kill database connection mid-transaction
  - Expected: Pipeline retries 3x, rolls back transaction, emits error event
  - Validation: No partial writes, data consistency maintained

- [ ] **Test 2: Database Deadlock**
  - Inject: Concurrent writes create deadlock
  - Expected: PostgreSQL detects deadlock, one transaction aborts, pipeline retries
  - Validation: All events eventually processed

- [ ] **Test 3: Module Timeout**
  - Inject: M02 (semantic_project) hangs for 60 seconds
  - Expected: Pipeline timeout kicks in (10s), module killed, pipeline fails
  - Validation: Timeout logged, no zombie processes

- [ ] **Test 4: Memory Exhaustion**
  - Inject: Large event (100MB payload) causes OOM
  - Expected: Pipeline rejects event, emits error, worker remains stable
  - Validation: Worker doesn't crash, next events processed normally

- [ ] **Test 5: Network Partition (Outbox Relay)**
  - Inject: NATS server unreachable
  - Expected: Outbox writes succeed (events queued), relay worker retries publish
  - Validation: At-least-once delivery guaranteed

- [ ] **Test 6: Cascading Failures**
  - Inject: M04 (affect.analyze) fails, causing M06 (salience.score) to fail
  - Expected: Pipeline halts at Stage 30, no downstream stages execute
  - Validation: Failure policy (stop) honored

- [ ] **Test 7: Slow Module (Latency Spike)**
  - Inject: M16 (writer) takes 5 seconds (database slowdown)
  - Expected: Pipeline completes but exceeds latency budget, alert triggered
  - Validation: SLA violation logged, monitoring alert fired

- [ ] **Test 8: Partial Failure Recovery**
  - Inject: UnitOfWork partially succeeds (hipp_events written, embedding_queue fails)
  - Expected: Transaction rolls back both writes, no orphaned rows
  - Validation: Database consistency maintained

**Failure Playbook**:

- [ ] Create `docs/runbooks/p02_failure_scenarios.md` with:
  - Failure scenarios (8 documented)
  - Expected behavior per scenario
  - Manual recovery steps (if needed)
  - Monitoring alerts to watch
  - Debugging commands (query logs, check database state)

**Master Document Validation**:

- [ ] Chaos test entry in Part 8.1 with ✅
- [ ] P02 shows chaos testing status

##### Implementation Steps

1. Setup chaos testing framework (failure injection library)
2. Write 8 chaos test scenarios
3. Implement failure injection points (database kill, network partition, etc.)
4. Run chaos tests and validate resilience
5. Document failure scenarios in runbook
6. Update master document
7. Run tests

##### Estimated Effort

- **Chaos Infrastructure**: 2 hours (failure injection setup)
- **Test Scenarios 1-4**: 3 hours (database, timeout, memory, network)
- **Test Scenarios 5-8**: 3 hours (cascading, latency, partial failure)
- **Failure Playbook**: 2 hours (document recovery procedures)
- **Master Doc Updates**: 30 minutes
- **Total**: 10.5 hours

##### Dependencies

- **Blocks**: Issue 7.2.1 (observability validation)
- **Blocked By**: Issue 7.1.1 (load testing establishes baseline)

---

### Epic 7.2: Observability & Monitoring

---

#### Issue 7.2.1: Observability Instrumentation & Validation

**Priority**: 🔴 Critical (production ops requirement)
**Size**: L (8-10 hours)
**Assignee**: TBD

##### Context References

**Primary Sources**:

- **P02 Dossier**: Lines 933-983 (Workflow Step 11: Production Testing - observability)
- **Observability Guide**: `k0/obs/README.md` (tracing, metrics, logging standards)
- **Runtime Tracing**: `k0/runtime/tracing.py` (trace context propagation)
- **Metrics Module**: `k0/telemetry/` (Prometheus metrics)

##### Master Document Tracking (MANDATORY)

**Update Locations**:

1. **Part 8.1**: Add `P02 Observability Validation | Operational | tests/observability/test_p02_observability.py | ✅ Created | Traces, metrics, logs, alerts`
2. **Part 2.1**: Update P02 observability status

##### Deliverables

- [ ] Create: `tests/observability/test_p02_observability.py`
- [ ] Create: `k0/obs/p02_dashboards.json` (Grafana dashboards)
- [ ] Create: `k0/obs/p02_alerts.yaml` (alert rules)
- [ ] Create: `docs/runbooks/p02_observability_guide.md`
- [ ] Update Master Doc Parts 8.1, 2.1
- [ ] All observability tests pass

##### Acceptance Criteria

**Tracing Validation**:

- [ ] Every envelope processed generates complete trace
- [ ] Trace spans include all 8 stages + 16 modules
- [ ] Trace context propagated through syscalls
- [ ] Trace IDs in all log messages
- [ ] Distributed traces link P02 → P08 (embedding job)

**Metrics Validation**:

- [ ] **Pipeline Metrics**:
  - `p02_events_processed_total` (counter)
  - `p02_latency_seconds` (histogram with P50/P95/P99)
  - `p02_errors_total` (counter by error_type)
  - `p02_stage_latency_seconds` (histogram by stage_id)

- [ ] **Module Metrics** (per module):
  - `module_latency_seconds{module_id="hippocampus.pattern_separate"}`
  - `module_errors_total{module_id="..."}`

- [ ] **Syscall Metrics**:
  - `syscall_latency_seconds{syscall="storage_write_hipp_events"}`
  - `syscall_errors_total{syscall="..."}`

- [ ] **Database Metrics**:
  - `db_queries_total{table="st_hipp_events"}`
  - `db_query_latency_seconds`
  - `db_connection_pool_size`

**Logging Validation**:

- [ ] Structured JSON logs for all events
- [ ] Log levels appropriate (INFO for success, ERROR for failures)
- [ ] PII redacted in logs (no raw text content)
- [ ] Logs include trace_id, tenant_id, event_id, stage_id, module_id
- [ ] Error logs include stack traces

**Alerting Validation**:

- [ ] **Alert 1: High Latency**
  - Trigger: P95 latency >150ms for 5 minutes
  - Severity: Warning
  - Action: Page on-call if P95 >250ms

- [ ] **Alert 2: High Error Rate**
  - Trigger: Error rate >1% for 5 minutes
  - Severity: Critical
  - Action: Page on-call immediately

- [ ] **Alert 3: Pipeline Throughput Drop**
  - Trigger: Throughput <5 events/sec for 10 minutes
  - Severity: Warning
  - Action: Investigate worker health

- [ ] **Alert 4: Database Connection Exhaustion**
  - Trigger: Connection pool >90% for 5 minutes
  - Severity: Warning
  - Action: Scale workers or increase pool size

**Dashboards**:

- [ ] Create Grafana dashboard: `P02 Pipeline Overview`
  - Panel 1: Event throughput (events/sec over time)
  - Panel 2: Latency percentiles (P50, P95, P99)
  - Panel 3: Error rate (%)
  - Panel 4: Stage latency breakdown (stacked bar chart)
  - Panel 5: Module latency heatmap (which modules are slow?)
  - Panel 6: Database query latency
  - Panel 7: Memory/CPU usage per worker

**Observability Guide**:

- [ ] Create `docs/runbooks/p02_observability_guide.md` with:
  - Metrics catalog (all metrics + descriptions)
  - Dashboard screenshots
  - Alert definitions
  - Debugging workflows (how to trace slow requests)
  - Log query examples (Elasticsearch/Loki queries)

**Master Document Validation**:

- [ ] Observability test entry in Part 8.1 with ✅
- [ ] P02 shows observability status in Part 2.1

##### Implementation Steps

1. **Validate Tracing**

   ```python
   # tests/observability/test_p02_observability.py

   @pytest.mark.asyncio
   async def test_trace_context_propagation():
       """Validate trace context flows through pipeline."""

       # Create envelope with trace_id
       envelope = create_test_envelope()
       trace_id = "test-trace-123"
       envelope.trace_id = trace_id

       # Execute pipeline with trace collection
       with trace_collector() as collector:
           await pipeline_executor.execute(envelope)

       # Validate trace spans
       spans = collector.get_spans()
       assert len(spans) >= 24  # 8 stages + 16 modules

       # Check trace_id in all spans
       for span in spans:
           assert span.trace_id == trace_id

       # Check span hierarchy
       assert spans[0].name == "p02.stage_10_dg_pattern_separate"
       assert spans[1].name == "hippocampus.pattern_separate.process"
   ```

2. **Create Metrics Tests**

   ```python
   @pytest.mark.asyncio
   async def test_metrics_emitted():
       """Validate all pipeline metrics emitted."""

       # Execute pipeline
       envelope = create_test_envelope()
       await pipeline_executor.execute(envelope)

       # Check metrics
       metrics = get_prometheus_metrics()

       assert "p02_events_processed_total" in metrics
       assert metrics["p02_events_processed_total"] == 1

       assert "p02_latency_seconds" in metrics
       assert metrics["p02_latency_seconds"]["p95"] < 0.15  # 150ms
   ```

3. **Create Grafana Dashboards**

   ```json
   // k0/obs/p02_dashboards.json
   {
     "dashboard": {
       "title": "P02 Pipeline Overview",
       "panels": [
         {
           "title": "Event Throughput",
           "targets": [
             {
               "expr": "rate(p02_events_processed_total[5m])"
             }
           ]
         },
         // ... more panels
       ]
     }
   }
   ```

4. **Create Alert Rules**

   ```yaml
   # k0/obs/p02_alerts.yaml
   groups:
     - name: p02_pipeline
       rules:
         - alert: P02HighLatency
           expr: histogram_quantile(0.95, p02_latency_seconds) > 0.15
           for: 5m
           labels:
             severity: warning
           annotations:
             summary: "P02 P95 latency exceeds 150ms"
   ```

5. **Update Master Document**
   - Add observability test to Part 8.1
   - Update P02 observability status in Part 2.1

##### Estimated Effort

- **Tracing Validation**: 2 hours (test trace propagation)
- **Metrics Validation**: 3 hours (test all metric types)
- **Logging Validation**: 1.5 hours (structured logs, PII redaction)
- **Dashboards**: 2 hours (Grafana JSON)
- **Alert Rules**: 1.5 hours (Prometheus alerts)
- **Observability Guide**: 2 hours (documentation)
- **Master Doc Updates**: 30 minutes
- **Total**: 12.5 hours

##### Dependencies

- **Blocks**: Issue 7.3.1 (deployment artifacts)
- **Blocked By**: Issue 7.1.2 (chaos testing complete)

---

### Epic 7.3: Deployment Readiness

---

#### Issue 7.3.1: Deployment Artifacts & Migration Scripts

**Priority**: 🔴 Critical (blocks production deployment)
**Size**: M (6-8 hours)
**Assignee**: TBD

##### Context References

**Primary Sources**:

- **P02 Dossier**: Lines 933-983 (Workflow Step 11: Production Testing - deployment prep)
- **Deployment Guide**: `k0/deploy/README.md` (deployment procedures)
- **Migration Plan**: `k0/pipelines/MIGRATION_PLAN.md` (Week 3: P02 deployment)
- **Database Migration**: Check for migration 0024 (st_hipp_events + st_embedding_queue tables)

##### Master Document Tracking (MANDATORY)

**Update Locations**:

1. **Part 2.1**: Update P02 deployment status
   - `Deployment: ✅ Artifacts Ready`
2. **Part 5.3**: Database Migration Registry (if exists)
   - Add migration 0024 entry

##### Deliverables

- [ ] Create: `k0/deploy/p02_deployment.yaml` (Kubernetes deployment config)
- [ ] Create: `k0/deploy/migrations/0024_p02_tables.sql` (database migration)
- [ ] Create: `k0/deploy/p02_config.yaml` (pipeline configuration)
- [ ] Create: `docs/runbooks/p02_deployment_guide.md`
- [ ] Update Master Doc Part 2.1 (deployment status)
- [ ] All deployment artifacts validated

##### Acceptance Criteria

**Database Migration**:

- [ ] **Migration 0024: Create P02 Tables**

  ```sql
  -- k0/deploy/migrations/0024_p02_tables.sql

  -- Create st_hipp_events table (60-70 columns)
  CREATE TABLE IF NOT EXISTS st_hipp_events (
      event_id UUID PRIMARY KEY,
      tenant_id TEXT NOT NULL,
      wal_pos BIGINT NOT NULL,
      text TEXT NOT NULL,

      -- Hippocampus fingerprints
      simhash_hex TEXT,
      minhash32 INTEGER[],

      -- Affect
      valence REAL,
      arousal REAL,
      affect_band TEXT,

      -- Social
      num_participants INT,
      social_context TEXT,

      -- Temporal
      event_time_utc TIMESTAMP,
      local_date DATE,
      local_time TIME,

      -- ... (50+ more columns from data schema)

      created_at_utc TIMESTAMP DEFAULT NOW(),

      CONSTRAINT st_hipp_events_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id)
  );

  -- Create indexes
  CREATE INDEX idx_hipp_events_tenant_id ON st_hipp_events(tenant_id);
  CREATE INDEX idx_hipp_events_simhash ON st_hipp_events(simhash_hex);
  CREATE INDEX idx_hipp_events_event_time ON st_hipp_events(event_time_utc);
  CREATE INDEX idx_hipp_events_local_date ON st_hipp_events(local_date);

  -- Create st_embedding_queue table
  CREATE TABLE IF NOT EXISTS st_embedding_queue (
      embedding_id UUID PRIMARY KEY,
      wal_pos BIGINT NOT NULL,
      event_id UUID NOT NULL,
      text TEXT NOT NULL,
      status TEXT NOT NULL DEFAULT 'PENDING',
      attempt_count INT DEFAULT 0,
      created_at_utc TIMESTAMP DEFAULT NOW(),

      CONSTRAINT st_embedding_queue_event_id_fkey FOREIGN KEY (event_id) REFERENCES st_hipp_events(event_id)
  );

  CREATE INDEX idx_embedding_queue_status ON st_embedding_queue(status);
  ```

- [ ] **Migration Validation**:
  - Migration runs idempotently (can re-run safely)
  - Indexes created (query performance validated)
  - Foreign keys enforce referential integrity
  - Test data inserted successfully

**Kubernetes Deployment**:

- [ ] **Deployment YAML**:

  ```yaml
  # k0/deploy/p02_deployment.yaml
  apiVersion: apps/v1
  kind: Deployment
  metadata:
    name: p02-pipeline-worker
    namespace: k0-pipelines
  spec:
    replicas: 3
    selector:
      matchLabels:
        app: p02-worker
    template:
      metadata:
        labels:
          app: p02-worker
      spec:
        containers:
        - name: p02-worker
          image: family-os/k0-runtime:v1.0.0
          env:
            - name: PIPELINE_YAML_PATH
              value: /config/p02_episodic_write.pipeline.yaml
            - name: DATABASE_URL
              valueFrom:
                secretKeyRef:
                  name: postgres-credentials
                  key: url
            - name: NATS_URL
              value: nats://nats-service:4222
          resources:
            requests:
              memory: "512Mi"
              cpu: "500m"
            limits:
              memory: "1Gi"
              cpu: "1000m"
          volumeMounts:
            - name: pipeline-config
              mountPath: /config
        volumes:
          - name: pipeline-config
            configMap:
              name: p02-pipeline-config
  ```

**Configuration Management**:

- [ ] **Pipeline Config**:

  ```yaml
  # k0/deploy/p02_config.yaml

  pipeline:
    id: p02_episodic_write
    version: v1
    workers: 3

  modules:
    hippocampus.pattern_separate:
      hash_seed: 42
      novelty_threshold: 0.7

    affect.analyze:
      tier0_enabled: true
      lexicon: VADER

    # ... config for all 16 modules

  database:
    connection_pool_size: 20
    query_timeout_sec: 10

  observability:
    tracing_enabled: true
    metrics_enabled: true
    log_level: INFO
  ```

**Deployment Guide**:

- [ ] Create `docs/runbooks/p02_deployment_guide.md` with:
  - **Prerequisites**: Database migration 0024, NATS server running
  - **Deployment Steps**:
    1. Run database migration: `psql -f migrations/0024_p02_tables.sql`
    2. Validate migration: `SELECT COUNT(*) FROM st_hipp_events;`
    3. Create ConfigMap: `kubectl create configmap p02-pipeline-config --from-file=p02_episodic_write.pipeline.yaml`
    4. Apply deployment: `kubectl apply -f k0/deploy/p02_deployment.yaml`
    5. Check workers: `kubectl get pods -l app=p02-worker`
    6. Tail logs: `kubectl logs -f deployment/p02-pipeline-worker`
  - **Rollback Procedure**: Scale deployment to 0, restore database snapshot
  - **Health Checks**: Query `st_hipp_events` for recent events
  - **Monitoring**: Link to Grafana dashboard

**Master Document Validation**:

- [ ] P02 deployment status updated in Part 2.1

##### Implementation Steps

1. Write database migration SQL (60-70 columns from data schema)
2. Test migration on staging database
3. Create Kubernetes deployment YAML
4. Create ConfigMap for pipeline config
5. Write deployment guide with step-by-step instructions
6. Update master document
7. Validate deployment on staging environment

##### Estimated Effort

- **Database Migration**: 2 hours (60-70 columns + indexes)
- **Kubernetes Deployment YAML**: 1.5 hours
- **Configuration Management**: 1.5 hours (module configs)
- **Deployment Guide**: 2 hours (step-by-step procedures)
- **Staging Validation**: 1.5 hours (deploy to staging)
- **Master Doc Updates**: 30 minutes
- **Total**: 9 hours

##### Dependencies

- **Blocks**: Issue 7.3.2 (runbook creation)
- **Blocked By**: Issue 7.2.1 (observability validated)

---

#### Issue 7.3.2: Operational Runbooks & Documentation

**Priority**: 🟡 Medium (post-deployment support)
**Size**: M (6-8 hours)
**Assignee**: TBD

##### Context References

**Primary Sources**:

- **P02 Dossier**: Lines 933-983 (Workflow Step 11: Production Testing - operational docs)
- **Existing Runbooks**: `docs/runbooks/` (check for existing patterns)
- **Deployment Guide**: Created in Issue 7.3.1

##### Master Document Tracking (MANDATORY)

**Update Locations**:

1. **Part 2.1**: Update P02 documentation status
   - `Docs: ✅ Runbooks Complete`

##### Deliverables

- [ ] Create: `docs/runbooks/p02_operations.md` (operational procedures)
- [ ] Create: `docs/runbooks/p02_troubleshooting.md` (debugging guide)
- [ ] Create: `docs/runbooks/p02_maintenance.md` (routine maintenance)
- [ ] Update Master Doc Part 2.1 (documentation status)
- [ ] Runbooks peer-reviewed by ops team

##### Acceptance Criteria

**Operations Runbook** (`p02_operations.md`):

- [ ] **Daily Operations**:
  - Health check procedures (query recent events)
  - Monitoring dashboard review (what to look for)
  - Log review (common log patterns)

- [ ] **Incident Response**:
  - High latency (check slow modules, database queries)
  - High error rate (query error logs, check module failures)
  - Pipeline stalled (check worker health, NATS connectivity)
  - Database deadlock (identify conflicting transactions)

- [ ] **Scaling Procedures**:
  - When to scale workers (throughput threshold)
  - How to scale (kubectl scale deployment)
  - Database connection pool tuning

**Troubleshooting Guide** (`p02_troubleshooting.md`):

- [ ] **Common Issues**:
  - Issue 1: Events not being processed
    - Symptoms: st_hipp_events not growing
    - Diagnosis: Check worker logs, NATS connectivity
    - Resolution: Restart workers, verify NATS topics

  - Issue 2: High database write latency
    - Symptoms: M16 (writer) taking >100ms
    - Diagnosis: Check database CPU, query plans
    - Resolution: Add indexes, tune connection pool

  - Issue 3: Memory leak in worker
    - Symptoms: Worker memory growing over time
    - Diagnosis: Profile worker with py-spy
    - Resolution: Identify leaking module, fix + redeploy

  - Issue 4: Duplicate events in st_hipp_events
    - Symptoms: Same event_id appearing multiple times
    - Diagnosis: Check idempotency logic in M16
    - Resolution: Fix UnitOfWork transaction handling

- [ ] **Debugging Commands**:

  ```bash
  # Check worker health
  kubectl get pods -l app=p02-worker

  # Tail worker logs
  kubectl logs -f deployment/p02-pipeline-worker

  # Query recent events
  psql -c "SELECT event_id, created_at_utc FROM st_hipp_events ORDER BY created_at_utc DESC LIMIT 10;"

  # Check error rate
  psql -c "SELECT COUNT(*) FROM st_outbox WHERE topic = 'p02.error.v1';"

  # Profile slow module
  py-spy top --pid <worker_pid>
  ```

**Maintenance Runbook** (`p02_maintenance.md`):

- [ ] **Routine Maintenance**:
  - Weekly: Review dashboard metrics, check for anomalies
  - Monthly: Database vacuum, index maintenance
  - Quarterly: Performance baseline re-test, capacity planning

- [ ] **Database Maintenance**:
  - Vacuum st_hipp_events (reclaim space)
  - Reindex slow queries (rebuild indexes)
  - Partition old events (archive >1 year old)

- [ ] **Configuration Updates**:
  - How to update module configs (kubectl edit configmap)
  - How to update pipeline YAML (rolling deployment)
  - How to tune latency budgets (edit module contracts)

**Master Document Validation**:

- [ ] P02 documentation status updated in Part 2.1

##### Implementation Steps

1. Write operations runbook (daily ops, incident response)
2. Write troubleshooting guide (4 common issues + debugging commands)
3. Write maintenance runbook (routine tasks, database maintenance)
4. Peer review with ops team (ensure actionable)
5. Update master document

##### Estimated Effort

- **Operations Runbook**: 2 hours
- **Troubleshooting Guide**: 3 hours (4 issues + commands)
- **Maintenance Runbook**: 2 hours
- **Peer Review**: 1 hour
- **Master Doc Updates**: 30 minutes
- **Total**: 8.5 hours

##### Dependencies

- **Blocks**: Milestone 7 completion (production ready)
- **Blocked By**: Issue 7.3.1 (deployment guide exists)

---

### Milestone 7 Summary

**Total Issues**: 5 (load testing, chaos testing, observability, deployment, runbooks)
**Total Effort**: ~52 hours (6-8 days for 1 developer)
**Critical Path**: Issue 7.1.1 → 7.1.2 → 7.2.1 → 7.3.1 → 7.3.2

**Completion Criteria**:

- [ ] Load testing complete (1000 events, <150ms P95, >10 events/sec)
- [ ] Chaos testing complete (8 failure scenarios validated)
- [ ] Observability instrumented (traces, metrics, logs, alerts, dashboards)
- [ ] Deployment artifacts created (migration 0024, Kubernetes YAML, configs)
- [ ] Operational runbooks complete (operations, troubleshooting, maintenance)
- [ ] Part 8.1 shows all production test entries with ✅
- [ ] Part 2.1 shows P02 production-ready status

**Quality Gates**:

- [ ] Performance SLAs met (P95 <150ms, P99 <250ms)
- [ ] Resilience validated (all chaos tests pass)
- [ ] Observability complete (100% trace coverage)
- [ ] Deployment tested on staging (successful deployment + rollback)
- [ ] Runbooks peer-reviewed by ops team

**Production Readiness Checklist**:

- [ ] All 7 milestones complete (M1-M7)
- [ ] All tests passing (unit, integration, load, chaos)
- [ ] Performance benchmarks met
- [ ] Observability fully instrumented
- [ ] Deployment artifacts validated
- [ ] Runbooks approved by ops team
- [ ] Master document updated (all tracking sections ✅)
- [ ] Sign-off from tech lead + ops lead

**Next**: P02 ready for production deployment! 🚀

---

## Implementation Plan Summary

### Overall Timeline

**Total Duration**: 10-12 weeks (with 4-person team)
**Total Effort**: ~450-520 hours

### Milestone Breakdown

| Milestone | Duration | Effort | Team Size | Status |
|-----------|----------|--------|-----------|--------|
| M1: Contracts | 3-4 days | 35-40h | 1-2 devs | 📝 Not Started |
| M2: ADRs | 4-5 days | 40-45h | 1-2 devs | 📝 Not Started |
| M3: Pipeline YAML | 2-3 days | 14h | 1 dev | 📝 Not Started |
| M4: Implementation | 12-15 days | 170-200h | 4 devs | 📝 Not Started |
| M5: Syscalls | 4-5 days | 31h | 1 dev | 📝 Not Started |
| M6: Integration Tests | 5-7 days | 45-50h | 1-2 devs | 📝 Not Started |
| M7: Production Testing | 6-8 days | 52h | 1-2 devs | 📝 Not Started |
| **Total** | **10-12 weeks** | **450-520h** | **4 devs avg** | 📝 Planning |

### Critical Path

```
M1 (Contracts) → M2 (ADRs) → M3 (Pipeline YAML) → M4 (Implementation) → M5 (Syscalls) → M6 (Integration) → M7 (Production)
```

### Parallelization Opportunities

- **Weeks 1-2**: M1 (Contracts) + M2 (ADRs) can overlap (2 devs)
- **Weeks 3-5**: M4 (Implementation) - 17 modules in parallel (4 devs)
- **Week 6**: M5 (Syscalls) + M6 (Integration) can overlap (2 devs)
- **Week 7-8**: M7 (Production Testing) can start during M6 (2 devs)

### Key Deliverables

1. **17 Module Contracts** (YAML) - Milestone 1
2. **16 ADR Documents** - Milestone 2
3. **1 Pipeline YAML** - Milestone 3
4. **17 Module Implementations** + Tests - Milestone 4
5. **4 Syscall Implementations** - Milestone 5
6. **Integration Test Suite** (8 scenarios) - Milestone 6
7. **Production Artifacts** (migration, deployment, runbooks) - Milestone 7

### Success Metrics

- ✅ All 580 acceptance criteria met
- ✅ Performance: <150ms P95 end-to-end latency
- ✅ Throughput: >10 events/sec per worker
- ✅ Test Coverage: ≥90% (unit + integration)
- ✅ Observability: 100% trace coverage
- ✅ Resilience: All 8 chaos scenarios pass
- ✅ Documentation: All runbooks complete

### Risk Mitigation

**High-Risk Areas**:

1. **Module Performance** (M01, M02, M16 may exceed budgets)
   - Mitigation: Early performance testing, profiling, optimization
2. **Database Scalability** (M16 writer may bottleneck)
   - Mitigation: Batch writes, connection pooling, index optimization
3. **Integration Complexity** (16 modules + 8 stages = many failure points)
   - Mitigation: Comprehensive integration tests, chaos testing
4. **Syscalls Missing** (4 methods not yet implemented)
   - Mitigation: M5 dedicated to syscalls, validate with module tests

**Medium-Risk Areas**:

1. **Contract Drift** (contracts may not match implementations)
   - Mitigation: Contract compliance tests (M6)
2. **Performance Regression** (optimizations break functionality)
   - Mitigation: CI/CD performance benchmarks
3. **Deployment Complexity** (Kubernetes + database migration)
   - Mitigation: Staging environment validation, rollback procedures

### Next Steps

1. **Immediate**: Start Milestone 1 (Module Contracts)
2. **Week 1**: Complete M1, start M2 (ADRs)
3. **Week 2**: Complete M2, start M3 (Pipeline YAML)
4. **Week 3-5**: M4 (Implementation) - full team
5. **Week 6-8**: M5 (Syscalls) + M6 (Integration)
6. **Week 9-10**: M7 (Production Testing)
7. **Week 11**: Staging deployment + validation
8. **Week 12**: Production deployment 🚀

---

**Document Version**: 1.0.0
**Last Updated**: 2025-11-16
**Status**: ✅ Complete - Ready for Execution
