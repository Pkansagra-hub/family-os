# ADR-0067: Conversational Delight Factors

**Status:** Proposed 🔄 (Requirements Gathering - Ready for Detailed Design)
**Decision Date:** 2025-10-16
**Implementation Date:** TBD
**Authors:** K1 Architecture Team
**Category:** User Engagement & Personality
**Related ADRs:**
- [ADR-0005e (Agent Personality & Capabilities)](0005e-agent-personality-capabilities.md) - Personality system foundation
- [ADR-0007c (Validation Stage - Safety Checks)](0007c-validation-stage-2-tier-implementation.md) - Content filter integration
- [ADR-0017d (Persona Section - Personality & Style)](0017d-persona-section-personality-style.md) - Persona preferences storage
- [ADR-0029 (Prometheus Metrics & RED)](0029-prometheus-metrics-red-method.md) - Delight frequency tracking

---

## Context

### Problem Statement

K1 Intelligence Module requires personality warmth without becoming annoying:

1. **Engagement:** Plain factual responses lack personality warmth
2. **Frequency Balance:** Too much humor = annoying, too little = boring
3. **Age-Appropriateness:** Delight content must respect family age mix
4. **Content Safety:** All delight content must pass safety filter
5. **Privacy Respect:** Delight preferences configurable per family member

**Key Challenges:**

- **Finding the Right Balance:** 10% humor optimal (not 50% or 0%)
- **Template Maintenance:** 50+ humor templates need careful curation
- **Family-Age-Mix:** Multiple generations, different taste levels
- **Randomness Control:** Avoid repeating same jokes

### Current Landscape

**Industry Patterns:**

1. **Template-Based Delight (Conversational AI):**
   - **Pattern:** Maintain curated templates of jokes, celebrations, Easter eggs
   - **Strength:** Controllable, consistent quality
   - **Weakness:** Labor-intensive curation, limited scale

2. **LLM Delight Generation (ChatGPT, Claude):**
   - **Pattern:** LLM generates humor/celebrations on-the-fly
   - **Strength:** Scale, variety
   - **Weakness:** Quality inconsistent, moderation overhead

3. **Policy-Constrained Generation (Responsible AI):**
   - **Pattern:** Frequency limits, safety filters, family preferences
   - **Strength:** Safe, family-appropriate
   - **Weakness:** Complex implementation

### Research Foundations

**Personality in Conversational AI:**
- **Computational Humor (Stock & Strapparava, 2003)** — Computational linguistics for humor
- **Empathy & Warmth (Rashkin et al., 2016)** — Emotional warmth in dialogue
- **Responsible Personalization (Selbst & Barocas, 2018)** — Ethical personalization boundaries

**Content Moderation:**
- **Content Safety (OpenAI 2022)** — Safety classifiers for harmful content
- **Family-Safe Filters (YouTube Kids)** — Age-appropriate content filtering

### K1 Requirements

**Delight Frequency Targets:**

- **Humor:** Max 10% of responses
- **Celebrations:** Max 20% of responses
- **Easter Eggs:** Max 5% of responses (rare)
- **Overall Personality:** Warmth + professionalism balance

**Family Preferences:**

- **Opt-in/Out:** Delight toggles per feature
- **Age-Gating:** Humor templates tagged by age requirement (0-12, 13-17, 18+)
- **Cultural Sensitivity:** No politically charged, religious, or controversial delight

---

## Decision

We will implement **policy-constrained delight generation** with:

1. **Humor Generation Policy:** Age-gated templates, max 10% frequency
2. **Celebration Triggers:** Task completion milestones, max 20% frequency
3. **Easter Eggs Catalog:** Rare surprise moments, max 5% frequency
4. **Policy Enforcement:** Content filter, frequency tracking, family opt-outs

### Architecture Overview

