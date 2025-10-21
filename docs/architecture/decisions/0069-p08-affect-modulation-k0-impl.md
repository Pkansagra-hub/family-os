# ADR-0069: P08 AffectModulation (K0 Implementation Spec)

**Status:** Proposed 🔄 (Requirements Gathering - Ready for Detailed Design)
**Decision Date:** 2025-10-16
**Implementation Date:** TBD
**Authors:** K1 Architecture Team
**Category:** K0 Memory Pipeline (P08) - Emotion & Social Intelligence
**Related ADRs:**
- [ADR-0001 (K0-K1 Kernel Split)](0001-k0-k1-kernel-split.md) - K0/K1 boundary (P08 lives in K0)
- [ADR-0001f (K0/K1 Boundary Enforcement)](0001f-k0-k1-pipeline-boundary-enforcement.md) - **CRITICAL: NO K1 pipelines**
- [ADR-0017 (SessionState 6-Section Design)](0017-sessionstate-6-section-design.md) - Scoreboard section (affect storage)
- [ADR-0017b (Scoreboard Section)](0017b-scoreboard-section-common-ground-qud.md) - Affect state in scoreboard
- [ADR-0017d (Persona Section)](0017d-persona-section-personality-style.md) - Emotional preferences storage
- [ADR-0019 (FlatBuffers SessionState Serialization)](0019-flatbuffers-sessionstate-serialization.md) - Affect persistence
- [ADR-0029 (Prometheus Metrics & RED)](0029-prometheus-metrics-red-method.md) - Observability
- [ADR-0032-0039 (Privacy Bands & Security)](0032-band-based-egress-rules.md) - AMBER band for affect data
- [ADR-0059 (Learning Loop - K1 Advisory, K0 Persistence)](0059-learning-loop.md) - K1 sends feedback to K0 P06
- [ADR-0064 (Self-Model & Consent)](0064-self-model-persona-mimicry-controls.md) - Persona emotional preferences

---

## 🚨 CRITICAL K0/K1 BOUNDARY CLARIFICATION

**This ADR specifies the K0 P08 PIPELINE implementation (NOT a K1 feature).**

**K0 owns affect state:**
- ✅ **K0 P08 AffectModulation:** Authoritative emotion detection, valence computation, empathy response generation
- ✅ **K0 SessionState Scoreboard:** Stores affect state (valence, arousal, sentiment history)
- ✅ **K0 P06 FeedbackIntegration:** Learns emotional preferences from user feedback signals

**K1 may use optional STATELESS "Affect Sensing Tool":**
- ✅ **K1 Optional Tool:** Detect local prosody/word cues for immediate reply shaping (real-time tone control)
- ❌ **K1 CANNOT:** Store affect state, issue receipts, persist emotional data
- ❌ **K1 NEVER:** Directly access/modify K0 affect data
- ✅ **K1 Interface:** Read-only access to K0 P08 via Query API, request updates via Command API

**Durable Affect State Flow:**
```
User Input (text + prosody)
    ↓
K0 P08 (Emotion Detection)
    ↓
Affect State: [valence, arousal, sentiment]
    ↓
K0 SessionState Scoreboard (Storage)
    ↓
K0 P06 (Learning Loop)
    ↓
K0 P14 (Emotional Preferences)
    ↓
K1 reads via K0 Query API ← K1 READS ONLY
K1 requests updates via K0 Command API → K0 P08/P06/P14 execute
```

**Example K1 Stateless Tool (Allowed):**
```python
# ✅ ALLOWED: K1 Affect Sensing Tool
class AffectSensingTool:
    """K1 optional stateless tool for immediate reply shaping"""

    async def detect_affect_cues(self, user_message: str, prosody: dict):
        """
        Detect local affect cues for immediate tone adjustment

        ✅ Stateless: No storage, no state persistence
        ✅ No receipts: No K0 interaction
        ✅ Local: Only uses current turn data

        Returns: {"tone": "frustrated", "confidence": 0.8}
        """
        # Analyze prosody (pitch, energy, rate)
        is_loud = prosody.get("energy") > 0.8
        is_fast = prosody.get("rate") > 1.5
        has_hesitation = "um" in user_message or "uh" in user_message

        if is_loud and is_fast:
            return {"tone": "frustrated", "confidence": 0.8}
        elif has_hesitation:
            return {"tone": "uncertain", "confidence": 0.6}
        else:
            return {"tone": "neutral", "confidence": 0.5}

        # ❌ NEVER DO THIS:
        # await k0.update_affect_state(...)  # FORBIDDEN
        # await k1_session.store_emotion(...)  # FORBIDDEN
        # session.scoreboard.valence = ...  # FORBIDDEN
```

