"""
k1.tools.family.sse_adapters -- default :class:`ISsePublisher` implementations.

Three adapters cover the wiring matrix:

* :class:`NullSsePublisher`     -- discard-only no-op.  Used by headless
                                   tests and bootstrap configurations
                                   that disable SSE entirely.
* :class:`LoggingSsePublisher`  -- forward envelopes to the structured
                                   logger at ``INFO`` level.  Useful for
                                   diagnostic mode without a bus.
* :class:`BusSsePublisher`      -- forward envelopes to the K1 bus via
                                   the supplied callable.  The kernel
                                   constructs this with a thin closure
                                   over its async/event-port adapters
                                   so this module stays bridge-free.

All implementations conform to :class:`ISsePublisher` (defined in
:mod:`k1.tools.family.ports`).
"""

from __future__ import annotations

import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)


class NullSsePublisher:
    """``ISsePublisher`` that discards every envelope."""

    def publish(self, topic: str, payload: dict[str, Any]) -> None:  # noqa: D401
        return None


class LoggingSsePublisher:
    """``ISsePublisher`` that emits one structured log line per envelope."""

    __slots__ = ("_level",)

    def __init__(self, level: int = logging.INFO) -> None:
        self._level = level

    def publish(self, topic: str, payload: dict[str, Any]) -> None:
        logger.log(
            self._level,
            "family-tools sse: topic=%s id=%s actor=%s",
            topic,
            payload.get("id"),
            payload.get("actor"),
        )


class BusSsePublisher:
    """Forward envelopes to the K1 bus via the supplied callable.

    The callable receives ``(topic, payload)`` and is responsible for
    constructing the bus ``Envelope`` and calling
    ``bus.publish(envelope)``.  Keeping the bus shape behind a closure
    means this module does NOT import any concrete bus implementation,
    which preserves the family-tool layer's lightweight dependency set.
    """

    __slots__ = ("_forward",)

    def __init__(self, forward: Callable[[str, dict[str, Any]], None]) -> None:
        if forward is None:  # pragma: no cover -- defensive
            raise ValueError("BusSsePublisher requires a non-None forward callable.")
        self._forward = forward

    def publish(self, topic: str, payload: dict[str, Any]) -> None:
        try:
            self._forward(topic, payload)
        except Exception:  # pragma: no cover -- defensive
            logger.exception("BusSsePublisher forward failed: topic=%s", topic)
