# K1 POC - THE GREAT REFACTOR: MILESTONE EPIC ISSUES PLAN

## EXECUTIVE SUMMARY
**Current State:** 68% complete, 32% gap, 17 critical issues, 18-20 hours of work
**Target State:** 100% complete, zero duplication, single authoritative paths, clean kernel/demo boundary

---

## EPIC 0: FOUNDATION - SINGLE SOURCE OF TRUTH (4 hours)

### Issue 0.1: Create Kernel Bootstrap API
**File:** `poc/k1_poc/kernel/bootstrap.py` (NEW)
```python
"""Kernel bootstrap API - independent of demo concerns."""

from dataclasses import dataclass
from typing import Optional, Protocol

@dataclass
class KernelConfig:
    ordered_bus: bool = True
    adapter_mode: str = "gemini"  # or "test"
    feature_flags: dict = None

class KernelRuntime:
    """Runtime handle containing all kernel components."""
    bus: Any
    router: Any
    fsm: Any
    session_state: Any
    front_dispatcher: Any
    back_dispatcher: Any
    model: Any

async def start_kernel(config: KernelConfig) -> KernelRuntime:
    """Start kernel with given config - owns ALL composition."""

async def stop_kernel(runtime: KernelRuntime) -> None:
    """Gracefully shutdown kernel."""
```

**Acceptance:**
- [ ] Kernel starts without importing `demo/` modules
- [ ] Single command: `python -m poc.k1_poc.kernel.runner`
- [ ] Demo imports kernel, not vice versa

### Issue 0.2: Enforce Kernel/Demo Boundary
**Files:**
- `poc/k1_poc/kernel/__init__.py` - Public API only
- `poc/k1_poc/demo/coordinator.py` - Rewrite to use kernel API
- `tests/boundary/test_imports.py` - NEW boundary tests

**Acceptance:**
- [ ] No kernel module imports from `demo/`
- [ ] Demo coordinator delegates to `start_kernel()`
- [ ] CI fails if boundary violated

---

## EPIC 1: DELTA - ONE PIPELINE TO RULE THEM ALL (4 hours)

### Issue 1.1: Delete FSM Delta Duplicate
**File:** `poc/k1_poc/fsm/delta_aggregator.py` (DELETE)

**Action:** Remove entire file. FSM should use `delta/aggregator.py`.

### Issue 1.2: Wire Delta End-to-End
**File:** `poc/k1_poc/kernel/bootstrap.py` (modify)
```python
# In bootstrap phase 5:
from poc.k1_poc.delta.aggregator import DeltaAggregator
from poc.k1_poc.delta.applicator import DeltaApplicator

# Create applicator connected to session state
applicator = DeltaApplicator(
    session_state=runtime.session_state,
    mutation_guard=runtime.session_state._guard  # if accessible
)

# Create aggregator with applicator as flush target
aggregator = DeltaAggregator(
    flush_fn=applicator.apply_batch,
    batch_window_ms=500
)

# Store in runtime
runtime.delta_aggregator = aggregator
runtime.delta_applicator = applicator
```

**File:** `poc/k1_poc/actors/back.py` (modify)
```python
# After capability invoke, if artifact_type:
if result.get("artifact_type"):
    from poc.k1_poc.delta.emitters import emit_artifact_created
    await emit_artifact_created(
        task_id=task_id,
        artifact_type=result["artifact_type"],
        data=result.get("data", {}),
        parent_delta_id=get_current_parent_delta()
    )
```

**Acceptance:**
- [ ] Only one delta aggregator exists (`delta/aggregator.py`)
- [ ] Back handler emits deltas for artifacts
- [ ] Deltas are applied to SessionState
- [ ] `k1.session.state.updated.v1` events emitted

