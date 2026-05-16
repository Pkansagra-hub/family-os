"""GroundingCapsuleBuilder — render a ``SituationFrame`` into a prompt-safe capsule.

The capsule is the prompt-time projection of the actor's
``S(actor) ∩ F ∩ C`` triple. It is injected by
``DynamicPromptBuilder`` as a late stage so every Front prompt grounds
the LLM in the actor's own self/family/constitution slice.

Design contract (whiteboard V0 + ``SERVICE_DESIGN_SELF_MODEL.md`` §6.4):

* Pure function of ``SituationFrame`` (no I/O, no side effects).
* Always emits the same five blocks in the same order.
* Hard size cap (default 2 KB) enforced by truncating later blocks
  before earlier ones (rules > capabilities > family > footer).
* BLACK-banded payloads must be **redacted** rather than reproduced --
  redaction substitutes a non-revealing sentinel.
* Freshness footer carries enough information for downstream tooling
  to decide whether to escalate (worst-of-three across self / family /
  constitution).
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from k1.selfmodel.contracts.capsule import GroundingCapsule
from k1.selfmodel.contracts.privacy import BlackBandLeakError, PrivacyBand
from k1.selfmodel.contracts.situation import SituationFrame

__all__ = ["GroundingCapsuleBuilder", "DEFAULT_CAPSULE_SIZE_LIMIT"]

logger = logging.getLogger(__name__)

# 2 KB hard cap (whiteboard p95 budget).
DEFAULT_CAPSULE_SIZE_LIMIT: int = 2_048

# Sentinel substituted whenever a BLACK-banded payload is encountered.
_BLACK_REDACTION = "[redacted: BLACK]"

# Stable ordering of freshness severity for the footer's worst-of-three.
_FRESHNESS_RANK: dict[str, int] = {
    "fresh": 0,
    "stale": 1,
    "offline_local_only": 2,
    "conflict_pending": 3,
}


@dataclass(frozen=True)
class _BuiltBlocks:
    actor: str  # legacy — kept for back-compat tests
    family: str  # legacy
    rules: str  # legacy (constitution rule_ids list)
    capabilities: str  # legacy
    footer: str
    # M7 typed blocks
    self_block: str = ""
    preferences: str = ""
    hobbies: str = ""
    goals: str = ""
    routines: str = ""
    space_graph: str = ""
    context: str = ""
    # M6 conscience block
    conscience: str = ""


class GroundingCapsuleBuilder:
    """Pure renderer that turns a SituationFrame into a GroundingCapsule.

    Stateless. Constructed once at session bootstrap; every
    ``build()`` call is independent.
    """

    __slots__ = ("_size_limit", "_clock_ms")

    def __init__(
        self,
        *,
        size_limit_bytes: int = DEFAULT_CAPSULE_SIZE_LIMIT,
        clock_ms=None,
    ) -> None:
        if not isinstance(size_limit_bytes, int) or size_limit_bytes <= 0:
            raise ValueError("size_limit_bytes must be a positive int")
        self._size_limit = size_limit_bytes
        # Test seam — production passes ``time.time``-style callable.
        self._clock_ms = clock_ms or (lambda: int(time.time() * 1000))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def build(self, frame: SituationFrame) -> GroundingCapsule:
        """Render ``frame`` into a ``GroundingCapsule``.

        Raises:
            TypeError: if ``frame`` is not a :class:`SituationFrame`.
            BlackBandLeakError: if a BLACK-banded payload reaches the
                renderer that does not get redacted by upstream
                composition (defense in depth — the composer should
                strip BLACK first; this is a final check).
        """
        if not isinstance(frame, SituationFrame):
            raise TypeError(f"frame must be SituationFrame, got {type(frame).__name__}")

        blocks = _BuiltBlocks(
            actor=self._render_actor(frame),
            family=self._render_family(frame),
            rules=self._render_rules(frame),
            capabilities=self._render_capabilities(frame),
            footer=self._render_footer(frame),
            self_block=self._render_self(frame),
            preferences=self._render_preferences(frame),
            hobbies=self._render_hobbies(frame),
            goals=self._render_goals(frame),
            routines=self._render_routines(frame),
            space_graph=self._render_space_graph(frame),
            context=self._render_context(frame),
            conscience=self._render_conscience(frame),
        )
        blocks = self._enforce_size_limit(blocks)

        return GroundingCapsule(
            actor_block=blocks.actor,
            family_block=blocks.family,
            rules_block=blocks.rules,
            capabilities_block=blocks.capabilities,
            freshness_footer=blocks.footer,
            rendered_at_ms=self._clock_ms(),
            self_block=blocks.self_block,
            preferences_block=blocks.preferences,
            hobbies_block=blocks.hobbies,
            goals_block=blocks.goals,
            routines_block=blocks.routines,
            space_graph_block=blocks.space_graph,
            context_block=blocks.context,
            conscience_block=blocks.conscience,
        )

    # ------------------------------------------------------------------
    # Block renderers
    # ------------------------------------------------------------------
    def _render_actor(self, frame: SituationFrame) -> str:
        proj = frame.projected_self or {}
        if _has_black_band(proj):
            raise BlackBandLeakError("actor projected_self contains BLACK-banded fields")
        name = _safe_str(proj.get("display_name") or proj.get("name") or frame.actor_id)
        role = _safe_str(proj.get("role") or "member")
        age_band = _safe_str(proj.get("age_band") or "")
        situation = _safe_str(frame.situation_kind or "unspecified")
        device = _safe_str(frame.device_id or "")

        lines = [
            "[actor]",
            f"id={_safe_str(frame.actor_id)}",
            f"name={name}",
            f"role={role}",
        ]
        if age_band:
            lines.append(f"age_band={age_band}")
        lines.append(f"situation={situation}")
        if device:
            lines.append(f"device={device}")
        return "\n".join(lines)

    def _render_family(self, frame: SituationFrame) -> str:
        rel = frame.relations
        edges = rel.edges if rel else ()
        others = rel.projected_others if rel else ()

        # Trusted roster: the actor's own L3 view of who's in their family.
        # This is NOT subject to E2 default-deny visibility (the actor is
        # always allowed to know their own family). It is the surface that
        # lets the LLM resolve casual references like nicknames/aliases.
        proj = frame.projected_self or {}
        roster_raw = proj.get("family_members") or ()
        roster: list[dict] = []
        if isinstance(roster_raw, (list, tuple)):
            for entry in roster_raw:
                if isinstance(entry, dict):
                    roster.append(entry)

        # Active actor's own aliases (if seeded) — helpful when the user
        # refers to themselves by a nickname.
        self_aliases_raw = proj.get("aliases") or ()
        self_aliases: list[str] = []
        if isinstance(self_aliases_raw, (list, tuple)):
            self_aliases = [_safe_str(a) for a in self_aliases_raw if a]

        if not edges and not others and not roster and not self_aliases:
            return "[family]\n(no related members in this frame)"

        lines = ["[family]"]

        # Roster first — gives the LLM a clean name+alias resolution map
        # before any privacy-projected attribute details.
        if self_aliases:
            lines.append("- self aliases: " + ", ".join(self_aliases))
        for entry in roster:
            mid = _safe_str(entry.get("member_id") or "")
            disp = _safe_str(entry.get("display_name") or "")
            role = _safe_str(entry.get("role") or "member")
            aliases_raw = entry.get("aliases") or ()
            if isinstance(aliases_raw, (list, tuple)):
                aliases = [_safe_str(a) for a in aliases_raw if a]
            else:
                aliases = []
            line = f"- {disp or mid} ({role}, id={mid})"
            if aliases:
                line += " aliases: " + ", ".join(aliases)
            lines.append(line)

        # Privacy-projected attribute details (E1 ∩ E2 ∩ E5 filtered).
        for other in others:
            visible = other.visible_attributes or {}
            if _has_black_band(visible):
                # Defense-in-depth: never re-emit raw BLACK content.
                attrs_part = _BLACK_REDACTION
            else:
                attrs = (
                    ", ".join(
                        f"{k}={_safe_str(v)}" for k, v in sorted(visible.items()) if v is not None
                    )
                    or "-"
                )
                attrs_part = attrs
            lines.append(
                f"- {_safe_str(other.member_id)} "
                f"({_safe_str(other.role or 'member')}, "
                f"{_safe_str(other.display_name or '')}): {attrs_part}"
            )
        for edge in edges:
            kind = _safe_str(getattr(edge, "kind", ""))
            src = _safe_str(getattr(edge, "src", ""))
            dst = _safe_str(getattr(edge, "dst", ""))
            if not kind:
                continue
            lines.append(f"- edge {src}--{kind}-->{dst}")
        return "\n".join(lines)

    def _render_rules(self, frame: SituationFrame) -> str:
        rules = frame.rules
        if not rules or not rules.rule_ids:
            return "[rules]\n(no constitution rules currently apply)"
        lines = ["[rules]", f"constitution_version={_safe_str(rules.constitution_version or 'v0')}"]
        for rid in rules.rule_ids:
            lines.append(f"- {_safe_str(rid)}")
        return "\n".join(lines)

    def _render_capabilities(self, frame: SituationFrame) -> str:
        caps = frame.capabilities
        if not caps or (
            not caps.can_do and not caps.requires_confirmation and not caps.requires_identity_tier
        ):
            return "[capabilities]\n(none granted)"
        lines = ["[capabilities]"]
        if caps.can_do:
            lines.append("can_do=" + ",".join(sorted(caps.can_do)))
        if caps.requires_confirmation:
            lines.append("requires_confirmation=" + ",".join(sorted(caps.requires_confirmation)))
        if caps.requires_identity_tier:
            tier_pairs = sorted(caps.requires_identity_tier.items())
            lines.append(
                "requires_identity_tier=" + ",".join(f"{name}:{tier}" for name, tier in tier_pairs)
            )
        return "\n".join(lines)

    def _render_footer(self, frame: SituationFrame) -> str:
        worst = self._worst_freshness(frame.freshness or {})
        lines = [
            "[freshness]",
            f"composed_at_ms={int(frame.composed_at_ms or 0)}",
            f"worst_of_three={worst}",
        ]
        if frame.freshness:
            for key in sorted(frame.freshness):
                lines.append(f"{key}={_safe_str(frame.freshness[key])}")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # M7 typed user-content renderers
    # ------------------------------------------------------------------
    def _render_self(self, frame: SituationFrame) -> str:
        sv = frame.self_view
        if sv is None:
            return ""
        lines = ["[self]"]
        if sv.display_name:
            lines.append(f"name={_safe_str(sv.display_name)}")
        if sv.role:
            lines.append(f"role={_safe_str(sv.role)}")
        if sv.age_band:
            lines.append(f"age_band={_safe_str(sv.age_band)}")
        if sv.language:
            lines.append(f"language={_safe_str(sv.language)}")
        if sv.pronouns:
            lines.append(f"pronouns={_safe_str(sv.pronouns)}")
        # occupation lives in L1_core but not on SelfView — pull from projected_self
        projected = getattr(frame, "projected_self", None) or {}
        occ = projected.get("occupation", "")
        if occ:
            lines.append(f"occupation={_safe_str(occ)}")
        if len(lines) == 1:
            return ""
        return "\n".join(lines)

    def _render_preferences(self, frame: SituationFrame) -> str:
        sv = frame.self_view
        if sv is None or not sv.preferences:
            return ""
        lines = ["[preferences]"]
        for k in sorted(sv.preferences):
            lines.append(f"- {_safe_str(k)}={_safe_str(sv.preferences[k])}")
        return "\n".join(lines)

    def _render_hobbies(self, frame: SituationFrame) -> str:
        sv = frame.self_view
        if sv is None or not (sv.hobbies or sv.likes or sv.dislikes):
            return ""
        lines = ["[hobbies]"]
        if sv.hobbies:
            lines.append("hobbies=" + ", ".join(_safe_str(h) for h in sv.hobbies))
        if sv.likes:
            lines.append("likes=" + ", ".join(_safe_str(h) for h in sv.likes))
        if sv.dislikes:
            lines.append("dislikes=" + ", ".join(_safe_str(h) for h in sv.dislikes))
        return "\n".join(lines)

    def _render_goals(self, frame: SituationFrame) -> str:
        sv = frame.self_view
        if sv is None or not sv.goals:
            return ""
        lines = ["[goals]"]
        for g in sv.goals:
            if g.status not in ("active", "paused"):
                continue
            lines.append(
                f"- {_safe_str(g.summary or g.goal_id)} "
                f"(horizon={_safe_str(g.horizon)}, status={_safe_str(g.status)})"
            )
        if len(lines) == 1:
            return ""
        return "\n".join(lines)

    def _render_routines(self, frame: SituationFrame) -> str:
        sv = frame.self_view
        if sv is None or not (sv.routines or sv.habits):
            return ""
        lines = ["[routines]"]
        for r in sv.routines:
            lines.append(f"- {_safe_str(r.name or r.routine_id)} ({_safe_str(r.schedule)})")
        for h in sv.habits:
            lines.append(f"- habit: {_safe_str(h.summary or h.habit_id)} ({_safe_str(h.cadence)})")
        return "\n".join(lines)

    def _render_space_graph(self, frame: SituationFrame) -> str:
        rel = frame.relations
        if rel is None:
            return ""
        family_routines: tuple = getattr(rel, "space_routines", ()) or ()
        others = rel.projected_others or ()
        if not family_routines and not others:
            return ""
        lines = ["[space]"]
        for other in others:
            visible = other.visible_attributes or {}
            if _has_black_band(visible):
                attrs_part = _BLACK_REDACTION
            else:
                attrs = (
                    ", ".join(
                        f"{k}={_safe_str(v)}" for k, v in sorted(visible.items()) if v is not None
                    )
                    or "-"
                )
                attrs_part = attrs
            lines.append(
                f"- {_safe_str(other.member_id)} "
                f"({_safe_str(other.role or 'member')}, "
                f"{_safe_str(other.display_name or '')}): {attrs_part}"
            )
        for r in family_routines:
            name = _safe_str(getattr(r, "name", "") or getattr(r, "routine_id", ""))
            sched = _safe_str(getattr(r, "schedule", ""))
            if name:
                lines.append(f"- routine: {name} ({sched})")
        return "\n".join(lines)

    def _render_context(self, frame: SituationFrame) -> str:
        sv = frame.self_view
        situation = _safe_str(frame.situation_kind or "")
        device = _safe_str(frame.device_id or "")
        comm_style = _safe_str(sv.communication_style if sv else "")
        if not (situation or device or comm_style):
            return ""
        lines = ["[context]"]
        if situation:
            lines.append(f"situation={situation}")
        if device:
            lines.append(f"device={device}")
        if comm_style:
            lines.append(f"communication_style={comm_style}")
        return "\n".join(lines)

    def _render_conscience(self, frame: SituationFrame) -> str:
        digest = frame.conscience
        if digest is None:
            return ""
        if not (
            digest.forbidden_acts
            or digest.must_ask_acts
            or digest.tier_floor
            or digest.risk_overrides
            or digest.protections
        ):
            # Empty conscience is meaningful — emit a minimal block so
            # the LLM knows it has been told "nothing is forbidden".
            return "[conscience]\n(no forbidden or must-ask acts in this situation)"
        lines = ["[conscience]"]
        if digest.forbidden_acts:
            lines.append("forbidden=" + ", ".join(sorted(digest.forbidden_acts)))
        if digest.must_ask_acts:
            lines.append("must_ask=" + ", ".join(sorted(digest.must_ask_acts)))
        if digest.tier_floor:
            tier_pairs = sorted(digest.tier_floor.items())
            lines.append("tier_floor=" + ",".join(f"{name}:{tier}" for name, tier in tier_pairs))
        if digest.risk_overrides:
            risk_pairs = sorted(digest.risk_overrides.items())
            lines.append("risk_overrides=" + ",".join(f"{name}:{r}" for name, r in risk_pairs))
        if digest.protections:
            lines.append("protections=" + ", ".join(sorted(digest.protections)))
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _worst_freshness(freshness: dict[str, str]) -> str:
        if not freshness:
            return "fresh"
        worst = "fresh"
        worst_rank = _FRESHNESS_RANK[worst]
        for value in freshness.values():
            rank = _FRESHNESS_RANK.get(value, _FRESHNESS_RANK["fresh"])
            if rank > worst_rank:
                worst, worst_rank = value, rank
        return worst

    def _enforce_size_limit(self, blocks: _BuiltBlocks) -> _BuiltBlocks:
        """Truncate blocks (footer/capabilities last) so total <= cap.

        Truncation order (preserve highest-priority semantic content):
        legacy capabilities/family/rules first, then preferences/hobbies/
        goals/routines/space_graph, then context, conscience, self_block,
        and footer last (footer always preserved).
        """
        order_to_truncate = (
            "capabilities",
            "rules",
            "family",
            "actor",  # legacy actor (self_block carries the typed copy)
            "preferences",
            "hobbies",
            "goals",
            "routines",
            "space_graph",
            "context",
            "conscience",
            "self_block",
            "footer",
        )
        block_dict = {
            "actor": blocks.actor,
            "family": blocks.family,
            "rules": blocks.rules,
            "capabilities": blocks.capabilities,
            "footer": blocks.footer,
            "self_block": blocks.self_block,
            "preferences": blocks.preferences,
            "hobbies": blocks.hobbies,
            "goals": blocks.goals,
            "routines": blocks.routines,
            "space_graph": blocks.space_graph,
            "context": blocks.context,
            "conscience": blocks.conscience,
        }
        total = sum(len(b.encode("utf-8")) for b in block_dict.values())
        if total <= self._size_limit:
            return blocks
        for key in order_to_truncate:
            if total <= self._size_limit:
                break
            block_bytes = block_dict[key].encode("utf-8")
            if not block_bytes:
                continue
            overflow = total - self._size_limit
            keep = max(0, len(block_bytes) - overflow - len(b" ...[truncated]"))
            truncated = block_bytes[:keep].decode("utf-8", errors="ignore") + " ...[truncated]"
            block_dict[key] = truncated
            total = sum(len(v.encode("utf-8")) for v in block_dict.values())
        return _BuiltBlocks(
            actor=block_dict["actor"],
            family=block_dict["family"],
            rules=block_dict["rules"],
            capabilities=block_dict["capabilities"],
            footer=block_dict["footer"],
            self_block=block_dict["self_block"],
            preferences=block_dict["preferences"],
            hobbies=block_dict["hobbies"],
            goals=block_dict["goals"],
            routines=block_dict["routines"],
            space_graph=block_dict["space_graph"],
            context=block_dict["context"],
            conscience=block_dict["conscience"],
        )


# ----------------------------------------------------------------------
# Module-level helpers
# ----------------------------------------------------------------------
def _safe_str(value: object) -> str:
    """Coerce arbitrary attribute values into a single-line prompt string."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value.replace("\n", " ").strip()
    return str(value).replace("\n", " ").strip()


def _has_black_band(payload: dict[str, object]) -> bool:
    """Return True when a payload carries an explicit BLACK band marker.

    Recognises both the enum value (``PrivacyBand.BLACK``) and the
    canonical wire string ``"BLACK"``.
    """
    if not isinstance(payload, dict):
        return False
    band = payload.get("privacy_band") or payload.get("band")
    if band is None:
        return False
    if isinstance(band, PrivacyBand):
        return band == PrivacyBand.BLACK
    return str(band).upper() == "BLACK"
