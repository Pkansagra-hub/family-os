"""
Prompt Template Engine — Dynamic prompt rendering with variable injection.

Merges static prompt templates with runtime context data. Supports:
  - Variable replacement: {{user_context}}, {{tools}}, {{history}}, {{constraints}}
  - Conditional blocks: {{#if has_health_data}}...{{/if}}
  - Loops: {{#each tools}}...{{/each}}

Uses simple Jinja2-like syntax for template rendering.

References:
  - docs/whiteboard/chat_experience.md - Agent Factory context merging
  - Jinja2 Docs: https://jinja.palletsprojects.com/
"""

import re
from datetime import datetime
from typing import Any, Dict, List, Optional

import structlog

from .prompt_registry import PromptTemplate, get_prompt_registry

logger = structlog.get_logger(__name__)


class PromptTemplateEngine:
    """
    Dynamic prompt template renderer.

    Fetches prompt templates from PromptRegistry and renders them with runtime context.
    Supports variable substitution, conditionals, and loops.

    Features:
        - Variable injection: {{variable_name}}
        - Conditional blocks: {{#if condition}}...{{/if}}
        - Loops: {{#each items}}...{{/each}}
        - Default values for missing variables
        - Template validation and error reporting
        - Metrics: render latency, cache hits, validation errors

    Singleton pattern: Use get_prompt_template_engine() for global access.
    """

    _instance: Optional["PromptTemplateEngine"] = None
    _initialized: bool = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """Initialize PromptTemplateEngine (singleton)."""
        if self._initialized:
            return

        self.registry = get_prompt_registry()
        self.metrics = {
            "renders": 0,
            "renders_success": 0,
            "renders_error": 0,
            "total_latency_ms": 0.0,
            "cache_hits": 0,
            "cache_misses": 0,
        }
        self.render_cache: Dict[str, str] = {}

        logger.info("Initializing PromptTemplateEngine")
        self._initialized = True

    def render_prompt(
        self,
        agent_type: str,
        context_data: Optional[Dict[str, Any]] = None,
        use_cache: bool = True,
    ) -> str:
        """
        Render prompt template with context data.

        Fetches prompt template by agent_type and merges with context_data.
        Supports variables, conditionals, and loops.

        Args:
            agent_type: str - Agent type (concierge, healthcare, finance, etc.)
            context_data: dict - Runtime context with keys:
                - user_context: str or dict - User KG data
                - tools: list[dict] - Available tools with name, description
                - history: str or list - Chat history
                - constraints: str or list - Additional constraints
                - has_health_data: bool - Conditional flag
                - (any other variables needed by template)
            use_cache: bool - Whether to cache rendered prompts (default True)

        Returns:
            str - Fully rendered prompt ready for LLM

        Raises:
            KeyError: If agent_type not found in registry
            ValueError: If template rendering fails
        """
        start_time = datetime.utcnow()
        self.metrics["renders"] += 1

        try:
            # Normalize context_data
            if context_data is None:
                context_data = {}

            # Check cache - create hashable key from context (convert lists to tuples)
            def make_hashable(obj):
                """Convert obj to hashable type."""
                if isinstance(obj, list):
                    return tuple(make_hashable(item) for item in obj)
                elif isinstance(obj, dict):
                    return tuple(sorted((k, make_hashable(v)) for k, v in obj.items()))
                else:
                    return obj

            # Convert context to hashable format first, then create cache key
            hashable_context = tuple(sorted((k, make_hashable(v)) for k, v in context_data.items()))
            cache_key = f"{agent_type}:{hash(hashable_context)}"
            if use_cache and cache_key in self.render_cache:
                self.metrics["cache_hits"] += 1
                logger.debug("Template cache hit", agent_type=agent_type)
                return self.render_cache[cache_key]

            self.metrics["cache_misses"] += 1

            # Fetch template from registry
            template: PromptTemplate = self.registry.get_prompt(agent_type)

            # Render all template sections
            rendered_system = self._render_template(template.system_prompt, context_data)

            rendered_tools = self._render_template(template.tool_prompt_template, context_data)

            rendered_context = self._render_template(template.context_prompt_template, context_data)

            rendered_constraints = self._render_list_to_string(template.constraints)

            # Combine all sections into final prompt
            final_prompt = f"{rendered_system}\n\n{rendered_tools}\n\n{rendered_context}\n\n## Constraints:\n{rendered_constraints}"

            # Cache result
            if use_cache:
                self.render_cache[cache_key] = final_prompt

            self.metrics["renders_success"] += 1
            latency_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
            self.metrics["total_latency_ms"] += latency_ms

            logger.info(
                "Prompt rendered successfully",
                agent_type=agent_type,
                latency_ms=latency_ms,
            )

            return final_prompt

        except Exception as e:
            self.metrics["renders_error"] += 1
            logger.error(
                "Failed to render prompt",
                agent_type=agent_type,
                error=str(e),
            )
            raise

    def _render_template(self, template: str, context: Dict[str, Any]) -> str:
        """
        Render template string with variable substitution, conditionals, and loops.

        Args:
            template: str - Template with {{variable}} syntax
            context: dict - Context data for variable substitution

        Returns:
            str - Rendered template
        """
        # Add defaults for missing context variables
        full_context = {
            "user_context": context.get("user_context", ""),
            "tools": context.get("tools", []),
            "history": context.get("history", ""),
            "constraints": context.get("constraints", []),
            "has_health_data": context.get("has_health_data", False),
        }
        full_context.update(context)

        result = template

        # Handle loops: {{#each items}}...{{/each}}
        result = self._render_loops(result, full_context)

        # Handle conditionals: {{#if condition}}...{{/if}}
        result = self._render_conditionals(result, full_context)

        # Handle simple variables: {{variable_name}}
        result = self._render_variables(result, full_context)

        return result.strip()

    def _render_variables(self, template: str, context: Dict[str, Any]) -> str:
        """
        Replace simple variables: {{variable_name}}.

        Args:
            template: str - Template string
            context: dict - Context variables

        Returns:
            str - String with variables replaced
        """
        # Pattern: {{variable_name}}
        pattern = r"\{\{([a-zA-Z_][a-zA-Z0-9_]*)\}\}"

        def replace_var(match):
            var_name = match.group(1)
            value = context.get(var_name, "")

            # Convert various types to string
            if isinstance(value, (list, dict)):
                return str(value)
            if value is None:
                return ""
            return str(value)

        return re.sub(pattern, replace_var, template)

    def _render_conditionals(self, template: str, context: Dict[str, Any]) -> str:
        """
        Render conditional blocks: {{#if condition}}...{{/if}}.

        Args:
            template: str - Template with conditionals
            context: dict - Context for condition evaluation

        Returns:
            str - Template with conditionals resolved
        """
        # Pattern: {{#if condition}}...{{/if}}
        pattern = r"\{\{#if\s+([a-zA-Z_][a-zA-Z0-9_]*)\}\}(.*?)\{\{/if\}\}"

        def replace_conditional(match):
            condition = match.group(1)
            body = match.group(2)

            # Evaluate condition (truthy check on context value)
            value = context.get(condition, False)
            if value:
                return body
            else:
                return ""

        return re.sub(pattern, replace_conditional, template, flags=re.DOTALL)

    def _render_loops(self, template: str, context: Dict[str, Any]) -> str:
        """
        Render loops: {{#each items}}...{{/each}}.

        Args:
            template: str - Template with loops
            context: dict - Context with items list

        Returns:
            str - Template with loops expanded
        """
        # Pattern: {{#each items}}...{{/each}}
        pattern = r"\{\{#each\s+([a-zA-Z_][a-zA-Z0-9_]*)\}\}(.*?)\{\{/each\}\}"

        def replace_loop(match):
            items_name = match.group(1)
            body = match.group(2)

            items = context.get(items_name, [])
            if not isinstance(items, list):
                items = []

            # Render body for each item
            results = []
            for item in items:
                # Replace {{this}} with item value
                if isinstance(item, dict):
                    # For dict items, replace {{this.key}} with value
                    item_result = body
                    for key, value in item.items():
                        item_result = re.sub(
                            r"\{\{this\." + key + r"\}\}",
                            str(value),
                            item_result,
                        )
                    # Also replace bare {{this}} with str(item)
                    item_result = re.sub(r"\{\{this\}\}", str(item), item_result)
                    results.append(item_result)
                else:
                    # For simple items, replace {{this}} with value
                    item_result = re.sub(r"\{\{this\}\}", str(item), body)
                    results.append(item_result)

            return "".join(results)

        return re.sub(pattern, replace_loop, template, flags=re.DOTALL)

    def _render_list_to_string(self, items: List[str]) -> str:
        """
        Convert list of strings to formatted string (one per line, with bullet points).

        Args:
            items: list[str] - List of strings

        Returns:
            str - Formatted string
        """
        if not items:
            return ""
        return "\n".join(f"• {item}" for item in items)

    def get_stats(self) -> Dict[str, Any]:
        """
        Get engine statistics.

        Returns:
            Dict with metrics: renders, success_rate, avg_latency_ms, cache_hit_rate
        """
        total_renders = self.metrics["renders"] or 1  # Avoid division by zero
        success_rate = (
            (self.metrics["renders_success"] / total_renders * 100) if total_renders > 0 else 0.0
        )

        total_cache_accesses = self.metrics["cache_hits"] + self.metrics["cache_misses"]
        cache_hit_rate = (
            (self.metrics["cache_hits"] / total_cache_accesses * 100)
            if total_cache_accesses > 0
            else 0.0
        )

        avg_latency_ms = (
            (self.metrics["total_latency_ms"] / self.metrics["renders_success"])
            if self.metrics["renders_success"] > 0
            else 0.0
        )

        return {
            "renders_total": self.metrics["renders"],
            "renders_success": self.metrics["renders_success"],
            "renders_error": self.metrics["renders_error"],
            "success_rate_percent": success_rate,
            "avg_latency_ms": avg_latency_ms,
            "cache_hits": self.metrics["cache_hits"],
            "cache_misses": self.metrics["cache_misses"],
            "cache_hit_rate_percent": cache_hit_rate,
        }

    def clear_cache(self) -> None:
        """Clear template cache."""
        self.render_cache.clear()
        logger.info("Template cache cleared")


# Singleton accessor
_engine: Optional[PromptTemplateEngine] = None


def get_prompt_template_engine() -> PromptTemplateEngine:
    """Get global PromptTemplateEngine instance (singleton pattern)."""
    global _engine
    if _engine is None:
        _engine = PromptTemplateEngine()
    return _engine
