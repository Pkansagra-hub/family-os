"""ResourceProjection — Contract B.

Resolves person/entity aliases and connected resources from
``LocalProjectionStore`` into a ``ResourceUniverse``.

Spec: Epic 3.4, whiteboard Contract B.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from k1.fabric.resolver.request_frame import RequestFrame
from k1.fabric.stores.global_projection_store import GlobalProjectionStore
from k1.fabric.stores.local_projection_store import LocalProjectionStore

# ── Write-operation set ────────────────────────────────────────────────
_WRITE_OPERATIONS = frozenset({"create", "update", "delete", "send", "fire", "write"})


# ── Dataclasses ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ResourceCandidate:
    """A concrete resource connected to the actor in this household."""

    resource_id: str
    label: str
    resource_kind: str
    connector_id: str  # empty if needs_resolution=False
    actor_permission: str  # "read_write" | "read_only" | "restricted" | "none"
    freshness_state: str  # "fresh" | "stale" | "unknown"
    aliases: list[str] = field(default_factory=list)
    admission_verdict: str | None = None


@dataclass(frozen=True)
class PersonCandidate:
    """A household member resolved from an alias."""

    person_id: str
    label: str
    role: str
    linked_resource_ids: dict[str, Any] = field(default_factory=dict)
    resolved: bool = False


@dataclass(frozen=True)
class UnresolvedRef:
    """A ref that could not be resolved — missing or ambiguous."""

    raw: str
    entity_type: str  # "person" | "resource"
    reason: str  # "not_found" | "ambiguous" | "permission_denied" | "revoked"
    candidates: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class ScopeProof:
    """Evidence of what sources were consulted for this projection."""

    scope_proof_id: str
    actor_id: str
    space_id: str
    projection_sources: list[dict[str, Any]] = field(default_factory=list)
    omissions: list[dict[str, Any]] = field(default_factory=list)
    exclusions: list[dict[str, Any]] = field(default_factory=list)
    completeness: str = "unknown"


@dataclass(frozen=True)
class ResourceUniverse:
    """The resolved local-world projection — what resources the actor has."""

    universe_id: str
    resource_candidates: list[ResourceCandidate]
    person_candidates: list[PersonCandidate]
    unresolved: list[UnresolvedRef]
    scope_proof: ScopeProof
    completeness: str  # "complete" | "partial" | "unknown"
    freshness: str  # "fresh" | "stale" | "unknown"


# ── Service ────────────────────────────────────────────────────────────


class ResolveResourcesService:
    """Resolves person/entity aliases and connected resources into a
    ``ResourceUniverse``.

    Uses ``LocalProjectionStore`` for alias resolution and connected
    resources; consults ``GlobalProjectionStore`` for connector admission
    status.
    """

    def __init__(
        self,
        global_store: GlobalProjectionStore,
        local_store: LocalProjectionStore,
    ) -> None:
        self.global_store = global_store
        self.local_store = local_store

    def resolve(self, frame: RequestFrame, actor_id: str, space_id: str) -> ResourceUniverse:
        """Resolve all person/entity and resource refs in the frame."""
        projection_sources: list[dict[str, Any]] = []
        omissions: list[dict[str, Any]] = []
        exclusions: list[dict[str, Any]] = []
        unresolved: list[UnresolvedRef] = []
        people: list[PersonCandidate] = []
        resources: list[ResourceCandidate] = []

        # ── Resolve person refs ──
        for person_ref in frame.person_refs:
            if not person_ref.needs_resolution:
                continue

            matches = self.local_store.resolve_alias(person_ref.raw, actor_id, entity_type="person")
            projection_sources.append(_source("alias_index", "person", person_ref.raw, matches))

            if not matches:
                matches = self.local_store.fuzzy_resolve_alias(
                    person_ref.raw, actor_id, entity_type="person"
                )
                projection_sources.append(
                    _source("alias_index_fuzzy", "person", person_ref.raw, matches)
                )

            if not matches:
                unresolved.append(UnresolvedRef(person_ref.raw, "person", "not_found"))
                continue

            # Deduplicate by entity_id (multiple alias spellings → same entity)
            unique_matches = _dedupe_matches_by_entity(matches)

            if len(unique_matches) > 1:
                unresolved.append(
                    UnresolvedRef(
                        person_ref.raw,
                        "person",
                        "ambiguous",
                        [_candidate_ref(m) for m in unique_matches],
                    )
                )
                continue

            member = self.local_store.get_household_member(str(unique_matches[0]["entity_id"]))
            projection_sources.append(
                _source("household_members", "person", person_ref.raw, unique_matches[:1])
            )
            if member is None:
                unresolved.append(UnresolvedRef(person_ref.raw, "person", "not_found"))
                continue

            people.append(
                PersonCandidate(
                    person_id=member["person_id"],
                    label=member["label"],
                    role=member["role"],
                    linked_resource_ids=member.get("linked_resource_ids", {}),
                    resolved=True,
                )
            )

        # ── Resolve resource refs ──
        for resource_ref in frame.resource_refs:
            if not resource_ref.needs_resolution:
                rk = resource_ref.resource_kind_hint or resource_ref.raw or "unknown"
                resources.append(
                    ResourceCandidate(
                        resource_id=f"res_direct_{rk}_{uuid.uuid4().hex[:8]}",
                        label=resource_ref.raw,
                        resource_kind=rk,
                        connector_id="",  # empty → CapabilityBinder searches by resource_kind
                        actor_permission="read_write",
                        freshness_state="fresh",
                        aliases=[],
                        admission_verdict="admitted",
                    )
                )
                continue

            matches = self.local_store.resolve_alias(
                resource_ref.raw, actor_id, entity_type="resource"
            )
            projection_sources.append(_source("alias_index", "resource", resource_ref.raw, matches))

            if not matches:
                matches = self.local_store.fuzzy_resolve_alias(
                    resource_ref.raw, actor_id, entity_type="resource"
                )
                projection_sources.append(
                    _source("alias_index_fuzzy", "resource", resource_ref.raw, matches)
                )

            if not matches:
                unresolved.append(UnresolvedRef(resource_ref.raw, "resource", "not_found"))
                continue

            # Deduplicate by entity_id (multiple alias spellings → same entity)
            unique_matches = _dedupe_matches_by_entity(matches)

            if len(unique_matches) > 1:
                unresolved.append(
                    UnresolvedRef(
                        resource_ref.raw,
                        "resource",
                        "ambiguous",
                        [_candidate_ref(m) for m in unique_matches],
                    )
                )
                continue

            resource = self.local_store.get_connected_resource(str(unique_matches[0]["entity_id"]))
            projection_sources.append(
                _source("connected_resources", "resource", resource_ref.raw, unique_matches[:1])
            )
            if resource is None:
                unresolved.append(UnresolvedRef(resource_ref.raw, "resource", "not_found"))
                continue

            if resource.get("status") != "active":
                exclusions.append(
                    {"entity_id": resource["resource_id"], "reason": resource.get("status")}
                )
                unresolved.append(UnresolvedRef(resource_ref.raw, "resource", "revoked"))
                continue

            if _permission_denied(resource, frame):
                exclusions.append(
                    {"entity_id": resource["resource_id"], "reason": "permission_denied"}
                )
                unresolved.append(UnresolvedRef(resource_ref.raw, "resource", "permission_denied"))
                continue

            connector = self.global_store.get_connector(resource.get("connector_id", ""))
            projection_sources.append(
                _source(
                    "global_connectors",
                    "connector",
                    resource.get("connector_id", ""),
                    [{"entity_id": resource.get("connector_id", "")}],
                )
            )

            admission_verdict = connector.admission_verdict if connector else None
            if admission_verdict != "admitted":
                omissions.append(
                    {
                        "entity_id": resource["resource_id"],
                        "connector_id": resource.get("connector_id"),
                        "reason": "connector_not_admitted",
                    }
                )

            resources.append(
                ResourceCandidate(
                    resource_id=resource["resource_id"],
                    label=resource["label"],
                    resource_kind=resource["resource_kind"],
                    connector_id=resource.get("connector_id", ""),
                    actor_permission=resource.get("permissions", "read_write"),
                    freshness_state=resource.get("freshness_state", "fresh"),
                    aliases=resource.get("aliases", []),
                    admission_verdict=admission_verdict,
                )
            )

        completeness = _completeness(frame, unresolved, omissions)
        freshness = _freshness(resources)

        return ResourceUniverse(
            universe_id="universe-" + uuid.uuid4().hex[:16],
            resource_candidates=resources,
            person_candidates=people,
            unresolved=unresolved,
            scope_proof=ScopeProof(
                scope_proof_id="scope-" + uuid.uuid4().hex[:16],
                actor_id=actor_id,
                space_id=space_id,
                projection_sources=projection_sources,
                omissions=omissions,
                exclusions=exclusions,
                completeness=completeness,
            ),
            completeness=completeness,
            freshness=freshness,
        )


# ── Helpers ────────────────────────────────────────────────────────────


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _source(
    source: str, entity_type: str, query: str, matches: list[dict[str, Any]]
) -> dict[str, Any]:
    return {
        "source": source,
        "entity_type": entity_type,
        "query": query,
        "entity_ids_considered": [str(m.get("entity_id", "")) for m in matches],
        "freshness": "fresh",
        "queried_at": _utc_now_iso(),
    }


def _candidate_ref(match: dict[str, Any]) -> dict[str, Any]:
    return {
        "entity_id": str(match.get("entity_id", "")),
        "entity_type": str(match.get("entity_type", "")),
        "alias_lower": str(match.get("alias_lower", match.get("alias", ""))),
    }


def _dedupe_matches_by_entity(matches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return deduplicated matches keyed by ``entity_id``, preserving first-seen order."""
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for m in matches:
        eid = str(m.get("entity_id", ""))
        if eid not in seen:
            seen.add(eid)
            deduped.append(m)
    return deduped


def _permission_denied(resource: dict[str, Any], frame: RequestFrame) -> bool:
    permission = resource.get("permissions", "read_write")
    if permission in {"none", "restricted"}:
        return True
    if permission == "read_only" and any(
        intent.operation_hint in _WRITE_OPERATIONS for intent in frame.intents
    ):
        return True
    return False


def _completeness(
    frame: RequestFrame,
    unresolved: list[UnresolvedRef],
    omissions: list[dict[str, Any]],
) -> str:
    write_intended = any(intent.operation_hint in _WRITE_OPERATIONS for intent in frame.intents)
    if unresolved and write_intended:
        return "unknown"
    if unresolved or omissions:
        return "partial"
    return "complete"


def _freshness(resources: list[ResourceCandidate]) -> str:
    if not resources:
        return "unknown"
    if any(r.freshness_state == "stale" for r in resources):
        return "stale"
    if any(r.freshness_state == "unknown" for r in resources):
        return "unknown"
    return "fresh"
