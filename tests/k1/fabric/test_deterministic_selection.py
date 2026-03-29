"""
Epic 6.3.10 -- Test deterministic provider selection (FAB-10).

Covers:
  - ProviderSelector deterministic ordering: highest score wins.
  - Tie-breaking: lower avg_latency_ms wins, then alphabetical provider_id.
  - 100 selections with same inputs produce identical results.
  - Through fabric.execute(): same capability = same provider every time.
  - select_top_n() returns ranked list in deterministic order.
  - Edge cases: single candidate, all rejected, no candidates.
  - Resolver pipeline: resolve() selects deterministically per FAB-10.

NO MOCKS -- all tests use real ProviderSelector, real Resolver, and
FabricFactory.create_for_testing() with real adapters.

References:
  - fabric-implementation-plan.md Epic 6.3.10
  - fabric_discussion.md Section 9 (Resolution Pipeline step 4)
  - FAB-10 (Deterministic selection given same inputs + registry state)
"""

from __future__ import annotations

from pathlib import Path

import pytest

from k1.fabric.factory import FabricFactory
from k1.fabric.provider_resolution.provider_selector import (
    AllProvidersRejectedError,
    NoCandidatesError,
    ProviderSelector,
    ScoredCandidate,
)
from k1.fabric.types import (
    CapabilityContract,
    CapabilityRequest,
    InputSpec,
    PolicyResult,
    ProviderConfig,
    Tier,
)
from tests.k1.fabric.helpers import (
    assert_capability_result_success,
    register_contract_with_provider,
)

# ---------------------------------------------------------------------------
# Fixtures directory (for YAML contracts)
# ---------------------------------------------------------------------------

FIXTURES_DIR = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_candidate(
    provider_id: str,
    score: float,
    avg_latency_ms: int = 0,
    *,
    allowed: bool = True,
) -> ScoredCandidate:
    """Create a ScoredCandidate with given score and latency."""
    return ScoredCandidate(
        provider_config=ProviderConfig(
            provider_id=provider_id,
            provider_type="MCP",
            endpoint=f"local://{provider_id}",
        ),
        contract=CapabilityContract(
            name="tool.execute.selector_test",
            version="1.0.0",
            domain=["TEST"],
            description="Selector test capability",
            capabilities=["tool.execute.selector_test"],
            provider_type="MCP",
            provider_id=provider_id,
            required_inputs=[InputSpec(name="query", type="STRING", description="Test input")],
            output={"type": "object"},
            avg_latency_ms=avg_latency_ms,
        ),
        policy_result=PolicyResult(
            allowed=allowed,
            score=score,
            reasons=[] if allowed else ["access_denied"],
        ),
    )


def _three_candidates() -> list[ScoredCandidate]:
    """Three candidates with different scores for deterministic tests."""
    return [
        _make_candidate("mcp-alpha", score=0.7, avg_latency_ms=50),
        _make_candidate("mcp-beta", score=0.9, avg_latency_ms=100),
        _make_candidate("mcp-gamma", score=0.5, avg_latency_ms=30),
    ]


def _request(
    capability_name: str,
    params: dict | None = None,
) -> CapabilityRequest:
    """Build a LOW tier request for deterministic tests."""
    return CapabilityRequest(
        capability_name=capability_name,
        params=params or {"query": "test"},
        tier=Tier.LOW.value,
        caller="test-deterministic",
    )


# =========================================================================
# 6.3.10a -- ProviderSelector deterministic ordering
# =========================================================================


