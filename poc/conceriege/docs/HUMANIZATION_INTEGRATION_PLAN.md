# 🚀 Humanization Integration Plan

**Target:** Integrate all 10 humanization topics into POC Concierge system
**Final Output:** Refined `web_ui.py` hosting truly human-like user-LLM conversation
**Date:** November 8, 2025

---

## 📋 Executive Summary

**Goal:** Transform the current functional Concierge V2 system into a human-like conversational experience by integrating 10 humanization topics systematically.

**Current State:**

- ✅ Basic WebSocket-based web UI (`web_ui.py`)
- ✅ Background proactive analysis working
- ✅ Real-time message push functional
- ⚠️ Feels robotic - instant responses, no personality, formal tone

**Target State:**

- ✅ Human-like rhythm with typing indicators and delays
- ✅ Emotion-aware responses with empathy
- ✅ Context-aware conversation with memory
- ✅ Natural proactive injection without interruption
- ✅ Personality-driven varied responses

---

## 🏗️ Architecture Overview

### **Current System Structure**

```
web_ui.py (Frontend + Backend)
├── FastAPI app with WebSocket endpoint
├── HTML/CSS/JS embedded chat UI
├── Background monitor (500ms polling)
└── ConciergeAgentV2 integration

backend/agents/concierge_v2.py (Orchestrator)
├── process_message() - Main flow
├── _generate_conversational_response() - LLM-based replies
├── _respond_with_findings() - Proactive injection
├── _check_completed_tasks() - Background task monitor
└── Background specialist tasks (Nutritionist, Psychiatrist)

backend/services/
├── llm_client.py - Groq API wrapper
├── k0_query_service.py - Data retrieval (mock)
├── progress_publisher.py - Event streaming
└── metrics_collector.py - Performance tracking
```

### **New System Structure (After Integration)**

```
web_ui.py (Enhanced)
├── send_with_rhythm() - Typing delays + indicators (NEW)
├── send_chunked_response() - Message splitting (NEW)
├── Enhanced WebSocket handler
└── Updated HTML/JS with typing indicator UI

backend/agents/concierge_v2.py (Enhanced)
├── EmotionEngine integration (NEW)
├── FocusTracker integration (NEW)
├── MemoryTracker integration (NEW)
├── ContextManager integration (NEW)
├── StyleMirror integration (NEW)
├── Enhanced prompts with personality modes
└── Hybrid LLM + rule-based decision flow

backend/agents/ (New Modules)
├── emotion_engine.py - Emotion detection + tone selection
├── focus_tracker.py - Context switching prevention
├── memory_tracker.py - Conversation history + user details
├── context_manager.py - Topic tracking + time references
└── style_mirror.py - User style analysis + mirroring
```

---

## 📊 Integration Strategy: 3 Phases

### **Phase 1: Critical Foundations (Week 1) - 4 Topics**

**Priority:** 🔴 CRITICAL
**Goal:** Eliminate robotic feel, add basic human-like behavior

| Topic | Type | Module | Integration Target | LLM/Rule-Based |
|-------|------|--------|-------------------|----------------|
| 1. Rhythm | Frontend | `web_ui.py` | WebSocket message sending | Rule-Based (math) |
| 2. Emotion | Backend | `emotion_engine.py` | `concierge_v2.py` process flow | LLM (analysis) |
| 4. Self-Expression | Prompts | `concierge_v2.py` | Response generation | LLM (generation) |
| 5. Proactivity Timing | Backend | `focus_tracker.py` | `process_message()` flow | Rule-Based (detection) |

**Deliverable:** Web UI with typing delays, emotion-aware responses, personality, no context switching

---

### **Phase 2: Flow Enhancement (Week 2) - 3 Topics**

**Priority:** 🟡 HIGH
**Goal:** Natural conversation flow with memory and variety

| Topic | Type | Module | Integration Target | LLM/Rule-Based |
|-------|------|--------|-------------------|----------------|
| 3. Memory | Backend | `memory_tracker.py` | `concierge_v2.py` context | Hybrid |
| 6. Variety | Prompts | `concierge_v2.py` | Response generation | LLM (generation) |
| 8. Context Awareness | Backend | `context_manager.py` | Topic tracking | Rule-Based (tracking) |

