"""
k1.tools.family.registry -- ``ToolRegistry`` for family-tool services.

The registry is the single source of truth used by:

* :class:`k1.fabric.providers.native_tool_provider.NativeToolProvider` --
  consumes the registry via :class:`IToolRegistryReader` to look up
  services on inbound capability requests.

* :class:`k1.fabric.manifest_translator.register_definition` -- called
  on every ``register_class`` so each :class:`ActionSpec` becomes a
  Fabric :class:`CapabilityContract`.

* :class:`ManifestGenerator` and the REST router factory -- iterate
  registered services to publish UI / OpenAPI manifests.

Construction order is::

    store    = K1FamilyStore(...)
    emitter  = EventEmitter(sse_publisher, sync_outbox)
    policy   = default_policy()
    registry = ToolRegistry(store.conn, emitter, fabric=shared_fabric, policy=policy)
    registry.register_all([CalendarToolService, HealthToolService, ...])

Plan reference: ``docs/plans/KERNEL_BOOTUP_PLAN.md`` §E15.0.7.
"""

from __future__ import annotations

import logging
import sqlite3
from typing import Any, Iterable, List, Optional, Type

from k1.fabric.manifest_translator import register_definition
from k1.tools.family.base_service import BaseToolService
from k1.tools.family.events import EventEmitter
from k1.tools.family.idem import IdempotencyStore
from k1.tools.family.policy import VisibilityPolicy, default_policy
from k1.tools.family.ports import IToolService

logger = logging.getLogger(__name__)


class ToolRegistry:
    """Owns the lifecycle of every family-tool service in a kernel process.

    The registry instantiates a singleton :class:`IdempotencyStore`
    against the shared SQLite connection, then constructs each service
    class with the standard (conn, emitter, policy, idem) dependencies.
    The same instance is exposed through the :class:`IToolRegistryReader`
    surface so :class:`NativeToolProvider` can route inbound capability
    requests by adapter id.
    """

    __slots__ = (
        "_conn",
        "_emitter",
        "_policy",
        "_fabric",
        "_idem",
        "_services",
        "_bus_publisher",
    )

    # ------------------------------------------------------------------ #
    # Construction
    # ------------------------------------------------------------------ #

    def __init__(
        self,
        conn: sqlite3.Connection,
        emitter: EventEmitter,
        *,
        fabric: Any | None = None,
        policy: Optional[VisibilityPolicy] = None,
        bus_publisher: Optional[Any] = None,
    ) -> None:
        self._conn = conn
        self._emitter = emitter
        self._policy = policy or default_policy()
        self._fabric = fabric
        self._idem = IdempotencyStore(conn)
        self._bus_publisher = bus_publisher
        self._services: dict[str, BaseToolService] = {}

    # ------------------------------------------------------------------ #
    # Registration
    # ------------------------------------------------------------------ #

    def register_class(self, service_cls: Type[BaseToolService]) -> BaseToolService:
        """Instantiate, register, and Fabric-publish a service class.

        The service's ``DEFINITION.adapter_id`` becomes the registry
        key.  Registering the same adapter_id twice raises ``ValueError``
        -- adapter authors should re-use the existing instance rather
        than producing a second one.
        """

        if not hasattr(service_cls, "DEFINITION"):
            raise TypeError(f"{service_cls.__name__} has no DEFINITION; cannot register.")

        svc = service_cls(
            self._conn,
            self._emitter,
            self._policy,
            self._idem,
            bus_publisher=self._bus_publisher,
        )

        adapter_id = svc.DEFINITION.adapter_id
        if adapter_id in self._services:
            raise ValueError(f"family-tool adapter {adapter_id!r} already registered")

        self._services[adapter_id] = svc

        # Fabric registration (optional -- offline tests pass fabric=None).
        if self._fabric is not None:
            registry = getattr(self._fabric, "capability_registry", None)
            if registry is None:
                logger.warning(
                    "ToolRegistry: shared_fabric has no capability_registry attribute; "
                    "skipping Fabric registration for adapter %s.",
                    adapter_id,
                )
            else:
                names = register_definition(svc.DEFINITION, registry)
                logger.info(
                    "ToolRegistry: registered %d Fabric capabilities for adapter %s: %s",
                    len(names),
                    adapter_id,
                    names,
                )

        logger.info("ToolRegistry: registered family adapter %s", adapter_id)
        return svc

    def register_all(
        self, service_classes: Iterable[Type[BaseToolService]]
    ) -> List[BaseToolService]:
        """Register every class in ``service_classes`` in iteration order."""

        return [self.register_class(cls) for cls in service_classes]

    # ------------------------------------------------------------------ #
    # IToolRegistryReader surface
    # ------------------------------------------------------------------ #

    def get_service(self, adapter_id: str) -> Optional[IToolService]:
        return self._services.get(adapter_id)

    def adapter_ids(self) -> List[str]:
        return sorted(self._services.keys())

    # ------------------------------------------------------------------ #
    # Other accessors
    # ------------------------------------------------------------------ #

    @property
    def services(self) -> dict[str, BaseToolService]:
        """Return the underlying ``adapter_id -> service`` mapping (live view)."""

        return self._services

    @property
    def idempotency_store(self) -> IdempotencyStore:
        """Return the shared :class:`IdempotencyStore` (used by tests)."""

        return self._idem
