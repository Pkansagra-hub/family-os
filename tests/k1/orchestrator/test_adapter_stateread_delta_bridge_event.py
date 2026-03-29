"""
Tests for MockStateReadAdapter (6.1.11), TestDeltaAdapter (6.1.12),
MockBridgeAdapter (6.1.13), and TestEventAdapter (6.1.14).
"""

from __future__ import annotations

import pytest

from k1.fabric.ports.state_reader import SessionSnapshot
from k1.fabric.types import SafetyBand
from k1.orchestrator.adapters.mock_bridge_adapter import MockBridgeAdapter
from k1.orchestrator.adapters.mock_state_read_adapter import MockStateReadAdapter
from k1.orchestrator.adapters.test_delta_adapter import TestDeltaAdapter
from k1.orchestrator.adapters.test_event_adapter import TestEventAdapter
from k1.orchestrator.types import HILRequest

# ===================================================================
# MockStateReadAdapter (6.1.11)
# ===================================================================


class TestMockStateReadAdapterReadSection:
    """6.1.11 -- read_section behavior."""

    @pytest.mark.asyncio
    async def test_returns_none_when_empty(self):
        adapter = MockStateReadAdapter()
        result = await adapter.read_section("sess-1", "control")
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_stored_section(self):
        adapter = MockStateReadAdapter()
        adapter.set_section("sess-1", "control", {"safety_band": "GREEN"})
        result = await adapter.read_section("sess-1", "control")
        assert result == {"safety_band": "GREEN"}

    @pytest.mark.asyncio
    async def test_returns_none_for_wrong_session(self):
        adapter = MockStateReadAdapter()
        adapter.set_section("sess-1", "control", {"x": 1})
        result = await adapter.read_section("sess-2", "control")
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_for_wrong_section(self):
        adapter = MockStateReadAdapter()
        adapter.set_section("sess-1", "control", {"x": 1})
        result = await adapter.read_section("sess-1", "beliefs")
        assert result is None

    @pytest.mark.asyncio
    async def test_read_logged(self):
        adapter = MockStateReadAdapter()
        await adapter.read_section("sess-1", "control")
        assert len(adapter.read_log) == 1
        assert adapter.read_log[0] == ("sess-1", "control")


class TestMockStateReadAdapterReadSections:
    """6.1.11 -- read_sections behavior."""

    @pytest.mark.asyncio
    async def test_returns_multiple_sections(self):
        adapter = MockStateReadAdapter()
        adapter.set_section("s1", "control", {"a": 1})
        adapter.set_section("s1", "beliefs", {"b": 2})
        result = await adapter.read_sections("s1", ["control", "beliefs"])
        assert result == {"control": {"a": 1}, "beliefs": {"b": 2}}

    @pytest.mark.asyncio
    async def test_omits_missing_sections(self):
        adapter = MockStateReadAdapter()
        adapter.set_section("s1", "control", {"a": 1})
        result = await adapter.read_sections("s1", ["control", "beliefs"])
        assert result == {"control": {"a": 1}}

    @pytest.mark.asyncio
    async def test_logs_each_section_read(self):
        adapter = MockStateReadAdapter()
        await adapter.read_sections("s1", ["control", "beliefs"])
        assert len(adapter.read_log) == 2


class TestMockStateReadAdapterGetSnapshot:
    """6.1.11 -- get_snapshot behavior."""

    @pytest.mark.asyncio
    async def test_snapshot_contains_all_sections(self):
        adapter = MockStateReadAdapter()
        adapter.set_section("s1", "control", {"a": 1})
        adapter.set_section("s1", "persona", {"b": 2})
        snap = await adapter.get_snapshot("s1")
        assert isinstance(snap, SessionSnapshot)
        assert snap.session_id == "s1"
        assert "control" in snap.sections
        assert "persona" in snap.sections

    @pytest.mark.asyncio
    async def test_snapshot_empty_session(self):
        adapter = MockStateReadAdapter()
        snap = await adapter.get_snapshot("s1")
        assert snap.sections == {}

    @pytest.mark.asyncio
    async def test_snapshot_logged(self):
        adapter = MockStateReadAdapter()
        await adapter.get_snapshot("s1")
        assert ("s1", "__snapshot__") in adapter.read_log


