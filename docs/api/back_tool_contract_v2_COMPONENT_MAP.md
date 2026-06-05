# Back Tool Contract v2 — Complete System Component Map

> Every component from connector ingestion to back tool execution, listed exhaustively.
> Generated 2026-06-04 from live codebase audit.

---

## 1. CONNECTOR INGESTION LAYER

### 1.1 Domain Catalog — `connectors/domain_catalog.py`

Defines 5 domains × 10 services each = 50 connector definitions.

| Domain | Services |
|--------|----------|
| `family` | calendar, tasks, reminders, chores, shopping, notes, contacts, habits, budgets, documents |
| `enterprise` | meetings, bug_tracker, feature_tracker, doc_repo, it_helpdesk, team_chat, tasks, code_review, oncall_schedule, analytics |
| `government` | permits, licenses, violations, meetings, records, inspections, tax_records, court_docket, dispatch, voter_registry |
| `agriculture` | field_planner, livestock, equipment_log, ag_weather, farm_inventory, soil_analyzer, irrigation, harvest_planner, grain_storage, market_prices |
| `healthcare` | ehr, appointments, prescriptions, lab_orders, messaging, imaging, billing, referrals, immunizations, vitals |

**Key functions:**

- `build_domain_corpus(domain_id) -> list[dict]` — builds all connector manifests for a domain
- `build_all_corpora() -> dict[str, list[dict]]` — all 5 domains
- `build_connector_manifest(domain_id, svc) -> dict` — single connector manifest
- `_build_capability(connector_id, resource_kind, op_type, operation, label, svc) -> dict`
- `_build_constitution(connector_id, read_op, write_op, resource_kind, is_write_capable) -> dict`

**Per-connector manifest shape:** `connector_id`, `connector_type`, `provider_type`, `label`, `description`, `version`, `provider_id`, `resource_kinds`, `actor_scope`, `constitution`, `capabilities`, `policy_declarations`, `registration_type`, `admission_verdict`

### 1.2 Family Catalog — `connectors/catalog.py`

40 family-specific connectors in 5 tiers.

| Tier | Count | Examples |
|------|-------|----------|
| NATIVE_LOCAL | 10 | calendar, tasks, reminders, notes, contacts, chores, habits, budgets, shopping, documents |
| BRIDGE_CONNECTED | 10 | google_calendar_read, google_tasks, todoist, notion, apple_reminders, slack_dm, email_send, weather, news_digest, location_context |
| IFL_READ_ONLY | 10 | school_calendar_read, sports_schedule_read, doctor_appointment_read, etc. |
| IFL_WRITE_CAPABLE | 5 | restaurant_reservation_create, appointment_book, ticket_purchase, rideshare_book, food_order |
| SYSTEM_CONNECTORS | 5 | family_broadcast, alert_send, reminder_fire, audit_log_write, notification_push |

**Key functions:**

- `all_connector_ids() -> list[str]`
- `build_all_connector_manifests() -> list[dict]`
- `build_connector_manifest(connector_id) -> dict`

### 1.3 Manifest Admission — `manifest_admission.py`

Validates and ingests connector manifests into GlobalProjectionStore.

**Dataclass:** `ManifestAdmissionRecord` (manifest_id, connector_id, admission_verdict, record_type, capabilities_admitted_count, capabilities_rejected_count, reason, admitted_at)

**Class:** `ManifestAdmissionService`

- `admit_manifest(manifest) -> ManifestAdmissionRecord`
- `admit_all_from_directory(directory) -> list[ManifestAdmissionRecord]`
- `admit_all(manifests) -> list[ManifestAdmissionRecord]`
- `_write_constitutions(manifest)` — writes each operation's constitution
- `_validate_manifest(manifest)` — 14 required fields
- `_validate_capability(cap)` — 10 required fields

**Constants:** `REQUIRED_MANIFEST_FIELDS` (14 fields), `REQUIRED_CAPABILITY_FIELDS` (10 fields)

---

## 2. STORAGE LAYER

### 2.1 GlobalProjectionStore — `stores/global_projection_store.py`

Global, shared, read-heavy SQLite store. All connectors + capabilities + graph ontology.

**Core tables (8):**

| Table | Purpose |
|-------|---------|
| `connectors` | Registered connector manifests (12 columns) |
| `capabilities` | Individual capability records (17 columns) |
| `capabilities_fts` | FTS5 virtual table for BM25 semantic search |
| `resource_kinds` | Known resource kind taxonomy |
| `connector_constitutions` | Per-connector, per-operation preconditions + verification |

**Graph tables (5):**

| Table | Purpose |
|-------|---------|
| `concept_aliases` | Natural language alias → canonical concept (alias, canonical_concept, domain, weight, generic, source) |
| `concept_resource_edges` | Canonical concept → resource_family (concept, resource_family, domain, weight) |
| `resource_connector_edges` | Resource family → connector_id (domain, resource_family, connector_id, weight) |
| `operation_aliases` | Verb alias → operation_family + effect (alias, operation_family, effect, weight, generic) |
| `capability_type_index` | Full typed index (capability_name, connector_id, domain, resource_family, operation_family, effect, side_effect_class, risk_class) |

**Query methods (12):**

- `get_connector(connector_id) -> dict | None`
- `find_capabilities(resource_kind, operation, effect, connector_id?, safety_band, record_type, include_synthetic) -> list[dict]`
- `fts_search_capabilities(query, limit, include_synthetic) -> list[dict]` — BM25 ranked
- `get_capability(capability_name) -> dict | None`
- `get_constitution(connector_id, operation) -> dict | None`
- `list_connectors(connector_type?, admission_verdict) -> list[dict]`
- `capability_count(include_synthetic?) -> int`
- `synthetic_count() -> int`
- `resolve_concept(alias, domain) -> list[dict]` — concept_aliases lookup
- `lookup_capability_by_type(domain, resource_family, operation_family, effect) -> list[dict]` — typed graph terminal lookup
- `get_concept_resource_family(concept, domain) -> list[dict]`
- `resolve_operation(alias, effect) -> list[dict]`

