"""
Epic 6.2.7 -- Test RetrievalEngine (full 4-step pipeline).

Covers:
  - EmbeddingIndex: add/remove/search/rebuild, Flat L2, dimension mismatch.
  - HardFilter: safety band exclusion, OFFLINE exclusion, input
    satisfiability, planner-can-ask relaxation.
  - SoftRanker: 4-weight formula (0.4/0.3/0.15/0.15), DEGRADED penalty
    (0.7x), default success rate (0.5), domain Jaccard, cost/latency.
  - TopKSelector: default 10, max 25, clamp, empty input.
  - RetrievalEngine end-to-end: discover_capabilities, find_relevant_prompts,
    empty registry, prompt-type filtering.

NO MOCKS -- all tests use real components.

References:
  - fabric-implementation-plan.md Epic 6.2.7
  - fabric_discussion.md Section 8 (Retrieval Pipeline)
  - FAB-002 (UltraBERT embedding, cosine similarity)
"""

from __future__ import annotations

import numpy as np
import pytest

from k1.fabric.retrieval.embedding_index import (
    DimensionMismatchError,
    DuplicateVectorError,
    EmbeddingIndex,
    EmbeddingIndexConfig,
    VectorNotFoundError,
)
from k1.fabric.retrieval.hard_filter import (
    REASON_INPUT_UNSATISFIABLE,
    REASON_OFFLINE,
    REASON_SAFETY_BAND,
    FilterCandidate,
    HardFilter,
    HardFilterConfig,
)
from k1.fabric.retrieval.retrieval_engine import RetrievalEngine, RetrievalEngineConfig
from k1.fabric.retrieval.soft_ranker import RankedResult, RankerCandidate, SoftRanker
from k1.fabric.retrieval.top_k_selector import TopKSelector, TopKSelectorConfig
from k1.fabric.types import CapabilityContract, InputSpec

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

DIM = 8  # small embedding dimension for fast tests


def _vec(*vals: float) -> np.ndarray:
    """Create a float32 vector of DIM dimensions, padding with zeros."""
    arr = np.zeros(DIM, dtype=np.float32)
    for i, v in enumerate(vals[:DIM]):
        arr[i] = v
    return arr


def _random_vec(seed: int = 0) -> np.ndarray:
    rng = np.random.RandomState(seed)
    v = rng.randn(DIM).astype(np.float32)
    return v / (np.linalg.norm(v) + 1e-9)


def _make_contract(
    name: str = "tool.read.test",
    domain: list[str] | None = None,
    description: str | None = None,
    capabilities: list[str] | None = None,
    activity_profile: str | None = None,
    safety_band_min: str = "GREEN",
    availability: str = "ONLINE",
    provider_type: str = "MCP",
    required_inputs: list[str] | None = None,
    cost_per_call: float = 0.01,
    avg_latency_ms: int = 50,
    success_rate_30d: float = -1.0,
) -> CapabilityContract:
    inputs = [InputSpec(name=n) for n in (required_inputs or [])]
    return CapabilityContract(
        name=name,
        version="1.0.0",
        domain=domain or ["TEST"],
        description=description or f"Test contract {name}",
        capabilities=capabilities or [name],
        provider_type=provider_type,
        provider_id=f"pid-{name}",
        activity_profile=activity_profile,
        safety_band_min=safety_band_min,
        availability=availability,
        required_inputs=inputs,
        cost_per_call=cost_per_call,
        avg_latency_ms=avg_latency_ms,
        success_rate_30d=success_rate_30d,
    )


class StubEmbeddingPort:
    """Real in-memory embedding port returning deterministic vectors."""

    def __init__(self, dimension: int = DIM):
        self._dim = dimension

    def embed(self, text: str) -> np.ndarray:
        rng = np.random.RandomState(hash(text) % (2**31))
        v = rng.randn(self._dim).astype(np.float32)
        return v / (np.linalg.norm(v) + 1e-9)


class ConstantEmbeddingPort:
    """Embedding port that makes semantic similarity equal for every contract."""

    def __init__(self, dimension: int = DIM):
        self._vector = np.ones(dimension, dtype=np.float32)
        self._vector = self._vector / np.linalg.norm(self._vector)

    def embed(self, text: str) -> np.ndarray:  # noqa: ARG002
        return self._vector


