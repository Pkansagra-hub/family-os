# Unified Fabric POC - "Saturday Dinner Party"

## 20-Turn End-to-End Demo Plan

**Status**: Planning
**Depends On**: Demo 1 (concierge_planner_orchestrator), Anniversary Demo (session_state_demo)
**Location**: `poc/unified_fabric_demo/`
**Goal**: ONE demo that proves ALL 3 Fabric roles, ALL 3 complexity tiers, SessionState continuity, and Agent Factory (created agent actually runs as LLM agent)

---

## The Hook

A parent plans a dinner party for 8 people this Saturday. What starts as simple weather checks and recipe searches escalates into full multi-agent orchestration, and ends with the system creating a **reusable LLM-powered dinner planner agent** that the user then **actually uses** for a different event. One continuous conversation, 20 turns, every system firing.

---

## What This Proves (That Demo 1 Does NOT)

| Capability | Demo 1 | This POC |
|---|---|---|
| Fabric Role 1 - Retrieval (Planner discovers tools) | YES | YES |
| Fabric Role 2 - Resolution + Execution (Orchestrator calls tools) | YES | YES |
| Fabric Role 3 - Agent Factory (created agent RUNS as LLM agent) | NO (only registers) | **YES** |
| SessionState continuity across 20 turns | NO | **YES** |
| LOW tier - Concierge handles directly via Fabric | Partial | **YES (5 turns)** |
| MEDIUM tier - Concierge spawns sub-agent via Fabric | NO | **YES (4 turns)** |
| HIGH tier - Full Concierge -> Planner -> Orchestrator pipeline | YES | **YES (5 turns)** |
| Agent Factory execution - created agent uses real tools | NO | **YES (4 turns)** |
| Beliefs persist and influence later decisions | NO | **YES** |
| Cross-tier data flow (LOW results feed HIGH planning) | NO | **YES** |

---

## Available MCP Tools (Real Servers)

From LiveMCPTransport (4 MCP servers in-process):

| Server | Tools | Protocol |
|---|---|---|
| Weather | `get_weather(city)`, `get_forecast(city, days)` | stdio JSON-RPC |
| Calendar | `get_events(date)`, `create_event(title, date, time, desc)` | stdio JSON-RPC |
| Notes | `create_note(title, content)`, `search_notes(query)`, `get_note(id)` | FastMCP |
| Recipes | `search_recipes(query, cuisine?, dietary?)`, `get_recipe(id)` | FastMCP |

Plus: `build_agent(name, prompt_template, tools, domain)` via Fabric

**Total: 10 discovery tools + 1 meta-agent tool = 11 capabilities through Fabric**

---

## The 20-Turn Story

### PHASE 1: LOW Tier - Concierge Direct (Turns 1-5)

**What it proves**: Concierge classifies LOW, executes tools directly through Fabric, SessionState records everything.

**Fabric touch**: Role 2 (Resolution + Execution via MCP providers)
**SessionState touch**: beliefs_active, interaction_history, persona

| Turn | User Says | Fabric Tool | SessionState Written |
|---|---|---|---|
| 1 | "What's the weather like this Saturday in Portland?" | `get_weather("Portland")` | belief: event_location=Portland |
| 2 | "Check my calendar for Saturday evening" | `get_events("2025-07-19")` | belief: saturday_evening=free |
| 3 | "Save a note - planning a dinner party for 8 people Saturday" | `create_note("Dinner Party Plan", ...)` | belief: event=dinner_party, guest_count=8 |
| 4 | "Mom has a nut allergy and my brother is vegetarian - save that" | `create_note("Dietary Restrictions", ...)` | belief: mom=nut_allergy, brother=vegetarian |
| 5 | "Find me some good pasta recipes" | `search_recipes("pasta")` | belief: cuisine_pref=pasta |

**Key proof**: Every tool call goes through `CapabilityFabric.execute()`. SessionState accumulates context that influences later turns.

---

### PHASE 2: MEDIUM Tier - Sub-Agent Spawning (Turns 6-9)

**What it proves**: Concierge detects task too complex for single tool call, spawns a specialist sub-agent via Fabric AgentProvider. Sub-agent runs with its own LLM context + subset of Fabric tools.

**Fabric touch**: Role 1 (Retrieval - agent discovers relevant tools) + Role 2 (Execution - agent calls tools)
**SessionState touch**: beliefs feed agent context, results stored back, task_context tracks agent delegations

| Turn | User Says | What Happens | Fabric Tools Used |
|---|---|---|---|
| 6 | "I need a full menu planned - appetizer, main, dessert. Everything nut-free with vegetarian options" | Concierge classifies MEDIUM, spawns menu-search agent | Agent calls: `search_recipes` x3 (appetizer, main, dessert queries with dietary filters) |
| 7 | "What about wine pairings for those dishes?" | Same sub-agent, follow-up task | Agent calls: `search_recipes("wine pairing [dish]")` per menu item |
| 8 | "I like option 2 - mushroom risotto. Find a nut-free tiramisu for dessert" | Sub-agent refines selection | Agent calls: `search_recipes("tiramisu nut-free")`, `get_recipe(id)` |
| 9 | "Save the final menu to my notes" | Sub-agent result -> Concierge -> Fabric | `create_note("Final Menu", compiled_menu)` |

**Key proof**: Sub-agent is a REAL LLM agent (not hardcoded). It has its own system prompt, its own tool subset (recipe tools + notes), and makes its own LLM decisions. All tool calls route through Fabric.

---

### PHASE 3: HIGH Tier - Full Pipeline (Turns 10-14)

**What it proves**: Complex multi-step requests that require Concierge -> Planner -> Orchestrator. Planner creates wave DAGs, Orchestrator executes via Fabric with ParamResolver wiring inter-step dependencies.

**Fabric touch**: Role 1 (Planner discovers available tools) + Role 2 (Orchestrator executes waves via Fabric)
**SessionState touch**: beliefs_active feeds Planner context, all results persisted, task_context tracks plan

| Turn | User Says | Plan Created | Waves |
|---|---|---|---|
| 10 | "Complete party setup: calendar event Sat 6pm, weather forecast for the day, and compile a shopping list from all recipes into a note" | 3-step plan with dependencies | W1: `get_forecast("Portland",1)` + `get_recipe(risotto_id)` + `get_recipe(tiramisu_id)` [parallel] -> W2: `create_event("Dinner Party", Sat, 6pm, weather_summary)` -> W3: `create_note("Shopping List", compiled_ingredients)` |
| 11 | "Add the weather details to the event description so guests know what to wear" | 2-step plan | W1: `get_forecast("Portland",1)` -> W2: `create_event(...)` with `$step1.result.forecast` in description |
| 12 | "Check my notes for dietary restrictions and verify every recipe is safe" | 3-step plan | W1: `search_notes("dietary")` -> W2: `get_recipe(risotto)` + `get_recipe(tiramisu)` [parallel] -> validation synthesis |
| 13 | "Create a master plan note - full menu, shopping list, timeline, weather. Call it 'Saturday Dinner Party Master Plan'" | Multi-source aggregation | W1: `search_notes("menu")` + `search_notes("shopping")` + `get_forecast("Portland",1)` [parallel] -> W2: `create_note("Master Plan", compiled)` |
| 14 | "Full status check - calendar, notes, everything" | Cross-system query | W1: `get_events("2025-07-19")` + `search_notes("dinner party")` [parallel] -> synthesis |

**Key proof**: ParamResolver wires `$step_id.result.path` references between waves. Planner autonomously decides wave structure. Orchestrator executes batch/wave through Fabric. LLM synthesizes multi-source results.

---

### PHASE 4: Agent Factory - Role 3 (Turns 15-20)

**What it proves**: The full Agent Factory lifecycle. User requests a custom agent. Fabric builds it (build_agent). The agent is ACTUALLY INSTANTIATED as a real LLM agent with its own prompt and tools. The agent EXECUTES real tasks through Fabric and produces real results.

**Fabric touch**: All 3 Roles - Role 1 (discovery for agent tools), Role 2 (build_agent execution + agent tool execution), Role 3 (Agent Factory - agent instantiation, pool, lifecycle)
**SessionState touch**: dietary restrictions from beliefs become part of agent prompt_template, agent results stored

| Turn | User Says | What Happens | Proves |
|---|---|---|---|
| 15 | "I host dinner parties a lot. Create me a personal dinner planner agent that knows my family's dietary restrictions and cooking preferences" | Concierge classifies META -> Planner -> Orchestrator -> `build_agent` through Fabric. Agent spec includes: prompt with dietary info from SessionState, tools=[search_recipes, get_recipe, create_note, search_notes], domain=meal_planning | **Role 3 creation**: Agent spec validated, registered as `agent.execute.dinner_planner` |
| 16 | "Try the new dinner planner - have it suggest a Thanksgiving menu for this family" | Concierge routes to `agent.execute.dinner_planner`. Fabric AgentProvider instantiates LLM agent with baked-in prompt + 4 tools. Agent runs autonomously: searches recipes, filters for nut-free + vegetarian, builds menu. | **Role 3 execution**: Created agent RUNS as real LLM with real tools through Fabric |
| 17 | "Have the planner save that Thanksgiving menu to my notes" | Created agent calls `create_note("Thanksgiving Menu", ...)` through Fabric | **Role 3 tool access**: Created agent uses Fabric tools independently |
| 18 | "Ask the planner for a quick weeknight meal - vegetarian, under 30 min" | Same agent, different task. Agent searches with new constraints. | **Role 3 reuse**: Agent is persistent, reusable, actually intelligent |
| 19 | "Summary of everything we planned today" | Concierge (LOW): `search_notes("dinner")` + `search_notes("thanksgiving")` + SessionState history review | SessionState continuity, cross-session memory |
| 20 | "This was amazing, thanks!" | Emotional closure | SessionState: emotion updated, session complete |

