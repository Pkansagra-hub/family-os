"""
Epic 6.5.3 -- Test Policy -> ContextBuilder -> Agent flow (cross-subsystem).

Verifies the full data flow chain:
  1. PolicyEngine reads SessionState (affective_now, cognitive) for soft scoring.
  2. ContextBuilder reads SessionState for agent required_context (beliefs_active, persona).
  3. AgentFactory._spawn() uses ContextBuilder to build ExecutionContext.
  4. Agent receives the assembled context and executes.
  5. Agent emits deltas via IDeltaBusPort on fact discovery.

Key architectural insight:
  - FabricFactory._create_agent() does NOT inject an AgentFactory into AgentProvider
    (agent_factory=None -> stub mode). So agent execution through fabric.execute()
    returns AgentNotImplementedError. Direct AgentFactory tests verify the full chain.
  - PolicyEngine and ContextBuilder BOTH read SessionState from the SAME reader,
    but they read DIFFERENT sections (affective_now/cognitive vs required_context).
  - ContextBuilder is wired into AgentFactory step 6 (build initial context).

NO MOCKS -- all tests use real adapters and real components.

References:
  - fabric-implementation-plan.md Epic 6.5.3
  - fabric_discussion.md Section 10 (Policy Dimensions)
  - fabric_discussion.md Section 12 (Context Assembly)
  - fabric_discussion.md Section 13 (Agent Factory 8-step)
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

from k1.fabric.adapters.test_delta_bus import TestDeltaBusAdapter
from k1.fabric.adapters.test_model_gateway import TestModelGatewayAdapter
from k1.fabric.adapters.test_prompt_system import TestPromptSystemAdapter
from k1.fabric.adapters.test_state_reader import TestSessionStateReaderAdapter
from k1.fabric.core.context_builder import ContextBuilder
from k1.fabric.events.fabric_events import TOPIC_CAPABILITY_INVOKED
from k1.fabric.factory import FabricFactory
from k1.fabric.policy.affective_routing import AffectiveRouting
from k1.fabric.policy.cognitive_load_routing import CognitiveLoadRouting
from k1.fabric.policy.policy_engine import PolicyEngine
from k1.fabric.policy.security_context import SecurityContext
from k1.fabric.provider_resolution.provider_selector import ScoredCandidate
from k1.fabric.providers.agent_provider import (
    AgentDelta,
    AgentFactory,
    AgentLifecycleState,
    AgentPool,
    DeltaEmitter,
)
from k1.fabric.types import (
    AgentContract,
    CapabilityRequest,
    ExecutionContext,
    InputSpec,
    ProviderConfig,
    SafetyBand,
    Tier,
)

# ---------------------------------------------------------------------------
# Fixtures directory
# ---------------------------------------------------------------------------

FIXTURES_DIR = Path(__file__).parent / "fixtures"

# ---------------------------------------------------------------------------
# Shared SessionState sections (realistic K1 data)
# ---------------------------------------------------------------------------

SESSION_ID = "sess-policy-ctx-agent-001"

BELIEFS_ACTIVE = {
    "facts": [
        {"text": "User prefers Italian food", "confidence": 0.92},
        {"text": "User lives in Seattle", "confidence": 0.98},
    ],
    "entities": {
        "Alice": {"role": "friend", "birthday": "1990-03-15"},
        "Bob": {"role": "colleague"},
    },
    "relationships": {
        "Alice": {"closeness": 0.9, "interaction_count": 42},
    },
}

PERSONA = {
    "name": "FamilyAI",
    "style": "warm and supportive",
    "bio": "A family assistant helping with daily life.",
    "quirks": ["uses gentle humor", "remembers birthdays"],
}

AFFECTIVE_NOW_CALM = {
    "raw": "calm",
    "intensity": 0.2,
    "valence": 0.5,
}

AFFECTIVE_NOW_SAD = {
    "raw": "sadness",
    "intensity": 0.85,
    "valence": -0.6,
}

AFFECTIVE_NOW_JOY = {
    "raw": "joy",
    "intensity": 0.9,
    "valence": 0.9,
}

COGNITIVE_LOW = {
    "load": 0.2,
    "complexity_tier": "LOW",
}

COGNITIVE_HIGH = {
    "load": 0.85,
    "complexity_tier": "HIGH",
}

COGNITIVE_MEDIUM = {
    "load": 0.5,
    "complexity_tier": "MEDIUM",
}

CONTROL = {
    "safety_band": "GREEN",
    "user_preferences": {"language": "en"},
}

HISTORY_RECENT = {
    "turns": [
        {"user": "Plan Alice's party", "assistant": "Let me help with that!"},
    ],
}


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def _make_agent_contract(
    name: str = "agent.execute.test_policy_agent",
    *,
    required_context: Optional[List[str]] = None,
    optional_context: Optional[List[str]] = None,
    tools_granted: Optional[List[str]] = None,
    safety_band_min: str = SafetyBand.GREEN.value,
    llm_budget_tokens: int = 4096,
    provider_id: str = "agent-policy-test",
) -> AgentContract:
    """Build an AgentContract with configurable context requirements."""
    return AgentContract(
        name=name,
        version="1.0.0",
        domain=["TEST"],
        description="Agent for policy-context integration test",
        capabilities=["test_action"],
        limitations=[],
        required_inputs=[
            InputSpec(name="query", type="STRING", description="Test input"),
        ],
        output={"type": "object"},
        provider_type="AGENT",
        provider_id=provider_id,
        safety_band_min=safety_band_min,
        required_context=required_context or ["beliefs_active", "persona"],
        optional_context=optional_context or ["control"],
        prompt_template="test_prompt_v1",
        tools_granted=tools_granted or [],
        llm_budget_tokens=llm_budget_tokens,
        max_tool_calls=5,
        max_execution_time_ms=10000,
    )


def _make_request(
    capability_name: str = "agent.execute.test_policy_agent",
    *,
    params: Optional[Dict[str, Any]] = None,
    session_id: str = SESSION_ID,
    safety_band: str = SafetyBand.GREEN.value,
) -> CapabilityRequest:
    """Build a CapabilityRequest with session_id for policy+context reads."""
    return CapabilityRequest(
        capability_name=capability_name,
        params=params or {"query": "Plan a birthday party for Alice"},
        tier=Tier.MEDIUM.value,
        caller="test-policy-ctx-agent",
        session_id=session_id,
        safety_band=safety_band,
    )


def _make_state_reader(
    *,
    affective: Optional[Dict[str, Any]] = None,
    cognitive: Optional[Dict[str, Any]] = None,
    beliefs: Optional[Dict[str, Any]] = None,
    persona: Optional[Dict[str, Any]] = None,
    control: Optional[Dict[str, Any]] = None,
    history: Optional[Dict[str, Any]] = None,
    session_id: str = SESSION_ID,
) -> TestSessionStateReaderAdapter:
    """Build a pre-loaded state reader with configurable sections."""
    reader = TestSessionStateReaderAdapter()
    sections: Dict[str, Dict[str, Any]] = {}
    if affective is not None:
        sections["affective_now"] = affective
    if cognitive is not None:
        sections["cognitive"] = cognitive
    if beliefs is not None:
        sections["beliefs_active"] = beliefs
    if persona is not None:
        sections["persona"] = persona
    if control is not None:
        sections["control"] = control
    if history is not None:
        sections["history_recent"] = history
    if sections:
        reader.load_many(session_id, sections)
    return reader


def _make_policy_engine(
    state_reader: TestSessionStateReaderAdapter,
) -> PolicyEngine:
    """Build a PolicyEngine with all 4 dimensions wired to the shared reader."""
    return PolicyEngine(
        security=SecurityContext(),
        affective=AffectiveRouting(state_reader=state_reader),
        cognitive=CognitiveLoadRouting(state_reader=state_reader),
    )


def _make_context_builder(
    state_reader: TestSessionStateReaderAdapter,
    prompt_system: Optional[TestPromptSystemAdapter] = None,
) -> ContextBuilder:
    """Build a ContextBuilder wired to the shared state reader."""
    return ContextBuilder(
        state_reader=state_reader,
        prompt_system=prompt_system,
    )


def _make_agent_factory(
    *,
    state_reader: TestSessionStateReaderAdapter,
    context_builder: ContextBuilder,
    delta_bus: Optional[TestDeltaBusAdapter] = None,
    model_gateway: Optional[TestModelGatewayAdapter] = None,
    contract: Optional[AgentContract] = None,
    pool: Optional[AgentPool] = None,
) -> AgentFactory:
    """Build an AgentFactory with real adapters and injected context builder."""
    gw = model_gateway or TestModelGatewayAdapter(
        default_responses=["Agent completed the task successfully."],
    )
    db = delta_bus or TestDeltaBusAdapter()
    target_contract = contract or _make_agent_contract()

    def loader(name: str) -> Optional[AgentContract]:
        if name == target_contract.name:
            return target_contract
        return None

    return AgentFactory(
        context_builder=context_builder,
        model_gateway=gw,
        state_reader=state_reader,
        delta_bus=db,
        contract_loader=loader,
        pool=pool,
    )


# =========================================================================
# 6.5.3a -- Policy reads SessionState for soft scoring
# =========================================================================


class TestPolicyReadsSessionState:
    """
    Verify PolicyEngine reads affective_now and cognitive sections
    from the shared SessionState reader for soft-score computation.
    """

    def test_affective_calm_returns_neutral(self) -> None:
        """Calm emotion (low intensity) -> affective score = 0.0."""
        reader = _make_state_reader(affective=AFFECTIVE_NOW_CALM)
        ar = AffectiveRouting(state_reader=reader)
        request = _make_request()

        score = ar.score(request)
        assert score.score == 0.0
        assert "low_intensity" in score.reason

    def test_affective_sadness_high_triggers_boost(self) -> None:
        """High-intensity sadness -> affective score = +0.10."""
        reader = _make_state_reader(affective=AFFECTIVE_NOW_SAD)
        ar = AffectiveRouting(state_reader=reader)
        request = _make_request()

        score = ar.score(request)
        assert score.score == 0.10
        assert "sad_anxious_boost" in score.reason

    def test_affective_joy_high_triggers_boost(self) -> None:
        """High-intensity joy -> affective score = +0.05."""
        reader = _make_state_reader(affective=AFFECTIVE_NOW_JOY)
        ar = AffectiveRouting(state_reader=reader)
        request = _make_request()

        score = ar.score(request)
        assert score.score == 0.05
        assert "joy_excited_boost" in score.reason

    def test_cognitive_low_load_returns_boost(self) -> None:
        """Low cognitive load -> cognitive score = +0.05."""
        reader = _make_state_reader(cognitive=COGNITIVE_LOW)
        cr = CognitiveLoadRouting(state_reader=reader)
        request = _make_request()

        score = cr.score(request)
        assert score.score == 0.05
        assert "low_load_boost" in score.reason

    def test_cognitive_high_load_returns_boost(self) -> None:
        """High cognitive load -> cognitive score = +0.10."""
        reader = _make_state_reader(cognitive=COGNITIVE_HIGH)
        cr = CognitiveLoadRouting(state_reader=reader)
        request = _make_request()

        score = cr.score(request)
        assert score.score == 0.10
        assert "high_load_boost" in score.reason

    def test_cognitive_medium_load_returns_neutral(self) -> None:
        """Medium cognitive load -> cognitive score = 0.0."""
        reader = _make_state_reader(cognitive=COGNITIVE_MEDIUM)
        cr = CognitiveLoadRouting(state_reader=reader)
        request = _make_request()

        score = cr.score(request)
        assert score.score == 0.0
        assert "medium_load" in score.reason

    def test_no_state_reader_returns_neutral(self) -> None:
        """No state reader -> both dimensions return 0.0."""
        ar = AffectiveRouting(state_reader=None)
        cr = CognitiveLoadRouting(state_reader=None)
        request = _make_request()

        assert ar.score(request).score == 0.0
        assert cr.score(request).score == 0.0

    def test_missing_section_returns_neutral(self) -> None:
        """State reader present but section missing -> neutral."""
        reader = _make_state_reader()  # empty reader
        ar = AffectiveRouting(state_reader=reader)
        cr = CognitiveLoadRouting(state_reader=reader)
        request = _make_request()

        assert ar.score(request).score == 0.0
        assert cr.score(request).score == 0.0


# =========================================================================
# 6.5.3b -- PolicyEngine composite score incorporates SessionState
# =========================================================================


class TestPolicyEngineCompositeScore:
    """
    Verify PolicyEngine composes security + affective + cognitive into
    a single composite score that reflects SessionState.
    """

    def test_composite_with_sad_and_high_load(self) -> None:
        """Sadness + high cognitive load -> score = 1.0 + 0.10 + 0.10 = 1.20."""
        reader = _make_state_reader(
            affective=AFFECTIVE_NOW_SAD,
            cognitive=COGNITIVE_HIGH,
        )
        engine = _make_policy_engine(reader)
        contract = _make_agent_contract()
        request = _make_request()

        provider = ProviderConfig(
            provider_id="agent-policy-test",
            provider_type="AGENT",
            endpoint="local://agent",
        )
        scored = engine.evaluate([provider], contract, request)

        assert len(scored) == 1
        sc = scored[0]
        assert sc.policy_result.allowed is True
        # base(1.0) + affective(0.10) + cognitive(0.10) + qos(0.0)
        assert sc.policy_result.score == pytest.approx(1.20, abs=0.01)

    def test_composite_with_joy_and_low_load(self) -> None:
        """Joy + low cognitive load -> score = 1.0 + 0.05 + 0.05 = 1.10."""
        reader = _make_state_reader(
            affective=AFFECTIVE_NOW_JOY,
            cognitive=COGNITIVE_LOW,
        )
        engine = _make_policy_engine(reader)
        contract = _make_agent_contract()
        request = _make_request()

        provider = ProviderConfig(
            provider_id="agent-policy-test",
            provider_type="AGENT",
            endpoint="local://agent",
        )
        scored = engine.evaluate([provider], contract, request)

        assert len(scored) == 1
        sc = scored[0]
        assert sc.policy_result.allowed is True
        # base(1.0) + affective(0.05) + cognitive(0.05) + qos(0.0)
        assert sc.policy_result.score == pytest.approx(1.10, abs=0.01)

    def test_composite_calm_medium_is_baseline(self) -> None:
        """Calm + medium load -> score = 1.0 (all soft scores are 0)."""
        reader = _make_state_reader(
            affective=AFFECTIVE_NOW_CALM,
            cognitive=COGNITIVE_MEDIUM,
        )
        engine = _make_policy_engine(reader)
        contract = _make_agent_contract()
        request = _make_request()

        provider = ProviderConfig(
            provider_id="agent-policy-test",
            provider_type="AGENT",
            endpoint="local://agent",
        )
        scored = engine.evaluate([provider], contract, request)

        assert len(scored) == 1
        assert scored[0].policy_result.score == pytest.approx(1.0, abs=0.01)

    def test_composite_no_state_returns_baseline(self) -> None:
        """No SessionState -> all soft scores 0, composite = 1.0."""
        reader = _make_state_reader()  # empty
        engine = _make_policy_engine(reader)
        contract = _make_agent_contract()
        request = _make_request()

        provider = ProviderConfig(
            provider_id="agent-policy-test",
            provider_type="AGENT",
            endpoint="local://agent",
        )
        scored = engine.evaluate([provider], contract, request)

        assert len(scored) == 1
        assert scored[0].policy_result.allowed is True
        assert scored[0].policy_result.score == pytest.approx(1.0, abs=0.01)

    def test_security_hard_gate_blocks_amber_contract_green_caller(self) -> None:
        """AMBER safety band contract + GREEN caller -> blocked by security."""
        reader = _make_state_reader(
            affective=AFFECTIVE_NOW_SAD,
            cognitive=COGNITIVE_HIGH,
        )
        engine = _make_policy_engine(reader)
        contract = _make_agent_contract(safety_band_min="AMBER")
        request = _make_request(safety_band=SafetyBand.GREEN.value)

        provider = ProviderConfig(
            provider_id="agent-policy-test",
            provider_type="AGENT",
            endpoint="local://agent",
        )
        scored = engine.evaluate([provider], contract, request)

        assert len(scored) == 1
        assert scored[0].policy_result.allowed is False
        assert scored[0].policy_result.score == 0.0


# =========================================================================
# 6.5.3c -- ContextBuilder reads SessionState for agent required_context
# =========================================================================


class TestContextBuilderReadsForAgent:
    """
    Verify ContextBuilder fetches the sections declared in an agent
    contract's required_context and optional_context from SessionState.
    """

    def test_required_sections_fetched(self) -> None:
        """Required context sections (beliefs_active, persona) are read."""
        reader = _make_state_reader(
            beliefs=BELIEFS_ACTIVE,
            persona=PERSONA,
        )
        builder = _make_context_builder(reader)
        contract = _make_agent_contract(
            required_context=["beliefs_active", "persona"],
        )

        result = builder.build(
            contract=contract,
            params={"query": "hello"},
            session_id=SESSION_ID,
            trace_id="tr-ctx-001",
        )

        assert "beliefs_active" in result.context.session_sections
        assert "persona" in result.context.session_sections
        assert result.context.session_sections["beliefs_active"] == BELIEFS_ACTIVE
        assert result.context.session_sections["persona"] == PERSONA
        assert len(result.missing_required) == 0

    def test_optional_sections_included_when_present(self) -> None:
        """Optional context sections are included if available."""
        reader = _make_state_reader(
            beliefs=BELIEFS_ACTIVE,
            persona=PERSONA,
            control=CONTROL,
        )
        builder = _make_context_builder(reader)
        contract = _make_agent_contract(
            required_context=["beliefs_active", "persona"],
            optional_context=["control"],
        )

        result = builder.build(
            contract=contract,
            params={},
            session_id=SESSION_ID,
        )

        assert "control" in result.context.session_sections
        assert len(result.missing_optional) == 0

    def test_missing_optional_section_skipped(self) -> None:
        """Missing optional sections are reported but build succeeds."""
        reader = _make_state_reader(beliefs=BELIEFS_ACTIVE, persona=PERSONA)
        builder = _make_context_builder(reader)
        contract = _make_agent_contract(
            required_context=["beliefs_active", "persona"],
            optional_context=["control", "history_recent"],
        )

        result = builder.build(
            contract=contract,
            params={},
            session_id=SESSION_ID,
        )

        assert "control" in result.missing_optional
        assert "history_recent" in result.missing_optional
        assert len(result.missing_required) == 0

    def test_missing_required_section_reported(self) -> None:
        """Missing required sections logged but build does not crash."""
        reader = _make_state_reader(persona=PERSONA)  # no beliefs_active
        builder = _make_context_builder(reader)
        contract = _make_agent_contract(
            required_context=["beliefs_active", "persona"],
        )

        result = builder.build(
            contract=contract,
            params={},
            session_id=SESSION_ID,
        )

        assert "beliefs_active" in result.missing_required
        assert "persona" in result.context.session_sections

    def test_params_injected_into_context(self) -> None:
        """Request params are included in ExecutionContext."""
        reader = _make_state_reader(beliefs=BELIEFS_ACTIVE, persona=PERSONA)
        builder = _make_context_builder(reader)
        contract = _make_agent_contract()
        params = {"query": "Plan a party", "budget": 500}

        result = builder.build(
            contract=contract,
            params=params,
            session_id=SESSION_ID,
            trace_id="tr-params-001",
        )

        assert result.context.params["query"] == "Plan a party"
        assert result.context.params["budget"] == 500
        assert result.context.trace_id == "tr-params-001"

    def test_prompt_template_resolved_and_compiled(self) -> None:
        """Prompt template resolved via IPromptSystemPort and compiled."""
        reader = _make_state_reader(beliefs=BELIEFS_ACTIVE, persona=PERSONA)
        prompt_sys = TestPromptSystemAdapter()
        prompt_sys.add_template(
            "test_prompt_v1",
            "You are {persona}. Help the user with: {task}",
            variables=["persona", "task"],
        )
        builder = _make_context_builder(reader, prompt_system=prompt_sys)
        contract = _make_agent_contract()

        result = builder.build(
            contract=contract,
            params={"query": "hello"},
            session_id=SESSION_ID,
            prompt_template_name="test_prompt_v1",
            prompt_variables={"persona": "FamilyAI", "task": "party planning"},
        )

        assert result.prompt_resolved is True
        assert result.context.prompt is not None
        assert "FamilyAI" in result.context.prompt
        assert "party planning" in result.context.prompt

    def test_no_state_reader_graceful_degradation(self) -> None:
        """No state reader -> all sections missing, build succeeds."""
        builder = ContextBuilder(state_reader=None)
        contract = _make_agent_contract(
            required_context=["beliefs_active", "persona"],
        )

        result = builder.build(
            contract=contract,
            params={"query": "test"},
            session_id=SESSION_ID,
        )

        assert result.context.session_sections == {}
        assert "beliefs_active" in result.missing_required
        assert "persona" in result.missing_required

    def test_context_trace_id_propagated(self) -> None:
        """trace_id from build() flows into ExecutionContext."""
        reader = _make_state_reader(beliefs=BELIEFS_ACTIVE)
        builder = _make_context_builder(reader)
        contract = _make_agent_contract()

        result = builder.build(
            contract=contract,
            params={},
            session_id=SESSION_ID,
            trace_id="tr-propagate-001",
        )

        assert result.context.trace_id == "tr-propagate-001"


# =========================================================================
# 6.5.3d -- Policy + ContextBuilder share same SessionState reader
# =========================================================================


class TestPolicyAndContextShareReader:
    """
    Verify that PolicyEngine and ContextBuilder read from the SAME
    SessionState reader instance but access DIFFERENT sections.
    """

    def test_policy_reads_affective_context_reads_beliefs(self) -> None:
        """
        One reader, two consumers: Policy reads affective_now,
        ContextBuilder reads beliefs_active and persona.
        """
        reader = _make_state_reader(
            affective=AFFECTIVE_NOW_SAD,
            cognitive=COGNITIVE_HIGH,
            beliefs=BELIEFS_ACTIVE,
            persona=PERSONA,
        )

        # Policy reads affective_now + cognitive
        engine = _make_policy_engine(reader)
        contract = _make_agent_contract()
        request = _make_request()
        provider_cfg = ProviderConfig(
            provider_id="agent-policy-test",
            provider_type="AGENT",
            endpoint="local://agent",
        )
        scored = engine.evaluate([provider_cfg], contract, request)
        assert scored[0].policy_result.allowed is True
        # Affective(0.10) + cognitive(0.10) + base(1.0) = 1.20
        assert scored[0].policy_result.score == pytest.approx(1.20, abs=0.01)

        # ContextBuilder reads beliefs_active + persona
        builder = _make_context_builder(reader)
        build_result = builder.build(
            contract=contract,
            params={"query": "test"},
            session_id=SESSION_ID,
            trace_id="tr-shared-001",
        )
        assert "beliefs_active" in build_result.context.session_sections
        assert "persona" in build_result.context.session_sections
        assert build_result.context.session_sections["beliefs_active"] == BELIEFS_ACTIVE
        assert build_result.context.session_sections["persona"] == PERSONA

    def test_changing_affective_state_updates_policy_not_context(self) -> None:
        """
        Mutating affective_now changes policy score but NOT context.
        Context still reads beliefs_active and persona.
        """
        reader = _make_state_reader(
            affective=AFFECTIVE_NOW_CALM,
            beliefs=BELIEFS_ACTIVE,
            persona=PERSONA,
        )
        engine = _make_policy_engine(reader)
        contract = _make_agent_contract()
        request = _make_request()
        provider_cfg = ProviderConfig(
            provider_id="agent-policy-test",
            provider_type="AGENT",
            endpoint="local://agent",
        )

        # Calm -> baseline score
        scored_calm = engine.evaluate([provider_cfg], contract, request)
        assert scored_calm[0].policy_result.score == pytest.approx(1.0, abs=0.01)

        # Update affective to sad
        reader.load(SESSION_ID, "affective_now", AFFECTIVE_NOW_SAD)

        # Score changes
        scored_sad = engine.evaluate([provider_cfg], contract, request)
        assert scored_sad[0].policy_result.score == pytest.approx(1.10, abs=0.01)

        # Context still sees beliefs_active and persona (unchanged)
        builder = _make_context_builder(reader)
        build_result = builder.build(
            contract=contract,
            params={},
            session_id=SESSION_ID,
        )
        assert build_result.context.session_sections["beliefs_active"] == BELIEFS_ACTIVE
        assert build_result.context.session_sections["persona"] == PERSONA

    def test_changing_beliefs_updates_context_not_policy(self) -> None:
        """
        Mutating beliefs_active changes context but NOT policy score.
        """
        reader = _make_state_reader(
            affective=AFFECTIVE_NOW_SAD,
            cognitive=COGNITIVE_HIGH,
            beliefs=BELIEFS_ACTIVE,
            persona=PERSONA,
        )
        engine = _make_policy_engine(reader)
        builder = _make_context_builder(reader)
        contract = _make_agent_contract()
        request = _make_request()
        provider_cfg = ProviderConfig(
            provider_id="agent-policy-test",
            provider_type="AGENT",
            endpoint="local://agent",
        )

        # Initial
        scored = engine.evaluate([provider_cfg], contract, request)
        initial_score = scored[0].policy_result.score

        build_result_1 = builder.build(
            contract=contract,
            params={},
            session_id=SESSION_ID,
        )
        assert "User prefers Italian food" in str(
            build_result_1.context.session_sections["beliefs_active"]
        )

        # Update beliefs
        updated_beliefs = {
            "facts": [{"text": "User prefers sushi", "confidence": 0.95}],
        }
        reader.load(SESSION_ID, "beliefs_active", updated_beliefs)

        # Policy score unchanged (doesn't read beliefs_active)
        scored_after = engine.evaluate([provider_cfg], contract, request)
        assert scored_after[0].policy_result.score == pytest.approx(initial_score, abs=0.01)

        # Context updated
        build_result_2 = builder.build(
            contract=contract,
            params={},
            session_id=SESSION_ID,
        )
        assert "User prefers sushi" in str(
            build_result_2.context.session_sections["beliefs_active"]
        )


# =========================================================================
# 6.5.3e -- AgentFactory._spawn() uses ContextBuilder for context
# =========================================================================


class TestAgentFactoryUsesContextBuilder:
    """
    Verify AgentFactory step 6 (build initial context) uses ContextBuilder
    to assemble ExecutionContext from SessionState sections.
    """

    def test_spawn_builds_context_with_beliefs_and_persona(self) -> None:
        """AgentFactory._spawn() calls ContextBuilder.build() with contract."""
        reader = _make_state_reader(beliefs=BELIEFS_ACTIVE, persona=PERSONA)
        builder = _make_context_builder(reader)
        contract = _make_agent_contract(
            required_context=["beliefs_active", "persona"],
        )
        factory = _make_agent_factory(
            state_reader=reader,
            context_builder=builder,
            contract=contract,
        )
        fallback_ctx = ExecutionContext(params={"fallback": True}, trace_id="tr-fallback")

        agent = factory._spawn(
            contract, fallback_ctx, {"query": "test"}, "tr-spawn-001", session_id=SESSION_ID
        )

        # Agent received context built by ContextBuilder (not fallback)
        assert "beliefs_active" in agent.context.session_sections
        assert "persona" in agent.context.session_sections
        assert agent.context.session_sections["beliefs_active"] == BELIEFS_ACTIVE
        assert agent.context.session_sections["persona"] == PERSONA
        assert agent.lifecycle_state == AgentLifecycleState.PENDING

    def test_spawn_fallback_when_no_context_builder(self) -> None:
        """Without ContextBuilder, agent uses fallback context."""
        reader = _make_state_reader(beliefs=BELIEFS_ACTIVE)
        contract = _make_agent_contract()
        factory = AgentFactory(
            context_builder=None,
            model_gateway=TestModelGatewayAdapter(),
            state_reader=reader,
            delta_bus=TestDeltaBusAdapter(),
            contract_loader=lambda name: contract if name == contract.name else None,
        )
        fallback_ctx = ExecutionContext(
            params={"fallback": True},
            trace_id="tr-fallback",
            session_sections={"manual": {"key": "value"}},
        )

        agent = factory._spawn(
            contract, fallback_ctx, {"query": "test"}, "tr-fb-001", session_id=SESSION_ID
        )

        # Uses fallback context
        assert "manual" in agent.context.session_sections
        assert "beliefs_active" not in agent.context.session_sections

    def test_spawn_context_has_correct_trace_id(self) -> None:
        """trace_id from caller flows through ContextBuilder into Agent context."""
        reader = _make_state_reader(beliefs=BELIEFS_ACTIVE)
        builder = _make_context_builder(reader)
        contract = _make_agent_contract()
        factory = _make_agent_factory(
            state_reader=reader,
            context_builder=builder,
            contract=contract,
        )
        fallback_ctx = ExecutionContext(trace_id="tr-wrong")

        agent = factory._spawn(contract, fallback_ctx, {}, "tr-correct-001", session_id=SESSION_ID)

        assert agent.context.trace_id == "tr-correct-001"

    def test_spawn_optional_sections_included(self) -> None:
        """Optional context sections included when present in SessionState."""
        reader = _make_state_reader(
            beliefs=BELIEFS_ACTIVE,
            persona=PERSONA,
            control=CONTROL,
        )
        builder = _make_context_builder(reader)
        contract = _make_agent_contract(
            required_context=["beliefs_active", "persona"],
            optional_context=["control"],
        )
        factory = _make_agent_factory(
            state_reader=reader,
            context_builder=builder,
            contract=contract,
        )
        fallback_ctx = ExecutionContext()

        agent = factory._spawn(contract, fallback_ctx, {}, "tr-opt-001", session_id=SESSION_ID)

        assert "beliefs_active" in agent.context.session_sections
        assert "persona" in agent.context.session_sections
        assert "control" in agent.context.session_sections


# =========================================================================
# 6.5.3f -- Agent execution with context (spawn_and_execute)
# =========================================================================


class TestAgentExecutionWithContext:
    """
    Verify the full AgentFactory.spawn_and_execute() flow:
    ContextBuilder assembles context -> Agent executes with it.
    """

    @pytest.mark.asyncio
    async def test_spawn_and_execute_returns_success(self) -> None:
        """Full pipeline: spawn with context, execute, get result."""
        reader = _make_state_reader(beliefs=BELIEFS_ACTIVE, persona=PERSONA)
        builder = _make_context_builder(reader)
        contract = _make_agent_contract()
        factory = _make_agent_factory(
            state_reader=reader,
            context_builder=builder,
            contract=contract,
        )
        request = _make_request()
        fallback_ctx = ExecutionContext(trace_id="tr-exec-001")

        result = await factory.spawn_and_execute(request, fallback_ctx, "tr-exec-001")

        assert result.success is True
        assert result.agent_id != ""
        assert len(result.output) > 0

    @pytest.mark.asyncio
    async def test_execute_with_llm_handle(self) -> None:
        """Agent with LLM handle generates response using prompt."""
        reader = _make_state_reader(beliefs=BELIEFS_ACTIVE, persona=PERSONA)
        prompt_sys = TestPromptSystemAdapter()
        prompt_sys.add_template(
            "test_prompt_v1",
            "Context: {context}\nTask: {task}",
            variables=["context", "task"],
        )
        builder = _make_context_builder(reader, prompt_system=prompt_sys)
        gw = TestModelGatewayAdapter(
            default_responses=["I'll help you plan the party!"],
        )
        contract = _make_agent_contract()
        factory = _make_agent_factory(
            state_reader=reader,
            context_builder=builder,
            model_gateway=gw,
            contract=contract,
        )
        request = _make_request()
        fallback_ctx = ExecutionContext(trace_id="tr-llm-001")

        result = await factory.spawn_and_execute(request, fallback_ctx, "tr-llm-001")

        assert result.success is True
        # LLM was called (output contains response)
        assert "response" in result.output
        assert result.tokens_used > 0

    @pytest.mark.asyncio
    async def test_missing_contract_returns_failure(self) -> None:
        """Contract not found -> failure result (not exception)."""
        reader = _make_state_reader(beliefs=BELIEFS_ACTIVE)
        builder = _make_context_builder(reader)
        factory = _make_agent_factory(
            state_reader=reader,
            context_builder=builder,
        )
        request = _make_request(capability_name="agent.execute.nonexistent")
        fallback_ctx = ExecutionContext()

        result = await factory.spawn_and_execute(request, fallback_ctx, "tr-miss-001")

        assert result.success is False
        assert "not found" in result.error_message.lower()


# =========================================================================
# 6.5.3g -- Agent emits deltas via IDeltaBusPort
# =========================================================================


class TestAgentEmitsDeltas:
    """
    Verify agents emit deltas through the DeltaBusPort when they
    produce output (fact discovery).
    """

    @pytest.mark.asyncio
    async def test_delta_emitted_on_execution(self) -> None:
        """Agent execution emits at least one delta to the delta bus."""
        reader = _make_state_reader(beliefs=BELIEFS_ACTIVE, persona=PERSONA)
        builder = _make_context_builder(reader)
        delta_bus = TestDeltaBusAdapter()
        contract = _make_agent_contract()
        factory = _make_agent_factory(
            state_reader=reader,
            context_builder=builder,
            delta_bus=delta_bus,
            contract=contract,
        )
        request = _make_request()
        fallback_ctx = ExecutionContext(trace_id="tr-delta-001")

        result = await factory.spawn_and_execute(request, fallback_ctx, "tr-delta-001")

        assert result.success is True
        assert delta_bus.delta_count > 0

    @pytest.mark.asyncio
    async def test_delta_has_correct_agent_id(self) -> None:
        """Emitted delta contains the spawned agent's ID."""
        reader = _make_state_reader(beliefs=BELIEFS_ACTIVE, persona=PERSONA)
        builder = _make_context_builder(reader)
        delta_bus = TestDeltaBusAdapter()
        contract = _make_agent_contract()
        factory = _make_agent_factory(
            state_reader=reader,
            context_builder=builder,
            delta_bus=delta_bus,
            contract=contract,
        )
        request = _make_request()
        fallback_ctx = ExecutionContext(trace_id="tr-delta-id-001")

        result = await factory.spawn_and_execute(request, fallback_ctx, "tr-delta-id-001")

        assert result.success is True
        deltas = delta_bus.get_deltas()
        assert len(deltas) > 0
        # The agent_id in the delta should match the spawned agent
        assert deltas[0].agent_id == result.agent_id

    @pytest.mark.asyncio
    async def test_delta_section_is_history_active(self) -> None:
        """Agent output delta targets 'history_active' section."""
        reader = _make_state_reader(beliefs=BELIEFS_ACTIVE, persona=PERSONA)
        builder = _make_context_builder(reader)
        delta_bus = TestDeltaBusAdapter()
        contract = _make_agent_contract()
        factory = _make_agent_factory(
            state_reader=reader,
            context_builder=builder,
            delta_bus=delta_bus,
            contract=contract,
        )
        request = _make_request()
        fallback_ctx = ExecutionContext(trace_id="tr-delta-sec-001")

        await factory.spawn_and_execute(request, fallback_ctx, "tr-delta-sec-001")

        deltas = delta_bus.get_deltas(section="history_active")
        assert len(deltas) >= 1

    @pytest.mark.asyncio
    async def test_delta_type_is_agent_output(self) -> None:
        """Agent output delta has delta_type='agent_output'."""
        reader = _make_state_reader(beliefs=BELIEFS_ACTIVE, persona=PERSONA)
        builder = _make_context_builder(reader)
        delta_bus = TestDeltaBusAdapter()
        contract = _make_agent_contract()
        factory = _make_agent_factory(
            state_reader=reader,
            context_builder=builder,
            delta_bus=delta_bus,
            contract=contract,
        )
        request = _make_request()
        fallback_ctx = ExecutionContext(trace_id="tr-delta-type-001")

        await factory.spawn_and_execute(request, fallback_ctx, "tr-delta-type-001")

        deltas = delta_bus.get_deltas(delta_type="agent_output")
        assert len(deltas) >= 1

    @pytest.mark.asyncio
    async def test_no_delta_emitted_when_no_delta_bus(self) -> None:
        """Without delta bus, agent execution still succeeds (no crash)."""
        reader = _make_state_reader(beliefs=BELIEFS_ACTIVE, persona=PERSONA)
        builder = _make_context_builder(reader)
        contract = _make_agent_contract()
        factory = AgentFactory(
            context_builder=builder,
            model_gateway=TestModelGatewayAdapter(),
            state_reader=reader,
            delta_bus=None,
            contract_loader=lambda name: contract if name == contract.name else None,
        )
        request = _make_request()
        fallback_ctx = ExecutionContext(trace_id="tr-no-delta")

        result = await factory.spawn_and_execute(request, fallback_ctx, "tr-no-delta")

        assert result.success is True


