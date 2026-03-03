"""
Memory Writer v2 Configuration -- Centralized config dataclass.

Single config object loaded at MW initialization time.
Immutable after creation -- restart required for changes.

All tunable parameters in one place. Values sourced from:
  - policies.contract.yaml (authoritative budgets and limits)
  - stage5_proposal_corrections.md (design decisions)
  - memory_writer_architecture.md (MW-01 through MW-11)

Source priority: env vars > config file > defaults below.

Import graph: k1.memory_writer.config imports from stdlib only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

# SessionState sections read by MW (13 of 15)
_DEFAULT_HOT_SECTIONS: List[str] = [
    "beliefs_active",
    "beliefs_history",
    "history_active",
    "history_recent",
    "affective_now",
    "affective_baseline",
    "narrative_active",
    "scoreboard",
    "control",
    "persona",
]

_DEFAULT_WARM_SECTIONS: List[str] = [
    "task_state",
    "ifl",
    "meta",
]

# Sections MW never reads (not relevant for memory extraction)
_SKIPPED_SECTIONS: List[str] = [
    "telemetry",
    "artifacts_warm",
]


@dataclass(frozen=True)
class MWConfig:
    """Centralized Memory Writer v2 configuration.

    Loaded once at MW initialization time.
    Immutable after creation -- restart required for changes.

    Organized into logical groups:
      1. LLM Extraction
      2. Atom Validation
      3. Batch Configuration
      4. Filter Configuration
      5. Circuit Breaker
      6. SessionState Sections
      7. Model Hub Routing
    """

    # --- 1. LLM Extraction (MW-06) ---
    llm_token_budget: int = 2000

    # --- 2. Atom Validation (MW-04, MW-05) ---
    max_atoms_per_turn: int = 6
    max_text_words: int = 50
    confidence_floor: float = 0.30

    # --- 3. Batch Configuration (MW-08) ---
    batch_window_ms: int = 250
    max_batch_size: int = 10

    # --- 4. Filter Configuration (MW-07: rule-based only) ---
    filter_dedup_window_seconds: int = 300
    filter_trivial_word_threshold: int = 5

    # --- 5. Circuit Breaker (IModelHubPort protection) ---
    circuit_breaker_failure_threshold: int = 3
    circuit_breaker_recovery_probe_seconds: int = 30

    # --- 6. SessionState Sections (MW-01: read-only, MW-02: <1ms) ---
    session_sections_hot: List[str] = field(default_factory=lambda: list(_DEFAULT_HOT_SECTIONS))
    session_sections_warm: List[str] = field(default_factory=lambda: list(_DEFAULT_WARM_SECTIONS))

    # --- 7. Model Hub Routing ---
    model_hint: str = "cheapest"

    @property
    def all_sections(self) -> List[str]:
        """Return all sections MW reads (hot + warm). 13 total."""
        return self.session_sections_hot + self.session_sections_warm
