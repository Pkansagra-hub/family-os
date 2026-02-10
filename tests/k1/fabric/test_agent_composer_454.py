"""
Tests for AgentComposer (4.5.4) -- Builder pattern agent composition.

Tests the builder pattern for composing agent CapabilityContract instances:
  - compose_agent() factory returns new builder instance
  - Builder methods: add_tool, set_prompt, set_context, set_budget,
    set_safety_band, set_lifecycle -- all return self for chaining
  - build() terminal method with cross-field validation
  - from_discovery_result() factory auto-composes from ScoredCapability
  - AgentCompositionError for build-time validation failures
  - Protocol satisfaction: ComposerLike and AgentBuilderInstanceLike

Test infrastructure:
  Real adapters for RegistryLike and PromptSystemLike (NO MOCKS).
  TestRegistry -- configurable known tools set with call tracking
  TestPromptSystem -- configurable known templates with call tracking

References:
  - fabric-implementation-plan.md Epic 4.5, Issue 4.5.4
  - meta-agent-creation-integration-proposal.md (auto-union of required_context)

Naming: test_agent_composer_454.py (issue number suffix).
"""

from __future__ import annotations

from typing import List, Optional, Set

import pytest

from k1.fabric.core.agent_builder import DEFAULT_SAFETY_BAND, AgentComposer, AgentCompositionError
from k1.fabric.types import CapabilityContract, ScoredCapability

# ===================================================================
# Test Adapters (real behavior, NO MOCKS)
# ===================================================================


class TestRegistry:
    """
    Test adapter for RegistryLike protocol.

    Pre-populated known tools for contains(). Tracks all calls.
    """

    def __init__(self, *, known_tools: Optional[List[str]] = None) -> None:
        self._known: Set[str] = set(known_tools) if known_tools else set()
        self.contains_calls: List[str] = []

    def contains(self, name: str) -> bool:
        self.contains_calls.append(name)
        return name in self._known


class TestPromptSystem:
    """
    Test adapter for PromptSystemLike protocol.

    Pre-populated known templates for resolve(). Tracks all calls.
    Returns template name as content on success, None on unknown.
    """

    def __init__(self, *, known_templates: Optional[List[str]] = None) -> None:
        self._known: Set[str] = set(known_templates) if known_templates else set()
        self.resolve_calls: List[str] = []

    def resolve(self, template_name: str) -> Optional[str]:
        self.resolve_calls.append(template_name)
        if template_name in self._known:
            return f"Resolved: {template_name}"
        return None


# ===================================================================
# Fixtures
# ===================================================================


@pytest.fixture
def registry() -> TestRegistry:
    """Registry with standard test tools registered."""
    return TestRegistry(
        known_tools=[
            "tool.read.memory_search",
            "tool.write.memory_store",
            "tool.read.web_search",
            "tool.read.calendar",
        ]
    )


@pytest.fixture
def prompt_system() -> TestPromptSystem:
    """Prompt system with standard test templates registered."""
    return TestPromptSystem(
        known_templates=[
            "summarizer_v1",
            "recall_assistant_v1",
            "general_helper_v1",
        ]
    )


@pytest.fixture
def composer(registry: TestRegistry, prompt_system: TestPromptSystem) -> AgentComposer:
    """AgentComposer with standard test deps."""
    return AgentComposer(registry=registry, prompt_system=prompt_system)


@pytest.fixture
def composer_no_prompt(registry: TestRegistry) -> AgentComposer:
    """AgentComposer without prompt system (optional dep)."""
    return AgentComposer(registry=registry, prompt_system=None)


# ===================================================================
# TestAgentCompositionError
# ===================================================================


