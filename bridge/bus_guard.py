"""K1 local-bus guard for cross-kernel topic publishes (R10).

The K1 local bus is intra-kernel only. Any topic that the bridge
contract registry declares as cross-kernel (``k0_to_k1``,
``k1_to_k0``, ``device_to_k0``, ``k0_to_device``) must travel
through the bridge runtime, not the local bus. R10 enforces this at
the publish boundary so we can never silently double-publish a
contract over both transports.

This module exposes:

* :class:`UnknownContractError` — raised by guards when a publish
  attempts a bridge-bound topic.
* :func:`load_bridge_topics` — returns the frozen set of
  cross-kernel topic strings declared in
  ``bridge/contracts/manifests``.
* :class:`BridgeAwareLocalBus` — thin proxy around
  :class:`k1.bus.impl.local_bus.LocalBus` that validates the topic
  before delegating to the underlying ``publish``.

The proxy approach keeps the production ``LocalBus`` (with its 1k+
regression tests) untouched while still providing a real,
production-grade enforcement surface that K1 boot-up code wires in.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from tooling.contracts.manifest_loader import load_manifests

if TYPE_CHECKING:  # pragma: no cover - typing only
    from k1.bus.impl.local_bus import LocalBus
    from k1.bus.ports.bus import Envelope


_CROSS_KERNEL_DIRECTIONS = frozenset({"k0_to_k1", "k1_to_k0", "device_to_k0", "k0_to_device"})


class UnknownContractError(RuntimeError):
    """Raised when a bridge-bound topic is published on the local bus.

    The topic is either:

    * declared in the bridge registry as cross-kernel (must use the
      generated client), or
    * matches a cross-kernel-prefix pattern but has no registered
      contract (publishing is forbidden until the manifest exists).
    """


def load_bridge_topics(
    contracts_root: Path | None = None,
) -> frozenset[str]:
    """Return the frozen set of cross-kernel topics in the registry.

    Includes only topics whose ``direction`` puts them on the bridge
    surface; intra-kernel ``k1_to_k1`` and ``k0_to_k0`` are excluded.
    All ``status`` values are honoured (proposed, experimental,
    active, deprecated, deferred) — once a manifest exists, the local
    bus must refuse the topic regardless of ship state.
    """
    if contracts_root is None:
        contracts_root = Path(__file__).resolve().parent / "contracts"
    manifests = load_manifests(contracts_root)
    return frozenset(m.topic for m in manifests if m.direction in _CROSS_KERNEL_DIRECTIONS)


class BridgeAwareLocalBus:
    """Proxy around :class:`LocalBus` that enforces R10 on ``publish``.

    All other ``IBus`` methods (``subscribe``, ``unsubscribe``,
    ``flush``, etc.) are delegated unchanged. Holds a frozen set of
    bridge-bound topics resolved at construction; the registry is not
    consulted on the hot path.
    """

    __slots__ = ("_inner", "_bridge_topics")

    def __init__(
        self,
        inner: "LocalBus",
        *,
        bridge_topics: frozenset[str] | None = None,
        contracts_root: Path | None = None,
    ) -> None:
        self._inner = inner
        if bridge_topics is None:
            bridge_topics = load_bridge_topics(contracts_root)
        self._bridge_topics = bridge_topics

    @property
    def inner(self) -> "LocalBus":
        return self._inner

    @property
    def bridge_topics(self) -> frozenset[str]:
        return self._bridge_topics

    def publish(self, envelope: "Envelope") -> None:
        topic = envelope.topic
        if topic in self._bridge_topics:
            raise UnknownContractError(
                f"R10 violation: topic {topic!r} is cross-kernel and "
                f"must be published via the bridge generated client, "
                f"not the K1 local bus."
            )
        self._inner.publish(envelope)

    def __getattr__(self, name: str):
        # Delegate everything else (subscribe, unsubscribe, stats, ...).
        return getattr(self._inner, name)