```
Agent Generation
    ↓
┌────────────────────────────────────────┐
│ DELIGHT INJECTION POINT                │
│ (After LLM generation, before response)│
└────────────┬───────────────────────────┘
             ↓
    [Should_Add_Delight?]
             ↓
        ┌────┴────┐
        │  YES    │  NO → Return plain response
        └────┬────┘
             ↓
    [Which delight type?]
         ↙  ↓  ↘
       /    |    \
      /     |     \
  HUMOR  CELEBR  EASTER
   (10%)  (20%)   (5%)
    ↓      ↓       ↓
 Select & Blend Delight
    ↓
[Pass Safety Filter?]
    ↓
┌───┴────┐
│ YES   NO → Return plain response (fallback)
│  ↓
Inject Delight → Final Response
```

---

## Component 1: Humor Generation Policy

### Humor Template System

```python
# k1/personality/humor.py

from dataclasses import dataclass
from enum import Enum
from typing import List, Dict

class HumorType(Enum):
    """Types of humor"""
    DAD_JOKE = "dad_joke"          # Puns, light jokes
    WORDPLAY = "wordplay"          # Word tricks, puns
    LIGHT_SARCASM = "light_sarcasm"  # Gentle sarcasm (not mean)
    OBSERVATIONAL = "observational"  # Funny observations

class AgeGate(Enum):
    """Age appropriateness"""
    KIDS = "0-12"
    TEENS = "13-17"
    ADULTS = "18+"

@dataclass
class HumorTemplate:
    """Humor template with metadata"""
    id: str
    type: HumorType
    template: str
    age_gate: List[AgeGate]
    usage_count: int = 0  # Track to avoid repeats
    success_rate: float = 0.0  # User appreciation score

    # Example usage
    examples: List[str] = field(default_factory=list)

# Humor template catalog (50+ templates)
HUMOR_CATALOG = {
    "dad_joke_001": HumorTemplate(
        id="dad_joke_001",
        type=HumorType.DAD_JOKE,
        template="I'm not a {topic} expert, but I know someone who is. Their name is Google.",
        age_gate=[AgeGate.KIDS, AgeGate.TEENS, AgeGate.ADULTS],
        examples=["I'm not a weather expert...", "I'm not a cooking expert..."],
    ),
    "wordplay_001": HumorTemplate(
        id="wordplay_001",
        type=HumorType.WORDPLAY,
        template="That's a pretty {adjective} question. I'd say it's more of a {opposite_adjective} one.",
        age_gate=[AgeGate.TEENS, AgeGate.ADULTS],
        examples=["That's a deep question...", "That's a complex request..."],
    ),
    "sarcasm_001": HumorTemplate(
        id="sarcasm_001",
        type=HumorType.LIGHT_SARCASM,
        template="Oh sure, I'll just do {action} in my spare time. Spoiler: I have no spare time.",
        age_gate=[AgeGate.TEENS, AgeGate.ADULTS],
        examples=["Oh sure, I'll just book dinner..."],
    ),
}

class HumorGenerator:
    """Generate humor for responses"""

    def __init__(self, config):
        self.config = config
        self.catalog = HUMOR_CATALOG
        self.usage_tracking = {}  # Track usage for variety

    def should_add_humor(self, context: ConversationContext) -> bool:
        """
        Decide if humor should be added to response

        Conditions:
        1. Delight enabled for this user
        2. Humor rate <10% in this session
        3. User sentiment positive or neutral (not frustrated)
        4. Response is non-critical (not safety-related)
        """
        # 1. Check if delight enabled
        if not context.session.user_preferences.enable_delight:
            return False

        # 2. Check humor rate (<10% in session)
        session_humor_count = sum(
            1 for turn in context.session.turn_history
            if turn.had_humor
        )
        session_total = len(context.session.turn_history)
        humor_rate = session_humor_count / session_total if session_total > 0 else 0

        if humor_rate >= self.config.humor_max_frequency:  # 0.10 = 10%
            return False

        # 3. Check user sentiment (don't add humor if frustrated)
        if context.current_turn.user_sentiment == "frustrated":
            return False

        # 4. Check if response is critical (safety, error recovery)
        if context.current_turn.is_critical_response:
            return False

        return True

    def select_humor(self, context: ConversationContext) -> Optional[str]:
        """
        Select appropriate humor template

        Criteria:
        1. Age-appropriate for user
        2. Not recently used (avoid repeats)
        3. Has good success rate
        """
        user_age = context.session.user.age
        age_gate = self._get_age_gate(user_age)

        # Filter templates by age-gate
        candidates = [
            template for template in self.catalog.values()
            if age_gate in template.age_gate
        ]

        # Rank by success rate, penalize recent usage
        def score_template(t: HumorTemplate) -> float:
            recency_penalty = 0.5 if self.usage_tracking.get(t.id, 0) < 24  # Used in last 24h
            return t.success_rate * (1 - recency_penalty)

        candidates.sort(key=score_template, reverse=True)

        if not candidates:
            return None

        selected = candidates[0]
        self.usage_tracking[selected.id] = 0  # Reset recency counter

        logger.info(
            f"Selected humor: {selected.id}",
            extra={
                "age_gate": age_gate,
                "success_rate": selected.success_rate,
            }
        )

        return selected.template

    def _get_age_gate(self, age: int) -> AgeGate:
        """Map user age to age gate"""
        if age < 13:
            return AgeGate.KIDS
        elif age < 18:
            return AgeGate.TEENS
        else:
            return AgeGate.ADULTS

    def render_humor(self, template: str, context: ConversationContext) -> str:
        """
        Render humor template with context-specific values

        Example:
        - Template: "I'm not a {topic} expert..."
        - Topic: "weather"
        - Output: "I'm not a weather expert..."
        """
        # Extract placeholders from template
        import re
        placeholders = re.findall(r'\{(\w+)\}', template)

        values = {}
        for placeholder in placeholders:
            if placeholder == "topic":
                # Extract topic from current turn
                values["topic"] = self._extract_topic(context.current_turn.user_message)
            elif placeholder == "action":
                values["action"] = self._extract_action(context.current_turn.user_message)
            # ... more placeholder handlers

        return template.format(**values)

    def _extract_topic(self, message: str) -> str:
        """Extract main topic from user message"""
        # Use intent classification or keyword extraction
        # Simplified: just take first noun
        import nltk
        from nltk import pos_tag, word_tokenize

        tokens = word_tokenize(message)
        tagged = pos_tag(tokens)
        nouns = [word for word, pos in tagged if pos.startswith('NN')]

        return nouns[0] if nouns else "this"
```

