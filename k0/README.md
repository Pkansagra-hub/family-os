# K0 Intelligence Kernel

**Production-Ready Orchestration System for Family AI**

---

## Overview

K0 is the core intelligence kernel that manages agents, planning, execution, protocol adherence, and adaptation. Built on strong architectural principles: actor-based concurrency, capability security, protocol validation, staged execution, and fault isolation.

## Architecture

```text
k0/
├── kernel/          # FastAPI server, config, lifecycle management
├── runtime/         # Pipeline execution, module registry, model registry
├── modules/         # Reusable ML modules (16+ modules)
├── pipelines/       # Pipeline definitions and protocol
├── config/          # YAML configurations
├── contracts/       # Module and pipeline contracts
├── bus/             # Event bus and message dispatching
├── drivers/         # External service integrations
├── storage/         # SQLite storage adapters
├── gate/            # Envelope validation
├── uow/             # Unit of work transactions
├── obs/             # Observability (metrics, tracing, logging)
├── qos/             # Quality of service scheduler
└── security/        # Capability security
```

## Quick Start

### 1. Start the Kernel

```bash
# Install dependencies
pip install -r requirements.txt

# Start kernel server
python -m k0.cli.k0ctl serve --host 0.0.0.0 --port 8080
```

### 2. Submit an Envelope

```bash
curl -X POST http://localhost:8080/v1/envelopes \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "family_123",
    "space_id": "home",
    "schema_uri": "envelope.schema.json",
    "body": {"text": "Had dinner with my wife at the Italian restaurant"}
  }'
```

---

## ML Model Management

K0 provides a centralized **Model Registry** for managing ML models across all modules.

### Loading Models

Models are lazy-loaded on first use to minimize startup time and memory usage.

```python
from k0.runtime import get_model_registry, init_model_registry

# Option 1: Get singleton registry (initialized at kernel startup)
registry = get_model_registry()

# Option 2: Initialize with custom config
registry = await init_model_registry(
    config_path="k0/config/models.yaml",
    gpu_memory_limit_mb=4096,
    cpu_memory_limit_mb=8192,
)
```

### Getting Models

```python
# Async get (lazy loads if needed)
spacy_nlp = await registry.get("spacy_nlp")
doc = spacy_nlp("Hello world")
entities = [(ent.text, ent.label_) for ent in doc.ents]

# Sync get (returns None if not loaded)
vader = registry.get_sync("vader_analyzer")
if vader:
    scores = vader.polarity_scores("I love this product!")
    print(f"Compound: {scores['compound']}")
```

### Using Models in Modules

Modules receive preloaded models via `PipelineContext`:

```python
# k0/modules/affect/analyze.py
async def run(
    message: BusMessage,
    context: PipelineContext,
    **config,
) -> dict:
    # Get preloaded models from context
    vader = context.preloaded_models.get("vader_analyzer")
    spacy_nlp = context.preloaded_models.get("spacy_nlp")

    # Parse envelope
    import json
    envelope = json.loads(message.payload)
    text = envelope.get("body", {}).get("text", "")

    # Use VADER for sentiment
    if vader:
        scores = vader.polarity_scores(text)
        sentiment = {
            "compound": scores["compound"],
            "positive": scores["pos"],
            "negative": scores["neg"],
            "neutral": scores["neu"],
        }
    else:
        sentiment = {"compound": 0.0}

    # Use spaCy for entities
    entities = []
    if spacy_nlp:
        doc = spacy_nlp(text)
        entities = [
            {"text": ent.text, "label": ent.label_}
            for ent in doc.ents
        ]

    return {
        **envelope,
        "affect": sentiment,
        "entities": entities,
    }
```

### Available Models

| Model Name | Description | Memory | Device |
|------------|-------------|--------|--------|
| `spacy_nlp` | spaCy en_core_web_sm (NER, POS, parsing) | 100MB | CPU |
| `spacy_nlp_lg` | spaCy en_core_web_lg (better accuracy) | 800MB | CPU |
| `vader_analyzer` | VADER sentiment analyzer | 50MB | CPU |
| `sentence_transformer` | all-MiniLM-L6-v2 embeddings | 500MB | CUDA/CPU |
| `sentiment_transformer` | DistilBERT sentiment classifier | 400MB | CUDA/CPU |
| `zero_shot_classifier` | BART-large-MNLI zero-shot | 1500MB | CUDA/CPU |

### Model Registry API

```python
# Check if model is loaded
if registry.is_loaded("sentence_transformer"):
    model = await registry.get("sentence_transformer")

# List available models
available = registry.list_specs()  # ["spacy_nlp", "vader_analyzer", ...]

# List loaded models
loaded = registry.list_loaded()  # ["spacy_nlp", "vader_analyzer"]

# Get statistics
stats = registry.get_stats()
print(f"GPU used: {stats['gpu_memory_used_mb']}MB / {stats['gpu_memory_limit_mb']}MB")

# Preload multiple models
results = await registry.preload(["spacy_nlp", "vader_analyzer"])

# Unload model to free memory
await registry.unload("sentence_transformer")

# Shutdown (unload all)
await registry.shutdown()
```