**Key proof**: Turn 16 is the money shot. The agent created in Turn 15 actually runs as a **real LLM-powered agent** with its own system prompt (containing dietary restrictions), its own tool access (4 Fabric tools), and produces real results. NOT a mock. NOT a registration stub. A running agent.

---

## System Architecture

```
User Input
    |
    v
SessionState <----+----> SQLite (beliefs, history, persona, task_context)
    |              |
    v              |
Concierge (LLM)   |
    |              |
    +-- LOW -------+---> Fabric.execute(tool) ---> MCP Provider ---> MCP Server
    |              |
    +-- MEDIUM ----+---> Spawn Sub-Agent (LLM) --> Agent uses Fabric tools
    |              |
    +-- HIGH ------+---> Planner (LLM) --> DAG
    |              |         |
    |              |         v
    |              |    Orchestrator --> Wave Execution --> Fabric.execute(step)
    |              |         |
    |              |    ParamResolver ($ref wiring between waves)
    |              |
    +-- META ------+---> Planner --> Orchestrator --> Fabric.execute(build_agent)
                   |         |
                   |         v
                   |    AgentFactory --> AgentSpec validated --> Registry
                   |         |
                   |         v
                   |    AgentProvider.execute() --> Instantiate LLM Agent
                   |         |
                   |         v
                   |    Created Agent (own LLM + own tools via Fabric)
                   |
                   +----> All results written back to SessionState
```

---

## Reused Components

### From `poc/concierge_planner_orchestrator/`

- `SimpleLLMClient` (Gemini wrapper with function calling)
- `Concierge` (classification + response synthesis)
- `Planner` (LLM-driven DAG planning)
- `Orchestrator` (wave execution + ParamResolver)
- `display.py` (terminal visualization)
- `LiveMCPTransport` (4 MCP servers)
- `discovery.py` (capability catalog loading)

### From `poc/session_state_demo/`

- `SessionLLMBridge` (SessionState read/write for LLM context)
- `SessionStateManager` (SQLite persistence, 12 sections)
- `ConciergeFSM` patterns (state machine patterns, not full FSM)
- `DynamicPromptBuilder` pattern (SessionState -> LLM prompt injection)

### From `k1/fabric/` (production code)

- `CapabilityFabric` (the whole thing)
- `AgentFactory` + `AgentBuilder` + `AgentSpec`
- `AgentProvider` (for Role 3 execution)
- `CapabilityRegistry`, `RetrievalEngine`, `PolicyEngine`
- `FabricFactory.create_for_testing()`

---

## Milestone / Epic / Issue Breakdown

### Milestone: POC-UNIFIED - Unified Fabric + SessionState 20-Turn Demo

**Acceptance**: All 20 turns run end-to-end with real Gemini LLM, real MCP servers, real SQLite SessionState, and a created agent that actually executes autonomously.

---

### Epic 1: Infrastructure & Scaffold

**Goal**: POC directory, config, shared types, wiring between anniversary_demo infra and concierge_planner_orchestrator infra.

| Issue | Title | Description | Depends |
| --- | --- | --- | --- |
| 1.1 | Create POC scaffold | `poc/unified_fabric_demo/` with `__init__.py`, types, config, `.env` loader | - |
| 1.2 | Wire SessionLLMBridge into pipeline | Import and configure SessionLLMBridge from session_state_demo. Initialize with SQLite DB. Every turn records to SessionState. | 1.1 |
| 1.3 | Wire LiveMCPTransport + FabricFactory | Set up 4 MCP servers, load capability catalog, create `CapabilityFabric` instance. Same as demo 1 but as reusable fixture. | 1.1 |
| 1.4 | Create DynamicPromptBuilder (Fabric-aware) | Extend DynamicPromptBuilder from anniversary_demo to include Fabric-discovered capabilities in prompts. Build prompt from SessionState + Fabric tool catalog. | 1.2, 1.3 |
| 1.5 | Create script.py (20-turn definitions) | Define all 20 turns with user_input, expected_tier, expected_tools, act grouping. Similar to anniversary_demo script.py but 20 turns / 4 phases. | 1.1 |
| 1.6 | Create display.py (visual output) | Terminal display functions. Reuse from demo 1 display.py with additions for SessionState changes and agent spawning. | 1.1 |

---

### ISSUE 1.1 — Create POC Scaffold (`types.py`, `config.py`, `__init__.py`)

#### What We Build

The `poc/unified_fabric_demo/` directory with three foundational files:

**`__init__.py`** — Empty, makes the directory a Python package so `python -m poc.unified_fabric_demo.runner` works.

**`config.py`** — Env/API config. Reuses the exact `.env` loading pattern from `poc/session_state_demo/config.py`.

**`types.py`** — Shared frozen dataclasses for the entire demo. Extends `poc/concierge_planner_orchestrator/types.py` with new tier and session-aware types.

#### Code Analysis: What We Reuse

**From `poc/concierge_planner_orchestrator/types.py`** (119 lines):

- `ComplexityTier(str, Enum)` — `LOW`, `MEDIUM`, `HIGH`. We ADD `META` as a fourth value.
- `TaskEnvelope` (frozen) — user_input, intent, domains, tier, context, trace_id. We extend with `session_beliefs: Dict[str, Any]` for SessionState context injection.
- `PlanRequest` (frozen) — intent, user_input, domains, available_capabilities, context, trace_id. Reused as-is.
- `PlanStep` (frozen) — step_id, capability_name, params, depends_on, description. Reused as-is.
- `CommittedPlan` (frozen) — plan_id, intent, steps, reasoning, trace_id. Reused as-is.
- `StepResult` (mutable) — step_id, capability_name, success, data, error, duration_ms. Reused as-is.
- `OrchestratorResult` (mutable) — plan_id, success, step_results, total_duration_ms, trace_id. Reused as-is.

**From `poc/session_state_demo/config.py`** (57 lines):

- `DemoConfig` dataclass — llm_provider, google_api_key, google_model, session_id, db_path, display flags. We take the same pattern but add Fabric-specific config (contracts_dir, live_mode).
- `get_config()` factory — Loads from env. Same pattern.
- `.env` loading: `load_dotenv(Path(__file__).parent.parent.parent / ".env")` + `load_dotenv(Path(__file__).parent.parent / "chat_experience_poc" / ".env")`. Same two paths.

#### New Types We Define

```python
# Extends ComplexityTier with META
class ComplexityTier(str, Enum):
    LOW = "LOW"       # Single tool, Concierge handles directly via Fabric
    MEDIUM = "MEDIUM" # Multi-tool, spawn sub-agent with own LLM + Fabric tools
    HIGH = "HIGH"     # Multi-step DAG, Concierge -> Planner -> Orchestrator -> Fabric
    META = "META"     # Agent creation, routes to build_agent pipeline

# Phase grouping for the 20-turn script
class DemoPhase(str, Enum):
    LOW_DIRECT = "PHASE 1: LOW TIER — CONCIERGE DIRECT"
    MEDIUM_AGENT = "PHASE 2: MEDIUM TIER — SUB-AGENT SPAWNING"
    HIGH_PIPELINE = "PHASE 3: HIGH TIER — FULL PIPELINE"
    AGENT_FACTORY = "PHASE 4: AGENT FACTORY — ROLE 3"

# Turn definition (mirrors anniversary_demo's DemoTurn pattern)
@dataclass(frozen=True)
class DemoTurn:
    turn_number: int
    user_input: str
    phase: DemoPhase
    description: str
    expected_tier: ComplexityTier
    expected_tools: List[str]           # Fabric capability names expected
    expected_beliefs: List[str]         # SessionState beliefs expected to be written
    highlight: bool = False             # Extra visual attention

# Extended TaskEnvelope with SessionState beliefs injection
@dataclass(frozen=True)
class TaskEnvelope:
    envelope_id: str
    user_input: str
    intent: str
    domains: List[str]
    tier: ComplexityTier
    context: Dict[str, Any]             # Same as demo 1
    session_beliefs: Dict[str, Any]     # NEW: beliefs from SessionState for next agent
    trace_id: str

# Sub-agent task for MEDIUM tier
@dataclass(frozen=True)
class AgentTask:
    agent_name: str                     # e.g. "menu_search_agent"
    system_prompt: str                  # Built from SessionState context + task
    tool_names: List[str]               # Fabric capability names this agent can use
    task_description: str               # What the agent should accomplish
    session_beliefs: Dict[str, Any]     # Dietary restrictions, preferences, etc.
    max_tool_calls: int = 10

# Agent task result
@dataclass
class AgentTaskResult:
    agent_name: str
    success: bool
    results: List[StepResult]           # All Fabric calls the agent made
    final_response: str                 # LLM-synthesized summary from agent
    total_duration_ms: int = 0

# Pipeline config (mirrors demo 1 runner args + session config)
@dataclass
class DemoConfig:
    google_api_key: str
    google_model: str = "gemini-2.5-flash"
    session_id: str = "unified-demo-001"
    db_path: str = ""                   # SQLite path, auto-set if empty
    contracts_dir: str = "k1/contracts/tools"
    live_mode: bool = True              # Always True for this demo
    fast_mode: bool = False             # Skip dramatic pauses
    verbose: bool = False               # Show full prompts/payloads
    auto_mode: bool = False             # No user interaction pauses
```

#### File Structure Created

```
poc/unified_fabric_demo/
    __init__.py     # Empty package marker
    config.py       # DemoConfig + get_config() + .env loading
    types.py        # All types above: ComplexityTier, DemoPhase, DemoTurn,
                    #   TaskEnvelope, AgentTask, AgentTaskResult, DemoConfig
                    #   PLUS re-exports of PlanRequest, PlanStep, CommittedPlan,
                    #   StepResult, OrchestratorResult from demo 1 types
```

