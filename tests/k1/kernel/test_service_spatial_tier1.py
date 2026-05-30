"""M3-E4 KernelService Tier-1 spatial bundle wiring."""

from __future__ import annotations

import pytest

from k1.concierge.config.kernel import KernelConfig
from k1.kernel.service import KernelService


@pytest.mark.asyncio
async def test_startup_tier1_builds_spatial_bundle_when_enabled(tmp_path) -> None:
    svc = KernelService(
        config=KernelConfig(
            model_mode="test",
            sessionstate_db_path=str(tmp_path / "ssm.db"),
            enable_spatial=True,
        )
    )

    try:
        await svc._startup_tier1()

        assert svc.spatial_bundle is not None
        assert svc.describe_wiring()["tier1"]["spatial_bundle"] == "SpatialServiceBundle"
    finally:
        await svc._cleanup_tier1_partial()


@pytest.mark.asyncio
async def test_startup_tier1_skips_spatial_bundle_by_default(tmp_path) -> None:
    svc = KernelService(
        config=KernelConfig(model_mode="test", sessionstate_db_path=str(tmp_path / "ssm.db"))
    )

    try:
        await svc._startup_tier1()

        assert svc.spatial_bundle is None
        assert svc.describe_wiring()["tier1"]["spatial_bundle"] is None
    finally:
        await svc._cleanup_tier1_partial()
