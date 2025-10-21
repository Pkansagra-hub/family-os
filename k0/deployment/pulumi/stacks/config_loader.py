"""Utility helpers for reading Pulumi configuration within stack modules."""

from __future__ import annotations

from typing import Any, Iterable, List, Mapping, Optional, Sequence, cast


def load_configs(*namespaces: str) -> List[Any]:
    try:
        pulumi_mod = __import__("pulumi")
    except ImportError:
        return []
    return [pulumi_mod.Config(namespace) for namespace in namespaces]


def _iter_configs(configs: Sequence[Any]) -> Iterable[Any]:
    for cfg in configs:
        if cfg is not None:
            yield cfg


def resolve_int(configs: Sequence[Any], keys: Sequence[str], default: int) -> int:
    for key in keys:
        value = _get_int(configs, key)
        if value is not None:
            return value
    return default


def resolve_bool(configs: Sequence[Any], keys: Sequence[str], default: bool) -> bool:
    for key in keys:
        value = _get_bool(configs, key)
        if value is not None:
            return value
    return default


def resolve_str(configs: Sequence[Any], keys: Sequence[str], default: str) -> str:
    for key in keys:
        value = _get_str(configs, key)
        if value is not None:
            return value
    return default


def resolve_mapping(
    configs: Sequence[Any], keys: Sequence[str], default: Mapping[str, Any]
) -> Mapping[str, Any]:
    for key in keys:
        value = _get_mapping(configs, key)
        if value is not None:
            return value
    return default


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


def _get_str(configs: Sequence[Any], key: str) -> Optional[str]:
    for cfg in _iter_configs(configs):
        getter = getattr(cfg, "get", None)
        if callable(getter):
            value = getter(key)
            if value is not None:
                return str(value)
    return None


def _get_mapping(configs: Sequence[Any], key: str) -> Optional[Mapping[str, Any]]:
    for cfg in _iter_configs(configs):
        getter = getattr(cfg, "get_object", None)
        if callable(getter):
            mapping = getter(key)
            if mapping is not None:
                if not isinstance(mapping, Mapping):
                    raise ValueError(f"Config key '{key}' must be a mapping")
                return cast(Mapping[str, Any], mapping)

        getter = getattr(cfg, "get", None)
        if callable(getter):
            raw_value = getter(key)
            if raw_value is not None and isinstance(raw_value, Mapping):
                return cast(Mapping[str, Any], raw_value)
    return None


def _coerce_int(value: Any, key: str) -> int:
    if isinstance(value, bool):
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
    except (TypeError, ValueError) as exc:  # pragma: no cover - defensive guard
        raise ValueError(f"Invalid integer for config key '{key}': {value}") from exc
