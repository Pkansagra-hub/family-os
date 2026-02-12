"""
k1.orchestrator.adapters.event_subscription_adapter -- EventSubscriptionAdapter (6.1.7).

Production adapter for IEventSubscriptionPort.

Design:
  - Thin pass-through wrapping Fabric's ``IEventPort``.
  - Tracks all SubscriptionHandles for bulk unsubscribe at shutdown.
  - All methods SYNC (Fabric convention).
  - subscribe/unsubscribe errors -> AdapterException(RECOVERABLE).
  - shutdown() unsubscribes all tracked handles (called by
    OrchestratorFactory.shutdown()).

Error Mapping:
  - subscribe/unsubscribe failure -> AdapterException(RECOVERABLE).
  - emit failure -> log warning, return silently (fire-and-forget).

References:
  - Issue 6.1.7 in orchestrator-implementation-plan.md
  - k1/fabric/ports/event_port.py (IEventPort, SubscriptionHandle)

Exports:
  EventSubscriptionAdapter
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List

from k1.fabric.ports.event_port import IEventPort, SubscriptionHandle
from k1.orchestrator.orchestration.orchestrator_service import AdapterException
from k1.orchestrator.types import AdapterError, ErrorSeverity

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 6.1.7 -- EventSubscriptionAdapter
# ---------------------------------------------------------------------------


class EventSubscriptionAdapter:
    """
    Production IEventSubscriptionPort adapter wrapping Fabric's IEventPort.

    Tracks all active subscription handles so ``shutdown()`` can
    bulk-unsubscribe. All methods are SYNC per Fabric convention.

    Handler semantics (from IEventPort):
      - Handlers are called synchronously during ``emit()``.
      - Handlers MUST NOT raise (emit never fails).
      - Signature: ``Callable[[str, Dict[str, Any]], None]``.
    """

    __slots__ = ("_event_port", "_handles")

    def __init__(self, event_port: IEventPort) -> None:
        self._event_port = event_port
        self._handles: List[SubscriptionHandle] = []

    # ------------------------------------------------------------------
    # IEventSubscriptionPort.subscribe
    # ------------------------------------------------------------------

    def subscribe(
        self,
        topic: str,
        handler: Callable[[str, Dict[str, Any]], None],
    ) -> SubscriptionHandle:
        """Subscribe a handler to a topic. Tracks handle for shutdown."""
        try:
            handle = self._event_port.subscribe(topic, handler)
            self._handles.append(handle)
            return handle
        except Exception as exc:
            raise AdapterException(
                AdapterError(
                    adapter_name="event_subscription",
                    operation="subscribe",
                    error_code="SUBSCRIBE_FAILED",
                    error_message=f"Failed to subscribe to {topic}: {exc}",
                    severity=ErrorSeverity.RECOVERABLE,
                )
            ) from exc

    # ------------------------------------------------------------------
    # IEventSubscriptionPort.unsubscribe
    # ------------------------------------------------------------------

    def unsubscribe(self, handle: SubscriptionHandle) -> bool:
        """Unsubscribe a handle. Removes from tracked handles."""
        try:
            result = self._event_port.unsubscribe(handle)
            # Remove from tracked handles (best-effort, may already be gone)
            try:
                self._handles.remove(handle)
            except ValueError:
                pass
            return result
        except Exception as exc:
            raise AdapterException(
                AdapterError(
                    adapter_name="event_subscription",
                    operation="unsubscribe",
                    error_code="UNSUBSCRIBE_FAILED",
                    error_message=f"Failed to unsubscribe {handle}: {exc}",
                    severity=ErrorSeverity.RECOVERABLE,
                )
            ) from exc

    # ------------------------------------------------------------------
    # IEventSubscriptionPort.emit
    # ------------------------------------------------------------------

    def emit(self, topic: str, payload: Dict[str, Any]) -> None:
        """Emit an event. Fire-and-forget -- never raises."""
        try:
            self._event_port.emit(topic, payload)
        except Exception:
            logger.warning(
                "EventSubscriptionAdapter.emit failed for topic=%s",
                topic,
                exc_info=True,
            )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def shutdown(self) -> None:
        """Unsubscribe all tracked handles. Called by OrchestratorFactory.shutdown()."""
        for handle in list(self._handles):
            try:
                self._event_port.unsubscribe(handle)
            except Exception:
                logger.warning(
                    "EventSubscriptionAdapter.shutdown: failed to unsubscribe %s",
                    handle,
                    exc_info=True,
                )
        self._handles.clear()

    @property
    def active_subscriptions(self) -> int:
        """Return the number of currently tracked subscriptions."""
        return len(self._handles)
