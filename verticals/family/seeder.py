"""verticals.family.seeder — SpaceDataSeeder.

Three injection paths from a ``FamilyProfile``:

  L0 Session Beliefs  → list[dict] returned by ``build_seed_memories()``,
                        passed to ``KernelConfig.seed_memories`` BEFORE
                        ``start_kernel()``.
  L1/L2 Self-Model    → ``SpaceGraphSnapshot`` written to the projection
                        store via ``seed_space_projection()`` AFTER
                        ``start_kernel()`` (uses ``SelfModelServiceBundle``).
  L3 K0 Episodic      → ``IBridgeCommandPort.submit_batch()`` via
                        ``seed_k0_memories()`` (M14 hook — no-op until
                        bridge is live).

This module performs NO LLM calls and is fully synchronous except for the
bridge path. Idempotent: ``seed_space_projection`` reads existing snapshot
and skips re-writing if members are already populated.
"""

from __future__ import annotations

import inspect
import logging
import time
from typing import Any, Dict, List, Optional

from k1.selfmodel.contracts.self_model import K1SelfModelSnapshot
from k1.selfmodel.contracts.space_graph import (
    ActorRef,
    SpaceEdge,
    SpaceGraphSnapshot,
)
from k1.selfmodel.service.self_model import SELF_MODEL_WRITER_ID
from k1.selfmodel.service.space_graph import SPACE_GRAPH_WRITER_ID
from verticals.family.profile import FamilyProfile

logger = logging.getLogger(__name__)


