"""M3-E4 SpatialHandle tests."""

from __future__ import annotations

import pytest

from k1.spatial.factory import SpatialFactory
from k1.spatial.kernel import SpatialHandle, build_spatial_handle


@pytest.mark.asyncio
async def test_spatial_handle_refresh_and_projection_roundtrip() -> None:
    bundle, _adapters = SpatialFactory.create_for_testing()
    handle = build_spatial_handle(
        bundle,
        session_id="s1",
        actor_id="actor:parent",
        device_id="device-1",
        installation_id="install-1",
    )

    assert isinstance(handle, SpatialHandle)
    handle.install_into_session()
    snapshot = await handle.refresh_turn("s1", consumer="front")
    projection = await handle.build_projection("s1", consumer="tool")

    assert handle.installed is True
    assert snapshot.session_id == "s1"
    assert projection.consumer == "tool"
    assert projection.precision == "place_id"


@pytest.mark.asyncio
async def test_spatial_handle_rejects_cross_session_access() -> None:
    bundle, _adapters = SpatialFactory.create_for_testing()
    handle = build_spatial_handle(bundle, session_id="s1")

    with pytest.raises(ValueError, match="bound to session"):
        await handle.get_context("other")
