# 🎯 Concierge PoC - Requirements & Implementation Plan

**Goal:** Prove dual-path conversational architecture with real-time progress streaming.

---

## 📋 Phase 1: PATH 1 (Data Analysis - Background Specialists)

### **Objective**
Prove that ConciergeAgent can maintain conversation continuity while background specialists query K0 and analyze data.

### **User Story**
```
User: "remember we talked about reducing my gerd and you gave
       input to add milk I think it is making me more sick"

Expected Flow:
1. Concierge responds immediately with empathy (<50ms)
2. Nutritionist spawned in background (50-100ms)
3. User sees progress updates (4 milestones)
4. Concierge continues conversation (not blocked)
5. Nutritionist completes analysis (500-1000ms)
6. Concierge presents findings naturally
```

### **Requirements**

#### **1. ConciergeAgent (Conversational Brain)**
- **Must Have:**
  - [ ] Intent classification (QUERY vs ACTION)
  - [ ] Immediate empathetic responses (<50ms)
  - [ ] Specialist spawning decision logic
  - [ ] **Reactive-Proactive Loop:** Generate proactive prompts during background work
  - [ ] Progress event subscription
  - [ ] Result synthesis (LLM-based)
  - [ ] Conversation continuity (multi-turn tracking)
  - [ ] **Future action promises:** "I'll remind you at next doctor visit"

- **Reactive-Proactive Pattern:**
  ```python
  # Pattern: Fill conversation gaps during background work

  # REACTIVE (50ms): Acknowledge user immediately
  await stream_to_user("That's sad to hear. Looping in nutritionist.")

  # SPAWN: Background work (500-1000ms)
  task_id = await spawn_specialist("nutritionist", intent)

  # PROACTIVE (100ms): Fill wait time with meaningful conversation
  proactive_prompt = await generate_proactive_prompt(intent, context)
  # Example: "Until nutritionist gathers data and sees triggers,
  #           why can't you tell me how uneasy it was?"
  await stream_to_user(proactive_prompt)

  # LISTEN: User may respond (turns conversation anxiety into engagement)
  # User: "pain in left side of stomach"

  # REACTIVE (50ms): Acknowledge user response
  await stream_to_user("I'll take a note about milk for next doctor visit.")

  # SYNTHESIS (when ready): Integrate background result
  result = await wait_for_result(task_id)
  synthesis = await synthesize_result(result, context)
  await stream_to_user(synthesis)
  ```

- **Why This Feels Human:**
  - Conversation rhythm maintained (no awkward silence)
  - Proactive prompts reduce user anxiety ("Is it working?")
  - Shows anticipation (thinks ahead: "I'll remind you...")
  - Natural turn-taking (doctor conversation pattern)

- **Data Structures:**
  ```python
  @dataclass
  class Intent:
      type: str          # "QUERY" | "ACTION"
      domain: str        # "health" | "finance" | "social"
      complexity: str    # "simple" | "multi_step"
      confidence: float  # 0.0-1.0
      entities: List[str]

  @dataclass
  class ConversationContext:
      turn_count: int
      recent_history: Deque[Turn]  # Last 10 turns
      active_specialists: Dict[str, str]  # {specialist_type: agent_id}
      pending_results: List[str]  # Awaiting specialist completion
  ```

- **APIs:**
  ```python
  async def classify_intent(message: str) -> Intent
  async def spawn_specialist(specialist_type: str, task: Intent) -> str
  async def stream_to_user(user_id: str, message: str, type: str)
  async def synthesize_response(results: List[AnalysisResult]) -> str
  ```

- **Performance Targets:**
  - Intent classification: <30ms P95
  - Initial response: <50ms P95
  - Final synthesis: <100ms P95

#### **2. NutritionistAgent (Specialist - K0 Analyst)**
- **Must Have:**
  - [ ] K0 P01 (Recall) integration
  - [ ] Correlation analysis (diet, sleep, symptoms)
  - [ ] Progress milestone emission (5 stages)
  - [ ] LLM-based insight generation
  - [ ] Error handling (K0 query failures)

- **Data Structures:**
  ```python
  @dataclass
  class AnalysisResult:
      agent_name: str
      insights: List[Insight]
      correlations: List[Correlation]
      confidence: float
      duration_ms: int

  @dataclass
  class Insight:
      summary: str          # "Late night coffee is trigger"
      evidence: List[str]   # ["3/5 GERD episodes after coffee"]
      confidence: float     # 0.87
      recommendation: str   # "Avoid coffee after 6pm"
  ```

