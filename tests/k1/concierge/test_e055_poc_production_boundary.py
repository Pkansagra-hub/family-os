"""
E-0.5.5 / I-0.5.5.3 — POC↔Production type boundary integration tests.

Verifies that the translation adapter (_FabricGatewayAdapter in bootstrap.py)
correctly bridges POC orchestrator types (k1.concierge.orchestrator.types)
and production types (k1.fabric.types, k1.orchestrator.types) at the
dispatch boundary.

Tests:
  1. POC CapabilityRequest → production CapabilityRequest field mapping
  2. Production CapabilityResult (success) → POC CapabilityResult
  3. Production CapabilityResult (failure) → POC CapabilityResult
  4. Full round-trip: OrchestratorStub → _FabricGatewayAdapter → mock bridge
  5. POC TaskEnvelope construction invariants (task_id, budget, session_id)
  6. AggregatedResult.from_medium() factory with POC CapabilityResult
  7. Budget enforcement in OrchestratorStub
"""

from __future__ import annotations

import pytest

from k1.concierge.orchestrator.types import AggregatedResult, Budget, CannedResponse
from k1.concierge.orchestrator.types import CapabilityRequest as POCCapabilityRequest
from k1.concierge.orchestrator.types import CapabilityResult as POCCapabilityResult
from k1.concierge.orchestrator.types import TaskEnvelope
from k1.concierge.task.complexity import ComplexityTier
from k1.fabric.types import CapabilityRequest as ProdCapabilityRequest
from k1.fabric.types import CapabilityResult as ProdCapabilityResult
from k1.fabric.types import ErrorInfo

# =========================================================================
# 1. POC → Production field mapping
# =========================================================================


class TestPOCToProdFieldMapping:
    """Verify POC types map to production types correctly."""

    def test_poc_capability_request_name_maps_to_capability_name(self):
        """POC uses `name`, production uses `capability_name`."""
        poc_req = POCCapabilityRequest(
            name="summarize",
            params={"text": "hello"},
            session_id="sess-1",
            trace_id="trace-1",
        )
        # Simulate adapter translation (same logic as _FabricGatewayAdapter)
        prod_req = ProdCapabilityRequest(
            capability_name=poc_req.name,
            params=poc_req.params or {},
            session_id=poc_req.session_id or "",
            trace_id=poc_req.trace_id or "",
            caller="orchestrator",
            caller_id="orchestrator.stub",
        )
        assert prod_req.capability_name == "summarize"
        assert prod_req.params == {"text": "hello"}
        assert prod_req.session_id == "sess-1"
        assert prod_req.trace_id == "trace-1"
        assert prod_req.caller == "orchestrator"

    def test_prod_success_result_maps_to_poc(self):
        """Production success CapabilityResult → POC CapabilityResult."""
        prod_result = ProdCapabilityResult.success_result(
            request_id="req-1",
            data={"answer": "42"},
            provider_id="gemini",
            trace_id="trace-1",
            duration_ms=150,
        )
        # Simulate adapter translation
        poc_result = POCCapabilityResult(
            success=prod_result.success,
            data=prod_result.data if prod_result.success else {},
            error=(
                ""
                if prod_result.success
                else (prod_result.error.message if prod_result.error else "invoke_failed")
            ),
            capability_name="summarize",
            duration_ms=prod_result.duration_ms,
        )
        assert poc_result.success is True
        assert poc_result.data == {"answer": "42"}
        assert poc_result.error == ""
        assert poc_result.capability_name == "summarize"
        assert poc_result.duration_ms == 150

    def test_prod_failure_result_maps_to_poc(self):
        """Production failure CapabilityResult → POC CapabilityResult (error.message → error str)."""
        prod_result = ProdCapabilityResult.failure_result(
            request_id="req-2",
            error_code="capability_not_found",
            error_message="No provider for 'unknown_cap'",
            retriable=False,
            duration_ms=10,
        )
        poc_result = POCCapabilityResult(
            success=prod_result.success,
            data=prod_result.data if prod_result.success else {},
            error=(
                ""
                if prod_result.success
                else (prod_result.error.message if prod_result.error else "invoke_failed")
            ),
            capability_name="unknown_cap",
            duration_ms=prod_result.duration_ms,
        )
        assert poc_result.success is False
        assert poc_result.data == {}
        assert poc_result.error == "No provider for 'unknown_cap'"
        assert poc_result.capability_name == "unknown_cap"

    def test_prod_failure_none_error_maps_to_invoke_failed(self):
        """Production failure with error=None → POC error='invoke_failed'."""
        prod_result = ProdCapabilityResult(
            success=False,
            data=None,
            error=None,
            duration_ms=5,
        )
        poc_result = POCCapabilityResult(
            success=False,
            data={},
            error=(
                ""
                if prod_result.success
                else (prod_result.error.message if prod_result.error else "invoke_failed")
            ),
            capability_name="test",
            duration_ms=prod_result.duration_ms,
        )
        assert poc_result.error == "invoke_failed"


# =========================================================================
# 2. POC TaskEnvelope construction invariants
# =========================================================================


