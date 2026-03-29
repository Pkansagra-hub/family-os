"""
Epic 6.3.5 -- Test safety band enforcement end-to-end (integration).

Verify that FAB-06 safety band access control is enforced through the
full fabric.execute() pipeline:
  request(safety_band) -> Resolver -> PolicyEngine -> SecurityContext.check_band()
  -> user_band >= capability.safety_band_min -> allow / reject (access_denied)

Band ordering: GREEN(0) < AMBER(1) < RED(2) < CRISIS(3).
  - GREEN user can access GREEN capabilities only.
  - AMBER user can access GREEN + AMBER.
  - RED user can access GREEN + AMBER + RED.
  - CRISIS user can access all.

MANDATORY per plan:
  1. ALL executions through fabric.execute() -- NEVER direct provider access.
  2. Uses FabricFactory.create_for_testing() with event capture.
  3. Real adapters only (test adapters are real, not mocks).
  4. Verify events via event adapter capture mode.
  5. Registers custom contracts with different safety_band_min values.

References:
  - fabric-implementation-plan.md Epic 6.3, Issue 6.3.5
  - FAB-06 (Safety band enforcement)
  - No-Mock Testing Strategy (lines 1181-1300 of plan)
"""

from __future__ import annotations

from pathlib import Path

from k1.fabric.events.fabric_events import (
    TOPIC_CAPABILITY_COMPLETED,
    TOPIC_CAPABILITY_FAILED,
    TOPIC_CAPABILITY_INVOKED,
)
from k1.fabric.fabric import Fabric
from k1.fabric.factory import FabricFactory
from k1.fabric.types import (
    CapabilityContract,
    CapabilityRequest,
    InputSpec,
    SafetyBand,
    Tier,
)
from tests.k1.fabric.helpers import (
    assert_capability_result_success,
    register_contract_with_provider,
)

# ---------------------------------------------------------------------------
# Fixtures directory (for auto-loaded contracts like restaurant_booking)
# ---------------------------------------------------------------------------

FIXTURES_DIR = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Contract builders with specific safety bands
# ---------------------------------------------------------------------------


def _make_band_contract(
    name: str,
    safety_band_min: str,
    *,
    provider_type: str = "MCP",
    provider_id: str = "",
) -> CapabilityContract:
    """Build a CapabilityContract with a specific safety_band_min."""
    pid = provider_id or f"provider-{name.replace('.', '-')}"
    return CapabilityContract(
        name=name,
        version="1.0.0",
        domain=["SAFETY_TEST"],
        description=f"Safety band test: {safety_band_min}",
        capabilities=["test_action"],
        limitations=[],
        required_inputs=[
            InputSpec(name="input_a", type="STRING", description="Test input"),
        ],
        output={"type": "object"},
        provider_type=provider_type,
        provider_id=pid,
        safety_band_min=safety_band_min,
    )


def _band_request(
    capability_name: str,
    user_band: str = SafetyBand.GREEN.value,
    *,
    caller: str = "test-safety",
) -> CapabilityRequest:
    """Build a CapabilityRequest with a specific user safety_band."""
    return CapabilityRequest(
        capability_name=capability_name,
        params={"input_a": "test"},
        tier=Tier.LOW.value,
        safety_band=user_band,
        caller=caller,
    )


def _make_fabric() -> Fabric:
    """Create a Fabric with event capture for integration tests."""
    return FabricFactory.create_for_testing(
        capture_events=True,
        contracts_dir=str(FIXTURES_DIR),
    )


def _register_band_contracts(fabric: Fabric) -> dict[str, str]:
    """
    Register contracts at GREEN, AMBER, RED, and CRISIS band levels.

    Returns mapping of band -> capability_name for test use.
    """
    bands = {
        SafetyBand.GREEN.value: "tool.execute.band_green",
        SafetyBand.AMBER.value: "tool.execute.band_amber",
        SafetyBand.RED.value: "tool.execute.band_red",
        SafetyBand.CRISIS.value: "tool.execute.band_crisis",
    }
    for band, cap_name in bands.items():
        contract = _make_band_contract(name=cap_name, safety_band_min=band)
        register_contract_with_provider(fabric, contract)

    return bands


