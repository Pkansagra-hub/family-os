"""
SessionState Sections Package - HOT CORE + WARM TIER Sections
==============================================================

This package contains individual section implementations.
Each section is a bounded buffer with specific budget and behavior.

HOT CORE Sections (52KB total, always in memory):
- control.py        - 8KB, NEVER EVICT, mode/turn/focus
- beliefs_active.py - 8KB, active beliefs
- scoreboard.py     - 6KB, task progress
- history_active.py - 8KB, last N turns
- clarifications.py - 4KB, pending clarifications
- affective_now.py  - 4KB, current mood
- narrative_active.py - 4KB, current threads
- meta.py           - 2KB, schema version
- spatial.py        - 4KB, current spatial context/projection
- task_state.py     - 4KB, NEVER EVICT, active tasks
- task_artifacts.py - 4KB, task output artifacts

WARM TIER Sections (48KB total, evictable):
- beliefs_history.py - 12KB, demoted beliefs
- history_recent.py  - 16KB, demoted history
- persona.py         - 8KB, stable traits
- place_registry.py  - 8KB, known places/geofences
- telemetry.py       - 4KB, metrics
- artifacts_warm.py  - 8KB, demoted artifacts
"""

from .affective_now import AffectiveNowSection
from .artifacts_warm import ArtifactsWarmSection
from .beliefs_active import BeliefsActiveSection

# WARM TIER sections
from .beliefs_history import BeliefsHistorySection
from .clarifications import ClarificationsSection

# HOT CORE sections
from .control import ControlSection
from .grounding import GroundingSection
from .history_active import HistoryActiveSection
from .history_recent import HistoryRecentSection
from .meta import MetaSection
from .narrative_active import NarrativeActiveSection
from .persona import PersonaSection
from .place_registry import PlaceRegistrySection
from .scoreboard import ScoreboardSection
from .spatial import SpatialSection
from .task_artifacts import ArtifactType, TaskArtifactEntry, TaskArtifactsSection
from .task_state import TaskStateEntry, TaskStateSection, TaskStatus
from .telemetry import TelemetrySection
from .temporal import TemporalSection

__all__ = [
    # HOT CORE
    "ControlSection",
    "BeliefsActiveSection",
    "ScoreboardSection",
    "HistoryActiveSection",
    "ClarificationsSection",
    "AffectiveNowSection",
    "NarrativeActiveSection",
    "MetaSection",
    "TemporalSection",
    "SpatialSection",
    "GroundingSection",
    "TaskStateSection",
    "TaskStateEntry",
    "TaskStatus",
    "TaskArtifactsSection",
    "TaskArtifactEntry",
    "ArtifactType",
    # WARM TIER
    "BeliefsHistorySection",
    "HistoryRecentSection",
    "PersonaSection",
    "PlaceRegistrySection",
    "TelemetrySection",
    "ArtifactsWarmSection",
]
