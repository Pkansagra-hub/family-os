# 🚀 Chat Experience PoC - Implementation Plan

**Project**: K1 Intelligence Module - Complete Chat Experience Architecture
**Based on**: `docs/whiteboard/chat_experience.md`
**Goal**: Build end-to-end PoC demonstrating full K1 system without actual K0 persistence
**LLM Provider**: Groq API
**Validation**: Mock K0/MCP servers validate request format only

---

## 📊 **Project Overview**

### **What We're Building**

A complete K1 intelligence system with:

- **2 Interaction Paths**:
  - PATH 1: Specialist Agents (Query/Retrieval from K0)
  - PATH 2: Planner Path (Action/Execution with DAG)
- **Full SessionState** with delta tracking
- **Agent Lifecycle FSM** (6 states)
- **Proactive Flow** with temporal scheduling
- **User Knowledge Graph** for personalization
- **Mock K0/MCP** validation (no actual persistence/execution)

### **Key Architecture Layers**

| Layer | Components | Status |
|-------|-----------|--------|
| **Layer 1: Input** | Intent Router, SessionState Bootstrap | 🔴 Not Started |
| **Layer 2: Orchestration** | Orchestrator (3-phase), Planner (4-stage) | 🔴 Not Started |
| **Layer 3: Execution** | Concierge, Specialists, Writers (58 agents) | 🔴 Not Started |
| **Layer 4: Runtime** | SessionState, DeltaBus, Mailbox, Lifecycle | 🔴 Not Started |
| **Layer 5: Infrastructure** | Agent Factory, K0 Bridge, Tool/Prompt Registry | 🔴 Not Started |

---

## 🎯 **Milestone 1: Foundation & Infrastructure**

**Goal**: Set up project scaffolding, external integrations, and core registries
**Duration**: 3-4 days
**Dependencies**: None

### **Epic 1.1: Project Scaffolding & Groq API Integration**

**Objective**: Create project structure and integrate Groq API for LLM inference

#### **Issue 1.1.1: Initialize PoC Project Structure**

**Context**:
Create the foundation directory structure for the chat experience PoC under `poc/chat_experience_poc/`. This structure follows K1's layered architecture (Layers 1-5) and separates concerns clearly.

**Tasks**:

- Create main directory: `poc/chat_experience_poc/`
- Create layer directories:
  - `l1_input/` - Intent routing, stream normalization
  - `l2_orchestration/` - Orchestrator, Planner
  - `l3_execution/agents/` - All agent implementations
  - `l4_runtime/` - SessionState, DeltaBus, Mailbox, Lifecycle
  - `l5_infrastructure/` - Agent Factory, K0 Bridge, Registries
- Create support directories:
  - `models/` - Pydantic data models
  - `mock_services/` - Mock K0 API, Mock MCP servers
  - `tests/` - Integration tests
  - `config/` - Configuration files
- Create files: `__init__.py`, `main.py`, `README.md`, `requirements.txt`

**Acceptance Criteria**:

- ✅ Directory structure matches K1 layer architecture
- ✅ All `__init__.py` files created for Python package imports
- ✅ README.md documents project purpose and structure

**References**:

- `docs/whiteboard/chat_experience.md` - Complete architecture
- `.github/copilot-instructions.md` - K1 module structure guidelines

---

#### **Issue 1.1.2: Install Dependencies & Configure Groq API**

**Context**:
Install Python dependencies and configure Groq API client. Groq provides fast LLM inference for Concierge, Planner, and Specialist agents.

**Tasks**:

- Add to `requirements.txt`:
  - `groq` - Groq API client
  - `fastapi` - API framework
  - `uvicorn` - ASGI server
  - `pydantic` - Data validation
  - `httpx` - Async HTTP client
  - `asyncio` - Already in stdlib
  - `python-dotenv` - Environment variables
  - `sqlite3` - Already in stdlib (for User KG)
- Create `.env` file with `GROQ_API_KEY=your_key_here`
- Create `config/groq_config.py`:
  - Default model: `llama-3.1-70b-versatile`
  - Temperature: 0.7 for Concierge/Specialists, 0.3 for Planner
  - Max tokens: 2048
  - Timeout: 30s
- Create `l5_infrastructure/groq_client.py`:
  - Async Groq client wrapper
  - Error handling with retries (3 attempts)
  - Token counting and budget tracking
  - Response streaming support

**Acceptance Criteria**:

- ✅ All dependencies install without errors
- ✅ Groq API key loads from `.env`
- ✅ Test script successfully calls Groq API
- ✅ Client handles errors gracefully (network, rate limit, invalid key)

**References**:

- Groq API Docs: <https://console.groq.com/docs>
- `docs/whiteboard/chat_experience.md` - LLM requirements for agents

---

#### **Issue 1.1.3: Create Base Configuration System**

**Context**:
Centralize configuration management for all PoC components. This mirrors K1's `k1/config/*.yml` pattern.

**Tasks**:

- Create `config/poc_config.yml`:
  - Session settings (timeout: 600s, max_turns: 100)
  - Performance budgets (TTFT: 150ms, E2E: 2000ms)
  - Agent settings (max_concurrent: 3, pool_size: 5)
  - K0 Bridge settings (batch_interval: 250ms, batch_size: 100)
  - Temporal settings (tick_interval: 60s)
- Create `config/config_loader.py`:
  - Load YAML config
  - Merge with environment variables
  - Validate required fields
  - Type checking with Pydantic
- Create config models in `models/config_models.py`:
  - `SessionConfig`, `PerformanceConfig`, `AgentConfig`, `K0BridgeConfig`

**Acceptance Criteria**:

- ✅ Config loads from YAML file
- ✅ Environment variables override YAML values
- ✅ Missing required fields raise clear errors
- ✅ Config accessible via singleton pattern

**References**:

- `k1/config/` - K1 configuration structure
- `.github/copilot-instructions.md` - Configuration standards

---

### **Epic 1.2: MCP Tool Registry & Mock MCP Servers**

**Objective**: Create tool registry and mock MCP servers for tool call validation

#### **Issue 1.2.1: Design MCP Tool Registry Schema**

**Context**:
The Tool Registry stores definitions of all MCP tools available to agents. Agents query this registry to discover which tools they can use. Format validation happens at mock MCP servers.

**Tasks**:

- Create `l5_infrastructure/registries/tool_registry.py`
- Define tool schema:

  ```python
  ToolDefinition:
    - tool_id: str (unique identifier)
    - name: str (human-readable)
    - description: str (what it does)
    - parameters: dict (JSON schema)
    - required_capabilities: list[str] (permissions needed)
    - category: str (search, calendar, k0_query, etc.)
    - mock_endpoint: str (URL for mock validation)
    - response_schema: dict (expected response format)
  ```

- Create initial tools:
  - `web_search` - Search the web
  - `calendar_add` - Add calendar event
  - `query_k0_health` - Query K0 health memories
  - `query_k0_episodic` - Query K0 episodic memories
  - `query_k0_semantic` - Query K0 semantic memories
  - `store_prospective_trigger` - Store time-based reminder
- Store registry in: `config/tool_registry.json`

**Acceptance Criteria**:

- ✅ Tool registry loads from JSON file
- ✅ Tools can be queried by category, capability, name
- ✅ Schema validation for tool definitions
- ✅ At least 6 tools defined with complete schemas

**References**:

- `docs/whiteboard/chat_experience.md` - Tool call flow
- MCP Protocol: <https://modelcontextprotocol.io/>

---

#### **Issue 1.2.2: Implement Mock MCP Servers**

**Context**:
Mock MCP servers validate tool call request formats and return "accepted" or "error". They don't execute actual tool logic, just verify the request structure matches the tool's parameter schema.

**Tasks**:

- Create `mock_services/mock_mcp_server.py`
- Implement FastAPI endpoints for each tool:
  - `POST /tools/web_search`
  - `POST /tools/calendar_add`
  - `POST /tools/query_k0_health`
  - `POST /tools/query_k0_episodic`
  - `POST /tools/query_k0_semantic`
  - `POST /tools/store_prospective_trigger`
- Validation logic:
  - Parse incoming JSON request
  - Validate against tool's parameter schema (from registry)
  - Check required fields present
  - Return: `{"status": "accepted", "tool": "<tool_name>"}` if valid
  - Return: `{"status": "error", "reason": "Missing field: <field>"}` if invalid
- Add request logging for debugging
- Run server on port 8001

**Acceptance Criteria**:

- ✅ Mock server starts and responds to health check
- ✅ Valid requests return "accepted"
- ✅ Invalid requests return descriptive errors
- ✅ All 6 tools have working endpoints
- ✅ Request/response logged for debugging

**References**:

- `docs/whiteboard/chat_experience.md` - MCP tool integration
- FastAPI Docs: <https://fastapi.tiangolo.com/>

---

#### **Issue 1.2.3: Create Tool Call Handler**

**Context**:
Agents need a unified way to call MCP tools. The Tool Call Handler formats requests according to tool schemas, sends to mock MCP servers, and processes responses.

**Tasks**:

- Create `l5_infrastructure/tool_call_handler.py`
- Implement `ToolCallHandler` class:
  - `async call_tool(tool_id, parameters, agent_id)`:
    - Lookup tool definition in registry
    - Validate parameters against schema
    - Format request (add metadata: agent_id, timestamp, trace_id)
    - POST to mock MCP server
    - Handle response (success/error)
    - Return result + receipt
  - Error handling: network errors, timeouts, validation errors
  - Retry logic: 3 attempts with exponential backoff
  - Receipt generation: `{tool_id, status, timestamp, agent_id, trace_id}`
- Add observability: log all tool calls with latency

**Acceptance Criteria**:

- ✅ Can call any tool from registry
- ✅ Invalid parameters caught before sending request
- ✅ Network errors handled gracefully
- ✅ Receipts generated for all calls (success or failure)
- ✅ Latency metrics logged

**References**:

- `docs/whiteboard/chat_experience.md` - Tool call → Receipt flow
- ADR-0008 (Saga Pattern) - Error handling patterns

---

### **Epic 1.3: Prompt Registry**

**Objective**: Create centralized prompt management for agent system prompts

#### **Issue 1.3.1: Design Prompt Registry Schema**

**Context**:
The Prompt Registry stores system prompts for each agent type. Agent Factory fetches prompts when spawning new agents. Prompts define agent personality, capabilities, and behavior.

**Tasks**:

- Create `l5_infrastructure/registries/prompt_registry.py`
- Define prompt schema:

  ```python
  PromptTemplate:
    - agent_type: str (concierge, healthcare, finance, planner, etc.)
    - system_prompt: str (base personality and role)
    - tool_prompt_template: str (how to describe available tools)
    - context_prompt_template: str (how to inject user context)
    - constraints: list[str] (behavioral rules)
    - examples: list[dict] (few-shot examples)
    - temperature: float (LLM creativity setting)
    - max_tokens: int (response length limit)
  ```

- Create initial prompts:
  - **Concierge**: "You are a friendly AI assistant. Route specialized queries to experts. Handle casual chat directly."
  - **Healthcare Agent**: "You are a healthcare specialist. Help users track PT, medications, recovery progress."
  - **Finance Agent**: "You are a finance advisor. Help users with budgets, expenses, financial goals."
  - **Planner Agent**: "You are a task planner. Break down complex requests into executable steps."
  - **Memory Writer**: "You extract entities and context from conversations to store in K0 memory."
- Store prompts in: `config/prompt_registry.json`

**Acceptance Criteria**:

- ✅ Prompt registry loads from JSON file
- ✅ Prompts can be queried by agent_type
- ✅ Template variables support ({{user_context}}, {{tools}}, {{history}})
- ✅ At least 5 agent prompts defined
- ✅ Prompts tested with Groq API for quality

**References**:

- `docs/whiteboard/chat_experience.md` - Agent Factory prompt merging
- ADR-0005 - Agent architecture and roles

---

#### **Issue 1.3.2: Implement Prompt Template Engine**

**Context**:
Prompts need dynamic content injection (user context, tools, chat history). The Template Engine merges static prompts with runtime data.

**Tasks**:

- Create `l5_infrastructure/registries/prompt_template_engine.py`
- Implement `PromptTemplateEngine` class:
  - `render_prompt(agent_type, context_data)`:
    - Fetch prompt template from registry
    - Replace `{{user_context}}` with User KG data
    - Replace `{{tools}}` with formatted tool descriptions
    - Replace `{{history}}` with recent chat messages
    - Replace `{{constraints}}` with privacy/capability constraints
    - Return final prompt string
  - Support conditional blocks: `{{#if has_health_data}}...{{/if}}`
  - Support loops: `{{#each tools}}...{{/each}}`
- Use Jinja2 or simple string formatting

**Acceptance Criteria**:

- ✅ Templates render with all variables replaced
- ✅ Conditional blocks work correctly
- ✅ Loops work for tools and history
- ✅ Missing variables don't break rendering (use defaults)
- ✅ Rendered prompts tested with Groq API

**References**:

- `docs/whiteboard/chat_experience.md` - Agent Factory context merging
- Jinja2 Docs: <https://jinja.palletsprojects.com/>

---

### **Epic 1.4: User Knowledge Graph Setup**

**Objective**: Create graph database for user self-model and personalization

#### **Issue 1.4.1: Design User KG Schema**

**Context**:
The User Knowledge Graph represents the user as a digital twin. All agents query this graph to understand who they're talking to and personalize responses.

**Tasks**:

- Create `l5_infrastructure/user_kg/kg_schema.py`
- Define node types:
  - `Person` (name, age, locale, timezone)
  - `HealthMetric` (type, value, unit, date, confidence)
  - `Goal` (description, deadline, progress, active)
  - `Relationship` (person_name, relation_type, closeness, notes)
  - `Preference` (category, value, strength, source)
  - `Routine` (activity, schedule, adherence_rate, last_execution)
  - `Memory` (summary, date, importance, emotional_valence)
- Define edge types:
  - `HAS_GOAL` (Person → Goal)
  - `TRACKS_METRIC` (Person → HealthMetric)
  - `PREFERS` (Person → Preference)
  - `RELATED_TO` (Person → Relationship)
  - `FOLLOWS_ROUTINE` (Person → Routine)
  - `RECALLS` (Person → Memory)
- Use SQLite with tables for nodes and edges (simpler than Neo4j for PoC)
- Create schema SQL: `config/user_kg_schema.sql`

**Acceptance Criteria**:

- ✅ Schema supports all node and edge types
- ✅ Indexes on frequently queried fields (person_id, date, type)
- ✅ Foreign key constraints maintain referential integrity
- ✅ Schema documented with examples

**References**:

- `docs/whiteboard/chat_experience.md` - User KG requirements
- ADR-0017 (SessionState) - User context representation

---

#### **Issue 1.4.2: Implement User KG Query Interface**

**Context**:
Agents need a simple API to query the User KG without writing raw SQL. The Query Interface provides high-level methods for common queries.

**Tasks**:

- Create `l5_infrastructure/user_kg/kg_query_interface.py`
- Implement `UserKG` class with methods:
  - `get_user_profile(user_id)` - Get Person node with basic info
  - `get_health_context(user_id)` - Get recent HealthMetrics (last 30 days)
  - `get_active_goals(user_id)` - Get all active Goal nodes
  - `get_preferences(user_id, category)` - Get Preferences filtered by category
  - `get_routines(user_id)` - Get all Routine nodes with adherence
  - `get_relationships(user_id)` - Get all Relationship nodes
  - `query_memories(user_id, date_range, keywords)` - Search Memory nodes
  - `add_node(node_type, properties)` - Insert new node
  - `add_edge(from_node, to_node, edge_type, properties)` - Insert new edge
  - `update_node(node_id, properties)` - Update existing node
- Add query caching for performance (cache for 60s)
- Connection pooling for concurrent access

**Acceptance Criteria**:

- ✅ All query methods work correctly
- ✅ Caching reduces repeated queries
- ✅ Thread-safe for concurrent agent access
- ✅ Performance: queries <10ms P95

**References**:

- `docs/whiteboard/chat_experience.md` - Agent KG queries
- SQLite Docs: <https://www.sqlite.org/docs.html>

---

#### **Issue 1.4.3: Seed User KG with Sample Data**

**Context**:
For PoC demonstration, populate User KG with realistic sample data representing a user in PT recovery.

**Tasks**:

- Create `scripts/seed_user_kg.py`
- Seed data for user "John" (age 45):
  - **Person**: John, age 45, timezone US/Pacific
  - **HealthMetrics**:
    - Knee strength: 8.5 kg (2025-11-05)
    - Pain level: 2/10 (2025-11-05)
    - PT sessions completed: 6/8
  - **Goals**:
    - "Return to running by Dec 1, 2025" (progress: 0.85)
    - "Complete 8 PT sessions" (progress: 0.75)
  - **Relationships**:
    - "Mom" (caregiver, lives nearby)
    - "Sarah" (partner, high closeness)
  - **Preferences**:
    - Food: Italian (strength: 0.9)
    - Exercise: Morning (strength: 0.8)
  - **Routines**:
    - PT exercises (daily 8am, adherence: 0.75)
    - Drink water (every 4 hours, adherence: 0.60)
  - **Memories**:
    - "Started PT recovery" (2025-09-15, importance: 0.9)
    - "Last PT session went well" (2025-10-28, importance: 0.7)
- Script should be idempotent (can run multiple times without duplicates)

**Acceptance Criteria**:

- ✅ Script successfully seeds all data
- ✅ Data can be queried via UserKG interface
- ✅ Running script twice doesn't create duplicates
- ✅ Sample data is realistic and demonstrates all node/edge types

**References**:

- `docs/whiteboard/chat_experience.md` - User context examples

---

### **Epic 1.5: Temporal Module (Scheduling & Time Context)**

**Objective**: Implement time-based scheduling and temporal context for proactive features

#### **Issue 1.5.1: Design Temporal Module Architecture**