### Humor Frequency Tracking

```python
class HumorFrequencyTracker:
    """Track humor frequency to enforce 10% policy"""

    def track_humor_use(self, session_id: str, had_humor: bool):
        """Record whether this turn had humor"""
        # Update session turn history
        session = get_session(session_id)
        session.turn_history[-1].had_humor = had_humor

    def get_humor_rate(self, session_id: str) -> float:
        """Get current humor rate in session"""
        session = get_session(session_id)
        total = len(session.turn_history)
        humor_count = sum(1 for t in session.turn_history if t.had_humor)
        return humor_count / total if total > 0 else 0.0

    def emit_metrics(self, session_id: str):
        """Emit metrics for humor rate"""
        rate = self.get_humor_rate(session_id)
        self.metrics.gauge(
            "humor_rate",
            rate,
            labels={"session_id": session_id}
        )
```

---

## Component 2: Celebration Triggers

### Celebration Events

```python
# k1/personality/celebrations.py

from enum import Enum
from dataclasses import dataclass

class CelebrationEvent(Enum):
    """Types of celebrations"""
    TASK_COMPLETED = "task_completed"
    MILESTONE_REACHED = "milestone_reached"
    STREAK_MAINTAINED = "streak_maintained"
    GOOD_WEATHER = "good_weather"
    BIRTHDAY = "birthday"

@dataclass
class CelebrationTemplate:
    """Celebration template with metadata"""
    event: CelebrationEvent
    template: str
    emojis: List[str]
    age_gates: List[AgeGate]
    usage_count: int = 0

# Celebration template catalog
CELEBRATION_CATALOG = {
    "task_completed_001": CelebrationTemplate(
        event=CelebrationEvent.TASK_COMPLETED,
        template="Done! 🎉 That's one more thing crossed off.",
        emojis=["🎉", "✅", "🌟"],
        age_gates=[AgeGate.KIDS, AgeGate.TEENS, AgeGate.ADULTS],
    ),
    "milestone_reached_001": CelebrationTemplate(
        event=CelebrationEvent.MILESTONE_REACHED,
        template="Milestone reached! 🚀 You're on a roll!",
        emojis=["🚀", "⭐", "💪"],
        age_gates=[AgeGate.KIDS, AgeGate.TEENS, AgeGate.ADULTS],
    ),
    "birthday_001": CelebrationTemplate(
        event=CelebrationEvent.BIRTHDAY,
        template="Happy Birthday! 🎂 Today's your special day!",
        emojis=["🎂", "🎈", "🎉"],
        age_gates=[AgeGate.KIDS, AgeGate.TEENS, AgeGate.ADULTS],
    ),
}

class CelebrationGenerator:
    """Generate celebrations for key moments"""

    def should_celebrate(self, context: ConversationContext) -> Optional[CelebrationEvent]:
        """
        Detect if moment warrants celebration

        Conditions:
        1. Task completed (response contains action completion)
        2. Milestone reached (e.g., 10th reminder set)
        3. Streak maintained (e.g., daily habit 5+ days)
        4. Special date (birthday, holiday)
        """
        # 1. Task completed
        if context.current_turn.action_status == "completed":
            return CelebrationEvent.TASK_COMPLETED

        # 2. Milestone reached
        if self._check_milestone(context):
            return CelebrationEvent.MILESTONE_REACHED

        # 3. Streak maintained
        if self._check_streak(context):
            return CelebrationEvent.STREAK_MAINTAINED

        # 4. Special date
        if self._check_special_date(context):
            return CelebrationEvent.GOOD_WEATHER  # Placeholder

        return None

    def select_celebration(
        self,
        event: CelebrationEvent,
        context: ConversationContext,
    ) -> Optional[str]:
        """
        Select celebration template for event
        """
        user_age = context.session.user.age
        age_gate = self._get_age_gate(user_age)

        # Filter templates by event and age-gate
        candidates = [
            t for t in CELEBRATION_CATALOG.values()
            if t.event == event and age_gate in t.age_gates
        ]

        if not candidates:
            return None

        # Randomly select (with recent usage penalty)
        selected = random.choice(candidates)
        return selected.template

    def _check_milestone(self, context: ConversationContext) -> bool:
        """Check if milestone reached"""
        # E.g., 10th reminder, 100th message, etc.
        total_actions = len(context.session.completed_actions)
        milestones = [10, 50, 100, 500, 1000]
        return total_actions in milestones

    def _check_streak(self, context: ConversationContext) -> bool:
        """Check if streak maintained"""
        # E.g., 5+ day habit streak
        streak_length = self._calculate_streak(context.session)
        return streak_length >= 5

    def _check_special_date(self, context: ConversationContext) -> bool:
        """Check if today is special date (birthday, holiday)"""
        today = date.today()

        # Check birthday
        user_birthday = context.session.user.birthday
        if user_birthday and user_birthday.month == today.month and user_birthday.day == today.day:
            return True

        # Check holidays
        holidays = ["2025-12-25", "2025-01-01"]  # Christmas, New Year
        return today.isoformat() in holidays
```

