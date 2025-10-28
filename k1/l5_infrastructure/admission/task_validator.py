"""
Task Validator - Schema Validation and Request Type Checking

Layer: L5 Infrastructure
Component: Admission Control
Priority: P2 (Flow Control)
Status: 🚧 STUB - NEEDS_IMPLEMENTATION

Architecture Decision Records:
    - ADR-0032: Admission Control Design
    - ADR-0011: FlatBuffers Serialization (schema format)
    - ADR-0013: Schema Evolution and Versioning

Dependencies:
    Internal:
        - k1.contracts.jsonschema (task schemas)
        - k1.l5_infrastructure.metrics (observability)
    External:
        - jsonschema (JSON Schema validation)
        - json (JSON parsing)
        - typing (type hints)
        - logging (structured logging)

Connects To:
    Upstream:
        - k1.l5_infrastructure.admission.admission_controller (validation requests)
    Downstream:
        - k1.contracts.jsonschema.tasks (schema registry)

Performance Budgets:
    - Schema registration: <1ms
    - Validation (with cache): <2ms P95
    - Schema reload: <100ms
    - Metrics aggregation: <5ms
    - Cache hit rate: >90% target

Observability:
    - Metrics:
        - k1_task_validator_validation_total{status, task_type} (counter)
        - k1_task_validator_validation_latency_ms{p50, p95, p99} (histogram)
        - k1_task_validator_schema_errors_total{error_type} (counter)
        - k1_task_validator_cache_hit_rate (gauge)
        - k1_task_validator_schemas_registered (gauge)
    - Traces:
        - Span: task_validator.validate
        - Attributes: task_type, schema_version, validation_result, cognitive_trace_id
    - Logs:
        - INFO: validation result (task_type, valid, latency_ms)
        - WARNING: schema validation failed (task_type, field, error)
        - ERROR: unknown task type (task_type)

References:
    - Diagram: architecture_diagrams/k1/k1_admission_control.mmd
    - Whiteboard: docs/whiteboard.md (Section 7: Flow Control)
    - Test: tests/k1/l5_infrastructure/admission/test_task_validator.py
    - Schemas: k1/contracts/jsonschema/tasks/*.json
"""

import logging
import time
from dataclasses import dataclass
from enum import Enum
# =============================================================================
# SECTION 1: IMPORTS
# =============================================================================
# Standard library imports
from typing import TYPE_CHECKING, Any, Dict, List, Optional

# Forward reference for type hints (avoid circular import)
if TYPE_CHECKING:
    from k1.l5_infrastructure.admission.admission_controller import Request

# Third-party imports
try:
    import jsonschema
    from jsonschema import Draft7Validator
except ImportError:
    # TODO(@platform-team): Install jsonschema package
    jsonschema = None
    Draft7Validator = None

# Internal imports
# TODO(@platform-team): Import after implementing dependent modules
# from k1.l5_infrastructure.metrics import MetricsCollector

# Configure module logger
logger = logging.getLogger(__name__)

# =============================================================================
# SECTION 2: CONSTANTS & CONFIGURATION
# =============================================================================

# TODO(@platform-team): Load from k1/config/admission_control.yml (ADR-0032)
# Assigned to: Issue #L5-12.2.1
DEFAULT_CONFIG = {
    # Schema cache configuration
    'schema_cache_enabled': True,
    'schema_cache_size': 1000,
    'schema_cache_ttl_seconds': 3600,  # 1 hour

    # Validation configuration
    'lenient_mode_enabled': False,  # Warn on unknown fields vs reject
    'hot_reload_enabled': True,  # Allow runtime schema updates
    'validation_timeout_ms': 2,  # Max validation time

    # Schema paths
    'schema_directory': 'k1/contracts/jsonschema/tasks',

    # SLA constraints
    'min_sla_ms': 100,  # Minimum allowed SLA deadline
    'max_sla_ms': 300000,  # Maximum allowed SLA deadline (5 minutes)
}

# Default SLA deadline (5 seconds)
DEFAULT_DEADLINE_MS = 5000

