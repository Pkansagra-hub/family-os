from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, Iterable, Tuple

import yaml
from jsonschema import Draft202012Validator, SchemaError, ValidationError
from jsonschema.validators import RefResolver


class SchemaValidator:
    """
    Validates contract data against JSON Schema Draft 2020-12.

    Key features:
    - Loads all *.schema.yaml under schemas_dir
    - Uses $id as the canonical key (supports k1://... URIs)
    - Resolves $ref via an in-memory store (no file/network refs needed)
    - Produces readable error messages with JSON pointer paths
    """

    def __init__(self, schemas_dir: Optional[Path] = None):
        if schemas_dir is None:
            current_dir = Path(__file__).parent
            schemas_dir = current_dir.parent / "schemas"

        self.schemas_dir = schemas_dir
        self._schema_cache: Dict[str, Dict[str, Any]] = {}

        self._load_all_schemas()

        # In-memory schema store for $ref resolution.
        # jsonschema will look up referenced schemas by their $id (URI).
        self._store: Dict[str, Dict[str, Any]] = dict(self._schema_cache)

    def _load_all_schemas(self) -> None:
        """Load all schema files into cache keyed by $id."""
        for schema_file in self.schemas_dir.rglob("*.schema.yaml"):
            try:
                schema = self._load_yaml(schema_file)
                schema_id = schema.get("$id")
                if not schema_id or not isinstance(schema_id, str):
                    # We require every schema to have a stable $id
                    raise ValueError(f"Schema missing valid $id: {schema_file}")

                self._schema_cache[schema_id] = schema
            except Exception as e:
                raise RuntimeError(f"Failed to load schema {schema_file}: {e}") from e

    @staticmethod
    def _load_yaml(path: Path) -> Dict[str, Any]:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if not isinstance(data, dict):
            raise ValueError(f"Schema YAML must be a mapping/object: {path}")
        return data

    def validate_contract(self, contract_data: Dict[str, Any], schema_id: str) -> bool:
        """
        Validate contract data against a schema by $id.

        Raises:
            ValueError: schema_id not found
            SchemaError: schema invalid
            ValidationError: contract does not conform
        """
        schema = self._schema_cache.get(schema_id)
        if schema is None:
            known = ", ".join(sorted(self._schema_cache.keys()))
            raise ValueError(f"Schema '{schema_id}' not found. Known schemas: {known}")

        # Build a resolver rooted at this schema_id and backed by our in-memory store.
        resolver = RefResolver.from_schema(schema, store=self._store)

        # Draft 2020-12 validator explicitly (avoids ambiguity).
        validator = Draft202012Validator(schema, resolver=resolver)

        # Validate schema itself (catches broken schemas early).
        try:
            Draft202012Validator.check_schema(schema)
        except SchemaError as e:
            raise e

        errors = sorted(validator.iter_errors(contract_data), key=lambda e: list(e.path))
        if errors:
            # Raise the first error, but with improved message including paths.
            raise self._pretty_validation_error(errors[0])

        return True

    def is_valid(self, contract_data: Dict[str, Any], schema_id: str) -> bool:
        try:
            self.validate_contract(contract_data, schema_id)
            return True
        except (ValidationError, SchemaError, ValueError):
            return False

    def get_validation_errors(self, contract_data: Dict[str, Any], schema_id: str) -> Optional[str]:
        try:
            self.validate_contract(contract_data, schema_id)
            return None
        except (ValidationError, SchemaError, ValueError) as e:
            return str(e)

    def iter_validation_errors(
        self, contract_data: Dict[str, Any], schema_id: str
    ) -> Iterable[str]:
        """
        Return ALL validation errors (useful for VSCode Problems-style reporting).
        """
        schema = self._schema_cache.get(schema_id)
        if schema is None:
            yield f"Schema '{schema_id}' not found"
            return

        resolver = RefResolver.from_schema(schema, store=self._store)
        validator = Draft202012Validator(schema, resolver=resolver)

        try:
            Draft202012Validator.check_schema(schema)
        except SchemaError as e:
            yield f"SchemaError: {e}"
            return

        for err in sorted(validator.iter_errors(contract_data), key=lambda e: list(e.path)):
            yield str(self._pretty_validation_error(err))

    @staticmethod
    def _format_path(path_parts: Iterable[Any]) -> str:
        # Convert deque/path list -> JSON Pointer-ish string
        parts = []
        for p in path_parts:
            if isinstance(p, int):
                parts.append(f"[{p}]")
            else:
                # keys
                parts.append(f".{p}" if parts else str(p))
        return "".join(parts) if parts else "<root>"

    def _pretty_validation_error(self, err: ValidationError) -> ValidationError:
        """
        Return a ValidationError with a more actionable message.
        """
        instance_path = self._format_path(err.path)
        schema_path = (
            "/".join(str(p) for p in err.schema_path) if err.schema_path else "<schema-root>"
        )
        msg = (
            f"ValidationError at '{instance_path}': {err.message}\n"
            f"  Schema path: {schema_path}\n"
        )
        # Preserve original error context & metadata
        return ValidationError(
            msg,
            validator=err.validator,
            validator_value=err.validator_value,
            instance=err.instance,
            schema=err.schema,
            path=err.path,
            schema_path=err.schema_path,
            parent=err.parent,
            context=err.context,
        )
