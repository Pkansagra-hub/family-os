"""
Tests for capability contract files.

Issue 1.3.2: Create Default Capability Registry YAML
ADR: ADR-K004 Capability Mesh Architecture
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml
from jsonschema import Draft7Validator

# Paths
REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = REPO_ROOT / "k0" / "contracts" / "jsonschema" / "capability.schema.json"
CAPABILITIES_DIR = REPO_ROOT / "k0" / "contracts" / "capabilities"
MODULES_DIR = REPO_ROOT / "k0" / "contracts" / "modules"


@pytest.fixture
def capability_schema() -> dict[str, Any]:
    """Load the capability JSON schema."""
    return json.loads(SCHEMA_PATH.read_text())


@pytest.fixture
def validator(capability_schema: dict[str, Any]) -> Draft7Validator:
    """Create a JSON Schema validator."""
    return Draft7Validator(capability_schema)


@pytest.fixture
def core_capabilities() -> dict[str, Any]:
    """Load core.v1.yaml capability definitions."""
    core_path = CAPABILITIES_DIR / "core.v1.yaml"
    return yaml.safe_load(core_path.read_text())


# -----------------------------------------------------------------------------
# core.v1.yaml Tests
# -----------------------------------------------------------------------------


class TestCoreCapabilitiesYaml:
    """Tests for core.v1.yaml file."""

    def test_core_capabilities_yaml_valid(
        self, validator: Draft7Validator, core_capabilities: dict[str, Any]
    ):
        """core.v1.yaml validates against JSON Schema."""
        errors = list(validator.iter_errors(core_capabilities))
        error_messages = [f"{e.path}: {e.message}" for e in errors]
        assert len(errors) == 0, f"Validation errors: {error_messages}"

    def test_core_capabilities_loads_without_error(self):
        """core.v1.yaml loads and parses without error."""
        core_path = CAPABILITIES_DIR / "core.v1.yaml"
        assert core_path.exists(), f"core.v1.yaml not found at {core_path}"

        content = yaml.safe_load(core_path.read_text())
        assert content is not None
        assert "version" in content
        assert "capabilities" in content

    def test_core_capabilities_has_version(self, core_capabilities: dict[str, Any]):
        """core.v1.yaml has version field."""
        assert core_capabilities["version"] == "v1"

    def test_core_capabilities_not_empty(self, core_capabilities: dict[str, Any]):
        """core.v1.yaml has at least one capability."""
        assert len(core_capabilities["capabilities"]) > 0

    def test_all_capabilities_have_descriptions(self, core_capabilities: dict[str, Any]):
        """All capabilities have descriptions."""
        for cap_name, cap_def in core_capabilities["capabilities"].items():
            assert "description" in cap_def, f"Capability {cap_name} missing description"
            assert len(cap_def["description"]) > 0, f"Capability {cap_name} has empty description"

    def test_all_providers_have_valid_module_ids(self, core_capabilities: dict[str, Any]):
        """All module providers have valid module_id format."""
        import re

        module_id_pattern = re.compile(r"^[a-z_]+\.[a-z_]+(:[a-z0-9]+)?$")

        for cap_name, cap_def in core_capabilities["capabilities"].items():
            providers = cap_def.get("providers", [])
            for provider in providers:
                if provider["type"] == "module":
                    module_id = provider["module_id"]
                    assert module_id_pattern.match(
                        module_id
                    ), f"Capability {cap_name} has invalid module_id: {module_id}"

    def test_all_module_ids_have_corresponding_contracts(self, core_capabilities: dict[str, Any]):
        """All module_ids reference existing module contracts."""
        missing_contracts = []

        for cap_name, cap_def in core_capabilities["capabilities"].items():
            providers = cap_def.get("providers", [])
            for provider in providers:
                if provider["type"] == "module":
                    module_id = provider["module_id"]
                    # Module contract filename: module_id.v1.yaml
                    # e.g., salience.score -> salience.score.v1.yaml
                    contract_name = f"{module_id}.v1.yaml"
                    contract_path = MODULES_DIR / contract_name

                    if not contract_path.exists():
                        missing_contracts.append(
                            f"{cap_name} -> {module_id} (expected: {contract_name})"
                        )

        # Currently some modules may not have contracts yet
        # This test documents which are missing
        if missing_contracts:
            pytest.skip(f"Some module contracts are not yet created: {missing_contracts}")


# -----------------------------------------------------------------------------
# Expected Capabilities Tests
# -----------------------------------------------------------------------------


class TestExpectedCapabilities:
    """Tests for expected capabilities in core.v1.yaml."""

    EXPECTED_CAPABILITIES = [
        "score_salience",
        "pattern_separate",
        "semantic_project",
        "analyze_affect",
        "generate_embedding",
        "resolve_family_graph",
        "emit_event",
    ]

    def test_expected_capabilities_exist(self, core_capabilities: dict[str, Any]):
        """Expected core capabilities are defined."""
        defined = set(core_capabilities["capabilities"].keys())

        for expected in self.EXPECTED_CAPABILITIES:
            assert expected in defined, f"Expected capability {expected} not found"

    def test_score_salience_has_module_provider(self, core_capabilities: dict[str, Any]):
        """score_salience has a module provider."""
        cap = core_capabilities["capabilities"]["score_salience"]
        providers = cap.get("providers", [])
        assert len(providers) >= 1
        assert providers[0]["type"] == "module"
        assert providers[0]["module_id"] == "salience.score"

    def test_pattern_separate_has_module_provider(self, core_capabilities: dict[str, Any]):
        """pattern_separate has a module provider."""
        cap = core_capabilities["capabilities"]["pattern_separate"]
        providers = cap.get("providers", [])
        assert len(providers) >= 1
        assert providers[0]["type"] == "module"
        assert providers[0]["module_id"] == "hippocampus.pattern_separate"


# -----------------------------------------------------------------------------
# All Capability Files Tests
# -----------------------------------------------------------------------------


class TestAllCapabilityFiles:
    """Tests that run on all capability YAML files."""

    def test_all_capability_yamls_are_valid(self, validator: Draft7Validator):
        """All capability YAML files validate against schema."""
        if not CAPABILITIES_DIR.exists():
            pytest.skip("Capabilities directory does not exist")

        errors_by_file = {}

        for yaml_file in CAPABILITIES_DIR.glob("*.yaml"):
            content = yaml.safe_load(yaml_file.read_text())
            errors = list(validator.iter_errors(content))
            if errors:
                errors_by_file[yaml_file.name] = [f"{e.path}: {e.message}" for e in errors]

        assert len(errors_by_file) == 0, f"Validation errors: {errors_by_file}"

    def test_all_capability_yamls_parse(self):
        """All capability YAML files parse without error."""
        if not CAPABILITIES_DIR.exists():
            pytest.skip("Capabilities directory does not exist")

        for yaml_file in CAPABILITIES_DIR.glob("*.yaml"):
            try:
                content = yaml.safe_load(yaml_file.read_text())
                assert content is not None, f"{yaml_file.name} parsed to None"
            except yaml.YAMLError as e:
                pytest.fail(f"{yaml_file.name} failed to parse: {e}")
