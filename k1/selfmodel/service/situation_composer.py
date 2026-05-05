"""``SituationFrameComposer`` — produces ``SituationFrame = S(actor) ∩ F ∩ C``.

Issue M1.E2.I1.

The composer is the only object the rest of K1 consumes from
``k1.selfmodel`` (per ``SERVICE_DESIGN_SELF_MODEL.md``). Every
Empty-Set Invariant in the V0 set is enforced HERE because the
SituationFrame is the boundary between the algebra and the rest of
the kernel:

- **E1 (consent):** every ``ProjectedSelf`` in ``relations`` is
  filtered through the *target's* own ``L1_core["consent_posture"]``
  before any visibility rule applies. No consent → no attributes.
- **E2 (default-deny visibility):** the visibility lookup uses
  ``constitution_body.get_visibility_keys(...)`` which returns ``()``
  for any missing key path. NEVER inserts wildcards.
- **E5 (no raw other_self):** ``relations.projected_others`` is built
  from ``ProjectedSelf`` instances ONLY; the only place we ever read
  another actor's full snapshot is to extract their consent posture +
  display fields, and that snapshot never escapes the function frame.
- **E6 (no tool outside capabilities):** ``Capabilities.can_do`` is
  populated solely from ``autonomy_rules[role]["can"]``; unknown roles
  get empty capabilities — the policy gate (M2) refuses any tool not
  in the resulting list.

Composition cost target (per design doc §10.3): p95 ≤ 5ms on the
in-memory store. The benchmark lives at
``tests/k1/selfmodel/perf/test_composer_bench.py``.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Mapping
from typing import Any

from k1.selfmodel.contracts import constitution_body as body_keys
from k1.selfmodel.contracts.conscience import ConscienceDigest
from k1.selfmodel.contracts.family_model import (
    FamilyMemberRef,
    RelationshipEdge,
)
from k1.selfmodel.contracts.pattern import coerce_l3
from k1.selfmodel.contracts.self_model import K1SelfModelSnapshot
from k1.selfmodel.contracts.situation import (
    ApplicableRules,
    Capabilities,
    ProjectedSelf,
    RelationsSubset,
    SelfView,
    SituationFrame,
    Visibility,
)
from k1.selfmodel.contracts.situations import is_known_situation
from k1.selfmodel.ports.projection_store import ProjectionFreshness
from k1.selfmodel.service.constitution import ConstitutionService
from k1.selfmodel.service.errors import (
    ConstitutionUnavailableError,
    UnknownActorError,
    UnknownSituationError,
)
from k1.selfmodel.service.family_model import (
    FamilyModelService,
    _adjacent_member_ids,
)
from k1.selfmodel.service.self_model import SelfModelService

__all__ = ["SituationFrameComposer"]


logger = logging.getLogger(__name__)


# Layer-3 keys NEVER projected into ProjectedSelf for OTHER actors.
# Even if a (role, target_role) visibility rule allowlists them, these
# are ALWAYS stripped because they are raw behavioural patterns.
_L3_NEVER_SHARE: frozenset[str] = frozenset(
    {
        "raw_dialogue",
        "raw_audio_features",
        "raw_keystrokes",
        "raw_location_trace",
    }
)


class SituationFrameComposer:
    """Compose ``SituationFrame`` from S(actor), F, C at ``(T, D)``.

    Stateless. Safe to share across sessions. The optional cache (per
    ``(actor_id, T_ms, device_id, situation_kind)``) is not implemented
    in M1 — the design doc reserves it for §10.3 follow-up — but the
    method is pure so a simple ``functools.lru_cache``-style wrapper
    can be bolted on later without changing semantics.
    """

    def __init__(
        self,
        *,
        self_model: SelfModelService,
        family_model: FamilyModelService,
        constitution: ConstitutionService,
        family_space_id: str,
    ) -> None:
        if not family_space_id:
            raise ValueError("family_space_id must be non-empty")
        self._self = self_model
        self._family = family_model
        self._constitution = constitution
        self._family_space_id = family_space_id

    # ------------------------------------------------------------------
    # Public surface (matches ``ISituationFramePort.compose``)
    # ------------------------------------------------------------------
    def compose(
        self,
        actor_id: str,
        T_ms: int,
        device_id: str,
        situation_kind: str,
    ) -> SituationFrame:
        if not actor_id:
            raise ValueError("actor_id must be non-empty")
        if not is_known_situation(situation_kind):
            raise UnknownSituationError(f"situation_kind={situation_kind!r} is not in the V0 set")

        # ---- Read S(actor) -----------------------------------------
        actor_read = self._self.get(actor_id)
        if actor_read is None:
            raise UnknownActorError(f"compose: actor_id={actor_id!r} not in projection store")
        actor_snapshot = actor_read.snapshot
        actor_role = _extract_role(actor_snapshot)

        # ---- Read C (active constitution) ---------------------------
        try:
            constitution_read = self._constitution.get_active()
            constitution = constitution_read.snapshot
            constitution_freshness = constitution_read.freshness
            constitution_body: Mapping[str, Any] = constitution.body
            constitution_version = constitution.version
        except ConstitutionUnavailableError:
            # Empty body → every default-deny path returns empty
            # collections. The composer still produces a SituationFrame
            # (with empty rules/caps/visibility) so downstream code can
            # observe the freshness signal and degrade gracefully.
            logger.warning("compose: constitution unavailable; producing default-deny frame")
            constitution_body = {}
            constitution_version = ""
            constitution_freshness = self._constitution.freshness()

        # ---- Read F (projected for actor) ---------------------------
        family_read = self._family.get_view(actor_id, self._family_space_id)
        family = family_read.snapshot

        # ---- Build projected_self (actor sees own L1+L2+filtered L3) -
        projected_self_dict = _build_projected_self_dict(
            actor_snapshot, constitution_body, actor_role
        )

        # ---- Build relations.projected_others (E1 ∩ E2 ∩ E5) --------
        relations = self._build_relations(
            actor_id=actor_id,
            actor_role=actor_role,
            adjacent_edges=family.relations,  # already adjacency-filtered
            members=family.members,
            constitution_body=constitution_body,
        )

        # ---- Derive ApplicableRules / Capabilities / Visibility -----
        rules = _build_applicable_rules(
            constitution_body=constitution_body,
            constitution_version=constitution_version,
            actor_role=actor_role,
            situation_kind=situation_kind,
        )
        capabilities = _build_capabilities(
            constitution_body=constitution_body, actor_role=actor_role
        )
        conscience = _build_conscience(constitution_body=constitution_body, actor_role=actor_role)
        self_view = _build_self_view(actor_snapshot, actor_role)
        visibility = _build_visibility(
            constitution_body=constitution_body,
            actor_role=actor_role,
            members=family.members,
            actor_id=actor_id,
        )

        # ---- Transient (actor's own L4/L5 ONLY — never another's) ---
        transient: dict[str, object] = {}
        if actor_snapshot.L4_context:
            transient["L4"] = dict(actor_snapshot.L4_context)
        if actor_snapshot.L5_state:
            transient["L5"] = dict(actor_snapshot.L5_state)

        # ---- Freshness signals --------------------------------------
        freshness = {
            "self": actor_read.freshness.value,
            "family": family_read.freshness.value,
            "constitution": constitution_freshness.value,
        }

        return SituationFrame(
            actor_id=actor_id,
            situation_kind=situation_kind,
            composed_at_ms=T_ms or _now_ms(),
            device_id=device_id,
            projected_self=projected_self_dict,
            self_view=self_view,
            relations=relations,
            rules=rules,
            capabilities=capabilities,
            conscience=conscience,
            visibility=visibility,
            transient=transient,
            freshness=freshness,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _build_relations(
        self,
        *,
        actor_id: str,
        actor_role: str,
        adjacent_edges: tuple[RelationshipEdge, ...],
        members: tuple[FamilyMemberRef, ...],
        constitution_body: Mapping[str, Any],
    ) -> RelationsSubset:
        if not adjacent_edges:
            return RelationsSubset()

        member_index: dict[str, FamilyMemberRef] = {m.member_id: m for m in members}
        other_ids = _adjacent_member_ids(adjacent_edges, actor_id)
        projected: list[ProjectedSelf] = []

        for other_id in other_ids:
            ref = member_index.get(other_id)
            if ref is None:
                # Edge points at a member not present in the snapshot.
                # Default-deny: skip (do NOT fabricate a placeholder).
                continue

            # E2: visibility allowlist (default-deny on missing rule).
            allowed_keys = body_keys.get_visibility_keys(
                constitution_body,
                viewer_role=actor_role,
                target_role=ref.role,
            )
            if not allowed_keys:
                continue

            # E1: target's own consent posture.
            other_read = self._self.get(other_id)
            if other_read is None:
                continue
            other_snapshot = other_read.snapshot
            consent_keys = _extract_consent_for_family(other_snapshot)
            if not consent_keys:
                continue

            # E1 ∩ E2: intersect.
            effective_keys = tuple(k for k in allowed_keys if k in consent_keys)
            if not effective_keys:
                continue

            # Build the visible_attributes payload from L1+L2+L3.
            vis_attrs = _project_visible_attributes(other_snapshot, effective_keys)
            if not vis_attrs:
                # All allowlisted keys were absent on the target.
                # Still emit a ProjectedSelf with display info so the
                # frame reflects the relationship existence — but with
                # no leak.
                projected.append(
                    ProjectedSelf(
                        member_id=ref.member_id,
                        display_name=ref.display_name,
                        role=ref.role,
                        visible_attributes={},
                    )
                )
                continue

            projected.append(
                ProjectedSelf(
                    member_id=ref.member_id,
                    display_name=ref.display_name,
                    role=ref.role,
                    visible_attributes=vis_attrs,
                )
            )

        # E5 sanity check (cheap, structural).
        for p in projected:
            assert isinstance(p, ProjectedSelf), (
                "E5 violation: relations.projected_others must contain only "
                f"ProjectedSelf instances, got {type(p).__name__}"
            )

        return RelationsSubset(
            edges=tuple(adjacent_edges),
            projected_others=tuple(projected),
        )


# ---------------------------------------------------------------------
# Module-level helpers (pure functions; no I/O)
# ---------------------------------------------------------------------
def _extract_role(snapshot: K1SelfModelSnapshot) -> str:
    """Resolve the actor's role from L2 (preferred) or L1 fallback."""
    raw = snapshot.L2_identity.get("role_in_family")
    if isinstance(raw, str) and raw:
        return raw
    raw_l1 = snapshot.L1_core.get("role")
    if isinstance(raw_l1, str) and raw_l1:
        return raw_l1
    return ""


