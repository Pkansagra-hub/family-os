"""
Tests for Epic 4.1 issues 4.1.1 (EmbeddingIndex) and 4.1.2 (HardFilter).

Covers:
  - EmbeddingIndex: add/remove/update/search/rebuild, IVF strategy,
    dimension validation, thread safety, edge cases.
  - HardFilter: safety band, availability, input satisfiability,
    config toggles, filter_passed convenience, edge cases.
  - Module __init__.py exports.

Test doubles:
  - numpy arrays as embeddings (no real model needed).
  - FilterCandidate for HardFilter inputs.

Run:
    python -m pytest tests/k1/fabric/test_retrieval_411_412.py -v --tb=short
"""

from __future__ import annotations

import numpy as np
import pytest

# ---------------------------------------------------------------------------
# Imports under test -- EmbeddingIndex (4.1.1)
# ---------------------------------------------------------------------------
from k1.fabric.retrieval.embedding_index import (
    DEFAULT_DIMENSION,
    IVF_THRESHOLD,
    DimensionMismatchError,
    DuplicateVectorError,
    EmbeddingIndex,
    EmbeddingIndexConfig,
    EmbeddingIndexError,
    SearchHit,
    VectorNotFoundError,
)

# ---------------------------------------------------------------------------
# Imports under test -- HardFilter (4.1.2)
# ---------------------------------------------------------------------------
from k1.fabric.retrieval.hard_filter import (
    DEFAULT_SATISFIABILITY_THRESHOLD,
    REASON_INPUT_UNSATISFIABLE,
    REASON_OFFLINE,
    REASON_SAFETY_BAND,
    FilterCandidate,
    FilterResult,
    HardFilter,
    HardFilterConfig,
)

# ===================================================================
# Helpers
# ===================================================================

DIM = 8  # small dimension for fast tests


def _rand(dim: int = DIM, seed: int = 0) -> np.ndarray:
    rng = np.random.RandomState(seed)
    return rng.randn(dim).astype(np.float32)


def _index(dim: int = DIM, **kwargs) -> EmbeddingIndex:
    return EmbeddingIndex(EmbeddingIndexConfig(dimension=dim, **kwargs))


def _candidate(
    name: str = "tool.test",
    band: str = "GREEN",
    avail: str = "ONLINE",
    required: frozenset | None = None,
    contract: object = None,
) -> FilterCandidate:
    return FilterCandidate(
        contract_name=name,
        safety_band_min=band,
        availability=avail,
        required_input_names=required or frozenset(),
        contract=contract,
    )


# ===================================================================
# 4.1.1 -- EmbeddingIndex
# ===================================================================


class TestEmbeddingIndexAddRemove:
    """Basic add / remove / contains / size."""

    def test_add_and_contains(self) -> None:
        idx = _index()
        idx.add_vector("a", _rand())
        assert idx.contains("a")
        assert idx.size == 1

    def test_add_multiple(self) -> None:
        idx = _index()
        idx.add_vector("a", _rand(seed=1))
        idx.add_vector("b", _rand(seed=2))
        assert idx.size == 2
        assert idx.contains("a")
        assert idx.contains("b")

    def test_add_duplicate_raises(self) -> None:
        idx = _index()
        idx.add_vector("a", _rand())
        with pytest.raises(DuplicateVectorError) as exc:
            idx.add_vector("a", _rand(seed=1))
        assert exc.value.contract_id == "a"

    def test_add_empty_id_raises(self) -> None:
        idx = _index()
        with pytest.raises(ValueError, match="non-empty"):
            idx.add_vector("", _rand())

    def test_remove_existing(self) -> None:
        idx = _index()
        idx.add_vector("a", _rand())
        idx.remove_vector("a")
        assert not idx.contains("a")
        assert idx.size == 0

    def test_remove_nonexistent_raises(self) -> None:
        idx = _index()
        with pytest.raises(VectorNotFoundError) as exc:
            idx.remove_vector("x")
        assert exc.value.contract_id == "x"

    def test_add_after_remove(self) -> None:
        idx = _index()
        idx.add_vector("a", _rand())
        idx.remove_vector("a")
        idx.add_vector("a", _rand(seed=99))
        assert idx.contains("a")