class TestMockStateReadAdapterHelpers:
    """6.1.11 -- set helpers and assertions."""

    @pytest.mark.asyncio
    async def test_set_safety_band(self):
        adapter = MockStateReadAdapter()
        adapter.set_safety_band("s1", SafetyBand.AMBER)
        result = await adapter.read_section("s1", "control")
        assert result == {"safety_band": SafetyBand.AMBER}

    @pytest.mark.asyncio
    async def test_set_user_preferences(self):
        adapter = MockStateReadAdapter()
        adapter.set_user_preferences("s1", {"lang": "en", "theme": "dark"})
        result = await adapter.read_section("s1", "persona")
        assert result == {"lang": "en", "theme": "dark"}

    @pytest.mark.asyncio
    async def test_assert_read_passes(self):
        adapter = MockStateReadAdapter()
        await adapter.read_section("s1", "control")
        adapter.assert_read("control", times=1)

    @pytest.mark.asyncio
    async def test_assert_read_fails(self):
        adapter = MockStateReadAdapter()
        with pytest.raises(AssertionError):
            adapter.assert_read("control", times=1)

    @pytest.mark.asyncio
    async def test_clear(self):
        adapter = MockStateReadAdapter()
        adapter.set_section("s1", "control", {"x": 1})
        await adapter.read_section("s1", "control")
        adapter.clear()
        assert adapter.sections == {}
        assert adapter.read_log == []


# ===================================================================
# TestDeltaAdapter (6.1.12)
# ===================================================================


class TestDeltaAdapterEmit:
    """6.1.12 -- emit behavior."""

    @pytest.mark.asyncio
    async def test_emit_captures_event(self):
        adapter = TestDeltaAdapter()
        await adapter.emit("k1.dag.completed", {"data": 1}, "t-1")
        assert len(adapter.emitted) == 1
        assert adapter.emitted[0] == ("k1.dag.completed", {"data": 1}, "t-1")

    @pytest.mark.asyncio
    async def test_emit_multiple(self):
        adapter = TestDeltaAdapter()
        await adapter.emit("topic.a", {}, "t-1")
        await adapter.emit("topic.b", {}, "t-2")
        assert len(adapter.emitted) == 2


class TestDeltaAdapterEmitProgress:
    """6.1.12 -- emit_progress behavior."""

    @pytest.mark.asyncio
    async def test_progress_captured(self):
        adapter = TestDeltaAdapter()
        await adapter.emit_progress("step-1", "done", "t-1")
        assert len(adapter.progress_log) == 1
        assert adapter.progress_log[0] == ("step-1", "done", "t-1")


class TestDeltaAdapterEmitHIL:
    """6.1.12 -- emit_hil_request behavior."""

    @pytest.mark.asyncio
    async def test_hil_captured(self):
        adapter = TestDeltaAdapter()
        hil = HILRequest(request_id="h-1", question="Choose?", options=["A", "B"])
        await adapter.emit_hil_request(hil, "t-1")
        assert len(adapter.hil_requests) == 1
        assert adapter.hil_requests[0] == (hil, "t-1")