**Context**:
The Temporal Module manages time-based triggers (reminders, schedules) and provides time context to agents. It runs a background scheduler that evaluates triggers every minute (like K0 P05).

**Tasks**:

- Create `l5_infrastructure/temporal/temporal_module.py`
- Define trigger types:
  - `TimeBasedTrigger`: Fire at specific time (e.g., 8:00am)
  - `RecurringTrigger`: Fire on schedule (e.g., every 4 hours, daily, weekly)
  - `PatternTrigger`: Fire based on detected patterns (e.g., "milk day")
  - `AnomalyTrigger`: Fire on unusual activity
- Define trigger schema:

  ```python
  Trigger:
    - trigger_id: str
    - trigger_type: str
    - fire_time: datetime (next fire time)
    - recurrence: str (None, "4h", "daily", "weekly")
    - message: str (notification text)
    - action: str (what to do when fired)
    - metadata: dict (additional context)
    - active: bool
  ```

- Store triggers in SQLite: `temporal_triggers` table
- Create scheduler loop:
  - Runs every 60 seconds
  - Queries all active triggers where `fire_time <= now()`
  - Sends SSE tick for each fired trigger
  - Updates `fire_time` for recurring triggers

**Acceptance Criteria**:

- ✅ Trigger schema supports all types
- ✅ Scheduler loop runs continuously in background
- ✅ Triggers fire at correct times (±5 seconds)
- ✅ Recurring triggers automatically reschedule

**References**:

- `docs/whiteboard/chat_experience.md` - Proactive flow with K0 P05
- ADR-0019 - Temporal context handling

---

#### **Issue 1.5.2: Implement Trigger Storage & Management**

**Context**:
Agents need to create, update, and delete triggers. The Trigger Manager provides CRUD operations for triggers.

**Tasks**:

- Create `l5_infrastructure/temporal/trigger_manager.py`
- Implement `TriggerManager` class:
  - `create_trigger(trigger_data)` - Insert new trigger
  - `get_trigger(trigger_id)` - Fetch trigger by ID
  - `list_triggers(user_id, active_only=True)` - List user's triggers
  - `update_trigger(trigger_id, updates)` - Update trigger fields
  - `delete_trigger(trigger_id)` - Soft delete (set active=False)
  - `fire_trigger(trigger_id)` - Manual trigger firing for testing
  - `reschedule_recurring(trigger_id)` - Calculate next fire_time
- Add validation:
  - `fire_time` must be in the future
  - `recurrence` must be valid format
  - `message` and `action` required
- Thread-safe for concurrent access

**Acceptance Criteria**:

- ✅ All CRUD operations work correctly
- ✅ Triggers persist across restarts
- ✅ Validation catches invalid triggers
- ✅ Recurring triggers reschedule correctly

**References**:

- `docs/whiteboard/chat_experience.md` - "Remind me to drink water" example

---

#### **Issue 1.5.3: Implement Mock K0 SSE Server for Proactive Ticks**

**Context**:
When triggers fire, the Temporal Module needs to notify K1's ProactiveAgent. This mimics K0 P05 sending SSE ticks to K1.

**Tasks**:

- Create `mock_services/mock_k0_sse_server.py`
- Implement SSE endpoint: `GET /sse/stream`
  - Clients connect and keep connection open
  - Server sends events in SSE format:

    ```
    event: prospective.trigger.fired
    data: {"trigger_id": "...", "time": "...", "message": "...", "action": "..."}
    ```

- Connect Temporal Module to SSE server:
  - When trigger fires in scheduler loop
  - Send tick to all connected SSE clients
  - Log tick sent (for debugging)
- Support multiple SSE topics:
  - `prospective.trigger.fired` - Time-based reminders
  - `prospective.pattern.detected` - Pattern triggers
  - `prospective.anomaly.alert` - Anomaly alerts
- Run SSE server on port 8002

**Acceptance Criteria**:

- ✅ SSE server accepts connections
- ✅ Clients receive ticks when triggers fire
- ✅ Multiple clients can connect simultaneously
- ✅ Connection resilient to brief network interruptions
- ✅ Ticks logged for debugging

**References**:

- `docs/whiteboard/chat_experience.md` - K0 P05 → K1 ProactiveAgent SSE flow
- SSE Spec: <https://html.spec.whatwg.org/multipage/server-sent-events.html>

---

## ✅ **Milestone 1 Completion Criteria**

- ✅ Project structure matches K1 architecture
- ✅ Groq API integrated and tested
- ✅ Tool Registry with 6+ tools defined
- ✅ Mock MCP servers validate tool requests
- ✅ Prompt Registry with 5+ agent prompts
- ✅ User KG schema implemented with sample data
- ✅ Temporal Module scheduler running
- ✅ Mock K0 SSE server sending proactive ticks
- ✅ All components independently tested

**Ready for Milestone 2**: Runtime Core (SessionState, DeltaBus, Mailbox, Lifecycle)

---

## 🎯 **Milestone 2: Layer 4 - Runtime Core**

**Goal**: Implement K1's runtime infrastructure (SessionState, DeltaBus, Mailbox, Agent Lifecycle)
**Duration**: 4-5 days
**Dependencies**: Milestone 1 (Foundation)

### **Epic 2.1: SessionState (6-Section Working Memory)**

**Objective**: Implement in-memory session state with 6 sections and delta tracking

#### **Issue 2.1.1: Design SessionState Data Model**

**Context**:
SessionState is K1's working memory - stores conversation context, user beliefs, agent roster, and execution state. It's the single source of truth for a chat session. Structure follows ADR-0017.

**Tasks**:

- Create `l4_runtime/session_state/session_state.py`
- Define 6-section data model using Pydantic:
  1. **Beliefs** (user beliefs, confidence scores, temporal decay)
     - `belief_id`, `statement`, `confidence` (0-1), `source`, `timestamp`, `decay_rate`
  2. **Scoreboard** (QUD stack, entity tracking, pronoun resolution)
     - `qud_stack` (list of Questions Under Discussion)
     - `entities` (dict of tracked entities with properties)
     - `pronouns` (pronoun → entity mappings)
  3. **Control** (execution state, agent roster, current flow)
     - `session_id`, `current_flow` (specialist/planner), `agent_roster` (list of active agents)
     - `execution_state` (idle/processing/waiting)
  4. **Persona** (personality traits, LLM system prompt fragments)
     - `personality_traits` (friendly, professional, etc.)
     - `communication_style`, `humor_level`
  5. **Multimodal** (audio waveforms, image embeddings - stub for PoC)
     - `audio_buffer` (placeholder), `image_embeddings` (placeholder)
  6. **Meta** (session metadata, trace IDs, metrics)
     - `session_id`, `user_id`, `creation_time`, `turn_count`, `cognitive_trace_id`
- All sections have `last_updated` timestamp
- Implement `to_dict()` and `from_dict()` for serialization
- Add validation: required fields, type checking

**Acceptance Criteria**:

- ✅ All 6 sections defined with correct structure
- ✅ Pydantic validation catches invalid data
- ✅ Serialization/deserialization works correctly
- ✅ In-memory access time <1ms P95

**References**:

- `docs/whiteboard/chat_experience.md` - SessionState 6-section structure
- ADR-0017 - SessionState design
- K1 `k1/l4_runtime/session_state/` - Reference implementation

---

#### **Issue 2.1.2: Implement Delta Computation**

**Context**:
SessionState changes constantly during conversations. Instead of persisting entire state, compute field-level deltas (only what changed). This reduces K0 Bridge bandwidth and enables efficient updates.

**Tasks**:

- Create `l4_runtime/session_state/delta_computer.py`
- Implement `DeltaComputer` class:
  - `compute_deltas(old_state, new_state)` - Compare states, return field-level diffs
  - Delta format:

    ```python
    Delta:
      - field_path: str (e.g., "beliefs.b123.confidence")
      - old_value: Any
      - new_value: Any
      - timestamp: datetime
      - origin: str (which agent caused change)
    ```

  - Handle nested structures (beliefs within beliefs, entities within scoreboard)
  - Handle list operations (append, remove, reorder)
  - Optimize: only compute deltas for changed sections
- Add delta batching:
  - Collect deltas over 250ms window OR 100 deltas (whichever first)
  - Batch format: `{session_id, deltas: [...], batch_timestamp}`
- Implement delta application: `apply_deltas(state, deltas)` - Reconstruct state from deltas

**Acceptance Criteria**:

- ✅ Deltas correctly capture all changes
- ✅ Delta application reconstructs original state
- ✅ Nested structure changes tracked
- ✅ List operations handled correctly
- ✅ Batching reduces delta volume by >80%

**References**:

- `docs/whiteboard/chat_experience.md` - Delta computation flow
- ADR-0019 - Field-level delta serialization
- K1 `k1/l4_runtime/session_state/state_delta_emitter.py`

---

#### **Issue 2.1.3: Implement SessionState Manager**

**Context**:
SessionStateManager provides the primary interface for agents to read/write session state. It handles concurrency, delta computation, and event emission.

**Tasks**:

- Create `l4_runtime/session_state/session_state_manager.py`
- Implement `SessionStateManager` class:
  - `create_session(user_id)` - Initialize new SessionState
  - `get_session(session_id)` - Retrieve existing session
  - `update_section(session_id, section_name, updates)` - Update specific section
    - Computes deltas automatically
    - Emits deltas to DeltaBus
    - Updates `last_updated` timestamp
  - `get_section(session_id, section_name)` - Read section (fast path)
  - `add_belief(session_id, statement, confidence, source)` - High-level API
  - `track_entity(session_id, entity_name, properties)` - High-level API
  - `update_agent_roster(session_id, agent_id, status)` - High-level API
- Add read-write locking for thread safety
- Cache frequently accessed sections (Control, Meta) in memory
- Session timeout: 600s idle → archive session

**Acceptance Criteria**:

- ✅ Concurrent updates don't corrupt state
- ✅ Delta emission happens on every update
- ✅ Read operations <1ms, write operations <5ms
- ✅ Sessions automatically timeout after 600s idle
- ✅ High-level APIs simplify agent code

**References**:

- `docs/whiteboard/chat_experience.md` - SessionState access patterns
- ADR-0017 - SessionState lifecycle
- Python `threading.RLock` for concurrency

---

### **Epic 2.2: DeltaBus (In-Process Event Bus)**

**Objective**: Implement event bus for SessionState delta propagation to Writer Agents

#### **Issue 2.2.1: Design DeltaBus Architecture**

**Context**:
DeltaBus is an in-process pub/sub system. SessionStateManager publishes deltas, Writer Agents subscribe and react. This decouples state changes from persistence logic.

**Tasks**:

- Create `l4_runtime/deltabus/deltabus.py`
- Define event model:

  ```python
  DeltaBusEvent:
    - event_type: str ("session.delta", "agent.spawned", "tool.called")
    - session_id: str
    - payload: dict (event-specific data)
    - timestamp: datetime
    - trace_id: str
  ```

- Implement `DeltaBus` singleton class:
  - `subscribe(event_type, callback)` - Register subscriber
  - `unsubscribe(callback_id)` - Remove subscriber
  - `publish(event)` - Send event to all subscribers
  - `publish_async(event)` - Non-blocking publish
- Use `asyncio.Queue` for async delivery
- Support wildcard subscriptions: `subscribe("session.*", callback)`
- Event ordering guarantee: FIFO per session_id

**Acceptance Criteria**:

- ✅ Events delivered to all subscribers
- ✅ Async publish doesn't block publisher
- ✅ Event ordering preserved per session
- ✅ Wildcard subscriptions work correctly
- ✅ Performance: <1ms event delivery latency

**References**:

- `docs/whiteboard/chat_experience.md` - DeltaBus → Writer Agents flow
- ADR-0019 - Event-driven delta propagation
- Python `asyncio.Queue` for async events

---

#### **Issue 2.2.2: Integrate SessionState with DeltaBus**

**Context**:
SessionStateManager needs to publish delta events to DeltaBus whenever state changes. This enables Writer Agents to react to changes automatically.

**Tasks**:

- Update `l4_runtime/session_state/session_state_manager.py`:
  - Inject `DeltaBus` instance into constructor
  - After computing deltas in `update_section()`:
    - Create `DeltaBusEvent` with `event_type="session.delta"`
    - Include: `session_id`, `deltas`, `origin` (which agent caused change)
    - Call `deltabus.publish_async(event)`
  - Add event for session creation: `event_type="session.created"`
  - Add event for session timeout: `event_type="session.archived"`
- Add observability: log all events published (debug level)
- Add metrics: count events published per event_type

**Acceptance Criteria**:

- ✅ All SessionState updates emit delta events
- ✅ Events contain complete delta information
- ✅ Non-blocking: publish doesn't slow down updates
- ✅ Events logged for debugging

**References**:

- `docs/whiteboard/chat_experience.md` - SessionState → DeltaBus integration
- K1 `k1/l4_runtime/session_state/state_delta_emitter.py`

---

#### **Issue 2.2.3: Create DeltaBus Test Subscriber**

**Context**:
Before building Writer Agents, verify DeltaBus works correctly with a test subscriber that logs all events.

**Tasks**:

- Create `tests/test_deltabus_integration.py`
- Implement `TestSubscriber` class:
  - Subscribes to "session.*" events
  - Logs all received events to console
  - Counts events by type
  - Verifies event structure (required fields present)
- Integration test:
  - Create SessionState
  - Update beliefs, scoreboard, control
  - Verify test subscriber receives all delta events
  - Check event ordering (FIFO)
  - Verify event payloads match updates
- Add performance test: 1000 rapid updates, all events delivered

**Acceptance Criteria**:

- ✅ Test subscriber receives all events
- ✅ Event payloads match SessionState changes
- ✅ Event ordering preserved
- ✅ No events lost under load (1000 updates)

**References**:

- `docs/whiteboard/chat_experience.md` - DeltaBus architecture

---

### **Epic 2.3: Mailbox System (MPSC with 4 Priority Levels)**

**Objective**: Implement async message passing for inter-agent communication

#### **Issue 2.3.1: Design Mailbox Architecture**

**Context**:
Mailboxes enable agents to communicate asynchronously. Each agent has a mailbox (MPSC queue). Messages have 4 priority levels. Weighted Fair Queueing ensures high-priority messages processed first.

**Tasks**:

- Create `l4_runtime/mailbox/mailbox.py`
- Define message model:

  ```python
  Message:
    - message_id: str
    - sender_id: str
    - receiver_id: str
    - priority: int (0=URGENT, 1=REALTIME, 2=INTERACTIVE, 3=BACKGROUND)
    - payload: dict
    - timestamp: datetime
    - trace_id: str
  ```

- Define priority levels (from chat_experience.md):
  - `URGENT (0)` - Processed 4x more often
  - `REALTIME (1)` - Processed 2x more often
  - `INTERACTIVE (2)` - Normal processing (user-facing)
  - `BACKGROUND (3)` - Lowest priority (memory writes)
- Implement `Mailbox` class:
  - `__init__(agent_id, capacity=50)` - Create mailbox with backpressure limit
  - `send(message)` - Enqueue message (async, non-blocking)
  - `receive()` - Dequeue message (async, blocks if empty)
  - `peek()` - Look at next message without removing
  - `size()` - Current queue depth
- Use 4 separate `asyncio.Queue` instances (one per priority)
- Weighted Fair Queueing: Round-robin with weights [4, 2, 1, 1]

**Acceptance Criteria**:

- ✅ Messages enqueue/dequeue correctly
- ✅ Higher priority messages processed first
- ✅ Backpressure: enqueue blocks when capacity reached
- ✅ Performance: <0.5ms P95 enqueue/dequeue latency
- ✅ Thread-safe for concurrent access

**References**:

- `docs/whiteboard/chat_experience.md` - Mailbox system description
- ADR-0005 - Actor Model communication
- Weighted Fair Queueing algorithm

---

#### **Issue 2.3.2: Implement Mailbox Manager**

**Context**:
MailboxManager creates and manages mailboxes for all agents. Provides routing logic to send messages to correct agent mailbox.

**Tasks**:

- Create `l4_runtime/mailbox/mailbox_manager.py`
- Implement `MailboxManager` singleton class:
  - `create_mailbox(agent_id)` - Create new mailbox for agent
  - `get_mailbox(agent_id)` - Retrieve agent's mailbox
  - `delete_mailbox(agent_id)` - Remove mailbox (agent terminated)
  - `send_message(sender_id, receiver_id, payload, priority)` - Route message
    - Lookup receiver's mailbox
    - Create Message object
    - Call `receiver_mailbox.send(message)`
    - Handle errors: receiver not found, mailbox full
  - `broadcast(sender_id, receiver_ids, payload, priority)` - Send to multiple agents
  - `get_stats()` - Return metrics (total messages sent, avg latency, queue depths)
- Add message tracing: log all sends with trace_id
- Add metrics: message count by priority, queue depth per agent

**Acceptance Criteria**:

- ✅ Messages routed to correct agent mailboxes
- ✅ Broadcast delivers to all specified receivers
- ✅ Handles missing receivers gracefully (log warning)
- ✅ Metrics track system load
- ✅ Message tracing works for debugging

**References**:

- `docs/whiteboard/chat_experience.md` - Inter-agent message flow
- K1 `k1/l4_runtime/actor_fabric/mailbox/`

---

#### **Issue 2.3.3: Create Mailbox Integration Tests**

**Context**:
Test mailbox system with simulated agent communication patterns before building real agents.

**Tasks**:

- Create `tests/test_mailbox_integration.py`
- Test scenarios:
  1. **Basic Send/Receive**: Agent A sends to Agent B, B receives
  2. **Priority Ordering**: Send 10 messages (mixed priorities), verify URGENT comes first
  3. **Backpressure**: Fill mailbox to capacity, verify send blocks
  4. **Broadcast**: Send to 5 agents, all receive message
  5. **High Load**: 1000 messages, verify no lost messages
  6. **Weighted Fair Queueing**: Send equal counts of all priorities, verify URGENT gets 4x processing
