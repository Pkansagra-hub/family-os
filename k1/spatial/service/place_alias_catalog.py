"""Curated place alias helpers."""

from __future__ import annotations

import unicodedata

DEFAULT_PLACE_ALIASES: dict[str, tuple[str, ...]] = {
    "home": ("house", "my house", "our house", "family home", "home"),
    "school": ("school", "campus", "classroom"),
    "work": ("office", "work", "workplace"),
    "vehicle": ("car", "vehicle", "van"),
}


def normalize_place_label(value: object) -> str:
    """Normalize a user/device place label for deterministic matching."""
    text = unicodedata.normalize("NFKC", str(value or "")).strip().lower()
    return " ".join(text.replace("_", " ").replace("-", " ").split())


def expanded_aliases(label: str, aliases: tuple[str, ...] = ()) -> tuple[str, ...]:
    """Return normalized aliases for a place label and common place-kind labels."""
    normalized = normalize_place_label(label)
    values = {normalized, *(normalize_place_label(item) for item in aliases)}
    values.update(DEFAULT_PLACE_ALIASES.get(normalized, ()))
    return tuple(sorted(item for item in values if item))


__all__ = ["DEFAULT_PLACE_ALIASES", "expanded_aliases", "normalize_place_label"]
