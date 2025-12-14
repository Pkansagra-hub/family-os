┌─────────────────────────────────────────────────────────────────────┐
│ CONVERSATION PART 1: PATH 1 (Data Analysis)                        │
└─────────────────────────────────────────────────────────────────────┘

User: "remember we talked about reducing my gerd and you gave
       input to add milk I think it is making me more sick"
    ↓
ConciergeAgent: "That's sad to hear. Looping in nutritionist."
    ↓
    ├─ FOREGROUND: Concierge continues talking
    └─ BACKGROUND: Nutritionist (Specialist) spawned
                   • Queries K0 (diet, sleep, patterns)
                   • NO MCP tools
                   • NO external actions
                   • Pure data analysis
    ↓
ConciergeAgent: "Until nutritionist gathers all data..."
User: "pain in left side of stomach"
ConciergeAgent: "Ahh I will take a note..."
    ↓
Nutritionist completes analysis (500-1000ms)
    ↓
ConciergeAgent: "Nutritionist: ...trigger may be late night coffee"

┌─────────────────────────────────────────────────────────────────────┐
│ ✅ PATH 1 COMPLETE: Data analysis done, user informed               │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│ CONVERSATION PART 2: PATH 2 (Action Execution)                     │
└─────────────────────────────────────────────────────────────────────┘

User: "You know what, pain is more. I would like to schedule
       an appointment"
    ↓
┌─────────────────────────────────────────────────────────────────────┐
│ T0: ConciergeAgent (Intent Classification)                         │
│  • Intent: ACTION_REQUEST (not just query)                         │
│  • Type: schedule_appointment                                       │
│  • Complexity: Multi-step (find doctor, check calendar, book)      │
│  • DECISION: Trigger PATH 2 (Planner → Orchestrator)              │
│                                                                      │
│  IMMEDIATE RESPONSE:                                                │
│  "I'll help you schedule that appointment. Let me check your       │
│   calendar and find available slots."                              │
└─────────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│ T0+50ms: PlannerAgent (4-Stage Pipeline - ADR-0007)               │
└─────────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│ STAGE 1: SKETCH (LLM-based, 150-500ms)                            │
│  PlannerAgent generates high-level plan:                           │
│                                                                      │
│  Step 1: Query K0 for medical history (find gastroenterologist)   │
│  Step 2: Check user calendar (find free slots)                     │
│  Step 3: Search web for doctor availability                        │
│  Step 4: Fill appointment form (patient info from K0)              │
│  Step 5: Book appointment (API call)                               │
│  Step 6: Confirm with user                                         │
└─────────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│ STAGE 2: EXPAND (Deterministic, <1ms)                             │
│  Fill tool schemas from registry:                                   │
│                                                                      │
│  Step 1: {tool: "k0_p01_query", domain: "health"}                 │
│  Step 2: {tool: "mcp_calendar_check", user_id: "prince"}          │
│  Step 3: {tool: "mcp_web_search", query: "gastro Dr. Smith"}      │
│  Step 4: {tool: "mcp_form_fill", template: "appointment_form"}    │
│  Step 5: {tool: "mcp_booking_api", endpoint: "/appointments"}     │
└─────────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│ STAGE 3: VALIDATE (Two-Tier)                                       │
│  Tier 1 (Rules, <1ms):                                             │
│    ✅ Structure valid                                               │
│    ✅ No circular dependencies                                      │
│    ✅ Budget OK (5 steps < 10 step limit)                          │
│                                                                      │
│  Tier 2 (Safety Arbiter, 50-100ms):                                │
│    Check: Booking appointment (PII involved, AMBER band)           │
│    ⚠️  Requires safety validation                                  │
│    Safety Arbiter (LLM):                                            │
│      • Check for PII leaks                                          │
│      • Verify consent for booking                                   │
│      • Validate doctor credentials                                  │
│    ✅ APPROVED (user explicitly requested, legitimate use)         │
└─────────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│ STAGE 4: COMMIT (<10ms)                                            │
│  Serialize plan to FlowDef (FlatBuffers)                           │
│  Write to K0 WAL (persistence)                                      │
│  Plan ID: plan_sess_123_004                                        │
└─────────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│ T0+700ms: K1 Orchestrator (3-Phase - ADR-0006)                    │
└─────────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│ PHASE 1: NEGOTIATION (Broadcast + Bidding)                         │
│  Orchestrator broadcasts task to Tool Agents:                       │
│                                                                      │
│  HealthcareAgent (K0 query specialist):                            │
│    • Confidence: 0.95 (has K0 access)                             │
│    • Latency: 100ms                                                 │
│    • Cost: $0.0001                                                 │
│    • Capabilities: ✅ K0 P01 query, medical history access         │
│                                                                      │
│  CalendarAgent (MCP tool agent):                                    │
│    • Confidence: 0.98 (has calendar MCP tool)                      │
│    • Latency: 200ms                                                 │
│    • Cost: $0.0002                                                 │
│    • Capabilities: ✅ mcp_calendar_check tool                       │
│                                                                      │
│  WebSearchAgent (MCP tool agent):                                   │
│    • Confidence: 0.85 (web search can be flaky)                    │
│    • Latency: 500ms                                                 │
│    • Cost: $0.001                                                  │
│    • Capabilities: ✅ mcp_web_search tool                           │
│                                                                      │
│  FormFillerAgent (MCP tool agent):                                  │
│    • Confidence: 0.92 (has form templates)                         │
│    • Latency: 150ms                                                 │
│    • Cost: $0.0001                                                 │
│    • Capabilities: ✅ mcp_form_fill tool, K0 access for patient info│
│                                                                      │
│  BookingAgent (MCP tool agent):                                     │
│    • Confidence: 0.90 (external API dependency)                    │
│    • Latency: 800ms (external API)                                 │
│    • Cost: $0.005                                                  │
│    • Capabilities: ✅ mcp_booking_api tool                          │
│                                                                      │
│  Duration: ~50ms (negotiate + spawn if needed)                     │
└─────────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│ PHASE 2: SELECTION (Weighted Scoring)                              │
│  Orchestrator selects agents based on plan DAG:                     │
│                                                                      │
│  Wave 1 (Parallel - no dependencies):                              │
│    • HealthcareAgent (K0 query) - SELECTED                         │
│    • CalendarAgent (calendar check) - SELECTED                      │
│                                                                      │
│  Wave 2 (Depends on Wave 1):                                       │
│    • WebSearchAgent (doctor search) - SELECTED                      │
│                                                                      │
│  Wave 3 (Depends on Wave 2):                                       │
│    • FormFillerAgent (pre-fill form) - SELECTED                    │
│    • BookingAgent (book appointment) - SELECTED                     │
│                                                                      │
│  Duration: ~5ms                                                     │
└─────────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│ PHASE 3: EXECUTION (Parallel DAG - ADR-0006c)                     │
└─────────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│ WAVE 1: Parallel Execution                                          │
└─────────────────────────────────────────────────────────────────────┘
         ┌────────────────────┴────────────────────┐
         │                                         │