- **Progress Milestones:**
  1. `initializing` (0-10%): "🔍 Starting analysis..."
  2. `querying_k0` (10-40%): "📊 Checking your diet history..."
  3. `analyzing_patterns` (40-80%): "🧠 Analyzing GERD triggers..."
  4. `generating_insights` (80-100%): "💡 Identifying correlations..."
  5. `complete` (100%): "✅ Analysis complete"

- **Performance Targets:**
  - Total analysis time: <1000ms P95
  - K0 queries: <200ms P95 per query
  - Correlation analysis: <300ms

#### **3. Progress Streaming Infrastructure**
- **Must Have:**
  - [ ] Progress event pub/sub (Redis or in-memory)
  - [ ] Progress event data structure
  - [ ] Frontend SSE endpoint
  - [ ] Rate limiting (max 5 updates/sec)
  - [ ] Event aggregation (similar events batched)

- **Data Structures:**
  ```python
  @dataclass
  class ProgressEvent:
      agent_id: str
      agent_name: str       # "Nutritionist" (user-friendly)
      milestone: str        # "querying_k0", "analyzing_patterns"
      message: str          # "📊 Checking your diet history..."
      progress: float       # 0.0-1.0
      eta_ms: Optional[int] # Estimated time remaining
      status: str           # "in_progress" | "complete" | "error"
      timestamp: datetime
      details: Optional[Dict[str, Any]]
  ```

- **APIs:**
  ```python
  async def publish_progress(event: ProgressEvent)
  async def subscribe_progress(filter: Dict[str, str]) -> AsyncIterator[ProgressEvent]
  async def stream_progress_sse(user_id: str) -> StreamingResponse
  ```

#### **4. K0 Integration (Minimal)**
- **Must Have:**
  - [ ] P01 (Recall) mock/stub for testing
  - [ ] P02 (Write) mock for memory capture
  - [ ] Health domain data structure
  - [ ] Query API (tags, time range, limit)

- **Mock Data:**
  ```python
  # Mock K0 memories for GERD example
  memories = [
      Memory(
          timestamp="2024-10-15T20:30:00Z",
          domain="health",
          tags=["diet", "gerd", "milk"],
          content="User tried milk for GERD relief",
          metadata={"episode_id": "gerd_001"}
      ),
      Memory(
          timestamp="2024-10-20T22:00:00Z",
          domain="health",
          tags=["sleep", "coffee"],
          content="User drank coffee at 10pm, poor sleep",
          metadata={"sleep_quality": 3.5}
      ),
      # ... 10-20 mock memories
  ]
  ```

#### **5. Frontend (Simple UI)**
- **Must Have:**
  - [ ] Chat interface (message input + history)
  - [ ] Progress indicators (spinner + progress bar)
  - [ ] SSE connection for real-time updates
  - [ ] Message types: user, assistant, progress_update
  - [ ] Visual cues (emoji, colors)

- **UI Components:**
  ```typescript
  // Message types
  type MessageType = "user" | "assistant" | "progress_update";

  // Progress component
  <ProgressIndicator
    agentName="Nutritionist"
    message="📊 Checking your diet history..."
    progress={0.3}
    status="in_progress"
  />

  // Chat message
  <ChatMessage
    role="assistant"
    content="That's sad to hear. Looping in nutritionist."
    timestamp={Date.now()}
  />
  ```

### **Success Criteria (Phase 1)**
- [ ] User sees Concierge response <50ms after input
- [ ] **Reactive-Proactive Loop:** Concierge generates proactive prompt during background work
- [ ] **Conversational Continuity:** 2-3 conversation turns during 1000ms background work
- [ ] **User Anxiety Reduction:** <5% "Did it freeze?" incidents (qualitative)
- [ ] **Proactive Engagement:** >70% users respond to proactive prompts
- [ ] Progress updates stream in real-time (4 milestones visible)
- [ ] Nutritionist completes analysis <1000ms P95
- [ ] Final response synthesized <100ms
- [ ] End-to-end latency <1200ms P95
- [ ] User never sees "frozen" UI (continuous feedback)
- [ ] **Human-Like Rating:** >4.0/5.0 on "Feels like talking to human" (user study)

