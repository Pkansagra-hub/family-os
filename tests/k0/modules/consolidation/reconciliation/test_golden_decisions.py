"""Golden decision vector tests for ReconciliationFramework (M9.4).

Covers V17: 7 golden vectors (G1-G7) from M9.4.18.
Each vector is an end-to-end test through the full 6-stage pipeline
with exact expected outputs.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from k0.modules.consolidation.reconciliation.engine import ReconciliationFramework
from k0.modules.consolidation.truth_layer_registry import TruthLayerRegistry
from k0.modules.consolidation.types import K1SignalBundle, ReconciliationCandidate, TruthRecord
from k0.pipelines.p03.event_state import ReconciliationAction

# ===================================================================
# Shared fixtures
# ===================================================================

_CONTRACTS_DIR = Path(__file__).resolve().parents[5] / "k0" / "contracts" / "schemas"


@pytest.fixture()
def registry() -> TruthLayerRegistry:
    return TruthLayerRegistry.from_contracts(_CONTRACTS_DIR)


def _vec(seed: int, dim: int = 768) -> list[float]:
    """Deterministic L2-normalized vector."""
    rng = np.random.default_rng(seed)
    v = rng.standard_normal(dim)
    v /= np.linalg.norm(v)
    return v.tolist()


def _similar_vec(base: list[float], target_sim: float) -> list[float]:
    """Create a vector with approximately target_sim cosine similarity to base."""
    b = np.asarray(base, dtype=np.float64)
    b /= np.linalg.norm(b)

    rng = np.random.default_rng(42)
    noise = rng.standard_normal(len(base))
    noise -= np.dot(noise, b) * b
    noise /= np.linalg.norm(noise)

    theta = math.acos(max(-1.0, min(1.0, target_sim)))
    v = math.cos(theta) * b + math.sin(theta) * noise
    v /= np.linalg.norm(v)
    return v.tolist()


class _PassAllIdentity:
    """Identity strategy that accepts all records via key match."""

    @property
    def layer_name(self) -> str:
        return "st_epi"

    def match_key(self, candidate, existing):
        return True

    def score_identity(self, candidate, existing, cosine_sim):
        from k0.modules.consolidation.types import IdentityResult

        return IdentityResult(
            score=0.8,
            p_create=0.1,
            p_extend=0.5,
            p_reinforce=0.4,
            recommended_action="EXTEND",
        )


class _RejectAllIdentity:
    """Identity strategy that rejects all records."""

    @property
    def layer_name(self) -> str:
        return "st_epi"

    def match_key(self, candidate, existing):
        return None  # Inconclusive -> falls to score_identity

    def score_identity(self, candidate, existing, cosine_sim):
        from k0.modules.consolidation.types import IdentityResult

        return IdentityResult(
            score=0.1,
            p_create=0.9,
            p_extend=0.05,
            p_reinforce=0.05,
            recommended_action="CREATE",
        )


def _candidate(
    embedding: list[float] | None = None,
    k1_signals: K1SignalBundle | None = None,
    metadata: dict[str, Any] | None = None,
) -> ReconciliationCandidate:
    return ReconciliationCandidate(
        candidate_id="golden-cand",
        layer="st_epi",
        source_phase="R2",
        embedding=embedding or _vec(1),
        k1_signals=k1_signals or K1SignalBundle(),
        metadata=metadata or {},
        cycle_id="golden-cycle",
        tenant_id="test-tenant",
        space_id="test-space",
    )


def _record(record_id: str, embedding: list[float] | None = None) -> TruthRecord:
    return TruthRecord(
        record_id=record_id,
        layer="st_epi",
        embedding=embedding or _vec(50),
        confidence=0.80,
        version=1,
        observation_count=3,
        last_observed_ms=1700000000000,
        metadata={},
    )


# ===================================================================
# G1: EVOLVE (Tier 1) -- K1 correction signal
# ===================================================================


class TestGoldenG1:
    """G1: K1 correction signal -> EVOLVE Tier 1."""

    def test_g1_evolve_tier1(self, registry):
        signals = K1SignalBundle(
            correction_signal=True,
            contradiction_signal=False,
            correction_source="user_edit",
            session_context_id="sess-001",
        )
        cand = _candidate(k1_signals=signals)
        records = [_record("ep-existing")]

        result = ReconciliationFramework.decide(
            candidate=cand,
            layer="st_epi",
            registry=registry,
            existing_records=records,
        )

        assert result.action == ReconciliationAction.EVOLVE
        assert result.tier == 1
        assert result.similarity == 0.0
        assert result.confidence == 0.95
        assert result.match_id is None
        assert "K1_CORRECTION" in result.reason


# ===================================================================
# G2: CONTRADICT (Tier 1) -- K1 contradiction signal
# ===================================================================


class TestGoldenG2:
    """G2: K1 contradiction signal -> CONTRADICT Tier 1."""

    def test_g2_contradict_tier1(self, registry):
        signals = K1SignalBundle(
            correction_signal=False,
            contradiction_signal=True,
            supersedes_concept="old_fact",
            correction_source="user_edit",
            session_context_id="sess-002",
        )
        cand = _candidate(k1_signals=signals)
        records = [_record("ep-existing")]

        result = ReconciliationFramework.decide(
            candidate=cand,
            layer="st_epi",
            registry=registry,
            existing_records=records,
        )

        assert result.action == ReconciliationAction.CONTRADICT
        assert result.tier == 1
        assert result.similarity == 0.0
        assert result.confidence == 0.90
        assert result.contradiction_details is not None
        assert result.contradiction_details["supersedes_concept"] == "old_fact"
        assert "K1_CONTRADICTION" in result.reason


# ===================================================================
# G3: SKIP (Override) -- duplicate metadata
# ===================================================================


class TestGoldenG3:
    """G3: is_duplicate=True -> SKIP."""

    def test_g3_skip_override(self, registry):
        cand = _candidate(metadata={"is_duplicate": True})
        records = [_record("ep-existing")]

        result = ReconciliationFramework.decide(
            candidate=cand,
            layer="st_epi",
            registry=registry,
            existing_records=records,
        )

        assert result.action == ReconciliationAction.SKIP
        assert result.tier == 2
        assert result.confidence == 1.0
        assert result.match_id is None
        assert "OVERRIDE_SKIP" in result.reason


# ===================================================================
# G4: REINFORCE (Tier 2) -- sim=0.92 with identity match
# ===================================================================


class TestGoldenG4:
    """G4: High similarity (0.92) -> REINFORCE."""

    def test_g4_reinforce(self, registry):
        base = _vec(10)
        match_emb = _similar_vec(base, 0.92)
        cand = _candidate(embedding=base)
        records = [_record("ep-match", embedding=match_emb)]

        result = ReconciliationFramework.decide(
            candidate=cand,
            layer="st_epi",
            registry=registry,
            existing_records=records,
            identity_strategy=_PassAllIdentity(),
        )

        assert result.action == ReconciliationAction.REINFORCE
        assert result.tier == 2
        assert result.match_id == "ep-match"
        assert result.match_layer == "st_epi"
        # slerp-constructed vector should be close to 0.92
        assert abs(result.similarity - 0.92) < 0.02
        assert result.identity_match is True
        assert "recompute_centroid" in result.hooks_required
        assert "REINFORCE" in result.reason


# ===================================================================
# G5: EXTEND (Tier 2) -- sim=0.72
# ===================================================================


class TestGoldenG5:
    """G5: Medium similarity (0.72) -> EXTEND."""

    def test_g5_extend(self, registry):
        base = _vec(20)
        match_emb = _similar_vec(base, 0.72)
        cand = _candidate(embedding=base)
        records = [_record("ep-match", embedding=match_emb)]

        result = ReconciliationFramework.decide(
            candidate=cand,
            layer="st_epi",
            registry=registry,
            existing_records=records,
            identity_strategy=_PassAllIdentity(),
        )

        assert result.action == ReconciliationAction.EXTEND
        assert result.tier == 2
        assert result.match_id == "ep-match"
        assert abs(result.similarity - 0.72) < 0.02
        assert "recompute_centroid" in result.hooks_required
        assert "regenerate_summary" in result.hooks_required
        assert "EXTEND" in result.reason


# ===================================================================
# G6: EVOLVE (Tier 2) -- sim=0.48
# ===================================================================


class TestGoldenG6:
    """G6: Low similarity (0.48) -> EVOLVE Tier 2."""

    def test_g6_evolve_tier2(self, registry):
        base = _vec(30)
        match_emb = _similar_vec(base, 0.48)
        cand = _candidate(embedding=base)
        records = [_record("ep-match", embedding=match_emb)]

        result = ReconciliationFramework.decide(
            candidate=cand,
            layer="st_epi",
            registry=registry,
            existing_records=records,
            identity_strategy=_PassAllIdentity(),
        )

        assert result.action == ReconciliationAction.EVOLVE
        assert result.tier == 2
        assert result.match_id == "ep-match"
        assert abs(result.similarity - 0.48) < 0.02
        assert "archive_superseded" in result.hooks_required
        assert "recompute_centroid" in result.hooks_required
        assert "regenerate_summary" in result.hooks_required
        assert "EVOLVE" in result.reason


# ===================================================================
# G7: CREATE (Tier 2) -- no identity-compatible records
# ===================================================================


class TestGoldenG7:
    """G7: No identity-compatible records -> CREATE."""

    def test_g7_create_no_compatible(self, registry):
        cand = _candidate(embedding=_vec(40))
        # 5 records, all identity-incompatible
        records = [_record(f"ep-{i}", embedding=_vec(100 + i)) for i in range(5)]

        result = ReconciliationFramework.decide(
            candidate=cand,
            layer="st_epi",
            registry=registry,
            existing_records=records,
            identity_strategy=_RejectAllIdentity(),
        )

        assert result.action == ReconciliationAction.CREATE
        assert result.tier == 2
        assert result.similarity == 0.0
        assert result.match_id is None
        assert "recompute_centroid" in result.hooks_required
        assert "regenerate_summary" in result.hooks_required
        assert "CREATE" in result.reason
