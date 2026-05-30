"""M2 Plugin Architecture -- Test IProviderPlugin & Supporting Types [F20].

Tests the IProviderPlugin protocol, NormalizedRequest, ProviderResponse,
ProviderChunk, ProviderHealth dataclasses, frozen immutability, defaults,
and Protocol runtime_checkable behavior.

Covers:
  - NormalizedRequest: all 14 fields, defaults, frozen
  - ProviderResponse: all 7 fields, defaults, frozen
  - ProviderChunk: all 4 fields, defaults, frozen
  - ProviderHealth: all 4 fields, defaults, frozen
  - IProviderPlugin: runtime_checkable, 7-method contract, structural subtyping
  - Re-exports from plugins/__init__.py

NO MOCKS (except for Protocol conformance checks with minimal stubs).
"""

from __future__ import annotations

import dataclasses
from typing import AsyncIterator, List

import pytest

from k1.model_hub.manifest import ProviderManifest
from k1.model_hub.plugins.base import (
    IProviderPlugin,
    NormalizedRequest,
    ProviderChunk,
    ProviderHealth,
    ProviderResponse,
)
from k1.model_hub.types import (
    CapabilityType,
    FinishReason,
    HealthStatus,
    Message,
    ToolCallResult,
)

# ===========================================================================
# NormalizedRequest Tests
# ===========================================================================


class TestNormalizedRequest:
    """Tests for NormalizedRequest dataclass."""

    def test_defaults(self) -> None:
        nr = NormalizedRequest(capability=CapabilityType.CHAT)
        assert nr.capability == CapabilityType.CHAT
        assert nr.messages == []
        assert nr.system_prompt is None
        assert nr.tools is None
        assert nr.tool_choice is None
        assert nr.output_schema is None
        assert nr.max_tokens == 65535
        assert nr.timeout_ms == 30000
        assert nr.temperature == 0.7
        assert nr.model_id == ""
        assert nr.trace_id == ""
        assert nr.consumer_id == ""
        assert nr.reasoning_effort is None
        assert nr.extra == {}

    def test_all_fields(self) -> None:
        msgs = [Message(role="user", content="hello")]
        tools = [{"name": "get_weather", "description": "Get weather", "parameters": {}}]
        schema = {"type": "object", "properties": {"name": {"type": "string"}}}
        extra = {"custom_key": "custom_value"}
        nr = NormalizedRequest(
            capability=CapabilityType.TOOL_CALL,
            messages=msgs,
            system_prompt="You are helpful.",
            tools=tools,
            tool_choice="auto",
            output_schema=schema,
            max_tokens=4096,
            timeout_ms=10000,
            temperature=0.5,
            model_id="gpt-4o",
            trace_id="trace-123",
            consumer_id="concierge",
            reasoning_effort="high",
            extra=extra,
        )
        assert nr.capability == CapabilityType.TOOL_CALL
        assert len(nr.messages) == 1
        assert nr.system_prompt == "You are helpful."
        assert nr.tools == tools
        assert nr.tool_choice == "auto"
        assert nr.output_schema == schema
        assert nr.max_tokens == 4096
        assert nr.timeout_ms == 10000
        assert nr.temperature == 0.5
        assert nr.model_id == "gpt-4o"
        assert nr.trace_id == "trace-123"
        assert nr.consumer_id == "concierge"
        assert nr.reasoning_effort == "high"
        assert nr.extra == extra

    def test_frozen(self) -> None:
        nr = NormalizedRequest(capability=CapabilityType.CHAT)
        with pytest.raises(dataclasses.FrozenInstanceError):
            nr.capability = CapabilityType.EMBED  # type: ignore[misc]

    def test_is_dataclass(self) -> None:
        assert dataclasses.is_dataclass(NormalizedRequest)

    def test_field_count(self) -> None:
        fields = dataclasses.fields(NormalizedRequest)
        assert len(fields) == 14


# ===========================================================================
# ProviderResponse Tests
# ===========================================================================


class TestProviderResponse:
    """Tests for ProviderResponse dataclass."""

    def test_defaults(self) -> None:
        pr = ProviderResponse()
        assert pr.text == ""
        assert pr.tool_calls is None
        assert pr.prompt_tokens == 0
        assert pr.completion_tokens == 0
        assert pr.model_id == ""
        assert pr.finish_reason == FinishReason.STOP
        assert pr.raw_response is None

    def test_all_fields(self) -> None:
        tool_calls = [ToolCallResult(id="tc-1", name="get_weather", arguments='{"city":"NYC"}')]
        pr = ProviderResponse(
            text="It is sunny in NYC.",
            tool_calls=tool_calls,
            prompt_tokens=100,
            completion_tokens=50,
            model_id="gpt-4o",
            finish_reason=FinishReason.TOOL_CALLS,
            raw_response={"id": "resp-1"},
        )
        assert pr.text == "It is sunny in NYC."
        assert pr.tool_calls is not None
        assert len(pr.tool_calls) == 1
        assert pr.prompt_tokens == 100
        assert pr.completion_tokens == 50
        assert pr.model_id == "gpt-4o"
        assert pr.finish_reason == FinishReason.TOOL_CALLS
        assert pr.raw_response == {"id": "resp-1"}

    def test_frozen(self) -> None:
        pr = ProviderResponse()
        with pytest.raises(dataclasses.FrozenInstanceError):
            pr.text = "changed"  # type: ignore[misc]

    def test_is_dataclass(self) -> None:
        assert dataclasses.is_dataclass(ProviderResponse)

    def test_field_count(self) -> None:
        fields = dataclasses.fields(ProviderResponse)
        assert len(fields) == 7