---

## 📋 Phase 2: PATH 2 (Action Execution - Planner → Orchestrator → Tool Agents)

### **Objective**
Prove multi-step workflow planning, parallel agent coordination, and MCP tool integration.

### **User Story**
```
User: "You know what, pain is more. I would like to
       schedule an appointment"

Expected Flow:
1. Concierge detects ACTION intent
2. PlannerAgent creates 5-step plan (200-600ms)
3. Orchestrator coordinates 5 tool agents
4. Agents execute in 3 parallel waves
5. Progress shows all agents working simultaneously
6. Total latency <3000ms
7. Appointment booked, user confirmed
```

### **Requirements**

#### **1. PlannerAgent (4-Stage Pipeline)**
- **Must Have:**
  - [ ] Stage 1: Sketch (LLM-based plan generation)
  - [ ] Stage 2: Expand (tool schema lookup)
  - [ ] Stage 3: Validate (rules + safety arbiter)
  - [ ] Stage 4: Commit (serialize to FlowDef)
  - [ ] Tool registry (schemas for MCP tools)
  - [ ] DAG construction (dependencies, waves)

- **Data Structures:**
  ```python
  @dataclass
  class Plan:
      plan_id: str
      steps: List[PlanStep]
      dag: DAG  # Dependency graph
      total_estimated_ms: int

  @dataclass
  class PlanStep:
      step_id: str
      action: str           # "query_k0" | "calendar_check" | "book_appointment"
      tool: str             # Tool name from registry
      dependencies: List[str]  # Step IDs this depends on
      estimated_ms: int

  @dataclass
  class DAG:
      waves: List[List[str]]  # [[step1, step2], [step3], [step4, step5]]
      edges: List[Tuple[str, str]]  # [(src_step, dst_step), ...]
  ```

- **APIs:**
  ```python
  async def sketch_plan(intent: Intent) -> List[str]  # High-level steps
  async def expand_plan(sketch: List[str]) -> List[PlanStep]
  async def validate_plan(plan: Plan) -> ValidationResult
  async def commit_plan(plan: Plan) -> str  # Returns plan_id
  ```

- **Performance Targets:**
  - Sketch: <500ms P95 (LLM call)
  - Expand: <5ms (lookup)
  - Validate: <100ms P95 (rules + optional LLM)
  - Commit: <10ms
  - Total: <600ms P95

#### **2. Orchestrator (3-Phase Coordination)**
- **Must Have:**
  - [ ] Phase 1: Negotiation (broadcast + bidding)
  - [ ] Phase 2: Selection (weighted scoring)
  - [ ] Phase 3: Execution (parallel DAG execution)
  - [ ] Agent registry (available agents + capabilities)
  - [ ] Wave-based execution (barrier synchronization)
  - [ ] Fault tolerance (retry, fallback)

- **Data Structures:**
  ```python
  @dataclass
  class AgentBid:
      agent_id: str
      agent_type: str
      confidence: float     # 0.0-1.0
      estimated_ms: int
      estimated_cost: float
      capabilities: List[str]

  @dataclass
  class ExecutionResult:
      step_id: str
      agent_id: str
      status: str           # "success" | "error"
      result: Any
      duration_ms: int
  ```

- **APIs:**
  ```python
  async def broadcast_task(task: PlanStep) -> List[AgentBid]
  async def select_agent(bids: List[AgentBid]) -> str  # Returns agent_id
  async def execute_dag(dag: DAG, agents: Dict[str, Agent]) -> List[ExecutionResult]
  ```

- **Performance Targets:**
  - Negotiation: <50ms P95
  - Selection: <5ms
  - Execution: <2000ms P95 (depends on tools)
  - Total overhead: <80ms (negotiate + select)

#### **3. Tool Agents (MCP Integration)**

##### **CalendarAgent**
- [ ] MCP tool: `calendar_check`
- [ ] Find free slots (next 7 days)
- [ ] Progress: "📅 Checking your availability..."
- [ ] Latency: <200ms

##### **WebSearchAgent**
- [ ] MCP tool: `web_search`
- [ ] Search doctor availability
- [ ] Progress: "🔍 Checking Dr. Smith's availability..."
- [ ] Latency: <500ms