# =========================================================================
# 6.3.5a -- GREEN user access control
# =========================================================================


class TestGreenUserAccess:
    """
    GREEN user (lowest band) can only access GREEN capabilities.
    """

    async def test_green_user_executes_green_capability(self) -> None:
        """GREEN user can execute a GREEN capability successfully."""
        fabric = _make_fabric()
        bands = _register_band_contracts(fabric)

        request = _band_request(bands[SafetyBand.GREEN.value], SafetyBand.GREEN.value)
        result = await fabric.execute(request)

        assert_capability_result_success(result)

    async def test_green_user_rejected_by_amber_capability(self) -> None:
        """GREEN user is rejected when accessing AMBER capability."""
        fabric = _make_fabric()
        bands = _register_band_contracts(fabric)

        request = _band_request(bands[SafetyBand.AMBER.value], SafetyBand.GREEN.value)
        result = await fabric.execute(request)

        assert result.success is False
        assert result.error is not None
        # Resolution fails because SecurityContext rejects the band
        assert result.error.code in ("access_denied", "resolution_failed")

    async def test_green_user_rejected_by_red_capability(self) -> None:
        """GREEN user is rejected when accessing RED capability."""
        fabric = _make_fabric()
        bands = _register_band_contracts(fabric)

        request = _band_request(bands[SafetyBand.RED.value], SafetyBand.GREEN.value)
        result = await fabric.execute(request)

        assert result.success is False
        assert result.error is not None
        assert result.error.code in ("access_denied", "resolution_failed")

    async def test_green_user_rejected_by_crisis_capability(self) -> None:
        """GREEN user is rejected when accessing CRISIS capability."""
        fabric = _make_fabric()
        bands = _register_band_contracts(fabric)

        request = _band_request(bands[SafetyBand.CRISIS.value], SafetyBand.GREEN.value)
        result = await fabric.execute(request)

        assert result.success is False
        assert result.error is not None
        assert result.error.code in ("access_denied", "resolution_failed")


# =========================================================================
# 6.3.5b -- AMBER user access control
# =========================================================================


class TestAmberUserAccess:
    """
    AMBER user can access GREEN and AMBER capabilities.
    """

    async def test_amber_user_executes_green_capability(self) -> None:
        """AMBER user can execute GREEN capability (band >= min)."""
        fabric = _make_fabric()
        bands = _register_band_contracts(fabric)

        request = _band_request(bands[SafetyBand.GREEN.value], SafetyBand.AMBER.value)
        result = await fabric.execute(request)

        assert_capability_result_success(result)

    async def test_amber_user_executes_amber_capability(self) -> None:
        """AMBER user can execute AMBER capability (band == min)."""
        fabric = _make_fabric()
        bands = _register_band_contracts(fabric)

        request = _band_request(bands[SafetyBand.AMBER.value], SafetyBand.AMBER.value)
        result = await fabric.execute(request)

        assert_capability_result_success(result)

    async def test_amber_user_rejected_by_red_capability(self) -> None:
        """AMBER user is rejected when accessing RED capability."""
        fabric = _make_fabric()
        bands = _register_band_contracts(fabric)

        request = _band_request(bands[SafetyBand.RED.value], SafetyBand.AMBER.value)
        result = await fabric.execute(request)

        assert result.success is False
        assert result.error is not None
        assert result.error.code in ("access_denied", "resolution_failed")

    async def test_amber_user_rejected_by_crisis_capability(self) -> None:
        """AMBER user is rejected when accessing CRISIS capability."""
        fabric = _make_fabric()
        bands = _register_band_contracts(fabric)

        request = _band_request(bands[SafetyBand.CRISIS.value], SafetyBand.AMBER.value)
        result = await fabric.execute(request)

        assert result.success is False
        assert result.error is not None
        assert result.error.code in ("access_denied", "resolution_failed")


# =========================================================================
# 6.3.5c -- RED user access control
# =========================================================================


