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
        self.animated: bool = False

    async def add_connection(self, ws: Any) -> None:
        async with self._lock:
            self._connections.append(ws)

    async def remove_connection(self, ws: Any) -> None:
        async with self._lock:
            if ws in self._connections:
                self._connections.remove(ws)

    async def _broadcast(self, message: dict[str, Any]) -> None:
        """Send a JSON message to all connected clients."""
        data = json.dumps(message)
        async with self._lock:
            dead: list[Any] = []
            for ws in self._connections:
                try:
                    await ws.send_text(data)
                except Exception:
                    dead.append(ws)
            for ws in dead:
                self._connections.remove(ws)

    def _broadcast_sync(self, message: dict[str, Any]) -> None:
        """Fire-and-forget broadcast from sync context (bus handlers)."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.ensure_future(self._broadcast(message))
            else:
                loop.run_until_complete(self._broadcast(message))
        except RuntimeError:
            pass

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