┌────────▼───────────┐                 ┌──────────▼──────────┐
│ HealthcareAgent    │                 │ CalendarAgent       │
│ (Specialist)       │                 │ (Tool Agent)        │
└────────┬───────────┘                 └──────────┬──────────┘
         │                                         │
         │ Query K0 P01:                          │ MCP Tool: calendar_check
         │ • Past GERD episodes                   │ • User: prince
         │ • Doctor: Dr. Smith (gastro)           │ • Next 7 days
         │ • Last visit: 2 months ago             │ • Result: Free slots:
         │                                         │   - Tue 2pm-4pm
         │ Duration: ~100ms                       │   - Wed 10am-12pm
         └────────┬───────────────────────────────┴─Thu 3pm-5pm
                  │                                │
                  │                                │ Duration: ~200ms
         ┌────────▼────────┐
         │ Barrier: Wait   │
         │ for Wave 1      │
         └────────┬────────┘
                  ↓
┌─────────────────────────────────────────────────────────────────────┐
│ WAVE 2: WebSearchAgent                                              │
│  MCP Tool: web_search                                               │
│  Query: "Dr. Smith gastroenterologist availability"                │
│  Result: Office hours Mon-Fri 9am-5pm, accepting new patients      │
│  Duration: ~500ms                                                   │
└─────────────────────────────────────────────────────────────────────┘
                  ↓
         ┌────────▼────────┐
         │ Barrier: Wait   │
         │ for Wave 2      │
         └────────┬────────┘
                  ↓
