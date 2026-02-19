# Concierge FSM PoC -- Phase 10 Plan

**Date**: 2026-02-18
**Status**: Planned
**Scope**: 4 features, 4 epics, 28 issues across 2 milestones

---

## Milestone 1: Acknowledge Removal + Live Panel Redesign

> Independent changes with no cross-dependencies.
> Target: All existing tests pass (803/829), no LLM behavior change except dropping wasted acknowledge calls.

### Epic 1.1 -- Hide Acknowledge Tool from LLM

**Goal**: Keep `signal.py` code intact but prevent the LLM from ever seeing or calling `acknowledge()`. Saves 1 wasted tool call per turn across 14+ turns.

**Decision**: "Just hide from LLM" -- do NOT delete code, only stop registering it in tool declarations.

#### Issue 1.1.1 -- Remove acknowledge registration from ToolRegistry

**File**: `poc/concierge_fsm_poc/tools/registry.py`
**Lines**: 180, 194-202

- Remove `from .signal import ACKNOWLEDGE_SCHEMA, acknowledge` at line 180
- Remove the entire `registry.register(ToolDefinition(name="acknowledge", ...))` block (lines 194-202)
- The "SIGNAL (1 tool)" section header comment becomes "SIGNAL (0 tools -- acknowledge hidden)" or is removed
- `build_default_registry()` will return a registry with 14 tools instead of 15
- Signal category will have 0 tools

**Acceptance**:

- `registry.get("acknowledge")` raises `ToolNotFoundError`
- `registry.get_llm_declarations("LOW")` does not include acknowledge
- `len(registry.all_tools)` == 14

---

#### Issue 1.1.2 -- Remove acknowledge from COGNITIVE_TOOLS frozenset

**File**: `poc/concierge_fsm_poc/react/scratchpad.py`
**Line**: 34

- Remove `"acknowledge"` from the `COGNITIVE_TOOLS` frozenset
- Set goes from 7 members to 6

**Acceptance**:

- `"acknowledge" not in COGNITIVE_TOOLS`
- `len(COGNITIVE_TOOLS) == 6`

---

#### Issue 1.1.3 -- Remove ack_sent tracking and dynamic filtering from ReActLoop

**File**: `poc/concierge_fsm_poc/react/loop.py`
**Lines**: 248, 398-402, 491-492

Three removals:

1. **Line 248**: Remove `ack_sent = False`
2. **Lines 398-402**: Remove the `if tc.name == "acknowledge":` block that sets `ack_sent = True` and emits `ACK_DELIVERED`
3. **Lines 491-492**: Remove the `if ack_sent: tool_declarations = [...]` dynamic filtering block

Also update the module docstring (lines 22-28) to remove mention of acknowledge from COGNITIVE_TOOLS routing description.

**Acceptance**:

- No variable named `ack_sent` in loop.py
- No `ACK_DELIVERED` event ever emitted during loop execution
- No dynamic tool filtering based on acknowledge

---

#### Issue 1.1.4 -- Update system prompt Rules 3 and 5

**File**: `poc/concierge_fsm_poc/llm/client.py`
**Lines**: 161-165 (Rule 3), 173-181 (Rule 5)

**Rule 3** -- Replace entirely:

```
### 3. ONE acknowledge() CALL -- NO MORE
Call acknowledge() ONCE at the very start of your first response. ...
```

becomes:

```
### 3. PROCEED DIRECTLY TO ACTION
Do NOT waste calls on greetings or acknowledgments. Start immediately \
with data-gathering tools (invoke_capability, recall_memory, \
update_beliefs) to fulfill the user's request. Every tool call must \
advance the task.
```

**Rule 5** -- Remove line 1 (`1. acknowledge() -- ONCE, first call only`), renumber remaining items 1-7:

```
### 5. TOOL USAGE PRIORITY (in order)
1. invoke_capability() -- for weather, hotels, activities, restaurants
2. recall_memory() -- for family data, preferences, history
3. update_beliefs() -- to store new facts discovered
4. update_scoreboard() -- to track entities and tasks
5. update_clarifications() -- to record information gaps needing resolution
6. discover_capabilities -- ONLY if you truly need to find an unknown capability
7. read_session_state -- to check existing session data
```

