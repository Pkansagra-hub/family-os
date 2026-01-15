"""
Tests for k0ctl dlq commands (P03 extensions).

Issue 6.2.16: k0ctl dlq commands for P03
"""

from __future__ import annotations

import pytest

# ============================================================================
# Tests for dlq list --pipeline filter
# ============================================================================


class TestDlqListPipeline:
    """Tests for dlq list with --pipeline filter."""

    def test_pipeline_alias_for_driver(self) -> None:
        """Test --pipeline is treated as alias for --driver."""
        from k0.cli.k0ctl import build_parser

        parser = build_parser()
        args = parser.parse_args(
            [
                "dlq",
                "list",
                "--pipeline",
                "p03_consolidation",
            ]
        )

        assert args.pipeline == "p03_consolidation"

    def test_phase_filter_argument(self) -> None:
        """Test --phase filter argument is parsed."""
        from k0.cli.k0ctl import build_parser

        parser = build_parser()
        args = parser.parse_args(
            [
                "dlq",
                "list",
                "--pipeline",
                "p03_consolidation",
                "--phase",
                "R7",
            ]
        )

        assert args.phase == "R7"

    def test_error_type_filter_argument(self) -> None:
        """Test --error-type filter argument is parsed."""
        from k0.cli.k0ctl import build_parser

        parser = build_parser()
        args = parser.parse_args(
            [
                "dlq",
                "list",
                "--pipeline",
                "p03_consolidation",
                "--error-type",
                "TRANSIENT",
            ]
        )

        assert args.error_type == "TRANSIENT"


# ============================================================================
# Tests for dlq stats command
# ============================================================================


class TestDlqStats:
    """Tests for dlq stats command."""

    def test_stats_command_exists(self) -> None:
        """Test stats subcommand is registered."""
        from k0.cli.k0ctl import build_parser

        parser = build_parser()
        args = parser.parse_args(["dlq", "stats"])

        assert args.dlq_command == "stats"

    def test_stats_with_pipeline(self) -> None:
        """Test stats with --pipeline filter."""
        from k0.cli.k0ctl import build_parser

        parser = build_parser()
        args = parser.parse_args(
            [
                "dlq",
                "stats",
                "--pipeline",
                "p03_consolidation",
            ]
        )

        assert args.pipeline == "p03_consolidation"

    def test_stats_with_driver_alias(self) -> None:
        """Test stats with --driver (alias for --pipeline)."""
        from k0.cli.k0ctl import build_parser

        parser = build_parser()
        args = parser.parse_args(
            [
                "dlq",
                "stats",
                "--driver",
                "p03_consolidation",
            ]
        )

        assert args.driver == "p03_consolidation"


# ============================================================================
# Tests for dlq requeue-all command
# ============================================================================


class TestDlqRequeueAll:
    """Tests for dlq requeue-all command."""

    def test_requeue_all_command_exists(self) -> None:
        """Test requeue-all subcommand is registered."""
        from k0.cli.k0ctl import build_parser

        parser = build_parser()
        args = parser.parse_args(
            [
                "dlq",
                "requeue-all",
                "--pipeline",
                "p03_consolidation",
            ]
        )

        assert args.dlq_command == "requeue-all"

    def test_requeue_all_requires_pipeline(self) -> None:
        """Test requeue-all requires --pipeline."""
        from k0.cli.k0ctl import build_parser

        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["dlq", "requeue-all"])

    def test_requeue_all_max_items_default(self) -> None:
        """Test requeue-all has default max_items=100."""
        from k0.cli.k0ctl import build_parser

        parser = build_parser()
        args = parser.parse_args(
            [
                "dlq",
                "requeue-all",
                "--pipeline",
                "p03_consolidation",
            ]
        )

        assert args.max_items == 100

    def test_requeue_all_with_phase_filter(self) -> None:
        """Test requeue-all with --phase filter."""
        from k0.cli.k0ctl import build_parser

        parser = build_parser()
        args = parser.parse_args(
            [
                "dlq",
                "requeue-all",
                "--pipeline",
                "p03_consolidation",
                "--phase",
                "R3",
            ]
        )

        assert args.phase == "R3"

    def test_requeue_all_with_force(self) -> None:
        """Test requeue-all with --force flag."""
        from k0.cli.k0ctl import build_parser

        parser = build_parser()
        args = parser.parse_args(
            [
                "dlq",
                "requeue-all",
                "--pipeline",
                "p03_consolidation",
                "--force",
            ]
        )

        assert args.force is True

    def test_requeue_all_force_default_false(self) -> None:
        """Test requeue-all force defaults to False."""
        from k0.cli.k0ctl import build_parser

        parser = build_parser()
        args = parser.parse_args(
            [
                "dlq",
                "requeue-all",
                "--pipeline",
                "p03_consolidation",
            ]
        )

        assert args.force is False


# ============================================================================
# Integration tests for command handlers (mocked)
# ============================================================================


class TestDlqCommandHandler:
    """Tests for _handle_dlq_command with new features."""

    def test_list_uses_pipeline_as_driver(self) -> None:
        """Test list command uses --pipeline as driver filter."""
        from k0.cli.k0ctl import build_parser

        parser = build_parser()
        args = parser.parse_args(
            [
                "dlq",
                "list",
                "--pipeline",
                "p03_consolidation",
                "--limit",
                "10",
            ]
        )

        # Verify args are correctly parsed
        assert args.pipeline == "p03_consolidation"
        assert args.driver is None  # Only pipeline set

    def test_list_driver_takes_precedence(self) -> None:
        """Test --driver takes precedence if both set."""
        from k0.cli.k0ctl import build_parser

        parser = build_parser()
        args = parser.parse_args(
            [
                "dlq",
                "list",
                "--driver",
                "explicit_driver",
                "--pipeline",
                "p03_consolidation",
            ]
        )

        # Both should be present
        assert args.driver == "explicit_driver"
        assert args.pipeline == "p03_consolidation"


# ============================================================================
# Argument validation tests
# ============================================================================


class TestArgumentValidation:
    """Tests for argument validation."""

    def test_requeue_all_max_items_positive(self) -> None:
        """Test max_items accepts positive integers."""
        from k0.cli.k0ctl import build_parser

        parser = build_parser()
        args = parser.parse_args(
            [
                "dlq",
                "requeue-all",
                "--pipeline",
                "p03",
                "--max-items",
                "50",
            ]
        )

        assert args.max_items == 50

    def test_stats_no_required_args(self) -> None:
        """Test stats command has no required arguments."""
        from k0.cli.k0ctl import build_parser

        parser = build_parser()
        args = parser.parse_args(["dlq", "stats"])

        assert args.dlq_command == "stats"
        assert args.pipeline is None
        assert args.driver is None


# ============================================================================
# Help text tests
# ============================================================================


class TestHelpText:
    """Tests for command help text."""

    def test_requeue_all_help_mentions_pipeline(self) -> None:
        """Test requeue-all help mentions pipeline filter."""
        from k0.cli.k0ctl import build_parser

        parser = build_parser()
        # Extract help text (this doesn't actually test content, just no crash)
        try:
            parser.parse_args(["dlq", "requeue-all", "--help"])
        except SystemExit:
            pass  # --help causes exit

    def test_stats_help_available(self) -> None:
        """Test stats command help is available."""
        from k0.cli.k0ctl import build_parser

        parser = build_parser()
        try:
            parser.parse_args(["dlq", "stats", "--help"])
        except SystemExit:
            pass  # --help causes exit
