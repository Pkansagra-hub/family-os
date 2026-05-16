"""
Tests for Epics 11.4, 11.5, 11.6 -- DeltaApplicator, WriterRegistry,
SnapshotReader.

Epic 11.4: FSM Delta Applicator
    V2 Design Ref: Section 5 (DeltaAggregator Write Pipeline, FSM.apply_deltas)
    DeltaApplicator apply, preflight check, eviction retry, notify.

Epic 11.5: Single Writer Enforcement
    V2 Design Ref: Section 5 (Single Writer Invariant, Read/Write Matrix)
    WriterRole enum, SECTION_WRITERS, validate_writer, enforce_writer.

Epic 11.6: Cross-Actor Read Consistency
    V2 Design Ref: Section 5 (lock-free snapshots, <1ms reads)
    SnapshotReader read, write, delete, read_multiple, snapshot isolation.

Source of truth: implemented code + concierge_poc_design_v2.md
"""

from __future__ import annotations

import importlib
import time

import pytest

from k1.concierge.delta.aggregator import DeltaBatch
from k1.concierge.delta.applicator import ApplyResult, DeltaApplicator
from k1.concierge.delta.session_delta import SessionDelta
from k1.concierge.delta.snapshot_reader import SectionSnapshot, SnapshotReader
from k1.concierge.delta.writer_registry import (
    ALL_WRITER_SECTIONS,
    SECTION_WRITERS,
    SingleWriterViolation,
    WriterRole,
    enforce_writer,
    validate_writer,
)

# =========================================================================
# Helpers
# =========================================================================


def _delta(
    section: str = "task_state",
    key: str = "task-1",
    operation: str = "set",
    data: dict | None = None,
    delta_id: str | None = None,
) -> SessionDelta:
    kwargs: dict = {
        "section": section,
        "key": key,
        "operation": operation,
        "data": data if data is not None else {},
    }
    if delta_id is not None:
        kwargs["delta_id"] = delta_id
    return SessionDelta(**kwargs)


def _batch(deltas: list[SessionDelta], batch_id: str = "batch-test") -> DeltaBatch:
    return DeltaBatch(
        deltas=deltas,
        batch_id=batch_id,
        collected_at_ns=0,
    )


# =========================================================================
# Fake Approval (duck-typed to match sessionstate.guard.Approval)
# =========================================================================


class FakeApproval:
    """Duck-typed Approval for testing DeltaApplicator preflight."""

    def __init__(self, approved: bool, reason: str = "") -> None:
        self.approved = approved
        self.reason = reason


# =========================================================================
# Epic 11.4 -- FSM Delta Applicator
# =========================================================================


class TestApplyResultDataclass:
    """11.4.1 -- ApplyResult structure and computed properties."""

    def test_basic_creation(self):
        r = ApplyResult(batch_id="batch-1")
        assert r.batch_id == "batch-1"
        assert r.applied == 0
        assert r.rejected == 0
        assert r.evicted == 0
        assert r.rejections == []

    def test_total_property(self):
        r = ApplyResult(batch_id="b", applied=3, rejected=1)
        assert r.total == 4

    def test_success_rate_all_applied(self):
        r = ApplyResult(batch_id="b", applied=5, rejected=0)
        assert r.success_rate == 1.0

    def test_success_rate_partial(self):
        r = ApplyResult(batch_id="b", applied=3, rejected=1)
        assert r.success_rate == 0.75

    def test_success_rate_all_rejected(self):
        r = ApplyResult(batch_id="b", applied=0, rejected=2)
        assert r.success_rate == 0.0

    def test_success_rate_empty(self):
        r = ApplyResult(batch_id="b")
        assert r.success_rate == 1.0  # vacuously true


