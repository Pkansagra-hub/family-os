"""
EmbeddingTextGenerator — GAP-001 Milestone 2

Generates embeddable text for truth layers without LLM.
Uses template-based and extractive summarization strategies.

This module provides:
    - EmbeddingTextGenerator: Abstract base class for layer-specific generators
    - GeneratedText: Result dataclass with embedding text and metadata
    - TextGenerationStrategy: Enum for generation strategies

GAP Reference: GAP_001_CROSS_LAYER_VECTOR_LINKING.md §4
Milestone: GAP_001_MILESTONE_2_SUMMARY_GENERATOR.md Issue 2.1

Strategy Overview:
    - TEMPLATE: Fill placeholders from structured columns (patterns, routines)
    - CONCATENATE: Join source texts with deduplication (≤3 events)
    - TEXTRANK: Extractive summarization using PageRank (>5 events)
    - NARRATIVE_ARC: First + peak emotion + last (long episodes)

TIMESTAMP CONVENTION: All timestamps use MILLISECONDS since Unix epoch.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional


class TextGenerationStrategy(str, Enum):
    """
    Strategy for generating embedding text.

    TEMPLATE: Fill placeholders from structured columns (best for patterns, routines)
    CONCATENATE: Join source texts with deduplication (best for ≤3 events)
    TEXTRANK: Extractive summarization using PageRank (best for >5 events)
    NARRATIVE_ARC: First + peak emotion + last (best for long episodes)
    """

    TEMPLATE = "template"
    CONCATENATE = "concatenate"
    TEXTRANK = "textrank"
    NARRATIVE_ARC = "narrative_arc"


@dataclass
class GeneratedText:
    """
    Result of text generation for a truth layer record.

    Attributes:
        embedding_text: Text to embed with UltraBERT (stored in embedding_text column)
        source_texts_json: JSON array of original source texts (stored in source_texts_json column)
        strategy_used: Which generation strategy was applied
        token_count: Approximate token count (for size limits)
        layer: Target layer name (st_epi, st_sem, etc.)
        record_id: ID of the record being generated for (for logging)
    """

    embedding_text: str
    source_texts_json: str = "[]"
    strategy_used: TextGenerationStrategy = TextGenerationStrategy.TEMPLATE
    token_count: int = 0
    layer: str = ""
    record_id: str = ""

    def __post_init__(self) -> None:
        """Compute token count if not provided."""
        if self.token_count == 0 and self.embedding_text:
            # Rough approximation: 1 token ≈ 4 chars for English
            self.token_count = len(self.embedding_text) // 4


class EmbeddingTextGenerator(ABC):
    """
    Abstract base class for layer-specific text generators.

    Each truth layer has specific structured data that should be
    converted to embeddable text. Subclasses implement layer-specific
    templates and summarization logic.

    Usage:
        generator = EpisodicTextGenerator()
        result = generator.generate(
            record_data={"episode_id": "ep_123", ...},
            source_texts=["Had dinner with mom", "At Thai restaurant"],
        )
        # result.embedding_text → "Friday evening episode..."
        # result.source_texts_json → '["Had dinner with mom", ...]'
    """

    # Maximum embedding text length (UltraBERT handles 512 tokens)
    MAX_TEXT_LENGTH = 2000  # chars ≈ 500 tokens

    # Threshold for switching to TextRank summarization
    TEXTRANK_THRESHOLD = 5  # events

    @abstractmethod
    def generate(
        self,
        record_data: Dict[str, Any],
        source_texts: Optional[List[str]] = None,
    ) -> GeneratedText:
        """
        Generate embedding text for a record.

        Args:
            record_data: Dictionary of column values from the truth layer record
            source_texts: Optional list of original source event texts

        Returns:
            GeneratedText with embedding_text and metadata
        """
        ...

    @property
    @abstractmethod
    def layer(self) -> str:
        """Target layer name (st_epi, st_sem, etc.)."""
        ...

    def _truncate(self, text: str, max_length: Optional[int] = None) -> str:
        """Truncate text to max length with ellipsis."""
        max_len = max_length or self.MAX_TEXT_LENGTH
        if len(text) <= max_len:
            return text
        return text[: max_len - 3] + "..."

    def _clean_text(self, text: str) -> str:
        """Clean and normalize text for embedding."""
        if not text:
            return ""
        # Remove excessive whitespace
        text = " ".join(text.split())
        # Remove control characters
        text = "".join(c for c in text if c.isprintable() or c in "\n\t")
        return text.strip()

    def _parse_json_field(
        self,
        record_data: Dict[str, Any],
        field_name: str,
        default: Any = None,
    ) -> Any:
        """Safely parse a JSON field from record data."""
        value = record_data.get(field_name)
        if value is None:
            return default if default is not None else []

        if isinstance(value, (list, dict)):
            return value

        if isinstance(value, str):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return default if default is not None else []

        return default if default is not None else []

    def _deduplicate_texts(self, texts: List[str]) -> List[str]:
        """Remove duplicate texts while preserving order."""
        seen = set()
        result = []
        for text in texts:
            normalized = text.lower().strip()
            if normalized and normalized not in seen:
                seen.add(normalized)
                result.append(text)
        return result

    def _source_texts_to_json(self, texts: List[str]) -> str:
        """Convert source texts list to JSON string."""
        if not texts:
            return "[]"
        return json.dumps(texts, ensure_ascii=False)

    def _concatenate_texts(
        self,
        texts: List[str],
        separator: str = ". ",
        max_texts: int = 5,
    ) -> str:
        """Concatenate texts with separator and limit."""
        if not texts:
            return ""
        unique_texts = self._deduplicate_texts(texts)
        limited = unique_texts[:max_texts]
        result = separator.join(limited)
        if len(unique_texts) > max_texts:
            result += f" (+{len(unique_texts) - max_texts} more)"
        return result
