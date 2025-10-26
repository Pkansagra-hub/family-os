"""
Configuration Schema Validator

Purpose: Validate K1 configuration files against JSON schemas
Location: k1/l5_infrastructure/config/schema_validator.py
Performance: <10ms validation

Primary ADRs:
- ADR-0080: Config Hot-Reload (ConfigValidator component)

Related ADRs:
- ADR-0024b: Component-Level Budgets (validation <10ms)

Key Responsibilities:

1. Schema Validation (JSON Schema Draft 7):
   - Validate config structure, types, constraints
   - JSON Schema Draft 7 compliance
   - Required fields validation
   - Type checking (string, number, boolean, array, object)
   - Range validation (min/max values)
   - Enum validation (allowed values)
   - Pattern validation (regex patterns)

2. Semantic Validation:
   - Config-specific validators (beyond JSON Schema)
   - Cross-field validation (e.g., min <= max)
   - Business logic validation (e.g., max_agents > 0)
   - Dependency validation (e.g., if feature_enabled, then config_required)

3. Error Reporting:
   - Detailed validation errors (field path, error message, expected/actual values)
   - Multiple error reporting (all validation errors, not just first)
   - Human-readable error messages
   - JSON path to error location (e.g., "agent_fabric.max_agents_per_session")

4. Schema Definitions:
   - kernel.schema.json: Core K1 configuration schema
   - logging.schema.json: Logging configuration schema
   - circuit_breaker.schema.json: Circuit breaker settings schema
   - thermal.schema.json: Thermal management settings schema
   - metrics.schema.json: Metrics configuration schema

Performance Metrics:
- Validation: <10ms P95 (<5ms typical)
- Schema parsing: <5ms (one-time at startup)
- Error formatting: <1ms

Implementation Notes:
- Use jsonschema library (Python)
- JSON Schema Draft 7 (latest stable)
- Fail-fast: Return all validation errors (not just first)
- Schema caching: Parse schemas once at startup
- Custom validators: Add custom validation functions for semantic checks

Example Usage:
    from k1.l5_infrastructure.config import SchemaValidator

    # Create validator
    validator = SchemaValidator(schema_dir="/etc/k1/schemas")

    # Validate config
    config_data = yaml.safe_load(open("kernel.yaml"))
    errors = validator.validate("kernel", config_data)

    if errors:
        for error in errors:
            print(f"Validation error at {error.path}: {error.message}")
            print(f"  Expected: {error.expected}")
            print(f"  Actual: {error.actual}")
    else:
        print("Config is valid!")

    # Semantic validation
    if config_data["agent_fabric"]["max_agents_per_session"] < 1:
        errors.append(ValidationError(
            path="agent_fabric.max_agents_per_session",
            message="Must be at least 1",
            expected=">= 1",
            actual=config_data["agent_fabric"]["max_agents_per_session"]
        ))

Research Foundation:
- JSON Schema (Draft 7, constraint validation)
- Schema validation (structure, type, constraint checking)
- Error reporting (detailed, human-readable, actionable)

TODO:
- [ ] Implement SchemaValidator class with jsonschema
- [ ] Define JSON Schema Draft 7 schemas (kernel, logging, circuit_breaker, thermal, metrics)
- [ ] Implement schema validation with detailed error reporting
- [ ] Implement semantic validation (cross-field, business logic)
- [ ] Implement ValidationError class (path, message, expected, actual)
- [ ] Add schema caching (parse once at startup)
- [ ] Add custom validators for semantic checks
- [ ] Add unit tests for schema validation and error reporting
- [ ] Add integration tests with real config files
"""

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from jsonschema import Draft7Validator
from jsonschema import ValidationError as JsonSchemaValidationError

logger = logging.getLogger(__name__)


@dataclass
class ValidationError:
    """Configuration validation error with detailed context"""

    path: str  # JSON path to error (e.g., "kernel.max_agents_per_session")
    message: str  # Human-readable error message
    expected: Optional[str] = None  # Expected value or constraint
    actual: Optional[Any] = None  # Actual value that failed validation


