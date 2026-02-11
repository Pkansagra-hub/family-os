# Milestone 3: Constraint Resolution + Adaptive DAG Extensions -- Work Tickets

> **Module**: Orchestrator (Layer 2 in K1 Cognitive Architecture)
> **Milestone**: M3 -- Constraint Resolution + Adaptive DAG Extensions
> **Goal**: Implement pre-execution validation and the 6 agent-aware extensions that make the DAG adaptive (all deterministic, NO LLM).
> **Prerequisite**: M2 complete (basic DAG execution working via OrchestratorService, DAGExecutor, StepRunner)
> **Estimated Epics**: 2 (3.1 Constraint Resolution Engine, 3.2 Adaptive DAG Extensions)
> **Estimated Issues**: 14 (5 in Epic 3.1, 9 in Epic 3.2)

---

## How to Use These Tickets

Each ticket is self-contained. Before starting:

1. Read **Context Files** listed in the ticket
2. Check **Blocked By** -- all listed tickets must be complete
3. Follow **Anti-Hallucination Rules** strictly
4. Verify all items in **Done When** checklist upon completion

---

## Global Anti-Hallucination Rules (ALL M3 Tickets)

- ALL guards are deterministic -- NO LLM calls anywhere in this milestone
- ConstraintResolver does NOT execute steps -- it only calls `fabric_port.query_registry()`, NEVER `fabric_port.execute()`
- ConstraintResolver does NOT modify CommittedPlan in-place -- it CLONES before substituting alternatives (original preserved for audit)
- Guard construction order in OrchestratorFactory step 12 defines execution order -- do NOT reorder without understanding cascading effects
- OutputSchemaGuard MUST run before QualityGate (schema failures should not be quality-retried)
- ConcurrencyGuard is NOT a DAGGuard -- it wraps the entry point in `OrchestratorService._process_one()`, not the DAG walk
- SubStepObserver is NOT a DAGGuard -- it is an event subscriber managed by ExecutionMonitor lifecycle
- Do NOT write to SessionState (ORCH-01: read-only)
- Do NOT add more than 3 resolution cycles to ConstraintResolver -- 3 is a HARD gate
- MicroReplanCheckpoint calls `planner_port.micro_replan()` (synchronous, 10s) -- NOT `planner_port.request_plan()` (async)

---

## Source Document Cross-References

All specifications in this file are grounded in two authoritative documents:

| Aspect | Source | Location |
|--------|--------|----------|
| Issue specs, constructor signatures, wiring | orchestrator-implementation-plan.md | Lines 445-527 (M3 section) |
| Guard pipeline canonical ordering (G0-G10) | schema_whiteboard.md | S8.1-S8.6 (lines 1839-2000) |
| Guard return values (GuardAction, GuardDecision) | schema_whiteboard.md | S8.3 (lines 1900-1920) |
| Guard interface protocols (IPreWaveGuard, IPostStepGuard, IPostWaveGuard) | schema_whiteboard.md | S8.4 (lines 1920-1938) |
| Factory wiring (step 12 of 15) | schema_whiteboard.md | S8.5 (lines 1938-1960) |
| Circuit breaker definitions and ownership | schema_whiteboard.md | S7.1-S7.6 (lines 1732-1838) |
| Planner-Orchestrator protocol (PlanRequest, CommittedPlan) | schema_whiteboard.md | S10.1-S10.7 (lines 2069-2565) |
| MicroReplan round-trip contract | schema_whiteboard.md | S10.6 (lines 2440-2565) |
| CommittedPlan field reconciliation | schema_whiteboard.md | S10.3 (lines 2285-2380) |
| CapabilityDescriptor schema (what Fabric returns) | schema_whiteboard.md | S10.5 (lines 2380-2440) |
| Circuit breaker state machine | schema_whiteboard.md | S7.2 (lines 1749-1758) |
| ErrorRouter classification with CB | schema_whiteboard.md | S7.5 (lines 1816-1830) |

---

## Ordering Reconciliation Note

The plan wiring section (factory step 12) lists guards as a flat ordered list:
`[OutputSchemaGuard, ConditionalEdgeEvaluator, TokenBudgetTracker, QualityGate, MicroReplanCheckpoint, ExecutionMonitor, CostBudgetGuard]`

The schema whiteboard S8.1 uses a more granular phase-based model:
- **Pre-wave**: G1=ConditionalEdgeEvaluator, G2=TokenBudgetTracker, G3=CostBudgetGuard
- **Post-step**: G4=OutputSchemaGuard, G5=QualityGate, G6=TokenBudgetTracker, G7=CostBudgetGuard
- **Post-wave**: G8=ExecutionMonitor, G9=MicroReplanCheckpoint, G10=SafetyBandReRead
- **Wraps dispatch**: G0=ConcurrencyGuard

**Use the whiteboard S8.1 phase-based model** as the canonical reference. The plan's flat list is a construction order only. DAGExecutor calls guards at the correct phase hooks (pre-wave, post-step, post-wave), not sequentially.

**SafetyBandReRead (G10)**: Present in whiteboard S8.1 but not a separate guard in the plan. In the plan, safety band re-read is inline in `DAGExecutor.execute_wave()` (2.2.2 line: `band = await state_port.read("control.safety_band")`). Implementers may either keep it inline or extract to a G10 guard -- both are acceptable. The work ticket below (WT-3.2.10) covers this as an optional extraction.

---

## Epic 3.1: Constraint Resolution Engine

> **File**: `k1/orchestrator/orchestration/constraint_resolver.py`
> **Constructor**: 3 dependencies + 1 policy config (fabric, delta, events, max_cycles=3)
> **Called by**: `DAGExecutor.execute()` (2.2.2) BEFORE the wave loop starts -- NOT directly by OrchestratorService
> **Key invariant**: ConstraintResolver only calls `query_registry()` -- NEVER `execute()`

---

### WT-3.1.1: Implement ConstraintResolver Class + validate() Method

**Deliverable**: `k1/orchestrator/orchestration/constraint_resolver.py`

**Blocked By**: WT-1.2.3 (CommittedPlan), WT-1.2.18 (PlanStep), WT-1.2.20 (ValidationResult, CapabilityCheck, ResolutionResult, RegistryEntry), WT-1.4.2 (IFabricGatewayPort), WT-1.4.5 (IDeltaEmitPort), WT-1.4.7 (IEventSubscriptionPort)

**Context Files**:
- [orchestrator-implementation-plan.md](docs/plans/orchestrator-implementation-plan.md) (lines 454-460 -- Issue 3.1.1 details)
- [orchestrator-implementation-plan.md](docs/plans/orchestrator-implementation-plan.md) (lines 470-482 -- Epic 3.1 wiring section)
- [schema_whiteboard.md](docs/whiteboard/schema_whiteboard.md) (S10.5 lines 2380-2440 -- CapabilityDescriptor schema, what query_registry returns)

**Specification**:

Constructor:
```python
class ConstraintResolver:
    def __init__(
        self,
        fabric: IFabricGatewayPort,
        delta: IDeltaEmitPort,
        events: IEventSubscriptionPort,
        max_cycles: int = 3,  # from policies.contract.yaml (1.3.3)
    ): ...
```

Supporting types (defined in M1 `k1/orchestrator/types.py`):
```python
@dataclass
class ValidationResult:
    valid: bool
    errors: list[str]
    warnings: list[str]
    alternatives_applied: list[AlternativeMapping]
    time_pressure: bool = False
    hil_required: bool = False

@dataclass
class AlternativeMapping:
    original_capability: str
    replacement_capability: str
    reason: str
```

Primary method:
```python
async def validate(self, plan: CommittedPlan) -> ValidationResult:
```

