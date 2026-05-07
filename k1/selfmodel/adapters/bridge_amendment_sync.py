"""Bridge amendment sync adapter.

Outbound (K1 → K0): ``submit_delta`` builds a canonical-JSON envelope
of an amendment, signs it with ``Ed25519Signing``, and pushes it via
``IBridgeClient.submit_command(topic="sync.delta", ..., band="GREEN")``.
``BlackBandLeakError`` is raised at the adapter for any BLACK input
(Empty-Set Invariant E3, defense in depth).

Inbound (K0 → K1): ``start_sse`` subscribes to
``k0.sync.complete.v1`` and on each event refreshes the local
constitution projection, updates ``projection_sync_state``, and
publishes ``k1.selfmodel.constitution.amendment_active.v1`` on the
local bus.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any, Optional

from k1.selfmodel.contracts.constitution import AmendmentProposal
from k1.selfmodel.contracts.privacy import (
    BlackBandLeakError,
    PrivacyBand,
    privacy_band_to_bridge,
)
from k1.selfmodel.events.topics import TOPIC_CONSTITUTION_AMENDMENT_ACTIVE

__all__ = [
    "BridgeAmendmentSyncAdapter",
    "AmendmentRefreshFn",
    "TOPIC_K0_SYNC_COMPLETE",
    "TOPIC_BRIDGE_SYNC_DELTA",
]

logger = logging.getLogger(__name__)

# K0-emitted SSE topic that signals a sync round-trip completed.
TOPIC_K0_SYNC_COMPLETE = "k0.sync.complete.v1"
# Outbound submit_command topic (per bridge taxonomy).
TOPIC_BRIDGE_SYNC_DELTA = "sync.delta"
# Schema URI for the canonical amendment delta envelope.
AMENDMENT_DELTA_SCHEMA = "k1.selfmodel.amendment.delta.v1"

# Refresh callback signature: (device_id, sync_event_data) -> awaitable
AmendmentRefreshFn = Callable[[str, dict[str, Any]], Awaitable[None]]


class BridgeAmendmentSyncAdapter:
    """Submit amendments to K0 + listen for completion events.

    Construction is cheap (no I/O). ``start_sse`` opens the long-lived
    subscription; ``stop_sse`` cancels it cleanly.
    """

    __slots__ = (
        "_bridge",
        "_signing",
        "_local_bus",
        "_refresh_fn",
        "_sse_task",
        "_sse_cursor",
        "_sse_topics",
        "_stopped",
    )

    def __init__(
        self,
        *,
        bridge,
        signing,
        local_bus=None,
        refresh_fn: AmendmentRefreshFn | None = None,
        sse_topics: tuple[str, ...] = (TOPIC_K0_SYNC_COMPLETE,),
    ) -> None:
        if bridge is None:
            raise ValueError("bridge is required")
        if signing is None:
            raise ValueError("signing is required")
        self._bridge = bridge
        self._signing = signing
        self._local_bus = local_bus
        self._refresh_fn = refresh_fn
        self._sse_task: Optional[asyncio.Task] = None
        self._sse_cursor: str = ""
        self._sse_topics: tuple[str, ...] = tuple(sse_topics)
        self._stopped = False

    # ------------------------------------------------------------------
    # Outbound: submit_delta
    # ------------------------------------------------------------------
    async def submit_delta(
        self,
        proposal: AmendmentProposal,
        *,
        band: PrivacyBand = PrivacyBand.GREEN,
        trace_id: str | None = None,
    ) -> str:
        """Build, sign, and submit an amendment delta envelope.

        Args:
            proposal: The amendment to ship.
            band: Privacy band (default GREEN). BLACK raises
                :class:`BlackBandLeakError` *before* serialization.
            trace_id: Optional cognitive trace id for cross-system
                correlation.

        Returns:
            The signature string (the only stable handle the adapter
            knows about — bridge ``submit_command`` is fire-and-forget).
        """
        if proposal is None:
            raise ValueError("proposal is required")
        # E3 defense-in-depth: BLACK never crosses the K1/K0 boundary.
        wire_band = privacy_band_to_bridge(band)  # raises BlackBandLeakError on BLACK

        body = _proposal_to_envelope(proposal)
        canonical_bytes = json.dumps(
            body, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
        signature = self._signing.sign(canonical_bytes)
        body["signature"] = signature
        body["signing_key_id"] = getattr(self._signing, "key_id", "")

        await self._bridge.submit_command(
            TOPIC_BRIDGE_SYNC_DELTA,
            body,
            schema_uri=AMENDMENT_DELTA_SCHEMA,
            band=wire_band,
            trace_id=trace_id,
        )
        logger.info(
            "BridgeAmendmentSyncAdapter  submitted amendment_id=%s parent=%s band=%s",
            proposal.amendment_id,
            proposal.parent_version,
            wire_band,
        )
        return signature

    # ------------------------------------------------------------------
    # Inbound: SSE handler
    # ------------------------------------------------------------------
    async def start_sse(self) -> None:
        """Open the K0→K1 SSE subscription as a background task.

        Idempotent; calling twice is a no-op (a single task per
        adapter instance). ``stop_sse`` cancels and clears the task.
        """
        if self._sse_task is not None and not self._sse_task.done():
            return
        self._stopped = False
        self._sse_task = asyncio.create_task(self._sse_loop(), name="selfmodel-bridge-sse")

    async def stop_sse(self) -> None:
        """Cancel and await the SSE task. Safe to call without start."""
        self._stopped = True
        task = self._sse_task
        if task is None:
            return
        if not task.done():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
        self._sse_task = None

    async def _sse_loop(self) -> None:
        """Run the subscription with reconnect-with-backoff."""
        backoff = 0.5
        while not self._stopped:
            try:
                async_iter = self._bridge.subscribe(
                    list(self._sse_topics), cursor=self._sse_cursor or None
                )
                # subscribe() is itself async in some clients; call it lazily.
                if asyncio.iscoroutine(async_iter):
                    async_iter = await async_iter
                async for event in async_iter:
                    if self._stopped:
                        break
                    await self._handle_sse_event(event)
                # Stream ended cleanly — restart unless stopped.
                if self._stopped:
                    return
                logger.info("BridgeAmendmentSyncAdapter  SSE stream ended; reconnecting")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30.0)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception(
                    "BridgeAmendmentSyncAdapter  SSE loop error; backing off %.1fs", backoff
                )
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30.0)
        logger.info("BridgeAmendmentSyncAdapter  SSE loop exiting")

    async def _handle_sse_event(self, event: Any) -> None:
        """Refresh constitution projection and publish active event."""
        topic = getattr(event, "topic", "")
        if topic != TOPIC_K0_SYNC_COMPLETE:
            return
        cursor = getattr(event, "cursor", "") or ""
        if cursor:
            self._sse_cursor = cursor
        data = getattr(event, "data", {}) or {}
        device_id = str(data.get("device_id", ""))

        # 1. Refresh local constitution projection (caller-provided).
        if self._refresh_fn is not None:
            try:
                await self._refresh_fn(device_id, dict(data))
            except Exception:
                logger.exception(
                    "BridgeAmendmentSyncAdapter  refresh_fn raised for device=%s", device_id
                )
        # 2. Publish local notification (best-effort).
        if self._local_bus is not None:
            payload = {
                "device_id": device_id,
                "k0_topic": topic,
                "cursor": cursor,
                "policy_stamp": getattr(event, "policy_stamp", ""),
            }
            await _publish_local(self._local_bus, TOPIC_CONSTITUTION_AMENDMENT_ACTIVE, payload)

        # 3. Ack so K0 can advance the cursor.
        if cursor:
            try:
                ack = self._bridge.ack(topic, cursor)
                if asyncio.iscoroutine(ack):
                    await ack
            except Exception:
                logger.exception(
                    "BridgeAmendmentSyncAdapter  ack failed for topic=%s cursor=%s",
                    topic,
                    cursor,
                )


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------
def _proposal_to_envelope(proposal: AmendmentProposal) -> dict[str, Any]:
    """Render an AmendmentProposal into the canonical wire envelope."""
    return {
        "schema": AMENDMENT_DELTA_SCHEMA,
        "amendment_id": proposal.amendment_id,
        "parent_version": proposal.parent_version,
        "proposed_by": proposal.proposed_by,
        "status": (
            proposal.status.value if hasattr(proposal.status, "value") else str(proposal.status)
        ),
        "body": dict(proposal.body),
        "expires_at_ms": proposal.expires_at_ms,
    }


async def _publish_local(bus: Any, topic: str, body: dict[str, Any]) -> None:
    """Publish to whatever shape of bus we were handed (best effort)."""
    try:
        publish_simple = getattr(bus, "publish_simple", None)
        if publish_simple is not None:
            result = publish_simple(topic, body)
            if asyncio.iscoroutine(result):
                await result
            return
        publish = getattr(bus, "publish", None)
        if publish is not None:
            result = publish(topic, body)
            if asyncio.iscoroutine(result):
                await result
    except Exception:
        logger.exception("BridgeAmendmentSyncAdapter  local publish failed for topic=%s", topic)
