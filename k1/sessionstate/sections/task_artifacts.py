"""
TaskArtifactsSection - Task Output Artifacts (HOT CORE)
=========================================================

MILESTONE: M02 -- Session State Extensions
EPIC: 2.2 TaskArtifacts Section

Stores output artifacts produced by task execution (confirmation codes,
receipts, summaries, generated content). Artifacts are evicted HOT -> WARM
(artifacts_warm) after 10 turns post-presentation. Unpresented artifacts
are NEVER evicted.

Budget: 4KB (4096 bytes)
Tier: HOT CORE
Eviction: Demotes to artifacts_warm (WARM) after presentation + 10 turns

Single Writer: Back LLM (produces artifacts on task completion)
Readers: Front LLM (display to user), Orchestrator (dependency resolution)
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import IntEnum
from typing import Any, Dict, List, Optional

# =============================================================================
# ArtifactType Enum
# =============================================================================


class ArtifactType(IntEnum):
    """Types of task output artifacts."""

    TEXT = 0  # Plain text result
    CONFIRMATION = 1  # Booking/order confirmation code
    RECEIPT = 2  # Transaction receipt
    SUMMARY = 3  # Summarized result
    LIST = 4  # Structured list (e.g. search results)
    ERROR = 5  # Error detail from failed task
    MEDIA_REF = 6  # Reference/URL to media content


# =============================================================================
# TaskArtifactEntry Dataclass
# =============================================================================


@dataclass
class TaskArtifactEntry:
    """
    Single artifact produced by a task.

    Fields per V2 design Section 5:
        artifact_id: UUID
        task_id: UUID of the producing task
        artifact_type: ArtifactType enum value
        content: artifact payload (text, code, URL, etc.)
        created_at_ms: epoch ms when produced
        presented_at_turn: turn when shown to user (0 = not yet)
        size_bytes: byte size of content (computed on creation)
        metadata: optional key-value pairs
    """

    artifact_id: str = ""
    task_id: str = ""
    artifact_type: int = 0  # ArtifactType value
    content: str = ""
    created_at_ms: int = 0
    presented_at_turn: int = 0
    size_bytes: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


# Eviction threshold: evict after N turns post-presentation
_EVICT_AFTER_TURNS: int = 10


# =============================================================================
# TaskArtifactsSection Implementation
# =============================================================================


class TaskArtifactsSection:
    """
    Task Artifacts Section -- HOT CORE, 4KB budget.

    Stores recent task output artifacts. Evicts to artifacts_warm (WARM tier)
    after results have been presented for 10+ turns.

    ISection protocol:
        name = "task_artifacts"
        tier = "hot"
        budget_bytes = 4096
        can_evict = True (demotes to artifacts_warm)
    """

    BUDGET_BYTES: int = 4096  # 4KB
    TIER: str = "hot"
    CAN_EVICT: bool = True
    SECTION_NAME: str = "task_artifacts"
    MAX_ARTIFACTS: int = 30  # Safety cap

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
    # Write Operations (Single Writer: Back LLM)
    # =========================================================================

    def add_artifact(
        self,
        task_id: str,
        content: str,
        artifact_type: ArtifactType = ArtifactType.TEXT,
        artifact_id: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> TaskArtifactEntry:
        """Add a new artifact from task output.

        Args:
            task_id: UUID of the producing task.
            content: Artifact payload.
            artifact_type: ArtifactType enum value.
            artifact_id: UUID. Auto-generated if empty.
            metadata: Optional key-value pairs.

        Returns:
            The created TaskArtifactEntry.

        Raises:
            ValueError: If MAX_ARTIFACTS reached.
        """
        if len(self._artifacts) >= self.MAX_ARTIFACTS:
            raise ValueError(f"Max artifacts ({self.MAX_ARTIFACTS}) reached")

        aid = artifact_id or str(uuid.uuid4())
        now_ms = int(time.time() * 1000)
        content_bytes = len(content.encode("utf-8"))

        entry = TaskArtifactEntry(
            artifact_id=aid,
            task_id=task_id,
            artifact_type=int(artifact_type),
            content=content,
            created_at_ms=now_ms,
            size_bytes=content_bytes,
            metadata=metadata or {},
        )
        self._artifacts[aid] = entry
        self._last_updated_ms = now_ms
        self._cache_valid = False
        return entry

    def mark_presented(self, artifact_id: str, turn_number: int) -> None:
        """Mark an artifact as presented to the user.

        Args:
            artifact_id: Artifact UUID.
            turn_number: Turn number when shown.

        Raises:
            KeyError: If artifact_id not found.
        """
        if artifact_id not in self._artifacts:
            raise KeyError(f"Artifact not found: {artifact_id}")
        self._artifacts[artifact_id].presented_at_turn = turn_number
        self._last_updated_ms = int(time.time() * 1000)
        self._cache_valid = False

    # =========================================================================
    # Read Operations
    # =========================================================================

    def get_all(self) -> List[TaskArtifactEntry]:
        """Return all artifacts."""
        return list(self._artifacts.values())

    def get_by_id(self, artifact_id: str) -> Optional[TaskArtifactEntry]:
        """Get single artifact by ID."""
        return self._artifacts.get(artifact_id)

    def get_by_task(self, task_id: str) -> List[TaskArtifactEntry]:
        """Get all artifacts for a given task."""
        return [a for a in self._artifacts.values() if a.task_id == task_id]

    def get_unpresented(self) -> List[TaskArtifactEntry]:
        """Get artifacts not yet shown to user."""
        return [a for a in self._artifacts.values() if a.presented_at_turn == 0]

    @property
    def artifact_count(self) -> int:
        return len(self._artifacts)

    # =========================================================================
    # Prompt Generation
    # =========================================================================

    def to_prompt(self) -> str:
        """Full prompt for Front LLM context.

        Format:
            [ARTIFACTS]
            - [CONFIRMATION] order_food task abc: CODE-12345
            - [TEXT] search task def: Found 3 restaurants nearby...
        """
        if not self._artifacts:
            return "[ARTIFACTS]\nNo artifacts."

        lines = ["[ARTIFACTS]"]
        type_names = {v: v.name for v in ArtifactType}
        for a in self._artifacts.values():
            tname = type_names.get(ArtifactType(a.artifact_type), "UNKNOWN")
            preview = a.content[:80] + ("..." if len(a.content) > 80 else "")
            lines.append(f"- [{tname}] task {a.task_id[:8]}: {preview}")
        return "\n".join(lines)

    def to_slim_prompt(self) -> str:
        """Slim prompt for Back LLM (IDs and types only)."""
        if not self._artifacts:
            return ""
        type_names = {v: v.name for v in ArtifactType}
        parts = []
        for a in self._artifacts.values():
            tname = type_names.get(ArtifactType(a.artifact_type), "?")
            parts.append(f"{a.artifact_id[:8]}:{tname}")
        return "artifacts=" + ",".join(parts)

    # =========================================================================
    # Eviction Lifecycle (Epic 2.6)
    # =========================================================================

    def get_eviction_candidates(self, current_turn: int) -> List[TaskArtifactEntry]:
        """Get artifacts eligible for eviction to WARM tier.

        Rule: presented_at_turn > 0 AND (current_turn - presented_at_turn) >= 10
        Unpresented artifacts are NEVER evicted.

        Args:
            current_turn: Current turn number.

        Returns:
            List of evictable artifacts.
        """
        return [
            a
            for a in self._artifacts.values()
            if a.presented_at_turn > 0
            and (current_turn - a.presented_at_turn) >= _EVICT_AFTER_TURNS
        ]

    def evict_to_warm(self, current_turn: int) -> List[TaskArtifactEntry]:
        """Remove eviction-eligible artifacts and return them for WARM storage.

        The caller (HotTier demotion engine) is responsible for writing
        the returned entries into ArtifactsWarmSection.

        Args:
            current_turn: Current turn number.

        Returns:
            List of evicted TaskArtifactEntry objects.
        """
        candidates = self.get_eviction_candidates(current_turn)
        for a in candidates:
            del self._artifacts[a.artifact_id]

        if candidates:
            self._last_updated_ms = int(time.time() * 1000)
            self._cache_valid = False

        return candidates
