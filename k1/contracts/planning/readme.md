# Planning Contracts

**Source ADRs:** ADR-0006, ADR-0006a-d

## Overview

This directory contains contracts for K1's Planner Agent, which implements a 4-stage planning pipeline: Sketch (LLM) → Expand (deterministic) → Validate (rules + arbiter) → Commit.

## Research Foundation

- **Planning Systems (Nau et al. 2004):** HTN (Hierarchical Task Network) planning
- **LLM-based Planning (Huang et al. 2022):** Language models for plan generation
- **Constraint Satisfaction:** Rule-based validation for plan correctness

## Contracts Included

### 1. Four-Stage Pipeline Contract (`four_stage_pipeline.yaml`)
- **Source:** ADR-0006a
- Stage 1: Sketch (LLM generates high-level plan)
- Stage 2: Expand (deterministic expansion to detailed steps)
- Stage 3: Validate (rule-based validation + arbiter approval)
- Stage 4: Commit (persist plan to SessionState)

### 2. LLM Sketch Contract (`llm_sketch.yaml`)
- **Source:** ADR-0006b
- LLM prompt format for plan sketching
- Output schema (YAML or JSON)
- Sketch quality criteria

### 3. Deterministic Expansion Contract (`deterministic_expansion.yaml`)
- **Source:** ADR-0006c
- Expansion rules (e.g., "search web" → [formulate_query, call_tool, parse_results])
- Tool schema integration
- Dependency resolution

### 4. Validation & Arbiter Contract (`validation_arbiter.yaml`)
- **Source:** ADR-0006d
- Rule-based validation (capability checks, privacy bands, constraints)
- Arbiter approval for RED band operations
- Fallback strategies on validation failure

## Four-Stage Planning Pipeline

```yaml
four_stage_pipeline:
  overview: |
    Hybrid LLM + deterministic planning:
    1. Sketch: LLM generates high-level plan (flexible, creative)
    2. Expand: Deterministic expansion to detailed steps (reliable)
    3. Validate: Rules + arbiter approval (safe, compliant)
    4. Commit: Persist plan to SessionState (traceable)

  performance_target:
    total_latency_p95_ms: 800
    stage1_sketch_ms: 400
    stage2_expand_ms: 100
    stage3_validate_ms: 200
    stage4_commit_ms: 100
```

### Stage 1: Sketch (LLM)

**Source:** ADR-0006a, ADR-0006b

```yaml
stage1_sketch:
  description: LLM generates high-level plan outline

  input:
    user_intent: string
    context: SessionState context
    available_tools: [ToolSchema]
    constraints: [Constraint]

  llm_config:
    model: gpt-4-turbo or equivalent
    temperature: 0.7
    max_tokens: 1000
    timeout_ms: 400

  prompt_template: |
    You are a planning agent. Generate a high-level plan to satisfy this user request:

    User Request: {{user_intent}}

    Available Context:
    {{context_summary}}

    Available Tools:
    {{tool_list}}

    Constraints:
    {{constraint_list}}

    Generate a YAML plan with steps. Each step should have:
    - action: The action to perform
    - tool: The tool to use (if applicable)
    - inputs: Required inputs
    - expected_output: What the step should produce

    Plan:

  output_schema:
    plan:
      steps:
        - step_id: string
          action: string
          tool: string | null
          inputs: [string]
          expected_output: string
          depends_on: [step_id]

  quality_criteria:
    - All required inputs available or derivable
    - Steps are logically ordered
    - Dependencies are acyclic (no circular deps)
    - Tools exist and are accessible

  failure_handling:
    - If LLM timeout: Use fallback template-based plan
    - If invalid YAML: Retry with corrected prompt
    - If no tools available: Generate information-gathering plan
```

### Stage 2: Expand (Deterministic)

**Source:** ADR-0006a, ADR-0006c

