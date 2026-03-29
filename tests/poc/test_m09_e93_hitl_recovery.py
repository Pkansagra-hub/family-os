"""
M9 E9.3: HITL Coordinator ledger integration + rebuild tests.

Covers:
    E9.3.1 -- HILCoordinator emits HILRequested/HILResolved to ledger.
    E9.3.2 -- project_hitl_state() projection.
    E9.3.3 -- HILCoordinator.rebuild_from_events().
    E9.3.4 -- Multi-round HITL crash recovery with L2 defense.

Run:
    python -m pytest tests/poc/test_m09_e93_hitl_recovery.py -v
"""

from __future__ import annotations

from typing import Any

import pytest

from poc.k1_poc.ledger.projections import project_hitl_state
from poc.k1_poc.ledger.store import InMemoryLedgerStore, LedgerEntry
from poc.k1_poc.ledger.writer import LedgerWriter
from poc.k1_poc.protocols.hitl import SafetyBand
from poc.k1_poc.protocols.hitl_coordinator import HILCoordinator, HILCoordinatorConfig

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_writer(session_id: str = "s1") -> LedgerWriter:
    store = InMemoryLedgerStore()
    return LedgerWriter(store, session_id=session_id)


def _entries(writer: LedgerWriter) -> list[LedgerEntry]:
    return writer.store.read(writer.session_id)


def _make_ledger_entry(
    event_type: str,
    task_id: str,
    seq: int = 0,
    **extra: Any,
) -> LedgerEntry:
    payload: dict[str, Any] = {"task_id": task_id, **extra}
    return LedgerEntry(
        seq=seq,
        event_id=f"evt-{seq}",
        event_type=event_type,
        session_id="s1",
        payload=payload,
        written_at_utc="2025-01-01T00:00:00Z",
    )


def _make_coordinator(
    ledger: LedgerWriter | None = None,
    max_rounds: int = 3,
) -> HILCoordinator:
    cfg = HILCoordinatorConfig(
        max_rounds=max_rounds,
        timeouts={"clarification": 60000, "approval": 120000, "selection": 90000},
    )
    return HILCoordinator(config=cfg, ledger=ledger)


# ===================================================================
# E9.3.1 -- HILCoordinator ledger writes
# ===================================================================


class TestHILCoordinatorLedgerWrites:
    """Verify handle_needs_human/handle_user_response emit events."""

    @pytest.mark.asyncio
    async def test_handle_needs_human_writes_hil_requested(self) -> None:
        writer = _make_writer()
        coord = _make_coordinator(ledger=writer)

        await coord.handle_needs_human(
            task_id="t1",
            hil_type="clarification",
            question="Which hotel?",
        )

        entries = _entries(writer)
        # SuspensionManager also writes task.suspended, so we should have >=1
        requested = [e for e in entries if e.event_type == "hil.requested"]
        assert len(requested) == 1
        assert requested[0].payload["task_id"] == "t1"
        assert requested[0].payload["hil_type"] == "clarification"
        assert requested[0].payload["question"] == "Which hotel?"

    @pytest.mark.asyncio
    async def test_handle_user_response_writes_hil_resolved(self) -> None:
        writer = _make_writer()
        coord = _make_coordinator(ledger=writer)

        await coord.handle_needs_human(task_id="t1", hil_type="clarification", question="Q?")
        await coord.handle_user_response(
            task_id="t1",
            decision="answered",
            resolution={"answer": "option_b"},
            raw_user_text="I pick B",
        )

        entries = _entries(writer)
        resolved = [e for e in entries if e.event_type == "hil.resolved"]
        assert len(resolved) == 1
        assert resolved[0].payload["task_id"] == "t1"
        assert resolved[0].payload["resolution_type"] == "answered"
        assert resolved[0].payload["raw_user_text"] == "I pick B"

    @pytest.mark.asyncio
    async def test_no_ledger_no_writes(self) -> None:
        coord = _make_coordinator()
        await coord.handle_needs_human(task_id="t1", hil_type="clarification", question="Q?")
        assert coord.is_pending("t1")

    @pytest.mark.asyncio
    async def test_set_ledger_post_construction(self) -> None:
        writer = _make_writer()
        coord = _make_coordinator()
        coord.set_ledger(writer)

        await coord.handle_needs_human(task_id="t1", hil_type="approval", question="Confirm?")
        requested = [e for e in _entries(writer) if e.event_type == "hil.requested"]
        assert len(requested) == 1

    @pytest.mark.asyncio
    async def test_response_for_non_pending_no_write(self) -> None:
        writer = _make_writer()
        coord = _make_coordinator(ledger=writer)
        result = await coord.handle_user_response(task_id="t_none", decision="answered")
        assert result is None
        resolved = [e for e in _entries(writer) if e.event_type == "hil.resolved"]
        assert len(resolved) == 0


