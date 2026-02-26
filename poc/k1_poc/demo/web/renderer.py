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