class StubRegistryPort:
    """Real in-memory registry port listing contracts."""

    def __init__(self, contracts: list[CapabilityContract] | None = None):
        self._contracts = list(contracts or [])
        self.list_all_calls = 0
        self.list_by_domain_calls: list[str] = []

    def add(self, c: CapabilityContract) -> None:
        self._contracts.append(c)

    def list_all(self) -> list[CapabilityContract]:
        self.list_all_calls += 1
        return list(self._contracts)

    def list_by_domain(self, domain: str) -> list[CapabilityContract]:
        self.list_by_domain_calls.append(domain)
        return [c for c in self._contracts if domain in (getattr(c, "domain", None) or [])]


# ===========================================================================
# EmbeddingIndex
# ===========================================================================


class TestEmbeddingIndex:
    """Tests for EmbeddingIndex (4.1.1)."""

    def test_add_and_search(self):
        idx = EmbeddingIndex(EmbeddingIndexConfig(dimension=DIM))
        v1 = _vec(1.0, 0.0)
        idx.add_vector("cap-a", v1)
        assert idx.size == 1
        assert idx.contains("cap-a")
        hits = idx.search(v1, k=1)
        assert len(hits) == 1
        assert hits[0].contract_id == "cap-a"
        assert hits[0].score > 0.9  # near-identical vector

    def test_add_duplicate_raises(self):
        idx = EmbeddingIndex(EmbeddingIndexConfig(dimension=DIM))
        idx.add_vector("cap-a", _vec(1.0))
        with pytest.raises(DuplicateVectorError):
            idx.add_vector("cap-a", _vec(0.0, 1.0))

    def test_remove_vector(self):
        idx = EmbeddingIndex(EmbeddingIndexConfig(dimension=DIM))
        idx.add_vector("cap-a", _vec(1.0))
        idx.remove_vector("cap-a")
        assert idx.size == 0
        assert not idx.contains("cap-a")

    def test_remove_nonexistent_raises(self):
        idx = EmbeddingIndex(EmbeddingIndexConfig(dimension=DIM))
        with pytest.raises(VectorNotFoundError):
            idx.remove_vector("nope")

    def test_dimension_mismatch_raises(self):
        idx = EmbeddingIndex(EmbeddingIndexConfig(dimension=DIM))
        wrong = np.zeros(DIM + 5, dtype=np.float32)
        with pytest.raises(DimensionMismatchError):
            idx.add_vector("cap-a", wrong)

    def test_search_returns_nearest(self):
        idx = EmbeddingIndex(EmbeddingIndexConfig(dimension=DIM))
        v_a = _vec(1.0, 0.0)
        v_b = _vec(0.0, 1.0)
        v_c = _vec(0.5, 0.5)
        idx.add_vector("a", v_a)
        idx.add_vector("b", v_b)
        idx.add_vector("c", v_c)
        hits = idx.search(v_a, k=3)
        assert hits[0].contract_id == "a"  # closest to itself

    def test_search_empty_index(self):
        idx = EmbeddingIndex(EmbeddingIndexConfig(dimension=DIM))
        hits = idx.search(_vec(1.0), k=5)
        assert hits == []

    def test_rebuild(self):
        idx = EmbeddingIndex(EmbeddingIndexConfig(dimension=DIM))
        vectors = {"x": _vec(1.0), "y": _vec(0.0, 1.0)}
        idx.rebuild(vectors)
        assert idx.size == 2
        assert idx.contains("x") and idx.contains("y")

    def test_update_vector(self):
        idx = EmbeddingIndex(EmbeddingIndexConfig(dimension=DIM))
        idx.add_vector("a", _vec(1.0))
        idx.update_vector("a", _vec(0.0, 1.0))
        assert idx.size == 1
        hits = idx.search(_vec(0.0, 1.0), k=1)
        assert hits[0].contract_id == "a"

    def test_k_larger_than_size(self):
        idx = EmbeddingIndex(EmbeddingIndexConfig(dimension=DIM))
        idx.add_vector("a", _vec(1.0))
        hits = idx.search(_vec(1.0), k=100)
        assert len(hits) == 1


# ===========================================================================
# HardFilter
# ===========================================================================


