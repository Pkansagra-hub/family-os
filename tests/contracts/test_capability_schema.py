"""
Tests for capability JSON Schema validation.

Issue 1.3.1: Create Capability JSON Schema
ADR: ADR-K004 Capability Mesh Architecture
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft7Validator

# Path to the capability schema
REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = REPO_ROOT / "k0" / "contracts" / "jsonschema" / "capability.schema.json"


@pytest.fixture
def capability_schema() -> dict[str, Any]:
    """Load the capability JSON schema."""
    return json.loads(SCHEMA_PATH.read_text())


@pytest.fixture
def validator(capability_schema: dict[str, Any]) -> Draft7Validator:
    """Create a JSON Schema validator."""
    return Draft7Validator(capability_schema)


# -----------------------------------------------------------------------------
# Schema Validity Tests
# -----------------------------------------------------------------------------


class TestSchemaValidity:
    """Tests for schema structure validity."""

    def test_schema_is_valid_draft7(self, capability_schema: dict[str, Any]):
        """Schema passes Draft7 validation."""
        Draft7Validator.check_schema(capability_schema)

    def test_schema_has_required_fields(self, capability_schema: dict[str, Any]):
        """Schema has required top-level fields."""
        assert capability_schema["$schema"] == "http://json-schema.org/draft-07/schema#"
        assert "title" in capability_schema
        assert "definitions" in capability_schema
        assert "capability" in capability_schema["definitions"]
        assert "provider" in capability_schema["definitions"]


# -----------------------------------------------------------------------------
# Valid Capability Tests
# -----------------------------------------------------------------------------


class TestValidCapabilities:
    """Tests for valid capability definitions."""

    def test_valid_module_provider_validates(self, validator: Draft7Validator):
        """Valid module provider passes validation."""
        doc = {
            "version": "v1",
            "capabilities": {
                "score_salience": {
                    "description": "Compute salience score",
                    "providers": [
                        {
                            "type": "module",
                            "module_id": "salience.score",
                            "priority": 1,
                        }
                    ],
                }
            },
        }
        errors = list(validator.iter_errors(doc))
        assert len(errors) == 0, f"Unexpected errors: {[e.message for e in errors]}"

    def test_valid_pipeline_provider_validates(self, validator: Draft7Validator):
        """Valid pipeline provider passes validation."""
        doc = {
            "version": "v1",
            "capabilities": {
                "consolidate_memory": {
                    "description": "Consolidate memories",
                    "providers": [
                        {
                            "type": "pipeline",
                            "pipeline_id": "P03_CONSOLIDATION",
                            "request_topic": "fabric.consolidation.request.v1",
                            "response_topic": "fabric.consolidation.response.v1",
                            "priority": 1,
                        }
                    ],
                }
            },
        }
        errors = list(validator.iter_errors(doc))
        assert len(errors) == 0, f"Unexpected errors: {[e.message for e in errors]}"

    def test_valid_module_provider_with_version(self, validator: Draft7Validator):
        """Module provider with version suffix validates."""
        doc = {
            "version": "v1",
            "capabilities": {
                "pattern_separate": {
                    "description": "Pattern separation",
                    "providers": [
                        {
                            "type": "module",
                            "module_id": "hippocampus.pattern_separate:v1",
                            "priority": 1,
                            "latency_budget_ms": 15,
                        }
                    ],
                }
            },
        }
        errors = list(validator.iter_errors(doc))
        assert len(errors) == 0, f"Unexpected errors: {[e.message for e in errors]}"

    def test_capability_without_providers_validates(self, validator: Draft7Validator):
        """Capability without providers (declaration only) validates."""
        doc = {
            "version": "v1",
            "capabilities": {
                "future_capability": {
                    "description": "Placeholder for future capability",
                }
            },
        }
        errors = list(validator.iter_errors(doc))
        assert len(errors) == 0, f"Unexpected errors: {[e.message for e in errors]}"

    def test_multiple_capabilities_validate(self, validator: Draft7Validator):
        """Multiple capabilities in one file validate."""
        doc = {
            "version": "v1",
            "capabilities": {
                "cap1": {
                    "description": "First capability",
                    "providers": [{"type": "module", "module_id": "mod.func"}],
                },
                "cap2": {
                    "description": "Second capability",
                    "providers": [{"type": "module", "module_id": "mod.other"}],
                },
            },
        }
        errors = list(validator.iter_errors(doc))
        assert len(errors) == 0, f"Unexpected errors: {[e.message for e in errors]}"

    def test_provider_with_all_optional_fields(self, validator: Draft7Validator):
        """Provider with all optional fields validates."""
        doc = {
            "version": "v1",
            "capabilities": {
                "full_config": {
                    "description": "Fully configured capability",
                    "default_timeout_ms": 200,
                    "providers": [
                        {
                            "type": "module",
                            "module_id": "test.module",
                            "priority": 5,
                            "condition": "fallback",
                            "latency_budget_ms": 50,
                            "timeout_ms": 100,
                        }
                    ],
                }
            },
        }
        errors = list(validator.iter_errors(doc))
        assert len(errors) == 0, f"Unexpected errors: {[e.message for e in errors]}"


# -----------------------------------------------------------------------------
# Invalid Capability Tests
# -----------------------------------------------------------------------------


class TestInvalidCapabilities:
    """Tests for invalid capability definitions."""

    def test_missing_version_fails(self, validator: Draft7Validator):
        """Missing version fails validation."""
        doc = {"capabilities": {"test": {"description": "Test"}}}
        errors = list(validator.iter_errors(doc))
        assert any("version" in str(e.message) for e in errors)

    def test_invalid_version_format_fails(self, validator: Draft7Validator):
        """Invalid version format fails validation."""
        doc = {"version": "1.0", "capabilities": {"test": {"description": "Test"}}}  # Should be v1
        errors = list(validator.iter_errors(doc))
        assert len(errors) > 0

    def test_missing_capabilities_fails(self, validator: Draft7Validator):
        """Missing capabilities fails validation."""
        doc = {"version": "v1"}
        errors = list(validator.iter_errors(doc))
        assert any("capabilities" in str(e.message) for e in errors)

    def test_empty_capabilities_fails(self, validator: Draft7Validator):
        """Empty capabilities fails validation."""
        doc = {"version": "v1", "capabilities": {}}
        errors = list(validator.iter_errors(doc))
        assert len(errors) > 0

    def test_missing_description_fails(self, validator: Draft7Validator):
        """Missing capability description fails validation."""
        doc = {
            "version": "v1",
            "capabilities": {"test": {"providers": [{"type": "module", "module_id": "test.mod"}]}},
        }
        errors = list(validator.iter_errors(doc))
        assert any("description" in str(e.message) for e in errors)

    def test_missing_module_id_fails(self, validator: Draft7Validator):
        """Module provider without module_id fails validation."""
        doc = {
            "version": "v1",
            "capabilities": {
                "test": {"description": "Test", "providers": [{"type": "module", "priority": 1}]}
            },
        }
        errors = list(validator.iter_errors(doc))
        assert len(errors) > 0

    def test_missing_pipeline_topics_fails(self, validator: Draft7Validator):
        """Pipeline provider without topics fails validation."""
        doc = {
            "version": "v1",
            "capabilities": {
                "test": {
                    "description": "Test",
                    "providers": [
                        {
                            "type": "pipeline",
                            "pipeline_id": "P01_TEST",
                        }
                    ],
                }
            },
        }
        errors = list(validator.iter_errors(doc))
        assert len(errors) > 0

    def test_invalid_module_id_pattern_fails(self, validator: Draft7Validator):
        """Invalid module_id pattern fails validation."""
        doc = {
            "version": "v1",
            "capabilities": {
                "test": {
                    "description": "Test",
                    "providers": [
                        {
                            "type": "module",
                            "module_id": "InvalidModule",  # Should be lowercase with dot
                        }
                    ],
                }
            },
        }
        errors = list(validator.iter_errors(doc))
        assert len(errors) > 0

    def test_invalid_priority_too_low_fails(self, validator: Draft7Validator):
        """Priority below 1 fails validation."""
        doc = {
            "version": "v1",
            "capabilities": {
                "test": {
                    "description": "Test",
                    "providers": [
                        {
                            "type": "module",
                            "module_id": "test.mod",
                            "priority": 0,
                        }
                    ],
                }
            },
        }
        errors = list(validator.iter_errors(doc))
        assert len(errors) > 0

    def test_invalid_priority_too_high_fails(self, validator: Draft7Validator):
        """Priority above 100 fails validation."""
        doc = {
            "version": "v1",
            "capabilities": {
                "test": {
                    "description": "Test",
                    "providers": [
                        {
                            "type": "module",
                            "module_id": "test.mod",
                            "priority": 101,
                        }
                    ],
                }
            },
        }
        errors = list(validator.iter_errors(doc))
        assert len(errors) > 0

    def test_invalid_provider_type_fails(self, validator: Draft7Validator):
        """Invalid provider type fails validation."""
        doc = {
            "version": "v1",
            "capabilities": {
                "test": {
                    "description": "Test",
                    "providers": [
                        {
                            "type": "invalid",
                            "module_id": "test.mod",
                        }
                    ],
                }
            },
        }
        errors = list(validator.iter_errors(doc))
        assert len(errors) > 0

    def test_extra_properties_fail(self, validator: Draft7Validator):
        """Extra properties in capability fail validation."""
        doc = {
            "version": "v1",
            "capabilities": {
                "test": {
                    "description": "Test",
                    "unknown_field": "value",
                }
            },
        }
        errors = list(validator.iter_errors(doc))
        assert len(errors) > 0
