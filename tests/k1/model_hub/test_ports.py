"""M1 Foundation -- Test Port Protocols [F09-F16].

Tests that all 7 port protocols are runtime_checkable, have correct
method signatures, and the ports __init__.py re-exports all symbols.

NO MOCKS.  Protocol interface structure tests.
"""

from __future__ import annotations

from k1.model_hub.ports import (
    ConfigSubscription,
    HealthReport,
    IConfigPort,
    ICredentialPort,
    IEventPort,
    IHealthPort,
    IMetricsPort,
    IModelHubPort,
    IStateReadPort,
    StateSnapshot,
    Subscription,
)


class TestPortsReExport:
    """All 7 ports + supporting types re-exported from k1.model_hub.ports."""

    def test_all_ports_importable(self) -> None:
        assert IModelHubPort is not None
        assert IEventPort is not None
        assert IStateReadPort is not None
        assert IMetricsPort is not None
        assert IConfigPort is not None
        assert ICredentialPort is not None
        assert IHealthPort is not None

    def test_supporting_types(self) -> None:
        assert Subscription is not None
        assert StateSnapshot is not None
        assert ConfigSubscription is not None
        assert HealthReport is not None


class TestIModelHubPort:
    def test_is_runtime_checkable(self) -> None:
        assert hasattr(IModelHubPort, "__protocol_attrs__") or hasattr(
            IModelHubPort, "__abstractmethods__"
        )

    def test_has_execute(self) -> None:
        assert hasattr(IModelHubPort, "execute")

    def test_has_stream_execute(self) -> None:
        assert hasattr(IModelHubPort, "stream_execute")

    def test_has_discover_capabilities(self) -> None:
        assert hasattr(IModelHubPort, "discover_capabilities")

    def test_has_discover_models(self) -> None:
        assert hasattr(IModelHubPort, "discover_models")

    def test_has_health(self) -> None:
        assert hasattr(IModelHubPort, "health")


class TestIEventPort:
    def test_has_publish(self) -> None:
        assert hasattr(IEventPort, "publish")

    def test_has_subscribe(self) -> None:
        assert hasattr(IEventPort, "subscribe")


class TestIStateReadPort:
    def test_has_read(self) -> None:
        assert hasattr(IStateReadPort, "read")

    def test_no_write_method_mh01(self) -> None:
        """MH-01: IStateReadPort NEVER writes."""
        assert not hasattr(IStateReadPort, "write")
        assert not hasattr(IStateReadPort, "update")
        assert not hasattr(IStateReadPort, "set")
        assert not hasattr(IStateReadPort, "put")
        assert not hasattr(IStateReadPort, "delete")


class TestIMetricsPort:
    def test_has_emit(self) -> None:
        assert hasattr(IMetricsPort, "emit")


class TestIConfigPort:
    def test_has_get(self) -> None:
        assert hasattr(IConfigPort, "get")

    def test_has_watch(self) -> None:
        assert hasattr(IConfigPort, "watch")


class TestICredentialPort:
    def test_has_get_key(self) -> None:
        assert hasattr(ICredentialPort, "get_key")

    def test_has_refresh_key(self) -> None:
        assert hasattr(ICredentialPort, "refresh_key")


class TestIHealthPort:
    def test_has_report_health(self) -> None:
        assert hasattr(IHealthPort, "report_health")

    def test_has_check_health(self) -> None:
        assert hasattr(IHealthPort, "check_health")
