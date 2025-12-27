"""Tests for k0.cli.k0ctl module."""

from __future__ import annotations

import argparse
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from k0.automation.migrate import MigrationError
from k0.cli.k0ctl import (
    ServeOptions,
    _compose_overrides,
    _handle_db_command,
    _handle_dlq_command,
    _handle_key_command,
    _handle_replay_command,
    _handle_schema_command,
    _handle_snapshot_command,
    _parse_override_pair,
    _provision_device,
    _resolve_serve_options,
    build_parser,
    main,
)


class TestServeOptions:
    """Test ServeOptions dataclass."""

    def test_serve_options_creation(self) -> None:
        """Test ServeOptions can be created."""
        options = ServeOptions(
            host="localhost", port=8000, log_level="info", timeout_graceful_shutdown=30.0
        )
        assert options.host == "localhost"
        assert options.port == 8000
        assert options.log_level == "info"
        assert options.timeout_graceful_shutdown == 30.0

    def test_serve_options_frozen(self) -> None:
        """Test ServeOptions is frozen."""
        options = ServeOptions(
            host="localhost", port=8000, log_level="info", timeout_graceful_shutdown=30.0
        )
        with pytest.raises(AttributeError):
            options.host = "127.0.0.1"


class TestBuildParser:
    """Test argument parser construction."""

    def test_build_parser_basic(self) -> None:
        """Test basic parser construction."""
        parser = build_parser()
        assert isinstance(parser, argparse.ArgumentParser)
        assert "K0 kernel control surface" in (parser.description or "")

    def test_build_parser_config_argument(self) -> None:
        """Test config argument parsing."""
        parser = build_parser()
        args = parser.parse_args(["--config", "test.yaml", "serve"])
        assert args.config == Path("test.yaml")
        assert args.command == "serve"

    def test_build_parser_serve_command(self) -> None:
        """Test serve command parsing."""
        parser = build_parser()
        args = parser.parse_args(["serve", "--host", "127.0.0.1", "--port", "9000"])
        assert args.command == "serve"
        assert args.host == "127.0.0.1"
        assert args.port == 9000

    def test_build_parser_migrate_command(self) -> None:
        """Test migrate command parsing."""
        parser = build_parser()
        args = parser.parse_args(["migrate", "--database", "test.db", "--dry-run"])
        assert args.command == "migrate"
        assert str(args.database) == "test.db"
        assert args.dry_run is True


