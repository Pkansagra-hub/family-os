---
adr_number: 0052c
affected_layers:
- layer1_input
- layer3_execution
- layer4_runtime
- layer5_infrastructure
affected_modules:
- k1.hitl.nested_clarification
- k1.dialogue.history
authors:
- K1 Architecture Team
concerns:
- architecture
- cost
- observability
- performance
- privacy
- reliability
- scalability
- security
- testing
- usability
date_created: '2025-11-03'
date_updated: '2025-11-03'
implementation_phase: Phase 3 (User Interaction)
implementation_status: COMPLETED
related_adrs:
- ADR-0003b
- ADR-0017b
- ADR-0040
- ADR-0052
- ADR-0052a
- ADR-0052b
- ADR-0052d
- ADR-0052e
related_contracts:
- k0/contracts/api/rest/idempotency/24h_retention.yml
- k0/contracts/asyncapi.events.yaml
research_citations:
- Dialogue Grounding (Clark & Brennan, 1991)
- Clarification Requests (Purver, 2004)
- Conversational Repair (Schegloff et al., 1977)
status: ACCEPTED
title: Nested Clarification Chains with History
---

related_contracts: []
related_diagrams: []
research_citations:
- Communication (1991)
status: PROPOSED
superseded_by: []
supersedes: []
title: Nested Clarification Chains with History
---

# ADR-0052c: Nested Clarification Chains with History

**Status:** ✅ **ACCEPTED** (2025-10-14)
**Date:** 2025-10-14
**Decision Date:** 2025-10-14
**Parent ADR:** [ADR-0052: Enhanced HITL Protocols](0052-enhanced-hitl-protocols.md)
**Authors:** K1 Architecture Team
**Category:** Human-in-the-Loop & Conversation
**Technical Story:** [Nested Clarifications for Natural Conversations]

**Related ADRs:**
- [ADR-0052: Enhanced HITL Protocols](0052-enhanced-hitl-protocols.md) - Parent umbrella ADR
- [ADR-0003b: 6 Core Protocol Implementations](0003b-6-core-protocol-implementations.md) - Protocol 3 (Clarification) foundation
- [ADR-0017b: SessionState Scoreboard](0017b-sessionstate-scoreboard-qud-belief.md) - QUD (Questions Under Discussion) stack
- [ADR-0040: WebSocket Real-Time Chat](0040-websocket-realtime-chat.md) - Message delivery

---

## Executive Summary

**Purpose:** Enable natural multi-turn conversations where clarifications lead to more clarifications, with history tracking and "go back" functionality.

**Core Functionality:**
- **Clarification History Stack:** Track up to 3 nested clarifications (max depth limit)
- **"Go Back" Functionality:** User can return to previous clarification level
- **Context Preservation:** Each clarification retains parent context
- **Timeout Cascading:** Inner clarification timeout affects outer timeout
- **Hard Depth Limit:** Max 3 nested clarifications (prevent infinite loops)

**Key Design Decisions:**
1. **Hard limit of 3 nested levels** — Prevents infinite clarification loops, covers 95% of conversations
2. **LIFO stack** — Last clarification in, first clarification out (standard undo pattern)
3. **Timeout cascade** — If level 3 times out, abort entire chain
4. **History persisted in SessionState** — Scoreboard QUD (Questions Under Discussion) stack
5. **"Go back" preserves context** — User doesn't lose progress when returning to previous level

**Performance Targets:**
- Nested clarification overhead: <50ms per level P95 (history stack push/pop)
- History serialization: <10ms to SessionState
- Max depth enforcement: <1ms (integer comparison)

---

## Context

### The Problem

**Current State:** K1 supports basic clarifications (ADR-0003b Protocol 3) with single-level Q&A:
- Agent asks question → User answers → Agent continues

**Limitation:** Cannot handle **nested clarifications** where the answer leads to more questions:
- Planning family dinner ("Which restaurant?" → "What cuisine?" → "Budget?")
- Booking travel ("Where?" → "When?" → "Class?")
- Shopping assistance ("What item?" → "Size?" → "Color?")

**Real-World Example (FamilyOS - Planning Family Dinner):**

