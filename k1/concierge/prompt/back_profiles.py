"""Back execution profile selection and rendering.

Profiles are compact operating hints for the Back actor. They help Back choose
the right discovery domain and execution discipline, but they never grant tools
or override Fabric contracts, schemas, policy, or HIL.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class BackExecutionProfile:
    """Static profile definition for Back task execution."""

    profile_id: str
    title: str
    domains: tuple[str, ...]
    cues: tuple[str, ...]
    param_cues: tuple[str, ...] = ()
    capability_prefixes: tuple[str, ...] = ()
    guidance: tuple[str, ...] = ()


@dataclass(frozen=True)
class SelectedBackExecutionProfile:
    """A profile selected for a task or intent with evidence."""

    profile: BackExecutionProfile
    score: int
    evidence: tuple[str, ...] = ()
    intent_index: int | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "profile_id": self.profile.profile_id,
            "score": self.score,
            "evidence": list(self.evidence),
        }
        if self.intent_index is not None:
            result["intent_index"] = self.intent_index
        return result


@dataclass(frozen=True)
class BackProfileSelection:
    """Profile selection result for one Back task."""

    selected: tuple[SelectedBackExecutionProfile, ...] = ()
    reason: str = "no_match"

    @property
    def profile_ids(self) -> tuple[str, ...]:
        return tuple(item.profile.profile_id for item in self.selected)

    def to_dict(self) -> dict[str, Any]:
        return {
            "reason": self.reason,
            "profiles": [item.to_dict() for item in self.selected],
        }


_PROFILES: dict[str, BackExecutionProfile] = {
    "calendar.v1": BackExecutionProfile(
        profile_id="calendar.v1",
        title="Calendar and schedule execution",
        domains=("calendar", "schedule", "scheduling", "events"),
        cues=(
            "calendar",
            "event",
            "meeting",
            "appointment",
            "schedule",
            "reschedule",
            "invite",
            "availability",
        ),
        param_cues=("start", "end", "attendees", "rrule", "location", "event_id"),
        capability_prefixes=("tool.read.calendar.", "tool.execute.calendar."),
        guidance=(
            "Use calendar as the system of record for dated events, meetings, appointments, invites, and availability.",
            "For writes, discover the exact calendar capability, inspect required fields, then include start/end times and timezone-sensitive details when known.",
            "When a reminder or task is linked to an event, preserve returned event identifiers in results or semantic_context for the follow-up write.",
        ),
    ),
    "tasks.v1": BackExecutionProfile(
        profile_id="tasks.v1",
        title="Task and checklist execution",
        domains=("tasks", "task", "todo", "to_do", "checklist"),
        cues=(
            "task",
            "todo",
            "to-do",
            "checklist",
            "complete",
            "assign",
            "due",
            "priority",
            "list",
        ),
        param_cues=("assigned_to", "due_at", "list_id", "priority", "status", "task_id"),
        capability_prefixes=("tool.read.tasks.", "tool.execute.tasks."),
        guidance=(
            "Use tasks as the system of record for obligations, assignments, checklists, status changes, and due dates that are not calendar events.",
            "Do not convert a task into a calendar event just because it has a due time; discover tasks first when the intent or domain says task.",
            "For cross-member assignment or status-changing writes, preserve assignee, due date, priority, and version/conflict fields returned by the schema.",
        ),
    ),
    "reminders.v1": BackExecutionProfile(
        profile_id="reminders.v1",
        title="Reminder and notification execution",
        domains=("reminders", "reminder", "notifications", "notification"),
        cues=(
            "reminder",
            "remind",
            "notification",
            "notify",
            "alert",
            "snooze",
            "dismiss",
        ),
        param_cues=("trigger", "recipient", "linked_event_id", "message", "reminder_id"),
        capability_prefixes=("tool.read.reminders.", "tool.execute.reminders."),
        guidance=(
            "Use reminders for time, location, or event-offset prompts that should notify someone later.",
            "Discover reminder capabilities before invoking; do not guess names such as set_reminder or send_reminder.",
            "If the reminder is tied to a calendar event, chain from the calendar result and fill linked_event_id only from an authoritative returned id.",
        ),
    ),
    "chores.v1": BackExecutionProfile(
        profile_id="chores.v1",
        title="Chore execution",
        domains=("chores", "chore", "household"),
        cues=("chore", "chores", "points", "allowance", "skip chore", "reopen chore"),
        param_cues=("template_id", "occurrence_id", "assignee", "points_awarded"),
        capability_prefixes=("tool.read.chores.", "tool.execute.chores."),
        guidance=(
            "Use chores for recurring household work, chore occurrences, points, skips, and reopen actions.",
            "Respect role and parent/guardian gates returned by the tool or policy layer.",
        ),
    ),
    "shopping.v1": BackExecutionProfile(
        profile_id="shopping.v1",
        title="Shopping list execution",
        domains=("shopping", "groceries", "grocery"),
        cues=("shopping", "grocery", "groceries", "buy", "add to list", "shopping list"),
        param_cues=("item", "quantity", "store", "shopping_item_id"),
        capability_prefixes=("tool.read.shopping.", "tool.execute.shopping."),
        guidance=(
            "Use shopping for grocery or shopping-list records when a matching adapter exists.",
            "If discovery returns no shopping capability, report needs_human or use the closest discovered list capability; do not invent the adapter.",
        ),
    ),
    "email.v1": BackExecutionProfile(
        profile_id="email.v1",
        title="Email and message execution",
        domains=("email", "mail", "messaging", "communication"),
        cues=("email", "mail", "message", "send", "draft", "reply", "forward"),
        param_cues=("to", "cc", "bcc", "subject", "body", "thread_id"),
        capability_prefixes=("tool.read.email.", "tool.execute.email.", "tool.execute.messaging."),
        guidance=(
            "Use communication capabilities for drafts, sends, replies, and message lookup.",
            "Sending is a side effect; verify the user explicitly requested it or request HIL approval.",
        ),
    ),
    "finance.v1": BackExecutionProfile(
        profile_id="finance.v1",
        title="Finance execution",
        domains=("finance", "money", "banking", "billing"),
        cues=("payment", "bill", "budget", "bank", "invoice", "receipt", "transaction"),
        param_cues=("amount", "currency", "account", "merchant", "invoice_id"),
        capability_prefixes=("tool.read.finance.", "tool.execute.finance."),
        guidance=(
            "Use finance capabilities for account, bill, transaction, invoice, payment, and budget records.",
            "Treat payment or account-changing actions as high-risk side effects and follow policy/HIL responses exactly.",
        ),
    ),
    "health.v1": BackExecutionProfile(
        profile_id="health.v1",
        title="Health execution",
        domains=("health", "medical", "care", "elder_care"),
        cues=("health", "doctor", "medication", "appointment", "symptom", "care", "medical"),
        param_cues=("patient", "provider", "medication", "dosage", "clinic"),
        capability_prefixes=("tool.read.health.", "tool.execute.health."),
        guidance=(
            "Use health capabilities for authoritative medical, care, medication, or provider-owned records.",
            "Do not present general model knowledge as medical authority; mark provenance and defer specifics to providers or specialists.",
        ),
    ),
    "system_of_record.generic.v1": BackExecutionProfile(
        profile_id="system_of_record.generic.v1",
        title="Generic system-of-record execution",
        domains=("system_of_record", "records", "tools"),
        cues=("create", "update", "delete", "check", "list", "read", "verify", "reconcile"),
        guidance=(
            "For live records, discover capabilities, inspect schemas, invoke exact registry names, and copy structured results into submit_result.",
            "Use memory only as context for live-record work; the capability result is the authoritative answer.",
        ),
    ),
}

_MATCH_THRESHOLD = 35
_MAX_SELECTED = 3


def get_back_execution_profile(profile_id: str) -> BackExecutionProfile | None:
    """Return a registered profile by id."""
    return _PROFILES.get(profile_id)


def list_back_execution_profiles() -> tuple[BackExecutionProfile, ...]:
    """Return all registered Back profiles."""
    return tuple(_PROFILES.values())


def select_back_execution_profiles(
    task: dict[str, Any] | None,
    *,
    reference_context: dict[str, Any] | None = None,
    max_profiles: int = _MAX_SELECTED,
) -> BackProfileSelection:
    """Select execution profiles for a Back task.

    Existing ``task["execution_profiles"]`` metadata wins so resumes can reuse
    the original selection. Without existing metadata, each intent is scored
    independently and then de-duplicated by profile id.
    """
    if not task:
        return _generic_selection("empty_task")

    existing_selection = _selection_from_task_metadata(task)
    if existing_selection is not None:
        return existing_selection

    intents = _task_intents(task)
    reference_context = reference_context or _dict_value(task.get("reference_context")) or {}
    scored: list[SelectedBackExecutionProfile] = []

    for intent_index, intent in enumerate(intents):
        scored.extend(_score_intent(intent, intent_index, reference_context))

    if not scored:
        return _generic_selection("no_intent_match")

    by_profile: dict[str, SelectedBackExecutionProfile] = {}
    for item in sorted(scored, key=lambda candidate: candidate.score, reverse=True):
        if item.score < _MATCH_THRESHOLD:
            continue
        existing = by_profile.get(item.profile.profile_id)
        if existing is None or item.score > existing.score:
            by_profile[item.profile.profile_id] = item

    selected = tuple(
        sorted(by_profile.values(), key=lambda candidate: candidate.score, reverse=True)[
            :max_profiles
        ]
    )
    if not selected:
        return _generic_selection("below_threshold")

    return BackProfileSelection(selected=selected, reason="matched")


def render_back_execution_profile_block(
    selection: BackProfileSelection,
    *,
    max_chars: int = 1800,
) -> str:
    """Render selected profiles into a bounded Back prompt block."""
    if not selection.selected:
        return ""

    lines = [
        "\n== EXECUTION PROFILES ==",
        "These are activity-specific operating hints for this task.",
        "They do not grant tools or authority. Registry schemas, policy, HIL, and tool recovery contracts override these hints.",
    ]
    for selected in selection.selected:
        evidence = ", ".join(selected.evidence[:3]) or "selector"
        lines.append(f"- {selected.profile.profile_id}: {selected.profile.title}")
        lines.append(f"  evidence: score={selected.score}; {evidence}")
        for guidance in selected.profile.guidance[:3]:
            lines.append(f"  - {guidance}")

    rendered = "\n".join(lines)
    if len(rendered) <= max_chars:
        return rendered
    suffix = "\n[profiles truncated]"
    if max_chars <= 0:
        return ""
    if len(suffix) >= max_chars:
        return suffix[:max_chars]
    return rendered[: max(0, max_chars - len(suffix))].rstrip() + suffix


def _generic_selection(reason: str) -> BackProfileSelection:
    profile = _PROFILES["system_of_record.generic.v1"]
    return BackProfileSelection(
        selected=(
            SelectedBackExecutionProfile(
                profile=profile,
                score=_MATCH_THRESHOLD,
                evidence=(reason,),
            ),
        ),
        reason=reason,
    )


def _selection_from_task_metadata(task: dict[str, Any]) -> BackProfileSelection | None:
    raw_profiles = task.get("execution_profiles")
    if not isinstance(raw_profiles, list) or not raw_profiles:
        return None

    selected: list[SelectedBackExecutionProfile] = []
    for raw_item in raw_profiles:
        if not isinstance(raw_item, dict):
            continue
        profile_id = str(raw_item.get("profile_id", "") or "")
        profile = _PROFILES.get(profile_id)
        if profile is None:
            continue
        selected.append(
            SelectedBackExecutionProfile(
                profile=profile,
                score=int(raw_item.get("score") or 100),
                evidence=tuple(str(item) for item in raw_item.get("evidence", [])[:5]),
                intent_index=raw_item.get("intent_index"),
            )
        )
    if not selected:
        return None
    return BackProfileSelection(selected=tuple(selected), reason="task_metadata")


def _task_intents(task: dict[str, Any]) -> list[dict[str, Any]]:
    raw_intents = task.get("intents")
    if isinstance(raw_intents, list) and raw_intents:
        return [item for item in raw_intents if isinstance(item, dict)] or [{}]
    return [
        {
            "action": task.get("action", ""),
            "params": task.get("params", {}),
            "domain": task.get("domain"),
        }
    ]


def _score_intent(
    intent: dict[str, Any],
    intent_index: int,
    reference_context: dict[str, Any],
) -> list[SelectedBackExecutionProfile]:
    domain = _normalize_text(intent.get("domain"))
    action = _normalize_text(intent.get("action"))
    params = _dict_value(intent.get("params")) or {}
    params_text = _normalize_text(" ".join(str(key) for key in params.keys()))
    ref_text = _normalize_text(_flatten_reference_context(reference_context))

    scored: list[SelectedBackExecutionProfile] = []
    for profile in _PROFILES.values():
        if profile.profile_id == "system_of_record.generic.v1":
            continue
        score = 0
        evidence: list[str] = []

        if domain and domain in profile.domains:
            score += 80
            evidence.append(f"domain:{domain}")

        for prefix in profile.capability_prefixes:
            if prefix and prefix in action:
                score += 100
                evidence.append(f"capability_prefix:{prefix.rstrip('.')}")
                break

        cue_hits = [cue for cue in profile.cues if _contains_phrase(action, cue)]
        if cue_hits:
            score += min(72, 35 + (18 * (len(cue_hits) - 1)))
            evidence.append("action:" + "/".join(cue_hits[:3]))

        param_hits = [cue for cue in profile.param_cues if _contains_phrase(params_text, cue)]
        if param_hits:
            score += min(36, 18 * len(param_hits))
            evidence.append("params:" + "/".join(param_hits[:3]))

        ref_hits = [cue for cue in profile.cues if _contains_phrase(ref_text, cue)]
        if ref_hits:
            score += min(20, 10 * len(ref_hits))
            evidence.append("reference_context:" + "/".join(ref_hits[:2]))

        if score > 0:
            scored.append(
                SelectedBackExecutionProfile(
                    profile=profile,
                    score=score,
                    evidence=tuple(evidence),
                    intent_index=intent_index,
                )
            )
    return scored


def _dict_value(value: Any) -> dict[str, Any] | None:
    return value if isinstance(value, dict) else None


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).lower().replace("_", "-").split())


def _contains_phrase(text: str, phrase: str) -> bool:
    normalized_phrase = _normalize_text(phrase)
    if not text or not normalized_phrase:
        return False
    if " " in normalized_phrase or "-" in normalized_phrase or "." in normalized_phrase:
        return normalized_phrase in text
    return normalized_phrase in text.split() or normalized_phrase in text


def _flatten_reference_context(reference_context: dict[str, Any]) -> str:
    parts: list[str] = []
    stack: list[Any] = [reference_context]
    while stack:
        item = stack.pop()
        if isinstance(item, dict):
            parts.extend(str(key) for key in item.keys())
            stack.extend(item.values())
        elif isinstance(item, list):
            stack.extend(item)
        else:
            parts.append(str(item))
    return " ".join(parts)
