"""
Tests for Epic 5.2 -- Adapters (5.2.1, 5.2.2, 5.2.3).

Covers:
  5.2.1 SessionStateReaderAdapter (production)
  5.2.2 TestSessionStateReaderAdapter (test)
  5.2.3 LocalEventAdapter (event dispatch + capture)

Test structure:
  TestSessionStateReaderAdapter -- Protocol conformance, delegation, to_dict
  TestSessionStateReaderAdapterEdge -- Session mismatch, missing sections
  TestTestSessionStateReaderAdapterBasic -- Load, read, snapshot
  TestTestSessionStateReaderAdapterBatch -- load_many, read_sections
  TestTestSessionStateReaderAdapterHelpers -- remove, clear, section_count
  TestTestSessionStateReaderAdapterProtocol -- Protocol conformance
  TestTestSessionStateReaderAdapterThreadSafety -- Concurrent reads
  TestLocalEventAdapterProtocol -- Protocol conformance, runtime_checkable
  TestLocalEventAdapterEmit -- Fire-and-forget, handler dispatch
  TestLocalEventAdapterSubscription -- Subscribe, unsubscribe, handles
  TestLocalEventAdapterCapture -- Capture mode, drain, assert_emitted
  TestLocalEventAdapterConcurrency -- Thread-safe emit + subscribe
  TestLocalEventAdapterFailingHandler -- Exception isolation
  TestAdaptersExports -- __all__ count and presence
"""

from __future__ import annotations

import threading
import time
from typing import Any, Dict, List, Optional, Tuple

import pytest

from k1.fabric.adapters import LocalEventAdapter as LocalEventAdapterPkg
from k1.fabric.adapters import SessionStateReaderAdapter as SessionStateReaderAdapterPkg
from k1.fabric.adapters import TestSessionStateReaderAdapter as TestStateReaderPkg
from k1.fabric.adapters.local_event import LocalEventAdapter
from k1.fabric.adapters.sessionstate_reader import SessionStateReaderAdapter
from k1.fabric.adapters.test_state_reader import (
    TestSessionStateReaderAdapter as TestStateReaderAdapter,
)
from k1.fabric.ports import IEventPort, ISessionStateReader, SessionSnapshot, SubscriptionHandle

# ---------------------------------------------------------------------------
# Fake SessionStateManager for production adapter tests
# ---------------------------------------------------------------------------


class FakeSection:
    """Mimics a real SessionState section with to_dict()."""

    def __init__(self, data: Dict[str, Any]) -> None:
        self._data = data

    def to_dict(self) -> Dict[str, Any]:
        return dict(self._data)


class FakeManager:
    """Mimics a SessionStateManager with get_section + get_all_section_sizes."""

    def __init__(self, session_id: str = "test-session") -> None:
        self.session_id = session_id
        self._sections: Dict[str, FakeSection] = {}

    def add_section(self, name: str, data: Dict[str, Any]) -> None:
        self._sections[name] = FakeSection(data)

    def get_section(self, name: str) -> Any:
        if name not in self._sections:
            raise KeyError(f"Section '{name}' not found")
        return self._sections[name]

    def get_all_section_sizes(self) -> Dict[str, int]:
        return {name: 100 for name in self._sections}


class FakeManagerDictSections:
    """Manager that returns raw dicts instead of objects with to_dict()."""

    def __init__(self) -> None:
        self._sections: Dict[str, Dict[str, Any]] = {}

    def add_section(self, name: str, data: Dict[str, Any]) -> None:
        self._sections[name] = data

    def get_section(self, name: str) -> Any:
        if name not in self._sections:
            raise KeyError(f"Section '{name}' not found")
        return self._sections[name]

    def get_all_section_sizes(self) -> Dict[str, int]:
        return {name: 50 for name in self._sections}


# ===========================================================================
# 5.2.1 -- SessionStateReaderAdapter (production)
# ===========================================================================