# =============================================================================
# SECTION 3: TYPE DEFINITIONS & ENUMS
# =============================================================================

class ValidationStatus(Enum):
    """Validation result status (ADR-0032)"""
    VALID = 'VALID'  # Request is valid
    UNKNOWN_TYPE = 'UNKNOWN_TYPE'  # Task type not registered
    SCHEMA_INVALID = 'SCHEMA_INVALID'  # Schema validation failed
    MISSING_FIELD = 'MISSING_FIELD'  # Required field missing
    TYPE_MISMATCH = 'TYPE_MISMATCH'  # Field type incorrect
    SLA_OUT_OF_RANGE = 'SLA_OUT_OF_RANGE'  # SLA deadline invalid
    INVALID_PRIVACY_BAND = 'INVALID_PRIVACY_BAND'  # Privacy band invalid


@dataclass
class ValidationResult:
    """
    Validation result structure.

    Fields:
        status: ValidationStatus enum
        is_valid: Boolean validity flag
        error_message: Error message (if invalid)
        field_name: Field that failed validation (if applicable)
        expected_type: Expected type for field (if type mismatch)
        actual_type: Actual type for field (if type mismatch)
        validation_latency_ms: Validation duration
    """
    status: ValidationStatus
    is_valid: bool
    error_message: Optional[str] = None
    field_name: Optional[str] = None
    expected_type: Optional[str] = None
    actual_type: Optional[str] = None
    validation_latency_ms: float = 0.0


@dataclass
class TaskSchema:
    """
    Task schema metadata.

    Fields:
        task_type: Task type identifier (e.g., "inference")
        version: Schema version (e.g., "1.0")
        schema: JSON Schema dict
        required_fields: List of required field names
        optional_fields: List of optional field names
        created_at_ms: Schema registration timestamp
    """
    task_type: str
    version: str
    schema: Dict[str, Any]
    required_fields: List[str]
    optional_fields: List[str]
    created_at_ms: int


@dataclass
class ValidationMetrics:
    """
    Validation metrics snapshot.

    Fields:
        total_validations: Total validations performed
        valid_count: Successful validations
        invalid_count: Failed validations
        error_breakdown: Errors by type
        cache_hit_rate: Validation cache hit rate
        avg_validation_latency_ms: Average validation latency
        p95_validation_latency_ms: P95 validation latency
        schemas_registered: Total schemas registered
    """
    total_validations: int
    valid_count: int
    invalid_count: int
    error_breakdown: Dict[str, int]
    cache_hit_rate: float
    avg_validation_latency_ms: float
    p95_validation_latency_ms: float
    schemas_registered: int


# =============================================================================
# SECTION 4: CORE CLASSES
# =============================================================================