class TestRedUserAccess:
    """
    RED user can access GREEN, AMBER, and RED capabilities.
    """

    async def test_red_user_executes_green_capability(self) -> None:
        """RED user can execute GREEN capability."""
        fabric = _make_fabric()
        bands = _register_band_contracts(fabric)

        request = _band_request(bands[SafetyBand.GREEN.value], SafetyBand.RED.value)
        result = await fabric.execute(request)

        assert_capability_result_success(result)

    async def test_red_user_executes_amber_capability(self) -> None:
        """RED user can execute AMBER capability."""
        fabric = _make_fabric()
        bands = _register_band_contracts(fabric)

        request = _band_request(bands[SafetyBand.AMBER.value], SafetyBand.RED.value)
        result = await fabric.execute(request)

        assert_capability_result_success(result)

    async def test_red_user_executes_red_capability(self) -> None:
        """RED user can execute RED capability (band == min)."""
        fabric = _make_fabric()
        bands = _register_band_contracts(fabric)

        request = _band_request(bands[SafetyBand.RED.value], SafetyBand.RED.value)
        result = await fabric.execute(request)

        assert_capability_result_success(result)

    async def test_red_user_rejected_by_crisis_capability(self) -> None:
        """RED user is rejected when accessing CRISIS capability."""
        fabric = _make_fabric()
        bands = _register_band_contracts(fabric)

        request = _band_request(bands[SafetyBand.CRISIS.value], SafetyBand.RED.value)
        result = await fabric.execute(request)

        assert result.success is False
        assert result.error is not None
        assert result.error.code in ("access_denied", "resolution_failed")


# =========================================================================
# 6.3.5d -- CRISIS user access control
# =========================================================================


class TestCrisisUserAccess:
    """
    CRISIS user (highest band) can access ALL capabilities.
    """

    async def test_crisis_user_executes_green_capability(self) -> None:
        """CRISIS user can execute GREEN capability."""
        fabric = _make_fabric()
        bands = _register_band_contracts(fabric)

        request = _band_request(bands[SafetyBand.GREEN.value], SafetyBand.CRISIS.value)
        result = await fabric.execute(request)

        assert_capability_result_success(result)

    async def test_crisis_user_executes_amber_capability(self) -> None:
        """CRISIS user can execute AMBER capability."""
        fabric = _make_fabric()
        bands = _register_band_contracts(fabric)

        request = _band_request(bands[SafetyBand.AMBER.value], SafetyBand.CRISIS.value)
        result = await fabric.execute(request)

        assert_capability_result_success(result)

    async def test_crisis_user_executes_red_capability(self) -> None:
        """CRISIS user can execute RED capability."""
        fabric = _make_fabric()
        bands = _register_band_contracts(fabric)

        request = _band_request(bands[SafetyBand.RED.value], SafetyBand.CRISIS.value)
        result = await fabric.execute(request)

        assert_capability_result_success(result)

    async def test_crisis_user_executes_crisis_capability(self) -> None:
        """CRISIS user can execute CRISIS capability (band == min)."""
        fabric = _make_fabric()
        bands = _register_band_contracts(fabric)

        request = _band_request(bands[SafetyBand.CRISIS.value], SafetyBand.CRISIS.value)
        result = await fabric.execute(request)

        assert_capability_result_success(result)


# =========================================================================
# 6.3.5e -- Event emission for band enforcement
# =========================================================================


