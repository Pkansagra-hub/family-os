"""
Tests for Prompt Registry — Centralized prompt management.

Tests cover:
  - Loading prompts from JSON file
  - Querying prompts by agent_type
  - Prompt validation and schema enforcement
  - Registry statistics and metrics
  - Thread-safe singleton pattern
  - CRUD operations (add, update, delete)
  - Error handling and edge cases

Run: python -m pytest tests/test_prompt_registry.py -v
"""

from datetime import datetime
from unittest.mock import mock_open, patch

import pytest
from l5_infrastructure.registries.prompt_registry import (
    PromptRegistry,
    PromptTemplate,
    create_default_prompts,
    get_prompt_registry,
)


class TestPromptTemplate:
    """Test PromptTemplate dataclass."""

    def test_prompt_template_creation(self):
        """Test creating a valid PromptTemplate."""
        prompt = PromptTemplate(
            agent_type="concierge",
            system_prompt="You are helpful",
            tool_prompt_template="Tools: {{#each tools}}{{this.name}}{{/each}}",
            context_prompt_template="Context: {{user_context}}",
            constraints=["Be nice", "Be safe"],
            examples=[{"input": "hi", "output": "hello"}],
            temperature=0.7,
            max_tokens=1024,
        )

        assert prompt.agent_type == "concierge"
        assert prompt.temperature == 0.7
        assert len(prompt.constraints) == 2
        assert len(prompt.examples) == 1

    def test_prompt_template_validation_success(self):
        """Test validation passes for valid template."""
        prompt = PromptTemplate(
            agent_type="healthcare",
            system_prompt="Medical expert",
            tool_prompt_template="Tools",
            context_prompt_template="Context",
            constraints=["Safe"],
            examples=[],
            temperature=0.3,
            max_tokens=2048,
        )

        assert prompt.validate() is True

    def test_prompt_template_validation_empty_agent_type(self):
        """Test validation fails with empty agent_type."""
        prompt = PromptTemplate(
            agent_type="",
            system_prompt="Valid",
            tool_prompt_template="Valid",
            context_prompt_template="Valid",
            constraints=[],
            examples=[],
            temperature=0.5,
            max_tokens=1024,
        )

        with pytest.raises(ValueError, match="agent_type must be non-empty"):
            prompt.validate()

    def test_prompt_template_validation_invalid_temperature(self):
        """Test validation fails with invalid temperature."""
        prompt = PromptTemplate(
            agent_type="test",
            system_prompt="Valid",
            tool_prompt_template="Valid",
            context_prompt_template="Valid",
            constraints=[],
            examples=[],
            temperature=3.5,  # Out of range
            max_tokens=1024,
        )

        with pytest.raises(ValueError, match="temperature must be between 0.0 and 2.0"):
            prompt.validate()

    def test_prompt_template_validation_invalid_max_tokens(self):
        """Test validation fails with invalid max_tokens."""
        prompt = PromptTemplate(
            agent_type="test",
            system_prompt="Valid",
            tool_prompt_template="Valid",
            context_prompt_template="Valid",
            constraints=[],
            examples=[],
            temperature=0.5,
            max_tokens=0,  # Invalid
        )

        with pytest.raises(ValueError, match="max_tokens must be positive"):
            prompt.validate()

    def test_prompt_template_to_dict(self):
        """Test serialization to dictionary."""
        prompt = PromptTemplate(
            agent_type="concierge",
            system_prompt="Helpful assistant",
            tool_prompt_template="Tools",
            context_prompt_template="Context",
            constraints=["Safe"],
            examples=[{"input": "hi", "output": "hello"}],
            temperature=0.7,
            max_tokens=1024,
        )

        data = prompt.to_dict()

        assert data["agent_type"] == "concierge"
        assert data["system_prompt"] == "Helpful assistant"
        assert data["temperature"] == 0.7
        assert isinstance(data["created_at"], str)  # Should be ISO format
        assert isinstance(data["updated_at"], str)

    def test_prompt_template_from_dict(self):
        """Test deserialization from dictionary."""
        data = {
            "agent_type": "healthcare",
            "system_prompt": "Medical expert",
            "tool_prompt_template": "Tools",
            "context_prompt_template": "Context",
            "constraints": ["Safe"],
            "examples": [],
            "temperature": 0.3,
            "max_tokens": 1024,
            "version": "1.0",
            "created_at": "2025-11-05T00:00:00",
            "updated_at": "2025-11-05T00:00:00",
        }

        prompt = PromptTemplate.from_dict(data)

        assert prompt.agent_type == "healthcare"
        assert isinstance(prompt.created_at, datetime)