class TestAgentCompositionError:
    """Tests for AgentCompositionError exception class."""

    def test_single_error(self) -> None:
        exc = AgentCompositionError(["Agent name is required"])
        assert len(exc.errors) == 1
        assert "Agent name is required" in str(exc)
        assert "1 error(s)" in str(exc)

    def test_multiple_errors(self) -> None:
        errors = ["Agent name is required", "At least one domain tag is required"]
        exc = AgentCompositionError(errors)
        assert len(exc.errors) == 2
        assert "2 error(s)" in str(exc)
        for e in errors:
            assert e in str(exc)

    def test_is_exception(self) -> None:
        exc = AgentCompositionError(["test"])
        assert isinstance(exc, Exception)

    def test_errors_list_preserved(self) -> None:
        errors = ["a", "b", "c"]
        exc = AgentCompositionError(errors)
        assert exc.errors == errors


# ===================================================================
# TestComposeAgent -- Factory method
# ===================================================================


class TestComposeAgent:
    """Tests for compose_agent() factory method."""

    def test_returns_new_instance(self, composer: AgentComposer) -> None:
        builder = composer.compose_agent("agent.execute.test", "Test agent", ["memory"])
        assert isinstance(builder, AgentComposer)
        assert builder is not composer

    def test_sets_name_description_domain(self, composer: AgentComposer) -> None:
        builder = composer.compose_agent("agent.execute.test", "Test desc", ["memory", "recall"])
        builder.add_tool("tool.read.memory_search")
        contract = builder.build()
        assert contract.name == "agent.execute.test"
        assert contract.description == "Test desc"
        assert contract.domain == ["memory", "recall"]

    def test_inherits_registry(
        self, registry: TestRegistry, prompt_system: TestPromptSystem
    ) -> None:
        composer = AgentComposer(registry=registry, prompt_system=prompt_system)
        builder = composer.compose_agent("agent.execute.test", "desc", ["d"])
        # Adding a known tool should work (uses inherited registry)
        builder.add_tool("tool.read.memory_search")
        assert "tool.read.memory_search" in registry.contains_calls

    def test_inherits_prompt_system(
        self, registry: TestRegistry, prompt_system: TestPromptSystem
    ) -> None:
        composer = AgentComposer(registry=registry, prompt_system=prompt_system)
        builder = composer.compose_agent("agent.execute.test", "desc", ["d"])
        builder.set_prompt("summarizer_v1")
        assert "summarizer_v1" in prompt_system.resolve_calls

    def test_fresh_builder_has_defaults(self, composer: AgentComposer) -> None:
        builder = composer.compose_agent("agent.execute.test", "desc", ["d"])
        # Tools should be empty (none added yet)
        # Build should fail because no tools added
        with pytest.raises(AgentCompositionError, match="At least one tool"):
            builder.build()


# ===================================================================
# TestAddTool
# ===================================================================


class TestAddTool:
    """Tests for add_tool() builder method."""

    def test_returns_self(self, composer: AgentComposer) -> None:
        builder = composer.compose_agent("agent.execute.test", "desc", ["d"])
        result = builder.add_tool("tool.read.memory_search")
        assert result is builder

    def test_known_tool_succeeds(self, composer: AgentComposer) -> None:
        builder = composer.compose_agent("agent.execute.test", "desc", ["d"])
        builder.add_tool("tool.read.memory_search")
        contract = builder.build()
        assert contract.name == "agent.execute.test"

    def test_unknown_tool_raises_value_error(self, composer: AgentComposer) -> None:
        builder = composer.compose_agent("agent.execute.test", "desc", ["d"])
        with pytest.raises(ValueError, match="Tool not found in registry"):
            builder.add_tool("tool.nonexistent")

    def test_multiple_tools(self, composer: AgentComposer) -> None:
        builder = composer.compose_agent("agent.execute.test", "desc", ["d"])
        builder.add_tool("tool.read.memory_search").add_tool("tool.write.memory_store")
        contract = builder.build()
        assert contract.provider_type == "AGENT"

    def test_registry_called_for_each_tool(
        self, registry: TestRegistry, prompt_system: TestPromptSystem
    ) -> None:
        composer = AgentComposer(registry=registry, prompt_system=prompt_system)
        builder = composer.compose_agent("agent.execute.test", "desc", ["d"])
        builder.add_tool("tool.read.memory_search")
        builder.add_tool("tool.write.memory_store")
        assert registry.contains_calls == [
            "tool.read.memory_search",
            "tool.write.memory_store",
        ]


