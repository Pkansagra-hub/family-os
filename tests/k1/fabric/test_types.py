"""
Epic 6.2.10 -- Test Core Types.

Tests all dataclasses, enums, to_dict()/from_dict() roundtrips,
and factory methods defined in k1.fabric.types.

Covers:
  - Enums: WFQPriority, RequestStatus, Tier, SafetyBand, Availability,
    ProviderType, OutputFormat, TriggerType, AgentLifecycleState, ProviderStatus,
    TransportType, CapabilityType
  - Dataclasses: CapabilityRequest, CapabilityResult (+ ErrorInfo),
    CapabilityContract (+ InputSpec), AgentContract, PromptContract (+ VariableSpec),
    WorkflowContract (+ TriggerSpec + PlanStep), RetrievalResult (+ ScoredCapability),
    ExecutionContext, ProviderConfig, ProviderHealth, PolicyResult, ResolvedProvider,
    AgentResponsePayload
  - Factory methods: CapabilityResult.success_result(), .failure_result(), .timeout_result()
  - Validation: CapabilityRequest.validate(), .validate_or_raise()
  - CapabilityVersion: parse, compare, compatibility, to_dict
  - Roundtrip: to_dict -> from_dict produces equal dataclass

NO MOCKS.  Pure data structure tests.
"""

from __future__ import annotations

import pytest

from k1.fabric.types import (
    AgentContract,
    AgentLifecycleState,
    AgentResponsePayload,
    Availability,
    CapabilityContract,
    CapabilityRequest,
    CapabilityRequestValidationError,
    CapabilityResult,
    CapabilityType,
    CapabilityVersion,
    CapabilityVersionError,
    ErrorInfo,
    ExecutionContext,
    InputSpec,
    OutputFormat,
    PlanStep,
    PolicyResult,
    PromptContract,
    ProviderConfig,
    ProviderHealth,
    ProviderStatus,
    ProviderType,
    RequestStatus,
    ResolvedProvider,
    RetrievalResult,
    SafetyBand,
    ScoredCapability,
    Tier,
    TransportType,
    TriggerSpec,
    TriggerType,
    VariableSpec,
    WFQPriority,
    WorkflowContract,
)

# =========================================================================
# Enums
# =========================================================================


class TestEnums:
    """All enums have expected members and are str subclasses."""

    def test_wfq_priority_members(self) -> None:
        assert set(WFQPriority) == {
            WFQPriority.URGENT,
            WFQPriority.REALTIME,
            WFQPriority.INTERACTIVE,
            WFQPriority.BACKGROUND,
        }
        assert WFQPriority.URGENT.value == "URGENT"

    def test_request_status_members(self) -> None:
        expected = {"PENDING", "IN_PROGRESS", "COMPLETED", "FAILED", "CANCELLED", "TIMED_OUT"}
        assert {s.value for s in RequestStatus} == expected

    def test_tier_members(self) -> None:
        assert set(t.value for t in Tier) == {"LOW", "MEDIUM", "HIGH"}

    def test_safety_band_ordering(self) -> None:
        assert SafetyBand.GREEN < SafetyBand.AMBER
        assert SafetyBand.AMBER < SafetyBand.RED
        assert SafetyBand.RED < SafetyBand.CRISIS
        assert SafetyBand.CRISIS >= SafetyBand.GREEN

    def test_safety_band_le_ge(self) -> None:
        assert SafetyBand.GREEN <= SafetyBand.GREEN
        assert SafetyBand.GREEN <= SafetyBand.AMBER
        assert SafetyBand.RED >= SafetyBand.AMBER
        assert not (SafetyBand.GREEN > SafetyBand.RED)

    def test_availability_members(self) -> None:
        assert set(a.value for a in Availability) == {"ONLINE", "DEGRADED", "OFFLINE"}

    def test_provider_type_members(self) -> None:
        expected = {"MCP", "WASM", "BRIDGE", "AGENT", "WORKFLOW", "CONCIERGE", "LOCAL_STUB"}
        assert {p.value for p in ProviderType} == expected

    def test_output_format_members(self) -> None:
        assert set(o.value for o in OutputFormat) == {"TEXT", "JSON", "STRUCTURED"}

    def test_trigger_type_members(self) -> None:
        assert set(t.value for t in TriggerType) == {"cron", "event", "manual"}

    def test_agent_lifecycle_state_members(self) -> None:
        expected = {"PENDING", "WARMING", "ACTIVE", "IDLE", "DRAINING", "TERMINATED"}
        assert {s.value for s in AgentLifecycleState} == expected

    def test_provider_status_members(self) -> None:
        expected = {"HEALTHY", "DEGRADED", "UNHEALTHY", "UNKNOWN"}
        assert {s.value for s in ProviderStatus} == expected

    def test_transport_type_members(self) -> None:
        assert set(t.value for t in TransportType) == {"stdio", "sse", "streamable-http"}

    def test_enums_are_str(self) -> None:
        """All enums subclass str for JSON serialization."""
        assert isinstance(SafetyBand.GREEN, str)
        assert isinstance(WFQPriority.URGENT, str)
        assert isinstance(Tier.LOW, str)