def _extract_consent_for_family(snapshot: K1SelfModelSnapshot) -> tuple[str, ...]:
    """Read ``L1_core["consent_posture"]["family"]`` defensively.

    Default-deny: any malformed shape returns ``()``.
    """
    posture = snapshot.L1_core.get("consent_posture")
    if not isinstance(posture, Mapping):
        return ()
    raw = posture.get(body_keys.CONSENT_AUDIENCE_FAMILY)
    if not isinstance(raw, (list, tuple, set, frozenset)):
        return ()
    return tuple(str(k) for k in raw)


def _project_visible_attributes(
    snapshot: K1SelfModelSnapshot, allowed_keys: tuple[str, ...]
) -> dict[str, object]:
    """Copy allowlisted keys from L1+L2+filtered L3 only."""
    out: dict[str, object] = {}
    for key in allowed_keys:
        if key in snapshot.L1_core:
            out[key] = snapshot.L1_core[key]
            continue
        if key in snapshot.L2_identity:
            out[key] = snapshot.L2_identity[key]
            continue
        if key in snapshot.L3_pattern and key not in _L3_NEVER_SHARE:
            out[key] = snapshot.L3_pattern[key]
            continue
        # E5: NEVER copy from L4/L5 of OTHER actors.
        # Missing key → default-deny (omitted).
    return out


