"""
k1.fabric.core.context_budget -- Token budget management (4.2.2 + 4.2.3).

Manages a 128K-token ceiling for ExecutionContext assembly.  Five-level
compression strategy when over budget:

  1. Drop optional_context sections
  2. Truncate history_recent to last 3 turns
  3. Summarize beliefs_active (drop low-confidence)
  4. Summarize scoreboard (keep only current QUD)
  5. Emergency: drop all WARM, keep HOT only

Token counting (4.2.3):
  - Uses tiktoken (cl100k_base) when available
  - Falls back to chars / 4 heuristic
  - Must be <1 ms for typical context

Budget allocation defaults (soft targets, enforced by compression):
  - system_prompt:    2 000 -- 5 000
  - compiled_prompt:    500 -- 2 000
  - session_sections: 10 000 -- 40 000
  - request_params:    1 000 -- 5 000
  - tool_results:      5 000 -- 20 000
  - response_headroom: 2 000 -- 8 000

Thread safety: All public methods are stateless (no shared mutable state).

References:
  - fabric_discussion.md Section 12 (Context Assembly Flow)
  - Epic 4.2.2 + 4.2.3 in fabric-implementation-plan.md
  - FAB-008 (Single Writer / read-only context)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Token counting (Issue 4.2.3)
# ---------------------------------------------------------------------------

_TIKTOKEN_ENCODING: Any = None
_TIKTOKEN_LOADED: bool = False


def _load_tiktoken() -> Any:
    """Lazy-load tiktoken cl100k_base encoding.  Returns None on import failure."""
    global _TIKTOKEN_ENCODING, _TIKTOKEN_LOADED  # noqa: PLW0603
    if _TIKTOKEN_LOADED:
        return _TIKTOKEN_ENCODING
    try:
        import tiktoken  # type: ignore[import-untyped]

        _TIKTOKEN_ENCODING = tiktoken.get_encoding("cl100k_base")
    except Exception:  # pragma: no cover -- optional dependency
        _TIKTOKEN_ENCODING = None
    _TIKTOKEN_LOADED = True
    return _TIKTOKEN_ENCODING


def count_tokens(text: str) -> int:
    """
    Count tokens in *text*.

    Uses tiktoken (cl100k_base) when available, else approximate via
    ``len(text) // 4``.

    Performance: <1 ms for typical context (~10 KB).

    Args:
        text: The string to count tokens for.

    Returns:
        Estimated token count (always >= 0).
    """
    if not text:
        return 0
    enc = _load_tiktoken()
    if enc is not None:
        return len(enc.encode(text))
    # Fallback: chars / 4 heuristic (conservative overestimate)
    return max(1, len(text) // 4)


def count_tokens_dict(data: Dict[str, Any]) -> int:
    """Count tokens for a dictionary by converting to compact repr."""
    if not data:
        return 0
    import json

    return count_tokens(json.dumps(data, separators=(",", ":")))


# ---------------------------------------------------------------------------
# Public constants
# ---------------------------------------------------------------------------

#: Hard ceiling for total token count (128K context window).
TOKEN_CEILING: int = 128_000

#: Default response headroom reserved from ceiling.
DEFAULT_RESPONSE_HEADROOM: int = 4_000

#: Minimum confidence threshold for beliefs kept during compression L3.
MIN_BELIEF_CONFIDENCE: float = 0.5

#: Maximum history turns kept during compression L2.
MAX_HISTORY_TURNS_COMPRESSED: int = 3


# ---------------------------------------------------------------------------
# Compression level enum
# ---------------------------------------------------------------------------


class CompressionLevel(str, Enum):
    """Applied compression level during budget enforcement."""

    NONE = "none"
    L1_DROP_OPTIONAL = "L1_drop_optional"
    L2_TRUNCATE_HISTORY = "L2_truncate_history"
    L3_SUMMARIZE_BELIEFS = "L3_summarize_beliefs"
    L4_SUMMARIZE_SCOREBOARD = "L4_summarize_scoreboard"
    L5_EMERGENCY_HOT_ONLY = "L5_emergency_hot_only"


# ---------------------------------------------------------------------------
# Budget allocation config
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BudgetAllocation:
    """Soft allocation targets (informational, not hard-enforced individually)."""

    system_prompt_min: int = 2_000
    system_prompt_max: int = 5_000
    compiled_prompt_min: int = 500
    compiled_prompt_max: int = 2_000
    session_sections_min: int = 10_000
    session_sections_max: int = 40_000
    request_params_min: int = 1_000
    request_params_max: int = 5_000
    tool_results_min: int = 5_000
    tool_results_max: int = 20_000
    response_headroom_min: int = 2_000
    response_headroom_max: int = 8_000

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "system_prompt": {"min": self.system_prompt_min, "max": self.system_prompt_max},
            "compiled_prompt": {"min": self.compiled_prompt_min, "max": self.compiled_prompt_max},
            "session_sections": {
                "min": self.session_sections_min,
                "max": self.session_sections_max,
            },
            "request_params": {"min": self.request_params_min, "max": self.request_params_max},
            "tool_results": {"min": self.tool_results_min, "max": self.tool_results_max},
            "response_headroom": {
                "min": self.response_headroom_min,
                "max": self.response_headroom_max,
            },
        }

    def __repr__(self) -> str:
        return f"BudgetAllocation(ceiling={TOKEN_CEILING})"


# ---------------------------------------------------------------------------
# Budget result
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BudgetResult:
    """Outcome of applying the token budget to assembled sections."""

    #: Final session_sections dict (possibly compressed).
    session_sections: Dict[str, Any] = field(default_factory=dict)

    #: Final compiled prompt (possibly None).
    prompt: Optional[str] = None

    #: Final request params dict.
    params: Dict[str, Any] = field(default_factory=dict)

    #: Total token count across all parts.
    total_tokens: int = 0

    #: Highest compression level applied.
    compression_applied: CompressionLevel = CompressionLevel.NONE

    #: Sections dropped during compression (names).
    sections_dropped: List[str] = field(default_factory=list)

    #: Whether the result is still over budget after all compression.
    over_budget: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "total_tokens": self.total_tokens,
            "compression_applied": self.compression_applied.value,
            "sections_dropped": list(self.sections_dropped),
            "over_budget": self.over_budget,
        }

    def __repr__(self) -> str:
        return (
            f"BudgetResult(tokens={self.total_tokens}, "
            f"compression={self.compression_applied.value}, "
            f"over_budget={self.over_budget})"
        )


# ---------------------------------------------------------------------------
# ContextBudget configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ContextBudgetConfig:
    """Configuration for ContextBudget."""

    #: Hard ceiling (tokens).
    ceiling: int = TOKEN_CEILING

    #: Response headroom reserved from ceiling.
    response_headroom: int = DEFAULT_RESPONSE_HEADROOM

    #: Min belief confidence kept during L3 compression.
    min_belief_confidence: float = MIN_BELIEF_CONFIDENCE

    #: Max history turns kept during L2 compression.
    max_history_turns: int = MAX_HISTORY_TURNS_COMPRESSED

    #: Budget allocation targets.
    allocation: BudgetAllocation = field(default_factory=BudgetAllocation)

    def __repr__(self) -> str:
        return f"ContextBudgetConfig(ceiling={self.ceiling}, " f"headroom={self.response_headroom})"


# ---------------------------------------------------------------------------
# HOT / WARM section classification (mirrors SessionState tiers)
# ---------------------------------------------------------------------------

HOT_SECTION_NAMES: frozenset[str] = frozenset(
    {
        "control",
        "beliefs_active",
        "scoreboard",
        "history_active",
        "clarifications",
        "affective_now",
        "narrative_active",
        "meta",
    }
)

WARM_SECTION_NAMES: frozenset[str] = frozenset(
    {
        "beliefs_history",
        "history_recent",
        "persona",
        "telemetry",
    }
)

ALL_SECTION_NAMES: frozenset[str] = HOT_SECTION_NAMES | WARM_SECTION_NAMES


# ---------------------------------------------------------------------------
# ContextBudget -- main class
# ---------------------------------------------------------------------------


class ContextBudget:
    """
    Token budget manager for ExecutionContext assembly.

    Enforces a hard 128K token ceiling with a 5-level compression strategy
    when the assembled context exceeds the budget.

    Stateless per call -- all state is passed in and returned via
    ``BudgetResult``.  Thread-safe (no shared mutable state).

    Usage::

        budget = ContextBudget()
        result = budget.apply(
            session_sections={"control": {...}, "beliefs_active": {...}},
            prompt="You are a helpful assistant.",
            params={"query": "turn on lights"},
            optional_sections=["persona", "telemetry"],
        )
        assert not result.over_budget
    """

    __slots__ = ("_config",)

    def __init__(self, config: Optional[ContextBudgetConfig] = None) -> None:
        self._config: ContextBudgetConfig = config or ContextBudgetConfig()

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def config(self) -> ContextBudgetConfig:
        """Current configuration (frozen)."""
        return self._config

    @property
    def effective_budget(self) -> int:
        """Ceiling minus response headroom."""
        return max(0, self._config.ceiling - self._config.response_headroom)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def apply(
        self,
        session_sections: Dict[str, Any],
        prompt: Optional[str] = None,
        params: Optional[Dict[str, Any]] = None,
        optional_sections: Optional[Sequence[str]] = None,
    ) -> BudgetResult:
        """
        Apply token budget to assembled context.

        Runs the 5-level compression strategy if the total token count
        exceeds ``effective_budget``.

        Args:
            session_sections: Section name -> section data dict.
            prompt: Compiled prompt string (may be None).
            params: Request parameters dict.
            optional_sections: Names of optional sections (dropped first).

        Returns:
            BudgetResult with compressed sections, total tokens, and
            compression metadata.
        """
        params = params or {}
        optional_set: frozenset[str] = frozenset(optional_sections or ())

        # --- mutable working copies ---
        working_sections = dict(session_sections)
        working_prompt = prompt
        working_params = dict(params)
        dropped: List[str] = []
        compression = CompressionLevel.NONE

        budget = self.effective_budget

        # --- check if already within budget ---
        total = self._total_tokens(working_sections, working_prompt, working_params)
        if total <= budget:
            return BudgetResult(
                session_sections=working_sections,
                prompt=working_prompt,
                params=working_params,
                total_tokens=total,
                compression_applied=compression,
                sections_dropped=dropped,
                over_budget=False,
            )

        # --- L1: Drop optional_context sections ---
        compression = CompressionLevel.L1_DROP_OPTIONAL
        for name in sorted(optional_set):
            if name in working_sections:
                del working_sections[name]
                dropped.append(name)
        total = self._total_tokens(working_sections, working_prompt, working_params)
        if total <= budget:
            return BudgetResult(
                session_sections=working_sections,
                prompt=working_prompt,
                params=working_params,
                total_tokens=total,
                compression_applied=compression,
                sections_dropped=dropped,
                over_budget=False,
            )

        # --- L2: Truncate history_recent to last N turns ---
        compression = CompressionLevel.L2_TRUNCATE_HISTORY
        self._truncate_history(working_sections, self._config.max_history_turns)
        total = self._total_tokens(working_sections, working_prompt, working_params)
        if total <= budget:
            return BudgetResult(
                session_sections=working_sections,
                prompt=working_prompt,
                params=working_params,
                total_tokens=total,
                compression_applied=compression,
                sections_dropped=dropped,
                over_budget=False,
            )

        # --- L3: Summarize beliefs_active (drop low-confidence) ---
        compression = CompressionLevel.L3_SUMMARIZE_BELIEFS
        self._filter_beliefs(working_sections, self._config.min_belief_confidence)
        total = self._total_tokens(working_sections, working_prompt, working_params)
        if total <= budget:
            return BudgetResult(
                session_sections=working_sections,
                prompt=working_prompt,
                params=working_params,
                total_tokens=total,
                compression_applied=compression,
                sections_dropped=dropped,
                over_budget=False,
            )

        # --- L4: Summarize scoreboard (keep only current QUD) ---
        compression = CompressionLevel.L4_SUMMARIZE_SCOREBOARD
        self._summarize_scoreboard(working_sections)
        total = self._total_tokens(working_sections, working_prompt, working_params)
        if total <= budget:
            return BudgetResult(
                session_sections=working_sections,
                prompt=working_prompt,
                params=working_params,
                total_tokens=total,
                compression_applied=compression,
                sections_dropped=dropped,
                over_budget=False,
            )

        # --- L5: Emergency -- drop all WARM, keep HOT only ---
        compression = CompressionLevel.L5_EMERGENCY_HOT_ONLY
        for name in list(working_sections):
            if name in WARM_SECTION_NAMES:
                del working_sections[name]
                if name not in dropped:
                    dropped.append(name)
        total = self._total_tokens(working_sections, working_prompt, working_params)

        return BudgetResult(
            session_sections=working_sections,
            prompt=working_prompt,
            params=working_params,
            total_tokens=total,
            compression_applied=compression,
            sections_dropped=sorted(dropped),
            over_budget=(total > budget),
        )

    # ------------------------------------------------------------------
    # Internal: Token counting helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _total_tokens(
        sections: Dict[str, Any],
        prompt: Optional[str],
        params: Dict[str, Any],
    ) -> int:
        """Sum tokens across all parts."""
        total = 0
        total += count_tokens_dict(sections)
        if prompt:
            total += count_tokens(prompt)
        total += count_tokens_dict(params)
        return total

    # ------------------------------------------------------------------
    # Internal: Compression strategies
    # ------------------------------------------------------------------

    @staticmethod
    def _truncate_history(sections: Dict[str, Any], max_turns: int) -> None:
        """L2: Truncate ``history_recent`` to last *max_turns* turns."""
        hr = sections.get("history_recent")
        if not isinstance(hr, dict):
            return
        turns = hr.get("turns")
        if isinstance(turns, list) and len(turns) > max_turns:
            hr["turns"] = turns[-max_turns:]

    @staticmethod
    def _filter_beliefs(sections: Dict[str, Any], min_confidence: float) -> None:
        """L3: Remove low-confidence beliefs from ``beliefs_active``."""
        ba = sections.get("beliefs_active")
        if not isinstance(ba, dict):
            return
        facts = ba.get("facts")
        if isinstance(facts, list):
            ba["facts"] = [
                f
                for f in facts
                if isinstance(f, dict) and f.get("confidence", 1.0) >= min_confidence
            ]

    @staticmethod
    def _summarize_scoreboard(sections: Dict[str, Any]) -> None:
        """L4: Keep only ``current_qud`` from ``scoreboard``."""
        sb = sections.get("scoreboard")
        if not isinstance(sb, dict):
            return
        current_qud = sb.get("current_qud")
        # Replace full scoreboard with only the current QUD
        sections["scoreboard"] = {"current_qud": current_qud} if current_qud else {}
