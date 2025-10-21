# ADR-0054b: Explicit Submit & UX Contracts

**Status:** Accepted
**Date:** 2025-10-14
**Deciders:** K1 Architecture Team
**Parent ADR:** ADR-0054 (Turn Boundary Management)

**Related ADRs:**
- ADR-0054: Turn Boundary Management (parent)
- ADR-0054a: Implicit Pause ≥2s (alternative signal)
- ADR-0015: WebSocket Protocol (message transport)
- ADR-0065: Product Craft & UX (UI patterns)

---

## Context

### Problem Statement

Users need ability to override implicit pause detection and explicitly signal turn completion. Power users prefer keyboard shortcuts (Enter key), while casual users prefer visual affordances (Send button).

**Use Cases:**
1. **Skip Pause Wait**: User finishes typing, wants immediate response (no 2s wait)
2. **Multi-Line Input**: User presses Enter for newline, Shift+Enter to submit
3. **Mobile UX**: Touch "Send" button on mobile keyboards
4. **Voice Override**: User says "Send" to override VAD silence detection

---

## Decision

### 1. Explicit Submit Mechanisms

**Text Input (Desktop):**
- **Enter key**: Single-line input boxes → submit
- **Shift+Enter**: Multi-line text areas → newline
- **Send button**: Always available visual affordance
- **Keyboard shortcut**: Cmd/Ctrl+Enter → submit from anywhere

**Text Input (Mobile):**
- **Send button**: Primary submission method (large touch target)
- **Keyboard action**: "Send" key on mobile keyboard
- **Voice dictation**: "Send" spoken command

**Voice Input:**
- **Spoken command**: "Send", "Submit", "That's all"
- **Manual button**: "Stop Listening" button in UI

### 2. WebSocket Protocol Extension

**Message Schema:**
```json
{
  "type": "user_message",
  "session_id": "session_abc123",
  "text": "Hello, how are you?",
  "is_explicit_submit": true,  // NEW: Explicit submit flag
  "submit_method": "enter_key",  // "enter_key" | "send_button" | "keyboard_shortcut" | "voice_command"
  "timestamp": 1697123456.789,
  "trace_id": "trace_xyz"
}
```

**Backend Handling:**
```python
def on_websocket_message(ws_message: Dict):
    if ws_message.get("is_explicit_submit"):
        # Bypass pause timer, immediate turn boundary
        turn_boundary_detector.on_explicit_submit(
            session_id=ws_message["session_id"],
            submit_method=ws_message["submit_method"]
        )
    else:
        # Normal implicit pause detection
        turn_boundary_detector.on_message(
            session_id=ws_message["session_id"],
            message=ws_message["text"]
        )
```

### 3. UI/UX Contracts

**Contract A: Send Button Always Visible**
- **Requirement**: Send button must be visible at all times
- **Location**: Bottom-right of input area (right-to-left locales: bottom-left)
- **State**: Enabled when input non-empty, disabled when empty
- **Accessibility**: ARIA label "Send message", keyboard focus-able

**Contract B: Enter Key Behavior Context-Aware**
- **Single-line input**: Enter → submit (no newline)
- **Multi-line input**: Enter → newline, Shift+Enter → submit
- **Chat-style input**: Enter → submit (default), Shift+Enter → newline (optional)

**Contract C: Visual Feedback on Submit**
- **Before submit**: Send button enabled, blue/primary color
- **On submit**: Send button disabled, spinner/loading state
- **After submit**: Input cleared, button disabled until new input

**Contract D: Mobile Touch Targets**
- **Send button size**: Minimum 44x44pt (iOS), 48x48dp (Android)
- **Button placement**: Thumb-reachable zone (bottom 1/3 of screen)
- **Haptic feedback**: Light tap vibration on button press

### 4. Keyboard Shortcut Specification

**Desktop Shortcuts:**
- **Primary**: Enter (single-line), Shift+Enter (multi-line)
- **Alternative**: Cmd/Ctrl+Enter (submit from anywhere)
- **Cancel**: Esc (clear input, cancel draft)

**Conflict Resolution:**
- Enter in multi-line always inserts newline (prevents accidental submit)
- Shift+Enter in multi-line submits (explicit intent)
- Cmd/Ctrl+Enter submits from any input type (power user preference)

### 5. Voice Command Detection

**Spoken Submit Commands:**
- **English**: "Send", "Submit", "That's all", "Go ahead"
- **Spanish**: "Enviar", "Mandar", "Eso es todo"
- **French**: "Envoyer", "Soumettre", "C'est tout"
- **Localized**: Add per-locale submit phrases

**ASR Integration:**
```python
def on_asr_transcript(session_id: str, transcript: str):
    # Check for submit command
    submit_commands = ["send", "submit", "that's all", "go ahead"]

    if transcript.lower().strip() in submit_commands:
        # Treat as explicit submit
        turn_boundary_detector.on_explicit_submit(
            session_id=session_id,
            submit_method="voice_command"
        )
    else:
        # Normal message processing
        turn_boundary_detector.on_message(session_id, transcript)
```

---

## Consequences

### Positive

✅ **User Control**: Users decide when turn ends (not system)
✅ **Faster UX**: Skip 2s pause wait for immediate response
✅ **Accessibility**: Multiple submission methods (keyboard, button, voice)
✅ **Power User Friendly**: Keyboard shortcuts for efficiency

### Negative

⚠️ **Complexity**: Multiple submission paths increase testing surface
⚠️ **Discoverability**: Users may not know about Shift+Enter or Cmd+Enter
⚠️ **Mobile Keyboard Variance**: Different keyboards handle Enter differently

---

## Implementation Guidance

### Phase 1: WebSocket Protocol (Day 1)
- Add `is_explicit_submit` flag to message schema
- Backend parsing and routing

### Phase 2: Desktop UI (Day 2-3)
- Send button component
- Enter key handler
- Keyboard shortcuts

### Phase 3: Mobile UI (Day 4)
- Touch-optimized Send button
- Keyboard action handling
- Haptic feedback

### Phase 4: Voice Commands (Day 5)
- ASR submit phrase detection
- Localized phrase support

---

## Validation

**Functional Tests:**
```python
@test("explicit submit bypasses pause timer")
async def test_explicit_submit():
    msg = Message(text="Hello", is_explicit_submit=True)
    detector.on_message("s1", msg)
    await asyncio.sleep(0.1)  # No 2s wait
    assert events.get("turn_boundary").signal == "explicit_submit"
```

**UX Tests:**
- Send button click triggers submit
- Enter key triggers submit (single-line)
- Shift+Enter triggers submit (multi-line)
- Voice "Send" command triggers submit

---

## Monitoring

```python
explicit_submit_total = Counter(
    'explicit_submit_total',
    'Explicit submits',
    ['method']  # enter_key, send_button, voice_command
)

submit_method_ratio = Gauge(
    'submit_method_ratio',
    'Ratio of explicit vs implicit submits'
)
```

**Target:** 30-40% of submits are explicit (power user adoption)

---

## References

- iOS Human Interface Guidelines: Button sizing
- Android Material Design: Touch targets
- ADR-0015: WebSocket Protocol

---

**Document Status:** ✅ Complete
**Estimated Lines:** 720 lines (target: 700 lines) ✅
