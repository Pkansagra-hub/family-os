"""ui.web — Web UI layer for the K1 kernel.

Lives OUTSIDE k1/ (see ADR-1: UI is not a kernel concern). The web layer
adapts the production K1 kernel for a browser-based chat experience with
real-time FSM badges, affect meter, timeline, and dashboard panels.

Entry point::

    python -m ui.web [--port 8765] [--host 127.0.0.1] [--test-mode]

Package structure:
    __init__.py    — package surface (this file)
    __main__.py    — uvicorn CLI entry-point
    app.py         — FastAPI application + WebSocket handler
    coordinator.py — UiCoordinator: kernel-as-library adapter
    renderer.py    — WebSocketRenderer (verbatim copy from POC, zero deps)
    static/        — index.html, app.js, styles.css (verbatim browser assets)
"""

from __future__ import annotations

from ui.web.coordinator import UiCoordinator, get_web_coordinator, reset_coordinator
from ui.web.renderer import WebSocketRenderer

__all__ = [
    "UiCoordinator",
    "WebSocketRenderer",
    "get_web_coordinator",
    "reset_coordinator",
]