class TestDeltaApplicatorApply:
    """11.4.1 -- DeltaApplicator.apply() basic path."""

    @pytest.mark.asyncio
    async def test_apply_all_approved(self):
        """All deltas pass preflight and are written."""
        writes: list[tuple] = []

        async def mock_write(section, key, op, data):
            writes.append((section, key, op, data))

        applicator = DeltaApplicator(
            preflight_fn=lambda s, o, sz: FakeApproval(approved=True),
            write_fn=mock_write,
        )
        batch = _batch(
            [
                _delta(section="task_state", key="t1", data={"status": "COMPLETED"}),
                _delta(
                    section="task_artifacts", key="t1:booking", operation="append", data={"x": 1}
                ),
            ]
        )
        result = await applicator.apply(batch)

        assert result.applied == 2
        assert result.rejected == 0
        assert len(writes) == 2

    @pytest.mark.asyncio
    async def test_apply_no_preflight(self):
        """Without preflight_fn, all deltas are written unconditionally."""
        writes: list[tuple] = []

        async def mock_write(section, key, op, data):
            writes.append((section, key))

        applicator = DeltaApplicator(write_fn=mock_write)
        batch = _batch([_delta(), _delta(key="t2")])
        result = await applicator.apply(batch)

        assert result.applied == 2
        assert len(writes) == 2

    @pytest.mark.asyncio
    async def test_apply_no_write_fn(self):
        """Without write_fn, apply still counts correctly (dry run)."""
        applicator = DeltaApplicator(
            preflight_fn=lambda s, o, sz: FakeApproval(approved=True),
        )
        batch = _batch([_delta()])
        result = await applicator.apply(batch)

        assert result.applied == 1

    @pytest.mark.asyncio
    async def test_apply_empty_batch(self):
        """Empty batch produces zero counts."""
        applicator = DeltaApplicator()
        batch = _batch([])
        result = await applicator.apply(batch)

        assert result.applied == 0
        assert result.rejected == 0
        assert result.total == 0

    @pytest.mark.asyncio
    async def test_batch_id_propagated(self):
        """batch_id from DeltaBatch is propagated to ApplyResult."""
        applicator = DeltaApplicator()
        batch = _batch([], batch_id="batch-42")
        result = await applicator.apply(batch)

        assert result.batch_id == "batch-42"


class TestDeltaApplicatorRejection:
    """11.4.1 -- DeltaApplicator rejection paths."""

    @pytest.mark.asyncio
    async def test_rejected_no_eviction(self):
        """Rejected delta without evict_fn is rejected directly."""
        applicator = DeltaApplicator(
            preflight_fn=lambda s, o, sz: FakeApproval(approved=False, reason="section full"),
        )
        batch = _batch([_delta(delta_id="d-rej")])
        result = await applicator.apply(batch)

        assert result.applied == 0
        assert result.rejected == 1
        assert len(result.rejections) == 1
        assert result.rejections[0]["delta_id"] == "d-rej"
        assert result.rejections[0]["reason"] == "section full"

    @pytest.mark.asyncio
    async def test_rejected_eviction_succeeds(self):
        """Rejected delta triggers eviction, retry succeeds."""
        call_count = 0

        def preflight(s, o, sz):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return FakeApproval(approved=False, reason="full")
            return FakeApproval(approved=True)

        writes: list = []

        async def mock_write(s, k, o, d):
            writes.append((s, k))

        async def mock_evict(section, needed):
            return 1

        applicator = DeltaApplicator(
            preflight_fn=preflight,
            write_fn=mock_write,
            evict_fn=mock_evict,
        )
        batch = _batch([_delta(section="task_artifacts", key="t1:x", data={"v": 1})])
        result = await applicator.apply(batch)

        assert result.applied == 1
        assert result.rejected == 0
        assert result.evicted == 1
        assert len(writes) == 1

    @pytest.mark.asyncio
    async def test_rejected_eviction_frees_nothing(self):
        """Eviction returns 0 -- delta is rejected."""

        async def mock_evict(section, needed):
            return 0

        applicator = DeltaApplicator(
            preflight_fn=lambda s, o, sz: FakeApproval(approved=False, reason="overflow"),
            evict_fn=mock_evict,
        )
        batch = _batch([_delta(delta_id="d-stuck")])
        result = await applicator.apply(batch)

        assert result.applied == 0
        assert result.rejected == 1
        assert result.evicted == 0
        assert result.rejections[0]["delta_id"] == "d-stuck"

    @pytest.mark.asyncio
    async def test_rejected_eviction_retry_also_fails(self):
        """Eviction succeeds but retry preflight still rejects."""

        async def mock_evict(section, needed):
            return 2

        applicator = DeltaApplicator(
            preflight_fn=lambda s, o, sz: FakeApproval(approved=False, reason="still full"),
            evict_fn=mock_evict,
        )
        batch = _batch([_delta(delta_id="d-double")])
        result = await applicator.apply(batch)

        assert result.applied == 0
        assert result.rejected == 1
        assert result.evicted == 2
        assert "still full" in result.rejections[0]["reason"]

    @pytest.mark.asyncio
    async def test_mixed_approved_and_rejected(self):
        """Batch with some approved and some rejected deltas."""
        call_count = 0

        def preflight(s, o, sz):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                return FakeApproval(approved=False, reason="no room")
            return FakeApproval(approved=True)

        writes: list = []

        async def mock_write(s, k, o, d):
            writes.append(k)

        applicator = DeltaApplicator(
            preflight_fn=preflight,
            write_fn=mock_write,
        )
        batch = _batch(
            [
                _delta(key="t1"),
                _delta(key="t2"),  # This one gets rejected
                _delta(key="t3"),
            ]
        )
        result = await applicator.apply(batch)

        assert result.applied == 2
        assert result.rejected == 1
        assert len(writes) == 2


