"""P2.2 -- ModelHubFactory.from_config + _HubCore.shutdown unit tests.

No live API calls. Reuses the stub-plugin pattern from test_loader.py
to exercise from_config's happy / skip / fail paths and shutdown's
idempotency / timeout / exception-swallowing behavior.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import AsyncIterator

import pytest
import yaml

from k1.model_hub.factory import ModelHubFactory, _HubCore
from k1.model_hub.loader import ProviderConfig, ProviderEntry
from k1.model_hub.manifest import ProviderManifest
from k1.model_hub.plugins.base import (
    NormalizedRequest,
    ProviderChunk,
    ProviderHealth,
    ProviderResponse,
)
from k1.model_hub.types import CapabilityType, HealthStatus

# ---------------------------------------------------------------------------
# Stub plugins (instances are class-tracked so tests can assert close-state)
# ---------------------------------------------------------------------------


class _SpyPlugin:
    """IProviderPlugin stub. Records initialize/close call counts per instance."""

    instances: "list[_SpyPlugin]" = []

    def __init__(self) -> None:
        self.api_key: str | None = None
        self.initialized_with: ProviderManifest | None = None
        self.close_call_count: int = 0
        type(self).instances.append(self)

    async def initialize(self, manifest: ProviderManifest) -> None:
        self.initialized_with = manifest

    def supports(self, capability: CapabilityType) -> bool:
        return True

    async def execute(self, request: NormalizedRequest) -> ProviderResponse:
        return ProviderResponse(text="stub")

    async def stream_execute(self, request: NormalizedRequest) -> AsyncIterator[ProviderChunk]:
        yield ProviderChunk(delta="stub")

    def estimate_tokens(self, text: str) -> int:
        return len(text.split()) if isinstance(text, str) else 0

    async def health_check(self) -> ProviderHealth:
        return ProviderHealth(status=HealthStatus.HEALTHY)

    async def close(self) -> None:
        self.close_call_count += 1

    def set_api_key(self, key: str) -> None:
        self.api_key = key


class _RaisingClosePlugin(_SpyPlugin):
    async def close(self) -> None:
        self.close_call_count += 1
        raise RuntimeError("close exploded")


class _HangingClosePlugin(_SpyPlugin):
    async def close(self) -> None:
        self.close_call_count += 1
        # Sleep longer than _PLUGIN_CLOSE_TIMEOUT_S (5.0s) -> trigger TimeoutError.
        await asyncio.sleep(60.0)


_SPY_PLUGIN_PATH = "tests.k1.model_hub.test_factory_from_config._SpyPlugin"
_RAISING_PLUGIN_PATH = "tests.k1.model_hub.test_factory_from_config._RaisingClosePlugin"
_HANGING_PLUGIN_PATH = "tests.k1.model_hub.test_factory_from_config._HangingClosePlugin"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_manifest(
    dir_: Path,
    provider_id: str,
    *,
    plugin_class: str = _SPY_PLUGIN_PATH,
    auth_type: str = "bearer",
    credential_key: str = "P22_TEST_API_KEY",
) -> Path:
    payload = {
        "provider_id": provider_id,
        "display_name": f"Test {provider_id}",
        "plugin_class": plugin_class,
        "api_base": "https://example.invalid",
        "auth": {"type": auth_type, "credential_key": credential_key},
        "capabilities": ["CHAT"],
        "models": [
            {
                "id": f"{provider_id}-model",
                "capabilities": ["CHAT"],
                "cost_per_1m_input": 1.0,
                "cost_per_1m_output": 2.0,
            }
        ],
    }
    path = dir_ / f"{provider_id}.manifest.yaml"
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")
    return path


class _StubCredentialPort:
    """Minimal ICredentialPort stub for create_with_ports tests."""

    async def get_key(self, provider_id: str) -> str:
        return ""

    async def refresh_key(self, provider_id: str) -> str:  # pragma: no cover
        return ""


@pytest.fixture(autouse=True)
def _reset_spy_instances():
    _SpyPlugin.instances.clear()
    yield
    _SpyPlugin.instances.clear()


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch):
    monkeypatch.delenv("P22_TEST_API_KEY", raising=False)


# ---------------------------------------------------------------------------
# from_config -- construction paths
# ---------------------------------------------------------------------------


class TestFromConfigConstruction:
    @pytest.mark.asyncio
    async def test_ports_none_uses_standalone_path(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setenv("P22_TEST_API_KEY", "k1")
        _write_manifest(tmp_path, "alpha")
        config = ProviderConfig(providers=(ProviderEntry(provider_id="alpha"),))

        hub, result = await ModelHubFactory.from_config(config, ports=None, manifest_root=tmp_path)

        assert isinstance(hub, _HubCore)
        assert result.registered == ("alpha",)
        assert result.total == 1

    @pytest.mark.asyncio
    async def test_ports_dict_uses_with_ports_path(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setenv("P22_TEST_API_KEY", "k1")
        _write_manifest(tmp_path, "alpha")
        config = ProviderConfig(providers=(ProviderEntry(provider_id="alpha"),))

        hub, result = await ModelHubFactory.from_config(
            config,
            ports={"credential_port": _StubCredentialPort()},
            manifest_root=tmp_path,
        )

        assert isinstance(hub, _HubCore)
        assert result.registered == ("alpha",)


# ---------------------------------------------------------------------------
# from_config -- load outcomes
# ---------------------------------------------------------------------------


class TestFromConfigOutcomes:
    @pytest.mark.asyncio
    async def test_happy_path_registers_and_indexes_capability(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        monkeypatch.setenv("P22_TEST_API_KEY", "k1")
        _write_manifest(tmp_path, "alpha")
        config = ProviderConfig(providers=(ProviderEntry(provider_id="alpha"),))

        hub, result = await ModelHubFactory.from_config(config, manifest_root=tmp_path)

        assert result.registered == ("alpha",)
        capabilities = await hub.discover_capabilities()
        chat_providers = capabilities.get(CapabilityType.CHAT, [])
        assert "alpha" in chat_providers

    @pytest.mark.asyncio
    async def test_missing_env_var_skipped(self, tmp_path: Path) -> None:
        _write_manifest(tmp_path, "alpha")
        config = ProviderConfig(providers=(ProviderEntry(provider_id="alpha"),))

        hub, result = await ModelHubFactory.from_config(config, manifest_root=tmp_path)

        assert result.registered == ()
        assert len(result.skipped) == 1
        assert result.skipped[0][0] == "alpha"
        # Hub still constructed and queryable
        capabilities = await hub.discover_capabilities()
        assert capabilities == {} or all(not v for v in capabilities.values())

    @pytest.mark.asyncio
    async def test_bad_plugin_class_failed_loader_continues(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        monkeypatch.setenv("P22_TEST_API_KEY", "k1")
        _write_manifest(tmp_path, "good")
        _write_manifest(
            tmp_path,
            "bad",
            plugin_class="nonexistent.module.NoSuchClass",
        )
        config = ProviderConfig(
            providers=(
                ProviderEntry(provider_id="bad"),
                ProviderEntry(provider_id="good"),
            )
        )

        hub, result = await ModelHubFactory.from_config(config, manifest_root=tmp_path)

        assert result.registered == ("good",)
        assert len(result.failed) == 1
        assert result.failed[0][0] == "bad"
        assert isinstance(hub, _HubCore)

    @pytest.mark.asyncio
    async def test_double_call_records_failed_keeps_first_plugins(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        monkeypatch.setenv("P22_TEST_API_KEY", "k1")
        _write_manifest(tmp_path, "alpha")
        config = ProviderConfig(providers=(ProviderEntry(provider_id="alpha"),))

        hub, first = await ModelHubFactory.from_config(config, manifest_root=tmp_path)
        assert first.registered == ("alpha",)

        # Re-load against the SAME hub via the loader (mirrors what a
        # second from_config on the same hub would do internally if the
        # caller were to manually re-run the loader).
        from k1.model_hub.loader import ProviderLoader

        second = await ProviderLoader(hub, manifest_root=tmp_path).load(config)
        assert second.registered == ()
        assert len(second.failed) == 1
        assert second.failed[0][0] == "alpha"

        # First call's plugin still functional
        capabilities = await hub.discover_capabilities()
        assert "alpha" in capabilities.get(CapabilityType.CHAT, [])


# ---------------------------------------------------------------------------
# _HubCore.shutdown
# ---------------------------------------------------------------------------


class TestShutdown:
    @pytest.mark.asyncio
    async def test_empty_hub_returns_immediately(self, tmp_path: Path) -> None:
        config = ProviderConfig(providers=())
        hub, _result = await ModelHubFactory.from_config(config, manifest_root=tmp_path)
        await hub.shutdown()  # must not raise

    @pytest.mark.asyncio
    async def test_drains_all_registered_plugins(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setenv("P22_TEST_API_KEY", "k1")
        _write_manifest(tmp_path, "alpha")
        _write_manifest(tmp_path, "beta")
        config = ProviderConfig(
            providers=(
                ProviderEntry(provider_id="alpha"),
                ProviderEntry(provider_id="beta"),
            )
        )

        hub, result = await ModelHubFactory.from_config(config, manifest_root=tmp_path)
        assert sorted(result.registered) == ["alpha", "beta"]
        # Pull the registered plugins straight from the dispatcher's
        # plugin store -- avoids the dual-package class-identity issue
        # (importlib resolves the dotted path under tests.* but the
        # current module may also be loaded as familyos.tests.*).
        registered_plugins = list(hub._router._dispatcher._plugins.values())
        assert len(registered_plugins) == 2

        await hub.shutdown()

        assert all(p.close_call_count == 1 for p in registered_plugins)

    @pytest.mark.asyncio
    async def test_idempotent_second_call_safe(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setenv("P22_TEST_API_KEY", "k1")
        _write_manifest(tmp_path, "alpha")
        config = ProviderConfig(providers=(ProviderEntry(provider_id="alpha"),))

        hub, _result = await ModelHubFactory.from_config(config, manifest_root=tmp_path)
        await hub.shutdown()
        await hub.shutdown()  # must not raise; SpyPlugin.close is a counter, not a guard

        plugins = list(hub._router._dispatcher._plugins.values())
        assert len(plugins) == 1
        # Called both times; real plugins guard internally with _session.closed
        assert plugins[0].close_call_count == 2

    @pytest.mark.asyncio
    async def test_raising_close_logged_and_swallowed(
        self, tmp_path: Path, monkeypatch, caplog
    ) -> None:
        monkeypatch.setenv("P22_TEST_API_KEY", "k1")
        _write_manifest(tmp_path, "good")
        _write_manifest(tmp_path, "bad", plugin_class=_RAISING_PLUGIN_PATH)
        config = ProviderConfig(
            providers=(
                ProviderEntry(provider_id="good"),
                ProviderEntry(provider_id="bad"),
            )
        )

        hub, result = await ModelHubFactory.from_config(config, manifest_root=tmp_path)
        assert sorted(result.registered) == ["bad", "good"]

        with caplog.at_level(logging.WARNING, logger="k1.model_hub.factory"):
            await hub.shutdown()  # must not raise

        # Both plugins called close; the raising one logged a warning.
        registered = list(hub._router._dispatcher._plugins.values())
        assert len(registered) == 2
        assert all(p.close_call_count == 1 for p in registered)
        assert any("plugin close failed" in rec.message.lower() for rec in caplog.records)

    @pytest.mark.asyncio
    async def test_hanging_close_times_out_others_finish(
        self, tmp_path: Path, monkeypatch, caplog
    ) -> None:
        monkeypatch.setenv("P22_TEST_API_KEY", "k1")
        _write_manifest(tmp_path, "good")
        _write_manifest(tmp_path, "slow", plugin_class=_HANGING_PLUGIN_PATH)
        config = ProviderConfig(
            providers=(
                ProviderEntry(provider_id="good"),
                ProviderEntry(provider_id="slow"),
            )
        )

        hub, _result = await ModelHubFactory.from_config(config, manifest_root=tmp_path)

        # Patch the timeout constant down so the test runs quickly.
        import k1.model_hub.factory as factory_mod

        monkeypatch.setattr(factory_mod, "_PLUGIN_CLOSE_TIMEOUT_S", 0.1)

        with caplog.at_level(logging.WARNING, logger="k1.model_hub.factory"):
            await hub.shutdown()  # must not raise; slow plugin times out

        # The hanging plugin's close was started (counter incremented) but timed out.
        registered = list(hub._router._dispatcher._plugins.values())
        assert len(registered) == 2
        assert all(p.close_call_count == 1 for p in registered)
        # A TimeoutError was logged
        assert any("timeout" in rec.message.lower() for rec in caplog.records)