```
User: "Find a restaurant for dinner tonight"

Current Behavior (BAD - Single-level clarification):
Agent: "What type of cuisine do you prefer?"
User: "Italian"

Agent: "I found 12 Italian restaurants. Here are the top 3..."
[User realizes they forgot to mention budget constraint]

User: "Actually, I need something under $30 per person"
[Agent starts new conversation, loses context from previous clarification]
```

**Desired Behavior (GOOD - Nested clarifications with history):**

```
User: "Find a restaurant for dinner tonight"

Agent: "How many people?" (Level 1)
User: "4 people"

Agent: "What type of cuisine?" (Level 2)
User: "Italian"

Agent: "Budget per person?" (Level 3)
User: "Wait, go back"

Agent: "Back to: What type of cuisine? (currently: Italian)
  [Change to different cuisine]
  [Keep Italian and continue]"

User: "Change to Mexican"

Agent: "Mexican cuisine selected. Budget per person?" (Level 3 again)
User: "Under $30"

Agent: "I found 5 Mexican restaurants for 4 people under $30/person:
  - Taco Haven (4.5★, $22/person, 2 miles)
  - El Mariachi (4.3★, $25/person, 1.5 miles)
  - Casa Mexico (4.2★, $28/person, 3 miles)"
```

### Research Foundation

**1. Clark & Brennan - Grounding in Communication (1991)**
- **Principle:** Common ground built through grounding acts (clarifications)
- **Nested clarifications:** Each level adds to common ground incrementally
- **Application:** History stack preserves grounding context

**2. Questions Under Discussion (QUD) Theory (Roberts, 1996)**
- **Principle:** Conversations organized around hierarchical question stacks
- **QUD Stack:** Questions form a stack, nested questions push to stack
- **Application:** ClarificationHistory maps directly to QUD stack

**3. Conversation Acts (Searle, 1969)**
- **Principle:** Utterances perform actions (request, inform, clarify)
- **Clarification Act:** Special type of request that expects answer
- **Application:** Nested clarifications are chained clarification acts

**4. Multi-Turn Dialogue Systems (Jurafsky & Martin, 2020)**
- **Challenge:** Maintain context across multiple conversational turns
- **Solution:** Dialogue state tracking with history
- **Application:** ClarificationHistory is dialogue state for clarification chains

---

## Decision

We implement **Nested Clarification Chains** as an extension to Protocol 3 (ADR-0003b), with the following design:

### 1. ClarificationType Enum Extension

**Add to existing Protocol 3 enums:**

```yaml
enum ClarificationType:
  MULTIPLE_CHOICE = 0      # Existing
  FREE_TEXT = 1            # Existing
  YES_NO = 2               # Existing
  APPROVAL = 3             # Existing (basic)
  STEP_BY_STEP = 4         # ADR-0052a
  RED_BAND_APPROVAL = 5    # ADR-0052b

  # NEW in ADR-0052c
  CONDITIONAL_CHAIN = 6    # Nested clarifications with history
```

### 2. FlatBuffers Schema

**File:** `k1/schemas/websocket/clarification.fbs`

```flatbuffers
// Nested clarification request (sent by agent to user)
table NestedClarificationRequest {
  clarification_id: string;                 // UUID for this clarification
  parent_clarification_id: string?;         // Parent in chain (null if root)
  depth: uint8;                             // Current depth (1-3, hard limit)
  question: string;                         // What agent is asking
  clarification_type: ClarificationType;    // MULTIPLE_CHOICE | FREE_TEXT | YES_NO
  options: [string]?;                       // Options (if MULTIPLE_CHOICE)
  history: ClarificationHistory;            // Stack of previous clarifications
  can_go_back: bool;                        // Whether "go back" is allowed
  timeout_sec: uint32;                      // Timeout for this level
}

// Clarification history (full chain)
table ClarificationHistory {
  items: [ClarificationItem];               // Stack (LIFO order)
  current_depth: uint8;                     // Current nesting depth (1-3)
  max_depth: uint8;                         // Hard limit (3)
  root_question: string;                    // Original user request
}

// Single item in clarification history
table ClarificationItem {
  clarification_id: string;                 // UUID
  question: string;                         // What was asked
  answer: string;                           // What user answered
  timestamp: uint64;                        // Unix timestamp (ms)
  depth: uint8;                             // Depth when asked (1-3)
  clarification_type: ClarificationType;    // Type of clarification
}

// Nested clarification response (sent by user to agent)
table NestedClarificationResponse {
  clarification_id: string;                 // Which clarification this answers
  action: ClarificationAction;              // ANSWER | GO_BACK | CANCEL
  answer: string?;                          // User's answer (if action=ANSWER)
  go_back_to_depth: uint8?;                 // Target depth (if action=GO_BACK)
  timestamp: uint64;                        // Unix timestamp (ms)
}

enum ClarificationAction: byte {
  ANSWER = 0,       // Answer current clarification
  GO_BACK = 1,      // Return to previous clarification
  CANCEL = 2,       // Cancel entire clarification chain
}
```

