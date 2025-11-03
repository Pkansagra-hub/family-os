---
adr_number: '0065'
title: Product Craft & UX Micro-Interactions
status: PROPOSED
date_created: '2025-11-03'
date_updated: '2025-11-03'
authors:
- K1 Architecture Team
affected_layers:
- layer1_input
- layer2_orchestration
- layer3_execution
- layer4_runtime
- layer5_infrastructure
affected_modules: []
concerns:
- architecture
- compliance
- cost
- modularity
- observability
- performance
- privacy
- scalability
- security
- testing
- ux
supersedes: []
superseded_by: []
related_adrs:
- ADR-0015
- ADR-0015d
- ADR-0017
- ADR-0021
- ADR-0026
- ADR-0052b
- ADR-0056
- ADR-0065
- ADR-0065a
- ADR-0065b
- ADR-0065c
- ADR-0065d
- ADR-0066
implementation_status: COMPLETED
implementation_date: null
implementation_phase: null
related_contracts: []
related_diagrams: []
research_citations: []
propagation:
  triggers:
  - Adding new module to any layer
  - Changing layer dependency rules
  - Modifying system architecture
  - Performance requirement changes
  affected_adrs:
  - ADR-0015
  - ADR-0015d
  - ADR-0017
  - ADR-0021
  - ADR-0026
  - ADR-0052b
  - ADR-0056
  - ADR-0065
  - ADR-0065a
  - ADR-0065b
  - ADR-0065c
  - ADR-0065d
  - ADR-0066
  affected_contracts:
  - k1/contracts/flatbuffers/layer3_execution/mcp_message.fbs
  - k1/contracts/flatbuffers/layer3_execution/mcp_resource_request.fbs
  - k1/contracts/flatbuffers/layer3_execution/mcp_resource_response.fbs
  - k1/contracts/flatbuffers/layer3_execution/mcp_tool_discovery.fbs
  - k1/contracts/flatbuffers/layer3_execution/model_cache_entry.fbs
  - k1/contracts/flatbuffers/layer3_execution/model_request.fbs
  - k1/contracts/flatbuffers/layer3_execution/model_response.fbs
  - k1/contracts/flatbuffers/layer3_execution/model_stream_chunk.fbs
  - k1/contracts/flatbuffers/layer3_execution/stream_chunk.fbs
  - k1/contracts/flatbuffers/layer3_execution/stream_config.fbs
  affected_tests: []
---


# ADR-0065: Product Craft & UX Micro-Interactions

**Status:** Proposed
**Date:** 2025-10-15
**Tier:** 3
**Umbrella ADR**

## Context

K1 Intelligence Module provides a sophisticated conversational interface with voice and text modalities, but production-quality user experience requires attention to micro-interactions that shape perceived responsiveness and delight. The challenge: **how do we implement UX polish that makes the system feel fast, responsive, and thoughtful even under real-world latency constraints?**

**Problem Statement:**

While core functionality exists (WebSocket streaming ADR-0015, voice pipeline ADR-0056, intent classification ADR-0021), the system lacks production-grade UX patterns that define modern conversational interfaces:

- ❌ **No typing indicators**: Users stare at blank screen waiting for response (perceived latency feels longer)
- ❌ **No progressive rendering**: Text appears all-at-once instead of streaming (feels robotic)
- ❌ **No session continuity**: Can't resume conversation on different device (frustrating context loss)
- ❌ **No quick actions**: Users must type full responses instead of tapping suggested replies (friction)
- ❌ **No costly action safeguards**: Irreversible operations (money transfer, data deletion) lack explicit confirmation UX

**Current Industry Practice:**

Modern conversational UIs (ChatGPT, Claude, Gemini, Alexa, Google Assistant) provide:
- **Typing indicators**: "Assistant is typing..." with animated dots (perceived latency reduction)
- **Streaming text**: Token-by-token rendering with smooth scroll (feels responsive even at 150ms TTFT)
- **Session sync**: "Continue on phone" cross-device handoff (Google Assistant, Alexa multi-room)
- **Quick replies**: 3-5 suggested action chips (WhatsApp, Messenger, RCS)
- **Explicit confirmations**: "Say YES to confirm transfer" for irreversible actions (Alexa shopping, Google Pay)

