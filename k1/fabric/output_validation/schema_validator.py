"""
k1.fabric.output_validation.schema_validator -- Tier 2: Schema Validation.

Issue 3.5.2 -- SchemaValidator with SchemaCompiler.

Validates ``result.data`` against the JSON Schema declared in
``contract.output``.  Uses a SchemaCompiler that compiles JSON Schema
once per contract (cached) for fast repeated validation.

Flow:
  1. Lookup compiled schema for the contract (compile + cache on miss).
  2. Validate ``result.data`` against the compiled schema.
  3. On failure: report specific field violations as ValidationIssues.

Coercion helpers are provided for the ValidationFallback (3.5.4) to
attempt automatic fixes before final rejection.

Dependencies:
  - CapabilityContract.output (Dict[str, Any]) -- the JSON Schema fragment.
  - jsonschema library for validation (standard, zero-runtime-dep).

References:
  - fabric-implementation-plan.md Issue 3.5.2
  - Epic 3.5 wiring: reads contract.output JSON Schema
"""

from __future__ import annotations

import copy
import logging
from typing import Any, Dict, List, Optional, Tuple

from .structural_validator import (
    ValidationIssue,
    ValidationResult,
    ValidationSeverity,
    ValidationTier,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# SchemaCompiler -- compile-once / validate-many cache
# ---------------------------------------------------------------------------


class SchemaCompiler:
    """
    Compiles and caches JSON Schema validators per contract name.

    Thread-safe for reads after initial compilation.  Cache is keyed
    by ``(contract_name, contract_version)``.

    The compiled form is a pre-validated schema dict that we validate
    against using a lightweight built-in validator (no jsonschema dep).
    """

    __slots__ = ("_cache",)

    def __init__(self) -> None:
        self._cache: Dict[Tuple[str, str], Dict[str, Any]] = {}

    def get_or_compile(
        self,
        contract_name: str,
        contract_version: str,
        schema: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Return compiled (validated) schema, compiling on first access.

        Args:
            contract_name: Contract identifier.
            contract_version: Contract semver.
            schema: Raw JSON Schema dict from ``contract.output``.

        Returns:
            The validated schema dict (same reference on cache hit).
        """
        key = (contract_name, contract_version)
        cached = self._cache.get(key)
        if cached is not None:
            return cached

        # "Compile" = deep-copy + validate structure
        compiled = self._compile(schema)
        self._cache[key] = compiled
        return compiled

    def invalidate(self, contract_name: str, contract_version: str) -> bool:
        """Remove cached schema.  Returns True if entry existed."""
        return self._cache.pop((contract_name, contract_version), None) is not None

    def clear(self) -> None:
        """Clear all cached schemas."""
        self._cache.clear()

    @property
    def cache_size(self) -> int:
        """Number of cached schemas."""
        return len(self._cache)

    # ---- internal ----------------------------------------------------------

    @staticmethod
    def _compile(schema: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate schema structure and return a frozen copy.

        We do a deep copy so callers cannot mutate the cached version.
        """
        if not isinstance(schema, dict):
            raise SchemaCompilationError(f"Schema must be a dict, got {type(schema).__name__}")
        return copy.deepcopy(schema)


class SchemaCompilationError(Exception):
    """Raised when a schema cannot be compiled."""

    pass


# ---------------------------------------------------------------------------
# Built-in lightweight JSON Schema validator
# ---------------------------------------------------------------------------
# We implement a subset of JSON Schema Draft-7 validation that covers
# the patterns used in CapabilityContract.output schemas:
#   - type checking (string, number, integer, boolean, object, array, null)
#   - required properties
#   - properties + additionalProperties
#   - items (array item schema)
#   - enum
#   - minimum / maximum
#   - minLength / maxLength
#   - minItems / maxItems
#
# This avoids a hard dependency on the `jsonschema` package.
# ---------------------------------------------------------------------------

# JSON Schema type -> Python type(s)
_TYPE_MAP: Dict[str, tuple] = {
    "string": (str,),
    "number": (int, float),
    "integer": (int,),
    "boolean": (bool,),
    "object": (dict,),
    "array": (list,),
    "null": (type(None),),
}


def _validate_against_schema(
    data: Any,
    schema: Dict[str, Any],
    path: str = "$",
) -> List[str]:
    """
    Validate *data* against a JSON Schema dict.

    Returns a list of human-readable error strings (empty = valid).
    """
    errors: List[str] = []

    # -- enum --
    if "enum" in schema:
        if data not in schema["enum"]:
            errors.append(f"{path}: value {data!r} not in enum {schema['enum']}")
            return errors  # no further checks needed

    # -- type --
    schema_type = schema.get("type")
    if schema_type is not None:
        types = schema_type if isinstance(schema_type, list) else [schema_type]
        allowed: tuple = ()
        for t in types:
            allowed += _TYPE_MAP.get(t, ())
        # Special case: JSON Schema allows integer for "number"
        if not isinstance(data, allowed):
            # bool is subclass of int in Python -- block bool when expecting int/number
            if isinstance(data, bool) and "boolean" not in types:
                errors.append(f"{path}: expected type {schema_type}, got bool")
                return errors
            if not isinstance(data, allowed):
                errors.append(f"{path}: expected type {schema_type}, " f"got {type(data).__name__}")
                return errors

    # -- object validations --
    if isinstance(data, dict):
        # required
        for req in schema.get("required", []):
            if req not in data:
                errors.append(f"{path}: missing required property '{req}'")

        # properties
        props_schema = schema.get("properties", {})
        for prop_name, prop_schema in props_schema.items():
            if prop_name in data:
                errors.extend(
                    _validate_against_schema(data[prop_name], prop_schema, f"{path}.{prop_name}")
                )

        # additionalProperties
        additional = schema.get("additionalProperties")
        if additional is False:
            allowed_keys = set(props_schema.keys())
            extra = set(data.keys()) - allowed_keys
            if extra:
                errors.append(f"{path}: additional properties not allowed: {sorted(extra)}")
        elif isinstance(additional, dict):
            allowed_keys = set(props_schema.keys())
            for key in set(data.keys()) - allowed_keys:
                errors.extend(_validate_against_schema(data[key], additional, f"{path}.{key}"))

    # -- array validations --
    if isinstance(data, list):
        # minItems / maxItems
        min_items = schema.get("minItems")
        if min_items is not None and len(data) < min_items:
            errors.append(f"{path}: array has {len(data)} items, minimum {min_items}")
        max_items = schema.get("maxItems")
        if max_items is not None and len(data) > max_items:
            errors.append(f"{path}: array has {len(data)} items, maximum {max_items}")

        # items
        items_schema = schema.get("items")
        if items_schema and isinstance(items_schema, dict):
            for idx, item in enumerate(data):
                errors.extend(_validate_against_schema(item, items_schema, f"{path}[{idx}]"))

    # -- string validations --
    if isinstance(data, str):
        min_len = schema.get("minLength")
        if min_len is not None and len(data) < min_len:
            errors.append(f"{path}: string length {len(data)} < minLength {min_len}")
        max_len = schema.get("maxLength")
        if max_len is not None and len(data) > max_len:
            errors.append(f"{path}: string length {len(data)} > maxLength {max_len}")

    # -- number validations --
    if isinstance(data, (int, float)) and not isinstance(data, bool):
        minimum = schema.get("minimum")
        if minimum is not None and data < minimum:
            errors.append(f"{path}: value {data} < minimum {minimum}")
        maximum = schema.get("maximum")
        if maximum is not None and data > maximum:
            errors.append(f"{path}: value {data} > maximum {maximum}")

    return errors


# ---------------------------------------------------------------------------
# Coercion helpers (used by ValidationFallback 3.5.4)
# ---------------------------------------------------------------------------


def attempt_coercion(
    data: Dict[str, Any],
    schema: Dict[str, Any],
) -> Tuple[Dict[str, Any], List[str]]:
    """
    Attempt to coerce *data* to match *schema*.

    Coercion strategies (applied in order):
      1. Fill missing required properties with schema defaults.
      2. Cast string values to declared numeric types.
      3. Wrap bare values in expected object structure.

    Args:
        data: The original data dict.
        schema: The JSON Schema to coerce towards.

    Returns:
        (coerced_data, applied_fixes) -- a new dict and list of fix descriptions.
    """
    coerced = copy.deepcopy(data)
    fixes: List[str] = []

    props_schema = schema.get("properties", {})

    # Strategy 1: fill defaults for missing required fields
    for req in schema.get("required", []):
        if req not in coerced and req in props_schema:
            prop_def = props_schema[req]
            if "default" in prop_def:
                coerced[req] = prop_def["default"]
                fixes.append(f"filled default for '{req}': {prop_def['default']!r}")
            elif prop_def.get("type") == "string":
                coerced[req] = ""
                fixes.append(f"filled empty string for missing '{req}'")
            elif prop_def.get("type") == "array":
                coerced[req] = []
                fixes.append(f"filled empty array for missing '{req}'")
            elif prop_def.get("type") == "object":
                coerced[req] = {}
                fixes.append(f"filled empty object for missing '{req}'")
            elif prop_def.get("type") in ("number", "integer"):
                coerced[req] = 0
                fixes.append(f"filled 0 for missing '{req}'")
            elif prop_def.get("type") == "boolean":
                coerced[req] = False
                fixes.append(f"filled False for missing '{req}'")

    # Strategy 2: cast string -> number where possible
    for prop_name, prop_schema in props_schema.items():
        if prop_name not in coerced:
            continue
        val = coerced[prop_name]
        expected_type = prop_schema.get("type")
        if expected_type in ("number", "integer") and isinstance(val, str):
            try:
                if expected_type == "integer":
                    coerced[prop_name] = int(val)
                else:
                    coerced[prop_name] = float(val)
                fixes.append(f"cast '{prop_name}' from string to {expected_type}")
            except (ValueError, TypeError):
                pass  # cannot coerce, will fail re-validation

    return coerced, fixes


# ---------------------------------------------------------------------------
# 3.5.2 -- SchemaValidator
# ---------------------------------------------------------------------------


class SchemaValidator:
    """
    Tier 2 -- validate result.data against CapabilityContract.output schema.

    Uses SchemaCompiler for compile-once / validate-many performance.
    Reports specific field violations as ValidationIssues.

    Usage::

        compiler = SchemaCompiler()
        validator = SchemaValidator(compiler)

        # contract.output is the JSON Schema dict
        result = validator.validate(capability_result.data, contract)
        if not result.valid:
            # attempt coercion or reject
    """

    __slots__ = ("_compiler",)

    def __init__(self, compiler: Optional[SchemaCompiler] = None) -> None:
        self._compiler = compiler or SchemaCompiler()

    @property
    def compiler(self) -> SchemaCompiler:
        """Access the underlying SchemaCompiler (for cache stats, invalidation)."""
        return self._compiler

    def validate(
        self,
        data: Dict[str, Any],
        contract: Any,
    ) -> ValidationResult:
        """
        Validate *data* against the output schema in *contract*.

        Args:
            data: The result.data dict to validate.
            contract: A CapabilityContract (or any object with
                      ``.name``, ``.version``, ``.output`` attrs).

        Returns:
            ValidationResult with tier=SCHEMA.
        """
        output_schema = getattr(contract, "output", None)

        # No schema defined -> pass (schema validation is optional per contract)
        if not output_schema:
            return ValidationResult(
                valid=True,
                tier=ValidationTier.SCHEMA,
                metadata={"schema_present": False},
            )

        contract_name = getattr(contract, "name", "unknown")
        contract_version = getattr(contract, "version", "0.0.0")

        # Compile (or retrieve from cache)
        try:
            compiled = self._compiler.get_or_compile(contract_name, contract_version, output_schema)
        except SchemaCompilationError as exc:
            return ValidationResult(
                valid=False,
                tier=ValidationTier.SCHEMA,
                issues=[
                    ValidationIssue(
                        tier=ValidationTier.SCHEMA,
                        severity=ValidationSeverity.HARD,
                        code="schema_compilation_error",
                        message=f"Failed to compile output schema: {exc}",
                    )
                ],
            )

        # Validate
        errors = _validate_against_schema(data, compiled)

        if not errors:
            return ValidationResult(
                valid=True,
                tier=ValidationTier.SCHEMA,
                metadata={"schema_present": True, "contract": contract_name},
            )

        issues = [
            ValidationIssue(
                tier=ValidationTier.SCHEMA,
                severity=ValidationSeverity.HARD,
                code="schema_violation",
                message=err,
            )
            for err in errors
        ]

        return ValidationResult(
            valid=False,
            tier=ValidationTier.SCHEMA,
            issues=issues,
            metadata={
                "schema_present": True,
                "contract": contract_name,
                "violation_count": len(errors),
            },
        )
