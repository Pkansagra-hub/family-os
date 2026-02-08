"""
k1.fabric.ports.prompt_system -- IPromptSystemPort port (5.1.5).

Prompt template resolution and compilation for Context Builder.

Design:
  - PORT ONLY -- implementation lives in the Prompt System adapter (5.2).
  - ``resolve()`` fetches a prompt template by name.
  - ``compile()`` renders a template with variable substitutions.
  - PromptTemplate: frozen dataclass carrying template metadata and
    the raw template string.

Consumers:
  - ContextBuilder (k1/fabric/core/context_builder.py)

Production adapter: Prompt System adapter (5.2)
Test adapter: StaticPromptAdapter (5.2)

References:
  - Context Builder inline preview (context_builder.py IPromptSystemPort)
  - Section-based context merging (4.2.1)

Exports:
  IPromptSystemPort
  PromptTemplate
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

# ---------------------------------------------------------------------------
# Supporting types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PromptTemplate:
    """
    A resolved prompt template.

    Attributes:
        name: Template identifier used in ``resolve()``.
        template: Raw template string with variable placeholders.
        version: Template version for cache invalidation.
        variables: List of variable names expected in this template.
        metadata: Optional template metadata (author, description, etc.).
    """

    name: str = ""
    template: str = ""
    version: str = "1.0"
    variables: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def has_variable(self, var_name: str) -> bool:
        """Check if this template expects a given variable."""
        return var_name in self.variables

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict (compatible with inline Dict expectation)."""
        return {
            "name": self.name,
            "template": self.template,
            "version": self.version,
            "variables": list(self.variables),
            "metadata": dict(self.metadata),
        }


# ---------------------------------------------------------------------------
# Port protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class IPromptSystemPort(Protocol):
    """
    Prompt template resolution and compilation port.

    This is the canonical port interface (5.1.5).  Any object with
    matching method signatures satisfies this protocol (structural
    subtyping via ``typing.Protocol``).

    Context Builder calls ``resolve()`` to load a named template and
    ``compile()`` to render it with variables (agent context sections,
    session state, etc.).

    Structural compatibility:
      The inline preview in context_builder.py declares ``resolve()``
      returning ``Optional[Dict[str, Any]]``.  PromptTemplate has a
      ``to_dict()`` method for dict compatibility.  Implementations
      may return either form.

    Thread safety:
      ``resolve()`` and ``compile()`` MUST be safe for concurrent use
      from multiple asyncio tasks.
    """

    def resolve(self, template_name: str) -> Optional[PromptTemplate]:
        """
        Look up a prompt template by name.

        Args:
            template_name: The template identifier to resolve.

        Returns:
            PromptTemplate if found, None if the name is unknown.
        """
        ...  # pragma: no cover

    def compile(
        self,
        template: str,
        variables: Dict[str, Any],
    ) -> str:
        """
        Render a template string with variable substitutions.

        Args:
            template: Raw template string (from PromptTemplate.template
                or any valid template string).
            variables: Mapping of variable names to their values.

        Returns:
            Compiled/rendered string with variables substituted.
        """
        ...  # pragma: no cover
