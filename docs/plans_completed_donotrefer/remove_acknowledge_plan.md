# Remove acknowledge() + Add Streaming Thinking Artifacts

**Branch:** `k1-kernel`
**Date:** 2026-02-23
**Status:** Planning

---

## Milestone 1: Remove acknowledge() Mechanism

Remove the `acknowledge()` tool, ACKING FSM state, and all supporting code from the K1 Concierge POC. The acknowledge mechanism wastes 1 of 6 ReAct iterations, blocks the dispatcher with ACK-first enforcement, and causes FSM coordination bugs. Removal has zero impact on HITL and Weaving flows.

**FSM Flow Change:**

```
BEFORE: LISTENING -> ACKING -> DISPATCHING -> COMPANIONING -> DELIVERING -> LISTENING
AFTER:  LISTENING -> DISPATCHING -> COMPANIONING -> DELIVERING -> LISTENING
```

All transitions currently targeting ACKING (from LISTENING, CLARIFYING_USER, INTERRUPT_HANDLING) will target DISPATCHING instead.

---

### Epic 1.1: Tool Layer Removal

Remove acknowledge from tool schemas, implementations, dispatcher allowlists, and ACK-first enforcement.

#### Issue 1.1.1: Remove ACKNOWLEDGE_SCHEMA definition

**File:** `poc/k1_poc/tools/schemas_front.py`

| Touchpoint | Lines | Current Code | Action |
|-----------|-------|-------------|--------|
| Category comment | L7 | `Signal (1):    acknowledge` | Change to `Signal (0):    (none)` |
| Section header | L22-24 | `# SIGNAL (1)` section | Remove entire section header |
| Schema definition | L26-41 | `ACKNOWLEDGE_SCHEMA = ToolSchema(name="acknowledge", ...)` | Delete entire schema (L26-41) |
| FRONT_TOOLS list | L534 | `ACKNOWLEDGE_SCHEMA,` with `# Signal` comment | Remove entry + comment |

#### Issue 1.1.2: Remove ACKNOWLEDGE_SCHEMA exports

**File:** `poc/k1_poc/tools/__init__.py`

| Touchpoint | Lines | Current Code | Action |
|-----------|-------|-------------|--------|
| Import | L52 | `ACKNOWLEDGE_SCHEMA,` | Remove line |
| `__all__` | L68 | `"ACKNOWLEDGE_SCHEMA",` | Remove line |

#### Issue 1.1.3: Remove execute_acknowledge implementation

**File:** `poc/k1_poc/tools/implementations.py`

| Touchpoint | Lines | Current Code | Action |
|-----------|-------|-------------|--------|
| Comment listing | L12 | `Front tools (10): acknowledge, update_beliefs, ...` | Change to `Front tools (9): update_beliefs, ...` |
| FSM intercept comment | L24 | `acknowledge and dispatch_task are intercepted by the FSM` | Change to `dispatch_task is intercepted by the FSM` |
| Section header | L112-113 | `# SIGNAL (1) -- Front only` | Remove |
| Function | L115-133 | `@_register("acknowledge") def execute_acknowledge(...)` | Delete entire function |

#### Issue 1.1.4: Remove acknowledge from dispatcher allowlists and ACK-first enforcement

**File:** `poc/k1_poc/tools/dispatcher.py`

| Touchpoint | Lines | Current Code | Action |
|-----------|-------|-------------|--------|
| Module docstring | L11 | `ACK-first enforcement (Front only)` | Remove line |
| Pipeline step 4 | L19 | `4. ACK-first enforcement (Front only)` | Remove line, renumber 5->4, 6->5, 7->6 |
| LOW allowlist | L65 | `"acknowledge",` | Remove line |
| MEDIUM allowlist | L76 | `"acknowledge",` | Remove line |
| HIGH allowlist | L88 | `"acknowledge",` | Remove line |
| Step 4 docstring | L221 | `4. ACK-first enforcement (Front only)` | Remove line, renumber steps |
| Step 4 enforcement | L297-306 | `if self.actor == "front" and self.call_count == 0 and name != "acknowledge":` block | Delete entire Step 4 block (10 lines) |

#### Issue 1.1.5: Remove acknowledge from parallelism rules

**File:** `poc/k1_poc/tools/parallelism.py`