### Model Configuration

Configure models in `k0/config/models.yaml`:

```yaml
models:
  my_custom_model:
    name: "Custom NER Model"
    model_id: "my-org/custom-ner"
    tier: transformer_small
    loader: "k0.runtime.model_loaders.load_transformers_pipeline"
    memory_mb: 600
    device_preference: cuda
    fallback_to_cpu: true
    warmup_input: "Test sentence for warmup"
```

---

## Feature Flags (ML Tier Selection)

K0 provides **Feature Flags** for controlling which ML tier each module uses, enabling gradual rollouts and A/B testing.

### ML Tiers

| Tier | Description | Example Models |
|------|-------------|----------------|
| `RULE_BASED` | Lexicon/regex rules | VADER, keyword matching |
| `SPACY_SMALL` | spaCy small models | en_core_web_sm |
| `SPACY_LARGE` | spaCy large models | en_core_web_lg |
| `TRANSFORMER_SMALL` | Small transformers | DistilBERT, MiniLM |
| `TRANSFORMER_LARGE` | Large transformers | BART, RoBERTa-large |

### Using Feature Flags in Modules

```python
from k0.config.feature_flags import get_feature_flags, MLTier

async def run(message: BusMessage, context: PipelineContext, **config):
    flags = get_feature_flags()

    # Get tier for this module (uses consistent hashing for A/B)
    tier = flags.get_tier("affect.analyze", request_id=message.trace_id)

    if tier == MLTier.TRANSFORMER_SMALL:
        # Use transformer-based sentiment
        transformer = await context.model_registry.get("sentiment_transformer")
        result = transformer(text)
        sentiment = {"compound": result[0]["score"]}
    else:
        # Use VADER (rule-based)
        vader = context.preloaded_models.get("vader_analyzer")
        scores = vader.polarity_scores(text)
        sentiment = {"compound": scores["compound"]}

    # Record success for auto-fallback tracking
    flags.record_success("affect.analyze")

    return {**envelope, "sentiment": sentiment}
```

### Using the @with_ml_tier Decorator

```python
from k0.config.feature_flags import with_ml_tier, MLTier

@with_ml_tier("affect.analyze")
async def analyze_sentiment(text: str, tier: MLTier = None) -> dict:
    """Tier is automatically injected based on feature flags."""
    if tier == MLTier.TRANSFORMER_SMALL:
        # Transformer path
        return await transformer_sentiment(text)
    elif tier == MLTier.SPACY_LARGE:
        # spaCy large path
        return await spacy_sentiment(text)
    else:
        # Default: VADER (rule-based)
        return vader_sentiment(text)

# Usage - tier selected automatically
result = await analyze_sentiment("I love this!", request_id="req-123")
```

### Configuring Feature Flags

Edit `k0/config/feature_flags.yaml`:

```yaml
modules:
  # Start with VADER, gradually roll out transformer
  affect.analyze:
    enabled_tier: transformer_small
    fallback_tier: rule_based
    rollout_percentage: 25.0  # 25% get transformer
    max_failures_before_fallback: 3
    description: "Sentiment analysis"

  # Use spaCy large for entity extraction
  hippocampus.semantic_project:
    enabled_tier: spacy_large
    fallback_tier: spacy_small
    rollout_percentage: 100.0
    description: "Entity and KG extraction"
```

### Feature Flags API

```python
from k0.config.feature_flags import get_feature_flags, init_feature_flags, MLTier

# Get singleton
flags = get_feature_flags()

# Initialize with config
flags = await init_feature_flags("k0/config/feature_flags.yaml")

# Get tier for module
tier = flags.get_tier("affect.analyze", request_id="req-123")

# Set tier at runtime
flags.set_tier("affect.analyze", MLTier.TRANSFORMER_SMALL, rollout_percentage=50.0)

# Record outcomes for auto-fallback
flags.record_success("affect.analyze")
flags.record_failure("affect.analyze")

# Reset failure count
flags.reset_failures("affect.analyze")

# Get A/B metrics
metrics = flags.get_metrics("affect.analyze")
# {'affect.analyze': {'advanced_calls': 150, 'fallback_calls': 50, 'failures': 3}}

# Get all flags
all_flags = flags.get_all_flags()
```

### Percentage-Based Rollouts

Feature flags support percentage-based rollouts with consistent hashing:

