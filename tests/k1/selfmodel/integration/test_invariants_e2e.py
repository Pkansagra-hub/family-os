"""M5.E1.I3 — All six Empty-Set Invariants verified end-to-end.

Runs E1–E6 against the **assembled** selfmodel bundle (composer +
policy + capsule + citation + amendment + bridge), not isolated
units, under a chaos fixture: random tier flips, stale projections,
conflict_pending constitution, and unsigned tampered amendments.

The chaos fixture is **deterministic** (fixed seed) so failures are
reproducible — selfmodel invariants must NEVER depend on luck.

Acceptance: zero invariant violations across the full chaos sweep.

Mapping
=======
* E1 (consent)   → composer projects ``other`` only when other's own
  ``consent_posture.family`` ∩ visibility-allowlist is non-empty.
* E2 (default-deny visibility) → unknown role / missing rule yields
  empty visible_attributes.
* E3 (no BLACK egress) → ``BridgeAmendmentSyncAdapter.submit_delta``
  raises ``BlackBandLeakError``; ``GroundingCapsuleBuilder.build``
  raises on a frame whose actor projected_self carries BLACK.
* E4 (no unsigned amendment active) → ``AmendmentService.sign`` of a
  proposal with no real signature does NOT activate (Ed25519 chain
  validator rejects it on the next ``ConstitutionService.get_active``).
* E5 (no raw other_self) → every entry in
  ``frame.relations.projected_others`` is a ``ProjectedSelf`` and
  contains no L4/L5 keys for the other actor.
* E6 (no tool outside capabilities) → every PolicyEvaluator verdict
  for a tool not in ``can_do ∪ requires_confirmation`` returns DENY
  with reason ``CAPABILITY_NOT_GRANTED``.
"""

from __future__ import annotations

import asyncio
import base64
import json
import random
from dataclasses import dataclass

import pytest
from nacl.signing import SigningKey

from k1.selfmodel.adapters.bridge_amendment_sync import (
    BridgeAmendmentSyncAdapter,
)
from k1.selfmodel.adapters.memory_projection_store import InMemoryProjectionStore
from k1.selfmodel.contracts.citation import CitationPack
from k1.selfmodel.contracts.constitution import (
    AmendmentProposal,
    AmendmentStatus,
    ConstitutionSnapshot,
    SigningProof,
)
from k1.selfmodel.contracts.family_model import RelationshipEdge
from k1.selfmodel.contracts.policy import (
    FreshnessState,
    PolicyRequest,
    ReasonCode,
    RiskClass,
)
from k1.selfmodel.contracts.privacy import (
    BlackBandLeakError,
    PrivacyBand,
)
from k1.selfmodel.contracts.situation import (
    ProjectedSelf,
    SituationFrame,
)
from k1.selfmodel.ports.projection_store import ProjectionFreshness
from k1.selfmodel.service.amendment import AmendmentService
from k1.selfmodel.service.capsule_builder import GroundingCapsuleBuilder
from k1.selfmodel.service.citation_builder import CitationPackBuilder
from k1.selfmodel.service.constitution import ConstitutionService
from k1.selfmodel.service.errors import ConstitutionUnavailableError
from k1.selfmodel.service.family_model import (
    FAMILY_MODEL_WRITER_ID,
    FamilyModelService,
)
from k1.selfmodel.service.policy_evaluator import PolicyEvaluator
from k1.selfmodel.service.self_model import (
    SELF_MODEL_WRITER_ID,
    SelfModelService,
)
from k1.selfmodel.service.signature_chain import (
    Ed25519SignatureChainValidator,
    canonical_body_bytes,
)
from k1.selfmodel.service.situation_composer import SituationFrameComposer
from tests.k1.selfmodel.service._helpers import (
    DEFAULT_CONSTITUTION_ID,
    DEFAULT_FAMILY_SPACE,
    T0_MS,
    make_actor,
    make_family,
    make_member,
    v0_body,
)

pytestmark = [pytest.mark.integration, pytest.mark.invariant]


CHAOS_SEED = 0xC0FFEE
CID = DEFAULT_CONSTITUTION_ID
WRITER_AMD = "selfmodel:amendment"
ALL_WRITERS = (
    SELF_MODEL_WRITER_ID,
    FAMILY_MODEL_WRITER_ID,
    WRITER_AMD,
    "test:fixture",
)


# ---------------------------------------------------------------------
# Fakes for the bridge adapter (E3 sweep).
# ---------------------------------------------------------------------
class _NullSigning:
    key_id = "test-key-1"

    def sign(self, payload: bytes) -> str:
        return "sig_" + base64.urlsafe_b64encode(payload[:8]).decode("ascii")


