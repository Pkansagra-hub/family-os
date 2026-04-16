"""
k1.sessionstate.public_types -- Stable public API surface for cross-component imports.

This module re-exports the SessionState types that other K1 components
(primarily Concierge) legitimately need. Importing from here instead of
deep internal paths (e.g. ``k1.sessionstate.sections.control``) provides
a stable boundary that survives internal refactors.

Consumers:
  - Concierge (fsm/controller.py, fsm/task_bridge.py, tools/implementations.py,
    protocols/hitl_wiring.py, prompt/builder.py)

Design:
  - Re-exports only. No new logic.
  - If a type moves internally, update this file — consumers don't change.
  - Test code may still import deep paths for test-specific section access.

References:
  - E-0.5.7: Concierge Direct SS Import Leakage
  - SessionState ARCHITECTURE.md §4.3

Exports grouped by source module:
  1. Writer port types (MutationRequest, BatchRequest, etc.)
  2. Control section types (IntentClassification, PrivacyBand)
  3. Task section types (TaskStatus, TaskStateEntry, TaskStateSection)
  4. Task artifact types (ArtifactType, TaskArtifactEntry, TaskArtifactsSection)
  5. Temporal context (compute_temporal_anchor, TemporalAnchor)
  6. Meta section (MetaSection)
  7. Factory (SessionStateFactory)
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# 7. Factory
# ---------------------------------------------------------------------------
from k1.sessionstate.factory import SessionStateFactory

# ---------------------------------------------------------------------------
# 1. Writer port types
# ---------------------------------------------------------------------------
from k1.sessionstate.ports.writer import BatchRequest, MutationRequest, RejectionCategory

# ---------------------------------------------------------------------------
# 2. Control section types
# ---------------------------------------------------------------------------
from k1.sessionstate.sections.control import IntentClassification, PrivacyBand

# ---------------------------------------------------------------------------
# 6. Meta section
# ---------------------------------------------------------------------------
from k1.sessionstate.sections.meta import MetaSection

# ---------------------------------------------------------------------------
# 4. Task artifacts section types
# ---------------------------------------------------------------------------
from k1.sessionstate.sections.task_artifacts import (
    ArtifactType,
    TaskArtifactEntry,
    TaskArtifactsSection,
)

# ---------------------------------------------------------------------------
# 3. Task state section types
# ---------------------------------------------------------------------------
from k1.sessionstate.sections.task_state import TaskStateEntry, TaskStateSection, TaskStatus

# ---------------------------------------------------------------------------
# 5. Temporal context
# ---------------------------------------------------------------------------
from k1.sessionstate.sections.temporal_context import TemporalAnchor, compute_temporal_anchor

__all__ = [
    # Writer port types
    "BatchRequest",
    "MutationRequest",
    "RejectionCategory",
    # Control section types
    "IntentClassification",
    "PrivacyBand",
    # Task state types
    "TaskStateEntry",
    "TaskStateSection",
    "TaskStatus",
    # Task artifact types
    "ArtifactType",
    "TaskArtifactEntry",
    "TaskArtifactsSection",
    # Temporal context
    "TemporalAnchor",
    "compute_temporal_anchor",
    # Meta section
    "MetaSection",
    # Factory
    "SessionStateFactory",
]
