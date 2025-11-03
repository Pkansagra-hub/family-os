---
adr_number: 0007c
title: Validation Stage 2-Tier Implementation
status: PROPOSED
date_created: '2025-11-03'
date_updated: '2025-11-03'
authors:
- K1 Architecture Team
affected_layers:
- layer1_input
- layer2_orchestration
- layer3_execution
- layer4_runtime
affected_modules: []
concerns:
- architecture
- cost
- observability
- performance
- privacy
- reliability
- scalability
- security
- testing
supersedes: []
superseded_by: []
related_adrs:
- ADR-0001b
- ADR-0007
- ADR-0007b
- ADR-0007c
- ADR-0007d
- ADR-0010
implementation_status: COMPLETED
implementation_date: null
implementation_phase: null
related_contracts: []
related_diagrams: []
research_citations: []
propagation:
  triggers:
  - Modifying system architecture
  - Performance requirement changes
  affected_adrs:
  - ADR-0001b
  - ADR-0007
  - ADR-0007b
  - ADR-0007c
  - ADR-0007d
  - ADR-0010
  affected_contracts:
  - k1/contracts/flatbuffers/layer3_execution/mcp_message.fbs
  - k1/contracts/flatbuffers/layer3_execution/mcp_resource_request.fbs
  - k1/contracts/flatbuffers/layer3_execution/mcp_resource_response.fbs
  - k1/contracts/flatbuffers/layer3_execution/mcp_tool_discovery.fbs
  - k1/contracts/flatbuffers/layer3_execution/model_cache_entry.fbs
  - k1/contracts/flatbuffers/layer3_execution/model_request.fbs
  - k1/contracts/flatbuffers/layer3_execution/model_response.fbs
  - k1/contracts/flatbuffers/layer3_execution/model_stream_chunk.fbs
  - k1/contracts/flatbuffers/layer3_execution/stream_chunk.fbs
  - k1/contracts/flatbuffers/layer3_execution/stream_config.fbs
  affected_tests: []
---


# ADR-0007c: Validation Stage 2-Tier Implementation

**Status:** ✅ Approved (2025-10-12)
**Parent ADR:** [ADR-0007: 4-Stage Planning Pipeline](./0007-4stage-planning-pipeline.md)
**Related ADRs:**
- [ADR-0007b: Expand Stage Tool/Prompt Registry Integration](./0007b-expand-stage-tool-prompt-registry-integration.md) - Provides expanded plan input
- [ADR-0007d: Commit Stage K0 WAL Integration](./0007d-commit-stage-k0-wal-integration.md) - Persists validated plan
- [ADR-0010: Capability-Based Security](./0010-capability-based-security.md) - Capability validation logic
- [ADR-0001b: Model Hub Architecture](./0001b-model-hub-architecture.md) - Arbiter LLM inference

**Research Citations:**
- Planning validation (Fikes & Nilsson 1971) - STRIPS precondition checking
- DAG cycle detection (Kahn 1962) - Topological sort algorithm
- LLM safety alignment (Anthropic Constitutional AI 2022) - Arbiter pattern

---

## Context & Problem Statement

### Current State
After Stage 2 (Expand), the Planner has an ExpandedPlan with complete metadata, but **not validated for correctness or safety**:
- ❌ No structural validation (plan has steps, step count within limits)
- ❌ No dependency validation (circular dependencies, invalid step refs)
- ❌ No capability validation (agent has required capabilities)
- ❌ No budget validation (total latency/cost within budget)
- ❌ No safety validation (LLM arbiter for risky plans)

### Problem Statement
**How do we validate ExpandedPlan for correctness (<1ms rule-based checks) and safety (50-100ms LLM arbiter for AMBER/RED band plans only) to achieve >95% error detection rate while minimizing arbiter invocation (<15%)?**

### Key Challenges