**K1 Requirements:**

- **Perceived responsiveness**: <200ms TTFT perception (actual may be 150ms, but typing indicator makes it feel instant)
- **Cross-device continuity**: Resume conversation across phone/tablet/desktop with consent
- **Reduced friction**: Quick action chips reduce typing by 60-80% for common replies
- **Safety**: Zero-tolerance for accidental irreversible actions (requires explicit typed confirmation)

---

## Decision

We adopt a **3-tier UX framework** for micro-interactions: Client-side animations (instant feedback) → Protocol extensions (WebSocket) → Server-side orchestration (K1 coordination).

### **Decision Matrix**

**Five alternatives evaluated for UX micro-interaction implementation:**

| Alternative | Responsiveness | Safety | Cross-Device | Complexity | Client Burden | K1 Fit |
|-------------|----------------|--------|--------------|------------|---------------|--------|
| **1. No Micro-Interactions** | ❌ Poor | ❌ Unsafe | ❌ No | ✅ Low | ✅ Minimal | ❌ 2/10 |
| **2. Client-Only** | ⚠️ Moderate | ⚠️ Partial | ❌ No | ✅ Low | ❌ Heavy | ⚠️ 4/10 |
| **3. Server-Only** | ❌ Laggy | ✅ Good | ✅ Yes | ✅ Low | ✅ Minimal | ⚠️ 5/10 |
| **4. Protocol Extensions** | ⚠️ Good | ✅ Good | ⚠️ Limited | ⚠️ Medium | ⚠️ Moderate | ⚠️ 7/10 |
| **5. 3-Tier Hybrid** | ✅ Excellent | ✅ Excellent | ✅ Yes | ⚠️ High | ✅ Balanced | ✅ **9/10** |

**Decision: Alternative 5 (3-Tier Hybrid) selected.**

**Key Decision Factors:**

1. **Client-side animations**: Instant typing indicators, scroll anchoring (no server round-trip needed)
2. **Protocol extensions**: WebSocket events for typing state, quick actions, device sync
3. **Server orchestration**: K1 generates quick actions, manages device handoff, enforces costly action confirmations
4. **Layered fallback**: Works gracefully even if client/server features unavailable

**Rejection Rationale:**

- **Alternative 1 (No Micro-Interactions)**: Unacceptable UX quality for production system
- **Alternative 2 (Client-Only)**: Cannot handle cross-device sync or server-enforced safety
- **Alternative 3 (Server-Only)**: Too laggy (every animation requires server round-trip)
- **Alternative 4 (Protocol Extensions)**: Good but misses client-side instant feedback

---

### **Core Principles**

**1. Instant Feedback (No Server Round-Trip)**
- Typing indicators appear immediately (<16ms, 1 frame) when user finishes input
- Scroll anchoring prevents content jumping during streaming
- Button press feedback (<100ms visual response)
- **Rationale**: Perceived responsiveness requires <100ms feedback (Nielsen Norman Group)

**2. Progressive Disclosure (Streaming Over Batch)**
- Text renders token-by-token (not all-at-once)
- Quick action chips appear after first sentence of response
- Costly action confirmation UI slides in progressively
- **Rationale**: Streaming creates perception of continuous progress vs waiting

**3. Cross-Device Continuity (Session Portability)**
- Session state syncs across devices via K0 bridge
- "Continue on [device]" prompt when multiple devices available
- Device handoff preserves conversation context (last 10 turns)
- **Rationale**: Modern users expect multi-device experiences (Google, Apple ecosystems)

**4. Reduced Friction (Quick Actions Over Typing)**
- 3-5 suggested reply chips for >60% of agent questions
- Accessibility-first (keyboard navigation, screen reader support)
- Dynamic generation based on conversation context
- **Rationale**: Quick actions reduce user effort by 60-80% (industry benchmarks)

