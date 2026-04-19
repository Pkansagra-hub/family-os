"""Backward-compatible kernel bootstrap — thin delegate to KernelService.

P4B.1: ``start_kernel()`` / ``stop_kernel()`` now delegate to
``KernelService.startup()`` + ``create_session()`` / ``destroy_session()``
+ ``shutdown()``.  The ``KernelRuntime`` dataclass is preserved for
backward compatibility with ``chat_repl.py`` and ``runner.py``.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from k1.bus.ports.bus import IBus
from k1.bus.ports.mailbox import IMailbox, IMailboxRouter
from k1.concierge.config.kernel import KernelConfig

if TYPE_CHECKING:
    # Type-only imports keep runtime dep graph unchanged while still
    # giving static type-checkers proper coverage on KernelRuntime.
    from k1.concierge.ledger.store import ILedgerStore
    from k1.concierge.ports import ILLMPort, IStatePort
    from k1.kernel.ports.orchestrator_port import IOrchestratorPort
    from k1.planner.types import HILCoordinatorLike

logger = logging.getLogger(__name__)


@dataclass
class KernelRuntime:
    """Live kernel runtime object returned by start_kernel().

    Backward-compat facade: fields are populated from
    ``KernelService`` (Tier 1) + ``SessionInstance`` (Tier 2).
    """

    config: KernelConfig
    bus: IBus
    router: IMailboxRouter
    adapter: Any = None
    front_mailbox: IMailbox | None = None
    back_mailbox: IMailbox | None = None
    session_state: "IStatePort | None" = None
    capability_registry: Any = None
    model: "ILLMPort | None" = None
    fsm: Any = None
    front_dispatcher: Any = None
    back_dispatcher: Any = None
    experience_layer: Any = None
    delta_aggregator: Any = None
    delta_applicator: Any = None
    hitl_coordinator: "HILCoordinatorLike | None" = None
    orchestrator: "IOrchestratorPort | None" = None
    front_subscriptions: list[Any] = field(default_factory=list)
    back_subscriptions: list[Any] = field(default_factory=list)
    consumer_task: asyncio.Task | None = None
    ledger: Any = None
    ledger_store: "ILedgerStore | None" = None
    dead_letter_consumer: Any = None
    started: bool = False
    weave_batcher: Any = None
    weave_policy: Any = None
    activity_tracker: Any = None
    front_ctx: Any = None
    back_ctx: Any = None

    # Internal: KernelService reference for stop_kernel()
    _service: Any = field(default=None, repr=False)
    _session_id: str | None = field(default=None, repr=False)


async def start_kernel(config: KernelConfig | None = None) -> KernelRuntime:
    """Start the Concierge kernel via KernelService (P4B.1).

    Creates a single-session kernel for backward compatibility with
    ``chat_repl.py`` and ``runner.py``.
    """
    from k1.kernel.service import KernelService

    cfg = config or KernelConfig()

    session_id = cfg.session_id or f"kernel-{uuid.uuid4().hex[:8]}"

    svc = KernelService(cfg)
    await svc.startup()
    session = await svc.create_session(session_id)

    # Map SessionInstance → KernelRuntime for backward compat
    concierge = session.concierge  # ConciergeRuntime
    runtime = KernelRuntime(
        config=cfg,
        bus=session.bus,
        router=session.router,
        adapter=None,
        front_mailbox=session.front_mailbox,
        back_mailbox=session.back_mailbox,
        session_state=session.session_state,
        capability_registry=None,
        model=getattr(concierge, "model", None),
        fsm=concierge.fsm,
        front_dispatcher=session.front_dispatcher,
        back_dispatcher=session.back_dispatcher,
        experience_layer=session.experience_layer,
        delta_aggregator=session.delta_aggregator,
        delta_applicator=session.delta_applicator,
        hitl_coordinator=session.hitl_coordinator,
        orchestrator=svc._orchestrator,
        front_subscriptions=concierge.front_subscriptions,
        consumer_task=session.consumer_task,
        ledger=session.ledger,
        ledger_store=session.ledger_store,
        dead_letter_consumer=session.dead_letter_consumer,
        started=True,
        front_ctx=session.front_ctx,
        back_ctx=session.back_ctx,
        _service=svc,
        _session_id=session_id,
    )
    logger.info("start_kernel: session %s ready (via KernelService)", session_id)
    return runtime


async def stop_kernel(runtime: KernelRuntime) -> None:
    """Stop the kernel via KernelService (P4B.1)."""
    svc = runtime._service
    if svc is None:
        logger.warning("stop_kernel: no KernelService reference, skipping")
        return
    if runtime._session_id:
        try:
            await svc.destroy_session(runtime._session_id)
        except KeyError:
            pass  # already destroyed
    await svc.shutdown()
    runtime.started = False
    logger.info("stop_kernel: kernel stopped")


# P4B.5: Backward-compat re-exports of _FabricGatewayAdapter / _StateReadAdapter /
# _DeltaEmitAdapter / _build_delta_applicator removed. The three internal adapter
# classes were deleted (they only existed to feed the deleted OrchestratorStub).
# _build_delta_applicator remains importable from k1.concierge.factory directly.
