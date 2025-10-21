"""Utility for loading driver alias bindings."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

_DEFAULT_PATH = Path(__file__).with_name("alias_map.yaml")


@dataclass(slots=True)
class AliasMap:
    bindings: dict[str, str]

    @classmethod
    def from_file(cls, path: Path | str | None = None) -> "AliasMap":
        file_path = Path(path) if path is not None else _DEFAULT_PATH
        if not file_path.exists():
            raise FileNotFoundError(f"Alias map not found: {file_path}")
        with file_path.open("r", encoding="utf-8") as handle:
            data: dict[str, Any] = yaml.safe_load(handle) or {}
        aliases_raw = data.get("aliases", {})
        if not isinstance(aliases_raw, dict):
            raise ValueError("Expected 'aliases' mapping in alias_map.yaml")
        typed_aliases: dict[str, str] = {}
        for alias, driver in aliases_raw.items():
            if not isinstance(alias, str) or not isinstance(driver, str):
                raise ValueError("Alias map keys and values must be strings")
            typed_aliases[alias] = driver
        return cls(bindings=typed_aliases)

    def resolve(self, alias: str) -> str:
        return self.bindings[alias]