# ===================================================================
# TestSetPrompt
# ===================================================================


class TestSetPrompt:
    """Tests for set_prompt() builder method."""

    def test_returns_self(self, composer: AgentComposer) -> None:
        builder = composer.compose_agent("agent.execute.test", "desc", ["d"])
        result = builder.set_prompt("summarizer_v1")
        assert result is builder

    def test_known_template_succeeds(self, composer: AgentComposer) -> None:
        builder = composer.compose_agent("agent.execute.test", "desc", ["d"])
        builder.set_prompt("summarizer_v1")
        builder.add_tool("tool.read.memory_search")
        contract = builder.build()
        assert contract.name == "agent.execute.test"

    def test_unknown_template_raises_value_error(self, composer: AgentComposer) -> None:
        builder = composer.compose_agent("agent.execute.test", "desc", ["d"])
        with pytest.raises(ValueError, match="Prompt template not found"):
            builder.set_prompt("nonexistent_template")

    def test_prompt_system_called(
        self, registry: TestRegistry, prompt_system: TestPromptSystem
    ) -> None:
        composer = AgentComposer(registry=registry, prompt_system=prompt_system)
        builder = composer.compose_agent("agent.execute.test", "desc", ["d"])
        builder.set_prompt("summarizer_v1")
        assert "summarizer_v1" in prompt_system.resolve_calls

    def test_no_prompt_system_skips_validation(self, composer_no_prompt: AgentComposer) -> None:
        builder = composer_no_prompt.compose_agent("agent.execute.test", "desc", ["d"])
        # Should not raise even with unknown template
        builder.set_prompt("anything_goes")
        builder.add_tool("tool.read.memory_search")
        contract = builder.build()
        assert contract.name == "agent.execute.test"


# ===================================================================
# TestSetContext
# ===================================================================


class TestSetContext:
    """Tests for set_context() builder method."""

    def test_returns_self(self, composer: AgentComposer) -> None:
        builder = composer.compose_agent("agent.execute.test", "desc", ["d"])
        result = builder.set_context(["beliefs_active"])
        assert result is builder

    def test_required_context_set(self, composer: AgentComposer) -> None:
        builder = composer.compose_agent("agent.execute.test", "desc", ["d"])
        builder.add_tool("tool.read.memory_search")
        builder.set_context(["beliefs_active", "task_context"])
        contract = builder.build()
        assert contract.required_context == ["beliefs_active", "task_context"]

    def test_optional_context_set(self, composer: AgentComposer) -> None:
        builder = composer.compose_agent("agent.execute.test", "desc", ["d"])
        builder.add_tool("tool.read.memory_search")
        builder.set_context(["beliefs_active"], optional=["rhythm_state"])
        contract = builder.build()
        assert contract.required_context == ["beliefs_active"]
        assert contract.optional_context == ["rhythm_state"]

    def test_empty_context(self, composer: AgentComposer) -> None:
        builder = composer.compose_agent("agent.execute.test", "desc", ["d"])
        builder.add_tool("tool.read.memory_search")
        builder.set_context([])
        contract = builder.build()
        assert contract.required_context == []

    def test_context_without_optional(self, composer: AgentComposer) -> None:
        builder = composer.compose_agent("agent.execute.test", "desc", ["d"])
        builder.add_tool("tool.read.memory_search")
        builder.set_context(["task_context"])
        contract = builder.build()
        assert contract.optional_context == []


# ===================================================================
# TestSetBudget
# ===================================================================


