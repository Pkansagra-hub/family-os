# UltraBERT Deployment Guide

## Overview

FamilyOS UltraBERT v4.0.9 is a multi-head ModernBERT model providing 13 inference capabilities in a single forward pass. The K0 kernel depends on UltraBERT for all NLP operations including NER, sentiment, embeddings, safety classification, and more.

**Package**: `familyos-ultrabert>=4.0.8` (PyPI)
**Backend**: PyTorch (GPU) or ONNX (CPU)
**Weights**: ~967MB (fp32), cached at `~/.cache/familyos_ultrabert/encoder/v2/fp32/`
**HuggingFace Repo**: `Pkansagra/ultrabert-weights` (private)

---

## Inference Heads (13 Capabilities)

| # | Head | Output Attribute | Labels / Output |
|---|------|-----------------|-----------------|
| 1 | ner_family | `.entities` | KINSHIP, PERSON, PET, FAMILY_EVENT, HOME_LOC |
| 2 | ner_general | `.general_entities` | PER, ORG, LOC, GPE |
| 3 | temporal | `.temporal` | DATE_REL, DATE_ABS, TIME, FREQUENCY, DURATION |
| 4 | relation | `.relations` | spouse_of, sibling_of, parent_of, child_of, colleague_of, lives_at |
| 5 | sentiment | `.sentiment` `.sentiment_scores` | very_negative, negative, neutral, positive, very_positive |
| 6 | emotions | `.emotions` `.emotion_scores` | 44 classes (joy, grief, anger, gratitude, etc.) |
| 7 | intent | `.intent` `.intent_scores` | log_memory, query_memory, set_reminder, express_feeling, seek_advice, share_news, reflect, other |
| 8 | ingress | `.ingress` `.ingress_scores` | DIARY, TASK, HEALTH, FINANCE, RELATIONSHIP, WORK, META, MEMORY, PLANNING, CELEBRATION, CONCERN, GRATITUDE |
| 9 | safety | `.safety` `.is_safe` `.is_crisis` `.needs_attention` | GREEN, AMBER, RED, CRISIS |
| 10 | embedding | `.embedding` | 768-dim, unit-normalized |
| 11 | nli | `.nli` | entailment, neutral, contradiction |
| 12 | relevance | `score_relevance(query, doc)` | float score |
| 13 | safety_generic | (merged into safety) | — |

### Batch & Utility Methods

- `analyze_batch(texts)` — batch multi-head inference
- `embed_batch(texts)` — batch embedding extraction
- `similarity(text1, text2)` — cosine similarity
- `rerank(query, documents)` — document reranking
- `find_similar(query, documents, top_k)` — top-k similarity search
- `stream_analyze(text)` — streaming analysis
- `get_query_embedding(text)` — query-optimized embedding
- `get_document_embedding(text)` — document-optimized embedding
- `set_intent_labels(labels)` / `set_ingress_labels(labels)` — custom label override
- `init_intent_from_descriptions(descriptions)` — description-based intent init
- `init_ingress_from_descriptions(descriptions)` — description-based ingress init

### Convenience Booleans

- `.is_safe` — safety == GREEN
- `.is_crisis` — safety == CRISIS
- `.is_positive` — sentiment in (positive, very_positive)
- `.is_negative` — sentiment in (negative, very_negative)
- `.needs_attention` — safety in (AMBER, RED, CRISIS)

---

## Docker Deployment

### Weight Management

UltraBERT weights (~967MB) are NOT bundled in the Docker image. They are loaded at runtime via a volume mount from the host cache.

**Host cache location**: `~/.cache/familyos_ultrabert/encoder/v2/fp32/`

**Required files** (10 total):

```
model.safetensors          (~967MB)  Core model weights
config.json                (~2KB)    Model configuration
capabilities.json          (<1KB)    Head capability manifest
tokenizer.json             (~3.5MB)  Tokenizer vocabulary
tokenizer_config.json      (<1KB)    Tokenizer settings
special_tokens_map.json    (<1KB)    Special token definitions
embedding_metadata.json    (~2KB)    Embedding head metadata
globalpointer_metadata.json (~3KB)  NER head metadata
mgrh_metadata.json         (~1KB)   Multi-granularity head metadata
pruning_metadata.json      (~15KB)  Pruning configuration
```