**Deliverable:** Agent remembers conversation, varies responses, bridges topics smoothly

---

### **Phase 3: Polish & Personalization (Week 3) - 3 Topics**

**Priority:** 🟢 MEDIUM
**Goal:** Fine-tuned human-like polish

| Topic | Type | Module | Integration Target | LLM/Rule-Based |
|-------|------|--------|-------------------|----------------|
| 7. Reasoning | Prompts | `concierge_v2.py` | Response generation | LLM (generation) |
| 9. Style Mirror | Backend | `style_mirror.py` | Style adaptation | Rule-Based (analysis) |
| 10. Closure | Prompts | `concierge_v2.py` | Response generation | Hybrid |

**Deliverable:** Uncertainty markers, user style mirroring, graceful closures

---

## 🔧 Phase 1 Implementation Details

### **Day 1-2: Topic 1 - Conversational Rhythm**

**Target File:** `web_ui.py`

**Changes Required:**

1. **Add rhythm functions before WebSocket handler:**

```python
import random

async def send_with_rhythm(websocket, message_type: str, content: str):
    """Send message with human-like typing delay"""
    word_count = len(content.split())
    base_delay = min(word_count * 0.15, 2.0)  # 150ms per word, max 2s
    variance = random.uniform(0.8, 1.2)
    delay = base_delay * variance

    # Show typing indicator
    await websocket.send_json({
        "type": "typing_indicator",
        "visible": True
    })

    await asyncio.sleep(delay)

    # Hide typing indicator
    await websocket.send_json({
        "type": "typing_indicator",
        "visible": False
    })

    # Send message
    await websocket.send_json({
        "type": message_type,
        "content": content,
        "timestamp": datetime.now().isoformat()
    })

async def send_chunked_response(websocket, full_text: str):
    """Split long response into 2-3 chunks"""
    sentences = full_text.split('. ')

    if len(sentences) <= 2:
        await send_with_rhythm(websocket, "agent_message", full_text)
        return

    chunk_size = len(sentences) // 2 if len(sentences) > 4 else 2
    chunks = ['. '.join(sentences[i:i+chunk_size]) + '.'
              for i in range(0, len(sentences), chunk_size)]

    for i, chunk in enumerate(chunks):
        await send_with_rhythm(websocket, "agent_message", chunk)
        if i < len(chunks) - 1:
            await asyncio.sleep(random.uniform(0.3, 0.8))
```

2. **Replace all `websocket.send_json()` calls with `send_with_rhythm()`:**

```python
# OLD
await websocket.send_json({
    "type": "agent_message",
    "message": response,
    "timestamp": datetime.now().isoformat()
})

# NEW
await send_with_rhythm(websocket, "agent_message", response)
```

3. **Add typing indicator to HTML template:**

```html
<!-- Add inside .messages div -->
<div id="typing-indicator" class="typing-indicator" style="display: none;">
    <div class="message agent">
        <div class="message-bubble">
            <span></span><span></span><span></span>
        </div>
    </div>
</div>

<!-- Add CSS -->
<style>
.typing-indicator span {
    display: inline-block;
    width: 8px;
    height: 8px;
    background: #999;
    border-radius: 50%;
    margin: 0 2px;
    animation: typing 1.4s infinite;
}

.typing-indicator span:nth-child(2) {
    animation-delay: 0.2s;
}

.typing-indicator span:nth-child(3) {
    animation-delay: 0.4s;
}

@keyframes typing {
    0%, 60%, 100% { transform: translateY(0); }
    30% { transform: translateY(-10px); }
}
</style>

<!-- Update JavaScript -->
<script>
ws.onmessage = (event) => {
    const data = JSON.parse(event.data);

    if (data.type === 'typing_indicator') {
        const indicator = document.getElementById('typing-indicator');
        indicator.style.display = data.visible ? 'block' : 'none';
    } else {
        addMessage(data);
    }
};
</script>
```

**Testing:**

- Send message → typing indicator appears → delay 200-1500ms → message arrives
- Long responses split into 2-3 chunks with micro-pauses

