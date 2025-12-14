# Issue 6.5.2.2: Dynamic Specialist Agent Spawning

## User Story

As the Orchestrator in Phase 3 execution,
I need to dynamically spawn specialized agents on-demand,
So that I can handle any type of task (ticket booking, flight search, medical consultation, etc.) without pre-provisioning all agent types.

**Key Workflow**:

```
User: "book a restaurant ticket"
  ↓
Concierge: route as PLANNING intent
  ↓
Orchestrator Phase 1: TaskAnnouncement("booking_service")
  ↓
Agents bid (healthcare declines, finance declines)
  ↓
Orchestrator Phase 2: No agents available → select "specialist_factory"
  ↓
Orchestrator Phase 3: [**THIS ISSUE**]
  ├─ Check Agent Roster: TicketBookingAgent not ACTIVE
  ├─ Check Prompt Registry: TicketBookingAgent prompt not found
  ├─ Generate prompt: "You are a restaurant ticket booking specialist..."
  ├─ Resolve tools: [web_search, parse_html, api_call, format_booking]
  ├─ Spawn agent: TicketBookingAgent(prompt, tools)
  ├─ Send TaskAssignment
  └─ Collect result
  ↓
Planner: [if multi-step, decompose into DAG]
  ↓
Return result to user
```

## Acceptance Criteria

- [x] **Criteria 1**: Orchestrator Phase 3 can generate prompts for new agent types
- [x] **Criteria 2**: Prompt generation is cached in Prompt Registry (no duplicate generation)
- [x] **Criteria 3**: Tool Registry supports agent_type → tools mapping
- [x] **Criteria 4**: Orchestrator Phase 3 resolves tools before spawning
- [x] **Criteria 5**: Integration tests validate end-to-end dynamic spawning for 3+ agent types
- [x] **Criteria 6**: Spawned agents can execute tasks and return results
- [x] **Criteria 7**: Agent lifecycle state tracked (WARMING → ACTIVE → IDLE → TERMINATED)
- [x] **Criteria 8**: Agents reused if already ACTIVE within 5-minute TTL

## Architecture Context

### Current State (Before This Issue)

**What's Done**:

- ✅ Orchestrator Phase 1 (TaskAnnouncement & bidding)
- ✅ Orchestrator Phase 2 (MADM scoring & selection)
- ✅ Orchestrator Phase 3 (stubbed - no agent spawning yet)
- ✅ Planner (full 4-stage pipeline)
- ✅ Prompt Registry (loads/stores prompts, supports add/save)
- ✅ Tool Registry (stores tool definitions, supports validation)

**What's Missing**:

- ❌ `Orchestrator._generate_agent_prompt()` (dynamic prompt generation)
- ❌ `Orchestrator._resolve_agent_tools()` (tool resolution by agent type)
- ❌ `Orchestrator._spawn_agent()` (agent instantiation)
- ❌ Agent Factory (Milestone 3, use stub for POC)
- ❌ Agent lifecycle state machine (WARMING → ACTIVE → IDLE → TERMINATED)
- ❌ Agent reuse pool with 5-minute TTL

### Key Components

**Orchestrator Phase 3** (l2_orchestration/orchestrator/orchestrator.py, line ~1000)

```python
# Currently:
result = await self._wait_for_agent_response(agent_id, task_id, ...)

# After Issue 6.5.2.2:
# 1. Check Agent Roster for agent_id
# 2. If not ACTIVE: generate prompt, resolve tools, spawn agent
# 3. Send TaskAssignment
# 4. Wait for response
# 5. Update agent state to IDLE
```

**Prompt Registry** (l5_infrastructure/registries/prompt_registry.py)

- Already has: `add_prompt()`, `save_prompts()`, `get_prompt()`
- Will use: Dynamic prompt generation + caching

**Tool Registry** (l5_infrastructure/registries/tool_registry.py)

- Already has: `get_tools_by_category()`
- Needs: `get_tools_for_agent_type()` method
- Needs: `agent_type_tools` mapping in config

**SessionState** (l4_runtime/session_state/session_state_manager.py)

- Already has: `agent_roster` (dict of active agents)
- Needs: Agent lifecycle state tracking (timestamps, state, TTL)

## Implementation Plan

### Phase 1: Dynamic Prompt Generation (Orchestrator)

**Goal**: Orchestrator can generate specialized prompts on-demand for new agent types.

**Changes to**: `l2_orchestration/orchestrator/orchestrator.py`