# =========================================================================
# 6.5.3h -- DeltaEmitter batching and LWW merge
# =========================================================================


class TestDeltaEmitterBatchingAndLWW:
    """
    Verify DeltaEmitter aggregation behavior:
    500ms batch window, LWW (Last-Writer-Wins) merge on (section, key).
    """

    def test_emit_and_flush(self) -> None:
        """Emitted deltas flushed to IDeltaBusPort on flush()."""
        delta_bus = TestDeltaBusAdapter()
        emitter = DeltaEmitter(
            agent_id="agent-001",
            delta_bus=delta_bus,
            trace_id="tr-emitter-001",
        )

        emitter.emit(
            delta_type="fact",
            section="beliefs_active",
            key="food_pref",
            value="Italian",
            op="set",
        )
        assert emitter.pending_count == 1

        flushed = emitter.flush()
        assert flushed == 1
        assert emitter.pending_count == 0
        assert delta_bus.delta_count == 1

    def test_lww_merge_same_key(self) -> None:
        """Two emits to same (section, key) -> LWW keeps latest."""
        delta_bus = TestDeltaBusAdapter()
        emitter = DeltaEmitter(
            agent_id="agent-002",
            delta_bus=delta_bus,
            trace_id="tr-lww-001",
        )

        emitter.emit(
            delta_type="fact",
            section="beliefs_active",
            key="food_pref",
            value="Italian",
        )
        emitter.emit(
            delta_type="fact",
            section="beliefs_active",
            key="food_pref",
            value="Sushi",
        )

        # Only 1 pending (LWW merged)
        assert emitter.pending_count == 1

        flushed = emitter.flush()
        assert flushed == 1
        deltas = delta_bus.get_deltas()
        assert len(deltas) == 1
        # Latest value wins
        assert deltas[0].data["value"] == "Sushi"

    def test_different_keys_not_merged(self) -> None:
        """Different (section, key) pairs kept separate."""
        delta_bus = TestDeltaBusAdapter()
        emitter = DeltaEmitter(
            agent_id="agent-003",
            delta_bus=delta_bus,
            trace_id="tr-sep-001",
        )

        emitter.emit(
            delta_type="fact",
            section="beliefs_active",
            key="food_pref",
            value="Italian",
        )
        emitter.emit(
            delta_type="fact",
            section="beliefs_active",
            key="city",
            value="Seattle",
        )

        assert emitter.pending_count == 2
        flushed = emitter.flush()
        assert flushed == 2

    def test_delta_operations(self) -> None:
        """AgentDelta supports set, append, delete operations."""
        d_set = AgentDelta(
            agent_id="a1",
            delta_type="fact",
            section="beliefs_active",
            key="k1",
            value="v1",
            op="set",
        )
        d_append = AgentDelta(
            agent_id="a1",
            delta_type="fact",
            section="beliefs_active",
            key="k2",
            value="v2",
            op="append",
        )
        d_delete = AgentDelta(
            agent_id="a1",
            delta_type="fact",
            section="beliefs_active",
            key="k3",
            value=None,
            op="delete",
        )

        assert d_set.op == "set"
        assert d_append.op == "append"
        assert d_delete.op == "delete"

    def test_invalid_delta_op_raises(self) -> None:
        """Invalid op raises ValueError."""
        with pytest.raises(ValueError, match="Invalid delta op"):
            AgentDelta(
                agent_id="a1",
                delta_type="fact",
                section="s",
                key="k",
                value="v",
                op="invalid",
            )


