# Activity Profile And Tool Prompt Injection Plan

> Branch: `feature/back-execution-profiles`
> Date: 2026-05-16
> Scope: Fabric, Concierge, Planner, Orchestrator, KernelService, `k1/tools/family`, MCP, WASM, prompt contracts, and targeted tests.

## Goal

Introduce a cross-kernel activity profile system so every tool family can declare LLM-facing operating guidance and prompt-template metadata, and the runtime can inject the right guidance at the right boundary.

## Current Implementation Slice

Implemented on this branch:

- M1 complete: `CapabilityContract` now round-trips `prompt_template`, `activity_profile`, `tool_instructions`, and `prompt_variables_schema`.
- M1 complete: YAML tool contract schema/parser accepts the new prompt/profile metadata; MCP and WASM validation coverage exists, and `k1/contracts/tools/find_prompts.yaml` is the current MCP representative with profile metadata.
- M1 complete: family `ActionSpec` and `ToolDefinition` can declare prompt/profile metadata, and `manifest_translator.py` propagates it into Fabric contracts.
- M2 complete: production prompt contracts now live under `k1/contracts/prompts`, prompt text lives under `k1/prompts/activities`, and `PromptSystemProdAdapter` loads external `template_file` markdown into `PromptTemplate.template`.
- M2 complete: prompt contract schema supports canonical `template_file` production contracts plus inline `template` compatibility for tests/transitional fixtures.
- M3 complete: `CapabilityRequest.context_override` now reaches `ContextBuilder`, selected prompts compile with request > contract > `tool_instructions` precedence, and MCP/WASM/native/agent provider paths receive prompt/profile metadata through reserved channels.
- M4 corrected complete: Concierge Back loads profile definitions from prompt contracts, selects/reuses only explicit profile metadata or exact structured domain metadata, and renders a bounded execution profile block.
- M4 complete: `build_back_prompt()` accepts `execution_profile_block` and injects it before Step 1 orientation.
- M4 complete: `back_handler()` and `back_resume_handler()` select/reuse profile metadata for initial execution and HITL resume.
- M4 complete: `TaskDispatch` round-trips optional `execution_profiles` metadata.

Recent milestone status:

- M5 complete: Planner preserves only exact discovery/inventory-backed prompt names, clears unverified template names, and carries validated profile metadata into Orchestrator/Fabric context.
- M6 complete: Back direct invoke/batch now runs a metadata-only bind-before-execute path for active Back tasks, degrades guessed/non-exact candidates before Fabric dispatch, and attaches prompt/profile context to `CapabilityRequest` without mutating business params.
- M7 complete: KernelService verifies the production prompt store at shared/session Fabric wiring, exposes template count diagnostics, and proves family calendar prompt/profile metadata survives shared-registry session Fabric discovery.
- M8 complete: Initial family profiles are attached to calendar/tasks/reminders definitions, and representative MCP/WASM contracts declare generic prompt/profile metadata.
- M9 complete: Focused rollout matrix, Back profile-selection observability, and real-component Back handler profile wiring coverage are in place.
- Remaining: no open milestone in this plan; future profile expansion stays review-driven per domain.

## Plan Readiness After Closure Pass

| Milestone | Ready | Closure note |
| --- | --- | --- |
| M0 Branch + Vocabulary | Yes | Vocabulary is frozen and the branch target is explicit. |
| M1 Tool Metadata | Yes | `prompt_variables_schema` is defined below as a JSON Schema for compile variables, not runtime values. |
| M2 Prompt Store | Yes | Canonical decision is `template_file` plus external markdown prompt text; inline `template` remains compatibility-only. |
| M3 Fabric Plumbing | Yes | Implemented via existing `ContextBuilder`, provider metadata helpers, and reserved `__metadata__` / `WriteContext.extras` channels. |
| M4 Concierge Back | Yes | MVP profile render/injection path is implemented and tested; selection is metadata-driven, not a Back-local cue router. |
| M5 Planner/Orchestrator | Yes | Prompt binding validation now preserves exact registry/discovery-backed names or clears unverified names; no Planner replacement inference. |
| M6 MEDIUM Binding | Yes | Binder interface, result states, direct Back wiring, and prompt/profile forwarding are implemented and tested. |
| M7 KernelService | Yes | Runtime prompt-store verification and shared/session family metadata visibility are implemented and tested. |
| M8 Initial Profiles | Yes | Calendar/tasks/reminders family metadata plus MCP/WASM generic provider profiles are implemented and tested. |
| M9 Tests + Rollout | Yes | Focused matrix passed with real component wiring and no full kernel/Fabric suite. |

## Documentation Freshness Gate

Every epic in this plan has a required documentation sync before it can be marked complete. The sync is part of the epic acceptance criteria, not optional cleanup after implementation.

Rule for every epic:

1. Update the component docs for every component whose public contract, wiring, state, runtime flow, or diagram changed.
2. Update docs in the same PR/branch slice as the code change.
3. If the component has no doc surface yet, create the missing doc files instead of leaving the plan as the only source of truth.
4. Add a short "Documentation updated" note to the epic completion evidence listing exact files changed.
5. Do not close the epic if code and docs disagree.

Doc file meaning:

- `CONTRACT.md`: public dataclasses, request/result payloads, schema fields, validation rules, invariants, and compatibility promises.
- `WIRING.md`: construction path, dependency injection, provider/port wiring, startup/session placement, and feature flags.
- `STATE.md`: current runtime state, implemented vs pending status, known gaps, rollout flags, and operational caveats.
- `ARCHITECTURE.md`: ownership boundaries, control/data flow, component responsibilities, and cross-component interactions.
- `*.mmd`: Mermaid diagrams showing the current flow. Update these when requests, providers, runtime path, or ownership arrows change.
- `README.md` or developer guides: update only when a developer or adapter author needs new instructions.

Affected component doc matrix:

| Component | Required doc surface for this feature |
| --- | --- |
| Concierge | `k1/concierge/CONTRACT.md`, `k1/concierge/WIRING.md`, `k1/concierge/STATE.md`, `k1/concierge/ARCHITECTURE.md`, `k1/concierge/concierge_unified.mmd` |
| Fabric | `k1/fabric/CONTRACT.md`, `k1/fabric/WIRING.md`, `k1/fabric/STATE.md`, `k1/fabric/ARCHITECTURE.md`, `k1/fabric/fabric.mmd`, `k1/fabric/fabric_new.mmd` |
| Planner | `k1/planner/CONTRACT.md`, `k1/planner/WIRING.md`, `k1/planner/STATE.md`, `k1/planner/ARCHITECTURE.md`, `k1/planner/planner.mmd`, `k1/planner/planner_v2.mmd` |
| Orchestrator | `k1/orchestrator/CONTRACT.md`, `k1/orchestrator/WIRING.md`, `k1/orchestrator/STATE.md`, `k1/orchestrator/ARCHITECTURE.md`, `k1/orchestrator/orchestrator.mmd` |
| KernelService | `k1/kernel/CONTRACT.md`, `k1/kernel/WIRING.md`, `k1/kernel/STATE.md`; create `k1/kernel/ARCHITECTURE.md` only if this feature changes kernel ownership boundaries beyond wiring/state |
| Family tools | Create `k1/tools/family/CONTRACT.md`, `k1/tools/family/WIRING.md`, `k1/tools/family/STATE.md`, `k1/tools/family/ARCHITECTURE.md`, and `k1/tools/family/family_tools.mmd` when M1/M8 metadata work touches family definitions |
| MCP tools | Add or update `k1/tools/mcp_servers/README.md`; create component docs only when MCP prompt/profile forwarding becomes production behavior |
| WASM tools | Add or update `k1/tools/wasm_modules/README.md`; create component docs only when WASM prompt/profile forwarding becomes production behavior |
| Prompt contracts | `k1/fabric/CONTRACT.md`, `k1/fabric/WIRING.md`, `k1/fabric/STATE.md`, prompt inventory tests, and any new prompt directory README if prompt authoring rules become non-obvious |

Epic documentation sync map:

