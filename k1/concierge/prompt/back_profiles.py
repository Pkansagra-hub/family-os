"""Back execution profile selection and rendering.

Profiles are compact operating hints for the Back actor. The profile
definitions come from prompt contracts under ``k1/contracts/prompts``; this
module must not become a second hardcoded domain router.

Profiles help Back maintain execution discipline, but they never grant tools,
bind capability names, authorize side effects, or override Fabric contracts,
schemas, policy, or HIL.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BackExecutionProfile:
    """Prompt-contract-backed profile definition for Back task execution."""

    profile_id: str
    title: str
    domains: tuple[str, ...] = ()
    prompt_template: str | None = None
    guidance: tuple[str, ...] = ()
    compatible_tools: tuple[str, ...] = ()


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

    @property
    def confidence(self) -> float:
        if not self.selected:
            return 0.0
        score = max(max(item.score, 0) for item in self.selected)
        return round(min(score, 100) / 100.0, 3)

    @property
    def evidence_sources(self) -> tuple[str, ...]:
        evidence: list[str] = []
        seen: set[str] = set()
        for selected in self.selected:
            for item in selected.evidence:
                text = str(item or "").strip()
                if not text or text in seen:
                    continue
                seen.add(text)
                evidence.append(text)
        return tuple(evidence)

    def to_dict(self) -> dict[str, Any]:
        return {
            "reason": self.reason,
            "profiles": [item.to_dict() for item in self.selected],
        }

    def to_observability_dict(self, *, task_id: str = "", trace_id: str = "") -> dict[str, Any]:
        return {
            "task_id": task_id,
            "trace_id": trace_id,
            "profile_ids": list(self.profile_ids),
            "confidence": self.confidence,
            "evidence_sources": list(self.evidence_sources),
            "fallback_reason": self.reason,
        }


_MAX_SELECTED = 3
_GENERIC_PROFILE_ID = "system_of_record.generic.v1"


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

    Selection is intentionally metadata-driven:
    - Existing ``task["execution_profiles"]`` wins for resume/binder reuse.
    - Explicit ``activity_profile`` / ``execution_profile`` metadata wins.
    - Exact structured intent domain metadata may select a prompt-backed profile.
    - Free-text action/param/reference cue scanning is not performed here.

    Capability binding and discovery remain separate kernel responsibilities.
    """
    del reference_context

    if not task:
        return _generic_selection("empty_task")

    existing_selection = _selection_from_task_metadata(task)
    if existing_selection is not None:
        return existing_selection

    intents = _task_intents(task)
    explicit_selection = _selection_from_explicit_metadata(
        task,
        intents=intents,
        max_profiles=max_profiles,
    )
    if explicit_selection is not None:
        return explicit_selection

    domain_selection = _selection_from_structured_domains(intents, max_profiles=max_profiles)
    if domain_selection is not None:
        return domain_selection

    return _generic_selection("discovery_required")


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
        for guidance in selected.profile.guidance[:5]:
            lines.append(f"  - {guidance}")
        preferred = selected.profile.compatible_tools[:8]
        if preferred:
            lines.append("  preferred capabilities (soft hint — not an allowlist):")
            for cap in preferred:
                lines.append(f"    * {cap}")
            lines.append(
                "  Prefer these when the task fits. Reach beyond them only "
                "when the task clearly requires it."
            )

    rendered = "\n".join(lines)
    logger.debug(
        "render_back_execution_profile_block: rendered %d chars profiles=%s",
        len(rendered),
        [s.profile.profile_id for s in selection.selected],
    )
    if len(rendered) <= max_chars:
        return rendered
    suffix = "\n[profiles truncated]"
    if max_chars <= 0:
        return ""
    if len(suffix) >= max_chars:
        return suffix[:max_chars]
    return rendered[: max(0, max_chars - len(suffix))].rstrip() + suffix


