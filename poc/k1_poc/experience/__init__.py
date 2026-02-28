"""
poc.k1_poc.experience -- Experience Layer package.

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

from poc.k1_poc.experience.affective_mirror import AffectiveMirror, ToneAdjustment
from poc.k1_poc.experience.anticipatory_responder import Anticipation, AnticipatoryResponder
from poc.k1_poc.experience.emotional_processor import EmotionalProcessor, EmotionalTrajectory
from poc.k1_poc.experience.layer import ExperienceLayer
from poc.k1_poc.experience.narrative_weaver import NarrativeContext, NarrativeWeaver
from poc.k1_poc.experience.proactive_agent import FillMessage, ProactiveAgent
from poc.k1_poc.experience.rhythm_controller import ResponseStyle, RhythmController, TimingParams

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