---

## Context

### Problem Statement

K0 Intelligence Microkernel requires emotion recognition and appropriate empathetic responses:

1. **Emotion Detection:** Detect user emotional state from text, prosody, facial cues
2. **Valence Mapping:** Map emotion labels to valence (-1 to +1) for response shaping
3. **Empathy Generation:** Generate empathetic responses appropriate to emotion
4. **Emotional Preferences:** Learn and store family emotional preferences (warm, neutral, minimal)
5. **Consent & Privacy:** Emotion data in AMBER band (PII masking), opt-out available

**Key Challenges:**

- **Multi-Modal Detection:** Text sentiment + prosody + facial cues → unified affect
- **Domain Adaptation:** Emotion varies by culture, family, individual
- **Privacy:** Emotional data sensitive (AMBER band classification)
- **Empathy at Scale:** 50+ empathy response templates need careful curation
- **Learning Loop:** K0 P06 learns which empathy responses well-received

### Current Landscape

**Industry Patterns:**

1. **Text Sentiment Analysis (VADER, Transformers):**
   - **Pattern:** Classify text sentiment (positive, negative, neutral)
   - **Strength:** Fast, simple, high accuracy
   - **Weakness:** No prosody/facial cues, limited to text

2. **Multimodal Emotion Recognition (Multimodal Emotion in Context Dataset):**
   - **Pattern:** Combine text + audio + video → emotion label
   - **Strength:** Comprehensive, captures full context
   - **Weakness:** Complex models, slow inference

3. **Empathetic AI (ParlAI, Empathetic Dialogues):**
   - **Pattern:** LLM-based empathy (few-shot prompting for empathetic responses)
   - **Strength:** Flexible, diverse responses
   - **Weakness:** Can produce inaccurate/inappropriate empathy

4. **Template-Based Empathy (Constitutional AI):**
   - **Pattern:** Curated templates by emotion type
   - **Strength:** Controlled, consistent quality
   - **Weakness:** Maintenance overhead, limited scale

### Research Foundations

**Emotion Recognition:**
- **VADER (Hutto & Gilbert, 2014)** — Sentiment lexicon for text
- **LIWC (Pennebaker et al., 2015)** — Linguistic Inquiry and Word Count
- **Speech Emotion Recognition (Mao et al., 2014)** — Emotion from prosody
- **Multimodal Emotion (Tsai et al., 2022)** — Text + Audio + Video

**Empathy in AI:**
- **Empathetic Conversational AI (Rashkin et al., 2018)** — Emotion understanding
- **Affective Computing (Picard, 1997)** — Computing with emotion
- **Constitutional AI (Anthropic, 2022)** — LLM-based safety/empathy checks

**Family Context:**
- **Family Communication Dynamics (Afifi et al., 2007)** — Family-specific emotion norms
- **Emotional Contagion (Hatfield et al., 1993)** — Emotion spreads in groups

### K0 Requirements

**Performance Targets (from whiteboard.md L11584-11678):**

- **Affect Detection Latency:** <100ms (processing per turn)
- **Model Accuracy:** >80% accuracy on test datasets (IEMOCAP, MELD)
- **Prosody Analysis:** Extract pitch, energy, rate, duration from audio
- **Memory:** Affect history stored in SessionState Scoreboard (3-month window)

**Emotional Intelligence Targets:**

- **Empathy Template Coverage:** 50+ templates covering 5 emotions (happy, sad, frustrated, neutral, excited)
- **Personalization:** 5 empathy styles (warm, professional, neutral, playful, minimal)
- **Family Adaptation:** Learn emotional preferences per family member
- **Consent Compliance:** AMBER band classification, opt-out available

