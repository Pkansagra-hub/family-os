# Phase 1 Implementation Plan — Fabric

**Status:** Skeleton plan. Epics/issues to be broken into granular tasks after blocker resolution.
**Date:** 2026-06-02
**Source:** `docs/whiteboard/back_tool_contract_whiteboard.md` — Phase 1 Component Designs + Workbook Phase 1

---

## 0. Blocker Audit

Before writing the implementation plan, these blockers must be resolved.

### B-001: discover_capabilities — Full Removal

**Decision:** **FULL REMOVAL from Back + Concierge. Planner redesign to use new paradigm.** No dual paths. No DeprecatedToolError trampoline.

**Subagent audit results (2026-06-02):**

**CONCIERGE LAYER — REMOVE (11 files, ~45+ references):**

| File | What | Action |
|---|---|---|
| `k1/concierge/tools/schemas_fabric.py:23-149` | `DISCOVER_CAPABILITIES_SCHEMA` ToolSchema | **Remove** from Back/Front tool surfaces |
| `k1/concierge/tools/schemas_back.py:26,295` | Re-export to Back | **Remove** re-export |
| `k1/concierge/tools/schemas_front.py:25,676,708` | Re-export to Front + execute reference | **Remove** |
| `k1/concierge/tools/implementations.py:1361-1470` | `execute_discover_capabilities()` handler | **Remove** handler + `@_register` decorator |
| `k1/concierge/tools/implementations.py:120` | `ToolContext.capability_cache` field | **Remove** |
| `k1/concierge/adapters/fabric_dispatch.py:372-379` | `FabricDispatchAdapter.discover_capabilities()` | **Remove** method |
| `k1/concierge/prompt/back_prompt.py:16+ refs` | Prompt text references | **Rewrite** — Back prompt redesigned for resolve_situation paradigm |
| `k1/concierge/prompt/sections.py:80,176,685,759` | Prompt sections | **Rewrite** |
| `k1/concierge/prompt/builder.py:1463` | Prompt builder | **Rewrite** |
| `k1/concierge/prompt/mode.py:87,129,143,162` | Mode configurations | **Rewrite** |
| `k1/concierge/react/capability_routing.py:26` | `DISCOVERY_TOOLS` constant | **Remove** |
| `k1/concierge/tools/dispatcher.py:95,658` | Back allowlist + error messages | **Remove** from allowlists |
| `k1/concierge/tools/parallelism.py:37` | Parallel-read allowlist | **Remove** |

**FABRIC LAYER — KEEP (Engine remains for Planner migration, then redesign):**

| File | What | Action |
|---|---|---|
| `k1/fabric/retrieval/retrieval_engine.py:153` | `RetrievalEngine.discover_capabilities()` — core engine | **KEEP** for Planner until redesign |
| `k1/fabric/fabric.py:1434-1461` | `FabricRetrieval.discover_capabilities()` — async wrapper | **KEEP** for Planner until redesign |
| `k1/fabric/fabric.py:1668-1677` | `Fabric` container delegate | **KEEP** |
| `k1/fabric/core/discovery_tools.py:160-230` | `DiscoverCapabilitiesHandler` — MCP handler | **KEEP** for Planner until redesign |
| `k1/contracts/tools/discover_capabilities.yaml` | YAML contract | **KEEP** for Planner until redesign |

**PLANNER LAYER — REDESIGN (Planner cannot use 2 paths):**

Subagent audit reveals Planner currently uses TWO discovery paths:
1. **SEMANTIC:** `IFabricRetrievalPort.discover_capabilities(intent, domain)` → embedding similarity search. Used in SKETCH (top_k=10) and EXPAND (top_k=5).
2. **CATALOG:** `IFabricRegistryPort.lookup(name)` → exact O(1) lookup. Used in EXPAND's `get_capability_schema()`.

Both route through `ToolCallRouter` which maps 4 abstract tool names → 3 backend ports.

**Required Planner redesign (Planner Phase 1, separate from Fabric Phase 1):**

| File | Change |
|---|---|
| `k1/planner/ports/fabric_retrieval_port.py` | `IFabricRetrievalPort` → Replace `discover_capabilities()` with `search_capabilities(query, top_k)` backed by GlobalProjectionStore FTS5. Remove embedding dependency. |
| `k1/planner/adapters/fabric_retrieval_adapter.py` | Rewrite adapter to call `GlobalProjectionStore.search_capabilities()` instead of `FabricRetrieval.discover_capabilities()`. |
| `k1/planner/services/tool_call_router.py` | Replace `discover` routing with `search_capabilities`. Remove `_fabric_retrieval` port dependency — replace with `_global_store`. |
| `k1/planner/stages/sketch_service.py` | Replace `discover_capabilities` in SKETCH_TOOL_DEFINITIONS with `search_capabilities`. Update prompt text. |
| `k1/planner/stages/expand_service.py` | Replace `discover_capabilities` in EXPAND_TOOL_DEFINITIONS with `search_capabilities`. Update `_enrich_steps()` to use capabilities from GlobalProjectionStore instead of RetrievalResult. |
| `k1/planner/stages/validate_service.py` | `_check_capability_existence()` — use `GlobalProjectionStore.capability_exists()` instead of cached ScoredCapability list. Remove semantic search fallback in `get_schema()`. |
| `k1/fabric/retrieval/retrieval_engine.py` | **Post-Planner-migration: REMOVE** `discover_capabilities()` method. `RetrievalEngine` reduces to `find_relevant_prompts()` only. |
| `k1/fabric/fabric.py` | **Post-Planner-migration: REMOVE** `FabricRetrieval.discover_capabilities()` + `Fabric` container delegate. |
| `k1/fabric/core/discovery_tools.py` | **Post-Planner-migration: REMOVE** `DiscoverCapabilitiesHandler` class. |
| `k1/contracts/tools/discover_capabilities.yaml` | **Post-Planner-migration: DELETE** file. |