##### **FormFillerAgent**
- [ ] MCP tool: `form_fill`
- [ ] Pre-fill patient info from K0
- [ ] Progress: "📝 Pre-filling appointment form..."
- [ ] Latency: <150ms

##### **BookingAgent**
- [ ] MCP tool: `booking_api`
- [ ] Book appointment (external API)
- [ ] Progress: "📞 Booking appointment..."
- [ ] Latency: <800ms

- **Common Data Structures:**
  ```python
  @dataclass
  class ToolResult:
      tool_name: str
      status: str           # "success" | "error"
      data: Any
      error_message: Optional[str]
      duration_ms: int
  ```

#### **4. Multi-Agent Progress Streaming**
- **Must Have:**
  - [ ] Parallel progress tracking (5+ agents)
  - [ ] Per-agent progress bars
  - [ ] Completion indicators (✅)
  - [ ] Error indicators (❌)
  - [ ] Wave-based grouping (visual hierarchy)

- **Frontend UI:**
  ```typescript
  // Multi-agent progress
  <MultiAgentProgress>
    <WaveGroup label="Wave 1: Initial Queries">
      <AgentProgress name="HealthcareAgent" progress={1.0} status="complete" />
      <AgentProgress name="CalendarAgent" progress={1.0} status="complete" />
    </WaveGroup>

    <WaveGroup label="Wave 2: External Search">
      <AgentProgress name="WebSearchAgent" progress={0.6} status="in_progress" />
    </WaveGroup>

    <WaveGroup label="Wave 3: Booking">
      <AgentProgress name="FormFillerAgent" progress={0.0} status="pending" />
      <AgentProgress name="BookingAgent" progress={0.0} status="pending" />
    </WaveGroup>
  </MultiAgentProgress>
  ```

#### **5. MCP Tool Registry**
- **Must Have:**
  - [ ] Tool schemas (input/output types)
  - [ ] Capability metadata
  - [ ] Latency hints
  - [ ] Cost hints
  - [ ] Safety band requirements

- **Data Structure:**
  ```python
  @dataclass
  class ToolSchema:
      name: str
      description: str
      input_schema: Dict[str, Any]
      output_schema: Dict[str, Any]
      capabilities: List[str]
      latency_hint_ms: int
      cost_hint_usd: float
      safety_band: str      # "GREEN" | "AMBER" | "RED"

  # Example registry
  tool_registry = {
      "calendar_check": ToolSchema(
          name="calendar_check",
          description="Check user's calendar for free slots",
          input_schema={"user_id": "string", "days": "int"},
          output_schema={"slots": "List[TimeSlot]"},
          capabilities=["calendar_read"],
          latency_hint_ms=200,
          cost_hint_usd=0.0002,
          safety_band="GREEN"
      ),
      # ... other tools
  }
  ```

### **Success Criteria (Phase 2)**
- [ ] PlannerAgent generates 5-step plan <600ms
- [ ] Orchestrator spawns 5 agents <50ms
- [ ] Parallel execution (Wave 1 + Wave 2 + Wave 3)
- [ ] Progress updates show all agents simultaneously
- [ ] End-to-end latency <3000ms P95
- [ ] Appointment booked successfully
- [ ] Saga pattern handles failures (compensation)

---

## 🛠️ Technical Stack

### **Backend**
- **Language:** Python 3.11+
- **Framework:** FastAPI (async support)
- **LLM:** OpenAI GPT-4 or local model
- **Message Bus:** Redis Pub/Sub or asyncio queues
- **State Management:** In-memory (Phase 1), Redis (Phase 2)

### **Frontend**
- **Framework:** React + TypeScript
- **Real-time:** Server-Sent Events (SSE)
- **UI Library:** Tailwind CSS + shadcn/ui
- **State Management:** Zustand or Context API

### **Infrastructure**
- **K0 Mock:** SQLite or JSON files
- **MCP Tools:** Mock implementations (Phase 1), real APIs (Phase 2)
- **Observability:** structlog + OpenTelemetry

---

## 📦 Dependencies

### **Python (backend)**
```toml
[tool.poetry.dependencies]
python = "^3.11"
fastapi = "^0.104.0"
uvicorn = "^0.24.0"
pydantic = "^2.5.0"
openai = "^1.3.0"
redis = "^5.0.1"
structlog = "^23.2.0"
httpx = "^0.25.0"
```

