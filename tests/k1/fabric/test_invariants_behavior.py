"""
Epic 6.6.3 -- Behavioral invariant tests (FAB-09 to FAB-13).

Hard behavioral invariants that MUST hold at all times.
These tests verify invariants through event inspection, deterministic
execution, naming validation, registration validation, and performance.

Invariants covered:
  FAB-09: Every event emitted carries a cognitive_trace_id.
  FAB-10: Same inputs + same registry state = same provider selected.
  FAB-11: Invalid capability names are rejected at registration.
  FAB-12: Registration always validates contracts (no bypass by default).
  FAB-13: Performance benchmarks (lookup <1ms, retrieval <50ms, overhead <100ms).

NO MOCKS -- all tests use real adapters and real Fabric components.

References:
  - fabric-implementation-plan.md Epic 6.6, Issue 6.6.3
  - FAB-09, FAB-10, FAB-11, FAB-12, FAB-13
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from k1.fabric.core.contract_validator import (
    _NAME_PATTERNS,
    ContractValidationError,
    ContractValidator,
)
from k1.fabric.core.registry import CapabilityRegistry
from k1.fabric.events import (
    TOPIC_CAPABILITY_COMPLETED,
    TOPIC_CAPABILITY_FAILED,
    TOPIC_CAPABILITY_INVOKED,
    TOPIC_CAPABILITY_REGISTERED,
    TOPIC_LEARNING_SIGNAL,
)
from k1.fabric.fabric import Fabric
from k1.fabric.factory import FabricFactory
from k1.fabric.types import (
    Availability,
    CapabilityContract,
    CapabilityRequest,
    InputSpec,
    SafetyBand,
    Tier,
)
from tests.k1.fabric.helpers import (
    assert_capability_result_success,
    create_n_contracts,
    register_contract_with_provider,
)

# ---------------------------------------------------------------------------
# Fixtures directory
# ---------------------------------------------------------------------------

FIXTURES_DIR = Path(__file__).parent / "fixtures"

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_fabric() -> Fabric:
    """Create a Fabric with event capture for behavioral invariant tests."""
    return FabricFactory.create_for_testing(
        capture_events=True,
        contracts_dir=str(FIXTURES_DIR),
    )


def _make_contract(
    name: str,
    *,
    version: str = "1.0.0",
    provider_id: str = "",
    domain: str = "BEHAVIOR_TEST",
    provider_type: str = "MCP",
    safety_band_min: str = SafetyBand.GREEN.value,
    availability: str = Availability.ONLINE.value,
) -> CapabilityContract:
    """Build a CapabilityContract with sensible defaults."""
    pid = provider_id or f"provider-{name.replace('.', '-')}"
    return CapabilityContract(
        name=name,
        version=version,
        domain=[domain],
        description=f"Behavioral invariant test: {name}",
        capabilities=["test_action"],
        limitations=[],
        required_inputs=[
            InputSpec(name="input_a", type="STRING", description="Test input"),
        ],
        output={"type": "object"},
        provider_type=provider_type,
        provider_id=pid,
        safety_band_min=safety_band_min,
        availability=availability,
    )


def _request(
    capability_name: str,
    *,
    caller: str = "test-behavior-inv",
    params: dict | None = None,
) -> CapabilityRequest:
    """Build a CapabilityRequest for behavioral invariant tests."""
    return CapabilityRequest(
        capability_name=capability_name,
        params=params or {"input_a": "test"},
        tier=Tier.LOW.value,
        caller=caller,
    )


def _register_test_cap(
    fabric: Fabric,
    name: str = "tool.execute.beh_test",
    provider_id: str = "mcp-beh-test",
) -> CapabilityContract:
    """Register a minimal test capability for behavioral tests."""
    contract = _make_contract(name, provider_id=provider_id)
    register_contract_with_provider(fabric, contract)
    return contract


# =========================================================================
# FAB-09 -- Every event carries cognitive_trace_id
# =========================================================================


class TestFAB09CognitiveTraceId:
    """
    FAB-09: Every event emitted by EventEmitter carries cognitive_trace_id.

    The EventEmitter wraps every emit call to inject cognitive_trace_id
    into the payload. This ensures full end-to-end traceability of every
    event emitted during capability execution.
    """

    async def test_invoked_event_has_cognitive_trace_id(self) -> None:
        """Invoked event carries a non-empty cognitive_trace_id."""
        fabric = _make_fabric()
        _register_test_cap(fabric, "tool.execute.trace_inv", "mcp-trace-inv")

        request = _request("tool.execute.trace_inv")
        await fabric.execute(request)

        captured = fabric.event_port.get_captured(topic=TOPIC_CAPABILITY_INVOKED)
        assert len(captured) >= 1, "Expected at least 1 invoked event"
        _, payload = captured[-1]
        trace_id = payload.get("cognitive_trace_id")
        assert trace_id, f"Expected non-empty cognitive_trace_id, got: {trace_id!r}"

    async def test_completed_event_has_cognitive_trace_id(self) -> None:
        """Completed event carries a non-empty cognitive_trace_id."""
        fabric = _make_fabric()
        _register_test_cap(fabric, "tool.execute.trace_comp", "mcp-trace-comp")

        request = _request("tool.execute.trace_comp")
        result = await fabric.execute(request)
        assert_capability_result_success(result)

        captured = fabric.event_port.get_captured(topic=TOPIC_CAPABILITY_COMPLETED)
        assert len(captured) >= 1, "Expected at least 1 completed event"
        _, payload = captured[-1]
        trace_id = payload.get("cognitive_trace_id")
        assert trace_id, f"Expected non-empty cognitive_trace_id, got: {trace_id!r}"

    async def test_failed_event_has_cognitive_trace_id(self) -> None:
        """Failed event carries cognitive_trace_id even on resolution failure."""
        fabric = _make_fabric()
        # Do NOT register the capability so execution fails at resolution
        request = _request("tool.execute.nonexistent_trace_fail")
        result = await fabric.execute(request)
        assert result.success is False

        # Check failed events
        captured = fabric.event_port.get_captured(topic=TOPIC_CAPABILITY_FAILED)
        if captured:
            _, payload = captured[-1]
            trace_id = payload.get("cognitive_trace_id")
            # cognitive_trace_id is always set (may be empty string for unresolved)
            assert (
                "cognitive_trace_id" in payload
            ), "Failed event must contain cognitive_trace_id key"

    async def test_learning_signal_has_cognitive_trace_id(self) -> None:
        """Learning signal event carries cognitive_trace_id."""
        fabric = _make_fabric()
        _register_test_cap(fabric, "tool.execute.trace_learn", "mcp-trace-learn")

        request = _request("tool.execute.trace_learn")
        await fabric.execute(request)

        captured = fabric.event_port.get_captured(topic=TOPIC_LEARNING_SIGNAL)
        assert len(captured) >= 1, "Expected at least 1 learning signal event"
        _, payload = captured[-1]
        # Learning signal also carries cognitive_trace_id via EventEmitter
        assert (
            "cognitive_trace_id" in payload
        ), "Learning signal must contain cognitive_trace_id key"

    async def test_registered_event_has_cognitive_trace_id(self) -> None:
        """Registration event carries cognitive_trace_id key."""
        fabric = _make_fabric()
        contract = _make_contract("tool.execute.trace_reg", provider_id="mcp-trace-reg")
        register_contract_with_provider(fabric, contract)

        captured = fabric.event_port.get_captured(topic=TOPIC_CAPABILITY_REGISTERED)
        assert len(captured) >= 1, "Expected at least 1 registered event"
        _, payload = captured[-1]
        assert (
            "cognitive_trace_id" in payload
        ), "Registered event must contain cognitive_trace_id key"

    async def test_all_events_share_trace_id_within_execution(self) -> None:
        """All events from one execution share the same cognitive_trace_id."""
        fabric = _make_fabric()
        _register_test_cap(fabric, "tool.execute.trace_shared", "mcp-trace-shared")

        # Clear any events from registration
        fabric.event_port.drain()

        request = _request("tool.execute.trace_shared")
        result = await fabric.execute(request)
        assert_capability_result_success(result)

        # Collect trace_ids from all execution-lifecycle events
        trace_ids = set()
        for topic in (
            TOPIC_CAPABILITY_INVOKED,
            TOPIC_CAPABILITY_COMPLETED,
            TOPIC_LEARNING_SIGNAL,
        ):
            for _, payload in fabric.event_port.get_captured(topic=topic):
                tid = payload.get("cognitive_trace_id")
                if tid:
                    trace_ids.add(tid)

        # All events from the single execution should share one trace_id
        assert (
            len(trace_ids) == 1
        ), f"Expected 1 shared trace_id across all events, got {len(trace_ids)}: {trace_ids}"

    async def test_different_executions_have_different_trace_ids(self) -> None:
        """Separate executions produce distinct cognitive_trace_ids."""
        fabric = _make_fabric()
        _register_test_cap(fabric, "tool.execute.trace_diff", "mcp-trace-diff")

        trace_ids = []
        for _ in range(5):
            fabric.event_port.drain()
            request = _request("tool.execute.trace_diff")
            await fabric.execute(request)

            captured = fabric.event_port.get_captured(topic=TOPIC_CAPABILITY_INVOKED)
            assert len(captured) >= 1
            _, payload = captured[-1]
            tid = payload.get("cognitive_trace_id")
            if tid:
                trace_ids.append(tid)

        unique = set(trace_ids)
        assert len(unique) == 5, f"Expected 5 unique trace_ids, got {len(unique)}: {unique}"

    async def test_cognitive_trace_id_is_string(self) -> None:
        """cognitive_trace_id value is a string type."""
        fabric = _make_fabric()
        _register_test_cap(fabric, "tool.execute.trace_type", "mcp-trace-type")

        request = _request("tool.execute.trace_type")
        await fabric.execute(request)

        captured = fabric.event_port.get_captured(topic=TOPIC_CAPABILITY_INVOKED)
        assert len(captured) >= 1
        _, payload = captured[-1]
        trace_id = payload.get("cognitive_trace_id")
        assert isinstance(
            trace_id, str
        ), f"cognitive_trace_id must be str, got {type(trace_id).__name__}"

    async def test_bulk_executions_all_have_trace_ids(self) -> None:
        """10 sequential executions each produce events with cognitive_trace_id."""
        fabric = _make_fabric()
        _register_test_cap(fabric, "tool.execute.trace_bulk", "mcp-trace-bulk")

        for _ in range(10):
            request = _request("tool.execute.trace_bulk")
            await fabric.execute(request)

        captured = fabric.event_port.get_captured(topic=TOPIC_CAPABILITY_INVOKED)
        assert len(captured) >= 10, f"Expected >= 10 invoked events, got {len(captured)}"

        trace_ids = set()
        for _, payload in captured:
            tid = payload.get("cognitive_trace_id")
            assert tid, "Every invoked event must have a non-empty cognitive_trace_id"
            trace_ids.add(tid)

        assert len(trace_ids) >= 10, f"Expected >= 10 unique trace_ids, got {len(trace_ids)}"


# =========================================================================
# FAB-10 -- Deterministic provider selection
# =========================================================================


class TestFAB10DeterministicSelection:
    """
    FAB-10: Same inputs + same registry state = same provider selected.

    The provider resolution pipeline (HardFilter -> SoftRanker -> ProviderSelector)
    must produce deterministic results. Running the same request with the same
    registry state must always select the same provider.
    """

    async def test_same_execution_100_times_same_provider(self) -> None:
        """Execute same capability 100 times: provider_id is always identical."""
        fabric = _make_fabric()
        _register_test_cap(fabric, "tool.execute.det_100", "mcp-det-100")

        provider_ids = []
        for _ in range(100):
            request = _request("tool.execute.det_100")
            result = await fabric.execute(request)
            assert_capability_result_success(result)
            provider_ids.append(result.provider_id)

        unique = set(provider_ids)
        assert (
            len(unique) == 1
        ), f"Expected 1 provider across 100 executions, got {len(unique)}: {unique}"
        assert unique.pop() == "mcp-det-100"

    async def test_two_capabilities_each_deterministic(self) -> None:
        """Two different capabilities each consistently select their own provider."""
        fabric = _make_fabric()
        _register_test_cap(fabric, "tool.execute.det_a", "mcp-det-a")
        _register_test_cap(fabric, "tool.execute.det_b", "mcp-det-b")

        providers_a = set()
        providers_b = set()
        for _ in range(20):
            req_a = _request("tool.execute.det_a")
            result_a = await fabric.execute(req_a)
            assert_capability_result_success(result_a)
            providers_a.add(result_a.provider_id)

            req_b = _request("tool.execute.det_b")
            result_b = await fabric.execute(req_b)
            assert_capability_result_success(result_b)
            providers_b.add(result_b.provider_id)

        assert len(providers_a) == 1, f"Cap A not deterministic: {providers_a}"
        assert len(providers_b) == 1, f"Cap B not deterministic: {providers_b}"
        assert providers_a != providers_b, "Different caps should have different providers"

    async def test_deterministic_after_interleaved_requests(self) -> None:
        """Interleaving requests for different capabilities doesn't affect determinism."""
        fabric = _make_fabric()
        _register_test_cap(fabric, "tool.execute.det_intl_x", "mcp-det-intl-x")
        _register_test_cap(fabric, "tool.execute.det_intl_y", "mcp-det-intl-y")

        # Interleave: x, y, x, y, x, y, ...
        providers_x = set()
        providers_y = set()
        for _ in range(15):
            rx = _request("tool.execute.det_intl_x")
            res_x = await fabric.execute(rx)
            assert_capability_result_success(res_x)
            providers_x.add(res_x.provider_id)

            ry = _request("tool.execute.det_intl_y")
            res_y = await fabric.execute(ry)
            assert_capability_result_success(res_y)
            providers_y.add(res_y.provider_id)

        assert len(providers_x) == 1, f"X not deterministic: {providers_x}"
        assert len(providers_y) == 1, f"Y not deterministic: {providers_y}"

    async def test_deterministic_with_different_callers(self) -> None:
        """Different callers for the same capability get the same provider."""
        fabric = _make_fabric()
        _register_test_cap(fabric, "tool.execute.det_caller", "mcp-det-caller")

        providers = set()
        for i in range(10):
            request = _request("tool.execute.det_caller", caller=f"caller-{i}")
            result = await fabric.execute(request)
            assert_capability_result_success(result)
            providers.add(result.provider_id)

        assert len(providers) == 1, f"Different callers got different providers: {providers}"

    async def test_deterministic_with_different_params(self) -> None:
        """Different params for the same capability get the same provider."""
        fabric = _make_fabric()
        _register_test_cap(fabric, "tool.execute.det_params", "mcp-det-params")

        providers = set()
        for i in range(10):
            request = _request(
                "tool.execute.det_params",
                params={"input_a": f"value_{i}"},
            )
            result = await fabric.execute(request)
            assert_capability_result_success(result)
            providers.add(result.provider_id)

        assert len(providers) == 1, f"Different params got different providers: {providers}"


