"""
BERT-NER Adapter - Pretrained General NER for P03 Consolidation.

This module provides a wrapper around dslim/bert-base-NER for extracting
general entities (PERSON, ORG, LOC) during P03 nightly consolidation.

Architecture Decision:
- UltraBERT v2-checkpoint-18000 has ner_family trained but ner_general was only
  used for replay/distillation (no proper training). The ner_general head produces
  garbage entities like "Drove" (PERSON), "Fur" (ORG), "authentication" (PERSON).

- Solution: Use dslim/bert-base-NER (pretrained on CoNLL-2003) for general NER
  in P03's R4 phase. This model correctly extracts PERSON, ORG, LOC, MISC.

- Why P03 only: P02 is hot path (user chat). P03 is nightly batch. Running
  BERT-NER in P03 adds ~3.8ms/event but doesn't impact user-facing latency.
  Also better for future edge device deployment (no model during active hours).

Performance:
- Model load: ~2 seconds
- Inference: ~3.8ms per event (after warmup)
- Batch inference: ~1.5ms per event (batches of 16-32)
- Memory: ~400MB

Usage:
    from k0.modules.consolidation.algorithms.bert_ner_adapter import (
        get_bert_ner,
        BertNERResult,
    )

    # Single text extraction
    ner = get_bert_ner()
    results = ner.extract("Visited Golden Gate Bridge in San Francisco with Mike")
    # => [BertNERResult(text="Golden Gate Bridge", label="LOC", ...),
    #     BertNERResult(text="San Francisco", label="LOC", ...),
    #     BertNERResult(text="Mike", label="PER", ...)]

    # Batch extraction (more efficient)
    batch_results = ner.extract_batch([
        "Mike went to Google HQ",
        "Emma visited Paris last summer",
    ])

Author: K0 Architecture Team
Date: 2025-01-09
"""

from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

# Singleton instance
_bert_ner_instance: "BertNERAdapter | None" = None
_bert_ner_lock = threading.Lock()


@dataclass
class BertNERResult:
    """Result from BERT-NER extraction.

    Compatible with UltraBERT entity format for easy merging.
    """

    text: str  # Entity text span (e.g., "San Francisco")
    label: str  # CoNLL label: PER, ORG, LOC, MISC
    start: int  # Character start position
    end: int  # Character end position
    score: float  # Confidence score (0-1)

    def to_ultrabert_format(self) -> dict[str, Any]:
        """Convert to UltraBERT ner_general format for entity_extractor.

        Maps CoNLL labels to UltraBERT labels:
        - PER -> PERSON
        - ORG -> ORG (same)
        - LOC -> LOC (same)
        - MISC -> CONCEPT
        """
        label_map = {
            "PER": "PERSON",
            "ORG": "ORG",
            "LOC": "LOC",
            "MISC": "CONCEPT",
        }
        return {
            "text": self.text,
            "label": label_map.get(self.label, self.label),
            "start_token": self.start,  # Using char position as proxy
            "end_token": self.end,
            "score": self.score,
        }


@dataclass
class BertNERMetrics:
    """Metrics for BERT-NER operations."""

    model_loaded: bool = False
    load_time_ms: float = 0.0
    inference_count: int = 0
    batch_count: int = 0
    total_inference_time_ms: float = 0.0
    entities_extracted: int = 0
    errors: int = 0


