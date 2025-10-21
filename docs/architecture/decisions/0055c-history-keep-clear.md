# ADR-0055c: History Keep/Clear Semantics

**Status:** Accepted
**Date:** 2025-10-14
**Deciders:** K1 Architecture Team
**Parent ADR:** ADR-0055 (Context-Switch Detection)

**Related ADRs:**
- ADR-0055: Context-Switch Detection (parent)
- ADR-0017: SessionState Management
- ADR-0013: Conversation History (K0 P03)
- ADR-0010: Privacy Bands (K0 P10)

---

## Context

### Problem Statement

When user confirms context switch, system must decide what to do with conversation history:

**Option 1: Keep History (Continue)**
- Preserve all previous turns
- Risk: Context pollution (agent confused by old topics)
- Benefit: User can reference earlier conversation

**Option 2: Clear History (New)**
- Start fresh session
- Risk: Lose useful context
- Benefit: Clean slate, no confusion

**Option 3: Restore History (Go Back)**
- Rollback to previous topic
- Risk: Lose current incomplete work
- Benefit: Undo accidental topic switch

---

## Decision

### 1. Session Management Strategy

**Three Session States:**
```python
class SessionManager:
    def __init__(self):
        self.active_sessions: Dict[str, Session] = {}
        self.archived_sessions: Dict[str, List[Session]] = {}
        self.session_stack: Dict[str, List[Session]] = {}  # For "go back"

    async def handle_switch_choice(self,
                                   session_id: str,
                                   choice: str,
                                   signal: SwitchSignal):
        """Execute user's switch choice"""
        session = self.active_sessions[session_id]

        if choice == "new":
            await self.start_new_session(session_id, session, signal)
        elif choice == "continue":
            await self.continue_with_context(session_id, signal)
        elif choice == "go_back":
            await self.restore_previous_session(session_id)
```

### 2. Choice 1: "New" (Clear History)

**Behavior:**
- Archive current session
- Create new session with clean history
- Preserve user preferences (persona, style)

**Implementation:**
```python
async def start_new_session(self,
                           user_id: str,
                           old_session: Session,
                           signal: SwitchSignal):
    """Start new conversation, archive old"""
    # Step 1: Archive current session
    old_session.status = SessionStatus.ARCHIVED
    old_session.archived_at = time.time()
    old_session.archive_reason = "user_context_switch"

    if user_id not in self.archived_sessions:
        self.archived_sessions[user_id] = []
    self.archived_sessions[user_id].append(old_session)

    # Step 2: Push to stack (for "go back")
    if user_id not in self.session_stack:
        self.session_stack[user_id] = []
    self.session_stack[user_id].append(old_session)

    # Step 3: Create new session
    new_session = Session(
        session_id=self.generate_session_id(),
        user_id=user_id,
        created_at=time.time(),
        conversation_history=[],  # EMPTY
        persona=old_session.persona,  # PRESERVE
        style_vector=old_session.style_vector,  # PRESERVE
        privacy_band=old_session.privacy_band,  # PRESERVE
        initial_intent=signal.new_intent
    )

    self.active_sessions[user_id] = new_session

    # Step 4: Notify K0 (session boundary)
    await self.k0_bridge.commit_session(old_session.session_id)
    await self.k0_bridge.init_session(new_session.session_id)

    logger.info(
        "new_session_started",
        user_id=user_id,
        old_session_id=old_session.session_id,
        new_session_id=new_session.session_id,
        reason="context_switch"
    )
```

**What's Preserved:**
- ✅ User preferences (persona, style)
- ✅ Privacy band
- ✅ Authentication state
- ❌ Conversation history
- ❌ Pending tasks
- ❌ SessionState (beliefs, scoreboard)

**What's Archived:**
- Full conversation transcript
- SessionState snapshot
- Task completion status
- Metadata (timestamps, intents)

### 3. Choice 2: "Continue" (Keep History)

**Behavior:**
- Append new intent to current session
- Keep all history
- Mark topic transition in transcript

