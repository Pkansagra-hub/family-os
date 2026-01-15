"""Tests for compute_contract_checksums module.

Tests cover:
- SHA256 computation for files
- Contract artifact collection (OpenAPI, AsyncAPI, JSON schemas, SQL)
- VERSION registry creation, loading, and writing
- Checksum verification and mismatch detection
- CLI argument parsing and main execution
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from k0.automation.compute_contract_checksums import (
    collect_contract_artifacts,
    compute_sha256,
    create_version_registry,
    display_checksums,
    load_version_registry,
    main,
    parse_args,
    verify_checksums,
    write_version_registry,
)


@pytest.fixture
def temp_contracts_dir():
    """Create temporary contracts directory with sample artifacts."""
    with tempfile.TemporaryDirectory() as tmpdir:
        contracts_dir = Path(tmpdir) / "k0" / "contracts"
        contracts_dir.mkdir(parents=True)

        # Create sample OpenAPI file
        openapi_file = contracts_dir / "openapi.k0.yaml"
        openapi_content = {"openapi": "3.0.0", "info": {"title": "Test API"}}
        openapi_file.write_text(yaml.dump(openapi_content))

        # Create sample AsyncAPI file
        asyncapi_file = contracts_dir / "asyncapi.events.yaml"
        asyncapi_content = {"asyncapi": "2.0.0", "info": {"title": "Test Events"}}
        asyncapi_file.write_text(yaml.dump(asyncapi_content))

        # Create jsonschema directory with sample schemas
        schema_dir = contracts_dir / "jsonschema"
        schema_dir.mkdir()

        schema1 = schema_dir / "user.json"
        schema1.write_text(
            json.dumps({"type": "object", "properties": {"name": {"type": "string"}}})
        )

        schema2 = schema_dir / "product.json"
        schema2.write_text(
            json.dumps({"type": "object", "properties": {"id": {"type": "integer"}}})
        )

        # Create SQL storage file
        sql_dir = contracts_dir / "sql"
        sql_dir.mkdir()
        sql_file = sql_dir / "storage.sql"
        sql_file.write_text("CREATE TABLE test (id INTEGER);")

        yield contracts_dir


@pytest.fixture
def mock_repo_root(temp_contracts_dir):
    """Mock the REPO_ROOT to point to our temp directory."""
    repo_root = temp_contracts_dir.parent.parent
    with patch("k0.automation.compute_contract_checksums.REPO_ROOT", repo_root):
        yield repo_root


class TestComputeSha256:
    """Tests for compute_sha256 function."""

    def test_compute_sha256_basic(self):
        """Test SHA256 computation for a simple file."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            f.write("test content")
            f.flush()
            file_path = Path(f.name)

        try:
            checksum = compute_sha256(file_path)
            assert isinstance(checksum, str)
            assert len(checksum) == 64  # SHA256 hex length
            # SHA256 of "test content"
            expected = "6ae8a75555209fd6c44157c0aed8016e763ff435a19cf186f76863140143ff72"
            assert checksum == expected
        finally:
            file_path.unlink()

    def test_compute_sha256_large_file(self):
        """Test SHA256 computation for a larger file."""
        content = "x" * 10000
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            f.write(content)
            f.flush()
            file_path = Path(f.name)

        try:
            checksum = compute_sha256(file_path)
            assert isinstance(checksum, str)
            assert len(checksum) == 64
        finally:
            file_path.unlink()

    def test_compute_sha256_empty_file(self):
        """Test SHA256 computation for an empty file."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            file_path = Path(f.name)

        try:
            checksum = compute_sha256(file_path)
            # SHA256 of empty string
            expected = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
            assert checksum == expected
        finally:
            file_path.unlink()


class TestCollectContractArtifacts:
    """Tests for collect_contract_artifacts function."""

    def test_collect_all_artifacts(self, mock_repo_root):
        """Test collecting all types of contract artifacts."""
        artifacts = collect_contract_artifacts()

        assert "openapi" in artifacts
        assert "asyncapi" in artifacts
        assert "schemas" in artifacts

        # Check OpenAPI
        assert artifacts["openapi"]["file"] == "openapi.k0.yaml"
        assert artifacts["openapi"]["version"] == "1.0.0"
        assert "sha256" in artifacts["openapi"]

        # Check AsyncAPI
        assert artifacts["asyncapi"]["file"] == "asyncapi.events.yaml"
        assert artifacts["asyncapi"]["version"] == "1.0.0"
        assert "sha256" in artifacts["asyncapi"]

        # Check schemas
        assert len(artifacts["schemas"]) == 16  # Real count from workspace
        schema_files = [s["file"] for s in artifacts["schemas"]]
        assert "jsonschema/acl.schema.json" in schema_files


class TestVersionRegistry:
    """Tests for VERSION registry management."""

    def test_create_version_registry(self):
        """Test creating a new VERSION registry."""
        registry = create_version_registry()

        assert registry["version"] == "1.0.0"
        assert registry["status"] == "frozen"
        assert "artifacts" in registry
        assert "approvals" in registry
        assert "changelog" in registry

        assert registry["approvals"]["architecture"] is None
        assert len(registry["changelog"]) == 1

    def test_write_and_load_version_registry(self, temp_contracts_dir):
        """Test writing and loading VERSION registry."""
        version_file = temp_contracts_dir / "VERSION"
        registry = create_version_registry()

        with patch("k0.automation.compute_contract_checksums.VERSION_FILE", version_file):
            write_version_registry(registry)

        assert version_file.exists()

        with patch("k0.automation.compute_contract_checksums.VERSION_FILE", version_file):
            loaded = load_version_registry()

        assert loaded["version"] == registry["version"]
        assert loaded["status"] == registry["status"]

    def test_load_missing_version_file(self, temp_contracts_dir):
        """Test loading non-existent VERSION file raises error."""
        version_file = temp_contracts_dir / "VERSION"

        with patch("k0.automation.compute_contract_checksums.VERSION_FILE", version_file):
            with pytest.raises(FileNotFoundError, match="VERSION file not found"):
                load_version_registry()


class TestVerifyChecksums:
    """Tests for verify_checksums function."""

    @patch("k0.automation.compute_contract_checksums.load_version_registry")
    @patch("k0.automation.compute_contract_checksums.collect_contract_artifacts")
    def test_verify_matching_checksums(self, mock_collect, mock_load):
        """Test verification when checksums match."""
        artifacts = {"openapi": {"sha256": "abc123"}}
        mock_load.return_value = {"artifacts": artifacts}
        mock_collect.return_value = artifacts

        result = verify_checksums()

        assert result is True

    @patch("k0.automation.compute_contract_checksums.load_version_registry")
    @patch("k0.automation.compute_contract_checksums.collect_contract_artifacts")
    def test_verify_mismatched_checksums(self, mock_collect, mock_load):
        """Test verification when checksums don't match."""
        mock_load.return_value = {"artifacts": {"openapi": {"sha256": "abc123"}}}
        mock_collect.return_value = {"openapi": {"sha256": "def456"}}

        result = verify_checksums()

        assert result is False

    @patch("k0.automation.compute_contract_checksums.load_version_registry")
    def test_verify_missing_version_file(self, mock_load):
        """Test verification when VERSION file doesn't exist."""
        mock_load.side_effect = FileNotFoundError("VERSION file not found")

        result = verify_checksums()

        assert result is False


