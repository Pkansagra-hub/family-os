"""
k1.concierge.ledger -- V3 append-only conversation ledger.

M1 E1.2: Event-sourced conversation ledger infrastructure.

The ledger is the canonical timeline of all domain events for a session.
All session state (history, task states, pending results) is a derived
projection from the ledger event stream.

Key components:
    LedgerEntry         -- Immutable record in the ledger.
    ILedgerStore        -- Storage protocol (append, read, query).
    InMemoryLedgerStore -- POC/test implementation.
    LedgerWriter        -- Append logic with idempotency via event_id.

Reference: v3_whiteboard.md Section 3.A (Event-Sourced Conversation Ledger).
Reference: v3_milestones.md E1.2.1 (append-only ledger with idempotency).
"""

from k1.concierge.ledger.projections import (
    project_cancel_state,
    project_history,
    project_hitl_state,
    project_pending_results,
    project_suspension_state,
    project_task_states,
)
from k1.concierge.ledger.store import ILedgerStore, InMemoryLedgerStore, LedgerEntry
from k1.concierge.ledger.writer import LedgerWriter

__all__ = [
    "ILedgerStore",
    "InMemoryLedgerStore",
    "LedgerEntry",
    "LedgerWriter",
    "project_cancel_state",
    "project_history",
    "project_hitl_state",
    "project_pending_results",
    "project_suspension_state",
    "project_task_states",
]
