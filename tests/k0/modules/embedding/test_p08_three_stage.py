"""Integration tests for P08Runner -- 3-stage sequential pipeline execution.

Exercises P08Runner.handle() with real module functions resolved from a
FakeModuleRegistry. Tests all-stages-pass, fault isolation on stage failure,
and the aggregate result structure.

Epic: M4 4.21
Runner: k0/pipelines/p08/runner.py
Contract: k0/contracts/pipelines/p08_embedding_management.v3.yaml
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from k0.modules.embedding import backfill, cleanup, integrity_check
from k0.pipelines.p08.runner import P08Runner
from tests.k0.modules.embedding.conftest import FakeContext, FakeMessage, FakeSyscalls

# =============================================================================
# Lightweight StageSpec / PipelineSpec doubles
# =============================================================================


class FakeStageSpec:
    """Minimal StageSpec double for P08Runner iteration."""

    def __init__(self, stage_id: str, module: str, config: dict[str, Any] | None = None) -> None:
        self.id = stage_id
        self.module = module
        self.after: list[str] = []
        self.config: dict[str, Any] = config or {}


class FakePipelineSpec:
    """Minimal PipelineSpec double with the 3 P08 stages."""

    def __init__(
        self,
        stages: list[FakeStageSpec] | None = None,
        pipeline_id: str = "P08_EMBEDDING",
    ) -> None:
        self.pipeline_id = pipeline_id
        self.version = "v3"
        self.dag = stages or [
            FakeStageSpec("stage_10_backfill", "embedding.backfill:v2", {"batch_size": 100}),
            FakeStageSpec("stage_20_cleanup", "embedding.cleanup:v2", {"batch_size": 500}),
            FakeStageSpec(
                "stage_30_integrity", "embedding.integrity_check:v1", {"auto_correct_missing": True}
            ),
        ]
        self.declared_topics = ("scheduled.p08.maintenance.v1",)
        self.concurrency = 1
        self.max_queue = 1000
        self.required_caps = ("st_vec.read", "st_vec.write")
        self.contract_version = 3


class FakeModuleRegistry:
    """Resolves module strings to real async functions."""

    def __init__(self, modules: dict[str, Any] | None = None) -> None:
        self._modules = modules or {}

    def get(self, module_path: str) -> Any:
        fn = self._modules.get(module_path)
        if fn is None:
            raise KeyError(f"Module not found: {module_path}")
        return fn


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture()
def registry() -> FakeModuleRegistry:
    """Registry that resolves P08 stage modules to real functions."""
    return FakeModuleRegistry(
        {
            "embedding.backfill:v2": backfill.run,
            "embedding.cleanup:v2": cleanup.run,
            "embedding.integrity_check:v1": integrity_check.run,
        }
    )


@pytest.fixture()
def p08_spec() -> FakePipelineSpec:
    return FakePipelineSpec()


@pytest.fixture()
def p08_runner(p08_spec: FakePipelineSpec, registry: FakeModuleRegistry) -> P08Runner:
    return P08Runner(spec=p08_spec, registry=registry)


@pytest.fixture()
def trigger_message() -> FakeMessage:
    """Message simulating a scheduler trigger with context."""
    payload = {
        "trigger_id": "backfill_interval",
        "context": {
            "tenant_id": "tenant_test",
            "space_id": "space_home",
        },
    }
    return FakeMessage(payload=payload)


@pytest.fixture(autouse=True)
def _reset_module_metrics() -> None:
    """Reset all module metrics before each test."""
    backfill.reset_metrics()
    cleanup.reset_metrics()
    integrity_check.reset_metrics()


# =============================================================================
# Test Class 1: All Stages Complete Successfully
# =============================================================================


class TestP08AllStagesPass:
    """P08Runner executes all 3 stages when no errors occur."""

    @pytest.mark.asyncio
    async def test_all_stages_completed(
        self,
        p08_runner: P08Runner,
        syscalls: FakeSyscalls,
        context: FakeContext,
        trigger_message: FakeMessage,
        sample_events: list[dict[str, Any]],
    ) -> None:
        await p08_runner.on_startup(context)
        result = await p08_runner.handle(trigger_message)

        assert result["status"] == "completed"
        assert result["completed_count"] == 3
        assert result["failed_count"] == 0
        assert result["total_stages"] == 3

    @pytest.mark.asyncio
    async def test_all_stage_ids_in_results(
        self,
        p08_runner: P08Runner,
        syscalls: FakeSyscalls,
        context: FakeContext,
        trigger_message: FakeMessage,
        sample_events: list[dict[str, Any]],
    ) -> None:
        await p08_runner.on_startup(context)
        result = await p08_runner.handle(trigger_message)

        assert "stage_10_backfill" in result["stages"]
        assert "stage_20_cleanup" in result["stages"]
        assert "stage_30_integrity" in result["stages"]

    @pytest.mark.asyncio
    async def test_each_stage_has_completed_status(
        self,
        p08_runner: P08Runner,
        syscalls: FakeSyscalls,
        context: FakeContext,
        trigger_message: FakeMessage,
        sample_events: list[dict[str, Any]],
    ) -> None:
        await p08_runner.on_startup(context)
        result = await p08_runner.handle(trigger_message)

        for stage_id, stage_result in result["stages"].items():
            assert stage_result["status"] == "completed", f"{stage_id} should be completed"
            assert "duration_ms" in stage_result
            assert stage_result["duration_ms"] >= 0

    @pytest.mark.asyncio
    async def test_backfill_stage_produces_vectors(
        self,
        p08_runner: P08Runner,
        syscalls: FakeSyscalls,
        context: FakeContext,
        trigger_message: FakeMessage,
        sample_events: list[dict[str, Any]],
    ) -> None:
        await p08_runner.on_startup(context)
        result = await p08_runner.handle(trigger_message)

        backfill_result = result["stages"]["stage_10_backfill"]["result"]
        assert backfill_result["backfilled_count"] == 5
        assert len(syscalls.vec_store) == 5

    @pytest.mark.asyncio
    async def test_integrity_stage_reports_healthy(
        self,
        p08_runner: P08Runner,
        syscalls: FakeSyscalls,
        context: FakeContext,
        trigger_message: FakeMessage,
        sample_events: list[dict[str, Any]],
    ) -> None:
        await p08_runner.on_startup(context)
        result = await p08_runner.handle(trigger_message)

        integrity_result = result["stages"]["stage_30_integrity"]["result"]
        assert integrity_result["integrity_check"]["status"] == "HEALTHY"

    @pytest.mark.asyncio
    async def test_pipeline_id_in_result(
        self,
        p08_runner: P08Runner,
        syscalls: FakeSyscalls,
        context: FakeContext,
        trigger_message: FakeMessage,
        sample_events: list[dict[str, Any]],
    ) -> None:
        await p08_runner.on_startup(context)
        result = await p08_runner.handle(trigger_message)

        assert result["pipeline_id"] == "P08_EMBEDDING"

    @pytest.mark.asyncio
    async def test_run_id_is_uuid(
        self,
        p08_runner: P08Runner,
        syscalls: FakeSyscalls,
        context: FakeContext,
        trigger_message: FakeMessage,
        sample_events: list[dict[str, Any]],
    ) -> None:
        import uuid

        await p08_runner.on_startup(context)
        result = await p08_runner.handle(trigger_message)

        uuid.UUID(result["run_id"])  # raises ValueError if not valid UUID


# =============================================================================
# Test Class 2: Fault Isolation -- Stage Failure Doesn't Block Others
# =============================================================================


class TestP08FaultIsolation:
    """A failing stage does NOT prevent subsequent stages from running."""

    @pytest.mark.asyncio
    async def test_stage_10_failure_does_not_block_stage_20_30(
        self,
        syscalls: FakeSyscalls,
        context: FakeContext,
        trigger_message: FakeMessage,
    ) -> None:
        async def failing_backfill(*args: Any, **kwargs: Any) -> dict:
            raise RuntimeError("UltraBERT unavailable")

        registry = FakeModuleRegistry(
            {
                "embedding.backfill:v2": failing_backfill,
                "embedding.cleanup:v2": cleanup.run,
                "embedding.integrity_check:v1": integrity_check.run,
            }
        )
        spec = FakePipelineSpec()
        runner = P08Runner(spec=spec, registry=registry)
        await runner.on_startup(context)

        result = await runner.handle(trigger_message)

        assert result["status"] == "partial"
        assert result["failed_count"] == 1
        assert result["completed_count"] == 2

        # Stage 10 failed
        assert result["stages"]["stage_10_backfill"]["status"] == "failed"
        assert "UltraBERT unavailable" in result["stages"]["stage_10_backfill"]["error"]

        # Stage 20 and 30 still completed
        assert result["stages"]["stage_20_cleanup"]["status"] == "completed"
        assert result["stages"]["stage_30_integrity"]["status"] == "completed"

    @pytest.mark.asyncio
    async def test_stage_20_failure_does_not_block_stage_30(
        self,
        syscalls: FakeSyscalls,
        context: FakeContext,
        trigger_message: FakeMessage,
        sample_events: list[dict[str, Any]],
    ) -> None:
        async def failing_cleanup(*args: Any, **kwargs: Any) -> dict:
            raise RuntimeError("Cleanup query timeout")

        registry = FakeModuleRegistry(
            {
                "embedding.backfill:v2": backfill.run,
                "embedding.cleanup:v2": failing_cleanup,
                "embedding.integrity_check:v1": integrity_check.run,
            }
        )
        spec = FakePipelineSpec()
        runner = P08Runner(spec=spec, registry=registry)
        await runner.on_startup(context)

        result = await runner.handle(trigger_message)

        assert result["status"] == "partial"
        assert result["stages"]["stage_10_backfill"]["status"] == "completed"
        assert result["stages"]["stage_20_cleanup"]["status"] == "failed"
        assert result["stages"]["stage_30_integrity"]["status"] == "completed"

    @pytest.mark.asyncio
    async def test_all_stages_fail_returns_partial(
        self,
        context: FakeContext,
        trigger_message: FakeMessage,
    ) -> None:
        async def always_fail(*args: Any, **kwargs: Any) -> dict:
            raise RuntimeError("Total failure")

        registry = FakeModuleRegistry(
            {
                "embedding.backfill:v2": always_fail,
                "embedding.cleanup:v2": always_fail,
                "embedding.integrity_check:v1": always_fail,
            }
        )
        spec = FakePipelineSpec()
        runner = P08Runner(spec=spec, registry=registry)
        await runner.on_startup(context)

        result = await runner.handle(trigger_message)

        assert result["status"] == "partial"
        assert result["failed_count"] == 3
        assert result["completed_count"] == 0


# =============================================================================
# Test Class 3: Trigger Payload Parsing
# =============================================================================


class TestP08TriggerPayload:
    """P08Runner correctly parses trigger context from message payload."""

    @pytest.mark.asyncio
    async def test_parses_tenant_from_payload(
        self,
        p08_runner: P08Runner,
        syscalls: FakeSyscalls,
        context: FakeContext,
    ) -> None:
        # Seed event for specific tenant
        syscalls.hipp_events["evt_ta"] = {
            "event_id": "evt_ta",
            "tenant_id": "tenant_alpha",
            "space_id": "space_work",
            "event_text": "Alpha tenant event",
            "embedding_status": "PENDING",
        }

        payload = {
            "trigger_id": "backfill_threshold",
            "context": {"tenant_id": "tenant_alpha", "space_id": "space_work"},
        }
        msg = FakeMessage(payload=payload)

        await p08_runner.on_startup(context)
        result = await p08_runner.handle(msg)

        assert result["status"] == "completed"

    @pytest.mark.asyncio
    async def test_handles_empty_payload_gracefully(
        self,
        p08_runner: P08Runner,
        syscalls: FakeSyscalls,
        context: FakeContext,
    ) -> None:
        msg = FakeMessage(payload=b"{}")

        await p08_runner.on_startup(context)
        result = await p08_runner.handle(msg)

        # Should still run all stages (with default tenant/space)
        assert result["total_stages"] == 3

    @pytest.mark.asyncio
    async def test_handles_malformed_payload(
        self,
        p08_runner: P08Runner,
        syscalls: FakeSyscalls,
        context: FakeContext,
    ) -> None:
        msg = FakeMessage(payload=b"not valid json")

        await p08_runner.on_startup(context)
        result = await p08_runner.handle(msg)

        # Malformed payload falls back to empty context
        assert result["total_stages"] == 3


# =============================================================================
# Test Class 4: Result Structure Contract
# =============================================================================


class TestP08ResultContract:
    """P08Runner result matches the documented return structure."""

    @pytest.mark.asyncio
    async def test_result_has_required_keys(
        self,
        p08_runner: P08Runner,
        syscalls: FakeSyscalls,
        context: FakeContext,
        trigger_message: FakeMessage,
    ) -> None:
        await p08_runner.on_startup(context)
        result = await p08_runner.handle(trigger_message)

        required_keys = {
            "pipeline_id",
            "run_id",
            "status",
            "stages",
            "completed_count",
            "failed_count",
            "total_stages",
            "duration_ms",
            "executed_at",
        }
        assert required_keys.issubset(set(result.keys()))

    @pytest.mark.asyncio
    async def test_duration_is_positive(
        self,
        p08_runner: P08Runner,
        syscalls: FakeSyscalls,
        context: FakeContext,
        trigger_message: FakeMessage,
    ) -> None:
        await p08_runner.on_startup(context)
        result = await p08_runner.handle(trigger_message)

        assert result["duration_ms"] > 0

    @pytest.mark.asyncio
    async def test_executed_at_is_iso_format(
        self,
        p08_runner: P08Runner,
        syscalls: FakeSyscalls,
        context: FakeContext,
        trigger_message: FakeMessage,
    ) -> None:
        from datetime import datetime

        await p08_runner.on_startup(context)
        result = await p08_runner.handle(trigger_message)

        # Should parse without error
        datetime.fromisoformat(result["executed_at"])


# =============================================================================
# Test Class 5: V3 Contract Alignment
# =============================================================================


class TestP08ContractAlignment:
    """P08Runner properties align with v3 YAML contract."""

    def test_contract_loads(self) -> None:
        contract_path = Path("k0/contracts/pipelines/p08_embedding_management.v3.yaml")
        contract = yaml.safe_load(contract_path.read_text(encoding="utf-8"))
        assert contract["pipeline_id"] == "P08_EMBEDDING"
        assert contract["version"] == "v3"

    def test_runner_class_in_contract(self) -> None:
        contract_path = Path("k0/contracts/pipelines/p08_embedding_management.v3.yaml")
        contract = yaml.safe_load(contract_path.read_text(encoding="utf-8"))
        assert contract["runner_class"] == "k0.pipelines.p08.runner:P08Runner"

    def test_three_stages_in_contract(self) -> None:
        contract_path = Path("k0/contracts/pipelines/p08_embedding_management.v3.yaml")
        contract = yaml.safe_load(contract_path.read_text(encoding="utf-8"))
        assert len(contract["dag"]) == 3

    def test_stage_ids_match_contract(self) -> None:
        contract_path = Path("k0/contracts/pipelines/p08_embedding_management.v3.yaml")
        contract = yaml.safe_load(contract_path.read_text(encoding="utf-8"))
        stage_ids = [s["id"] for s in contract["dag"]]
        assert stage_ids == ["stage_10_backfill", "stage_20_cleanup", "stage_30_integrity"]

    def test_pipeline_properties(
        self,
        p08_runner: P08Runner,
    ) -> None:
        assert p08_runner.pipeline_id == "P08_EMBEDDING"
        assert p08_runner.concurrency == 1
        assert p08_runner.max_queue == 1000