---

### **Day 3-4: Topic 2 - Emotion & Empathy Layer**

**Target Files:**

- NEW: `backend/agents/emotion_engine.py`
- MODIFY: `backend/agents/concierge_v2.py`

**Step 1: Create `emotion_engine.py`**

```python
from dataclasses import dataclass
from typing import Literal
from backend.services.llm_client import LLMClient
import json

@dataclass
class EmotionContext:
    sentiment: Literal["happy", "sad", "frustrated", "anxious", "neutral"]
    intensity: float
    tone_mode: Literal["supportive", "playful", "concerned", "analytical"]
    empathy_phrase: str

class EmotionEngine:
    def __init__(self, llm_client: LLMClient):
        self.llm_client = llm_client

    async def analyze_emotion(self, message: str, conversation_history: list) -> EmotionContext:
        """Detect emotion using LLM"""

        prompt = f"""Analyze emotional tone.

User: "{message}"

Recent context: {conversation_history[-3:] if conversation_history else "None"}

Return JSON:
{{
    "sentiment": "happy|sad|frustrated|anxious|neutral",
    "intensity": 0.0-1.0,
    "tone_mode": "supportive|playful|concerned|analytical",
    "empathy_phrase": "2-4 word empathy response"
}}

Examples:
- "ugh still hurts" → {{"sentiment": "frustrated", "intensity": 0.7, "tone_mode": "concerned", "empathy_phrase": "ugh that sucks"}}
- "yay better!" → {{"sentiment": "happy", "intensity": 0.8, "tone_mode": "playful", "empathy_phrase": "yay awesome!"}}

JSON:"""

        response = await self.llm_client.generate_async(
            prompt,
            model_profile="creative",
            max_tokens=100
        )

        emotion_data = json.loads(response.strip())

        return EmotionContext(
            sentiment=emotion_data["sentiment"],
            intensity=emotion_data["intensity"],
            tone_mode=emotion_data["tone_mode"],
            empathy_phrase=emotion_data["empathy_phrase"]
        )

    def get_tone_instructions(self, emotion: EmotionContext) -> str:
        """Generate LLM prompt instructions based on emotion"""

        tone_guides = {
            "supportive": "Use warm, encouraging language. Show you care.",
            "playful": "Be light and friendly. Use casual language.",
            "concerned": "Show genuine care. Be direct but kind.",
            "analytical": "Be clear and informative. Stay calm."
        }

        return f"""User emotion: {emotion.sentiment} (intensity: {emotion.intensity})

Tone: {emotion.tone_mode}
{tone_guides[emotion.tone_mode]}

Start with empathy: "{emotion.empathy_phrase}" (or similar)
Then respond."""
```

**Step 2: Integrate into `concierge_v2.py`**

```python
# Add import
from backend.agents.emotion_engine import EmotionEngine, EmotionContext

class ConciergeAgentV2:
    def __init__(self, ...):
        # ... existing init
        self.emotion_engine = EmotionEngine(self.llm_client)
        self.current_emotion: Optional[EmotionContext] = None

    async def process_message(self, user_id: str, message: str) -> str:
        # NEW: Analyze emotion FIRST
        self.current_emotion = await self.emotion_engine.analyze_emotion(
            message,
            self.conversation_history
        )

        # ... rest of existing logic

    async def _generate_conversational_response(self, message: str) -> str:
        # Include emotion context in prompt
        emotion_instructions = ""
        if self.current_emotion:
            emotion_instructions = self.emotion_engine.get_tone_instructions(
                self.current_emotion
            )

        prompt = f"""{emotion_instructions}

Recent conversation:
{self._build_history_text()}

User: {message}

Response (1-2 sentences, use empathy):"""

        response = await self.llm_client.generate_async(
            prompt,
            model_profile="creative",
            max_tokens=150
        )

        return response.strip()
```

**Testing:**

- Frustrated message → "ugh that sucks" + concerned tone
- Happy message → "yay!" + playful tone

---

### **Day 5: Topic 4 - Self-Expression**

**Target File:** `backend/agents/concierge_v2.py`

**Add personality constants:**