# =========================================================================
# CapabilityType
# =========================================================================


class TestCapabilityType:
    """CapabilityType prefix matching."""

    def test_matches_valid_prefixes(self) -> None:
        assert CapabilityType.matches("tool.execute.weather")
        assert CapabilityType.matches("agent.spawn.planner")
        assert CapabilityType.matches("workflow.run.daily_check")
        assert CapabilityType.matches("concierge.state.manage")

    def test_no_match_for_unknown(self) -> None:
        assert not CapabilityType.matches("unknown.thing")
        assert not CapabilityType.matches("")

    def test_get_type(self) -> None:
        assert CapabilityType.get_type("tool.execute.weather") == "tool.execute"
        assert CapabilityType.get_type("agent.spawn.x") == "agent.spawn"
        assert CapabilityType.get_type("nope.nope") is None


# =========================================================================
# ErrorInfo
# =========================================================================


class TestErrorInfo:
    """ErrorInfo roundtrip and defaults."""

    def test_defaults(self) -> None:
        e = ErrorInfo()
        assert e.code == ""
        assert e.message == ""
        assert e.retriable is False

    def test_roundtrip(self) -> None:
        e = ErrorInfo(code="timeout", message="Timed out", retriable=True)
        d = e.to_dict()
        e2 = ErrorInfo.from_dict(d)
        assert e2.code == "timeout"
        assert e2.message == "Timed out"
        assert e2.retriable is True


# =========================================================================
# CapabilityRequest
# =========================================================================


class TestCapabilityRequest:
    """CapabilityRequest validation, to_dict, from_dict."""

    @staticmethod
    def _valid(**overrides) -> CapabilityRequest:
        defaults = dict(
            capability_name="tool.execute.weather",
            caller="orchestrator",
            params={"loc": "SF"},
        )
        defaults.update(overrides)
        return CapabilityRequest(**defaults)

    def test_valid_request_passes_validation(self) -> None:
        r = self._valid()
        assert r.validate() == []

    def test_missing_capability_name(self) -> None:
        r = self._valid(capability_name="")
        errors = r.validate()
        assert any("capability_name" in e for e in errors)

    def test_bad_prefix(self) -> None:
        r = self._valid(capability_name="bad.prefix.thing")
        errors = r.validate()
        assert any("must start with" in e for e in errors)

    def test_invalid_tier(self) -> None:
        r = self._valid(tier="ULTRA")
        assert len(r.validate()) > 0

    def test_invalid_wfq(self) -> None:
        r = self._valid(wfq_priority="WARP")
        assert len(r.validate()) > 0

    def test_negative_timeout(self) -> None:
        r = self._valid(timeout_ms=-1)
        assert any("timeout_ms" in e for e in r.validate())

    def test_negative_retry(self) -> None:
        r = self._valid(retry_count=-1)
        assert any("retry_count" in e for e in r.validate())

    def test_empty_trace(self) -> None:
        r = self._valid(trace_id="")
        assert any("trace_id" in e for e in r.validate())

    def test_empty_caller(self) -> None:
        r = self._valid(caller="")
        assert any("caller" in e for e in r.validate())

    def test_validate_or_raise(self) -> None:
        r = self._valid(capability_name="", caller="")
        with pytest.raises(CapabilityRequestValidationError) as exc:
            r.validate_or_raise()
        assert len(exc.value.errors) >= 2

    def test_to_dict_from_dict_roundtrip(self) -> None:
        r = self._valid(plan_id="p1", step_id="s1")
        d = r.to_dict()
        r2 = CapabilityRequest.from_dict(d)
        assert r2.capability_name == r.capability_name
        assert r2.params == r.params
        assert r2.plan_id == "p1"
        assert r2.step_id == "s1"
        assert r2.request_id == r.request_id

    def test_frozen(self) -> None:
        r = self._valid()
        with pytest.raises(AttributeError):
            r.capability_name = "nope"  # type: ignore[misc]


