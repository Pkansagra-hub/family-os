"""
Epic 3.17 -- Module Contract YAML Validation Tests

Validates all 6 v2 module contracts and the P02 pipeline contract parse correctly
and conform to the ModuleContract Pydantic schema.

Contract: k0/contracts/modules/*.v2.yaml, k0/contracts/pipelines/p02_write.v2.yaml
"""

from pathlib import Path

import pytest
import yaml

from k0.runtime.schemas import ModuleContract

CONTRACTS_DIR = Path(__file__).resolve().parents[3] / "k0" / "contracts" / "modules"
PIPELINES_DIR = Path(__file__).resolve().parents[3] / "k0" / "contracts" / "pipelines"

# The 6 v2 module contracts required by Epic 3.17
V2_MODULE_CONTRACTS = [
    "affect.analyze.v2.yaml",
    "social.family_graph_resolve.v2.yaml",
    "salience.score.v2.yaml",
    "context.temporal_profile.v2.yaml",
    "builders.hipp_events_row.v2.yaml",
    "hippocampus.semantic_project.v2.yaml",
]


# =============================================================================
# Contract file existence
# =============================================================================


@pytest.mark.parametrize("filename", V2_MODULE_CONTRACTS)
def test_v2_module_contract_file_exists(filename):
    """Each v2 module contract YAML file exists"""
    path = CONTRACTS_DIR / filename
    assert path.exists(), f"Missing contract file: {path}"


def test_p02_pipeline_v2_contract_exists():
    """P02 pipeline v2 contract YAML exists"""
    path = PIPELINES_DIR / "p02_write.v2.yaml"
    assert path.exists(), f"Missing pipeline contract: {path}"


# =============================================================================
# YAML parsing
# =============================================================================


@pytest.mark.parametrize("filename", V2_MODULE_CONTRACTS)
def test_v2_module_contract_yaml_parses(filename):
    """Each v2 module contract is valid YAML"""
    path = CONTRACTS_DIR / filename
    with open(path) as f:
        data = yaml.safe_load(f)
    assert isinstance(data, dict), f"{filename} did not parse to a dict"
    assert "module_id" in data, f"{filename} missing module_id"
    assert "version" in data, f"{filename} missing version"


def test_p02_pipeline_v2_yaml_parses():
    """P02 pipeline v2 contract is valid YAML"""
    path = PIPELINES_DIR / "p02_write.v2.yaml"
    with open(path) as f:
        data = yaml.safe_load(f)
    assert isinstance(data, dict)
    assert "pipeline_id" in data


# =============================================================================
# Pydantic schema validation (ModuleContract)
# =============================================================================


@pytest.mark.parametrize("filename", V2_MODULE_CONTRACTS)
def test_v2_module_contract_validates_against_schema(filename):
    """Each v2 module contract validates against ModuleContract Pydantic model"""
    path = CONTRACTS_DIR / filename
    with open(path) as f:
        data = yaml.safe_load(f)

    # ModuleContract requires: module_id, version, latency_budget_ms
    contract = ModuleContract(**data)
    assert contract.module_id
    assert contract.version == "v2"
    assert contract.latency_budget_ms >= 1


# =============================================================================
# Contract content validation
# =============================================================================


EXPECTED_CONTRACTS = {
    "affect.analyze.v2.yaml": {
        "module_id": "affect.analyze",
        "latency_budget_ms": 70,
        "idempotent": True,
    },
    "social.family_graph_resolve.v2.yaml": {
        "module_id": "social.family_graph_resolve",
        "latency_budget_ms": 12,
        "idempotent": True,
    },
    "salience.score.v2.yaml": {
        "module_id": "salience.score",
        "latency_budget_ms": 5,
        "idempotent": True,
    },
    "context.temporal_profile.v2.yaml": {
        "module_id": "context.temporal_profile",
        "latency_budget_ms": 6,
        "idempotent": True,
    },
    "builders.hipp_events_row.v2.yaml": {
        "module_id": "builders.hipp_events_row",
        "latency_budget_ms": 10,
        "idempotent": True,
    },
    "hippocampus.semantic_project.v2.yaml": {
        "module_id": "hippocampus.semantic_project",
        "latency_budget_ms": 150,
        "idempotent": True,
    },
}


@pytest.mark.parametrize("filename", V2_MODULE_CONTRACTS)
def test_v2_contract_latency_matches_spec(filename):
    """Contract latency_budget_ms matches Part A epic specifications"""
    path = CONTRACTS_DIR / filename
    with open(path) as f:
        data = yaml.safe_load(f)
    expected = EXPECTED_CONTRACTS[filename]
    assert data["latency_budget_ms"] == expected["latency_budget_ms"], (
        f"{filename}: expected latency {expected['latency_budget_ms']}ms, "
        f"got {data['latency_budget_ms']}ms"
    )


@pytest.mark.parametrize("filename", V2_MODULE_CONTRACTS)
def test_v2_contract_module_id_matches_spec(filename):
    """Contract module_id matches expected value"""
    path = CONTRACTS_DIR / filename
    with open(path) as f:
        data = yaml.safe_load(f)
    expected = EXPECTED_CONTRACTS[filename]
    assert data["module_id"] == expected["module_id"]


@pytest.mark.parametrize("filename", V2_MODULE_CONTRACTS)
def test_v2_contract_has_output_event_types(filename):
    """Each v2 contract specifies output_event_types"""
    path = CONTRACTS_DIR / filename
    with open(path) as f:
        data = yaml.safe_load(f)
    assert "output_event_types" in data
    assert len(data["output_event_types"]) >= 1


@pytest.mark.parametrize("filename", V2_MODULE_CONTRACTS)
def test_v2_contract_has_input_event_types(filename):
    """Each v2 contract specifies input_event_types"""
    path = CONTRACTS_DIR / filename
    with open(path) as f:
        data = yaml.safe_load(f)
    assert "input_event_types" in data
    assert len(data["input_event_types"]) >= 1


def test_v1_contracts_not_deleted():
    """v1 contracts still exist (not deleted, kept for reference)"""
    v1_files = list(CONTRACTS_DIR.glob("*.v1.yaml"))
    assert len(v1_files) > 0, "No v1 contracts found -- they should be kept for reference"


def test_all_7_epic317_files_exist():
    """All 7 files required by Epic 3.17 exist"""
    for filename in V2_MODULE_CONTRACTS:
        assert (CONTRACTS_DIR / filename).exists(), f"Missing: {filename}"
    assert (PIPELINES_DIR / "p02_write.v2.yaml").exists(), "Missing: p02_write.v2.yaml"
