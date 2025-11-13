"""
Tests for Prompt Template Engine — Dynamic template rendering.

Tests cover:
  - Variable substitution: {{variable_name}}
  - Conditional blocks: {{#if condition}}...{{/if}}
  - Loops: {{#each items}}...{{/each}}
  - Template rendering from registry
  - Cache behavior and hit rates
  - Error handling and edge cases
  - Integration with PromptRegistry

Run: python -m pytest tests/test_prompt_template_engine.py -v
"""

import pytest
from l5_infrastructure.registries.prompt_registry import (
    PromptRegistry,
    PromptTemplate,
    get_prompt_registry,
)
from l5_infrastructure.registries.prompt_template_engine import (
    PromptTemplateEngine,
    get_prompt_template_engine,
)


class TestPromptTemplateEngineVariables:
    """Test simple variable substitution."""

    def test_render_single_variable(self):
        """Test replacing a single variable."""
        engine = PromptTemplateEngine()
        engine._initialized = False
        PromptTemplateEngine._instance = engine

        template = "Hello {{name}}, welcome!"
        context = {"name": "John"}

        result = engine._render_variables(template, context)

        assert "John" in result
        assert "{{name}}" not in result

    def test_render_multiple_variables(self):
        """Test replacing multiple variables."""
        engine = PromptTemplateEngine()
        engine._initialized = False
        PromptTemplateEngine._instance = engine

        template = "User: {{user_name}}, Role: {{role}}, Status: {{status}}"
        context = {
            "user_name": "Alice",
            "role": "admin",
            "status": "active",
        }

        result = engine._render_variables(template, context)

        assert "Alice" in result
        assert "admin" in result
        assert "active" in result
        assert "{{" not in result

    def test_render_missing_variable_defaults_to_empty(self):
        """Test missing variables default to empty string."""
        engine = PromptTemplateEngine()
        engine._initialized = False
        PromptTemplateEngine._instance = engine

        template = "Name: {{name}}, Age: {{age}}"
        context = {"name": "Bob"}  # age is missing

        result = engine._render_variables(template, context)

        assert "Bob" in result
        assert "Name: Bob, Age:" in result

    def test_render_variable_with_list_value(self):
        """Test variable can be list (converted to string)."""
        engine = PromptTemplateEngine()
        engine._initialized = False
        PromptTemplateEngine._instance = engine

        template = "Items: {{items}}"
        context = {"items": ["apple", "banana", "cherry"]}

        result = engine._render_variables(template, context)

        assert "apple" in result
        assert "{{items}}" not in result

    def test_render_variable_with_dict_value(self):
        """Test variable can be dict (converted to string)."""
        engine = PromptTemplateEngine()
        engine._initialized = False
        PromptTemplateEngine._instance = engine

        template = "Data: {{data}}"
        context = {"data": {"key": "value"}}

        result = engine._render_variables(template, context)

        assert "value" in result
        assert "{{data}}" not in result


class TestPromptTemplateEngineConditionals:
    """Test conditional block rendering."""

    def test_render_conditional_true(self):
        """Test conditional renders when condition is true."""
        engine = PromptTemplateEngine()
        engine._initialized = False
        PromptTemplateEngine._instance = engine

        template = "{{#if has_health_data}}Health: {{health_info}}{{/if}}"
        context = {
            "has_health_data": True,
            "health_info": "Good",
        }

        result = engine._render_conditionals(template, context)

        assert "Health: {{health_info}}" in result
        assert "{{#if" not in result

    def test_render_conditional_false(self):
        """Test conditional removed when condition is false."""
        engine = PromptTemplateEngine()
        engine._initialized = False
        PromptTemplateEngine._instance = engine

        template = "Start {{#if has_health_data}}Health: {{health_info}}{{/if}} End"
        context = {
            "has_health_data": False,
            "health_info": "Good",
        }

        result = engine._render_conditionals(template, context)

        assert "Start  End" in result
        assert "Health:" not in result

    def test_render_multiple_conditionals(self):
        """Test multiple conditional blocks."""
        engine = PromptTemplateEngine()
        engine._initialized = False
        PromptTemplateEngine._instance = engine

        template = "{{#if has_health}}Health{{/if}} {{#if has_finance}}Finance{{/if}}"
        context = {
            "has_health": True,
            "has_finance": False,
        }

        result = engine._render_conditionals(template, context)

        assert "Health" in result
        assert "Finance" not in result

    def test_render_nested_conditional_logic(self):
        """Test conditional with newlines and formatting."""
        engine = PromptTemplateEngine()
        engine._initialized = False
        PromptTemplateEngine._instance = engine

        template = """Options:
{{#if show_option_1}}
- Option 1
{{/if}}
{{#if show_option_2}}
- Option 2
{{/if}}"""
        context = {
            "show_option_1": True,
            "show_option_2": False,
        }

        result = engine._render_conditionals(template, context)

        assert "Option 1" in result
        assert "Option 2" not in result