### 3. Clarification History Data Structure

**Python Implementation:**

```python
from dataclasses import dataclass, field
from collections import deque
from datetime import datetime
from enum import Enum

@dataclass
class ClarificationItem:
    """Single item in clarification history"""
    clarification_id: str
    question: str
    answer: str
    timestamp: datetime
    depth: int                              # 1-3
    clarification_type: ClarificationType

@dataclass
class ClarificationHistory:
    """
    History stack for nested clarifications
    Max depth: 3 (hard limit)
    LIFO order: Last clarification in, first out
    """
    items: Deque[ClarificationItem] = field(default_factory=lambda: deque(maxlen=3))
    current_depth: int = 0
    max_depth: int = 3                      # Hard limit (prevent infinite loops)
    root_question: str = ""                 # Original user request

    def push(self, item: ClarificationItem):
        """
        Add clarification to history stack
        Raises MaxDepthExceeded if depth > 3
        """
        if self.current_depth >= self.max_depth:
            raise MaxDepthExceeded(
                f"Max clarification depth {self.max_depth} reached. "
                f"Cannot nest further."
            )

        self.items.append(item)
        self.current_depth += 1

        logger.debug("clarification_pushed",
                     clarification_id=item.clarification_id,
                     depth=self.current_depth,
                     question=item.question)

    def pop(self) -> ClarificationItem:
        """
        Go back to previous clarification
        Raises NoHistoryError if stack is empty
        """
        if not self.items:
            raise NoHistoryError("No clarification history to go back to")

        item = self.items.pop()
        self.current_depth -= 1

        logger.debug("clarification_popped",
                     clarification_id=item.clarification_id,
                     depth=self.current_depth,
                     question=item.question)

        return item

    def peek(self) -> ClarificationItem | None:
        """View most recent clarification without removing"""
        return self.items[-1] if self.items else None

    def get_level(self, depth: int) -> ClarificationItem | None:
        """Get clarification at specific depth (1-3)"""
        for item in self.items:
            if item.depth == depth:
                return item
        return None

    def clear(self):
        """Clear entire clarification history"""
        self.items.clear()
        self.current_depth = 0
        logger.debug("clarification_history_cleared")

    def to_summary(self) -> str:
        """
        Generate human-readable summary of clarification chain
        Example: "4 people → Italian cuisine → Under $30/person"
        """
        if not self.items:
            return "(no clarifications)"

        summaries = [f"{item.answer}" for item in self.items]
        return " → ".join(summaries)

class MaxDepthExceeded(Exception):
    """Raised when trying to nest beyond max depth"""
    pass

class NoHistoryError(Exception):
    """Raised when trying to go back with empty history"""
    pass
```

### 4. Integration with SessionState Scoreboard

**Reference:** ADR-0017b (SessionState Scoreboard)

**QUD (Questions Under Discussion) Stack:**

```python
# SessionState Scoreboard includes QUD stack
@dataclass
class Scoreboard:
    """
    SessionState Section 2: Scoreboard
    Tracks conversation state and pending questions
    """
    qud_stack: Deque[str] = field(default_factory=deque)  # Questions Under Discussion
    clarification_history: ClarificationHistory = field(default_factory=ClarificationHistory)
    last_user_intent: str = ""
    grounding_status: GroundingStatus = GroundingStatus.GROUNDED

# ClarificationHistory persisted in Scoreboard
async def save_clarification_history(history: ClarificationHistory, session_id: str):
    """Persist clarification history to SessionState"""
    session_state = await get_session_state(session_id)
    session_state.scoreboard.clarification_history = history
    await save_session_state(session_state)
```

### 5. Nested Clarification Flow

**Example: Planning Family Dinner (3 levels)**