class TestSafetyBandEvents:
    """
    Verify event emission during safety band enforcement.
    """

    async def test_allowed_access_emits_invoked_and_completed(self) -> None:
        """Successful execution emits both invoked and completed events."""
        fabric = _make_fabric()
        bands = _register_band_contracts(fabric)

        request = _band_request(bands[SafetyBand.GREEN.value], SafetyBand.GREEN.value)
        result = await fabric.execute(request)

        assert result.success is True
        event_adapter = fabric.event_port
        invoked = event_adapter.get_captured(topic=TOPIC_CAPABILITY_INVOKED)
        completed = event_adapter.get_captured(topic=TOPIC_CAPABILITY_COMPLETED)
        assert len(invoked) >= 1
        assert len(completed) >= 1

    async def test_denied_access_emits_invoked_event(self) -> None:
        """Rejected execution still emits invoked event."""
        fabric = _make_fabric()
        bands = _register_band_contracts(fabric)

        request = _band_request(bands[SafetyBand.RED.value], SafetyBand.GREEN.value)
        result = await fabric.execute(request)

        assert result.success is False
        event_adapter = fabric.event_port
        invoked = event_adapter.get_captured(topic=TOPIC_CAPABILITY_INVOKED)
        assert len(invoked) >= 1

    async def test_denied_access_emits_learning_signal(self) -> None:
        """Rejected execution emits failed event for feedback loop.

        Note: Band rejection occurs at resolution (policy evaluation),
        which emits a 'failed' event but NOT a 'learning_signal'.
        The learning_signal is only emitted after execution (step 9).
        """
        fabric = _make_fabric()
        bands = _register_band_contracts(fabric)

        request = _band_request(bands[SafetyBand.AMBER.value], SafetyBand.GREEN.value)
        result = await fabric.execute(request)

        assert result.success is False
        event_adapter = fabric.event_port
        # Band rejection happens at resolution, which emits 'failed' (not 'learning_signal')
        failed = event_adapter.get_captured(topic=TOPIC_CAPABILITY_FAILED)
        assert len(failed) >= 1


# =========================================================================
# 6.3.5f -- Edge cases
# =========================================================================


class TestSafetyBandEdgeCases:
    """
    Edge cases and boundary conditions for safety band enforcement.
    """

    async def test_default_band_is_green(self) -> None:
        """CapabilityRequest defaults to GREEN safety_band."""
        request = CapabilityRequest(
            capability_name="tool.execute.some_tool",
            params={"input_a": "test"},
        )
        assert request.safety_band == SafetyBand.GREEN.value

    async def test_contract_default_band_min_is_green(self) -> None:
        """CapabilityContract defaults to GREEN safety_band_min."""
        contract = CapabilityContract(
            name="tool.execute.default_band",
            version="1.0.0",
            domain=["TEST"],
            description="Default band test",
            capabilities=["test"],
            required_inputs=[],
            output={"type": "object"},
            provider_type="MCP",
            provider_id="test-default-band",
        )
        assert contract.safety_band_min == SafetyBand.GREEN.value

    async def test_same_band_always_allowed(self) -> None:
        """When user_band == capability_band_min, access is always allowed."""
        fabric = _make_fabric()
        for band in [SafetyBand.GREEN, SafetyBand.AMBER, SafetyBand.RED, SafetyBand.CRISIS]:
            contract = _make_band_contract(
                name=f"tool.execute.eq_band_{band.value.lower()}",
                safety_band_min=band.value,
            )
            register_contract_with_provider(fabric, contract)

            request = _band_request(contract.name, band.value)
            result = await fabric.execute(request)
            assert_capability_result_success(result)

    async def test_band_ordering_is_strictly_hierarchical(self) -> None:
        """Lower bands cannot access higher band capabilities."""
        fabric = _make_fabric()
        # Register a RED-only capability
        contract = _make_band_contract(
            name="tool.execute.red_only",
            safety_band_min=SafetyBand.RED.value,
        )
        register_contract_with_provider(fabric, contract)

        # GREEN cannot access RED
        result_green = await fabric.execute(
            _band_request("tool.execute.red_only", SafetyBand.GREEN.value)
        )
        assert result_green.success is False

        # AMBER cannot access RED
        result_amber = await fabric.execute(
            _band_request("tool.execute.red_only", SafetyBand.AMBER.value)
        )
        assert result_amber.success is False

        # RED can access RED
        result_red = await fabric.execute(
            _band_request("tool.execute.red_only", SafetyBand.RED.value)
        )
        assert_capability_result_success(result_red)

        # CRISIS can access RED
        result_crisis = await fabric.execute(
            _band_request("tool.execute.red_only", SafetyBand.CRISIS.value)
        )
        assert_capability_result_success(result_crisis)

    async def test_fixture_restaurant_booking_is_green(self) -> None:
        """Pre-loaded restaurant_booking fixture has GREEN band (accessible by all)."""
        fabric = _make_fabric()
        request = _band_request(
            "tool.execute.restaurant_booking",
            SafetyBand.GREEN.value,
        )
        result = await fabric.execute(request)
        assert_capability_result_success(result)