**Acceptance**:

- `"acknowledge"` does not appear in `build_system_prompt()` output
- Rule 3 mentions "PROCEED DIRECTLY TO ACTION"
- Rule 5 starts with `invoke_capability` at position 1

---

#### Issue 1.1.5 -- Remove acknowledge references from trip_timeline.py

**File**: `poc/concierge_fsm_poc/scenarios/trip_timeline.py`
**Lines**: 74, 89, 105, 156, 168, 183, 223, 238, 266, 280, 293, 305, 319, 334

- Remove `"acknowledge"` from every `expected_tools` list (14 occurrences across turns 1-3, 6-8, 11-12, 14-19)
- Turn 16 (`flow_id="F24"`) has `expected_tools=["acknowledge"]` -- becomes `expected_tools=[]` (CB-OPEN, no LLM called anyway)

**Acceptance**:

- `grep -r "acknowledge" trip_timeline.py` returns 0 matches
- No TurnHint has "acknowledge" in expected_tools

---

#### Issue 1.1.6 -- Remove ack_log usage from run_demo.py

**File**: `poc/concierge_fsm_poc/run_demo.py`
**Lines**: ~839 (reset_ack_log), ~1197-1201 (get_ack_log + session_ops append)

- Remove `reset_ack_log()` call in `_run_turn()` (line ~839)
- Remove the `ack_log = get_ack_log()` block and `for ack_entry in ack_log` loop (lines ~1197-1201)
- Remove import of `reset_ack_log` and `get_ack_log` from the imports section

**Acceptance**:

- No calls to `reset_ack_log()` or `get_ack_log()` in run_demo.py
- `_run_turn()` no longer references acknowledge logging

---

#### Issue 1.1.7 -- Remove ACK_DELIVERED handler from LiveLoopDisplay

**File**: `poc/concierge_fsm_poc/run_demo.py`
**Lines**: ~584-587

- Remove the `elif t == LoopEventType.ACK_DELIVERED:` block
- Remove `self._ack_message` field from `__init__` (line ~521)
- ACK_DELIVERED event type stays in events.py (no harm, may be useful later for other purposes)

**Acceptance**:

- `LiveLoopDisplay.on_event()` has no ACK_DELIVERED branch
- No `_ack_message` attribute

---

#### Issue 1.1.8 -- Update test_registry.py for acknowledge removal

**File**: `poc/concierge_fsm_poc/tests/test_registry.py`
**Lines**: 32, 52, 377-379, 466-470

Changes:

1. **Line 32**: Remove `"acknowledge"` from `ALL_TOOL_NAMES` (14 items now)
2. **Line 52**: Remove `"acknowledge"` from `LOW_TOOL_NAMES`
3. **Lines 377-379**: `test_signal_is_acknowledge` -- delete or rewrite as `test_signal_category_empty`:

   ```python
   def test_signal_category_empty(self, registry):
       tools = registry.get_by_category("signal")
       assert len(tools) == 0
   ```

4. **Category count parametrize**: Signal category count changes from 1 to 0
5. **Lines 466-470**: `test_acknowledge_description_mentions_first_call` -- delete entirely

**Acceptance**:

- All test_registry.py tests pass
- No test references `acknowledge` as a registered tool

---

#### Issue 1.1.9 -- Update test_scratchpad.py for COGNITIVE_TOOLS change

**File**: `poc/concierge_fsm_poc/tests/test_scratchpad.py`
**Lines**: 38, 41-42, 67-68, 74, 360

Changes:

1. **Line 38**: `test_has_seven_tools` -> `test_has_six_tools`, assert `len == 6`
2. **Lines 41-42**: Delete `test_acknowledge_present` entirely
3. **Lines 67-68**: Remove `"acknowledge"` from the `expected` set in `test_expected_names`
4. **Line 360**: Change `pad.record_tool_call("acknowledge")` to `pad.record_tool_call("update_beliefs")` (or any other cognitive tool)

**Acceptance**:

- All test_scratchpad.py tests pass
- `COGNITIVE_TOOLS` has 6 members, no acknowledge

---

#### Issue 1.1.10 -- Update test_loop.py for acknowledge removal