```yaml
stage2_expand:
  description: Expand high-level steps into detailed executable steps

  expansion_rules:
    # Example: "search web" expands to multiple steps
    search_web:
      pattern: "action == 'search_web'"
      expansion:
        - step_id: "{{original_step_id}}.1"
          action: formulate_search_query
          tool: null
          inputs: [user_query, context]

        - step_id: "{{original_step_id}}.2"
          action: call_search_tool
          tool: web_search
          inputs: [search_query]

        - step_id: "{{original_step_id}}.3"
          action: parse_search_results
          tool: null
          inputs: [search_results]

    # Example: "retrieve context" expands to K0 recall
    retrieve_context:
      pattern: "action == 'retrieve_context'"
      expansion:
        - step_id: "{{original_step_id}}.1"
          action: formulate_recall_query
          tool: null
          inputs: [user_intent]

        - step_id: "{{original_step_id}}.2"
          action: k0_recall
          tool: k0_bridge
          inputs: [recall_query]

  tool_schema_integration:
    description: Inject tool schemas into expanded steps

    for_each_step:
      if step.tool:
        tool_schema = ToolRegistry.get(step.tool)
        step.inputs = validate_and_complete_inputs(
          step.inputs,
          tool_schema.required_inputs
        )
        step.output_schema = tool_schema.output_schema

  dependency_resolution:
    description: Resolve data dependencies between steps
    algorithm: topological_sort

    validate:
      - No circular dependencies
      - All inputs are available or produced by prior steps
      - Execution order respects dependencies

  performance:
    latency_target_ms: 100
    max_expansion_depth: 3
    max_steps: 20
```

### Stage 3: Validate (Rules + Arbiter)

**Source:** ADR-0006a, ADR-0006d

```yaml
stage3_validate:
  description: Validate plan safety and compliance

  rule_based_validation:
    capability_checks:
      description: Ensure agent has required capabilities for each step
      validation:
        for_each_step:
          required_caps = step.tool.required_capabilities
          agent_caps = agent.capabilities
          if not (required_caps ⊆ agent_caps):
            raise ValidationError("Missing capability")

    privacy_band_checks:
      description: Check privacy band compliance
      validation:
        for_each_step:
          if step.privacy_band == PrivacyBand.RED:
            requires_arbiter_approval = true
          elif step.privacy_band == PrivacyBand.AMBER:
            requires_logging = true
          # GREEN requires no special handling

    constraint_checks:
      description: Validate plan constraints
      validations:
        - Step count <= max_steps (20)
        - Estimated duration <= task.deadline
        - All tools are available
        - No blacklisted tools
        - Resource requirements within limits

    dependency_checks:
      description: Validate dependencies
      validations:
        - No circular dependencies (DAG)
        - All inputs available or producible
        - Execution order is valid

  arbiter_approval:
    description: Human-in-the-loop approval for sensitive operations

    trigger_conditions:
      - Any step has privacy_band == RED
      - Plan modifies sensitive data
      - Plan performs irreversible operations

    approval_request:
      message_type: ArbiterApprovalRequest
      payload:
        plan: Plan
        sensitive_steps: [step_id]
        justification: string
        timeout_ms: 30000

    approval_response:
      message_type: ArbiterApprovalResponse
      payload:
        approved: boolean
        modified_plan: Plan | null
        rejection_reason: string | null

    timeout_handling:
      - If no response within 30s: reject plan
      - Alert: arbiter_approval_timeout{plan_id}

  fallback_strategies:
    validation_failure:
      - Log validation errors
      - Return errors to LLM for plan revision
      - Retry sketch stage with additional constraints
      - Max retries: 2

    arbiter_rejection:
      - Log rejection reason
      - Generate alternative plan without RED steps
      - Inform user of limitation
```

### Stage 4: Commit (Persist)

**Source:** ADR-0006a

```yaml
stage4_commit:
  description: Persist validated plan to SessionState

  storage:
    location: SessionState.beliefs.current_plan
    format: FlatBuffers PlanSchema

  plan_metadata:
    plan_id: string
    created_at: timestamp
    created_by: agent_id
    user_intent: string
    validated: boolean
    arbiter_approved: boolean
    estimated_duration_ms: integer
    step_count: integer

  persistence:
    write_to: K0 Bridge (P02)
    durability: synchronous_flush
    latency_target_ms: 100

  notifications:
    - Notify orchestrator: PlanReady
    - Log event: plan_committed{plan_id, step_count}
    - Metric: plan_generation_duration_ms{duration}
```

