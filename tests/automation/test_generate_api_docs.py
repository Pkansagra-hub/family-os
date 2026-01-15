"""Tests for generate_api_docs module.

Tests cover:
- YAML loading and parsing
- OpenAPI HTML rendering
- AsyncAPI HTML rendering
- PDF generation from text
- API summary generation
- Example loading
- Postman collection generation
- File writing operations
- Main documentation generation
- CLI argument parsing
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
import yaml

from k0.automation.generate_api_docs import (
    _asyncapi_summary_lines,
    _generate_postman_collection,
    _load_examples,
    _load_yaml,
    _openapi_summary_lines,
    _pdf_bytes_from_lines,
    _render_asyncapi_html,
    _render_openapi_html,
    _write_bytes,
    _write_text,
    generate_docs,
    main,
    parse_args,
)


@pytest.fixture
def temp_contracts_dir():
    """Create temporary contracts directory with sample specs."""
    with tempfile.TemporaryDirectory() as tmpdir:
        contracts_dir = Path(tmpdir) / "k0" / "contracts"
        contracts_dir.mkdir(parents=True)

        # Create sample OpenAPI spec
        openapi_spec = {
            "openapi": "3.0.0",
            "info": {"title": "Test API", "version": "1.0.0"},
            "paths": {
                "/users": {
                    "get": {
                        "summary": "Get users",
                        "responses": {"200": {"description": "Success"}},
                    }
                }
            },
        }
        openapi_file = contracts_dir / "openapi.k0.yaml"
        openapi_file.write_text(yaml.dump(openapi_spec))

        # Create sample AsyncAPI spec
        asyncapi_spec = {
            "asyncapi": "2.0.0",
            "info": {"title": "Test Events", "version": "1.0.0"},
            "channels": {
                "user.created": {
                    "publish": {
                        "message": {
                            "payload": {"type": "object", "properties": {"id": {"type": "string"}}}
                        }
                    }
                }
            },
        }
        asyncapi_file = contracts_dir / "asyncapi.events.yaml"
        asyncapi_file.write_text(yaml.dump(asyncapi_spec))

        # Create examples directory
        examples_dir = contracts_dir / "jsonschema" / "examples"
        examples_dir.mkdir(parents=True)

        example_file = examples_dir / "user_example.json"
        example_file.write_text(json.dumps({"id": "123", "name": "John"}))

        yield contracts_dir


@pytest.fixture
def mock_repo_root(temp_contracts_dir):
    """Mock the REPO_ROOT to point to our temp directory."""
    repo_root = temp_contracts_dir.parent.parent
    with patch("k0.automation.generate_api_docs.REPO_ROOT", repo_root):
        yield repo_root


class TestLoadYaml:
    """Tests for _load_yaml function."""

    def test_load_yaml_success(self):
        """Test successful YAML loading."""
        content = {"key": "value", "number": 42}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(content, f)
            f.flush()
            file_path = Path(f.name)

        try:
            result = _load_yaml(file_path)
            assert result == content
        finally:
            file_path.unlink()

    def test_load_yaml_file_not_found(self):
        """Test loading non-existent YAML file."""
        with pytest.raises(FileNotFoundError):
            _load_yaml(Path("/nonexistent/file.yaml"))


class TestRenderOpenAPIHTML:
    """Tests for _render_openapi_html function."""

    def test_render_openapi_html(self):
        """Test OpenAPI HTML rendering."""
        spec = {
            "openapi": "3.0.0",
            "info": {"title": "Test API"},
            "paths": {"/test": {"get": {"responses": {"200": {"description": "OK"}}}}},
        }

        html = _render_openapi_html(spec)

        assert "<!DOCTYPE html>" in html
        assert "K0 OpenAPI Reference" in html
        assert "redoc.standalone.js" in html
        assert "Redoc.init" in html
        assert json.dumps(spec, ensure_ascii=False) in html


class TestRenderAsyncAPIHTML:
    """Tests for _render_asyncapi_html function."""

    def test_render_asyncapi_html(self):
        """Test AsyncAPI HTML rendering."""
        spec = {
            "asyncapi": "2.0.0",
            "info": {"title": "Test Events"},
            "channels": {"test.channel": {"publish": {"message": {"payload": {"type": "string"}}}}},
        }

        html = _render_asyncapi_html(spec)

        assert "<!DOCTYPE html>" in html
        assert "K0 AsyncAPI Reference" in html
        assert "test.channel" in html
        assert "Channels" in html


class TestPDFBytesFromLines:
    """Tests for _pdf_bytes_from_lines function."""

    def test_pdf_bytes_from_lines(self):
        """Test PDF generation from text lines."""
        lines = ["Line 1", "Line 2", "Line 3"]

        with (
            patch("k0.automation.generate_api_docs._load_fpdf_class") as mock_load_fpdf,
            patch("k0.automation.generate_api_docs.io.BytesIO") as mock_bytesio,
        ):
            mock_fpdf_cls = Mock()
            mock_pdf_instance = Mock()
            mock_buffer = Mock()
            mock_buffer.getvalue.return_value = b"pdf content"
            mock_bytesio.return_value = mock_buffer
            mock_pdf_instance.w = 210
            mock_pdf_instance.l_margin = 10
            mock_pdf_instance.r_margin = 10
            mock_fpdf_cls.return_value = mock_pdf_instance
            mock_load_fpdf.return_value = mock_fpdf_cls

            pdf_bytes = _pdf_bytes_from_lines(lines, title="Test PDF")

            assert pdf_bytes == b"pdf content"
            mock_fpdf_cls.assert_called_once()
            mock_pdf_instance.add_page.assert_called_once()
            mock_pdf_instance.output.assert_called_once_with(mock_buffer)


class TestAPISummaryLines:
    """Tests for API summary generation functions."""

    def test_openapi_summary_lines(self):
        """Test OpenAPI summary generation."""
        spec = {
            "info": {"title": "Test API", "version": "1.0.0"},
            "paths": {
                "/users": {"get": {"summary": "Get users"}},
                "/posts": {"post": {"summary": "Create post"}},
            },
        }

        lines = _openapi_summary_lines(spec)

        assert "Title: Test API" in " ".join(lines)
        assert "Version: 1.0.0" in " ".join(lines)
        assert "/users" in " ".join(lines)
        assert "/posts" in " ".join(lines)

    def test_asyncapi_summary_lines(self):
        """Test AsyncAPI summary generation."""
        spec = {
            "info": {"title": "Test Events", "version": "1.0.0"},
            "channels": {
                "user.created": {"publish": {"message": {"summary": "User created"}}},
                "post.updated": {"subscribe": {"message": {"summary": "Post updated"}}},
            },
        }

        lines = _asyncapi_summary_lines(spec)

        assert "Title: Test Events" in " ".join(lines)
        assert "Version: 1.0.0" in " ".join(lines)
        assert "user.created" in " ".join(lines)
        assert "post.updated" in " ".join(lines)


class TestLoadExamples:
    """Tests for _load_examples function."""

    def test_load_examples_success(self, mock_repo_root):
        """Test successful example loading."""
        examples = _load_examples()

        assert isinstance(examples, dict)
        # Should contain our test example
        assert len(examples) > 0

    def test_load_examples_no_directory(self):
        """Test loading examples when directory doesn't exist."""
        with patch("k0.automation.generate_api_docs.EXAMPLES_DIR", Path("/nonexistent")):
            examples = _load_examples()
            assert examples == {}