#### Dependencies

None. This is the foundation. All other issues depend on this.

#### Acceptance Criteria

- `from poc.unified_fabric_demo.types import ComplexityTier, DemoTurn, TaskEnvelope` works
- `from poc.unified_fabric_demo.config import get_config` works and loads API key from env
- `ComplexityTier.META` exists as a valid tier
- All frozen dataclasses are truly frozen (immutable)

---

### ISSUE 1.2 — Wire SessionLLMBridge into Pipeline (`session_setup.py`)

#### What We Build

`poc/unified_fabric_demo/session_setup.py` — A module that initializes, configures, and exposes the `SessionLLMBridge` from `poc/session_state_demo/bridge.py` for use by every demo component.

#### Code Analysis: What SessionLLMBridge Gives Us

**Source**: `poc/session_state_demo/bridge.py` (1635 lines)

The `SessionLLMBridge` is the bridge between LLM conversation and `SessionStateManager` (SQLite-backed, 12 sections). Here are the exact APIs we will call:

**Lifecycle** (called once at demo start/end):

```python
bridge = SessionLLMBridge(session_id="unified-demo-001", db_path="/path/to/db")
bridge.start()                        # Initializes SessionStateManager, restores if exists
bridge.stop(checkpoint_before_stop=True)  # Checkpoints and stops
bridge.checkpoint()                   # Manual checkpoint -> (success, msg, bytes)
```

**Per-Turn Recording** (called every turn):

```python
bridge.record_user_turn(content)              # Buffers user message
bridge.record_assistant_turn(               # Writes complete turn to history_active + telemetry
    content=response_text,
    duration_ms=elapsed,
    token_count=0,
    had_tool_call=True
)
```

**Context Building** (called before each LLM call):

```python
ctx = bridge.build_llm_context(max_history_turns=20)
# Returns: {
#   "system_prompt": str,       # Template with persona + history + emotional context
#   "messages": List[Dict],     # Conversation history as {"role": ..., "content": ...}
#   "metadata": {
#       "turn_number": int,
#       "persona_traits": dict,
#       "emotional_state": dict
#   }
# }

# Or for raw history messages only:
messages = bridge.get_history_messages(max_turns=20)
# Returns: [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}, ...]
```

**Tool Execution — SessionState writes** (called when LLM wants to store beliefs/persona/emotion):

```python
changes = bridge.execute_tool_calls([
    {"name": "add_belief", "args": {"subject": "mom", "predicate": "has_allergy", "object": "nuts"}},
    {"name": "update_persona", "args": {"preference_name": "cuisine", "preference_value": "pasta"}},
    {"name": "update_emotion", "args": {"emotion": "excited", "intensity": 0.7}},
])
# Returns: List[StateChange] — each has section, operation, description, success, bytes_delta
```

**Advanced SessionState Access** (for specific sections):

```python
bridge.update_scoreboard(topic="menu_planning", referents={"mom": {"type": "family_member", "salience": 0.9}})
bridge.add_clarification_gap(gap_type="allergy_info", question="...", turn_asked=4)
bridge.resolve_clarification_gap(gap_type="allergy_info")
bridge.update_narrative(phase="execution", thread="dinner_party_planning")
```

**Direct Beliefs Access** (for extracting beliefs to inject into agent prompts):

```python
# We need to read beliefs_active directly for agent prompt building
manager = bridge._manager  # SessionStateManager
beliefs_section = manager.get_section("beliefs_active")
# beliefs_section.get_all() -> list of fact objects
# Each fact: subject, predicate, obj, confidence
```

#### What We Wire

```python
# session_setup.py

from poc.session_state_demo.bridge import SessionLLMBridge, StateChange

class SessionSetup:
    """
    Initializes and manages the SessionLLMBridge lifecycle for the demo.

    Provides:
      - bridge: SessionLLMBridge instance (the main interface)
      - start() / stop() lifecycle
      - get_beliefs_for_agent() — extracts relevant beliefs as dict for agent prompt injection
      - get_history_as_messages() — returns conversation history in LLM format
      - record_turn() — records a complete user+assistant turn
      - record_belief() — shorthand for add_belief tool call
    """

    def __init__(self, config: DemoConfig):
        db_path = config.db_path or str(Path.home() / ".familyos" / "demo" / "unified_demo.db")
        self._bridge = SessionLLMBridge(
            session_id=config.session_id,
            db_path=db_path,
            restore_on_start=False,   # Fresh session for demo
        )

    @property
    def bridge(self) -> SessionLLMBridge:
        return self._bridge

    def start(self) -> str:
        success, msg = self._bridge.start()
        return msg

    def stop(self) -> str:
        success, msg = self._bridge.stop(checkpoint_before_stop=True)
        return msg

    def get_beliefs_as_dict(self) -> Dict[str, Any]:
        """
        Extract all beliefs_active as a flat dict for agent prompt injection.

        Returns e.g.:
        {
            "mom_has_allergy": "nuts",
            "brother_dietary": "vegetarian",
            "event_location": "Portland",
            "guest_count": "8",
            "cuisine_preference": "pasta",
        }
        """
        beliefs = {}
        try:
            section = self._bridge._manager.get_section("beliefs_active")
            if hasattr(section, "get_all"):
                for fact in section.get_all():
                    key = f"{fact.subject}_{fact.predicate}"
                    beliefs[key] = fact.obj
        except Exception:
            pass
        return beliefs

    def get_history_as_messages(self, max_turns: int = 20) -> List[Dict[str, str]]:
        return self._bridge.get_history_messages(max_turns)

    def record_user_turn(self, content: str) -> None:
        self._bridge.record_user_turn(content)

    def record_assistant_turn(self, content: str, duration_ms: int, had_tool_call: bool = False) -> List[StateChange]:
        return self._bridge.record_assistant_turn(content, duration_ms, had_tool_call=had_tool_call)

    def record_belief(self, subject: str, predicate: str, obj: str, confidence: float = 0.8) -> StateChange:
        changes = self._bridge.execute_tool_calls([{
            "name": "add_belief",
            "args": {"subject": subject, "predicate": predicate, "object": obj, "confidence": confidence}
        }])
        return changes[0] if changes else None

    def record_persona(self, pref_name: str, pref_value: str) -> StateChange:
        changes = self._bridge.execute_tool_calls([{
            "name": "update_persona",
            "args": {"preference_name": pref_name, "preference_value": pref_value}
        }])
        return changes[0] if changes else None

    def record_emotion(self, emotion: str, intensity: float = 0.5) -> StateChange:
        changes = self._bridge.execute_tool_calls([{
            "name": "update_emotion",
            "args": {"emotion": emotion, "intensity": intensity}
        }])
        return changes[0] if changes else None

    def get_turn_number(self) -> int:
        return self._bridge._turn_number

    def get_stats(self) -> dict:
        s = self._bridge._stats
        return {
            "total_turns": s.total_turns,
            "tool_calls_executed": s.tool_calls_executed,
            "tool_calls_rejected": s.tool_calls_rejected,
            "total_latency_ms": s.total_latency_ms,
            "checkpoints": s.checkpoints_created,
            "slo_violations": s.slo_violations,
        }
```

#### Key Integration Points

1. **Every turn**: `record_user_turn()` before processing, `record_assistant_turn()` after response synthesis.
2. **Before Concierge classify**: `get_history_as_messages()` provides conversation context.
3. **After classification**: `record_belief()` stores extracted facts (location, allergy, event type).
4. **Before Planner**: `get_beliefs_as_dict()` feeds beliefs into Planner's context.
5. **Before agent spawn (MEDIUM)**: `get_beliefs_as_dict()` feeds dietary restrictions into agent prompt.
6. **Before build_agent (META)**: `get_beliefs_as_dict()` feeds restrictions into agent `prompt_template`.

#### Dependencies

- Issue 1.1 (types.py for DemoConfig)

#### Acceptance Criteria

- `SessionSetup(config).start()` initializes SQLite + SessionStateManager
- `record_belief("mom", "has_allergy", "nuts")` writes to beliefs_active section
- `get_beliefs_as_dict()` returns `{"mom_has_allergy": "nuts", ...}` after beliefs recorded
- `get_history_as_messages()` returns LLM-format messages after turns recorded
- `stop()` cleanly checkpoints and shuts down

---

### ISSUE 1.3 — Wire LiveMCPTransport + FabricFactory (`fabric_setup.py`)

#### What We Build

`poc/unified_fabric_demo/fabric_setup.py` — Initializes the full Fabric stack with real MCP servers, loads the capability catalog, and exposes the `CapabilityFabric` instance + `Orchestrator` + `Planner` + discovery handler.

#### Code Analysis: What We Reuse

**`k1/fabric/adapters/live_mcp_transport.py`** (404 lines):

The `LiveMCPTransport` routes MCP requests to 4 real in-process servers:

```python
transport = LiveMCPTransport()  # Instantiates:
# - WeatherMCPServer()                -> handle_message() JSON-RPC
# - CalendarMCPServer(db_path=":memory:") -> handle_message() JSON-RPC
# - Notes NoteStorage(db_path=":memory:") -> direct async function calls
# - Recipes built-in API client       -> direct async function calls
```

Route table (11 tools):

```python
# JSON-RPC servers:
"tool.read.weather_current"      -> WeatherMCPServer.handle_message()
"tool.read.weather_forecast"     -> WeatherMCPServer.handle_message()
"tool.read.calendar_list_events" -> CalendarMCPServer.handle_message()
"tool.write.calendar_create_event" -> CalendarMCPServer.handle_message()
"tool.write.calendar_delete_event" -> CalendarMCPServer.handle_message()

# FastMCP direct calls:
"tool.write.notes_create"  -> notes_server.notes_create.fn()
"tool.read.notes_list"     -> notes_server.notes_list.fn()
"tool.read.notes_search"   -> notes_server.notes_search.fn()
"tool.read.recipe_search"  -> recipes_server.recipe_search.fn()
"tool.write.recipe_meal_plan" -> recipes_server.recipe_meal_plan.fn()

# Meta-agent:
"tool.write.build_agent"   -> _call_build_agent() with real AgentSpecValidator
```