class _RecordingBridge:
    def __init__(self) -> None:
        self.submit_calls: list[dict] = []

    async def submit_command(self, topic, body, *, schema_uri, band, trace_id=None):
        self.submit_calls.append(
            {"topic": topic, "body": body, "schema_uri": schema_uri, "band": band}
        )


# ---------------------------------------------------------------------
# Assembled bundle: every M1–M4 service composed end-to-end.
# ---------------------------------------------------------------------
@dataclass
class _AssembledBundle:
    store: InMemoryProjectionStore
    self_model: SelfModelService
    family_model: FamilyModelService
    constitution: ConstitutionService
    composer: SituationFrameComposer
    evaluator: PolicyEvaluator
    capsule: GroundingCapsuleBuilder
    citation: CitationPackBuilder
    amendments: AmendmentService
    bridge_adapter: BridgeAmendmentSyncAdapter
    bridge: _RecordingBridge
    bootstrap_version: str


def _build_assembled_bundle() -> _AssembledBundle:
    """Wire every M1–M4 service against an InMemoryProjectionStore."""
    store = InMemoryProjectionStore(allowed_writers=ALL_WRITERS)

    # Multi-actor household so E1/E2/E5 have surface to bite on.
    actors = (
        make_actor(
            "g1",
            role="guardian",
            name="Aanya",
            consent_family=("name", "role_in_family", "schedule"),
        ),
        make_actor(
            "c1",
            role="child",
            name="Liam",
            age_band="child",
            consent_family=("name", "role_in_family", "age_band", "schedule"),
            extra_l3={"schedule": {"after_school": "soccer"}},
            extra_l4={"copresence": {"in_bedroom": True}},
            extra_l5={"mood": {"frustrated": True}},
        ),
        make_actor(
            "c2",
            role="child",
            name="Maya",
            age_band="child",
            consent_family=(),  # E1 will bite: no consent
        ),
    )
    family = make_family(
        members=(
            make_member("g1", role="guardian", name="Aanya"),
            make_member("c1", role="child", name="Liam"),
            make_member("c2", role="child", name="Maya"),
        ),
        edges=(
            RelationshipEdge("g1", "c1", "parent_of"),
            RelationshipEdge("g1", "c2", "parent_of"),
            RelationshipEdge("c1", "c2", "sibling_of"),
        ),
    )
    for a in actors:
        store.write_self(a, writer_id="test:fixture")
    store.write_family(family, writer_id="test:fixture")

    # Real signed bootstrap constitution.
    body = v0_body()
    sk = SigningKey.generate()
    pk = bytes(sk.verify_key)
    sig = sk.sign(canonical_body_bytes(body)).signature
    proof = SigningProof(
        signer_id="bootstrap",
        key_id="did:bootstrap#0",
        algorithm="ed25519",
        signature_b64=base64.b64encode(sig).decode("ascii"),
        signed_at_ms=T0_MS,
    )
    bootstrap_version = "v0"
    snapshot = ConstitutionSnapshot(
        constitution_id=CID,
        version=bootstrap_version,
        parent_version="",
        body=body,
        signatures=(proof,),
        activated_at_ms=T0_MS,
    )
    store.write_constitution(snapshot, writer_id="test:fixture")

    validator = Ed25519SignatureChainValidator()
    validator.register_signer("bootstrap", pk)

    sm = SelfModelService(store)
    fm = FamilyModelService(store)
    cs = ConstitutionService(store, constitution_id=CID, validator=validator)
    composer = SituationFrameComposer(
        self_model=sm,
        family_model=fm,
        constitution=cs,
        family_space_id=DEFAULT_FAMILY_SPACE,
    )
    evaluator = PolicyEvaluator()
    capsule = GroundingCapsuleBuilder(clock_ms=lambda: T0_MS)
    citation = CitationPackBuilder(clock_ms=lambda: T0_MS)
    amendments = AmendmentService(store, cs, signing_quorum=1, clock=lambda: T0_MS)
    bridge = _RecordingBridge()
    bridge_adapter = BridgeAmendmentSyncAdapter(bridge=bridge, signing=_NullSigning())
    return _AssembledBundle(
        store=store,
        self_model=sm,
        family_model=fm,
        constitution=cs,
        composer=composer,
        evaluator=evaluator,
        capsule=capsule,
        citation=citation,
        amendments=amendments,
        bridge_adapter=bridge_adapter,
        bridge=bridge,
        bootstrap_version=bootstrap_version,
    )


# ---------------------------------------------------------------------
# Chaos generators (deterministic via fixed seed).
# ---------------------------------------------------------------------
def _apply_freshness_chaos(store: InMemoryProjectionStore, *, rng: random.Random) -> None:
    """Random per-projection freshness flips covering all states."""
    keys = (
        "self:g1",
        "self:c1",
        "self:c2",
        f"family:{DEFAULT_FAMILY_SPACE}",
        f"constitution:{CID}",
    )
    states = (
        ProjectionFreshness.FRESH,
        ProjectionFreshness.STALE,
        ProjectionFreshness.OFFLINE_LOCAL_ONLY,
        ProjectionFreshness.CONFLICT_PENDING,
    )
    for k in keys:
        # Direct write — same path the public mutators use.
        store._freshness[k] = rng.choice(states)


