# Root SessionState table
from .SessionState import SessionState

# Section tables (6 core sections)
from .BeliefsSection import BeliefsSection
from .ScoreboardSection import ScoreboardSection
from .ControlSection import ControlSection
from .PersonaSection import PersonaSection
from .MultimodalSection import MultimodalSection
from .MetaSection import MetaSection

# Supporting tables
from .UserFact import UserFact
from .WorldKnowledge import WorldKnowledge
from .TemporalContext import TemporalContext
from .SpatialContext import SpatialContext
from .BlobRef import BlobRef
from .ActiveTask import ActiveTask
from .PendingProposal import PendingProposal
from .SagaCheckpoint import SagaCheckpoint
from .BackpressureState import BackpressureState

# Enums (strong typing)
from .Modality import Modality
from .Tone import Tone
from .BackpressureTier import BackpressureTier
from .Compression import Compression
from .ChecksumAlgo import ChecksumAlgo
from .TaskStatus import TaskStatus
from .ScoreBasis import ScoreBasis
from .RedactionBand import RedactionBand

# Structs (zero-copy hot paths)
from .AgentScore import AgentScore
from .ToolScore import ToolScore

# High-level wrapper (ergonomic API)
from .wrapper import (
    SessionStateWrapper,
    SessionStateBuilder,
    BlobHandle,
    SectionMask,
)

__all__ = [
    "SessionState",
    "BeliefsSection",
    "ScoreboardSection",
    "ControlSection",
    "PersonaSection",
    "MultimodalSection",
    "MetaSection",
    "UserFact",
    "WorldKnowledge",
    "TemporalContext",
    "SpatialContext",
    "BlobRef",
    "ActiveTask",
    "PendingProposal",
    "SagaCheckpoint",
    "BackpressureState",
    "Modality",
    "Tone",
    "BackpressureTier",
    "Compression",
    "ChecksumAlgo",
    "TaskStatus",
    "ScoreBasis",
    "RedactionBand",
    "AgentScore",
    "ToolScore",
    "SessionStateWrapper",
    "SessionStateBuilder",
    "BlobHandle",
    "SectionMask",
]

__version__ = "2.0.0"
