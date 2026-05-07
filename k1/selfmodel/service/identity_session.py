"""``IdentitySessionManager`` — tier-aware session manager for k1.selfmodel.

Issue M3.E2.I1.

Implements ``IIdentityPort`` end-to-end:

* ``list_eligible_profiles(device)`` -> profiles paired with the device.
* ``start_session(profile_id, device, proof?)`` -> returns a fresh
  ``IdentitySession`` with token + tier + hard expiry.
* ``present_credential(token, credential)`` -> verifies via
  ``ICredentialPort`` and PROMOTES the session tier if the credential is
  accepted; never demotes.
* ``end_session(token)`` -> revokes the token (one-shot replay rejection).
* ``get_session_tier(token)`` -> current tier or ``ANONYMOUS`` if the
  token is unknown / revoked / past its hard TTL.

Hard TTL semantics (from whiteboard line 122 + plan §M3.E2.I1):

The TTL is independent of UI inactivity. Once issued, a session has a
fixed wall-clock deadline. After that deadline the token is treated as
``ANONYMOUS`` for tier queries, all credential presentations are
rejected, and the token is removed at the next maintenance call.

Persistence:

The class accepts an optional ``IIdentitySessionStore`` (in-memory
default). The SQLite implementation lives in
``adapters/sqlite_projection_store.py`` (M3.E4) and survives process
restarts.

Bus events (best-effort, swallowed if the bus rejects):

* ``k1.selfmodel.identity.session_started.v1``
* ``k1.selfmodel.identity.session_promoted.v1``
* ``k1.selfmodel.identity.session_ended.v1``
"""

from __future__ import annotations

import logging
import secrets
import threading
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field, replace

from k1.selfmodel.events.topics import (
    TOPIC_IDENTITY_SESSION_ENDED,
    TOPIC_IDENTITY_SESSION_PROMOTED,
    TOPIC_IDENTITY_SESSION_STARTED,
)
from k1.selfmodel.ports.credential import ICredentialPort
from k1.selfmodel.ports.identity import (
    CredentialPresentation,
    DeviceContext,
    IdentitySession,
    IdentityTier,
    IIdentityPort,
    ProfileSummary,
    VerificationResult,
)

__all__ = [
    "IdentitySessionManager",
    "IIdentitySessionStore",
    "InMemorySessionStore",
    "DEFAULT_HARD_TTL_MS",
]


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------
#: 12 hours by default; production overrides via constructor.
DEFAULT_HARD_TTL_MS: int = 12 * 60 * 60 * 1000


ClockFn = Callable[[], int]


def _now_ms() -> int:
    return int(time.time() * 1000)


# ---------------------------------------------------------------------
# Session store (in-memory default; SQLite in M3.E4)
# ---------------------------------------------------------------------
class IIdentitySessionStore:
    """Persistence port for identity sessions.

    Methods MUST be thread-safe. Implementations must NOT raise on a
    missing token — return ``None`` instead.
    """

    def put(self, session: IdentitySession) -> None:  # pragma: no cover - interface
        raise NotImplementedError

    def get(self, token: str) -> IdentitySession | None:  # pragma: no cover
        raise NotImplementedError

    def delete(self, token: str) -> None:  # pragma: no cover
        raise NotImplementedError

    def purge_expired(self, *, now_ms: int) -> int:  # pragma: no cover
        raise NotImplementedError


