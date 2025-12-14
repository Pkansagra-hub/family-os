"""
Tests for ModuleContract and PipelineSpec schema extensions.

Issue 1.1.3: Extend ModuleContract for Fabric Integration
Issue 1.1.4: Extend PipelineSpec for Triggers
ADR: ADR-K004 Capability Mesh Architecture
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from k0.runtime.schemas import (
    FabricContextPolicy,
    ModuleContract,
    PipelineSpec,
    StageSpec,
    TriggerSpec,
    TriggerType,
)


class TestModuleContractFabricFields:
    """Tests for ModuleContract fabric integration fields (Issue 1.1.3)."""

    def test_module_contract_fabric_callable_default_false(self):
        """fabric_callable defaults to False for backward compatibility."""
        contract = ModuleContract(
            module_id="hippocampus.pattern_separate",
            version="v1",
            latency_budget_ms=15,
        )
        assert contract.fabric_callable is False

    def test_module_contract_fabric_capabilities_empty_default(self):
        """fabric_capabilities defaults to empty list."""
        contract = ModuleContract(
            module_id="hippocampus.pattern_separate",
            version="v1",
            latency_budget_ms=15,
        )
        assert contract.fabric_capabilities == []

    def test_module_contract_fabric_context_policy_default_inherit(self):
        """fabric_context_policy defaults to INHERIT."""
        contract = ModuleContract(
            module_id="hippocampus.pattern_separate",
            version="v1",
            latency_budget_ms=15,
        )
        assert contract.fabric_context_policy == FabricContextPolicy.INHERIT

    def test_module_contract_with_fabric_fields(self):
        """ModuleContract with all fabric fields set."""
        contract = ModuleContract(
            module_id="salience.score",
            version="v1",
            latency_budget_ms=50,
            fabric_callable=True,
            fabric_capabilities=["score_salience", "compute_novelty"],
            fabric_context_policy=FabricContextPolicy.ISOLATED,
        )
        assert contract.fabric_callable is True
        assert contract.fabric_capabilities == ["score_salience", "compute_novelty"]
        assert contract.fabric_context_policy == FabricContextPolicy.ISOLATED

    def test_module_contract_fabric_context_policy_synthetic(self):
        """ModuleContract with SYNTHETIC context policy."""
        contract = ModuleContract(
            module_id="retrieval.faiss",
            version="v1",
            latency_budget_ms=100,
            fabric_callable=True,
            fabric_capabilities=["retrieve_similar"],
            fabric_context_policy=FabricContextPolicy.SYNTHETIC,
        )
        assert contract.fabric_context_policy == FabricContextPolicy.SYNTHETIC

    def test_existing_module_contracts_still_validate(self):
        """Existing module contracts without fabric fields still validate."""
        # Simulates loading an old contract YAML
        contract = ModuleContract(
            module_id="affect.analyze",
            version="v1",
            input_event_types=["p02.write.requested.v1"],
            output_event_types=["p02.affect.analyzed.v1"],
            latency_budget_ms=10,
            side_effects=["read:st_hipp_events"],
            idempotent=True,
        )
        assert contract.module_id == "affect.analyze"
        # Defaults applied
        assert contract.fabric_callable is False
        assert contract.fabric_capabilities == []
        assert contract.fabric_context_policy == FabricContextPolicy.INHERIT


class TestPipelineSpecTriggerFields:
    """Tests for PipelineSpec trigger fields (Issue 1.1.4)."""

    def test_pipeline_spec_triggers_default_empty(self):
        """triggers defaults to empty list for backward compatibility."""
        spec = PipelineSpec(
            pipeline_id="P02_WRITE",
            version="v1",
            dag=[
                StageSpec(
                    id="stage_10_affect",
                    module="affect.analyze:v1",
                ),
            ],
        )
        assert spec.triggers == []

    def test_pipeline_spec_fabric_actions_default_empty(self):
        """fabric_actions defaults to empty list."""
        spec = PipelineSpec(
            pipeline_id="P02_WRITE",
            version="v1",
            dag=[
                StageSpec(
                    id="stage_10_affect",
                    module="affect.analyze:v1",
                ),
            ],
        )
        assert spec.fabric_actions == []

    def test_pipeline_spec_with_interval_trigger(self):
        """PipelineSpec with interval trigger."""
        spec = PipelineSpec(
            pipeline_id="P08_EMBEDDING_MANAGEMENT",
            version="v2",
            entry_topic="scheduled.p08.trigger.v1",
            dag=[
                StageSpec(
                    id="stage_10_index",
                    module="faiss.index:v1",
                ),
            ],
            triggers=[
                TriggerSpec(
                    id="faiss_indexer_interval",
                    type=TriggerType.INTERVAL,
                    interval_seconds=300,
                    batch_size=100,
                ),
            ],
        )
        assert len(spec.triggers) == 1
        assert spec.triggers[0].id == "faiss_indexer_interval"
        assert spec.triggers[0].type == TriggerType.INTERVAL
        assert spec.triggers[0].interval_seconds == 300

    def test_pipeline_spec_with_threshold_trigger(self):
        """PipelineSpec with threshold trigger."""
        spec = PipelineSpec(
            pipeline_id="P08_EMBEDDING_MANAGEMENT",
            version="v2",
            dag=[
                StageSpec(
                    id="stage_10_index",
                    module="faiss.index:v1",
                ),
            ],
            triggers=[
                TriggerSpec(
                    id="faiss_indexer_threshold",
                    type=TriggerType.THRESHOLD,
                    table="st_vec",
                    condition="status = 'READY'",
                    threshold_count=50,
                    check_interval_seconds=30,
                ),
            ],
        )
        assert len(spec.triggers) == 1
        assert spec.triggers[0].table == "st_vec"
        assert spec.triggers[0].threshold_count == 50

    def test_pipeline_spec_with_multiple_triggers(self):
        """PipelineSpec with multiple triggers."""
        spec = PipelineSpec(
            pipeline_id="P08_EMBEDDING_MANAGEMENT",
            version="v2",
            dag=[
                StageSpec(
                    id="stage_10_index",
                    module="faiss.index:v1",
                ),
            ],
            triggers=[
                TriggerSpec(
                    id="faiss_indexer_interval",
                    type=TriggerType.INTERVAL,
                    interval_seconds=300,
                ),
                TriggerSpec(
                    id="faiss_indexer_threshold",
                    type=TriggerType.THRESHOLD,
                    table="st_vec",
                    threshold_count=50,
                ),
                TriggerSpec(
                    id="faiss_indexer_manual",
                    type=TriggerType.MANUAL,
                ),
            ],
        )
        assert len(spec.triggers) == 3
        assert spec.triggers[0].type == TriggerType.INTERVAL
        assert spec.triggers[1].type == TriggerType.THRESHOLD
        assert spec.triggers[2].type == TriggerType.MANUAL

    def test_pipeline_spec_with_fabric_actions(self):
        """PipelineSpec with fabric_actions."""
        spec = PipelineSpec(
            pipeline_id="P03_CONSOLIDATION",
            version="v1",
            dag=[
                StageSpec(
                    id="stage_10_novelty",
                    module="consolidation.novelty:v1",
                ),
            ],
            fabric_actions=["consolidate_memory", "prune_duplicates"],
        )
        assert spec.fabric_actions == ["consolidate_memory", "prune_duplicates"]

    def test_existing_pipeline_specs_still_validate(self):
        """Existing pipeline specs without trigger fields still validate."""
        # Simulates loading an old pipeline YAML
        spec = PipelineSpec(
            pipeline_id="P02_WRITE",
            version="v1",
            entry_topic="cognitive.memory.write.committed.v1",
            exit_topic="p02.write.complete.v1",
            concurrency=1,
            max_queue=512,
            dag=[
                StageSpec(
                    id="stage_10_affect",
                    module="affect.analyze:v1",
                    after=[],
                ),
                StageSpec(
                    id="stage_20_space",
                    module="space.resolve_visibility:v1",
                    after=["stage_10_affect"],
                ),
            ],
        )
        assert spec.pipeline_id == "P02_WRITE"
        # Defaults applied
        assert spec.triggers == []
        assert spec.fabric_actions == []

    def test_pipeline_spec_invalid_trigger_raises(self):
        """Invalid trigger in pipeline spec raises ValidationError."""
        with pytest.raises(ValidationError):
            PipelineSpec(
                pipeline_id="P08_EMBEDDING_MANAGEMENT",
                version="v2",
                dag=[
                    StageSpec(
                        id="stage_10_index",
                        module="faiss.index:v1",
                    ),
                ],
                triggers=[
                    TriggerSpec(
                        id="bad_interval",
                        type=TriggerType.INTERVAL,
                        # Missing interval_seconds
                    ),
                ],
            )
