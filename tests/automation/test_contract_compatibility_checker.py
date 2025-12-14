"""Tests for contract_compatibility_checker module.

Tests cover:
- Breaking change detection (field removal, type changes, required additions, enum contraction)
- SemVer validation (MAJOR/MINOR/PATCH enforcement)
- N/N+1 compatibility policy validation
- Report generation
"""

from __future__ import annotations

import pytest

from k0.automation.contract_compatibility_checker import (
    ChangeType,
    CompatibilityCheckResult,
    SchemaChange,
    classify_change_severity,
    detect_changes,
    generate_compatibility_report,
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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