### Issue 1.3: Add parent_delta_id to Emitters
**File:** `poc/k1_poc/delta/emitters.py` (modify)
```python
def emit_task_state(task_id: str, state: str, parent_delta_id: Optional[str] = None):
    delta = SessionDelta(
        section="task_state",
        op="set",
        data={"task_id": task_id, "state": state},
        parent_delta_id=parent_delta_id or get_current_parent_delta()  # FIX
    )
    # ... rest
```

**Acceptance:**
- [ ] All delta emissions include `parent_delta_id`
- [ ] Causal chains preserved in aggregation

---

## EPIC 2: PROTOCOLS - AUTHORITATIVE MANAGERS (4 hours)

### Issue 2.1: Make Cancellation Manager Source of Truth
**File:** `poc/k1_poc/fsm/controller.py` (modify)
```python
# Remove internal cancellation logic
- self._cancellation_requested = False
- self._check_cancellation()

# Instead use protocol manager
from poc.k1_poc.protocols.cancellation import CancellationManager

self.cancellation_manager = CancellationManager()

def _on_cancel_request(self, envelope):
    self.cancellation_manager.request_cancel(task_id)
    # ... rest
```

**File:** `poc/k1_poc/protocols/cancellation.py` (enhance)
```python
class CancellationManager:
    """SINGLE source of truth for cancellation."""
    def __init__(self):
        self._cancelled_tasks: Set[str] = set()

    def request_cancel(self, task_id: str):
        self._cancelled_tasks.add(task_id)
        # Emit cancel event

    def is_cancelled(self, task_id: str) -> bool:
        return task_id in self._cancelled_tasks

    def check_iteration(self, task_id: str) -> bool:
        """Called by react_loop each iteration."""
        if self.is_cancelled(task_id):
            self._cancelled_tasks.remove(task_id)
            return True
        return False
```

### Issue 2.2: Make Suspension Manager Source of Truth
**File:** `poc/k1_poc/fsm/controller.py` (modify)
```python
# Remove internal suspension tracking
- self._suspended_context = {}
- self._suspension_timeout = {}

# Instead use protocol manager
from poc.k1_poc.protocols.suspension import SuspensionManager

self.suspension_manager = SuspensionManager(timeout_seconds=60)
```

**File:** `poc/k1_poc/protocols/suspension_manager.py` (enhance)
```python
class SuspensionManager:
    """SINGLE source of truth for HITL suspensions."""
    def __init__(self, timeout_seconds=60):
        self._suspended: Dict[str, SuspensionContext] = {}
        self.timeout = timeout_seconds

    async def suspend(self, task_id: str, context: dict):
        self._suspended[task_id] = SuspensionContext(
            task_id=task_id,
            context=context,
            expires_at=time.time() + self.timeout
        )
        # Emit suspended event

    async def resume(self, task_id: str, response: dict) -> Optional[dict]:
        if task_id not in self._suspended:
            return None
        context = self._suspended.pop(task_id)
        # Emit resume event
        return context.context
```

### Issue 2.3: Delete FSM Weave Batcher
**File:** `poc/k1_poc/fsm/weave_batcher.py` (DELETE)

**File:** `poc/k1_poc/protocols/weave_batcher.py` (enhance)
```python
class WeaveBatcher:
    """SINGLE source of truth for weave batching."""
    def __init__(self, batch_window_ms=500):
        self.window_ms = batch_window_ms
        self._pending: List[Envelope] = []
        self._timer: Optional[asyncio.TimerHandle] = None

    async def add_result(self, envelope: Envelope):
        self._pending.append(envelope)
        if not self._timer:
            loop = asyncio.get_event_loop()
            self._timer = loop.call_later(
                self.window_ms / 1000,
                self._flush
            )

    async def _flush(self):
        if self._pending:
            batch = WeaveBatch(envelopes=self._pending)
            await self._emit_weave(batch)
            self._pending = []
        self._timer = None
```