class TestSessionStateReaderAdapterProd:
    """SessionStateReaderAdapter protocol conformance and delegation."""

    def test_satisfies_protocol(self) -> None:
        mgr = FakeManager()
        adapter = SessionStateReaderAdapter(manager=mgr, session_id="s1")
        assert isinstance(adapter, ISessionStateReader)

    def test_read_section_returns_dict(self) -> None:
        mgr = FakeManager()
        mgr.add_section("affective_now", {"emotion": "calm", "intensity": 0.3})
        adapter = SessionStateReaderAdapter(manager=mgr, session_id="s1")
        result = adapter.read_section("s1", "affective_now")
        assert result == {"emotion": "calm", "intensity": 0.3}

    def test_read_section_none_for_missing(self) -> None:
        mgr = FakeManager()
        adapter = SessionStateReaderAdapter(manager=mgr, session_id="s1")
        result = adapter.read_section("s1", "nonexistent")
        assert result is None

    def test_read_section_none_for_session_mismatch(self) -> None:
        mgr = FakeManager()
        mgr.add_section("affective_now", {"emotion": "calm"})
        adapter = SessionStateReaderAdapter(manager=mgr, session_id="s1")
        result = adapter.read_section("other-session", "affective_now")
        assert result is None

    def test_read_sections_returns_dict(self) -> None:
        mgr = FakeManager()
        mgr.add_section("affective_now", {"emotion": "calm"})
        mgr.add_section("cognitive", {"load": "low"})
        adapter = SessionStateReaderAdapter(manager=mgr, session_id="s1")
        result = adapter.read_sections("s1", ["affective_now", "cognitive", "missing"])
        assert "affective_now" in result
        assert "cognitive" in result
        assert "missing" not in result

    def test_read_sections_empty_for_mismatch(self) -> None:
        mgr = FakeManager()
        mgr.add_section("affective_now", {"emotion": "calm"})
        adapter = SessionStateReaderAdapter(manager=mgr, session_id="s1")
        result = adapter.read_sections("wrong", ["affective_now"])
        assert result == {}

    def test_get_snapshot(self) -> None:
        mgr = FakeManager()
        mgr.add_section("affective_now", {"emotion": "calm"})
        mgr.add_section("cognitive", {"load": "low"})
        adapter = SessionStateReaderAdapter(manager=mgr, session_id="s1")
        snap = adapter.get_snapshot("s1")
        assert isinstance(snap, SessionSnapshot)
        assert snap.session_id == "s1"
        assert snap.has_section("affective_now")
        assert snap.has_section("cognitive")

    def test_get_snapshot_empty_for_mismatch(self) -> None:
        mgr = FakeManager()
        mgr.add_section("affective_now", {"emotion": "calm"})
        adapter = SessionStateReaderAdapter(manager=mgr, session_id="s1")
        snap = adapter.get_snapshot("wrong")
        assert snap.sections == {}

    def test_get_snapshot_timestamp(self) -> None:
        mgr = FakeManager()
        adapter = SessionStateReaderAdapter(manager=mgr, session_id="s1")
        before = int(time.time() * 1000)
        snap = adapter.get_snapshot("s1")
        after = int(time.time() * 1000)
        assert before <= snap.timestamp_ms <= after

    def test_session_id_property(self) -> None:
        mgr = FakeManager()
        adapter = SessionStateReaderAdapter(manager=mgr, session_id="my-session")
        assert adapter.session_id == "my-session"

    def test_repr(self) -> None:
        mgr = FakeManager()
        adapter = SessionStateReaderAdapter(manager=mgr, session_id="s1")
        r = repr(adapter)
        assert "SessionStateReaderAdapter" in r
        assert "s1" in r

    def test_dict_sections_fallback(self) -> None:
        """Manager returning raw dicts instead of section objects."""
        mgr = FakeManagerDictSections()
        mgr.add_section("control", {"turn": 5})
        adapter = SessionStateReaderAdapter(manager=mgr, session_id="s1")
        result = adapter.read_section("s1", "control")
        assert result == {"turn": 5}

    def test_direct_import_identity(self) -> None:
        assert SessionStateReaderAdapter is SessionStateReaderAdapterPkg