Orchestration logic:
1. `checks = await self.check_capabilities(plan.steps)` (3.1.2)
2. If checks non-empty (issues found): `for check in checks: check.alternatives = await self.find_alternatives(check.capability, step)` (3.1.3)
3. `resolution = await self.resolve_iteratively(plan, checks)` (3.1.4)
4. If `resolution.hil_requested`: `await self.trigger_hil_fallback(resolution.unresolved, plan)` (3.1.5)
5. Compute time budget estimation (per BUDGET-1): sum `estimated_duration_ms` from capability contracts for critical-path steps. If sum > 10s: set `time_pressure=True` on ValidationResult, emit WARN. V1: advisory only, not a hard gate.
6. Return ValidationResult

**Caller integration** (from plan wiring section lines 470-482):
- Called by `DAGExecutor.execute()` BEFORE wave loop: `validation = await self.constraint_resolver.validate(plan, fresh_snapshot)`
- If `not validation.valid`: DAGExecutor returns FAILED immediately without executing any wave
- If `validation.hil_required`: DAGExecutor returns control to OrchestratorService for async HIL parking via PendingHILContext

**Anti-Hallucination Rules**:
- ConstraintResolver does NOT execute steps
- ConstraintResolver does NOT call `fabric_port.execute()` -- ONLY `query_registry()`
- Must CLONE CommittedPlan before substituting alternatives (original preserved for audit)
- max_cycles=3 is a HARD gate -- do NOT add more cycles

**Done When**:
- [ ] File exists at `k1/orchestrator/orchestration/constraint_resolver.py`
- [ ] Constructor accepts 3 deps + max_cycles
- [ ] `validate()` orchestrates 4 sub-steps in order
- [ ] Time budget estimation computed (sum estimated_duration_ms from capability contracts)
- [ ] time_pressure=True when sum > 10s (advisory only)
- [ ] Returns ValidationResult with all fields populated
- [ ] CommittedPlan cloned before any modification (original preserved)

---

### WT-3.1.2: Implement check_capabilities() -- Capability Availability Check

**Deliverable**: `k1/orchestrator/orchestration/constraint_resolver.py` (add method)

**Blocked By**: WT-3.1.1, WT-1.2.20 (CapabilityCheck, RegistryEntry types)

**Context Files**:
- [orchestrator-implementation-plan.md](docs/plans/orchestrator-implementation-plan.md) (lines 460-462 -- Issue 3.1.2 details)
- [schema_whiteboard.md](docs/whiteboard/schema_whiteboard.md) (S10.5 lines 2380-2440 -- CapabilityDescriptor returned by query_registry, fields: name, provider_type, input_schema, output_schema, safety_band_min, has_side_effects, compensation_capability, estimated_duration_ms, domains, description)

**Specification**:
```python
async def check_capabilities(self, steps: list[PlanStep]) -> list[CapabilityCheck]:
```

Supporting type (defined in M1 `k1/orchestrator/types.py`):
```python
@dataclass
class CapabilityCheck:
    step_id: str
    capability: str
    available: bool
    contract_entry: Optional[RegistryEntry]
    alternatives: list[str]
```

Logic:
1. Collect unique capability names across all steps (dedup -- a 10-step plan may reference same capability multiple times)
2. Batch query: `{cap: await self.fabric.query_registry(cap) for cap in unique_caps}` -- one query per unique name, not per step
3. For each step: build CapabilityCheck with `available = (registry_entry is not None)`
4. For unavailable: populate alternatives list from `find_alternatives()` (3.1.3)
5. Also check safety_band_min mismatch: if capability exists but requires higher safety band than current -> treat as unavailable

**Return**: only CapabilityChecks where `available=false` OR where `contract_entry` shows safety_band_min mismatch. Empty list = all capabilities valid.

**Anti-Hallucination Rules**:
- Uses the 14-field PlanStep (from WT-1.2.18), NOT the Fabric 6-field PlanStep
- Import from `k1.orchestrator.types`, NOT `k1.fabric.types`
- One `query_registry()` per unique capability name, NOT per step

**Done When**:
- [ ] `check_capabilities()` deduplicates capability names
- [ ] Batch queries via `fabric.query_registry()` (one per unique name)
- [ ] Checks both availability AND safety_band_min mismatch
- [ ] Returns only problematic CapabilityChecks (empty = all valid)
- [ ] Imports PlanStep from k1.orchestrator.types

---

### WT-3.1.3: Implement find_alternatives() -- Alternative Capability Discovery

**Deliverable**: `k1/orchestrator/orchestration/constraint_resolver.py` (add method)

**Blocked By**: WT-3.1.2

**Context Files**:
- [orchestrator-implementation-plan.md](docs/plans/orchestrator-implementation-plan.md) (lines 462-465 -- Issue 3.1.3 details)
- [schema_whiteboard.md](docs/whiteboard/schema_whiteboard.md) (S10.5 lines 2380-2440 -- CapabilityDescriptor fields including input_schema, output_schema, safety_band_min, domains)

**Specification**:
```python
async def find_alternatives(
    self, missing_capability: str, step: PlanStep
) -> list[AlternativeCapability]:
```

Supporting type:
```python
@dataclass
class AlternativeCapability:
    capability_id: str
    score: float
    param_mapping: dict[str, str]
    safety_band: str  # "GREEN", "AMBER", "RED"
```

Logic:
1. **Category derivation**: Parse capability name via naming convention `tool.{type}.{domain}.*`. Query Fabric Registry for all capabilities in same category.
2. **Safety band filter**: `candidate.safety_band_min <= step.safety_band_min` (same or stricter only)
3. **Scoring** (3 weighted factors):
   - `schema_overlap_ratio` (weight 0.6): how many input/output params match by name+type between candidate's `input_schema`/`output_schema` (from CapabilityDescriptor per WB S10.5) and step's params
   - `safety_band_match` (weight 0.2): exact=1.0, stricter=0.8
   - `name_similarity` (weight 0.2): normalized edit distance on capability_id
4. Sort descending by score, return top 3
5. Build `param_mapping`: `{original_param: alternative_param}` for auto-substitution
6. **Filter**: Remove alternatives with score < 0.3 (too noisy to suggest)

**V1 scope**: Same-category alternatives only. Cross-category deferred to V2.

**Done When**:
- [ ] `find_alternatives()` queries same-category capabilities from Fabric
- [ ] Safety band filter: same or stricter only
- [ ] 3-factor weighted scoring (0.6 schema + 0.2 safety + 0.2 name)
- [ ] Returns top 3 alternatives sorted by score
- [ ] Filters out score < 0.3
- [ ] Builds param_mapping for auto-substitution
- [ ] Returns empty list if no viable alternatives (triggers HIL in cycle 3)

---

### WT-3.1.4: Implement resolve_iteratively() -- 3-Cycle State Machine

**Deliverable**: `k1/orchestrator/orchestration/constraint_resolver.py` (add method)

**Blocked By**: WT-3.1.2, WT-3.1.3

**Context Files**:
- [orchestrator-implementation-plan.md](docs/plans/orchestrator-implementation-plan.md) (lines 465-470 -- Issue 3.1.4 details)

**Specification**:
```python
async def resolve_iteratively(
    self, plan: CommittedPlan, initial_checks: list[CapabilityCheck]
) -> ResolutionResult:
```

Supporting type (defined in M1 `k1/orchestrator/types.py`):
```python
@dataclass
class ResolutionResult:
    resolved: bool
    modified_plan: Optional[CommittedPlan]
    unresolved: list[CapabilityCheck]
    hil_requested: bool
    cycles_used: int
```

**State machine** (max 3 cycles, per `self.max_cycles`):

**Cycle 1 (auto-resolve)**:
- For each unavailable capability with alternatives (score >= 0.3): clone plan, apply best-scored AlternativeCapability substitution, mark step as AUTO_RESOLVED
- Use `AlternativeCapability.param_mapping` for parameter remapping

**Cycle 2 (re-validate)**:
- Run `check_capabilities()` on modified plan
- Substitutions may invalidate downstream steps (e.g., alternative has different output_schema, breaking ParamResolver refs in dependent steps)
- If new issues found: attempt one more `find_alternatives()` round

