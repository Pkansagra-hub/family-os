"""
k1.concierge.delta.writer_registry -- Single Writer Invariant enforcement.

V2 Design Ref: Section 5 (Single Writer Invariant, Authoritative Read/Write Matrix)

The Single Writer Invariant (ADR-0017g) prevents concurrent writes
from corrupting SessionState:

    Rule 1: Sectional isolation -- Front and Back write to DIFFERENT sections.
            No section has two concurrent LLM writers.
    Rule 2: Back never writes SS directly -- Back emits structured deltas
            to the bus.  The FSM aggregates and writes them.
    Rule 3: Reads are lock-free snapshots -- no write contention on reads.

This module encodes the Authoritative Read/Write Matrix from V2
Section 5.  It validates that a given WriterRole is authorized to
write to a given section.

Writer roles and their authorized sections (V2 Section 5):
    FRONT_LLM:        beliefs_active, scoreboard, affective_now,
                      clarifications, narrative_active
    PHASE1:           scoreboard, affective_now, control
    FSM:              control, history_active, meta, task_state, task_artifacts
    EXPERIENCE_LAYER: affective_now
    SESSION_INIT:     persona

Back LLM is NOT a WriterRole.  It never writes SS directly.  It emits
structured deltas that the FSM applies via DeltaApplicator.

Sequential safety within turns (V2 Section 5):
    Phase1 finishes BEFORE Front LLM starts (TurnLock).
    ExperienceLayer fires at turn_end AFTER Front completes.
    Multiple writers to the same section are always sequential, never concurrent.
"""

from __future__ import annotations

from enum import Enum


class WriterRole(str, Enum):
    """Authorized SS writer roles.

    V2 Design Ref: Section 5, Authoritative Read/Write Matrix.

    Back LLM is intentionally absent.  Back never writes SS
    directly -- it emits deltas to the bus (Rule 2).
    """

    FRONT_LLM = "front_llm"
    PHASE1 = "phase1"
    FSM = "fsm"
    EXPERIENCE_LAYER = "experience_layer"
    SESSION_INIT = "session_init"


class SingleWriterViolation(Exception):
    """Raised when an unauthorized writer attempts a section write.

    Carries the section name, the attempted role, and the list of
    authorized writers for diagnostics.
    """

    pass


# =========================================================================
# Section -> authorized writers (V2 Section 5, Authoritative Read/Write Matrix)
# =========================================================================
#
# Each entry maps a section name to its authorized writers, ordered
# by priority.  The ordering reflects the design doc's Write Matrix:
#   - First writer is the primary writer.
#   - Additional writers are secondary (Phase1 before LLM, etc.).
#
# Sequential safety is guaranteed by the turn lifecycle:
#   Phase1 finishes BEFORE Front LLM starts (TurnLock).
#   ExperienceLayer fires at turn_end AFTER Front completes.

SECTION_WRITERS: dict[str, list[WriterRole]] = {
    # Front-LLM cognitive sections
    "beliefs_active": [WriterRole.FRONT_LLM],
    "scoreboard": [WriterRole.PHASE1, WriterRole.FRONT_LLM],
    "affective_now": [
        WriterRole.PHASE1,
        WriterRole.FRONT_LLM,
        WriterRole.EXPERIENCE_LAYER,
    ],
    "clarifications": [WriterRole.FRONT_LLM],
    "narrative_active": [WriterRole.FRONT_LLM],
    # FSM-managed sections
    "control": [WriterRole.FSM, WriterRole.PHASE1],
    "history_active": [WriterRole.FSM],
    "meta": [WriterRole.FSM],
    # Immutable after init
    "persona": [WriterRole.SESSION_INIT],
    # Task lifecycle (FSM via DeltaApplicator from Back's bus deltas)
    "task_state": [WriterRole.FSM],
    "task_artifacts": [WriterRole.FSM],
}

# All registered sections (for quick membership tests)
ALL_WRITER_SECTIONS: frozenset[str] = frozenset(SECTION_WRITERS.keys())


def validate_writer(section: str, role: WriterRole) -> bool:
    """Check if a writer role is authorized for a section.

    Args:
        section: SS section name.
        role:    The writer's role.

    Returns:
        True if the role is an authorized writer for this section.
        False if the section is unknown or the role is not authorized.
    """
    writers = SECTION_WRITERS.get(section)
    if writers is None:
        return False
    return role in writers


def enforce_writer(section: str, role: WriterRole) -> None:
    """Enforce that a writer role is authorized for a section.

    This is the validation gate used at write boundaries.  If the
    role is not authorized, a SingleWriterViolation is raised with
    a diagnostic message listing the authorized writers.

    Args:
        section: SS section name.
        role:    The writer's role.

    Raises:
        SingleWriterViolation: If the role is not an authorized writer.
    """
    if not validate_writer(section, role):
        authorized = SECTION_WRITERS.get(section, [])
        raise SingleWriterViolation(
            f"WriterRole.{role.name} is not authorized to write "
            f"'{section}'. Authorized writers: "
            f"{[w.name for w in authorized]}"
        )