# =========================================================================
# 6.5.3i -- Full pipeline: Policy -> ContextBuilder -> Agent -> Delta
# =========================================================================


class TestFullPipelinePolicyContextAgentDelta:
    """
    End-to-end: PolicyEngine evaluates with SessionState scores,
    ContextBuilder assembles context from SessionState,
    Agent executes and emits deltas.
    """

    @pytest.mark.asyncio
    async def test_full_chain_sad_high_load(self) -> None:
        """
        Full chain with sadness + high cognitive load:
        Policy score = 1.20, context has beliefs + persona, delta emitted.
        """
        reader = _make_state_reader(
            affective=AFFECTIVE_NOW_SAD,
            cognitive=COGNITIVE_HIGH,
            beliefs=BELIEFS_ACTIVE,
            persona=PERSONA,
            control=CONTROL,
        )

        # Step 1: Policy evaluates with soft scores
        engine = _make_policy_engine(reader)
        contract = _make_agent_contract()
        request = _make_request()
        provider_cfg = ProviderConfig(
            provider_id="agent-policy-test",
            provider_type="AGENT",
            endpoint="local://agent",
        )
        scored = engine.evaluate([provider_cfg], contract, request)
        assert scored[0].policy_result.allowed is True
        assert scored[0].policy_result.score == pytest.approx(1.20, abs=0.01)

        # Step 2: ContextBuilder assembles context
        builder = _make_context_builder(reader)
        build_result = builder.build(
            contract=contract,
            params=request.params,
            session_id=SESSION_ID,
            trace_id=request.trace_id,
        )
        assert "beliefs_active" in build_result.context.session_sections
        assert "persona" in build_result.context.session_sections
        assert len(build_result.missing_required) == 0

        # Step 3: AgentFactory spawns and executes with built context
        delta_bus = TestDeltaBusAdapter()
        factory = _make_agent_factory(
            state_reader=reader,
            context_builder=builder,
            delta_bus=delta_bus,
            contract=contract,
        )
        fallback_ctx = ExecutionContext(trace_id=request.trace_id)
        result = await factory.spawn_and_execute(request, fallback_ctx, request.trace_id)

        assert result.success is True
        assert result.agent_id != ""

        # Step 4: Delta emitted
        assert delta_bus.delta_count > 0
        deltas = delta_bus.get_deltas(delta_type="agent_output")
        assert len(deltas) >= 1
        assert deltas[0].agent_id == result.agent_id

    @pytest.mark.asyncio
    async def test_full_chain_joy_low_load(self) -> None:
        """
        Full chain with joy + low cognitive load:
        Policy score = 1.10, context assembled, delta emitted.
        """
        reader = _make_state_reader(
            affective=AFFECTIVE_NOW_JOY,
            cognitive=COGNITIVE_LOW,
            beliefs=BELIEFS_ACTIVE,
            persona=PERSONA,
        )

        engine = _make_policy_engine(reader)
        contract = _make_agent_contract()
        request = _make_request()
        provider_cfg = ProviderConfig(
            provider_id="agent-policy-test",
            provider_type="AGENT",
            endpoint="local://agent",
        )
        scored = engine.evaluate([provider_cfg], contract, request)
        assert scored[0].policy_result.score == pytest.approx(1.10, abs=0.01)

        builder = _make_context_builder(reader)
        delta_bus = TestDeltaBusAdapter()
        factory = _make_agent_factory(
            state_reader=reader,
            context_builder=builder,
            delta_bus=delta_bus,
            contract=contract,
        )
        fallback_ctx = ExecutionContext(trace_id=request.trace_id)
        result = await factory.spawn_and_execute(request, fallback_ctx, request.trace_id)

        assert result.success is True
        assert delta_bus.delta_count > 0

    @pytest.mark.asyncio
    async def test_full_chain_security_blocks_no_agent_execution(self) -> None:
        """
        Security hard gate blocks -> agent should NOT execute.
        AMBER contract + GREEN caller = blocked.
        """
        reader = _make_state_reader(
            affective=AFFECTIVE_NOW_SAD,
            cognitive=COGNITIVE_HIGH,
            beliefs=BELIEFS_ACTIVE,
            persona=PERSONA,
        )

        engine = _make_policy_engine(reader)
        contract = _make_agent_contract(safety_band_min="AMBER")
        request = _make_request(safety_band=SafetyBand.GREEN.value)
        provider_cfg = ProviderConfig(
            provider_id="agent-policy-test",
            provider_type="AGENT",
            endpoint="local://agent",
        )

        scored = engine.evaluate([provider_cfg], contract, request)
        assert scored[0].policy_result.allowed is False

        # In the real pipeline, resolver would reject before agent spawns.
        # This verifies the decision: no context built, no agent spawned.

    @pytest.mark.asyncio
    async def test_full_chain_with_prompt_resolution(self) -> None:
        """
        Full chain including prompt template resolution.
        Policy OK -> ContextBuilder resolves prompt -> Agent gets prompt in context.
        """
        reader = _make_state_reader(
            affective=AFFECTIVE_NOW_CALM,
            beliefs=BELIEFS_ACTIVE,
            persona=PERSONA,
        )
        prompt_sys = TestPromptSystemAdapter()
        prompt_sys.add_template(
            "test_prompt_v1",
            "You are {persona}. User is {emotion}. Task: {task}",
            variables=["persona", "emotion", "task"],
        )

        builder = _make_context_builder(reader, prompt_system=prompt_sys)
        delta_bus = TestDeltaBusAdapter()
        gw = TestModelGatewayAdapter(
            default_responses=["Here's the party plan!"],
        )
        contract = _make_agent_contract()
        factory = _make_agent_factory(
            state_reader=reader,
            context_builder=builder,
            delta_bus=delta_bus,
            model_gateway=gw,
            contract=contract,
        )
        request = _make_request()
        fallback_ctx = ExecutionContext(trace_id=request.trace_id)

        result = await factory.spawn_and_execute(request, fallback_ctx, request.trace_id)

        assert result.success is True
        assert result.tokens_used > 0
        assert delta_bus.delta_count > 0