def _build_projected_self_dict(
    snapshot: K1SelfModelSnapshot,
    constitution_body: Mapping[str, Any],
    actor_role: str,
) -> dict[str, object]:
    """The actor's view of self.

    An actor always sees their own L1+L2 in full. L3 is filtered through
    the actor's own visibility rule against themselves (the "self-self"
    visibility entry), defaulting to the union of L3 keys absent from
    ``_L3_NEVER_SHARE`` if no self-self rule exists. L4/L5 are placed on
    ``SituationFrame.transient`` separately, never here.
    """
    out: dict[str, object] = {}
    out.update(snapshot.L1_core)
    out.update(snapshot.L2_identity)

    # Self-self visibility allowlist (optional; absence = include all
    # safe L3 keys, since the actor is always allowed to see their own
    # patterns).
    self_self_keys = body_keys.get_visibility_keys(
        constitution_body, viewer_role=actor_role, target_role=actor_role
    )
    if self_self_keys:
        for k in self_self_keys:
            if k in snapshot.L3_pattern and k not in _L3_NEVER_SHARE:
                out[k] = snapshot.L3_pattern[k]
    else:
        for k, v in snapshot.L3_pattern.items():
            if k not in _L3_NEVER_SHARE:
                out[k] = v
    return out


def _build_applicable_rules(
    *,
    constitution_body: Mapping[str, Any],
    constitution_version: str,
    actor_role: str,
    situation_kind: str,
) -> ApplicableRules:
    """Collect rule_ids that match (actor_role, situation_kind).

    Sources (in order of precedence — later overrides earlier in the
    output ordering only, never in the truth value):

    1. ``protection_rules[situation_kind]`` — situation-scoped
    2. ``autonomy_rules[role][can|must_ask|cannot]`` keys — role-scoped
       (the *tool ids* themselves count as rule_ids for the policy gate
       to inspect; this gives M2 a single iteration source)
    """
    collected: list[str] = []
    seen: set[str] = set()

    for rid in body_keys.get_protection_rules(constitution_body, situation_kind=situation_kind):
        if rid not in seen:
            seen.add(rid)
            collected.append(rid)

    for bucket in (
        body_keys.AUTONOMY_CAN,
        body_keys.AUTONOMY_MUST_ASK,
        body_keys.AUTONOMY_CANNOT,
    ):
        for tool_id in body_keys.get_autonomy_bucket(
            constitution_body, role=actor_role, bucket=bucket
        ):
            rid = f"autonomy:{bucket}:{tool_id}"
            if rid not in seen:
                seen.add(rid)
                collected.append(rid)

    return ApplicableRules(
        rule_ids=tuple(collected),
        constitution_version=constitution_version,
    )


