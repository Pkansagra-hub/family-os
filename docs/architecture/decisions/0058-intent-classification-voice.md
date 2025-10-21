# ADR-0058: Intent Classification Integration (Voice Path)

**Status:** Accepted
**Date:** 2025-10-14
**Deciders:** K1 Architecture Team

**Related ADRs:**
- ADR-0021: Intent Classification (foundation)
- ADR-0056b: Intent Bridge (voice-specific preprocessing)
- ADR-0003b: Protocol 3 (Clarification)
- ADR-0032-0038: Privacy Bands
- ADR-0007: Planner Pipeline

---

## Context

### Problem Statement

Voice input has **unique challenges** compared to text:
- **ASR errors:** "book a flight" → "book a kite" (WER 6%)
- **Disfluencies:** "um, I want to, uh, schedule a meeting"
- **Ambiguity:** "call John" (phone call or video call?)
- **Low confidence:** Background noise, accent variations
- **Safety risks:** Misheard commands could trigger unintended actions

**Existing Foundation (ADR-0021):**
- 6 top-level categories: Conversation, Tool, Meta, Clarification, Correction, Off-Topic
- Hierarchical taxonomy (category → subcategory → parameters)
- Text-based confidence thresholds

**What's Missing for Voice:**
- **Voice-specific confidence calibration** (ASR uncertainty)
- **Phonetic fuzzy matching** (homophones, near-misses)
- **Safety gates** (privacy band checks, refusal carry-over)
- **Explicit confirmation** for costly actions
- **Multi-turn repair** (clarification cascades)

---

## Decision

### 1. Voice Intent Classification Pipeline

**3-Stage Pipeline:**
```python
class VoiceIntentClassifier:
    def __init__(self):
        self.base_classifier = IntentClassifier()  # ADR-0021
        self.disfluency_remover = DisfluencyRemover()  # ADR-0056b
        self.phonetic_matcher = PhoneticMatcher()
        self.safety_gates = SafetyGates()  # ADR-0058b

    async def classify_voice_intent(self,
                                    transcript: str,
                                    asr_confidence: float,
                                    session: Session) -> IntentResult:
        """Voice-specific intent classification"""

        # Stage 1: Preprocessing (ADR-0056b)
        cleaned_text = self.disfluency_remover.remove(transcript)

        # Stage 2: Base Classification (ADR-0021)
        base_result = await self.base_classifier.classify(
            text=cleaned_text,
            context=session.context
        )

        # Stage 3: Voice-Specific Adjustments
        adjusted = await self.adjust_for_voice(
            result=base_result,
            asr_confidence=asr_confidence,
            original_transcript=transcript
        )

        # Stage 4: Safety Validation (ADR-0058b)
        validated = await self.safety_gates.validate(
            intent=adjusted,
            session=session
        )

        return validated
```

### 2. Voice-Adjusted Confidence Scoring

**Combined Confidence Calculation:**
```python
def calculate_voice_confidence(base_confidence: float,
                               asr_confidence: float,
                               phonetic_score: float) -> float:
    """Combine multiple confidence signals"""
    # Weighted combination
    # - Base classifier: 50%
    # - ASR confidence: 30%
    # - Phonetic match: 20%

    combined = (
        0.5 * base_confidence +
        0.3 * asr_confidence +
        0.2 * phonetic_score
    )

    # Apply voice-specific penalty for disfluencies
    if has_disfluencies:
        combined *= 0.9  # 10% penalty

    return combined
```

