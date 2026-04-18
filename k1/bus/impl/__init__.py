"""
k1.bus.impl -- Concrete implementations of the bus ports.

Provides:
    LocalBus              -- In-process IBus with trie routing, WFQ, sequence gen
    LocalMailbox          -- Bounded per-actor mailbox with WFQ priority
    LocalMailboxRouter    -- Router managing many LocalMailboxes
    TopicTrie             -- Radix trie for O(k) topic matching
    BusStats              -- Observable bus statistics
    RustBusAdapter        -- IBus backed by ``k1_bus_core`` Rust crate (opt-in)
    RustMailboxAdapter    -- IMailbox backed by Rust crate (opt-in)
    RustMailboxRouterAdapter -- IMailboxRouter backed by Rust crate (opt-in)

Rust adapters are imported lazily and only re-exported when the
``k1_bus_core`` extension is importable. Consumers should normally use
``BusFactory`` from ``k1.bus.factory`` rather than instantiating adapters
directly.
"""

from k1.bus.impl.local_bus import BusStats, LocalBus
from k1.bus.impl.local_mailbox import LocalMailbox, LocalMailboxRouter
from k1.bus.impl.topic_trie import TopicTrie

__all__ = [
    "LocalBus",
    "LocalMailbox",
    "LocalMailboxRouter",
    "TopicTrie",
    "BusStats",
]

# P6.4 (finding B): expose Rust adapters from ``k1.bus.impl`` for parity
# with the top-level ``k1.bus`` package. Import is best-effort -- when the
# Rust crate isn't built, only the Python implementations are re-exported.
try:
    from k1.bus.impl.rust_bus_adapter import RustBusAdapter
    from k1.bus.impl.rust_mailbox_adapter import RustMailboxAdapter, RustMailboxRouterAdapter
except ImportError:  # pragma: no cover - exercised only when Rust unavailable
    pass
else:
    __all__ += [
        "RustBusAdapter",
        "RustMailboxAdapter",
        "RustMailboxRouterAdapter",
    ]
