"""Tests for PlannerFactory (Epic 6.3).

Covers the 4 creation modes and all validation paths:
- create_standalone: zero-dep test shortcut (all test adapters)
- create_for_testing: test adapter defaults + overrides
- create_with_ports: explicit typed port injection
- create_production: production wiring with 7 typed ports
- Port validation: missing, protocol mismatch, duplicates
- Config validation: bounds checking
- Error types: correct exception classes with metadata

Test adapters satisfy @runtime_checkable Protocols so the factory
accepts them as valid ports. Tests do NOT call agent.start() (the
dequeue loop blocks forever).
"""

from __future__ import annotations

from typing import Any, Dict

import pytest

from k1.planner.config import PlannerConfig
from k1.planner.factory import PlannerFactory
from k1.planner.planner_agent import PlannerAgent
from k1.planner.types import (
    DuplicatePortError,
    HealthStatus,
    InvalidConfigError,
    InvalidPortError,
    MissingPortError,
)
from tests.k1.planner.adapters import (
    TestBridgeAdapter,
    TestDeltaAdapter,
    TestEventAdapter,
    TestFabricRetrievalAdapter,
    TestLLMAdapter,
    TestMailboxAdapter,
    TestStateReadAdapter,
)

# =========================================================================
# Fixtures
# =========================================================================


@pytest.fixture
def all_ports() -> Dict[str, Any]:
    """All 7 test adapters keyed by factory slot name."""
    return {
        "llm_port": TestLLMAdapter(),
        "fabric_port": TestFabricRetrievalAdapter(),
        "state_port": TestStateReadAdapter(),
        "bridge_port": TestBridgeAdapter(),
        "delta_port": TestDeltaAdapter(),
        "event_port": TestEventAdapter(),
        "mailbox_port": TestMailboxAdapter(),
    }


@pytest.fixture
def default_config() -> PlannerConfig:
    """Default PlannerConfig with valid bounds."""
    return PlannerConfig()


# =========================================================================
# create_standalone -- zero-dep test shortcut
# =========================================================================


class TestCreateStandalone:
    """Tests for PlannerFactory.create_standalone() -- zero-dep shortcut."""

    @pytest.mark.asyncio
    async def test_returns_planner_agent(self) -> None:
        """Zero-arg standalone creation returns a PlannerAgent instance."""
        agent = await PlannerFactory.create_standalone()
        assert isinstance(agent, PlannerAgent)

    @pytest.mark.asyncio
    async def test_not_running_before_start(self) -> None:
        """Agent is wired but not started -- running is False."""
        agent = await PlannerFactory.create_standalone()
        assert agent.ready() is False

    @pytest.mark.asyncio
    async def test_default_config(self) -> None:
        """Default PlannerConfig is used when none provided."""
        agent = await PlannerFactory.create_standalone()
        assert agent.config == PlannerConfig()

    @pytest.mark.asyncio
    async def test_custom_config(self) -> None:
        """Custom config is propagated to the agent."""
        config = PlannerConfig(pipeline_timeout_ms=30_000)
        agent = await PlannerFactory.create_standalone(config=config)
        assert agent.config.pipeline_timeout_ms == 30_000

    @pytest.mark.asyncio
    async def test_health_unhealthy_before_start(self) -> None:
        """Agent health is UNHEALTHY before start() is called."""
        agent = await PlannerFactory.create_standalone()
        health = agent.health()
        assert isinstance(health, HealthStatus)
        assert health.status == "UNHEALTHY"


# =========================================================================
# create_production -- production wiring (kernel Phase 5)
# =========================================================================