┌─────────────────────────────────────────────────────────────────────┐
│ WAVE 3: Parallel Execution                                          │
└─────────────────────────────────────────────────────────────────────┘
         ┌────────────────────┴────────────────────┐
         │                                         │
┌────────▼───────────┐                 ┌──────────▼──────────┐
│ FormFillerAgent    │                 │ BookingAgent        │
│ (Tool Agent)       │                 │ (Tool Agent)        │
└────────┬───────────┘                 └──────────┬──────────┘
         │                                         │
         │ MCP Tool: form_fill                    │ MCP Tool: booking_api
         │ Template: appointment_form             │ Endpoint: /appointments
         │ Data from K0:                          │ Payload:
         │ • Name: Prince                         │ • Patient: Prince
         │ • DOB: [from K0]                       │ • Doctor: Dr. Smith
         │ • Insurance: [from K0]                 │ • Date: Tue 2pm
         │ • Symptoms: GERD, left side pain       │ • Reason: GERD follow-up
         │                                         │
         │ Duration: ~150ms                       │ Duration: ~800ms (API)
         └────────┬───────────────────────────────┴──────────┘
                  │
         ┌────────▼────────┐
         │ Barrier: Wait   │
         │ for Wave 3      │
         └────────┬────────┘
                  ↓
┌─────────────────────────────────────────────────────────────────────┐
│ T0+3000ms: All waves complete                                       │
│  • Healthcare data: Dr. Smith, last visit 2 months ago             │
│  • Calendar: 3 free slots found                                     │
│  • Web search: Dr. Smith available, accepting patients             │
│  • Form: Pre-filled with patient info                              │
│  • Booking: ✅ Appointment confirmed (Tue 2pm)                      │
└─────────────────────────────────────────────────────────────────────┘
                  ↓
┌─────────────────────────────────────────────────────────────────────┐
│ T0+3100ms: ConciergeAgent Synthesis                                │
│  Input: All agent results                                           │
│  Output: Natural language response                                  │
│                                                                      │
│  "I've scheduled an appointment with Dr. Smith (your                │
│   gastroenterologist) for Tuesday at 2pm. I've pre-filled the      │
│   form with your insurance info and noted the GERD symptoms and    │
│   left-side pain. You should receive a confirmation email shortly. │
│   Is there anything else you'd like me to prepare for the visit?"  │
│                                                                      │
│  Duration: ~100ms (LLM synthesis)                                   │
└─────────────────────────────────────────────────────────────────────┘
                  ↓
┌─────────────────────────────────────────────────────────────────────┐
│ T0+3200ms: K0 Memory Formation (Background)                        │
│  P02: Episodic memory                                               │
│    • Appointment booked: Dr. Smith, Tue 2pm, GERD follow-up       │
│    • Triggered by: Increased pain                                   │
│    • Action taken: User proactive about health                      │
│                                                                      │
│  P06: Learning update                                               │
│    • Pattern: User seeks medical help when symptoms worsen         │
│    • Preference: Prefers AI to handle appointment logistics        │
│                                                                      │
│  P19: Personalization                                               │
│    • Add to profile: "Appreciates proactive health management"     │
└─────────────────────────────────────────────────────────────────────┘
                  ↓
┌─────────────────────────────────────────────────────────────────────┐
│ T0+3500ms: Agent Lifecycle Cleanup                                  │
│  HealthcareAgent: ACTIVE → IDLE (may be reused soon)               │
│  CalendarAgent: ACTIVE → IDLE                                       │
│  WebSearchAgent: ACTIVE → DRAINING → TERMINATED (one-time use)     │
│  FormFillerAgent: ACTIVE → DRAINING → TERMINATED (one-time use)    │
│  BookingAgent: ACTIVE → DRAINING → TERMINATED (action complete)    │
│  ConciergeAgent: Remains ACTIVE (always active)                    │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│ ✅ PATH 2 COMPLETE: Appointment booked, user confirmed              │
│ TOTAL LATENCY: ~3200ms (within 5000ms P95 budget for actions)     │
└─────────────────────────────────────────────────────────────────────┘




