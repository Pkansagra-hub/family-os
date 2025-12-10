"""
Model Loaders - Factory functions for loading ML models.

UltraBERT is the ONLY model needed for K0 kernel.
It replaces 9 separate models (4.6GB -> 500MB):
- spaCy NER, VADER, GoEmotions, clinical_safety
- sentence_transformer, zero_shot_classifier, etc.

Related:
- k0/runtime/model_registry.py: Uses these loaders
- k0/runtime/ultrabert_adapter.py: High-level adapter

Issue: UltraBERT Migration - Single Unified Model
Status: IMPLEMENTED
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def load_ultrabert(model_id: str, device: str = "cpu") -> Any:
    """
    Load FamilyOS UltraBERT unified model.

    UltraBERT v2.0.3 provides 12 capabilities in a single 500MB model:
    - sentiment, emotions, safety_familyos, safety_generic
    - ner_family, ner_general, temporal, intent
    - ingress, relation, nli, embedding

    The client handles:
    - Automatic warmup (warmup=True by default)
    - Device selection (auto-detects CUDA/MPS/CPU)
    - Lazy loading option if needed

    Args:
        model_id: Model identifier (ignored, UltraBERT is singleton)
        device: Device hint (ignored, client auto-detects)

    Returns:
        UltraBERT Client instance (already warmed up and ready)

    Raises:
        ImportError: If familyos_ultrabert package not installed
        RuntimeError: If model fails to load
    """
    try:
        from familyos_ultrabert import Client
    except ImportError:
        raise ImportError(
            "familyos_ultrabert not installed. Install with: "
            "pip install familyos_ultrabert-2.0.3-py3-none-any.whl"
        )

    logger.info("Loading UltraBERT unified model...")

    # Client auto-warms on init (warmup=True default, 3 rounds)
    # This replaces 9 separate models with 1 unified model
    client = Client(warmup=True, warmup_rounds=3, verbose=False)

    if not client.is_ready:
        raise RuntimeError("UltraBERT model failed to initialize")

    logger.info(
        f"UltraBERT ready: version={client.VERSION}, "
        f"backend={client.backend}, "
        f"capabilities={len(client.capabilities)}"
    )

    return client


# =============================================================================
# DEPRECATED LOADERS - Kept for backward compatibility but NOT USED
# All functionality is now provided by UltraBERT
# =============================================================================


def load_spacy(model_id: str, device: str = "cpu") -> Any:
    """DEPRECATED: Use UltraBERT instead. Kept for backward compatibility."""
    logger.warning(f"load_spacy() is DEPRECATED. UltraBERT provides NER. " f"Requested: {model_id}")
    import spacy

    return spacy.load(model_id)


def load_vader(model_id: str, device: str = "cpu") -> Any:
    """DEPRECATED: Use UltraBERT sentiment instead."""
    logger.warning("load_vader() is DEPRECATED. Use UltraBERT sentiment.")
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

    return SentimentIntensityAnalyzer()


def load_sentence_transformer(model_id: str, device: str = "cpu") -> Any:
    """DEPRECATED: Use UltraBERT embedding instead."""
    logger.warning("load_sentence_transformer() is DEPRECATED. Use UltraBERT embedding.")
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(model_id, device=device)


def load_transformers_pipeline(model_id: str, device: str = "cpu") -> Any:
    """DEPRECATED: Use UltraBERT instead."""
    logger.warning("load_transformers_pipeline() is DEPRECATED. Use UltraBERT.")
    from transformers import pipeline

    device_arg = -1 if device == "cpu" else 0
    return pipeline("text-classification", model=model_id, device=device_arg)


def load_zero_shot_classifier(model_id: str, device: str = "cpu") -> Any:
    """DEPRECATED: Use UltraBERT intent/ingress instead."""
    logger.warning("load_zero_shot_classifier() is DEPRECATED. Use UltraBERT.")
    from transformers import pipeline

    device_arg = -1 if device == "cpu" else 0
    return pipeline("zero-shot-classification", model=model_id, device=device_arg)


def load_ner_model(model_id: str, device: str = "cpu") -> Any:
    """DEPRECATED: Use UltraBERT NER instead."""
    logger.warning("load_ner_model() is DEPRECATED. Use UltraBERT NER.")
    if model_id.startswith("spacy:"):
        return load_spacy(model_id.split(":", 1)[1], device)
    from transformers import pipeline

    device_arg = -1 if device == "cpu" else 0
    return pipeline("ner", model=model_id, device=device_arg, aggregation_strategy="simple")


def load_embedding_model(model_id: str, device: str = "cpu") -> Any:
    """DEPRECATED: Use UltraBERT embedding instead."""
    logger.warning("load_embedding_model() is DEPRECATED. Use UltraBERT embedding.")
    return load_sentence_transformer(model_id, device)


def load_go_emotions(model_id: str, device: str = "cpu") -> Any:
    """DEPRECATED: Use UltraBERT emotions instead."""
    logger.warning("load_go_emotions() is DEPRECATED. Use UltraBERT emotions.")
    from transformers import pipeline

    device_arg = -1 if device == "cpu" else 0
    return pipeline("text-classification", model=model_id, top_k=5, device=device_arg)


def load_clinical_safety(model_id: str, device: str = "cpu") -> Any:
    """DEPRECATED: Use UltraBERT safety_familyos instead."""
    logger.warning("load_clinical_safety() is DEPRECATED. Use UltraBERT safety.")
    from transformers import pipeline

    device_arg = -1 if device == "cpu" else 0
    return pipeline("text-classification", model=model_id, device=device_arg)
