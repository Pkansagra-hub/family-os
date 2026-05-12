"""
k1.tools.family.ports -- structural protocols for the family-tool surface.

These ``typing.Protocol`` declarations are the contracts that decouple
the family-tool layer from concrete K1 infrastructure (SSE publisher,
bridge sync outbox, session-state reader, etc.).  Every adapter in
``k1.tools.family`` -- and ``NativeToolProvider`` itself -- depends on
these protocols, never on concrete classes, so the wiring layer
(``k1/kernel`` boot) can swap implementations freely (test stubs vs.
production adapters) without touching tool code.

The protocols are deliberately minimal: they capture only the
operations actually consumed by the family-tool runtime, not the full
surface of the underlying K1 component.
"""

from __future__ import annotations

from typing import Any, Optional, Protocol, runtime_checkable

from k1.tools.family.base import WriteContext
from k1.tools.family.definition import ToolDefinition

# ---------------------------------------------------------------------------
# IToolService -- adapter contract
# ---------------------------------------------------------------------------


@runtime_checkable
class IToolService(Protocol):
    """Structural contract every family-tool service implements.

    A service publishes a class-level ``DEFINITION`` (its
    ``ToolDefinition``) and exposes a single ``dispatch`` coroutine that
    routes by action name.  ``NativeToolProvider`` invokes services
    through this protocol -- it never imports concrete service classes.

    Service authors typically inherit ``k1.tools.family.base_service.
    BaseToolService`` (see §E15.0.6) which provides the dispatch table,
    ACL hooks, and EventEmitter wiring; only ``DEFINITION`` and the
    per-action methods are author-supplied.
    """

    DEFINITION: ToolDefinition

    async def dispatch(
        self,
        action: str,
        params: dict[str, Any],
        ctx: WriteContext,
    ) -> dict[str, Any]:
        """Execute ``action`` with ``params`` under ``ctx``.

        Returns:
            JSON-serialisable result dict.  For read actions the dict
            typically contains ``{"items": [...], "count": int}``.
        """
        ...


# ---------------------------------------------------------------------------
# IToolRegistryReader -- lookup contract used by NativeToolProvider
# ---------------------------------------------------------------------------


@runtime_checkable
class IToolRegistryReader(Protocol):
    """Read-only view over the family-tool service registry.

    Implementations are typically maintained by the K1 boot wiring
    (see §E15.0.10) which registers each ``IToolService`` instance under
    its ``adapter_id`` after constructing it with the shared
    ``EventEmitter`` and ``K1FamilyStore``.
    """

    def get_service(self, adapter_id: str) -> Optional[IToolService]:
        """Return the registered service, or ``None`` if unknown."""
        ...

    def adapter_ids(self) -> list[str]:
        """Return the sorted list of currently registered adapter ids."""
        ...


# ---------------------------------------------------------------------------
# ISsePublisher -- in-process pub/sub used by EventEmitter
# ---------------------------------------------------------------------------


@runtime_checkable
class ISsePublisher(Protocol):
    """Minimum surface ``EventEmitter`` needs from the K1 SSE layer.

    Implementations MUST be non-blocking and SHOULD swallow downstream
    backpressure errors (the emitter logs and continues -- SSE delivery
    is best-effort, never authoritative).
    """

    def publish(self, topic: str, payload: dict[str, Any]) -> None:
        """Publish ``payload`` on ``topic``.  Best-effort, fire-and-forget."""
        ...


# ---------------------------------------------------------------------------
# ISyncOutbox -- optional K0 cold-sync hand-off
# ---------------------------------------------------------------------------


@runtime_checkable
class ISyncOutbox(Protocol):
    """Optional K0 cold-sync hand-off for family-tool events.

    Under the K1-hot / K0-optional pivot (M15 R-2) the K0 store is no
    longer in the hot path.  When a sync outbox is wired the
    ``EventEmitter`` enqueues an envelope for asynchronous transmission
    via the existing M14 bridge outbox; when no outbox is wired, the
    family tools still operate -- they just produce no K0 mirror.
    """

    def enqueue(self, envelope: dict[str, Any]) -> None:
        """Enqueue a sync envelope.  Returns immediately; transmission is async."""
        ...


# ---------------------------------------------------------------------------
# IPolicyEvaluator -- optional pluggable policy backend
# ---------------------------------------------------------------------------


@runtime_checkable
class IPolicyEvaluator(Protocol):
    """Optional extension hook for richer policy backends.

    The default in-package ``VisibilityPolicy`` evaluator covers role +
    band + visibility checks.  Apps with bespoke rules (e.g. consent
    sub-systems) can inject an alternate evaluator at boot time without
    forking the ACL module.
    """

    def allow_read(
        self,
        row: dict[str, Any],
        ctx: WriteContext,
    ) -> bool:
        """Return True iff ``ctx`` may read ``row``."""
        ...

    def allow_write(
        self,
        action_name: str,
        ctx: WriteContext,
    ) -> bool:
        """Return True iff ``ctx`` may execute the named write/delete action."""
        ...
