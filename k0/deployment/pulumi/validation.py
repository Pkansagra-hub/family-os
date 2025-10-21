"""Validation helpers for Pulumi deployment artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence, cast

import yaml
from jsonschema import Draft7Validator
from jsonschema.exceptions import ValidationError

from . import _renderer

_SCHEMA_RESOURCE = "bundle_manifest.schema.json"


class BundleManifestValidationError(ValueError):
    """Raised when a bundle manifest fails schema validation."""

    def __init__(self, errors: Sequence[str]) -> None:
        message = "Bundle manifest validation failed:\n" + "\n".join(
            f"  - {line}" for line in errors
        )
        super().__init__(message)
        self.errors = list(errors)


@lru_cache(maxsize=1)
def _load_validator() -> Draft7Validator:
    schema_data = (
        resources.files("k0.deployment.pulumi.schema")
        .joinpath(_SCHEMA_RESOURCE)
        .read_text(encoding="utf-8")
    )
    schema = json.loads(schema_data)
    return Draft7Validator(schema)


def validate_bundle_manifest(manifest: Mapping[str, Any]) -> None:
    """Validate a bundle manifest mapping against the canonical schema."""

    validator = _load_validator()
    validator_any = cast(Any, validator)
    errors_iter = cast(Iterable[ValidationError], validator_any.iter_errors(manifest))
    errors: Sequence[ValidationError] = sorted(
        errors_iter, key=lambda err: tuple(err.path)
    )
    if errors:
        formatted = [
            f"{'/'.join(str(segment) for segment in error.path) or '<root>'}: {error.message}"
            for error in errors
        ]
        raise BundleManifestValidationError(formatted)


def load_and_validate_bundle_manifest(path: Path) -> Mapping[str, Any]:
    """Load a manifest from JSON or YAML and validate it."""

    text = path.read_text(encoding="utf-8")
    loaded: Any
    if path.suffix.lower() in {".yaml", ".yml"}:
        loaded = yaml.safe_load(text)
    else:
        loaded = json.loads(text)

    if not isinstance(loaded, Mapping):
        raise BundleManifestValidationError(["manifest root must be a mapping/object"])

    mapping_loaded = cast(Mapping[Any, Any], loaded)

    if not all(isinstance(key, str) for key in mapping_loaded.keys()):
        raise BundleManifestValidationError(["manifest keys must be strings"])

    manifest: dict[str, Any] = {
        str(key): value for key, value in mapping_loaded.items()
    }
    validate_bundle_manifest(manifest)
    return dict(manifest)


def _iter_manifest_candidates(target: Path) -> Iterable[Path]:
    if target.is_dir():
        for pattern in ("*bundle.json", "*bundle.yaml", "*bundle.yml"):
            yield from sorted(target.rglob(pattern))
    else:
        yield target


def _default_manifest_directory() -> Path:
    return _renderer.generated_directory()


def _validate_paths(targets: Sequence[Path]) -> list[Path]:
    validated: list[Path] = []
    errors: list[tuple[Path, BundleManifestValidationError]] = []

    for target in targets:
        for manifest_path in _iter_manifest_candidates(target):
            try:
                load_and_validate_bundle_manifest(manifest_path)
            except BundleManifestValidationError as exc:
                errors.append((manifest_path, exc))
            else:
                validated.append(manifest_path)

    if errors:
        message_lines = ["Bundle manifest validation failures detected:"]
        for manifest_path, exc in errors:
            message_lines.append(f"  - {manifest_path}:")
            message_lines.extend(f"      {line}" for line in exc.errors)
        raise SystemExit("\n".join(message_lines))

    return validated


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate K0 deployment bundle manifests against the schema.",
    )
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        help=(
            "Manifest files or directories to validate. Defaults to the "
            "generated compose directory if not provided."
        ),
    )
    return parser.parse_args(list(argv) if argv is not None else None)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.paths:
        targets = [Path(path).resolve() for path in args.paths]
    else:
        targets = [_default_manifest_directory()]

    validated = _validate_paths(targets)
    if validated:
        rel_paths = [str(path) for path in validated]
        print(
            "Validated bundle manifests:",
            "\n".join(f"  - {entry}" for entry in rel_paths),
            sep="\n",
        )
    else:
        print("No bundle manifest files found to validate.")

    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