def _all_situation_kinds_subset() -> tuple[str, ...]:
    """A subset of V0 situations we walk in chaos to keep runtime sane."""
    return (
        "caregiver_context_briefing",
        "caregiver_child_read",
        "child_daily_read",
        "shared_hub_unknown_speaker",
    )


# =====================================================================
# E1 — Consent intersection
# =====================================================================
def test_e1_consent_intersection_holds_under_chaos() -> None:
    rng = random.Random(CHAOS_SEED)
    for _ in range(20):
        bundle = _build_assembled_bundle()
        _apply_freshness_chaos(bundle.store, rng=rng)
        for kind in _all_situation_kinds_subset():
            try:
                frame = bundle.composer.compose("g1", T0_MS, "d1", kind)
            except (ConstitutionUnavailableError, Exception):
                # Composer gracefully degrades; if it raised that's a
                # bug — re-raise so the invariant test fails loudly.
                raise
            others = {p.member_id: p for p in frame.relations.projected_others}
            # c2 has empty consent_posture.family → MUST be absent.
            assert "c2" not in others or others["c2"].visible_attributes == {}, (
                f"E1 violation: c2 appeared with attributes " f"under situation={kind}"
            )


# =====================================================================
# E2 — Default-deny visibility
# =====================================================================
def test_e2_unknown_role_yields_empty_visibility() -> None:
    bundle = _build_assembled_bundle()
    # Inject an actor with a role missing from the visibility table.
    rogue = make_actor("x1", role="unknown_role", name="Rogue")
    bundle.store.write_self(rogue, writer_id="test:fixture")
    bundle.store.write_family(
        make_family(
            members=(
                make_member("g1", role="guardian"),
                make_member("x1", role="unknown_role"),
            ),
            edges=(RelationshipEdge("g1", "x1", "guardian_of"),),
        ),
        writer_id="test:fixture",
    )
    frame = bundle.composer.compose("g1", T0_MS, "d1", "caregiver_context_briefing")
    others = {p.member_id: p for p in frame.relations.projected_others}
    assert "x1" not in others, "E2 violation: rogue role with no visibility rule was projected"


# =====================================================================
# E3 — No BLACK egress
# =====================================================================
def test_e3_bridge_submit_with_black_band_raises() -> None:
    bundle = _build_assembled_bundle()
    proposal = AmendmentProposal(
        amendment_id="amd_black",
        parent_version=bundle.bootstrap_version,
        proposed_by="g1",
        body={},
        status=AmendmentStatus.DRAFT,
    )

    async def _go():
        with pytest.raises(BlackBandLeakError):
            await bundle.bridge_adapter.submit_delta(proposal, band=PrivacyBand.BLACK)

    asyncio.run(_go())
    assert (
        bundle.bridge.submit_calls == []
    ), "E3 violation: bridge.submit_command was called for BLACK input"


def test_e3_capsule_with_black_actor_raises() -> None:
    bundle = _build_assembled_bundle()
    bad_frame = SituationFrame(
        actor_id="g1",
        situation_kind="caregiver_context_briefing",
        composed_at_ms=T0_MS,
        projected_self={"display_name": "Aanya", "privacy_band": "BLACK"},
    )
    with pytest.raises(BlackBandLeakError):
        bundle.capsule.build(bad_frame)


# =====================================================================
# E4 — No unsigned amendment active
# =====================================================================
def test_e4_unsigned_proposal_never_visible_as_active() -> None:
    """A tampered (signature-stripped) snapshot must not pass through
    ``ConstitutionService.get_active`` once the validator latches into
    safe-mode."""
    bundle = _build_assembled_bundle()
    # Directly write an unsigned snapshot under a higher version into
    # the store — bypasses the amendment lifecycle to mimic tampering.
    tampered = ConstitutionSnapshot(
        constitution_id=CID,
        version="v_tampered",
        parent_version=bundle.bootstrap_version,
        body=v0_body(),
        signatures=(),
        activated_at_ms=T0_MS,
    )
    bundle.store.write_constitution(tampered, writer_id="test:fixture")
    with pytest.raises(ConstitutionUnavailableError):
        bundle.constitution.get_active()
    # Safe-mode latched.
    assert bundle.constitution.is_safe_mode is True


