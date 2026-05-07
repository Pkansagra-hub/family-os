"""
FlatBuffer Round-Trip Tests for M4/M6 Extension Sections
==========================================================

E-0.5.18 — Issue I-0.5.18.2

Tests serialize/deserialize round-trip for the 3 sections that were added
in M4/M6 without FlatBuffer schema updates:

1. TaskStateSection (HOT CORE, 4KB, NEVER EVICT) — M4
2. TaskArtifactsSection (HOT CORE, 4KB, demotes to artifacts_warm) — M6
3. ArtifactsWarmSection (WARM, 8KB, LRU to COLD) — M6

Test pattern matches existing test_flatbuffers.py conventions.

Run with: pytest tests/k1/sessionstate/test_e0518_flatbuffer_drift.py -v
"""

from k1.sessionstate.sections import (
    ArtifactsWarmSection,
    ArtifactType,
    TaskArtifactEntry,
    TaskArtifactsSection,
    TaskStateEntry,
    TaskStateSection,
    TaskStatus,
)

# =============================================================================
# BUDGET CONSTANTS
# =============================================================================

SECTION_BUDGETS = {
    "task_state": 4096,
    "task_artifacts": 4096,
    "artifacts_warm": 8192,
}


# =============================================================================
# TaskStateSection FLATBUFFER ROUND-TRIP
# =============================================================================


class TestTaskStateSectionFlatBuffer:
    """FlatBuffer round-trip for TaskStateSection (HOT CORE, NEVER EVICT)."""

    def test_empty_roundtrip(self):
        """Empty section serializes and deserializes correctly."""
        section = TaskStateSection()

        data = section.to_flatbuffer()
        assert isinstance(data, bytes)
        assert len(data) > 0
        assert len(data) <= SECTION_BUDGETS["task_state"]

        restored = TaskStateSection()
        restored.from_flatbuffer(data)

        assert restored.name == section.name
        assert restored.tier == section.tier
        assert restored.task_count == 0

    def test_single_task_roundtrip(self):
        """Single task entry round-trips with all fields preserved."""
        section = TaskStateSection()
        entry = section.add_task("order_food", task_id="task-001")
        section.update_status("task-001", TaskStatus.DISPATCHED)
        section.set_progress("task-001", 50)

        data = section.to_flatbuffer()
        assert len(data) <= SECTION_BUDGETS["task_state"]

        restored = TaskStateSection()
        restored.from_flatbuffer(data)

        assert restored.task_count == 1
        t = restored.get_by_id("task-001")
        assert t is not None
        assert t.action == "order_food"
        assert t.status == TaskStatus.DISPATCHED
        assert t.progress_pct == 50
        assert t.dispatched_at_ms > 0

    def test_multiple_tasks_roundtrip(self):
        """Multiple tasks with different statuses round-trip correctly."""
        section = TaskStateSection()
        section.add_task("order_food", task_id="t1")
        section.add_task("book_ride", task_id="t2")
        section.add_task("check_weather", task_id="t3")

        section.update_status("t1", TaskStatus.DISPATCHED)
        section.update_status("t1", TaskStatus.ACTIVE)
        section.update_status("t2", TaskStatus.DISPATCHED)
        section.update_status("t2", TaskStatus.SUSPENDED)
        section.update_status("t3", TaskStatus.DISPATCHED)
        section.update_status("t3", TaskStatus.ACTIVE)
        section.update_status("t3", TaskStatus.COMPLETED)

        data = section.to_flatbuffer()
        assert len(data) <= SECTION_BUDGETS["task_state"]

        restored = TaskStateSection()
        restored.from_flatbuffer(data)

        assert restored.task_count == 3
        assert restored.get_by_id("t1").status == TaskStatus.ACTIVE
        assert restored.get_by_id("t2").status == TaskStatus.SUSPENDED
        assert restored.get_by_id("t2").pending_hil is True
        assert restored.get_by_id("t3").status == TaskStatus.COMPLETED
        assert restored.get_by_id("t3").completed_at_ms > 0

    def test_depends_on_roundtrip(self):
        """Task dependency list survives round-trip."""
        section = TaskStateSection()
        section.add_task("step_a", task_id="a")
        section.add_task("step_b", task_id="b", depends_on=["a"])

        data = section.to_flatbuffer()
        restored = TaskStateSection()
        restored.from_flatbuffer(data)

        b = restored.get_by_id("b")
        assert b is not None
        assert b.depends_on == ["a"]

    def test_hil_data_roundtrip(self):
        """pending_hil_data dict survives round-trip."""
        section = TaskStateSection()
        section.add_task("confirm_order", task_id="h1")
        section.update_status("h1", TaskStatus.DISPATCHED)
        section.update_status("h1", TaskStatus.SUSPENDED)
        hil_payload = {"question": "Confirm order?", "options": ["yes", "no"]}
        section.set_pending_hil_data("h1", hil_payload)

        data = section.to_flatbuffer()
        restored = TaskStateSection()
        restored.from_flatbuffer(data)

        h = restored.get_by_id("h1")
        assert h is not None
        assert h.pending_hil is True
        assert h.pending_hil_data == hil_payload
        assert h.hil_suspensions_count == 1

    def test_size_within_budget_max_tasks(self):
        """8 tasks stays within 4KB budget (POC JSON serialisation is larger than real FlatBuffer)."""
        section = TaskStateSection()
        for i in range(8):
            section.add_task(f"act_{i}", task_id=f"t{i}")

        data = section.to_flatbuffer()
        assert (
            len(data) <= SECTION_BUDGETS["task_state"]
        ), f"TaskStateSection exceeds budget: {len(data)} > {SECTION_BUDGETS['task_state']}"

    def test_never_evict_property(self):
        """TaskStateSection has can_evict=False."""
        section = TaskStateSection()
        assert section.can_evict is False
        assert section.tier == "hot"

    def test_section_metadata(self):
        """get_metadata() returns correct structure."""
        section = TaskStateSection()
        section.add_task("test_action", task_id="m1")

        meta = section.get_metadata()
        assert meta["section"] == "task_state"
        assert meta["tier"] == "hot"
        assert meta["budget_bytes"] == 4096
        assert meta["task_count"] == 1


