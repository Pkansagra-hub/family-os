"""M9.8 R2 Engine Path Tests.

Tests for the R2 adapter, migration harness, and engine wiring
into the R2EpisodicIntegrator phase.

Covers:
  - R2Adapter (event_to_candidate, episode_to_candidate, existing_to_truth_record)
  - DualPathRunner (legacy-only, engine-only, dual-path with divergence)
  - R2 config engine flags
  - Engine REINFORCE matching (Seam 1)
  - Engine EXTEND matching (Seam 2)
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import numpy as np
import pytest

from k0.modules.consolidation.identity.episodic import EpisodicIdentity
from k0.modules.consolidation.reconciliation.adapters.r2_adapter import R2Adapter
from k0.modules.consolidation.reconciliation.engine import ReconciliationFramework
from k0.modules.consolidation.reconciliation.migration import (
    Divergence,
    DualPathResult,
    DualPathRunner,
)
from k0.modules.consolidation.reconciliation.result import ReconciliationResult
from k0.modules.consolidation.truth_layer_registry import TruthLayerRegistry
from k0.pipelines.p03.event_state import P03EventState, ReconciliationAction

_CONTRACTS_DIR = Path(__file__).resolve().parents[4] / "k0" / "contracts" / "schemas"

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _vec(seed: int = 1, dim: int = 768) -> list[float]:
    rng = np.random.default_rng(seed)
    v = rng.standard_normal(dim)
    v /= np.linalg.norm(v)
    return v.tolist()


def _similar_vec(base: list[float], similarity: float) -> list[float]:
    base_arr = np.asarray(base, dtype=np.float64)
    base_arr /= np.linalg.norm(base_arr)
    rng = np.random.default_rng(42)
    rand = rng.standard_normal(len(base))
    rand -= np.dot(rand, base_arr) * base_arr
    rand /= np.linalg.norm(rand)
    theta = np.arccos(np.clip(similarity, -1.0, 1.0))
    result = np.cos(theta) * base_arr + np.sin(theta) * rand
    result /= np.linalg.norm(result)
    return result.tolist()


def _make_event(
    event_id: str = "evt-1",
    embedding: list[float] | None = None,
    narrative_thread_id: str = "thread-1",
    topics_json: str = '["cooking", "dinner"]',
    participants_json: str = '["alice", "bob"]',
    social_context: str = "nuclear_family",
    location_name: str = "kitchen",
    focal_entity: str = "",
    source_type: str = "",
    correction_signal: bool = False,
    contradiction_signal: bool = False,
    timestamp: int = 1000000,
) -> P03EventState:
    ev = P03EventState(event_id=event_id)
    ev.embedding_768 = embedding or _vec(hash(event_id) % 10000)
    ev.narrative_thread_id = narrative_thread_id
    ev.topics_json = topics_json
    ev.participants_json = participants_json
    ev.social_context = social_context
    ev.location_name = location_name
    ev.focal_entity = focal_entity
    ev.source_type = source_type
    ev.correction_signal = correction_signal
    ev.contradiction_signal = contradiction_signal
    ev.timestamp = timestamp
    return ev


def _make_existing_episode(
    episode_id: str = "ep-1",
    embedding: list[float] | None = None,
    version: int = 1,
    narrative_thread_id: str = "thread-1",
    start_time_utc: int = 500000,
    end_time_utc: int = 900000,
    source_event_count: int = 5,
    cluster_confidence: float = 0.8,
    primary_location: str = "kitchen",
) -> dict[str, Any]:
    return {
        "episode_id": episode_id,
        "embedding": np.asarray(embedding or _vec(hash(episode_id) % 10000), dtype=np.float64),
        "version": version,
        "narrative_thread_id": narrative_thread_id,
        "start_time_utc": start_time_utc,
        "end_time_utc": end_time_utc,
        "source_event_count": source_event_count,
        "cluster_confidence": cluster_confidence,
        "primary_location": primary_location,
    }


@pytest.fixture()
def registry() -> TruthLayerRegistry:
    return TruthLayerRegistry.from_contracts(_CONTRACTS_DIR)


@pytest.fixture()
def identity() -> EpisodicIdentity:
    return EpisodicIdentity()


# =========================================================================
# R2Adapter Tests
# =========================================================================


class TestR2AdapterEventToCandidate:
    """Tests for R2Adapter.event_to_candidate."""

    def test_basic_conversion(self):
        event = _make_event(event_id="evt-abc")
        rc = R2Adapter.event_to_candidate(event, cycle_id="c1", space_id="s1", tenant_id="t1")

        assert rc.candidate_id == "evt-abc"
        assert rc.layer == "st_epi"
        assert rc.source_phase == "R2"
        assert rc.cycle_id == "c1"
        assert rc.space_id == "s1"
        assert rc.tenant_id == "t1"
        assert rc.embedding is not None
        assert len(rc.embedding) == 768
        assert rc.source_event_ids == ("evt-abc",)

    def test_metadata_extraction(self):
        event = _make_event(
            topics_json='["cooking", "baking"]',
            participants_json='["alice"]',
            social_context="solo",
            location_name="oven_room",
            focal_entity="pie",
        )
        rc = R2Adapter.event_to_candidate(event, cycle_id="c1")

        assert rc.metadata["topics"] == {"cooking", "baking"}
        assert rc.metadata["participants"] == {"alice"}
        assert rc.metadata["social_context"] == "solo"
        assert rc.metadata["location"] == "oven_room"
        assert rc.metadata["focal"] == "pie"

    def test_k1_signals_forwarded(self):
        event = _make_event(correction_signal=True, contradiction_signal=False)
        rc = R2Adapter.event_to_candidate(event, cycle_id="c1")

        assert rc.k1_signals.correction_signal is True
        assert rc.k1_signals.contradiction_signal is False

    def test_none_embedding(self):
        event = _make_event()
        event.embedding_768 = None
        rc = R2Adapter.event_to_candidate(event, cycle_id="c1")

        assert rc.embedding is None

    def test_empty_json_fields(self):
        event = _make_event(topics_json="", participants_json="[]")
        rc = R2Adapter.event_to_candidate(event, cycle_id="c1")

        assert rc.metadata["topics"] == set()
        assert rc.metadata["participants"] == set()

    def test_malformed_json_fallback(self):
        event = _make_event(topics_json="not-json", participants_json="{bad}")
        rc = R2Adapter.event_to_candidate(event, cycle_id="c1")

        assert rc.metadata["topics"] == set()
        assert rc.metadata["participants"] == set()


class TestR2AdapterEpisodeToCandidate:
    """Tests for R2Adapter.episode_to_candidate."""

    def test_basic_conversion(self):
        cand = MagicMock()
        cand.cluster_id = "cluster-1"
        cand.event_ids = ["evt-1", "evt-2"]
        cand.centroid_embedding = _vec(99)
        cand.temporal_start = 100
        cand.temporal_end = 200

        rc = R2Adapter.episode_to_candidate(cand, cycle_id="c1", space_id="s1")

        assert rc.candidate_id == "cluster-1"
        assert rc.layer == "st_epi"
        assert rc.source_phase == "R2"
        assert len(rc.source_event_ids) == 2
        assert rc.embedding is not None

    def test_metadata_aggregation_from_events(self):
        cand = MagicMock()
        cand.cluster_id = "cluster-1"
        cand.event_ids = ["evt-1", "evt-2"]
        cand.centroid_embedding = _vec(99)
        cand.temporal_start = 100
        cand.temporal_end = 200

        ev1 = _make_event(
            event_id="evt-1",
            topics_json='["cooking"]',
            participants_json='["alice"]',
            narrative_thread_id="th-A",
        )
        ev2 = _make_event(
            event_id="evt-2",
            topics_json='["baking"]',
            participants_json='["bob"]',
            narrative_thread_id="th-A",
        )
        event_lookup = {"evt-1": ev1, "evt-2": ev2}

        rc = R2Adapter.episode_to_candidate(cand, cycle_id="c1", event_lookup=event_lookup)

        assert "cooking" in rc.metadata["topics"]
        assert "baking" in rc.metadata["topics"]
        assert "alice" in rc.metadata["participants"]
        assert "bob" in rc.metadata["participants"]
        assert rc.metadata["narrative_thread_id"] == "th-A"

    def test_none_centroid(self):
        cand = MagicMock()
        cand.cluster_id = "cluster-1"
        cand.event_ids = []
        cand.centroid_embedding = None
        cand.temporal_start = 0
        cand.temporal_end = 0

        rc = R2Adapter.episode_to_candidate(cand, cycle_id="c1")
        assert rc.embedding is None


class TestR2AdapterExistingToTruthRecord:
    """Tests for R2Adapter.existing_to_truth_record."""

    def test_basic_conversion(self):
        ep = _make_existing_episode(episode_id="ep-99", version=3)
        tr = R2Adapter.existing_to_truth_record(ep)

        assert tr.record_id == "ep-99"
        assert tr.layer == "st_epi"
        assert tr.version == 3
        assert tr.embedding is not None
        assert len(tr.embedding) == 768

    def test_metadata_preserved(self):
        ep = _make_existing_episode(
            narrative_thread_id="th-B",
            primary_location="park",
        )
        tr = R2Adapter.existing_to_truth_record(ep)

        assert tr.metadata["narrative_thread_id"] == "th-B"
        assert tr.metadata["location"] == "park"

    def test_none_embedding(self):
        ep = _make_existing_episode()
        ep["embedding"] = None
        tr = R2Adapter.existing_to_truth_record(ep)

        assert tr.embedding is None


# =========================================================================
# DualPathRunner Tests
# =========================================================================


class TestDualPathRunnerLegacyOnly:
    """Legacy-only path (no engine flags)."""

    def test_legacy_only_returns_legacy_result(self):
        runner = DualPathRunner(use_engine=False, dual_path=False)

        result = runner.run(
            candidate_id="evt-1",
            legacy_fn=lambda: (
                ReconciliationAction.REINFORCE,
                "ep-1",
                0.92,
                2,
                "legacy match",
            ),
            engine_fn=lambda: (_ for _ in ()).throw(AssertionError("should not be called")),
        )

        assert result.action == ReconciliationAction.REINFORCE
        assert result.match_id == "ep-1"
        assert result.match_similarity == 0.92
        assert result.match_version == 2
        assert result.engine_result is None
        assert result.divergence is None


class TestDualPathRunnerEngineOnly:
    """Engine-only path."""

    def test_engine_only_returns_engine_result(self):
        engine_result = ReconciliationResult(
            action=ReconciliationAction.REINFORCE,
            tier=2,
            match_id="ep-2",
            match_layer="st_epi",
            similarity=0.88,
            identity_match=True,
            confidence=0.9,
            reason="engine reinforce",
            candidate_id="evt-1",
            layer="st_epi",
            cycle_id="c1",
            hooks_required=["recompute_centroid"],
        )

        runner = DualPathRunner(use_engine=True, dual_path=False)

        result = runner.run(
            candidate_id="evt-1",
            legacy_fn=lambda: (_ for _ in ()).throw(AssertionError("should not be called")),
            engine_fn=lambda: engine_result,
        )

        assert result.action == ReconciliationAction.REINFORCE
        assert result.match_id == "ep-2"
        assert result.match_similarity == 0.88
        assert result.engine_result is engine_result
        assert result.divergence is None


class TestDualPathRunnerDualPath:
    """Dual-path mode: both paths run, legacy authoritative."""

    def test_dual_path_no_divergence(self):
        engine_result = ReconciliationResult(
            action=ReconciliationAction.REINFORCE,
            tier=2,
            match_id="ep-1",
            match_layer="st_epi",
            similarity=0.90,
            identity_match=True,
            confidence=0.9,
            reason="engine",
            candidate_id="evt-1",
            layer="st_epi",
            cycle_id="c1",
        )

        runner = DualPathRunner(use_engine=True, dual_path=True)

        result = runner.run(
            candidate_id="evt-1",
            legacy_fn=lambda: (
                ReconciliationAction.REINFORCE,
                "ep-1",
                0.92,
                2,
                "legacy",
            ),
            engine_fn=lambda: engine_result,
        )

        # Legacy is authoritative
        assert result.action == ReconciliationAction.REINFORCE
        assert result.match_id == "ep-1"
        assert result.match_similarity == 0.92
        assert result.engine_result is engine_result
        assert result.divergence is None  # Same action + match

    def test_dual_path_action_divergence(self, caplog):
        engine_result = ReconciliationResult(
            action=ReconciliationAction.EXTEND,
            tier=2,
            match_id="ep-1",
            match_layer="st_epi",
            similarity=0.75,
            identity_match=True,
            confidence=0.7,
            reason="engine extend",
            candidate_id="evt-1",
            layer="st_epi",
            cycle_id="c1",
        )

        runner = DualPathRunner(use_engine=True, dual_path=True, log_divergences=True)

        with caplog.at_level(logging.WARNING):
            result = runner.run(
                candidate_id="evt-1",
                legacy_fn=lambda: (
                    ReconciliationAction.REINFORCE,
                    "ep-1",
                    0.92,
                    2,
                    "legacy",
                ),
                engine_fn=lambda: engine_result,
            )

        assert result.action == ReconciliationAction.REINFORCE  # legacy wins
        assert result.divergence is not None
        assert result.divergence.legacy_action == ReconciliationAction.REINFORCE
        assert result.divergence.engine_action == ReconciliationAction.EXTEND
        assert "divergence" in caplog.text.lower()

    def test_dual_path_match_divergence(self):
        engine_result = ReconciliationResult(
            action=ReconciliationAction.REINFORCE,
            tier=2,
            match_id="ep-999",
            match_layer="st_epi",
            similarity=0.90,
            identity_match=True,
            confidence=0.9,
            reason="engine",
            candidate_id="evt-1",
            layer="st_epi",
            cycle_id="c1",
        )

        runner = DualPathRunner(use_engine=True, dual_path=True, log_divergences=False)

        result = runner.run(
            candidate_id="evt-1",
            legacy_fn=lambda: (
                ReconciliationAction.REINFORCE,
                "ep-1",
                0.92,
                2,
                "legacy",
            ),
            engine_fn=lambda: engine_result,
        )

        assert result.divergence is not None
        assert result.divergence.legacy_match_id == "ep-1"
        assert result.divergence.engine_match_id == "ep-999"


# =========================================================================
# R2Config Engine Flag Tests
# =========================================================================


class TestR2ConfigEngineFlags:
    """Validate engine flags on R2Config."""

    def test_defaults_all_off(self):
        from k0.pipelines.p03.phases.r2_episodic_integrator import R2Config

        cfg = R2Config()
        assert cfg.enable_engine_reinforce is False
        assert cfg.enable_engine_extend is False
        assert cfg.engine_dual_path_enabled is False
        assert cfg.engine_dual_path_log_divergences is True

    def test_engine_flags_settable(self):
        from k0.pipelines.p03.phases.r2_episodic_integrator import R2Config

        cfg = R2Config(
            enable_engine_reinforce=True,
            enable_engine_extend=True,
            engine_dual_path_enabled=True,
            engine_dual_path_log_divergences=False,
        )
        assert cfg.enable_engine_reinforce is True
        assert cfg.enable_engine_extend is True
        assert cfg.engine_dual_path_enabled is True
        assert cfg.engine_dual_path_log_divergences is False


# =========================================================================
# Engine REINFORCE Matching (Seam 1) - Integration Tests
# =========================================================================


class TestEngineReinforceMatching:
    """Test _engine_match_events using real engine components."""

    def test_high_similarity_event_gets_reinforce(self, registry, identity):
        from k0.pipelines.p03.phases.r2_episodic_integrator import R2Config, R2EpisodicIntegrator

        integrator = R2EpisodicIntegrator(config=R2Config(enable_engine_reinforce=True))
        integrator._engine_registry = registry
        integrator._engine_identity = identity

        # Create event and episode with very similar embeddings
        base_vec = _vec(42)
        similar = _similar_vec(base_vec, 0.95)

        event = _make_event(event_id="evt-high", embedding=base_vec)
        episode = _make_existing_episode(episode_id="ep-target", embedding=similar)

        matched, novel = integrator._engine_match_events(
            events=[event],
            existing_episodes=[episode],
            cycle_id="c1",
            space_id="s1",
            tenant_id="t1",
        )

        assert len(matched) == 1
        assert matched[0].event_id == "evt-high"
        assert matched[0].reconciliation_action == ReconciliationAction.REINFORCE
        assert matched[0].episode_match_id == "ep-target"
        assert len(novel) == 0

    def test_low_similarity_event_stays_novel(self, registry, identity):
        from k0.pipelines.p03.phases.r2_episodic_integrator import R2Config, R2EpisodicIntegrator

        integrator = R2EpisodicIntegrator(config=R2Config(enable_engine_reinforce=True))
        integrator._engine_registry = registry
        integrator._engine_identity = identity

        # Totally different embeddings
        event = _make_event(event_id="evt-diff", embedding=_vec(1))
        episode = _make_existing_episode(episode_id="ep-other", embedding=_vec(9999))

        matched, novel = integrator._engine_match_events(
            events=[event],
            existing_episodes=[episode],
            cycle_id="c1",
            space_id="s1",
            tenant_id="t1",
        )

        assert len(matched) == 0
        assert len(novel) == 1

    def test_no_existing_episodes_all_novel(self, registry, identity):
        from k0.pipelines.p03.phases.r2_episodic_integrator import R2Config, R2EpisodicIntegrator

        integrator = R2EpisodicIntegrator(config=R2Config(enable_engine_reinforce=True))
        integrator._engine_registry = registry
        integrator._engine_identity = identity

        event = _make_event(event_id="evt-solo")

        matched, novel = integrator._engine_match_events(
            events=[event],
            existing_episodes=[],
            cycle_id="c1",
            space_id="s1",
            tenant_id="t1",
        )

        assert len(matched) == 0
        assert len(novel) == 1

    def test_event_without_embedding_stays_novel(self, registry, identity):
        from k0.pipelines.p03.phases.r2_episodic_integrator import R2Config, R2EpisodicIntegrator

        integrator = R2EpisodicIntegrator(config=R2Config(enable_engine_reinforce=True))
        integrator._engine_registry = registry
        integrator._engine_identity = identity

        event = _make_event(event_id="evt-no-emb")
        event.embedding_768 = None
        episode = _make_existing_episode(episode_id="ep-1")

        matched, novel = integrator._engine_match_events(
            events=[event],
            existing_episodes=[episode],
            cycle_id="c1",
            space_id="s1",
            tenant_id="t1",
        )

        assert len(matched) == 0
        assert len(novel) == 1

    def test_multiple_events_mixed_matches(self, registry, identity):
        from k0.pipelines.p03.phases.r2_episodic_integrator import R2Config, R2EpisodicIntegrator

        integrator = R2EpisodicIntegrator(config=R2Config(enable_engine_reinforce=True))
        integrator._engine_registry = registry
        integrator._engine_identity = identity

        base_vec = _vec(42)
        high_sim = _similar_vec(base_vec, 0.95)

        # Event 1: will match (high similarity)
        ev_match = _make_event(event_id="evt-match", embedding=base_vec)
        # Event 2: won't match (different vector)
        ev_novel = _make_event(event_id="evt-novel", embedding=_vec(9999))

        episode = _make_existing_episode(episode_id="ep-1", embedding=high_sim)

        matched, novel = integrator._engine_match_events(
            events=[ev_match, ev_novel],
            existing_episodes=[episode],
            cycle_id="c1",
            space_id="s1",
            tenant_id="t1",
        )

        assert len(matched) == 1
        assert len(novel) == 1
        assert matched[0].event_id == "evt-match"
        assert novel[0].event_id == "evt-novel"

    def test_k1_correction_signal_overrides(self, registry, identity):
        """K1 correction signal should produce EVOLVE, not REINFORCE."""
        from k0.pipelines.p03.phases.r2_episodic_integrator import R2Config, R2EpisodicIntegrator

        integrator = R2EpisodicIntegrator(config=R2Config(enable_engine_reinforce=True))
        integrator._engine_registry = registry
        integrator._engine_identity = identity

        base_vec = _vec(42)
        similar = _similar_vec(base_vec, 0.95)

        event = _make_event(event_id="evt-k1", embedding=base_vec, correction_signal=True)
        episode = _make_existing_episode(episode_id="ep-1", embedding=similar)

        matched, novel = integrator._engine_match_events(
            events=[event],
            existing_episodes=[episode],
            cycle_id="c1",
            space_id="s1",
            tenant_id="t1",
        )

        # K1 correction triggers EVOLVE, not REINFORCE, so event goes to novel
        assert len(matched) == 0
        assert len(novel) == 1


# =========================================================================
# Engine EXTEND Matching (Seam 2) - Integration Tests
# =========================================================================


class TestEngineExtendMatching:
    """Test _engine_extend_episodes using real engine components."""

    def test_high_similarity_candidate_gets_extend(self, registry, identity):
        from k0.pipelines.p03.phases.r2_episodic_integrator import R2Config, R2EpisodicIntegrator

        integrator = R2EpisodicIntegrator(config=R2Config(enable_engine_extend=True))
        integrator._engine_registry = registry
        integrator._engine_identity = identity

        base_vec = _vec(42)
        similar = _similar_vec(base_vec, 0.90)

        cand = MagicMock()
        cand.cluster_id = "cluster-1"
        cand.event_ids = ["evt-1", "evt-2"]
        cand.centroid_embedding = base_vec
        cand.temporal_start = 1000
        cand.temporal_end = 2000
        cand.reconciliation_action = "CREATE"
        cand.extend_target_episode_id = None
        cand.extend_similarity = 0.0

        episode = _make_existing_episode(episode_id="ep-target", embedding=similar)

        extended = integrator._engine_extend_episodes(
            episode_candidates=[cand],
            existing_episodes=[episode],
            event_lookup={},
            cycle_id="c1",
            space_id="s1",
            tenant_id="t1",
        )

        assert extended == 1
        assert cand.reconciliation_action == "EXTEND"
        assert cand.extend_target_episode_id == "ep-target"

    def test_low_similarity_candidate_stays_create(self, registry, identity):
        from k0.pipelines.p03.phases.r2_episodic_integrator import R2Config, R2EpisodicIntegrator

        integrator = R2EpisodicIntegrator(config=R2Config(enable_engine_extend=True))
        integrator._engine_registry = registry
        integrator._engine_identity = identity

        cand = MagicMock()
        cand.cluster_id = "cluster-1"
        cand.event_ids = ["evt-1"]
        cand.centroid_embedding = _vec(1)
        cand.temporal_start = 1000
        cand.temporal_end = 2000
        cand.reconciliation_action = "CREATE"
        cand.extend_target_episode_id = None
        cand.extend_similarity = 0.0

        episode = _make_existing_episode(episode_id="ep-far", embedding=_vec(9999))

        extended = integrator._engine_extend_episodes(
            episode_candidates=[cand],
            existing_episodes=[episode],
            event_lookup={},
            cycle_id="c1",
            space_id="s1",
            tenant_id="t1",
        )

        assert extended == 0

    def test_no_existing_episodes(self, registry, identity):
        from k0.pipelines.p03.phases.r2_episodic_integrator import R2Config, R2EpisodicIntegrator

        integrator = R2EpisodicIntegrator(config=R2Config(enable_engine_extend=True))
        integrator._engine_registry = registry
        integrator._engine_identity = identity

        cand = MagicMock()
        cand.cluster_id = "cluster-1"
        cand.event_ids = []
        cand.centroid_embedding = _vec(1)
        cand.temporal_start = 0
        cand.temporal_end = 0

        extended = integrator._engine_extend_episodes(
            episode_candidates=[cand],
            existing_episodes=[],
            event_lookup={},
            cycle_id="c1",
            space_id="s1",
            tenant_id="t1",
        )

        assert extended == 0

    def test_none_centroid_skipped(self, registry, identity):
        from k0.pipelines.p03.phases.r2_episodic_integrator import R2Config, R2EpisodicIntegrator

        integrator = R2EpisodicIntegrator(config=R2Config(enable_engine_extend=True))
        integrator._engine_registry = registry
        integrator._engine_identity = identity

        cand = MagicMock()
        cand.cluster_id = "cluster-1"
        cand.event_ids = []
        cand.centroid_embedding = None
        cand.temporal_start = 0
        cand.temporal_end = 0

        episode = _make_existing_episode()

        extended = integrator._engine_extend_episodes(
            episode_candidates=[cand],
            existing_episodes=[episode],
            event_lookup={},
            cycle_id="c1",
            space_id="s1",
            tenant_id="t1",
        )

        assert extended == 0


# =========================================================================
# Lazy initialization
# =========================================================================


class TestLazyEngineInit:
    """Engine components are lazily initialized."""

    def test_engine_components_none_by_default(self):
        from k0.pipelines.p03.phases.r2_episodic_integrator import R2EpisodicIntegrator

        integrator = R2EpisodicIntegrator()
        assert integrator._engine_registry is None
        assert integrator._engine_identity is None

    def test_ensure_engine_components_initializes(self):
        from k0.pipelines.p03.phases.r2_episodic_integrator import R2EpisodicIntegrator

        integrator = R2EpisodicIntegrator()
        integrator._ensure_engine_components()

        assert integrator._engine_registry is not None
        assert integrator._engine_identity is not None

    def test_ensure_engine_components_idempotent(self):
        from k0.pipelines.p03.phases.r2_episodic_integrator import R2EpisodicIntegrator

        integrator = R2EpisodicIntegrator()
        integrator._ensure_engine_components()
        reg1 = integrator._engine_registry
        integrator._ensure_engine_components()

        assert integrator._engine_registry is reg1


# =========================================================================
# Engine decision roundtrip through adapter
# =========================================================================


class TestAdapterEngineRoundtrip:
    """End-to-end: event -> adapter -> engine -> result."""

    def test_event_through_engine_produces_valid_result(self, registry, identity):
        base_vec = _vec(42)
        similar = _similar_vec(base_vec, 0.90)

        event = _make_event(event_id="evt-rt", embedding=base_vec)
        episode = _make_existing_episode(episode_id="ep-rt", embedding=similar)

        # Adapt
        candidate = R2Adapter.event_to_candidate(event, cycle_id="c1")
        truth_record = R2Adapter.existing_to_truth_record(episode)

        # Decide
        result = ReconciliationFramework.decide(
            candidate=candidate,
            layer="st_epi",
            registry=registry,
            existing_records=[truth_record],
            identity_strategy=identity,
        )

        assert isinstance(result, ReconciliationResult)
        assert result.action in (
            ReconciliationAction.CREATE,
            ReconciliationAction.EXTEND,
            ReconciliationAction.REINFORCE,
        )
        assert result.candidate_id == "evt-rt"
        assert result.layer == "st_epi"
        assert 0.0 <= result.similarity <= 1.0
        assert 0.0 <= result.confidence <= 1.0

    def test_episode_through_engine_produces_valid_result(self, registry, identity):
        base_vec = _vec(42)
        similar = _similar_vec(base_vec, 0.85)

        cand_mock = MagicMock()
        cand_mock.cluster_id = "cluster-rt"
        cand_mock.event_ids = ["evt-1"]
        cand_mock.centroid_embedding = base_vec
        cand_mock.temporal_start = 1000
        cand_mock.temporal_end = 2000

        episode = _make_existing_episode(episode_id="ep-rt", embedding=similar)

        # Adapt
        candidate = R2Adapter.episode_to_candidate(cand_mock, cycle_id="c1")
        truth_record = R2Adapter.existing_to_truth_record(episode)

        # Decide
        result = ReconciliationFramework.decide(
            candidate=candidate,
            layer="st_epi",
            registry=registry,
            existing_records=[truth_record],
            identity_strategy=identity,
        )

        assert isinstance(result, ReconciliationResult)
        assert result.candidate_id == "cluster-rt"


# =========================================================================
# DualPathResult properties
# =========================================================================


class TestDualPathResultProperties:
    """Verify DualPathResult behavior."""

    def test_used_engine_true_when_no_divergence(self):
        engine_result = ReconciliationResult(
            action=ReconciliationAction.REINFORCE,
            tier=2,
            match_id="ep-1",
            match_layer="st_epi",
            similarity=0.9,
            identity_match=True,
            confidence=0.9,
            reason="test",
            candidate_id="c1",
            layer="st_epi",
            cycle_id="c1",
        )
        r = DualPathResult(
            action=ReconciliationAction.REINFORCE,
            engine_result=engine_result,
            divergence=None,
        )
        assert r.used_engine is True

    def test_used_engine_false_when_divergence(self):
        engine_result = ReconciliationResult(
            action=ReconciliationAction.EXTEND,
            tier=2,
            match_id="ep-1",
            match_layer="st_epi",
            similarity=0.7,
            identity_match=True,
            confidence=0.7,
            reason="test",
            candidate_id="c1",
            layer="st_epi",
            cycle_id="c1",
        )
        div = Divergence(
            candidate_id="c1",
            legacy_action=ReconciliationAction.REINFORCE,
            engine_action=ReconciliationAction.EXTEND,
            legacy_match_id="ep-1",
            engine_match_id="ep-1",
            legacy_similarity=0.92,
            engine_similarity=0.7,
            reason="action divergence",
        )
        r = DualPathResult(
            action=ReconciliationAction.REINFORCE,
            engine_result=engine_result,
            divergence=div,
        )
        assert r.used_engine is False

    def test_used_engine_false_when_no_engine(self):
        r = DualPathResult(action=ReconciliationAction.REINFORCE)
        assert r.used_engine is False
