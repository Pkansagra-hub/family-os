"""Locale resolution helpers for temporal anchors."""

from __future__ import annotations

from k1.temporal.config import TemporalConfig


def resolve_locale(
    device_locale: str | None,
    persona_locale: str | None = None,
    *,
    config: TemporalConfig | None = None,
) -> str:
    """Resolve locale with device preference first, then persona, then config."""

    cfg = config or TemporalConfig()
    return device_locale or persona_locale or cfg.default_locale


__all__ = ["resolve_locale"]