The `send(request: MCPRequest) -> MCPResponse` method:

1. Strips Fabric metadata keys (`_depends_on` etc.)
2. Routes to appropriate server by tool_name lookup
3. Handles JSON-RPC response parsing or direct function call
4. Returns `MCPResponse(success, content, latency_ms)`

**`k1/fabric/factory.py`** — `FabricFactory.create_for_testing()`:

```python
fabric_container = FabricFactory.create_for_testing(
    capture_events=True,
    contracts_dir="k1/contracts",       # Scans k1/contracts/tools/*.yaml
    mcp_transport=transport,            # Our LiveMCPTransport
)
# Returns Fabric container with:
#   fabric_container.facade    -> CapabilityFabric (the execute() / execute_batch() API)
#   fabric_container.retrieval -> FabricRetrieval (the retrieval API)
#   fabric_container.registry  -> CapabilityRegistry (registered capabilities)
#   fabric_container.module_loader -> ModuleLoader (contract scanner)
#   fabric_container.event_port -> LocalEventAdapter (event capture)
```

The 20-step `_construct_fabric()` builds:

- ContractValidator, CapabilityRegistry, ModuleLoader (scans `k1/contracts/` YAML files)
- PolicyEngine (SecurityContext, AffectiveRouting, CognitiveLoadRouting, QoSIntegration)
- ProviderRegistry, CircuitBreakers, ContextBuilder
- ProviderFactory (with our LiveMCPTransport injected)
- Resolver (ProviderMatcher, ProviderSelector, ProviderFactory, PolicyEngine)
- RetrievalEngine (EmbeddingIndex, HardFilter, SoftRanker, TopKSelector)
- OutputValidationPipeline, HealthChecker, AvailabilityTracker
- EventEmitter, CapabilityFabric (FabricFacade)
- ProactiveGapDetector (event wiring)
- Auto-registers providers from loaded contracts

**`poc/concierge_planner_orchestrator/discovery.py`** (176 lines):

```python
catalog = load_capability_catalog(Path("k1/contracts/tools"))
# Reads all *.yaml in k1/contracts/tools/
# Returns list of dicts: {name, description, domain, capabilities, required_inputs, optional_inputs, provider_type, safety_band_min}
# Skips: discover_capabilities, find_prompts (internal tools)
# build_agent IS included (discoverable for Planner)

filtered = filter_capabilities_by_domain(catalog, ["WEATHER", "RECIPES"])
# Returns capabilities with matching domain tags

handler = create_discovery_handler(Path("k1/contracts/tools"))
# Returns callable: handler(domain="WEATHER", intent="check weather") -> List[Dict]
# This is what the Planner's agentic loop calls when LLM invokes discover_capabilities
```

**`poc/concierge_planner_orchestrator/orchestrator.py`** (435 lines):

```python
orchestrator = Orchestrator(fabric=fabric_container.facade)
# Has two methods:
#   execute_plan(plan: CommittedPlan) -> OrchestratorResult    # Full DAG execution
#   execute_direct(envelope, capability_name, params) -> OrchestratorResult  # Single call

# execute_plan has two modes:
#   1. Batch mode (no $-refs): sends all via execute_batch(strategy=DAG)
#   2. Wave mode ($-refs present): topological waves + ParamResolver between them
```

**`poc/concierge_planner_orchestrator/planner.py`** (487 lines):

```python
planner = Planner(llm_client=llm)
planner.set_discovery_handler(handler)   # Wire discovery handler
plan = await planner.build_plan(plan_request, on_tool_call=callback)
# Returns CommittedPlan with steps
# Internally runs agentic_loop: discover_capabilities -> reason -> commit_plan
```

**`poc/concierge_planner_orchestrator/concierge.py`** (206 lines):

```python
concierge = Concierge(llm_client=llm)
envelope = await concierge.classify(user_input)  # Returns TaskEnvelope
response = await concierge.synthesize_response(user_input, step_results)  # Returns str
```

#### What We Wire

```python
# fabric_setup.py

from k1.fabric.adapters.live_mcp_transport import LiveMCPTransport
from k1.fabric.factory import FabricFactory
from k1.fabric.fabric import CapabilityFabric
from k1.fabric.types import CapabilityRequest, CapabilityResult
from poc.concierge_planner_orchestrator.discovery import (
    load_capability_catalog,
    filter_capabilities_by_domain,
    create_discovery_handler,
)
from poc.concierge_planner_orchestrator.orchestrator import Orchestrator
from poc.concierge_planner_orchestrator.planner import Planner
from poc.concierge_planner_orchestrator.concierge import Concierge
from poc.session_state_demo.llm_client import SimpleLLMClient

class FabricSetup:
    """
    Initializes and holds the entire Fabric + Pipeline stack.

    Creates:
      - LiveMCPTransport (4 real MCP servers + build_agent handler)
      - Fabric container via FabricFactory.create_for_testing(mcp_transport=transport)
      - Capability catalog loaded from k1/contracts/tools/*.yaml
      - Discovery handler for Planner's agentic loop
      - SimpleLLMClient (Gemini)
      - Concierge (classifier + synthesizer)
      - Planner (agentic discovery + DAG planning)
      - Orchestrator (wave execution through Fabric)

    Usage:
        setup = FabricSetup(config)
        setup.initialize()

        # Then use:
        setup.concierge.classify(user_input)
        setup.planner.build_plan(request)
        setup.orchestrator.execute_plan(plan)
        setup.fabric.execute(request)  # Direct Fabric call
        setup.catalog  # Full capability list
    """

    def __init__(self, config: DemoConfig):
        self._config = config
        self._transport: LiveMCPTransport | None = None
        self._fabric_container = None
        self._llm: SimpleLLMClient | None = None
        self._concierge: Concierge | None = None
        self._planner: Planner | None = None
        self._orchestrator: Orchestrator | None = None
        self._catalog: list = []
        self._discovery_handler = None

    def initialize(self) -> None:
        """Build the full stack. Call once at demo start."""

        # 1. MCP Transport (4 real servers)
        self._transport = LiveMCPTransport()

        # 2. Fabric container (20-step construction + contract scanning)
        self._fabric_container = FabricFactory.create_for_testing(
            capture_events=True,
            contracts_dir="k1/contracts",
            mcp_transport=self._transport,
        )

        # 3. Capability catalog (for stats + domain filtering)
        self._catalog = load_capability_catalog(Path(self._config.contracts_dir))

        # 4. Discovery handler (for Planner's agentic loop)
        self._discovery_handler = create_discovery_handler(Path(self._config.contracts_dir))

        # 5. LLM client
        self._llm = SimpleLLMClient(
            api_key=self._config.google_api_key,
            model=self._config.google_model,
        )

        # 6. Pipeline agents
        self._concierge = Concierge(llm_client=self._llm)
        self._planner = Planner(llm_client=self._llm)
        self._planner.set_discovery_handler(self._discovery_handler)
        self._orchestrator = Orchestrator(fabric=self._fabric_container.facade)

    @property
    def fabric(self) -> CapabilityFabric:
        return self._fabric_container.facade

    @property
    def transport(self) -> LiveMCPTransport:
        return self._transport

    @property
    def concierge(self) -> Concierge:
        return self._concierge

    @property
    def planner(self) -> Planner:
        return self._planner

    @property
    def orchestrator(self) -> Orchestrator:
        return self._orchestrator

    @property
    def llm(self) -> SimpleLLMClient:
        return self._llm

    @property
    def catalog(self) -> list:
        return self._catalog

    @property
    def created_agents(self) -> list:
        """Agents created via build_agent (stored in transport)."""
        return self._transport._created_agents if self._transport else []

    def get_agent_spec(self, agent_name: str) -> dict | None:
        """Look up a created agent spec by name."""
        for agent in self.created_agents:
            if agent.get("agent_name") == agent_name:
                return agent
        return None

    def filter_capabilities(self, domains: list) -> list:
        """Filter catalog by domains."""
        return filter_capabilities_by_domain(self._catalog, domains)

    def get_tool_declarations_for_llm(self, tool_names: list[str] | None = None) -> list:
        """
        Convert Fabric capability catalog to Gemini function declarations.

        If tool_names is provided, filter to only those tools.
        Used to give sub-agents and created agents their tool subset.

        Returns list of dicts matching Gemini function_declarations format:
        [{"name": "...", "description": "...", "parameters": {...}}, ...]
        """
        declarations = []
        for cap in self._catalog:
            name = cap.get("name", "")
            if tool_names and name not in tool_names:
                continue

            # Build JSON Schema from required_inputs + optional_inputs
            properties = {}
            required = []

            for inp in cap.get("required_inputs", []):
                param_name = inp.get("name", "")
                if param_name:
                    properties[param_name] = {
                        "type": inp.get("type", "string").lower(),
                        "description": inp.get("description", ""),
                    }
                    required.append(param_name)

            for inp in cap.get("optional_inputs", []):
                param_name = inp.get("name", "")
                if param_name:
                    properties[param_name] = {
                        "type": inp.get("type", "string").lower(),
                        "description": inp.get("description", ""),
                    }

            declarations.append({
                "name": name,
                "description": cap.get("description", ""),
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            })

        return declarations

    async def execute_capability(self, capability_name: str, params: dict, trace_id: str = "") -> CapabilityResult:
        """
        Execute a single capability through Fabric.

        This is the primary interface for LOW tier and sub-agent tool calls.
        Wraps Fabric.execute() with CapabilityRequest construction.
        """
        request = CapabilityRequest(
            capability_name=capability_name,
            params=params,
            tier="LOW",
            caller="unified_demo",
            safety_band="AMBER",
            trace_id=trace_id,
        )
        return await self.fabric.execute(request)

    async def close(self) -> None:
        """Clean up MCP servers."""
        if self._transport:
            await self._transport.close()
```