### First-Time Setup (Host Machine)

Download weights to host cache before deploying:

```python
from familyos_ultrabert import Client
c = Client()  # triggers download on first use
r = c.analyze("test")
print(r.sentiment)  # verify working
```

Or via weights_manager directly:

```python
from familyos_ultrabert.weights_manager import download_encoder
path = download_encoder(version="v2", quantization="fp32")
print(path)  # ~/.cache/familyos_ultrabert/encoder/v2/fp32
```

### docker-compose.gpu.yml Volume Mount

The GPU compose file mounts the host weight cache into the container:

```yaml
volumes:
  # UltraBERT pre-cached weights (avoids runtime HuggingFace download)
  - ~/.cache/familyos_ultrabert:/root/.cache/familyos_ultrabert:ro
```

The container runs as `root` (`user: "0:0"`), so `Path.home()` = `/root`, and the weights_manager finds cached weights at `/root/.cache/familyos_ultrabert/encoder/v2/fp32/`.

### Environment Variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `FAMILYOS_CACHE_DIR` | Override weight cache directory | `~/.cache/familyos_ultrabert/` |
| `HF_TOKEN` | HuggingFace token (fallback download) | — |
| `CUDA_VISIBLE_DEVICES` | GPU device selection | `0` |
| `K0_ULTRABERT_SINGLE_PASS` | Enable single-pass analysis mode | `1` |
| `K0_ULTRABERT_FULL_WARMUP` | Run all heads during warmup | `0` |

### GPU Requirements

- NVIDIA GPU with CUDA 12.8+ support
- Docker Desktop with NVIDIA Container Toolkit
- Minimum ~2GB VRAM for fp32 inference

---

## Troubleshooting

### Error: 401 Unauthorized / Repository Not Found

```
Failed to download encoder: 401 Client Error. Repository Not Found
```

**Cause**: The HF repo `Pkansagra/ultrabert-weights` is private. Container tried to download at runtime without authentication.

**Fix**: Ensure weights are pre-cached on the host and the volume mount is configured:

```yaml
- ~/.cache/familyos_ultrabert:/root/.cache/familyos_ultrabert:ro
```

### Error: No weights found

```
Failed to load UltraBERT: No weights found
```

**Cause**: Neither cached weights nor downloadable weights are available.

**Fix**: Run the first-time setup on the host machine to populate the cache.

### Error: PyTorch backend requires fp32

```
PyTorch backend requires fp32 weights. Switching from int8 to fp32.
```

**Expected behavior**: PyTorch GPU backend only supports fp32 weights. The int8 default is auto-corrected to fp32. This is not an error.

### Log shows "vv2"

**Fixed**: Was a format bug in weights_manager.py where `f"v{version}"` with `version="v2"` produced "vv2". Now correctly logs `"Downloading encoder v2 (fp32)..."`.

---

## K0 Integration

The K0 kernel uses UltraBERT through `k0/runtime/ultrabert_adapter.py`:

- **Singleton pattern**: One UltraBERT instance shared across all pipelines
- **Single-pass mode**: All 13 heads fire once per text, results cached (TTL 30s, LRU 64 entries)
- **Full warmup**: Optional pre-load of all heads at startup via `K0_ULTRABERT_FULL_WARMUP=1`
- **Thread-safe**: Initialization protected by threading lock

### Pipeline Usage

| Pipeline | UltraBERT Heads Used |
|----------|---------------------|
| P00 (Ingestion) | All 13 heads via single-pass |
| P02 (Write) | embedding, sentiment, safety, intent, ingress |
| P03 (Consolidation) | embedding (via R0 batch selector) |
| P08 (Search) | embedding, relevance, nli |
