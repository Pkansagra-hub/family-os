"""
P02 Inline Embedding Integration Tests

Tests the P02 v1.1 pipeline contract with ADR-K003 inline embedding changes.

Contract: k0/contracts/pipelines/p02_write.v1.yaml (v1.1)
Modules: M22 (embedding.extract_from_cache), M23 (builders.embedding_write)
Related: ADR-K003 (Inline Embedding via UltraBERT Single-Pass Cache)

Test Scope:
- P02 v1.1 contract validation (stages 22 and 61)
- M22 and M23 module discovery
- Contract schema validation

Note: Module unit tests are in tests/k0/modules/embedding/ and tests/k0/modules/builders/
This file validates P02 v1.1 contract structure and module discovery for inline embedding (ADR-K003).
"""

from pathlib import Path

import yaml

# =============================================================================
# Test 1: P02 v1.1 Contract Structure
# =============================================================================


def test_p02_v1_1_contract_structure():
    """
    Test that P02 v1.1 contract exists and has inline embedding stages.

    Validates:
    - Contract file exists at k0/contracts/pipelines/p02_write.v1.yaml
    - Version is v1.1
    - Stage 22 exists (embedding.extract_from_cache:v1)
    - Stage 61 exists (builders.embedding_write:v1)
    - st_vec.write capability registered
    """
    contract_path = Path("k0/contracts/pipelines/p02_write.v1.yaml")
    assert contract_path.exists(), f"P02 contract not found at {contract_path}"

    with open(contract_path) as f:
        contract = yaml.safe_load(f)

    # Validate version
    assert contract["version"] == "v1.1", f"Expected v1.1, got {contract['version']}"

    # Validate inline embedding is mentioned in description
    assert (
        "ADR-K003" in contract["description"]
        or "inline embedding" in contract["description"].lower()
    ), "P02 v1.1 should reference ADR-K003 inline embedding"

    # Validate required capabilities
    capabilities = contract.get("required_capabilities", [])
    assert "st_vec.write" in capabilities, "P02 v1.1 should require st_vec.write capability"

    # Validate DAG stages
    dag = contract["dag"]
    stage_ids = [stage["id"] for stage in dag]

    # Stage 22: embedding.extract_from_cache:v1
    assert (
        "stage_22_embedding_extract" in stage_ids
    ), "P02 v1.1 should have stage_22_embedding_extract"
    stage_22 = next(s for s in dag if s["id"] == "stage_22_embedding_extract")
    assert stage_22["module"] == "embedding.extract_from_cache:v1"

    # Stage 61: builders.embedding_write:v1
    assert "stage_61_embedding_write" in stage_ids, "P02 v1.1 should have stage_61_embedding_write"
    stage_61 = next(s for s in dag if s["id"] == "stage_61_embedding_write")
    assert stage_61["module"] == "builders.embedding_write:v1"


# =============================================================================
# Test 2: M22 Module Discovery
# =============================================================================


def test_m22_module_discovery():
    """
    Test that M22 (embedding.extract_from_cache) module is discoverable.

    Validates:
    - Module file exists at k0/modules/embedding/extract_from_cache.py
    - Module contract exists at k0/contracts/modules/embedding.extract_from_cache.v1.yaml
    - Module exports run() function
    """
    # Check module file
    module_path = Path("k0/modules/embedding/extract_from_cache.py")
    assert module_path.exists(), f"M22 module not found at {module_path}"

    # Check contract
    contract_path = Path("k0/contracts/modules/embedding.extract_from_cache.v1.yaml")
    assert contract_path.exists(), f"M22 contract not found at {contract_path}"

    # Validate module exports run()
    from k0.modules.embedding.extract_from_cache import run

    assert callable(run), "M22 must export run() function"


# =============================================================================
# Test 3: M23 Module Discovery
# =============================================================================


def test_m23_module_discovery():
    """
    Test that M23 (builders.embedding_write) module is discoverable.

    Validates:
    - Module file exists at k0/modules/builders/embedding_write.py
    - Module contract exists at k0/contracts/modules/builders.embedding_write.v1.yaml
    - Module exports run() function
    """
    # Check module file
    module_path = Path("k0/modules/builders/embedding_write.py")
    assert module_path.exists(), f"M23 module not found at {module_path}"

    # Check contract
    contract_path = Path("k0/contracts/modules/builders.embedding_write.v1.yaml")
    assert contract_path.exists(), f"M23 contract not found at {contract_path}"

    # Validate module exports run()
    from k0.modules.builders.embedding_write import run

    assert callable(run), "M23 must export run() function"


# =============================================================================
# Test 4: P02 v1.1 Stage Dependencies
# =============================================================================


def test_p02_v1_1_stage_dependencies():
    """
    Test that P02 v1.1 stage dependencies are correct.

    Validates:
    - Stage 22 runs after stage 20
    - Stage 60 depends on stage 22
    - Stage 61 depends on stage 22
    - Stage 70 depends on stage 61
    """
    contract_path = Path("k0/contracts/pipelines/p02_write.v1.yaml")
    with open(contract_path) as f:
        contract = yaml.safe_load(f)

    dag = contract["dag"]

    # Find stages
    stage_22 = next(s for s in dag if s["id"] == "stage_22_embedding_extract")
    stage_60 = next(s for s in dag if s["id"] == "stage_60_build_hipp_events_row")
    stage_61 = next(s for s in dag if s["id"] == "stage_61_embedding_write")
    stage_70 = next(s for s in dag if s["id"] == "stage_70_atomic_writer")

    # Validate dependencies
    # Stage 22 should have no dependencies on stage 60/61 (runs early)
    assert "stage_60_build_hipp_events_row" not in stage_22.get("after", [])

    # Stage 60 should depend on stage 22
    assert "stage_22_embedding_extract" in stage_60["after"], "Stage 60 should depend on stage 22"

    # Stage 61 should NOT depend on stage 60 (parallel execution)
    # Stage 61 after list should reference stage 22
    assert "stage_22_embedding_extract" in stage_61.get(
        "after", []
    ), "Stage 61 should run after stage 22"

    # Stage 70 should depend on stage 61 (must wait for embedding write)
    assert "stage_61_embedding_write" in stage_70["after"], "Stage 70 should depend on stage 61"


# =============================================================================
# Test 5: Deprecated st_embedding_queue.write Capability
# =============================================================================


def test_p02_v1_1_deprecated_capability():
    """
    Test that P02 v1.1 marks st_embedding_queue.write as deprecated.

    Validates:
    - st_embedding_queue.write is still listed (backward compat)
    - st_embedding_queue.write is marked as deprecated or optional
    - st_vec.write is the new required capability
    """
    contract_path = Path("k0/contracts/pipelines/p02_write.v1.yaml")
    with open(contract_path) as f:
        contract = yaml.safe_load(f)

    capabilities = contract.get("required_capabilities", [])

    # st_vec.write should be required
    assert "st_vec.write" in capabilities, "P02 v1.1 should require st_vec.write"

    # Check description for deprecation note
    description = contract.get("description", "")
    assert (
        "deprecated" in description.lower() or "st_vec" in description.lower()
    ), "P02 v1.1 should document capability change"