class TestSetBudget:
    """Tests for set_budget() builder method."""

    def test_returns_self(self, composer: AgentComposer) -> None:
        builder = composer.compose_agent("agent.execute.test", "desc", ["d"])
        result = builder.set_budget(llm_tokens=4096)
        assert result is builder

    def test_custom_budget(self, composer: AgentComposer) -> None:
        builder = composer.compose_agent("agent.execute.test", "desc", ["d"])
        builder.add_tool("tool.read.memory_search")
        builder.set_budget(llm_tokens=4096, max_tool_calls=5, max_execution_ms=15000)
        contract = builder.build()
        # Budget values are not in CapabilityContract fields,
        # but the build should succeed
        assert contract.provider_type == "AGENT"

    def test_default_budget_values(self, composer: AgentComposer) -> None:
        builder = composer.compose_agent("agent.execute.test", "desc", ["d"])
        builder.add_tool("tool.read.memory_search")
        builder.set_budget()
        contract = builder.build()
        assert contract.provider_type == "AGENT"


# ===================================================================
# TestSetSafetyBand
# ===================================================================


class TestSetSafetyBand:
    """Tests for set_safety_band() builder method."""

    def test_returns_self(self, composer: AgentComposer) -> None:
        builder = composer.compose_agent("agent.execute.test", "desc", ["d"])
        result = builder.set_safety_band("AMBER")
        assert result is builder

    def test_green_band(self, composer: AgentComposer) -> None:
        builder = composer.compose_agent("agent.execute.test", "desc", ["d"])
        builder.add_tool("tool.read.memory_search")
        builder.set_safety_band("GREEN")
        contract = builder.build()
        assert contract.safety_band_min == "GREEN"

    def test_amber_band(self, composer: AgentComposer) -> None:
        builder = composer.compose_agent("agent.execute.test", "desc", ["d"])
        builder.add_tool("tool.read.memory_search")
        builder.set_safety_band("AMBER")
        contract = builder.build()
        assert contract.safety_band_min == "AMBER"

    def test_red_band(self, composer: AgentComposer) -> None:
        builder = composer.compose_agent("agent.execute.test", "desc", ["d"])
        builder.add_tool("tool.read.memory_search")
        builder.set_safety_band("RED")
        contract = builder.build()
        assert contract.safety_band_min == "RED"

    def test_default_band(self, composer: AgentComposer) -> None:
        builder = composer.compose_agent("agent.execute.test", "desc", ["d"])
        builder.add_tool("tool.read.memory_search")
        contract = builder.build()
        assert contract.safety_band_min == DEFAULT_SAFETY_BAND


# ===================================================================
# TestSetLifecycle
# ===================================================================


class TestSetLifecycle:
    """Tests for set_lifecycle() builder method."""

    def test_returns_self(self, composer: AgentComposer) -> None:
        builder = composer.compose_agent("agent.execute.test", "desc", ["d"])
        result = builder.set_lifecycle(ephemeral=False)
        assert result is builder

    def test_non_ephemeral(self, composer: AgentComposer) -> None:
        builder = composer.compose_agent("agent.execute.test", "desc", ["d"])
        builder.add_tool("tool.read.memory_search")
        builder.set_lifecycle(ephemeral=False, session_scoped=False)
        contract = builder.build()
        assert contract.provider_type == "AGENT"

    def test_default_lifecycle(self, composer: AgentComposer) -> None:
        builder = composer.compose_agent("agent.execute.test", "desc", ["d"])
        builder.add_tool("tool.read.memory_search")
        builder.set_lifecycle()
        contract = builder.build()
        assert contract.provider_type == "AGENT"


# ===================================================================
# TestBuild -- Cross-field validation
# ===================================================================


