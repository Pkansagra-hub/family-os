"""Declarative provider config + ProviderLoader (P2.1).

Replaces the kernel's per-provider hand-coded registration with a single
config-driven loader. Reads `ProviderConfig`, instantiates each plugin
via the manifest's dotted ``plugin_class`` path, awaits ``initialize``,
calls ``set_api_key`` when both an env-var key is present AND the plugin
exposes the method, and registers via ``hub.register_plugin(manifest, plugin)``.

The loader never raises on per-provider failure: each entry's outcome
(registered/skipped/failed) is recorded in :class:`ProviderLoadResult`
and the caller decides how to surface it.
"""

from __future__ import annotations

import importlib
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from k1.model_hub.manifest import ProviderManifest, load_manifest

if TYPE_CHECKING:
    from k1.model_hub.factory import _HubCore
    from k1.model_hub.plugins.base import IProviderPlugin

logger = logging.getLogger(__name__)

# Default location for `{provider_id}.manifest.yaml` files.
_DEFAULT_MANIFEST_ROOT = Path(__file__).resolve().parents[1] / "config" / "providers"

# Providers auto-enabled by ``ProviderConfig.default()``. Restricted to
# the env-var-gated cloud providers so that local self-hosted plugins
# (Ollama at ``localhost:11434``, vLLM at a configurable host) do NOT get
# wired into the dispatcher's fallback chain unless a deployment opts in.
# Add an entry explicitly via :class:`ProviderEntry` to enable them.
_KNOWN_PROVIDERS: tuple[str, ...] = (
    "google",
    "openai",
    "anthropic",
)


@dataclass(frozen=True)
class ProviderEntry:
    """One provider's load instructions.

    ``manifest_path`` and ``plugin_class`` are optional: when omitted, the
    loader resolves them from convention (``{root}/{provider_id}.manifest.yaml``)
    and from the manifest's own ``plugin_class`` field.
    """

    provider_id: str
    manifest_path: Path | None = None
    plugin_class: str | None = None
    enabled: bool = True


@dataclass(frozen=True)
class ProviderConfig:
    """Ordered tuple of provider entries to load."""

    providers: tuple[ProviderEntry, ...]

    @classmethod
    def default(cls) -> "ProviderConfig":
        """Enable every known provider; loader skips ones with missing env vars."""
        return cls(providers=tuple(ProviderEntry(provider_id=pid) for pid in _KNOWN_PROVIDERS))


@dataclass(frozen=True)
class ProviderLoadResult:
    """Outcome of one ``ProviderLoader.load`` invocation."""

    registered: tuple[str, ...] = field(default_factory=tuple)
    skipped: tuple[tuple[str, str], ...] = field(default_factory=tuple)
    failed: tuple[tuple[str, str], ...] = field(default_factory=tuple)

    @property
    def total(self) -> int:
        return len(self.registered) + len(self.skipped) + len(self.failed)


def _import_plugin_class(dotted_path: str) -> type:
    """Resolve a dotted ``module.Class`` path to its class object."""
    if "." not in dotted_path:
        raise ValueError(f"plugin_class must be a dotted path, got {dotted_path!r}")
    module_path, _, class_name = dotted_path.rpartition(".")
    module = importlib.import_module(module_path)
    try:
        return getattr(module, class_name)
    except AttributeError as exc:
        raise ImportError(
            f"plugin_class {dotted_path!r}: module {module_path!r} has no attribute {class_name!r}"
        ) from exc