**File**: `poc/concierge_fsm_poc/tests/test_loop.py`
**Lines**: 73, 635, 1124, 1145-1147

Changes:

1. **Lines 72-79**: Remove `"acknowledge"` entry from `_make_registry()` default handlers dict. The first registered tool becomes `"update_beliefs"`.
2. **Lines 627-650**: `test_mixed_tools_only_extracts_non_cognitive` -- replace acknowledge ToolCall with `update_beliefs` ToolCall (still cognitive, same routing behavior):

   ```python
   ToolCall(
       name="update_beliefs",
       arguments={"key": "test", "value": "data", "source": "user"},
   ),
   ```

3. **Lines 1117-1148**: `test_two_tools_one_response` -- replace acknowledge ToolCall with `update_beliefs`, update assertions from `"acknowledge" in tool_names` to `"update_beliefs" in tool_names`

**Acceptance**:

- All test_loop.py tests pass (55 tests)
- No test constructs an acknowledge ToolCall

---

#### Issue 1.1.11 -- Update test_streaming.py for acknowledge removal

**File**: `poc/concierge_fsm_poc/tests/test_streaming.py`
**Line**: 314

- Replace `"acknowledge"` in `_make_registry()` with `"update_beliefs"` (or remove entirely if not needed for the test)

**Acceptance**:

- All test_streaming.py tests pass (29 tests)

---

#### Issue 1.1.12 -- Update test_llm_client.py for system prompt changes

**File**: `poc/concierge_fsm_poc/tests/test_llm_client.py`
**Lines**: 201, 211, 253

Changes:

1. **Lines 200-201**: `test_tool_names_listed` -- change `"acknowledge"` to `"update_beliefs"` in test tool list
2. **Line 211**: Update assertion from `assert "acknowledge" in prompt` to `assert "update_beliefs" in prompt`
3. **Line 253**: `test_instructions_present` -- change `assert "acknowledge()" in prompt` to `assert "PROCEED DIRECTLY TO ACTION" in prompt` (matching new Rule 3 text)

Note: Lines 492, 509, 587-588, 917-918, 933-934 are in the SDK migration tests that are already pre-failing (26 failures). Leave those as-is -- they test LLM client internals, not system prompt text.

**Acceptance**:

- System prompt tests in test_llm_client.py pass
- Pre-existing 26 failures in SDK migration tests unchanged

---

### Epic 1.2 -- Multi-Section LiveLoopDisplay Redesign

**Goal**: Replace the flat-text `__rich__()` with a structured multi-section layout showing FSM State, Active Tool, Findings, and Event Log as independent sections.

**Decision**: Multi-section layout with dedicated areas.

#### Issue 1.2.1 -- Add new state fields to LiveLoopDisplay.**init**

**File**: `poc/concierge_fsm_poc/run_demo.py`
**Lines**: 512-523

Add new fields:

```python
self._start_time: float = time.time()
self._fsm_state: str = "LISTENING"
self._recent_findings: deque[tuple[str, str]] = deque(maxlen=3)
self._elapsed_s: float = 0.0
```

Remove `self._ack_message` (covered by Issue 1.1.7).

**Acceptance**:

- `LiveLoopDisplay()` has `_start_time`, `_fsm_state`, `_recent_findings` attributes

---

#### Issue 1.2.2 -- Update on_event() for new fields

**File**: `poc/concierge_fsm_poc/run_demo.py`
**Lines**: 528-602

Updates to event handlers:

1. **FSM_TRANSITION**: Set `self._fsm_state = d.get("to_state", "?")` (currently only logs)
2. **FINDING_EXTRACTED**: Append `(key, value)` to `self._recent_findings` deque
3. **BUDGET_WARNING** (new handler): `self._log("red", f"BUDGET: {d.get('resource')} {d.get('used')}/{d.get('limit')}")`
4. Add unicode markers to `_log()` calls:
   - TOOL_CALL_START: prefix `">>"` (already has it)
   - TOOL_CALL_END: prefix checkmark/cross `"[ok]"` / `"[x]"`
   - LLM_CALL_START: prefix `"~"`
   - FINDING_EXTRACTED: prefix `"*"`
   - ITERATION_START: prefix `"---"`
5. Update elapsed time on every event: `self._elapsed_s = time.time() - self._start_time`

