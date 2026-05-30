"""M1.5-E4: KernelService per-session grounding handle wiring."""

from __future__ import annotations

import pytest

from k1.concierge.config.kernel import KernelConfig
from k1.grounding.kernel.handle import GroundingHandle
from k1.kernel.service import KernelService


@pytest.mark.asyncio
async def test_create_session_wires_grounding_handle_into_session_and_concierge(tmp_path) -> None:
    svc = KernelService(
        config=KernelConfig(
            model_mode="test",
            sessionstate_db_path=str(tmp_path / "ssm.db"),
            enable_temporal=True,
            enable_grounding=True,
        )
    )
    await svc.startup()

    try:
        session = await svc.create_session("grounding-session", device_id="device-1")

        assert isinstance(session.grounding, GroundingHandle)
        assert session.grounding.installed is True
        assert session.concierge.grounding is session.grounding
        assert (
            svc.describe_wiring()["sessions"]["grounding-session"]["grounding"] == "GroundingHandle"
        )
    finally:
        await svc.shutdown()