class TestCreateProduction:
    """Tests for PlannerFactory.create_production()."""

    @pytest.mark.asyncio
    async def test_returns_planner_agent(self, all_ports: Dict[str, Any]) -> None:
        """Production creation returns a PlannerAgent instance."""
        agent = await PlannerFactory.create_production(**all_ports)
        assert isinstance(agent, PlannerAgent)

    @pytest.mark.asyncio
    async def test_agent_not_running_before_start(self, all_ports: Dict[str, Any]) -> None:
        """Agent is wired but not started -- running is False."""
        agent = await PlannerFactory.create_production(**all_ports)
        assert agent.ready() is False
        assert agent.running is False

    @pytest.mark.asyncio
    async def test_health_unhealthy_before_start(self, all_ports: Dict[str, Any]) -> None:
        """Agent health is UNHEALTHY before start() is called."""
        agent = await PlannerFactory.create_production(**all_ports)
        health = agent.health()
        assert isinstance(health, HealthStatus)
        assert health.status == "UNHEALTHY"

    @pytest.mark.asyncio
    async def test_custom_config(self, all_ports: Dict[str, Any]) -> None:
        """Custom config is propagated to the agent."""
        config = PlannerConfig(pipeline_timeout_ms=30_000, max_hil_rounds=1)
        agent = await PlannerFactory.create_production(**all_ports, config=config)
        assert agent.config.pipeline_timeout_ms == 30_000
        assert agent.config.max_hil_rounds == 1

    @pytest.mark.asyncio
    async def test_default_config_when_none(self, all_ports: Dict[str, Any]) -> None:
        """When config=None, default PlannerConfig is used."""
        agent = await PlannerFactory.create_production(**all_ports, config=None)
        assert agent.config == PlannerConfig()

    @pytest.mark.asyncio
    async def test_ports_wired_correctly(self, all_ports: Dict[str, Any]) -> None:
        """Agent receives the correct mailbox port."""
        agent = await PlannerFactory.create_production(**all_ports)
        assert agent.get_mailbox() is all_ports["mailbox_port"]

    @pytest.mark.asyncio
    async def test_event_port_wired(self, all_ports: Dict[str, Any]) -> None:
        """Agent receives the correct event port."""
        agent = await PlannerFactory.create_production(**all_ports)
        assert agent.event_port is all_ports["event_port"]

    @pytest.mark.asyncio
    async def test_pipeline_wired(self, all_ports: Dict[str, Any]) -> None:
        """Agent has a non-None pipeline controller."""
        agent = await PlannerFactory.create_production(**all_ports)
        assert agent.pipeline is not None


# =========================================================================
# create_for_testing -- happy path
# =========================================================================


class TestCreateForTesting:
    """Tests for PlannerFactory.create_for_testing()."""

    @pytest.mark.asyncio
    async def test_returns_agent_and_adapters(self) -> None:
        """Returns (PlannerAgent, dict) tuple."""
        result = await PlannerFactory.create_for_testing()
        assert isinstance(result, tuple)
        assert len(result) == 2
        agent, adapters = result
        assert isinstance(agent, PlannerAgent)
        assert isinstance(adapters, dict)

    @pytest.mark.asyncio
    async def test_all_7_adapters_returned(self) -> None:
        """Adapters dict contains all 7 port slots."""
        _, adapters = await PlannerFactory.create_for_testing()
        expected_keys = {
            "llm_port",
            "fabric_port",
            "state_port",
            "bridge_port",
            "delta_port",
            "event_port",
            "mailbox_port",
        }
        assert set(adapters.keys()) == expected_keys

    @pytest.mark.asyncio
    async def test_default_adapters_are_test_types(self) -> None:
        """Default adapters are test adapter instances."""
        _, adapters = await PlannerFactory.create_for_testing()
        assert isinstance(adapters["llm_port"], TestLLMAdapter)
        assert isinstance(adapters["fabric_port"], TestFabricRetrievalAdapter)
        assert isinstance(adapters["state_port"], TestStateReadAdapter)
        assert isinstance(adapters["bridge_port"], TestBridgeAdapter)
        assert isinstance(adapters["delta_port"], TestDeltaAdapter)
        assert isinstance(adapters["event_port"], TestEventAdapter)
        assert isinstance(adapters["mailbox_port"], TestMailboxAdapter)

    @pytest.mark.asyncio
    async def test_override_single_port(self) -> None:
        """Single port override replaces the default adapter."""
        custom_llm = TestLLMAdapter(latency_ms=100)
        agent, adapters = await PlannerFactory.create_for_testing(
            llm_port=custom_llm,
        )
        assert adapters["llm_port"] is custom_llm

    @pytest.mark.asyncio
    async def test_override_multiple_ports(self) -> None:
        """Multiple port overrides work simultaneously."""
        custom_llm = TestLLMAdapter(latency_ms=100)
        custom_event = TestEventAdapter()
        _, adapters = await PlannerFactory.create_for_testing(
            llm_port=custom_llm,
            event_port=custom_event,
        )
        assert adapters["llm_port"] is custom_llm
        assert adapters["event_port"] is custom_event

    @pytest.mark.asyncio
    async def test_invalid_override_key_raises(self) -> None:
        """Unknown override key raises InvalidPortError."""
        with pytest.raises(InvalidPortError, match="Unknown port slot"):
            await PlannerFactory.create_for_testing(bogus_port=object())

    @pytest.mark.asyncio
    async def test_custom_config(self) -> None:
        """Custom config is propagated."""
        config = PlannerConfig(max_tool_calls_per_plan=3)
        agent, _ = await PlannerFactory.create_for_testing(config=config)
        assert agent.config.max_tool_calls_per_plan == 3