**Cycle 3 (HIL fallback)**:
- If unresolved issues remain: set `hil_requested=True`, return ResolutionResult with remaining issues
- Caller (`validate()`) invokes `trigger_hil_fallback()`

**Early termination conditions**:
- (a) All checks pass after any cycle -> `resolved=True`, exit immediately
- (b) No alternatives found in cycle 1 -> skip cycle 2, jump straight to cycle 3
- (c) Cycle 2 introduces MORE issues than cycle 1 resolved -> abort auto-resolve, go to cycle 3

**Anti-Hallucination Rules**:
- Each cycle MUST re-run full `check_capabilities()` -- substitutions cascade
- Do NOT add more than 3 cycles
- Clone plan before modification (original preserved for audit)

**Done When**:
- [ ] 3-cycle state machine implemented
- [ ] Cycle 1: auto-substitute best alternatives (score >= 0.3)
- [ ] Cycle 2: re-validate substituted plan via check_capabilities()
- [ ] Cycle 3: set hil_requested=True for remaining issues
- [ ] All 3 early termination conditions handled
- [ ] cycles_used tracked and returned in ResolutionResult
- [ ] Plan cloned before each modification round

---

### WT-3.1.5: Implement trigger_hil_fallback() -- Non-Blocking HIL Request

**Deliverable**: `k1/orchestrator/orchestration/constraint_resolver.py` (add method)

**Blocked By**: WT-3.1.4, WT-1.2.19 (PendingHILContext), WT-1.2.20 (HILRequest)

**Context Files**:
- [orchestrator-implementation-plan.md](docs/plans/orchestrator-implementation-plan.md) (lines 470-475 -- Issue 3.1.5 details)
- [orchestrator-implementation-plan.md](docs/plans/orchestrator-implementation-plan.md) (lines 476-482 -- HIL async pattern wiring)
- [schema_whiteboard.md](docs/whiteboard/schema_whiteboard.md) (S10.1 lines 2083-2169 -- Protocol sequence showing PendingPlanContext parking pattern)

**Specification**:

```python
async def trigger_hil_fallback(
    self, unresolved: list[CapabilityCheck], plan: CommittedPlan
) -> None:
```
Non-blocking -- parks state and returns to mailbox loop immediately.

Helper methods:
```python
def format_constraint_question(self, unresolved: list[CapabilityCheck]) -> str:
```
Human-readable summary of missing capabilities + available alternatives. E.g., "Step s3 requires 'tool.execute.booking' which is unavailable. Alternatives: 'tool.execute.reservation' (score: 0.72). Options: skip step, use alternative, or cancel plan."

```python
def build_options(self, unresolved: list[CapabilityCheck]) -> list[dict]:
```
List of `{label, value}` for each unresolvable step: "skip step" / "choose alternative X" / "cancel plan".

**Async pattern** (per ARCH-3 / ADR-1.1.12):
1. Build HILRequest: `HILRequest(request_id=uuid4(), question=format_constraint_question(unresolved), options=build_options(unresolved), timeout_ms=60000)`
2. Emit via `self.delta.emit_hil_request(hil_request, trace_id)`
3. Park state: `self.service_ref.pending_hil[request_id] = PendingHILContext(dag_state=plan, question=hil_request.question, created_at=time.time(), timeout_ms=60000, timeout_fallback="GRACEFUL_FAIL")`
4. Return to mailbox loop -- DO NOT BLOCK