**New Method** (lines after `_apply_tie_breaking()`):

```python
async def _generate_agent_prompt(
    self,
    agent_type: str,
    task_context: Dict[str, Any]
) -> PromptTemplate:
    """
    Generate a specialized prompt for a new agent type.

    Args:
        agent_type: e.g., "TicketBookingAgent", "FlightSearchAgent"
        task_context: Task details to inform prompt generation

    Returns:
        PromptTemplate with system_prompt, constraints, tools template

    Raises:
        PromptGenerationError if generation fails
    """
    # Step 1: Check cache (avoid duplicate generation)
    cached_prompt = self.prompt_registry.get_prompt(agent_type)
    if cached_prompt:
        self.logger.debug(f"Using cached prompt for {agent_type}")
        return cached_prompt

    # Step 2: Generate specialized prompt via LLM
    generation_prompt = f"""
    Create a specialized system prompt for an AI agent.

    Agent Type: {agent_type}
    Task Domain: {task_context.get("domain", "general")}
    Task Description: {task_context.get("description", "")}
    Available Tools: {', '.join(task_context.get("tools", []))}

    Requirements:
    - Be specific about the agent's role and expertise
    - Include constraints for the domain
    - Reference available tools
    - Keep temperature=0.7 for creativity, max_tokens=500

    Format as JSON: {{
        "system_prompt": "...",
        "constraints": ["...", "..."],
        "temperature": 0.7
    }}
    """

    response = await self.llm_client.generate(
        prompt=generation_prompt,
        temperature=0.3,  # Low temp for deterministic generation
        max_tokens=600
    )

    # Step 3: Parse LLM response
    try:
        prompt_config = json.loads(response.text)
    except json.JSONDecodeError:
        raise PromptGenerationError(f"Invalid JSON from LLM: {response.text}")

    # Step 4: Create PromptTemplate
    new_prompt = PromptTemplate(
        agent_type=agent_type,
        system_prompt=prompt_config["system_prompt"],
        tool_prompt_template=self._build_tool_prompt_template(
            task_context.get("tools", [])
        ),
        context_prompt_template=DEFAULT_CONTEXT_TEMPLATE,
        constraints=prompt_config.get("constraints", []),
        temperature=prompt_config.get("temperature", 0.7),
        max_tokens=prompt_config.get("max_tokens", 1000),
        safety_rules=[
            "Do not execute unvalidated code",
            "Require user confirmation for irreversible actions"
        ]
    )

    # Step 5: Cache in Prompt Registry (for reuse)
    self.prompt_registry.add_prompt(new_prompt)
    await self._save_prompt_registry()  # Async persist

    self.logger.info(f"Generated and cached prompt for {agent_type}")
    return new_prompt
```

**Integration Point**:

- Called from `_execute_singlestep_task()` before agent spawning
- Only called if agent prompt not in registry
- Result cached for future tasks

---

### Phase 2: Tool Resolution (Tool Registry)

**Goal**: Map agent types to available tools + add resolution method.

**Changes to**: `l5_infrastructure/registries/tool_registry.py`

**Add to ToolRegistry class** (after `get_tools_by_category()` method):

```python
def get_tools_for_agent_type(self, agent_type: str) -> List[ToolDefinition]:
    """
    Get all tools available for a specific agent type.

    Args:
        agent_type: e.g., "TicketBookingAgent"

    Returns:
        List of ToolDefinition objects available for this agent
    """
    # Step 1: Lookup agent_type in mapping
    agent_type_lower = agent_type.lower()

    # Pre-built agent_type → tools mapping
    agent_tool_mapping = {
        "ticketbookingagent": ["web_search", "parse_html", "api_call", "format_booking"],
        "flightsearchagent": ["web_search", "api_call", "compare_results", "format_itinerary"],
        "healthcareagent": ["medical_db_query", "symptom_checker", "referral_generator"],
        "financialanalyst": ["stock_api", "financial_calc", "report_generator"],
        "researcharticleagent": ["web_search", "pdf_parser", "citation_formatter"],
        # ... more agents
    }

    # Step 2: Get tool names for this agent
    tool_names = agent_tool_mapping.get(agent_type_lower, [])

    if not tool_names:
        self.logger.warning(f"No tools configured for agent type: {agent_type}")
        # Fallback: return generic tools
        tool_names = ["web_search", "api_call"]  # Basic fallback

    # Step 3: Resolve tool names to ToolDefinition objects
    tools = []
    for tool_name in tool_names:
        tool = self.tools.get(tool_name)
        if tool:
            tools.append(tool)
        else:
            self.logger.warning(f"Tool '{tool_name}' not found in registry")

    return tools
```

