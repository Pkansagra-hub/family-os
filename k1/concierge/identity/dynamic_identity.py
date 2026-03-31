"""
k1.concierge.identity.dynamic_identity -- Dynamic Identity Context (OPP-7)

Generalized kernel primitive: enriches the static persona with dynamic,
context-aware identity fields that adapt during a conversation.

Architecture:
    PersonaSection (static identity, set at SESSION_INIT)
        -> DynamicIdentityContext (adaptive overlay per turn)
        -> PromptBuilder (injects both static + dynamic identity)

The kernel provides the identity context; verticals configure:
    - Which dynamic fields are active
    - Adaptation rules per field
    - Context sources that feed identity adaptation

Static identity (PersonaSection):
    - Personality traits, voice preferences, vocabulary
    - Set once at session init, frozen thereafter

Dynamic identity (this module):
    - Active user context (who is speaking right now)
    - Conversational role adaptation (expert vs peer vs guide)
    - Domain expertise level (learned from conversation)
    - Relationship context (formal vs casual, based on history)
    - Emotional attunement (how to relate given current affect)

The dynamic context is ephemeral -- it resets or recalculates each turn
based on the latest signals. It does NOT modify the persona section.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


class ConversationalRole(str):
    """Role the system adopts relative to the user this turn."""

    EXPERT = "expert"
    PEER = "peer"
    GUIDE = "guide"
    SUPPORTER = "supporter"
    EXECUTOR = "executor"


@dataclass
class DynamicIdentityConfig:
    """Configuration for dynamic identity adaptation.

    Attributes:
        enable_role_adaptation:  Adapt conversational role per turn.
        enable_expertise_tracking: Track domain expertise from conversation.
        enable_formality_drift:  Allow formality to drift based on signals.
        default_role:            Starting conversational role.
        expertise_learning_rate: How fast expertise scores update.
    """

    enable_role_adaptation: bool = True
    enable_expertise_tracking: bool = True
    enable_formality_drift: bool = True
    default_role: str = ConversationalRole.PEER
    expertise_learning_rate: float = 0.1


@dataclass
class IdentitySnapshot:
    """Dynamic identity state for a single turn.

    Produced fresh each turn by DynamicIdentityContext.compute().
    Consumed by PromptBuilder for identity-enriched prompts.
    """

    active_user_id: str = ""
    active_user_name: str = ""
    conversational_role: str = ConversationalRole.PEER
    domain_expertise: dict[str, float] = field(default_factory=dict)
    formality_level: float = 0.5
    relationship_turns: int = 0
    emotional_attunement: str = ""
    context_tags: list[str] = field(default_factory=list)

    def to_prompt_block(self) -> str:
        """Format as prompt injection block for identity context."""
        lines = ["== DYNAMIC IDENTITY CONTEXT =="]

        if self.active_user_name:
            lines.append(f"Speaking with: {self.active_user_name}")

        lines.append(f"Role: {self.conversational_role}")

        if self.domain_expertise:
            top_domains = sorted(self.domain_expertise.items(), key=lambda x: x[1], reverse=True)[
                :3
            ]
            expertise_str = ", ".join(f"{d} ({s:.0%})" for d, s in top_domains)
            lines.append(f"Domain expertise: {expertise_str}")

        formality_label = (
            "formal"
            if self.formality_level > 0.7
            else ("casual" if self.formality_level < 0.3 else "balanced")
        )
        lines.append(f"Register: {formality_label}")

        if self.emotional_attunement:
            lines.append(f"Attunement: {self.emotional_attunement}")

        if self.context_tags:
            lines.append(f"Context: {', '.join(self.context_tags)}")

        lines.append("== END IDENTITY ==")
        return "\n".join(lines)


class DynamicIdentityContext:
    """Computes dynamic identity overlay per turn.

    Generalized kernel primitive. Maintains session-level identity
    signals and computes a fresh IdentitySnapshot each turn.
    """

    __slots__ = (
        "_config",
        "_domain_expertise",
        "_turn_count",
        "_formality_samples",
        "_last_role",
    )

    def __init__(self, config: DynamicIdentityConfig | None = None) -> None:
        self._config = config or DynamicIdentityConfig()
        self._domain_expertise: dict[str, float] = {}
        self._turn_count: int = 0
        self._formality_samples: list[float] = []
        self._last_role: str = self._config.default_role
        logger.info("DynamicIdentityContext initialised")

    def compute(
        self,
        user_id: str = "",
        user_name: str = "",
        affect_band: str = "neutral",
        domain: str = "",
        complexity_tier: str = "LOW",
        has_inflight_tasks: bool = False,
    ) -> IdentitySnapshot:
        """Compute dynamic identity for the current turn.

        Args:
            user_id:           Active user identifier.
            user_name:         Active user display name.
            affect_band:       Current affect band.
            domain:            Current conversation domain.
            complexity_tier:   Task complexity tier.
            has_inflight_tasks: Whether background tasks are running.

        Returns:
            Fresh IdentitySnapshot for this turn.
        """
        self._turn_count += 1

        role = self._compute_role(
            complexity_tier=complexity_tier,
            affect_band=affect_band,
            has_inflight=has_inflight_tasks,
        )

        if domain and self._config.enable_expertise_tracking:
            self._update_expertise(domain)

        formality = self._compute_formality()

        attunement = self._compute_attunement(affect_band)

        tags = self._compute_context_tags(
            has_inflight=has_inflight_tasks,
            domain=domain,
        )

        snapshot = IdentitySnapshot(
            active_user_id=user_id,
            active_user_name=user_name,
            conversational_role=role,
            domain_expertise=dict(self._domain_expertise),
            formality_level=formality,
            relationship_turns=self._turn_count,
            emotional_attunement=attunement,
            context_tags=tags,
        )

        self._last_role = role
        return snapshot

    @property
    def turn_count(self) -> int:
        """Total turns processed."""
        return self._turn_count

    @property
    def domain_expertise(self) -> dict[str, float]:
        """Current domain expertise scores."""
        return dict(self._domain_expertise)

    # -----------------------------------------------------------------
    # Internal
    # -----------------------------------------------------------------

    def _compute_role(
        self,
        complexity_tier: str,
        affect_band: str,
        has_inflight: bool,
    ) -> str:
        """Select conversational role based on context."""
        if not self._config.enable_role_adaptation:
            return self._config.default_role

        if affect_band in ("crisis", "low"):
            return ConversationalRole.SUPPORTER

        if complexity_tier == "HIGH":
            return ConversationalRole.EXPERT

        if has_inflight:
            return ConversationalRole.EXECUTOR

        if self._turn_count > 10:
            return ConversationalRole.PEER

        return ConversationalRole.GUIDE

    def _update_expertise(self, domain: str) -> None:
        """Update domain expertise score based on conversation."""
        lr = self._config.expertise_learning_rate
        current = self._domain_expertise.get(domain, 0.0)
        self._domain_expertise[domain] = min(1.0, current + lr)

    def _compute_formality(self) -> float:
        """Compute formality level from accumulated signals."""
        if not self._config.enable_formality_drift:
            return 0.5

        if self._turn_count <= 3:
            return 0.6

        if self._turn_count > 20:
            return 0.3

        return max(0.2, 0.6 - (self._turn_count * 0.02))

    def _compute_attunement(self, affect_band: str) -> str:
        """Compute emotional attunement guidance."""
        attunement_map = {
            "crisis": "Be calm and grounding. Lead with action.",
            "low": "Be gentle and patient. No pressure.",
            "neutral": "Natural and efficient.",
            "positive": "Match energy. Celebrate.",
            "elevated": "Acknowledge feeling, then proceed.",
        }
        return attunement_map.get(affect_band, "")

    def _compute_context_tags(
        self,
        has_inflight: bool,
        domain: str,
    ) -> list[str]:
        """Compute context tags for prompt enrichment."""
        tags: list[str] = []

        if has_inflight:
            tags.append("multitasking")

        if self._turn_count > 15:
            tags.append("extended_session")

        if domain:
            tags.append(f"domain:{domain}")

        familiar_domains = [d for d, s in self._domain_expertise.items() if s > 0.5]
        if familiar_domains:
            tags.append("returning_topic")

        return tags