```python
PERSONALITY_MODES = {
    "caring": {
        "description": "Warm, supportive",
        "phrases": ["hope you're okay", "take care"],
        "tone": "Use gentle language, show care"
    },
    "analytical": {
        "description": "Clear, factual",
        "phrases": ["let me check", "based on data"],
        "tone": "Be direct but kind, focus on facts"
    },
    "playful": {
        "description": "Light, friendly",
        "phrases": ["btw", "you know", "honestly"],
        "tone": "Be casual, use light humor"
    },
    "concerned": {
        "description": "Serious but empathetic",
        "phrases": ["that's tough", "ugh that sucks"],
        "tone": "Acknowledge difficulty, be direct"
    },
    "uncertain": {
        "description": "Not fully confident",
        "phrases": ["not sure but", "might be", "possibly"],
        "tone": "Show thinking process, admit uncertainty"
    }
}
```

**Add personality method:**

```python
def _get_personality_instructions(self, mode: str = "caring") -> str:
    personality = PERSONALITY_MODES.get(mode, PERSONALITY_MODES["caring"])

    return f"""Personality: {personality['description']}

{personality['tone']}

Common phrases: {', '.join(personality['phrases'])}

RULES:
- Use contractions: "you're", "it's", "gonna", "btw"
- Keep SHORT (1-2 sentences)
- NO formal: "I understand", "Let me help"
- Vary sentence length, use ellipses sometimes
- Metacomments: "not sure if this helps but..."
"""

async def _generate_conversational_response(self, message: str) -> str:
    # Select mode based on emotion
    mode = "caring"
    if self.current_emotion:
        emotion_to_mode = {
            "frustrated": "concerned",
            "anxious": "caring",
            "happy": "playful",
            "sad": "caring",
            "neutral": "analytical"
        }
        mode = emotion_to_mode.get(self.current_emotion.sentiment, "caring")

    personality_instructions = self._get_personality_instructions(mode)
    emotion_instructions = self.emotion_engine.get_tone_instructions(
        self.current_emotion
    ) if self.current_emotion else ""

    prompt = f"""{personality_instructions}

{emotion_instructions}

Recent conversation:
{self._build_history_text()}

User: {message}

Response:"""

    # ... rest of method
```

**Testing:**

- Responses use contractions ("you're" not "you are")
- No formal phrases ("I understand")
- Personality matches emotion (concerned for frustrated, playful for happy)

---

### **Day 6-7: Topic 5 - Proactivity Timing (Focus Tracker)**

**Target Files:**

- NEW: `backend/agents/focus_tracker.py`
- MODIFY: `backend/agents/concierge_v2.py`

**Step 1: Create `focus_tracker.py`**

```python
from dataclasses import dataclass
from typing import Literal, Optional
from datetime import datetime

@dataclass
class FocusState:
    current_focus: Literal["reactive", "proactive", "insight_thread"]
    locked_insight_id: Optional[str] = None
    insight_turn_count: int = 0
    last_insight_message: Optional[str] = None
    last_update: datetime = None

class ConversationFocusTracker:
    """Prevents context switching - RULE-BASED (fast)"""

    def __init__(self):
        self.state = FocusState(
            current_focus="reactive",
            last_update=datetime.now()
        )

        # RULE-BASED: Known curiosity patterns
        self.curiosity_markers = [
            "oh really", "really?", "seriously?", "no way",
            "are you sure", "how do you know", "interesting",
            "wow", "what", "huh", "wait", "hold on"
        ]

        # RULE-BASED: Known resolution patterns
        self.resolution_markers = [
            "got it", "thanks", "okay", "ok", "cool",
            "makes sense", "yeah", "right", "sure"
        ]

    def determine_focus(
        self,
        user_message: str,
        has_pending_proactive: bool
    ) -> Literal["continue_insight_thread", "inject_proactive", "reactive"]:
        """RULE-BASED focus determination (ultra-fast)"""

        message_lower = user_message.lower()
        word_count = len(user_message.split())

        # Check if in insight thread
        if self.state.current_focus == "insight_thread":
            # Check resolution
            if any(marker in message_lower for marker in self.resolution_markers):
                self._release_lock()
                return "reactive"

            # Check curiosity continuation
            if any(marker in message_lower for marker in self.curiosity_markers):
                return "continue_insight_thread"

            # Continue for max 3 turns
            if self.state.insight_turn_count < 3:
                self.state.insight_turn_count += 1
                return "continue_insight_thread"
            else:
                self._release_lock()

        # Check if user just got curious
        if (self.state.last_insight_message and
            any(marker in message_lower for marker in self.curiosity_markers)):
            self.state.current_focus = "insight_thread"
            self.state.insight_turn_count = 0
            return "continue_insight_thread"

        # Check proactive injection
        if has_pending_proactive:
            # Don't interrupt long messages
            if word_count > 10:
                return "reactive"

            # Don't interrupt questions
            if "?" in user_message:
                return "reactive"

            return "inject_proactive"

        return "reactive"

    def track_insight_injection(self, insight_message: str):
        """Track proactive insight for context"""
        self.state.last_insight_message = insight_message
        self.state.current_focus = "proactive"
        self.state.last_update = datetime.now()

    def _release_lock(self):
        """Release focus lock"""
        self.state.current_focus = "reactive"
        self.state.locked_insight_id = None
        self.state.insight_turn_count = 0
        self.state.last_update = datetime.now()
```

