"""P2.3: Kernel-level ModelHub lifecycle tests.

Covers the new contract introduced by EPIC P2.3:
  - ``_startup_tier1`` builds the hub via ``ModelHubFactory.from_config``
    when ``model_mode == "hub"``; uses ``create_with_ports`` otherwise.
  - ``KernelService.shutdown`` calls ``self._model_hub.shutdown()`` to
    drain plugin connections (mirrors Orchestrator/Fabric/Bridge pattern).
  - Exceptions raised by the hub's ``shutdown`` are logged at WARNING and
    accumulated, never propagated as uncaught errors past the kernel.
  - ``_cleanup_tier1_partial`` drains the hub before nulling the field
    (closes the resource leak surfaced by the P2.3 archaeology).

These are the first kernel-level tests of the model-hub lifecycle; the
existing TestS2ModelHubWiring class only verifies static port wiring.
"""

from __future__ import annotations

import logging

import pytest

from k1.concierge.config.kernel import KernelConfig
from k1.kernel.service import KernelService

# ── helpers ─────────────────────────────────────────────────


class _SpyPlugin:
    """Minimal plugin stub that counts close() invocations."""

    def __init__(self, *, raise_on_close: bool = False) -> None:
        self.close_call_count = 0
        self._raise = raise_on_close

    async def close(self) -> None:
        self.close_call_count += 1
        if self._raise:
            raise RuntimeError("spy plugin close() boom")


def _inject_spy_plugin(svc: KernelService, plugin: _SpyPlugin, *, name: str = "spy") -> None:
    """Register a spy plugin into the live hub's dispatcher.

    Bypasses the registry to avoid needing a full ProviderManifest. The
    dispatcher's ``_plugins`` dict is the canonical source iterated by
    ``_HubCore.shutdown()``.
    """
    dispatcher = svc._model_hub._router._dispatcher
    dispatcher._plugins[name] = plugin


# ── startup wiring ──────────────────────────────────────────


class TestStartupCallsFromConfig:
    """P2.3: ``_startup_tier1`` uses ``from_config`` only in hub mode."""

    @pytest.mark.asyncio
    async def test_hub_mode_logs_provider_load(self, caplog: pytest.LogCaptureFixture) -> None:
        """When model_mode == 'hub', the loader runs and logs its result."""
        caplog.set_level(logging.INFO, logger="k1.kernel.service")
        svc = KernelService(config=KernelConfig(model_mode="hub"))
        try:
            await svc._startup_tier1()
            assert svc._model_hub is not None
            # The new from_config path always emits the load summary.
            assert any(
                "ModelHub provider load: registered=" in rec.getMessage() for rec in caplog.records
            ), f"Expected provider-load log line, got: {[r.getMessage() for r in caplog.records]}"
        finally:
            await _safe_teardown(svc)

    @pytest.mark.asyncio
    async def test_non_hub_mode_constructs_hub_without_loader(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """When model_mode != 'hub', hub is built but loader is skipped."""
        caplog.set_level(logging.INFO, logger="k1.kernel.service")
        # Anything other than "hub" exercises the else-branch.
        # "test" is the canonical non-hub mode; "legacy" was renamed.
        svc = KernelService(config=KernelConfig(model_mode="test"))
        try:
            await svc._startup_tier1()
            assert svc._model_hub is not None
            # No loader summary should appear.
            assert not any(
                "ModelHub provider load: registered=" in rec.getMessage() for rec in caplog.records
            )
        finally:
            await _safe_teardown(svc)


# ── teardown drain ──────────────────────────────────────────


class TestShutdownDrainsModelHub:
    """P2.3: ``KernelService.shutdown`` drains hub plugins."""

    @pytest.mark.asyncio
    async def test_shutdown_calls_plugin_close(self) -> None:
        svc = KernelService(config=KernelConfig(model_mode="hub"))
        await svc._startup_tier1()
        svc._running = True  # shutdown() guards on this flag
        spy = _SpyPlugin()
        _inject_spy_plugin(svc, spy)
        await svc.shutdown()
        assert spy.close_call_count == 1

    @pytest.mark.asyncio
    async def test_shutdown_swallows_plugin_close_exception(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A raising plugin must not propagate past KernelService.shutdown.

        ``_HubCore.shutdown`` itself swallows per-plugin exceptions (logs
        them at WARNING). The kernel's outer wait_for therefore sees a
        clean return; no aggregate RuntimeError is raised when no other
        teardown step fails.
        """
        caplog.set_level(logging.WARNING)
        svc = KernelService(config=KernelConfig(model_mode="hub"))
        await svc._startup_tier1()
        svc._running = True
        spy = _SpyPlugin(raise_on_close=True)
        _inject_spy_plugin(svc, spy)
        # Must not raise.
        await svc.shutdown()
        assert spy.close_call_count == 1
        # The hub's own shutdown logs the per-plugin failure.
        assert any("ModelHub plugin close failed" in rec.getMessage() for rec in caplog.records)


# ── partial-cleanup drain ───────────────────────────────────


class TestCleanupTier1PartialDrainsHub:
    """P2.3: ``_cleanup_tier1_partial`` calls hub.shutdown() before nulling."""

    @pytest.mark.asyncio
    async def test_partial_cleanup_drains_then_nulls(self) -> None:
        svc = KernelService(config=KernelConfig(model_mode="hub"))
        await svc._startup_tier1()
        spy = _SpyPlugin()
        _inject_spy_plugin(svc, spy)
        await svc._cleanup_tier1_partial()
        assert spy.close_call_count == 1, "hub must be drained before field is nulled"
        assert svc._model_hub is None

    @pytest.mark.asyncio
    async def test_partial_cleanup_swallows_hub_exception(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Raising plugin during partial cleanup must not propagate."""
        caplog.set_level(logging.WARNING, logger="k1.kernel.service")
        svc = KernelService(config=KernelConfig(model_mode="hub"))
        await svc._startup_tier1()
        spy = _SpyPlugin(raise_on_close=True)
        _inject_spy_plugin(svc, spy)
        # Must not raise -- error-recovery path swallows everything.
        await svc._cleanup_tier1_partial()
        assert svc._model_hub is None


# ── shared helpers ──────────────────────────────────────────


async def _safe_teardown(svc: KernelService) -> None:
    """Best-effort teardown for tests that only ran ``_startup_tier1``."""
    if svc._model_hub is not None:
        try:
            await svc._model_hub.shutdown()
        except Exception:
            pass
    if svc._bus is not None:
        try:
            svc._bus.close()
        except Exception:
            pass
    if svc._router is not None:
        try:
            svc._router.close()
        except Exception:
            pass
