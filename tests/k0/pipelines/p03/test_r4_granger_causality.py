"""
Tests for R4 Granger Causality Inference.

Issue: 4.4.9 - Implement Granger causality inference

Spec Reference:
    - Dossier §4.5.4: Causal Inference (Granger Causality)
    - Dossier Appendix C.5.2: Granger Causality Algorithm
    - M4_EXECUTION.md Issue 4.4.9

Test Cases (from M4_EXECUTION.md):
    1. test_compute_precedence_a_before_b — Clear A→B pattern
    2. test_compute_precedence_b_before_a — Clear B→A pattern
    3. test_compute_precedence_simultaneous — Within 1 min = simultaneous
    4. test_infer_causal_no_observations — <5 obs → None
    5. test_infer_causal_strong_precedence — 0.95 ratio → CausalEdge
    6. test_infer_causal_weak_precedence — 0.55 ratio → None
    7. test_infer_causal_reverse_direction — 0.20 ratio → B CAUSES A
    8. test_persist_creates_new_edge — New edge inserted
    9. test_persist_updates_existing_edge — Existing edge updated
    10. test_batch_analysis — Multiple pairs processed

TIMESTAMP CONVENTION: All timestamps use MILLISECONDS since Unix epoch.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

import pytest

from k0.modules.consolidation.algorithms.granger_causality import (
    CausalEdge,
    CausalityConfig,
    GrangerCausalityInference,
    generate_ulid,
    now_ms,
)

# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def default_config() -> CausalityConfig:
    """Default causality config from spec."""
    return CausalityConfig(
        min_observations=5,
        causality_threshold=0.75,
        temporal_window_minutes=60,
        simultaneous_threshold_minutes=1,
    )


@pytest.fixture
def inference(default_config: CausalityConfig) -> GrangerCausalityInference:
    """Granger causality inference instance."""
    return GrangerCausalityInference(config=default_config)


@pytest.fixture
def base_time() -> int:
    """Base timestamp in milliseconds."""
    return 1704067200000  # 2024-01-01 00:00:00 UTC


# =============================================================================
# Mock Classes for Database Tests
# =============================================================================


class MockObservationStore:
    """Mock observation store for testing."""

    def __init__(self, observations: dict[tuple[str, str], List[Tuple[int, int]]]):
        self.observations = observations

    async def get_cooccurrence_timestamps(
        self,
        entity_a: str,
        entity_b: str,
        db_conn,
    ) -> List[Tuple[int, int]]:
        """Return mock observations."""
        return self.observations.get((entity_a, entity_b), [])


class MockDatabaseConnection:
    """Mock database connection for testing."""

    def __init__(self):
        self.edges: dict[tuple[str, str], dict] = {}
        self.queries_executed: List[str] = []

    async def fetchrow(self, query: str, *args) -> Optional[dict]:
        """Fetch single row."""
        self.queries_executed.append(query)
        if "SELECT edge_id" in query and len(args) >= 2:
            key = (args[0], args[1])
            return self.edges.get(key)
        return None

    async def execute(self, query: str, *args) -> None:
        """Execute query."""
        self.queries_executed.append(query)
        if "INSERT INTO st_kg_edges" in query and len(args) >= 10:
            key = (args[1], args[2])  # source_entity_id, target_entity_id
            self.edges[key] = {
                "edge_id": args[0],
                "source_entity_id": args[1],
                "target_entity_id": args[2],
                "relation_type": args[3],
                "edge_type": args[4],
                "causal_confidence": args[5],
                "observation_count": args[6],
                "precedence_ratio": args[7],
            }
        elif "UPDATE st_kg_edges" in query and len(args) >= 5:
            edge_id = args[4]
            for key, edge in self.edges.items():
                if edge.get("edge_id") == edge_id:
                    edge["causal_confidence"] = args[0]
                    edge["observation_count"] = args[1]
                    edge["precedence_ratio"] = args[2]
                    break


# =============================================================================
# Test: compute_temporal_precedence
# =============================================================================


class TestComputeTemporalPrecedence:
    """Tests for compute_temporal_precedence method."""

    def test_compute_precedence_a_before_b(
        self,
        inference: GrangerCausalityInference,
        base_time: int,
    ):
        """
        Test Case 1: Clear A→B pattern.

        When A consistently happens before B, precedence_ratio should be high.
        """
        # A happens 10 minutes before B each time
        observations = [
            (base_time, base_time + 10 * 60000),  # A at 0, B at +10min
            (base_time + 3600000, base_time + 3600000 + 15 * 60000),  # 1hr later
            (base_time + 7200000, base_time + 7200000 + 5 * 60000),  # 2hr later
            (base_time + 10800000, base_time + 10800000 + 20 * 60000),  # 3hr later
            (base_time + 14400000, base_time + 14400000 + 8 * 60000),  # 4hr later
        ]

        stats = inference.compute_temporal_precedence("entity_a", "entity_b", observations)

        assert stats.a_before_b == 5
        assert stats.b_before_a == 0
        assert stats.simultaneous == 0
        assert stats.total == 5
        assert stats.precedence_ratio == 1.0

    def test_compute_precedence_b_before_a(
        self,
        inference: GrangerCausalityInference,
        base_time: int,
    ):
        """
        Test Case 2: Clear B→A pattern.

        When B consistently happens before A, precedence_ratio should be low.
        """
        # B happens before A (ts_a > ts_b means B first)
        observations = [
            (base_time + 10 * 60000, base_time),  # A at +10min, B at 0
            (base_time + 3600000 + 15 * 60000, base_time + 3600000),
            (base_time + 7200000 + 5 * 60000, base_time + 7200000),
            (base_time + 10800000 + 20 * 60000, base_time + 10800000),
            (base_time + 14400000 + 8 * 60000, base_time + 14400000),
        ]

        stats = inference.compute_temporal_precedence("entity_a", "entity_b", observations)

        assert stats.a_before_b == 0
        assert stats.b_before_a == 5
        assert stats.simultaneous == 0
        assert stats.total == 5
        assert stats.precedence_ratio == 0.0

    def test_compute_precedence_simultaneous(
        self,
        inference: GrangerCausalityInference,
        base_time: int,
    ):
        """
        Test Case 3: Within 1 min = simultaneous.

        When events are within simultaneous_threshold_minutes, count as simultaneous.
        """
        # Events within 30 seconds of each other (< 1 minute threshold)
        observations = [
            (base_time, base_time + 30000),  # 30 seconds apart
            (base_time + 3600000, base_time + 3600000 + 20000),  # 20 seconds
            (base_time + 7200000, base_time + 7200000 + 45000),  # 45 seconds
            (base_time + 10800000, base_time + 10800000 + 10000),  # 10 seconds
            (base_time + 14400000, base_time + 14400000 + 55000),  # 55 seconds
        ]

        stats = inference.compute_temporal_precedence("entity_a", "entity_b", observations)

        assert stats.simultaneous == 5
        assert stats.a_before_b == 0
        assert stats.b_before_a == 0
        assert stats.total == 5
        # Ratio defaults to 0/5 = 0.0 (but all are simultaneous)
        assert stats.precedence_ratio == 0.0

    def test_compute_precedence_mixed(
        self,
        inference: GrangerCausalityInference,
        base_time: int,
    ):
        """
        Test mixed pattern: some A before B, some B before A, some simultaneous.
        """
        observations = [
            (base_time, base_time + 10 * 60000),  # A before B
            (base_time + 3600000, base_time + 3600000 + 5 * 60000),  # A before B
            (base_time + 7200000 + 15 * 60000, base_time + 7200000),  # B before A
            (base_time + 10800000, base_time + 10800000 + 30000),  # Simultaneous
            (base_time + 14400000, base_time + 14400000 + 8 * 60000),  # A before B
        ]

        stats = inference.compute_temporal_precedence("entity_a", "entity_b", observations)

        assert stats.a_before_b == 3
        assert stats.b_before_a == 1
        assert stats.simultaneous == 1
        assert stats.total == 5
        assert stats.precedence_ratio == 3 / 5  # 0.6

    def test_compute_precedence_empty_observations(
        self,
        inference: GrangerCausalityInference,
    ):
        """Test with no observations returns neutral ratio."""
        stats = inference.compute_temporal_precedence("entity_a", "entity_b", [])

        assert stats.total == 0
        assert stats.precedence_ratio == 0.5  # Neutral default


# =============================================================================
# Test: infer_causal_direction
# =============================================================================


class TestInferCausalDirection:
    """Tests for infer_causal_direction method."""

    def test_infer_causal_no_observations(
        self,
        inference: GrangerCausalityInference,
        base_time: int,
    ):
        """
        Test Case 4: <5 obs → None.

        Insufficient observations should return None.
        """
        # Only 3 observations (below min_observations=5)
        observations = [
            (base_time, base_time + 10 * 60000),
            (base_time + 3600000, base_time + 3600000 + 15 * 60000),
            (base_time + 7200000, base_time + 7200000 + 5 * 60000),
        ]

        result = inference.infer_causal_direction("entity_a", "entity_b", observations)

        assert result is None

    def test_infer_causal_strong_precedence(
        self,
        inference: GrangerCausalityInference,
        base_time: int,
    ):
        """
        Test Case 5: 0.95 ratio → CausalEdge.

        Strong precedence should create A CAUSES B edge.
        """
        # A before B in all 10 observations
        observations = [
            (base_time + i * 3600000, base_time + i * 3600000 + 10 * 60000) for i in range(10)
        ]

        result = inference.infer_causal_direction("entity_a", "entity_b", observations)

        assert result is not None
        assert result.source_id == "entity_a"
        assert result.target_id == "entity_b"
        assert result.relation_type == "CAUSES"
        assert result.confidence == 1.0
        assert result.observation_count == 10
        assert result.precedence_ratio == 1.0

    def test_infer_causal_weak_precedence(
        self,
        inference: GrangerCausalityInference,
        base_time: int,
    ):
        """
        Test Case 6: 0.55 ratio → None.

        Weak precedence (below threshold) should return None.
        """
        # 11 observations: 6 A before B, 5 B before A
        # Ratio = 6/11 ≈ 0.545 (below 0.75 threshold)
        observations = []
        for i in range(6):
            # A before B
            observations.append((base_time + i * 3600000, base_time + i * 3600000 + 10 * 60000))
        for i in range(5):
            # B before A
            observations.append(
                (base_time + (6 + i) * 3600000 + 10 * 60000, base_time + (6 + i) * 3600000)
            )

        result = inference.infer_causal_direction("entity_a", "entity_b", observations)

        assert result is None

    def test_infer_causal_reverse_direction(
        self,
        inference: GrangerCausalityInference,
        base_time: int,
    ):
        """
        Test Case 7: 0.20 ratio → B CAUSES A.

        When precedence_ratio <= (1 - threshold), reverse direction is inferred.
        """
        # B before A in 9 of 10 observations
        # Ratio = 1/10 = 0.10 <= 0.25 (1 - 0.75)
        observations = []
        # 1 time A before B
        observations.append((base_time, base_time + 10 * 60000))
        # 9 times B before A
        for i in range(1, 10):
            observations.append((base_time + i * 3600000 + 10 * 60000, base_time + i * 3600000))

        result = inference.infer_causal_direction("entity_a", "entity_b", observations)

        assert result is not None
        assert result.source_id == "entity_b"  # Reversed!
        assert result.target_id == "entity_a"
        assert result.relation_type == "CAUSES"
        assert result.confidence == 0.9  # 1 - 0.1
        assert result.observation_count == 10
        assert result.precedence_ratio == 0.9

    def test_infer_causal_exactly_at_threshold(
        self,
        inference: GrangerCausalityInference,
        base_time: int,
    ):
        """Test exactly at threshold creates edge."""
        # 15 A before B, 5 B before A = ratio 0.75 exactly
        observations = []
        for i in range(15):
            observations.append((base_time + i * 3600000, base_time + i * 3600000 + 10 * 60000))
        for i in range(5):
            observations.append(
                (base_time + (15 + i) * 3600000 + 10 * 60000, base_time + (15 + i) * 3600000)
            )

        result = inference.infer_causal_direction("entity_a", "entity_b", observations)

        assert result is not None
        assert result.source_id == "entity_a"
        assert result.confidence == 0.75

    def test_infer_causal_custom_config(
        self,
        base_time: int,
    ):
        """Test with custom config override."""
        # Use stricter threshold
        strict_config = CausalityConfig(
            min_observations=3,
            causality_threshold=0.90,
        )
        inference = GrangerCausalityInference(config=strict_config)

        # 8 of 10 A before B = 0.80 ratio (below 0.90)
        observations = []
        for i in range(8):
            observations.append((base_time + i * 3600000, base_time + i * 3600000 + 10 * 60000))
        for i in range(2):
            observations.append(
                (base_time + (8 + i) * 3600000 + 10 * 60000, base_time + (8 + i) * 3600000)
            )

        result = inference.infer_causal_direction("entity_a", "entity_b", observations)

        # 0.80 is below 0.90 threshold, so None
        assert result is None


# =============================================================================
# Test: persist_causal_edges
# =============================================================================


class TestPersistCausalEdges:
    """Tests for persist_causal_edges method."""

    @pytest.mark.asyncio
    async def test_persist_creates_new_edge(
        self,
        inference: GrangerCausalityInference,
    ):
        """
        Test Case 8: New edge inserted.

        When no existing edge, should INSERT new row.
        """
        db = MockDatabaseConnection()
        edges = [
            CausalEdge(
                source_id="alarm_entity",
                target_id="wakeup_entity",
                relation_type="CAUSES",
                confidence=0.95,
                observation_count=20,
                precedence_ratio=0.95,
            )
        ]

        count = await inference.persist_causal_edges(edges, "space_1", db)

        assert count == 1
        assert ("alarm_entity", "wakeup_entity") in db.edges
        edge = db.edges[("alarm_entity", "wakeup_entity")]
        assert edge["relation_type"] == "CAUSES"
        assert edge["edge_type"] == "CAUSAL"
        assert edge["causal_confidence"] == 0.95
        assert edge["observation_count"] == 20

    @pytest.mark.asyncio
    async def test_persist_updates_existing_edge(
        self,
        inference: GrangerCausalityInference,
    ):
        """
        Test Case 9: Existing edge updated.

        When edge already exists, should UPDATE instead of INSERT.
        """
        db = MockDatabaseConnection()
        # Pre-existing edge
        existing_edge_id = generate_ulid()
        db.edges[("coffee_entity", "work_entity")] = {
            "edge_id": existing_edge_id,
            "source_entity_id": "coffee_entity",
            "target_entity_id": "work_entity",
            "causal_confidence": 0.80,
            "observation_count": 10,
        }

        edges = [
            CausalEdge(
                source_id="coffee_entity",
                target_id="work_entity",
                relation_type="CAUSES",
                confidence=0.88,
                observation_count=25,
                precedence_ratio=0.88,
            )
        ]

        count = await inference.persist_causal_edges(edges, "space_1", db)

        assert count == 1
        edge = db.edges[("coffee_entity", "work_entity")]
        assert edge["causal_confidence"] == 0.88
        assert edge["observation_count"] == 25
        assert edge["precedence_ratio"] == 0.88

    @pytest.mark.asyncio
    async def test_persist_multiple_edges(
        self,
        inference: GrangerCausalityInference,
    ):
        """Test persisting multiple causal edges."""
        db = MockDatabaseConnection()
        edges = [
            CausalEdge(
                source_id="alarm",
                target_id="wakeup",
                relation_type="CAUSES",
                confidence=0.95,
                observation_count=20,
                precedence_ratio=0.95,
            ),
            CausalEdge(
                source_id="coffee",
                target_id="work",
                relation_type="CAUSES",
                confidence=0.82,
                observation_count=15,
                precedence_ratio=0.82,
            ),
            CausalEdge(
                source_id="exercise",
                target_id="mood",
                relation_type="CAUSES",
                confidence=0.78,
                observation_count=12,
                precedence_ratio=0.78,
            ),
        ]

        count = await inference.persist_causal_edges(edges, "space_1", db)

        assert count == 3
        assert len(db.edges) == 3


# =============================================================================
# Test: analyze_cooccurrence_pairs
# =============================================================================


class TestAnalyzeCooccurrencePairs:
    """Tests for analyze_cooccurrence_pairs method."""

    @pytest.mark.asyncio
    async def test_batch_analysis(
        self,
        inference: GrangerCausalityInference,
        base_time: int,
    ):
        """
        Test Case 10: Multiple pairs processed.

        Should analyze all pairs and return causal edges where applicable.
        """
        # Create observations for different pairs
        observations = {
            # Alarm → Wakeup: Strong causality (100%)
            ("alarm", "wakeup"): [
                (base_time + i * 3600000, base_time + i * 3600000 + 5 * 60000) for i in range(10)
            ],
            # Coffee → Work: Strong causality (80%)
            ("coffee", "work"): [
                (base_time + i * 3600000, base_time + i * 3600000 + 10 * 60000) for i in range(8)
            ]
            + [
                (base_time + (8 + i) * 3600000 + 10 * 60000, base_time + (8 + i) * 3600000)
                for i in range(2)
            ],
            # Rain ↔ StayHome: No causality (50%)
            ("rain", "stayhome"): [
                (base_time + i * 3600000, base_time + i * 3600000 + 5 * 60000) for i in range(5)
            ]
            + [
                (base_time + (5 + i) * 3600000 + 5 * 60000, base_time + (5 + i) * 3600000)
                for i in range(5)
            ],
        }

        store = MockObservationStore(observations)
        db = MockDatabaseConnection()

        pairs = [("alarm", "wakeup"), ("coffee", "work"), ("rain", "stayhome")]
        edges = await inference.analyze_cooccurrence_pairs(pairs, store, db)

        # alarm→wakeup and coffee→work have strong causality
        # rain↔stayhome has no clear direction
        assert len(edges) == 2

        # Check alarm→wakeup
        alarm_edge = next((e for e in edges if e.source_id == "alarm"), None)
        assert alarm_edge is not None
        assert alarm_edge.target_id == "wakeup"
        assert alarm_edge.confidence == 1.0

        # Check coffee→work
        coffee_edge = next((e for e in edges if e.source_id == "coffee"), None)
        assert coffee_edge is not None
        assert coffee_edge.target_id == "work"
        assert coffee_edge.confidence == 0.8

    @pytest.mark.asyncio
    async def test_batch_analysis_empty_pairs(
        self,
        inference: GrangerCausalityInference,
    ):
        """Test with no pairs returns empty list."""
        store = MockObservationStore({})
        db = MockDatabaseConnection()

        edges = await inference.analyze_cooccurrence_pairs([], store, db)

        assert edges == []

    @pytest.mark.asyncio
    async def test_batch_analysis_insufficient_observations(
        self,
        inference: GrangerCausalityInference,
        base_time: int,
    ):
        """Test pairs with insufficient observations are skipped."""
        observations = {
            # Only 3 observations (below min_observations=5)
            ("entity_a", "entity_b"): [
                (base_time + i * 3600000, base_time + i * 3600000 + 5 * 60000) for i in range(3)
            ],
        }

        store = MockObservationStore(observations)
        db = MockDatabaseConnection()

        edges = await inference.analyze_cooccurrence_pairs([("entity_a", "entity_b")], store, db)

        assert edges == []


# =============================================================================
# Test: Configuration Validation
# =============================================================================


class TestCausalityConfigValidation:
    """Tests for CausalityConfig validation."""

    def test_valid_config(self):
        """Valid config should not raise."""
        config = CausalityConfig(
            min_observations=5,
            causality_threshold=0.75,
            temporal_window_minutes=60,
            simultaneous_threshold_minutes=1,
        )
        config.validate()  # Should not raise

    def test_invalid_min_observations(self):
        """min_observations < 1 should raise."""
        config = CausalityConfig(min_observations=0)
        with pytest.raises(ValueError, match="min_observations must be >= 1"):
            config.validate()

    def test_invalid_causality_threshold_low(self):
        """causality_threshold <= 0 should raise."""
        config = CausalityConfig(causality_threshold=0.0)
        with pytest.raises(ValueError, match="causality_threshold must be in"):
            config.validate()

    def test_invalid_causality_threshold_high(self):
        """causality_threshold >= 1 should raise."""
        config = CausalityConfig(causality_threshold=1.0)
        with pytest.raises(ValueError, match="causality_threshold must be in"):
            config.validate()

    def test_invalid_temporal_window(self):
        """temporal_window_minutes < 1 should raise."""
        config = CausalityConfig(temporal_window_minutes=0)
        with pytest.raises(ValueError, match="temporal_window_minutes must be >= 1"):
            config.validate()

    def test_invalid_simultaneous_threshold(self):
        """simultaneous_threshold_minutes < 0 should raise."""
        config = CausalityConfig(simultaneous_threshold_minutes=-1)
        with pytest.raises(ValueError, match="simultaneous_threshold_minutes must be >= 0"):
            config.validate()


# =============================================================================
# Test: Utility Functions
# =============================================================================


class TestUtilityFunctions:
    """Tests for utility functions."""

    def test_generate_ulid_uniqueness(self):
        """Generated ULIDs should be unique."""
        ulids = [generate_ulid() for _ in range(100)]
        assert len(set(ulids)) == 100

    def test_generate_ulid_format(self):
        """Generated ULID should be 26 characters."""
        ulid = generate_ulid()
        assert len(ulid) == 26
        # Should only contain Crockford Base32 chars
        valid_chars = set("0123456789ABCDEFGHJKMNPQRSTVWXYZ")
        assert all(c in valid_chars for c in ulid)

    def test_now_ms(self):
        """now_ms should return current time in milliseconds."""
        import time

        before = int(time.time() * 1000)
        result = now_ms()
        after = int(time.time() * 1000)

        assert before <= result <= after


# =============================================================================
# Test: Causal Pattern Examples from Spec
# =============================================================================


class TestCausalPatternExamples:
    """Test patterns from Dossier C.5.2 examples."""

    @pytest.fixture
    def inference(self) -> GrangerCausalityInference:
        """Inference with default config."""
        return GrangerCausalityInference()

    def test_alarm_wakeup_pattern(
        self,
        inference: GrangerCausalityInference,
    ):
        """
        'Alarm' always before 'Wake up' → 0.95 ratio → Alarm CAUSES Wake_up.
        """
        base = 1704067200000
        # 19 of 20 times Alarm before Wakeup (95%)
        observations = [(base + i * 3600000, base + i * 3600000 + 10 * 60000) for i in range(19)]
        # 1 time Wakeup before Alarm (perhaps woke up before alarm)
        observations.append((base + 19 * 3600000 + 10 * 60000, base + 19 * 3600000))

        result = inference.infer_causal_direction("alarm", "wakeup", observations)

        assert result is not None
        assert result.source_id == "alarm"
        assert result.target_id == "wakeup"
        assert result.confidence == 0.95

    def test_coffee_work_pattern(
        self,
        inference: GrangerCausalityInference,
    ):
        """
        'Coffee' before 'Work start' → 0.82 ratio → Coffee CAUSES Work_start.
        """
        base = 1704067200000
        # 82% of observations: Coffee before Work
        observations = []
        for i in range(82):
            observations.append((base + i * 3600000, base + i * 3600000 + 15 * 60000))
        for i in range(18):
            observations.append((base + (82 + i) * 3600000 + 15 * 60000, base + (82 + i) * 3600000))

        result = inference.infer_causal_direction("coffee", "work_start", observations)

        assert result is not None
        assert result.source_id == "coffee"
        assert result.target_id == "work_start"
        assert result.confidence == 0.82

    def test_rain_stayhome_no_causality(
        self,
        inference: GrangerCausalityInference,
    ):
        """
        'Rain' mixed with 'Stay home' → 0.55 ratio → No causal edge (correlation only).
        """
        base = 1704067200000
        # 55% Rain before StayHome, 45% reverse
        observations = []
        for i in range(11):
            observations.append((base + i * 3600000, base + i * 3600000 + 30 * 60000))
        for i in range(9):
            observations.append((base + (11 + i) * 3600000 + 30 * 60000, base + (11 + i) * 3600000))

        result = inference.infer_causal_direction("rain", "stay_home", observations)

        assert result is None  # No clear causality