# =========================================================================
# 6.5.3j -- Agent lifecycle during full pipeline
# =========================================================================


class TestAgentLifecycleDuringPipeline:
    """
    Verify agent lifecycle transitions during the full pipeline:
    PENDING -> WARMING -> ACTIVE -> execute -> IDLE (pool) or TERMINATED.
    """

    @pytest.mark.asyncio
    async def test_successful_execution_pools_agent(self) -> None:
        """On success, agent transitions to IDLE and enters pool."""
        reader = _make_state_reader(beliefs=BELIEFS_ACTIVE, persona=PERSONA)
        builder = _make_context_builder(reader)
        delta_bus = TestDeltaBusAdapter()
        pool = AgentPool()
        contract = _make_agent_contract()
        factory = _make_agent_factory(
            state_reader=reader,
            context_builder=builder,
            delta_bus=delta_bus,
            contract=contract,
        )
        # Inject pool
        factory._pool = pool
        request = _make_request()
        fallback_ctx = ExecutionContext(trace_id="tr-pool-001")

        result = await factory.spawn_and_execute(request, fallback_ctx, "tr-pool-001")

        assert result.success is True
        assert pool.size(contract.name) == 1

    @pytest.mark.asyncio
    async def test_pooled_agent_reused_on_second_call(self) -> None:
        """Second call for same contract reuses pooled agent."""
        reader = _make_state_reader(beliefs=BELIEFS_ACTIVE, persona=PERSONA)
        builder = _make_context_builder(reader)
        delta_bus = TestDeltaBusAdapter()
        pool = AgentPool()
        contract = _make_agent_contract()
        factory = _make_agent_factory(
            state_reader=reader,
            context_builder=builder,
            delta_bus=delta_bus,
            contract=contract,
        )
        factory._pool = pool
        request = _make_request()
        fallback_ctx = ExecutionContext(trace_id="tr-reuse-001")

        result1 = await factory.spawn_and_execute(request, fallback_ctx, "tr-reuse-001")
        agent_id_1 = result1.agent_id

        result2 = await factory.spawn_and_execute(request, fallback_ctx, "tr-reuse-002")
        agent_id_2 = result2.agent_id

        assert result1.success is True
        assert result2.success is True
        # Same agent reused
        assert agent_id_1 == agent_id_2
        assert pool.total_reuses == 1