class TestMainFunction:
    """Test main function."""

    @patch("k0.cli.k0ctl.configure_structured_logging")
    @patch("k0.cli.k0ctl.KernelSettings.load")
    def test_main_no_command(self, mock_load: MagicMock, mock_logging: MagicMock) -> None:
        """Test main with no command provided."""
        with patch("k0.cli.k0ctl.build_parser") as mock_build_parser:
            mock_parser = MagicMock()
            mock_parser.parse_args.return_value = MagicMock(command=None)
            mock_build_parser.return_value = mock_parser

            result = main([])
            assert result == 1
            mock_parser.print_help.assert_called_once()

    @patch("k0.cli.k0ctl.configure_structured_logging")
    @patch("k0.cli.k0ctl.KernelSettings.load")
    @patch("k0.cli.k0ctl._resolve_serve_options")
    @patch("k0.cli.k0ctl._default_serve_runner")
    def test_main_serve_command(
        self,
        mock_runner: MagicMock,
        mock_resolve: MagicMock,
        mock_load: MagicMock,
        mock_logging: MagicMock,
    ) -> None:
        """Test main with serve command."""
        mock_settings = MagicMock()
        mock_load.return_value = mock_settings
        mock_resolve.return_value = MagicMock()
        mock_runner.return_value = 0

        with patch("k0.cli.k0ctl.build_parser") as mock_build_parser:
            mock_parser = MagicMock()
            mock_args = MagicMock()
            mock_args.command = "serve"
            mock_args.overrides = None
            mock_parser.parse_args.return_value = mock_args
            mock_build_parser.return_value = mock_parser

            result = main(["serve"])
            assert result == 0
            mock_runner.assert_called_once()

    @patch("k0.cli.k0ctl.configure_structured_logging")
    @patch("k0.cli.k0ctl.KernelSettings.load")
    @patch("k0.cli.k0ctl.apply_migrations")
    @patch("k0.cli.k0ctl._report_migration_results")
    def test_main_migrate_command(
        self,
        mock_report: MagicMock,
        mock_apply: MagicMock,
        mock_load: MagicMock,
        mock_logging: MagicMock,
    ) -> None:
        """Test main with migrate command."""
        mock_settings = MagicMock()
        mock_load.return_value = mock_settings
        mock_apply.return_value = []

        with patch("k0.cli.k0ctl.build_parser") as mock_build_parser:
            mock_parser = MagicMock()
            mock_args = MagicMock()
            mock_args.command = "migrate"
            mock_args.database = None
            mock_args.migrations_dir = None
            mock_args.overrides = None
            mock_parser.parse_args.return_value = mock_args
            mock_build_parser.return_value = mock_parser

            with patch("k0.cli.k0ctl._get_database_path", return_value="test.db"):
                result = main(["migrate"])
                assert result == 0
                mock_apply.assert_called_once()
                mock_report.assert_called_once()

    @patch("k0.cli.k0ctl.configure_structured_logging")
    @patch("k0.cli.k0ctl.KernelSettings.load")
    @patch("k0.cli.k0ctl.apply_migrations", side_effect=MigrationError("Migration failed"))
    def test_main_migrate_command_error(
        self, mock_apply: MagicMock, mock_load: MagicMock, mock_logging: MagicMock
    ) -> None:
        """Test main with migrate command that fails."""
        mock_settings = MagicMock()
        mock_load.return_value = mock_settings

        with patch("k0.cli.k0ctl.build_parser") as mock_build_parser:
            mock_parser = MagicMock()
            mock_args = MagicMock()
            mock_args.command = "migrate"
            mock_args.database = None
            mock_args.migrations_dir = None
            mock_args.overrides = None
            mock_parser.parse_args.return_value = mock_args
            mock_build_parser.return_value = mock_parser

            with patch("k0.cli.k0ctl._get_database_path", return_value="test.db"):
                result = main(["migrate"])
                assert result == 2
                mock_apply.assert_called_once()

    @patch("k0.cli.k0ctl.configure_structured_logging")
    @patch("k0.cli.k0ctl.KernelSettings.load")
    def test_main_invalid_override(self, mock_load: MagicMock, mock_logging: MagicMock) -> None:
        """Test main with invalid override."""
        with patch("k0.cli.k0ctl.build_parser") as mock_build_parser:
            with patch("k0.cli.k0ctl._compose_overrides", side_effect=ValueError("invalid")):
                mock_parser = MagicMock()
                mock_args = MagicMock()
                mock_args.overrides = ["invalid=value"]
                mock_parser.parse_args.return_value = mock_args
                mock_build_parser.return_value = mock_parser

                result = main(["serve"])
                assert result == 2

    @patch("k0.cli.k0ctl.configure_structured_logging")
    @patch("k0.cli.k0ctl.KernelSettings.load", side_effect=Exception("load failed"))
    def test_main_config_load_error(self, mock_load: MagicMock, mock_logging: MagicMock) -> None:
        """Test main with config load error."""
        with patch("k0.cli.k0ctl.build_parser") as mock_build_parser:
            mock_parser = MagicMock()
            mock_args = MagicMock()
            mock_args.overrides = None
            mock_parser.parse_args.return_value = mock_args
            mock_build_parser.return_value = mock_parser

            result = main(["serve"])
            assert result == 2

    @patch("k0.cli.k0ctl.configure_structured_logging")
    @patch("k0.cli.k0ctl.KernelSettings.load")
    @patch("k0.cli.k0ctl.configure_pool")
    @patch("k0.cli.k0ctl.shutdown_pool")
    @patch("k0.cli.k0ctl.SchemaRegistry")
    def test_main_schema_command(
        self,
        mock_registry_class: MagicMock,
        mock_shutdown: MagicMock,
        mock_configure: MagicMock,
        mock_load: MagicMock,
        mock_logging: MagicMock,
    ) -> None:
        """Test main with schema command."""
        mock_settings = MagicMock()
        mock_load.return_value = mock_settings

        mock_registry = MagicMock()
        mock_registry_class.return_value = mock_registry
        mock_registry.records_for_uri.return_value = []

        with patch("k0.cli.k0ctl.build_parser") as mock_build_parser:
            mock_parser = MagicMock()
            mock_args = MagicMock()
            mock_args.command = "schema"
            mock_args.schema_command = "audit"
            mock_args.database = None
            mock_args.overrides = None
            mock_args.uri = "test://schema"
            mock_args.version = "1.0"
            mock_args.status = None
            mock_parser.parse_args.return_value = mock_args
            mock_build_parser.return_value = mock_parser

            with patch("k0.cli.k0ctl._get_database_path", return_value="test.db"):
                result = main(["schema", "audit", "--uri", "test://schema", "--version", "1.0"])
                assert result == 0
                mock_registry.get_audit_trail.assert_called_once()

    @patch("k0.cli.k0ctl.configure_structured_logging")
    @patch("k0.cli.k0ctl.KernelSettings.load")
    @patch("k0.cli.k0ctl._provision_device")
    def test_main_provision_command(
        self, mock_provision: MagicMock, mock_load: MagicMock, mock_logging: MagicMock
    ) -> None:
        """Test main with provision command."""
        mock_settings = MagicMock()
        mock_load.return_value = mock_settings

        with patch("k0.cli.k0ctl.build_parser") as mock_build_parser:
            mock_parser = MagicMock()
            mock_args = MagicMock()
            mock_args.command = "provision"
            mock_args.database = None
            mock_args.overrides = None
            mock_args.tenant_id = "tenant1"
            mock_args.space_id = "space1"
            mock_args.device_id = "device1"
            mock_args.mls_group_id = "group1"
            mock_args.key_version = 1
            mock_args.verify_key = "key"
            mock_args.provisioned_ts = None
            mock_parser.parse_args.return_value = mock_args
            mock_build_parser.return_value = mock_parser

            with patch("k0.cli.k0ctl._get_database_path", return_value="test.db"):
                with patch("k0.cli.k0ctl._resolve_timestamp", return_value=1234567890):
                    result = main(
                        [
                            "provision",
                            "--tenant-id",
                            "tenant1",
                            "--space-id",
                            "space1",
                            "--device-id",
                            "device1",
                            "--mls-group-id",
                            "group1",
                            "--key-version",
                            "1",
                            "--verify-key",
                            "key",
                        ]
                    )
                    assert result == 0
                    mock_provision.assert_called_once()

    @patch("k0.cli.k0ctl.configure_structured_logging")
    @patch("k0.cli.k0ctl.KernelSettings.load")
    @patch("k0.cli.k0ctl._provision_device", side_effect=Exception("Provisioning failed"))
    def test_main_provision_command_error(
        self, mock_provision: MagicMock, mock_load: MagicMock, mock_logging: MagicMock
    ) -> None:
        """Test main with provision command that fails."""
        mock_settings = MagicMock()
        mock_load.return_value = mock_settings

        with patch("k0.cli.k0ctl.build_parser") as mock_build_parser:
            mock_parser = MagicMock()
            mock_args = MagicMock()
            mock_args.command = "provision"
            mock_args.database = None
            mock_args.overrides = None
            mock_args.tenant_id = "tenant1"
            mock_args.space_id = "space1"
            mock_args.device_id = "device1"
            mock_args.mls_group_id = "group1"
            mock_args.key_version = 1
            mock_args.verify_key = "key"
            mock_args.provisioned_ts = None
            mock_parser.parse_args.return_value = mock_args
            mock_build_parser.return_value = mock_parser

            with patch("k0.cli.k0ctl._get_database_path", return_value="test.db"):
                with patch("k0.cli.k0ctl._resolve_timestamp", return_value=1234567890):
                    result = main(
                        [
                            "provision",
                            "--tenant-id",
                            "tenant1",
                            "--space-id",
                            "space1",
                            "--device-id",
                            "device1",
                            "--mls-group-id",
                            "group1",
                            "--key-version",
                            "1",
                            "--verify-key",
                            "key",
                        ]
                    )
                    assert result == 2
                    mock_provision.assert_called_once()

    @patch("k0.cli.k0ctl.configure_structured_logging")
    @patch("k0.cli.k0ctl.KernelSettings.load")
    @patch("k0.cli.k0ctl.configure_pool")
    @patch("k0.cli.k0ctl.shutdown_pool")
    @patch("k0.cli.k0ctl.ProvisioningLedger")
    def test_main_key_command(
        self,
        mock_ledger_class: MagicMock,
        mock_shutdown: MagicMock,
        mock_configure: MagicMock,
        mock_load: MagicMock,
        mock_logging: MagicMock,
    ) -> None:
        """Test main with key command."""
        mock_settings = MagicMock()
        mock_load.return_value = mock_settings

        mock_ledger = MagicMock()
        mock_ledger_class.return_value = mock_ledger
        mock_ledger.get_keys.return_value = []

        with patch("k0.cli.k0ctl.build_parser") as mock_build_parser:
            mock_parser = MagicMock()
            mock_args = MagicMock()
            mock_args.command = "key"
            mock_args.key_command = "list"
            mock_args.database = None
            mock_args.overrides = None
            mock_args.device_id = "device1"
            mock_args.key_state = "ALL"
            mock_parser.parse_args.return_value = mock_args
            mock_build_parser.return_value = mock_parser

            with patch("k0.cli.k0ctl._get_database_path", return_value="test.db"):
                result = main(["key", "list", "--device-id", "device1"])
                assert result == 0
                mock_ledger.get_keys.assert_called_once_with("device1", states=None)

    @patch("k0.cli.k0ctl.configure_structured_logging")
    @patch("k0.cli.k0ctl.KernelSettings.load")
    def test_main_key_command_no_subcommand(
        self, mock_load: MagicMock, mock_logging: MagicMock
    ) -> None:
        """Test main with key command but no subcommand."""
        mock_settings = MagicMock()
        mock_load.return_value = mock_settings

        with patch("k0.cli.k0ctl.build_parser") as mock_build_parser:
            mock_parser = MagicMock()
            mock_args = MagicMock()
            mock_args.command = "key"
            mock_args.key_command = None  # No subcommand
            mock_args.database = None
            mock_args.overrides = None
            mock_parser.parse_args.return_value = mock_args
            mock_build_parser.return_value = mock_parser

            result = main(["key"])
            assert result == 1

    @patch("k0.cli.k0ctl.configure_structured_logging")
    @patch("k0.cli.k0ctl.KernelSettings.load")
    def test_main_schema_command_no_subcommand(
        self, mock_load: MagicMock, mock_logging: MagicMock
    ) -> None:
        """Test main with schema command but no subcommand."""
        mock_settings = MagicMock()
        mock_load.return_value = mock_settings

        with patch("k0.cli.k0ctl.build_parser") as mock_build_parser:
            mock_parser = MagicMock()
            mock_args = MagicMock()
            mock_args.command = "schema"
            mock_args.schema_command = None  # No subcommand
            mock_args.database = None
            mock_args.overrides = None
            mock_parser.parse_args.return_value = mock_args
            mock_build_parser.return_value = mock_parser

            result = main(["schema"])
            assert result == 1

    @patch("k0.cli.k0ctl.configure_structured_logging")
    @patch("k0.cli.k0ctl.KernelSettings.load")
    def test_main_snapshot_command_no_subcommand(
        self, mock_load: MagicMock, mock_logging: MagicMock
    ) -> None:
        """Test main with snapshot command but no subcommand."""
        mock_settings = MagicMock()
        mock_load.return_value = mock_settings

        with patch("k0.cli.k0ctl.build_parser") as mock_build_parser:
            mock_parser = MagicMock()
            mock_args = MagicMock()
            mock_args.command = "snapshot"
            mock_args.snapshot_command = None  # No subcommand
            mock_args.database = None
            mock_args.overrides = None
            mock_parser.parse_args.return_value = mock_args
            mock_build_parser.return_value = mock_parser

            result = main(["snapshot"])
            assert result == 1

    @patch("k0.cli.k0ctl.configure_structured_logging")
    @patch("k0.cli.k0ctl.KernelSettings.load")
    def test_main_dlq_command_no_subcommand(
        self, mock_load: MagicMock, mock_logging: MagicMock
    ) -> None:
        """Test main with dlq command but no subcommand."""
        mock_settings = MagicMock()
        mock_load.return_value = mock_settings

        with patch("k0.cli.k0ctl.build_parser") as mock_build_parser:
            mock_parser = MagicMock()
            mock_args = MagicMock()
            mock_args.command = "dlq"
            mock_args.dlq_command = None  # No subcommand
            mock_args.database = None
            mock_args.overrides = None
            mock_parser.parse_args.return_value = mock_args
            mock_build_parser.return_value = mock_parser

            result = main(["dlq"])
            assert result == 1

    @patch("k0.cli.k0ctl.configure_structured_logging")
    @patch("k0.cli.k0ctl.KernelSettings.load")
    def test_main_db_command_no_subcommand(
        self, mock_load: MagicMock, mock_logging: MagicMock
    ) -> None:
        """Test main with db command but no subcommand."""
        mock_settings = MagicMock()
        mock_load.return_value = mock_settings

        with patch("k0.cli.k0ctl.build_parser") as mock_build_parser:
            mock_parser = MagicMock()
            mock_args = MagicMock()
            mock_args.command = "db"
            mock_args.db_command = None  # No subcommand
            mock_args.database = None
            mock_args.overrides = None
            mock_parser.parse_args.return_value = mock_args
            mock_build_parser.return_value = mock_parser

            result = main(["db"])
            assert result == 1

    @patch("k0.cli.k0ctl.configure_structured_logging")
    @patch("k0.cli.k0ctl.KernelSettings.load")
    @patch("k0.cli.k0ctl._build_operational_instrumentation")
    @patch("k0.cli.k0ctl.SnapshotScheduler")
    def test_main_snapshot_command(
        self,
        mock_scheduler_class: MagicMock,
        mock_build_inst: MagicMock,
        mock_load: MagicMock,
        mock_logging: MagicMock,
    ) -> None:
        """Test main with snapshot command."""
        mock_settings = MagicMock()
        mock_load.return_value = mock_settings

        mock_metrics, mock_observability = MagicMock(), MagicMock()
        mock_build_inst.return_value = (mock_metrics, mock_observability)

        mock_scheduler = MagicMock()
        mock_scheduler_class.return_value = mock_scheduler

        with patch("k0.cli.k0ctl.build_parser") as mock_build_parser:
            mock_parser = MagicMock()
            mock_args = MagicMock()
            mock_args.command = "snapshot"
            mock_args.snapshot_command = "create"
            mock_args.database = None
            mock_args.overrides = None
            mock_args.output_dir = Path("/output")
            mock_args.snapshot_id = "snap-123"
            mock_args.dry_run = False
            mock_parser.parse_args.return_value = mock_args
            mock_build_parser.return_value = mock_parser

            with patch("k0.cli.k0ctl._get_database_path", return_value="test.db"):
                result = main(
                    ["snapshot", "create", "--output-dir", "/output", "--snapshot-id", "snap-123"]
                )
                assert result == 0
                mock_scheduler.create_snapshot.assert_called_once()

    @patch("k0.cli.k0ctl.configure_structured_logging")
    @patch("k0.cli.k0ctl.KernelSettings.load")
    @patch("k0.cli.k0ctl.configure_pool")
    @patch("k0.cli.k0ctl.shutdown_pool")
    @patch("k0.cli.k0ctl._build_operational_instrumentation")
    @patch("k0.cli.k0ctl.SchemaRegistry")
    @patch("k0.cli.k0ctl.Replayer")
    def test_main_replay_command(
        self,
        mock_replayer_class: MagicMock,
        mock_registry_class: MagicMock,
        mock_build_inst: MagicMock,
        mock_shutdown: MagicMock,
        mock_configure: MagicMock,
        mock_load: MagicMock,
        mock_logging: MagicMock,
    ) -> None:
        """Test main with replay command."""
        mock_settings = MagicMock()
        mock_load.return_value = mock_settings

        mock_metrics, mock_observability = MagicMock(), MagicMock()
        mock_build_inst.return_value = (mock_metrics, mock_observability)

        mock_replayer = MagicMock()
        mock_replayer_class.return_value = mock_replayer
        mock_result = MagicMock()
        mock_result.processed = 100
        mock_result.last_position = "pos-100"
        mock_result.duration_seconds = 1.5
        mock_result.parity_failures = 0
        mock_replayer.run.return_value = mock_result

        with patch("k0.cli.k0ctl.build_parser") as mock_build_parser:
            mock_parser = MagicMock()
            mock_args = MagicMock()
            mock_args.command = "replay"
            mock_args.database = None
            mock_args.overrides = None
            mock_args.from_position = None
            mock_args.tenant_id = None
            mock_args.space_id = None
            mock_args.dry_run = False
            mock_parser.parse_args.return_value = mock_args
            mock_build_parser.return_value = mock_parser

            with patch("k0.cli.k0ctl._get_database_path", return_value="test.db"):
                result = main(["replay"])
                assert result == 0
                mock_replayer.run.assert_called_once()

    @patch("k0.cli.k0ctl.configure_structured_logging")
    @patch("k0.cli.k0ctl.KernelSettings.load")
    @patch("k0.cli.k0ctl.configure_pool")
    @patch("k0.cli.k0ctl.shutdown_pool")
    @patch("k0.cli.k0ctl.DeadLetterQueue")
    @patch("k0.cli.k0ctl.OutboxStore")
    def test_main_dlq_command(
        self,
        mock_outbox_class: MagicMock,
        mock_dlq_class: MagicMock,
        mock_shutdown: MagicMock,
        mock_configure: MagicMock,
        mock_load: MagicMock,
        mock_logging: MagicMock,
    ) -> None:
        """Test main with dlq command."""
        mock_settings = MagicMock()
        mock_load.return_value = mock_settings

        mock_dlq = MagicMock()
        mock_dlq_class.return_value = mock_dlq
        mock_dlq.list_pending.return_value = []

        with patch("k0.cli.k0ctl.build_parser") as mock_build_parser:
            mock_parser = MagicMock()
            mock_args = MagicMock()
            mock_args.command = "dlq"
            mock_args.dlq_command = "list"
            mock_args.database = None
            mock_args.overrides = None
            mock_args.limit = 10
            mock_args.state = None
            mock_args.tenant = None
            mock_args.space = None
            mock_args.driver = None
            mock_parser.parse_args.return_value = mock_args
            mock_build_parser.return_value = mock_parser

            with patch("k0.cli.k0ctl._get_database_path", return_value="test.db"):
                result = main(["dlq", "list", "--limit", "10"])
                assert result == 0
                mock_dlq.list_pending.assert_called_once()

    @patch("k0.cli.k0ctl.configure_structured_logging")
    @patch("k0.cli.k0ctl.KernelSettings.load")
    @patch("k0.cli.k0ctl._handle_db_command")
    def test_main_db_command(
        self, mock_handle: MagicMock, mock_load: MagicMock, mock_logging: MagicMock
    ) -> None:
        """Test main with db command."""
        mock_settings = MagicMock()
        mock_load.return_value = mock_settings
        mock_handle.return_value = 0

        with patch("k0.cli.k0ctl.build_parser") as mock_build_parser:
            mock_parser = MagicMock()
            mock_args = MagicMock()
            mock_args.command = "db"
            mock_args.db_command = "current"
            mock_args.overrides = None
            mock_parser.parse_args.return_value = mock_args
            mock_build_parser.return_value = mock_parser

            result = main(["db", "current"])
            assert result == 0
            mock_handle.assert_called_once()

    @patch("k0.cli.k0ctl.configure_structured_logging")
    @patch("k0.cli.k0ctl.KernelSettings.load")
    def test_main_unknown_command(self, mock_load: MagicMock, mock_logging: MagicMock) -> None:
        """Test main with unknown command."""
        mock_settings = MagicMock()
        mock_load.return_value = mock_settings

        with patch("k0.cli.k0ctl.build_parser") as mock_build_parser:
            mock_parser = MagicMock()
            mock_args = MagicMock()
            mock_args.command = "unknown"
            mock_args.overrides = None
            mock_parser.parse_args.return_value = mock_args
            mock_build_parser.return_value = mock_parser

            result = main(["unknown"])
            assert result == 2