class TaskValidator:
    """
    Schema validation for task requests with JSON Schema registry.

    Purpose:
        Register and manage task schemas, validate incoming requests against
        schemas, provide type checking, field validation, and error reporting.

    Responsibilities:
        1. Register and manage task schemas (JSON Schema, FlatBuffers)
        2. Validate incoming requests against schemas
        3. Type checking (known task types)
        4. Field validation (required fields, type constraints)
        5. Performance validation (check against SLA requirements)
        6. Privacy metadata validation
        7. Schema hot-reload support
        8. Validation caching for performance

    Schema Registry:
        - Built-in schemas for 7 standard task types (inference, training, etc.)
        - User-defined schemas loaded from k1/contracts/jsonschema/tasks/
        - Schema versioning (v1.0, v1.1, v2.0)
        - Hot-reload support for schema updates

    Validation Levels:
        1. Type Check: Is task_type in registered_types?
        2. Schema Check: Does request match JSON Schema?
        3. Field Check: Are required fields present? Types correct?
        4. Performance Check: Does SLA fit within execution budgets?
        5. Privacy Check: Privacy band metadata present and valid?

    Thread Safety: Yes (async-safe with locks)
    Async Safe: Yes (fully async)

    Cognitive Trace:
        - Propagates cognitive_trace_id to validation operations
        - Required for: validate()

    Performance Budget (P95):
        - Schema registration: <1ms
        - Validation (with cache): <2ms
        - Schema reload: <100ms
        - Cache hit rate target: >90%

    Examples:
        >>> config = DEFAULT_CONFIG
        >>> validator = TaskValidator(config)
        >>> await validator.initialize()
        >>> result = await validator.validate(request)
        >>> if result.is_valid:
        ...     # Proceed with admission
        >>> await validator.shutdown()

    References:
        - ADR-0032: Admission Control Design
        - ADR-0011: FlatBuffers Serialization
        - ADR-0013: Schema Evolution and Versioning
        - Schemas: k1/contracts/jsonschema/tasks/
    """

    def __init__(self, config: Dict[str, Any] = DEFAULT_CONFIG) -> None:
        """
        Initialize Task Validator.

        Args:
            config: Configuration dict with schema paths, cache settings

        Raises:
            ValueError: If configuration is invalid
            TypeError: If config type is incorrect

        Side Effects:
            - Initializes schema registry
            - Creates validation cache
            - Loads built-in schemas

        ADR: ADR-0032 (Admission Control Design)
        Assigned to: Issue #L5-12.2.1
        """
        # TODO(@platform-team): Implement initialization (ADR-0032)
        # 1. Validate config
        # 2. Initialize schema registry (dict: task_type → TaskSchema)
        # 3. Setup validation cache (LRU cache)
        # 4. Load built-in schemas (7 standard task types)
        # 5. Setup metrics collectors
        self.config = config
        self._logger = logger

        # Schema registry: {task_type: {version: TaskSchema}}
        self.schema_registry: Dict[str, Dict[str, TaskSchema]] = {}

        # Validation cache: {request_hash: ValidationResult}
        self.validation_cache: Dict[str, ValidationResult] = {}
        self.cache_hits = 0
        self.cache_misses = 0

        # Metrics state
        self.total_validations = 0
        self.valid_count = 0
        self.invalid_count = 0
        self.error_breakdown: Dict[str, int] = {}
        self.validation_latencies: List[float] = []

        self._logger.info(f"TaskValidator initialized with schema_cache_enabled={config['schema_cache_enabled']}")

    async def initialize(self) -> None:
        """
        Async initialization phase (called after __init__).

        This method performs async setup that cannot be done in __init__.

        Raises:
            RuntimeError: If initialization fails
            FileNotFoundError: If schema directory not found

        Lifecycle:
            Called after __init__, before validator becomes active

        ADR: ADR-0032
        Assigned to: Issue #L5-12.2.1
        """
        # TODO(@platform-team): Implement async initialization (ADR-0032)
        # 1. Load schemas from disk (k1/contracts/jsonschema/tasks/)
        # 2. Register built-in schemas (7 standard task types)
        # 3. Setup file watchers for hot-reload (if enabled)
        # 4. Register with observability stack
        self._logger.info("TaskValidator async initialization started")

        # Register built-in schemas
        await self._register_builtin_schemas()

    async def _register_builtin_schemas(self) -> None:
        """
        Register built-in schemas for standard task types.

        Built-in Task Types:
            1. inference - Run model inference on input data
            2. training - Train model on dataset
            3. evaluation - Evaluate model on test set
            4. preprocessing - Prepare data for training
            5. postprocessing - Transform model outputs
            6. monitoring - Health check and telemetry
            7. maintenance - Background cleanup tasks

        ADR: ADR-0032
        """
        # TODO(@platform-team): Implement built-in schema registration (ADR-0032)
        # 1. Define JSON schemas for 7 standard task types
        # 2. Register each schema with version 1.0
        # 3. Log registration success

        # Example: inference schema
        inference_schema = {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
            "required": ["model_id", "input_data", "priority"],
            "properties": {
                "model_id": {"type": "string"},
                "input_data": {"type": "object"},
                "priority": {"type": "string", "enum": ["CRITICAL", "HIGH", "NORMAL", "LOW", "BACKGROUND"]},
                "deadline_ms": {"type": "integer", "minimum": 100},
                "privacy_band": {"type": "string", "enum": ["RED", "AMBER", "GREEN"]},
                "batch_size": {"type": "integer", "minimum": 1},
            }
        }

        await self.register_schema("inference", inference_schema, version="1.0")
        self._logger.info("Built-in schema registered: inference v1.0")

    async def register_schema(
        self,
        task_type: str,
        schema: Dict[str, Any],
        version: str = "1.0",
    ) -> None:
        """
        Register a new task type schema.

        Args:
            task_type: Unique task type identifier (e.g., "inference")
            schema: JSON Schema dict
            version: Schema version (e.g., "1.0")

        Raises:
            ValueError: If schema is invalid
            TypeError: If schema type is incorrect

        Performance:
            - <1ms registration time

        Observability:
            - Metrics: k1_task_validator_schemas_registered (gauge)
            - Logs: INFO: schema registered (task_type, version)

        ADR: ADR-0032
        Assigned to: Issue #L5-12.2.1
        """
        # TODO(@platform-team): Implement schema registration (ADR-0032)
        # 1. Validate schema structure (is it valid JSON Schema?)
        # 2. Extract required and optional fields
        # 3. Create TaskSchema object
        # 4. Store in registry: schema_registry[task_type][version]
        # 5. Clear validation cache (schema changed)
        # 6. Emit metrics

        if task_type not in self.schema_registry:
            self.schema_registry[task_type] = {}

        task_schema = TaskSchema(
            task_type=task_type,
            version=version,
            schema=schema,
            required_fields=schema.get('required', []),
            optional_fields=[k for k in schema.get('properties', {}).keys() if k not in schema.get('required', [])],
            created_at_ms=int(time.time() * 1000),
        )

        self.schema_registry[task_type][version] = task_schema
        self._logger.info(f"Schema registered: {task_type} v{version}")

    async def validate(
        self,
        request: 'Request',  # Forward reference from admission_controller
    ) -> ValidationResult:
        """
        Validate request against registered schema.

        Args:
            request: Task request to validate (from admission_controller.Request)

        Returns:
            ValidationResult with status and error details if invalid

        Raises:
            ValueError: If request is None or malformed
            TimeoutError: If validation exceeds timeout (>2ms)

        Performance:
            - Target: <2ms P95 validation time (with caching)
            - Cache hit: <0.1ms
            - Cache miss: <2ms

        Validation Pipeline:
            1. Check validation cache (request hash)
            2. Type validation (is task_type registered?)
            3. Schema validation (JSON Schema check)
            4. Field extraction & type validation
            5. Performance validation (SLA deadline check)
            6. Privacy metadata validation
            7. Cache result
            8. Return ValidationResult

        Observability:
            - Metrics: k1_task_validator_validation_total{status, task_type}
            - Metrics: k1_task_validator_validation_latency_ms{p50, p95, p99}
            - Traces: Span name: task_validator.validate
            - Logs: INFO: validation result (task_type, valid, latency_ms)

        Cognitive Trace:
            - Accepts cognitive_trace_id from request
            - Propagates to all validation checks
            - Logs include trace_id

        ADR: ADR-0032 (Admission Control Design)
        Assigned to: Issue #L5-12.2.1
        """
        # TODO(@platform-team): Implement validation logic (ADR-0032)
        # This is the core validation algorithm from the milestone spec

        start_time_ms = time.time() * 1000
        self.total_validations += 1

        self._logger.info(
            f"Validation request: task_type={request.task_type}, "
            f"request_id={request.request_id}, "
            f"trace_id={request.cognitive_trace_id}"
        )

        # 1. Check validation cache (if enabled)
        request_hash = self._compute_request_hash(request)
        if self.config['schema_cache_enabled'] and request_hash in self.validation_cache:
            self.cache_hits += 1
            cached_result = self.validation_cache[request_hash]
            self._logger.debug(f"Validation cache hit: {request.task_type}")
            return cached_result

        self.cache_misses += 1

        # 2. Type validation
        if request.task_type not in self.schema_registry:
            result = ValidationResult(
                status=ValidationStatus.UNKNOWN_TYPE,
                is_valid=False,
                error_message=f"Unknown task type: {request.task_type}",
            )
            self.invalid_count += 1
            self.error_breakdown['UNKNOWN_TYPE'] = self.error_breakdown.get('UNKNOWN_TYPE', 0) + 1
            return result

        # 3. Get schema (default to latest version)
        schemas = self.schema_registry[request.task_type]
        latest_version = max(schemas.keys())
        task_schema = schemas[latest_version]

        # 4. JSON Schema validation
        if jsonschema is not None and Draft7Validator is not None:
            validator = Draft7Validator(task_schema.schema)
            errors = list(validator.iter_errors(request.payload))
            if errors:
                error = errors[0]
                result = ValidationResult(
                    status=ValidationStatus.SCHEMA_INVALID,
                    is_valid=False,
                    error_message=f"Schema validation failed: {error.message}",
                    field_name=str(error.path[0]) if error.path else None,
                )
                self.invalid_count += 1
                self.error_breakdown['SCHEMA_INVALID'] = self.error_breakdown.get('SCHEMA_INVALID', 0) + 1
                return result

        # 5. Field extraction & type validation
        for field in task_schema.required_fields:
            if field not in request.payload:
                result = ValidationResult(
                    status=ValidationStatus.MISSING_FIELD,
                    is_valid=False,
                    error_message=f"Missing required field: {field}",
                    field_name=field,
                )
                self.invalid_count += 1
                self.error_breakdown['MISSING_FIELD'] = self.error_breakdown.get('MISSING_FIELD', 0) + 1
                return result

        # 6. Performance validation (SLA deadline check)
        sla_deadline = request.payload.get('deadline_ms', DEFAULT_DEADLINE_MS)
        min_sla = self.config['min_sla_ms']
        max_sla = self.config['max_sla_ms']
        if sla_deadline < min_sla or sla_deadline > max_sla:
            result = ValidationResult(
                status=ValidationStatus.SLA_OUT_OF_RANGE,
                is_valid=False,
                error_message=f"SLA deadline out of range: {sla_deadline}ms (allowed: {min_sla}-{max_sla}ms)",
            )
            self.invalid_count += 1
            self.error_breakdown['SLA_OUT_OF_RANGE'] = self.error_breakdown.get('SLA_OUT_OF_RANGE', 0) + 1
            return result

        # 7. Privacy metadata validation
        privacy_band = request.payload.get('privacy_band', 'GREEN')
        if privacy_band not in ['RED', 'AMBER', 'GREEN']:
            result = ValidationResult(
                status=ValidationStatus.INVALID_PRIVACY_BAND,
                is_valid=False,
                error_message=f"Invalid privacy band: {privacy_band}",
            )
            self.invalid_count += 1
            self.error_breakdown['INVALID_PRIVACY_BAND'] = self.error_breakdown.get('INVALID_PRIVACY_BAND', 0) + 1
            return result

        # 8. All checks passed
        end_time_ms = time.time() * 1000
        validation_latency_ms = end_time_ms - start_time_ms
        self.validation_latencies.append(validation_latency_ms)

        result = ValidationResult(
            status=ValidationStatus.VALID,
            is_valid=True,
            validation_latency_ms=validation_latency_ms,
        )

        # 9. Cache result (if enabled)
        if self.config['schema_cache_enabled']:
            self.validation_cache[request_hash] = result

        self.valid_count += 1

        self._logger.info(
            f"Validation result: task_type={request.task_type}, "
            f"valid={result.is_valid}, latency_ms={validation_latency_ms:.2f}"
        )

        return result

    async def get_schema(self, task_type: str, version: str = "latest") -> Optional[Dict[str, Any]]:
        """
        Get registered schema for task type.

        Args:
            task_type: Task type identifier
            version: Schema version (default: latest)

        Returns:
            JSON Schema dict or None if not found

        Performance:
            - <1ms lookup time

        ADR: ADR-0032
        Assigned to: Issue #L5-12.2.1
        """
        # TODO(@platform-team): Implement schema lookup (ADR-0032)
        # 1. Check if task_type in registry
        # 2. If version == "latest", get max version
        # 3. Return schema dict

        if task_type not in self.schema_registry:
            return None

        schemas = self.schema_registry[task_type]
        if version == "latest":
            version = max(schemas.keys())

        if version not in schemas:
            return None

        return schemas[version].schema

    async def reload_schemas_from_disk(self) -> int:
        """
        Hot-reload schemas from k1/contracts/jsonschema/tasks/.

        Useful for deploying new schemas without restarting.

        Returns:
            Number of schemas reloaded

        Performance:
            - <100ms reload time

        Raises:
            FileNotFoundError: If schema directory not found
            ValueError: If schema file is invalid

        Observability:
            - Logs: INFO: schemas reloaded (count, duration_ms)

        ADR: ADR-0032
        Assigned to: Issue #L5-12.2.1
        """
        # TODO(@platform-team): Implement hot-reload (ADR-0032)
        # 1. Scan schema directory (k1/contracts/jsonschema/tasks/)
        # 2. Load JSON files
        # 3. Parse and validate schemas
        # 4. Update registry
        # 5. Clear validation cache
        # 6. Emit metrics
        # 7. Return count

        self._logger.info("Hot-reloading schemas from disk")
        return 0

    async def get_validation_metrics(self) -> ValidationMetrics:
        """
        Get validation statistics (validation count, error breakdown, cache hit rate).

        Returns:
            ValidationMetrics with validation_count, errors_by_type, cache_hit_rate

        Performance:
            - <5ms metrics collection

        Observability:
            - Metrics: All validation metrics exported to Prometheus

        ADR: ADR-0032
        Assigned to: Issue #L5-12.2.1
        """
        # TODO(@platform-team): Implement metrics collection (ADR-0032)
        # 1. Calculate cache hit rate
        # 2. Calculate P95 validation latency
        # 3. Count schemas registered
        # 4. Return ValidationMetrics

        total_cache_checks = self.cache_hits + self.cache_misses
        cache_hit_rate = self.cache_hits / total_cache_checks if total_cache_checks > 0 else 0.0

        # Calculate P95 latency
        sorted_latencies = sorted(self.validation_latencies)
        p95_index = int(len(sorted_latencies) * 0.95)
        p95_latency_ms = sorted_latencies[p95_index] if sorted_latencies else 0.0
        avg_latency_ms = sum(self.validation_latencies) / len(self.validation_latencies) if self.validation_latencies else 0.0

        schemas_registered = sum(len(versions) for versions in self.schema_registry.values())

        return ValidationMetrics(
            total_validations=self.total_validations,
            valid_count=self.valid_count,
            invalid_count=self.invalid_count,
            error_breakdown=self.error_breakdown.copy(),
            cache_hit_rate=cache_hit_rate,
            avg_validation_latency_ms=avg_latency_ms,
            p95_validation_latency_ms=p95_latency_ms,
            schemas_registered=schemas_registered,
        )

    async def shutdown(self) -> None:
        """
        Graceful shutdown sequence.

        This method performs cleanup and state transitions.

        Lifecycle:
            - Flushes validation cache
            - Finalizes metrics
            - Closes file watchers

        Guarantees:
            - No data loss
            - Graceful degradation

        ADR: ADR-0032
        Assigned to: Issue #L5-12.2.1
        """
        # TODO(@platform-team): Implement shutdown (ADR-0032)
        # 1. Flush validation cache
        # 2. Finalize metrics
        # 3. Close file watchers
        # 4. Log shutdown complete
        self._logger.info("TaskValidator shutdown initiated")

    # =========================================================================
    # PRIVATE METHODS (Implementation Details)
    # =========================================================================

    def _compute_request_hash(self, request: 'Request') -> str:
        """
        Compute hash for request caching.

        Args:
            request: Task request

        Returns:
            Hash string

        ADR: ADR-0032
        """
        # TODO(@platform-team): Implement request hashing (ADR-0032)
        # 1. Extract task_type, priority, payload
        # 2. Compute hash (e.g., SHA256)
        # 3. Return hash string
        return f"{request.task_type}:{request.request_id}"

    def _validate_schema_structure(self, schema: Dict[str, Any]) -> bool:
        """
        Validate schema is valid JSON Schema.

        Args:
            schema: JSON Schema dict

        Returns:
            True if valid, False otherwise

        ADR: ADR-0032
        """
        # TODO(@platform-team): Implement schema structure validation (ADR-0032)
        # 1. Check if schema has "$schema" field
        # 2. Check if schema has "type" field
        # 3. Check if schema has "properties" field
        # 4. Return validity
        return True