Intent: QUERY (read-only)
Example: "remember we talked about reducing my gerd..."

Flow:
  ConciergeAgent → Specialist (Nutritionist)
                   • K0 queries only
                   • NO MCP tools
                   • NO external actions
                   • Pure analysis

Agents: Nutritionist, Psychiatrist, FinanceAnalyst
Speed: <1s
Complexity: Low (direct spawn, no planning)
Risk: Low (read-only)



Intent: ACTION (write operations)
Example: "I would like to schedule an appointment"

Flow:
  ConciergeAgent → PlannerAgent (4 stages)
                → Orchestrator (3 phases)
                → Tool Agents (MCP tools)
                   • External APIs
                   • Form filling
                   • Web search
                   • Calendar integration

Agents: CalendarAgent, BookingAgent, FormFillerAgent, WebSearchAgent
Speed: 2-5s
Complexity: High (planning + orchestration + validation)
Risk: High (external state changes, requires safety checks)


Thinking

Perfect! Yes, **real-time progress streaming** is essential for user experience. Let me show you the architecture:

## 🎯 Progress Streaming Architecture (No LLM, Animation-Based)

### **Pattern: Agent Progress Events**

```python
@dataclass
class ProgressEvent:
    """
    Progress event emitted by agents during execution.
    NO LLM generation - agents define milestones in code.
    """
    agent_id: str          # "agent-sess-123-nutritionist-001"
    agent_name: str        # "Nutritionist" (user-friendly)
    milestone: str         # "querying_k0", "analyzing_patterns", "complete"
    message: str           # "📊 Checking your diet history..."
    progress: float        # 0.0 to 1.0
    eta_ms: Optional[int]  # Estimated time remaining
    status: str            # "in_progress", "complete", "error"
    timestamp: datetime

    # Optional metadata
    details: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
```

### **Agent Implementation Example: Nutritionist**

```python
class NutritionistAgent:
    """
    Specialist agent that analyzes dietary patterns from K0.
    Emits progress events during execution (no LLM for progress).
    """

    def __init__(self, k0_client, progress_publisher):
        self.k0 = k0_client
        self.progress = progress_publisher  # Pub/sub for progress events

    async def analyze_gerd_triggers(self, context: AgentContext) -> AnalysisResult:
        """
        Analyze GERD triggers from K0 data.
        Emits 4 progress milestones during execution.
        """

        # MILESTONE 1: Initializing (0-10%)
        await self.progress.publish(ProgressEvent(
            agent_id=self.agent_id,
            agent_name="Nutritionist",
            milestone="initializing",
            message="🔍 Starting analysis...",
            progress=0.1,
            status="in_progress"
        ))

        # MILESTONE 2: Querying K0 (10-40%)
        await self.progress.publish(ProgressEvent(
            agent_name="Nutritionist",
            milestone="querying_k0",
            message="📊 Checking your diet history...",
            progress=0.3,
            status="in_progress",
            details={"query": "GERD episodes + diet correlation"}
        ))

        # Query K0 (actual work)
        diet_history = await self.k0.query_memories(
            domain="health",
            tags=["diet", "gerd"],
            limit=100
        )
        sleep_logs = await self.k0.query_memories(
            domain="health",
            tags=["sleep"],
            limit=50
        )

        # MILESTONE 3: Analyzing patterns (40-80%)
        await self.progress.publish(ProgressEvent(
            agent_name="Nutritionist",
            milestone="analyzing_patterns",
            message="🧠 Analyzing GERD triggers...",
            progress=0.6,
            status="in_progress",
            details={"memories_analyzed": len(diet_history) + len(sleep_logs)}
        ))

        # Run correlation analysis (actual work)
        correlations = await self._analyze_correlations(
            diet_history,
            sleep_logs,
            context.user_concern  # "milk making me sick"
        )

        # MILESTONE 4: Generating insights (80-100%)
        await self.progress.publish(ProgressEvent(
            agent_name="Nutritionist",
            milestone="generating_insights",
            message="💡 Identifying correlations...",
            progress=0.9,
            status="in_progress",
            details={"top_trigger": correlations[0].trigger}
        ))

        # Generate final insights
        insights = await self._generate_insights(correlations)

        # MILESTONE 5: Complete (100%)
        await self.progress.publish(ProgressEvent(
            agent_name="Nutritionist",
            milestone="complete",
            message="✅ Analysis complete",
            progress=1.0,
            status="complete",
            details={"insights_count": len(insights)}
        ))

        return AnalysisResult(
            agent_name="Nutritionist",
            insights=insights,
            correlations=correlations,
            confidence=0.87
        )
```