class TestHandleSchemaCommand:
    """Test _handle_schema_command function."""

    @patch("k0.cli.k0ctl.configure_pool")
    @patch("k0.cli.k0ctl.shutdown_pool")
    @patch("k0.cli.k0ctl.SchemaRegistry")
    def test_handle_schema_register_command(
        self, mock_registry_class: MagicMock, mock_shutdown: MagicMock, mock_configure: MagicMock
    ) -> None:
        """Test schema register subcommand."""
        mock_registry = MagicMock()
        mock_registry_class.return_value = mock_registry
        mock_record = MagicMock()
        mock_record.uri = "test://schema"
        mock_record.version = "1.0.0"
        mock_record.status = "REGISTERED"
        mock_registry.register.return_value = mock_record
        mock_registry.promote.return_value = mock_record

        args = MagicMock()
        args.schema_command = "register"
        args.uri = "test://schema"
        args.version = "1.0.0"
        args.sha256 = "abc123"
        args.status = "REGISTERED"
        args.activate = False

        with patch("k0.cli.k0ctl._log_schema_state"):
            result = _handle_schema_command(Path("test.db"), args)
            assert result == 0
            mock_registry.register.assert_called_once()
            mock_registry.load.assert_called_once()

    @patch("k0.cli.k0ctl.configure_pool")
    @patch("k0.cli.k0ctl.shutdown_pool")
    @patch("k0.cli.k0ctl.SchemaRegistry")
    def test_handle_schema_promote_command(
        self, mock_registry_class: MagicMock, mock_shutdown: MagicMock, mock_configure: MagicMock
    ) -> None:
        """Test schema promote subcommand."""
        mock_registry = MagicMock()
        mock_registry_class.return_value = mock_registry
        mock_record = MagicMock()
        mock_record.uri = "test://schema"
        mock_record.version = "1.0.0"
        mock_registry.promote.return_value = mock_record

        args = MagicMock()
        args.schema_command = "promote"
        args.uri = "test://schema"
        args.version = "1.0.0"

        with patch("k0.cli.k0ctl._log_schema_state"):
            result = _handle_schema_command(Path("test.db"), args)
            assert result == 0
            mock_registry.promote.assert_called_once_with("test://schema", "1.0.0")

    @patch("k0.cli.k0ctl.configure_pool")
    @patch("k0.cli.k0ctl.shutdown_pool")
    @patch("k0.cli.k0ctl.SchemaRegistry")
    def test_handle_schema_block_command(
        self, mock_registry_class: MagicMock, mock_shutdown: MagicMock, mock_configure: MagicMock
    ) -> None:
        """Test schema block subcommand."""
        mock_registry = MagicMock()
        mock_registry_class.return_value = mock_registry
        mock_record = MagicMock()
        mock_record.uri = "test://schema"
        mock_record.version = "1.0.0"
        mock_record.operator_id = "admin"
        mock_record.blocked_reason = "security"
        mock_registry.block.return_value = mock_record

        args = MagicMock()
        args.schema_command = "block"
        args.uri = "test://schema"
        args.version = "1.0.0"
        args.operator_id = "admin"
        args.reason = "security"

        with patch("k0.cli.k0ctl._log_schema_state"):
            result = _handle_schema_command(Path("test.db"), args)
            assert result == 0
            mock_registry.block.assert_called_once_with(
                "test://schema", "1.0.0", operator_id="admin", reason="security"
            )

    @patch("k0.cli.k0ctl.configure_pool")
    @patch("k0.cli.k0ctl.shutdown_pool")
    @patch("k0.cli.k0ctl.SchemaRegistry")
    def test_handle_schema_audit_command(
        self, mock_registry_class: MagicMock, mock_shutdown: MagicMock, mock_configure: MagicMock
    ) -> None:
        """Test schema audit subcommand."""
        mock_registry = MagicMock()
        mock_registry_class.return_value = mock_registry
        mock_record = MagicMock()
        mock_record.uri = "test://schema"
        mock_record.version = "1.0.0"
        mock_record.status = "ACTIVE"
        mock_record.sha256 = "abc123"
        mock_record.operator_id = None
        mock_registry.get_audit_trail.return_value = [mock_record]

        args = MagicMock()
        args.schema_command = "audit"
        args.uri = "test://schema"
        args.version = "1.0.0"
        args.status = "ACTIVE"

        result = _handle_schema_command(Path("test.db"), args)
        assert result == 0
        mock_registry.get_audit_trail.assert_called_once_with(
            uri="test://schema", version="1.0.0", status="ACTIVE"
        )

    @patch("k0.cli.k0ctl.configure_pool")
    @patch("k0.cli.k0ctl.shutdown_pool")
    @patch("k0.cli.k0ctl.SchemaRegistry")
    def test_handle_schema_unknown_command(
        self, mock_registry_class: MagicMock, mock_shutdown: MagicMock, mock_configure: MagicMock
    ) -> None:
        """Test schema unknown subcommand."""
        mock_registry = MagicMock()
        mock_registry_class.return_value = mock_registry

        args = MagicMock()
        args.schema_command = "unknown"

        result = _handle_schema_command(Path("test.db"), args)
        assert result == 2

    @patch("k0.cli.k0ctl.configure_pool")
    @patch("k0.cli.k0ctl.shutdown_pool")
    @patch("k0.cli.k0ctl.SchemaRegistry")
    def test_handle_schema_command_exception(
        self, mock_registry_class: MagicMock, mock_shutdown: MagicMock, mock_configure: MagicMock
    ) -> None:
        """Test schema command with exception."""
        mock_registry = MagicMock()
        mock_registry.load.side_effect = ValueError("Registry load failed")
        mock_registry_class.return_value = mock_registry

        args = MagicMock()
        args.schema_command = "register"
        args.uri = "test://schema"
        args.version = "1.0"
        args.sha256 = "abc123"
        args.status = "DRAFT"
        args.activate = False

        result = _handle_schema_command(Path("test.db"), args)
        assert result == 2