# ===================================================================
# E9.3.2 -- project_hitl_state()
# ===================================================================


class TestHITLStateProjection:
    """Verify project_hitl_state() replays events correctly."""

    def test_empty_events(self) -> None:
        pending, counts, histories = project_hitl_state([])
        assert pending == {}
        assert counts == {}
        assert histories == {}

    def test_requested_task_is_pending(self) -> None:
        entries = [
            _make_ledger_entry(
                "hil.requested", "t1", seq=1, hil_type="clarification", question="Which?"
            ),
        ]
        pending, counts, histories = project_hitl_state(entries)
        assert "t1" in pending
        assert pending["t1"]["hil_type"] == "clarification"
        assert counts["t1"] == 1
        assert "t1" not in histories

    def test_resolved_clears_pending(self) -> None:
        entries = [
            _make_ledger_entry("hil.requested", "t1", seq=1, hil_type="clarification"),
            _make_ledger_entry(
                "hil.resolved",
                "t1",
                seq=2,
                resolution={"answer": "yes"},
                resolution_type="answered",
            ),
        ]
        pending, counts, histories = project_hitl_state(entries)
        assert "t1" not in pending
        assert counts["t1"] == 1
        assert len(histories["t1"]) == 1
        assert histories["t1"][0]["resolution_type"] == "answered"

    def test_two_rounds(self) -> None:
        entries = [
            _make_ledger_entry("hil.requested", "t1", seq=1, hil_type="clarification"),
            _make_ledger_entry(
                "hil.resolved", "t1", seq=2, resolution={}, resolution_type="answered"
            ),
            _make_ledger_entry("hil.requested", "t1", seq=3, hil_type="approval"),
            _make_ledger_entry(
                "hil.resolved", "t1", seq=4, resolution={}, resolution_type="approved"
            ),
        ]
        pending, counts, histories = project_hitl_state(entries)
        assert "t1" not in pending
        assert counts["t1"] == 2
        assert len(histories["t1"]) == 2

    def test_completed_clears_pending(self) -> None:
        entries = [
            _make_ledger_entry("hil.requested", "t1", seq=1, hil_type="clarification"),
            _make_ledger_entry("task.completed", "t1", seq=2),
        ]
        pending, counts, histories = project_hitl_state(entries)
        assert "t1" not in pending

    def test_mixed_tasks(self) -> None:
        entries = [
            _make_ledger_entry("hil.requested", "t1", seq=1, hil_type="clarification"),
            _make_ledger_entry("hil.requested", "t2", seq=2, hil_type="approval"),
            _make_ledger_entry(
                "hil.resolved", "t1", seq=3, resolution={}, resolution_type="answered"
            ),
        ]
        pending, counts, histories = project_hitl_state(entries)
        assert "t1" not in pending
        assert "t2" in pending
        assert counts["t1"] == 1
        assert counts["t2"] == 1


# ===================================================================
# E9.3.3 -- HILCoordinator.rebuild_from_events()
# ===================================================================


