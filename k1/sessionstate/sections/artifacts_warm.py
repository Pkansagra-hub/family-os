"""
ArtifactsWarmSection - Demoted Task Artifacts (WARM)
======================================================

MILESTONE: M02 -- Session State Extensions
EPIC: 2.2 TaskArtifacts Section (Issue 2.2.4)

Receives artifacts evicted from HOT task_artifacts section after
presentation + 10 turns. Provides read-only archival access.
Uses LRU eviction to LOCAL COLD when budget is exceeded.

Budget: 8KB (8192 bytes)
Tier: WARM
Eviction: LRU to COLD (archive oldest first)

Single Writer: HotTier demotion engine (on eviction from task_artifacts)
Readers: Front LLM (historical reference), Orchestrator (dependency lookup)
"""

from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional

import flatbuffers

from k1.sessionstate.generated.flatbuffers.K1.SessionState.ArtifactsWarmSection import (
    ArtifactsWarmSection as _FBArtifactsWarmSectionClass,
)
from k1.sessionstate.generated.flatbuffers.K1.SessionState.ArtifactsWarmSection import (
    ArtifactsWarmSectionAddArtifacts,
    ArtifactsWarmSectionAddHeader,
    ArtifactsWarmSectionAddLastUpdatedMs,
    ArtifactsWarmSectionEnd,
    ArtifactsWarmSectionStart,
    ArtifactsWarmSectionStartArtifactsVector,
)
from k1.sessionstate.generated.flatbuffers.K1.SessionState.SectionHeader import (
    SectionHeaderAddLastUpdatedMs,
    SectionHeaderAddSectionName,
    SectionHeaderAddSizeBytes,
    SectionHeaderEnd,
    SectionHeaderStart,
)
from k1.sessionstate.generated.flatbuffers.K1.SessionState.TaskArtifactEntry import (
    TaskArtifactEntryAddArtifactId,
    TaskArtifactEntryAddArtifactType,
    TaskArtifactEntryAddContent,
    TaskArtifactEntryAddCreatedAtMs,
    TaskArtifactEntryAddMetadata,
    TaskArtifactEntryAddPresentedAtTurn,
    TaskArtifactEntryAddSizeBytes,
    TaskArtifactEntryAddTaskId,
    TaskArtifactEntryEnd,
    TaskArtifactEntryStart,
)

from .task_artifacts import TaskArtifactEntry

# =============================================================================
# ArtifactsWarmSection Implementation
# =============================================================================