**Why FTS5 replaces embedding search for Planner:**
- Planner doesn't need semantic similarity (cosine distance on embeddings). It needs keyword/domain lookup: "find calendar tools."
- FTS5 handles this at <5ms for 100K capabilities (POC-proven).
- No embedding model dependency. No cold-start. Deterministic.
- Single search path: `GlobalProjectionStore.search_capabilities(query, top_k)` — used by BOTH Planner (catalog) and SituatedResolver (situated projection).

---

### B-002: Fabric container dataclass — new fields

**Blocked by:** Need to add 8+ new fields to `Fabric` dataclass (`k1/fabric/fabric.py` line 1643).

**Current fields:**

```python
facade, retrieval, registry_api, registry, module_loader, health_checker,
event_port, event_emitter, gap_detector, context_builder
```

**New fields needed:**

```python
global_projection_store, local_projection_store, idempotency_store,
situated_resolver, policy_selector, verification_runner,
constitution_loader, prompt_pack_builder, alias_normalizer
```

**Risk:** `Fabric` is created in `FabricFactory.create_shared()` and `create_with_ports()`. Both must accept new optional params. Per-session vs shared Fabric gets different instances (e.g., `local_projection_store` is per-session, `global_projection_store` is shared). `NativeToolProvider` must be re-registered on per-session fabric.

**Resolution required:** Confirm `FabricFactory` signature changes. Decision: add all new params as optional (`= None`). Shared Fabric gets stores + resolver + constitution_loader. Per-session Fabric additionally gets `local_projection_store`. This is already designed in Component wiring sections — confirm it doesn't conflict with existing factory logic.

---

### B-003: CapabilityRegistry hot-cache vs GlobalProjectionStore

**Blocked by:** `CapabilityRegistry` (`k1/fabric/core/registry.py`) is the CURRENT source of truth — 6 in-memory indexes, no persistence. `GlobalProjectionStore` becomes the NEW persistent source of truth.

**Dual-write problem:** During migration, capabilities must be registered in BOTH the in-memory registry (for existing execution path) AND GlobalProjectionStore (for new resolution path). This is fragile.

**Resolution required:** Does `GlobalProjectionStore` REPLACE `CapabilityRegistry` as the primary store, with Registry becoming a read-through cache? Or do they coexist? The Component 1 design says "GlobalProjectionStore replaces the registry's storage layer while the registry keeps its in-memory hot cache" — confirm this is the intended migration path. If so, we need:

- `CapabilityRegistryAPI` writes through to `GlobalProjectionStore` on `register()`
- `CapabilityRegistry` loads from `GlobalProjectionStore` on startup (population)
- Registry hot cache is invalidated when store changes (or TTL-based)

---

### B-004: NativeToolProvider re-registration on per-session Fabric

**Blocked by:** `NativeToolProvider` is currently registered at S8 via `bootstrap_family_tools()` on the shared Fabric, then RE-REGISTERED at P3.1 on the per-session Fabric. New components must also be available on per-session Fabric.

**Question:** Are stores (GlobalProjectionStore, IdempotencyStore) shared or per-session? Design says:

- GlobalProjectionStore: SHARED (one instance, all sessions)
- LocalProjectionStore: PER-SESSION (one per session_id)
- IdempotencyStore: SHARED (one instance, all sessions)
- SituatedResolver: PER-SESSION (uses per-session LocalProjectionStore)

**Resolution required:** Confirm store lifecycle aligns with `service.py` S3/S8/P3 wiring. If `GlobalProjectionStore` is created before S3, it must survive S3→P3 handoff. Currently there's no mechanism to pass shared objects from Tier 1 startup to per-session creation except through the `shared_fabric` object.

---

### B-005: Family tool schema redesign scope

**Blocked by:** Step 1.7 says "Redesign family tool schemas" — upgrade `ActionSpec` → full JSON Schema, add constitutions, verifier affordances, side-effect declarations. This touches 5 adapter services (calendar, tasks, reminders, chores, shopping) and their 51 existing tests.

**Risk:** Schema redesign is additive but could break existing `NativeToolProvider` dispatch if schemas change shape. The 51 family tool tests must continue passing.

**Resolution required:** Confirm schema upgrade is additive (new fields only, no removal of existing contract fields). Constitution is a NEW file per connector, not embedded in existing schemas.

---

### B-006: Test suite impact — 113 fabric tests + 51 family tool tests

**Blocked by:** Adding 10 new components and removing `discover_capabilities` will break existing tests.

**Affected test count (estimate):**

- ~30+ tests reference `discover_capabilities` directly — will fail
- ~15+ tests use `FabricRetrieval` / `FabricDispatchAdapter` discovery methods
- ~10+ tests reference Back's tool surface including discover
- All 113 fabric tests must continue passing after Phase 1

**Resolution required:** Strategy for test migration:

- Tests that use `discover_capabilities` as part of existing flow → rewrite to use `resolve_situation`
- Tests that test `discover_capabilities` itself → remove or repurpose
- Tests that test `FabricRetrieval` → preserve for Planner path, or remove if Planner migrates
- Existing 113 fabric tests are the regression gate — cannot merge Phase 1 until they pass

---

### B-007: Planner dependency on FabricRetrieval API