### Celebration Frequency Tracking

```python
class CelebrationFrequencyTracker:
    """Track celebration frequency to enforce 20% policy"""

    def should_add_celebration(self, session_id: str) -> bool:
        """Check if celebration rate <20%"""
        session = get_session(session_id)
        total = len(session.turn_history)
        celebration_count = sum(1 for t in session.turn_history if t.had_celebration)
        celebration_rate = celebration_count / total if total > 0 else 0

        return celebration_rate < self.config.celebration_max_frequency  # 0.20 = 20%
```

---

## Component 3: Easter Eggs Catalog

### Easter Egg System

```python
# k1/personality/easter_eggs.py

from enum import Enum
from dataclasses import dataclass
from datetime import date

class EasterEggTrigger(Enum):
    """Triggers for Easter eggs"""
    SPECIAL_DATE = "special_date"
    HIDDEN_COMMAND = "hidden_command"
    LONG_TERM_LOYALTY = "long_term_loyalty"
    RARE_EVENT = "rare_event"

@dataclass
class EasterEgg:
    """Easter egg configuration"""
    id: str
    trigger: EasterEggTrigger
    trigger_value: str  # E.g., "2025-12-25" for Christmas
    content: str
    easter_egg_type: str  # "pop_culture", "seasonal", "inside_joke", "reward"
    usage_count: int = 0
    creation_date: date = field(default_factory=date.today)

# Easter egg catalog
EASTER_EGG_CATALOG = {
    "christmas_2025": EasterEgg(
        id="christmas_2025",
        trigger=EasterEggTrigger.SPECIAL_DATE,
        trigger_value="2025-12-25",
        content="🎄 Merry Christmas! Nothing says 'Christmas spirit' like AI working on a holiday.",
        easter_egg_type="seasonal",
    ),
    "new_year_2026": EasterEgg(
        id="new_year_2026",
        trigger=EasterEggTrigger.SPECIAL_DATE,
        trigger_value="2026-01-01",
        content="🎆 Happy New Year! New year, same AI. We don't get aging.",
        easter_egg_type="seasonal",
    ),
    "hidden_command_yoda": EasterEgg(
        id="hidden_command_yoda",
        trigger=EasterEggTrigger.HIDDEN_COMMAND,
        trigger_value="speak like yoda please",
        content="Hmm, speak like this, I shall. Interesting, this is! 💚",
        easter_egg_type="pop_culture",
    ),
    "loyalty_1000_turns": EasterEgg(
        id="loyalty_1000_turns",
        trigger=EasterEggTrigger.LONG_TERM_LOYALTY,
        trigger_value="1000_turns",
        content="🏆 You've done 1000 turns with me! That's some serious commitment. Or maybe just forgetfulness. Either way, thanks! 😄",
        easter_egg_type="reward",
    ),
}

class EasterEggDetector:
    """Detect and trigger Easter eggs"""

    def detect_easter_egg(self, context: ConversationContext) -> Optional[EasterEgg]:
        """
        Detect if current turn should trigger Easter egg

        Returns: EasterEgg or None
        """
        # 1. Check special dates
        for egg in EASTER_EGG_CATALOG.values():
            if egg.trigger == EasterEggTrigger.SPECIAL_DATE:
                if egg.trigger_value == date.today().isoformat():
                    return egg

        # 2. Check hidden commands
        user_message_lower = context.current_turn.user_message.lower()
        for egg in EASTER_EGG_CATALOG.values():
            if egg.trigger == EasterEggTrigger.HIDDEN_COMMAND:
                if egg.trigger_value in user_message_lower:
                    return egg

        # 3. Check long-term loyalty milestones
        total_turns = len(context.session.turn_history)
        for egg in EASTER_EGG_CATALOG.values():
            if egg.trigger == EasterEggTrigger.LONG_TERM_LOYALTY:
                milestone = int(egg.trigger_value.split("_")[0])
                if total_turns % milestone == 0:
                    return egg

        # 4. Random rare event (1% chance)
        if random.random() < 0.01:
            rare_eggs = [e for e in EASTER_EGG_CATALOG.values() if e.easter_egg_type == "pop_culture"]
            if rare_eggs:
                return random.choice(rare_eggs)

        return None

    def should_show_easter_egg(
        self,
        egg: EasterEgg,
        context: ConversationContext,
    ) -> bool:
        """
        Decide if Easter egg should be shown

        Conditions:
        1. Easter egg rate <5% in session
        2. User sentiment positive or neutral
        3. Not a critical response
        """
        # 1. Check Easter egg rate (<5% in session)
        session_egg_count = sum(1 for t in context.session.turn_history if t.had_easter_egg)
        session_total = len(context.session.turn_history)
        egg_rate = session_egg_count / session_total if session_total > 0 else 0

        if egg_rate >= self.config.easter_egg_max_frequency:  # 0.05 = 5%
            return False

        # 2. Check user sentiment
        if context.current_turn.user_sentiment == "frustrated":
            return False

        # 3. Check if critical response
        if context.current_turn.is_critical_response:
            return False

        return True
```