**Acceptance**:

- `_fsm_state` updates on FSM_TRANSITION events
- `_recent_findings` deque populates on FINDING_EXTRACTED events
- BUDGET_WARNING has a handler (currently missing)

---

#### Issue 1.2.3 -- Rewrite **rich**() as multi-section layout

**File**: `poc/concierge_fsm_poc/run_demo.py`
**Lines**: 610-651

Replace the current flat `Text()` layout with a Rich `Table` (no header) structure:

```
+------------------------------------------------------+
|  ReAct Live                                          |
+------------------------------------------------------+
| [/] Iteration 3  |  12.4s  |  Tools: 5  |  Found: 3 |  <- Status bar
+------------------------------------------------------+
| FSM: PROGRESSING          | Tool: invoke_capability  |  <- State row
+------------------------------------------------------+
| Findings:                                             |  <- Findings
|   weather = 45F sunny                                 |
|   hotel_price = $189/night                            |
|   activity = Ski lessons available                    |
+------------------------------------------------------+
| ~ LLM call: 8 messages, 7 tools available            |  <- Event log
| >> invoke_capability({...})                           |
| [ok] invoke_capability -> OK: weather data            |
| * Learned: weather = 45F sunny                        |
+------------------------------------------------------+
| Streaming: ...planning your Lake Tahoe trip_          |  <- Stream
+------------------------------------------------------+
```

Implementation:

- Use `from rich.table import Table` with `show_header=False`, `box=box.ROUNDED`
- Row 1: Status bar -- spinner, iteration, elapsed, tools, findings counts
- Row 2: Two-column -- FSM state badge (colored), active tool (or "Idle" dim)
- Row 3: Findings section -- last 3 key=value pairs from `_recent_findings`
- Row 4: Event log -- last 8 entries from `_events_log`
- Row 5: Streaming text preview with blinking cursor `_` appended
- Wrap in `Panel(table, title="...", border_style="cyan")`

**Acceptance**:

- `__rich__()` returns a `Panel` containing a `Table`
- All 5 sections render correctly
- Panel width stays at 72 chars
- Elapsed time updates in real-time

---

#### Issue 1.2.4 -- Update test_streaming.py LiveLoopDisplay tests

**File**: `poc/concierge_fsm_poc/tests/test_streaming.py`

- Update any tests that inspect `LiveLoopDisplay` internal state (e.g., `_ack_message` removed)
- Add test for new `_fsm_state` field population
- Add test for `_recent_findings` deque population
- Add test for BUDGET_WARNING handler

**Acceptance**:

- All test_streaming.py tests pass
- New fields have test coverage

---

## Milestone 2: Interactive Modes + LLM Clarification

> Depends on Milestone 1 completion (acknowledge removal cleans up the tool set).
> Target: Three CLI modes working, LLM generates clarifying questions.

### Epic 2.1 -- Interactive CLI Modes (--user and --guided)

**Goal**: Add `--user` (free-form chat, no scenario) and `--guided` (scenario with user typing) alongside the existing scripted default.

**Decision**: "Both modes" -- mutually exclusive with each other and with `--auto`.

#### Issue 2.1.1 -- Add CLI argument parsing for modes

**File**: `poc/concierge_fsm_poc/run_demo.py`
**Lines**: 1422-1437

Replace current argparse block with:

```python
parser = argparse.ArgumentParser(description="Concierge FSM Demo")
group = parser.add_mutually_exclusive_group()
group.add_argument("--auto", action="store_true",
                   help="Scripted mode without pausing")
group.add_argument("--user", action="store_true",
                   help="Free-form interactive chat (no scenario)")
group.add_argument("--guided", action="store_true",
                   help="Scenario-guided mode (shows hints, you type)")
```

Determine mode string: `"scripted"` (default), `"user"`, `"guided"`, `"auto"` (scripted without pauses).
Pass to `main()`.

**Acceptance**:

- `python -m poc.concierge_fsm_poc.run_demo --user` starts user mode
- `python -m poc.concierge_fsm_poc.run_demo --guided` starts guided mode
- `python -m poc.concierge_fsm_poc.run_demo` starts scripted mode (default)
- `python -m poc.concierge_fsm_poc.run_demo --auto` starts auto scripted mode
- `--user --guided` errors with "mutually exclusive"
- `--auto --user` errors with "mutually exclusive"