class TestEmbeddingIndexDimension:
    """Dimension validation."""

    def test_wrong_dimension_raises(self) -> None:
        idx = _index(dim=8)
        bad = np.zeros(16, dtype=np.float32)
        with pytest.raises(DimensionMismatchError) as exc:
            idx.add_vector("a", bad)
        assert exc.value.expected == 8
        assert exc.value.got == 16

    def test_dimension_property(self) -> None:
        idx = _index(dim=32)
        assert idx.dimension == 32

    def test_auto_cast_to_float32(self) -> None:
        idx = _index()
        vec = np.ones(DIM, dtype=np.float64)
        idx.add_vector("a", vec)
        assert idx.contains("a")

    def test_list_coerced(self) -> None:
        idx = _index()
        vec = [1.0] * DIM
        idx.add_vector("a", np.array(vec))
        assert idx.contains("a")


class TestEmbeddingIndexSearch:
    """Search operations."""

    def test_search_empty_index(self) -> None:
        idx = _index()
        hits = idx.search(_rand(), k=5)
        assert hits == []

    def test_search_single_vector(self) -> None:
        idx = _index()
        vec = _rand()
        idx.add_vector("a", vec)
        hits = idx.search(vec, k=1)
        assert len(hits) == 1
        assert hits[0].contract_id == "a"
        assert hits[0].score > 0

    def test_search_returns_nearest(self) -> None:
        idx = _index()
        target = np.ones(DIM, dtype=np.float32)
        close = target + 0.01 * np.ones(DIM, dtype=np.float32)
        far = target + 10.0 * np.ones(DIM, dtype=np.float32)
        idx.add_vector("close", close)
        idx.add_vector("far", far)
        hits = idx.search(target, k=2)
        assert hits[0].contract_id == "close"
        assert hits[1].contract_id == "far"

    def test_search_k_clamped_to_size(self) -> None:
        idx = _index()
        idx.add_vector("a", _rand(seed=1))
        idx.add_vector("b", _rand(seed=2))
        hits = idx.search(_rand(), k=100)
        assert len(hits) == 2

    def test_search_k_minimum_1(self) -> None:
        idx = _index()
        idx.add_vector("a", _rand())
        hits = idx.search(_rand(), k=0)
        assert len(hits) == 1

    def test_search_hit_score_bounded(self) -> None:
        idx = _index()
        idx.add_vector("a", _rand())
        hits = idx.search(_rand(seed=99), k=1)
        assert 0.0 < hits[0].score <= 1.0

    def test_search_hit_has_distance(self) -> None:
        idx = _index()
        idx.add_vector("a", _rand())
        hits = idx.search(_rand(seed=99), k=1)
        assert hits[0].distance >= 0.0

    def test_exact_match_highest_score(self) -> None:
        idx = _index()
        vec = _rand()
        idx.add_vector("exact", vec)
        idx.add_vector("other", _rand(seed=42))
        hits = idx.search(vec, k=2)
        assert hits[0].contract_id == "exact"
        # Distance should be ~0 for exact match
        assert hits[0].distance < 0.01


class TestEmbeddingIndexUpdate:
    """update_vector (upsert)."""

    def test_update_existing(self) -> None:
        idx = _index()
        idx.add_vector("a", _rand(seed=1))
        new_vec = _rand(seed=99)
        idx.update_vector("a", new_vec)
        assert idx.size == 1
        # Search with new_vec should find 'a' as exact match
        hits = idx.search(new_vec, k=1)
        assert hits[0].contract_id == "a"

    def test_update_new_inserts(self) -> None:
        idx = _index()
        idx.update_vector("new_id", _rand())
        assert idx.contains("new_id")
        assert idx.size == 1

    def test_update_empty_id_raises(self) -> None:
        idx = _index()
        with pytest.raises(ValueError, match="non-empty"):
            idx.update_vector("", _rand())