class TestHardFilter:
    """Tests for HardFilter (4.1.2) -- three elimination rules."""

    def _candidate(
        self,
        name: str = "cap",
        band: str = "GREEN",
        avail: str = "ONLINE",
        inputs: frozenset[str] | None = None,
    ) -> FilterCandidate:
        return FilterCandidate(
            contract_name=name,
            safety_band_min=band,
            availability=avail,
            required_input_names=inputs or frozenset(),
        )

    # -- Rule 1: Safety band --

    def test_safety_green_user_green_passes(self):
        hf = HardFilter()
        results = hf.filter([self._candidate(band="GREEN")], user_band="GREEN")
        assert results[0].passed

    def test_safety_amber_user_green_rejected(self):
        hf = HardFilter()
        results = hf.filter([self._candidate(band="AMBER")], user_band="GREEN")
        assert not results[0].passed
        assert results[0].rejection_reason == REASON_SAFETY_BAND

    def test_safety_green_user_amber_passes(self):
        """User at AMBER can access GREEN contracts."""
        hf = HardFilter()
        results = hf.filter([self._candidate(band="GREEN")], user_band="AMBER")
        assert results[0].passed

    def test_safety_crisis_user_crisis_passes(self):
        hf = HardFilter()
        results = hf.filter([self._candidate(band="CRISIS")], user_band="CRISIS")
        assert results[0].passed

    # -- Rule 2: Availability --

    def test_offline_rejected(self):
        hf = HardFilter()
        results = hf.filter([self._candidate(avail="OFFLINE")])
        assert not results[0].passed
        assert results[0].rejection_reason == REASON_OFFLINE

    def test_degraded_passes(self):
        """DEGRADED is not eliminated by hard filter (SoftRanker penalizes)."""
        hf = HardFilter()
        results = hf.filter([self._candidate(avail="DEGRADED")])
        assert results[0].passed

    def test_online_passes(self):
        hf = HardFilter()
        results = hf.filter([self._candidate(avail="ONLINE")])
        assert results[0].passed

    # -- Rule 3: Input satisfiability --

    def test_inputs_satisfied_from_params(self):
        hf = HardFilter()
        c = self._candidate(inputs=frozenset(["query"]))
        results = hf.filter([c], available_param_names=frozenset(["query"]))
        assert results[0].passed

    def test_inputs_unsatisfied_rejected(self):
        hf = HardFilter(HardFilterConfig(planner_can_ask=False, satisfiability_threshold=1.0))
        c = self._candidate(inputs=frozenset(["query", "extra"]))
        results = hf.filter([c], available_param_names=frozenset(["query"]))
        assert not results[0].passed
        assert results[0].rejection_reason == REASON_INPUT_UNSATISFIABLE

    def test_inputs_planner_can_ask_relaxes(self):
        """With planner_can_ask=True, missing inputs are potentially satisfiable."""
        hf = HardFilter(HardFilterConfig(planner_can_ask=True))
        c = self._candidate(inputs=frozenset(["query", "missing"]))
        results = hf.filter([c], available_param_names=frozenset(["query"]))
        assert results[0].passed

    def test_no_required_inputs_passes(self):
        hf = HardFilter()
        c = self._candidate(inputs=frozenset())
        results = hf.filter([c])
        assert results[0].passed

    # -- filter_passed convenience --

    def test_filter_passed_returns_only_survivors(self):
        hf = HardFilter()
        candidates = [
            self._candidate(name="ok", avail="ONLINE"),
            self._candidate(name="gone", avail="OFFLINE"),
        ]
        survivors = hf.filter_passed(candidates)
        assert len(survivors) == 1
        assert survivors[0].contract_name == "ok"

    # -- Config disable rules --

    def test_disable_safety_check(self):
        hf = HardFilter(HardFilterConfig(check_safety=False))
        results = hf.filter([self._candidate(band="CRISIS")], user_band="GREEN")
        assert results[0].passed  # safety check disabled

    def test_disable_availability_check(self):
        hf = HardFilter(HardFilterConfig(check_availability=False))
        results = hf.filter([self._candidate(avail="OFFLINE")])
        assert results[0].passed  # availability check disabled


# ===========================================================================
# SoftRanker
# ===========================================================================