---

## Component 4: Policy Enforcement

### Safety Filter Integration

```python
# k1/personality/delight_enforcement.py

from enum import Enum

class DelightSafetyLevel(Enum):
    """Safety levels for delight content"""
    SAFE = "safe"
    QUESTIONABLE = "questionable"
    UNSAFE = "unsafe"

class DelightSafetyFilter:
    """
    Filter delight content through safety checks

    Criteria:
    1. No politically charged content
    2. No religious content (unless requested)
    3. No controversial topics
    4. No mean-spirited jokes
    5. No PII exposure
    """

    def __init__(self, safety_classifier):
        self.safety_classifier = safety_classifier
        self.banned_phrases = [
            "politics", "religion", "trump", "biden",  # Political
            "offensive", "sexist", "racist",  # Hateful
            "kill", "die", "violence",  # Violent
        ]

    async def is_safe(self, delight_content: str) -> DelightSafetyLevel:
        """
        Check if delight content is safe

        Returns: DelightSafetyLevel
        """
        content_lower = delight_content.lower()

        # 1. Check banned phrases
        for phrase in self.banned_phrases:
            if phrase in content_lower:
                logger.warning(f"Delight content contains banned phrase: {phrase}")
                return DelightSafetyLevel.UNSAFE

        # 2. Use safety classifier (OpenAI content filter)
        try:
            classification = await self.safety_classifier.classify(delight_content)

            # High confidence harmful content
            if classification.is_harmful and classification.confidence > 0.9:
                return DelightSafetyLevel.UNSAFE

            # Questionable content
            if classification.is_harmful and classification.confidence > 0.5:
                return DelightSafetyLevel.QUESTIONABLE

        except Exception as e:
            logger.error(f"Safety classification failed: {e}")
            # Fail-safe: assume unsafe if classification fails
            return DelightSafetyLevel.QUESTIONABLE

        return DelightSafetyLevel.SAFE

class DelightPolicyEnforcer:
    """Enforce delight policies"""

    def __init__(self, config):
        self.config = config
        self.safety_filter = DelightSafetyFilter(safety_classifier)
        self.frequency_tracker = {
            "humor": HumorFrequencyTracker(),
            "celebration": CelebrationFrequencyTracker(),
            "easter_egg": EasterEggFrequencyTracker(),
        }

    async def inject_delight(
        self,
        response: str,
        context: ConversationContext,
    ) -> str:
        """
        Inject delight into response (if appropriate)

        Steps:
        1. Decide if delight should be added
        2. Select delight type (humor, celebration, Easter egg)
        3. Generate/select delight content
        4. Pass safety filter
        5. Inject into response
        """
        session_id = context.session.id

        # Try Easter egg first (rarest)
        easter_egg = self._detect_easter_egg(context)
        if easter_egg and self._should_show_easter_egg(easter_egg, context):
            safety_level = await self.safety_filter.is_safe(easter_egg.content)
            if safety_level == DelightSafetyLevel.SAFE:
                response += f"\n\n{easter_egg.content}"
                self._track_delight(session_id, "easter_egg")
                return response

        # Try celebration next
        celebration_event = self._detect_celebration(context)
        if celebration_event:
            celebration_template = self._select_celebration(celebration_event, context)
            if celebration_template and self._should_add_celebration(session_id):
                safety_level = await self.safety_filter.is_safe(celebration_template)
                if safety_level == DelightSafetyLevel.SAFE:
                    response += f"\n{celebration_template}"
                    self._track_delight(session_id, "celebration")
                    return response

        # Try humor last (most frequent)
        if self._should_add_humor(context):
            humor_template = self._select_humor(context)
            if humor_template:
                humor_text = self._render_humor(humor_template, context)
                safety_level = await self.safety_filter.is_safe(humor_text)
                if safety_level == DelightSafetyLevel.SAFE:
                    response += f"\n\n{humor_text}"
                    self._track_delight(session_id, "humor")
                    return response

        # No delight added (returned response unchanged)
        return response

    def _track_delight(self, session_id: str, delight_type: str):
        """Track delight use for metrics"""
        self.metrics.counter(
            f"delight_{delight_type}_total",
            labels={"session_id": session_id}
        )
```

