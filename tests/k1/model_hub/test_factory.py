"""Tests for ModelHubFactory [Epic 6.3].

Coverage:
  - create_standalone() returns valid IModelHubPort
  - create_for_testing() returns (facade, dict) tuple
  - create_with_ports() accepts custom ports
  - _HubCore implements IModelHubPort protocol
  - _DefaultHealthQuery implements IHealthQuery
  - _validate_ports() rejects wrong types
  - DI wiring: all services constructed and accessible
  - Facade methods delegate to RequestRouter
  - discover_capabilities / discover_models work through registry
  - health() returns HubHealthReport
"""

from __future__ import annotations

import asyncio

import pytest

from k1.model_hub.config import ModelHubConfig
from k1.model_hub.factory import ModelHubFactory, _DefaultHealthQuery, _HubCore
from k1.model_hub.ports.hub_port import IModelHubPort
from k1.model_hub.services.capability_router import IHealthQuery
from k1.model_hub.types import HealthStatus, HubHealthReport

# ===========================================================================
# _DefaultHealthQuery tests
# ===========================================================================


class TestDefaultHealthQuery:
    """IHealthQuery stub returns HEALTHY for all providers."""

    def test_get_status_returns_healthy(self) -> None:
        q = _DefaultHealthQuery()
        assert q.get_status("openai") == HealthStatus.HEALTHY

    def test_get_status_any_provider(self) -> None:
        q = _DefaultHealthQuery()
        assert q.get_status("anthropic") == HealthStatus.HEALTHY
        assert q.get_status("unknown") == HealthStatus.HEALTHY

    def test_isinstance_ihealthquery(self) -> None:
        q = _DefaultHealthQuery()
        assert isinstance(q, IHealthQuery)


# ===========================================================================
# create_standalone() tests
# ===========================================================================


class TestCreateStandalone:
    """create_standalone() returns a valid IModelHubPort."""

    def test_returns_imodelhubport(self) -> None:
        hub = ModelHubFactory.create_standalone()
        assert isinstance(hub, IModelHubPort)

    def test_with_custom_config(self) -> None:
        cfg = ModelHubConfig()
        hub = ModelHubFactory.create_standalone(config=cfg)
        assert isinstance(hub, IModelHubPort)

    def test_is_hub_core(self) -> None:
        hub = ModelHubFactory.create_standalone()
        assert isinstance(hub, _HubCore)

    def test_discover_capabilities_empty_registry(self) -> None:
        hub = ModelHubFactory.create_standalone()
        caps = asyncio.get_event_loop().run_until_complete(hub.discover_capabilities())
        assert caps == {}

    def test_discover_models_empty_registry(self) -> None:
        hub = ModelHubFactory.create_standalone()
        models = asyncio.get_event_loop().run_until_complete(hub.discover_models())
        assert models == []

    def test_health_returns_report(self) -> None:
        hub = ModelHubFactory.create_standalone()
        report = asyncio.get_event_loop().run_until_complete(hub.health())
        assert isinstance(report, HubHealthReport)
        assert report.status == HealthStatus.HEALTHY


# ===========================================================================
# create_for_testing() tests
# ===========================================================================


class TestCreateForTesting:
    """create_for_testing() returns (facade, services_dict)."""

    def test_returns_tuple(self) -> None:
        result = ModelHubFactory.create_for_testing()
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_facade_is_imodelhubport(self) -> None:
        facade, _ = ModelHubFactory.create_for_testing()
        assert isinstance(facade, IModelHubPort)

    def test_adapters_dict_has_ports(self) -> None:
        _, adapters = ModelHubFactory.create_for_testing()
        expected_keys = {
            "credential_port",
            "event_port",
            "state_read_port",
            "metrics_port",
            "config_port",
            "health_port",
        }
        assert expected_keys.issubset(adapters.keys())

    def test_adapters_dict_has_services(self) -> None:
        _, adapters = ModelHubFactory.create_for_testing()
        expected_keys = {
            "registry",
            "circuit_mgr",
            "rate_limiter",
            "response_cache",
            "capability_router",
            "model_selector",
            "normalization",
            "dispatcher",
            "audit_logger",
            "router",
        }
        assert expected_keys.issubset(adapters.keys())

    def test_adapters_dict_has_config(self) -> None:
        _, adapters = ModelHubFactory.create_for_testing()
        assert "config" in adapters
        assert isinstance(adapters["config"], ModelHubConfig)

    def test_custom_config_override(self) -> None:
        cfg = ModelHubConfig(cache_max_entries=500)
        _, adapters = ModelHubFactory.create_for_testing(overrides={"config": cfg})
        assert adapters["config"].cache_max_entries == 500

    def test_facade_health(self) -> None:
        facade, _ = ModelHubFactory.create_for_testing()
        report = asyncio.get_event_loop().run_until_complete(facade.health())
        assert isinstance(report, HubHealthReport)
        assert report.status == HealthStatus.HEALTHY

    def test_facade_discover_empty(self) -> None:
        facade, _ = ModelHubFactory.create_for_testing()
        caps = asyncio.get_event_loop().run_until_complete(facade.discover_capabilities())
        assert caps == {}


