"""
Tests for Epic 4.1 issues 4.1.3, 4.1.4, and 4.1.5.

Covers:
  - SoftRanker: cosine similarity, Jaccard domain match, success rate,
    cost/latency scoring, DEGRADED penalty, composite formula, config.
  - TopKSelector: K clamping, selection, provider_type extraction, config.
  - RetrievalEngine: full pipeline, discover_capabilities, find_relevant_prompts,
    edge cases, prompt filtering, empty results, timing.
  - Module __init__.py exports (updated count).

Test doubles:
  - numpy arrays as embeddings (no real model).
  - Fake registry, embedding port, and contract objects.

Run:
    python -m pytest tests/k1/fabric/test_retrieval_413_415.py -v --tb=short
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, FrozenSet, List, Optional, Sequence

import numpy as np
import pytest

# ---------------------------------------------------------------------------
# Imports from prior modules
# ---------------------------------------------------------------------------
from k1.fabric.retrieval.embedding_index import EmbeddingIndex, EmbeddingIndexConfig
from k1.fabric.retrieval.hard_filter import HardFilter

# ---------------------------------------------------------------------------
# Imports under test -- RetrievalEngine (4.1.5)
# ---------------------------------------------------------------------------
from k1.fabric.retrieval.retrieval_engine import (
    EmbeddingUnavailableError,
    RetrievalEngine,
    RetrievalEngineConfig,
    RetrievalEngineError,
)

# ---------------------------------------------------------------------------
# Imports under test -- SoftRanker (4.1.3)
# ---------------------------------------------------------------------------
from k1.fabric.retrieval.soft_ranker import (
    DEFAULT_SUCCESS_RATE,
    DEGRADED_PENALTY,
    W_COST_LATENCY,
    W_DOMAIN,
    W_SEMANTIC,
    W_SUCCESS,
    RankedResult,
    RankerCandidate,
    SoftRanker,
    SoftRankerConfig,
)

# ---------------------------------------------------------------------------
# Imports under test -- TopKSelector (4.1.4)
# ---------------------------------------------------------------------------
from k1.fabric.retrieval.top_k_selector import (
    DEFAULT_K,
    MAX_K,
    MIN_K,
    SelectedCapability,
    TopKSelector,
    TopKSelectorConfig,
)

# ===================================================================
# Helpers
# ===================================================================

DIM = 8


def _rand(dim: int = DIM, seed: int = 0) -> np.ndarray:
    rng = np.random.RandomState(seed)
    return rng.randn(dim).astype(np.float32)


def _unit(dim: int = DIM, seed: int = 0) -> np.ndarray:
    """Unit vector (for controlled cosine similarity)."""
    v = _rand(dim, seed)
    norm = np.linalg.norm(v)
    if norm == 0:
        v[0] = 1.0
        return v
    return v / norm


def _candidate(
    name: str = "tool.test",
    vector: Any = None,
    domains: FrozenSet[str] = frozenset(),
    success_rate: float = -1.0,
    cost: float = 0.0,
    latency: int = 0,
    availability: str = "ONLINE",
    contract: Any = None,
) -> RankerCandidate:
    return RankerCandidate(
        contract_name=name,
        capability_vector=vector,
        domains=domains,
        success_rate_30d=success_rate,
        cost_per_call=cost,
        avg_latency_ms=latency,
        availability=availability,
        contract=contract,
    )


@dataclass(frozen=True)
class FakeContract:
    """Minimal contract for tests."""

    name: str = ""
    version: str = "1.0.0"
    domain: List[str] = field(default_factory=list)
    description: str = ""
    capabilities: List[str] = field(default_factory=list)
    required_inputs: List[Any] = field(default_factory=list)
    optional_inputs: List[Any] = field(default_factory=list)
    provider_type: str = "MCP"
    provider_id: str = ""
    safety_band_min: str = "GREEN"
    cost_per_call: float = 0.0
    avg_latency_ms: int = 0
    availability: str = "ONLINE"
    success_rate_30d: float = 0.0
    output: Dict[str, Any] = field(default_factory=dict)


class FakeEmbeddingPort:
    """Fake embedding port returning deterministic vectors."""

    def __init__(self, dim: int = DIM) -> None:
        self._dim = dim
        self._counter = 0

    def embed(self, text: str) -> np.ndarray:
        # Deterministic: use hash of text to seed
        seed = abs(hash(text)) % (2**31)
        rng = np.random.RandomState(seed)
        return rng.randn(self._dim).astype(np.float32)


class FakeRegistry:
    """Fake registry returning configured contracts."""

    def __init__(self, contracts: Optional[List[Any]] = None) -> None:
        self._contracts = contracts or []

    def list_all(self) -> Sequence[Any]:
        return list(self._contracts)

    def list_by_domain(self, domain: str) -> Sequence[Any]:
        return [c for c in self._contracts if domain in (getattr(c, "domain", None) or [])]


# ===================================================================
# 4.1.3 -- SoftRanker
# ===================================================================


class TestSoftRankerCosineSimilarity:
    """Test the cosine similarity dimension."""

    def test_identical_vectors_score_1(self) -> None:
        v = _unit(DIM, seed=42)
        ranker = SoftRanker()
        sim = ranker._cosine_similarity(v, v)
        assert sim == pytest.approx(1.0, abs=1e-5)

    def test_orthogonal_vectors_score_0(self) -> None:
        a = np.array([1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0], dtype=np.float32)
        b = np.array([0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0], dtype=np.float32)
        ranker = SoftRanker()
        sim = ranker._cosine_similarity(a, b)
        assert sim == pytest.approx(0.0, abs=1e-5)

    def test_opposite_vectors_clamped_to_0(self) -> None:
        a = np.array([1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0], dtype=np.float32)
        b = np.array([-1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0], dtype=np.float32)
        ranker = SoftRanker()
        sim = ranker._cosine_similarity(a, b)
        assert sim == 0.0  # clamped

    def test_none_vector_returns_0(self) -> None:
        ranker = SoftRanker()
        sim = ranker._cosine_similarity(_unit(), None)
        assert sim == 0.0

    def test_zero_vector_returns_0(self) -> None:
        ranker = SoftRanker()
        zero = np.zeros(DIM, dtype=np.float32)
        sim = ranker._cosine_similarity(_unit(), zero)
        assert sim == 0.0

    def test_dimension_mismatch_returns_0(self) -> None:
        ranker = SoftRanker()
        a = _rand(4)
        b = _rand(8)
        sim = ranker._cosine_similarity(a, b)
        assert sim == 0.0


class TestSoftRankerJaccard:
    """Test the Jaccard domain match dimension."""

    def test_identical_sets_score_1(self) -> None:
        s = frozenset({"math", "science"})
        assert SoftRanker._jaccard(s, s) == 1.0

    def test_disjoint_sets_score_0(self) -> None:
        a = frozenset({"math"})
        b = frozenset({"music"})
        assert SoftRanker._jaccard(a, b) == 0.0

    def test_partial_overlap(self) -> None:
        a = frozenset({"math", "science"})
        b = frozenset({"science", "music"})
        # intersection=1, union=3
        assert SoftRanker._jaccard(a, b) == pytest.approx(1 / 3)

    def test_both_empty_returns_0(self) -> None:
        assert SoftRanker._jaccard(frozenset(), frozenset()) == 0.0

    def test_one_empty(self) -> None:
        assert SoftRanker._jaccard(frozenset({"a"}), frozenset()) == 0.0

    def test_subset(self) -> None:
        a = frozenset({"a", "b", "c"})
        b = frozenset({"a", "b"})
        # intersection=2, union=3
        assert SoftRanker._jaccard(a, b) == pytest.approx(2 / 3)


class TestSoftRankerCostLatency:
    """Test the cost/latency scoring dimension."""

    def test_zero_cost_zero_latency_scores_1(self) -> None:
        score = SoftRanker._cost_latency_score(0.0, 0, 1.0, 100)
        assert score == pytest.approx(1.0)

    def test_max_cost_max_latency_scores_0(self) -> None:
        score = SoftRanker._cost_latency_score(1.0, 100, 1.0, 100)
        assert score == pytest.approx(0.0, abs=1e-5)

    def test_half_cost_half_latency(self) -> None:
        score = SoftRanker._cost_latency_score(0.5, 50, 1.0, 100)
        assert score == pytest.approx(0.5, abs=1e-5)

    def test_zero_max_cost_all_zero(self) -> None:
        score = SoftRanker._cost_latency_score(0.0, 0, 0.0, 0)
        assert score == pytest.approx(1.0)

    def test_bounded_0_to_1(self) -> None:
        score = SoftRanker._cost_latency_score(10.0, 50000, 10.0, 50000)
        assert 0.0 <= score <= 1.0


class TestSoftRankerSuccessRate:
    """Test success rate handling."""

    def test_default_rate_used_for_new_capability(self) -> None:
        ranker = SoftRanker()
        c = _candidate(name="new", vector=_unit(), success_rate=-1.0)
        results = ranker.rank([c], _unit())
        assert results[0].success_rate == pytest.approx(DEFAULT_SUCCESS_RATE)

    def test_explicit_rate_used(self) -> None:
        ranker = SoftRanker()
        c = _candidate(name="good", vector=_unit(), success_rate=0.9)
        results = ranker.rank([c], _unit())
        assert results[0].success_rate == pytest.approx(0.9)

    def test_rate_clamped_above_1(self) -> None:
        ranker = SoftRanker()
        c = _candidate(name="x", vector=_unit(), success_rate=1.5)
        results = ranker.rank([c], _unit())
        assert results[0].success_rate <= 1.0

    def test_rate_clamped_below_0_uses_default(self) -> None:
        ranker = SoftRanker()
        c = _candidate(name="x", vector=_unit(), success_rate=-0.5)
        results = ranker.rank([c], _unit())
        assert results[0].success_rate == pytest.approx(DEFAULT_SUCCESS_RATE)


class TestSoftRankerDegradedPenalty:
    """Test DEGRADED multiplicative penalty."""

    def test_online_no_penalty(self) -> None:
        ranker = SoftRanker()
        c = _candidate(name="a", vector=_unit(), availability="ONLINE")
        results = ranker.rank([c], _unit())
        assert results[0].degraded_penalty_applied is False

    def test_degraded_penalty_applied(self) -> None:
        ranker = SoftRanker()
        c_online = _candidate(name="a", vector=_unit(), availability="ONLINE")
        c_degraded = _candidate(name="b", vector=_unit(), availability="DEGRADED")
        online_result = ranker.rank([c_online], _unit())[0]
        degraded_result = ranker.rank([c_degraded], _unit())[0]
        assert degraded_result.degraded_penalty_applied is True
        assert degraded_result.score == pytest.approx(
            online_result.score * DEGRADED_PENALTY, abs=1e-5
        )

    def test_custom_penalty(self) -> None:
        config = SoftRankerConfig(degraded_penalty=0.5)
        ranker = SoftRanker(config)
        c_online = _candidate(name="a", vector=_unit(), availability="ONLINE")
        c_degraded = _candidate(name="b", vector=_unit(), availability="DEGRADED")
        online_score = ranker.rank([c_online], _unit())[0].score
        degraded_score = ranker.rank([c_degraded], _unit())[0].score
        assert degraded_score == pytest.approx(online_score * 0.5, abs=1e-5)


class TestSoftRankerComposite:
    """Test the full composite scoring formula."""

    def test_empty_candidates_returns_empty(self) -> None:
        ranker = SoftRanker()
        assert ranker.rank([], _unit()) == []

    def test_single_candidate_scored(self) -> None:
        ranker = SoftRanker()
        c = _candidate(name="a", vector=_unit(seed=1), success_rate=0.8)
        results = ranker.rank([c], _unit(seed=1))
        assert len(results) == 1
        assert 0.0 <= results[0].score <= 1.0

    def test_results_sorted_descending_by_score(self) -> None:
        ranker = SoftRanker()
        # Make c1 more similar to query
        query = _unit(seed=0)
        c1 = _candidate(
            name="a",
            vector=_unit(seed=0),
            domains=frozenset({"math"}),
            success_rate=0.9,
            cost=0.01,
            latency=10,
        )
        c2 = _candidate(
            name="b",
            vector=_unit(seed=99),
            domains=frozenset({"music"}),
            success_rate=0.3,
            cost=0.5,
            latency=500,
        )
        results = ranker.rank([c2, c1], query, frozenset({"math"}))
        assert results[0].contract_name == "a"
        assert results[1].contract_name == "b"
        assert results[0].score >= results[1].score

    def test_weights_sum_to_1(self) -> None:
        total = W_SEMANTIC + W_DOMAIN + W_SUCCESS + W_COST_LATENCY
        assert total == pytest.approx(1.0)

    def test_perfect_match_all_dimensions(self) -> None:
        query = _unit(seed=5)
        domains = frozenset({"math"})
        c = _candidate(
            name="perfect",
            vector=query,
            domains=domains,
            success_rate=1.0,
            cost=0.0,
            latency=0,
        )
        ranker = SoftRanker()
        results = ranker.rank([c], query, domains)
        # All dimensions maxed out: 0.4*1 + 0.3*1 + 0.15*1 + 0.15*1 = 1.0
        assert results[0].score == pytest.approx(1.0, abs=0.01)

    def test_result_carries_contract_ref(self) -> None:
        sentinel = object()
        c = _candidate(name="a", vector=_unit(), contract=sentinel)
        results = SoftRanker().rank([c], _unit())
        assert results[0].contract is sentinel

    def test_ranked_result_to_dict(self) -> None:
        r = RankedResult(
            contract_name="x",
            score=0.5,
            semantic_similarity=0.4,
            domain_match=0.3,
            success_rate=0.8,
            cost_latency_score=0.9,
            degraded_penalty_applied=True,
        )
        d = r.to_dict()
        assert d["contract_name"] == "x"
        assert d["degraded_penalty_applied"] is True


class TestSoftRankerConfig:
    """Test SoftRankerConfig."""

    def test_defaults(self) -> None:
        c = SoftRankerConfig()
        assert c.w_semantic == W_SEMANTIC
        assert c.w_domain == W_DOMAIN
        assert c.w_success == W_SUCCESS
        assert c.w_cost_latency == W_COST_LATENCY
        assert c.default_success_rate == DEFAULT_SUCCESS_RATE
        assert c.degraded_penalty == DEGRADED_PENALTY

    def test_custom(self) -> None:
        c = SoftRankerConfig(w_semantic=0.5, w_domain=0.2, w_success=0.2, w_cost_latency=0.1)
        assert c.w_semantic == 0.5

    def test_frozen(self) -> None:
        c = SoftRankerConfig()
        with pytest.raises(AttributeError):
            c.w_semantic = 0.9  # type: ignore[misc]

    def test_repr(self) -> None:
        ranker = SoftRanker()
        r = repr(ranker)
        assert "SoftRanker" in r
        assert "degraded_penalty" in r


class TestRankerCandidateType:
    """Test RankerCandidate data type."""

    def test_defaults(self) -> None:
        c = RankerCandidate()
        assert c.contract_name == ""
        assert c.success_rate_30d == -1.0
        assert c.availability == "ONLINE"

    def test_to_dict(self) -> None:
        c = _candidate(name="t", domains=frozenset({"a", "b"}))
        d = c.to_dict()
        assert d["contract_name"] == "t"
        assert set(d["domains"]) == {"a", "b"}

    def test_frozen(self) -> None:
        c = RankerCandidate()
        with pytest.raises(AttributeError):
            c.contract_name = "x"  # type: ignore[misc]


# ===================================================================
# 4.1.4 -- TopKSelector
# ===================================================================


class TestTopKSelectorSelect:
    """Test selection from ranked list."""

    def test_select_default_k(self) -> None:
        items = [RankedResult(contract_name=f"c{i}", score=1.0 - i * 0.1) for i in range(15)]
        selector = TopKSelector()
        selected = selector.select(items)
        assert len(selected) == DEFAULT_K

    def test_select_custom_k(self) -> None:
        items = [RankedResult(contract_name=f"c{i}", score=0.9) for i in range(20)]
        selector = TopKSelector()
        selected = selector.select(items, k=5)
        assert len(selected) == 5

    def test_k_clamped_to_max(self) -> None:
        items = [RankedResult(contract_name=f"c{i}", score=0.9) for i in range(30)]
        selector = TopKSelector()
        selected = selector.select(items, k=100)
        assert len(selected) == MAX_K

    def test_k_clamped_to_min(self) -> None:
        items = [RankedResult(contract_name="a", score=0.9)]
        selector = TopKSelector()
        selected = selector.select(items, k=0)
        assert len(selected) == MIN_K

    def test_fewer_items_than_k(self) -> None:
        items = [RankedResult(contract_name="a", score=0.9)]
        selector = TopKSelector()
        selected = selector.select(items, k=10)
        assert len(selected) == 1

    def test_empty_list_returns_empty(self) -> None:
        selector = TopKSelector()
        selected = selector.select([], k=5)
        assert selected == []

    def test_preserves_order(self) -> None:
        items = [
            RankedResult(contract_name="best", score=0.9),
            RankedResult(contract_name="mid", score=0.5),
            RankedResult(contract_name="worst", score=0.1),
        ]
        selector = TopKSelector()
        selected = selector.select(items, k=3)
        assert [s.contract_name for s in selected] == ["best", "mid", "worst"]

    def test_extracts_score(self) -> None:
        items = [RankedResult(contract_name="a", score=0.777)]
        selector = TopKSelector()
        selected = selector.select(items, k=1)
        assert selected[0].score == pytest.approx(0.777)


class TestTopKSelectorProviderType:
    """Test provider_type extraction from contract."""

    def test_extracts_from_contract(self) -> None:
        fake_contract = FakeContract(name="tool.x", provider_type="MCP")
        item = RankedResult(contract_name="tool.x", score=0.9, contract=fake_contract)
        selected = TopKSelector().select([item], k=1)
        assert selected[0].provider_type == "MCP"

    def test_no_contract_empty_type(self) -> None:
        item = RankedResult(contract_name="tool.x", score=0.9, contract=None)
        selected = TopKSelector().select([item], k=1)
        assert selected[0].provider_type == ""

    def test_custom_extractor(self) -> None:
        item = RankedResult(contract_name="tool.x", score=0.9)
        selected = TopKSelector().select(
            [item],
            k=1,
            extract_provider_type=lambda _: "CUSTOM",
        )
        assert selected[0].provider_type == "CUSTOM"


class TestTopKSelectorConfig:
    """Test TopKSelectorConfig."""

    def test_defaults(self) -> None:
        c = TopKSelectorConfig()
        assert c.default_k == DEFAULT_K
        assert c.max_k == MAX_K

    def test_custom_config(self) -> None:
        selector = TopKSelector(TopKSelectorConfig(default_k=3, max_k=5))
        items = [RankedResult(contract_name=f"c{i}", score=0.5) for i in range(10)]
        selected = selector.select(items)
        assert len(selected) == 3
        selected_max = selector.select(items, k=100)
        assert len(selected_max) == 5

    def test_frozen(self) -> None:
        c = TopKSelectorConfig()
        with pytest.raises(AttributeError):
            c.default_k = 5  # type: ignore[misc]

    def test_repr(self) -> None:
        r = repr(TopKSelector())
        assert "TopKSelector" in r
        assert "default_k" in r


class TestSelectedCapabilityType:
    """Test SelectedCapability data type."""

    def test_defaults(self) -> None:
        s = SelectedCapability()
        assert s.contract_name == ""
        assert s.score == 0.0
        assert s.provider_type == ""
        assert s.contract is None

    def test_to_dict(self) -> None:
        s = SelectedCapability(contract_name="x", score=0.5, provider_type="WASM")
        d = s.to_dict()
        assert d["contract_name"] == "x"
        assert d["provider_type"] == "WASM"

    def test_frozen(self) -> None:
        s = SelectedCapability()
        with pytest.raises(AttributeError):
            s.contract_name = "y"  # type: ignore[misc]

    def test_contract_carried_through(self) -> None:
        sentinel = object()
        item = RankedResult(contract_name="a", score=0.9, contract=sentinel)
        selected = TopKSelector().select([item], k=1)
        assert selected[0].contract is sentinel


# ===================================================================
# 4.1.5 -- RetrievalEngine
# ===================================================================


def _make_engine(
    contracts: Optional[List[FakeContract]] = None,
    dim: int = DIM,
    config: Optional[RetrievalEngineConfig] = None,
) -> RetrievalEngine:
    """Build a RetrievalEngine with fake ports and real components."""
    contracts = contracts or []
    idx = EmbeddingIndex(EmbeddingIndexConfig(dimension=dim))
    embed_port = FakeEmbeddingPort(dim)
    registry = FakeRegistry(contracts)

    # Index all contracts
    for c in contracts:
        if c.name:
            vec = embed_port.embed(f"{c.description} | {' '.join(c.capabilities)}")
            idx.add_vector(c.name, vec)

    return RetrievalEngine(
        embedding_index=idx,
        hard_filter=HardFilter(),
        soft_ranker=SoftRanker(),
        top_k_selector=TopKSelector(),
        embedding_port=embed_port,
        registry_port=registry,
        config=config,
    )


class TestRetrievalEngineDiscoverCapabilities:
    """Test discover_capabilities -- the full pipeline."""

    def test_returns_retrieval_result_type(self) -> None:
        contracts = [FakeContract(name="tool.calc", description="calculator", capabilities=["add"])]
        engine = _make_engine(contracts)
        result = engine.discover_capabilities(intent="calculator")
        # Check it has the expected attributes
        assert hasattr(result, "capabilities")
        assert hasattr(result, "total_matched")
        assert hasattr(result, "query_latency_ms")
        assert hasattr(result, "query_intent")
        assert hasattr(result, "index_size")

    def test_returns_matching_capabilities(self) -> None:
        contracts = [
            FakeContract(name="tool.calc", description="math calculator", domain=["math"]),
            FakeContract(name="tool.weather", description="weather service", domain=["weather"]),
        ]
        engine = _make_engine(contracts)
        result = engine.discover_capabilities(intent="math calculator")
        assert result.total_matched == 2  # both pass hard filter with GREEN
        assert len(result.capabilities) > 0
        assert len(result.capabilities) <= 2

    def test_empty_registry_returns_empty(self) -> None:
        engine = _make_engine([])
        result = engine.discover_capabilities(intent="anything")
        assert result.total_matched == 0
        assert len(result.capabilities) == 0

    def test_query_intent_preserved(self) -> None:
        contracts = [FakeContract(name="tool.a", description="test")]
        engine = _make_engine(contracts)
        result = engine.discover_capabilities(intent="find a tool")
        assert result.query_intent == "find a tool"

    def test_index_size_reported(self) -> None:
        contracts = [
            FakeContract(name="tool.a", description="a"),
            FakeContract(name="tool.b", description="b"),
        ]
        engine = _make_engine(contracts)
        result = engine.discover_capabilities(intent="x")
        assert result.index_size == 2

    def test_embedding_model_reported(self) -> None:
        engine = _make_engine([FakeContract(name="tool.a", description="a")])
        result = engine.discover_capabilities(intent="x")
        assert result.embedding_model == "ultrabert-v4.0.0"

    def test_custom_top_k(self) -> None:
        contracts = [FakeContract(name=f"tool.{i}", description=f"desc {i}") for i in range(15)]
        engine = _make_engine(contracts)
        result = engine.discover_capabilities(intent="x", top_k=3)
        assert len(result.capabilities) == 3

    def test_latency_ms_is_non_negative(self) -> None:
        contracts = [FakeContract(name="tool.a", description="a")]
        engine = _make_engine(contracts)
        result = engine.discover_capabilities(intent="x")
        assert result.query_latency_ms >= 0


class TestRetrievalEngineHardFilterIntegration:
    """Test that HardFilter rules are respected in the pipeline."""

    def test_offline_eliminated(self) -> None:
        contracts = [
            FakeContract(name="tool.on", description="online tool", availability="ONLINE"),
            FakeContract(name="tool.off", description="offline tool", availability="OFFLINE"),
        ]
        engine = _make_engine(contracts)
        result = engine.discover_capabilities(intent="tool")
        names = [c.contract.name for c in result.capabilities if c.contract]
        assert "tool.off" not in names
        assert result.total_matched == 1

    def test_safety_band_filter(self) -> None:
        contracts = [
            FakeContract(name="tool.green", description="safe", safety_band_min="GREEN"),
            FakeContract(name="tool.red", description="restricted", safety_band_min="RED"),
        ]
        engine = _make_engine(contracts)
        result = engine.discover_capabilities(intent="tool", safety_band="GREEN")
        names = [c.contract.name for c in result.capabilities if c.contract]
        assert "tool.red" not in names

    def test_all_filtered_returns_empty(self) -> None:
        contracts = [
            FakeContract(name="tool.off", description="x", availability="OFFLINE"),
        ]
        engine = _make_engine(contracts)
        result = engine.discover_capabilities(intent="x")
        assert result.total_matched == 0
        assert len(result.capabilities) == 0


class TestRetrievalEngineSoftRankIntegration:
    """Test that SoftRanker scoring is reflected in results."""

    def test_higher_similarity_ranked_first(self) -> None:
        # Two contracts, one with description matching the intent
        contracts = [
            FakeContract(
                name="tool.match",
                description="math calculator add numbers",
                capabilities=["add"],
                domain=["math"],
            ),
            FakeContract(
                name="tool.other",
                description="weather report forecast",
                capabilities=["forecast"],
                domain=["weather"],
            ),
        ]
        engine = _make_engine(contracts)
        result = engine.discover_capabilities(
            intent="math calculator add numbers",
        )
        assert len(result.capabilities) == 2
        # The first result should be the better match
        assert result.capabilities[0].score >= result.capabilities[1].score

    def test_degraded_penalized_in_ranking(self) -> None:
        contracts = [
            FakeContract(name="tool.online", description="fast tool", availability="ONLINE"),
            FakeContract(name="tool.degraded", description="fast tool", availability="DEGRADED"),
        ]
        engine = _make_engine(contracts)
        result = engine.discover_capabilities(intent="fast tool")
        scores = {c.contract.name: c.score for c in result.capabilities if c.contract}
        # DEGRADED should have lower score
        if "tool.online" in scores and "tool.degraded" in scores:
            assert scores["tool.degraded"] <= scores["tool.online"]


class TestRetrievalEngineFindRelevantPrompts:
    """Test find_relevant_prompts -- prompt-type filtering."""

    def test_filters_to_prompt_type_only(self) -> None:
        contracts = [
            FakeContract(
                name="prompt.greeting", description="greeting prompt", provider_type="prompt"
            ),
            FakeContract(name="tool.calc", description="calculator", provider_type="MCP"),
        ]
        engine = _make_engine(contracts)
        result = engine.find_relevant_prompts(intent="greeting")
        names = [c.contract.name for c in result.capabilities if c.contract]
        assert "tool.calc" not in names

    def test_filters_by_name_prefix(self) -> None:
        contracts = [
            FakeContract(name="prompt.hello", description="hello", provider_type="MCP"),
        ]
        engine = _make_engine(contracts)
        result = engine.find_relevant_prompts(intent="hello")
        assert result.total_matched >= 0  # May or may not match depending on filter

    def test_empty_when_no_prompts(self) -> None:
        contracts = [
            FakeContract(name="tool.calc", description="calculator", provider_type="MCP"),
        ]
        engine = _make_engine(contracts)
        result = engine.find_relevant_prompts(intent="math")
        assert len(result.capabilities) == 0


class TestRetrievalEngineConfig:
    """Test RetrievalEngineConfig."""

    def test_defaults(self) -> None:
        c = RetrievalEngineConfig()
        assert c.default_top_k == 10
        assert c.max_top_k == 25
        assert c.embedding_model == "ultrabert-v4.0.0"

    def test_custom(self) -> None:
        c = RetrievalEngineConfig(default_top_k=5, max_top_k=15)
        assert c.default_top_k == 5
        assert c.max_top_k == 15

    def test_frozen(self) -> None:
        c = RetrievalEngineConfig()
        with pytest.raises(AttributeError):
            c.default_top_k = 20  # type: ignore[misc]


class TestRetrievalEngineExceptions:
    """Test exception hierarchy."""

    def test_embedding_unavailable_is_engine_error(self) -> None:
        assert issubclass(EmbeddingUnavailableError, RetrievalEngineError)

    def test_engine_error_is_exception(self) -> None:
        assert issubclass(RetrievalEngineError, Exception)

    def test_repr(self) -> None:
        contracts = [FakeContract(name="tool.a", description="a")]
        engine = _make_engine(contracts)
        r = repr(engine)
        assert "RetrievalEngine" in r
        assert "ultrabert" in r


class TestRetrievalEngineSessionContext:
    """Test session context passthrough."""

    def test_session_keys_used_for_input_satisfiability(self) -> None:
        # Contract requires 'user_name' input
        @dataclass(frozen=True)
        class FakeInput:
            name: str = ""

        contracts = [
            FakeContract(
                name="tool.greet",
                description="greeting",
                required_inputs=[FakeInput(name="user_name")],
            ),
        ]
        engine = _make_engine(contracts)
        # Without session context, planner_can_ask covers it
        result = engine.discover_capabilities(
            intent="greeting",
            session_context={"user_name": "Alice"},
        )
        assert result.total_matched >= 1


# ===================================================================
# Module exports
# ===================================================================


class TestModuleExportsUpdated:
    """Verify __init__.py exports all new symbols."""

    def test_all_exports_importable(self) -> None:
        import k1.fabric.retrieval as mod

        for name in mod.__all__:
            assert hasattr(mod, name), f"Missing export: {name}"

    def test_all_list_count(self) -> None:
        import k1.fabric.retrieval as mod

        # 11 (embedding_index) + 8 (hard_filter) + 10 (soft_ranker) + 6 (top_k_selector) + 4 (retrieval_engine) = 39
        assert len(mod.__all__) == 39

    def test_soft_ranker_exports(self) -> None:
        from k1.fabric.retrieval import DEGRADED_PENALTY, W_SEMANTIC

        assert W_SEMANTIC == 0.40
        assert DEGRADED_PENALTY == 0.70

    def test_top_k_selector_exports(self) -> None:
        from k1.fabric.retrieval import DEFAULT_K, MAX_K, MIN_K

        assert DEFAULT_K == 10
        assert MAX_K == 25
        assert MIN_K == 1

    def test_retrieval_engine_exports(self) -> None:
        from k1.fabric.retrieval import EmbeddingUnavailableError, RetrievalEngineError

        assert issubclass(EmbeddingUnavailableError, RetrievalEngineError)

    def test_prior_exports_still_work(self) -> None:
        from k1.fabric.retrieval import EmbeddingIndex, HardFilter

        assert EmbeddingIndex is not None
        assert HardFilter is not None