| Touchpoint | Lines | Current Code | Action |
|-----------|-------|-------------|--------|
| Rules comment | L10-11 | `Signal tools (acknowledge) are ALWAYS_SEQUENTIAL` | Change to `Control tools (dispatch_task, submit_result) are ALWAYS_SEQUENTIAL` |
| ALWAYS_SEQUENTIAL | L54 | `"acknowledge",  # Must be first` | Remove line |
| partition_calls | L112-115 | `if "acknowledge" in sequential: batches.append(["acknowledge"]) sequential.remove("acknowledge")` | Delete block |

**File:** `poc/k1_poc/task/parallel_safety.py`

| Touchpoint | Lines | Current Code | Action |
|-----------|-------|-------------|--------|
| Classification comment | L17 | `acknowledge (must be first)` | Remove from comment |
| ALWAYS_SEQUENTIAL | L52 | `"acknowledge",  # Must be iteration 1` | Remove line |

---

### Epic 1.2: FSM Layer Removal

Remove ACKING state from enum, transition table, and controller handlers.

#### Issue 1.2.1: Remove ACKING from ConciergeState enum

**File:** `poc/k1_poc/fsm/states.py`

| Touchpoint | Lines | Current Code | Action |
|-----------|-------|-------------|--------|
| Docstring row | L24 | `\| ACKING \| user.input received \| Phase 1 (determ.) \|` | Delete row |
| Enum member | L38 | `ACKING = auto()` | Delete line |

#### Issue 1.2.2: Rewrite transition table (ACKING -> DISPATCHING)

**File:** `poc/k1_poc/fsm/transition_table.py`

| Touchpoint | Lines | Current Code | Action |
|-----------|-------|-------------|--------|
| Import | L17 | `TOPIC_ACK,` | Remove line |
| LISTENING entry | L39 | `TOPIC_USER_INPUT: ConciergeState.ACKING` | Change to `TOPIC_USER_INPUT: ConciergeState.DISPATCHING` |
| ACKING block | L42-44 | `ConciergeState.ACKING: { TRIGGER_PHASE1_COMPLETE: ConciergeState.DISPATCHING, }` | Delete entire block |
| DISPATCHING block | L47 | `TOPIC_ACK: ConciergeState.COMPANIONING,` | Delete line |
| CLARIFYING_USER entry | L78 | `TOPIC_USER_INPUT: ConciergeState.ACKING` | Change to `TOPIC_USER_INPUT: ConciergeState.DISPATCHING` |
| INTERRUPT entry | L88 | `TRIGGER_INTERRUPT_ROUTED: ConciergeState.ACKING` | Change to `TRIGGER_INTERRUPT_ROUTED: ConciergeState.DISPATCHING` |

#### Issue 1.2.3: Remove _on_ack handler and ACKING references from controller

**File:** `poc/k1_poc/fsm/controller.py`

| Touchpoint | Lines | Current Code | Action |
|-----------|-------|-------------|--------|
| Import | L44 | `TOPIC_ACK,` | Remove line |
| Subscription | L417 | `(TOPIC_ACK, self._on_ack),` | Remove line |
| _on_user_input (LISTENING) | L663 | `ConciergeState.ACKING` transition target | Change to `ConciergeState.DISPATCHING` |
| _on_user_input (COMPANIONING interrupt) | L626-628 | `self._transition(ConciergeState.ACKING, TRIGGER_INTERRUPT_ROUTED, ...)` | Change to `ConciergeState.DISPATCHING` |
| _on_user_input (PROGRESSING interrupt) | L694 | `ConciergeState.ACKING` transition target | Change to `ConciergeState.DISPATCHING` |
| _on_user_input comment | L555-557 | `LISTENING -> Normal turn start, ACKING` | Update comment to `DISPATCHING` |
| FrontLock drop comment | L730 | `Any other state (ACKING, DISPATCHING)` | Change to `Any other state (DISPATCHING)` |
| _on_ack handler | L823-858 | Entire `def _on_ack(self, envelope)` method | Delete entire method (~35 lines) |

**Note:** The `_on_ack` handler writes history entry type "ack" and releases FrontLock. After removal, FrontLock release needs to happen elsewhere -- on first FINAL_RESPONSE or at turn end. This will be handled by the existing `_on_response_final` handler which already releases FrontLock.

#### Issue 1.2.4: Remove ack from history writer

**File:** `poc/k1_poc/fsm/history_writer.py`

