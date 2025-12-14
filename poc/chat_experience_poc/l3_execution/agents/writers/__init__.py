"""
Writer Agents - Tier 3 Background Agents for K0 Persistence.

Writer agents are ALWAYS-ACTIVE background agents that:
- RECEIVE TASKS from Planner (via mailbox)
- READ SessionState and DeltaBus events
- KNOW K0 table schemas (P02 episodic, P05 prospective, semantic, learning)
- ENRICH deltas with metadata (entities, triggers, semantic tags)
- BATCH writes (100 deltas OR 250ms window)
- WRITE to Mock K0 via K0 Bridge

Architecture:
- Tier 3: Background processing (doesn't block response streaming)
- Always-Active: Persist for session lifetime (like Tier 1)
- Mailbox-based: Receive tasks from Planner (not just DeltaBus subscribers)
- Specialized knowledge: Each writer knows specific K0 schemas

Writers:
- MemoryWriterAgent: Episodic (P02) + Prospective (P05) + Semantic
- LearningExtractorAgent: Learning signals (P06)
- SemanticEnricherAgent: Concepts, relationships, affect

References:
- docs/whiteboard/chat_experience.md - Writer Agents architecture
- Epic 5.1, 5.2, 5.3 - Writer agent implementation
"""

from .learning_extractor_agent_ai import LearningExtractorAgent
from .memory_writer_agent_ai import MemoryWriterAgent
from .semantic_enricher_agent_ai import SemanticEnricherAgent
from .writer_agent_base import WriterAgentBase, WriterCommand, WriterCommandPort

__all__ = [
    "WriterAgentBase",
    "WriterCommand",
    "WriterCommandPort",
    "MemoryWriterAgent",
    "LearningExtractorAgent",
    "SemanticEnricherAgent",
]