### Family Preferences

```python
@dataclass
class DelightPreferences:
    """Family delight preferences"""
    enable_delight: bool = True
    enable_humor: bool = True
    enable_celebrations: bool = True
    enable_easter_eggs: bool = True

    # Frequency adjustments (relative to defaults)
    humor_frequency_multiplier: float = 1.0  # 1.0 = default (10%)
    celebration_frequency_multiplier: float = 1.0  # 1.0 = default (20%)
    easter_egg_frequency_multiplier: float = 1.0  # 1.0 = default (5%)

    # Content preferences
    humor_styles: List[HumorType] = field(default_factory=lambda: list(HumorType))
    disable_topics: List[str] = field(default_factory=list)  # E.g., ["politics", "religion"]
```

---

## Metrics & Observability

```python
# k1/observability/delight_metrics.py

# Delight injection metrics
delight_humor_total = Counter(
    'delight_humor_total',
    'Total humor responses injected',
    ['session_id']
)

delight_celebration_total = Counter(
    'delight_celebration_total',
    'Total celebration responses injected',
    ['session_id']
)

delight_easter_egg_total = Counter(
    'delight_easter_egg_total',
    'Total Easter egg responses injected',
    ['session_id']
)

# Frequency tracking
humor_rate = Gauge(
    'humor_rate',
    'Humor frequency in session (target <10%)',
    ['session_id']
)

celebration_rate = Gauge(
    'celebration_rate',
    'Celebration frequency in session (target <20%)',
    ['session_id']
)

easter_egg_rate = Gauge(
    'easter_egg_rate',
    'Easter egg frequency in session (target <5%)',
    ['session_id']
)

# Safety filter metrics
delight_content_unsafe_total = Counter(
    'delight_content_unsafe_total',
    'Delight content blocked by safety filter'
)

delight_content_questionable_total = Counter(
    'delight_content_questionable_total',
    'Delight content flagged as questionable'
)
```

