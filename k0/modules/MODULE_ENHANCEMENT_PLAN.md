# Module Enhancement Plan: Production-Hardened Intelligence

> **Vision**: Transform rule-based modules into research-backed, production-grade intelligence systems while maintaining API compatibility.
>
> **Principle**: Input/Output contracts remain unchanged. Only internal logic evolves.

---

## Executive Summary

| Module | Current State | Target State | Research Foundation |
|--------|---------------|--------------|---------------------|
| M02 | spaCy NER + template KG | Transformer NER + Neural KG | Honnibal 2020, Bordes 2013 |
| M04 | VADER lexicon | RoBERTa emotions | Demszky 2020, GoEmotions |
| M06 | Static formula | Learned weights + attention | Corbetta 2002, Itti 2000 |
| M07 | Hardcoded dict | Graph neural network | Hamilton 2017, Kipf 2016 |
| M10 | Keyword matching | Zero-shot classification | Yin 2019, BART-MNLI |

---

# Milestone 1: Foundation (Week 1-2)

## Epic 1.1: Model Infrastructure

### Issue 1.1.1: Unified Model Registry
**Priority**: P0 (Blocker)
**Estimate**: 3 days

**Current State**:
- Models loaded ad-hoc in each module
- No GPU memory management
- Cold start on every request

**Target State**:
- Centralized model registry with lazy loading
- Shared GPU memory pool with automatic offloading
- Model warmup during kernel startup

**Implementation**:
```python
# k0/runtime/model_registry.py
class ModelRegistry:
    """
    Centralized model management with:
    - Lazy loading (load on first use)
    - Memory-aware GPU allocation
    - Automatic CPU fallback
    - Model versioning
    """
    _models: Dict[str, Any] = {}
    _gpu_memory_limit: int = 4 * 1024 * 1024 * 1024  # 4GB default

    async def get_model(self, model_id: str) -> Any:
        """Thread-safe model retrieval with automatic loading."""
        pass
```

**Input/Output**: N/A (Infrastructure)

**Acceptance Criteria**:
- [ ] Models loaded once, shared across requests
- [ ] GPU memory stays under configured limit
- [ ] Graceful fallback to CPU when GPU unavailable
- [ ] Model loading time < 5s for largest model

---

### Issue 1.1.2: Feature Flag System for Model Tiers
**Priority**: P0 (Blocker)
**Estimate**: 2 days

**Current State**:
- No way to toggle between rule-based and ML approaches
- All-or-nothing deployment

**Target State**:
- Feature flags for each module's ML tier
- Gradual rollout capability (1% → 10% → 100%)
- Automatic fallback on model failure

**Implementation**:
```python
# k0/config/feature_flags.py
MODULE_TIERS = {
    "M02_semantic_project": {
        "default": "RULE_BASED",
        "options": ["RULE_BASED", "SPACY_LARGE", "TRANSFORMER"],
        "rollout_percentage": 0,  # 0-100
    },
    "M04_affect_analyze": {
        "default": "VADER",
        "options": ["VADER", "ROBERTA_EMOTIONS"],
        "rollout_percentage": 0,
    },
    # ...
}
```

**Input/Output**: N/A (Infrastructure)

**Acceptance Criteria**:
- [ ] Feature flags configurable via environment variables
- [ ] Percentage-based rollout working
- [ ] Automatic fallback on model errors
- [ ] Metrics emitted for A/B comparison

---

## Epic 1.2: Testing Infrastructure

### Issue 1.2.1: Golden Dataset for Module Accuracy
**Priority**: P0 (Blocker)
**Estimate**: 5 days

**Current State**:
- No ground truth dataset
- Cannot measure accuracy improvements

**Target State**:
- 1000+ annotated family memories
- Human-labeled entities, emotions, activities
- Automated accuracy benchmarking

**Dataset Schema**:
```yaml
# tests/fixtures/golden_dataset/schema.yaml
memories:
  - id: "mem_001"
    text: "Had dinner with Sarah and the kids at Olive Garden for Emma's birthday"
    ground_truth:
      entities:
        - {text: "Sarah", type: "PERSON", role: "spouse"}
        - {text: "Emma", type: "PERSON", role: "child"}
        - {text: "Olive Garden", type: "ORG", subtype: "restaurant"}
      emotions:
        primary: "joy"
        secondary: ["love", "gratitude"]
        valence: 0.85
        arousal: 0.6
      activity:
        type: "meal"
        subtype: "dinner"
        is_celebration: true
      social:
        context: "nuclear_family"
        participants: ["spouse", "child", "child"]
```