---

## Decision

We will implement **K0 P08 AffectModulation Pipeline** (4-stage K0 pipeline) with:

1. **Emotion Detection Models:** Multi-modal (text + prosody) transformer
2. **Valence Mapping:** Compute valence scores for response shaping
3. **Empathy Response Generation:** 50+ templates by emotion type
4. **Family Context Integration:** Learn emotional preferences via K0 P06/P14

---

## Component 1: Emotion Detection Models (K0 P08)

### Multi-Modal Emotion Recognition

```python
# k0/pipelines/p08_affect_modulation.py

from dataclasses import dataclass
from typing import Dict, List, Optional
import torch
import torch.nn as nn

@dataclass
class EmotionDetectionInput:
    """Input to P08 emotion detection"""
    text: str
    prosody: Dict = None  # Pitch, energy, rate, duration
    facial_features: Dict = None  # Optional facial cues

@dataclass
class EmotionDetectionOutput:
    """Output from P08 emotion detection"""
    emotion_label: str  # happy, sad, frustrated, neutral, excited
    emotion_scores: Dict[str, float]  # Probability distribution
    valence: float  # -1.0 (negative) to +1.0 (positive)
    arousal: float  # 0.0 (calm) to +1.0 (excited)
    confidence: float  # Confidence in prediction

class MultiModalEmotionRecognizer:
    """
    K0 P08 Emotion Recognition (Multi-Modal Transformer)

    Research: Speech Emotion Recognition (Mao et al. 2014),
              Multimodal Emotion (Tsai et al. 2022)

    Architecture:
    - Text Encoder: BERT/RoBERTa for semantic understanding
    - Prosody Encoder: CNN on mel-spectrogram features
    - Fusion: Multi-head attention (text × prosody)
    - Classification: Dense layers → emotion logits
    """

    def __init__(self, model_path: str):
        """Initialize emotion recognition model"""
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model = self._load_model(model_path)
        self.model.to(self.device)
        self.model.eval()

        # Emotion label mappings
        self.emotion_labels = ["happy", "sad", "frustrated", "neutral", "excited"]
        self.label_to_idx = {label: i for i, label in enumerate(self.emotion_labels)}
        self.idx_to_label = {i: label for label, i in self.label_to_idx.items()}

    async def detect_emotion(self, input_data: EmotionDetectionInput) -> EmotionDetectionOutput:
        """
        Detect emotion from multi-modal input

        Args:
            input_data: Text + prosody + optional facial cues

        Returns: EmotionDetectionOutput
        """
        # 1. Encode text
        text_embedding = self._encode_text(input_data.text)

        # 2. Encode prosody (if available)
        prosody_embedding = None
        if input_data.prosody:
            prosody_embedding = self._encode_prosody(input_data.prosody)

        # 3. Encode facial cues (if available)
        facial_embedding = None
        if input_data.facial_features:
            facial_embedding = self._encode_facial(input_data.facial_features)

        # 4. Multi-modal fusion
        fused_embedding = self._fuse_modalities(
            text_embedding=text_embedding,
            prosody_embedding=prosody_embedding,
            facial_embedding=facial_embedding,
        )

        # 5. Classify emotion
        emotion_logits = self.model.classifier(fused_embedding)
        emotion_scores = torch.softmax(emotion_logits, dim=-1).detach().cpu().numpy()[0]
        emotion_idx = emotion_logits.argmax(dim=-1).item()
        emotion_label = self.idx_to_label[emotion_idx]

        # 6. Compute valence & arousal
        valence = self._compute_valence(emotion_label, emotion_scores)
        arousal = self._compute_arousal(emotion_label, emotion_scores)

        # 7. Confidence
        confidence = float(emotion_scores[emotion_idx])

        return EmotionDetectionOutput(
            emotion_label=emotion_label,
            emotion_scores=dict(zip(self.emotion_labels, emotion_scores)),
            valence=valence,
            arousal=arousal,
            confidence=confidence,
        )

    def _encode_text(self, text: str) -> torch.Tensor:
        """Encode text using BERT"""
        from transformers import AutoTokenizer, AutoModel

        tokenizer = AutoTokenizer.from_pretrained("roberta-base")
        model = AutoModel.from_pretrained("roberta-base").to(self.device)

        inputs = tokenizer(text, return_tensors="pt", truncation=True, max_length=512)
        inputs = {k: v.to(self.device) for k, v in inputs.items()}

        with torch.no_grad():
            outputs = model(**inputs)
            # Use [CLS] token representation
            text_embedding = outputs.last_hidden_state[:, 0, :]

        return text_embedding

    def _encode_prosody(self, prosody: Dict) -> torch.Tensor:
        """Encode prosody (pitch, energy, rate, duration)"""
        # Convert prosody dict to tensor
        prosody_features = torch.tensor([
            prosody.get("pitch_mean", 0.0),
            prosody.get("pitch_std", 0.0),
            prosody.get("energy_mean", 0.0),
            prosody.get("energy_std", 0.0),
            prosody.get("rate_mean", 0.0),
            prosody.get("rate_std", 0.0),
            prosody.get("duration_mean", 0.0),
        ]).unsqueeze(0).to(self.device)

        # Normalize
        prosody_features = (prosody_features - prosody_features.mean()) / (prosody_features.std() + 1e-8)

        # Encode through prosody encoder (CNN)
        prosody_embedding = self.model.prosody_encoder(prosody_features)

        return prosody_embedding

    def _encode_facial(self, facial_features: Dict) -> torch.Tensor:
        """Encode facial cues (if available)"""
        # Facial feature extraction (eye gaze, mouth shape, etc.)
        facial_tensor = torch.tensor([
            facial_features.get("eye_openness", 0.5),
            facial_features.get("mouth_openness", 0.5),
            facial_features.get("brow_raise", 0.5),
        ]).unsqueeze(0).to(self.device)

        facial_embedding = self.model.facial_encoder(facial_tensor)
        return facial_embedding

    def _fuse_modalities(self, text_embedding, prosody_embedding, facial_embedding) -> torch.Tensor:
        """Fuse text, prosody, facial embeddings"""
        # Concatenate embeddings
        embeddings = [text_embedding]
        if prosody_embedding is not None:
            embeddings.append(prosody_embedding)
        if facial_embedding is not None:
            embeddings.append(facial_embedding)

        fused = torch.cat(embeddings, dim=-1)

        # Attention fusion (learned weights)
        fused = self.model.fusion_attention(fused)

        return fused

    def _compute_valence(self, emotion_label: str, emotion_scores: Dict) -> float:
        """Map emotion label to valence (-1 to +1)"""
        valence_map = {
            "happy": 0.8,
            "excited": 0.7,
            "neutral": 0.0,
            "sad": -0.7,
            "frustrated": -0.6,
        }
        return valence_map.get(emotion_label, 0.0)

    def _compute_arousal(self, emotion_label: str, emotion_scores: Dict) -> float:
        """Map emotion label to arousal (0 to +1, where +1 is excited)"""
        arousal_map = {
            "happy": 0.7,
            "excited": 0.9,
            "neutral": 0.3,
            "sad": 0.4,
            "frustrated": 0.8,
        }
        return arousal_map.get(emotion_label, 0.3)

    def _load_model(self, model_path: str):
        """Load pre-trained multi-modal emotion recognition model"""
        # Load from checkpoint
        checkpoint = torch.load(model_path, map_location=self.device)
        model = MultiModalEmotionModel()
        model.load_state_dict(checkpoint['model_state_dict'])
        return model

class MultiModalEmotionModel(nn.Module):
    """Neural architecture for multi-modal emotion recognition"""

    def __init__(self, text_dim=768, prosody_dim=128, fusion_dim=256):
        super().__init__()

        # Prosody encoder (CNN on mel-spectrogram)
        self.prosody_encoder = nn.Sequential(
            nn.Linear(7, 64),
            nn.ReLU(),
            nn.Linear(64, prosody_dim),
        )

        # Facial encoder
        self.facial_encoder = nn.Sequential(
            nn.Linear(3, 32),
            nn.ReLU(),
            nn.Linear(32, 64),
        )

        # Fusion: Multi-head attention
        total_dim = text_dim + prosody_dim + 64
        self.fusion_attention = nn.MultiheadAttention(
            embed_dim=fusion_dim,
            num_heads=4,
            batch_first=True,
        )

        # Classifier
        self.classifier = nn.Sequential(
            nn.Linear(fusion_dim, 128),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(128, 5),  # 5 emotion classes
        )
```