class TestProviderSelectorDeterminism:
    """
    Verify ProviderSelector.select() is deterministic per FAB-10.
    Sort key: (-score, +avg_latency_ms, +provider_id).
    """

    def test_highest_score_wins(self) -> None:
        """Provider with highest policy score is selected."""
        selector = ProviderSelector()
        candidates = _three_candidates()

        result = selector.select(candidates, capability_name="test")

        # mcp-beta has score 0.9 (highest)
        assert result.provider_config.provider_id == "mcp-beta"
        assert result.policy_result.score == 0.9

    def test_score_ordering_with_many_candidates(self) -> None:
        """select_top_n returns all candidates in score-descending order."""
        selector = ProviderSelector()
        candidates = _three_candidates()

        ranked = selector.select_top_n(candidates, n=3, capability_name="test")

        # Order: beta (0.9) > alpha (0.7) > gamma (0.5)
        assert ranked[0].provider_config.provider_id == "mcp-beta"
        assert ranked[1].provider_config.provider_id == "mcp-alpha"
        assert ranked[2].provider_config.provider_id == "mcp-gamma"

    def test_100_selections_identical(self) -> None:
        """100 calls with same inputs produce identical results."""
        selector = ProviderSelector()
        candidates = _three_candidates()

        first = selector.select(candidates, capability_name="test")
        for _ in range(99):
            result = selector.select(candidates, capability_name="test")
            assert result.provider_config.provider_id == first.provider_config.provider_id
            assert result.policy_result.score == first.policy_result.score

    def test_shuffled_input_same_result(self) -> None:
        """Candidate order in input list does not affect selection."""
        selector = ProviderSelector()

        # Forward order
        c1 = [
            _make_candidate("mcp-a", score=0.6),
            _make_candidate("mcp-b", score=0.8),
            _make_candidate("mcp-c", score=0.4),
        ]
        # Reversed order
        c2 = list(reversed(c1))

        r1 = selector.select(c1, capability_name="test")
        r2 = selector.select(c2, capability_name="test")

        assert r1.provider_config.provider_id == r2.provider_config.provider_id

    def test_select_top_n_deterministic(self) -> None:
        """select_top_n(n=2) always returns same top 2 in same order."""
        selector = ProviderSelector()
        candidates = _three_candidates()

        for _ in range(50):
            top2 = selector.select_top_n(candidates, n=2, capability_name="test")
            assert len(top2) == 2
            assert top2[0].provider_config.provider_id == "mcp-beta"
            assert top2[1].provider_config.provider_id == "mcp-alpha"


# =========================================================================
# 6.3.10b -- Tie-breaking rules
# =========================================================================


class TestTieBreaking:
    """
    Verify tie-breaking order per FAB-10:
      1. Higher score first
      2. Lower avg_latency_ms (from contract)
      3. Alphabetical provider_id (final deterministic tiebreaker)
    """

    def test_same_score_lower_latency_wins(self) -> None:
        """When scores are equal, lower latency wins."""
        selector = ProviderSelector()
        candidates = [
            _make_candidate("mcp-slow", score=0.8, avg_latency_ms=200),
            _make_candidate("mcp-fast", score=0.8, avg_latency_ms=50),
        ]

        result = selector.select(candidates, capability_name="test")
        assert result.provider_config.provider_id == "mcp-fast"

    def test_same_score_same_latency_alphabetical_wins(self) -> None:
        """When score AND latency are equal, alphabetical provider_id wins."""
        selector = ProviderSelector()
        candidates = [
            _make_candidate("mcp-zebra", score=0.8, avg_latency_ms=100),
            _make_candidate("mcp-alpha", score=0.8, avg_latency_ms=100),
        ]

        result = selector.select(candidates, capability_name="test")
        assert result.provider_config.provider_id == "mcp-alpha"

    def test_score_dominates_latency(self) -> None:
        """Higher score wins even with higher latency."""
        selector = ProviderSelector()
        candidates = [
            _make_candidate("mcp-slow-good", score=0.9, avg_latency_ms=500),
            _make_candidate("mcp-fast-weak", score=0.5, avg_latency_ms=10),
        ]

        result = selector.select(candidates, capability_name="test")
        assert result.provider_config.provider_id == "mcp-slow-good"

    def test_latency_dominates_alphabetical(self) -> None:
        """Lower latency wins over alphabetical provider_id."""
        selector = ProviderSelector()
        candidates = [
            _make_candidate("mcp-alpha", score=0.8, avg_latency_ms=200),
            _make_candidate("mcp-zulu", score=0.8, avg_latency_ms=50),
        ]

        result = selector.select(candidates, capability_name="test")
        # zulu wins because lower latency, despite alphabetical disadvantage
        assert result.provider_config.provider_id == "mcp-zulu"

    def test_three_way_tie_broken_alphabetically(self) -> None:
        """Three candidates with same score + latency: alphabetical wins."""
        selector = ProviderSelector()
        candidates = [
            _make_candidate("mcp-charlie", score=0.8, avg_latency_ms=100),
            _make_candidate("mcp-alpha", score=0.8, avg_latency_ms=100),
            _make_candidate("mcp-bravo", score=0.8, avg_latency_ms=100),
        ]

        result = selector.select(candidates, capability_name="test")
        assert result.provider_config.provider_id == "mcp-alpha"

        # Full ranking is alphabetical
        ranked = selector.select_top_n(candidates, n=3, capability_name="test")
        assert [r.provider_config.provider_id for r in ranked] == [
            "mcp-alpha",
            "mcp-bravo",
            "mcp-charlie",
        ]