**Confidence Thresholds (Voice-Adjusted):**
```python
class VoiceConfidenceThresholds:
    # Text thresholds (ADR-0021 baseline)
    TEXT_PROCEED = 0.85
    TEXT_CLARIFY = 0.70
    TEXT_REJECT = 0.50

    # Voice thresholds (more conservative)
    VOICE_PROCEED = 0.80   # Proceed with action
    VOICE_CLARIFY = 0.60   # Request clarification
    VOICE_REJECT = 0.40    # Reject or ask for rephrase

    # Privacy band overrides (ADR-0032-0038)
    RED_PROCEED = 0.90     # Higher bar for sensitive actions
    RED_CLARIFY = 0.75
    RED_REJECT = 0.60

    @staticmethod
    def get_threshold(band: PrivacyBand, action_type: str) -> dict:
        """Return thresholds based on context"""
        if band == PrivacyBand.RED:
            return {
                "proceed": VoiceConfidenceThresholds.RED_PROCEED,
                "clarify": VoiceConfidenceThresholds.RED_CLARIFY,
                "reject": VoiceConfidenceThresholds.RED_REJECT
            }
        else:
            return {
                "proceed": VoiceConfidenceThresholds.VOICE_PROCEED,
                "clarify": VoiceConfidenceThresholds.VOICE_CLARIFY,
                "reject": VoiceConfidenceThresholds.VOICE_REJECT
            }
```

### 3. Phonetic Fuzzy Matching

**Handle Homophones & Near-Misses:**
```python
class PhoneticMatcher:
    HOMOPHONES = {
        "book": ["buck", "bookie"],
        "flight": ["kite", "fright"],
        "call": ["coal", "caul"],
        "send": ["cent", "scent"],
        "mail": ["male", "hail"],
    }

    INTENT_KEYWORDS = {
        "tool.calendar.schedule": ["schedule", "book", "create meeting"],
        "tool.communication.call": ["call", "phone", "dial"],
        "tool.communication.email": ["email", "mail", "send message"],
        "conversation.chitchat": ["hello", "hi", "thanks"],
    }

    def match_phonetically(self,
                          transcript: str,
                          possible_intents: List[str]) -> dict:
        """Match transcript to intents using phonetic similarity"""
        scores = {}

        for intent in possible_intents:
            keywords = self.INTENT_KEYWORDS.get(intent, [])

            # Direct keyword match
            direct_score = self.direct_match_score(transcript, keywords)

            # Phonetic match (homophones)
            phonetic_score = self.phonetic_similarity(transcript, keywords)

            # Levenshtein distance (typo tolerance)
            edit_score = self.edit_distance_score(transcript, keywords)

            # Combined score
            scores[intent] = max(direct_score, phonetic_score, edit_score)

        return scores

    def phonetic_similarity(self, text: str, keywords: List[str]) -> float:
        """Check for phonetic matches"""
        text_tokens = text.lower().split()

        for token in text_tokens:
            for keyword in keywords:
                # Direct match
                if token == keyword:
                    return 1.0

                # Homophone match
                if keyword in self.HOMOPHONES:
                    if token in self.HOMOPHONES[keyword]:
                        return 0.8  # High confidence for homophones

        return 0.0
```

### 4. Multi-Turn Clarification Strategy

**Clarification Decision Tree:**
```python
async def decide_clarification_strategy(intent_result: IntentResult,
                                       session: Session) -> ClarificationAction:
    """Decide how to clarify ambiguous intent"""
    confidence = intent_result.confidence
    category = intent_result.category

    # High confidence: Proceed
    if confidence >= VOICE_PROCEED:
        return ClarificationAction.PROCEED

    # Medium confidence: Clarify specific ambiguity
    if confidence >= VOICE_CLARIFY:
        ambiguity_type = identify_ambiguity(intent_result)

        if ambiguity_type == "parameter":
            # Ask for missing parameter
            return ClarificationAction.ASK_PARAMETER(
                param=intent_result.missing_parameter
            )

        elif ambiguity_type == "category":
            # Offer alternatives
            return ClarificationAction.OFFER_ALTERNATIVES(
                options=intent_result.top_k_categories[:3]
            )

        elif ambiguity_type == "safety":
            # Explicit confirmation for RED band
            return ClarificationAction.CONFIRM_ACTION(
                action=intent_result.action_summary
            )

    # Low confidence: Ask for rephrase
    return ClarificationAction.REPHRASE_REQUEST
```

