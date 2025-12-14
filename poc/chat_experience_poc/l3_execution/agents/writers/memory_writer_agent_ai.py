"""
Memory Writer Agent - Intelligent AI-powered writer for episodic and prospective memories

This agent:
- Analyzes SessionState deltas using Groq LLM
- Extracts episodic memories (P02) from user interactions
- Extracts prospective memories (P05) for future triggers/goals
- Sends extraction decisions via command port to K0
"""

import json
from importlib import import_module
from typing import Any, Dict, List

from config import groq_config

from .writer_agent_base import WriterAgentBase


def _get_logger(name: str):
    try:
        _structlog = import_module("structlog")
        return _structlog.get_logger(name)
    except Exception:

        class _ShimLogger:
            def __init__(self, n: str):
                self.name = n

            def debug(self, *args, **kwargs):
                pass

            def info(self, *args, **kwargs):
                pass

            def warning(self, *args, **kwargs):
                pass

            def error(self, *args, **kwargs):
                pass

        return _ShimLogger(name)


logger = _get_logger(__name__)


class MemoryWriterAgent(WriterAgentBase):
    """
    AI-powered writer for extracting episodic and prospective memories.

    P02 Schema (Episodic):
    - what: Event/interaction description
    - who: Entities involved
    - when: Timestamp
    - where: Context/location
    - emotion: Emotional valence
    - importance: 1-10 scale

    P05 Schema (Prospective):
    - trigger: What should remind user (calendar, location, person, etc.)
    - goal: What user wants to achieve
    - deadline: When goal should be done
    - context: Why this matters
    - agent_notes: How to help user achieve this
    """

    def __init__(self, groq_client, batch_client, session_id: str):
        """Initialize memory writer agent."""
        super().__init__(
            agent_id="memory_writer_ai",
            writer_type="memory",
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
        Build LLM prompt for episodic and prospective memory extraction.

        Tells LLM: "Look at this delta, extract any episodic memories (P02) or
        prospective memories (P05) using these schemas."
        """
        delta_str = json.dumps(delta, indent=2, default=str)
        session_state_str = (
            json.dumps(session_state, indent=2, default=str)
            if session_state
            else "No session context"
        )

        prompt = (
            """You are an intelligent memory extraction system for a personal AI assistant.

Analyze the following SessionState delta and extract memories if they exist.

## EPISODIC MEMORY (P02) - What happened
Extract if the delta shows:
- A user interaction or event
- A conversation with meaningful content
- A completed action or decision
- A user preference or behavior signal

P02 Schema:
{
    "what": "Description of the event/interaction",
    "who": ["Person", "Agent", "System"],
    "when": "2024-10-22T14:30:00Z",
    "where": "Context/location/channel",
    "emotion": "positive|neutral|negative",
    "importance": 7,
    "tags": ["tag1", "tag2"]
}

## PROSPECTIVE MEMORY (P05) - What's coming
Extract if the delta shows:
- User mentions a future event or goal
- User asks for a reminder
- User expresses an upcoming deadline or plan
- User sets a followup question or action

P05 Schema:
{
    "trigger": "What reminds the user (time, location, person, etc.)",
    "goal": "What the user wants to achieve",
    "deadline": "2024-10-25T18:00:00Z or 'ASAP' or null",
    "context": "Why this matters",
    "agent_notes": "How the agent should help user achieve this"
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
    "memories": [
        {
            "type": "episodic|prospective",
            "data": { ... P02 or P05 schema ... },
            "confidence": 0.85,
            "reason": "Why this memory was extracted"
        }
    ],
    "no_memories": false
}

If no memories should be extracted, return:
{
    "memories": [],
    "no_memories": true,
    "reason": "Why no memories apply"
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
        Use Groq LLM to extract episodic and prospective memories.

        Returns list of extraction decisions ready to send as WriterCommands.
        """
        try:
            # Call Groq LLM
            response = await self.groq_client.complete(
                model=groq_config.DEFAULT_MODEL,  # Configurable via GROQ_MODEL env var
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,  # Low temp for consistent extraction
                max_tokens=1000,
                trace_id=trace_id,
            )

            # Parse response
            response_text = response["content"].strip()
            extracted = self.parse_json_from_text(response_text)

            # Convert to decision format
            decisions = []
            for memory in extracted.get("memories", []):
                decision = {
                    "delta_type": "episodic" if memory["type"] == "episodic" else "prospective",
                    "content": memory.get("data", {}),
                    "schema_version": "1.0",
                    "confidence": memory.get("confidence", 0.8),
                }
                decisions.append(decision)

            logger.debug(
                "memory_extraction_complete",
                trace_id=trace_id,
                memories_extracted=len(decisions),
            )

            return decisions

        except json.JSONDecodeError as e:
            logger.error("memory_extraction_json_error", trace_id=trace_id, error=str(e))
            return []

        except Exception as e:
            logger.error("memory_extraction_llm_error", trace_id=trace_id, error=str(e))
            return []
            return []
            return []