**Write methods (11):**

- `upsert_connector(connector)`, `upsert_capability(capability)`, `bulk_upsert_capabilities(caps, chunk_size)`, `upsert_resource_kind(rk)`, `upsert_constitution(constitution)`
- `upsert_concept_alias(alias, canonical_concept, domain, weight, generic, source)`
- `upsert_concept_resource_edge(concept, resource_family, domain, weight)`
- `upsert_resource_connector_edge(domain, resource_family, connector_id, weight)`
- `upsert_operation_alias(alias, operation_family, effect, weight, generic)`
- `upsert_capability_type_index(capability_name, connector_id, domain, resource_family, operation_family, effect, side_effect_class?, risk_class?)`

### 2.2 LocalProjectionStore — `stores/local_projection_store.py`

Per-user, per-space projection of connected resources and household members.

**Tables (4):**

| Table | Purpose |
|-------|---------|
| `connected_resources` | Resources the actor has access to (resource_id, actor_id, space_id, connector_id, resource_kind, label, aliases_json, status, actor_permission, freshness_state) |
| `household_members` | People in the space (person_id, actor_id, space_id, display_name, aliases_json, role, resource_ids_json) |
| `alias_index` | Fast alias→entity resolution (alias_lower, entity_type, entity_id, actor_id, space_id) |
| `resource_projection_snapshots` | Time-windowed projection freshness records |

**Query methods (6):**

- `resolve_alias(alias, actor_id, entity_type?) -> list[dict]`
- `fuzzy_resolve_alias(alias, actor_id, entity_type?) -> list[dict]`
- `get_connected_resource(resource_id) -> dict | None`
- `list_connected_resources(actor_id, resource_kind?, status) -> list[dict]`
- `get_household_member(person_id) -> dict | None`
- `get_fresh_snapshot(resource_id, max_age_seconds, now?) -> dict | None`

**Write methods (7):**

- `upsert_connected_resource(resource)`, `upsert_household_member(member)`, `rebuild_alias_index(actor_id, space_id)`, `upsert_projection_snapshot(snapshot)`, `mark_resource_stale(resource_id)`, `mark_resource_fresh(resource_id, observed_at?)`, `reset()`

### 2.3 IdempotencyStore — `stores/idempotency_store.py`

Prevents duplicate capability invocations.

**Dataclass:** `IdempotencyCheckResult` (state: not_seen/in_flight/succeeded/failed, prior_observation, error)

**Table:** `idempotency_records` (idempotency_key PK, state, invocation_id, observation_json, error, created_at, updated_at)

**Methods:** `check(key) -> IdempotencyCheckResult`, `mark_in_flight(key, invocation_id)`, `mark_success(key, observation)`, `mark_failed(key, error)`

### 2.4 ProviderResourceStore — `stores/provider_resource_store.py`

Actual resource records written by native providers.

**Table:** `provider_events` (event_id PK, resource_id, connector_id, title, start_at, end_at, created_by, extra_json, created_at)

**Methods:** `create_event(...) -> dict`, `get_event(event_id) -> dict | None`, `list_events(resource_id, time_min?, time_max?) -> list[dict]`

### 2.5 ScaleLoader — `stores/scale_loader.py`

Performance testing: loads 100k synthetic capability variants.

**Functions:** `load_connector_corpus(store)`, `load_synthetic_capability_variants(store, target_count=100000)`, `assert_query_performance(store)`

### 2.6 ProjectionDelta — `projection_delta.py`

Ingests projection observation results as fresh snapshots.

**Dataclass:** `ProjectionDeltaRecord` (delta_id, resource_id, snapshot_id, items_observed, observed_at, expires_at, prior_freshness_state, new_freshness_state)

**Class:** `ProjectionDeltaIngester`

- `ingest(observation, query_window?) -> ProjectionDeltaRecord`
- `is_fresh(resource_id, max_age_seconds?, now?) -> bool`

---

## 3. TASK INGESTION LAYER

### 3.1 BackTaskEnvelope — `back_task_envelope.py`

Parses incoming JSON task dispatch into validated envelope.

**Dataclass:** `BackTaskEnvelope` (envelope_id, task_id, trace_id, session_id, actor_id, space_id, tier, safety_band, task_dispatch, budget: BackTaskBudget, session_state_ref, grounding_envelope_id, temporal_anchor_id, spatial_context_id, submitted_at)

**Dataclass:** `BackTaskBudget` (max_iterations, max_fabric_calls, max_prompt_tokens)

**Exception:** `BackTaskEnvelopeError` (field_name)

**Functions:**

- `parse_back_task_envelope(payload: dict) -> BackTaskEnvelope`
- `_parse_budget(value) -> BackTaskBudget`
- `_required_str(payload, field) -> str`
- `_required_int(payload, field) -> int`
- `_optional_str(value) -> str | None`

**Constants:** `VALID_TIERS = {"LOW","MEDIUM","HIGH"}`, `VALID_SAFETY_BANDS = {"GREEN","AMBER","RED"}`

### 3.2 RequestFrameBuilder — `request_frame_builder.py`

Converts BackTaskEnvelope (or LLM extraction JSON) into structured RequestFrame.

**Dataclasses:**

| Dataclass | Fields |
|-----------|--------|
| `PersonRef` | raw, confidence, needs_resolution |
| `ResourceRef` | raw, resource_kind_hint, confidence, needs_resolution |
| `TimeWindowHint` | raw_phrase, resolved_start, resolved_end, confidence |
| `RequestFrameIntent` | intent_id, action, domain, operation_hint, resource_kind_hint, subject_hint, params |
| `RequestFrame` | request_id, task_id, trace_id, actor_id, space_id, intents, time_window_hint, person_refs, resource_refs, safety_context, target_tier, resolution_mode, created_at |