**5. Safety-First Confirmations (Explicit Typed Confirmation)**
- Irreversible actions require explicit typed phrase (e.g., "CONFIRM")
- Read-back of action details before confirmation
- Receipt delivery after completion
- **Rationale**: Zero-tolerance for accidental money transfers, data deletion

**6. Graceful Degradation (Works Without JS/WebSocket)**
- Basic text chat works with plain HTTP POST (no WebSocket required)
- Quick actions degrade to numbered list ("Reply: 1, 2, 3")
- Typing indicators optional (system works without them)
- **Rationale**: Accessibility and low-bandwidth scenarios

---

## Architecture Components

### **Component Overview**

```
┌─────────────────────────────────────────────────────────────────┐
│                      CLIENT LAYER (Browser/App)                  │
├─────────────────────────────────────────────────────────────────┤
│ • Typing Indicator (CSS animation, <16ms)                       │
│ • Progressive Text Renderer (token-by-token)                    │
│ • Scroll Anchor (prevent jump during streaming)                 │
│ • Quick Action Chips (button UI, keyboard nav)                  │
│ • Costly Action Modal (confirmation dialog)                     │
└─────────────────────────────────────────────────────────────────┘
                              ▼ WebSocket Events
┌─────────────────────────────────────────────────────────────────┐
│                   PROTOCOL LAYER (WebSocket/SSE)                 │
├─────────────────────────────────────────────────────────────────┤
│ • typing_start / typing_stop events                             │
│ • token_stream (text streaming)                                 │
│ • quick_actions (chip suggestions)                              │
│ • device_handoff (session transfer)                             │
│ • costly_action_confirm (explicit confirmation)                 │
└─────────────────────────────────────────────────────────────────┘
                              ▼ K1 Orchestration
┌─────────────────────────────────────────────────────────────────┐
│                   SERVER LAYER (K1 Intelligence)                 │
├─────────────────────────────────────────────────────────────────┤
│ • UX Orchestrator (coordinates micro-interactions)              │
│ • Quick Action Generator (intent → chip suggestions)            │
│ • Device Registry (active devices per user)                     │
│ • Costly Action Enforcer (confirmation validation)              │
│ • Session Sync Manager (K0 bridge for device handoff)           │
└─────────────────────────────────────────────────────────────────┘
```

**Key Modules:**

- **k1/interfaces/ux_orchestrator.py**: Coordinates all UX micro-interactions
- **k1/interfaces/quick_action_generator.py**: Generates context-aware quick reply chips
- **k1/interfaces/device_registry.py**: Tracks active devices per user session
- **k1/interfaces/costly_action_enforcer.py**: Validates explicit confirmations
- **k1/interfaces/session_sync_manager.py**: Handles device handoff via K0

---

## Alternatives Considered

### **Alternative 1: No Micro-Interactions (Minimal UX)**

**Description:**
- No typing indicators, text appears all-at-once
- No quick actions, users must type all responses
- No cross-device sync, separate sessions per device
- No special confirmations for costly actions

**Pros:**
- ✅ Zero implementation complexity
- ✅ Minimal client requirements (works on any browser)
- ✅ No protocol extensions needed

**Cons:**
- ❌ **Poor perceived responsiveness**: Users stare at blank screen during response generation
- ❌ **High friction**: Users must type full sentences for common replies
- ❌ **No cross-device continuity**: Conversation context lost when switching devices
- ❌ **Safety risk**: Accidental irreversible actions (no safeguards)

**Rejection Reason:** Unacceptable UX quality for production conversational system. Modern users expect typing indicators, quick replies, and cross-device continuity (industry standard).

---

### **Alternative 2: Client-Only Micro-Interactions**

**Description:**
- All UX logic in client JavaScript (no server coordination)
- Client generates fake typing indicators (setTimeout-based)
- Client manages session storage (localStorage for device handoff)
- Client-side validation for costly actions

