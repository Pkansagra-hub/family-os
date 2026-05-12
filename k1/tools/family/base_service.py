"""
k1.tools.family.base_service -- ``BaseToolService`` dispatch backbone.

Adapter authors subclass :class:`BaseToolService` and provide:

* ``DEFINITION``  -- the class-level :class:`ToolDefinition`.
* per-action methods named after each :class:`ActionSpec.name` -- e.g.
  ``async def list_events(self, params, ctx) -> dict``.

In return they get -- uniformly across every family adapter -- the
following machinery for free:

* Idempotency replay (`idempotent` actions + `ctx.idempotency_key`).
* Role gate (`min_role` + `allowed_roles`).
* Safety-band gate (`min_band`, via :class:`VisibilityPolicy`).
* Tables provisioning (runs ``DEFINITION.tables_sql`` exactly once).
* Audit emission on success (via :class:`EventEmitter.emit_entity_write`
  or :meth:`emit_write` for non-entity payloads).
* Uniform error envelope: every failure is returned as
  ``{"success": False, "error_code": ..., "error_message": ...}``
  rather than raised, so the Fabric pipeline can translate it
  consistently.

Plan reference: ``docs/plans/KERNEL_BOOTUP_PLAN.md`` §E15.0.6.
"""

from __future__ import annotations

import inspect
import logging
import sqlite3
from typing import Any, ClassVar, Optional

from k1.tools.family.base import (
    BaseEntity,
    WriteContext,
    role_satisfies,
)
from k1.tools.family.definition import ActionSpec, ToolDefinition
from k1.tools.family.events import EventEmitter
from k1.tools.family.idem import IdempotencyStore
from k1.tools.family.policy import VisibilityPolicy

logger = logging.getLogger(__name__)


# Topic suffix used for bus-level observability on every dispatch.  The
# kernel bus subscribes (optionally) to ``k1.tools.*.dispatch.*`` to
# track which adapters are receiving traffic.
_DISPATCH_TOPIC_FMT: str = "k1.tools.{adapter_id}.dispatch.{outcome}.v1"


