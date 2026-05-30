"""tests/k1/concierge/test_m6_e2_narrative_weaving.py

M6.E2 -- Narrative Weaving wiring tests.

Covers:
  * I1: ``_build_experience_context`` projects ``intent`` / ``topic`` /
        ``thread`` from ``TypedHistoryEntry.metadata`` so NarrativeWeaver
        receives non-empty signal.
  * I2: ``_tick_experience`` writes a non-empty ``narrative`` output to
        the ``narrative_active`` SS section: create on empty, update on
        same primary, and switch only when salience delta >= 0.25.
  * I2 negative: skip when FSM state is ``CLARIFYING_WORKER``.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

# ---------------------------------------------------------------------------
# Lightweight runtime stand-in -- exercises just the methods under test.
# ---------------------------------------------------------------------------


def _make_runtime(
    *,
    fsm_state: str = "STANDARD",
    narrative=None,
    section=None,
    turn_number: int = 5,
    history_entries: list | None = None,
):
    from k1.concierge.session import ConciergeRuntime

    rt = ConciergeRuntime.__new__(ConciergeRuntime)
    rt._fsm = SimpleNamespace(
        state=SimpleNamespace(name=fsm_state),
        history=[],
        turn_number=turn_number,
    )
    layer_mock = MagicMock()
    layer_mock.tick = AsyncMock(return_value={"narrative": narrative})
    rt._experience_layer = layer_mock

    # Minimal session_state with get_section returning ``section`` for
    # narrative_active and a benign ``history_active`` if requested.
    sections = {"narrative_active": section}
    if history_entries is not None:
        ha = MagicMock()
        ha.get_typed_entries = MagicMock(return_value=history_entries)
        sections["history_active"] = ha
    rt._session_state = SimpleNamespace(get_section=lambda name: sections.get(name))

    rt._bus = SimpleNamespace(publish=lambda *a, **kw: None)
    return rt


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro) if False else asyncio.run(coro)


# ---------------------------------------------------------------------------
# I2: write narrative to narrative_active
# ---------------------------------------------------------------------------


class TestNarrativeWriter:
    def test_creates_thread_when_primary_absent(self):
        section = MagicMock()
        section.primary_thread = None
        section.create_thread = MagicMock()
        section.update_thread = MagicMock()

        narrative = SimpleNamespace(
            active_threads=["paris_trip", "groceries"],
            thread_salience={"paris_trip": 0.7, "groceries": 0.3},
            weave_suggestion="Continue thread: paris_trip",
        )
        rt = _make_runtime(narrative=narrative, section=section)
        _run(rt._tick_experience())

        section.create_thread.assert_called_once()
        kwargs = section.create_thread.call_args.kwargs
        assert kwargs["title"] == "paris_trip"
        assert kwargs["goal"] == "Continue thread: paris_trip"
        assert kwargs["turn_number"] == 5
        assert kwargs["related_intents"][:2] == ["paris_trip", "groceries"]
        section.update_thread.assert_not_called()

    def test_updates_existing_thread_when_top_matches(self):
        section = MagicMock()
        primary = SimpleNamespace(id="t1", title="paris_trip")
        section.primary_thread = primary
        section.create_thread = MagicMock()
        section.update_thread = MagicMock()

        narrative = SimpleNamespace(
            active_threads=["paris_trip"],
            thread_salience={"paris_trip": 1.0},
            weave_suggestion="Continue thread: paris_trip",
        )
        rt = _make_runtime(narrative=narrative, section=section)
        _run(rt._tick_experience())

        section.update_thread.assert_called_once()
        args, kwargs = section.update_thread.call_args
        assert args[0] == "t1"
        assert kwargs["goal"] == "Continue thread: paris_trip"
        section.create_thread.assert_not_called()

    def test_does_not_switch_when_salience_delta_below_threshold(self):
        """Different top thread but delta < 0.25 -> update existing,
        do NOT create a new thread (anti-thrash gate)."""
        section = MagicMock()
        primary = SimpleNamespace(id="t1", title="paris_trip")
        section.primary_thread = primary
        section.create_thread = MagicMock()
        section.update_thread = MagicMock()

        narrative = SimpleNamespace(
            active_threads=["groceries", "paris_trip"],
            thread_salience={"groceries": 0.55, "paris_trip": 0.45},  # delta 0.10
            weave_suggestion="Continue thread: groceries",
        )
        rt = _make_runtime(narrative=narrative, section=section)
        _run(rt._tick_experience())

        section.create_thread.assert_not_called()
        section.update_thread.assert_called_once()

    def test_switches_thread_when_salience_delta_meets_threshold(self):
        section = MagicMock()
        primary = SimpleNamespace(id="t1", title="paris_trip")
        section.primary_thread = primary
        section.create_thread = MagicMock()
        section.update_thread = MagicMock()

        narrative = SimpleNamespace(
            active_threads=["groceries", "paris_trip"],
            thread_salience={"groceries": 0.7, "paris_trip": 0.3},  # delta 0.40
            weave_suggestion="Continue thread: groceries",
        )
        rt = _make_runtime(narrative=narrative, section=section)
        _run(rt._tick_experience())

        section.create_thread.assert_called_once()
        assert section.create_thread.call_args.kwargs["title"] == "groceries"

    def test_skip_when_fsm_clarifying_worker(self):
        section = MagicMock()
        section.primary_thread = None
        section.create_thread = MagicMock()
        section.update_thread = MagicMock()

        narrative = SimpleNamespace(
            active_threads=["paris_trip"],
            thread_salience={"paris_trip": 1.0},
            weave_suggestion="x",
        )
        rt = _make_runtime(fsm_state="CLARIFYING_WORKER", narrative=narrative, section=section)
        _run(rt._tick_experience())

        section.create_thread.assert_not_called()
        section.update_thread.assert_not_called()

    def test_skip_when_narrative_is_none(self):
        section = MagicMock()
        section.primary_thread = None
        section.create_thread = MagicMock()
        rt = _make_runtime(narrative=None, section=section)
        _run(rt._tick_experience())
        section.create_thread.assert_not_called()

    def test_skip_when_active_threads_empty(self):
        section = MagicMock()
        section.primary_thread = None
        section.create_thread = MagicMock()
        narrative = SimpleNamespace(active_threads=[], thread_salience={}, weave_suggestion="")
        rt = _make_runtime(narrative=narrative, section=section)
        _run(rt._tick_experience())
        section.create_thread.assert_not_called()


# ---------------------------------------------------------------------------
# I1: _build_experience_context projects intent/topic/thread
# ---------------------------------------------------------------------------


class TestExperienceContextProjection:
    def test_metadata_arbiter_decision_projects_to_intent(self):
        from k1.sessionstate.sections.history_active import TypedHistoryEntry

        entry = TypedHistoryEntry(
            turn_number=1,
            entry_type="user_input",
            text="hi",
            timestamp_ms=1,
            source="user",
            metadata={
                "arbiter": {"decision": "STANDARD"},
                "topic": "trip_planning",
                "thread": "paris_trip",
            },
        )
        rt = _make_runtime(history_entries=[entry])
        ctx = rt._build_experience_context()
        rows = ctx["conversation_history"]
        assert len(rows) == 1
        row = rows[0]
        assert row["intent"] == "STANDARD"
        assert row["topic"] == "trip_planning"
        assert row["thread"] == "paris_trip"

    def test_metadata_intent_used_when_no_arbiter(self):
        from k1.sessionstate.sections.history_active import TypedHistoryEntry

        entry = TypedHistoryEntry(
            turn_number=1,
            entry_type="user_input",
            text="hi",
            timestamp_ms=1,
            source="user",
            metadata={"intent": "WEAVE"},
        )
        rt = _make_runtime(history_entries=[entry])
        ctx = rt._build_experience_context()
        assert ctx["conversation_history"][0]["intent"] == "WEAVE"

    def test_entry_type_fallback_when_no_metadata_signals(self):
        from k1.sessionstate.sections.history_active import TypedHistoryEntry

        entry = TypedHistoryEntry(
            turn_number=1,
            entry_type="user_input",
            text="hi",
            timestamp_ms=1,
            source="user",
            metadata={},
        )
        rt = _make_runtime(history_entries=[entry])
        ctx = rt._build_experience_context()
        assert ctx["conversation_history"][0]["intent"] == "user_input"

    def test_narrative_weaver_sees_intent_signal_end_to_end(self):
        """Sanity-check: with projected rows the NarrativeWeaver must
        produce non-empty active_threads."""
        from k1.concierge.experience.narrative_weaver import NarrativeWeaver

        rows = [
            {"intent": "trip_planning", "topic": "", "thread": ""},
            {"intent": "trip_planning", "topic": "", "thread": ""},
            {"intent": "groceries", "topic": "", "thread": ""},
        ]
        weaver = NarrativeWeaver()
        ctx = asyncio.run(weaver.weave(rows, []))
        assert ctx.active_threads
        assert ctx.active_threads[0] == "trip_planning"
