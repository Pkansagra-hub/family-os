"""Tests for E-0.5.7: Concierge Direct SS Import Leakage fix.

Verifies:
  1. public_types.py facade exports all required types
  2. Each re-exported symbol is the SAME object as the deep import
  3. No production Concierge code imports from deep SS paths
  4. Facade module is importable without errors

References:
  - E-0.5.7: Concierge Direct SS Import Leakage
  - k1/sessionstate/public_types.py
"""

from __future__ import annotations

import ast
import importlib
from pathlib import Path

# ===========================================================================
# Facade importability
# ===========================================================================


class TestPublicTypesFacade:
    """public_types.py facade is importable and exports expected symbols."""

    def test_facade_imports_cleanly(self) -> None:
        """Module imports without error."""
        mod = importlib.import_module("k1.sessionstate.public_types")
        assert mod is not None

    def test_all_declared(self) -> None:
        """__all__ is defined and non-empty."""
        from k1.sessionstate import public_types

        assert hasattr(public_types, "__all__")
        assert len(public_types.__all__) > 0

    def test_all_symbols_accessible(self) -> None:
        """Every symbol in __all__ is actually importable."""
        from k1.sessionstate import public_types

        for name in public_types.__all__:
            assert hasattr(public_types, name), f"Missing: {name}"


# ===========================================================================
# Identity checks: facade re-exports are the same objects
# ===========================================================================


class TestReExportIdentity:
    """Each re-exported symbol is identical to the deep import."""

    def test_mutation_request_identity(self) -> None:
        from k1.sessionstate.ports.writer import MutationRequest as Deep
        from k1.sessionstate.public_types import MutationRequest as Facade

        assert Facade is Deep

    def test_batch_request_identity(self) -> None:
        from k1.sessionstate.ports.writer import BatchRequest as Deep
        from k1.sessionstate.public_types import BatchRequest as Facade

        assert Facade is Deep

    def test_rejection_category_identity(self) -> None:
        from k1.sessionstate.ports.writer import RejectionCategory as Deep
        from k1.sessionstate.public_types import RejectionCategory as Facade

        assert Facade is Deep

    def test_intent_classification_identity(self) -> None:
        from k1.sessionstate.public_types import IntentClassification as Facade
        from k1.sessionstate.sections.control import IntentClassification as Deep

        assert Facade is Deep

    def test_privacy_band_identity(self) -> None:
        from k1.sessionstate.public_types import PrivacyBand as Facade
        from k1.sessionstate.sections.control import PrivacyBand as Deep

        assert Facade is Deep

    def test_task_status_identity(self) -> None:
        from k1.sessionstate.public_types import TaskStatus as Facade
        from k1.sessionstate.sections.task_state import TaskStatus as Deep

        assert Facade is Deep

    def test_task_state_entry_identity(self) -> None:
        from k1.sessionstate.public_types import TaskStateEntry as Facade
        from k1.sessionstate.sections.task_state import TaskStateEntry as Deep

        assert Facade is Deep

    def test_task_state_section_identity(self) -> None:
        from k1.sessionstate.public_types import TaskStateSection as Facade
        from k1.sessionstate.sections.task_state import TaskStateSection as Deep

        assert Facade is Deep

    def test_artifact_type_identity(self) -> None:
        from k1.sessionstate.public_types import ArtifactType as Facade
        from k1.sessionstate.sections.task_artifacts import ArtifactType as Deep

        assert Facade is Deep

    def test_task_artifact_entry_identity(self) -> None:
        from k1.sessionstate.public_types import TaskArtifactEntry as Facade
        from k1.sessionstate.sections.task_artifacts import TaskArtifactEntry as Deep

        assert Facade is Deep

    def test_task_artifacts_section_identity(self) -> None:
        from k1.sessionstate.public_types import TaskArtifactsSection as Facade
        from k1.sessionstate.sections.task_artifacts import TaskArtifactsSection as Deep

        assert Facade is Deep

    def test_compute_temporal_anchor_identity(self) -> None:
        from k1.sessionstate.public_types import compute_temporal_anchor as Facade
        from k1.sessionstate.sections.temporal_context import compute_temporal_anchor as Deep

        assert Facade is Deep

    def test_temporal_anchor_identity(self) -> None:
        from k1.sessionstate.public_types import TemporalAnchor as Facade
        from k1.sessionstate.sections.temporal_context import TemporalAnchor as Deep

        assert Facade is Deep

    def test_meta_section_identity(self) -> None:
        from k1.sessionstate.public_types import MetaSection as Facade
        from k1.sessionstate.sections.meta import MetaSection as Deep

        assert Facade is Deep

    def test_session_state_factory_identity(self) -> None:
        from k1.sessionstate.factory import SessionStateFactory as Deep
        from k1.sessionstate.public_types import SessionStateFactory as Facade

        assert Facade is Deep


# ===========================================================================
# Boundary enforcement: no deep SS imports in production Concierge code
# ===========================================================================

# Directories that are PRODUCTION code (not tests)
_CONCIERGE_PROD_ROOT = Path("k1/concierge")

# Patterns that indicate a deep SS internal import
_DEEP_SS_PATTERNS = (
    "k1.sessionstate.sections.",
    "k1.sessionstate.ports.",
    "k1.sessionstate.factory",
    "k1.sessionstate.sizetracker",
    "k1.sessionstate.adapters.",
    "k1.sessionstate.guard",
    "k1.sessionstate.eviction",
    "k1.sessionstate.migration",
)

# Allowed import: the facade itself
_ALLOWED_SS_IMPORT = "k1.sessionstate.public_types"


def _collect_production_py_files() -> list[Path]:
    """Collect all .py files under k1/concierge/ (exclude tests/)."""
    root = Path(__file__).resolve().parents[3] / "k1" / "concierge"
    files = []
    for py_file in root.rglob("*.py"):
        # Skip test directories
        rel = py_file.relative_to(root)
        parts = rel.parts
        if any(p.startswith("test") for p in parts):
            continue
        files.append(py_file)
    return files


def _extract_imports(source: str) -> list[str]:
    """Extract all import module strings from Python source."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                modules.append(node.module)
    return modules


class TestNoDeepSSImports:
    """Production Concierge code must not import from deep SS paths."""

    def test_no_deep_imports_in_production(self) -> None:
        """Scan all production .py files for deep SS imports."""
        violations: list[str] = []
        files = _collect_production_py_files()
        assert len(files) > 0, "No production files found"

        for py_file in files:
            source = py_file.read_text(encoding="utf-8")
            imports = _extract_imports(source)
            for mod in imports:
                if any(mod.startswith(p) for p in _DEEP_SS_PATTERNS):
                    if mod == _ALLOWED_SS_IMPORT:
                        continue
                    violations.append(f"{py_file.name}: {mod}")

        assert (
            violations == []
        ), "Deep SS imports found in production Concierge code:\n" + "\n".join(
            f"  - {v}" for v in violations
        )
