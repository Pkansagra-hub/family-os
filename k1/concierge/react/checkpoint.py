"""Versioned ReAct checkpoint model for Back suspension/resume."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class ReActCheckpointVersionError(ValueError):
    """Raised when a serialized checkpoint version is unsupported."""


@dataclass(frozen=True, slots=True)
class ReActCheckpoint:
    """JSON-safe snapshot of ReAct state at a suspension boundary."""

    task_id: str
    messages: list[dict[str, Any]] = field(default_factory=list)
    tool_history: list[dict[str, Any]] = field(default_factory=list)
    completed_tool_call_ids: list[str] = field(default_factory=list)
    suspension_count: int = 1
    budget_remaining: int = 0
    last_iteration: int = 0
    scratchpad: dict[str, Any] = field(default_factory=dict)
    version: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "task_id": self.task_id,
            "messages": list(self.messages),
            "tool_history": list(self.tool_history),
            "completed_tool_call_ids": list(self.completed_tool_call_ids),
            "suspension_count": self.suspension_count,
            "budget_remaining": self.budget_remaining,
            "last_iteration": self.last_iteration,
            "scratchpad": dict(self.scratchpad),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ReActCheckpoint":
        version = int(data.get("version", 1))
        if version != 1:
            raise ReActCheckpointVersionError(f"Unsupported ReActCheckpoint version: {version}")
        return cls(
            version=version,
            task_id=str(data.get("task_id", "")),
            messages=list(data.get("messages") or []),
            tool_history=list(data.get("tool_history") or []),
            completed_tool_call_ids=[str(v) for v in data.get("completed_tool_call_ids") or []],
            suspension_count=int(data.get("suspension_count", 1) or 1),
            budget_remaining=int(data.get("budget_remaining", 0) or 0),
            last_iteration=int(data.get("last_iteration", 0) or 0),
            scratchpad=dict(data.get("scratchpad") or {}),
        )

    def completed_tool_keys(self) -> set[str]:
        keys: set[str] = set()
        for record in self.tool_history:
            if not isinstance(record, dict):
                continue
            status = str(record.get("result_status", "")).lower()
            if status not in {"ok", "partial"}:
                continue
            tool_name = str(record.get("tool_name", "") or "")
            args_hash = str(record.get("args_hash", "") or "")
            if tool_name and args_hash:
                keys.add(f"{tool_name}:{args_hash}")
        return keys