class TestSessionStateReaderAdapterEdge:
    """Edge cases for SessionStateReaderAdapter."""

    def test_get_section_data_isolation(self) -> None:
        """Returned dicts should be independent copies."""
        mgr = FakeManager()
        mgr.add_section("beliefs_active", {"belief_a": True})
        adapter = SessionStateReaderAdapter(manager=mgr, session_id="s1")
        d1 = adapter.read_section("s1", "beliefs_active")
        d2 = adapter.read_section("s1", "beliefs_active")
        assert d1 == d2
        # Both from to_dict() which creates new dict each time
        assert d1 is not d2

    def test_snapshot_uses_get_all_section_sizes(self) -> None:
        """Snapshot should discover sections via get_all_section_sizes."""
        mgr = FakeManager()
        mgr.add_section("custom_section", {"val": 42})
        adapter = SessionStateReaderAdapter(manager=mgr, session_id="s1")
        snap = adapter.get_snapshot("s1")
        assert snap.has_section("custom_section")

    def test_manager_exception_returns_none(self) -> None:
        """If manager raises unexpected exception, read returns None."""

        class BrokenManager:
            def get_section(self, name: str) -> Any:
                raise RuntimeError("Something broke")

            def get_all_section_sizes(self) -> Dict[str, int]:
                return {}

        adapter = SessionStateReaderAdapter(manager=BrokenManager(), session_id="s1")
        result = adapter.read_section("s1", "anything")
        assert result is None


# ===========================================================================
# 5.2.2 -- TestSessionStateReaderAdapter (test)
# ===========================================================================


class TestTestStateReaderAdapterBasic:
    """Basic load/read/snapshot operations."""

    def test_satisfies_protocol(self) -> None:
        adapter = TestStateReaderAdapter()
        assert isinstance(adapter, ISessionStateReader)

    def test_load_and_read(self) -> None:
        adapter = TestStateReaderAdapter()
        adapter.load("s1", "affective_now", {"emotion": "calm"})
        result = adapter.read_section("s1", "affective_now")
        assert result == {"emotion": "calm"}

    def test_read_missing_returns_none(self) -> None:
        adapter = TestStateReaderAdapter()
        result = adapter.read_section("s1", "missing")
        assert result is None

    def test_read_wrong_session_returns_none(self) -> None:
        adapter = TestStateReaderAdapter()
        adapter.load("s1", "affective_now", {"emotion": "calm"})
        result = adapter.read_section("s2", "affective_now")
        assert result is None

    def test_get_snapshot(self) -> None:
        adapter = TestStateReaderAdapter()
        adapter.load("s1", "affective_now", {"emotion": "calm"})
        adapter.load("s1", "cognitive", {"load": "low"})
        snap = adapter.get_snapshot("s1")
        assert isinstance(snap, SessionSnapshot)
        assert snap.session_id == "s1"
        assert snap.has_section("affective_now")
        assert snap.has_section("cognitive")
        assert not snap.has_section("missing")

    def test_get_snapshot_empty_session(self) -> None:
        adapter = TestStateReaderAdapter()
        snap = adapter.get_snapshot("empty")
        assert snap.sections == {}
        assert snap.session_id == "empty"

    def test_get_snapshot_timestamp(self) -> None:
        adapter = TestStateReaderAdapter()
        adapter.load("s1", "control", {"turn": 1})
        before = int(time.time() * 1000)
        snap = adapter.get_snapshot("s1")
        after = int(time.time() * 1000)
        assert before <= snap.timestamp_ms <= after

    def test_snapshot_section_names(self) -> None:
        adapter = TestStateReaderAdapter()
        adapter.load("s1", "b", {"x": 1})
        adapter.load("s1", "a", {"y": 2})
        snap = adapter.get_snapshot("s1")
        # Auto-populated and sorted
        assert snap.section_names == ["a", "b"]