class TestEmbeddingIndexRebuild:
    """Full rebuild."""

    def test_rebuild_replaces_all(self) -> None:
        idx = _index()
        idx.add_vector("old", _rand(seed=1))
        idx.rebuild(
            {
                "new1": _rand(seed=10),
                "new2": _rand(seed=20),
            }
        )
        assert not idx.contains("old")
        assert idx.contains("new1")
        assert idx.contains("new2")
        assert idx.size == 2

    def test_rebuild_empty(self) -> None:
        idx = _index()
        idx.add_vector("a", _rand())
        idx.rebuild({})
        assert idx.size == 0

    def test_rebuild_dimension_mismatch_raises(self) -> None:
        idx = _index(dim=8)
        with pytest.raises(DimensionMismatchError):
            idx.rebuild({"bad": np.zeros(16, dtype=np.float32)})


class TestEmbeddingIndexConfig:
    """Config and properties."""

    def test_default_config(self) -> None:
        idx = EmbeddingIndex()
        assert idx.dimension == DEFAULT_DIMENSION
        assert idx.config.ivf_threshold == IVF_THRESHOLD

    def test_custom_config(self) -> None:
        cfg = EmbeddingIndexConfig(dimension=64, ivf_threshold=5)
        idx = EmbeddingIndex(cfg)
        assert idx.dimension == 64
        assert idx.config.ivf_threshold == 5

    def test_is_ivf_below_threshold(self) -> None:
        cfg = EmbeddingIndexConfig(dimension=DIM, ivf_threshold=100)
        idx = EmbeddingIndex(cfg)
        for i in range(10):
            idx.add_vector(f"v{i}", _rand(seed=i))
        assert not idx.is_ivf

    def test_is_ivf_above_threshold(self) -> None:
        cfg = EmbeddingIndexConfig(dimension=DIM, ivf_threshold=5)
        idx = EmbeddingIndex(cfg)
        for i in range(10):
            idx.add_vector(f"v{i}", _rand(seed=i))
        assert idx.is_ivf

    def test_config_frozen(self) -> None:
        cfg = EmbeddingIndexConfig()
        with pytest.raises(AttributeError):
            cfg.dimension = 999  # type: ignore[misc]

    def test_repr(self) -> None:
        idx = _index()
        r = repr(idx)
        assert "EmbeddingIndex" in r
        assert "FlatL2" in r


class TestEmbeddingIndexIVF:
    """IVF strategy for large indexes."""

    def test_ivf_search_works(self) -> None:
        cfg = EmbeddingIndexConfig(dimension=DIM, ivf_threshold=5, ivf_nlist=4, ivf_nprobe=2)
        idx = EmbeddingIndex(cfg)
        vecs = {f"v{i}": _rand(seed=i) for i in range(20)}
        idx.rebuild(vecs)
        assert idx.is_ivf
        hits = idx.search(_rand(seed=0), k=3)
        assert len(hits) > 0
        # The exact match (seed=0 -> v0) should appear
        ids = [h.contract_id for h in hits]
        assert "v0" in ids

    def test_ivf_add_triggers_rebuild(self) -> None:
        cfg = EmbeddingIndexConfig(dimension=DIM, ivf_threshold=3, ivf_nlist=2, ivf_nprobe=1)
        idx = EmbeddingIndex(cfg)
        for i in range(5):
            idx.add_vector(f"v{i}", _rand(seed=i))
        assert idx.is_ivf


class TestSearchHitType:
    """SearchHit frozen dataclass."""

    def test_defaults(self) -> None:
        h = SearchHit()
        assert h.contract_id == ""
        assert h.score == 0.0
        assert h.distance == 0.0

    def test_to_dict(self) -> None:
        h = SearchHit(contract_id="x", score=0.9, distance=0.1)
        d = h.to_dict()
        assert d["contract_id"] == "x"
        assert d["score"] == 0.9

    def test_frozen(self) -> None:
        h = SearchHit(contract_id="x")
        with pytest.raises(AttributeError):
            h.contract_id = "y"  # type: ignore[misc]


