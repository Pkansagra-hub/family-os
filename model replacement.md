Created 9 todos

Let me do comprehensive code discovery to map all model usages:

Searched for regex `from familyos_ultrabert|import.*ultrabert`, no results

Searched for regex `go_emotions|GoEmotions`, 20 results

Searched for regex `clinical_safety|ClinicalSafety`, 20 results

Searched for regex `vader|VADER|VaderSentiment`, 20 results

Searched for regex `zero_shot_classifier|ZeroShot`, 20 results

Searched for regex `TransformerNER|transformer_ner`, 20 results

Searched for regex `TransformerAffect|transformer_affect`, 20 results

Searched for regex `sentence_transformer|SentenceTransformer`, 20 results

Searched for regex `model_registry|ModelRegistry` (`**/k0/**/*.py`), 20 results

Searched for regex `spacy\.load|en_core_web`, 20 results

Now let me check the key integration points in the kernel:

Read [](file:///d%3A/familyos/k0/kernel/app.py#600-600), lines 600 to 750

Read [](file:///d%3A/familyos/k0/runtime)

Now let me understand the flow better by checking how modules consume models:

Read [](file:///d%3A/familyos/k0/modules/affect/analyze.py#1-1), lines 1 to 100

Read [](file:///d%3A/familyos/k0/modules/affect/analyze.py#200-200), lines 200 to 680

Now I have a clear picture. Let me update the todo list and create a comprehensive integration plan:

Completed: *Code Discovery - Map all model usages* (1/9)

---

## Code Discovery Complete - Integration Plan

### Current Model Usage Map

| File | Current Models Used | Replace With UltraBERT |
|------|---------------------|------------------------|
| app.py | Initializes: VADER, spaCy, TransformerNER, TransformerAffect, ClinicalSafety | Single UltraBERT Client |
| model_registry.py | Manages 9 models: spacy_nlp, vader, ner_transformer, sentence_transformer, sentiment_transformer, ner_family, go_emotions, clinical_safety, zero_shot_classifier | Single UltraBERT entry |
| model_loaders.py | load_spacy, load_vader, load_ner_model, load_sentence_transformer, load_transformers_pipeline, load_go_emotions, load_clinical_safety, load_zero_shot_classifier | load_ultrabert |
| analyze.py | VADER (tier0), TransformerAffect (tier1), ClinicalSafety | UltraBERT: sentiment, emotions, safety_familyos |
| transformer_affect.py | GoEmotions (roberta-base-go_emotions) | UltraBERT: emotions |
| clinical_safety.py | distilbert-sst2 + rule-based | UltraBERT: safety_familyos |
| semantic_project.py | spaCy (en_core_web_sm/lg), TransformerNER (bert-base-NER) | UltraBERT: ner_family, ner_general, temporal |
| transformer_ner.py | dslim/bert-base-NER | UltraBERT: ner_family, ner_general |
| ingress_classify.py | Rule-based + zero_shot_classifier (bart-large-mnli) | UltraBERT: ingress, intent |
| zero_shot_classifier.py | facebook/bart-large-mnli | UltraBERT: ingress, intent |

---

### Integration Steps (Ordered)

#### Step 1: Create UltraBERT Adapter Module
**File**: `k0/runtime/ultrabert_adapter.py`
- Singleton Client wrapper
- Map UltraBERT outputs to K0 module interfaces
- Provide backward-compatible API

#### Step 2: Update Model Registry
**File**: model_registry.py
- Add `ultrabert` model spec
- Add `load_ultrabert` loader
- Remove/deprecate old model specs

#### Step 3: Update M04 (affect.analyze)
**Files**:
- analyze.py - Main entry point
- transformer_affect.py - Remove or delegate to UltraBERT
- clinical_safety.py - Remove or delegate to UltraBERT

**Mapping**:
```python
# OLD
vader_scores = vader_analyzer(text)
emotions = go_emotions(text)
safety = clinical_safety(text)

# NEW
result = ultrabert_client.analyze(text, capabilities=["sentiment", "emotions", "safety_familyos"])
sentiment = result.sentiment  # "very_positive"
emotions = result.emotions    # ["joy", "love"]
safety = result.safety        # "GREEN"
valence = result.sentiment_confidence  # 0.92
```

#### Step 4: Update M02 (semantic_project)
**Files**:
- semantic_project.py - Main entry point
- transformer_ner.py - Remove or delegate to UltraBERT

**Mapping**:
```python
# OLD
entities = transformer_ner.extract(text)
temporal = spacy_nlp(text).ents

# NEW
result = ultrabert_client.analyze(text, capabilities=["ner_family", "ner_general", "temporal"])
entities = result.entities + result.general_entities
temporal = result.temporal
```

#### Step 5: Update M10 (ingress_classify)
**Files**:
- ingress_classify.py
- zero_shot_classifier.py

**Mapping**:
```python
# OLD
activity = zero_shot_classifier(text, candidate_labels)

# NEW
result = ultrabert_client.analyze(text, capabilities=["ingress", "intent"])
activity_type = result.ingress  # "CELEBRATION"
intent = result.intent          # "share_news"
```

#### Step 6: Update Kernel Lifespan
**File**: app.py
- Remove Phase 1.5-1.7 (individual model initialization)
- Add single UltraBERT initialization
- Remove legacy preloaded_models dict

#### Step 7: Update Docker
**File**: Dockerfile
- Add UltraBERT wheel to container
- Remove unused model downloads

#### Step 8: Run Benchmark
- Submit envelopes
- Validate accuracy improvements

---

### File Changes Summary

| Action | Files |
|--------|-------|
| **CREATE** | `k0/runtime/ultrabert_adapter.py` |
| **MODIFY** | model_registry.py, model_loaders.py |
| **MODIFY** | analyze.py |
| **DEPRECATE** | transformer_affect.py, clinical_safety.py |
| **MODIFY** | semantic_project.py |
| **DEPRECATE** | transformer_ner.py |
| **MODIFY** | ingress_classify.py |
| **DEPRECATE** | zero_shot_classifier.py |
| **MODIFY** | app.py |
| **MODIFY** | Dockerfile |

---

Ready to proceed? Let's start with **Step 1: Create UltraBERT Adapter Module**.
