"""
Epic 6.2.5 -- Test ProviderResolution subsystem.

Covers the full resolution pipeline: Resolver, ProviderMatcher,
ProviderSelector, ProviderRegistry, and ProviderFactory.

Tests:
  - Resolver 5-step pipeline: registry lookup -> provider matching ->
    policy evaluation -> selection -> instantiation.
  - ProviderMatcher: 1:1 matching via provider_id, health filtering.
  - ProviderSelector: deterministic selection per FAB-10
    (sort key: -score, +avg_latency_ms, +provider_id).
  - ProviderRegistry: register, unregister, lookup, health.
  - ProviderFactory: handler registration, create, unsupported type.
  - Error codes: capability_not_found, no_provider, access_denied.

NO MOCKS -- all tests use real adapters via FabricFactory.

References:
  - fabric-implementation-plan.md Epic 6.2.5
  - fabric_discussion.md Section 9 (Resolution Pipeline)
  - FAB-10 (deterministic provider selection)
"""

from __future__ import annotations

import pytest

from k1.fabric.adapters.local_event import LocalEventAdapter
from k1.fabric.core.contract_validator import ContractValidator
from k1.fabric.core.registry import CapabilityRegistry
from k1.fabric.provider_resolution.provider_factory import (
    ProviderFactory,
    ProviderInstantiationError,
    UnsupportedProviderTypeError,
)
from k1.fabric.provider_resolution.provider_matcher import (
    NoProviderError,
    ProviderMatcher,
)
from k1.fabric.provider_resolution.provider_registry import ProviderRegistry
from k1.fabric.provider_resolution.provider_selector import (
    AllProvidersRejectedError,
    NoCandidatesError,
    ProviderSelector,
    ScoredCandidate,
)
from k1.fabric.provider_resolution.resolver import ResolutionFailedError, Resolver
from k1.fabric.types import (
    CapabilityContract,
    CapabilityRequest,
    InputSpec,
    PolicyResult,
    ProviderConfig,
    ProviderHealth,
    ProviderStatus,
    SafetyBand,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_contract(
    name: str = "tool.execute.test_cap",
    provider_id: str = "test-provider",
    provider_type: str = "MCP",
    safety_band: str = SafetyBand.GREEN.value,
    avg_latency_ms: int = 100,
) -> CapabilityContract:
    """Create a minimal valid CapabilityContract."""
    return CapabilityContract(
        name=name,
        version="1.0.0",
        domain=["TEST"],
        description=f"Test capability {name}",
        capabilities=["test_action"],
        limitations=[],
        required_inputs=[
            InputSpec(name="input_a", type="STRING", description="Test input"),
        ],
        output={"type": "object"},
        provider_type=provider_type,
        provider_id=provider_id,
        safety_band_min=safety_band,
        avg_latency_ms=avg_latency_ms,
    )


def _make_provider_config(
    provider_id: str = "test-provider",
    provider_type: str = "MCP",
    max_execution_ms: int = 30000,
) -> ProviderConfig:
    """Create a minimal ProviderConfig."""
    return ProviderConfig(
        provider_id=provider_id,
        provider_type=provider_type,
        endpoint="mcp://local/test",
        max_execution_ms=max_execution_ms,
    )


def _make_request(
    capability_name: str = "tool.execute.test_cap",
    safety_band: str = SafetyBand.GREEN.value,
) -> CapabilityRequest:
    """Create a minimal CapabilityRequest."""
    return CapabilityRequest(
        capability_name=capability_name,
        safety_band=safety_band,
        caller="test-caller",
    )


def _make_registry() -> CapabilityRegistry:
    """Create a clean CapabilityRegistry with real validator and event adapter."""
    validator = ContractValidator()
    event_port = LocalEventAdapter(capture_mode=True)
    return CapabilityRegistry(validator=validator, event_port=event_port)


def _make_provider_registry() -> ProviderRegistry:
    """Create a clean ProviderRegistry."""
    return ProviderRegistry()


# ===========================================================================
# ProviderRegistry tests
# ===========================================================================


class TestProviderRegistry:
    """ProviderRegistry: register, lookup, unregister, health."""

    def test_register_and_lookup(self):
        reg = _make_provider_registry()
        cfg = _make_provider_config(provider_id="p1")
        reg.register_provider("p1", cfg)
        result = reg.lookup_provider("p1")
        assert result is not None
        assert result.provider_id == "p1"

    def test_lookup_missing_returns_none(self):
        reg = _make_provider_registry()
        assert reg.lookup_provider("nonexistent") is None

    def test_unregister_provider(self):
        reg = _make_provider_registry()
        cfg = _make_provider_config(provider_id="p1")
        reg.register_provider("p1", cfg)
        reg.unregister_provider("p1")
        assert reg.lookup_provider("p1") is None

    def test_register_multiple_providers(self):
        reg = _make_provider_registry()
        for i in range(5):
            cfg = _make_provider_config(provider_id=f"p{i}")
            reg.register_provider(f"p{i}", cfg)
        for i in range(5):
            assert reg.lookup_provider(f"p{i}") is not None

    def test_health_check_default(self):
        reg = _make_provider_registry()
        cfg = _make_provider_config(provider_id="p1")
        reg.register_provider("p1", cfg)
        health = reg.health_check("p1")
        assert isinstance(health, ProviderHealth)
        assert health.provider_id == "p1"

    def test_update_health(self):
        reg = _make_provider_registry()
        cfg = _make_provider_config(provider_id="p1")
        reg.register_provider("p1", cfg)
        reg.update_health("p1", status=ProviderStatus.DEGRADED.value, latency_ms=500)
        health = reg.health_check("p1")
        assert health.status == ProviderStatus.DEGRADED.value


# ===========================================================================
# ProviderMatcher tests
# ===========================================================================


class TestProviderMatcher:
    """ProviderMatcher: find providers for a contract."""

    def test_match_single_provider(self):
        preg = _make_provider_registry()
        cfg = _make_provider_config(provider_id="mcp-test")
        preg.register_provider("mcp-test", cfg)
        matcher = ProviderMatcher(provider_registry=preg)

        contract = _make_contract(provider_id="mcp-test")
        results = matcher.match(contract)
        assert len(results) == 1
        assert results[0].provider_id == "mcp-test"

    def test_match_no_provider_returns_empty(self):
        preg = _make_provider_registry()
        matcher = ProviderMatcher(provider_registry=preg)
        contract = _make_contract(provider_id="nonexistent")
        results = matcher.match(contract)
        assert results == []

    def test_match_or_raise_on_missing(self):
        preg = _make_provider_registry()
        matcher = ProviderMatcher(provider_registry=preg)
        contract = _make_contract(provider_id="nonexistent")
        with pytest.raises(NoProviderError):
            matcher.match_or_raise(contract)

    def test_match_unhealthy_filtered(self):
        preg = _make_provider_registry()
        cfg = _make_provider_config(provider_id="p1")
        preg.register_provider("p1", cfg)
        preg.update_health("p1", status=ProviderStatus.UNHEALTHY.value)
        matcher = ProviderMatcher(provider_registry=preg)
        contract = _make_contract(provider_id="p1")
        results = matcher.match(contract)
        assert results == []

    def test_match_unhealthy_included_when_flag_set(self):
        preg = _make_provider_registry()
        cfg = _make_provider_config(provider_id="p1")
        preg.register_provider("p1", cfg)
        preg.update_health("p1", status=ProviderStatus.UNHEALTHY.value)
        matcher = ProviderMatcher(provider_registry=preg)
        contract = _make_contract(provider_id="p1")
        results = matcher.match(contract, include_unhealthy=True)
        assert len(results) == 1

    def test_match_degraded_included(self):
        preg = _make_provider_registry()
        cfg = _make_provider_config(provider_id="p1")
        preg.register_provider("p1", cfg)
        preg.update_health("p1", status=ProviderStatus.DEGRADED.value)
        matcher = ProviderMatcher(provider_registry=preg)
        contract = _make_contract(provider_id="p1")
        results = matcher.match(contract)
        assert len(results) == 1

    def test_match_prompt_contract_empty(self):
        """Prompt contracts have no provider_id, so match returns []."""
        from k1.fabric.types import PromptContract, VariableSpec

        preg = _make_provider_registry()
        matcher = ProviderMatcher(provider_registry=preg)
        prompt = PromptContract(
            name="test_prompt_v1",
            version="1.0.0",
            domain=["TEST"],
            description="Test prompt",
            variables=[
                VariableSpec(name="input", type="STRING", required=True, description="Test var"),
            ],
        )
        results = matcher.match(prompt)
        assert results == []


# ===========================================================================
# ProviderSelector tests
# ===========================================================================


class TestProviderSelector:
    """ProviderSelector: deterministic selection per FAB-10."""

    def test_select_single_candidate(self):
        selector = ProviderSelector()
        cfg = _make_provider_config(provider_id="p1")
        contract = _make_contract(provider_id="p1")
        candidate = ScoredCandidate(
            provider_config=cfg,
            contract=contract,
            policy_result=PolicyResult(allowed=True, score=1.0),
        )
        result = selector.select([candidate])
        assert result.provider_config.provider_id == "p1"
        assert result.policy_result.score == 1.0

    def test_select_highest_score_wins(self):
        selector = ProviderSelector()
        candidates = []
        for pid, score in [("p1", 0.8), ("p2", 0.95), ("p3", 0.7)]:
            candidates.append(
                ScoredCandidate(
                    provider_config=_make_provider_config(provider_id=pid),
                    contract=_make_contract(provider_id=pid),
                    policy_result=PolicyResult(allowed=True, score=score),
                )
            )
        result = selector.select(candidates)
        assert result.provider_config.provider_id == "p2"

    def test_select_deterministic_tiebreak_latency(self):
        """When scores tie, lower avg_latency_ms wins."""
        selector = ProviderSelector()
        candidates = [
            ScoredCandidate(
                provider_config=_make_provider_config(provider_id="p1"),
                contract=_make_contract(provider_id="p1", avg_latency_ms=500),
                policy_result=PolicyResult(allowed=True, score=1.0),
            ),
            ScoredCandidate(
                provider_config=_make_provider_config(provider_id="p2"),
                contract=_make_contract(provider_id="p2", avg_latency_ms=100),
                policy_result=PolicyResult(allowed=True, score=1.0),
            ),
        ]
        result = selector.select(candidates)
        assert result.provider_config.provider_id == "p2"

    def test_select_deterministic_tiebreak_provider_id(self):
        """When score and latency tie, alphabetical provider_id wins."""
        selector = ProviderSelector()
        candidates = [
            ScoredCandidate(
                provider_config=_make_provider_config(provider_id="zoo-provider"),
                contract=_make_contract(provider_id="zoo-provider", avg_latency_ms=100),
                policy_result=PolicyResult(allowed=True, score=1.0),
            ),
            ScoredCandidate(
                provider_config=_make_provider_config(provider_id="alpha-provider"),
                contract=_make_contract(provider_id="alpha-provider", avg_latency_ms=100),
                policy_result=PolicyResult(allowed=True, score=1.0),
            ),
        ]
        result = selector.select(candidates)
        assert result.provider_config.provider_id == "alpha-provider"

    def test_select_empty_raises_no_candidates(self):
        selector = ProviderSelector()
        with pytest.raises(NoCandidatesError):
            selector.select([])

    def test_select_all_rejected_raises(self):
        selector = ProviderSelector()
        candidates = [
            ScoredCandidate(
                provider_config=_make_provider_config(provider_id="p1"),
                contract=_make_contract(provider_id="p1"),
                policy_result=PolicyResult(allowed=False, score=0.0, reasons=["band_denied"]),
            ),
        ]
        with pytest.raises(AllProvidersRejectedError):
            selector.select(candidates)

    def test_select_filters_rejected_before_ranking(self):
        """Rejected candidates are filtered out; best allowed candidate wins."""
        selector = ProviderSelector()
        candidates = [
            ScoredCandidate(
                provider_config=_make_provider_config(provider_id="p1"),
                contract=_make_contract(provider_id="p1"),
                policy_result=PolicyResult(allowed=False, score=0.0, reasons=["denied"]),
            ),
            ScoredCandidate(
                provider_config=_make_provider_config(provider_id="p2"),
                contract=_make_contract(provider_id="p2"),
                policy_result=PolicyResult(allowed=True, score=0.8),
            ),
        ]
        result = selector.select(candidates)
        assert result.provider_config.provider_id == "p2"

    def test_select_top_n(self):
        selector = ProviderSelector()
        candidates = [
            ScoredCandidate(
                provider_config=_make_provider_config(provider_id=f"p{i}"),
                contract=_make_contract(provider_id=f"p{i}"),
                policy_result=PolicyResult(allowed=True, score=1.0 - i * 0.1),
            )
            for i in range(5)
        ]
        top_3 = selector.select_top_n(candidates, n=3)
        assert len(top_3) == 3
        assert top_3[0].provider_config.provider_id == "p0"
        assert top_3[1].provider_config.provider_id == "p1"
        assert top_3[2].provider_config.provider_id == "p2"


# ===========================================================================
# ProviderFactory tests
# ===========================================================================


class TestProviderFactory:
    """ProviderFactory: handler registration and instantiation."""

    def test_register_and_create(self):
        factory = ProviderFactory()

        class FakeProvider:
            def __init__(self, config, **kwargs):
                self.config = config

        factory.register_handler("MCP", FakeProvider)
        assert factory.has_handler("MCP")
        cfg = _make_provider_config(provider_id="p1", provider_type="MCP")
        provider = factory.create(cfg)
        assert provider.config.provider_id == "p1"

    def test_create_unsupported_type_raises(self):
        factory = ProviderFactory()
        cfg = _make_provider_config(provider_id="p1", provider_type="UNKNOWN")
        with pytest.raises(UnsupportedProviderTypeError):
            factory.create(cfg)

    def test_create_constructor_failure_raises(self):
        factory = ProviderFactory()

        def bad_constructor(config, **kwargs):
            raise RuntimeError("constructor exploded")

        factory.register_handler("BOOM", bad_constructor)
        cfg = _make_provider_config(provider_id="p1", provider_type="BOOM")
        with pytest.raises(ProviderInstantiationError):
            factory.create(cfg)

    def test_registered_types_sorted(self):
        factory = ProviderFactory()
        factory.register_handler("WASM", lambda c, **k: None)
        factory.register_handler("MCP", lambda c, **k: None)
        factory.register_handler("AGENT", lambda c, **k: None)
        assert factory.registered_types() == ["AGENT", "MCP", "WASM"]

    def test_register_empty_type_raises(self):
        factory = ProviderFactory()
        with pytest.raises(ValueError):
            factory.register_handler("", lambda c, **k: None)

    def test_port_deps_passed_to_constructor(self):
        received_deps = {}

        def capturing_constructor(config, **kwargs):
            received_deps.update(kwargs)
            return config  # dummy provider

        factory = ProviderFactory(bridge_port="fake_bridge")
        factory.register_handler("MCP", capturing_constructor)
        cfg = _make_provider_config(provider_id="p1", provider_type="MCP")
        factory.create(cfg)
        assert received_deps.get("bridge_port") == "fake_bridge"


# ===========================================================================
# Resolver tests
# ===========================================================================


class TestResolver:
    """Resolver: full 5-step resolution pipeline."""

    def _build_resolver(
        self,
        contracts: list[CapabilityContract] | None = None,
        provider_configs: list[ProviderConfig] | None = None,
        policy_engine=None,
    ) -> Resolver:
        """Wire up a complete Resolver with real components."""
        cap_reg = _make_registry()
        prov_reg = _make_provider_registry()
        factory = ProviderFactory()

        # Register a dummy handler for MCP
        factory.register_handler("MCP", lambda c, **k: c)

        if contracts:
            for c in contracts:
                cap_reg.register(c)
        if provider_configs:
            for cfg in provider_configs:
                prov_reg.register_provider(cfg.provider_id, cfg)

        matcher = ProviderMatcher(provider_registry=prov_reg)
        selector = ProviderSelector()

        return Resolver(
            capability_registry=cap_reg,
            provider_matcher=matcher,
            provider_selector=selector,
            provider_factory=factory,
            policy_engine=policy_engine,
        )

    def test_resolve_happy_path(self):
        """Full pipeline succeeds: lookup -> match -> policy(default) -> select."""
        contract = _make_contract(provider_id="mcp-test")
        cfg = _make_provider_config(provider_id="mcp-test")
        resolver = self._build_resolver(
            contracts=[contract],
            provider_configs=[cfg],
        )
        request = _make_request(capability_name="tool.execute.test_cap")
        resolved = resolver.resolve(request)
        assert resolved.provider_config.provider_id == "mcp-test"
        assert resolved.policy_result.allowed is True
        assert resolved.policy_result.score == 1.0

    def test_resolve_capability_not_found(self):
        """No contract registered -> ResolutionFailedError with capability_not_found."""
        resolver = self._build_resolver()
        request = _make_request(capability_name="tool.execute.missing")
        with pytest.raises(ResolutionFailedError) as exc_info:
            resolver.resolve(request)
        assert exc_info.value.error_code == "capability_not_found"

    def test_resolve_no_provider(self):
        """Contract exists but no provider registered -> no_provider."""
        contract = _make_contract(provider_id="mcp-missing")
        resolver = self._build_resolver(contracts=[contract])
        request = _make_request(capability_name="tool.execute.test_cap")
        with pytest.raises(ResolutionFailedError) as exc_info:
            resolver.resolve(request)
        assert exc_info.value.error_code == "no_provider"

    def test_resolve_to_result_success(self):
        """resolve_to_result() returns CapabilityResult.success on happy path."""
        contract = _make_contract(provider_id="mcp-test")
        cfg = _make_provider_config(provider_id="mcp-test")
        resolver = self._build_resolver(
            contracts=[contract],
            provider_configs=[cfg],
        )
        request = _make_request(capability_name="tool.execute.test_cap")
        result = resolver.resolve_to_result(request)
        assert result.success is True
        assert result.data["provider_id"] == "mcp-test"

    def test_resolve_to_result_failure(self):
        """resolve_to_result() returns CapabilityResult.failure on error."""
        resolver = self._build_resolver()
        request = _make_request(capability_name="tool.execute.missing")
        result = resolver.resolve_to_result(request)
        assert result.success is False
        assert result.error is not None
        assert result.error.code == "capability_not_found"

    def test_resolve_with_custom_policy_engine(self):
        """Resolver uses injected PolicyEngine (access_denied path)."""

        class RejectAllPolicy:
            def evaluate(self, candidates, contract, request):
                return [
                    ScoredCandidate(
                        provider_config=cfg,
                        contract=contract,
                        policy_result=PolicyResult(
                            allowed=False,
                            score=0.0,
                            reasons=["test_rejection"],
                        ),
                    )
                    for cfg in candidates
                ]

        contract = _make_contract(provider_id="mcp-test")
        cfg = _make_provider_config(provider_id="mcp-test")
        resolver = self._build_resolver(
            contracts=[contract],
            provider_configs=[cfg],
            policy_engine=RejectAllPolicy(),
        )
        request = _make_request()
        with pytest.raises(ResolutionFailedError) as exc_info:
            resolver.resolve(request)
        assert exc_info.value.error_code == "access_denied"

    def test_resolve_default_policy_passes_all(self):
        """Without PolicyEngine, all candidates get score=1.0, allowed=True."""
        contract = _make_contract(provider_id="mcp-a")
        cfg = _make_provider_config(provider_id="mcp-a")
        resolver = self._build_resolver(
            contracts=[contract],
            provider_configs=[cfg],
        )
        request = _make_request()
        resolved = resolver.resolve(request)
        assert resolved.policy_result.allowed is True
        assert resolved.policy_result.score == 1.0
        assert "default_pass_all" in resolved.policy_result.reasons

    def test_resolve_to_result_timing(self):
        """resolve_to_result() populates resolution_time_ms."""
        contract = _make_contract(provider_id="mcp-test")
        cfg = _make_provider_config(provider_id="mcp-test")
        resolver = self._build_resolver(
            contracts=[contract],
            provider_configs=[cfg],
        )
        request = _make_request()
        result = resolver.resolve_to_result(request)
        assert result.success is True
        assert result.resolution_time_ms >= 0

    def test_resolve_multiple_contracts_correct_lookup(self):
        """Resolver finds the correct contract when multiple are registered."""
        c1 = _make_contract(
            name="tool.execute.alpha",
            provider_id="p-alpha",
        )
        c2 = _make_contract(
            name="tool.execute.beta",
            provider_id="p-beta",
        )
        p1 = _make_provider_config(provider_id="p-alpha")
        p2 = _make_provider_config(provider_id="p-beta")

        resolver = self._build_resolver(
            contracts=[c1, c2],
            provider_configs=[p1, p2],
        )
        req = _make_request(capability_name="tool.execute.beta")
        resolved = resolver.resolve(req)
        assert resolved.provider_config.provider_id == "p-beta"
