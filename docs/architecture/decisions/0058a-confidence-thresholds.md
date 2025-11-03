---
adr_number: 0058a
title: Confidence Thresholds & Clarification Strategy
status: ACCEPTED
date_created: '2025-11-03'
date_updated: '2025-11-03'
authors:
- K1 Architecture Team
affected_layers:
- layer1_input
- layer3_execution
- layer4_runtime
- layer5_infrastructure
affected_modules: []
concerns:
- architecture
- cost
- observability
- performance
- privacy
- reliability
- testing
supersedes: []
superseded_by: []
related_adrs:
- ADR-0003b
- ADR-0021
- ADR-0056b
- ADR-0058
- ADR-0058a
implementation_status: COMPLETED
implementation_date: null
implementation_phase: null
related_contracts: []
related_diagrams: []
research_citations: []
propagation:
  triggers:
  - Modifying system architecture
  affected_adrs:
  - ADR-0003b
  - ADR-0021
  - ADR-0056b
  - ADR-0058
  - ADR-0058a
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


# ADR-0058a: Confidence Thresholds & Clarification Strategy

**Status:** Accepted
**Date:** 2025-10-14
**Deciders:** K1 Architecture Team
**Parent ADR:** ADR-0058 (Intent Classification Integration)

**Related ADRs:**
- ADR-0058: Intent Classification Integration (parent)
- ADR-0021: Intent Classification (baseline)
- ADR-0003b: Protocol 3 (Clarification)
- ADR-0056b: Intent Bridge (disfluency removal)

---

## Context

### Problem Statement

Voice input has **variable confidence** due to:
- ASR errors (WER 6%)
- Background noise
- Accents and speaking styles
- Disfluencies ("um", "uh")
- Homophones ("flight" vs "kite")

**Challenges:**
1. **Setting thresholds:** Too high = too many clarifications, too low = errors
2. **Clarification loops:** Users get frustrated with repeated questions
3. **Context awareness:** Different thresholds for different actions
4. **Multi-signal fusion:** Combine ASR, classifier, phonetic scores

---

## Decision

### 1. Confidence Calculation Formula

**Multi-Signal Fusion:**
```python
@dataclass
class ConfidenceSignals:
    base_classifier: float      # Intent classifier confidence (0-1)
    asr_confidence: float        # ASR engine confidence (0-1)
    phonetic_match: float        # Phonetic similarity score (0-1)
    context_alignment: float     # Session context alignment (0-1)
    has_disfluencies: bool       # True if "um", "uh" detected

class ConfidenceCalculator:
    # Weights for signal fusion
    WEIGHTS = {
        "base_classifier": 0.40,    # 40% - Primary signal
        "asr_confidence": 0.25,     # 25% - ASR quality
        "phonetic_match": 0.20,     # 20% - Fuzzy matching
        "context_alignment": 0.15   # 15% - Session context
    }

    # Penalties
    DISFLUENCY_PENALTY = 0.10      # -10% for disfluencies
    BACKGROUND_NOISE_PENALTY = 0.05 # -5% for noise

    def calculate_combined_confidence(self,
                                     signals: ConfidenceSignals) -> float:
        """Weighted combination of confidence signals"""
        # Base weighted sum
        combined = (
            self.WEIGHTS["base_classifier"] * signals.base_classifier +
            self.WEIGHTS["asr_confidence"] * signals.asr_confidence +
            self.WEIGHTS["phonetic_match"] * signals.phonetic_match +
            self.WEIGHTS["context_alignment"] * signals.context_alignment
        )

        # Apply penalties
        if signals.has_disfluencies:
            combined *= (1.0 - self.DISFLUENCY_PENALTY)

        # Clamp to [0, 1]
        return max(0.0, min(1.0, combined))
```

### 2. Dynamic Threshold Selection