class TestTestStateReaderAdapterBatch:
    """Batch load and read operations."""

    def test_load_many(self) -> None:
        adapter = TestStateReaderAdapter()
        adapter.load_many(
            "s1",
            {
                "affective_now": {"emotion": "calm"},
                "cognitive": {"load": "low"},
            },
        )
        assert adapter.read_section("s1", "affective_now") == {"emotion": "calm"}
        assert adapter.read_section("s1", "cognitive") == {"load": "low"}

    def test_read_sections(self) -> None:
        adapter = TestStateReaderAdapter()
        adapter.load_many(
            "s1",
            {
                "affective_now": {"emotion": "calm"},
                "cognitive": {"load": "low"},
                "control": {"turn": 3},
            },
        )
        result = adapter.read_sections("s1", ["affective_now", "control", "missing"])
        assert "affective_now" in result
        assert "control" in result
        assert "missing" not in result
        assert len(result) == 2

    def test_read_sections_empty_names(self) -> None:
        adapter = TestStateReaderAdapter()
        adapter.load("s1", "x", {"a": 1})
        result = adapter.read_sections("s1", [])
        assert result == {}

    def test_read_sections_wrong_session(self) -> None:
        adapter = TestStateReaderAdapter()
        adapter.load("s1", "x", {"a": 1})
        result = adapter.read_sections("s2", ["x"])
        assert result == {}


class TestTestStateReaderAdapterHelpers:
    """Helper methods: remove, clear, section_count."""

    def test_remove_existing(self) -> None:
        adapter = TestStateReaderAdapter()
        adapter.load("s1", "x", {"a": 1})
        assert adapter.remove("s1", "x") is True
        assert adapter.read_section("s1", "x") is None

    def test_remove_nonexistent(self) -> None:
        adapter = TestStateReaderAdapter()
        assert adapter.remove("s1", "x") is False

    def test_clear(self) -> None:
        adapter = TestStateReaderAdapter()
        adapter.load("s1", "x", {"a": 1})
        adapter.load("s2", "y", {"b": 2})
        adapter.clear()
        assert adapter.section_count() == 0

    def test_section_count_all(self) -> None:
        adapter = TestStateReaderAdapter()
        adapter.load("s1", "x", {"a": 1})
        adapter.load("s2", "y", {"b": 2})
        assert adapter.section_count() == 2

    def test_section_count_per_session(self) -> None:
        adapter = TestStateReaderAdapter()
        adapter.load("s1", "x", {"a": 1})
        adapter.load("s1", "y", {"b": 2})
        adapter.load("s2", "z", {"c": 3})
        assert adapter.section_count("s1") == 2
        assert adapter.section_count("s2") == 1
        assert adapter.section_count("s3") == 0

    def test_repr(self) -> None:
        adapter = TestStateReaderAdapter()
        adapter.load("s1", "x", {"a": 1})
        r = repr(adapter)
        assert "TestSessionStateReaderAdapter" in r
        assert "1" in r

    def test_direct_import_identity(self) -> None:
        assert TestStateReaderAdapter is TestStateReaderPkg


class TestTestStateReaderAdapterProtocol:
    """Protocol conformance for TestSessionStateReaderAdapter."""

    def test_runtime_checkable(self) -> None:
        adapter = TestStateReaderAdapter()
        assert isinstance(adapter, ISessionStateReader)

    def test_has_read_section(self) -> None:
        assert hasattr(TestStateReaderAdapter, "read_section")

    def test_has_read_sections(self) -> None:
        assert hasattr(TestStateReaderAdapter, "read_sections")

    def test_has_get_snapshot(self) -> None:
        assert hasattr(TestStateReaderAdapter, "get_snapshot")

    def test_overwrite_section(self) -> None:
        adapter = TestStateReaderAdapter()
        adapter.load("s1", "x", {"v": 1})
        adapter.load("s1", "x", {"v": 2})
        assert adapter.read_section("s1", "x") == {"v": 2}