class TestEmbeddingIndexExceptions:
    """Exception hierarchy."""

    def test_duplicate_is_embedding_error(self) -> None:
        assert issubclass(DuplicateVectorError, EmbeddingIndexError)

    def test_not_found_is_embedding_error(self) -> None:
        assert issubclass(VectorNotFoundError, EmbeddingIndexError)

    def test_dimension_mismatch_is_embedding_error(self) -> None:
        assert issubclass(DimensionMismatchError, EmbeddingIndexError)


# ===================================================================
# 4.1.2 -- HardFilter
# ===================================================================


class TestHardFilterSafetyBand:
    """Rule 1: safety_band_min <= user_band."""

    def test_green_user_green_cap_passes(self) -> None:
        hf = HardFilter()
        results = hf.filter([_candidate(band="GREEN")], user_band="GREEN")
        assert results[0].passed

    def test_green_user_amber_cap_rejected(self) -> None:
        hf = HardFilter()
        results = hf.filter([_candidate(band="AMBER")], user_band="GREEN")
        assert not results[0].passed
        assert results[0].rejection_reason == REASON_SAFETY_BAND

    def test_crisis_user_red_cap_passes(self) -> None:
        hf = HardFilter()
        results = hf.filter([_candidate(band="RED")], user_band="CRISIS")
        assert results[0].passed

    def test_amber_user_amber_cap_passes(self) -> None:
        hf = HardFilter()
        results = hf.filter([_candidate(band="AMBER")], user_band="AMBER")
        assert results[0].passed

    def test_red_user_crisis_cap_rejected(self) -> None:
        hf = HardFilter()
        results = hf.filter([_candidate(band="CRISIS")], user_band="RED")
        assert not results[0].passed

    def test_unknown_band_treated_as_green(self) -> None:
        hf = HardFilter()
        results = hf.filter([_candidate(band="UNKNOWN_BAND")], user_band="GREEN")
        # Unknown maps to 0 (GREEN level), so GREEN(0) >= 0 => passes
        assert results[0].passed

    def test_safety_disabled(self) -> None:
        hf = HardFilter(HardFilterConfig(check_safety=False))
        results = hf.filter([_candidate(band="CRISIS")], user_band="GREEN")
        assert results[0].passed


class TestHardFilterAvailability:
    """Rule 2: not OFFLINE."""

    def test_online_passes(self) -> None:
        hf = HardFilter()
        results = hf.filter([_candidate(avail="ONLINE")])
        assert results[0].passed

    def test_degraded_passes(self) -> None:
        hf = HardFilter()
        results = hf.filter([_candidate(avail="DEGRADED")])
        assert results[0].passed

    def test_offline_rejected(self) -> None:
        hf = HardFilter()
        results = hf.filter([_candidate(avail="OFFLINE")])
        assert not results[0].passed
        assert results[0].rejection_reason == REASON_OFFLINE

    def test_availability_disabled(self) -> None:
        hf = HardFilter(HardFilterConfig(check_availability=False))
        results = hf.filter([_candidate(avail="OFFLINE")])
        assert results[0].passed