class TestPromptTemplateEngineLoops:
    """Test loop rendering."""

    def test_render_loop_with_simple_items(self):
        """Test loop over simple list items."""
        engine = PromptTemplateEngine()
        engine._initialized = False
        PromptTemplateEngine._instance = engine

        template = "Items: {{#each items}}{{this}} {{/each}}"
        context = {"items": ["apple", "banana", "cherry"]}

        result = engine._render_loops(template, context)

        assert "apple" in result
        assert "banana" in result
        assert "cherry" in result

    def test_render_loop_with_dict_items(self):
        """Test loop over list of dicts."""
        engine = PromptTemplateEngine()
        engine._initialized = False
        PromptTemplateEngine._instance = engine

        template = "Tools: {{#each tools}}\n- {{this.name}}: {{this.description}}\n{{/each}}"
        context = {
            "tools": [
                {"name": "web_search", "description": "Search the web"},
                {"name": "calendar_add", "description": "Add to calendar"},
            ]
        }

        result = engine._render_loops(template, context)

        assert "web_search" in result
        assert "Search the web" in result
        assert "calendar_add" in result
        assert "Add to calendar" in result

    def test_render_empty_loop(self):
        """Test loop with empty list."""
        engine = PromptTemplateEngine()
        engine._initialized = False
        PromptTemplateEngine._instance = engine

        template = "Tools: {{#each tools}}- {{this.name}}\n{{/each}}Done"
        context = {"tools": []}

        result = engine._render_loops(template, context)

        assert "Done" in result
        assert "-" not in result

    def test_render_loop_with_newlines(self):
        """Test loop preserves formatting with newlines."""
        engine = PromptTemplateEngine()
        engine._initialized = False
        PromptTemplateEngine._instance = engine

        template = """Constraints:
{{#each constraints}}• {{this}}
{{/each}}"""
        context = {
            "constraints": [
                "Be safe",
                "Be helpful",
                "Be honest",
            ]
        }

        result = engine._render_loops(template, context)

        assert "Be safe" in result
        assert "Be helpful" in result
        assert "Be honest" in result


class TestPromptTemplateEngineRendering:
    """Test full prompt rendering."""

    def test_render_prompt_with_all_elements(self):
        """Test rendering template with variables, conditionals, and loops."""
        engine = PromptTemplateEngine()
        engine._initialized = False
        PromptTemplateEngine._instance = engine

        template = """You are {{role}}.
{{#if has_expertise}}
Expertise: {{#each expertise}}- {{this}}
{{/each}}{{/if}}
Context: {{context}}"""

        context = {
            "role": "healthcare specialist",
            "has_expertise": True,
            "expertise": ["PT", "Recovery", "Health Tracking"],
            "context": "Helping John with recovery",
        }

        result = engine._render_template(template, context)

        assert "healthcare specialist" in result
        assert "PT" in result
        assert "Recovery" in result
        assert "Helping John with recovery" in result

    def test_render_list_to_string(self):
        """Test converting list of strings to formatted bullet list."""
        engine = PromptTemplateEngine()
        engine._initialized = False
        PromptTemplateEngine._instance = engine

        items = ["Rule 1", "Rule 2", "Rule 3"]
        result = engine._render_list_to_string(items)

        assert "• Rule 1" in result
        assert "• Rule 2" in result
        assert "• Rule 3" in result

    def test_render_list_to_string_empty(self):
        """Test converting empty list."""
        engine = PromptTemplateEngine()
        engine._initialized = False
        PromptTemplateEngine._instance = engine

        result = engine._render_list_to_string([])
        assert result == ""


