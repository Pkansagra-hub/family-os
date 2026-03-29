"""
Performance benchmark for R1 importance scoring (5.O.2.3).

AC: Score 100 events in < 30ms, 1000 events in < 300ms.
    Timing assertions pass on CI.

Uses production ImportanceScorer.compute_importance_score() directly
with representative event mixes from POC scenarios.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import pytest

from k0.modules.consolidation.algorithms.importance_scorer import (
    ImportanceScorer,
    ImportanceWeights,
)


@dataclass
class PerfEventState:
    """Minimal event state for performance testing."""

    event_id: str = "perf-event"
    sentiment_score: float = 0.5
    affect_valence: float = 0.3
    affect_arousal: float = 0.4
    surprise_level: float = 0.3
    num_participants: int = 2
    social_intimacy: str = "MEDIUM"
    content_type: str = "message"
    intent_label: str = "casual_chat"
    novelty: str = "EXPECTED"
    elaboration_depth: str = "DISCUSSED"
    temporal_orientation: str = "PAST"
    identity_relevance: float = 0.3
    source_reliability: float = 0.95
    source_type: str = "user_stated"
    narrative_is_goal_event: bool = False
    narrative_arc_position: str = "EXPOSITION"
    memory_tier: str = "routine"
    timestamp: int = 0


def _make_event_batch(n: int, now_ms: int) -> list[PerfEventState]:
    """Create n diverse events by cycling through representative patterns."""
    patterns = [
        # Critical milestone (high score)
        dict(
            sentiment_score=0.95,
            affect_valence=0.90,
            affect_arousal=0.85,
            surprise_level=0.80,
            num_participants=4,
            social_intimacy="HIGH",
            content_type="milestone",
            intent_label="share_news",
            novelty="SURPRISING",
            elaboration_depth="DEEPLY_PROCESSED",
            identity_relevance=0.90,
        ),
        # Routine low (low score)
        dict(
            sentiment_score=0.10,
            affect_valence=0.0,
            affect_arousal=0.10,
            surprise_level=0.0,
            num_participants=1,
            social_intimacy="LOW",
            content_type="routine",
            intent_label="other",
            novelty="ROUTINE",
            elaboration_depth="MENTION",
            identity_relevance=0.0,
        ),
        # Medium social event
        dict(
            sentiment_score=0.50,
            affect_valence=0.40,
            affect_arousal=0.30,
            surprise_level=0.20,
            num_participants=3,
            social_intimacy="MEDIUM",
            content_type="message",
            intent_label="casual_chat",
            novelty="EXPECTED",
            elaboration_depth="DISCUSSED",
            identity_relevance=0.30,
        ),
        # High-emotion event
        dict(
            sentiment_score=-0.80,
            affect_valence=-0.70,
            affect_arousal=0.90,
            surprise_level=0.90,
            num_participants=2,
            social_intimacy="HIGH",
            content_type="message",
            intent_label="express_feeling",
            novelty="SURPRISING",
            elaboration_depth="ELABORATED",
            identity_relevance=0.60,
        ),
        # Planning event
        dict(
            sentiment_score=0.30,
            affect_valence=0.20,
            affect_arousal=0.20,
            surprise_level=0.10,
            num_participants=2,
            social_intimacy="MEDIUM",
            content_type="calendar",
            intent_label="make_plan",
            novelty="EXPECTED",
            elaboration_depth="DISCUSSED",
            temporal_orientation="FUTURE_COMMITMENT",
            identity_relevance=0.20,
        ),
    ]

    events = []
    for i in range(n):
        p = patterns[i % len(patterns)]
        events.append(
            PerfEventState(
                event_id=f"perf-{i:05d}",
                timestamp=now_ms,
                **p,
            )
        )
    return events


class TestR1PerformanceBenchmark:
    """
    Performance regression tests for ImportanceScorer.

    Thresholds are conservative (3x headroom) to avoid flakiness on CI.
    """

    @pytest.fixture
    def scorer(self) -> ImportanceScorer:
        return ImportanceScorer(space_id="perf-bench")

    @pytest.fixture
    def weights(self) -> ImportanceWeights:
        return ImportanceWeights()

    @pytest.fixture
    def now_ms(self) -> int:
        return int(time.time() * 1000)

    def test_100_events_under_30ms(
        self, scorer: ImportanceScorer, weights: ImportanceWeights, now_ms: int
    ) -> None:
        """Score 100 events in under 30ms."""
        events = _make_event_batch(100, now_ms)

        start = time.perf_counter()
        for event in events:
            scorer.compute_importance_score(event, weights, now_ms=now_ms)
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert elapsed_ms < 30.0, f"Scored 100 events in {elapsed_ms:.1f}ms (threshold: 30ms)"

    def test_1000_events_under_300ms(
        self, scorer: ImportanceScorer, weights: ImportanceWeights, now_ms: int
    ) -> None:
        """Score 1000 events in under 300ms."""
        events = _make_event_batch(1000, now_ms)

        start = time.perf_counter()
        for event in events:
            scorer.compute_importance_score(event, weights, now_ms=now_ms)
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert elapsed_ms < 300.0, f"Scored 1000 events in {elapsed_ms:.1f}ms (threshold: 300ms)"

    def test_per_event_latency_under_1ms(
        self, scorer: ImportanceScorer, weights: ImportanceWeights, now_ms: int
    ) -> None:
        """Average per-event latency should be under 1ms."""
        events = _make_event_batch(500, now_ms)

        start = time.perf_counter()
        for event in events:
            scorer.compute_importance_score(event, weights, now_ms=now_ms)
        elapsed_ms = (time.perf_counter() - start) * 1000
        avg_ms = elapsed_ms / 500

        assert avg_ms < 1.0, f"Average per-event latency {avg_ms:.3f}ms (threshold: 1ms)"

    def test_warmup_then_benchmark(
        self, scorer: ImportanceScorer, weights: ImportanceWeights, now_ms: int
    ) -> None:
        """Warmup pass followed by timed pass -- eliminates JIT/cache effects."""
        events = _make_event_batch(100, now_ms)

        # Warmup
        for event in events:
            scorer.compute_importance_score(event, weights, now_ms=now_ms)

        # Timed run
        start = time.perf_counter()
        for event in events:
            scorer.compute_importance_score(event, weights, now_ms=now_ms)
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert elapsed_ms < 30.0, f"Post-warmup: 100 events in {elapsed_ms:.1f}ms (threshold: 30ms)"

    def test_all_scores_valid_in_batch(
        self, scorer: ImportanceScorer, weights: ImportanceWeights, now_ms: int
    ) -> None:
        """Every event in a 1000-batch produces a valid score and breakdown."""
        events = _make_event_batch(1000, now_ms)

        for event in events:
            score, breakdown = scorer.compute_importance_score(event, weights, now_ms=now_ms)
            assert 0.0 <= score <= 1.0
            assert breakdown is not None