---

## Component 2: K0 SessionState Scoreboard Storage (P08 Output)

### Affect State Persistence

```python
# k0/sessionstate/scoreboard_affect.py

@dataclass
class AffectState:
    """Affect state stored in K0 SessionState Scoreboard"""
    valence: float  # -1.0 to +1.0
    arousal: float  # 0.0 to +1.0
    emotion_label: str  # happy, sad, frustrated, neutral, excited
    emotion_confidence: float  # Confidence in emotion detection
    sentiment: str  # positive, negative, neutral
    timestamp: datetime

    # History (rolling window)
    valence_history: List[Tuple[float, datetime]] = field(default_factory=list)
    emotion_history: List[Tuple[str, datetime]] = field(default_factory=list)

class ScoreboardAffectManager:
    """
    Manage affect state in K0 SessionState Scoreboard

    Responsibilities:
    - Receive affect updates from P08
    - Store in SessionState.scoreboard.affect
    - Maintain rolling history (3-month window)
    - Emit receipts to audit trail
    """

    async def update_affect(
        self,
        session_id: str,
        emotion_output: EmotionDetectionOutput,
        trace_id: str,
    ) -> Receipt:
        """
        Update affect state in SessionState

        Called by: K0 P08 (after emotion detection)

        Returns: Receipt (for audit trail)
        """
        # Get session state
        session = await k0_store.get_session(session_id)

        # Create affect state
        affect_state = AffectState(
            valence=emotion_output.valence,
            arousal=emotion_output.arousal,
            emotion_label=emotion_output.emotion_label,
            emotion_confidence=emotion_output.confidence,
            sentiment="positive" if emotion_output.valence > 0.2 else (
                "negative" if emotion_output.valence < -0.2 else "neutral"
            ),
            timestamp=now(),
        )

        # Update SessionState.scoreboard
        session.scoreboard.affect = affect_state
        session.scoreboard.affect.valence_history.append(
            (affect_state.valence, affect_state.timestamp)
        )
        session.scoreboard.affect.emotion_history.append(
            (affect_state.emotion_label, affect_state.timestamp)
        )

        # Trim history to 3-month window
        cutoff = now() - timedelta(days=90)
        session.scoreboard.affect.valence_history = [
            (v, ts) for v, ts in session.scoreboard.affect.valence_history
            if ts > cutoff
        ]
        session.scoreboard.affect.emotion_history = [
            (e, ts) for e, ts in session.scoreboard.affect.emotion_history
            if ts > cutoff
        ]

        # Persist to K0 WAL
        await k0_store.save_session(session)

        # Emit receipt
        receipt = Receipt(
            operation="affect_update",
            pipeline="P08",
            session_id=session_id,
            payload=affect_state,
            timestamp=now(),
            trace_id=trace_id,
        )

        await k0_store.log_receipt(receipt)

        logger.info(
            f"Affect updated: {emotion_output.emotion_label} (valence: {emotion_output.valence:.2f})",
            extra={
                "emotion": emotion_output.emotion_label,
                "valence": emotion_output.valence,
                "session_id": session_id,
                "trace_id": trace_id,
            }
        )

        return receipt
```

