"""CapabilityTypeResolver — graph-based typed resolution.

Traverses the 5 graph ontology tables in ``GlobalProjectionStore`` to
deterministically map an intent (operation_hint + resource_kind_hint) to a
specific capability.

Spec: Epic 3.5.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from k1.fabric.resolver.request_frame import RequestFrame, RequestFrameIntent
from k1.fabric.resolver.resource_projection import ResourceUniverse
from k1.fabric.stores.global_projection_store import GlobalProjectionStore
from k1.fabric.stores.local_projection_store import LocalProjectionStore

# ── Constant sets ──────────────────────────────────────────────────────
_WRITE_OPERATIONS = frozenset({"create", "update", "delete", "send", "fire", "write"})
_READ_OPERATIONS = frozenset({"list", "read", "search"})

# Stop-words skipped during concept extraction from action text
_STOP_WORDS = frozenset(
    {
        "the",
        "a",
        "an",
        "to",
        "for",
        "of",
        "in",
        "on",
        "at",
        "is",
        "me",
        "my",
        "and",
        "or",
        "with",
        "from",
        "by",
    }
)

# ── Universal operation aliases ────────────────────────────────────────
# Common LLM verbs → (operation_family, effect).  POC-proven at 96%.
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


# ── ResolvedIntentType ─────────────────────────────────────────────────


@dataclass
class ResolvedIntentType:
    """Typed output of CapabilityTypeResolver."""

    intent_id: str
    domain: str
    resource_family: str | None  # canonical resource family
    operation_family: str  # canonical operation
    effect: str  # "read" | "write"
    role: str = "primary"  # "primary" | "companion" | "prerequisite" | "verifier"
    evidence: list[str] = field(default_factory=list)
    confidence: str = "low"  # "high" | "medium" | "low"
    rejected: list[dict[str, str]] = field(default_factory=list)
    fallback_capabilities: list[dict[str, Any]] = field(default_factory=list)


# ── CapabilityTypeResolver ─────────────────────────────────────────────


class CapabilityTypeResolver:
    """Traverses concept→resource→connector→capability graph tables.

    Uses the 5 graph ontology tables in ``GlobalProjectionStore``:
      concept_aliases → concept_resource_edges → resource_connector_edges
      operation_aliases → capability_type_index

    Fallback: when graph confidence is low, delegates to FTS5 BM25 search
    as a concept suggestion layer (not a decision layer).
    """

    def __init__(
        self,
        global_store: GlobalProjectionStore,
        local_store: LocalProjectionStore,
    ) -> None:
        self.global_store = global_store
        self.local_store = local_store

    # ── Public API ─────────────────────────────────────────────────

    def resolve(
        self,
        frame: RequestFrame,
        universe: ResourceUniverse,
    ) -> list[ResolvedIntentType]:
        """Resolve every intent in the frame to its typed capability target."""
        results: list[ResolvedIntentType] = []
        for intent in frame.intents:
            resolved = self._resolve_one(intent, universe)
            results.append(resolved)
        return results

    # ── Internal 4-step traversal ───────────────────────────────────

    def _resolve_one(
        self,
        intent: RequestFrameIntent,
        universe: ResourceUniverse,
    ) -> ResolvedIntentType:
        """4-step graph traversal:
        1. Resolve operation: operation_hint → (operation_family, effect)
        2. Resolve concept: resource_kind_hint → canonical concepts
        3. Map concept → resource_family
        4. Typed capability lookup: domain + resource_family + operation_family + effect
        """
        evidence: list[str] = []
        rejected: list[dict[str, str]] = []

        # ── Step 1: Resolve operation ──
        op_hint = (intent.operation_hint or "").lower().strip()
        op_family, effect = self._resolve_operation(op_hint, intent)
        if op_family:
            evidence.append(f"operation: {op_hint} → {op_family}/{effect}")

        # ── Step 2: Resolve concept ──
        rk = (intent.resource_kind_hint or "").strip()
        action = (intent.action or "").strip()
        domain = intent.domain or ""

        concept_hits = self._resolve_concept(rk, action, domain)
        if concept_hits:
            best = concept_hits[0]
            evidence.append(f"concept: {rk}|{action[:40]} → {best}")
        else:
            concept_hits = self._extract_concept_from_action(action, domain)

        # ── Step 3: Map concept → resource_family ──
        resource_family: str | None = None
        for concept in concept_hits[:3]:
            rfs = self.global_store.get_concept_resource_family(concept, domain)
            if rfs:
                resource_family = rfs[0]["resource_family"]
                evidence.append(f"resource_family: {concept} → {resource_family}")
                break
            rejected.append({"concept": concept, "reason": "no_resource_family_edge"})

        if not resource_family:
            # Fallback 1: try concepts directly as resource_family
            for concept in concept_hits[:3]:
                caps = self.global_store.lookup_capability_by_type(
                    domain=domain,
                    resource_family=concept,
                    operation_family=op_family or "",
                    effect=effect,
                )
                if caps:
                    resource_family = concept
                    evidence.append(f"resource_family: direct concept match → {concept}")
                    break
            # Fallback 2: use resource_kind_hint directly
            if not resource_family and rk:
                resource_family = rk
                evidence.append(f"resource_family: fallback from rk_hint={rk}")

        # ── Step 4: Typed capability lookup ──
        capabilities: list[dict[str, Any]] = []
        if resource_family and op_family:
            caps = self.global_store.lookup_capability_by_type(
                domain=domain,
                resource_family=resource_family,
                operation_family=op_family,
                effect=effect,
            )
            if caps:
                capabilities = caps
                evidence.append(
                    f"typed_lookup: {domain}.{resource_family}.{op_family}.{effect} "
                    f"→ {len(caps)} matches"
                )

        # ── Confidence scoring ──
        conf = "low"
        if len(evidence) >= 4:
            conf = "high"
        elif len(evidence) >= 2:
            conf = "medium"

        return ResolvedIntentType(
            intent_id=intent.intent_id,
            domain=domain,
            resource_family=resource_family,
            operation_family=op_family or op_hint,
            effect=effect,
            evidence=evidence,
            confidence=conf,
            rejected=rejected,
            fallback_capabilities=capabilities,
        )

    # ── Step 1 helper ───────────────────────────────────────────────

    def _resolve_operation(
        self,
        op_hint: str,
        intent: RequestFrameIntent,
    ) -> tuple[str, str]:
        """Resolve operation alias → operation_family + effect."""
        # Check universal aliases first
        if op_hint in UNIVERSAL_OPERATION_ALIASES:
            op_family, effect = UNIVERSAL_OPERATION_ALIASES[op_hint]
            return op_family, effect

        # Check graph table
        hits = self.global_store.resolve_operation(op_hint)
        if hits:
            return hits[0]["operation_family"], hits[0]["effect"]

        # Derive from known operation sets
        if op_hint in _READ_OPERATIONS:
            return op_hint, "read"
        if op_hint in _WRITE_OPERATIONS:
            return op_hint, "write"

        return op_hint, "read"  # default

    # ── Step 2 helpers ──────────────────────────────────────────────

    def _resolve_concept(
        self,
        rk: str,
        action: str,
        domain: str,
    ) -> list[str]:
        """Resolve resource_kind_hint or action text → canonical concepts."""
        concepts: list[str] = []

        # Exact lookup via concept_aliases table
        if rk:
            hits = self.global_store.resolve_concept(rk, domain)
            for h in hits:
                if h["canonical_concept"] not in concepts:
                    concepts.append(h["canonical_concept"])

        # Also try the action text words as aliases
        if action:
            words = action.lower().split()
            for word in words[:5]:
                if word in _STOP_WORDS:
                    continue
                hits = self.global_store.resolve_concept(word, domain)
                for h in hits:
                    if h["canonical_concept"] not in concepts:
                        concepts.append(h["canonical_concept"])

        return concepts

    def _extract_concept_from_action(
        self,
        action: str,
        domain: str,
    ) -> list[str]:
        """Fallback: extract potential concept words from action text."""
        concepts: list[str] = []
        if not action:
            return concepts

        words = action.lower().split()
        # Try multi-word phrases first, then individual words
        for i in range(len(words)):
            for j in range(i + 1, min(i + 4, len(words) + 1)):
                phrase = " ".join(words[i:j])
                hits = self.global_store.resolve_concept(phrase, domain)
                for h in hits:
                    if h["canonical_concept"] not in concepts:
                        concepts.append(h["canonical_concept"])
        return concepts