class TestHandleKeyCommand:
    """Test _handle_key_command function."""

    @patch("k0.cli.k0ctl.configure_pool")
    @patch("k0.cli.k0ctl.shutdown_pool")
    @patch("k0.cli.k0ctl.ProvisioningLedger")
    @patch("k0.cli.k0ctl._resolve_timestamp")
    def test_handle_key_add_command(
        self,
        mock_resolve: MagicMock,
        mock_ledger_class: MagicMock,
        mock_shutdown: MagicMock,
        mock_configure: MagicMock,
    ) -> None:
        """Test key add subcommand."""
        mock_ledger = MagicMock()
        mock_ledger_class.return_value = mock_ledger
        mock_resolve.return_value = "2023-01-01T00:00:00"

        args = MagicMock()
        args.key_command = "add"
        args.device_id = "device1"
        args.key_version = "1"
        args.verify_key = "key123"
        args.key_state = "ACTIVE"
        args.registered_ts = None

        result = _handle_key_command(Path("test.db"), args, settings=MagicMock())
        assert result == 0
        mock_ledger.add_key.assert_called_once()

    @patch("k0.cli.k0ctl.configure_pool")
    @patch("k0.cli.k0ctl.shutdown_pool")
    @patch("k0.cli.k0ctl.ProvisioningLedger")
    def test_handle_key_list_command(
        self, mock_ledger_class: MagicMock, mock_shutdown: MagicMock, mock_configure: MagicMock
    ) -> None:
        """Test key list subcommand."""
        mock_ledger = MagicMock()
        mock_ledger_class.return_value = mock_ledger
        mock_key = MagicMock()
        mock_key.key_version = "1"
        mock_key.key_state = "ACTIVE"
        mock_key.registered_ts = "2023-01-01T00:00:00"
        mock_key.activated_ts = "2023-01-01T00:00:00"
        mock_key.grace_expires_ts = None
        mock_key.revocation_reason = None
        mock_ledger.get_keys.return_value = [mock_key]

        args = MagicMock()
        args.key_command = "list"
        args.device_id = "device1"
        args.key_state = "ALL"

        result = _handle_key_command(Path("test.db"), args, settings=MagicMock())
        assert result == 0
        mock_ledger.get_keys.assert_called_once_with("device1", states=None)

    @patch("k0.cli.k0ctl.configure_pool")
    @patch("k0.cli.k0ctl.shutdown_pool")
    @patch("k0.cli.k0ctl.ProvisioningLedger")
    @patch("k0.cli.k0ctl.replace")
    def test_handle_key_revoke_command(
        self,
        mock_replace: MagicMock,
        mock_ledger_class: MagicMock,
        mock_shutdown: MagicMock,
        mock_configure: MagicMock,
    ) -> None:
        """Test key revoke subcommand."""
        mock_ledger = MagicMock()
        mock_ledger_class.return_value = mock_ledger
        mock_key = MagicMock()
        mock_key.key_version = "1"
        mock_key.key_state = "ACTIVE"
        mock_ledger.get_keys.return_value = [mock_key]
        mock_replace.return_value = MagicMock()

        args = MagicMock()
        args.key_command = "revoke"
        args.device_id = "device1"
        args.key_version = "1"
        args.revocation_reason = "compromised"

        result = _handle_key_command(Path("test.db"), args, settings=MagicMock())
        assert result == 0
        mock_ledger.add_key.assert_called_once()

    @patch("k0.cli.k0ctl.configure_pool")
    @patch("k0.cli.k0ctl.shutdown_pool")
    @patch("k0.cli.k0ctl.ProvisioningLedger")
    @patch("k0.cli.k0ctl.replace")
    @patch("k0.cli.k0ctl.connection_scope")
    @patch("k0.cli.k0ctl.asyncio")
    def test_handle_key_activate_command(
        self,
        mock_asyncio: MagicMock,
        mock_connection_scope: MagicMock,
        mock_replace: MagicMock,
        mock_ledger_class: MagicMock,
        mock_shutdown: MagicMock,
        mock_configure: MagicMock,
    ) -> None:
        """Test key activate subcommand."""
        mock_ledger = MagicMock()
        mock_ledger_class.return_value = mock_ledger

        mock_key = MagicMock()
        mock_key.key_version = "2"
        mock_key.key_state = "REGISTERED"
        mock_ledger.get_keys.return_value = [mock_key]

        mock_replace.return_value = mock_key

        # Mock the async context manager
        mock_conn = MagicMock()
        mock_connection_scope.return_value.__aenter__ = MagicMock(return_value=mock_conn)
        mock_connection_scope.return_value.__aexit__ = MagicMock(return_value=None)

        mock_asyncio.run = MagicMock()

        args = MagicMock()
        args.key_command = "activate"
        args.device_id = "device1"
        args.key_version = "2"
        args.grace_hours = 24

        mock_settings = MagicMock()
        mock_settings.security.key_rotation_grace_window_hours = 24
        mock_settings.security.key_rotation_max_grace_hours = 168

        result = _handle_key_command(Path("test.db"), args, settings=mock_settings)
        assert result == 0
        mock_asyncio.run.assert_called_once()

    @patch("k0.cli.k0ctl.configure_pool")
    @patch("k0.cli.k0ctl.shutdown_pool")
    @patch("k0.cli.k0ctl.ProvisioningLedger")
    def test_handle_key_activate_grace_exceeds_max(
        self,
        mock_ledger_class: MagicMock,
        mock_shutdown: MagicMock,
        mock_configure: MagicMock,
    ) -> None:
        """Test key activate subcommand when grace hours exceed maximum."""
        mock_ledger = MagicMock()
        mock_ledger_class.return_value = mock_ledger

        args = MagicMock()
        args.key_command = "activate"
        args.device_id = "device1"
        args.key_version = "2"
        args.grace_hours = 200  # Exceeds max

        mock_settings = MagicMock()
        mock_settings.security.key_rotation_grace_window_hours = 24
        mock_settings.security.key_rotation_max_grace_hours = 168

        result = _handle_key_command(Path("test.db"), args, settings=mock_settings)
        assert result == 2

    @patch("k0.cli.k0ctl.configure_pool")
    @patch("k0.cli.k0ctl.shutdown_pool")
    @patch("k0.cli.k0ctl.ProvisioningLedger")
    def test_handle_key_activate_key_not_found(
        self,
        mock_ledger_class: MagicMock,
        mock_shutdown: MagicMock,
        mock_configure: MagicMock,
    ) -> None:
        """Test key activate subcommand when key not found."""
        mock_ledger = MagicMock()
        mock_ledger_class.return_value = mock_ledger

        # Return empty list - key not found
        mock_ledger.get_keys.return_value = []

        args = MagicMock()
        args.key_command = "activate"
        args.device_id = "device1"
        args.key_version = "2"
        args.grace_hours = 24

        mock_settings = MagicMock()
        mock_settings.security.key_rotation_grace_window_hours = 24
        mock_settings.security.key_rotation_max_grace_hours = 168

        result = _handle_key_command(Path("test.db"), args, settings=mock_settings)
        assert result == 2

    @patch("k0.cli.k0ctl.configure_pool")
    @patch("k0.cli.k0ctl.shutdown_pool")
    @patch("k0.cli.k0ctl.ProvisioningLedger")
    def test_handle_key_activate_revoked_key(
        self,
        mock_ledger_class: MagicMock,
        mock_shutdown: MagicMock,
        mock_configure: MagicMock,
    ) -> None:
        """Test key activate subcommand when key is revoked."""
        mock_ledger = MagicMock()
        mock_ledger_class.return_value = mock_ledger

        mock_key = MagicMock()
        mock_key.key_version = "2"
        mock_key.key_state = "REVOKED"
        mock_ledger.get_keys.return_value = [mock_key]

        args = MagicMock()
        args.key_command = "activate"
        args.device_id = "device1"
        args.key_version = "2"
        args.grace_hours = 24

        mock_settings = MagicMock()
        mock_settings.security.key_rotation_grace_window_hours = 24
        mock_settings.security.key_rotation_max_grace_hours = 168

        result = _handle_key_command(Path("test.db"), args, settings=mock_settings)
        assert result == 2

    @patch("k0.cli.k0ctl.configure_pool")
    @patch("k0.cli.k0ctl.shutdown_pool")
    @patch("k0.cli.k0ctl.ProvisioningLedger")
    def test_handle_key_unknown_command(
        self, mock_ledger_class: MagicMock, mock_shutdown: MagicMock, mock_configure: MagicMock
    ) -> None:
        """Test key unknown subcommand."""
        mock_ledger = MagicMock()
        mock_ledger_class.return_value = mock_ledger

        args = MagicMock()
        args.key_command = "unknown"

        result = _handle_key_command(Path("test.db"), args, settings=MagicMock())
        assert result == 2