- Create mock agents for testing:
  - `MockAgent` class with `agent_id` and `receive_loop()`
  - Count messages received by priority
- Measure performance: enqueue/dequeue latency P50, P95, P99

**Acceptance Criteria**:

- ✅ All test scenarios pass
- ✅ Priority ordering works correctly
- ✅ Backpressure prevents unbounded growth
- ✅ No messages lost under load
- ✅ Performance meets <0.5ms P95 target

**References**:

- `docs/whiteboard/chat_experience.md` - Mailbox performance budgets

---

### **Epic 2.4: Agent Lifecycle FSM (6-State Machine)**

**Objective**: Implement agent state machine with transitions and health checks

#### **Issue 2.4.1: Design Agent Lifecycle States**

**Context**:
Every agent has a lifecycle: spawned → warmed up → active → idle → draining → terminated. Each state has entry/exit behaviors and transition rules. Based on ADR-0005 + ADR-0073 enhancements.

**Tasks**:

- Create `l4_runtime/lifecycle/agent_lifecycle.py`
- Define 6 states:
  1. **PENDING**: Agent created, not yet ready
     - Entry: Initialize mailbox, register with MailboxManager
     - Exit: None
  2. **WARMING**: Resource validation and model loading
     - Entry: Check resources (memory, CPU), load model, bind capabilities
     - Exit: Model ready, capabilities verified
     - Budget: <35s P95
  3. **ACTIVE**: Processing tasks, accepting bids
     - Entry: Add to agent roster, ready for work
     - Exit: None
  4. **IDLE**: No tasks, waiting (pooled for reuse)
     - Entry: Start TTL timer (10 minutes default)
     - Health check every 30s
     - Exit: Reactivate or terminate on TTL expiry
  5. **DRAINING**: Finishing tasks, no new work
     - Entry: Stop accepting bids, track in-flight tasks
     - Wait for task completion (max 30s timeout)
     - Exit: All tasks complete or timeout
  6. **TERMINATED**: Agent shut down, resources freed
     - Entry: Unload model, revoke capabilities, delete mailbox
     - Exit: None (final state)
- Define allowed transitions:
  - PENDING → WARMING → ACTIVE
  - ACTIVE ↔ IDLE (bidirectional)
  - ACTIVE/IDLE → DRAINING → TERMINATED
- Create state transition table with validation

**Acceptance Criteria**:

- ✅ All 6 states defined with entry/exit behaviors
- ✅ State transitions follow allowed paths
- ✅ Invalid transitions rejected (with clear error)
- ✅ State documented with ADR references

**References**:

- `docs/whiteboard/chat_experience.md` - Agent Lifecycle FSM section
- ADR-0005 - Agent architecture
- ADR-0073 - WARMING/IDLE/DRAINING enhancements

---

#### **Issue 2.4.2: Implement Lifecycle State Machine**

**Context**:
Agents need a state machine implementation to manage transitions, execute entry/exit behaviors, and track current state.

**Tasks**:

- Create `l4_runtime/lifecycle/lifecycle_fsm.py`
- Implement `LifecycleFSM` class:
  - `__init__(agent_id)` - Initialize in PENDING state
  - `current_state()` - Get current state
  - `transition_to(new_state)` - Change state (validates transition)
    - Check if transition allowed
    - Execute exit behavior of old state
    - Update state
    - Execute entry behavior of new state
    - Emit event to DeltaBus: `agent.state_changed`
    - Log transition with timestamp
  - `can_transition_to(new_state)` - Check if transition valid
  - `get_state_history()` - Return list of state transitions
- Entry/exit behaviors as callbacks:
  - `on_enter_warming()`, `on_exit_warming()`, etc.
  - Agents override these for custom behavior
- Add state timeout enforcement:
  - WARMING: 35s max, auto-transition to TERMINATED if exceeded
  - IDLE: TTL (default 10 min), auto-transition to DRAINING
  - DRAINING: 30s max, force TERMINATED if exceeded

**Acceptance Criteria**:

- ✅ State transitions work correctly
- ✅ Invalid transitions rejected with clear error
- ✅ Entry/exit behaviors execute in order
- ✅ Timeouts enforced automatically
- ✅ State changes logged and emitted to DeltaBus

**References**:

- `docs/whiteboard/chat_experience.md` - Lifecycle state transitions
- ADR-0073 - State-specific behaviors and timeouts

---

#### **Issue 2.4.3: Implement Agent Pooling (IDLE State Optimization)**

**Context**:
Agent pooling reuses agents instead of destroying them. When agent goes IDLE, it stays resident with model loaded. If similar task arrives, reactivate existing agent (<1ms) instead of spawning new one (~30s).

**Tasks**:

- Create `l4_runtime/lifecycle/agent_pool.py`
- Implement `AgentPool` singleton class:
  - `add_to_pool(agent_id, agent_type)` - Add IDLE agent to pool
  - `get_from_pool(agent_type)` - Retrieve pooled agent (if available)
  - `remove_from_pool(agent_id)` - Remove expired/unhealthy agent
  - `pool_size(agent_type)` - Count pooled agents by type
  - `evict_lru()` - Remove least recently used when pool full
- Pooling constraints (from ADR-0073):
  - Max 3 agents per session
  - Max 5 agents globally per type
  - TTL: 10 minutes idle → auto-drain
- Health checks:
  - Run every 30s on pooled agents
  - Check: model still loaded, capabilities valid, mailbox responsive
  - If unhealthy: remove from pool, transition to DRAINING
- Metrics: pool hit rate, avg reuse latency, eviction count

**Acceptance Criteria**:

- ✅ Pooled agents reactivate <1ms
- ✅ Pool respects size limits (3 per session, 5 globally)
- ✅ TTL expiry removes stale agents
- ✅ Health checks catch unhealthy agents
- ✅ Pool hit rate >70% for specialist agents

**References**:

- `docs/whiteboard/chat_experience.md` - Agent pooling for performance
- ADR-0073 - IDLE state pooling with TTL and health checks

---

#### **Issue 2.4.4: Create Lifecycle Integration Tests**

**Context**:
Test agent lifecycle FSM with full state transitions and pooling before integrating with real agents.

**Tasks**:

- Create `tests/test_agent_lifecycle.py`
- Test scenarios:
  1. **Happy Path**: PENDING → WARMING → ACTIVE → IDLE → DRAINING → TERMINATED
  2. **Invalid Transition**: PENDING → ACTIVE (should fail)
  3. **Timeout**: WARMING exceeds 35s → auto-TERMINATED
  4. **Pooling**: Agent goes IDLE → added to pool → reactivated <1ms
  5. **TTL Expiry**: Agent IDLE for 10 min → auto-DRAINING
  6. **Health Check Failure**: Unhealthy agent removed from pool
  7. **Pool Eviction**: Add 6 agents (over limit) → LRU evicted
- Create `MockAgent` with lifecycle FSM:
  - Override entry/exit behaviors to log actions
  - Simulate model loading (100ms delay)
  - Simulate task processing
- Measure state transition latency
- Verify DeltaBus events emitted for state changes

**Acceptance Criteria**:

- ✅ All state transitions work correctly
- ✅ Invalid transitions prevented
- ✅ Timeouts enforced automatically
- ✅ Pooling reduces spawn latency >95%
- ✅ Health checks and eviction work correctly
- ✅ All state changes emit DeltaBus events

**References**:

- `docs/whiteboard/chat_experience.md` - Complete lifecycle flow
- ADR-0073 - Lifecycle performance budgets

---

## ✅ **Milestone 2 Completion Criteria**

- ✅ SessionState 6-section model implemented
- ✅ Delta computation tracks all changes
- ✅ DeltaBus publishes state changes
- ✅ Mailbox system routes messages by priority
- ✅ Agent Lifecycle FSM transitions correctly
- ✅ Agent pooling reduces spawn latency
- ✅ All components integration tested
- ✅ Performance meets budgets (<1ms state access, <0.5ms mailbox ops)

**Ready for Milestone 3**: Layer 5 Infrastructure (Agent Factory, K0 Bridge, Mock Services)

---

## 🎯 **Milestone 3: Layer 5 - Infrastructure**

**Goal**: Build agent spawning, K0 bridge communication, and mock K0 services
**Duration**: 4-5 days
**Dependencies**: Milestone 1 (Foundation), Milestone 2 (Runtime Core)

### **Epic 3.1: Agent Factory (Spawn Agents with Prompt + Tools + Context)**

**Objective**: Dynamically create agents with merged prompts, tool access, and user context

#### **Issue 3.1.1: Design Agent Factory Architecture**

**Context**:
Agent Factory spawns new agents on-demand when Orchestrator needs specialists. It fetches prompts from Prompt Registry, tools from Tool Registry, user context from User KG, and merges everything into a single LLM prompt passed to Groq API.

**Tasks**:

- Create `l5_infrastructure/agent_factory/agent_factory.py`
- Define agent spawn request model:

  ```python
  AgentSpawnRequest:
    - agent_type: str (healthcare, finance, planner, etc.)
    - session_id: str
    - user_id: str
    - required_tools: list[str] (optional, specific tools needed)
    - context_hints: dict (optional, extra context)
    - trace_id: str
  ```

- Factory workflow:
  1. Fetch system prompt from Prompt Registry (by agent_type)
  2. Fetch tools from Tool Registry (by agent_type or required_tools)
  3. Query User KG for user context (health, goals, preferences)
  4. Fetch recent chat history from SessionState (last 5 messages)
  5. Merge all into final prompt using Prompt Template Engine
  6. Create agent instance with Groq client
  7. Initialize agent lifecycle (PENDING state)
  8. Register agent mailbox
  9. Return agent instance
- Support agent reuse: check Agent Pool first before spawning
- Add metrics: agents spawned by type, spawn latency, pool hit rate

**Acceptance Criteria**:

- ✅ Factory spawns agents with complete context
- ✅ Checks pool before spawning (optimization)
- ✅ All required components fetched and merged
- ✅ Agent lifecycle initialized correctly
- ✅ Spawn latency <35s (WARMING state budget)

**References**:

- `docs/whiteboard/chat_experience.md` - Agent Factory merging logic
- ADR-0005 - Agent architecture
- ADR-0073 - WARMING state resource validation

---

#### **Issue 3.1.2: Implement Agent Base Class**

**Context**:
All agents (Concierge, Specialists, Planner, Writers) inherit from a common base class. This provides shared functionality: mailbox access, lifecycle management, tool calling, SessionState updates.

**Tasks**:

- Create `l3_execution/agents/agent_base.py`
- Implement `AgentBase` abstract class:
  - `__init__(agent_id, agent_type, session_id, groq_client, lifecycle_fsm, mailbox, tool_handler)`
  - **Core methods**:
    - `async receive_message()` - Pull message from mailbox
    - `async send_message(receiver_id, payload, priority)` - Send via MailboxManager
    - `async call_tool(tool_id, parameters)` - Use ToolCallHandler
    - `async update_session(section, updates)` - Update SessionState
    - `async query_user_kg(query_type)` - Fetch user context
  - **Lifecycle hooks** (subclasses override):
    - `async on_warming()` - Custom WARMING behavior
    - `async on_active()` - Start processing loop
    - `async on_idle()` - Pause processing
    - `async on_draining()` - Finish in-flight work
    - `async on_terminated()` - Cleanup
  - **Abstract methods** (subclasses must implement):
    - `async process_message(message)` - Handle incoming message
  - Add tracing: inject `cognitive_trace_id` into all operations
  - Add error handling: wrap all operations with try/except

**Acceptance Criteria**:

- ✅ Base class provides all core functionality
- ✅ Lifecycle hooks called at correct times
- ✅ Tracing propagates through all operations
- ✅ Error handling prevents agent crashes
- ✅ Subclasses only need to implement `process_message()`

**References**:

- `docs/whiteboard/chat_experience.md` - Agent architecture
- ADR-0005 - Agent base capabilities
- K1 `k1/l3_execution/agents/` - Reference implementations

---

#### **Issue 3.1.3: Integrate Agent Factory with Agent Pool**

**Context**:
Before spawning a new agent, Agent Factory should check if a pooled agent of the same type is available. This reduces latency from ~30s to <1ms.

**Tasks**:

- Update `l5_infrastructure/agent_factory/agent_factory.py`:
  - In `spawn_agent()` method:
    - First: `pooled_agent = agent_pool.get_from_pool(agent_type)`
    - If found:
      - Reactivate: transition IDLE → ACTIVE
      - Update agent's session_id (may be different session)
      - Refresh user context from User KG
      - Return pooled agent (<1ms path)
    - If not found:
      - Proceed with full spawn (30s path)
      - After spawn complete, register with AgentPool
- Add metrics:
  - Pool hits vs misses
  - Latency: pooled agent reuse vs fresh spawn
  - Pool size by agent type
- Log: "Reused pooled HealthcareAgent" vs "Spawned new HealthcareAgent"

**Acceptance Criteria**:

- ✅ Factory checks pool before spawning
- ✅ Pooled agents reactivated correctly
- ✅ User context refreshed on reuse
- ✅ Pool hit rate >70% for specialist agents
- ✅ Reuse latency <1ms vs spawn latency ~30s

**References**:

- `docs/whiteboard/chat_experience.md` - Agent pooling optimization
- ADR-0073 - IDLE state pooling

---

### **Epic 3.2: K0 Bridge (SessionState Deltas → Mock K0 Validation)**

**Objective**: Batch SessionState deltas and send to Mock K0 for format validation

#### **Issue 3.2.1: Implement State Delta Emitter**

**Context**:
State Delta Emitter collects deltas from DeltaBus, batches them (250ms OR 64KB OR 100 deltas), and hands off to Batch Client for transmission. This reduces K0 Bridge traffic and improves efficiency.

**Tasks**:

- Create `l5_infrastructure/k0_bridge/state_delta_emitter.py`
- Implement `StateDeltaEmitter` class:
  - Subscribe to DeltaBus for "session.delta" events
  - Collect deltas into batch buffer
  - Flush conditions (any triggers flush):
    - Time: 250ms elapsed since last flush
    - Size: 64KB accumulated
    - Count: 100 deltas collected
  - On flush:
    - Create `DeltaBatch` object:

      ```python
      DeltaBatch:
        - batch_id: str
        - session_id: str
        - deltas: list[Delta]
        - batch_timestamp: datetime
        - origin: str (e.g., "session_state_manager")
      ```

    - Hand off to `BatchClient.send_batch(delta_batch)`
    - Clear buffer
  - Run as background async task
  - Graceful shutdown: flush remaining deltas on exit
- Add metrics: batches sent, avg batch size, flush trigger distribution

**Acceptance Criteria**:

- ✅ Deltas batched correctly (not sent individually)
- ✅ All 3 flush triggers work correctly
- ✅ Background task runs continuously
- ✅ No deltas lost on shutdown
- ✅ Batch size reduced traffic by >90%

**References**:

- `docs/whiteboard/chat_experience.md` - K0 Bridge batching pipeline
- ADR-0019 - Delta batching (250ms OR 64KB OR 100 deltas)
- K1 `k1/l5_infrastructure/k0_bridge/state_delta_emitter.py`

---

#### **Issue 3.2.2: Implement Batch Client (HTTP POST to Mock K0)**

**Context**:
Batch Client serializes delta batches to JSON and POSTs to Mock K0 API. Mock K0 validates request format and returns "accepted" or "error". This simulates real K0 communication without actual persistence.

**Tasks**:

- Create `l5_infrastructure/k0_bridge/batch_client.py`
- Implement `BatchClient` class:
  - `async send_batch(delta_batch)` - Main method
    - Serialize `DeltaBatch` to JSON
    - Determine endpoint based on origin:
      - SessionState deltas → `POST /p02/memory_write`
      - Prospective triggers → `POST /p05/prospective_write`
      - Learning signals → `POST /p06/learning_signal`
    - Add headers: `Content-Type: application/json`, `X-Trace-ID: <trace_id>`
    - POST to Mock K0 API (httpx async client)
    - Handle response:
      - `{"status": "accepted"}` → Log success
      - `{"status": "error", "reason": "..."}` → Log error, retry
    - Retry logic: 3 attempts, exponential backoff (1s, 2s, 4s)
    - Timeout: 5s per request
  - Add circuit breaker: if 5 consecutive errors, pause 30s before retry
  - Add metrics: requests sent, success rate, error rate, latency

**Acceptance Criteria**:

- ✅ Batches serialized to correct JSON format
- ✅ Routed to correct Mock K0 endpoint
- ✅ Retry logic handles transient errors
- ✅ Circuit breaker prevents cascading failures
- ✅ Latency <50ms P95 (Mock K0 validation fast)

**References**:

- `docs/whiteboard/chat_experience.md` - K0 Bridge command_client.py
- ADR-0001a - K0 Bridge communication protocol
- K1 `k1/l5_infrastructure/k0_bridge/batch_client.py`

---

#### **Issue 3.2.3: Create Mock K0 API (Format Validation Only)**

**Context**:
Mock K0 API receives delta batches, validates JSON structure matches expected schemas, and returns "accepted" or descriptive errors. No actual persistence - just validation to verify K1 is formatting requests correctly.

**Tasks**:

- Create `mock_services/mock_k0_api.py`
- Implement FastAPI endpoints:
  - `POST /p02/memory_write` - Memory delta batches
    - Validate: `{batch_id, session_id, deltas: [{field_path, old_value, new_value, timestamp, origin}]}`
    - Required fields: batch_id, session_id, deltas (non-empty list)
    - Each delta must have: field_path (string), timestamp (ISO datetime)
  - `POST /p05/prospective_write` - Prospective triggers
    - Validate: `{trigger_id, trigger_type, fire_time, message, action, recurrence, active}`
    - fire_time must be future datetime
    - trigger_type in ["time_based", "recurring", "pattern", "anomaly"]
  - `POST /p06/learning_signal` - Learning feedback
    - Validate: `{signal_id, signal_type, confidence, metadata}`
    - confidence must be 0.0-1.0