| Epic | Required doc update before epic close |
| --- | --- |
| M0.E1 / M0.E2 | Update this plan and `docs/whiteboard/conversation_continuity.md` with branch/vocabulary decisions. |
| M1.E1 | Fabric contract docs and Fabric mmd diagrams must show new `CapabilityContract` prompt/profile fields. |
| M1.E2 | Family tool docs must be created/updated; Fabric translator docs must explain metadata propagation. |
| M1.E3 | Fabric contract docs must show MCP/WASM YAML prompt/profile metadata support. |
| M2.E1 / M2.E2 | Fabric WIRING/STATE/CONTRACT and mmd prompt-store nodes must show `k1/contracts/prompts` plus `template_file` -> `k1/prompts/...` resolution. |
| M3.E1 / M3.E2 | Fabric WIRING/ARCHITECTURE/CONTRACT/mmd must show `context_override`, prompt variable precedence, provider metadata keys, and native/MCP/WASM behavior. |
| M4.E1 / M4.E2 / M4.E3 | Concierge CONTRACT/WIRING/STATE/ARCHITECTURE/mmd must show Back profile selection, prompt injection, resume reuse, and `TaskDispatch.execution_profiles`. |
| M5.E1 | Planner CONTRACT/WIRING/ARCHITECTURE/mmd must show prompt binding validation and invalid-template clearing states. |
| M5.E2 | Orchestrator CONTRACT/WIRING/ARCHITECTURE/mmd must show `PlanStep.activity_profile` and `CapabilityRequest.context_override["activity_profile"]`. |
| M6.E1 | Concierge and Orchestrator docs/mmd must show binder states and MEDIUM degradation flow; Fabric docs must mention strict exact-name validation remains unchanged. |
| M7.E1 / M7.E2 | Kernel WIRING/STATE and Fabric/Concierge STATE docs must show prompt-store verification and shared/session metadata visibility. |
| M8.E1 / M8.E2 | Family tool docs, Fabric prompt inventory docs, and provider READMEs must show concrete calendar/tasks/reminders/MCP/WASM profile assets. |
| M9.E1 / M9.E2 | All touched component STATE docs must include final implemented/pending status and rollout evidence. |

This is not only a Concierge prompt change. The feature spans:

- tool definitions and contracts, so family/MCP/WASM/native tools can declare activity profiles and prompt templates;
- Fabric context building, so prompt templates, context overrides, and prompt variables flow into execution;
- provider behavior, so MCP/WASM/native/agent providers can receive or ignore prompt context deliberately;
- Concierge Back execution, so Back gets compact activity-specific guidance before it discovers/invokes capabilities;
- Planner/Orchestrator, so HIGH-tier DAG steps use validated prompt/profile bindings;
- KernelService wiring, so prompt stores, shared Fabric, session Fabric, family tools, and Concierge receive the same contract surface.

## Design Principle

Profiles are procedure, not authority.

A profile can tell Back or an agent how to work with a domain, but it must not grant tools, guess capability names, authorize side effects, bypass HIL, or replace schema inspection. Fabric contracts, policy, HIL, and provider schemas remain authoritative.

## Key Runtime Split

```text
Back Execution Profile
  - selected per TaskDispatch or per intent
  - rendered into Back system prompt
  - guides discovery/schema/HIL/invoke/verify behavior

Tool Prompt Template
  - declared by tool/contract/prompt registry
  - compiled by Fabric ContextBuilder
  - used by LLM-backed providers and agent execution
  - optionally passed as metadata to MCP/WASM/native providers

Fabric Meta-Agent
  - registered specialist capability/agent
  - own contract, tool scope, prompt template, lifecycle
  - used for recurring or complex specialist work
```

## Current Evidence From Code Sweep

- `TaskIntent.domain` already exists in `k1/concierge/task/intent.py`.
- Front `dispatch_task` already accepts per-intent `domain` in `k1/concierge/tools/schemas_front.py`.
- `TaskDispatch` now carries optional `execution_profiles`; `reference_context` and `context_snapshot` remain unchanged.
- `back_handler()` and `back_resume_handler()` both call `build_back_prompt()` before entering `react_loop()`.
- `build_back_prompt()` is a simple template-substitution path and now accepts `execution_profile_block`.
- `discover_capabilities()` already returns contract domains, names, scores, and schema snippets.
- `invoke_capability()` already checks required params and returns structured recovery/HIL when params are incomplete.
- Family tools are production-wired through `k1/tools/family/*`, `manifest_translator.py`, and `NativeToolProvider`.
- Family `ActionSpec` and `ToolDefinition` now have prompt/profile metadata fields, and `manifest_translator.py` propagates them into Fabric contracts.
- MCP/WASM YAML contracts can now declare prompt/profile fields through the tool contract schema, but their providers still need explicit forwarding behavior.
- `CapabilityRequest.prompt_template` and `CapabilityRequest.context_override` already exist. The gap is that `CapabilityFabric._build_context()` currently forwards only `request.prompt_template`; it does not yet forward `request.context_override` or prompt variables.
- `CapabilityContract` now has `prompt_template`, `activity_profile`, `tool_instructions`, and `prompt_variables_schema`; `AgentContract` still has its existing `prompt_template`.
- `PromptSystemProdAdapter` is wired to `k1/contracts/prompts`; that directory now exists and external `template_file` markdown loads into `PromptTemplate.template`.
- Planner HIGH-tier flow can discover prompts and Orchestrator passes `PlanStep.prompt_template` into `CapabilityRequest`, but template names are not validated.
- MEDIUM/Back direct dispatch does not select or pass prompt templates.

## Milestone M0 - Branch, Inventory, And Contract Freeze

Purpose: Put the work on a feature branch and freeze the target contracts before behavior changes.

### M0 Execution Evidence - 2026-05-16

- Branch verification: `git branch --show-current` returned `feature/back-execution-profiles`; the local branch exists and tracks `origin/feature/back-execution-profiles`.
- Dirty-worktree baseline before M0 doc edits: `data/bridge_outbox.db-shm`, `data/bridge_outbox.db-wal`, and `data/k1/sessionstate.db-wal` were already modified. No reset, checkout, or revert was performed.
- Architecture sweep preservation: `docs/whiteboard/conversation_continuity.md` keeps the Back Execution Profiles section and now matches the current `TaskDispatch.execution_profiles` implementation reality.
- Vocabulary freeze: use `activity_profile`, `execution_profile`, `tool_prompt_template`, `prompt_template`, and `tool_instructions`; do not introduce legacy labels without an alias/deprecation plan.
- Documentation updated: `docs/plans/k1/activity_profile_prompt_injection_plan.md` and `docs/whiteboard/conversation_continuity.md`.

### Epic M0.E1 - Branch And Baseline Evidence

#### Issue M0.E1.I1 - Create feature branch from current development state

Files: none.

Implementation directive:

- Branch from `currentdevelopment` without reverting dirty working-tree changes.
- Branch name: `feature/back-execution-profiles`.
- Record dirty-worktree reality in final implementation notes.

Acceptance:

- `git branch --show-current` returns `feature/back-execution-profiles`.

#### Issue M0.E1.I2 - Preserve architecture sweep notes

Files:

- `docs/whiteboard/conversation_continuity.md`
- `docs/plans/k1/activity_profile_prompt_injection_plan.md`

Implementation directive:

- Keep the Back Execution Profiles whiteboard section.
- Keep this milestone plan as the implementation tracker.

Acceptance:

- The plan references Fabric, Concierge, `k1/tools/family`, MCP, WASM, Planner, Orchestrator, and KernelService.

### Epic M0.E2 - Contract Names And Vocabulary

#### Issue M0.E2.I1 - Freeze vocabulary

Implementation directive:

Use these terms consistently:

- `activity_profile`: domain/tool operating guidance selected by capability/domain evidence.
- `execution_profile`: the selected profile attached to a task or plan step.
- `tool_prompt_template`: prompt template declared by a capability/tool contract.
- `prompt_template`: existing Fabric request field for a prompt template name.
- `tool_instructions`: inline non-template instructions declared directly on a capability.

Acceptance:

- No new code introduces competing names like `persona_pack`, `activity_pack`, or `domain_prompt` without an alias plan.

