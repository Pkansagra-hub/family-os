"""Comprehensive tests for enhanced lint_schemas with orphan detection and cross-reference validation."""

import json
import tempfile
from pathlib import Path

import pytest
import yaml

from k0.automation.lint_schemas import (
    ValidationMessage,
    detect_orphaned_schemas,
    format_report,
    group_messages_by_severity,
    lint_contracts,
    validate_document_contract,
    validate_json_schemas,
)


@pytest.fixture
def temp_contracts_dir():
    """Create a temporary contracts directory structure."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)

        # Create jsonschema directory
        schema_dir = tmppath / "jsonschema"
        schema_dir.mkdir()

        yield tmppath, schema_dir


class TestValidationMessage:
    """Tests for ValidationMessage class."""

    def test_validation_message_creation(self):
        msg = ValidationMessage(
            severity="ERROR",
            message="Test error",
            file="test.json",
            line=42,
            fix="Fix this",
        )
        assert msg.severity == "ERROR"
        assert msg.message == "Test error"
        assert msg.file == "test.json"
        assert msg.line == 42
        assert msg.fix == "Fix this"

    def test_validation_message_str_with_all_fields(self):
        msg = ValidationMessage(
            severity="ERROR",
            message="Test error",
            file="test.json",
            line=42,
            fix="Fix this",
        )
        msg_str = str(msg)
        assert "[ERROR] Test error" in msg_str
        assert "File: test.json:42" in msg_str
        assert "Fix: Fix this" in msg_str

    def test_validation_message_str_minimal(self):
        msg = ValidationMessage(severity="INFO", message="Test info")
        msg_str = str(msg)
        assert "[INFO] Test info" in msg_str
        assert "File:" not in msg_str
        assert "Fix:" not in msg_str

    def test_validation_message_equality(self):
        msg1 = ValidationMessage("ERROR", "Test", file="test.json")
        msg2 = ValidationMessage("ERROR", "Test", file="test.json")
        msg3 = ValidationMessage("WARNING", "Test", file="test.json")

        assert msg1 == msg2
        assert msg1 != msg3

    def test_validation_message_inequality_with_non_message(self):
        msg = ValidationMessage("ERROR", "Test")
        assert msg != "not a message"
        assert msg != 42


class TestGroupMessagesBySeverity:
    """Tests for grouping messages by severity."""

    def test_empty_messages(self):
        result = group_messages_by_severity([])
        assert result == {"ERROR": [], "WARNING": [], "INFO": []}

    def test_single_severity(self):
        messages = [
            ValidationMessage("ERROR", "Error 1"),
            ValidationMessage("ERROR", "Error 2"),
        ]
        result = group_messages_by_severity(messages)
        assert len(result["ERROR"]) == 2
        assert len(result["WARNING"]) == 0
        assert len(result["INFO"]) == 0

    def test_mixed_severities(self):
        messages = [
            ValidationMessage("ERROR", "Error 1"),
            ValidationMessage("WARNING", "Warning 1"),
            ValidationMessage("INFO", "Info 1"),
            ValidationMessage("ERROR", "Error 2"),
        ]
        result = group_messages_by_severity(messages)
        assert len(result["ERROR"]) == 2
        assert len(result["WARNING"]) == 1
        assert len(result["INFO"]) == 1

    def test_unknown_severity(self):
        messages = [
            ValidationMessage("UNKNOWN", "Unknown severity"),
        ]
        result = group_messages_by_severity(messages)
        # Unknown severities should go to INFO
        assert len(result["INFO"]) == 1


class TestFormatReport:
    """Tests for report formatting."""

    def test_empty_report(self):
        report = format_report([])
        assert "✅" in report
        assert "successfully" in report

    def test_error_only_report(self):
        messages = [
            ValidationMessage("ERROR", "Error 1", file="test.json"),
        ]
        report = format_report(messages)
        assert "Errors: 1" in report
        assert "ERRORS:" in report
        assert "Error 1" in report

    def test_mixed_severity_report(self):
        messages = [
            ValidationMessage("ERROR", "Error 1"),
            ValidationMessage("WARNING", "Warning 1"),
            ValidationMessage("INFO", "Info 1"),
        ]
        report = format_report(messages)
        assert "Errors: 1" in report
        assert "Warnings: 1" in report
        assert "Info: 1" in report
        assert "ERRORS:" in report
        assert "WARNINGS:" in report
        assert "INFOS:" in report


class TestValidateJsonSchemas:
    """Tests for JSON schema validation."""

    def test_valid_schema(self, temp_contracts_dir):
        tmppath, schema_dir = temp_contracts_dir

        # Create a valid JSON schema
        schema = {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
            "properties": {"name": {"type": "string"}},
        }
        (schema_dir / "valid.json").write_text(json.dumps(schema))

        messages = validate_json_schemas(schema_dir)
        assert len(messages) == 0

    def test_invalid_json_syntax(self, temp_contracts_dir):
        tmppath, schema_dir = temp_contracts_dir

        # Create file with invalid JSON
        (schema_dir / "invalid.json").write_text("{invalid json}")

        messages = validate_json_schemas(schema_dir)
        assert len(messages) == 1
        assert messages[0].severity == "ERROR"
        assert "invalid.json" in messages[0].message

    def test_invalid_schema_structure(self, temp_contracts_dir):
        tmppath, schema_dir = temp_contracts_dir

        # Create valid JSON but invalid schema
        invalid_schema = {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "not_a_valid_type",
        }
        (schema_dir / "invalid_schema.json").write_text(json.dumps(invalid_schema))

        messages = validate_json_schemas(schema_dir)
        assert len(messages) == 1
        assert messages[0].severity == "ERROR"
        assert "invalid_schema.json" in messages[0].message

    def test_multiple_schemas(self, temp_contracts_dir):
        tmppath, schema_dir = temp_contracts_dir

        # Create multiple valid schemas
        for i in range(3):
            schema = {
                "$schema": "http://json-schema.org/draft-07/schema#",
                "type": "object",
                "properties": {"id": {"type": "integer"}},
            }
            (schema_dir / f"schema{i}.json").write_text(json.dumps(schema))

        messages = validate_json_schemas(schema_dir)
        assert len(messages) == 0


class TestValidateDocumentContract:
    """Tests for document contract validation."""

    def test_valid_yaml_document(self, temp_contracts_dir):
        tmppath, _ = temp_contracts_dir

        # Create a simple valid YAML
        doc = {"openapi": "3.1.0", "info": {"title": "Test", "version": "1.0.0"}}
        yaml_path = tmppath / "openapi.yaml"
        yaml_path.write_text(yaml.dump(doc))

        messages = validate_document_contract(yaml_path)
        assert len(messages) == 0

    def test_invalid_yaml_syntax(self, temp_contracts_dir):
        tmppath, _ = temp_contracts_dir

        # Create file with invalid YAML
        yaml_path = tmppath / "invalid.yaml"
        yaml_path.write_text("invalid:\n  - yaml\n    syntax:\nerror:")

        messages = validate_document_contract(yaml_path)
        assert len(messages) == 1
        assert messages[0].severity == "ERROR"

    def test_missing_internal_reference(self, temp_contracts_dir):
        tmppath, _ = temp_contracts_dir

        # Create YAML with broken internal reference
        doc = {
            "openapi": "3.1.0",
            "components": {"schemas": {"Test": {"$ref": "#/components/schemas/NonExistent"}}},
        }
        yaml_path = tmppath / "openapi.yaml"
        yaml_path.write_text(yaml.dump(doc))

        messages = validate_document_contract(yaml_path)
        assert len(messages) == 1
        assert messages[0].severity == "ERROR"
        assert "NonExistent" in messages[0].message or "resolve" in messages[0].message


class TestDetectOrphanedSchemas:
    """Tests for orphan schema detection."""

    def test_no_orphans(self, temp_contracts_dir):
        tmppath, schema_dir = temp_contracts_dir

        # Create schemas
        schema1 = {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
        }
        (schema_dir / "schema1.json").write_text(json.dumps(schema1))
        (schema_dir / "schema2.json").write_text(json.dumps(schema1))

        # Create OpenAPI that references both
        openapi = {
            "openapi": "3.1.0",
            "components": {
                "schemas": {
                    "Schema1": {"$ref": "./jsonschema/schema1.json"},
                    "Schema2": {"$ref": "./jsonschema/schema2.json"},
                }
            },
        }
        openapi_path = tmppath / "openapi.yaml"
        openapi_path.write_text(yaml.dump(openapi))

        # Create empty AsyncAPI
        asyncapi_path = tmppath / "asyncapi.yaml"
        asyncapi_path.write_text(yaml.dump({"asyncapi": "2.6.0"}))

        messages = detect_orphaned_schemas(schema_dir, openapi_path, asyncapi_path)
        assert len(messages) == 0

    def test_with_orphans(self, temp_contracts_dir):
        tmppath, schema_dir = temp_contracts_dir

        # Create schemas
        schema1 = {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
        }
        (schema_dir / "schema1.json").write_text(json.dumps(schema1))
        (schema_dir / "schema2.json").write_text(json.dumps(schema1))
        (schema_dir / "orphan.json").write_text(json.dumps(schema1))

        # Create OpenAPI that references only schema1 and schema2
        openapi = {
            "openapi": "3.1.0",
            "components": {
                "schemas": {
                    "Schema1": {"$ref": "./jsonschema/schema1.json"},
                    "Schema2": {"$ref": "./jsonschema/schema2.json"},
                }
            },
        }
        openapi_path = tmppath / "openapi.yaml"
        openapi_path.write_text(yaml.dump(openapi))

        # Create empty AsyncAPI
        asyncapi_path = tmppath / "asyncapi.yaml"
        asyncapi_path.write_text(yaml.dump({"asyncapi": "2.6.0"}))

        messages = detect_orphaned_schemas(schema_dir, openapi_path, asyncapi_path)
        assert len(messages) == 1
        assert messages[0].severity == "WARNING"
        assert "orphan" in messages[0].message.lower()
        assert "orphan.json" in messages[0].message

    def test_all_orphans(self, temp_contracts_dir):
        tmppath, schema_dir = temp_contracts_dir

        # Create schemas
        schema1 = {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
        }
        (schema_dir / "schema1.json").write_text(json.dumps(schema1))
        (schema_dir / "schema2.json").write_text(json.dumps(schema1))

        # Create empty OpenAPI and AsyncAPI
        openapi_path = tmppath / "openapi.yaml"
        openapi_path.write_text(yaml.dump({"openapi": "3.1.0"}))

        asyncapi_path = tmppath / "asyncapi.yaml"
        asyncapi_path.write_text(yaml.dump({"asyncapi": "2.6.0"}))

        messages = detect_orphaned_schemas(schema_dir, openapi_path, asyncapi_path)
        assert len(messages) == 2
        assert all(m.severity == "WARNING" for m in messages)
        assert all("orphan" in m.message.lower() for m in messages)


class TestLintContractsIntegration:
    """Integration tests for the main lint_contracts function."""

    def test_valid_contracts(self, temp_contracts_dir):
        tmppath, schema_dir = temp_contracts_dir

        # Create valid schema
        schema = {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
            "properties": {"id": {"type": "string"}},
        }
        (schema_dir / "test.json").write_text(json.dumps(schema))

        # Create valid OpenAPI referencing the schema
        openapi = {
            "openapi": "3.1.0",
            "components": {"schemas": {"Test": {"$ref": "./jsonschema/test.json"}}},
        }
        openapi_path = tmppath / "openapi.yaml"
        openapi_path.write_text(yaml.dump(openapi))

        # Create empty AsyncAPI
        asyncapi_path = tmppath / "asyncapi.yaml"
        asyncapi_path.write_text(yaml.dump({"asyncapi": "2.6.0"}))

        messages = lint_contracts(
            schema_dir=schema_dir,
            openapi_path=openapi_path,
            asyncapi_path=asyncapi_path,
            check_orphans=True,
        )
        assert len(messages) == 0

    def test_with_errors_and_warnings(self, temp_contracts_dir):
        tmppath, schema_dir = temp_contracts_dir

        # Create valid schema
        schema = {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
        }
        (schema_dir / "used.json").write_text(json.dumps(schema))
        (schema_dir / "orphan.json").write_text(json.dumps(schema))

        # Create OpenAPI with broken and valid references
        openapi = {
            "openapi": "3.1.0",
            "components": {
                "schemas": {
                    "Good": {"$ref": "./jsonschema/used.json"},
                    "Bad": {"$ref": "#/components/schemas/NonExistent"},
                }
            },
        }
        openapi_path = tmppath / "openapi.yaml"
        openapi_path.write_text(yaml.dump(openapi))

        # Create empty AsyncAPI
        asyncapi_path = tmppath / "asyncapi.yaml"
        asyncapi_path.write_text(yaml.dump({"asyncapi": "2.6.0"}))

        messages = lint_contracts(
            schema_dir=schema_dir,
            openapi_path=openapi_path,
            asyncapi_path=asyncapi_path,
            check_orphans=True,
        )

        # Should have at least error for broken ref and warning for orphan
        errors = [m for m in messages if m.severity == "ERROR"]
        warnings = [m for m in messages if m.severity == "WARNING"]

        assert len(errors) >= 1  # Broken reference
        assert len(warnings) >= 1  # Orphan schema

    def test_orphan_check_can_be_disabled(self, temp_contracts_dir):
        tmppath, schema_dir = temp_contracts_dir

        # Create valid schema and orphaned schema
        schema = {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
        }
        (schema_dir / "used.json").write_text(json.dumps(schema))
        (schema_dir / "orphan.json").write_text(json.dumps(schema))

        # Create OpenAPI referencing only used
        openapi = {
            "openapi": "3.1.0",
            "components": {"schemas": {"Used": {"$ref": "./jsonschema/used.json"}}},
        }
        openapi_path = tmppath / "openapi.yaml"
        openapi_path.write_text(yaml.dump(openapi))

        asyncapi_path = tmppath / "asyncapi.yaml"
        asyncapi_path.write_text(yaml.dump({"asyncapi": "2.6.0"}))

        # With check_orphans=False, should not warn about orphan
        messages = lint_contracts(
            schema_dir=schema_dir,
            openapi_path=openapi_path,
            asyncapi_path=asyncapi_path,
            check_orphans=False,
        )
        assert len(messages) == 0

        # With check_orphans=True, should warn about orphan
        messages = lint_contracts(
            schema_dir=schema_dir,
            openapi_path=openapi_path,
            asyncapi_path=asyncapi_path,
            check_orphans=True,
        )
        assert any("orphan" in m.message.lower() for m in messages)