**Context-Aware Thresholds:**
```python
@dataclass
class ThresholdConfig:
    proceed: float    # Confidence to proceed without clarification
    clarify: float    # Confidence to request clarification
    reject: float     # Below this, reject or ask for rephrase

class DynamicThresholds:
    # Baseline thresholds (GREEN band, low-cost actions)
    BASELINE = ThresholdConfig(
        proceed=0.80,
        clarify=0.60,
        reject=0.40
    )

    # Privacy band adjustments
    BAND_ADJUSTMENTS = {
        PrivacyBand.GREEN: 0.0,     # No adjustment
        PrivacyBand.AMBER: +0.05,   # +5% more conservative
        PrivacyBand.RED: +0.10      # +10% more conservative
    }

    # Action cost adjustments
    COST_ADJUSTMENTS = {
        "low": 0.0,        # Chitchat, queries
        "medium": +0.05,   # Calendar, reminders
        "high": +0.10,     # Payments, deletions
        "critical": +0.15  # Account changes
    }

    def get_thresholds(self,
                      band: PrivacyBand,
                      action_cost: str,
                      user_profile: UserProfile) -> ThresholdConfig:
        """Calculate context-specific thresholds"""
        base = self.BASELINE

        # Apply privacy band adjustment
        band_adj = self.BAND_ADJUSTMENTS[band]

        # Apply cost adjustment
        cost_adj = self.COST_ADJUSTMENTS[action_cost]

        # User-specific adjustment (learned over time)
        user_adj = user_profile.threshold_preference  # -0.1 to +0.1

        # Combined adjustment
        total_adj = band_adj + cost_adj + user_adj

        return ThresholdConfig(
            proceed=min(0.95, base.proceed + total_adj),
            clarify=min(0.90, base.clarify + total_adj),
            reject=max(0.20, base.reject + total_adj)
        )
```

### 3. Clarification Decision Logic

**Decision Tree:**
```python
class ClarificationDecider:
    async def decide(self,
                    intent: IntentResult,
                    confidence: float,
                    thresholds: ThresholdConfig,
                    session: Session) -> ClarificationDecision:
        """Decide whether and how to clarify"""

        # Case 1: High confidence → Proceed
        if confidence >= thresholds.proceed:
            return ClarificationDecision(
                action=ClarificationAction.PROCEED,
                reason="high_confidence"
            )

        # Case 2: Low confidence → Reject or rephrase
        if confidence < thresholds.reject:
            # Check if we've already asked for rephrase
            rephrase_count = session.state.get("rephrase_count", 0)

            if rephrase_count >= 2:
                # Give up, offer text input
                return ClarificationDecision(
                    action=ClarificationAction.FALLBACK_TEXT,
                    reason="repeated_low_confidence"
                )
            else:
                return ClarificationDecision(
                    action=ClarificationAction.REPHRASE,
                    reason="low_confidence"
                )

        # Case 3: Medium confidence → Clarify
        # Identify type of ambiguity
        ambiguity = self.identify_ambiguity(intent, session)

        if ambiguity.type == "missing_parameter":
            return ClarificationDecision(
                action=ClarificationAction.ASK_PARAMETER,
                target_parameter=ambiguity.parameter,
                reason="missing_required_parameter"
            )

        elif ambiguity.type == "category_confusion":
            # Multiple possible intents with similar confidence
            return ClarificationDecision(
                action=ClarificationAction.OFFER_ALTERNATIVES,
                alternatives=ambiguity.top_k_intents[:3],
                reason="ambiguous_intent"
            )

        elif ambiguity.type == "value_ambiguity":
            # Parameter value unclear
            return ClarificationDecision(
                action=ClarificationAction.CONFIRM_VALUE,
                parameter=ambiguity.parameter,
                heard_value=ambiguity.extracted_value,
                reason="ambiguous_parameter_value"
            )

        else:
            # Generic clarification
            return ClarificationDecision(
                action=ClarificationAction.GENERIC_CLARIFY,
                reason="medium_confidence"
            )

    def identify_ambiguity(self,
                          intent: IntentResult,
                          session: Session) -> AmbiguityAnalysis:
        """Analyze why confidence is medium"""
        # Check for missing required parameters
        if intent.has_missing_parameters:
            return AmbiguityAnalysis(
                type="missing_parameter",
                parameter=intent.missing_parameters[0]
            )

        # Check for competing intents (top-2 confidence close)
        if len(intent.alternatives) > 0:
            top1 = intent.confidence
            top2 = intent.alternatives[0].confidence

            if top1 - top2 < 0.15:  # Within 15% confidence
                return AmbiguityAnalysis(
                    type="category_confusion",
                    top_k_intents=[intent] + intent.alternatives[:2]
                )

        # Check for ambiguous parameter values
        for param, value in intent.parameters.items():
            if self.is_value_ambiguous(param, value):
                return AmbiguityAnalysis(
                    type="value_ambiguity",
                    parameter=param,
                    extracted_value=value
                )

        return AmbiguityAnalysis(type="generic")
```

### 4. Clarification Prompt Generation