**Changes to config file** (`config/tool_registry_config.json`):

Add section:

```json
{
  "agent_type_tools": {
    "TicketBookingAgent": ["web_search", "parse_html", "api_call", "format_booking"],
    "FlightSearchAgent": ["web_search", "api_call", "compare_results"],
    "HealthcareAgent": ["medical_db_query", "symptom_checker"],
    "FinancialAnalyst": ["stock_api", "financial_calc", "report_generator"]
  }
}
```

**Integration Point**:

- Called from `_execute_singlestep_task()` before agent spawning
- Provides list of tools to pass to agent constructor

---

### Phase 3: Agent Spawning (Orchestrator)

**Goal**: Orchestrator can spawn agents dynamically with generated prompts + resolved tools.

**Changes to**: `l2_orchestration/orchestrator/orchestrator.py`

**New Method** (after `_generate_agent_prompt()`):

```python
async def _spawn_agent(
    self,
    agent_type: str,
    prompt: PromptTemplate,
    tools: List[ToolDefinition],
    task_context: Dict[str, Any],
    session_id: str,
    trace_id: str
) -> str:
    """
    Spawn a new specialist agent with generated prompt and tools.

    Args:
        agent_type: Agent type identifier
        prompt: PromptTemplate with system prompt and constraints
        tools: List of available tools
        task_context: Task details for agent initialization
        session_id: Session identifier
        trace_id: Trace ID for observability

    Returns:
        agent_id for newly spawned agent

    Raises:
        AgentSpawningError if spawn fails
    """
    agent_id = f"{agent_type}_{uuid.uuid4().hex[:8]}"

    # Step 1: Create agent initialization envelope
    agent_init_request = AgentSpawnRequest(
        agent_id=agent_id,
        agent_type=agent_type,
        system_prompt=prompt.system_prompt,
        available_tools=[t.to_dict() for t in tools],
        task_context=task_context,
        session_id=session_id,
        trace_id=trace_id,
        timestamp_ms=int(time.time() * 1000)
    )

    # Step 2: Spawn agent (stub for POC, full implementation in Milestone 3)
    # For POC: Use AgentFactoryStub to create placeholder agent
    agent = await self.agent_factory.spawn_agent(
        agent_init_request
    )

    # Step 3: Track agent in roster with lifecycle state
    self.session_state.control.agent_roster[agent_id] = AgentRecord(
        agent_id=agent_id,
        agent_type=agent_type,
        state=AgentState.WARMING,  # Initial state
        spawned_at_ms=int(time.time() * 1000),
        last_active_ms=int(time.time() * 1000),
        idle_timeout_ms=300000,  # 5 minutes
        assigned_tasks=0,
        completed_tasks=0
    )

    self.logger.info(
        f"Spawned agent {agent_id} (type={agent_type}) "
        f"with {len(tools)} tools",
        extra={"trace_id": trace_id}
    )

    return agent_id
```

**Update `_execute_singlestep_task()` method** (lines ~1029):

```python
async def _execute_singlestep_task(
    self,
    agent_id: str,
    task_assignment: TaskAssignment,
    task_start_time_ms: int
) -> TaskResult:
    """Enhanced to spawn agents dynamically"""

    agent_state = self.session_state.control.agent_roster.get(agent_id)

    # Case 1: Agent already ACTIVE (reuse)
    if agent_state and agent_state.state == AgentState.ACTIVE:
        self.logger.debug(f"Reusing active agent {agent_id}")

    # Case 2: Agent exists but IDLE (transition to WARMING for reuse)
    elif agent_state and agent_state.state == AgentState.IDLE:
        ttl_expired = (
            int(time.time() * 1000) - agent_state.last_active_ms
            > agent_state.idle_timeout_ms
        )
        if not ttl_expired:
            self.logger.debug(f"Reusing idle agent {agent_id} (within TTL)")
            agent_state.state = AgentState.WARMING
        else:
            self.logger.debug(f"Agent {agent_id} TTL expired, spawning new")
            # [Fall through to dynamic spawning below]

    # Case 3: Agent doesn't exist (dynamic spawning - **NEW**)
    else:
        # Extract agent type from task_assignment
        agent_type = self._infer_agent_type(task_assignment)

        # Step A: Generate prompt if not in registry
        prompt = await self._generate_agent_prompt(
            agent_type=agent_type,
            task_context={"description": task_assignment.description}
        )

        # Step B: Resolve tools for this agent type
        tools = self.tool_registry.get_tools_for_agent_type(agent_type)

        # Step C: Spawn agent
        agent_id = await self._spawn_agent(
            agent_type=agent_type,
            prompt=prompt,
            tools=tools,
            task_context={
                "description": task_assignment.description,
                "user_context": task_assignment.user_context
            },
            session_id=task_assignment.session_id,
            trace_id=task_assignment.trace_id
        )

    # Step 4: Send task to agent
    result = await self._wait_for_agent_response(
        agent_id, task_assignment.task_id, timeout_ms=5000
    )

    # Step 5: Update agent state
    agent_state = self.session_state.control.agent_roster[agent_id]
    agent_state.state = AgentState.IDLE
    agent_state.last_active_ms = int(time.time() * 1000)
    agent_state.completed_tasks += 1

    return result
```

