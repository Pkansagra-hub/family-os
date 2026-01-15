"""Tests for contract_compatibility_checker module.

Tests cover:
- Breaking change detection (field removal, type changes, required additions, enum contraction)
- SemVer validation (MAJOR/MINOR/PATCH enforcement)
- N/N+1 compatibility policy validation
- Report generation
- Git-based schema loading and change detection
- CLI functionality
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from k0.automation.contract_compatibility_checker import (
    ChangeType,
    CompatibilityCheckResult,
    SchemaChange,
    _get_changed_schema_files,
    _load_schema_from_git,
    check_compatibility,
    classify_change_severity,
    detect_changes,
    generate_compatibility_report,
    main,
    parse_semver,
    validate_version_bump,
)


class TestParseSemver:
    """Tests for parse_semver function."""

    def test_valid_semver(self):
        """Test parsing valid semantic versions."""
        assert parse_semver("1.0.0") == (1, 0, 0)
        assert parse_semver("2.5.3") == (2, 5, 3)
        assert parse_semver("0.0.1") == (0, 0, 1)

    def test_invalid_semver(self):
        """Test parsing invalid semantic versions."""
        with pytest.raises(ValueError, match="Invalid SemVer format"):
            parse_semver("1.0")
        with pytest.raises(ValueError, match="Invalid SemVer format"):
            parse_semver("v1.0.0")
        with pytest.raises(ValueError, match="Invalid SemVer format"):
            parse_semver("1.0.0.0")


class TestBreakingChangeDetection:
    """Tests for detect_changes function with breaking changes."""

    def test_field_removal(self):
        """Test detection of removed fields (BREAKING)."""
        old = {
            "properties": {
                "name": {"type": "string"},
                "email": {"type": "string"},
            }
        }
        new = {
            "properties": {
                "name": {"type": "string"},
            }
        }

        changes = detect_changes(old, new)

        breaking = [c for c in changes if c.change_type == ChangeType.BREAKING]
        assert len(breaking) == 1
        assert "/properties/email" in breaking[0].path
        assert "Field removed" in breaking[0].description

    def test_type_change(self):
        """Test detection of type changes (BREAKING)."""
        old = {"properties": {"count": {"type": "string"}}}
        new = {"properties": {"count": {"type": "integer"}}}

        changes = detect_changes(old, new)

        breaking = [c for c in changes if c.change_type == ChangeType.BREAKING]
        assert len(breaking) == 1
        assert "Type changed" in breaking[0].description

    def test_required_field_addition(self):
        """Test detection of fields becoming required (BREAKING)."""
        old = {
            "required": ["name"],
            "properties": {
                "name": {"type": "string"},
                "email": {"type": "string"},
            },
        }
        new = {
            "required": ["name", "email"],
            "properties": {
                "name": {"type": "string"},
                "email": {"type": "string"},
            },
        }

        changes = detect_changes(old, new)

        breaking = [c for c in changes if c.change_type == ChangeType.BREAKING]
        assert len(breaking) == 1
        assert "now required" in breaking[0].description

    def test_enum_value_removal(self):
        """Test detection of enum value removal (BREAKING)."""
        old = {
            "properties": {"status": {"type": "string", "enum": ["active", "inactive", "pending"]}}
        }
        new = {"properties": {"status": {"type": "string", "enum": ["active", "inactive"]}}}

        changes = detect_changes(old, new)

        breaking = [c for c in changes if c.change_type == ChangeType.BREAKING]
        assert len(breaking) == 1
        assert "Enum values removed" in breaking[0].description


class TestCompatibleChangeDetection:
    """Tests for detect_changes function with compatible changes."""

    def test_optional_field_addition(self):
        """Test detection of added optional fields (COMPATIBLE)."""
        old = {"properties": {"name": {"type": "string"}}}
        new = {"properties": {"name": {"type": "string"}, "description": {"type": "string"}}}

        changes = detect_changes(old, new)

        compatible = [c for c in changes if c.change_type == ChangeType.COMPATIBLE]
        assert len(compatible) == 1
        assert "/properties/description" in compatible[0].path

    def test_enum_value_addition(self):
        """Test detection of enum value addition (COMPATIBLE)."""
        old = {"properties": {"status": {"type": "string", "enum": ["active", "inactive"]}}}
        new = {
            "properties": {"status": {"type": "string", "enum": ["active", "inactive", "pending"]}}
        }

        changes = detect_changes(old, new)

        compatible = [c for c in changes if c.change_type == ChangeType.COMPATIBLE]
        assert len(compatible) == 1
        assert "Enum values added" in compatible[0].description

    def test_no_changes(self):
        """Test detection when schemas are identical."""
        schema = {"properties": {"name": {"type": "string"}}}

        changes = detect_changes(schema, schema)
        assert len(changes) == 0


class TestChangeClassification:
    """Tests for classify_change_severity function."""

    def test_classify_breaking(self):
        """Test classification of breaking changes."""
        changes = [
            SchemaChange(
                change_type=ChangeType.BREAKING,
                path="/properties/id",
                old_value="string",
                new_value=None,
                description="Field removed",
            )
        ]

        severity = classify_change_severity(changes)
        assert severity == ChangeType.BREAKING

    def test_classify_compatible(self):
        """Test classification of compatible changes."""
        changes = [
            SchemaChange(
                change_type=ChangeType.COMPATIBLE,
                path="/properties/description",
                old_value=None,
                new_value={"type": "string"},
                description="Optional field added",
            )
        ]

        severity = classify_change_severity(changes)
        assert severity == ChangeType.COMPATIBLE

    def test_classify_patch(self):
        """Test classification of patch-level changes."""
        changes = []

        severity = classify_change_severity(changes)
        assert severity == ChangeType.PATCH

    def test_breaking_overrides_compatible(self):
        """Test that breaking changes override compatible in classification."""
        changes = [
            SchemaChange(
                change_type=ChangeType.COMPATIBLE,
                path="/properties/description",
                old_value=None,
                new_value={"type": "string"},
                description="Optional field added",
            ),
            SchemaChange(
                change_type=ChangeType.BREAKING,
                path="/properties/id",
                old_value="string",
                new_value=None,
                description="Field removed",
            ),
        ]

        severity = classify_change_severity(changes)
        assert severity == ChangeType.BREAKING


class TestVersionBumpValidation:
    """Tests for validate_version_bump function."""

    def test_major_bump_for_breaking(self):
        """Test MAJOR version bump validates for breaking changes."""
        is_valid, msg = validate_version_bump("1.0.0", "2.0.0", ChangeType.BREAKING)
        assert is_valid is True
        assert "MAJOR" in msg

    def test_minor_bump_rejects_breaking(self):
        """Test MINOR version bump fails for breaking changes."""
        is_valid, msg = validate_version_bump("1.0.0", "1.1.0", ChangeType.BREAKING)
        assert is_valid is False
        assert "BREAKING changes require MAJOR" in msg

    def test_minor_bump_for_compatible(self):
        """Test MINOR version bump validates for compatible changes."""
        is_valid, msg = validate_version_bump("1.0.0", "1.1.0", ChangeType.COMPATIBLE)
        assert is_valid is True
        assert "MINOR" in msg

    def test_major_bump_for_compatible(self):
        """Test MAJOR version bump also validates for compatible changes (conservative)."""
        is_valid, msg = validate_version_bump("1.0.0", "2.0.0", ChangeType.COMPATIBLE)
        assert is_valid is True

    def test_patch_bump_for_patch(self):
        """Test PATCH version bump validates for patch-level changes."""
        is_valid, msg = validate_version_bump("1.0.0", "1.0.1", ChangeType.PATCH)
        assert is_valid is True
        assert "PATCH" in msg

    def test_minor_bump_rejects_patch(self):
        """Test MINOR version bump fails for patch-only changes."""
        is_valid, msg = validate_version_bump("1.0.0", "1.1.0", ChangeType.PATCH)
        assert is_valid is False

    def test_invalid_version_format(self):
        """Test invalid version format raises error."""
        is_valid, msg = validate_version_bump("1.0", "2.0", ChangeType.BREAKING)
        assert is_valid is False
        assert "Invalid SemVer format" in msg


class TestReportGeneration:
    """Tests for generate_compatibility_report function."""

    def test_no_changes_report(self):
        """Test report generation with no changes."""
        report, success = generate_compatibility_report([])

        assert success is True
        assert "No contract changes detected" in report
        assert "✅ PASS" in report

    def test_breaking_changes_report(self):
        """Test report generation with breaking changes."""
        result = CompatibilityCheckResult(
            schema_name="envelope",
            old_version="1.0.0",
            new_version="1.1.0",
            changes=[
                SchemaChange(
                    change_type=ChangeType.BREAKING,
                    path="/properties/tenant_id",
                    old_value="string",
                    new_value=None,
                    description="Field removed: tenant_id",
                )
            ],
            is_breaking=True,
            semver_valid=False,
            issues=["SemVer violation: BREAKING changes require MAJOR version bump"],
        )

        report, success = generate_compatibility_report([result], fail_on_breaking=True)

        assert success is False
        assert "❌ FAIL" in report
        assert "envelope" in report
        assert "SemVer violation" in report
        assert "🔴" in report  # Breaking change icon

    def test_compatible_changes_report(self):
        """Test report generation with compatible changes."""
        result = CompatibilityCheckResult(
            schema_name="query.recall.request",
            old_version="1.0.0",
            new_version="1.1.0",
            changes=[
                SchemaChange(
                    change_type=ChangeType.COMPATIBLE,
                    path="/properties/timeout_ms",
                    old_value=None,
                    new_value={"type": "integer"},
                    description="Optional field added: timeout_ms",
                )
            ],
            is_breaking=False,
            semver_valid=True,
            issues=[],
        )

        report, success = generate_compatibility_report([result])

        assert success is True
        assert "✅ PASS" in report
        assert "query.recall.request" in report
        assert "1.0.0 → 1.1.0" in report
        assert "🟡" in report  # Compatible change icon

    def test_recommendations_included(self):
        """Test that report includes remediation recommendations."""
        result = CompatibilityCheckResult(
            schema_name="envelope",
            old_version="1.0.0",
            new_version="1.1.0",
            changes=[
                SchemaChange(
                    change_type=ChangeType.BREAKING,
                    path="/properties/tenant_id",
                    old_value="string",
                    new_value=None,
                    description="Field removed",
                )
            ],
            is_breaking=True,
            semver_valid=False,
            issues=["SemVer violation: BREAKING changes require MAJOR version bump"],
        )

        report, success = generate_compatibility_report([result])

        assert "Recommendations" in report
        assert "2.0.0" in report  # Recommended version
        assert "MAJOR bump" in report


class TestIntegrationWithRealSchemas:
    """Integration tests using realistic schema scenarios."""

    def test_envelope_schema_backward_compat(self):
        """Test typical evolution of envelope schema."""
        old_envelope = {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
            "required": ["tenant_id", "space_id", "topic"],
            "properties": {
                "tenant_id": {"type": "string"},
                "space_id": {"type": "string"},
                "topic": {"type": "string"},
                "schema_version": {"type": "string"},
            },
        }

        # Add optional field (compatible change)
        new_envelope = {
            **old_envelope,
            "properties": {**old_envelope["properties"], "metadata": {"type": "object"}},
        }

        changes = detect_changes(old_envelope, new_envelope)
        severity = classify_change_severity(changes)

        assert severity == ChangeType.COMPATIBLE
        is_valid, _ = validate_version_bump("1.0.0", "1.1.0", severity)
        assert is_valid is True

    def test_envelope_schema_breaking_change(self):
        """Test breaking change in envelope schema."""
        old_envelope = {
            "type": "object",
            "required": ["tenant_id", "space_id", "topic"],
            "properties": {
                "tenant_id": {"type": "string"},
                "space_id": {"type": "string"},
                "topic": {"type": "string"},
            },
        }

        # Remove required field (breaking change)
        new_envelope = {
            "type": "object",
            "required": ["topic"],
            "properties": {
                "topic": {"type": "string"},
            },
        }

        changes = detect_changes(old_envelope, new_envelope)
        severity = classify_change_severity(changes)

        assert severity == ChangeType.BREAKING
        is_valid, _ = validate_version_bump("1.0.0", "2.0.0", severity)
        assert is_valid is True
        is_valid, _ = validate_version_bump("1.0.0", "1.1.0", severity)
        assert is_valid is False

    def test_error_schema_type_migration(self):
        """Test error schema evolving with type change."""
        old_error = {
            "type": "object",
            "properties": {
                "code": {"type": "integer"},
                "message": {"type": "string"},
            },
        }

        # Change code type (breaking)
        new_error = {
            "type": "object",
            "properties": {
                "code": {"type": "string"},  # Changed!
                "message": {"type": "string"},
            },
        }

        changes = detect_changes(old_error, new_error)
        severity = classify_change_severity(changes)

        assert severity == ChangeType.BREAKING


class TestLoadSchemaFromGit:
    """Tests for _load_schema_from_git function."""

    @patch("k0.automation.contract_compatibility_checker.subprocess.run")
    @patch("k0.automation.contract_compatibility_checker.REPO_ROOT", Path("/tmp/repo"))
    def test_load_json_schema_success(self, mock_run):
        """Test successful loading of JSON schema from git."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = '{"type": "object", "properties": {"name": {"type": "string"}}}'
        mock_run.return_value = mock_result

        result = _load_schema_from_git("main", "schemas/test.json")

        assert result == {"type": "object", "properties": {"name": {"type": "string"}}}
        mock_run.assert_called_once_with(
            ["git", "show", "main:schemas/test.json"],
            cwd=Path("/tmp/repo"),
            capture_output=True,
            text=True,
            timeout=5,
        )

    @patch("k0.automation.contract_compatibility_checker.subprocess.run")
    @patch("k0.automation.contract_compatibility_checker.REPO_ROOT", Path("/tmp/repo"))
    def test_load_yaml_schema_success(self, mock_run):
        """Test successful loading of YAML schema from git."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "type: object\nproperties:\n  name:\n    type: string\n"
        mock_run.return_value = mock_result

        result = _load_schema_from_git("v1.0.0", "schemas/test.yaml")

        assert result == {"type": "object", "properties": {"name": {"type": "string"}}}

    @patch("k0.automation.contract_compatibility_checker.subprocess.run")
    def test_load_schema_file_not_found(self, mock_run):
        """Test loading schema when file doesn't exist in git."""
        mock_result = MagicMock()
        mock_result.returncode = 1  # File not found
        mock_run.return_value = mock_result

        result = _load_schema_from_git("main", "schemas/missing.json")

        assert result is None

    @patch("k0.automation.contract_compatibility_checker.subprocess.run")
    def test_load_schema_subprocess_error(self, mock_run):
        """Test loading schema when subprocess fails."""
        mock_run.side_effect = subprocess.CalledProcessError(1, "git")

        result = _load_schema_from_git("main", "schemas/test.json")

        assert result is None

    @patch("k0.automation.contract_compatibility_checker.subprocess.run")
    def test_load_schema_timeout(self, mock_run):
        """Test loading schema when git command times out."""
        mock_run.side_effect = subprocess.TimeoutExpired("git", 5)

        result = _load_schema_from_git("main", "schemas/test.json")

        assert result is None


