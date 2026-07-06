"""
k1.concierge.task.intent -- TaskIntent dataclass.

V2 Design Ref: Section 8.2 (TaskIntent schema)

A TaskIntent represents one discrete action the Back actor should
execute.  Multiple TaskIntents can be bundled in a single TaskDispatch
(V2 Section 17.3) when the user expresses independent intents
in one utterance ("Book hotel AND search restaurants").

Key design decisions:
    - frozen=True: intents are immutable once created. If Front needs
      to modify an intent, it creates a new TaskDispatch.
    - action is required and non-empty. It can be natural language
      ("book hotel") or a known capability name ("tool.execute.hotel_booking").
      Back uses discover_capabilities() if the action is natural language.
    - params may contain $ref placeholders for chained tasks (V2 Section 17.4):
      e.g. {"near": "$prev.result.address"}.  These are resolved by the
      orchestrator before the dependent task is dispatched.
    - urgency maps to bus Envelope priority during dispatch:
      urgent -> Priority.URGENT, normal -> Priority.INTERACTIVE,
      background -> Priority.BACKGROUND.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class TaskIntent:
    """A single intent within a task dispatch.

    Attributes:
        action:  What to do -- natural language or capability name.
                 Back uses this to select the invoke_capability target.
        params:  Structured parameters for the action. May contain
                 $ref placeholders for chained tasks:
                 e.g. {"near": "$prev.result.address"}.
        domain:  Optional domain hint (travel, health, productivity).
                 Helps Back select domain-specific capabilities.
        resource_family: Optional taxonomy family hint (e.g. "item", "event").
                 Populated by Front LLM from registry hints; passed through
                 to Back's resolve_situation call.
        operation_hint: Optional operation hint (e.g. "create", "read").
                 Helps Back select the right capability mode.
        urgency: Priority hint: "normal" (default), "urgent", "background".
                 Maps to bus Envelope priority during dispatch.
    """

    action: str
    params: dict[str, Any] = field(default_factory=dict)
    domain: str | None = None
    # DEPRECATED (2026-06-16): resolver no longer uses domain/rf/op hints as
    # filters.  These fields survive for backward compat but are dead weight.
    resource_family: str | None = None
    # DEPRECATED (2026-06-16): see resource_family note above.
    operation_hint: str | None = None
    urgency: str = "normal"

    _VALID_URGENCIES = frozenset({"normal", "urgent", "background"})

    def __post_init__(self) -> None:
        if not self.action or not self.action.strip():
            raise ValueError("TaskIntent.action must be non-empty")
        if self.urgency not in self._VALID_URGENCIES:
            raise ValueError(
                f"TaskIntent.urgency must be one of {sorted(self._VALID_URGENCIES)}, "
                f"got '{self.urgency}'"
            )

    def has_refs(self) -> bool:
        """Return True if any param value contains a $ref placeholder.

        Ref placeholders start with '$' and reference another task's
        result field.  Example: "$task-003.result.address"
        """
        return any(isinstance(v, str) and v.startswith("$") for v in self.params.values())

    def ref_targets(self) -> list[str]:
        """Return list of task IDs referenced via $ref placeholders.

        Extracts the task ID portion from each $ref value.
        Example: "$task-003.result.address" -> "task-003"
        """
        targets: list[str] = []
        for v in self.params.values():
            if isinstance(v, str) and v.startswith("$"):
                # $task-003.result.address -> task-003
                parts = v.lstrip("$").split(".", 1)
                if parts:
                    targets.append(parts[0])
        return targets

    def to_dict(self) -> dict[str, Any]:
        """Serialize for JSON/envelope payload.

        Only includes non-default fields to minimize payload size.
        """
        d: dict[str, Any] = {"action": self.action, "params": self.params}
        if self.domain is not None:
            d["domain"] = self.domain
        if self.resource_family is not None:
            d["resource_family"] = self.resource_family
        if self.operation_hint is not None:
            d["operation_hint"] = self.operation_hint
        if self.urgency != "normal":
            d["urgency"] = self.urgency
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TaskIntent:
        """Deserialize from dict."""
        return cls(
            action=data["action"],
            params=data.get("params", {}),
            domain=data.get("domain"),
            resource_family=data.get("resource_family"),
            operation_hint=data.get("operation_hint"),
            urgency=data.get("urgency", "normal"),
        )