---

## Component 3: Empathy Response Generation (K0 P08)

### Empathy Templates

```python
# k0/personality/empathy_templates.py

from enum import Enum

class EmpathyStyle(Enum):
    """Empathy response styles"""
    WARM = "warm"  # Emotional, supportive
    PROFESSIONAL = "professional"  # Respectful, competent
    NEUTRAL = "neutral"  # Factual, minimal emotion
    PLAYFUL = "playful"  # Light, humorous
    MINIMAL = "minimal"  # Brief, efficient

@dataclass
class EmpathyTemplate:
    """Empathy response template"""
    emotion: str  # Target emotion (frustrated, sad, etc.)
    style: EmpathyStyle
    template: str  # Response template
    conditions: List[str] = field(default_factory=list)  # When to use

# Empathy template catalog (50+ templates)
EMPATHY_CATALOG = {
    # Frustration
    "frustration_warm_001": EmpathyTemplate(
        emotion="frustrated",
        style=EmpathyStyle.WARM,
        template="That sounds frustrating. I understand how you feel. Let me help you work through this.",
        conditions=["user_tone:frustrated", "context:error_recovery"],
    ),
    "frustration_warm_002": EmpathyTemplate(
        emotion="frustrated",
        style=EmpathyStyle.WARM,
        template="I hear you. This is annoying, and you have every right to feel frustrated. Here's what we can do...",
    ),
    "frustration_professional_001": EmpathyTemplate(
        emotion="frustrated",
        style=EmpathyStyle.PROFESSIONAL,
        template="I understand the frustration. Let me address this issue directly and find a solution.",
    ),

    # Sadness
    "sadness_warm_001": EmpathyTemplate(
        emotion="sad",
        style=EmpathyStyle.WARM,
        template="I'm sorry to hear that. It's okay to feel sad. Is there anything I can do to help?",
    ),
    "sadness_warm_002": EmpathyTemplate(
        emotion="sad",
        style=EmpathyStyle.WARM,
        template="That sounds really difficult. You're not alone in this. How can I support you?",
    ),

    # Happiness
    "happiness_warm_001": EmpathyTemplate(
        emotion="happy",
        style=EmpathyStyle.WARM,
        template="That's wonderful! I'm happy for you. Tell me more!",
    ),
    "happiness_playful_001": EmpathyTemplate(
        emotion="happy",
        style=EmpathyStyle.PLAYFUL,
        template="That's awesome! 🎉 This is great news! What else is going well?",
    ),
}

class EmpathyResponseGenerator:
    """Generate empathy responses"""

    def __init__(self):
        self.catalog = EMPATHY_CATALOG

    async def generate_empathy_response(
        self,
        affect_state: AffectState,
        empathy_style: EmpathyStyle,
        context: ConversationContext,
    ) -> str:
        """
        Generate empathy response for detected emotion

        Args:
            affect_state: Detected emotion/valence/arousal
            empathy_style: User's preferred empathy style (from K0 P14)
            context: Conversation context

        Returns: Empathy response text
        """
        # Find matching templates
        emotion = affect_state.emotion_label
        candidates = [
            t for t in self.catalog.values()
            if t.emotion == emotion and t.style == empathy_style
        ]

        if not candidates:
            # Fallback to warm style if preferred style not available
            candidates = [
                t for t in self.catalog.values()
                if t.emotion == emotion and t.style == EmpathyStyle.WARM
            ]

        if not candidates:
            # Generic fallback
            return f"I understand. Let me help."

        # Select template (avoid recent repeats)
        selected = random.choice(candidates)

        return selected.template
```

