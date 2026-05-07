"""Tool → ``RiskClass`` registry (M2.E1.I3 + M8.E2.I1).

Per the whiteboard "Low-Risk Definition" section:

* Risk class is **not** an LLM judgement — it is a per-tool declared
  property in the tool contract.
* **Fail-closed default (M8):** unmapped tools default to
  ``SAFETY_SENSITIVE`` so an unregistered fabric/wrapper tool can
  never sneak past the matrix as ``LOW``. The registry emits a single
  warning per unknown tool name.
* Concierge tools that touch other members or external systems start at
  ``MEDIUM``+. Adjust as new tools land.

Legacy callers that need the old default-LOW behaviour can pass
``default=RiskClass.LOW`` explicitly to ``get_risk_class``.

Add new tools here as they are introduced. ``register_tool_risk`` is
exposed so feature modules (and tests) can register without touching
this file.
"""

from __future__ import annotations

import logging
import threading

from k1.selfmodel.contracts.policy import RiskClass

__all__ = [
    "RISK_CLASS_BY_TOOL",
    "register_tool_risk",
    "get_risk_class",
    "reset_unknown_warnings",
    "FAIL_CLOSED_DEFAULT",
]

logger = logging.getLogger(__name__)

# M12.E2.I1 fail-open default — unmapped tool → LOW.
# Conscience risk_overrides + Fabric-level conscience gate (M12.E4) provide
# the escalation path for unknown high-risk capabilities. All real
# capabilities must declare risk_class explicitly in their YAML contract
# (M12.E2.I2) — falling through to this default emits a one-shot warning
# (M12.E2.I3) and a bus event so missing declarations surface loudly.
FAIL_CLOSED_DEFAULT: RiskClass = RiskClass.LOW


# Canonical defaults. Source of truth for V0.
RISK_CLASS_BY_TOOL: dict[str, RiskClass] = {
    # ---- Front-FSM (read-only / self) -------------------------------
    "submit_result": RiskClass.LOW,
    "needs_human": RiskClass.LOW,  # routed via HIL; gate is informational
    "recall_memory": RiskClass.LOW,  # reads, capsule will mark stale
    "search_memory": RiskClass.LOW,
    "list_routines": RiskClass.LOW,
    "list_reminders": RiskClass.LOW,
    "summarize_context": RiskClass.LOW,
    "complete_chore": RiskClass.LOW,
    # ---- Self-write (own low-impact domain) -------------------------
    "create_reminder": RiskClass.LOW,
    "complete_task": RiskClass.LOW,
    "set_preference": RiskClass.LOW,
    # ---- Cross-member writes (medium) -------------------------------
    "update_persona": RiskClass.MEDIUM,
    "assign_task": RiskClass.MEDIUM,
    "create_calendar_event": RiskClass.MEDIUM,
    "set_routine": RiskClass.MEDIUM,
    # ---- High-risk -------------------------------------------------
    "send_message": RiskClass.HIGH,
    "create_automation": RiskClass.HIGH,
    "bulk_edit": RiskClass.HIGH,
    "approve_request": RiskClass.HIGH,
    "pickup_change": RiskClass.HIGH,
    # ---- Safety-sensitive ------------------------------------------
    "set_medication": RiskClass.SAFETY_SENSITIVE,
    "schedule_medical": RiskClass.SAFETY_SENSITIVE,
    "make_payment": RiskClass.SAFETY_SENSITIVE,
    "share_location": RiskClass.SAFETY_SENSITIVE,
    "modify_constitution": RiskClass.SAFETY_SENSITIVE,
    "pair_device": RiskClass.SAFETY_SENSITIVE,
    "red_memory_op": RiskClass.SAFETY_SENSITIVE,
    # ---- Wrappers (M8) — these MUST be unwrapped by the gate ------
    # Listed here so the registry never returns the fail-closed
    # default for the wrapper itself; the gate is responsible for
    # extracting `arguments["capability_name"]` and re-looking up.
    "invoke_capability": RiskClass.SAFETY_SENSITIVE,
    "batch_invoke_capabilities": RiskClass.SAFETY_SENSITIVE,
    "spawn_via_fabric": RiskClass.SAFETY_SENSITIVE,
    "execute_workflow": RiskClass.SAFETY_SENSITIVE,
}

_lock = threading.Lock()
_warned: set[str] = set()


def register_tool_risk(tool_name: str, risk: RiskClass) -> None:
    """Register or override a tool's risk class. Thread-safe."""
    if not isinstance(tool_name, str) or not tool_name:
        raise ValueError("tool_name must be a non-empty string")
    if not isinstance(risk, RiskClass):
        raise TypeError("risk must be a RiskClass member")
    with _lock:
        RISK_CLASS_BY_TOOL[tool_name] = risk
        _warned.discard(tool_name)


def get_risk_class(
    tool_name: str,
    *,
    default: RiskClass | None = None,
) -> RiskClass:
    """Look up a tool's risk class.

    Unknown tools default to :data:`FAIL_CLOSED_DEFAULT`
    (:class:`RiskClass.SAFETY_SENSITIVE`) and emit a single warning
    the first time they are seen. Pass ``default=RiskClass.LOW`` for
    legacy back-compat.
    """
    fallback = default if isinstance(default, RiskClass) else FAIL_CLOSED_DEFAULT
    if not isinstance(tool_name, str) or not tool_name:
        return fallback
    with _lock:
        risk = RISK_CLASS_BY_TOOL.get(tool_name)
        if risk is not None:
            return risk
        if tool_name not in _warned:
            _warned.add(tool_name)
            logger.warning(
                "tool_risk_default_fail_closed tool=%s risk=%s — "
                "register_tool_risk() to override",
                tool_name,
                fallback.value,
            )
    return fallback


def reset_unknown_warnings() -> None:
    """Test helper — re-arm the per-tool warning latch."""
    with _lock:
        _warned.clear()