class TestBuild:
    """Tests for build() terminal method and cross-field validation."""

    def test_happy_path_returns_capability_contract(self, composer: AgentComposer) -> None:
        contract = (
            composer.compose_agent("agent.execute.summarizer", "Summarizes text", ["memory"])
            .add_tool("tool.read.memory_search")
            .set_prompt("summarizer_v1")
            .set_context(["beliefs_active"])
            .set_budget(llm_tokens=4096)
            .set_safety_band("GREEN")
            .set_lifecycle(ephemeral=True)
            .build()
        )
        assert isinstance(contract, CapabilityContract)
        assert contract.name == "agent.execute.summarizer"
        assert contract.version == "1.0.0"
        assert contract.domain == ["memory"]
        assert contract.description == "Summarizes text"
        assert contract.provider_type == "AGENT"
        assert contract.safety_band_min == "GREEN"

    def test_contract_is_frozen(self, composer: AgentComposer) -> None:
        contract = (
            composer.compose_agent("agent.execute.test", "desc", ["d"])
            .add_tool("tool.read.memory_search")
            .build()
        )
        with pytest.raises(AttributeError):
            contract.name = "changed"  # type: ignore[misc]

    def test_missing_name_raises(self, registry: TestRegistry) -> None:
        c = AgentComposer(registry=registry)
        c._tools = ["tool.read.memory_search"]
        c._description = "desc"
        c._domain = ["d"]
        with pytest.raises(AgentCompositionError, match="Agent name is required"):
            c.build()

    def test_missing_description_raises(self, registry: TestRegistry) -> None:
        c = AgentComposer(registry=registry)
        c._name = "agent.execute.test"
        c._tools = ["tool.read.memory_search"]
        c._domain = ["d"]
        with pytest.raises(AgentCompositionError, match="Agent description is required"):
            c.build()

    def test_missing_domain_raises(self, registry: TestRegistry) -> None:
        c = AgentComposer(registry=registry)
        c._name = "agent.execute.test"
        c._description = "desc"
        c._tools = ["tool.read.memory_search"]
        c._domain = []
        with pytest.raises(AgentCompositionError, match="At least one domain tag"):
            c.build()

    def test_no_tools_raises(self, composer: AgentComposer) -> None:
        builder = composer.compose_agent("agent.execute.test", "desc", ["d"])
        with pytest.raises(AgentCompositionError, match="At least one tool"):
            builder.build()

    def test_multiple_validation_errors(self, registry: TestRegistry) -> None:
        c = AgentComposer(registry=registry)
        # No name, no description, no domain, no tools
        with pytest.raises(AgentCompositionError) as exc_info:
            c.build()
        assert len(exc_info.value.errors) == 4

    def test_provider_type_always_agent(self, composer: AgentComposer) -> None:
        contract = (
            composer.compose_agent("agent.execute.test", "desc", ["d"])
            .add_tool("tool.read.memory_search")
            .build()
        )
        assert contract.provider_type == "AGENT"

    def test_version_always_1_0_0(self, composer: AgentComposer) -> None:
        contract = (
            composer.compose_agent("agent.execute.test", "desc", ["d"])
            .add_tool("tool.read.memory_search")
            .build()
        )
        assert contract.version == "1.0.0"


# ===================================================================
# TestBuilderChaining
# ===================================================================


class TestBuilderChaining:
    """Tests for fluent builder chaining."""

    def test_full_chain(self, composer: AgentComposer) -> None:
        contract = (
            composer.compose_agent("agent.execute.recall", "Recall agent", ["memory", "recall"])
            .add_tool("tool.read.memory_search")
            .add_tool("tool.write.memory_store")
            .set_prompt("recall_assistant_v1")
            .set_context(["beliefs_active", "interaction_history"], optional=["rhythm_state"])
            .set_budget(llm_tokens=16384, max_tool_calls=20, max_execution_ms=45000)
            .set_safety_band("AMBER")
            .set_lifecycle(ephemeral=False, session_scoped=True)
            .build()
        )
        assert contract.name == "agent.execute.recall"
        assert contract.domain == ["memory", "recall"]
        assert contract.safety_band_min == "AMBER"
        assert contract.required_context == ["beliefs_active", "interaction_history"]
        assert contract.optional_context == ["rhythm_state"]

    def test_minimal_chain(self, composer: AgentComposer) -> None:
        contract = (
            composer.compose_agent("agent.execute.minimal", "Minimal agent", ["general"])
            .add_tool("tool.read.memory_search")
            .build()
        )
        assert contract.name == "agent.execute.minimal"
        assert contract.provider_type == "AGENT"

    def test_methods_return_same_instance(self, composer: AgentComposer) -> None:
        builder = composer.compose_agent("agent.execute.test", "desc", ["d"])
        b1 = builder.add_tool("tool.read.memory_search")
        assert b1 is builder
        b2 = builder.set_prompt("summarizer_v1")
        assert b2 is builder
        b3 = builder.set_context(["beliefs_active"])
        assert b3 is builder
        b4 = builder.set_budget()
        assert b4 is builder
        b5 = builder.set_safety_band()
        assert b5 is builder
        b6 = builder.set_lifecycle()
        assert b6 is builder


