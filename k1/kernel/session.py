"""Per-session component container (Tier 2).

SessionInstance holds ONLY per-session components created during
P1→P7 of ``KernelService.create_session()``.  Shared (Tier 1)
components live on ``KernelService`` itself.

See: ADR-0095, 09_wiring_plan Issue 2.1.2
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from k1.bus.ports.bus import IBus
from k1.bus.ports.mailbox import IMailbox, IMailboxRouter


@dataclass
class SessionInstance:
    """Typed container for one user session's Tier 2 components."""

    # ── identity ────────────────────────────────────────────
    session_id: str
    member_id: str | None

    # ── bus layer (per-session, SIM-D-01) ───────────────────
    bus: IBus
    router: IMailboxRouter
    front_mailbox: IMailbox
    back_mailbox: IMailbox

    # ── session state ───────────────────────────────────────
    session_state: Any  # SessionStateManager — typed as Any until SSM ports consolidated

    # ── fabric (per-session CapabilityFabric) ───────────────
    fabric: Any

    # ── concierge ───────────────────────────────────────────
    concierge: Any  # ConciergeRuntime from ConciergeFactory

    # ── memory writer ───────────────────────────────────────
    memory_writer: Any  # MemoryWriterService from MemoryWriterFactory

    # ── dispatchers ─────────────────────────────────────────
    front_dispatcher: Any
    back_dispatcher: Any

    # ── experience / delta / hitl ───────────────────────────
    experience_layer: Any
    delta_aggregator: Any
    delta_applicator: Any
    hil_port: Any

    # ── background tasks ────────────────────────────────────
    consumer_task: asyncio.Task[Any] | None
    dead_letter_consumer: Any

    # ── timestamps ──────────────────────────────────────────
    created_at: datetime

    # ── optional fields (set post-construction) ─────────────
    front_ctx: Any = None
    back_ctx: Any = None
    ledger: Any = None
    ledger_store: Any = None
    concierge_task: asyncio.Task[Any] | None = None

    # ── M5.E3.I3: per-session selfmodel handle ──────────────
    # ``None`` when ``KernelConfig.enable_self_model`` is False (the
    # default). When True, ``create_session`` builds a
    # :class:`k1.selfmodel.kernel.SelfModelHandle` at P3.5 and assigns
    # it here so consumers (concierge prompt builder, dispatcher,
    # bridge gates) can reach the bundle without hopping back through
    # ``KernelService``.
    self_model: Any = None  # SelfModelHandle | None

    # ── M1.E7: per-session temporal handle ──────────────────
    temporal: Any = None  # TemporalHandle | None

    # ── lifecycle helpers ───────────────────────────────────

    @property
    def is_started(self) -> bool:
        """True once the consumer task has been created."""
        return self.consumer_task is not None

    def _repr_summary(self) -> str:
        """Compact repr for logging."""
        started = "started" if self.is_started else "idle"
        return f"<Session {self.session_id} [{started}]>"