**Class:** `RequestFrameBuilder`

- `__init__(now?, actor_timezone?)`
- `build(envelope: BackTaskEnvelope) -> RequestFrame`

**Classifier constants:** `OPERATION_KEYWORDS` (5 families: create/list/read/update/delete), `RESOURCE_KIND_KEYWORDS` (7 kinds), `PERSON_KEYS`, `RESOURCE_KEYS`, `TIME_KEYS`

---

## 4. RESOLUTION PIPELINE — `resolve_situation.py`

### 4.1 Request/Response Types

**Dataclass:** `ResolveSituationRequest` — request_frame, actor_scope, safety_context, resolution_mode, target_tier, disclosure_phase, freshness_policy, prompt_budget, completed_prerequisite_bindings, previous_resolution_id

**Dataclass:** `ResolutionEnvelope` — resolution_id, request_id, request_frame, candidate_universe: ResourceUniverse, policy_bundle: PolicyBundle, binding_bundle: BindingBundle, prompt_pack: PromptPack, policy_bundle_ref, binding_bundle_ref, completeness, freshness, verdict, allowed_next_actions, allowed_capability_names, capability_name_to_binding, diagnostics, created_at, expires_at

**Dataclass:** `PromptPack` — prompt_pack_id, disclosure_phase, visible_summary, hidden_refs, created_at

### 4.2 ResolveSituationService

**Class:** `ResolveSituationService`

- `__init__(global_store, local_store, resource_resolver?, policy_selector?, capability_binder?)`
- `resolve(request) -> ResolutionEnvelope`
- `_determine_verdict(request, universe, policy_bundle, binding_bundle, diagnostics) -> str`
- `_has_ambiguous_person_reference(request) -> bool`
- `_has_stale_write_candidate(frame, universe) -> bool`
- `_allowed_next_actions(verdict, binding_bundle, completed_prereqs) -> list[dict]`
- `_build_prompt_pack(request, universe, verdict, allowed, binding_bundle) -> PromptPack`

### 4.3 13-Step Verdict Cascade

| # | Check | Verdict |
|---|-------|---------|
| 1 | Budget exhausted | `cannot_execute` |
| 2 | Idempotency duplicate_success | `cannot_execute` |
| 3 | Ambiguous person reference | `needs_disambiguation` |
| 4 | Stale projection + write intent | `stale_projection` |
| 5 | Unresolved "ambiguous" ref | `needs_disambiguation` |
| 6 | Unresolved "not_found" ref | `missing_required_params` |
| 7 | Intent too vague (no subject/params/time) | `missing_required_params` |
| 8 | Should promote to Tier 3 (6+ connectors or 3+ dep depth) | `promote_to_tier3` |
| 9 | Policy deny | `blocked_by_policy` |
| 10 | Stale role in bindings | `stale_projection` |
| 11 | Missing capability/connector/guide_only | `missing_capability` |
| 12 | Incomplete prerequisites | `can_execute_with_gate` |
| 13 | All passed | `can_execute` |

**Module helpers:** `_universe_diagnostics`, `_binding_diagnostics`, `_budget_exhausted`, `_intent_too_vague`, `_should_promote_to_tier3`, `_has_incomplete_prerequisites`, `_stable_ref`, `_action`

---

## 5. RESOURCE PROJECTION — `resource_projection.py`

### 5.1 Data Types

| Dataclass | Fields |
|-----------|--------|
| `ResourceCandidate` | resource_id, label, resource_kind, connector_id, actor_permission, freshness_state, aliases, admission_verdict |
| `PersonCandidate` | person_id, label, role, linked_resource_ids, resolved |
| `UnresolvedRef` | raw, entity_type, reason, candidates |
| `ScopeProof` | scope_proof_id, actor_id, space_id, projection_sources, omissions, exclusions, completeness |
| `ResourceUniverse` | universe_id, resource_candidates, person_candidates, unresolved, scope_proof, completeness, freshness |

### 5.2 ResolveResourcesService

**Class:** `ResolveResourcesService`

- `__init__(global_store, local_store)`
- `resolve(frame, actor_id, space_id) -> ResourceUniverse`
  - For each person_ref: resolve alias → household_member → PersonCandidate
  - For each resource_ref with needs_resolution=False: create direct ResourceCandidate (connector_id="")
  - For each resource_ref with needs_resolution=True: resolve alias → connected_resource → ResourceCandidate
  - Produce unresolved list for not_found / ambiguous refs

**Helpers:** `_source`, `_candidate_ref`, `_permission_denied`, `_completeness`, `_freshness`

---

## 6. CAPABILITY TYPE RESOLVER (Graph) — `capability_type_resolver.py`

### 6.1 Data Types

**Dataclass:** `ResolvedIntentType` — intent_id, domain, resource_family, operation_family, effect, evidence: list[str], confidence: "high"/"medium"/"low", rejected: list[dict], fallback_capabilities: list[dict]

### 6.2 CapabilityTypeResolver

**Class:** `CapabilityTypeResolver`

- `__init__(global_store, local_store)`
- `resolve(frame, universe) -> list[ResolvedIntentType]`
- `_resolve_one(intent, universe) -> ResolvedIntentType`
  - Step 1: `_resolve_operation(op_hint, intent)` → (operation_family, effect) — checks universal aliases, graph operation_aliases, derived defaults
  - Step 2: `_resolve_concept(rk, action, domain)` → list of canonical concepts — exact concept_aliases lookup + action text word extraction
  - Step 3: map concepts → resource_family via `get_concept_resource_family(concept, domain)` with fallbacks
  - Step 4: `lookup_capability_by_type(domain, resource_family, operation_family, effect)` → typed capabilities
  - Confidence: ≥4 evidence = "high", ≥2 = "medium", else "low"