# =========================================================================
# CapabilityResult + Factory Methods
# =========================================================================


class TestCapabilityResult:
    """CapabilityResult factory methods, roundtrip, invariants."""

    def test_success_result_factory(self) -> None:
        r = CapabilityResult.success_result(
            request_id="r1",
            data={"answer": "ok"},
            provider_id="p1",
            trace_id="t1",
            duration_ms=100,
        )
        assert r.success is True
        assert r.data == {"answer": "ok"}
        assert r.error is None
        assert r.provider_id == "p1"

    def test_failure_result_factory(self) -> None:
        r = CapabilityResult.failure_result(
            request_id="r1",
            error_code="provider_error",
            error_message="Boom",
            retriable=True,
        )
        assert r.success is False
        assert r.data is None
        assert r.error is not None
        assert r.error.code == "provider_error"
        assert r.error.retriable is True

    def test_timeout_result_factory(self) -> None:
        r = CapabilityResult.timeout_result(
            request_id="r1",
            timeout_ms=5000,
            provider_id="p1",
        )
        assert r.success is False
        assert r.error is not None
        assert r.error.code == "timeout"
        assert r.error.retriable is True
        assert "5000ms" in r.error.message

    def test_to_dict_from_dict_success(self) -> None:
        r = CapabilityResult.success_result(
            request_id="r1", data={"x": 1}, provider_id="p1", trace_id="t1"
        )
        d = r.to_dict()
        r2 = CapabilityResult.from_dict(d)
        assert r2.success is True
        assert r2.data == {"x": 1}
        assert r2.error is None

    def test_to_dict_from_dict_failure(self) -> None:
        r = CapabilityResult.failure_result(
            request_id="r1", error_code="err", error_message="msg", retriable=False
        )
        d = r.to_dict()
        r2 = CapabilityResult.from_dict(d)
        assert r2.success is False
        assert r2.error is not None
        assert r2.error.code == "err"

    def test_frozen(self) -> None:
        r = CapabilityResult.success_result("r1", {"a": 1}, "p1")
        with pytest.raises(AttributeError):
            r.success = False  # type: ignore[misc]

    def test_timing_fields_roundtrip(self) -> None:
        r = CapabilityResult.success_result(
            request_id="r1",
            data={"ok": True},
            provider_id="p1",
            duration_ms=500,
            retrieval_time_ms=50,
            resolution_time_ms=100,
            execution_time_ms=350,
        )
        d = r.to_dict()
        r2 = CapabilityResult.from_dict(d)
        assert r2.duration_ms == 500
        assert r2.retrieval_time_ms == 50
        assert r2.resolution_time_ms == 100
        assert r2.execution_time_ms == 350


# =========================================================================
# InputSpec
# =========================================================================


class TestInputSpec:
    """InputSpec roundtrip."""

    def test_roundtrip(self) -> None:
        i = InputSpec(name="loc", type="string", description="Location", enum=["sf", "ny"])
        d = i.to_dict()
        i2 = InputSpec.from_dict(d)
        assert i2.name == "loc"
        assert i2.enum == ["sf", "ny"]

    def test_no_enum_no_default(self) -> None:
        i = InputSpec(name="x", type="int", description="count")
        d = i.to_dict()
        assert "enum" not in d
        assert "default" not in d


# =========================================================================
# CapabilityContract
# =========================================================================