class TestTestStateReaderAdapterThreadSafety:
    """Concurrent read access."""

    def test_concurrent_reads(self) -> None:
        adapter = TestStateReaderAdapter()
        for i in range(100):
            adapter.load("s1", f"section_{i}", {"idx": i})

        results: List[Optional[Dict[str, Any]]] = [None] * 100
        errors: List[Optional[Exception]] = []

        def reader(idx: int) -> None:
            try:
                results[idx] = adapter.read_section("s1", f"section_{idx}")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=reader, args=(i,)) for i in range(100)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5.0)

        assert not errors
        for i in range(100):
            assert results[i] == {"idx": i}


# ===========================================================================
# 5.2.3 -- LocalEventAdapter
# ===========================================================================


class TestLocalEventAdapterProtocol:
    """LocalEventAdapter protocol conformance."""

    def test_satisfies_protocol(self) -> None:
        adapter = LocalEventAdapter()
        assert isinstance(adapter, IEventPort)

    def test_has_emit(self) -> None:
        assert hasattr(LocalEventAdapter, "emit")

    def test_has_subscribe(self) -> None:
        assert hasattr(LocalEventAdapter, "subscribe")

    def test_has_unsubscribe(self) -> None:
        assert hasattr(LocalEventAdapter, "unsubscribe")

    def test_runtime_checkable(self) -> None:
        adapter = LocalEventAdapter(capture_mode=True)
        assert isinstance(adapter, IEventPort)

    def test_direct_import_identity(self) -> None:
        assert LocalEventAdapter is LocalEventAdapterPkg


class TestLocalEventAdapterEmit:
    """Emit fire-and-forget behavior."""

    def test_emit_no_subscribers(self) -> None:
        """emit() must not raise even without subscribers."""
        adapter = LocalEventAdapter()
        adapter.emit("some.topic", {"data": "value"})
        # No error

    def test_emit_calls_handler(self) -> None:
        received: List[Tuple[str, Dict[str, Any]]] = []
        adapter = LocalEventAdapter()
        adapter.subscribe("topic.a", lambda t, p: received.append((t, p)))
        adapter.emit("topic.a", {"key": "val"})
        assert len(received) == 1
        assert received[0] == ("topic.a", {"key": "val"})

    def test_emit_only_matching_topic(self) -> None:
        received: List[str] = []
        adapter = LocalEventAdapter()
        adapter.subscribe("topic.a", lambda t, p: received.append("a"))
        adapter.subscribe("topic.b", lambda t, p: received.append("b"))
        adapter.emit("topic.a", {})
        assert received == ["a"]

    def test_emit_multiple_handlers(self) -> None:
        count = [0]
        adapter = LocalEventAdapter()
        adapter.subscribe("t", lambda t, p: count.__setitem__(0, count[0] + 1))
        adapter.subscribe("t", lambda t, p: count.__setitem__(0, count[0] + 1))
        adapter.emit("t", {})
        assert count[0] == 2

    def test_emit_returns_none(self) -> None:
        adapter = LocalEventAdapter()
        result = adapter.emit("t", {})
        assert result is None