**Implementation:**
```javascript
// Client-side typing indicator
function showTypingIndicator() {
  const indicator = document.createElement('div');
  indicator.className = 'typing-indicator';
  indicator.innerHTML = '<span></span><span></span><span></span>'; // Animated dots
  chatContainer.appendChild(indicator);

  // Fake delay (no server signal)
  setTimeout(() => {
    indicator.remove();
    showResponse(responseText);
  }, 1500); // Hardcoded 1.5s delay
}

// Client-side session sync (localStorage)
function syncSession() {
  const sessionState = {
    conversationHistory: getHistory(),
    lastUpdated: Date.now()
  };
  localStorage.setItem('k1_session', JSON.stringify(sessionState));
}
```

**Pros:**
- ✅ Instant responsiveness (no server round-trip)
- ✅ Simple implementation (just JavaScript)
- ✅ Works offline (localStorage-based sync)

**Cons:**
- ❌ **No real typing state**: Fake indicator (always 1.5s regardless of actual processing time)
- ❌ **Limited device sync**: localStorage only works within same browser, no cross-device
- ❌ **No server enforcement**: Costly action validation bypassable (client-side only)
- ❌ **Heavy client burden**: All UX logic in JavaScript (large bundle size, slow on mobile)

**Rejection Reason:** Cannot handle cross-device sync (localStorage browser-scoped) or enforce server-side safety checks. Fake typing indicators feel disconnected from actual system state.

---

### **Alternative 3: Server-Only Micro-Interactions**

**Description:**
- All UX logic server-side (K1 orchestrator)
- Typing indicators generated as HTML snippets from server
- Quick actions rendered server-side (HTML buttons)
- Device handoff managed entirely by K0 bridge

**Implementation:**
```python
# Server-side typing indicator (HTML snippet)
async def send_typing_indicator(session_id: str):
    html = """
    <div class="typing-indicator">
      <span></span><span></span><span></span>
    </div>
    """
    await websocket.send_text(html)

    # Wait for response generation
    response = await generate_response(session_id)

    # Send response (replaces typing indicator)
    await websocket.send_text(f'<div class="response">{response}</div>')
```

**Pros:**
- ✅ Server has full control (no client-side logic)
- ✅ Secure (all validation server-side)
- ✅ Easy to implement cross-device sync (K0 bridge)

**Cons:**
- ❌ **Laggy**: Every animation requires server round-trip (adds 50-100ms latency)
- ❌ **No instant feedback**: Typing indicator delayed by network latency
- ❌ **Heavy server load**: Server generates HTML for every UI update
- ❌ **Poor offline experience**: Requires active connection for all interactions

**Rejection Reason:** Too laggy for instant feedback. Typing indicators should appear <100ms after user input, but server round-trip adds 50-100ms+ latency. Violates perceived responsiveness requirement.

---

### **Alternative 4: Protocol Extensions Only**

**Description:**
- Extend WebSocket protocol with UX events (typing_start, token_stream, quick_actions)
- Client renders based on protocol events (no hardcoded delays)
- Server sends structured events (JSON), client interprets

**Protocol:**
```json
// Server → Client: Typing indicator
{
  "event": "typing_start",
  "session_id": "s_123",
  "timestamp": 1729012345678
}

// Server → Client: Streamed token
{
  "event": "token_stream",
  "token": "Hello",
  "is_final": false
}

// Server → Client: Quick actions
{
  "event": "quick_actions",
  "actions": [
    {"id": "qa_1", "label": "Yes, continue", "intent": "affirmative"},
    {"id": "qa_2", "label": "No, stop", "intent": "negative"},
    {"id": "qa_3", "label": "Tell me more", "intent": "clarification"}
  ]
}
```

**Pros:**
- ✅ Real-time state sync (client reflects actual server state)
- ✅ Structured protocol (easy to extend, version)
- ✅ Language-agnostic (any client can implement)

**Cons:**
- ⚠️ **Moderate complexity**: Requires protocol design, client/server implementation
- ⚠️ **Still has latency**: Typing indicator delayed by network round-trip (50-100ms)
- ⚠️ **No instant feedback**: Client must wait for server signal