# =============================================================================
# SECTION 5: HELPER FUNCTIONS
# =============================================================================

def extract_required_fields(schema: Dict[str, Any]) -> List[str]:
    """
    Extract required fields from JSON Schema.

    Args:
        schema: JSON Schema dict

    Returns:
        List of required field names

    ADR: ADR-0032
    Assigned to: Issue #L5-12.2.1
    """
    # TODO(@platform-team): Implement required fields extraction (ADR-0032)
    return schema.get('required', [])


def extract_optional_fields(schema: Dict[str, Any]) -> List[str]:
    """
    Extract optional fields from JSON Schema.

    Args:
        schema: JSON Schema dict

    Returns:
        List of optional field names

    ADR: ADR-0032
    Assigned to: Issue #L5-12.2.1
    """
    # TODO(@platform-team): Implement optional fields extraction (ADR-0032)
    required = schema.get('required', [])
    all_fields = list(schema.get('properties', {}).keys())
    return [field for field in all_fields if field not in required]


# =============================================================================
# SECTION 6: MODULE EXPORTS & INITIALIZATION
# =============================================================================

__all__ = [
    'TaskValidator',
    'ValidationStatus',
    'ValidationResult',
    'ValidationMetrics',
    'TaskSchema',
]

# Module initialization hook (optional)
async def initialize_task_validator(config: Dict[str, Any] = DEFAULT_CONFIG) -> TaskValidator:
    """
    Initialize task validator with default configuration.

    Args:
        config: Configuration dict (defaults to DEFAULT_CONFIG)

    Returns:
        Initialized TaskValidator instance

    ADR: ADR-0032
    """
    # TODO(@platform-team): Implement module initialization (ADR-0032)
    validator = TaskValidator(config)
    await validator.initialize()
    return validator