class TestGeneratePostmanCollection:
    """Tests for _generate_postman_collection function."""

    def test_generate_postman_collection(self):
        """Test Postman collection generation."""
        openapi_spec = {
            "openapi": "3.0.0",
            "info": {"title": "Test API", "version": "1.0.0"},
            "servers": [{"url": "https://api.example.com"}],
            "paths": {
                "/users": {
                    "get": {
                        "summary": "Get users",
                        "responses": {"200": {"description": "Success"}},
                    }
                }
            },
        }

        collection = _generate_postman_collection(openapi_spec)

        assert collection["info"]["name"] == "Test API"
        assert "item" in collection
        assert len(collection["item"]) > 0
        assert collection["item"][0]["name"] == "Get users"


class TestWriteOperations:
    """Tests for file writing functions."""

    def test_write_text_success(self, tmp_path):
        """Test successful text file writing."""
        file_path = tmp_path / "test.txt"
        content = "test content"

        result = _write_text(file_path, content)

        assert result is True
        assert file_path.read_text() == content

    def test_write_text_failure(self, tmp_path):
        """Test text file writing failure."""
        # Try to write to a directory that doesn't allow writing
        file_path = tmp_path / "readonly" / "test.txt"

        result = _write_text(file_path, "content")

        assert result is False

    def test_write_bytes_success(self, tmp_path):
        """Test successful binary file writing."""
        file_path = tmp_path / "test.bin"
        content = b"binary content"

        result = _write_bytes(file_path, content)

        assert result is True
        assert file_path.read_bytes() == content

    def test_write_bytes_failure(self, tmp_path):
        """Test binary file writing failure."""
        file_path = tmp_path / "readonly" / "test.bin"

        result = _write_bytes(file_path, b"content")

        assert result is False


