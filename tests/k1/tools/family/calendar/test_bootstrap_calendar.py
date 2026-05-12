"""Bootstrap + manifest fan-out test for the Calendar adapter."""

from __future__ import annotations

from pathlib import Path

from k1.tools.family.bootstrap import bootstrap_family_tools
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