- Response format:
  - Success: `{"status": "accepted", "batch_id": "...", "timestamp": "..."}`
  - Error: `{"status": "error", "reason": "Missing field: fire_time", "batch_id": "..."}`
- Add request logging: log all received requests with status
- Run server on port 8003

**Acceptance Criteria**:

- ✅ All 3 endpoints validate request format
- ✅ Valid requests return "accepted"
- ✅ Invalid requests return descriptive errors
- ✅ All requests logged for debugging
- ✅ Response latency <10ms

**References**:

- `docs/whiteboard/chat_experience.md` - Mock K0 validation
- K0 schemas in `k0/contracts/`

---

### **Epic 3.3: Mock K0 SSE Server (Proactive Ticks)**

**Objective**: Send proactive trigger ticks to K1 ProactiveAgent via SSE

#### **Issue 3.3.1: Integrate Temporal Module with SSE Server**

**Context**:
When Temporal Module's scheduler detects fired triggers, it needs to notify Mock K0 SSE Server. SSE Server then broadcasts ticks to connected K1 ProactiveAgents. This completes the proactive flow loop.

**Tasks**:

- Update `l5_infrastructure/temporal/temporal_module.py`:
  - In scheduler loop (runs every 60s):
    - Query active triggers where `fire_time <= now()`
    - For each fired trigger:
      - Create SSE event payload:

        ```python
        SSEEvent:
          - event: "prospective.trigger.fired"
          - data: {
              trigger_id: str,
              time: datetime,
              message: str,
              action: str,
              metadata: dict
            }
        ```

      - Send to SSE Server: `sse_server.broadcast(event)`
      - Update trigger: reschedule if recurring, else mark inactive
    - Log: "Fired trigger {trigger_id}: {message}"
- Add SSE client connection tracking:
  - Temporal Module registers as SSE event source
  - SSE Server tracks connected ProactiveAgents
- Handle SSE disconnections: buffer events, retry delivery

**Acceptance Criteria**:

- ✅ Fired triggers send SSE events
- ✅ Events contain complete trigger data
- ✅ Recurring triggers reschedule automatically
- ✅ Events delivered to all connected clients
- ✅ Buffering handles temporary disconnections

**References**:

- `docs/whiteboard/chat_experience.md` - K0 P05 → SSE → ProactiveAgent flow
- Milestone 1, Epic 1.5 - Temporal Module foundation

---

#### **Issue 3.3.2: Implement SSE Event Broadcasting**

**Context**:
SSE Server needs to broadcast events to multiple connected clients (ProactiveAgents). Events are SSE-formatted with topic-based routing.

**Tasks**:

- Update `mock_services/mock_k0_sse_server.py` (from Milestone 1):
  - Maintain list of connected clients: `{client_id: (connection, subscribed_topics)}`
  - Implement `broadcast(event, topic=None)`:
    - If topic specified: send only to clients subscribed to that topic
    - If no topic: send to all clients
    - Format event as SSE:

      ```
      event: prospective.trigger.fired
      data: {"trigger_id": "...", ...}
      id: <event_id>
      ```

    - Handle send errors: remove disconnected clients
  - Support topic subscriptions:
    - Clients subscribe via query param: `GET /sse/stream?topics=prospective.*`
    - Wildcard support: `prospective.*` matches all prospective events
  - Implement heartbeat: send ping every 30s to keep connections alive
  - Add metrics: connected clients, events sent, delivery errors

**Acceptance Criteria**:

- ✅ Events broadcast to all subscribed clients
- ✅ Topic filtering works correctly
- ✅ Disconnected clients handled gracefully
- ✅ Heartbeat keeps connections alive
- ✅ No events lost for connected clients

**References**:

- `docs/whiteboard/chat_experience.md` - K0 SSE port (:5202) architecture
- SSE Spec: Server-Sent Events standard

---

## ✅ **Milestone 3 Completion Criteria**

- ✅ Agent Factory spawns agents with merged context
- ✅ Agent Base Class provides common functionality
- ✅ Agent pooling integrated (reuse >70%)
- ✅ State Delta Emitter batches efficiently
- ✅ Batch Client sends to Mock K0
- ✅ Mock K0 API validates all request formats
- ✅ SSE Server broadcasts proactive ticks
- ✅ All components integration tested

**Ready for Milestone 4**: Layer 3 Agents (Concierge, ProactiveAgent, Specialists, Writers)

---

## 🎯 **Milestone 4: Layer 3 - Agents (Tier 1 & 2)**

**Goal**: Implement core agents (Concierge, ProactiveAgent, Specialist Agents)
**Duration**: 5-6 days
**Dependencies**: Milestone 1-3 (Foundation, Runtime, Infrastructure)

### **Epic 4.1: Concierge Agent (Tier 1 - Always-Active)**

**Objective**: Implement master coordinator for intent routing and casual chat handling

#### **Issue 4.1.1: Implement Concierge Intent Classification**

**Context**:
Concierge receives all user messages and classifies intent into 3 categories: meta-intent (handle directly), query-intent (route to Specialist), planning-intent (route to Planner). Uses LLM with few-shot examples for classification.

**Tasks**:

- Create `l3_execution/agents/concierge_agent.py`
- Implement `ConciergeAgent` (inherits from `AgentBase`):
  - `async process_message(message)` - Main handler
    - Extract user input from message payload
    - Query User KG: get user profile for personalization
    - Classify intent using Groq LLM:

      ```python
      Intent:
        - type: str ("meta", "query", "planning")
        - confidence: float (0-1)
        - routing_target: str (None, agent_type, or "planner")
        - reasoning: str (why this classification)
      ```

    - Few-shot examples in system prompt:
      - "hey what's up?" → meta (handle directly)
      - "how's my recovery?" → query (route to HealthcareAgent)
      - "plan a trip to Hawaii" → planning (route to Planner)
    - Decision tree:
      - If meta: handle with `_handle_meta_intent()`
      - If query: route with `_route_to_specialist()`
      - If planning: route with `_route_to_planner()`
  - Add SessionState updates:
    - Update Control.current_flow ("casual_chat" / "specialist" / "planning")
    - Track conversation turn count in Meta section
- Add observability: log all intent classifications with confidence

**Acceptance Criteria**:

- ✅ Intent classification accuracy >90% (manual test)
- ✅ Meta-intents handled correctly (greetings, small talk)
- ✅ Query-intents route to correct specialist type
- ✅ Planning-intents route to Planner
- ✅ SessionState updated with current flow

**References**:

- `docs/whiteboard/chat_experience.md` - Concierge decision making
- ADR-0005 - Concierge role as Tier 1 AI Agent

---

#### **Issue 4.1.2: Implement Specialist Agent Routing with Chat Feedback**

**Context**:
When Concierge detects specialized knowledge needed, it shows "⏳ Looping in health specialist..." message to user BEFORE routing. This provides transparency and manages user expectations during agent spawning.

**Tasks**:

- Implement `_route_to_specialist(user_input, specialist_type)` in `ConciergeAgent`:
  - Step 1: Send immediate feedback to user
    - Format: "⏳ Looping in {specialist_type} to give you better insights..."
    - Send via chat interface (update SessionState.Scoreboard with pending message)
  - Step 2: Check if specialist already active in agent roster
    - Query SessionState.Control.agent_roster
    - If found: send message directly to specialist's mailbox
    - If not found: request spawn from Orchestrator
  - Step 3: Send task to specialist/Orchestrator:
    - Create task envelope:

      ```python
      TaskEnvelope:
        - task_id: str
        - user_input: str
        - specialist_type: str
        - user_context: dict (from User KG)
        - session_id: str
        - trace_id: str
      ```

    - Priority: INTERACTIVE (2) - user-facing
  - Step 4: Wait for specialist response (async)
    - Timeout: 5s (specialist should respond quickly)
    - If timeout: show error to user
  - Step 5: Relay specialist response back to user
    - Format response with personality (friendly, clear)
- Add SessionState updates:
  - Control.agent_roster: add specialist when spawned
  - Beliefs: store any facts learned from specialist response
  - Meta: increment turn_count

**Acceptance Criteria**:

- ✅ "Looping in specialist" message appears before routing
- ✅ Existing specialists reused (no duplicate spawns)
- ✅ Task envelope contains complete context
- ✅ Specialist responses relayed correctly
- ✅ Timeout handling prevents hanging

**References**:

- `docs/whiteboard/chat_experience.md` - "Looping in specialist" user experience
- ADR-0005 - Concierge routing logic

---

#### **Issue 4.1.3: Implement Meta-Intent Direct Handling**

**Context**:
Meta-intents (greetings, acknowledgements, small talk, time queries) don't require orchestration. Concierge handles these directly with quick LLM responses.

**Tasks**:

- Implement `_handle_meta_intent(user_input, intent_subtype)` in `ConciergeAgent`:
  - Detect intent subtypes (11 patterns from chat_experience.md):
    - ACK: "ok", "thanks", "got it"
    - GREETING: "hey", "hi", "hello"
    - SMALL_TALK: "how are you?", "what's up?"
    - TIME_QUERY: "what time is it?"
    - STATUS: "what's my status?", "what are we doing?"
    - CLARIFICATION: "what do you mean?", "can you explain?"
    - Others: AFFIRMATION, REJECTION, WAIT, CANCEL, HELP
  - For simple queries (TIME, STATUS):
    - Generate response directly (no LLM needed)
    - Example: "It's 3:45 PM" for time query
  - For conversational queries (GREETING, SMALL_TALK):
    - Use LLM with persona-aware prompt
    - Keep responses brief and friendly
    - Example: "Hey! I'm here to help. How's your day going?"
  - Update SessionState:
    - Scoreboard: track conversation flow
    - Meta: increment turn_count
  - Latency target: <200ms (fast, no orchestration)

**Acceptance Criteria**:

- ✅ All 11 meta-intent patterns handled
- ✅ Simple queries answered without LLM (<50ms)
- ✅ Conversational queries use persona (<200ms)
- ✅ Responses match Concierge personality
- ✅ No unnecessary orchestration triggered

**References**:

- `docs/whiteboard/chat_experience.md` - Meta-intent triage (11 patterns)
- ADR-0005 - Concierge direct resolution

---

### **Epic 4.2: ProactiveAgent (Tier 1 - Always-Active SSE Listener)**

**Objective**: Listen to SSE ticks from Mock K0 and trigger proactive notifications

#### **Issue 4.2.1: Implement SSE Client Connection**

**Context**:
ProactiveAgent connects to Mock K0 SSE Server on startup and maintains persistent connection. It subscribes to "prospective.*" events to receive trigger ticks.

**Tasks**:

- Create `l3_execution/agents/proactive_agent.py`
- Implement `ProactiveAgent` (inherits from `AgentBase`):
  - `async on_active()` - Lifecycle hook when agent becomes ACTIVE
    - Connect to SSE Server: `GET http://localhost:8002/sse/stream?topics=prospective.*`
    - Keep connection open indefinitely
    - Handle reconnection on disconnect (retry every 5s)
  - `async _sse_listen_loop()` - Background task
    - Parse SSE events in real-time
    - Dispatch to handlers based on event type:
      - `prospective.trigger.fired` → `_handle_trigger_tick()`
      - `prospective.pattern.detected` → `_handle_pattern_tick()`
      - `prospective.anomaly.alert` → `_handle_anomaly_tick()`
    - Log all received ticks with trace_id
  - Handle SSE connection errors:
    - Network errors: retry with exponential backoff
    - Parse errors: log and skip malformed events
  - Graceful shutdown: close SSE connection on DRAINING

**Acceptance Criteria**:

- ✅ SSE connection established on agent ACTIVE
- ✅ All "prospective.*" events received
- ✅ Automatic reconnection on disconnect
- ✅ Events dispatched to correct handlers
- ✅ Clean shutdown on agent DRAINING

**References**:

- `docs/whiteboard/chat_experience.md` - ProactiveAgent SSE listener
- ADR-0005 - ProactiveAgent role
- Milestone 3, Epic 3.3 - Mock K0 SSE Server

---

#### **Issue 4.2.2: Implement Proactive Trigger Handlers**

**Context**:
When SSE tick arrives (trigger fired), ProactiveAgent needs to notify the user. Notification method depends on trigger type and action.

**Tasks**:

- Implement tick handlers in `ProactiveAgent`:
  - `_handle_trigger_tick(tick_data)`:
    - Parse: `{trigger_id, time, message, action, metadata}`
    - Determine action type:
      - `notify_user`: Send message to user immediately
      - `enrich_context`: Add to SessionState for next turn
      - `invoke_agent`: Trigger specific agent to act
    - For `notify_user`:
      - Format notification: "💧 Time to drink water! (4/8 daily goal)"
      - Send via Concierge (Concierge handles user communication)
      - Update SessionState: add notification to Scoreboard
    - For `enrich_context`:
      - Add trigger data to SessionState.Control.proactive_triggers
      - Next user turn can reference this context
    - For `invoke_agent`:
      - Send message to specified agent's mailbox
      - Example: RoutineAgent handles routine triggers
  - `_handle_pattern_tick(tick_data)`:
    - Parse detected pattern: "Milk day detected with 85% confidence"
    - Notify user: "Looks like today is milk day - reminder to buy milk?"
  - `_handle_anomaly_tick(tick_data)`:
    - Parse anomaly: "Unusual spending detected: $500 at restaurant"
    - Notify user: "⚠️ Unusual activity: large transaction detected"
- Update SessionState:
  - Meta: track proactive_ticks_received count
  - Control: store recent ticks for context

**Acceptance Criteria**:

- ✅ All tick types handled correctly
- ✅ User notifications formatted clearly
- ✅ Context enrichment works for next turn
- ✅ Agent invocations route correctly
- ✅ SessionState updated with tick history

**References**:

- `docs/whiteboard/chat_experience.md` - Proactive flow example
- K0 P05 - Prospective memory pipeline

---

### **Epic 4.3: Specialist Agents (Tier 2 - On-Demand Dynamic Creation)**

**Objective**: Implement specialist agents that query K0/User KG for domain-specific insights

#### **Issue 4.3.1: Implement HealthcareAgent (Specialist)**

**Context**:
HealthcareAgent handles health-related queries: PT schedules, medications, recovery progress, pain tracking. It queries User KG for health context and Mock K0 for episodic memories.

**Tasks**:

- Create `l3_execution/agents/specialists/healthcare_agent.py`
- Implement `HealthcareAgent` (inherits from `AgentBase`):
  - System prompt (from Prompt Registry):
    - "You are a healthcare specialist helping users track physical therapy, medications, and recovery progress."
  - `async process_message(message)` - Main handler
    - Extract user query: "How's my recovery?"
    - Query User KG:
      - `get_health_context(user_id)` → Recent HealthMetrics
      - `get_active_goals(user_id)` → Health goals
      - `get_routines(user_id)` → PT exercises adherence
    - Call MCP tool: `query_k0_health`
      - Search episodic memories for PT sessions
      - Extract: dates, exercises completed, therapist notes
    - Synthesize response using Groq LLM:
      - Combine User KG data + K0 memories
      - Format personalized insight
      - Example: "Your recovery is on track! You've completed 6/8 PT sessions. Knee strength improved 40%. Next PT: Nov 12 at 2pm."
    - Send response back to Concierge
  - Update SessionState:
    - Beliefs: add health insights as beliefs
    - Scoreboard: track entities mentioned (PT, therapist, knee)

**Acceptance Criteria**:

- ✅ Queries User KG for health context
- ✅ Calls query_k0_health tool correctly
- ✅ Synthesizes personalized insights
- ✅ Response format clear and actionable
- ✅ SessionState updated with learned facts

**References**:

- `docs/whiteboard/chat_experience.md` - HealthcareAgent example
- User KG schema (Milestone 1, Epic 1.4)

---

#### **Issue 4.3.2: Implement FinanceAgent (Specialist)**

**Context**:
FinanceAgent handles finance queries: budgets, expenses, savings goals, upcoming bills.

**Tasks**:

- Create `l3_execution/agents/specialists/finance_agent.py`
- Implement `FinanceAgent` (similar structure to HealthcareAgent):
  - System prompt: "You are a finance advisor helping users manage budgets and expenses."
  - Query User KG:
    - `get_preferences(user_id, category="finance")` → Budget limits
    - `get_active_goals(user_id)` → Savings goals
  - Call MCP tool: `query_k0_finance` (queries K0 episodic for transactions)
  - Synthesize response:
    - Budget analysis, spending trends, goal progress
    - Example: "You've spent $1,200 this month (80% of budget). Groceries: $400, Dining: $300. On track for $500 savings goal."
  - Update SessionState: track financial entities (budget, categories)

**Acceptance Criteria**:

- ✅ Queries User KG and K0 correctly
- ✅ Synthesizes financial insights
- ✅ Budget analysis accurate
- ✅ Response actionable

**References**:

- `docs/whiteboard/chat_experience.md` - Specialist agent patterns

---

#### **Issue 4.3.3: Implement ResearcherAgent (Specialist)**

**Context**:
ResearcherAgent handles information lookup queries: web search, knowledge synthesis, factual questions.

**Tasks**:

- Create `l3_execution/agents/specialists/researcher_agent.py`
- Implement `ResearcherAgent`:
  - System prompt: "You are a research assistant providing factual information."
  - Call MCP tool: `web_search` (mock validates request format)
  - For PoC: Return mock search results (no actual search)
  - Synthesize response from "search results"
  - Example: "I found 3 Italian restaurants nearby: Bella Italia, Luigi's, Trattoria..."

**Acceptance Criteria**:

- ✅ Calls web_search tool correctly
- ✅ Synthesizes mock results
- ✅ Response formatted clearly

**References**:

- `docs/whiteboard/chat_experience.md` - ResearcherAgent role

---

## ✅ **Milestone 4 Completion Criteria**