class TestPromptTemplateEngineWithRegistry:
    """Test full integration with PromptRegistry."""

    def test_render_prompt_full_flow(self):
        """Test rendering prompt by agent_type from registry."""
        # Use shared registry/engine singleton pattern
        PromptRegistry._instance = None
        PromptRegistry._initialized = False
        PromptTemplateEngine._instance = None
        PromptTemplateEngine._initialized = False

        # Add prompt via registry
        registry = get_prompt_registry()
        prompt = PromptTemplate(
            agent_type="test_agent_unique_1",
            system_prompt="You are {{role}}",
            tool_prompt_template="Tools: {{#each tools}}{{this}} {{/each}}",
            context_prompt_template="Context: {{user_context}}",
            constraints=["Rule 1", "Rule 2"],
            examples=[],
            temperature=0.5,
            max_tokens=1024,
        )
        registry.add_prompt(prompt)

        # Get engine and render
        engine = get_prompt_template_engine()

        context = {
            "role": "healthcare specialist",
            "tools": ["health_tracker", "pt_scheduler"],
            "user_context": "Patient recovering from knee injury",
        }

        result = engine.render_prompt("test_agent_unique_1", context)

        assert "healthcare specialist" in result
        assert "Patient recovering from knee injury" in result
        assert "Rule 1" in result
        assert "Rule 2" in result

    def test_render_prompt_missing_agent_type(self):
        """Test error when agent_type not in registry."""
        PromptRegistry._instance = None
        PromptRegistry._initialized = False

        PromptTemplateEngine._instance = None
        PromptTemplateEngine._initialized = False
        engine = PromptTemplateEngine()

        with pytest.raises(KeyError):
            engine.render_prompt("nonexistent_agent", {})

    def test_render_prompt_increments_metrics(self):
        """Test that rendering increments metrics."""
        PromptRegistry._instance = None
        PromptRegistry._initialized = False
        PromptTemplateEngine._instance = None
        PromptTemplateEngine._initialized = False

        registry = get_prompt_registry()
        prompt = PromptTemplate(
            agent_type="test_agent_unique_2",
            system_prompt="Test",
            tool_prompt_template="Tools",
            context_prompt_template="Context",
            constraints=[],
            examples=[],
            temperature=0.5,
            max_tokens=1024,
        )
        registry.add_prompt(prompt)

        engine = get_prompt_template_engine()

        initial_renders = engine.metrics["renders"]
        engine.render_prompt("test_agent_unique_2", {})

        assert engine.metrics["renders"] == initial_renders + 1
        assert engine.metrics["renders_success"] > 0

    def test_render_prompt_cache(self):
        """Test that caching works for repeated renders."""
        PromptRegistry._instance = None
        PromptRegistry._initialized = False
        PromptTemplateEngine._instance = None
        PromptTemplateEngine._initialized = False

        registry = get_prompt_registry()
        prompt = PromptTemplate(
            agent_type="test_agent_unique_3",
            system_prompt="Test {{name}}",
            tool_prompt_template="Tools",
            context_prompt_template="Context",
            constraints=[],
            examples=[],
            temperature=0.5,
            max_tokens=1024,
        )
        registry.add_prompt(prompt)

        engine = get_prompt_template_engine()

        context = {"name": "John"}

        # First render (cache miss)
        result1 = engine.render_prompt("test_agent_unique_3", context, use_cache=True)

        # Second render (cache hit)
        result2 = engine.render_prompt("test_agent_unique_3", context, use_cache=True)

        # Results should be identical
        assert result1 == result2
        # At least 1 cache hit should have occurred
        assert engine.metrics["cache_hits"] >= 1

    def test_render_prompt_bypass_cache(self):
        """Test rendering without cache."""
        PromptRegistry._instance = None
        PromptRegistry._initialized = False
        PromptTemplateEngine._instance = None
        PromptTemplateEngine._initialized = False

        registry = get_prompt_registry()
        prompt = PromptTemplate(
            agent_type="test_agent_unique_4",
            system_prompt="Test",
            tool_prompt_template="Tools",
            context_prompt_template="Context",
            constraints=[],
            examples=[],
            temperature=0.5,
            max_tokens=1024,
        )
        registry.add_prompt(prompt)

        engine = get_prompt_template_engine()

        # Both renders should succeed even with use_cache=False
        result1 = engine.render_prompt("test_agent_unique_4", {}, use_cache=False)
        result2 = engine.render_prompt("test_agent_unique_4", {}, use_cache=False)

        # Results should be identical
        assert result1 == result2
        # At least 2 renders should have occurred
        assert engine.metrics["renders"] >= 2