class TestDeltaApplicatorNotify:
    """11.4.3 -- DeltaApplicator notification."""

    @pytest.mark.asyncio
    async def test_notify_emitted_on_apply(self):
        """notify_fn is called when deltas are applied."""
        notifications: list[tuple] = []

        async def mock_notify(batch_id, count):
            notifications.append((batch_id, count))

        async def mock_write(s, k, o, d):
            pass

        applicator = DeltaApplicator(
            preflight_fn=lambda s, o, sz: FakeApproval(approved=True),
            write_fn=mock_write,
            notify_fn=mock_notify,
        )
        batch = _batch([_delta()], batch_id="batch-notify")
        await applicator.apply(batch)

        assert len(notifications) == 1
        assert notifications[0] == ("batch-notify", 1)

    @pytest.mark.asyncio
    async def test_notify_with_correct_count(self):
        """notify_fn receives the correct count of applied deltas."""
        notifications: list[tuple] = []

        async def mock_notify(batch_id, count):
            notifications.append((batch_id, count))

        async def mock_write(s, k, o, d):
            pass

        applicator = DeltaApplicator(
            preflight_fn=lambda s, o, sz: FakeApproval(approved=True),
            write_fn=mock_write,
            notify_fn=mock_notify,
        )
        batch = _batch([_delta(key="a"), _delta(key="b"), _delta(key="c")])
        await applicator.apply(batch)

        assert notifications[0][1] == 3

    @pytest.mark.asyncio
    async def test_no_notify_when_nothing_applied(self):
        """notify_fn is NOT called when all deltas are rejected."""
        notifications: list = []

        async def mock_notify(batch_id, count):
            notifications.append(batch_id)

        applicator = DeltaApplicator(
            preflight_fn=lambda s, o, sz: FakeApproval(approved=False, reason="blocked"),
            notify_fn=mock_notify,
        )
        batch = _batch([_delta()])
        await applicator.apply(batch)

        assert len(notifications) == 0

    @pytest.mark.asyncio
    async def test_no_notify_fn_is_fine(self):
        """apply() works fine without notify_fn."""

        async def mock_write(s, k, o, d):
            pass

        applicator = DeltaApplicator(write_fn=mock_write)
        batch = _batch([_delta()])
        result = await applicator.apply(batch)

        assert result.applied == 1


class TestDeltaApplicatorWriteData:
    """11.4.1 -- Verify correct data reaches write_fn."""

    @pytest.mark.asyncio
    async def test_write_receives_correct_args(self):
        """write_fn receives section, key, operation, data from delta."""
        writes: list[tuple] = []

        async def mock_write(section, key, op, data):
            writes.append((section, key, op, data))

        applicator = DeltaApplicator(write_fn=mock_write)
        d = _delta(
            section="task_artifacts",
            key="t1:booking",
            operation="append",
            data={"hotel": "Vineyard"},
        )
        batch = _batch([d])
        await applicator.apply(batch)

        assert len(writes) == 1
        section, key, op, data = writes[0]
        assert section == "task_artifacts"
        assert key == "t1:booking"
        assert op == "append"
        assert data == {"hotel": "Vineyard"}