## Milestone M1 - Tool And Contract Metadata

Purpose: Let every tool family declare profile/template metadata in a schema-valid, discoverable way.

### Epic M1.E1 - Fabric Contract Surface

#### M1 Execution Evidence - 2026-05-16

- Code reality: `CapabilityContract`, tool-contract schema/parser, family `ActionSpec` / `ToolDefinition`, and `manifest_translator.py` already carried the M1 fields before this pass.
- Added focused coverage in `tests/k1/fabric/test_contract_validator.py`, `tests/k1/fabric/test_tool_schema_validation.py`, `tests/k1/tools/family/test_definition.py`, `tests/k1/fabric/test_manifest_translator.py`, and `tests/k1/fabric/providers/test_native_tool_provider_path.py`.
- Existing focused coverage remains in `tests/k1/fabric/test_capability_contract_prompt_metadata.py`.
- Updated `k1/contracts/tools/find_prompts.yaml` as the real MCP representative contract carrying `activity_profile`, `tool_instructions`, and `prompt_variables_schema`.
- WASM has no production representative YAML contract in `k1/contracts/` yet; M1 coverage validates WASM prompt/profile metadata through schema tests without adding a dead production contract.
- Documentation updated: `k1/fabric/CONTRACT.md`, `k1/fabric/WIRING.md`, `k1/fabric/STATE.md`, `k1/fabric/ARCHITECTURE.md`, `k1/fabric/fabric.mmd`, `k1/fabric/fabric_new.mmd`, `k1/tools/family/CONTRACT.md`, `k1/tools/family/WIRING.md`, `k1/tools/family/STATE.md`, `k1/tools/family/ARCHITECTURE.md`, and `k1/tools/family/family_tools.mmd`.
- Validation run: `pytest tests/k1/fabric/test_contract_validator.py tests/k1/fabric/test_tool_schema_validation.py tests/k1/tools/family/test_definition.py tests/k1/fabric/test_manifest_translator.py tests/k1/fabric/providers/test_native_tool_provider_path.py tests/k1/fabric/test_capability_contract_prompt_metadata.py -v` passed with 224 tests.

#### Issue M1.E1.I1 - Add profile/template fields to CapabilityContract

Files:

- `k1/fabric/types.py`
- `tests/k1/fabric/test_contract_validator.py`
- `tests/k1/fabric/test_tool_schema_validation.py`

Implementation directive:

Add optional fields to `CapabilityContract`:

```python
prompt_template: str | None
activity_profile: str | None
tool_instructions: str | None
prompt_variables_schema: dict[str, Any] | None
```

`prompt_variables_schema` is a JSON Schema object describing variables that may be passed to the selected prompt template. It is not the variable value map. Runtime values come from schema property defaults, `request.params`, and `request.context_override["prompt_variables"]` during M3 ContextBuilder work. The schema is used for documentation, prompt inventory checks, and default compile values only; it never mutates business `params`.

Update `to_dict()` / `from_dict()` round trips.

Acceptance:

- Existing contracts without these fields still parse.
- A contract with these fields round-trips without loss.
- The fields do not alter provider selection by themselves.
- `prompt_variables_schema` never changes request params; it only validates/declares the compile-variable surface.

Run:

```bash
pytest tests/k1/fabric/test_contract_validator.py tests/k1/fabric/test_tool_schema_validation.py -v
```

#### Issue M1.E1.I2 - Extend tool contract JSON schema

Files:

- `k1/contracts/schemas/tool_contract.schema.json`
- contract parser tests under `tests/k1/fabric/`

Implementation directive:

Add optional schema properties:

- `prompt_template`
- `activity_profile`
- `tool_instructions`
- `prompt_variables_schema` as a JSON Schema object or null

Acceptance:

- Schema accepts these fields.
- Unknown unrelated fields remain rejected if the schema currently rejects them.
- Contracts with `prompt_variables_schema` but no `prompt_template` are valid because inline `tool_instructions` may still use documented variables later.

### Epic M1.E2 - Family Tool Metadata

#### Issue M1.E2.I1 - Extend family ActionSpec and ToolDefinition

Files:

- `k1/tools/family/definition.py`
- `tests/k1/tools/family/test_definition.py`
- `tests/k1/fabric/test_manifest_translator.py`

Implementation directive:

Add optional fields:

```python
ActionSpec.prompt_template: str | None
ActionSpec.activity_profile: str | None
ActionSpec.tool_instructions: str | None
ActionSpec.social_act: str | None
ActionSpec.side_effects: list[dict[str, Any]]
ToolDefinition.activity_profile: str | None
ToolDefinition.domain_tags: list[str]
```

Acceptance:

- Calendar/tasks/reminders/chores definitions still instantiate.
- Defaults are empty/None and backward-compatible.

#### Issue M1.E2.I2 - Propagate family metadata through manifest translator

Files:

- `k1/fabric/manifest_translator.py`
- `tests/k1/fabric/test_manifest_translator.py`
- `tests/k1/fabric/providers/test_native_tool_provider_path.py`

Implementation directive:

- Copy action/profile/template fields into `CapabilityContract`.
- Preserve `llm.examples` by appending them to `tool_instructions` when an action has no explicit `tool_instructions`; do not invent a second examples metadata field in this milestone.
- Fold `ToolDefinition.domain_tags` into contract domains.
- Propagate `social_act` and `side_effects` for policy/conscience/HIL consumers.

Acceptance:

- Discovery results can expose profile/template metadata through contract schema snippets.
- Existing native tool provider routing is unchanged.

### Epic M1.E3 - MCP/WASM Contract Metadata

#### Issue M1.E3.I1 - Add prompt/profile fields to MCP/WASM YAML contracts

Files:

- `k1/contracts/schemas/tool_contract.schema.json`
- representative MCP contracts under `k1/contracts/`; WASM coverage uses schema fixtures until a real production WASM contract exists
- `tests/k1/fabric/test_tool_schema_validation.py`

Implementation directive:

- Make MCP/WASM tool contracts able to declare `prompt_template`, `activity_profile`, and `tool_instructions`.
- Do not require these fields.

Acceptance:

- MCP/WASM contracts with and without profile metadata validate; do not add a dead production WASM YAML only to satisfy the plan.

## Milestone M2 - Prompt Store And Template Loading

Purpose: Make prompt templates real production assets, not test-only stubs.

### M2 Execution Evidence - 2026-05-16

- Extended `PromptSystemProdAdapter` instead of adding a parallel prompt system.
- `template_file` now resolves from repo root first, then relative to the prompt-contract YAML directory, and reads the referenced markdown at load time.
- Inline `template` remains supported for tests/backward compatibility and is marked through `PromptTemplate.metadata["template_source"]`.
- Updated `prompt_contract.schema.json` to accept either `template_file` or inline `template`, while production inventory tests require external `template_file` contracts.
- Added production prompt contracts and markdown text for `calendar_activity_v1`, `tasks_activity_v1`, `reminders_activity_v1`, and `system_of_record_generic_v1`.
- Documentation updated: `k1/fabric/CONTRACT.md`, `k1/fabric/WIRING.md`, `k1/fabric/STATE.md`, `k1/fabric/ARCHITECTURE.md`, `k1/fabric/fabric.mmd`, and `k1/fabric/fabric_new.mmd`.
- Validation run: `pytest tests/k1/fabric/test_adapters_prod_510_512.py tests/k1/fabric/test_prompt_system_inventory.py -v` passed.
- Additional prompt schema/parser regression: `pytest tests/k1/fabric/test_contract_validator.py::TestValidContractsPasses::test_valid_prompt_contract tests/k1/fabric/test_contract_parsers.py::TestParseContractFromFile::test_parse_prompt_contract tests/k1/fabric/test_contract_parsers.py::TestParseContractBody::test_parse_prompt_body -v` passed.

### Epic M2.E1 - Prompt Contract Store

#### Issue M2.E1.I1 - Create production prompt directory

Files:

- `k1/contracts/prompts/`
- `k1/prompts/` or inline template YAMLs
- `tests/k1/fabric/test_prompt_system_inventory.py` (new)

Implementation directive:

