"""
poc.k1_poc.bus.setup -- Bus infrastructure factory for the POC.

Thin wrappers around BusFactory that apply POC-specific defaults:
    - Ordered bus (TimingChain with default K1 prefix rules)
    - Mailbox router with two actors: front_half, back_half
    - SessionBusAdapter wired to the bus
    - MailboxConfig: capacity=64, priority_wfq=True

These functions are called once at boot time.  They return real K1
objects -- no mocks, no simulation.

Usage::

    from poc.k1_poc.bus.setup import create_poc_bus, create_poc_router, register_poc_actors

    bus = create_poc_bus()
    router = create_poc_router()
    front_mailbox, back_mailbox = register_poc_actors(router)
"""

from __future__ import annotations

import logging

from k1.bus.adapters.session_adapter import SessionBusAdapter
from k1.bus.factory import BusFactory
from k1.bus.impl.local_bus import LocalBus
from k1.bus.impl.local_mailbox import LocalMailbox, LocalMailboxRouter
from k1.bus.ports.mailbox import MailboxConfig
from poc.k1_poc.config import get_config

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# POC defaults -- now backed by config (V3 E0.2.3)
#
# These were previously stale hardcoded constants that duplicated values
# already read from config at runtime.  They are now thin wrappers that
# read from config/defaults.yaml so there is a single source of truth.
# New code should read from get_config().bus directly.
# ---------------------------------------------------------------------------


def _bus_cfg():
    return get_config().bus


# Actor IDs (backward-compat aliases; prefer get_config().bus.actor_*_id)
ACTOR_FRONT: str = "front_half"  # V3 E0.2.3: kept for test_m01_e2e compat
ACTOR_BACK: str = "back_half"  # V3 E0.2.3: kept for test_m01_e2e compat


def create_poc_bus(*, capture: bool = False) -> LocalBus:
    """
    Create an ordered LocalBus with default K1 timing rules.

    Args:
        capture: If True, record all published envelopes (for testing).

    Returns:
        LocalBus with TimingChain wired in.
    """
    bus = BusFactory.create_local_ordered(
        timeout_ms=get_config().bus.gap_timeout_ms,
        capture=capture,
    )
    logger.info(
        "create_poc_bus: LocalBus created (ordered=True, capture=%s, gap_timeout_ms=%d)",
        capture,
        get_config().bus.gap_timeout_ms,
    )
    return bus


def create_poc_router() -> LocalMailboxRouter:
    """
    Create a mailbox router (Python backend).

    Returns:
        Empty LocalMailboxRouter -- call register_poc_actors() next.
    """
    router = BusFactory.create_mailbox_router(backend="python")
    logger.info("create_poc_router: LocalMailboxRouter created (backend=python)")
    return router


def create_poc_session_adapter(bus: LocalBus) -> SessionBusAdapter:
    """
    Create a SessionBusAdapter wired to the given bus.

    SessionState events emitted via the adapter are automatically
    mapped to k1.session.{event_type} topics.

    Args:
        bus: The LocalBus to adapt.

    Returns:
        SessionBusAdapter instance.
    """
    adapter = SessionBusAdapter(bus)
    logger.info("create_poc_session_adapter: SessionBusAdapter wired to bus")
    return adapter


def register_poc_actors(
    router: LocalMailboxRouter,
) -> tuple[LocalMailbox, LocalMailbox]:
    """
    Register the Front and Back actors on the mailbox router.

    Both actors get bounded mailboxes with WFQ priority scheduling:
        capacity and priority_wfq loaded from config.

    Args:
        router: The mailbox router to register actors on.

    Returns:
        (front_mailbox, back_mailbox) tuple.
    """
    _cfg = get_config().bus
    config = MailboxConfig(
        capacity=_cfg.mailbox_capacity,
        priority_wfq=_cfg.priority_wfq,
    )
    front = router.register(_cfg.actor_front_id, config=config)
    back = router.register(_cfg.actor_back_id, config=config)
    logger.info(
        "register_poc_actors: registered front=%s back=%s (capacity=%d, wfq=%s)",
        _cfg.actor_front_id,
        _cfg.actor_back_id,
        _cfg.mailbox_capacity,
        _cfg.priority_wfq,
    )
    return front, back


__all__ = [
    "create_poc_bus",
    "create_poc_router",
    "create_poc_session_adapter",
    "register_poc_actors",
    "ACTOR_FRONT",
    "ACTOR_BACK",
    # V3 E0.2.3: POC_MAILBOX_CAPACITY and POC_GAP_TIMEOUT_MS removed.
    # Use get_config().bus.mailbox_capacity / .gap_timeout_ms instead.
]
