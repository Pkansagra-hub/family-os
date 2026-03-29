# K1 Concierge Module (Layer 2: Orchestration - Master Coordinator)

## Overview

The `concierge/` module implements the **ConciergeAgent** pattern as the master coordinator for the K1 Intelligence Kernel. This module serves as the single entry point for all user messages, handling meta-intent classification, SessionState management, and intelligent routing decisions between direct handling and orchestration.

## Purpose

- **Meta-Intent Classification**: Distinguish between 11 conversational meta-intents (acknowledgments, corrections, amendments, etc.) and task-oriented requests
- **SessionState Management**: Maintain conversation context, affect tracking, referent resolution, and QUD (Questions Under Discussion)
- **Intelligent Routing**: Route task-intents to K1 Orchestrator while handling meta-intents directly
- **Workflow Coordination**: Manage multi-turn conversations, corrections, amendments, and interruptions

## Architecture

### Core Components

- **`concierge_agent.py`**: Main ConciergeAgent implementation with LLM-based classification
- **`meta_intent_classifier.py`**: Specialized classification logic for 11 meta-intent types
- **`sessionstate_updater.py`**: SessionState management and updates
- **`routing_decision_engine.py`**: Logic for routing to orchestrator vs direct handling
- **`tool_call_handler.py`**: Interface for tool calls to Orchestrator (not direct execution)

### Process Flow

```mermaid
USER MESSAGE
    ↓
ConciergeAgent (Always Active)
├── Classify Meta-Intent (11 types)
├── Update SessionState (6 sections)
└── Route Decision
    ├── Meta-Intent → Handle Directly
    │   ├── ACKNOWLEDGMENT: "You're welcome"
    │   ├── STATUS_CHECK: Progress update
    │   ├── CANCELLATION: Cancel task
    │   └── SMALL_TALK: Friendly response
    └── Task-Intent → Tool Call to Orchestrator
        └── Orchestrator executes via tool batching
```

## Key ADRs

- **ADR-0093**: ConciergeAgent Pattern - Master coordinator with 11 meta-intents
- **ADR-0078**: Tool Call Batching Pipeline - Parallel tool execution via orchestrator
- **ADR-0006f**: 3-Phase Orchestration - Routes task-intents to orchestrator
- **ADR-0017**: SessionState 6-Section Design - Manages conversation context
- **ADR-0086**: Dynamic Agent Creation Subsystem - Triggers agent spawning via orchestrator
- **ADR-0007**: 4-Stage Planning Pipeline - Planning coordination
- **ADR-0001**: K0/K1 Kernel Split - Clean separation of concerns

## 11 Meta-Intents

### Direct Handling (No Orchestration)

1. **ACKNOWLEDGMENT**: "ok", "thanks", "got it" - Brief acknowledgment response
2. **STATUS_CHECK**: "are you there?", "still working?" - Progress updates from active tasks
3. **CANCELLATION**: "never mind", "stop", "forget it" - Cancel tasks with partial save
4. **RETRY**: "try again", "retry" - Retry failed tasks with fallback strategies
5. **CORRECTION**: Typo fixes (<2s follow-up) - Merge corrections, cancel superseded messages
6. **RAPID_BATCH**: Multiple messages <500ms - Merge into single multi-part query
7. **AMENDMENT**: "Actually make it 4 people" (<30s) - Compensate and amend via saga pattern
8. **REFINEMENT**: "Only Italian restaurants" - Filter current results without restart
9. **TOPIC_CHANGE**: Domain switches - Cancel old tasks, start new QUD
10. **AMBIGUOUS_QUERY**: Low confidence queries - Ask clarification questions
11. **SMALL_TALK**: "How are you?" - Friendly social responses

### Task Routing (To Orchestrator)

- All other intents route to K1 Orchestrator via tool calls
- Orchestrator handles 3-phase coordination: selection → spawning → execution
- Tool call batching enables parallel execution (ADR-0078)

## Interfaces

### ConciergeAgent Interface