Use `template_file` as the canonical production pattern. Prompt contract YAML lives in `k1/contracts/prompts/*.yaml`; prompt text lives in `k1/prompts/activities/*.md` or a more specific `k1/prompts/<domain>/` directory. Inline `template:` remains supported only for tests, transitional fixtures, and emergency compatibility.

Production prompt contract convention:

```yaml
prompt_contract:
  name: calendar_activity_v1
  version: 1.0.0
  domain: [calendar, family]
  description: Calendar activity execution guidance
  variables: []
  template_file: k1/prompts/activities/calendar_activity_v1.md
  max_tokens: 900
  output_format: TEXT
  compatible_tools:
    - tool.read.calendar.list_events
    - tool.execute.calendar.create_event
```

Acceptance:

- `PromptSystemProdAdapter("k1/contracts/prompts")` loads at least one template without warning.
- Inventory test asserts known template names exist.
- Production prompt YAMLs use `template_file`; any inline production prompt requires a comment explaining why it is temporary.

#### Issue M2.E1.I2 - Reconcile PromptContract schema and PromptSystemProdAdapter

Files:

- `k1/contracts/schemas/prompt_contract.schema.json`
- `k1/fabric/adapters/prompt_system_prod.py`
- `tests/k1/fabric/test_adapters_prod_510_512.py`

Implementation directive:

- If YAML has `template_file`, resolve relative paths from repo root first, then relative to the YAML file's directory as a fallback, and read the target text file.
- If YAML has inline `template`, support it for tests/backward compatibility and log/debug-mark the source as inline.
- Validate variables are preserved.

Acceptance:

- Existing adapter tests still pass.
- A schema-compliant `template_file` prompt loads into `PromptTemplate.template`.

### Epic M2.E2 - Initial Activity Templates

#### Issue M2.E2.I1 - Add first activity prompt templates

Files:

- `k1/contracts/prompts/calendar_activity_v1.yaml`
- `k1/contracts/prompts/tasks_activity_v1.yaml`
- `k1/contracts/prompts/reminders_activity_v1.yaml`
- `k1/prompts/activities/*.md`

Implementation directive:

Add compact templates for:

- calendar operations;
- task operations;
- reminder operations;
- generic system-of-record operations.

Acceptance:

- Templates are loadable by `PromptSystemProdAdapter`.
- Templates do not contain hardcoded guessed capability names as authority.

## Milestone M3 - Fabric Prompt/Profile Plumbing

Purpose: Make Fabric carry prompt/profile metadata correctly across all provider types.

### M3 Execution Evidence - 2026-05-16

- Extended `ContextBuilder.build()` with `context_override` and preserved overrides under `ExecutionContext.session_sections["context_override"]`.
- Implemented prompt priority: request `prompt_template` -> contract `prompt_template` -> `tool_instructions` inline fallback -> no prompt.
- Audit hardening: `context_override["prompt_template"]` is preserved only when selected from request/contract metadata and cannot become an unvalidated prompt selector; structured `profile_selection` is not serialized as `__activity_profile__`.
- Implemented prompt variable precedence: `prompt_variables_schema` property defaults -> request `params` -> `context_override["prompt_variables"]`.
- Forwarded `CapabilityRequest.context_override` from `CapabilityFabric._build_context()` and kept `CapabilityRequest.params` business-only.
- Added reserved provider metadata helpers in `base_provider.py`; MCP and WASM carry metadata under `__metadata__`, while native family tools expose it through `WriteContext.extras["fabric_prompt_metadata"]`.
- Updated `AgentFactory._spawn()` so agent context compilation sees the selected contract prompt template.
- Added focused coverage in `tests/k1/fabric/test_context_builder.py`, `tests/k1/fabric/test_capability_contract_prompt_metadata.py`, `tests/k1/fabric/test_providers_331_332.py`, `tests/k1/fabric/test_providers_333_334.py`, `tests/k1/fabric/providers/test_native_tool_provider_path.py`, and `tests/k1/fabric/test_policy_context_agent.py`.
- Documentation updated: `k1/fabric/CONTRACT.md`, `WIRING.md`, `STATE.md`, `ARCHITECTURE.md`, `fabric.mmd`, and `fabric_new.mmd` now show context override, prompt priority, and provider metadata flow.
- Validation run: focused M1-M4 changed-file regression set passed (`559 passed`).

### Epic M3.E1 - ContextBuilder Input Flow

#### Issue M3.E1.I1 - Forward existing context_override and prompt_variables

Files:

- `k1/fabric/fabric.py`
- `k1/fabric/core/context_builder.py`
- `k1/fabric/types.py`
- `tests/k1/fabric/test_context_builder.py`

Implementation directive:

- Keep `CapabilityRequest.context_override` as the request-level extension point; the field already exists in `k1/fabric/types.py` and round-trips through `to_dict()` / `from_dict()`.
- Extend the `IContextBuilder` protocol and `ContextBuilder.build()` with `context_override: dict[str, Any] | None = None`.
- Pass `request.context_override` from `CapabilityFabric._build_context()`.
- Merge normal context with a reserved `context_override` section in `ExecutionContext.session_sections`, rather than mutating authoritative SessionState sections in place.
- Compile prompt variables from this precedence order:
  1. contract defaults or empty map;
  2. `request.params`;
  3. `request.context_override["prompt_variables"]`.

Reserved `context_override` keys:

```python
{
    "activity_profile": str | None,
    "execution_profiles": list[dict[str, Any]],
    "prompt_variables": dict[str, Any],
    "tools_granted": list[str],
    "profile_selection": dict[str, Any],
}
```

Unknown keys must be preserved under the `context_override` section for observability, but must not alter SessionState or tool authorization.

Acceptance:

- Existing ContextBuilder tests pass.
- A request-level override appears in `ExecutionContext`.
- Prompt variables can render from request params.
- `request.context_override["prompt_variables"]` overrides same-named request params only for prompt compilation, not provider `params`.
- Unknown override keys are preserved for diagnostics and ignored by policy unless explicitly supported.

#### Issue M3.E1.I2 - Contract default prompt resolution

Files:

- `k1/fabric/core/context_builder.py`
- `tests/k1/fabric/test_context_builder.py`

Implementation directive:

Prompt resolution priority:

1. `CapabilityRequest.prompt_template`
2. `CapabilityContract.prompt_template`
3. `CapabilityContract.tool_instructions` as inline prompt fallback
4. no prompt

`CapabilityContract.prompt_variables_schema` contributes compile-variable defaults when schema properties declare `default`. Full JSON Schema validation of the runtime variable map is intentionally not added in M3 because the current contracts do not mark prompts as required and the existing prompt system already degrades gracefully on missing templates.

Acceptance:

- Request-level template overrides contract default.
- Contract `tool_instructions` becomes `ExecutionContext.prompt` only when no template exists.
- Missing optional prompt templates do not fail native/MCP/WASM tool execution.
- Missing agent prompt templates continue through the current graceful-degradation path until a prompt-required contract flag exists.

### Epic M3.E2 - Provider Consumption

#### Issue M3.E2.I1 - Thread prompts through AgentProvider

Files:

- `k1/fabric/providers/agent_provider.py`
- `tests/k1/fabric/test_agent_*.py`

Implementation directive:

- Ensure per-request `prompt_template` can override `AgentContract.prompt_template`.
- Avoid naive prompt+params concatenation where a structured compile path exists.

Acceptance:

- Agent execution sees the compiled prompt from request or contract.

#### Issue M3.E2.I2 - Make MCP/WASM prompt behavior explicit

Files:

- `k1/fabric/providers/mcp_provider.py`
- `k1/fabric/providers/wasm_provider.py`
- `tests/k1/fabric/providers/test_mcp_provider.py`
- `tests/k1/fabric/providers/test_wasm_provider.py`

Implementation directive:

- If `ExecutionContext.prompt` is present, pass it as provider metadata using a reserved key such as `__system_instructions__` or `__activity_profile__`.
- If a provider ignores it by design, log/debug-record that it was ignored.
- Reserved provider metadata keys are:
  - `__system_instructions__`: compiled prompt text.
  - `__activity_profile__`: profile id or selection summary.
  - `__prompt_template__`: template name used to compile the prompt.
