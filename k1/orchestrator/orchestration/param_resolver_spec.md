# ParamResolver -- Implementation Specification (4.5.9)

**Status**: SPEC READY -- implement when DAGExecutor is built
**Epic**: 4.5 Meta-Agent Creation
**Scope**: Orchestrator (NOT Fabric)
**Depends on**: `k1.fabric.types.CapabilityResult` (frozen dataclass)
**Consumed by**: DAGExecutor step resolution loop

---

## Purpose

ParamResolver resolves dynamic references (`$step_id.result.path`) in DAG step
definitions before handing them to Fabric for execution.  The existing behavior
resolves references in `params` dict values.  This spec adds resolution of the
`capability` field itself -- enabling the meta-agent creation pattern where
`build_agent` returns a dynamically created agent name that the next DAG step
must execute.

---

## Class: `ParamResolver`

```
File: k1/orchestrator/orchestration/param_resolver.py
```

### Constructor

```python
class ParamResolver:
    __slots__ = ("_registry",)

    def __init__(self, registry: RegistryPort) -> None:
        """
        Args:
            registry: Capability registry for existence checks.
                      Must implement contains(name: str) -> bool.
        """
        self._registry = registry
```

### Registry Port (Protocol)

```python
class RegistryPort(Protocol):
    def contains(self, name: str) -> bool: ...
```

Satisfied by `CapabilityRegistry` (k1.fabric.core.registry).  Use Protocol to
avoid circular imports between orchestrator and fabric.

---

## Method: `resolve_step`

```python
def resolve_step(
    self,
    step: dict[str, Any],
    completed_results: dict[str, CapabilityResult],
) -> dict[str, Any]:
```

### Input

| Field | Type | Description |
|-------|------|-------------|
| `step` | `dict` | DAG step definition. Must contain `"capability"` key. May contain `"params"` dict. |
| `completed_results` | `dict[str, CapabilityResult]` | Results from previously completed DAG steps, keyed by step_id. |

### Output

Returns a **shallow copy** of `step` with all `$`-references resolved.
Original `step` dict is NEVER mutated.

### Resolution Logic

#### 1. Param resolution (existing behavior)

For each value in `step["params"]`:
- If value is a string starting with `"$"`, resolve via `_resolve_reference(ref, completed_results)`
- Non-string values pass through unchanged
- Nested dicts are NOT recursed (flat params only)

#### 2. Capability resolution (NEW -- 4.5.9)

```python
capability = step.get("capability", "")
if capability.startswith("$"):
    resolved = self._resolve_reference(capability, completed_results)
    if not isinstance(resolved, str) or not resolved:
        raise UnresolvedCapabilityError(
            step_id=step.get("id", ""),
            capability_ref=capability,
            resolved_value=str(resolved),
        )
    if not self._registry.contains(resolved):
        raise UnresolvedCapabilityError(
            step_id=step.get("id", ""),
            capability_ref=capability,
            resolved_value=resolved,
        )
    resolved_step["capability"] = resolved
```

#### 3. Reference resolution helper

```python
def _resolve_reference(
    self,
    ref: str,
    completed_results: dict[str, CapabilityResult],
) -> Any:
    """
    Resolve $step_id.result.path.to.value references.

    Parse: "$step_1a.result.agent_name"
      -> step_id = "step_1a"
      -> path    = ["result", "agent_name"]

    Traversal:
      1. completed_results["step_1a"] -> CapabilityResult
      2. "result" is a keyword -> access CapabilityResult.data
      3. "agent_name" -> data["agent_name"]

    Raises:
        StepReferenceError: if step_id not in completed_results
        PathResolutionError: if path traversal fails
    """
```

**Path traversal rules:**
- First segment after `$` is the step_id
- `"result"` keyword maps to `CapabilityResult.data` (the dict)
- Subsequent segments are dict key lookups on `.data`
- If any segment fails, raise `PathResolutionError`

---

## Exceptions

### `UnresolvedCapabilityError`

```python
class UnresolvedCapabilityError(Exception):
    """Raised when a $-reference in capability field cannot be resolved."""

    def __init__(
        self,
        step_id: str,
        capability_ref: str,
        resolved_value: str,
    ) -> None:
        self.step_id = step_id
        self.capability_ref = capability_ref
        self.resolved_value = resolved_value
        super().__init__(
            f"Step '{step_id}': capability ref '{capability_ref}' "
            f"resolved to '{resolved_value}' which is not registered"
        )
```

### `StepReferenceError`

```python
class StepReferenceError(Exception):
    """Raised when a referenced step_id is not in completed_results."""
```

### `PathResolutionError`

```python
class PathResolutionError(Exception):
    """Raised when path traversal on CapabilityResult.data fails."""
```

---