class TestDeltaAdapterAssertions:
    """6.1.12 -- assertion helpers."""

    @pytest.mark.asyncio
    async def test_assert_emitted_passes(self):
        adapter = TestDeltaAdapter()
        await adapter.emit("topic.a", {}, "t")
        adapter.assert_emitted("topic.a", count=1)

    @pytest.mark.asyncio
    async def test_assert_emitted_fails(self):
        adapter = TestDeltaAdapter()
        with pytest.raises(AssertionError):
            adapter.assert_emitted("topic.a", count=1)

    @pytest.mark.asyncio
    async def test_get_emitted(self):
        adapter = TestDeltaAdapter()
        await adapter.emit("topic.a", {"x": 1}, "t")
        await adapter.emit("topic.b", {"y": 2}, "t")
        await adapter.emit("topic.a", {"z": 3}, "t")
        result = adapter.get_emitted("topic.a")
        assert result == [{"x": 1}, {"z": 3}]

    @pytest.mark.asyncio
    async def test_assert_progress_passes(self):
        adapter = TestDeltaAdapter()
        await adapter.emit_progress("s1", "ok", "t")
        adapter.assert_progress("s1")

    @pytest.mark.asyncio
    async def test_assert_progress_fails(self):
        adapter = TestDeltaAdapter()
        with pytest.raises(AssertionError):
            adapter.assert_progress("s1")

    @pytest.mark.asyncio
    async def test_assert_hil_requested_passes(self):
        adapter = TestDeltaAdapter()
        hil = HILRequest(request_id="h-1", question="Q?")
        await adapter.emit_hil_request(hil, "t")
        adapter.assert_hil_requested(count=1)

    @pytest.mark.asyncio
    async def test_assert_hil_requested_fails(self):
        adapter = TestDeltaAdapter()
        with pytest.raises(AssertionError):
            adapter.assert_hil_requested(count=1)


class TestDeltaAdapterReset:
    """6.1.12 -- reset clears all logs."""

    @pytest.mark.asyncio
    async def test_reset(self):
        adapter = TestDeltaAdapter()
        await adapter.emit("t", {}, "x")
        await adapter.emit_progress("s", "ok", "x")
        hil = HILRequest(request_id="h", question="Q?")
        await adapter.emit_hil_request(hil, "x")
        adapter.reset()
        assert adapter.emitted == []
        assert adapter.progress_log == []
        assert adapter.hil_requests == []


# ===================================================================
# MockBridgeAdapter (6.1.13)
# ===================================================================


class TestMockBridgeAdapterAudit:
    """6.1.13 -- submit_audit behavior."""

    @pytest.mark.asyncio
    async def test_audit_captured(self):
        adapter = MockBridgeAdapter()
        await adapter.submit_audit({"plan": "p1"}, "t-1")
        assert len(adapter.audit_log) == 1
        assert adapter.audit_log[0] == ({"plan": "p1"}, "t-1")

    @pytest.mark.asyncio
    async def test_assert_audit_written_passes(self):
        adapter = MockBridgeAdapter()
        await adapter.submit_audit({}, "t")
        adapter.assert_audit_written(count=1)

    @pytest.mark.asyncio
    async def test_assert_audit_written_fails(self):
        adapter = MockBridgeAdapter()
        with pytest.raises(AssertionError):
            adapter.assert_audit_written(count=1)


class TestMockBridgeAdapterWAL:
    """6.1.13 -- write_wal / read_wal behavior."""

    @pytest.mark.asyncio
    async def test_write_and_read_wal(self):
        adapter = MockBridgeAdapter()
        await adapter.write_wal("dag-1", "PLAN_START", {"plan": "p1"}, "t-1")
        entries = await adapter.read_wal("dag-1")
        assert entries is not None
        assert len(entries) == 1
        assert entries[0]["entry_type"] == "PLAN_START"

    @pytest.mark.asyncio
    async def test_read_wal_returns_none_when_empty(self):
        adapter = MockBridgeAdapter()
        entries = await adapter.read_wal("nonexistent")
        assert entries is None

    @pytest.mark.asyncio
    async def test_multiple_wal_entries(self):
        adapter = MockBridgeAdapter()
        await adapter.write_wal("dag-1", "PLAN_START", {}, "t")
        await adapter.write_wal("dag-1", "STEP_COMPLETE", {"step": "s1"}, "t")
        await adapter.write_wal("dag-1", "DAG_COMPLETE", {}, "t")
        entries = await adapter.read_wal("dag-1")
        assert len(entries) == 3
        types = [e["entry_type"] for e in entries]
        assert types == ["PLAN_START", "STEP_COMPLETE", "DAG_COMPLETE"]

    @pytest.mark.asyncio
    async def test_assert_wal_written_passes(self):
        adapter = MockBridgeAdapter()
        await adapter.write_wal("dag-1", "PLAN_START", {}, "t")
        adapter.assert_wal_written("dag-1", "PLAN_START")

    @pytest.mark.asyncio
    async def test_assert_wal_written_fails(self):
        adapter = MockBridgeAdapter()
        with pytest.raises(AssertionError):
            adapter.assert_wal_written("dag-1", "PLAN_START")

    @pytest.mark.asyncio
    async def test_get_wal_empty(self):
        adapter = MockBridgeAdapter()
        assert adapter.get_wal("nonexistent") == []