| Touchpoint | Lines | Current Code | Action |
|-----------|-------|-------------|--------|
| ASSISTANT_ENTRY_TYPES | L48 | `"ack",` in frozenset | Remove entry |
| Event-to-entry table | L78 | `k1.response.ack.v1 -> "ack"` row | Remove row |
| Distinguish comment | L178 | `distinguish acks from finals` | Update comment |
| Prefix mapping | L193 | `"ack": "[ack] ",` | Remove entry |

#### Issue 1.2.5: Update control_extension ACKING comment

**File:** `poc/k1_poc/fsm/control_extension.py`

| Touchpoint | Lines | Current Code | Action |
|-----------|-------|-------------|--------|
| Comment | L148 | `Called by FSM after Phase 1 runs during ACKING` | Change to `Called by FSM after Phase 1 runs during DISPATCHING` |

#### Issue 1.2.6: Remove ACKING from weave state table

**File:** `poc/k1_poc/protocols/weave_state.py`

| Touchpoint | Lines | Current Code | Action |
|-----------|-------|-------------|--------|
| STATE_ACTION_TABLE | L80 | `ConciergeState.ACKING: WeaveAction.QUEUE,` | Delete line |

---

### Epic 1.3: Bus Layer Removal

Remove TOPIC_ACK constant and build_ack builder from the bus module.

#### Issue 1.3.1: Remove TOPIC_ACK from topics.py

**File:** `poc/k1_poc/bus/topics.py`

| Touchpoint | Lines | Current Code | Action |
|-----------|-------|-------------|--------|
| Constant | L40 | `TOPIC_ACK = "k1.response.ack.v1"` | Delete line |
| ALL_TOPICS set | L101 | `TOPIC_ACK,` | Remove entry |
| URGENT_TOPICS set | L135 | `TOPIC_ACK,` | Remove entry |
| Priority map | L194 | `TOPIC_ACK: 0,` | Remove entry |
| `__all__` | L220 | `"TOPIC_ACK",` | Remove entry |

**Note:** `TOPIC_RESPONSE_STREAM` already exists (L41) and will be used for streaming in Milestone 2.

#### Issue 1.3.2: Remove build_ack from builders.py

**File:** `poc/k1_poc/bus/builders.py`

| Touchpoint | Lines | Current Code | Action |
|-----------|-------|-------------|--------|
| Import | L41 | `TOPIC_ACK,` | Remove line |
| Causal chain comment | L27 | `ACK, task dispatch have parent_id = user input` | Update comment to remove ACK |
| Function | L138-140 | `def build_ack(payload, parent_id=0) -> Envelope:` | Delete function (3 lines) |
| BUILDERS registry | L298 | `TOPIC_ACK: build_ack,` | Remove entry |
| `__all__` | L335 | `"build_ack",` | Remove entry |

#### Issue 1.3.3: Remove from bus __init__.py

**File:** `poc/k1_poc/bus/__init__.py`

| Touchpoint | Lines | Current Code | Action |
|-----------|-------|-------------|--------|
| builders import | L17 | `build_ack,` | Remove line |
| topics import | L62 | `TOPIC_ACK,` | Remove line |

---

### Epic 1.4: Actor and React Loop Removal

Remove on_ack callback from react_loop, front_handler, and back_handler.

#### Issue 1.4.1: Remove on_ack from react_loop

**File:** `poc/k1_poc/react/loop.py`

| Touchpoint | Lines | Current Code | Action |
|-----------|-------|-------------|--------|
| _resolve_tool_choice | L116 | `Forces the first tool call (which should be acknowledge)` | Change comment to `Forces the first tool call` |
| on_ack parameter | L153 | `on_ack: Callable[[str], Awaitable[None]] \| None,` | Remove parameter |
| tool_choice comment | L170 | `tool_choice='required' on Front iteration 0 forces acknowledge` | Update comment |
| Docstring | L182 | `on_ack: Front only: callback when acknowledge() fires` | Remove from docstring |
| Parallel comment | L424 | `acknowledge + ...` | Update comment |
| on_ack fire | L453-455 | `if tc.name == "acknowledge" and on_ack is not None: await on_ack(...)` | Delete block (3 lines) |