class TestSoftRanker:
    """Tests for SoftRanker (4.1.3) -- 4-dimension weighted formula."""

    def _candidate(
        self,
        name: str = "cap",
        vec: np.ndarray | None = None,
        domains: frozenset[str] | None = None,
        success_rate: float = -1.0,
        cost: float = 0.01,
        latency: int = 50,
        avail: str = "ONLINE",
    ) -> RankerCandidate:
        return RankerCandidate(
            contract_name=name,
            capability_vector=vec,
            domains=domains or frozenset(),
            success_rate_30d=success_rate,
            cost_per_call=cost,
            avg_latency_ms=latency,
            availability=avail,
        )

    def test_identical_vector_scores_high(self):
        ranker = SoftRanker()
        qvec = _random_vec(42)
        c = self._candidate(vec=qvec)
        results = ranker.rank([c], qvec)
        assert len(results) == 1
        assert results[0].semantic_similarity > 0.99

    def test_orthogonal_vectors_score_low(self):
        ranker = SoftRanker()
        qvec = _vec(1.0, 0.0)
        c = self._candidate(vec=_vec(0.0, 1.0))
        results = ranker.rank([c], qvec)
        assert results[0].semantic_similarity < 0.1

    def test_domain_match_increases_score(self):
        ranker = SoftRanker()
        qvec = _vec(1.0)
        c_match = self._candidate(name="match", vec=_vec(1.0), domains=frozenset(["FOOD"]))
        c_no = self._candidate(name="no", vec=_vec(1.0), domains=frozenset(["HEALTH"]))
        results = ranker.rank([c_match, c_no], qvec, frozenset(["FOOD"]))
        by_name = {r.contract_name: r for r in results}
        assert by_name["match"].domain_match > by_name["no"].domain_match

    def test_default_success_rate_used_for_new(self):
        ranker = SoftRanker()
        c = self._candidate(success_rate=-1.0)
        results = ranker.rank([c], _vec(1.0))
        assert results[0].success_rate == pytest.approx(0.5)

    def test_degraded_penalty_applied(self):
        ranker = SoftRanker()
        qvec = _vec(1.0)
        c_online = self._candidate(name="online", vec=qvec, avail="ONLINE")
        c_degraded = self._candidate(name="degraded", vec=qvec, avail="DEGRADED")
        results = ranker.rank([c_online, c_degraded], qvec)
        by_name = {r.contract_name: r for r in results}
        assert by_name["degraded"].degraded_penalty_applied is True
        assert by_name["online"].score > by_name["degraded"].score

    def test_degraded_penalty_factor(self):
        """DEGRADED score should be roughly 0.7x the ONLINE score."""
        ranker = SoftRanker()
        qvec = _vec(1.0)
        c_online = self._candidate(name="on", vec=qvec, avail="ONLINE")
        c_deg = self._candidate(name="deg", vec=qvec, avail="DEGRADED")
        results = ranker.rank([c_online, c_deg], qvec)
        by_name = {r.contract_name: r for r in results}
        ratio = by_name["deg"].score / by_name["on"].score
        assert ratio == pytest.approx(0.7, abs=0.02)

    def test_sorted_by_descending_score(self):
        ranker = SoftRanker()
        qvec = _vec(1.0)
        cands = [
            self._candidate(name="high", vec=qvec, success_rate=0.99, cost=0.001, latency=10),
            self._candidate(
                name="low", vec=_vec(0.0, 1.0), success_rate=0.1, cost=1.0, latency=5000
            ),
        ]
        results = ranker.rank(cands, qvec)
        assert results[0].contract_name == "high"

    def test_empty_candidates(self):
        ranker = SoftRanker()
        assert ranker.rank([], _vec(1.0)) == []

    def test_no_vector_semantic_zero(self):
        """Candidate with no capability_vector gets 0 semantic similarity."""
        ranker = SoftRanker()
        c = self._candidate(vec=None)
        results = ranker.rank([c], _vec(1.0))
        assert results[0].semantic_similarity == pytest.approx(0.0)

    def test_cost_latency_prefers_cheap_fast(self):
        ranker = SoftRanker()
        qvec = _vec(1.0)
        cheap = self._candidate(name="cheap", vec=qvec, cost=0.001, latency=10)
        expensive = self._candidate(name="expensive", vec=qvec, cost=1.0, latency=5000)
        results = ranker.rank([cheap, expensive], qvec)
        by_name = {r.contract_name: r for r in results}
        assert by_name["cheap"].cost_latency_score > by_name["expensive"].cost_latency_score