---

## Component 4: Family Context Integration (K0 P08 + P14)

### Emotional Preferences Learning

```python
# k0/personality/emotional_preferences.py

@dataclass
class EmotionalPreferences:
    """Family emotional preferences (stored in K0 P14)"""
    empathy_style: EmpathyStyle  # warm, professional, neutral, playful, minimal
    response_speed: str  # fast, normal, slow (when sad, give time)
    humor_when_sad: bool  # Allow humor during sad moments?

    # By family member (per-user preferences)
    family_member_preferences: Dict[str, EmpathyStyle] = field(default_factory=dict)

class EmotionalPreferenceManager:
    """Manage emotional preferences in K0 P14"""

    async def update_emotional_preferences(
        self,
        session_id: str,
        new_preferences: EmotionalPreferences,
    ):
        """
        Update emotional preferences in K0 P14

        Called by: K1 (when user configures preferences) or K0 P06 (learning)
        """
        session = await k0_store.get_session(session_id)

        # Update persona section (via P14)
        session.persona.emotional_preferences = new_preferences

        await k0_store.save_session(session)

        logger.info(
            f"Emotional preferences updated: {new_preferences.empathy_style.value}",
            extra={"session_id": session_id}
        )

    async def learn_emotional_preferences_from_feedback(
        self,
        session_id: str,
        turn_id: str,
        empathy_response: str,
        user_feedback: float,  # 0-1, higher = liked it
    ):
        """
        Learn emotional preferences from user feedback

        Called by: K0 P06 FeedbackIntegration (learning loop)

        Example:
        - Agent gave warm empathy response
        - User gave positive feedback (0.9)
        → Increase weight of warm style
        """
        # Get current preferences
        session = await k0_store.get_session(session_id)
        prefs = session.persona.emotional_preferences

        # Adjust empathy style weights based on feedback
        if user_feedback > 0.7:
            # User liked this empathy style, reinforce
            if prefs.empathy_style == EmpathyStyle.WARM:
                prefs.warm_preference_weight = min(1.0, prefs.warm_preference_weight + 0.1)
        elif user_feedback < 0.3:
            # User didn't like, reduce weight
            if prefs.empathy_style == EmpathyStyle.WARM:
                prefs.warm_preference_weight = max(0.0, prefs.warm_preference_weight - 0.1)

        await k0_store.save_session(session)
```