- ✅ Concierge routes intents correctly (>90% accuracy)
- ✅ "Looping in specialist" messages appear in chat
- ✅ Meta-intents handled directly (<200ms)
- ✅ ProactiveAgent receives SSE ticks
- ✅ Proactive notifications delivered to users
- ✅ HealthcareAgent, FinanceAgent, ResearcherAgent functional
- ✅ All specialists query User KG and Mock K0
- ✅ SessionState updated by all agents

**Ready for Milestone 5**: Writer Agents & Planner + Orchestrator

---

## 🎯 **Milestone 5: Layer 3 - Writer Agents (Tier 3 Background)**

**Goal**: Implement background agents that process SessionState deltas and write to Mock K0
**Duration**: 3-4 days
**Dependencies**: Milestone 1-4 (Foundation, Runtime, Infrastructure, Core Agents)

### **Epic 5.1: MemoryWriterAgent (Always-Active Background)**

**Objective**: Extract entities from SessionState deltas and batch writes to Mock K0 P02/P05

#### **Issue 5.1.1: Implement MemoryWriterAgent Core**

**Context**:
MemoryWriterAgent subscribes to DeltaBus for SessionState deltas. It enriches deltas with metadata (entities, temporal context, trigger candidates), batches them, and sends to K0 Bridge. Knows P02 (episodic memory) and P05 (prospective memory) schemas.

**Tasks**:

- Create `l3_execution/agents/writers/memory_writer_agent.py`
- Implement `MemoryWriterAgent` (inherits from `AgentBase`):
  - `async on_active()` - Lifecycle hook
    - Subscribe to DeltaBus for "session.delta" events
    - Start background processing loop
  - `async _process_delta_event(event)` - Main handler
    - Extract delta from event payload
    - Classify delta type:
      - Beliefs change → Episodic memory (P02)
      - Prospective trigger request → Prospective memory (P05)
      - Entity tracking → Episodic with entity tags
    - Enrich delta with metadata:
      - Extract entities: names, dates, locations, health metrics
      - Add temporal context: timestamp, duration, recurrence
      - Tag with session_id, user_id, agent_roster
      - Detect prospective trigger candidates:
        - Keywords: "remind me", "every", "daily", "at X time"
        - Parse trigger parameters (fire_time, recurrence, message)
    - Batch deltas: collect 100 OR 250ms window
    - Send batch to K0 Bridge via `BatchClient`
  - Handle different schema requirements:
    - P02 (episodic): `{session_id, deltas, entities, timestamp, importance}`
    - P05 (prospective): `{trigger_id, fire_time, recurrence, message, action}`
- Add observability: log all batches sent with entity count

**Acceptance Criteria**:

- ✅ Subscribes to DeltaBus successfully
- ✅ Entities extracted accurately (names, dates, metrics)
- ✅ Prospective triggers detected from keywords
- ✅ Batches sent to correct K0 endpoints (P02 vs P05)
- ✅ Mock K0 validates all batch formats

**References**:

- `docs/whiteboard/chat_experience.md` - MemoryWriterAgent knows P02/P05 schemas
- ADR-0019 - Delta enrichment
- K0 P02/P05 schemas in `k0/contracts/`

---

#### **Issue 5.1.2: Implement Entity Extraction Logic**

**Context**:
Entity extraction identifies important concepts from SessionState deltas: people, places, health metrics, temporal references. These entities enhance memory searchability in K0.

**Tasks**:

- Create `l3_execution/agents/writers/entity_extractor.py`
- Implement `EntityExtractor` class:
  - `extract_entities(delta, session_state)` - Main method
    - Use LLM (Groq) with entity extraction prompt
    - Extract entity types:
      - **Person**: Names, relationships (Mom, Sarah, Dr. Smith)
      - **HealthMetric**: Measurements (knee strength: 8.5kg, pain: 2/10)
      - **Temporal**: Dates, times, durations (Nov 12, 8am, 4 hours)
      - **Location**: Places (hospital, home, restaurant name)
      - **Goal**: Objectives (return to running, save $500)
      - **Routine**: Activities (PT exercises, drink water)
    - Return structured entities:

      ```python
      Entity:
        - entity_id: str
        - entity_type: str (person, health_metric, temporal, etc.)
        - value: str (entity value)
        - confidence: float (0-1)
        - source_delta: str (field_path from delta)
      ```

    - Cross-reference with User KG: link entities to existing KG nodes
  - Optimization: cache LLM results for 60s (avoid re-extracting same delta)

**Acceptance Criteria**:

- ✅ All entity types extracted correctly
- ✅ Entity linking with User KG works
- ✅ Confidence scores reasonable (>0.8 for clear entities)
- ✅ Extraction latency <500ms per delta batch

**References**:

- `docs/whiteboard/chat_experience.md` - Entity extraction for memory
- User KG schema (Milestone 1, Epic 1.4)

---

#### **Issue 5.1.3: Implement Prospective Trigger Detection**

**Context**:
When user says "remind me to drink water every 4 hours", MemoryWriterAgent needs to detect this is a prospective trigger request and create appropriate P05 schema payload.

**Tasks**:

- Create `l3_execution/agents/writers/trigger_detector.py`
- Implement `TriggerDetector` class:
  - `detect_triggers(user_input, session_state)` - Main method
    - Keyword patterns:
      - Time-based: "remind me", "alert me", "notify me"
      - Recurring: "every X hours", "daily at X", "weekly on X"
      - Pattern: "when I usually", "like last time"
    - Parse trigger parameters using LLM:
      - `fire_time`: When to first trigger (parse natural language time)
      - `recurrence`: Frequency (None, "4h", "daily", "weekly")
      - `message`: User-friendly notification text
      - `action`: What to do (notify_user, enrich_context, invoke_agent)
    - Create P05 payload:

      ```python
      ProspectiveTrigger:
        - trigger_id: str (UUID)
        - trigger_type: str ("time_based", "recurring")
        - fire_time: datetime
        - recurrence: str (None or cron-like)
        - message: str
        - action: str
        - metadata: dict (user_id, session_id, origin)
        - active: bool (True)
      ```

    - Validation: fire_time must be future, recurrence format valid
  - Handle edge cases:
    - Ambiguous time: "later" → ask for clarification (return None)
    - Past time: "yesterday" → return error
    - Invalid recurrence: "every 0 hours" → return error

**Acceptance Criteria**:

- ✅ Trigger keywords detected reliably
- ✅ Time parsing handles natural language ("in 4 hours", "tomorrow at 8am")
- ✅ Recurrence patterns parsed correctly
- ✅ P05 payload passes Mock K0 validation
- ✅ Edge cases handled gracefully

**References**:

- `docs/whiteboard/chat_experience.md` - "Remind me to drink water" example
- Temporal Module (Milestone 1, Epic 1.5) - Trigger schema
- K0 P05 schema

---

### **Epic 5.2: LearningExtractorAgent (Background)**

**Objective**: Extract learning signals from user feedback and agent performance

#### **Issue 5.2.1: Implement LearningExtractorAgent Core**

**Context**:
LearningExtractorAgent monitors SessionState for learning signals: user corrections, feedback, agent successes/failures. Sends learning signals to Mock K0 P06 (learning pipeline).

**Tasks**:

- Create `l3_execution/agents/writers/learning_extractor_agent.py`
- Implement `LearningExtractorAgent` (inherits from `AgentBase`):
  - Subscribe to DeltaBus for:
    - "session.delta" events (user feedback in Scoreboard)
    - "agent.task_completed" events (agent performance)
    - "tool.called" events (tool success/failure)
  - `async _process_learning_event(event)` - Main handler
    - Extract learning signal types:
      - **User Correction**: User corrects agent response
        - Example: Agent says "PT is Nov 10", user corrects "No, Nov 12"
        - Signal: `{signal_type: "correction", old_value, new_value, confidence: -0.5}`
      - **Positive Feedback**: User says "thanks", "perfect", "exactly"
        - Signal: `{signal_type: "positive", agent_id, task_id, confidence: +0.3}`
      - **Negative Feedback**: User says "no", "wrong", "not what I asked"
        - Signal: `{signal_type: "negative", agent_id, task_id, confidence: -0.4}`
      - **Task Success**: Task completed within budget, user satisfied
        - Signal: `{signal_type: "success", agent_id, latency, cost}`
      - **Task Failure**: Timeout, error, user dissatisfaction
        - Signal: `{signal_type: "failure", agent_id, error_type, retry_count}`
    - Create P06 payload:

      ```python
      LearningSignal:
        - signal_id: str
        - signal_type: str (correction, positive, negative, success, failure)
        - agent_id: str (which agent generated signal)
        - confidence_delta: float (-1.0 to +1.0)
        - metadata: dict (task details, user feedback text)
        - timestamp: datetime
      ```

    - Send to K0 Bridge → Mock K0 P06
  - Add drift detection:
    - Compare agent predictions vs actual outcomes
    - If drift >20% over 10 tasks → signal: `{signal_type: "drift_detected"}`

**Acceptance Criteria**:

- ✅ All learning signal types detected
- ✅ User feedback classified correctly (positive/negative/correction)
- ✅ Agent performance tracked (success/failure)
- ✅ P06 payloads pass Mock K0 validation
- ✅ Drift detection triggers appropriately

**References**:

- `docs/whiteboard/chat_experience.md` - LearningExtractorAgent knows P06 schema
- K0 P06 - Learning pipeline
- ADR-0006 - Agent performance tracking

---

### **Epic 5.3: SemanticEnricherAgent (Background)**

**Objective**: Enrich memories with semantic tags, concepts, and affect

#### **Issue 5.3.1: Implement SemanticEnricherAgent Core**

**Context**:
SemanticEnricherAgent analyzes SessionState deltas to extract semantic meaning: concepts, relationships, emotional valence. Updates User KG with semantic connections.

**Tasks**:

- Create `l3_execution/agents/writers/semantic_enricher_agent.py`
- Implement `SemanticEnricherAgent` (inherits from `AgentBase`):
  - Subscribe to DeltaBus for "session.delta" events
  - `async _process_delta_event(event)` - Main handler
    - Semantic analysis on delta content:
      - **Concept Extraction**: Identify abstract concepts
        - Example: "recovery", "progress", "pain management"
      - **Relationship Extraction**: Identify connections
        - Example: "PT helps knee strength", "Mom provides support"
      - **Affect Analysis**: Emotional tone
        - Example: "frustrated about slow progress" → negative valence
        - Example: "excited to return to running" → positive valence
      - **Salience Scoring**: Importance (0-1)
        - Based on: user emphasis, repetition, emotional intensity
    - Update User KG:
      - Add concept nodes: `{concept_id, concept_name, definition}`
      - Add relationship edges: `{from_node, to_node, relation_type, strength}`
      - Update memory nodes: add affect, salience, concepts tags
    - Create semantic index payload:

      ```python
      SemanticEnrichment:
        - enrichment_id: str
        - session_id: str
        - concepts: list[str]
        - relationships: list[dict]
        - affect: dict (valence, arousal, dominance)
        - salience: float (0-1)
        - timestamp: datetime
      ```

    - Send to K0 Bridge → Mock K0 semantic index
  - Use LLM (Groq) for semantic analysis with specialized prompt

**Acceptance Criteria**:

- ✅ Concepts extracted accurately
- ✅ Relationships identified correctly
- ✅ Affect analysis reasonable (matches user tone)
- ✅ Salience scores prioritize important information
- ✅ User KG updated with semantic data

**References**:

- `docs/whiteboard/chat_experience.md` - SemanticEnricherAgent enriches KG
- User KG schema (Milestone 1, Epic 1.4)
- K0 semantic memory structure

---

## ✅ **Milestone 5 Completion Criteria**

- ✅ MemoryWriterAgent extracts entities and batches to K0
- ✅ Prospective triggers detected and sent to P05
- ✅ LearningExtractorAgent captures learning signals
- ✅ SemanticEnricherAgent enriches User KG
- ✅ All Writer Agents run in background (non-blocking)
- ✅ Mock K0 validates all P02/P05/P06 payloads
- ✅ Writer Agents don't block user responses

**Ready for Milestone 6**: Layer 2 Orchestration (Orchestrator, Planner, DAG Executor)

---

## 🎯 **Milestone 6: Layer 2 - Orchestration**

**Goal**: Implement orchestrator, planner, and DAG execution for multi-step task coordination
**Duration**: 6-7 days
**Dependencies**: Milestone 1-5 (All foundation, agents, and infrastructure)

### **Epic 6.1: Orchestrator (3-Phase Contract Net)**

**Objective**: Implement deterministic agent selection and task coordination

#### **Issue 6.1.1: Implement Phase 1 - Negotiation (Task Announcement & Bidding)**

**Context**:
When Concierge routes a task-intent to Orchestrator, Phase 1 broadcasts task announcement to capable agents. Agents evaluate and submit bids with confidence scores. Based on ADR-0006a.

**Tasks**:

- Create `l2_orchestration/orchestrator/orchestrator.py`
- Implement `Orchestrator` class (Pure Actor, NO LLM):
  - `async execute_task(task_envelope)` - Main entry point
    - Parse task requirements: required tools, domain, complexity
  - **Phase 1: Negotiation (<50ms P95 budget)**
    - `async _phase1_negotiation(task_envelope)` method:
      - Step 1: Identify capable agents
        - Query Agent Registry: which agent types have required tools?
        - Check Agent Roster (SessionState.Control): which agents already ACTIVE?
        - Result: list of candidate agents (active + spawnable)
      - Step 2: Broadcast task announcement
        - Create `TaskAnnouncement` message:

          ```python
          TaskAnnouncement:
            - task_id: str
            - task_type: str (query, planning, tool_execution)
            - required_tools: list[str]
            - budget: dict (time_ms, cost_credits)
            - deadline_ms: int (50ms for bids)
            - user_context: dict (from User KG)
            - trace_id: str
          ```

        - Send to candidate agents' mailboxes (Priority: INTERACTIVE)
        - Non-blocking send (fire-and-forget)
      - Step 3: Collect proposals (50ms deadline)
        - Use `asyncio.wait_for(timeout=0.05)` to collect bids
        - Agents respond with `Proposal`:

          ```python
          Proposal:
            - agent_id: str
            - confidence: float (0-1, from 4 factors)
            - estimated_latency_ms: int
            - estimated_cost: float
            - can_parallelize: bool
            - message: str (why I'm suited)
          ```

        - Early exit: if all expected agents responded, stop waiting
        - Handle no proposals: fallback to spawn new agent
      - Step 4: Fallback handling (if no proposals)
        - Tier 1: Hire new agent from Agent Factory
        - Tier 2: Simplify task (reduce tool count)
        - Tier 3: Wait 100ms, retry announcement
        - Tier 4: Graceful degradation (return error to Concierge)
  - Add observability: log all announcements and received proposals

**Acceptance Criteria**:

- ✅ Task announcements broadcast correctly
- ✅ Proposals collected within 50ms deadline
- ✅ Capable agents identified accurately
- ✅ Fallback handling works for no-proposal scenario
- ✅ Phase 1 latency <50ms P95

**References**:

- `docs/whiteboard/chat_experience.md` - Phase 1 Negotiation detailed flow
- ADR-0006a - Contract Net Protocol Phase 1
- Smith 1980 - Contract Net Protocol paper

---

#### **Issue 6.1.2: Implement Agent Confidence Scoring (4 Factors)**

**Context**:
When agents receive task announcements, they evaluate their suitability and compute confidence score from 4 factors: capability match, success rate, load, context availability.

**Tasks**:

- Create `l2_orchestration/orchestrator/confidence_scorer.py`
- Implement `ConfidenceScorer` utility (used by agents):
  - `compute_confidence(agent, task_announcement)` - Main method
    - **Factor 1: Capability Match (40% weight)**
      - Check: Do I have all required tools?
      - Score: (matching_tools / required_tools) × 0.4
      - Example: 3/3 tools = 0.4, 2/3 tools = 0.27
    - **Factor 2: Success Rate (30% weight)**
      - Historical success rate for this task type
      - Score: success_rate × 0.3
      - Example: 90% success = 0.27, 50% success = 0.15
      - Initially: default 0.7 (70% success assumption)
    - **Factor 3: Load (20% weight, inverse)**
      - Current mailbox depth (lower = better)
      - Score: (1 - mailbox_depth / capacity) × 0.2
      - Example: 10/50 depth = 0.16, 40/50 depth = 0.04
    - **Factor 4: Context Availability (10% weight)**
      - Do I have session context cached?
      - Score: 0.1 if context available, 0.0 if not
    - **Total Confidence**: Sum all factors (0.0 - 1.0)
  - Threshold: Only bid if confidence ≥ 0.5 (50%)
  - Add to Proposal message: include factor breakdown for explainability

**Acceptance Criteria**:

- ✅ All 4 factors computed correctly
- ✅ Weighted sum ranges 0.0-1.0
- ✅ Agents only bid if confidence ≥ 0.5
- ✅ Factor breakdown included for debugging

**References**:

- `docs/whiteboard/chat_experience.md` - Phase 1 confidence scoring (4 factors)
- ADR-0006a - Bidding criteria

---

#### **Issue 6.1.3: Implement Phase 2 - Selection (Weighted Scoring & Tie-Breaking)**

**Context**:
Orchestrator scores all proposals using Multi-Criteria Decision Analysis (MADM) with weighted factors. Selects best agent(s) and sends task assignment. Based on ADR-0006b. Budget: <5ms P95.

**Tasks**:

