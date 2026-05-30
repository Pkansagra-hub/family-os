"""Back capability execution coverage plan.

The Back actor is a worker.  This module gives the ReAct loop a small,
JSON-safe ledger for the work it was asked to execute so the model cannot
submit a complete result after covering only part of a bundled dispatch.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class BackExecutionStatus(str, Enum):
    """Coverage state for one Back work item."""

    PENDING = "pending"
    DISCOVERED = "discovered"
    IN_PROGRESS = "in_progress"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    NEEDS_HUMAN = "needs_human"


_TERMINAL_STATUSES = frozenset(
    {
        BackExecutionStatus.SUCCEEDED.value,
        BackExecutionStatus.FAILED.value,
    }
)


def _as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _text(value: Any) -> str:
    return str(value or "").strip()


def _lower(value: Any) -> str:
    return _text(value).lower()


def _capability_domain_tokens(name: str) -> set[str]:
    parts = [part for part in name.split(".") if part]
    if len(parts) <= 2:
        domain_parts = parts
    else:
        domain_parts = parts[2:-1] or parts[1:-1]
    tokens: set[str] = set()
    for part in domain_parts:
        for token in part.replace("-", "_").split("_"):
            if token:
                tokens.add(token)
                if len(token) > 3 and token.endswith("s"):
                    tokens.add(token[:-1])
    return tokens


@dataclass(slots=True)
class BackExecutionWorkItem:
    """One intent that Back must cover before a complete submit_result."""

    intent_index: int
    action: str
    domain: str | None = None
    params: dict[str, Any] = field(default_factory=dict)
    status: str = BackExecutionStatus.PENDING.value
    discovered_capabilities: list[dict[str, Any]] = field(default_factory=list)
    attempted_capabilities: list[str] = field(default_factory=list)
    results: list[Any] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @classmethod
    def from_intent(cls, intent_index: int, intent: dict[str, Any]) -> "BackExecutionWorkItem":
        return cls(
            intent_index=intent_index,
            action=_text(intent.get("action")),
            domain=_text(intent.get("domain")) or None,
            params=_as_dict(intent.get("params")),
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BackExecutionWorkItem":
        return cls(
            intent_index=int(data.get("intent_index", 0) or 0),
            action=_text(data.get("action")),
            domain=_text(data.get("domain")) or None,
            params=_as_dict(data.get("params")),
            status=_text(data.get("status")) or BackExecutionStatus.PENDING.value,
            discovered_capabilities=[
                dict(item)
                for item in _as_list(data.get("discovered_capabilities"))
                if isinstance(item, dict)
            ],
            attempted_capabilities=[
                _text(item) for item in _as_list(data.get("attempted_capabilities")) if _text(item)
            ],
            results=_as_list(data.get("results")),
            errors=[_text(item) for item in _as_list(data.get("errors")) if _text(item)],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "intent_index": self.intent_index,
            "action": self.action,
            "domain": self.domain,
            "params": dict(self.params),
            "status": self.status,
            "discovered_capabilities": [dict(item) for item in self.discovered_capabilities],
            "attempted_capabilities": list(self.attempted_capabilities),
            "results": list(self.results),
            "errors": list(self.errors),
        }

    @property
    def is_complete(self) -> bool:
        return self.status in _TERMINAL_STATUSES

    def record_discovery(self, capabilities: list[dict[str, Any]]) -> None:
        if capabilities:
            self.discovered_capabilities = [dict(item) for item in capabilities]
            if self.status == BackExecutionStatus.PENDING.value:
                self.status = BackExecutionStatus.DISCOVERED.value
        elif self.status == BackExecutionStatus.PENDING.value:
            self.errors.append("no_capability_candidates")

    def record_attempt(
        self,
        *,
        capability_name: str,
        success: bool,
        payload: Any = None,
        error: str = "",
        needs_human: bool = False,
    ) -> None:
        if capability_name and capability_name not in self.attempted_capabilities:
            self.attempted_capabilities.append(capability_name)
        if payload not in (None, "", []):
            self.results.append(payload)
        if error:
            self.errors.append(error)
        if needs_human:
            self.status = BackExecutionStatus.NEEDS_HUMAN.value
        elif success:
            self.status = BackExecutionStatus.SUCCEEDED.value
        else:
            self.status = BackExecutionStatus.FAILED.value

    def fact(self) -> dict[str, Any]:
        fact: dict[str, Any] = {
            "_type": "back_intent_result",
            "intent_index": self.intent_index,
            "action": self.action,
            "status": self.status,
            "capabilities": list(self.attempted_capabilities),
        }
        if self.domain:
            fact["domain"] = self.domain
        if self.results:
            fact["result"] = self.results[-1]
        if self.errors:
            fact["errors"] = list(self.errors)
        return fact


@dataclass(slots=True)
class BackExecutionPlan:
    """JSON-safe internal coverage plan for a Back dispatch."""

    task_id: str = ""
    work_items: list[BackExecutionWorkItem] = field(default_factory=list)

    @classmethod
    def from_task(cls, task: dict[str, Any] | None) -> "BackExecutionPlan":
        source = _as_dict(task)
        intents = _as_list(source.get("intents"))
        work_items: list[BackExecutionWorkItem] = []
        for index, raw_intent in enumerate(intents):
            if isinstance(raw_intent, dict):
                work_items.append(BackExecutionWorkItem.from_intent(index, raw_intent))
        if not work_items:
            action = _text(source.get("action"))
            if action:
                work_items.append(
                    BackExecutionWorkItem.from_intent(
                        0,
                        {
                            "action": action,
                            "domain": source.get("domain"),
                            "params": source.get("params") or {},
                        },
                    )
                )
        return cls(task_id=_text(source.get("task_id")), work_items=work_items)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "BackExecutionPlan":
        source = _as_dict(data)
        return cls(
            task_id=_text(source.get("task_id")),
            work_items=[
                BackExecutionWorkItem.from_dict(item)
                for item in _as_list(source.get("work_items"))
                if isinstance(item, dict)
            ],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "work_items": [item.to_dict() for item in self.work_items],
            "complete": self.is_complete,
            "pending": [item.intent_index for item in self.uncovered_items()],
        }

    @property
    def is_complete(self) -> bool:
        return bool(self.work_items) and all(item.is_complete for item in self.work_items)

    def uncovered_items(self) -> list[BackExecutionWorkItem]:
        return [item for item in self.work_items if not item.is_complete]

    def can_submit_complete(self) -> bool:
        return not self.work_items or self.is_complete

    def submit_rejection_payload(self) -> dict[str, Any]:
        return {
            "error_code": "BACK_EXECUTION_PLAN_INCOMPLETE",
            "pending_intents": [item.fact() for item in self.uncovered_items()],
            "execution_plan": self.to_dict(),
            "hint": (
                "Finish every pending intent with invoke_capability or "
                "batch_invoke_capabilities before submit_result(result_type='complete'). "
                "If an input or capability is missing, submit result_type='needs_human'."
            ),
        }

    def record_discovery(self, args: dict[str, Any], data: dict[str, Any]) -> None:
        # Batched discovery: data carries `intent_results: [{intent,
        # capability_names, count}, ...]` from a single multi-intent
        # discover_capabilities call.  Match each intent's discovered
        # capabilities to its corresponding work item using the same
        # _match_item scorer; the per-intent capability list is the
        # ground truth, not the merged top-level array.
        intent_results = _as_list(data.get("intent_results"))
        if intent_results and bool(data.get("batched")):
            top_level_caps_by_name: dict[str, dict[str, Any]] = {}
            for cap in _as_list(data.get("capabilities")):
                if isinstance(cap, dict):
                    name = _text(cap.get("name"))
                    if name:
                        top_level_caps_by_name[name] = cap
            for entry in intent_results:
                if not isinstance(entry, dict):
                    continue
                sub_intent = _text(entry.get("intent"))
                if not sub_intent:
                    continue
                item = self._match_item(
                    action=sub_intent,
                    domain=_text(args.get("domain")) or None,
                )
                if item is None:
                    continue
                cap_names = [
                    _text(name) for name in _as_list(entry.get("capability_names")) if _text(name)
                ]
                sub_caps: list[dict[str, Any]] = []
                for name in cap_names:
                    cap = top_level_caps_by_name.get(name)
                    if cap is not None:
                        sub_caps.append(dict(cap))
                    else:
                        sub_caps.append({"name": name})
                item.record_discovery(sub_caps)
            return

        item = self._match_item(
            action=_text(args.get("intent") or args.get("action")),
            domain=_text(args.get("domain")) or None,
        )
        if item is None:
            return
        capabilities = [
            dict(capability)
            for capability in _as_list(data.get("capabilities"))
            if isinstance(capability, dict)
        ]
        item.record_discovery(capabilities)

    def record_authority_result(
        self,
        *,
        tool_name: str,
        args: dict[str, Any],
        data: dict[str, Any],
        error: str = "",
        tool_ok: bool = True,
    ) -> None:
        if tool_name == "batch_invoke_capabilities":
            self._record_batch(args=args, data=data, error=error, tool_ok=tool_ok)
            return

        capability_name = _text(
            args.get("capability_name")
            or data.get("capability_name")
            or args.get("workflow_name")
            or args.get("workflow_id")
            or args.get("agent_name")
            or args.get("agent_type")
        )
        item = self._match_item(
            action=_text(
                args.get("action")
                or args.get("intent")
                or args.get("workflow_name")
                or args.get("workflow_id")
                or args.get("agent_name")
                or args.get("agent_type")
            ),
            domain=_text(args.get("domain")) or None,
            capability_name=capability_name,
        )
        if item is None:
            if tool_name == "execute_workflow":
                for target in self.uncovered_items():
                    target.record_attempt(
                        capability_name=capability_name or tool_name,
                        success=bool(tool_ok),
                        payload=data.get("result") if "result" in data else data,
                        error=error or _text(data.get("error")),
                    )
            return
        needs_human = _lower(data.get("status")) == "needs_human"
        success = bool(
            tool_ok
            and _lower(data.get("status") or "success")
            not in {"error", "failed", "failure", "needs_human"}
        )
        item.record_attempt(
            capability_name=capability_name or tool_name,
            success=success,
            payload=data.get("result") if "result" in data else data,
            error=error or _text(data.get("error")),
            needs_human=needs_human,
        )

    def _record_batch(
        self,
        *,
        args: dict[str, Any],
        data: dict[str, Any],
        error: str,
        tool_ok: bool,
    ) -> None:
        invocations = [item for item in _as_list(args.get("invocations")) if isinstance(item, dict)]
        result_rows = [item for item in _as_list(data.get("results")) if isinstance(item, dict)]
        if not invocations and not result_rows:
            item = self._match_item(action="", domain=None)
            if item is not None:
                item.record_attempt(
                    capability_name="batch_invoke_capabilities",
                    success=bool(tool_ok),
                    payload=data,
                    error=error,
                )
            return
        max_len = max(len(invocations), len(result_rows))
        for index in range(max_len):
            invocation = invocations[index] if index < len(invocations) else {}
            row = result_rows[index] if index < len(result_rows) else {}
            capability_name = _text(row.get("capability_name") or invocation.get("capability_name"))
            item = self._match_item(
                action=_text(invocation.get("action") or invocation.get("intent")),
                domain=_text(invocation.get("domain")) or None,
                capability_name=capability_name,
            )
            if item is None:
                continue
            row_status = _lower(row.get("status"))
            item.record_attempt(
                capability_name=capability_name or "batch_invoke_capabilities",
                success=bool(tool_ok and row_status in {"success", "ok"}),
                payload=row.get("result") if "result" in row else row,
                error=_text(row.get("error")) or error,
                needs_human=row_status == "needs_human",
            )

    def merge_submit_args(self, args: dict[str, Any]) -> dict[str, Any]:
        merged = dict(args)
        merged["execution_plan"] = self.to_dict()
        plan_facts = [item.fact() for item in self.work_items if item.is_complete]
        existing_facts = [item for item in _as_list(merged.get("facts"))]
        if plan_facts:
            merged["facts"] = existing_facts + plan_facts
        if not _as_list(merged.get("results")) and plan_facts:
            merged["results"] = plan_facts
        return merged

    def _match_item(
        self,
        *,
        action: str = "",
        domain: str | None = None,
        capability_name: str = "",
    ) -> BackExecutionWorkItem | None:
        if not self.work_items:
            return None
        action_l = _lower(action)
        domain_l = _lower(domain)
        capability_tokens = _capability_domain_tokens(capability_name)

        scored: list[tuple[int, BackExecutionWorkItem]] = []
        for item in self.work_items:
            score = 0
            item_action = _lower(item.action)
            item_domain = _lower(item.domain)
            if action_l and item_action:
                if action_l == item_action:
                    score += 8
                elif action_l in item_action or item_action in action_l:
                    score += 4
            if domain_l and item_domain and domain_l == item_domain:
                score += 5
            if item_domain and item_domain in capability_tokens:
                score += 3
            if item_action:
                action_tokens = set(item_action.replace("_", " ").split())
                if action_tokens.intersection(capability_tokens):
                    score += 2
            if score:
                scored.append((score, item))
        if scored:
            scored.sort(key=lambda pair: (-pair[0], pair[1].intent_index))
            return scored[0][1]

        pending = [item for item in self.work_items if not item.is_complete]
        if len(pending) == 1:
            return pending[0]
        if len(self.work_items) == 1:
            return self.work_items[0]
        return None
