"""
k1.fabric.adapters.test_prompt_system -- TestPromptSystemAdapter (5.2.6).

In-memory prompt template store for testing.  Returns static templates
from a pre-loaded dict.

Design:
  - ``resolve()`` looks up a PromptTemplate by name.
  - ``compile()`` performs simple ``{variable}`` string replacement.
  - ``add_template()`` / ``remove_template()`` for test setup.
  - Thread-safe via RLock for concurrent test scenarios.
  - No real Prompt System dependency.

Structural subtyping:
  Satisfies IPromptSystemPort protocol without inheriting from it.

Exports:
  TestPromptSystemAdapter
"""

from __future__ import annotations

import threading
from typing import Any, Dict, List, Optional

from k1.fabric.ports.prompt_system import PromptTemplate

# ---------------------------------------------------------------------------
# TestPromptSystemAdapter
# ---------------------------------------------------------------------------


class TestPromptSystemAdapter:
    """
    In-memory prompt template stub for testing (5.2.6).

    Implements IPromptSystemPort structurally:
      - resolve(template_name) -> Optional[PromptTemplate]
      - compile(template, variables) -> str

    Setup helpers:
      - add_template(name, template, variables, version, metadata)
      - add_template_obj(prompt_template) -- add a PromptTemplate directly
      - remove_template(name) -- remove by name
      - clear() -- remove all templates
      - template_count -- number of templates loaded
      - has_template(name) -- check existence
      - list_names() -- all template names

    Compile behaviour:
      Simple ``{variable_name}`` substitution.  Unresolved placeholders
      are left as-is (no error).  Extra variables are ignored.
    """

    def __init__(self) -> None:
        self._templates: Dict[str, PromptTemplate] = {}
        self._resolve_count = 0
        self._compile_count = 0
        self._lock = threading.RLock()

    # -- Setup helpers -----------------------------------------------------

    def add_template(
        self,
        name: str,
        template: str,
        *,
        variables: Optional[List[str]] = None,
        version: str = "1.0",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Register a template by parts."""
        pt = PromptTemplate(
            name=name,
            template=template,
            version=version,
            variables=variables or [],
            metadata=metadata or {},
        )
        with self._lock:
            self._templates[name] = pt

    def add_template_obj(self, prompt_template: PromptTemplate) -> None:
        """Register a pre-built PromptTemplate."""
        with self._lock:
            self._templates[prompt_template.name] = prompt_template

    def remove_template(self, name: str) -> bool:
        """Remove a template. Returns True if it existed."""
        with self._lock:
            return self._templates.pop(name, None) is not None

    def clear(self) -> None:
        """Remove all templates and reset counters."""
        with self._lock:
            self._templates.clear()
            self._resolve_count = 0
            self._compile_count = 0

    @property
    def template_count(self) -> int:
        """Number of loaded templates."""
        with self._lock:
            return len(self._templates)

    def has_template(self, name: str) -> bool:
        """Check if a template name is loaded."""
        with self._lock:
            return name in self._templates

    def list_names(self) -> List[str]:
        """Return all loaded template names."""
        with self._lock:
            return list(self._templates.keys())

    @property
    def resolve_count(self) -> int:
        """Number of resolve() calls made."""
        with self._lock:
            return self._resolve_count

    @property
    def compile_count(self) -> int:
        """Number of compile() calls made."""
        with self._lock:
            return self._compile_count

    # -- Protocol methods --------------------------------------------------

    def resolve(self, template_name: str) -> Optional[PromptTemplate]:
        """Look up a prompt template by name."""
        with self._lock:
            self._resolve_count += 1
            return self._templates.get(template_name)

    def compile(
        self,
        template: Any,
        variables: Dict[str, Any],
    ) -> str:
        """
        Render a template string with variable substitutions.

        Uses simple ``{key}`` replacement.  Unresolved placeholders
        are left as-is.  Extra variables are ignored.

        Accepts either a raw ``str`` or a ``PromptTemplate`` instance
        (extracting its ``.template`` attribute).
        """
        with self._lock:
            self._compile_count += 1

        # ContextBuilder passes the resolve() result directly, which
        # is a PromptTemplate.  Extract the raw string.
        if hasattr(template, "template"):
            raw = template.template
        elif isinstance(template, dict):
            raw = template.get("template", template.get("text", ""))
        else:
            raw = str(template)

        result = raw
        for key, value in variables.items():
            result = result.replace(f"{{{key}}}", str(value))
        return result

    def __repr__(self) -> str:
        with self._lock:
            return (
                f"TestPromptSystemAdapter(templates={len(self._templates)}, "
                f"resolves={self._resolve_count}, "
                f"compiles={self._compile_count})"
            )