# =========================================================================
# create_with_ports -- happy path
# =========================================================================


class TestCreateWithPorts:
    """Tests for PlannerFactory.create_with_ports() -- typed keyword args."""

    @pytest.mark.asyncio
    async def test_returns_planner_agent(self, all_ports: Dict[str, Any]) -> None:
        """Returns a PlannerAgent instance."""
        agent = await PlannerFactory.create_with_ports(**all_ports)
        assert isinstance(agent, PlannerAgent)

    @pytest.mark.asyncio
    async def test_custom_config(self, all_ports: Dict[str, Any]) -> None:
        """Custom config is propagated."""
        config = PlannerConfig(sketch_timeout_ms=3_000)
        agent = await PlannerFactory.create_with_ports(**all_ports, config=config)
        assert agent.config.sketch_timeout_ms == 3_000

    @pytest.mark.asyncio
    async def test_missing_kwarg_raises_type_error(self) -> None:
        """Missing keyword arg raises TypeError (Python enforcement)."""
        with pytest.raises(TypeError):
            await PlannerFactory.create_with_ports(
                llm_port=TestLLMAdapter(),
                fabric_port=TestFabricRetrievalAdapter(),
            )


# =========================================================================
# Port validation
# =========================================================================


class TestPortValidation:
    """Tests for port validation across all creation modes."""

    @pytest.mark.asyncio
    async def test_none_port_raises_missing(self, all_ports: Dict[str, Any]) -> None:
        """None port value raises MissingPortError."""
        all_ports["llm_port"] = None
        with pytest.raises(MissingPortError) as exc_info:
            await PlannerFactory.create_production(**all_ports)
        assert exc_info.value.port_name == "llm_port"

    @pytest.mark.asyncio
    async def test_invalid_protocol_raises(self, all_ports: Dict[str, Any]) -> None:
        """Object not satisfying Protocol raises InvalidPortError."""
        all_ports["llm_port"] = "not_an_llm_port"
        with pytest.raises(InvalidPortError) as exc_info:
            await PlannerFactory.create_production(**all_ports)
        assert exc_info.value.port_name == "llm_port"
        assert "ILLMPort" in exc_info.value.expected_protocol

    @pytest.mark.asyncio
    async def test_duplicate_port_raises(self, all_ports: Dict[str, Any]) -> None:
        """Same object in two slots raises DuplicatePortError."""
        shared = TestEventAdapter()
        all_ports["event_port"] = shared
        all_ports["delta_port"] = shared  # Same object, wrong protocol
        # This may raise InvalidPortError first since TestEventAdapter
        # doesn't satisfy IDeltaEmitPort. If it does satisfy both,
        # DuplicatePortError is raised.
        with pytest.raises((InvalidPortError, DuplicatePortError)):
            await PlannerFactory.create_production(**all_ports)

    @pytest.mark.asyncio
    async def test_each_port_checked_for_none(self) -> None:
        """Each of the 7 port slots is individually checked for None."""
        slot_names = [
            "llm_port",
            "fabric_port",
            "state_port",
            "bridge_port",
            "delta_port",
            "event_port",
            "mailbox_port",
        ]
        for slot in slot_names:
            ports = {
                "llm_port": TestLLMAdapter(),
                "fabric_port": TestFabricRetrievalAdapter(),
                "state_port": TestStateReadAdapter(),
                "bridge_port": TestBridgeAdapter(),
                "delta_port": TestDeltaAdapter(),
                "event_port": TestEventAdapter(),
                "mailbox_port": TestMailboxAdapter(),
            }
            ports[slot] = None
            with pytest.raises(MissingPortError) as exc_info:
                await PlannerFactory.create_production(**ports)
            assert slot in exc_info.value.port_name, f"Expected MissingPortError for '{slot}'"