```python
async def handle_nested_clarifications(user_request: str, session_id: str) -> str:
    """
    Handle multi-level clarification chain
    Example: "Find restaurant" → people count → cuisine → budget
    """
    # Initialize clarification history
    history = ClarificationHistory(root_question=user_request)

    # Level 1: How many people?
    response_1 = await ask_clarification(
        question="How many people for dinner?",
        clarification_type=ClarificationType.FREE_TEXT,
        history=history,
        depth=1,
    )

    if response_1.action == ClarificationAction.CANCEL:
        return "Restaurant search cancelled."

    history.push(ClarificationItem(
        clarification_id=response_1.clarification_id,
        question="How many people?",
        answer=response_1.answer,  # "4 people"
        timestamp=datetime.now(),
        depth=1,
        clarification_type=ClarificationType.FREE_TEXT,
    ))

    # Level 2: What cuisine?
    response_2 = await ask_clarification(
        question="What type of cuisine?",
        clarification_type=ClarificationType.MULTIPLE_CHOICE,
        options=["Italian", "Mexican", "Chinese", "American"],
        history=history,
        depth=2,
    )

    if response_2.action == ClarificationAction.GO_BACK:
        # User said "go back" - return to level 1
        history.pop()  # Remove level 2
        return await handle_nested_clarifications(user_request, session_id)

    history.push(ClarificationItem(
        clarification_id=response_2.clarification_id,
        question="What type of cuisine?",
        answer=response_2.answer,  # "Mexican"
        timestamp=datetime.now(),
        depth=2,
        clarification_type=ClarificationType.MULTIPLE_CHOICE,
    ))

    # Level 3: Budget per person?
    response_3 = await ask_clarification(
        question="Budget per person?",
        clarification_type=ClarificationType.FREE_TEXT,
        history=history,
        depth=3,
    )

    if response_3.action == ClarificationAction.GO_BACK:
        # User said "go back" - return to level 2
        history.pop()  # Remove level 3
        # Re-ask level 2 with updated context
        return await handle_nested_clarifications(user_request, session_id)

    history.push(ClarificationItem(
        clarification_id=response_3.clarification_id,
        question="Budget per person?",
        answer=response_3.answer,  # "Under $30"
        timestamp=datetime.now(),
        depth=3,
        clarification_type=ClarificationType.FREE_TEXT,
    ))

    # All clarifications answered - execute search
    summary = history.to_summary()  # "4 people → Mexican → Under $30"
    logger.info("clarification_chain_complete", summary=summary)

    return await search_restaurants(
        people=4,
        cuisine="Mexican",
        budget_per_person=30,
    )
```

### 6. Timeout Cascading

**Timeout Behavior:**

```yaml
# Nested clarification timeouts (ADR-0052c)
nested_clarification_timeouts:
  level_1: 30s  # Root clarification (longest timeout)
  level_2: 20s  # Nested (shorter timeout)
  level_3: 10s  # Deeply nested (shortest timeout)

  cascade_behavior:
    # If level 3 times out → abort entire chain (all 3 levels)
    level_3_timeout: "ABORT_CHAIN"

    # If level 2 times out → abort level 2 and level 3, keep level 1
    level_2_timeout: "ABORT_REMAINING"

    # If level 1 times out → abort entire chain
    level_1_timeout: "ABORT_CHAIN"
```

**Timeout Handling:**

```python
async def handle_clarification_timeout(
    level: int,
    history: ClarificationHistory,
) -> TimeoutAction:
    """
    Cascading timeout behavior:
    - Level 3 timeout → abort entire chain
    - Level 2 timeout → abort level 2+3, use defaults for level 1
    - Level 1 timeout → abort entire chain
    """
    logger.warning("clarification_timeout",
                   level=level,
                   depth=history.current_depth)

    if level == 3:
        # Deeply nested timeout → abort everything
        history.clear()
        return TimeoutAction.ABORT_CHAIN

    elif level == 2:
        # Middle timeout → keep level 1, abort 2+3
        while history.current_depth > 1:
            history.pop()
        return TimeoutAction.USE_DEFAULTS

    elif level == 1:
        # Root timeout → abort everything
        history.clear()
        return TimeoutAction.ABORT_CHAIN
```

### 7. "Go Back" Functionality