# =============================================================================
# TaskArtifactsSection FLATBUFFER ROUND-TRIP
# =============================================================================


class TestTaskArtifactsSectionFlatBuffer:
    """FlatBuffer round-trip for TaskArtifactsSection (HOT CORE, evicts to warm)."""

    def test_empty_roundtrip(self):
        """Empty section serializes and deserializes correctly."""
        section = TaskArtifactsSection()

        data = section.to_flatbuffer()
        assert isinstance(data, bytes)
        assert len(data) > 0
        assert len(data) <= SECTION_BUDGETS["task_artifacts"]

        restored = TaskArtifactsSection()
        restored.from_flatbuffer(data)

        assert restored.name == section.name
        assert restored.tier == section.tier

    def test_single_artifact_roundtrip(self):
        """Single artifact round-trips with all fields preserved."""
        section = TaskArtifactsSection()
        entry = section.add_artifact(
            task_id="task-001",
            content="Order #12345 confirmed",
            artifact_type=ArtifactType.CONFIRMATION,
            artifact_id="art-001",
            metadata={"order_total": "$42.50"},
        )

        data = section.to_flatbuffer()
        assert len(data) <= SECTION_BUDGETS["task_artifacts"]

        restored = TaskArtifactsSection()
        restored.from_flatbuffer(data)

        arts = restored.get_all()
        assert len(arts) == 1
        a = arts[0]
        assert a.task_id == "task-001"
        assert a.content == "Order #12345 confirmed"
        assert a.artifact_type == ArtifactType.CONFIRMATION
        assert a.created_at_ms > 0

    def test_multiple_artifact_types_roundtrip(self):
        """Artifacts of different types round-trip correctly."""
        section = TaskArtifactsSection()
        section.add_artifact("t1", "Plain text result", ArtifactType.TEXT, "a1")
        section.add_artifact("t1", "Receipt #789", ArtifactType.RECEIPT, "a2")
        section.add_artifact("t2", "Search results...", ArtifactType.LIST, "a3")
        section.add_artifact("t2", "Task failed: timeout", ArtifactType.ERROR, "a4")
        section.add_artifact(
            "t3", "https://img.example.com/photo.jpg", ArtifactType.MEDIA_REF, "a5"
        )

        data = section.to_flatbuffer()
        assert len(data) <= SECTION_BUDGETS["task_artifacts"]

        restored = TaskArtifactsSection()
        restored.from_flatbuffer(data)

        restored_arts = restored.get_all()
        assert len(restored_arts) == 5

        # Verify types preserved
        type_map = {a.artifact_id: a.artifact_type for a in restored_arts}
        assert type_map.get("a1") == ArtifactType.TEXT
        assert type_map.get("a2") == ArtifactType.RECEIPT
        assert type_map.get("a3") == ArtifactType.LIST
        assert type_map.get("a4") == ArtifactType.ERROR
        assert type_map.get("a5") == ArtifactType.MEDIA_REF

    def test_metadata_dict_roundtrip(self):
        """Artifact metadata dict survives round-trip."""
        section = TaskArtifactsSection()
        section.add_artifact(
            "t1",
            "Summary of findings",
            ArtifactType.SUMMARY,
            "a1",
            metadata={"word_count": 150, "language": "en"},
        )

        data = section.to_flatbuffer()
        restored = TaskArtifactsSection()
        restored.from_flatbuffer(data)

        a = restored.get_all()[0]
        assert a.metadata == {"word_count": 150, "language": "en"}

    def test_size_within_budget_max_artifacts(self):
        """Realistic artifact load stays within 4KB budget."""
        section = TaskArtifactsSection()
        for i in range(15):
            section.add_artifact(f"t-{i}", f"Content {i}", ArtifactType.TEXT, f"a-{i}")

        data = section.to_flatbuffer()
        assert (
            len(data) <= SECTION_BUDGETS["task_artifacts"]
        ), f"TaskArtifactsSection exceeds budget: {len(data)} > {SECTION_BUDGETS['task_artifacts']}"

    def test_can_evict_property(self):
        """TaskArtifactsSection has can_evict=True (demotes to warm)."""
        section = TaskArtifactsSection()
        assert section.can_evict is True
        assert section.tier == "hot"

    def test_section_metadata(self):
        """get_metadata() returns correct structure."""
        section = TaskArtifactsSection()
        section.add_artifact("t1", "test", ArtifactType.TEXT, "a1")

        meta = section.get_metadata()
        assert meta["section"] == "task_artifacts"
        assert meta["tier"] == "hot"
        assert meta["budget_bytes"] == 4096
        assert meta["artifact_count"] == 1