class TestCapabilityContract:
    """CapabilityContract roundtrip and field coverage."""

    @staticmethod
    def _make(**overrides) -> CapabilityContract:
        defaults = dict(
            name="tool.execute.weather",
            version="1.0.0",
            domain=["WEATHER"],
            description="Get weather",
            capabilities=["forecast"],
            limitations=[],
            required_inputs=[InputSpec(name="loc", type="string", description="Location")],
            provider_type="MCP",
            provider_id="mcp-weather",
            safety_band_min="GREEN",
            availability="ONLINE",
        )
        defaults.update(overrides)
        return CapabilityContract(**defaults)

    def test_to_dict_from_dict_roundtrip(self) -> None:
        c = self._make(
            optional_context=["prefs"],
            output={"type": "object"},
            cost_per_call=0.05,
            ephemeral=False,
        )
        d = c.to_dict()
        c2 = CapabilityContract.from_dict(d)
        assert c2.name == c.name
        assert c2.version == c.version
        assert c2.domain == c.domain
        assert c2.optional_context == ["prefs"]
        assert c2.cost_per_call == 0.05
        assert c2.ephemeral is False

    def test_required_inputs_preserved(self) -> None:
        c = self._make()
        d = c.to_dict()
        c2 = CapabilityContract.from_dict(d)
        assert len(c2.required_inputs) == 1
        assert c2.required_inputs[0].name == "loc"

    def test_frozen(self) -> None:
        c = self._make()
        with pytest.raises(AttributeError):
            c.name = "changed"  # type: ignore[misc]


# =========================================================================
# AgentContract
# =========================================================================


class TestAgentContract:
    """AgentContract inherits CapabilityContract, adds agent fields."""

    def test_roundtrip(self) -> None:
        a = AgentContract(
            name="agent.execute.planner",
            version="2.0.0",
            domain=["PLANNING"],
            description="Plans things",
            capabilities=["plan"],
            limitations=[],
            required_inputs=[InputSpec(name="goal", type="string", description="Goal")],
            provider_type="AGENT",
            provider_id="local-planner",
            safety_band_min="GREEN",
            availability="ONLINE",
            prompt_template="planner_v1",
            tools_granted=["tool.execute.calendar"],
            llm_budget_tokens=4096,
            max_tool_calls=5,
            max_execution_time_ms=30000,
            template_file="planner_v1.txt",
        )
        d = a.to_dict()
        a2 = AgentContract.from_dict(d)
        assert a2.prompt_template == "planner_v1"
        assert a2.tools_granted == ["tool.execute.calendar"]
        assert a2.llm_budget_tokens == 4096
        assert a2.max_tool_calls == 5
        assert a2.template_file == "planner_v1.txt"
        # Base fields preserved
        assert a2.name == "agent.execute.planner"
        assert a2.domain == ["PLANNING"]

    def test_is_subclass_of_capability_contract(self) -> None:
        a = AgentContract(name="agent.execute.x")
        assert isinstance(a, CapabilityContract)


# =========================================================================
# VariableSpec
# =========================================================================


class TestVariableSpec:
    """VariableSpec roundtrip."""

    def test_roundtrip_with_default(self) -> None:
        v = VariableSpec(name="tone", type="STRING", required=False, default="casual")
        d = v.to_dict()
        v2 = VariableSpec.from_dict(d)
        assert v2.default == "casual"
        assert v2.required is False

    def test_roundtrip_no_default(self) -> None:
        v = VariableSpec(name="name", type="STRING", required=True)
        d = v.to_dict()
        assert "default" not in d


# =========================================================================
# PromptContract
# =========================================================================


class TestPromptContract:
    """PromptContract roundtrip and field coverage."""

    def test_roundtrip(self) -> None:
        p = PromptContract(
            name="invitation_drafter_v1",
            version="1.0.0",
            domain=["SOCIAL"],
            description="Draft invitations",
            intent_match=["invite", "send"],
            variables=[VariableSpec(name="event_name", type="STRING", required=True)],
            template_file="invitation.txt",
            max_tokens=2048,
            output_format="TEXT",
            compatible_agents=["agent.execute.invitation_sender"],
            compatible_tools=[],
        )
        d = p.to_dict()
        p2 = PromptContract.from_dict(d)
        assert p2.name == "invitation_drafter_v1"
        assert len(p2.variables) == 1
        assert p2.variables[0].name == "event_name"
        assert p2.compatible_agents == ["agent.execute.invitation_sender"]
        assert p2.output_format == "TEXT"


# =========================================================================
# TriggerSpec + PlanStep
# =========================================================================


