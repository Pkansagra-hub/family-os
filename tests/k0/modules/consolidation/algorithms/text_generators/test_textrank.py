"""
Unit tests for TextRank summarization module.

GAP Reference: GAP_001_CROSS_LAYER_VECTOR_LINKING.md §4
Milestone: GAP_001_MILESTONE_2_SUMMARY_GENERATOR.md Issue 2.10
"""

from __future__ import annotations

import pytest

from k0.modules.consolidation.algorithms.text_generators.textrank import (
    SKLEARN_AVAILABLE,
    narrative_arc_summarize,
    textrank_summarize,
)


class TestTextRankSummarize:
    """Tests for textrank_summarize function."""

    def test_empty_input(self) -> None:
        """Test with empty input."""
        result = textrank_summarize([])
        assert result == []

    def test_fewer_texts_than_k(self) -> None:
        """Test when fewer texts than top_k."""
        texts = ["Text 1", "Text 2"]
        result = textrank_summarize(texts, top_k=5)
        assert result == texts

    def test_exact_k_texts(self) -> None:
        """Test when exactly top_k texts."""
        texts = ["A", "B", "C"]
        result = textrank_summarize(texts, top_k=3)
        assert result == texts

    def test_basic_summarization(self) -> None:
        """Test basic summarization with more texts than k."""
        texts = [
            "The family went to the park for a picnic",
            "They brought sandwiches and lemonade",
            "The children played on the swings",
            "Mom and dad relaxed under a tree",
            "Everyone had a wonderful time",
            "They decided to come back next week",
        ]
        result = textrank_summarize(texts, top_k=3)

        assert len(result) <= 3
        # Results should be from original texts
        for text in result:
            assert text in texts

    def test_preserves_order(self) -> None:
        """Test that results are returned in original order."""
        texts = [
            "First event happened",
            "Second event occurred",
            "Third thing took place",
            "Fourth activity ensued",
            "Fifth moment arrived",
        ]
        result = textrank_summarize(texts, top_k=3)

        # Get original indices
        indices = [texts.index(t) for t in result]
        # Should be sorted
        assert indices == sorted(indices)

    def test_handles_empty_strings(self) -> None:
        """Test handling of empty strings in input."""
        texts = ["Valid text", "", "Another valid text", "", "Third text"]
        result = textrank_summarize(texts, top_k=2)

        assert len(result) <= 2
        assert "" not in result

    def test_handles_whitespace_only(self) -> None:
        """Test handling of whitespace-only strings."""
        texts = ["Real content here", "   ", "More content", "\t\n"]
        result = textrank_summarize(texts, top_k=2)

        assert all(t.strip() for t in result)

    @pytest.mark.skipif(not SKLEARN_AVAILABLE, reason="sklearn not available")
    def test_sklearn_algorithm(self) -> None:
        """Test that sklearn algorithm produces reasonable results."""
        texts = [
            "Machine learning is transforming technology",
            "Deep learning uses neural networks",
            "AI systems can learn from data",
            "Natural language processing helps understand text",
            "Computer vision recognizes images",
            "Reinforcement learning teaches through rewards",
        ]
        result = textrank_summarize(texts, top_k=2)

        assert len(result) == 2
        assert all(t in texts for t in result)


class TestNarrativeArcSummarize:
    """Tests for narrative_arc_summarize function."""

    def test_empty_input(self) -> None:
        """Test with empty input."""
        result = narrative_arc_summarize([])
        assert result == []

    def test_single_text(self) -> None:
        """Test with single text."""
        texts = ["Only event"]
        result = narrative_arc_summarize(texts)
        assert result == texts

    def test_two_texts(self) -> None:
        """Test with two texts."""
        texts = ["First", "Second"]
        result = narrative_arc_summarize(texts)
        assert result == texts

    def test_three_texts(self) -> None:
        """Test with three texts."""
        texts = ["Start", "Middle", "End"]
        result = narrative_arc_summarize(texts)
        assert result == texts

    def test_basic_arc_without_emotions(self) -> None:
        """Test basic arc selection without emotion scores."""
        texts = [
            "Woke up early",
            "Had breakfast",
            "Went to work",
            "Had lunch meeting",
            "Finished project",
            "Came home",
            "Had dinner",
        ]
        result = narrative_arc_summarize(texts)

        # Should get first, middle, and last
        assert len(result) == 3
        assert result[0] == texts[0]  # First
        assert result[-1] == texts[-1]  # Last
        assert result[1] in texts[1:-1]  # Some middle

    def test_arc_with_emotion_scores(self) -> None:
        """Test arc selection with emotion scores."""
        texts = [
            "Started the day calmly",
            "Something exciting happened",
            "Peak emotional moment",
            "Things calmed down",
            "Ended peacefully",
        ]
        emotion_scores = [0.2, 0.5, 0.9, 0.4, 0.1]

        result = narrative_arc_summarize(texts, emotion_scores=emotion_scores)

        assert len(result) == 3
        assert result[0] == texts[0]  # First
        assert result[1] == texts[2]  # Peak emotion
        assert result[2] == texts[-1]  # Last

    def test_arc_with_mismatched_scores(self) -> None:
        """Test that mismatched emotion scores are handled."""
        texts = ["A", "B", "C", "D", "E"]
        # Wrong length - should fall back to middle selection
        emotion_scores = [0.1, 0.5, 0.9]

        result = narrative_arc_summarize(texts, emotion_scores=emotion_scores)

        assert len(result) == 3
        assert result[0] == texts[0]

    def test_arc_no_duplicates(self) -> None:
        """Test that arc doesn't contain duplicates."""
        texts = ["Only unique", "Another unique", "Third unique", "Fourth unique"]
        result = narrative_arc_summarize(texts)

        assert len(result) == len(set(result))