# ===========================================================================
# TopKSelector
# ===========================================================================


class TestTopKSelector:
    """Tests for TopKSelector (4.1.4)."""

    def _ranked(self, n: int) -> list[RankedResult]:
        return [RankedResult(contract_name=f"cap-{i}", score=1.0 - i * 0.01) for i in range(n)]

    def test_default_k_is_10(self):
        sel = TopKSelector()
        results = sel.select(self._ranked(20))
        assert len(results) == 10

    def test_custom_k(self):
        sel = TopKSelector()
        results = sel.select(self._ranked(20), k=5)
        assert len(results) == 5

    def test_max_k_clamped_to_25(self):
        sel = TopKSelector()
        results = sel.select(self._ranked(50), k=100)
        assert len(results) == 25

    def test_min_k_is_1(self):
        sel = TopKSelector()
        results = sel.select(self._ranked(10), k=0)
        assert len(results) == 1

    def test_fewer_than_k(self):
        sel = TopKSelector()
        results = sel.select(self._ranked(3), k=10)
        assert len(results) == 3

    def test_empty_input(self):
        sel = TopKSelector()
        results = sel.select([], k=5)
        assert results == []

    def test_preserves_order(self):
        sel = TopKSelector()
        ranked = self._ranked(5)
        results = sel.select(ranked, k=5)
        assert results[0].contract_name == "cap-0"
        assert results[-1].contract_name == "cap-4"

    def test_selected_capability_has_score(self):
        sel = TopKSelector()
        ranked = [RankedResult(contract_name="x", score=0.87)]
        results = sel.select(ranked, k=1)
        assert results[0].score == pytest.approx(0.87)

    def test_custom_config(self):
        sel = TopKSelector(TopKSelectorConfig(default_k=3, max_k=5))
        results = sel.select(self._ranked(10))
        assert len(results) == 3
        results2 = sel.select(self._ranked(10), k=20)
        assert len(results2) == 5  # clamped by max_k


# ===========================================================================
# RetrievalEngine (end-to-end)
# ===========================================================================


