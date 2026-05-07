"""Tests for bridge/connector/contracts.py typed boundary objects."""

from __future__ import annotations

import pytest

from bridge.connector.contracts import (
    AdapterHealth,
    AdapterQuarantinedError,
    ConnectorCaller,
    ConnectorGatewayError,
    ConnectorResult,
    InvalidAdapterSignatureError,
    OfflineAdapterError,
    TokenDeniedError,
    ToolDescriptor,
    UnknownAdapterError,
)


def test_connector_caller_is_frozen() -> None:
    caller = ConnectorCaller(session_id="s", tenant_id="t")
    with pytest.raises((AttributeError, TypeError)):
        caller.session_id = "other"  # type: ignore[misc]


def test_connector_caller_defaults() -> None:
    caller = ConnectorCaller(session_id="s", tenant_id="t")
    assert caller.space_id == "personal"
    assert caller.user_band == "GREEN"
    assert caller.capability_token == ""
    assert caller.trace_id == ""


def test_connector_result_defaults_imply_success_with_empty_data() -> None:
    r = ConnectorResult()
    assert r.success is True
    assert r.data == {}
    assert r.attempt_count == 1


def test_tool_descriptor_default_schemas_are_empty_dicts() -> None:
    td = ToolDescriptor(name="events.list")
    assert td.input_schema == {}
    assert td.output_schema == {}


def test_adapter_health_default_state_is_unknown() -> None:
    h = AdapterHealth(adapter_id="x")
    assert h.state == "unknown"
    assert h.last_ping_ms == 0


@pytest.mark.parametrize(
    "exc_cls",
    [
        OfflineAdapterError,
        AdapterQuarantinedError,
        InvalidAdapterSignatureError,
        TokenDeniedError,
        UnknownAdapterError,
    ],
)
def test_all_gateway_errors_subclass_connector_gateway_error(exc_cls: type) -> None:
    assert issubclass(exc_cls, ConnectorGatewayError)
    assert issubclass(exc_cls, Exception)
