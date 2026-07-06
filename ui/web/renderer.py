"""
poc.k1_poc.demo.web.renderer -- WebSocket renderer for the K1 demo.

Implements the IRenderer protocol from output_channel.py, sending all
render calls as JSON messages over a WebSocket connection instead of
writing to stdout.  Supports live streaming, timeline events, and
affect updates.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

logger = logging.getLogger(__name__)


class WebSocketRenderer:
    """IRenderer implementation that pushes JSON messages over WebSocket.

    Unlike the ConsoleRenderer, this renderer does NOT need the weave
    buffering mechanism -- WebSocket delivery never corrupts user input
    because the browser separates the input field from the message area.
    Proactive/weave messages are delivered immediately.
    """

    supports_immediate_proactive: bool = True

    def __init__(self) -> None:
        self._connections: list[Any] = []  # list of WebSocket objects
        self._lock = asyncio.Lock()
        self._queue: asyncio.Queue[dict[str, Any]] | None = None
        self._pump_task: asyncio.Task[None] | None = None
        self.animated: bool = False

    async def add_connection(self, ws: Any) -> None:
        async with self._lock:
            self._connections.append(ws)

    async def remove_connection(self, ws: Any) -> None:
        async with self._lock:
            if ws in self._connections:
                self._connections.remove(ws)

    async def _ensure_pump(self) -> None:
        if self._queue is None:
            self._queue = asyncio.Queue(maxsize=1000)

        if self._pump_task is None or self._pump_task.done():
            self._pump_task = asyncio.create_task(
                self._broadcast_pump(),
                name="websocket-renderer-broadcast-pump",
            )

    async def _broadcast_pump(self) -> None:
        assert self._queue is not None

        while True:
            message = await self._queue.get()
            try:
                await self._broadcast(message)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("WEB: broadcast pump failed")
            finally:
                self._queue.task_done()

    async def _broadcast(self, message: dict[str, Any]) -> None:
        """Send a JSON message to all connected clients.

        Lock held only for snapshotting connections — never during socket I/O.
        """
        data = json.dumps(message)

        async with self._lock:
            connections = list(self._connections)

        dead: list[Any] = []

        for ws in connections:
            try:
                await ws.send_text(data)
            except Exception:
                dead.append(ws)

        if dead:
            async with self._lock:
                for ws in dead:
                    if ws in self._connections:
                        self._connections.remove(ws)

    def _broadcast_sync(self, message: dict[str, Any]) -> None:
        """Fire-and-forget broadcast from sync context (bus handlers).

        Queues the message through a single pump task so streaming
        chunks don't create a task storm that chokes Python 3.13's
        task-context tracking when aiohttp connection cleanup races
        with WebSocket writes.
        """
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return

        def _enqueue() -> None:
            async def _put() -> None:
                await self._ensure_pump()
                assert self._queue is not None
                try:
                    self._queue.put_nowait(message)
                except asyncio.QueueFull:
                    logger.warning(
                        "WEB: broadcast queue full, dropping message type=%s",
                        message.get("type"),
                    )

            asyncio.create_task(_put(), name="websocket-renderer-enqueue")

        loop.call_soon(_enqueue)

    # -- IRenderer protocol ------------------------------------------------

    def render_response(self, text: str, member: str, affect: str) -> None:
        self._broadcast_sync(
            {
                "type": "response",
                "text": text,
                "member": member,
                "affect": affect,
                "timestamp": time.time(),
            }
        )

    def render_proactive(self, text: str) -> None:
        self._broadcast_sync(
            {
                "type": "proactive",
                "text": text,
                "timestamp": time.time(),
            }
        )

    def render_weave(self, texts: list[str]) -> None:
        self._broadcast_sync(
            {
                "type": "weave",
                "texts": texts,
                "timestamp": time.time(),
            }
        )

    def render_system(self, text: str) -> None:
        self._broadcast_sync(
            {
                "type": "system",
                "text": text,
                "timestamp": time.time(),
            }
        )

    def render_stream_chunk(self, text: str, chunk_type: str) -> None:
        self._broadcast_sync(
            {
                "type": "stream_chunk",
                "text": text,
                "chunk_type": chunk_type,
                "timestamp": time.time(),
            }
        )

    # -- Extended events (beyond IRenderer) --------------------------------

    def send_timeline_entry(self, entry: dict[str, Any]) -> None:
        self._broadcast_sync(
            {
                "type": "timeline",
                "entry": entry,
            }
        )

    def send_affect_update(self, emotion: str, valence: float) -> None:
        self._broadcast_sync(
            {
                "type": "affect_update",
                "emotion": emotion,
                "valence": valence,
                "timestamp": time.time(),
            }
        )

    def send_activity(self, data: dict[str, Any]) -> None:
        self._broadcast_sync(
            {
                "type": "activity",
                "data": data,
                "timestamp": time.time(),
            }
        )

    def send_fsm_state(self, from_state: str, to_state: str, trigger: str) -> None:
        self._broadcast_sync(
            {
                "type": "fsm_state",
                "from_state": from_state,
                "to_state": to_state,
                "trigger": trigger,
                "timestamp": time.time(),
            }
        )

    def send_tool_event(self, tool_name: str, actor: str, phase: str, **extra: Any) -> None:
        self._broadcast_sync(
            {
                "type": "tool_event",
                "tool_name": tool_name,
                "actor": actor,
                "phase": phase,
                **extra,
                "timestamp": time.time(),
            }
        )

    def send_turn_info(self, turn: int, member: str) -> None:
        self._broadcast_sync(
            {
                "type": "turn_info",
                "turn": turn,
                "member": member,
                "timestamp": time.time(),
            }
        )

    def send_tool_refresh(self, adapter_id: str, space_id: str = "") -> None:
        """E15.10: notify the browser that a family-tool's data has changed."""
        self._broadcast_sync(
            {
                "type": "tool_refresh",
                "adapter": adapter_id,
                "space_id": space_id,
                "timestamp": time.time(),
            }
        )

    def send_hil_request(self, envelope: dict[str, Any]) -> None:
        """Forward a HIL request envelope to the browser for user action."""
        connections = len(self._connections)
        if connections == 0:
            logger.warning(
                "WEB: no active websocket connections for hil_request hil_request_id=%s kind=%s",
                envelope.get("hil_request_id", ""),
                envelope.get("kind", ""),
            )
        else:
            logger.info(
                "WEB: broadcasting hil_request hil_request_id=%s kind=%s connections=%d",
                envelope.get("hil_request_id", ""),
                envelope.get("kind", ""),
                connections,
            )
        self._broadcast_sync(
            {
                "type": "hil_request",
                "hil_request_id": envelope.get("hil_request_id", ""),
                "kind": envelope.get("kind", ""),
                "caller_key": envelope.get("caller_key", ""),
                "payload": envelope.get("payload", {}),
                "timeout_ms": envelope.get("timeout_ms", 120000),
                "timestamp": time.time(),
            }
        )

    def send_hil_presented(self, envelope: dict[str, Any]) -> None:
        """GAP-HIL-009: notify the browser that a HIL question is now visible.

        Emitted in response to TOPIC_HIL_PRESENTED. The browser uses this
        to mark the chat input as the active answer channel (data-hil-active)
        so free-text input is correlated with the open HIL request.
        """
        self._broadcast_sync(
            {
                "type": "hil_presented",
                "hil_request_id": envelope.get("hil_request_id", ""),
                "task_id": envelope.get("task_id", ""),
                "kind": envelope.get("kind", ""),
                "presentation_channel": envelope.get("presentation_channel", ""),
                "presented_at_ms": envelope.get("presented_at_ms", 0),
                "timestamp": time.time(),
            }
        )

    def send_task_failed(
        self,
        task_id: str,
        reason: str = "error",
        error_message: str = "",
        error_code: str = "",
    ) -> None:
        """Notify the browser that a Back task failed so the UI can unstick.

        Emitted in response to ``TOPIC_TASK_FAILED`` envelopes. The browser
        clears its streaming spinner, marks the active back-activity panel as
        errored, and shows a brief in-chat fallback message so the user knows
        the turn is over even when Front never produces a response.final.
        """
        connections = len(self._connections)
        if connections == 0:
            logger.warning(
                "WEB: no active websocket connections for task_failed task_id=%s reason=%s",
                task_id,
                reason,
            )
        else:
            logger.info(
                "WEB: broadcasting task_failed task_id=%s reason=%s connections=%d",
                task_id,
                reason,
                connections,
            )
        self._broadcast_sync(
            {
                "type": "task_failed",
                "task_id": task_id,
                "reason": reason,
                "error_message": error_message,
                "error_code": error_code,
                "timestamp": time.time(),
            }
        )

    def send_session_updated(self, session_id: str, title: str) -> None:
        """Push a session title update to all connected browsers.

        Slice 7: Called from the coordinator's ``TOPIC_SESSION_TITLE_UPDATED``
        bus subscription.  The browser handles ``type:session_updated`` by
        updating the sidebar item's title text.
        """
        self._broadcast_sync(
            {
                "type": "session_updated",
                "session_id": session_id,
                "title": title,
            }
        )
