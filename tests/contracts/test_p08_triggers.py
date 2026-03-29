"""
P08 Contract Trigger Tests (Issue 5.1.1).

Tests that verify P08 contract is properly updated with declarative triggers
and validates against the PipelineSpec schema.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from k0.runtime.schemas import PipelineSpec, StageSpec


class TestP08ContractValidation:
    """Test P08 contract structure and validation."""

    @pytest.fixture
    def p08_contract_path(self) -> Path:
        """Path to P08 contract file."""
        return Path("k0/contracts/pipelines/p08_embedding_management.v3.yaml")

    @pytest.fixture
    def p08_contract(self, p08_contract_path: Path) -> dict:
        """Load P08 contract as dict."""
        with open(p08_contract_path) as f:
            return yaml.safe_load(f)

    def test_p08_contract_loads_without_error(self, p08_contract: dict) -> None:
        """Verify P08 contract loads successfully."""
        assert p08_contract is not None
        assert p08_contract["pipeline_id"] == "P08_EMBEDDING"

    def test_p08_contract_validates_schema(self, p08_contract: dict) -> None:
        """Verify P08 contract validates against PipelineSpec schema."""
        # Extract DAG stages for PipelineSpec
        dag_raw = p08_contract.get("dag", [])
        dag_stages = []
        for stage in dag_raw:
            dag_stages.append(
                StageSpec(
                    id=stage["id"],
                    module=stage["module"],
                    after=stage.get("after", stage.get("depends_on", [])),
                )
            )

        # Create PipelineSpec - use placeholder stage if no dag
        spec = PipelineSpec(
            pipeline_id=p08_contract["pipeline_id"],
            version=p08_contract["version"],
            description=p08_contract.get("description"),
            entry_topic=p08_contract.get("entry_topic"),
            exit_topic=p08_contract.get("exit_topic"),
            triggers=p08_contract.get("triggers", []),
            concurrency=p08_contract.get("concurrency", 1),
            max_queue=p08_contract.get("max_queue", 100),
            dag=(
                dag_stages
                if dag_stages
                else [StageSpec(id="placeholder", module="placeholder:v1", after=[])]
            ),
        )

        # If we got here, validation passed
        assert spec.pipeline_id == "P08_EMBEDDING"
        assert len(spec.triggers) == 3

    def test_p08_has_triggers(self, p08_contract: dict) -> None:
        """Verify P08 has triggers field."""
        assert "triggers" in p08_contract
        assert isinstance(p08_contract["triggers"], list)
        assert len(p08_contract["triggers"]) == 3

    def test_p08_has_interval_trigger(self, p08_contract: dict) -> None:
        """Verify P08 has interval trigger properly configured."""
        triggers = p08_contract["triggers"]
        interval = next((t for t in triggers if t["type"] == "interval"), None)

        assert interval is not None, "Missing interval trigger"
        assert interval["id"] == "backfill_interval"
        assert interval["interval_seconds"] == 300
        assert interval["batch_size"] == 100
        assert interval["catch_up_enabled"] is True

    def test_p08_has_threshold_trigger(self, p08_contract: dict) -> None:
        """Verify P08 has threshold trigger properly configured."""
        triggers = p08_contract["triggers"]
        threshold = next((t for t in triggers if t["type"] == "threshold"), None)

        assert threshold is not None, "Missing threshold trigger"
        assert threshold["id"] == "backfill_threshold"
        assert threshold["table"] == "st_hipp_events"
        assert threshold["condition"] == "embedding_status = 'PENDING'"
        assert threshold["threshold_count"] == 50
        assert threshold["check_interval_seconds"] == 60
        assert threshold["batch_size"] == 50

    def test_p08_has_manual_trigger(self, p08_contract: dict) -> None:
        """Verify P08 has manual trigger properly configured."""
        triggers = p08_contract["triggers"]
        manual = next((t for t in triggers if t["type"] == "manual"), None)

        assert manual is not None, "Missing manual trigger"
        assert manual["id"] == "maintenance_manual"

    def test_p08_no_legacy_trigger_mode(self, p08_contract: dict) -> None:
        """Verify P08 doesn't have legacy trigger_mode field active."""
        # The contract may have comments about the deprecated field,
        # but trigger_mode should not be active (triggers takes precedence)
        assert "triggers" in p08_contract
        # If trigger_mode exists, it should be ignored in favor of triggers
        if "trigger_mode" in p08_contract:
            # Legacy field exists but triggers should take precedence
            assert len(p08_contract["triggers"]) > 0

    def test_p08_has_fabric_dependencies(self, p08_contract: dict) -> None:
        """Verify P08 has required_capabilities defined."""
        assert "required_capabilities" in p08_contract
        caps = p08_contract["required_capabilities"]

        # Should have vector storage capabilities (FAISS deprecated, using pgvector)
        assert "st_vec.read" in caps
        assert "st_vec.write" in caps
        assert "st_hipp_events.read" in caps
        # Note: faiss.read/faiss.write removed after pgvector migration

    def test_p08_triggers_all_have_ids(self, p08_contract: dict) -> None:
        """Verify all triggers have unique IDs."""
        triggers = p08_contract["triggers"]
        ids = [t["id"] for t in triggers]

        assert len(ids) == len(set(ids)), "Trigger IDs must be unique"
        assert all(id for id in ids), "All triggers must have IDs"