class TestMockBridgeAdapterInjectWAL:
    """6.1.13 -- inject_wal for crash recovery tests."""

    @pytest.mark.asyncio
    async def test_inject_wal_readable(self):
        adapter = MockBridgeAdapter()
        adapter.inject_wal(
            "dag-1",
            [
                {"entry_type": "PLAN_START", "payload": {}, "trace_id": "t"},
                {"entry_type": "STEP_COMPLETE", "payload": {"step": "s1"}, "trace_id": "t"},
            ],
        )
        entries = await adapter.read_wal("dag-1")
        assert entries is not None
        assert len(entries) == 2

    @pytest.mark.asyncio
    async def test_constructor_wal_store(self):
        store = {"dag-1": [{"entry_type": "PLAN_START", "payload": {}, "trace_id": "t"}]}
        adapter = MockBridgeAdapter(wal_store=store)
        entries = await adapter.read_wal("dag-1")
        assert entries is not None
        assert len(entries) == 1


class TestMockBridgeAdapterListWalIds:
    """6.1.13 -- list_wal_ids behavior."""

    @pytest.mark.asyncio
    async def test_list_wal_ids_empty(self):
        adapter = MockBridgeAdapter()
        ids = await adapter.list_wal_ids()
        assert ids == []

    @pytest.mark.asyncio
    async def test_list_wal_ids_after_writes(self):
        adapter = MockBridgeAdapter()
        await adapter.write_wal("dag-1", "PLAN_START", {}, "t")
        await adapter.write_wal("dag-2", "PLAN_START", {}, "t")
        ids = await adapter.list_wal_ids()
        assert sorted(ids) == ["dag-1", "dag-2"]


class TestMockBridgeAdapterDeferredResult:
    """6.1.13 -- submit_deferred_result behavior."""

    @pytest.mark.asyncio
    async def test_deferred_result_captured(self):
        adapter = MockBridgeAdapter()
        await adapter.submit_deferred_result({"out": "x"}, "wf-1", "t-1")
        assert len(adapter.deferred_results) == 1
        assert adapter.deferred_results[0]["workflow_id"] == "wf-1"


class TestMockBridgeAdapterReset:
    """6.1.13 -- reset clears all state."""

    @pytest.mark.asyncio
    async def test_reset(self):
        adapter = MockBridgeAdapter()
        await adapter.submit_audit({}, "t")
        await adapter.write_wal("d", "PLAN_START", {}, "t")
        await adapter.submit_deferred_result({}, "w", "t")
        adapter.reset()
        assert adapter.audit_log == []
        assert adapter.wal_entries == {}
        assert adapter.deferred_results == []


# ===================================================================
# TestEventAdapter (6.1.14)
# ===================================================================


class TestEventAdapterSubscribe:
    """6.1.14 -- subscribe behavior."""

    def test_subscribe_returns_handle(self):
        adapter = TestEventAdapter()
        handle = adapter.subscribe("topic.a", lambda t, p: None)
        assert handle.topic == "topic.a"
        assert handle.subscription_id

    def test_subscribe_multiple_handlers(self):
        adapter = TestEventAdapter()
        adapter.subscribe("topic.a", lambda t, p: None)
        adapter.subscribe("topic.a", lambda t, p: None)
        assert len(adapter.subscriptions["topic.a"]) == 2


class TestEventAdapterUnsubscribe:
    """6.1.14 -- unsubscribe behavior."""

    def test_unsubscribe_removes_handler(self):
        adapter = TestEventAdapter()
        handle = adapter.subscribe("topic.a", lambda t, p: None)
        result = adapter.unsubscribe(handle)
        assert result is True
        assert "topic.a" not in adapter.subscriptions

    def test_unsubscribe_unknown_returns_false(self):
        from k1.fabric.ports.event_port import SubscriptionHandle

        adapter = TestEventAdapter()
        fake = SubscriptionHandle(subscription_id="nope", topic="x")
        assert adapter.unsubscribe(fake) is False