- MCP request arguments may carry these under a reserved `__metadata__` object if direct argument injection would collide with tool schemas.
- WASM params may carry these under a reserved `__metadata__` object; sandbox code can ignore the object safely.

Acceptance:

- Tests prove context prompt reaches MCP/WASM request metadata.
- Existing provider behavior remains backward-compatible.

#### Issue M3.E2.I3 - NativeToolProvider carries profile context deliberately

Files:

- `k1/fabric/providers/native_tool_provider.py`
- `k1/tools/family/base.py`
- `tests/k1/fabric/providers/test_native_tool_provider_path.py`

Implementation directive:

- Native family services must not receive or depend on prompt text for correctness.
- Native provider may attach `activity_profile` and `prompt_template` to execution records/audit metadata only.
- Do not add prompt text to family tool params because adapter schemas should remain business-object schemas.

Acceptance:

- Native tools work without profiles.
- Profile metadata can be observed for audit/debug when present.
- No family service test needs `context.prompt` to pass.

## Milestone M4 - Concierge Back Execution Profiles

Purpose: Give Back compact domain-specific procedure before capability discovery/invocation.

### M4 Execution Evidence - 2026-05-16

- Code reality: `k1/concierge/prompt/back_profiles.py` owns `BackExecutionProfile`, `SelectedBackExecutionProfile`, `BackProfileSelection`, prompt-contract-backed profile registry accessors, metadata-driven selection, and bounded rendering.
- Profile definitions are loaded from `k1/contracts/prompts/*.yaml` via `activity_profile`, `domain`, `name`, `description`, and `template_file` guidance in `k1/prompts/activities/*.md`; Back no longer owns hardcoded domain cue tables, param cue tables, capability-prefix tables, or action/reference text scoring.
- Selection accepts existing `task.execution_profiles`, explicit `activity_profile` / `execution_profile` / `profile_id` metadata, and exact structured intent `domain` compatibility. Otherwise it falls back to `system_of_record.generic.v1` with `discovery_required` so binder/discovery remains responsible for capability/domain binding.
- `build_back_prompt()` accepts `execution_profile_block` and injects it before Step 1 orientation without changing empty-block behavior.
- `back_handler()` selects profile guidance before prompt construction, stores selected metadata on the task payload for suspension/resume continuity, and `back_resume_handler()` reuses existing `original_task.execution_profiles` when present.
- `TaskDispatch.execution_profiles` is optional payload metadata and round-trips through `to_dict()` / `from_dict()` without emitting the key when absent.
- Added handler-level coverage in `tests/k1/concierge/test_back_handler_profile_wiring.py`, plus selector and dispatch metadata regressions in `tests/k1/concierge/prompt/test_back_profiles.py` and `tests/k1/concierge/tools/test_task_dispatch_execution_profiles.py`.
- Documentation updated: `k1/concierge/CONTRACT.md`, `k1/concierge/WIRING.md`, `k1/concierge/STATE.md`, `k1/concierge/ARCHITECTURE.md`, and `k1/concierge/concierge_unified.mmd`.
- Validation run: `pytest tests/k1/concierge/prompt/test_back_profiles.py tests/k1/concierge/prompt/test_back_prompt_profile_injection.py tests/k1/concierge/tools/test_task_dispatch_execution_profiles.py tests/k1/concierge/test_back_handler_profile_wiring.py tests/k1/fabric/test_prompt_system_inventory.py -v` passed with 21 tests.

### Epic M4.E1 - Back Profile Registry And Selector

#### Issue M4.E1.I1 - Add BackExecutionProfile registry

Files:

- `k1/concierge/prompt/back_profiles.py` (new)
- `tests/k1/concierge/prompt/test_back_profiles.py` (new)

Implementation directive:

Implement:

- `BackExecutionProfile`
- `SelectedBackExecutionProfile`
- `BackProfileSelection`
- prompt-contract-backed profile registry loaded from `k1/contracts/prompts/*.yaml` using `activity_profile` and `template_file` guidance.
- conservative metadata-driven selection using existing `execution_profiles`, explicit `activity_profile` / `execution_profile` metadata, and exact structured domain compatibility only.
- no Back-local hardcoded cue tables, action text scoring, param-name scoring, reference-context text scoring, or capability-prefix routing.

Acceptance:

- Known prompt contracts load `calendar.v1`, `tasks.v1`, `reminders.v1`, and `system_of_record.generic.v1` profile guidance.
- Explicit `activity_profile` / `execution_profile` metadata selects the matching prompt-backed profile.
- Exact structured domain metadata can select a matching prompt-backed profile as compatibility.
- Free-text action cues, param names, and reference context do not select profiles.
- Ambiguous or unbacked domains fall back to `system_of_record.generic.v1` with discovery required.

Run:

```bash
pytest tests/k1/concierge/prompt/test_back_profiles.py -v
```

#### Issue M4.E1.I2 - Render compact profile blocks

Files:

- `k1/concierge/prompt/back_profiles.py`
- `tests/k1/concierge/prompt/test_back_profiles.py`

Implementation directive:

- Render only selected profile summaries.
- Cap rendered block size.
- Include override rule: registry schemas and tool recovery contracts override profiles.

Acceptance:

- Rendered block stays under the configured character limit.
- Block never grants tools or names a guessed capability as authority.

### Epic M4.E2 - Back Prompt Injection

#### Issue M4.E2.I1 - Add execution_profile_block to build_back_prompt

Files:

- `k1/concierge/prompt/back_prompt.py`
- `tests/k1/concierge/prompt/test_back_prompt_capability_names.py`
- `tests/k1/concierge/prompt/test_back_prompt_profile_injection.py` (new)

Implementation directive:

- Add `execution_profile_block: str = ""` param.
- Insert block after generic ReAct protocol and before tool usage rules.
- Keep empty block behavior unchanged.

Acceptance:

- Existing Back prompt tests still pass.
- New test proves block placement and empty behavior.

#### Issue M4.E2.I2 - Wire selector into back_handler and back_resume_handler

Files:

- `k1/concierge/actors/back.py`
- `tests/k1/concierge/test_back_handler_profile_wiring.py` (new)

Implementation directive:

- Compute selection from task before prompt construction.
- Pass rendered block to `build_back_prompt()`.
- On resume, reuse original task selection or recompute from structured `original_task` metadata.

Acceptance:

- Initial Back execution receives selected profile block.
- HITL resume receives the same profile guidance.

### Epic M4.E3 - TaskDispatch Profile Metadata

#### Issue M4.E3.I1 - Add execution_profiles to TaskDispatch

Files:

- `k1/concierge/task/dispatch.py`
- `k1/concierge/tools/implementations.py`
- `tests/k1/concierge/tools/test_task_dispatch_execution_profiles.py` (new)

Implementation directive:

- Add optional `execution_profiles: list[dict[str, Any]]` to `TaskDispatch`.
- Preserve it through `to_dict()` / `from_dict()`.
- MVP may compute in Back only; later dispatch can precompute and carry it.

Acceptance:

- Round-trip preserves profile metadata.
- Existing dispatch tests still pass.

## Milestone M5 - Planner And Orchestrator Profile Binding

Purpose: Make HIGH-tier plans use validated prompt/profile bindings, not hallucinated strings.

### M5 Execution Evidence - 2026-05-17

- Planner EXPAND prompt binding now accepts only exact `prompt_template` names returned by `find_prompts` or supplied through injected prompt inventory.
- Unverified prompt names are cleared and logged; EXPAND does not infer substitutes from domains, capability-name text, prompt scores, or compatible prompt metadata.
- `PlanStep.activity_profile` round-trips through Orchestrator types and is populated from capability-contract metadata or exact validated prompt descriptors only.
- `StepRunner._build_request()` forwards `PlanStep.activity_profile` through `CapabilityRequest.context_override["activity_profile"]` while preserving existing `tools_granted` behavior.
- Documentation updated: `docs/plans/k1/activity_profile_prompt_injection_plan.md`, `k1/planner/CONTRACT.md`, `k1/planner/WIRING.md`, `k1/planner/STATE.md`, `k1/planner/ARCHITECTURE.md`, `k1/planner/planner.mmd`, `k1/planner/planner_v2.mmd`, `k1/orchestrator/CONTRACT.md`, `k1/orchestrator/WIRING.md`, `k1/orchestrator/STATE.md`, `k1/orchestrator/ARCHITECTURE.md`, and `k1/orchestrator/orchestrator.mmd`.
- Validation run: `pytest tests/k1/planner/test_expand_prompt_binding_m5.py tests/k1/planner/test_planner_expand_3_2.py tests/k1/orchestrator/test_plan_step_profile_binding_m5.py tests/k1/orchestrator/test_step_runner.py -v` passed with 161 tests.