```python
# Same request_id always gets same result (consistent A/B assignment)
tier1 = flags.get_tier("affect.analyze", request_id="user-123")
tier2 = flags.get_tier("affect.analyze", request_id="user-123")
assert tier1 == tier2  # Always same for same request_id

# Different request_ids get different assignments based on rollout %
# With 25% rollout:
# - ~25% of request_ids get enabled_tier (TRANSFORMER_SMALL)
# - ~75% of request_ids get fallback_tier (RULE_BASED)
```

### Auto-Fallback on Failures

When a module's advanced tier fails repeatedly, it automatically falls back:

```python
# After max_failures_before_fallback (default: 3) failures:
flags.record_failure("affect.analyze")
flags.record_failure("affect.analyze")
flags.record_failure("affect.analyze")

# Now get_tier returns fallback_tier regardless of rollout %
tier = flags.get_tier("affect.analyze")  # Returns RULE_BASED

# Reset to re-enable advanced tier
flags.reset_failures("affect.analyze")
```

---

## Module Development

### Creating a New Module

1. **Create module file**: `k0/modules/<domain>/<action>.py`

```python
# k0/modules/affect/analyze.py
"""Affect Analysis Module - Sentiment and emotion detection."""

from __future__ import annotations
import json
import logging
from typing import Any
from k0.bus import BusMessage
from k0.pipelines.protocol import PipelineContext

logger = logging.getLogger(__name__)

async def run(
    message: BusMessage,
    context: PipelineContext,
    **config: Any,
) -> dict[str, Any]:
    """
    Analyze sentiment and emotions in text.

    Args:
        message: Incoming BusMessage with envelope
        context: PipelineContext with syscalls, models, logger
        **config: Stage-specific configuration

    Returns:
        Enriched envelope with affect analysis
    """
    envelope = json.loads(message.payload)
    text = envelope.get("body", {}).get("text", "")

    # Get models
    vader = context.preloaded_models.get("vader_analyzer")

    # Compute sentiment
    if vader and text:
        scores = vader.polarity_scores(text)
        affect = {
            "sentiment_compound": scores["compound"],
            "sentiment_label": (
                "positive" if scores["compound"] > 0.05
                else "negative" if scores["compound"] < -0.05
                else "neutral"
            ),
        }
    else:
        affect = {"sentiment_compound": 0.0, "sentiment_label": "neutral"}

    context.logger.info(
        f"Affect analysis complete",
        extra={"sentiment": affect["sentiment_label"], "trace_id": message.trace_id},
    )

    return {**envelope, "affect": affect}
```

2. **Create module contract**: `k0/contracts/modules/affect.analyze.v1.yaml`

```yaml
module_id: affect.analyze
version: v1
input_event_types:
  - p02.write.requested.v1
output_event_types:
  - p02.affect.analyzed.v1
latency_budget_ms: 20
side_effects: []
idempotent: true
description: |
  Sentiment and emotion analysis using VADER or transformer models.
  Outputs sentiment scores and emotion labels.
```

3. **Add to pipeline**: `k0/contracts/pipelines/p02_write.v1.yaml`

```yaml
dag:
  - id: stage_04_affect
    module: affect.analyze:v1
    after: [stage_03_previous]
    config:
      confidence_threshold: 0.8
```

---

## Configuration Reference

| File | Purpose |
|------|---------|
| `k0/config/kernel.yaml` | Core kernel settings (server, QoS, security) |
| `k0/config/models.yaml` | ML model definitions and memory budgets |
| `k0/config/feature_flags.yaml` | ML tier selection and rollout configuration |
| `k0/config/logging.yaml` | Python logging configuration |
| `k0/config/neo4j.yaml` | Neo4j knowledge graph settings |
| `k0/config/embeddings.yml` | Embedding backend configuration |

---

## Testing

```bash
# Run all tests
python -m pytest tests/k0/ -v

# Run model registry tests
python -m pytest tests/k0/runtime/test_model_registry.py -v

# Run feature flags tests
python -m pytest tests/k0/config/test_feature_flags.py -v

# Run module tests
python -m pytest tests/k0/modules/ -v
```

---

## Related Documentation

- `k0/kernel/README.md` - Kernel server and API
- `k0/runtime/README.md` - Pipeline execution engine
- `k0/config/README.md` - Configuration reference
- `k0/modules/README.md` - Module development guide
- `k0/modules/MODULE_ENHANCEMENT_PLAN.md` - ML upgrade roadmap
- `k0/pipelines/README.md` - Pipeline protocol

---

## Architecture Decision Records

- `docs/architecture/decisions-K0/` - K0-specific ADRs
- `docs/architecture/decisions-K1/` - K1-specific ADRs

---

## Performance Goals

- **First response**: < 100ms
- **P95 latency**: < 500ms for full pipeline
- **Memory**: < 8GB total (models + runtime)
- **GPU**: < 4GB VRAM (with CPU fallback)