class TestGetChangedSchemaFiles:
    """Tests for _get_changed_schema_files function."""

    @patch("k0.automation.contract_compatibility_checker.subprocess.run")
    @patch("k0.automation.contract_compatibility_checker.REPO_ROOT", Path("/tmp/repo"))
    def test_get_changed_files_success(self, mock_run):
        """Test successful retrieval of changed schema files."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "k0/contracts/jsonschema/envelope.schema.json\nk0/contracts/jsonschema/query.schema.json\n"
        mock_run.return_value = mock_result

        result = _get_changed_schema_files("origin/main", "HEAD", Path("k0/contracts/jsonschema"))

        assert result == [
            "k0/contracts/jsonschema/envelope.schema.json",
            "k0/contracts/jsonschema/query.schema.json",
        ]
        mock_run.assert_called_once()

    @patch("k0.automation.contract_compatibility_checker.subprocess.run")
    def test_get_changed_files_no_changes(self, mock_run):
        """Test when no schema files have changed."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_run.return_value = mock_result

        result = _get_changed_schema_files("origin/main", "HEAD", Path("k0/contracts/jsonschema"))

        assert result == []

    @patch("k0.automation.contract_compatibility_checker.subprocess.run")
    def test_get_changed_files_git_error(self, mock_run):
        """Test when git command fails."""
        mock_run.side_effect = subprocess.CalledProcessError(1, "git")

        result = _get_changed_schema_files("origin/main", "HEAD", Path("k0/contracts/jsonschema"))

        assert result == []

    @patch("k0.automation.contract_compatibility_checker.subprocess.run")
    def test_get_changed_files_timeout(self, mock_run):
        """Test when git command times out."""
        mock_run.side_effect = subprocess.TimeoutExpired("git", 10)

        result = _get_changed_schema_files("origin/main", "HEAD", Path("k0/contracts/jsonschema"))

        assert result == []