**Rejection Reason:** Good foundation but missing instant client-side feedback. Typing indicators should appear <16ms (1 frame) after user input, but protocol-only approach adds 50-100ms network latency.

---

### **Alternative 5: 3-Tier Hybrid (Client + Protocol + Server) — SELECTED**

**Description:**
- **Tier 1 (Client-side)**: Instant animations (typing indicator, scroll anchor) <16ms
- **Tier 2 (Protocol)**: WebSocket events for state sync (typing_start, quick_actions, device_handoff)
- **Tier 3 (Server)**: K1 orchestration (generate quick actions, enforce costly confirmations, manage device registry)

**Implementation:**

**Client-side (instant feedback):**
```javascript
// Tier 1: Instant typing indicator (no server signal needed)
function onUserInput(text) {
  // Show typing indicator immediately (<16ms)
  showTypingIndicatorInstant();

  // Send message to server
  websocket.send(JSON.stringify({
    event: 'user_message',
    text: text
  }));
}

// Typing indicator appears instantly (CSS animation)
function showTypingIndicatorInstant() {
  const indicator = document.createElement('div');
  indicator.className = 'typing-indicator';
  indicator.innerHTML = `
    <span class="dot"></span>
    <span class="dot"></span>
    <span class="dot"></span>
  `;
  chatContainer.appendChild(indicator);
}
```

**Protocol (state sync):**
```json
// Server → Client: Real typing state (confirms instant indicator was correct)
{
  "event": "typing_confirmed",
  "session_id": "s_123",
  "estimated_duration_ms": 1200
}

// Server → Client: Token streaming (progressive text)
{
  "event": "token_stream",
  "token": "Hello, ",
  "is_final": false
}

// Server → Client: Quick actions (generated by K1)
{
  "event": "quick_actions",
  "actions": [
    {"id": "qa_1", "label": "✅ Yes, continue", "value": "yes"},
    {"id": "qa_2", "label": "❌ No, cancel", "value": "no"},
    {"id": "qa_3", "label": "💬 Tell me more", "value": "clarify"}
  ],
  "expires_in_ms": 30000
}
```

**Server orchestration:**
```python
# Tier 3: K1 generates quick actions based on conversation context
async def generate_quick_actions(session_id: str, agent_response: str) -> list[QuickAction]:
    """Generate 3-5 contextual quick reply chips"""

    # 1. Extract intent from agent response
    intent = await intent_classifier.classify(agent_response)

    # 2. Generate appropriate quick actions
    if intent == "yes_no_question":
        return [
            QuickAction(id="qa_1", label="✅ Yes", value="yes", intent="affirmative"),
            QuickAction(id="qa_2", label="❌ No", value="no", intent="negative")
        ]
    elif intent == "multiple_choice":
        # Extract options from agent response
        options = extract_options(agent_response)
        return [
            QuickAction(id=f"qa_{i}", label=opt, value=opt, intent="selection")
            for i, opt in enumerate(options[:5])
        ]
    elif intent == "open_ended":
        return [
            QuickAction(id="qa_1", label="💬 Tell me more", value="clarify", intent="clarification"),
            QuickAction(id="qa_2", label="👍 Got it", value="acknowledge", intent="acknowledgment"),
            QuickAction(id="qa_3", label="⏭️ Next topic", value="continue", intent="continuation")
        ]
    else:
        return []  # No quick actions for this intent
```

**Pros:**
- ✅ **Instant responsiveness**: Client-side animations <16ms (no network latency)
- ✅ **Real state sync**: Protocol confirms/corrects instant feedback
- ✅ **Server control**: K1 orchestrates complex logic (quick actions, device handoff, safety)
- ✅ **Graceful degradation**: Works even if client/protocol features unavailable

**Cons:**
- ⚠️ **Complexity**: Requires coordination across 3 tiers
- ⚠️ **Client requirements**: JavaScript required for instant feedback
- ⚠️ **Protocol versioning**: Must maintain backward compatibility