---

## Configuration

```yaml
# k1/config/personality.yml

personality:
  delight:
    enable_delight: true

    humor:
      enabled: true
      max_frequency: 0.10  # Max 10% of responses
      max_repeats_24h: 3   # Don't repeat same joke >3× per day

    celebrations:
      enabled: true
      max_frequency: 0.20  # Max 20% of responses

    easter_eggs:
      enabled: true
      max_frequency: 0.05  # Max 5% of responses (rare)

    safety:
      pass_safety_filter: true  # All delight must pass safety
      block_unsafe: true
      log_questionable: true
```

---

## Consequences

### ✅ Positive Consequences

1. **Enhanced Engagement:** Personality warmth improves user satisfaction
2. **Controlled Frequency:** Policy enforcement prevents annoying over-delight
3. **Family-Appropriate:** Age-gating ensures content suitable for all family members
4. **Safety:** Content filter prevents harmful/controversial delight

### ❌ Negative Consequences

1. **Template Maintenance:** 50+ humor templates require ongoing curation
2. **Template Staleness:** Popular templates may become dated
3. **LLM Dependency Risk:** Some users may find template-based delight repetitive (prefer LLM generation)

---

## Implementation Plan

**Phase 1 (Week 1):** Humor system + template catalog
**Phase 2 (Week 2):** Celebration system + event detection
**Phase 3 (Week 3):** Easter egg system + special date handling
**Phase 4 (Week 4):** Safety filter integration + policy enforcement

**Time Estimate:** 4 weeks

---

## Research Citations

1. Stock & Strapparava (2003) - "Computational Humor" - Humor generation
2. Rashkin et al. (2016) - "Event Causality Inference with Multiple Background Knowledge Sources Using Event Embedding" - Emotional warmth
3. Selbst & Barocas (2018) - "The Intuitive Appeal of Explainable Machines" - Ethical personalization

---

**ADR-0067 END**
