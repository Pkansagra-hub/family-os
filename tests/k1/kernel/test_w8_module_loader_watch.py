"""W8 regression: KernelConfig.module_loader_watch gates the Fabric
ModuleLoader hot-reload watcher.

- Default (False): no watcher running after startup; manifests are
  scanned once but not polled.
- Opt-in (True): watcher is running; shutdown stops it.
"""

from __future__ import annotations

import pytest

from k1.concierge.config.kernel import KernelConfig
from k1.kernel.service import KernelService


@pytest.mark.asyncio
async def test_w8_watch_disabled_by_default() -> None:
    svc = KernelService(config=KernelConfig())
    await svc.startup()
    try:
        ml = svc._shared_fabric.module_loader  # type: ignore[union-attr]
        assert ml is not None
        assert ml.is_running is False
    finally:
        await svc.shutdown()


@pytest.mark.asyncio
async def test_w8_watch_starts_when_flag_true() -> None:
    svc = KernelService(config=KernelConfig(module_loader_watch=True))
    await svc.startup()
    try:
        ml = svc._shared_fabric.module_loader  # type: ignore[union-attr]
        assert ml is not None
        assert ml.is_running is True
    finally:
        await svc.shutdown()


@pytest.mark.asyncio
async def test_w8_shutdown_stops_watcher() -> None:
    svc = KernelService(config=KernelConfig(module_loader_watch=True))
    await svc.startup()
    ml = svc._shared_fabric.module_loader  # type: ignore[union-attr]
    assert ml is not None and ml.is_running is True
    await svc.shutdown()
    assert ml.is_running is False