class TestHandleSnapshotCommand:
    """Test _handle_snapshot_command function."""

    @patch("k0.cli.k0ctl.configure_pool")
    @patch("k0.cli.k0ctl.shutdown_pool")
    @patch("k0.cli.k0ctl.SnapshotScheduler")
    @patch("k0.cli.k0ctl._build_operational_instrumentation")
    def test_handle_snapshot_create_command(
        self,
        mock_build_inst: MagicMock,
        mock_scheduler_class: MagicMock,
        mock_shutdown: MagicMock,
        mock_configure: MagicMock,
    ) -> None:
        """Test snapshot create subcommand."""
        mock_metrics = MagicMock()
        mock_observability = MagicMock()
        mock_build_inst.return_value = (mock_metrics, mock_observability)

        mock_scheduler = MagicMock()
        mock_scheduler_class.return_value = mock_scheduler

        mock_manifest = MagicMock()
        mock_manifest.snapshot_id = "snap-123"
        mock_manifest.watermark = "wm-456"
        mock_manifest.begin_position = "pos-1"
        mock_manifest.commit_position = "pos-2"
        mock_manifest.artifact_path = Path("/path/to/artifact")
        mock_manifest.manifest_path = Path("/path/to/manifest")
        mock_scheduler.create_snapshot.return_value = mock_manifest

        args = MagicMock()
        args.snapshot_command = "create"
        args.output_dir = Path("/output")
        args.snapshot_id = "snap-123"
        args.dry_run = False

        result = _handle_snapshot_command(Path("test.db"), args, settings=MagicMock())
        assert result == 0
        mock_scheduler.create_snapshot.assert_called_once_with(
            output_dir=Path("/output"), snapshot_id="snap-123", dry_run=False
        )

    @patch("k0.cli.k0ctl.configure_pool")
    @patch("k0.cli.k0ctl.shutdown_pool")
    @patch("k0.cli.k0ctl.SnapshotScheduler")
    @patch("k0.cli.k0ctl._build_operational_instrumentation")
    def test_handle_snapshot_unknown_command(
        self,
        mock_build_inst: MagicMock,
        mock_scheduler_class: MagicMock,
        mock_shutdown: MagicMock,
        mock_configure: MagicMock,
    ) -> None:
        """Test snapshot unknown subcommand."""
        args = MagicMock()
        args.snapshot_command = "unknown"

        result = _handle_snapshot_command(Path("test.db"), args, settings=MagicMock())
        assert result == 2