# =============================================================================
# ArtifactsWarmSection FLATBUFFER ROUND-TRIP
# =============================================================================


class TestArtifactsWarmSectionFlatBuffer:
    """FlatBuffer round-trip for ArtifactsWarmSection (WARM, LRU eviction)."""

    def test_empty_roundtrip(self):
        """Empty section serializes and deserializes correctly."""
        section = ArtifactsWarmSection()

        data = section.to_flatbuffer()
        assert isinstance(data, bytes)
        assert len(data) > 0
        assert len(data) <= SECTION_BUDGETS["artifacts_warm"]

        restored = ArtifactsWarmSection()
        restored.from_flatbuffer(data)

        assert restored.name == section.name
        assert restored.tier == section.tier

    def test_accept_demoted_roundtrip(self):
        """Demoted artifacts from HOT tier round-trip correctly."""
        section = ArtifactsWarmSection()
        demoted = [
            TaskArtifactEntry(
                artifact_id="d1",
                task_id="t1",
                artifact_type=ArtifactType.CONFIRMATION,
                content="Booking #ABC",
                created_at_ms=1706745600000,
                presented_at_turn=5,
                size_bytes=12,
            ),
            TaskArtifactEntry(
                artifact_id="d2",
                task_id="t2",
                artifact_type=ArtifactType.RECEIPT,
                content="Receipt: $99.00",
                created_at_ms=1706745700000,
                presented_at_turn=8,
                size_bytes=15,
            ),
        ]
        section.accept_demoted(demoted)

        data = section.to_flatbuffer()
        assert len(data) <= SECTION_BUDGETS["artifacts_warm"]

        restored = ArtifactsWarmSection()
        restored.from_flatbuffer(data)

        assert restored.artifact_count == 2
        d1 = restored.get_by_id("d1")
        assert d1 is not None
        assert d1.content == "Booking #ABC"
        assert d1.artifact_type == ArtifactType.CONFIRMATION
        assert d1.presented_at_turn == 5

    def test_get_by_task_after_roundtrip(self):
        """get_by_task() works after round-trip."""
        section = ArtifactsWarmSection()
        artifacts = [
            TaskArtifactEntry(
                artifact_id=f"a{i}",
                task_id="shared-task",
                content=f"Artifact {i}",
                created_at_ms=1706745600000 + i * 1000,
                size_bytes=10,
            )
            for i in range(3)
        ]
        section.accept_demoted(artifacts)

        data = section.to_flatbuffer()
        restored = ArtifactsWarmSection()
        restored.from_flatbuffer(data)

        task_arts = restored.get_by_task("shared-task")
        assert len(task_arts) == 3

    def test_size_within_budget_max_artifacts(self):
        """Realistic archived artifact load stays within 8KB budget."""
        section = ArtifactsWarmSection()
        artifacts = [
            TaskArtifactEntry(
                artifact_id=f"a-{i}",
                task_id=f"t-{i}",
                content=f"C{i}",
                created_at_ms=1706745600000 + i,
                size_bytes=5,
            )
            for i in range(40)
        ]
        section.accept_demoted(artifacts)

        data = section.to_flatbuffer()
        assert (
            len(data) <= SECTION_BUDGETS["artifacts_warm"]
        ), f"ArtifactsWarmSection exceeds budget: {len(data)} > {SECTION_BUDGETS['artifacts_warm']}"

    def test_warm_tier_properties(self):
        """ArtifactsWarmSection is WARM tier with can_evict=True."""
        section = ArtifactsWarmSection()
        assert section.can_evict is True
        assert section.tier == "warm"
        assert section.budget_bytes == 8192

    def test_eviction_candidates(self):
        """get_eviction_candidates() returns oldest first."""
        section = ArtifactsWarmSection()
        artifacts = [
            TaskArtifactEntry(
                artifact_id=f"e{i}",
                task_id="t1",
                content=f"C{i}",
                created_at_ms=1706745600000 + i * 1000,
                size_bytes=5,
            )
            for i in range(10)
        ]
        section.accept_demoted(artifacts)

        candidates = section.get_eviction_candidates(3)
        assert len(candidates) == 3
        assert candidates[0].artifact_id == "e0"
        assert candidates[1].artifact_id == "e1"
        assert candidates[2].artifact_id == "e2"