class TestHardFilterInputSatisfiability:
    """Rule 3: input satisfiability."""

    def test_no_required_inputs_passes(self) -> None:
        hf = HardFilter()
        results = hf.filter([_candidate(required=frozenset())])
        assert results[0].passed

    def test_all_inputs_in_params(self) -> None:
        hf = HardFilter(HardFilterConfig(planner_can_ask=False))
        results = hf.filter(
            [_candidate(required=frozenset({"a", "b"}))],
            available_param_names=frozenset({"a", "b", "c"}),
        )
        assert results[0].passed

    def test_all_inputs_in_session(self) -> None:
        hf = HardFilter(HardFilterConfig(planner_can_ask=False))
        results = hf.filter(
            [_candidate(required=frozenset({"x"}))],
            session_keys=frozenset({"x", "y"}),
        )
        assert results[0].passed

    def test_mixed_params_and_session(self) -> None:
        hf = HardFilter(HardFilterConfig(planner_can_ask=False))
        results = hf.filter(
            [_candidate(required=frozenset({"a", "b"}))],
            available_param_names=frozenset({"a"}),
            session_keys=frozenset({"b"}),
        )
        assert results[0].passed

    def test_none_satisfiable_rejected(self) -> None:
        hf = HardFilter(HardFilterConfig(planner_can_ask=False))
        results = hf.filter(
            [_candidate(required=frozenset({"a", "b"}))],
        )
        assert not results[0].passed
        assert results[0].rejection_reason == REASON_INPUT_UNSATISFIABLE

    def test_below_threshold_rejected(self) -> None:
        # threshold=0.5, 1/4 = 0.25 < 0.5 => rejected
        hf = HardFilter(
            HardFilterConfig(
                planner_can_ask=False,
                satisfiability_threshold=0.5,
            )
        )
        results = hf.filter(
            [_candidate(required=frozenset({"a", "b", "c", "d"}))],
            available_param_names=frozenset({"a"}),
        )
        assert not results[0].passed

    def test_at_threshold_passes(self) -> None:
        # threshold=0.5, 2/4 = 0.5 >= 0.5 => passes
        hf = HardFilter(
            HardFilterConfig(
                planner_can_ask=False,
                satisfiability_threshold=0.5,
            )
        )
        results = hf.filter(
            [_candidate(required=frozenset({"a", "b", "c", "d"}))],
            available_param_names=frozenset({"a", "b"}),
        )
        assert results[0].passed

    def test_planner_can_ask_relaxes(self) -> None:
        # With planner_can_ask=True, all inputs are considered satisfiable
        hf = HardFilter(HardFilterConfig(planner_can_ask=True))
        results = hf.filter(
            [_candidate(required=frozenset({"unknown_input"}))],
        )
        assert results[0].passed

    def test_inputs_disabled(self) -> None:
        hf = HardFilter(HardFilterConfig(check_inputs=False, planner_can_ask=False))
        results = hf.filter(
            [_candidate(required=frozenset({"a", "b", "c"}))],
        )
        assert results[0].passed


class TestHardFilterMultipleCandidates:
    """Filtering multiple candidates at once."""

    def test_mixed_pass_fail(self) -> None:
        hf = HardFilter()
        candidates = [
            _candidate(name="pass1", band="GREEN", avail="ONLINE"),
            _candidate(name="fail_band", band="RED", avail="ONLINE"),
            _candidate(name="fail_avail", band="GREEN", avail="OFFLINE"),
            _candidate(name="pass2", band="AMBER", avail="DEGRADED"),
        ]
        results = hf.filter(candidates, user_band="AMBER")
        assert results[0].passed  # pass1: GREEN <= AMBER
        assert not results[1].passed  # fail_band: RED > AMBER
        assert not results[2].passed  # fail_avail: OFFLINE
        assert results[3].passed  # pass2: AMBER <= AMBER, DEGRADED not OFFLINE

    def test_empty_candidates(self) -> None:
        hf = HardFilter()
        results = hf.filter([])
        assert results == []

    def test_order_preserved(self) -> None:
        hf = HardFilter()
        candidates = [_candidate(name=f"c{i}") for i in range(5)]
        results = hf.filter(candidates)
        assert [r.contract_name for r in results] == [f"c{i}" for i in range(5)]


class TestHardFilterPassed:
    """filter_passed convenience method."""

    def test_returns_only_passed(self) -> None:
        hf = HardFilter()
        candidates = [
            _candidate(name="good", avail="ONLINE"),
            _candidate(name="bad", avail="OFFLINE"),
        ]
        passed = hf.filter_passed(candidates)
        assert len(passed) == 1
        assert passed[0].contract_name == "good"

    def test_empty_when_all_fail(self) -> None:
        hf = HardFilter()
        candidates = [_candidate(avail="OFFLINE")]
        passed = hf.filter_passed(candidates)
        assert passed == []


class TestHardFilterShortCircuit:
    """Rules short-circuit: safety checked before availability checked before inputs."""

    def test_safety_fails_before_availability_check(self) -> None:
        hf = HardFilter()
        # This candidate would also fail availability, but safety fails first
        results = hf.filter(
            [_candidate(band="CRISIS", avail="OFFLINE")],
            user_band="GREEN",
        )
        assert results[0].rejection_reason == REASON_SAFETY_BAND

    def test_availability_fails_before_input_check(self) -> None:
        hf = HardFilter(HardFilterConfig(planner_can_ask=False))
        results = hf.filter(
            [_candidate(avail="OFFLINE", required=frozenset({"missing"}))],
        )
        assert results[0].rejection_reason == REASON_OFFLINE