#### Key Contract: k1/contracts/tools/*.yaml

These are the YAML files that get scanned by `ModuleLoader` during `FabricFactory.create_for_testing()`. Each file defines a tool contract:

```yaml
tool_contract:
  name: "tool.read.weather_current"
  description: "Get current weather for a city"
  domain: ["WEATHER"]
  capabilities: ["weather.current"]
  provider_type: "MCP"
  required_inputs:
    - name: "city"
      type: "STRING"
      description: "City name"
  optional_inputs: []
  safety_band_min: "GREEN"
```

These contracts are what:

1. Gets loaded into `CapabilityRegistry` (so Fabric knows what tools exist)
2. Gets auto-registered into `ProviderRegistry` (so Fabric can route to MCPProvider)
3. Gets read by `load_capability_catalog()` for Planner discovery
4. Gets returned by `create_discovery_handler()` when Planner calls `discover_capabilities`

#### Dependencies

- Issue 1.1 (types.py for DemoConfig)

#### Acceptance Criteria

- `FabricSetup(config).initialize()` completes without errors
- `setup.catalog` contains 11 capabilities (10 tools + build_agent)
- `await setup.execute_capability("tool.read.weather_current", {"city": "Portland"})` returns real weather data
- `setup.concierge`, `setup.planner`, `setup.orchestrator` are all initialized
- `setup.get_tool_declarations_for_llm(["tool.read.recipe_search"])` returns Gemini-formatted declaration for recipe_search only
- `await setup.close()` cleans up servers

---

### ISSUE 1.4 — Create DynamicPromptBuilder (`prompt_builder.py`)

#### What We Build

`poc/unified_fabric_demo/prompt_builder.py` — Builds dynamic system prompts by injecting SessionState context + Fabric-discovered tool catalog into the LLM prompt. Used by Concierge, sub-agents, and created agents.

#### Code Analysis: What We Reuse

**From `poc/session_state_demo/anniversary_demo/runner.py`** (lines 210-380) — `DynamicPromptBuilder`:

This builder reads from all 12 SessionState sections and injects them into the system prompt:

```python
class DynamicPromptBuilder:
    BASE_IDENTITY = """You are the FamilyOS Concierge..."""
    RESPONSE_STYLE = """TOOL CALLING RULES..."""
    SPAWNABLE_AGENTS = """SUB-AGENT ARCHITECTURE..."""

    def build_prompt(self) -> str:
        sections = []
        sections.append(self.BASE_IDENTITY)
        sections.append(self._build_plan_context())       # From PlanController
        sections.append(self._build_context_section())    # All 12 SessionState sections
        sections.append(self._build_resolved_refs_section())
        sections.append(self._build_tools_section())      # Available tool list
        sections.append(self.SPAWNABLE_AGENTS)
        sections.append(self.RESPONSE_STYLE)
        return "\n\n".join(sections)

    def _build_context_section(self) -> str:
        # Reads from:
        # beliefs_active -> "KNOWN FACTS"
        # persona -> "USER PREFERENCES"
        # scoreboard -> "CURRENT FOCUS"
        # affective_now -> "EMOTIONAL STATE"
        # clarifications -> "PENDING CLARIFICATIONS"
        # narrative_active -> "CONVERSATION PHASE"
        # meta -> "SESSION INFO"
```

The key pattern: SessionState sections become labeled prompt sections that the LLM sees.

**From `poc/concierge_planner_orchestrator/concierge.py`** — `CLASSIFY_SYSTEM_PROMPT`:

The current classifier prompt lists domains but NOT available tools. We need to extend it to include Fabric-discovered tools so the LLM can make better tier decisions.

#### What We Build

```python
# prompt_builder.py

class UnifiedPromptBuilder:
    """
    Builds dynamic system prompts from SessionState + Fabric capabilities.

    Three prompt types:
    1. CLASSIFY prompt — For Concierge tier classification
       Includes: beliefs, persona, available tools (from Fabric catalog)

    2. CONCIERGE prompt — For LOW tier direct tool calling
       Includes: beliefs, persona, tool declarations (Gemini format),
       conversation history

    3. AGENT prompt — For MEDIUM tier sub-agents and created agents
       Includes: task description, relevant beliefs (dietary, preferences),
       tool declarations (subset from Fabric catalog)

    4. PLANNER prompt — For HIGH tier planning
       Includes: beliefs, persona, note about discovered tools
       (the Planner discovers its own tools via agentic loop)

    5. SYNTHESIS prompt — For response generation from tool results
       Same as demo 1 RESPONSE_SYSTEM_PROMPT
    """

    def __init__(
        self,
        session: SessionSetup,          # For SessionState reads
        fabric: FabricSetup,            # For Fabric capability catalog
    ):
        self._session = session
        self._fabric = fabric

    def build_classify_prompt(self) -> str:
        """
        Build Concierge classification prompt.

        Includes SessionState beliefs + Fabric tool list so the LLM
        can make informed tier decisions (e.g. knowing that recipe_search
        exists means "find me pasta recipes" is LOW not HIGH).
        """
        sections = [
            self._base_classify_identity(),
            self._beliefs_section(),
            self._persona_section(),
            self._fabric_tools_summary(),
        ]
        return "\n\n".join(s for s in sections if s)

    def build_concierge_prompt(self) -> str:
        """
        Build LOW tier Concierge prompt for direct tool calling.

        The LLM sees tool declarations and can call them directly.
        Includes SessionState context so it knows what's been discussed.
        """
        sections = [
            self._base_concierge_identity(),
            self._beliefs_section(),
            self._persona_section(),
            self._emotional_section(),
            self._history_summary(),
        ]
        return "\n\n".join(s for s in sections if s)

    def build_agent_prompt(
        self,
        task_description: str,
        tool_names: list[str],
        extra_context: str = "",
    ) -> str:
        """
        Build sub-agent prompt for MEDIUM tier.

        Includes task, dietary restrictions, and available tools.
        """
        beliefs = self._session.get_beliefs_as_dict()

        sections = [
            f"You are a specialist agent for FamilyOS.\n\nYOUR TASK:\n{task_description}",
            self._beliefs_for_agent(beliefs),
            f"AVAILABLE TOOLS:\n" + "\n".join(f"- {t}" for t in tool_names),
            "Execute your task by calling the appropriate tools. Make autonomous decisions.",
        ]
        if extra_context:
            sections.insert(2, f"ADDITIONAL CONTEXT:\n{extra_context}")

        return "\n\n".join(s for s in sections if s)

    def build_created_agent_prompt(self, agent_spec: dict, task: str) -> str:
        """
        Build prompt for a created agent (Role 3 Agent Factory).

        Uses the agent's prompt_template from its spec, plus the current task.
        """
        template = agent_spec.get("prompt_template", "You are a helpful assistant.")
        tools = agent_spec.get("tools_granted", [])

        sections = [
            template,  # The prompt_template from build_agent (includes dietary restrictions)
            f"\nCURRENT TASK:\n{task}",
            f"\nAVAILABLE TOOLS:\n" + "\n".join(f"- {t}" for t in tools),
            "\nExecute the task using your tools. Make autonomous decisions about which tools to call and in what order.",
        ]
        return "\n\n".join(sections)

    def _beliefs_section(self) -> str:
        beliefs = self._session.get_beliefs_as_dict()
        if not beliefs:
            return ""
        lines = ["KNOWN FACTS (from session memory):"]
        for key, value in beliefs.items():
            lines.append(f"- {key.replace('_', ' ')}: {value}")
        return "\n".join(lines)

    def _beliefs_for_agent(self, beliefs: dict) -> str:
        if not beliefs:
            return ""
        # Filter to dietary/allergy/preference beliefs
        relevant = {k: v for k, v in beliefs.items()
                    if any(w in k.lower() for w in ["allergy", "dietary", "vegetarian", "preference", "nut", "restriction"])}
        if not relevant:
            relevant = beliefs  # If no dietary found, include all
        lines = ["IMPORTANT CONSTRAINTS (from family profile):"]
        for key, value in relevant.items():
            lines.append(f"- {key.replace('_', ' ')}: {value}")
        lines.append("\nYou MUST respect these constraints in all recommendations.")
        return "\n".join(lines)

    def _persona_section(self) -> str:
        ctx = self._session.bridge.build_llm_context()
        traits = ctx.get("metadata", {}).get("persona_traits", {})
        if not traits:
            return ""
        lines = ["USER PREFERENCES:"]
        for k, v in traits.items():
            lines.append(f"- {k}: {v}")
        return "\n".join(lines)

    def _emotional_section(self) -> str:
        ctx = self._session.bridge.build_llm_context()
        state = ctx.get("metadata", {}).get("emotional_state", {})
        if not state:
            return ""
        emotion = state.get("emotion", "neutral")
        return f"EMOTIONAL CONTEXT: User seems {emotion}."

    def _history_summary(self) -> str:
        messages = self._session.get_history_as_messages(max_turns=5)
        if not messages:
            return ""
        return f"CONVERSATION HISTORY: {len(messages)//2} recent turns in context."

    def _fabric_tools_summary(self) -> str:
        catalog = self._fabric.catalog
        if not catalog:
            return ""
        lines = [f"AVAILABLE TOOLS ({len(catalog)} capabilities via Fabric):"]
        for cap in catalog:
            name = cap.get("name", "")
            desc = cap.get("description", "")[:80]
            domains = ", ".join(cap.get("domain", []))
            lines.append(f"- {name} [{domains}]: {desc}")
        return "\n".join(lines)

    def _base_classify_identity(self) -> str:
        return (
            "You are FamilyOS Concierge -- the front door of a family AI assistant.\n\n"
            "Analyze what the user needs and classify it by calling classify_request.\n\n"
            "Complexity guide:\n"
            "- LOW: Single straightforward action (one tool call)\n"
            "- MEDIUM: Multiple related actions needing specialist reasoning (2-5 tool calls in same domain)\n"
            "- HIGH: Multiple domains or steps that need coordination (cross-domain planning)\n"
            "- META domain requests are ALWAYS HIGH -- they require planning to extract parameters\n\n"
            "Think about: domains involved, number of steps, whether steps depend on each other."
        )

    def _base_concierge_identity(self) -> str:
        return (
            "You are FamilyOS Concierge -- a warm, helpful family assistant.\n\n"
            "You have access to real tools via the Capability Fabric. "
            "Use the tools to answer the user's request. "
            "Be concise but helpful. Reference known facts naturally.\n\n"
            "When you learn new information (preferences, restrictions, facts), "
            "acknowledge it and the system will record it."
        )
```

