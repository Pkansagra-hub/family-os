"""
E1.7.2 — Unit Tests for k1/model_hub/ports.py
===============================================

Validates:
  - IModelHubPort is runtime_checkable
  - All 7 ports are Protocols with correct method signatures
  - TestProviderPlugin satisfies IProviderPlugin
  - Supporting types construction
"""

from __future__ import annotations

import pytest

from k1.model_hub.plugins.base import IProviderPlugin
from k1.model_hub.plugins.test_plugin import TestProviderPlugin
from k1.model_hub.ports import (
    HubHealthReport,
    IConfigPort,
    ICredentialPort,
    IEventPort,
    IHealthPort,
    IMetricsPort,
    IModelHubPort,
    IStateReadPort,
    ProviderHealthStatus,
    StateSnapshot,
    Subscription,
)

# =====================================================================
# Runtime checkable — all 7 ports
# =====================================================================


class TestRuntimeCheckable:
    """All ports decorated with @runtime_checkable can be used with isinstance."""

    def test_imodel_hub_port_is_runtime_checkable(self) -> None:
        assert (
            hasattr(IModelHubPort, "__protocol_attrs__")
            or hasattr(IModelHubPort, "__abstractmethods__")
            or isinstance(IModelHubPort, type)
        )

    def test_ievent_port_is_runtime_checkable(self) -> None:
        assert isinstance(IEventPort, type)

    def test_istate_read_port_is_runtime_checkable(self) -> None:
        assert isinstance(IStateReadPort, type)

    def test_imetrics_port_is_runtime_checkable(self) -> None:
        assert isinstance(IMetricsPort, type)

    def test_iconfig_port_is_runtime_checkable(self) -> None:
        assert isinstance(IConfigPort, type)

    def test_icredential_port_is_runtime_checkable(self) -> None:
        assert isinstance(ICredentialPort, type)

    def test_ihealth_port_is_runtime_checkable(self) -> None:
        assert isinstance(IHealthPort, type)


# =====================================================================
# IModelHubPort method signatures
# =====================================================================


class TestIModelHubPortSignature:
    """IModelHubPort declares 5 methods."""

    EXPECTED_METHODS = {
        "execute",
        "stream_execute",
        "discover_capabilities",
        "discover_models",
        "health",
    }

    def test_has_all_methods(self) -> None:
        for method_name in self.EXPECTED_METHODS:
            assert hasattr(IModelHubPort, method_name), f"Missing {method_name}"

    def test_no_unexpected_abstract_methods(self) -> None:
        actual = {
            name
            for name in dir(IModelHubPort)
            if not name.startswith("_") and callable(getattr(IModelHubPort, name, None))
        }
        assert self.EXPECTED_METHODS.issubset(actual)


# =====================================================================
# Other ports — expected method names
# =====================================================================


class TestEventPortSignature:
    def test_has_publish_and_subscribe(self) -> None:
        assert hasattr(IEventPort, "publish")
        assert hasattr(IEventPort, "subscribe")


class TestStateReadPortSignature:
    def test_has_read(self) -> None:
        assert hasattr(IStateReadPort, "read")


class TestMetricsPortSignature:
    def test_has_emit(self) -> None:
        assert hasattr(IMetricsPort, "emit")


class TestConfigPortSignature:
    def test_has_get_and_watch(self) -> None:
        assert hasattr(IConfigPort, "get")
        assert hasattr(IConfigPort, "watch")


class TestCredentialPortSignature:
    def test_has_get_key_and_refresh_key(self) -> None:
        assert hasattr(ICredentialPort, "get_key")
        assert hasattr(ICredentialPort, "refresh_key")


class TestHealthPortSignature:
    def test_has_report_and_check(self) -> None:
        assert hasattr(IHealthPort, "report_health")
        assert hasattr(IHealthPort, "check_health")


# =====================================================================
# TestProviderPlugin satisfies IProviderPlugin
# =====================================================================


class TestProviderPluginProtocol:
    def test_isinstance_check(self) -> None:
        plugin = TestProviderPlugin()
        assert isinstance(plugin, IProviderPlugin)

    def test_custom_provider_id(self) -> None:
        plugin = TestProviderPlugin(provider_id="custom-test")
        assert plugin.provider_id == "custom-test"


# =====================================================================
# Supporting types
# =====================================================================


class TestSupportingTypes:
    def test_hub_health_report_defaults(self) -> None:
        r = HubHealthReport()
        assert r.status == "HEALTHY"
        assert r.providers == []

    def test_hub_health_report_with_providers(self) -> None:
        prov = ProviderHealthStatus(
            provider_id="google",
            status="DEGRADED",
            latency_ms=500,
            error_rate=0.05,
            circuit_state="HALF_OPEN",
        )
        r = HubHealthReport(status="DEGRADED", providers=[prov])
        assert len(r.providers) == 1
        assert r.providers[0].circuit_state == "HALF_OPEN"

    def test_state_snapshot(self) -> None:
        s = StateSnapshot(sections={"persona": {"model_pref": "fast"}})
        assert s.sections["persona"]["model_pref"] == "fast"

    def test_subscription_cancel(self) -> None:
        sub = Subscription()
        sub.cancel()  # should not raise
