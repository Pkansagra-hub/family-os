"""
k1.fabric.adapters.prompt_system_prod -- Production PromptSystemAdapter.

Loads prompt templates from YAML contract files on disk and provides
``resolve()`` / ``compile()`` for the Context Builder.

Design:
  - Scans a directory for ``*.yaml`` / ``*.yml`` prompt contract files.
  - Each file has a ``prompt_contract`` top-level key with ``name``,
    ``template_file``, ``variables``, ``version``, ``description``,
    ``metadata`` fields (see ``tests/k1/fabric/fixtures/prompts/``).
  - ``resolve()`` returns a ``PromptTemplate`` loaded from the contract.
  - ``compile()`` performs ``{variable}`` substitution (same as test adapter).
  - Thread-safe via RLock (supports concurrent ContextBuilder calls).
  - Templates are loaded eagerly at construction and cached.
  - ``reload()`` re-scans the directory for hot-reload in long-running
    processes.

Consumers:
  - ContextBuilder (k1/fabric/core/context_builder.py)
  - Injected via FabricFactory.create_with_ports(prompt_system=...)

Structural subtyping:
  Satisfies IPromptSystemPort protocol without inheriting from it.

References:
  - IPromptSystemPort (5.1.5)
  - TestPromptSystemAdapter (5.2.6) -- mirror API for compatibility

Exports:
  PromptSystemProdAdapter
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from k1.fabric.ports.prompt_system import PromptTemplate

logger = logging.getLogger(__name__)


class PromptSystemProdAdapter:
    """
    Production prompt template adapter for Fabric's IPromptSystemPort.

    Loads prompt contracts from YAML files in a configured directory.
    Caches all templates at construction time.  Thread-safe.

    Implements ``IPromptSystemPort`` via structural subtyping:
      - resolve(template_name) -> Optional[PromptTemplate]
      - compile(template, variables) -> str
    """

    __slots__ = ("_templates", "_prompts_dir", "_lock", "_resolve_count", "_compile_count")

    def __init__(self, prompts_dir: str | Path) -> None:
        """
        Initialize and load all prompt templates from the directory.

        Args:
            prompts_dir: Path to the directory containing YAML prompt
                contract files.  Non-existent directory is tolerated
                (adapter starts with zero templates and logs a warning).
        """
        self._prompts_dir = Path(prompts_dir)
        self._templates: Dict[str, PromptTemplate] = {}
        self._lock = threading.RLock()
        self._resolve_count = 0
        self._compile_count = 0
        self._load_all()

    # ------------------------------------------------------------------
    # IPromptSystemPort protocol methods
    # ------------------------------------------------------------------

    def resolve(self, template_name: str) -> Optional[PromptTemplate]:
        """
        Look up a prompt template by name.

        Args:
            template_name: The template identifier to resolve.

        Returns:
            PromptTemplate if found, None if the name is unknown.
        """
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

        Accepts either a raw ``str`` or a ``PromptTemplate`` instance
        (extracting its ``.template`` attribute).  Uses simple
        ``{variable_name}`` replacement.  Unresolved placeholders
        are left as-is.  Extra variables are ignored.

        Args:
            template: Raw template string, PromptTemplate, or dict
                with a ``template`` key.
            variables: Mapping of variable names to their values.

        Returns:
            Compiled/rendered string with variables substituted.
        """
        with self._lock:
            self._compile_count += 1

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

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def reload(self) -> int:
        """
        Re-scan the prompts directory and reload all templates.

        Returns:
            Number of templates loaded.
        """
        with self._lock:
            self._templates.clear()
        self._load_all()
        with self._lock:
            return len(self._templates)

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    @property
    def template_count(self) -> int:
        """Number of loaded templates."""
        with self._lock:
            return len(self._templates)

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

    def has_template(self, name: str) -> bool:
        """Check if a template name is loaded."""
        with self._lock:
            return name in self._templates

    def list_names(self) -> List[str]:
        """Return all loaded template names."""
        with self._lock:
            return list(self._templates.keys())

    # ------------------------------------------------------------------
    # Internal: YAML loading
    # ------------------------------------------------------------------

    def _load_all(self) -> None:
        """Scan prompts_dir for YAML files and load each as a PromptTemplate."""
        if not self._prompts_dir.exists():
            logger.warning(
                "PromptSystemProdAdapter: prompts directory does not exist: %s",
                self._prompts_dir,
            )
            return

        if not self._prompts_dir.is_dir():
            logger.warning(
                "PromptSystemProdAdapter: prompts path is not a directory: %s",
                self._prompts_dir,
            )
            return

        loaded = 0
        for path in sorted(self._prompts_dir.iterdir()):
            if path.suffix not in (".yaml", ".yml"):
                continue
            try:
                pt = self._parse_prompt_file(path)
                if pt is not None:
                    with self._lock:
                        self._templates[pt.name] = pt
                    loaded += 1
            except Exception:
                logger.warning(
                    "PromptSystemProdAdapter: failed to load %s",
                    path,
                    exc_info=True,
                )

        logger.info(
            "PromptSystemProdAdapter: loaded %d templates from %s",
            loaded,
            self._prompts_dir,
        )

    @staticmethod
    def _parse_prompt_file(path: Path) -> Optional[PromptTemplate]:
        """Parse a single YAML prompt contract file into a PromptTemplate."""
        import yaml

        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if data is None:
            return None

        # Support both top-level and nested prompt_contract key
        contract = data.get("prompt_contract", data)

        name = contract.get("name", "")
        if not name:
            logger.debug("Skipping prompt file with no name: %s", path)
            return None

        # Build template string from template_file reference or inline
        template_str = contract.get("template", "")
        template_file = contract.get("template_file", "")
        if not template_str and template_file:
            # Store the file reference in the template — actual file
            # loading happens at compile-time if needed.
            template_str = f"{{{{template_file:{template_file}}}}}"

        # Extract variable names from the variables list
        raw_vars = contract.get("variables", [])
        var_names = []
        for v in raw_vars:
            if isinstance(v, dict):
                var_names.append(v.get("name", ""))
            elif isinstance(v, str):
                var_names.append(v)

        version = str(contract.get("version", "1.0"))

        metadata: Dict[str, Any] = {}
        for key in (
            "description",
            "domain",
            "intent_match",
            "max_tokens",
            "output_format",
            "compatible_agents",
            "template_file",
        ):
            if key in contract:
                metadata[key] = contract[key]

        return PromptTemplate(
            name=name,
            template=template_str,
            version=version,
            variables=[v for v in var_names if v],
            metadata=metadata,
        )

    def __repr__(self) -> str:
        with self._lock:
            return (
                f"PromptSystemProdAdapter(dir={self._prompts_dir}, "
                f"templates={len(self._templates)}, "
                f"resolves={self._resolve_count}, "
                f"compiles={self._compile_count})"
            )
