"""
poc.k1_poc.main -- Boot script for the K1 POC bus infrastructure.

Initializes all bus infrastructure in one call and returns a dict of
live components ready for use by higher-level modules.

Usage::

    from poc.k1_poc.main import boot

    infra = boot()
    bus = infra["bus"]
    bus.publish(some_envelope)

For testing::

    infra = boot(capture=True)
    bus = infra["bus"]
    bus.publish(some_envelope)
    assert len(bus.captured) == 1
"""

from __future__ import annotations

from typing import Any

from poc.k1_poc.bus.setup import (
    create_poc_bus,
    create_poc_router,
    create_poc_session_adapter,
    register_poc_actors,
)


def boot(*, capture: bool = False, ordered: bool = True) -> dict[str, Any]:
    """
    Initialize all POC bus infrastructure.

    Creates:
        - IBus (ordered with TimingChain, or unordered)
        - IMailboxRouter
        - SessionBusAdapter
        - front_half and back_half actor mailboxes

    Args:
        capture: If True, bus records all published envelopes.
        ordered: If True (default), use TimingChain with STRICT/RELAXED
                 ordering.  If False, use plain IBus without
                 TimingChain (simpler, no causal cascade).

    Returns:
        Dict with keys:
            bus:            IBus (with or without TimingChain)
            router:         IMailboxRouter
            adapter:        SessionBusAdapter
            front_mailbox:  IMailbox (actor_id="front_half")
            back_mailbox:   IMailbox (actor_id="back_half")
    """
    if ordered:
        bus = create_poc_bus(capture=capture)
    else:
        from k1.bus.factory import BusFactory

        bus = BusFactory.create_local(capture=capture)
    router = create_poc_router()
    adapter = create_poc_session_adapter(bus)
    front_mailbox, back_mailbox = register_poc_actors(router)

    return {
        "bus": bus,
        "router": router,
        "adapter": adapter,
        "front_mailbox": front_mailbox,
        "back_mailbox": back_mailbox,
    }
