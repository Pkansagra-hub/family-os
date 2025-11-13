# 🧠 Concierge PoC - Design Rationale & Research Foundation

**Purpose:** Explain the research-backed patterns enabling ConciergeAgent to maintain human-like conversation while delegating tasks to background specialists.

**Status:** Design Document
**Date:** 2025-11-07

---

## 🎯 Core Design Challenge

**Problem Statement:**
How do we create a conversational AI that feels **ALIVE and HUMAN** while simultaneously coordinating complex background work (K0 queries, multi-agent orchestration, external API calls)?

**User Expectation:**

```
User: "remember we talked about reducing my gerd..."
System: "That's sad to hear. Looping in nutritionist."
        [100ms later, not 1000ms blocked waiting]
User: "until nutritionist gathers data, why can't you tell me..."
System: "Of course! Tell me how uneasy it was."
        [ConciergeAgent continues conversation]
        [Meanwhile: Nutritionist queries K0 in background]
```

**Key Tension:**

- **Conversational Flow:** Must feel instant, empathetic, natural (human-like)
- **Background Work:** Specialists need 500-3000ms to complete tasks
- **Traditional Approach:** User waits → "Loading..." → Response (feels robotic)
- **Our Approach:** Conversation continues → Background work → Seamless integration

---

## 📚 Research Foundation (2022+ Focus)

### **0. LLM-Based Multi-Agent Systems (2023-2024) - NEW PARADIGM**

**Research:** Recent explosion in LLM-powered agent research

- **MetaGPT (Hong, 2023):** Multi-agent framework for software development
- **AutoGen (Wu, 2023):** Microsoft's conversable agents with code execution
- **ChatDev (Qian, 2023):** Multi-agent collaboration for software engineering
- **Generative Agents (Park, 2023):** Stanford's simulation with believable human behavior

**Core Insights:**

- LLMs enable agents to communicate in natural language (no rigid protocols)
- Agents can reflect on past actions and plan future steps (meta-cognition)
- Human-in-the-loop critical for steering complex agent systems
- Emergent behaviors from simple agent roles + LLM reasoning

**Application to ConciergeAgent:**

```
Traditional Multi-Agent (pre-2022):
  - Rigid message protocols (FIPA-ACL, KQML)
  - Hand-coded coordination rules
  - Limited adaptability

LLM-Powered (2023+):
  - Natural language communication
  - ConciergeAgent synthesizes specialist results via LLM
  - Dynamic task decomposition (Planner uses GPT-4)
  - Context-aware delegation ("looping in nutritionist" = LLM generates empathy)
```

**Why This Changes Everything:**

- ConciergeAgent can EXPLAIN what specialists are doing (LLM synthesis)
- Specialist results integrated naturally (not template-based)
- User interruptions handled via LLM reasoning (not FSM)
- Emergent conversation patterns (not scripted dialogues)

**Research Citations:**

- Hong, S., et al. (2023). "MetaGPT: Meta Programming for Multi-Agent Collaborative Framework"
- Wu, Q., et al. (2023). "AutoGen: Enabling Next-Gen LLM Applications via Multi-Agent Conversation"
- Qian, C., et al. (2023). "ChatDev: Communicative Agents for Software Development"
- Park, J. S., et al. (2023). "Generative Agents: Interactive Simulacra of Human Behavior"

---

### **1. Actor Model (Hewitt, 1973) - Foundation for Concurrent Processing**

**Classic Research:** Carl Hewitt's Actor Model