class TestPromptTemplateEngineStats:
    """Test engine statistics tracking."""

    def test_get_stats(self):
        """Test retrieving engine statistics."""
        PromptRegistry._instance = None
        PromptRegistry._initialized = False
        PromptTemplateEngine._instance = None
        PromptTemplateEngine._initialized = False

        registry = get_prompt_registry()
        prompt = PromptTemplate(
            agent_type="test_agent_unique_5",
            system_prompt="Test",
            tool_prompt_template="Tools",
            context_prompt_template="Context",
            constraints=[],
            examples=[],
            temperature=0.5,
            max_tokens=1024,
        )
        registry.add_prompt(prompt)

        engine = get_prompt_template_engine()

        engine.render_prompt("test_agent_unique_5", {})
        engine.render_prompt("test_agent_unique_5", {})

        stats = engine.get_stats()

        assert stats["renders_total"] > 0
        assert stats["renders_success"] > 0
        assert "success_rate_percent" in stats
        assert "avg_latency_ms" in stats

    def test_clear_cache(self):
        """Test clearing template cache."""
        PromptTemplateEngine._instance = None
        PromptTemplateEngine._initialized = False
        engine = PromptTemplateEngine()

        engine.render_cache["test_key"] = "test_value"
        assert len(engine.render_cache) > 0

        engine.clear_cache()

        assert len(engine.render_cache) == 0

    def test_get_prompt_template_engine_singleton(self):
        """Test get_prompt_template_engine() returns singleton."""
        PromptTemplateEngine._instance = None
        PromptTemplateEngine._initialized = False

        engine1 = get_prompt_template_engine()
        engine2 = get_prompt_template_engine()

        assert engine1 is engine2


class TestPromptTemplateEngineEdgeCases:
    """Test edge cases and error handling."""

    def test_render_with_special_characters(self):
        """Test rendering with special characters."""
        engine = PromptTemplateEngine()
        engine._initialized = False
        PromptTemplateEngine._instance = engine

        template = "Special: {{special}} (test)"
        context = {"special": "!@#$%^&*()"}

        result = engine._render_variables(template, context)

        assert "!@#$%^&*()" in result

    def test_render_with_newlines_and_tabs(self):
        """Test rendering preserves whitespace."""
        engine = PromptTemplateEngine()
        engine._initialized = False
        PromptTemplateEngine._instance = engine

        template = "Line1\nLine2\t{{var}}"
        context = {"var": "Value"}

        result = engine._render_variables(template, context)

        assert "Line1\nLine2" in result
        assert "Value" in result

    def test_render_with_unicode(self):
        """Test rendering with Unicode characters."""
        engine = PromptTemplateEngine()
        engine._initialized = False
        PromptTemplateEngine._instance = engine

        template = "Unicode: {{emoji}}"
        context = {"emoji": "🎉"}

        result = engine._render_variables(template, context)

        assert "🎉" in result

    def test_render_nested_loops_not_supported(self):
        """Test that nested loops don't break rendering."""
        engine = PromptTemplateEngine()
        engine._initialized = False
        PromptTemplateEngine._instance = engine

        # Simple nested structure (not true nesting, just sequential)
        template = """{{#each groups}}
Group: {{this.name}}
{{#each this.items}}- {{this}}
{{/each}}{{/each}}"""
        context = {
            "groups": [
                {"name": "Group1", "items": ["item1", "item2"]},
            ]
        }

        result = engine._render_loops(template, context)

        # Should render without error
        assert "Group1" in result