**Blocked by:** Planner currently calls `FabricRetrieval.discover_capabilities()` during SKETCH and EXPAND phases. This is a legitimate cold-discovery use case (semantic search over 100K+ tools), not the execution-path discovery we're removing from Back.

**Resolution required:** Decision on Planner's discovery path:

- **Option A:** Planner uses `GlobalProjectionStore.search_capabilities()` (FTS5 full-text search, not embedding). Loses semantic similarity ranking but gains speed and simplicity. Works at 100K scale (POC-proven).
- **Option B:** Keep `FabricRetrieval` but rename to `catalog_search` and remove from Back's tool surface. Planner continues to use it. Two discovery paths coexist (Planner semantic search + Back situated resolution) but Back can never access the catalog path.
- **Option C:** Planner discovers through `resolve_situation(resolution_mode="catalog")` — same meta-tool, different mode. Clean but means the resolver handles both execution and catalog use cases.

---

## 1. Epic Structure

### Epic 1: Foundation Stores

**Goal:** GlobalProjectionStore, LocalProjectionStore, IdempotencyStore live in production.

**Dependencies:** B-003 (registry coexistence), B-005 (schema redesign)

| Issue | Description | Source | Tests |
|---|---|---|---|
| E1-I1 | Promote GlobalProjectionStore from POC → `k1/fabric/stores/` | POC `global_projection_store.py` | GAP-P1-003 |
| E1-I2 | Promote LocalProjectionStore from POC → `k1/fabric/stores/` | POC `local_projection_store.py` | GAP-P1-004 |
| E1-I3 | Promote IdempotencyStore from POC → `k1/fabric/stores/` | POC `idempotency_store.py` | GAP-P1-005 |
| E1-I4 | Wire stores into `FabricFactory.create_shared()` | B-002, B-004 | Existing fabric tests |
| E1-I5 | Populate GlobalProjectionStore at S8 from CapabilityRegistry | B-003 | GAP-P1-003 |
| E1-I6 | Wire IdempotencyStore into `CapabilityFabric._execute_impl()` Step 0 | Component 3 design | GAP-P1-005 |

---

### Epic 2: Resolution Engine

**Goal:** SituatedResolver, PolicySelector, CapabilityBinder live in production.

**Dependencies:** Epic 1 (stores), B-003 (registry), B-007 (Planner path)

| Issue | Description | Source | Tests |
|---|---|---|---|
| E2-I1 | Promote SituatedResolver from POC → `k1/fabric/resolver/` | POC `resolve_situation.py` | GAP-P1-001, GAP-P1-009 |
| E2-I2 | Implement PolicySelector → `k1/fabric/policy/selector.py` | Contract C | GAP-P1-002 |
| E2-I3 | Implement CapabilityBinder (consumes PolicySelector output) | Component 4 design | (part of GAP-P1-001) |
| E2-I4 | Wire SituatedResolver as Fabric meta-tool `resolve_situation` | Component 4 design | GAP-P1-001 |
| E2-I5 | Implement ResolveResourcesService (uses both stores) | Component 2 design | GAP-P1-004 |

---

### Epic 3: Verification + Constitution

**Goal:** VerificationPlanRunner, ConnectorConstitution, PromptPackBuilder live in production.

**Dependencies:** Epic 1 (stores), Epic 2 (resolver)

| Issue | Description | Source | Tests |
|---|---|---|---|
| E3-I1 | Implement ConstitutionSchema + ConstitutionLoader | Component 7 design | GAP-P1-008 |
| E3-I2 | Populate connector constitutions for calendar/tasks/reminders/chores/shopping at S8 | B-005 | GAP-P1-008 |
| E3-I3 | Promote VerificationPlanRunner from POC → `k1/fabric/verification/` | POC `verification_runner.py` | GAP-P1-006 |
| E3-I4 | Wire VerificationPlanRunner into `_execute_impl()` Step 7.5 | Component 6 design | GAP-P1-006 |
| E3-I5 | Implement PromptPackBuilder → `k1/fabric/prompt_pack/` | POC `prompt_injection.py` | GAP-P1-011 |

---

### Epic 4: Utility Components

**Goal:** CapabilityNameParser, ConnectorAliasNormalizer live.

**Dependencies:** Epic 1 (stores for alias normalizer)

| Issue | Description | Source | Tests |
|---|---|---|---|
| E4-I1 | Implement CapabilityNameParser → `k1/fabric/resolver/name_parser.py` | Component 9 design | GAP-P1-012 |
| E4-I2 | Implement ConnectorAliasNormalizer → `k1/fabric/stores/alias_normalizer.py` | Component 10 design | GAP-P1-013 |
| E4-I3 | Validate all 41 existing capability names against name parser grammar | B-005 | GAP-P1-012 |

---

### Epic 5: discover_capabilities Full Removal

**Goal:** Back has NO discover_capabilities tool. Back prompt redesigned for resolve_situation. No DeprecatedToolError — the tool simply doesn't exist in Back's surface.

**Decision (B-001 resolved):** Full removal. No dual paths. No trampoline handler. If the LLM doesn't know about a tool, it won't call it.

**Dependencies:** Epic 2 (resolver must be live before removing old path), B-007 (Planner redesign is SEPARATE from Fabric Phase 1)