# =============================================================================
# HOT→WARM DEMOTION ROUND-TRIP (END-TO-END)
# =============================================================================


class TestHotToWarmDemotionRoundTrip:
    """End-to-end: artifacts created in HOT, demoted to WARM, both round-trip."""

    def test_hot_to_warm_pipeline(self):
        """Full pipeline: create in HOT → demote → serialize both → restore both."""
        # Step 1: Create artifacts in HOT
        hot = TaskArtifactsSection()
        hot.add_artifact("t1", "Booking confirmed", ArtifactType.CONFIRMATION, "a1")
        hot.add_artifact("t2", "Summary of trip", ArtifactType.SUMMARY, "a2")

        # Serialize HOT
        hot_data = hot.to_flatbuffer()
        assert len(hot_data) <= SECTION_BUDGETS["task_artifacts"]

        # Step 2: Simulate demotion — get artifacts, move to WARM
        warm = ArtifactsWarmSection()
        warm.accept_demoted(hot.get_all())

        # Serialize WARM
        warm_data = warm.to_flatbuffer()
        assert len(warm_data) <= SECTION_BUDGETS["artifacts_warm"]

        # Step 3: Restore both from serialized
        hot_restored = TaskArtifactsSection()
        hot_restored.from_flatbuffer(hot_data)
        assert len(hot_restored.get_all()) == 2

        warm_restored = ArtifactsWarmSection()
        warm_restored.from_flatbuffer(warm_data)
        assert warm_restored.artifact_count == 2

        # Verify WARM has the same content
        w_a1 = warm_restored.get_by_id("a1")
        assert w_a1 is not None
        assert w_a1.content == "Booking confirmed"
        assert w_a1.artifact_type == ArtifactType.CONFIRMATION

    def test_task_state_independent_of_artifacts(self):
        """TaskState and TaskArtifacts serialize independently."""
        state = TaskStateSection()
        state.add_task("order_food", task_id="t1")
        state.update_status("t1", TaskStatus.DISPATCHED)
        state.update_status("t1", TaskStatus.ACTIVE)
        state.update_status("t1", TaskStatus.COMPLETED)

        artifacts = TaskArtifactsSection()
        artifacts.add_artifact("t1", "Order confirmed", ArtifactType.CONFIRMATION, "a1")

        # Serialize independently
        state_data = state.to_flatbuffer()
        art_data = artifacts.to_flatbuffer()

        # Restore independently
        state_restored = TaskStateSection()
        state_restored.from_flatbuffer(state_data)
        assert state_restored.get_by_id("t1").status == TaskStatus.COMPLETED

        art_restored = TaskArtifactsSection()
        art_restored.from_flatbuffer(art_data)
        assert art_restored.get_all()[0].task_id == "t1"