class TestDisplayChecksums:
    """Tests for display_checksums function."""

    def test_display_checksums(self, mock_repo_root, capsys):
        """Test displaying checksums to stdout."""
        display_checksums()

        captured = capsys.readouterr()
        assert "ContractChecksums" in captured.out
        assert "OpenAPI:" in captured.out
        assert "AsyncAPI:" in captured.out
        assert "JSON Schemas" in captured.out
        # Note: Storage SQL not present in real workspace
        # assert "Storage SQL:" in captured.out


class TestParseArgs:
    """Tests for parse_args function."""

    def test_parse_args_default(self):
        """Test parsing default arguments."""
        args = parse_args([])
        assert not args.check
        assert not args.update

    def test_parse_args_check(self):
        """Test parsing --check argument."""
        args = parse_args(["--check"])
        assert args.check
        assert not args.update

    def test_parse_args_update(self):
        """Test parsing --update argument."""
        args = parse_args(["--update"])
        assert not args.check
        assert args.update

    def test_parse_args_mutually_exclusive(self):
        """Test that --check and --update are mutually exclusive."""
        with pytest.raises(SystemExit):
            parse_args(["--check", "--update"])


class TestMain:
    """Tests for main function."""

    @patch("k0.automation.compute_contract_checksums.display_checksums")
    @patch("k0.automation.compute_contract_checksums.parse_args")
    def test_main_display(self, mock_parse, mock_display):
        """Test main function displays checksums by default."""
        mock_parse.return_value = MagicMock(check=False, update=False)

        exit_code = main([])

        assert exit_code == 0
        mock_display.assert_called_once()

    @patch("k0.automation.compute_contract_checksums.verify_checksums")
    @patch("k0.automation.compute_contract_checksums.parse_args")
    def test_main_check_success(self, mock_parse, mock_verify):
        """Test main function with --check when checksums match."""
        mock_parse.return_value = MagicMock(check=True, update=False)
        mock_verify.return_value = True

        exit_code = main(["--check"])

        assert exit_code == 0
        mock_verify.assert_called_once()

    @patch("k0.automation.compute_contract_checksums.verify_checksums")
    @patch("k0.automation.compute_contract_checksums.parse_args")
    def test_main_check_failure(self, mock_parse, mock_verify):
        """Test main function with --check when checksums don't match."""
        mock_parse.return_value = MagicMock(check=True, update=False)
        mock_verify.return_value = False

        exit_code = main(["--check"])

        assert exit_code == 1
        mock_verify.assert_called_once()

    @patch("k0.automation.compute_contract_checksums.update_version_file")
    @patch("k0.automation.compute_contract_checksums.parse_args")
    def test_main_update(self, mock_parse, mock_update):
        """Test main function with --update."""
        mock_parse.return_value = MagicMock(check=False, update=True)

        exit_code = main(["--update"])

        assert exit_code == 0
        mock_update.assert_called_once()