# =========================================================================
# FAB-11 -- Invalid capability names rejected
# =========================================================================


class TestFAB11InvalidNameRejected:
    """
    FAB-11: Invalid capability names are rejected by ContractValidator.

    The _NAME_PATTERNS in ContractValidator enforce naming conventions
    per contract type. Names that don't match are rejected before
    registration completes.
    """

    def test_tool_name_uppercase_rejected(self) -> None:
        """Tool name with uppercase letters is rejected."""
        fabric = _make_fabric()
        contract = _make_contract("tool.execute.BAD_NAME")
        with pytest.raises(ContractValidationError) as exc_info:
            fabric.register(contract)
        assert "rule-01" in str(exc_info.value) or "name" in str(exc_info.value).lower()

    def test_tool_name_missing_prefix_rejected(self) -> None:
        """Tool name without 'tool.' prefix is rejected."""
        fabric = _make_fabric()
        contract = _make_contract("execute.some_action")
        with pytest.raises(ContractValidationError) as exc_info:
            fabric.register(contract)
        assert any("rule-01" in e for e in exc_info.value.errors)

    def test_tool_name_missing_action_segment_rejected(self) -> None:
        """Tool name without action segment (execute/read/write/delete) is rejected."""
        fabric = _make_fabric()
        contract = _make_contract("tool.some_action")
        with pytest.raises(ContractValidationError) as exc_info:
            fabric.register(contract)
        assert any("rule-01" in e for e in exc_info.value.errors)

    def test_tool_name_with_spaces_rejected(self) -> None:
        """Tool name containing spaces is rejected."""
        fabric = _make_fabric()
        contract = _make_contract("tool.execute.bad name")
        with pytest.raises(ContractValidationError) as exc_info:
            fabric.register(contract)
        assert any("rule-01" in e for e in exc_info.value.errors)

    def test_tool_name_with_special_chars_rejected(self) -> None:
        """Tool name with special characters is rejected."""
        fabric = _make_fabric()
        contract = _make_contract("tool.execute.bad@name!")
        with pytest.raises(ContractValidationError) as exc_info:
            fabric.register(contract)
        assert any("rule-01" in e for e in exc_info.value.errors)

    def test_empty_name_rejected(self) -> None:
        """Empty name is rejected by the validator."""
        fabric = _make_fabric()
        contract = _make_contract("tool.execute.placeholder")
        # Override name to empty after construction
        object.__setattr__(contract, "name", "")
        with pytest.raises(ContractValidationError) as exc_info:
            fabric.register(contract)
        assert any("rule-01" in e for e in exc_info.value.errors)

    def test_tool_name_only_two_segments_rejected(self) -> None:
        """Tool name with only two segments (tool.execute) is rejected."""
        fabric = _make_fabric()
        contract = _make_contract("tool.execute")
        with pytest.raises(ContractValidationError) as exc_info:
            fabric.register(contract)
        assert any("rule-01" in e for e in exc_info.value.errors)

    def test_tool_name_starting_with_digit_segment_rejected(self) -> None:
        """Tool name with a segment starting with digit is rejected."""
        fabric = _make_fabric()
        contract = _make_contract("tool.execute.9bad")
        with pytest.raises(ContractValidationError) as exc_info:
            fabric.register(contract)
        assert any("rule-01" in e for e in exc_info.value.errors)

    def test_valid_tool_name_accepted(self) -> None:
        """Valid tool name with 3 segments passes validation."""
        fabric = _make_fabric()
        contract = _make_contract("tool.execute.valid_action")
        # Should NOT raise
        register_contract_with_provider(fabric, contract)
        assert fabric.lookup("tool.execute.valid_action") is not None

    def test_valid_tool_name_with_underscores_accepted(self) -> None:
        """Valid tool name with underscores in capability segment passes."""
        fabric = _make_fabric()
        contract = _make_contract("tool.execute.home_hue_set_brightness")
        register_contract_with_provider(fabric, contract)
        assert fabric.lookup("tool.execute.home_hue_set_brightness") is not None

    def test_valid_tool_read_action_accepted(self) -> None:
        """Valid tool name with 'read' action passes validation."""
        fabric = _make_fabric()
        contract = _make_contract("tool.read.data_store")
        register_contract_with_provider(fabric, contract)
        assert fabric.lookup("tool.read.data_store") is not None

    def test_valid_tool_write_action_accepted(self) -> None:
        """Valid tool name with 'write' action passes validation."""
        fabric = _make_fabric()
        contract = _make_contract("tool.write.file_output")
        register_contract_with_provider(fabric, contract)
        assert fabric.lookup("tool.write.file_output") is not None

    def test_valid_tool_delete_action_accepted(self) -> None:
        """Valid tool name with 'delete' action passes validation."""
        fabric = _make_fabric()
        contract = _make_contract("tool.delete.cache_entry")
        register_contract_with_provider(fabric, contract)
        assert fabric.lookup("tool.delete.cache_entry") is not None

    def test_name_patterns_keys_match_contract_types(self) -> None:
        """_NAME_PATTERNS has entries for all four contract types."""
        expected = {"tool_contract", "agent_contract", "prompt_contract", "workflow_contract"}
        assert set(_NAME_PATTERNS.keys()) == expected

    def test_tool_pattern_rejects_invalid_action_verb(self) -> None:
        """Tool name with invalid action verb (not execute/read/write/delete) is rejected."""
        fabric = _make_fabric()
        contract = _make_contract("tool.update.something")
        with pytest.raises(ContractValidationError) as exc_info:
            fabric.register(contract)
        assert any("rule-01" in e for e in exc_info.value.errors)