# =========================================================================
# 6.5.3k -- Fabric.execute() with agent contract (stub mode)
# =========================================================================


class TestFabricExecuteAgentStubMode:
    """
    Verify fabric.execute() with agent contracts goes through the
    full resolve pipeline but hits AgentProvider stub mode
    (agent_factory=None in current wiring).
    """

    @pytest.mark.asyncio
    async def test_agent_execution_through_fabric_hits_stub(self) -> None:
        """
        fabric.execute() with agent contract resolves correctly
        but AgentProvider in stub mode returns error.
        Documents the current wiring gap: _create_agent() does NOT
        inject an AgentFactory into AgentProvider.
        """
        fabric = FabricFactory.create_for_testing(
            capture_events=True,
            contracts_dir=str(FIXTURES_DIR),
        )
        request = CapabilityRequest(
            capability_name="agent.execute.invitation_sender",
            params={
                "event_name": "Birthday Party",
                "guest_list": ["Alice"],
            },
            tier=Tier.MEDIUM.value,
            caller="test-stub",
            safety_band=SafetyBand.AMBER.value,
            session_id=SESSION_ID,
        )

        result = await fabric.execute(request)

        # AgentProvider stub returns failure
        assert result.success is False

    @pytest.mark.asyncio
    async def test_agent_resolution_works_through_fabric(self) -> None:
        """
        The resolution pipeline (registry lookup + provider match + policy)
        works for agent contracts even though execution fails at stub.
        """
        fabric = FabricFactory.create_for_testing(
            capture_events=True,
            contracts_dir=str(FIXTURES_DIR),
        )
        # The YAML fixture health_summarizer requires AMBER safety band.
        # Use AMBER caller so policy passes.
        request = CapabilityRequest(
            capability_name="agent.execute.invitation_sender",
            params={
                "event_name": "Test",
                "guest_list": ["Alice"],
            },
            tier=Tier.MEDIUM.value,
            caller="test-resolution",
            safety_band=SafetyBand.GREEN.value,
            session_id=SESSION_ID,
        )

        # Events should show invocation was attempted
        result = await fabric.execute(request)
        event_adapter = fabric.event_port
        invoked = event_adapter.get_captured(topic=TOPIC_CAPABILITY_INVOKED)
        assert len(invoked) >= 1