**Step 2: Integrate into `concierge_v2.py`**

```python
from backend.agents.focus_tracker import ConversationFocusTracker

class ConciergeAgentV2:
    def __init__(self, ...):
        # ... existing init
        self.focus_tracker = ConversationFocusTracker()

    async def process_message(self, user_id: str, message: str) -> str:
        # Analyze emotion
        self.current_emotion = await self.emotion_engine.analyze_emotion(
            message,
            self.conversation_history
        )

        # Check completed tasks
        await self._check_completed_tasks()

        # RULE-BASED: Determine focus (ultra-fast)
        focus = self.focus_tracker.determine_focus(
            message,
            has_pending_proactive=bool(self.completed_analyses)
        )

        if focus == "continue_insight_thread":
            # User curious about last insight
            response = await self._continue_insight_discussion(message)

        elif focus == "inject_proactive" and self.completed_analyses:
            # Safe to inject proactive findings
            response = await self._respond_with_findings(message)
            self.focus_tracker.track_insight_injection(response)

        else:
            # Normal reactive conversation
            response = await self._generate_conversational_response(message)

        # Store history
        self.conversation_history.append({"role": "user", "content": message})
        self.conversation_history.append({"role": "assistant", "content": response})

        return response

    async def _continue_insight_discussion(self, message: str) -> str:
        """LLM-based insight continuation"""

        prompt = f"""User is curious about your recent finding.

Your insight: "{self.focus_tracker.state.last_insight_message}"

User reaction: "{message}"

Continue naturally:
- Acknowledge curiosity: "Yeah, I was surprised too..."
- Provide more detail
- Offer to investigate further

Keep conversational (1-2 sentences, use contractions).

Response:"""

        response = await self.llm_client.generate_async(
            prompt,
            model_profile="creative",
            max_tokens=150
        )

        return response.strip()
```

**Testing:**

- System injects finding → User says "oh really?" → System continues that thread (no topic switch)
- User says "got it" → Focus released, normal conversation resumes

---

## 🎯 Phase 1 Success Criteria

After Day 7, test the following:

1. **Rhythm Test:**
   - Send message → Typing indicator appears → Delay 200-1500ms → Message arrives
   - Long responses split into 2-3 chunks with pauses

2. **Emotion Test:**
   - "ugh hurts" → System uses concerned tone with empathy ("ugh that sucks")
   - "yay better!" → System uses playful tone ("yay awesome!")

3. **Personality Test:**
   - Responses use contractions ("you're", "gonna", "btw")
   - No formal phrases ("I understand", "Let me help")
   - Consistent personality per emotion

4. **Focus Test:**
   - System injects finding → User: "oh really?" → System continues insight (no switch)
   - User: "got it thanks" → System resumes normal conversation

**Acceptance:** All 4 tests pass, conversation feels noticeably more human-like