---

#### Issue 2.1.2 -- Update main() signature and mode routing

**File**: `poc/concierge_fsm_poc/run_demo.py`
**Lines**: 1228-1370

Change signature: `async def main(auto: bool = False, mode: str = "scripted") -> None`

Add mode routing after persona pre-load:

```python
if mode == "user":
    await _run_user_mode(manager, fsm, classifier, registry, llm)
elif mode == "guided":
    await _run_guided_mode(manager, fsm, classifier, registry, llm)
else:
    # Existing scripted timeline loop (current code)
    ...
```

**Acceptance**:

- `main(mode="user")` calls `_run_user_mode()`
- `main(mode="guided")` calls `_run_guided_mode()`
- `main()` or `main(auto=True)` runs existing scripted loop

---

#### Issue 2.1.3 -- Add module-level _interactive_mode flag

**File**: `poc/concierge_fsm_poc/run_demo.py`

Add near `_auto_mode`:

```python
_interactive_mode: bool = False  # True when --user or --guided
```

Set in `main()` when mode is `"user"` or `"guided"`.

Used by `_run_clarification()` to decide whether to prompt user or use scripted answers.

**Acceptance**:

- `_interactive_mode` is `True` in user/guided modes
- `_interactive_mode` is `False` in scripted/auto modes

---

#### Issue 2.1.4 -- Add _run_turn() override_message parameter

**File**: `poc/concierge_fsm_poc/run_demo.py`
**Lines**: 806-816

Add parameter: `override_message: str | None = None`

When set:

- Use `override_message` instead of `hint.suggested_message` for classification
- Use `override_message` instead of `hint.suggested_message` for LLM user message
- Display `override_message` as user message (not "scripted")
- Keep `hint` for expected_tools, special_flags, etc.

Touch points within `_run_turn()`:

- Line ~822: `_show_user_message(override_message or hint.suggested_message)`
- Line ~851: `classifier.classify_with_fallback(override_message or hint.suggested_message, ...)`
- Line ~902: `_run_clarification(..., override_message or hint.suggested_message, ...)`
- Line ~1015-1025: `llm_user_message` construction uses `override_message or hint.suggested_message`

**Acceptance**:

- `_run_turn(..., override_message="custom text")` classifies and sends "custom text" to LLM
- `_run_turn(..., override_message=None)` behaves identically to current code

---

#### Issue 2.1.5 -- Update _show_user_message() for typed vs scripted

**File**: `poc/concierge_fsm_poc/run_demo.py`

Find `_show_user_message()` definition. Add parameter `scripted: bool = True`.

- If `scripted=True`: current display `"USER (scripted): ..."`
- If `scripted=False`: display `"USER: ..."` in brighter style (e.g., bold white)

**Acceptance**:

- Scripted messages show "(scripted)" tag
- User-typed messages show without tag

---

#### Issue 2.1.6 -- Update _run_clarification() for interactive input

**File**: `poc/concierge_fsm_poc/run_demo.py`
**Lines**: 690-797

When `_interactive_mode` is True:

- Instead of `hint.clarification_answers[scripted_idx]`, call `console.input("  Your answer: ")`
- Display the LLM-generated question (from Issue 2.2.1) instead of raw gap list
- Show `"USER: {answer}"` instead of `"USER (scripted): {answer}"`

When `_interactive_mode` is False (default):

- Current behavior unchanged (scripted answers)

**Acceptance**:

- In guided/user modes, user types clarification answers
- In scripted mode, scripted answers from TurnHint used
- Empty input in interactive mode treated as "no additional info"

---

#### Issue 2.1.7 -- Implement _run_guided_mode()

**File**: `poc/concierge_fsm_poc/run_demo.py`

New function: `async def _run_guided_mode(manager, fsm, classifier, registry, llm)`

Behavior:

1. Iterate `TRIP_TIMELINE` (same as scripted)
2. Show ACT headers (same as scripted)
3. Before each turn, show hint template:

   ```
   Suggested: "What's the weather like in Lake Tahoe this weekend?"
   ```

   in dim italic style