class SchemaValidator:
    """Validate K1 configuration files against JSON schemas

    Responsibilities:
    - Load and cache JSON Schema Draft 7 schemas
    - Validate YAML configs against schemas
    - Provide detailed error reporting (path, message, expected, actual)
    - Support semantic validation (custom validators)

    Performance: <10ms P95 validation target

    Example:
        validator = SchemaValidator(schema_dir="k1/contracts/schemas")
        errors = validator.validate("kernel", config_data)
        if errors:
            for error in errors:
                print(f"Error at {error.path}: {error.message}")
    """

    def __init__(self, schema_dir: Optional[str] = None):
        """Initialize schema validator

        Args:
            schema_dir: Directory containing JSON schemas (default: k1/contracts/schemas)
        """
        if schema_dir is None:
            # Default to k1/contracts/schemas
            repo_root = Path(__file__).resolve().parents[3]
            self.schema_dir = repo_root / "k1" / "contracts" / "schemas"
        else:
            self.schema_dir = Path(schema_dir)

        # Schema cache (loaded once at startup)
        self._schemas: Dict[str, Dict[str, Any]] = {}
        self._validators: Dict[str, Draft7Validator] = {}

        # Load all schemas
        self._load_schemas()

        logger.info(
            "[SchemaValidator] Initialized",
            extra={
                "schema_dir": str(self.schema_dir),
                "num_schemas": len(self._schemas),
            },
        )

    def _load_schemas(self):
        """Load all JSON schemas from schema directory"""
        if not self.schema_dir.exists():
            logger.warning(
                "[SchemaValidator] Schema directory not found",
                extra={"schema_dir": str(self.schema_dir)},
            )
            return

        for schema_file in self.schema_dir.glob("*.schema.json"):
            config_name = schema_file.stem.replace(".schema", "")

            try:
                with open(schema_file, "r", encoding="utf-8") as f:
                    schema = json.load(f)

                # Validate schema itself
                Draft7Validator.check_schema(schema)

                # Cache schema and validator
                self._schemas[config_name] = schema
                self._validators[config_name] = Draft7Validator(schema)

                logger.debug(
                    "[SchemaValidator] Loaded schema",
                    extra={"config_name": config_name, "schema_file": schema_file.name},
                )

            except Exception as e:
                logger.error(
                    "[SchemaValidator] Failed to load schema",
                    extra={"config_name": config_name, "error": str(e)},
                )

    def validate(
        self, config_name: str, config_data: Dict[str, Any]
    ) -> List[ValidationError]:
        """Validate configuration against JSON schema

        Args:
            config_name: Config name (kernel, logging, circuit_breaker, thermal, metrics)
            config_data: Configuration dictionary (parsed YAML)

        Returns:
            List of validation errors (empty if valid)

        Performance: <10ms P95 (<5ms typical)
        """
        errors: List[ValidationError] = []

        # Check if schema exists
        if config_name not in self._validators:
            logger.warning(
                "[SchemaValidator] Schema not found",
                extra={
                    "config_name": config_name,
                    "available_schemas": list(self._schemas.keys()),
                },
            )
            errors.append(
                ValidationError(
                    path="",
                    message=f"No schema found for config '{config_name}'",
                    expected=f"One of: {', '.join(self._schemas.keys())}",
                    actual=config_name,
                )
            )
            return errors

        # Schema validation
        validator = self._validators[config_name]

        for json_error in validator.iter_errors(config_data):
            # Convert jsonschema ValidationError to our ValidationError
            path = ".".join(str(p) for p in json_error.absolute_path)
            if not path:
                path = json_error.json_path or "<root>"

            errors.append(
                ValidationError(
                    path=path,
                    message=json_error.message,
                    expected=self._format_constraint(json_error),
                    actual=json_error.instance,
                )
            )

        # Semantic validation (custom validators)
        semantic_errors = self._semantic_validation(config_name, config_data)
        errors.extend(semantic_errors)

        if errors:
            logger.warning(
                "[SchemaValidator] Validation failed",
                extra={"config_name": config_name, "num_errors": len(errors)},
            )
        else:
            logger.debug(
                "[SchemaValidator] Validation passed",
                extra={"config_name": config_name},
            )

        return errors

    def _format_constraint(
        self, json_error: JsonSchemaValidationError
    ) -> Optional[str]:
        """Format JSON Schema constraint as human-readable string"""
        if json_error.validator == "type":
            return f"type: {json_error.validator_value}"
        elif json_error.validator == "minimum":
            return f">= {json_error.validator_value}"
        elif json_error.validator == "maximum":
            return f"<= {json_error.validator_value}"
        elif json_error.validator == "minLength":
            return f"length >= {json_error.validator_value}"
        elif json_error.validator == "maxLength":
            return f"length <= {json_error.validator_value}"
        elif json_error.validator == "enum":
            return f"one of: {', '.join(map(str, json_error.validator_value))}"
        elif json_error.validator == "pattern":
            return f"pattern: {json_error.validator_value}"
        elif json_error.validator == "required":
            return f"required fields: {', '.join(json_error.validator_value)}"
        else:
            return None

    def _semantic_validation(
        self, config_name: str, config_data: Dict[str, Any]
    ) -> List[ValidationError]:
        """Perform semantic validation (beyond JSON Schema)

        Args:
            config_name: Config name
            config_data: Configuration dictionary

        Returns:
            List of semantic validation errors
        """
        errors: List[ValidationError] = []

        # Config-specific semantic validators
        if config_name == "thermal":
            errors.extend(self._validate_thermal_semantic(config_data))
        elif config_name == "circuit_breaker":
            errors.extend(self._validate_circuit_breaker_semantic(config_data))
        elif config_name == "kernel":
            errors.extend(self._validate_kernel_semantic(config_data))

        return errors

    def _validate_thermal_semantic(
        self, config_data: Dict[str, Any]
    ) -> List[ValidationError]:
        """Semantic validation for thermal config (ADR-0080, ADR-0009b)"""
        errors: List[ValidationError] = []

        if "thermal" not in config_data or "thresholds" not in config_data["thermal"]:
            return errors

        thresholds = config_data["thermal"]["thresholds"]

        # Extract temperatures
        cool = thresholds.get("cool_celsius", 50)
        warm = thresholds.get("warm_celsius", 65)
        hot = thresholds.get("hot_celsius", 80)
        critical = thresholds.get("critical_celsius", 90)

        # Check strictly increasing order: cool < warm < hot < critical
        if not (cool < warm < hot < critical):
            errors.append(
                ValidationError(
                    path="thermal.thresholds",
                    message="Temperature thresholds must be strictly increasing: cool < warm < hot < critical",
                    expected=f"{cool} < {warm} < {hot} < {critical}",
                    actual=f"cool={cool}, warm={warm}, hot={hot}, critical={critical}",
                )
            )

        return errors

    def _validate_circuit_breaker_semantic(
        self, config_data: Dict[str, Any]
    ) -> List[ValidationError]:
        """Semantic validation for circuit breaker config (ADR-0009b)"""
        errors: List[ValidationError] = []

        if "circuit_breakers" not in config_data:
            return errors

        for service_name, service_config in config_data["circuit_breakers"].items():
            # Check fallback_strategy matches alternate_service if provided
            if service_config.get("fallback_strategy") == "alternate_model":
                if "alternate_service" not in service_config:
                    errors.append(
                        ValidationError(
                            path=f"circuit_breakers.{service_name}.alternate_service",
                            message="alternate_service required when fallback_strategy='alternate_model'",
                            expected="service name (e.g., 'model_hub_remote')",
                            actual="<missing>",
                        )
                    )

            # Check cached_result strategy has cache_ttl_ms
            if service_config.get("fallback_strategy") == "cached_result":
                if "cache_ttl_ms" not in service_config:
                    errors.append(
                        ValidationError(
                            path=f"circuit_breakers.{service_name}.cache_ttl_ms",
                            message="cache_ttl_ms required when fallback_strategy='cached_result'",
                            expected="TTL in milliseconds (e.g., 300000)",
                            actual="<missing>",
                        )
                    )

        return errors

    def _validate_kernel_semantic(
        self, config_data: Dict[str, Any]
    ) -> List[ValidationError]:
        """Semantic validation for kernel config"""
        errors: List[ValidationError] = []

        if "kernel" not in config_data:
            return errors

        kernel = config_data["kernel"]

        # Check session_timeout >= supervisor_check_interval
        session_timeout = kernel.get("session_timeout_ms", 300000)
        check_interval = kernel.get("supervisor_check_interval_ms", 1000)

        if session_timeout < check_interval:
            errors.append(
                ValidationError(
                    path="kernel.session_timeout_ms",
                    message="session_timeout_ms must be >= supervisor_check_interval_ms",
                    expected=f">= {check_interval}",
                    actual=session_timeout,
                )
            )

        return errors
        return errors
        return errors