**New Helper Method** (to infer agent type from task):

```python
def _infer_agent_type(self, task_assignment: TaskAssignment) -> str:
    """Infer agent type from task description"""
    # Simple heuristic for POC
    description_lower = task_assignment.description.lower()

    type_keywords = {
        "TicketBookingAgent": ["book", "ticket", "reservation", "restaurant"],
        "FlightSearchAgent": ["flight", "travel", "airline", "airport"],
        "HealthcareAgent": ["health", "medical", "doctor", "symptom"],
        "FinancialAnalyst": ["stock", "financial", "invest", "market"],
    }

    for agent_type, keywords in type_keywords.items():
        if any(kw in description_lower for kw in keywords):
            return agent_type

    # Default
    return "GeneralistAgent"
```

---

### Phase 4: Agent Lifecycle State Machine (SessionState)

**Goal**: Track agent lifecycle state and implement 5-minute reuse window.

**Changes to**: `l4_runtime/session_state/session_state_manager.py`

**Add new dataclasses** (before SessionState class):

```python
from enum import Enum

class AgentState(Enum):
    """Agent lifecycle state machine"""
    WARMING = "warming"        # Just spawned, initializing
    ACTIVE = "active"          # Currently executing task
    IDLE = "idle"              # Waiting for next task (reusable)
    DRAINING = "draining"      # Finishing up, no new tasks
    TERMINATED = "terminated"  # No longer available

class AgentRecord:
    """Tracks agent instance lifecycle"""
    agent_id: str
    agent_type: str
    state: AgentState
    spawned_at_ms: int
    last_active_ms: int
    idle_timeout_ms: int        # e.g., 300000 for 5 minutes
    assigned_tasks: int = 0
    completed_tasks: int = 0
    failed_tasks: int = 0

    def is_reusable(self, current_time_ms: int) -> bool:
        """Check if agent is still reusable (not expired)"""
        return (
            self.state == AgentState.IDLE and
            (current_time_ms - self.last_active_ms) <= self.idle_timeout_ms
        )
```

**Update `SessionState.Control`** (in SessionState class):

```python
@dataclass
class Control:
    """..."""
    agent_roster: Dict[str, AgentRecord] = field(default_factory=dict)
    # ... other fields

    def cleanup_expired_agents(self, current_time_ms: int) -> List[str]:
        """Remove agents that have exceeded idle TTL"""
        expired_agents = []
        for agent_id, record in list(self.agent_roster.items()):
            if not record.is_reusable(current_time_ms):
                if record.state == AgentState.IDLE:
                    expired_agents.append(agent_id)
                    del self.agent_roster[agent_id]
        return expired_agents
```

---

### Phase 5: Integration Tests (Comprehensive)

**Goal**: Validate end-to-end dynamic spawning for 3+ agent types.

**File**: `tests/integration/test_dynamic_agent_spawning.py` (new file, ~600 lines)

**Test Suite** (6 tests):

