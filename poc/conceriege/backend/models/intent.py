"""
Intent Classification Model

Represents the classified intent from user messages for routing between PATH1 (specialist)
and PATH2 (orchestrator).

Research basis:
- Intent classification from dialogue systems (Allen 1999, Purver 2004)
- Mixed-Initiative Dialogue (Horvitz 1999)
"""

from dataclasses import dataclass, field
from typing import List, Literal


@dataclass
class Intent:
    """
    User intent classification result from LLM or rule-based classifier.

    Fields:
        type: Intent type - QUERY (data analysis) or ACTION (execute task)
        domain: Domain of the query - health, finance, social, general
        complexity: Query complexity - simple (PATH1) or multi_step (PATH2)
        specialist_type: Target specialist agent (nutritionist, psychiatrist, etc.)
        confidence: Classification confidence score (0.0-1.0)
        entities: Extracted entities from user message
        routing: Routing decision - PATH1 (single specialist) or PATH2 (orchestrator)

    Examples:
        >>> intent = Intent(
        ...     type="QUERY",
        ...     domain="health",
        ...     complexity="simple",
        ...     specialist_type="nutritionist",
        ...     confidence=0.92,
        ...     entities=["milk", "GERD"]
        ... )
        >>> intent.is_simple()
        True
        >>> intent.requires_orchestrator()
        False
    """

    type: Literal["QUERY", "ACTION"]
    domain: Literal["health", "finance", "social", "general"]
    complexity: Literal["simple", "multi_step"]
    specialist_type: str
    confidence: float
    entities: List[str] = field(default_factory=list)
    routing: Literal["PATH1", "PATH2"] = "PATH1"

    def __post_init__(self):
        """Auto-determine routing based on complexity if not set."""
        if self.complexity == "simple":
            self.routing = "PATH1"
        elif self.complexity == "multi_step":
            self.routing = "PATH2"

    def to_dict(self) -> dict:
        """
        Convert Intent to dictionary for JSON serialization.

        Returns:
            Dictionary representation of Intent
        """
        return {
            "type": self.type,
            "domain": self.domain,
            "complexity": self.complexity,
            "specialist_type": self.specialist_type,
            "confidence": self.confidence,
            "entities": self.entities,
            "routing": self.routing,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Intent":
        """
        Create Intent from dictionary.

        Args:
            data: Dictionary with intent fields

        Returns:
            Intent instance

        Examples:
            >>> data = {
            ...     "type": "QUERY",
            ...     "domain": "health",
            ...     "complexity": "simple",
            ...     "specialist_type": "nutritionist",
            ...     "confidence": 0.92,
            ...     "entities": ["milk", "GERD"],
            ...     "routing": "PATH1"
            ... }
            >>> intent = Intent.from_dict(data)
            >>> intent.type
            'QUERY'
        """
        return cls(
            type=data["type"],
            domain=data["domain"],
            complexity=data["complexity"],
            specialist_type=data["specialist_type"],
            confidence=data["confidence"],
            entities=data.get("entities", []),
            routing=data.get("routing", "PATH1"),
        )

    def is_simple(self) -> bool:
        """
        Check if this is a simple query (PATH1).

        Returns:
            True if complexity is "simple", False otherwise
        """
        return self.complexity == "simple"

    def requires_orchestrator(self) -> bool:
        """
        Check if this intent requires orchestrator (PATH2).

        Returns:
            True if complexity is "multi_step", False otherwise
        """
        return self.complexity == "multi_step"