# ===========================================================================
# ProviderChunk Tests
# ===========================================================================


class TestProviderChunk:
    """Tests for ProviderChunk dataclass."""

    def test_defaults(self) -> None:
        pc = ProviderChunk()
        assert pc.text == ""
        assert pc.done is False
        assert pc.tool_calls is None
        assert pc.metadata is None

    def test_final_chunk(self) -> None:
        pc = ProviderChunk(text="final", done=True, metadata={"tokens": 42})
        assert pc.text == "final"
        assert pc.done is True
        assert pc.metadata == {"tokens": 42}

    def test_with_tool_calls(self) -> None:
        tc = [ToolCallResult(id="tc-1", name="fn", arguments="{}")]
        pc = ProviderChunk(tool_calls=tc)
        assert pc.tool_calls is not None
        assert len(pc.tool_calls) == 1

    def test_frozen(self) -> None:
        pc = ProviderChunk()
        with pytest.raises(dataclasses.FrozenInstanceError):
            pc.done = True  # type: ignore[misc]

    def test_is_dataclass(self) -> None:
        assert dataclasses.is_dataclass(ProviderChunk)

    def test_field_count(self) -> None:
        fields = dataclasses.fields(ProviderChunk)
        assert len(fields) == 6


# ===========================================================================
# ProviderHealth Tests
# ===========================================================================


class TestProviderHealth:
    """Tests for ProviderHealth dataclass."""

    def test_defaults(self) -> None:
        ph = ProviderHealth()
        assert ph.status == HealthStatus.HEALTHY
        assert ph.latency_ms == 0
        assert ph.error_rate == 0.0
        assert ph.details == ""

    def test_all_fields(self) -> None:
        ph = ProviderHealth(
            status=HealthStatus.DEGRADED,
            latency_ms=150,
            error_rate=0.05,
            details="High latency on /chat/completions",
        )
        assert ph.status == HealthStatus.DEGRADED
        assert ph.latency_ms == 150
        assert ph.error_rate == 0.05
        assert "High latency" in ph.details

    def test_unhealthy(self) -> None:
        ph = ProviderHealth(status=HealthStatus.UNHEALTHY, error_rate=0.5)
        assert ph.status == HealthStatus.UNHEALTHY

    def test_frozen(self) -> None:
        ph = ProviderHealth()
        with pytest.raises(dataclasses.FrozenInstanceError):
            ph.status = HealthStatus.UNHEALTHY  # type: ignore[misc]

    def test_is_dataclass(self) -> None:
        assert dataclasses.is_dataclass(ProviderHealth)

    def test_field_count(self) -> None:
        fields = dataclasses.fields(ProviderHealth)
        assert len(fields) == 4


# ===========================================================================
# IProviderPlugin Protocol Tests
# ===========================================================================


class _ConformingPlugin:
    """Minimal plugin that satisfies IProviderPlugin structurally."""

    async def initialize(self, manifest: ProviderManifest) -> None:
        pass

    def supports(self, capability: CapabilityType) -> bool:
        return True

    async def execute(self, request: NormalizedRequest) -> ProviderResponse:
        return ProviderResponse(text="ok")

    async def stream_execute(self, request: NormalizedRequest) -> AsyncIterator[ProviderChunk]:
        yield ProviderChunk(text="ok", done=True)

    def estimate_tokens(self, messages: List[Message]) -> int:
        return 0

    async def health_check(self) -> ProviderHealth:
        return ProviderHealth()

    async def close(self) -> None:
        pass


class _NonConformingPlugin:
    """Plugin missing required methods."""

    def supports(self, capability: CapabilityType) -> bool:
        return True


class TestIProviderPlugin:
    """Tests for IProviderPlugin Protocol."""

    def test_runtime_checkable(self) -> None:
        assert isinstance(_ConformingPlugin(), IProviderPlugin)

    def test_non_conforming_fails(self) -> None:
        assert not isinstance(_NonConformingPlugin(), IProviderPlugin)

    def test_protocol_has_7_methods(self) -> None:
        expected = {
            "initialize",
            "supports",
            "execute",
            "stream_execute",
            "estimate_tokens",
            "health_check",
            "close",
        }
        # Get all non-dunder callable members from Protocol annotations
        members = {
            name
            for name in dir(IProviderPlugin)
            if not name.startswith("_") and callable(getattr(IProviderPlugin, name, None))
        }
        assert expected.issubset(members)

    def test_conforming_supports(self) -> None:
        plugin = _ConformingPlugin()
        assert plugin.supports(CapabilityType.CHAT) is True

    def test_conforming_estimate_tokens(self) -> None:
        plugin = _ConformingPlugin()
        msgs = [Message(role="user", content="hello")]
        assert plugin.estimate_tokens(msgs) == 0


# ===========================================================================
# Re-exports from plugins/__init__.py
# ===========================================================================


class TestPluginsPackageReexports:
    """Verify plugins package re-exports all public types."""

    def test_reexport_iprovider_plugin(self) -> None:
        from k1.model_hub.plugins import IProviderPlugin as IP

        assert IP is IProviderPlugin

    def test_reexport_normalized_request(self) -> None:
        from k1.model_hub.plugins import NormalizedRequest as NR

        assert NR is NormalizedRequest

    def test_reexport_provider_response(self) -> None:
        from k1.model_hub.plugins import ProviderResponse as PR

        assert PR is ProviderResponse

    def test_reexport_provider_chunk(self) -> None:
        from k1.model_hub.plugins import ProviderChunk as PC

        assert PC is ProviderChunk

    def test_reexport_provider_health(self) -> None:
        from k1.model_hub.plugins import ProviderHealth as PH

        assert PH is ProviderHealth