**Helpers:**

- `_resolve_operation(op_hint, intent) -> (str, str)`
- `_resolve_concept(rk, action, domain) -> list[str]`
- `_extract_concept_from_action(action, domain) -> list[str]`

**Constants:** `UNIVERSAL_OPERATION_ALIASES` (30+ verbs → operation_family + effect), `WRITE_OPERATIONS`, `READ_OPERATIONS`

### 6.3 Graph Traversal Path

```
LLM verb (e.g. "prescribe")
  → operation_aliases[UNIVERSAL] or operation_aliases[graph table]
  → (operation_family="create", effect="write")

LLM noun (e.g. "prescription")
  → concept_aliases[graph table]
  → canonical_concept="prescription"
  → concept_resource_edges[graph table]
  → resource_family="prescription"
  → capability_type_index[graph table]
  → capability_name="tool.execute.healthcare.prescriptions.create"
  → capabilities[core table]
  → full capability contract JSON
```

---

## 7. POLICY SELECTOR — `policy_selector.py`

### 7.1 Data Types

| Dataclass | Fields |
|-----------|--------|
| `SafetyMappingEvidence` | evidence_id, operation, required_band, actual_band, connector_id, capability_name, mapping_result, hard_block_reason |
| `PolicyGate` | gate_id, gate_type, description, condition, action_required |
| `PolicyBundle` | policy_id, connector_ids, operations, actor_role, safety_band, roles_allowed, gates, hil_triggers, protected_read_policy, guide_refs, verifier_requirements, policy_verdict ("allow"/"deny"/"needs_hil"/"allow_with_gate"), deny_reason, safety_mapping_evidence |

### 7.2 PolicySelectorService

**Class:** `PolicySelectorService`

- `__init__(global_store)`
- `select(resource_universe, operations, actor_role, safety_band) -> PolicyBundle`
  - Default-allow: empty role list → allow all
  - Default-allow: missing connector → skip (no deny)
  - Safety band mapping: check each operation's required band vs actual band

**Helpers:** `_find_capability`, `_operation_candidates`, `_store_operation`, `_resource_kind`, `_operation_alias`

**Constants:** `SAFETY_RANK = {"GREEN":1, "AMBER":2, "RED":3}`, `WRITE_OPERATIONS`, `READ_OPERATIONS`

---

## 8. CAPABILITY BINDER — `capability_binder.py`

### 8.1 Data Types

| Dataclass | Fields |
|-----------|--------|
| `ToolSelectionCommit` | committed_tool_names, rejected_tool_names, accepted, reason — property: all_accepted |
| `CapabilityBinding` | binding_id, role (primary_read/primary_write/alternative_read/alternative_write/prerequisite_read), capability_name, resource_id, connector_id, contract_ref, input_schema_ref, output_schema_ref, effect_summary, safety_requirement, authority_verdict, verifier_ref, guide_refs, freshness_state, limitations, created_at, expires_at |
| `UnboundRole` | operation, resource_kind, reason, detail |
| `BindingBundle` | binding_bundle_id, bindings, unbound_roles, tool_name_cards, selected_schema_cards, guide_refs, verifier_links, binding_diagnostics, disclosure_phase — properties: allowed_capability_names, capability_name_to_binding |

### 8.2 CapabilityBinderService

**Class:** `CapabilityBinderService`

- `__init__(global_store, local_store)`
- `bind(resource_universe, policy_bundle, operations, actor_id, session_id, disclosure_phase, committed_tool_names?, intent_actions?, intent_types?) -> BindingBundle`
- `refresh_binding(binding_id) -> CapabilityBinding`
- `commit_tool_selection(binding_bundle, committed_tool_names) -> ToolSelectionCommit`

### 8.3 Three-Pass Capability Discovery (`_find_all_capabilities`)

| Pass | Strategy | Source |
|------|----------|--------|
| 1 | **Typed graph** (high/medium/low confidence) | `CapabilityTypeResolver.fallback_capabilities` → `capability_type_index` → `get_capability` |
| 2 | **Exact match** | `find_capabilities(resource_kind, operation, effect, connector_id)` — indexed lookup |
| 3 | **FTS5 BM25 fallback** | `fts_search_capabilities(query)` — semantic search on descriptions |

**Helpers:** `make_binding_id`, `_binding`, `_find_all_capabilities`, `_find_capability`, `_operation_candidates`, `_store_operation`, `_resource_kind`, `_dedupe_bindings`

---

## 9. INVOCATION LAYER

### 9.1 InvocationRuntime — `invocation_runtime.py`

**Dataclasses:**

- `InvocationRequest` — invocation_id, resolution_id, request_id, binding_id, capability_name, params, idempotency_key, actor_ref, safety_context, expected_effect, verifier_requested, audit_fields, created_at
- `InvocationObservation` — invocation_id, binding_id, status ("ok"/"error"), detail_status, provider_status, summary, safe_result, structured_result, error: ErrorObservation, recovery, recovery_directive, verifier_obligation, allowed_next_actions, audit_fields, latency_ms

**Class:** `InvocationRuntime`

- `__init__(native_provider, idempotency_store, global_store, local_store)`
- `invoke(request, ctx, now?) -> InvocationObservation`
  - Preflight checks: binding_not_found, stale_binding, stale_resolution, capability_params_incomplete, missing_idempotency_key, idempotency_conflict_in_flight, safety_band_mismatch, stale_projection_at_invocation, policy_gate_expired, policy_deny
  - Idempotency gate: check → mark_in_flight
  - Dispatch: `NativeProviderDispatch.dispatch(capability_name, params, write_context)`
  - Mark success/failed in idempotency store
  - Build verifier obligation

### 9.2 NativeProviderDispatch — `native_provider_dispatch.py`

**Dataclasses:**

