"""
Semantic Enricher Agent - AI-powered writer for semantic relationships and user knowledge graph

This agent:
- Analyzes SessionState deltas for semantic meaning
- Extracts entities, relationships, concepts, tags, and emotional valence
- Sends extraction decisions to User Knowledge Graph (not directly to K0)
"""

import json
from typing import Any, Dict, List

from config import groq_config

try:
    import structlog
except Exception:  # Fallback shim for lint/typecheck environments

    class _ShimLogger:
        def __init__(self, name: str):
            self.name = name

        def debug(self, *args, **kwargs):
            pass

        def info(self, *args, **kwargs):
            pass

        def warning(self, *args, **kwargs):
            pass

        def error(self, *args, **kwargs):
            pass

    class _ShimStructlog:
        @staticmethod
        def get_logger(name: str = __name__):
            return _ShimLogger(name)

    structlog = _ShimStructlog()  # type: ignore

from .writer_agent_base import WriterAgentBase

logger = structlog.get_logger(__name__)


class SemanticEnricherAgent(WriterAgentBase):
    """
    AI-powered writer for semantic enrichment and user knowledge graph updates.

    This writer enriches the User Knowledge Graph (not K0 directly) with:
    - Entity extraction (people, places, concepts)
    - Relationships between entities
    - Topic tags and semantic clusters
    - Emotional valence and context
    """

    def __init__(self, groq_client, batch_client, session_id: str):
        """Initialize semantic enricher agent."""
        super().__init__(
            agent_id="semantic_enricher_ai",
            writer_type="semantic",
            groq_client=groq_client,
            batch_client=batch_client,
            session_id=session_id,
        )

    def _build_extraction_prompt(
        self,
        delta: Dict[str, Any],
        session_state: Any,
    ) -> str:
        """
        Build LLM prompt for semantic extraction.

        Tells LLM: "Extract entities, relationships, and semantic meaning from this delta."
        """
        delta_str = json.dumps(delta, indent=2, default=str)
        session_state_str = (
            json.dumps(session_state, indent=2, default=str)
            if session_state
            else "No session context"
        )

        prompt = (
            """You are an intelligent semantic extraction system for building a user knowledge graph.

Analyze the following SessionState delta and extract semantic meaning if it exists.

## SEMANTIC EXTRACTION - Entities, Relationships, Concepts
Extract:
- Named entities: People, places, organizations, concepts
- Relationships: Who knows whom, what is related to what
- Topics and tags: What is this about
- Emotional context: How does the user feel about this
- Importance: How relevant is this to user's life

Semantic Data Schema:
{
    "entities": [
        {
            "name": "Entity name",
            "type": "person|place|organization|concept|topic",
            "description": "What is this entity",
            "aliases": ["Alternative names"],
            "importance": 1-10
        }
    ],
    "relationships": [
        {
            "from_entity": "Entity A",
            "relationship_type": "knows|works_with|related_to|interested_in",
            "to_entity": "Entity B",
            "strength": 1-10,
            "context": "Why this relationship matters"
        }
    ],
    "topics": ["topic1", "topic2", "topic3"],
    "emotional_valence": "positive|negative|neutral",
    "semantic_tags": ["tag1", "tag2"],
    "context_summary": "What this is about in plain language"
}

## DELTA TO ANALYZE
"""
            + delta_str
            + """

## SESSION CONTEXT
"""
            + session_state_str
            + """

## RESPONSE FORMAT
Return ONLY valid JSON with this structure (no markdown, no explanation):
{
    "semantic_extractions": [
        {
            "entities": [],
            "relationships": [],
            "topics": [],
            "emotional_valence": "positive|negative|neutral",
            "semantic_tags": [],
            "context_summary": "",
            "confidence": 0.85
        }
    ],
    "no_extractions": false
}

If no semantic meaning should be extracted, return:
{
    "semantic_extractions": [],
    "no_extractions": true,
    "reason": "Why no semantic content applies"
}
"""
        )
        return prompt

    async def _extract_with_llm(
        self,
        prompt: str,
        trace_id: str,
    ) -> List[Dict[str, Any]]:
        """
        Use Groq LLM to extract semantic relationships.

        Returns list of extraction decisions for User Knowledge Graph.
        """
        try:
            # Call Groq LLM
            response = await self.groq_client.complete(
                model=groq_config.DEFAULT_MODEL,  # Configurable via GROQ_MODEL env var
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=1500,
                trace_id=trace_id,
            )

            # Parse response
            response_text = response["content"].strip()
            extracted = self.parse_json_from_text(response_text)

            # Convert to decision format (writes to semantic storage, not K0 directly)
            decisions = []
            for extraction in extracted.get("semantic_extractions", []):
                decision = {
                    "delta_type": "semantic",  # Custom delta type for semantic storage
                    "content": {
                        "entities": extraction.get("entities", []),
                        "relationships": extraction.get("relationships", []),
                        "topics": extraction.get("topics", []),
                        "emotional_valence": extraction.get("emotional_valence", "neutral"),
                        "semantic_tags": extraction.get("semantic_tags", []),
                        "context_summary": extraction.get("context_summary", ""),
                    },
                    "schema_version": "1.0",
                    "confidence": extraction.get("confidence", 0.8),
                }
                decisions.append(decision)

            logger.debug(
                "semantic_extraction_complete",
                trace_id=trace_id,
                extractions=len(decisions),
            )

            return decisions

        except json.JSONDecodeError as e:
            logger.error("semantic_extraction_json_error", trace_id=trace_id, error=str(e))
            return []

        except Exception as e:
            logger.error("semantic_extraction_llm_error", trace_id=trace_id, error=str(e))
            return []
