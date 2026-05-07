"""Manifest discovery + meta-schema validation.

Loads every YAML under ``bridge/contracts/manifests/`` and validates it
against ``bridge/contracts/_meta/manifest.schema.json``. Returns a list of
:class:`Manifest` records sorted by topic for determinism.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator


class ManifestValidationError(ValueError):
    """Raised when one or more manifests fail meta-schema validation."""


@dataclass(frozen=True)
class Manifest:
    """Parsed + validated bridge contract manifest."""

    topic: str
    direction: str
    owner_team: str
    status: str
    schema_path: str
    source_path: Path
    raw: dict[str, Any] = field(repr=False)

    @property
    def producer_kernel(self) -> str:
        return self.raw["producer"]["kernel"]

    @property
    def consumer_kernel(self) -> str:
        return self.raw["consumer"]["kernel"]

    @property
    def paired_with(self) -> str | None:
        """Topic of the paired response manifest, or None for fire-and-forget."""
        value = self.raw.get("paired_with")
        return value if isinstance(value, str) else None


def _meta_schema_path(contracts_root: Path) -> Path:
    return contracts_root / "_meta" / "manifest.schema.json"


def load_meta_schema(contracts_root: Path) -> dict[str, Any]:
    """Read and parse the manifest meta-schema."""
    return json.loads(_meta_schema_path(contracts_root).read_text(encoding="utf-8"))


def discover_manifest_files(contracts_root: Path) -> list[Path]:
    """List manifest YAMLs in deterministic (sorted) order."""
    manifests_dir = contracts_root / "manifests"
    if not manifests_dir.exists():
        return []
    return sorted(p for p in manifests_dir.glob("*.yaml") if p.is_file())


def load_manifests(contracts_root: Path) -> list[Manifest]:
    """Load + validate every manifest under ``contracts_root/manifests/``.

    Raises :class:`ManifestValidationError` on the first invalid manifest
    with a message listing every error across all manifests (so authors
    see all problems at once).
    """
    schema = load_meta_schema(contracts_root)
    validator = Draft202012Validator(schema)

    manifests: list[Manifest] = []
    errors: list[str] = []
    for path in discover_manifest_files(contracts_root):
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            errors.append(f"{path.name}: YAML parse error: {exc}")
            continue
        if not isinstance(raw, dict):
            errors.append(f"{path.name}: top-level YAML must be a mapping")
            continue
        local_errors = sorted(validator.iter_errors(raw), key=lambda e: e.path)
        if local_errors:
            for err in local_errors:
                errors.append(f"{path.name}: {err.message}")
            continue
        manifests.append(
            Manifest(
                topic=raw["topic"],
                direction=raw["direction"],
                owner_team=raw["owner_team"],
                status=raw["status"],
                schema_path=raw["schema"],
                source_path=path,
                raw=raw,
            )
        )

    if errors:
        raise ManifestValidationError("manifest validation failed:\n  " + "\n  ".join(errors))

    manifests.sort(key=lambda m: m.topic)

    # Cross-manifest invariant: every paired_with topic must resolve to an
    # existing manifest. Expressing this in JSON Schema across separate files
    # would require a custom $ref resolver; doing it here keeps the meta-schema
    # local-per-file and gives authors clearer error messages.
    topics = {m.topic for m in manifests}
    pair_errors: list[str] = []
    for m in manifests:
        partner = m.paired_with
        if partner is not None and partner not in topics:
            pair_errors.append(
                f"{m.source_path.name}: paired_with references unknown topic "
                f"{partner!r}; partner manifest must exist under manifests/"
            )
    if pair_errors:
        raise ManifestValidationError("manifest validation failed:\n  " + "\n  ".join(pair_errors))

    return manifests
