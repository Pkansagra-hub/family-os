# Dynamic Agent Spawning Architecture - Conceptual Summary

## The Pattern You Described

### Core Concept
**Agents are spawned on-demand for specific tasks**, not pre-built. The system generates specialized agents dynamically based on task requirements.

---

## Flow: From Task to Agent Execution

```
USER REQUEST
   ↓
Concierge (Intent Router)
   ├─ Classification: "query" | "planning"
   ├─ Extract: domain, action keywords
   └─ Route to Orchestrator

ORCHESTRATOR PHASE 1-2 (Agent Selection)
   ↓
Orchestrator Phase 3 (Dynamic Agent Spawning)
   ├─ Determine agent_type needed
   │   Example: "book restaurant" → TicketBookingAgent
   │            "search weather"   → WebSearchAgent
   │
   ├─ CHECK AGENT ROSTER
   │   Is TicketBookingAgent already ACTIVE?
   │   ├─ YES: Use existing agent (REUSE)
   │   └─ NO: Proceed to spawn
   │
   ├─ CHECK PROMPT REGISTRY
   │   Do we have a prompt for TicketBookingAgent?
   │   ├─ YES: Use cached prompt
   │   └─ NO: Generate new prompt (LLM call)
   │
   ├─ RESOLVE TOOLS (from Tool Registry)
   │   What tools are available for this agent?
   │   Example: web_search, parse_html, api_call, format_output
   │
   └─ SPAWN AGENT (via Agent Factory)
      ├─ Send SpawnRequest:
      │   - agent_type: "TicketBookingAgent"
      │   - system_prompt: "You are a restaurant booking specialist..."
      │   - available_tools: ["web_search", "parse_html", "format_output"]
      │   - session_id, trace_id, deadline_ms
      │
      ├─ Wait for agent ACTIVE (WARMING phase, 35s budget)
      │
      └─ Update Agent Roster (add to active pool)

SEND TASKASSIGNMENT
   ├─ TaskAssignment envelope to agent mailbox:
   │   - user_input: "Book a table at an Italian restaurant in NYC"
   │   - available_tools: ["web_search", "parse_html", "format_output"]
   │   - deadline_ms: 5000 (5 seconds to complete)
   │   - trace_id: (propagated from ingress)
   │
   └─ Wait for agent response

AGENT EXECUTES
   ├─ Agent uses its system_prompt + available_tools
   │   Steps:
   │   1. Use web_search to find Italian restaurants in NYC
   │   2. Parse results with parse_html
   │   3. Format booking info with format_output
   │
   └─ Return results with tool call receipts

COLLECT RESULTS
   ├─ Agent completes task successfully
   ├─ Build TaskResult:
   │   - status: "success"
   │   - answer: "I found 3 restaurants with availability..."
   │   - tools_called: ["web_search", "parse_html", "format_output"]
   │   - receipts: [receipt1, receipt2, receipt3] (detailed logs)
   │
   └─ Return to Concierge → User

AGENT LIFECYCLE
   ├─ After task completes: Mark agent as IDLE
   ├─ Keep agent in Agent Roster for 5 minutes (reusable)
   │   Benefit: Next booking task reuses same agent (no spawn overhead)
   ├─ After 5 min inactivity: Transition to TERMINATED
   └─ Free agent resources
```

---

## Key Innovations

### 1. **Prompt Generation on First Use**
- Task comes in: "book restaurant ticket"
- Agent type needed: TicketBookingAgent
- Check Prompt Registry: Does TicketBookingAgent prompt exist?
  - **NO**: Generate it dynamically using LLM
    - Input: agent_type, domain, available_tools, task_context
    - Output: System prompt ("You are a restaurant booking specialist...")
  - Save to Prompt Registry for future use
  - Next TicketBookingAgent task: Use cached prompt (no LLM call)

### 2. **Tool Resolution from Registry**
- Agent types have associated tool sets:
  - TicketBookingAgent: [web_search, parse_html, api_call, format_booking]
  - WebSearchAgent: [web_search, parse_results, summarize]
  - PaymentAgent: [validate_payment, charge_card, generate_receipt]
- SpawnRequest includes available_tools
- Agent gets initialized with full tool arsenal

### 3. **Agent Reuse Pool**
- After task completion: Keep agent IDLE in Agent Roster
- 5-minute TTL (Time-To-Live)
- Next request of same type: Reuse agent (skip WARMING phase)
- Benefit: Avoid 35s spawn overhead on every request

### 4. **Error Handling**
- Prompt generation fails? Use fallback template
- Tool resolution fails? List available tools dynamically
- Agent spawn fails? Retry or use alternative agent type

---

## Component Responsibilities

### Orchestrator Phase 3
- Determine agent type from task
- Check availability (Roster + Prompt Registry)
- Request spawning if needed
- Send TaskAssignment
- Collect results

### Agent Factory
- Receive SpawnRequest
- Load system prompt (provided by Orchestrator)
- Initialize tools (list provided by Orchestrator)
- Spawn agent instance
- Signal ACTIVE when ready

### Agent Instance (TicketBookingAgent, etc.)
- Receive TaskAssignment
- Use system_prompt to understand role
- Use available_tools to solve task
- Call tools, collect receipts
- Return results with full execution log

### Prompt Registry (Caching)
- Store: agent_type → system_prompt mapping
- On first TicketBookingAgent task: agent_type="TicketBookingAgent" not found
  - Generate prompt
  - Store in registry