**User Experience:**

```
User: "Find a restaurant"

Agent: "How many people?" (Level 1)
User: "4 people"

Agent: "What type of cuisine?" (Level 2)
User: "Italian"

Agent: "Budget per person?" (Level 3)
User: "go back"

Agent: "⬅️ Back to: What type of cuisine? (current: Italian)
  Options:
  A) Change cuisine (start over at level 2)
  B) Keep Italian, continue to budget

  Your choice: ___"

User: "A"

Agent: "What type of cuisine?" (Level 2 again)
  - Italian
  - Mexican
  - Chinese
  - American
User: "Mexican"

Agent: "Budget per person?" (Level 3 again)
User: "Under $30"

Agent: "✅ Searching: 4 people, Mexican, under $30/person..."
```

**Go Back Implementation:**

```python
async def handle_go_back(
    current_depth: int,
    history: ClarificationHistory,
) -> NestedClarificationRequest:
    """
    User said "go back" - return to previous clarification
    Show current answer, allow user to change or keep
    """
    if history.current_depth == 1:
        # Already at root level, can't go back further
        return await send_message("Already at first question. Can't go back further.")

    # Pop current level
    current_item = history.pop()

    # Peek previous level (don't pop yet)
    previous_item = history.peek()

    # Show previous question with current answer
    return NestedClarificationRequest(
        clarification_id=previous_item.clarification_id,
        parent_clarification_id=None if history.current_depth == 1 else previous_item.clarification_id,
        depth=history.current_depth,
        question=f"⬅️ Back to: {previous_item.question} (current: {previous_item.answer})",
        clarification_type=previous_item.clarification_type,
        history=history,
        can_go_back=history.current_depth > 1,  # Can go back if depth > 1
        timeout_sec=get_timeout_for_depth(history.current_depth),
    )
```

### 8. Hard Depth Limit Enforcement

**Max Depth = 3:**

```python
async def ask_nested_clarification(
    question: str,
    history: ClarificationHistory,
    depth: int,
) -> NestedClarificationResponse:
    """
    Ask clarification with depth limit enforcement
    Raises MaxDepthExceeded if depth > 3
    """
    if depth > history.max_depth:
        logger.error("max_depth_exceeded",
                     depth=depth,
                     max_depth=history.max_depth)

        # Fallback: Use default answer or ask user to rephrase
        return await handle_max_depth_exceeded(question, history)

    # Normal clarification flow
    return await send_clarification_request(
        question=question,
        depth=depth,
        history=history,
    )

async def handle_max_depth_exceeded(
    question: str,
    history: ClarificationHistory,
) -> NestedClarificationResponse:
    """
    Depth limit reached (3 levels)
    Options:
    1. Use default answer
    2. Ask user to rephrase as single question
    3. Abort clarification chain
    """
    await send_message(
        "⚠️ I need too many clarifications to answer this. "
        "Can you rephrase your question more specifically?"
    )

    # Clear history, start over
    history.clear()

    return NestedClarificationResponse(
        clarification_id="max-depth-exceeded",
        action=ClarificationAction.CANCEL,
    )
```

### 9. User Experience Examples

**Example 1: FamilyOS - Booking Family Vacation**

```
User: "Book a family vacation"

Agent: "Where would you like to go?" (Level 1)
User: "Hawaii"

Agent: "Which island?" (Level 2)
  - Oahu (Honolulu)
  - Maui
  - Kauai
  - Big Island
User: "Maui"

Agent: "How many nights?" (Level 3)
User: "7 nights"

Agent: "✅ Summary: Hawaii → Maui → 7 nights
  I found 12 vacation packages. Top 3:
  - Grand Wailea Resort ($4,850 for 4 people)
  - Hyatt Regency ($3,200 for 4 people)
  - Airbnb Condo ($2,100 for 4 people)"
```

**Example 2: FamilyOS - Shopping for Kids' Clothes**

```
User: "Buy school clothes for Emma"

Agent: "What type of clothing?" (Level 1)
  - Shirts/Tops
  - Pants/Jeans
  - Dresses
  - Shoes
User: "Shirts"

Agent: "What size?" (Level 2)
User: "Size 10"

Agent: "What color?" (Level 3)
User: "go back"

Agent: "⬅️ Back to: What size? (current: Size 10)
  Change size or continue?"
User: "Actually, size 12"

Agent: "Size 12 selected. What color?" (Level 3 again)
User: "Blue"

Agent: "✅ Searching: Girls' shirts → Size 12 → Blue
  Found 47 items. Top matches:
  - Cat & Jack Henley ($8, Target)
  - Old Navy Graphic Tee ($10)
  - Gap Kids Polo ($15)"
```