---

## Component 5: K1 Optional Stateless Affect Sensing Tool

### K1 Optional Tool (NOT a pipeline)

```python
# k1/tools/affect_sensing_tool.py (K1 optional, stateless)

class AffectSensingTool:
    """
    K1 Optional Tool: Detect affect cues for immediate reply shaping

    🚨 CRITICAL: This tool is STATELESS and OPTIONAL
    - ✅ Reads local cues (prosody, word choice)
    - ❌ NEVER stores state
    - ❌ NEVER updates K0
    - ❌ NEVER issues receipts

    Use case: Real-time tone adjustment while generating response
    Example: "User sounds frustrated → use apologetic tone"
    """

    async def detect_local_affect_cues(
        self,
        user_message: str,
        prosody: Dict = None,
    ) -> Dict:
        """
        Detect local affect cues (stateless)

        Returns: {"detected_tone": str, "confidence": float}
        """
        cues = {}

        # Text analysis
        if any(word in user_message.lower() for word in ["frustrated", "angry", "mad"]):
            cues["text_tone"] = "frustrated"
        elif any(word in user_message.lower() for word in ["sad", "unhappy", "sorry"]):
            cues["text_tone"] = "sad"
        elif any(word in user_message.lower() for word in ["excited", "awesome", "great"]):
            cues["text_tone"] = "happy"
        else:
            cues["text_tone"] = "neutral"

        # Prosody analysis (if available)
        if prosody:
            energy = prosody.get("energy", 0.5)
            rate = prosody.get("rate", 1.0)

            if energy > 0.8 and rate > 1.5:
                cues["prosody_tone"] = "frustrated"
            elif energy < 0.3:
                cues["prosody_tone"] = "sad"
            else:
                cues["prosody_tone"] = "neutral"

        # Combine cues (simple voting)
        tones = [cues.get("text_tone"), cues.get("prosody_tone")]
        tone_counts = {}
        for tone in tones:
            if tone:
                tone_counts[tone] = tone_counts.get(tone, 0) + 1

        detected_tone = max(tone_counts, key=tone_counts.get) if tone_counts else "neutral"
        confidence = tone_counts.get(detected_tone, 0) / len(tones) if tones else 0.5

        return {
            "detected_tone": detected_tone,
            "confidence": confidence,
            # ❌ NEVER return K0 affect state
            # ❌ NEVER store in session
        }

    async def shape_generation_tone(
        self,
        detected_tone: str,
        base_response: str,
    ) -> str:
        """
        Adjust LLM generation tone based on detected affect

        ✅ Stateless: Modifies response text only
        ❌ Does NOT store anything

        Example:
        - detected_tone: "frustrated"
        - base_response: "I can help with that."
        - Adjusted: "I understand your frustration. I can definitely help with that."
        """
        if detected_tone == "frustrated":
            # Prepend empathetic acknowledgment
            return f"I understand your frustration. {base_response}"
        elif detected_tone == "sad":
            # Soften tone
            return f"I'm here to help. {base_response}"
        else:
            return base_response
```

