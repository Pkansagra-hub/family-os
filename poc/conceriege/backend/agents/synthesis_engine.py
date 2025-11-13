"""
SynthesisEngine: Generates natural synthesis of specialist results with contradiction detection.

Purpose:
- Generate natural language synthesis of specialist analysis
- Detect when specialist findings contradict user assumptions
- Present evidence clearly
- Maintain conversational tone

Architecture:
- Uses LLMClient for synthesis generation
- Extracts user assumptions from conversation context
- Detects contradictions via entity extraction
- Formats evidence for presentation
"""

import logging
import re

from backend.models.analysis_result import AnalysisResult

logger = logging.getLogger(__name__)


class SynthesisEngine:
    """Generates natural synthesis of specialist results with contradiction detection."""

    def __init__(self, llm_client, metrics_collector=None):
        """
        Initialize SynthesisEngine.

        Args:
            llm_client: LLMClient for generating synthesis via LLM
            metrics_collector: Optional metrics collector for tracking synthesis performance
        """
        self.llm_client = llm_client
        self.metrics_collector = metrics_collector

    async def synthesize(self, specialist_result: AnalysisResult, context: dict) -> dict:
        """
        Generate natural synthesis of specialist analysis.

        Args:
            specialist_result: AnalysisResult from specialist
            context: Dict with 'conversation_history', 'user_message', 'recent_history'

        Returns:
            Dict with:
            - synthesis: Natural language synthesis string
            - has_contradiction: bool
            - user_assumption: str (what user thought)
            - actual_finding: str (what specialist found)
            - confidence: float
        """
        # Extract user assumption from context
        user_assumption = self._extract_user_assumption(context)

        # Get specialist's primary finding
        primary_insight = specialist_result.insights[0] if specialist_result.insights else None

        if not primary_insight:
            return {
                "synthesis": "The specialist completed their analysis but didn't find specific insights.",
                "has_contradiction": False,
                "user_assumption": user_assumption,
                "actual_finding": "No specific findings",
                "confidence": 0.0,
            }

        # Extract actual finding from specialist
        actual_finding = primary_insight.summary

        # Detect contradiction
        has_contradiction = self._detect_contradiction(user_assumption, actual_finding)

        # Format evidence
        formatted_evidence = self._format_evidence(primary_insight.evidence)

        # Build synthesis prompt
        synthesis_prompt = self._build_synthesis_prompt(
            specialist_result,
            context,
            has_contradiction,
            formatted_evidence,
            user_assumption,
            actual_finding,
        )

        # Generate synthesis via LLM
        try:
            synthesis_text = await self.llm_client.generate_async(
                synthesis_prompt, model_profile="synthesis"
            )
        except Exception as e:
            logger.error(f"Synthesis generation failed: {e}, using fallback")
            synthesis_text = self._fallback_synthesis(
                specialist_result.specialist_type,
                actual_finding,
                has_contradiction,
                user_assumption,
            )

        return {
            "synthesis": synthesis_text,
            "has_contradiction": has_contradiction,
            "user_assumption": user_assumption,
            "actual_finding": actual_finding,
            "confidence": specialist_result.confidence,
        }

    def _extract_user_assumption(self, context: dict) -> str:
        """
        Extract user's original assumption/concern from conversation context.

        Args:
            context: Dict with conversation history

        Returns:
            str: User's assumption (e.g., "milk is making me sick")
        """
        # Get user message from context
        user_message = context.get("user_message", "")

        # Extract the core concern (first clause, primary concern)
        # Simple heuristic: text before first conjunction or question mark
        assumption = user_message
        for marker in [" and ", " or ", " but ", " because "]:
            if marker in assumption:
                assumption = assumption.split(marker)[0]
                break

        # Remove question marks and extra whitespace
        assumption = assumption.replace("?", "").strip()

        return assumption

    def _detect_contradiction(self, user_assumption: str, specialist_finding: str) -> bool:
        """
        Detect if specialist finding contradicts user assumption.

        Algorithm:
        1. Extract key entities (nouns/foods) from user assumption
        2. Extract key entities from specialist finding
        3. If different entities → Contradiction

        Args:
            user_assumption: User's original concern (e.g., "milk is making me sick")
            specialist_finding: Specialist's finding (e.g., "late night coffee")

        Returns:
            bool: True if contradiction detected
        """
        # Extract entities (simple keyword matching for PoC)
        user_entities = self._extract_entities(user_assumption)
        finding_entities = self._extract_entities(specialist_finding)

        # Check for contradiction: different primary entities = contradiction
        if not user_entities or not finding_entities:
            return False

        # Get primary entity from each
        user_primary = user_entities[0].lower()
        finding_primary = finding_entities[0].lower()

        # Check if they match (case-insensitive)
        if user_primary == finding_primary:
            return False

        # Check for partial matches (e.g., "coffee" in "late night coffee")
        if finding_primary in user_assumption.lower():
            return False

        if user_primary in specialist_finding.lower():
            return False

        # Different entities = contradiction
        return True

    def _extract_entities(self, text: str) -> list[str]:
        """
        Extract key food/health entities from text using simple keyword matching.

        Args:
            text: Text to extract entities from

        Returns:
            list[str]: Extracted entities (e.g., ["milk"], ["late night coffee"])
        """
        # Common health/food keywords
        keywords = [
            # Foods
            "milk",
            "coffee",
            "tea",
            "pizza",
            "spicy",
            "citrus",
            "tomato",
            "chocolate",
            "alcohol",
            "caffeine",
            "fried",
            "fatty",
            "dairy",
            # Health conditions
            "gerd",
            "reflux",
            "heartburn",
            "indigestion",
            "nausea",
            "bloating",
            # Symptoms
            "pain",
            "sick",
            "ache",
            "uncomfortable",
            "burning",
            "acid",
        ]

        entities = []
        text_lower = text.lower()

        # Check for compound terms first (e.g., "late night coffee")
        if "late night coffee" in text_lower:
            entities.append("late night coffee")
        else:
            # Single keywords
            for keyword in keywords:
                if keyword in text_lower:
                    entities.append(keyword)

        # Also look for phrases with "is" or "causes"
        # e.g., "X is making me sick" -> extract X
        pattern = r"(\w+)\s+(?:is|are|causes?|trigger)"
        matches = re.findall(pattern, text_lower)
        for match in matches:
            if match not in entities and len(match) > 2:  # Avoid single letters
                entities.append(match)

        return entities

    def _format_evidence(self, evidence: list[str], max_items: int = 3) -> str:
        """
        Format evidence list into readable format.

        Args:
            evidence: List of evidence strings
            max_items: Maximum number of evidence items to include

        Returns:
            str: Formatted evidence (e.g., "3 out of 5 GERD episodes occurred after coffee")
        """
        if not evidence:
            return ""

        # Take first max_items
        evidence = evidence[:max_items]

        # Format as bullet list or sentence
        if len(evidence) == 1:
            return evidence[0]
        elif len(evidence) == 2:
            return f"{evidence[0]} and {evidence[1]}"
        else:
            # Bullet list format
            formatted = "\n".join([f"  • {item}" for item in evidence])
            return formatted

    def _build_synthesis_prompt(
        self,
        result: AnalysisResult,
        context: dict,
        has_contradiction: bool,
        formatted_evidence: str,
        user_assumption: str,
        actual_finding: str,
    ) -> str:
        """
        Build LLM prompt for synthesis generation.

        Args:
            result: AnalysisResult from specialist
            context: Conversation context
            has_contradiction: Whether contradiction detected
            formatted_evidence: Formatted evidence string
            user_assumption: User's assumption
            actual_finding: Specialist's finding

        Returns:
            str: LLM prompt for synthesis
        """
        specialist_name = self._get_specialist_name(result.specialist_type)
        confidence_pct = int(result.confidence * 100)

        recent_history = context.get("recent_history", "")
        if isinstance(recent_history, list):
            recent_history = "\n".join(recent_history[-3:])  # Last 3 turns

        contradiction_note = ""
        if has_contradiction:
            contradiction_note = f"""
User assumption: "{user_assumption}"
Actual finding: "{actual_finding}"
Note: The specialist's finding differs from what the user initially thought.
Use gentle language to present the actual finding ("actually", "interestingly", "it turns out").
"""

        prompt = f"""You are synthesizing findings from a {specialist_name} into natural conversation.

Recent conversation:
{recent_history}

Specialist findings:
- Main insight: {actual_finding}
- Evidence: {formatted_evidence}
- Confidence: {confidence_pct}%

{contradiction_note}

Generate a natural synthesis that:
1. Acknowledges the specialist's work ("Interesting - the {specialist_name} found...")
2. Presents the key finding clearly
3. If contradiction exists, gently correct it
4. Connects evidence to user's original concern
5. Sounds conversational, not like a report

Good example:
"Interesting - the nutritionist analyzed your patterns and found that the trigger may actually be
late night coffee, not the milk. The evidence shows 3 out of 5 GERD episodes occurred after evening coffee."

Natural synthesis (20-50 words):"""

        return prompt

    def _get_specialist_name(self, specialist_type: str) -> str:
        """Get human-readable specialist name."""
        names = {
            "nutritionist": "nutritionist",
            "psychiatrist": "psychiatrist",
            "finance_analyst": "finance analyst",
            "planner": "planner",
            "orchestrator": "assistant",
        }
        return names.get(specialist_type, specialist_type)

    def _fallback_synthesis(
        self, specialist_type: str, finding: str, has_contradiction: bool, user_assumption: str
    ) -> str:
        """
        Fallback synthesis if LLM call fails.

        Args:
            specialist_type: Type of specialist
            finding: Specialist's finding
            has_contradiction: Whether contradiction detected
            user_assumption: User's original assumption

        Returns:
            str: Fallback synthesis text
        """
        specialist_name = self._get_specialist_name(specialist_type)

        if has_contradiction:
            return (
                f"The {specialist_name} analyzed your situation and found something interesting: "
                f"{finding}. This differs from what you initially mentioned ({user_assumption}), "
                f"but the evidence points to this finding."
            )
        else:
            return (
                f"The {specialist_name} analyzed your situation and found: {finding}. "
                f"The evidence supports this conclusion."
            )
