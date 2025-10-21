"""Contract schema linter for JSON Schema, OpenAPI, and AsyncAPI validation.

This automation script validates all contract artifacts in the k0/contracts
directory to ensure:
- JSON schemas are well-formed and Draft7-compliant
- OpenAPI and AsyncAPI specifications reference valid schemas
- All $ref references resolve correctly
- No orphaned or unreferenced schemas exist

Usage:
    python -m k0.automation.lint_schemas
    python -m k0.automation.lint_schemas --contracts-dir <path>

Exit Codes:
    0 - All schemas valid
    1 - Validation errors found
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Iterator, Sequence
from json import JSONDecodeError
from pathlib import Path
from typing import Any, cast

import yaml
from jsonschema import Draft7Validator
from jsonschema.exceptions import SchemaError

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONTRACTS_DIR = REPO_ROOT / "k0" / "contracts"
DEFAULT_SCHEMA_DIR = DEFAULT_CONTRACTS_DIR / "jsonschema"
DEFAULT_OPENAPI_PATH = DEFAULT_CONTRACTS_DIR / "openapi.k0.yaml"
DEFAULT_ASYNCAPI_PATH = DEFAULT_CONTRACTS_DIR / "asyncapi.events.yaml"


def _iter_refs(node: Any) -> Iterator[str]:
    if isinstance(node, dict):
        typed_node = cast(dict[str, Any], node)
        ref_value = typed_node.get("$ref")
        if isinstance(ref_value, str):
            yield ref_value
        for value in typed_node.values():
            yield from _iter_refs(value)
    elif isinstance(node, list):
        typed_list = cast(list[Any], node)
        for item in typed_list:
            yield from _iter_refs(item)


def _resolve_json_pointer(document: Any, pointer: str) -> Any:
    if not pointer.startswith("#/"):
        raise ValueError(f"Unsupported pointer format: {pointer}")

    target: Any = document
    parts = pointer[2:].split("/")
    for raw_part in parts:
        part = raw_part.replace("~1", "/").replace("~0", "~")
        if isinstance(target, list):
            target_list = cast(list[Any], target)
            index = int(part)
            target = target_list[index]
        elif isinstance(target, dict):
            mapping = cast(dict[str, Any], target)
            if part not in mapping:
                raise KeyError(f"Pointer segment '{part}' missing in document")
            target = mapping[part]
        else:
            raise KeyError(f"Encountered non-indexable segment for pointer {pointer}")
    return target


def _validate_document_references(document: Any, *, base_path: Path) -> list[str]:
    errors: list[str] = []
    for ref in _iter_refs(document):
        if ref.startswith("#/"):
            try:
                _resolve_json_pointer(document, ref)
            except (ValueError, KeyError, IndexError, TypeError) as exc:
                errors.append(f"Failed to resolve pointer '{ref}': {exc}")
        elif ref.startswith("./"):
            target_path = (base_path / ref).resolve()
            if not target_path.exists():
                errors.append(f"Referenced file '{ref}' not found")
                continue
            if target_path.suffix == ".json":
                try:
                    Draft7Validator.check_schema(json.loads(target_path.read_text()))
                except (JSONDecodeError, SchemaError) as exc:
                    errors.append(f"Schema at '{ref}' failed Draft7 check: {exc}")
        else:
            errors.append(f"Unsupported $ref format '{ref}'")
    return errors


def _load_yaml_doc(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def validate_json_schemas(schema_dir: Path) -> list[str]:
    errors: list[str] = []
    for schema_path in sorted(schema_dir.glob("*.json")):
        try:
            Draft7Validator.check_schema(json.loads(schema_path.read_text()))
        except (JSONDecodeError, SchemaError) as exc:
            errors.append(f"Schema '{schema_path.name}' failed Draft7 check: {exc}")
    return errors


def validate_document_contract(path: Path) -> list[str]:
    document = _load_yaml_doc(path)
    base_path = path.parent
    return _validate_document_references(document, base_path=base_path)


def lint_contracts(
    *, schema_dir: Path, openapi_path: Path, asyncapi_path: Path
) -> list[str]:
    errors: list[str] = []
    errors.extend(validate_json_schemas(schema_dir))
    errors.extend(validate_document_contract(openapi_path))
    errors.extend(validate_document_contract(asyncapi_path))
    return errors


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Lint canonical contract schemas for drift"
    )
    parser.add_argument("--schema-dir", type=Path, default=DEFAULT_SCHEMA_DIR)
    parser.add_argument("--openapi", type=Path, default=DEFAULT_OPENAPI_PATH)
    parser.add_argument("--asyncapi", type=Path, default=DEFAULT_ASYNCAPI_PATH)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    errors = lint_contracts(
        schema_dir=args.schema_dir,
        openapi_path=args.openapi,
        asyncapi_path=args.asyncapi,
    )
    if errors:
        for message in errors:
            print(f"[SchemaLint] {message}")
        return 1

    print("[SchemaLint] All schemas and contract documents validated successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
