"""
M22 DreamExplorer Module — Dream-Like Exploration for R5.

This module implements the R5 dream-like exploration algorithms that run
during consolidation cycles. It generates counterfactuals, forward simulations,
insights, and prospective memories.

References:
- M8_EXECUTION.md Issue 8.1.3: M22 DreamExplorer scaffold
- Dossier §4.6: R5 — Dream-Like Exploration (REM)
- Dossier §7.4.5: M22 — DreamExplorer

Module Layout:
    config.py        - DreamConfig dataclass
    models.py        - Insight, CounterfactualScenario, ProspectiveMemory
    dream_explorer.py - M22 DreamExplorer orchestrator class
    intent_signals.py - IntentSignal models for GAP-001
"""

from k0.modules.consolidation.dream.config import DreamConfig

# DreamExplorer must be imported after intent_signals to break cycle
from k0.modules.consolidation.dream.dream_explorer import DreamExplorer

# Import intent_signals BEFORE dream_explorer to avoid circular import
# dream_explorer imports intent_signal_detector which imports intent_signals
from k0.modules.consolidation.dream.intent_signals import (
    DecisionSignal,
    EmotionalSignal,
    IntentSignal,
    IntentSignalType,
    LessonSignal,
    MilestoneSignal,
    MilestoneType,
    QueryBoostSignal,
    ReminderSignal,
)
from k0.modules.consolidation.dream.models import (
    CounterfactualScenario,
    DreamExplorerInput,
    DreamExplorerOutput,
    Insight,
    InsightType,
    ProspectiveMemory,
    RoutineOptimization,
    ScenarioType,
)

__all__ = [
    # Config
    "DreamConfig",
    # Models
    "Insight",
    "InsightType",
    "CounterfactualScenario",
    "ScenarioType",
    "RoutineOptimization",
    "ProspectiveMemory",
    "DreamExplorerInput",
    "DreamExplorerOutput",
    # Intent Signals (GAP-001)
    "IntentSignal",
    "IntentSignalType",
    "ReminderSignal",
    "DecisionSignal",
    "LessonSignal",
    "EmotionalSignal",
    "MilestoneSignal",
    "MilestoneType",
    "QueryBoostSignal",
    # Main class
    "DreamExplorer",
]