**Also:** Consider changing `_resolve_tool_choice` to always return `"auto"` for Front iteration 0, since there's no forced tool anymore. Or keep `"required"` to force at least one tool call (cognitive tools). Decision: Keep `"required"` -- it ensures the model calls at least one cognitive tool on the first iteration.

#### Issue 1.4.2: Remove _on_ack from front_handler

**File:** `poc/k1_poc/actors/front.py`

| Touchpoint | Lines | Current Code | Action |
|-----------|-------|-------------|--------|
| Import | L34 | `build_ack,` | Remove import |
| _on_ack callback | L593-605 | `async def _on_ack(text): ... bus.publish(env)` | Delete entire callback (13 lines) |
| react_loop call | L631 | `on_ack=_on_ack,` | Remove argument |

#### Issue 1.4.3: Remove on_ack=None from back_handler

**File:** `poc/k1_poc/actors/back.py`

| Touchpoint | Lines | Current Code | Action |
|-----------|-------|-------------|--------|
| back_handler call | L452 | `on_ack=None,` | Remove line |
| back_resume_handler call | L620 | `on_ack=None,` | Remove line |

#### Issue 1.4.4: Remove acknowledge-first validation from LLM validator

**File:** `poc/k1_poc/llm/validator.py`

| Touchpoint | Lines | Current Code | Action |
|-----------|-------|-------------|--------|
| Docstring item 3 | L11 | `3. Acknowledge-first -- Front actor's first tool MUST be acknowledge()` | Remove item, renumber |
| Comment | L75 | `protocol violations (acknowledge-first)` | Change to `protocol violations` |
| Ack-first check | L106-121 | `ack_available = ... if actor == "front" and iteration == 0 and ack_available: if not self._first_tool_is_acknowledge(response):` | Delete entire block (16 lines) |
| _first_tool_is_acknowledge | L197-201 | `@staticmethod def _first_tool_is_acknowledge(response):` | Delete method (5 lines) |
| Reorder logic | L264-290 | `if actor == "front" and iteration == 0: ack_idx = ... valid_calls.insert(0, ack_call)` | Delete acknowledge reorder block |

#### Issue 1.4.5: Update test adapter default response

**File:** `poc/k1_poc/llm/test_adapter.py`

| Touchpoint | Lines | Current Code | Action |
|-----------|-------|-------------|--------|
| Default example | L38 | `name="acknowledge"` | Change to `name="update_beliefs"` or similar cognitive tool |

---

### Epic 1.5: Prompt and Config Removal

Remove acknowledge from prompt templates, tool allowlists, scenario instructions, and YAML config.

#### Issue 1.5.1: Remove acknowledge from TOOL_ALLOWLIST

**File:** `poc/k1_poc/prompt/mode.py`

| Touchpoint | Lines | Current Code | Action |
|-----------|-------|-------------|--------|
| STANDARD | L67 | `"acknowledge",` | Remove line |
| CLARIFY_ASK | L78 | `"acknowledge",` | Remove line |
| CLARIFY_RESOLVE | L83 | `"acknowledge",` | Remove line |
| HITL_RESOLVE | L105 | `"acknowledge",` | Remove line |
| CANCEL | L110 | `"acknowledge",` | Remove line |
| INTERRUPT | L93 | `"acknowledge",` | Remove line |

**Note:** MEMBER_SWITCH (if exists) also needs removal.

#### Issue 1.5.2: Rewrite ReAct rhythm prompt sections

**File:** `poc/k1_poc/prompt/sections.py`

| Touchpoint | Lines | Current Code | Action |
|-----------|-------|-------------|--------|
| Parallel example | L78 | `acknowledge() + recall_memory() + update_scoreboard()` | Change to `recall_memory() + update_scoreboard() + update_beliefs()` |
| Iteration 1 rule | L85 | `Iteration 1: ALWAYS call acknowledge() first. Non-negotiable.` | Change to `Iteration 1: Call recall_memory() and cognitive tools. Batch independent tools.` |
| Typical turn ex | L93 | `1. acknowledge() + recall_memory() + update_scoreboard()` | Change to `1. recall_memory() + update_scoreboard() + update_beliefs()` |
| Short turn ex | L98 | `1. acknowledge()` | Change to `1. update_beliefs() (or skip tools for simple greetings)` |
| Anti-ack rule | L107 | `Do NOT call acknowledge() on these triggers` | Remove line |
| REDUCED rhythm | L115 | `1. acknowledge() -- if this was triggered by user input` | Change to `1. Cognitive tools (if needed), batch in one response` |
| REDUCED anti-ack | L122 | `Do NOT call acknowledge() on task_complete, weave, or hitl triggers.` | Remove line |
| Anti-pattern | L320 | `Call acknowledge() on task_complete, weave, or hitl triggers.` | Remove line |
| STANDARD examples | L531-615 | Multiple `1: acknowledge(...)` in ReAct examples | Remove acknowledge from all iteration 1 examples, renumber steps |