### Epic M5.E1 - Planner Prompt Binding Validation

#### Issue M5.E1.I1 - Validate find_prompts output against PlanStep.prompt_template

Files:

- `k1/planner/stages/expand_service.py`
- `tests/k1/planner/*` or focused new test

Implementation directive:

- Track prompt names returned by `find_prompts`.
- In `_enrich_steps()`, if LLM sets `prompt_template`, verify it exists in discovered prompt names or prompt registry.
- If valid, preserve it.
- If invalid, clear `prompt_template` and emit a warning.
- If the LLM sets `prompt_template` but never called `find_prompts`, clear it unless the name is present in the prompt registry inventory.
- Do not infer or substitute prompt templates from domain labels, scores, capability-name text, cue lists, string-pattern matching, or compatible-prompt metadata.

Suggested helper:

```python
def validate_prompt_binding(
  *,
  requested_template: str | None,
  capability_name: str,
  discovered_prompts: list[dict[str, Any]],
  prompt_inventory: set[str],
) -> PromptBindingResult:
  ...
```

`PromptBindingResult` states: `valid`, `cleared`, `missing_inventory`.

Acceptance:

- Hallucinated template names do not reach `CommittedPlan` silently.
- A hallucinated template is cleared and logged even when another discovered prompt advertises compatible metadata.
- Exact discovered or inventory-backed template names are preserved.
- Existing tests that only assert prompt preservation should be updated to assert preservation only for valid/inventory-backed names.

#### Issue M5.E1.I2 - Add activity_profile to PlanStep

Files:

- `k1/orchestrator/types.py`
- `k1/planner/stages/expand_service.py`
- `tests/k1/orchestrator/*`

Implementation directive:

- Add optional `activity_profile` to `PlanStep`.
- Preserve in `from_dict()` / `to_dict()` / `from_fabric()` paths.
- Populate `activity_profile` only from capability-contract metadata or exact validated prompt descriptor metadata.
- Do not allow an activity profile to grant tools that are not already present in a contract, plan policy, or orchestrator grant set.

Acceptance:

- Plan step round-trip preserves profile.
- Profile-driven prompt/template selection cannot expand tool authority.

### Epic M5.E2 - Orchestrator CapabilityRequest Propagation

#### Issue M5.E2.I1 - Propagate activity_profile/context into CapabilityRequest

Files:

- `k1/orchestrator/orchestration/step_runner.py`
- `k1/orchestrator/adapters/fabric_gateway_adapter.py`
- `tests/k1/orchestrator/*`

Implementation directive:

- Continue passing `prompt_template`.
- Add `activity_profile` to `CapabilityRequest.context_override["activity_profile"]`; do not add a first-class `CapabilityRequest.activity_profile` field in this milestone.
- Preserve `tools_granted` behavior.

Acceptance:

- Fabric receives activity profile metadata for HIGH-tier steps.
- `StepRunner._build_request()` produces a request whose `context_override` contains both existing `tools_granted` and new `activity_profile` when present.

## Milestone M6 - MEDIUM Binding And Back Direct Dispatch

Purpose: Fix the observed failure class where MEDIUM bypasses Back discovery and exact registry validation fails.

### Epic M6.E1 - Capability Binder For Conversational MEDIUM

#### Issue M6.E1.I1 - Add bind-before-execute path for MEDIUM

Files:

- `k1/concierge/react/capability_routing.py`
- `k1/orchestrator/orchestration/orchestrator_service.py`
- `k1/concierge/tools/implementations.py`
- `tests/k1/concierge/tools/test_dispatch_task_plan_derivation.py`
- `tests/k1/concierge/react/test_capability_binder.py` (new)

Implementation directive:

- MEDIUM conversational tasks should not validate free-text capability names as registry keys.
- Introduce a metadata-only binder used before any MEDIUM direct execution path attempts Fabric validation.
- The binder must accept natural-language intent/action/domain plus optional candidate capability names and return either an exact registry capability name or a typed degradation instruction.

Binder interface:

```python
@dataclass(frozen=True)
class CapabilityBindingRequest:
  action: str
  domain: str | None = None
  params: dict[str, Any] = field(default_factory=dict)
  candidate_capability_name: str | None = None
  session_id: str = ""
  trace_id: str = ""
  safety_band: str = "AMBER"
  actor: str = "back"

@dataclass(frozen=True)
class CapabilityBindingResult:
  status: Literal[
    "bound",
    "needs_discovery",
    "ambiguous",
    "not_found",
    "invalid_candidate",
    "needs_human",
  ]
  capability_name: str | None = None
  params: dict[str, Any] = field(default_factory=dict)
  prompt_template: str | None = None
  activity_profile: str | None = None
  context_override: dict[str, Any] = field(default_factory=dict)
  candidates: list[dict[str, Any]] = field(default_factory=list)
  recovery: dict[str, Any] | None = None
  reason: str = ""
```

Binder resolution order:

1. If `candidate_capability_name` is an exact registry name, return `bound` with contract prompt/profile metadata.
2. If the candidate is not exact but looks like a guessed capability slug, return `invalid_candidate` and force discovery rather than Fabric validation.
3. Run `discover_capabilities(intent=action, domain=domain)` through the existing dispatch/retrieval surface.
4. If one high-confidence exact match exists, return `bound`.
5. If multiple plausible matches exist, return `ambiguous` with candidate options for Back `submit_result(needs_human, selection)`.
6. If no match exists, return `not_found`; Back may ask for clarification or escalate to HIGH Planner if task complexity warrants it.

MEDIUM degradation flow:

```text
Front dispatch_task -> Back task.dispatch
Back profile selector -> discover/binder
  exact bound -> invoke_capability/batch with exact name + context_override
  invalid guessed slug -> do not call Fabric; run discovery once
  ambiguous -> submit_result(needs_human, selection)
  not_found -> submit_result(needs_human, clarification) or spawn_via_fabric for HIGH-worthy work
```

Direct `invoke_capability` remains strict: if a caller already supplies `capability_name`, it must be exact. The binder is used by MEDIUM conversational dispatch/batch derivation before those strict calls are built.

Acceptance:

- Multi-intent Riley task+calendar request does not fail before Back/binder has attempted discovery.
- A guessed name such as `tool.execute.tasks.add_task` is converted to `invalid_candidate` and does not hit Fabric validation directly.
- Ambiguous discovery returns a typed selection payload instead of choosing silently.
- Bound results include `prompt_template`, `activity_profile`, and `context_override` when contract metadata provides them.

#### Issue M6.E1.I2 - Select prompt/profile for direct invoke/batch

Files:

- `k1/concierge/tools/implementations.py`
- `tests/k1/concierge/test_tool_fabric_port_wiring.py`

Implementation directive:

- When `invoke_capability` or `batch_invoke_capabilities` builds `CapabilityRequest`, attach prompt/profile metadata if known from contract or profile selection.
- Do not require prompt/profile for direct native tool success.
- For direct invoke, metadata source order is:
  1. explicit tool args if later added to schema;
  2. looked-up `CapabilityContract.prompt_template` / `activity_profile`;
  3. active Back execution profile selection;
  4. none.
- Build requests as:

```python
CapabilityRequest(
    capability_name=capability_name,
    params=params,
    prompt_template=resolved_prompt_template,
    context_override={
        "activity_profile": resolved_activity_profile,
        "execution_profiles": active_execution_profiles,
        "prompt_variables": params,
    },
    ...
)
```

