"""Batch coordination tests for ReconciliationFramework (M9.4).

Covers V12 (batch == N individual), V13 (empty batch),
plus query deduplication and mixed-layer scenarios.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from k0.modules.consolidation.reconciliation.engine import ReconciliationFramework
from k0.modules.consolidation.truth_layer_registry import TruthLayerRegistry
from k0.modules.consolidation.types import K1SignalBundle, ReconciliationCandidate, TruthRecord
from k0.pipelines.p03.event_state import ReconciliationAction

_CONTRACTS_DIR = Path(__file__).resolve().parents[5] / "k0" / "contracts" / "schemas"


@pytest.fixture()
def registry() -> TruthLayerRegistry:
    return TruthLayerRegistry.from_contracts(_CONTRACTS_DIR)


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


def _candidate(cid: str, seed: int, **kwargs) -> ReconciliationCandidate:
    return ReconciliationCandidate(
        candidate_id=cid,
        layer=kwargs.get("layer", "st_epi"),
        source_phase="R3",
        embedding=kwargs.get("embedding", _vec(seed)),
        k1_signals=kwargs.get("k1_signals", K1SignalBundle()),
        metadata=kwargs.get("metadata", {}),
        cycle_id=kwargs.get("cycle_id", "cycle-batch"),
        tenant_id="t1",
        space_id="s1",
    )


def _record(rid: str, embedding: list[float] | None = None) -> TruthRecord:
    return TruthRecord(
        record_id=rid,
        layer="st_epi",
        embedding=embedding or _vec(999),
        confidence=0.8,
        version=1,
        observation_count=5,
        last_observed_ms=1700000000000,
    )


# ===================================================================
# V12: batch equals individual
# ===================================================================


class TestBatchEqualsIndividual:
    """V12: decide_batch() produces same results as N individual decide() calls."""

    def test_batch_equals_individual(self, registry):
        emb1 = _vec(10)
        emb2 = _vec(20)
        emb3 = _vec(30)

        records = [
            _record("r1", _similar_vec(emb1, 0.92)),
            _record("r2", _similar_vec(emb2, 0.72)),
            _record("r3", _similar_vec(emb3, 0.48)),
        ]

        candidates = [
            _candidate("c1", 10, embedding=emb1),
            _candidate("c2", 20, embedding=emb2),
            _candidate("c3", 30, embedding=emb3),
        ]

        # Batch
        batch_results = ReconciliationFramework.decide_batch(
            candidates=candidates,
            layer="st_epi",
            registry=registry,
            existing_records=records,
        )

        # Individual
        for cand in candidates:
            individual = ReconciliationFramework.decide(
                candidate=cand,
                layer="st_epi",
                registry=registry,
                existing_records=records,
            )
            batch_result = batch_results[cand.candidate_id]

            assert batch_result.action == individual.action
            assert batch_result.match_id == individual.match_id
            assert batch_result.tier == individual.tier
            assert abs(batch_result.similarity - individual.similarity) < 1e-6
            assert abs(batch_result.confidence - individual.confidence) < 1e-6

    def test_batch_with_mixed_actions(self, registry):
        """Batch with K1 signal, duplicate, and normal candidate."""
        emb = _vec(50)
        records = [_record("r1", _similar_vec(emb, 0.92))]

        candidates = [
            _candidate("k1-cand", 50, k1_signals=K1SignalBundle(correction_signal=True)),
            _candidate("dup-cand", 50, metadata={"is_duplicate": True}),
            _candidate("normal", 50, embedding=emb),
        ]

        results = ReconciliationFramework.decide_batch(
            candidates=candidates,
            layer="st_epi",
            registry=registry,
            existing_records=records,
        )

        assert results["k1-cand"].action == ReconciliationAction.EVOLVE
        assert results["k1-cand"].tier == 1
        assert results["dup-cand"].action == ReconciliationAction.SKIP
        assert results["normal"].action == ReconciliationAction.REINFORCE


# ===================================================================
# V13: empty batch
# ===================================================================


class TestEmptyBatch:
    """V13: Empty batch returns empty dict."""

    def test_empty_batch(self, registry):
        results = ReconciliationFramework.decide_batch(
            candidates=[],
            layer="st_epi",
            registry=registry,
            existing_records=[_record("r1")],
        )
        assert results == {}

    def test_batch_with_empty_records(self, registry):
        """All candidates -> CREATE when no records exist."""
        candidates = [
            _candidate("c1", 10),
            _candidate("c2", 20),
        ]
        results = ReconciliationFramework.decide_batch(
            candidates=candidates,
            layer="st_epi",
            registry=registry,
            existing_records=[],
        )
        for r in results.values():
            assert r.action == ReconciliationAction.CREATE


# ===================================================================
# Batch size and result keys
# ===================================================================


class TestBatchMechanics:
    """Batch mechanics: key mapping, ordering."""

    def test_result_keys_match_candidate_ids(self, registry):
        candidates = [_candidate(f"c{i}", i) for i in range(5)]
        results = ReconciliationFramework.decide_batch(
            candidates=candidates,
            layer="st_epi",
            registry=registry,
            existing_records=[],
        )
        assert set(results.keys()) == {f"c{i}" for i in range(5)}

    def test_large_batch(self, registry):
        """50 candidates, all CREATE."""
        candidates = [_candidate(f"c{i}", i) for i in range(50)]
        results = ReconciliationFramework.decide_batch(
            candidates=candidates,
            layer="st_epi",
            registry=registry,
            existing_records=[],
        )
        assert len(results) == 50
        for r in results.values():
            assert r.action == ReconciliationAction.CREATE

    def test_single_candidate_batch(self, registry):
        """Batch of 1 works."""
        emb = _vec(100)
        records = [_record("r1", _similar_vec(emb, 0.92))]
        results = ReconciliationFramework.decide_batch(
            candidates=[_candidate("c1", 100, embedding=emb)],
            layer="st_epi",
            registry=registry,
            existing_records=records,
        )
        assert len(results) == 1
        assert results["c1"].action == ReconciliationAction.REINFORCE

    def test_batch_preserves_cycle_id(self, registry):
        candidates = [_candidate("c1", 1, cycle_id="cy-42")]
        results = ReconciliationFramework.decide_batch(
            candidates=candidates,
            layer="st_epi",
            registry=registry,
            existing_records=[],
        )
        assert results["c1"].cycle_id == "cy-42"
