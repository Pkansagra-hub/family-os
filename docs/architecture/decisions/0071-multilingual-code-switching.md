---
adr_number: '0071'
title: Multilingual & Code-Switching
status: PROPOSED
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
- compliance
- cost
- modularity
- observability
- performance
- privacy
- reliability
- scalability
- security
- testing
- ux
supersedes: []
superseded_by: []
related_adrs:
- ADR-0005e
- ADR-0010
- ADR-0017
- ADR-0017d
- ADR-0021
- ADR-0029
- ADR-0032
- ADR-0056d
- ADR-0070
- ADR-0074
- ADR-0075
- ADR-0076
implementation_status: COMPLETED
implementation_date: null
implementation_phase: null
related_contracts: []
related_diagrams: []
research_citations:
- Conneau & Lample (2019)
- Devlin et al. (2018)
- Grave et al. (2018)
- Joulin et al. (2017)
- Lample (2019)
- Luo et al. (2020)
- Solorio et al. (2014)
propagation:
  triggers:
  - Modifying system architecture
  - Performance requirement changes
  - Updating API contracts or schemas
  affected_adrs:
  - ADR-0005e
  - ADR-0010
  - ADR-0017
  - ADR-0017d
  - ADR-0021
  - ADR-0029
  - ADR-0032
  - ADR-0056d
  - ADR-0070
  - ADR-0074
  - ADR-0075
  - ADR-0076
  affected_contracts:
  - k0/contracts/api/rest/idempotency/24h_retention.yml
  - k0/contracts/asyncapi.events.yaml
  - k0/contracts/openapi.k0.yaml
  - k1/contracts/flatbuffers/layer3_execution/mcp_message.fbs
  - k1/contracts/flatbuffers/layer3_execution/mcp_resource_request.fbs
  - k1/contracts/flatbuffers/layer3_execution/mcp_resource_response.fbs
  - k1/contracts/flatbuffers/layer3_execution/mcp_tool_discovery.fbs
  - k1/contracts/flatbuffers/layer3_execution/model_cache_entry.fbs
  - k1/contracts/flatbuffers/layer3_execution/model_request.fbs
  - k1/contracts/flatbuffers/layer3_execution/model_response.fbs
  affected_tests: []
---


# ADR-0071: Multilingual & Code-Switching

**Status:** Proposed 🔄
**Created:** October 16, 2025
**Authors:** Architecture Team
**Type:** Single ADR
**Supercedes:** None
**Superseded By:** None

---

## Table of Contents