#### Issue 1.5.3: Update scenario templates

**File:** `poc/k1_poc/prompt/scenario_templates.py`

| Touchpoint | Lines | Current Code | Action |
|-----------|-------|-------------|--------|
| PRESENT | L48 | `Do not call acknowledge().` | Remove line (no longer relevant) |
| WEAVE | L59 | `Do not call acknowledge().` | Remove line |
| ERROR | L72 | `Do not call acknowledge().` | Remove line |
| HITL_RESOLVE | L79 | `Call acknowledge().` | Remove line |
| HITL_RELAY | L88 | `Do not call acknowledge().` | Remove line |

#### Issue 1.5.4: Remove acknowledge from config YAML

**File:** `poc/k1_poc/config/defaults.yaml`

| Touchpoint | Lines | Current Code | Action |
|-----------|-------|-------------|--------|
| LOW allowlist | L328 | `- acknowledge` | Remove line |
| MEDIUM allowlist | L338 | `- acknowledge` | Remove line |
| HIGH allowlist | L349 | `- acknowledge` | Remove line |
| Control category | L408 | `- acknowledge` | Remove line |

---

### Epic 1.6: Demo / UI Layer Removal

Remove acknowledge rendering from output channel and spinner.

#### Issue 1.6.1: Remove acknowledge from OutputChannel

**File:** `poc/k1_poc/demo/output_channel.py`

| Touchpoint | Lines | Current Code | Action |
|-----------|-------|-------------|--------|
| Import | L26 | `TOPIC_ACK,` | Remove line |
| IRenderer protocol | L60 | `def render_ack(self, text: str, member: str) -> None: ...` | Remove method |
| TimelineEntry phase | L78 | `"ack"` in phase docstring | Remove from docstring |
| ConsoleRenderer | L122 | `def render_ack(self, text, member):` | Remove method |
| Subscription map | L341 | `TOPIC_ACK: self._on_ack,` | Remove entry |
| _on_ack handler | L440-452 | `def _on_ack(self, envelope): ... self._response_event.set()` | Delete entire handler |

**Critical:** The `_on_ack` handler currently calls `self._response_event.set()`. After removal, `_on_final_response` must set `_response_event` (it should already do this, verify).

#### Issue 1.6.2: Remove acknowledge from spinner

**File:** `poc/k1_poc/demo/spinner.py`

| Touchpoint | Lines | Current Code | Action |
|-----------|-------|-------------|--------|
| Example comments | L8-11 | `[check] Acknowledged: "Good morning!"` | Remove line |
| Import | L32 | `TOPIC_ACK,` | Remove line |
| FSM labels | L83 | `"ACKING": ("Acknowledging input", YELLOW),` | Remove entry |
| Subscription | L320 | `TOPIC_ACK: self._on_ack,` | Remove entry |
| Handler | L402-406 | `def _on_ack(self, envelope):` | Delete entire handler |

---

### Epic 1.7: Supporting Module Updates

Update HITL wiring validation and other cross-cutting references.

#### Issue 1.7.1: Update HITL wiring validation

**File:** `poc/k1_poc/protocols/hitl_wiring.py`

| Touchpoint | Lines | Current Code | Action |
|-----------|-------|-------------|--------|
| HITL_RESOLVE comment | L290 | `2 tools (acknowledge + update_beliefs)` | Change to `1 tool (update_beliefs)` |
| HITL_RESOLVE comment | L325 | `HITL_RESOLVE has exactly [acknowledge, update_beliefs]` | Change to `HITL_RESOLVE has exactly [update_beliefs]` |
| Validation assertion | L377 | `expected_tools = {"acknowledge", "update_beliefs"}` | Change to `expected_tools = {"update_beliefs"}` |

---

### Epic 1.8: Test Updates

Update all test files that assert on acknowledge behavior.