class TestTriggerSpec:
    """TriggerSpec roundtrip."""

    def test_cron_trigger(self) -> None:
        t = TriggerSpec(type="cron", schedule="0 8 * * MON", timezone="US/Pacific")
        d = t.to_dict()
        t2 = TriggerSpec.from_dict(d)
        assert t2.type == "cron"
        assert t2.schedule == "0 8 * * MON"
        assert t2.timezone == "US/Pacific"

    def test_event_trigger(self) -> None:
        t = TriggerSpec(type="event", event_topic="k1.something.v1")
        d = t.to_dict()
        assert "event_topic" in d
        t2 = TriggerSpec.from_dict(d)
        assert t2.event_topic == "k1.something.v1"

    def test_manual_default(self) -> None:
        t = TriggerSpec()
        assert t.type == "manual"


class TestPlanStep:
    """PlanStep roundtrip."""

    def test_roundtrip(self) -> None:
        s = PlanStep(
            id="s1",
            capability="tool.execute.weather",
            params={"loc": "SF"},
            tools_granted=["tool.execute.calendar"],
            deps=["s0"],
        )
        d = s.to_dict()
        s2 = PlanStep.from_dict(d)
        assert s2.id == "s1"
        assert s2.capability == "tool.execute.weather"
        assert s2.deps == ["s0"]

    def test_minimal(self) -> None:
        s = PlanStep(id="s1", capability="agent.spawn.x")
        d = s.to_dict()
        assert "deps" not in d  # empty list omitted
        assert "tools_granted" not in d


# =========================================================================
# WorkflowContract
# =========================================================================


class TestWorkflowContract:
    """WorkflowContract roundtrip and field coverage."""

    def test_roundtrip(self) -> None:
        w = WorkflowContract(
            name="workflow.run.daily_check",
            version="1.0.0",
            domain=["HEALTH"],
            description="Daily check",
            trigger=TriggerSpec(type="cron", schedule="0 8 * * *"),
            steps=[
                PlanStep(id="s1", capability="tool.read.weather_api"),
                PlanStep(id="s2", capability="agent.execute.summarizer", deps=["s1"]),
            ],
            dependencies={"s2": ["s1"]},
            max_depth=5,
            safety_band_min="GREEN",
        )
        d = w.to_dict()
        w2 = WorkflowContract.from_dict(d)
        assert w2.name == "workflow.run.daily_check"
        assert w2.trigger is not None
        assert w2.trigger.type == "cron"
        assert len(w2.steps) == 2
        assert w2.steps[1].deps == ["s1"]
        assert w2.dependencies == {"s2": ["s1"]}
        assert w2.max_depth == 5

    def test_no_trigger(self) -> None:
        w = WorkflowContract(name="workflow.run.manual", version="1.0.0")
        d = w.to_dict()
        assert d["trigger"] is None
        w2 = WorkflowContract.from_dict(d)
        assert w2.trigger is None


# =========================================================================
# ScoredCapability + RetrievalResult
# =========================================================================


class TestScoredCapability:
    """ScoredCapability roundtrip."""

    def test_roundtrip(self) -> None:
        c = CapabilityContract(name="tool.execute.x", version="1.0.0")
        sc = ScoredCapability(contract=c, score=0.95)
        d = sc.to_dict()
        sc2 = ScoredCapability.from_dict(d)
        assert sc2.score == 0.95
        assert sc2.contract is not None
        assert sc2.contract.name == "tool.execute.x"

    def test_none_contract(self) -> None:
        sc = ScoredCapability(score=0.5)
        d = sc.to_dict()
        assert d["contract"] is None


class TestRetrievalResult:
    """RetrievalResult roundtrip."""

    def test_roundtrip(self) -> None:
        c = CapabilityContract(name="tool.execute.x", version="1.0.0")
        rr = RetrievalResult(
            capabilities=[ScoredCapability(contract=c, score=0.9)],
            total_matched=5,
            query_latency_ms=42,
            query_intent="weather",
            index_size=100,
        )
        d = rr.to_dict()
        rr2 = RetrievalResult.from_dict(d)
        assert rr2.total_matched == 5
        assert rr2.query_latency_ms == 42
        assert len(rr2.capabilities) == 1
        assert rr2.capabilities[0].score == 0.9
        assert rr2.embedding_model == "ultrabert-v4.0.0"


# =========================================================================
# ExecutionContext
# =========================================================================


