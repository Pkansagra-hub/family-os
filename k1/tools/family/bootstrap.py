"""
k1.tools.family.bootstrap -- one-shot factory wiring the family-tool layer.

:func:`bootstrap_family_tools` is the single entrypoint the K1 kernel
calls during ``_startup_tier1`` (after ``shared_fabric`` is constructed)
to bring up the family-tool runtime end-to-end.  It:

1. Opens the K1-hot SQLite store (``K1FamilyStore``).
2. Constructs the shared :class:`EventEmitter` over the supplied SSE
   publisher (default :class:`NullSsePublisher`) and optional sync
   outbox (default ``None`` -- K0-free).
3. Constructs the :class:`ToolRegistry` over the shared connection and
   emitter, with the supplied Fabric for capability publication.
4. Registers every service class in ``service_classes`` -- this
   simultaneously creates each adapter's projection tables (DDL block)
   AND publishes its actions as Fabric capabilities.
5. Constructs the :class:`NativeToolProvider` over the registry and
   registers it with the Fabric provider registry under
   ``provider_type="LOCAL"`` / ``provider_id="k1_native_tools"`` so
   every family-tool capability resolves to it transparently.
6. Returns a :class:`FamilyToolsBundle` that the kernel stashes on
   ``KernelService`` so downstream surfaces (REST routers, planner,
   eval harness) can reach the live registry.

No part of this module imports ``bridge.*`` -- the optional K0
cold-sync outbox is reached via the injected :class:`ISyncOutbox`
implementation, which the kernel-side adapter constructs.

Plan reference: ``docs/plans/KERNEL_BOOTUP_PLAN.md`` §E15.0.10.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Iterable, List, Optional, Type

from k1.fabric.manifest_translator import (
    NATIVE_PROVIDER_ENDPOINT,
    NATIVE_PROVIDER_ID,
    NATIVE_PROVIDER_TYPE,
)
from k1.fabric.providers.native_tool_provider import NativeToolProvider
from k1.fabric.types import ProviderConfig
from k1.tools.family.base_service import BaseToolService
from k1.tools.family.events import EventEmitter
from k1.tools.family.policy import VisibilityPolicy, default_policy
from k1.tools.family.ports import ISsePublisher, ISyncOutbox
from k1.tools.family.registry import ToolRegistry
from k1.tools.family.sse_adapters import NullSsePublisher
from k1.tools.family.storage import DEFAULT_DB_PATH, K1FamilyStore

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class FamilyToolsBundle:
    """The set of live objects produced by :func:`bootstrap_family_tools`."""

    store: K1FamilyStore
    emitter: EventEmitter
    tool_registry: ToolRegistry
    native_provider: NativeToolProvider
    capability_names: List[str] = field(default_factory=list)

    def close(self) -> None:
        """Release the SQLite connection (kernel-side shutdown hook)."""

        self.store.close()


def _register_provider_with_fabric(
    fabric: Any,
    provider: NativeToolProvider,
) -> None:
    """Register ``provider`` with the Fabric provider registry.

    The Fabric in the workspace exposes both a provider *factory*
    (handler-keyed, used to lazily construct provider instances) and a
    provider *registry* (instance-keyed, used to dispatch by
    provider_id).  We register the live instance with the latter so the
    pipeline can resolve ``capability.provider_id == "k1_native_tools"``
    without round-tripping through the factory.

    The function is defensive about which surfaces actually exist:
    missing attributes are logged but do not abort boot, so this module
    keeps working as the Fabric surface evolves.
    """

    # Factory hook -- some test fabrics expose ``_provider_factory``.
    factory = getattr(fabric, "_provider_factory", None)
    if factory is not None and hasattr(factory, "register_handler"):
        try:
            factory.register_handler(
                NATIVE_PROVIDER_TYPE,
                lambda config, **_deps: provider,  # noqa: ARG005 -- factory contract
            )
            logger.info(
                "Family-tools: registered NativeToolProvider factory under provider_type=%s",
                NATIVE_PROVIDER_TYPE,
            )
        except Exception:  # pragma: no cover -- defensive
            logger.exception("Family-tools: provider factory registration failed")

    # Instance registry hook.
    registry = getattr(fabric, "_provider_registry", None)
    if registry is None:
        # Modern Fabric facades may expose this via a public attribute instead.
        registry = getattr(fabric, "provider_registry", None)
    if registry is not None and hasattr(registry, "register_provider"):
        try:
            registry.register_provider(provider)
            logger.info(
                "Family-tools: registered NativeToolProvider instance under provider_id=%s",
                NATIVE_PROVIDER_ID,
            )
        except Exception:  # pragma: no cover -- defensive
            logger.exception("Family-tools: provider instance registration failed")


def bootstrap_family_tools(
    fabric: Any,
    *,
    sse_publisher: Optional[ISsePublisher] = None,
    sync_outbox: Optional[ISyncOutbox] = None,
    db_path: str = DEFAULT_DB_PATH,
    service_classes: Iterable[Type[BaseToolService]] = (),
    policy: Optional[VisibilityPolicy] = None,
    bus_publisher: Optional[Any] = None,
) -> FamilyToolsBundle:
    """Wire the entire family-tool layer.

    Args
    ----
    fabric:
        The shared :class:`Fabric` produced by ``FabricFactory``.  Used
        for two things: (1) registering each adapter's
        :class:`CapabilityContract`s on its ``capability_registry``,
        (2) registering the live :class:`NativeToolProvider` on its
        provider registry.  Pass ``None`` only in tests that explicitly
        exercise the family-tool layer without Fabric.
    sse_publisher:
        ``ISsePublisher`` for audit emission.  Defaults to
        :class:`NullSsePublisher` so headless boots stay silent.
    sync_outbox:
        Optional K0 cold-sync outbox.  Pass ``None`` (default) for
        K1-only deployments.
    db_path:
        Filesystem path for the K1-hot SQLite store.  Created with WAL
        journaling and FK enforcement.
    service_classes:
        Iterable of :class:`BaseToolService` subclasses to instantiate
        and register.  Order is preserved (useful when one adapter
        references another via ``can_reference``).
    policy:
        Optional :class:`VisibilityPolicy` override.  Defaults to
        :func:`default_policy`.
    bus_publisher:
        Optional secondary publisher used by :class:`BaseToolService`
        for thin per-dispatch observability events
        (``k1.tools.<adapter>.dispatch.<outcome>.v1``).

    Returns
    -------
    A :class:`FamilyToolsBundle` carrying every live object.  The
    kernel keeps a strong reference so the SQLite connection survives
    the call.
    """

    publisher: ISsePublisher = sse_publisher or NullSsePublisher()
    pol = policy or default_policy()

    store = K1FamilyStore(db_path)
    emitter = EventEmitter(publisher, sync_outbox)

    registry = ToolRegistry(
        store.conn,
        emitter,
        fabric=fabric,
        policy=pol,
        bus_publisher=bus_publisher,
    )

    services = registry.register_all(service_classes)

    # Construct the in-process provider over the live registry.
    provider_config = ProviderConfig(
        provider_id=NATIVE_PROVIDER_ID,
        provider_type=NATIVE_PROVIDER_TYPE,
        endpoint=NATIVE_PROVIDER_ENDPOINT,
        max_execution_ms=30_000,
    )
    provider = NativeToolProvider(provider_config, registry=registry)

    if fabric is not None:
        _register_provider_with_fabric(fabric, provider)

    capability_names = [
        cap
        for svc in services
        for cap in provider.capabilities()
        if cap.endswith(f".{svc.DEFINITION.adapter_id}.{cap.rsplit('.', 1)[-1]}")
    ]
    # The list-comprehension above is a sanity collection; in practice
    # `provider.capabilities()` already enumerates the union and is the
    # canonical answer.  Use the simpler direct call as the published list.
    capability_names = provider.capabilities()

    logger.info(
        "Family-tools bootstrap complete: adapters=%s capabilities=%d db_path=%s",
        registry.adapter_ids(),
        len(capability_names),
        db_path,
    )

    return FamilyToolsBundle(
        store=store,
        emitter=emitter,
        tool_registry=registry,
        native_provider=provider,
        capability_names=capability_names,
    )