#### Dependencies

- Issue 1.2 (`SessionSetup` for beliefs/history reads)
- Issue 1.3 (`FabricSetup` for capability catalog + tool declarations)

#### Acceptance Criteria

- `build_classify_prompt()` includes SessionState beliefs AND Fabric tool list
- `build_concierge_prompt()` includes tool declarations in Gemini format
- `build_agent_prompt("Plan a menu", ["tool.read.recipe_search"])` includes dietary restrictions from SessionState
- `build_created_agent_prompt(agent_spec, "Plan Thanksgiving")` uses the agent's `prompt_template`

---

### ISSUE 1.5 — Create script.py (20-Turn Definitions)

#### What We Build

`poc/unified_fabric_demo/script.py` — Defines all 20 turns with user inputs, expected tiers, expected tools, phase grouping. Mirrors the pattern from `poc/session_state_demo/anniversary_demo/script.py` (505 lines).

#### Code Analysis: Anniversary Demo Pattern

The anniversary demo defines:

```python
class Act(Enum):          # Story acts (5 acts)
class TurnEvent(Enum):    # Special events (CRASH, WEATHER_ALERT)
class DemoTurn:           # Turn definition with user_input, act, expected behaviors
DEMO_SCRIPT: List[DemoTurn] = [...]  # 30 turns
SCRIPT_METADATA = {...}              # Stats about the script
```

Each turn has:

- `turn_number`, `user_input`, `act`, `description`
- `expected: ExpectedBehavior` (expected_tools, expects_gap, starts_background_task, etc.)
- `response_theme` (hint for what the response should cover)
- `event: TurnEvent` (NONE, CRASH, WEATHER_ALERT, RESTORE)
- `pause_before`, `pause_after`, `highlight`

We simplify this for our 20-turn demo - no crash/restore, no background tasks (Fabric handles everything).

#### What We Define

```python
# script.py

DEMO_SCRIPT: List[DemoTurn] = [
    # =============== PHASE 1: LOW TIER (Turns 1-5) ===============
    DemoTurn(
        turn_number=1,
        user_input="What's the weather like this Saturday in Portland?",
        phase=DemoPhase.LOW_DIRECT,
        description="Weather check — single tool call",
        expected_tier=ComplexityTier.LOW,
        expected_tools=["tool.read.weather_current"],
        expected_beliefs=["event_location=Portland"],
    ),
    DemoTurn(
        turn_number=2,
        user_input="Check my calendar for Saturday evening",
        phase=DemoPhase.LOW_DIRECT,
        description="Calendar check — single tool call",
        expected_tier=ComplexityTier.LOW,
        expected_tools=["tool.read.calendar_list_events"],
        expected_beliefs=["saturday_evening=free"],
    ),
    DemoTurn(
        turn_number=3,
        user_input="Save a note - planning a dinner party for 8 people Saturday",
        phase=DemoPhase.LOW_DIRECT,
        description="Create note — single tool call",
        expected_tier=ComplexityTier.LOW,
        expected_tools=["tool.write.notes_create"],
        expected_beliefs=["event=dinner_party", "guest_count=8"],
    ),
    DemoTurn(
        turn_number=4,
        user_input="Mom has a nut allergy and my brother is vegetarian - save that as a note too",
        phase=DemoPhase.LOW_DIRECT,
        description="Dietary restrictions — CRITICAL for later turns",
        expected_tier=ComplexityTier.LOW,
        expected_tools=["tool.write.notes_create"],
        expected_beliefs=["mom_has_allergy=nuts", "brother_dietary=vegetarian"],
        highlight=True,
    ),
    DemoTurn(
        turn_number=5,
        user_input="Find me some good pasta recipes",
        phase=DemoPhase.LOW_DIRECT,
        description="Recipe search — single tool call",
        expected_tier=ComplexityTier.LOW,
        expected_tools=["tool.read.recipe_search"],
        expected_beliefs=["cuisine_preference=pasta"],
    ),
    # =============== PHASE 2: MEDIUM TIER (Turns 6-9) ===============
    DemoTurn(
        turn_number=6,
        user_input="I need a full menu planned - appetizer, main, dessert. Everything nut-free with vegetarian options",
        phase=DemoPhase.MEDIUM_AGENT,
        description="MEDIUM — spawn menu search agent (multiple recipe searches)",
        expected_tier=ComplexityTier.MEDIUM,
        expected_tools=["tool.read.recipe_search", "tool.read.recipe_search", "tool.read.recipe_search"],
        expected_beliefs=[],
        highlight=True,
    ),
    DemoTurn(
        turn_number=7,
        user_input="What about wine pairings for those dishes?",
        phase=DemoPhase.MEDIUM_AGENT,
        description="Sub-agent follow-up — wine pairing searches",
        expected_tier=ComplexityTier.MEDIUM,
        expected_tools=["tool.read.recipe_search"],
        expected_beliefs=[],
    ),
    DemoTurn(
        turn_number=8,
        user_input="I like option 2 - mushroom risotto. Find a nut-free tiramisu for dessert",
        phase=DemoPhase.MEDIUM_AGENT,
        description="Sub-agent refinement — specific searches",
        expected_tier=ComplexityTier.MEDIUM,
        expected_tools=["tool.read.recipe_search"],
        expected_beliefs=["selected_main=mushroom_risotto"],
    ),
    DemoTurn(
        turn_number=9,
        user_input="Save the final menu to my notes",
        phase=DemoPhase.MEDIUM_AGENT,
        description="Save agent results — note creation",
        expected_tier=ComplexityTier.LOW,
        expected_tools=["tool.write.notes_create"],
        expected_beliefs=["menu_finalized=true"],
    ),
    # =============== PHASE 3: HIGH TIER (Turns 10-14) ===============
    DemoTurn(
        turn_number=10,
        user_input="Complete party setup: create a calendar event for Saturday at 6pm, get the weather forecast, and compile a shopping list from all the recipes into a note",
        phase=DemoPhase.HIGH_PIPELINE,
        description="HIGH — full Planner->Orchestrator, 3+ steps with dependencies",
        expected_tier=ComplexityTier.HIGH,
        expected_tools=["tool.read.weather_forecast", "tool.write.calendar_create_event", "tool.write.notes_create"],
        expected_beliefs=["party_event_created=true"],
        highlight=True,
    ),
    DemoTurn(
        turn_number=11,
        user_input="Add the weather details to the calendar event description so guests know what to wear",
        phase=DemoPhase.HIGH_PIPELINE,
        description="HIGH — 2-step with $ref dependency (forecast -> event update)",
        expected_tier=ComplexityTier.HIGH,
        expected_tools=["tool.read.weather_forecast", "tool.write.calendar_create_event"],
        expected_beliefs=[],
    ),
    DemoTurn(
        turn_number=12,
        user_input="Check my notes for the dietary restrictions and make sure every recipe in the menu is safe",
        phase=DemoPhase.HIGH_PIPELINE,
        description="HIGH — cross-reference notes + recipes for safety validation",
        expected_tier=ComplexityTier.HIGH,
        expected_tools=["tool.read.notes_search", "tool.read.recipe_search"],
        expected_beliefs=[],
    ),
    DemoTurn(
        turn_number=13,
        user_input="Create a master plan note with the full menu, shopping list, timeline, and weather. Call it 'Saturday Dinner Party Master Plan'",
        phase=DemoPhase.HIGH_PIPELINE,
        description="HIGH — multi-source aggregation into single note",
        expected_tier=ComplexityTier.HIGH,
        expected_tools=["tool.read.notes_search", "tool.read.weather_forecast", "tool.write.notes_create"],
        expected_beliefs=[],
        highlight=True,
    ),
    DemoTurn(
        turn_number=14,
        user_input="Full status check - show me the calendar event, all my notes, everything for Saturday",
        phase=DemoPhase.HIGH_PIPELINE,
        description="HIGH — cross-system query (calendar + notes)",
        expected_tier=ComplexityTier.HIGH,
        expected_tools=["tool.read.calendar_list_events", "tool.read.notes_search"],
        expected_beliefs=[],
    ),
    # =============== PHASE 4: AGENT FACTORY (Turns 15-20) ===============
    DemoTurn(
        turn_number=15,
        user_input="I host dinner parties a lot. Create me a personal dinner planner agent that knows my family's dietary restrictions and cooking preferences",
        phase=DemoPhase.AGENT_FACTORY,
        description="META — build_agent through full pipeline, dietary restrictions baked into prompt",
        expected_tier=ComplexityTier.HIGH,
        expected_tools=["tool.write.build_agent"],
        expected_beliefs=["agent_created=dinner_planner"],
        highlight=True,
    ),
    DemoTurn(
        turn_number=16,
        user_input="Try the new dinner planner - have it suggest a Thanksgiving menu for 12 people",
        phase=DemoPhase.AGENT_FACTORY,
        description="THE MONEY SHOT — created agent RUNS as real LLM with real Fabric tools",
        expected_tier=ComplexityTier.MEDIUM,
        expected_tools=["tool.read.recipe_search", "tool.read.recipe_search", "tool.read.recipe_search"],
        expected_beliefs=["thanksgiving_menu_planned=true"],
        highlight=True,
    ),
    DemoTurn(
        turn_number=17,
        user_input="Have the planner save that Thanksgiving menu to my notes",
        phase=DemoPhase.AGENT_FACTORY,
        description="Created agent uses note creation tool through Fabric",
        expected_tier=ComplexityTier.LOW,
        expected_tools=["tool.write.notes_create"],
        expected_beliefs=[],
    ),
    DemoTurn(
        turn_number=18,
        user_input="Ask the planner for a quick weeknight dinner - vegetarian, under 30 minutes",
        phase=DemoPhase.AGENT_FACTORY,
        description="Created agent reuse — different task, same agent instance",
        expected_tier=ComplexityTier.MEDIUM,
        expected_tools=["tool.read.recipe_search"],
        expected_beliefs=[],
    ),
    DemoTurn(
        turn_number=19,
        user_input="Give me a summary of everything we planned today - the Saturday dinner party and all the other stuff",
        phase=DemoPhase.AGENT_FACTORY,
        description="Cross-session summary using notes search + SessionState history",
        expected_tier=ComplexityTier.HIGH,
        expected_tools=["tool.read.notes_search", "tool.read.notes_search"],
        expected_beliefs=[],
    ),
    DemoTurn(
        turn_number=20,
        user_input="This was amazing, thanks for all the help!",
        phase=DemoPhase.AGENT_FACTORY,
        description="Emotional closure — SessionState emotion update",
        expected_tier=ComplexityTier.LOW,
        expected_tools=[],
        expected_beliefs=["session_emotion=grateful"],
    ),
]

SCRIPT_METADATA = {
    "title": "The Saturday Dinner Party",
    "total_turns": 20,
    "total_phases": 4,
    "features_demonstrated": [
        "LOW tier — Concierge direct via Fabric (5 turns)",
        "MEDIUM tier — Sub-agent spawning with own LLM (4 turns)",
        "HIGH tier — Full Planner->Orchestrator pipeline (5 turns)",
        "Agent Factory — Role 3 creation + execution (6 turns)",
        "SessionState continuity across 20 turns",
        "Beliefs persist and influence later decisions",
        "Wave DAG execution with $ref dependencies",
        "Created agent runs as real LLM with real tools",
    ],
    "key_moments": {
        4: "Dietary restrictions stored (critical for turns 6-8, 12, 15-16)",
        6: "First MEDIUM tier — sub-agent with multiple recipe searches",
        10: "First HIGH tier — Planner creates 3-step DAG with dependencies",
        15: "Agent Factory — build_agent with SessionState beliefs in prompt",
        16: "THE MONEY SHOT — created agent runs autonomously through Fabric",
    },
}

# Helper functions (same pattern as anniversary_demo)
def get_turn(n: int) -> DemoTurn | None: ...
def get_turns_by_phase(phase: DemoPhase) -> List[DemoTurn]: ...
def get_all_turns() -> List[DemoTurn]: ...
```