```python
@pytest.mark.integration
class TestDynamicAgentSpawning:

    async def test_spawn_ticket_booking_agent(self):
        """Verify TicketBookingAgent spawning with prompt generation"""
        # Setup
        orchestrator = await self._setup_orchestrator()

        # Execute: Orchestrator Phase 3 with unknown agent type
        task = TaskAssignment(
            task_id="task_001",
            description="Book a table at Mario's for 2 people",
            user_context="New user, no prior bookings"
        )

        # Act
        result = await orchestrator._execute_singlestep_task(
            agent_id="TicketBookingAgent_spawn",
            task_assignment=task,
            task_start_time_ms=time.time_ms()
        )

        # Assert
        assert result.status == "success"
        assert "booking_id" in result.result

        # Verify prompt was generated and cached
        prompt = orchestrator.prompt_registry.get_prompt("TicketBookingAgent")
        assert prompt is not None
        assert "ticket booking" in prompt.system_prompt.lower()

    async def test_dynamic_prompt_generation_caching(self):
        """Verify generated prompts are cached for reuse"""
        # Act: Generate prompt twice
        orchestrator = await self._setup_orchestrator()

        prompt1 = await orchestrator._generate_agent_prompt(
            agent_type="FlightSearchAgent",
            task_context={"domain": "travel"}
        )

        # Simulate LLM call count before second generation
        llm_call_count_before = orchestrator.llm_client.call_count

        prompt2 = await orchestrator._generate_agent_prompt(
            agent_type="FlightSearchAgent",
            task_context={"domain": "travel"}
        )

        # Assert: Second call should use cache
        assert prompt1 == prompt2
        assert orchestrator.llm_client.call_count == llm_call_count_before

    async def test_tool_resolution_by_agent_type(self):
        """Verify tool registry resolves tools for specific agent types"""
        tool_registry = ToolRegistry()

        # Act
        ticket_booking_tools = tool_registry.get_tools_for_agent_type("TicketBookingAgent")
        flight_search_tools = tool_registry.get_tools_for_agent_type("FlightSearchAgent")

        # Assert
        assert len(ticket_booking_tools) >= 3  # At least web_search, parse_html, api_call
        assert len(flight_search_tools) >= 3
        assert "web_search" in [t.name for t in ticket_booking_tools]
        assert "web_search" in [t.name for t in flight_search_tools]

    async def test_agent_reuse_within_ttl(self):
        """Verify agents are reused if IDLE and within 5-minute TTL"""
        orchestrator = await self._setup_orchestrator()

        # Setup: Spawn and use agent (transitions to IDLE)
        task1 = TaskAssignment(task_id="task_1", description="Book ticket")
        result1 = await orchestrator._execute_singlestep_task(
            agent_id="TicketBookingAgent_1",
            task_assignment=task1,
            task_start_time_ms=current_time_ms()
        )

        # Verify agent is now IDLE
        agent_record = orchestrator.session_state.control.agent_roster["TicketBookingAgent_1"]
        assert agent_record.state == AgentState.IDLE

        # Act: Use same agent for second task (within TTL)
        task2 = TaskAssignment(task_id="task_2", description="Book another ticket")

        # Record spawn count before
        spawn_count_before = orchestrator.agent_factory.spawn_call_count

        result2 = await orchestrator._execute_singlestep_task(
            agent_id="TicketBookingAgent_1",
            task_assignment=task2,
            task_start_time_ms=current_time_ms() + 30000  # 30 seconds later
        )

        # Assert: Agent was reused (no new spawn)
        assert orchestrator.agent_factory.spawn_call_count == spawn_count_before
        assert agent_record.completed_tasks == 2

    async def test_agent_respawn_after_ttl_expiry(self):
        """Verify agents are respawned if IDLE and TTL expired"""
        orchestrator = await self._setup_orchestrator()

        # Setup: Spawn agent
        task1 = TaskAssignment(task_id="task_1", description="Book ticket")
        await orchestrator._execute_singlestep_task(
            agent_id="TicketBookingAgent_1",
            task_assignment=task1,
            task_start_time_ms=current_time_ms()
        )

        # Act: Reuse after TTL expires (300+ seconds later)
        task2 = TaskAssignment(task_id="task_2", description="Book another ticket")
        spawn_count_before = orchestrator.agent_factory.spawn_call_count

        result2 = await orchestrator._execute_singlestep_task(
            agent_id="TicketBookingAgent_1",
            task_assignment=task2,
            task_start_time_ms=current_time_ms() + 350000  # 350 seconds later
        )

        # Assert: Agent was respawned (new spawn)
        assert orchestrator.agent_factory.spawn_call_count == spawn_count_before + 1

    async def test_concurrent_agent_spawning(self):
        """Verify multiple agents can be spawned concurrently"""
        orchestrator = await self._setup_orchestrator()

        # Act: Spawn 5 different agent types concurrently
        tasks = [
            TaskAssignment(task_id=f"task_{i}", description=desc)
            for i, desc in [
                (1, "Book restaurant ticket"),
                (2, "Search flights"),
                (3, "Check medical symptoms"),
                (4, "Analyze stock"),
                (5, "Research article")
            ]
        ]

        agent_ids = ["TicketBookingAgent", "FlightSearchAgent", "HealthcareAgent",
                     "FinancialAnalyst", "ResearchArticleAgent"]

        results = await asyncio.gather(*[
            orchestrator._execute_singlestep_task(
                agent_id=agent_ids[i],
                task_assignment=tasks[i],
                task_start_time_ms=current_time_ms()
            )
            for i in range(5)
        ])

        # Assert: All agents spawned and completed tasks
        assert len(results) == 5
        assert all(r.status == "success" for r in results)
        assert len(orchestrator.session_state.control.agent_roster) >= 5
```