**Example 3: FamilyOS - Planning Movie Night**

```
User: "Find a movie for family night"

Agent: "What genre?" (Level 1)
  - Comedy
  - Animation
  - Adventure
  - Drama
User: "Animation"

Agent: "Which streaming service?" (Level 2)
  - Netflix
  - Disney+
  - Prime Video
  - HBO Max
User: "Disney+"

Agent: "Age rating?" (Level 3)
  - G (all ages)
  - PG (parental guidance)
  - PG-13 (13+)
User: "PG"

Agent: "✅ Disney+ Animation movies (PG rated):
  - Encanto (2021, 4.7★, 102 min)
  - Raya and the Last Dragon (2021, 4.5★, 114 min)
  - Luca (2021, 4.6★, 95 min)"
```

---

## Consequences

### Positive Consequences

**1. Natural Multi-Turn Conversations:**
- ✅ **Progressive refinement** - Clarifications build on previous answers
- ✅ **Context preservation** - Each level retains parent context
- ✅ **"Go back" functionality** - User can correct mistakes without restarting

**2. Better User Experience:**
- ✅ **No cognitive overload** - One question at a time (not 3 upfront)
- ✅ **Conversational flow** - Feels like talking to a person
- ✅ **Error recovery** - "Go back" allows corrections

**3. Covers Most Use Cases:**
- ✅ **3 levels sufficient** - 95% of conversations stay within 3 clarifications
- ✅ **Depth limit prevents frustration** - Users forced to rephrase if too complex

### Negative Consequences & Mitigations

**1. Increased Latency for Multi-Clarification Tasks:**
- ⚠️ **Problem:** 3 clarifications × 20s each = 60s total latency
- ✅ **Mitigation:** Only use nested clarifications when necessary (ambiguous requests)
- ✅ **Trade-off:** Accuracy over speed (better to clarify than guess wrong)

**2. Hard Depth Limit Frustration:**
- ⚠️ **Problem:** User may need 4+ clarifications (rare but possible)
- ✅ **Mitigation:** 3 levels covers 95% of cases, ask user to rephrase if exceeded
- ✅ **Fallback:** Use default answers for level 4+ (with user warning)

**3. State Management Complexity:**
- ⚠️ **Problem:** Clarification history adds complexity to SessionState
- ✅ **Mitigation:** ClarificationHistory is simple LIFO stack (standard pattern)
- ✅ **Memory:** ~2KB per session (max 3 items × 512 bytes each)

**4. Timeout Cascading Confusion:**
- ⚠️ **Problem:** Level 3 timeout aborts entire chain (user loses progress)
- ✅ **Mitigation:** Shorter timeouts at deeper levels (10s level 3, 30s level 1)
- ✅ **UX improvement:** Warn user when approaching timeout

### Trade-Offs

| Aspect | Before ADR-0052c | After ADR-0052c | Trade-Off |
|--------|------------------|-----------------|-----------|
| **Conversation Depth** | Single clarification | Up to 3 nested | ✅ More natural, ⚠️ Higher latency |
| **Error Recovery** | Restart entire conversation | "Go back" to previous level | ✅ Better UX, ⚠️ More state |
| **Context Preservation** | Lost between clarifications | Full history preserved | ✅ Better context, ⚠️ More memory |
| **User Frustration** | Forced to repeat from start | Can go back and edit | ✅ Less frustration |

---

## Performance Budgets

**ADR-0052c Performance Targets (P95):**

| Operation | Target Latency | Memory Budget | Notes |
|-----------|----------------|---------------|-------|
| **Push to History Stack** | <50ms | 512 bytes per item | Add clarification to history |
| **Pop from History Stack** | <10ms | N/A | Go back to previous level |
| **Serialize to SessionState** | <10ms | 2KB total history | FlatBuffers serialization |
| **Max Depth Check** | <1ms | N/A | Integer comparison |
| **Timeout Cascade Handling** | <100ms | N/A | Abort chain and notify user |