class TestCheckCompatibility:
    """Tests for check_compatibility function."""

    @patch("k0.automation.contract_compatibility_checker._get_changed_schema_files")
    @patch("k0.automation.contract_compatibility_checker._load_schema_from_git")
    @patch("k0.automation.contract_compatibility_checker.detect_changes")
    @patch("k0.automation.contract_compatibility_checker.classify_change_severity")
    @patch("k0.automation.contract_compatibility_checker.validate_version_bump")
    @patch("pathlib.Path.relative_to")
    def test_check_compatibility_with_breaking_changes(
        self,
        mock_relative_to,
        mock_validate,
        mock_classify,
        mock_detect,
        mock_load,
        mock_get_changed,
    ):
        """Test compatibility check with breaking changes detected."""
        # Setup mocks
        mock_get_changed.return_value = ["k0/contracts/jsonschema/envelope.schema.json"]
        mock_relative_to.return_value = Path("k0/contracts/jsonschema/envelope.schema.json")
        mock_load.side_effect = [
            {"version": "1.0.0", "$id": "envelope/v1.0.0"},  # old schema
            {"version": "1.1.0", "$id": "envelope/v1.1.0"},  # new schema
        ]
        mock_detect.return_value = [
            SchemaChange(
                change_type=ChangeType.BREAKING,
                path="/properties/tenant_id",
                old_value="string",
                new_value=None,
                description="Field removed",
            )
        ]
        mock_classify.return_value = ChangeType.BREAKING
        mock_validate.return_value = (False, "BREAKING changes require MAJOR version bump")

        results = check_compatibility("origin/main", "HEAD")

        assert len(results) == 1
        result = results[0]
        assert result.schema_name == "envelope.schema"
        assert result.old_version == "1.0.0"
        assert result.new_version == "1.1.0"
        assert result.is_breaking is True
        assert result.semver_valid is False
        assert len(result.issues) == 1

    @patch("k0.automation.contract_compatibility_checker._get_changed_schema_files")
    @patch("k0.automation.contract_compatibility_checker._load_schema_from_git")
    @patch("pathlib.Path.relative_to")
    def test_check_compatibility_no_changes(self, mock_relative_to, mock_load, mock_get_changed):
        """Test compatibility check when schemas are identical."""
        mock_get_changed.return_value = ["k0/contracts/jsonschema/envelope.schema.json"]
        mock_relative_to.return_value = Path("k0/contracts/jsonschema/envelope.schema.json")
        schema = {"version": "1.0.0", "type": "object"}
        mock_load.side_effect = [schema, schema]  # Same schema

        results = check_compatibility("origin/main", "HEAD")

        assert len(results) == 0  # No changes detected

    @patch("k0.automation.contract_compatibility_checker._get_changed_schema_files")
    @patch("k0.automation.contract_compatibility_checker._load_schema_from_git")
    @patch("pathlib.Path.relative_to")
    def test_check_compatibility_schema_not_found(
        self, mock_relative_to, mock_load, mock_get_changed
    ):
        """Test compatibility check when old schema doesn't exist."""
        mock_get_changed.return_value = ["k0/contracts/jsonschema/envelope.schema.json"]
        mock_relative_to.return_value = Path("k0/contracts/jsonschema/envelope.schema.json")
        mock_load.side_effect = [None, {"version": "1.0.0"}]  # Old schema not found

        results = check_compatibility("origin/main", "HEAD")

        assert len(results) == 0  # Skipped because old schema is None

    @patch("k0.automation.contract_compatibility_checker._get_changed_schema_files")
    @patch("k0.automation.contract_compatibility_checker._load_schema_from_git")
    @patch("k0.automation.contract_compatibility_checker.detect_changes")
    @patch("k0.automation.contract_compatibility_checker.classify_change_severity")
    @patch("k0.automation.contract_compatibility_checker.validate_version_bump")
    @patch("pathlib.Path.relative_to")
    def test_check_compatibility_version_from_id(
        self,
        mock_relative_to,
        mock_validate,
        mock_classify,
        mock_detect,
        mock_load,
        mock_get_changed,
    ):
        """Test compatibility check with version extracted from $id field."""
        # Setup mocks
        mock_get_changed.return_value = ["k0/contracts/jsonschema/envelope.schema.json"]
        mock_relative_to.return_value = Path("k0/contracts/jsonschema/envelope.schema.json")
        mock_load.side_effect = [
            {"$id": "envelope/v1.0.0"},  # old schema with version in $id
            {"$id": "envelope/v2.0.0"},  # new schema with version in $id
        ]
        mock_detect.return_value = [
            SchemaChange(
                change_type=ChangeType.BREAKING,
                path="/properties/tenant_id",
                old_value="string",
                new_value=None,
                description="Field removed",
            )
        ]
        mock_classify.return_value = ChangeType.BREAKING
        mock_validate.return_value = (True, "MAJOR version bump matches breaking changes")

        results = check_compatibility("origin/main", "HEAD")

        assert len(results) == 1
        result = results[0]
        assert result.old_version == "1.0.0"
        assert result.new_version == "2.0.0"


