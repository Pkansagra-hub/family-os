"""
Learning Extractor Agent - AI-powered writer for learning signals (P06)

This agent:
- Analyzes user feedback, corrections, and performance metrics
- Extracts learning signals that help improve agent performance
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


class LearningExtractorAgent(WriterAgentBase):
    """
    AI-powered writer for extracting learning signals.

    P06 Schema (Learning):
    - signal_type: "feedback" | "correction" | "performance" | "preference_shift"
    - signal_data: Type-specific data
    - valence: Positive/negative/neutral impact on agent learning
    - confidence: How confident this is a valid learning signal
    - context: Why this matters for agent improvement
    """

    def __init__(self, groq_client, batch_client, session_id: str):
        """Initialize learning extractor agent."""
        super().__init__(
            agent_id="learning_extractor_ai",
            writer_type="learning",
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
        Build LLM prompt for learning signal extraction.

        Tells LLM: "Look at this delta, extract learning signals that help the agent improve."
        """
        delta_str = json.dumps(delta, indent=2, default=str)

        # COMPACT prompt to reduce tokens and get cleaner JSON output
        prompt = f"""Extract learning signals from this interaction delta. Return ONLY JSON.

Delta: {delta_str}

If there are learning signals (user feedback, corrections, performance issues), return:
{{"learning_signals":[{{"type":"feedback|correction|performance","data":{{"feedback_text":"...","feedback_sentiment":"positive|negative|neutral"}},"confidence":0.85}}],"no_signals":false}}

If no signals found, return:
{{"learning_signals":[],"no_signals":true}}"""
        return prompt

    async def _extract_with_llm(
        self,
        prompt: str,
        trace_id: str,
    ) -> List[Dict[str, Any]]:
        """
        Use Groq LLM to extract learning signals.

        Returns list of extraction decisions ready to send as WriterCommands.
        """
        try:
            # Call Groq LLM with higher token limit to prevent truncation
            response = await self.groq_client.complete(
                model=groq_config.DEFAULT_MODEL,  # Configurable via GROQ_MODEL env var
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,  # Lower temperature for more consistent JSON
                max_tokens=1500,  # Increased to prevent truncation
                trace_id=trace_id,
            )

            # Parse response
            response_text = response["content"].strip()
            extracted = self.parse_json_from_text(response_text)

            # Convert to decision format
            decisions = []
            for signal in extracted.get("learning_signals", []):
                decision = {
                    "delta_type": "learning",
                    "content": signal.get("data", {}),
                    "schema_version": "1.0",
                    "confidence": signal.get("confidence", 0.8),
                }
                decisions.append(decision)

            logger.debug(
                "learning_extraction_complete",
                trace_id=trace_id,
                signals_extracted=len(decisions),
            )

            return decisions

        except json.JSONDecodeError as e:
            logger.error("learning_extraction_json_error", trace_id=trace_id, error=str(e))
            return []

        except Exception as e:
            logger.error("learning_extraction_llm_error", trace_id=trace_id, error=str(e))
            return []
            return []
            return []
