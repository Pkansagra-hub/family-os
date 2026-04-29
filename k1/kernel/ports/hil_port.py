"""
k1.kernel.ports.hil_port -- IHILPort (F2 audit).

Kernel-level port for Human-in-the-Loop coordination.

Design notes
------------
There are currently TWO HILCoordinator implementations in the codebase
that serve different roles:

  - ``k1.concierge.protocols.hitl_coordinator.HILCoordinator`` --
    FSM-side closed-cycle HITL orchestration for the Concierge runtime
    (V2 §9.1). Owns suspension manager, ledger persistence, and
    bus emission for ``task.suspended.v1`` / ``task.resume.v1``.

  - ``k1.planner.services.hil_coordinator.HILCoordinator`` --
    Planner-side clarification/approval coordination (PLAN-10).
    Owns LLM-driven question generation and ``hil.*`` bus topics
    used during SKETCH/VALIDATE stages.

The kernel does NOT need to unify these two classes — they have
genuinely different responsibilities (suspension management vs.
plan clarification). This port instead exposes the *minimal* surface
the kernel cares about: a coordinator can produce a HIL request and
accept a user response.

Both implementations satisfy this Protocol structurally via
``handle_*`` methods; the kernel binds the appropriate concrete
coordinator at construction time (Concierge S10, Planner S?).

Audit reference
---------------
- F2 (Findings doc): "Unified IHILPort + collapse 2 HILCoordinator
  classes". The collapse is rejected because the two classes serve
  distinct subsystems; instead this port documents the kernel-visible
  contract so that downstream modules depend on the Protocol rather
  than the concrete classes.
- W10 (Findings doc): "IHILPort Protocol missing" -- resolved by this
  module.

Exports:
  IHILPort
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class IHILPort(Protocol):
    """Minimal kernel-level Human-in-the-Loop coordinator port.

    Concrete implementations:

      - ``k1.concierge.protocols.hitl_coordinator.HILCoordinator``
        (FSM-side, suspension + ledger).
      - ``k1.planner.services.hil_coordinator.HILCoordinator``
        (planner-side, clarification + approval).

    Both implementations are structurally compatible with this
    Protocol via their public ``handle_*`` / ``request_*`` /
    ``submit_*`` methods. The exact method shape is intentionally
    left to the concrete implementations because the two subsystems
    have different bus topics and persistence needs.

    The kernel uses this Protocol only to declare type-safe
    dependencies on a HIL coordinator without importing concrete
    classes from concierge or planner subpackages.
    """

    # No abstract methods are declared here on purpose: the two
    # concrete coordinators expose different method sets. This
    # Protocol functions as a *marker* port that downstream code can
    # use for type annotations (``coordinator: IHILPort``) without
    # creating a circular import on either subsystem.
    ...
