"""ConnectorResolver — MiniLM dense-retrieval connector routing.

Replaces the old 4-step graph traversal with POC-v2-validated MiniLM-L6
cosine-similarity search over connector documents (80.8% Strict C@1).

Spec: Epic 3.5 → Resolver Redesign M2 (RES-006 + RES-007a, 2026-06-17).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from k1.fabric.stores.global_projection_store import GlobalProjectionStore

logger = logging.getLogger(__name__)

# ── Universal operation aliases ────────────────────────────────────────
# Common LLM verbs → (operation_family, effect).  POC-proven at 96%.
# NOTE: Still imported by manifest_admission.py for effect classification.
# Will be migrated to a shared location in a later RES.
UNIVERSAL_OPERATION_ALIASES: dict[str, tuple[str, str]] = {
    # Reads
    "find": ("search", "read"),
    "search": ("search", "read"),
    "look": ("search", "read"),
    "check": ("list", "read"),
    "show": ("list", "read"),
    "view": ("list", "read"),
    "review": ("list", "read"),
    "read": ("list", "read"),
    "list": ("list", "read"),
    "pull": ("list", "read"),
    "get": ("list", "read"),
    "what": ("list", "read"),
    "who": ("list", "read"),
    # Writes
    "add": ("create", "write"),
    "schedule": ("create", "write"),
    "book": ("create", "write"),
    "create": ("create", "write"),
    "order": ("create", "write"),
    "log": ("create", "write"),
    "prescribe": ("create", "write"),
    "issue": ("create", "write"),
    "submit": ("create", "write"),
    "make": ("create", "write"),
    "remind": ("create", "write"),
    "notify": ("send", "write"),
    "send": ("send", "write"),
    "message": ("send", "write"),
    "share": ("send", "write"),
    "assign": ("update", "write"),
    "move": ("update", "write"),
    "update": ("update", "write"),
    "change": ("update", "write"),
    "edit": ("update", "write"),
    "process": ("update", "write"),
    "complete": ("update", "write"),
    "cancel": ("delete", "write"),
    "delete": ("delete", "write"),
    "remove": ("delete", "write"),
}


# ── ResolvedIntentType (DEPRECATED) ─────────────────────────────────────
# Kept for backward compatibility — still imported by situated_resolver,
# capability_binder, and policy/selector.  Will be removed when those
# consumers are migrated (RES-007b, RES-010, RES-013).


@dataclass
class ResolvedIntentType:
    """Legacy typed output.  Superseded by RankedConnectorSet."""

    intent_id: str
    domain: str
    resource_family: str | None
    operation_family: str
    effect: str
    role: str = "primary"
    evidence: list[str] = field(default_factory=list)
    confidence: str = "low"
    rejected: list[dict[str, str]] = field(default_factory=list)
    fallback_capabilities: list[dict[str, Any]] = field(default_factory=list)


# ── RankedConnectorSet ─────────────────────────────────────────────────


@dataclass
class RankedConnectorSet:
    """Output of ConnectorResolver.resolve().

    Primary is the top-ranked connector (or None if no match).
    Alternatives are the next best matches for the resolution envelope.
    """

    primary: dict[str, Any] | None
    alternatives: list[dict[str, Any]]


# ── ConnectorResolver ──────────────────────────────────────────────────


class ConnectorResolver:
    """MiniLM dense-retrieval connector router.

    Replaces the old 4-step graph traversal with POC-v2-validated
    MiniLM-L6 cosine-similarity search (80.8% Strict C@1).

    No domain facts in resolver code.  No graph tables.  No knobs.
    All connector semantics live in the GPS connector documents.
    """

    def __init__(self, global_store: GlobalProjectionStore) -> None:
        self.gps = global_store

    # ── Public API ─────────────────────────────────────────────────

    def resolve(
        self,
        action_text: str,
        context_hints: dict[str, Any] | None = None,
    ) -> RankedConnectorSet:
        """Resolve a raw user utterance to the best-matching connector.

        Args:
            action_text: Raw user utterance (no LLM pre-processing).
            context_hints: Optional advisory hints (active_os_domains, etc.).

        Returns:
            RankedConnectorSet with primary connector and alternatives.
        """
        active_os_domains: list[str] | None = None
        if context_hints:
            active_os_domains = context_hints.get("active_os_domains")

        hits = self.gps.search_connectors(
            action_text,
            top_k=5,
            active_os_domains=active_os_domains,
        )
        return RankedConnectorSet(
            primary=hits[0] if hits else None,
            alternatives=hits[1:] if len(hits) > 1 else [],
        )

    # ── Graph traversal methods DELETED (RES-006, 2026-06-17) ────────
    # _resolve_one, _resolve_operation, _resolve_concept,
    # _extract_concept_from_action, and all knob/embedding fields
    # have been removed.  The new resolve() above uses GPS MiniLM
    # dense retrieval instead of graph traversal.
    pass


# ── Legacy graph traversal (deleted — kept as comment for archaeology) ─
# The following methods were removed in RES-006:
#   _resolve_one()        — 4-step graph walk orchestrator
#   _resolve_operation()  — universal alias + graph table + first-word fallback
#   _resolve_concept()    — concept_aliases table traversal + word splitting
#   _extract_concept_from_action() — multi-word phrase fallback
#
# Replaced by: ConnectorResolver.resolve() → GPS.search_connectors()
# (MiniLM-L6 dense retrieval, POC-validated at 80.8% Strict C@1).


# Prevent the file from ending with a docstring that could be misread as active code
__all__ = [
    "ConnectorResolver",
    "RankedConnectorSet",
    "ResolvedIntentType",
    "UNIVERSAL_OPERATION_ALIASES",
]

# ── Legacy graph traversal methods deleted in RES-006 (2026-06-17).
# See git history for the old _resolve_one, _resolve_operation,
# _resolve_concept, _extract_concept_from_action implementations.