# =============================================================================
# OBSERVABILITY INTEGRATION
# =============================================================================
# Metrics to export:
#   - k1_task_validator_validation_total{status, task_type} - Total validations
#   - k1_task_validator_validation_latency_ms{p50, p95, p99} - Validation latency histogram
#   - k1_task_validator_schema_errors_total{error_type} - Schema error count
#   - k1_task_validator_cache_hit_rate - Validation cache hit rate
#   - k1_task_validator_schemas_registered - Total schemas registered
#
# Traces to generate:
#   - Span name: task_validator.validate
#   - Attributes: task_type, schema_version, validation_result, cognitive_trace_id
#
# Logs to emit:
#   - Level: INFO (validation result), WARNING (schema validation failed), ERROR (unknown task type)
#   - Fields: task_type, request_id, valid, error_message, latency_ms, trace_id
#
# =============================================================================

# =============================================================================
# COGNITIVE TRACE PROPAGATION
# =============================================================================
# All async methods must:
#   1. Accept cognitive_trace_id parameter in Request
#   2. Create trace span with this ID
#   3. Pass ID to downstream components
#   4. Include ID in all log statements
#
# This enables end-to-end request tracing across K1 layers.
#
# =============================================================================

# =============================================================================
# TESTING REQUIREMENTS (pytest Framework)
# =============================================================================
# Integration tests required:
#   - tests/k1/l5_infrastructure/admission/test_task_validator.py
#   - Schema registration tests (register, lookup, hot-reload)
#   - Validation tests (valid requests, invalid requests, error cases)
#   - Performance budget tests (ensure <2ms P95 validation time)
#   - Cache tests (hit rate >90%, cache invalidation)
#   - Error handling tests (unknown task type, schema validation failure)
#
# No simulation code allowed:
#   - No asyncio.sleep() for testing timeouts
#   - Use real components or pytest fixtures
#   - Integration tests > unit tests
#
# =============================================================================