- Implement `_phase2_selection(proposals, task_envelope)` in `Orchestrator`:
  - **Step 1: Normalize factors** (all to 0-1 scale)
    - Confidence: Already 0-1 from agent
    - Latency: `1.0 if latency ≤ 50% budget, else decay to 0.5 at budget`
    - Cost: `1.0 if cost ≤ 30% budget, else decay to 0.5 at budget`
    - Parallelism: `1.0 (yes) or 0.7 (partial) or 0.0 (no)`
    - Track record: Agent's historical success rate (0.0-1.0)
    - Load penalty: `1.0 - (mailbox_depth / capacity)`
  - **Step 2: Score all proposals** (weighted sum formula from chat_experience.md)
    - Formula:

      ```python
      score = (10.0 × confidence) + (8.0 × latency_norm) +
              (-5.0 × cost_norm) + (3.0 × parallelism_norm) +
              (2.0 × track_record) + (-4.0 × load_penalty)
      ```

    - Typical range: -10 to +25
    - Example: Expert agent with low load = ~20.0
  - **Step 3: Rank by score** (descending, highest = best)
    - Sort proposals by score
    - Select top N agents (N = 1 for single task, N > 1 for parallel)
  - **Step 4: Tie-breaking** (if multiple agents have same max score)
    - 60% prefer_resident: Agent already in session (context cached)
    - 20% prefer_fast: Lowest estimated latency
    - 10% prefer_cheap: Lowest cost
    - 10% random: For exploration (prevent local optima)
  - **Step 5: Send TaskAssignment** to winner
    - Create `TaskAssignment` message:

      ```python
      TaskAssignment:
        - task_id: str
        - agent_id: str (winner)
        - task_announcement: TaskAnnouncement (full context)
        - deadline_ms: int (execution budget)
        - priority: int (INTERACTIVE = 2)
      ```

    - Send to winner's mailbox
    - Log: Full score breakdown for explainability
  - **Deterministic**: No randomness except in tie-breaking 10% case

**Acceptance Criteria**:

- ✅ All factors normalized correctly
- ✅ Weighted scoring formula produces expected ranges
- ✅ Highest-scoring agent selected
- ✅ Tie-breaking works deterministically
- ✅ Task assignment sent to winner
- ✅ Phase 2 latency <5ms P95

**References**:

- `docs/whiteboard/chat_experience.md` - Phase 2 Selection detailed flow
- ADR-0006b - Multi-Criteria Decision Making (MADM)
- Deterministic selection requirements

---

#### **Issue 6.1.4: Implement Phase 3 - Execution (Parallel DAG with Barriers)**

**Context**:
After agent selection, Phase 3 coordinates task execution. For single-step tasks, agent executes directly. For multi-step tasks (from Planner), DAG Executor runs parallel waves with barriers. Based on ADR-0006c.

**Tasks**:

- Implement `_phase3_execution(agent_id, task_assignment)` in `Orchestrator`:
  - **Single-Step Execution** (simple tasks)
    - Wait for agent to complete task (async receive response)
    - Timeout: task deadline (default 5s)
    - Handle response:
      - Success: return result to Concierge
      - Failure: retry or compensate (if Saga-enabled)
  - **Multi-Step Execution** (complex tasks with plan)
    - Hand off to `DAGExecutor` (Epic 6.3)
    - DAG Executor parses plan into waves
    - Execute waves with barriers (MapReduce-style)
    - Collect results + handle errors (Saga Pattern)
  - **Performance Budgets** (from chat_experience.md)
    - Simple task: 50-500ms (LLM call)
    - Complex task: Variable (depends on wave count)
    - Max: 120s saga timeout
  - **Error Handling**
    - Critical step fails: Abort + trigger compensation
    - Non-critical fails: Log + continue with partial results
    - Timeout: Force terminate + cleanup
  - Return `TaskResult`:

    ```python
    TaskResult:
      - task_id: str
      - status: str (success, partial, failure)
      - result: dict (output data)
      - latency_ms: int
      - agents_used: list[str]
      - receipts: list[Receipt] (tool call receipts)
      - error: str (if failure)
    ```

**Acceptance Criteria**:

- ✅ Single-step tasks execute correctly
- ✅ Multi-step tasks handed to DAG Executor
- ✅ Error handling prevents cascading failures
- ✅ TaskResult contains complete execution info
- ✅ Receipts generated for all tool calls

**References**:

- `docs/whiteboard/chat_experience.md` - Phase 3 Execution detailed flow
- ADR-0006c - DAG Execution with barriers
- ADR-0008 - Saga Pattern error recovery

---

### **Epic 6.2: Planner Agent (4-Stage Pipeline)**

**Objective**: Decompose complex tasks into executable multi-step plans

#### **Issue 6.2.1: Implement Stage 1 - Sketch (High-Level Plan Generation)**

**Context**:
Planner receives task from Orchestrator (after Phase 2 selection). Stage 1 uses LLM to generate high-level sketch plan. Based on ADR-0007. Budget: ~50ms.

**Tasks**:

- Create `l2_orchestration/planner/planner_agent.py`
- Implement `PlannerAgent` (inherits from `AgentBase`, Tier 2 AI Agent):
  - `async process_message(message)` - Receives TaskAssignment from Orchestrator
    - Extract task requirements: user intent, constraints, budget
    - Query User KG: get preferences, goals for context
  - **Stage 1: Sketch (<50ms)**
    - `async _stage1_sketch(task, user_context)` method:
      - Build LLM prompt:

        ```
        System: You are a task planner. Break down user requests into executable steps.

        User Intent: {task.user_input}
        User Context: {user_preferences}, {active_goals}
        Available Tools: {tool_registry_summary}

        Generate a high-level plan with 3-5 steps. Each step should be:
        - Actionable (can be executed by an agent)
        - Specific (clear what to do)
        - Ordered (respect dependencies)

        Output format: [step_1, step_2, step_3, ...]
        ```

      - Call Groq LLM (temperature=0.3 for consistency)
      - Parse LLM output into structured steps:

        ```python
        SketchStep:
          - step_id: str
          - description: str (high-level action)
          - dependencies: list[str] (step_ids this depends on)
          - estimated_parallel: bool (can run in parallel with siblings)
        ```

      - Validate sketch:
        - No circular dependencies (basic DAG check)
        - Step count reasonable (3-15 steps)
        - All steps have clear actions
      - Return `SketchPlan` object
  - Add observability: log sketch with LLM reasoning

**Acceptance Criteria**:

- ✅ LLM generates reasonable step sequences
- ✅ Steps are actionable and specific
- ✅ Dependencies identified correctly
- ✅ Parallel opportunities detected
- ✅ Stage 1 latency <50ms P95

**References**:

- `docs/whiteboard/chat_experience.md` - Planner 4-stage pipeline, Stage 1 Sketch
- ADR-0007 - Planner architecture
- Phi-3-medium (or Groq equivalent) for planning

---

#### **Issue 6.2.2: Implement Stage 2 - Expand (Deterministic Tool Resolution)**

**Context**:
Stage 2 takes sketch steps and expands with concrete executors (agents + tools). This is deterministic (no LLM), just registry lookups. Budget: ~1ms.

**Tasks**:

- Implement `_stage2_expand(sketch_plan, task_envelope)` in `PlannerAgent`:
  - **For each sketch step**:
    - Extract action keywords: "search", "book", "query", "calculate", etc.
    - Lookup Tool Registry: which tools match this action?
      - Example: "search restaurants" → `web_search` tool
      - Example: "query health records" → `query_k0_health` tool
    - Lookup Agent Registry: which agent type can use this tool?
      - Example: `web_search` → `ResearcherAgent`
      - Example: `query_k0_health` → `HealthcareAgent`
    - Create `ExpandedStep`:

      ```python
      ExpandedStep:
        - step_id: str
        - description: str (from sketch)
        - executor_agent_type: str (healthcare, researcher, etc.)
        - required_tools: list[str] ([web_search], [query_k0_health])
        - input_schema: dict (expected input format)
        - output_schema: dict (expected output format)
        - dependencies: list[str] (inherited from sketch)
        - estimated_latency_ms: int (from tool registry)
        - estimated_cost: float (from tool registry)
      ```

    - Validation:
      - Tool exists in registry
      - Agent type can use tool (capability check)
      - Input/output schemas compatible with dependencies
  - **Parallelism Analysis** (topological sort):
    - Build dependency graph from step dependencies
    - Compute parallel waves: steps with no dependencies = Wave 1, etc.
    - Mark steps that can run concurrently
  - Return `ExpandedPlan` object with waves
  - **Performance**: O(1) registry lookup + O(steps) iteration = <1ms

**Acceptance Criteria**:

- ✅ All sketch steps expanded with executors
- ✅ Tools resolved from registry correctly
- ✅ Agent types assigned correctly
- ✅ Parallel waves computed correctly
- ✅ Stage 2 latency <1ms P95

**References**:

- `docs/whiteboard/chat_experience.md` - Stage 2 Expand detailed
- ADR-0007 - Deterministic expansion
- Tool Registry (Milestone 1, Epic 1.2)

---

#### **Issue 6.2.3: Implement Stage 3 - Validate (Safety & Capability Checks)**

**Context**:
Stage 3 validates expanded plan against safety constraints, privacy bands, resource budgets, and API availability. Uses rules engine + optional LLM arbiter for edge cases. Budget: ~10ms.

**Tasks**:

- Implement `_stage3_validate(expanded_plan, task_envelope)` in `PlannerAgent`:
  - **Validation Checks** (parallel execution):
    1. **Privacy Band Enforcement**
       - Check each step's data access against privacy bands (GREEN/AMBER/RED)
       - GREEN: No restrictions
       - AMBER: Requires user confirmation for sensitive data
       - RED: Blocked (cannot access)
       - Fail if RED data accessed without permission
    2. **Permission Validation**
       - Check user capabilities: can user invoke these tools?
       - Example: booking requires payment capability
       - Fail if missing required capability
    3. **Resource Budget Forecasting**
       - Sum estimated latency: all steps ≤ total budget?
       - Sum estimated cost: all tools ≤ cost budget?
       - Fail if over budget
    4. **API Health Checks**
       - Query circuit breakers: are required APIs available?
       - Example: if web_search API down, plan will fail
       - Warn if API degraded, fail if API unavailable
    5. **Dependency Validation**
       - Check DAG: no circular dependencies, valid topological sort
       - Check schemas: step outputs match next step inputs
       - Fail if dependency chain broken
  - **LLM Arbiter** (for risky/ambiguous cases)
    - When to escalate:
      - AMBER data access (sensitive but allowed)
      - Over budget but close (110% of limit)
      - API degraded (might succeed, might fail)
    - LLM arbiter prompt:

      ```
      Context: Plan validation found potential risk: {risk_description}

      Options:
      1. APPROVE: Risk acceptable, proceed with plan
      2. OPTIMIZE: Modify plan to reduce risk (suggest changes)
      3. REJECT: Risk too high, abort plan

      Decide: [APPROVE/OPTIMIZE/REJECT] with reasoning
      ```

    - Apply arbiter decision
  - Return `ValidatedPlan` with status:
    - `APPROVED`: All checks passed
    - `APPROVED_WITH_WARNINGS`: Passed but has warnings (log warnings)
    - `REJECTED`: Failed validation (return error)

**Acceptance Criteria**:

- ✅ All 5 validation checks work correctly
- ✅ Privacy band enforcement blocks RED data
- ✅ Budget forecasting accurate
- ✅ LLM arbiter handles edge cases reasonably
- ✅ Stage 3 latency <10ms P95 (rules) or <100ms (with LLM arbiter)

**References**:

- `docs/whiteboard/chat_experience.md` - Stage 3 Validate detailed
- ADR-0007 - Validation criteria
- ADR-0037 - Capability-based access control

---

#### **Issue 6.2.4: Implement Stage 4 - Commit (Serialize & Persist to WAL)**

**Context**:
Stage 4 serializes validated plan to JSON (skip FlatBuffers for PoC), persists to Mock K0 WAL for crash recovery, and returns to Orchestrator for execution. Budget: ~5ms.

**Tasks**:

- Implement `_stage4_commit(validated_plan, task_envelope)` in `PlannerAgent`:
  - **Serialize Plan** (JSON format for PoC)
    - Convert `ValidatedPlan` → `CommittedPlan`:

      ```python
      CommittedPlan:
        - plan_id: str (UUID)
        - session_id: str
        - task_id: str
        - steps: list[CommittedStep]
        - waves: list[list[str]] (step_ids grouped by wave)
        - total_estimated_latency_ms: int
        - total_estimated_cost: float
        - validation_status: str
        - trace_id: str
        - committed_at: datetime
      ```

    - Each `CommittedStep`:

      ```python
      CommittedStep:
        - step_id: str
        - description: str
        - executor_agent_type: str
        - required_tools: list[str]
        - dependencies: list[str]
        - fallback: Optional[CommittedStep] (if this step fails, try fallback)
      ```

    - Serialize to JSON
  - **Persist to Mock K0 WAL**
    - POST to Mock K0: `POST /wal/plan_commit`
    - Payload: JSON serialized plan
    - Mock K0 validates structure, returns `{"status": "accepted", "plan_id": "..."}`
    - Retry: 3 attempts if network error
  - **Return CommittedPlan** to Orchestrator
    - Orchestrator Phase 3 will execute via DAG Executor
  - Add observability: log committed plan with wave structure

**Acceptance Criteria**:

- ✅ Plan serialized to valid JSON
- ✅ Mock K0 WAL accepts plan
- ✅ Committed plan returned to Orchestrator
- ✅ Stage 4 latency <5ms P95

**References**:

- `docs/whiteboard/chat_experience.md` - Stage 4 Commit detailed
- ADR-0007 - Plan persistence
- K0 WAL contract

---

### **Epic 6.3: DAG Executor (Parallel Wave Execution)**

**Objective**: Execute committed plans with parallel waves, barriers, and error recovery

#### **Issue 6.3.1: Implement DAG Parser & Wave Computation**

**Context**:
DAG Executor receives committed plan from Orchestrator Phase 3. First task: parse plan into dependency graph and compute parallel execution waves.

**Tasks**:

- Create `l2_orchestration/executor/dag_executor.py`
- Implement `DAGExecutor` class:
  - `async execute_plan(committed_plan)` - Main entry point
  - `_parse_dag(committed_plan)` - Parse into graph
    - Create directed graph: nodes = steps, edges = dependencies
    - Validate: no cycles (topological sort possible)
    - Return: `nx.DiGraph` (use NetworkX library)
  - `_compute_waves(dag)` - Topological sort into parallel waves
    - Wave 1: All nodes with in-degree = 0 (no dependencies)
    - Execute Wave 1 → Mark nodes complete
    - Wave 2: All nodes with in-degree = 0 after Wave 1
    - Repeat until all nodes processed
    - Return: `list[list[step_id]]` (waves of step IDs)
  - **Max Parallelism**: 3 concurrent tasks per wave (semaphore limit)
    - If wave has >3 steps, split into sub-waves of size 3
  - Add visualization: log wave structure

    ```
    Wave 1: [step_1, step_2, step_3] (parallel)
    Barrier
    Wave 2: [step_4, step_5] (parallel, depends on Wave 1)
    Barrier
    Wave 3: [step_6] (depends on Wave 2)
    ```

**Acceptance Criteria**:

- ✅ DAG parsed correctly from committed plan
- ✅ Cycles detected and rejected
- ✅ Waves computed via topological sort
- ✅ Max 3 concurrent tasks enforced
- ✅ Wave structure logged for debugging

**References**:

- `docs/whiteboard/chat_experience.md` - DAG Execution with MapReduce barriers
- ADR-0006c - Parallel execution
- NetworkX library for graph algorithms

---

#### **Issue 6.3.2: Implement Wave Execution with Barriers**

**Context**:
Execute each wave's steps in parallel, wait for all to complete (barrier), then proceed to next wave. Steps may require agent spawning if not already active.

**Tasks**:

- Implement `_execute_waves(waves, committed_plan)` in `DAGExecutor`:
  - **For each wave**:
    - Get steps in wave: `wave_steps = [committed_plan.steps[id] for id in wave]`
    - Execute all steps in parallel:

      ```python
      tasks = [_execute_step(step) for step in wave_steps]
      results = await asyncio.gather(*tasks, return_exceptions=True)
      ```

    - **Barrier**: Wait for all steps to complete before next wave
    - Handle results:
      - Success: Store result, mark step complete
      - Failure: Check if critical (abort) or non-critical (continue)
    - If critical failure: Abort execution, trigger compensation (Saga)
  - **Step Execution**: `_execute_step(step)`
    - Check if executor agent active in Agent Roster
    - If not: Request spawn from Agent Factory (via Orchestrator)
    - Send task to agent's mailbox:

      ```python
      StepTask:
        - step_id: str
        - description: str
        - required_tools: list[str]
        - input_data: dict (from previous steps)
        - timeout_ms: int
      ```

    - Wait for agent response (async)
    - Timeout: 30s default per step
    - Collect tool call receipts from agent
    - Return `StepResult`:

      ```python
      StepResult:
        - step_id: str
        - status: str (success, failure, timeout)
        - output_data: dict
        - agent_id: str (who executed)
        - latency_ms: int
        - receipts: list[Receipt]
        - error: str (if failure)
      ```

  - **Dependency Data Flow**:
    - Step outputs stored in execution context
    - Dependent steps receive outputs as input_data

**Acceptance Criteria**:

- ✅ Waves execute in parallel (up to 3 concurrent)
- ✅ Barriers enforce sequential waves
- ✅ Agent spawning works for missing agents
- ✅ Step results collected correctly
- ✅ Dependency data flows between steps

**References**:

- `docs/whiteboard/chat_experience.md` - Wave execution with barriers
- ADR-0006c - Parallel DAG execution

---

#### **Issue 6.3.3: Integrate Saga Pattern for Error Recovery**

**Context**:
If a critical step fails, DAG Executor triggers Saga Pattern compensation: undo completed steps in reverse order. Based on ADR-0008.

**Tasks**:

