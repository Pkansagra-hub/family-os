"""
Tests for DiscoverCapabilitiesHandler and FindPromptsHandler (4.5.3).

Validates two MCP discovery tool wrappers that expose Fabric retrieval
as capability discovery tools for Planner consumption.

Test strategy:
  - Real test adapter (TestRetrievalEngine) -- no mocks
  - Call tracking for delegation verification
  - Input validation edge cases (missing, invalid types, empty)
  - Happy path with all params and with defaults
  - Error propagation (engine exceptions -> internal_error)
  - Result structure (CapabilityResult fields, data mapping)
  - Protocol compliance (RetrievalLike structural subtyping)
  - Timing propagation (retrieval_time_ms passthrough)

References:
  - fabric-implementation-plan.md Issue 4.5.3
  - No-Mock Testing Strategy
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from k1.fabric.core.discovery_tools import (
    DEFAULT_DISCOVER_TOP_K,
    DEFAULT_FIND_PROMPTS_TOP_K,
    DISCOVER_CAPABILITIES_NAME,
    DISCOVER_CAPABILITIES_PROVIDER_ID,
    FIND_PROMPTS_NAME,
    FIND_PROMPTS_PROVIDER_ID,
    DiscoverCapabilitiesHandler,
    DiscoveryToolError,
    FindPromptsHandler,
    RetrievalLike,
)
from k1.fabric.types import CapabilityContract, CapabilityRequest, RetrievalResult, ScoredCapability

# ---------------------------------------------------------------------------
# Test Adapter -- TestRetrievalEngine
# ---------------------------------------------------------------------------


class TestRetrievalEngine:
    """
    Test adapter for RetrievalLike protocol.

    Configurable return values + call tracking.
    Satisfies RetrievalLike protocol via structural subtyping.
    """

    def __init__(
        self,
        discover_result: Optional[RetrievalResult] = None,
        find_result: Optional[RetrievalResult] = None,
        discover_error: Optional[Exception] = None,
        find_error: Optional[Exception] = None,
    ) -> None:
        self.discover_result = discover_result or RetrievalResult()
        self.find_result = find_result or RetrievalResult()
        self.discover_error = discover_error
        self.find_error = find_error
        self.discover_calls: List[Dict[str, Any]] = []
        self.find_calls: List[Dict[str, Any]] = []

    def discover_capabilities(
        self,
        domain: Optional[List[str]] = None,
        intent: str = "",
        safety_band: str = "GREEN",
        session_context: Optional[Dict[str, Any]] = None,
        top_k: Optional[int] = None,
    ) -> RetrievalResult:
        self.discover_calls.append(
            {
                "domain": domain,
                "intent": intent,
                "safety_band": safety_band,
                "session_context": session_context,
                "top_k": top_k,
            }
        )
        if self.discover_error:
            raise self.discover_error
        return self.discover_result

    def find_relevant_prompts(
        self,
        intent: str = "",
        domain: Optional[List[str]] = None,
        safety_band: str = "GREEN",
        top_k: Optional[int] = None,
    ) -> RetrievalResult:
        self.find_calls.append(
            {
                "intent": intent,
                "domain": domain,
                "safety_band": safety_band,
                "top_k": top_k,
            }
        )
        if self.find_error:
            raise self.find_error
        return self.find_result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_contract(
    name: str = "tool.read.test_capability",
    version: str = "1.0.0",
    domain: Optional[List[str]] = None,
    description: str = "Test capability",
    provider_type: str = "MCP",
    safety_band_min: str = "GREEN",
) -> CapabilityContract:
    """Create minimal CapabilityContract for testing."""
    return CapabilityContract(
        name=name,
        version=version,
        domain=domain or ["TEST"],
        description=description,
        provider_type=provider_type,
        safety_band_min=safety_band_min,
    )


def _make_scored(
    name: str = "tool.read.test_capability",
    score: float = 0.85,
    domain: Optional[List[str]] = None,
) -> ScoredCapability:
    """Create ScoredCapability with a test contract."""
    return ScoredCapability(
        contract=_make_contract(name=name, domain=domain),
        score=score,
    )


def _make_retrieval_result(
    capabilities: Optional[List[ScoredCapability]] = None,
    total_matched: int = 0,
    query_latency_ms: int = 5,
    query_intent: str = "test intent",
) -> RetrievalResult:
    """Create RetrievalResult with configurable data."""
    caps = capabilities or []
    return RetrievalResult(
        capabilities=caps,
        total_matched=total_matched or len(caps),
        query_latency_ms=query_latency_ms,
        query_intent=query_intent,
    )


def _make_request(
    params: Dict[str, Any],
    capability_name: str = DISCOVER_CAPABILITIES_NAME,
    request_id: str = "req-001",
    trace_id: str = "trace-001",
    session_id: str = "session-001",
) -> CapabilityRequest:
    """Create CapabilityRequest for testing."""
    return CapabilityRequest(
        request_id=request_id,
        capability_name=capability_name,
        params=params,
        trace_id=trace_id,
        session_id=session_id,
        caller="test",
    )


# ===========================================================================
# DiscoverCapabilitiesHandler Tests
# ===========================================================================


class TestDiscoverCapabilitiesHandlerHappyPath:
    """Happy path tests for DiscoverCapabilitiesHandler."""

    def test_discover_with_all_params(self) -> None:
        """Full param set: intent, domain, top_k, safety_band."""
        scored = [
            _make_scored("tool.read.health_check", 0.95, ["HEALTH"]),
            _make_scored("tool.read.health_metrics", 0.80, ["HEALTH"]),
        ]
        engine = TestRetrievalEngine(
            discover_result=_make_retrieval_result(scored, total_matched=5, query_latency_ms=12),
        )
        handler = DiscoverCapabilitiesHandler(engine)

        request = _make_request(
            params={
                "intent": "find health monitoring tools",
                "domain": ["HEALTH"],
                "top_k": 3,
                "safety_band": "AMBER",
            },
        )
        result = handler.execute(request)

        assert result.success is True
        assert result.request_id == "req-001"
        assert result.trace_id == "trace-001"
        assert result.provider_id == DISCOVER_CAPABILITIES_PROVIDER_ID
        assert result.data is not None
        assert len(result.data["capabilities"]) == 2
        assert result.data["total_matched"] == 5
        assert result.data["query_latency_ms"] == 12
        assert result.retrieval_time_ms == 12

    def test_discover_delegates_correct_params(self) -> None:
        """Verify delegation passes exact params to retrieval engine."""
        engine = TestRetrievalEngine()
        handler = DiscoverCapabilitiesHandler(engine)

        request = _make_request(
            params={
                "intent": "find weather tools",
                "domain": ["WEATHER", "PLANNING"],
                "top_k": 7,
                "safety_band": "GREEN",
            },
        )
        handler.execute(request)

        assert len(engine.discover_calls) == 1
        call = engine.discover_calls[0]
        assert call["intent"] == "find weather tools"
        assert call["domain"] == ["WEATHER", "PLANNING"]
        assert call["top_k"] == 7
        assert call["safety_band"] == "GREEN"
        assert call["session_context"] is None

    def test_discover_with_defaults(self) -> None:
        """Only required params: intent and domain. top_k and safety_band default."""
        engine = TestRetrievalEngine()
        handler = DiscoverCapabilitiesHandler(engine)

        request = _make_request(
            params={"intent": "booking tool", "domain": ["FOOD"]},
        )
        result = handler.execute(request)

        assert result.success is True
        call = engine.discover_calls[0]
        assert call["top_k"] == DEFAULT_DISCOVER_TOP_K
        assert call["safety_band"] == "GREEN"

    def test_discover_returns_empty_results(self) -> None:
        """No matching capabilities -> success with empty list."""
        engine = TestRetrievalEngine(
            discover_result=_make_retrieval_result([], total_matched=0),
        )
        handler = DiscoverCapabilitiesHandler(engine)

        request = _make_request(
            params={"intent": "quantum computing", "domain": ["QUANTUM"]},
        )
        result = handler.execute(request)

        assert result.success is True
        assert result.data is not None
        assert len(result.data["capabilities"]) == 0
        assert result.data["total_matched"] == 0

    def test_discover_result_contains_contract_details(self) -> None:
        """Result data includes full contract info in each scored capability."""
        contract = _make_contract(
            name="tool.read.medication_lookup",
            version="2.1.0",
            domain=["HEALTH", "PHARMACOLOGY"],
            description="Look up medication info",
            provider_type="MCP",
            safety_band_min="GREEN",
        )
        scored = [ScoredCapability(contract=contract, score=0.92)]
        engine = TestRetrievalEngine(
            discover_result=_make_retrieval_result(scored, total_matched=1),
        )
        handler = DiscoverCapabilitiesHandler(engine)

        request = _make_request(
            params={"intent": "medication info", "domain": ["HEALTH"]},
        )
        result = handler.execute(request)

        assert result.success is True
        cap_data = result.data["capabilities"][0]
        assert cap_data["score"] == 0.92
        assert cap_data["contract"]["name"] == "tool.read.medication_lookup"
        assert cap_data["contract"]["version"] == "2.1.0"

    def test_discover_timing_propagation(self) -> None:
        """duration_ms and retrieval_time_ms are populated."""
        engine = TestRetrievalEngine(
            discover_result=_make_retrieval_result(query_latency_ms=15),
        )
        handler = DiscoverCapabilitiesHandler(engine)

        request = _make_request(
            params={"intent": "test", "domain": ["TEST"]},
        )
        result = handler.execute(request)

        assert result.success is True
        assert result.retrieval_time_ms == 15
        assert result.duration_ms >= 0


class TestDiscoverCapabilitiesHandlerValidation:
    """Input validation tests for DiscoverCapabilitiesHandler."""

    def test_missing_intent(self) -> None:
        """No intent param -> validation_failed."""
        engine = TestRetrievalEngine()
        handler = DiscoverCapabilitiesHandler(engine)

        request = _make_request(params={"domain": ["HEALTH"]})
        result = handler.execute(request)

        assert result.success is False
        assert result.error is not None
        assert result.error.code == "validation_failed"
        assert "'intent'" in result.error.message

    def test_empty_intent(self) -> None:
        """Empty string intent -> validation_failed."""
        engine = TestRetrievalEngine()
        handler = DiscoverCapabilitiesHandler(engine)

        request = _make_request(params={"intent": "", "domain": ["TEST"]})
        result = handler.execute(request)

        assert result.success is False
        assert result.error is not None
        assert result.error.code == "validation_failed"
        assert "'intent'" in result.error.message

    def test_whitespace_only_intent(self) -> None:
        """Whitespace-only intent -> validation_failed."""
        engine = TestRetrievalEngine()
        handler = DiscoverCapabilitiesHandler(engine)

        request = _make_request(params={"intent": "   ", "domain": ["TEST"]})
        result = handler.execute(request)

        assert result.success is False
        assert result.error is not None
        assert result.error.code == "validation_failed"

    def test_intent_wrong_type(self) -> None:
        """Non-string intent -> validation_failed."""
        engine = TestRetrievalEngine()
        handler = DiscoverCapabilitiesHandler(engine)

        request = _make_request(params={"intent": 42, "domain": ["TEST"]})
        result = handler.execute(request)

        assert result.success is False
        assert result.error is not None
        assert result.error.code == "validation_failed"

    def test_missing_domain(self) -> None:
        """No domain param -> validation_failed."""
        engine = TestRetrievalEngine()
        handler = DiscoverCapabilitiesHandler(engine)

        request = _make_request(params={"intent": "search"})
        result = handler.execute(request)

        assert result.success is False
        assert result.error is not None
        assert result.error.code == "validation_failed"
        assert "'domain'" in result.error.message

    def test_empty_domain(self) -> None:
        """Empty domain list -> validation_failed."""
        engine = TestRetrievalEngine()
        handler = DiscoverCapabilitiesHandler(engine)

        request = _make_request(params={"intent": "search", "domain": []})
        result = handler.execute(request)

        assert result.success is False
        assert result.error is not None
        assert result.error.code == "validation_failed"
        assert "'domain'" in result.error.message

    def test_domain_wrong_type(self) -> None:
        """Non-list domain -> validation_failed."""
        engine = TestRetrievalEngine()
        handler = DiscoverCapabilitiesHandler(engine)

        request = _make_request(params={"intent": "search", "domain": "HEALTH"})
        result = handler.execute(request)

        assert result.success is False
        assert result.error is not None
        assert result.error.code == "validation_failed"

    def test_domain_non_string_tag(self) -> None:
        """Non-string tag in domain list -> validation_failed."""
        engine = TestRetrievalEngine()
        handler = DiscoverCapabilitiesHandler(engine)

        request = _make_request(params={"intent": "search", "domain": [123]})
        result = handler.execute(request)

        assert result.success is False
        assert result.error is not None
        assert result.error.code == "validation_failed"
        assert "string" in result.error.message.lower()

    def test_invalid_top_k_not_int(self) -> None:
        """Non-int top_k -> validation_failed."""
        engine = TestRetrievalEngine()
        handler = DiscoverCapabilitiesHandler(engine)

        request = _make_request(
            params={"intent": "search", "domain": ["TEST"], "top_k": "five"},
        )
        result = handler.execute(request)

        assert result.success is False
        assert result.error is not None
        assert result.error.code == "validation_failed"
        assert "'top_k'" in result.error.message

    def test_invalid_top_k_zero(self) -> None:
        """Zero top_k -> validation_failed."""
        engine = TestRetrievalEngine()
        handler = DiscoverCapabilitiesHandler(engine)

        request = _make_request(
            params={"intent": "search", "domain": ["TEST"], "top_k": 0},
        )
        result = handler.execute(request)

        assert result.success is False
        assert result.error is not None
        assert result.error.code == "validation_failed"

    def test_invalid_top_k_negative(self) -> None:
        """Negative top_k -> validation_failed."""
        engine = TestRetrievalEngine()
        handler = DiscoverCapabilitiesHandler(engine)

        request = _make_request(
            params={"intent": "search", "domain": ["TEST"], "top_k": -1},
        )
        result = handler.execute(request)

        assert result.success is False
        assert result.error is not None
        assert result.error.code == "validation_failed"

    def test_invalid_safety_band_empty(self) -> None:
        """Empty safety_band -> validation_failed."""
        engine = TestRetrievalEngine()
        handler = DiscoverCapabilitiesHandler(engine)

        request = _make_request(
            params={"intent": "search", "domain": ["TEST"], "safety_band": ""},
        )
        result = handler.execute(request)

        assert result.success is False
        assert result.error is not None
        assert result.error.code == "validation_failed"

    def test_invalid_safety_band_non_string(self) -> None:
        """Non-string safety_band -> validation_failed."""
        engine = TestRetrievalEngine()
        handler = DiscoverCapabilitiesHandler(engine)

        request = _make_request(
            params={"intent": "search", "domain": ["TEST"], "safety_band": 42},
        )
        result = handler.execute(request)

        assert result.success is False
        assert result.error is not None
        assert result.error.code == "validation_failed"

    def test_missing_both_required_reports_multiple_errors(self) -> None:
        """Missing both intent and domain -> multiple errors in message."""
        engine = TestRetrievalEngine()
        handler = DiscoverCapabilitiesHandler(engine)

        request = _make_request(params={})
        result = handler.execute(request)

        assert result.success is False
        assert result.error is not None
        assert result.error.code == "validation_failed"
        assert "2 issue(s)" in result.error.message

    def test_validation_failure_preserves_trace_id(self) -> None:
        """Validation failure result preserves request_id and trace_id."""
        engine = TestRetrievalEngine()
        handler = DiscoverCapabilitiesHandler(engine)

        request = _make_request(
            params={},
            request_id="req-fail",
            trace_id="trace-fail",
        )
        result = handler.execute(request)

        assert result.success is False
        assert result.request_id == "req-fail"
        assert result.trace_id == "trace-fail"

    def test_no_delegation_on_validation_failure(self) -> None:
        """Engine not called when inputs are invalid."""
        engine = TestRetrievalEngine()
        handler = DiscoverCapabilitiesHandler(engine)

        request = _make_request(params={})
        handler.execute(request)

        assert len(engine.discover_calls) == 0


class TestDiscoverCapabilitiesHandlerErrors:
    """Error handling tests for DiscoverCapabilitiesHandler."""

    def test_engine_runtime_error_returns_internal_error(self) -> None:
        """RuntimeError from engine -> internal_error."""
        engine = TestRetrievalEngine(
            discover_error=RuntimeError("embedding index unavailable"),
        )
        handler = DiscoverCapabilitiesHandler(engine)

        request = _make_request(
            params={"intent": "test", "domain": ["TEST"]},
        )
        result = handler.execute(request)

        assert result.success is False
        assert result.error is not None
        assert result.error.code == "internal_error"
        assert "RuntimeError" in result.error.message
        assert "embedding index unavailable" in result.error.message

    def test_engine_value_error_returns_internal_error(self) -> None:
        """ValueError from engine -> internal_error."""
        engine = TestRetrievalEngine(
            discover_error=ValueError("invalid embedding dimension"),
        )
        handler = DiscoverCapabilitiesHandler(engine)

        request = _make_request(
            params={"intent": "test", "domain": ["TEST"]},
        )
        result = handler.execute(request)

        assert result.success is False
        assert result.error is not None
        assert result.error.code == "internal_error"
        assert "ValueError" in result.error.message

    def test_engine_error_preserves_trace(self) -> None:
        """Internal error preserves request_id and trace_id."""
        engine = TestRetrievalEngine(discover_error=Exception("boom"))
        handler = DiscoverCapabilitiesHandler(engine)

        request = _make_request(
            params={"intent": "test", "domain": ["TEST"]},
            request_id="req-err",
            trace_id="trace-err",
        )
        result = handler.execute(request)

        assert result.success is False
        assert result.request_id == "req-err"
        assert result.trace_id == "trace-err"


# ===========================================================================
# FindPromptsHandler Tests
# ===========================================================================


class TestFindPromptsHandlerHappyPath:
    """Happy path tests for FindPromptsHandler."""

    def test_find_with_all_params(self) -> None:
        """Full param set: intent, domain, top_k."""
        scored = [
            _make_scored("prompt.health.vitals_summary", 0.90, ["HEALTH"]),
            _make_scored("prompt.health.medication_review", 0.75, ["HEALTH"]),
        ]
        engine = TestRetrievalEngine(
            find_result=_make_retrieval_result(scored, total_matched=3, query_latency_ms=8),
        )
        handler = FindPromptsHandler(engine)

        request = _make_request(
            params={
                "intent": "summarize patient vitals",
                "domain": ["HEALTH"],
                "top_k": 2,
            },
            capability_name=FIND_PROMPTS_NAME,
        )
        result = handler.execute(request)

        assert result.success is True
        assert result.request_id == "req-001"
        assert result.trace_id == "trace-001"
        assert result.provider_id == FIND_PROMPTS_PROVIDER_ID
        assert result.data is not None
        assert len(result.data["capabilities"]) == 2
        assert result.data["total_matched"] == 3
        assert result.retrieval_time_ms == 8

    def test_find_delegates_correct_params(self) -> None:
        """Verify delegation passes exact params to retrieval engine."""
        engine = TestRetrievalEngine()
        handler = FindPromptsHandler(engine)

        request = _make_request(
            params={
                "intent": "create greeting template",
                "domain": ["SOCIAL"],
                "top_k": 3,
            },
            capability_name=FIND_PROMPTS_NAME,
        )
        handler.execute(request)

        assert len(engine.find_calls) == 1
        call = engine.find_calls[0]
        assert call["intent"] == "create greeting template"
        assert call["domain"] == ["SOCIAL"]
        assert call["top_k"] == 3
        assert call["safety_band"] == "GREEN"

    def test_find_with_defaults_intent_only(self) -> None:
        """Only required param: intent. domain=None, top_k defaults to 5."""
        engine = TestRetrievalEngine()
        handler = FindPromptsHandler(engine)

        request = _make_request(
            params={"intent": "find a greeting prompt"},
            capability_name=FIND_PROMPTS_NAME,
        )
        result = handler.execute(request)

        assert result.success is True
        call = engine.find_calls[0]
        assert call["domain"] is None
        assert call["top_k"] == DEFAULT_FIND_PROMPTS_TOP_K

    def test_find_returns_empty_results(self) -> None:
        """No matching prompts -> success with empty list."""
        engine = TestRetrievalEngine(
            find_result=_make_retrieval_result([], total_matched=0),
        )
        handler = FindPromptsHandler(engine)

        request = _make_request(
            params={"intent": "nonexistent prompt"},
            capability_name=FIND_PROMPTS_NAME,
        )
        result = handler.execute(request)

        assert result.success is True
        assert result.data is not None
        assert len(result.data["capabilities"]) == 0

    def test_find_result_contains_prompt_info(self) -> None:
        """Result includes scored capability details."""
        contract = _make_contract(
            name="prompt.health.daily_summary",
            version="1.0.0",
            domain=["HEALTH"],
            description="Daily health summary template",
            provider_type="prompt",
        )
        scored = [ScoredCapability(contract=contract, score=0.88)]
        engine = TestRetrievalEngine(
            find_result=_make_retrieval_result(scored, total_matched=1),
        )
        handler = FindPromptsHandler(engine)

        request = _make_request(
            params={"intent": "daily summary"},
            capability_name=FIND_PROMPTS_NAME,
        )
        result = handler.execute(request)

        assert result.success is True
        cap_data = result.data["capabilities"][0]
        assert cap_data["score"] == 0.88
        assert cap_data["contract"]["name"] == "prompt.health.daily_summary"

    def test_find_always_passes_green_safety_band(self) -> None:
        """find_prompts always delegates with GREEN safety band."""
        engine = TestRetrievalEngine()
        handler = FindPromptsHandler(engine)

        request = _make_request(
            params={"intent": "test"},
            capability_name=FIND_PROMPTS_NAME,
        )
        handler.execute(request)

        call = engine.find_calls[0]
        assert call["safety_band"] == "GREEN"

    def test_find_timing_propagation(self) -> None:
        """duration_ms and retrieval_time_ms are populated."""
        engine = TestRetrievalEngine(
            find_result=_make_retrieval_result(query_latency_ms=10),
        )
        handler = FindPromptsHandler(engine)

        request = _make_request(
            params={"intent": "test"},
            capability_name=FIND_PROMPTS_NAME,
        )
        result = handler.execute(request)

        assert result.success is True
        assert result.retrieval_time_ms == 10
        assert result.duration_ms >= 0


class TestFindPromptsHandlerValidation:
    """Input validation tests for FindPromptsHandler."""

    def test_missing_intent(self) -> None:
        """No intent param -> validation_failed."""
        engine = TestRetrievalEngine()
        handler = FindPromptsHandler(engine)

        request = _make_request(
            params={"domain": ["HEALTH"]},
            capability_name=FIND_PROMPTS_NAME,
        )
        result = handler.execute(request)

        assert result.success is False
        assert result.error is not None
        assert result.error.code == "validation_failed"
        assert "'intent'" in result.error.message

    def test_empty_intent(self) -> None:
        """Empty string intent -> validation_failed."""
        engine = TestRetrievalEngine()
        handler = FindPromptsHandler(engine)

        request = _make_request(
            params={"intent": ""},
            capability_name=FIND_PROMPTS_NAME,
        )
        result = handler.execute(request)

        assert result.success is False
        assert result.error is not None
        assert result.error.code == "validation_failed"

    def test_intent_wrong_type(self) -> None:
        """Non-string intent -> validation_failed."""
        engine = TestRetrievalEngine()
        handler = FindPromptsHandler(engine)

        request = _make_request(
            params={"intent": ["not", "a", "string"]},
            capability_name=FIND_PROMPTS_NAME,
        )
        result = handler.execute(request)

        assert result.success is False
        assert result.error is not None
        assert result.error.code == "validation_failed"

    def test_domain_wrong_type(self) -> None:
        """Non-list domain -> validation_failed."""
        engine = TestRetrievalEngine()
        handler = FindPromptsHandler(engine)

        request = _make_request(
            params={"intent": "test", "domain": "HEALTH"},
            capability_name=FIND_PROMPTS_NAME,
        )
        result = handler.execute(request)

        assert result.success is False
        assert result.error is not None
        assert result.error.code == "validation_failed"
        assert "'domain'" in result.error.message

    def test_domain_non_string_tag(self) -> None:
        """Non-string tag in domain list -> validation_failed."""
        engine = TestRetrievalEngine()
        handler = FindPromptsHandler(engine)

        request = _make_request(
            params={"intent": "test", "domain": [True]},
            capability_name=FIND_PROMPTS_NAME,
        )
        result = handler.execute(request)

        assert result.success is False
        assert result.error is not None
        assert result.error.code == "validation_failed"

    def test_invalid_top_k_not_int(self) -> None:
        """Non-int top_k -> validation_failed."""
        engine = TestRetrievalEngine()
        handler = FindPromptsHandler(engine)

        request = _make_request(
            params={"intent": "test", "top_k": 3.5},
            capability_name=FIND_PROMPTS_NAME,
        )
        result = handler.execute(request)

        assert result.success is False
        assert result.error is not None
        assert result.error.code == "validation_failed"
        assert "'top_k'" in result.error.message

    def test_invalid_top_k_zero(self) -> None:
        """Zero top_k -> validation_failed."""
        engine = TestRetrievalEngine()
        handler = FindPromptsHandler(engine)

        request = _make_request(
            params={"intent": "test", "top_k": 0},
            capability_name=FIND_PROMPTS_NAME,
        )
        result = handler.execute(request)

        assert result.success is False
        assert result.error is not None
        assert result.error.code == "validation_failed"

    def test_validation_preserves_trace(self) -> None:
        """Validation failure preserves request_id and trace_id."""
        engine = TestRetrievalEngine()
        handler = FindPromptsHandler(engine)

        request = _make_request(
            params={},
            capability_name=FIND_PROMPTS_NAME,
            request_id="req-fp-fail",
            trace_id="trace-fp-fail",
        )
        result = handler.execute(request)

        assert result.success is False
        assert result.request_id == "req-fp-fail"
        assert result.trace_id == "trace-fp-fail"

    def test_no_delegation_on_validation_failure(self) -> None:
        """Engine not called when inputs are invalid."""
        engine = TestRetrievalEngine()
        handler = FindPromptsHandler(engine)

        request = _make_request(
            params={},
            capability_name=FIND_PROMPTS_NAME,
        )
        handler.execute(request)

        assert len(engine.find_calls) == 0


class TestFindPromptsHandlerErrors:
    """Error handling tests for FindPromptsHandler."""

    def test_engine_error_returns_internal_error(self) -> None:
        """Exception from engine -> internal_error."""
        engine = TestRetrievalEngine(
            find_error=RuntimeError("index corrupted"),
        )
        handler = FindPromptsHandler(engine)

        request = _make_request(
            params={"intent": "test"},
            capability_name=FIND_PROMPTS_NAME,
        )
        result = handler.execute(request)

        assert result.success is False
        assert result.error is not None
        assert result.error.code == "internal_error"
        assert "RuntimeError" in result.error.message
        assert "index corrupted" in result.error.message

    def test_engine_error_preserves_trace(self) -> None:
        """Internal error preserves request_id and trace_id."""
        engine = TestRetrievalEngine(find_error=Exception("boom"))
        handler = FindPromptsHandler(engine)

        request = _make_request(
            params={"intent": "test"},
            capability_name=FIND_PROMPTS_NAME,
            request_id="req-fp-err",
            trace_id="trace-fp-err",
        )
        result = handler.execute(request)

        assert result.success is False
        assert result.request_id == "req-fp-err"
        assert result.trace_id == "trace-fp-err"


# ===========================================================================
# Protocol & Constants Tests
# ===========================================================================


class TestRetrievalLikeProtocol:
    """Protocol compliance tests for RetrievalLike."""

    def test_test_adapter_satisfies_protocol(self) -> None:
        """TestRetrievalEngine satisfies RetrievalLike at runtime."""
        engine = TestRetrievalEngine()
        assert isinstance(engine, RetrievalLike)

    def test_incomplete_adapter_does_not_satisfy(self) -> None:
        """Object missing methods does NOT satisfy RetrievalLike."""

        class Incomplete:
            def discover_capabilities(self) -> None:
                pass

        obj = Incomplete()
        assert not isinstance(obj, RetrievalLike)


class TestDiscoveryToolConstants:
    """Verify constant values match contract YAMLs."""

    def test_discover_capabilities_name(self) -> None:
        assert DISCOVER_CAPABILITIES_NAME == "tool.read.discover_capabilities"

    def test_discover_capabilities_provider_id(self) -> None:
        assert DISCOVER_CAPABILITIES_PROVIDER_ID == "discover_capabilities_handler"

    def test_find_prompts_name(self) -> None:
        assert FIND_PROMPTS_NAME == "tool.read.find_prompts"

    def test_find_prompts_provider_id(self) -> None:
        assert FIND_PROMPTS_PROVIDER_ID == "find_prompts_handler"

    def test_default_discover_top_k(self) -> None:
        assert DEFAULT_DISCOVER_TOP_K == 10

    def test_default_find_prompts_top_k(self) -> None:
        assert DEFAULT_FIND_PROMPTS_TOP_K == 5


class TestDiscoveryToolError:
    """Tests for DiscoveryToolError exception."""

    def test_single_error(self) -> None:
        err = DiscoveryToolError(["missing intent"])
        assert err.errors == ["missing intent"]
        assert "1 issue(s)" in str(err)
        assert "missing intent" in str(err)

    def test_multiple_errors(self) -> None:
        err = DiscoveryToolError(["error a", "error b"])
        assert len(err.errors) == 2
        assert "2 issue(s)" in str(err)

    def test_is_exception(self) -> None:
        err = DiscoveryToolError(["test"])
        assert isinstance(err, Exception)


class TestHandlerRepr:
    """Tests for handler __repr__."""

    def test_discover_handler_repr(self) -> None:
        engine = TestRetrievalEngine()
        handler = DiscoverCapabilitiesHandler(engine)
        r = repr(handler)
        assert "DiscoverCapabilitiesHandler" in r

    def test_find_prompts_handler_repr(self) -> None:
        engine = TestRetrievalEngine()
        handler = FindPromptsHandler(engine)
        r = repr(handler)
        assert "FindPromptsHandler" in r


class TestCoreExports:
    """Verify all 4.5.3 exports are accessible from k1.fabric.core."""

    def test_all_discovery_exports(self) -> None:
        from k1.fabric import core

        expected = [
            "DiscoverCapabilitiesHandler",
            "FindPromptsHandler",
            "DiscoveryToolError",
            "DISCOVER_CAPABILITIES_NAME",
            "DISCOVER_CAPABILITIES_PROVIDER_ID",
            "FIND_PROMPTS_NAME",
            "FIND_PROMPTS_PROVIDER_ID",
            "DEFAULT_DISCOVER_TOP_K",
            "DEFAULT_FIND_PROMPTS_TOP_K",
        ]
        for name in expected:
            assert hasattr(core, name), f"Missing export: {name}"
            assert name in core.__all__, f"Not in __all__: {name}"