4. Prompt: `message = console.input("  You: ").strip()`
5. If empty, use `hint.suggested_message` as fallback (show `"  (using suggested message)"`)
6. Call `await _run_turn(..., override_message=message)`
7. `_pause()` between turns (no `--auto` in guided mode)

**Acceptance**:

- Shows 20-turn scenario with hints
- User can type custom messages or press Enter for suggested
- Custom messages flow through classification and LLM correctly
- ACT headers display at act boundaries

---

#### Issue 2.1.8 -- Implement _run_user_mode()

**File**: `poc/concierge_fsm_poc/run_demo.py`

New function: `async def _run_user_mode(manager, fsm, classifier, registry, llm)`

Behavior:

1. Show welcome banner: "Free-form mode. Type your message, or 'quit' to exit."
2. Infinite loop:

   ```python
   turn = 1
   while True:
       message = console.input(f"\n  [Turn {turn}] You: ").strip()
       if message.lower() in ("quit", "exit", "bye", "q"):
           break
       if not message:
           continue
       # Create minimal TurnHint
       hint = TurnHint(
           turn_number=turn,
           flow_id=f"U{turn}",
           suggested_message=message,
       )
       await _run_turn(turn, 0, hint, manager, fsm, classifier, registry, llm,
                       override_message=message)
       turn += 1
   ```

3. On exit: show session summary

**Acceptance**:

- Infinite chat loop with real FSM, classifier, LLM
- "quit" / "exit" / "bye" terminates
- Empty input skipped (prompt again)
- Turn counter increments
- Session summary on exit

---

#### Issue 2.1.9 -- Handle TurnHint defaults for user mode

**File**: `poc/concierge_fsm_poc/scenarios/trip_timeline.py`
**Lines**: 43-55 (TurnHint dataclass)

Verify that `TurnHint` default values work for user mode:

- `expected_tier=""` -- OK (not used in user mode logic)
- `expected_safety=""` -- OK
- `expected_tools=[]` -- OK
- `clarification_answers=[]` -- OK (interactive mode uses console.input)
- `interrupt_message=""` -- OK
- `special_flags={}` -- OK

May need to make `_run_turn()` resilient to missing/empty expected_tools (skip validation panel if empty).

**Acceptance**:

- `TurnHint(turn_number=1, flow_id="U1", suggested_message="Hello")` constructs without error
- `_run_turn()` works with minimal TurnHint (no crashes on empty expected_tools)

---

### Epic 2.2 -- LLM-Generated Clarification Questions

**Goal**: When the mock classifier detects gaps, use the LLM to generate a natural clarifying question instead of showing a raw gap list.

**Decision**: "LLM gap questions" -- keep MockPhase1Classifier for gap detection, LLM only generates question text.

#### Issue 2.2.1 -- Add generate_clarification_question() to GeminiClient

**File**: `poc/concierge_fsm_poc/llm/client.py`

New method after `generate_stream()` (after line ~612):

```python
async def generate_clarification_question(
    self,
    user_message: str,
    gaps: list[str],
    intent: str,
) -> str:
    """Generate a natural clarifying question for detected information gaps.

    Uses a focused prompt to produce a warm, concise question that asks
    for the missing information without listing raw field names.

    Falls back to a formatted gap list if the LLM call fails.
    """
```

Implementation:

- System prompt: "You are a warm family travel concierge. The user said: '{user_message}'. Their intent appears to be '{intent}'. The following information is missing: {', '.join(gaps)}. Generate a single natural, warm clarifying question that asks for all the missing information. Be concise (1-2 sentences). Do not list field names. Do not number items."
- Call `self._client.models.generate_content(model=self.model, contents=[...], config=GenerateContentConfig(temperature=0.7, max_output_tokens=150))`
- No tools needed
- Track: `self.total_calls += 1`, `self.total_tokens_in += ...`, `self.total_tokens_out += ...`
- Fallback on exception: `f"Could you tell me more about: {', '.join(gaps)}?"`
- Return the question text string

**Acceptance**:

- `await llm.generate_clarification_question("Book a hotel", ["check_in", "check_out", "guests"], "hotel_booking")` returns a natural question like "When would you like to check in and out, and how many guests will be staying?"
- On LLM failure, returns fallback string
- Token counters updated