#### Issue 1.8.1: Update FSM controller tests

**File:** `tests/poc/test_m08_fsm_controller.py`

| Scope | Lines | Action |
|-------|-------|--------|
| TOPIC_ACK import | L36 | Remove import |
| ConciergeState.ACKING | L41, L45 | Remove/update assertions |
| ACKING transitions | L71 | Update transition expectations |
| build_ack usage | L134 | Remove or replace |
| ACKING lifecycle tests | L306, L395-407 | Change LISTENING->ACKING to LISTENING->DISPATCHING |
| _on_ack handler tests | L442-496 | Delete or rewrite without ACK step |
| Full lifecycle | L533-593 | Remove ACK step from lifecycle sequences |
| TOPIC_ACK assertions | L946, L960, L963 | Remove ACK assertions |

#### Issue 1.8.2: Update react loop tests

**File:** `tests/poc/test_m05_react_loop.py`

| Scope | Lines | Action |
|-------|-------|--------|
| on_ack parameter | L151, L160 | Remove parameter from react_loop calls |
| acknowledge tool calls | L291-292, L327, L546, L581, L673-674, L716 | Change mock tool calls from "acknowledge" to cognitive tools |
| on_ack callback assertions | L929-930, L957, L960, L1010, L1051-1053, L1152-1153, L1328 | Remove callback assertions |

#### Issue 1.8.3: Update front handler tests

**File:** `tests/poc/test_m06_front_handler.py`

| Scope | Lines | Action |
|-------|-------|--------|
| TOPIC_ACK captures | L114, L464, L482 | Remove ACK topic captures |
| acknowledge in mock responses | L934, L958, L1019, L1066, L1070, L1091, L1125 | Replace with cognitive tools |
| ACK envelope assertions | L1597, L1668, L1705, L1758, L1804, L1852 | Remove ACK assertions |

#### Issue 1.8.4: Update capabilities e2e tests

**File:** `tests/poc/test_m07_capabilities_e2e.py`

| Scope | Lines | Action |
|-------|-------|--------|
| TOPIC_ACK ref | L38 | Remove |
| Back rejects acknowledge | L70, L563-613 | Remove test or update expectation |

#### Issue 1.8.5: Update prompt mode tests

**File:** `tests/poc/test_m09_epics_4_5.py`

| Scope | Lines | Action |
|-------|-------|--------|
| TOOL_ALLOWLIST assertions | L179-195, L201 | Remove "acknowledge" from expected allowlists |

#### Issue 1.8.6: Update scenario template tests

**File:** `tests/poc/test_m09_epics_6_7_8.py`

| Scope | Lines | Action |
|-------|-------|--------|
| Scenario template assertions | L114-117 | Remove acknowledge instruction checks |
| Affect block assertions | L412-414 | Update expectations |

#### Issue 1.8.7: Update HITL/clarify tests

**File:** `tests/poc/test_m09_epics_13_14.py`

| Scope | Lines | Action |
|-------|-------|--------|
| HITL allowlist assertions | L270, L317, L325 | Remove "acknowledge" from expected sets |

#### Issue 1.8.8: Update parallelism tests

**File:** `tests/poc/test_m10_epics_13_14.py`

| Scope | Lines | Action |
|-------|-------|--------|
| ALWAYS_SEQUENTIAL assertions | L931, L1006, L1053, L1085, L1092 | Remove "acknowledge" from expected sequential sets |

#### Issue 1.8.9: Update weave state tests

**File:** `tests/poc/test_m12_epic_7.py`

| Scope | Lines | Action |
|-------|-------|--------|
| ACKING -> QUEUE assertion | L804 | Delete assertion |

**File:** `tests/poc/test_m12_epics_4_5_6.py`

| Scope | Lines | Action |
|-------|-------|--------|
| ACKING assertions | L466-467, L487 | Remove ACKING -> QUEUE entries |

#### Issue 1.8.10: Update HITL resolve/relay tests

**File:** `tests/poc/test_m13_epics_7_8_9.py`

| Scope | Lines | Action |
|-------|-------|--------|
| HITL_RESOLVE tool assertions | L229-232, L244, L251-258 | Remove "acknowledge" from expected tools |
| HITL_RELAY assertions | L378-381, L477-480 | Update expectations |
| Wiring validation | L904, L1453-1471 | Update expected_tools for HITL_RESOLVE |

