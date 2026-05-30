"""Proof-of-path test for NativeToolProvider (M15 §E15.-1 AC).

Acceptance criterion (M15 R-8 / §E15.-1):

  A request issued through the Fabric capability surface, addressed to a
  family-tool capability, MUST flow through the manifest translator ->
  CapabilityRegistry -> NativeToolProvider -> IToolService.dispatch path
  and return a CapabilityResult that proves the path executed end-to-end.

This test does not exercise full Fabric resolution wiring (that is
§E15.0.10 boot work) -- it constructs the minimum slice required to
prove the contract: register a service, build a provider, drive it with
a CapabilityRequest, assert the result.
"""

from __future__ import annotations

import pytest

from k1.fabric.core.registry import CapabilityRegistry
from k1.fabric.manifest_translator import (
    NATIVE_PROVIDER_ID,
    NATIVE_PROVIDER_TYPE,
    register_definition,
)
from k1.fabric.providers.base_provider import CapabilityProvider
from k1.fabric.providers.native_tool_provider import (
    InMemoryToolRegistry,
    NativeToolProvider,
)
from k1.fabric.types import (
    CapabilityRequest,
    ExecutionContext,
    ProviderConfig,
    ProviderStatus,
)
from k1.tools.family.definition import ActionSpec, FieldSpec, ToolDefinition
from tests.k1.tools.family._stubs import PingToolService

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def service() -> PingToolService:
    return PingToolService()


@pytest.fixture
def tool_registry(service: PingToolService) -> InMemoryToolRegistry:
    reg = InMemoryToolRegistry()
    reg.register(service)
    return reg


@pytest.fixture
def fabric_registry(service: PingToolService) -> CapabilityRegistry:
    reg = CapabilityRegistry()
    register_definition(service.DEFINITION, reg)
    return reg