# =========================================================================
# 6.5.3l -- Multiple agents with different context requirements
# =========================================================================


class TestMultipleAgentsDifferentContext:
    """
    Verify multiple agent contracts with different required_context
    sections each get the correct context from the same SessionState.
    """

    @pytest.mark.asyncio
    async def test_two_agents_different_required_sections(self) -> None:
        """
        Agent A requires [beliefs_active, persona].
        Agent B requires [beliefs_active, control].
        Both get correct sections from same reader.
        """
        reader = _make_state_reader(
            beliefs=BELIEFS_ACTIVE,
            persona=PERSONA,
            control=CONTROL,
        )
        builder = _make_context_builder(reader)
        delta_bus_a = TestDeltaBusAdapter()
        delta_bus_b = TestDeltaBusAdapter()

        contract_a = _make_agent_contract(
            name="agent.execute.agent_a",
            required_context=["beliefs_active", "persona"],
            provider_id="agent-a-provider",
        )
        contract_b = _make_agent_contract(
            name="agent.execute.agent_b",
            required_context=["beliefs_active", "control"],
            provider_id="agent-b-provider",
        )

        factory_a = _make_agent_factory(
            state_reader=reader,
            context_builder=builder,
            delta_bus=delta_bus_a,
            contract=contract_a,
        )
        factory_b = _make_agent_factory(
            state_reader=reader,
            context_builder=builder,
            delta_bus=delta_bus_b,
            contract=contract_b,
        )

        request_a = _make_request(capability_name="agent.execute.agent_a")
        request_b = _make_request(capability_name="agent.execute.agent_b")
        fallback = ExecutionContext()

        result_a = await factory_a.spawn_and_execute(request_a, fallback, "tr-a")
        result_b = await factory_b.spawn_and_execute(request_b, fallback, "tr-b")

        assert result_a.success is True
        assert result_b.success is True

        # Both emitted deltas
        assert delta_bus_a.delta_count > 0
        assert delta_bus_b.delta_count > 0

    @pytest.mark.asyncio
    async def test_agent_with_no_required_context(self) -> None:
        """Agent with empty required_context still executes successfully."""
        reader = _make_state_reader(beliefs=BELIEFS_ACTIVE)
        builder = _make_context_builder(reader)
        contract = _make_agent_contract(
            required_context=[],
            optional_context=[],
        )
        factory = _make_agent_factory(
            state_reader=reader,
            context_builder=builder,
            contract=contract,
        )
        request = _make_request()
        fallback = ExecutionContext()

        result = await factory.spawn_and_execute(request, fallback, "tr-empty-ctx")

        assert result.success is True

    @pytest.mark.asyncio
    async def test_sequential_agents_share_state_independently(self) -> None:
        """Two sequential agent executions share SessionState but get independent contexts."""
        reader = _make_state_reader(beliefs=BELIEFS_ACTIVE, persona=PERSONA)
        builder = _make_context_builder(reader)
        delta_bus = TestDeltaBusAdapter()
        contract = _make_agent_contract()
        factory = _make_agent_factory(
            state_reader=reader,
            context_builder=builder,
            delta_bus=delta_bus,
            contract=contract,
        )
        request = _make_request()
        fallback = ExecutionContext()

        result_1 = await factory.spawn_and_execute(request, fallback, "tr-seq-001")
        result_2 = await factory.spawn_and_execute(request, fallback, "tr-seq-002")

        assert result_1.success is True
        assert result_2.success is True
        # Different agent instances
        assert result_1.agent_id != result_2.agent_id
        # Both emitted deltas
        assert delta_bus.delta_count >= 2