- On second TicketBookingAgent task: agent_type="TicketBookingAgent" found
  - Use cached prompt (instant, no LLM)

### Tool Registry
- Store: agent_type → available_tools mapping
- Example: "TicketBookingAgent" → ["web_search", "parse_html", "api_call", "format_booking"]
- Orchestrator queries this during spawn

### Agent Roster (in SessionState)
- Track active agents: {agent_id: {agent_type, state, spawned_time}}
- Update when agent spawned: Add to roster
- Update when agent IDLE: Keep in roster (TTL 5 min)
- Update when agent TERMINATED: Remove from roster

---

## Example: Booking a Restaurant

### First Request (Cold Start)
```
User: "Book me a table at Luigi's for 2 people tomorrow at 7pm"

1. Concierge classifies: intent="planning", requires_orchestration=true
2. Orchestrator Phase 1-2: Select TicketBookingAgent
3. Orchestrator Phase 3:
   - Check Roster: TicketBookingAgent? NO
   - Check Prompt Registry: TicketBookingAgent prompt? NO
   - Generate prompt (1 LLM call): "You are a restaurant booking specialist..."
   - Save to registry
   - Resolve tools: ["web_search", "parse_html", "api_call", "format_booking"]
   - Spawn agent (WARMING phase, ~1-2 sec)
   - Mark agent ACTIVE
   - Update Roster
4. Send TaskAssignment:
   - agent_id: ticket_booking_001
   - available_tools: [web_search, parse_html, api_call, format_booking]
   - user_input: "Book me a table at Luigi's for 2 people tomorrow at 7pm"
5. Agent executes:
   - web_search("Luigi's restaurant NYC")
   - parse_html(results)
   - api_call(booking_service, check_availability, params)
   - format_booking(result)
6. Results:
   - "Booking confirmed at Luigi's for 2 people, 7pm tomorrow. Confirmation #12345"
   - receipts: [web_search receipt, parse receipt, api receipt, format receipt]
7. Agent marked IDLE in Roster (5-min TTL)

TOTAL LATENCY: ~5-8 seconds (includes WARMING phase)
```

### Second Request (Hot Start - Agent Reuse)
```
User: "I also need to book a spa appointment tomorrow at 2pm"

Same user, different domain. But if orchestrator selects same TicketBookingAgent:

1. Orchestrator Phase 3:
   - Check Roster: TicketBookingAgent? YES (still IDLE)
   - Use existing agent (REUSE)
   - No WARMING phase needed
   - Skip to TaskAssignment immediately
2. Send TaskAssignment to existing agent
3. Agent executes (with same system_prompt, same tools)
4. Results returned

TOTAL LATENCY: ~3-5 seconds (no spawn overhead)
SAVINGS: ~2-3 seconds by reusing agent
```

### Different Agent Type
```
User: "What's the weather in NYC?"

1. Concierge classifies: intent="query", specialist_type="research"
2. Orchestrator Phase 1-2: Select WebSearchAgent
3. Orchestrator Phase 3:
   - Check Roster: WebSearchAgent? NO
   - Check Prompt Registry: WebSearchAgent prompt? NO
   - Generate prompt: "You are a web search specialist..."
   - Save to registry
   - Resolve tools: ["web_search", "parse_results", "summarize"]
   - Spawn WebSearchAgent
   - Send TaskAssignment
4. Agent executes, returns weather info
5. Agent marked IDLE in Roster

→ Now we have both TicketBookingAgent AND WebSearchAgent in Roster
→ Next ticket booking reuses TicketBookingAgent (HOT)
→ Next weather query reuses WebSearchAgent (HOT)
```

---

## Performance Impact

### Cold Start (First Agent of Type)
- Prompt generation: ~1 LLM call (50-100ms)
- Agent spawn: WARMING phase (1-2 sec)
- **Total: ~5-8 seconds**

### Hot Start (Agent Reuse)
- No prompt generation (cached)
- No spawn (reuse existing agent)
- **Total: ~3-5 seconds** (2-3 sec savings)

### Caching ROI
- 1st booking request: 8 sec (cold)
- 2nd booking request: 5 sec (hot, saved 3 sec)
- 3rd booking request: 5 sec (hot, saved 3 sec)
- 10th booking request: 5 sec (hot, saved 3 sec)
- **Cumulative savings: 30+ seconds over 10 requests**

---

## Next Steps in Implementation

1. **Orchestrator Phase 3** - Implement dynamic agent spawning logic
2. **Prompt Generation Service** - LLM-based prompt generation for new agent types
3. **Prompt Registry** - Storage layer for caching prompts
4. **Agent Reuse Pool** - TTL-based agent lifecycle in Roster
5. **Tool Registry Updates** - Map agent types to available tools
6. **Integration Tests** - Verify spawning, prompt caching, tool resolution

---

## Architecture Alignment

This pattern aligns with:
- **ADR-0005**: Concierge as master coordinator
- **ADR-0006a-c**: Orchestrator 3-phase contract net
- **ADR-0003**: Agent Factory dynamic spawning
- **Capability-based access**: Each agent gets exactly the tools it needs
- **Least privilege**: Agents not given unnecessary tools

---

**Summary**: You've described a **just-in-time agent generation system** where agents are created on-demand with specialized prompts and tool sets, then reused when possible. This is fundamentally different from pre-built static agents and enables massive flexibility for handling arbitrary task types.
