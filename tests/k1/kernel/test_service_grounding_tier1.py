"""M1.5-E4: KernelService Tier-1 grounding bundle wiring."""

from __future__ import annotations

import pytest

from k1.concierge.config.kernel import KernelConfig
from k1.kernel.service import KernelService


@pytest.mark.asyncio
async def test_startup_tier1_builds_grounding_bundle_when_enabled(tmp_path) -> None:
    svc = KernelService(
        config=KernelConfig(
            model_mode="test",
            sessionstate_db_path=str(tmp_path / "ssm.db"),
            enable_temporal=True,
            enable_grounding=True,
        )
    )

    try:
        await svc._startup_tier1()

        assert svc.grounding_bundle is not None
        assert svc.describe_wiring()["tier1"]["grounding_bundle"] == "GroundingServiceBundle"
    finally:
        await svc._cleanup_tier1_partial()


@pytest.mark.asyncio
async def test_startup_tier1_skips_grounding_bundle_by_default(tmp_path) -> None:
    svc = KernelService(
        config=KernelConfig(model_mode="test", sessionstate_db_path=str(tmp_path / "ssm.db"))
    )

    try:
        await svc._startup_tier1()

        assert svc.grounding_bundle is None
        assert svc.describe_wiring()["tier1"]["grounding_bundle"] is None
    finally:
        await svc._cleanup_tier1_partial()