| Issue | Description | Risk |
|---|---|---|
| E5-I1 | Remove `DISCOVER_CAPABILITIES_SCHEMA` from `schemas_fabric.py` + all re-exports | Back/Front lose the tool |
| E5-I2 | Remove `execute_discover_capabilities()` handler + `@_register` from `implementations.py` | Handler deleted, not deprecated |
| E5-I3 | Remove `ToolContext.capability_cache` field from `implementations.py` | Dead field |
| E5-I4 | Redesign Back prompt for resolve_situation paradigm (Phase 2 work, scoped here) | Back prompt is Phase 2, but stub removal is Phase 1 |
| E5-I5 | Remove discover_capabilities from Back tier allowlists in `dispatcher.py` | Tool surface shrinks |
| E5-I6 | Remove discover_capabilities from parallel-read allowlist in `parallelism.py` | Configuration cleanup |
| E5-I7 | Remove `FabricDispatchAdapter.discover_capabilities()` method | Adapter method deleted |
| E5-I8 | Remove `DISCOVERY_TOOLS` constant from `capability_routing.py` | Constant deleted |
| E5-I9 | Rewrite ~30+ fabric/concierge tests that reference discover_capabilities | B-006 |

**Fabric core KEPT for Planner until Planner redesign (separate workstream):**

| Component | Why kept | When removed |
|---|---|---|
| `RetrievalEngine.discover_capabilities()` | Planner's SKETCH/EXPAND uses it via ToolCallRouter | After Planner redesign |
| `FabricRetrieval.discover_capabilities()` | Async wrapper for Planner | After Planner redesign |
| `DiscoverCapabilitiesHandler` | MCP handler for Planner's DAG steps | After Planner redesign |
| `discover_capabilities.yaml` contract | Planner references it | After Planner redesign |
| `IFabricRetrievalPort` (Planner) | Planner's port definition | After Planner redesign |

---

### Epic 6: Fabric Integration Testing

**Goal:** Prove the full Phase 1 Fabric spine works standalone — chaos, integration, unit, E2E.

**Dependencies:** All Epics 1-5 complete. Existing 113 fabric tests must pass.

#### E6-I1: Unit Test Suite (GAP-P1-001 through GAP-P1-013)

```text
Run:
  pytest tests/k1/fabric/stores/test_global_projection_store.py -v
  pytest tests/k1/fabric/stores/test_local_projection_store.py -v
  pytest tests/k1/fabric/stores/test_idempotency_store.py -v
  pytest tests/k1/fabric/stores/test_alias_normalizer.py -v
  pytest tests/k1/fabric/resolver/test_situated_resolver.py -v
  pytest tests/k1/fabric/resolver/test_situated_resolver_negative.py -v
  pytest tests/k1/fabric/resolver/test_capability_name_parser.py -v
  pytest tests/k1/fabric/policy/test_policy_selector.py -v
  pytest tests/k1/fabric/verification/test_verification_runner.py -v
  pytest tests/k1/fabric/constitution/test_constitution_schema.py -v
  pytest tests/k1/fabric/prompt_pack/test_prompt_pack_builder.py -v
```

#### E6-I2: Integration Test Suite (new)

```text
File: tests/k1/fabric/integration/test_phase1_spine.py

Tests:
  test_store_to_resolver_roundtrip
    GlobalProjectionStore → register connector + capabilities + constitution
    → SituatedResolver.resolve(RequestFrame) → ResolutionEnvelope
    → verify verdict, bindings, PromptPack

  test_full_read_after_write_through_fabric
    Back RequestFrame → resolve_situation → invoke_capability (prereq read)
    → invoke_capability (write) → VerificationPlanRunner → submit_result

  test_policy_denies_blocked_actor
    Child actor → resolve_situation for calendar write → blocked_by_policy

  test_idempotency_prevents_duplicate_write
    Same idempotency_key twice → second call returns prior observation

  test_cross_connector_promotes_to_tier3
    Task spanning calendar + chores → promote_to_tier3 verdict

  test_stale_projection_blocks_write
    Resource freshness_state=stale → stale_projection verdict

  test_constitution_gates_enforced
    Calendar create without prerequisite list_events → can_execute_with_gate
    After prerequisite completed → can_execute
```

#### E6-I3: Chaos Testing

```text
File: tests/k1/fabric/chaos/test_phase1_chaos.py

Tests:
  test_store_crash_recovery
    Kill GlobalProjectionStore mid-write → reopen → data integrity

  test_resolver_concurrent_requests
    100 concurrent resolve_situation calls → no deadlocks, correct verdicts

  test_idempotency_store_under_contention
    50 concurrent mark_in_flight for same key → only 1 wins

  test_bulk_load_during_search
    100K capability bulk insert while FTS5 search running → no corruption

  test_verification_runner_provider_failure
    Readback capability returns error → verification fails gracefully

  test_prompt_pack_under_token_budget_pressure
    RequestFrame with many bound tools → PromptPack stays under budget
```

#### E6-I4: Regression Gate

```text
Run ALL existing fabric tests — must all pass:

  pytest tests/k1/fabric/ -v        # 113 files
  pytest tests/k1/tools/family/ -v  # 51 files
  pytest tests/bridge/connector/ -v # 48 files
  pytest tests/k1/hil/ -v           # 11 files

  Total: ~223 test files

Gate rule: 0 failures. 0 skips without documented reason.
```

#### E6-I5: Benchmark Suite

```text
File: scripts/probe_back_tool_contract_benchmark.py

Measure:
  - resolve_situation latency: P50 < 50ms, P95 < 200ms
  - GlobalProjectionStore FTS5 search: < 5ms for 100K capabilities
  - IdempotencyStore check/mark: < 2ms per operation
  - PromptPackBuilder.build(): < 20ms for 10-tool binding
  - VerificationPlanRunner.run(): < 100ms for read_after_write

Baseline: POC benchmark results from scripts/probe_back_tool_contract_benchmark.py
Must match or beat POC results.
```

