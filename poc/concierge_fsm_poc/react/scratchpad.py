"""Scratchpad, Finding, and LoopBudget models -- Epic 3.1 (PAD-001).

Adapted from ``poc/react_scratchpad_poc/core/models.py``.  Stripped of
benchmark-specific fields (TurnRecord, RunResult, Checkpoint, Scenario,
IterationSnapshot) and tailored for the Concierge FSM PoC.

Key additions vs the original PoC:

* ``Scratchpad.fsm_state`` -- current FSM state, so the ReAct loop
  always knows which phase the Concierge is in.
* ``COGNITIVE_TOOLS`` frozenset -- the 7 signal + cognitive tool names
  whose outputs are SessionState writes (not findings).
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from poc.concierge_fsm_poc.fsm.controller import State

# ---------------------------------------------------------------------------
# COGNITIVE_TOOLS -- tools that write to SessionState directly.
# Their outputs are confirmations ({success: true, ...}), NOT raw data.
# The ReAct loop must NOT extract findings from these -- the data is
# already in SessionState sections.
# ---------------------------------------------------------------------------

COGNITIVE_TOOLS: frozenset[str] = frozenset(
    {
        "update_beliefs",
        "update_scoreboard",
        "update_clarifications",
        "update_narrative",
        "refine_affect",
        "promote_belief",
    }
)

# ---------------------------------------------------------------------------
# Tier enum (LOCAL -- avoids circular import with registry)
# ---------------------------------------------------------------------------


class Tier(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


# ---------------------------------------------------------------------------
# LoopBudget
# ---------------------------------------------------------------------------


@dataclass
class LoopBudget:
    """Tiered resource budget for a ReAct loop execution.

    Prevents runaway loops by capping tool calls, iterations, time,
    and token output.  ``for_tier()`` returns sensible defaults.

    Limits are set very high to avoid premature budget exhaustion
    during real LLM calls (Gemini API latency ~8-21s per call).
    """

    max_tools: int = 200
    max_iterations: int = 200
    timeout_ms: int = 600_000
    max_context_tokens: int = 128_000
    max_tokens_out: int = 32_000

    # Mutable counters
    tools_used: int = 0
    iterations_used: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    elapsed_ms: int = 0

    @classmethod
    def for_tier(cls, tier: Tier) -> LoopBudget:
        """Factory with per-tier defaults.

        Limits are sized for real Gemini API latency (~8-21s per call).
        Keep them tight to prevent runaway loops and ensure the budget-
        exhausted fallback (which builds a findings-based response)
        fires before the user gives up.
        """
        presets: dict[Tier, dict[str, int]] = {
            Tier.LOW: dict(
                max_tools=5, max_iterations=3, timeout_ms=45_000, max_tokens_out=16_000
            ),
            Tier.MEDIUM: dict(
                max_tools=15,
                max_iterations=6,
                timeout_ms=120_000,
                max_tokens_out=32_000,
            ),
            Tier.HIGH: dict(
                max_tools=30,
                max_iterations=10,
                timeout_ms=300_000,
                max_tokens_out=64_000,
            ),
        }
        return cls(**presets[tier])

    @property
    def exhausted(self) -> bool:
        """True when any hard limit is hit."""
        return (
            self.tools_used >= self.max_tools
            or self.iterations_used >= self.max_iterations
            or self.elapsed_ms >= self.timeout_ms
        )

    @property
    def remaining_tools(self) -> int:
        return max(0, self.max_tools - self.tools_used)

    @property
    def remaining_iterations(self) -> int:
        return max(0, self.max_iterations - self.iterations_used)

    def consume_tool(self) -> None:
        self.tools_used += 1

    def consume_iteration(self) -> None:
        self.iterations_used += 1

    def add_tokens(self, tokens_in: int, tokens_out: int) -> None:
        self.tokens_in += tokens_in
        self.tokens_out += tokens_out


# ---------------------------------------------------------------------------
# Finding
# ---------------------------------------------------------------------------


@dataclass
class Finding:
    """A structured fact extracted from a tool result.

    Findings survive message compaction -- they live in a dict
    keyed by ``key`` and are injected into the KNOWN FACTS section
    of every LLM context window.
    """

    key: str
    value: Any
    type: str = "fact"  # weather, flight, fact, calculation, error, ...
    confidence: float = 1.0
    source_iteration: int = 0
    source_tool: str = ""


# ---------------------------------------------------------------------------
# ToolEntry -- lightweight tool-call history row
# ---------------------------------------------------------------------------


@dataclass
class ToolEntry:
    """One row in the scratchpad tool-call history."""

    iteration: int
    tool_name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    ok: bool = True
    summary: str = ""


# ---------------------------------------------------------------------------
# Scratchpad
# ---------------------------------------------------------------------------


@dataclass
class Scratchpad:
    """Ephemeral working memory for a single ReAct loop execution.

    Unlike naive message passing (append everything), the scratchpad:

    * Extracts structured **findings** from tool results.
    * Tracks a lightweight **tool_history** instead of full messages.
    * Supports token-based **compaction** (threshold = 0.8 of 128K).
    * Carries the current **fsm_state** so the loop is FSM-aware.
    * Tracks budget to prevent runaway loops.

    Created at loop start, destroyed at loop end.  Never persisted.
    """

    # -- Identity ----------------------------------------------------------
    turn_id: str = field(default_factory=lambda: f"turn-{uuid.uuid4().hex[:8]}")

    # -- FSM awareness (NEW vs original PoC) -------------------------------
    fsm_state: State = State.LISTENING

    # -- Context -----------------------------------------------------------
    system_prompt: str = ""
    user_query: str = ""
    tier: Tier = Tier.MEDIUM

    # -- Structured findings (the core innovation) -------------------------
    findings: dict[str, Finding] = field(default_factory=dict)

    # -- Tool-call history (lightweight, no raw payloads) -------------------
    tool_history: list[ToolEntry] = field(default_factory=list)

    # -- Budget ------------------------------------------------------------
    budget: LoopBudget = field(default_factory=LoopBudget)

    # -- Loop state --------------------------------------------------------
    iteration: int = 0
    started_at_ns: int = field(default_factory=time.time_ns)

    # -- Thought tracking --------------------------------------------------
    thoughts: list[tuple[int, str]] = field(default_factory=list)

    # -- Compaction config -------------------------------------------------
    compaction_token_ratio: float = 0.8
    _compaction_summaries: list[str] = field(default_factory=list)

    # ------------------------------------------------------------------ #
    # Findings
    # ------------------------------------------------------------------ #

    def add_finding(self, finding: Finding) -> None:
        """Add a structured finding, deduplicating by normalized key and value.

        Deduplication layers:
        1. Exact key+value match -> skip silently.
        2. Normalized key match (strip common prefixes, lowercase) with
           same value -> skip (semantic duplicate).
        3. Key collision with different value -> namespace as key_2, key_3...
        """
        finding.source_iteration = self.iteration
        key = finding.key

        # --- Layer 1: exact key + value match ---
        if key in self.findings:
            existing = self.findings[key]
            if str(existing.value) == str(finding.value):
                return  # exact duplicate

        # --- Layer 2: normalized-key semantic dedup ---
        norm_key = self._normalize_finding_key(key)
        norm_val = str(finding.value).strip().lower()
        for existing_key, existing_finding in self.findings.items():
            if self._normalize_finding_key(existing_key) == norm_key:
                if str(existing_finding.value).strip().lower() == norm_val:
                    return  # semantic duplicate (same fact, different key spelling)

        # --- Layer 3: key collision with different value -> namespace ---
        if key in self.findings:
            n = 2
            while f"{key}_{n}" in self.findings:
                n += 1
            finding.key = f"{key}_{n}"

        self.findings[finding.key] = finding

    @staticmethod
    def _normalize_finding_key(key: str) -> str:
        """Normalize a finding key for semantic dedup comparison.

        Strips common verbose prefixes that the LLM adds, lowercases,
        and sorts tokens so 'hotel_rate_hyatt' matches 'hyatt_hotel_rate'.
        """
        k = key.lower().strip()
        # Remove common prefixes the LLM attaches
        for prefix in (
            "result_",
            "data_",
            "info_",
            "detail_",
            "details_",
            "finding_",
            "fact_",
        ):
            if k.startswith(prefix):
                k = k[len(prefix) :]
        # Sort tokens so word order doesn't matter
        tokens = sorted(k.split("_"))
        return "_".join(tokens)

    def add_findings(self, findings: list[Finding]) -> None:
        for f in findings:
            self.add_finding(f)

    def findings_summary(self) -> str:
        """Format all findings as a concise fact sheet for the LLM."""
        if not self.findings:
            return ""
        by_type: dict[str, list[Finding]] = {}
        for f in self.findings.values():
            by_type.setdefault(f.type, []).append(f)

        lines: list[str] = []
        for ftype, facts in sorted(by_type.items()):
            lines.append(f"### {ftype.upper()}")
            for f in facts:
                conf = f" (confidence: {f.confidence:.0%})" if f.confidence < 1.0 else ""
                lines.append(f"- {f.key}: {f.value}{conf}")
        return "\n".join(lines)

    # ------------------------------------------------------------------ #
    # Tool history
    # ------------------------------------------------------------------ #

    def record_tool_call(
        self,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
        ok: bool = True,
        summary: str = "",
    ) -> None:
        """Append a lightweight record and consume a budget tool call."""
        self.tool_history.append(
            ToolEntry(
                iteration=self.iteration,
                tool_name=tool_name,
                arguments=arguments or {},
                ok=ok,
                summary=summary,
            )
        )
        self.budget.consume_tool()

    # ------------------------------------------------------------------ #
    # Compaction
    # ------------------------------------------------------------------ #

    def needs_compaction(self) -> bool:
        """True when estimated context tokens exceed the compaction threshold.

        Token estimate: 4 chars per token (standard heuristic).
        Threshold: ``compaction_token_ratio`` * ``budget.max_context_tokens``
        (default 0.8 * 128K = 102,400 tokens).
        """
        total_chars = len(self.system_prompt) + len(self.user_query)
        total_chars += sum(len(e.summary) for e in self.tool_history)
        total_chars += len(self.findings_summary())
        total_chars += sum(len(s) for s in self._compaction_summaries)

        token_estimate = total_chars // 4
        threshold = int(self.budget.max_context_tokens * self.compaction_token_ratio)
        return token_estimate > threshold

    def add_compaction_summary(self, summary: str) -> None:
        """Store a compacted summary produced by the LLM summarizer."""
        self._compaction_summaries.append(summary)

    # ------------------------------------------------------------------ #
    # Thought tracking
    # ------------------------------------------------------------------ #

    def record_thought(self, text: str, iteration: int | None = None) -> None:
        """Record the LLM's reasoning text emitted before tool calls.

        Thoughts are the text that accompanies function-call responses.
        They reveal the model's reasoning chain for debugging.
        """
        it = iteration if iteration is not None else self.iteration
        self.thoughts.append((it, text))

    @property
    def compaction_count(self) -> int:
        return len(self._compaction_summaries)

    # ------------------------------------------------------------------ #
    # State helpers
    # ------------------------------------------------------------------ #

    @property
    def is_complete(self) -> bool:
        """Loop should terminate when budget is exhausted."""
        return self.budget.exhausted

    def elapsed_ms(self) -> int:
        return (time.time_ns() - self.started_at_ns) // 1_000_000

    def estimated_context_tokens(self) -> int:
        """Rough char/4 estimate of the current context window size."""
        total_chars = len(self.system_prompt) + len(self.user_query)
        total_chars += sum(len(e.summary) for e in self.tool_history)
        total_chars += len(self.findings_summary())
        total_chars += sum(len(s) for s in self._compaction_summaries)
        return total_chars // 4