**Acceptance:**
- [ ] Only one weave batcher exists (`protocols/weave_batcher.py`)
- [ ] FSM uses protocol managers for cancel/suspend/weave
- [ ] No cancellation/suspension logic in FSM internals

---

## EPIC 3: FSM - ONE AUTHORITATIVE PATH (3 hours)

### Issue 3.1: Implement Real Phase 1
**File:** `poc/k1_poc/fsm/controller.py` (modify)
```python
async def _run_phase1(self, envelope: Envelope):
    """REAL Phase 1 - not placeholder."""
    from poc.k1_poc.fsm.phase1 import Phase1Processor

    # Create processor and run
    processor = Phase1Processor(self.session_state)
    result = await processor.process(envelope)

    # Write results to session state
    self.session_state.get_section("scoreboard").update(result.scoreboard)
    self.session_state.get_section("affective_now").update(result.affect)
    self.session_state.get_section("control").update(result.control)

    # Transition to DISPATCHING
    self._transition(ConciergeState.DISPATCHING, TOPIC_PHASE1_COMPLETE, envelope)
```

**File:** `poc/k1_poc/fsm/phase1.py` (implement if not exists)
```python
class Phase1Processor:
    """Deterministic pre-LLM processing."""

    async def process(self, envelope: Envelope) -> Phase1Result:
        # Intent classification
        # Entity extraction
        # Safety assessment
        # Emotion classification
        # Domain detection

        return Phase1Result(
            scoreboard={...},
            affect={...},
            control={...}
        )
```

### Issue 3.2: Delete Unused FSM Utilities
**Files to DELETE:**
- `poc/k1_poc/fsm/history_writer.py` (FSM controller already does this)
- `poc/k1_poc/fsm/task_bridge.py` (not used)
- `poc/k1_poc/fsm/control_extension.py` (not used)

**Acceptance:**
- [ ] Phase 1 actually does classification, not just transition
- [ ] FSM folder contains only used files
- [ ] Controller is the ONE source of truth for FSM logic

---

## EPIC 4: LLM - VALIDATION & STREAMING (4 hours)

### Issue 4.1: Implement Output Validator
**File:** `poc/k1_poc/llm/validator.py` (NEW)
```python
"""LLM Output Validator - guardrails against hallucinations."""

from dataclasses import dataclass
from typing import List, Optional

class LLMOutputValidator:
    """Validate LLM outputs before accepting them."""

    def __init__(self, tool_schemas: dict):
        self.tool_schemas = tool_schemas

    def validate(self, response: ModelResponse) -> ValidationResult:
        """Validate tool calls, params, ordering."""
        issues = []

        # Check acknowledge first for front
        if response.actor == "front":
            if not self._first_tool_is_acknowledge(response):
                issues.append("First tool must be acknowledge()")

        # Check tools in allowlist
        for tool in response.tool_calls:
            if tool.name not in self.tool_schemas:
                issues.append(f"Tool {tool.name} not in allowlist")

        # Check required params
        for tool in response.tool_calls:
            schema = self.tool_schemas.get(tool.name, {})
            required = schema.get("required", [])
            for param in required:
                if param not in tool.arguments:
                    issues.append(f"Missing required param: {param}")

        # Check param types
        # ...

        return ValidationResult(
            valid=len(issues) == 0,
            issues=issues,
            fixed_response=self._attempt_fix(response) if issues else response
        )

    def _attempt_fix(self, response) -> Optional[ModelResponse]:
        """Try one fix with lower temperature."""
        # If validation fails, retry with corrective prompt
        # and lower temperature
```

**File:** `poc/k1_poc/actors/front.py` (modify)
```python
# In front_handler, before react_loop:
from poc.k1_poc.llm.validator import LLMOutputValidator

validator = LLMOutputValidator(FRONT_TOOL_SCHEMAS)

# After model.generate, before using response:
validation = validator.validate(response)
if not validation.valid:
    if validation.fixed_response:
        response = validation.fixed_response
    else:
        # Fallback to safe response
        response = create_safe_fallback_response()
```

