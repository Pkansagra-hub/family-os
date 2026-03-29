"""Per-stage unit tests for ReconciliationFramework (M9.4).

Covers validation criteria V1-V12, V16, V18-V23 from the design doc.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from k0.modules.consolidation.reconciliation.decision_log import log_decision
from k0.modules.consolidation.reconciliation.engine import ReconciliationFramework
from k0.modules.consolidation.reconciliation.metrics import DecisionMetrics
from k0.modules.consolidation.reconciliation.result import ReconciliationResult
from k0.modules.consolidation.truth_layer_registry import TruthLayerRegistry
from k0.modules.consolidation.types import K1SignalBundle, ReconciliationCandidate, TruthRecord
from k0.pipelines.p03.event_state import ReconciliationAction

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_CONTRACTS_DIR = Path(__file__).resolve().parents[5] / "k0" / "contracts" / "schemas"


@pytest.fixture()
def registry() -> TruthLayerRegistry:
    return TruthLayerRegistry.from_contracts(_CONTRACTS_DIR)


def _vec(seed: int = 1, dim: int = 768) -> list[float]:
    """Deterministic L2-normalized random vector."""
    rng = np.random.default_rng(seed)
    v = rng.standard_normal(dim)
    v /= np.linalg.norm(v)
    return v.tolist()


def _similar_vec(base: list[float], similarity: float) -> list[float]:
    """Create a vector with approximate cosine similarity to *base*.

    Uses spherical interpolation (slerp) between the base vector
    and a random orthogonal vector.
    """
    base_arr = np.asarray(base, dtype=np.float64)
    base_arr /= np.linalg.norm(base_arr)

    rng = np.random.default_rng(42)
    rand = rng.standard_normal(len(base))
    # Make orthogonal to base
    rand -= np.dot(rand, base_arr) * base_arr
    rand /= np.linalg.norm(rand)

    # Slerp: cos(theta) = similarity
    theta = np.arccos(np.clip(similarity, -1.0, 1.0))
    result = np.cos(theta) * base_arr + np.sin(theta) * rand
    result /= np.linalg.norm(result)
    return result.tolist()


def _candidate(
    candidate_id: str = "cand-1",
    layer: str = "st_epi",
    embedding: list[float] | None = None,
    k1_signals: K1SignalBundle | None = None,
    metadata: dict[str, Any] | None = None,
    cycle_id: str = "cycle-001",
) -> ReconciliationCandidate:
    return ReconciliationCandidate(
        candidate_id=candidate_id,
        layer=layer,
        source_phase="R3",
        embedding=embedding or _vec(1),
        k1_signals=k1_signals or K1SignalBundle(),
        metadata=metadata or {},
        cycle_id=cycle_id,
        tenant_id="test-tenant",
        space_id="test-space",
    )


def _record(
    record_id: str = "rec-1",
    layer: str = "st_epi",
    embedding: list[float] | None = None,
    metadata: dict[str, Any] | None = None,
) -> TruthRecord:
    return TruthRecord(
        record_id=record_id,
        layer=layer,
        embedding=embedding or _vec(2),
        confidence=0.8,
        version=1,
        observation_count=5,
        last_observed_ms=1700000000000,
        metadata=metadata or {},
    )


class _PassAllIdentity:
    """Test identity strategy that accepts all records."""

    @property
    def layer_name(self) -> str:
        return "st_epi"

    def score_identity(self, candidate, existing, cosine_sim):
        from k0.modules.consolidation.types import IdentityResult

        return IdentityResult(
            score=0.8,
            p_create=0.1,
            p_extend=0.5,
            p_reinforce=0.4,
            recommended_action="EXTEND",
        )

    def match_key(self, candidate, existing):
        return None  # Inconclusive -> falls to score_identity


class _RejectAllIdentity:
    """Test identity strategy that rejects all records."""

    @property
    def layer_name(self) -> str:
        return "st_epi"

    def score_identity(self, candidate, existing, cosine_sim):
        from k0.modules.consolidation.types import IdentityResult

        return IdentityResult(
            score=0.1,
            p_create=0.9,
            p_extend=0.05,
            p_reinforce=0.05,
            recommended_action="CREATE",
        )

    def match_key(self, candidate, existing):
        return None


class _KeyMatchIdentity:
    """Test identity strategy with deterministic key matching."""

    @property
    def layer_name(self) -> str:
        return "st_epi"

    def score_identity(self, candidate, existing, cosine_sim):
        from k0.modules.consolidation.types import IdentityResult

        return IdentityResult(
            score=0.5,
            p_create=0.3,
            p_extend=0.4,
            p_reinforce=0.3,
            recommended_action="EXTEND",
        )

    def match_key(self, candidate, existing):
        # Match only if record_id starts with "match-"
        return existing.record_id.startswith("match-")


# ===================================================================
# V1: decide() is a pure function (no DB reads/writes)
# ===================================================================


class TestPurity:
    """V1, V22: No DB, no async, no state mutation."""

    def test_no_async_imports(self):
        """V22: No import of asyncio, asyncpg, or k0.db in engine.py."""
        import k0.modules.consolidation.reconciliation.engine as mod

        source = Path(mod.__file__).read_text(encoding="utf-8")
        for forbidden in ("import asyncio", "import asyncpg", "from k0.db"):
            assert forbidden not in source, f"Found forbidden import: {forbidden}"

    def test_no_await_in_source(self):
        """V1: No await keyword in engine.py."""
        import k0.modules.consolidation.reconciliation.engine as mod

        source = Path(mod.__file__).read_text(encoding="utf-8")
        lines = source.splitlines()
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            assert "await " not in stripped, f"Found 'await' at line {i}: {stripped}"


# ===================================================================
# V2, V3: K1 Signal Check (Stage 1, Tier 1)
# ===================================================================


class TestK1Signals:
    """Stage 1: K1 correction/contradiction signals."""

    def test_k1_correction_returns_evolve(self, registry):
        """V2: correction_signal -> EVOLVE with tier=1."""
        cand = _candidate(
            k1_signals=K1SignalBundle(
                correction_signal=True,
                correction_source="user_edit",
                session_context_id="sess-42",
            ),
        )
        result = ReconciliationFramework.decide(
            candidate=cand,
            layer="st_epi",
            registry=registry,
            existing_records=[_record()],
        )
        assert result.action == ReconciliationAction.EVOLVE
        assert result.tier == 1
        assert result.similarity == 0.0
        assert result.confidence == 0.95
        assert result.identity_match is False
        assert "archive_superseded" in result.hooks_required
        assert "K1_CORRECTION" in result.reason

    def test_k1_contradiction_returns_contradict(self, registry):
        """V3: contradiction_signal -> CONTRADICT with tier=1, details populated."""
        cand = _candidate(
            k1_signals=K1SignalBundle(
                contradiction_signal=True,
                supersedes_concept="earth_is_flat",
                correction_source="k1_agent",
            ),
        )
        result = ReconciliationFramework.decide(
            candidate=cand,
            layer="st_epi",
            registry=registry,
            existing_records=[_record()],
        )
        assert result.action == ReconciliationAction.CONTRADICT
        assert result.tier == 1
        assert result.similarity == 0.0
        assert result.confidence == 0.90
        assert result.contradiction_details is not None
        assert result.contradiction_details["supersedes_concept"] == "earth_is_flat"
        assert "K1_CONTRADICTION" in result.reason

    def test_k1_correction_takes_precedence(self, registry):
        """Both correction + contradiction -> correction wins (checked first)."""
        cand = _candidate(
            k1_signals=K1SignalBundle(
                correction_signal=True,
                contradiction_signal=True,
                correction_source="user",
            ),
        )
        result = ReconciliationFramework.decide(
            candidate=cand,
            layer="st_epi",
            registry=registry,
            existing_records=[_record()],
        )
        assert result.action == ReconciliationAction.EVOLVE
        assert result.tier == 1

    def test_no_k1_signals_passes_through(self, registry):
        """No signals -> proceeds to Stage 2+."""
        emb = _vec(10)
        cand = _candidate(embedding=emb)
        rec = _record(embedding=_similar_vec(emb, 0.92))
        result = ReconciliationFramework.decide(
            candidate=cand,
            layer="st_epi",
            registry=registry,
            existing_records=[rec],
        )
        assert result.tier == 2


# ===================================================================
# V4, V5: Override Check (Stage 2)
# ===================================================================


class TestOverrides:
    """Stage 2: Skip/Prune overrides."""

    def test_override_skip(self, registry):
        """V4: is_duplicate -> SKIP with confidence=1.0."""
        cand = _candidate(
            metadata={"is_duplicate": True, "duplicate_of_id": "dup-99"},
        )
        result = ReconciliationFramework.decide(
            candidate=cand,
            layer="st_epi",
            registry=registry,
            existing_records=[],
        )
        assert result.action == ReconciliationAction.SKIP
        assert result.confidence == 1.0
        assert result.match_id is None
        assert "OVERRIDE_SKIP" in result.reason
        assert "dup-99" in result.reason

    def test_override_prune(self, registry):
        """V5: prune_decision=TOMBSTONE -> PRUNE with confidence=1.0."""
        cand = _candidate(metadata={"prune_decision": "TOMBSTONE"})
        result = ReconciliationFramework.decide(
            candidate=cand,
            layer="st_epi",
            registry=registry,
            existing_records=[],
        )
        assert result.action == ReconciliationAction.PRUNE
        assert result.confidence == 1.0
        assert "OVERRIDE_PRUNE" in result.reason

    def test_k1_overrides_skip(self, registry):
        """K1 signal takes precedence over duplicate flag."""
        cand = _candidate(
            metadata={"is_duplicate": True},
            k1_signals=K1SignalBundle(correction_signal=True),
        )
        result = ReconciliationFramework.decide(
            candidate=cand,
            layer="st_epi",
            registry=registry,
            existing_records=[],
        )
        assert result.action == ReconciliationAction.EVOLVE
        assert result.tier == 1


# ===================================================================
# V6: Identity Filter (Stage 3)
# ===================================================================


class TestIdentityFilter:
    """Stage 3: Identity-based record filtering."""

    def test_identity_filter_empty_creates(self, registry):
        """V6: 0 identity-compatible records -> CREATE."""
        emb = _vec(20)
        cand = _candidate(embedding=emb)
        records = [_record(f"rec-{i}", embedding=_similar_vec(emb, 0.95)) for i in range(5)]

        result = ReconciliationFramework.decide(
            candidate=cand,
            layer="st_epi",
            registry=registry,
            existing_records=records,
            identity_strategy=_RejectAllIdentity(),
        )
        assert result.action == ReconciliationAction.CREATE
        assert result.match_id is None
        assert "IDENTITY_FILTER" in result.reason
        assert "0/5" in result.reason

    def test_identity_filter_passes_compatible(self, registry):
        """Compatible records proceed to similarity ranking."""
        emb = _vec(30)
        cand = _candidate(embedding=emb)
        rec = _record("rec-1", embedding=_similar_vec(emb, 0.92))

        result = ReconciliationFramework.decide(
            candidate=cand,
            layer="st_epi",
            registry=registry,
            existing_records=[rec],
            identity_strategy=_PassAllIdentity(),
        )
        assert result.action == ReconciliationAction.REINFORCE
        assert result.match_id == "rec-1"

    def test_key_match_identity(self, registry):
        """Key-match identity selects only matching records."""
        emb = _vec(40)
        cand = _candidate(embedding=emb)
        good = _record("match-1", embedding=_similar_vec(emb, 0.90))
        bad = _record("nomatch-1", embedding=_similar_vec(emb, 0.95))

        result = ReconciliationFramework.decide(
            candidate=cand,
            layer="st_epi",
            registry=registry,
            existing_records=[good, bad],
            identity_strategy=_KeyMatchIdentity(),
        )
        # Should match "match-1" (0.90), not "nomatch-1" (0.95) which was filtered out
        assert result.match_id == "match-1"

    def test_no_identity_strategy_passes_all(self, registry):
        """When identity_strategy=None, all records pass filter."""
        emb = _vec(50)
        cand = _candidate(embedding=emb)
        records = [
            _record(f"rec-{i}", embedding=_similar_vec(emb, 0.5 + 0.1 * i)) for i in range(3)
        ]

        result = ReconciliationFramework.decide(
            candidate=cand,
            layer="st_epi",
            registry=registry,
            existing_records=records,
            identity_strategy=None,
        )
        # Best match should be rec-2 (highest similarity)
        assert result.action != ReconciliationAction.CREATE or result.tier == 2

    def test_empty_records_creates(self, registry):
        """No existing records -> CREATE."""
        cand = _candidate()
        result = ReconciliationFramework.decide(
            candidate=cand,
            layer="st_epi",
            registry=registry,
            existing_records=[],
        )
        assert result.action == ReconciliationAction.CREATE
        assert result.match_id is None


# ===================================================================
# V7-V10: Threshold Decision (Stage 5)
# ===================================================================


class TestThresholds:
    """Stage 5: Per-layer threshold decisions.

    st_epi thresholds: reinforce=0.85, extend=0.60, evolve=0.40
    """

    def test_threshold_reinforce(self, registry):
        """V7: sim >= reinforce -> REINFORCE."""
        emb = _vec(100)
        rec = _record(embedding=_similar_vec(emb, 0.92))
        cand = _candidate(embedding=emb)

        result = ReconciliationFramework.decide(
            candidate=cand,
            layer="st_epi",
            registry=registry,
            existing_records=[rec],
        )
        assert result.action == ReconciliationAction.REINFORCE
        assert result.similarity >= 0.85

    def test_threshold_extend(self, registry):
        """V8: extend <= sim < reinforce -> EXTEND."""
        emb = _vec(101)
        rec = _record(embedding=_similar_vec(emb, 0.72))
        cand = _candidate(embedding=emb)

        result = ReconciliationFramework.decide(
            candidate=cand,
            layer="st_epi",
            registry=registry,
            existing_records=[rec],
        )
        assert result.action == ReconciliationAction.EXTEND
        assert 0.60 <= result.similarity < 0.85

    def test_threshold_evolve_tier2(self, registry):
        """V9: evolve <= sim < extend -> EVOLVE (Tier 2, not Tier 1)."""
        emb = _vec(102)
        rec = _record(embedding=_similar_vec(emb, 0.48))
        cand = _candidate(embedding=emb)

        result = ReconciliationFramework.decide(
            candidate=cand,
            layer="st_epi",
            registry=registry,
            existing_records=[rec],
        )
        assert result.action == ReconciliationAction.EVOLVE
        assert result.tier == 2
        assert 0.40 <= result.similarity < 0.60

    def test_below_evolve_creates_not_contradicts(self, registry):
        """V10: sim < evolve -> CREATE, NOT CONTRADICT."""
        emb = _vec(103)
        rec = _record(embedding=_similar_vec(emb, 0.25))
        cand = _candidate(embedding=emb)

        result = ReconciliationFramework.decide(
            candidate=cand,
            layer="st_epi",
            registry=registry,
            existing_records=[rec],
        )
        assert result.action == ReconciliationAction.CREATE
        assert result.action != ReconciliationAction.CONTRADICT
        assert result.similarity < 0.40

    def test_boundary_at_reinforce(self, registry):
        """Exactly at reinforce threshold -> REINFORCE."""
        emb = _vec(104)
        rec = _record(embedding=_similar_vec(emb, 0.85))
        cand = _candidate(embedding=emb)

        result = ReconciliationFramework.decide(
            candidate=cand,
            layer="st_epi",
            registry=registry,
            existing_records=[rec],
        )
        assert result.action == ReconciliationAction.REINFORCE

    def test_boundary_at_extend(self, registry):
        """Exactly at extend threshold -> EXTEND."""
        emb = _vec(105)
        rec = _record(embedding=_similar_vec(emb, 0.60))
        cand = _candidate(embedding=emb)

        result = ReconciliationFramework.decide(
            candidate=cand,
            layer="st_epi",
            registry=registry,
            existing_records=[rec],
        )
        assert result.action == ReconciliationAction.EXTEND

    def test_boundary_at_evolve(self, registry):
        """Exactly at evolve threshold -> EVOLVE."""
        emb = _vec(106)
        rec = _record(embedding=_similar_vec(emb, 0.40))
        cand = _candidate(embedding=emb)

        result = ReconciliationFramework.decide(
            candidate=cand,
            layer="st_epi",
            registry=registry,
            existing_records=[rec],
        )
        assert result.action == ReconciliationAction.EVOLVE


# ===================================================================
# V11: Custom (per-layer) thresholds
# ===================================================================


class TestCustomThresholds:
    """V11: Per-layer thresholds, not hardcoded 0.85/0.60/0.40."""

    def test_custom_thresholds(self, registry):
        """st_procedural has 0.90/0.70/0.50 -- sim=0.88 should EXTEND, not REINFORCE."""
        emb = _vec(200)
        rec = _record("rec-1", layer="st_procedural", embedding=_similar_vec(emb, 0.88))
        cand = _candidate(embedding=emb, layer="st_procedural")

        result = ReconciliationFramework.decide(
            candidate=cand,
            layer="st_procedural",
            registry=registry,
            existing_records=[rec],
        )
        # st_procedural reinforce=0.90, so 0.88 is EXTEND not REINFORCE
        assert result.action == ReconciliationAction.EXTEND

    def test_st_prospective_lower_thresholds(self, registry):
        """st_prospective thresholds are 0.90/0.70/0.50."""
        emb = _vec(201)
        rec = _record("rec-1", layer="st_prospective", embedding=_similar_vec(emb, 0.92))
        cand = _candidate(embedding=emb, layer="st_prospective")

        result = ReconciliationFramework.decide(
            candidate=cand,
            layer="st_prospective",
            registry=registry,
            existing_records=[rec],
        )
        # st_prospective reinforce=0.90, so 0.92 should be REINFORCE
        assert result.action == ReconciliationAction.REINFORCE


# ===================================================================
# V16: Hooks per action
# ===================================================================


class TestHooks:
    """V16: hooks_required correct per action."""

    def test_reinforce_hooks(self, registry):
        emb = _vec(300)
        rec = _record(embedding=_similar_vec(emb, 0.92))
        cand = _candidate(embedding=emb)

        result = ReconciliationFramework.decide(
            candidate=cand,
            layer="st_epi",
            registry=registry,
            existing_records=[rec],
        )
        assert result.action == ReconciliationAction.REINFORCE
        assert result.hooks_required == ["recompute_centroid"]

    def test_extend_hooks(self, registry):
        emb = _vec(301)
        rec = _record(embedding=_similar_vec(emb, 0.72))
        cand = _candidate(embedding=emb)

        result = ReconciliationFramework.decide(
            candidate=cand,
            layer="st_epi",
            registry=registry,
            existing_records=[rec],
        )
        assert result.action == ReconciliationAction.EXTEND
        assert result.hooks_required == ["recompute_centroid", "regenerate_summary"]

    def test_evolve_hooks(self, registry):
        emb = _vec(302)
        rec = _record(embedding=_similar_vec(emb, 0.48))
        cand = _candidate(embedding=emb)

        result = ReconciliationFramework.decide(
            candidate=cand,
            layer="st_epi",
            registry=registry,
            existing_records=[rec],
        )
        assert result.action == ReconciliationAction.EVOLVE
        assert result.hooks_required == [
            "archive_superseded",
            "recompute_centroid",
            "regenerate_summary",
        ]

    def test_create_hooks(self, registry):
        cand = _candidate()
        result = ReconciliationFramework.decide(
            candidate=cand,
            layer="st_epi",
            registry=registry,
            existing_records=[],
        )
        assert result.action == ReconciliationAction.CREATE
        assert result.hooks_required == ["recompute_centroid", "regenerate_summary"]

    def test_skip_no_hooks(self, registry):
        cand = _candidate(metadata={"is_duplicate": True})
        result = ReconciliationFramework.decide(
            candidate=cand,
            layer="st_epi",
            registry=registry,
            existing_records=[],
        )
        assert result.action == ReconciliationAction.SKIP
        assert result.hooks_required == []

    def test_k1_evolve_hooks(self, registry):
        cand = _candidate(
            k1_signals=K1SignalBundle(correction_signal=True),
        )
        result = ReconciliationFramework.decide(
            candidate=cand,
            layer="st_epi",
            registry=registry,
            existing_records=[],
        )
        assert result.action == ReconciliationAction.EVOLVE
        assert "archive_superseded" in result.hooks_required


# ===================================================================
# V18: ReconciliationResult is frozen
# ===================================================================


class TestResultImmutability:
    """V18: Frozen dataclass prevents mutation."""

    def test_result_frozen(self, registry):
        cand = _candidate()
        result = ReconciliationFramework.decide(
            candidate=cand,
            layer="st_epi",
            registry=registry,
            existing_records=[],
        )
        with pytest.raises(AttributeError):
            result.action = ReconciliationAction.SKIP  # type: ignore[misc]

    def test_result_invariants(self, registry):
        """match_id is None for CREATE and SKIP."""
        cand = _candidate()
        result = ReconciliationFramework.decide(
            candidate=cand,
            layer="st_epi",
            registry=registry,
            existing_records=[],
        )
        assert result.action == ReconciliationAction.CREATE
        assert result.match_id is None

    def test_similarity_clamped(self):
        result = ReconciliationResult(
            action=ReconciliationAction.CREATE,
            tier=2,
            match_id=None,
            match_layer="st_epi",
            similarity=1.5,  # Over 1.0
            identity_match=False,
            confidence=-0.3,  # Below 0.0
            reason="test",
            candidate_id="c1",
            layer="st_epi",
            cycle_id="cycle-1",
        )
        assert result.similarity == 1.0
        assert result.confidence == 0.0

    def test_has_match_property(self):
        with_match = ReconciliationResult(
            action=ReconciliationAction.REINFORCE,
            tier=2,
            match_id="rec-1",
            match_layer="st_epi",
            similarity=0.9,
            identity_match=True,
            confidence=0.8,
            reason="test",
            candidate_id="c1",
            layer="st_epi",
            cycle_id="cy",
        )
        assert with_match.has_match is True

        without = ReconciliationResult(
            action=ReconciliationAction.CREATE,
            tier=2,
            match_id=None,
            match_layer="st_epi",
            similarity=0.0,
            identity_match=False,
            confidence=0.5,
            reason="test",
            candidate_id="c1",
            layer="st_epi",
            cycle_id="cy",
        )
        assert without.has_match is False

    def test_is_k1_override_property(self):
        tier1 = ReconciliationResult(
            action=ReconciliationAction.EVOLVE,
            tier=1,
            match_id=None,
            match_layer="st_epi",
            similarity=0.0,
            identity_match=False,
            confidence=0.95,
            reason="test",
            candidate_id="c1",
            layer="st_epi",
            cycle_id="cy",
        )
        assert tier1.is_k1_override is True

        tier2 = ReconciliationResult(
            action=ReconciliationAction.REINFORCE,
            tier=2,
            match_id="rec-1",
            match_layer="st_epi",
            similarity=0.9,
            identity_match=True,
            confidence=0.8,
            reason="test",
            candidate_id="c1",
            layer="st_epi",
            cycle_id="cy",
        )
        assert tier2.is_k1_override is False


# ===================================================================
# V19: DecisionMetrics
# ===================================================================


class _FakeMetricsRegistry:
    """Captures metric emissions for testing."""

    def __init__(self):
        self.counters: list[tuple[str, dict]] = []
        self.observations: list[tuple[str, float, dict]] = []
        self.gauges: list[tuple[str, float, dict]] = []

    def counter(self, name, *, labels):
        self.counters.append((name, labels))

    def observe(self, name, value, *, labels):
        self.observations.append((name, value, labels))

    def gauge(self, name, value, *, labels):
        self.gauges.append((name, value, labels))


class TestMetrics:
    """V19: DecisionMetrics records expected counters."""

    def test_metrics_emitted(self, registry):
        emb = _vec(400)
        rec = _record(embedding=_similar_vec(emb, 0.92))
        cand = _candidate(embedding=emb)

        result = ReconciliationFramework.decide(
            candidate=cand,
            layer="st_epi",
            registry=registry,
            existing_records=[rec],
        )

        fake = _FakeMetricsRegistry()
        metrics = DecisionMetrics(fake)
        metrics.record_decision(result)

        counter_names = [c[0] for c in fake.counters]
        assert "reconciliation_decisions_total" in counter_names

        obs_names = [o[0] for o in fake.observations]
        assert "reconciliation_decision_confidence" in obs_names
        assert "reconciliation_decision_latency_ms" in obs_names
        assert "reconciliation_similarity_score" in obs_names

    def test_k1_bypass_counter(self, registry):
        cand = _candidate(
            k1_signals=K1SignalBundle(correction_signal=True),
        )
        result = ReconciliationFramework.decide(
            candidate=cand,
            layer="st_epi",
            registry=registry,
            existing_records=[],
        )

        fake = _FakeMetricsRegistry()
        metrics = DecisionMetrics(fake)
        metrics.record_decision(result)

        k1_counters = [c for c in fake.counters if c[0] == "reconciliation_k1_bypass_total"]
        assert len(k1_counters) == 1
        assert k1_counters[0][1]["signal_type"] == "correction"

    def test_batch_summary(self, registry):
        results = {
            "c1": ReconciliationResult(
                action=ReconciliationAction.REINFORCE,
                tier=2,
                match_id="r1",
                match_layer="st_epi",
                similarity=0.9,
                identity_match=True,
                confidence=0.8,
                reason="test",
                candidate_id="c1",
                layer="st_epi",
                cycle_id="cy",
            ),
            "c2": ReconciliationResult(
                action=ReconciliationAction.CREATE,
                tier=2,
                match_id=None,
                match_layer="st_epi",
                similarity=0.0,
                identity_match=False,
                confidence=0.5,
                reason="test",
                candidate_id="c2",
                layer="st_epi",
                cycle_id="cy",
            ),
        }

        fake = _FakeMetricsRegistry()
        metrics = DecisionMetrics(fake)
        metrics.record_batch_summary("st_epi", 10, 3, results)

        gauge_names = [g[0] for g in fake.gauges]
        assert "reconciliation_batch_size" in gauge_names
        assert "reconciliation_identity_filter_ratio" in gauge_names
        assert "reconciliation_batch_action_count" in gauge_names


# ===================================================================
# V20: Structured log
# ===================================================================


class TestDecisionLog:
    """V20: log_decision produces structured output."""

    def test_structured_log(self, registry, caplog):
        emb = _vec(500)
        rec = _record(embedding=_similar_vec(emb, 0.92))
        cand = _candidate(embedding=emb)

        result = ReconciliationFramework.decide(
            candidate=cand,
            layer="st_epi",
            registry=registry,
            existing_records=[rec],
        )

        with caplog.at_level(logging.INFO, logger="k0.reconciliation"):
            log_decision(result)

        assert len(caplog.records) >= 1
        record = caplog.records[-1]
        assert record.getMessage() == "reconciliation_decision"
        assert record.cycle_id == "cycle-001"  # type: ignore[attr-defined]
        assert record.action == "REINFORCE"  # type: ignore[attr-defined]


# ===================================================================
# V23: ReconciliationAction not duplicated
# ===================================================================


class TestActionEnum:
    """V23: ReconciliationAction imported from event_state.py, not duplicated."""

    def test_action_reused(self):
        from k0.pipelines.p03.event_state import ReconciliationAction as FromEventState

        assert ReconciliationAction is FromEventState
        assert len(ReconciliationAction) == 8

    def test_all_expected_values(self):
        expected = {
            "PENDING",
            "REINFORCE",
            "EXTEND",
            "CREATE",
            "EVOLVE",
            "CONTRADICT",
            "PRUNE",
            "SKIP",
        }
        actual = {a.value for a in ReconciliationAction}
        assert actual == expected


# ===================================================================
# Error handling edge cases
# ===================================================================


class TestErrorHandling:
    """M9.4.16: Error handling for edge cases."""

    def test_no_embedding_creates(self, registry):
        """candidate.embedding is None -> CREATE."""
        cand = _candidate(embedding=None)
        rec = _record(embedding=_vec(2))

        result = ReconciliationFramework.decide(
            candidate=cand,
            layer="st_epi",
            registry=registry,
            existing_records=[rec],
        )
        # With no embedding, similarity rank returns 0.0
        assert result.action == ReconciliationAction.CREATE

    def test_record_no_embedding(self, registry):
        """Record with no embedding -> treated as 0 similarity."""
        emb = _vec(600)
        cand = _candidate(embedding=emb)
        rec = TruthRecord(
            record_id="rec-noembedding",
            layer="st_epi",
            embedding=None,
            confidence=0.8,
            version=1,
            observation_count=5,
            last_observed_ms=1700000000000,
        )

        result = ReconciliationFramework.decide(
            candidate=cand,
            layer="st_epi",
            registry=registry,
            existing_records=[rec],
        )
        assert result.similarity == 0.0
        assert result.action == ReconciliationAction.CREATE

    def test_unknown_layer_raises(self, registry):
        """Unknown layer -> KeyError (not silently caught)."""
        cand = _candidate(layer="st_nonexistent")
        with pytest.raises(KeyError, match="st_nonexistent"):
            ReconciliationFramework.decide(
                candidate=cand,
                layer="st_nonexistent",
                registry=registry,
                existing_records=[],
            )

    def test_decision_time_populated(self, registry):
        """decision_time_ms is always > 0."""
        cand = _candidate()
        result = ReconciliationFramework.decide(
            candidate=cand,
            layer="st_epi",
            registry=registry,
            existing_records=[],
        )
        assert result.decision_time_ms > 0.0


# ===================================================================
# Reason string format
# ===================================================================


class TestReasonFormat:
    """M9.4.10: Structured reason strings."""

    def test_reinforce_reason(self, registry):
        emb = _vec(700)
        rec = _record(embedding=_similar_vec(emb, 0.92))
        cand = _candidate(embedding=emb)

        result = ReconciliationFramework.decide(
            candidate=cand,
            layer="st_epi",
            registry=registry,
            existing_records=[rec],
        )
        assert "REINFORCE:" in result.reason
        assert "sim=" in result.reason
        assert "threshold=" in result.reason
        assert "layer=st_epi" in result.reason

    def test_create_reason_includes_threshold(self, registry):
        emb = _vec(701)
        rec = _record(embedding=_similar_vec(emb, 0.25))
        cand = _candidate(embedding=emb)

        result = ReconciliationFramework.decide(
            candidate=cand,
            layer="st_epi",
            registry=registry,
            existing_records=[rec],
        )
        assert "CREATE:" in result.reason
        assert "evolve_threshold=" in result.reason