**Acceptance Criteria**:
- [ ] 1000 memories with full annotations
- [ ] Inter-annotator agreement > 0.8 (Cohen's kappa)
- [ ] Automated benchmark script
- [ ] CI integration for regression testing

---

# Milestone 2: Semantic Intelligence (Week 3-4)

## Epic 2.1: M02 Semantic Project Enhancement

### Issue 2.1.1: Upgrade NER to Transformer Model
**Priority**: P1 (High)
**Estimate**: 5 days
**Dependencies**: Issue 1.1.1

**Current State**:
```python
# Uses spaCy en_core_web_sm (50MB, 85% accuracy)
_nlp = spacy.load("en_core_web_sm")
entities = [(ent.text, ent.label_) for ent in doc.ents]
```

**Problems**:
- Misses informal names ("mom", "kiddo", "hubby")
- No coreference resolution ("she" → "Sarah")
- Poor on family-specific vocabulary

**Target State**:
```python
# Uses fine-tuned RoBERTa NER (125MB, 94% accuracy on family text)
from transformers import pipeline

class TransformerNER:
    """
    Research: Honnibal et al. (2020) - spaCy transformers
    Model: roberta-base fine-tuned on family corpus

    Improvements:
    - Contextual embeddings capture "mom" = PERSON
    - Handles informal names and nicknames
    - Coreference resolution via mention clustering
    """
    def __init__(self):
        self.ner = pipeline("ner", model="familyos/roberta-ner-v1")
        self.coref = pipeline("coreference", model="lingmess/coref-roberta")

    def extract(self, text: str) -> List[Entity]:
        # Step 1: Raw NER
        raw_entities = self.ner(text)

        # Step 2: Coreference resolution
        clusters = self.coref(text)

        # Step 3: Merge mentions to canonical entities
        return self._resolve_coreferences(raw_entities, clusters)
```

**Research Foundation**:
- Honnibal, M., & Montani, I. (2020). spaCy: Industrial-strength NLP.
- Joshi, M., et al. (2020). SpanBERT: Improving Pre-training by Representing and Predicting Spans.
- Lee, K., et al. (2017). End-to-end Neural Coreference Resolution.

**Input Contract** (unchanged):
```python
Input: envelope["body"]["text"] (str)
```

**Output Contract** (unchanged):
```python
Output: {
    "entities_json": "[\"person_sarah\", \"org_olive_garden\"]",
    "embedding_id": "uuid",
    "kg_triples_json": "[[\"actor\", \"had_meal_at\", \"olive_garden\"]]"
}
```

**Acceptance Criteria**:
- [ ] NER accuracy > 92% on golden dataset
- [ ] Coreference resolution accuracy > 85%
- [ ] Latency < 50ms P95 (GPU), < 200ms P95 (CPU)
- [ ] Memory footprint < 500MB

---

### Issue 2.1.2: Neural Knowledge Graph Generation
**Priority**: P1 (High)
**Estimate**: 7 days
**Dependencies**: Issue 2.1.1

**Current State**:
```python
# Template-based KG generation with hardcoded predicates
def _activity_type_to_predicate(activity_type, object_type):
    activity_map = {
        "MEAL": ("had_meal_at", "had_meal_with"),
        "SOCIAL_EVENT": ("attended_event_at", "attended_event_with"),
        # ... hardcoded mappings
    }
```

**Problems**:
- Only 7 activity types supported
- No relationship extraction from text
- Misses implicit relationships ("celebrated" → celebration event)

**Target State**:
```python
class NeuralKGExtractor:
    """
    Research: Bordes et al. (2013) - TransE embeddings
             Yao et al. (2019) - DocRED relation extraction

    Architecture:
    1. Entity pair enumeration from NER output
    2. Relation classification via fine-tuned BERT
    3. Confidence filtering (threshold = 0.7)
    4. KG embedding for consistency scoring
    """
    def __init__(self):
        self.relation_classifier = pipeline(
            "text-classification",
            model="familyos/bert-relation-extraction-v1"
        )
        self.kg_embedder = TransE(embedding_dim=100)

    def extract_triples(
        self,
        text: str,
        entities: List[Entity]
    ) -> List[Triple]:
        triples = []

        # Enumerate all entity pairs
        for e1, e2 in itertools.combinations(entities, 2):
            # Extract context between entities
            context = self._get_context(text, e1, e2)

            # Classify relation
            relation = self.relation_classifier(context)

            if relation.confidence > 0.7:
                triples.append(Triple(e1.id, relation.label, e2.id))

        # Score triples for consistency
        return self._filter_by_kg_consistency(triples)
```

**Research Foundation**:
- Bordes, A., et al. (2013). Translating Embeddings for Modeling Multi-relational Data.
- Yao, Y., et al. (2019). DocRED: A Large-Scale Document-Level Relation Extraction Dataset.
- Zhang, Y., et al. (2017). Position-aware Attention and Supervised Data Improve Slot Filling.

**Acceptance Criteria**:
- [ ] Relation extraction F1 > 0.75 on golden dataset
- [ ] Support 50+ relation types (vs current 14)
- [ ] KG consistency score > 0.9
- [ ] Latency < 100ms P95

---

### Issue 2.1.3: Fix Envelope Field Extraction Bug
**Priority**: P0 (Critical Bug)
**Estimate**: 1 day

**Current State** (BUG):
```python
# semantic_project.py line 298
participants = envelope.get("participants", [])  # WRONG!
place = envelope.get("location_name")  # WRONG!
```

**Problem**:
- Participants are in `envelope["body"]["participants"]`
- Location is in `envelope["body"]["location_name"]`
- KG triples are empty because these are always None

**Fix**:
```python
# Correct extraction
body = envelope.get("body", {})
participants = body.get("participants", [])
place = body.get("location_name") or body.get("place")
```

**Acceptance Criteria**:
- [ ] Entities resolved against participants list
- [ ] KG triples include location relationships
- [ ] E2E test shows non-empty entities_json and kg_triples_json

---

# Milestone 3: Affect Intelligence (Week 5-6)

## Epic 3.1: M04 Affect Analysis Enhancement

### Issue 3.1.1: Upgrade to Transformer-Based Emotion Detection
**Priority**: P1 (High)
**Estimate**: 5 days
**Dependencies**: Issue 1.1.1

**Current State**:
```python
# VADER lexicon-based sentiment (2014 technology)
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
scores = analyzer.polarity_scores(text)
valence = (scores["compound"] + 1.0) / 2.0
```

**Problems**:
- Lexicon-based (7,500 words) - misses context
- No multi-label emotion detection
- Fails on nuanced expressions ("bittersweet", "exhausted but grateful")
- Claims 73% accuracy but real-world is ~60%

**Target State**:
```python
class TransformerAffect:
    """
    Research: Demszky et al. (2020) - GoEmotions
             Barbieri et al. (2020) - TweetEval

    Model: RoBERTa fine-tuned on GoEmotions (27 emotions + neutral)

    Improvements:
    - Contextual understanding of nuanced emotions
    - Multi-label classification (joy + gratitude simultaneously)
    - Valence/arousal derived from emotion mixture
    - Confidence calibration via temperature scaling
    """
    def __init__(self):
        self.classifier = pipeline(
            "text-classification",
            model="SamLowe/roberta-base-go_emotions",
            top_k=5  # Return top 5 emotions
        )
        self.emotion_to_va = self._load_emotion_va_mapping()

    def analyze(self, text: str) -> AffectAnnotation:
        # Step 1: Multi-label emotion classification
        emotions = self.classifier(text)

        # Step 2: Map to valence/arousal via Russell's circumplex
        valence, arousal = self._emotions_to_va(emotions)

        # Step 3: Derive affect band (GREEN/AMBER/RED)
        band = self._classify_band(valence, arousal, emotions)

        return AffectAnnotation(
            valence=valence,
            arousal=arousal,
            dominant_emotions=tuple(e["label"] for e in emotions[:3]),
            affect_band=band,
            confidence=self._calibrated_confidence(emotions),
        )

    def _emotions_to_va(self, emotions: List[dict]) -> Tuple[float, float]:
        """
        Russell's Circumplex Model (1980):
        - Each emotion maps to (valence, arousal) coordinates
        - Weighted average based on emotion probabilities
        """
        v_sum, a_sum, weight_sum = 0, 0, 0
        for e in emotions:
            v, a = self.emotion_to_va[e["label"]]
            w = e["score"]
            v_sum += v * w
            a_sum += a * w
            weight_sum += w

        return v_sum / weight_sum, a_sum / weight_sum
```

**Research Foundation**:
- Demszky, D., et al. (2020). GoEmotions: A Dataset of Fine-Grained Emotions.
- Russell, J. A. (1980). A Circumplex Model of Affect.
- Guo, C., et al. (2017). On Calibration of Modern Neural Networks.

**GoEmotions Emotion Categories** (27 + neutral):
```
admiration, amusement, anger, annoyance, approval, caring,
confusion, curiosity, desire, disappointment, disapproval,
disgust, embarrassment, excitement, fear, gratitude, grief,
joy, love, nervousness, optimism, pride, realization, relief,
remorse, sadness, surprise, neutral
```

**Acceptance Criteria**:
- [ ] Emotion classification accuracy > 85% on golden dataset
- [ ] Valence/arousal correlation with human ratings > 0.8
- [ ] Latency < 30ms P95 (GPU), < 100ms P95 (CPU)
- [ ] Confidence calibration ECE < 0.05

---

### Issue 3.1.2: Add Safety Detection with Clinical NLP
**Priority**: P0 (Critical)
**Estimate**: 3 days

**Current State**:
```python
# Keyword matching for safety
SAFETY_KEYWORDS = ("suicide", "kill myself", "self harm", ...)
if any(keyword in text_lower for keyword in SAFETY_KEYWORDS):
    return RED_BAND
```

**Problems**:
- Keyword matching has high false positive rate
- Misses euphemisms ("end it all", "not worth it anymore")
- No clinical validation

**Target State**:
```python
class ClinicalSafetyDetector:
    """
    Research: Coppersmith et al. (2018) - CLPsych shared task
             Zirikly et al. (2019) - Suicide risk assessment

    Model: Fine-tuned on CLPsych + Reddit mental health corpus

    Features:
    - Clinically validated risk indicators
    - Temporal pattern detection (declining sentiment)
    - Euphemism and indirect reference detection
    - Calibrated severity levels (LOW/MEDIUM/HIGH/CRITICAL)
    """
    def __init__(self):
        self.risk_classifier = pipeline(
            "text-classification",
            model="mental/mental-bert-base-uncased"
        )
        self.severity_thresholds = {
            "LOW": 0.3,
            "MEDIUM": 0.5,
            "HIGH": 0.7,
            "CRITICAL": 0.9
        }

    def assess_risk(self, text: str) -> SafetyAssessment:
        score = self.risk_classifier(text)[0]["score"]
        severity = self._score_to_severity(score)

        return SafetyAssessment(
            risk_detected=score > 0.3,
            severity=severity,
            confidence=score,
            indicators=self._extract_indicators(text),
            recommended_action=self._get_action(severity)
        )
```

**Acceptance Criteria**:
- [ ] Sensitivity > 95% (catch real risks)
- [ ] Specificity > 80% (reduce false alarms)
- [ ] Clinician-validated indicator set
- [ ] Appropriate escalation actions defined

---

# Milestone 4: Social Intelligence (Week 7-8)

## Epic 4.1: M07 Family Graph Enhancement

### Issue 4.1.1: Replace Hardcoded Dict with Graph Database Query
**Priority**: P0 (Critical Bug)
**Estimate**: 3 days

**Current State** (BROKEN):
```python
# Hardcoded 3-person family - completely useless
_RELATIONSHIP_DB: Dict[str, List[Tuple[str, str]]] = {
    "person_dad": [("person_mom", "SPOUSE_OF"), ("person_sharvi", "PARENT_OF")],
    "person_mom": [("person_dad", "SPOUSE_OF"), ("person_sharvi", "PARENT_OF")],
    "person_sharvi": [("person_dad", "CHILD_OF"), ("person_mom", "CHILD_OF")],
}
```

**Target State**:
```python
class FamilyGraphResolver:
    """
    Queries st_relationships table for actual family graph.
    Falls back to inference if relationship not found.
    """
    async def get_relationships(
        self,
        actor_id: str,
        context: PipelineContext
    ) -> List[Tuple[str, str]]:
        # Query actual database
        query = """
            SELECT related_person_id, relationship_type
            FROM st_relationships
            WHERE person_id = ? AND tenant_id = ?
        """
        rows = await context.syscalls.db_query(query, [actor_id, tenant_id])

        if rows:
            return [(r["related_person_id"], r["relationship_type"]) for r in rows]

        # Fallback: Return empty (no assumptions)
        return []
```

**Acceptance Criteria**:
- [ ] Queries real st_relationships table
- [ ] Handles missing relationships gracefully
- [ ] Cache with 5-minute TTL
- [ ] E2E test shows correct participant roles

---

### Issue 4.1.2: Graph Neural Network for Relationship Inference
**Priority**: P2 (Medium)
**Estimate**: 7 days
**Dependencies**: Issue 4.1.1

**Current State**:
- No inference capability
- Unknown participants get `role="OTHER"`

**Target State**:
```python
class GNNRelationshipInference:
    """
    Research: Hamilton et al. (2017) - GraphSAGE
             Kipf & Welling (2016) - Graph Convolutional Networks

    Purpose: Infer likely relationships from:
    - Co-occurrence patterns (who appears together)
    - Communication patterns (who messages whom)
    - Event attendance (shared activities)
    - Name similarity (family naming patterns)

    Architecture:
    - 2-layer GraphSAGE with mean aggregation
    - Node features: Person embeddings + activity history
    - Edge prediction: Binary classification (related/not)
    - Relation type: Multi-class classification
    """
    def __init__(self):
        self.encoder = GraphSAGE(
            in_channels=128,
            hidden_channels=64,
            out_channels=32,
            num_layers=2
        )
        self.edge_predictor = MLP([64, 32, 1])  # Related or not
        self.relation_classifier = MLP([64, 32, 5])  # 5 relation types

    def infer_relationship(
        self,
        person1: str,
        person2: str,
        graph: FamilyGraph
    ) -> Optional[str]:
        # Encode both persons
        h1 = self.encoder(graph, person1)
        h2 = self.encoder(graph, person2)

        # Predict if related
        edge_score = self.edge_predictor(torch.cat([h1, h2]))
        if edge_score < 0.5:
            return None

        # Classify relationship type
        relation_probs = self.relation_classifier(torch.cat([h1, h2]))
        return RELATION_TYPES[relation_probs.argmax()]
```

**Research Foundation**:
- Hamilton, W., et al. (2017). Inductive Representation Learning on Large Graphs.
- Kipf, T., & Welling, M. (2016). Semi-Supervised Classification with GCN.
- Schlichtkrull, M., et al. (2018). Modeling Relational Data with GCN.

**Acceptance Criteria**:
- [ ] Relationship inference accuracy > 80%
- [ ] Works with sparse graphs (few known relationships)
- [ ] Latency < 20ms P95
- [ ] Explainable predictions (why inferred)

---

### Issue 4.1.3: Social Context from Participant Analysis
**Priority**: P1 (High)
**Estimate**: 3 days

**Current State**:
```python
# Simple set membership check
if roles_set & {"SPOUSE", "PARENT", "CHILD"}:
    return "nuclear_family"
```

**Target State**:
```python
class SocialContextClassifier:
    """
    Research: Dunbar (1992) - Social group sizes
             Granovetter (1973) - Strength of weak ties

    Features:
    - Group composition analysis
    - Relationship strength scoring
    - Social distance calculation
    - Context-appropriate intimacy levels
    """
    DUNBAR_LAYERS = {
        "intimate": 5,      # Close family/friends
        "close": 15,        # Good friends, extended family
        "friends": 50,      # Friends
        "acquaintances": 150  # Acquaintances
    }

    def classify(
        self,
        participants: List[str],
        relationships: Dict[str, str],
        actor_id: str
    ) -> SocialContext:
        # Calculate average relationship strength
        strengths = [
            self._relationship_strength(relationships.get(p, "OTHER"))
            for p in participants if p != actor_id
        ]

        avg_strength = sum(strengths) / len(strengths) if strengths else 0

        # Classify based on composition and strength
        context = self._classify_context(participants, relationships)
        intimacy = self._strength_to_intimacy(avg_strength)

        return SocialContext(
            context=context,
            intimacy=intimacy,
            group_size=len(participants),
            dunbar_layer=self._get_dunbar_layer(avg_strength)
        )
```

**Acceptance Criteria**:
- [ ] Social context accuracy > 90%
- [ ] Intimacy levels validated against survey data
- [ ] Handles mixed groups (family + friends)

---

# Milestone 5: Activity Intelligence (Week 9-10)

## Epic 5.1: M10 Ingress Classification Enhancement

### Issue 5.1.1: Zero-Shot Activity Classification
**Priority**: P1 (High)
**Estimate**: 5 days
**Dependencies**: Issue 1.1.1

**Current State**:
```python
# Keyword matching with hardcoded lists
ACTIVITY_KEYWORDS = {
    "meal": ["breakfast", "lunch", "dinner", "ate", ...],
    "milestone": ["birthday", "anniversary", "graduation", ...],
    # Only 7 activity types
}
```

**Problems**:
- Only 7 activity types
- Keyword matching misses context
- "Had a great time at the park" → "unknown" (no keyword match)

**Target State**:
```python
class ZeroShotActivityClassifier:
    """
    Research: Yin et al. (2019) - Zero-shot text classification
             Lewis et al. (2019) - BART for NLI

    Model: facebook/bart-large-mnli

    Advantages:
    - No training data needed for new categories
    - Handles novel activity descriptions
    - Confidence scores for uncertainty
    """
    def __init__(self):
        self.classifier = pipeline(
            "zero-shot-classification",
            model="facebook/bart-large-mnli"
        )
        self.activity_labels = [
            "meal", "exercise", "work meeting", "medical appointment",
            "family gathering", "shopping", "travel", "entertainment",
            "education", "religious activity", "household chore",
            "outdoor recreation", "social event", "personal care",
            "creative activity", "sports", "celebration", "routine"
        ]

    def classify(self, text: str) -> ActivityClassification:
        result = self.classifier(
            text,
            candidate_labels=self.activity_labels,
            multi_label=True
        )

        return ActivityClassification(
            primary_activity=result["labels"][0],
            confidence=result["scores"][0],
            secondary_activities=result["labels"][1:3],
            is_multi_activity=result["scores"][1] > 0.3
        )
```

**Research Foundation**:
- Yin, W., et al. (2019). Benchmarking Zero-shot Text Classification.
- Lewis, M., et al. (2020). BART: Denoising Sequence-to-Sequence Pre-training.

**Acceptance Criteria**:
- [ ] Activity classification accuracy > 85%
- [ ] Support 20+ activity types (vs current 7)
- [ ] Latency < 50ms P95
- [ ] Handles multi-activity memories

---

### Issue 5.1.2: Hierarchical Activity Taxonomy
**Priority**: P2 (Medium)
**Estimate**: 3 days

**Target State**:
```yaml
# k0/contracts/taxonomies/activity_taxonomy.yaml
activity_taxonomy:
  version: "1.0.0"

  categories:
    - id: "sustenance"
      label: "Food & Drink"
      children:
        - id: "meal"
          children: ["breakfast", "lunch", "dinner", "snack", "brunch"]
        - id: "cooking"
        - id: "dining_out"

    - id: "wellness"
      label: "Health & Wellness"
      children:
        - id: "exercise"
          children: ["running", "gym", "yoga", "sports", "hiking"]
        - id: "medical"
          children: ["doctor_visit", "therapy", "dental"]
        - id: "self_care"

    - id: "social"
      label: "Social Activities"
      children:
        - id: "family_event"
        - id: "party"
        - id: "reunion"
        - id: "date"

    # ... 50+ activity types in hierarchy
```

**Acceptance Criteria**:
- [ ] Taxonomy covers 95% of common activities
- [ ] Hierarchical classification (meal → dinner)
- [ ] Easy to extend without code changes

---

# Milestone 6: Salience Intelligence (Week 11-12)

## Epic 6.1: M06 Salience Scoring Enhancement

### Issue 6.1.1: Learned Salience Weights
**Priority**: P1 (High)
**Estimate**: 5 days

**Current State**:
```python
# Hardcoded weights (no learning)
salience_score = 0.50 * social + 0.40 * affect + 0.10 * recency
```

**Problems**:
- Static weights ignore user preferences
- No personalization
- Research-based but not validated on our data

**Target State**:
```python
class LearnedSalienceScorer:
    """
    Research: Corbetta & Shulman (2002) - Attention control
             Itti & Koch (2000) - Saliency-based attention
             Cahill & McGaugh (1998) - Emotional memory

    Architecture:
    - Base weights from cognitive research
    - User-specific weight adaptation via online learning
    - Contextual attention (time of day, activity type)
    """
    BASE_WEIGHTS = {
        "social": 0.50,   # From kin selection theory
        "affect": 0.40,   # From amygdala-hippocampus interaction
        "recency": 0.10   # From working memory decay
    }

    def __init__(self, user_id: str):
        self.user_weights = self._load_user_weights(user_id)

    def score(
        self,
        social_score: float,
        affect_score: float,
        recency_score: float,
        context: Dict[str, Any]
    ) -> float:
        # Blend base weights with learned user weights
        weights = self._blend_weights(self.BASE_WEIGHTS, self.user_weights)

        # Apply contextual attention
        weights = self._apply_context_attention(weights, context)

        return (
            weights["social"] * social_score +
            weights["affect"] * affect_score +
            weights["recency"] * recency_score
        )

    def update_from_feedback(self, memory_id: str, user_rating: float):
        """
        Online learning from user interactions:
        - Explicit: User marks memory as important/unimportant
        - Implicit: User views, shares, or revisits memory
        """
        # Gradient update on weights
        pass
```

**Research Foundation**:
- Corbetta, M., & Shulman, G. L. (2002). Control of goal-directed and stimulus-driven attention.
- Itti, L., & Koch, C. (2000). A saliency-based search mechanism for overt and covert shifts of visual attention.
- Cahill, L., & McGaugh, J. L. (1998). Mechanisms of emotional arousal and lasting declarative memory.

**Acceptance Criteria**:
- [ ] Weight learning from user feedback
- [ ] Personalized salience within 2 weeks of usage
- [ ] A/B test shows improved engagement
- [ ] Weights interpretable and explainable

---

### Issue 6.1.2: Attention-Based Salience with Memory Context
**Priority**: P2 (Medium)
**Estimate**: 7 days

**Target State**:
```python
class AttentionSalienceScorer:
    """
    Research: Vaswani et al. (2017) - Attention is all you need
             Graves et al. (2014) - Neural Turing Machines

    Idea: Salience depends on what's already in memory.
    - Novelty: How different from recent memories?
    - Coherence: How well does it fit existing narrative?
    - Gap-filling: Does it answer open questions?

    Architecture:
    - Encode current memory
    - Attend over recent memory bank
    - Score based on attention patterns
    """
    def __init__(self):
        self.encoder = SentenceTransformer("all-MiniLM-L6-v2")
        self.attention = MultiHeadAttention(
            embed_dim=384,
            num_heads=8
        )

    def score(
        self,
        current_memory: str,
        recent_memories: List[str],
        user_id: str
    ) -> SalienceScore:
        # Encode current memory
        current_emb = self.encoder.encode(current_memory)

        # Encode recent memories
        recent_embs = self.encoder.encode(recent_memories)

        # Compute attention weights
        attn_weights = self.attention(
            query=current_emb,
            key=recent_embs,
            value=recent_embs
        )

        # Novelty = low attention (dissimilar to recent)
        novelty = 1.0 - attn_weights.max()

        # Coherence = attention to thematically related memories
        coherence = self._compute_coherence(attn_weights, recent_embs)

        return SalienceScore(
            novelty=novelty,
            coherence=coherence,
            overall=self._combine(novelty, coherence)
        )
```

**Acceptance Criteria**:
- [ ] Novelty scoring accuracy > 0.8 correlation with human ratings
- [ ] Memory bank retrieval < 10ms
- [ ] Explainable attention patterns

---

# Milestone 7: Integration & Validation (Week 13-14)

## Epic 7.1: End-to-End Validation

### Issue 7.1.1: Full Pipeline Accuracy Benchmark
**Priority**: P0 (Critical)
**Estimate**: 5 days

**Scope**:
- Run full P02 pipeline on golden dataset
- Measure accuracy of each module
- Compare rule-based vs ML tiers
- Generate accuracy report

**Metrics**:
```yaml
accuracy_report:
  M02_semantic_project:
    ner_accuracy: 0.92
    kg_triple_f1: 0.78
    latency_p95_ms: 45

  M04_affect_analyze:
    emotion_accuracy: 0.87
    valence_mae: 0.08
    arousal_mae: 0.12
    latency_p95_ms: 28

  M07_family_graph:
    relationship_accuracy: 0.95
    social_context_accuracy: 0.91
    latency_p95_ms: 8

  M10_ingress_classify:
    activity_accuracy: 0.88
    latency_p95_ms: 42

  overall:
    pipeline_latency_p95_ms: 180
    memory_peak_mb: 1200
```

**Acceptance Criteria**:
- [ ] All modules meet accuracy targets
- [ ] Pipeline latency < 200ms P95
- [ ] Memory usage < 2GB
- [ ] Regression test in CI

---

### Issue 7.1.2: A/B Testing Framework
**Priority**: P1 (High)
**Estimate**: 3 days

**Purpose**:
- Compare rule-based vs ML accuracy
- Measure user engagement differences
- Gradual rollout with automatic rollback

**Implementation**:
```python
class ABTestFramework:
    def assign_variant(self, user_id: str, experiment: str) -> str:
        """Deterministic assignment based on user_id hash."""
        hash_val = hash(f"{user_id}:{experiment}") % 100

        config = EXPERIMENTS[experiment]
        if hash_val < config["treatment_percentage"]:
            return "TREATMENT"  # ML tier
        return "CONTROL"  # Rule-based tier

    def record_outcome(
        self,
        user_id: str,
        experiment: str,
        metric: str,
        value: float
    ):
        """Record metric for statistical analysis."""
        pass

    def analyze(self, experiment: str) -> ABTestResult:
        """Statistical significance testing."""
        pass
```

**Acceptance Criteria**:
- [ ] Deterministic user assignment
- [ ] Metric recording and analysis
- [ ] Statistical significance calculation
- [ ] Automatic rollback on degradation

---

# Appendix A: Research Bibliography

## Natural Language Processing
1. Honnibal, M., & Montani, I. (2020). spaCy: Industrial-strength Natural Language Processing in Python.
2. Devlin, J., et al. (2019). BERT: Pre-training of Deep Bidirectional Transformers for Language Understanding.
3. Liu, Y., et al. (2019). RoBERTa: A Robustly Optimized BERT Pretraining Approach.

## Knowledge Graphs
4. Bordes, A., et al. (2013). Translating Embeddings for Modeling Multi-relational Data. NeurIPS.
5. Yao, Y., et al. (2019). DocRED: A Large-Scale Document-Level Relation Extraction Dataset. ACL.
6. Schlichtkrull, M., et al. (2018). Modeling Relational Data with Graph Convolutional Networks. ESWC.

## Emotion & Sentiment
7. Demszky, D., et al. (2020). GoEmotions: A Dataset of Fine-Grained Emotions. ACL.
8. Russell, J. A. (1980). A Circumplex Model of Affect. Journal of Personality and Social Psychology.
9. Barbieri, F., et al. (2020). TweetEval: Unified Benchmark and Comparative Evaluation. EMNLP.

## Attention & Salience
10. Corbetta, M., & Shulman, G. L. (2002). Control of goal-directed and stimulus-driven attention in the brain. Nature Reviews Neuroscience.
11. Itti, L., & Koch, C. (2000). A saliency-based search mechanism for overt and covert shifts of visual attention. Vision Research.
12. Cahill, L., & McGaugh, J. L. (1998). Mechanisms of emotional arousal and lasting declarative memory. TINS.

## Graph Neural Networks
13. Hamilton, W., et al. (2017). Inductive Representation Learning on Large Graphs. NeurIPS.
14. Kipf, T., & Welling, M. (2016). Semi-Supervised Classification with Graph Convolutional Networks. ICLR.
15. Veličković, P., et al. (2018). Graph Attention Networks. ICLR.

## Social Psychology
16. Dunbar, R. I. M. (1992). Neocortex size as a constraint on group size in primates. Journal of Human Evolution.
17. Granovetter, M. S. (1973). The Strength of Weak Ties. American Journal of Sociology.
18. Hamilton, W. D. (1964). The genetical evolution of social behaviour. Journal of Theoretical Biology.

## Clinical NLP
19. Coppersmith, G., et al. (2018). CLPsych 2018 Shared Task: Predicting Current and Future Psychological Health.
20. Zirikly, A., et al. (2019). CLPsych 2019 Shared Task: Predicting the Degree of Suicide Risk.

## Zero-Shot Learning
21. Yin, W., et al. (2019). Benchmarking Zero-shot Text Classification: Datasets, Evaluation and Entailment Approach. EMNLP.
22. Lewis, M., et al. (2020). BART: Denoising Sequence-to-Sequence Pre-training. ACL.

---

# Appendix B: Model Size & Latency Budget

| Module | Model | Size | GPU Latency | CPU Latency |
|--------|-------|------|-------------|-------------|
| M02 NER | roberta-base | 125MB | 15ms | 60ms |
| M02 Coref | lingmess-coref | 400MB | 25ms | 100ms |
| M02 Relation | bert-relation | 125MB | 20ms | 80ms |
| M04 Emotion | roberta-go-emotions | 125MB | 12ms | 50ms |
| M04 Safety | mental-bert | 125MB | 10ms | 45ms |
| M07 GNN | graphsage-family | 50MB | 5ms | 15ms |
| M10 Zero-Shot | bart-large-mnli | 400MB | 40ms | 150ms |
| **Total** | | **1.35GB** | **127ms** | **500ms** |

Budget: 200ms P95 GPU, 600ms P95 CPU ✓

---

# Appendix C: Rollout Plan

## Phase 1: Shadow Mode (Week 1-2)
- Run ML models in parallel with rule-based
- Log predictions but use rule-based output
- Collect accuracy metrics

## Phase 2: Canary (Week 3-4)
- 1% traffic to ML models
- Monitor latency, accuracy, error rates
- Automatic rollback if degradation > 5%

## Phase 3: Gradual Rollout (Week 5-8)
- 1% → 5% → 10% → 25% → 50% → 100%
- A/B test user engagement
- Per-module rollout (not all at once)

## Phase 4: Deprecation (Week 9-10)
- Remove rule-based code paths
- Archive VADER, keyword matching code
- Update documentation

---

*Document Version: 1.0.0*
*Last Updated: 2025-11-26*
*Authors: K0 Architecture Team*