Do not put prompt/profile keys inside business `params`.

Acceptance:

- Direct Fabric calls can carry profile context.
- Native tools ignore prompt/profile metadata for business logic.
- MCP/WASM/Agent providers can observe metadata after M3 provider forwarding lands.

### M6 Execution Evidence - 2026-05-17

- Added `CapabilityBindingRequest`, `CapabilityBindingResult`, and metadata-only `bind_capability()` in `k1/concierge/react/capability_routing.py`.
- Wired active Back task `invoke_capability` and `batch_invoke_capabilities` through the binder before Fabric `dispatch_direct`; guessed candidates degrade with typed binding errors and do not call Fabric when discovery offers exact alternatives.
- Added prompt/profile forwarding for direct and batch `CapabilityRequest` construction using binder/contract metadata plus active Back execution profiles. Prompt/profile metadata stays out of business `params`.
- Updated Concierge and Fabric docs/diagram to show binder states and unchanged Fabric exact-name execution validation.
- Validation run: `pytest tests/k1/concierge/react/test_capability_binder.py tests/k1/concierge/tools/test_dispatch_task_plan_derivation.py tests/k1/concierge/test_tool_fabric_port_wiring.py -v` passed with 72 tests.
- Additional profile regression: `pytest tests/k1/concierge/prompt/test_back_profiles.py tests/k1/concierge/test_back_handler_profile_wiring.py -v` passed with 14 tests.

## Milestone M7 - KernelService And Runtime Wiring

Purpose: Wire prompt/profile support through shared and per-session runtime creation.

### Epic M7.E1 - KernelService Prompt Store Verification

#### Issue M7.E1.I1 - Verify PromptSystemProdAdapter boot path

Files:

- `k1/kernel/service.py`
- `k1/concierge/config/kernel.py`
- `tests/integration/k1/selfmodel/test_selfmodel_sessionstate.py`

Implementation directive:

- Keep `PromptSystemProdAdapter("k1/contracts/prompts")` wired for shared and session Fabric.
- Add startup verification that logs template count.
- Add optional feature flag `enable_activity_profiles`; default can be true once M2 prompt inventory exists because profiles are advisory only.
- Startup verification should warn, not fail, when the prompt directory is empty unless `enable_activity_profiles_strict=True` is introduced for CI.

Acceptance:

- Kernel startup no longer warns that prompt directory is missing.
- Prompt system template count is observable.
- Missing prompt inventory never prevents native family tools from registering.

### Epic M7.E2 - Family Tools Per-Session Registration

#### Issue M7.E2.I1 - Ensure family tool profile metadata survives shared/session fabric split

Files:

- `k1/kernel/service.py`
- `k1/tools/family/bootstrap.py`
- `tests/k1/tools/family/calendar/test_definition.py`
- `tests/integration/k1/live/m1/test_m1_x3_x12_concierge_cross_component.py`

Implementation directive:

- Shared Fabric registry receives metadata at Tier 1.
- Session Fabric reuses the shared registry and re-registers `NativeToolProvider` at P3.1.
- Verify profile/template fields remain visible in session Fabric discovery.
- Add one targeted assertion that a family calendar contract discovered from session Fabric still has the same `activity_profile` and `prompt_template` as the shared registry contract.

Acceptance:

- Back `discover_capabilities` in a session can see profile/template metadata for family tools.
- Shared/session registry reuse does not strip metadata during provider re-registration.

### M7 Execution Evidence - 2026-05-16

- Added `KernelConfig.enable_activity_profiles` and `enable_activity_profiles_strict` with advisory defaults.
- Added KernelService prompt-store verification for `PromptSystemProdAdapter("k1/contracts/prompts")`; shared startup logs the template count, strict mode fails only on empty inventory, and non-strict mode warns while native family tools remain available.
- Per-session Fabric now reuses the verified shared prompt adapter and the shared `CapabilityRegistry`; P3.1 still re-registers the singleton `NativeToolProvider` without mutating contracts.
- Added calendar core action metadata (`calendar.v1` / `calendar_activity_v1`) so the M7 registry-visibility assertion has real family metadata to preserve; broader tasks/reminders and full family profile expansion remain M8.
- Documentation updated: `docs/plans/k1/activity_profile_prompt_injection_plan.md`, `k1/kernel/CONTRACT.md`, `k1/kernel/WIRING.md`, `k1/kernel/STATE.md`, `k1/fabric/STATE.md`, `k1/concierge/STATE.md`, and `k1/tools/family/STATE.md`.
- Validation run: focused M7 tests covering KernelConfig defaults, prompt-store verification, calendar definition metadata, and session Fabric discovery preservation passed (`12 passed`).
- Prompt inventory regression: `tests/k1/fabric/test_prompt_system_inventory.py` passed (`6 passed`).

## Milestone M8 - Initial Tool Profiles

Purpose: Ship useful first profiles before expanding to every domain.

### M8 Execution Evidence - 2026-05-17

- Expanded calendar from the M7 core slice to all calendar actions and added scheduling/availability/external-calendar domain tags. Calendar guidance now explicitly says to read existing events/feeds before edits, responses, visibility changes, feed changes, or likely duplicate creates when no trusted id is present.
- Added `tasks.v1` / `tasks_activity_v1` to every Tasks action, with task-management/delegation/deadline tags. The task prompt now covers duplicate task/list checks and read-before-update/complete/reassign/delete discipline.
- Added `reminders.v1` / `reminders_activity_v1` to user-invokable Reminders actions, with alerting/notification/scheduler tags. `fire_reminder` remains scheduler-only with explicit tool instructions and no prompt template.
- Added `chores.v1` / `chores_activity_v1` to every Chores action, with recurrence/gamification/reward-tracking tags. The chore prompt covers template-vs-occurrence discipline, parent/guardian gates, duplicate assignment checks, completion/skip/reopen rules, and point-summary confirmation.
- Added `shopping.v1` / `shopping_activity_v1` to every Shopping action, with shopping/category/approval tags. The shopping prompt covers category buckets, duplicate item checks, parent-managed list creation, child request approval, approval/rejection, and check-off discipline.
- Added generic provider prompt assets: `mcp_generic_activity_v1` and `wasm_generic_activity_v1` under `k1/contracts/prompts` plus markdown under `k1/prompts/activities`.
- Attached `mcp.generic.v1` / `mcp_generic_activity_v1` to `find_prompts`, `discover_capabilities`, and `build_agent` contracts; each keeps exact-schema/contract evidence as authority and forbids guessed names.
- Added missing representative WASM tool contracts for `date_calc` and `unit_convert` with `wasm.generic.v1` / `wasm_generic_activity_v1` metadata.
- Documentation updated: `docs/plans/k1/activity_profile_prompt_injection_plan.md`, `docs/whiteboard/conversation_continuity.md`, `k1/tools/family/CONTRACT.md`, `k1/tools/family/WIRING.md`, `k1/tools/family/STATE.md`, `k1/tools/family/ARCHITECTURE.md`, `k1/tools/family/family_tools.mmd`, `k1/fabric/CONTRACT.md`, `k1/fabric/WIRING.md`, `k1/fabric/STATE.md`, `k1/tools/fabric_developer_guide.md`, `k1/tools/mcp_servers/README.md`, and `k1/tools/wasm_modules/README.md`.
- Focused validation passed: family calendar/tasks/reminders definition tests, prompt inventory/profile contract tests, and real `date_calc` / `unit_convert` WASM contract tests (`280 passed`).

### Epic M8.E1 - Family Profiles

#### Issue M8.E1.I1 - Calendar profile

Files:

- `k1/tools/family/calendar/definition.py`
- `k1/contracts/prompts/calendar_activity_v1.yaml`
- `k1/prompts/activities/calendar_activity_v1.md`
- `tests/k1/tools/family/calendar/test_definition.py`

Acceptance:

- Calendar read/write contracts expose calendar activity profile/template.
- Back prompt selector can render calendar guidance.
- Calendar definitions inherit `ToolDefinition.activity_profile` unless an action-specific override is needed.

#### Issue M8.E1.I2 - Tasks profile

Files:

