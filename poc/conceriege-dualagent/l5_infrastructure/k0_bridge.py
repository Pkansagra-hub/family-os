"""
Mock K0 Bridge - Simulates K0 Kernel Memory Queries
Returns conditional data based on symptoms and dietary patterns
"""

import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


class MockK0Bridge:
    """
    Mock K0 Bridge that simulates episodic and semantic memory queries
    Returns different patterns based on symptoms
    """

    # Mock memory database
    EPISODIC_MEMORY = [
        {
            "date": "2025-11-05",
            "entry": "User mentioned 'milk makes me feel sick' during breakfast conversation",
            "context": "morning routine discussion",
        },
        {
            "date": "2025-11-02",
            "entry": "User avoided dairy at dinner, said 'cheese doesn't agree with me'",
            "context": "meal planning",
        },
        {
            "date": "2025-10-28",
            "entry": "User noted stomach discomfort after latte",
            "context": "coffee routine",
        },
    ]

    DIETARY_PATTERNS = {
        "stomach": {
            "pattern": "lactose_intolerance",
            "confidence": 0.85,
            "triggers": ["milk", "cheese", "yogurt", "ice cream"],
            "frequency": "3 incidents in past 2 weeks",
            "severity": "moderate - stomach discomfort, bloating",
            "recommendations": [
                "Consider lactose-free alternatives",
                "Try digestive enzyme supplements",
                "Monitor portion sizes of dairy",
            ],
        },
        "headache": {
            "pattern": "possible_migraine_trigger",
            "confidence": 0.65,
            "triggers": ["aged cheese", "milk chocolate"],
            "frequency": "2 incidents in past month",
            "severity": "mild to moderate headaches",
            "recommendations": [
                "Track timing of dairy consumption vs headaches",
                "Consider tyramine sensitivity testing",
                "Try eliminating aged dairy products first",
            ],
        },
        "nausea": {
            "pattern": "dairy_sensitivity",
            "confidence": 0.75,
            "triggers": ["whole milk", "cream", "butter"],
            "frequency": "intermittent over past 3 weeks",
            "severity": "mild nausea, occasional vomiting",
            "recommendations": [
                "Reduce dairy fat content gradually",
                "Try plant-based milk alternatives",
                "Consult with gastroenterologist if persists",
            ],
        },
    }

    async def query_episodic_memory(
        self, query: str, context: Dict[str, Any]
    ) -> list[Dict[str, Any]]:
        """Query episodic memory (past events)"""
        logger.info(f"K0 Bridge: Querying episodic memory for '{query}'")

        # Simple keyword matching for POC
        relevant_memories = []
        keywords = query.lower().split()

        for memory in self.EPISODIC_MEMORY:
            if any(keyword in memory["entry"].lower() for keyword in keywords):
                relevant_memories.append(memory)

        logger.info(f"K0 Bridge: Found {len(relevant_memories)} relevant memories")
        return relevant_memories

    async def query_semantic_patterns(
        self, symptom_type: str, context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Query semantic memory for patterns"""
        logger.info(f"K0 Bridge: Analyzing patterns for symptom type '{symptom_type}'")

        # Normalize symptom type
        symptom_type = symptom_type.lower().strip()

        # Check for keyword matches
        if "stomach" in symptom_type or "bloat" in symptom_type or "digest" in symptom_type:
            pattern_data = self.DIETARY_PATTERNS["stomach"]
        elif "head" in symptom_type or "migraine" in symptom_type:
            pattern_data = self.DIETARY_PATTERNS["headache"]
        elif "nausea" in symptom_type or "sick" in symptom_type or "vomit" in symptom_type:
            pattern_data = self.DIETARY_PATTERNS["nausea"]
        else:
            # Default fallback
            pattern_data = {
                "pattern": "insufficient_data",
                "confidence": 0.3,
                "triggers": ["dairy products (general)"],
                "frequency": "unclear",
                "severity": "not enough data to determine",
                "recommendations": [
                    "Need more specific symptom information",
                    "Recommend keeping food diary for 1-2 weeks",
                ],
            }

        logger.info(
            f"K0 Bridge: Pattern identified - {pattern_data['pattern']} (confidence: {pattern_data['confidence']})"
        )
        return pattern_data

    async def query_combined(
        self, query: str, symptom_type: str, context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Combined query: episodic + semantic"""
        episodic = await self.query_episodic_memory(query, context)
        semantic = await self.query_semantic_patterns(symptom_type, context)

        return {
            "episodic_memories": episodic,
            "semantic_pattern": semantic,
            "query": query,
            "symptom_type": symptom_type,
        }


# Global singleton
_k0_bridge: MockK0Bridge | None = None


def get_k0_bridge() -> MockK0Bridge:
    """Get or create global K0 bridge singleton"""
    global _k0_bridge
    if _k0_bridge is None:
        _k0_bridge = MockK0Bridge()
    return _k0_bridge
