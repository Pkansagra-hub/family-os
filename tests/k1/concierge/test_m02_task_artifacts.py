"""
M02 Tests: TaskArtifacts + ArtifactsWarm Sections (Epic 2.2)
==============================================================

Tests for TaskArtifactsSection (HOT), ArtifactsWarmSection (WARM),
and the HOT->WARM eviction flow.
"""

import pytest

from k1.sessionstate.sections.artifacts_warm import ArtifactsWarmSection
from k1.sessionstate.sections.task_artifacts import (
    ArtifactType,
    TaskArtifactEntry,
    TaskArtifactsSection,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def section() -> TaskArtifactsSection:
    return TaskArtifactsSection()


@pytest.fixture
def warm() -> ArtifactsWarmSection:
    return ArtifactsWarmSection()


@pytest.fixture
def section_with_artifacts(section: TaskArtifactsSection) -> TaskArtifactsSection:
    section.add_artifact(
        "t1", "Booking confirmed: ABC-123", ArtifactType.CONFIRMATION, artifact_id="a1"
    )
    section.add_artifact("t2", "Found 3 restaurants nearby", ArtifactType.TEXT, artifact_id="a2")
    section.add_artifact("t1", "Receipt: $45.00", ArtifactType.RECEIPT, artifact_id="a3")
    return section


# =============================================================================
# Epic 2.2.1: ArtifactType and TaskArtifactEntry
# =============================================================================


class TestArtifactType:
    def test_all_types(self):
        assert ArtifactType.TEXT == 0
        assert ArtifactType.CONFIRMATION == 1
        assert ArtifactType.RECEIPT == 2
        assert ArtifactType.SUMMARY == 3
        assert ArtifactType.LIST == 4
        assert ArtifactType.ERROR == 5
        assert ArtifactType.MEDIA_REF == 6


class TestTaskArtifactEntry:
    def test_default_values(self):
        entry = TaskArtifactEntry()
        assert entry.artifact_id == ""
        assert entry.task_id == ""
        assert entry.artifact_type == 0
        assert entry.content == ""
        assert entry.presented_at_turn == 0
        assert entry.size_bytes == 0
        assert entry.metadata == {}


# =============================================================================
# Epic 2.2.2: ISection Protocol
# =============================================================================


class TestISection:
    def test_name(self, section):
        assert section.name == "task_artifacts"

    def test_tier(self, section):
        assert section.tier == "hot"

    def test_budget_bytes(self, section):
        assert section.budget_bytes == 4096

    def test_can_evict(self, section):
        assert section.can_evict is True

    def test_clear(self, section_with_artifacts):
        section_with_artifacts.clear()
        assert section_with_artifacts.artifact_count == 0

    def test_get_metadata(self, section):
        meta = section.get_metadata()
        assert meta["section"] == "task_artifacts"
        assert "artifact_count" in meta


# =============================================================================
# Epic 2.2.2: Write Operations
# =============================================================================


class TestWriteOps:
    def test_add_artifact_default(self, section):
        entry = section.add_artifact("t1", "Hello result")
        assert entry.artifact_id != ""
        assert entry.task_id == "t1"
        assert entry.artifact_type == ArtifactType.TEXT
        assert entry.content == "Hello result"
        assert entry.size_bytes == len("Hello result".encode("utf-8"))

    def test_add_artifact_with_type(self, section):
        entry = section.add_artifact("t1", "CODE-123", ArtifactType.CONFIRMATION)
        assert entry.artifact_type == ArtifactType.CONFIRMATION

    def test_add_artifact_with_metadata(self, section):
        entry = section.add_artifact("t1", "data", metadata={"source": "api"})
        assert entry.metadata == {"source": "api"}

    def test_add_artifact_max_reached(self, section):
        for i in range(30):
            section.add_artifact(f"t{i}", f"content_{i}")
        with pytest.raises(ValueError, match="Max artifacts"):
            section.add_artifact("overflow", "content")

    def test_mark_presented(self, section_with_artifacts):
        section_with_artifacts.mark_presented("a1", 5)
        assert section_with_artifacts.get_by_id("a1").presented_at_turn == 5

    def test_mark_presented_not_found(self, section):
        with pytest.raises(KeyError):
            section.mark_presented("nonexistent", 5)


# =============================================================================
# Epic 2.2.3: Read Operations
# =============================================================================


class TestReadOps:
    def test_get_all(self, section_with_artifacts):
        assert len(section_with_artifacts.get_all()) == 3

    def test_get_by_id(self, section_with_artifacts):
        a = section_with_artifacts.get_by_id("a1")
        assert a is not None
        assert "ABC-123" in a.content

    def test_get_by_task(self, section_with_artifacts):
        artifacts = section_with_artifacts.get_by_task("t1")
        assert len(artifacts) == 2  # a1 and a3

    def test_get_unpresented(self, section_with_artifacts):
        section_with_artifacts.mark_presented("a1", 5)
        unpresented = section_with_artifacts.get_unpresented()
        assert len(unpresented) == 2  # a2, a3

    def test_artifact_count(self, section_with_artifacts):
        assert section_with_artifacts.artifact_count == 3


# =============================================================================
# Epic 2.2.3: Prompt Generation
# =============================================================================


class TestPrompts:
    def test_to_prompt_empty(self, section):
        prompt = section.to_prompt()
        assert "[ARTIFACTS]" in prompt
        assert "No artifacts" in prompt

    def test_to_prompt_with_artifacts(self, section_with_artifacts):
        prompt = section_with_artifacts.to_prompt()
        assert "[ARTIFACTS]" in prompt
        assert "CONFIRMATION" in prompt
        assert "ABC-123" in prompt

    def test_to_slim_prompt_empty(self, section):
        assert section.to_slim_prompt() == ""

    def test_to_slim_prompt(self, section_with_artifacts):
        slim = section_with_artifacts.to_slim_prompt()
        assert slim.startswith("artifacts=")
        assert "CONFIRMATION" in slim


# =============================================================================
# Epic 2.2: Serialization
# =============================================================================


class TestSerialization:
    def test_roundtrip(self, section_with_artifacts):
        data = section_with_artifacts.to_flatbuffer()
        assert isinstance(data, bytes)

        new_section = TaskArtifactsSection()
        new_section.from_flatbuffer(data)
        assert new_section.artifact_count == 3
        assert new_section.get_by_id("a1").content == "Booking confirmed: ABC-123"
        assert new_section.get_by_id("a1").artifact_type == ArtifactType.CONFIRMATION


# =============================================================================
# Epic 2.6: Eviction Lifecycle (HOT -> WARM)
# =============================================================================


class TestEviction:
    def test_no_eviction_unpresented(self, section_with_artifacts):
        candidates = section_with_artifacts.get_eviction_candidates(current_turn=100)
        assert candidates == []

    def test_no_eviction_recent(self, section_with_artifacts):
        section_with_artifacts.mark_presented("a1", 5)
        candidates = section_with_artifacts.get_eviction_candidates(current_turn=10)
        assert candidates == []

    def test_eviction_after_10_turns(self, section_with_artifacts):
        section_with_artifacts.mark_presented("a1", 5)
        section_with_artifacts.mark_presented("a2", 5)
        candidates = section_with_artifacts.get_eviction_candidates(current_turn=15)
        assert len(candidates) == 2

    def test_evict_to_warm(self, section_with_artifacts):
        section_with_artifacts.mark_presented("a1", 5)
        evicted = section_with_artifacts.evict_to_warm(current_turn=15)
        assert len(evicted) == 1
        assert evicted[0].artifact_id == "a1"
        assert section_with_artifacts.artifact_count == 2

    def test_evict_to_warm_and_accept(self, section_with_artifacts, warm):
        section_with_artifacts.mark_presented("a1", 1)
        section_with_artifacts.mark_presented("a2", 1)

        evicted = section_with_artifacts.evict_to_warm(current_turn=11)
        assert len(evicted) == 2

        accepted = warm.accept_demoted(evicted)
        assert accepted == 2
        assert warm.artifact_count == 2
        assert warm.get_by_id("a1") is not None
        assert warm.get_by_id("a2") is not None


# =============================================================================
# ArtifactsWarmSection Tests
# =============================================================================


class TestArtifactsWarm:
    def test_isection_protocol(self, warm):
        assert warm.name == "artifacts_warm"
        assert warm.tier == "warm"
        assert warm.budget_bytes == 8192
        assert warm.can_evict is True

    def test_accept_demoted(self, warm):
        entries = [
            TaskArtifactEntry(
                artifact_id="a1", task_id="t1", content="data1", size_bytes=10, created_at_ms=100
            ),
            TaskArtifactEntry(
                artifact_id="a2", task_id="t2", content="data2", size_bytes=20, created_at_ms=200
            ),
        ]
        accepted = warm.accept_demoted(entries)
        assert accepted == 2
        assert warm.artifact_count == 2

    def test_lru_eviction_on_overflow(self, warm):
        # Fill to max
        entries = [
            TaskArtifactEntry(
                artifact_id=f"a{i}",
                task_id="t1",
                content=f"d{i}",
                size_bytes=10,
                created_at_ms=i * 100,
            )
            for i in range(50)
        ]
        warm.accept_demoted(entries)
        assert warm.artifact_count == 50

        # Add one more should evict oldest
        overflow = [
            TaskArtifactEntry(
                artifact_id="overflow",
                task_id="t1",
                content="new",
                size_bytes=10,
                created_at_ms=999999,
            )
        ]
        warm.accept_demoted(overflow)
        assert warm.artifact_count == 50
        assert warm.get_by_id("a0") is None  # oldest evicted
        assert warm.get_by_id("overflow") is not None

    def test_get_by_task(self, warm):
        entries = [
            TaskArtifactEntry(
                artifact_id="a1", task_id="t1", content="d1", size_bytes=10, created_at_ms=100
            ),
            TaskArtifactEntry(
                artifact_id="a2", task_id="t2", content="d2", size_bytes=10, created_at_ms=200
            ),
            TaskArtifactEntry(
                artifact_id="a3", task_id="t1", content="d3", size_bytes=10, created_at_ms=300
            ),
        ]
        warm.accept_demoted(entries)
        assert len(warm.get_by_task("t1")) == 2

    def test_evict_oldest(self, warm):
        entries = [
            TaskArtifactEntry(
                artifact_id=f"a{i}",
                task_id="t1",
                content=f"d{i}",
                size_bytes=10,
                created_at_ms=i * 100,
            )
            for i in range(10)
        ]
        warm.accept_demoted(entries)
        evicted = warm.evict_oldest(3)
        assert len(evicted) == 3
        assert evicted[0].artifact_id == "a0"
        assert warm.artifact_count == 7

    def test_serialization_roundtrip(self, warm):
        entries = [
            TaskArtifactEntry(
                artifact_id="a1",
                task_id="t1",
                content="data1",
                artifact_type=1,
                size_bytes=10,
                created_at_ms=100,
            ),
        ]
        warm.accept_demoted(entries)
        data = warm.to_flatbuffer()

        new_warm = ArtifactsWarmSection()
        new_warm.from_flatbuffer(data)
        assert new_warm.artifact_count == 1
        assert new_warm.get_by_id("a1").content == "data1"

    def test_clear(self, warm):
        entries = [
            TaskArtifactEntry(
                artifact_id="a1", task_id="t1", content="d", size_bytes=5, created_at_ms=100
            )
        ]
        warm.accept_demoted(entries)
        warm.clear()
        assert warm.artifact_count == 0