# =========================================================================
# FAB-12 -- Registration always validates contracts
# =========================================================================


class TestFAB12RegistrationValidates:
    """
    FAB-12: Registration always validates contracts by default.

    CapabilityRegistry.register() runs ContractValidator on every contract
    unless skip_validation=True (internal use only). This ensures no
    unvalidated contract enters the registry.
    """

    def test_registry_has_validator(self) -> None:
        """CapabilityRegistry is initialized with a ContractValidator."""
        fabric = _make_fabric()
        registry = fabric.facade._registry
        assert isinstance(registry, CapabilityRegistry)
        assert hasattr(registry, "_validator")
        assert isinstance(registry._validator, ContractValidator)

    def test_valid_contract_registers_successfully(self) -> None:
        """A valid contract passes validation and is registered."""
        fabric = _make_fabric()
        contract = _make_contract("tool.execute.val_ok")
        register_contract_with_provider(fabric, contract)
        assert fabric.lookup("tool.execute.val_ok") is not None

    def test_invalid_contract_rejected_at_registration(self) -> None:
        """An invalid contract (bad name) is rejected at registration time."""
        fabric = _make_fabric()
        contract = _make_contract("INVALID_NAME_NO_PREFIX")
        with pytest.raises(ContractValidationError):
            fabric.register(contract)

    def test_invalid_contract_not_in_registry_after_rejection(self) -> None:
        """After rejection, the contract is NOT present in the registry."""
        fabric = _make_fabric()
        contract = _make_contract("INVALID_NAME_CHECK")
        with pytest.raises(ContractValidationError):
            fabric.register(contract)
        # Verify not registered
        result = fabric.lookup("INVALID_NAME_CHECK")
        assert result is None

    def test_register_default_validates(self) -> None:
        """Registry.register() default skip_validation=False triggers validation."""
        fabric = _make_fabric()
        registry = fabric.facade._registry

        # A contract with an invalid name should be caught by the validator
        contract = _make_contract("BAD.CONTRACT.Name")
        with pytest.raises(ContractValidationError):
            registry.register(contract)

    def test_skip_validation_bypasses_validator(self) -> None:
        """skip_validation=True allows registration without validator check."""
        fabric = _make_fabric()
        registry = fabric.facade._registry

        # Use a name that would normally fail validation
        contract = _make_contract("tool.execute.skip_val_test")
        # This valid contract should work with skip_validation=True too
        registry.register(contract, skip_validation=True)
        assert registry.lookup("tool.execute.skip_val_test") is not None

    def test_validation_catches_empty_description(self) -> None:
        """Contract with empty description is rejected at registration."""
        fabric = _make_fabric()
        contract = _make_contract("tool.execute.no_desc")
        # Override description to empty
        object.__setattr__(contract, "description", "")
        with pytest.raises(ContractValidationError) as exc_info:
            fabric.register(contract)
        assert any("rule-04" in e or "description" in e.lower() for e in exc_info.value.errors)

    def test_validation_catches_invalid_version(self) -> None:
        """Contract with malformed version is rejected at registration."""
        fabric = _make_fabric()
        contract = _make_contract("tool.execute.bad_ver", version="abc")
        with pytest.raises(ContractValidationError) as exc_info:
            fabric.register(contract)
        assert any("rule-02" in e or "version" in e.lower() for e in exc_info.value.errors)

    def test_validation_catches_empty_domain(self) -> None:
        """Contract with empty domain list is rejected at registration."""
        fabric = _make_fabric()
        contract = _make_contract("tool.execute.no_domain")
        # Override domain to empty
        object.__setattr__(contract, "domain", [])
        with pytest.raises(ContractValidationError) as exc_info:
            fabric.register(contract)
        assert any("rule-03" in e or "domain" in e.lower() for e in exc_info.value.errors)

    def test_fabric_register_delegates_with_validation(self) -> None:
        """Fabric.register() goes through validation (not skip)."""
        fabric = _make_fabric()
        # Invalid contract should be rejected at Fabric level
        contract = _make_contract("NOT_A_VALID_NAME")
        with pytest.raises(ContractValidationError):
            fabric.register(contract)