- `WriteContext` — user_id, role, band, space_id, idempotency_key, trace_id, session_id
- `NativeProviderResult` — success, data, latency_ms, error_code, error_message

**Class:** `NativeProviderDispatch`

- `__init__(provider_store, global_store)`
- `dispatch(capability_name, params, write_context) -> NativeProviderResult`
- `_handler_for(connector_id, action_name)` — routes to read/write/event handler
- `_read_records`, `_create_record`, `_list_events`, `_get_event`, `_create_event`

**Functions:**

- `parse_capability_name(capability_name) -> (effect, connector_id, action_name)`
- `build_write_context_from_invocation(request, binding, actor_id) -> WriteContext`

### 9.3 VerificationPlanRunner — `verification_runner.py`

**Dataclasses:**

- `VerificationPlan` — verification_plan_id, resolution_id, binding_id, invocation_id, verifier_ref, verifier_method, expected_effect, expected_resource_state, readback_capability_ref, readback_params, max_staleness_ms, degraded_completion_policy, required_for_submit_status
- `VerificationObservation` — verification_id, verification_plan_id, status ("verified"/"degraded_verified"/"failed"/"inconclusive"/"skipped_by_policy"/"unavailable"), observed_effect, observed_resource_state_ref, mismatch_summary, stale_read_summary, degraded_reason, recovery_directive, proof_refs

**Class:** `VerificationPlanRunner`

- `__init__(native_provider, global_store)`
- `build_plan(binding, observation, constitution, ...) -> VerificationPlan`
- `run(plan, observation?) -> VerificationObservation`
- `_run_read_after_write`, `_run_output_schema`, `_run_none_available`

### 9.4 SubmitResultGate — `submit_result_gate.py`

**Dataclass:** `SubmitResultGateResult` — accepted, submit_result, error, recovery

**Function:** `execute_submit_result(args, loop_state, resolution_id) -> SubmitResultGateResult`

**Gate rules (ISSUE-031):**

1. completed requires verified/degraded_verified verification + completed invocation
2. completed requires prior resolution_id
3. needs_hil requires HIL request emitted
4. cannot_execute/failed/blocked require a reason

---

## 10. ERROR TAXONOMY — `error_types.py`

### 10.1 Data Types

| Dataclass | Fields |
|-----------|--------|
| `RecoveryDirective` | recovery_id, error_id, action, suggested_params_patch, required_fields, candidate_refs, hil_options, block_reason |
| `ErrorObservation` | error_id, source_component, code, severity, retryability, user_visible_summary, developer_code, context, recovery |

### 10.2 Error Codes (21)

| Code | Severity | Retryability |
|------|----------|-------------|
| `binding_not_found` | terminal | no_retry |
| `stale_binding` | recoverable | retry_with_patch |
| `stale_resolution` | recoverable | retry_with_patch |
| `capability_params_incomplete` | recoverable | retry_with_patch |
| `missing_idempotency_key` | recoverable | retry_with_patch |
| `idempotency_conflict_in_flight` | recoverable | retry_later |
| `safety_band_mismatch` | terminal | no_retry |
| `stale_projection_at_invocation` | recoverable | retry_with_patch |
| `policy_gate_expired` | recoverable | retry_with_patch |
| `policy_deny` | terminal | no_retry |
| `native_provider_error` | degraded | retry_later |
| `bridge_dispatch_error` | degraded | retry_later |
| `ifl_adapter_error` | degraded | retry_later |
| `verification_failed` | degraded | retry_later |
| `verification_inconclusive` | degraded | retry_later |
| `verification_unavailable` | degraded | retry_later |
| `budget_exhausted` | terminal | no_retry |
| `must_call_resolve_situation_first` | recoverable | retry_with_patch |
| `capability_not_in_allowed_next_actions` | recoverable | retry_with_patch |
| `prerequisite_read_not_completed` | recoverable | retry_with_patch |
| `completed_requires_verification_observation` | recoverable | retry_with_patch |

### 10.3 Recovery Actions (8)

`ask_hil`, `retry_with_params`, `refresh_projection`, `run_prerequisite_read`, `choose_from_candidates`, `block_and_submit`, `cannot_execute`, `no_recovery`

### 10.4 Factory Functions (16)

One per error code: `make_binding_not_found()`, `make_stale_binding()`, `make_stale_resolution()`, `make_capability_params_incomplete()`, `make_missing_idempotency_key()`, `make_idempotency_conflict_in_flight()`, `make_safety_band_mismatch()`, `make_stale_projection_at_invocation()`, `make_policy_gate_expired()`, `make_policy_deny()`, `make_native_provider_error()`, `make_bridge_dispatch_error()`, `make_ifl_adapter_error()`, `make_verification_failed()`, `make_verification_inconclusive()`, `make_verification_unavailable()`

---

## 11. HUMAN-IN-THE-LOOP — `hil.py`

**Dataclasses:**

- `HILRequest` — hil_request_id, task_id, resolution_id, hil_type, prompt, options, required, context_summary, expires_at
- `HILResponse` — hil_response_id, hil_request_id, selected_option_id, freeform_input, responded_at

**Class:** `HILPort`

- `__init__(auto_responses?)`
- `request(hil_request) -> HILResponse`
- `resolve(response)` — applies resolution

**Constants:** `HIL_TYPES` — disambiguation, missing_input, confirmation, risk_acknowledgement

**Functions:** `make_hil_request(...)`, `make_hil_response(...)`, `apply_disambiguation_response(local_store, actor_id, space_id, alias, resolved_person_id)`

---

## 12. PROMPT INJECTION — `prompt_injection.py`

### 12.1 Data Types