- `k1/tools/family/tasks/definition.py`
- `k1/contracts/prompts/tasks_activity_v1.yaml`
- `k1/prompts/activities/tasks_activity_v1.md`
- `tests/k1/tools/family/tasks/*`

Acceptance:

- Task update/create/complete actions expose task activity profile/template.
- Task definitions use task-specific profile ids and do not reuse calendar profiles for due-date-only tasks.

#### Issue M8.E1.I3 - Reminders profile

Files:

- `k1/tools/family/reminders/definition.py`
- `k1/contracts/prompts/reminders_activity_v1.yaml`
- `k1/prompts/activities/reminders_activity_v1.md`
- `tests/k1/tools/family/reminders/*`

Acceptance:

- Reminder create/update/snooze/dismiss actions expose reminder profile/template.
- Reminder definitions preserve event-linking guidance through `tool_instructions` or prompt template metadata.

#### Issue M8.E1.I4 - Chores profile

Files:

- `k1/tools/family/chores/definition.py`
- `k1/contracts/prompts/chores_activity_v1.yaml`
- `k1/prompts/activities/chores_activity_v1.md`
- `tests/k1/tools/family/chores/*`

Acceptance:

- Chore template, occurrence, completion, skip, reopen, list, and summary contracts expose chore profile/template metadata.
- Chore definitions keep recurring chore guidance distinct from one-shot tasks, reminders, and calendar events.

#### Issue M8.E1.I5 - Shopping profile

Files:

- `k1/tools/family/shopping/definition.py`
- `k1/contracts/prompts/shopping_activity_v1.yaml`
- `k1/prompts/activities/shopping_activity_v1.md`
- `tests/k1/tools/family/shopping/*`

Acceptance:

- Shopping list, item, approval, rejection, check-off, and read contracts expose shopping profile/template metadata.
- Child-originated shopping items remain pending until explicit parent/guardian approval.

### Epic M8.E2 - Generic Provider Profiles

#### Issue M8.E2.I1 - MCP generic profile

Files:

- representative MCP contracts
- `k1/prompts/activities/mcp_generic_activity_v1.md`

Acceptance:

- MCP tools can declare and receive generic profile metadata.

#### Issue M8.E2.I2 - WASM generic profile

Files:

- representative WASM contracts
- `k1/prompts/activities/wasm_generic_activity_v1.md`

Acceptance:

- WASM tools can declare and receive generic profile metadata.

## Milestone M9 - Tests, Observability, And Rollout

Purpose: Make the feature measurable, safe, and incrementally releasable.

### M9 Execution Evidence - 2026-05-17

- Back profile selection now exposes profile IDs, confidence, evidence sources, and fallback reason through `BackProfileSelection` / `BackProfileSelectionOutcome`.
- `back_handler()` and `back_resume_handler()` log structured profile-selection evidence with task ID, trace ID, reason, selected profile IDs, confidence, and evidence sources.
- `record_back_profile_selection()` emits `back.profile.*` metrics through the real `ToolContext.metrics_collector` path when a collector is configured.
- Back handler profile wiring tests use real components: POC bus, testing SessionState, real Back `ToolDispatcher`, real `react_loop()`, real schema validation, and the deterministic ModelHub test bridge. They do not monkeypatch the loop or dispatcher; the model first calls a real allowed Back tool before `submit_result(complete)` so the no-work guard remains active.
- Documentation updated: `docs/plans/k1/activity_profile_prompt_injection_plan.md`, `docs/whiteboard/conversation_continuity.md`, and `k1/concierge/STATE.md`.
- Focused validation passed: Concierge selector/prompt/dispatch/profile wiring/observability tests, Fabric context/provider tests using the actual provider test filenames on this branch, focused family tests, and the targeted live cross-component regression (`808 passed`).
- Final checks: Python diagnostics on touched M9 files were clean, no mock/monkeypatch/fake/stub terms were present in the M9 handler/observability/live tests, and `git diff --check` produced no output.

### Epic M9.E1 - Focused Test Matrix

#### Issue M9.E1.I1 - Concierge selector and prompt tests

Run:

```bash
pytest tests/k1/concierge/prompt/test_back_profiles.py -v
pytest tests/k1/concierge/prompt/test_back_prompt_profile_injection.py -v
pytest tests/k1/concierge/tools/test_task_dispatch_execution_profiles.py -v
pytest tests/k1/concierge/test_back_handler_profile_wiring.py -v
```

#### Issue M9.E1.I2 - Fabric context/provider tests

Run:

```bash
pytest tests/k1/fabric/test_context_builder.py -v
pytest tests/k1/fabric/test_tool_schema_validation.py -v
pytest tests/k1/fabric/test_providers_331_332.py tests/k1/fabric/test_providers_333_334.py -v
pytest tests/k1/fabric/providers/test_native_tool_provider_path.py -v
```

#### Issue M9.E1.I3 - Family tool tests

Run focused family tests only:

```bash
pytest tests/k1/tools/family/calendar/test_definition.py tests/k1/tools/family/calendar/test_service_crud.py -v
pytest tests/k1/concierge/test_family_tools.py -v
```

#### Issue M9.E1.I4 - Live regression

Run only targeted live tests:

```bash
pytest tests/integration/k1/live/m1/test_m1_x3_x12_concierge_cross_component.py -v
```

Do not run full `tests/k1/kernel/` or full Fabric suite unless explicitly requested.

### Epic M9.E2 - Observability

#### Issue M9.E2.I1 - Log profile selection evidence

Files:

- `k1/concierge/prompt/back_profiles.py`
- `k1/concierge/actors/back.py`
- `k1/concierge/obs/actor_metrics.py`

Implementation directive:

Emit structured metadata:

- selected profile IDs;
- confidence;
- evidence sources;
- fallback reason;
- task_id and trace_id.

Acceptance:

- Logs can explain why Back received a calendar/task/reminder profile.

## MVP Cut

The first implementation cut should include:

1. `BackExecutionProfile` registry and selector.
2. `build_back_prompt(execution_profile_block=...)` injection.
3. Back handler and resume handler wiring.
4. `TaskDispatch.execution_profiles` round-trip or safe storage under `reference_context`.
5. Calendar/tasks/reminders generic profiles.
6. Focused Concierge tests only.

This MVP gives immediate value without requiring Fabric provider prompt plumbing. Fabric/schema/provider work follows in M1-M3 to make the system universal across family/MCP/WASM/agent tooling.

## Cross-Cutting Invariants

- Profiles never grant tools, raise safety bands, approve side effects, or bypass HIL.
- Prompt/profile metadata must travel in `prompt_template`, `tool_instructions`, `activity_profile`, or `context_override`; it must not be mixed into business `params`.
- `prompt_variables_schema` describes compile variables only. It never supplies values and never changes provider params.
- `template_file` is the production prompt storage convention. Inline `template` is compatibility-only.
- Native family tools must pass without prompt inventory present.
- Planner and Back may use profiles to rank/discover, but the registry response decides exact capability names.
- MEDIUM conversational dispatch binds before strict Fabric validation; direct `invoke_capability` stays exact-name-only.

## Non-Goals For MVP

- Do not build a full prompt authoring UI.
- Do not create runtime-generated prompt templates.
- Do not make Back conversational.
- Do not let profiles grant tools or authorize side effects.
- Do not require MCP/WASM providers to become LLM-aware.
- Do not block family tools on prompt profile availability.

## Closed Decisions

1. `activity_profile` remains in `CapabilityRequest.context_override["activity_profile"]` for this feature. Do not add a first-class request field until multiple providers need it outside context building.
2. Native family tools do not receive prompt text in business params. They may receive profile/template ids only in audit or execution metadata.
3. `PromptSystemProdAdapter` should prefer schema-intended `template_file` for production; inline `template` stays compatibility-only.
4. Profile selection starts in Concierge Back for M4. Planner/Orchestrator use validated prompt/profile binding in M5. A shared `ActivityProfileResolver` is deferred until duplication appears.
5. Module `tool.yaml` upgrade is deferred until `k1/fabric/module_registry` is production-wired. Family tools and YAML contracts are the active implementation surface now.