#### Dependencies

- Issue 1.1 (types.py for DemoTurn, DemoPhase, ComplexityTier)

#### Acceptance Criteria

- `get_all_turns()` returns exactly 20 turns
- `get_turns_by_phase(DemoPhase.LOW_DIRECT)` returns turns 1-5
- `get_turns_by_phase(DemoPhase.AGENT_FACTORY)` returns turns 15-20
- Turn 4 has `highlight=True` and `expected_beliefs=["mom_has_allergy=nuts", "brother_dietary=vegetarian"]`
- Turn 16 has `highlight=True` (the money shot)

---

### ISSUE 1.6 — Create display.py (Visual Output)

#### What We Build

`poc/unified_fabric_demo/display.py` — Terminal visualization. We reuse the entire `poc/concierge_planner_orchestrator/display.py` (949 lines) as a base since it already has all the Fabric pipeline visualization, and ADD new display functions for:

1. **SessionState changes** — show beliefs/persona/emotion writes
2. **Sub-agent spawning** — show when MEDIUM tier spawns an agent
3. **Agent Factory** — show agent creation and execution
4. **Turn indicators** — show turn number and phase
5. **20-turn header** — show the full demo banner with phases

#### Code Analysis: What We Reuse From Demo 1 display.py

All 949 lines. The existing functions we use directly:

```python
setup_unicode_console()             # Windows Unicode fix
print_pipeline_header()             # Main banner
print_phase(number, title, icon)    # Phase separator
print_divider(char, color)          # Thin divider
print_user_input(text)              # User request box
print_llm_call_start(agent, purpose, model)  # LLM call starting
print_llm_call_end(latency, tool_calls, text_length)  # LLM call done
print_classification(tier, intent, domains, reasoning, latency)  # Classification result
print_routing(tier)                 # Routing decision
print_capabilities_discovered(total, filtered, domains, caps)  # Discovery results
print_agentic_tool_call(tool_name, args, result, turn)  # Planner tool call
print_plan(steps, reasoning, plan_id, latency)  # DAG visualization
print_fabric_start(count, strategy)   # Fabric execution start
print_fabric_step(step_id, cap, success, duration, data, error)  # Single step
print_fabric_end(total_ms, success, fail)  # Fabric summary
print_response(text)                # Final response box
print_stats(stats)                  # Statistics
print_pipeline_complete(success)    # Pipeline done banner

# Verbose functions (when --verbose):
print_system_prompt(agent, prompt)
print_user_message(agent, message)
print_tool_definitions(tools)
print_raw_tool_call(name, args)
print_raw_tool_result(name, result)
print_llm_raw_response(content, tool_calls)
print_fabric_request_detail(step_id, cap, params, safety, trace)
print_fabric_response_detail(step_id, cap, success, data, error, duration)
print_synthesis_context(user_input, step_results)
```

#### New Functions We Add

```python
# --- Session State Display ---
def print_session_state_change(section: str, operation: str, description: str, success: bool) -> None:
    """Show a SessionState write (belief added, persona updated, etc.)"""

def print_beliefs_snapshot(beliefs: Dict[str, str]) -> None:
    """Show current beliefs state (e.g. after Phase 1 accumulation)"""

def print_session_stats(stats: dict) -> None:
    """Show SessionState statistics (turns, writes, checkpoints)"""

# --- Turn Display ---
def print_turn_header(turn_number: int, phase: str, description: str, highlight: bool = False) -> None:
    """Show turn number with phase indicator and description"""

def print_demo_header() -> None:
    """Full demo banner: 'Saturday Dinner Party — 20-Turn Unified Fabric Demo'"""

def print_phase_transition(phase: str) -> None:
    """Big visual transition between phases (LOW -> MEDIUM -> HIGH -> FACTORY)"""

# --- Agent Display ---
def print_agent_spawn(agent_name: str, tools: list, task: str) -> None:
    """Show sub-agent being spawned (MEDIUM tier)"""

def print_agent_tool_call(agent_name: str, tool_name: str, args: dict) -> None:
    """Show a tool call made BY a sub-agent (not Concierge)"""

def print_agent_result(agent_name: str, success: bool, tool_calls: int, duration_ms: int) -> None:
    """Show sub-agent completion"""

def print_agent_factory_create(agent_name: str, tools: list, domain: list, prompt_preview: str) -> None:
    """Show agent being created via build_agent (Role 3)"""

def print_agent_factory_execute(agent_name: str, task: str) -> None:
    """Show created agent starting execution"""

# --- End-of-Demo ---
def print_demo_complete(total_turns: int, fabric_calls: int, agents_created: int, session_writes: int) -> None:
    """Final demo completion banner with all stats"""

def print_full_stats(pipeline_stats: dict, session_stats: dict) -> None:
    """Combined pipeline + SessionState statistics"""
```

#### Implementation Strategy

Import everything from the demo 1 display module and add the new functions:

```python
# display.py

# Reuse ALL display functions from demo 1
from poc.concierge_planner_orchestrator.display import *  # noqa: F401,F403
from poc.concierge_planner_orchestrator.display import (
    c, W, TL_D, TR_D, BL_D, BR_D, HZ_D, VT_D, TL_H, TR_H, BL_H, BR_H, HZ_H, VT_H,
    TL, TR, BL, BR, HZ, VT,
    RESET, BOLD, DIM, RED, GREEN, YELLOW, BLUE, MAGENTA, CYAN, WHITE, GRAY,
    CHECK, CROSS, ARROW_R, BULLET, STAR, LIGHTNING, GEAR, DATABASE, CLOCK, BRAIN, NETWORK, WAVE,
    _box_line,
)

# NEW display functions for SessionState, agents, turns, etc.
# (implementations as described above)
```

#### Dependencies

- Issue 1.1 (types.py for DemoPhase)
- `poc/concierge_planner_orchestrator/display.py` (949 lines, imported wholesale)

#### Acceptance Criteria

- All existing display functions from demo 1 work via import
- `print_demo_header()` shows the unified demo banner
- `print_turn_header(4, "LOW TIER", "Dietary restrictions", highlight=True)` shows highlighted turn
- `print_session_state_change("beliefs_active", "add_fact", "mom has_allergy nuts", True)` shows state write
- `print_agent_spawn("menu_search", ["recipe_search"], "Plan menu")` shows agent spawning
- `print_agent_factory_create("dinner_planner", [...], [...], "You are...")` shows agent creation
- `print_demo_complete(20, 45, 1, 30)` shows final stats

---