#### Issue 1.8.11: Update affect ordering tests

**File:** `tests/poc/test_m14_epics_4_5.py`

| Scope | Lines | Action |
|-------|-------|--------|
| Tool ordering assertions | L190, L195, L242, L482, L492, L568 | Remove acknowledge from expected orderings |

---

## Milestone 2: Add Streaming Thinking Artifacts

Replace the deleted ACK visual feedback with Gemini streaming. Instead of wasting a ReAct iteration to show "On it!", stream the model's thinking tokens to the UI as they arrive, giving sub-second first-token visibility.

**Note:** `TOPIC_RESPONSE_STREAM` and `build_response_stream` already exist in the bus layer.

---

### Epic 2.1: Streaming Infrastructure

#### Issue 2.1.1: Implement generate_stream() in Gemini adapter

**File:** `poc/k1_poc/llm/gemini_adapter.py` (new method)

| Touchpoint | Action |
|-----------|--------|
| New method | Add `async def generate_stream(self, request) -> AsyncIterator[StreamChunk]` |
| StreamChunk | Define dataclass with `type: Literal["thinking", "text", "tool_call"]` and `content: str` |
| Gemini config | Use `stream=True` + `thinking_config` for Gemini 2.5 Flash/Pro |
| Yield chunks | Yield `StreamChunk(type="thinking", content=...)` for thought tokens, `StreamChunk(type="text", content=...)` for response text |

#### Issue 2.1.2: Add on_stream callback to react_loop

**File:** `poc/k1_poc/react/loop.py`

| Touchpoint | Action |
|-----------|--------|
| New parameter | Add `on_stream: Callable[[StreamChunk], Awaitable[None]] | None = None` |
| Front iteration 0 | If `on_stream` is not None and `actor == "front"`, use `model.generate_stream()` instead of `model.generate()`, forward each chunk via `await on_stream(chunk)` |
| Remaining iterations | Continue using `model.generate()` (non-streaming) |

#### Issue 2.1.3: Wire on_stream callback in front_handler

**File:** `poc/k1_poc/actors/front.py`

| Touchpoint | Action |
|-----------|--------|
| New callback | Add `async def _on_stream(chunk): bus.publish(build_response_stream(...))` |
| react_loop call | Add `on_stream=_on_stream` argument |

---

### Epic 2.2: Streaming UI

#### Issue 2.2.1: Add streaming handler to OutputChannel

**File:** `poc/k1_poc/demo/output_channel.py`

| Touchpoint | Action |
|-----------|--------|
| New subscription | Subscribe to `TOPIC_RESPONSE_STREAM` with `self._on_stream_chunk` |
| New handler | `def _on_stream_chunk(self, envelope)` -- renders thinking tokens progressively |
| IRenderer | Add `def render_stream_chunk(self, text: str, chunk_type: str) -> None` |
| ConsoleRenderer | Implement `render_stream_chunk` -- dim gray for thinking, normal for text |

#### Issue 2.2.2: Add streaming display to spinner

**File:** `poc/k1_poc/demo/spinner.py`

| Touchpoint | Action |
|-----------|--------|
| New subscription | Subscribe to `TOPIC_RESPONSE_STREAM` with `self._on_stream` |
| New handler | Show streaming thinking chunks in the spinner line |

---

## Execution Order

```
Phase 1: Epic 1.1 (tools) + Epic 1.3 (bus)      -> import smoke test
Phase 2: Epic 1.2 (FSM)                          -> run FSM controller tests
Phase 3: Epic 1.4 (actors/react)                 -> run react loop + front handler tests
Phase 4: Epic 1.5 (prompt/config)                -> run prompt tests
Phase 5: Epic 1.6 (demo) + Epic 1.7 (support)   -> manual smoke test
Phase 6: Epic 1.8 (tests)                        -> full test suite green
Phase 7: Epic 2.1 + 2.2 (streaming)              -> manual demo test
```

---

## Summary

| Metric | Count |
|--------|-------|
| Source files modified | 27 |
| Test files modified | 13 |
| New files created | 0 (streaming adds to existing files) |
| Lines deleted (est.) | ~250 |
| Lines modified (est.) | ~80 |
| Lines added (est.) | ~120 (streaming) |
| Total issues | 30 |
| Total epics | 10 |
| Total milestones | 2 |