### **TypeScript (frontend)**
```json
{
  "dependencies": {
    "react": "^18.2.0",
    "typescript": "^5.3.0",
    "tailwindcss": "^3.3.0",
    "@radix-ui/react-progress": "^1.0.3",
    "zustand": "^4.4.0"
  }
}
```

---

## 📁 Project Structure

```
poc/conceriege/
├── requirements.md          # This file
├── flow.md                  # Architecture flow diagrams
├── backend/
│   ├── main.py             # FastAPI app
│   ├── agents/
│   │   ├── concierge.py    # ConciergeAgent
│   │   ├── nutritionist.py # NutritionistAgent
│   │   ├── planner.py      # PlannerAgent (Phase 2)
│   │   └── orchestrator.py # Orchestrator (Phase 2)
│   ├── progress/
│   │   ├── events.py       # ProgressEvent data structures
│   │   ├── pubsub.py       # Pub/sub implementation
│   │   └── streaming.py    # SSE endpoint
│   ├── k0/
│   │   ├── client.py       # K0 mock client
│   │   └── mock_data.py    # Mock memories
│   ├── tools/              # Phase 2
│   │   ├── registry.py     # Tool registry
│   │   ├── calendar.py     # CalendarAgent
│   │   ├── websearch.py    # WebSearchAgent
│   │   └── booking.py      # BookingAgent
│   └── models/
│       ├── intent.py       # Intent classification
│       ├── context.py      # Conversation context
│       └── results.py      # Analysis results
├── frontend/
│   ├── src/
│   │   ├── App.tsx
│   │   ├── components/
│   │   │   ├── ChatInterface.tsx
│   │   │   ├── ProgressIndicator.tsx
│   │   │   ├── MultiAgentProgress.tsx  # Phase 2
│   │   │   └── MessageBubble.tsx
│   │   ├── hooks/
│   │   │   ├── useSSE.ts
│   │   │   └── useChat.ts
│   │   └── types/
│   │       └── index.ts
│   └── package.json
└── tests/
    ├── test_concierge.py
    ├── test_nutritionist.py
    ├── test_progress.py
    └── test_orchestrator.py  # Phase 2
```

---

## ⏱️ Implementation Timeline

### **Phase 1: PATH 1 (Week 1-2)**
- **Day 1-2:** Backend scaffolding (FastAPI, data structures)
- **Day 3-4:** ConciergeAgent + intent classification
- **Day 5-6:** NutritionistAgent + K0 mock integration
- **Day 7-8:** Progress streaming (pub/sub + SSE)
- **Day 9-10:** Frontend (chat UI + progress indicators)
- **Day 11-12:** Integration testing + polish
- **Day 13-14:** Demo prep + documentation

### **Phase 2: PATH 2 (Week 3-4)**
- **Day 1-2:** PlannerAgent (4-stage pipeline)
- **Day 3-4:** Orchestrator (3-phase coordination)
- **Day 5-6:** Tool Agents (5 agents + MCP mocks)
- **Day 7-8:** DAG execution + parallel progress
- **Day 9-10:** Frontend (multi-agent progress UI)
- **Day 11-12:** Saga pattern + error handling
- **Day 13-14:** End-to-end testing + demo

---

## 🎯 Success Metrics

### **Performance**
- [ ] PATH 1 end-to-end: <1200ms P95
- [ ] PATH 2 end-to-end: <3000ms P95
- [ ] Progress update latency: <100ms
- [ ] Frontend responsiveness: <16ms frame time

### **User Experience**
- [ ] Zero "frozen" UI moments
- [ ] Continuous feedback during work
- [ ] Natural conversation flow
- [ ] Clear progress indicators
- [ ] Graceful error handling

### **Architecture**
- [ ] Clean separation: PATH 1 vs PATH 2
- [ ] Modular agent design (easy to add new specialists)
- [ ] Scalable progress streaming (supports 10+ parallel agents)
- [ ] MCP tool integration pattern (reusable)

---

## 🚀 Next Steps

1. **Review requirements** with team
2. **Set up project structure** (`poc/conceriege/backend/`, `frontend/`)
3. **Implement Phase 1** (PATH 1: ConciergeAgent + Nutritionist)
4. **Demo Phase 1** (validate architecture)
5. **Implement Phase 2** (PATH 2: Planner + Orchestrator)
6. **Final demo** (end-to-end GERD scenario)