# =========================================================================
# Config validation
# =========================================================================


class TestConfigValidation:
    """Tests for config bounds checking.

    PlannerConfig's __post_init__ rejects invalid values at construction
    time. The factory's _validate_config is defense-in-depth for configs
    constructed via deserialization or bypass. We test both layers.
    """

    def test_planner_config_rejects_zero_timeout(self) -> None:
        """PlannerConfig itself rejects pipeline_timeout_ms=0."""
        with pytest.raises(ValueError, match="pipeline_timeout_ms"):
            PlannerConfig(pipeline_timeout_ms=0)

    def test_planner_config_rejects_zero_mailbox(self) -> None:
        """PlannerConfig itself rejects mailbox_max_depth=0."""
        with pytest.raises(ValueError, match="mailbox_max_depth"):
            PlannerConfig(mailbox_max_depth=0)

    def test_planner_config_rejects_zero_tool_budget(self) -> None:
        """PlannerConfig itself rejects max_tool_calls_per_plan=0."""
        with pytest.raises(ValueError, match="max_tool_calls_per_plan"):
            PlannerConfig(max_tool_calls_per_plan=0)

    def test_planner_config_rejects_negative_hil(self) -> None:
        """PlannerConfig itself rejects max_hil_rounds=-1."""
        with pytest.raises(ValueError, match="max_hil_rounds"):
            PlannerConfig(max_hil_rounds=-1)

    @pytest.mark.asyncio
    async def test_factory_validate_config_defense_in_depth(self) -> None:
        """Factory's _validate_config catches bypass-constructed invalid config.

        Uses object.__new__ to create a PlannerConfig without __post_init__,
        then sets an invalid field to exercise the factory's validation.
        """
        # Bypass __post_init__ to create a config with invalid value
        bad_config = object.__new__(PlannerConfig)
        # Copy all defaults first
        defaults = PlannerConfig()
        for field_name in defaults.__dataclass_fields__:
            object.__setattr__(bad_config, field_name, getattr(defaults, field_name))
        # Set one invalid field
        object.__setattr__(bad_config, "pipeline_timeout_ms", 0)

        all_ports = {
            "llm_port": TestLLMAdapter(),
            "fabric_port": TestFabricRetrievalAdapter(),
            "state_port": TestStateReadAdapter(),
            "bridge_port": TestBridgeAdapter(),
            "delta_port": TestDeltaAdapter(),
            "event_port": TestEventAdapter(),
            "mailbox_port": TestMailboxAdapter(),
        }
        with pytest.raises(InvalidConfigError) as exc_info:
            await PlannerFactory.create_production(**all_ports, config=bad_config)
        assert exc_info.value.field_name == "pipeline_timeout_ms"

    @pytest.mark.asyncio
    async def test_factory_validate_config_mailbox_depth(self) -> None:
        """Factory's _validate_config catches mailbox_max_depth=0."""
        bad_config = object.__new__(PlannerConfig)
        defaults = PlannerConfig()
        for field_name in defaults.__dataclass_fields__:
            object.__setattr__(bad_config, field_name, getattr(defaults, field_name))
        object.__setattr__(bad_config, "mailbox_max_depth", 0)

        all_ports = {
            "llm_port": TestLLMAdapter(),
            "fabric_port": TestFabricRetrievalAdapter(),
            "state_port": TestStateReadAdapter(),
            "bridge_port": TestBridgeAdapter(),
            "delta_port": TestDeltaAdapter(),
            "event_port": TestEventAdapter(),
            "mailbox_port": TestMailboxAdapter(),
        }
        with pytest.raises(InvalidConfigError) as exc_info:
            await PlannerFactory.create_production(**all_ports, config=bad_config)
        assert exc_info.value.field_name == "mailbox_max_depth"

    @pytest.mark.asyncio
    async def test_valid_config_passes(self, all_ports: Dict[str, Any]) -> None:
        """Default config passes validation without errors."""
        agent = await PlannerFactory.create_production(**all_ports)
        assert agent is not None