```python
class ConciergeAgent:
    async def process_message(self, user_message: str, session_id: str) -> ConciergeResponse:
        """Single entry point for all user messages"""

    async def classify_meta_intent(self, message: str, context: SessionState) -> MetaIntentClassification:
        """LLM-based classification of 11 meta-intent types"""

    async def update_sessionstate(self, classification: MetaIntentClassification) -> SessionStateUpdates:
        """Update all 6 SessionState sections"""

    async def make_routing_decision(self, classification: MetaIntentClassification) -> RoutingDecision:
        """Decide: handle directly or route to orchestrator"""
```

### ToolCallHandler Interface

```python
class ToolCallHandler:
    async def call_orchestrator_tool(self, tool_name: str, parameters: Dict) -> ToolResult:
        """Make tool calls to Orchestrator (not direct execution)"""

    async def batch_tool_calls(self, tool_calls: List[ToolCall]) -> List[ToolResult]:
        """Batch multiple tool calls for parallel execution"""
```

### SessionStateUpdater Interface

```python
class SessionStateUpdater:
    async def update_scoreboard(self, message: str, classification: MetaIntentClassification) -> None:
        """Update recent_turns, topics_discussed, QUD, referents"""

    async def update_control(self, classification: MetaIntentClassification) -> None:
        """Update active_tasks, last_query, last_action_id"""

    async def update_affect(self, message: str) -> None:
        """Detect and update emotional state"""

    async def update_self_model(self, message: str) -> None:
        """Extract self-perception beliefs"""
```

## Performance Characteristics

- **Classification Latency**: <50ms P95 (LLM-based meta-intent classification)
- **SessionState Updates**: <10ms P95 (deterministic updates)
- **Routing Decision**: <5ms P95 (conditional logic)
- **Total Overhead**: <65ms P95 (within E2E 2000ms budget)
- **Tool Call Latency**: <3000ms P95 (via orchestrator batching)

## Tool Call Pattern (Not Direct Execution)

**Important**: ConciergeAgent does NOT execute tools directly. It makes tool calls to the Orchestrator:

```python
# Correct: Tool call to Orchestrator
tool_result = await self.tool_call_handler.call_orchestrator_tool(
    "orchestrate_task",
    {"task": user_task, "session_id": session_id}
)

# Incorrect: Direct execution (violates architecture)
# result = await self.orchestrator.execute_task(user_task)  # NO!
```

This pattern ensures:

- Clean separation between intent classification and execution
- Tool batching and parallelization via Orchestrator
- Proper capability boundaries and security
- Observable tool execution with receipts


## Fault Tolerance

- **Classification Fallbacks**: Rule-based fallbacks if LLM classification fails
- **SessionState Recovery**: Automatic reconstruction from message history
- **Tool Call Retries**: Automatic retry with exponential backoff
- **Graceful Degradation**: Direct responses for critical meta-intents even if orchestrator unavailable
- **Circuit Breaker**: Protect against orchestrator failures

## Security

- **Input Validation**: Sanitize all user messages before processing
- **Capability Checks**: Validate tool call permissions before routing
- **Audit Trail**: Log all classifications, routing decisions, and tool calls
- **Privacy Protection**: Respect privacy bands in SessionState updates
- **Rate Limiting**: Prevent abuse of meta-intent processing

## Testing

- **Unit Tests**: Isolated classification and SessionState update logic
- **Integration Tests**: End-to-end message processing with mock orchestrator
- **Performance Tests**: Classification latency and throughput under load
- **Conversation Tests**: Multi-turn scenarios with corrections, amendments, interruptions
- **Tool Call Tests**: Proper tool call formatting and error handling

## Dependencies

- `k1.orchestrator`: Tool call target for task execution
- `k1.sessionstate`: Conversation context management
- `k1.model_hub`: LLM access for meta-intent classification
- `k1.bus`: Event publishing for observability
- `k1.telemetry`: Performance monitoring and tracing

## Development Notes

- ConciergeAgent is always ACTIVE (never IDLE/TERMINATED)
- Single entry point prevents message routing confusion
- Tool calls to Orchestrator enable parallel batching (ADR-0078)
- SessionState updates happen on every message for context awareness
- Meta-intent handling prevents unnecessary orchestration overhead
- LLM-based classification handles complex conversational scenarios
- Clean separation between intent understanding and task execution