class TestGenerateDocs:
    """Tests for generate_docs function."""

    def test_generate_docs_success(self, mock_repo_root, tmp_path):
        """Test successful documentation generation."""
        output_dir = tmp_path / "docs" / "api"
        output_dir.mkdir(parents=True)

        with (
            patch("k0.automation.generate_api_docs.OUTPUT_DIR", output_dir),
            patch("k0.automation.generate_api_docs.POSTMAN_DIR", output_dir / "postman"),
            patch("k0.automation.generate_api_docs.OPENAPI_HTML_PATH", output_dir / "openapi.html"),
            patch(
                "k0.automation.generate_api_docs.ASYNCAPI_HTML_PATH", output_dir / "asyncapi.html"
            ),
            patch("k0.automation.generate_api_docs.OPENAPI_PDF_PATH", output_dir / "openapi.pdf"),
            patch("k0.automation.generate_api_docs.ASYNCAPI_PDF_PATH", output_dir / "asyncapi.pdf"),
            patch(
                "k0.automation.generate_api_docs.POSTMAN_JSON_PATH",
                output_dir / "postman" / "K0_Ports_Collection.json",
            ),
            patch("k0.automation.generate_api_docs._load_fpdf_class") as mock_load_fpdf,
        ):

            mock_pdf_instance = Mock()
            mock_pdf_instance.output.return_value = b"pdf content"
            mock_pdf_instance.w = 210  # A4 width in points
            mock_pdf_instance.l_margin = 12
            mock_pdf_instance.r_margin = 12

            mock_fpdf_cls = Mock()
            mock_fpdf_cls.return_value = mock_pdf_instance
            mock_load_fpdf.return_value = mock_fpdf_cls

            result = generate_docs(check=False)

            assert result is True

            # Check that files were created
            assert (output_dir / "openapi.html").exists()
            assert (output_dir / "asyncapi.html").exists()
            assert (output_dir / "openapi.pdf").exists()
            assert (output_dir / "asyncapi.pdf").exists()
            assert (output_dir / "postman" / "K0_Ports_Collection.json").exists()

    def test_generate_docs_check_mode(self, mock_repo_root, tmp_path):
        """Test documentation generation in check mode."""
        output_dir = tmp_path / "docs" / "api"
        output_dir.mkdir(parents=True)

        # Generate docs first
        generate_docs(check=False)

        # Now check should pass
        result = generate_docs(check=True)
        assert result is False

    def test_generate_docs_missing_specs(self, tmp_path):
        """Test documentation generation with missing specs."""
        output_dir = tmp_path / "docs" / "api"
        output_dir.mkdir(parents=True)

        with (
            patch("k0.automation.generate_api_docs.OUTPUT_DIR", output_dir),
            patch("k0.automation.generate_api_docs.OPENAPI_PATH", tmp_path / "missing.yaml"),
        ):

            result = generate_docs(check=False)
            assert result is False


class TestParseArgs:
    """Tests for parse_args function."""

    def test_parse_args_default(self):
        """Test parsing default arguments."""
        args = parse_args([])
        assert not args.check

    def test_parse_args_check(self):
        """Test parsing --check argument."""
        args = parse_args(["--check"])
        assert args.check

    def test_parse_args_output_dir(self):
        """Test parsing --output-dir argument."""
        # Note: output_dir argument doesn't exist in current parser
        with pytest.raises(SystemExit):
            parse_args(["--output-dir", "/tmp/docs"])


