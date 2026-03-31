"""
Prompt Package -- Mode-Driven Prompt Assembly for Front LLM
=============================================================

V2 Design Ref: Section 16.3 (PromptMode Architecture)

Exports:
  Mode resolution:
    - PromptMode: 10-variant enum for cognitive modes
    - determine_mode: Resolves FSM state + event + SS signals to one mode
    - TOOL_ALLOWLIST: Mode -> tool name list mapping
    - get_tool_allowlist: Conditional tool inclusion per mode
    - MAX_ITERATIONS_TABLE: Mode -> default iteration limit
    - CRISIS_ITERATIONS_TABLE: Mode -> crisis override iteration limit

  Affect computation:
    - AffectBand: Frozen dataclass with band string
    - compute_affect_band: Computes band from affective_now dict
    - AFFECT_TONE_BLOCKS: Band -> prompt tone block text
    - AffectModifiers: Frozen dataclass for per-band overrides
    - compute_affect_modifiers: Resolves band to AffectModifiers
    - AFFECT_MODIFIERS: Band -> AffectModifiers mapping
    - AFFECT_MODE_INTERACTIONS: (mode, band) -> extra prompt block
    - get_affect_mode_interaction: Lookup for (mode, band) pair

  Sections & assembly:
    - PROMPT_SECTIONS: 20 named prompt text blocks
    - MODE_SECTIONS: Mode -> ordered list of PROMPT_SECTIONS keys
    - ANTI_PATTERN_KEYS: Mode -> anti-pattern section key
    - MODE_EXAMPLES: Mode -> in-context example text

  Scenario templates:
    - SCENARIO_DATA_TEMPLATES: Mode -> format-string for scenario data block

  Clarification depth:
    - ClarificationDepthState: Mutable tracker for per-gap depth
    - CLARIFY_DEPTH_BLOCKS: Depth -> prompt injection text
    - get_clarify_depth_block: Returns formatted depth block
    - ClarificationTracker: Multi-gap depth manager

  Domain rules:
    - DOMAIN_RULES: Domain name -> prompt injection text
    - get_domain_rules: Lookup helper returning text or ""
    - DOMAIN_SAFETY_FLOORS: Domain -> minimum safety band
    - DOMAIN_APPLICABLE_MODES: Domain -> applicable mode list or "ALL"
    - get_domain_safety_floor: Returns minimum safety band for domain
    - is_domain_applicable: Checks if domain rules apply to a mode

  Iterations:
    - get_max_iterations: Standalone iteration budget with crisis override

  Builder:
    - BuiltContext: Assembled context for react_loop()
    - DynamicPromptBuilder: Mode-driven prompt assembly
    - SSReadConfig: Per-section read directive
    - SS_READ_CONFIGS: Mode -> SSReadConfig list mapping
"""

from k1.concierge.prompt.affect import (
    AFFECT_MODE_INTERACTIONS,
    AFFECT_MODIFIERS,
    AFFECT_TONE_BLOCKS,
    AffectBand,
    AffectModifiers,
    compute_affect_band,
    compute_affect_modifiers,
    get_affect_mode_interaction,
)
from k1.concierge.prompt.builder import (
    SS_READ_CONFIGS,
    BuiltContext,
    DynamicPromptBuilder,
    SSReadConfig,
    apply_affect_modifiers,
)
from k1.concierge.prompt.clarify_depth import (
    CLARIFY_DEPTH_BLOCKS,
    ClarificationDepthState,
    ClarificationTracker,
    get_clarify_depth_block,
)
from k1.concierge.prompt.domain_rules import (
    DOMAIN_APPLICABLE_MODES,
    DOMAIN_RULES,
    DOMAIN_SAFETY_FLOORS,
    get_domain_rules,
    get_domain_safety_floor,
    is_domain_applicable,
)
from k1.concierge.prompt.mode import (
    CRISIS_ITERATIONS_TABLE,
    MAX_ITERATIONS_TABLE,
    TOOL_ALLOWLIST,
    PromptMode,
    determine_mode,
    get_max_iterations,
    get_tool_allowlist,
)
from k1.concierge.prompt.scenario_templates import SCENARIO_DATA_TEMPLATES
from k1.concierge.prompt.sections import (
    ANTI_PATTERN_KEYS,
    MODE_EXAMPLES,
    MODE_SECTIONS,
    PROMPT_SECTIONS,
)

__all__ = [
    # Mode
    "PromptMode",
    "determine_mode",
    "TOOL_ALLOWLIST",
    "get_tool_allowlist",
    "MAX_ITERATIONS_TABLE",
    "CRISIS_ITERATIONS_TABLE",
    # Affect
    "AffectBand",
    "compute_affect_band",
    "AFFECT_TONE_BLOCKS",
    "AffectModifiers",
    "compute_affect_modifiers",
    "AFFECT_MODIFIERS",
    "AFFECT_MODE_INTERACTIONS",
    "get_affect_mode_interaction",
    # Sections
    "PROMPT_SECTIONS",
    "MODE_SECTIONS",
    "ANTI_PATTERN_KEYS",
    "MODE_EXAMPLES",
    # Scenario templates
    "SCENARIO_DATA_TEMPLATES",
    # Clarification depth
    "ClarificationDepthState",
    "CLARIFY_DEPTH_BLOCKS",
    "get_clarify_depth_block",
    "ClarificationTracker",
    # Domain rules
    "DOMAIN_RULES",
    "get_domain_rules",
    "DOMAIN_SAFETY_FLOORS",
    "DOMAIN_APPLICABLE_MODES",
    "get_domain_safety_floor",
    "is_domain_applicable",
    # Iterations
    "get_max_iterations",
    # Builder
    "BuiltContext",
    "DynamicPromptBuilder",
    "SSReadConfig",
    "SS_READ_CONFIGS",
    "apply_affect_modifiers",
]