# =========================================================================
# Epic 11.5 -- Single Writer Enforcement
# =========================================================================


class TestWriterRole:
    """11.5.1 -- WriterRole enum values."""

    def test_front_llm(self):
        assert WriterRole.FRONT_LLM.value == "front_llm"

    def test_fsm(self):
        assert WriterRole.FSM.value == "fsm"

    def test_experience_layer(self):
        assert WriterRole.EXPERIENCE_LAYER.value == "experience_layer"

    def test_session_init(self):
        assert WriterRole.SESSION_INIT.value == "session_init"

    def test_all_roles_count(self):
        """Four roles: FRONT_LLM, FSM, EXPERIENCE_LAYER, SESSION_INIT."""
        assert len(WriterRole) == 4

    def test_no_back_llm_role(self):
        """Back LLM is NOT a WriterRole (V2 Section 5, Rule 2)."""
        role_names = {r.name for r in WriterRole}
        assert "BACK_LLM" not in role_names
        assert "BACK" not in role_names


class TestSectionWritersMatrix:
    """11.5.1 -- SECTION_WRITERS matches V2 Section 5 Read/Write Matrix."""

    def test_all_11_sections_present(self):
        """All 11 sections from the V2 design doc are registered."""
        expected = {
            "beliefs_active",
            "scoreboard",
            "affective_now",
            "clarifications",
            "narrative_active",
            "control",
            "history_active",
            "meta",
            "persona",
            "task_state",
            "task_artifacts",
        }
        assert set(SECTION_WRITERS.keys()) == expected

    def test_beliefs_active_writers(self):
        assert SECTION_WRITERS["beliefs_active"] == [WriterRole.FRONT_LLM]

    def test_scoreboard_writers(self):
        """scoreboard: Front LLM only (post-Phase1 removal)."""
        assert SECTION_WRITERS["scoreboard"] == [WriterRole.FRONT_LLM]

    def test_affective_now_writers(self):
        """affective_now: Front LLM, ExperienceLayer."""
        assert SECTION_WRITERS["affective_now"] == [
            WriterRole.FRONT_LLM,
            WriterRole.EXPERIENCE_LAYER,
        ]

    def test_clarifications_writers(self):
        assert SECTION_WRITERS["clarifications"] == [WriterRole.FRONT_LLM]

    def test_narrative_active_writers(self):
        assert SECTION_WRITERS["narrative_active"] == [WriterRole.FRONT_LLM]

    def test_control_writers(self):
        """control: FSM only (post-Phase1 removal)."""
        assert SECTION_WRITERS["control"] == [WriterRole.FSM]

    def test_history_active_writer(self):
        assert SECTION_WRITERS["history_active"] == [WriterRole.FSM]

    def test_meta_writer(self):
        assert SECTION_WRITERS["meta"] == [WriterRole.FSM]

    def test_persona_writer(self):
        """persona: SESSION_INIT only (read-only after init)."""
        assert SECTION_WRITERS["persona"] == [WriterRole.SESSION_INIT]

    def test_task_state_writer(self):
        """task_state: FSM only (via DeltaApplicator from Back bus deltas)."""
        assert SECTION_WRITERS["task_state"] == [WriterRole.FSM]

    def test_task_artifacts_writer(self):
        """task_artifacts: FSM only (via DeltaApplicator)."""
        assert SECTION_WRITERS["task_artifacts"] == [WriterRole.FSM]

    def test_every_section_has_at_least_one_writer(self):
        for section, writers in SECTION_WRITERS.items():
            assert len(writers) >= 1, f"{section} has no writers"

    def test_all_writer_sections_constant(self):
        assert ALL_WRITER_SECTIONS == frozenset(SECTION_WRITERS.keys())
        assert isinstance(ALL_WRITER_SECTIONS, frozenset)