---

## 📊 Phase 2 & 3 Summary

### **Phase 2: Memory, Variety, Context (Week 2)**

**Day 1-2: Memory Tracker**

- Create `memory_tracker.py` with ConversationThread, UserDetail tracking
- Integrate into `concierge_v2.py` for topic extraction and memory context
- RULE-BASED: Keyword matching for topics
- LLM: Natural memory references in prompts

**Day 3-4: Conversational Variety**

- Add `_get_variety_instructions()` to `concierge_v2.py`
- Alternate response lengths (short vs medium)
- Random structural variety (questions, acknowledgments, observations)
- LLM generates varied responses based on instructions

**Day 5-7: Context Manager**

- Create `context_manager.py` for topic tracking and time references
- RULE-BASED: Time delta calculations, topic state tracking
- LLM: Topic bridging in responses

### **Phase 3: Reasoning, Style, Closure (Week 3)**

**Day 1-2: Human Reasoning**

- Add REASONING_MARKERS constants to `concierge_v2.py`
- Implement `_get_reasoning_instructions()` based on confidence
- LLM generates responses with uncertainty markers

**Day 3-5: Style Mirror**

- Create `style_mirror.py` for user style analysis
- RULE-BASED: Regex emoji detection, punctuation counting, formality heuristics
- LLM: Mirror style in responses via prompt instructions

**Day 6-7: Closure**

- Add CLOSURE_PATTERNS to `concierge_v2.py`
- RULE-BASED: Resolution marker detection, correction detection
- LLM: Graceful closure responses

---

## 🔧 Final Web UI Integration

After all 3 phases, `web_ui.py` will have:

### **New Functions:**

1. `send_with_rhythm()` - Typing delays + indicators
2. `send_chunked_response()` - Message splitting
3. Enhanced `background_monitor()` - Focus-aware injection

### **Enhanced WebSocket Handler:**

```python
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()

    async def background_monitor():
        while True:
            await asyncio.sleep(0.5)
            await concierge._check_completed_tasks()

            if concierge.completed_analyses:
                # Check if safe to inject (focus tracker)
                if concierge.focus_tracker.state.current_focus != "insight_thread":
                    analysis = concierge.completed_analyses[0]

                    # Send with rhythm (no instant push)
                    injection = await concierge._respond_with_findings("(continuing)")
                    await send_chunked_response(websocket, injection)

    monitor_task = asyncio.create_task(background_monitor())

    try:
        while True:
            data = await websocket.receive_json()
            user_message = data.get("message", "")

            # Echo user message (no delay)
            await websocket.send_json({
                "type": "user_message",
                "message": user_message,
                "timestamp": datetime.now().isoformat()
            })

            # Process with all humanization
            response = await concierge.process_message(user_id, user_message)

            # Send with rhythm and chunking
            await send_chunked_response(websocket, response)

    except WebSocketDisconnect:
        monitor_task.cancel()
```

### **Enhanced HTML Template:**

- Typing indicator with 3 animated dots
- Enhanced CSS for message bubbles
- Smooth animations for message arrival
- Status indicators for background tasks

---

## 📈 Testing & Validation

### **Integration Test Scenarios:**

1. **Full Conversation Flow:**

   ```
   User: "hello"
   → Typing indicator (500ms)
   → Agent: "Hey! How's it going?" (playful tone, short)

   User: "milk makes me sick"
   → Typing indicator (800ms)
   → Agent: "Oh that's rough. How often?" (concerned tone, empathy)
   → [Background: Nutritionist analyzing]

   User: "every morning"
   → Typing indicator (700ms)
   → Agent: "Hmm that's a pattern" (analytical)

   [2 seconds pass]
   → Typing indicator (1200ms)
   → Agent: "Btw I checked your logs..." (chunk 1)
   → Pause (500ms)
   → Typing indicator (900ms)
   → Agent: "Milk's triggering GERD 90 mins after" (chunk 2)

   User: "oh really?"
   → Typing indicator (600ms)
   → Agent: "Yeah surprised me too. Pattern's consistent" (continues insight thread)

   User: "got it thanks"
   → Typing indicator (400ms)
   → Agent: "Hope you feel better!" (warm closure)
   ```

