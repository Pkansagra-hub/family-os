"""Tests for per-session TemporalHandle."""

from __future__ import annotations

import pytest

from k1.temporal.kernel import build_temporal_bundle, build_temporal_handle


async def test_temporal_handle_satisfies_kernel_protocol_and_refreshes() -> None:
    from k1.kernel.ports import ITemporalPort

    bundle = build_temporal_bundle()
    handle = build_temporal_handle(bundle, session_id="s1", principal_id="p1")
    assert isinstance(handle, ITemporalPort)

    handle.install_into_session()
    snapshot = await handle.refresh_turn("s1", turn_id="t1")
    projection = await handle.build_projection("s1", "front")

    assert handle.installed is True
    assert snapshot.session_id == "s1"
    assert projection.anchor.anchor_id == snapshot.anchor.anchor_id

    handle.uninstall_from_session()
    assert handle.installed is False


async def test_temporal_handle_empty_session_id_uses_bound_session() -> None:
    bundle = build_temporal_bundle()
    handle = build_temporal_handle(bundle, session_id="s-bound", principal_id="p1")

    snapshot = await handle.refresh_turn("", turn_id="t-empty")
    projection = await handle.build_projection("", "front")

    assert snapshot.session_id == "s-bound"
    assert projection.anchor.anchor_id == snapshot.anchor.anchor_id


async def test_temporal_handle_refresh_can_use_turn_device_context() -> None:
    class _DeviceContext:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str, str]] = []

        async def get_device_snapshot(
            self,
            session_id: str,
            device_id: str,
            installation_id: str,
        ) -> dict[str, str]:
            self.calls.append((session_id, device_id, installation_id))
            return {"timezone": "America/Chicago", "locale": "en-US"}

    device_context = _DeviceContext()
    bundle = build_temporal_bundle(device_context_port=device_context)
    handle = build_temporal_handle(bundle, session_id="s-bound", principal_id="p1")

    snapshot = await handle.refresh_turn(
        "s-bound",
        turn_id="t-device",
        device_id="alex_phone",
        installation_id="alex_phone",
    )

    assert device_context.calls == [("s-bound", "alex_phone", "alex_phone")]
    assert snapshot.anchor.timezone == "America/Chicago"
    assert snapshot.anchor.timezone_source == "device"


async def test_temporal_handle_rejects_non_empty_session_mismatch() -> None:
    bundle = build_temporal_bundle()
    handle = build_temporal_handle(bundle, session_id="s-bound", principal_id="p1")

    with pytest.raises(ValueError, match="TemporalHandle bound to session"):
        await handle.refresh_turn("s-other", turn_id="t-mismatch")