class InMemorySessionStore(IIdentitySessionStore):
    """Reference implementation backing :class:`IdentitySessionManager`."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._sessions: dict[str, IdentitySession] = {}

    def put(self, session: IdentitySession) -> None:
        with self._lock:
            self._sessions[session.session_token] = session

    def get(self, token: str) -> IdentitySession | None:
        with self._lock:
            return self._sessions.get(token)

    def delete(self, token: str) -> None:
        with self._lock:
            self._sessions.pop(token, None)

    def purge_expired(self, *, now_ms: int) -> int:
        with self._lock:
            stale = [
                t
                for t, s in self._sessions.items()
                if s.hard_expires_at_ms and s.hard_expires_at_ms <= now_ms
            ]
            for t in stale:
                self._sessions.pop(t, None)
            return len(stale)

    def all(self) -> tuple[IdentitySession, ...]:
        with self._lock:
            return tuple(self._sessions.values())


# ---------------------------------------------------------------------
# Profile registry (admin-side; tests build their own)
# ---------------------------------------------------------------------
@dataclass
class _ProfileEntry:
    summary: ProfileSummary
    paired_devices: set[str] = field(default_factory=set)


# ---------------------------------------------------------------------
# Manager
# ---------------------------------------------------------------------
class IdentitySessionManager(IIdentityPort):
    """Production identity session manager."""

    def __init__(
        self,
        credential_port: ICredentialPort,
        *,
        store: IIdentitySessionStore | None = None,
        hard_ttl_ms: int = DEFAULT_HARD_TTL_MS,
        clock: ClockFn | None = None,
        bus=None,
        token_factory: Callable[[], str] | None = None,
    ) -> None:
        if credential_port is None:
            raise ValueError("credential_port is required")
        if hard_ttl_ms <= 0:
            raise ValueError("hard_ttl_ms must be positive")
        self._credentials = credential_port
        self._store = store or InMemorySessionStore()
        self._hard_ttl_ms = hard_ttl_ms
        self._clock: ClockFn = clock or _now_ms
        self._bus = bus
        self._token_factory = token_factory or (lambda: secrets.token_urlsafe(32))
        self._lock = threading.RLock()
        self._profiles: dict[str, _ProfileEntry] = {}
        # Revoked-token ledger so ``end_session`` makes the token
        # *unforgeable-for-reuse*: even if a caller retains the string,
        # subsequent ``get_session_tier`` returns ``ANONYMOUS``.
        self._revoked: set[str] = set()

    # ------------------------------------------------------------------
    # Profile admin (out of port; used by kernel bootstrap + tests)
    # ------------------------------------------------------------------
    def register_profile(
        self,
        summary: ProfileSummary,
        *,
        paired_devices: tuple[str, ...] = (),
    ) -> None:
        if not summary.profile_id:
            raise ValueError("ProfileSummary.profile_id must be non-empty")
        with self._lock:
            entry = self._profiles.get(summary.profile_id)
            if entry is None:
                entry = _ProfileEntry(summary=summary)
                self._profiles[summary.profile_id] = entry
            else:
                entry.summary = summary
            entry.paired_devices.update(paired_devices)

    def pair_device(self, profile_id: str, device_id: str) -> None:
        if not profile_id or not device_id:
            raise ValueError("profile_id and device_id required")
        with self._lock:
            entry = self._profiles.get(profile_id)
            if entry is None:
                raise KeyError(f"unknown profile {profile_id!r}")
            entry.paired_devices.add(device_id)

    # ------------------------------------------------------------------
    # IIdentityPort
    # ------------------------------------------------------------------
    def list_eligible_profiles(
        self, device: DeviceContext
    ) -> tuple[ProfileSummary, ...]:
        if not isinstance(device, DeviceContext):
            raise TypeError("device must be DeviceContext")
        with self._lock:
            if device.is_shared_hub:
                # Shared hub: every registered profile is eligible.
                profiles = [e.summary for e in self._profiles.values()]
            else:
                profiles = [
                    e.summary
                    for e in self._profiles.values()
                    if device.device_id in e.paired_devices
                ]
        # Stable sort by last_seen_at_ms desc, then profile_id asc.
        profiles.sort(key=lambda p: (-p.last_seen_at_ms, p.profile_id))
        return tuple(profiles)

    def start_session(
        self,
        profile_id: str,
        device: DeviceContext,
        proof: CredentialPresentation | None = None,
    ) -> IdentitySession:
        if not profile_id:
            raise ValueError("profile_id required")
        if not isinstance(device, DeviceContext):
            raise TypeError("device must be DeviceContext")
        with self._lock:
            if profile_id not in self._profiles:
                raise KeyError(f"unknown profile {profile_id!r}")

        now = self._clock()
        token = self._token_factory()
        # SOFT_CLAIM if the caller asserted *who* they are without proof,
        # otherwise ANONYMOUS.
        initial_tier = IdentityTier.SOFT_CLAIM if profile_id else IdentityTier.ANONYMOUS

        session = IdentitySession(
            session_token=token,
            profile_id=profile_id,
            tier=initial_tier,
            device_id=device.device_id,
            issued_at_ms=now,
            hard_expires_at_ms=now + self._hard_ttl_ms,
        )
        self._store.put(session)
        self._publish(
            TOPIC_IDENTITY_SESSION_STARTED,
            {
                "profile_id": profile_id,
                "device_id": device.device_id,
                "tier": int(initial_tier),
                "issued_at_ms": now,
                "hard_expires_at_ms": session.hard_expires_at_ms,
            },
        )
        # If the caller already has a credential, attempt promotion now.
        if proof is not None:
            promoted = self._promote(session, proof, now=now)
            if promoted is not None:
                return promoted
        return session

    def present_credential(
        self, session_token: str, credential: CredentialPresentation
    ) -> VerificationResult:
        if not session_token:
            return VerificationResult(accepted=False, reason="missing_token")
        if not isinstance(credential, CredentialPresentation):
            return VerificationResult(accepted=False, reason="malformed_credential")
        now = self._clock()
        with self._lock:
            if session_token in self._revoked:
                return VerificationResult(accepted=False, reason="token_revoked")
        session = self._store.get(session_token)
        if session is None:
            return VerificationResult(accepted=False, reason="unknown_token")
        if session.hard_expires_at_ms and session.hard_expires_at_ms <= now:
            self._store.delete(session_token)
            return VerificationResult(accepted=False, reason="token_expired")
        promoted = self._promote(session, credential, now=now)
        if promoted is None:
            # _promote already returned its rejection via the verifier;
            # re-derive the rejection result for the caller.
            return self._credentials.verify(session.profile_id, credential)
        return VerificationResult(
            accepted=True,
            promoted_to_tier=promoted.tier,
            reason="promoted",
        )

    def end_session(self, session_token: str) -> None:
        if not session_token:
            return
        with self._lock:
            self._revoked.add(session_token)
        session = self._store.get(session_token)
        self._store.delete(session_token)
        if session is not None:
            self._publish(
                TOPIC_IDENTITY_SESSION_ENDED,
                {
                    "profile_id": session.profile_id,
                    "device_id": session.device_id,
                    "ended_at_ms": self._clock(),
                },
            )

    def get_session_tier(self, session_token: str) -> IdentityTier:
        if not session_token:
            return IdentityTier.ANONYMOUS
        with self._lock:
            if session_token in self._revoked:
                return IdentityTier.ANONYMOUS
        session = self._store.get(session_token)
        if session is None:
            return IdentityTier.ANONYMOUS
        if session.hard_expires_at_ms and session.hard_expires_at_ms <= self._clock():
            self._store.delete(session_token)
            return IdentityTier.ANONYMOUS
        return session.tier

    # ------------------------------------------------------------------
    # Maintenance
    # ------------------------------------------------------------------
    def purge_expired(self) -> int:
        return self._store.purge_expired(now_ms=self._clock())

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------
    def _promote(
        self,
        session: IdentitySession,
        credential: CredentialPresentation,
        *,
        now: int,
    ) -> IdentitySession | None:
        result = self._credentials.verify(session.profile_id, credential)
        if not result.accepted:
            return None
        ceiling = self._credentials.max_tier_for(credential.kind)
        proposed = IdentityTier(min(int(result.promoted_to_tier), int(ceiling)))
        # Never demote.
        new_tier = proposed if int(proposed) > int(session.tier) else session.tier
        if new_tier == session.tier:
            return session
        promoted = replace(session, tier=new_tier)
        self._store.put(promoted)
        self._publish(
            TOPIC_IDENTITY_SESSION_PROMOTED,
            {
                "profile_id": session.profile_id,
                "device_id": session.device_id,
                "from_tier": int(session.tier),
                "to_tier": int(new_tier),
                "promoted_at_ms": now,
            },
        )
        return promoted

    def _publish(self, topic: str, body: dict) -> None:
        bus = self._bus
        if bus is None:
            return
        try:
            publish_simple = getattr(bus, "publish_simple", None)
            if callable(publish_simple):
                publish_simple(topic, body)
                return
            publish = getattr(bus, "publish", None)
            if callable(publish):
                publish(topic, body)  # best effort on raw publish
        except Exception:
            logger.debug("identity_session: bus publish failed topic=%s", topic, exc_info=True)
