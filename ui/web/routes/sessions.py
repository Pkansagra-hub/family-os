"""
ui.web.routes.sessions — Chat session REST API.

Exposes CRUD for persistent chat sessions backed by kernel.db.
Follows the same lazy-coordinator pattern as family_tools.py.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List

from fastapi import APIRouter, HTTPException, Query


def build_sessions_api(get_coordinator: Callable[[], Any]) -> APIRouter:
    """Return a FastAPI router for /api/sessions/* endpoints.

    Parameters
    ----------
    get_coordinator:
        Zero-arg callable returning the current ``UiCoordinator`` or ``None``.
        Typically ``lambda: _coordinator`` from ``ui.web.app``.
    """
    router = APIRouter(prefix="/api/sessions", tags=["sessions_api"])

    # ── helpers ──────────────────────────────────────────────

    def _registry():
        coord = get_coordinator()
        if coord is None:
            raise HTTPException(503, "Coordinator not initialized")
        svc = getattr(getattr(coord, "_runtime", None), "_service", None)
        if svc is None:
            raise HTTPException(503, "Kernel service not available")
        reg = getattr(svc, "_session_registry", None)
        if reg is None:
            raise HTTPException(503, "Session registry not available (kernel.db disabled?)")
        return reg

    def _kernel_db():
        coord = get_coordinator()
        if coord is None:
            raise HTTPException(503, "Coordinator not initialized")
        svc = getattr(getattr(coord, "_runtime", None), "_service", None)
        if svc is None:
            raise HTTPException(503, "Kernel service not available")
        db = getattr(svc, "_kernel_db", None)
        if db is None:
            raise HTTPException(503, "kernel.db not available")
        return db

    def _active_session_id():
        coord = get_coordinator()
        if coord is None:
            return None
        rt = coord._runtime
        if rt is None:
            return None
        return str(getattr(rt, "_session_id", "") or "")

    # ── GET /api/sessions ────────────────────────────────────

    @router.get("")
    async def list_sessions() -> Dict[str, Any]:
        """Return all sessions, newest first, with the active session id."""
        reg = _registry()
        sessions: List[Dict[str, Any]] = reg.list_all()
        active_id = _active_session_id()
        return {"sessions": sessions, "active_session_id": active_id}

    # ── POST /api/sessions ───────────────────────────────────

    @router.post("")
    async def create_session(title: str = Query("New Chat")) -> Dict[str, Any]:
        """Create a new session row. Does NOT activate it (Slice 6)."""
        reg = _registry()
        session_id = reg.create(title=title, origin="web")
        return {"session_id": session_id, "title": title}

    # ── DELETE /api/sessions/{session_id} ────────────────────

    @router.delete("/{session_id}")
    async def delete_session(session_id: str) -> Dict[str, Any]:
        """Delete a session and its messages. Cannot delete the active session."""
        active_id = _active_session_id()
        if session_id == active_id:
            raise HTTPException(409, "Cannot delete the active session. Switch first.")
        reg = _registry()
        ok = reg.delete(session_id)
        if not ok:
            raise HTTPException(404, f"Session '{session_id}' not found")
        return {"deleted": True, "session_id": session_id}

    # ── PATCH /api/sessions/{session_id} ─────────────────────

    @router.patch("/{session_id}")
    async def update_session(session_id: str, title: str = Query(...)) -> Dict[str, Any]:
        """Update a session's title."""
        reg = _registry()
        ok = reg.update_title(session_id, title)
        if not ok:
            raise HTTPException(404, f"Session '{session_id}' not found")
        return {"session_id": session_id, "title": title}

    # ── POST /api/sessions/{session_id}/activate ─────────────

    @router.post("/{session_id}/activate")
    async def activate_session(session_id: str) -> Dict[str, Any]:
        """Activate (switch to) a session.  Staged create-before-destroy.

        The current session is checkpointed, the target session is built
        and validated, then the old session is torn down.  If the new
        session fails, the old session is untouched.
        """
        coord = get_coordinator()
        if coord is None:
            raise HTTPException(503, "Coordinator not initialized")

        # Guard: block concurrent switch requests
        if getattr(coord, "_switching", False):
            raise HTTPException(409, "A session switch is already in progress")

        # Guard: don't switch to already-active session
        active_id = _active_session_id()
        if session_id == active_id:
            return {"session_id": session_id, "already_active": True}

        # Guard: target must exist in registry
        reg = _registry()
        if reg.get(session_id) is None:
            raise HTTPException(404, f"Session '{session_id}' not found")

        try:
            result = await coord.activate_session(session_id)
            return result
        except ValueError as e:
            raise HTTPException(409, str(e))
        except KeyError as e:
            raise HTTPException(404, str(e))
        except RuntimeError as e:
            raise HTTPException(503, str(e))

    # ── GET /api/sessions/{session_id}/history ───────────────

    @router.get("/{session_id}/history")
    async def get_session_history(session_id: str) -> Dict[str, Any]:
        """Return chat messages for a session, grouped by turn."""
        db = _kernel_db()
        reg = _registry()
        session = reg.get(session_id)
        if session is None:
            raise HTTPException(404, f"Session '{session_id}' not found")

        rows: List[Dict[str, Any]] = db.get_messages(session_id)
        # Group by turn_number into turn pairs {turn_num, user, assistant, timestamp}
        by_turn: Dict[int, Dict[str, Any]] = {}
        for row in rows:
            tn = row["turn_num"]
            if tn not in by_turn:
                by_turn[tn] = {"turn_num": tn, "timestamp": row["timestamp"]}
            by_turn[tn][row["role"]] = row["content"]

        turns: List[Dict[str, Any]] = []
        for tn in sorted(by_turn):
            t = by_turn[tn]
            turns.append(
                {
                    "turn_num": tn,
                    "user": t.get("user", ""),
                    "assistant": t.get("assistant", ""),
                    "timestamp": t["timestamp"],
                }
            )

        return {
            "session_id": session_id,
            "title": session.get("title", ""),
            "turn_count": session.get("turn_count", 0),
            "turns": turns,
        }

    return router