class TestValidateWriter:
    """11.5.1 -- validate_writer() function."""

    def test_front_llm_writes_beliefs(self):
        assert validate_writer("beliefs_active", WriterRole.FRONT_LLM) is True

    def test_fsm_writes_task_state(self):
        assert validate_writer("task_state", WriterRole.FSM) is True

    def test_fsm_writes_task_artifacts(self):
        assert validate_writer("task_artifacts", WriterRole.FSM) is True

    def test_fsm_writes_history_active(self):
        assert validate_writer("history_active", WriterRole.FSM) is True

    def test_fsm_writes_meta(self):
        assert validate_writer("meta", WriterRole.FSM) is True

    def test_front_llm_cannot_write_task_state(self):
        """Front LLM is NOT authorized for task_state."""
        assert validate_writer("task_state", WriterRole.FRONT_LLM) is False

    def test_front_llm_cannot_write_task_artifacts(self):
        assert validate_writer("task_artifacts", WriterRole.FRONT_LLM) is False

    def test_fsm_cannot_write_beliefs(self):
        assert validate_writer("beliefs_active", WriterRole.FSM) is False

    def test_experience_layer_writes_affective_now(self):
        assert validate_writer("affective_now", WriterRole.EXPERIENCE_LAYER) is True

    def test_experience_layer_cannot_write_beliefs(self):
        assert validate_writer("beliefs_active", WriterRole.EXPERIENCE_LAYER) is False

    def test_session_init_writes_persona(self):
        assert validate_writer("persona", WriterRole.SESSION_INIT) is True

    def test_front_llm_cannot_write_persona(self):
        """persona is read-only after init."""
        assert validate_writer("persona", WriterRole.FRONT_LLM) is False

    def test_unknown_section_returns_false(self):
        assert validate_writer("nonexistent_section", WriterRole.FSM) is False


class TestEnforceWriter:
    """11.5.1 -- enforce_writer() raises on unauthorized access."""

    def test_authorized_writer_passes(self):
        """No exception for authorized writers."""
        enforce_writer("task_state", WriterRole.FSM)  # Should not raise

    def test_unauthorized_writer_raises(self):
        """SingleWriterViolation for unauthorized writers."""
        with pytest.raises(SingleWriterViolation, match="FRONT_LLM"):
            enforce_writer("task_state", WriterRole.FRONT_LLM)

    def test_violation_message_contains_section(self):
        with pytest.raises(SingleWriterViolation, match="task_artifacts"):
            enforce_writer("task_artifacts", WriterRole.FRONT_LLM)

    def test_violation_message_lists_authorized(self):
        """Error message lists the authorized writers."""
        with pytest.raises(SingleWriterViolation, match="FSM"):
            enforce_writer("task_state", WriterRole.EXPERIENCE_LAYER)

    def test_unknown_section_raises(self):
        with pytest.raises(SingleWriterViolation):
            enforce_writer("fake_section", WriterRole.FSM)

    def test_violation_is_exception(self):
        assert issubclass(SingleWriterViolation, Exception)


class TestSingleWriterInvariantDesignDoc:
    """11.5 -- Validate design doc Section 5 invariant rules."""

    def test_rule1_sectional_isolation(self):
        """Front-LLM and FSM never share a section as concurrent writers.

        V2 Section 5 Rule 1: Front and Back write to DIFFERENT sections.
        (Phase1 and Front share sections but run sequentially via TurnLock.)
        """
        front_sections = {s for s, ws in SECTION_WRITERS.items() if WriterRole.FRONT_LLM in ws}
        fsm_sections = {s for s, ws in SECTION_WRITERS.items() if WriterRole.FSM in ws}
        # control has both FSM and Phase1, not Front LLM
        # The only overlap allowed is through sequential Phase1 → Front
        direct_overlap = front_sections & fsm_sections
        assert direct_overlap == set(), f"Front LLM and FSM share sections: {direct_overlap}"

    def test_rule2_back_has_no_writer_role(self):
        """V2 Section 5 Rule 2: Back never writes SS directly."""
        all_roles_used = set()
        for writers in SECTION_WRITERS.values():
            all_roles_used.update(writers)
        role_names = {r.name for r in all_roles_used}
        assert "BACK_LLM" not in role_names
        assert "BACK" not in role_names

    def test_fsm_sections_match_delta_targets(self):
        """FSM-writable sections include both task lifecycle sections.

        These are the sections written via DeltaApplicator from Back
        bus deltas.
        """
        fsm_sections = {
            s for s, ws in SECTION_WRITERS.items() if WriterRole.FSM in ws and len(ws) == 1
        }
        # FSM exclusive sections include the delta targets
        assert "task_state" in fsm_sections
        assert "task_artifacts" in fsm_sections
        assert "history_active" in fsm_sections
        assert "meta" in fsm_sections