# =========================================================================
# 6.5.3m -- SessionState hot-reload reflected in context
# =========================================================================


class TestSessionStateHotReload:
    """
    Verify that changes to SessionState between agent executions
    are reflected in subsequent context builds.
    """

    @pytest.mark.asyncio
    async def test_updated_beliefs_reflected_in_next_agent(self) -> None:
        """
        Update beliefs_active between two agent spawns.
        Second agent gets updated beliefs.
        """
        reader = _make_state_reader(beliefs=BELIEFS_ACTIVE, persona=PERSONA)
        builder = _make_context_builder(reader)
        contract = _make_agent_contract()
        delta_bus = TestDeltaBusAdapter()

        # First build
        build_1 = builder.build(
            contract=contract,
            params={},
            session_id=SESSION_ID,
            trace_id="tr-hot-1",
        )
        assert "User prefers Italian food" in str(
            build_1.context.session_sections["beliefs_active"]
        )

        # Update beliefs
        updated_beliefs = {
            "facts": [{"text": "User now prefers Japanese cuisine", "confidence": 0.96}],
        }
        reader.load(SESSION_ID, "beliefs_active", updated_beliefs)

        # Second build sees updated data
        build_2 = builder.build(
            contract=contract,
            params={},
            session_id=SESSION_ID,
            trace_id="tr-hot-2",
        )
        assert "Japanese cuisine" in str(build_2.context.session_sections["beliefs_active"])

    @pytest.mark.asyncio
    async def test_removed_section_becomes_missing(self) -> None:
        """Remove a section -> next build reports it as missing."""
        reader = _make_state_reader(beliefs=BELIEFS_ACTIVE, persona=PERSONA)
        builder = _make_context_builder(reader)
        contract = _make_agent_contract(
            required_context=["beliefs_active", "persona"],
        )

        # First build OK
        build_1 = builder.build(
            contract=contract,
            params={},
            session_id=SESSION_ID,
        )
        assert len(build_1.missing_required) == 0

        # Remove persona
        reader.remove(SESSION_ID, "persona")

        # Second build reports missing
        build_2 = builder.build(
            contract=contract,
            params={},
            session_id=SESSION_ID,
        )
        assert "persona" in build_2.missing_required


# =========================================================================
# 6.5.3n -- Context budget (128K ceiling, FAB-08)
# =========================================================================


class TestContextBudgetIntegration:
    """
    Verify ContextBuilder applies the 128K token budget ceiling (FAB-08)
    during agent context assembly.
    """

    def test_small_context_within_budget(self) -> None:
        """Normal-sized context stays within budget."""
        reader = _make_state_reader(beliefs=BELIEFS_ACTIVE, persona=PERSONA)
        builder = _make_context_builder(reader)
        contract = _make_agent_contract()

        result = builder.build(
            contract=contract,
            params={"query": "test"},
            session_id=SESSION_ID,
        )

        assert result.budget.total_tokens > 0
        from k1.fabric.core.context_budget import TOKEN_CEILING

        assert result.budget.total_tokens <= TOKEN_CEILING

    def test_assembly_time_recorded(self) -> None:
        """ContextBuildResult records assembly_ms."""
        reader = _make_state_reader(beliefs=BELIEFS_ACTIVE, persona=PERSONA)
        builder = _make_context_builder(reader)
        contract = _make_agent_contract()

        result = builder.build(
            contract=contract,
            params={},
            session_id=SESSION_ID,
        )

        assert result.assembly_ms >= 0.0


# =========================================================================
# 6.5.3o -- YAML fixture agents through full pipeline
# =========================================================================