# =========================================================================
# 6.3.10c -- Fabric.execute() deterministic (end-to-end)
# =========================================================================


class TestFabricExecuteDeterminism:
    """
    Through fabric.execute(): same capability + same registry state
    = same provider selected every time.
    """

    async def test_100_executions_same_provider(self) -> None:
        """Execute same capability 100 times: always same provider_id."""
        fabric = FabricFactory.create_for_testing(
            capture_events=True,
            contracts_dir=str(FIXTURES_DIR),
        )

        provider_ids = set()
        for _ in range(100):
            result = await fabric.execute(
                _request("tool.execute.restaurant_booking"),
            )
            assert_capability_result_success(result)
            provider_ids.add(result.provider_id)

        # Always same provider
        assert len(provider_ids) == 1
        assert "mcp-opentable" in provider_ids

    async def test_different_params_same_provider(self) -> None:
        """Different params do NOT change provider selection."""
        fabric = FabricFactory.create_for_testing(
            capture_events=True,
            contracts_dir=str(FIXTURES_DIR),
        )

        r1 = await fabric.execute(
            _request(
                "tool.execute.restaurant_booking",
                {"restaurant_name": "Alpha"},
            ),
        )
        r2 = await fabric.execute(
            _request(
                "tool.execute.restaurant_booking",
                {"restaurant_name": "Beta"},
            ),
        )
        r3 = await fabric.execute(
            _request(
                "tool.execute.restaurant_booking",
                {"restaurant_name": "Gamma", "date": "2026-12-25"},
            ),
        )

        assert r1.provider_id == r2.provider_id == r3.provider_id

    async def test_programmatic_contract_deterministic(self) -> None:
        """Programmatically registered capability is resolved deterministically."""
        fabric = FabricFactory.create_for_testing(
            capture_events=True,
            contracts_dir=str(FIXTURES_DIR),
        )

        contract = CapabilityContract(
            name="tool.execute.det_prog_test",
            version="1.0.0",
            domain=["TEST"],
            description="Determinism test capability",
            capabilities=["tool.execute.det_prog_test"],
            provider_type="MCP",
            provider_id="mcp-det-prog",
            required_inputs=[InputSpec(name="query", type="STRING", description="Test input")],
            output={"type": "object"},
        )
        register_contract_with_provider(fabric, contract)

        provider_ids = set()
        for _ in range(50):
            result = await fabric.execute(_request("tool.execute.det_prog_test"))
            assert_capability_result_success(result, expected_provider="mcp-det-prog")
            provider_ids.add(result.provider_id)

        assert len(provider_ids) == 1

    async def test_multiple_capabilities_each_deterministic(self) -> None:
        """Multiple different capabilities each resolve deterministically."""
        fabric = FabricFactory.create_for_testing(
            capture_events=True,
            contracts_dir=str(FIXTURES_DIR),
        )

        caps = [
            "tool.execute.restaurant_booking",
            "tool.read.weather_api",
        ]

        for cap in caps:
            providers = set()
            for _ in range(20):
                result = await fabric.execute(_request(cap))
                assert_capability_result_success(result)
                providers.add(result.provider_id)
            # Each capability always resolves to same provider
            assert len(providers) == 1