class TestHardFilterConfig:
    """HardFilterConfig."""

    def test_defaults(self) -> None:
        cfg = HardFilterConfig()
        assert cfg.satisfiability_threshold == DEFAULT_SATISFIABILITY_THRESHOLD
        assert cfg.planner_can_ask is True
        assert cfg.check_safety is True
        assert cfg.check_availability is True
        assert cfg.check_inputs is True

    def test_frozen(self) -> None:
        cfg = HardFilterConfig()
        with pytest.raises(AttributeError):
            cfg.check_safety = False  # type: ignore[misc]

    def test_repr(self) -> None:
        hf = HardFilter()
        r = repr(hf)
        assert "HardFilter" in r
        assert "safety=True" in r


class TestFilterCandidateType:
    """FilterCandidate frozen dataclass."""

    def test_defaults(self) -> None:
        c = FilterCandidate()
        assert c.contract_name == ""
        assert c.safety_band_min == "GREEN"
        assert c.availability == "ONLINE"
        assert c.required_input_names == frozenset()

    def test_to_dict(self) -> None:
        c = _candidate(name="test", required=frozenset({"a", "b"}))
        d = c.to_dict()
        assert d["contract_name"] == "test"
        assert set(d["required_input_names"]) == {"a", "b"}

    def test_frozen(self) -> None:
        c = FilterCandidate()
        with pytest.raises(AttributeError):
            c.contract_name = "x"  # type: ignore[misc]

    def test_contract_carried_through(self) -> None:
        sentinel = object()
        c = _candidate(contract=sentinel)
        hf = HardFilter()
        results = hf.filter([c])
        assert results[0].contract is sentinel


class TestFilterResultType:
    """FilterResult frozen dataclass."""

    def test_to_dict_passed(self) -> None:
        r = FilterResult(contract_name="x", passed=True)
        d = r.to_dict()
        assert d["passed"] is True
        assert "rejection_reason" not in d

    def test_to_dict_rejected(self) -> None:
        r = FilterResult(contract_name="x", passed=False, rejection_reason=REASON_OFFLINE)
        d = r.to_dict()
        assert d["rejection_reason"] == REASON_OFFLINE

    def test_frozen(self) -> None:
        r = FilterResult()
        with pytest.raises(AttributeError):
            r.passed = True  # type: ignore[misc]


# ===================================================================
# Module exports
# ===================================================================


class TestModuleExports:
    """Verify __init__.py exports."""

    def test_all_exports_importable(self) -> None:
        import k1.fabric.retrieval as mod
        from k1.fabric.retrieval import __all__

        for name in __all__:
            assert hasattr(mod, name), f"Missing export: {name}"

    def test_all_list_count(self) -> None:
        from k1.fabric.retrieval import __all__

        assert len(__all__) == 39

    def test_embedding_constants(self) -> None:
        from k1.fabric.retrieval import DEFAULT_DIMENSION, IVF_NLIST, IVF_NPROBE, IVF_THRESHOLD

        assert DEFAULT_DIMENSION == 384
        assert IVF_THRESHOLD == 10_000
        assert isinstance(IVF_NLIST, int)
        assert isinstance(IVF_NPROBE, int)

    def test_filter_reason_constants(self) -> None:
        from k1.fabric.retrieval import (
            REASON_INPUT_UNSATISFIABLE,
            REASON_OFFLINE,
            REASON_SAFETY_BAND,
        )

        assert REASON_SAFETY_BAND == "safety_band"
        assert REASON_OFFLINE == "offline"
        assert REASON_INPUT_UNSATISFIABLE == "input_unsatisfiable"

    def test_default_threshold_value(self) -> None:
        from k1.fabric.retrieval import DEFAULT_SATISFIABILITY_THRESHOLD

        assert DEFAULT_SATISFIABILITY_THRESHOLD == 0.5
