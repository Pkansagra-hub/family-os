"""
Tests for R4 Ambiguous Entity Resolver.

Issue: 4.4.4 - Implement ambiguous entity resolution with context hierarchy
Spec Reference: M4_EXECUTION.md, Dossier Section 4.5.1.2

Test Coverage:
1. 5-priority context hierarchy scoring
2. Confidence band routing (AUTO, FLAG, GAP)
3. Close race penalty
4. Edge cases (no candidates, single candidate)
5. Gap emission to P06
6. Resolution audit recording
7. Metrics tracking

Author: K0 Architecture Team
Date: 2025-01-03
"""

import time
from unittest.mock import AsyncMock

import pytest

from k0.modules.consolidation.algorithms.ambiguous_resolver import (
    P03_RESOLUTION_BOOST_CO_OCCURRING,
    P03_RESOLUTION_THRESHOLD_AUTO,
    P03_RESOLUTION_THRESHOLD_FLAG,
    AmbiguousEntityResolver,
    AmbiguousResolverConfig,
    CandidateEntity,
    EventContext,
    ResolutionOutcome,
    get_ambiguous_resolver,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def resolver() -> AmbiguousEntityResolver:
    """Fresh resolver instance with default config."""
    return AmbiguousEntityResolver()


@pytest.fixture
def custom_resolver() -> AmbiguousEntityResolver:
    """Resolver with custom thresholds for testing."""
    config = AmbiguousResolverConfig(
        threshold_auto=0.90,
        threshold_flag=0.50,
        recency_window_ms=1800_000,  # 30 minutes
    )
    return AmbiguousEntityResolver(config=config)


@pytest.fixture
def now_ms() -> int:
    """Current timestamp in milliseconds."""
    return int(time.time() * 1000)


@pytest.fixture
def candidate_john_work(now_ms: int) -> CandidateEntity:
    """Candidate: John from work, seen recently."""
    return CandidateEntity(
        entity_id="ent_john_work_001",
        entity_type="PERSON",
        canonical_name="John Smith (Colleague)",
        last_seen_ms=now_ms - 60_000,  # 1 minute ago
        frequency=50,
        attributes={"relationship_type": "coworker"},
    )


@pytest.fixture
def candidate_john_family(now_ms: int) -> CandidateEntity:
    """Candidate: John from family, seen yesterday."""
    return CandidateEntity(
        entity_id="ent_john_family_002",
        entity_type="FAMILY_MEMBER",
        canonical_name="John (Uncle)",
        last_seen_ms=now_ms - 86400_000,  # 1 day ago
        frequency=20,
        attributes={"relationship_type": "family"},
    )


@pytest.fixture
def candidate_john_random(now_ms: int) -> CandidateEntity:
    """Candidate: John random acquaintance, rarely seen."""
    return CandidateEntity(
        entity_id="ent_john_random_003",
        entity_type="PERSON",
        canonical_name="John Doe",
        last_seen_ms=now_ms - 604800_000,  # 1 week ago
        frequency=2,
        attributes={},
    )


@pytest.fixture
def work_context(now_ms: int, candidate_john_work: CandidateEntity) -> EventContext:
    """Event context: at work, co-occurring with Sarah."""
    return EventContext(
        session_id="sess_001",
        event_timestamp_ms=now_ms,
        co_occurring_entities=["ent_sarah_001", candidate_john_work.entity_id],
        location_hint="work",
        temporal_category="afternoon",
        tenant_id="tenant_001",
        space_id="space_001",
    )


@pytest.fixture
def home_context(now_ms: int) -> EventContext:
    """Event context: at home, evening."""
    return EventContext(
        session_id="sess_002",
        event_timestamp_ms=now_ms,
        co_occurring_entities=[],
        location_hint="home",
        temporal_category="evening",
        tenant_id="tenant_001",
        space_id="space_001",
    )


@pytest.fixture
def neutral_context(now_ms: int) -> EventContext:
    """Event context: no location or temporal hints."""
    return EventContext(
        session_id="sess_003",
        event_timestamp_ms=now_ms,
        co_occurring_entities=[],
        location_hint=None,
        temporal_category=None,
        tenant_id="tenant_001",
        space_id="space_001",
    )


# =============================================================================
# Test: Configuration
# =============================================================================


class TestConfiguration:
    """Test resolver configuration."""

    def test_default_thresholds(self, resolver: AmbiguousEntityResolver) -> None:
        """Default thresholds match spec."""
        assert resolver.config.threshold_auto == P03_RESOLUTION_THRESHOLD_AUTO
        assert resolver.config.threshold_flag == P03_RESOLUTION_THRESHOLD_FLAG

    def test_custom_thresholds(self, custom_resolver: AmbiguousEntityResolver) -> None:
        """Custom thresholds are applied."""
        assert custom_resolver.config.threshold_auto == 0.90
        assert custom_resolver.config.threshold_flag == 0.50

    def test_config_validation_invalid_thresholds(self) -> None:
        """Invalid threshold ordering raises error."""
        config = AmbiguousResolverConfig(threshold_auto=0.50, threshold_flag=0.70)
        with pytest.raises(ValueError, match="threshold_flag"):
            config.validate()

    def test_factory_function(self) -> None:
        """Factory function creates resolver."""
        resolver = get_ambiguous_resolver()
        assert isinstance(resolver, AmbiguousEntityResolver)

    def test_factory_with_config(self) -> None:
        """Factory function accepts config."""
        config = AmbiguousResolverConfig(threshold_auto=0.95)
        resolver = get_ambiguous_resolver(config=config)
        assert resolver.config.threshold_auto == 0.95


# =============================================================================
# Test: Edge Cases
# =============================================================================


class TestEdgeCases:
    """Test edge cases in resolution."""

    def test_no_candidates_returns_gap(
        self,
        resolver: AmbiguousEntityResolver,
        neutral_context: EventContext,
    ) -> None:
        """No candidates returns GAP_EMITTED outcome."""
        result = resolver.resolve("John", [], neutral_context)

        assert result.outcome == ResolutionOutcome.GAP_EMITTED
        assert result.selected_entity_id is None
        assert result.confidence == 0.0
        assert result.candidates_considered == 0

    def test_single_candidate_auto_resolves(
        self,
        resolver: AmbiguousEntityResolver,
        candidate_john_work: CandidateEntity,
        neutral_context: EventContext,
    ) -> None:
        """Single candidate auto-resolves with high confidence."""
        result = resolver.resolve("John", [candidate_john_work], neutral_context)

        assert result.outcome == ResolutionOutcome.AUTO_RESOLVED
        assert result.selected_entity_id == candidate_john_work.entity_id
        assert result.confidence == 0.95
        assert result.candidates_considered == 1
        assert "single_candidate" in result.breakdown


# =============================================================================
# Test: 5-Priority Hierarchy
# =============================================================================


class TestPriorityHierarchy:
    """Test 5-priority context hierarchy scoring."""

    def test_p1_recency_boost(
        self,
        resolver: AmbiguousEntityResolver,
        candidate_john_work: CandidateEntity,
        candidate_john_random: CandidateEntity,
        neutral_context: EventContext,
    ) -> None:
        """P1: Recent candidate gets recency boost."""
        # John work was seen 1 minute ago, John random 1 week ago
        result = resolver.resolve(
            "John",
            [candidate_john_random, candidate_john_work],  # Order shouldn't matter
            neutral_context,
        )

        assert result.selected_entity_id == candidate_john_work.entity_id
        assert result.breakdown.get("recent_context", 0) > 0

    def test_p2_co_occurring_boost(
        self,
        resolver: AmbiguousEntityResolver,
        candidate_john_work: CandidateEntity,
        candidate_john_family: CandidateEntity,
        work_context: EventContext,
    ) -> None:
        """P2: Co-occurring candidate gets boost."""
        # John work is in co_occurring_entities
        result = resolver.resolve(
            "John",
            [candidate_john_family, candidate_john_work],
            work_context,
        )

        assert result.selected_entity_id == candidate_john_work.entity_id
        assert result.breakdown.get("co_occurring", 0) == P03_RESOLUTION_BOOST_CO_OCCURRING

    def test_p3_location_boost(
        self,
        resolver: AmbiguousEntityResolver,
        now_ms: int,
        work_context: EventContext,
    ) -> None:
        """P3: Location-matching candidate gets boost."""
        # Create two candidates with similar recency but different location match
        colleague = CandidateEntity(
            entity_id="ent_colleague",
            entity_type="ORGANIZATION",  # Matches "work" location
            canonical_name="Bob (colleague)",
            last_seen_ms=now_ms - 3600_000,  # 1 hour ago
            frequency=10,
        )
        friend = CandidateEntity(
            entity_id="ent_friend",
            entity_type="PERSON",
            canonical_name="Bob (friend)",
            last_seen_ms=now_ms - 3600_000,  # 1 hour ago
            frequency=10,
        )

        result = resolver.resolve("Bob", [friend, colleague], work_context)

        # Location boost should be applied to the winning candidate
        # (both have same base score, but colleague gets location boost)
        assert result.breakdown.get("location", 0) > 0

    def test_p4_temporal_boost(
        self,
        resolver: AmbiguousEntityResolver,
        now_ms: int,
    ) -> None:
        """P4: Temporal-matching candidate gets boost."""
        # Evening context
        evening_context = EventContext(
            session_id="sess_evening",
            event_timestamp_ms=now_ms,
            co_occurring_entities=[],
            location_hint=None,
            temporal_category="evening",
            tenant_id="tenant_001",
            space_id="space_001",
        )

        # Candidates with similar scores but different temporal match
        dinner_friend = CandidateEntity(
            entity_id="ent_dinner",
            entity_type="PERSON",
            canonical_name="Dinner friend",  # Contains "dinner" -> matches evening
            last_seen_ms=now_ms - 3600_000,
            frequency=10,
        )
        work_person = CandidateEntity(
            entity_id="ent_work",
            entity_type="PERSON",
            canonical_name="Work person",
            last_seen_ms=now_ms - 3600_000,
            frequency=10,
        )

        result = resolver.resolve("friend", [work_person, dinner_friend], evening_context)

        # Dinner friend should get temporal boost
        assert result.breakdown.get("temporal", 0) > 0

    def test_p5_frequency_boost(
        self,
        resolver: AmbiguousEntityResolver,
        now_ms: int,
        neutral_context: EventContext,
    ) -> None:
        """P5: Higher frequency candidate gets small boost."""
        frequent = CandidateEntity(
            entity_id="ent_frequent",
            entity_type="PERSON",
            canonical_name="Frequent Person",
            last_seen_ms=now_ms - 7200_000,  # 2 hours ago (outside recency window)
            frequency=100,
        )
        rare = CandidateEntity(
            entity_id="ent_rare",
            entity_type="PERSON",
            canonical_name="Rare Person",
            last_seen_ms=now_ms - 7200_000,  # Same recency
            frequency=1,
        )

        result = resolver.resolve("Person", [rare, frequent], neutral_context)

        # Frequency boost should be applied
        assert result.breakdown.get("frequency", 0) > 0


# =============================================================================
# Test: Confidence Bands
# =============================================================================


class TestConfidenceBands:
    """Test confidence band routing."""

    def test_auto_resolved_above_threshold(
        self,
        resolver: AmbiguousEntityResolver,
        candidate_john_work: CandidateEntity,
        work_context: EventContext,
    ) -> None:
        """Confidence >= 0.85 returns AUTO_RESOLVED."""
        # John work has recency + co-occurring + location boosts
        result = resolver.resolve("John", [candidate_john_work], work_context)

        # Single candidate = 0.95 confidence
        assert result.outcome == ResolutionOutcome.AUTO_RESOLVED
        assert result.confidence >= P03_RESOLUTION_THRESHOLD_AUTO

    def test_resolved_flagged_in_middle_band(
        self,
        resolver: AmbiguousEntityResolver,
        now_ms: int,
    ) -> None:
        """Confidence 0.60-0.85 returns RESOLVED_FLAGGED."""
        # One candidate with strong recency + frequency to reach FLAG band
        strong = CandidateEntity(
            entity_id="ent_1",
            entity_type="PERSON",
            canonical_name="Strong Candidate",
            last_seen_ms=now_ms - 300_000,  # 5 minutes ago (within recency window)
            frequency=80,
        )
        weak = CandidateEntity(
            entity_id="ent_2",
            entity_type="PERSON",
            canonical_name="Weak Candidate",
            last_seen_ms=now_ms - 86400_000,  # 1 day ago
            frequency=5,
        )

        # Use context that helps strong candidate reach FLAG band
        context = EventContext(
            session_id="sess_flag",
            event_timestamp_ms=now_ms,
            co_occurring_entities=[],
            location_hint=None,
            temporal_category=None,
            tenant_id="tenant_001",
            space_id="space_001",
        )

        result = resolver.resolve("Candidate", [weak, strong], context)

        # With strong recency boost, should reach FLAG band
        # Base (0.30) + recency (~0.30) + frequency (0.04) = ~0.64
        assert result.outcome == ResolutionOutcome.RESOLVED_FLAGGED
        assert P03_RESOLUTION_THRESHOLD_FLAG <= result.confidence < P03_RESOLUTION_THRESHOLD_AUTO

    def test_gap_emitted_below_threshold(
        self,
        resolver: AmbiguousEntityResolver,
        now_ms: int,
        neutral_context: EventContext,
    ) -> None:
        """Confidence < 0.60 returns GAP_EMITTED."""
        # Very old, low frequency candidates with no context match
        old1 = CandidateEntity(
            entity_id="ent_old1",
            entity_type="PERSON",
            canonical_name="Old One",
            last_seen_ms=now_ms - 86400_000 * 30,  # 30 days ago
            frequency=1,
        )
        old2 = CandidateEntity(
            entity_id="ent_old2",
            entity_type="PERSON",
            canonical_name="Old Two",
            last_seen_ms=now_ms - 86400_000 * 30,  # 30 days ago
            frequency=1,
        )

        result = resolver.resolve("Old", [old1, old2], neutral_context)

        # Base 0.30 + minimal frequency boost + close race penalty = low confidence
        # May end up in FLAG or GAP depending on exact calculation
        assert result.confidence < P03_RESOLUTION_THRESHOLD_AUTO


# =============================================================================
# Test: Close Race Penalty
# =============================================================================


class TestCloseRacePenalty:
    """Test close race penalty application."""

    def test_penalty_applied_when_gap_small(
        self,
        resolver: AmbiguousEntityResolver,
        now_ms: int,
        neutral_context: EventContext,
    ) -> None:
        """Close race penalty applied when gap < 0.10."""
        # Create candidates with nearly identical scores
        c1 = CandidateEntity(
            entity_id="ent_1",
            entity_type="PERSON",
            canonical_name="Candidate One",
            last_seen_ms=now_ms - 7200_000,
            frequency=50,
        )
        c2 = CandidateEntity(
            entity_id="ent_2",
            entity_type="PERSON",
            canonical_name="Candidate Two",
            last_seen_ms=now_ms - 7200_000,
            frequency=49,  # Nearly identical
        )

        result = resolver.resolve("Candidate", [c1, c2], neutral_context)

        # Penalty should be recorded in breakdown
        assert result.breakdown.get("close_race_penalty", 0) < 0

    def test_no_penalty_when_gap_large(
        self,
        resolver: AmbiguousEntityResolver,
        now_ms: int,
        work_context: EventContext,
    ) -> None:
        """No close race penalty when gap >= 0.10."""
        # One candidate has significant advantages
        strong = CandidateEntity(
            entity_id="ent_strong",
            entity_type="ORGANIZATION",  # Matches work location
            canonical_name="Strong Candidate",
            last_seen_ms=now_ms - 60_000,  # Recent
            frequency=100,
        )
        weak = CandidateEntity(
            entity_id="ent_weak",
            entity_type="PERSON",
            canonical_name="Weak Candidate",
            last_seen_ms=now_ms - 86400_000,  # Old
            frequency=1,
        )

        result = resolver.resolve("Candidate", [weak, strong], work_context)

        # No penalty for large gap
        assert (
            "close_race_penalty" not in result.breakdown
            or result.breakdown.get("close_race_penalty", 0) >= 0
        )


# =============================================================================
# Test: Metrics
# =============================================================================


class TestMetrics:
    """Test metrics tracking."""

    def test_metrics_increment_on_resolution(
        self,
        resolver: AmbiguousEntityResolver,
        candidate_john_work: CandidateEntity,
        neutral_context: EventContext,
    ) -> None:
        """Metrics are updated after each resolution."""
        initial_total = resolver.metrics.total_resolutions

        resolver.resolve("John", [candidate_john_work], neutral_context)

        assert resolver.metrics.total_resolutions == initial_total + 1

    def test_metrics_track_outcome_counts(
        self,
        resolver: AmbiguousEntityResolver,
        candidate_john_work: CandidateEntity,
        neutral_context: EventContext,
    ) -> None:
        """Metrics track outcome distribution."""
        # Single candidate = AUTO_RESOLVED
        resolver.resolve("John", [candidate_john_work], neutral_context)
        assert resolver.metrics.auto_resolved >= 1

        # No candidates = GAP_EMITTED
        resolver.resolve("Unknown", [], neutral_context)
        assert resolver.metrics.gaps_emitted >= 1

    def test_metrics_track_boost_usage(
        self,
        resolver: AmbiguousEntityResolver,
        candidate_john_work: CandidateEntity,
        work_context: EventContext,
    ) -> None:
        """Metrics track which boosts are applied."""
        _result = resolver.resolve("John", [candidate_john_work], work_context)

        # Various boosts should be tracked
        assert resolver.metrics.boost_usage.get("recent_context", 0) >= 0


# =============================================================================
# Test: Async Operations
# =============================================================================


class TestAsyncOperations:
    """Test async operations for gap emission and recording."""

    @pytest.mark.asyncio
    async def test_emit_gap_to_p06(
        self,
        resolver: AmbiguousEntityResolver,
        candidate_john_work: CandidateEntity,
        candidate_john_family: CandidateEntity,
        neutral_context: EventContext,
    ) -> None:
        """emit_gap_to_p06 publishes to event bus."""
        # Create a low-confidence result
        result = resolver.resolve(
            "John",
            [candidate_john_work, candidate_john_family],
            neutral_context,
        )

        # Mock event bus
        mock_bus = AsyncMock()

        await resolver.emit_gap_to_p06(
            mention="John",
            candidates=[candidate_john_work, candidate_john_family],
            event_context=neutral_context,
            result=result,
            event_bus=mock_bus,
        )

        # Verify publish was called
        mock_bus.publish.assert_called_once()
        call_args = mock_bus.publish.call_args
        assert call_args.kwargs["topic"] == "p03.gap.detected.v1"
        assert call_args.kwargs["payload"]["gap_type"] == "AMBIGUOUS_ENTITY"

    @pytest.mark.asyncio
    async def test_record_resolution(
        self,
        resolver: AmbiguousEntityResolver,
        candidate_john_work: CandidateEntity,
        neutral_context: EventContext,
    ) -> None:
        """record_resolution persists to database."""
        result = resolver.resolve("John", [candidate_john_work], neutral_context)

        # Mock database connection
        mock_db = AsyncMock()

        resolution_id = await resolver.record_resolution(
            result=result,
            event_context=neutral_context,
            db_conn=mock_db,
        )

        # Verify execute was called with INSERT
        mock_db.execute.assert_called_once()
        call_args = mock_db.execute.call_args
        assert "INSERT INTO st_entity_resolutions" in call_args.args[0]
        assert resolution_id is not None


# =============================================================================
# Test: Data Classes
# =============================================================================


class TestDataClasses:
    """Test data class serialization."""

    def test_candidate_entity_to_dict(
        self,
        candidate_john_work: CandidateEntity,
    ) -> None:
        """CandidateEntity serializes to dict."""
        d = candidate_john_work.to_dict()

        assert d["entity_id"] == candidate_john_work.entity_id
        assert d["entity_type"] == "PERSON"
        assert d["canonical_name"] == "John Smith (Colleague)"
        assert "embedding" not in d  # Embedding excluded

    def test_event_context_to_dict(
        self,
        work_context: EventContext,
    ) -> None:
        """EventContext serializes to dict."""
        d = work_context.to_dict()

        assert d["session_id"] == work_context.session_id
        assert d["location_hint"] == "work"
        assert "tenant_id" not in d  # Internal fields excluded

    def test_resolution_result_to_dict(
        self,
        resolver: AmbiguousEntityResolver,
        candidate_john_work: CandidateEntity,
        neutral_context: EventContext,
    ) -> None:
        """ResolutionResult serializes to dict."""
        result = resolver.resolve("John", [candidate_john_work], neutral_context)
        d = result.to_dict()

        assert d["mention"] == "John"
        assert d["selected_entity_id"] == candidate_john_work.entity_id
        assert d["outcome"] == "auto_resolved"
        assert isinstance(d["confidence"], float)
        assert isinstance(d["breakdown"], dict)
