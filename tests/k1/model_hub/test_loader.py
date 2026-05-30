"""P2.1 -- ProviderLoader unit tests.

No live API calls. Uses an in-memory _HubCore via
ModelHubFactory.create_for_testing and a minimal stub plugin to exercise
every load outcome (registered / skipped / failed).
"""

from __future__ import annotations

from pathlib import Path
from typing import AsyncIterator

import pytest
import yaml

from k1.model_hub.events import TOPIC_PROVIDER_REGISTERED
from k1.model_hub.factory import ModelHubFactory
from k1.model_hub.loader import (
    ProviderConfig,
    ProviderEntry,
    ProviderLoader,
    _import_plugin_class,
)
from k1.model_hub.manifest import ProviderManifest
from k1.model_hub.plugins.base import (
    NormalizedRequest,
    ProviderChunk,
    ProviderHealth,
    ProviderResponse,
)
from k1.model_hub.ports.event_port import Subscription
from k1.model_hub.types import CapabilityType, HealthStatus

# ---------------------------------------------------------------------------
# Stub plugins
# ---------------------------------------------------------------------------


class _StubPlugin:
    """Minimal IProviderPlugin implementation. Records set_api_key calls."""

    def __init__(self) -> None:
        self.api_key: str | None = None
        self.initialized_with: ProviderManifest | None = None

    async def initialize(self, manifest: ProviderManifest) -> None:
        self.initialized_with = manifest

    def supports(self, capability: CapabilityType) -> bool:
        return True

    async def execute(self, request: NormalizedRequest) -> ProviderResponse:
        return ProviderResponse(text="stub")

    async def stream_execute(self, request: NormalizedRequest) -> AsyncIterator[ProviderChunk]:
        yield ProviderChunk(text="stub")

    def estimate_tokens(self, text: str) -> int:
        return len(text.split()) if isinstance(text, str) else 0

    async def health_check(self) -> ProviderHealth:
        return ProviderHealth(status=HealthStatus.HEALTHY)

    async def close(self) -> None:
        pass

    def set_api_key(self, key: str) -> None:
        self.api_key = key


class _NoApiKeyPlugin(_StubPlugin):
    """Same as _StubPlugin but without set_api_key (Ollama-style)."""

    set_api_key = None  # type: ignore[assignment]


class _BoomOnInitPlugin(_StubPlugin):
    async def initialize(self, manifest: ProviderManifest) -> None:
        raise RuntimeError("init exploded")


class _RecordingEventPort:
    def __init__(self) -> None:
        self.published: list[tuple[str, object]] = []

    async def publish(self, topic: str, payload: object) -> None:
        self.published.append((topic, payload))

    async def subscribe(self, topics, handler) -> Subscription:
        return Subscription(subscription_id="test-sub", topics=list(topics))


