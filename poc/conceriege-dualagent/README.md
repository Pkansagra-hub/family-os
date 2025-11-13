# 🤖 Concierge Dual-Agent POC

**Proof of Concept: Reactive/Proactive Dual-Agent Pattern**

## Overview

This POC demonstrates a novel dual-agent conversational pattern where:

- **Reactive LLM**: Owns the user turn, triggers specialists, integrates results
- **Proactive LLM**: Fills conversation gaps, handles clarifications, maintains flow
- **Specialist Agents**: Domain experts (e.g., Nutritionist) that analyze patterns and query memory

### The Problem We're Solving

In traditional chatbots, long-running operations (like querying memory systems or analyzing patterns) create awkward gaps in conversation. Users wait silently while the system works.

### Our Solution

The **dual-agent pattern** eliminates these gaps:

1. User asks a complex question
2. Reactive agent detects need for specialist
3. **While specialist works**, Proactive agent keeps conversation flowing
4. Specialist can request clarifications through Proactive
5. Reactive integrates final result seamlessly

**Result**: Smooth, natural conversation with no awkward silences.

## Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                               USER                                   │
└───────────────┬───────────────────────────────────────────────────────┘
                │ 1. message ("milk makes me sick")
                ▼
        ┌──────────────────────────────────────────────┐
        │        CONCIERGE (Thread: t-123)            │
        │  ┌───────────────┐   ┌───────────────────┐  │
        │  │ REACTIVE LLM  │   │ PROACTIVE LLM     │  │
        │  │ (turn owner)  │   │ (keeps chatting)  │  │
        │  └───────┬───────┘   └─────────┬─────────┘  │
        │          │ 2. decides tool call              │
        └──────────┼──────────────────────────────────┘
                   │
                   ▼
        ┌──────────────────────────────────────────────┐
        │         SHARED HANDOFF SPACE                 │
        │  (In-Memory Topic-Based Queue)               │
        │  Topics: job.request, job.clarification,     │
        │          job.result                           │
        └───────┬──────────────────────────────────────┘
                │ 4. Specialist picks up job
                ▼
┌──────────────────────────────────────────────────────────────────────┐
│                    NUTRITIONIST SPECIALIST                           │
│  - Analyzes query                                                    │
│  - Requests clarifications (up to 2)                                │
│  - Queries Mock K0 Bridge                                           │
│  - Compiles findings                                                 │
└───────┬──────────────────────────────────────────────────────────────┘
        │ 5. Returns result
        ▼
   [Reactive integrates result]
        │
        ▼
   [User receives comprehensive answer]
```

### Layer Architecture (K1-Style)

```
poc/conceriege-dualagent/
├── l1_input/           # (Future: user input processing)
├── l2_orchestration/   # Concierge coordinator
│   └── concierge.py
├── l3_execution/       # Agents (Reactive, Proactive, Specialist)
│   ├── reactive_agent.py
│   ├── proactive_agent.py
│   └── nutritionist_specialist.py
├── l4_runtime/         # (Future: session state, caching)
├── l5_infrastructure/  # Handoff space, K0 bridge
│   ├── handoff_space.py
│   └── k0_bridge.py
├── config/             # Settings
│   └── settings.py
├── contracts/          # Message contracts
│   └── messages.py
└── main.py            # FastAPI server
```

## Features Demonstrated

### ✅ Dual-Agent Coordination
- Reactive and Proactive share context
- State transitions (idle → active → waiting → idle)
- Seamless handoffs

### ✅ Specialist Pattern
- Dynamic specialist invocation
- Clarification requests (up to 2 rounds)
- Mock K0 memory queries with conditional data

### ✅ Smooth Conversation Flow
- Proactive fills gaps with warm messages
- Clarifications handled naturally
- No awkward silences

### ✅ Handoff Space
- In-memory topic-based pub/sub
- Pattern: `job.request.{thread_id}`, `job.clarification.{thread_id}`, etc.
- Fast (<2ms latency)

## Setup

### Prerequisites
- Python 3.11+
- Groq API key (free tier works)

### Installation

```bash
# Navigate to POC directory
cd poc/conceriege-dualagent

# Install dependencies
pip install -r requirements.txt

# Create .env file
cp .env.example .env

# Edit .env and add your Groq API key
# GROQ_API_KEY=your_key_here
```

### Running the POC

```bash
# Start the server
python -m main

# Or use uvicorn directly
uvicorn main:app --reload --port 8000
```

Open browser: `http://localhost:8000`

## Testing the POC

### Test Case 1: Basic Flow with Clarification

```
User: "milk makes me sick"

Expected behavior:
1. Reactive detects need for nutritionist
2. Proactive: "Let me check our records for any patterns..."
3. Nutritionist asks: "What kind of symptoms? Stomach issues, headaches, etc?"
4. User: "stomach issues"
5. Nutritionist queries K0 (mock data)
6. Reactive: "Based on analysis, you show signs of lactose intolerance..."
```

### Test Case 2: Simple Query (No Specialist)