class TestHandleDlqCommand:
    """Test _handle_dlq_command function."""

    @patch("k0.cli.k0ctl.configure_pool")
    @patch("k0.cli.k0ctl.shutdown_pool")
    @patch("k0.cli.k0ctl.DeadLetterQueue")
    @patch("k0.cli.k0ctl.OutboxStore")
    def test_handle_dlq_list_command(
        self,
        mock_outbox_class: MagicMock,
        mock_dlq_class: MagicMock,
        mock_shutdown: MagicMock,
        mock_configure: MagicMock,
    ) -> None:
        """Test dlq list subcommand."""
        mock_queue = MagicMock()
        mock_dlq_class.return_value = mock_queue
        mock_outbox = MagicMock()
        mock_outbox_class.return_value = mock_outbox

        mock_letter = MagicMock()
        mock_letter.id = "letter-1"
        mock_letter.state = "PENDING"
        mock_queue.list_pending.return_value = [mock_letter]

        args = MagicMock()
        args.dlq_command = "list"
        args.limit = 10
        args.state = None
        args.tenant = None
        args.space = None
        args.driver = None

        with patch("k0.cli.k0ctl._log_dead_letter"):
            result = _handle_dlq_command(Path("test.db"), args)
            assert result == 0
            mock_queue.list_pending.assert_called_once_with(
                limit=10, state=None, tenant_id=None, space_id=None, driver=None
            )

    @patch("k0.cli.k0ctl.configure_pool")
    @patch("k0.cli.k0ctl.shutdown_pool")
    @patch("k0.cli.k0ctl.DeadLetterQueue")
    @patch("k0.cli.k0ctl.OutboxStore")
    def test_handle_dlq_unknown_command(
        self,
        mock_outbox_class: MagicMock,
        mock_dlq_class: MagicMock,
        mock_shutdown: MagicMock,
        mock_configure: MagicMock,
    ) -> None:
        """Test dlq unknown subcommand."""
        mock_queue = MagicMock()
        mock_dlq_class.return_value = mock_queue
        mock_outbox = MagicMock()
        mock_outbox_class.return_value = mock_outbox

        args = MagicMock()
        args.dlq_command = "unknown"

        result = _handle_dlq_command(Path("test.db"), args)
        assert result == 2

    @patch("k0.cli.k0ctl.configure_pool")
    @patch("k0.cli.k0ctl.shutdown_pool")
    @patch("k0.cli.k0ctl.DeadLetterQueue")
    @patch("k0.cli.k0ctl.OutboxStore")
    @patch("k0.cli.k0ctl.asyncio")
    @patch("k0.cli.k0ctl.connection_scope")
    def test_handle_dlq_requeue_command(
        self,
        mock_connection_scope: MagicMock,
        mock_asyncio: MagicMock,
        mock_outbox_class: MagicMock,
        mock_dlq_class: MagicMock,
        mock_shutdown: MagicMock,
        mock_configure: MagicMock,
    ) -> None:
        """Test dlq requeue subcommand."""
        mock_queue = MagicMock()
        mock_dlq_class.return_value = mock_queue
        mock_outbox = MagicMock()
        mock_outbox_class.return_value = mock_outbox

        # Make enqueue and mark_requeued async
        mock_outbox.enqueue = AsyncMock()
        mock_queue.mark_requeued = AsyncMock()

        # Mock the dead letter entry
        mock_letter = MagicMock()
        mock_letter.id = "letter-1"
        mock_letter.state = "PENDING"
        mock_letter.wal_pos = "0/12345"
        mock_letter.tenant_id = "tenant1"
        mock_letter.space_id = "space1"
        mock_letter.driver = "driver1"
        mock_letter.op_kind = "INSERT"
        mock_letter.payload = b"test payload"
        mock_letter.fingerprint = "fp123"
        mock_letter.requeue_seq = 0
        mock_letter.reason = "test error"
        mock_queue.get.return_value = mock_letter

        # Mock async context manager
        mock_conn = MagicMock()
        mock_connection_scope.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_connection_scope.return_value.__aexit__ = AsyncMock(return_value=None)

        # Mock asyncio.run to actually execute the coroutine
        def run_side_effect(coro):
            # Simulate running the coroutine by calling the async function logic
            import asyncio

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(coro)
            finally:
                loop.close()

        mock_asyncio.run.side_effect = run_side_effect

        args = MagicMock()
        args.dlq_command = "requeue"
        args.letter_id = "letter-1"
        args.requeue_seq = None

        result = _handle_dlq_command(Path("test.db"), args)
        assert result == 0
        mock_queue.get.assert_called_once_with("letter-1")
        mock_asyncio.run.assert_called_once()
        mock_queue.mark_requeued.assert_called_once_with(
            "letter-1", requeue_seq=1, connection=mock_conn
        )

    @patch("k0.cli.k0ctl.configure_pool")
    @patch("k0.cli.k0ctl.shutdown_pool")
    @patch("k0.cli.k0ctl.DeadLetterQueue")
    @patch("k0.cli.k0ctl.OutboxStore")
    def test_handle_dlq_requeue_not_found(
        self,
        mock_outbox_class: MagicMock,
        mock_dlq_class: MagicMock,
        mock_shutdown: MagicMock,
        mock_configure: MagicMock,
    ) -> None:
        """Test dlq requeue subcommand when letter not found."""
        mock_queue = MagicMock()
        mock_dlq_class.return_value = mock_queue
        mock_outbox = MagicMock()
        mock_outbox_class.return_value = mock_outbox

        mock_queue.get.return_value = None

        args = MagicMock()
        args.dlq_command = "requeue"
        args.letter_id = "letter-1"

        result = _handle_dlq_command(Path("test.db"), args)
        assert result == 2

    @patch("k0.cli.k0ctl.configure_pool")
    @patch("k0.cli.k0ctl.shutdown_pool")
    @patch("k0.cli.k0ctl.DeadLetterQueue")
    @patch("k0.cli.k0ctl.OutboxStore")
    def test_handle_dlq_requeue_already_requeued(
        self,
        mock_outbox_class: MagicMock,
        mock_dlq_class: MagicMock,
        mock_shutdown: MagicMock,
        mock_configure: MagicMock,
    ) -> None:
        """Test dlq requeue subcommand when already requeued."""
        mock_queue = MagicMock()
        mock_dlq_class.return_value = mock_queue
        mock_outbox = MagicMock()
        mock_outbox_class.return_value = mock_outbox

        mock_letter = MagicMock()
        mock_letter.state = "REQUEUED"
        mock_queue.get.return_value = mock_letter

        args = MagicMock()
        args.dlq_command = "requeue"
        args.letter_id = "letter-1"

        result = _handle_dlq_command(Path("test.db"), args)
        assert result == 0

    @patch("k0.cli.k0ctl.configure_pool")
    @patch("k0.cli.k0ctl.shutdown_pool")
    @patch("k0.cli.k0ctl.DeadLetterQueue")
    @patch("k0.cli.k0ctl.OutboxStore")
    def test_handle_dlq_requeue_quarantined(
        self,
        mock_outbox_class: MagicMock,
        mock_dlq_class: MagicMock,
        mock_shutdown: MagicMock,
        mock_configure: MagicMock,
    ) -> None:
        """Test dlq requeue subcommand when quarantined."""
        mock_queue = MagicMock()
        mock_dlq_class.return_value = mock_queue
        mock_outbox = MagicMock()
        mock_outbox_class.return_value = mock_outbox

        mock_letter = MagicMock()
        mock_letter.state = "QUARANTINED"
        mock_queue.get.return_value = mock_letter

        args = MagicMock()
        args.dlq_command = "requeue"
        args.letter_id = "letter-1"

        result = _handle_dlq_command(Path("test.db"), args)
        assert result == 2

    @patch("k0.cli.k0ctl.configure_pool")
    @patch("k0.cli.k0ctl.shutdown_pool")
    @patch("k0.cli.k0ctl.DeadLetterQueue")
    @patch("k0.cli.k0ctl.OutboxStore")
    def test_handle_dlq_purge_command(
        self,
        mock_outbox_class: MagicMock,
        mock_dlq_class: MagicMock,
        mock_shutdown: MagicMock,
        mock_configure: MagicMock,
    ) -> None:
        """Test dlq purge subcommand."""
        mock_queue = MagicMock()
        mock_dlq_class.return_value = mock_queue
        mock_outbox = MagicMock()
        mock_outbox_class.return_value = mock_outbox

        mock_queue.purge.return_value = True

        args = MagicMock()
        args.dlq_command = "purge"
        args.letter_id = "letter-1"

        result = _handle_dlq_command(Path("test.db"), args)
        assert result == 0
        mock_queue.purge.assert_called_once_with("letter-1")

    @patch("k0.cli.k0ctl.configure_pool")
    @patch("k0.cli.k0ctl.shutdown_pool")
    @patch("k0.cli.k0ctl.DeadLetterQueue")
    @patch("k0.cli.k0ctl.OutboxStore")
    def test_handle_dlq_purge_not_found(
        self,
        mock_outbox_class: MagicMock,
        mock_dlq_class: MagicMock,
        mock_shutdown: MagicMock,
        mock_configure: MagicMock,
    ) -> None:
        """Test dlq purge subcommand when letter not found."""
        mock_queue = MagicMock()
        mock_dlq_class.return_value = mock_queue
        mock_outbox = MagicMock()
        mock_outbox_class.return_value = mock_outbox

        mock_queue.purge.return_value = False

        args = MagicMock()
        args.dlq_command = "purge"
        args.letter_id = "letter-1"

        result = _handle_dlq_command(Path("test.db"), args)
        assert result == 2