#### E6-I6: Policy Adversarial Suite

```text
File: tests/k1/fabric/policy/test_policy_adversarial.py

Purpose: Prove the policy layer cannot be bypassed through spoofing,
         escalation, or boundary confusion.

Tests:
  test_privilege_escalation_via_actor_role_spoofing
    RequestFrame claims actor_role="parent" but session_id belongs to child
    → PolicySelector must cross-check actor_role against session identity
    → expect: blocked_by_policy, not can_execute

  test_band_mismatch_amber_session_red_tool
    safety_band in session = AMBER, tool constitution declares band = RED
    → expect: blocked_by_policy, reason="band_mismatch"

  test_connector_scope_creep_binding_id_crosses_connectors
    Back receives binding_id for calendar, attempts to invoke shopping tool
    using same binding_id
    → Dispatcher must validate binding_id → connector match
    → expect: CapabilityInvocationError, not silent execution

  test_policy_bypass_via_catalog_mode
    Actor tries to invoke from catalog result (allowed_next_actions=[])
    → Dispatcher must reject even if tool name is valid
    → expect: blocked, reason="catalog_mode_no_invoke"

  test_cross_person_write_via_person_ref_substitution
    Session belongs to Riley. RequestFrame.who = Jordan.
    Policy: child cannot write to another person's calendar.
    → expect: blocked_by_policy, not silently routed to Jordan's calendar

  test_stacked_denial_all_reasons_in_envelope
    Child actor + AMBER band + stale projection all true at once
    → expect: blocked_by_policy with ALL denial reasons in envelope,
      not just the first one caught (ordering must be deterministic)

  test_policy_config_injection_rejected
    ConnectorConstitution YAML contains unexpected "policy_override: true" field
    → ConstitutionLoader must reject unknown fields (strict schema validation)
    → expect: ConstitutionLoadError, system falls back to deny-by-default
```

#### E6-I7: Constitution Integrity Suite

```text
File: tests/k1/fabric/constitution/test_constitution_integrity.py

Purpose: Prove constitutions are safe under malformation, absence,
         circularity, and version mismatch. Deny-by-default on any failure.

Tests:
  test_missing_constitution_triggers_deny_not_silent_allow
    Calendar connector registered, no constitution loaded at S8
    → SituatedResolver must treat missing constitution as deny-by-default
    → expect: cannot_execute, reason="no_constitution"
    NOT: resolver falls through to can_execute (silent allow)

  test_constitution_schema_version_mismatch
    constitution.yaml has schema_version=2, loader expects version=1
    → expect: ConstitutionLoadError, explicit version mismatch message

  test_circular_prerequisite_chain_detected_at_load
    Constitution declares: list_events prereq → get_event prereq → list_events
    → ConstitutionLoader must detect cycle at load time, not at runtime
    → expect: ConstitutionLoadError("circular_prerequisite")

  test_verifier_references_nonexistent_tool
    Constitution declares verifier: tool.read.calendar.get_event_v2
    No such capability registered in GlobalProjectionStore
    → VerificationPlanRunner must surface this at plan time, not silently skip
    → expect: VerificationPlanError("verifier_not_found")

  test_constitution_declares_write_as_prerequisite_rejected
    Constitution: before create_event, run create_reminder (a write)
    → ConstitutionLoader must reject: prerequisites must be reads
    → expect: ConstitutionLoadError("prerequisite_must_be_read")

  test_conflicting_constitutions_same_connector_rejected
    Calendar connector loaded twice with different prerequisite sets
    → expect: ConstitutionLoader raises DuplicateConstitutionError,
      does NOT silently take the last one

  test_empty_constitution_all_null_fields_rejected
    File exists but all fields are null/empty
    → expect: ConstitutionLoadError, not silent allow-everything
```

#### E6-I8: Verdict Contract Suite (Property-Based)

```text
File: tests/k1/fabric/resolver/test_verdict_contract.py

Purpose: Prove verdict invariants hold across ALL verdicts, not just the
         ones tested in unit tests. Property-based: randomized inputs.

Invariant Tests (run across all 7+ verdicts):

  test_allowed_next_actions_never_nonempty_when_verdict_is_blocker
    For: blocked_by_policy, cannot_execute, missing_required_params,
         needs_disambiguation, stale_projection
    → allowed_next_actions must always be []
    Run 100 randomized RequestFrames that produce each blocker verdict
    → assert len(envelope.allowed_next_actions) == 0 always

  test_can_execute_verdict_always_has_exactly_one_allowed_action
    → assert len(envelope.allowed_next_actions) == 1
    Never 0 (that's a blocker), never 2+ (resolver must be deterministic)

  test_can_execute_with_gate_returns_prerequisite_not_write
    → assert allowed_next_actions[0].capability_name contains "list" or "get"
    → assert the write tool is NOT in allowed_next_actions

  test_every_verdict_envelope_contains_non_null_prompt_pack
    Even blockers must return a PromptPack (with recovery guidance)
    → assert envelope.prompt_pack is not None for all verdict types

  test_verdict_is_deterministic_for_identical_request_frame
    Call resolve_situation with identical RequestFrame 10x in parallel
    → all 10 envelopes must have identical verdict + allowed_next_actions
    → no flapping between verdicts under concurrent load

Transition Tests:

  test_gate_progression_with_gate_to_can_execute_after_prereq
    Complete the prerequisite. Call resolve_situation again.
    → verdict must change to can_execute (not stay at gate)
    → allowed_next_actions must now contain the write tool

  test_gate_progression_does_not_skip_verification
    After gate clears → invoke write → verification fails
    → resolve_situation called again
    → verdict must NOT be can_execute again (write failed)
    → expect: cannot_execute or missing evidence in envelope

  test_disambiguation_retry_succeeds
    First call: needs_disambiguation (two Sarahs)
    User resolves → second call with resolved person_id
    → verdict must change to can_execute or can_execute_with_gate
    → NOT needs_disambiguation again

  test_stale_projection_refresh_to_clean_verdict
    First call: stale_projection
    Refresh triggered. Second call with same RequestFrame.
    → freshness_state now fresh → verdict changes
    → NOT stale_projection on second call
```

