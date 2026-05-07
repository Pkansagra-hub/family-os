"""
k1.concierge.experience -- Experience Layer package.

V2 Design Ref: Section 12

Exports all 6 output dataclasses, 6 component stub classes,
and the ExperienceLayer orchestrator.

Component inventory:
  - EmotionalProcessor  -> EmotionalTrajectory  (every 25th turn)
  - AffectiveMirror     -> ToneAdjustment       (chained after EP)
  - NarrativeWeaver     -> NarrativeContext      (every 20th turn)
  - AnticipatoryResponder -> Anticipation        (every 30th turn)
  - ProactiveAgent      -> FillMessage           (COMPANIONING + wait > 5s)
  - RhythmController    -> TimingParams          (every output)
  - ExperienceLayer     -> tick() orchestrator
"""

from k1.concierge.experience.affective_mirror import AffectiveMirror, ToneAdjustment
from k1.concierge.experience.anticipatory_responder import Anticipation, AnticipatoryResponder
from k1.concierge.experience.emotional_processor import EmotionalProcessor, EmotionalTrajectory
from k1.concierge.experience.layer import ExperienceLayer
from k1.concierge.experience.narrative_weaver import NarrativeContext, NarrativeWeaver
from k1.concierge.experience.proactive_agent import FillMessage, ProactiveAgent
from k1.concierge.experience.rhythm_controller import ResponseStyle, RhythmController, TimingParams

__all__ = [
    # Output dataclasses
    "Anticipation",
    "EmotionalTrajectory",
    "FillMessage",
    "NarrativeContext",
    "ResponseStyle",
    "TimingParams",
    "ToneAdjustment",
    # Component stubs
    "AffectiveMirror",
    "AnticipatoryResponder",
    "EmotionalProcessor",
    "NarrativeWeaver",
    "ProactiveAgent",
    "RhythmController",
    # Orchestrator
    "ExperienceLayer",
]