class TestLocalEventAdapterSubscription:
    """Subscribe/unsubscribe and SubscriptionHandle management."""

    def test_subscribe_returns_handle(self) -> None:
        adapter = LocalEventAdapter()
        handle = adapter.subscribe("topic.x", lambda t, p: None)
        assert isinstance(handle, SubscriptionHandle)
        assert handle.topic == "topic.x"
        assert handle.subscription_id != ""

    def test_unsubscribe_returns_true(self) -> None:
        adapter = LocalEventAdapter()
        handle = adapter.subscribe("t", lambda t, p: None)
        assert adapter.unsubscribe(handle) is True

    def test_unsubscribe_unknown_returns_false(self) -> None:
        adapter = LocalEventAdapter()
        fake_handle = SubscriptionHandle(subscription_id="nope", topic="t")
        assert adapter.unsubscribe(fake_handle) is False

    def test_unsubscribe_stops_handler(self) -> None:
        received: List[str] = []
        adapter = LocalEventAdapter()
        handle = adapter.subscribe("t", lambda t, p: received.append("hit"))
        adapter.emit("t", {})
        assert len(received) == 1
        adapter.unsubscribe(handle)
        adapter.emit("t", {})
        assert len(received) == 1  # No new hit

    def test_double_unsubscribe(self) -> None:
        adapter = LocalEventAdapter()
        handle = adapter.subscribe("t", lambda t, p: None)
        assert adapter.unsubscribe(handle) is True
        assert adapter.unsubscribe(handle) is False

    def test_subscription_count(self) -> None:
        adapter = LocalEventAdapter()
        assert adapter.subscription_count == 0
        h1 = adapter.subscribe("a", lambda t, p: None)
        h2 = adapter.subscribe("b", lambda t, p: None)
        assert adapter.subscription_count == 2
        adapter.unsubscribe(h1)
        assert adapter.subscription_count == 1

    def test_handler_count_per_topic(self) -> None:
        adapter = LocalEventAdapter()
        adapter.subscribe("t", lambda t, p: None)
        adapter.subscribe("t", lambda t, p: None)
        adapter.subscribe("other", lambda t, p: None)
        assert adapter.handler_count("t") == 2
        assert adapter.handler_count("other") == 1
        assert adapter.handler_count("unknown") == 0


class TestLocalEventAdapterCapture:
    """Capture mode: store events for test assertions."""

    def test_capture_mode_off_by_default(self) -> None:
        adapter = LocalEventAdapter()
        assert adapter.capture_mode is False
        adapter.emit("t", {"a": 1})
        assert adapter.captured_count == 0

    def test_capture_mode_constructor(self) -> None:
        adapter = LocalEventAdapter(capture_mode=True)
        assert adapter.capture_mode is True

    def test_capture_stores_events(self) -> None:
        adapter = LocalEventAdapter(capture_mode=True)
        adapter.emit("t1", {"a": 1})
        adapter.emit("t2", {"b": 2})
        assert adapter.captured_count == 2

    def test_get_captured_all(self) -> None:
        adapter = LocalEventAdapter(capture_mode=True)
        adapter.emit("t1", {"a": 1})
        adapter.emit("t2", {"b": 2})
        events = adapter.get_captured()
        assert len(events) == 2
        assert events[0] == ("t1", {"a": 1})
        assert events[1] == ("t2", {"b": 2})

    def test_get_captured_filtered(self) -> None:
        adapter = LocalEventAdapter(capture_mode=True)
        adapter.emit("t1", {"a": 1})
        adapter.emit("t2", {"b": 2})
        adapter.emit("t1", {"c": 3})
        events = adapter.get_captured(topic="t1")
        assert len(events) == 2
        assert events[0][1] == {"a": 1}
        assert events[1][1] == {"c": 3}

    def test_drain_returns_and_clears(self) -> None:
        adapter = LocalEventAdapter(capture_mode=True)
        adapter.emit("t", {"x": 1})
        adapter.emit("t", {"x": 2})
        events = adapter.drain()
        assert len(events) == 2
        assert adapter.captured_count == 0

    def test_assert_emitted_pass(self) -> None:
        adapter = LocalEventAdapter(capture_mode=True)
        adapter.emit("t", {})
        adapter.emit("t", {})
        adapter.assert_emitted("t", count=2)

    def test_assert_emitted_fail(self) -> None:
        adapter = LocalEventAdapter(capture_mode=True)
        adapter.emit("t", {})
        with pytest.raises(AssertionError, match="Expected 2"):
            adapter.assert_emitted("t", count=2)

    def test_assert_emitted_zero(self) -> None:
        adapter = LocalEventAdapter(capture_mode=True)
        adapter.assert_emitted("nonexistent", count=0)

    def test_clear_captured(self) -> None:
        adapter = LocalEventAdapter(capture_mode=True)
        adapter.emit("t", {})
        adapter.clear_captured()
        assert adapter.captured_count == 0

    def test_enable_disable_capture(self) -> None:
        adapter = LocalEventAdapter()
        adapter.emit("t", {"init": True})
        assert adapter.captured_count == 0
        adapter.enable_capture()
        adapter.emit("t", {"captured": True})
        assert adapter.captured_count == 1
        adapter.disable_capture()
        adapter.emit("t", {"not_captured": True})
        assert adapter.captured_count == 1  # Still 1

    def test_repr(self) -> None:
        adapter = LocalEventAdapter(capture_mode=True)
        adapter.emit("t", {})
        r = repr(adapter)
        assert "LocalEventAdapter" in r
        assert "capture_mode=True" in r