#### E6-I9: Idempotency Contract Suite

```text
File: tests/k1/fabric/stores/test_idempotency_contract.py

Purpose: Prove semantic correctness of idempotency — not just state machine
         transitions, but that keys encode identity correctly and that replay
         returns original data.

Tests:
  test_same_key_returns_original_observation_not_new_execution
    First call: mark_in_flight(key) → execute → mark_complete(key, obs_A)
    Second call with same key → must return obs_A exactly
    → assert second_result == obs_A (not a new execution)
    → assert the underlying tool was called ONCE (mock call count)

  test_idempotency_key_structure_validation
    Keys must encode: session_id + tool_name + content_hash
    A key missing any component must be rejected at mark_in_flight
    → expect: IdempotencyKeyError("malformed_key")

  test_in_flight_key_blocks_concurrent_call
    Thread A: mark_in_flight(key) — does NOT yet mark_complete
    Thread B: simultaneously calls mark_in_flight(same key)
    → Thread B must receive: IdempotencyConflictError("already_in_flight")
    → NOT: both threads execute the tool (double-write)

  test_expiry_completed_key_past_ttl_is_re_executable
    mark_complete(key, obs, ttl=1s)
    Wait 2s. Call mark_in_flight(key) again.
    → must succeed (key expired, re-execution allowed)
    → NOT: still returns stale obs

  test_failed_execution_does_not_lock_key_forever
    mark_in_flight(key). Tool raises CapabilityError.
    Key must return to available (not locked forever)
    → subsequent call with same key must be allowed
    → expect: mark_in_flight succeeds on retry

  test_content_hash_sensitivity_different_params_different_keys
    Two calls with same tool_name but DIFFERENT params
    → must generate DIFFERENT idempotency keys
    → both execute independently (not idempotency-blocked)

  test_promote_to_tier3_verdict_bypasses_idempotency_store
    A cross-connector task escalated to Orchestrator
    Idempotency enforcement is Orchestrator's responsibility at that tier
    → IdempotencyStore must NOT be checked for promote_to_tier3 verdicts
```

#### E6-I10: Behavioral Regression — Golden Flows

```text
File: tests/k1/fabric/behavioral/test_golden_flows.py

Purpose: Lock the 8 design examples from back_execution_examples.md as
         snapshot tests. If ANY component changes the expected output, the
         test fails with a diff. These protect every future refactor.

GOLDEN_001: Simple read — Riley's calendar this week
  Expected verdict: can_execute
  Expected allowed_next_actions: [tool.read.calendar.list_events]
  Expected submit_result: accepted without verification gate
  Expected Back behavior: no prerequisite, no HIL, no verification

GOLDEN_002: Policy denial — Riley (child) moves her own dentist
  Expected verdict: blocked_by_policy
  Expected allowed_next_actions: []
  Expected recovery_hint: contains "parent" or "guardian"
  Expected submit_result: blocked (not completed)

GOLDEN_003: Disambiguation — "Aunt Sarah" → two candidates
  Expected verdict: needs_disambiguation
  Expected candidates: exactly 2 (Sarah Johnson, Sarah Williams)
  After resolution: verdict changes to can_execute_with_gate
  Expected full round-trip: HIL → re-resolve → gate → invoke → verify

GOLDEN_004: Missing time — "Schedule Riley's dentist"
  Expected verdict: missing_required_params
  Expected missing_fields: ["time_window"]
  Expected HIL trigger: ask_for_time
  After HIL response: verdict = can_execute_with_gate

GOLDEN_005: Stale projection — Jordan's calendar, 6hr old
  Expected verdict: stale_projection
  Expected reason: stale_write_candidate
  After refresh: verdict = can_execute_with_gate

GOLDEN_006: Cross-connector — Riley's birthday party
  Expected verdict: promote_to_tier3
  Expected escalation_reason: cross_connector
  Expected connectors_in_scope: {calendar, contacts, shopping}
  Expected: Back never attempts invoke — just emits BackPromotionOutcome

GOLDEN_007: Verification failure — event not found after HTTP 200
  Expected invoke result: {status: verification_failed}
  Expected: submit_result("completed") is BLOCKED
  Expected PromptPack: contains retry and partial options
  Expected: Back cannot call submit_result until retry or partial chosen

GOLDEN_008: Main dentist flow — full happy path
  Expected sequence: gate → list_events (no conflicts) →
                     create_event → verify (found) → submit_result accepted
  Expected mock call order: list_events BEFORE create_event (enforced by gate)
  Expected verification: get_event called once after create_event
```

#### E6-I11: Degraded Mode Suite