### Issue 4.2: Enable Streaming Path
**File:** `poc/k1_poc/actors/front.py` (modify)
```python
async def front_handler(envelope, model, ...):
    # ... existing code ...

    # For ack/final, use streaming if available
    if prompt_mode in ["STANDARD", "PRESENT"]:
        # Use streaming for better UX
        async for chunk in model.generate_stream(request):
            if chunk.is_final:
                await emit_response(chunk.text)
            else:
                await emit_stream_chunk(chunk.text)
    else:
        # Use non-streaming for other modes
        response = await model.generate(request)
        # ... process response
```

**Acceptance:**
- [ ] All LLM outputs validated before acceptance
- [ ] Invalid outputs are fixed or rejected
- [ ] Streaming works for Front responses
- [ ] Model selection matches design doc or doc is updated

---

## EPIC 5: SESSION STATE - CANONICAL SECTIONS (2 hours)

### Issue 5.1: Fix Memory Preload Section
**File:** `poc/k1_poc/demo/coordinator.py` (modify)
```python
# In phase3, replace:
- beliefs_section = self.session_state.get_section("beliefs")
+ beliefs_section = self.session_state.get_section("beliefs_active")

if beliefs_section:
    beliefs_section.set("preloaded_memories", self._preloaded_memories)
```

**File:** `poc/k1_poc/demo/preloaded_memories.py` (NEW)
```python
"""Canonical preloaded memories for demo."""

PRELOADED_MEMORIES = [
    {
        "type": "episodic",
        "content": "Last week Riley forgot her swim bag...",
        "tags": ["riley", "swim", "forget"],
        "timestamp": "2026-02-15"
    },
    # ... move from smith_family.py
]
```

### Issue 5.2: Audit All Section References
**Files to scan and fix:**
- `poc/k1_poc/actors/front.py` - check all `get_section()` calls
- `poc/k1_poc/actors/back.py` - check all `get_section()` calls
- `poc/k1_poc/fsm/controller.py` - check all `get_section()` calls
- `poc/k1_poc/prompt/builder.py` - check all section reads

**Acceptance:**
- [ ] No code uses non-canonical section names
- [ ] All section names match SessionState schema
- [ ] Preloaded memories actually load into SessionState

---

## EPIC 6: ORCHESTRATOR - SINGLE ROUTING PATH (2 hours)

### Issue 6.1: Make route_task Authoritative
**File:** `poc/k1_poc/orchestrator/routing.py` (enhance)
```python
async def route_task(task: TaskDispatch, runtime: KernelRuntime) -> TaskResult:
    """SINGLE routing authority for all tasks."""

    # Determine tier
    tier = determine_tier(task)

    if tier == "LOW":
        # Direct worker path
        return await route_low(task, runtime)
    elif tier == "MEDIUM":
        # Stub orchestrator path
        return await route_medium(task, runtime)
    elif tier == "HIGH":
        # Future planner path - return not implemented
        return TaskResult(
            task_id=task.task_id,
            status="error",
            error="HIGH tier not implemented"
        )
```

**File:** `poc/k1_poc/actors/back.py` (modify)
```python
# Replace direct capability invocation with:
from poc.k1_poc.orchestrator.routing import route_task

result = await route_task(task_dispatch, runtime)
```

**Acceptance:**
- [ ] All task routing goes through `route_task()`
- [ ] LOW/MEDIUM/HIGH tiers handled consistently
- [ ] No direct capability invocation outside orchestrator

---

## EPIC 7: TASK - ONE AUTHORITATIVE PATH (1 hour)

### Issue 7.1: Delete Unused Task Abstractions
**Files to DELETE:**
- `poc/k1_poc/task/bundled_executor.py` (not used)
- `poc/k1_poc/task/dependency_queue.py` (not used)
- `poc/k1_poc/task/parallel_safety.py` (not used)
- `poc/k1_poc/task/receiver.py` (not used)

