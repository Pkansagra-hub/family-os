"""Helpers for converting fastmcp tool objects to our ToolDescriptor.

Kept in a dedicated module so :mod:`bridge.connector.transport` and
:mod:`bridge.connector.mcp_child` can share the conversion without
introducing a circular import.
"""

from __future__ import annotations

from typing import Any

from .contracts import ToolDescriptor


def tool_descriptors_from_fastmcp(tools: list[Any]) -> list[dict[str, Any]]:
    """Convert fastmcp ``Tool`` records into plain dicts.

    Plain dicts (rather than :class:`ToolDescriptor`) keep the
    transport layer free of connector contract types — the manager
    promotes them via :func:`to_tool_descriptors` once it owns the
    list.
    """
    out: list[dict[str, Any]] = []
    for t in tools:
        # fastmcp Tool has .name, .description, .inputSchema (camelCase
        # to match MCP wire format). Pydantic models expose .model_dump.
        if isinstance(t, dict):
            out.append(
                {
                    "name": t.get("name", ""),
                    "description": t.get("description", ""),
                    "input_schema": t.get("input_schema") or t.get("inputSchema") or {},
                }
            )
            continue
        dump = getattr(t, "model_dump", None)
        if callable(dump):
            d = dump()
            out.append(
                {
                    "name": d.get("name", ""),
                    "description": d.get("description", ""),
                    "input_schema": d.get("inputSchema") or d.get("input_schema") or {},
                }
            )
            continue
        out.append(
            {
                "name": getattr(t, "name", ""),
                "description": getattr(t, "description", ""),
                "input_schema": getattr(t, "inputSchema", None)
                or getattr(t, "input_schema", None)
                or {},
            }
        )
    return out


def to_tool_descriptors(rows: list[dict[str, Any]]) -> list[ToolDescriptor]:
    """Promote plain dicts to typed :class:`ToolDescriptor` rows."""
    return [
        ToolDescriptor(
            name=r.get("name", ""),
            description=r.get("description", ""),
            input_schema=r.get("input_schema") or {},
        )
        for r in rows
    ]


__all__ = ["tool_descriptors_from_fastmcp", "to_tool_descriptors"]
