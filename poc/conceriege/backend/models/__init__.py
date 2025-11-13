"""
Data Models for Concierge PoC

This module contains all dataclass models for type safety and serialization.
These models are based on the design rationale, flow, and envelope design documents.

Research basis:
- Conversational Grounding (Clark 1991) - QUD, scoreboard, referents
- Mixed-Initiative Dialogue (Allen 1999) - Intent classification
- Reactive-Proactive Loop (Novel pattern) - ProactivePrompt
- Actor Model (Hewitt 1973) - Cognitive Envelope
"""

from .analysis_result import AnalysisResult, Insight
from .conversation_state import ConversationState, Referent, Scoreboard, Turn
from .envelope import CognitiveEnvelope, EnvelopeFactory, EnvelopeValidator
from .intent import Intent
from .proactive_prompt import ProactivePrompt
from .progress_event import ProgressEvent

__all__ = [
    "Intent",
    "ConversationState",
    "Scoreboard",
    "Referent",
    "Turn",
    "ProactivePrompt",
    "AnalysisResult",
    "Insight",
    "ProgressEvent",
    "CognitiveEnvelope",
    "EnvelopeFactory",
    "EnvelopeValidator",
]