## Meta-Agent Creation Pattern (end-to-end)

This is the primary use case driving 4.5.9:

```
DAG Plan (committed by Planner, executed by Orchestrator):

  step_1a:
    capability: "tool.write.build_agent"
    params:
      agent_name: "agent.execute.diabetes_companion"
      tools_granted: ["tool.execute.vitals_lookup", "tool.execute.glucose_history"]
      domain: ["health", "diabetes"]
      prompt_template: "diabetes_companion_v1"
      ephemeral: true

  step_2a:
    depends_on: [step_1a]
    capability: "$step_1a.result.agent_name"    # <-- DYNAMIC RESOLUTION
    params:
      query: "What is my latest blood sugar reading?"
      session_id: "sess-001"
```

**Execution flow:**
1. DAGExecutor executes `step_1a` -> Fabric executes `tool.write.build_agent`
2. BuildAgentHandler (4.5.2) validates, composes, registers agent
3. Returns `CapabilityResult.success_result(data={"agent_name": "agent.execute.diabetes_companion", "status": "registered"})`
4. DAGExecutor calls `ParamResolver.resolve_step(step_2a, {"step_1a": result})`
5. ParamResolver sees `capability: "$step_1a.result.agent_name"`
6. Resolves: `completed_results["step_1a"].data["agent_name"]` -> `"agent.execute.diabetes_companion"`
7. Checks `registry.contains("agent.execute.diabetes_companion")` -> True (registered in step 3)
8. Returns resolved step with `capability: "agent.execute.diabetes_companion"`
9. DAGExecutor sends to Fabric as standard `CapabilityRequest("agent.execute.diabetes_companion", params)`
10. Fabric resolves + executes via standard pipeline (AgentProvider 4.3.5)

---

## Fabric Contract Boundary

ParamResolver sits **before** the Fabric boundary:

```
Orchestrator                          |  Fabric
                                      |
DAGExecutor                           |
  -> ParamResolver.resolve_step()     |
  -> CapabilityRequest(resolved_name) --> Fabric.execute(request)
                                      |     -> Resolver -> Provider -> Result
```

Fabric NEVER sees `$`-references. It receives a fully resolved capability name
as a standard `CapabilityRequest`. This is by design (separation of concerns).

---

## Fabric Types Used

Import from `k1.fabric.types`:

```python
from k1.fabric.types import CapabilityResult
```

`CapabilityResult` fields used by ParamResolver:
- `.success: bool` -- check if referenced step succeeded
- `.data: Optional[Dict[str, Any]]` -- traverse path to extract values

---

## Test Scenarios (~20 tests)

### Param resolution (existing behavior)
1. Static params pass through unchanged
2. `$step_id.result.key` in params resolves correctly
3. Missing step_id in completed_results raises `StepReferenceError`
4. Missing key in data raises `PathResolutionError`
5. Non-string param values pass through unchanged
6. Multiple params with mixed static and dynamic refs

### Capability resolution (4.5.9 new)
7. Static capability passes through unchanged
8. `$step_id.result.agent_name` resolves to registered capability
9. Resolved capability NOT in registry raises `UnresolvedCapabilityError`
10. Referenced step not in completed_results raises `StepReferenceError`
11. Path traversal failure raises `PathResolutionError`
12. Resolved value is not a string raises `UnresolvedCapabilityError`
13. Resolved value is empty string raises `UnresolvedCapabilityError`
14. Deep path: `$step_id.result.nested.key` resolves correctly

### End-to-end pattern
15. build_agent -> execute created agent full flow
16. Multiple dynamic steps in sequence
17. Step dict is NOT mutated (immutability)
18. Failed step (success=False) referenced raises appropriate error

### Edge cases
19. Capability field missing from step dict -- no-op
20. Empty completed_results with no references -- pass through

---

## File Layout

```
k1/orchestrator/orchestration/
    param_resolver.py          # ParamResolver class + exceptions
    __init__.py                # re-export ParamResolver, exceptions

tests/k1/orchestrator/
    test_param_resolver_459.py # ~20 tests
```

---

## Thread Safety

ParamResolver is stateless (constructor-injected registry is thread-safe via
RLock from 2.2.1). `resolve_step()` creates new dicts per call. Safe for
concurrent use by DAGExecutor wave parallelism.

---

## References

- Epic 4.5.9 in `docs/plans/fabric-implementation-plan.md`
- `k1/orchestrator/orchestrator.mmd` line 111 (META-AGENT CREATION node)
- `k1/orchestrator/orchestrator.mmd` line 316 (DAGExecutor resolve_params)
- ADR-0005 (Agent Lifecycle)
- ADR-K004 (Capability Fabric Adaptation)
- PLAN-06: Planner NEVER executes writes. Orchestrator executes all steps.