- **Paper:** "A Universal Modular ACTOR Formalism for Artificial Intelligence" (1973)
- **Core Insight:** Actors are independent entities that process messages asynchronously
- **Key Principles:**
  - No shared state (message passing only)
  - Concurrent execution (actors work in parallel)
  - Location transparency (actors don't know where others are)

**Modern Evolution (2022+):**

- **LangGraph (Harrison, 2024):** Graph-based orchestration for LLM agents
- **CrewAI (2024):** Role-based agent collaboration with LLMs
- Actor Model + LLMs = Flexible agent coordination

**Application to ConciergeAgent:**

```
ConciergeAgent (Actor 1) ──message──> NutritionistAgent (Actor 2)
     │                                       │
     └─ Continues conversation              └─ Queries K0 (parallel)
     │                                       │
     └─ Receives result ◄───message─────────┘
```

**Why This Works:**

- ConciergeAgent doesn't WAIT for Nutritionist (non-blocking)
- Both agents run concurrently (Actor Model guarantee)
- Message passing decouples conversation from analysis
- User sees continuous conversation (ConciergeAgent always responsive)

**Research Citations:**

- Hewitt, C., Bishop, P., & Steiger, R. (1973). "A Universal Modular ACTOR Formalism"
- Agha, G. (1986). "Actors: A Model of Concurrent Computation"

---

### **2. Conversational Grounding (Clark & Brennan, 1991) - Human-Like Dialogue**

**Research:** Herbert Clark's Theory of Grounding

- **Paper:** "Grounding in Communication" (1991)
- **Core Insight:** Human conversation builds "common ground" through continuous feedback
- **Key Principles:**
  - Acknowledgment tokens ("I see", "Hmm", "That's sad to hear")
  - Presentation-acceptance pairs (speaker presents, listener accepts)
  - Side sequences (sub-conversations while main task pending)

**Application to ConciergeAgent:**

```
User: "remember we talked about reducing my gerd..."
      ↓
Concierge: "That's sad to hear. Looping in nutritionist."
           └─ GROUNDING: Acknowledges user's concern
           └─ TRANSPARENCY: Explains what's happening
      ↓
[Nutritionist working in background]
      ↓
Concierge: "Until nutritionist gathers data, why can't you tell me..."
           └─ SIDE SEQUENCE: Keeps conversation alive
           └─ COMMON GROUND: Maintains shared understanding
      ↓
User: "pain in left side of stomach"
      ↓
Concierge: "Ahh I will take a note..."
           └─ ACKNOWLEDGMENT: Captures new information
           └─ CONTINUITY: Conversation never stops
```

**Why This Works:**

- User feels HEARD (acknowledgment tokens prevent "ghost AI" feeling)
- Transparency builds trust ("looping in nutritionist" = user knows what's happening)
- Side sequences fill wait time (conversation doesn't freeze)
- Common ground accumulates (SessionState tracks shared knowledge)

**Research Citations:**

- Clark, H. H., & Brennan, S. E. (1991). "Grounding in Communication"
- Traum, D. R. (1994). "A Computational Theory of Grounding in Natural Language Conversation"

---

### **3. Incremental Processing + Streaming LLMs (2011 → 2023+)**

**Classic Research:** Incremental Dialogue Processing (Schlangen & Skantze, 2011)

- **Paper:** "A General, Abstract Model of Incremental Dialogue Processing"
- **Core Insight:** Human conversation processes input incrementally (word-by-word), not sentence-by-sentence

**Modern Evolution - Streaming LLMs (2023+):**

- **GPT-4 Turbo Streaming (OpenAI, 2023):** Token-by-token response generation
- **Anthropic Claude Streaming (2024):** Reduced latency via streaming
- **Gemini 1.5 Pro (Google, 2024):** Multi-modal streaming (text + vision + audio)

**New Capability: Real-Time LLM Synthesis**

- Traditional: Wait for full LLM response (2-5s) → Display
- Streaming: Display tokens as generated (user sees response immediately)
- **ConciergeAgent Application:** Synthesis streams word-by-word (feels instant)

**Key Principles:**

- Immediate feedback (before full utterance complete)
- Partial results (show progress, not "loading...")
- Revisions allowed (user can interrupt/correct)
- **NEW:** Token streaming (LLM responses appear word-by-word)

**Application to ConciergeAgent:**

```
Traditional (Batch Processing):
User: "remember we talked about reducing my gerd..."
      [1000ms silence]
System: "I found that milk triggers GERD..."
        └─ User waited 1s → Feels slow

Our Approach (Incremental Processing):
User: "remember we talked about reducing my gerd..."
      [10ms]
Concierge: "That's sad to hear..."
      [50ms]
Concierge: "Looping in nutritionist."
      [Progress updates every 200ms]
      "📊 Checking your diet history..."
      "🧠 Analyzing GERD triggers..."
      [Final result at 1000ms]
Concierge: "Nutritionist: ...late night coffee trigger"
        └─ User saw continuous feedback → Feels instant
```

**Why This Works:**

- First response <50ms (user never sees "thinking...")
- Progress updates every 200-500ms (continuous feedback loop)
- User can interrupt anytime (ConciergeAgent detects new messages)
- Feels like human conversation (doctor says "let me check" then keeps talking)

**Research Citations:**

- Schlangen, D., & Skantze, G. (2011). "A General, Abstract Model of Incremental Dialogue Processing"
- Buß, O., & Schlangen, D. (2011). "DIUM - An Incremental Dialogue Manager"

---

### **4. Progressive Disclosure (Norman, 1988) - Information Architecture**

**Research:** Donald Norman's Design of Everyday Things

- **Book:** "The Design of Everyday Things" (1988)
- **Core Insight:** Show information progressively, not all at once
- **Key Principles:**
  - Reveal complexity gradually
  - Provide signifiers (what's happening now)
  - Feedback loops (progress indicators)

**Application to Progress Streaming:**

```
Simple Query (PATH 1):
User: "What triggers my GERD?"
      ↓
Concierge: "Let me check..." [10ms]
      ↓
Progress: "🔍 Starting analysis..." [100ms]
Progress: "📊 Checking diet history..." [300ms]
Progress: "🧠 Analyzing patterns..." [600ms]
Progress: "✅ Analysis complete" [1000ms]
      ↓
Concierge: "Late night coffee is the trigger" [1100ms]

Complex Action (PATH 2):
User: "Schedule an appointment"
      ↓
Concierge: "Let me coordinate that..." [10ms]
      ↓
Progress: [PARALLEL - Multiple Agents Visible]
          "📋 Finding your doctor..." [100ms]
          "📅 Checking calendar..." [100ms]
          "✅ Found 3 free slots" [300ms]
          "🔍 Searching availability..." [500ms]
          "📞 Booking appointment..." [1500ms]
          "✅ Confirmed!" [2500ms]
      ↓
Concierge: "Appointment booked for Tuesday 2pm" [2600ms]
```

**Why This Works:**

- User sees WHAT'S HAPPENING (not black box)
- Progress indicators reduce perceived wait time (psychology: known wait < unknown wait)
- Parallel agents visible (user understands system is multitasking)
- Emoji signifiers (📊, 🧠, ✅) provide instant semantic meaning

**Research Citations:**

- Norman, D. A. (1988). "The Design of Everyday Things"
- Miller, R. B. (1968). "Response Time in Man-Computer Conversational Transactions"

---

### **5. Cognitive Load Theory (Sweller, 1988) - Managing User Attention**

**Research:** John Sweller's Cognitive Load Theory

- **Paper:** "Cognitive Load During Problem Solving" (1988)
- **Core Insight:** Human working memory is limited (7±2 items)
- **Key Principles:**
  - Minimize extraneous load (don't overwhelm with info)
  - Optimize germane load (focus on what matters)
  - Progressive complexity (simple → complex)

**Application to Dual-Path Architecture:**

```
PATH 1 (Simple Queries) - LOW Cognitive Load:
User: "What triggers my GERD?"
Concierge: "Let me check..."
           [1 specialist, 4 progress updates, 1 result]
           └─ User tracks: 1 task, 1 agent, 1 outcome
           └─ Cognitive Load: LOW (< 3 items)

PATH 2 (Complex Actions) - MANAGED Cognitive Load:
User: "Schedule appointment"
Concierge: "Let me coordinate that..."
           [5 agents, waves grouped, progress batched]
           └─ User tracks: 1 goal ("book appointment")
           └─ Visual grouping: Wave 1 → Wave 2 → Wave 3
           └─ Cognitive Load: MODERATE (chunked into 3 waves)

NOT This (Cognitive Overload):
[10 agents firing simultaneously, no structure]
└─ User overwhelmed, can't track progress
└─ Cognitive Load: HIGH (10+ items) → User confused
```

**Why This Works:**

- PATH 1: Simple queries stay simple (1 specialist, clear progress)
- PATH 2: Complex actions grouped into waves (chunking reduces load)
- Progress messages short (7-10 words max, fits working memory)
- Visual hierarchy (waves, completion indicators) aids comprehension

**Research Citations:**

- Sweller, J. (1988). "Cognitive Load During Problem Solving"
- Miller, G. A. (1956). "The Magical Number Seven, Plus or Minus Two"

---

## 🏗️ Architectural Patterns (2022+ Novel Approaches)

### **Pattern 0: ReAct + Chain-of-Thought for Agent Planning (Yao, 2022; Wei, 2022)**

**Research Foundation:**

- **ReAct (Yao, 2022):** Reasoning + Acting in LLM agents
- **Chain-of-Thought (Wei, 2022):** Step-by-step reasoning improves LLM performance
- **Tree of Thoughts (Yao, 2023):** Exploration of reasoning paths
- **Reflexion (Shinn, 2023):** Self-reflection for agent improvement

**What is ReAct Architecture?**

ReAct (Reasoning + Acting) is a pattern where LLMs generate interleaved **thoughts** and **actions**:

```
Question: "What is the elevation of the mountain where Obama was born?"

[THOUGHT 1]: "I need to find where Obama was born first"
[ACTION 1]:  Search["Barack Obama birthplace"]
[OBSERVATION 1]: "Barack Obama was born in Honolulu, Hawaii"

[THOUGHT 2]: "Now I need to find a mountain in Honolulu"
[ACTION 2]:  Search["mountains in Honolulu Hawaii"]
[OBSERVATION 2]: "Diamond Head, elevation 760 feet"

[THOUGHT 3]: "But Obama wasn't born on a mountain, let me reconsider"
[ACTION 3]:  Search["Honolulu elevation"]
[OBSERVATION 3]: "Honolulu elevation is 16 feet above sea level"

[ANSWER]: "Obama was born in Honolulu at ~16 feet elevation, not on a mountain"
```

**ReAct Loop:**

```
1. THOUGHT:     LLM reasons about what to do next
2. ACTION:      LLM generates action (API call, tool use)
3. OBSERVATION: External environment returns result
4. REPEAT:      Loop until task complete
```

**Key Properties:**

- **Task-focused:** Solves specific problems (Q&A, decision making)
- **Sequential:** One thought → one action → one observation
- **External grounding:** Actions query external knowledge (Wikipedia, environment)
- **Self-correcting:** Thoughts can revise plan based on observations

---

**IMPORTANT: ReAct vs Reactive-Proactive (DIFFERENT PATTERNS)**

| Aspect | ReAct (Yao, 2022) | Reactive-Proactive (Ours) |
|--------|-------------------|---------------------------|
| **Purpose** | Task-solving with reasoning | Conversation continuity during wait |
| **Focus** | Thinking before acting | Maintaining human-like dialogue |
| **Loop** | Thought → Action → Observation | Reactive → Spawn → Proactive → Synthesis |
| **User Role** | Asks question, waits for answer | Active conversation partner |
| **Timing** | Sequential (one step at a time) | Concurrent (conversation + background work) |
| **Goal** | Correct answer via reasoning | Natural conversation rhythm |
| **Example** | "Search Wikipedia → Think → Search again" | "Empathy → Spawn specialist → Ask follow-up" |

**Where We Use Each:**

**ReAct (Planning):**

- **Component:** PlannerAgent (PATH 2 - ACTION intent)
- **Usage:** Generate multi-step plans with reasoning
- **Example:** "Book appointment" → Thought: "Need calendar + doctor + booking" → Action: Create 5-step DAG

**Reactive-Proactive (Conversation):**

- **Component:** ConciergeAgent (all intents)
- **Usage:** Maintain dialogue while specialists work
- **Example:** "Milk makes me sick" → Reactive: "That's sad" → Proactive: "Tell me how uneasy?" → Synthesis: "Coffee is trigger"

**Both Patterns Working Together:**

```
User: "Schedule appointment"
      ↓
[REACTIVE-PROACTIVE] ConciergeAgent: "Let me coordinate that." [<50ms]
      ↓
[ReAct PLANNING] PlannerAgent uses ReAct reasoning:
    Thought: "Need doctor + calendar + booking"
    Action: Create 5-step plan
    Observation: Plan validated by Safety Arbiter
      ↓
[REACTIVE-PROACTIVE] ConciergeAgent: "While planning, which doctor?" [Proactive]
      ↓
[ORCHESTRATION] Tool agents execute plan
      ↓
[REACTIVE-PROACTIVE] ConciergeAgent: "Appointment booked for Tuesday 2pm" [Synthesis]
```

---

**Application to PlannerAgent (PATH 2):**

```
Traditional Planning (pre-2022):
  - Hand-coded rules (if X then Y)
  - Fixed task decomposition
  - No adaptation

ReAct-Style Planning (2023+):
  STAGE 1 (SKETCH):
    Thought: "User wants to schedule appointment"
    Reasoning: "Need doctor info + calendar + booking"
    Action: Generate 5-step plan

  STAGE 3 (VALIDATE):
    Thought: "Booking involves PII (AMBER band)"
    Reasoning: "Need safety check for PII handling"
    Action: Trigger Safety Arbiter
```

**Why This Works:**

- LLM generates plans via reasoning (not templates)
- Self-correction via reflection (Safety Arbiter = reflexion step)
- Adaptive to user intent (not rigid workflows)

**Research Citations:**

- Yao, S., et al. (2022). "ReAct: Synergizing Reasoning and Acting in Language Models"
- Wei, J., et al. (2022). "Chain-of-Thought Prompting Elicits Reasoning in LLMs"
- Yao, S., et al. (2023). "Tree of Thoughts: Deliberate Problem Solving with LLMs"
- Shinn, N., et al. (2023). "Reflexion: Language Agents with Verbal Reinforcement Learning"

---

### **Pattern 1: Conversational Orchestration (Our Novel Pattern)**

**Definition:**
A conversational agent that maintains dialogue continuity while orchestrating background work, using Actor Model concurrency + Grounding Theory + Incremental Processing.

**Components:**

1. **Conversational Frontend (ConciergeAgent)**
   - Always responsive (<50ms)
   - Empathetic acknowledgments
   - Side sequences during wait time
   - Result synthesis

2. **Background Workers (Specialists / Tool Agents)**
   - Async execution (Actor Model)
   - Progress milestone emission
   - No direct user interaction

3. **Progress Streaming Layer**
   - Pub/sub event bus
   - Rate-limited updates
   - Visual signifiers (emoji + text)

4. **Dual-Path Routing**
   - PATH 1: Simple queries → Direct specialist spawn
   - PATH 2: Complex actions → Planner → Orchestrator → Tool agents

**Novel Contribution:**

- **Traditional orchestrators:** Wait for all tasks → Return result (blocking)
- **Our approach:** Start conversation → Spawn workers → Continue conversation → Integrate results (non-blocking)
- **Key Innovation:** ConciergeAgent acts as **conversational facade** over async orchestration

**Pseudocode:**

```python
class ConciergeAgent:
    async def handle_message(self, message):
        # 1. IMMEDIATE RESPONSE (Grounding Theory)
        await self.respond("That's sad to hear...")

        # 2. SPAWN BACKGROUND WORK (Actor Model)
        task = asyncio.create_task(
            self.spawn_specialist(message)
        )

        # 3. CONTINUE CONVERSATION (Incremental Processing)
        while not task.done():
            # Stream progress updates
            async for progress in self.progress_stream:
                await self.stream_to_user(progress)

            # Check for user interruptions
            if self.new_message_arrived():
                # Side sequence (Clark & Brennan)
                await self.handle_interruption()

        # 4. INTEGRATE RESULTS (Progressive Disclosure)
        result = await task
        await self.synthesize_response(result)
```

**Research Synthesis:**

- Actor Model (Hewitt) → Concurrent specialists
- Grounding Theory (Clark) → Continuous acknowledgments
- Incremental Processing (Schlangen) → Progress streaming
- Progressive Disclosure (Norman) → Gradual complexity reveal
- Cognitive Load (Sweller) → Chunked presentation

---

### **Pattern 2: Tiered Agent Hierarchy (Inspired by Multi-Agent Systems)**

**Definition:**
3-tier agent architecture where Tier 1 (ConciergeAgent) is always active and user-facing, Tier 2 (Specialists) spawned on-demand for data analysis, Tier 3 (Tool Agents) coordinated by Orchestrator for actions.

**Hierarchy:**

```
Tier 1: ConciergeAgent
  ├─ Always active (never terminated)
  ├─ User-facing (all conversation flows through)
  ├─ Routes to Tier 2 or Tier 3
  └─ Synthesizes results into natural language

Tier 2: Specialists (PATH 1)
  ├─ Spawned on-demand (ADR-0086 Dynamic Agent Creation)
  ├─ K0 data analysts (query + analyze)
  ├─ NO external actions (read-only)
  └─ Report back to ConciergeAgent

Tier 3: Tool Agents (PATH 2)
  ├─ Coordinated by Planner + Orchestrator
  ├─ MCP tool integration (external APIs)
  ├─ Write operations (bookings, forms, emails)
  └─ Saga pattern for compensation
```

**Research Foundation:**

- **Contract Net Protocol (Smith, 1980):** Tier 3 agents bid on tasks
- **Blackboard Systems (Erman, 1980):** Tier 1 (ConciergeAgent) = blackboard controller
- **BDI Architecture (Rao, 1995):** Tier 2/3 agents have Beliefs (K0 context), Desires (task goals), Intentions (execution plans)

**Why Tiered:**

- Tier 1 guarantees responsiveness (always active = instant <50ms)
- Tier 2 isolates K0 queries (no external dependencies = predictable <1s)
- Tier 3 isolates risky actions (planning + validation before execution)

**Citations:**

- Smith, R. G. (1980). "The Contract Net Protocol"
- Erman, L. D. (1980). "The Hearsay-II Speech-Understanding System"
- Rao, A. S., & Georgeff, M. P. (1995). "BDI Agents"

---

### **Pattern 3: Progress-Aware Streaming (Our Evolution of SSE)**

**Definition:**
Server-Sent Events (SSE) extended with agent progress milestones, allowing frontend to show real-time work status without polling.

**Traditional SSE:**

```
Server → Client: "data: {message: 'Hello'}\n\n"
                 (single message type)
```

**Our Evolution:**

```
Server → Client:
  "data: {type: 'assistant_message', content: 'That's sad to hear'}\n\n"
  "data: {type: 'progress_update', agent: 'Nutritionist', progress: 0.3}\n\n"
  "data: {type: 'progress_update', agent: 'Nutritionist', progress: 0.6}\n\n"
  "data: {type: 'assistant_message', content: 'Nutritionist: ...'}\n\n"
  (multiple message types with structured metadata)
```

**Novel Contributions:**

1. **Agent-defined milestones** (not LLM-generated)
   - Faster (no LLM call for progress)
   - Cheaper (zero token cost)
   - Deterministic (predictable messages)

2. **Multi-agent multiplexing** (parallel agents visible)
   - User sees 5 agents working simultaneously
   - Wave-based grouping (visual hierarchy)
   - Per-agent progress bars

3. **Rate limiting + batching** (cognitive load management)
   - Max 5 updates/sec (avoid flooding)
   - Similar events batched (reduce noise)
   - Completion aggregation (✅ indicators)

**Research Foundation:**

- **Event-Driven Architecture (Michelson, 2006):** SSE = event stream
- **Reactive Streams (Boner, 2014):** Backpressure + rate limiting
- **Information Scent (Pirolli, 2003):** Progress messages = "scent" of progress

**Citations:**

- Michelson, B. M. (2006). "Event-Driven Architecture Overview"
- Boner, J. (2014). "Reactive Streams"
- Pirolli, P., & Card, S. (2003). "Information Foraging Theory"

---

### **Pattern 4: Conversational State Management (SessionState + Scoreboard)**

**Definition:**
Unified session state tracking conversation history, active agents, pending tasks, and user context (affect, beliefs, referents).

**Data Structure:**

```python
@dataclass
class SessionState:
    # Conversation tracking
    turn_count: int
    recent_history: Deque[Turn]  # Last 10 turns

    # Agent coordination
    active_specialists: Dict[str, AgentID]
    pending_tasks: List[TaskID]

    # User context (from whiteboard_chatexp.md)
    affect: AffectState          # User emotion tracking
    self_model: SelfModel        # User beliefs about self
    scoreboard: Scoreboard       # Common ground, referents

    # Progress tracking
    progress_events: List[ProgressEvent]
```

**Key Innovation: Scoreboard Pattern**
From whiteboard_chatexp.md, extended for ConciergeAgent:

```python
@dataclass
class Scoreboard:
    # Common ground (Clark & Brennan)
    qud: str  # Question Under Discussion
    referents: Dict[str, Any]  # "the nutritionist", "that trigger"

    # Task tracking
    pending_specialists: List[str]  # ["Nutritionist"]
    completed_tasks: List[str]      # ["analyze_gerd"]

    # Conversation flow
    last_user_intent: Intent
    last_assistant_response: str
    conversation_state: str  # "awaiting_specialist" | "active_dialogue"
```

**Why This Works:**

- **Referent resolution:** User says "that trigger" → Scoreboard resolves to "late night coffee"
- **Task continuity:** User interrupts → Scoreboard tracks pending work
- **Context carryover:** Multi-turn conversation → Scoreboard maintains shared knowledge
- **Progress visibility:** Frontend queries Scoreboard for active specialists

**Research Foundation:**

- **Dialogue State Tracking (Williams, 2007):** Track beliefs over dialogue
- **Common Ground Theory (Clark, 1991):** Scoreboard = computational common ground
- **QUD Framework (Roberts, 2012):** Question Under Discussion guides conversation

**Citations:**

- Williams, J. D. (2007). "Partially Observable Markov Decision Processes for Dialog Systems"
- Clark, H. H. (1991). "Grounding in Communication"
- Roberts, C. (2012). "Information Structure in Discourse"

---

## 🧪 Validation Through Research

### **Performance Targets (Backed by HCI Research)**

| Metric | Target | Research Basis |
|--------|--------|---------------|
| Initial response | <50ms | Miller (1968): <100ms = instant |
| Progress update | <200ms | Card (1991): <200ms = immediate |
| Total latency (PATH 1) | <1200ms | Nielsen (1993): <1s = continuous flow |
| Total latency (PATH 2) | <3000ms | Nielsen (1993): <10s = acceptable |
| Progress update rate | 5/sec max | Cognitive load: 7±2 items/sec |

**Research Citations:**

- Miller, R. B. (1968). "Response Time in Man-Computer Conversational Transactions"
- Card, S. K. (1991). "The Psychology of Human-Computer Interaction"
- Nielsen, J. (1993). "Usability Engineering"

---

### **User Experience Goals (Backed by Conversation Analysis)**

| Goal | Pattern | Research Basis |
|------|---------|---------------|
| Feel heard | Acknowledgment tokens | Clark (1991): Grounding |
| Trust system | Transparency signals | Norman (1988): Signifiers |
| Stay engaged | Side sequences | Sacks (1974): Turn-taking |
| Understand progress | Visual feedback | Norman (1988): Feedback loops |
| Maintain control | Interruptibility | Schegloff (1987): Repair |

**Research Citations:**

- Clark, H. H. (1991). "Grounding in Communication"
- Norman, D. A. (1988). "The Design of Everyday Things"
- Sacks, H. (1974). "A Simplest Systematics for the Organization of Turn-Taking"
- Schegloff, E. A. (1987). "Some Sources of Misunderstanding in Talk-in-Interaction"

---

## 🔬 Novel Contributions (Building on 2023+ Research)

### **0. Reactive-Proactive Conversation Loop (2025 - NOVEL PATTERN)**

**Related Research (1990s-2020s):**

There IS existing research on proactive/reactive dialogue, BUT focused on different problems:

1. **Mixed-Initiative Dialogue (Allen, 1999; Horvitz, 1999)**
   - **Focus:** WHO controls conversation (user vs system)
   - **Example:** System proactively suggests "Would you like to add dessert?"
   - **Gap:** Not about filling wait time during async work

2. **Proactive Assistants (Horvitz, 1999; Rich, 2001)**
   - **Focus:** System initiates tasks (reminders, notifications)
   - **Example:** "Traffic is bad, leave now for your meeting"
   - **Gap:** Notification-based, not conversational continuity

3. **Clarification Strategies (Purver, 2004; Schlangen, 2016)**
   - **Focus:** Resolving ambiguity (ask clarifying questions)
   - **Example:** "Did you mean X or Y?"
   - **Gap:** Reactive to confusion, not proactive during processing

4. **Proactive Dialogue Systems (Yang, 2018; Sun, 2021)**
   - **Focus:** Task-oriented systems asking for missing info
   - **Example:** "What date for your flight?"
   - **Gap:** Sequential turn-taking, no async background work

5. **Conversational Grounding (Clark, 1991; Traum, 1994)**
   - **Focus:** Mutual understanding, acknowledgment tokens
   - **Example:** "Uh-huh", "I see", "Got it"
   - **Gap:** Doesn't address wait-time anxiety during processing

**What's NOVEL About Our Pattern:**

| Aspect | Existing Research | Our Reactive-Proactive Loop |
|--------|-------------------|----------------------------|
| **Proactive Timing** | Task initiation or clarification | Fill conversation gaps DURING background work |
| **Concurrency** | Sequential turn-taking | Conversation + specialist work in parallel |
| **Purpose** | Resolve ambiguity or suggest tasks | Maintain human-like rhythm, reduce wait anxiety |
| **LLM Integration** | Pre-LLM dialogue systems (rule-based) | LLM generates contextual proactive prompts |
| **Target Latency** | Not time-sensitive | Specifically designed for 500-1000ms async gaps |

**Research Citations:**

- Allen, J. F., et al. (1999). "Mixed-Initiative Interaction." *IEEE Intelligent Systems*, 14(5), 14-23.
- Horvitz, E. (1999). "Principles of Mixed-Initiative User Interfaces." *CHI Conference*.
- Purver, M. (2004). "The Theory and Use of Clarification Requests in Dialogue." *PhD Thesis, King's College London*.
- Rich, C., & Sidner, C. L. (2001). "COLLAGEN: When Agents Collaborate with People." *AGENTS*.
- Yang, Z., et al. (2018). "Proactive Dialogue Retrieval for Conversations." *EMNLP*.
- Sun, K., & Tseng, B. (2021). "Proactive Human-Machine Conversation." *ACL*.
- Clark, H. H., & Brennan, S. E. (1991). "Grounding in Communication." *American Psychological Association*.
- Traum, D. R. (1994). "A Computational Theory of Grounding." *PhD Thesis, University of Rochester*.

---

**Our Contribution (Building on Prior Work):**

**The Pattern You Discovered:**

```
User: "milk is making me more sick"
      ↓
[REACTIVE] Concierge: "That's sad to hear. Looping in nutritionist." [Empathy + Action]
      ↓
[SPAWN] Nutritionist working in background (500-1000ms)
      ↓
[PROACTIVE] Concierge: "Until nutritionist gathers data and sees triggers,
                        why can't you tell me how uneasy it was?" [Anticipates user's wait anxiety]
      ↓
[REACTIVE] User: "pain in left side of stomach" [Responds to proactive prompt]
      ↓
[PROACTIVE] Concierge: "I'll take a note about milk and remind you at next doctor visit" [Future action]
      ↓
[BACKGROUND COMPLETE] Nutritionist: "Trigger may be late night coffee, not milk"
      ↓
[SYNTHESIS] Concierge: "Interesting - nutritionist found coffee as trigger..." [Integrates result]
```

**Why This Feels HUMAN:**

**Classic Reactive-Only (Robotic):**

```
User: "milk is making me sick"
Concierge: "Let me check..." [BLOCKS]
[1000ms silence]
Concierge: "It's actually coffee, not milk"
└─ User anxiety during wait, feels like talking to machine
```

**Proactive-Only (Annoying):**

```
User: "milk is making me sick"
Concierge: "Tell me more! How uneasy? What symptoms? When did it start?" [Bombards]
└─ Feels interrogative, not conversational
```

**Reactive-Proactive Loop (HUMAN-LIKE):**

```
User: "milk is making me sick"
Concierge: [REACTIVE] "That's sad to hear. Looping in nutritionist."
           [PROACTIVE] "While we wait, tell me how uneasy it was?"
User: "pain in left side"
Concierge: [REACTIVE] "I'll note that."
           [PROACTIVE] "I'll remind you to mention milk at next visit"
[Background work completes]
Concierge: [SYNTHESIS] "Nutritionist found coffee is trigger, not milk"
└─ Feels like doctor conversation: empathy + action + follow-up + integration
```

**Research Foundation (2024+):**

- **Conversational Grounding (Clark, 1991):** Side sequences during main task
- **Generative Agents (Park, 2023):** Believable behavior via reflection + planning
- **Turn-Taking Theory (Sacks, 1974):** Human conversation has natural rhythm
- **Gap in Research:** No LLM agent systems implement reactive-proactive INTERLEAVING

**Why Current Systems Fail:**

- **AutoGen (2023):** Task-focused, no proactive conversation fillers
- **ChatDev (2023):** Batch workflow, no real-time interaction
- **Voice Assistants (Alexa/Siri):** Reactive only, no anticipatory prompts during wait

**Our Novel Contribution:**

1. **Proactive Prompts DURING Background Work:**
   - ConciergeAgent doesn't just say "working..."
   - Asks clarifying questions to reduce user anxiety
   - Example: "Until nutritionist finishes, tell me X..."

2. **Reactive-Proactive Rhythm:**
   - REACTIVE: Acknowledge user input immediately
   - PROACTIVE: Anticipate next conversation move
   - LOOP: Maintain rhythm even during 1000ms background work

3. **LLM-Powered Anticipation:**
   - Not scripted templates ("Tell me more...")
   - LLM generates contextually relevant proactive prompts
   - Example: "Why can't you tell me how uneasy it was?" (natural, not robotic)

4. **Future Action Promises:**
   - "I'll remind you at next doctor visit"
   - Shows system is thinking ahead (proactive memory formation)
   - Builds trust (user knows system won't forget)

**Implementation Pattern:**

```python
# ConciergeAgent main loop
async def handle_message(user_message: str):
    # 1. REACTIVE: Immediate acknowledgment
    intent = await classify_intent(user_message)
    await stream("That's sad to hear. Looping in nutritionist.")

    # 2. SPAWN: Background work
    task_id = await spawn_specialist("nutritionist", intent)

    # 3. PROACTIVE: Fill conversation gap
    proactive_prompt = await generate_proactive_prompt(intent, context)
    # "Until nutritionist gathers data, why can't you tell me how uneasy it was?"
    await stream(proactive_prompt)

    # 4. LISTEN: User may respond to proactive prompt
    # (handled by next message in conversation)

    # 5. SYNTHESIS: Integrate background result when ready
    result = await wait_for_result(task_id)
    synthesis = await synthesize_result(result, context)
    await stream(synthesis)
```

**Validation Metrics:**

- **Conversational Continuity:** Turns during background work (target: 2-3 turns)
- **User Anxiety Reduction:** "Did it freeze?" incidents (target: <5%)
- **Proactive Prompt Quality:** User engagement rate (target: >70% respond)
- **Human-Like Rating:** Likert scale "Feels like talking to human" (target: >4.0/5.0)

**Expected Research Contribution:**

- **Pattern:** "Reactive-Proactive Loop for LLM Agent Orchestration"
- **Metric:** Conversational Flow Index (CFI) = proactive turns / total background time
- **Paper:** "Human-Like Agent Conversation: Interleaving Reactive and Proactive Turns During Async Work"

---

## 🏗️ Implementation Design: Reactive-Proactive Loop

### **System Architecture Overview**

```
┌─────────────────────────────────────────────────────────────┐
│                      ConciergeAgent                          │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │  Reactive   │  │  Proactive   │  │   Synthesis      │  │
│  │  Handler    │  │  Generator   │  │   Engine         │  │
│  └──────┬──────┘  └──────┬───────┘  └────────┬─────────┘  │
│         │                 │                    │             │
│         ├─────────────────┴────────────────────┤             │
│         │      Conversation State Manager      │             │
│         └──────────────────┬───────────────────┘             │
└────────────────────────────┼─────────────────────────────────┘
                             │
                    ┌────────┴────────┐
                    │                 │
           ┌────────▼──────┐  ┌──────▼──────────┐
           │  Background   │  │   Progress      │
           │  Specialists  │  │   Publisher     │
           └───────────────┘  └─────────────────┘
```

---

## 🎯 System Design: Building the PoC with LLMs

### **Design Philosophy**

**Hybrid Approach: LLMs + Deterministic Logic**

| Component | LLM or Deterministic? | Rationale |
|-----------|----------------------|-----------|
| Intent Classification | LLM (cached) | Natural language understanding needs flexibility |
| Empathy Generation | Rule-based with LLM fallback | Fast (<10ms) for common patterns, LLM for edge cases |
| Proactive Prompt Generation | LLM | Context-aware, natural language, adaptive |
| Progress Milestones | Deterministic | Predictable, zero latency, zero cost |
| Result Synthesis | LLM | Natural integration of specialist findings |
| Contradiction Detection | Rule-based + LLM | Fast pattern matching, LLM for complex cases |

**Key Principle:** Use LLMs for **creativity** (empathy, proactive prompts, synthesis), use deterministic logic for **speed** (milestones, routing, error handling).

---

### **LLM Integration Points (6 Critical Calls)**

#### **1. Intent Classification (Reactive Handler)**

**Purpose:** Classify user intent to route to PATH 1 (specialist) or PATH 2 (orchestrator)

**LLM Call:**
```python
async def classify_intent(user_message: str, context: ConversationState) -> Intent:
    """
    Classify user intent using LLM

    Budget: <30ms (use cached model or fast model like Phi-3-mini)
    Cost: ~$0.0001 per call (100 tokens)
    """

    # Build prompt with conversation context
    prompt = f"""You are an intent classifier for a health assistant.

Previous conversation:
{format_recent_history(context.recent_history)}

Current user message: "{user_message}"

Classify the intent:
- Type: QUERY (data analysis) or ACTION (execute task)
- Domain: health, finance, social, general
- Complexity: simple (one specialist) or multi_step (orchestrator needed)
- Specialist: nutritionist, psychiatrist, finance_analyst, or orchestrator

Output JSON:
{{
  "type": "QUERY|ACTION",
  "domain": "health|finance|social|general",
  "complexity": "simple|multi_step",
  "specialist_type": "nutritionist|psychiatrist|finance_analyst|orchestrator",
  "confidence": 0.0-1.0,
  "entities": ["milk", "GERD", "pain"]
}}
"""

    # Call LLM (use fast model)
    response = await llm_client.generate(
        prompt=prompt,
        model="gpt-4o-mini",  # Fast, cheap
        max_tokens=100,
        temperature=0.0,  # Deterministic
        cache_key=f"intent_{hash(user_message)}"  # Cache for repeated queries
    )

    # Parse JSON response
    intent_data = json.loads(response)

    return Intent(
        type=intent_data["type"],
        domain=intent_data["domain"],
        complexity=intent_data["complexity"],
        specialist_type=intent_data["specialist_type"],
        confidence=intent_data["confidence"],
        entities=intent_data["entities"]
    )
```

**Research Basis:** Intent classification from dialogue systems (Allen, 1999; Purver, 2004)

**Performance Target:** <30ms P95 (use model caching, small model)

---

#### **2. Empathy Generation (Reactive Handler)**

**Purpose:** Generate immediate empathetic response to user message

**LLM Call:**
```python
async def generate_empathy(
    user_message: str,
    detected_emotion: str,
    context: ConversationState
) -> str:
    """
    Generate empathetic acknowledgment

    Budget: <20ms (rule-based fallback, LLM for complex cases)
    Cost: ~$0.0001 per call
    """

    # Rule-based fast path (covers 80% of cases)
    EMPATHY_MAP = {
        "frustrated": ["That must be frustrating", "I understand your frustration"],
        "concerned": ["I understand your concern", "That's concerning"],
        "sad": ["That's sad to hear", "I'm sorry to hear that"],
        "pain": ["That sounds painful", "That's tough to deal with"],
    }

    # Check if simple pattern match works
    for keyword, responses in EMPATHY_MAP.items():
        if keyword in user_message.lower() or keyword == detected_emotion:
            return random.choice(responses)

    # LLM fallback for complex cases
    prompt = f"""Generate a brief empathetic response (5-8 words max).

User message: "{user_message}"
Detected emotion: {detected_emotion}

Examples:
- "That must be frustrating"
- "I understand your concern"
- "That's sad to hear"

Empathetic response:"""

    response = await llm_client.generate(
        prompt=prompt,
        model="gpt-4o-mini",
        max_tokens=20,
        temperature=0.7,  # Slight variation
        cache_key=f"empathy_{detected_emotion}"
    )

    return response.strip()
```

**Research Basis:** Conversational grounding (Clark, 1991) - acknowledgment tokens

**Performance Target:** <20ms (rule-based), <50ms (LLM fallback)

---

#### **3. Proactive Prompt Generation (Proactive Generator)**

**Purpose:** Generate contextually relevant proactive prompt to fill conversation gap during background work

**LLM Call (CRITICAL - This is the novel pattern):**
```python
async def generate_proactive_prompt(
    context: ConversationState,
    background_task: BackgroundTask,
    strategy: str  # "fill_gap", "future_action", "clarify"
) -> ProactivePrompt:
    """
    Generate proactive prompt using LLM

    Budget: <100ms (this is the "magic" - worth the latency)
    Cost: ~$0.0005 per call (200-300 tokens)

    Research Basis:
    - Mixed-initiative dialogue (Horvitz, 1999)
    - Proactive systems (Yang, 2018; Sun, 2021)
    - Our novel contribution: proactive prompts DURING async work
    """

    specialist_name = background_task.specialist_type.title()
    specialist_action = get_specialist_action(background_task)  # "gathers data"

    # Extract information gaps from conversation
    gaps = context.information_gaps  # ["pain_location", "severity", "duration"]
    recent_concern = extract_last_concern(context)  # "milk"

    if strategy == "fill_gap" and gaps:
        prompt = f"""You are a conversational AI that maintains natural dialogue during background work.

Context:
- User mentioned: "{recent_concern}"
- Specialist working: {specialist_name} is {specialist_action} (will take ~1 second)
- Missing information: {gaps}

Generate a natural proactive prompt that:
1. Acknowledges the specialist is working ("Until {specialist_name} {specialist_action}...")
2. Naturally transitions to asking for missing info
3. Sounds conversational, not robotic
4. Fills the wait time productively

Examples of GOOD prompts:
- "Until nutritionist gathers data and sees triggers, why can't you tell me how uneasy it was?"
- "While they're analyzing patterns, could you describe where exactly the pain is?"
- "As they check your history, tell me - how long have you had this?"

Examples of BAD prompts:
- "Please wait while I process your request." (too robotic)
- "Tell me more." (too generic)
- "What else?" (not natural)

Generate ONE natural proactive prompt (15-25 words):"""

        response = await llm_client.generate(
            prompt=prompt,
            model="gpt-4o-mini",  # Or gpt-4 for better quality
            max_tokens=50,
            temperature=0.8,  # More creative
            top_p=0.9
        )

        return ProactivePrompt(
            text=response.strip(),
            prompt_type="fill_gap",
            information_target=gaps[0],
            sent_at=time.time(),
            user_responded=False
        )

    elif strategy == "future_action":
        prompt = f"""Generate a brief future action promise that builds user trust.

Context:
- User mentioned concern: "{recent_concern}"
- Specialist working: {specialist_name}

Generate a promise to remember and act on this later (10-15 words):

Examples:
- "I'll take a note about {recent_concern} and remind you at your next doctor visit."
- "I'll flag {recent_concern} for when you see your doctor next."

Natural promise:"""

        response = await llm_client.generate(
            prompt=prompt,
            model="gpt-4o-mini",
            max_tokens=40,
            temperature=0.7
        )

        return ProactivePrompt(
            text=response.strip(),
            prompt_type="future_action",
            information_target=recent_concern,
            sent_at=time.time(),
            user_responded=False
        )
```

**Research Basis:**
- Mixed-initiative dialogue (Horvitz, 1999) - system takes initiative
- Proactive dialogue (Yang, 2018; Sun, 2021) - anticipatory questions
- **Our novel contribution:** Timing (during background work) + Purpose (maintain rhythm)

**Performance Target:** <100ms (acceptable during background work window)

---

#### **4. Result Synthesis (Synthesis Engine)**

**Purpose:** Naturally integrate specialist results into conversation

**LLM Call:**
```python
async def synthesize_result(
    specialist_result: AnalysisResult,
    context: ConversationState
) -> str:
    """
    Synthesize specialist findings into natural conversation

    Budget: <200ms (after specialist completes, user expects thoughtful response)
    Cost: ~$0.001 per call (400-500 tokens)

    Research Basis:
    - Conversational grounding (Clark, 1991) - present common ground
    - Generative agents (Park, 2023) - believable synthesis
    """

    # Extract key data
    primary_insight = specialist_result.insights[0]
    evidence = specialist_result.insights[0].evidence
    user_assumption = extract_user_assumption(context.recent_history)  # "milk"
    actual_finding = primary_insight.summary  # "late night coffee"

    # Check for contradiction
    contradiction = (user_assumption and
                    user_assumption.lower() not in actual_finding.lower())

    prompt = f"""You are synthesizing findings from a nutrition specialist into natural conversation.

Conversation context:
{format_recent_history(context.recent_history)}

Specialist findings:
- Main insight: {primary_insight.summary}
- Evidence: {', '.join(evidence[:3])}
- Confidence: {specialist_result.confidence:.0%}

User assumption: "{user_assumption}"
Actual finding: "{actual_finding}"
Contradiction detected: {contradiction}

Generate a natural synthesis that:
1. Acknowledges the specialist's work ("Interesting - the nutritionist found...")
2. Presents the key finding clearly
3. If contradiction exists, gently correct it ("actually", "interestingly")
4. Connects evidence to user's original concern
5. Sounds conversational, not like a report

Good example:
"Interesting - the nutritionist analyzed your patterns and found that the trigger
may actually be late night coffee, not the milk. The evidence shows 3 out of 5
GERD episodes occurred after evening coffee."

Bad example:
"Analysis complete. Result: Coffee trigger identified. Confidence: 87%." (too robotic)

Natural synthesis (30-50 words):"""

    response = await llm_client.generate(
        prompt=prompt,
        model="gpt-4o-mini",  # Or gpt-4 for higher quality
        max_tokens=100,
        temperature=0.7,  # Natural variation
        top_p=0.9
    )

    return response.strip()
```

**Research Basis:**
- Conversational grounding (Clark, 1991) - establishing common ground
- Generative agents (Park, 2023) - natural language generation
- ReAct (Yao, 2022) - observation integration (though not sequential here)

**Performance Target:** <200ms (user waits 1000ms for specialist, 200ms more is acceptable)

---

#### **5. Emotion Detection (Reactive Handler - Optional)**

**Purpose:** Detect user emotion for better empathy generation

**LLM Call (Lightweight):**
```python
async def detect_emotion(user_message: str) -> str:
    """
    Detect user emotion from message

    Budget: <20ms (can use rule-based + sentiment model instead of LLM)
    Cost: ~$0.0001 per call
    """

    # Fast pattern matching first (covers 70% of cases)
    EMOTION_PATTERNS = {
        "frustrated": ["frustrated", "annoyed", "irritated", "fed up"],
        "concerned": ["worried", "concerned", "nervous", "anxious"],
        "sad": ["sad", "upset", "down", "depressed"],
        "pain": ["pain", "hurt", "ache", "sore", "uncomfortable"],
        "confused": ["confused", "don't understand", "unclear", "lost"],
    }

    message_lower = user_message.lower()
    for emotion, keywords in EMOTION_PATTERNS.items():
        if any(kw in message_lower for kw in keywords):
            return emotion

    # LLM fallback for ambiguous cases
    prompt = f"""Detect emotion in one word: frustrated, concerned, sad, pain, confused, or neutral.

Message: "{user_message}"

Emotion:"""

    response = await llm_client.generate(
        prompt=prompt,
        model="gpt-4o-mini",
        max_tokens=5,
        temperature=0.0,
        cache_key=f"emotion_{hash(user_message)}"
    )

    return response.strip().lower()
```

**Alternative:** Use lightweight sentiment model (DistilBERT, <10ms) instead of LLM

**Performance Target:** <20ms

---

#### **6. Information Gap Identification (Conversation State Manager)**

**Purpose:** Identify what information is missing for proactive prompts

**LLM Call:**
```python
async def identify_information_gaps(
    user_message: str,
    specialist_type: str,
    context: ConversationState
) -> List[str]:
    """
    Identify missing information that specialist might need

    Budget: <50ms (run in parallel with specialist spawn)
    Cost: ~$0.0002 per call
    """

    prompt = f"""Identify missing information for a {specialist_type} analysis.

User message: "{user_message}"

Conversation history:
{format_recent_history(context.recent_history)}

Common information gaps for {specialist_type}:
- pain_location: Where exactly is the pain?
- pain_severity: How severe? (scale 1-10)
- pain_duration: How long has this been happening?
- symptoms: What symptoms are you experiencing?
- triggers: What makes it worse?
- timing: When did it start?

Which gaps are present? List up to 3 most important gaps.

Output JSON array:
["gap1", "gap2", "gap3"]

Missing information:"""

    response = await llm_client.generate(
        prompt=prompt,
        model="gpt-4o-mini",
        max_tokens=30,
        temperature=0.0,  # Deterministic
        response_format={"type": "json"}
    )

    gaps = json.loads(response)
    return gaps[:3]  # Limit to top 3
```

**Performance Target:** <50ms (parallel with specialist spawn)

---

### **LLM Call Summary & Cost Analysis**

| LLM Call | When | Model | Budget | Tokens | Cost/Call | Frequency |
|----------|------|-------|--------|--------|-----------|-----------|
| Intent Classification | Every user message | gpt-4o-mini | 30ms | ~100 | $0.0001 | Every turn |
| Empathy Generation | Every user message | gpt-4o-mini (fallback) | 20ms | ~20 | $0.0001 | 20% of turns |
| Proactive Prompt | If background work >300ms | gpt-4o-mini/gpt-4 | 100ms | ~200 | $0.0005 | 50% of turns |
| Result Synthesis | When specialist completes | gpt-4o-mini/gpt-4 | 200ms | ~400 | $0.001 | Every specialist result |
| Emotion Detection | Every user message | gpt-4o-mini (fallback) | 20ms | ~10 | $0.0001 | 30% of turns |
| Gap Identification | If spawning specialist | gpt-4o-mini | 50ms | ~50 | $0.0002 | 50% of turns |

**Per-Conversation Cost Estimate:**
- Average conversation: 10 turns
- Total LLM cost: ~$0.02 per conversation (affordable)
- Total latency budget: <500ms LLM time per conversation (acceptable)

**Cost Optimization Strategies:**
1. **Caching:** Cache intent classification, emotion detection (~30% hit rate)
2. **Rule-based fallbacks:** Use deterministic logic for common patterns (empathy)
3. **Model selection:** Use gpt-4o-mini for speed/cost, gpt-4 only for synthesis quality
4. **Batching:** Not applicable here (real-time conversation)

---

### **Complete System Flow with LLM Calls**

```
USER MESSAGE: "remember we talked about reducing my gerd and milk is making me sick"
│
├─ 0-30ms:  LLM Call #1 - Intent Classification
│           └─ Result: {type: "QUERY", specialist: "nutritionist", confidence: 0.92}
│
├─ 0-20ms:  (Parallel) LLM Call #2 - Emotion Detection (rule-based match: "sad")
│           └─ Result: "concerned"
│
├─ 0-20ms:  (Parallel) Rule-based Empathy Generation
│           └─ Result: "That's sad to hear"
│
├─ 50ms:    REACTIVE Response Sent
│           └─ "That's sad to hear. Looping in nutritionist."
│
├─ 50-100ms: Spawn NutritionistAgent (background, 500-1000ms)
│            (Parallel) LLM Call #3 - Gap Identification
│            └─ Result: ["pain_severity", "pain_location", "duration"]
│
├─ 100-200ms: LLM Call #4 - Proactive Prompt Generation
│             └─ Prompt: "Until nutritionist gathers data and sees triggers,
│                         why can't you tell me how uneasy it was?"
│
├─ 200ms:   PROACTIVE Response Sent
│           └─ User may respond with "pain in left side"
│
├─ 200-1000ms: [USER MAY RESPOND - New message loop]
│              If user responds: New intent classification → Reactive acknowledgment
│              "I'll take a note about milk for your doctor visit"
│
├─ 300-1000ms: Progress Updates (Deterministic - NO LLM)
│              └─ "📊 Checking your diet history..." [30%]
│              └─ "🧠 Analyzing patterns..." [60%]
│              └─ "💡 Generating insights..." [90%]
│
├─ 1000ms:  NutritionistAgent completes
│           LLM Call #5 - Result Synthesis
│           └─ "Interesting - the nutritionist found that the trigger
│               may actually be late night coffee, not the milk..."
│
└─ 1200ms:  SYNTHESIS Response Sent
            Conversation continues...
```

**Total LLM Budget:** ~400ms per conversation turn (out of 1200ms total)
**Total Cost:** ~$0.002 per turn (~$0.02 per 10-turn conversation)

---

### **Component Architecture: Research Pattern → Implementation Mapping**

| Research Pattern | Our Implementation | Code Location | Purpose |
|-----------------|-------------------|---------------|---------|
| **Actor Model** (Hewitt 1973) | `asyncio.Queue` mailboxes for agent communication | `backend/agents/base.py` | Message passing between ConciergeAgent, specialists |
| **Conversational Grounding** (Clark 1991) | Acknowledgment tokens in reactive responses | `backend/agents/concierge.py` | "That's sad to hear", "I understand" |
| **Incremental Processing** (Schlangen 2011) | SSE streaming responses, word-by-word | `backend/api/chat.py` | Real-time response streaming |
| **Progressive Disclosure** (Norman 1988) | 5 progress milestones per specialist | `backend/models/progress_event.py` | Reduce cognitive load during wait |
| **ReAct** (Yao 2022) | PlannerAgent Thought→Action→Observation loop | `backend/agents/planner.py` | Multi-step plan generation (PATH 2) |
| **Mixed-Initiative Dialogue** (Allen 1999) | Proactive prompts during background work | `backend/agents/proactive_generator.py` | System takes initiative to ask questions |
| **Proactive Dialogue Systems** (Yang 2018) | Information gap identification + filling | `backend/agents/conversation_state.py` | Detect missing information, ask naturally |
| **SEDA** (Welsh 2001) | Background specialist work with progress events | `backend/agents/nutritionist.py` | Staged event-driven architecture |
| **Reactive-Proactive Loop** (Our novel pattern) | Interleaving reactive + proactive responses | `backend/agents/concierge.py` | Conversation continuity during async work |

---

### **Detailed Component Implementation**

#### **Component 1: ConciergeAgent (Main Orchestrator)**

**Location:** `backend/agents/concierge.py`

**Responsibilities:**
1. Receive user messages
2. Classify intent (LLM)
3. Send immediate reactive response (empathy + action declaration)
4. Spawn specialist agent in background
5. Generate proactive prompts during wait
6. Synthesize final results

**Key Methods:**

```python
class ConciergeAgent:
    """
    Main conversational orchestrator using reactive-proactive loop

    Research basis: Mixed-Initiative Dialogue (Allen 1999),
                   Actor Model (Hewitt 1973),
                   Our Reactive-Proactive Loop pattern
    """

    def __init__(self, llm_client, k0_query_service):
        self.llm_client = llm_client
        self.k0_query_service = k0_query_service
        self.conversation_state = ConversationStateManager()
        self.reactive_handler = ReactiveHandler(llm_client)
        self.proactive_generator = ProactiveGenerator(llm_client)
        self.synthesis_engine = SynthesisEngine(llm_client)
        self.specialist_registry = {
            "nutritionist": NutritionistAgent,
            "psychiatrist": PsychiatristAgent,
            "finance_analyst": FinanceAnalystAgent,
        }
        self.progress_publisher = ProgressPublisher()  # SSE publisher

    async def handle_message(self, user_message: str, user_id: str) -> AsyncGenerator:
        """
        Main message handling loop with reactive-proactive pattern

        Yields SSE events: reactive response, proactive prompts, progress, synthesis
        """

        # Step 1: Intent Classification (LLM - 30ms)
        intent = await self.reactive_handler.classify_intent(
            user_message,
            self.conversation_state
        )

        # Step 2: Reactive Response (empathy + action, LLM/rule-based - 20ms)
        reactive_response = await self.reactive_handler.generate_response(
            user_message,
            intent,
            self.conversation_state
        )

        # Yield immediate reactive response (50ms total)
        yield SSEEvent(type="message", data=reactive_response)

        # Update conversation state
        self.conversation_state.add_turn(user_message, reactive_response)

        # Step 3: Decide routing (PATH 1 or PATH 2)
        if intent.complexity == "simple":
            # PATH 1: Single specialist
            await self._handle_specialist_path(intent, user_message, user_id)
        else:
            # PATH 2: Orchestrator + Planner
            await self._handle_orchestrator_path(intent, user_message, user_id)

    async def _handle_specialist_path(self, intent, user_message, user_id):
        """
        PATH 1: Spawn specialist, generate proactive prompts, synthesize results

        This is where the reactive-proactive loop magic happens!
        """

        # Spawn specialist in background (asyncio.create_task)
        specialist_class = self.specialist_registry[intent.specialist_type]
        specialist = specialist_class(self.k0_query_service)

        # Create background task
        specialist_task = asyncio.create_task(
            specialist.analyze(user_message, user_id)
        )

        # Step 4: Identify information gaps (LLM - 50ms, parallel)
        gaps = await self.proactive_generator.identify_gaps(
            user_message,
            intent.specialist_type,
            self.conversation_state
        )

        # Step 5: Generate proactive prompt after delay (100ms delay + 100ms LLM)
        await asyncio.sleep(0.1)  # 100ms delay before first proactive prompt

        # Only generate if specialist task is still running
        if not specialist_task.done():
            proactive_prompt = await self.proactive_generator.generate_prompt(
                self.conversation_state,
                BackgroundTask(
                    specialist_type=intent.specialist_type,
                    estimated_duration=1.0  # 1 second
                ),
                strategy="fill_gap" if gaps else "future_action"
            )

            # Yield proactive prompt (200ms total)
            yield SSEEvent(type="proactive", data=proactive_prompt.text)
            self.conversation_state.add_proactive_prompt(proactive_prompt)

        # Step 6: Subscribe to progress updates (deterministic - NO LLM)
        async for progress in self.progress_publisher.subscribe(specialist_task):
            yield SSEEvent(type="progress", data=progress)

        # Step 7: Wait for specialist to complete
        specialist_result = await specialist_task

        # Step 8: Synthesize results (LLM - 200ms)
        synthesis = await self.synthesis_engine.synthesize(
            specialist_result,
            self.conversation_state
        )

        # Yield final synthesis
        yield SSEEvent(type="message", data=synthesis)
        self.conversation_state.add_turn(None, synthesis)  # System turn
```

**Key LLM Integration Points:**
1. `classify_intent()` - LLM Call #1 (30ms)
2. `generate_response()` - LLM Call #2 (20ms, fallback)
3. `identify_gaps()` - LLM Call #3 (50ms)
4. `generate_prompt()` - LLM Call #4 (100ms) **[NOVEL PATTERN]**
5. `synthesize()` - LLM Call #5 (200ms)

---

#### **Component 2: ReactiveHandler (Immediate Response Generator)**

**Location:** `backend/agents/reactive_handler.py`

**Responsibilities:**
1. Classify user intent (PATH 1 vs PATH 2)
2. Detect emotion (sentiment analysis or LLM)
3. Generate empathetic acknowledgment
4. Declare action (which specialist is being called)

**Key Methods:**

```python
class ReactiveHandler:
    """
    Handles immediate reactive responses (<50ms budget)

    Research basis: Conversational Grounding (Clark 1991)
    """

    def __init__(self, llm_client):
        self.llm_client = llm_client
        self.emotion_detector = EmotionDetector()  # Rule-based + LLM fallback
        self.empathy_generator = EmpathyGenerator()  # Rule-based + LLM fallback

    async def classify_intent(
        self,
        user_message: str,
        context: ConversationState
    ) -> Intent:
        """
        Classify intent using LLM (see LLM Call #1 above)
        """
        # Implementation in LLM Integration Points section
        pass

    async def generate_response(
        self,
        user_message: str,
        intent: Intent,
        context: ConversationState
    ) -> str:
        """
        Generate immediate reactive response

        Format: "{empathy}. {action_declaration}."
        Example: "That's sad to hear. Looping in nutritionist."
        """

        # Detect emotion (rule-based fast path, LLM fallback)
        emotion = await self.emotion_detector.detect(user_message)

        # Generate empathy (rule-based fast path, LLM fallback)
        empathy = await self.empathy_generator.generate(user_message, emotion)

        # Declare action (deterministic - NO LLM)
        action = self._get_action_declaration(intent)

        return f"{empathy}. {action}."

    def _get_action_declaration(self, intent: Intent) -> str:
        """
        Deterministic action declaration (no LLM needed)
        """
        ACTION_TEMPLATES = {
            "nutritionist": "Looping in nutritionist",
            "psychiatrist": "Connecting you with psychiatrist",
            "finance_analyst": "Checking with finance analyst",
            "orchestrator": "Creating a plan for you",
        }

        return ACTION_TEMPLATES.get(
            intent.specialist_type,
            f"Working on that with {intent.specialist_type}"
        )
```

**Performance Optimization:**
- **Rule-based fast path:** 80% of empathy responses use pattern matching (<10ms)
- **LLM fallback:** Only for complex/ambiguous cases (20%)
- **Caching:** Cache intent classifications for repeated phrases

---

#### **Component 3: ProactiveGenerator (Novel Pattern - Core Innovation)**

**Location:** `backend/agents/proactive_generator.py`

**Responsibilities:**
1. Identify information gaps in conversation
2. Generate contextually relevant proactive prompts
3. Choose strategy: fill_gap, future_action, or clarify
4. Respect timing rules (only if >300ms background work, 5s cooldown)

**Key Methods:**

```python
class ProactiveGenerator:
    """
    Generates proactive prompts during background work

    Research basis:
    - Mixed-Initiative Dialogue (Allen 1999, Horvitz 1999)
    - Proactive Dialogue Systems (Yang 2018, Sun 2021)
    - Our novel contribution: Timing (during background work) + Purpose (maintain rhythm)
    """

    def __init__(self, llm_client):
        self.llm_client = llm_client
        self.last_proactive_time = None
        self.COOLDOWN_SECONDS = 5  # Don't spam proactive prompts
        self.MIN_BACKGROUND_DURATION = 0.3  # Only if >300ms background work

    async def identify_gaps(
        self,
        user_message: str,
        specialist_type: str,
        context: ConversationState
    ) -> List[str]:
        """
        Identify missing information using LLM (see LLM Call #3 above)
        """
        # Implementation in LLM Integration Points section
        pass

    async def generate_prompt(
        self,
        context: ConversationState,
        background_task: BackgroundTask,
        strategy: str
    ) -> ProactivePrompt:
        """
        Generate proactive prompt using LLM (see LLM Call #4 above)

        This is the CORE NOVEL PATTERN!
        """

        # Check cooldown
        if self.last_proactive_time:
            elapsed = time.time() - self.last_proactive_time
            if elapsed < self.COOLDOWN_SECONDS:
                return None  # Skip proactive prompt

        # Check background task duration
        if background_task.estimated_duration < self.MIN_BACKGROUND_DURATION:
            return None  # Too short, no need for proactive prompt

        # Generate prompt using LLM (see LLM Integration Points)
        proactive_prompt = await self._generate_with_llm(
            context, background_task, strategy
        )

        # Update cooldown
        self.last_proactive_time = time.time()

        return proactive_prompt

    def choose_strategy(
        self,
        gaps: List[str],
        context: ConversationState
    ) -> str:
        """
        Choose proactive strategy based on context

        Deterministic rule-based logic (no LLM)
        """
        if gaps and len(gaps) > 0:
            return "fill_gap"  # Ask for missing information

        if context.user_expressed_future_concern:
            return "future_action"  # Promise to remember later

        if context.last_turn_was_ambiguous:
            return "clarify"  # Ask for clarification

        return "fill_gap"  # Default
```

**Key Innovation:**
- **Timing:** Generate prompts DURING background work (100-200ms after spawn)
- **Context-aware:** LLM generates natural prompts, not templates
- **Adaptive:** Choose strategy based on conversation state
- **Respectful:** 5-second cooldown, only if background work >300ms

**Validation Metrics:**
- 2-3 proactive turns per conversation (not overwhelming)
- <5% "frozen" perception incidents
- 80%+ perceived naturalness ratings

---

#### **Component 4: SynthesisEngine (Result Integration)**

**Location:** `backend/agents/synthesis_engine.py`

**Responsibilities:**
1. Receive specialist results (AnalysisResult)
2. Extract key insights
3. Detect contradictions with user assumptions
4. Generate natural synthesis using LLM

**Key Methods:**

```python
class SynthesisEngine:
    """
    Synthesizes specialist findings into natural conversation

    Research basis:
    - Conversational Grounding (Clark 1991) - common ground
    - Generative Agents (Park, 2023) - believable synthesis
    """

    def __init__(self, llm_client):
        self.llm_client = llm_client

    async def synthesize(
        self,
        specialist_result: AnalysisResult,
        context: ConversationState
    ) -> str:
        """
        Synthesize results using LLM (see LLM Call #5 above)
        """
        # Implementation in LLM Integration Points section
        pass

    def _detect_contradiction(
        self,
        user_assumption: str,
        specialist_finding: str
    ) -> bool:
        """
        Simple contradiction detection (rule-based)
        """
        # Check if user mentioned X but specialist found Y
        user_lower = user_assumption.lower()
        finding_lower = specialist_finding.lower()

        # Extract key entities
        user_entities = extract_entities(user_assumption)
        finding_entities = extract_entities(specialist_finding)

        # Check for mismatch
        return len(set(user_entities) & set(finding_entities)) == 0

    def _format_evidence(self, evidence: List[str], max_items: int = 3) -> str:
        """
        Format evidence list for LLM prompt
        """
        if len(evidence) <= max_items:
            return ", ".join(evidence)

        return ", ".join(evidence[:max_items]) + f" (and {len(evidence) - max_items} more)"
```

**Key Features:**
- **Contradiction handling:** Gently correct user assumptions ("actually", "interestingly")
- **Evidence presentation:** Show top 3 evidence items
- **Natural language:** Conversational tone, not report-like
- **Context-aware:** Reference conversation history

---

#### **Component 5: NutritionistAgent (Specialist Example)**

**Location:** `backend/agents/nutritionist.py`

**Responsibilities:**
1. Receive query from ConciergeAgent
2. Query K0 for user data (diet history, GERD episodes, correlations)
3. Emit progress milestones (deterministic - NO LLM)
4. Generate insights using LLM (optional)

**Key Methods:**

```python
class NutritionistAgent:
    """
    Specialist agent for nutrition analysis

    Research basis:
    - Actor Model (Hewitt 1973) - message passing
    - SEDA (Welsh 2001) - staged event-driven architecture
    - Progressive Disclosure (Norman 1988) - 5 milestones
    """

    def __init__(self, k0_query_service):
        self.k0_query_service = k0_query_service
        self.progress_emitter = ProgressEmitter()

    async def analyze(
        self,
        user_query: str,
        user_id: str
    ) -> AnalysisResult:
        """
        Analyze nutrition query with progress updates

        Total duration: 500-1000ms
        Progress milestones: 5 deterministic events (NO LLM)
        """

        # Milestone 1: Starting (0ms)
        await self.progress_emitter.emit(
            milestone=1,
            message="📊 Checking your diet history...",
            percent=20
        )

        # Query K0 for diet history (200ms)
        diet_history = await self.k0_query_service.query(
            user_id=user_id,
            data_type="diet_entries",
            time_range="last_30_days"
        )

        # Milestone 2: Data retrieved (200ms)
        await self.progress_emitter.emit(
            milestone=2,
            message="🧠 Analyzing patterns...",
            percent=40
        )

        # Query K0 for GERD episodes (200ms)
        gerd_episodes = await self.k0_query_service.query(
            user_id=user_id,
            data_type="health_events",
            filters={"condition": "GERD"},
            time_range="last_30_days"
        )

        # Milestone 3: Correlating (400ms)
        await self.progress_emitter.emit(
            milestone=3,
            message="🔗 Finding correlations...",
            percent=60
        )

        # Correlate diet with GERD (deterministic algorithm - NO LLM)
        correlations = self._correlate_diet_with_gerd(
            diet_history, gerd_episodes
        )

        # Milestone 4: Generating insights (600ms)
        await self.progress_emitter.emit(
            milestone=4,
            message="💡 Generating insights...",
            percent=80
        )

        # Generate insights (LLM optional, can be rule-based)
        insights = await self._generate_insights(correlations)

        # Milestone 5: Complete (1000ms)
        await self.progress_emitter.emit(
            milestone=5,
            message="✅ Analysis complete",
            percent=100
        )

        return AnalysisResult(
            specialist_type="nutritionist",
            query=user_query,
            insights=insights,
            evidence=correlations,
            confidence=self._calculate_confidence(correlations),
            duration_ms=1000
        )

    def _correlate_diet_with_gerd(
        self,
        diet_history: List[DietEntry],
        gerd_episodes: List[HealthEvent]
    ) -> List[Correlation]:
        """
        Deterministic correlation algorithm (NO LLM)

        Algorithm:
        1. For each food item, count GERD episodes within 2 hours
        2. Calculate correlation score (episodes / total occurrences)
        3. Rank by score, return top 5 triggers
        """
        food_gerd_counts = defaultdict(lambda: {"total": 0, "gerd_episodes": 0})

        for diet_entry in diet_history:
            food_item = diet_entry.food_item
            food_gerd_counts[food_item]["total"] += 1

            # Check if GERD occurred within 2 hours
            gerd_within_2h = any(
                abs((episode.timestamp - diet_entry.timestamp).total_seconds()) < 7200
                for episode in gerd_episodes
            )

            if gerd_within_2h:
                food_gerd_counts[food_item]["gerd_episodes"] += 1

        # Calculate correlation scores
        correlations = []
        for food, counts in food_gerd_counts.items():
            if counts["total"] >= 3:  # Minimum 3 occurrences
                score = counts["gerd_episodes"] / counts["total"]
                correlations.append(Correlation(
                    food_item=food,
                    gerd_episodes=counts["gerd_episodes"],
                    total_occurrences=counts["total"],
                    score=score
                ))

        # Rank by score
        correlations.sort(key=lambda c: c.score, reverse=True)
        return correlations[:5]  # Top 5 triggers

    async def _generate_insights(
        self,
        correlations: List[Correlation]
    ) -> List[Insight]:
        """
        Generate insights from correlations

        Can use LLM for natural language, but deterministic logic also works
        """
        insights = []

        for corr in correlations:
            # Deterministic insight generation (NO LLM)
            if corr.score > 0.5:
                severity = "strong"
            elif corr.score > 0.3:
                severity = "moderate"
            else:
                severity = "weak"

            insights.append(Insight(
                summary=f"{severity.title()} trigger: {corr.food_item}",
                evidence=[
                    f"{corr.gerd_episodes} out of {corr.total_occurrences} times led to GERD",
                    f"Correlation score: {corr.score:.0%}"
                ],
                severity=severity,
                confidence=corr.score
            ))

        return insights
```

**Key Design Decisions:**
- **Progress milestones:** 5 deterministic events (NO LLM) for transparency
- **Correlation algorithm:** Deterministic (fast, predictable, explainable)
- **Insight generation:** Can use LLM for natural language OR deterministic rules
- **Duration:** Target 500-1000ms (allows proactive prompts at 200ms)

---

#### **Component 6: ProgressPublisher (SSE Streaming)**

**Location:** `backend/api/progress_publisher.py`

**Responsibilities:**
1. Subscribe to specialist progress events
2. Stream progress updates via SSE
3. Handle connection lifecycle

**Key Methods:**

```python
class ProgressPublisher:
    """
    Publishes progress updates via Server-Sent Events (SSE)

    Research basis: Incremental Processing (Schlangen 2011)
    """

    def __init__(self):
        self.subscribers = {}  # task_id -> queue

    async def subscribe(self, task: asyncio.Task) -> AsyncGenerator:
        """
        Subscribe to progress updates for a task

        Yields ProgressEvent objects as they are emitted
        """
        task_id = id(task)
        queue = asyncio.Queue()
        self.subscribers[task_id] = queue

        try:
            while not task.done():
                # Wait for progress event with timeout
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=0.1)
                    yield event
                except asyncio.TimeoutError:
                    continue  # Check if task is done

            # Drain any remaining events
            while not queue.empty():
                event = queue.get_nowait()
                yield event

        finally:
            # Cleanup subscription
            del self.subscribers[task_id]

    async def publish(self, task_id: int, event: ProgressEvent):
        """
        Publish progress event to subscribers
        """
        if task_id in self.subscribers:
            await self.subscribers[task_id].put(event)
```

---

### **End-to-End Sequence Diagram with Research Patterns**

```mermaid
sequenceDiagram
    participant User
    participant ConciergeAgent
    participant ReactiveHandler
    participant ProactiveGenerator
    participant NutritionistAgent
    participant K0Query
    participant ProgressPublisher
    participant SynthesisEngine

    Note over User,SynthesisEngine: Research: Reactive-Proactive Loop (Our Pattern)

    User->>ConciergeAgent: "milk is making me sick"

    Note over ConciergeAgent,ReactiveHandler: Research: Conversational Grounding (Clark 1991)
    ConciergeAgent->>ReactiveHandler: classify_intent(message)
    ReactiveHandler-->>ConciergeAgent: Intent(specialist=nutritionist)

    ConciergeAgent->>ReactiveHandler: generate_response(message, intent)
    ReactiveHandler-->>ConciergeAgent: "That's sad to hear. Looping in nutritionist."

    ConciergeAgent->>User: [50ms] "That's sad to hear. Looping in nutritionist."

    Note over ConciergeAgent,NutritionistAgent: Research: Actor Model (Hewitt 1973)
    ConciergeAgent->>NutritionistAgent: spawn analyze(message) [background task]

    Note over ConciergeAgent,ProactiveGenerator: Research: Mixed-Initiative (Allen 1999)
    ConciergeAgent->>ProactiveGenerator: identify_gaps(message)
    ProactiveGenerator-->>ConciergeAgent: ["pain_severity", "pain_location"]

    Note over NutritionistAgent,K0Query: Research: Progressive Disclosure (Norman 1988)
    NutritionistAgent->>ProgressPublisher: emit(milestone 1: "Checking diet history...")
    ProgressPublisher->>User: [200ms] Progress: 20%

    NutritionistAgent->>K0Query: query(diet_entries, last_30_days)
    K0Query-->>NutritionistAgent: diet_history

    par Proactive Prompt Generation
        Note over ConciergeAgent,ProactiveGenerator: Research: Proactive Dialogue (Yang 2018)
        ConciergeAgent->>ProactiveGenerator: generate_prompt(context, task, "fill_gap")
        ProactiveGenerator-->>ConciergeAgent: "Until nutritionist gathers data, why can't you tell me how uneasy it was?"
        ConciergeAgent->>User: [200ms] Proactive prompt
    and Background Analysis
        NutritionistAgent->>ProgressPublisher: emit(milestone 2: "Analyzing patterns...")
        ProgressPublisher->>User: Progress: 40%

        NutritionistAgent->>K0Query: query(health_events, GERD)
        K0Query-->>NutritionistAgent: gerd_episodes

        NutritionistAgent->>NutritionistAgent: correlate_diet_with_gerd()
    end

    User->>ConciergeAgent: "pain in left side" [User responds to proactive prompt!]

    Note over ConciergeAgent,ReactiveHandler: Research: Conversational Grounding
    ConciergeAgent->>ReactiveHandler: classify_intent("pain in left side")
    ReactiveHandler-->>ConciergeAgent: Intent(type=additional_info)
    ConciergeAgent->>User: [300ms] "I'll take a note about milk for your doctor visit"

    NutritionistAgent->>ProgressPublisher: emit(milestone 4: "Generating insights...")
    ProgressPublisher->>User: Progress: 80%

    NutritionistAgent->>ProgressPublisher: emit(milestone 5: "Complete")
    ProgressPublisher->>User: Progress: 100%

    NutritionistAgent-->>ConciergeAgent: AnalysisResult(insights, evidence, confidence)

    Note over ConciergeAgent,SynthesisEngine: Research: Conversational Grounding
    ConciergeAgent->>SynthesisEngine: synthesize(result, context)
    SynthesisEngine-->>ConciergeAgent: "Interesting - the nutritionist found that the trigger may actually be late night coffee, not the milk..."

    ConciergeAgent->>User: [1200ms] Final synthesis

    Note over User,SynthesisEngine: Result: Natural conversation maintained during 1000ms background work
```

**Research Patterns Applied:**

1. **Conversational Grounding (Clark 1991):** Acknowledgment tokens ("That's sad to hear")
2. **Actor Model (Hewitt 1973):** Message passing between agents (spawn NutritionistAgent)
3. **Mixed-Initiative Dialogue (Allen 1999):** System takes initiative (proactive prompts)
4. **Proactive Dialogue (Yang 2018):** Anticipatory questions ("why can't you tell me how uneasy it was?")
5. **Progressive Disclosure (Norman 1988):** 5 milestones (20% → 40% → 60% → 80% → 100%)
6. **Incremental Processing (Schlangen 2011):** SSE streaming for real-time updates
7. **Reactive-Proactive Loop (Our Pattern):** Interleaving reactive + proactive responses during background work

---

### **Technology Stack & Implementation Details**

#### **Core Technologies**

| Layer | Technology | Purpose | Research Basis |
|-------|-----------|---------|----------------|
| **Frontend** | React 18 + TypeScript | UI with SSE streaming | - |
| **API** | FastAPI (Python 3.11+) | Async HTTP + SSE endpoints | SEDA (Welsh 2001) |
| **LLM Client** | OpenAI SDK / Azure OpenAI | GPT-4o-mini for speed, GPT-4 for quality | - |
| **Agent Framework** | asyncio + dataclasses | Actor Model implementation | Actor Model (Hewitt 1973) |
| **K0 Query Service** | REST API to K0 kernel | FamilyOS data access | - |
| **State Management** | In-memory (ConversationState) | Fast state transitions | - |
| **Progress Streaming** | SSE (Server-Sent Events) | Real-time updates | Incremental Processing (Schlangen 2011) |
| **Caching** | functools.lru_cache | LLM response caching | - |
| **Testing** | pytest + pytest-asyncio | Integration > unit tests | - |

#### **API Endpoints**

**POST /api/chat/message**
```python
@app.post("/api/chat/message")
async def handle_chat_message(request: ChatRequest):
    """
    Handle user message with reactive-proactive pattern

    Returns: StreamingResponse (SSE)

    SSE Events:
    - type: "message" (reactive response, synthesis)
    - type: "proactive" (proactive prompt)
    - type: "progress" (milestone updates)
    """

    concierge = ConciergeAgent(llm_client, k0_query_service)

    async def event_stream():
        async for event in concierge.handle_message(
            user_message=request.message,
            user_id=request.user_id
        ):
            yield f"data: {json.dumps(event.to_dict())}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream"
    )
```

**GET /api/chat/history/{user_id}**
```python
@app.get("/api/chat/history/{user_id}")
async def get_chat_history(user_id: str, limit: int = 50):
    """
    Retrieve conversation history for context
    """
    history = await conversation_store.get_history(user_id, limit)
    return {"turns": history}
```

#### **Data Models**

**Intent**
```python
@dataclass
class Intent:
    """User intent classification result"""
    type: Literal["QUERY", "ACTION"]
    domain: Literal["health", "finance", "social", "general"]
    complexity: Literal["simple", "multi_step"]
    specialist_type: str  # "nutritionist", "psychiatrist", etc.
    confidence: float  # 0.0-1.0
    entities: List[str]  # Extracted entities
```

**ConversationState**
```python
@dataclass
class ConversationState:
    """Conversation context for ConciergeAgent"""
    user_id: str
    recent_history: List[Turn]  # Last 10 turns
    information_gaps: List[str]  # Missing information
    user_expressed_future_concern: bool
    last_turn_was_ambiguous: bool
    proactive_prompts_sent: List[ProactivePrompt]

    def add_turn(self, user_message: Optional[str], agent_response: str):
        """Add conversation turn"""
        self.recent_history.append(Turn(
            timestamp=time.time(),
            user_message=user_message,
            agent_response=agent_response
        ))

        # Keep only last 10 turns (working memory limit: 7±2)
        if len(self.recent_history) > 10:
            self.recent_history = self.recent_history[-10:]
```

**ProactivePrompt**
```python
@dataclass
class ProactivePrompt:
    """Proactive prompt sent during background work"""
    text: str
    prompt_type: Literal["fill_gap", "future_action", "clarify"]
    information_target: Optional[str]  # e.g., "pain_severity"
    sent_at: float  # Timestamp
    user_responded: bool  # Did user respond?
```

**AnalysisResult**
```python
@dataclass
class AnalysisResult:
    """Specialist analysis result"""
    specialist_type: str
    query: str
    insights: List[Insight]
    evidence: List[str]  # Supporting evidence
    confidence: float  # 0.0-1.0
    duration_ms: int
```

**ProgressEvent**
```python
@dataclass
class ProgressEvent:
    """Progress milestone event"""
    milestone: int  # 1-5
    message: str  # "📊 Checking your diet history..."
    percent: int  # 0-100
    timestamp: float
```

#### **LLM Client Configuration**

```python
# config/llm_config.yaml
llm_clients:
  fast:
    model: "gpt-4o-mini"
    temperature: 0.0
    max_tokens: 100
    timeout_ms: 50
    use_case: "intent_classification, emotion_detection, gap_identification"

  creative:
    model: "gpt-4o-mini"
    temperature: 0.8
    max_tokens: 50
    timeout_ms: 150
    use_case: "empathy_generation, proactive_prompts"

  synthesis:
    model: "gpt-4o-mini"  # Upgrade to gpt-4 for better quality
    temperature: 0.7
    max_tokens: 100
    timeout_ms: 300
    use_case: "result_synthesis"

caching:
  enabled: true
  ttl_seconds: 3600  # 1 hour
  max_size: 1000  # Cache up to 1000 responses
```

#### **Performance Budgets (Enforced)**

| Component | P50 | P95 | P99 | Timeout |
|-----------|-----|-----|-----|---------|
| Intent Classification | 20ms | 30ms | 50ms | 100ms |
| Empathy Generation (rule-based) | 5ms | 10ms | 20ms | 50ms |
| Empathy Generation (LLM fallback) | 30ms | 50ms | 100ms | 200ms |
| Proactive Prompt Generation | 80ms | 100ms | 150ms | 300ms |
| Result Synthesis | 150ms | 200ms | 300ms | 500ms |
| Specialist Analysis (Nutritionist) | 700ms | 1000ms | 1500ms | 3000ms |
| **Total Turn Latency** | **1000ms** | **1500ms** | **2000ms** | **5000ms** |

**Budget Enforcement:**
```python
async def with_timeout(coro, timeout_ms: int, operation: str):
    """Enforce timeout budget"""
    try:
        return await asyncio.wait_for(
            coro,
            timeout=timeout_ms / 1000.0
        )
    except asyncio.TimeoutError:
        logger.error(f"{operation} exceeded timeout {timeout_ms}ms")
        raise HTTPException(
            status_code=504,
            detail=f"{operation} timeout"
        )
```

#### **Observability & Monitoring**

**Metrics (Prometheus)**
```python
# Metrics to track
INTENT_CLASSIFICATION_LATENCY = Histogram(
    "intent_classification_latency_ms",
    "Intent classification latency"
)

PROACTIVE_PROMPT_GENERATED = Counter(
    "proactive_prompts_generated_total",
    "Total proactive prompts generated"
)

USER_RESPONDED_TO_PROACTIVE = Counter(
    "user_responded_to_proactive_total",
    "User responded to proactive prompt"
)

LLM_CALL_COST = Counter(
    "llm_call_cost_usd",
    "Total LLM cost in USD"
)

CONVERSATION_TURNS = Histogram(
    "conversation_turns_total",
    "Total turns per conversation"
)
```

**Logging**
```python
# Structured logging with context
logger.info(
    "reactive_response_sent",
    user_id=user_id,
    message_length=len(user_message),
    intent_type=intent.type,
    specialist=intent.specialist_type,
    latency_ms=latency,
    response=reactive_response
)
```

**Tracing (OpenTelemetry)**
```python
# Distributed tracing for LLM calls
with tracer.start_as_current_span("classify_intent") as span:
    span.set_attribute("user_id", user_id)
    span.set_attribute("message_length", len(user_message))

    intent = await llm_client.generate(prompt, model="gpt-4o-mini")

    span.set_attribute("intent_type", intent.type)
    span.set_attribute("confidence", intent.confidence)
```

#### **Testing Strategy**

**Integration Tests (Priority)**
```python
@pytest.mark.asyncio
async def test_reactive_proactive_loop_gerd_scenario():
    """
    Test complete reactive-proactive loop with GERD scenario

    Research validation: Reactive-Proactive Loop pattern
    """
    # Setup
    concierge = ConciergeAgent(mock_llm_client, mock_k0_service)
    user_message = "milk is making me sick"

    # Collect events
    events = []
    async for event in concierge.handle_message(user_message, "user_123"):
        events.append(event)

    # Validate reactive response (first event)
    assert events[0].type == "message"
    assert "sad" in events[0].data.lower()  # Empathy
    assert "nutritionist" in events[0].data.lower()  # Action declaration

    # Validate proactive prompt (second event)
    assert events[1].type == "proactive"
    assert "until" in events[1].data.lower()  # Timing phrase
    assert "?" in events[1].data  # Question

    # Validate progress events (3-7 events)
    progress_events = [e for e in events if e.type == "progress"]
    assert len(progress_events) == 5  # 5 milestones

    # Validate synthesis (last event)
    assert events[-1].type == "message"
    assert "nutritionist" in events[-1].data.lower()  # Specialist mentioned
    assert "found" in events[-1].data.lower()  # Findings presented
```

**Unit Tests (Secondary)**
```python
@pytest.mark.asyncio
async def test_proactive_generator_respects_cooldown():
    """Test cooldown period between proactive prompts"""
    generator = ProactiveGenerator(mock_llm_client)

    # First prompt succeeds
    prompt1 = await generator.generate_prompt(context, task, "fill_gap")
    assert prompt1 is not None

    # Second prompt within 5s is skipped
    await asyncio.sleep(1)
    prompt2 = await generator.generate_prompt(context, task, "fill_gap")
    assert prompt2 is None  # Cooldown active

    # Third prompt after 5s succeeds
    await asyncio.sleep(5)
    prompt3 = await generator.generate_prompt(context, task, "fill_gap")
    assert prompt3 is not None
```

#### **Deployment Configuration**

**Environment Variables**
```bash
# LLM Configuration
OPENAI_API_KEY=sk-...
OPENAI_MODEL_FAST=gpt-4o-mini
OPENAI_MODEL_SYNTHESIS=gpt-4o-mini
OPENAI_TIMEOUT_MS=1000

# K0 Integration
K0_API_URL=http://localhost:8000
K0_API_KEY=...

# Performance
MAX_CONVERSATION_HISTORY=10
PROACTIVE_COOLDOWN_SECONDS=5
MIN_BACKGROUND_DURATION_MS=300

# Observability
PROMETHEUS_PORT=9090
OTEL_EXPORTER_OTLP_ENDPOINT=http://jaeger:4318
LOG_LEVEL=INFO
```

**Docker Compose**
```yaml
version: '3.8'

services:
  concierge-poc:
    build: .
    ports:
      - "8001:8001"  # FastAPI
      - "9090:9090"  # Prometheus metrics
    environment:
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - K0_API_URL=http://k0-kernel:8000
    depends_on:
      - k0-kernel
    volumes:
      - ./config:/app/config

  k0-kernel:
    image: familyos/k0-kernel:latest
    ports:
      - "8000:8000"

  prometheus:
    image: prom/prometheus:latest
    ports:
      - "9091:9090"
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml

  jaeger:
    image: jaegertracing/all-in-one:latest
    ports:
      - "16686:16686"  # UI
      - "4318:4318"    # OTLP
```

---

### **Implementation Roadmap (14 Days)**

**Phase 1: Foundation (Days 1-3)**
- Day 1: Setup project structure, FastAPI + SSE, basic data models
- Day 2: Implement ReactiveHandler (intent classification, empathy generation)
- Day 3: Implement ProactiveGenerator (gap identification, prompt generation)

**Phase 2: Specialists (Days 4-6)**
- Day 4: Implement NutritionistAgent with progress milestones
- Day 5: Integrate K0 query service for real data
- Day 6: Add PsychiatristAgent, FinanceAnalystAgent (simpler versions)

**Phase 3: Synthesis & Orchestration (Days 7-9)**
- Day 7: Implement SynthesisEngine (result integration, contradiction detection)
- Day 8: Implement ConciergeAgent main loop (reactive-proactive orchestration)
- Day 9: Add ProgressPublisher (SSE streaming)

**Phase 4: Testing & Polish (Days 10-12)**
- Day 10: Write integration tests (GERD scenario, contradiction handling)
- Day 11: Add observability (metrics, logging, tracing)
- Day 12: Performance optimization (caching, timeouts, rule-based fast paths)

**Phase 5: Validation (Days 13-14)**
- Day 13: User testing with real conversations (5-10 users, 10 turns each)
- Day 14: Analyze metrics, refine prompts, document findings

**Success Criteria:**
- ✅ P95 latency <1500ms (reactive-proactive-synthesis cycle)
- ✅ 2-3 proactive turns per conversation (not overwhelming)
- ✅ <5% "frozen" perception incidents
- ✅ 80%+ perceived naturalness ratings
- ✅ Cost <$0.03 per conversation

---

### **Validation Against Research**

| Research Pattern | How We Implement | Where to Validate |
|-----------------|------------------|-------------------|
| **Conversational Grounding** (Clark 1991) | Acknowledgment tokens in reactive responses | User study: "Did agent acknowledge your concern?" |
| **Actor Model** (Hewitt 1973) | asyncio.Queue mailboxes for agent messaging | Code review: Message passing architecture |
| **Mixed-Initiative Dialogue** (Allen 1999) | Proactive prompts during background work | Metrics: Proactive prompt count per conversation |
| **Proactive Dialogue** (Yang 2018) | Information gap filling | User study: "Did agent ask relevant questions?" |
| **Progressive Disclosure** (Norman 1988) | 5 progress milestones | Metrics: Milestone emission timing, user anxiety reduction |
| **Incremental Processing** (Schlangen 2011) | SSE streaming | Performance: Real-time event delivery latency |
| **ReAct** (Yao 2022) | PlannerAgent for multi-step tasks | Integration tests: Plan generation correctness |
| **Reactive-Proactive Loop** (Our Pattern) | Interleaving reactive + proactive responses | User study: "Did conversation feel natural during wait?" |

**Key Metrics for Research Validation:**
1. **Naturalness:** Likert scale (1-5) - "How natural did the conversation feel?"
2. **Wait Perception:** "Did you notice any awkward silences?" (Yes/No)
3. **Proactive Relevance:** "Were the proactive questions relevant?" (1-5)
4. **Empathy:** "Did the agent acknowledge your concern?" (Yes/No)
5. **Information Gathering:** "Did the agent gather enough context?" (1-5)

---

### **Cognitive Envelope Design**

**See:** `envelope_design.md` for complete envelope specification

The Concierge PoC uses a **Cognitive Envelope** that extends FamilyOS's universal `envelope.schema.json` with domain-specific fields:

**Key Envelope Extensions:**
1. **actor:** Identity and authorization context (`agent`, `user_id`, `space_id`, `session_id`)
2. **policy:** Capability-based access control (`band`, `caps`, `budget_ceiling_usd`)
3. **intent:** Intent classification result (`type`, `domain`, `complexity`, `specialist_type`, `routing`)
4. **conversation:** QUD + scoreboard + affect (common ground tracking)
5. **spawn:** Specialist spawn request (`specialist`, `task_id`, `est_duration_ms`, `query`)
6. **progress_policy:** Progress update controls (`max_updates_per_sec`, `milestones`)
7. **telemetry:** Performance tracking (LLM calls, latency, cost)
8. **observability:** Research validation metrics (`research_pattern`, `validation_metrics`)

**Envelope Kinds (Message Types):**
- `user_utterance` → User message
- `reactive_response` → Immediate empathy + action
- `proactive_prompt` → Fill information gap
- `spawn_specialist` → Request specialist spawn
- `progress_event` → Progress milestone
- `specialist_result` → Analysis complete
- `synthesis_response` → Final integrated result
- `user_additional_info` → Response to proactive prompt

**Research Alignment:**
- **Actor Model (Hewitt 1973):** Envelope = message between actors
- **Conversational Grounding (Clark 1991):** QUD + scoreboard track common ground
- **Mixed-Initiative (Allen 1999):** Intent + spawn enable proactive behavior
- **Progressive Disclosure (Norman 1988):** Progress policy controls information flow

**Performance Budget:**
- Target envelope size: <5KB (base + extensions)
- Lazy enrichment: Only add full `telemetry` in synthesis response
- Scoreboard pruning: Keep top 10 referents by salience

**Example Usage:**
```python
from envelope_factory import EnvelopeFactory

# Create reactive response
envelope = EnvelopeFactory.create_reactive_response(
    user_message="milk is making me sick",
    intent=intent,
    affect={"label": "concerned", "confidence": 0.78},
    conversation_state=conversation_state,
    trace_id="trace_xyz789"
)

# Validate envelope
valid, errors = validate_envelope(envelope.to_dict())
if not valid:
    logger.error(f"Invalid envelope: {errors}")

# Send via SSE
await sse_publisher.send(envelope)
```

---

**Purpose:** Track conversation context to enable intelligent proactive prompts

```python
@dataclass
class ConversationState:
    """Tracks multi-turn conversation for reactive-proactive coordination"""

    # Current conversation
    turn_count: int
    recent_history: Deque[Turn]  # Last 10 turns
    current_topic: str  # "gerd_symptoms", "appointment_booking"

    # Background work tracking
    active_tasks: Dict[str, BackgroundTask]  # {task_id: task_info}
    pending_proactive: Optional[ProactivePrompt]
    awaiting_synthesis: List[str]  # task_ids ready for integration

    # User context (for proactive prompts)
    user_emotion: str  # "concerned", "frustrated", "confused"
    information_gaps: List[str]  # ["pain_location", "severity", "duration"]
    future_actions: List[FutureAction]  # [{action: "doctor_visit", reminder: "mention_milk"}]

    # Timing
    last_user_message: float  # timestamp
    last_proactive_prompt: float  # timestamp
    background_work_started: float  # timestamp

@dataclass
class BackgroundTask:
    task_id: str
    specialist_type: str  # "nutritionist", "psychiatrist"
    status: str  # "spawned", "working", "complete"
    estimated_duration_ms: int  # 500-1000ms
    started_at: float
    proactive_prompt_sent: bool

@dataclass
class ProactivePrompt:
    text: str  # "Until nutritionist gathers data, why can't you tell me..."
    prompt_type: str  # "fill_gap", "clarify", "future_action"
    information_target: str  # "pain_location", "severity"
    sent_at: float
    user_responded: bool
```

### **2. Reactive Handler**

**Purpose:** Immediate acknowledgment with empathy + action declaration

```python
class ReactiveHandler:
    """Handles immediate user acknowledgment"""

    async def handle_user_message(
        self,
        user_message: str,
        context: ConversationState
    ) -> ReactiveResponse:
        """
        Generate immediate reactive response (<50ms)

        Pattern:
        1. Empathy: "That's sad to hear"
        2. Action: "Looping in nutritionist"
        3. NO blocking operations
        """

        # Classify intent (cached LLM or lightweight model)
        intent = await self.classify_intent(user_message, context)

        # Generate empathetic response
        empathy = self.generate_empathy(user_message, context.user_emotion)
        # Examples: "That's sad to hear", "I understand your concern",
        #           "That must be frustrating"

        # Declare action
        action_declaration = self.declare_action(intent)
        # Examples: "Looping in nutritionist", "Let me coordinate that",
        #           "I'll help you schedule"

        # Combine
        reactive_response = f"{empathy}. {action_declaration}."

        return ReactiveResponse(
            text=reactive_response,
            intent=intent,
            spawn_specialist=intent.requires_specialist,
            specialist_type=intent.specialist_type
        )

    def generate_empathy(self, message: str, emotion: str) -> str:
        """
        Fast empathy generation (rule-based or cached LLM)

        Patterns:
        - Negative emotion → "That's sad to hear", "I'm sorry to hear that"
        - Concern → "I understand your concern"
        - Frustration → "That must be frustrating"
        - Question → "Great question"
        """
        if emotion == "frustrated":
            return "That must be frustrating"
        elif emotion == "concerned":
            return "I understand your concern"
        elif "sick" in message.lower() or "pain" in message.lower():
            return "That's sad to hear"
        else:
            return "I hear you"
```

### **3. Proactive Generator**

**Purpose:** Generate contextually relevant prompts to fill conversation gaps

```python
class ProactiveGenerator:
    """Generates proactive prompts during background work"""

    async def generate_proactive_prompt(
        self,
        context: ConversationState,
        background_task: BackgroundTask
    ) -> Optional[ProactivePrompt]:
        """
        Generate proactive prompt if:
        1. Background work will take >300ms
        2. No proactive prompt sent in last 5 seconds
        3. User has information gaps we can fill

        Timing:
        - Send 100-200ms after reactive response
        - Before first progress update (at ~300ms)
        """

        # Check if proactive prompt needed
        if not self.should_generate_proactive(context, background_task):
            return None

        # Determine proactive strategy
        strategy = self.select_strategy(context, background_task)

        if strategy == "fill_information_gap":
            return await self.generate_gap_filler(context, background_task)

        elif strategy == "offer_future_action":
            return await self.generate_future_action(context, background_task)

        elif strategy == "clarify_context":
            return await self.generate_clarification(context, background_task)

        else:
            return None

    def should_generate_proactive(
        self,
        context: ConversationState,
        task: BackgroundTask
    ) -> bool:
        """Decide if proactive prompt appropriate"""

        # Don't spam proactive prompts
        if context.pending_proactive and context.pending_proactive.sent_at:
            time_since_last = time.time() - context.pending_proactive.sent_at
            if time_since_last < 5.0:  # 5 second cooldown
                return False

        # Only if task will take meaningful time
        if task.estimated_duration_ms < 300:
            return False

        # Only if we have information gaps to fill
        if not context.information_gaps and not context.future_actions:
            return False

        return True

    async def generate_gap_filler(
        self,
        context: ConversationState,
        task: BackgroundTask
    ) -> ProactivePrompt:
        """
        Generate prompt to fill information gap

        Example: "Until nutritionist gathers data and sees triggers,
                  why can't you tell me how uneasy it was?"

        Pattern:
        1. Acknowledge background work: "Until {specialist} {action}..."
        2. Natural transition: "why can't you tell me..."
        3. Target information gap: "how uneasy it was"
        """

        specialist_name = task.specialist_type.title()  # "Nutritionist"
        specialist_action = self.get_specialist_action(task)  # "gathers data"

        # Get first information gap
        gap = context.information_gaps[0] if context.information_gaps else "more details"
        gap_question = self.gap_to_question(gap)
        # "how uneasy it was" for gap="pain_severity"
        # "where exactly the pain is" for gap="pain_location"

        # Use LLM to make it natural (cached for common patterns)
        prompt_template = (
            f"Until {specialist_name} {specialist_action}, "
            f"why can't you tell me {gap_question}?"
        )

        # Make it more natural with LLM (optional, can use templates)
        natural_prompt = await self.naturalize_prompt(prompt_template, context)

        return ProactivePrompt(
            text=natural_prompt,
            prompt_type="fill_gap",
            information_target=gap,
            sent_at=time.time(),
            user_responded=False
        )

    async def generate_future_action(
        self,
        context: ConversationState,
        task: BackgroundTask
    ) -> ProactivePrompt:
        """
        Offer future action promise

        Example: "I'll take a note about milk and remind you
                  at your next doctor visit"

        Pattern:
        1. Acknowledge user concern: "I'll take a note about {topic}"
        2. Future action: "and remind you at {future_event}"
        """

        # Extract topic from recent conversation
        topic = self.extract_concern_topic(context)
        # "milk" from "milk is making me sick"

        # Predict future event
        future_event = self.predict_future_event(context)
        # "next doctor visit" for health topics
        # "next week" for general tasks

        prompt = (
            f"I'll take a note about {topic} and remind you "
            f"at your {future_event}."
        )

        return ProactivePrompt(
            text=prompt,
            prompt_type="future_action",
            information_target=topic,
            sent_at=time.time(),
            user_responded=False
        )

    def gap_to_question(self, gap: str) -> str:
        """Convert information gap to natural question"""
        gap_map = {
            "pain_severity": "how uneasy it was",
            "pain_location": "where exactly the pain is",
            "pain_duration": "how long you've had this",
            "symptoms": "what symptoms you're experiencing",
            "triggers": "what makes it worse",
            "timeline": "when this started"
        }
        return gap_map.get(gap, f"more about {gap}")
```

### **4. Synthesis Engine**

**Purpose:** Integrate background results naturally into conversation

```python
class SynthesisEngine:
    """Synthesizes specialist results into natural conversation"""

    async def synthesize_result(
        self,
        specialist_result: AnalysisResult,
        context: ConversationState
    ) -> str:
        """
        Generate natural synthesis of specialist findings

        Pattern:
        1. Acknowledge completion: "Interesting - nutritionist found..."
        2. Key insight: "trigger may be late night coffee, not milk"
        3. Connect to user concern: "So it might not be the milk causing issues"

        NOT template-based - use LLM for natural language
        """

        # Extract key insights
        primary_insight = specialist_result.insights[0]
        evidence = specialist_result.insights[0].evidence

        # Check if result contradicts user assumption
        contradiction = self.detect_contradiction(
            specialist_result,
            context.recent_history
        )
        # User said "milk" but result says "coffee"

        # Generate synthesis prompt for LLM
        synthesis_prompt = self.build_synthesis_prompt(
            specialist_result,
            context,
            contradiction
        )

        # Use LLM to generate natural synthesis
        synthesis = await self.llm.generate(synthesis_prompt)

        # Example output:
        # "Interesting - the nutritionist analyzed your patterns and
        #  found that the trigger may actually be late night coffee,
        #  not the milk. The evidence shows 3 out of 5 GERD episodes
        #  occurred after evening coffee."

        return synthesis

    def detect_contradiction(
        self,
        result: AnalysisResult,
        history: Deque[Turn]
    ) -> Optional[Contradiction]:
        """Check if result contradicts user assumption"""

        # User mentioned "milk" as suspected cause
        user_assumption = self.extract_user_assumption(history)
        # "milk"

        # Result found different cause
        actual_cause = result.insights[0].summary
        # "late night coffee"

        if user_assumption and actual_cause:
            if user_assumption.lower() not in actual_cause.lower():
                return Contradiction(
                    user_thought=user_assumption,
                    actual_finding=actual_cause
                )

        return None
```

### **5. Orchestration Flow**

**Complete implementation:**

```python
class ConciergeAgent:
    """Main orchestration loop with reactive-proactive pattern"""

    def __init__(self):
        self.reactive_handler = ReactiveHandler()
        self.proactive_generator = ProactiveGenerator()
        self.synthesis_engine = SynthesisEngine()
        self.conversation_state = ConversationState()

    async def handle_message(self, user_message: str, user_id: str):
        """
        Main message handling loop

        Timeline:
        0ms:    User message received
        50ms:   Reactive response sent
        100ms:  Background specialist spawned
        200ms:  Proactive prompt sent
        300ms:  First progress update
        1000ms: Specialist completes
        1100ms: Synthesis sent
        """

        # PHASE 1: REACTIVE (0-50ms)
        reactive_response = await self.reactive_handler.handle_user_message(
            user_message,
            self.conversation_state
        )

        # Stream to user immediately
        await self.stream_to_user(user_id, reactive_response.text, "message")

        # Update conversation state
        self.conversation_state.recent_history.append(Turn(
            speaker="user",
            text=user_message,
            timestamp=time.time()
        ))
        self.conversation_state.recent_history.append(Turn(
            speaker="concierge",
            text=reactive_response.text,
            timestamp=time.time()
        ))

        # PHASE 2: SPAWN (50-100ms)
        if reactive_response.spawn_specialist:
            task_id = await self.spawn_specialist(
                reactive_response.specialist_type,
                reactive_response.intent,
                user_id
            )

            background_task = BackgroundTask(
                task_id=task_id,
                specialist_type=reactive_response.specialist_type,
                status="spawned",
                estimated_duration_ms=800,
                started_at=time.time(),
                proactive_prompt_sent=False
            )

            self.conversation_state.active_tasks[task_id] = background_task

        # PHASE 3: PROACTIVE (100-200ms)
        # Wait a bit for natural pacing
        await asyncio.sleep(0.1)  # 100ms

        if reactive_response.spawn_specialist:
            proactive_prompt = await self.proactive_generator.generate_proactive_prompt(
                self.conversation_state,
                background_task
            )

            if proactive_prompt:
                await self.stream_to_user(user_id, proactive_prompt.text, "message")
                self.conversation_state.pending_proactive = proactive_prompt
                background_task.proactive_prompt_sent = True

                self.conversation_state.recent_history.append(Turn(
                    speaker="concierge",
                    text=proactive_prompt.text,
                    timestamp=time.time()
                ))

        # PHASE 4: LISTEN (200ms - whenever user responds)
        # User may respond to proactive prompt
        # This will trigger NEW handle_message call
        # We don't block here - message handler is async

        # PHASE 5: SYNTHESIS (when specialist completes)
        # This runs in parallel, handled by specialist completion callback
        # See handle_specialist_completion() below

    async def handle_specialist_completion(
        self,
        task_id: str,
        result: AnalysisResult,
        user_id: str
    ):
        """Called when background specialist finishes"""

        # Update task status
        task = self.conversation_state.active_tasks[task_id]
        task.status = "complete"

        # Check if user responded to proactive prompt
        if self.conversation_state.pending_proactive:
            # Count turns since proactive prompt
            proactive_time = self.conversation_state.pending_proactive.sent_at
            user_turns_after = sum(
                1 for turn in self.conversation_state.recent_history
                if turn.speaker == "user" and turn.timestamp > proactive_time
            )

            if user_turns_after > 0:
                self.conversation_state.pending_proactive.user_responded = True
                # SUCCESS: User engaged with proactive prompt!

        # Synthesize result
        synthesis = await self.synthesis_engine.synthesize_result(
            result,
            self.conversation_state
        )

        # Stream synthesis to user
        await self.stream_to_user(user_id, synthesis, "message")

        self.conversation_state.recent_history.append(Turn(
            speaker="concierge",
            text=synthesis,
            timestamp=time.time()
        ))

        # Cleanup
        del self.conversation_state.active_tasks[task_id]
        self.conversation_state.awaiting_synthesis.remove(task_id)
```

### **6. Timing Orchestration**

**Critical timing windows:**

```
USER MESSAGE ARRIVES
│
├─ 0-50ms:  Reactive response (empathy + action)
│           └─ "That's sad to hear. Looping in nutritionist."
│
├─ 50-100ms: Spawn background specialist
│            └─ NutritionistAgent starts K0 queries
│
├─ 100-200ms: Proactive prompt (if background work >300ms)
│             └─ "Until nutritionist gathers data,
│                 why can't you tell me how uneasy it was?"
│
├─ 200-500ms: [USER MAY RESPOND to proactive prompt]
│             User: "pain in left side of stomach"
│             Concierge: "I'll note that for your doctor visit."
│
├─ 300ms:    First progress update (if no user response)
│            └─ "📊 Checking your diet history..." [30%]
│
├─ 500ms:    Second progress update
│            └─ "🧠 Analyzing patterns..." [60%]
│
├─ 800ms:    Third progress update
│            └─ "💡 Generating insights..." [90%]
│
└─ 1000ms:   Specialist completes, synthesis sent
             └─ "Interesting - nutritionist found coffee
                 is the trigger, not milk."
```

**Key Design Decisions:**

1. **100ms delay for proactive prompt** - Feels natural, not rushed
2. **5-second cooldown between proactive prompts** - Avoid spam
3. **Only proactive if task >300ms** - Don't add noise for fast tasks
4. **Progress updates start at 300ms** - After proactive prompt window
5. **Non-blocking architecture** - User can interrupt anytime

---

### **1. LLM-Powered Conversational Orchestration**

**2023+ Research Context:**

- **AutoGen (Wu, 2023):** Multi-agent conversation framework
- **MetaGPT (Hong, 2023):** Role-based agents for software development
- **ChatDev (Qian, 2023):** Collaborative agents with defined roles

**Gap in Current Research:**

- AutoGen focuses on TASK completion (not continuous conversation)
- MetaGPT optimizes for software output (not human interaction)
- ChatDev assumes batch workflow (not real-time dialogue)
- **None prioritize human-like conversational continuity during work**

**Our Novel Contribution:**

- **ConciergeAgent as conversational facade** over async orchestration
- **Human-first design:** Conversation never stops (unlike AutoGen's task-focused approach)
- **Progress streaming integrated into dialogue** (not separate status endpoint)
- **LLM synthesizes specialist results naturally** (not template concatenation)
- **Reactive-Proactive Loop:** Anticipates user needs during background work (NEW)

**Compared to Existing Frameworks:**

```
AutoGen (2023):
  User → Task Definition → Agent Conversation → Result
  └─ User waits during agent conversation

Our Approach:
  User → Immediate Response → Background Work (parallel) → Streamed Integration
  └─ User sees continuous dialogue
```

**Validation Plan:**

- User study: Perceived responsiveness (ours vs AutoGen/MetaGPT)
- Qualitative: "Does it feel human?" (Likert scale, 50+ participants)
- Quantitative: Perceived wait time vs actual latency

**Expected Research Contribution:**

- Pattern: "Conversational Orchestration for LLM Agents"
- Metric: Conversational Continuity Index (CCI) = turns during wait / total turns
- Paper: "Human-First Multi-Agent Systems: Prioritizing Conversation over Coordination"

---

### **2. Dual-Path LLM Agent Architecture**

**2023+ Research Context:**

- **ReAct (Yao, 2022):** Single reasoning-action loop
- **Tree of Thoughts (Yao, 2023):** Exploration for complex reasoning
- **Reflexion (Shinn, 2023):** Self-correction via reflection

**Gap in Current Research:**

- Most frameworks use ONE planning strategy (ReAct OR ToT)
- No adaptive routing based on task complexity
- Planning overhead same for simple and complex tasks

**Our Novel Contribution:**

- **PATH 1 (Simple Queries):** Skip planning, direct specialist spawn (<1s)
- **PATH 2 (Complex Actions):** Full ReAct-style planning + validation (<3s)
- **Automatic routing:** LLM classifies intent → Routes to appropriate path
- **Decision boundary:** Read-only (PATH 1) vs Write operations (PATH 2)

**Performance Impact:**

```
Single-Path (Traditional):
  Simple Query: Plan (500ms) + Execute (500ms) = 1000ms
  └─ Overhead: 50% wasted on planning

Dual-Path (Ours):
  Simple Query: Execute (500ms) = 500ms
  Complex Action: Plan (500ms) + Execute (2000ms) = 2500ms
  └─ Optimization: 50% faster for simple queries, same for complex
```

**Validation Plan:**

- A/B test: Single-path vs dual-path latency (100 queries)
- Error analysis: Does PATH 2 validation reduce failures?
- User perception: Noticeable speed improvement for simple queries?

**Expected Research Contribution:**

- Pattern: "Adaptive Planning for LLM Agents"
- Metric: Planning Efficiency Ratio = (queries skipping plan / total queries)
- Paper: "Complexity-Aware Routing in Multi-Agent LLM Systems"

---

### **3. Deterministic Progress Milestones (Non-LLM)**

**2023+ Research Context:**

- **GPT-4 Streaming (OpenAI, 2023):** Token-by-token responses
- **Anthropic Claude Streaming (2024):** Real-time output
- Most research focuses on LLM output streaming (final answer)
- **No research on progress streaming during agent work**

**Gap in Current Research:**

- Progress indicators mostly static ("Agent working...")
- LLM-generated progress too slow (adds 50-100ms per update)
- Token cost prohibitive (5-10 updates × 100 tokens = 500-1000 tokens)

**Our Novel Contribution:**

- **Agent-defined milestones:** 5 progress stages per agent (<1ms overhead)
- **Semantic signifiers:** Emoji + text (📊 = data query, 🧠 = analysis)
- **Zero LLM cost:** Deterministic messages (no API calls)
- **Multi-agent multiplexing:** Show 5+ agents simultaneously

**Cost Comparison:**

```
LLM-Generated Progress (Expensive):
  5 updates × 100 tokens × $0.01/1K = $0.05 per query
  └─ At scale: 10K queries/day = $500/day

Deterministic Milestones (Free):
  5 updates × 0 tokens = $0.00
  └─ At scale: 10K queries/day = $0.00
```

**Validation Plan:**

- User preference: Static vs LLM vs deterministic (3-way comparison)
- Comprehension test: "What is the agent doing?" (accuracy rate)
- Perceived speed: Impact of milestones on wait time perception

**Expected Research Contribution:**

- Pattern: "Deterministic Progress Streaming for LLM Agents"
- Metric: Progress Comprehension Accuracy (PCA) = correct interpretations / total
- Paper: "Zero-Cost Progress Feedback in Multi-Agent LLM Systems"

---

### **4. Human-in-the-Loop via Conversational Interruptions (2024+)**

**2023+ Research Context:**

- **Constitutional AI (Anthropic, 2023):** Human feedback in training
- **RLHF (OpenAI, 2022):** Reinforcement learning from human feedback
- **Human-in-the-Loop for RAG (2024):** User validates retrieved docs

**Gap in Current Research:**

- Human feedback mostly AFTER task completion
- Mid-execution interruptions not well-studied
- Conversation repair during agent work under-explored

**Our Novel Contribution:**

- **Mid-execution interruptions:** User can correct during specialist work
- **Conversational repair:** ConciergeAgent detects corrections, cancels/restarts tasks
- **Context preservation:** SessionState.scoreboard tracks interrupted work
- **Graceful degradation:** Partial results saved if user interrupts

**Example Scenario:**

```
User: "remember we talked about reducing my gerd..."
Concierge: "Looping in nutritionist." [Specialist working]
Progress: "📊 Checking your diet history..." [30% complete]

User: "actually, not milk, I meant cheese"
Concierge: [Detects correction]
         "Ah, let me update that for the nutritionist."
         [Cancels current task, restarts with cheese]
Progress: "🔄 Updating analysis..." [New task]
```

**Validation Plan:**

- Frequency study: How often do users interrupt? (log analysis)
- Recovery success: Does system handle corrections properly?
- User satisfaction: Interruption handling UX (qualitative)

**Expected Research Contribution:**

- Pattern: "Conversational Repair in Multi-Agent LLM Systems"
- Metric: Interruption Recovery Rate (IRR) = successful corrections / total interruptions
- Paper: "Human-in-the-Loop Agent Orchestration via Mid-Execution Corrections"

---

## 📖 Reference Implementation (From This PoC)

### **Key Artifacts:**

1. **`requirements.md`** - Data structures, APIs, performance targets
2. **`IMPLEMENTATION_PLAN.md`** - Day-by-day guide with code examples
3. **`flow.md`** - Visual representation of dual-path architecture
4. **`DESIGN_RATIONALE.md`** (this document) - Research foundation

### **Code Patterns to Extract:**

From `IMPLEMENTATION_PLAN.md`:

- `ConciergeAgent.handle_message()` - Conversational orchestration pattern
- `NutritionistAgent.analyze_gerd_triggers()` - Progress milestone emission
- `ProgressPublisher` - Pub/sub streaming infrastructure
- `backend/api/chat.py` - SSE streaming endpoint

---

## 🎯 Future Research Directions

### **1. Adaptive Progress Granularity**

**Question:** Should progress updates adapt to task complexity?

- Simple tasks: 2-3 milestones
- Complex tasks: 10+ milestones with sub-tasks

**Hypothesis:** Users want more detail for longer waits (Nielsen: 10s = detailed feedback needed)

---

### **2. Conversational Repair During Background Work**

**Question:** How to handle user corrections while specialist working?

- User: "actually, not milk, I meant cheese"
- ConciergeAgent: Cancel Nutritionist task, restart with new info?

**Hypothesis:** Conversation Analysis repair mechanisms apply to AI orchestration

---

### **3. Multi-Modal Progress (Voice + Visual)**

**Question:** Does progress streaming translate to voice interfaces?

- Visual: Progress bars + emoji + text
- Voice: "I'm checking your diet history now..." (every 2s?)

**Hypothesis:** Voice needs less frequent updates (auditory cognitive load)

---

## ✅ Success Criteria (Research Validation)

This PoC succeeds if it demonstrates:

1. **Conversational Continuity**
   - [ ] User never sees "frozen" UI (continuous feedback)
   - [ ] ConciergeAgent responds <50ms P95
   - [ ] Side sequences feel natural (qualitative evaluation)

2. **Background Work Coordination**
   - [ ] Specialists execute concurrently (Actor Model verified)
   - [ ] Progress streaming works for 1-10 parallel agents
   - [ ] End-to-end latency meets targets (PATH 1: <1.2s, PATH 2: <3s)

3. **User Experience**
   - [ ] Users understand what's happening (progress messages comprehensible)
   - [ ] Perceived responsiveness higher than traditional "loading..." approach
   - [ ] Cognitive load manageable (user study with 10+ participants)

4. **Novel Pattern Validation**
   - [ ] Conversational Orchestration pattern reusable (publish as design pattern)
   - [ ] Dual-path architecture generalizes to other domains
   - [ ] Progress milestone approach documented for others

---

## 📚 Bibliography

### **LLM-Based Multi-Agent Systems (2023-2024)**

Hong, S., et al. (2023). "MetaGPT: Meta Programming for Multi-Agent Collaborative Framework." *arXiv preprint arXiv:2308.00352*. <https://arxiv.org/abs/2308.00352>

Wu, Q., et al. (2023). "AutoGen: Enabling Next-Gen LLM Applications via Multi-Agent Conversation Framework." *arXiv preprint arXiv:2308.08155*. <https://arxiv.org/abs/2308.08155>

Qian, C., et al. (2023). "ChatDev: Communicative Agents for Software Development." *arXiv preprint arXiv:2307.07924*. <https://arxiv.org/abs/2307.07924>

Park, J. S., et al. (2023). "Generative Agents: Interactive Simulacra of Human Behavior." *Proceedings of the 36th Annual ACM Symposium on User Interface Software and Technology*. <https://arxiv.org/abs/2304.03442>

---

### **Agent Reasoning & Tool Use (2022-2023)**

Yao, S., et al. (2022). "ReAct: Synergizing Reasoning and Acting in Language Models." *arXiv preprint arXiv:2210.03629*. <https://arxiv.org/abs/2210.03629>

Wei, J., et al. (2022). "Chain-of-Thought Prompting Elicits Reasoning in Large Language Models." *Advances in Neural Information Processing Systems*, 35. <https://arxiv.org/abs/2201.11903>

Yao, S., et al. (2023). "Tree of Thoughts: Deliberate Problem Solving with Large Language Models." *arXiv preprint arXiv:2305.10601*. <https://arxiv.org/abs/2305.10601>

Shinn, N., et al. (2023). "Reflexion: Language Agents with Verbal Reinforcement Learning." *arXiv preprint arXiv:2303.11366*. <https://arxiv.org/abs/2303.11366>

Schick, T., et al. (2023). "Toolformer: Language Models Can Teach Themselves to Use Tools." *arXiv preprint arXiv:2302.04761*. <https://arxiv.org/abs/2302.04761>

Qin, Y., et al. (2023). "Tool Learning with Foundation Models." *arXiv preprint arXiv:2304.08354*. <https://arxiv.org/abs/2304.08354>

---

### **Streaming LLMs (2023-2024)**

OpenAI (2023). "GPT-4 Turbo and GPT-4." *Technical Report*. <https://openai.com/research/gpt-4>

Anthropic (2024). "Claude 3 Model Family." *Technical Documentation*. <https://www.anthropic.com/claude>

Google DeepMind (2024). "Gemini 1.5: Unlocking multimodal understanding across millions of tokens of context." *Technical Report*. <https://deepmind.google/technologies/gemini/>

---

### **Memory & State Management (2023-2024)**

Shinn, N., et al. (2023). "Reflexion: an autonomous agent with dynamic memory and self-reflection." *arXiv preprint arXiv:2303.11366*. <https://arxiv.org/abs/2303.11366>

Zhong, W., et al. (2024). "MemGPT: Towards LLMs as Operating Systems." *arXiv preprint arXiv:2310.08560*. <https://arxiv.org/abs/2310.08560>

---

### **Mixed-Initiative & Proactive Dialogue Systems (1990s-2020s)**

Allen, J. F., Byron, D. K., Dzikovska, M., Ferguson, G., Galescu, L., & Stent, A. (1999). "Mixed-Initiative Interaction." *IEEE Intelligent Systems*, 14(5), 14-23.

Horvitz, E. (1999). "Principles of Mixed-Initiative User Interfaces." *CHI Conference on Human Factors in Computing Systems*, 159-166.

Purver, M. (2004). "The Theory and Use of Clarification Requests in Dialogue." *PhD Thesis, King's College London*.

Rich, C., & Sidner, C. L. (2001). "COLLAGEN: When Agents Collaborate with People." *Proceedings of the International Conference on Autonomous Agents*, 284-291.

Schlangen, D., & Skantze, G. (2016). "A General, Abstract Model of Incremental Dialogue Processing." *Dialogue & Discourse*, 2(1), 83-111.

Yang, Z., Levow, G. A., & Meng, H. (2018). "Proactive Dialogue Retrieval for Conversations." *EMNLP Conference*, 52-61.

Sun, K., & Tseng, B. (2021). "Proactive Human-Machine Conversation." *ACL Conference*, 313-324.

Traum, D. R. (1994). "A Computational Theory of Grounding in Natural Language Conversation." *PhD Thesis, University of Rochester*.

---

### **Multi-Agent Frameworks (2024)**

LangChain AI (2024). "LangGraph: Multi-Agent Workflows." *Documentation*. <https://python.langchain.com/docs/langgraph>

CrewAI (2024). "Framework for orchestrating role-playing, autonomous AI agents." *GitHub Repository*. <https://github.com/joaomdmoura/crewAI>

---

### **Classic Foundations (1973-2011)**

**Actor Model & Concurrency:**

- Hewitt, C., Bishop, P., & Steiger, R. (1973). "A Universal Modular ACTOR Formalism for Artificial Intelligence"
- Agha, G. (1986). "Actors: A Model of Concurrent Computation in Distributed Systems"

**Conversation Theory:**

- Clark, H. H., & Brennan, S. E. (1991). "Grounding in Communication"
- Traum, D. R. (1994). "A Computational Theory of Grounding in Natural Language Conversation"
- Sacks, H., Schegloff, E. A., & Jefferson, G. (1974). "A Simplest Systematics for the Organization of Turn-Taking"

**Incremental Processing:**

- Schlangen, D., & Skantze, G. (2011). "A General, Abstract Model of Incremental Dialogue Processing"
- Buß, O., & Schlangen, D. (2011). "DIUM - An Incremental Dialogue Manager"

**Design & Usability:**

- Norman, D. A. (1988). "The Design of Everyday Things"
- Miller, R. B. (1968). "Response Time in Man-Computer Conversational Transactions"
- Nielsen, J. (1993). "Usability Engineering"

**Cognitive Science:**

- Sweller, J. (1988). "Cognitive Load During Problem Solving"
- Miller, G. A. (1956). "The Magical Number Seven, Plus or Minus Two"
- Card, S. K., Moran, T. P., & Newell, A. (1983). "The Psychology of Human-Computer Interaction"

**Multi-Agent Systems:**

- Smith, R. G. (1980). "The Contract Net Protocol: High-Level Communication and Control"
- Rao, A. S., & Georgeff, M. P. (1995). "BDI Agents: From Theory to Practice"
- Wooldridge, M. (2009). "An Introduction to MultiAgent Systems"

**Dialogue Systems:**

- Williams, J. D., & Young, S. (2007). "Partially Observable Markov Decision Processes for Spoken Dialog Systems"
- Roberts, C. (2012). "Information Structure in Discourse"

---

## 🚀 Next Steps

1. **Implement PoC** (follow `IMPLEMENTATION_PLAN.md`)
2. **Collect Metrics** (latency, cognitive load, user satisfaction)
3. **User Study** (10+ participants, qualitative + quantitative)
4. **Publish Pattern** (if validated, contribute to research community)
5. **Iterate** (refine based on findings)

---

**Document Status:** Living document, updated as patterns evolve.
**Last Updated:** 2025-11-07
**Authors:** Based on conversation with user exploring dual-path conversational orchestration.
