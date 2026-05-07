"""Unit tests for ``IdentitySessionManager`` (M3.E2.I1)."""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from k1.selfmodel.events.topics import (
    TOPIC_IDENTITY_SESSION_ENDED,
    TOPIC_IDENTITY_SESSION_PROMOTED,
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
from k1.selfmodel.service.identity_session import (
    DEFAULT_HARD_TTL_MS,
    IdentitySessionManager,
    InMemorySessionStore,
)


T_MS = 1_700_000_000_000


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------
@dataclass
class StubCredentialPort(ICredentialPort):
    """ICredentialPort stub returning canned VerificationResults."""

    result: VerificationResult = field(
        default_factory=lambda: VerificationResult(
            accepted=True,
            promoted_to_tier=IdentityTier.PIN_VERIFIED,
            reason="ok",
        )
    )
    ceiling: IdentityTier = IdentityTier.PIN_VERIFIED
    calls: list[tuple[str, CredentialPresentation]] = field(default_factory=list)

    def verify(
        self, profile_id: str, credential: CredentialPresentation
    ) -> VerificationResult:
        self.calls.append((profile_id, credential))
        return self.result

    def max_tier_for(self, kind: str) -> IdentityTier:
        return self.ceiling


@dataclass
class StubBus:
    events: list[tuple[str, dict]] = field(default_factory=list)

    def publish_simple(self, topic: str, body: dict) -> None:
        self.events.append((topic, body))


def _device(device_id: str = "dev:1", *, shared_hub: bool = False) -> DeviceContext:
    return DeviceContext(device_id=device_id, is_shared_hub=shared_hub)


def _profile(profile_id: str = "p1", *, last_seen: int = 0) -> ProfileSummary:
    return ProfileSummary(profile_id=profile_id, display_name=profile_id, last_seen_at_ms=last_seen)


def _make_manager(**overrides) -> tuple[IdentitySessionManager, StubCredentialPort, StubBus]:
    cred = overrides.pop("credential_port", None) or StubCredentialPort()
    bus = overrides.pop("bus", None) or StubBus()
    clock_ref = {"t": T_MS}

    def _clk():
        return clock_ref["t"]

    mgr = IdentitySessionManager(
        cred,
        clock=overrides.pop("clock", _clk),
        bus=bus,
        **overrides,
    )
    mgr._clock_ref = clock_ref  # type: ignore[attr-defined]
    return mgr, cred, bus


# ---------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------
def test_constructor_validates_credential_port() -> None:
    with pytest.raises(ValueError):
        IdentitySessionManager(None)  # type: ignore[arg-type]


def test_constructor_validates_ttl() -> None:
    with pytest.raises(ValueError):
        IdentitySessionManager(StubCredentialPort(), hard_ttl_ms=0)
    with pytest.raises(ValueError):
        IdentitySessionManager(StubCredentialPort(), hard_ttl_ms=-1)


def test_default_ttl_is_12_hours() -> None:
    assert DEFAULT_HARD_TTL_MS == 12 * 60 * 60 * 1000


# ---------------------------------------------------------------------
# Profile registration / pairing
# ---------------------------------------------------------------------
def test_register_profile_validates_id() -> None:
    mgr, _, _ = _make_manager()
    with pytest.raises(ValueError):
        mgr.register_profile(ProfileSummary(profile_id=""))


def test_pair_device_unknown_profile_raises() -> None:
    mgr, _, _ = _make_manager()
    with pytest.raises(KeyError):
        mgr.pair_device("missing", "dev:1")


def test_pair_device_validates_args() -> None:
    mgr, _, _ = _make_manager()
    mgr.register_profile(_profile())
    with pytest.raises(ValueError):
        mgr.pair_device("", "dev:1")
    with pytest.raises(ValueError):
        mgr.pair_device("p1", "")


def test_register_profile_can_update_existing() -> None:
    mgr, _, _ = _make_manager()
    mgr.register_profile(_profile("p1"), paired_devices=("dev:1",))
    mgr.register_profile(
        ProfileSummary(profile_id="p1", display_name="Updated"),
        paired_devices=("dev:2",),
    )
    eligible = mgr.list_eligible_profiles(_device("dev:2"))
    assert len(eligible) == 1
    assert eligible[0].display_name == "Updated"


# ---------------------------------------------------------------------
# list_eligible_profiles
# ---------------------------------------------------------------------
def test_list_eligible_profiles_paired_only() -> None:
    mgr, _, _ = _make_manager()
    mgr.register_profile(_profile("p1"), paired_devices=("dev:1",))
    mgr.register_profile(_profile("p2"), paired_devices=("dev:2",))
    out = mgr.list_eligible_profiles(_device("dev:1"))
    assert tuple(p.profile_id for p in out) == ("p1",)


def test_list_eligible_profiles_shared_hub_returns_all() -> None:
    mgr, _, _ = _make_manager()
    mgr.register_profile(_profile("p1"), paired_devices=("dev:1",))
    mgr.register_profile(_profile("p2"), paired_devices=("dev:2",))
    out = mgr.list_eligible_profiles(_device("hub", shared_hub=True))
    assert {p.profile_id for p in out} == {"p1", "p2"}


def test_list_eligible_profiles_sorted_by_last_seen_desc() -> None:
    mgr, _, _ = _make_manager()
    mgr.register_profile(_profile("p_old", last_seen=10), paired_devices=("dev:1",))
    mgr.register_profile(_profile("p_new", last_seen=20), paired_devices=("dev:1",))
    out = mgr.list_eligible_profiles(_device("dev:1"))
    assert tuple(p.profile_id for p in out) == ("p_new", "p_old")


def test_list_eligible_profiles_validates_device_type() -> None:
    mgr, _, _ = _make_manager()
    with pytest.raises(TypeError):
        mgr.list_eligible_profiles("not-a-device")  # type: ignore[arg-type]


# ---------------------------------------------------------------------
# start_session
# ---------------------------------------------------------------------
def test_start_session_happy_returns_soft_claim() -> None:
    mgr, _, bus = _make_manager()
    mgr.register_profile(_profile("p1"), paired_devices=("dev:1",))
    sess = mgr.start_session("p1", _device("dev:1"))
    assert sess.profile_id == "p1"
    assert sess.tier == IdentityTier.SOFT_CLAIM
    assert sess.hard_expires_at_ms == T_MS + DEFAULT_HARD_TTL_MS
    assert any(t == TOPIC_IDENTITY_SESSION_STARTED for t, _ in bus.events)


def test_start_session_with_proof_promotes_immediately() -> None:
    mgr, _, bus = _make_manager()
    mgr.register_profile(_profile("p1"), paired_devices=("dev:1",))
    cred = CredentialPresentation(kind="pin", payload={"pin": "0420"}, presented_at_ms=T_MS)
    sess = mgr.start_session("p1", _device("dev:1"), proof=cred)
    assert sess.tier == IdentityTier.PIN_VERIFIED
    topics = [t for t, _ in bus.events]
    assert TOPIC_IDENTITY_SESSION_STARTED in topics
    assert TOPIC_IDENTITY_SESSION_PROMOTED in topics


def test_start_session_unknown_profile() -> None:
    mgr, _, _ = _make_manager()
    with pytest.raises(KeyError):
        mgr.start_session("ghost", _device("dev:1"))


def test_start_session_validates_device() -> None:
    mgr, _, _ = _make_manager()
    mgr.register_profile(_profile("p1"))
    with pytest.raises(TypeError):
        mgr.start_session("p1", "not a device")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        mgr.start_session("", _device("dev:1"))


# ---------------------------------------------------------------------
# present_credential
# ---------------------------------------------------------------------
def test_present_credential_promotes_tier() -> None:
    mgr, cred, bus = _make_manager()
    mgr.register_profile(_profile("p1"), paired_devices=("dev:1",))
    sess = mgr.start_session("p1", _device("dev:1"))
    res = mgr.present_credential(
        sess.session_token,
        CredentialPresentation(kind="pin", payload={"pin": "x"}, presented_at_ms=T_MS),
    )
    assert res.accepted is True
    assert res.promoted_to_tier == IdentityTier.PIN_VERIFIED
    assert mgr.get_session_tier(sess.session_token) == IdentityTier.PIN_VERIFIED


def test_present_credential_never_demotes() -> None:
    cred = StubCredentialPort(
        result=VerificationResult(
            accepted=True, promoted_to_tier=IdentityTier.SOFT_CLAIM, reason="ok"
        ),
        ceiling=IdentityTier.SOFT_CLAIM,
    )
    mgr, _, _ = _make_manager(credential_port=cred)
    mgr.register_profile(_profile("p1"))
    # Pre-elevate the session via stronger initial proof.
    cred.result = VerificationResult(
        accepted=True, promoted_to_tier=IdentityTier.STRONG_CRED, reason="ok"
    )
    cred.ceiling = IdentityTier.STRONG_CRED
    sess = mgr.start_session(
        "p1",
        _device("dev:1"),
        proof=CredentialPresentation(kind="passkey", payload={}, presented_at_ms=T_MS),
    )
    assert sess.tier == IdentityTier.STRONG_CRED
    # Now present a weaker credential — must NOT demote.
    cred.result = VerificationResult(
        accepted=True, promoted_to_tier=IdentityTier.PIN_VERIFIED, reason="ok"
    )
    cred.ceiling = IdentityTier.PIN_VERIFIED
    mgr.present_credential(
        sess.session_token,
        CredentialPresentation(kind="pin", payload={}, presented_at_ms=T_MS),
    )
    assert mgr.get_session_tier(sess.session_token) == IdentityTier.STRONG_CRED


def test_present_credential_clamped_by_ceiling() -> None:
    cred = StubCredentialPort(
        result=VerificationResult(
            accepted=True, promoted_to_tier=IdentityTier.STRONG_CRED, reason="ok"
        ),
        ceiling=IdentityTier.PIN_VERIFIED,  # ceiling lower than result.
    )
    mgr, _, _ = _make_manager(credential_port=cred)
    mgr.register_profile(_profile("p1"))
    sess = mgr.start_session("p1", _device("dev:1"))
    mgr.present_credential(
        sess.session_token,
        CredentialPresentation(kind="pin", payload={}, presented_at_ms=T_MS),
    )
    assert mgr.get_session_tier(sess.session_token) == IdentityTier.PIN_VERIFIED


def test_present_credential_rejected_returns_verifier_result() -> None:
    cred = StubCredentialPort(
        result=VerificationResult(accepted=False, reason="pin_mismatch")
    )
    mgr, _, _ = _make_manager(credential_port=cred)
    mgr.register_profile(_profile("p1"))
    sess = mgr.start_session("p1", _device("dev:1"))
    res = mgr.present_credential(
        sess.session_token,
        CredentialPresentation(kind="pin", payload={}, presented_at_ms=T_MS),
    )
    assert res.accepted is False
    assert res.reason == "pin_mismatch"
    assert mgr.get_session_tier(sess.session_token) == IdentityTier.SOFT_CLAIM


def test_present_credential_unknown_token() -> None:
    mgr, _, _ = _make_manager()
    res = mgr.present_credential(
        "ghost", CredentialPresentation(kind="pin", payload={}, presented_at_ms=T_MS)
    )
    assert res.accepted is False
    assert res.reason == "unknown_token"


def test_present_credential_missing_token() -> None:
    mgr, _, _ = _make_manager()
    res = mgr.present_credential(
        "", CredentialPresentation(kind="pin", payload={}, presented_at_ms=T_MS)
    )
    assert res.reason == "missing_token"


def test_present_credential_malformed_input() -> None:
    mgr, _, _ = _make_manager()
    mgr.register_profile(_profile("p1"))
    sess = mgr.start_session("p1", _device("dev:1"))
    res = mgr.present_credential(sess.session_token, "nope")  # type: ignore[arg-type]
    assert res.reason == "malformed_credential"


def test_present_credential_expired_token_returns_token_expired() -> None:
    mgr, _, _ = _make_manager(hard_ttl_ms=1000)
    mgr.register_profile(_profile("p1"))
    sess = mgr.start_session("p1", _device("dev:1"))
    mgr._clock_ref["t"] = T_MS + 5000  # type: ignore[attr-defined]
    res = mgr.present_credential(
        sess.session_token,
        CredentialPresentation(kind="pin", payload={}, presented_at_ms=T_MS),
    )
    assert res.reason == "token_expired"


def test_present_credential_revoked_token_rejected() -> None:
    mgr, _, _ = _make_manager()
    mgr.register_profile(_profile("p1"))
    sess = mgr.start_session("p1", _device("dev:1"))
    mgr.end_session(sess.session_token)
    res = mgr.present_credential(
        sess.session_token,
        CredentialPresentation(kind="pin", payload={}, presented_at_ms=T_MS),
    )
    assert res.reason == "token_revoked"


# ---------------------------------------------------------------------
# end_session / get_session_tier
# ---------------------------------------------------------------------
def test_end_session_revokes_and_emits_event() -> None:
    mgr, _, bus = _make_manager()
    mgr.register_profile(_profile("p1"))
    sess = mgr.start_session("p1", _device("dev:1"))
    mgr.end_session(sess.session_token)
    assert mgr.get_session_tier(sess.session_token) == IdentityTier.ANONYMOUS
    assert any(t == TOPIC_IDENTITY_SESSION_ENDED for t, _ in bus.events)


def test_end_session_empty_token_noop() -> None:
    mgr, _, bus = _make_manager()
    mgr.end_session("")
    assert all(t != TOPIC_IDENTITY_SESSION_ENDED for t, _ in bus.events)


def test_get_session_tier_unknown_returns_anonymous() -> None:
    mgr, _, _ = _make_manager()
    assert mgr.get_session_tier("missing") == IdentityTier.ANONYMOUS
    assert mgr.get_session_tier("") == IdentityTier.ANONYMOUS


def test_get_session_tier_expired_returns_anonymous_and_purges() -> None:
    mgr, _, _ = _make_manager(hard_ttl_ms=500)
    mgr.register_profile(_profile("p1"))
    sess = mgr.start_session("p1", _device("dev:1"))
    mgr._clock_ref["t"] = T_MS + 1000  # type: ignore[attr-defined]
    assert mgr.get_session_tier(sess.session_token) == IdentityTier.ANONYMOUS


# ---------------------------------------------------------------------
# Maintenance
# ---------------------------------------------------------------------
def test_purge_expired_returns_count() -> None:
    mgr, _, _ = _make_manager(hard_ttl_ms=500)
    mgr.register_profile(_profile("p1"))
    mgr.register_profile(_profile("p2"))
    mgr.start_session("p1", _device("dev:1"))
    mgr.start_session("p2", _device("dev:1"))
    mgr._clock_ref["t"] = T_MS + 1000  # type: ignore[attr-defined]
    assert mgr.purge_expired() == 2


# ---------------------------------------------------------------------
# Bus failure tolerance
# ---------------------------------------------------------------------
def test_bus_publish_failure_swallowed() -> None:
    class _Boom:
        def publish_simple(self, topic, body):
            raise RuntimeError("boom")

    mgr, _, _ = _make_manager(bus=_Boom())
    mgr.register_profile(_profile("p1"))
    sess = mgr.start_session("p1", _device("dev:1"))  # must not raise
    assert sess.profile_id == "p1"


def test_bus_falls_back_to_publish_when_no_publish_simple() -> None:
    class _LegacyBus:
        def __init__(self):
            self.events = []

        def publish(self, topic, body):
            self.events.append((topic, body))

    bus = _LegacyBus()
    mgr, _, _ = _make_manager(bus=bus)
    mgr.register_profile(_profile("p1"))
    mgr.start_session("p1", _device("dev:1"))
    assert any(t == TOPIC_IDENTITY_SESSION_STARTED for t, _ in bus.events)


# ---------------------------------------------------------------------
# InMemorySessionStore directly
# ---------------------------------------------------------------------
def test_in_memory_session_store_purge_expired() -> None:
    from k1.selfmodel.ports.identity import IdentitySession

    store = InMemorySessionStore()
    s = IdentitySession(
        session_token="tok1",
        profile_id="p1",
        tier=IdentityTier.SOFT_CLAIM,
        device_id="dev:1",
        issued_at_ms=T_MS,
        hard_expires_at_ms=T_MS + 1000,
    )
    store.put(s)
    assert store.get("tok1") is s
    assert store.purge_expired(now_ms=T_MS + 2000) == 1
    assert store.get("tok1") is None
    assert store.all() == ()
    store.delete("missing")  # no-op