# =========================================================================
# 6.3.10d -- Edge cases
# =========================================================================


class TestSelectionEdgeCases:
    """
    Edge cases for ProviderSelector: single candidate, all rejected,
    no candidates, filtered candidates.
    """

    def test_single_candidate_selected(self) -> None:
        """Single candidate is always selected."""
        selector = ProviderSelector()
        candidates = [_make_candidate("mcp-only", score=0.5)]

        result = selector.select(candidates, capability_name="test")
        assert result.provider_config.provider_id == "mcp-only"

    def test_all_rejected_raises_error(self) -> None:
        """All candidates with allowed=False raises AllProvidersRejectedError."""
        selector = ProviderSelector()
        candidates = [
            _make_candidate("mcp-a", score=0.9, allowed=False),
            _make_candidate("mcp-b", score=0.8, allowed=False),
        ]

        with pytest.raises(AllProvidersRejectedError) as exc_info:
            selector.select(candidates, capability_name="test_cap")

        assert "test_cap" in str(exc_info.value)

    def test_no_candidates_raises_error(self) -> None:
        """Empty candidates list raises NoCandidatesError."""
        selector = ProviderSelector()

        with pytest.raises(NoCandidatesError):
            selector.select([], capability_name="test")

    def test_rejected_candidates_filtered_before_selection(self) -> None:
        """Only allowed candidates participate in selection."""
        selector = ProviderSelector()
        candidates = [
            _make_candidate("mcp-rejected", score=0.99, allowed=False),
            _make_candidate("mcp-allowed", score=0.5, allowed=True),
        ]

        result = selector.select(candidates, capability_name="test")
        # mcp-rejected has higher score but is filtered out
        assert result.provider_config.provider_id == "mcp-allowed"

    def test_mixed_allowed_rejected_selects_best_allowed(self) -> None:
        """Among allowed candidates, best score wins."""
        selector = ProviderSelector()
        candidates = [
            _make_candidate("mcp-rejected-best", score=0.99, allowed=False),
            _make_candidate("mcp-allowed-low", score=0.3, allowed=True),
            _make_candidate("mcp-allowed-high", score=0.7, allowed=True),
        ]

        result = selector.select(candidates, capability_name="test")
        assert result.provider_config.provider_id == "mcp-allowed-high"


# =========================================================================
# 6.3.10e -- Resolved provider metadata
# =========================================================================


class TestResolvedProviderMetadata:
    """
    Verify ResolvedProvider carries correct metadata from selection.
    """

    def test_resolved_carries_provider_config(self) -> None:
        """ResolvedProvider has the winning provider's config."""
        selector = ProviderSelector()
        candidates = _three_candidates()

        result = selector.select(candidates, capability_name="test")
        assert result.provider_config.provider_type == "MCP"
        assert result.provider_config.provider_id == "mcp-beta"

    def test_resolved_carries_contract(self) -> None:
        """ResolvedProvider has the contract from the winning candidate."""
        selector = ProviderSelector()
        candidates = _three_candidates()

        result = selector.select(candidates, capability_name="test")
        assert result.contract is not None
        assert result.contract.name == "tool.execute.selector_test"

    def test_resolved_carries_policy_result(self) -> None:
        """ResolvedProvider has the policy result from the winning candidate."""
        selector = ProviderSelector()
        candidates = _three_candidates()

        result = selector.select(candidates, capability_name="test")
        assert result.policy_result.allowed is True
        assert result.policy_result.score == 0.9

    def test_select_top_n_returns_n_results(self) -> None:
        """select_top_n(n) returns exactly n results when enough candidates."""
        selector = ProviderSelector()
        candidates = _three_candidates()

        for n in [1, 2, 3]:
            results = selector.select_top_n(candidates, n=n, capability_name="test")
            assert len(results) == n

    def test_select_top_n_returns_fewer_when_insufficient(self) -> None:
        """select_top_n(n) returns fewer than n when not enough candidates."""
        selector = ProviderSelector()
        candidates = [_make_candidate("mcp-only", score=0.8)]

        results = selector.select_top_n(candidates, n=5, capability_name="test")
        assert len(results) == 1