## Plan Schema

```yaml
plan_schema:
  plan_id: string
  user_intent: string
  steps:
    - step_id: string
      action: string
      tool: string | null
      inputs: object
      expected_output: string
      depends_on: [step_id]
      privacy_band: GREEN | AMBER | RED
      estimated_duration_ms: integer

  metadata:
    created_at: timestamp
    created_by: agent_id
    validated: boolean
    arbiter_approved: boolean
    total_estimated_duration_ms: integer
```

## LLM Sketch Quality

**Source:** ADR-0006b

```yaml
sketch_quality:
  completeness:
    - All required actions identified
    - Input sources specified
    - Dependencies captured

  feasibility:
    - All tools exist
    - All capabilities available
    - Constraints satisfied

  efficiency:
    - Minimal redundant steps
    - Parallelizable steps identified
    - Estimated duration reasonable

  scoring:
    formula: |
      quality_score = (
        completeness_score * 0.4 +
        feasibility_score * 0.4 +
        efficiency_score * 0.2
      )
    threshold: 0.7

    rejection:
      - If quality_score < 0.7: Retry sketch
      - Max retries: 2
      - Fallback: Template-based plan
```

## Performance Requirements

```yaml
performance:
  total_latency_p95_ms: 800
  total_latency_p99_ms: 1500

  stage_latencies:
    sketch_p95_ms: 400
    expand_p95_ms: 100
    validate_p95_ms: 200
    commit_p95_ms: 100

  throughput:
    plans_per_minute: 50

  success_rate:
    target: 95%
    validation_failure_rate: <5%
    arbiter_rejection_rate: <2%
```

## Observability

```yaml
observability:
  events:
    - plan_sketch_started{plan_id}
    - plan_sketch_completed{plan_id, step_count, duration_ms}
    - plan_expand_completed{plan_id, expanded_step_count}
    - plan_validation_started{plan_id}
    - plan_validation_completed{plan_id, result}
    - plan_validation_failed{plan_id, errors}
    - arbiter_approval_requested{plan_id}
    - arbiter_approval_received{plan_id, approved}
    - plan_committed{plan_id}

  metrics:
    - plan_generation_duration_ms{stage, percentile}
    - plan_step_count{percentile}
    - plan_validation_failure_total{reason}
    - arbiter_approval_rate
    - plan_success_rate

  alerts:
    - PlanGenerationSlow: p95 > 800ms for 5 min
    - PlanValidationFailureHigh: failure_rate > 5% for 5 min
    - ArbiterApprovalTimeoutHigh: timeout_rate > 10% for 5 min
```

## Testing Strategies

```yaml
planning_tests:
  unit_tests:
    - LLM sketch prompt formatting
    - Expansion rule application
    - Validation rule checking
    - Arbiter approval logic

  integration_tests:
    - Full 4-stage pipeline
    - Plan execution (orchestration)
    - Validation failure and retry
    - Arbiter approval flow

  llm_tests:
    - Sketch quality evaluation
    - Prompt robustness
    - Fallback to templates
```

## Usage Examples

```python
# Full planning pipeline
planner = PlannerAgent(agent_id="planner-1")

# Stage 1: Sketch
sketch = await planner.sketch(
    user_intent="Find information about quantum computing",
    context=session_context,
    available_tools=tool_registry.list()
)

# Stage 2: Expand
expanded_plan = await planner.expand(sketch)

# Stage 3: Validate
validation_result = await planner.validate(
    expanded_plan,
    agent_capabilities=agent.capabilities
)

if validation_result.requires_arbiter_approval:
    approval = await arbiter.request_approval(expanded_plan)
    if not approval.approved:
        raise PlanRejected(approval.reason)

# Stage 4: Commit
await planner.commit(expanded_plan, session_id)
```

## Related Contracts

- Orchestration: `../orchestration/`
- Agent Lifecycle: `../agent_lifecycle/`
- Tools: `../tools/`
- Security: `../security/arbiter.yaml`

---

**Last Updated:** 2025-10-13
