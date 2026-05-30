"""M3-E4 KernelService per-session spatial handle wiring."""

from __future__ import annotations

import pytest

from k1.concierge.config.kernel import KernelConfig
from k1.kernel.service import KernelService
from k1.spatial.kernel.handle import SpatialHandle


@pytest.mark.asyncio
async def test_create_session_wires_spatial_handle_into_session_and_concierge(tmp_path) -> None:
    svc = KernelService(
        config=KernelConfig(
            model_mode="test",
            sessionstate_db_path=str(tmp_path / "ssm.db"),
            enable_spatial=True,
        )
    )
    await svc.startup()

    try:
        session = await svc.create_session("spatial-session", device_id="device-1")

        assert isinstance(session.spatial, SpatialHandle)
        assert session.spatial.installed is True
        assert session.concierge.spatial is session.spatial
        assert svc.describe_wiring()["sessions"]["spatial-session"]["spatial"] == "SpatialHandle"
    finally:
        await svc.shutdown()