### **ConciergeAgent: Progress Stream Subscriber**

```python
class ConciergeAgent:
    """
    Central conversational brain.
    Subscribes to progress events and streams to user.
    """

    async def handle_user_message(self, message: str, user_id: str):
        """
        Main conversation handler with progress streaming.
        """

        # Classify intent
        intent = await self._classify_intent(message)

        if intent.type == "QUERY" and intent.domain == "health":
            # PATH 1: Background specialist

            # Immediate empathetic response
            await self.stream_to_user(
                user_id,
                message="That's sad to hear. Looping in nutritionist.",
                type="assistant_message"
            )

            # Subscribe to progress events BEFORE spawning agent
            progress_stream = self.progress_bus.subscribe(
                filter={"agent_type": "Nutritionist"}
            )

            # Spawn Nutritionist (background)
            task = asyncio.create_task(
                self._spawn_and_execute_specialist(
                    specialist_type="Nutritionist",
                    task=intent
                )
            )

            # Stream progress to user while agent works
            await self._stream_progress_to_user(
                user_id,
                progress_stream,
                until=task  # Stop when task completes
            )

            # Wait for result
            result = await task

            # Synthesize and stream final response
            await self.stream_to_user(
                user_id,
                message=f"Nutritionist: {result.insights[0].summary}",
                type="assistant_message"
            )

    async def _stream_progress_to_user(
        self,
        user_id: str,
        progress_stream: AsyncIterator[ProgressEvent],
        until: asyncio.Task
    ):
        """
        Stream progress events to user until task completes.
        """
        try:
            async for event in progress_stream:
                if until.done():
                    break

                # Stream progress event to user (SSE/WebSocket)
                await self.stream_to_user(
                    user_id,
                    message=event.message,
                    type="progress_update",
                    metadata={
                        "agent_name": event.agent_name,
                        "progress": event.progress,
                        "milestone": event.milestone,
                        "status": event.status
                    }
                )

                # Small delay to avoid flooding (100ms)
                await asyncio.sleep(0.1)

        except asyncio.CancelledError:
            # Task completed, stop streaming
            pass
```

### **PATH 2: Multi-Agent Progress (Parallel)**

```python
class ConciergeAgent:

    async def handle_action_request(self, message: str, user_id: str):
        """
        PATH 2: Action execution with multi-agent progress.
        """

        # Immediate response
        await self.stream_to_user(
            user_id,
            message="I'll help you schedule that appointment. Let me check your calendar...",
            type="assistant_message"
        )

        # Subscribe to ALL agent progress (multi-agent parallel)
        progress_stream = self.progress_bus.subscribe(
            filter={"session_id": self.session_id}
        )

        # Trigger Planner → Orchestrator → Tool Agents
        task = asyncio.create_task(
            self.orchestrator.coordinate_task(
                intent="schedule_appointment",
                context=self.session_state
            )
        )

        # Stream progress from ALL agents (parallel)
        await self._stream_progress_to_user(
            user_id,
            progress_stream,
            until=task
        )

        # Get results
        results = await task

        # Synthesize final response
        await self.stream_to_user(
            user_id,
            message=f"I've scheduled an appointment with {results.doctor_name} "
                   f"for {results.appointment_time}...",
            type="assistant_message"
        )
```

### **Frontend Experience (User View)**