def _generic_selection(reason: str) -> BackProfileSelection:
    profile = _PROFILES.get(_GENERIC_PROFILE_ID) or BackExecutionProfile(
        profile_id=_GENERIC_PROFILE_ID,
        title="Generic system-of-record execution",
    )
    return BackProfileSelection(
        selected=(
            SelectedBackExecutionProfile(
                profile=profile,
                score=35,
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
        profile = _profile_for_id(profile_id)
        if profile is None:
            continue
        selected.append(
            SelectedBackExecutionProfile(
                profile=profile,
                score=_safe_int(raw_item.get("score"), default=100),
                evidence=tuple(str(item) for item in raw_item.get("evidence", [])[:5]),
                intent_index=_optional_int(raw_item.get("intent_index")),
            )
        )
    if not selected:
        return None
    return BackProfileSelection(selected=tuple(selected), reason="task_metadata")


def _selection_from_explicit_metadata(
    task: dict[str, Any],
    *,
    intents: list[dict[str, Any]],
    max_profiles: int,
) -> BackProfileSelection | None:
    candidates: list[SelectedBackExecutionProfile] = []

    for key in ("activity_profile", "execution_profile", "profile_id"):
        profile_id = task.get(key)
        if isinstance(profile_id, str):
            selected = _selected_for_profile_id(
                profile_id,
                score=100,
                evidence=(f"task:{key}",),
            )
            if selected is not None:
                candidates.append(selected)

    for intent_index, intent in enumerate(intents):
        for key in ("activity_profile", "execution_profile", "profile_id"):
            profile_id = intent.get(key)
            if isinstance(profile_id, str):
                selected = _selected_for_profile_id(
                    profile_id,
                    score=100,
                    evidence=(f"intent:{key}",),
                    intent_index=intent_index,
                )
                if selected is not None:
                    candidates.append(selected)
        raw_profiles = intent.get("execution_profiles")
        if isinstance(raw_profiles, list):
            for raw_item in raw_profiles:
                if not isinstance(raw_item, dict):
                    continue
                selected = _selected_for_profile_id(
                    str(raw_item.get("profile_id", "") or ""),
                    score=_safe_int(raw_item.get("score"), default=100),
                    evidence=tuple(str(item) for item in raw_item.get("evidence", [])[:5])
                    or ("intent:execution_profiles",),
                    intent_index=intent_index,
                )
                if selected is not None:
                    candidates.append(selected)

    selected = _dedupe_selected(candidates, max_profiles=max_profiles)
    if not selected:
        return None
    return BackProfileSelection(selected=selected, reason="explicit_metadata")


def _selection_from_structured_domains(
    intents: list[dict[str, Any]],
    *,
    max_profiles: int,
) -> BackProfileSelection | None:
    candidates: list[SelectedBackExecutionProfile] = []
    for intent_index, intent in enumerate(intents):
        domain = _normalize_key(intent.get("domain"))
        if not domain:
            continue
        for profile in _PROFILES.values():
            primary_domain = _primary_domain(profile)
            if domain != primary_domain:
                continue
            candidates.append(
                SelectedBackExecutionProfile(
                    profile=profile,
                    score=80,
                    evidence=(f"domain:{domain}",),
                    intent_index=intent_index,
                )
            )

    selected = _dedupe_selected(candidates, max_profiles=max_profiles)
    if not selected:
        return None
    return BackProfileSelection(selected=selected, reason="domain_metadata")


def _task_intents(task: dict[str, Any]) -> list[dict[str, Any]]:
    raw_intents = task.get("intents")
    if isinstance(raw_intents, list) and raw_intents:
        return [item for item in raw_intents if isinstance(item, dict)] or [{}]
    return [
        {
            "params": task.get("params", {}),
            "domain": task.get("domain"),
            "activity_profile": task.get("activity_profile"),
            "execution_profile": task.get("execution_profile"),
        }
    ]


def _selected_for_profile_id(
    profile_id: str,
    *,
    score: int,
    evidence: tuple[str, ...],
    intent_index: int | None = None,
) -> SelectedBackExecutionProfile | None:
    profile = _profile_for_id(profile_id)
    if profile is None:
        return None
    return SelectedBackExecutionProfile(
        profile=profile,
        score=score,
        evidence=evidence,
        intent_index=intent_index,
    )


def _profile_for_id(profile_id: str) -> BackExecutionProfile | None:
    if not profile_id:
        return None
    return _PROFILES.get(profile_id)


def _dedupe_selected(
    candidates: list[SelectedBackExecutionProfile],
    *,
    max_profiles: int,
) -> tuple[SelectedBackExecutionProfile, ...]:
    by_profile: dict[str, SelectedBackExecutionProfile] = {}
    for candidate in candidates:
        existing = by_profile.get(candidate.profile.profile_id)
        if existing is None or candidate.score > existing.score:
            by_profile[candidate.profile.profile_id] = candidate
    return tuple(
        sorted(by_profile.values(), key=lambda item: item.score, reverse=True)[:max_profiles]
    )


def _primary_domain(profile: BackExecutionProfile) -> str:
    if not profile.domains:
        return ""
    return _normalize_key(profile.domains[0])


def _normalize_key(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip().lower()


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_int(value: Any, *, default: int) -> int:
    parsed = _optional_int(value)
    return default if parsed is None else parsed


def _load_profiles_from_prompt_contracts(
    contracts_dir: Path | None = None,
) -> dict[str, BackExecutionProfile]:
    directory = contracts_dir or _repo_root() / "k1" / "contracts" / "prompts"
    if not directory.is_dir():
        logger.warning("Back profile prompt contracts directory not found: %s", directory)
        return {}

    profiles: dict[str, BackExecutionProfile] = {}
    for path in sorted(directory.glob("*.yaml")):
        try:
            profile = _profile_from_prompt_contract(path)
        except Exception:
            logger.warning("Failed to load Back profile from %s", path, exc_info=True)
            continue
        if profile is not None:
            profiles[profile.profile_id] = profile
    return profiles


def _profile_from_prompt_contract(path: Path) -> BackExecutionProfile | None:
    import yaml

    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return None
    contract = data.get("prompt_contract")
    if not isinstance(contract, dict):
        return None

    profile_id = str(contract.get("activity_profile", "") or "")
    if not profile_id:
        return None

    template_file = str(contract.get("template_file", "") or "")
    guidance = _guidance_from_template_file(path, template_file)
    domains = tuple(str(item) for item in contract.get("domain", []) if item)

    return BackExecutionProfile(
        profile_id=profile_id,
        title=str(contract.get("description", "") or profile_id),
        domains=domains,
        prompt_template=str(contract.get("name", "") or "") or None,
        guidance=guidance,
        compatible_tools=tuple(
            str(item) for item in (contract.get("compatible_tools") or []) if item
        ),
    )


def _guidance_from_template_file(contract_path: Path, template_file: str) -> tuple[str, ...]:
    if not template_file:
        return ()
    template_path = _resolve_template_file(contract_path, template_file)
    if template_path is None:
        return ()
    lines = template_path.read_text(encoding="utf-8").splitlines()
    bullets = [line.strip()[2:].strip() for line in lines if line.strip().startswith("- ")]
    if bullets:
        return tuple(item for item in bullets if item)
    return tuple(
        line.strip() for line in lines if line.strip() and not line.lstrip().startswith("#")
    )


def _resolve_template_file(contract_path: Path, template_file: str) -> Path | None:
    candidate = Path(template_file)
    candidates = (
        [candidate]
        if candidate.is_absolute()
        else [_repo_root() / candidate, contract_path.parent / candidate]
    )
    for item in candidates:
        if item.is_file():
            return item
    return None


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


_PROFILES: dict[str, BackExecutionProfile] = _load_profiles_from_prompt_contracts()
