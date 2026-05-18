"""Bootstrap + manifest fan-out test for the Calendar adapter."""

from __future__ import annotations

from pathlib import Path

import pytest

from k1.fabric.adapters.local_event import LocalEventAdapter
from k1.fabric.adapters.test_bridge import TestBridgeAdapter
from k1.fabric.adapters.test_delta_bus import TestDeltaBusAdapter
from k1.fabric.adapters.test_model_gateway import TestModelGatewayAdapter
from k1.fabric.adapters.test_prompt_system import TestPromptSystemAdapter
from k1.fabric.adapters.test_state_reader import TestSessionStateReaderAdapter
from k1.fabric.factory import FabricFactory
from k1.tools.family.bootstrap import bootstrap_family_tools, register_provider_with_fabric
from k1.tools.family.calendar.definition import CALENDAR_DEFINITION
from k1.tools.family.calendar.service import CalendarToolService
from k1.tools.family.manifest import llm_tool_specs, ui_manifest
from tests.k1.tools.family._stubs import RecordingSsePublisher


def test_bootstrap_registers_calendar_service(tmp_path: Path) -> None:
    """Smoke-test the offline bootstrap path (no Fabric)."""

    pub = RecordingSsePublisher()
    bundle = bootstrap_family_tools(
        fabric=None,
        sse_publisher=pub,
        db_path=str(tmp_path / "boot.db"),
        service_classes=[CalendarToolService],
    )
    try:
        assert "calendar" in bundle.tool_registry.services
        svc = bundle.tool_registry.services["calendar"]
        assert isinstance(svc, CalendarToolService)

        # NativeToolProvider enumerates one capability per action.
        caps = bundle.native_provider.capabilities()
        assert any("calendar" in c and "create_event" in c for c in caps)
        assert any("calendar" in c and "list_events" in c for c in caps)
    finally:
        bundle.close()


def test_calendar_definition_renders_in_manifest() -> None:
    specs = llm_tool_specs(CALENDAR_DEFINITION)
    spec_names = {s["name"] for s in specs}
    assert "calendar.create_event" in spec_names
    assert "calendar.list_events" in spec_names

    manifest = ui_manifest(CALENDAR_DEFINITION, role="parent")
    assert manifest["adapter_id"] == "calendar"
    action_names = {a["name"] for a in manifest["actions"]}
    assert "set_visibility" in action_names


def test_calendar_ui_manifest_hides_parent_only_actions_from_child() -> None:
    manifest = ui_manifest(CALENDAR_DEFINITION, role="child")
    action_names = {a["name"] for a in manifest["actions"]}
    assert "set_visibility" not in action_names
    assert "connect_feed" not in action_names
    assert "list_events" in action_names


@pytest.mark.asyncio
async def test_session_fabric_preserves_calendar_prompt_profile_metadata(
    tmp_path: Path,
) -> None:
    shared_fabric = FabricFactory.create_standalone()
    bundle = bootstrap_family_tools(
        fabric=shared_fabric,
        db_path=str(tmp_path / "family.db"),
        service_classes=[CalendarToolService],
    )
    session_fabric = None
    try:
        capability_name = "tool.execute.calendar.create_event"
        shared_contract = shared_fabric.lookup(capability_name)
        assert shared_contract is not None
        assert shared_contract.activity_profile == "calendar.v1"
        assert shared_contract.prompt_template == "calendar_activity_v1"

        session_fabric = FabricFactory.create_with_ports(
            state_reader=TestSessionStateReaderAdapter(),
            event_port=LocalEventAdapter(),
            bridge=TestBridgeAdapter(),
            model_gateway=TestModelGatewayAdapter(),
            prompt_system=TestPromptSystemAdapter(),
            delta_bus=TestDeltaBusAdapter(),
            capability_registry=shared_fabric.registry,
        )
        register_provider_with_fabric(session_fabric, bundle.native_provider)

        discovery = await session_fabric.discover_capabilities(
            domain=["calendar"],
            intent="create calendar event",
            safety_band="AMBER",
            top_k=10,
        )
        discovered_contract = next(
            (
                scored.contract
                for scored in discovery.capabilities
                if getattr(scored.contract, "name", "") == capability_name
            ),
            None,
        )

        assert discovered_contract is not None
        assert discovered_contract.activity_profile == shared_contract.activity_profile
        assert discovered_contract.prompt_template == shared_contract.prompt_template
    finally:
        if session_fabric is not None:
            await session_fabric.shutdown()
        await shared_fabric.shutdown()
        bundle.close()
        await shared_fabric.shutdown()
        bundle.close()
