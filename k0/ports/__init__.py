"""FastAPI routers that expose the kernel ports."""

from __future__ import annotations

from fastapi import APIRouter

from . import command, drivers, observe, query, sse

__all__ = [
    "command",
    "drivers",
    "observe",
    "query",
    "sse",
    "all_routers",
]


def all_routers() -> list[APIRouter]:
    """Return all routers that should be registered with the FastAPI app."""

    return [command.router, query.router, sse.router, observe.router, drivers.router]