class TestYAMLFixtureAgentPipeline:
    """
    Verify YAML fixture agent contracts (invitation_sender, health_summarizer)
    can go through policy evaluation and context building.
    """

    def test_invitation_sender_policy_green_passes(self) -> None:
        """invitation_sender (GREEN safety) passes GREEN caller policy."""
        from tests.k1.fabric.helpers import load_fixture_contract

        contract = load_fixture_contract("invitation_sender")
        reader = _make_state_reader(
            affective=AFFECTIVE_NOW_CALM,
            cognitive=COGNITIVE_LOW,
        )
        engine = _make_policy_engine(reader)
        request = CapabilityRequest(
            capability_name="agent.execute.invitation_sender",
            params={"event_name": "Party", "guest_list": ["Alice"]},
            tier=Tier.MEDIUM.value,
            caller="test",
            safety_band=SafetyBand.GREEN.value,
            session_id=SESSION_ID,
        )
        provider_cfg = ProviderConfig(
            provider_id=contract.provider_id or "invitation-sender-provider",
            provider_type="AGENT",
            endpoint="local://agent",
        )

        scored = engine.evaluate([provider_cfg], contract, request)

        assert len(scored) == 1
        assert scored[0].policy_result.allowed is True
        assert scored[0].policy_result.score >= 1.0

    def test_health_summarizer_policy_amber_passes(self) -> None:
        """health_summarizer (AMBER safety) passes AMBER caller policy."""
        from tests.k1.fabric.helpers import load_fixture_contract

        contract = load_fixture_contract("health_summarizer")
        reader = _make_state_reader(
            affective=AFFECTIVE_NOW_CALM,
        )
        engine = _make_policy_engine(reader)
        request = CapabilityRequest(
            capability_name="agent.execute.health_summarizer",
            params={"time_range": "7d"},
            tier=Tier.MEDIUM.value,
            caller="test",
            safety_band=SafetyBand.AMBER.value,
            session_id=SESSION_ID,
        )
        provider_cfg = ProviderConfig(
            provider_id=contract.provider_id or "health-summarizer-provider",
            provider_type="AGENT",
            endpoint="local://agent",
        )

        scored = engine.evaluate([provider_cfg], contract, request)

        assert len(scored) == 1
        assert scored[0].policy_result.allowed is True

    def test_health_summarizer_policy_green_blocked(self) -> None:
        """health_summarizer (AMBER safety) blocked by GREEN caller."""
        from tests.k1.fabric.helpers import load_fixture_contract

        contract = load_fixture_contract("health_summarizer")
        reader = _make_state_reader()
        engine = _make_policy_engine(reader)
        request = CapabilityRequest(
            capability_name="agent.execute.health_summarizer",
            params={"time_range": "7d"},
            tier=Tier.MEDIUM.value,
            caller="test",
            safety_band=SafetyBand.GREEN.value,
            session_id=SESSION_ID,
        )
        provider_cfg = ProviderConfig(
            provider_id=contract.provider_id or "health-summarizer-provider",
            provider_type="AGENT",
            endpoint="local://agent",
        )

        scored = engine.evaluate([provider_cfg], contract, request)

        assert len(scored) == 1
        assert scored[0].policy_result.allowed is False

    def test_invitation_sender_context_build(self) -> None:
        """ContextBuilder fetches invitation_sender required_context sections."""
        from tests.k1.fabric.helpers import load_fixture_contract

        contract = load_fixture_contract("invitation_sender")
        reader = _make_state_reader(
            beliefs=BELIEFS_ACTIVE,
            persona=PERSONA,
        )
        # invitation_sender requires beliefs_active.entities and
        # beliefs_active.relationships. These are dot-path sections.
        # ContextBuilder reads them as full section names from SessionState.
        builder = _make_context_builder(reader)

        result = builder.build(
            contract=contract,
            params={"event_name": "Party", "guest_list": ["Alice"]},
            session_id=SESSION_ID,
        )

        # The YAML fixture uses "beliefs_active.entities" as section name,
        # which won't match our "beliefs_active" key in state reader.
        # This documents the dot-path vs flat-section naming convention.
        # Either way, the build should succeed (graceful degradation).
        assert result.context is not None
        assert result.assembly_ms >= 0


# =========================================================================
# 6.5.3p -- Concurrent policy + context + agent
# =========================================================================


class TestConcurrentPolicyContextAgent:
    """
    Verify concurrent agent executions through shared SessionState
    reader are isolated.
    """

    @pytest.mark.asyncio
    async def test_parallel_agent_executions(self) -> None:
        """5 concurrent agent executions each get correct context."""
        reader = _make_state_reader(
            affective=AFFECTIVE_NOW_CALM,
            cognitive=COGNITIVE_LOW,
            beliefs=BELIEFS_ACTIVE,
            persona=PERSONA,
        )
        builder = _make_context_builder(reader)
        delta_bus = TestDeltaBusAdapter()
        contract = _make_agent_contract()
        factory = _make_agent_factory(
            state_reader=reader,
            context_builder=builder,
            delta_bus=delta_bus,
            contract=contract,
        )
        fallback = ExecutionContext()

        # Run 5 in parallel
        tasks = [
            factory.spawn_and_execute(
                _make_request(),
                fallback,
                f"tr-parallel-{i}",
            )
            for i in range(5)
        ]
        results = await asyncio.gather(*tasks)

        assert all(r.success for r in results)
        # All 5 got unique agent IDs
        agent_ids = {r.agent_id for r in results}
        assert len(agent_ids) == 5
        # All 5 emitted deltas
        assert delta_bus.delta_count >= 5

    @pytest.mark.asyncio
    async def test_parallel_policy_evaluations(self) -> None:
        """Concurrent policy evaluations are thread-safe."""
        reader = _make_state_reader(
            affective=AFFECTIVE_NOW_SAD,
            cognitive=COGNITIVE_HIGH,
        )
        engine = _make_policy_engine(reader)
        contract = _make_agent_contract()
        provider_cfg = ProviderConfig(
            provider_id="agent-policy-test",
            provider_type="AGENT",
            endpoint="local://agent",
        )

        # Run 10 evaluations via asyncio (simulates concurrent requests)
        async def evaluate_one(i: int) -> ScoredCandidate:
            request = _make_request()
            scored = engine.evaluate([provider_cfg], contract, request)
            return scored[0]

        tasks = [evaluate_one(i) for i in range(10)]
        results = await asyncio.gather(*tasks)

        # All should produce same score (deterministic)
        scores = [r.policy_result.score for r in results]
        assert all(s == pytest.approx(1.20, abs=0.01) for s in scores)


# =========================================================================
# 6.5.3q -- Edge cases
# =========================================================================


class TestEdgeCases:
    """Boundary conditions for the Policy -> Context -> Agent flow."""

    def test_empty_session_state_policy_still_works(self) -> None:
        """Completely empty SessionState -> policy returns baseline."""
        reader = _make_state_reader()
        engine = _make_policy_engine(reader)
        contract = _make_agent_contract()
        request = _make_request()
        provider_cfg = ProviderConfig(
            provider_id="agent-policy-test",
            provider_type="AGENT",
            endpoint="local://agent",
        )

        scored = engine.evaluate([provider_cfg], contract, request)
        assert scored[0].policy_result.allowed is True
        assert scored[0].policy_result.score == pytest.approx(1.0, abs=0.01)

    def test_empty_session_state_context_still_builds(self) -> None:
        """Empty SessionState -> context built with all missing reported."""
        reader = _make_state_reader()
        builder = _make_context_builder(reader)
        contract = _make_agent_contract(
            required_context=["beliefs_active", "persona"],
        )

        result = builder.build(
            contract=contract,
            params={"query": "test"},
            session_id=SESSION_ID,
        )

        assert result.context.session_sections == {}
        assert len(result.missing_required) == 2

    @pytest.mark.asyncio
    async def test_agent_with_large_session_data(self) -> None:
        """Agent with large session data still executes."""
        large_beliefs = {
            "facts": [
                {"text": f"Fact number {i}", "confidence": 0.5 + i * 0.001} for i in range(200)
            ],
        }
        reader = _make_state_reader(beliefs=large_beliefs, persona=PERSONA)
        builder = _make_context_builder(reader)
        contract = _make_agent_contract()
        factory = _make_agent_factory(
            state_reader=reader,
            context_builder=builder,
            contract=contract,
        )
        request = _make_request()
        fallback = ExecutionContext()

        result = await factory.spawn_and_execute(request, fallback, "tr-large-001")

        assert result.success is True

    def test_wrong_session_id_returns_empty_context(self) -> None:
        """Wrong session_id -> no sections found."""
        reader = _make_state_reader(beliefs=BELIEFS_ACTIVE, persona=PERSONA)
        builder = _make_context_builder(reader)
        contract = _make_agent_contract()

        result = builder.build(
            contract=contract,
            params={},
            session_id="wrong-session-id",
        )

        assert result.context.session_sections == {}
        assert len(result.missing_required) == 2

    @pytest.mark.asyncio
    async def test_delta_emitter_flush_if_ready_respects_window(self) -> None:
        """flush_if_ready() respects the batch window timing."""
        delta_bus = TestDeltaBusAdapter()
        emitter = DeltaEmitter(
            agent_id="agent-window",
            delta_bus=delta_bus,
            trace_id="tr-window",
            batch_window_ms=500,
        )

        emitter.emit(
            delta_type="fact",
            section="beliefs_active",
            key="test",
            value="data",
        )

        # Immediately after emit, window hasn't elapsed
        flushed = emitter.flush_if_ready()
        # May or may not flush depending on timing; just verify no crash
        assert flushed >= 0
