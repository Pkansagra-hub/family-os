"""M3-E6 grounding SpatialHandleAdapter tests."""

from __future__ import annotations

from types import SimpleNamespace

from k1.grounding.adapters.spatial_handle_adapter import SpatialHandleAdapter
from k1.spatial.types import SpatialProjection


class _SpatialHandle:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self.refresh_calls: list[dict[str, object]] = []

    async def refresh_turn(self, session_id: str, consumer: str, **kwargs):  # type: ignore[no-untyped-def]
        self.refresh_calls.append({"session_id": session_id, "consumer": consumer, **kwargs})
        return SimpleNamespace(
            projection=SpatialProjection(
                projection_id="sp-refresh",
                context_id="ctx-refresh",
                session_id=session_id,
                consumer=consumer,
                semantic_place="home",
                precision="semantic",
                place_refs=(),
                active_device_surface="mobile",
                co_presence=(),
                freshness="live",
                redactions=(),
            )
        )

    async def build_projection(self, session_id: str, consumer: str, **kwargs):  # type: ignore[no-untyped-def]
        self.calls.append({"session_id": session_id, "consumer": consumer, **kwargs})
        return SpatialProjection(
            projection_id="sp1",
            context_id="ctx1",
            session_id=session_id,
            consumer=consumer,
            semantic_place="home",
            precision=kwargs.get("requested_precision") or "semantic",
            place_refs=(),
            active_device_surface="mobile",
            co_presence=(),
            freshness="live",
            redactions=(),
        )


async def test_spatial_handle_adapter_passes_requested_precision_to_real_handle() -> None:
    handle = _SpatialHandle()
    adapter = SpatialHandleAdapter(handle)

    projection = await adapter.build_projection(
        "s1",
        "tool",
        device_id="device-1",
        installation_id="install-1",
        requested_precision="place_id",
    )

    assert projection.precision == "place_id"
    assert handle.calls[0]["requested_precision"] == "place_id"


async def test_spatial_handle_adapter_refreshes_real_handle_before_projection() -> None:
    handle = _SpatialHandle()
    adapter = SpatialHandleAdapter(handle)

    projection = await adapter.refresh_turn(
        "s1",
        "front",
        device_id="device-1",
        installation_id="install-1",
    )

    assert projection.context_id == "ctx-refresh"
    assert projection.freshness == "live"
    assert handle.refresh_calls == [
        {
            "session_id": "s1",
            "consumer": "front",
            "device_id": "device-1",
            "installation_id": "install-1",
        }
    ]


async def test_spatial_handle_adapter_unknown_fallback_uses_requested_precision() -> None:
    projection = await SpatialHandleAdapter().build_projection(
        "s1",
        "front",
        requested_precision="semantic",
    )

    assert projection.semantic_place == "unknown"
    assert projection.precision == "semantic"
    assert "source_unavailable" in projection.redactions
