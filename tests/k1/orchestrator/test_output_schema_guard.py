"""OutputSchemaGuard pipeline tests (Epic 7.2.1 / ORCH-15).

Guard tests do NOT import guard classes directly -- they verify guard
behaviour through the OrchestratorService.process() -> DAGExecutor pipeline.

Coverage:
  1) Guard pipeline ordering (positional check only)
  2) Valid output -> process COMPLETED, fabric called once
  3) Invalid output -> StepRunner schema retry -> fabric called twice
  4) Invalid + retry succeeds -> process COMPLETED
  5) Invalid + retry still invalid -> OutputSchemaGuard HARD_STOP -> FAILED
  6) No output_schema -> process COMPLETED, no retry
  7) Nested schema: valid passes, invalid fails after retry
  8) Array schema: valid passes, invalid fails after retry
  9) Null data -> schema retry -> still null -> HARD_STOP -> FAILED
"""

from __future__ import annotations

from typing import Any, Dict
from uuid import uuid4

import pytest

from k1.fabric.types import CapabilityRequest, CapabilityResult
from k1.orchestrator.types import ProcessResult
from tests.k1.orchestrator.helpers import (
    make_plan,
    make_step,
    orchestrator_for_testing,
    process_plan,
    register_capabilities,
)

# ======================================================================
# Schemas
# ======================================================================

SIMPLE_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {"summary": {"type": "string"}},
    "required": ["summary"],
}

NESTED_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "user": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "meta": {
                    "type": "object",
                    "properties": {"age": {"type": "integer"}},
                    "required": ["age"],
                },
            },
            "required": ["name", "meta"],
        }
    },
    "required": ["user"],
}

ARRAY_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 1,
        }
    },
    "required": ["items"],
}


# ======================================================================
# Helpers
# ======================================================================


def _ok(data: Dict[str, Any] | None, trace_id: str = "trace-test") -> CapabilityResult:
    return CapabilityResult(
        request_id=f"r-{uuid4()}",
        success=True,
        data=data,
        error=None,
        provider_id="mock",
        trace_id=trace_id,
    )


def _seq_results(fabric, capability: str, *results: CapabilityResult):
    """Script sequential results for consecutive calls to *capability*."""
    calls = {"n": 0}
    original_log = fabric.call_log

    async def handler(request: CapabilityRequest) -> CapabilityResult:
        original_log.append(request)
        idx = min(calls["n"], len(results) - 1)
        calls["n"] += 1
        return results[idx]

    fabric.execute = handler


# ======================================================================
# Tests
# ======================================================================