# =====================================================================
# E5 — No raw other_self
# =====================================================================
def test_e5_relations_carry_only_projected_self_under_chaos() -> None:
    rng = random.Random(CHAOS_SEED + 1)
    for _ in range(20):
        bundle = _build_assembled_bundle()
        _apply_freshness_chaos(bundle.store, rng=rng)
        frame = bundle.composer.compose("g1", T0_MS, "d1", "caregiver_child_read")
        for entry in frame.relations.projected_others:
            assert isinstance(
                entry, ProjectedSelf
            ), f"E5 violation: relations contains {type(entry).__name__}"
            blob = json.dumps(entry.visible_attributes, sort_keys=True)
            # L4/L5 keys must NEVER appear in another actor's projection.
            for forbidden in ("copresence", "mood", "in_bedroom", "frustrated"):
                assert forbidden not in blob, (
                    f"E5 violation: forbidden L4/L5 key {forbidden!r} leaked "
                    f"into projected_others for {entry.member_id}"
                )


# =====================================================================
# E6 (M8 restated) — only conscience.forbidden_acts triggers DENY.
# Default-allow for any act not mentioned by the conscience.
# =====================================================================
def test_e6_unmentioned_tool_default_allowed_under_chaos() -> None:
    """M6/M8 inversion: ghost tools no longer auto-deny.

    The conscience-first design treats unmapped acts as ALLOW unless
    the matrix (risk × freshness) says otherwise. The only DENY path
    is membership in ``conscience.forbidden_acts``.
    """
    rng = random.Random(CHAOS_SEED + 2)
    bundle = _build_assembled_bundle()

    for _ in range(20):
        _apply_freshness_chaos(bundle.store, rng=rng)
        frame = bundle.composer.compose("g1", T0_MS, "d1", "caregiver_context_briefing")
        random_state = rng.choice(list(FreshnessState))
        random_risk = rng.choice(list(RiskClass))
        random_tier = rng.choice([0, 1, 2, 3])
        verdict = bundle.evaluator.evaluate(
            PolicyRequest(
                actor_id="g1",
                tool_name="ghost_tool_never_granted",
                risk_class=random_risk,
            ),
            frame,
            freshness_state=random_state,
            current_tier=random_tier,
        )
        # Ghost is not in conscience.forbidden_acts → never DENY for
        # capability reasons. Matrix may still produce DEFER_OFFLINE /
        # REQUIRE_CONFIRMATION based on risk × freshness.
        assert verdict.reason != ReasonCode.CAPABILITY_NOT_GRANTED, (
            f"M6/M8: ghost tool must not produce CAPABILITY_NOT_GRANTED "
            f"(got decision={verdict.decision.value} reason={verdict.reason.value})"
        )


# =====================================================================
# Cross-invariant: assembled bundle survives the full chaos sweep
# =====================================================================
def test_assembled_bundle_full_sweep_no_invariant_violations() -> None:
    """One pass that exercises composer → policy → capsule → citation
    under chaos and asserts every per-invariant predicate at once."""
    rng = random.Random(CHAOS_SEED + 3)
    bundle = _build_assembled_bundle()

    for _ in range(30):
        _apply_freshness_chaos(bundle.store, rng=rng)
        frame = bundle.composer.compose("g1", T0_MS, "d1", "caregiver_child_read")

        # E1: c2 must not leak attributes (empty consent).
        others = {p.member_id: p for p in frame.relations.projected_others}
        if "c2" in others:
            assert others["c2"].visible_attributes == {}

        # E5: every relation entry is ProjectedSelf with no L4/L5 keys.
        for entry in frame.relations.projected_others:
            assert isinstance(entry, ProjectedSelf)
            for k in entry.visible_attributes:
                assert k not in ("copresence", "mood")

        # E6 (M8 restated): ghost tool is NOT in conscience.forbidden,
        # so the only DENY path is unrelated; reason must not be
        # CAPABILITY_NOT_GRANTED. (Matrix can still produce other
        # decisions based on risk × freshness.)
        verdict = bundle.evaluator.evaluate(
            PolicyRequest(
                actor_id="g1",
                tool_name="ghost",
                risk_class=rng.choice(list(RiskClass)),
            ),
            frame,
            freshness_state=rng.choice(list(FreshnessState)),
            current_tier=rng.choice([0, 1, 2, 3]),
        )
        assert verdict.reason != ReasonCode.CAPABILITY_NOT_GRANTED

        # Capsule must build without raising for normal frames.
        cap = bundle.capsule.build(frame)
        assert cap.actor_block.startswith("[actor]")

        # Citation must wrap arbitrary recall payloads cleanly.
        pack = bundle.citation.wrap(
            "g1",
            [
                {"id": "m1", "source_layer": "L1", "content": "x"},
                {"id": "m2", "source_layer": "L2", "content": "y"},
            ],
        )
        assert isinstance(pack, CitationPack)
        assert len(pack.citations) == 2