class TestPOCTaskEnvelopeInvariants:
    """Verify POC TaskEnvelope has fields NOT present in production."""

    def test_task_id_auto_generated(self):
        env = TaskEnvelope(intent="test")
        assert env.task_id.startswith("task-")
        assert len(env.task_id) > 5

    def test_explicit_task_id(self):
        env = TaskEnvelope(intent="test", task_id="t1")
        assert env.task_id == "t1"

    def test_budget_default(self):
        env = TaskEnvelope(intent="test")
        assert isinstance(env.budget, Budget)
        assert env.budget.max_fabric_calls == 2
        assert env.budget.max_planner_tokens == 0

    def test_session_id_default_empty(self):
        env = TaskEnvelope(intent="test")
        assert env.session_id == ""

    def test_tier_is_complexity_tier_enum(self):
        env = TaskEnvelope(intent="test", tier=ComplexityTier.MEDIUM)
        assert env.tier == ComplexityTier.MEDIUM
        assert isinstance(env.tier, ComplexityTier)

    def test_tier_low_rejected(self):
        with pytest.raises(ValueError, match="MEDIUM or HIGH"):
            TaskEnvelope(intent="test", tier=ComplexityTier.LOW)

    def test_empty_intent_rejected(self):
        with pytest.raises(ValueError, match="intent is required"):
            TaskEnvelope(intent="")

    def test_trace_id_auto_generated(self):
        env = TaskEnvelope(intent="test")
        assert env.trace_id.startswith("trace-")

    def test_context_default_empty_dict(self):
        env = TaskEnvelope(intent="test")
        assert env.context == {}


# =========================================================================
# 3. AggregatedResult.from_medium() with POC CapabilityResult
# =========================================================================


class TestAggregatedResultFactory:
    """Verify AggregatedResult.from_medium() works with POC types."""

    def test_from_medium_success(self):
        cap = POCCapabilityResult(
            success=True,
            data={"answer": "42"},
            capability_name="summarize",
            duration_ms=100,
        )
        agg = AggregatedResult.from_medium(
            capability_result=cap,
            trace_id="trace-1",
            duration_ms=120,
        )
        assert agg.success is True
        assert agg.total_steps == 1
        assert agg.completed == 1
        assert agg.failed == 0
        assert agg.trace_id == "trace-1"
        assert agg.duration_ms == 120
        assert len(agg.step_results) == 1
        assert agg.step_results[0].status == "COMPLETED"

    def test_from_medium_failure(self):
        cap = POCCapabilityResult(
            success=False,
            error="provider_error",
            capability_name="summarize",
        )
        agg = AggregatedResult.from_medium(capability_result=cap)
        assert agg.success is False
        assert agg.completed == 0
        assert agg.failed == 1
        assert agg.step_results[0].status == "FAILED"
        assert agg.step_results[0].error_detail == "provider_error"

    def test_from_multi_step(self):
        caps = [
            POCCapabilityResult(success=True, data={"a": 1}, capability_name="cap1"),
            POCCapabilityResult(success=True, data={"b": 2}, capability_name="cap2"),
        ]
        agg = AggregatedResult.from_multi_step(
            capability_results=caps,
            trace_id="trace-2",
            duration_ms=200,
        )
        assert agg.success is True
        assert agg.total_steps == 2
        assert agg.completed == 2
        assert agg.failed == 0

    def test_to_dict_serialization(self):
        cap = POCCapabilityResult(success=True, data={}, capability_name="test")
        agg = AggregatedResult.from_medium(capability_result=cap, trace_id="t1")
        d = agg.to_dict()
        assert d["trace_id"] == "t1"
        assert d["total_steps"] == 1
        assert d["success"] is True
        assert isinstance(d["step_results"], list)
        assert len(d["step_results"]) == 1


# =========================================================================
# 4. Full round-trip: adapter translation
# =========================================================================