class TestPromptRegistry:
    """Test PromptRegistry class."""

    def test_prompt_registry_singleton(self):
        """Test PromptRegistry is singleton."""
        # Reset singleton for testing
        PromptRegistry._instance = None
        PromptRegistry._initialized = False

        registry1 = PromptRegistry()
        registry2 = PromptRegistry()

        assert registry1 is registry2

    def test_prompt_registry_initialization_empty(self):
        """Test registry initialization when file doesn't exist."""
        PromptRegistry._instance = None
        PromptRegistry._initialized = False

        with patch("pathlib.Path.exists", return_value=False):
            registry = PromptRegistry()
            assert len(registry.prompts) == 0

    def test_prompt_registry_get_prompt_success(self):
        """Test retrieving a prompt by agent_type."""
        # Setup
        PromptRegistry._instance = None
        PromptRegistry._initialized = False

        registry = PromptRegistry()
        prompt = PromptTemplate(
            agent_type="test_agent",
            system_prompt="Test",
            tool_prompt_template="Tools",
            context_prompt_template="Context",
            constraints=[],
            examples=[],
            temperature=0.5,
            max_tokens=1024,
        )
        registry.add_prompt(prompt)

        # Test
        retrieved = registry.get_prompt("test_agent")
        assert retrieved.agent_type == "test_agent"
        assert registry.metrics["queries"] > 0
        assert registry.metrics["hits"] > 0

    def test_prompt_registry_get_prompt_not_found(self):
        """Test KeyError when prompt not found."""
        PromptRegistry._instance = None
        PromptRegistry._initialized = False

        registry = PromptRegistry()

        with pytest.raises(KeyError, match="Prompt not found"):
            registry.get_prompt("nonexistent")

        assert registry.metrics["misses"] > 0

    def test_prompt_registry_list_prompts(self):
        """Test listing all available prompts."""
        PromptRegistry._instance = None
        PromptRegistry._initialized = False

        registry = PromptRegistry()
        initial_count = len(registry.list_prompts())

        prompt1 = PromptTemplate(
            agent_type="agent1_unique",
            system_prompt="Test",
            tool_prompt_template="Tools",
            context_prompt_template="Context",
            constraints=[],
            examples=[],
            temperature=0.5,
            max_tokens=1024,
        )
        prompt2 = PromptTemplate(
            agent_type="agent2_unique",
            system_prompt="Test",
            tool_prompt_template="Tools",
            context_prompt_template="Context",
            constraints=[],
            examples=[],
            temperature=0.5,
            max_tokens=1024,
        )

        registry.add_prompt(prompt1)
        registry.add_prompt(prompt2)

        prompts = registry.list_prompts()
        assert "agent1_unique" in prompts
        assert "agent2_unique" in prompts
        assert len(prompts) == initial_count + 2

    def test_prompt_registry_add_prompt(self):
        """Test adding a prompt to registry."""
        PromptRegistry._instance = None
        PromptRegistry._initialized = False

        registry = PromptRegistry()
        prompt = PromptTemplate(
            agent_type="new_agent",
            system_prompt="New",
            tool_prompt_template="Tools",
            context_prompt_template="Context",
            constraints=[],
            examples=[],
            temperature=0.5,
            max_tokens=1024,
        )

        registry.add_prompt(prompt)

        assert "new_agent" in registry.prompts
        assert registry.prompts["new_agent"].system_prompt == "New"

    def test_prompt_registry_add_invalid_prompt(self):
        """Test adding invalid prompt raises error."""
        PromptRegistry._instance = None
        PromptRegistry._initialized = False

        registry = PromptRegistry()
        invalid_prompt = PromptTemplate(
            agent_type="",  # Invalid
            system_prompt="Test",
            tool_prompt_template="Tools",
            context_prompt_template="Context",
            constraints=[],
            examples=[],
            temperature=0.5,
            max_tokens=1024,
        )

        with pytest.raises(ValueError):
            registry.add_prompt(invalid_prompt)

    def test_prompt_registry_get_stats(self):
        """Test retrieving registry statistics."""
        PromptRegistry._instance = None
        PromptRegistry._initialized = False

        registry = PromptRegistry()
        initial_count = len(registry.prompts)

        prompt = PromptTemplate(
            agent_type="test_unique",
            system_prompt="Test",
            tool_prompt_template="Tools",
            context_prompt_template="Context",
            constraints=[],
            examples=[],
            temperature=0.5,
            max_tokens=1024,
        )
        registry.add_prompt(prompt)

        # Query a few times
        registry.get_prompt("test_unique")
        registry.get_prompt("test_unique")

        stats = registry.get_stats()

        assert stats["prompt_count"] == initial_count + 1
        assert stats["queries"] > 0
        assert stats["hit_rate_percent"] > 0

    def test_prompt_registry_reset(self):
        """Test resetting registry to empty state."""
        PromptRegistry._instance = None
        PromptRegistry._initialized = False

        registry = PromptRegistry()
        initial_count = len(registry.prompts)
        assert initial_count > 0  # Should have loaded defaults

        prompt = PromptTemplate(
            agent_type="test_reset",
            system_prompt="Test",
            tool_prompt_template="Tools",
            context_prompt_template="Context",
            constraints=[],
            examples=[],
            temperature=0.5,
            max_tokens=1024,
        )
        registry.add_prompt(prompt)
        assert len(registry.prompts) == initial_count + 1

        registry.reset()
        assert len(registry.prompts) == 0

    def test_prompt_registry_save_prompts(self):
        """Test saving prompts to JSON file."""
        PromptRegistry._instance = None
        PromptRegistry._initialized = False

        registry = PromptRegistry()
        prompt = PromptTemplate(
            agent_type="test",
            system_prompt="Test",
            tool_prompt_template="Tools",
            context_prompt_template="Context",
            constraints=["Rule1"],
            examples=[],
            temperature=0.5,
            max_tokens=1024,
        )
        registry.add_prompt(prompt)

        # Mock file writing
        with patch("builtins.open", mock_open()) as mock_file:
            registry.save_prompts()
            mock_file.assert_called()
            assert registry.metrics["saves"] > 0

    def test_get_prompt_registry_singleton(self):
        """Test get_prompt_registry() returns singleton."""
        PromptRegistry._instance = None
        PromptRegistry._initialized = False

        reg1 = get_prompt_registry()
        reg2 = get_prompt_registry()

        assert reg1 is reg2