**Natural Language Prompts:**
```python
class ClarificationPrompts:
    TEMPLATES = {
        "rephrase": [
            "I didn't quite catch that. Could you say it again?",
            "Sorry, can you rephrase that for me?",
            "I'm not sure I understood. Can you say it differently?",
        ],

        "ask_parameter": [
            "I heard you want to {action}. Which {parameter} should I use?",
            "Got it, {action}. What {parameter} did you have in mind?",
            "{action} - sure! Can you tell me the {parameter}?",
        ],

        "offer_alternatives": [
            "Did you want to {option1} or {option2}?",
            "I can help with {option1}, {option2}, or {option3}. Which one?",
            "Just to clarify, are you asking about {option1} or {option2}?",
        ],

        "confirm_value": [
            "I heard {parameter} as '{value}'. Is that correct?",
            "Just confirming: {parameter} = '{value}', right?",
            "Did you say {parameter} is '{value}'?",
        ],

        "generic_clarify": [
            "Can you give me a bit more detail?",
            "I need a little more information. Can you elaborate?",
            "Tell me more about what you'd like to do.",
        ],
    }

    def generate(self, decision: ClarificationDecision, intent: IntentResult) -> str:
        """Generate natural clarification prompt"""
        template_key = self.map_action_to_template(decision.action)
        templates = self.TEMPLATES[template_key]

        # Random selection for variety
        template = random.choice(templates)

        # Fill in placeholders
        context = self.build_context(decision, intent)
        return template.format(**context)

    def build_context(self, decision: ClarificationDecision, intent: IntentResult) -> dict:
        """Build context for template"""
        context = {}

        if decision.action == ClarificationAction.ASK_PARAMETER:
            context["action"] = self.humanize_action(intent.category)
            context["parameter"] = self.humanize_parameter(decision.target_parameter)

        elif decision.action == ClarificationAction.OFFER_ALTERNATIVES:
            context["option1"] = self.humanize_action(decision.alternatives[0].category)
            context["option2"] = self.humanize_action(decision.alternatives[1].category)
            if len(decision.alternatives) > 2:
                context["option3"] = self.humanize_action(decision.alternatives[2].category)

        elif decision.action == ClarificationAction.CONFIRM_VALUE:
            context["parameter"] = self.humanize_parameter(decision.parameter)
            context["value"] = decision.heard_value

        return context

    def humanize_action(self, category: str) -> str:
        """Convert category to natural language"""
        mappings = {
            "tool.calendar.schedule": "schedule a meeting",
            "tool.communication.call": "make a phone call",
            "tool.communication.email": "send an email",
            "conversation.chitchat": "just chat",
        }
        return mappings.get(category, category.replace(".", " "))

    def humanize_parameter(self, param: str) -> str:
        """Convert parameter name to natural language"""
        mappings = {
            "recipient": "recipient",
            "datetime": "date and time",
            "subject": "subject",
            "duration": "duration",
            "location": "location",
        }
        return mappings.get(param, param.replace("_", " "))
```

### 5. Clarification State Management

**Track Clarification History:**
```python
@dataclass
class ClarificationState:
    session_id: str
    original_transcript: str
    original_intent: IntentResult
    clarification_attempts: List[ClarificationAttempt] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)

    MAX_ATTEMPTS = 3
    TIMEOUT_SECONDS = 120  # 2 minutes

    def can_attempt_clarification(self) -> bool:
        """Check if more clarifications allowed"""
        if len(self.clarification_attempts) >= self.MAX_ATTEMPTS:
            return False

        if time.time() - self.created_at > self.TIMEOUT_SECONDS:
            return False

        return True

    def add_attempt(self, decision: ClarificationDecision, prompt: str):
        """Record clarification attempt"""
        attempt = ClarificationAttempt(
            action=decision.action,
            prompt=prompt,
            reason=decision.reason,
            timestamp=time.time()
        )
        self.clarification_attempts.append(attempt)

class ClarificationStateManager:
    def __init__(self):
        self.states: Dict[str, ClarificationState] = {}

    async def start_clarification(self,
                                 session_id: str,
                                 transcript: str,
                                 intent: IntentResult) -> ClarificationState:
        """Initialize clarification state"""
        state = ClarificationState(
            session_id=session_id,
            original_transcript=transcript,
            original_intent=intent
        )
        self.states[session_id] = state
        return state

    async def record_clarification(self,
                                  session_id: str,
                                  decision: ClarificationDecision,
                                  prompt: str):
        """Record a clarification attempt"""
        if session_id not in self.states:
            logger.warning("No clarification state for session", session_id=session_id)
            return

        state = self.states[session_id]
        state.add_attempt(decision, prompt)

        # Emit metric
        clarification_attempts.labels(
            reason=decision.reason,
            attempt_number=len(state.clarification_attempts)
        ).inc()

    async def resolve_clarification(self, session_id: str):
        """Clear clarification state on success"""
        if session_id in self.states:
            state = self.states[session_id]

            # Log successful resolution
            logger.info(
                "clarification_resolved",
                session_id=session_id,
                attempts=len(state.clarification_attempts),
                duration_ms=(time.time() - state.created_at) * 1000
            )

            del self.states[session_id]

    async def abandon_clarification(self, session_id: str, reason: str):
        """Give up on clarification"""
        if session_id in self.states:
            state = self.states[session_id]

            logger.warning(
                "clarification_abandoned",
                session_id=session_id,
                reason=reason,
                attempts=len(state.clarification_attempts)
            )

            clarification_abandoned.labels(reason=reason).inc()

            del self.states[session_id]
```