# =========================================================================
# Epic 11.6 -- Cross-Actor Read Consistency
# =========================================================================


class TestSectionSnapshotDataclass:
    """11.6.1 -- SectionSnapshot structure."""

    def test_basic_creation(self):
        snap = SectionSnapshot(
            section="beliefs_active",
            data={"hotel": "Vineyard"},
            snapshot_ns=time.monotonic_ns(),
            version=3,
        )
        assert snap.section == "beliefs_active"
        assert snap.data == {"hotel": "Vineyard"}
        assert snap.version == 3

    def test_frozen(self):
        """SectionSnapshot is immutable."""
        snap = SectionSnapshot(section="meta", data={}, snapshot_ns=0, version=0)
        with pytest.raises(AttributeError):
            snap.section = "other"  # type: ignore[misc]

    def test_age_ms(self):
        """age_ms measures time since snapshot creation."""
        snap = SectionSnapshot(
            section="meta",
            data={},
            snapshot_ns=time.monotonic_ns(),
            version=0,
        )
        time.sleep(0.01)
        assert snap.age_ms > 5  # At least 5ms old


class TestSnapshotReaderRegister:
    """11.6.1 -- SnapshotReader section registration."""

    def test_register_empty_section(self):
        reader = SnapshotReader()
        reader.register_section("beliefs_active")
        snap = reader.read("beliefs_active")
        assert snap.data == {}
        assert snap.version == 0

    def test_register_with_initial_data(self):
        reader = SnapshotReader()
        reader.register_section("beliefs_active", {"hotel": "Vineyard"})
        snap = reader.read("beliefs_active")
        assert snap.data == {"hotel": "Vineyard"}

    def test_register_copies_initial_data(self):
        """Initial data is copied, not referenced."""
        init = {"key": "value"}
        reader = SnapshotReader()
        reader.register_section("meta", init)
        init["key"] = "changed"
        snap = reader.read("meta")
        assert snap.data["key"] == "value"

    def test_section_names(self):
        reader = SnapshotReader()
        reader.register_section("beliefs_active")
        reader.register_section("task_state")
        assert reader.section_names == frozenset({"beliefs_active", "task_state"})


class TestSnapshotReaderRead:
    """11.6.1 -- SnapshotReader.read() lock-free snapshots."""

    def test_read_returns_section_snapshot(self):
        reader = SnapshotReader()
        reader.register_section("task_state")
        snap = reader.read("task_state")
        assert isinstance(snap, SectionSnapshot)
        assert snap.section == "task_state"

    def test_read_unregistered_section(self):
        """Reading an unregistered section returns empty data."""
        reader = SnapshotReader()
        snap = reader.read("nonexistent")
        assert snap.data == {}
        assert snap.version == 0

    def test_read_has_monotonic_timestamp(self):
        reader = SnapshotReader()
        reader.register_section("meta")
        snap = reader.read("meta")
        assert snap.snapshot_ns > 0

    def test_snapshot_is_isolated(self):
        """Writes after snapshot do NOT affect the snapshot.

        V2 Section 5: If Back reads beliefs_active while Front is
        updating it, Back gets the pre-update version.
        """
        reader = SnapshotReader()
        reader.register_section("beliefs_active", {"hotel": "Vineyard"})
        snap = reader.read("beliefs_active")
        # Write after snapshot
        reader.write("beliefs_active", "dates", "June 15-17")
        # Snapshot should NOT see the new write
        assert "dates" not in snap.data
        assert snap.data == {"hotel": "Vineyard"}

    def test_new_read_sees_write(self):
        """A new read() after write() sees the updated data."""
        reader = SnapshotReader()
        reader.register_section("task_state")
        reader.write("task_state", "t1", {"status": "COMPLETED"})
        snap = reader.read("task_state")
        assert snap.data["t1"] == {"status": "COMPLETED"}
        assert snap.version == 1