class TestOutputSchemaGuardPipeline:
    """Verify ORCH-15 (output schema enforcement) through process() pipeline."""

    # -- (1) Guard pipeline ordering -----------------------------------

    @pytest.mark.asyncio
    async def test_guard_pipeline_order_includes_output_schema_first(self) -> None:
        """OutputSchemaGuard is guards[0] in factory pipeline."""
        service, _ = await orchestrator_for_testing()
        names = [g.__class__.__name__ for g in service._dag_executor._guards]
        assert names[0] == "OutputSchemaGuard"

    # -- (2) No output_schema -> COMPLETED, fabric called once ---------

    @pytest.mark.asyncio
    async def test_no_output_schema_completes_without_retry(self) -> None:
        service, adapters = await orchestrator_for_testing()
        fabric = adapters["fabric"]
        register_capabilities(fabric, "cap.plain")

        step = make_step("s1", "cap.plain")
        plan = make_plan([step])

        result = await process_plan(service, plan)

        assert result == ProcessResult.COMPLETED
        fabric.assert_called("cap.plain", times=1)

    # -- (3) Valid output -> COMPLETED, fabric called once -------------

    @pytest.mark.asyncio
    async def test_valid_output_completes_one_call(self) -> None:
        service, adapters = await orchestrator_for_testing()
        fabric = adapters["fabric"]
        register_capabilities(fabric, "cap.schema")

        fabric.script_result("cap.schema", _ok({"summary": "ok"}))
        step = make_step("s1", "cap.schema", output_schema=SIMPLE_SCHEMA)
        plan = make_plan([step])

        result = await process_plan(service, plan)

        assert result == ProcessResult.COMPLETED
        fabric.assert_called("cap.schema", times=1)

    # -- (4) Invalid then valid -> COMPLETED, fabric called twice ------

    @pytest.mark.asyncio
    async def test_invalid_then_valid_retries_once(self) -> None:
        service, adapters = await orchestrator_for_testing()
        fabric = adapters["fabric"]
        register_capabilities(fabric, "cap.schema")

        _seq_results(
            fabric,
            "cap.schema",
            _ok({"wrong": 1}),  # 1st call: invalid
            _ok({"summary": "fixed"}),  # 2nd call (schema retry): valid
        )
        step = make_step("s1", "cap.schema", output_schema=SIMPLE_SCHEMA)
        plan = make_plan([step])

        result = await process_plan(service, plan)

        assert result == ProcessResult.COMPLETED
        fabric.assert_called("cap.schema", times=2)
        # Verify schema hint was injected in retry request
        retry_req = fabric.call_log[1]
        assert "__schema_hint" in retry_req.params

    # -- (5) Invalid both times -> HARD_STOP -> FAILED -----------------

    @pytest.mark.asyncio
    async def test_persistent_invalid_yields_failed(self) -> None:
        service, adapters = await orchestrator_for_testing()
        fabric = adapters["fabric"]
        register_capabilities(fabric, "cap.schema")

        # Both calls return schema-violating data
        fabric.script_result("cap.schema", _ok({"wrong": True}))
        step = make_step("s1", "cap.schema", output_schema=SIMPLE_SCHEMA)
        plan = make_plan([step])

        result = await process_plan(service, plan)

        assert result == ProcessResult.FAILED
        fabric.assert_called("cap.schema", times=2)

    # -- (6) Null data -> schema retry -> still null -> FAILED ---------

    @pytest.mark.asyncio
    async def test_null_data_fails_after_retry(self) -> None:
        service, adapters = await orchestrator_for_testing()
        fabric = adapters["fabric"]
        register_capabilities(fabric, "cap.schema")

        fabric.script_result("cap.schema", _ok(None))
        step = make_step("s1", "cap.schema", output_schema=SIMPLE_SCHEMA)
        plan = make_plan([step])

        result = await process_plan(service, plan)

        assert result == ProcessResult.FAILED
        fabric.assert_called("cap.schema", times=2)

    # -- (7) Nested schema: valid -> COMPLETED -------------------------

    @pytest.mark.asyncio
    async def test_nested_schema_valid_completes(self) -> None:
        service, adapters = await orchestrator_for_testing()
        fabric = adapters["fabric"]
        register_capabilities(fabric, "cap.nested")

        fabric.script_result(
            "cap.nested",
            _ok({"user": {"name": "alice", "meta": {"age": 30}}}),
        )
        step = make_step("s1", "cap.nested", output_schema=NESTED_SCHEMA)
        plan = make_plan([step])

        result = await process_plan(service, plan)

        assert result == ProcessResult.COMPLETED
        fabric.assert_called("cap.nested", times=1)

    # -- (8) Nested schema: invalid -> retry -> still invalid -> FAILED

    @pytest.mark.asyncio
    async def test_nested_schema_invalid_fails_after_retry(self) -> None:
        service, adapters = await orchestrator_for_testing()
        fabric = adapters["fabric"]
        register_capabilities(fabric, "cap.nested")

        # Missing required "meta.age"
        fabric.script_result("cap.nested", _ok({"user": {"name": "alice"}}))
        step = make_step("s1", "cap.nested", output_schema=NESTED_SCHEMA)
        plan = make_plan([step])

        result = await process_plan(service, plan)

        assert result == ProcessResult.FAILED
        fabric.assert_called("cap.nested", times=2)

    # -- (9) Array schema: valid -> COMPLETED --------------------------

    @pytest.mark.asyncio
    async def test_array_schema_valid_completes(self) -> None:
        service, adapters = await orchestrator_for_testing()
        fabric = adapters["fabric"]
        register_capabilities(fabric, "cap.arr")

        fabric.script_result("cap.arr", _ok({"items": ["a", "b"]}))
        step = make_step("s1", "cap.arr", output_schema=ARRAY_SCHEMA)
        plan = make_plan([step])

        result = await process_plan(service, plan)

        assert result == ProcessResult.COMPLETED
        fabric.assert_called("cap.arr", times=1)

    # -- (10) Array schema: invalid type -> retry -> FAILED ------------

    @pytest.mark.asyncio
    async def test_array_schema_invalid_fails_after_retry(self) -> None:
        service, adapters = await orchestrator_for_testing()
        fabric = adapters["fabric"]
        register_capabilities(fabric, "cap.arr")

        # Array items should be strings, not ints
        fabric.script_result("cap.arr", _ok({"items": [1, 2]}))
        step = make_step("s1", "cap.arr", output_schema=ARRAY_SCHEMA)
        plan = make_plan([step])

        result = await process_plan(service, plan)

        assert result == ProcessResult.FAILED
        fabric.assert_called("cap.arr", times=2)

    # -- (11) Multi-step plan: one valid, one invalid -> DEGRADED ------

    @pytest.mark.asyncio
    async def test_mixed_steps_degraded_when_one_fails_schema(self) -> None:
        """Two independent steps in same wave: s1 passes, s2 fails."""
        service, adapters = await orchestrator_for_testing()
        fabric = adapters["fabric"]
        register_capabilities(fabric, "cap.good", "cap.bad")

        fabric.script_result("cap.good", _ok({"summary": "ok"}))
        fabric.script_result("cap.bad", _ok({"wrong": True}))

        s1 = make_step("s1", "cap.good", output_schema=SIMPLE_SCHEMA)
        s2 = make_step("s2", "cap.bad", output_schema=SIMPLE_SCHEMA)
        plan = make_plan([s1, s2])

        result = await process_plan(service, plan)

        # One succeeded, one failed via HARD_STOP -> DEGRADED
        assert result == ProcessResult.DEGRADED
        fabric.assert_called("cap.good", times=1)
        fabric.assert_called("cap.bad", times=2)

    # -- (12) DAG events emitted with correct trace_id -----------------

    @pytest.mark.asyncio
    async def test_dag_events_emitted(self) -> None:
        service, adapters = await orchestrator_for_testing()
        fabric = adapters["fabric"]
        delta = adapters["delta"]
        register_capabilities(fabric, "cap.schema")

        fabric.script_result("cap.schema", _ok({"summary": "ok"}))
        step = make_step("s1", "cap.schema", output_schema=SIMPLE_SCHEMA)
        plan = make_plan([step], trace_id="trace-schema")

        await process_plan(service, plan)

        topics = [t for t, _, _ in delta.emitted]
        assert any("dag.started" in t for t in topics)
        assert any("dag.completed" in t for t in topics)