class TestExecutionContext:
    """ExecutionContext roundtrip."""

    def test_roundtrip(self) -> None:
        ec = ExecutionContext(
            session_sections={"beliefs": {"key": "val"}},
            params={"loc": "SF"},
            prompt="Hello!",
            token_count=42,
            trace_id="t1",
        )
        d = ec.to_dict()
        ec2 = ExecutionContext.from_dict(d)
        assert ec2.session_sections == {"beliefs": {"key": "val"}}
        assert ec2.prompt == "Hello!"
        assert ec2.token_count == 42

    def test_defaults(self) -> None:
        ec = ExecutionContext()
        assert ec.session_sections == {}
        assert ec.prompt is None
        assert ec.token_count == 0


# =========================================================================
# ProviderConfig
# =========================================================================


class TestProviderConfig:
    """ProviderConfig roundtrip."""

    def test_roundtrip_mcp(self) -> None:
        pc = ProviderConfig(
            provider_id="mcp-weather",
            provider_type="MCP",
            endpoint="mcp://local/weather",
            transport="stdio",
            max_concurrent=5,
            health_check_interval_s=30,
            max_execution_ms=10000,
        )
        d = pc.to_dict()
        pc2 = ProviderConfig.from_dict(d)
        assert pc2.provider_id == "mcp-weather"
        assert pc2.endpoint == "mcp://local/weather"
        assert pc2.transport == "stdio"
        assert pc2.max_concurrent == 5

    def test_roundtrip_wasm(self) -> None:
        pc = ProviderConfig(
            provider_id="wasm-calc",
            provider_type="WASM",
            module_path="/path/to/calc.wasm",
            sandbox_memory_mb=128,
        )
        d = pc.to_dict()
        pc2 = ProviderConfig.from_dict(d)
        assert pc2.module_path == "/path/to/calc.wasm"
        assert pc2.sandbox_memory_mb == 128

    def test_defaults(self) -> None:
        pc = ProviderConfig()
        assert pc.max_concurrent == 10
        assert pc.health_check_interval_s == 60
        assert pc.max_execution_ms == 30000


# =========================================================================
# ProviderHealth
# =========================================================================


class TestProviderHealth:
    """ProviderHealth to_dict."""

    def test_to_dict(self) -> None:
        ph = ProviderHealth(
            provider_id="p1",
            status="HEALTHY",
            latency_ms=50,
            error=None,
        )
        d = ph.to_dict()
        assert d["provider_id"] == "p1"
        assert d["status"] == "HEALTHY"
        assert d["error"] is None


# =========================================================================
# PolicyResult + ResolvedProvider
# =========================================================================


class TestPolicyResult:
    """PolicyResult to_dict."""

    def test_to_dict(self) -> None:
        pr = PolicyResult(allowed=False, score=0.5, reasons=["bad vibes"])
        d = pr.to_dict()
        assert d["allowed"] is False
        assert d["score"] == 0.5
        assert d["reasons"] == ["bad vibes"]


class TestResolvedProvider:
    """ResolvedProvider to_dict."""

    def test_to_dict_with_contract(self) -> None:
        c = CapabilityContract(name="tool.execute.x", version="1.0.0")
        rp = ResolvedProvider(
            provider_config=ProviderConfig(provider_id="p1"),
            contract=c,
            policy_result=PolicyResult(allowed=True, score=0.9),
        )
        d = rp.to_dict()
        assert d["provider_config"]["provider_id"] == "p1"
        assert d["contract"]["name"] == "tool.execute.x"
        assert d["policy_result"]["allowed"] is True

    def test_to_dict_no_contract(self) -> None:
        rp = ResolvedProvider()
        d = rp.to_dict()
        assert d["contract"] is None


# =========================================================================
# AgentResponsePayload
# =========================================================================


