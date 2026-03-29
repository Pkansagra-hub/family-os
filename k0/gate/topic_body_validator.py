"""Per-topic body schema validation for MinimalGate.

Loads gate_topic_validation.yaml rules and per-topic JSON Schema files,
then validates envelope body against the correct schema based on command topic.

Contract: k0/contracts/capabilities/gate_topic_validation.yaml
Schemas:  k0/contracts/jsonschema/topics/*.body.json
Milestone: M2 Epics 2.10 + 2.11
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from fnmatch import fnmatch
from pathlib import Path
from typing import Any, Sequence

import yaml
from jsonschema import Draft202012Validator
from jsonschema import ValidationError as JsonSchemaValidationError
from jsonschema.validators import RefResolver

logger = logging.getLogger(__name__)

# -- Rejection reason constants ------------------------------------------------
TOPIC_UNKNOWN = "TOPIC_UNKNOWN"
TOPIC_BODY_VALIDATION_FAILED = "BODY_VALIDATION_FAILED"
TOPIC_BODY_SIZE_EXCEEDED = "BODY_SIZE_EXCEEDED"
TOPIC_BAND_NOT_ALLOWED = "BAND_NOT_ALLOWED"

# -- Default contract file paths (relative to repo root) -----------------------
_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_VALIDATION_YAML = (
    _REPO_ROOT / "k0" / "contracts" / "capabilities" / "gate_topic_validation.yaml"
)
_DEFAULT_SCHEMAS_DIR = _REPO_ROOT / "k0" / "contracts" / "jsonschema" / "topics"
_DEFAULT_SCHEMAS_ROOT = _REPO_ROOT / "k0" / "contracts" / "jsonschema"


@dataclass(slots=True, frozen=True)
class BodyViolation:
    """Single body schema violation."""

    path: str
    message: str


@dataclass(slots=True, frozen=True)
class TopicValidationResult:
    """Result of per-topic body validation."""

    valid: bool
    reason: str | None = None
    violations: tuple[BodyViolation, ...] = ()


@dataclass(slots=True)
class _TopicRule:
    """Parsed per-topic validation rule."""

    topic_pattern: str
    match_type: str  # "exact" or "glob"
    body_required: bool
    body_schema_path: str | None
    max_body_bytes: int
    allowed_bands: tuple[str, ...]
    required_envelope_fields: tuple[str, ...]
    validation_level: str  # "STRICT" or "LENIENT"
    compiled_validator: Draft202012Validator | None = field(default=None, repr=False)


class TopicBodyValidator:
    """Validates envelope body against per-topic JSON Schema.

    Loaded at startup from gate_topic_validation.yaml + per-topic body schema files.
    Thread-safe after construction (all state is immutable after __init__).
    """

    def __init__(
        self,
        *,
        validation_yaml_path: Path | None = None,
        schemas_dir: Path | None = None,
        schemas_root: Path | None = None,
    ) -> None:
        self._validation_yaml = validation_yaml_path or _DEFAULT_VALIDATION_YAML
        self._schemas_dir = schemas_dir or _DEFAULT_SCHEMAS_DIR
        self._schemas_root = schemas_root or _DEFAULT_SCHEMAS_ROOT

        # Parse rules
        raw = yaml.safe_load(self._validation_yaml.read_text(encoding="utf-8"))
        config = raw["gate_topic_validation"]
        defaults = config.get("defaults", {})

        self._default_body_required: bool = defaults.get("body_required", True)
        self._default_max_body_bytes: int = defaults.get("max_body_bytes", 8192)
        self._default_validation_level: str = defaults.get("validation_level", "STRICT")

        # Build schema store for $ref resolution (load ALL schemas in schemas_root)
        self._schema_store: dict[str, dict[str, Any]] = {}
        self._load_schema_store()

        # Parse per-topic rules and compile validators
        self._exact_rules: dict[str, _TopicRule] = {}
        self._glob_rules: list[_TopicRule] = []
        self._parse_topic_rules(config.get("topics", []))

        logger.info(
            "TopicBodyValidator loaded: %d exact rules, %d glob rules, %d schemas in store",
            len(self._exact_rules),
            len(self._glob_rules),
            len(self._schema_store),
        )

    # -- Public API ------------------------------------------------------------

    def validate_topic_body(
        self,
        topic: str,
        body: dict[str, Any] | None,
        band: str,
        body_bytes_len: int,
    ) -> TopicValidationResult:
        """Validate envelope body against per-topic rules.

        Args:
            topic: Command topic string (e.g. "memory.write")
            body: Parsed body dict (or None if body absent)
            band: Envelope privacy band ("GREEN", "AMBER", "RED")
            body_bytes_len: Raw body size in bytes

        Returns:
            TopicValidationResult with valid=True on success, or reason + violations on failure.
        """
        rule = self._resolve_rule(topic)
        if rule is None:
            return TopicValidationResult(
                valid=False,
                reason=f"{TOPIC_UNKNOWN}:{topic}",
            )

        # Band check
        if band not in rule.allowed_bands:
            return TopicValidationResult(
                valid=False,
                reason=f"{TOPIC_BAND_NOT_ALLOWED}:{topic}:band={band}:allowed={','.join(rule.allowed_bands)}",
            )

        # Body size check (per-topic limit, not the global gate limit)
        if body_bytes_len > rule.max_body_bytes:
            return TopicValidationResult(
                valid=False,
                reason=f"{TOPIC_BODY_SIZE_EXCEEDED}:{topic}:size={body_bytes_len}:max={rule.max_body_bytes}",
            )

        # Body presence check
        if rule.body_required and (body is None or len(body) == 0):
            return TopicValidationResult(
                valid=False,
                reason=f"BODY_REQUIRED:{topic}",
            )

        # Body schema validation
        if rule.compiled_validator is not None and body is not None:
            errors = sorted(
                rule.compiled_validator.iter_errors(body),
                key=lambda e: list(e.absolute_path),
            )
            if errors:
                violations = tuple(
                    BodyViolation(
                        path=_json_path(err),
                        message=err.message,
                    )
                    for err in errors[:10]  # Cap at 10 violations to avoid huge responses
                )
                return TopicValidationResult(
                    valid=False,
                    reason=f"{TOPIC_BODY_VALIDATION_FAILED}:{topic}",
                    violations=violations,
                )

        return TopicValidationResult(valid=True)

    def is_known_topic(self, topic: str) -> bool:
        """Check if a topic matches any registered rule (exact or glob)."""
        return self._resolve_rule(topic) is not None

    def known_topics(self) -> Sequence[str]:
        """Return list of all registered exact topic patterns."""
        return list(self._exact_rules.keys())

    # -- Internal: rule resolution ---------------------------------------------

    def _resolve_rule(self, topic: str) -> _TopicRule | None:
        """Resolve topic to a rule: exact match first, then glob."""
        # Exact match
        rule = self._exact_rules.get(topic)
        if rule is not None:
            return rule

        # Glob match
        for glob_rule in self._glob_rules:
            if fnmatch(topic, glob_rule.topic_pattern):
                return glob_rule

        return None

    # -- Internal: startup loading ---------------------------------------------

    def _load_schema_store(self) -> None:
        """Load all JSON Schema files into an in-memory store for $ref resolution.

        Scans both K0 and K1 schema directories because per-topic body schemas
        may $ref K1 schemas (e.g. memory_write.body.json refs memory_atom.v2.schema.json).
        """
        scan_dirs = [
            self._schemas_root,
            _REPO_ROOT / "k1" / "contracts" / "schemas",
        ]
        for scan_dir in scan_dirs:
            if not scan_dir.exists():
                continue
            for schema_file in scan_dir.rglob("*.json"):
                try:
                    schema = json.loads(schema_file.read_text(encoding="utf-8"))
                    schema_id = schema.get("$id")
                    if schema_id and isinstance(schema_id, str):
                        self._schema_store[schema_id] = schema
                except (json.JSONDecodeError, OSError) as exc:
                    logger.warning("Failed to load schema %s: %s", schema_file, exc)

    def _parse_topic_rules(self, topics_list: list[dict[str, Any]]) -> None:
        """Parse per-topic rules from YAML config and compile JSON Schema validators."""
        for entry in topics_list:
            pattern = entry["topic_pattern"]
            match_type = entry.get("match_type", "exact")
            body_schema_path = entry.get("body_schema")

            # Compile JSON Schema validator if schema path provided
            compiled = None
            if body_schema_path:
                compiled = self._compile_schema(body_schema_path)

            rule = _TopicRule(
                topic_pattern=pattern,
                match_type=match_type,
                body_required=entry.get("body_required", self._default_body_required),
                body_schema_path=body_schema_path,
                max_body_bytes=entry.get("max_body_bytes", self._default_max_body_bytes),
                allowed_bands=tuple(entry.get("allowed_bands", ("GREEN", "AMBER", "RED"))),
                required_envelope_fields=tuple(entry.get("required_envelope_fields", ())),
                validation_level=entry.get("validation_level", self._default_validation_level),
                compiled_validator=compiled,
            )

            if match_type == "exact":
                self._exact_rules[pattern] = rule
            else:
                self._glob_rules.append(rule)

    def _compile_schema(self, schema_rel_path: str) -> Draft202012Validator | None:
        """Load and compile a JSON Schema file into a Draft202012Validator."""
        schema_path = _REPO_ROOT / schema_rel_path
        if not schema_path.exists():
            logger.warning("Body schema file not found: %s", schema_path)
            return None

        try:
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to load body schema %s: %s", schema_path, exc)
            return None

        # Add this schema to the store if it has an $id
        schema_id = schema.get("$id")
        if schema_id:
            self._schema_store[schema_id] = schema

        # Build resolver backed by in-memory store for $ref resolution
        resolver = RefResolver.from_schema(schema, store=self._schema_store)

        try:
            Draft202012Validator.check_schema(schema)
        except Exception as exc:
            logger.warning("Invalid body schema %s: %s", schema_rel_path, exc)
            return None

        return Draft202012Validator(schema, resolver=resolver)


def _json_path(error: JsonSchemaValidationError) -> str:
    """Convert jsonschema error path to JSONPath string (e.g. '$.affect.valence')."""
    parts = list(error.absolute_path)
    if not parts:
        return "$"
    return "$." + ".".join(str(p) for p in parts)
    return "$." + ".".join(str(p) for p in parts)