- Implement compensation logic in `DAGExecutor`:
  - **Track Completed Steps**: Maintain stack of successful steps
  - **On Critical Failure**:
    - `_trigger_compensation(completed_steps)` method
    - For each step in reverse order (LIFO):
      - Lookup compensation action from step metadata
      - Execute compensation (reverse step)
      - Examples:
        - `book_restaurant` → `cancel_booking`
        - `charge_payment` → `refund_payment`
        - `create_calendar_event` → `delete_calendar_event`
      - Compensation timeout: 3s per step (fail-fast)
      - Log all compensations executed
    - Return `CompensationResult`:

      ```python
      CompensationResult:
        - compensated_steps: list[str]
        - compensation_errors: list[str] (if any failed)
        - total_latency_ms: int
      ```

  - **Compensation Registry** (from Milestone 1 or inline):
    - Map tools to undo actions
    - Example: `{book_restaurant: cancel_booking, charge_payment: refund_payment}`
  - **Update TaskResult**:
    - Include compensation info if triggered
    - User message: "I couldn't complete X because Y failed. I've cancelled A and B."

**Acceptance Criteria**:

- ✅ Compensations execute in reverse order
- ✅ All completed steps compensated
- ✅ Compensation errors logged
- ✅ User receives clear error message

**References**:

- `docs/whiteboard/chat_experience.md` - Saga Pattern integration
- ADR-0008 - Saga Pattern error recovery (all sub-ADRs)
- Garcia-Molina 1987 - Saga Pattern paper

---

## ✅ **Milestone 6 Completion Criteria**

- ✅ Orchestrator 3-phase coordination works (Negotiation → Selection → Execution)
- ✅ Agent bidding with confidence scoring functional
- ✅ Planner 4-stage pipeline produces valid plans
- ✅ DAG Executor parses plans and computes waves
- ✅ Parallel wave execution with barriers functional
- ✅ Saga Pattern compensations work on failures
- ✅ End-to-end orchestration latency meets budgets (<150ms)

**Ready for Milestone 7**: Integration & Testing (End-to-End Flows)

---

## 🎯 **Milestone 7: Integration & End-to-End Testing**

**Goal**: Test complete flows (PATH 1 & PATH 2) and verify all components work together
**Duration**: 4-5 days
**Dependencies**: Milestone 1-6 (All components built)

### **Epic 7.1: PATH 1 - Specialist Query Flow (End-to-End)**

**Objective**: Test query/retrieval path from user question to specialist response

#### **Issue 7.1.1: Integration Test - Healthcare Query**

**Context**:
Verify complete PATH 1 flow: User asks health question → Concierge routes → HealthcareAgent queries User KG/K0 → Returns personalized insight.

**Tasks**:

- Create `tests/integration/test_path1_specialist_query.py`
- Test scenario: "How's my recovery going?"
  - **Step 1: User Input**
    - Simulate user message via chat interface
    - Input: "How's my recovery going?"
  - **Step 2: Intent Router (Layer 1)**
    - Verify: Intent classified as "query" (not meta or planning)
    - Verify: SessionState bootstrap creates session
  - **Step 3: Concierge Routes to Specialist**
    - Verify: Concierge detects specialized knowledge needed (healthcare)
    - Verify: "⏳ Looping in health specialist..." message sent to user
    - Verify: Task envelope created with correct structure
  - **Step 4: Orchestrator (if needed)**
    - If HealthcareAgent not active: spawns via Agent Factory
    - If active: reuses existing agent
    - Verify: Agent added to SessionState.Control.agent_roster
  - **Step 5: HealthcareAgent Executes**
    - Verify: User KG queried (get_health_context)
    - Verify: MCP tool called (query_k0_health)
    - Verify: Mock K0 validates tool request format
    - Verify: Response synthesized with LLM
  - **Step 6: SessionState Updates**
    - Verify: Beliefs section updated with health insights
    - Verify: Scoreboard tracks entities (PT, therapist, knee)
    - Verify: DeltaBus emits delta events
  - **Step 7: Writer Agents Process Deltas**
    - Verify: MemoryWriterAgent receives deltas
    - Verify: Entities extracted (PT session, knee strength)
    - Verify: Batch sent to Mock K0 P02
    - Verify: Mock K0 accepts batch
  - **Step 8: Response to User**
    - Verify: Concierge receives specialist response
    - Verify: Response formatted and sent to user
    - Expected: "Your recovery is on track! You've completed 6/8 PT sessions..."
- Measure end-to-end latency: Target <2s
- Verify: No errors in any component

**Acceptance Criteria**:

- ✅ Complete flow executes without errors
- ✅ User KG and Mock K0 queried correctly
- ✅ SessionState updated with all changes
- ✅ DeltaBus events flow to Writer Agents
- ✅ Mock K0 receives and validates batches
- ✅ End-to-end latency <2s

**References**:

- `docs/whiteboard/chat_experience.md` - Complete PATH 1 flow
- All prior milestones (full system integration)

---

#### **Issue 7.1.2: Integration Test - Finance Query**

**Context**:
Test PATH 1 with different specialist (FinanceAgent) to verify routing flexibility.

**Tasks**:

- Test scenario: "What's my budget this month?"
- Same flow as Issue 7.1.1 but with FinanceAgent
- Verify:
  - Concierge routes to FinanceAgent (not HealthcareAgent)
  - User KG queried for finance preferences
  - query_k0_finance tool called
  - Financial insights synthesized
  - Response: "You've spent $1,200 this month (80% of budget)..."
- Measure latency: Target <2s

**Acceptance Criteria**:

- ✅ FinanceAgent spawned/reused correctly
- ✅ Finance-specific queries work
- ✅ Response accurate for finance domain

**References**:

- `docs/whiteboard/chat_experience.md` - Specialist agent patterns

---

#### **Issue 7.1.3: Integration Test - Meta-Intent Handling**

**Context**:
Test Concierge direct handling of meta-intents (no orchestration needed).

**Tasks**:

- Test scenarios:
  1. **Greeting**: "hey what's up?"
     - Verify: Concierge handles directly
     - No specialist spawned
     - Response: "Hey! I'm here to help. How's your day going?"
     - Latency: <200ms
  2. **Time Query**: "what time is it?"
     - Verify: Direct response (no LLM)
     - Response: "It's 3:45 PM"
     - Latency: <50ms
  3. **Acknowledgement**: "ok thanks"
     - Verify: Brief confirmation
     - Response: "You're welcome! Let me know if you need anything else."
     - Latency: <200ms