---

## Implementation Sequence

### Week 1

- [ ] **Day 1-2**: Implement Phase 1 (Dynamic Prompt Generation)
  - Add `_generate_agent_prompt()` method
  - Add `_build_tool_prompt_template()` helper
  - Test with TicketBookingAgent prompt generation

- [ ] **Day 3**: Implement Phase 2 (Tool Resolution)
  - Add `get_tools_for_agent_type()` method
  - Add agent_type_tools mapping to config
  - Test tool resolution for 3+ agent types

- [ ] **Day 4-5**: Implement Phase 3 (Agent Spawning)
  - Add `_spawn_agent()` method
  - Update `_execute_singlestep_task()`
  - Add `_infer_agent_type()` helper

### Week 2

- [ ] **Day 1-2**: Implement Phase 4 (Lifecycle State Machine)
  - Add AgentState enum and AgentRecord dataclass
  - Update SessionState.Control
  - Implement reuse and TTL logic

- [ ] **Day 3-5**: Implement Phase 5 (Integration Tests)
  - Write 6 integration tests (~100 lines each)
  - All tests passing
  - 0 lint errors

---

## Dependencies & Prerequisites

### Required (Already Exist)

- ✅ Orchestrator Phase 1-2 (TaskAnnouncement, MADM scoring)
- ✅ Prompt Registry (get_prompt, add_prompt, save_prompts)
- ✅ Tool Registry (list tools, validate)
- ✅ Planner (4-stage pipeline)
- ✅ SessionState (agent_roster tracking)

### Optional (For Full Feature)

- ⚠️ Agent Factory (use stub for POC, full implementation in Milestone 3)
- ⚠️ Agent Communication (mailbox, envelopes)
- ⚠️ DAG Executor (for multi-step tasks)

### External Dependencies

- `groq` (AsyncGroq for LLM-based prompt generation)
- `pydantic` (for request validation)

---

## Success Metrics

| Metric | Target | Validation |
|--------|--------|------------|
| **Prompt Generation** | <500ms P95 | Profiling with py-spy |
| **Tool Resolution** | <10ms P95 | Direct timing tests |
| **Agent Spawning** | <200ms P95 | Orchestrator phase timing |
| **Cache Hit Rate** | >85% | Prompt registry metrics |
| **Test Coverage** | 100% (Issue 6.5.2.2 paths) | pytest coverage report |
| **Agent Reuse Rate** | >75% (for recurring tasks) | SessionState metrics |

---

## Risk Mitigation

| Risk | Mitigation |
|------|-----------|
| **LLM Prompt Gen Fails** | Use cached fallback prompt; log error; alert ops |
| **Tool Resolution Missing Tools** | Fallback to generic tools (web_search, api_call) |
| **Agent Spawn Timeout** | Retry with exponential backoff; fall back to existing agent |
| **TTL Cleanup Memory Leak** | Periodic cleanup sweep in SessionState (every 60s) |
| **Circular Dependency** | Agent type naming convention (avoid reserved words) |

---

## Rollback Plan

If issues arise:

1. Disable dynamic spawning: Comment out `_spawn_agent()` call
2. Revert to static agents only (query flow still works)
3. Disable agent reuse: Set idle_timeout_ms=0
4. Scale back to single agent type for testing

---

## Documentation & Notes

- Dynamic prompt generation uses `temperature=0.3` for deterministic results
- Agent reuse TTL is 5 minutes (configurable in config)
- Agent lifecycle: WARMING (init) → ACTIVE (executing) → IDLE (reusable) → TERMINATED
- Tool resolution uses keyword mapping in config (extensible)
- Orchestrator Phase 3 remains single-threaded (serial task execution per agent)
