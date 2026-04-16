"""
tests.k1.memory_writer.test_factory -- 18 tests for MemoryWriterFactory.

Covers: create, port validation, invariant validation, wiring.
"""

from __future__ import annotations

from typing import Any, Callable, Coroutine, Dict, FrozenSet, List, Optional
from unittest.mock import patch

import pytest

from k1.memory_writer.config import MWConfig
from k1.memory_writer.factory import MemoryWriterFactory
from k1.memory_writer.health.circuit_breaker import CircuitBreaker
from k1.memory_writer.invariants import InvariantViolation
from k1.memory_writer.service import MemoryWriterService
from k1.memory_writer.types import ChatResponse, HealthStatus, Subscription

# ---------------------------------------------------------------------------
# Fake port adapters (must pass isinstance checks for runtime_checkable)
# ---------------------------------------------------------------------------


class FakeSessionReadPort:
    async def snapshot(self, sections: List[str]) -> Dict[str, Any]:
        return {}

    async def read_section(self, name: str) -> Optional[Dict[str, Any]]:
        return None

    async def list_sections(self) -> FrozenSet[str]:
        return frozenset()

    async def snapshot_all(self, exclude: FrozenSet[str] = frozenset()) -> Dict[str, Any]:
        return {}


class FakeModelHubPort:
    async def chat(
        self,
        messages: List[Dict[str, str]],
        budget_tokens: int,
        model_hint: str,
    ) -> ChatResponse:
        return ChatResponse(content="[]", total_tokens=10)


class FakeBridgeCommandPort:
    async def submit(self, topic: str, schema_uri: str, body: Dict) -> None:
        pass

    async def submit_batch(self, envelopes: List[Dict]) -> None:
        pass


class FakeEventSubscriptionPort:
    async def subscribe(
        self,
        topic: str,
        handler: Callable[..., Coroutine[Any, Any, None]],
    ) -> Subscription:
        return Subscription(subscription_id="sub-1", topic=topic)

    async def unsubscribe(self, subscription_id: str) -> None:
        pass

    async def publish(self, topic: str, payload: dict) -> None:
        pass


class FakeHealthPort:
    async def is_ready(self) -> bool:
        return True

    async def health_check(self) -> HealthStatus:
        return HealthStatus(is_healthy=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _all_ports() -> dict:
    return {
        "session_read_port": FakeSessionReadPort(),
        "model_hub_port": FakeModelHubPort(),
        "bridge_command_port": FakeBridgeCommandPort(),
        "event_subscription_port": FakeEventSubscriptionPort(),
        "health_port": FakeHealthPort(),
    }


def _create(**overrides: Any) -> MemoryWriterService:
    ports = _all_ports()
    ports.update(overrides)
    with patch("k1.memory_writer.factory.validate_init_invariants"):
        return MemoryWriterFactory.create(**ports)


# ===========================================================================
# TestFactoryCreate — 5 tests
# ===========================================================================


class TestFactoryCreate:
    """Happy path factory creation."""

    def test_create_returns_service(self) -> None:
        svc = _create()
        assert isinstance(svc, MemoryWriterService)

    def test_create_with_default_config(self) -> None:
        svc = _create(config=None)
        assert isinstance(svc, MemoryWriterService)

    def test_create_with_custom_config(self) -> None:
        cfg = MWConfig(batch_window_ms=500)
        svc = _create(config=cfg)
        assert isinstance(svc, MemoryWriterService)

    def test_service_not_started_after_create(self) -> None:
        svc = _create()
        assert svc.is_started is False

    def test_service_has_circuit_breaker(self) -> None:
        svc = _create()
        assert svc.circuit_breaker is not None
        assert isinstance(svc.circuit_breaker, CircuitBreaker)


# ===========================================================================
# TestFactoryPortValidation — 6 tests
# ===========================================================================


class TestFactoryPortValidation:
    """Port None/type checks."""

    def test_none_session_read_port_raises(self) -> None:
        with pytest.raises(TypeError, match="session_read_port"):
            _create(session_read_port=None)

    def test_none_model_hub_port_raises(self) -> None:
        with pytest.raises(TypeError, match="model_hub_port"):
            _create(model_hub_port=None)

    def test_none_bridge_command_port_raises(self) -> None:
        with pytest.raises(TypeError, match="bridge_command_port"):
            _create(bridge_command_port=None)

    def test_none_event_subscription_port_raises(self) -> None:
        with pytest.raises(TypeError, match="event_subscription_port"):
            _create(event_subscription_port=None)

    def test_none_health_port_raises(self) -> None:
        with pytest.raises(TypeError, match="health_port"):
            _create(health_port=None)

    def test_wrong_type_port_raises(self) -> None:
        with pytest.raises(TypeError, match="session_read_port"):
            _create(session_read_port=object())


# ===========================================================================
# TestFactoryInvariantValidation — 4 tests
# ===========================================================================


class TestFactoryInvariantValidation:
    """Init-time invariant checks."""

    def test_mw01_checked(self) -> None:
        """validate_init_invariants receives deps without write ports."""
        ports = _all_ports()
        with patch("k1.memory_writer.factory.validate_init_invariants") as mock_validate:
            MemoryWriterFactory.create(**ports)
        deps = mock_validate.call_args[0][0]
        # MW-01 checks that no write port keys exist
        assert "state_write_port" not in deps
        assert "session_write" not in deps

    def test_mw03_checked(self) -> None:
        """validate_init_invariants receives deps without forbidden output ports."""
        ports = _all_ports()
        with patch("k1.memory_writer.factory.validate_init_invariants") as mock_validate:
            MemoryWriterFactory.create(**ports)
        deps = mock_validate.call_args[0][0]
        assert "db_port" not in deps
        assert "http_port" not in deps

    def test_mw08_checked(self) -> None:
        """validate_init_invariants receives config for batch window check."""
        ports = _all_ports()
        cfg = MWConfig(batch_window_ms=250)
        with patch("k1.memory_writer.factory.validate_init_invariants") as mock_validate:
            MemoryWriterFactory.create(**ports, config=cfg)
        passed_config = mock_validate.call_args[0][3]
        assert passed_config.batch_window_ms == 250

    def test_invariant_failure_raises(self) -> None:
        """Invalid config → InvariantViolation propagated from validate_init_invariants."""
        ports = _all_ports()
        with patch(
            "k1.memory_writer.factory.validate_init_invariants",
            side_effect=InvariantViolation("MW-08", "batch window invalid"),
        ):
            with pytest.raises(InvariantViolation):
                MemoryWriterFactory.create(**ports)


# ===========================================================================
# TestFactoryWiring — 3 tests
# ===========================================================================


class TestFactoryWiring:
    """Verify internal wiring of created service."""

    def test_pipeline_has_all_stages(self) -> None:
        svc = _create()
        pipeline = svc._pipeline
        assert hasattr(pipeline, "_filter")
        assert hasattr(pipeline, "_session_reader")
        assert hasattr(pipeline, "_writer_agent")
        assert hasattr(pipeline, "_envelope_builder")
        assert hasattr(pipeline, "_emitter")

    def test_dispatcher_has_event_port(self) -> None:
        ep = FakeEventSubscriptionPort()
        svc = _create(event_subscription_port=ep)
        assert svc._dispatcher._event_port is ep

    def test_circuit_breaker_config_applied(self) -> None:
        cfg = MWConfig(
            circuit_breaker_failure_threshold=5,
            circuit_breaker_recovery_probe_seconds=60,
        )
        svc = _create(config=cfg)
        cb = svc.circuit_breaker
        assert cb._failure_threshold == 5
        assert cb._recovery_probe_seconds == 60
