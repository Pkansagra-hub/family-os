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
from dataclasses import asdict
from typing import Any, Dict, List, Optional

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
        """Serialize to JSON bytes (POC)."""
        payload = {
            "section": self.SECTION_NAME,
            "last_updated_ms": self._last_updated_ms,
            "artifacts": [asdict(a) for a in self._artifacts.values()],
        }
        data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self._cached_bytes = data
        self._cache_valid = True
        return data

    def from_flatbuffer(self, data: bytes) -> None:
        """Deserialize from JSON bytes."""
        payload = json.loads(data)
        self._last_updated_ms = payload.get("last_updated_ms", int(time.time() * 1000))
        self._artifacts.clear()
        for a in payload.get("artifacts", []):
            entry = TaskArtifactEntry(
                artifact_id=a["artifact_id"],
                task_id=a["task_id"],
                artifact_type=a.get("artifact_type", 0),
                content=a.get("content", ""),
                created_at_ms=a.get("created_at_ms", 0),
                presented_at_turn=a.get("presented_at_turn", 0),
                size_bytes=a.get("size_bytes", 0),
                metadata=a.get("metadata", {}),
            )
            self._artifacts[entry.artifact_id] = entry
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
