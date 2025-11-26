"""
Model Loaders - Factory functions for loading ML models.

This module provides standardized loader functions for each model type.
Loaders are referenced by path in ModelSpec and called by ModelRegistry.

Related:
- k0/runtime/model_registry.py: Uses these loaders
- k0/config/models.yaml: References loader paths

Issue: 1.1.1 - Unified Model Registry
Status: IMPLEMENTED
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def load_spacy(model_id: str, device: str = "cpu") -> Any:
    """
    Load a spaCy model.

    Args:
        model_id: spaCy model name (e.g., "en_core_web_sm", "en_core_web_lg")
        device: Device to load on (cpu/cuda)

    Returns:
        spaCy Language object
    """
    import spacy

    logger.debug(f"Loading spaCy model: {model_id}")

    # Load model
    nlp = spacy.load(model_id)

    # Enable GPU if requested and available
    if device == "cuda":
        try:
            spacy.require_gpu()
            logger.info(f"spaCy GPU enabled for {model_id}")
        except Exception as e:
            logger.warning(f"spaCy GPU not available: {e}")

    return nlp


def load_vader(model_id: str, device: str = "cpu") -> Any:
    """
    Load VADER sentiment analyzer.

    Args:
        model_id: Ignored (VADER has single model)
        device: Ignored (VADER is CPU-only)

    Returns:
        SentimentIntensityAnalyzer instance
    """
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

    logger.debug("Loading VADER sentiment analyzer")
    return SentimentIntensityAnalyzer()


def load_sentence_transformer(model_id: str, device: str = "cpu") -> Any:
    """
    Load a sentence-transformers model.

    Args:
        model_id: Model name (e.g., "all-MiniLM-L6-v2")
        device: Device to load on (cpu/cuda)

    Returns:
        SentenceTransformer model
    """
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        raise ImportError(
            "sentence-transformers not installed. Install with: pip install sentence-transformers"
        )

    logger.debug(f"Loading sentence transformer: {model_id}")

    model = SentenceTransformer(model_id, device=device)

    return model


def load_transformers_pipeline(model_id: str, device: str = "cpu") -> Any:
    """
    Load a HuggingFace transformers pipeline.

    Args:
        model_id: Pipeline task or model name
        device: Device to load on (cpu/cuda)

    Returns:
        Transformers pipeline object
    """
    try:
        from transformers import pipeline
    except ImportError:
        raise ImportError("transformers not installed. Install with: pip install transformers")

    logger.debug(f"Loading transformers pipeline: {model_id}")

    # Determine device index
    device_arg = -1 if device == "cpu" else 0

    # Handle different model_id formats:
    # "sentiment-analysis" -> task name
    # "distilbert-base-uncased-finetuned-sst-2-english" -> model name
    if "-analysis" in model_id or model_id in ("ner", "sentiment", "text-classification"):
        pipe = pipeline(model_id, device=device_arg)
    else:
        pipe = pipeline("text-classification", model=model_id, device=device_arg)

    return pipe


def load_zero_shot_classifier(model_id: str, device: str = "cpu") -> Any:
    """
    Load a zero-shot classification model.

    Args:
        model_id: Model name (e.g., "facebook/bart-large-mnli")
        device: Device to load on (cpu/cuda)

    Returns:
        Zero-shot classification pipeline
    """
    try:
        from transformers import pipeline
    except ImportError:
        raise ImportError("transformers not installed. Install with: pip install transformers")

    logger.debug(f"Loading zero-shot classifier: {model_id}")

    device_arg = -1 if device == "cpu" else 0

    classifier = pipeline(
        "zero-shot-classification",
        model=model_id,
        device=device_arg,
    )

    return classifier


def load_ner_model(model_id: str, device: str = "cpu") -> Any:
    """
    Load a named entity recognition model.

    Args:
        model_id: Model name or "spacy:en_core_web_sm"
        device: Device to load on

    Returns:
        NER model (spaCy or transformers)
    """
    if model_id.startswith("spacy:"):
        # Use spaCy for NER
        spacy_model = model_id.split(":", 1)[1]
        return load_spacy(spacy_model, device)
    else:
        # Use transformers NER
        try:
            from transformers import pipeline
        except ImportError:
            raise ImportError("transformers not installed")

        device_arg = -1 if device == "cpu" else 0
        return pipeline("ner", model=model_id, device=device_arg, aggregation_strategy="simple")


def load_embedding_model(model_id: str, device: str = "cpu") -> Any:
    """
    Load an embedding model.

    Args:
        model_id: Model name
        device: Device to load on

    Returns:
        Embedding model (sentence-transformers or HF)
    """
    # Prefer sentence-transformers for embeddings
    return load_sentence_transformer(model_id, device)