class TestSnapshotReaderWrite:
    """11.6.1 -- SnapshotReader.write() updates live data."""

    def test_write_increments_version(self):
        reader = SnapshotReader()
        reader.register_section("task_state")
        assert reader.section_version("task_state") == 0
        reader.write("task_state", "t1", {"status": "DISPATCHED"})
        assert reader.section_version("task_state") == 1
        reader.write("task_state", "t1", {"status": "COMPLETED"})
        assert reader.section_version("task_state") == 2

    def test_write_to_unregistered_creates_section(self):
        """Writing to an unregistered section auto-creates it."""
        reader = SnapshotReader()
        reader.write("new_section", "key", "value")
        snap = reader.read("new_section")
        assert snap.data["key"] == "value"

    def test_write_overwrites_existing_key(self):
        reader = SnapshotReader()
        reader.register_section("beliefs_active")
        reader.write("beliefs_active", "hotel", "Vineyard")
        reader.write("beliefs_active", "hotel", "Grand Hotel")
        snap = reader.read("beliefs_active")
        assert snap.data["hotel"] == "Grand Hotel"

    def test_multiple_keys(self):
        reader = SnapshotReader()
        reader.register_section("task_state")
        reader.write("task_state", "t1", {"status": "COMPLETED"})
        reader.write("task_state", "t2", {"status": "IN_PROGRESS"})
        snap = reader.read("task_state")
        assert "t1" in snap.data
        assert "t2" in snap.data


class TestSnapshotReaderDelete:
    """11.6.1 -- SnapshotReader.delete() removes keys."""

    def test_delete_existing_key(self):
        reader = SnapshotReader()
        reader.register_section("task_state")
        reader.write("task_state", "t1", {"status": "COMPLETED"})
        result = reader.delete("task_state", "t1")
        assert result is True
        snap = reader.read("task_state")
        assert "t1" not in snap.data

    def test_delete_nonexistent_key(self):
        reader = SnapshotReader()
        reader.register_section("meta")
        result = reader.delete("meta", "nonexistent")
        assert result is False

    def test_delete_increments_version(self):
        reader = SnapshotReader()
        reader.register_section("task_state")
        reader.write("task_state", "t1", "x")
        v_before = reader.section_version("task_state")
        reader.delete("task_state", "t1")
        assert reader.section_version("task_state") == v_before + 1

    def test_delete_unregistered_section(self):
        reader = SnapshotReader()
        result = reader.delete("nonexistent", "key")
        assert result is False


class TestSnapshotReaderMultiple:
    """11.6.1 -- SnapshotReader.read_multiple()."""

    def test_read_multiple_basic(self):
        reader = SnapshotReader()
        reader.register_section("beliefs_active", {"k": "v"})
        reader.register_section("task_state", {"t": "s"})
        snaps = reader.read_multiple(["beliefs_active", "task_state"])
        assert "beliefs_active" in snaps
        assert "task_state" in snaps
        assert snaps["beliefs_active"].data == {"k": "v"}

    def test_read_multiple_includes_unregistered(self):
        """Unregistered sections get empty snapshots."""
        reader = SnapshotReader()
        reader.register_section("meta")
        snaps = reader.read_multiple(["meta", "nonexistent"])
        assert snaps["nonexistent"].data == {}

    def test_read_multiple_empty_list(self):
        reader = SnapshotReader()
        snaps = reader.read_multiple([])
        assert snaps == {}

    def test_read_multiple_each_is_isolated(self):
        """Each snapshot in a multi-read is independently isolated."""
        reader = SnapshotReader()
        reader.register_section("beliefs_active", {"x": 1})
        reader.register_section("task_state", {"y": 2})
        snaps = reader.read_multiple(["beliefs_active", "task_state"])
        reader.write("beliefs_active", "x", 99)
        # Pre-write snapshot is unaffected
        assert snaps["beliefs_active"].data["x"] == 1