class TestHILCoordinatorRebuildFromEvents:
    """Verify rebuild restores coordinator state from projection."""

    def test_rebuild_pending_request(self) -> None:
        entries = [
            _make_ledger_entry(
                "hil.requested",
                "t1",
                seq=1,
                hil_type="clarification",
                question="Which hotel?",
                options=[{"label": "A"}, {"label": "B"}],
                safety_band="AMBER",
                timeout_s=60.0,
                max_rounds=3,
            ),
        ]
        coord = _make_coordinator()
        restored = coord.rebuild_from_events(entries)

        assert restored == 1
        assert coord.is_pending("t1")
        req = coord.get_pending_request("t1")
        assert req is not None
        assert req.hil_type == "clarification"
        assert req.question == "Which hotel?"
        assert req.safety_band == SafetyBand.AMBER

    def test_rebuild_resolved_not_pending(self) -> None:
        entries = [
            _make_ledger_entry("hil.requested", "t1", seq=1, hil_type="clarification"),
            _make_ledger_entry(
                "hil.resolved", "t1", seq=2, resolution={}, resolution_type="answered"
            ),
        ]
        coord = _make_coordinator()
        restored = coord.rebuild_from_events(entries)

        assert restored == 0
        assert not coord.is_pending("t1")

    def test_rebuild_preserves_hil_counts(self) -> None:
        entries = [
            _make_ledger_entry("hil.requested", "t1", seq=1, hil_type="clarification"),
            _make_ledger_entry(
                "hil.resolved", "t1", seq=2, resolution={}, resolution_type="answered"
            ),
            _make_ledger_entry("hil.requested", "t1", seq=3, hil_type="approval"),
        ]
        coord = _make_coordinator()
        coord.rebuild_from_events(entries)

        assert coord.get_hil_count("t1") == 2

    def test_rebuild_clears_previous_state(self) -> None:
        coord = _make_coordinator()
        coord._hil_counts["old"] = 5

        entries = [
            _make_ledger_entry("hil.requested", "t1", seq=1, hil_type="clarification"),
        ]
        coord.rebuild_from_events(entries)

        assert "old" not in coord._hil_counts
        assert coord.is_pending("t1")


# ===================================================================
# E9.3.4 -- Multi-round HITL crash recovery + L2 defense
# ===================================================================


class TestHITLCrashRecoveryWithL2:
    """End-to-end: multi-round HITL -> crash -> rebuild -> L2 check."""

    @pytest.mark.asyncio
    async def test_two_rounds_crash_rebuild_counts_correct(self) -> None:
        """2 HITL rounds -> crash -> rebuild -> round counts = 2."""
        writer = _make_writer()
        coord = _make_coordinator(ledger=writer, max_rounds=3)

        # Round 1
        await coord.handle_needs_human(task_id="t1", hil_type="clarification", question="Q1?")
        await coord.handle_user_response(task_id="t1", decision="answered")

        # Round 2
        await coord.handle_needs_human(task_id="t1", hil_type="approval", question="Confirm?")
        await coord.handle_user_response(task_id="t1", decision="approved")

        # Crash -> rebuild
        coord2 = _make_coordinator(max_rounds=3)
        entries = _entries(writer)
        coord2.rebuild_from_events(entries)

        assert coord2.get_hil_count("t1") == 2
        assert not coord2.is_pending("t1")

    @pytest.mark.asyncio
    async def test_pending_request_survives_crash(self) -> None:
        """HITL requested but not resolved -> crash -> rebuild -> still pending."""
        writer = _make_writer()
        coord = _make_coordinator(ledger=writer)

        await coord.handle_needs_human(task_id="t1", hil_type="clarification", question="Which?")

        # Crash -> rebuild
        coord2 = _make_coordinator()
        entries = _entries(writer)
        coord2.rebuild_from_events(entries)

        assert coord2.is_pending("t1")
        assert coord2.get_hil_count("t1") == 1

    def test_l2_defense_uses_rebuilt_history(self) -> None:
        """L2 defense check works with rebuilt HITL history from projection."""
        # Build history entries as if recovered from projection
        entries = [
            _make_ledger_entry("hil.requested", "t1", seq=1, hil_type="clarification"),
            _make_ledger_entry(
                "hil.resolved", "t1", seq=2, resolution={}, resolution_type="answered"
            ),
        ]
        _, _, histories = project_hitl_state(entries)

        coord = _make_coordinator()
        # No prior approval in history -> should block
        result = coord.validate_before_invoke(
            task_id="t1",
            capability_contract={"has_side_effects": True, "safety_band": "AMBER"},
            task_history=histories.get("t1", []),
        )
        assert result == "block_needs_approval"

    def test_l2_allows_after_approval_in_history(self) -> None:
        """L2 allows execution when rebuilt history contains prior approval."""
        entries = [
            _make_ledger_entry(
                "hil.requested",
                "t1",
                seq=1,
                hil_type="approval",
            ),
            _make_ledger_entry(
                "hil.resolved",
                "t1",
                seq=2,
                resolution={"decision": "approve"},
                resolution_type="approved",
                hil_type="approval",
            ),
        ]
        _, _, histories = project_hitl_state(entries)

        coord = _make_coordinator()
        result = coord.validate_before_invoke(
            task_id="t1",
            capability_contract={"has_side_effects": True, "safety_band": "AMBER"},
            task_history=histories.get("t1", []),
        )
        assert result == "allow"