| Dataclass | Fields |
|-----------|--------|
| `ConstitutionCard` | connector_id, label, preconditions, companion_resource_roles, verification_requirement |
| `ToolNameCard` | capability_name, description, role |
| `PolicyCard` | connector_id, what_is_required, what_triggers_hil, what_is_denied |
| `GuideCard` | guide_id, title, content, relevance |
| `SchemaCard` | capability_name, binding_id, input_schema, required_fields, optional_fields |
| `RedactionEvidence` | redaction_id, prompt_hash, fields_redacted, fields_verified_absent, prompt_visible_leak_count, verdict |
| `PromptPack` | prompt_pack_id, react_state, target_tier, disclosure_phase, source_refs, source_versions, candidate_summary, connector_constitution_cards, tool_name_cards, policy_cards, guide_cards, selected_schema_cards, decision_surface, uncertainty_markers, omission_summary, allowed_tool_calls, forbidden_tool_calls, allowed_next_actions, hil_options, redaction_summary, expires_at |

### 12.2 PromptPackBuilder

**Class:** `PromptPackBuilder`

- `__init__(global_store)`
- `build(resolution_envelope, disclosure_phase, prompt_budget_tokens, committed_tool_names?) -> PromptPack`

### 12.3 Disclosure Phases (5)

| Phase | What's Visible |
|-------|---------------|
| `loop_start` | Nothing (initial state) |
| `connector_summary` | Candidates + constitution cards + policy cards + guide cards |
| `tool_name_selection` | Tool name cards (no schemas) |
| `schema_binding` | Full schemas for committed tools |
| `execution` | Everything + decision surface |

**Constants:** `PHASE_ALLOWED_FIELDS` (5 phases with field-level gating)

---

## 13. LLM TOOLS (ReAct Loop Interface)

### 13.1 resolve_situation_tool.py

**Schema:** `RESOLVE_SITUATION_TOOL_SCHEMA` — function definition with parameters: resolution_mode, target_tier, disclosure_phase, freshness_policy, prompt_budget, completed_prerequisite_bindings, previous_resolution_id, committed_tool_names

**Function:** `execute_resolve_situation(args, ctx: ToolContext) -> ToolResult`

### 13.2 invoke_capability_tool.py

**Schema:** `INVOKE_CAPABILITY_TOOL_SCHEMA` — parameters: resolution_id, request_id, capability_name, binding_id, params, idempotency_key

**Function:** `execute_invoke_capability(args, ctx: ToolContext) -> ToolResult`

**Class:** `LocalProjectionReadRuntime` — `invoke(request, ctx) -> InvocationObservation`

### 13.3 submit_result_tool.py / submit_result_gate.py

**Schema:** `SUBMIT_RESULT_TOOL_SCHEMA` — result_type: completed/partial/needs_hil/cannot_execute/failed/blocked

**Function:** `execute_submit_result(args, ctx or loop_state, resolution_id?) -> ToolResult or SubmitResultGateResult`

---

## 14. BACK REACT LOOP — `back_react_loop_poc.py`

### 14.1 Data Types

| Dataclass | Fields |
|-----------|--------|
| `ReactLoopState` (mutable) | iteration, request_frame, last_resolution_id, prerequisite_reads_completed, completed_prerequisite_bindings, allowed_capability_names, capability_name_to_binding, invocations_completed, verification_observations, tool_call_log, prompt_injection_queue, last_gate_error, model_ids_used, submit_result_called, hil_request_emitted, final_result |
| `ReactLoopResult` | status, result, error, evidence, iterations, model_id, llm_mock_used, audit_records, loop_trace_summary |

### 14.2 Loop Flow

```
back_react_loop_poc(envelope, model_client, resolver, invocation_runtime,
                    prompt_pack_builder, verification_runner, local_store,
                    global_store, proof_writer?)
  │
  ├── While iteration < budget.max_iterations:
  │     │
  │     ├── Build system prompt (back_prompt_poc)
  │     ├── Inject prompt packs from queue
  │     ├── LLM call (model_client.chat)
  │     ├── Parse tool calls from response
  │     ├── For each tool call:
  │     │     ├── resolve_situation → ResolveSituationService.resolve()
  │     │     │   → ResolutionEnvelope → PromptPackBuilder.build()
  │     │     │   → render_prompt_pack() → enqueue for next injection
  │     │     ├── invoke_capability → InvocationRuntime.invoke()
  │     │     │   → preflight → idempotency → dispatch → observation
  │     │     │   → build verification plan → run verification
  │     │     └── submit_result → SubmitResultGateResult
  │     │           → gate checks → mark submit_result_called
  │     ├── Late iteration: nudge if no submit_result
  │     └── If submit_result_called OR budget exhausted: break
  │
  └── Return ReactLoopResult
```

**Key functions:**

- `back_react_loop_poc(envelope, model_client, resolver, invocation_runtime, prompt_pack_builder, verification_runner, local_store, global_store, proof_writer?, ...) -> ReactLoopResult`
- `dispatch_tool_call(call, state, ctx) -> ToolResult`
- `tool_result_to_message(result) -> dict`

---

## 15. LLM CLIENT — `model_client.py`

### 15.1 Protocol

**Protocol:** `ModelClient`

- `async chat(messages, tools, tool_choice, temperature, max_tokens) -> ModelResponse`
- `model_id: str`
- `is_mock: bool`

### 15.2 Response Types

**Dataclass:** `ModelResponse` — model_id, content, tool_calls: list[ToolCall], finish_reason, usage, raw_provider

**Dataclass:** `ToolCall` — id, name, args: dict

### 15.3 Provider Implementations

| Class | Provider |
|-------|----------|
| `OpenAIModelClient` | OpenAI API |
| `AnthropicModelClient` | Anthropic API |
| `GeminiModelClient` | Vertex AI Gemini (with flash model pool fallback) |

**Factory:** `create_model_client_from_env(env_path?) -> ModelClient`

---

## 16. BACK SYSTEM PROMPT — `back_prompt_poc.py`

**Function:** `build_back_prompt_poc(envelope, session_snapshot, grounding_block) -> str`

**Template content:**