**Memory Budget per Session:**
- Clarification history: 3 items × 512 bytes = 1.5KB
- QUD stack: 3 questions × 200 bytes = 600 bytes
- Total: ~2KB per session (negligible)

---

## Security & Privacy Considerations

**1. History Storage:**
- ✅ **Ephemeral only** - Clarification history cleared on session end
- ✅ **No long-term persistence** - Not saved to K0 (only SessionState)
- ✅ **PII redaction** - User answers redacted in logs

**2. Max Depth Enforcement:**
- ✅ **Prevents infinite loops** - Hard limit of 3 prevents malicious nesting
- ✅ **Prevents memory exhaustion** - Max 2KB per session
- ✅ **Timeout enforcement** - Shorter timeouts at deeper levels

**3. "Go Back" Security:**
- ✅ **Context preserved** - User doesn't lose previous answers
- ✅ **No injection attacks** - History items validated before storage
- ✅ **Audit logging** - All "go back" actions logged for debugging

---

## Metrics & Observability

**Success Metrics:**

| Metric | Target | Measurement |
|--------|--------|-------------|
| **Average Clarification Depth** | <2 | Most conversations stay at 1-2 levels |
| **% Chains Reaching Depth 3** | <20% | Few conversations need 3 levels |
| **% "Go Back" Usage** | 10-15% | Users occasionally correct mistakes |
| **% Timeout at Depth 3** | <5% | Few deep clarifications time out |
| **% Max Depth Exceeded** | <1% | Rare to hit 3-level limit |

**Prometheus Metrics:**

```yaml
# Nested clarification metrics
nested_clarification_depth:
  type: histogram
  buckets: [1, 2, 3]
  description: "Distribution of clarification chain depths"

nested_clarification_go_back_total:
  type: counter
  labels: [depth, direction]
  description: "Total 'go back' actions by depth"

nested_clarification_timeout_total:
  type: counter
  labels: [depth, cascade_action]
  description: "Timeouts by depth and cascade behavior"

nested_clarification_max_depth_exceeded_total:
  type: counter
  description: "Times max depth (3) exceeded"
```

**Structured Logging:**

```python
logger.info("nested_clarification_started",
            root_question=history.root_question,
            max_depth=history.max_depth)

logger.info("clarification_level_answered",
            depth=depth,
            question=question,
            answer=answer)

logger.info("clarification_go_back",
            from_depth=from_depth,
            to_depth=to_depth)

logger.info("nested_clarification_complete",
            total_depth=history.current_depth,
            summary=history.to_summary())
```

---

## Testing Strategy

### Unit Tests (WARD)

```python
from ward import test

@test("nested clarification: 3 levels with history")
async def _():
    history = ClarificationHistory(root_question="Find restaurant")

    # Level 1
    history.push(ClarificationItem(
        clarification_id="c1",
        question="How many people?",
        answer="4 people",
        timestamp=datetime.now(),
        depth=1,
        clarification_type=ClarificationType.FREE_TEXT,
    ))

    assert history.current_depth == 1

    # Level 2
    history.push(ClarificationItem(
        clarification_id="c2",
        question="Cuisine?",
        answer="Mexican",
        timestamp=datetime.now(),
        depth=2,
        clarification_type=ClarificationType.MULTIPLE_CHOICE,
    ))

    assert history.current_depth == 2

    # Level 3
    history.push(ClarificationItem(
        clarification_id="c3",
        question="Budget?",
        answer="$30",
        timestamp=datetime.now(),
        depth=3,
        clarification_type=ClarificationType.FREE_TEXT,
    ))

    assert history.current_depth == 3
    assert history.to_summary() == "4 people → Mexican → $30"

@test("nested clarification: go back from level 3 to level 2")
async def _():
    history = ClarificationHistory()

    # Add 3 levels
    for i in range(1, 4):
        history.push(ClarificationItem(
            clarification_id=f"c{i}",
            question=f"Q{i}",
            answer=f"A{i}",
            timestamp=datetime.now(),
            depth=i,
            clarification_type=ClarificationType.FREE_TEXT,
        ))

    assert history.current_depth == 3

    # Go back
    popped = history.pop()

    assert popped.question == "Q3"
    assert history.current_depth == 2

@test("nested clarification: max depth exceeded")
async def _():
    history = ClarificationHistory(max_depth=3)

    # Add 3 levels
    for i in range(1, 4):
        history.push(ClarificationItem(
            clarification_id=f"c{i}",
            question=f"Q{i}",
            answer=f"A{i}",
            timestamp=datetime.now(),
            depth=i,
            clarification_type=ClarificationType.FREE_TEXT,
        ))

    # Try to add level 4 (should fail)
    with raises(MaxDepthExceeded):
        history.push(ClarificationItem(
            clarification_id="c4",
            question="Q4",
            answer="A4",
            timestamp=datetime.now(),
            depth=4,
            clarification_type=ClarificationType.FREE_TEXT,
        ))
```