**Selection Reason:** Best balance of responsiveness (client-side instant feedback), control (server orchestration), and safety (server-enforced confirmations). Only alternative that meets <200ms perceived responsiveness requirement while maintaining server authority.

---

## Consequences

### **Positive Consequences**

**✅ Perceived Responsiveness (UX)**
- Typing indicators <16ms (instant feedback), TTFT perception <200ms
- Progressive text streaming (feels responsive even at 150ms TTFT)
- Quick actions reduce typing friction by 60-80%
- **Benefit**: Users perceive system as faster than actual latency

**✅ Cross-Device Continuity (Modern UX)**
- Resume conversation on different device with consent
- "Continue on [device]" prompt when multiple devices available
- Session state syncs via K0 bridge
- **Benefit**: Matches modern multi-device user expectations (Google, Apple ecosystems)

**✅ Safety & Explicit Confirmation (Zero Accidents)**
- Irreversible actions require explicit typed confirmation ("CONFIRM")
- Read-back of action details before confirmation
- Receipt delivery after completion
- **Benefit**: Zero accidental money transfers, data deletions (compliance with financial/healthcare regulations)

**✅ Reduced Cognitive Load (Interaction Design)**
- Quick action chips reduce decision-making burden
- Suggested replies eliminate "what do I say next?" friction
- Accessibility-first (keyboard navigation, screen reader support)
- **Benefit**: 60-80% reduction in user input effort (industry benchmark)

**✅ Graceful Degradation (Accessibility)**
- Basic text chat works without JavaScript
- Quick actions degrade to numbered list
- System functional even without WebSocket
- **Benefit**: Low-bandwidth scenarios, assistive technology compatibility

---

### **Negative Consequences**

**⚠️ Implementation Complexity**
- 3-tier architecture requires careful coordination
- **Mitigation**: Comprehensive integration tests (ADR-0066), protocol validation
- **Risk Level**: MEDIUM (requires 4-6 weeks implementation + testing)

**⚠️ Client Bundle Size**
- JavaScript for instant feedback adds ~50KB (gzipped)
- **Mitigation**: Code splitting, lazy loading for advanced features
- **Risk Level**: LOW (<5% page load time increase)

**⚠️ Protocol Versioning**
- WebSocket protocol extensions require backward compatibility
- **Mitigation**: Protocol version negotiation, feature detection
- **Risk Level**: MEDIUM (requires careful version management)

**⚠️ Device Registry Maintenance**
- Device registry can grow unbounded (zombie devices)
- **Mitigation**: 30-day device expiration, periodic cleanup
- **Risk Level**: LOW (routine maintenance task)

---

## Implementation Notes

### **Implementation Timeline**

**Phase 1 (Week 1): Client-Side Instant Feedback**
- Implement typing indicator (CSS animation)
- Implement progressive text renderer (token-by-token)
- Implement scroll anchor (prevent jumping)
- Unit tests, accessibility validation

**Phase 2 (Week 2): Protocol Extensions**
- Extend WebSocket protocol (typing_start, token_stream, quick_actions, device_handoff)
- Implement protocol version negotiation
- Integration tests with WebSocket (ADR-0015)

**Phase 3 (Week 3): Server Orchestration**
- Implement UX Orchestrator (k1/interfaces/ux_orchestrator.py)
- Implement Quick Action Generator (k1/interfaces/quick_action_generator.py)
- Implement Device Registry (k1/interfaces/device_registry.py)
- Integration tests with K1 orchestrator

**Phase 4 (Week 4): Costly Action Confirmation (ADR-0065d)**
- Implement Costly Action Enforcer (k1/interfaces/costly_action_enforcer.py)
- Implement explicit typed confirmation UX
- Implement read-back + receipt delivery
- Security audit, penetration testing

**Phase 5 (Week 5): Session Continuity (ADR-0065b)**
- Implement Session Sync Manager (k1/interfaces/session_sync_manager.py)
- Integrate with K0 bridge (ADR-0026)
- Implement "Continue on [device]" prompt
- Cross-device testing (phone, tablet, desktop)