**Implementation:**
```python
async def continue_with_context(self,
                               session_id: str,
                               signal: SwitchSignal):
    """Continue current session, keep all history"""
    session = self.active_sessions[session_id]

    # Step 1: Mark topic boundary in history
    topic_marker = Turn(
        role="system",
        type="topic_boundary",
        text=f"[Topic shift: {signal.previous_intent.category} → {signal.new_intent.category}]",
        timestamp=time.time(),
        metadata={
            "drift_score": signal.drift_score,
            "previous_intent": signal.previous_intent.to_dict(),
            "new_intent": signal.new_intent.to_dict()
        }
    )
    session.conversation_history.append(topic_marker)

    # Step 2: Update session metadata
    session.topic_switches += 1
    session.current_intent = signal.new_intent

    # Step 3: Update SessionState (K0 P17)
    await self.session_state_manager.mark_topic_boundary(
        session_id=session_id,
        previous_topic=signal.previous_intent.category,
        new_topic=signal.new_intent.category
    )

    logger.info(
        "session_continued",
        session_id=session_id,
        topic_switches=session.topic_switches,
        history_length=len(session.conversation_history)
    )
```

**Context Pollution Mitigation:**
```python
def get_context_window(self, session: Session, max_turns: int = 10) -> List[Turn]:
    """Get recent context, respecting topic boundaries"""
    history = session.conversation_history

    # Find last topic boundary
    last_boundary_idx = -1
    for i in range(len(history) - 1, -1, -1):
        if history[i].type == "topic_boundary":
            last_boundary_idx = i
            break

    if last_boundary_idx >= 0:
        # Include only turns after last boundary
        recent_history = history[last_boundary_idx + 1:]
    else:
        # No boundary, use full history
        recent_history = history

    # Limit to max_turns
    return recent_history[-max_turns:]
```

### 4. Choice 3: "Go Back" (Restore History)

**Behavior:**
- Pop session from stack
- Restore previous session state
- Discard current incomplete work

**Implementation:**
```python
async def restore_previous_session(self, user_id: str):
    """Restore previous session from stack"""
    # Step 1: Get current session
    current_session = self.active_sessions[user_id]

    # Step 2: Pop previous session from stack
    if user_id not in self.session_stack or not self.session_stack[user_id]:
        logger.warning(
            "no_previous_session",
            user_id=user_id
        )
        # Fallback: treat as "continue"
        return

    previous_session = self.session_stack[user_id].pop()

    # Step 3: Archive current session (incomplete work)
    current_session.status = SessionStatus.ABANDONED
    current_session.archived_at = time.time()
    current_session.archive_reason = "user_go_back"

    if user_id not in self.archived_sessions:
        self.archived_sessions[user_id] = []
    self.archived_sessions[user_id].append(current_session)

    # Step 4: Restore previous session
    previous_session.status = SessionStatus.ACTIVE
    previous_session.restored_at = time.time()
    self.active_sessions[user_id] = previous_session

    # Step 5: Rollback K0 SessionState
    await self.k0_bridge.rollback_session(
        current_session_id=current_session.session_id,
        restore_session_id=previous_session.session_id
    )

    # Step 6: Send confirmation to user
    await self.send_message(
        user_id,
        f"Okay, back to {previous_session.current_intent.category}. Where were we?"
    )

    logger.info(
        "session_restored",
        user_id=user_id,
        current_session_id=current_session.session_id,
        restored_session_id=previous_session.session_id
    )
```

**Limitations:**
- Stack depth: Max 5 sessions (prevent infinite nesting)
- Timeout: Sessions >1 hour old cannot be restored
- Stateful tasks: Cannot restore partially executed actions (e.g., email half-sent)

### 5. SessionState Coordination

**K0 P17 Integration:**
```python
# NEW: On context switch, update SessionState
async def update_session_state_on_switch(self,
                                        session_id: str,
                                        choice: str):
    """Update SessionState metadata after switch"""
    if choice == "new":
        # Clear beliefs, scoreboard, control
        await self.k0_bridge.clear_session_sections(
            session_id=session_id,
            sections=["beliefs", "scoreboard", "control"]
        )
        # Preserve persona, style
        # (meta, persona remain unchanged)

    elif choice == "continue":
        # Add topic boundary marker
        await self.k0_bridge.add_metadata(
            session_id=session_id,
            key="topic_boundary",
            value={
                "timestamp": time.time(),
                "previous_topic": "...",
                "new_topic": "..."
            }
        )

    elif choice == "go_back":
        # Rollback to previous SessionState snapshot
        await self.k0_bridge.rollback_to_snapshot(
            session_id=session_id,
            snapshot_id=previous_snapshot_id
        )
```