- Verify: SessionState updated (turn_count incremented)
- Verify: No orchestration triggered
- Verify: No Writer Agent activity (meta-intents don't generate memories)

**Acceptance Criteria**:

- ✅ All meta-intents handled directly
- ✅ No unnecessary orchestration
- ✅ Latency meets targets (<200ms)
- ✅ Responses match Concierge personality

**References**:

- `docs/whiteboard/chat_experience.md` - Meta-intent triage (11 patterns)

---

### **Epic 7.2: PATH 2 - Planning & Execution Flow (End-to-End)**

**Objective**: Test action/execution path from planning request to task completion

#### **Issue 7.2.1: Integration Test - Simple Planning Task**

**Context**:
Test PATH 2 with single-step plan: "Find Italian restaurants nearby" → ResearcherAgent → web_search tool.

**Tasks**:

- Test scenario: "Find Italian restaurants nearby"
  - **Step 1: User Input**
    - Input: "Find Italian restaurants nearby"
  - **Step 2: Concierge Detects Planning Intent**
    - Verify: Intent classified as "planning"
    - Verify: Routes to Planner (not Specialist)
  - **Step 3: Orchestrator Phase 1 - Negotiation**
    - Verify: Task announcement broadcast
    - Verify: Planner bids with confidence score
    - Budget: <50ms
  - **Step 4: Orchestrator Phase 2 - Selection**
    - Verify: Planner selected (highest score)
    - Verify: TaskAssignment sent to Planner
    - Budget: <5ms
  - **Step 5: Planner 4-Stage Pipeline**
    - Stage 1 (Sketch): LLM generates plan ["Search restaurants", "Filter by cuisine"]
    - Stage 2 (Expand): Assigns ResearcherAgent + web_search tool
    - Stage 3 (Validate): Passes validation (no privacy/budget issues)
    - Stage 4 (Commit): Serialized and sent to Mock K0 WAL
    - Budget: ~60ms total
  - **Step 6: Orchestrator Phase 3 - Execution**
    - Verify: DAG Executor parses plan
    - Verify: 1 wave (2 steps, both can run in parallel)
  - **Step 7: DAG Wave Execution**
    - Wave 1: ResearcherAgent calls web_search tool
    - Verify: Mock MCP server validates request
    - Verify: Tool call receipt generated
    - Mock result: "Found 3 restaurants: Bella Italia, Luigi's, Trattoria"
  - **Step 8: Receipts Collected**
    - Verify: TaskResult contains receipt
    - Verify: Receipt has tool_id, status, timestamp
  - **Step 9: Response to User**
    - Verify: Concierge receives TaskResult
    - Response: "I found 3 Italian restaurants nearby: Bella Italia, Luigi's, Trattoria..."
- Measure end-to-end latency: Target <3s (includes planning)
- Verify: No errors in any component

**Acceptance Criteria**:

- ✅ Complete PATH 2 flow executes
- ✅ Planner generates valid plan
- ✅ DAG Executor parses and executes correctly
- ✅ Tool call receipts generated
- ✅ End-to-end latency <3s

**References**:

- `docs/whiteboard/chat_experience.md` - Complete PATH 2 flow
- Planner 4-stage pipeline (Milestone 6, Epic 6.2)

---

#### **Issue 7.2.2: Integration Test - Multi-Step Planning with Parallel Execution**

**Context**:
Test complex plan with parallel waves: "Book dinner at Italian restaurant for 4 tonight" → Multiple agents + tools.

**Tasks**:

- Test scenario: "Book dinner for 4 at Italian restaurant tonight at 7pm"
  - **Planner generates 4-step plan**:
    1. Search restaurants (ResearcherAgent + web_search)
    2. Check user preferences (FinanceAgent + query_k0_finance) [parallel with step 1]
    3. Filter results by preferences (ResearcherAgent)
    4. Present options to user (ConciergeAgent)
  - **DAG Executor computes 3 waves**:
    - Wave 1: [Step 1, Step 2] (parallel, no dependencies)
    - Wave 2: [Step 3] (depends on Wave 1)
    - Wave 3: [Step 4] (depends on Wave 2)
  - **Verify parallel execution**:
    - Steps 1 & 2 start simultaneously
    - Barrier: Wait for both before Step 3
    - Step 3 uses outputs from Steps 1 & 2
  - **Verify agent spawning**:
    - ResearcherAgent spawned (or reused)
    - FinanceAgent spawned (or reused)
    - Both added to Agent Roster
  - **Verify tool calls**:
    - web_search called (Mock MCP validates)
    - query_k0_finance called (Mock K0 validates)
  - **Verify receipts**:
    - 2 receipts generated (one per tool)
    - All receipts in TaskResult
  - **Response**:
    - "Based on your preference for Italian food and $50 budget, I found: Bella Italia ($15/person)..."
- Measure latency: Target <4s (multi-step)
- Verify: Parallel execution reduces latency vs sequential

**Acceptance Criteria**:

- ✅ Multi-step plan generated correctly
- ✅ Parallel waves execute simultaneously
- ✅ Barriers enforce sequential dependencies
- ✅ Multiple agents spawned/coordinated
- ✅ All tool calls successful with receipts
- ✅ Latency <4s (parallel faster than sequential)

**References**:

- `docs/whiteboard/chat_experience.md` - DAG parallel execution
- ADR-0006c - Parallel waves with barriers

---

#### **Issue 7.2.3: Integration Test - Saga Pattern Error Recovery**

**Context**:
Test error handling: simulate step failure and verify compensations execute in reverse order.

**Tasks**:

- Test scenario: "Book dinner + add to calendar" with simulated failure
  - **Plan (3 steps)**:
    1. Search restaurants (SUCCESS)
    2. Book table (SUCCESS)
    3. Add calendar event (FAILURE - simulated)
  - **Execution**:
    - Wave 1: Step 1 succeeds
    - Wave 2: Step 2 succeeds (booking created)
    - Wave 3: Step 3 fails (calendar API down)
  - **Trigger Compensation**:
    - Detect: Critical step failed
    - Compensation 2: Cancel booking (reverse Step 2)
      - Verify: cancel_booking tool called
      - Verify: Mock MCP validates cancellation
      - Verify: Receipt shows cancellation
    - Compensation 1: No action needed (Step 1 was read-only)
  - **Result**:
    - TaskResult.status = "failure"
    - TaskResult.compensations = [Step 2 cancelled]
    - User message: "I couldn't add this to your calendar because the calendar service is down. The restaurant booking was cancelled to avoid charges."
- Verify: User not charged (compensation worked)
- Verify: All compensations logged
- Measure compensation latency: Target <10s

**Acceptance Criteria**:

- ✅ Failure detected correctly
- ✅ Compensations execute in reverse order
- ✅ Cancelled actions recorded in receipts
- ✅ User receives clear error message
- ✅ System returns to consistent state

**References**:

- `docs/whiteboard/chat_experience.md` - Saga Pattern example
- ADR-0008 - Saga Pattern with compensating transactions
- Milestone 6, Epic 6.3 - DAG compensation logic

---

### **Epic 7.3: Proactive Flow (Temporal Module + SSE Ticks)**

**Objective**: Test proactive notifications from K0 P05 triggers

#### **Issue 7.3.1: Integration Test - Store Prospective Trigger**

**Context**:
Test end-to-end proactive flow: User sets reminder → MemoryWriter detects → Sends to K0 P05.

**Tasks**:

- Test scenario: "Remind me to drink water every 4 hours"
  - **Step 1: User Input**
    - Input: "Remind me to drink water every 4 hours"
  - **Step 2: Concierge Routes to Planner**
    - Verify: Intent classified as planning (action needed)
  - **Step 3: Planner Generates Plan**
    - Sketch: "Create prospective trigger for water reminder"
    - Expand: Assigns MemoryWriterAgent
    - Commit: Plan sent to DAG Executor
  - **Step 4: MemoryWriterAgent Executes**
    - Receives task: "Store prospective trigger"
    - Detects trigger keywords: "remind me", "every 4 hours"
    - Parses parameters:
      - fire_time: Now + 4 hours (8:00pm if now is 4:00pm)
      - recurrence: "4h"
      - message: "Drink water"
      - action: "notify_user"
    - Creates P05 payload
    - Sends to K0 Bridge → Mock K0 P05
    - Verify: Mock K0 accepts trigger
  - **Step 5: Temporal Module Stores Trigger**
    - Verify: Trigger added to temporal_triggers table
    - Verify: fire_time = 8:00pm
    - Verify: recurrence = "4h"
    - Verify: active = True
  - **Response to User**:
    - "I'll remind you to drink water at 8:00pm and every 4 hours after that."
- Verify: Trigger stored correctly
- Verify: No errors in flow

**Acceptance Criteria**:

- ✅ Trigger keywords detected
- ✅ P05 payload formatted correctly
- ✅ Mock K0 validates and accepts
- ✅ Temporal Module stores trigger
- ✅ User receives confirmation

**References**:

- `docs/whiteboard/chat_experience.md` - "Remind me to drink water" example
- Milestone 1, Epic 1.5 - Temporal Module
- Milestone 5, Epic 5.1 - MemoryWriter trigger detection

---

#### **Issue 7.3.2: Integration Test - Proactive Tick Delivery**

**Context**:
Test SSE tick flow: Temporal scheduler fires trigger → SSE tick → ProactiveAgent → User notification.

**Tasks**:

- Test scenario: Trigger fires at scheduled time
  - **Step 1: Advance Clock**
    - Simulate: Current time = 8:00pm (trigger fire_time)
  - **Step 2: Temporal Scheduler Runs**
    - Scheduler loop (every 60s) detects fired trigger
    - Verify: Trigger fire_time ≤ now()
    - Verify: Trigger active = True
  - **Step 3: SSE Tick Sent**
    - Temporal Module sends tick to Mock K0 SSE Server
    - Event: "prospective.trigger.fired"
    - Data: {trigger_id, time, message: "Drink water", action: "notify_user"}
    - Verify: SSE Server broadcasts to connected clients
  - **Step 4: ProactiveAgent Receives Tick**
    - Verify: ProactiveAgent listening on SSE
    - Verify: Tick received
    - Verify: Event parsed correctly
  - **Step 5: ProactiveAgent Handles Tick**
    - Action: notify_user
    - Sends notification via Concierge
    - Message: "💧 Time to drink water! (4/8 daily goal)"
  - **Step 6: User Sees Notification**
    - Verify: Notification appears in chat
    - Verify: SessionState updated (proactive_triggers in Control)
  - **Step 7: Trigger Reschedules** (recurring)
    - Verify: fire_time updated to next occurrence (12:00am + 4h = 4:00am)
    - Verify: Trigger still active
- Verify: End-to-end proactive flow <1s from fire_time

**Acceptance Criteria**:

- ✅ Scheduler detects fired trigger
- ✅ SSE tick sent and received
- ✅ ProactiveAgent handles tick correctly
- ✅ User notification delivered
- ✅ Recurring trigger rescheduled
- ✅ Proactive flow latency <1s

**References**:

- `docs/whiteboard/chat_experience.md` - Complete proactive flow example
- Milestone 4, Epic 4.2 - ProactiveAgent SSE listener
- Milestone 3, Epic 3.3 - Mock K0 SSE Server

---

### **Epic 7.4: SessionState & DeltaBus Integration**

**Objective**: Verify SessionState delta tracking and Writer Agent processing

#### **Issue 7.4.1: Integration Test - Delta Propagation**

**Context**:
Test SessionState updates flow through DeltaBus to Writer Agents.

**Tasks**:

- Test scenario: User conversation generates multiple SessionState changes
  - **Conversation**:
    1. User: "How's my recovery?" (HealthcareAgent responds)
    2. User: "What's my budget?" (FinanceAgent responds)
  - **Track SessionState Changes**:
    - Turn 1:
      - Beliefs: Add health insights
      - Scoreboard: Track entities (PT, knee)
      - Control: Add HealthcareAgent to roster
      - Meta: Increment turn_count
    - Turn 2:
      - Beliefs: Add finance insights
      - Scoreboard: Track entities (budget, expenses)
      - Control: Add FinanceAgent to roster
      - Meta: Increment turn_count
  - **Verify DeltaBus Events**:
    - Event 1: session.delta (Beliefs changed)
    - Event 2: session.delta (Scoreboard changed)
    - Event 3: session.delta (Control changed)
    - Event 4: session.delta (Meta changed)
    - Total: 8 events (4 per turn)
  - **Verify Writer Agent Processing**:
    - MemoryWriterAgent subscribes to all events
    - Entities extracted: PT, knee, budget, expenses
    - Batches sent to Mock K0 P02 (2 batches, one per turn)
    - Mock K0 validates and accepts both
  - **Verify Batching**:
    - First turn: 4 deltas batched together (250ms window)
    - Second turn: 4 deltas batched separately
    - Not sent individually (bandwidth optimization)
- Measure: Delta-to-batch latency <300ms

**Acceptance Criteria**:

- ✅ All SessionState changes emit deltas
- ✅ DeltaBus delivers all events to subscribers
- ✅ Writer Agents process all deltas
- ✅ Batching reduces K0 Bridge traffic
- ✅ Mock K0 validates all batches

**References**:

- `docs/whiteboard/chat_experience.md` - SessionState → DeltaBus → Writer Agents
- Milestone 2, Epic 2.1-2.2 - SessionState & DeltaBus
- Milestone 5, Epic 5.1 - MemoryWriterAgent

---

## ✅ **Milestone 7 Completion Criteria**

- ✅ PATH 1 (Specialist Query) end-to-end tests pass
- ✅ PATH 2 (Planning/Execution) end-to-end tests pass
- ✅ Proactive flow (triggers + SSE ticks) works
- ✅ SessionState delta propagation verified
- ✅ All components integrate without errors
- ✅ Performance meets budgets (latency, throughput)
- ✅ Error recovery (Saga) tested and working

**Ready for Milestone 8**: Chat Interface (CLI with Real-Time Updates)

---

## 🎯 **Milestone 8: Chat Interface & Final Demo**

**Goal**: Build interactive CLI with real-time updates and create final demo
**Duration**: 3-4 days
**Dependencies**: Milestone 1-7 (Complete working system)

### **Epic 8.1: CLI Chat Interface**

**Objective**: Build user-friendly command-line chat interface with live updates

#### **Issue 8.1.1: Implement Basic CLI Chat Loop**

**Context**:
Create interactive CLI that accepts user input, sends to K1 system, and displays responses.

**Tasks**:

- Create `poc/chat_experience_poc/cli/chat_interface.py`
- Implement `ChatInterface` class:
  - `start()` - Main loop
    - Display welcome message with system info
    - Prompt: `You:` for user input
    - Send input to Concierge via API (or direct function call)
    - Display response: `Assistant: <response>`
    - Repeat until user types "exit" or "quit"
  - `send_message(user_input)` - Send to K1
    - Create session if first message
    - Call Concierge.process_message()
    - Wait for response (async)
    - Return response text
  - `display_response(response)` - Format output
    - Wrap text at 80 characters
    - Add timestamp
    - Color-code by type (info: blue, error: red, notification: yellow)
- Add command support:
  - `/help` - Show available commands
  - `/status` - Show session stats (turn count, active agents)
  - `/agents` - List active agents with lifecycle state
  - `/history` - Show last 5 messages
  - `/clear` - Clear screen
  - `/exit` - Quit
- Use `prompt_toolkit` for better CLI experience (autocomplete, history)

**Acceptance Criteria**:

- ✅ CLI accepts input and displays responses
- ✅ Multi-turn conversation works
- ✅ Commands work correctly
- ✅ Clean, readable output format
- ✅ No crashes on malformed input

**References**:

- `docs/whiteboard/chat_experience.md` - User interface requirements
- `prompt_toolkit` docs for CLI features

---

#### **Issue 8.1.2: Implement Real-Time Status Updates**

**Context**:
Show live updates during processing: agent spawning, tool calls, orchestration phases, to give users transparency into system operation.

**Tasks**:

- Add status update mechanism to CLI:
  - Subscribe to DeltaBus for key events:
    - `agent.spawned` → Display: "🤖 Spawning HealthcareAgent..."
    - `agent.state_changed` → Display: "⚡ HealthcareAgent: WARMING → ACTIVE"
    - `orchestrator.phase` → Display: "🔄 Orchestrator: Phase 1 (Negotiation)..."
    - `tool.called` → Display: "🔧 Calling web_search..."
    - `tool.completed` → Display: "✅ web_search completed (250ms)"
    - `planner.stage` → Display: "📋 Planner: Stage 2 (Expand)..."
  - Display updates in real-time (non-blocking)
    - Use separate thread/async task for updates
    - Don't block user input
  - Format with icons and colors:
    - 🤖 Agent spawning (yellow)
    - ⚡ State change (blue)
    - 🔄 Orchestration (cyan)
    - 🔧 Tool call (magenta)
    - ✅ Success (green)
    - ❌ Error (red)
    - 💧 Proactive notification (blue)
  - Add verbosity flag: `--verbose` or `--quiet`
    - Verbose: Show all updates
    - Normal: Show agent/tool updates only
    - Quiet: Show responses only
- Example output:

  ```
  You: How's my recovery?

  ⏳ Looping in health specialist to give you better insights...
  🤖 Spawning HealthcareAgent... (30s)
  ⚡ HealthcareAgent: WARMING → ACTIVE
  🔧 Calling query_k0_health... (150ms)
  ✅ query_k0_health completed

  Assistant: Your recovery is on track! You've completed 6/8 PT sessions.
             Knee strength improved 40%. Next PT: Nov 12 at 2pm. 💪
  ```

**Acceptance Criteria**:

- ✅ Real-time updates appear during processing
- ✅ Updates don't block user input
- ✅ Icons and colors make output clear
- ✅ Verbosity levels work correctly
- ✅ Updates provide transparency without overwhelming

**References**:

- `docs/whiteboard/chat_experience.md` - "Looping in specialist" transparency
- DeltaBus events (Milestone 2, Epic 2.2)

---

#### **Issue 8.1.3: Implement Agent Lifecycle Visualization**

**Context**:
Show agent pool and lifecycle states in real-time so users can see which agents are active, idle, or draining.

**Tasks**:

- Add `/agents` command to CLI:
  - Query Agent Pool and Agent Roster
  - Display table:

    ```
    Active Agents:
    ┌─────────────────┬────────────┬──────────┬────────────┬───────┐
    │ Agent ID        │ Type       │ State    │ Uptime     │ Load  │
    ├─────────────────┼────────────┼──────────┼────────────┼───────┤
    │ concierge-1     │ Concierge  │ ACTIVE   │ 5m 30s     │ 5/50  │
    │ healthcare-42   │ Healthcare │ ACTIVE   │ 2m 15s     │ 2/50  │
    │ finance-17      │ Finance    │ IDLE     │ 1m 05s TTL │ 0/50  │
    └─────────────────┴────────────┴──────────┴────────────┴───────┘

    Pooled Agents: 1 (finance-17)
    Total Agents: 3
    ```

  - Color-code states:
    - ACTIVE: Green
    - IDLE: Yellow
    - DRAINING: Orange
    - TERMINATED: Red
  - Update every 5s in `/agents --watch` mode
- Add lifecycle transition animations:
  - When agent spawns: "🤖 Spawning HealthcareAgent... [████░░░░░░] 40%"
  - Show WARMING progress (4 checks)
  - Celebrate ACTIVE: "✅ HealthcareAgent ready!"

**Acceptance Criteria**:

- ✅ `/agents` command shows all agents
- ✅ Table formatted clearly
- ✅ States color-coded correctly
- ✅ Watch mode updates live
- ✅ Lifecycle transitions visible

**References**:

- `docs/whiteboard/chat_experience.md` - Agent Lifecycle FSM
- Milestone 2, Epic 2.4 - Agent Lifecycle

---

### **Epic 8.2: Demo Scenarios**

**Objective**: Create polished demo scenarios showcasing all features

#### **Issue 8.2.1: Create Demo Script - PATH 1 (Healthcare)**

**Context**:
Prepare scripted demo showing specialist query flow with all features.

**Tasks**:

- Create `demos/demo_path1_healthcare.py`
- Script (automated walkthrough):
  1. Welcome: "Welcome to K1 Intelligence Module Demo - PATH 1: Specialist Query"
  2. User: "hey!"
     - Show: Concierge handles meta-intent directly (<200ms)
  3. User: "How's my recovery going?"
     - Show: "Looping in health specialist..." message
     - Show: Agent spawning (if first time)
     - Show: User KG query + K0 query
     - Show: Personalized response
  4. User: "When is my next PT?"
     - Show: Agent reuse (pooled agent, <1ms)
     - Show: Quick response
  5. User: "What's my knee strength progress?"
     - Show: SessionState tracking entities
     - Show: DeltaBus events flowing
     - Show: MemoryWriter batching to K0
  6. Summary: Show stats (turn count, agents used, total latency, K0 batches sent)
- Add narration between steps explaining what's happening
- Pause for user input: "Press Enter to continue..."
- Run in verbose mode to show all internal updates

**Acceptance Criteria**:

- ✅ Demo runs without errors
- ✅ All features demonstrated
- ✅ Narration clear and helpful
- ✅ Visually appealing output
- ✅ <5 minutes total duration

**References**:

- `docs/whiteboard/chat_experience.md` - PATH 1 flow

---

#### **Issue 8.2.2: Create Demo Script - PATH 2 (Planning)**

**Context**:
Prepare demo showing planning, DAG execution, and parallel waves.

**Tasks**:

- Create `demos/demo_path2_planning.py`
- Script:
  1. Welcome: "K1 Intelligence Module Demo - PATH 2: Planning & Execution"
  2. User: "Find Italian restaurants nearby"
     - Show: Concierge routes to Planner
     - Show: Orchestrator 3-phase (Negotiation → Selection → Execution)
     - Show: Planner 4-stage (Sketch → Expand → Validate → Commit)
     - Show: DAG with 2 steps in 1 wave (parallel)
     - Show: Tool calls with receipts
  3. User: "Book dinner for 4 at Italian restaurant tonight"
     - Show: Multi-step plan (4 steps, 3 waves)
     - Show: Parallel execution (Wave 1 with 2 concurrent steps)
     - Show: Barriers between waves
     - Show: Multiple agents spawned/coordinated
  4. User: "Book dinner and add to calendar" (simulate failure)
     - Show: Step 3 fails (calendar API down)
     - Show: Saga compensation triggers
     - Show: Booking cancelled (reverse order)
     - Show: User error message with transparency
  5. Summary: Performance stats, parallel speedup, receipts generated
- Highlight key concepts with ASCII art diagrams (waves, barriers, compensation)

**Acceptance Criteria**:

- ✅ All PATH 2 features demonstrated
- ✅ Parallel execution visible
- ✅ Saga compensation shown
- ✅ ASCII diagrams helpful
- ✅ <7 minutes total duration

**References**:

- `docs/whiteboard/chat_experience.md` - PATH 2 flow
- DAG Executor (Milestone 6, Epic 6.3)

---

#### **Issue 8.2.3: Create Demo Script - Proactive Flow**

**Context**:
Demonstrate proactive notifications from temporal triggers.

**Tasks**:

- Create `demos/demo_proactive_flow.py`
- Script:
  1. Welcome: "K1 Intelligence Module Demo - Proactive Notifications"
  2. User: "Remind me to drink water every 4 hours"
     - Show: Trigger detected by MemoryWriter
     - Show: P05 payload sent to K0
     - Show: Temporal Module stores trigger
     - Confirmation: "I'll remind you at 8:00pm and every 4 hours"
  3. Simulate time advance: "⏩ Fast-forwarding to 8:00pm..."
  4. Show: Temporal scheduler fires trigger
     - Show: SSE tick sent
     - Show: ProactiveAgent receives tick
     - Notification: "💧 Time to drink water! (4/8 daily goal)"
  5. Show: Trigger reschedules (next fire: 12:00am)
  6. User: "ok done"
     - Concierge: "Great! Keep it up! 💪"
  7. Summary: Proactive system = always-on assistance
- Highlight: System remembers and acts without user asking

**Acceptance Criteria**:

- ✅ Proactive flow demonstrated end-to-end
- ✅ Trigger creation and firing shown
- ✅ SSE tick delivery visible
- ✅ User sees value of proactive features
- ✅ <4 minutes total duration

**References**:

- `docs/whiteboard/chat_experience.md` - Proactive flow example
- Temporal Module (Milestone 1, Epic 1.5)

---

### **Epic 8.3: Final Documentation & Handoff**

**Objective**: Create comprehensive documentation for PoC handoff

#### **Issue 8.3.1: Write PoC Final Report**

**Context**:
Document what was built, what works, performance results, and next steps.

**Tasks**:

- Create `docs/poc_final_report.md` with sections:
  1. **Executive Summary**
     - What we built: Complete K1 chat experience architecture
     - Key achievements: All 8 milestones completed
     - Performance: Latency budgets met, throughput acceptable
  2. **Architecture Overview**
     - 5 layers implemented (Layer 1-5)
     - 58 agents (4 AI + 54 pure actors - 3 core + 3 specialists + 3 writers in PoC)
     - 2 interaction paths (Specialist Query + Planning/Execution)
     - Proactive flow with temporal triggers
  3. **Components Built** (reference milestones)
     - Foundation: Groq API, Tool Registry, Prompt Registry, User KG, Temporal Module
     - Runtime: SessionState, DeltaBus, Mailbox, Lifecycle FSM
     - Infrastructure: Agent Factory, K0 Bridge, Mock K0/MCP
     - Agents: Concierge, ProactiveAgent, 3 Specialists, 3 Writers
     - Orchestration: Orchestrator (3-phase), Planner (4-stage), DAG Executor
  4. **Performance Results**
     - PATH 1 latency: <2s (target: <2s) ✅
     - PATH 2 latency: <4s (target: <5s) ✅
     - Meta-intent: <200ms (target: <200ms) ✅
     - Proactive tick: <1s (target: <1s) ✅
     - Agent pooling hit rate: >70% ✅
  5. **Demo Videos/Screenshots**
     - Link to recorded demos
     - Screenshots of CLI with real-time updates
  6. **Lessons Learned**
     - What worked well
     - What was challenging
     - Design decisions and tradeoffs
  7. **Next Steps for Production**
     - Replace mock K0 with real K0 connection
     - Replace mock MCP with real MCP servers
     - Add FlatBuffers serialization (JSON → FlatBuffers)
     - Scale to full 58 agents
     - Production observability (Prometheus, Grafana)
     - Load testing and optimization
  8. **References**
     - Link to all ADRs used
     - Link to chat_experience.md
     - Link to plan document
- Format: Professional markdown with diagrams
- Length: 10-15 pages

**Acceptance Criteria**:

- ✅ Report covers all sections
- ✅ Performance data included
- ✅ Clear next steps
- ✅ Professional quality
- ✅ Reviewed and approved

**References**:

- All milestones and issues
- `docs/whiteboard/chat_experience.md`

---

#### **Issue 8.3.2: Create Developer Onboarding Guide**

**Context**:
Help future developers understand and extend the PoC codebase.

**Tasks**:

- Create `docs/developer_onboarding.md`:
  1. **Getting Started**
     - Clone repo, install dependencies
     - Set up Groq API key
     - Run tests: `pytest tests/`
     - Start CLI: `python -m poc.chat_experience_poc.cli.chat_interface`
  2. **Architecture Tour**
     - Diagram showing all components
     - Walk through each layer with code pointers
     - Key files to understand first
  3. **Adding New Agents**
     - Step-by-step guide using Agent Factory
     - System prompt template
     - Tool registry entry
     - Example: Create "GardenAgent"
  4. **Adding New Tools**
     - Tool registry schema
     - Mock MCP endpoint creation
     - Integration with agents
     - Example: Add "weather_forecast" tool
  5. **Extending Planner**
     - How to add new planning patterns
     - Validation rules customization
     - Example: Add "budget-aware" validation
  6. **Debugging Tips**
     - Enable verbose logging
     - DeltaBus event inspection
     - Agent lifecycle visualization
     - Common issues and solutions
  7. **Testing Patterns**
     - Unit tests vs integration tests
     - Mocking strategies
     - Performance testing
  8. **Code Style**
     - Follow K1 conventions
     - Copilot instructions reference
- Include code snippets and examples
- Length: 8-10 pages

**Acceptance Criteria**:

- ✅ Guide enables new developer to contribute
- ✅ Examples clear and working
- ✅ Covers common tasks
- ✅ References to relevant code
- ✅ Tested with fresh developer

**References**:

- `.github/copilot-instructions.md`
- All milestone implementations

---

## ✅ **Milestone 8 Completion Criteria**

- ✅ CLI chat interface working with real-time updates
- ✅ Agent lifecycle visible in UI
- ✅ 3 demo scripts created and tested
- ✅ Final report written
- ✅ Developer onboarding guide created
- ✅ All documentation reviewed
- ✅ PoC ready for handoff/production planning

---

## 🎉 **Project Completion**

**Total Milestones**: 8
**Total Epics**: 24
**Total Issues**: 100+
**Estimated Duration**: 30-35 days
**Key Deliverables**:

1. ✅ Complete K1 chat experience system (all layers)
2. ✅ 2 interaction paths (Specialist Query + Planning/Execution)
3. ✅ Proactive flow with temporal triggers
4. ✅ Mock K0/MCP validation (format checking only)
5. ✅ Interactive CLI with real-time updates
6. ✅ 3 polished demos
7. ✅ Comprehensive documentation
8. ✅ Production readiness plan

**Performance Achieved**:

- PATH 1: <2s end-to-end
- PATH 2: <4s end-to-end
- Meta-intents: <200ms
- Proactive: <1s tick-to-notification
- Agent pooling: >70% hit rate

**Ready for**: Production planning and full K0 integration

---