# Module-level so importlib can resolve them via dotted paths.
_PLUGIN_PATH = "tests.k1.model_hub.test_loader._StubPlugin"
_NO_KEY_PLUGIN_PATH = "tests.k1.model_hub.test_loader._NoApiKeyPlugin"
_BOOM_PLUGIN_PATH = "tests.k1.model_hub.test_loader._BoomOnInitPlugin"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_manifest(
    dir_: Path,
    provider_id: str,
    *,
    plugin_class: str = _PLUGIN_PATH,
    auth_type: str = "bearer",
    credential_key: str = "TEST_API_KEY",
) -> Path:
    """Write a minimal manifest YAML file. Returns the path."""
    payload = {
        "provider_id": provider_id,
        "display_name": f"Test {provider_id}",
        "plugin_class": plugin_class,
        "api_base": "https://example.invalid",
        "auth": {
            "type": auth_type,
            "credential_key": credential_key,
        },
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


@pytest.fixture
def manifest_dir(tmp_path: Path) -> Path:
    """Per-test manifest directory."""
    return tmp_path


@pytest.fixture
def hub():
    """Real _HubCore via the for-testing factory (no live network)."""
    facade, _adapters = ModelHubFactory.create_for_testing()
    return facade


# ---------------------------------------------------------------------------
# ProviderEntry / ProviderConfig
# ---------------------------------------------------------------------------


class TestProviderConfig:
    def test_entry_defaults(self) -> None:
        entry = ProviderEntry(provider_id="google")
        assert entry.provider_id == "google"
        assert entry.manifest_path is None
        assert entry.plugin_class is None
        assert entry.enabled is True

    def test_default_lists_all_known_providers(self) -> None:
        config = ProviderConfig.default()
        ids = [e.provider_id for e in config.providers]
        # Default is intentionally restricted to env-var-gated cloud
        # providers; self-hosted (ollama/vllm) require explicit opt-in.
        assert ids == ["google", "openai", "anthropic"]
        assert all(e.enabled for e in config.providers)

    def test_from_env_empty_keeps_legacy_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LLM_PROVIDER", "vertex")
        config = ProviderConfig.from_env({})
        assert [e.provider_id for e in config.providers] == ["google", "openai", "anthropic"]

    def test_from_env_google_loads_only_developer_api_provider(self) -> None:
        config = ProviderConfig.from_env({"LLM_PROVIDER": "google"})
        assert [e.provider_id for e in config.providers] == ["google"]

    def test_from_env_vertex_loads_only_agent_platform_provider(self) -> None:
        config = ProviderConfig.from_env({"LLM_PROVIDER": "vertex"})
        assert [e.provider_id for e in config.providers] == ["vertex"]

    def test_from_env_cloud_alias_loads_vertex(self) -> None:
        config = ProviderConfig.from_env({"LLM_PROVIDER": "agent-platform"})
        assert [e.provider_id for e in config.providers] == ["vertex"]

    def test_from_env_vertexai_flag_loads_vertex_when_provider_unset(self) -> None:
        config = ProviderConfig.from_env({"GOOGLE_GENAI_USE_VERTEXAI": "True"})
        assert [e.provider_id for e in config.providers] == ["vertex"]


# ---------------------------------------------------------------------------
# _import_plugin_class
# ---------------------------------------------------------------------------


class TestImportPluginClass:
    def test_resolves_known_class(self) -> None:
        cls = _import_plugin_class(_PLUGIN_PATH)
        assert cls.__name__ == "_StubPlugin"
        assert cls.__module__.endswith("tests.k1.model_hub.test_loader")

    def test_rejects_undotted_path(self) -> None:
        with pytest.raises(ValueError):
            _import_plugin_class("StubPlugin")

    def test_missing_attribute(self) -> None:
        with pytest.raises(ImportError):
            _import_plugin_class("tests.k1.model_hub.test_loader.NotAClassName")

    def test_missing_module(self) -> None:
        with pytest.raises(ImportError):
            _import_plugin_class("does.not.exist.NoClass")


# ---------------------------------------------------------------------------
# Loader happy / skip / fail paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestProviderLoader:
    async def test_happy_path_registers(
        self, hub, manifest_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _write_manifest(manifest_dir, "stubco")
        monkeypatch.setenv("TEST_API_KEY", "secret-123")

        loader = ProviderLoader(hub, manifest_root=manifest_dir)
        result = await loader.load(ProviderConfig(providers=(ProviderEntry(provider_id="stubco"),)))

        assert result.registered == ("stubco",)
        assert result.skipped == ()
        assert result.failed == ()
        assert result.total == 1

    async def test_happy_path_publishes_provider_registered(
        self, hub, manifest_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _write_manifest(manifest_dir, "evented")
        monkeypatch.setenv("TEST_API_KEY", "secret-123")
        event_port = _RecordingEventPort()

        loader = ProviderLoader(hub, manifest_root=manifest_dir, event_port=event_port)
        result = await loader.load(
            ProviderConfig(providers=(ProviderEntry(provider_id="evented"),))
        )

        assert result.registered == ("evented",)
        assert event_port.published == [
            (
                TOPIC_PROVIDER_REGISTERED,
                {
                    "provider_id": "evented",
                    "capabilities": ["CHAT"],
                    "model_count": 1,
                },
            )
        ]

    async def test_missing_env_var_skipped(
        self, hub, manifest_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _write_manifest(manifest_dir, "needskey", credential_key="UNSET_KEY_XYZ")
        monkeypatch.delenv("UNSET_KEY_XYZ", raising=False)

        loader = ProviderLoader(hub, manifest_root=manifest_dir)
        result = await loader.load(
            ProviderConfig(providers=(ProviderEntry(provider_id="needskey"),))
        )

        assert result.registered == ()
        assert len(result.skipped) == 1
        assert result.skipped[0][0] == "needskey"
        assert "UNSET_KEY_XYZ" in result.skipped[0][1]
        assert result.failed == ()

    async def test_disabled_entry_skipped(self, hub, manifest_dir: Path) -> None:
        loader = ProviderLoader(hub, manifest_root=manifest_dir)
        result = await loader.load(
            ProviderConfig(providers=(ProviderEntry(provider_id="any", enabled=False),))
        )
        assert result.skipped == (("any", "disabled in config"),)
        assert result.registered == ()

    async def test_missing_manifest_skipped(self, hub, manifest_dir: Path) -> None:
        loader = ProviderLoader(hub, manifest_root=manifest_dir)
        result = await loader.load(ProviderConfig(providers=(ProviderEntry(provider_id="ghost"),)))
        assert result.registered == ()
        assert len(result.skipped) == 1
        assert "manifest not found" in result.skipped[0][1]

    async def test_auth_none_registers_without_env_var(
        self, hub, manifest_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _write_manifest(
            manifest_dir,
            "ollama_like",
            plugin_class=_NO_KEY_PLUGIN_PATH,
            auth_type="none",
            credential_key="",
        )
        loader = ProviderLoader(hub, manifest_root=manifest_dir)
        result = await loader.load(
            ProviderConfig(providers=(ProviderEntry(provider_id="ollama_like"),))
        )
        assert result.registered == ("ollama_like",)

    async def test_bad_plugin_path_failed(
        self, hub, manifest_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _write_manifest(
            manifest_dir,
            "broken",
            plugin_class="does.not.exist.NoClass",
        )
        monkeypatch.setenv("TEST_API_KEY", "x")
        loader = ProviderLoader(hub, manifest_root=manifest_dir)
        result = await loader.load(ProviderConfig(providers=(ProviderEntry(provider_id="broken"),)))
        assert result.registered == ()
        assert len(result.failed) == 1
        assert "import" in result.failed[0][1]

    async def test_initialize_failure_recorded(
        self, hub, manifest_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _write_manifest(
            manifest_dir,
            "boom",
            plugin_class=_BOOM_PLUGIN_PATH,
        )
        monkeypatch.setenv("TEST_API_KEY", "x")
        loader = ProviderLoader(hub, manifest_root=manifest_dir)
        result = await loader.load(ProviderConfig(providers=(ProviderEntry(provider_id="boom"),)))
        assert result.registered == ()
        assert len(result.failed) == 1
        assert "initialize" in result.failed[0][1]

    async def test_duplicate_provider_id_failed(
        self, hub, manifest_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _write_manifest(manifest_dir, "twice")
        monkeypatch.setenv("TEST_API_KEY", "x")
        loader = ProviderLoader(hub, manifest_root=manifest_dir)
        # First load should register; second hits ProviderRegistry's
        # ValueError on duplicate provider_id and is recorded as failed.
        first = await loader.load(ProviderConfig(providers=(ProviderEntry(provider_id="twice"),)))
        assert first.registered == ("twice",)
        second = await loader.load(ProviderConfig(providers=(ProviderEntry(provider_id="twice"),)))
        assert second.registered == ()
        assert len(second.failed) == 1
        assert "register_plugin" in second.failed[0][1]

    async def test_set_api_key_called_when_present(
        self, hub, manifest_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verify the plugin actually receives the resolved API key."""
        _write_manifest(manifest_dir, "checked", credential_key="MY_KEY")
        monkeypatch.setenv("MY_KEY", "the-secret")
        loader = ProviderLoader(hub, manifest_root=manifest_dir)
        result = await loader.load(
            ProviderConfig(providers=(ProviderEntry(provider_id="checked"),))
        )
        assert result.registered == ("checked",)
        # Confirm via the registry that the plugin is the one we wrote
        # and that set_api_key fired with the env value.
        plugin = hub._registry.get_plugin("checked")
        assert type(plugin).__name__ == "_StubPlugin"
        assert plugin.api_key == "the-secret"

    async def test_mixed_outcome_total_consistent(
        self, hub, manifest_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _write_manifest(manifest_dir, "good")
        _write_manifest(manifest_dir, "skipme", credential_key="UNSET_FOO")
        _write_manifest(manifest_dir, "bad", plugin_class="does.not.exist.NoClass")
        monkeypatch.setenv("TEST_API_KEY", "x")
        monkeypatch.delenv("UNSET_FOO", raising=False)
        loader = ProviderLoader(hub, manifest_root=manifest_dir)
        result = await loader.load(
            ProviderConfig(
                providers=(
                    ProviderEntry(provider_id="good"),
                    ProviderEntry(provider_id="skipme"),
                    ProviderEntry(provider_id="bad"),
                    ProviderEntry(provider_id="ghost"),  # missing manifest
                )
            )
        )
        assert result.registered == ("good",)
        skipped_ids = [s[0] for s in result.skipped]
        failed_ids = [f[0] for f in result.failed]
        assert "skipme" in skipped_ids
        assert "ghost" in skipped_ids
        assert "bad" in failed_ids
        assert result.total == 4