class BertNERAdapter:
    """Adapter for dslim/bert-base-NER pretrained model.

    This replaces UltraBERT's broken ner_general head with a properly
    trained general NER model for P03 consolidation.
    """

    MODEL_NAME = "dslim/bert-base-NER"

    def __init__(self, device: str = "auto") -> None:
        """Initialize BERT-NER adapter.

        Args:
            device: Device to run model on. "auto" uses GPU if available.
                    Options: "auto", "cuda", "cpu", "cuda:0", etc.
        """
        self._pipeline: Any = None
        self._device = device
        self._metrics = BertNERMetrics()
        self._lock = threading.Lock()

    @property
    def metrics(self) -> BertNERMetrics:
        """Get current metrics."""
        return self._metrics

    def _ensure_loaded(self) -> bool:
        """Ensure model is loaded. Thread-safe lazy loading.

        Returns:
            True if model is ready, False if loading failed.
        """
        if self._pipeline is not None:
            return True

        with self._lock:
            # Double-check after acquiring lock
            if self._pipeline is not None:
                return True

            try:
                start = time.perf_counter()

                # Import here to avoid startup cost if not used
                from transformers import pipeline

                # Determine device
                device = self._device
                if device == "auto":
                    import torch

                    device = 0 if torch.cuda.is_available() else -1
                elif device == "cuda":
                    device = 0
                elif device == "cpu":
                    device = -1
                elif device.startswith("cuda:"):
                    device = int(device.split(":")[1])
                else:
                    device = -1

                self._pipeline = pipeline(
                    "ner",  # type: ignore[arg-type]  # Valid task, type stubs incomplete
                    model=self.MODEL_NAME,
                    aggregation_strategy="simple",  # Merge B-I-O tokens
                    device=device,
                )

                self._metrics.load_time_ms = (time.perf_counter() - start) * 1000
                self._metrics.model_loaded = True

                logger.info(
                    "BERT-NER model loaded",
                    extra={
                        "model": self.MODEL_NAME,
                        "device": device,
                        "load_time_ms": round(self._metrics.load_time_ms, 2),
                    },
                )

                # Warmup
                _ = self._pipeline("warmup")

                return True

            except Exception as e:
                logger.error(f"Failed to load BERT-NER model: {e}")
                self._metrics.errors += 1
                return False

    def extract(self, text: str) -> list[BertNERResult]:
        """Extract general entities from text.

        Args:
            text: Input text to analyze.

        Returns:
            List of BertNERResult entities.
        """
        if not text or not text.strip():
            return []

        if not self._ensure_loaded():
            return []

        try:
            start = time.perf_counter()

            raw_results = self._pipeline(text)

            self._metrics.inference_count += 1
            self._metrics.total_inference_time_ms += (time.perf_counter() - start) * 1000

            results = []
            for r in raw_results:
                # Handle aggregation_strategy="simple" output format
                entity = BertNERResult(
                    text=r.get("word", r.get("entity_group", "")),
                    label=r.get("entity_group", r.get("entity", "")),
                    start=r.get("start", 0),
                    end=r.get("end", 0),
                    score=r.get("score", 0.0),
                )
                results.append(entity)

            self._metrics.entities_extracted += len(results)
            return results

        except Exception as e:
            logger.error(f"BERT-NER extraction failed: {e}")
            self._metrics.errors += 1
            return []

    def extract_batch(self, texts: list[str]) -> list[list[BertNERResult]]:
        """Extract entities from multiple texts in batch.

        Batch processing is more efficient than individual calls.

        Args:
            texts: List of input texts to analyze.

        Returns:
            List of entity lists, one per input text.
        """
        if not texts:
            return []

        # Filter empty texts but track positions
        valid_texts = []
        valid_indices = []
        for i, t in enumerate(texts):
            if t and t.strip():
                valid_texts.append(t)
                valid_indices.append(i)

        if not valid_texts:
            return [[] for _ in texts]

        if not self._ensure_loaded():
            return [[] for _ in texts]

        try:
            start = time.perf_counter()

            # Run batch inference
            batch_results = self._pipeline(valid_texts)

            self._metrics.batch_count += 1
            self._metrics.inference_count += len(valid_texts)
            self._metrics.total_inference_time_ms += (time.perf_counter() - start) * 1000

            # Parse results
            parsed_results: list[list[BertNERResult]] = [[] for _ in texts]

            for idx, raw_list in zip(valid_indices, batch_results):
                entities = []
                for r in raw_list:
                    entity = BertNERResult(
                        text=r.get("word", r.get("entity_group", "")),
                        label=r.get("entity_group", r.get("entity", "")),
                        start=r.get("start", 0),
                        end=r.get("end", 0),
                        score=r.get("score", 0.0),
                    )
                    entities.append(entity)
                    self._metrics.entities_extracted += 1
                parsed_results[idx] = entities

            return parsed_results

        except Exception as e:
            logger.error(f"BERT-NER batch extraction failed: {e}")
            self._metrics.errors += 1
            return [[] for _ in texts]

    def to_ultrabert_format(self, results: list[BertNERResult]) -> dict[str, Any]:
        """Convert BERT-NER results to UltraBERT ner_general format.

        This allows direct use in UltraBERTEntityExtractor.extract_from_ultrabert()

        Args:
            results: List of BERT-NER results.

        Returns:
            Dict in UltraBERT ner_general format.
        """
        return {
            "entities": [r.to_ultrabert_format() for r in results],
            "source": "bert-base-NER",
        }


def get_bert_ner() -> BertNERAdapter:
    """Get the singleton BERT-NER adapter instance.

    Thread-safe singleton that lazily loads the model on first use.

    Returns:
        BertNERAdapter singleton instance.
    """
    global _bert_ner_instance

    if _bert_ner_instance is not None:
        return _bert_ner_instance

    with _bert_ner_lock:
        if _bert_ner_instance is not None:
            return _bert_ner_instance

        device = os.getenv("K0_BERT_NER_DEVICE", "auto")
        _bert_ner_instance = BertNERAdapter(device=device)

        # Optionally preload
        if os.getenv("K0_BERT_NER_PRELOAD", "0") in {"1", "true", "True"}:
            _bert_ner_instance._ensure_loaded()

        return _bert_ner_instance


def reset_bert_ner() -> None:
    """Reset the singleton instance. For testing only."""
    global _bert_ner_instance
    with _bert_ner_lock:
        _bert_ner_instance = None