class TestRetrievalEngine:
    """Tests for RetrievalEngine (4.1.5) -- full 4-step pipeline."""

    def _build_engine(
        self,
        contracts: list[CapabilityContract] | None = None,
        default_top_k: int = 10,
        embedding_port=None,
    ) -> RetrievalEngine:
        """Wire real components into a RetrievalEngine."""
        embed_port = embedding_port or StubEmbeddingPort(dimension=DIM)
        index = EmbeddingIndex(EmbeddingIndexConfig(dimension=DIM))
        reg_port = StubRegistryPort(contracts or [])

        # Add each contract to the index with a deterministic embedding
        for c in contracts or []:
            vec = embed_port.embed(f"{c.description} | {' '.join(c.capabilities)}")
            index.add_vector(c.name, vec)

        return RetrievalEngine(
            embedding_index=index,
            hard_filter=HardFilter(),
            soft_ranker=SoftRanker(),
            top_k_selector=TopKSelector(),
            embedding_port=embed_port,
            registry_port=reg_port,
            config=RetrievalEngineConfig(
                default_top_k=default_top_k,
                max_top_k=25,
            ),
        )

    def test_discover_basic(self):
        contracts = [_make_contract(name=f"tool.read.c{i}") for i in range(5)]
        engine = self._build_engine(contracts)
        result = engine.discover_capabilities(intent="test query")
        assert result.total_matched > 0
        assert len(result.capabilities) <= 10
        assert result.query_intent == "test query"

    def test_discover_empty_registry(self):
        engine = self._build_engine([])
        result = engine.discover_capabilities(intent="anything")
        assert result.total_matched == 0
        assert result.capabilities == []

    def test_discover_respects_top_k(self):
        contracts = [_make_contract(name=f"tool.read.c{i}") for i in range(20)]
        engine = self._build_engine(contracts, default_top_k=10)
        result = engine.discover_capabilities(intent="query", top_k=3)
        assert len(result.capabilities) <= 3

    def test_discover_excludes_offline(self):
        contracts = [
            _make_contract(name="tool.read.online", availability="ONLINE"),
            _make_contract(name="tool.read.offline", availability="OFFLINE"),
        ]
        engine = self._build_engine(contracts)
        result = engine.discover_capabilities(intent="query")
        names = [sc.contract.name for sc in result.capabilities if sc.contract]
        assert "tool.read.offline" not in names

    def test_discover_excludes_safety_band(self):
        contracts = [
            _make_contract(name="tool.read.green", safety_band_min="GREEN"),
            _make_contract(name="tool.read.crisis", safety_band_min="CRISIS"),
        ]
        engine = self._build_engine(contracts)
        result = engine.discover_capabilities(intent="query", safety_band="GREEN")
        names = [sc.contract.name for sc in result.capabilities if sc.contract]
        assert "tool.read.crisis" not in names
        assert "tool.read.green" in names

    def test_find_relevant_prompts_filters_prompt_type(self):
        contracts = [
            _make_contract(name="prompt.template.greet", provider_type="prompt_default"),
            _make_contract(name="tool.read.weather", provider_type="MCP"),
        ]
        engine = self._build_engine(contracts)
        result = engine.find_relevant_prompts(intent="greeting")
        # Only prompt-type contracts should appear
        names = [sc.contract.name for sc in result.capabilities if sc.contract]
        assert "tool.read.weather" not in names

    def test_discover_capabilities_excludes_prompt_type_contracts(self):
        contracts = [
            _make_contract(name="prompt.template.greet", provider_type="prompt_default"),
            _make_contract(name="tool.read.weather", provider_type="MCP"),
        ]
        engine = self._build_engine(contracts)
        result = engine.discover_capabilities(intent="greeting")
        names = [sc.contract.name for sc in result.capabilities if sc.contract]
        assert "prompt.template.greet" not in names
        assert "tool.read.weather" in names

    def test_result_metadata(self):
        contracts = [_make_contract(name="tool.read.x")]
        engine = self._build_engine(contracts)
        result = engine.discover_capabilities(intent="query")
        assert result.index_size == 1
        assert result.embedding_model == "ultrabert-v4.0.0"
        assert result.query_latency_ms >= 0

    def test_discover_with_many_contracts(self):
        """Ensure engine handles bulk contracts without error."""
        contracts = [_make_contract(name=f"tool.read.bulk{i}") for i in range(50)]
        engine = self._build_engine(contracts, default_top_k=10)
        result = engine.discover_capabilities(intent="find something")
        assert result.total_matched > 0
        assert len(result.capabilities) <= 10

    def test_scored_capabilities_have_contracts(self):
        contracts = [_make_contract(name="tool.read.attached")]
        engine = self._build_engine(contracts)
        result = engine.discover_capabilities(intent="query")
        for sc in result.capabilities:
            assert sc.contract is not None

    def test_discover_with_session_context(self):
        contracts = [
            _make_contract(name="tool.read.needs_q", required_inputs=["query"]),
        ]
        engine = self._build_engine(contracts)
        result = engine.discover_capabilities(
            intent="query",
            session_context={"beliefs_active": {}, "_param_names": ["query"]},
        )
        # Should survive hard filter since param 'query' is available
        assert result.total_matched >= 1

    def test_contract_evidence_ranks_tasks_and_calendar_queries(self):
        contracts = [
            _make_contract(
                name="tool.read.family_tasks.list_tasks",
                domain=["tasks", "family"],
                description="List family tasks from the tasks adapter",
                capabilities=["read", "list", "adapter:tasks"],
                activity_profile="tasks.v1",
            ),
            _make_contract(
                name="tool.read.calendar.list_events",
                domain=["calendar", "family"],
                description="List calendar events from the calendar adapter",
                capabilities=["read", "list", "adapter:calendar"],
                activity_profile="calendar.v1",
            ),
            _make_contract(
                name="tool.read.date.current_date",
                domain=["date"],
                description="Read current date",
                capabilities=["read", "adapter:date"],
            ),
            _make_contract(
                name="tool.read.units.convert_units",
                domain=["units"],
                description="Convert units",
                capabilities=["read", "adapter:units"],
            ),
        ]
        engine = self._build_engine(contracts, embedding_port=ConstantEmbeddingPort())

        tasks_result = engine.discover_capabilities(intent="list tasks", top_k=4)
        calendar_result = engine.discover_capabilities(intent="list calendar events", top_k=4)

        assert tasks_result.capabilities[0].contract.name == "tool.read.family_tasks.list_tasks"
        assert calendar_result.capabilities[0].contract.name == "tool.read.calendar.list_events"
        assert tasks_result.capabilities[0].diagnostics["contract_evidence_score"] > 0

    def test_domain_hint_is_soft_when_exact_domain_misses_capability(self):
        contracts = [
            _make_contract(
                name="tool.read.family_tasks.list_tasks",
                domain=["tasks", "family"],
                description="List family tasks",
                capabilities=["read", "list", "adapter:tasks"],
            ),
            _make_contract(
                name="tool.read.calendar.list_events",
                domain=["calendar", "family"],
                description="List calendar events",
                capabilities=["read", "list", "adapter:calendar"],
            ),
        ]
        engine = self._build_engine(contracts, embedding_port=ConstantEmbeddingPort())

        result = engine.discover_capabilities(
            intent="list tasks",
            domain=["household"],
            top_k=2,
        )

        names = [sc.contract.name for sc in result.capabilities]
        assert "tool.read.family_tasks.list_tasks" in names
        assert result.capabilities[0].contract.name == "tool.read.family_tasks.list_tasks"
        assert result.capabilities[0].diagnostics["domain_hint_exact"] is False
        assert result.diagnostics["domain_fallback_used"] is True

    def test_exact_domain_hint_uses_domain_index_without_global_scan(self):
        contracts = [
            _make_contract(
                name="tool.read.family_tasks.list_tasks",
                domain=["tasks"],
                description="List family tasks",
                capabilities=["read", "list", "adapter:tasks"],
            ),
            _make_contract(
                name="tool.read.calendar.list_events",
                domain=["calendar"],
                description="List calendar events",
                capabilities=["read", "list", "adapter:calendar"],
            ),
        ]
        embed_port = ConstantEmbeddingPort()
        index = EmbeddingIndex(EmbeddingIndexConfig(dimension=DIM))
        for contract in contracts:
            index.add_vector(contract.name, embed_port.embed(contract.name))
        registry = StubRegistryPort(contracts)
        engine = RetrievalEngine(
            embedding_index=index,
            hard_filter=HardFilter(),
            soft_ranker=SoftRanker(),
            top_k_selector=TopKSelector(),
            embedding_port=embed_port,
            registry_port=registry,
        )

        result = engine.discover_capabilities(
            intent="list tasks",
            domain=["tasks"],
            top_k=2,
        )

        assert registry.list_by_domain_calls == ["tasks"]
        assert registry.list_all_calls == 0
        assert [cap.contract.name for cap in result.capabilities] == [
            "tool.read.family_tasks.list_tasks"
        ]
        assert result.diagnostics["domain_fallback_used"] is False

    def test_mixed_exact_and_broad_domain_hints_preserve_exact_evidence(self):
        contracts = [
            _make_contract(
                name="tool.read.family_tasks.list_tasks",
                domain=["tasks"],
                description="List family tasks",
                capabilities=["read", "list", "adapter:tasks"],
            ),
            _make_contract(
                name="tool.read.calendar.list_events",
                domain=["calendar"],
                description="List calendar events",
                capabilities=["read", "list", "adapter:calendar"],
            ),
        ]
        embed_port = ConstantEmbeddingPort()
        index = EmbeddingIndex(EmbeddingIndexConfig(dimension=DIM))
        for contract in contracts:
            index.add_vector(contract.name, embed_port.embed(contract.name))
        registry = StubRegistryPort(contracts)
        engine = RetrievalEngine(
            embedding_index=index,
            hard_filter=HardFilter(),
            soft_ranker=SoftRanker(),
            top_k_selector=TopKSelector(),
            embedding_port=embed_port,
            registry_port=registry,
        )

        result = engine.discover_capabilities(
            intent="list tasks",
            domain=["tasks", "household"],
            top_k=2,
        )

        assert registry.list_by_domain_calls == ["tasks"]
        assert registry.list_all_calls == 1
        assert result.capabilities[0].contract.name == "tool.read.family_tasks.list_tasks"
        assert result.capabilities[0].diagnostics["domain_hint_exact"] is True
        assert result.diagnostics["domain_fallback_used"] is True
