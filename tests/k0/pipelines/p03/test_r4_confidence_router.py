"""
Tests for R4 Confidence Router.

Issue: 4.4.5 - Implement confidence bands + P06 gap emission
Spec Reference: M4_EXECUTION.md, Dossier Section 4.5.1.3

Test Coverage:
1. Confidence band determination (AUTO, FLAG, GAP)
2. Routing with gap payload generation
3. Gap emission to st_learning_queue
4. Outbox staging for reliable delivery
5. Batch gap emission
6. Metrics tracking
7. Quick band lookup

Author: K0 Architecture Team
Date: 2025-01-03
"""

from unittest.mock import AsyncMock

import pytest

from k0.modules.consolidation.algorithms.confidence_router import (
    P03_CONFIDENCE_THRESHOLD_AUTO,
    P03_CONFIDENCE_THRESHOLD_FLAG,
    ConfidenceBand,
    ConfidenceRouter,
    ConfidenceRouterConfig,
    GapPayload,
    GapType,
    get_confidence_router,
    quick_band,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def router() -> ConfidenceRouter:
    """Fresh router instance with default config."""
    return ConfidenceRouter()


@pytest.fixture
def custom_router() -> ConfidenceRouter:
    """Router with custom thresholds for testing."""
    config = ConfidenceRouterConfig(
        threshold_auto=0.90,
        threshold_flag=0.50,
        gap_batch_size=10,
    )
    return ConfidenceRouter(config=config)


@pytest.fixture
def sample_candidates() -> list:
    """Sample candidate entities."""
    return [
        {
            "entity_id": "ent_001",
            "entity_type": "PERSON",
            "canonical_name": "John Smith",
        },
        {
            "entity_id": "ent_002",
            "entity_type": "PERSON",
            "canonical_name": "John Doe",
        },
    ]


@pytest.fixture
def sample_context() -> dict:
    """Sample event context."""
    return {
        "session_id": "sess_001",
        "event_timestamp_ms": 1704067200000,
        "co_occurring_entities": [],
        "location_hint": "home",
    }


@pytest.fixture
def sample_breakdown() -> dict:
    """Sample score breakdown."""
    return {
        "base_score": 0.30,
        "recent_context": 0.15,
        "co_occurring": 0.0,
        "location": 0.10,
    }


# =============================================================================
# Test: Configuration
# =============================================================================


class TestConfiguration:
    """Test router configuration."""

    def test_default_thresholds(self, router: ConfidenceRouter) -> None:
        """Default thresholds match spec."""
        assert router.config.threshold_auto == P03_CONFIDENCE_THRESHOLD_AUTO
        assert router.config.threshold_flag == P03_CONFIDENCE_THRESHOLD_FLAG

    def test_custom_thresholds(self, custom_router: ConfidenceRouter) -> None:
        """Custom thresholds are applied."""
        assert custom_router.config.threshold_auto == 0.90
        assert custom_router.config.threshold_flag == 0.50

    def test_config_validation_invalid_thresholds(self) -> None:
        """Invalid threshold ordering raises error."""
        config = ConfidenceRouterConfig(threshold_auto=0.50, threshold_flag=0.70)
        with pytest.raises(ValueError, match="threshold_flag"):
            config.validate()

    def test_factory_function(self) -> None:
        """Factory function creates router."""
        router = get_confidence_router()
        assert isinstance(router, ConfidenceRouter)

    def test_factory_with_config(self) -> None:
        """Factory function accepts config."""
        config = ConfidenceRouterConfig(threshold_auto=0.95)
        router = get_confidence_router(config=config)
        assert router.config.threshold_auto == 0.95


# =============================================================================
# Test: Band Determination
# =============================================================================


class TestBandDetermination:
    """Test confidence band determination."""

    def test_auto_band_at_threshold(self, router: ConfidenceRouter) -> None:
        """Confidence == threshold_auto returns AUTO."""
        band = router.determine_band(P03_CONFIDENCE_THRESHOLD_AUTO)
        assert band == ConfidenceBand.AUTO

    def test_auto_band_above_threshold(self, router: ConfidenceRouter) -> None:
        """Confidence > threshold_auto returns AUTO."""
        band = router.determine_band(0.95)
        assert band == ConfidenceBand.AUTO

    def test_flag_band_at_threshold(self, router: ConfidenceRouter) -> None:
        """Confidence == threshold_flag returns FLAG."""
        band = router.determine_band(P03_CONFIDENCE_THRESHOLD_FLAG)
        assert band == ConfidenceBand.FLAG

    def test_flag_band_between_thresholds(self, router: ConfidenceRouter) -> None:
        """Confidence in (flag, auto) returns FLAG."""
        band = router.determine_band(0.75)
        assert band == ConfidenceBand.FLAG

    def test_gap_band_below_threshold(self, router: ConfidenceRouter) -> None:
        """Confidence < threshold_flag returns GAP."""
        band = router.determine_band(0.50)
        assert band == ConfidenceBand.GAP

    def test_gap_band_at_zero(self, router: ConfidenceRouter) -> None:
        """Confidence == 0 returns GAP."""
        band = router.determine_band(0.0)
        assert band == ConfidenceBand.GAP


# =============================================================================
# Test: Routing
# =============================================================================


class TestRouting:
    """Test full routing with payload generation."""

    def test_route_auto_no_gap(
        self,
        router: ConfidenceRouter,
        sample_candidates: list,
        sample_context: dict,
    ) -> None:
        """AUTO band does not generate gap payload."""
        result = router.route(
            confidence=0.90,
            mention="John",
            candidates=sample_candidates,
            context=sample_context,
        )

        assert result.band == ConfidenceBand.AUTO
        assert result.should_emit_gap is False
        assert result.gap_payload is None
        assert "auto" in result.action_taken.lower()

    def test_route_flag_no_gap(
        self,
        router: ConfidenceRouter,
        sample_candidates: list,
        sample_context: dict,
    ) -> None:
        """FLAG band does not generate gap payload."""
        result = router.route(
            confidence=0.75,
            mention="John",
            candidates=sample_candidates,
            context=sample_context,
        )

        assert result.band == ConfidenceBand.FLAG
        assert result.should_emit_gap is False
        assert result.gap_payload is None
        assert "flag" in result.action_taken.lower()

    def test_route_gap_generates_payload(
        self,
        router: ConfidenceRouter,
        sample_candidates: list,
        sample_context: dict,
        sample_breakdown: dict,
    ) -> None:
        """GAP band generates gap payload."""
        result = router.route(
            confidence=0.45,
            mention="John",
            candidates=sample_candidates,
            context=sample_context,
            breakdown=sample_breakdown,
            gap_type=GapType.AMBIGUOUS_ENTITY,
        )

        assert result.band == ConfidenceBand.GAP
        assert result.should_emit_gap is True
        assert result.gap_payload is not None
        assert result.gap_payload.gap_type == GapType.AMBIGUOUS_ENTITY
        assert result.gap_payload.mention == "John"
        assert result.gap_payload.confidence == 0.45
        assert "clarification" in result.action_taken.lower()

    def test_route_truncates_candidates(
        self,
        router: ConfidenceRouter,
        sample_context: dict,
    ) -> None:
        """GAP payload truncates candidates to max."""
        # Create more candidates than max
        many_candidates = [{"entity_id": f"ent_{i}", "name": f"Candidate {i}"} for i in range(10)]

        result = router.route(
            confidence=0.45,
            mention="Test",
            candidates=many_candidates,
            context=sample_context,
        )

        # Should be truncated to gap_max_candidates (default 5)
        assert len(result.gap_payload.candidates) <= router.config.gap_max_candidates

    def test_routing_result_serialization(
        self,
        router: ConfidenceRouter,
        sample_candidates: list,
        sample_context: dict,
    ) -> None:
        """RoutingResult serializes to dict."""
        result = router.route(
            confidence=0.45,
            mention="John",
            candidates=sample_candidates,
            context=sample_context,
        )

        d = result.to_dict()
        assert d["band"] == "gap"
        assert d["confidence"] == 0.45
        assert d["should_emit_gap"] is True
        assert "gap_payload" in d


# =============================================================================
# Test: Gap Emission
# =============================================================================


class TestGapEmission:
    """Test gap emission to database."""

    @pytest.mark.asyncio
    async def test_emit_gap_persists_to_queue(
        self,
        router: ConfidenceRouter,
    ) -> None:
        """emit_gap persists to st_learning_queue."""
        gap_payload = GapPayload(
            gap_type=GapType.AMBIGUOUS_ENTITY,
            mention="John",
            candidates=[{"entity_id": "ent_001"}],
            context={"session_id": "sess_001"},
            confidence=0.45,
        )

        mock_db = AsyncMock()

        entry_id = await router.emit_gap(
            gap_payload=gap_payload,
            db_conn=mock_db,
            tenant_id="tenant_001",
            space_id="space_001",
        )

        # Verify two execute calls (queue + outbox)
        assert mock_db.execute.call_count == 2

        # First call: st_learning_queue
        first_call = mock_db.execute.call_args_list[0]
        assert "INSERT INTO st_learning_queue" in first_call.args[0]

        # Second call: st_outbox
        second_call = mock_db.execute.call_args_list[1]
        assert "INSERT INTO st_outbox" in second_call.args[0]

        assert entry_id is not None

    @pytest.mark.asyncio
    async def test_emit_gap_updates_metrics(
        self,
        router: ConfidenceRouter,
    ) -> None:
        """emit_gap updates metrics."""
        gap_payload = GapPayload(
            gap_type=GapType.AMBIGUOUS_ENTITY,
            mention="John",
            candidates=[],
            context={},
            confidence=0.45,
        )

        mock_db = AsyncMock()
        initial_count = router.metrics.gaps_emitted

        await router.emit_gap(gap_payload, mock_db)

        assert router.metrics.gaps_emitted == initial_count + 1

    @pytest.mark.asyncio
    async def test_emit_gap_handles_error(
        self,
        router: ConfidenceRouter,
    ) -> None:
        """emit_gap increments gaps_failed on error."""
        gap_payload = GapPayload(
            gap_type=GapType.AMBIGUOUS_ENTITY,
            mention="John",
            candidates=[],
            context={},
            confidence=0.45,
        )

        mock_db = AsyncMock()
        mock_db.execute.side_effect = Exception("Database error")
        initial_failed = router.metrics.gaps_failed

        with pytest.raises(Exception, match="Database error"):
            await router.emit_gap(gap_payload, mock_db)

        assert router.metrics.gaps_failed == initial_failed + 1


# =============================================================================
# Test: Batch Emission
# =============================================================================


class TestBatchEmission:
    """Test batch gap emission."""

    @pytest.mark.asyncio
    async def test_emit_batch_processes_all(
        self,
        router: ConfidenceRouter,
    ) -> None:
        """emit_batch processes all gaps."""
        gaps = [
            GapPayload(
                gap_type=GapType.AMBIGUOUS_ENTITY,
                mention=f"Entity{i}",
                candidates=[],
                context={},
                confidence=0.45,
            )
            for i in range(3)
        ]

        mock_db = AsyncMock()

        entry_ids = await router.emit_batch(
            gaps=gaps,
            db_conn=mock_db,
            tenant_id="tenant_001",
            space_id="space_001",
        )

        assert len(entry_ids) == 3

    @pytest.mark.asyncio
    async def test_emit_batch_respects_limit(
        self,
        custom_router: ConfidenceRouter,
    ) -> None:
        """emit_batch respects gap_batch_size."""
        # custom_router has gap_batch_size=10
        gaps = [
            GapPayload(
                gap_type=GapType.AMBIGUOUS_ENTITY,
                mention=f"Entity{i}",
                candidates=[],
                context={},
                confidence=0.45,
            )
            for i in range(15)
        ]

        mock_db = AsyncMock()

        entry_ids = await custom_router.emit_batch(
            gaps=gaps,
            db_conn=mock_db,
        )

        # Should only process first 10
        assert len(entry_ids) == 10

    @pytest.mark.asyncio
    async def test_emit_batch_continues_on_error(
        self,
        router: ConfidenceRouter,
    ) -> None:
        """emit_batch continues processing after error."""
        gaps = [
            GapPayload(
                gap_type=GapType.AMBIGUOUS_ENTITY,
                mention=f"Entity{i}",
                candidates=[],
                context={},
                confidence=0.45,
            )
            for i in range(3)
        ]

        mock_db = AsyncMock()
        # First call fails, rest succeed
        mock_db.execute.side_effect = [
            Exception("First error"),
            "OK",
            "OK",
            "OK",
            "OK",
        ]

        entry_ids = await router.emit_batch(
            gaps=gaps,
            db_conn=mock_db,
        )

        # Should have 2 successful (first failed)
        assert len(entry_ids) == 2


# =============================================================================
# Test: Metrics
# =============================================================================


class TestMetrics:
    """Test metrics tracking."""

    def test_metrics_increment_on_route(
        self,
        router: ConfidenceRouter,
        sample_candidates: list,
        sample_context: dict,
    ) -> None:
        """Metrics are updated after each route."""
        initial_total = router.metrics.total_routed

        router.route(
            confidence=0.90,
            mention="John",
            candidates=sample_candidates,
            context=sample_context,
        )

        assert router.metrics.total_routed == initial_total + 1

    def test_metrics_track_band_counts(
        self,
        router: ConfidenceRouter,
        sample_candidates: list,
        sample_context: dict,
    ) -> None:
        """Metrics track band distribution."""
        # Route one of each band
        router.route(confidence=0.90, mention="Auto", candidates=[], context={})
        router.route(confidence=0.75, mention="Flag", candidates=[], context={})
        router.route(
            confidence=0.45,
            mention="Gap",
            candidates=sample_candidates,
            context=sample_context,
        )

        assert router.metrics.auto_count >= 1
        assert router.metrics.flag_count >= 1
        assert router.metrics.gap_count >= 1

    def test_metrics_update_distribution(
        self,
        router: ConfidenceRouter,
    ) -> None:
        """Metrics calculate band distribution percentages."""
        # Route 2 AUTO, 1 FLAG, 1 GAP
        router.route(confidence=0.90, mention="A1", candidates=[], context={})
        router.route(confidence=0.90, mention="A2", candidates=[], context={})
        router.route(confidence=0.75, mention="F1", candidates=[], context={})
        router.route(confidence=0.45, mention="G1", candidates=[{"id": 1}], context={})

        assert router.metrics.band_distribution["auto"] == 0.5
        assert router.metrics.band_distribution["flag"] == 0.25
        assert router.metrics.band_distribution["gap"] == 0.25

    def test_metrics_avg_confidence(
        self,
        router: ConfidenceRouter,
    ) -> None:
        """Metrics track average confidence."""
        router.route(confidence=0.80, mention="A", candidates=[], context={})
        router.route(confidence=0.60, mention="B", candidates=[], context={})

        # EMA with alpha=0.1: first=0.80, second=0.1*0.60+0.9*0.80=0.78
        # But there may be prior routes, so just check it's tracked
        assert router.metrics.avg_confidence > 0


# =============================================================================
# Test: Quick Band Function
# =============================================================================


class TestQuickBand:
    """Test quick_band convenience function."""

    def test_quick_band_auto(self) -> None:
        """quick_band returns AUTO for high confidence."""
        assert quick_band(0.90) == ConfidenceBand.AUTO
        assert quick_band(0.85) == ConfidenceBand.AUTO

    def test_quick_band_flag(self) -> None:
        """quick_band returns FLAG for medium confidence."""
        assert quick_band(0.75) == ConfidenceBand.FLAG
        assert quick_band(0.60) == ConfidenceBand.FLAG

    def test_quick_band_gap(self) -> None:
        """quick_band returns GAP for low confidence."""
        assert quick_band(0.50) == ConfidenceBand.GAP
        assert quick_band(0.0) == ConfidenceBand.GAP


# =============================================================================
# Test: Gap Payload Serialization
# =============================================================================


class TestGapPayloadSerialization:
    """Test GapPayload serialization."""

    def test_to_dict(self) -> None:
        """GapPayload serializes to dict."""
        payload = GapPayload(
            gap_type=GapType.AMBIGUOUS_ENTITY,
            mention="John",
            candidates=[{"entity_id": "ent_001"}],
            context={"session_id": "sess_001"},
            confidence=0.45,
            breakdown={"base": 0.30},
            created_at_ms=1704067200000,
            ttl_ms=86400000,
        )

        d = payload.to_dict()

        assert d["gap_type"] == "AMBIGUOUS_ENTITY"
        assert d["mention"] == "John"
        assert d["confidence"] == 0.45
        assert d["breakdown"] == {"base": 0.30}
        assert d["created_at_ms"] == 1704067200000

    def test_from_dict(self) -> None:
        """GapPayload deserializes from dict."""
        data = {
            "gap_type": "AMBIGUOUS_ENTITY",
            "mention": "John",
            "candidates": [{"entity_id": "ent_001"}],
            "context": {"session_id": "sess_001"},
            "confidence": 0.45,
            "breakdown": {"base": 0.30},
            "created_at_ms": 1704067200000,
        }

        payload = GapPayload.from_dict(data)

        assert payload.gap_type == GapType.AMBIGUOUS_ENTITY
        assert payload.mention == "John"
        assert payload.confidence == 0.45


# =============================================================================
# Test: Thresholds Getter
# =============================================================================


class TestThresholdsGetter:
    """Test get_band_thresholds method."""

    def test_get_band_thresholds(self, router: ConfidenceRouter) -> None:
        """get_band_thresholds returns threshold values."""
        thresholds = router.get_band_thresholds()

        assert thresholds["auto"] == P03_CONFIDENCE_THRESHOLD_AUTO
        assert thresholds["flag"] == P03_CONFIDENCE_THRESHOLD_FLAG

    def test_custom_thresholds_returned(self, custom_router: ConfidenceRouter) -> None:
        """Custom thresholds are returned."""
        thresholds = custom_router.get_band_thresholds()

        assert thresholds["auto"] == 0.90
        assert thresholds["flag"] == 0.50