**PATH 1: Single Specialist (Sequential Progress)**
```
┌──────────────────────────────────────────────────┐
│ User: "remember we talked about reducing my gerd │
│       and milk is making me more sick"           │
└──────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────┐
│ Concierge: "That's sad to hear. Looping in       │
│             nutritionist."                        │
└──────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────┐
│ [PROGRESS ANIMATION]                              │
│                                                   │
│ 🔍 Starting analysis...          [⏳ 10%]        │
└──────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────┐
│ [PROGRESS ANIMATION]                              │
│                                                   │
│ 📊 Checking your diet history... [⏳ 30%]        │
└──────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────┐
│ [PROGRESS ANIMATION]                              │
│                                                   │
│ 🧠 Analyzing GERD triggers...    [⏳ 60%]        │
└──────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────┐
│ [PROGRESS ANIMATION]                              │
│                                                   │
│ 💡 Identifying correlations...   [⏳ 90%]        │
└──────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────┐
│ ✅ Analysis complete                              │
└──────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────┐
│ Nutritionist: "I got your info and while going   │
│ through your diet chart and seeing your sleep    │
│ and work patterns it seems gerd may be not due   │
│ to milk but trigger may be late night coffee"    │
└──────────────────────────────────────────────────┘
```

**PATH 2: Multi-Agent (Parallel Progress)**
```
┌──────────────────────────────────────────────────┐
│ User: "Pain is more I would like to schedule an  │
│       appointment"                                │
└──────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────┐
│ Concierge: "I'll help you schedule that. Let me  │
│             check your calendar..."               │
└──────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────┐
│ [PARALLEL PROGRESS - Multiple Agents]             │
│                                                   │
│ 📋 Finding your gastroenterologist... [⏳ 20%]   │
│ 📅 Checking your availability...      [⏳ 20%]   │
└──────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────┐
│ [PARALLEL PROGRESS]                               │
│                                                   │
│ 📋 Finding your gastroenterologist... [⏳ 60%]   │
│ 📅 Checking your availability...      [✅ 100%]  │
│                                                   │
│ ✅ Found 3 free slots this week                   │
└──────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────┐
│ [PARALLEL PROGRESS]                               │
│                                                   │
│ 📋 Dr. Smith found                     [✅ 100%] │
│ 🔍 Checking availability...            [⏳ 40%]  │
└──────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────┐
│ [PARALLEL PROGRESS]                               │
│                                                   │
│ 📝 Pre-filling appointment form...    [⏳ 50%]   │
│ 📞 Booking appointment...              [⏳ 30%]   │
└──────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────┐
│ [PARALLEL PROGRESS]                               │
│                                                   │
│ 📝 Form ready                          [✅ 100%] │
│ 📞 Booking appointment...              [⏳ 70%]   │
└──────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────┐
│ ✅ All tasks complete                             │
│                                                   │
│ ✅ Appointment confirmed!                         │
└──────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────┐
│ Concierge: "I've scheduled an appointment with   │
│ Dr. Smith for Tuesday at 2pm. You should receive │
│ a confirmation email shortly."                    │
└──────────────────────────────────────────────────┘
```

## 🎯 Key Architecture Decisions

### ✅ **What Works**
1. **Agent-defined milestones** (not LLM-generated)
   - Fast (no LLM latency)
   - Cheap (no token cost)
   - Deterministic (predictable messages)

2. **Progress pub/sub pattern**
   - Agents publish events
   - ConciergeAgent subscribes
   - Frontend receives via SSE/WebSocket

3. **Visual cues + text**
   - Emoji for context (📊, 🔍, ✅)
   - Progress bars (0-100%)
   - Spinners for in-progress states

4. **Parallel agent visibility**
   - User sees all agents working
   - Real-time updates as each completes
   - Natural multi-tasking feeling

### ❌ **What to Avoid**
1. **LLM-generated progress messages**
   - Too slow (adds 50-100ms per update)
   - Too expensive (tokens for each message)
   - Not real-time (feels laggy)

2. **Blocking for progress**
   - Don't wait for progress to update
   - Stream asynchronously
   - User sees instant feedback

3. **Too many updates**
   - Rate-limit to ~200ms between updates
   - Avoid flooding user with events
   - Aggregate similar events

## 🎯 Updated PoC Requirements

**Phase 1: PATH 1 (Simple Specialist)**
1. ✅ ConciergeAgent conversation
2. ✅ Nutritionist spawning
3. ✅ K0 query integration
4. ✅ **Progress streaming** (4 milestones)
5. ✅ Result synthesis

**Phase 2: PATH 2 (Multi-Agent Actions)**
1. ✅ PlannerAgent pipeline
2. ✅ Orchestrator coordination
3. ✅ Tool Agents with MCP tools
4. ✅ **Parallel progress streaming** (multiple agents)
5. ✅ Saga pattern

---