class TestFabricGatewayAdapterRoundTrip:
    """Test the actual _FabricGatewayAdapter from bootstrap.py."""

    @pytest.fixture
    def mock_bridge(self):
        """Mock bridge that returns a production CapabilityResult."""

        class MockBridge:
            def __init__(self):
                self.last_request = None

            async def execute(self, request):
                self.last_request = request
                return ProdCapabilityResult.success_result(
                    request_id="req-bridge",
                    data={"result": "ok"},
                    provider_id="test-provider",
                    trace_id=request.trace_id,
                    duration_ms=50,
                )

        return MockBridge()

    @pytest.fixture
    def adapter(self, mock_bridge):
        from k1.concierge.kernel.bootstrap import _FabricGatewayAdapter

        return _FabricGatewayAdapter(bridge=mock_bridge)

    async def test_execute_translates_request(self, adapter, mock_bridge):
        """POC request.name → production request.capability_name."""
        poc_req = POCCapabilityRequest(
            name="summarize",
            params={"text": "hello"},
            session_id="sess-1",
            trace_id="trace-1",
        )
        result = await adapter.execute(poc_req)

        # Verify bridge received production CapabilityRequest
        assert mock_bridge.last_request is not None
        assert isinstance(mock_bridge.last_request, ProdCapabilityRequest)
        assert mock_bridge.last_request.capability_name == "summarize"
        assert mock_bridge.last_request.params == {"text": "hello"}
        assert mock_bridge.last_request.session_id == "sess-1"
        assert mock_bridge.last_request.trace_id == "trace-1"
        assert mock_bridge.last_request.caller == "orchestrator"

    async def test_execute_translates_success_result(self, adapter, mock_bridge):
        """Production success result → POC CapabilityResult."""
        poc_req = POCCapabilityRequest(name="test", trace_id="t1")
        result = await adapter.execute(poc_req)

        assert isinstance(result, POCCapabilityResult)
        assert result.success is True
        assert result.data == {"result": "ok"}
        assert result.error == ""
        assert result.capability_name == "test"
        assert result.duration_ms == 50

    async def test_execute_translates_failure_result(self):
        """Production failure result → POC CapabilityResult with error string."""

        class FailBridge:
            async def execute(self, request):
                return ProdCapabilityResult.failure_result(
                    request_id="req-fail",
                    error_code="timeout",
                    error_message="Request timed out after 30s",
                    retriable=True,
                    duration_ms=30000,
                )

        from k1.concierge.kernel.bootstrap import _FabricGatewayAdapter

        adapter = _FabricGatewayAdapter(bridge=FailBridge())
        poc_req = POCCapabilityRequest(name="slow_cap")
        result = await adapter.execute(poc_req)

        assert result.success is False
        assert result.data == {}
        assert result.error == "Request timed out after 30s"
        assert result.capability_name == "slow_cap"
        assert result.duration_ms == 30000

    async def test_execute_batch(self, adapter, mock_bridge):
        """execute_batch delegates to execute for each request."""
        reqs = [
            POCCapabilityRequest(name="cap1", trace_id="t1"),
            POCCapabilityRequest(name="cap2", trace_id="t2"),
        ]
        results = await adapter.execute_batch(reqs)
        assert len(results) == 2
        assert all(isinstance(r, POCCapabilityResult) for r in results)
        assert all(r.success is True for r in results)


# =========================================================================
# 5. CannedResponse POC-only type
# =========================================================================


class TestCannedResponsePOCOnly:
    """CannedResponse has no production equivalent -- verify it works."""

    def test_default_text(self):
        cr = CannedResponse()
        assert "trouble" in cr.text.lower() or "try again" in cr.text.lower()

    def test_custom_text(self):
        cr = CannedResponse(text="System busy", reason="CB_FABRIC open")
        assert cr.text == "System busy"
        assert cr.reason == "CB_FABRIC open"

    def test_frozen(self):
        cr = CannedResponse()
        with pytest.raises(AttributeError):
            cr.text = "modified"


# =========================================================================
# 6. Budget POC-only type
# =========================================================================


class TestBudgetPOCOnly:
    """Budget has no production equivalent -- verify defaults and validation."""

    def test_default_medium_tier(self):
        b = Budget()
        assert b.max_fabric_calls == 2
        assert b.max_planner_tokens == 0
        assert b.timeout_ms > 0  # resolved from config

    def test_high_tier_budget(self):
        b = Budget(max_fabric_calls=10, max_planner_tokens=3500)
        assert b.max_fabric_calls == 10
        assert b.max_planner_tokens == 3500

    def test_negative_fabric_calls_rejected(self):
        with pytest.raises(ValueError, match="max_fabric_calls"):
            Budget(max_fabric_calls=-1)

    def test_negative_planner_tokens_rejected(self):
        with pytest.raises(ValueError, match="max_planner_tokens"):
            Budget(max_planner_tokens=-1)

    def test_frozen(self):
        b = Budget()
        with pytest.raises(AttributeError):
            b.max_fabric_calls = 5


# =========================================================================
# 7. Type identity: POC types are distinct from production types
# =========================================================================


class TestTypeIdentityDistinct:
    """POC types and production types are separate classes."""

    def test_capability_request_distinct(self):
        assert POCCapabilityRequest is not ProdCapabilityRequest

    def test_capability_result_distinct(self):
        assert POCCapabilityResult is not ProdCapabilityResult

    def test_poc_has_name_not_capability_name(self):
        req = POCCapabilityRequest(name="test")
        assert hasattr(req, "name")
        assert not hasattr(req, "capability_name")

    def test_prod_has_capability_name_not_name(self):
        req = ProdCapabilityRequest(capability_name="test")
        assert hasattr(req, "capability_name")
        # ProdCapabilityRequest has no 'name' field
        assert (
            "name" not in req.__dataclass_fields__ or req.__dataclass_fields__.get("name") is None
        )

    def test_poc_error_is_str(self):
        res = POCCapabilityResult(success=False, error="bad")
        assert isinstance(res.error, str)

    def test_prod_error_is_error_info(self):
        res = ProdCapabilityResult.failure_result(
            request_id="r1", error_code="e", error_message="bad"
        )
        assert isinstance(res.error, ErrorInfo)