class TestCreateDefaultPrompts:
    """Test default prompt creation."""

    def test_create_default_prompts(self):
        """Test creating default prompts for all agent types."""
        prompts = create_default_prompts()

        assert "concierge" in prompts
        assert "healthcare" in prompts
        assert "finance" in prompts
        assert "planner" in prompts
        assert "memory_writer" in prompts

        # Verify each prompt is valid
        for prompt in prompts.values():
            assert prompt.validate() is True

    def test_default_prompts_have_required_fields(self):
        """Test each default prompt has all required fields."""
        prompts = create_default_prompts()

        for agent_type, prompt in prompts.items():
            assert prompt.agent_type == agent_type
            assert len(prompt.system_prompt) > 0
            assert len(prompt.tool_prompt_template) > 0
            assert len(prompt.context_prompt_template) > 0
            assert len(prompt.constraints) > 0
            assert 0.0 <= prompt.temperature <= 2.0
            assert prompt.max_tokens > 0

    def test_default_prompts_include_examples(self):
        """Test each default prompt includes examples."""
        prompts = create_default_prompts()

        for agent_type, prompt in prompts.items():
            if agent_type != "memory_writer":  # Most have examples
                assert len(prompt.examples) > 0, f"{agent_type} should have examples"


class TestPromptRegistryIntegration:
    """Integration tests for Prompt Registry."""

    def test_load_and_query_flow(self):
        """Test complete flow: create, save, load, query."""
        PromptRegistry._instance = None
        PromptRegistry._initialized = False

        # Create and add prompts
        registry = PromptRegistry()
        defaults = create_default_prompts()
        for prompt in defaults.values():
            registry.add_prompt(prompt)

        # Query
        concierge = registry.get_prompt("concierge")
        assert concierge.agent_type == "concierge"
        assert "friendly" in concierge.system_prompt.lower()

        healthcare = registry.get_prompt("healthcare")
        assert healthcare.agent_type == "healthcare"
        assert healthcare.temperature == 0.3  # Should be lower for medical

    def test_multiple_agents_different_temperatures(self):
        """Test that different agents have appropriate temperatures."""
        PromptRegistry._instance = None
        PromptRegistry._initialized = False

        registry = PromptRegistry()
        defaults = create_default_prompts()
        for prompt in defaults.values():
            registry.add_prompt(prompt)

        # Healthcare and Memory Writer should be precise (low temp)
        healthcare = registry.get_prompt("healthcare")
        assert healthcare.temperature <= 0.4

        memory_writer = registry.get_prompt("memory_writer")
        assert memory_writer.temperature <= 0.3

        # Concierge should be more creative (higher temp)
        concierge = registry.get_prompt("concierge")
        assert concierge.temperature >= 0.6

    def test_concurrent_access_thread_safety(self):
        """Test registry is thread-safe for concurrent reads."""
        import threading

        PromptRegistry._instance = None
        PromptRegistry._initialized = False

        registry = PromptRegistry()
        defaults = create_default_prompts()
        for prompt in defaults.values():
            registry.add_prompt(prompt)

        results = []

        def query_agent(agent_type):
            try:
                registry.get_prompt(agent_type)
                results.append((agent_type, True))
            except Exception as e:
                results.append((agent_type, False, str(e)))

        # Create multiple threads querying different agents
        threads = []
        for agent_type in registry.list_prompts():
            t = threading.Thread(target=query_agent, args=(agent_type,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        # All queries should succeed
        assert all(success for result in results for success in result[1:2])
