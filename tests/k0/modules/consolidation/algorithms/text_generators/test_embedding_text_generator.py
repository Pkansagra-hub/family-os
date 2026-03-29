"""
Unit tests for EmbeddingTextGenerator base class.

GAP Reference: GAP_001_CROSS_LAYER_VECTOR_LINKING.md §4
Milestone: GAP_001_MILESTONE_2_SUMMARY_GENERATOR.md Issue 2.10
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

import pytest

from k0.modules.consolidation.algorithms.embedding_text_generator import (
    EmbeddingTextGenerator,
    GeneratedText,
    TextGenerationStrategy,
)


class ConcreteGenerator(EmbeddingTextGenerator):
    """Concrete implementation for testing base class methods."""

    @property
    def layer(self) -> str:
        return "test_layer"

    def generate(
        self,
        record_data: Dict[str, Any],
        source_texts: Optional[List[str]] = None,
    ) -> GeneratedText:
        """Simple implementation for testing."""
        texts = source_texts or []
        text = self._concatenate_texts(texts)
        return GeneratedText(
            embedding_text=text,
            source_texts_json=self._source_texts_to_json(texts),
            layer=self.layer,
            record_id=str(record_data.get("id", "")),
        )


class TestGeneratedText:
    """Tests for GeneratedText dataclass."""

    def test_basic_creation(self) -> None:
        """Test basic GeneratedText creation."""
        result = GeneratedText(
            embedding_text="Test text",
            source_texts_json='["source1"]',
            strategy_used=TextGenerationStrategy.TEMPLATE,
            layer="st_epi",
            record_id="ep_123",
        )

        assert result.embedding_text == "Test text"
        assert result.source_texts_json == '["source1"]'
        assert result.strategy_used == TextGenerationStrategy.TEMPLATE
        assert result.layer == "st_epi"
        assert result.record_id == "ep_123"

    def test_token_count_auto_computed(self) -> None:
        """Test that token count is auto-computed if not provided."""
        result = GeneratedText(embedding_text="This is a test sentence")
        # Rough estimate: 23 chars / 4 = 5 tokens
        assert result.token_count == 5

    def test_token_count_explicit(self) -> None:
        """Test that explicit token count is preserved."""
        result = GeneratedText(
            embedding_text="Test",
            token_count=100,
        )
        assert result.token_count == 100

    def test_empty_text(self) -> None:
        """Test with empty embedding text."""
        result = GeneratedText(embedding_text="")
        assert result.token_count == 0


class TestTextGenerationStrategy:
    """Tests for TextGenerationStrategy enum."""

    def test_enum_values(self) -> None:
        """Test all strategy values exist."""
        assert TextGenerationStrategy.TEMPLATE == "template"
        assert TextGenerationStrategy.CONCATENATE == "concatenate"
        assert TextGenerationStrategy.TEXTRANK == "textrank"
        assert TextGenerationStrategy.NARRATIVE_ARC == "narrative_arc"

    def test_string_conversion(self) -> None:
        """Test string conversion."""
        assert str(TextGenerationStrategy.TEMPLATE) == "TextGenerationStrategy.TEMPLATE"
        assert TextGenerationStrategy.TEMPLATE.value == "template"


class TestEmbeddingTextGenerator:
    """Tests for EmbeddingTextGenerator base class methods."""

    @pytest.fixture
    def generator(self) -> ConcreteGenerator:
        """Create a concrete generator instance."""
        return ConcreteGenerator()

    def test_truncate_short_text(self, generator: ConcreteGenerator) -> None:
        """Test truncate with text shorter than max."""
        text = "Short text"
        result = generator._truncate(text, max_length=100)
        assert result == text

    def test_truncate_long_text(self, generator: ConcreteGenerator) -> None:
        """Test truncate with text longer than max."""
        text = "A" * 100
        result = generator._truncate(text, max_length=50)
        assert len(result) == 50
        assert result.endswith("...")

    def test_clean_text_whitespace(self, generator: ConcreteGenerator) -> None:
        """Test clean_text normalizes whitespace."""
        text = "  Multiple   spaces   here  "
        result = generator._clean_text(text)
        assert result == "Multiple spaces here"

    def test_clean_text_empty(self, generator: ConcreteGenerator) -> None:
        """Test clean_text with empty string."""
        assert generator._clean_text("") == ""
        assert generator._clean_text(None) == ""  # type: ignore

    def test_parse_json_field_list(self, generator: ConcreteGenerator) -> None:
        """Test parsing JSON list field."""
        data = {"items": '["a", "b", "c"]'}
        result = generator._parse_json_field(data, "items")
        assert result == ["a", "b", "c"]

    def test_parse_json_field_dict(self, generator: ConcreteGenerator) -> None:
        """Test parsing JSON dict field."""
        data = {"meta": '{"key": "value"}'}
        result = generator._parse_json_field(data, "meta", default={})
        assert result == {"key": "value"}

    def test_parse_json_field_already_parsed(self, generator: ConcreteGenerator) -> None:
        """Test parsing already-parsed field."""
        data = {"items": ["a", "b", "c"]}
        result = generator._parse_json_field(data, "items")
        assert result == ["a", "b", "c"]

    def test_parse_json_field_missing(self, generator: ConcreteGenerator) -> None:
        """Test parsing missing field."""
        data: Dict[str, Any] = {}
        result = generator._parse_json_field(data, "missing")
        assert result == []

    def test_parse_json_field_invalid(self, generator: ConcreteGenerator) -> None:
        """Test parsing invalid JSON."""
        data = {"bad": "not valid json {"}
        result = generator._parse_json_field(data, "bad")
        assert result == []

    def test_deduplicate_texts(self, generator: ConcreteGenerator) -> None:
        """Test text deduplication."""
        texts = ["Hello", "World", "hello", "HELLO", "World"]
        result = generator._deduplicate_texts(texts)
        # Case-insensitive dedup, preserves first occurrence
        assert result == ["Hello", "World"]

    def test_deduplicate_texts_empty(self, generator: ConcreteGenerator) -> None:
        """Test deduplication with empty strings."""
        texts = ["", "Hello", "", "World", ""]
        result = generator._deduplicate_texts(texts)
        assert result == ["Hello", "World"]

    def test_source_texts_to_json(self, generator: ConcreteGenerator) -> None:
        """Test source texts JSON conversion."""
        texts = ["Text 1", "Text 2"]
        result = generator._source_texts_to_json(texts)
        assert result == '["Text 1", "Text 2"]'

    def test_source_texts_to_json_empty(self, generator: ConcreteGenerator) -> None:
        """Test source texts JSON with empty list."""
        assert generator._source_texts_to_json([]) == "[]"

    def test_concatenate_texts(self, generator: ConcreteGenerator) -> None:
        """Test text concatenation."""
        texts = ["First", "Second", "Third"]
        result = generator._concatenate_texts(texts)
        assert result == "First. Second. Third"

    def test_concatenate_texts_with_limit(self, generator: ConcreteGenerator) -> None:
        """Test concatenation with limit."""
        texts = ["A", "B", "C", "D", "E"]
        result = generator._concatenate_texts(texts, max_texts=3)
        assert result == "A. B. C (+2 more)"

    def test_concatenate_texts_custom_separator(self, generator: ConcreteGenerator) -> None:
        """Test concatenation with custom separator."""
        texts = ["A", "B", "C"]
        result = generator._concatenate_texts(texts, separator="; ")
        assert result == "A; B; C"

    def test_generate_method(self, generator: ConcreteGenerator) -> None:
        """Test the concrete generate implementation."""
        result = generator.generate(
            record_data={"id": "test_123"},
            source_texts=["Event 1", "Event 2"],
        )

        assert isinstance(result, GeneratedText)
        assert result.layer == "test_layer"
        assert result.record_id == "test_123"
        assert "Event 1" in result.embedding_text
        assert "Event 2" in result.embedding_text
        assert json.loads(result.source_texts_json) == ["Event 1", "Event 2"]