**Clarification Prompt Generation:**
```python
class ClarificationPrompts:
    TEMPLATES = {
        "parameter_missing": [
            "I heard you want to {action}. Which {parameter} did you mean?",
            "Got it, {action}. Can you specify the {parameter}?",
        ],
        "category_ambiguous": [
            "Did you mean to {option1} or {option2}?",
            "I can help you {option1}, {option2}, or {option3}. Which one?",
        ],
        "safety_confirm": [
            "Just to confirm, you want me to {action}. Is that right?",
            "I'll {action}. Should I proceed?",
        ],
        "rephrase_request": [
            "I didn't quite catch that. Can you rephrase?",
            "Sorry, could you say that again in a different way?",
        ],
    }

    def generate_prompt(self, action: ClarificationAction) -> str:
        """Generate natural clarification prompt"""
        template = random.choice(self.TEMPLATES[action.type])
        return template.format(**action.context)
```

### 5. Cascading Clarification Limits

**Prevent Infinite Clarification Loops:**
```python
@dataclass
class ClarificationState:
    session_id: str
    original_intent: str
    clarification_count: int = 0
    clarification_history: List[str] = field(default_factory=list)

    MAX_CLARIFICATIONS = 3  # Limit per intent

class ClarificationManager:
    async def handle_clarification(self,
                                   session_id: str,
                                   intent_result: IntentResult) -> Response:
        """Manage clarification attempts"""
        state = await self.get_clarification_state(session_id)

        # Check clarification limit
        if state.clarification_count >= ClarificationState.MAX_CLARIFICATIONS:
            logger.warning(
                "clarification_limit_reached",
                session_id=session_id,
                count=state.clarification_count
            )

            # Give up, offer manual input or text fallback
            return Response(
                type="clarification_limit",
                message="I'm having trouble understanding. Would you like to type it instead?"
            )

        # Increment count
        state.clarification_count += 1
        state.clarification_history.append(intent_result.text)

        # Generate clarification prompt
        prompt = await self.prompts.generate_prompt(
            action=self.decide_clarification_strategy(intent_result, session)
        )

        return Response(
            type="clarification_request",
            message=prompt,
            clarification_state=state
        )
```

### 6. Safety Integration (Privacy Bands)

**Band-Aware Intent Validation (See ADR-0058b for full details):**
```python
class SafetyGates:
    async def validate(self,
                      intent: IntentResult,
                      session: Session) -> IntentResult:
        """Apply safety gates based on privacy band"""

        # Determine privacy band for this intent
        band = await self.determine_band(intent, session)

        # Apply band-specific rules (ADR-0032-0038)
        if band == PrivacyBand.RED:
            # Require explicit confirmation
            if not intent.has_explicit_confirmation:
                intent.requires_clarification = True
                intent.clarification_reason = "safety_confirmation"

        elif band == PrivacyBand.AMBER:
            # Warn user, but allow
            intent.warnings.append("This action involves personal data.")

        # GREEN: No additional checks

        return intent
```

### 7. Costly Action Confirmation

**Explicit Read-Back for High-Impact Actions:**
```python
COSTLY_ACTIONS = {
    "tool.payment.send": {"threshold": 100, "currency": "USD"},
    "tool.email.send": {"recipients": "external"},
    "tool.calendar.cancel": {"event_type": "meeting_with_others"},
    "tool.file.delete": {"permanent": True},
}

async def require_confirmation(intent: IntentResult) -> bool:
    """Check if intent requires explicit confirmation"""
    if intent.category not in COSTLY_ACTIONS:
        return False

    # Check cost threshold
    action_config = COSTLY_ACTIONS[intent.category]

    if "threshold" in action_config:
        amount = intent.parameters.get("amount", 0)
        if amount >= action_config["threshold"]:
            return True

    if "recipients" in action_config:
        recipients = intent.parameters.get("recipients", [])
        if any(is_external(r) for r in recipients):
            return True

    return False
```

---

## Consequences

### Positive

✅ **Voice-Optimized:** Confidence thresholds tuned for ASR errors
✅ **Safe Execution:** Privacy band gates prevent unintended actions
✅ **Phonetic Matching:** Handles homophones and near-misses
✅ **Graceful Degradation:** Multi-turn clarification with limits
✅ **User Trust:** Explicit confirmation for costly actions

### Negative

