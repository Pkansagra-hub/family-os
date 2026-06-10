"""Epic 16.6 — Verify resolve_situation works end-to-end.

Tests the full chain: schema → allowlist → handler → adapter → Fabric.

Run:
    pytest tests/k1/concierge/actors/test_back_resolve_situation_tool.py -v -p no:xdist -p no:cacheprovider
"""

from __future__ import annotations

import pytest

from k1.concierge.adapters.fabric_dispatch import FabricDispatchAdapter
from k1.concierge.llm.types import ToolSchema
from k1.concierge.tools.implementations import (
    TOOL_REGISTRY,
    ToolContext,
    execute_resolve_situation,
)
from k1.concierge.tools.schemas_back import (
    _BACK_SIMPLE_LIST,
    BACK_TIER_ALLOWLISTS,
    BACK_TOOL_SCHEMAS,
    RESOLVE_SITUATION_SCHEMA,
)

# ── Schema tests ─────────────────────────────────────────────────────────


class TestResolveSituationSchema:
    def test_schema_valid(self):
        assert isinstance(RESOLVE_SITUATION_SCHEMA, ToolSchema)
        assert RESOLVE_SITUATION_SCHEMA.name == "resolve_situation"
        assert RESOLVE_SITUATION_SCHEMA.actor == "back"

    def test_in_simple_allowlist(self):
        assert "resolve_situation" in _BACK_SIMPLE_LIST

    def test_in_all_tier_allowlists(self):
        for tier in ("simple", "LOW", "MEDIUM", "HIGH", "plan"):
            assert "resolve_situation" in BACK_TIER_ALLOWLISTS[tier]

    def test_in_back_schemas(self):
        names = [s.name for s in BACK_TOOL_SCHEMAS]
        assert "resolve_situation" in names


# ── Handler tests ────────────────────────────────────────────────────────


class TestResolveSituationHandler:
    def test_handler_registered(self):
        assert "resolve_situation" in TOOL_REGISTRY

    @pytest.mark.asyncio
    async def test_missing_frame_returns_error(self):
        result = await execute_resolve_situation({}, _mock_ctx())
        assert result.status == "error"
        assert "frame" in result.error

    @pytest.mark.asyncio
    async def test_dispatch_not_wired_returns_error(self):
        result = await execute_resolve_situation(
            {"frame": {"intents": []}}, _mock_ctx(dispatch=None)
        )
        assert result.status == "error"
        assert "dispatch not wired" in result.error

    @pytest.mark.asyncio
    async def test_auto_fills_identity_and_calls_dispatch(self):
        called_with = {}

        class _D:
            async def resolve_situation(self, payload):
                called_with.update(payload)
                return {"verdict": "can_execute", "resolution_id": "r-001"}

        result = await execute_resolve_situation(
            {"frame": {"intents": [{"action": "schedule dentist"}]}},
            _mock_ctx(dispatch=_D()),
        )

        assert result.status == "ok"
        assert result.data["verdict"] == "can_execute"
        assert called_with["actor_id"] == "test-user"
        assert called_with["space_id"] == "family:default"
        assert called_with["frame"]["intents"][0]["action"] == "schedule dentist"

    @pytest.mark.asyncio
    async def test_optional_overrides_forwarded(self):
        called_with = {}

        class _D:
            async def resolve_situation(self, payload):
                called_with.update(payload)
                return {"verdict": "ok"}

        await execute_resolve_situation(
            {
                "frame": {"intents": []},
                "disclosure_phase": "schema_binding",
                "freshness_policy": "require_fresh",
                "prompt_budget_tokens": 4000,
                "idempotency_keys": ["k1", "k2"],
            },
            _mock_ctx(dispatch=_D()),
        )

        assert called_with["disclosure_phase"] == "schema_binding"
        assert called_with["prompt_budget_tokens"] == 4000
        assert called_with["idempotency_keys"] == ["k1", "k2"]


# ── Adapter tests ────────────────────────────────────────────────────────


class TestResolveSituationAdapter:
    @pytest.mark.asyncio
    async def test_adapter_delegates_to_wired_fabric(self):
        class _F:
            async def _handle_resolve_situation(self, payload):
                return {"verdict": "can_execute", "resolution_id": "r-002"}

        result = await FabricDispatchAdapter(fabric_port=_F()).resolve_situation({})
        assert result["verdict"] == "can_execute"

    @pytest.mark.asyncio
    async def test_adapter_returns_error_when_not_wired(self):
        result = await FabricDispatchAdapter(fabric_port=object()).resolve_situation({})
        assert result["verdict"] == "cannot_execute"
        assert result["sub_reason"] == "resolve_situation_not_wired"


# ── Full chain test ──────────────────────────────────────────────────────


class TestFullResolveSituationChain:
    @pytest.mark.asyncio
    async def test_handler_through_adapter_to_mock_fabric(self):
        called_with = {}

        class _F:
            async def _handle_resolve_situation(self, payload):
                called_with.update(payload)
                return {
                    "verdict": "can_execute",
                    "resolution_id": "r-full",
                    "allowed_capability_names": ["tool.execute.calendar.create_event"],
                }

        adapter = FabricDispatchAdapter(fabric_port=_F())
        result = await execute_resolve_situation(
            {"frame": {"intents": [{"action": "schedule dentist", "domain": "calendar"}]}},
            _mock_ctx(dispatch=adapter),
        )

        assert result.status == "ok"
        assert result.data["verdict"] == "can_execute"
        assert "tool.execute.calendar.create_event" in result.data["allowed_capability_names"]
        assert called_with["actor_id"] == "test-user"


# ── Helpers ──────────────────────────────────────────────────────────────


def _mock_ctx(dispatch: object = "not_set", **kwargs) -> ToolContext:
    sm = type("M", (), {"principal_id": "test-user", "session_id": "test-session"})()
    ctx_kwargs: dict = {"session_manager": sm, "actor": "back", "session_id": "test-session"}
    if dispatch != "not_set":
        ctx_kwargs["dispatch"] = dispatch
    ctx_kwargs.update(kwargs)
    return ToolContext(**ctx_kwargs)