2. **Performance Test:**
   - Total latency per message: <500ms (rhythm delays intentional)
   - Rule-based operations: <5ms
   - LLM operations: 50-200ms
   - WebSocket overhead: <10ms

3. **Human-Like Perception Test:**
   - Survey 10 users: "Did this feel like talking to a human?" (target: >7/10)
   - Count template phrases (target: 0)
   - Count context switches during insight discussion (target: 0)

---

## 📝 Deliverables Checklist

### **Phase 1 (Week 1):**

- [ ] `web_ui.py` - Rhythm functions + typing indicator
- [ ] `backend/agents/emotion_engine.py` - NEW module
- [ ] `backend/agents/focus_tracker.py` - NEW module
- [ ] `backend/agents/concierge_v2.py` - Personality modes + emotion integration
- [ ] Integration tests pass (4 scenarios)

### **Phase 2 (Week 2):**

- [ ] `backend/agents/memory_tracker.py` - NEW module
- [ ] `backend/agents/context_manager.py` - NEW module
- [ ] `backend/agents/concierge_v2.py` - Variety + memory + context integration
- [ ] Integration tests pass (3 scenarios)

### **Phase 3 (Week 3):**

- [ ] `backend/agents/style_mirror.py` - NEW module
- [ ] `backend/agents/concierge_v2.py` - Reasoning + closure + style integration
- [ ] Integration tests pass (3 scenarios)

### **Final Deliverable:**

- [ ] `web_ui.py` - Fully refined with all humanization
- [ ] `backend/agents/concierge_v2.py` - Complete humanization integration
- [ ] 5 new modules created and integrated
- [ ] Human-like perception score >7/10
- [ ] Performance <500ms per message (including intentional delays)
- [ ] Zero template phrases detected
- [ ] Zero context switching during insight threads

---

## 🚀 Quick Start Guide

### **To Begin Phase 1 (Today):**

1. **Backup current system:**

   ```bash
   cd d:/familyos/poc/conceriege
   git checkout -b humanization-integration
   git add .
   git commit -m "Backup before humanization integration"
   ```

2. **Start with Rhythm (easiest win):**
   - Open `web_ui.py`
   - Add `send_with_rhythm()` function
   - Update WebSocket handler to use it
   - Add typing indicator to HTML
   - Test immediately

3. **Move to Emotion:**
   - Create `backend/agents/emotion_engine.py`
   - Copy code from implementation guide
   - Integrate into `concierge_v2.py`
   - Test with frustrated/happy messages

4. **Add Personality:**
   - Add PERSONALITY_MODES to `concierge_v2.py`
   - Update `_generate_conversational_response()`
   - Test personality variety

5. **Finish with Focus Tracker:**
   - Create `backend/agents/focus_tracker.py`
   - Integrate into `process_message()` flow
   - Test "oh really?" continuity

**Expected Time:**

- Day 1-2: Rhythm (4 hours)
- Day 3-4: Emotion (6 hours)
- Day 5: Personality (4 hours)
- Day 6-7: Focus Tracker (6 hours)

**Total Phase 1:** 20 hours over 7 days = ~3 hours/day

---

## 🎯 Success Metrics

| Metric | Current | Target | Measurement |
|--------|---------|--------|-------------|
| Human-like feel | 3/10 | >7/10 | Post-chat survey |
| Template phrases | Many | 0 | Code scan |
| Context switches | Common | 0 | Conversation logs |
| Response latency | ~150ms | <500ms | Performance monitor |
| Typing feel | Instant | Natural | User feedback |
| Emotion matching | None | >80% | Accuracy test |
| Personality consistency | None | Yes | Conversation analysis |

---

## 📚 References

- HUMANIZATION_IMPLEMENTATION_GUIDE.md - Full technical specs
- CONVERSATION_UX_ANALYSIS.md - UX requirements and analysis
- Current web_ui.py - Baseline implementation
- Current concierge_v2.py - Core orchestrator

---

**Next Step:** Begin Phase 1, Day 1 - Add conversational rhythm to `web_ui.py`