class ArtifactsWarmSection:
    """
    Artifacts WARM Section -- receives demoted artifacts from HOT tier.

    LRU-ordered storage with 8KB budget. Oldest artifacts evicted first
    when budget is exceeded.

    ISection protocol:
        name = "artifacts_warm"
        tier = "warm"
        budget_bytes = 8192
        can_evict = True
    """

    BUDGET_BYTES: int = 8192  # 8KB
    TIER: str = "warm"
    CAN_EVICT: bool = True
    SECTION_NAME: str = "artifacts_warm"
    MAX_ARTIFACTS: int = 50  # Safety cap

    __slots__ = ("_artifacts", "_last_updated_ms", "_cached_bytes", "_cache_valid")

    def __init__(self) -> None:
        self._artifacts: Dict[str, TaskArtifactEntry] = {}
        self._last_updated_ms: int = int(time.time() * 1000)
        self._cached_bytes: Optional[bytes] = None
        self._cache_valid: bool = False

    # =========================================================================
    # ISection Protocol
    # =========================================================================

    @property
    def name(self) -> str:
        return self.SECTION_NAME

    @property
    def tier(self) -> str:
        return self.TIER

    @property
    def budget_bytes(self) -> int:
        return self.BUDGET_BYTES

    @property
    def can_evict(self) -> bool:
        return self.CAN_EVICT

    def get_size_bytes(self) -> int:
        if self._cache_valid and self._cached_bytes is not None:
            return len(self._cached_bytes)
        return 50 + sum(a.size_bytes + 80 for a in self._artifacts.values())

    def to_flatbuffer(self) -> bytes:
        builder = flatbuffers.Builder(512)

        artifacts = list(self._artifacts.values())

        # Pre-create all offsets before any StartObject
        entry_offsets: List[int] = []
        for a in artifacts:
            artifact_id_off = builder.CreateString(a.artifact_id or "")
            task_id_off = builder.CreateString(a.task_id or "")
            content_off = builder.CreateString(a.content or "")
            metadata_off = builder.CreateString(json.dumps(a.metadata) if a.metadata else "{}")

            TaskArtifactEntryStart(builder)
            TaskArtifactEntryAddArtifactId(builder, artifact_id_off)
            TaskArtifactEntryAddTaskId(builder, task_id_off)
            TaskArtifactEntryAddArtifactType(builder, int(a.artifact_type))
            TaskArtifactEntryAddContent(builder, content_off)
            TaskArtifactEntryAddCreatedAtMs(builder, a.created_at_ms)
            TaskArtifactEntryAddPresentedAtTurn(builder, a.presented_at_turn)
            TaskArtifactEntryAddSizeBytes(builder, a.size_bytes)
            TaskArtifactEntryAddMetadata(builder, metadata_off)
            entry_offsets.append(TaskArtifactEntryEnd(builder))

        # Artifacts vector
        ArtifactsWarmSectionStartArtifactsVector(builder, len(entry_offsets))
        for off in reversed(entry_offsets):
            builder.PrependUOffsetTRelative(off)
        artifacts_vec = builder.EndVector(len(entry_offsets))

        # Header
        section_name_off = builder.CreateString(self.SECTION_NAME)
        SectionHeaderStart(builder)
        SectionHeaderAddSectionName(builder, section_name_off)
        SectionHeaderAddSizeBytes(builder, self.get_size_bytes())
        SectionHeaderAddLastUpdatedMs(builder, self._last_updated_ms)
        header_off = SectionHeaderEnd(builder)

        # Root table
        ArtifactsWarmSectionStart(builder)
        ArtifactsWarmSectionAddHeader(builder, header_off)
        ArtifactsWarmSectionAddArtifacts(builder, artifacts_vec)
        ArtifactsWarmSectionAddLastUpdatedMs(builder, self._last_updated_ms)
        root = ArtifactsWarmSectionEnd(builder)

        builder.Finish(root)
        data = bytes(builder.Output())
        self._cached_bytes = data
        self._cache_valid = True
        return data

    def from_flatbuffer(self, data: bytes) -> None:
        buf = bytearray(data)
        section = _FBArtifactsWarmSectionClass.GetRootAsArtifactsWarmSection(buf, 0)
        self._last_updated_ms = section.LastUpdatedMs() or int(time.time() * 1000)
        self._artifacts.clear()
        for i in range(section.ArtifactsLength()):
            fb_entry = section.Artifacts(i)
            if fb_entry is None:
                continue
            artifact_id = (fb_entry.ArtifactId() or b"").decode("utf-8")
            task_id = (fb_entry.TaskId() or b"").decode("utf-8")
            content = (fb_entry.Content() or b"").decode("utf-8")
            raw_meta = fb_entry.Metadata()
            metadata: Dict[str, Any] = json.loads(raw_meta.decode("utf-8")) if raw_meta else {}
            entry = TaskArtifactEntry(
                artifact_id=artifact_id,
                task_id=task_id,
                artifact_type=fb_entry.ArtifactType(),
                content=content,
                created_at_ms=fb_entry.CreatedAtMs(),
                presented_at_turn=fb_entry.PresentedAtTurn(),
                size_bytes=fb_entry.SizeBytes(),
                metadata=metadata,
            )
            self._artifacts[artifact_id] = entry
        self._cache_valid = False

    def clear(self) -> None:
        self._artifacts.clear()
        self._last_updated_ms = int(time.time() * 1000)
        self._cache_valid = False

    def get_metadata(self) -> Dict[str, Any]:
        return {
            "section": self.SECTION_NAME,
            "tier": self.TIER,
            "budget_bytes": self.BUDGET_BYTES,
            "current_size_bytes": self.get_size_bytes(),
            "artifact_count": len(self._artifacts),
            "last_updated_ms": self._last_updated_ms,
        }

    # =========================================================================
    # Write Operations (Writer: HotTier demotion engine)
    # =========================================================================

    def accept_demoted(self, artifacts: List[TaskArtifactEntry]) -> int:
        """Accept artifacts evicted from HOT task_artifacts section.

        If adding exceeds MAX_ARTIFACTS, oldest entries are evicted
        (LRU by created_at_ms).

        Args:
            artifacts: List of TaskArtifactEntry objects from HOT eviction.

        Returns:
            Number of artifacts accepted.
        """
        accepted = 0
        for a in artifacts:
            self._artifacts[a.artifact_id] = a
            accepted += 1

        # LRU eviction if over cap
        while len(self._artifacts) > self.MAX_ARTIFACTS:
            oldest_id = min(self._artifacts, key=lambda k: self._artifacts[k].created_at_ms)
            del self._artifacts[oldest_id]

        if accepted > 0:
            self._last_updated_ms = int(time.time() * 1000)
            self._cache_valid = False

        return accepted

    # =========================================================================
    # Read Operations
    # =========================================================================

    def get_all(self) -> List[TaskArtifactEntry]:
        """Return all archived artifacts."""
        return list(self._artifacts.values())

    def get_by_id(self, artifact_id: str) -> Optional[TaskArtifactEntry]:
        """Get artifact by ID."""
        return self._artifacts.get(artifact_id)

    def get_by_task(self, task_id: str) -> List[TaskArtifactEntry]:
        """Get all artifacts for a given task."""
        return [a for a in self._artifacts.values() if a.task_id == task_id]

    @property
    def artifact_count(self) -> int:
        return len(self._artifacts)

    # =========================================================================
    # Eviction (WARM -> COLD)
    # =========================================================================

    def get_eviction_candidates(self, count: int = 5) -> List[TaskArtifactEntry]:
        """Get oldest artifacts for eviction to COLD.

        Args:
            count: Number of candidates to return.

        Returns:
            Oldest artifacts by created_at_ms.
        """
        sorted_artifacts = sorted(self._artifacts.values(), key=lambda a: a.created_at_ms)
        return sorted_artifacts[:count]

    def evict_oldest(self, count: int = 5) -> List[TaskArtifactEntry]:
        """Evict oldest artifacts to make room.

        Args:
            count: Number to evict.

        Returns:
            Evicted artifacts (for COLD archival by caller).
        """
        candidates = self.get_eviction_candidates(count)
        for a in candidates:
            del self._artifacts[a.artifact_id]

        if candidates:
            self._last_updated_ms = int(time.time() * 1000)
            self._cache_valid = False

        return candidates