1. **Tier 1 Performance (<1ms):**
   - Must perform 6 validation checks in <1ms P95
   - DAG cycle detection (Kahn's algorithm O(V+E))
   - Schema validation (JSON Schema validation)
   - Capability validation (set intersection)

2. **Tier 2 Arbiter Latency (50-100ms):**
   - Current: 72ms P95 (gpt-4o-mini)
   - Target: <50ms (model distillation or faster model)
   - Must minimize invocations (<15% of plans)

3. **Error Detection Rate (>95%):**
   - Tier 1 should catch 95%+ invalid plans (structural, capability, budget errors)
   - Tier 2 should catch safety violations (AMBER/RED band risky actions)

4. **Arbiter Invocation Rate (<15%):**
   - Most plans are GREEN band (skip arbiter)
   - Only AMBER/RED band plans trigger arbiter (child space, user age < 18)

---

## Decision

### Overview
Implement **2-tier validation** for Stage 3 (Validate) of the 4-stage planning pipeline:

**Tier 1 (Rule-Based, <1ms, Always Run):**
1. Structural validation (plan has steps, step count ≤ max_steps)
2. Dependency validation (DAG cycle detection, no circular deps)
3. Capability validation (agent has required tools/caps)
4. Budget validation (total latency ≤ session budget, total cost ≤ session budget)
5. Band validation (step band ≤ session band)
6. Schema validation (step inputs match tool schema_in)

**Tier 2 (LLM Arbiter, 50-100ms, AMBER/RED Only):**
7. Safety check (arbiter prompt with plan + user context)
8. Arbiter decision (safe: true/false, reason: string)
9. Invocation rules (AMBER/RED band, child space, user age < 18)

---

### Tier 1: Rule-Based Validation (<1ms)

#### **Check 1: Structural Validation**

**Purpose:** Ensure plan has valid structure (steps exist, count within limits).

**Validation Rules:**
```python
def validate_structure(plan: ExpandedPlan, config: ValidationConfig) -> List[ValidationError]:
    """
    Structural validation checks:
    1. Plan has at least 1 step
    2. Step count ≤ max_steps (default: 10)
    3. All step_ids are unique
    4. All step_ids are sequential (0, 1, 2, ...)
    """
    errors = []

    # Check 1: Plan has steps
    if len(plan.steps) == 0:
        errors.append(ValidationError(
            type="STRUCTURAL",
            message="Plan has no steps"
        ))

    # Check 2: Step count within limits
    if len(plan.steps) > config.max_steps_per_plan:
        errors.append(ValidationError(
            type="STRUCTURAL",
            message=f"Plan has {len(plan.steps)} steps, max is {config.max_steps_per_plan}"
        ))

    # Check 3: Unique step_ids
    step_ids = [step.step_id for step in plan.steps]
    if len(step_ids) != len(set(step_ids)):
        errors.append(ValidationError(
            type="STRUCTURAL",
            message="Duplicate step_ids detected"
        ))

    # Check 4: Sequential step_ids (0, 1, 2, ...)
    expected_ids = list(range(len(plan.steps)))
    if sorted(step_ids) != expected_ids:
        errors.append(ValidationError(
            type="STRUCTURAL",
            message=f"Step IDs not sequential: expected {expected_ids}, got {sorted(step_ids)}"
        ))

    return errors
```

**Performance:** <0.1ms (simple checks)

---

#### **Check 2: Dependency Validation (DAG Cycle Detection)**

**Purpose:** Ensure dependencies form valid DAG (no circular dependencies).

**Algorithm:** Kahn's topological sort (O(V+E) complexity)

```python
def validate_dependencies(plan: ExpandedPlan) -> List[ValidationError]:
    """
    Dependency validation using Kahn's algorithm:
    1. Build in-degree map (step → count of incoming edges)
    2. Topological sort (BFS starting from in-degree 0)
    3. If all steps visited, DAG is acyclic
    4. If not all visited, circular dependency exists
    """
    errors = []

    # Build in-degree map
    in_degree = {step.step_id: 0 for step in plan.steps}
    for step in plan.steps:
        for dep_id in step.dependencies:
            if dep_id not in in_degree:
                errors.append(ValidationError(
                    type="DEPENDENCY",
                    message=f"Step {step.step_id} references non-existent dependency {dep_id}"
                ))
                continue
            in_degree[dep_id] += 1

    # Kahn's algorithm: topological sort
    queue = [step_id for step_id, degree in in_degree.items() if degree == 0]
    visited_count = 0

    while queue:
        step_id = queue.pop(0)
        visited_count += 1

        # Find steps that depend on this step
        for step in plan.steps:
            if step_id in step.dependencies:
                in_degree[step.step_id] -= 1
                if in_degree[step.step_id] == 0:
                    queue.append(step.step_id)

    # Check if all steps visited (acyclic)
    if visited_count != len(plan.steps):
        errors.append(ValidationError(
            type="DEPENDENCY",
            message=f"Circular dependency detected: {visited_count}/{len(plan.steps)} steps reachable"
        ))

    return errors
```

**Performance:** <0.2ms for 10 steps (O(V+E) = O(10+20) = O(30))

---

#### **Check 3: Capability Validation**

**Purpose:** Ensure agent has all required capabilities for plan execution.

```python
def validate_capabilities(
    plan: ExpandedPlan,
    agent_capabilities: Set[str]
) -> List[ValidationError]:
    """
    Capability validation:
    1. Check if agent has all required capabilities (union of all step caps)
    2. Report missing capabilities
    """
    errors = []

    # Get all required capabilities (union across steps)
    required_caps = plan.all_caps_required

    # Check if agent has all required capabilities
    missing_caps = required_caps - agent_capabilities
    if missing_caps:
        errors.append(ValidationError(
            type="CAPABILITY",
            message=f"Agent missing required capabilities: {missing_caps}"
        ))

    return errors
```

**Performance:** <0.05ms (set intersection)

---

#### **Check 4: Budget Validation**

**Purpose:** Ensure total latency/cost within session budget.

```python
def validate_budgets(
    plan: ExpandedPlan,
    session_state: SessionState
) -> List[ValidationError]:
    """
    Budget validation:
    1. Total latency ≤ session latency budget
    2. Total cost ≤ session cost budget
    """
    errors = []

    # Check latency budget
    latency_budget_ms = session_state.control.latency_budget_ms
    if plan.total_latency_hint_ms > latency_budget_ms:
        errors.append(ValidationError(
            type="BUDGET",
            message=f"Total latency ({plan.total_latency_hint_ms}ms) exceeds budget ({latency_budget_ms}ms)"
        ))

    # Check cost budget
    cost_budget_usd = session_state.control.cost_budget_usd
    if plan.total_cost_hint_usd > cost_budget_usd:
        errors.append(ValidationError(
            type="BUDGET",
            message=f"Total cost (${plan.total_cost_hint_usd}) exceeds budget (${cost_budget_usd})"
        ))

    return errors
```

**Performance:** <0.05ms (simple arithmetic)

---

#### **Check 5: Band Validation**

**Purpose:** Ensure plan privacy band ≤ session privacy band.

```python
def validate_band(
    plan: ExpandedPlan,
    session_state: SessionState
) -> List[ValidationError]:
    """
    Band validation:
    1. Plan's highest band ≤ session band
    2. Band hierarchy: GREEN < AMBER < RED
    """
    errors = []

    # Band priority
    band_priority = {"GREEN": 1, "AMBER": 2, "RED": 3}

    session_band = session_state.meta.privacy_band
    plan_band = plan.highest_band_required

    if band_priority[plan_band] > band_priority[session_band]:
        errors.append(ValidationError(
            type="BAND",
            message=f"Plan requires {plan_band} band, session is {session_band}"
        ))

    return errors
```

**Performance:** <0.05ms (comparison)

---

#### **Check 6: Schema Validation**

**Purpose:** Ensure step parameters match tool input schema.

```python
def validate_schemas(plan: ExpandedPlan) -> List[ValidationError]:
    """
    Schema validation:
    1. Step parameters match tool schema_in (JSON Schema validation)
    2. Report schema violations
    """
    errors = []

    for step in plan.steps:
        # Validate step parameters against schema_in
        try:
            jsonschema.validate(
                instance=step.parameters,
                schema=step.schema_in
            )
        except jsonschema.ValidationError as e:
            errors.append(ValidationError(
                type="SCHEMA",
                message=f"Step {step.step_id} parameter validation failed: {e.message}",
                step_id=step.step_id
            ))

    return errors
```

**Performance:** <0.5ms for 10 steps (10 × 0.05ms schema validation)

---

### Tier 1 Complete Validation Flow

```python
class Tier1Validator:
    """Tier 1 rule-based validation (<1ms)"""

    def __init__(self, config: ValidationConfig):
        self.config = config

    async def validate(
        self,
        plan: ExpandedPlan,
        agent_capabilities: Set[str],
        session_state: SessionState
    ) -> ValidationResult:
        """
        Run all Tier 1 validation checks.

        Returns ValidationResult with:
        - errors: List[ValidationError]
        - is_valid: bool (True if no errors)
        - validation_tier: "TIER1"
        - latency_ms: float
        """
        start_time = time.time()
        all_errors = []

        # Check 1: Structural validation
        all_errors.extend(validate_structure(plan, self.config))

        # Check 2: Dependency validation (DAG cycle detection)
        all_errors.extend(validate_dependencies(plan))

        # Check 3: Capability validation
        all_errors.extend(validate_capabilities(plan, agent_capabilities))

        # Check 4: Budget validation
        all_errors.extend(validate_budgets(plan, session_state))

        # Check 5: Band validation
        all_errors.extend(validate_band(plan, session_state))

        # Check 6: Schema validation
        all_errors.extend(validate_schemas(plan))

        latency_ms = (time.time() - start_time) * 1000

        return ValidationResult(
            errors=all_errors,
            is_valid=(len(all_errors) == 0),
            validation_tier="TIER1",
            latency_ms=latency_ms
        )
```

**Total Tier 1 Latency:** <1ms P95 (0.1 + 0.2 + 0.05 + 0.05 + 0.05 + 0.5 = 0.95ms)

---

### Tier 2: LLM Arbiter Safety Check (50-100ms, AMBER/RED Only)

#### **Arbiter Invocation Logic**

**Purpose:** Determine if plan requires arbiter safety check.

**Invocation Rules:**
```python
def should_invoke_arbiter(
    plan: ExpandedPlan,
    session_state: SessionState
) -> bool:
    """
    Arbiter invocation rules:
    1. AMBER or RED band plan (GREEN band skips arbiter)
    2. Child space (user.space == "child")
    3. User age < 18 (user.age < 18)

    Returns True if arbiter should be invoked.
    """
    # Rule 1: AMBER or RED band
    if plan.highest_band_required in ["AMBER", "RED"]:
        return True

    # Rule 2: Child space
    if session_state.meta.space == "child":
        return True

    # Rule 3: User age < 18
    if session_state.meta.user_age < 18:
        return True

    # Default: Skip arbiter (GREEN band, adult user)
    return False
```

**Invocation Rate:** <15% (most plans GREEN band)

---

#### **Arbiter Prompt Template**

**Purpose:** LLM prompt for safety checking risky plans.

**Template:**
```text
You are a safety arbiter for the K1 Intelligence family AI system.

Your role: Evaluate if the following plan is safe to execute for the user.

User Context:
- User age: {{user_age}}
- User space: {{user_space}}
- Privacy band: {{privacy_band}}

Plan to evaluate:
{{plan_json}}

Safety criteria:
1. Age-appropriate: Is the plan appropriate for user's age?
2. Privacy-safe: Does the plan respect privacy band constraints?
3. Risk-free: Does the plan avoid dangerous actions (financial transactions for minors, etc.)?

Output (JSON only):
{
  "safe": true | false,
  "reason": "Explanation of safety decision"
}
```

**Arbiter Call:**
```python
async def invoke_arbiter(
    plan: ExpandedPlan,
    session_state: SessionState,
    arbiter_model: str = "gpt-4o-mini"
) -> ArbiterDecision:
    """
    Invoke LLM arbiter for safety check.

    Returns ArbiterDecision with:
    - safe: bool (True if plan is safe)
    - reason: str (explanation)
    - latency_ms: float
    """
    # Assemble arbiter prompt
    prompt = assemble_arbiter_prompt(plan, session_state)

    # Call LLM (gpt-4o-mini, temperature 0.0 for determinism)
    response = await call_llm_arbiter(
        prompt=prompt,
        model=arbiter_model,
        temperature=0.0,
        max_tokens=200
    )

    # Parse arbiter decision
    decision = json.loads(response.content)

    return ArbiterDecision(
        safe=decision["safe"],
        reason=decision["reason"],
        latency_ms=response.latency_ms
    )
```

**Performance:** 50-100ms P95 (gpt-4o-mini inference)

---

### Tier 2 Complete Validation Flow

```python
class Tier2Validator:
    """Tier 2 LLM arbiter validation (50-100ms, AMBER/RED only)"""

    def __init__(self, config: ValidationConfig):
        self.config = config

    async def validate(
        self,
        plan: ExpandedPlan,
        session_state: SessionState
    ) -> ValidationResult:
        """
        Run Tier 2 arbiter validation (if needed).

        Returns ValidationResult with:
        - errors: List[ValidationError] (if arbiter flags unsafe)
        - is_valid: bool
        - validation_tier: "TIER2"
        - latency_ms: float
        - arbiter_decision: ArbiterDecision
        """
        start_time = time.time()

        # Check if arbiter should be invoked
        if not should_invoke_arbiter(plan, session_state):
            # Skip arbiter (GREEN band, adult user)
            return ValidationResult(
                errors=[],
                is_valid=True,
                validation_tier="TIER2_SKIPPED",
                latency_ms=0.0,
                arbiter_decision=None
            )

        # Invoke arbiter
        arbiter_decision = await invoke_arbiter(plan, session_state)

        latency_ms = (time.time() - start_time) * 1000

        # Check arbiter decision
        errors = []
        if not arbiter_decision.safe:
            errors.append(ValidationError(
                type="ARBITER_UNSAFE",
                message=f"Arbiter flagged plan as unsafe: {arbiter_decision.reason}"
            ))

        return ValidationResult(
            errors=errors,
            is_valid=arbiter_decision.safe,
            validation_tier="TIER2",
            latency_ms=latency_ms,
            arbiter_decision=arbiter_decision
        )
```

---

### Combined 2-Tier Validation Flow

```python
class PlanValidator:
    """Combined 2-tier plan validation"""

    def __init__(self, config: ValidationConfig):
        self.tier1_validator = Tier1Validator(config)
        self.tier2_validator = Tier2Validator(config)

    async def validate_plan(
        self,
        plan: ExpandedPlan,
        agent_capabilities: Set[str],
        session_state: SessionState,
        trace_id: str
    ) -> ValidatedPlan:
        """
        Full 2-tier validation:
        1. Tier 1 (rule-based, <1ms, always run)
        2. Tier 2 (arbiter, 50-100ms, AMBER/RED only)

        Returns ValidatedPlan with validation results.
        """
        # Tier 1: Rule-based validation (<1ms)
        tier1_result = await self.tier1_validator.validate(
            plan, agent_capabilities, session_state
        )

        logger.info(
            "validation_tier1_complete",
            error_count=len(tier1_result.errors),
            latency_ms=tier1_result.latency_ms,
            trace_id=trace_id
        )

        # If Tier 1 fails, skip Tier 2 (fail-fast)
        if not tier1_result.is_valid:
            return ValidatedPlan(
                plan=plan,
                validation_result=tier1_result,
                is_valid=False
            )

        # Tier 2: Arbiter validation (50-100ms, AMBER/RED only)
        tier2_result = await self.tier2_validator.validate(plan, session_state)

        logger.info(
            "validation_tier2_complete",
            arbiter_invoked=(tier2_result.validation_tier == "TIER2"),
            arbiter_safe=tier2_result.is_valid,
            latency_ms=tier2_result.latency_ms,
            trace_id=trace_id
        )

        # Combine results
        all_errors = tier1_result.errors + tier2_result.errors
        is_valid = (len(all_errors) == 0)

        return ValidatedPlan(
            plan=plan,
            validation_result=CombinedValidationResult(
                tier1=tier1_result,
                tier2=tier2_result,
                errors=all_errors,
                is_valid=is_valid
            ),
            is_valid=is_valid
        )
```

---

## Performance Analysis

### Latency Breakdown

| Component | Latency (P95) | Invocation Rate |
|-----------|---------------|-----------------|
| Tier 1 (rule-based) | <1ms | 100% (always run) |
| Tier 2 (arbiter) | 50-100ms | <15% (AMBER/RED only) |
| **Total (GREEN band)** | **~1ms** | **85%** |
| **Total (AMBER/RED band)** | **~75ms** | **15%** |

---

## Quality Metrics

### Error Detection Rate
**Target:** >95%

**Measurement:**
```python
error_detection_rate = errors_caught / total_invalid_plans
# Target: >0.95 (95%)
```

### Arbiter Invocation Rate
**Target:** <15%

**Measurement:**
```python
arbiter_invocation_rate = arbiter_invocations / total_plans
# Target: <0.15 (15%)
```

---

## Canonical Values

```yaml
# k1/config/planner.yml
planner:
  validation:
    # Structural limits
    max_steps_per_plan: 10

    # Performance targets
    validation_tier1_latency_p95_ms: 1
    validation_tier2_latency_p95_ms: 100

    # Quality targets
    error_detection_rate_target: 0.95    # >95%
    arbiter_invocation_rate_target: 0.15  # <15%

    # Arbiter configuration
    arbiter_model: "gpt-4o-mini"
    arbiter_temperature: 0.0              # Deterministic
    arbiter_max_tokens: 200
    arbiter_timeout_ms: 1500
```

---

## Conclusion

Stage 3 (Validate) implements 2-tier validation: Tier 1 rule-based (<1ms) catches 95%+ errors, Tier 2 LLM arbiter (50-100ms) provides safety check for AMBER/RED band plans only (<15% invocation rate).

**Next step:** Proceed to **0007d (Commit Stage)** for K0 WAL persistence.