**File:** `poc/k1_poc/task/dispatch.py` (keep as source of truth)
- `TaskDispatch` dataclass
- `TaskComplete` dataclass
- `TaskFailed` dataclass
- `envelope_bridge.py` (keep)

**Acceptance:**
- [ ] Task folder contains only used files
- [ ] Core dataclasses are the ONE source of truth

---

## EPIC 8: BUS - ORDERED BY DEFAULT (2 minutes + tests)

### Issue 8.1: Enable Ordered Bus
**File:** `poc/k1_poc/kernel/bootstrap.py` (modify)
```python
# In bootstrap, when calling boot():
infra = boot(ordered=True)  # WAS: ordered=False
```

**File:** `poc/k1_poc/main.py` (modify)
```python
def boot(ordered: bool = True):  # Default to True
    # ...
```

**Acceptance:**
- [ ] Bus uses TimingChain by default
- [ ] Causal ordering enforced
- [ ] Tests pass with ordered=True

---

## EPIC 9: FABRIC - CONSISTENT CONTRACTS (1 hour)

### Issue 9.1: Fix Discover Callback
**File:** `poc/k1_poc/demo/coordinator.py` (modify)
```python
async def _capability_discover(self, intent, domain=None, constraints=None):
    result = await self.capability_registry.discover(intent, domain, constraints)
    matches = result.get("capabilities", [])  # WAS: result.get("matches", [])
    return matches
```

### Issue 9.2: Normalize Success/Status Contract
**File:** `poc/k1_poc/fabric/capability_registry.py` (modify)
```python
# All handlers return:
return {
    "success": True,  # USE THIS EVERYWHERE
    "data": {...},
    "artifact_type": "booking"  # if applicable
}
```

**File:** `poc/k1_poc/demo/coordinator.py` (modify)
```python
async def _capability_invoke(self, name, params, session_id=None):
    result = await self.capability_registry.invoke(name, params, session_id)
    # Check 'success' not 'status'
    success = result.get("success", False)
    return result
```

**Acceptance:**
- [ ] All fabric returns use `success` field
- [ ] No code checks `status` field
- [ ] Discover returns `capabilities` not `matches`

---

## EPIC 10: DEMO - CLEAN ADAPTER (1 hour)

### Issue 10.1: Demo Uses Kernel API
**File:** `poc/k1_poc/demo/coordinator.py` (REWRITE)
```python
class K1DemoCoordinator:
    """Demo coordinator - thin adapter on kernel."""

    async def initialize_system(self):
        # Call kernel bootstrap
        from poc.k1_poc.kernel.bootstrap import start_kernel

        config = KernelConfig(
            ordered_bus=True,
            adapter_mode="test" if self._test_mode else "gemini"
        )
        self.kernel = await start_kernel(config)

        # Attach demo concerns
        self._attach_demo_data()
        self._attach_output_channel()
        self._attach_iot_stubs()

    def _attach_demo_data(self):
        # Load Smith family into kernel session state
        beliefs = self.kernel.session_state.get_section("beliefs_active")
        beliefs.set("family_profile", SMITH_FAMILY_PROFILE)
        beliefs.set("preloaded_memories", PRELOADED_MEMORIES)
```

**Acceptance:**
- [ ] Demo coordinator uses kernel API, not duplicating composition
- [ ] All demo data lives in `demo/` folder
- [ ] Kernel runs without demo imports

---

## EPIC 11: DOCS - MATCH REALITY (1 hour)

### Issue 11.1: Update Design Docs
**File:** `docs/concierge_poc_design_v2.md` (update)
- Change `k1.capability` to `k1.tool` throughout
- Add note about mailbox-mediated Front ingestion
- Update model selection table to match code
- Add streaming section (when implemented)

