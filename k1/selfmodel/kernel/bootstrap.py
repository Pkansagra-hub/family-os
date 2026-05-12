"""``SelfModelServiceBundle`` — Tier-1 wiring for ``k1.selfmodel``.

M5.E3.I2: Constructed once during ``KernelService._startup_tier1`` at
phase **S2.6** (after S2.5 HIL, before S4 Bridge). Holds the shared
read services, projection store, validator, capsule + citation
builders, identity manager, and amendment service.

The bundle owns the projection store lifecycle (``shutdown`` closes the
SQLite handle when one is in use). Per-session wiring (``P3.5``) builds
a :class:`~k1.selfmodel.kernel.handle.SelfModelHandle` that references
the same shared services.

This module performs **no business logic** — every service it wires is
already implemented in M0–M4. The bundle is pure wiring.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from k1.selfmodel.adapters.memory_projection_store import InMemoryProjectionStore
from k1.selfmodel.adapters.sqlite_projection_store import SQLiteProjectionStore
from k1.selfmodel.events.topics import (
    TOPIC_KERNEL_SAFE_MODE_ACTIVE,
    TOPIC_SELFMODEL_STARTUP_COMPLETE,
)
from k1.selfmodel.ports.projection_store import IProjectionStorePort
from k1.selfmodel.service.amendment import AmendmentService
from k1.selfmodel.service.bootstrap_constitution import (
    BOOTSTRAP_CONSTITUTION_ID_V1,
    BOOTSTRAP_SIGNER_ID,
    BootstrapResult,
    ensure_bootstrap_constitution,
)
from k1.selfmodel.service.capsule_builder import GroundingCapsuleBuilder
from k1.selfmodel.service.citation_builder import CitationPackBuilder
from k1.selfmodel.service.constitution import ConstitutionService
from k1.selfmodel.service.errors import ConstitutionUnavailableError
from k1.selfmodel.service.identity_session import IdentitySessionManager
from k1.selfmodel.service.policy_evaluator import PolicyEvaluator
from k1.selfmodel.service.self_model import SELF_MODEL_WRITER_ID, SelfModelService
from k1.selfmodel.service.signature_chain import Ed25519SignatureChainValidator
from k1.selfmodel.service.situation_composer import SituationFrameComposer
from k1.selfmodel.service.space_graph import SPACE_GRAPH_WRITER_ID, SpaceGraphService

if TYPE_CHECKING:  # pragma: no cover
    pass

logger = logging.getLogger(__name__)

__all__ = [
    "SelfModelServiceBundle",
    "build_self_model_bundle",
    "AMENDMENT_WRITER_ID",
]

#: Writer id used by ``AmendmentService`` for store mutations.
AMENDMENT_WRITER_ID = "selfmodel:amendment"


@dataclass
class SelfModelServiceBundle:
    """Container for Tier-1 ``k1.selfmodel`` services.

    Built once per kernel boot at S2.6 and reused across every session.
    Per-session bind happens in :func:`SelfModelHandle.attach` at P3.5.

    Fields are populated in dependency order by
    :func:`build_self_model_bundle`. ``shutdown()`` closes the
    projection store if it owns a SQLite handle.
    """

    # Persisted projections (M0/M3)
    store: IProjectionStorePort
    # Read services (M1)
    self_model: SelfModelService
    space_graph: SpaceGraphService
    constitution: ConstitutionService
    # Composer (M1)
    composer: SituationFrameComposer
    # Policy evaluator (M2)
    evaluator: PolicyEvaluator
    # Identity (M3) + Amendments (M3)
    identity: IdentitySessionManager
    amendments: AmendmentService
    # Bootstrap result + signature validator (M3)
    validator: Ed25519SignatureChainValidator
    bootstrap: BootstrapResult
    # Renderers / wrappers (M4)
    capsule_builder: GroundingCapsuleBuilder
    citation_builder: CitationPackBuilder
    # Config snapshot
    space_id: str
    constitution_id: str = BOOTSTRAP_CONSTITUTION_ID_V1
    # Lifecycle
    safe_mode: bool = False
    started_at_ms: int = 0
    # Internal: True when the store was constructed by the bundle and
    # therefore should be closed in ``shutdown``.
    _owns_store: bool = field(default=False, repr=False)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def shutdown(self) -> None:
        """Release any owned resources (SQLite handle, etc.).

        Safe to call multiple times. Errors are swallowed so kernel
        teardown never aborts on selfmodel cleanup failures.
        """
        if self._owns_store:
            close = getattr(self.store, "close", None)
            if callable(close):
                try:
                    close()
                except Exception:  # pragma: no cover — best-effort
                    logger.warning(
                        "SelfModelServiceBundle.shutdown: store close failed",
                        exc_info=True,
                    )
            self._owns_store = False

    # ------------------------------------------------------------------
    # Health (M5.E3.I4)
    # ------------------------------------------------------------------
    def health(self) -> dict[str, Any]:
        """Return a structured health snapshot of every wired service.

        Schema (kept stable for ``KernelService.health_check`` and the
        phase-9 probe):

        - ``status``: ``"ok" | "degraded" | "safe_mode"``
        - ``constitution``: ``{id, version, available, safe_mode,
          freshness}``
        - ``store``: ``{kind, owns_store}``
        - ``identity``: ``{registered_profiles}``
        - ``family_space_id``: configured family scope
        - ``started_at_ms``: monotonic millis from build time
        - ``bootstrap``: ``{created, signer_id, version}``
        """
        constitution_info: dict[str, Any] = {
            "id": self.constitution_id,
            "version": "",
            "available": False,
            "safe_mode": self.constitution.is_safe_mode,
            "freshness": "unknown",
        }
        try:
            read = self.constitution.get_active()
            constitution_info["available"] = True
            constitution_info["version"] = read.snapshot.version
            constitution_info["freshness"] = (
                read.freshness.value if hasattr(read.freshness, "value") else str(read.freshness)
            )
        except ConstitutionUnavailableError:
            constitution_info["available"] = False

        # Store kind via concrete class name (no isinstance import
        # cycles).
        store_kind = type(self.store).__name__

        # IdentitySessionManager exposes its profile registry via a
        # private dict; we surface only the count to keep the health
        # surface stable.
        try:
            registered_profiles = len(self.identity._profiles)  # noqa: SLF001
        except Exception:  # pragma: no cover
            registered_profiles = 0

        if self.safe_mode or constitution_info["safe_mode"]:
            status = "safe_mode"
        elif not constitution_info["available"]:
            status = "degraded"
        else:
            status = "ok"

        return {
            "status": status,
            "constitution": constitution_info,
            "store": {"kind": store_kind, "owns_store": self._owns_store},
            "identity": {"registered_profiles": registered_profiles},
            "family_space_id": self.space_id,
            "started_at_ms": self.started_at_ms,
            "bootstrap": {
                "created": self.bootstrap.created,
                "signer_id": BOOTSTRAP_SIGNER_ID,
                "version": self.bootstrap.snapshot.version,
            },
        }


def _build_store(
    db_path: str | None,
) -> tuple[IProjectionStorePort, bool]:
    """Construct the projection store.

    Returns ``(store, owns_store)``. When ``db_path`` is ``None`` or
    empty an :class:`InMemoryProjectionStore` is used and ``owns_store``
    is ``False`` (nothing to close). When a path is provided we build a
    :class:`SQLiteProjectionStore` and take ownership of the handle.
    """
    allowlist = (
        SELF_MODEL_WRITER_ID,
        SPACE_GRAPH_WRITER_ID,
        AMENDMENT_WRITER_ID,
        "selfmodel:bootstrap",
        "selfmodel:identity",
    )
    if db_path:
        return (
            SQLiteProjectionStore(db_path, allowed_writers=allowlist),
            True,
        )
    return InMemoryProjectionStore(allowed_writers=allowlist), False


def build_self_model_bundle(
    *,
    bus: Any | None = None,
    hil_service: Any | None = None,
    projection_db_path: str | None = None,
    space_id: str = "family:default",
    clock_ms: Any | None = None,
    publish_startup: bool = True,
) -> SelfModelServiceBundle:
    """Wire a :class:`SelfModelServiceBundle` for the kernel.

    Parameters mirror ``KernelConfig`` fields the kernel passes
    through. The function is also useful directly from tests that want
    a real bundle without spinning up the full kernel.

    ``hil_service`` is currently unused at bundle-build time — it is
    threaded into the per-session :class:`SelfModelHandle` instead so
    the gate can route ``REQUIRE_CONFIRMATION`` decisions.

    Behavior:

    1. Construct the projection store (in-memory or SQLite).
    2. Ensure a signed bootstrap constitution row exists (idempotent).
    3. Wire all read services (self / family / constitution).
    4. Wire the composer + policy evaluator.
    5. Wire the identity manager + amendment service.
    6. Wire the capsule + citation builders.
    7. (Optional) emit ``k1.selfmodel.startup.complete.v1`` on the
       bus.

    On constitution-signature failure the bundle is still returned but
    with ``safe_mode=True`` — reads continue to work; amendments will
    be rejected by ``ConstitutionService`` until the chain is
    repaired. Behavior matches the plan's "freeze in safe-mode" rule.
    """
    _clock = clock_ms or (lambda: int(time.time() * 1000))
    now_ms = int(_clock())

    store, owns_store = _build_store(projection_db_path)
    validator = Ed25519SignatureChainValidator()
    bootstrap = ensure_bootstrap_constitution(
        store,
        now_ms=now_ms,
        validator=validator,
    )
    constitution = ConstitutionService(
        store,
        constitution_id=BOOTSTRAP_CONSTITUTION_ID_V1,
        validator=validator,
    )
    self_model = SelfModelService(store)
    space_graph = SpaceGraphService(store)
    composer = SituationFrameComposer(
        self_model=self_model,
        space_graph=space_graph,
        constitution=constitution,
        space_id=space_id,
    )
    evaluator = PolicyEvaluator()

    # Identity manager wired with the M3 Ed25519 verifier. Importing
    # locally keeps the M0 import-graph thin (the verifier brings in
    # PyNaCl which we want to defer until the bundle is requested).
    from k1.selfmodel.adapters.credential_verifier import Ed25519CredentialVerifier

    identity = IdentitySessionManager(
        Ed25519CredentialVerifier(),
        clock=_clock,
        bus=bus,
    )
    amendments = AmendmentService(
        store,
        constitution,
        signing_quorum=1,
        clock=_clock,
        bus=bus,
    )
    capsule_builder = GroundingCapsuleBuilder(clock_ms=_clock)
    citation_builder = CitationPackBuilder()

    # Probe constitution to detect safe-mode at boot.
    safe_mode = False
    try:
        constitution.get_active()
    except ConstitutionUnavailableError:
        logger.error("selfmodel bundle: bootstrap constitution unavailable; entering safe mode")
        safe_mode = True

    bundle = SelfModelServiceBundle(
        store=store,
        self_model=self_model,
        space_graph=space_graph,
        constitution=constitution,
        composer=composer,
        evaluator=evaluator,
        identity=identity,
        amendments=amendments,
        validator=validator,
        bootstrap=bootstrap,
        capsule_builder=capsule_builder,
        citation_builder=citation_builder,
        space_id=space_id,
        constitution_id=BOOTSTRAP_CONSTITUTION_ID_V1,
        safe_mode=safe_mode,
        started_at_ms=now_ms,
        _owns_store=owns_store,
    )

    if publish_startup and bus is not None:
        publish = getattr(bus, "publish_simple", None)
        if callable(publish):
            try:
                publish(
                    TOPIC_SELFMODEL_STARTUP_COMPLETE,
                    {
                        "constitution_id": BOOTSTRAP_CONSTITUTION_ID_V1,
                        "version": bootstrap.snapshot.version,
                        "store_kind": type(store).__name__,
                        "safe_mode": safe_mode,
                        "started_at_ms": now_ms,
                    },
                )
            except Exception:
                logger.warning(
                    "selfmodel bundle: startup publish failed",
                    exc_info=True,
                )

    # M15.E1.I7: surface a one-shot WARNING + bus event when the
    # kernel boots into safe mode so operators can spot a degraded
    # constitution slice before the first turn arrives.
    if safe_mode:
        logger.warning(
            "selfmodel bundle: SAFE MODE active (constitution=%s); "
            "policy reads continue, amendments are blocked",
            BOOTSTRAP_CONSTITUTION_ID_V1,
        )
        if bus is not None:
            publish = getattr(bus, "publish_simple", None)
            if callable(publish):
                try:
                    publish(
                        TOPIC_KERNEL_SAFE_MODE_ACTIVE,
                        {
                            "constitution_id": BOOTSTRAP_CONSTITUTION_ID_V1,
                            "version": bootstrap.snapshot.version,
                            "started_at_ms": now_ms,
                            "reason": "constitution_unavailable",
                        },
                    )
                except Exception:
                    logger.debug(
                        "selfmodel bundle: safe_mode publish failed",
                        exc_info=True,
                    )

    logger.info(
        "selfmodel bundle: ready (store=%s, version=%s, safe_mode=%s)",
        type(store).__name__,
        bootstrap.snapshot.version,
        safe_mode,
    )
    return bundle
