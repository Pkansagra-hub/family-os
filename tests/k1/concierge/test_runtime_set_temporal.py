"""Tests for ConciergeRuntime temporal pre-start wiring."""

from __future__ import annotations

import pytest

from k1.concierge.factory import ConciergeFactory


async def test_runtime_set_temporal_pre_start_guard() -> None:
    runtime = ConciergeFactory.create_standalone()
    handle = object()
    runtime.set_temporal(handle)
    assert runtime.temporal is handle

    await runtime.start()
    try:
        with pytest.raises(RuntimeError, match="set_temporal"):
            runtime.set_temporal(object())
    finally:
        await runtime.stop()