class TestHandleReplayCommand:
    """Test _handle_replay_command function."""

    @patch("k0.cli.k0ctl.configure_pool")
    @patch("k0.cli.k0ctl.shutdown_pool")
    @patch("k0.cli.k0ctl.Replayer")
    @patch("k0.cli.k0ctl.SchemaRegistry")
    @patch("k0.cli.k0ctl._build_operational_instrumentation")
    def test_handle_replay_command_success(
        self,
        mock_build_inst: MagicMock,
        mock_registry_class: MagicMock,
        mock_replayer_class: MagicMock,
        mock_shutdown: MagicMock,
        mock_configure: MagicMock,
    ) -> None:
        """Test replay command success."""
        mock_metrics = MagicMock()
        mock_observability = MagicMock()
        mock_build_inst.return_value = (mock_metrics, mock_observability)

        mock_registry = MagicMock()
        mock_registry_class.return_value = mock_registry

        mock_replayer = MagicMock()
        mock_replayer_class.return_value = mock_replayer

        mock_result = MagicMock()
        mock_result.processed = 100
        mock_result.last_position = "pos-456"
        mock_result.duration_seconds = 1.234
        mock_result.parity_failures = 0
        mock_replayer.run.return_value = mock_result

        args = MagicMock()
        args.from_position = "pos-123"
        args.tenant_id = "tenant1"
        args.space_id = "space1"
        args.dry_run = False

        result = _handle_replay_command(Path("test.db"), args, settings=MagicMock())
        assert result == 0
        mock_replayer.run.assert_called_once_with(
            from_position="pos-123",
            tenant_id="tenant1",
            space_id="space1",
            dry_run=False,
        )

    @patch("k0.cli.k0ctl.configure_pool")
    @patch("k0.cli.k0ctl.shutdown_pool")
    @patch("k0.cli.k0ctl.Replayer")
    @patch("k0.cli.k0ctl.SchemaRegistry")
    @patch("k0.cli.k0ctl._build_operational_instrumentation")
    def test_handle_replay_command_error(
        self,
        mock_build_inst: MagicMock,
        mock_registry_class: MagicMock,
        mock_replayer_class: MagicMock,
        mock_shutdown: MagicMock,
        mock_configure: MagicMock,
    ) -> None:
        """Test replay command with error."""
        mock_metrics = MagicMock()
        mock_observability = MagicMock()
        mock_build_inst.return_value = (mock_metrics, mock_observability)

        mock_registry = MagicMock()
        mock_registry_class.return_value = mock_registry

        mock_replayer = MagicMock()
        mock_replayer_class.return_value = mock_replayer

        from k0.storage.replayer import ReplayError

        mock_replayer.run.side_effect = ReplayError("Replay failed")

        args = MagicMock()
        args.from_position = "pos-123"
        args.tenant_id = "tenant1"
        args.space_id = "space1"
        args.dry_run = False

        result = _handle_replay_command(Path("test.db"), args, settings=MagicMock())
        assert result == 2