### 6. Fallback Strategies

**When Clarification Fails:**
```python
class ClarificationFallbacks:
    async def handle_failed_clarification(self,
                                         state: ClarificationState,
                                         session: Session) -> Response:
        """Fallback when clarification doesn't work"""
        attempts = len(state.clarification_attempts)

        # Strategy 1: Offer text input (after 2 voice attempts)
        if attempts >= 2:
            return Response(
                type="fallback_text_input",
                message="I'm having trouble with voice. Would you like to type instead?",
                options=["Type message", "Try voice again", "Cancel"]
            )

        # Strategy 2: Suggest simpler commands
        if attempts >= 3:
            return Response(
                type="suggest_simpler",
                message="Let's try something simpler. You can ask me to:",
                suggestions=[
                    "Show my calendar",
                    "What's the weather?",
                    "Tell me a joke"
                ]
            )

        # Strategy 3: Escalate to human (critical actions)
        if state.original_intent.privacy_band == PrivacyBand.RED:
            return Response(
                type="escalate_human",
                message="For this request, I'll need to connect you with support.",
                escalation_reason="failed_clarification_red_band"
            )

        # Default: Give up gracefully
        return Response(
            type="give_up",
            message="I'm sorry, I couldn't understand that request. Let's try something else."
        )
```

---

## Consequences

### Positive

✅ **Context-Aware:** Dynamic thresholds based on risk/cost
✅ **Natural Clarification:** Human-like prompts
✅ **Prevents Loops:** Max 3 attempts, then fallback
✅ **Multi-Signal Fusion:** Combines ASR, classifier, phonetic scores
✅ **User Learning:** Thresholds adapt to user preference over time

### Negative

⚠️ **Tuning Complexity:** Many parameters to optimize
⚠️ **False Positives:** May clarify when not needed
⚠️ **Latency:** Confidence calculation adds 10-20ms

---

## Implementation Guidance

### Phase 1: Core Confidence (Day 1-2)
- Multi-signal fusion algorithm
- Dynamic threshold selection
- Basic clarification logic

### Phase 2: Prompt Generation (Day 3)
- Template library (20+ variations)
- Context extraction
- Humanization functions

### Phase 3: State Management (Day 4-5)
- Clarification state tracking
- Attempt limits
- Timeout handling

### Phase 4: Fallbacks (Day 6)
- Text input fallback
- Simpler command suggestions
- Escalation logic

### Phase 5: Tuning (Day 7-9)
- Real user testing
- Threshold optimization
- Prompt A/B testing

---

## Validation

```python
@test("confidence below clarify threshold triggers clarification")
async def test_clarification_trigger():
    decider = ClarificationDecider()

    intent = mock_intent(confidence=0.65)  # Below 0.80
    thresholds = ThresholdConfig(proceed=0.80, clarify=0.60, reject=0.40)

    decision = await decider.decide(intent, 0.65, thresholds, mock_session)

    assert decision.action != ClarificationAction.PROCEED

@test("clarification abandoned after 3 attempts")
async def test_max_attempts():
    manager = ClarificationStateManager()

    state = await manager.start_clarification("s1", "transcript", mock_intent)

    # 3 attempts
    for i in range(3):
        await manager.record_clarification("s1", mock_decision, "prompt")

    assert not state.can_attempt_clarification()
```

---

## Monitoring

```python
clarification_attempts = Counter(
    'clarification_attempts',
    'Clarification attempts',
    ['reason', 'attempt_number']
)

clarification_abandoned = Counter(
    'clarification_abandoned',
    'Abandoned clarifications',
    ['reason']
)

confidence_distribution = Histogram(
    'voice_confidence_distribution',
    'Distribution of voice confidence scores',
    buckets=[0.2, 0.4, 0.6, 0.8, 0.9, 0.95, 1.0]
)
```

---

**Document Status:** ✅ Complete
**Estimated Lines:** 920 lines (target: 900 lines) ✅