1. [Overview](#overview)
2. [Context](#context)
3. [Decision](#decision)
4. [Alternatives](#alternatives)
5. [Components](#components)
6. [Consequences](#consequences)
7. [Implementation](#implementation)
8. [Metrics & Observability](#metrics--observability)
9. [Configuration](#configuration)
10. [Security & Privacy](#security--privacy)
11. [Research Foundation](#research-foundation)
12. [Related ADRs](#related-adrs)

---

## Overview

**Purpose:** Establish formal specification for multilingual support and code-switching (language mixing) in conversational AI.

**Problem Statement:**
- Multi-generational families speak multiple languages (English, Spanish, Mandarin, etc.)
- Users often code-switch (mix languages) naturally: "¿Cómo está the weather today?"
- Current system assumes single language preference with no code-switching support
- No language detection on user input (relies on manual preference setting)
- No agent code-switching (agent speaks only one language despite mixed-language input)

**Gap Addressed:** Requirement #5 (Style, Voice & Persona) - **Multilingual ADR missing**

**Business Value:**
1. ✅ Expand addressable market (non-English families)
2. ✅ More natural conversations (support code-switching patterns)
3. ✅ Better family inclusivity (each member's language preference respected)
4. ✅ Competitive parity (similar systems support 50+ languages)

---

## Context

### Current State (Before ADR-0071)

**Language Support:**
- ✅ `preferred_language` field in SessionState.persona (ADR-0017d)
- ❌ No language detection (user language assumed = preferred_language)
- ❌ No code-switching (agent speaks one language regardless)
- ❌ No multi-language message routing
- ❌ Translation not supported (external APIs would violate privacy)

**Persona Section (SessionState):**

```python
@dataclass
class Persona:
    preferred_language: str           # e.g., "en-US"
    style_formality: float
    humor_preference: str
    # ... other preferences
    # MISSING: code_switching_enabled, language_detection_confidence_threshold
```

**Supported Languages (Hypothetical - Not yet Implemented):**
- English (en-US, en-GB, en-AU, en-NZ, en-CA)
- Spanish (es-ES, es-MX, es-AR)
- French (fr-FR, fr-CA)
- German (de-DE, de-AT)
- Italian (it-IT)
- Portuguese (pt-BR, pt-PT)
- Mandarin Chinese (zh-CN, zh-TW)
- Japanese (ja-JP)
- Korean (ko-KR)

**Existing ADRs:**
- **ADR-0017d:** Persona section (stores `preferred_language`)
- **ADR-0005e:** Personality system (can extend with language preferences)
- **ADR-0021:** Intent Classification (assumes single language input)

### Desired End State (After ADR-0071)

```
User Utterance (Mixed Language)
    ↓
"¿Cómo está the weather today?"
    ↓
┌─────────────────────────────────────────┐
│  Language Detection Module              │
│  - Detect primary language: Spanish     │
│  - Detect secondary language: English   │
│  - Confidence: 0.92 (Spanish), 0.88 (En)|
└─────────────────────────────────────────┘
    ↓ (if code-switching detected & enabled)
┌─────────────────────────────────────────┐
│  Code-Switching Handler                 │
│  - User mixing languages intentionally  │
│  - Agent mirrors code-switching pattern |
│  - Response: "El weather hoy está sunny"|
└─────────────────────────────────────────┘
    ↓ (if single-language mode)
┌─────────────────────────────────────────┐
│  Language Confirmation Dialog           │
│  - Clarify intended language            │
│  - User confirms: "Español, por favor"  │
└─────────────────────────────────────────┘
    ↓
├── Intent Classification (Spanish)
├── Tool Execution
├── Response Generation (Spanish)
└── TTS (Spanish voice)
```

---

## Decision

### Core Decision

**We will implement 4-tier multilingual system:**

1. **Tier 1: Language Preference**
   - Per-user preference stored in SessionState.persona
   - 9 languages supported (en, es, fr, de, it, pt, zh, ja, ko)
   - Preference override possible per-message

2. **Tier 2: Language Detection**
   - Automatic detection on every user input
   - Confidence threshold (0.8 = auto-switch, <0.8 = confirm)
   - Multi-language detection for code-switching patterns

3. **Tier 3: Code-Switching Support**
   - Opt-in feature (disabled by default for gradual rollout)
   - Agent mirrors user's code-switching pattern
   - Mixed-language response generation (if user mixes)

4. **Tier 4: Family-Level Language Preferences**
   - Each family member has own `preferred_language`
   - No automatic translation between family members (privacy)
   - Per-session language inheritance (parent → child)

### Why This Approach

| Aspect | Decision | Rationale |
|--------|----------|-----------|
| **Storage** | SessionState.persona per user | Persistent, family-specific, K0-managed (ADR-0017d) |
| **Detection** | Automatic per-message | More responsive than manual switching, better UX |
| **Code-Switching** | Opt-in, mirror user pattern | Gradual rollout, prevents forced language mixing |
| **Confidence Threshold** | 0.8 (auto-switch), <0.8 (confirm) | Balances automation vs accuracy |
| **Translation** | None (privacy-first) | External APIs violate AMBER band policies |
| **Fallback** | Default to `preferred_language` | Safe default when detection fails |

### What We're NOT Doing

- ❌ Automatic translation (privacy violation, external API)
- ❌ Force single-language conversations (breaks natural code-switching)
- ❌ Cross-family message translation (violates family privacy)
- ❌ Real-time dialect adaptation (out of scope, future enhancement)
- ❌ Linguistic analysis (sentiment, pragmatics in non-English - future)

---

## Alternatives

### Alternative 1: External Translation Service (Google Translate, DeepL)
**Pros:**
- High-quality translations (90%+ BLEU)
- Supports 100+ languages
- Mature, battle-tested service

**Cons:**
- ❌ Privacy violation (AMBER band messages leave K0)
- ❌ Latency impact (network round-trip, +200-500ms per translation)
- ❌ Cost (per-call pricing, $0.01-0.02 per request)
- ❌ Requires GDPR DPA with provider
- ❌ Cannot support offline mode

**Decision:** Rejected. K0 is single-tenant; messages are AMBER band PII. No external APIs allowed.

---

### Alternative 2: Local ML Translation Model (mBART, M2M100)
**Pros:**
- No external APIs (privacy ✅)
- Runs locally in K0 (offline support)
- ~85% BLEU score (acceptable quality)

**Cons:**
- ❌ Model deployment complexity (1.6GB model size, ~500ms inference)
- ❌ Not needed for code-switching (user message is already understandable)
- ❌ Overkill for current use case
- ⚠️ Future option if cross-family translation becomes requirement

**Decision:** Defer to future ADR. Code-switching support doesn't require translation.

---

### Alternative 3: Force Single Language (No Code-Switching)
**Pros:**
- Simpler implementation (no code-switching logic)
- Deterministic behavior (no ambiguity)

**Cons:**
- ❌ Breaks natural conversational patterns
- ❌ Forces users to "normalize" input
- ❌ Poor UX for bilingual families
- ❌ Competitive disadvantage vs systems supporting code-switching

**Decision:** Rejected. Code-switching is natural linguistic behavior; we support it.

---

## Components

### Component 1: Language Detection

**Responsibility:** Identify language(s) in user message

**Input:** User message (string)
**Output:** Detected languages with confidence scores

**Detection Algorithm:**

```python
from typing import Dict, Tuple, List
from dataclasses import dataclass
import enum

class LanguageCode(enum.Enum):
    """Supported language codes"""
    EN = "en"                         # English
    ES = "es"                         # Spanish
    FR = "fr"                         # French
    DE = "de"                         # German
    IT = "it"                         # Italian
    PT = "pt"                         # Portuguese
    ZH = "zh"                         # Mandarin Chinese
    JA = "ja"                         # Japanese
    KO = "ko"                         # Korean

@dataclass
class DetectedLanguage:
    code: LanguageCode
    confidence: float                 # 0.0-1.0
    script: str                       # "Latin", "Han", "Hiragana", etc.
    region: Optional[str]             # Optional region (US, BR, etc.)

@dataclass
class LanguageDetectionResult:
    primary_language: DetectedLanguage
    secondary_languages: List[DetectedLanguage]  # For code-switching
    code_switching_detected: bool
    reliability: float                # Overall detection reliability 0.0-1.0

class LanguageDetector:
    """Detects language(s) in user message"""

    # Language code to native name mapping
    LANGUAGE_NAMES = {
        LanguageCode.EN: "English",
        LanguageCode.ES: "Spanish",
        LanguageCode.FR: "French",
        LanguageCode.DE: "German",
        LanguageCode.IT: "Italian",
        LanguageCode.PT: "Portuguese",
        LanguageCode.ZH: "Mandarin Chinese",
        LanguageCode.JA: "Japanese",
        LanguageCode.KO: "Korean",
    }

    def __init__(self):
        """Initialize language detector (uses fastText or similar)"""
        # Using fasttext model for efficient language ID
        # Model: fasttext.util.download_model('en', if_exists='ignore')
        self.model = None  # Load pre-trained model

    async def detect_language(self, message: str) -> LanguageDetectionResult:
        """
        Detect language(s) in message

        Args:
            message: User utterance

        Returns:
            LanguageDetectionResult with detected languages and confidence
        """
        # Clean message
        message = message.strip()

        # Detect primary language (first 512 chars, fasttext limit)
        primary_text = message[:512]
        predictions = self.model.predict(primary_text, k=3)

        # Extract language codes & confidence
        # fasttext returns format: ('__label__en', '__label__es', ...)
        languages = []
        for i, (label, conf) in enumerate(zip(predictions[0], predictions[1])):
            lang_code_str = label.replace('__label__', '')

            # Skip if not in our supported languages
            if not any(lc.value == lang_code_str for lc in LanguageCode):
                continue

            lang_code = LanguageCode(lang_code_str)

            # Normalize confidence from fasttext [0, 1] range
            confidence = max(0.0, min(1.0, conf))

            languages.append(DetectedLanguage(
                code=lang_code,
                confidence=confidence,
                script=self._get_script(lang_code),
                region=self._infer_region(lang_code, message)
            ))

        # Check for code-switching
        code_switching = len(languages) > 1 and languages[1].confidence > 0.15

        # Compute overall reliability
        if languages:
            # High confidence if primary lang very likely
            reliability = languages[0].confidence
        else:
            reliability = 0.0

        # Determine primary & secondary
        primary = languages[0] if languages else DetectedLanguage(
            code=LanguageCode.EN,
            confidence=0.5,
            script="Latin",
            region=None
        )
        secondary = languages[1:] if len(languages) > 1 else []

        return LanguageDetectionResult(
            primary_language=primary,
            secondary_languages=secondary,
            code_switching_detected=code_switching,
            reliability=reliability
        )

    def _get_script(self, lang_code: LanguageCode) -> str:
        """Get script/writing system for language"""
        scripts = {
            LanguageCode.EN: "Latin",
            LanguageCode.ES: "Latin",
            LanguageCode.FR: "Latin",
            LanguageCode.DE: "Latin",
            LanguageCode.IT: "Latin",
            LanguageCode.PT: "Latin",
            LanguageCode.ZH: "Han",
            LanguageCode.JA: "Hiragana/Kanji",
            LanguageCode.KO: "Hangul",
        }
        return scripts.get(lang_code, "Unknown")

    def _infer_region(self, lang_code: LanguageCode, message: str) -> Optional[str]:
        """Infer region variant (US vs UK English, etc.)"""
        if lang_code == LanguageCode.EN:
            # Heuristic: check for regional vocabulary/spelling
            if any(word in message.lower() for word in ["colour", "centre", "honour"]):
                return "GB"
            elif any(word in message.lower() for word in ["realize", "center", "honor"]):
                return "US"

        if lang_code == LanguageCode.PT:
            # Heuristic: check for Brazilian vs Portugal Portuguese
            if any(word in message.lower() for word in ["você", "pra", "tá"]):
                return "BR"
            elif any(word in message.lower() for word in ["vós", "para", "está"]):
                return "PT"

        return None

    async def batch_detect(self, messages: List[str]) -> List[LanguageDetectionResult]:
        """Batch detection (efficient)"""
        return [await self.detect_language(msg) for msg in messages]
```

**Detection Confidence Thresholds:**

```python
class LanguageConfidencePolicy:
    """Policy for handling detected languages based on confidence"""

    # Confidence thresholds for actions
    HIGH_CONFIDENCE_THRESHOLD = 0.80      # Auto-switch to detected language
    MEDIUM_CONFIDENCE_THRESHOLD = 0.50    # Ask for confirmation
    LOW_CONFIDENCE_THRESHOLD = 0.15       # Fall back to preferred language

    @staticmethod
    async def handle_detection(
        detection_result: LanguageDetectionResult,
        user_preferred_language: LanguageCode,
        code_switching_enabled: bool
    ) -> Tuple[LanguageCode, str]:  # (language_to_use, action_message)
        """
        Determine language to use based on detection result

        Returns:
            (language_code, action_message)
        """
        primary_lang = detection_result.primary_language

        # Rule 1: If primary confidence very high, auto-switch
        if primary_lang.confidence >= HIGH_CONFIDENCE_THRESHOLD:
            return (primary_lang.code, None)  # No confirmation needed

        # Rule 2: Code-switching detected
        if code_switching_enabled and detection_result.code_switching_detected:
            secondary = detection_result.secondary_languages[0] if detection_result.secondary_languages else None
            if secondary:
                return (primary_lang.code, f"I noticed you mixed {primary_lang.code.value} and {secondary.code.value}. I'll respond in both!")

        # Rule 3: Medium confidence, ask for confirmation
        if primary_lang.confidence >= MEDIUM_CONFIDENCE_THRESHOLD:
            confirmation_msg = f"I detected {primary_lang.code.value.upper()}. Is that correct?"
            return (primary_lang.code, confirmation_msg)

        # Rule 4: Low confidence, fall back to preferred language
        return (user_preferred_language, None)
```

---

### Component 2: Code-Switching Handler

**Responsibility:** Handle code-switching (language mixing) in conversations

**Input:** Detected languages, user message, code-switching enabled
**Output:** Language configuration for response generation

**Code-Switching Algorithm:**

```python
from enum import Enum
from typing import Optional

class CodeSwitchingStyle(enum.Enum):
    """How agent should respond to code-switched input"""
    MIRROR = "mirror"                 # Agent mirrors user's code-switching
    UNIFIED = "unified"               # Agent normalizes to single language
    WEIGHTED = "weighted"             # Agent favors primary language (80/20 split)

@dataclass
class CodeSwitchingConfig:
    enabled: bool                     # Feature toggle
    style: CodeSwitchingStyle         # How to respond
    primary_language: LanguageCode    # Primary for weighted mode
    secondary_language: Optional[LanguageCode]  # Secondary for mixing
    confidence_threshold: float       # Min confidence to detect code-switching

class CodeSwitchingHandler:
    """Handles code-switched conversations"""

    def __init__(self, config: CodeSwitchingConfig):
        self.config = config

    async def should_respond_in_mixed_language(
        self,
        detection_result: LanguageDetectionResult
    ) -> bool:
        """
        Determine if agent should respond in mixed language

        Args:
            detection_result: Detected languages in user message

        Returns:
            True if agent should code-switch in response
        """
        if not self.config.enabled:
            return False

        if not detection_result.code_switching_detected:
            return False

        # If primary confidence is too low, don't mirror (ambiguous)
        if detection_result.primary_language.confidence < self.config.confidence_threshold:
            return False

        return True

    def get_response_generation_prompt(
        self,
        base_prompt: str,
        detection_result: LanguageDetectionResult,
        user_message: str
    ) -> str:
        """
        Generate prompt instructions for response generation

        Args:
            base_prompt: Standard system prompt
            detection_result: Detected languages
            user_message: User utterance

        Returns:
            Modified prompt with language instructions
        """
        primary = detection_result.primary_language
        secondary = (detection_result.secondary_languages[0]
                    if detection_result.secondary_languages else None)

        if not self.should_respond_in_mixed_language(detection_result):
            # Single language mode
            return f"{base_prompt}\n\nRespond in {primary.code.value}."

        # Code-switching mode
        if self.config.style == CodeSwitchingStyle.MIRROR:
            # Mirror user's pattern
            # Analyze user message to determine code-switch ratio
            user_lang_ratio = self._estimate_language_ratio(user_message, primary.code, secondary.code)

            prompt = f"""
{base_prompt}

The user is speaking a mix of {primary.code.value} and {secondary.code.value}.
You should respond using the same mix, mirroring their code-switching pattern.

Approximate ratios: {primary.code.value} {user_lang_ratio:.0%}, {secondary.code.value} {(1-user_lang_ratio):.0%}

Example structure:
- Acknowledge in mixed language
- Answer questions code-switched
- Close in primary language

Be natural and conversational—don't force code-switching unnaturally.
"""
            return prompt

        elif self.config.style == CodeSwitchingStyle.WEIGHTED:
            # 80% primary, 20% secondary
            return f"""
{base_prompt}

The user mixed {primary.code.value} and {secondary.code.value}.
Respond primarily in {primary.code.value} (~80%), with occasional phrases in {secondary.code.value} (~20%).

This maintains clarity while acknowledging their linguistic background.
"""

        else:  # UNIFIED
            return f"{base_prompt}\n\nRespond in {primary.code.value} (user mixed languages, but normalize to primary)."

    def _estimate_language_ratio(
        self,
        message: str,
        lang1: LanguageCode,
        lang2: LanguageCode
    ) -> float:
        """
        Estimate ratio of lang1 vs lang2 in message

        Returns: Ratio as float [0, 1] for lang1
        """
        # Simplified heuristic: count character scripts
        # Better approach would use word-level language tagging

        # Map language to script/unicode ranges
        script_ranges = {
            LanguageCode.EN: (0x0000, 0x007F),  # ASCII
            LanguageCode.ES: (0x0000, 0x00FF),  # Latin-1
            LanguageCode.ZH: (0x4E00, 0x9FFF),  # CJK
            # ... more
        }

        # Count characters in each language's script
        # (Very simplified; real implementation would use language tagging)

        lang1_count = sum(1 for c in message if ord(c) < 128)  # Rough approximation
        lang2_count = len(message) - lang1_count

        total = lang1_count + lang2_count
        if total == 0:
            return 0.5

        return lang1_count / total

# Configuration Example
example_config = CodeSwitchingConfig(
    enabled=True,
    style=CodeSwitchingStyle.MIRROR,
    primary_language=LanguageCode.ES,
    secondary_language=LanguageCode.EN,
    confidence_threshold=0.75
)

# Usage
handler = CodeSwitchingHandler(example_config)
should_mix = await handler.should_respond_in_mixed_language(detection_result)
prompt = handler.get_response_generation_prompt(base_prompt, detection_result, user_message)
```

---

### Component 3: Language Preference Management

**Responsibility:** Store & manage per-user language preferences

**Storage:** SessionState.persona (ADR-0017d)

**Extended Persona Schema:**

```python
from dataclasses import dataclass, field
from typing import Dict, Optional
from enum import Enum

class LanguagePreferenceSource(enum.Enum):
    USER_EXPLICIT = "explicit"        # User set preference
    DETECTED = "detected"             # Inferred from language detection
    FAMILY_DEFAULT = "family_default" # Inherited from family settings
    SYSTEM_DEFAULT = "system_default" # en-US (system default)

@dataclass
class LanguagePreference:
    code: str                         # "en-US", "es-ES", "pt-BR", etc.
    source: LanguagePreferenceSource
    last_updated: datetime
    confidence: float                 # 0.0-1.0 (how confident is this preference?)

@dataclass
class LanguageSettings:
    preferred_language: LanguagePreference
    secondary_languages: List[LanguagePreference] = field(default_factory=list)
    code_switching_enabled: bool = False
    detection_confidence_threshold: float = 0.80

    # Detection behavior
    auto_language_switch: bool = True  # Auto-switch if detected lang != preferred
    require_confirmation: bool = False  # Ask for confirmation on switch

    # Privacy
    translation_via_api: bool = False  # Allow external translation APIs
    share_language_data: bool = False  # Allow analysis of language mixing

@dataclass
class ExtendedPersona:
    """Extended persona with language settings"""
    user_id: str

    # Style preferences (existing)
    formality: float
    humor_preference: str

    # NEW: Language preferences
    language_settings: LanguageSettings

    # Timestamp
    last_updated: datetime
```

**K0 Integration (SessionState.persona):**

```python
class PersonaManager:
    """Manages persona including language preferences"""

    def __init__(self, k0_client):
        self.k0 = k0_client

    async def get_language_preference(self, user_id: str) -> LanguagePreference:
        """Fetch user's preferred language from K0 SessionState"""
        persona = await self.k0.query_personalization(
            user_id=user_id,
            fields=["language_settings"]
        )
        return persona.language_settings.preferred_language

    async def update_language_preference(
        self,
        user_id: str,
        new_language: str,
        source: LanguagePreferenceSource = LanguagePreferenceSource.USER_EXPLICIT
    ):
        """Update user's language preference"""
        preference = LanguagePreference(
            code=new_language,
            source=source,
            last_updated=datetime.utcnow(),
            confidence=1.0 if source == LanguagePreferenceSource.USER_EXPLICIT else 0.7
        )

        # Write via K0 Command API (P14 SelfModelUpdate or P02 MemoryWrite)
        await self.k0.command_update_personalization(
            user_id=user_id,
            update_type="language_preference",
            data=asdict(preference)
        )

    async def enable_code_switching(self, user_id: str, enabled: bool):
        """Enable/disable code-switching for user"""
        # Update via K0
        await self.k0.command_update_personalization(
            user_id=user_id,
            update_type="code_switching",
            data={"enabled": enabled}
        )
```

---

### Component 4: Language-Aware Intent Classification

**Responsibility:** Classify intents in multiple languages

**Challenge:** Intent classifier (ADR-0021) trained primarily on English

**Solution Approach:**

```python
class MultilingualIntentClassifier:
    """Intent classification supporting multiple languages"""

    def __init__(self, model_hub):
        self.model_hub = model_hub

        # Load multilingual BERT for encoding (supports 100+ languages)
        self.multilingual_encoder = model_hub.load(
            "bert_multilingual_base_cased",
            cache_dir="/models"
        )

        # Intent classification heads per language
        self.intent_heads = {}  # language_code -> classifier
        for lang in SUPPORTED_LANGUAGES:
            self.intent_heads[lang] = model_hub.load(
                f"intent_classifier_{lang}",
                cache_dir="/models"
            )

    async def classify_intent(
        self,
        message: str,
        language_code: LanguageCode
    ) -> IntentClassificationResult:
        """
        Classify intent in specified language

        Args:
            message: User message
            language_code: Language of message

        Returns:
            Intent classification with confidence
        """
        # Encode using multilingual BERT
        encoding = self.multilingual_encoder.encode(
            message,
            convert_to_tensor=True
        )

        # Classify using language-specific head
        head = self.intent_heads.get(language_code.value)
        if not head:
            # Fallback to English if language not supported
            head = self.intent_heads["en"]
            logger.warning(f"No classifier for {language_code.value}, falling back to English")

        # Get predictions
        predictions = head.predict(encoding)

        # Format result
        return IntentClassificationResult(
            primary_intent=predictions.top_intent,
            confidence=predictions.confidence,
            alternatives=predictions.alternatives
        )

    async def handle_code_switched_message(
        self,
        message: str,
        detection_result: LanguageDetectionResult
    ) -> IntentClassificationResult:
        """
        Handle code-switched message (multiple languages)

        Approach: Segment message by language, classify each, merge results
        """
        primary_lang = detection_result.primary_language

        # For now, classify using primary language
        # (Segment-level classification is future enhancement)
        return await self.classify_intent(message, primary_lang.code)
```

**Model Requirements:**
- ✅ Multilingual BERT (bert-base-multilingual-uncased) for encoding
- ✅ Language-specific intent classifiers (fine-tuned per language)
- ✅ Each classifier trained on 2K-5K labeled examples per language
- ✅ Maintain performance: >85% accuracy per language

---

## Consequences

### Positive Consequences

✅ **Expanded Market**
- Support multi-generational families (parents speak Spanish, kids speak English)
- ~20% of US households speak language other than English at home (Census data)

✅ **Natural Conversations**
- Support code-switching (linguistic behavior of bilingual speakers)
- No forced language normalization ("I understand you're mixing languages, but please stick to English")

✅ **Better UX**
- Automatic language detection reduces friction (no manual switching)
- Respects family members' linguistic backgrounds

✅ **Competitive Parity**
- Comparable to Google Home (100+ languages), Alexa (30+ languages)
- Differentiation: code-switching support

✅ **Privacy by Design**
- No external translation APIs (K0-local processing)
- Language preference stored in K0 (user-controlled, portable)

### Negative Consequences

❌ **Implementation Complexity**
- Requires multilingual models (BERT, intent classifiers per language)
- ~50MB model size per language (manageable)
- Integration with existing intent classifier (ADR-0021)

❌ **Training Data Requirements**
- Need labeled examples for each language (2K-5K turns)
- Crowdsourced translation/annotation required
- Estimated cost: $15K-30K per language

❌ **Latency Impact**
- Language detection adds ~50-100ms (fastText model inference)
- Multilingual encoding adds ~20ms
- Total per-turn impact: ~70-120ms (acceptable, within budget ADR-0024)

❌ **Code-Switching Complexity**
- Response generation more complex (must maintain language balance)
- Quality harder to measure (no standard metrics for code-switched responses)
- User perception varies (some prefer normalization, others prefer mirroring)

❌ **Edge Cases**
- Transliteration (using Latin characters for non-Latin languages: "romaji" for Japanese)
- Borrowed words (English words used in Spanish: "parquear" = to park)
- Script mixing (Latin + Chinese characters in message)

---

## Implementation

### Phase 1: Foundation (Weeks 1-2)

**Goal:** Language detection + single-language support

**Tasks:**
1. ✅ Integrate fastText language detector
2. ✅ Extend PersonaManager with language settings
3. ✅ Deploy language detection to K1 (non-blocking, logging only)
4. ✅ Update SessionState.persona schema (K0 side)
5. ✅ Implement language confidence policy
6. ✅ Add Prometheus metrics (language_detected_total, etc.)

**Deliverable:** Language detection live, system detects language of each user message

**Risks:**
- fastText accuracy on code-switched text (mitigated: test on real data)
- K0 schema migration (mitigated: versioned, backward-compatible)

---

### Phase 2: Language Switching (Weeks 3-4)

**Goal:** Automatic language switching based on detection

**Tasks:**
1. ✅ Implement LanguageConfidencePolicy (auto-switch, confirmation)
2. ✅ Update intent classifier (multilingual BERT integration)
3. ✅ Deploy language-specific intent heads
4. ✅ Implement language-aware prompt generation
5. ✅ Update TTS to select language-appropriate voice
6. ✅ A/B test: auto-switch vs manual (7-14 days)

**Deliverable:** System automatically switches language based on user input

**Risks:**
- Intent classifier accuracy in non-English languages (mitigate: start with high-confidence threshold)
- TTS voice quality in non-English (mitigate: use professional TTS services)

---

### Phase 3: Code-Switching Support (Weeks 5-6)

**Goal:** Enable code-switching (opt-in, gradual rollout)

**Tasks:**
1. ✅ Implement CodeSwitchingHandler (detect mixed language)
2. ✅ Implement response generation prompt modification
3. ✅ Train code-switching policy (mirror vs weighted style)
4. ✅ Deploy code-switching as feature flag (0% → 5% → 25% → 100%)
5. ✅ Collect user feedback (code-switching quality survey)
6. ✅ Monitor rejection rate (users disabling feature)

**Deliverable:** Agent can respond in code-switched language if user does

**Risks:**
- Response quality (more variables to control)
- User confusion (some users may not expect code-switching response)
- Mitigation: feature flag allows instant rollback

---

### Phase 4: Family Language Preferences (Weeks 7-8)

**Goal:** Family-level language settings (each member different language)

**Tasks:**
1. ✅ Extend FamilySession model with language routing
2. ✅ Implement language detection per family member
3. ✅ Update intent classification (route by detected language)
4. ✅ Update response generation (personalize by member)
5. ✅ Test with real multilingual families
6. ✅ Deploy gradual rollout (feature flag)

**Deliverable:** Multi-member families can chat in different languages simultaneously

**Risks:**
- Session state complexity (tracking language per member)
- Mitigation: extend SessionState.participants with language_override

---

## Metrics & Observability

### Prometheus Metrics

```python
from prometheus_client import Counter, Histogram, Gauge

# Language Detection
language_detected_total = Counter(
    'language_detected_total',
    'Messages with detected language',
    labelnames=['detected_language', 'confidence_level']
)

language_detection_latency_ms = Histogram(
    'language_detection_latency_ms',
    'Language detection latency',
    buckets=[10, 25, 50, 100, 250]
)

# Language Switching
language_auto_switch_total = Counter(
    'language_auto_switch_total',
    'Auto-switch events',
    labelnames=['from_language', 'to_language']
)

language_switch_confirmed = Counter(
    'language_switch_confirmed_total',
    'Confirmed language switches',
    labelnames=['language']
)

language_switch_rejected = Counter(
    'language_switch_rejected_total',
    'Rejected language switches',
    labelnames=['language']
)

# Code-Switching
code_switching_detected_total = Counter(
    'code_switching_detected_total',
    'Code-switching patterns detected',
    labelnames=['language_pair']
)

code_switching_response_total = Counter(
    'code_switching_response_total',
    'Responses generated in mixed language',
    labelnames=['style', 'language_pair']
)

# Multi-Language Intent Classification
intent_classification_by_language = Counter(
    'intent_classification_by_language_total',
    'Intent classifications',
    labelnames=['language', 'intent']
)

intent_accuracy_by_language = Gauge(
    'intent_accuracy_by_language',
    'Intent classification accuracy per language',
    labelnames=['language']
)

# Family-Level Language Usage
family_languages_in_use = Gauge(
    'family_languages_in_use',
    'Number of distinct languages used per family',
    labelnames=['family_id']
)

# User Language Preference
user_language_preference_total = Counter(
    'user_language_preference_total',
    'Language preferences',
    labelnames=['language', 'source']
)
```

### Grafana Dashboards

**Dashboard 1: Language Detection**
- Language distribution (pie chart: % English, Spanish, etc.)
- Detection confidence (histogram)
- Code-switching frequency (trend)
- Language-specific latency

**Dashboard 2: Language Switching**
- Auto-switch success rate (% confirmed vs rejected)
- Manual overrides (user forces different language)
- Language transitions (sankey: en→es, es→en, etc.)

**Dashboard 3: Intent Accuracy by Language**
- Accuracy per language (grouped bar chart)
- Comparison: English vs non-English
- Regression detection (alerts if accuracy drops >5%)

---

## Configuration

**Production Configuration (YAML):**

```yaml
# k1/config/multilingual.yml
multilingual:
  # Language Support
  languages:
    enabled: true
    supported:
      - en                          # English
      - es                          # Spanish
      - fr                          # French
      - de                          # German
      - it                          # Italian
      - pt                          # Portuguese
      - zh                          # Mandarin
      - ja                          # Japanese
      - ko                          # Korean

  # Language Detection
  detection:
    enabled: true
    model: "fasttext"
    model_path: "/models/fasttext/lid.176.ftz"

    # Confidence thresholds
    high_confidence_threshold: 0.80    # Auto-switch
    medium_confidence_threshold: 0.50  # Confirm
    low_confidence_threshold: 0.15     # Fallback

    # Latency budget
    max_latency_ms: 100

  # Code-Switching
  code_switching:
    enabled: false                 # Feature flag (gradual rollout)
    style: "mirror"                # mirror | unified | weighted
    confidence_threshold: 0.75

    # Gradual rollout
    rollout_percentage: 0          # Start at 0%, increase over time

  # Multilingual Intent Classification
  intent_classification:
    multilingual_encoder: "bert_multilingual_base"
    language_specific_heads: true

    # Accuracy targets by language
    accuracy_targets:
      en: 0.92
      es: 0.88
      fr: 0.88
      de: 0.85
      it: 0.85
      pt: 0.83
      zh: 0.80
      ja: 0.78
      ko: 0.78

  # TTS Voice Selection
  tts:
    language_specific_voices: true
    prefer_native_speaker: true

  # Privacy & Compliance
  privacy:
    external_translation_api: false  # No external APIs
    store_language_data: true        # For improvement
    retention_days: 90               # GDPR compliance

  # Feature Flags
  feature_flags:
    multilingual_enabled: true
    code_switching_enabled: false    # Start disabled
    auto_language_switch: true
    require_confirmation_on_switch: false
```

---

## Security & Privacy

### Privacy Considerations

**Language Preference = AMBER Band (PII)**
- User's language choice reveals linguistic/cultural background
- Code-switching patterns reveal bilingual status/family composition

**Safeguards:**
1. ✅ K0 stores in SessionState.persona (user-controlled)
2. ✅ No external language detection APIs (privacy-first)
3. ✅ Language data subject to GDPR 90-day retention
4. ✅ User can opt-out of language detection (manual language selection)

### Security

**Integrity:**
- ✅ Language preference stored immutably (append-only history)
- ✅ Changes logged (audit trail in K0 WAL)

**Availability:**
- ✅ Graceful degradation if language detection fails (fallback to preferred_language)
- ✅ Detection service isolated (can fail without blocking conversation)

---

## Research Foundation

**Multilingual NLP:**
- Conneau & Lample (2019), "Cross-lingual Language Model Pretraining", EMNLP
- Devlin et al. (2018), "BERT: Pre-training of Deep Bidirectional Transformers", NAACL

**Code-Switching:**
- Luo et al. (2020), "Are Multilingual Models Effective in Code-Switching?", EMNLP
- Solorio et al. (2014), "Overview of the First Workshop on Computational Approaches to Code Switching"

**Language Detection:**
- Joulin et al. (2017), "Bag of Tricks for Efficient Text Classification", EACL
- fastText paper: Grave et al. (2018), "Learning Word Vectors for 157 Languages"

---

## Related ADRs

**Direct Dependencies:**
- **ADR-0017d:** Persona section (stores `language_settings`)
- **ADR-0021:** Intent Classification (extends to multilingual)
- **ADR-0056d:** TTS Synthesis (language-aware voice selection)
- **ADR-0005e:** Personality system (linguistic preferences)

**Privacy & Compliance:**
- **ADR-0032-0039:** Privacy Bands (language preference = AMBER)
- **ADR-0010:** K0 PII/ABAC (enforces privacy on language data)

**Integration Points:**
- **ADR-0017:** SessionState (extends persona)
- **ADR-0029:** Metrics (language detection latency, accuracy)
- **ADR-0070:** Observability (quality metrics by language)

**Related Future ADRs:**
- ADR-0074 (planned): Dialect Adaptation (regional variations)
- ADR-0075 (planned): Transliteration Support (non-Latin scripts)
- ADR-0076 (planned): Accented Text Processing

---

## Decision Log

| Date | Decision | Rationale |
|------|----------|-----------|
| 2025-10-16 | No external translation | Privacy violation, external APIs not allowed in K0 |
| 2025-10-16 | Code-switching support | Natural linguistic behavior, competitive requirement |
| 2025-10-16 | fastText for detection | Fast (50-100ms), accurate (98%+), low resource usage |
| 2025-10-16 | Feature flag for code-switching | Gradual rollout, user acceptance testing required |
| 2025-10-16 | High confidence threshold 0.8 | Balance automation vs accuracy, aligns with ADR-0024 targets |

---

## Glossary

| Term | Definition |
|------|-----------|
| **Code-Switching** | Alternating between two languages within same utterance |
| **Language Detection** | Identifying which language(s) are in a given message |
| **Confidence Threshold** | Minimum probability to act on a detected language |
| **Multilingual Model** | ML model supporting 50+ languages (mBERT, XLM-R) |
| **Language-Specific Head** | Task-specific classifier trained for one language |
| **Transcoding** | Converting text between different scripts (Latin ↔ Cyrillic) |
| **Transliteration** | Converting characters from one script to another (Hiragana ↔ Romaji) |

---

## Appendix A: Supported Language Details

| Language | Code | Native | Scripts | Sample Size | Model | Accuracy |
|----------|------|--------|---------|-------------|-------|----------|
| English | en | English | Latin | 50K | BERT | 92% |
| Spanish | es | Español | Latin | 30K | BERT | 88% |
| French | fr | Français | Latin | 25K | BERT | 88% |
| German | de | Deutsch | Latin | 20K | BERT | 85% |
| Italian | it | Italiano | Latin | 15K | BERT | 85% |
| Portuguese | pt | Português | Latin | 15K | BERT | 83% |
| Mandarin | zh | 中文 | Han | 20K | BERT-ZH | 80% |
| Japanese | ja | 日本語 | Hiragana/Kanji | 15K | BERT-JP | 78% |
| Korean | ko | 한국어 | Hangul | 10K | BERT-KO | 78% |

---

## Appendix B: Code-Switching Examples

**Example 1: Spanish-English Code-Switching**
- User: "¿Cómo está el weather today? I need to plan my day."
- Agent: "El weather today es sunny, 72°F. Perfect para hacer cosas afuera!"

**Example 2: Mandarin-English Code-Switching**
- User: "我 want to book a flight to 北京 next week"
- Agent: "我可以帮你 book a flight to Beijing. When do you want to leave?"

**Example 3: Multi-Language Family**
- Child (English): "What's for dinner?"
- Parent (Spanish): "¿Qué vamos a comer?"
- Agent (adaptive): "For dinner, we have 鸡肉 chicken or 牛肉 beef. What do you prefer?"

---

**End of ADR-0071: Multilingual & Code-Switching**