class TestLocalEventAdapterConcurrency:
    """Thread-safe emit and subscribe operations."""

    def test_concurrent_emit(self) -> None:
        adapter = LocalEventAdapter(capture_mode=True)
        errors: List[Exception] = []

        def emitter(n: int) -> None:
            try:
                for i in range(50):
                    adapter.emit(f"topic.{n}", {"i": i})
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=emitter, args=(n,)) for n in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5.0)

        assert not errors
        assert adapter.captured_count == 500  # 10 threads * 50 emits

    def test_concurrent_subscribe_emit(self) -> None:
        adapter = LocalEventAdapter(capture_mode=True)
        received = []
        lock = threading.Lock()

        def handler(topic: str, payload: Dict[str, Any]) -> None:
            with lock:
                received.append(topic)

        # Subscribe from multiple threads
        handles = []

        def subscriber(n: int) -> None:
            h = adapter.subscribe(f"topic.{n}", handler)
            with lock:
                handles.append(h)

        sub_threads = [threading.Thread(target=subscriber, args=(n,)) for n in range(10)]
        for t in sub_threads:
            t.start()
        for t in sub_threads:
            t.join(timeout=5.0)

        assert len(handles) == 10

        # Emit to each topic
        for n in range(10):
            adapter.emit(f"topic.{n}", {})

        assert len(received) == 10


class TestLocalEventAdapterFailingHandler:
    """Exception isolation in handlers."""

    def test_failing_handler_doesnt_block_others(self) -> None:
        results: List[str] = []
        adapter = LocalEventAdapter()
        adapter.subscribe("t", lambda t, p: (_ for _ in ()).throw(ValueError("boom")))
        adapter.subscribe("t", lambda t, p: results.append("ok"))
        # Should not raise despite first handler failing
        adapter.emit("t", {})
        assert results == ["ok"]

    def test_failing_handler_doesnt_affect_capture(self) -> None:
        adapter = LocalEventAdapter(capture_mode=True)

        def bad_handler(topic: str, payload: Dict[str, Any]) -> None:
            raise RuntimeError("handler broke")

        adapter.subscribe("t", bad_handler)
        adapter.emit("t", {"data": 1})
        # Event was captured before handler was called
        assert adapter.captured_count == 1


# ===========================================================================
# Adapters package exports
# ===========================================================================


class TestAdaptersExports:
    """Verify adapters __all__ exports."""

    def test_all_count(self) -> None:
        from k1.fabric.adapters import __all__

        assert len(__all__) >= 3

    def test_all_names(self) -> None:
        from k1.fabric.adapters import __all__

        assert "SessionStateReaderAdapter" in __all__
        assert "TestSessionStateReaderAdapter" in __all__
        assert "LocalEventAdapter" in __all__

    def test_all_importable(self) -> None:
        import k1.fabric.adapters as pkg
        from k1.fabric.adapters import __all__

        for name in __all__:
            assert hasattr(pkg, name), f"{name} not importable"
