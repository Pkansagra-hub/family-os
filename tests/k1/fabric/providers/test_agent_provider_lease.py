"""M4-E2 agent grounding lease coverage."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from k1.fabric.core.context_builder import ContextBuilder
from k1.fabric.providers.agent_provider import AgentFactory, AgentProvider, AgentResult
from k1.fabric.types import (
    AgentContract,
    CapabilityRequest,
    ExecutionContext,
    ProviderConfig,
)
from k1.grounding.factory import GroundingFactory
from k1.grounding.kernel.handle import build_grounding_handle


def _contract(**overrides: Any) -> AgentContract:
    defaults: dict[str, Any] = {
        "name": "agent.execute.lease_probe",
        "version": "1.0.0",
        "domain": ["TEST"],
        "description": "Lease probe agent.",
        "provider_type": "AGENT",
        "provider_id": "agent-provider",
        "prompt_template": "lease_probe_v1",
        "tools_granted": [],
        "llm_budget_tokens": 512,
        "max_tool_calls": 0,
        "max_execution_time_ms": 30000,
        "lease": {"ttl_seconds": 30, "allow_refresh": True},
    }
    defaults.update(overrides)
    return AgentContract(**defaults)


class _CapturingAgentFactory:
    def __init__(self, contract: AgentContract) -> None:
        self.contract = contract
        self.contexts: list[ExecutionContext] = []

    def _load_contract(self, capability_name: str) -> AgentContract | None:
        return self.contract if capability_name == self.contract.name else None

    async def spawn_and_execute(
        self,
        request: CapabilityRequest,
        context: ExecutionContext,
        trace_id: str,
    ) -> AgentResult:
        self.contexts.append(context)
        return AgentResult(success=True, output={"ok": True}, agent_id="agent-1")


def _request(contract: AgentContract) -> CapabilityRequest:
    return CapabilityRequest(
        request_id="req-1",
        capability_name=contract.name,
        caller="test",
        session_id="s1",
        trace_id="trace-1",
    )


async def test_agent_provider_issues_grounding_lease_before_spawn() -> None:
    contract = _contract()
    factory = _CapturingAgentFactory(contract)
    bundle = GroundingFactory.create_standalone()
    grounding = build_grounding_handle(bundle, session_id="s1", actor_id="actor-1")
    provider = AgentProvider(
        ProviderConfig(provider_id="agent-provider", provider_type="AGENT"),
        agent_factory=factory,
        grounding_port=grounding,
        capability_names=[contract.name],
    )
    context = ExecutionContext(
        session_sections={"context_override": {"grounding_invocation": {}}},
        trace_id="trace-1",
    )

    result = await provider.execute(_request(contract), context, "trace-1")

    assert result.success is True
    captured = factory.contexts[0]
    lease = captured.grounding_lease
    assert lease is not None
    assert lease.task_scope == contract.name
    ttl = datetime.fromisoformat(lease.expires_at_utc) - datetime.fromisoformat(lease.issued_at_utc)
    assert int(ttl.total_seconds()) == 30
    invocation = captured.session_sections["context_override"]["grounding_invocation"]
    assert invocation["grounding_lease_id"] == lease.lease_id
    assert invocation["grounding_lease_expires_at_utc"] == lease.expires_at_utc
    assert captured.session_sections["agent_grounding_lease"]["lease_id"] == lease.lease_id


async def test_agent_provider_degrades_without_grounding_port() -> None:
    contract = _contract()
    factory = _CapturingAgentFactory(contract)
    provider = AgentProvider(
        ProviderConfig(provider_id="agent-provider", provider_type="AGENT"),
        agent_factory=factory,
        capability_names=[contract.name],
    )

    result = await provider.execute(_request(contract), ExecutionContext(), "trace-1")

    assert result.success is True
    assert factory.contexts[0].grounding_lease is None


async def test_agent_factory_preserves_provider_lease_when_rebuilding_context() -> None:
    contract = _contract()
    bundle = GroundingFactory.create_standalone()
    grounding = build_grounding_handle(bundle, session_id="s1", actor_id="actor-1")
    envelope = await grounding.create_envelope("s1", "agent", trace_id="trace-1")
    lease = await grounding.build_agent_lease(envelope, task_scope=contract.name, ttl_seconds=30)
    factory = AgentFactory(
        context_builder=ContextBuilder(),
        contract_loader=lambda _name: contract,
    )
    fallback = ExecutionContext(
        session_sections={
            "context_override": {"grounding_invocation": {"grounding_lease_id": lease.lease_id}}
        },
        trace_id="trace-1",
        grounding_lease=lease,
    )

    agent = factory._spawn(
        contract,
        fallback,
        {},
        "trace-1",
        session_id="s1",
        context_override={"prompt_variables": {"x": 1}},
    )

    assert agent.context.grounding_lease is lease
    override = agent.context.session_sections["context_override"]
    assert override["grounding_invocation"]["grounding_lease_id"] == lease.lease_id
    assert override["prompt_variables"] == {"x": 1}
