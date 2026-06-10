"""GAP-P1-021 — Tests for Fabric Phase 1 wiring + resolve_situation meta-tool (Issue 7.1)."""

from __future__ import annotations

import pytest

from k1.fabric.factory import FabricFactory
from k1.fabric.resolver.situated_resolver import ResolveSituationService

# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────

_PHASE1_FIELDS = (
    "global_projection_store",
    "local_projection_store",
    "idempotency_store",
    "situated_resolver",
    "policy_selector",
    "verification_runner",
    "constitution_loader",
    "prompt_pack_builder",
)


def _wired_resolver():
    """Build a real ResolveSituationService over an admitted calendar connector."""
    from k1.fabric.connectors.builder import build_connector_definition
    from k1.fabric.connectors.domain_catalog import DOMAIN_SERVICES
    from k1.fabric.manifest_admission import ManifestAdmissionService
    from k1.fabric.stores.global_projection_store import GlobalProjectionStore
    from k1.fabric.stores.local_projection_store import LocalProjectionStore

    store = GlobalProjectionStore(":memory:")
    store.open()
    ManifestAdmissionService(store).admit(
        build_connector_definition("family", DOMAIN_SERVICES["family"][0])
    )
    local = LocalProjectionStore(":memory:")
    local.open()
    return ResolveSituationService(store, local)


def _list_payload() -> dict:
    return {
        "request_id": "req-1",
        "actor_id": "actor-a",
        "space_id": "space-1",
        "session_id": "sess-1",
        "tier": "MEDIUM",
        "safety_band": "GREEN",
        "frame": {
            "intents": [
                {
                    "intent_id": "i1",
                    "action": "list calendar events",
                    "domain": "family",
                    "operation_hint": "list",
                    "resource_kind_hint": "calendar_event",
                }
            ],
            "resource_refs": [
                {
                    "raw": "calendar",
                    "resource_kind_hint": "calendar_event",
                    "needs_resolution": False,
                }
            ],
        },
    }


# ══════════════════════════════════════════════════════════════════════
# TestFabricFieldsExist
# ══════════════════════════════════════════════════════════════════════


class TestFabricFieldsExist:
    def test_all_eight_fields_present(self):
        from k1.fabric.fabric import Fabric

        fields = Fabric.__dataclass_fields__
        for name in _PHASE1_FIELDS:
            assert name in fields, f"missing Phase 1 field: {name}"

    def test_all_fields_default_none(self):
        from k1.fabric.fabric import Fabric

        fields = Fabric.__dataclass_fields__
        for name in _PHASE1_FIELDS:
            assert fields[name].default is None, f"{name} should default to None"


# ══════════════════════════════════════════════════════════════════════
# TestMetaToolRegistered
# ══════════════════════════════════════════════════════════════════════


class TestMetaToolRegistered:
    def test_resolve_situation_method_exists(self):
        from k1.fabric.fabric import Fabric

        assert hasattr(Fabric, "resolve_situation")
        assert callable(Fabric.resolve_situation)

    def test_handler_method_exists(self):
        from k1.fabric.fabric import Fabric

        assert hasattr(Fabric, "_handle_resolve_situation")


# ══════════════════════════════════════════════════════════════════════
# TestMetaToolHandlerReturnsErrorWhenNotWired
# ══════════════════════════════════════════════════════════════════════


class TestMetaToolHandlerReturnsErrorWhenNotWired:
    async def test_handler_error_envelope(self):
        fabric = FabricFactory.create_standalone()
        assert fabric.situated_resolver is None
        result = await fabric._handle_resolve_situation(_list_payload())
        assert result["verdict"] == "cannot_execute"
        assert result["sub_reason"] == "resolver_not_wired"

    def test_typed_resolve_raises_when_not_wired(self):
        from k1.fabric.fabric import FabricError
        from k1.fabric.resolver.request_frame import RequestFrame
        from k1.fabric.resolver.situated_resolver import ResolveSituationRequest

        fabric = FabricFactory.create_standalone()
        request = ResolveSituationRequest(
            request_id="r",
            frame=RequestFrame(
                request_id="r",
                task_id="t",
                trace_id="tr",
                actor_id="a",
                space_id="s",
                intents=[],
            ),
            actor_id="a",
            space_id="s",
            session_id="sess",
            tier="MEDIUM",
            safety_band="GREEN",
        )
        with pytest.raises(FabricError):
            fabric.resolve_situation(request)


# ══════════════════════════════════════════════════════════════════════
# TestMetaToolHandlerDelegates
# ══════════════════════════════════════════════════════════════════════


class TestMetaToolHandlerDelegates:
    async def test_handler_delegates_to_resolver(self):
        fabric = FabricFactory.create_standalone()
        fabric.situated_resolver = _wired_resolver()
        result = await fabric._handle_resolve_situation(_list_payload())
        assert result["verdict"] == "can_execute"
        assert "resolution_id" in result
        assert "binding_bundle" in result

    def test_typed_resolve_delegates(self):
        from k1.fabric.resolver.request_frame_builder import build_frame_from_dict
        from k1.fabric.resolver.situated_resolver import ResolveSituationRequest

        fabric = FabricFactory.create_standalone()
        fabric.situated_resolver = _wired_resolver()
        frame = build_frame_from_dict(
            _list_payload()["frame"], actor_id="actor-a", space_id="space-1"
        )
        request = ResolveSituationRequest(
            request_id="req-1",
            frame=frame,
            actor_id="actor-a",
            space_id="space-1",
            session_id="sess-1",
            tier="MEDIUM",
            safety_band="GREEN",
        )
        envelope = fabric.resolve_situation(request)
        assert envelope.verdict == "can_execute"

    async def test_handler_exception_returns_error_envelope(self):
        fabric = FabricFactory.create_standalone()
        fabric.situated_resolver = _wired_resolver()
        # Missing required 'actor_id' → handler catches KeyError, returns error.
        bad_payload = {"request_id": "r", "frame": {"intents": []}}
        result = await fabric._handle_resolve_situation(bad_payload)
        assert result["verdict"] == "cannot_execute"
        assert result["sub_reason"] == "handler_exception"


# ══════════════════════════════════════════════════════════════════════
# TestBackwardCompatible
# ══════════════════════════════════════════════════════════════════════


class TestBackwardCompatible:
    def test_standalone_leaves_phase1_none(self):
        fabric = FabricFactory.create_standalone()
        for name in _PHASE1_FIELDS:
            assert getattr(fabric, name) is None, f"{name} should be None without stores"

    def test_for_testing_leaves_phase1_none(self):
        fabric = FabricFactory.create_for_testing()
        for name in _PHASE1_FIELDS:
            assert getattr(fabric, name) is None