**Response handling** (receive_hil_response -- separate entry point in OrchestratorService):
- Pops PendingHILContext by request_id
- Applies user's choice: skip steps / apply chosen alternative / cancel plan
- Re-runs `validate()` to verify substitution (user's choice may introduce new constraint violations)

**Timeout**: 60s. On timeout: graceful failure with explanation ("User did not respond to constraint question within 60s").

**Anti-Hallucination Rules**:
- trigger_hil_fallback() RETURNS IMMEDIATELY after parking context
- It does NOT block waiting for user response
- Response arrives later via IEventSubscriptionPort on topic `k1.hil.fallback_response.v1`
- After HIL response, MUST re-run full validate()

**Done When**:
- [ ] `trigger_hil_fallback()` is non-blocking (returns after parking state)
- [ ] HILRequest built with question text + options list
- [ ] Emitted via delta_port.emit_hil_request()
- [ ] PendingHILContext parked in service_ref.pending_hil dict
- [ ] timeout_ms=60000 and timeout_fallback="GRACEFUL_FAIL"
- [ ] format_constraint_question() produces human-readable text
- [ ] build_options() includes skip/alternative/cancel options per step
- [ ] Requires ConstraintResolver to hold a `service_ref` backreference to OrchestratorService (lazy init in factory)

---

## Epic 3.2: Adaptive DAG Extensions (Guards)

> **File location**: Each guard in its own file under `k1/orchestrator/orchestration/guards/`
> **Package init**: `k1/orchestrator/orchestration/guards/__init__.py` exports DAGGuard ABC, DAGContext, GuardDecision, and all concrete guards
> **Canonical ordering**: Per WB S8.1 (lines 1845-1895):
>   - G0: ConcurrencyGuard (wraps _process_one)
>   - G1: ConditionalEdgeEvaluator (pre-wave)
>   - G2/G6: TokenBudgetTracker (pre-wave + post-step)
>   - G3/G7: CostBudgetGuard (pre-wave + post-step)
>   - G4: OutputSchemaGuard (post-step)
>   - G5: QualityGate (post-step)
>   - G8: ExecutionMonitor (post-wave)
>   - G9: MicroReplanCheckpoint (post-wave)
>   - G10: SafetyBandReRead (post-wave -- inline in DAGExecutor or extracted)
>
> **All guards are deterministic**: NO LLM calls. JSON Schema validation, boolean evaluation, counter arithmetic, float comparison, substring heuristic, flag check, lock.

---

### WT-3.2.0: Implement Guard Base Types (DAGGuard ABC, DAGContext, GuardDecision)

**Deliverable**: `k1/orchestrator/orchestration/guards/__init__.py`

**Blocked By**: WT-1.2.16 (CostAccumulator), WT-1.2.24 (GuardAction, GuardDecision types from M1)

**Context Files**:
- [schema_whiteboard.md](docs/whiteboard/schema_whiteboard.md) (S8.3 lines 1900-1920 -- GuardAction enum values: CONTINUE, RETRY, SKIP, HARD_STOP, BYPASS)
- [schema_whiteboard.md](docs/whiteboard/schema_whiteboard.md) (S8.4 lines 1920-1938 -- IPreWaveGuard, IPostStepGuard, IPostWaveGuard protocol interfaces)
- [orchestrator-implementation-plan.md](docs/plans/orchestrator-implementation-plan.md) (lines 520-527 -- Guard base types in wiring section)

**Specification**:

Guard ABC (from plan wiring):
```python
class DAGGuard(ABC):
    async def before_wave(self, wave: Wave, ctx: DAGContext) -> GuardDecision: ...
    async def after_step(self, step: PlanStep, result: StepResult, ctx: DAGContext) -> GuardDecision: ...
    async def after_wave(self, wave: Wave, results: list[StepResult], ctx: DAGContext) -> GuardDecision: ...
```
Default implementations return `GuardDecision(action=GuardAction.CONTINUE, ...)`.

Shared context (from plan wiring):
```python
@dataclass
class DAGContext:
    merged_results: dict[str, CapabilityResult]
    token_budget_max: int
    tokens_consumed: int
    cost_accumulator: CostAccumulator
    interrupt_flag: bool
    safety_band: str  # "GREEN", "AMBER", "RED", "BLACK"
    dag_id: str
    trace_id: str
```

GuardDecision (from WB S8.3):
```python
class GuardAction(str, Enum):
    CONTINUE = "CONTINUE"   # proceed normally
    RETRY = "RETRY"         # re-execute the step
    SKIP = "SKIP"           # skip the step
    HARD_STOP = "HARD_STOP" # abort remaining waves
    BYPASS = "BYPASS"       # guard not applicable

@dataclass(frozen=True)
class GuardDecision:
    action: GuardAction
    reason: str
    guard_name: str
    metadata: Dict[str, Any] = field(default_factory=dict)
```

Also define the 3 protocol interfaces (from WB S8.4):
```python
@runtime_checkable
class IPreWaveGuard(Protocol):
    async def evaluate_pre_wave(self, wave: Wave, ctx: ProcessingContext) -> List[GuardDecision]: ...

@runtime_checkable
class IPostStepGuard(Protocol):
    async def evaluate_post_step(self, step: PlanStep, result: StepResult, ctx: ProcessingContext) -> GuardDecision: ...

@runtime_checkable
class IPostWaveGuard(Protocol):
    async def evaluate_post_wave(self, wave_result: WaveResult, ctx: ProcessingContext) -> GuardDecision: ...
```

**Note on dual interface**: The plan uses `DAGGuard` ABC with 3 hooks. The whiteboard uses 3 separate Protocol interfaces. Both are valid; the ABC approach is simpler for V1. Guard classes extend DAGGuard and override only the hooks they need. The Protocol interfaces from WB S8.4 are documented here for future reference / potential migration.

**Guard decision handling by DAGExecutor** (from plan wiring):
- `CONTINUE` -> proceed
- `RETRY` -> `_execute_step()` re-invokes `step_runner.run()` with modified request
- `SKIP` -> step marked SKIPPED, reason in `StepResult.error_detail`
- `FAIL` -> step marked FAILED, trigger `cancel_dependents()` (2.2.4)
- `HARD_STOP` -> break wave loop, skip remaining waves, return partial results
- `BYPASS` -> guard not applicable, proceed (same as CONTINUE)

**Done When**:
- [ ] `guards/__init__.py` exists
- [ ] DAGGuard ABC with 3 hook methods, default implementations return CONTINUE
- [ ] DAGContext dataclass with all 8 fields
- [ ] GuardAction enum with 5 values matching WB S8.3 exactly
- [ ] GuardDecision frozen dataclass with action, reason, guard_name, metadata
- [ ] Package re-exports all concrete guards (empty initially, populated as guards are created)

---

### WT-3.2.1: Implement OutputSchemaGuard (ORCH-15) — G4 Post-Step

**Deliverable**: `k1/orchestrator/orchestration/guards/output_schema_guard.py`

**Blocked By**: WT-3.2.0 (guard base types), WT-1.2.18 (PlanStep with output_schema field), WT-1.2.5 (StepResult)

**Context Files**:
- [orchestrator-implementation-plan.md](docs/plans/orchestrator-implementation-plan.md) (lines 487-493 -- Issue 3.2.1 details)
- [schema_whiteboard.md](docs/whiteboard/schema_whiteboard.md) (S8.2 line for G4 -- OutputSchemaGuard, post-step phase, ORCH-15 invariant)
- [schema_whiteboard.md](docs/whiteboard/schema_whiteboard.md) (S8.5 lines 1938-1960 -- post_step_guards list: OutputSchemaGuard first, then QualityGate)

**Specification**:
```python
class OutputSchemaGuard(DAGGuard):
    def __init__(self) -> None:
        pass  # stateless, no dependencies
```

**Overrides**: `after_step()` only. `before_wave()` and `after_wave()` use default (CONTINUE).

**after_step logic**:
1. If `step.output_schema is None`: return `GuardDecision(BYPASS, "no output schema defined")`
2. Validate `result.result.data` against `step.output_schema` via `jsonschema.validate()` (JSON Schema Draft 2020-12)
3. **Valid**: return `GuardDecision(CONTINUE, "schema valid")`
4. **Invalid + first attempt** (check: `result.schema_retry is False`): return `GuardDecision(RETRY, f"schema validation failed: {errors}")` -- StepRunner (2.3.3) re-invokes with `__schema_hint` param containing validation error message
5. **Invalid + already retried** (`result.schema_retry is True`): return `GuardDecision(FAIL, "schema validation failed after retry")` -- step marked FAILED, `cancel_dependents()` invoked

**Anti-Hallucination Rules**:
- Schema validation is per-step (after_step), NOT per-wave
- OutputSchemaGuard MUST run before QualityGate in post-step phase (per WB S8.5: OutputSchemaGuard first, QualityGate second)
- `jsonschema` is a dev dependency -- must be in requirements.txt
- Large result.data: set `format_checker=None` to avoid slow format validation

**Done When**:
- [ ] File exists at `k1/orchestrator/orchestration/guards/output_schema_guard.py`
- [ ] Stateless (no constructor deps)
- [ ] after_step() validates result.data against step.output_schema
- [ ] BYPASS if no output_schema
- [ ] RETRY on first schema failure
- [ ] FAIL on second schema failure (already retried)
- [ ] Uses jsonschema.validate() with Draft 2020-12
- [ ] format_checker=None for performance

---

### WT-3.2.2: Implement ConditionalEdgeEvaluator (ORCH-16) — G1 Pre-Wave

**Deliverable**: `k1/orchestrator/orchestration/guards/conditional_eval.py`

**Blocked By**: WT-3.2.0 (guard base types), WT-1.2.20 (ConditionExpr type with AND/OR/NOT/EQ/NEQ/GT/LT)

**Context Files**:
- [orchestrator-implementation-plan.md](docs/plans/orchestrator-implementation-plan.md) (lines 493-497 -- Issue 3.2.2 details)
- [schema_whiteboard.md](docs/whiteboard/schema_whiteboard.md) (S8.2 line for G1 -- ConditionalEdgeEvaluator, pre-wave phase, ORCH-16 invariant)

**Specification**:
```python
class ConditionalEdgeEvaluator(DAGGuard):
    def __init__(self) -> None:
        pass  # stateless, pure evaluator
```

**Overrides**: `before_wave()` only.

**before_wave logic**:
For each step in `wave.steps`:
1. If `step.condition is None` (or empty list): PASS (always dispatch)
2. Otherwise evaluate each Condition against `ctx.merged_results`

**Condition language** (from plan):
```python
@dataclass
class Condition:
    left: str       # "step_id.status" or "step_id.result.json_path"
    op: str         # "==", "!=", ">", "<", ">=", "<=", "contains"
    right: str      # literal value (string, int, float, bool)
    combinator: str = "AND"  # "AND", "OR", "NOT"
```

**Evaluation**:
1. Resolve `left` by looking up `ctx.merged_results[step_id]`
2. Drill into `.status` (StepStatus enum value) or `.result.data` via dotted json_path
3. Compare with `op`
4. Combine multiple conditions via `combinator` (parsed left-to-right, no precedence grouping in V1)

**Results**:
- Step condition evaluates FALSE -> mark step SKIPPED (remove from wave dispatch list)
- Step condition evaluates TRUE -> CONTINUE (dispatch normally)
- ALL steps in wave evaluate FALSE -> empty wave -> skip entire wave

**Shared result store** (per SEM-4): `ctx.merged_results` is the same dict populated by DAGExecutor after each step completes, also read by MicroReplanCheckpoint (3.2.5).

**Anti-Hallucination Rules**:
- Missing step_id in merged_results (not yet executed) -> condition evaluates to FALSE (conservative skip)
- Empty conditions list = always dispatch (NOT always skip)
- V1: simple comparisons only -- no function calls in conditions (per ADR-1.1.11 Q10)

**Example**:
```python
# Step s4 has condition: left="s2.result.data.has_event_room", op="==", right="true"
# ctx.merged_results["s2"].data = {"has_event_room": true}
# Evaluation: true == true -> CONTINUE (dispatch s4)

# Step s5 has condition: left="s1.status", op="==", right="COMPLETED"
# s1 is FAILED -> "FAILED" == "COMPLETED" -> FALSE -> SKIP s5
```

**Done When**:
- [ ] File exists at `k1/orchestrator/orchestration/guards/conditional_eval.py`
- [ ] Stateless (no constructor deps)
- [ ] before_wave() evaluates conditions for each step
- [ ] Supports 7 comparison operators: ==, !=, >, <, >=, <=, contains
- [ ] Supports AND/OR/NOT combinators (left-to-right evaluation)
- [ ] Resolves left operand from ctx.merged_results
- [ ] Missing step_id -> FALSE (conservative skip)
- [ ] Empty conditions -> always dispatch
- [ ] Removes SKIPPED steps from wave dispatch list

---

### WT-3.2.3: Implement TokenBudgetTracker (ORCH-14) — G2 Pre-Wave + G6 Post-Step

**Deliverable**: `k1/orchestrator/orchestration/guards/token_tracker.py`

**Blocked By**: WT-3.2.0 (guard base types), WT-1.4.5 (IDeltaEmitPort for WARN emission)

**Context Files**:
- [orchestrator-implementation-plan.md](docs/plans/orchestrator-implementation-plan.md) (lines 497-503 -- Issue 3.2.3 details)
- [schema_whiteboard.md](docs/whiteboard/schema_whiteboard.md) (S8.2 lines for G2/G6 -- TokenBudgetTracker, pre-wave + post-step, ORCH-14 invariant, config: token_budget_warn_pct, token_budget_skip_pct)

**Specification**:
```python
class TokenBudgetTracker(DAGGuard):
    def __init__(
        self,
        warn_threshold: float = 0.80,
        skip_threshold: float = 0.95,
        hard_stop_threshold: float = 1.00,
    ):
        self.warn_threshold = warn_threshold
        self.skip_threshold = skip_threshold
        self.hard_stop_threshold = hard_stop_threshold
        self.tokens_consumed: int = 0
        self.budget_pressure: bool = False
```

**Overrides**: `after_step()` + `after_wave()` (plan says after_step + after_wave). Also acts at pre-wave per WB S8.1 (G2).

**after_step (G6)**: Accumulate tokens:
```python
self.tokens_consumed += result.tokens_consumed
```
ALL attempts count toward budget (INV-1): retries consume tokens. A step with 2 normal retries + 1 schema retry = 4 calls, all token costs charged. StepResult.tokens_consumed already includes retry totals (from WT-2.3.2).

**after_wave / pre_wave (G2)**: Check thresholds:
```python
utilization = self.tokens_consumed / ctx.token_budget_max
```
- `>= 0.80` (warn_threshold): emit DAG_BUDGET_WARNING via delta_port + set `self.budget_pressure = True`
  - Per BUDGET-3: DAGExecutor reads this flag and sets `budget_pressure=true` on subsequent CapabilityRequests
  - Fabric ContextBuilder applies shorter context window
  - Orchestrator stays pure -- no LLM compression
- `>= 0.95` (skip_threshold): return SKIP for optional (non-critical-path) steps in next wave (`step.is_optional=True`)
- `>= 1.00` (hard_stop_threshold): return HARD_STOP

**budget_pressure accessor**:
```python
@property
def budget_pressure(self) -> bool:
    return self._budget_pressure
```
Read by DAGExecutor when building CapabilityRequests for subsequent steps.

**Anti-Hallucination Rules**:
- `token_budget_max=0` -> guard disabled. Division by zero protection: if budget is 0, ALWAYS return CONTINUE
- Budget pressure flag is advisory -- Fabric decides how to compress, not Orchestrator
- Planner should include 1.5x per-step token sum in token_budget_max (documented in cross-component contract 1.3.4)

**Done When**:
- [ ] File exists at `k1/orchestrator/orchestration/guards/token_tracker.py`
- [ ] Constructor with 3 threshold params
- [ ] after_step() accumulates tokens_consumed
- [ ] after_wave() checks utilization against 3 thresholds
- [ ] Emits DAG_BUDGET_WARNING at >= 80%
- [ ] Returns SKIP for optional steps at >= 95%
- [ ] Returns HARD_STOP at >= 100%
- [ ] budget_pressure property readable by DAGExecutor
- [ ] Division by zero protection when token_budget_max=0

---

### WT-3.2.4: Implement QualityGate — G5 Post-Step

**Deliverable**: `k1/orchestrator/orchestration/guards/quality_gate.py`

**Blocked By**: WT-3.2.0 (guard base types), WT-1.2.20 (QualityDecision type)

**Context Files**:
- [orchestrator-implementation-plan.md](docs/plans/orchestrator-implementation-plan.md) (lines 503-507 -- Issue 3.2.4 details)
- [schema_whiteboard.md](docs/whiteboard/schema_whiteboard.md) (S8.2 line for G5 -- QualityGate, post-step, config: quality_threshold_low=0.3, quality_threshold_high=0.7)

**Specification**:
```python
class QualityGate(DAGGuard):
    def __init__(
        self,
        pass_threshold: float = 0.7,
        retry_threshold: float = 0.3,
    ):
        pass  # Stateless: thresholds set at construction, no mutable state
```

**Overrides**: `after_step()` only.

**after_step logic**:
1. Read `quality_score` from `result.result.data.get("quality_score")` if present (populated by Fabric agent execution per FAB-13)
2. `quality_score is None` (non-agent capability, e.g., tool-only): return CONTINUE (assume acceptable)
3. `>= pass_threshold (0.7)`: return CONTINUE -- sufficiently high quality
4. `>= retry_threshold (0.3) AND < pass_threshold`: return RETRY -- StepRunner (2.3.4) re-invokes with `__quality_hint` param. Max 1 quality retry per step.
5. `< retry_threshold (0.3)`: return FAIL (soft) -- result too poor to retry meaningfully

**Edge case**: If step already had a quality retry (`result.quality_retry is True`) and quality_score is still < 0.7: return FAIL (do NOT retry again).

**Soft fail behavior**: Step marked FAILED but does NOT trigger `cancel_dependents()` immediately. Downstream conditional edges (3.2.2) may still evaluate to TRUE based on partial data. This is different from HARD FAIL where dependents are always cancelled.

**Anti-Hallucination Rules**:
- quality_score is `float 0.0..1.0`, NOT percentage
- Quality retry only applies to agent-type capabilities (tool results don't have quality_score)
- Thresholds are constructor params -- can be overridden per deployment via OrchestratorFactory config
- QualityGate runs AFTER OutputSchemaGuard in post-step phase (per WB S8.5)

**Done When**:
- [ ] File exists at `k1/orchestrator/orchestration/guards/quality_gate.py`
- [ ] Stateless (thresholds set at construction only)
- [ ] after_step() reads quality_score from result data
- [ ] None quality_score -> CONTINUE
- [ ] >= 0.7 -> CONTINUE
- [ ] 0.3-0.7 -> RETRY (max 1)
- [ ] < 0.3 -> FAIL (soft)
- [ ] Already-retried + still < 0.7 -> FAIL (no second retry)

---

### WT-3.2.5: Implement MicroReplanCheckpoint (ORCH-13) — G9 Post-Wave

**Deliverable**: `k1/orchestrator/orchestration/guards/micro_replan.py`

**Blocked By**: WT-3.2.0 (guard base types), WT-1.4.3 (IPlannerPort), WT-1.2.8 (MicroReplanRequest), WT-1.2.20 (Discovery type)

**Context Files**:
- [orchestrator-implementation-plan.md](docs/plans/orchestrator-implementation-plan.md) (lines 507-513 -- Issue 3.2.5 details)
- [schema_whiteboard.md](docs/whiteboard/schema_whiteboard.md) (S10.6 lines 2440-2565 -- MicroReplan round-trip contract: protocol sequence, transport schema with fields request_id/original_plan_id/completed_results/discoveries/remaining_steps/failure_context/trace_id, key differences table vs request_plan)
- [schema_whiteboard.md](docs/whiteboard/schema_whiteboard.md) (S10.6 key contract differences table: micro_replan is SYNCHRONOUS 10s timeout, direct return, max 1 per DAG, on failure continue original plan)

**Specification**:
```python
class MicroReplanCheckpoint(DAGGuard):
    def __init__(self, planner: IPlannerPort, max_replans: int = 1):
        self.planner = planner
        self.max_replans = max_replans
        self.replans_used: int = 0  # reset per DAG
```

**Overrides**: `after_wave()` only.

**after_wave logic**:
1. Collect all `CapabilityResult.discoveries[]` from wave results (per SEM-4, discoveries come from step results)
2. **Heuristic**: for each discovery, check if `discovery.field` overlaps any param name in remaining (unexecuted) steps. Overlap = substring match or exact match on field name. (Conservative heuristic per ADR-1.1.11 Q8: exact field match in V1)
3. If overlap found AND `self.replans_used < self.max_replans`:
   a. Build MicroReplanRequest (per WB S10.6 transport schema):
      ```python
      MicroReplanRequest(
          request_id=uuid4(),
          original_plan_id=plan.plan_id,
          completed_results={s.step_id: s.to_dict() for s in all_completed},
          discoveries=discoveries,
          remaining_steps=remaining_steps,  # non-empty (validated)
          failure_context=None,  # or FailureContext if triggered by failure
          trace_id=ctx.trace_id,
      )
      ```
   b. `new_plan = await self.planner.micro_replan(request)` with 10s timeout (PROTOCOL-3 per WB S10.6)
   c. If new_plan received: replace remaining waves with `build_waves(new_plan.steps)`, increment `self.replans_used`, return CONTINUE
   d. If timeout or None: log warning, return CONTINUE (continue with original remaining plan)
4. If no overlap or max_replans reached: return CONTINUE

**Key contract differences** (from WB S10.6 table):
| Aspect | request_plan() | micro_replan() |
|--------|---------------|----------------|
| Delivery | Async (fire-and-forget, event-driven) | **SYNCHRONOUS** (10s timeout) |
| Response | CommittedPlan via event bus | Optional[CommittedPlan] returned directly |
| Correlation | PendingPlanContext parking | Direct await (no parking) |
| Context | Full ContextSnapshot | completed_results + discoveries + remaining |
| Max calls | Unlimited per session | **Max 1 per DAG** (ORCH-13) |
| Timeout | 45s (CB_PLANNER) | **10s** (PROTOCOL-3) |
| On failure | AggregatedResult FAILED | **Continue original plan** (graceful) |

**Result scope** (per SEM-4): Replacement waves have access to `ctx.merged_results` containing all prior step results. Replacement steps can reference prior outputs via ParamResolver without re-computation.

**Anti-Hallucination Rules**:
- Micro-replan is SYNCHRONOUS (10s block) -- acceptable because DAG is already mid-execution
- Calls `planner_port.micro_replan()` -- NOT `planner_port.request_plan()`
- Only 1 replan per DAG in V1
- Planner must handle MicroReplanRequest quickly -- it receives existing merged_results, NOT full intent re-planning
- remaining_steps must be non-empty (per WB S10.6 schema: minItems: 1)

**Done When**:
- [ ] File exists at `k1/orchestrator/orchestration/guards/micro_replan.py`
- [ ] Constructor takes planner port + max_replans (default 1)
- [ ] after_wave() collects discoveries from wave results
- [ ] Discovery-to-param overlap heuristic (exact field match V1)
- [ ] Builds MicroReplanRequest per WB S10.6 schema
- [ ] Calls planner.micro_replan() with 10s timeout
- [ ] On success: replaces remaining waves, increments replans_used
- [ ] On timeout/None: continues original plan (graceful)
- [ ] replans_used enforces max 1 per DAG
- [ ] replans_used reset mechanism for new DAG

---

### WT-3.2.6: Implement ExecutionMonitor — G8 Post-Wave + Interrupt Check

**Deliverable**: `k1/orchestrator/orchestration/guards/execution_monitor.py`

**Blocked By**: WT-3.2.0 (guard base types), WT-1.4.5 (IDeltaEmitPort), WT-1.2.19 (PendingHILContext), WT-1.2.20 (HILRequest)

**Context Files**:
- [orchestrator-implementation-plan.md](docs/plans/orchestrator-implementation-plan.md) (lines 513-518 -- Issue 3.2.6 details)
- [schema_whiteboard.md](docs/whiteboard/schema_whiteboard.md) (S8.2 line for G8 -- ExecutionMonitor, post-wave, ORCH-09 invariant, config: substep_rate_limit_ms)

**Specification**:
```python
class ExecutionMonitor(DAGGuard):
    def __init__(self, delta: IDeltaEmitPort, service_ref: "OrchestratorService"):
        self.delta = delta
        self.service_ref = service_ref  # backreference for PendingHILContext parking
```

`service_ref` creates a circular dependency with OrchestratorService, resolved by lazy init in OrchestratorFactory.

**Overrides**: `after_step()` + `after_wave()`

**after_step (per SPEC-5)**: Interrupt check
```python
if ctx.interrupt_flag:
    return GuardDecision(HARD_STOP, "interrupt requested by user")
```
Checks interrupt flag at **per-step completion** (not just wave boundary). Better UX: user waits max one step duration, not entire wave.

**after_wave**: Progress emission + optional override
1. Emit progress: `await self.delta.emit_progress(wave.wave_index, summary_of_results, ctx.trace_id)` on topic `k1.hil.progress.v1`
2. **Optional override** (only when: step count > 3 OR wave duration > 5s -- to avoid spamming):
   a. `request_id = uuid4()`
   b. Emit override prompt: `await self.delta.emit_hil_request(HILRequest(request_id, "Continue or cancel?", ["CONTINUE", "CANCEL_DAG"], 30000), ctx.trace_id)`
   c. Park: `self.service_ref.pending_hil[request_id] = PendingHILContext(timeout_ms=30000, timeout_fallback="CONTINUE")`
   d. Return control to mailbox loop

**Override options** (per SEM-2): `CONTINUE` or `CANCEL_DAG` only. MODIFY_PARAMS removed from V1 -- dangerously underspecified; if user wants different params, they cancel and re-issue.

**Timeout**: 30s. On timeout: CONTINUE (default -- user silence = proceed).

**Anti-Hallucination Rules**:
- Override emitting is OPTIONAL per wave -- only emit when wave is significant (> 3 steps or > 5s duration)
- service_ref backreference creates circular dep -- resolved by lazy init in factory
- MODIFY_PARAMS is NOT an option in V1

**Done When**:
- [ ] File exists at `k1/orchestrator/orchestration/guards/execution_monitor.py`
- [ ] Constructor takes delta_port + service_ref
- [ ] after_step() checks ctx.interrupt_flag -> HARD_STOP
- [ ] after_wave() emits progress delta
- [ ] Override prompt only when step_count > 3 or wave_duration > 5s
- [ ] HILRequest with options ["CONTINUE", "CANCEL_DAG"] only
- [ ] PendingHILContext parked with timeout_fallback="CONTINUE"
- [ ] timeout_ms=30000

---

### WT-3.2.7: Implement SubStepObserver -- Sub-Step Observability Pass-Through

**Deliverable**: `k1/orchestrator/orchestration/guards/execution_monitor.py` (same file as 3.2.6)

**Blocked By**: WT-3.2.6, WT-1.4.7 (IEventSubscriptionPort), WT-1.4.5 (IDeltaEmitPort)

**Context Files**:
- [orchestrator-implementation-plan.md](docs/plans/orchestrator-implementation-plan.md) (lines 518-520 -- Issue 3.2.7 details)
- ADR-1.1.11 Q11 (sub-step event rate limit: max 1 per step per 500ms)

**Specification**:
NOT a DAGGuard -- event subscriber managed by ExecutionMonitor lifecycle.

```python
class SubStepObserver:
    def __init__(
        self,
        events: IEventSubscriptionPort,
        delta: IDeltaEmitPort,
        rate_limit_ms: int = 500,
    ):
        self.events = events
        self.delta = delta
        self.rate_limit_ms = rate_limit_ms
        self.step_agent_map: dict[str, str] = {}       # step_id -> agent_id
        self.last_emit: dict[str, float] = {}           # step_id -> last emit timestamp
        self._subscription_ids: list[str] = []
```

**Methods**:
- `register_step_agent(step_id, agent_id)`: Called by StepRunner when CapabilityResult returns agent_id
- `async start(dag_id)`: Subscribes to `fabric.agent.*.tool_call.*` and `fabric.agent.*.llm_call.*` via events port
- `async stop()`: Unsubscribes all stored subscription_ids
- `async on_sub_step_event(event: dict)`: Callback:
  1. Extract agent_id from event topic
  2. Reverse-lookup step_id from step_agent_map
  3. Rate limit check: `if now - self.last_emit.get(step_id, 0) < rate_limit_ms / 1000: return` (drop)
  4. Enrich event with step_id
  5. Forward: `await self.delta.emit_progress(step_id, event["summary"], trace_id)`
  6. Update `self.last_emit[step_id] = now`

**Rate limiting** (per ADR-1.1.11 Q11): Max 1 sub-step event per step per 500ms. Prevents DeltaBus flooding during chatty agent executions.

**Lifecycle**: Started by `DAGExecutor.execute()` before wave loop, stopped after. Must be started/stopped with DAG lifecycle.

**Anti-Hallucination Rules**:
- Pass-through only -- NO transformation, NO LLM
- If agent_id not in step_agent_map (agent spawned sub-agent): log and forward with step_id="unknown"
- SubStepObserver is NOT in the guard list

**Done When**:
- [ ] SubStepObserver class in execution_monitor.py
- [ ] Subscribes to fabric.agent.*.tool_call.* and fabric.agent.*.llm_call.*
- [ ] Rate limiting: max 1 event per step per 500ms
- [ ] register_step_agent() maps step_id -> agent_id
- [ ] start()/stop() manage subscription lifecycle
- [ ] Unknown agent_id forwarded with step_id="unknown"

---

### WT-3.2.8: Implement CostBudgetGuard — G3 Pre-Wave + G7 Post-Step

**Deliverable**: `k1/orchestrator/orchestration/guards/cost_guard.py`

**Blocked By**: WT-3.2.0 (guard base types), WT-1.2.16 (CostAccumulator), WT-1.4.5 (IDeltaEmitPort)

**Context Files**:
- [orchestrator-implementation-plan.md](docs/plans/orchestrator-implementation-plan.md) (lines 520-522 -- Issue 3.2.8 details)
- [schema_whiteboard.md](docs/whiteboard/schema_whiteboard.md) (S8.2 lines for G3/G7 -- CostBudgetGuard, pre-wave + post-step, ORCH-14 cost variant)

**Specification**:
```python
class CostBudgetGuard(DAGGuard):
    def __init__(
        self,
        delta: IDeltaEmitPort,
        warn_threshold: float = 0.80,
        skip_threshold: float = 0.95,
        hard_stop_threshold: float = 1.00,
    ):
        self.delta = delta
        self.warn_threshold = warn_threshold
        self.skip_threshold = skip_threshold
        self.hard_stop_threshold = hard_stop_threshold
```

Mirrors TokenBudgetTracker pattern exactly, but operates on USD cost instead of tokens.

**after_step (G7)**: Read cost from result:
```python
ctx.cost_accumulator.add(step.id, result.cost_usd or 0.0)
```

**after_wave / pre_wave (G3)**: Check thresholds:
```python
utilization = ctx.cost_accumulator.utilization()
```
- `>= 0.80`: emit DAG_BUDGET_WARNING event via delta_port
- `>= 0.95`: return SKIP for optional steps (`step.is_optional=True`)
- `>= 1.00`: return HARD_STOP

**Pass-through mode**: If `cost_budget_max_usd` not set in CommittedPlan (or == 0.0 or None): guard disabled, all decisions return CONTINUE. Resolves Open Q7 from ADR-1.1.11.

**Anti-Hallucination Rules**:
- CostAccumulator (WT-1.2.16) lives in DAGContext, shared across guards
- CostBudgetGuard reads from accumulator; StepRunner writes to it (add per-step cost)
- cost_usd from CapabilityResult may be None for non-billable capabilities (internal tools) -- treat as 0.0
- Unlike token budget, cost budget has NO "budget_pressure" flag on CapabilityRequests (cost compression not applicable)

**Done When**:
- [ ] File exists at `k1/orchestrator/orchestration/guards/cost_guard.py`
- [ ] Constructor takes delta_port + 3 threshold params
- [ ] after_step() feeds cost into ctx.cost_accumulator
- [ ] after_wave() checks utilization against 3 thresholds
- [ ] Emits DAG_BUDGET_WARNING at >= 80%
- [ ] Returns SKIP for optional steps at >= 95%
- [ ] Returns HARD_STOP at >= 100%
- [ ] Pass-through mode when no cost budget set (None or 0.0)
- [ ] None cost_usd treated as 0.0

---

### WT-3.2.9: Implement ConcurrencyGuard — G0 Wraps Dispatch

**Deliverable**: `k1/orchestrator/orchestration/guards/concurrency_guard.py`

**Blocked By**: WT-2.1.1 (OrchestratorService -- uses ConcurrencyGuard in _process_one)

**Context Files**:
- [orchestrator-implementation-plan.md](docs/plans/orchestrator-implementation-plan.md) (lines 522-527 -- Issue 3.2.9 details incl asyncio.Lock usage)
- [schema_whiteboard.md](docs/whiteboard/schema_whiteboard.md) (S8.1 line 1857 -- G0 ConcurrencyGuard wraps _process_one, S8.2 G0 row: ORCH-02 invariant, config: max_concurrent_dags)

**Specification**:
NOT a DAGGuard -- checked in `OrchestratorService._process_one()` BEFORE dispatching to DAGExecutor.

```python
class ConcurrencyGuard:
    def __init__(self) -> None:
        self._lock: asyncio.Lock = asyncio.Lock()
        self._active: bool = False
```

**Methods**:
```python
async def acquire(self) -> bool:
    """Non-blocking lock acquisition. Returns False if DAG already active."""
    if self._lock.locked():
        return False
    await self._lock.acquire()
    self._active = True
    return True

def release(self) -> None:
    """Release lock. MUST be called in finally block."""
    self._active = False
    self._lock.release()

@property
def active(self) -> bool:
    return self._active
```

**Usage in OrchestratorService._process_one()** (M6 integration):
```python
# Before dispatching to DAGExecutor (in route_task and dispatch_workflow):
if not await self.concurrency_guard.acquire():
    # Re-enqueue message to mailbox with DEFERRED status
    self.mailbox.enqueue(message, priority="BACKGROUND")
    return ProcessResult.DEFERRED
try:
    result = await self.dag_executor.execute(...)
finally:
    self.concurrency_guard.release()  # MUST release in finally
```

Enforces single-DAG-at-a-time (V1, per ADR-1.1.5). DEFERRED messages re-enter mailbox at BACKGROUND priority (don't starve REALTIME).

**Anti-Hallucination Rules**:
- Use `asyncio.Lock` NOT `threading.Lock` -- Orchestrator is single-threaded async
- MUST release in finally -- unhandled exception during DAG must NOT permanently lock
- ConcurrencyGuard is NOT in the DAGGuard list -- it wraps the entry point, not the DAG walk
- DEFERRED messages re-enter at BACKGROUND priority (not REALTIME or INTERACTIVE)

**Done When**:
- [ ] File exists at `k1/orchestrator/orchestration/guards/concurrency_guard.py`
- [ ] Uses asyncio.Lock (not threading.Lock)
- [ ] acquire() is non-blocking (returns False immediately if locked)
- [ ] release() in finally block pattern documented
- [ ] active property for status checks
- [ ] V1: single-DAG-at-a-time enforced
- [ ] DEFERRED re-enqueue documented at BACKGROUND priority

---

### WT-3.2.10: (Optional) Extract SafetyBandReRead Guard — G10 Post-Wave

**Deliverable**: `k1/orchestrator/orchestration/guards/safety_band_guard.py` (optional extraction)

**Blocked By**: WT-3.2.0, WT-1.4.4 (IStateReadPort)

**Context Files**:
- [schema_whiteboard.md](docs/whiteboard/schema_whiteboard.md) (S8.1 line 1891 -- G10 SafetyBandReRead, post-wave, ORCH-07 invariant)
- [orchestrator-implementation-plan.md](docs/plans/orchestrator-implementation-plan.md) (lines 415-420 -- execute_wave step 1: safety band re-read inline)

**Specification**:
The schema whiteboard S8.1 lists G10 SafetyBandReRead as a post-wave guard. The plan implements safety band re-read inline in `DAGExecutor.execute_wave()` (2.2.2 step a: `band = await state_port.read("control.safety_band")` -- abort if RED/BLACK).

**Two valid approaches**:
1. **Keep inline** (plan approach): Safety band is read at the start of each wave in execute_wave(). Simpler, already implemented in M2.
2. **Extract to guard** (whiteboard approach): Create SafetyBandReRead guard in post-wave phase. Consistent with canonical pipeline ordering.

If extracting:
```python
class SafetyBandReRead(DAGGuard):
    def __init__(self, state_port: IStateReadPort):
        self.state_port = state_port

    async def after_wave(self, wave, results, ctx):
        band = await self.state_port.read("control.safety_band")
        level = band.data.get("level", "GREEN") if band else "GREEN"
        if level in ("RED", "BLACK"):
            return GuardDecision(HARD_STOP, f"safety band is {level}")
        ctx.safety_band = level  # update context for subsequent guards
        return GuardDecision(CONTINUE, f"safety band is {level}")
```

**Decision required**: Implementer should check if DAGExecutor.execute_wave() already reads safety band inline (from WT-2.2.2). If yes, either:
- Leave inline and skip this ticket
- Extract to guard and remove inline read

Both are acceptable. Document the choice.

**Done When**:
- [ ] Either: Guard extracted to dedicated file with IStateReadPort dependency
- [ ] Or: Decision documented to keep inline in execute_wave()
- [ ] Safety band RED/BLACK -> HARD_STOP
- [ ] Safety band GREEN/AMBER -> CONTINUE
- [ ] ORCH-07 invariant satisfied either way

---

## Dependency Summary

### Epic Build Order (within M3)

```
WT-3.2.0 (Guard base types)        -- first, all guards depend on this
    |
    +--- WT-3.2.9 (ConcurrencyGuard)    -- standalone (not a DAGGuard)
    |
    +--- WT-3.2.1 (OutputSchemaGuard)    -- stateless, no deps beyond base
    +--- WT-3.2.2 (ConditionalEdgeEval)  -- stateless, no deps beyond base
    +--- WT-3.2.4 (QualityGate)          -- stateless, no deps beyond base
    |
    +--- WT-3.2.3 (TokenBudgetTracker)   -- needs delta_port
    +--- WT-3.2.8 (CostBudgetGuard)      -- needs delta_port
    |
    +--- WT-3.2.6 (ExecutionMonitor)     -- needs delta_port + service_ref
    +--- WT-3.2.7 (SubStepObserver)      -- needs ExecutionMonitor + event_port
    |
    +--- WT-3.2.5 (MicroReplanCheckpoint)-- needs planner_port
    |
    +--- WT-3.2.10 (SafetyBandReRead)    -- optional, needs state_port

WT-3.1.1 (ConstraintResolver)       -- needs M1 ports + M1 types
    |
    +--- WT-3.1.2 (check_capabilities)   -- needs ConstraintResolver
    +--- WT-3.1.3 (find_alternatives)    -- needs check_capabilities
    +--- WT-3.1.4 (resolve_iteratively)  -- needs check_capabilities + find_alternatives
    +--- WT-3.1.5 (trigger_hil_fallback) -- needs resolve_iteratively
```

### Cross-Milestone Dependencies

| M3 Ticket | Depends on M1 | Depends on M2 | Notes |
|-----------|---------------|---------------|-------|
| WT-3.2.0 | WT-1.2.16 (CostAccumulator), WT-1.2.24 (guard types) | -- | Guard base types |
| WT-3.2.1 | WT-1.2.18 (PlanStep.output_schema), WT-1.2.5 (StepResult) | -- | Uses jsonschema library |
| WT-3.2.2 | WT-1.2.20 (ConditionExpr) | -- | Pure evaluator |
| WT-3.2.3 | WT-1.4.5 (IDeltaEmitPort) | WT-2.3.2 (StepResult.tokens_consumed includes retries) | Reads INV-1 token totals |
| WT-3.2.4 | WT-1.2.20 (QualityDecision) | WT-2.3.4 (quality retry integration) | Thresholds from policies |
| WT-3.2.5 | WT-1.4.3 (IPlannerPort), WT-1.2.8 (MicroReplanRequest) | WT-2.2.1 (build_waves for replacement) | WB S10.6 contract |
| WT-3.2.6 | WT-1.4.5 (IDeltaEmitPort), WT-1.2.19 (PendingHILContext) | WT-2.1.1 (OrchestratorService ref) | Circular dep via lazy init |
| WT-3.2.7 | WT-1.4.7 (IEventSubscriptionPort) | -- | Event subscriber, not guard |
| WT-3.2.8 | WT-1.2.16 (CostAccumulator), WT-1.4.5 (IDeltaEmitPort) | WT-2.3.6 (cost integration) | Mirrors token tracker |
| WT-3.2.9 | -- | WT-2.1.1 (OrchestratorService._process_one) | Uses asyncio.Lock |
| WT-3.2.10 | WT-1.4.4 (IStateReadPort) | WT-2.2.2 (execute_wave inline read) | Optional extraction |
| WT-3.1.1 | WT-1.2.3, WT-1.2.18, WT-1.2.20, WT-1.4.2, WT-1.4.5, WT-1.4.7 | -- | Orchestrates validation |
| WT-3.1.2 | WT-1.2.20 (CapabilityCheck, RegistryEntry) | -- | query_registry only |
| WT-3.1.3 | -- | -- | Scoring algorithm |
| WT-3.1.4 | WT-1.2.20 (ResolutionResult) | -- | 3-cycle state machine |
| WT-3.1.5 | WT-1.2.19 (PendingHILContext), WT-1.2.20 (HILRequest) | WT-2.1.1 (OrchestratorService.pending_hil) | Non-blocking HIL |

### Guard Construction Order (OrchestratorFactory step 12)

Per WB S8.5 (lines 1938-1960), factory wires guards in 3 phase-based lists:

```python
# Pre-wave guards (called before step dispatch):
pre_wave_guards = [
    ConditionalEdgeEvaluator(),          # G1 -- prune conditional edges
    TokenBudgetTracker(config),          # G2 -- check budget pre-wave
    CostBudgetGuard(config),             # G3 -- check cost pre-wave
]

# Post-step guards (called after each step completes):
post_step_guards = [
    OutputSchemaGuard(),                  # G4 -- schema validation FIRST
    QualityGate(config),                  # G5 -- quality check SECOND
    TokenBudgetTracker(config),           # G6 -- accumulate tokens THIRD
    CostBudgetGuard(config),             # G7 -- accumulate cost FOURTH
]

# Post-wave guards (called after wave completes):
post_wave_guards = [
    ExecutionMonitor(config, delta_port), # G8 -- progress emission
    MicroReplanCheckpoint(planner_port),  # G9 -- replan check
    SafetyBandReRead(state_port),         # G10 -- safety re-read LAST
]
```

**Note**: TokenBudgetTracker and CostBudgetGuard appear in BOTH pre-wave and post-step lists (they accumulate post-step and check thresholds pre-wave). This is the same instance -- factory passes the same object to both lists.