### Epic 2: LOW Tier - Concierge Direct Execution (Turns 1-5)

**Goal**: Concierge classifies LOW, calls tools directly through Fabric, SessionState records beliefs.

| Issue | Title | Description | Depends |
|---|---|---|---|
| 2.1 | Concierge classifier with Fabric tool awareness | Concierge system prompt includes Fabric-discovered tool list. Classifies intent + domains. Routes LOW directly to execution. | 1.3, 1.4 |
| 2.2 | Direct Fabric execution path | For LOW tier: Concierge LLM returns tool calls -> execute each via `CapabilityFabric.execute()` -> return results to Concierge for response synthesis. | 2.1 |
| 2.3 | SessionState belief recording | After each tool call + response, automatically extract beliefs from conversation and store via SessionLLMBridge. Record interaction_history. | 1.2, 2.2 |
| 2.4 | Turns 1-5 runner integration | Wire turns 1-5 into runner. Validate: correct tool called, SessionState updated, response coherent. | 2.1-2.3 |

---

### Epic 3: MEDIUM Tier - Sub-Agent Spawning (Turns 6-9)

**Goal**: Concierge detects multi-tool task, spawns a specialist sub-agent that runs as real LLM with Fabric tool access.

| Issue | Title | Description | Depends |
|---|---|---|---|
| 3.1 | Sub-agent spawner via Fabric | When Concierge classifies MEDIUM, spawn a sub-agent: create minimal LLM agent with specific system prompt + subset of Fabric tools. Agent makes its own LLM decisions. | 2.2, 1.3 |
| 3.2 | Menu search agent implementation | Concrete sub-agent for menu planning. System prompt includes dietary restrictions from SessionState. Tools: search_recipes, get_recipe. Makes multiple search calls autonomously. | 3.1 |
| 3.3 | Sub-agent result aggregation | Sub-agent results returned to Concierge. Concierge synthesizes into user-facing response. Results also written to SessionState task_context. | 3.1, 3.2 |
| 3.4 | Turns 6-9 runner integration | Wire turns 6-9. Validate: sub-agent spawned, multiple Fabric calls made by agent, results aggregated, SessionState updated. | 3.1-3.3 |

---

### Epic 4: HIGH Tier - Full Pipeline (Turns 10-14)

**Goal**: Complex multi-step requests route through Concierge -> Planner -> Orchestrator with wave execution via Fabric.

| Issue | Title | Description | Depends |
|---|---|---|---|
| 4.1 | Planner with SessionState context | Planner LLM prompt includes beliefs from SessionState + discovered Fabric tools. Plans multi-step DAGs with wave grouping. | 1.2, 1.3 |
| 4.2 | Orchestrator wave execution through Fabric | Reuse Orchestrator from demo 1. Executes each wave step via `CapabilityFabric.execute()`. ParamResolver wires `$step.result.path` dependencies. | 4.1 |
| 4.3 | Response synthesis from multi-step results | After orchestrator completes all waves, Concierge LLM synthesizes results into coherent response. Multi-source data (weather + recipes + notes) merged. | 4.2 |
| 4.4 | Turns 10-14 runner integration | Wire turns 10-14. Validate: plan created with correct waves, parallel execution where possible, ParamResolver wires dependencies, Fabric executes all steps. | 4.1-4.3 |

---

### Epic 5: Agent Factory - Role 3 (Turns 15-20)

**Goal**: Create a custom LLM agent via build_agent, then ACTUALLY RUN IT as a real agent with its own LLM and tools through Fabric.

| Issue | Title | Description | Depends |
|---|---|---|---|
| 5.1 | build_agent with SessionState context | When user requests agent creation, Concierge extracts relevant beliefs from SessionState (dietary restrictions, preferences) and includes them in agent prompt_template. Routes through full pipeline to Fabric build_agent. | 4.2, 1.2 |
| 5.2 | Agent instantiation via AgentProvider | After build_agent registers the agent spec, implement AgentProvider.execute() to actually instantiate the agent: create SimpleLLMClient, set system prompt from spec, bind Fabric tools from spec. | 5.1 |
| 5.3 | Created agent autonomous execution | The instantiated agent receives a task, makes its OWN LLM calls, decides which tools to call, executes them through Fabric, and returns results. Real LLM, real tool calls, real decision-making. | 5.2 |
| 5.4 | Agent reuse across turns | Same agent instance handles multiple different queries (Thanksgiving menu, weeknight meal). Proves persistence and reusability. | 5.3 |
| 5.5 | Turns 15-20 runner integration | Wire turns 15-20. Validate: agent created, agent executes autonomously, agent uses Fabric tools, agent produces real results, SessionState records everything. | 5.1-5.4 |

---

### Epic 6: End-to-End Runner & Polish

**Goal**: Full 20-turn runner with display, validation, and reporting.

| Issue | Title | Description | Depends |
|---|---|---|---|
| 6.1 | Full 20-turn runner | Orchestrate all 20 turns sequentially. Auto and interactive modes. Display pipeline activity, Fabric calls, SessionState changes, agent spawning, plan DAGs. | 2.4, 3.4, 4.4, 5.5 |
| 6.2 | SessionState continuity validation | After each turn, verify beliefs persist. Turn 11's dietary restrictions must still be accessible at Turn 16 when building agent prompt. Verify interaction_history has all 20 turns. | 6.1 |
| 6.3 | Demo stats and reporting | End-of-run report: total Fabric calls, tool breakdown by tier, SessionState sections written, agents created, agent tool calls, latencies, success rates. | 6.1 |
| 6.4 | Error handling and fallbacks | Graceful handling of LLM failures, MCP server errors, agent execution failures. Retry logic. Display error states clearly. | 6.1 |

---

## Implementation Order

```
Epic 1 (scaffold)
    |
    +---> Epic 2 (LOW) ---> validate turns 1-5
    |         |
    |         v
    +---> Epic 3 (MEDIUM) ---> validate turns 6-9
    |         |
    |         v
    +---> Epic 4 (HIGH) ---> validate turns 10-14
    |         |
    |         v
    +---> Epic 5 (AGENT FACTORY) ---> validate turns 15-20
              |
              v
         Epic 6 (full runner + polish) ---> 20-turn end-to-end
```

**Estimated implementation**: Each epic builds on the previous. Scaffold first (Epic 1), then tiers can be built and tested incrementally (LOW -> MEDIUM -> HIGH -> Factory). Final integration (Epic 6) ties everything together.

---

## Technical Decisions

### Concierge Classification

The Concierge LLM classifies each input into one of 4 tiers:

- **LOW**: Single tool call, straightforward. Concierge handles directly.
- **MEDIUM**: Multiple related tool calls requiring specialist reasoning. Spawn sub-agent.
- **HIGH**: Complex multi-step with dependencies. Full Planner -> Orchestrator pipeline.
- **META**: Agent creation request. Route to build_agent pipeline.

Classification prompt includes available Fabric tools and SessionState context.

### Sub-Agent Architecture (MEDIUM tier)

Sub-agents are lightweight LLM agents:

- Own SimpleLLMClient instance
- System prompt built from task description + relevant SessionState beliefs
- Tool declarations from Fabric capability catalog (filtered to task-relevant subset)
- Execute multiple tool calls autonomously via Fabric
- Return structured results to Concierge

NOT the same as the anniversary demo's SearchAgent/BookingAgent (which use mock data). These use REAL Fabric execution.

### Agent Factory Architecture (Role 3)

Turn 15 creates the agent spec. Turn 16+ runs it. The created agent:

1. Has a `prompt_template` that includes the user's dietary restrictions (extracted from SessionState beliefs at creation time)
2. Has declared tools (`search_recipes`, `get_recipe`, `create_note`, `search_notes`) that are real Fabric capabilities
3. Is instantiated with a real `SimpleLLMClient` (Gemini)
4. Makes autonomous LLM decisions about which tools to call
5. Executes all tool calls through `CapabilityFabric.execute()`
6. Returns results that feed back into SessionState

### SessionState Sections Used

| Section | Purpose in POC |
|---|---|
| `beliefs_active` | Dietary restrictions, location, event details, preferences |
| `interaction_history` | Full 20-turn conversation log |
| `persona` | User cooking preferences, hosting frequency |
| `task_context` | Active plans, delegated agent tasks, completion tracking |
| `affective_now` | Emotional state (excitement, satisfaction) |
| `meta` | Session ID, turn count, last checkpoint |

---

## Success Criteria

1. All 20 turns execute end-to-end with real Gemini API + real MCP servers + real SQLite SessionState
2. Turn 4's dietary restrictions are correctly used in Turn 8's recipe filtering, Turn 15's agent prompt, and Turn 16's agent execution
3. Turn 10's plan DAG has at least 2 waves with parallel steps
4. Turn 16's created agent makes at least 2 autonomous Fabric tool calls
5. SessionState `interaction_history` contains all 20 turns at completion
6. No mock/fake/simulated behavior anywhere - real LLM, real tools, real state

---

## Files Created

```
poc/unified_fabric_demo/
    __init__.py
    config.py              # Env vars, API keys, MCP server config
    types.py               # Shared types (Tier, Turn, AgentTask, etc.)
    script.py              # 20-turn definitions
    display.py             # Terminal visualization
    runner.py              # Main orchestrator (the demo entry point)
    concierge.py           # Classification + routing + response synthesis
    planner.py             # LLM-driven DAG planning (reuse from demo 1)
    orchestrator.py        # Wave execution + ParamResolver (reuse from demo 1)
    agent_spawner.py       # MEDIUM tier sub-agent creation + execution
    agent_factory.py       # Role 3: instantiate + run created agents
    prompt_builder.py      # Dynamic prompts from SessionState + Fabric
    fabric_setup.py        # LiveMCPTransport + FabricFactory wiring
    session_setup.py       # SessionLLMBridge configuration
```