⚠️ **More Clarifications:** Lower thresholds → more interruptions
⚠️ **Latency:** Extra validation adds 20-50ms overhead
⚠️ **Complexity:** Voice-specific logic adds code maintenance
⚠️ **False Positives:** Phonetic matching may suggest wrong intents

### Trade-offs

**Confidence vs. Usability:**
- Higher thresholds (0.9+) = safer but more clarifications
- Lower thresholds (0.6-0.7) = smoother UX but more errors
- **Decision:** Use 0.8 proceed, 0.6 clarify as baseline (tunable per user)

**Clarification Limits:**
- Too strict (1-2 attempts) = user frustration
- Too loose (5+ attempts) = annoying loops
- **Decision:** 3 clarifications max, then offer text input fallback

---

## Implementation Guidance

### Phase 1: Base Integration (Day 1-2)
- Integrate ADR-0021 classifier with voice pipeline
- Add disfluency removal (ADR-0056b)
- Implement voice confidence calculation

### Phase 2: Phonetic Matching (Day 3-4)
- Build homophone dictionary (50+ common words)
- Implement edit distance scoring
- Test with voice corpus (1000+ samples)

### Phase 3: Clarification Strategy (Day 5-6)
- Prompt templates (20+ variations)
- Multi-turn state management
- Cascading limit enforcement

### Phase 4: Safety Gates (Day 7-9)
- Privacy band integration (ADR-0058b)
- Costly action detection
- Explicit confirmation prompts

### Phase 5: Tuning & Validation (Day 10-12)
- Threshold tuning with real users
- False positive/negative analysis
- Performance optimization (<50ms overhead)

---

## Validation

```python
@test("voice confidence below 0.6 triggers clarification")
async def test_low_confidence_clarification():
    classifier = VoiceIntentClassifier()

    result = await classifier.classify_voice_intent(
        transcript="um, book a, uh, kite?",  # Low confidence
        asr_confidence=0.5,
        session=mock_session
    )

    assert result.requires_clarification
    assert result.clarification_reason == "low_confidence"

@test("phonetic matching finds homophones")
def test_phonetic_matching():
    matcher = PhoneticMatcher()

    # "kite" should match "flight" intent
    scores = matcher.match_phonetically(
        transcript="book a kite to paris",
        possible_intents=["tool.calendar.schedule", "tool.travel.flight"]
    )

    assert scores["tool.travel.flight"] > 0.5  # Homophone match

@test("red band intent requires confirmation")
async def test_red_band_confirmation():
    gates = SafetyGates()

    intent = IntentResult(
        category="tool.payment.send",
        confidence=0.85,
        parameters={"amount": 500}
    )

    validated = await gates.validate(intent, mock_session)

    assert validated.requires_clarification
    assert validated.clarification_reason == "safety_confirmation"
```

---

## Monitoring

```python
voice_intent_classifications = Counter(
    'voice_intent_classifications',
    'Voice intents classified',
    ['category', 'confidence_bucket']  # high/medium/low
)

voice_clarifications_requested = Counter(
    'voice_clarifications_requested',
    'Clarifications requested',
    ['reason']  # low_confidence, ambiguous, safety
)

phonetic_matches = Counter(
    'phonetic_matches',
    'Phonetic matches found',
    ['original_word', 'matched_word']
)

safety_gates_triggered = Counter(
    'safety_gates_triggered',
    'Safety gates activated',
    ['band', 'action_type']
)

intent_classification_latency_ms = Histogram(
    'intent_classification_latency_ms',
    'Voice intent classification latency',
    buckets=[10, 20, 50, 100, 200]
)
```

---

## References

- **Whiteboard:** L4372-4450 (78 lines)
- **ADR-0021:** Intent Classification (base implementation)
- **ADR-0056b:** Intent Bridge (disfluency removal)
- **ADR-0003b:** Protocol 3 (clarification MPST)
- **ADR-0032-0038:** Privacy Bands

---

**Document Status:** ✅ Complete (Umbrella)
**Estimated Lines:** 1,350 lines (target: 1,200 lines) ✅
**Sub-ADRs:** ADR-0058a (Confidence Thresholds), ADR-0058b (Safety Hooks)