---

#### Issue 2.2.2 -- Wire LLM clarification into _run_clarification()

**File**: `poc/concierge_fsm_poc/run_demo.py`
**Lines**: 688-695 (signature), 710-711 (gaps display)

1. Add `llm: GeminiClient` parameter to `_run_clarification()` signature
2. After detecting gaps (line ~710), generate question:

   ```python
   try:
       question = await llm.generate_clarification_question(
           original_message, current_phase1.gaps, current_phase1.intent
       )
   except Exception:
       question = f"Could you clarify: {', '.join(current_phase1.gaps)}?"
   ```

3. Display the question instead of raw gap list:

   ```python
   console.print(f"\n  [cyan]CONCIERGE:[/cyan] {question}")
   ```

4. Keep the `Round N/3` header and gaps list in dim for debugging:

   ```python
   console.print(f"  [dim](gaps: {gaps_text})[/dim]")
   ```

**Acceptance**:

- Clarification rounds show LLM-generated question
- Raw gaps shown in dim for debugging
- `_run_clarification()` requires `llm` parameter

---

#### Issue 2.2.3 -- Update _run_clarification() call site

**File**: `poc/concierge_fsm_poc/run_demo.py`
**Line**: ~903

Update the call from:

```python
phase1, clar_ops = await _run_clarification(
    manager, fsm, classifier, hint.suggested_message, phase1, hint
)
```

to:

```python
phase1, clar_ops = await _run_clarification(
    manager, fsm, classifier, hint.suggested_message, phase1, hint, llm
)
```

Also update any other call sites (search for `_run_clarification(` in the file).

**Acceptance**:

- `_run_clarification()` receives the `llm` argument at all call sites
- No TypeError on invocation

---

#### Issue 2.2.4 -- Add tests for generate_clarification_question()

**File**: `poc/concierge_fsm_poc/tests/test_llm_client.py` (or new `tests/test_clarification.py`)

Tests:

1. **test_clarification_question_returns_string**: Mock Gemini client, verify return type is str
2. **test_clarification_question_prompt_structure**: Verify the prompt sent to Gemini contains user_message, gaps, and intent
3. **test_clarification_question_fallback_on_error**: Simulate Gemini API error, verify fallback string returned
4. **test_clarification_question_tracks_tokens**: Verify `total_calls` incremented
5. **test_clarification_question_no_tools**: Verify no tool declarations passed to Gemini

**Acceptance**:

- 5 tests pass
- Full coverage of happy path, error path, and tracking

---

## Appendix A: File Impact Matrix

| File | Epic 1.1 | Epic 1.2 | Epic 2.1 | Epic 2.2 | Issues |
|------|----------|----------|----------|----------|--------|
| `tools/registry.py` | 1.1.1 | -- | -- | -- | Remove acknowledge registration |
| `tools/signal.py` | -- | -- | -- | -- | NO CHANGES (kept intact) |
| `tools/__init__.py` | -- | -- | -- | -- | Keep exports (tools tests still use them) |
| `react/scratchpad.py` | 1.1.2 | -- | -- | -- | Remove from COGNITIVE_TOOLS |
| `react/loop.py` | 1.1.3 | -- | -- | -- | Remove ack_sent, dynamic filter |
| `react/events.py` | -- | -- | -- | -- | NO CHANGES (keep ACK_DELIVERED type) |
| `llm/client.py` | 1.1.4 | -- | -- | 2.2.1 | Update rules + add clarification method |
| `scenarios/trip_timeline.py` | 1.1.5 | -- | 2.1.9 | -- | Remove "acknowledge" from expected_tools |
| `run_demo.py` | 1.1.6, 1.1.7 | 1.2.1-3 | 2.1.1-8 | 2.2.2-3 | Major: all 4 epics touch this file |
| `tests/test_registry.py` | 1.1.8 | -- | -- | -- | Remove acknowledge test expectations |
| `tests/test_scratchpad.py` | 1.1.9 | -- | -- | -- | Update COGNITIVE_TOOLS tests |
| `tests/test_loop.py` | 1.1.10 | -- | -- | -- | Replace acknowledge in mock registries |
| `tests/test_streaming.py` | 1.1.11 | 1.2.4 | -- | -- | Replace acknowledge + new display tests |
| `tests/test_llm_client.py` | 1.1.12 | -- | -- | 2.2.4 | System prompt tests + clarification tests |
| `tests/test_tools.py` | -- | -- | -- | -- | NO CHANGES (tests tool code, not registration) |
| `tests/test_fsm.py` | -- | -- | -- | -- | NO CHANGES (SEND_ACKNOWLEDGE is FSM action, not tool) |

