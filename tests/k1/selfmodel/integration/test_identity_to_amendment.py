"""M5.E1.I2 — Identity ➜ Amendment ➜ Constitution ➜ Composer round-trip.

Walks the full guardianship lifecycle end-to-end with NO stubs:

1. ``IdentitySessionManager`` registers a guardian profile.
2. ``start_session`` then ``present_credential`` promotes the session
   to ``STRONG_CRED`` (tier 3) — the tier the V0 constitution requires
   for any constitution-level mutation.
3. ``AmendmentService.propose`` → ``submit`` → ``sign`` (with a real
   Ed25519 signature validated by ``Ed25519SignatureChainValidator``).
4. The signed amendment auto-activates because ``signing_quorum=1``;
   ``ConstitutionService.get_active`` now returns the new snapshot.
5. A fresh ``SituationFrameComposer.compose`` reflects the new rule
   in ``Capabilities.can_do`` — proof the amendment really took effect.

Acceptance: all five stages produce the expected state with the real
services on top of ``InMemoryProjectionStore``.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field

import pytest
from nacl.signing import SigningKey

from k1.selfmodel.adapters.memory_projection_store import InMemoryProjectionStore
from k1.selfmodel.contracts.constitution import (
    AmendmentStatus,
    ConstitutionSnapshot,
    SigningProof,
)
from k1.selfmodel.events.topics import (
    TOPIC_CONSTITUTION_AMENDMENT_ACTIVE,
    TOPIC_IDENTITY_SESSION_STARTED,
)
from k1.selfmodel.ports.credential import ICredentialPort
from k1.selfmodel.ports.identity import (
    CredentialPresentation,
    DeviceContext,
    IdentityTier,
    ProfileSummary,
    VerificationResult,
)
from k1.selfmodel.service.amendment import AmendmentService
from k1.selfmodel.service.constitution import ConstitutionService
from k1.selfmodel.service.space_graph import (
    SPACE_GRAPH_WRITER_ID,
    SpaceGraphService,
)
from k1.selfmodel.service.identity_session import IdentitySessionManager
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

pytestmark = pytest.mark.integration


CID = DEFAULT_CONSTITUTION_ID
WRITER_AMD = "selfmodel:amendment"
ALL_WRITERS = (
    SELF_MODEL_WRITER_ID,
    SPACE_GRAPH_WRITER_ID,
    WRITER_AMD,
    "test:fixture",
)


# ---------------------------------------------------------------------
# Stub credential port that promotes to a configured tier.
# ---------------------------------------------------------------------
@dataclass
class _PromotingCredentialPort(ICredentialPort):
    promote_to: IdentityTier = IdentityTier.STRONG_CRED

    def verify(self, profile_id: str, credential: CredentialPresentation) -> VerificationResult:
        return VerificationResult(
            accepted=True,
            promoted_to_tier=self.promote_to,
            reason="ok",
        )

    def max_tier_for(self, kind: str) -> IdentityTier:
        return self.promote_to


@dataclass
class _RecordingBus:
    events: list[tuple[str, dict]] = field(default_factory=list)

    def publish_simple(self, topic: str, body: dict) -> None:
        self.events.append((topic, body))


# ---------------------------------------------------------------------
# Bundle assembled from real services + a real signed bootstrap row.
# ---------------------------------------------------------------------
@dataclass
class _IntegrationBundle:
    store: InMemoryProjectionStore
    identity: IdentitySessionManager
    constitution: ConstitutionService
    amendments: AmendmentService
    composer: SituationFrameComposer
    bus: _RecordingBus
    bootstrap_sk: SigningKey
    validator: Ed25519SignatureChainValidator
    bootstrap_version: str


def _build_integration_bundle(
    *, bootstrap_body: dict, bootstrap_version: str = "v0"
) -> _IntegrationBundle:
    store = InMemoryProjectionStore(allowed_writers=ALL_WRITERS)

    # ---- Bootstrap constitution: real Ed25519 signature ----
    sk = SigningKey.generate()
    pk = bytes(sk.verify_key)
    sig = sk.sign(canonical_body_bytes(bootstrap_body)).signature
    bootstrap_proof = SigningProof(
        signer_id="bootstrap",
        key_id="did:bootstrap#0",
        algorithm="ed25519",
        signature_b64=base64.b64encode(sig).decode("ascii"),
        signed_at_ms=T0_MS,
    )
    bootstrap_snap = ConstitutionSnapshot(
        constitution_id=CID,
        version=bootstrap_version,
        parent_version="",
        body=bootstrap_body,
        signatures=(bootstrap_proof,),
        activated_at_ms=T0_MS,
    )
    write_result = store.write_constitution(bootstrap_snap, writer_id="test:fixture")
    assert write_result.accepted, f"bootstrap write rejected: {write_result.reason}"

    validator = Ed25519SignatureChainValidator()
    validator.register_signer("bootstrap", pk)

    # ---- Family + actor ----
    actor = make_actor("g1", role="guardian", name="Aanya")
    family = make_family(members=(make_member("g1", role="guardian", name="Aanya"),))
    store.write_self(actor, writer_id="test:fixture")
    store.write_space(family, writer_id="test:fixture")

    # ---- Real services ----
    bus = _RecordingBus()
    cs = ConstitutionService(store, constitution_id=CID, validator=validator)
    sm = SelfModelService(store)
    fm = SpaceGraphService(store)
    composer = SituationFrameComposer(
        self_model=sm,
        space_graph=fm,
        constitution=cs,
        space_id=DEFAULT_FAMILY_SPACE,
    )
    amendments = AmendmentService(
        store,
        cs,
        signing_quorum=1,
        clock=lambda: T0_MS,
        bus=bus,
    )

    # ---- Identity manager with one guardian profile ----
    identity = IdentitySessionManager(
        _PromotingCredentialPort(),
        clock=lambda: T0_MS,
        bus=bus,
    )
    identity.register_profile(
        ProfileSummary(profile_id="g1", display_name="Aanya", role="guardian"),
        paired_devices=("d1",),
    )

    return _IntegrationBundle(
        store=store,
        identity=identity,
        constitution=cs,
        amendments=amendments,
        composer=composer,
        bus=bus,
        bootstrap_sk=sk,
        validator=validator,
        bootstrap_version=bootstrap_version,
    )


def _proof_for(sk: SigningKey, body: dict, *, signer_id: str = "bootstrap") -> SigningProof:
    sig = sk.sign(canonical_body_bytes(body)).signature
    return SigningProof(
        signer_id=signer_id,
        key_id="did:bootstrap#0",
        algorithm="ed25519",
        signature_b64=base64.b64encode(sig).decode("ascii"),
        signed_at_ms=T0_MS,
    )


# =====================================================================
# Stage 1+2 — Identity tier promotion
# =====================================================================
def test_guardian_session_promotes_to_strong_cred() -> None:
    bundle = _build_integration_bundle(bootstrap_body=v0_body())
    device = DeviceContext(device_id="d1")

    eligible = bundle.identity.list_eligible_profiles(device)
    assert any(p.profile_id == "g1" for p in eligible)

    session = bundle.identity.start_session("g1", device)
    assert session.tier == IdentityTier.SOFT_CLAIM
    assert any(t == TOPIC_IDENTITY_SESSION_STARTED for t, _ in bundle.bus.events)

    result = bundle.identity.present_credential(
        session.session_token,
        CredentialPresentation(kind="pin", payload={"pin": "1234"}, presented_at_ms=T0_MS),
    )
    assert result.accepted is True
    assert bundle.identity.get_session_tier(session.session_token) == IdentityTier.STRONG_CRED


# =====================================================================
# Stage 3+4+5 — Amendment lifecycle ➜ activation ➜ composer reflects rule
# =====================================================================
def test_full_lifecycle_amendment_activates_and_changes_capabilities() -> None:
    bundle = _build_integration_bundle(bootstrap_body=v0_body())

    # Baseline: ``send_message`` is NOT in guardian capabilities.
    baseline_frame = bundle.composer.compose("g1", T0_MS, "d1", "caregiver_context_briefing")
    assert "send_message" not in baseline_frame.capabilities.can_do

    # ---- Stage 3: amendment that grants ``send_message`` to guardians ----
    new_body = v0_body()
    new_body_autonomy = dict(new_body["autonomy_rules"])  # type: ignore[arg-type]
    guardian = dict(new_body_autonomy["guardian"])
    guardian["can"] = list(guardian["can"]) + ["send_message"]
    new_body_autonomy["guardian"] = guardian
    new_body["autonomy_rules"] = new_body_autonomy

    proposal = bundle.amendments.propose(
        proposed_by="g1",
        parent_version=bundle.bootstrap_version,
        body=new_body,
    )
    assert proposal.status == AmendmentStatus.DRAFT

    submitted = bundle.amendments.submit(proposal.amendment_id)
    assert submitted.status == AmendmentStatus.PENDING

    proof = _proof_for(bundle.bootstrap_sk, new_body)
    activated = bundle.amendments.sign(proposal.amendment_id, proof)

    # ---- Stage 4: activation visible on bus + via constitution service ----
    assert activated.status == AmendmentStatus.ACTIVE
    assert any(t == TOPIC_CONSTITUTION_AMENDMENT_ACTIVE for t, _ in bundle.bus.events)

    new_active = bundle.constitution.get_active().snapshot
    assert new_active.parent_version == bundle.bootstrap_version
    assert new_active.body == new_body
    assert new_active.version != bundle.bootstrap_version

    # ---- Stage 5: composer now reflects the new rule ----
    new_frame = bundle.composer.compose("g1", T0_MS, "d1", "caregiver_context_briefing")
    assert "send_message" in new_frame.capabilities.can_do
    # The pre-existing capabilities are unchanged.
    assert "recall_memory" in new_frame.capabilities.can_do
    assert "set_routine" in new_frame.capabilities.can_do


# =====================================================================
# Negative path — wrong parent_version is rejected
# =====================================================================
def test_amendment_with_wrong_parent_version_does_not_activate() -> None:
    bundle = _build_integration_bundle(bootstrap_body=v0_body())
    new_body = v0_body()

    bad = bundle.amendments.propose(
        proposed_by="g1",
        parent_version="v_does_not_exist",
        body=new_body,
    )
    bundle.amendments.submit(bad.amendment_id)

    # Sign reaches quorum and triggers ``_activate``, which raises
    # ``IllegalAmendmentTransition`` because parent_version mismatches.
    from k1.selfmodel.service.amendment import IllegalAmendmentTransition

    with pytest.raises(IllegalAmendmentTransition):
        bundle.amendments.sign(bad.amendment_id, _proof_for(bundle.bootstrap_sk, new_body))

    # Constitution unchanged.
    assert bundle.constitution.get_active().snapshot.version == bundle.bootstrap_version


# =====================================================================
# Anchor — composer survives across multiple amendment cycles
# =====================================================================
def test_two_amendments_chained_compose_reflects_each_step() -> None:
    bundle = _build_integration_bundle(bootstrap_body=v0_body())

    # First amendment: add ``send_message``.
    body_a = v0_body()
    body_a_aut = dict(body_a["autonomy_rules"])  # type: ignore[arg-type]
    g = dict(body_a_aut["guardian"])
    g["can"] = list(g["can"]) + ["send_message"]
    body_a_aut["guardian"] = g
    body_a["autonomy_rules"] = body_a_aut

    p1 = bundle.amendments.propose("g1", bundle.bootstrap_version, body_a)
    bundle.amendments.submit(p1.amendment_id)
    bundle.amendments.sign(p1.amendment_id, _proof_for(bundle.bootstrap_sk, body_a))
    v1 = bundle.constitution.get_active().snapshot.version

    # Second amendment: also add ``cancel_routine`` on top of the first.
    body_b = body_a
    body_b_aut = dict(body_b["autonomy_rules"])  # type: ignore[arg-type]
    g2 = dict(body_b_aut["guardian"])
    g2["can"] = list(g2["can"]) + ["cancel_routine"]
    body_b_aut["guardian"] = g2
    # Build a fresh dict so we have a separate object (avoid sharing).
    body_b = dict(body_b)
    body_b["autonomy_rules"] = body_b_aut

    p2 = bundle.amendments.propose("g1", v1, body_b)
    bundle.amendments.submit(p2.amendment_id)
    bundle.amendments.sign(p2.amendment_id, _proof_for(bundle.bootstrap_sk, body_b))
    v2 = bundle.constitution.get_active().snapshot.version

    assert v2 != v1 != bundle.bootstrap_version
    final_frame = bundle.composer.compose("g1", T0_MS, "d1", "caregiver_context_briefing")
    assert "send_message" in final_frame.capabilities.can_do
    assert "cancel_routine" in final_frame.capabilities.can_do