class TestMainFunction:
    """Tests for main function."""

    @patch("k0.automation.contract_compatibility_checker.check_compatibility")
    @patch("k0.automation.contract_compatibility_checker.generate_compatibility_report")
    def test_main_git_mode_success(self, mock_report, mock_check):
        """Test main function in git mode with success."""
        mock_check.return_value = []
        mock_report.return_value = ("No changes report", True)

        exit_code = main(["--base-ref", "origin/main", "--head-ref", "HEAD"])

        assert exit_code == 0
        # Should be called with DEFAULT_SCHEMA_DIR, not None
        mock_check.assert_called_once()
        args, kwargs = mock_check.call_args
        assert args[0] == "origin/main"
        assert args[1] == "HEAD"
        assert str(args[2]).endswith("k0\\contracts\\jsonschema")  # DEFAULT_SCHEMA_DIR
        mock_report.assert_called_once()

    @patch("k0.automation.contract_compatibility_checker.check_compatibility")
    @patch("k0.automation.contract_compatibility_checker.generate_compatibility_report")
    def test_main_git_mode_failure(self, mock_report, mock_check):
        """Test main function in git mode with failure."""
        mock_check.return_value = []
        mock_report.return_value = ("Breaking changes report", False)

        exit_code = main(["--base-ref", "origin/main", "--head-ref", "HEAD", "--fail-on-breaking"])

        assert exit_code == 1

    @patch("k0.automation.contract_compatibility_checker.detect_changes")
    @patch("k0.automation.contract_compatibility_checker.classify_change_severity")
    @patch("k0.automation.contract_compatibility_checker.validate_version_bump")
    def test_main_single_file_mode_success(self, mock_validate, mock_classify, mock_detect):
        """Test main function in single file mode with success."""
        mock_detect.return_value = []
        mock_classify.return_value = ChangeType.PATCH
        mock_validate.return_value = (True, "Valid patch bump")

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"type": "object"}, f)
            temp_file = Path(f.name)

        try:
            exit_code = main(
                [
                    "--schema-file",
                    str(temp_file),
                    "--old-version",
                    "1.0.0",
                    "--new-version",
                    "1.0.1",
                ]
            )

            assert exit_code == 0
        finally:
            temp_file.unlink()

    @patch("k0.automation.contract_compatibility_checker.detect_changes")
    @patch("k0.automation.contract_compatibility_checker.classify_change_severity")
    @patch("k0.automation.contract_compatibility_checker.validate_version_bump")
    def test_main_single_file_mode_failure(self, mock_validate, mock_classify, mock_detect):
        """Test main function in single file mode with failure."""
        mock_detect.return_value = []
        mock_classify.return_value = ChangeType.BREAKING
        mock_validate.return_value = (False, "Invalid version bump")

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"type": "object"}, f)
            temp_file = Path(f.name)

        try:
            exit_code = main(
                [
                    "--schema-file",
                    str(temp_file),
                    "--old-version",
                    "1.0.0",
                    "--new-version",
                    "1.1.0",
                ]
            )

            assert exit_code == 1
        finally:
            temp_file.unlink()

    def test_main_single_file_missing_versions(self):
        """Test main function with single file but missing version arguments."""
        exit_code = main(["--schema-file", "test.json"])

        assert exit_code == 1

    def test_main_single_file_not_found(self):
        """Test main function with non-existent schema file."""
        exit_code = main(
            [
                "--schema-file",
                "nonexistent.json",
                "--old-version",
                "1.0.0",
                "--new-version",
                "1.1.0",
            ]
        )

        assert exit_code == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