**Phase 6 (Week 6): Polish & Performance**
- Performance optimization (bundle size, latency)
- Accessibility audit (WCAG 2.1 AA compliance)
- Load testing (1000+ concurrent users)
- User acceptance testing (UAT)

---

### **Success Metrics**

**Performance:**
- ✅ Typing indicator appears <50ms after user input (P95)
- ✅ TTFT perception <200ms (user study)
- ✅ Token streaming latency <50ms per token (P95)
- ✅ Quick action generation <100ms (P95)
- ✅ Device handoff latency <500ms (P95)

**User Experience:**
- ✅ 60-80% of responses use quick actions (adoption rate)
- ✅ <1% accidental costly action confirmations (safety)
- ✅ >90% user satisfaction with responsiveness (survey)
- ✅ >80% cross-device handoff success rate

**Accessibility:**
- ✅ WCAG 2.1 AA compliance (keyboard nav, screen reader support)
- ✅ Works without JavaScript (graceful degradation)
- ✅ Low-bandwidth support (<1KB per turn overhead)

---

## References

### **Research & Industry Standards**

1. **Nielsen Norman Group (2020)**
   "Response Times: The 3 Important Limits"
   - 0.1s: Instant feedback threshold
   - 1.0s: User flow uninterrupted
   - 10s: Keep attention threshold
   **Relevance**: Typing indicator <100ms requirement

2. **Google Material Design (2023)**
   "Motion: Speed"
   - 100-300ms: Quick actions
   - 300-500ms: Complex animations
   **Relevance**: Progressive text rendering timing

3. **WCAG 2.1 (2018)**
   "Web Content Accessibility Guidelines"
   - Guideline 2.1: Keyboard Accessible
   - Guideline 4.1: Compatible (assistive technology)
   **Relevance**: Quick action accessibility, screen reader support

4. **WebSocket Protocol RFC 6455 (2011)**
   "The WebSocket Protocol"
   **Relevance**: Protocol extension patterns

5. **Apple Human Interface Guidelines (2023)**
   "Multi-Device Experiences"
   - Handoff: Continue activity on another device
   - Universal Clipboard: Share content across devices
   **Relevance**: Session continuity patterns

---

### **Related ADRs**

- [ADR-0015: WebSocket Ingress](0015-websocket-ingress.md) — Protocol foundation
- [ADR-0015d: Server-Sent Events Streaming](0015d-sse-streaming.md) — Token streaming
- [ADR-0021: Intent Classification](0021-intent-classification.md) — Quick action generation context
- [ADR-0017: SessionState Structure](0017-sessionstate-structure.md) — Device registry storage
- [ADR-0026: K0 Bridge Batching](0026-k0-bridge-batching.md) — Session continuity sync
- [ADR-0052b: RED Band Approval](0052b-red-band-approval.md) — Costly action two-person rule
- [ADR-0065a: Streaming Text & Typing Indicators](0065a-streaming-text-typing.md) — Client-side implementation
- [ADR-0065b: Session Continuity & Device Handoff](0065b-session-continuity-device-handoff.md) — Cross-device sync
- [ADR-0065c: Quick Actions & Suggested Replies](0065c-quick-actions-suggested-replies.md) — Contextual chips
- [ADR-0065d: Costly Action Confirmation](0065d-costly-action-confirmation.md) — Safety-critical UX

---

### **Architecture Diagrams**

- `architecture_diagrams/k1_ux_micro_interactions.mmd` — 3-tier UX architecture
- `architecture_diagrams/k1_device_registry.mmd` — Device handoff flow
- `docs/whiteboard.md` (lines TBD) — UX micro-interaction specifications

---

**Sub-ADRs:**
- 0065a: Streaming Text & Typing Indicators
- 0065b: Session Continuity & Device Handoff
- 0065c: Quick Actions & Suggested Replies
- 0065d: Costly Action Confirmation (Safety-Critical)

**Status:** Umbrella ADR complete, sub-ADRs pending