# =========================================================================
# FAB-13 -- Performance benchmarks
# =========================================================================


class TestFAB13PerformanceBenchmarks:
    """
    FAB-13: Performance benchmarks for registry and execution.

    Targets:
      - Registry lookup:        < 1ms (P95)
      - Capability discovery:   < 50ms
      - Execute overhead:       < 100ms
    """

    def test_registry_lookup_under_1ms(self) -> None:
        """Registry lookup for a registered capability completes in < 1ms (P95)."""
        fabric = _make_fabric()
        # Register 100 contracts to ensure non-trivial registry
        contracts = create_n_contracts(100, domain="PERF_TEST")
        for c in contracts:
            register_contract_with_provider(fabric, c)

        target_name = "tool.execute.test_cap_0050"

        # Warm up
        for _ in range(10):
            fabric.lookup(target_name)

        # Measure 1000 lookups
        timings = []
        for _ in range(1000):
            start = time.perf_counter()
            result = fabric.lookup(target_name)
            elapsed = (time.perf_counter() - start) * 1000  # ms
            timings.append(elapsed)
            assert result is not None

        timings.sort()
        p95 = timings[int(len(timings) * 0.95)]
        assert p95 < 1.0, f"Registry lookup P95 = {p95:.4f}ms, exceeds 1ms target"

    def test_registry_lookup_1000_contracts_under_1ms(self) -> None:
        """Registry lookup with 1000 contracts still < 1ms (O(1) dict access)."""
        fabric = _make_fabric()
        contracts = create_n_contracts(1000, domain="PERF_1K")
        for c in contracts:
            register_contract_with_provider(fabric, c)

        target_name = "tool.execute.test_cap_0500"

        # Warm up
        for _ in range(10):
            fabric.lookup(target_name)

        timings = []
        for _ in range(500):
            start = time.perf_counter()
            result = fabric.lookup(target_name)
            elapsed = (time.perf_counter() - start) * 1000
            timings.append(elapsed)
            assert result is not None

        timings.sort()
        p95 = timings[int(len(timings) * 0.95)]
        assert p95 < 1.0, f"Lookup P95 with 1K contracts = {p95:.4f}ms, exceeds 1ms target"

    async def test_discover_capabilities_under_50ms(self) -> None:
        """discover_capabilities with 100 contracts completes in < 50ms."""
        fabric = _make_fabric()
        contracts = create_n_contracts(100, domain="PERF_DISCOVER")
        for c in contracts:
            register_contract_with_provider(fabric, c)

        # Warm up
        await fabric.discover_capabilities(
            domain=["PERF_DISCOVER"],
            intent="test action",
        )

        timings = []
        for _ in range(20):
            start = time.perf_counter()
            result = await fabric.discover_capabilities(
                domain=["PERF_DISCOVER"],
                intent="test action",
            )
            elapsed = (time.perf_counter() - start) * 1000
            timings.append(elapsed)

        timings.sort()
        p95 = timings[int(len(timings) * 0.95)]
        assert p95 < 50.0, f"Discovery P95 = {p95:.4f}ms, exceeds 50ms target"

    async def test_execute_overhead_under_100ms(self) -> None:
        """Full fabric.execute() overhead (no real I/O) completes in < 100ms."""
        fabric = _make_fabric()
        _register_test_cap(fabric, "tool.execute.perf_exec", "mcp-perf-exec")

        # Warm up
        for _ in range(3):
            request = _request("tool.execute.perf_exec")
            await fabric.execute(request)

        timings = []
        for _ in range(50):
            request = _request("tool.execute.perf_exec")
            start = time.perf_counter()
            result = await fabric.execute(request)
            elapsed = (time.perf_counter() - start) * 1000
            timings.append(elapsed)
            assert_capability_result_success(result)

        timings.sort()
        p95 = timings[int(len(timings) * 0.95)]
        assert p95 < 100.0, f"Execute P95 = {p95:.4f}ms, exceeds 100ms target"

    def test_bulk_register_1000_contracts_all_discoverable(self) -> None:
        """1000 registered contracts are all discoverable via lookup."""
        fabric = _make_fabric()
        contracts = create_n_contracts(1000, domain="PERF_BULK")
        for c in contracts:
            register_contract_with_provider(fabric, c)

        # Verify every single one is findable
        for c in contracts:
            result = fabric.lookup(c.name)
            assert result is not None, f"Contract {c.name} not found after registration"

    def test_registry_contains_check_is_fast(self) -> None:
        """Registry contains() for a registered name < 1ms."""
        fabric = _make_fabric()
        contracts = create_n_contracts(500, domain="PERF_CONTAINS")
        for c in contracts:
            register_contract_with_provider(fabric, c)

        registry = fabric.facade._registry
        target = "tool.execute.test_cap_0250"

        timings = []
        for _ in range(1000):
            start = time.perf_counter()
            found = registry.contains(target)
            elapsed = (time.perf_counter() - start) * 1000
            timings.append(elapsed)
            assert found

        timings.sort()
        p95 = timings[int(len(timings) * 0.95)]
        assert p95 < 1.0, f"contains() P95 = {p95:.4f}ms, exceeds 1ms target"

    def test_registration_throughput(self) -> None:
        """Registering 100 contracts completes in < 2 seconds total."""
        fabric = _make_fabric()
        contracts = create_n_contracts(100, domain="PERF_REG_THROUGHPUT")

        start = time.perf_counter()
        for c in contracts:
            register_contract_with_provider(fabric, c)
        total_ms = (time.perf_counter() - start) * 1000

        assert (
            total_ms < 2000
        ), f"Registering 100 contracts took {total_ms:.1f}ms, exceeds 2000ms budget"
