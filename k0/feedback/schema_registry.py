"""Feedback schema registry.

Epic: 0.2 (Feedback Schema Registry)
Stories: FEEDBACK-003 (+ FEEDBACK-004 starter registrations)
Related ADR: K020

The feedback envelope is pipeline-agnostic, but the payload is pipeline-specific.
This registry allows each pipeline to register its payload schema for validation.

Design notes:
- Supports both Pydantic models (preferred) and JSON Schema dicts.
- Defaults to permissive mode for unregistered pipelines during early rollout.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from threading import RLock
from typing import Any, Type

from jsonschema import Draft7Validator, FormatChecker
from pydantic import BaseModel

_PIPELINE_ID_PATTERN = r"^P\d{2,3}$"  # P02, P08, ... P120
_PIPELINE_ID_RE = re.compile(_PIPELINE_ID_PATTERN)

_FORMAT_CHECKER = FormatChecker()


def _normalize_pipeline_id(pipeline_id: str) -> str:
    normalized = pipeline_id.strip().upper()
    if not normalized:
        raise ValueError("pipeline_id must not be empty")
    if _PIPELINE_ID_RE.fullmatch(normalized) is None:
        raise ValueError(f"pipeline_id must match {_PIPELINE_ID_PATTERN}")
    return normalized


class FeedbackSchemaRegistry:
    """Registry for pipeline-specific feedback payload schemas."""

    _lock = RLock()

    # Pipeline -> Pydantic payload model
    _pydantic_schemas: dict[str, Type[BaseModel]] = {}

    # Pipeline -> JSON schema dict
    _json_schemas: dict[str, dict[str, Any]] = {}

    # Pipeline -> compiled validator
    _validators: dict[str, Draft7Validator] = {}

    permissive_unregistered: bool = True

    @classmethod
    def reset(cls) -> None:
        """Reset the registry (primarily for tests)."""

        with cls._lock:
            cls._pydantic_schemas.clear()
            cls._json_schemas.clear()
            cls._validators.clear()
            cls.permissive_unregistered = True

    @classmethod
    def register_pydantic(cls, pipeline_id: str, schema: Type[BaseModel]) -> None:
        """Register a Pydantic model as the feedback payload schema for a pipeline."""

        pid = _normalize_pipeline_id(pipeline_id)
        with cls._lock:
            cls._pydantic_schemas[pid] = schema
            # Clear any JSON schema/validator for same pipeline to prevent ambiguity.
            cls._json_schemas.pop(pid, None)
            cls._validators.pop(pid, None)

    @classmethod
    def register_json_schema(cls, pipeline_id: str, schema: dict[str, Any]) -> None:
        """Register a JSON Schema for pipeline feedback payload validation."""

        pid = _normalize_pipeline_id(pipeline_id)
        with cls._lock:
            # Validate schema structure early (fail-fast).
            Draft7Validator.check_schema(schema)
            cls._json_schemas[pid] = schema
            cls._validators[pid] = Draft7Validator(schema, format_checker=_FORMAT_CHECKER)
            # Clear any Pydantic schema for same pipeline to prevent ambiguity.
            cls._pydantic_schemas.pop(pid, None)

    @classmethod
    def load_schemas_from_directory(cls, directory: Path) -> None:
        """Load JSON schemas from a directory of `*.json` files.

        Filenames are mapped by stem:
        - `p02.json` -> `P02`
        - `P08.json` -> `P08`
        """

        for schema_file in sorted(directory.glob("*.json"), key=lambda p: p.name):
            data = json.loads(schema_file.read_text(encoding="utf-8"))
            pipeline_id = _normalize_pipeline_id(schema_file.stem)
            cls.register_json_schema(pipeline_id, data)

    @classmethod
    def get_schema(cls, pipeline_id: str) -> Type[BaseModel] | dict[str, Any] | None:
        """Return the registered schema (Pydantic model or JSON schema) for a pipeline."""

        pid = _normalize_pipeline_id(pipeline_id)
        with cls._lock:
            return cls._pydantic_schemas.get(pid) or cls._json_schemas.get(pid)

    @classmethod
    def list_registered(cls) -> list[str]:
        """List all pipelines with registered feedback schemas."""

        with cls._lock:
            return sorted(set(cls._pydantic_schemas) | set(cls._json_schemas))

    @classmethod
    def validate(
        cls,
        pipeline_id: str,
        payload: dict[str, Any],
        *,
        permissive_unregistered: bool | None = None,
    ) -> tuple[bool, str | None]:
        """Validate payload against the registered schema for the pipeline.

        Returns:
            (ok, error_message)
        """

        pid = _normalize_pipeline_id(pipeline_id)
        mode = (
            cls.permissive_unregistered
            if permissive_unregistered is None
            else permissive_unregistered
        )

        with cls._lock:
            pyd_schema = cls._pydantic_schemas.get(pid)
            validator = cls._validators.get(pid)

        if pyd_schema is not None:
            try:
                pyd_schema.model_validate(payload)
                return True, None
            except Exception as exc:  # noqa: BLE001 - surface validation error text
                return False, str(exc)

        if validator is not None:
            try:
                validator.validate(payload)
                return True, None
            except Exception as exc:  # noqa: BLE001 - surface validation error text
                return False, str(exc)

        if mode:
            return True, None

        return False, f"No feedback payload schema registered for pipeline {pid}"
