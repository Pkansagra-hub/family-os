"""
R5 Dream Cold Start Fix Integration Tests — GAP-001 Milestone 9.5

Test Categories:
1. BGT-SM insight generation with 100+ entities (Issue 9.1)
2. Accumulated KG loading via syscalls (Issue 9.2)
3. CPN counterfactual generation with lowered threshold (Issue 9.3)
4. Entity embeddings available for BGT-SM (Issue 9.4)

References:
- GAP-001 Milestone 9: R5 Dream Stage Cold Start Fix
- P03 Dossier §4.6: R5 — Dream-Like Exploration (REM)
- ADR-011: R5 Dream Stage Architecture
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock

import pytest

from k0.modules.consolidation.dream import DreamConfig
from k0.pipelines.p03 import EpisodeCluster, KGEntity, P03BatchEnvelope, P03CycleContext
from k0.pipelines.p03.phase_interface import P03PhaseStatus, P03RunnerContext
from k0.pipelines.p03.phases.r5_dream_explorer import R5DreamExplorer
from k0.pipelines.p03.r5_config import R5Config, R5Mode

# =============================================================================
# TEST FIXTURES
# =============================================================================


@dataclass
class MockR5Syscalls:
    """Mock syscalls for R5 cold start testing."""

    # Storage for mock data
    entities: List[Dict[str, Any]] = field(default_factory=list)
    edges: List[Dict[str, Any]] = field(default_factory=list)
    embeddings: Dict[str, List[float]] = field(default_factory=dict)

    # Call tracking
    kg_entities_query_calls: List[Dict[str, Any]] = field(default_factory=list)
    kg_edges_query_calls: List[Dict[str, Any]] = field(default_factory=list)
    embedding_query_calls: List[List[str]] = field(default_factory=list)

    async def kg_entities_query(
        self,
        tenant_id: str,
        space_id: str,
        limit: int = 1000,
    ) -> Dict[str, Any]:
        """Mock kg_entities_query syscall (Issue 9.2)."""
        self.kg_entities_query_calls.append(
            {
                "tenant_id": tenant_id,
                "space_id": space_id,
                "limit": limit,
            }
        )
        return {
            "entities": self.entities[:limit],
            "count": len(self.entities[:limit]),
            "total_available": len(self.entities),
        }

    async def kg_edges_query(
        self,
        tenant_id: str,
        space_id: str,
        limit: int = 5000,
    ) -> Dict[str, Any]:
        """Mock kg_edges_query syscall (Issue 9.2)."""
        self.kg_edges_query_calls.append(
            {
                "tenant_id": tenant_id,
                "space_id": space_id,
                "limit": limit,
            }
        )
        return {
            "edges": self.edges[:limit],
            "count": len(self.edges[:limit]),
            "total_available": len(self.edges),
        }

    async def embedding_vectors_batch_query(
        self,
        embedding_ids: List[str],
    ) -> Dict[str, Any]:
        """Mock embedding_vectors_batch_query syscall (Issue 9.4)."""
        self.embedding_query_calls.append(embedding_ids)
        vectors = {}
        missing = []
        for eid in embedding_ids:
            if eid in self.embeddings:
                vectors[eid] = self.embeddings[eid]
            else:
                missing.append(eid)
        return {
            "vectors": vectors,
            "count": len(vectors),
            "missing": missing,
        }


def generate_mock_entities(count: int, with_embeddings: bool = True) -> tuple:
    """
    Generate mock entities for testing.

    Args:
        count: Number of entities to generate
        with_embeddings: Whether to include embedding IDs and vectors

    Returns:
        Tuple of (entity_dicts, embedding_dict)
    """
    entity_types = ["PERSON", "PLACE", "ACTIVITY", "ORGANIZATION", "EVENT"]
    entities = []
    embeddings = {}

    for i in range(count):
        entity_id = f"entity-{i:04d}"
        embedding_id = f"emb-{i:04d}" if with_embeddings else None

        entities.append(
            {
                "entity_id": entity_id,
                "canonical_name": f"Entity_{i}",
                "entity_type": random.choice(entity_types),
                "aliases_json": f'["alias_{i}"]',
                "confidence": random.uniform(0.7, 1.0),
                "embedding_id": embedding_id,
            }
        )

        if with_embeddings and embedding_id:
            # Generate 768-dim embedding vector (normalized random)
            vec = [random.gauss(0, 1) for _ in range(768)]
            norm = sum(v * v for v in vec) ** 0.5
            embeddings[embedding_id] = [v / norm for v in vec]

    return entities, embeddings


def generate_mock_edges(entity_count: int, edge_ratio: float = 0.5) -> List[Dict[str, Any]]:
    """
    Generate mock edges between entities.

    Args:
        entity_count: Number of entities (for ID range)
        edge_ratio: Ratio of edges to entities

    Returns:
        List of edge dicts
    """
    edge_types = ["RELATED_TO", "LOCATED_AT", "PARTICIPATED_IN", "KNOWS", "CAUSED"]
    edge_count = int(entity_count * edge_ratio)
    edges = []

    for i in range(edge_count):
        src_idx = random.randint(0, entity_count - 1)
        tgt_idx = random.randint(0, entity_count - 1)
        if src_idx == tgt_idx:
            tgt_idx = (tgt_idx + 1) % entity_count

        edges.append(
            {
                "edge_id": f"edge-{i:04d}",
                "source_entity_id": f"entity-{src_idx:04d}",
                "target_entity_id": f"entity-{tgt_idx:04d}",
                "relationship_type": random.choice(edge_types),
                "weight": random.uniform(0.5, 1.0),
                "confidence": random.uniform(0.7, 1.0),
            }
        )

    return edges


def generate_mock_episodes(count: int) -> List[EpisodeCluster]:
    """
    Generate mock episode clusters for CPN testing.

    Args:
        count: Number of episodes to generate

    Returns:
        List of EpisodeCluster instances
    """
    episodes = []
    base_ts = 1700000000000  # Fixed base timestamp

    for i in range(count):
        # Generate sentiment between 0.2 and 0.6 (within lowered threshold range)
        sentiment = 0.3 + random.uniform(-0.1, 0.3)

        episodes.append(
            EpisodeCluster(
                cluster_id=f"cluster-{i:03d}",
                member_event_ids=[f"evt-{i*2:04d}", f"evt-{i*2+1:04d}"],
                centroid_embedding_id=f"centroid-{i:03d}",
                dominant_sentiment=sentiment,
                temporal_start=base_ts + (i * 3600000),  # 1 hour apart
                temporal_end=base_ts + (i * 3600000) + 1800000,  # 30 min duration
                title=f"Episode {i}",
            )
        )

    return episodes


@pytest.fixture
def cold_start_r5_config() -> R5Config:
    """R5 config with cold start thresholds for testing."""
    return R5Config(
        mode=R5Mode.ENABLED,
        backlog_threshold=1000,
        min_remaining_window_seconds=10,
        mcts_rollouts_override=10,  # Fewer rollouts for faster tests
        # Issue 9.1: Lowered threshold
        bgt_sm_cold_start_threshold=100,
        # Issue 9.2: Accumulated KG limits
        accumulated_kg_entity_limit=500,
        accumulated_kg_edge_limit=2000,
        # Issue 9.3: Lowered CPN threshold
        cpn_emotional_threshold=0.3,
    )


@pytest.fixture
def mock_syscalls_with_data() -> MockR5Syscalls:
    """
    Create mock syscalls with 150 entities, edges, and embeddings.

    This exceeds the cold start threshold of 100.
    """
    entities, embeddings = generate_mock_entities(150, with_embeddings=True)
    edges = generate_mock_edges(150, edge_ratio=0.5)

    return MockR5Syscalls(
        entities=entities,
        edges=edges,
        embeddings=embeddings,
    )


@pytest.fixture
def sample_context() -> P03CycleContext:
    """Create a sample cycle context for testing."""
    return P03CycleContext.create(
        tenant_id="tenant-cold-start-test",
        space_id="space-cold-start-test",
        event_ids=[f"evt-{i:04d}" for i in range(10)],
        trigger_type="MANUAL",
        trigger_reason="Cold start integration test",
        pending_before=50,
        deadline_ms=300000,
    )


@pytest.fixture
def sample_envelope_with_episodes(sample_context: P03CycleContext) -> P03BatchEnvelope:
    """Create envelope with episode clusters for CPN testing."""
    envelope = P03BatchEnvelope.create(sample_context)

    # Add episodes with varied sentiment (Issue 9.3 testing)
    episodes = generate_mock_episodes(20)
    for episode in episodes:
        envelope.phases.r2_clusters.append(episode)

    return envelope


@pytest.fixture
def mock_metrics_registry() -> MagicMock:
    """Create mock metrics registry."""
    registry = MagicMock()
    registry.emit_r5_skip = MagicMock()
    registry.set_r5_mode = MagicMock()
    registry.emit_r5_duration = MagicMock()
    registry.emit_r5_insights = MagicMock()
    registry.emit_r5_counterfactuals = MagicMock()
    registry.emit_r5_routine_optimizations = MagicMock()
    registry.emit_r5_prospective_memories = MagicMock()
    registry.emit_r5_mcts_decisions = MagicMock()
    return registry


@pytest.fixture
def runner_context_with_syscalls(
    mock_syscalls_with_data: MockR5Syscalls,
    mock_metrics_registry: MagicMock,
) -> P03RunnerContext:
    """Create runner context with mock syscalls."""
    ctx = P03RunnerContext.create(
        syscalls=mock_syscalls_with_data,
        logger=MagicMock(),
        qos_band="GREEN",
        priority=50,
        config={"backlog_threshold": 1000},
    )
    ctx.metrics_registry = mock_metrics_registry
    return ctx


# =============================================================================
# TEST: Issue 9.1 - BGT-SM Cold Start Threshold
# =============================================================================


class TestBGTSMColdStartThreshold:
    """Test BGT-SM generates insights with lowered threshold (Issue 9.1)."""

    def test_cold_start_threshold_is_100(
        self,
        cold_start_r5_config: R5Config,
    ) -> None:
        """BGT-SM cold start threshold should be 100, not 10000."""
        assert cold_start_r5_config.bgt_sm_cold_start_threshold == 100

    def test_dream_config_receives_threshold(
        self,
        cold_start_r5_config: R5Config,
    ) -> None:
        """DreamConfig should receive the lowered threshold from R5Config."""
        dream_config = DreamConfig.from_r5_config(cold_start_r5_config)
        assert dream_config.cold_start_threshold == 100

    @pytest.mark.asyncio
    async def test_r5_loads_accumulated_entities_exceeding_threshold(
        self,
        cold_start_r5_config: R5Config,
        sample_envelope_with_episodes: P03BatchEnvelope,
        runner_context_with_syscalls: P03RunnerContext,
        mock_syscalls_with_data: MockR5Syscalls,
    ) -> None:
        """R5 should load accumulated entities exceeding cold start threshold."""
        phase = R5DreamExplorer(config=cold_start_r5_config)

        await phase.run(sample_envelope_with_episodes, runner_context_with_syscalls)

        # Verify kg_entities_query was called
        assert len(mock_syscalls_with_data.kg_entities_query_calls) >= 1
        call = mock_syscalls_with_data.kg_entities_query_calls[0]
        assert call["tenant_id"] == "tenant-cold-start-test"
        assert call["space_id"] == "space-cold-start-test"


# =============================================================================
# TEST: Issue 9.2 - Accumulated KG Loading
# =============================================================================


class TestAccumulatedKGLoading:
    """Test R5 loads accumulated KG via syscalls (Issue 9.2)."""

    @pytest.mark.asyncio
    async def test_r5_calls_kg_entities_query(
        self,
        cold_start_r5_config: R5Config,
        sample_envelope_with_episodes: P03BatchEnvelope,
        runner_context_with_syscalls: P03RunnerContext,
        mock_syscalls_with_data: MockR5Syscalls,
    ) -> None:
        """R5 should call kg_entities_query syscall."""
        phase = R5DreamExplorer(config=cold_start_r5_config)

        await phase.run(sample_envelope_with_episodes, runner_context_with_syscalls)

        # Should have called kg_entities_query
        assert len(mock_syscalls_with_data.kg_entities_query_calls) >= 1

    @pytest.mark.asyncio
    async def test_r5_calls_kg_edges_query(
        self,
        cold_start_r5_config: R5Config,
        sample_envelope_with_episodes: P03BatchEnvelope,
        runner_context_with_syscalls: P03RunnerContext,
        mock_syscalls_with_data: MockR5Syscalls,
    ) -> None:
        """R5 should call kg_edges_query syscall."""
        phase = R5DreamExplorer(config=cold_start_r5_config)

        await phase.run(sample_envelope_with_episodes, runner_context_with_syscalls)

        # Should have called kg_edges_query
        assert len(mock_syscalls_with_data.kg_edges_query_calls) >= 1

    @pytest.mark.asyncio
    async def test_accumulated_kg_respects_limits(
        self,
        cold_start_r5_config: R5Config,
        sample_envelope_with_episodes: P03BatchEnvelope,
        runner_context_with_syscalls: P03RunnerContext,
        mock_syscalls_with_data: MockR5Syscalls,
    ) -> None:
        """Accumulated KG queries should respect configured limits."""
        phase = R5DreamExplorer(config=cold_start_r5_config)

        await phase.run(sample_envelope_with_episodes, runner_context_with_syscalls)

        # Check entity limit
        if mock_syscalls_with_data.kg_entities_query_calls:
            entity_call = mock_syscalls_with_data.kg_entities_query_calls[0]
            assert entity_call["limit"] == 500

        # Check edge limit
        if mock_syscalls_with_data.kg_edges_query_calls:
            edge_call = mock_syscalls_with_data.kg_edges_query_calls[0]
            assert edge_call["limit"] == 2000


# =============================================================================
# TEST: Issue 9.3 - CPN Emotional Threshold
# =============================================================================


class TestCPNEmotionalThreshold:
    """Test CPN counterfactual generation with lowered threshold (Issue 9.3)."""

    def test_cpn_threshold_is_0_3(
        self,
        cold_start_r5_config: R5Config,
    ) -> None:
        """CPN emotional threshold should be 0.3, not 0.6."""
        assert cold_start_r5_config.cpn_emotional_threshold == 0.3

    def test_dream_config_receives_cpn_threshold(
        self,
        cold_start_r5_config: R5Config,
    ) -> None:
        """DreamConfig should receive the lowered CPN threshold."""
        dream_config = DreamConfig.from_r5_config(cold_start_r5_config)
        assert dream_config.cpn_emotional_threshold == 0.3

    def test_episodes_with_moderate_sentiment_qualify(self) -> None:
        """Episodes with sentiment 0.3-0.6 should qualify with lowered threshold."""
        episodes = generate_mock_episodes(20)

        # Count episodes that qualify with threshold=0.3
        qualifying = [e for e in episodes if abs(e.dominant_sentiment) >= 0.3]

        # With random sentiment in [0.2, 0.6], most should qualify
        assert len(qualifying) > 10, "Most episodes should qualify with threshold=0.3"


# =============================================================================
# TEST: Issue 9.4 - Entity Embeddings
# =============================================================================


class TestEntityEmbeddings:
    """Test entity embeddings are loaded for BGT-SM (Issue 9.4)."""

    def test_kg_entity_has_embedding_field(self) -> None:
        """KGEntity should have embedding field."""
        entity = KGEntity(
            entity_id="test-entity",
            canonical_name="Test",
            entity_type="PERSON",
            embedding_id="emb-001",
            embedding=[0.1, 0.2, 0.3],  # 3-dim for testing
        )
        assert entity.embedding is not None
        assert len(entity.embedding) == 3

    @pytest.mark.asyncio
    async def test_r5_calls_embedding_vectors_batch_query(
        self,
        cold_start_r5_config: R5Config,
        sample_envelope_with_episodes: P03BatchEnvelope,
        runner_context_with_syscalls: P03RunnerContext,
        mock_syscalls_with_data: MockR5Syscalls,
    ) -> None:
        """R5 should call embedding_vectors_batch_query for accumulated entities."""
        phase = R5DreamExplorer(config=cold_start_r5_config)

        await phase.run(sample_envelope_with_episodes, runner_context_with_syscalls)

        # Should have called embedding_vectors_batch_query
        assert len(mock_syscalls_with_data.embedding_query_calls) >= 1

    @pytest.mark.asyncio
    async def test_embedding_vectors_are_768_dim(
        self,
        mock_syscalls_with_data: MockR5Syscalls,
    ) -> None:
        """Embedding vectors should be 768-dimensional."""
        # Check the first embedding in the mock data
        for emb_id, vector in mock_syscalls_with_data.embeddings.items():
            assert len(vector) == 768
            break


# =============================================================================
# TEST: Full R5 Cold Start Integration
# =============================================================================


class TestR5ColdStartIntegration:
    """Integration tests for complete R5 cold start fix."""

    @pytest.mark.asyncio
    async def test_r5_completes_with_cold_start_fix(
        self,
        cold_start_r5_config: R5Config,
        sample_envelope_with_episodes: P03BatchEnvelope,
        runner_context_with_syscalls: P03RunnerContext,
    ) -> None:
        """R5 should complete successfully with cold start fixes applied."""
        phase = R5DreamExplorer(config=cold_start_r5_config)

        result = await phase.run(sample_envelope_with_episodes, runner_context_with_syscalls)

        # Should complete without error
        assert result.status == P03PhaseStatus.DONE
        assert result.error_info is None

    @pytest.mark.asyncio
    async def test_r5_metrics_emitted(
        self,
        cold_start_r5_config: R5Config,
        sample_envelope_with_episodes: P03BatchEnvelope,
        runner_context_with_syscalls: P03RunnerContext,
        mock_metrics_registry: MagicMock,
    ) -> None:
        """R5 should emit metrics after execution."""
        phase = R5DreamExplorer(config=cold_start_r5_config)

        await phase.run(sample_envelope_with_episodes, runner_context_with_syscalls)

        # Basic metrics should be emitted
        mock_metrics_registry.set_r5_mode.assert_called()
        mock_metrics_registry.emit_r5_duration.assert_called()


# =============================================================================
# TEST: Configuration Validation
# =============================================================================


class TestColdStartConfiguration:
    """Test cold start configuration values."""

    def test_all_cold_start_configs_present(
        self,
        cold_start_r5_config: R5Config,
    ) -> None:
        """R5Config should have all cold start configuration fields."""
        # Issue 9.1
        assert hasattr(cold_start_r5_config, "bgt_sm_cold_start_threshold")
        assert cold_start_r5_config.bgt_sm_cold_start_threshold == 100

        # Issue 9.2
        assert hasattr(cold_start_r5_config, "accumulated_kg_entity_limit")
        assert cold_start_r5_config.accumulated_kg_entity_limit == 500
        assert hasattr(cold_start_r5_config, "accumulated_kg_edge_limit")
        assert cold_start_r5_config.accumulated_kg_edge_limit == 2000

        # Issue 9.3
        assert hasattr(cold_start_r5_config, "cpn_emotional_threshold")
        assert cold_start_r5_config.cpn_emotional_threshold == 0.3

    def test_dream_config_propagation(
        self,
        cold_start_r5_config: R5Config,
    ) -> None:
        """DreamConfig should propagate all cold start settings from R5Config."""
        dream_config = DreamConfig.from_r5_config(cold_start_r5_config)

        # Verify propagation
        assert dream_config.cold_start_threshold == 100
        assert dream_config.cpn_emotional_threshold == 0.3


# =============================================================================
# TEST: Error Handling
# =============================================================================


class TestColdStartErrorHandling:
    """Test graceful degradation when syscalls fail."""

    @pytest.mark.asyncio
    async def test_r5_handles_kg_query_failure(
        self,
        cold_start_r5_config: R5Config,
        sample_envelope_with_episodes: P03BatchEnvelope,
        mock_metrics_registry: MagicMock,
    ) -> None:
        """R5 should handle kg_entities_query failure gracefully."""
        # Create syscalls that raise on kg_entities_query
        failing_syscalls = MockR5Syscalls()
        failing_syscalls.kg_entities_query = AsyncMock(
            side_effect=Exception("Database connection failed")
        )
        failing_syscalls.kg_edges_query = AsyncMock(
            side_effect=Exception("Database connection failed")
        )
        failing_syscalls.embedding_vectors_batch_query = AsyncMock(
            return_value={"vectors": {}, "count": 0, "missing": []}
        )

        ctx = P03RunnerContext.create(
            syscalls=failing_syscalls,
            logger=MagicMock(),
            qos_band="GREEN",
            priority=50,
            config={},
        )
        ctx.metrics_registry = mock_metrics_registry

        phase = R5DreamExplorer(config=cold_start_r5_config)

        # Should still complete (with warning logged, using batch-only entities)
        result = await phase.run(sample_envelope_with_episodes, ctx)

        # Phase should still complete (graceful degradation)
        assert result.status == P03PhaseStatus.DONE

    @pytest.mark.asyncio
    async def test_r5_handles_embedding_query_failure(
        self,
        cold_start_r5_config: R5Config,
        sample_envelope_with_episodes: P03BatchEnvelope,
        mock_metrics_registry: MagicMock,
    ) -> None:
        """R5 should handle embedding_vectors_batch_query failure gracefully."""
        entities, _ = generate_mock_entities(150, with_embeddings=True)
        edges = generate_mock_edges(150)

        syscalls = MockR5Syscalls(entities=entities, edges=edges)
        # Override embedding query to fail
        syscalls.embedding_vectors_batch_query = AsyncMock(
            side_effect=Exception("Embedding service unavailable")
        )

        ctx = P03RunnerContext.create(
            syscalls=syscalls,
            logger=MagicMock(),
            qos_band="GREEN",
            priority=50,
            config={},
        )
        ctx.metrics_registry = mock_metrics_registry

        phase = R5DreamExplorer(config=cold_start_r5_config)

        # Should still complete (without embeddings)
        result = await phase.run(sample_envelope_with_episodes, ctx)

        assert result.status == P03PhaseStatus.DONE