- Role definition: "You are Back, the FamilyOS AI agent..."
- 9-step "What You Must Do"
- Mandatory closure protocol
- 9 "What You Must Never Do" prohibitions

---

## 17. TOOL CONTEXT — `tool_context.py`

**Dataclass:** `ToolResult` — status, data, error, recovery

**Class:** `ToolContext` (mutable state bag shared across ReAct loop)

- `request_frame_store`, `resolution_store`, `resolver`, `prompt_pack_builder`, `local_store`, `global_store`, `invocation_runtime`, `verification_runner`, `prompt_injection_queue`, `completed_prerequisite_bindings: set`, `allowed_capability_names: set`, `capability_name_to_binding: dict`, `last_resolution_id`, `prompt_budget`, `audit_records`, `verification_observations`, `invocations_completed`, `submit_result_called`, `final_result`

**Protocol:** `InvocationRuntimeProtocol` — `invoke(request, ctx) -> Any`

---

## 18. PROOF & AUDIT — `proof.py`

**Dataclass:** `ProofWriteObservation` — accepted, path, rejected_fields, redaction_summary

**Class:** `ProofRecordWriter`

- `__init__(output_dir)`
- `write(record) -> ProofWriteObservation`
- `write_or_raise(record)`, `write_failure(reason)`

**Functions:**

- `utc_now_iso() -> str`
- `copy_json(obj) -> Any`
- `make_trace_id(prefix) -> str`
- `proof_record_template(...) -> dict`
- `redaction_check(record) -> dict` — detects 8 secret markers

---

## 19. SCENARIO CORPUS — `scenarios/`

### 19.1 corpus.py

100 scenarios across 16 categories for resolver testing.

**Function:** `build_scenario_corpus() -> list[Scenario]` (exactly 100)
**Categories:** unambiguous_person, ambiguous_person, implicit_actor, concrete_time, relative_time, ambiguous_time, calendar, task_reminder, contact, note, multi_connector, calendar_reminder, missing_param, conflict, stale, budget_and_idempotency

### 19.2 schema.py

Validates scenario corpus schema.

**Constants:** `REQUIRED_SCENARIO_FIELDS` (10 fields), `NEGATIVE_ASSERTION_TYPES` (8 types)

### 19.3 store.py

**Class:** `ScenarioStore`

- `list_scenarios() -> list[dict]`
- `get(scenario_id) -> dict`
- `index_by_expected_verdict() -> dict[str, list[str]]`

---

## 20. FIXTURES — `fixtures/household_fixture.py`

**Class:** `HouseholdFixtureLoader`

- `load_standard(reset=True) -> dict` — 3 persons + 40 connected resources
- `load_ambiguous_riley(reset=True) -> dict` — 2 persons both aliased "Riley"

---

## 21. BENCHMARK SCRIPTS

### 21.1 probe_back_llm_frame_benchmark_v3.py

LLM-as-Judge frame extraction benchmark. 50 scenarios × 5 domains.

**Dataclasses:** `DomainContext`, `FrameScenario`

**Architecture:** Phase 1 (LLM generate) → Phase 2 (LLM judge with rubric)

### 21.2 probe_back_resolver_benchmark.py

Full Tier 2 Spine benchmark: Extract → Build RequestFrame → Resolve → Verdict.

**Functions:**

- `build_request_frame(scenario, ctx, extraction_output) -> RequestFrame`
- `register_domain_connectors(global_store, domain_id) -> int`
- `resolve_frame(global_store, local_store, request_frame) -> ResolutionEnvelope`
- `_seed_global_graph(global_store)` — seeds universal concept + operation aliases
- `_populate_graph_edges(global_store, manifest)` — seeds all 5 graph tables per connector
- `ground_truth_tools(scenario) -> list[str]` — expected capability names per scenario
- `compute_hops_analysis(envelope) -> dict` — Tier 2 vs Tier 3 hop counts
- `_print_extraction_trace(scenario_id, raw_llm_json, parsed, frame)` — debug trace
- `run_scenario_with_resolver(client, scenario, ctx, context_block, global_store, local_store) -> ResolverScenarioResult`

**Dataclass:** `ResolverScenarioResult` (25 fields including 3-layer tool scoring: candidate_recall, commit_accuracy, execution_safety)

---

## 22. M8 E2E GATE — `e2e_scenario_gate.py`, `resolution_executor.py`, `model_matrix_runner.py`

### 22.1 resolution_executor.py

**Dataclass:** `ResolutionExecutorResult` — execution_id, scenario_id, passed, model_id, expected_submit_status, actual_submit_status, expected_resolution_verdict, actual_resolution_verdict, negative_assertions, llm_mock_used, loop_trace, loop_trace_summary, final_result

**Class:** `ResolutionExecutor`

- `__init__(model_client, resolver, invocation_runtime, verification_runner, hil_port, proof_writer, global_store, local_store)`
- `fork_with(...) -> ResolutionExecutor`
- `async execute(scenario, actor_config?) -> ResolutionExecutorResult`

### 22.2 e2e_scenario_gate.py

**Dataclass:** `E2ERunReport` — model_id, total_scenarios, passed, failed, skipped, failures, all_pass, scenario_results

**Class:** `E2EScenarioGate`

- `__init__(executor, scenario_corpus, model_clients, run_root, scenario_delay_seconds)`
- `async run_all(model_id, scenario_filter?) -> E2ERunReport`

### 22.3 model_matrix_runner.py

**Dataclass:** `ModelMatrixReport` — results: list[ModelMatrixEntry], recommendation

**Class:** `ModelMatrixRunner`

- `__init__(gate, proof_writer?)`
- `async run_matrix(model_ids, scenario_filter?, precomputed_reports?) -> ModelMatrixReport`

### 22.4 shadow_comparison.py

**Dataclass:** `ShadowComparisonRecord` — seam_id, component, scenarios_run, new_path_pass, old_path_pass, equivalence_rate, improvement_areas, regression_risks, recommendation