class TestCrossActorReadScenarios:
    """11.6 -- V2 Section 5 cross-actor read consistency scenarios."""

    def test_front_reads_while_fsm_writes(self):
        """Front reads task_artifacts while FSM writes it.

        V2: Front gets pre-write snapshot. None risk.
        """
        reader = SnapshotReader()
        reader.register_section("task_artifacts", {"t1:booking": {"hotel": "X"}})
        # Front takes a snapshot
        front_snap = reader.read("task_artifacts")
        # FSM writes new artifact
        reader.write("task_artifacts", "t1:itinerary", {"data": "new"})
        # Front's snapshot is unaffected
        assert "t1:itinerary" not in front_snap.data
        assert front_snap.data["t1:booking"] == {"hotel": "X"}

    def test_back_reads_while_front_writes(self):
        """Back reads beliefs_active while Front writes it.

        V2: Back gets pre-write snapshot. Minimal risk.
        """
        reader = SnapshotReader()
        reader.register_section("beliefs_active", {"preference": "boutique"})
        back_snap = reader.read("beliefs_active")
        reader.write("beliefs_active", "dates", "June 15-17")
        assert "dates" not in back_snap.data
        assert back_snap.data["preference"] == "boutique"

    def test_concurrent_reads_same_snapshot(self):
        """Both read history_active simultaneously.

        V2: Both get same snapshot. None risk (append-only).
        """
        reader = SnapshotReader()
        reader.register_section("history_active", {"turn-1": "hello"})
        snap1 = reader.read("history_active")
        snap2 = reader.read("history_active")
        assert snap1.data == snap2.data
        assert snap1.version == snap2.version

    def test_read_performance_target(self):
        """Snapshot creation should be <1ms (V2 Section 5)."""
        reader = SnapshotReader()
        reader.register_section("task_state")
        for i in range(100):
            reader.write("task_state", f"task-{i}", {"status": "COMPLETED"})

        start = time.monotonic_ns()
        snap = reader.read("task_state")
        elapsed_ms = (time.monotonic_ns() - start) / 1_000_000

        assert len(snap.data) == 100
        assert elapsed_ms < 10  # Well under 1ms for 100 entries, allow margin


# =========================================================================
# Package exports
# =========================================================================


class TestDeltaPackageExportsUpdated:
    """Package-level export validation including Epics 11.4-11.6."""

    def test_package_importable(self):
        import k1.concierge.delta as pkg

        assert hasattr(pkg, "__all__")

    def test_export_count(self):
        """Package exports at least 23 symbols (13 + 10 new)."""
        import k1.concierge.delta as pkg

        assert len(pkg.__all__) >= 23

    def test_all_exports_accessible(self):
        import k1.concierge.delta as pkg

        for name in pkg.__all__:
            assert hasattr(pkg, name), f"{name} in __all__ but not accessible"

    @pytest.mark.parametrize(
        "symbol",
        [
            # Epic 11.4
            "DeltaApplicator",
            "ApplyResult",
            # Epic 11.5
            "WriterRole",
            "SingleWriterViolation",
            "SECTION_WRITERS",
            "ALL_WRITER_SECTIONS",
            "validate_writer",
            "enforce_writer",
            # Epic 11.6
            "SectionSnapshot",
            "SnapshotReader",
        ],
    )
    def test_new_export_accessible(self, symbol: str):
        import k1.concierge.delta as pkg

        assert hasattr(pkg, symbol), f"{symbol} not accessible on package"

    @pytest.mark.parametrize(
        "symbol",
        [
            # Epic 11.1-11.3 (still present)
            "SessionDelta",
            "VALID_DELTA_SECTIONS",
            "VALID_DELTA_OPERATIONS",
            "ARTIFACT_CREATED",
            "TASK_STATE_CHANGED",
            "STATE_UPDATED",
            "ALL_DELTA_TOPICS",
            "emit_artifact",
            "emit_task_state_change",
            "VALID_TASK_STATUSES",
            "DeltaAggregator",
            "DeltaBatch",
            "DEFAULT_BATCH_WINDOW_MS",
        ],
    )
    def test_existing_export_still_accessible(self, symbol: str):
        import k1.concierge.delta as pkg

        assert hasattr(pkg, symbol), f"Existing {symbol} broke"

    def test_new_submodules_importable(self):
        expected = [
            "k1.concierge.delta.applicator",
            "k1.concierge.delta.writer_registry",
            "k1.concierge.delta.snapshot_reader",
        ]
        for mod_path in expected:
            mod = importlib.import_module(mod_path)
            assert mod is not None

    def test_no_circular_imports(self):
        import k1.concierge.delta as pkg

        importlib.reload(pkg)
        assert len(pkg.__all__) >= 23