def _build_capabilities(*, constitution_body: Mapping[str, Any], actor_role: str) -> Capabilities:
    can = body_keys.get_autonomy_bucket(
        constitution_body, role=actor_role, bucket=body_keys.AUTONOMY_CAN
    )
    must_ask = body_keys.get_autonomy_bucket(
        constitution_body, role=actor_role, bucket=body_keys.AUTONOMY_MUST_ASK
    )
    requires_tier: dict[str, int] = {}
    for tool_id in (*can, *must_ask):
        tier = body_keys.get_authority_tier(constitution_body, tool_id=tool_id)
        if tier > 0:
            requires_tier[tool_id] = tier
    return Capabilities(
        can_do=can,
        requires_confirmation=must_ask,
        requires_identity_tier=requires_tier,
    )


def _build_conscience(*, constitution_body: Mapping[str, Any], actor_role: str) -> ConscienceDigest:
    """Compose ``ConscienceDigest`` for the actor (M6.E3).

    Always emits a digest (never ``None``) so the M8 policy gate can
    rely on its presence. For the legacy v0 schema the bucket is
    derived from ``autonomy_rules``; for v1 it is read natively.
    Default-allow: only forbidden/must_ask/risk-overridden acts are
    listed.
    """
    bucket = body_keys.get_conscience_bucket(constitution_body, role=actor_role)
    return ConscienceDigest(
        forbidden_acts=bucket.forbidden,
        must_ask_acts=bucket.must_ask,
        soft_warn_acts=bucket.soft_warn,  # M14.E1.I1
        risk_overrides=dict(bucket.risk_overrides),
        protections=(),
        tier_floor=dict(bucket.tier_floor),
    )


def _build_self_view(snapshot: K1SelfModelSnapshot, actor_role: str) -> SelfView:
    """Project the actor's typed self-view (M7.E2).

    Pulls L1 display fields and the typed L3 pattern (via
    ``coerce_l3``) so the capsule renderer can surface them under
    ``[self]/[preferences]/[hobbies]/[goals]/[routines]/[context]``
    blocks. L4/L5 are intentionally excluded — they live on
    ``SituationFrame.transient``.
    """
    l1 = snapshot.L1_core
    l2 = snapshot.L2_identity
    pattern = coerce_l3(snapshot.L3_pattern)
    return SelfView(
        actor_id=snapshot.actor_id,
        display_name=str(l1.get("display_name") or l1.get("name") or ""),
        role=actor_role,
        age_band=str(l2.get("age_band") or ""),
        language=str(l2.get("language") or l1.get("language") or ""),
        pronouns=str(l2.get("pronouns") or ""),
        communication_style=pattern.communication_style,
        preferences=dict(pattern.preferences),
        hobbies=pattern.hobbies,
        likes=pattern.likes,
        dislikes=pattern.dislikes,
        goals=pattern.goals,
        routines=pattern.routines,
        habits=pattern.habits,
    )


def _build_visibility(
    *,
    constitution_body: Mapping[str, Any],
    actor_role: str,
    members: tuple[FamilyMemberRef, ...],
    actor_id: str,
) -> Visibility:
    """Per-member visibility map for the actor (E2 default-deny)."""
    can_see_members: list[str] = []
    can_see_attrs: dict[str, tuple[str, ...]] = {}
    for m in members:
        if m.member_id == actor_id:
            continue
        keys = body_keys.get_visibility_keys(
            constitution_body, viewer_role=actor_role, target_role=m.role
        )
        if keys:
            can_see_members.append(m.member_id)
            can_see_attrs[m.member_id] = keys
    return Visibility(
        can_see_members=tuple(can_see_members),
        can_see_attributes=can_see_attrs,
    )


def _now_ms() -> int:
    return int(time.time() * 1000)


# Suppress the unused-import lint while we keep the type around for
# the public surface narrative.
_ = ProjectionFreshness