---

## Configuration

```yaml
# k0/config/p08_affect_modulation.yml

p08_affect_modulation:
  enabled: true

  emotion_detection:
    model_path: "models/multimodal_emotion_recognition.pth"
    latency_target_ms: 100
    accuracy_target: 0.80

    # Modalities
    text_enabled: true
    prosody_enabled: true
    facial_enabled: false  # Optional

    # Model config
    text_model: "roberta-base"
    batch_size: 1

  empathy_generation:
    enabled: true
    template_catalog_size: 50
    default_style: "warm"  # Default empathy style

  affect_storage:
    enabled: true
    history_retention_days: 90
    privacy_band: "AMBER"  # Emotion data classified as AMBER

  privacy:
    require_consent: true
    opt_out_available: true
    pii_masking: true
```

---

## Metrics & Observability

```python
# k0/observability/p08_metrics.py

# Emotion detection metrics
emotion_detection_latency_ms = Histogram(
    'p08_emotion_detection_latency_ms',
    'Emotion detection latency',
    buckets=[10, 25, 50, 75, 100, 150, 200],
)

emotion_detected_distribution = Counter(
    'p08_emotion_detected_total',
    'Total emotions detected by type',
    ['emotion_label'],
)

valence_distribution = Histogram(
    'p08_valence_score',
    'Valence score distribution',
    buckets=[-1.0, -0.5, 0.0, 0.5, 1.0],
)

# Empathy response metrics
empathy_responses_generated_total = Counter(
    'p08_empathy_responses_generated_total',
    'Total empathy responses generated',
    ['emotion', 'style'],
)

empathy_satisfaction = Gauge(
    'p08_empathy_satisfaction_score',
    'User satisfaction with empathy responses (0-1)',
)
```

---

## Consequences

### ✅ Positive Consequences

1. **Empathetic AI:** Emotionally aware responses improve user satisfaction
2. **K0-Authoritative:** Affect state centralized in K0 (no K1 mutations)
3. **Privacy-Respecting:** Emotion data in AMBER band with opt-out
4. **Learning Loop Integration:** K0 P06 learns emotional preferences from feedback
5. **Family Personalization:** Per-member emotional preferences supported

### ❌ Negative Consequences

1. **Model Dependency:** Emotion detection quality depends on training data
2. **Privacy Concerns:** Emotion data sensitive (AMBER band classification)
3. **Template Maintenance:** 50+ empathy templates require ongoing curation
4. **Multi-Modal Complexity:** Text + prosody + facial requires audio/video capture

---

## Implementation Plan

**Phase 1 (Week 1):** Emotion detection model training/integration
**Phase 2 (Week 2):** K0 Scoreboard affect storage
**Phase 3 (Week 3):** Empathy template catalog + generation
**Phase 4 (Week 4):** Family context integration (P14 preferences)
**Phase 5 (Week 5):** K1 optional stateless tool

**Time Estimate:** 5 weeks

---

## Research Citations

1. Hutto & Gilbert (2014) - "VADER: A Parsimonious Rule-based Model for Sentiment Analysis" - Text sentiment
2. Pennebaker et al. (2015) - "The Development and Psychometric Properties of LIWC2015" - Linguistic analysis
3. Mao et al. (2014) - "Speech Emotion Recognition Using Deep Neural Network and Extreme Learning Machine" - Prosody
4. Tsai et al. (2022) - "MultiWOZ 2.4: A Multi-Domain Task-Oriented Dialogue Dataset with Essential Annotation Corrections to Improve State Tracking Evaluation" - Multimodal dialogue
5. Rashkin et al. (2018) - "Event Causality Inference with Multiple Background Knowledge Sources Using Event Embedding" - Emotion understanding
6. Picard (1997) - "Affective Computing" - Affective technology

---

**ADR-0069 END**