---

## 23. CAPABILITY NAMING CONVENTION

**Pattern:** `tool.{effect_type}.{domain}.{connector}.{action}`

| Component | Values |
|-----------|--------|
| effect_type | `read` or `execute` |
| domain | family, enterprise, government, agriculture, healthcare |
| connector | calendar, tasks, reminders, meetings, bug_tracker, permits, livestock, ehr, prescriptions, etc. |
| action | list, search, create, update, delete, send, fire, cancel |

**Examples:**

- `tool.read.family.calendar.list` — Read calendar events
- `tool.execute.family.calendar.create` — Create calendar event
- `tool.execute.healthcare.prescriptions.create` — Create prescription
- `tool.read.enterprise.it_helpdesk.list` — List IT tickets
- `tool.execute.agriculture.livestock.create` — Create livestock record

**Parser:** `parse_capability_name(name) -> (effect, connector_id, action_name)`

---

## 24. COMPLETE END-TO-END FLOW

```
1. User utterance → BackTaskEnvelope (back_task_envelope.py)
2. BackTaskEnvelope → RequestFrame (request_frame_builder.py)
3. RequestFrame → ResourceUniverse (resource_projection.py)
4. RequestFrame + ResourceUniverse → list[ResolvedIntentType] (capability_type_resolver.py)
5. ResourceUniverse + operations → PolicyBundle (policy_selector.py)
6. ResourceUniverse + PolicyBundle + intent_types → BindingBundle (capability_binder.py)
7. RequestFrame + ResourceUniverse + PolicyBundle + BindingBundle → ResolutionEnvelope (resolve_situation.py)
8. ResolutionEnvelope → PromptPack (prompt_injection.py)
9. PromptPack → injected into LLM system prompt (back_react_loop_poc.py)
10. LLM calls invoke_capability → InvocationRuntime.invoke() (invocation_runtime.py)
11. InvocationRuntime → NativeProviderDispatch.dispatch() → ProviderResourceStore (native_provider_dispatch.py)
12. Post-write: VerificationPlanRunner.run() (verification_runner.py)
13. LLM calls submit_result → SubmitResultGate (submit_result_gate.py)
14. Loop ends → ReactLoopResult (back_react_loop_poc.py)
```

---

## 25. FILE INDEX

| # | File | Purpose |
|---|------|---------|
| 1 | `back_task_envelope.py` | Parse incoming task JSON |
| 2 | `request_frame_builder.py` | Build structured RequestFrame |
| 3 | `resolve_situation.py` | Core orchestration + 13-step verdict cascade |
| 4 | `resource_projection.py` | Resolve people/resources → ResourceUniverse |
| 5 | `policy_selector.py` | Policy evaluation → PolicyBundle |
| 6 | `capability_binder.py` | 3-pass capability discovery → BindingBundle |
| 7 | `capability_type_resolver.py` | Graph-based typed concept→capability resolution |
| 8 | `prompt_injection.py` | Build disclosure-gated PromptPack |
| 9 | `resolve_situation_tool.py` | LLM-facing resolve_situation tool |
| 10 | `invoke_capability_tool.py` | LLM-facing invoke_capability tool |
| 11 | `submit_result_tool.py` | LLM-facing submit_result tool |
| 12 | `submit_result_gate.py` | Authority gate for submit_result |
| 13 | `invocation_runtime.py` | Preflight → idempotency → dispatch → verification |
| 14 | `native_provider_dispatch.py` | Route to ProviderResourceStore handlers |
| 15 | `verification_runner.py` | Read-after-write verification |
| 16 | `error_types.py` | 21 error codes + 8 recovery actions + 16 factories |
| 17 | `model_client.py` | LLM provider abstraction (OpenAI/Anthropic/Gemini) |
| 18 | `proof.py` | Proof records + redaction checking |
| 19 | `tool_context.py` | Shared ReAct loop mutable state |
| 20 | `projection_delta.py` | Ingest projection observations |
| 21 | `hil.py` | Human-in-the-loop requests/responses |
| 22 | `manifest_admission.py` | Validate + ingest connector manifests |
| 23 | `back_prompt_poc.py` | Build Back system prompt |
| 24 | `back_react_loop_poc.py` | M5 ReAct loop orchestrator |
| 25 | `resolution_executor.py` | M8 scenario-driven executor |
| 26 | `e2e_scenario_gate.py` | M8 full corpus gate |
| 27 | `model_matrix_runner.py` | M8 multi-model comparison |
| 28 | `shadow_comparison.py` | M8 shadow comparison records |
| 29 | `stores/global_projection_store.py` | 13 SQL tables + FTS5 + graph ontology |
| 30 | `stores/local_projection_store.py` | 4 SQL tables (per-user projection) |
| 31 | `stores/idempotency_store.py` | Idempotency key storage |
| 32 | `stores/provider_resource_store.py` | Native provider event storage |
| 33 | `stores/scale_loader.py` | 100k synthetic capability loader |
| 34 | `connectors/catalog.py` | 40 family connectors (5 tiers) |
| 35 | `connectors/domain_catalog.py` | 50 connectors × 5 domains |
| 36 | `scenarios/corpus.py` | 100 test scenarios |
| 37 | `scenarios/schema.py` | Scenario validation |
| 38 | `scenarios/store.py` | ScenarioStore |
| 39 | `fixtures/household_fixture.py` | Standard + ambiguous test fixtures |
| 40 | `scripts/probe_back_llm_frame_benchmark_v3.py` | LLM extraction benchmark |
| 41 | `scripts/probe_back_resolver_benchmark.py` | Full resolver benchmark |

---

**Total: 41 files, 13 SQL tables, 5 graph ontology tables, 9 verdict outcomes, 21 error codes, 8 recovery actions, 5 disclosure phases, 50 benchmark scenarios**