---

## Appendix B: Test Impact Summary

| Test File | Current Pass/Total | Expected Changes |
|-----------|--------------------|-----------------|
| `test_registry.py` | All passing | Remove/rewrite 3 tests, update 2 constants |
| `test_scratchpad.py` | All passing | Delete 1 test, update 2 tests |
| `test_loop.py` | 55/55 | Update 3 tests (swap acknowledge -> update_beliefs) |
| `test_streaming.py` | 29/29 | Update 1 registry helper + add 3 new tests |
| `test_llm_client.py` | Partial (26 pre-fail) | Update 3 prompt tests, add 5 clarification tests |
| `test_tools.py` | All passing | NO CHANGES |
| `test_fsm.py` | All passing | NO CHANGES |

**Total new tests**: ~8 (4 LiveLoopDisplay + 5 clarification - 1 overlap)
**Total deleted tests**: ~3 (acknowledge-specific)
**Total modified tests**: ~11

---

## Appendix C: Implementation Order

```
Issue 1.1.1  registry.py           -- Remove registration
  |
  +-> Issue 1.1.2  scratchpad.py   -- Remove from COGNITIVE_TOOLS
  +-> Issue 1.1.3  loop.py         -- Remove ack_sent tracking
  +-> Issue 1.1.4  client.py       -- Update system prompt
  +-> Issue 1.1.5  trip_timeline   -- Remove from expected_tools
  +-> Issue 1.1.6  run_demo.py     -- Remove ack_log usage
  +-> Issue 1.1.7  run_demo.py     -- Remove ACK_DELIVERED handler
  |
  +-> Issues 1.1.8-12              -- All test updates (parallel)
  |
  === CHECKPOINT: run full test suite ===
  |
Issue 1.2.1  run_demo.py           -- New LiveLoopDisplay fields
  +-> Issue 1.2.2                  -- Update on_event()
  +-> Issue 1.2.3                  -- Rewrite __rich__()
  +-> Issue 1.2.4                  -- Tests
  |
  === CHECKPOINT: visual verification ===
  |
Issue 2.1.1  run_demo.py           -- CLI args
  +-> Issue 2.1.2                  -- main() routing
  +-> Issue 2.1.3                  -- _interactive_mode flag
  +-> Issue 2.1.4                  -- override_message param
  +-> Issue 2.1.5                  -- _show_user_message update
  +-> Issue 2.1.6                  -- _run_clarification interactive
  |
  +-> Issue 2.1.7                  -- _run_guided_mode()
  +-> Issue 2.1.8                  -- _run_user_mode()
  +-> Issue 2.1.9                  -- TurnHint defaults
  |
  === CHECKPOINT: test --guided and --user ===
  |
Issue 2.2.1  client.py             -- generate_clarification_question()
  +-> Issue 2.2.2                  -- Wire into _run_clarification
  +-> Issue 2.2.3                  -- Update call site
  +-> Issue 2.2.4                  -- Tests
  |
  === FINAL: full test suite + manual demo ===
```

---

## Appendix D: Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|------------|
| Tests referencing acknowledge missed | Test failures | Comprehensive grep before marking done |
| LLM now skips acknowledge but still hallucinates one | Wasted call | System prompt Rule 3 explicitly says "do not acknowledge" |
| generate_clarification_question() adds latency | Extra 1-2s per clarification round | Only called when gaps exist (5/20 turns) |
| --user mode with no scenario guard-rails | Unexpected FSM states | FSM reset on invalid transition (existing code) |
| Rich Table layout breaks on narrow terminals | Visual glitch | Fixed width=72, tested on 80-col minimum |
| Interactive mode blocks on console.input() | Async event loop blocked | `console.input()` is sync but acceptable for interactive demo |