# =========================================================================
# Error type metadata
# =========================================================================


class TestErrorMetadata:
    """Tests that factory errors carry correct metadata."""

    def test_missing_port_error_has_port_name(self) -> None:
        """MissingPortError carries port_name."""
        err = MissingPortError("test", port_name="llm_port")
        assert err.port_name == "llm_port"

    def test_invalid_port_error_has_details(self) -> None:
        """InvalidPortError carries port_name, expected_protocol, actual_type."""
        err = InvalidPortError(
            "test",
            port_name="llm_port",
            expected_protocol="k1.planner.ports.ILLMPort",
            actual_type="str",
        )
        assert err.port_name == "llm_port"
        assert err.expected_protocol == "k1.planner.ports.ILLMPort"
        assert err.actual_type == "str"

    def test_duplicate_port_error_has_slots(self) -> None:
        """DuplicatePortError carries port_a and port_b."""
        err = DuplicatePortError("test", port_a="event_port", port_b="delta_port")
        assert err.port_a == "event_port"
        assert err.port_b == "delta_port"

    def test_invalid_config_error_has_details(self) -> None:
        """InvalidConfigError carries field_name, value, constraint."""
        err = InvalidConfigError(
            "test",
            field_name="pipeline_timeout_ms",
            value=0,
            constraint="> 0",
        )
        assert err.field_name == "pipeline_timeout_ms"
        assert err.value == 0
        assert err.constraint == "> 0"


# =========================================================================
# Instantiation guard
# =========================================================================


class TestInstantiationGuard:
    """PlannerFactory must not be instantiated."""

    def test_instantiation_raises_type_error(self) -> None:
        """Direct instantiation raises TypeError."""
        with pytest.raises(TypeError, match="must not be instantiated"):
            PlannerFactory()


# =========================================================================
# Agent convenience methods
# =========================================================================


class TestAgentMethods:
    """Tests for ready(), health(), get_mailbox() added for factory."""

    @pytest.mark.asyncio
    async def test_get_mailbox_returns_injected(self, all_ports: Dict[str, Any]) -> None:
        """get_mailbox() returns the injected mailbox port."""
        agent = await PlannerFactory.create_production(**all_ports)
        assert agent.get_mailbox() is all_ports["mailbox_port"]

    @pytest.mark.asyncio
    async def test_ready_false_before_start(self, all_ports: Dict[str, Any]) -> None:
        """ready() is False before start() is called."""
        agent = await PlannerFactory.create_production(**all_ports)
        assert agent.ready() is False

    @pytest.mark.asyncio
    async def test_health_unhealthy_before_start(self, all_ports: Dict[str, Any]) -> None:
        """health() returns UNHEALTHY before start()."""
        agent = await PlannerFactory.create_production(**all_ports)
        health = agent.health()
        assert health.status == "UNHEALTHY"
        assert health.details["running"] is False

    def test_health_status_frozen(self) -> None:
        """HealthStatus is a frozen dataclass."""
        hs = HealthStatus(status="HEALTHY", details={"running": True})
        with pytest.raises(AttributeError):
            hs.status = "DEGRADED"  # type: ignore[misc]