class TestResolveServeOptions:
    """Test _resolve_serve_options function."""

    def test_resolve_serve_options_with_args(self) -> None:
        """Test serve options resolution with provided args."""
        mock_settings = MagicMock()
        mock_settings.server.host = "default-host"
        mock_settings.server.port = 8080
        mock_settings.server.log_level = "WARNING"
        mock_settings.server.timeout_graceful_shutdown = 15.0

        args = MagicMock()
        args.host = "custom-host"
        args.port = 9090
        args.log_level = "debug"
        args.graceful_timeout = 30.0

        result = _resolve_serve_options(args, mock_settings)

        assert result.host == "custom-host"
        assert result.port == 9090
        assert result.log_level == "debug"
        assert result.timeout_graceful_shutdown == 30.0

    def test_resolve_serve_options_defaults(self) -> None:
        """Test serve options resolution with defaults."""
        mock_settings = MagicMock()
        mock_settings.server.host = "default-host"
        mock_settings.server.port = 8080
        mock_settings.server.log_level = "INFO"
        mock_settings.server.timeout_graceful_shutdown = 15.0

        args = MagicMock()
        args.host = None
        args.port = None
        args.log_level = None
        args.graceful_timeout = None

        result = _resolve_serve_options(args, mock_settings)

        assert result.host == "default-host"
        assert result.port == 8080
        assert result.log_level == "info"  # Should be lowercased
        assert result.timeout_graceful_shutdown == 15.0


class TestOverrideHelpers:
    """Test override helper functions."""

    def test_parse_override_pair_simple(self) -> None:
        """Test parsing simple override pair."""
        path, value = _parse_override_pair("key=value")
        assert path == ["key"]
        assert value == "value"

    def test_parse_override_pair_nested(self) -> None:
        """Test parsing nested override pair."""
        path, value = _parse_override_pair("server.host=localhost")
        assert path == ["server", "host"]
        assert value == "localhost"

    def test_parse_override_pair_yaml_value(self) -> None:
        """Test parsing override pair with YAML value."""
        path, value = _parse_override_pair("port=8080")
        assert path == ["port"]
        assert value == 8080  # Should be parsed as int

    def test_parse_override_pair_yaml_error(self) -> None:
        """Test parsing override pair with invalid YAML that falls back to string."""
        # This should return the string as-is since yaml.safe_load will fail on invalid YAML
        path, value = _parse_override_pair("value=not-valid-yaml-!!!")
        assert path == ["value"]
        assert value == "not-valid-yaml-!!!"

    def test_parse_override_pair_invalid_format(self) -> None:
        """Test parsing invalid override pair."""
        with pytest.raises(ValueError, match="Override must be in KEY=VALUE form"):
            _parse_override_pair("invalid")

    def test_parse_override_pair_empty_key(self) -> None:
        """Test parsing override pair with empty key."""
        with pytest.raises(ValueError, match="Override key must not be empty"):
            _parse_override_pair("=value")

    def test_parse_override_pair_empty_value(self) -> None:
        """Test parsing override pair with empty/whitespace value."""
        with pytest.raises(ValueError, match="Override values must be non-empty"):
            _parse_override_pair("   ")

    def test_compose_overrides_empty(self) -> None:
        """Test composing empty overrides."""
        result = _compose_overrides([])
        assert result == {}

    def test_compose_overrides_simple(self) -> None:
        """Test composing simple overrides."""
        result = _compose_overrides(["key=value"])
        assert result == {"key": "value"}

    def test_compose_overrides_nested(self) -> None:
        """Test composing nested overrides."""
        result = _compose_overrides(["server.host=localhost", "server.port=8080"])
        expected = {"server": {"host": "localhost", "port": 8080}}
        assert result == expected


class TestHandleDbCommand:
    """Test _handle_db_command function."""

    @patch("k0.cli.db_migrate.cmd_upgrade")
    def test_handle_db_upgrade_command(self, mock_cmd_upgrade: MagicMock) -> None:
        """Test db upgrade subcommand."""
        mock_cmd_upgrade.return_value = 0
        args = MagicMock()
        args.db_command = "upgrade"

        result = _handle_db_command(args)
        assert result == 0
        mock_cmd_upgrade.assert_called_once_with(args)

    @patch("k0.cli.db_migrate.cmd_downgrade")
    def test_handle_db_downgrade_command(self, mock_cmd_downgrade: MagicMock) -> None:
        """Test db downgrade subcommand."""
        mock_cmd_downgrade.return_value = 0
        args = MagicMock()
        args.db_command = "downgrade"

        result = _handle_db_command(args)
        assert result == 0
        mock_cmd_downgrade.assert_called_once_with(args)

    @patch("k0.cli.db_migrate.cmd_current")
    def test_handle_db_current_command(self, mock_cmd_current: MagicMock) -> None:
        """Test db current subcommand."""
        mock_cmd_current.return_value = 0
        args = MagicMock()
        args.db_command = "current"

        result = _handle_db_command(args)
        assert result == 0
        mock_cmd_current.assert_called_once_with(args)

    @patch("k0.cli.db_migrate.cmd_history")
    def test_handle_db_history_command(self, mock_cmd_history: MagicMock) -> None:
        """Test db history subcommand."""
        mock_cmd_history.return_value = 0
        args = MagicMock()
        args.db_command = "history"

        result = _handle_db_command(args)
        assert result == 0
        mock_cmd_history.assert_called_once_with(args)

    @patch("k0.cli.db_migrate.cmd_revision")
    def test_handle_db_revision_command(self, mock_cmd_revision: MagicMock) -> None:
        """Test db revision subcommand."""
        mock_cmd_revision.return_value = 0
        args = MagicMock()
        args.db_command = "revision"

        result = _handle_db_command(args)
        assert result == 0
        mock_cmd_revision.assert_called_once_with(args)

    @patch("k0.cli.k0ctl.logger")
    def test_handle_db_unknown_command(self, mock_logger: MagicMock) -> None:
        """Test db unknown subcommand."""
        args = MagicMock()
        args.db_command = "unknown"

        result = _handle_db_command(args)
        assert result == 2
        mock_logger.error.assert_called_once_with(
            "`db %s` command is not implemented yet", "unknown"
        )


class TestProvisionDevice:
    """Test _provision_device function."""

    @patch("k0.cli.k0ctl.shutdown_pool")
    @patch("k0.cli.k0ctl.configure_pool")
    @patch("k0.cli.k0ctl.ProvisioningLedger")
    def test_provision_device_success(
        self, mock_ledger_class: MagicMock, mock_configure: MagicMock, mock_shutdown: MagicMock
    ) -> None:
        """Test successful device provisioning."""
        mock_ledger = MagicMock()
        mock_ledger_class.return_value = mock_ledger

        settings = MagicMock()
        database_path = Path("test.db")

        _provision_device(
            database_path,
            settings=settings,
            tenant_id="tenant-123",
            space_id="space-456",
            device_id="device-789",
            mls_group_id="group-abc",
            key_version="v1.0",
            verify_key="key-xyz",
            provisioned_ts="2023-01-01T00:00:00Z",
        )

        mock_configure.assert_called_once_with(database_path)
        mock_shutdown.assert_called_once()

        # Verify ledger calls
        assert mock_ledger.register.called
        assert mock_ledger.add_key.called

    @patch("k0.cli.k0ctl.shutdown_pool")
    @patch("k0.cli.k0ctl.configure_pool")
    @patch("k0.cli.k0ctl.ProvisioningLedger")
    def test_provision_device_with_exception(
        self, mock_ledger_class: MagicMock, mock_configure: MagicMock, mock_shutdown: MagicMock
    ) -> None:
        """Test device provisioning with exception."""
        mock_ledger = MagicMock()
        mock_ledger.register.side_effect = Exception("Registration failed")
        mock_ledger_class.return_value = mock_ledger

        settings = MagicMock()
        database_path = Path("test.db")

        with pytest.raises(Exception, match="Registration failed"):
            _provision_device(
                database_path,
                settings=settings,
                tenant_id="tenant-123",
                space_id="space-456",
                device_id="device-789",
                mls_group_id="group-abc",
                key_version="v1.0",
                verify_key="key-xyz",
                provisioned_ts="2023-01-01T00:00:00Z",
            )

        mock_configure.assert_called_once_with(database_path)
        mock_shutdown.assert_called_once()
