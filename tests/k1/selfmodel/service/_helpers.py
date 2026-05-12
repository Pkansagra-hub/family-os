"""Shared builders for ``k1.selfmodel`` service / invariant / perf tests.

These are NOT pytest fixtures (the codebase prefers plain helpers per
the existing concierge / sessionstate test style — see
``tests/k1/concierge/test_session_delta.py``). Kept pure so they can be
composed inline in any test.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from k1.selfmodel.adapters.memory_projection_store import InMemoryProjectionStore
from k1.selfmodel.contracts.constitution import (
    ConstitutionSnapshot,
    SigningProof,
)
from k1.selfmodel.contracts.self_model import K1SelfModelSnapshot
from k1.selfmodel.contracts.space_graph import (
    FamilyMemberRef,
    FamilySelfModelSnapshot,
    RelationshipEdge,
    RoutineRef,
)
from k1.selfmodel.service.constitution import ConstitutionService
from k1.selfmodel.service.self_model import (
    SELF_MODEL_WRITER_ID,
    SelfModelService,
)
from k1.selfmodel.service.situation_composer import SituationFrameComposer
from k1.selfmodel.service.space_graph import (
    SPACE_GRAPH_WRITER_ID,
    SpaceGraphService,
)

T0_MS = 1_700_000_000_000  # fixed 2023-11-14 epoch ms; never time.time()
DEFAULT_FAMILY_SPACE = "fs:home_household"
DEFAULT_CONSTITUTION_ID = "c:home_household:v0"


# ---------------------------------------------------------------------
# Snapshot builders
# ---------------------------------------------------------------------
def make_actor(
    actor_id: str,
    *,
    role: str = "guardian",
    name: str = "Aanya",
    age_band: str = "adult",
    consent_family: tuple[str, ...] = ("name", "role_in_family", "age_band"),
    extra_l1: dict[str, object] | None = None,
    extra_l2: dict[str, object] | None = None,
    extra_l3: dict[str, object] | None = None,
    extra_l4: dict[str, object] | None = None,
    extra_l5: dict[str, object] | None = None,
) -> K1SelfModelSnapshot:
    l1: dict[str, object] = {
        "actor_id": actor_id,
        "name": name,
        "age_band": age_band,
        "consent_posture": {"family": list(consent_family)},
    }
    if extra_l1:
        l1.update(extra_l1)
    l2: dict[str, object] = {"role_in_family": role}
    if extra_l2:
        l2.update(extra_l2)
    return K1SelfModelSnapshot(
        actor_id=actor_id,
        L1_core=l1,
        L2_identity=l2,
        L3_pattern=dict(extra_l3 or {}),
        L4_context=dict(extra_l4 or {}),
        L5_state=dict(extra_l5 or {}),
        composed_at_ms=T0_MS,
    )


def make_family(
    *,
    space_id: str = DEFAULT_FAMILY_SPACE,
    members: tuple[FamilyMemberRef, ...] = (),
    edges: tuple[RelationshipEdge, ...] = (),
    routines: tuple[RoutineRef, ...] = (),
) -> FamilySelfModelSnapshot:
    return FamilySelfModelSnapshot(
        space_id=space_id,
        members=members,
        relations=edges,
        routines=routines,
        composed_at_ms=T0_MS,
    )


def make_member(
    member_id: str, *, role: str = "child", name: str = "", age_band: str = ""
) -> FamilyMemberRef:
    return FamilyMemberRef(
        member_id=member_id,
        display_name=name or member_id,
        role=role,
        age_band=age_band,
    )


def make_constitution(
    *,
    body: dict[str, object] | None = None,
    constitution_id: str = DEFAULT_CONSTITUTION_ID,
    version: str = "v0",
    signed: bool = True,
) -> ConstitutionSnapshot:
    sigs: tuple[SigningProof, ...] = ()
    if signed:
        sigs = (
            SigningProof(
                signer_id="bootstrap:system",
                key_id="did:device:hub#0",
                signature_b64="stub-system-sig",
                signed_at_ms=T0_MS,
            ),
        )
    return ConstitutionSnapshot(
        constitution_id=constitution_id,
        version=version,
        body=body or {},
        signatures=sigs,
        activated_at_ms=T0_MS,
    )


# ---------------------------------------------------------------------
# V0 default body — used as a baseline; tests may merge/override.
# ---------------------------------------------------------------------
def v0_body(
    *,
    extra_visibility: dict[str, dict[str, list[str]]] | None = None,
    extra_autonomy: dict[str, dict[str, list[str]]] | None = None,
    extra_authority: dict[str, int] | None = None,
    extra_protection: dict[str, list[str]] | None = None,
) -> dict[str, object]:
    visibility: dict[str, dict[str, list[str]]] = {
        "guardian": {
            "guardian": ["name", "role_in_family"],
            "child": ["name", "role_in_family", "age_band", "schedule"],
            "guest": ["name", "role_in_family"],
        },
        "child": {
            "guardian": ["name", "role_in_family"],
            "child": ["name"],  # siblings: name only
        },
        "guest": {
            "guardian": ["name"],
        },
    }
    if extra_visibility:
        for vk, sub in extra_visibility.items():
            visibility.setdefault(vk, {}).update(sub)

    autonomy: dict[str, dict[str, list[str]]] = {
        "guardian": {
            "can": ["recall_memory", "set_routine", "approve_request"],
            "must_ask": ["pickup_change"],
            "cannot": [],
        },
        "child": {
            "can": ["complete_chore"],
            "must_ask": ["leave_house"],
            "cannot": ["modify_constitution"],
        },
    }
    if extra_autonomy:
        for ak, sub in extra_autonomy.items():
            autonomy.setdefault(ak, {}).update(sub)

    authority: dict[str, int] = {
        "approve_request": 2,
        "set_routine": 2,
        "pickup_change": 2,
    }
    if extra_authority:
        authority.update(extra_authority)

    protection: dict[str, list[str]] = {
        "child_explicit_privacy": [
            "redact_from_siblings",
            "alert_caregiver_safety",
        ],
        "shared_hub_unknown_speaker": ["public_only_reads"],
    }
    if extra_protection:
        protection.update(extra_protection)

    return {
        "visibility_rules": visibility,
        "autonomy_rules": autonomy,
        "authority_rules": authority,
        "protection_rules": protection,
    }


# ---------------------------------------------------------------------
# Service bundle
# ---------------------------------------------------------------------
@dataclass
class Bundle:
    store: InMemoryProjectionStore
    self_model: SelfModelService
    space_graph: SpaceGraphService
    constitution: ConstitutionService
    composer: SituationFrameComposer


def build_bundle(
    *,
    actors: tuple[K1SelfModelSnapshot, ...] = (),
    family: FamilySelfModelSnapshot | None = None,
    constitution: ConstitutionSnapshot | None = None,
    space_id: str = DEFAULT_FAMILY_SPACE,
    constitution_id: str = DEFAULT_CONSTITUTION_ID,
    enforce_writer_allowlist: bool = True,
) -> Bundle:
    """Wire all four M1 services on top of an in-memory store."""
    allowed = (
        (SELF_MODEL_WRITER_ID, SPACE_GRAPH_WRITER_ID, "test:fixture")
        if enforce_writer_allowlist
        else None
    )
    store = InMemoryProjectionStore(allowed_writers=allowed)
    for actor in actors:
        store.write_self(actor, writer_id="test:fixture")
    if family is not None:
        store.write_space(family, writer_id="test:fixture")
    if constitution is not None:
        store.write_constitution(constitution, writer_id="test:fixture")

    sm = SelfModelService(store)
    fm = SpaceGraphService(store)
    cs = ConstitutionService(store, constitution_id=constitution_id)
    composer = SituationFrameComposer(
        self_model=sm,
        space_graph=fm,
        constitution=cs,
        space_id=space_id,
    )
    return Bundle(store=store, self_model=sm, space_graph=fm, constitution=cs, composer=composer)


def now_ms() -> int:
    """Stable timestamp helper (real wall-clock; tests should pass T0_MS instead)."""
    return int(time.time() * 1000)