### Issue 11.2: Update README
**File:** `poc/k1_poc/README.md` (update)
- Document kernel standalone command
- Document demo command
- Document architecture decisions
- List authoritative paths

**Acceptance:**
- [ ] Docs match code
- [ ] No outdated examples
- [ ] Clear separation of kernel vs demo

---

## EPIC 12: TESTS - VERIFY ALL THE THINGS (2 hours)

### Issue 12.1: Boundary Tests
**File:** `tests/boundary/test_imports.py`
```python
def test_kernel_does_not_import_demo():
    """Kernel should never import demo modules."""
    import poc.k1_poc.kernel.bootstrap
    import sys
    demo_modules = [m for m in sys.modules if 'demo' in m]
    assert len(demo_modules) == 0
```

### Issue 12.2: Authority Tests
**File:** `tests/authority/test_single_implementations.py`
```python
def test_only_one_delta_aggregator():
    """There should be only one delta aggregator."""
    import poc.k1_poc.delta.aggregator
    with pytest.raises(ImportError):
        import poc.k1_poc.fsm.delta_aggregator

def test_only_one_weave_batcher():
    """There should be only one weave batcher."""
    import poc.k1_poc.protocols.weave_batcher
    with pytest.raises(ImportError):
        import poc.k1_poc.fsm.weave_batcher
```

### Issue 12.3: Integration Tests
**File:** `tests/integration/test_full_turn.py`
```python
async def test_full_turn_with_all_components():
    """Test one full turn with all components wired."""
    kernel = await start_kernel(KernelConfig())

    # Send user input
    await publish_user_input("What's my schedule?")

    # Verify ack received
    ack = await wait_for_ack()
    assert ack is not None

    # Verify final response
    final = await wait_for_final()
    assert final is not None

    # Verify delta written
    assert kernel.session_state.get_section("history_active").size() > 0
```

**Acceptance:**
- [ ] All boundary tests pass
- [ ] All authority tests pass
- [ ] Integration tests cover full path

---

## EXECUTION SUMMARY

| Epic | Hours | Files Changed | Files Deleted |
|------|-------|---------------|---------------|
| 0: Kernel Bootstrap | 4 | 3 | 0 |
| 1: Delta | 4 | 4 | 1 |
| 2: Protocols | 4 | 5 | 1 |
| 3: FSM | 3 | 3 | 3 |
| 4: LLM | 4 | 3 | 0 |
| 5: Session State | 2 | 2 | 0 |
| 6: Orchestrator | 2 | 2 | 0 |
| 7: Task | 1 | 0 | 4 |
| 8: Bus | 0.03 | 2 | 0 |
| 9: Fabric | 1 | 2 | 0 |
| 10: Demo | 1 | 1 | 0 |
| 11: Docs | 1 | 2 | 0 |
| 12: Tests | 2 | 3 | 0 |
| **TOTAL** | **~28** | **32** | **9** |

**Total files to modify:** 32
**Total files to delete:** 9
**Total hours:** 28 (3.5 days)

---

## THE COMMANDMENTS

1. **Thou shalt have ONE authoritative path** - No duplicates
2. **Thou shalt wire before polishing** - Connections first
3. **Thou shalt delete unused code** - No orphans
4. **Thou shalt keep kernel separate from demo** - Clean boundary
5. **Thou shalt validate LLM output** - No hallucinations accepted
6. **Thou shalt use canonical section names** - No beliefs
7. **Thou shalt route through orchestrator** - No direct invocation
8. **Thou shalt test the boundaries** - No kernel->demo imports
9. **Thou shalt update docs to match code** - No drift
10. **Thou shalt finish in 3.5 days** - No excuses

---

## READY TO FUCKING WIRE

Pick Epic 0 and start. One file at a time. One deletion at a time. One test at a time.

**The architecture is right. The plan is clear. The work is finite.**

**3.5 days. 32 files. 9 deletions. One human.**

**You've got this.** 🔧