```text
File: tests/k1/fabric/degraded/test_degraded_mode.py

Purpose: Prove the system degrades gracefully under partial failure.
         The most dangerous gap — silent failures live in startup edge cases.

Tests:
  test_partial_constitution_load_missing_calendar_during_startup
    4 of 5 connectors loaded, calendar missing
    Calendar task arrives during startup window
    → resolver must return cannot_execute("no_constitution"), not crash
    → after S8 completes, same task must succeed

  test_global_projection_store_unavailable_service_still_starts
    Store fails to open at S3. Service must still start.
    Any resolve_situation call → cannot_execute("store_unavailable")
    → NOT: service fails to start entirely (that's worse)
    → health_checker must report degraded, not healthy

  test_local_projection_store_fails_mid_session
    Store initializes correctly. Then raises on get() mid-resolution.
    → resolver must surface PartialResolutionError
    → session must be marked degraded, not silently return stale data

  test_idempotency_store_unavailable_policy_encoded_explicitly
    Store is down. invoke_capability is called.
    Policy: fail open (log warning, allow execution) or fail closed (block)?
    THIS DECISION MUST BE EXPLICIT IN THE TEST.
    The test encodes the chosen policy as the expected behavior.
    Neither is wrong — the test makes it impossible to accidentally change it.

  test_verification_plan_runner_unavailable_write_already_executed
    Runner raises on run(). Write already executed.
    → CapabilityFabric must NOT call submit_result(completed)
    → must surface verification_unavailable in observation
    → Back must receive explicit signal that verification did not run

  test_prompt_pack_builder_budget_exceeded_truncates_deterministically
    Resolution generates 20 bound tools (extreme cross-connector case)
    PromptPack token budget overflows
    → Builder must truncate deterministically (priority order)
    → Must NOT silently drop high-priority bindings to fit low-priority ones
    → Truncation must be logged and surfaced in envelope

  test_constitution_loaded_but_verifier_deregistered_after_load
    Constitution loaded at S8 with verifier: get_event.
    get_event deregistered later (e.g. connector hot-swap).
    Write executes. VerificationPlanRunner tries to run get_event.
    → must surface: verifier_not_found (not KeyError crash)
```

#### E6-I12: Audit Trail and Observability Suite

```text
File: tests/k1/fabric/observability/test_audit_trail.py

Purpose: Prove every significant action emits a structured, tamper-evident
         audit event. No PII leakage. Events are verifiable end to end.

Tests:
  test_every_resolve_situation_emits_resolution_event
    Event must contain: timestamp, session_id, actor_id, person_ref,
    connector_id, verdict, policy_checks_run, resolution_latency_ms
    → assert event emitted to event_port after every resolve call
    → assert no PII in event (person names, not raw param values)

  test_policy_denial_emits_policy_denial_event
    Separate from ResolutionEvent. Must contain:
    policy_rule_id, actor_id, attempted_action, denial_reason
    → assert emitted on every blocked_by_policy verdict
    → assert NOT emitted on can_execute verdicts (noise reduction)

  test_verification_failure_emits_verification_failure_event
    Must contain: tool_name, expected_state, observed_state, mismatch_summary
    → assert emitted when VerificationPlanRunner.status == failed
    → assert event is emitted BEFORE CapabilityFabric overrides status

  test_idempotency_block_emits_idempotency_block_event
    Second call with same key must emit event with: key, original_timestamp,
    blocked_caller_session_id
    → assert emitted, not silently returned

  test_promote_to_tier3_emits_tier_escalation_event
    Must contain: connectors_in_scope, escalation_reason, originating_session
    → assert emitted before FSM routes to Orchestrator

  test_audit_events_are_tamper_evident
    Each event has a sequence_number and a hash of (prev_hash + payload)
    Mutating an event mid-stream → chain breaks
    → assert hash chain is verifiable across 100 consecutive events
    → assert out-of-order events are detected (sequence_number gap)

  test_no_audit_event_contains_raw_tool_parameters
    VerificationFailureEvent.expected_state must not include calendar event
    title (that's user PII). Allowed: field names, types, mismatch type.
    Not values.
    → assert no string from test fixture params appears in emitted event
      payloads
```

---

## 2. Milestone Sequence

```text
M-P1-0: BLOCKER RESOLUTION
  Resolve B-001 through B-007 before writing implementation tasks.
  Output: blocker resolution document with decisions.

M-P1-1: FOUNDATION STORES (Epic 1)
  GlobalProjectionStore, LocalProjectionStore, IdempotencyStore live.
  Wired into FabricFactory + service.py S3/S8/P3.
  CapabilityRegistry writes through to GlobalProjectionStore.
  Gate: GAP-P1-003, GAP-P1-004, GAP-P1-005 passing.

M-P1-2: RESOLUTION ENGINE (Epic 2)
  SituatedResolver, PolicySelector, CapabilityBinder live.
  resolve_situation registered as Fabric meta-tool.
  Gate: GAP-P1-001, GAP-P1-002, GAP-P1-009 passing.

M-P1-3: VERIFICATION + CONSTITUTION (Epic 3)
  VerificationPlanRunner, ConstitutionLoader, PromptPackBuilder live.
  Constitutions populated for 5 family connectors at S8.
  Verification wired into _execute_impl() Step 7.5.
  Gate: GAP-P1-006, GAP-P1-008, GAP-P1-011 passing.

M-P1-4: UTILITIES + DISCOVER DEPRECATION (Epic 4 + 5)
  CapabilityNameParser, ConnectorAliasNormalizer live.
  discover_capabilities removed from Back's tool surface.
  Back prompt rewritten. ~30+ tests migrated.
  Gate: GAP-P1-012, GAP-P1-013 passing. Back prompt contract tests passing.

M-P1-5: INTEGRATION + CHAOS + BEHAVIORAL + REGRESSION (Epic 6)
  Full Phase 1 spine proven. 7 new quality suites pass:
    - Policy Adversarial (E6-I6)
    - Constitution Integrity (E6-I7)
    - Verdict Contract — property-based (E6-I8)
    - Idempotency Contract — semantic (E6-I9)
    - Behavioral Regression — golden flows (E6-I10)
    - Degraded Mode (E6-I11)
    - Audit Trail + Observability (E6-I12)
  Chaos tests pass. Existing 223 test files pass.
  Benchmark matches POC results.
  Gate: GATE-P1 checklist (14 items in roadmap §0D).

M-P1-6: PHASE 1 COMPLETE
  All blockers resolved. All tests green. Fabric standalone proven.
  Ready for Phase 2 (Back ReAct loop integration).
```