class ProviderLoader:
    """Loads providers declared in a :class:`ProviderConfig` into an ``_HubCore``.

    Idempotency: the loader does NOT pre-check ``is_registered``. If a
    duplicate ``provider_id`` reaches ``ProviderRegistry.register`` the
    registry raises ``ValueError`` and the entry is recorded as ``failed``
    — the loader continues with the rest. Callers wanting stricter
    semantics should inspect the result.
    """

    def __init__(
        self,
        hub: "_HubCore",
        *,
        manifest_root: Path | None = None,
    ) -> None:
        self._hub = hub
        self._manifest_root = manifest_root or _DEFAULT_MANIFEST_ROOT

    async def load(self, config: ProviderConfig) -> ProviderLoadResult:
        registered: list[str] = []
        skipped: list[tuple[str, str]] = []
        failed: list[tuple[str, str]] = []

        for entry in config.providers:
            if not entry.enabled:
                skipped.append((entry.provider_id, "disabled in config"))
                continue

            try:
                outcome = await self._load_one(entry)
            except Exception as exc:  # pragma: no cover -- defensive
                failed.append((entry.provider_id, repr(exc)))
                logger.warning(
                    "ProviderLoader: %s failed with unhandled exception: %s",
                    entry.provider_id,
                    exc,
                )
                continue

            kind, detail = outcome
            if kind == "registered":
                registered.append(entry.provider_id)
            elif kind == "skipped":
                skipped.append((entry.provider_id, detail))
            else:
                failed.append((entry.provider_id, detail))

        result = ProviderLoadResult(
            registered=tuple(registered),
            skipped=tuple(skipped),
            failed=tuple(failed),
        )
        logger.info(
            "ProviderLoader: registered=%s skipped=%s failed=%s",
            result.registered,
            result.skipped,
            result.failed,
        )
        return result

    async def _load_one(self, entry: ProviderEntry) -> tuple[str, str]:
        """Load one entry. Returns ``(kind, detail)`` where ``kind`` is
        ``registered`` | ``skipped`` | ``failed`` and ``detail`` is a
        human-readable explanation (empty string when registered).
        """
        # 1. Resolve manifest path
        manifest_path = entry.manifest_path or (
            self._manifest_root / f"{entry.provider_id}.manifest.yaml"
        )
        if not manifest_path.is_file():
            return ("skipped", f"manifest not found at {manifest_path}")

        # 2. Load manifest
        try:
            manifest = load_manifest(manifest_path)
        except Exception as exc:
            return ("failed", f"load_manifest: {exc!r}")

        # 3. Resolve plugin class
        plugin_class_path = entry.plugin_class or manifest.plugin_class
        if not plugin_class_path:
            return ("failed", "plugin_class not set on entry or manifest")
        try:
            PluginCls = _import_plugin_class(plugin_class_path)
        except Exception as exc:
            return ("failed", f"import {plugin_class_path}: {exc!r}")

        # 4. Instantiate + initialize
        try:
            plugin: "IProviderPlugin" = PluginCls()
            await plugin.initialize(manifest)
        except Exception as exc:
            return ("failed", f"initialize: {exc!r}")

        # 5. Credential resolution. ``manifest.auth.credential_key`` is the
        #    env-var name. If auth.type == "none" we don't require a key
        #    (Ollama). Otherwise a missing env var → skip (not failure).
        env_var = manifest.auth.credential_key
        api_key = os.environ.get(env_var) if env_var else None
        if manifest.auth.type != "none":
            if not api_key:
                return ("skipped", f"env var {env_var!r} not set")
            set_api_key = getattr(plugin, "set_api_key", None)
            if callable(set_api_key):
                try:
                    set_api_key(api_key)
                except Exception as exc:
                    return ("failed", f"set_api_key: {exc!r}")
            else:
                logger.debug(
                    "ProviderLoader: %s plugin has no set_api_key method; skipping",
                    entry.provider_id,
                )
        elif api_key:
            # auth.type == "none" but env var is present — set if supported.
            set_api_key = getattr(plugin, "set_api_key", None)
            if callable(set_api_key):
                try:
                    set_api_key(api_key)
                except Exception:
                    pass  # auth.type=none means key is optional

        # 6. Register with the hub (both registry + dispatcher).
        try:
            self._hub.register_plugin(manifest, plugin)
        except Exception as exc:
            return ("failed", f"register_plugin: {exc!r}")

        return ("registered", "")
