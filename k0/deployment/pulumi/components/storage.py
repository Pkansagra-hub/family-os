"""Storage component utilities for Pulumi programs.

Implements filesystem artifacts and metadata exports used by Pulumi stacks.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple, cast

from .. import _renderer

logger = logging.getLogger(__name__)


def _empty_str_dict() -> dict[str, str]:
    """Return an empty mapping for dataclass default factories."""

    return {}


@dataclass(slots=True)
class StorageLayerConfig:
    """Declarative configuration for the FamilyOS storage tier."""

    enable_postgres: bool = False
    sqlite_path: str = "./data/k0.sqlite3"
    snapshot_bucket: Optional[str] = None
    blob_provider: str = "localfs"
    encryption_key_id: Optional[str] = None
    extra_tags: dict[str, str] = field(default_factory=_empty_str_dict)
    kernel_image: str = "ghcr.io/familyos/k0-kernel:latest"
    worker_image: str = "ghcr.io/familyos/k0-scheduler:latest"
    env_file: str = "./env/k0.env"
    kernel_port: int = 8080

    @classmethod
    def from_pulumi(
        cls,
        namespace: str = "k0-storage",
        *,
        fallback_namespace: str = "k0",
    ) -> "StorageLayerConfig":
        """Build a configuration instance from Pulumi config entries.

        The loader accepts snake_case keys (preferred) and will fall back to
        camelCase variants for compatibility with existing stacks.
        """

        defaults = cls()
        configs = _load_pulumi_configs(namespace, fallback_namespace)
        if not configs:
            return defaults

        bool_keys = ("enable_postgres", "enablePostgres")
        string_pairs = {
            "sqlite_path": ("sqlite_path", "sqlitePath"),
            "snapshot_bucket": ("snapshot_bucket", "snapshotBucket"),
            "blob_provider": ("blob_provider", "blobProvider"),
            "encryption_key_id": ("encryption_key_id", "encryptionKeyId"),
            "kernel_image": ("kernel_image", "kernelImage"),
            "worker_image": ("worker_image", "workerImage"),
            "env_file": ("env_file", "envFile"),
        }

        enable_postgres = _resolve_bool(configs, bool_keys, defaults.enable_postgres)
        sqlite_path = _resolve_str(
            configs, string_pairs["sqlite_path"], defaults.sqlite_path
        )
        snapshot_bucket = _resolve_optional_str(
            configs, string_pairs["snapshot_bucket"], defaults.snapshot_bucket
        )
        blob_provider = _resolve_str(
            configs, string_pairs["blob_provider"], defaults.blob_provider
        )
        encryption_key_id = _resolve_optional_str(
            configs, string_pairs["encryption_key_id"], defaults.encryption_key_id
        )
        kernel_image = _resolve_str(
            configs, string_pairs["kernel_image"], defaults.kernel_image
        )
        worker_image = _resolve_str(
            configs, string_pairs["worker_image"], defaults.worker_image
        )
        env_file = _resolve_str(configs, string_pairs["env_file"], defaults.env_file)
        kernel_port = _resolve_int(
            configs, ("kernel_port", "kernelPort"), defaults.kernel_port
        )

        extra_tags = _resolve_mapping(
            configs, ("extra_tags", "extraTags"), defaults.extra_tags
        )

        return cls(
            enable_postgres=enable_postgres,
            sqlite_path=sqlite_path,
            snapshot_bucket=snapshot_bucket,
            blob_provider=blob_provider,
            encryption_key_id=encryption_key_id,
            extra_tags=extra_tags,
            kernel_image=kernel_image,
            worker_image=worker_image,
            env_file=env_file,
            kernel_port=kernel_port,
        )

    @classmethod
    def from_mapping(cls, mapping: Dict[str, Any]) -> "StorageLayerConfig":
        """Hydrate configuration from a plain dictionary (tests / CLI usage)."""
        payload = dict(mapping)

        raw_extra_tags = payload.get("extra_tags", {})
        if raw_extra_tags is None:
            raw_extra_tags = {}
        if not isinstance(raw_extra_tags, Mapping):
            raise ValueError("extra_tags must be a mapping of string keys to values")
        raw_extra_tags_mapping = cast(Mapping[Any, Any], raw_extra_tags)
        extra_tags = _normalise_mapping(raw_extra_tags_mapping)

        return cls(
            enable_postgres=bool(payload.get("enable_postgres", False)),
            sqlite_path=str(payload.get("sqlite_path", "./data/k0.sqlite3")),
            snapshot_bucket=payload.get("snapshot_bucket"),
            blob_provider=str(payload.get("blob_provider", "localfs")),
            encryption_key_id=payload.get("encryption_key_id"),
            extra_tags=extra_tags,
            kernel_image=str(
                payload.get("kernel_image", "ghcr.io/familyos/k0-kernel:latest")
            ),
            worker_image=str(
                payload.get("worker_image", "ghcr.io/familyos/k0-scheduler:latest")
            ),
            env_file=str(payload.get("env_file", "./env/k0.env")),
            kernel_port=int(payload.get("kernel_port", 8080)),
        )


@dataclass(slots=True)
class StorageComponentResult:
    """Outputs and artifacts produced for the storage layer."""

    artifacts: List[_renderer.RenderedArtifact]
    outputs: Dict[str, Any]

    @property
    def compose_fragments(self) -> List[Path]:
        """Convenience accessor returning fragment paths as ``Path`` objects."""

        return [artifact.path for artifact in self.artifacts]


def _render_base_compose(
    *, stack_name: str, config: StorageLayerConfig
) -> _renderer.RenderedArtifact:
    context: Dict[str, Any] = {
        "kernel_image": config.kernel_image,
        "worker_image": config.worker_image,
        "env_file": config.env_file,
        "sqlite_path": config.sqlite_path,
        "kernel_port": config.kernel_port,
    }

    artifact = _renderer.write_template(
        "base.yml.j2",
        target_name=f"{stack_name}-storage.yml",
        context=context,
        subdir=stack_name,
    )

    logger.info(
        "Wrote storage compose fragment to %s (sha256=%s)",
        artifact.path,
        artifact.sha256,
    )

    return artifact


def register_storage_components(
    *, stack_name: str, config: StorageLayerConfig
) -> StorageComponentResult:
    """Materialise storage artifacts and metadata for downstream use."""

    compose_artifact = _render_base_compose(stack_name=stack_name, config=config)

    artifacts = [compose_artifact]

    outputs: Dict[str, Any] = {
        "compose_fragments": [str(artifact.path) for artifact in artifacts],
        "compose_artifacts": [artifact.as_output() for artifact in artifacts],
        "enable_postgres": config.enable_postgres,
        "sqlite_path": config.sqlite_path,
        "snapshot_bucket": config.snapshot_bucket,
        "blob_provider": config.blob_provider,
        "encryption_key_id": config.encryption_key_id,
        "extra_tags": dict(config.extra_tags),
        "kernel_image": config.kernel_image,
        "worker_image": config.worker_image,
        "env_file": config.env_file,
        "kernel_port": config.kernel_port,
    }

    if config.enable_postgres:
        outputs["postgresql"] = {
            "replicas": 1,
            "storage_class": "standard",
        }

    if config.snapshot_bucket:
        outputs["snapshots"] = {
            "bucket": config.snapshot_bucket,
        }

    return StorageComponentResult(artifacts=artifacts, outputs=outputs)


def _load_pulumi_configs(*namespaces: str) -> List[Any]:
    """Attempt to load Pulumi config objects for the requested namespaces."""

    try:
        pulumi_mod = __import__("pulumi")
    except ImportError:
        return []

    return [pulumi_mod.Config(namespace) for namespace in namespaces]


def _resolve_bool(configs: Sequence[Any], keys: Sequence[str], default: bool) -> bool:
    for key in keys:
        value = _get_bool(configs, key)
        if value is not None:
            return value
    return default


def _resolve_int(configs: Sequence[Any], keys: Sequence[str], default: int) -> int:
    for key in keys:
        value = _get_int(configs, key)
        if value is not None:
            return value
    return default


def _resolve_str(configs: Sequence[Any], keys: Sequence[str], default: str) -> str:
    result = _resolve_optional_str(configs, keys, None)
    return result if result is not None else default


def _resolve_optional_str(
    configs: Sequence[Any], keys: Sequence[str], default: Optional[str]
) -> Optional[str]:
    for key in keys:
        value = _get_str(configs, key)
        if value is not None:
            return value
    return default


def _resolve_mapping(
    configs: Sequence[Any], keys: Sequence[str], default: dict[str, str]
) -> dict[str, str]:
    for key in keys:
        mapping = _get_mapping(configs, key)
        if mapping is not None:
            return mapping
    return dict(default)


def _iter_configs(configs: Sequence[Any]) -> Iterable[Any]:
    for cfg in configs:
        if cfg is not None:
            yield cfg


def _get_bool(configs: Sequence[Any], key: str) -> Optional[bool]:
    for cfg in _iter_configs(configs):
        getter = getattr(cfg, "get_bool", None)
        if callable(getter):
            value = getter(key)
            if value is not None:
                return bool(value)

        raw_getter = getattr(cfg, "get", None)
        if callable(raw_getter):
            raw_value = raw_getter(key)
            if raw_value is not None:
                lowered = str(raw_value).strip().lower()
                if lowered in {"true", "1", "yes", "on"}:
                    return True
                if lowered in {"false", "0", "no", "off"}:
                    return False
    return None


def _get_int(configs: Sequence[Any], key: str) -> Optional[int]:
    for cfg in _iter_configs(configs):
        getter = getattr(cfg, "get_int", None)
        if callable(getter):
            value = getter(key)
            if value is not None:
                return _coerce_int(value, key)

        raw_getter = getattr(cfg, "get", None)
        if callable(raw_getter):
            raw_value = raw_getter(key)
            if raw_value is not None:
                return _coerce_int(raw_value, key)
    return None


def _get_str(configs: Sequence[Any], key: str) -> Optional[str]:
    for cfg in _iter_configs(configs):
        getter = getattr(cfg, "get", None)
        if callable(getter):
            value = getter(key)
            if value is not None:
                return str(value)
    return None


def _get_mapping(configs: Sequence[Any], key: str) -> Optional[dict[str, str]]:
    for cfg in _iter_configs(configs):
        getter = getattr(cfg, "get_object", None)
        if callable(getter):
            obj = getter(key)
            if obj is not None:
                if not isinstance(obj, Mapping):
                    raise ValueError(f"Config key '{key}' must resolve to a mapping")
                return _normalise_mapping(cast(Mapping[Any, Any], obj))

        raw_value = _get_str((cfg,), key)
        if raw_value is not None:
            try:
                parsed = json.loads(raw_value)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Config key '{key}' must be valid JSON mapping"
                ) from exc

            if not isinstance(parsed, Mapping):
                raise ValueError(f"Config key '{key}' must decode to a mapping")

            return _normalise_mapping(cast(Mapping[Any, Any], parsed))

    return None


def _coerce_int(value: Any, key: str) -> int:
    """Convert a Pulumi config value to ``int`` with helpful error messages."""

    if isinstance(value, bool):  # bool is a subclass of int; reject explicitly.
        raise ValueError(
            f"Config key '{key}' must be an integer, received boolean value instead"
        )

    try:
        if isinstance(value, int):
            return value
        text = str(value).strip()
        if not text:
            raise ValueError(f"Config key '{key}' cannot be blank")
        return int(text, 10)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid integer for config key '{key}': {value}") from exc


def _normalise_mapping(source: Mapping[Any, Any]) -> dict[str, str]:
    """Convert an arbitrary mapping into ``dict[str, str]``."""

    result: Dict[str, str] = {}
    for raw_key, raw_value in cast(Iterable[Tuple[Any, Any]], source.items()):
        result[str(raw_key)] = str(raw_value)
    return result