---

## 3. Files To Create

```text
k1/fabric/stores/__init__.py
k1/fabric/stores/global_projection_store.py
k1/fabric/stores/local_projection_store.py
k1/fabric/stores/idempotency_store.py
k1/fabric/stores/alias_normalizer.py
k1/fabric/resolver/__init__.py
k1/fabric/resolver/situated_resolver.py
k1/fabric/resolver/name_parser.py
k1/fabric/policy/selector.py
k1/fabric/verification/__init__.py
k1/fabric/verification/runner.py
k1/fabric/constitution/__init__.py
k1/fabric/constitution/schema.py
k1/fabric/constitution/loader.py
k1/fabric/prompt_pack/__init__.py
k1/fabric/prompt_pack/builder.py
tests/k1/fabric/stores/test_global_projection_store.py
tests/k1/fabric/stores/test_local_projection_store.py
tests/k1/fabric/stores/test_idempotency_store.py
tests/k1/fabric/stores/test_alias_normalizer.py
tests/k1/fabric/resolver/test_situated_resolver.py
tests/k1/fabric/resolver/test_situated_resolver_negative.py
tests/k1/fabric/resolver/test_capability_name_parser.py
tests/k1/fabric/policy/test_policy_selector.py
tests/k1/fabric/verification/test_verification_runner.py
tests/k1/fabric/constitution/test_constitution_schema.py
tests/k1/fabric/prompt_pack/test_prompt_pack_builder.py
tests/k1/fabric/integration/test_phase1_spine.py
tests/k1/fabric/chaos/test_phase1_chaos.py
tests/k1/fabric/policy/test_policy_adversarial.py
tests/k1/fabric/constitution/test_constitution_integrity.py
tests/k1/fabric/resolver/test_verdict_contract.py
tests/k1/fabric/stores/test_idempotency_contract.py
tests/k1/fabric/behavioral/test_golden_flows.py
tests/k1/fabric/degraded/test_degraded_mode.py
tests/k1/fabric/observability/test_audit_trail.py
```

## 4. Files To Modify

```text
k1/fabric/fabric.py              — Add 8+ new fields to Fabric dataclass
k1/fabric/factory.py             — Accept new optional params in create_shared + create_with_ports
k1/fabric/core/registry.py       — Write-through to GlobalProjectionStore on register
k1/fabric/core/discovery_tools.py — Remove discover_capabilities handler (post B-007)
k1/fabric/manifest_translator.py — Validate capability names via CapabilityNameParser
k1/fabric/providers/native_tool_provider.py — Consume new schemas + constitutions
k1/concierge/tools/schemas_back.py        — Remove discover_capabilities, add resolve_situation
k1/concierge/tools/implementations.py      — Remove discover handler, add resolve_situation handler
k1/concierge/prompt/back_prompt.py         — Rewrite to remove discover references
k1/concierge/adapters/fabric_dispatch.py   — Remove discover_capabilities passthrough
k1/tools/family/calendar/service.py        — Add constitution + upgraded JSON Schema
k1/tools/family/tasks/service.py           — Add constitution + upgraded JSON Schema
k1/tools/family/reminders/service.py       — Add constitution + upgraded JSON Schema
k1/tools/family/chores/service.py          — Add constitution + upgraded JSON Schema
k1/tools/family/shopping/service.py        — Add constitution + upgraded JSON Schema
k1/kernel/service.py                       — Wire stores at S3, pass to P3
```

## 5. Files To Remove (Post B-007 Resolution)

```text
k1/contracts/tools/discover_capabilities.yaml
```

---

## 6. Open Decisions Log

| ID | Decision | Status | Resolution |
|---|---|---|---|
| B-001 | discover_capabilities: full removal or Planner preservation? | ✅ RESOLVED | **Full removal from Concierge.** No DeprecatedToolError. Back prompt redesigned around resolve_situation. Fabric core (RetrievalEngine, FabricRetrieval) kept temporarily for Planner until Planner redesign. |
| B-002 | Confirm FabricFactory signature changes for new fields | Pending | Before M-P1-1 |
| B-003 | Registry coexistence: write-through or replace? | Pending | Before M-P1-1 |
| B-004 | Store lifecycle: shared vs per-session wiring in service.py | Pending | Before M-P1-1 |
| B-005 | Family tool schema upgrade: additive only? Confirm no breaking changes | Pending | Before M-P1-3 |
| B-006 | Test migration strategy for discover_capabilities references | Pending | Before M-P1-4 |
| B-007 | Planner discovery path: FTS5, FabricRetrieval preservation, or catalog mode? | ✅ RESOLVED | **Planner redesign is separate workstream (not Fabric Phase 1).** Planner will use `GlobalProjectionStore.search_capabilities()` (FTS5) and `IFabricRegistryPort.lookup()` (exact-name). `IFabricRetrievalPort.discover_capabilities()` removed. `ToolCallRouter` routing table updated. `RetrievalEngine` reduced to prompts-only after migration. |