# ===========================================================================
# create_with_ports() tests
# ===========================================================================


class TestCreateWithPorts:
    """create_with_ports() uses caller-supplied ports."""

    def test_with_credential_port(self) -> None:
        from tests.k1.model_hub.adapters.test_credential_adapter import (
            TestCredentialAdapter,
        )

        cred = TestCredentialAdapter()
        hub = ModelHubFactory.create_with_ports(ports={"credential_port": cred})
        assert isinstance(hub, IModelHubPort)

    def test_with_custom_config(self) -> None:
        from tests.k1.model_hub.adapters.test_credential_adapter import (
            TestCredentialAdapter,
        )

        cfg = ModelHubConfig()
        hub = ModelHubFactory.create_with_ports(
            ports={"credential_port": TestCredentialAdapter()},
            config=cfg,
        )
        assert isinstance(hub, IModelHubPort)

    def test_missing_credential_port_raises(self) -> None:
        with pytest.raises(KeyError):
            ModelHubFactory.create_with_ports(ports={})


# ===========================================================================
# _validate_ports() tests
# ===========================================================================


class TestValidatePorts:
    """DI validation rejects wrong types."""

    def test_rejects_non_credential_port(self) -> None:
        from k1.model_hub.factory import _validate_ports

        with pytest.raises(TypeError, match="credential_port"):
            _validate_ports(credential_port="not-a-port")

    def test_rejects_non_event_port(self) -> None:
        from k1.model_hub.factory import _validate_ports

        with pytest.raises(TypeError, match="event_port"):
            _validate_ports(event_port=42)

    def test_accepts_valid_ports(self) -> None:
        from k1.model_hub.factory import _validate_ports
        from tests.k1.model_hub.adapters.test_credential_adapter import (
            TestCredentialAdapter,
        )
        from tests.k1.model_hub.adapters.test_event_adapter import TestEventAdapter

        # Should not raise
        _validate_ports(
            credential_port=TestCredentialAdapter(),
            event_port=TestEventAdapter(),
        )

    def test_skips_none_ports(self) -> None:
        from k1.model_hub.factory import _validate_ports

        # Should not raise for None values
        _validate_ports(credential_port=None, event_port=None)

    def test_ignores_unknown_keys(self) -> None:
        from k1.model_hub.factory import _validate_ports

        # Unknown keys are silently ignored
        _validate_ports(unknown_port="anything")


# ===========================================================================
# _HubCore protocol compliance
# ===========================================================================


class TestHubCoreProtocol:
    """_HubCore satisfies IModelHubPort at runtime."""

    def test_isinstance_check(self) -> None:
        hub = ModelHubFactory.create_standalone()
        assert isinstance(hub, IModelHubPort)

    def test_has_execute(self) -> None:
        hub = ModelHubFactory.create_standalone()
        assert hasattr(hub, "execute")
        assert callable(hub.execute)

    def test_has_stream_execute(self) -> None:
        hub = ModelHubFactory.create_standalone()
        assert hasattr(hub, "stream_execute")
        assert callable(hub.stream_execute)

    def test_has_discover_capabilities(self) -> None:
        hub = ModelHubFactory.create_standalone()
        assert hasattr(hub, "discover_capabilities")
        assert callable(hub.discover_capabilities)

    def test_has_discover_models(self) -> None:
        hub = ModelHubFactory.create_standalone()
        assert hasattr(hub, "discover_models")
        assert callable(hub.discover_models)

    def test_has_health(self) -> None:
        hub = ModelHubFactory.create_standalone()
        assert hasattr(hub, "health")
        assert callable(hub.health)
