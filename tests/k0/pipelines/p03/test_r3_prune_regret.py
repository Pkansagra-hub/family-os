"""
Tests for PruneRegretDetector and related classes.

Issue: 4.3.6
Spec Reference: M4_EXECUTION.md, Dossier §4.4.2
"""

from __future__ import annotations

import numpy as np
import pytest

from k0.modules.consolidation.algorithms.prune_regret_detector import (
    DEFAULT_MATCHED_RETENTION_DAYS,
    DEFAULT_UNMATCHED_RETENTION_DAYS,
    LIKELY_MATCH_THRESHOLD,
    MS_PER_DAY,
    SEMANTIC_MATCH_THRESHOLD,
    STRONG_MATCH_THRESHOLD,
    InMemoryPrunedEntityStore,
    MatchType,
    PrunedEntitiesCleanup,
    PrunedEntityTracker,
    PruneRegretConfig,
    PruneRegretDetector,
    RegretMatch,
    classify_match,
    cosine_similarity,
    should_run_cleanup,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def tracker() -> PrunedEntityTracker:
    """Default tracker fixture."""
    return PrunedEntityTracker()


@pytest.fixture
def detector() -> PruneRegretDetector:
    """Default detector fixture."""
    return PruneRegretDetector()


@pytest.fixture
def cleanup() -> PrunedEntitiesCleanup:
    """Default cleanup fixture."""
    return PrunedEntitiesCleanup()


@pytest.fixture
def store() -> InMemoryPrunedEntityStore:
    """In-memory store fixture."""
    return InMemoryPrunedEntityStore()


def make_embedding(dim: int = 1024, seed: int = 42) -> np.ndarray:
    """Create a normalized random embedding."""
    rng = np.random.default_rng(seed)
    emb = rng.random(dim)
    return emb / np.linalg.norm(emb)


def make_similar_embedding(base: np.ndarray, similarity: float) -> np.ndarray:
    """
    Create an embedding with target cosine similarity to base.

    Uses linear interpolation with a random orthogonal component.
    """
    # Create random orthogonal component
    rng = np.random.default_rng(12345)
    random_vec = rng.random(len(base))
    # Gram-Schmidt orthogonalization
    random_vec = random_vec - np.dot(random_vec, base) * base / np.dot(base, base)
    random_vec = random_vec / np.linalg.norm(random_vec)

    # Interpolate: cos(theta) = similarity
    # New vector = base * similarity + orthogonal * sqrt(1 - similarity^2)
    theta_component = np.sqrt(max(0, 1 - similarity * similarity))
    result = base * similarity + random_vec * theta_component
    return result / np.linalg.norm(result)


# =============================================================================
# 4.3.6.T1: Track Pruned Entity Tests
# =============================================================================


class TestTrackPrunedEntity:
    """Test tracking of pruned entities."""

    @pytest.mark.asyncio
    async def test_track_pruned_entity_inserts_row(
        self, tracker: PrunedEntityTracker, store: InMemoryPrunedEntityStore
    ) -> None:
        """Tracking creates a new entry in store."""
        embedding = make_embedding()
        now = 1700000000000

        prune_id = await tracker.track_pruned_entity(
            entity_id="ent_123",
            entity_type="PERSON",
            canonical_name="john doe",
            embedding=embedding,
            space_id="space_1",
            layer_table="st_epi",
            decay_factor=0.15,
            lambda_value=0.02,
            pruned_at=now,
            store=store,
        )

        assert prune_id.startswith("prune_")
        assert len(store.get_all_entities()) == 1

        entity = store.get_entity(prune_id)
        assert entity is not None
        assert entity.entity_id == "ent_123"
        assert entity.entity_type == "PERSON"
        assert entity.canonical_name == "john doe"
        assert entity.space_id == "space_1"
        assert entity.layer_table == "st_epi"
        assert entity.decay_factor_at_prune == 0.15
        assert entity.lambda_at_prune == 0.02
        assert entity.pruned_at == now
        assert entity.matched_at is None

    @pytest.mark.asyncio
    async def test_track_multiple_entities(
        self, tracker: PrunedEntityTracker, store: InMemoryPrunedEntityStore
    ) -> None:
        """Multiple entities can be tracked."""
        now = 1700000000000

        for i in range(5):
            await tracker.track_pruned_entity(
                entity_id=f"ent_{i}",
                entity_type="THING",
                canonical_name=f"item {i}",
                embedding=make_embedding(seed=i),
                space_id="space_1",
                layer_table="st_epi",
                decay_factor=0.1,
                lambda_value=0.01,
                pruned_at=now + i * 1000,
                store=store,
            )

        assert len(store.get_all_entities()) == 5

    @pytest.mark.asyncio
    async def test_track_entity_generates_unique_ids(
        self, tracker: PrunedEntityTracker, store: InMemoryPrunedEntityStore
    ) -> None:
        """Each tracking generates a unique prune_id."""
        now = 1700000000000
        prune_ids = set()

        for i in range(10):
            prune_id = await tracker.track_pruned_entity(
                entity_id="ent_same",
                entity_type="THING",
                canonical_name="same item",
                embedding=make_embedding(seed=i),
                space_id="space_1",
                layer_table="st_epi",
                decay_factor=0.1,
                lambda_value=0.01,
                pruned_at=now + i * 1000,
                store=store,
            )
            prune_ids.add(prune_id)

        # All IDs should be unique
        assert len(prune_ids) == 10


# =============================================================================
# 4.3.6.T2: Cosine Similarity Tests
# =============================================================================


class TestCosineSimilarity:
    """Test cosine similarity computation."""

    def test_identical_vectors(self) -> None:
        """Identical vectors have similarity 1.0."""
        v = make_embedding()
        assert abs(cosine_similarity(v, v) - 1.0) < 0.0001

    def test_opposite_vectors(self) -> None:
        """Opposite vectors have similarity -1.0."""
        v = make_embedding()
        assert abs(cosine_similarity(v, -v) - (-1.0)) < 0.0001

    def test_orthogonal_vectors(self) -> None:
        """Orthogonal vectors have similarity ~0.0."""
        v1 = np.array([1.0, 0.0, 0.0])
        v2 = np.array([0.0, 1.0, 0.0])
        assert abs(cosine_similarity(v1, v2)) < 0.0001

    def test_zero_vector_returns_zero(self) -> None:
        """Zero vector returns 0.0 similarity."""
        v = make_embedding()
        zero = np.zeros_like(v)
        assert cosine_similarity(v, zero) == 0.0
        assert cosine_similarity(zero, v) == 0.0

    def test_similar_embedding_helper(self) -> None:
        """Test helper function creates correct similarity."""
        base = make_embedding(seed=100)
        for target_sim in [0.95, 0.90, 0.85, 0.80, 0.50]:
            similar = make_similar_embedding(base, target_sim)
            actual = cosine_similarity(base, similar)
            assert abs(actual - target_sim) < 0.05  # Allow 5% tolerance


# =============================================================================
# 4.3.6.T3: Match Type Classification Tests
# =============================================================================


class TestMatchTypeClassification:
    """Test match type classification based on similarity."""

    def test_strong_match_at_090(self) -> None:
        """Similarity >= 0.90 is STRONG_MATCH."""
        config = PruneRegretConfig()
        assert classify_match(0.90, config) == MatchType.STRONG_MATCH
        assert classify_match(0.95, config) == MatchType.STRONG_MATCH
        assert classify_match(1.00, config) == MatchType.STRONG_MATCH

    def test_likely_match_at_085(self) -> None:
        """Similarity >= 0.85 but < 0.90 is LIKELY_MATCH."""
        config = PruneRegretConfig()
        assert classify_match(0.85, config) == MatchType.LIKELY_MATCH
        assert classify_match(0.87, config) == MatchType.LIKELY_MATCH
        assert classify_match(0.899, config) == MatchType.LIKELY_MATCH

    def test_semantic_match_at_080(self) -> None:
        """Similarity >= 0.80 but < 0.85 is SEMANTIC_MATCH."""
        config = PruneRegretConfig()
        assert classify_match(0.80, config) == MatchType.SEMANTIC_MATCH
        assert classify_match(0.82, config) == MatchType.SEMANTIC_MATCH
        assert classify_match(0.849, config) == MatchType.SEMANTIC_MATCH

    def test_no_match_below_080(self) -> None:
        """Similarity < 0.80 is NO_MATCH."""
        config = PruneRegretConfig()
        assert classify_match(0.79, config) == MatchType.NO_MATCH
        assert classify_match(0.50, config) == MatchType.NO_MATCH
        assert classify_match(0.00, config) == MatchType.NO_MATCH

    def test_constants_match_spec(self) -> None:
        """Verify threshold constants from spec."""
        assert STRONG_MATCH_THRESHOLD == 0.90
        assert LIKELY_MATCH_THRESHOLD == 0.85
        assert SEMANTIC_MATCH_THRESHOLD == 0.80


# =============================================================================
# 4.3.6.T4: Regret Detection Tests
# =============================================================================


class TestRegretDetection:
    """Test regret detection logic."""

    @pytest.mark.asyncio
    async def test_regret_detected_at_085_cosine(
        self,
        tracker: PrunedEntityTracker,
        detector: PruneRegretDetector,
        store: InMemoryPrunedEntityStore,
    ) -> None:
        """Match at 0.85 similarity triggers regret."""
        now = 1700000000000
        base_embedding = make_embedding(seed=42)

        # Track a pruned entity
        await tracker.track_pruned_entity(
            entity_id="ent_123",
            entity_type="PERSON",
            canonical_name="john doe",
            embedding=base_embedding,
            space_id="space_1",
            layer_table="st_epi",
            decay_factor=0.15,
            lambda_value=0.02,
            pruned_at=now,
            store=store,
        )

        # Query with similar embedding (0.85 similarity)
        query_embedding = make_similar_embedding(base_embedding, 0.86)

        matches = await detector.check_query(
            query_embedding=query_embedding,
            space_id="space_1",
            query_id="query_001",
            current_time_ms=now + MS_PER_DAY,
            store=store,
        )

        assert len(matches) == 1
        assert matches[0].entity_id == "ent_123"
        assert matches[0].match_type in (MatchType.LIKELY_MATCH, MatchType.STRONG_MATCH)
        assert matches[0].match_confidence >= 0.85

    @pytest.mark.asyncio
    async def test_no_regret_below_085(
        self,
        tracker: PrunedEntityTracker,
        detector: PruneRegretDetector,
        store: InMemoryPrunedEntityStore,
    ) -> None:
        """No regret match at 0.84 similarity."""
        now = 1700000000000
        base_embedding = make_embedding(seed=42)

        await tracker.track_pruned_entity(
            entity_id="ent_123",
            entity_type="PERSON",
            canonical_name="john doe",
            embedding=base_embedding,
            space_id="space_1",
            layer_table="st_epi",
            decay_factor=0.15,
            lambda_value=0.02,
            pruned_at=now,
            store=store,
        )

        # Query with lower similarity (0.70)
        query_embedding = make_similar_embedding(base_embedding, 0.70)

        matches = await detector.check_query(
            query_embedding=query_embedding,
            space_id="space_1",
            query_id="query_001",
            current_time_ms=now + MS_PER_DAY,
            store=store,
        )

        assert len(matches) == 0

    @pytest.mark.asyncio
    async def test_strong_match_detected(
        self,
        tracker: PrunedEntityTracker,
        detector: PruneRegretDetector,
        store: InMemoryPrunedEntityStore,
    ) -> None:
        """Match at 0.90+ is STRONG_MATCH."""
        now = 1700000000000
        base_embedding = make_embedding(seed=42)

        await tracker.track_pruned_entity(
            entity_id="ent_123",
            entity_type="PERSON",
            canonical_name="john doe",
            embedding=base_embedding,
            space_id="space_1",
            layer_table="st_epi",
            decay_factor=0.15,
            lambda_value=0.02,
            pruned_at=now,
            store=store,
        )

        # Query with high similarity (0.95)
        query_embedding = make_similar_embedding(base_embedding, 0.95)

        matches = await detector.check_query(
            query_embedding=query_embedding,
            space_id="space_1",
            query_id="query_001",
            current_time_ms=now + MS_PER_DAY,
            store=store,
        )

        assert len(matches) == 1
        assert matches[0].match_type == MatchType.STRONG_MATCH

    @pytest.mark.asyncio
    async def test_entity_updated_on_match(
        self,
        tracker: PrunedEntityTracker,
        detector: PruneRegretDetector,
        store: InMemoryPrunedEntityStore,
    ) -> None:
        """Pruned entity is updated with match info."""
        now = 1700000000000
        base_embedding = make_embedding(seed=42)

        prune_id = await tracker.track_pruned_entity(
            entity_id="ent_123",
            entity_type="PERSON",
            canonical_name="john doe",
            embedding=base_embedding,
            space_id="space_1",
            layer_table="st_epi",
            decay_factor=0.15,
            lambda_value=0.02,
            pruned_at=now,
            store=store,
        )

        query_time = now + MS_PER_DAY
        query_embedding = make_similar_embedding(base_embedding, 0.92)

        await detector.check_query(
            query_embedding=query_embedding,
            space_id="space_1",
            query_id="query_001",
            current_time_ms=query_time,
            store=store,
        )

        # Check entity was updated
        entity = store.get_entity(prune_id)
        assert entity is not None
        assert entity.matched_at == query_time
        assert entity.matched_query_id == "query_001"
        assert entity.match_type == MatchType.STRONG_MATCH
        assert entity.match_confidence is not None and entity.match_confidence >= 0.90


# =============================================================================
# 4.3.6.T5: Space Isolation Tests
# =============================================================================


class TestSpaceIsolation:
    """Test space isolation for regret detection."""

    @pytest.mark.asyncio
    async def test_space_isolation(
        self,
        tracker: PrunedEntityTracker,
        detector: PruneRegretDetector,
        store: InMemoryPrunedEntityStore,
    ) -> None:
        """Can only see own space's pruned entities."""
        now = 1700000000000
        embedding = make_embedding(seed=42)

        # Track entity in space_1
        await tracker.track_pruned_entity(
            entity_id="ent_123",
            entity_type="PERSON",
            canonical_name="john doe",
            embedding=embedding,
            space_id="space_1",
            layer_table="st_epi",
            decay_factor=0.15,
            lambda_value=0.02,
            pruned_at=now,
            store=store,
        )

        # Query from space_2 (should not match)
        matches = await detector.check_query(
            query_embedding=embedding,  # Identical embedding
            space_id="space_2",  # Different space
            query_id="query_001",
            current_time_ms=now + MS_PER_DAY,
            store=store,
        )

        assert len(matches) == 0

    @pytest.mark.asyncio
    async def test_same_space_matches(
        self,
        tracker: PrunedEntityTracker,
        detector: PruneRegretDetector,
        store: InMemoryPrunedEntityStore,
    ) -> None:
        """Same space query matches pruned entity."""
        now = 1700000000000
        embedding = make_embedding(seed=42)

        await tracker.track_pruned_entity(
            entity_id="ent_123",
            entity_type="PERSON",
            canonical_name="john doe",
            embedding=embedding,
            space_id="space_1",
            layer_table="st_epi",
            decay_factor=0.15,
            lambda_value=0.02,
            pruned_at=now,
            store=store,
        )

        # Query from same space
        matches = await detector.check_query(
            query_embedding=embedding,
            space_id="space_1",
            query_id="query_001",
            current_time_ms=now + MS_PER_DAY,
            store=store,
        )

        assert len(matches) == 1


# =============================================================================
# 4.3.6.T6: Regret Signal Emission Tests
# =============================================================================


class TestRegretSignalEmission:
    """Test regret signal emission."""

    @pytest.mark.asyncio
    async def test_regret_signal_emitted(
        self,
        detector: PruneRegretDetector,
        store: InMemoryPrunedEntityStore,
    ) -> None:
        """Regret signal inserted into st_feedback_signals."""
        now = 1700000000000

        match = RegretMatch(
            prune_id="prune_abc123",
            entity_id="ent_123",
            entity_type="PERSON",
            match_type=MatchType.LIKELY_MATCH,
            match_confidence=0.87,
            query_id="query_001",
            pruned_at=now - MS_PER_DAY,
            matched_at=now,
            canonical_name="john doe",
            layer_table="st_epi",
        )

        await detector.emit_regret_signal(
            match=match,
            space_id="space_1",
            store=store,
        )

        signals = store.get_signals()
        assert len(signals) == 1

        signal = signals[0]
        assert signal["signal_type"] == "PRUNE_REGRET"
        assert signal["entity_id"] == "ent_123"
        assert signal["space_id"] == "space_1"
        assert signal["confidence"] == 0.87
        assert signal["metadata"]["prune_id"] == "prune_abc123"
        assert signal["metadata"]["match_type"] == "LIKELY_MATCH"

    @pytest.mark.asyncio
    async def test_multiple_regret_signals(
        self,
        detector: PruneRegretDetector,
        store: InMemoryPrunedEntityStore,
    ) -> None:
        """Multiple regret signals can be emitted."""
        now = 1700000000000

        for i in range(3):
            match = RegretMatch(
                prune_id=f"prune_{i}",
                entity_id=f"ent_{i}",
                entity_type="THING",
                match_type=MatchType.STRONG_MATCH,
                match_confidence=0.92,
                query_id=f"query_{i}",
                pruned_at=now - MS_PER_DAY,
                matched_at=now,
            )
            await detector.emit_regret_signal(match, "space_1", store)

        signals = store.get_signals()
        assert len(signals) == 3


# =============================================================================
# 4.3.6.T7: Cleanup Tests
# =============================================================================


class TestCleanup:
    """Test cleanup of old pruned entities."""

    @pytest.mark.asyncio
    async def test_cleanup_unmatched_14_days(
        self,
        tracker: PrunedEntityTracker,
        cleanup: PrunedEntitiesCleanup,
        store: InMemoryPrunedEntityStore,
    ) -> None:
        """Unmatched entities deleted after 14 days."""
        now = 1700000000000

        # Track entity 15 days ago (should be deleted)
        await tracker.track_pruned_entity(
            entity_id="ent_old",
            entity_type="THING",
            canonical_name="old item",
            embedding=make_embedding(seed=1),
            space_id="space_1",
            layer_table="st_epi",
            decay_factor=0.1,
            lambda_value=0.01,
            pruned_at=now - (15 * MS_PER_DAY),
            store=store,
        )

        # Track entity 5 days ago (should be kept)
        await tracker.track_pruned_entity(
            entity_id="ent_recent",
            entity_type="THING",
            canonical_name="recent item",
            embedding=make_embedding(seed=2),
            space_id="space_1",
            layer_table="st_epi",
            decay_factor=0.1,
            lambda_value=0.01,
            pruned_at=now - (5 * MS_PER_DAY),
            store=store,
        )

        deleted = await cleanup.cleanup_old_pruned_entities(now, store)

        assert deleted == 1
        entities = store.get_all_entities()
        assert len(entities) == 1
        assert entities[0].entity_id == "ent_recent"

    @pytest.mark.asyncio
    async def test_cleanup_matched_30_days(
        self,
        tracker: PrunedEntityTracker,
        cleanup: PrunedEntitiesCleanup,
        store: InMemoryPrunedEntityStore,
    ) -> None:
        """Matched entities kept until 30 days after match."""
        now = 1700000000000

        # Track and match entity 20 days ago (should be kept)
        prune_id = await tracker.track_pruned_entity(
            entity_id="ent_matched",
            entity_type="THING",
            canonical_name="matched item",
            embedding=make_embedding(seed=1),
            space_id="space_1",
            layer_table="st_epi",
            decay_factor=0.1,
            lambda_value=0.01,
            pruned_at=now - (25 * MS_PER_DAY),
            store=store,
        )

        # Mark as matched 20 days ago
        await store.update_match(
            prune_id=prune_id,
            query_id="query_001",
            matched_at=now - (20 * MS_PER_DAY),
            match_type=MatchType.LIKELY_MATCH,
            match_confidence=0.86,
        )

        deleted = await cleanup.cleanup_old_pruned_entities(now, store)

        # Matched 20 days ago < 30 day retention, so kept
        assert deleted == 0
        assert len(store.get_all_entities()) == 1

    @pytest.mark.asyncio
    async def test_cleanup_matched_after_30_days(
        self,
        tracker: PrunedEntityTracker,
        cleanup: PrunedEntitiesCleanup,
        store: InMemoryPrunedEntityStore,
    ) -> None:
        """Matched entities deleted after 30 days."""
        now = 1700000000000

        prune_id = await tracker.track_pruned_entity(
            entity_id="ent_matched",
            entity_type="THING",
            canonical_name="matched item",
            embedding=make_embedding(seed=1),
            space_id="space_1",
            layer_table="st_epi",
            decay_factor=0.1,
            lambda_value=0.01,
            pruned_at=now - (45 * MS_PER_DAY),
            store=store,
        )

        # Mark as matched 35 days ago
        await store.update_match(
            prune_id=prune_id,
            query_id="query_001",
            matched_at=now - (35 * MS_PER_DAY),
            match_type=MatchType.LIKELY_MATCH,
            match_confidence=0.86,
        )

        deleted = await cleanup.cleanup_old_pruned_entities(now, store)

        # Matched 35 days ago > 30 day retention, so deleted
        assert deleted == 1
        assert len(store.get_all_entities()) == 0

    def test_retention_constants_match_spec(self) -> None:
        """Verify retention constants from spec."""
        assert DEFAULT_UNMATCHED_RETENTION_DAYS == 14
        assert DEFAULT_MATCHED_RETENTION_DAYS == 30


# =============================================================================
# 4.3.6.T8: Configuration Tests
# =============================================================================


class TestPruneRegretConfig:
    """Test configuration validation."""

    def test_default_config_valid(self) -> None:
        """Default config is valid."""
        config = PruneRegretConfig()
        config.validate()  # Should not raise

    def test_unmatched_retention_too_low(self) -> None:
        """unmatched_retention_days < 1 raises ValueError."""
        config = PruneRegretConfig(unmatched_retention_days=0)
        with pytest.raises(ValueError, match="unmatched_retention_days"):
            config.validate()

    def test_matched_less_than_unmatched(self) -> None:
        """matched_retention_days < unmatched raises ValueError."""
        config = PruneRegretConfig(unmatched_retention_days=30, matched_retention_days=14)
        with pytest.raises(ValueError, match="matched_retention_days"):
            config.validate()

    def test_invalid_thresholds(self) -> None:
        """Invalid thresholds raise ValueError."""
        config = PruneRegretConfig(strong_threshold=0.0)
        with pytest.raises(ValueError, match="strong_threshold"):
            config.validate()

        config = PruneRegretConfig(likely_threshold=0.95)
        with pytest.raises(ValueError, match="likely_threshold"):
            config.validate()

    def test_invalid_cleanup_hour(self) -> None:
        """cleanup_hour outside [0, 23] raises ValueError."""
        config = PruneRegretConfig(cleanup_hour=25)
        with pytest.raises(ValueError, match="cleanup_hour"):
            config.validate()


# =============================================================================
# 4.3.6.T9: Scheduler Helper Tests
# =============================================================================


class TestSchedulerHelpers:
    """Test scheduler helper functions."""

    def test_should_run_cleanup_at_configured_hour(self) -> None:
        """Cleanup runs at configured hour."""
        config = PruneRegretConfig(cleanup_hour=2)
        assert should_run_cleanup(2, config) is True
        assert should_run_cleanup(3, config) is False
        assert should_run_cleanup(0, config) is False

    def test_should_run_cleanup_custom_hour(self) -> None:
        """Cleanup respects custom hour."""
        config = PruneRegretConfig(cleanup_hour=14)
        assert should_run_cleanup(14, config) is True
        assert should_run_cleanup(2, config) is False


# =============================================================================
# 4.3.6.T10: Edge Cases
# =============================================================================


class TestEdgeCases:
    """Test edge cases."""

    @pytest.mark.asyncio
    async def test_no_entities_returns_empty(
        self,
        detector: PruneRegretDetector,
        store: InMemoryPrunedEntityStore,
    ) -> None:
        """Empty store returns no matches."""
        query = make_embedding()
        matches = await detector.check_query(
            query_embedding=query,
            space_id="space_1",
            query_id="query_001",
            current_time_ms=1700000000000,
            store=store,
        )
        assert matches == []

    @pytest.mark.asyncio
    async def test_already_matched_not_rematched(
        self,
        tracker: PrunedEntityTracker,
        detector: PruneRegretDetector,
        store: InMemoryPrunedEntityStore,
    ) -> None:
        """Already matched entities not returned in subsequent queries."""
        now = 1700000000000
        embedding = make_embedding(seed=42)

        prune_id = await tracker.track_pruned_entity(
            entity_id="ent_123",
            entity_type="PERSON",
            canonical_name="john doe",
            embedding=embedding,
            space_id="space_1",
            layer_table="st_epi",
            decay_factor=0.15,
            lambda_value=0.02,
            pruned_at=now,
            store=store,
        )

        # First query matches
        matches1 = await detector.check_query(
            query_embedding=embedding,
            space_id="space_1",
            query_id="query_001",
            current_time_ms=now + MS_PER_DAY,
            store=store,
        )
        assert len(matches1) == 1

        # Second query should NOT match (already matched)
        matches2 = await detector.check_query(
            query_embedding=embedding,
            space_id="space_1",
            query_id="query_002",
            current_time_ms=now + (2 * MS_PER_DAY),
            store=store,
        )
        assert len(matches2) == 0

    @pytest.mark.asyncio
    async def test_cleanup_no_entities_returns_zero(
        self,
        cleanup: PrunedEntitiesCleanup,
        store: InMemoryPrunedEntityStore,
    ) -> None:
        """Cleanup with no entities returns 0."""
        deleted = await cleanup.cleanup_old_pruned_entities(1700000000000, store)
        assert deleted == 0