class TestEventAdapterEmit:
    """6.1.14 -- emit behavior and dispatch."""

    def test_emit_logs_event(self):
        adapter = TestEventAdapter()
        adapter.emit("topic.a", {"x": 1})
        assert len(adapter.emitted) == 1
        assert adapter.emitted[0] == ("topic.a", {"x": 1})

    def test_emit_dispatches_to_handler(self):
        received = []
        adapter = TestEventAdapter()
        adapter.subscribe("topic.a", lambda t, p: received.append((t, p)))
        adapter.emit("topic.a", {"x": 1})
        assert len(received) == 1
        assert received[0] == ("topic.a", {"x": 1})

    def test_emit_no_handler_no_crash(self):
        adapter = TestEventAdapter()
        adapter.emit("topic.unsubscribed", {})
        assert len(adapter.emitted) == 1


class TestEventAdapterWildcard:
    """6.1.14 -- wildcard matching."""

    def test_wildcard_matches(self):
        received = []
        adapter = TestEventAdapter()
        adapter.subscribe("k1.capability.*", lambda t, p: received.append(t))
        adapter.emit("k1.capability.completed.v1", {})
        assert len(received) == 1
        assert received[0] == "k1.capability.completed.v1"

    def test_wildcard_does_not_match_different_prefix(self):
        received = []
        adapter = TestEventAdapter()
        adapter.subscribe("k1.capability.*", lambda t, p: received.append(t))
        adapter.emit("k1.planner.plan.ready.v1", {})
        assert len(received) == 0

    def test_exact_and_wildcard_both_fire(self):
        received = []
        adapter = TestEventAdapter()
        adapter.subscribe("k1.capability.*", lambda t, p: received.append("wild"))
        adapter.subscribe("k1.capability.completed.v1", lambda t, p: received.append("exact"))
        adapter.emit("k1.capability.completed.v1", {})
        assert "wild" in received
        assert "exact" in received


class TestEventAdapterFire:
    """6.1.14 -- fire() is alias for emit()."""

    def test_fire_dispatches(self):
        received = []
        adapter = TestEventAdapter()
        adapter.subscribe("topic.a", lambda t, p: received.append(p))
        adapter.fire("topic.a", {"val": 42})
        assert len(received) == 1
        assert received[0] == {"val": 42}

    def test_fire_logs_event(self):
        adapter = TestEventAdapter()
        adapter.fire("topic.a", {})
        assert len(adapter.emitted) == 1


class TestEventAdapterAssertions:
    """6.1.14 -- assertion helpers."""

    def test_assert_subscribed_passes(self):
        adapter = TestEventAdapter()
        adapter.subscribe("topic.a", lambda t, p: None)
        adapter.assert_subscribed("topic.a")

    def test_assert_subscribed_fails(self):
        adapter = TestEventAdapter()
        with pytest.raises(AssertionError):
            adapter.assert_subscribed("topic.a")

    def test_assert_emitted_passes(self):
        adapter = TestEventAdapter()
        adapter.emit("topic.a", {})
        adapter.assert_emitted("topic.a", count=1)

    def test_assert_emitted_fails(self):
        adapter = TestEventAdapter()
        with pytest.raises(AssertionError):
            adapter.assert_emitted("topic.a", count=1)

    def test_get_emitted(self):
        adapter = TestEventAdapter()
        adapter.emit("topic.a", {"x": 1})
        adapter.emit("topic.b", {"y": 2})
        adapter.emit("topic.a", {"z": 3})
        result = adapter.get_emitted("topic.a")
        assert result == [{"x": 1}, {"z": 3}]


class TestEventAdapterReset:
    """6.1.14 -- reset clears emitted but preserves subscriptions."""

    def test_reset_clears_emitted(self):
        adapter = TestEventAdapter()
        adapter.subscribe("topic.a", lambda t, p: None)
        adapter.emit("topic.a", {})
        adapter.reset()
        assert adapter.emitted == []
        assert "topic.a" in adapter.subscriptions