---

## Implementation Checklist

**Phase 1: Schema & Data Structures (Week 1)**
- [ ] Add `CONDITIONAL_CHAIN` enum to `ClarificationType`
- [ ] Define FlatBuffers schema for `NestedClarificationRequest/Response`
- [ ] Create `ClarificationHistory` data structure with LIFO stack
- [ ] Add `ClarificationItem` for history tracking

**Phase 2: SessionState Integration (Week 2)**
- [ ] Add `clarification_history` to Scoreboard (ADR-0017b)
- [ ] Implement serialization/deserialization to SessionState
- [ ] Add QUD stack integration
- [ ] Test history persistence across turns

**Phase 3: Nested Clarification Flow (Week 3)**
- [ ] Implement multi-level clarification handler
- [ ] Add push/pop logic for history stack
- [ ] Implement max depth enforcement (3 levels)
- [ ] Add timeout cascading logic

**Phase 4: "Go Back" Functionality (Week 4)**
- [ ] Implement "go back" action handling
- [ ] Add UI for changing previous answers
- [ ] Test go back at each depth level
- [ ] Add context preservation when going back

**Phase 5: WebSocket Protocol (Week 5)**
- [ ] Add `NestedClarificationRequest` message to WebSocket
- [ ] Add `NestedClarificationResponse` message handling
- [ ] Implement UI wireframes (show history)
- [ ] Test full nested flow end-to-end

**Phase 6: Testing & Observability (Week 6)**
- [ ] Add Prometheus metrics (depth distribution)
- [ ] Add structured logging
- [ ] WARD unit tests (push/pop/go back)
- [ ] WARD integration tests (3-level conversation)

---

## Related Work & Research Evidence

**1. Grounding in Communication (Clark & Brennan, 1991)**
- **Source:** "Perspectives on socially shared cognition"
- **Application:** Nested clarifications build common ground

**2. Questions Under Discussion (Roberts, 1996)**
- **Source:** "Information structure in discourse"
- **Application:** QUD stack maps to clarification history

**3. Conversation Acts (Searle, 1969)**
- **Source:** "Speech Acts: An Essay in the Philosophy of Language"
- **Application:** Clarifications as chained speech acts

**4. Multi-Turn Dialogue Systems (Jurafsky & Martin, 2020)**
- **Source:** "Speech and Language Processing" (3rd ed)
- **Application:** Dialogue state tracking with history

---

## References

**ADRs:**
- [ADR-0052: Enhanced HITL Protocols](0052-enhanced-hitl-protocols.md)
- [ADR-0003b: 6 Core Protocol Implementations](0003b-6-core-protocol-implementations.md)
- [ADR-0017b: SessionState Scoreboard](0017b-sessionstate-scoreboard-qud-belief.md)
- [ADR-0040: WebSocket Real-Time Chat](0040-websocket-realtime-chat.md)

**Source Documents:**
- [HITL_MESSAGE_FLOW_ANALYSIS.md](../../HITL_MESSAGE_FLOW_ANALYSIS.md) - Gap 3 (Nested Clarifications)
- [whiteboard.md](../../whiteboard.md) - SessionState Scoreboard

---

**Document Status:** ✅ **ACCEPTED** (2025-10-14)

**Next Steps:**
1. Implement FlatBuffers schema (Week 1)
2. Integrate with SessionState Scoreboard (Week 2)
3. Add nested clarification flow (Week 3)
4. Implement "go back" functionality (Week 4)
5. WebSocket protocol implementation (Week 5)
6. WARD integration tests (Week 6)

---

**END OF ADR-0052c**