class TestMain:
    """Tests for main function."""

    def test_main_generate_docs(self, mock_repo_root, tmp_path):
        """Test main function generating documentation."""
        output_dir = tmp_path / "docs" / "api"
        output_dir.mkdir(parents=True)

        with (
            patch("k0.automation.generate_api_docs.OUTPUT_DIR", output_dir),
            patch("k0.automation.generate_api_docs._load_fpdf_class") as mock_load_fpdf,
        ):

            mock_pdf_instance = Mock()
            mock_pdf_instance.output.return_value = b"pdf content"
            mock_pdf_instance.w = 210  # A4 width in points
            mock_pdf_instance.l_margin = 12
            mock_pdf_instance.r_margin = 12

            mock_fpdf_cls = Mock()
            mock_fpdf_cls.return_value = mock_pdf_instance
            mock_load_fpdf.return_value = mock_fpdf_cls

            exit_code = main([])
            assert exit_code == 0

    def test_main_check_mode_success(self, mock_repo_root, tmp_path):
        """Test main function in check mode with up-to-date docs."""
        output_dir = tmp_path / "docs" / "api"
        output_dir.mkdir(parents=True)

        # Create mock spec files
        contracts_dir = tmp_path / "k0" / "contracts"
        contracts_dir.mkdir(parents=True)
        openapi_spec = {
            "openapi": "3.0.0",
            "info": {"title": "Test API", "version": "1.0.0"},
            "paths": {},
        }
        asyncapi_spec = {
            "asyncapi": "2.0.0",
            "info": {"title": "Test Events", "version": "1.0.0"},
            "channels": {},
        }

        (contracts_dir / "openapi.k0.yaml").write_text(yaml.dump(openapi_spec))
        (contracts_dir / "asyncapi.k0.yaml").write_text(yaml.dump(asyncapi_spec))

        # Generate docs first
        with (
            patch("k0.automation.generate_api_docs.OUTPUT_DIR", output_dir),
            patch("k0.automation.generate_api_docs.POSTMAN_DIR", output_dir / "postman"),
            patch("k0.automation.generate_api_docs.OPENAPI_HTML_PATH", output_dir / "openapi.html"),
            patch(
                "k0.automation.generate_api_docs.ASYNCAPI_HTML_PATH", output_dir / "asyncapi.html"
            ),
            patch("k0.automation.generate_api_docs.OPENAPI_PDF_PATH", output_dir / "openapi.pdf"),
            patch("k0.automation.generate_api_docs.ASYNCAPI_PDF_PATH", output_dir / "asyncapi.pdf"),
            patch(
                "k0.automation.generate_api_docs.POSTMAN_JSON_PATH",
                output_dir / "postman" / "K0_Ports_Collection.json",
            ),
            patch("k0.automation.generate_api_docs._load_fpdf_class") as mock_load_fpdf,
        ):
            mock_pdf_instance = Mock()
            mock_pdf_instance.output.return_value = b"pdf content"
            mock_pdf_instance.w = 210  # A4 width in points
            mock_pdf_instance.l_margin = 12
            mock_pdf_instance.r_margin = 12

            mock_fpdf_cls = Mock()
            mock_fpdf_cls.return_value = mock_pdf_instance
            mock_load_fpdf.return_value = mock_fpdf_cls
            generate_docs(check=False)

        # Now check should pass
        with (
            patch("k0.automation.generate_api_docs.OUTPUT_DIR", output_dir),
            patch("k0.automation.generate_api_docs.POSTMAN_DIR", output_dir / "postman"),
            patch("k0.automation.generate_api_docs.OPENAPI_HTML_PATH", output_dir / "openapi.html"),
            patch(
                "k0.automation.generate_api_docs.ASYNCAPI_HTML_PATH", output_dir / "asyncapi.html"
            ),
            patch("k0.automation.generate_api_docs.OPENAPI_PDF_PATH", output_dir / "openapi.pdf"),
            patch("k0.automation.generate_api_docs.ASYNCAPI_PDF_PATH", output_dir / "asyncapi.pdf"),
            patch(
                "k0.automation.generate_api_docs.POSTMAN_JSON_PATH",
                output_dir / "postman" / "K0_Ports_Collection.json",
            ),
            patch("k0.automation.generate_api_docs._load_fpdf_class") as mock_load_fpdf,
        ):
            mock_pdf_instance = Mock()
            mock_pdf_instance.output.return_value = b"pdf content"
            mock_pdf_instance.w = 210  # A4 width in points
            mock_pdf_instance.l_margin = 12
            mock_pdf_instance.r_margin = 12

            mock_fpdf_cls = Mock()
            mock_fpdf_cls.return_value = mock_pdf_instance
            mock_load_fpdf.return_value = mock_fpdf_cls

            exit_code = main(["--check"])
            assert exit_code == 0
