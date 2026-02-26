"""
poc.k1_poc.prompt.builder -- DynamicPromptBuilder and BuiltContext.

Mode-driven prompt assembly for Front LLM. Replaces the monolithic
prompt approach with mode-specific tool selection, SS read configs,
iteration limits, and affect modulation.

V2 Design Ref: Section 16.3 (PromptMode Architecture)

The DynamicPromptBuilder.build() method produces a BuiltContext containing
everything react_loop() needs for one Front LLM invocation:
    - system_prompt: assembled prompt text
    - messages: chat history as ModelMessage list
    - tools: filtered ToolSchema list per mode
    - max_iterations: mode + affect adjusted
    - mode: resolved PromptMode (for observability)
    - affect_band: computed band string
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Literal

from poc.k1_poc.llm.types import ModelMessage, ToolSchema

logger = logging.getLogger(__name__)
from poc.k1_poc.config import get_config
from poc.k1_poc.prompt.affect import (
    AFFECT_TONE_BLOCKS,
    AffectBand,
    AffectModifiers,
    compute_affect_modifiers,
    get_affect_mode_interaction,
)
from poc.k1_poc.prompt.clarify_depth import CLARIFY_DEPTH_BLOCKS
from poc.k1_poc.prompt.domain_rules import get_domain_rules, is_domain_applicable
from poc.k1_poc.prompt.mode import (
    CRISIS_ITERATIONS_TABLE,
    MAX_ITERATIONS_TABLE,
    PromptMode,
    get_tool_allowlist,
)
from poc.k1_poc.prompt.scenario_templates import SCENARIO_DATA_TEMPLATES
from poc.k1_poc.prompt.sections import (
    ANTI_PATTERN_KEYS,
    MODE_EXAMPLES,
    MODE_SECTIONS,
    PROMPT_SECTIONS,
)

# =========================================================================
# SSReadConfig -- per-section read directive
# =========================================================================


@dataclass(frozen=True)
class SSReadConfig:
    """Specifies how to read one SS section for a given mode.

    Attributes:
        section: SS section name (e.g. "beliefs_active", "control")
        read_mode: "full" | "slim" | "skip"
        history_window: Only meaningful for "history_active" section
    """

    section: str
    read_mode: Literal["full", "slim", "skip"]
    history_window: int = 20


# =========================================================================
# SS Read Configs per mode (V2 Section 16.3)
# =========================================================================

SS_READ_CONFIGS: dict[PromptMode, list[SSReadConfig]] = {
    PromptMode.STANDARD: [
        SSReadConfig("beliefs_active", "full"),
        SSReadConfig("scoreboard", "full"),
        SSReadConfig("affective_now", "full"),
        SSReadConfig("clarifications", "full"),
        SSReadConfig("narrative_active", "full"),
        SSReadConfig("control", "full"),
        SSReadConfig("history_active", "full", history_window=20),
        SSReadConfig("persona", "full"),
        SSReadConfig("task_state", "full"),
        SSReadConfig("task_artifacts", "full"),
    ],
    PromptMode.CLARIFY_ASK: [
        SSReadConfig("beliefs_active", "slim"),
        SSReadConfig("scoreboard", "slim"),
        SSReadConfig("affective_now", "full"),
        SSReadConfig("clarifications", "full"),
        SSReadConfig("control", "slim"),
        SSReadConfig("history_active", "full", history_window=10),
        SSReadConfig("persona", "full"),
    ],
    PromptMode.CLARIFY_RESOLVE: [
        SSReadConfig("beliefs_active", "full"),
        SSReadConfig("scoreboard", "full"),
        SSReadConfig("affective_now", "full"),
        SSReadConfig("clarifications", "full"),
        SSReadConfig("control", "slim"),
        SSReadConfig("history_active", "full", history_window=15),
        SSReadConfig("persona", "full"),
        SSReadConfig("task_state", "slim"),
    ],
    PromptMode.HITL_RELAY: [
        SSReadConfig("affective_now", "full"),
        SSReadConfig("control", "slim"),
        SSReadConfig("persona", "full"),
        SSReadConfig("task_state", "full"),
    ],
    PromptMode.HITL_RESOLVE: [
        SSReadConfig("beliefs_active", "slim"),
        SSReadConfig("scoreboard", "slim"),
        SSReadConfig("affective_now", "full"),
        SSReadConfig("control", "slim"),
        SSReadConfig("history_active", "full", history_window=5),
        SSReadConfig("persona", "full"),
        SSReadConfig("task_state", "full"),
    ],
    PromptMode.PRESENT: [
        SSReadConfig("affective_now", "full"),
        SSReadConfig("narrative_active", "slim"),
        SSReadConfig("control", "slim"),
        SSReadConfig("history_active", "full", history_window=10),
        SSReadConfig("persona", "full"),
        SSReadConfig("task_state", "full"),
        SSReadConfig("task_artifacts", "full"),
        SSReadConfig("beliefs_active", "slim"),
    ],
    PromptMode.WEAVE: [
        SSReadConfig("affective_now", "full"),
        SSReadConfig("narrative_active", "full"),
        SSReadConfig("control", "slim"),
        SSReadConfig("history_active", "full", history_window=10),
        SSReadConfig("persona", "full"),
        SSReadConfig("task_state", "full"),
        SSReadConfig("task_artifacts", "full"),
        SSReadConfig("beliefs_active", "slim"),
    ],
    PromptMode.CANCEL: [
        SSReadConfig("beliefs_active", "slim"),
        SSReadConfig("affective_now", "full"),
        SSReadConfig("narrative_active", "slim"),
        SSReadConfig("control", "slim"),
        SSReadConfig("history_active", "full", history_window=5),
        SSReadConfig("persona", "full"),
        SSReadConfig("task_state", "full"),
    ],
    PromptMode.INTERRUPT: [
        SSReadConfig("beliefs_active", "full"),
        SSReadConfig("scoreboard", "full"),
        SSReadConfig("affective_now", "full"),
        SSReadConfig("clarifications", "full"),
        SSReadConfig("narrative_active", "full"),
        SSReadConfig("control", "full"),
        SSReadConfig("history_active", "full", history_window=20),
        SSReadConfig("persona", "full"),
        SSReadConfig("task_state", "full"),
        SSReadConfig("task_artifacts", "full"),
    ],
    PromptMode.ERROR: [
        SSReadConfig("affective_now", "full"),
        SSReadConfig("narrative_active", "slim"),
        SSReadConfig("control", "slim"),
        SSReadConfig("history_active", "full", history_window=5),
        SSReadConfig("persona", "full"),
        SSReadConfig("task_state", "full"),
        SSReadConfig("task_artifacts", "slim"),
    ],
}


# =========================================================================
# BuiltContext -- output of DynamicPromptBuilder.build()
# =========================================================================


@dataclass
class BuiltContext:
    """Complete assembled context for a single Front LLM invocation.

    Returned by DynamicPromptBuilder.build(). Consumed by react_loop().

    Attributes:
        system_prompt: Assembled prompt text (sections + examples + affect
            tone + depth + domain rules + anti-pattern + scenario data)
        messages: Chat history + current input as ModelMessage list
        tools: Filtered ToolSchema list for this mode
        max_iterations: From MAX_ITERATIONS_TABLE, with crisis override
        mode: The resolved PromptMode (for observability/logging)
        affect_band: Computed band string
        estimated_tokens: Approximate token count for system_prompt
    """

    system_prompt: str
    messages: list[ModelMessage] = field(default_factory=list)
    tools: list[ToolSchema] = field(default_factory=list)
    max_iterations: int = 6
    mode: PromptMode = PromptMode.STANDARD
    affect_band: str = "neutral"
    estimated_tokens: int = 0


# =========================================================================
# apply_affect_modifiers -- standalone helper
# =========================================================================


def apply_affect_modifiers(
    modifiers: AffectModifiers,
    base_max_iterations: int,
    prompt_parts: list[str],
    tools: list[ToolSchema] | None = None,
) -> tuple[int, list[ToolSchema]]:
    """Apply affect-band modifiers to builder intermediates.

    Adjusts max_iterations by delta, filters tools (removes refine_affect
    when skip_refine_affect is True), and injects response_length_hint
    into the prompt parts list.

    Called by DynamicPromptBuilder.build() after base assembly stages.

    Args:
        modifiers: AffectModifiers from compute_affect_modifiers().
        base_max_iterations: Base iteration count from _get_max_iterations().
        prompt_parts: Mutable list of prompt sections. response_length_hint
            is appended in-place if non-empty.
        tools: Tool schemas list. refine_affect is removed if
            skip_refine_affect is True. None treated as empty list.

    Returns:
        Tuple of (adjusted_max_iterations, filtered_tools).
    """
    # 1. Adjust max_iterations by delta (minimum 1)
    adjusted_iterations = max(1, base_max_iterations + modifiers.max_iterations_delta)

    # 2. Inject response_length_hint into prompt
    if modifiers.response_length_hint:
        prompt_parts.append(f"== RESPONSE LENGTH ==\n{modifiers.response_length_hint}")

    # 3. Filter tools: remove refine_affect if skip_refine_affect
    adjusted_tools = list(tools) if tools else []
    if modifiers.skip_refine_affect:
        adjusted_tools = [t for t in adjusted_tools if t.name != "refine_affect"]

    return adjusted_iterations, adjusted_tools


# =========================================================================
# DynamicPromptBuilder
# =========================================================================


class DynamicPromptBuilder:
    """Mode-driven prompt assembly for Front LLM.

    V2 Design Doc Section 6.1: 9-stage assembly pipeline + affect modifiers.

    Assembly pipeline:
      1. Select prompt sections from MODE_SECTIONS[mode]
      2. Append mode-specific example from MODE_EXAMPLES[mode]
      3. Append affect tone modifier from AFFECT_TONE_BLOCKS[band]
      3b. Append affect x mode interaction block (if exists)
      4. Append clarification depth block (CLARIFY_ASK only)
      5. Append domain rules from DOMAIN_RULES[domain]
      6. Append anti-pattern subset from ANTI_PATTERN_KEYS[mode]
      7. Format and append scenario data from SCENARIO_DATA_TEMPLATES[mode]
      8. Read SS sections per SS_READ_CONFIGS[mode] (placeholder for SS)
      9. Apply affect modifiers + pre-call budget check

    After assembly:
      - Interpolate {max_iterations} placeholder
      - Filter tools by mode allowlist (with conditional inclusion)
      - Apply affect modifier tool filtering (remove refine_affect)
      - Build chat history with mode-appropriate window
    """

    # Gemini 2.5 Pro context window (V2 Section 26.9)
    CONTEXT_WINDOW = 128_000
    SAFETY_MARGIN = 0.80
    MAX_CONTEXT_TOKENS = int(CONTEXT_WINDOW * SAFETY_MARGIN)  # 102,400

    # Token estimation: ~4 chars per token (rough approximation)
    CHARS_PER_TOKEN = 4

    @property
    def _context_window(self) -> int:
        return get_config().prompt.context_window

    @property
    def _safety_margin(self) -> float:
        return get_config().prompt.safety_margin

    @property
    def _max_context_tokens(self) -> int:
        return int(self._context_window * self._safety_margin)

    @property
    def _chars_per_token(self) -> int:
        return get_config().prompt.chars_per_token

    def build(
        self,
        mode: PromptMode,
        affect_band: AffectBand,
        history_messages: list[ModelMessage] | None = None,
        all_tool_schemas: list[ToolSchema] | None = None,
        scenario_data: dict[str, Any] | None = None,
        clarify_depth: int = 0,
        domain: str | None = None,
        affect_confidence: float = 1.0,
        tier: str = "LOW",
    ) -> BuiltContext:
        """Assemble complete context for one Front LLM invocation.

        V2 Design Doc Section 6.1: 9-stage pipeline.

        Args:
            mode: Resolved PromptMode from determine_mode().
            affect_band: Computed AffectBand from compute_affect_band().
            history_messages: Pre-built chat history from build_chat_history().
            all_tool_schemas: Full FRONT_TOOL_SCHEMAS list to filter from.
            scenario_data: Mode-specific data dict for prompt injection.
            clarify_depth: Clarification re-ask depth (0=first, 1=re-ask, 2=final).
            domain: Optional domain string from Phase 1 classification.
            affect_confidence: Phase 1 affect confidence for conditional tools.
            tier: Task complexity tier for conditional tool inclusion.

        Returns:
            BuiltContext with everything react_loop() needs.
        """
        messages = list(history_messages) if history_messages else []
        all_schemas = all_tool_schemas or []

        logger.info(
            "DynamicPromptBuilder.build START  mode=%s affect=%s domain=%s tier=%s depth=%d",
            mode.value,
            affect_band.band,
            domain,
            tier,
            clarify_depth,
        )

        prompt_parts: list[str] = []

        # Stage 1: Select and concatenate prompt sections from MODE_SECTIONS
        section_keys = MODE_SECTIONS.get(mode, [])
        for key in section_keys:
            section_text = PROMPT_SECTIONS.get(key, "")
            if section_text:
                prompt_parts.append(section_text)
        logger.debug(
            "  Stage 1  sections=%d keys=%s",
            len(section_keys),
            section_keys,
        )

        # Stage 2: Append mode-specific example from MODE_EXAMPLES
        example_text = MODE_EXAMPLES.get(mode, "")
        if example_text:
            prompt_parts.append(example_text)
            logger.debug("  Stage 2  example appended (len=%d)", len(example_text))

        # Stage 3: Append affect tone modifier (skip neutral -- empty string)
        tone_block = AFFECT_TONE_BLOCKS.get(affect_band.band, "")
        if tone_block:
            prompt_parts.append(tone_block)

        # Stage 3b: Append affect x mode interaction block
        interaction_block = get_affect_mode_interaction(mode.name, affect_band.band)
        if interaction_block:
            prompt_parts.append(interaction_block)
            logger.debug("  Stage 3b  affect x mode interaction appended")

        # Stage 4: Append clarification depth block (CLARIFY_ASK only)
        if mode == PromptMode.CLARIFY_ASK and clarify_depth in CLARIFY_DEPTH_BLOCKS:
            depth_block = CLARIFY_DEPTH_BLOCKS[clarify_depth]
            # Format placeholders if scenario_data provides them
            if scenario_data and "{" in depth_block:
                try:
                    depth_block = depth_block.format(
                        field=scenario_data.get("gap_field", ""),
                        previous_question=scenario_data.get("previous_question", ""),
                    )
                except KeyError:
                    pass  # Use raw template if formatting fails
            prompt_parts.append(depth_block)

        # Stage 5: Append domain rules (only for applicable modes)
        # RC-3 fix: consult is_domain_applicable() to avoid leaking
        # domain rules into modes where they are irrelevant.
        if domain and is_domain_applicable(domain, mode.value):
            domain_block = get_domain_rules(domain)
            if domain_block:
                prompt_parts.append(domain_block)

        # Stage 6: Append anti-pattern subset
        if mode in ANTI_PATTERN_KEYS:
            ap_key = ANTI_PATTERN_KEYS[mode]
            ap_text = PROMPT_SECTIONS.get(ap_key, "")
            if ap_text:
                prompt_parts.append(ap_text)

        # Stage 7: Format and append scenario data from template
        if scenario_data:
            scenario_block = self._format_scenario_data(mode, scenario_data)
            if scenario_block:
                prompt_parts.append(scenario_block)

        # Stage 8: SS sections placeholder -- caller provides via history_messages
        # Full SS read is handled by front_handler via SS_READ_CONFIGS

        # Stage 9: Apply affect modifiers + pre-call budget check
        base_max_iter = self._get_max_iterations(mode, affect_band)
        modifiers = compute_affect_modifiers(affect_band)
        max_iter, _ = apply_affect_modifiers(modifiers, base_max_iter, prompt_parts)
        logger.debug(
            "  Stage 9  base_iter=%d adjusted_iter=%d skip_refine=%s",
            base_max_iter,
            max_iter,
            modifiers.skip_refine_affect,
        )

        # Assemble and interpolate placeholders
        system_prompt = "\n\n".join(part for part in prompt_parts if part)
        system_prompt = system_prompt.replace("{max_iterations}", str(max_iter))

        # RC-1 fix: interpolate {open_gaps_list} from scenario_data
        # STATE_INTERP_CLARIFY contains this placeholder; without
        # interpolation the raw string leaks into the LLM prompt.
        if "{open_gaps_list}" in system_prompt:
            gaps_value = (scenario_data or {}).get("open_gaps_list", "(none provided)")
            system_prompt = system_prompt.replace("{open_gaps_list}", str(gaps_value))

        # Filter tools by mode allowlist (with conditional inclusion)
        tools = self._select_tools(mode, all_schemas, affect_confidence, tier)

        # Apply affect modifier tool filtering
        if modifiers.skip_refine_affect:
            tools = [t for t in tools if t.name != "refine_affect"]

        # Estimate tokens and compress if needed
        estimated_tokens = self._estimate_tokens(system_prompt)
        if estimated_tokens > self._max_context_tokens:
            logger.warning(
                "  Prompt exceeds budget  tokens=%d max=%d -- compressing",
                estimated_tokens,
                self.MAX_CONTEXT_TOKENS,
            )
            system_prompt = self._compress_prompt(system_prompt)
            estimated_tokens = self._estimate_tokens(system_prompt)

        logger.info(
            "DynamicPromptBuilder.build DONE  mode=%s tools=%d max_iter=%d tokens=%d affect=%s",
            mode.value,
            len(tools),
            max_iter,
            estimated_tokens,
            affect_band.band,
        )

        return BuiltContext(
            system_prompt=system_prompt,
            messages=messages,
            tools=tools,
            max_iterations=max_iter,
            mode=mode,
            affect_band=affect_band.band,
            estimated_tokens=estimated_tokens,
        )

    def _get_max_iterations(self, mode: PromptMode, affect_band: AffectBand) -> int:
        """Get iteration limit with crisis override."""
        if affect_band.band == "crisis":
            return CRISIS_ITERATIONS_TABLE[mode]
        return MAX_ITERATIONS_TABLE[mode]

    def _select_tools(
        self,
        mode: PromptMode,
        all_schemas: list[ToolSchema],
        affect_confidence: float = 1.0,
        tier: str = "LOW",
    ) -> list[ToolSchema]:
        """Filter tool schemas by mode allowlist with conditional inclusion."""
        allowed_names = get_tool_allowlist(mode, affect_confidence, tier)
        return [t for t in all_schemas if t.name in allowed_names]

    def _format_scenario_data(self, mode: PromptMode, data: dict[str, Any]) -> str:
        """Format scenario data using SCENARIO_DATA_TEMPLATES.

        Uses the mode's template from SCENARIO_DATA_TEMPLATES and fills
        {placeholders} from the data dict. Falls back to key/value
        listing if template is empty or formatting fails.
        """
        if not data:
            return ""

        template = SCENARIO_DATA_TEMPLATES.get(mode, "")
        if template:
            try:
                return template.format(**data)
            except KeyError:
                # Missing placeholder -- fall through to key/value listing
                pass

        # Fallback: key/value listing for modes without templates
        lines = [f"== SCENARIO: {mode.value.upper()} =="]
        for key, value in data.items():
            if isinstance(value, list):
                lines.append(f"  {key}: {', '.join(str(v) for v in value)}")
            else:
                lines.append(f"  {key}: {value}")
        return "\n".join(lines)

    def _estimate_tokens(self, text: str) -> int:
        """Rough token estimate: len(text) / CHARS_PER_TOKEN.

        Fast heuristic for budget checking, not a precise tokenizer.
        Sufficient for pre-call compression decisions.
        """
        return len(text) // self._chars_per_token

    def _compress_prompt(self, prompt: str) -> str:
        """Compress prompt to fit within token budget.

        Compression strategy (V2 Section 26.9):
          1. Truncate from the end (SS sections/scenario data are last,
             lowest priority).
          2. Mark truncation point.

        This is a LAST RESORT. Normal mode-driven assembly should stay
        within budget. If compression is triggered, it indicates an
        unusually large SS state or prompt section set.
        """
        target_chars = self._max_context_tokens * self._chars_per_token
        if len(prompt) <= target_chars:
            return prompt
        return prompt[:target_chars] + "\n\n[Context truncated for budget]"

    def _get_history_window(self, mode: PromptMode) -> int:
        """Get history window for a mode from SS_READ_CONFIGS.

        Returns the history_window configured for history_active in
        the mode's SS_READ_CONFIGS, or 0 if history_active is skipped.
        """
        configs = SS_READ_CONFIGS.get(mode, [])
        return next(
            (c.history_window for c in configs if c.section == "history_active"),
            0,
        )