class SpaceDataSeeder:
    """Project a ``FamilyProfile`` into kernel seed surfaces."""

    # ------------------------------------------------------------------
    # L0 — Session Beliefs (Concierge seed_memories)
    # ------------------------------------------------------------------
    def build_seed_memories(
        self,
        profile: FamilyProfile,
        *,
        device_id: str = "",
    ) -> List[Dict[str, Any]]:
        """Return list[dict] ready for ``KernelConfig.seed_memories``.

        Emits 4 synthetic context entries derived from the profile, then
        appends every ``FamilyMemoryEntry`` converted via ``to_seed_dict()``.
        """
        active = profile.member_by_device(device_id) if device_id else None
        active_actor = active.actor_id if active else ""
        active_name = active.name if active else ""

        member_summary = ", ".join(f"{m.name} ({m.relation})" for m in profile.members)

        out: List[Dict[str, Any]] = [
            {
                "type": "semantic",
                "content": (
                    f"Family: {profile.family_name}. Members: {member_summary}. "
                    f"Located in {profile.location}, timezone {profile.timezone}."
                ),
                "tags": ["family_context", "members", "location"],
                "source": "FamilyProfile (synthetic)",
            },
            {
                "type": "semantic",
                "content": (
                    f"Active speaker on device '{device_id}': "
                    f"{active_name or 'unknown'} ({active_actor or 'unknown'})."
                ),
                "tags": ["active_member", "device", "session"],
                "source": "FamilyProfile (synthetic)",
                "actor_id": active_actor,
            },
            {
                "type": "semantic",
                "content": (
                    f"Session config: tone={profile.session_config.get('tone', 'neutral')}, "
                    f"formality={profile.session_config.get('formality', 'neutral')}, "
                    f"verbosity={profile.session_config.get('verbosity', 'normal')}, "
                    f"language={profile.preferred_language}."
                ),
                "tags": ["session_config", "tone"],
                "source": "FamilyProfile (synthetic)",
            },
            {
                "type": "semantic",
                "content": (
                    "Dietary restrictions: "
                    f"{'; '.join(profile.dietary_restrictions) or 'none'}. "
                    "Accessibility needs: "
                    f"{'; '.join(profile.accessibility_needs) or 'none'}."
                ),
                "tags": ["dietary", "accessibility", "constraints"],
                "source": "FamilyProfile (synthetic)",
            },
        ]

        for entry in profile.memories:
            out.append(entry.to_seed_dict())

        return out

    # ------------------------------------------------------------------
    # L1/L2 — Self-Model space-graph projection
    # ------------------------------------------------------------------
    def seed_space_projection(
        self,
        bundle: Any,
        profile: FamilyProfile,
        *,
        revision: str = "",
    ) -> bool:
        """Write a ``SpaceGraphSnapshot`` for ``profile`` via the bundle's store.

        Idempotent: returns ``False`` (no-op) if the store already holds a
        snapshot with at least as many members. Returns ``True`` on a fresh
        write. Raises on store rejection (writer_id mismatch, etc.) — caller
        decides fatality.
        """
        if bundle is None:
            raise ValueError("seed_space_projection requires a SelfModelServiceBundle")

        store = getattr(bundle, "store", None)
        if store is None:
            raise ValueError("SelfModelServiceBundle has no 'store' attribute")

        space_id = profile.space_id

        # Idempotency: skip only if a fully-populated snapshot already exists.
        # A "fully-populated" snapshot has every profile member AND the full
        # household_member edge mesh (one bidirectional edge between every
        # pair of members). Earlier seeder versions only wrote parent_of edges,
        # which left non-parent/non-child relations (grandparent, etc.)
        # invisible in the per-actor adjacency view. Re-seed those stores.
        try:
            existing, _ = store.read_space(space_id)
        except Exception:  # pragma: no cover — defensive
            existing = None
        member_count = len(profile.members)
        expected_min_edges = member_count * (member_count - 1)  # full mesh
        if (
            existing is not None
            and len(existing.members) >= member_count
            and len(existing.relations) >= expected_min_edges
        ):
            logger.info(
                "seed_space_projection: space '%s' already populated (%d members, %d edges) — skipping",
                space_id,
                len(existing.members),
                len(existing.relations),
            )
            return False

        now_ms = int(time.time() * 1000)
        rev = revision or f"seed-{now_ms}"

        members_tuple = tuple(
            ActorRef(
                member_id=m.actor_id,
                display_name=m.name,
                role=m.role(),
                age_band=m.age_band(),
            )
            for m in profile.members
        )

        # Build parent_of edges: every parent → every child.
        parents = [m for m in profile.members if m.relation.lower() == "parent"]
        children = [m for m in profile.members if m.relation.lower() == "child"]
        edges: List[SpaceEdge] = []
        for parent in parents:
            for child in children:
                edges.append(
                    SpaceEdge(
                        from_member=parent.actor_id,
                        to_member=child.actor_id,
                        kind="parent_of",
                        weight=1.0,
                    )
                )

        # Build coparent_of edges: every parent pair is mutually adjacent.
        # Without these edges, SpaceGraphService._filter_adjacent_edges drops
        # the other parent from any guardian actor's view, so the visible
        # space block would only ever list one parent + the children. See
        # k1/selfmodel/service/space_graph.py L181-L188.
        for i, p1 in enumerate(parents):
            for p2 in parents[i + 1:]:
                edges.append(
                    SpaceEdge(
                        from_member=p1.actor_id,
                        to_member=p2.actor_id,
                        kind="coparent_of",
                        weight=1.0,
                    )
                )
                edges.append(
                    SpaceEdge(
                        from_member=p2.actor_id,
                        to_member=p1.actor_id,
                        kind="coparent_of",
                        weight=1.0,
                    )
                )

        # Build sibling_of edges: every child pair is mutually adjacent so
        # children-rendered prompts see all their siblings, not just one.
        for i, c1 in enumerate(children):
            for c2 in children[i + 1:]:
                edges.append(
                    SpaceEdge(
                        from_member=c1.actor_id,
                        to_member=c2.actor_id,
                        kind="sibling_of",
                        weight=1.0,
                    )
                )
                edges.append(
                    SpaceEdge(
                        from_member=c2.actor_id,
                        to_member=c1.actor_id,
                        kind="sibling_of",
                        weight=1.0,
                    )
                )

        # Build child_of edges (reverse of parent_of) so children-rendered
        # prompts see all parents in their visible-space block.
        for parent in parents:
            for child in children:
                edges.append(
                    SpaceEdge(
                        from_member=child.actor_id,
                        to_member=parent.actor_id,
                        kind="child_of",
                        weight=1.0,
                    )
                )

        # Household-wide mesh: ensure every member is adjacent to every other
        # member with a generic ``household_member`` edge. This covers
        # extended-family roles (grandparent, aunt/uncle, caregiver) that the
        # parent/child/sibling typed edges above do not connect. Without this
        # mesh, _filter_adjacent_edges drops anyone whose relation does not
        # map to one of the four typed kinds, and they vanish from the
        # per-actor visible-space block even though the constitution permits
        # the viewer to see them. Skip pairs already covered by a typed edge.
        existing_pairs = {
            (e.from_member, e.to_member) for e in edges
        }
        all_members = list(profile.members)
        for i, m1 in enumerate(all_members):
            for m2 in all_members[i + 1:]:
                if (m1.actor_id, m2.actor_id) not in existing_pairs:
                    edges.append(
                        SpaceEdge(
                            from_member=m1.actor_id,
                            to_member=m2.actor_id,
                            kind="household_member",
                            weight=0.5,
                        )
                    )
                if (m2.actor_id, m1.actor_id) not in existing_pairs:
                    edges.append(
                        SpaceEdge(
                            from_member=m2.actor_id,
                            to_member=m1.actor_id,
                            kind="household_member",
                            weight=0.5,
                        )
                    )

        snapshot = SpaceGraphSnapshot(
            space_id=space_id,
            revision=rev,
            members=members_tuple,
            relations=tuple(edges),
            routines=(),
            composed_at_ms=now_ms,
        )

        result = store.write_space(snapshot, writer_id=SPACE_GRAPH_WRITER_ID)
        accepted = getattr(result, "accepted", True)
        if not accepted:
            reason = getattr(result, "reason", "<unknown>")
            raise RuntimeError(f"write_space rejected: {reason}")
        logger.info(
            "seed_space_projection: wrote SpaceGraphSnapshot space='%s' members=%d edges=%d",
            space_id,
            len(members_tuple),
            len(edges),
        )
        return True

    def seed_self_projections(
        self,
        bundle: Any,
        profile: FamilyProfile,
        *,
        extra_actor_ids: Optional[List[str]] = None,
    ) -> int:
        """Seed a minimal ``K1SelfModelSnapshot`` for every family member actor.

        Also seeds any ``extra_actor_ids`` (e.g. the ephemeral web session
        actor such as ``actor:web-901fe489``) so the policy gate can compose
        a SituationFrame without raising ``UnknownActorError``.

        Idempotent: skips actors that already have a stored snapshot.
        Returns the count of newly written entries.
        """
        if bundle is None:
            raise ValueError("seed_self_projections requires a SelfModelServiceBundle")

        self_model = getattr(bundle, "self_model", None)
        if self_model is None:
            raise ValueError("SelfModelServiceBundle has no 'self_model' attribute")

        now_ms = int(time.time() * 1000)
        written = 0

        actor_ids: List[str] = [m.actor_id for m in profile.members]
        if extra_actor_ids:
            actor_ids += [a for a in extra_actor_ids if a not in actor_ids]

        for actor_id in actor_ids:
            if not actor_id:
                continue
            existing, _ = self_model._store.read_self(actor_id)
            # Skip only if existing snapshot already has L3 data (rich seed)
            if existing is not None and existing.L3_pattern:
                continue
            member = next((m for m in profile.members if m.actor_id == actor_id), None)
            l1: dict = {"actor_id": actor_id}
            l2: dict = {}
            l3: dict = {}
            if member is not None:
                selfmodel_role = member.role()
                l1["display_name"] = member.name
                l1["role"] = selfmodel_role
                l1["consent_posture"] = {
                    "family": [
                        "display_name",
                        "role",
                        "role_in_family",
                        "age_band",
                        "preferences",
                        "schedule_summary",
                    ]
                }
                if member.age:
                    l1["age"] = member.age
                if member.occupation:
                    l1["occupation"] = member.occupation
                l2["role_in_family"] = selfmodel_role
                l2["family_relation"] = member.relation
                if member.age_band() != "unknown":
                    l2["age_band"] = member.age_band()
                # L3: rich profile data that fills [preferences]/[hobbies]/[space] blocks
                if member.preferences:
                    # Stringify values so capsule builder can render them safely
                    l3["preferences"] = {k: str(v) for k, v in member.preferences.items()}
                if getattr(member, "hobbies", None):
                    l3["hobbies"] = list(member.hobbies)
                if getattr(member, "likes", None):
                    l3["likes"] = list(member.likes)
                if getattr(member, "dislikes", None):
                    l3["dislikes"] = list(member.dislikes)
                # Family members visible to this actor
                others = [
                    {
                        "member_id": m.actor_id,
                        "display_name": m.name,
                        "role": m.relation,
                        "aliases": list(getattr(m, "aliases", []) or []),
                    }
                    for m in profile.members
                    if m.actor_id != actor_id
                ]
                if others:
                    l3["family_members"] = others
                # Also surface the active actor's own aliases (for use by
                # the [actor] / [self] capsule renderers).
                if getattr(member, "aliases", None):
                    l3["aliases"] = list(member.aliases)
            snapshot = K1SelfModelSnapshot(
                actor_id=actor_id,
                L1_core=l1,
                L2_identity=l2,
                L3_pattern=l3,
                composed_at_ms=now_ms,
            )
            self_model._store.write_self(snapshot, writer_id=SELF_MODEL_WRITER_ID)
            written += 1
            logger.info("seed_self_projections: seeded actor_id=%s", actor_id)

        return written

    # ------------------------------------------------------------------
    # L3 — K0 Episodic seed (M14 hook)
    # ------------------------------------------------------------------
    async def seed_k0_memories(
        self,
        bridge_command_port: Optional[Any],
        profile: FamilyProfile,
    ) -> int:
        """Submit profile memories to K0 via the bridge. No-op if bridge is None.

        Returns count of envelopes submitted (0 when offline).
        """
        if bridge_command_port is None:
            logger.info("seed_k0_memories: bridge offline — skipping (M14 hook)")
            return 0
        submit = getattr(bridge_command_port, "submit_batch", None)
        if submit is None:
            logger.warning("seed_k0_memories: bridge has no submit_batch — skipping")
            return 0
        envelopes = [e.to_seed_dict() for e in profile.memories]
        result = submit(envelopes)
        if inspect.isawaitable(result):  # pragma: no cover — async bridge
            await result
        logger.info("seed_k0_memories: submitted %d envelopes", len(envelopes))
        return len(envelopes)


__all__ = ["SpaceDataSeeder"]