class BaseToolService:
    """Common dispatch / policy / audit / persistence wiring for family tools.

    Subclasses MUST set ``DEFINITION``; the constructor will refuse to
    initialise without it.  Subclasses MAY override
    ``_resolve_handler(action_name)`` if they want a different method
    naming convention than ``action.name`` -> ``self.<action.name>``.
    """

    # Subclasses populate.
    DEFINITION: ClassVar[ToolDefinition]
    ENTITY_CLASSES: ClassVar[dict[str, type[BaseEntity]]] = {}

    __slots__ = ("_conn", "_emitter", "_policy", "_idem", "_bus_publisher")

    # ------------------------------------------------------------------ #
    # Construction
    # ------------------------------------------------------------------ #

    def __init__(
        self,
        conn: sqlite3.Connection,
        emitter: EventEmitter,
        policy: VisibilityPolicy,
        idem: IdempotencyStore,
        *,
        bus_publisher: Optional[Any] = None,
    ) -> None:
        if not hasattr(self, "DEFINITION") or self.DEFINITION is None:
            raise TypeError(f"{type(self).__name__} must declare a class-level DEFINITION.")

        self._conn = conn
        self._emitter = emitter
        self._policy = policy
        self._idem = idem
        self._bus_publisher = bus_publisher

        # Apply per-adapter DDL exactly once against the shared connection.
        # ToolDefinition.tables_sql already enforces P7 (must contain a
        # ``<adapter_id>_schema_version`` table).
        with self._conn:
            self._conn.executescript(self.DEFINITION.tables_sql)

    # ------------------------------------------------------------------ #
    # Public surface
    # ------------------------------------------------------------------ #

    @property
    def adapter_id(self) -> str:
        """Convenience accessor used by registry / manifest tooling."""

        return self.DEFINITION.adapter_id

    async def dispatch(
        self,
        action: str,
        params: dict[str, Any],
        ctx: WriteContext,
    ) -> dict[str, Any]:
        """Route ``action`` through the standard policy / idem / audit pipeline.

        Returns a JSON-serialisable result dict.  On any failure the
        return shape is::

            {"success": False, "error_code": str, "error_message": str}

        Exceptions raised by the handler are caught and translated into
        the same shape; the only exceptions surfaced to the caller are
        programmer errors detected during construction (missing
        DEFINITION etc).
        """

        adapter_id = self.adapter_id
        spec = self.DEFINITION.find_action(action)

        if spec is None:
            return self._fail(
                "action_not_found",
                f"Adapter {adapter_id!r} does not declare action {action!r}",
                ctx,
            )

        # ---- gate 1: role + safety band -------------------------------
        if not self._policy.check_role(spec, ctx):
            return self._fail(
                "role_denied",
                f"Role {ctx.role!r} not in allowed_roles for {action!r}",
                ctx,
                adapter_id=adapter_id,
                action=action,
            )
        if spec.min_role and not role_satisfies(ctx.role, spec.min_role):
            return self._fail(
                "role_below_min",
                f"Role {ctx.role!r} below min_role {spec.min_role!r} for {action!r}",
                ctx,
                adapter_id=adapter_id,
                action=action,
            )
        if not self._policy.check_band(spec, ctx):
            return self._fail(
                "band_denied",
                f"Band {ctx.band!r} below min_band {spec.min_band!r} for {action!r}",
                ctx,
                adapter_id=adapter_id,
                action=action,
            )

        # ---- gate 2: idempotency replay -------------------------------
        if spec.idempotent and ctx.idempotency_key:
            cached = self._idem.lookup(adapter_id, action, ctx.idempotency_key, ctx.space_id)
            if cached is not None:
                # Replay verbatim; flag the result so observers can tell.
                replay = dict(cached["result"])
                replay["idempotent_replay"] = True
                self._publish_bus(adapter_id, action, "replay")
                return replay

        # ---- gate 3: handler dispatch ---------------------------------
        handler = self._resolve_handler(spec)
        if handler is None:
            return self._fail(
                "handler_missing",
                f"No method on {type(self).__name__} for action {action!r}",
                ctx,
                adapter_id=adapter_id,
                action=action,
            )

        try:
            outcome = handler(params, ctx)
            if inspect.isawaitable(outcome):
                result = await outcome
            else:
                result = outcome
        except Exception as exc:
            logger.exception(
                "BaseToolService dispatch failure: adapter=%s action=%s",
                adapter_id,
                action,
            )
            self._publish_bus(adapter_id, action, "error")
            return self._fail(
                "dispatch_failed",
                f"{type(exc).__name__}: {exc}",
                ctx,
                adapter_id=adapter_id,
                action=action,
            )

        if not isinstance(result, dict):
            self._publish_bus(adapter_id, action, "error")
            return self._fail(
                "invalid_result",
                f"Handler for {action!r} returned {type(result).__name__}; expected dict",
                ctx,
                adapter_id=adapter_id,
                action=action,
            )

        # Successful dispatch: normalise the success flag.
        result.setdefault("success", True)

        # ---- gate 4: idempotency record + bus observability -----------
        if spec.idempotent and ctx.idempotency_key:
            try:
                self._idem.record(
                    adapter_id,
                    action,
                    ctx.idempotency_key,
                    ctx.space_id,
                    "ok" if result.get("success") else "err",
                    result,
                )
            except Exception:  # pragma: no cover -- defensive
                logger.exception(
                    "idempotency record failed adapter=%s action=%s", adapter_id, action
                )

        self._publish_bus(adapter_id, action, "ok")
        return result

    # ------------------------------------------------------------------ #
    # Helpers exposed to subclasses
    # ------------------------------------------------------------------ #

    def emit_entity_write(
        self,
        op: str,
        entity: BaseEntity,
        ctx: WriteContext,
        *,
        action: ActionSpec,
    ) -> str:
        """Convenience: emit a typed entity-write event through the EventEmitter."""

        return self._emitter.emit_entity_write(self.DEFINITION, action, op, entity, ctx)

    def emit_write(
        self,
        action: ActionSpec,
        payload: dict[str, Any],
        ctx: WriteContext,
    ) -> str:
        """Convenience: emit an arbitrary write envelope through the EventEmitter."""

        return self._emitter.emit_write(self.DEFINITION, action, payload, ctx)

    # ------------------------------------------------------------------ #
    # Overridable hooks
    # ------------------------------------------------------------------ #

    def _resolve_handler(self, spec: ActionSpec):
        """Return the bound method that implements ``spec`` (or ``None``).

        Default resolution: look up ``self.<spec.name>``.  Subclasses
        may override to support custom naming or to handle dynamic
        actions.
        """

        return getattr(self, spec.name, None)

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #

    def _fail(
        self,
        code: str,
        message: str,
        ctx: WriteContext,
        *,
        adapter_id: Optional[str] = None,
        action: Optional[str] = None,
    ) -> dict[str, Any]:
        """Return the uniform failure envelope."""

        envelope: dict[str, Any] = {
            "success": False,
            "error_code": code,
            "error_message": message,
            "trace_id": ctx.trace_id,
        }
        if adapter_id is not None:
            envelope["adapter_id"] = adapter_id
            self._publish_bus(adapter_id, action or "?", "error")
        return envelope

    def _publish_bus(self, adapter_id: str, action: str, outcome: str) -> None:
        """Emit a thin observability envelope on the K1 bus (when wired).

        ``outcome`` is one of ``"ok" | "error" | "replay"``.  The bus
        publisher is optional -- :class:`NullSsePublisher` and the
        default boot wiring leave ``bus_publisher=None`` for headless
        deployments, in which case this is a no-op.
        """

        if self._bus_publisher is None:
            return
        try:
            topic = _DISPATCH_TOPIC_FMT.format(adapter_id=adapter_id, outcome=outcome)
            self._bus_publisher.publish(
                topic, {"adapter_id": adapter_id, "action": action, "outcome": outcome}
            )
        except Exception:  # pragma: no cover -- defensive
            logger.exception(
                "bus observability publish failed adapter=%s action=%s", adapter_id, action
            )