# ===================================================================
# TestFromDiscoveryResult
# ===================================================================


class TestFromDiscoveryResult:
    """Tests for from_discovery_result() class factory method."""

    def test_basic_composition(self, registry: TestRegistry) -> None:
        caps = [
            ScoredCapability(
                contract=CapabilityContract(
                    name="tool.read.memory_search",
                    domain=["memory"],
                    safety_band_min="GREEN",
                    required_context=["beliefs_active"],
                ),
                score=0.95,
            ),
        ]
        builder = AgentComposer.from_discovery_result(
            capabilities=caps,
            intent="search memories",
            prompt_template="summarizer_v1",
            registry=registry,
        )
        contract = builder.build()
        assert contract.provider_type == "AGENT"
        assert contract.name == "agent.execute.search_memories"
        assert contract.description == "search memories"

    def test_auto_unions_domains(self, registry: TestRegistry) -> None:
        caps = [
            ScoredCapability(
                contract=CapabilityContract(
                    name="tool.read.memory_search",
                    domain=["memory", "recall"],
                    safety_band_min="GREEN",
                ),
                score=0.95,
            ),
            ScoredCapability(
                contract=CapabilityContract(
                    name="tool.write.memory_store",
                    domain=["memory", "storage"],
                    safety_band_min="GREEN",
                ),
                score=0.90,
            ),
        ]
        builder = AgentComposer.from_discovery_result(
            capabilities=caps,
            intent="manage memories",
            prompt_template="summarizer_v1",
            registry=registry,
        )
        contract = builder.build()
        # Should have union: memory, recall, storage (deduplicated, order preserved)
        assert contract.domain == ["memory", "recall", "storage"]

    def test_auto_computes_max_safety_band(self, registry: TestRegistry) -> None:
        caps = [
            ScoredCapability(
                contract=CapabilityContract(
                    name="tool.read.memory_search",
                    domain=["memory"],
                    safety_band_min="GREEN",
                ),
                score=0.95,
            ),
            ScoredCapability(
                contract=CapabilityContract(
                    name="tool.write.memory_store",
                    domain=["memory"],
                    safety_band_min="AMBER",
                ),
                score=0.90,
            ),
        ]
        builder = AgentComposer.from_discovery_result(
            capabilities=caps,
            intent="memory ops",
            prompt_template="summarizer_v1",
            registry=registry,
        )
        contract = builder.build()
        assert contract.safety_band_min == "AMBER"

    def test_max_safety_band_red(self, registry: TestRegistry) -> None:
        caps = [
            ScoredCapability(
                contract=CapabilityContract(
                    name="tool.read.memory_search",
                    domain=["d"],
                    safety_band_min="GREEN",
                ),
                score=0.95,
            ),
            ScoredCapability(
                contract=CapabilityContract(
                    name="tool.write.memory_store",
                    domain=["d"],
                    safety_band_min="RED",
                ),
                score=0.90,
            ),
            ScoredCapability(
                contract=CapabilityContract(
                    name="tool.read.web_search",
                    domain=["d"],
                    safety_band_min="AMBER",
                ),
                score=0.85,
            ),
        ]
        builder = AgentComposer.from_discovery_result(
            capabilities=caps,
            intent="mixed ops",
            prompt_template="summarizer_v1",
            registry=registry,
        )
        contract = builder.build()
        assert contract.safety_band_min == "RED"

    def test_auto_unions_required_context(self, registry: TestRegistry) -> None:
        caps = [
            ScoredCapability(
                contract=CapabilityContract(
                    name="tool.read.memory_search",
                    domain=["d"],
                    required_context=["beliefs_active", "task_context"],
                    safety_band_min="GREEN",
                ),
                score=0.95,
            ),
            ScoredCapability(
                contract=CapabilityContract(
                    name="tool.write.memory_store",
                    domain=["d"],
                    required_context=["task_context", "interaction_history"],
                    safety_band_min="GREEN",
                ),
                score=0.90,
            ),
        ]
        builder = AgentComposer.from_discovery_result(
            capabilities=caps,
            intent="context test",
            prompt_template="summarizer_v1",
            registry=registry,
        )
        contract = builder.build()
        assert contract.required_context == [
            "beliefs_active",
            "task_context",
            "interaction_history",
        ]

    def test_skips_none_contracts(self, registry: TestRegistry) -> None:
        caps = [
            ScoredCapability(contract=None, score=0.5),
            ScoredCapability(
                contract=CapabilityContract(
                    name="tool.read.memory_search",
                    domain=["memory"],
                    safety_band_min="GREEN",
                ),
                score=0.95,
            ),
        ]
        builder = AgentComposer.from_discovery_result(
            capabilities=caps,
            intent="skip none test",
            prompt_template="summarizer_v1",
            registry=registry,
        )
        contract = builder.build()
        assert contract.name == "agent.execute.skip_none_test"

    def test_empty_capabilities_fails_build(self, registry: TestRegistry) -> None:
        builder = AgentComposer.from_discovery_result(
            capabilities=[],
            intent="empty test",
            prompt_template="summarizer_v1",
            registry=registry,
        )
        with pytest.raises(AgentCompositionError, match="At least one tool"):
            builder.build()

    def test_sanitizes_intent_for_name(self, registry: TestRegistry) -> None:
        caps = [
            ScoredCapability(
                contract=CapabilityContract(
                    name="tool.read.memory_search",
                    domain=["d"],
                    safety_band_min="GREEN",
                ),
                score=0.95,
            ),
        ]
        builder = AgentComposer.from_discovery_result(
            capabilities=caps,
            intent="Search My Memories!!! Now @#$",
            prompt_template="summarizer_v1",
            registry=registry,
        )
        contract = builder.build()
        assert contract.name.startswith("agent.execute.")
        # Should be sanitized to lowercase alphanum + underscore
        suffix = contract.name.replace("agent.execute.", "")
        assert suffix.isidentifier() or all(c.isalnum() or c == "_" for c in suffix)

    def test_default_domain_when_empty(self, registry: TestRegistry) -> None:
        caps = [
            ScoredCapability(
                contract=CapabilityContract(
                    name="tool.read.memory_search",
                    domain=[],
                    safety_band_min="GREEN",
                ),
                score=0.95,
            ),
        ]
        builder = AgentComposer.from_discovery_result(
            capabilities=caps,
            intent="no domain",
            prompt_template="summarizer_v1",
            registry=registry,
        )
        contract = builder.build()
        assert contract.domain == ["general"]

    def test_with_prompt_system(
        self, registry: TestRegistry, prompt_system: TestPromptSystem
    ) -> None:
        caps = [
            ScoredCapability(
                contract=CapabilityContract(
                    name="tool.read.memory_search",
                    domain=["d"],
                    safety_band_min="GREEN",
                ),
                score=0.95,
            ),
        ]
        builder = AgentComposer.from_discovery_result(
            capabilities=caps,
            intent="with prompt system",
            prompt_template="summarizer_v1",
            registry=registry,
            prompt_system=prompt_system,
        )
        contract = builder.build()
        assert contract.provider_type == "AGENT"

    def test_further_customization_after_factory(self, registry: TestRegistry) -> None:
        caps = [
            ScoredCapability(
                contract=CapabilityContract(
                    name="tool.read.memory_search",
                    domain=["memory"],
                    safety_band_min="GREEN",
                ),
                score=0.95,
            ),
        ]
        builder = AgentComposer.from_discovery_result(
            capabilities=caps,
            intent="customizable",
            prompt_template="summarizer_v1",
            registry=registry,
        )
        # Can further customize after factory
        builder.set_safety_band("AMBER")
        builder.set_budget(llm_tokens=16384)
        builder.set_lifecycle(ephemeral=False)
        contract = builder.build()
        assert contract.safety_band_min == "AMBER"

    def test_all_green_stays_green(self, registry: TestRegistry) -> None:
        caps = [
            ScoredCapability(
                contract=CapabilityContract(
                    name="tool.read.memory_search",
                    domain=["d"],
                    safety_band_min="GREEN",
                ),
                score=0.95,
            ),
            ScoredCapability(
                contract=CapabilityContract(
                    name="tool.write.memory_store",
                    domain=["d"],
                    safety_band_min="GREEN",
                ),
                score=0.90,
            ),
        ]
        builder = AgentComposer.from_discovery_result(
            capabilities=caps,
            intent="all green",
            prompt_template="tpl",
            registry=registry,
        )
        contract = builder.build()
        assert contract.safety_band_min == "GREEN"


