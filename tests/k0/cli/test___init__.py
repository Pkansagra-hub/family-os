"""Tests for k0.cli module."""

from __future__ import annotations

from k0.cli import main


class TestCliInit:
    """Test CLI module initialization."""

    def test_main_import(self) -> None:
        """Test that main function is properly imported."""
        # This tests that the import in __init__.py works
        assert callable(main)
        assert main.__name__ == "main"
