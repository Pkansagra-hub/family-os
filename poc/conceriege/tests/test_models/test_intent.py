"""
Unit tests for Intent dataclass.

Tests:
- Intent creation with all fields
- to_dict() serialization
- from_dict() deserialization
- is_simple() method
- requires_orchestrator() method
- Automatic routing determination
"""

import pytest
from backend.models.intent import Intent


class TestIntent:
    """Test Intent dataclass functionality."""

    def test_intent_creation_simple_query(self):
        """Test creating simple query intent."""
        intent = Intent(
            type="QUERY",
            domain="health",
            complexity="simple",
            specialist_type="nutritionist",
            confidence=0.92,
            entities=["milk", "GERD"],
        )

        assert intent.type == "QUERY"
        assert intent.domain == "health"
        assert intent.complexity == "simple"
        assert intent.specialist_type == "nutritionist"
        assert intent.confidence == 0.92
        assert intent.entities == ["milk", "GERD"]
        assert intent.routing == "PATH1"  # Auto-determined

    def test_intent_creation_multi_step_action(self):
        """Test creating multi-step action intent."""
        intent = Intent(
            type="ACTION",
            domain="health",
            complexity="multi_step",
            specialist_type="orchestrator",
            confidence=0.88,
            entities=["appointment", "doctor"],
        )

        assert intent.type == "ACTION"
        assert intent.complexity == "multi_step"
        assert intent.routing == "PATH2"  # Auto-determined

    def test_intent_to_dict(self):
        """Test Intent serialization to dict."""
        intent = Intent(
            type="QUERY",
            domain="health",
            complexity="simple",
            specialist_type="nutritionist",
            confidence=0.92,
            entities=["milk", "GERD"],
        )

        data = intent.to_dict()

        assert data["type"] == "QUERY"
        assert data["domain"] == "health"
        assert data["complexity"] == "simple"
        assert data["specialist_type"] == "nutritionist"
        assert data["confidence"] == 0.92
        assert data["entities"] == ["milk", "GERD"]
        assert data["routing"] == "PATH1"

    def test_intent_from_dict(self):
        """Test Intent deserialization from dict."""
        data = {
            "type": "QUERY",
            "domain": "health",
            "complexity": "simple",
            "specialist_type": "nutritionist",
            "confidence": 0.92,
            "entities": ["milk", "GERD"],
            "routing": "PATH1",
        }

        intent = Intent.from_dict(data)

        assert intent.type == "QUERY"
        assert intent.domain == "health"
        assert intent.complexity == "simple"
        assert intent.specialist_type == "nutritionist"
        assert intent.confidence == 0.92
        assert intent.entities == ["milk", "GERD"]
        assert intent.routing == "PATH1"

    def test_intent_from_dict_no_entities(self):
        """Test Intent deserialization without entities."""
        data = {
            "type": "QUERY",
            "domain": "general",
            "complexity": "simple",
            "specialist_type": "general",
            "confidence": 0.85,
        }

        intent = Intent.from_dict(data)

        assert intent.entities == []  # Default empty list

    def test_intent_is_simple(self):
        """Test is_simple() method."""
        simple_intent = Intent(
            type="QUERY",
            domain="health",
            complexity="simple",
            specialist_type="nutritionist",
            confidence=0.92,
        )

        multi_step_intent = Intent(
            type="ACTION",
            domain="health",
            complexity="multi_step",
            specialist_type="orchestrator",
            confidence=0.88,
        )

        assert simple_intent.is_simple() is True
        assert multi_step_intent.is_simple() is False

    def test_intent_requires_orchestrator(self):
        """Test requires_orchestrator() method."""
        simple_intent = Intent(
            type="QUERY",
            domain="health",
            complexity="simple",
            specialist_type="nutritionist",
            confidence=0.92,
        )

        multi_step_intent = Intent(
            type="ACTION",
            domain="health",
            complexity="multi_step",
            specialist_type="orchestrator",
            confidence=0.88,
        )

        assert simple_intent.requires_orchestrator() is False
        assert multi_step_intent.requires_orchestrator() is True

    def test_intent_automatic_routing(self):
        """Test automatic routing determination based on complexity."""
        # Simple complexity -> PATH1
        simple_intent = Intent(
            type="QUERY",
            domain="health",
            complexity="simple",
            specialist_type="nutritionist",
            confidence=0.92,
        )
        assert simple_intent.routing == "PATH1"

        # Multi-step complexity -> PATH2
        complex_intent = Intent(
            type="ACTION",
            domain="health",
            complexity="multi_step",
            specialist_type="orchestrator",
            confidence=0.88,
        )
        assert complex_intent.routing == "PATH2"

    def test_intent_round_trip_serialization(self):
        """Test that serialization/deserialization preserves data."""
        original = Intent(
            type="QUERY",
            domain="health",
            complexity="simple",
            specialist_type="nutritionist",
            confidence=0.92,
            entities=["milk", "GERD", "pain"],
        )

        # Serialize to dict and back
        data = original.to_dict()
        restored = Intent.from_dict(data)

        # Verify all fields match
        assert restored.type == original.type
        assert restored.domain == original.domain
        assert restored.complexity == original.complexity
        assert restored.specialist_type == original.specialist_type
        assert restored.confidence == original.confidence
        assert restored.entities == original.entities
        assert restored.routing == original.routing


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