# ===================================================================
# TestProtocolSatisfaction
# ===================================================================


class TestProtocolSatisfaction:
    """Tests that AgentComposer satisfies the defined protocols."""

    def test_satisfies_composer_like(self, composer: AgentComposer) -> None:
        from k1.fabric.core.agent_builder import ComposerLike

        assert isinstance(composer, ComposerLike)

    def test_builder_from_compose_agent_has_builder_methods(self, composer: AgentComposer) -> None:
        builder = composer.compose_agent("agent.execute.test", "desc", ["d"])
        assert hasattr(builder, "add_tool")
        assert hasattr(builder, "set_prompt")
        assert hasattr(builder, "set_context")
        assert hasattr(builder, "set_budget")
        assert hasattr(builder, "set_safety_band")
        assert hasattr(builder, "set_lifecycle")
        assert hasattr(builder, "build")

    def test_compose_agent_return_type(self, composer: AgentComposer) -> None:
        builder = composer.compose_agent("agent.execute.test", "desc", ["d"])
        assert isinstance(builder, AgentComposer)


# ===================================================================
# TestRepr
# ===================================================================


class TestRepr:
    """Tests for __repr__ output."""

    def test_repr_uninitialized(self, composer: AgentComposer) -> None:
        r = repr(composer)
        assert "AgentComposer(" in r
        assert "initialized=False" in r

    def test_repr_initialized(self, composer: AgentComposer) -> None:
        builder = composer.compose_agent("agent.execute.test", "desc", ["d"])
        r = repr(builder)
        assert "agent.execute.test" in r
        assert "initialized=True" in r

    def test_repr_with_tools(self, composer: AgentComposer) -> None:
        builder = composer.compose_agent("agent.execute.test", "desc", ["d"])
        builder.add_tool("tool.read.memory_search")
        builder.add_tool("tool.write.memory_store")
        r = repr(builder)
        assert "tools=2" in r


# ===================================================================
# TestCoreExports
# ===================================================================


class TestCoreExports:
    """Tests that AgentComposer exports are accessible from k1.fabric.core."""

    def test_agent_composer_importable(self) -> None:
        from k1.fabric.core import AgentComposer as AC

        assert AC is not None

    def test_agent_composition_error_importable(self) -> None:
        from k1.fabric.core import AgentCompositionError as ACE

        assert ACE is not None

    def test_agent_composer_in_all(self) -> None:
        from k1.fabric.core import __all__

        assert "AgentComposer" in __all__
        assert "AgentCompositionError" in __all__

    def test_all_list_count(self) -> None:
        from k1.fabric.core import __all__

        # 15 prior (M2) + 18 (4.2) + 5 (4.5.1) + 2 (4.5.4) + 8 (4.5.2) + 9 (4.5.3) + 1 (4.5.6) = 58
        assert len(__all__) == 58