# =============================================================================
# SCHEMA DRIFT VERIFICATION
# =============================================================================


class TestSchemaDriftVerification:
    """Verify FBS schemas match Python field structure."""

    def test_task_state_entry_field_count(self):
        """TaskStateEntry has 11 fields matching .fbs schema."""
        import dataclasses

        fields = [f.name for f in dataclasses.fields(TaskStateEntry)]
        expected = {
            "task_id",
            "action",
            "status",
            "dispatched_at_ms",
            "completed_at_ms",
            "depends_on",
            "progress_pct",
            "pending_hil",
            "hil_suspensions_count",
            "presented_at_turn",
            "pending_hil_data",
        }
        assert set(fields) == expected

    def test_task_artifact_entry_field_count(self):
        """TaskArtifactEntry has 8 fields matching .fbs schema."""
        import dataclasses

        fields = [f.name for f in dataclasses.fields(TaskArtifactEntry)]
        expected = {
            "artifact_id",
            "task_id",
            "artifact_type",
            "content",
            "created_at_ms",
            "presented_at_turn",
            "size_bytes",
            "metadata",
        }
        assert set(fields) == expected

    def test_artifact_type_values_match_fbs(self):
        """ArtifactType enum values match .fbs ArtifactType enum."""
        assert ArtifactType.TEXT == 0
        assert ArtifactType.CONFIRMATION == 1
        assert ArtifactType.RECEIPT == 2
        assert ArtifactType.SUMMARY == 3
        assert ArtifactType.LIST == 4
        assert ArtifactType.ERROR == 5
        assert ArtifactType.MEDIA_REF == 6
        assert len(ArtifactType) == 7

    def test_all_three_sections_in_registry(self):
        """All 3 new sections are importable from sections package."""
        from k1.sessionstate.sections import (
            ArtifactsWarmSection,
            TaskArtifactsSection,
            TaskStateSection,
        )

        assert TaskStateSection.SECTION_NAME == "task_state"
        assert TaskArtifactsSection.SECTION_NAME == "task_artifacts"
        assert ArtifactsWarmSection.SECTION_NAME == "artifacts_warm"

    def test_fbs_files_exist(self):
        """All 3 .fbs schema files exist."""
        from pathlib import Path

        fbs_dir = (
            Path(__file__).resolve().parents[3]
            / "k1"
            / "contracts"
            / "flatbuffers"
            / "sessionstate"
        )
        assert (fbs_dir / "task_state_section.fbs").exists()
        assert (fbs_dir / "task_artifacts_section.fbs").exists()
        assert (fbs_dir / "artifacts_warm_section.fbs").exists()