@pytest.fixture
def provider(tool_registry: InMemoryToolRegistry) -> NativeToolProvider:
    return NativeToolProvider(
        config=ProviderConfig(
            provider_id=NATIVE_PROVIDER_ID,
            provider_type=NATIVE_PROVIDER_TYPE,
            endpoint="local://k1_native_tools",
        ),
        registry=tool_registry,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestNativeToolProviderPath:
    def test_satisfies_capability_provider_protocol(self, provider: NativeToolProvider) -> None:
        # CapabilityProvider is not runtime_checkable; assert structural shape.
        assert callable(getattr(provider, "execute", None))
        assert callable(getattr(provider, "health_check", None))
        assert callable(getattr(provider, "capabilities", None))
        _ = CapabilityProvider  # imported so static-type contract stays referenced

    def test_capabilities_lists_every_registered_action(self, provider: NativeToolProvider) -> None:
        names = set(provider.capabilities())
        assert names == {
            "tool.execute.ping.ping",
            "tool.read.ping.list_pings",
        }

    async def test_health_check_healthy_when_services_registered(
        self, provider: NativeToolProvider
    ) -> None:
        health = await provider.health_check()
        assert health.status == ProviderStatus.HEALTHY.value
        assert health.provider_id == NATIVE_PROVIDER_ID

    async def test_health_check_degraded_when_empty(self) -> None:
        empty = InMemoryToolRegistry()
        provider = NativeToolProvider(
            config=ProviderConfig(
                provider_id=NATIVE_PROVIDER_ID, provider_type=NATIVE_PROVIDER_TYPE
            ),
            registry=empty,
        )
        health = await provider.health_check()
        assert health.status == ProviderStatus.DEGRADED.value

    async def test_execute_routes_to_service_dispatch(
        self,
        provider: NativeToolProvider,
        service: PingToolService,
    ) -> None:
        request = CapabilityRequest(
            capability_name="tool.execute.ping.ping",
            params={"message": "hello"},
            caller="test-runner",
            caller_id="user-42",
            session_id="sess-1",
        )
        ctx = ExecutionContext(trace_id=request.trace_id)

        result = await provider.execute(request, ctx, request.trace_id)

        assert result.success is True
        assert result.data == {"pong": True, "echo": "hello"}
        assert result.provider_id == NATIVE_PROVIDER_ID
        # Service saw the dispatch with a fully-populated WriteContext.
        assert len(service.calls) == 1
        action_name, params, wctx = service.calls[0]
        assert action_name == "ping"
        assert params == {"message": "hello"}
        assert wctx.user_id == "user-42"
        assert wctx.session_id == "sess-1"
        assert wctx.trace_id == request.trace_id
        assert wctx.band == "GREEN"

    async def test_execute_carries_prompt_metadata_in_write_context_extras(
        self,
        provider: NativeToolProvider,
        service: PingToolService,
    ) -> None:
        request = CapabilityRequest(
            capability_name="tool.execute.ping.ping",
            params={"message": "hello"},
            caller="test-runner",
            caller_id="user-42",
            session_id="sess-1",
        )
        ctx = ExecutionContext(
            trace_id=request.trace_id,
            prompt="Use diagnostic procedure.",
            session_sections={
                "context_override": {
                    "activity_profile": "diagnostic.v1",
                    "prompt_template": "diagnostic_activity_v1",
                }
            },
        )

        result = await provider.execute(request, ctx, request.trace_id)

        assert result.success is True
        action_name, params, wctx = service.calls[0]
        assert action_name == "ping"
        assert params == {"message": "hello"}
        assert wctx.extras["fabric_prompt_metadata"] == {
            "__system_instructions__": "Use diagnostic procedure.",
            "__activity_profile__": "diagnostic.v1",
            "__prompt_template__": "diagnostic_activity_v1",
        }

    async def test_execute_propagates_service_failure_envelope(
        self,
        provider: NativeToolProvider,
        service: PingToolService,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        async def fail_dispatch(action, params, ctx):  # type: ignore[no-untyped-def]
            return {
                "success": False,
                "error_code": "dispatch_failed",
                "error_message": "missing required field: title",
            }

        monkeypatch.setattr(service, "dispatch", fail_dispatch)
        request = CapabilityRequest(
            capability_name="tool.execute.ping.ping",
            params={"message": "hello"},
            caller="test-runner",
        )
        ctx = ExecutionContext(trace_id=request.trace_id)

        result = await provider.execute(request, ctx, request.trace_id)

        assert result.success is False
        assert result.error is not None
        assert result.error.code == "dispatch_failed"
        assert "missing required field" in result.error.message

    async def test_execute_read_action(
        self,
        provider: NativeToolProvider,
        service: PingToolService,
    ) -> None:
        request = CapabilityRequest(
            capability_name="tool.read.ping.list_pings",
            caller="test-runner",
        )
        ctx = ExecutionContext(trace_id=request.trace_id)

        result = await provider.execute(request, ctx, request.trace_id)

        assert result.success is True
        assert result.data == {"items": [], "count": 0}

    async def test_execute_unknown_adapter_returns_failure(
        self, provider: NativeToolProvider
    ) -> None:
        request = CapabilityRequest(
            capability_name="tool.execute.unknown_adapter.do_something",
            caller="test-runner",
        )
        ctx = ExecutionContext(trace_id=request.trace_id)

        result = await provider.execute(request, ctx, request.trace_id)

        assert result.success is False
        assert result.error is not None
        assert result.error.code == "adapter_not_found"
        assert result.error.retriable is False

    async def test_execute_unknown_action_returns_failure(
        self, provider: NativeToolProvider
    ) -> None:
        request = CapabilityRequest(
            capability_name="tool.execute.ping.does_not_exist",
            caller="test-runner",
        )
        ctx = ExecutionContext(trace_id=request.trace_id)

        result = await provider.execute(request, ctx, request.trace_id)

        assert result.success is False
        assert result.error is not None
        assert result.error.code == "action_not_found"

    async def test_execute_invalid_capability_name(self, provider: NativeToolProvider) -> None:
        request = CapabilityRequest(
            capability_name="tool.execute.malformed",
            caller="test-runner",
        )
        ctx = ExecutionContext(trace_id=request.trace_id)

        result = await provider.execute(request, ctx, request.trace_id)
        assert result.success is False
        assert result.error is not None
        assert result.error.code == "invalid_capability_name"

    async def test_execute_propagates_session_band_to_context(
        self,
        provider: NativeToolProvider,
        service: PingToolService,
    ) -> None:
        request = CapabilityRequest(
            capability_name="tool.execute.ping.ping",
            caller="test-runner",
            caller_id="u9",
            safety_band="AMBER",
        )
        ctx = ExecutionContext(
            trace_id=request.trace_id,
            session_sections={"control": {"role": "guardian", "band": "AMBER"}},
        )

        result = await provider.execute(request, ctx, request.trace_id)

        assert result.success is True
        _, _, wctx = service.calls[0]
        assert wctx.role == "guardian"
        assert wctx.band == "AMBER"


class TestFabricRegistryIntegration:
    """The translator + registry path: every action gets registered and looked up."""

    def test_lookup_through_fabric_registry(self, fabric_registry: CapabilityRegistry) -> None:
        ping = fabric_registry.lookup("tool.execute.ping.ping")
        assert ping is not None
        assert ping.provider_type == NATIVE_PROVIDER_TYPE
        assert ping.provider_id == NATIVE_PROVIDER_ID

        listing = fabric_registry.lookup("tool.read.ping.list_pings")
        assert listing is not None
        assert "family" in listing.domain

    def test_lookup_preserves_prompt_profile_metadata(self) -> None:
        action = ActionSpec(
            name="record_ping",
            kind="write",
            summary="Record a ping",
            params=[FieldSpec(name="message", type="string", required=True)],
            prompt_template="diagnostic_activity_v1",
            tool_instructions="Record only the requested ping payload.",
        )
        definition = ToolDefinition(
            adapter_id="diag_profile",
            summary="Diagnostic profile adapter",
            tables_sql=(
                "CREATE TABLE IF NOT EXISTS diag_profile_schema_version "
                "(version INTEGER PRIMARY KEY);"
            ),
            activity_profile="diagnostic.default.v1",
            domain_tags=["diagnostic"],
            actions=[action],
        )
        registry = CapabilityRegistry()

        register_definition(definition, registry)
        contract = registry.lookup("tool.execute.diag_profile.record_ping")

        assert contract is not None
        assert contract.prompt_template == "diagnostic_activity_v1"
        assert contract.activity_profile == "diagnostic.default.v1"
        assert contract.tool_instructions == "Record only the requested ping payload."
        assert "diagnostic" in contract.domain
