"""Tests for bridge.connector.gateway.ConnectorGateway end-to-end pipeline."""

from __future__ import annotations

from typing import Any

import pytest

from bridge.connector import (
    AdapterQuarantinedError,
    CABundleAdapterVerifier,
    ConnectorCaller,
    ConnectorGateway,
    InMemoryCredentialVault,
    InvalidAdapterSignatureError,
    OfflineAdapterError,
    SkeletonMCPProcessManager,
    TokenDeniedError,
    ToolDescriptor,
    UnknownAdapterError,
)
from bridge.ports import IConnectorGatewayPort

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _stub_manifest(adapter_id: str = "echo") -> dict[str, Any]:
    """Minimal manifest that the gateway accepts; signature checks
    are bypassed via trust_unsigned=True on the verifier."""
    return {
        "topic": f"ifl.{adapter_id}.v1",
        "category": "test",
        "capabilities": ["echo.say"],
    }


def _gateway(
    *, manifest: dict[str, Any] | None = None
) -> tuple[ConnectorGateway, SkeletonMCPProcessManager]:
    pm = SkeletonMCPProcessManager()
    gw = ConnectorGateway(
        process_manager=pm,
        credential_vault=InMemoryCredentialVault(),
        adapter_verifier=CABundleAdapterVerifier(trust_unsigned=True),
    )
    if manifest is None:
        manifest = _stub_manifest("echo")
    gw.register(adapter_id="echo", manifest=manifest)
    return gw, pm


def _caller() -> ConnectorCaller:
    return ConnectorCaller(session_id="s1", tenant_id="t1", trace_id="trace-1")


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


def test_gateway_satisfies_port_protocol() -> None:
    gw = ConnectorGateway(adapter_verifier=CABundleAdapterVerifier(trust_unsigned=True))
    assert isinstance(gw, IConnectorGatewayPort)


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_invoke_routes_through_pipeline_to_mcp_child() -> None:
    gw, pm = _gateway()

    async def echo_impl(args: dict[str, Any]) -> dict[str, Any]:
        return {"echoed": args.get("message", "")}

    await pm.start(adapter_id="echo", manifest=_stub_manifest("echo"))
    pm.bind_tool(adapter_id="echo", tool="echo.say", impl=echo_impl)

    result = await gw.invoke(
        adapter_id="echo",
        tool="echo.say",
        args={"message": "hello"},
        caller=_caller(),
    )

    assert result.success is True
    assert result.data == {"echoed": "hello"}
    assert result.adapter_id == "echo"
    assert result.tool == "echo.say"
    assert result.latency_ms >= 0


@pytest.mark.asyncio
async def test_legacy_execute_alias_invokes_same_pipeline() -> None:
    gw, pm = _gateway()

    async def echo_impl(args: dict[str, Any]) -> dict[str, Any]:
        return {"args": args}

    await pm.start(adapter_id="echo", manifest=_stub_manifest("echo"))
    pm.bind_tool(adapter_id="echo", tool="echo.say", impl=echo_impl)

    result = await gw.execute("echo", "echo.say", {"k": "v"}, trace_id="t")
    assert result.success is True
    assert result.data == {"args": {"k": "v"}}


# ---------------------------------------------------------------------------
# Pipeline stage gates
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_invoke_unknown_adapter_raises_unknown_error() -> None:
    gw = ConnectorGateway(adapter_verifier=CABundleAdapterVerifier(trust_unsigned=True))
    with pytest.raises(UnknownAdapterError):
        await gw.invoke(
            adapter_id="missing",
            tool="x",
            args={},
            caller=_caller(),
        )


@pytest.mark.asyncio
async def test_token_verifier_denies_when_capability_required_and_missing() -> None:
    manifest = _stub_manifest("echo")
    manifest["capability_required"] = True
    gw, pm = _gateway(manifest=manifest)
    await pm.start(adapter_id="echo", manifest=manifest)

    with pytest.raises(TokenDeniedError):
        await gw.invoke(
            adapter_id="echo",
            tool="echo.say",
            args={},
            caller=ConnectorCaller(session_id="s", tenant_id="t"),  # no token
        )