class TestAgentResponsePayload:
    """AgentResponsePayload roundtrip and validation."""

    def test_roundtrip(self) -> None:
        p = AgentResponsePayload(
            answer="Here is your answer",
            confidence=0.95,
            domain=("HEALTH", "WELLNESS"),
            sources=({"ref": "doc1"},),
            domain_data={"summary": "ok"},
            follow_up_needed=True,
            follow_up_suggestion="Check again",
            reasoning_trace=("step1", "step2"),
            tools_used=("tool.execute.x",),
            k0_queries_made=3,
        )
        d = p.to_dict()
        p2 = AgentResponsePayload.from_dict(d)
        assert p2.answer == "Here is your answer"
        assert p2.confidence == 0.95
        assert p2.domain == ("HEALTH", "WELLNESS")
        assert len(p2.sources) == 1
        assert p2.tools_used == ("tool.execute.x",)
        assert p2.k0_queries_made == 3

    def test_validate_valid(self) -> None:
        p = AgentResponsePayload(
            answer="OK",
            confidence=0.8,
            domain=("HEALTH",),
        )
        assert p.validate() is True

    def test_validate_empty_answer(self) -> None:
        p = AgentResponsePayload(answer="  ", confidence=0.8, domain=("HEALTH",))
        assert p.validate() is False

    def test_validate_bad_confidence(self) -> None:
        p = AgentResponsePayload(answer="OK", confidence=1.5, domain=("X",))
        assert p.validate() is False

    def test_validate_empty_domain(self) -> None:
        p = AgentResponsePayload(answer="OK", confidence=0.5)
        assert p.validate() is False

    def test_from_dict_coerces_lists_to_tuples(self) -> None:
        d = {"answer": "ok", "domain": ["A", "B"], "sources": [{"x": 1}]}
        p = AgentResponsePayload.from_dict(d)
        assert isinstance(p.domain, tuple)
        assert isinstance(p.sources, tuple)


# =========================================================================
# CapabilityVersion
# =========================================================================


class TestCapabilityVersion:
    """CapabilityVersion parsing, comparison, compatibility."""

    def test_parse_valid(self) -> None:
        v = CapabilityVersion.parse("1.2.3")
        assert v.major == 1
        assert v.minor == 2
        assert v.patch == 3

    def test_parse_with_whitespace(self) -> None:
        v = CapabilityVersion.parse("  0.1.0  ")
        assert v == CapabilityVersion(0, 1, 0)

    def test_parse_invalid(self) -> None:
        with pytest.raises(CapabilityVersionError):
            CapabilityVersion.parse("not.a.version")

    def test_parse_incomplete(self) -> None:
        with pytest.raises(CapabilityVersionError):
            CapabilityVersion.parse("1.2")

    def test_comparison_operators(self) -> None:
        v1 = CapabilityVersion(1, 0, 0)
        v2 = CapabilityVersion(1, 1, 0)
        v3 = CapabilityVersion(2, 0, 0)
        assert v1 < v2
        assert v2 < v3
        assert v3 > v1
        assert v1 <= v1
        assert v2 >= v2

    def test_equality_and_hash(self) -> None:
        a = CapabilityVersion(1, 2, 3)
        b = CapabilityVersion(1, 2, 3)
        assert a == b
        assert hash(a) == hash(b)
        assert a != CapabilityVersion(1, 2, 4)

    def test_compatible_same_major(self) -> None:
        v1 = CapabilityVersion(2, 0, 0)
        v2 = CapabilityVersion(2, 5, 1)
        assert v1.is_compatible_with(v2)

    def test_incompatible_different_major(self) -> None:
        v1 = CapabilityVersion(1, 0, 0)
        v2 = CapabilityVersion(2, 0, 0)
        assert not v1.is_compatible_with(v2)

    def test_unstable_major_zero_exact_only(self) -> None:
        v1 = CapabilityVersion(0, 1, 0)
        v2 = CapabilityVersion(0, 1, 0)
        v3 = CapabilityVersion(0, 2, 0)
        assert v1.is_compatible_with(v2)
        assert not v1.is_compatible_with(v3)

    def test_compare_static(self) -> None:
        v1 = CapabilityVersion(1, 0, 0)
        v2 = CapabilityVersion(1, 1, 0)
        assert CapabilityVersion.compare(v1, v2) == -1
        assert CapabilityVersion.compare(v2, v1) == 1
        assert CapabilityVersion.compare(v1, v1) == 0

    def test_str_repr(self) -> None:
        v = CapabilityVersion(3, 2, 1)
        assert str(v) == "3.2.1"
        assert "3" in repr(v)

    def test_to_dict(self) -> None:
        v = CapabilityVersion(1, 2, 3)
        d = v.to_dict()
        assert d["major"] == 1
        assert d["minor"] == 2
        assert d["patch"] == 3
        assert d["string"] == "1.2.3"