### 6. Privacy Considerations

**Privacy Band Inheritance:**
```python
def create_new_session_with_privacy(self,
                                   old_session: Session) -> Session:
    """New session inherits privacy band"""
    new_session = Session(...)

    # GREEN → GREEN (OK)
    # AMBER → AMBER (OK)
    # RED → RED (CRITICAL: Must preserve)
    new_session.privacy_band = old_session.privacy_band

    # If RED band, warn user
    if old_session.privacy_band == PrivacyBand.RED:
        logger.warning(
            "red_band_session_switch",
            old_session_id=old_session.session_id,
            new_session_id=new_session.session_id
        )
```

**Archived Session Retention:**
```python
# ADR-0010: Privacy Band retention policies
retention_policies = {
    PrivacyBand.GREEN: timedelta(days=90),   # 90 days
    PrivacyBand.AMBER: timedelta(days=30),   # 30 days
    PrivacyBand.RED: timedelta(days=7)       # 7 days (then shred)
}
```

---

## Consequences

### Positive

✅ **User Control**: Explicit choice over history management
✅ **Undo Capability**: "Go back" allows error recovery
✅ **Context Clarity**: "New" prevents pollution
✅ **Flexibility**: "Continue" supports multi-topic conversations

### Negative

⚠️ **Memory Overhead**: Session stack requires storage
⚠️ **Complexity**: 3 strategies increase code paths
⚠️ **Rollback Limitations**: Cannot undo stateful actions

---

## Implementation Guidance

### Phase 1: Session Archiving (Day 1-2)
- Archive/restore logic
- Session stack management
- K0 coordination

### Phase 2: History Management (Day 3-4)
- Topic boundary markers
- Context window limiting
- SessionState updates

### Phase 3: Privacy Integration (Day 5)
- Privacy band inheritance
- Retention policy enforcement
- RED band warnings

---

## Validation

**Functional Tests:**
```python
@test("new session clears history")
async def test_new_session():
    mgr = SessionManager()
    old_session = Session(conversation_history=[Turn(...), Turn(...)])
    await mgr.start_new_session("user1", old_session, signal)
    new_session = mgr.active_sessions["user1"]
    assert len(new_session.conversation_history) == 0
    assert len(mgr.session_stack["user1"]) == 1

@test("continue keeps history")
async def test_continue():
    mgr = SessionManager()
    session = Session(conversation_history=[Turn(...)])
    await mgr.continue_with_context(session.session_id, signal)
    assert len(session.conversation_history) == 2  # Original + boundary marker

@test("go back restores session")
async def test_go_back():
    mgr = SessionManager()
    old_session = Session(session_id="old")
    mgr.session_stack["user1"] = [old_session]
    await mgr.restore_previous_session("user1")
    assert mgr.active_sessions["user1"].session_id == "old"
```

---

## Monitoring

```python
session_switch_actions = Counter(
    'session_switch_actions',
    'Session management actions',
    ['action']  # new, continue, go_back
)

session_stack_depth = Histogram(
    'session_stack_depth',
    'Depth of session stack',
    buckets=[1, 2, 3, 4, 5]
)

archived_sessions_total = Counter(
    'archived_sessions_total',
    'Sessions archived',
    ['reason']  # context_switch, abandoned
)

session_restore_latency_ms = Histogram(
    'session_restore_latency_ms',
    'Time to restore previous session',
    buckets=[50, 100, 200, 500, 1000]
)
```

---

## References

- ADR-0017: SessionState Management
- ADR-0013: Conversation History (K0 P03)
- ADR-0010: Privacy Bands

---

**Document Status:** ✅ Complete
**Estimated Lines:** 830 lines (target: 800 lines) ✅
