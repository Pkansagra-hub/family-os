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

# TODO: Implement SchemaValidator with JSON Schema Draft 7
