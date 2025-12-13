"""
M22: embedding.extract_from_cache

Extracts the 768-dim embedding from UltraBERT's single-pass cache.
Performance: <1ms P95 (cache read only, no inference)

ADR Reference: ADR-K003 (Inline Embedding via UltraBERT)
Contract: k0/contracts/modules/embedding.extract_from_cache.v1.yaml

Architecture:
- P02 M02 (semantic_project) calls UltraBERT for entity extraction
- P02 M04 (affect.analyze) calls UltraBERT for sentiment/emotions
- P02 M10 (ingress_classify) calls UltraBERT for intent/routing
- All three share ONE cached forward pass (K0_ULTRABERT_SINGLE_PASS=1)
- M22 extracts the 768-dim embedding from this cached result

Benefits vs Legacy P08 Async Pattern:
- Zero latency: embedding already computed
- No MiniLM model load: saves 250MB memory
- Immediate availability: P03 can use embeddings without PENDING fallback
- Higher quality: 768-dim UltraBERT vs 384-dim MiniLM
- Consistent model: same model for all NLP tasks
"""

import logging
import uuid
from typing import Any

from k0.runtime.ultrabert_adapter import _get_full_analysis_result, get_embedding

logger = logging.getLogger(__name__)

# Module metrics
_metrics = {
    "cache_hits": 0,
    "cache_misses_direct_call": 0,
    "embedding_failures": 0,
    "no_text_inputs": 0,
}


async def run(envelope: dict[str, Any], enriched: dict[str, Any], context: Any) -> dict[str, Any]:
    """
    Extract embedding from UltraBERT cache.

    Args:
        envelope: Memory envelope with body.text
        enriched: Enrichment data from previous modules
        context: Execution context

    Returns:
        Dictionary with:
        - embedding: list[float] (768 dimensions) or None
        - embedding_id: str (UUID) or None
        - vector_dim: int (768)
        - model_id: str ('ultrabert_v2.1.0')
        - source: str ('cache_hit' | 'direct_call' | 'failed' | 'no_text')
    """
    text = envelope.get("body", {}).get("text", "")

    if not text or not text.strip():
        _metrics["no_text_inputs"] += 1
        logger.debug("M22: No text input, skipping embedding extraction")
        return {
            "embedding": None,
            "embedding_id": None,
            "vector_dim": 768,
            "model_id": "ultrabert_v2.1.0",
            "source": "no_text",
        }

    # Try cached result first (should be warm from M02/M04/M10)
    result = _get_full_analysis_result(text)
    if result and hasattr(result, "embedding") and result.embedding:
        _metrics["cache_hits"] += 1
        logger.debug(
            "M22: Embedding extracted from cache",
            extra={
                "text_length": len(text),
                "vector_dim": len(result.embedding),
                "source": "cache_hit",
            },
        )
        return {
            "embedding": result.embedding,
            "embedding_id": str(uuid.uuid4()),
            "vector_dim": 768,
            "model_id": "ultrabert_v2.1.0",
            "source": "cache_hit",
        }

    # Fallback: direct embedding call (rare, cache miss)
    # This can happen if:
    # - M02/M04/M10 haven't run yet (unusual stage ordering)
    # - Cache evicted (TTL expired or LRU eviction)
    # - K0_ULTRABERT_SINGLE_PASS=0 (disabled)
    embedding = get_embedding(text)
    if embedding:
        _metrics["cache_misses_direct_call"] += 1
        logger.info(
            "M22: Cache miss, called get_embedding() directly",
            extra={
                "text_length": len(text),
                "vector_dim": len(embedding),
                "source": "direct_call",
                "latency_penalty_ms": 30,  # Typical UltraBERT inference time
            },
        )
        return {
            "embedding": embedding,
            "embedding_id": str(uuid.uuid4()),
            "vector_dim": 768,
            "model_id": "ultrabert_v2.1.0",
            "source": "direct_call",
        }

    # Failure: UltraBERT unavailable or error
    # This will result in embedding_status=PENDING in st_hipp_events
    # P08 M25 (backfill) will retry later
    _metrics["embedding_failures"] += 1
    logger.warning(
        "M22: Embedding extraction failed",
        extra={
            "text_length": len(text),
            "source": "failed",
            "will_backfill": True,
        },
    )
    return {
        "embedding": None,
        "embedding_id": None,
        "vector_dim": 768,
        "model_id": "ultrabert_v2.1.0",
        "source": "failed",
    }


def get_metrics() -> dict[str, int]:
    """
    Get module metrics for observability.

    Returns:
        Dictionary with metric counters
    """
    return dict(_metrics)


def reset_metrics() -> None:
    """
    Reset metrics counters (for testing).
    """
    for key in _metrics:
        _metrics[key] = 0
