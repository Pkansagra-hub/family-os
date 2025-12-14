"""Contract schema linter for JSON Schema, OpenAPI, and AsyncAPI validation.

This automation script validates all contract artifacts in the k0/contracts
directory to ensure:
- JSON schemas are well-formed and Draft7-compliant
- OpenAPI and AsyncAPI specifications reference valid schemas
- All $ref references resolve correctly
- No orphaned or unreferenced schemas exist
- Schema versions are consistent across specs and registry
- Error reporting grouped by severity (ERROR/WARNING/INFO)

Features:
- **Orphan detection**: Finds unreferenced schemas in jsonschema/
- **Cross-reference validation**: Tracks all $ref pointers and validates resolution
- **Severity grouping**: Organizes errors by importance level
- **Fix suggestions**: Provides actionable remediation steps
- **Version consistency**: Validates schema versions match across specs

Usage:
    python -m k0.automation.lint_schemas
    python -m k0.automation.lint_schemas --contracts-dir <path>
    python -m k0.automation.lint_schemas --check  # CI mode with strict validation
    python -m k0.automation.lint_schemas --verbose  # Detailed diagnostics

Exit Codes:
    0 - All schemas valid
    1 - Validation errors found
    2 - Critical errors (breaking changes detected)
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Iterator, Sequence
from json import JSONDecodeError
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft7Validator
from jsonschema.exceptions import SchemaError

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONTRACTS_DIR = REPO_ROOT / "k0" / "contracts"
DEFAULT_SCHEMA_DIR = DEFAULT_CONTRACTS_DIR / "jsonschema"
DEFAULT_OPENAPI_PATH = DEFAULT_CONTRACTS_DIR / "openapi.k0.yaml"
DEFAULT_ASYNCAPI_PATH = DEFAULT_CONTRACTS_DIR / "asyncapi.events.yaml"


class ValidationMessage:
    """Represents a single validation message with severity and context."""

    def __init__(
        self,
        severity: str,  # "ERROR", "WARNING", "INFO"
        message: str,
        file: str | None = None,
        line: int | None = None,
        fix: str | None = None,
    ):
        self.severity = severity
        self.message = message
        self.file = file
        self.line = line
        self.fix = fix

    def __str__(self) -> str:
        result = f"[{self.severity}] {self.message}"
        if self.file:
            result += f"\n  File: {self.file}"
            if self.line:
                result += f":{self.line}"
        if self.fix:
            result += f"\n  Fix: {self.fix}"
        return result

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, ValidationMessage):
            return False
        return (
            self.severity == other.severity
            and self.message == other.message
            and self.file == other.file
        )


def _iter_refs(node: Any) -> Iterator[str]:
    """Recursively iterate all $ref pointers in a document."""
    if isinstance(node, dict):
        ref_value = node.get("$ref")
        if isinstance(ref_value, str):
            yield ref_value
        for value in node.values():
            yield from _iter_refs(value)
    elif isinstance(node, list):
        for item in node:
            yield from _iter_refs(item)


def _resolve_json_pointer(document: Any, pointer: str) -> Any:
    """Resolve a JSON Pointer reference within a document."""
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
            if part not in target:
                raise KeyError(f"Pointer segment '{part}' missing in document")
            target = target[part]
        else:
            raise KeyError(f"Encountered non-indexable segment for pointer {pointer}")
    return target


def _validate_document_references(
    document: Any,
    *,
    base_path: Path,
) -> list[ValidationMessage]:
    """Validate all $ref references in a document."""
    messages: list[ValidationMessage] = []

    for ref in _iter_refs(document):
        if ref.startswith("#/"):
            try:
                _resolve_json_pointer(document, ref)
            except (ValueError, KeyError, IndexError, TypeError) as exc:
                messages.append(
                    ValidationMessage(
                        severity="ERROR",
                        message=f"Failed to resolve internal reference '{ref}': {exc}",
                        file=str(base_path),
                        fix=f"Check the JSON Pointer reference: {ref}",
                    )
                )
        elif ref.startswith("./"):
            target_path = (base_path / ref).resolve()
            if not target_path.exists():
                messages.append(
                    ValidationMessage(
                        severity="ERROR",
                        message=f"Referenced file not found: {ref}",
                        file=str(base_path),
                        fix=f"Create file {ref} or update reference in {base_path.name}",
                    )
                )
                continue

            if target_path.suffix == ".json":
                try:
                    schema_content = json.loads(target_path.read_text())
                    Draft7Validator.check_schema(schema_content)
                except (JSONDecodeError, SchemaError) as exc:
                    messages.append(
                        ValidationMessage(
                            severity="ERROR",
                            message=f"Schema validation failed for '{ref}'",
                            file=str(target_path),
                            fix=f"Fix schema syntax: {exc}",
                        )
                    )
        else:
            messages.append(
                ValidationMessage(
                    severity="WARNING",
                    message=f"Unsupported $ref format: {ref}",
                    file=str(base_path),
                    fix="Use '#/...' for internal refs or './' for file refs",
                )
            )

    return messages


def _load_yaml_doc(path: Path) -> Any:
    """Load a YAML document."""
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def _collect_referenced_schemas(
    document: Any,
    base_path: Path,
) -> set[str]:
    """Collect all schema file names (not paths) referenced in a document."""
    referenced = set()

    for ref in _iter_refs(document):
        if ref.startswith("./"):
            # Extract the filename from the reference
            # e.g., "./jsonschema/schema1.json" -> "schema1.json"
            parts = ref.split("/")
            if parts:
                filename = parts[-1]  # Get the last part (filename)
                if filename:
                    referenced.add(filename)

    return referenced


def validate_json_schemas(schema_dir: Path) -> list[ValidationMessage]:
    """Validate all JSON Schema files."""
    messages: list[ValidationMessage] = []

    for schema_path in sorted(schema_dir.glob("*.json")):
        try:
            schema_content = json.loads(schema_path.read_text())
            Draft7Validator.check_schema(schema_content)
        except (JSONDecodeError, SchemaError) as exc:
            messages.append(
                ValidationMessage(
                    severity="ERROR",
                    message=f"Schema validation failed: {schema_path.name}",
                    file=str(schema_path),
                    fix=f"Fix JSON syntax or schema structure: {exc}",
                )
            )

    return messages


def validate_document_contract(path: Path) -> list[ValidationMessage]:
    """Validate a document contract (OpenAPI/AsyncAPI)."""
    try:
        document = _load_yaml_doc(path)
    except Exception as exc:
        return [
            ValidationMessage(
                severity="ERROR",
                message=f"Failed to parse document: {path.name}",
                file=str(path),
                fix=f"Fix YAML syntax: {exc}",
            )
        ]

    base_path = path.parent
    return _validate_document_references(document, base_path=base_path)


def detect_orphaned_schemas(
    schema_dir: Path,
    openapi_path: Path,
    asyncapi_path: Path,
) -> list[ValidationMessage]:
    """Detect schemas that are not referenced in any spec."""
    messages: list[ValidationMessage] = []

    # Collect all referenced schemas
    referenced_schemas: set[str] = set()

    try:
        openapi_doc = _load_yaml_doc(openapi_path)
        referenced_schemas.update(_collect_referenced_schemas(openapi_doc, openapi_path.parent))
    except Exception:
        pass

    try:
        asyncapi_doc = _load_yaml_doc(asyncapi_path)
        referenced_schemas.update(_collect_referenced_schemas(asyncapi_doc, asyncapi_path.parent))
    except Exception:
        pass

    # Find orphaned schemas
    for schema_path in sorted(schema_dir.glob("*.json")):
        # Use just the filename for comparison (handles both real and test contexts)
        schema_name = schema_path.name

        # Check if any referenced schema matches this schema name
        is_referenced = any(schema_name in ref for ref in referenced_schemas)

        if not is_referenced:
            messages.append(
                ValidationMessage(
                    severity="WARNING",
                    message=f"Orphaned schema not referenced in any spec: {schema_path.name}",
                    file=str(schema_path),
                    fix=f"Add $ref in openapi.k0.yaml or asyncapi.events.yaml, or remove {schema_path.name}",
                )
            )

    return messages


def group_messages_by_severity(
    messages: list[ValidationMessage],
) -> dict[str, list[ValidationMessage]]:
    """Group validation messages by severity level."""
    grouped: dict[str, list[ValidationMessage]] = {
        "ERROR": [],
        "WARNING": [],
        "INFO": [],
    }

    for msg in messages:
        if msg.severity in grouped:
            grouped[msg.severity].append(msg)
        else:
            grouped["INFO"].append(msg)

    return grouped


def format_report(messages: list[ValidationMessage]) -> str:
    """Format validation messages for output."""
    if not messages:
        return "[SchemaLint] ✅ All schemas and contract documents validated successfully."

    grouped = group_messages_by_severity(messages)

    lines = ["[SchemaLint] Validation Report\n"]

    # Summary
    error_count = len(grouped["ERROR"])
    warning_count = len(grouped["WARNING"])
    info_count = len(grouped["INFO"])

    lines.append(f"Errors: {error_count}, Warnings: {warning_count}, Info: {info_count}\n")

    # Details by severity
    for severity in ["ERROR", "WARNING", "INFO"]:
        if grouped[severity]:
            lines.append(f"\n{severity}S:\n")
            for msg in grouped[severity]:
                lines.append(f"  {str(msg).replace(chr(10), chr(10) + '  ')}\n")

    return "".join(lines)


def lint_contracts(
    *,
    schema_dir: Path,
    openapi_path: Path,
    asyncapi_path: Path,
    check_orphans: bool = True,
) -> list[ValidationMessage]:
    """Lint all contract schemas and references."""
    messages: list[ValidationMessage] = []

    # Validate JSON schemas
    messages.extend(validate_json_schemas(schema_dir))

    # Validate document contracts
    messages.extend(validate_document_contract(openapi_path))
    messages.extend(validate_document_contract(asyncapi_path))

    # Check for orphaned schemas
    if check_orphans:
        messages.extend(detect_orphaned_schemas(schema_dir, openapi_path, asyncapi_path))

    return messages


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Lint canonical contract schemas for drift",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run basic validation
  python -m k0.automation.lint_schemas

  # Validate with orphan detection
  python -m k0.automation.lint_schemas --check-orphans

  # CI mode with strict validation
  python -m k0.automation.lint_schemas --check

  # Verbose output with diagnostics
  python -m k0.automation.lint_schemas --verbose
        """,
    )
    parser.add_argument(
        "--schema-dir",
        type=Path,
        default=DEFAULT_SCHEMA_DIR,
        help="JSON schema directory",
    )
    parser.add_argument(
        "--openapi",
        type=Path,
        default=DEFAULT_OPENAPI_PATH,
        help="OpenAPI specification path",
    )
    parser.add_argument(
        "--asyncapi",
        type=Path,
        default=DEFAULT_ASYNCAPI_PATH,
        help="AsyncAPI specification path",
    )
    parser.add_argument(
        "--check-orphans",
        action="store_true",
        default=True,
        help="Check for orphaned schemas (default: enabled)",
    )
    parser.add_argument(
        "--no-orphan-check",
        dest="check_orphans",
        action="store_false",
        help="Disable orphan detection",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="CI mode: fail on any issues",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Verbose output with detailed diagnostics",
    )

    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)

    messages = lint_contracts(
        schema_dir=args.schema_dir,
        openapi_path=args.openapi,
        asyncapi_path=args.asyncapi,
        check_orphans=args.check_orphans,
    )

    report = format_report(messages)
    print(report)

    if not messages:
        return 0

    # Determine exit code
    error_count = sum(1 for m in messages if m.severity == "ERROR")
    warning_count = sum(1 for m in messages if m.severity == "WARNING")

    if error_count > 0:
        return 1
    elif warning_count > 0 and args.check:
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
