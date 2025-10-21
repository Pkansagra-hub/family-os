from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

import yaml
from jsonschema import Draft7Validator
from ward import test  # type: ignore[import]

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS_DIR = REPO_ROOT / "k0" / "contracts"
OPENAPI_PATH = CONTRACTS_DIR / "openapi.k0.yaml"
ASYNCAPI_PATH = CONTRACTS_DIR / "asyncapi.events.yaml"


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
            index = int(part)
            target = target[index]
        elif isinstance(target, dict):
            target = target[part]
        else:
            raise KeyError(f"Encountered non-indexable segment for pointer {pointer}")
    return cast(Any, target)


def _validate_document_references(document: Any, *, base_path: Path) -> list[str]:
    errors: list[str] = []
    for ref in _iter_refs(document):
        if ref.startswith("#/"):
            try:
                _resolve_json_pointer(document, ref)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"Failed to resolve pointer '{ref}': {exc}")
        elif ref.startswith("./"):
            target_path = (base_path / ref).resolve()
            if not target_path.exists():
                errors.append(f"Referenced file '{ref}' not found")
                continue
            if target_path.suffix == ".json":
                try:
                    Draft7Validator.check_schema(json.loads(target_path.read_text()))
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"Schema at '{ref}' failed Draft7 check: {exc}")
        else:
            errors.append(f"Unsupported $ref format '{ref}'")
    return errors


@test("OpenAPI contract references resolve and schemas validate")
def openapi_contract_references_resolve() -> None:
    with OPENAPI_PATH.open("r", encoding="utf-8") as handle:
        document = yaml.safe_load(handle)

    errors = _validate_document_references(document, base_path=OPENAPI_PATH.parent)
    assert not errors, f"OpenAPI reference validation failed: {errors}"


@test("AsyncAPI contract references resolve and schemas validate")
def asyncapi_contract_references_resolve() -> None:
    with ASYNCAPI_PATH.open("r", encoding="utf-8") as handle:
        document = yaml.safe_load(handle)

    errors = _validate_document_references(document, base_path=ASYNCAPI_PATH.parent)
    assert not errors, f"AsyncAPI reference validation failed: {errors}"
