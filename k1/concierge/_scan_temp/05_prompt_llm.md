# 05 — Prompt & LLM Subsystem Scan

> Scan date: 2026-04-04
> Files scanned: 18 (9 prompt, 9 llm)
> Purpose: Comprehensive audit of the Prompt assembly and LLM adapter subsystems

---

## TABLE OF CONTENTS

1. [Prompt Subsystem Overview](#1-prompt-subsystem-overview)
2. [prompt/__init__.py — Public API Surface](#2-prompt__init__py--public-api-surface)
3. [prompt/mode.py — PromptMode Enum & Mode Resolution](#3-promptmodepy--promptmode-enum--mode-resolution)
4. [prompt/affect.py — Affect Band Computation & Modulation](#4-promptaffectpy--affect-band-computation--modulation)
5. [prompt/sections.py — 20 Composable Prompt Sections & Assembly Maps](#5-promptsectionspy--20-composable-prompt-sections--assembly-maps)
6. [prompt/scenario_templates.py — Mode-Specific Scenario Data Templates](#6-promptscenario_templatespy--mode-specific-scenario-data-templates)
7. [prompt/clarify_depth.py — Clarification Depth Tracking](#7-promptclarify_depthpy--clarification-depth-tracking)
8. [prompt/domain_rules.py — Domain-Specific Safety Rules](#8-promptdomain_rulespy--domain-specific-safety-rules)
9. [prompt/back_prompt.py — Back LLM System Prompt](#9-promptback_promptpy--back-llm-system-prompt)
10. [prompt/builder.py — DynamicPromptBuilder & BuiltContext](#10-promptbuilderpy--dynamicpromptbuilder--builtcontext)
11. [LLM Subsystem Overview](#11-llm-subsystem-overview)
12. [llm/__init__.py — Public API Surface](#12-llm__init__py--public-api-surface)
13. [llm/types.py — Provider-Agnostic Type Definitions](#13-llmtypespy--provider-agnostic-type-definitions)
14. [llm/ports.py — IConciergeModelPort Protocol](#14-llmportspy--iconciergeModelport-protocol)
15. [llm/model_selection.py — Capability-Based Model Routing](#15-llmmodel_selectionpy--capability-based-model-routing)
16. [llm/gemini_adapter.py — Gemini Provider Implementation](#16-llmgemini_adapterpy--gemini-provider-implementation)
17. [llm/model_hub_bridge.py — ModelHubPOCBridge to K1 Model Hub](#17-llmmodel_hub_bridgepy--modelhubpocbridge-to-k1-model-hub)
18. [llm/test_adapter.py — Deterministic Test Adapter](#18-llmtest_adapterpy--deterministic-test-adapter)
19. [llm/test_model_hub_bridge.py — Test Model Hub Bridge](#19-llmtest_model_hub_bridgepy--test-model-hub-bridge)
20. [llm/validator.py — LLM Output Validator](#20-llmvalidatorpy--llm-output-validator)
21. [Prompt Construction Pipeline (End-to-End)](#21-prompt-construction-pipeline-end-to-end)
22. [Cross-Component Import Map](#22-cross-component-import-map)
23. [Error Handling Patterns](#23-error-handling-patterns)
24. [Architecture Summary & Key Observations](#24-architecture-summary--key-observations)

---

## 1. Prompt Subsystem Overview

The `k1.concierge.prompt` package implements **mode-driven prompt assembly** for the Front LLM. Rather than a monolithic system prompt, 20 named prompt sections are composed per-mode, with affect modulation, domain rules, clarification depth, and scenario-specific data layered on top.

**Design reference:** V2 Design Doc Section 6.1 & 16.3

### Architecture Pattern

```
determine_mode() → PromptMode (10 variants)
       ↓
DynamicPromptBuilder.build() → BuiltContext
       ↓ (9-stage pipeline)
  1. MODE_SECTIONS[mode] → ordered section keys
  2. MODE_EXAMPLES[mode] → in-context examples
  3. AFFECT_TONE_BLOCKS[band] + affect×mode interaction
  4. CLARIFY_DEPTH_BLOCKS[depth] (CLARIFY_ASK only)
  5. DOMAIN_RULES[domain] (applicable modes only)
  6. ANTI_PATTERN_KEYS[mode] → mode-specific anti-patterns
  7. SCENARIO_DATA_TEMPLATES[mode].format(**data)
  8. SS section rendering via SECTION_RENDERERS
  9. Affect modifier application (iterations, tools, length hints)
       ↓
BuiltContext(system_prompt, messages, tools, max_iterations, mode, affect_band)
```

**Back LLM** uses a separate, simpler path: `build_back_prompt()` does template substitution on a constant ~1800-word prompt.

---

## 2. prompt/__init__.py — Public API Surface

**Purpose:** Package re-export hub. Aggregates all public symbols from sub-modules.

**Exports (41 symbols in `__all__`):**

| Category | Symbols |
|----------|---------|
| Mode | `PromptMode`, `determine_mode`, `TOOL_ALLOWLIST`, `get_tool_allowlist`, `MAX_ITERATIONS_TABLE`, `CRISIS_ITERATIONS_TABLE` |
| Affect | `AffectBand`, `compute_affect_band`, `AFFECT_TONE_BLOCKS`, `AffectModifiers`, `compute_affect_modifiers`, `AFFECT_MODIFIERS`, `AFFECT_MODE_INTERACTIONS`, `get_affect_mode_interaction` |
| Sections | `PROMPT_SECTIONS`, `MODE_SECTIONS`, `ANTI_PATTERN_KEYS`, `MODE_EXAMPLES` |
| Scenario | `SCENARIO_DATA_TEMPLATES` |
| Clarify | `ClarificationDepthState`, `CLARIFY_DEPTH_BLOCKS`, `get_clarify_depth_block`, `ClarificationTracker` |
| Domain | `DOMAIN_RULES`, `get_domain_rules`, `DOMAIN_SAFETY_FLOORS`, `DOMAIN_APPLICABLE_MODES`, `get_domain_safety_floor`, `is_domain_applicable` |
| Iterations | `get_max_iterations` |
| Builder | `BuiltContext`, `DynamicPromptBuilder`, `SSReadConfig`, `SS_READ_CONFIGS`, `apply_affect_modifiers` |

**Cross-component imports:** None directly — all imports are from sibling prompt sub-modules.

---

## 3. prompt/mode.py — PromptMode Enum & Mode Resolution

**Purpose:** Defines the 10-variant cognitive mode enum and the resolution function that maps FSM state + event topic + SS signals to exactly one mode.

### Class: `PromptMode(Enum)`

10 values — each determines tool subset, SS sections, prompt sections, examples, iteration limits:

| Mode | Value | Description |
|------|-------|-------------|
| `STANDARD` | `"standard"` | Normal user input, full cognitive processing |
| `CLARIFY_ASK` | `"clarify_ask"` | Front detected ambiguity, asking user |
| `CLARIFY_RESOLVE` | `"clarify_resolve"` | User answered a clarification question |
| `HITL_RELAY` | `"hitl_relay"` | Back suspended, present question to user |
| `HITL_RESOLVE` | `"hitl_resolve"` | User answered HITL question |
| `PRESENT` | `"present"` | Delivering task results |
| `WEAVE` | `"weave"` | Presenting async results mid-conversation |
| `CANCEL` | `"cancel"` | Confirming/handling cancellation |
| `INTERRUPT` | `"interrupt"` | New user input while task in progress |
| `ERROR` | `"error"` | Task failed, explaining gracefully |

### Data Tables

**TOOL_ALLOWLIST: `dict[PromptMode, list[str]]`**

Per-mode tool name lists. Key observations:
- STANDARD: 8 base tools (update_beliefs, update_scoreboard, update_clarifications, update_narrative, recall_memory, summarize_context, dispatch_task) + conditional refine_affect, promote_belief
- HITL_RELAY: Empty list (pure text-only, no tools)
- INTERRUPT: All 10 tools unconditionally
- WEAVE: update_beliefs, update_narrative, update_scoreboard (V3 E0.1.2 addition)

**MAX_ITERATIONS_TABLE / CRISIS_ITERATIONS_TABLE: `dict[PromptMode, int]`**

| Mode | Normal | Crisis |
|------|--------|--------|
| STANDARD | 6 | 4 |
| CLARIFY_ASK | 3 | 2 |
| CLARIFY_RESOLVE | 5 | 4 |
| HITL_RELAY | 2 | 2 |
| HITL_RESOLVE | 3 | 2 |
| PRESENT | 3 | 2 |
| WEAVE | 3 | 2 |
| CANCEL | 3 | 2 |
| INTERRUPT | 6 | 4 |
| ERROR | 2 | 2 |

### Function: `get_tool_allowlist(mode, affect_confidence, tier) → list[str]`

Conditional tool inclusion logic:
- `refine_affect` added when `affect_confidence < threshold` (config-driven, Phase 1 uncertain)
- `promote_belief` added when `tier != "LOW"` (MEDIUM/HIGH complexity)
- HITL_RELAY is strictly text-only — no conditional tools ever added

### Function: `get_max_iterations(mode, affect_band) → int`

Standalone iteration budget. Config-driven with fallback to module tables. Crisis band uses `CRISIS_ITERATIONS_TABLE`.

### Function: `determine_mode(fsm_state, envelope_topic, clarification_state, task_state, affect, routing_metadata) → PromptMode`

**Resolution priority (first match wins):**

1. **Explicit FSM state:** `CANCELLING` → CANCEL, `INTERRUPT_HANDLING` → INTERRUPT
2. **Routing metadata:** `routing_metadata.interrupt_origin` → INTERRUPT (transient FSM state may have already moved)
3. **FSM state + event topic:**
   - `CLARIFYING_USER` + `user_input` → CLARIFY_RESOLVE
   - `CLARIFYING_USER` + other → CLARIFY_ASK
   - `CLARIFYING_WORKER` + `user_input` → HITL_RESOLVE
   - `CLARIFYING_WORKER` + other → HITL_RELAY
4. **Event-topic-driven:**
   - `task_complete` → PRESENT
   - `task_failed` → ERROR
   - `weave_batch` → WEAVE
   - `task_suspended` → HITL_RELAY
5. **SS-signal-driven (user_input only):**
   - Suspended tasks exist → HITL_RESOLVE
   - `blocking_gaps > 0` → CLARIFY_RESOLVE
6. **Default:** STANDARD

### Cross-Component Imports

```python
from k1.concierge.config import get_config
from k1.concierge.bus.topics import (
    TOPIC_TASK_COMPLETE, TOPIC_TASK_FAILED, TOPIC_TASK_SUSPENDED,
    TOPIC_USER_INPUT, TOPIC_WEAVE_BATCH,
)
```

V3 E0.1.4 replaced inline string literals with canonical bus topic imports.

---

## 4. prompt/affect.py — Affect Band Computation & Modulation

**Purpose:** Computes an `AffectBand` from SS `affective_now`, then resolves to `AffectModifiers` that modulate prompt parameters.

### Class: `AffectBand` (frozen dataclass)

```python
@dataclass(frozen=True)
class AffectBand:
    band: Literal["crisis", "elevated", "neutral", "positive", "low"]
```

### Function: `compute_affect_band(affect: dict | None) → AffectBand`

Band resolution logic (valence -1..1, arousal 0..1):

| Band | Condition |
|------|-----------|
| crisis | valence < -0.5 AND arousal > 0.7 |
| low | valence < -0.3 AND arousal < 0.4 |
| positive | valence > 0.5 AND arousal > 0.6 |
| elevated | \|valence\| > 0.3 |
| neutral | default |

Returns `neutral` when `affect` is None.

### Data: `AFFECT_TONE_BLOCKS: dict[str, str]`

Five tone blocks injected into the assembled prompt:
- **crisis:** "Calm, structured language. No fluff. Lead with ACTION." Max 3 numbered options.
- **low:** "Gentle, brief language. Don't force cheerfulness."
- **neutral:** "Efficient but let personality show. Light wit."
- **positive:** "Full personality. Match energy. Celebrate."
- **elevated:** "Acknowledge feeling in ONE sentence, then action."

### Class: `AffectModifiers` (frozen dataclass)

```python
@dataclass(frozen=True)
class AffectModifiers:
    max_iterations_delta: int = 0
    examples_count_override: int | None = None
    history_window_delta: int = 0
    tone_prefix: str = ""
    response_length_hint: str = ""
    skip_refine_affect: bool = False
    max_response_tokens: int | None = None      # OPP-3: LLM call boundary cap
    vocabulary_tier: str = "standard"            # "simple" | "standard" | "rich"
    tool_budget_override: int | None = None      # OPP-3: max tool calls this turn
```

### Data: `AFFECT_MODIFIERS: dict[str, AffectModifiers]`

| Band | iter_delta | examples | history_delta | max_tokens | vocab | tool_budget | skip_refine |
|------|-----------|----------|---------------|------------|-------|-------------|-------------|
| crisis | -1 | 1 | -5 | 512 | simple | 2 | True |
| low | 0 | 1 | 0 | 1024 | simple | 3 | True |
| neutral | 0 | None | 0 | None | standard | None | False |
| positive | 0 | None | 0 | 2048 | rich | None | False |
| elevated | 0 | None | 0 | 1536 | standard | None | False |

### Function: `compute_affect_modifiers(band: AffectBand) → AffectModifiers`

Simple lookup in `AFFECT_MODIFIERS` dict. Falls back to neutral.

### Function: `apply_affect_hard_constraints(modifiers, llm_params) → dict`

OPP-3 generalized kernel primitive — applies hard constraints at LLM call boundary:
- Caps `max_tokens` to `modifiers.max_response_tokens`
- Sets `max_tool_calls` from `modifiers.tool_budget_override`

### Cross-Component Imports

None beyond stdlib. Self-contained module.

---

## 5. prompt/sections.py — 20 Composable Prompt Sections & Assembly Maps

**Purpose:** The monolithic system prompt decomposed into 20 named sections. Each mode selects a subset via `MODE_SECTIONS`. Builder concatenates only selected sections in order.

### Data: `PROMPT_SECTIONS: dict[str, str]` — 20 Keys

| Key | Included In | Approx Tokens | Description |
|-----|-------------|---------------|-------------|
| `IDENTITY` | ALL modes | ~150 | Core identity ("the Concierge, part of the family"), language rules, identity boundaries, time awareness |
| `PERSONALITY` | STANDARD, INTERRUPT, PRESENT, WEAVE | ~180 | Voice, humor rules, casual conversation, format matching, greeting rules, dead-giveaway phrase blacklist |
| `REACT_RHYTHM` | STANDARD, CLARIFY_RESOLVE, INTERRUPT | ~200 | Full Think-Act-Observe loop, parallel tool calls, mandatory recall, iteration guidelines |
| `REACT_RHYTHM_REDUCED` | CLARIFY_ASK, HITL_RESOLVE, CANCEL, PRESENT, ERROR | ~80 | Short version: tools + text response, budget |
| `STATE_INTERP` | STANDARD, CLARIFY_RESOLVE, INTERRUPT | ~200 | How to read affective_now, beliefs_active, task_state, clarifications, open_commitments |
| `STATE_INTERP_CLARIFY` | CLARIFY_ASK | ~60 | Focused on clarifications blocking_gaps. Contains `{open_gaps_list}` placeholder |
| `STATE_INTERP_TASK` | HITL_RESOLVE | ~60 | Focused on task_state SUSPENDED |
| `STATE_INTERP_PRESENT` | PRESENT | ~60 | Focused on task_state COMPLETED + task_artifacts |
| `COGNITIVE_DISCIPLINE` | STANDARD, INTERRUPT | ~150 | When to call cognitive tools (update_beliefs, update_scoreboard, refine_affect, update_narrative) |
| `COGNITIVE_DISCIPLINE_REDUCED` | CLARIFY_RESOLVE | ~50 | Light version: only update_beliefs and update_clarifications |
| `DISPATCH_RULES` | STANDARD, CLARIFY_RESOLVE, INTERRUPT | ~350 | When to dispatch, multi-intent handling, reference resolution, depends_on rules |
| `EMOTIONAL_CALIB` | ALL modes | ~100 | Tone matching to user emotional state |
| `SAFETY_HITL` | STANDARD, HITL_RELAY, HITL_RESOLVE, INTERRUPT | ~300 | GREEN/AMBER/RED safety bands, HITL relay rules |
| `WEAVE_PROTOCOL` | WEAVE | ~100 | Respond to current topic FIRST, then bridge to async result |
| `ANTI_PATTERNS_FULL` | STANDARD, INTERRUPT | ~150 | Chatbot tells, system exposure, behavioral anti-patterns |
| `ANTI_PATTERNS_CLARIFY` | CLARIFY_ASK, CLARIFY_RESOLVE | ~50 | No dispatch with blocking gaps, one question per turn |
| `ANTI_PATTERNS_HITL` | HITL_RELAY, HITL_RESOLVE | ~50 | No raw HILRequest JSON, no "system needs" |
| `ANTI_PATTERNS_PRESENT` | PRESENT | ~40 | No verbatim results, no unsolicited dispatch |
| `ANTI_PATTERNS_WEAVE` | WEAVE | ~30 | Don't ignore current topic, batch results |
| `ANTI_PATTERNS_CANCEL` | CANCEL | ~30 | No re-dispatch, no questioning cancellation |
| `ANTI_PATTERNS_ERROR` | ERROR | ~30 | No error codes, no jargon |
| `INTERRUPT_RULES` | INTERRUPT | ~200 | Classify interrupt (ack/constraint/new topic/cancel), never re-dispatch in-flight tasks |
| `PROACTIVE_INTELLIGENCE` | STANDARD, INTERRUPT | ~400 | Proactive recall, risk alerts, multi-concern briefings, HITL question offers, cross-member awareness |
| `COMMITMENT_TRACKING` | STANDARD, INTERRUPT, PRESENT, WEAVE | ~200 | Detect, record, surface deferred promises |

### Data: `MODE_SECTIONS: dict[PromptMode, list[str]]`

Ordered section keys per mode:

| Mode | Sections (in order) |
|------|---------------------|
| STANDARD | IDENTITY, PERSONALITY, REACT_RHYTHM, STATE_INTERP, COGNITIVE_DISCIPLINE, COMMITMENT_TRACKING, PROACTIVE_INTELLIGENCE, DISPATCH_RULES, EMOTIONAL_CALIB, SAFETY_HITL, ANTI_PATTERNS_FULL |
| CLARIFY_ASK | IDENTITY, REACT_RHYTHM_REDUCED, STATE_INTERP_CLARIFY, EMOTIONAL_CALIB |
| CLARIFY_RESOLVE | IDENTITY, REACT_RHYTHM, STATE_INTERP, COGNITIVE_DISCIPLINE_REDUCED, DISPATCH_RULES, EMOTIONAL_CALIB |
| HITL_RELAY | IDENTITY, EMOTIONAL_CALIB, SAFETY_HITL |
| HITL_RESOLVE | IDENTITY, REACT_RHYTHM_REDUCED, STATE_INTERP_TASK, EMOTIONAL_CALIB, SAFETY_HITL |
| PRESENT | IDENTITY, PERSONALITY, STATE_INTERP_PRESENT, COMMITMENT_TRACKING, EMOTIONAL_CALIB |
| WEAVE | IDENTITY, PERSONALITY, WEAVE_PROTOCOL, COMMITMENT_TRACKING, EMOTIONAL_CALIB |
| CANCEL | IDENTITY, REACT_RHYTHM_REDUCED, EMOTIONAL_CALIB |
| INTERRUPT | IDENTITY, PERSONALITY, REACT_RHYTHM, STATE_INTERP, COGNITIVE_DISCIPLINE, COMMITMENT_TRACKING, INTERRUPT_RULES, EMOTIONAL_CALIB, SAFETY_HITL, ANTI_PATTERNS_FULL |
| ERROR | IDENTITY, EMOTIONAL_CALIB |

### Data: `ANTI_PATTERN_KEYS: dict[PromptMode, str]`

Mode → anti-pattern section key for modes not using ANTI_PATTERNS_FULL directly. 8 entries (STANDARD and INTERRUPT already include ANTI_PATTERNS_FULL in MODE_SECTIONS).

### Data: `MODE_EXAMPLES: dict[PromptMode, str]`

In-context examples per mode. Each mode gets 1-2 targeted examples:
- STANDARD: 5 examples (single intent, proactive briefing, casual chat, mixed language, capabilities question)
- CLARIFY_ASK: 1 example (blocking gap detected)
- CLARIFY_RESOLVE: 1 example (user answers clarification)
- HITL_RELAY: 2 examples (approval with consequences, selection)
- HITL_RESOLVE: 1 example (user approves)
- PRESENT: 1 example (task result presentation)
- WEAVE: 1 example (async result during conversation)
- CANCEL: 1 example (user cancels)
- INTERRUPT: "Same as STANDARD examples"
- ERROR: 1 example (task failed gracefully)

### SS Section Renderers (11 renderers with full/slim variants)

Dispatch table `SECTION_RENDERERS: dict[str, tuple]` maps section names to (full_fn, slim_fn) pairs:

| Section | Full Renderer | Slim Renderer |
|---------|--------------|---------------|
| task_state | `to_prompt()` delegation | `to_slim_prompt()` delegation |
| task_artifacts | `to_prompt()` delegation | `to_slim_prompt()` delegation |
| history_active | `format_for_prompt(n=window)` | `format_for_prompt(n=min(5, window))` |
| beliefs_active | SVO lines with confidence + entities + time/location | Fact count + pinned fact IDs |
| scoreboard | Referents + topic + QUD stack + open commitments | Topic + referent count + commitment count |
| clarifications | Pending + blocking items | Count of pending |
| narrative_active | Thread title + goal + entities | Thread name only |
| affective_now | Emotion + intensity + valence + arousal + tone hints + style hints | `emotion (intensity) | Style: pref` |
| control | Full `get_metadata()` dict | FSM state + safety band |
| persona | All preferences key/value | Preference key names |
| temporal | Canonical temporal anchor, windows, freshness, resolved expressions | One-line temporal grounding summary |

Temporal prompt rendering reads the canonical `temporal` SessionState section produced by `k1.temporal`.

The legacy lazy temporal-context fallback has been removed; missing temporal state is handled as an unavailable grounding section.

**Affective now renderer** includes:
- Tone fine-tuning from `AffectiveMirror` (Experience Layer): warmth, formality, pace, mirror_intensity
- Response style from `ResponseStyleAdapter` (Experience Layer): length_preference, message_style, verbosity_level

### Cross-Component Imports

```python
from k1.concierge.prompt.mode import PromptMode  # sibling
```

---

## 6. prompt/scenario_templates.py — Mode-Specific Scenario Data Templates

**Purpose:** Format strings per mode for injecting mode-specific payload data (task results, HITL requests, error details) into the assembled prompt.

### Data: `SCENARIO_DATA_TEMPLATES: dict[PromptMode, str]`

| Mode | Template Placeholders | Notes |
|------|----------------------|-------|
| STANDARD | `{active_member}`, `{family_context}`, `{async_results_context}` | Family context |
| PRESENT | `{task_description}`, `{task_result_summary}`, `{artifacts}` | Task result presentation |
| WEAVE | `{urgency_label}`, `{emotional_context}`, `{result_count}`, `{results_summary}`, `{current_thread}` | Async result weaving |
| HITL_RELAY | `{hil_type}`, `{hil_question}`, `{hil_options}`, `{hil_side_effects}` | Structured HITL → natural language |
| HITL_RESOLVE | `{suspended_task_summary}`, `{original_question}`, `{user_answer}` | User's HITL answer |
| ERROR | `{task_description}`, `{failure_reason}`, `{partial_results}` | Graceful error explanation |
| CANCEL | `{task_id}`, `{task_action}`, `{task_status}` | Cancellation confirmation |
| CLARIFY_ASK | `""` (empty) | Context from SS clarifications |
| CLARIFY_RESOLVE | `""` (empty) | User answer in messages |
| INTERRUPT | Same as STANDARD | Family context |

### Cross-Component Imports

```python
from k1.concierge.prompt.mode import PromptMode
```

---

## 7. prompt/clarify_depth.py — Clarification Depth Tracking

**Purpose:** Prevents "20 questions" anti-pattern. Tracks per-gap clarification depth, escalating strategy from open question → specific options → best guess.

### Class: `ClarificationDepthState` (mutable dataclass)

```python
@dataclass
class ClarificationDepthState:
    field: str = ""                           # Gap field name (e.g. "dates", "budget")
    depth: int = 0                            # 0=first ask, 1=re-ask, 2=final
    previous_questions: list[str] = field(...)
    max_depth: int = 2                        # Config-driven via get_config().prompt.max_clarify_depth
```

**Key methods:**
- `increment()` — depth += 1 (capped at max_depth)
- `should_guess() → bool` — True when depth >= max_depth
- `reset()` — Clear depth, field, and previous_questions
- `to_dict() / from_dict()` — Serialization for SS persistence

### Data: `CLARIFY_DEPTH_BLOCKS: dict[int, str]`

| Depth | Strategy |
|-------|----------|
| 0 | Open question. ONE question. No options. Natural phrasing. |
| 1 | Specific options (2-3). Reference prior answer. Contains `{field}` and `{previous_question}` placeholders. |
| 2 | Best guess and proceed. No more asking. `{field}` placeholder. |

### Function: `get_clarify_depth_block(depth, field_name, previous_question) → str`

Returns formatted depth block with placeholder interpolation for depth >= 1.

### Class: `ClarificationTracker`

Multi-gap depth manager. Reads from / writes to `ss.clarifications`.

```python
class ClarificationTracker:
    _states: dict[str, ClarificationDepthState]
```

**Key methods:**
- `load_from_dict(data)` — Load from serialized SS clarifications (key: `"depth_states"`)
- `get_depth(field) → int` — Current depth (0 if never asked)
- `get_state(field) → ClarificationDepthState` — Get or create
- `record_question(field, question)` — Append question, increment depth
- `is_exhausted(field) → bool` — True if should_guess()
- `get_prompt_block(field) → str` — Get formatted depth block
- `active_fields → list[str]` — Currently tracked fields
- `to_dict()` — Serialize for SS persistence

### Cross-Component Imports

```python
from k1.concierge.config import get_config
```

---

## 8. prompt/domain_rules.py — Domain-Specific Safety Rules

**Purpose:** When a domain is detected (from Phase 1 classification or `ss.control.domain_context`), domain-specific rules are injected into the prompt.

### Data: `DOMAIN_RULES: dict[str, str]` — 8 Domains

| Domain | Safety Floor | Key Rules |
|--------|-------------|-----------|
| health | AMBER | Never diagnose. Can schedule/find providers. |
| finance | AMBER | State exact amounts. >$500 requires verbal confirmation. No auto-approve recurring. |
| elder_care | GREEN | Simpler language. Max 3 options. Confirm understanding. Slower pace. |
| children | AMBER | Route through parent profile. Filter age-inappropriate content. |
| legal | RED | Never provide legal advice. Can find professionals. |
| emergency | RED | User safety first. Provide emergency numbers IMMEDIATELY. No confirmation delays. |
| iot | GREEN | Confirm device actions. State device name. Safety-critical always confirm. |
| communication | GREEN | No impersonation. Drafts require approval. Never send without consent. |

### Data: `DOMAIN_SAFETY_FLOORS: dict[str, str]`

Maps domain → minimum safety band (GREEN/AMBER/RED). Cumulative with mode's existing safety band.

### Data: `DOMAIN_APPLICABLE_MODES: dict[str, list[str] | str]`

Which modes each domain's rules apply to:
- `"ALL"`: elder_care, emergency
- Specific modes: health → [standard, clarify_ask, hitl_relay], finance → [standard, hitl_relay, present], etc.

### Functions

- `get_domain_rules(domain) → str` — Returns prompt block or ""
- `get_domain_safety_floor(domain) → str` — Returns "GREEN"/"AMBER"/"RED", defaults to "GREEN"
- `is_domain_applicable(domain, mode_value) → bool` — Check if rules apply for mode

### Coherence Hierarchy

```
DOMAIN_RULES > SAFETY_HITL > AFFECT_TONE_BLOCKS > CLARIFY_DEPTH_BLOCKS > base PROMPT_SECTIONS
```

### Cross-Component Imports

None. Self-contained module.

---

## 9. prompt/back_prompt.py — Back LLM System Prompt

**Purpose:** Constant ~1800-word system prompt for the Back (Worker) LLM. Uses simple template substitution, NOT mode-driven assembly.

### Constant: `BACK_SYSTEM_PROMPT`

8 sections in the prompt:

1. **IDENTITY** — "You are the Worker. Pure executor. Never produce text for human consumption."
2. **REACT EXECUTION PROTOCOL** — 8-step mandatory sequence:
   - ORIENT: Read task, check beliefs. CRITICAL: check task_artifacts first, then recall_memory for info retrieval
   - CHECK EXISTING WORK: Don't re-do completed work
   - ASSESS CAPABILITY KNOWLEDGE: Pure retrieval → recall_memory. External action → discover_capabilities
   - DISCOVER: `discover_capabilities(intent, domain)` — ONLY for external services
   - SAFETY CHECK: RED → refuse. side_effects + user-requested → execute. side_effects + discovered → request approval
   - INVOKE: `batch_invoke_capabilities()` for 2+, `invoke_capability()` for 1. Max 1 retry.
   - WEB SEARCH + FETCH WORKFLOW: Mandatory follow-up with web_fetch after web_search
   - EVALUATE + SUBMIT
3. **TOOL SELECTION RULES** — Dynamic `{available_tools_note}` based on tier
4. **CAPABILITY DOMAINS** — 11 domain names (search, messaging, productivity, shopping, household, school, health, transport, iot, finance, calendar, family_activities, travel)
5. **TOOL USAGE ORDER** — recall_memory → discover_capabilities → invoke_capability → batch_invoke → spawn_via_fabric → execute_workflow → submit_result
6. **RESULT FORMAT** — submit_result structure (final_answer, results, artifacts_created)
7. **AMBIGUITY HANDLING** — Max 2 suspensions, pick best on 3rd
8. **ANTI-PATTERNS** — 14 anti-patterns including "never discover same intent twice"

Template variables: `{task_json}`, `{beliefs_summary}`, `{task_state_summary}`, `{artifacts_summary}`, `{safety_band}`, `{persona_prefs}`, `{max_tool_calls}`, `{available_tools_note}`

### Function: `build_back_prompt(task, beliefs, referents, task_state, task_artifacts, safety_band, persona_prefs, max_tool_calls) → str`

- Determines tier from task dict (`task.tier` or `task.complexity_tier`)
- Generates `available_tools_note` per tier:
  - LOW: recall_memory, discover_capabilities, invoke_capability, batch_invoke_capabilities, submit_result
  - MEDIUM: adds spawn_via_fabric, execute_workflow
  - HIGH: ALL tools
- Template-substitutes all variables into `BACK_SYSTEM_PROMPT`

### Cross-Component Imports

```python
from k1.concierge.config import get_config
```

---

## 10. prompt/builder.py — DynamicPromptBuilder & BuiltContext

**Purpose:** The central prompt assembly engine. 9-stage pipeline producing `BuiltContext` for one Front LLM invocation.

### Class: `SSReadConfig` (frozen dataclass)

```python
@dataclass(frozen=True)
class SSReadConfig:
    section: str                                    # SS section name
    read_mode: Literal["full", "slim", "skip"]
    history_window: int = 20                        # Only for history_active
```

### Data: `SS_READ_CONFIGS: dict[PromptMode, list[SSReadConfig]]`

All 10 modes mapped. Per-mode configurations specify which SS sections to read and at what fidelity. Key patterns:

| Section | STANDARD | CLARIFY_ASK | HITL_RELAY | PRESENT | ERROR |
|---------|----------|-------------|------------|---------|-------|
| temporal_context | full | slim | slim | full | slim |
| beliefs_active | full | slim | — | slim | — |
| scoreboard | full | slim | — | — | — |
| affective_now | full | full | full | full | full |
| clarifications | full | full | — | — | — |
| narrative_active | full | — | — | slim | slim |
| control | full | slim | slim | slim | slim |
| history_active | full/20 | full/10 | — | full/10 | full/5 |
| persona | full | full | full | full | full |
| task_state | full | — | full | full | full |
| task_artifacts | full | — | — | full | slim |

### Class: `BuiltContext` (dataclass)

```python
@dataclass
class BuiltContext:
    system_prompt: str
    messages: list[ModelMessage] = field(...)
    tools: list[ToolSchema] = field(...)
    max_iterations: int = 6
    mode: PromptMode = PromptMode.STANDARD
    affect_band: str = "neutral"
    estimated_tokens: int = 0
```

### Function: `apply_affect_modifiers(modifiers, base_max_iterations, prompt_parts, tools) → tuple[int, list[ToolSchema]]`

Standalone helper:
1. Adjust max_iterations by delta (minimum 1)
2. Inject response_length_hint into prompt_parts
3. Remove refine_affect from tools if skip_refine_affect

### Class: `DynamicPromptBuilder`

**Constants:**
- `CONTEXT_WINDOW = 128_000` (Gemini 2.5 Pro)
- `SAFETY_MARGIN = 0.80`
- `MAX_CONTEXT_TOKENS = 102,400`
- `CHARS_PER_TOKEN = 4`

All overridable via config properties.

**Method: `build(mode, affect_band, history_messages, all_tool_schemas, scenario_data, clarify_depth, domain, affect_confidence, tier, ss) → BuiltContext`**

9-stage pipeline:

1. **Select prompt sections** from `MODE_SECTIONS[mode]` → concatenate text
2. **Append mode example** from `MODE_EXAMPLES[mode]`
3. **Append affect tone block** from `AFFECT_TONE_BLOCKS[band]` (skip neutral) + affect×mode interaction block
4. **Append clarification depth block** (CLARIFY_ASK only, format placeholders from scenario_data)
5. **Append domain rules** (only for applicable modes per `is_domain_applicable()`) — RC-3 fix
6. **Append anti-pattern subset** from `ANTI_PATTERN_KEYS[mode]`
7. **Format scenario data** using `SCENARIO_DATA_TEMPLATES[mode].format(**data)` with key/value fallback
8. **Read SS sections** via `_read_ss_sections(ss, configs)` using `SECTION_RENDERERS` dispatch table
9. **Apply affect modifiers** — iteration adjustment, tool filtering, length hints

Post-assembly:
- Interpolate `{max_iterations}` placeholder in assembled text
- Interpolate `{open_gaps_list}` from scenario_data (RC-1 fix)
- Filter tools by mode allowlist with conditional inclusion
- Estimate tokens, compress if exceeding budget (truncate from end)
- Return `BuiltContext`

**Method: `_read_ss_sections(ss, configs) → str`**

For each `SSReadConfig`:
1. Resolve virtual section name via `SECTION_SOURCE_MAP`
2. Get section from `ss.get_section(name)` via `_safe_get_ss_section()`
3. Lookup renderer in `SECTION_RENDERERS`
4. Call full_fn or slim_fn based on read_mode
5. Assemble as `"== SESSION STATE ==\n\n## section_name\nrendered_text"`

**Method: `_compress_prompt(prompt) → str`**

Last-resort truncation: cuts to `max_context_tokens * chars_per_token` chars, appends `"[Context truncated for budget]"`.

### Cross-Component Imports

```python
from k1.concierge.llm.types import ModelMessage, ToolSchema
from k1.concierge.config import get_config
from k1.concierge.prompt.affect import (AffectBand, AffectModifiers, compute_affect_modifiers, ...)
from k1.concierge.prompt.clarify_depth import CLARIFY_DEPTH_BLOCKS
from k1.concierge.prompt.domain_rules import get_domain_rules, is_domain_applicable
from k1.concierge.prompt.mode import (PromptMode, get_tool_allowlist, ...)
from k1.concierge.prompt.scenario_templates import SCENARIO_DATA_TEMPLATES
from k1.concierge.prompt.sections import (PROMPT_SECTIONS, MODE_SECTIONS, ...)
```

---

## 11. LLM Subsystem Overview

The `k1.concierge.llm` package implements a **provider-agnostic LLM interface** via the hexagonal port/adapter pattern. Every actor calls `IConciergeModelPort`. No actor imports `google.genai`, `openai`, or `anthropic`.

### Architecture Pattern

```
Callers (Front, Back, Planner, agents)
       ↓
IConciergeModelPort (Protocol)
       ↓
┌──────────────────────────────────────────────┐
│ Adapters:                                    │
│  - GeminiConciergeAdapter (production)       │
│  - TestConciergeAdapter (testing)            │
│  - ModelHubPOCBridge (K1 bridge to model_hub)│
│  - TestModelHubBridge (test K1 bridge)       │
└──────────────────────────────────────────────┘
       ↓
model_selection.select_model(capability, actor, hint)
       ↓
Provider SDK (google.genai -- only in GeminiConciergeAdapter)
```

---

## 12. llm/__init__.py — Public API Surface

**Purpose:** Package re-export hub. Lazy import for `GeminiConciergeAdapter` to avoid requiring google-genai SDK at import time.

**Exports (21 symbols in `__all__`):**

| Category | Symbols |
|----------|---------|
| Protocol | `IConciergeModelPort` |
| Types | `Capability`, `ConciergeModelRequest`, `ConciergeModelResponse`, `FinishReason`, `ModelMessage`, `StreamChunk`, `ThinkingLevel`, `ToolCallResult`, `ToolResultMessage`, `ToolSchema` |
| Adapters | `TestConciergeAdapter` (GeminiConciergeAdapter lazily imported) |
| Model Selection | `DEFAULT_MODEL`, `MODEL_HINT_OVERRIDES`, `MODEL_SELECTION_TABLE`, `select_model` |
| Validation | `LLMOutputValidator`, `ValidationResult` |
| Helpers | `tool_result_to_message`, `response_to_assistant_message` |

---

## 13. llm/types.py — Provider-Agnostic Type Definitions

**Purpose:** All LLM types used across the system. No provider SDK types leak outside the adapter boundary.

### Enum: `Capability(str, Enum)`

| Value | Description |
|-------|-------------|
| `CHAT` | Text in, text out (acks, error explanations) |
| `TOOL_CALL` | Text in, tool calls + text out (ReAct loops) |
| `STRUCTURED` | Text in, schema-valid JSON out (dispatch intent parsing) |
| `STREAM` | Streaming variant of CHAT |
| `REASON` | Chain-of-thought + answer (complex planning) |

### Enum: `FinishReason(str, Enum)`

7 values: `STOP`, `TOOL_CALLS`, `LENGTH`, `ERROR`, `SAFETY`, `VALIDATION_FALLBACK`, `MALFORMED_TOOL_CALL`

### Enum: `ThinkingLevel(str, Enum)`

4 values: `NONE`, `LOW`, `MEDIUM`, `HIGH`

### Class: `ToolSchema` (frozen dataclass)

```python
@dataclass(frozen=True)
class ToolSchema:
    name: str
    description: str
    parameters: dict[str, Any]          # JSON Schema object
    returns: dict[str, Any] | None = None   # documentation/validation only
    actor: str | None = None            # "front" | "back" | "both"
    category: str | None = None         # "signal" | "cognitive" | "read" | "action" | "control"
    side_effects: bool = False
```

Tool categories reference V2 Section 6.0 taxonomy: signal, cognitive, read, action, control.

### Class: `ModelMessage` (frozen dataclass)

```python
@dataclass(frozen=True)
class ModelMessage:
    role: str                           # "user" | "assistant" | "tool"
    content: str
    tool_call_id: str | None = None     # for role="tool"
    name: str | None = None             # for role="tool"
    tool_calls: list[ToolCallResult] | None = None  # for role="assistant"
    _raw_provider_content: Any = None   # Opaque Gemini Content for thought signatures
```

Role mapping: "assistant" → Gemini "model", "tool" → Gemini FunctionResponse. System messages NOT in contents (via system_instruction).

### Class: `ConciergeModelRequest` (frozen dataclass)

```python
@dataclass(frozen=True)
class ConciergeModelRequest:
    capability: str = Capability.TOOL_CALL
    system_prompt: str = ""
    messages: list[ModelMessage] = field(...)
    tools: list[ToolSchema] | None = None
    tool_choice: str = "auto"           # "auto" | "required" | "none" | specific tool
    response_schema: dict | None = None # JSON Schema for STRUCTURED capability
    max_tokens: int = 65536
    timeout_ms: int = 120_000
    temperature: float = 1.0            # Gemini recommends 1.0 default
    thinking: ThinkingLevel | None = None
    trace_id: str = ""
    actor: str = ""                     # "front" | "back" | "planner"
    scenario: str = ""                  # "user_input" | "task_dispatch" etc.
    model_hint: str | None = None       # "fast" | "smart" | "cheap" | model name
    stop_sequences: list[str] | None = None
```

### Class: `ConciergeModelResponse` (mutable dataclass)

```python
@dataclass
class ConciergeModelResponse:
    text: str = ""
    tool_calls: list[ToolCallResult] = field(...)
    json_output: dict | None = None
    tokens_in: int = 0
    tokens_out: int = 0
    tokens_thoughts: int = 0
    latency_ms: int = 0
    model_id: str = ""
    finish_reason: str = FinishReason.STOP
    thought_text: str = ""
    _raw_provider_content: Any = None
```

Properties: `has_tool_calls`, `has_text`, `has_json`, `total_tokens`

### Class: `ToolCallResult` (frozen dataclass)

```python
@dataclass(frozen=True)
class ToolCallResult:
    id: str
    name: str
    arguments: dict[str, Any] = field(...)
```

### Class: `ToolResultMessage` (frozen dataclass)

```python
@dataclass(frozen=True)
class ToolResultMessage:
    tool_call_id: str
    name: str
    content: str  # JSON-serialized result
```

### Class: `StreamChunk` (mutable dataclass)

```python
@dataclass
class StreamChunk:
    chunk_type: str     # "text_delta" | "tool_call_delta" | "thought_delta" | "done"
    text: str = ""
    tool_call_partial: ToolCallResult | None = None
    thought_text: str = ""
    response: ConciergeModelResponse | None = None  # for "done"
```

### Helper Functions

- `tool_result_to_message(tool_call, result) → ModelMessage` — Converts tool execution result to "tool" role message
- `response_to_assistant_message(response) → ModelMessage` — Converts LLM response to "assistant" role message (preserves `_raw_provider_content`)

---

## 14. llm/ports.py — IConciergeModelPort Protocol

**Purpose:** Universal LLM port. `@runtime_checkable` Protocol with two async methods.

```python
@runtime_checkable
class IConciergeModelPort(Protocol):
    async def generate(self, request: ConciergeModelRequest) -> ConciergeModelResponse: ...
    async def generate_stream(self, request: ConciergeModelRequest) -> AsyncIterator[StreamChunk]: ...
```

**Contract:** Callers NEVER import provider SDKs. Callers NEVER construct provider-specific message formats.

**Usage:** Front (generate + generate_stream), Back (generate only), Planner (generate).

---

## 15. llm/model_selection.py — Capability-Based Model Routing

**Purpose:** Callers express INTENT ("fast", "smart", "cheap"), not model names. Decouples callers from provider-specific identifiers.

### Data: `MODEL_SELECTION_TABLE: dict[tuple[str, str], str]`

(capability, actor) → model:

| Capability | Actor | Model |
|------------|-------|-------|
| CHAT | front | gemini-2.5-flash |
| TOOL_CALL | front | gemini-2.5-flash |
| TOOL_CALL | back | gemini-2.5-flash |
| STRUCTURED | front | gemini-2.5-flash |
| STRUCTURED | back | gemini-2.5-flash |
| REASON | back | gemini-2.5-flash |
| REASON | front | gemini-2.5-flash |
| CHAT | back | gemini-2.5-flash-lite |
| STREAM | front | gemini-2.5-flash-lite |
| TOOL_CALL | planner | gemini-2.5-flash |
| CHAT | planner | gemini-2.5-flash |

**Note:** "Moved from Gemini 3.x due to persistent latency spikes"

### Data: `MODEL_HINT_OVERRIDES: dict[str, str]`

| Hint | Model |
|------|-------|
| fast | gemini-2.5-flash-lite |
| smart | gemini-2.5-flash |
| cheap | gemini-2.5-flash-lite |
| thinking | gemini-2.5-flash |
| pro | gemini-2.5-flash |
| flash | gemini-2.5-flash |

### Constant: `DEFAULT_MODEL = "gemini-2.5-flash"`

### Function: `select_model(capability, actor, hint, default) → str`

Selection priority:
1. Hint in MODEL_HINT_OVERRIDES → use override
2. Hint contains "-" (looks like model name) → use directly
3. (capability, actor) in selection table → use table entry
4. Capability-only fallback (any actor with matching capability)
5. Default model

Runtime tables are read from central config (`get_config().llm`).

### Cross-Component Imports

```python
from k1.concierge.config import get_config
```

---

## 16. llm/gemini_adapter.py — Gemini Provider Implementation

**Purpose:** The ONLY class that imports `google.genai`. All provider-specific translation happens here.

### Lazy Import Pattern

```python
_genai = None
_types = None

def _ensure_genai():
    global _genai, _types
    if _genai is None:
        from google import genai
        from google.genai import types
        _genai = genai
        _types = types
    return _genai, _types
```

Fails fast with clear ImportError message if SDK not installed.

### Class: `GeminiConciergeAdapter`

**Constructor:** `__init__(api_key=None, default_model=None)`
- Reads `GOOGLE_API_KEY` env var if api_key not provided
- Creates `genai.Client(api_key=...)`
- Default model from config

**Method: `generate(request) → ConciergeModelResponse`** (async)

1. Log diagnostic info (prompt first 500 chars, messages, tools)
2. Select model via `select_model()`
3. Convert messages → Gemini Contents via `_to_gemini_contents()`
4. Convert tools → Gemini FunctionDeclarations via `_to_gemini_tools()`
5. Build GenerateContentConfig via `_build_config()`
6. Execute with `asyncio.wait_for` timeout enforcement
7. Normalize response via `_normalize()`
8. Parse JSON output for STRUCTURED capability
9. Return `ConciergeModelResponse`

**Error handling:**
- `asyncio.TimeoutError` → FinishReason.ERROR with elapsed time
- Quota exhaustion (RESOURCE_EXHAUSTED/429) → specific error log
- All other exceptions → generic error log with exc_info

**Method: `generate_stream(request) → AsyncIterator[StreamChunk]`** (async)

1. Runs sync streaming iterator in thread executor via `run_in_executor()`
2. Enforces timeout via `asyncio.wait_for`
3. Yields:
   - `thought_delta` for thinking parts
   - `text_delta` for regular text
   - `tool_call_delta` for function calls
4. Accumulates raw Part objects to preserve thought_signature fields
5. Builds synthetic Content object from raw parts for round-trip
6. Final `done` chunk with complete `ConciergeModelResponse`

**Method: `generate_json(request, schema) → ConciergeModelResponse`** (async)

Structured JSON output using Gemini's JSON mode:
- Sets `response_mime_type = "application/json"`
- Sets `response_json_schema` from request or explicit schema
- No tools in JSON mode

**Method: `generate_batch(requests, max_concurrency) → list[ConciergeModelResponse]`** (async)

Concurrent batch via `asyncio.gather` with `Semaphore` concurrency control. Concurrency from config (`llm.batch_max_concurrency`).

### Internal Methods

**`_select_model(request) → str`** — Delegates to `select_model()`.

**`_build_config(request, gemini_tools, types, model) → GenerateContentConfig`**

Constructs:
- `system_instruction` from system_prompt
- `tools` (Gemini FunctionDeclarations)
- `tool_config` (calling mode: AUTO/ANY/NONE)
- `temperature`, `max_output_tokens`, `stop_sequences`
- JSON mode: `response_mime_type` + `response_json_schema`
- Thinking config:
  - 2.5 models: `ThinkingConfig(thinking_budget=N, include_thoughts=True)` — budget mapped: LOW=1024, MEDIUM=8192, HIGH=24576
  - Other models: `ThinkingConfig(thinking_level=value)`

**`_to_gemini_contents(messages) → list[Content]`**

Critical message conversion:
- Consecutive tool-result messages **merged** into single Content(role="user") with multiple FunctionResponse parts
- This is REQUIRED by Gemini — without merging, parallel tool calls break
- Assistant messages with `_raw_provider_content` use the raw Content directly (preserves thought signatures)
- System messages skipped (handled via system_instruction)

**`_to_gemini_tools(tools) → list[Tool]`**

Uses `parameters_json_schema` attribute on FunctionDeclaration.

**`_tool_config(tool_choice, types) → ToolConfig`**

- "auto" → AUTO, "required" → ANY, "none" → NONE
- Specific tool name → ANY with `allowed_function_names`

**`_normalize(response, model) → ConciergeModelResponse`**

Extracts from Gemini response:
- Text parts (non-thought)
- Thought parts (thought=True)
- Function call parts → ToolCallResult with UUID-based IDs
- Token usage metadata (prompt_token_count, candidates_token_count, thoughts_token_count)
- Finish reason mapping: MALFORMED_FUNCTION_CALL, STOP, MAX_TOKENS/LENGTH, SAFETY
- Preserves raw Content object for thought signature round-trips

### Cross-Component Imports

```python
from k1.concierge.llm.model_selection import select_model
from k1.concierge.llm.types import (Capability, ConciergeModelRequest, ConciergeModelResponse,
                                      FinishReason, StreamChunk, ThinkingLevel, ToolCallResult)
from k1.concierge.config import get_config
```

External: `google.genai`, `google.genai.types` (lazy)

---

## 17. llm/model_hub_bridge.py — ModelHubPOCBridge to K1 Model Hub

**Purpose:** Bridge implementing `IModelHubPort` (K1 types) that delegates to existing POC adapter (GeminiConciergeAdapter or TestConciergeAdapter). Translates between K1 types (HubRequest/HubResponse) and POC types (ConciergeModelRequest/ConciergeModelResponse).

**Lifecycle note:** "After M5 (Big Copy), the bridge swaps for the real Model Hub (M7)."

### Class: `ModelHubPOCBridge`

**Constructor:** `__init__(inner: Any)` — Accepts any object with `generate()` and `generate_stream()`.

**IModelHubPort Methods:**

| Method | Description |
|--------|-------------|
| `execute(request: HubRequest) → HubResponse` | Translate → delegate → translate back |
| `stream_execute(request: HubRequest) → AsyncIterator[HubChunk]` | Streaming delegation |
| `discover_capabilities() → dict[CapabilityType, list[str]]` | Returns POC capabilities |
| `discover_models(capability) → list[ModelInfo]` | Reads MODEL_SELECTION_TABLE |
| `health() → HubHealthReport` | Always returns HEALTHY |

### Translation Tables

**Capability mapping: `_K1_TO_POC_CAPABILITY`**

| K1 CapabilityType | POC Capability |
|-------------------|----------------|
| CHAT | CHAT |
| TOOL_CALL | TOOL_CALL |
| STRUCTURED | STRUCTURED |
| REASON | REASON |

**FinishReason mapping: `_POC_TO_HUB_FINISH`**

| POC | K1 HubFinishReason |
|-----|-------------------|
| stop | STOP |
| tool_calls | TOOL_CALLS |
| length | LENGTH |
| error | ERROR |
| safety | SAFETY |

**ThinkingLevel mapping: `_EFFORT_TO_THINKING`**

| ReasonPayload.reasoning_effort | POC ThinkingLevel |
|-------------------------------|-------------------|
| low | LOW |
| medium | MEDIUM |
| high | HIGH |

### Translation: HubRequest → ConciergeModelRequest

`_hub_to_poc_request(hub_req)`:

1. Map capability via `_K1_TO_POC_CAPABILITY`
2. Handle 4 payload types:
   - `ChatPayload` → system_prompt + messages
   - `ToolCallPayload` → + tools + tool_choice
   - `StructuredOutputPayload` → + response_schema
   - `ReasonPayload` → + thinking level
3. Parse consumer_id → actor ("concierge.front" → "front")
4. Extract model_hint from `constraints.model_preference`
5. Map constraints (max_tokens, timeout_ms, temperature)

### Translation: ConciergeModelResponse → HubResponse

`_poc_to_hub_response(poc_resp, capability, trace_id)`:

1. Build `CapabilityResult` per capability type:
   - TOOL_CALL → `ToolCallResultSet` with tool_calls
   - STRUCTURED → `StructuredResult` with json_output
   - REASON → `ReasonResult` with thinking text
   - Default → `ChatResult` with text
2. Build `ResponseMetadata` with model_id, provider_id, usage, latency, finish_reason
3. Return `HubResponse(result, metadata)`

### Translation: StreamChunk → HubChunk

Maps chunk types (done, tool_call_delta, text_delta, thought_delta).

### Helper Methods

- `_k1_msg_to_poc(msg) → ModelMessage` — K1 Message → POC ModelMessage (maps tool_calls)
- `_k1_tool_to_poc(tool: ToolDefinition) → ToolSchema` — K1 ToolDefinition → POC ToolSchema

### Cross-Component Imports

```python
from k1.model_hub.ports import HubHealthReport, ProviderHealthStatus
from k1.model_hub.types import (
    CapabilityResult, CapabilityType, ChatPayload, ChatResult,
    FinishReason as HubFinishReason, HubChunk, HubRequest, HubResponse,
    ModelInfo, ReasonPayload, ReasonResult, ResponseMetadata,
    StructuredOutputPayload, StructuredResult, ToolCallPayload,
    ToolCallResult as HubToolCallResult, ToolCallResultSet, ToolDefinition, Usage,
)
from k1.concierge.llm.types import (
    Capability, ConciergeModelRequest, ConciergeModelResponse,
    ModelMessage, StreamChunk, ThinkingLevel,
    ToolCallResult as POCToolCallResult, ToolSchema,
)
from k1.concierge.llm.model_selection import MODEL_SELECTION_TABLE
```

**This is the CRITICAL bridge connecting concierge LLM to k1.model_hub.**

---

## 18. llm/test_adapter.py — Deterministic Test Adapter

**Purpose:** No real LLM calls. Keyed by (actor, scenario) for exact response configuration. Records all calls for assertions.

### Class: `TestConciergeAdapter`

**Configuration:**
- `set_response(actor, scenario, response)` — Fixed response
- `set_response_sequence(actor, scenario, responses)` — Sequence (last repeats)
- `set_default_response(response)` — Fallback

**IConciergeModelPort Methods:**
- `generate(request) → ConciergeModelResponse` — Lookup by (actor, scenario), check sequence first, then fixed, then default
- `generate_stream(request) → AsyncIterator[StreamChunk]` — Simulates streaming (word-level chunks), then tool calls, then done

**Assertion Helpers:**
- `call_count: int`
- `last_call: ConciergeModelRequest | None`
- `calls_for(actor, scenario) → list[ConciergeModelRequest]`
- `calls_for_actor(actor) → list[ConciergeModelRequest]`
- `assert_called(actor, scenario)` — Raises AssertionError if no match
- `assert_not_called(actor, scenario)`
- `assert_tool_called(tool_name)` — Checks if tool was in any request's tools
- `reset()` — Clear all state

---

## 19. llm/test_model_hub_bridge.py — Test Model Hub Bridge

**Purpose:** Convenience wrapper creating `ModelHubPOCBridge` around `TestConciergeAdapter` for tests using K1 HubRequest/HubResponse types.

### Class: `TestModelHubBridge(ModelHubPOCBridge)`

```python
class TestModelHubBridge(ModelHubPOCBridge):
    def __init__(self):
        self._test_adapter = TestConciergeAdapter()
        super().__init__(inner=self._test_adapter)
```

**Pass-through API:** `set_response()`, `set_response_sequence()`, `set_default_response()`, `call_count`, `reset()`, `inner` property.

---

## 20. llm/validator.py — LLM Output Validator

**Purpose:** Guardrails against hallucinated tool calls. Validates every `ConciergeModelResponse` before acceptance.

### Class: `ValidationResult` (dataclass)

```python
@dataclass
class ValidationResult:
    valid: bool
    issues: list[str] = field(...)
    fixed_response: ConciergeModelResponse | None = None
```

### Class: `LLMOutputValidator`

**Constructor:** `__init__(tool_schemas: list[ToolSchema])` — Builds internal lookup dict by name.

**Method: `validate(response, actor, iteration, available_tool_names) → ValidationResult`**

Three validation checks:
1. **Tool allowlist** — All tool_calls reference known schemas
2. **Required params** — Each tool call supplies required arguments (from JSON Schema `required`)
3. **Param type spot-check** — Top-level type mismatches (string, number, boolean, object, array)

Text-only responses always pass (nothing to validate).

**Method: `_attempt_fix(response, actor, iteration) → ConciergeModelResponse | None`**

Fix strategy:
1. Keep only tool calls passing allowlist + required params
2. If no valid calls remain → return None (caller applies fallback)
3. Build cleaned response with `finish_reason = FinishReason.VALIDATION_FALLBACK`

**Properties:**
- `schema_names: set[str]` — Known tool names
- `has_schema(name) → bool`

### Cross-Component Imports

```python
from k1.concierge.llm.types import ConciergeModelResponse, FinishReason, ToolCallResult, ToolSchema
```

---

## 21. Prompt Construction Pipeline (End-to-End)

### Front LLM Pipeline

```
User Input / Event arrives
       ↓
Envelope on bus with topic (user_input, task_complete, task_failed, etc.)
       ↓
determine_mode(fsm_state, topic, ss_signals) → PromptMode
       ↓
compute_affect_band(ss.affective_now) → AffectBand
       ↓
DynamicPromptBuilder.build(mode, affect, history, tools, scenario, depth, domain, ss)
       ↓ (9-stage pipeline)
BuiltContext { system_prompt, messages, tools, max_iterations, mode, affect_band }
       ↓
ConciergeModelRequest(capability=TOOL_CALL, system_prompt, messages, tools, ...)
       ↓
LLMOutputValidator.validate(response) → strip hallucinated tools
       ↓
react_loop() iterates until text response or max_iterations
```

### Back LLM Pipeline

```
Task dispatch payload arrives
       ↓
build_back_prompt(task, beliefs, task_state, artifacts, safety_band, persona_prefs, max_tool_calls)
       ↓ (simple template substitution)
system_prompt string (~1800 words + dynamic sections)
       ↓
ConciergeModelRequest(capability=TOOL_CALL, system_prompt, messages, tools, ...)
       ↓
react_loop() with Back tools (recall_memory, discover_capabilities, invoke_capability, etc.)
```

---

## 22. Cross-Component Import Map

### Prompt Package Dependencies

| Module | Imports From |
|--------|-------------|
| `prompt.mode` | `k1.concierge.config`, `k1.concierge.bus.topics` (5 topic constants) |
| `prompt.affect` | stdlib only |
| `prompt.sections` | `k1.concierge.prompt.mode`, `k1.sessionstate.sections.temporal_context` (lazy, in renderer) |
| `prompt.scenario_templates` | `k1.concierge.prompt.mode` |
| `prompt.clarify_depth` | `k1.concierge.config` |
| `prompt.domain_rules` | None (self-contained) |
| `prompt.back_prompt` | `k1.concierge.config` |
| `prompt.builder` | `k1.concierge.llm.types` (ModelMessage, ToolSchema), `k1.concierge.config`, all sibling prompt modules |

### LLM Package Dependencies

| Module | Imports From |
|--------|-------------|
| `llm.types` | stdlib only |
| `llm.ports` | `k1.concierge.llm.types` |
| `llm.model_selection` | `k1.concierge.config` |
| `llm.gemini_adapter` | `k1.concierge.llm.types`, `k1.concierge.llm.model_selection`, `k1.concierge.config`, `google.genai` (lazy) |
| `llm.test_adapter` | `k1.concierge.llm.types` |
| `llm.model_hub_bridge` | `k1.model_hub.ports`, `k1.model_hub.types` (18 types), `k1.concierge.llm.types`, `k1.concierge.llm.model_selection` |
| `llm.test_model_hub_bridge` | `k1.concierge.llm.model_hub_bridge`, `k1.concierge.llm.test_adapter`, `k1.concierge.llm.types` |
| `llm.validator` | `k1.concierge.llm.types` |

### Cross-Package Dependencies (outside concierge)

| Import | Used By | Purpose |
|--------|---------|---------|
| `k1.concierge.bus.topics` | `prompt.mode` | 5 canonical topic constants |
| `k1.concierge.config` | 6 modules | Central config singleton |
| `k1.temporal` | prompt temporal projection bridge | canonical temporal anchors and projection rendering |
| `k1.model_hub.ports` | `llm.model_hub_bridge` | `HubHealthReport`, `ProviderHealthStatus` |
| `k1.model_hub.types` | `llm.model_hub_bridge` | 18 K1 type imports (HubRequest, HubResponse, CapabilityType, etc.) |
| `google.genai` | `llm.gemini_adapter` (lazy) | Gemini SDK |

---

## 23. Error Handling Patterns

### Prompt Subsystem

- **Safe SS section access:** `_safe_get_ss_section()` catches all exceptions, returns None
- **Section rendering:** Each renderer wrapped in try/except in `_read_ss_sections()`, logs and skips on failure
- **Template formatting:** `_format_scenario_data()` catches KeyError, falls back to key/value listing
- **Placeholder interpolation:** `{open_gaps_list}` RC-1 fix replaces missing placeholder with "(none provided)"
- **Context budget:** If estimated tokens exceed budget, `_compress_prompt()` truncates from end
- **Depth block formatting:** Catches KeyError in clarify_depth format, uses raw template

### LLM Subsystem

- **Timeout enforcement:** `asyncio.wait_for()` in both `generate()` and `generate_stream()`
- **Quota exhaustion:** Specific log for RESOURCE_EXHAUSTED/429 errors
- **Generic errors:** Caught, logged with exc_info, return error response
- **Validation fallback:** `LLMOutputValidator` strips invalid tool calls, returns `VALIDATION_FALLBACK` finish reason
- **Streaming errors:** Timeout and generic exceptions caught, set `FinishReason.ERROR`, still yield final "done" chunk
- **Lazy SDK import:** `_ensure_genai()` fails fast with clear ImportError

---

## 24. Architecture Summary & Key Observations

### Strengths

1. **Clean hexagonal pattern:** IConciergeModelPort protocol with runtime_checkable, multiple adapter implementations
2. **Mode-driven assembly:** 10 cognitive modes with precise tool/section/iteration selection — avoids monolithic prompt
3. **Affect modulation:** 5-band emotional state drives tone, iteration budget, token caps, vocabulary tier, tool budgets
4. **Domain safety rules:** 8 domains with safety floors, mode-scoped applicability, clear coherence hierarchy
5. **Clarification depth tracking:** 3-level escalation prevents infinite clarification loops
6. **ModelHub bridge:** Clean translation layer between POC types and K1 types with bidirectional mapping
7. **Output validation:** Tool allowlist, required param, and type checking with auto-fix capability
8. **Test infrastructure:** TestConciergeAdapter with sequence support, assertion helpers; TestModelHubBridge for K1-typed tests

### Architecture Patterns

- **Hexagonal ports:** `IConciergeModelPort` (protocol), `IModelHubPort` (bridge target)
- **Strategy pattern:** Mode → tool allowlist, SS read configs, section selection, iteration limits
- **Builder pattern:** `DynamicPromptBuilder` 9-stage pipeline producing immutable `BuiltContext`
- **Adapter pattern:** `GeminiConciergeAdapter` translates between universal types and Gemini SDK
- **Bridge pattern:** `ModelHubPOCBridge` connects POC adapter to K1 model_hub interface
- **Lazy loading:** Gemini SDK import only when adapter is constructed

### Current Model Routing

All critical paths route to **gemini-2.5-flash**. Only lightweight paths (back CHAT, front STREAM) use **gemini-2.5-flash-lite**. No pro/3.x models in use ("moved from Gemini 3.x due to persistent latency spikes").

### Key Design Decisions

1. **Front vs Back prompt divergence:** Front uses mode-driven 9-stage assembly; Back uses simple template substitution
2. **Thought signature preservation:** `_raw_provider_content` field on both ModelMessage and ConciergeModelResponse preserves Gemini thought signatures across function-calling round-trips
3. **Tool result merging:** Consecutive tool results merged into single Content for Gemini (required for parallel tool call understanding)
4. **SS section virtual mapping:** `temporal_context` reads from `control` sub-field (POC path; production reads from multimodal section)
5. **Config-driven overrides:** All mode tables, iteration limits, model selections, and thresholds can be overridden via central config

### Potential Production Concerns

1. **SECTION_SOURCE_MAP** maps `temporal_context` → `control` — noted as POC path, production reads from multimodal section (Section 5)
2. **`_compress_prompt()`** uses simple truncation (cut from end) — production may need more sophisticated compression
3. **`_estimate_tokens()`** uses `len(text) // 4` heuristic — not a real tokenizer
4. **ModelHubPOCBridge.health()** always returns HEALTHY — no real health checking
5. **ModelHubPOCBridge.discover_models()** reads from static MODEL_SELECTION_TABLE — not dynamic model discovery
6. **Affect hard constraints** (`apply_affect_hard_constraints`) defined but its call site is in the kernel/handler layer, not in the builder itself