```
User: "What's the weather today?"

Expected behavior:
1. Reactive responds directly (no specialist needed)
2. Quick response, no gaps
```

### Mock K0 Data

The POC includes mock episodic and semantic memory:

**Episodic Memories:**
- Nov 5: "milk makes me feel sick"
- Nov 2: "cheese doesn't agree with me"
- Oct 28: "stomach discomfort after latte"

**Semantic Patterns (Conditional):**
- **"stomach"** → Lactose intolerance (85% confidence)
- **"headache"** → Possible migraine trigger (65% confidence)
- **"nausea"** → Dairy sensitivity (75% confidence)

## Implementation Details

### Key Components

**1. Reactive Agent (`l3_execution/reactive_agent.py`)**
- Uses Groq LLM to analyze user messages
- Detects when specialist is needed
- Triggers job request via handoff space
- Waits for result
- Integrates findings into final response

**2. Proactive Agent (`l3_execution/proactive_agent.py`)**
- Activates when Reactive waits for specialist
- Generates warm transition messages
- Handles clarification requests from specialist
- Routes user responses back to specialist
- Yields when Reactive returns

**3. Nutritionist Specialist (`l3_execution/nutritionist_specialist.py`)**
- Listens for job requests on handoff space
- Analyzes query complexity
- Requests up to 2 clarifications if needed
- Queries mock K0 bridge
- Compiles findings with confidence scores
- Returns structured result

**4. Handoff Space (`l5_infrastructure/handoff_space.py`)**
- In-memory topic-based message queue
- Pub/sub pattern with asyncio.Queue
- Topics: `job.request.*`, `job.clarification.*`, `job.result.*`
- Message history for debugging

**5. Mock K0 Bridge (`l5_infrastructure/k0_bridge.py`)**
- Simulates episodic memory (past events)
- Simulates semantic patterns (dietary analysis)
- Conditional responses based on symptom type
- Returns realistic mock data

**6. Concierge Coordinator (`l2_orchestration/concierge.py`)**
- Orchestrates Reactive/Proactive lifecycle
- Manages shared context
- Handles state transitions
- Coordinates message flow

### Message Contracts

All messages use Pydantic models (`contracts/messages.py`):

- `JobRequest`: Reactive → Specialist
- `JobClarification`: Specialist → Proactive
- `JobClarificationResponse`: Proactive → Specialist
- `JobProgress`: Specialist → (optional monitoring)
- `JobResult`: Specialist → Reactive

### Configuration

**Environment Variables (.env):**
```bash
GROQ_API_KEY=your_key
GROQ_MODEL=llama-3.1-70b-versatile
SERVER_HOST=0.0.0.0
SERVER_PORT=8000
CLARIFICATION_LIMIT=2
```

## Limitations (POC Scope)

- **In-memory only**: No persistence (sessions lost on restart)
- **Single specialist**: Only Nutritionist implemented
- **Mock K0**: Hardcoded data, not real memory system
- **No production features**: No auth, rate limiting, error recovery
- **Simple WebSocket**: No reconnection logic, message delivery guarantees

## Future Enhancements

- [ ] Add more specialists (Sleep Coach, Financial Advisor, etc.)
- [ ] Integrate real K0 kernel
- [ ] Persistent thread storage (SQLite)
- [ ] Tool dispatch layer (PEP/Policy/QoS)
- [ ] Working memory & summarizer
- [ ] Multi-turn clarification chains
- [ ] Voice interface integration
- [ ] Performance metrics (P95 latency tracking)

## Success Criteria

This POC successfully demonstrates:

✅ **Smooth conversation flow** - No awkward gaps when specialist works
✅ **Dual-agent coordination** - Reactive/Proactive handoffs work seamlessly
✅ **Specialist clarifications** - Natural question/answer flow
✅ **Mock K0 integration** - Conditional data based on symptoms
✅ **Handoff space pattern** - Topic-based pub/sub coordination

## Troubleshooting

**WebSocket won't connect:**
- Check server is running: `http://localhost:8000/health`
- Check browser console for errors

**No specialist response:**
- Check logs for specialist listener startup
- Verify handoff space topic matching

**Groq API errors:**
- Verify API key in `.env`
- Check rate limits (free tier: 30 req/min)
- Try different model: `llama-3.1-8b-instant` (faster)

**Clarification not working:**
- Check `CLARIFICATION_LIMIT` setting
- Verify shared context updates
- Check logs for clarification queue messages

## Logs & Debugging

**Enable debug logging:**
```python
# In main.py, change:
logging.basicConfig(level=logging.DEBUG)
```

**Key log patterns:**
- `[Reactive]` - Reactive agent actions
- `[Proactive]` - Proactive agent actions
- `[Nutritionist]` - Specialist actions
- `[Concierge]` - Coordinator actions
- `K0 Bridge:` - Mock K0 queries

## License

Part of FamilyOS project. See root LICENSE file.

## Contact

Questions or feedback? Open an issue in the main repository.

---

**Built to prove the dual-agent pattern works. Mission accomplished. 🎯**