@pytest.mark.asyncio
async def test_invoke_when_child_not_started_returns_offline_error() -> None:
    gw, _pm = _gateway()
    # Did not call pm.start → state stays "stopped" via UnknownAdapterError
    # path inside SkeletonMCPProcessManager.invoke when no record.
    with pytest.raises(UnknownAdapterError):
        await gw.invoke(
            adapter_id="echo",
            tool="echo.say",
            args={},
            caller=_caller(),
        )


@pytest.mark.asyncio
async def test_invoke_when_quarantined_raises_quarantined_error() -> None:
    gw, pm = _gateway()
    await pm.start(adapter_id="echo", manifest=_stub_manifest("echo"))
    pm.bind_tool(
        adapter_id="echo",
        tool="echo.say",
        impl=lambda args: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    # Force quarantine by directly recording crashes (skeleton hook).
    for _ in range(pm.crash_budget_count):
        pm.record_crash(adapter_id="echo")

    with pytest.raises(AdapterQuarantinedError):
        await gw.invoke(
            adapter_id="echo",
            tool="echo.say",
            args={},
            caller=_caller(),
        )


@pytest.mark.asyncio
async def test_invoke_offline_when_state_not_ready() -> None:
    gw, pm = _gateway()
    await pm.start(adapter_id="echo", manifest=_stub_manifest("echo"))
    # Simulate restart / unhealthy.
    pm._records["echo"].state = "unhealthy"  # type: ignore[attr-defined]

    with pytest.raises(OfflineAdapterError):
        await gw.invoke(
            adapter_id="echo",
            tool="echo.say",
            args={},
            caller=_caller(),
        )


# ---------------------------------------------------------------------------
# list_tools / health surface
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_tools_returns_descriptors_when_registered() -> None:
    gw, pm = _gateway()
    await pm.start(adapter_id="echo", manifest=_stub_manifest("echo"))
    pm._records["echo"].tools = [  # type: ignore[attr-defined]
        ToolDescriptor(name="echo.say", description="echoes back input")
    ]

    tools = await gw.list_tools(adapter_id="echo")
    assert [t.name for t in tools] == ["echo.say"]


@pytest.mark.asyncio
async def test_list_tools_unknown_adapter_raises() -> None:
    gw = ConnectorGateway(adapter_verifier=CABundleAdapterVerifier(trust_unsigned=True))
    with pytest.raises(UnknownAdapterError):
        await gw.list_tools(adapter_id="ghost")


@pytest.mark.asyncio
async def test_health_unknown_adapter_returns_unknown_state() -> None:
    gw = ConnectorGateway(adapter_verifier=CABundleAdapterVerifier(trust_unsigned=True))
    h = await gw.health(adapter_id="ghost")
    assert h.adapter_id == "ghost"
    assert h.state == "unknown"


@pytest.mark.asyncio
async def test_health_ready_after_start() -> None:
    gw, pm = _gateway()
    await pm.start(adapter_id="echo", manifest=_stub_manifest("echo"))
    h = await gw.health(adapter_id="echo")
    assert h.state == "ready"
    assert h.last_ping_ms > 0


@pytest.mark.asyncio
async def test_legacy_list_adapters_reports_registered() -> None:
    gw, pm = _gateway()
    await pm.start(adapter_id="echo", manifest=_stub_manifest("echo"))
    statuses = await gw.list_adapters()
    assert len(statuses) == 1
    s = statuses[0]
    assert s.adapter_id == "echo"
    assert s.healthy is True
    assert "echo.say" in s.capabilities


# ---------------------------------------------------------------------------
# Registration / signature gating
# ---------------------------------------------------------------------------


def test_register_rejects_unsigned_manifest_when_strict() -> None:
    gw = ConnectorGateway(
        adapter_verifier=CABundleAdapterVerifier(trust_unsigned=False),
    )
    with pytest.raises(InvalidAdapterSignatureError):
        gw.register(adapter_id="echo", manifest=_stub_manifest("echo"))


def test_unregister_is_idempotent() -> None:
    gw, _pm = _gateway()
    gw.unregister(adapter_id="echo")
    gw.unregister(adapter_id="echo")  # no error
