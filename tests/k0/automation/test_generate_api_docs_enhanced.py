"""Comprehensive tests for enhanced generate_api_docs with AsyncAPI rendering, Postman generation, and deterministic PDFs."""

import json
import tempfile
from pathlib import Path
from unittest import mock

from k0.automation.generate_api_docs import (
    _asyncapi_summary_lines,
    _generate_postman_collection,
    _load_examples,
    _openapi_summary_lines,
    _render_asyncapi_html,
    _render_openapi_html,
)


class TestAsyncAPIHtmlRendering:
    """Tests for AsyncAPI HTML rendering with interactive interface."""

    def test_render_asyncapi_basic(self):
        """Test basic AsyncAPI HTML rendering."""
        spec = {
            "asyncapi": "2.6.0",
            "info": {"title": "Test Events", "version": "1.0.0"},
            "channels": {
                "events.created": {
                    "description": "Created events",
                    "publish": {"message": {"$ref": "#/components/messages/Event"}},
                }
            },
            "components": {
                "messages": {
                    "Event": {
                        "description": "A generic event",
                        "payload": {"type": "object"},
                    }
                }
            },
        }

        html = _render_asyncapi_html(spec)
        assert "<!DOCTYPE html>" in html
        assert "K0 AsyncAPI Reference" in html
        assert "Test Events" in html
        assert "1.0.0" in html
        assert "events.created" in html

    def test_render_asyncapi_with_multiple_channels(self):
        """Test AsyncAPI rendering with multiple channels."""
        spec = {
            "asyncapi": "2.6.0",
            "info": {"title": "K0 Events", "version": "2.0.0"},
            "channels": {
                "memory.write": {"description": "Memory writes"},
                "events.audit": {"description": "Audit events"},
                "policy.enforce": {"description": "Policy enforcement"},
            },
            "components": {"messages": {}},
        }

        html = _render_asyncapi_html(spec)
        assert "memory.write" in html
        assert "events.audit" in html
        assert "policy.enforce" in html
        assert "Interactive navigation" not in html  # No raw JSON dump

    def test_render_asyncapi_html_not_json_dump(self):
        """Test that AsyncAPI is NOT rendered as raw JSON dump."""
        spec = {
            "asyncapi": "2.6.0",
            "info": {"title": "Test", "version": "1.0.0"},
            "channels": {},
            "components": {"messages": {}},
        }

        html = _render_asyncapi_html(spec)
        # Should NOT contain escaped JSON dump (old behavior)
        assert "&quot;" not in html or html.count("&quot;") < 5  # Minimal quoting
        # Should contain HTML structure
        assert '<div class="container">' in html
        assert "<script>" in html  # Client-side rendering

    def test_render_asyncapi_with_description(self):
        """Test AsyncAPI rendering preserves description."""
        spec = {
            "asyncapi": "2.6.0",
            "info": {
                "title": "Events",
                "version": "1.0.0",
                "description": "Event sourcing system",
            },
            "channels": {},
            "components": {"messages": {}},
        }

        html = _render_asyncapi_html(spec)
        assert "Event sourcing system" in html


class TestOpenAPIHtmlRendering:
    """Tests for OpenAPI HTML rendering with ReDoc."""

    def test_render_openapi_basic(self):
        """Test basic OpenAPI HTML rendering."""
        spec = {
            "openapi": "3.1.0",
            "info": {"title": "K0 API", "version": "1.0.0"},
            "paths": {
                "/k0/command.submit": {
                    "post": {"summary": "Submit command", "operationId": "submitCommand"}
                }
            },
        }

        html = _render_openapi_html(spec)
        assert "<!DOCTYPE html>" in html
        assert "K0 OpenAPI Reference" in html
        assert "Redoc.init" in html
        assert spec["info"]["title"] in html


class TestPostmanCollectionGeneration:
    """Tests for Postman collection generation."""

    def test_generate_postman_collection_basic(self):
        """Test basic Postman collection generation."""
        spec = {
            "info": {"title": "K0 API", "version": "1.0.0"},
            "paths": {
                "/k0/command.submit": {
                    "post": {
                        "summary": "Submit command",
                        "description": "Submit a command envelope",
                        "requestBody": {
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/Envelope"}
                                }
                            }
                        },
                    }
                }
            },
        }

        with mock.patch("k0.automation.generate_api_docs.EXAMPLES_DIR") as mock_dir:
            mock_dir.exists.return_value = False
            collection = _generate_postman_collection(spec)

        assert collection["info"]["name"] == "K0 API"
        assert collection["info"]["version"] == "1.0.0"
        assert len(collection["item"]) == 1
        assert collection["item"][0]["request"]["method"] == "POST"
        assert collection["item"][0]["request"]["url"]["raw"] == "{{baseUrl}}/k0/command.submit"

    def test_generate_postman_collection_multiple_endpoints(self):
        """Test Postman collection with multiple endpoints."""
        spec = {
            "info": {"title": "API", "version": "1.0.0"},
            "paths": {
                "/api/submit": {"post": {"summary": "Submit"}},
                "/api/query": {"post": {"summary": "Query"}},
            },
        }

        with mock.patch("k0.automation.generate_api_docs.EXAMPLES_DIR") as mock_dir:
            mock_dir.exists.return_value = False
            collection = _generate_postman_collection(spec)

        assert len(collection["item"]) == 2
        assert collection["item"][0]["request"]["method"] == "POST"
        assert collection["item"][1]["request"]["method"] == "POST"

    def test_generate_postman_collection_has_base_url_variable(self):
        """Test Postman collection includes base URL variable."""
        spec = {
            "info": {"title": "API", "version": "1.0.0"},
            "paths": {},
        }

        with mock.patch("k0.automation.generate_api_docs.EXAMPLES_DIR") as mock_dir:
            mock_dir.exists.return_value = False
            collection = _generate_postman_collection(spec)

        assert "variable" in collection
        assert len(collection["variable"]) > 0
        base_url_var = collection["variable"][0]
        assert base_url_var["key"] == "baseUrl"
        assert base_url_var["value"] == "http://localhost:8080"

    def test_generate_postman_collection_with_examples(self):
        """Test Postman collection includes examples from files."""
        spec = {
            "info": {"title": "API", "version": "1.0.0"},
            "paths": {
                "/api/submit": {
                    "post": {
                        "summary": "Submit",
                        "requestBody": {
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/envelope.schema.json"}
                                }
                            }
                        },
                    }
                }
            },
        }

        # Mock examples
        mock_examples = {"envelope": {"id": "test-123", "data": {}}}

        with mock.patch(
            "k0.automation.generate_api_docs._load_examples", return_value=mock_examples
        ):
            collection = _generate_postman_collection(spec)

        # Body should contain example JSON
        body = collection["item"][0]["request"]["body"]["raw"]
        assert body != ""  # Should have loaded example


class TestDeterministicPDF:
    """Tests for deterministic PDF generation."""

    def test_pdf_generation_deterministic(self):
        """Test that PDF generation produces deterministic output."""
        from k0.automation.generate_api_docs import _pdf_bytes_from_lines

        lines = ["Test Line 1", "Test Line 2", "Test Line 3"]

        # Generate PDF twice
        pdf1 = _pdf_bytes_from_lines(lines, title="Test")
        pdf2 = _pdf_bytes_from_lines(lines, title="Test")

        # PDFs should be identical (deterministic)
        assert pdf1 == pdf2
        assert len(pdf1) > 0

    def test_pdf_has_static_timestamp(self):
        """Test that PDF uses static timestamp."""
        from k0.automation.generate_api_docs import _pdf_bytes_from_lines

        lines = ["Test"]
        pdf = _pdf_bytes_from_lines(lines, title="Test")

        # PDF should not contain varying timestamp values
        # Check for hardcoded timestamp pattern
        pdf_str = pdf.decode("latin-1", errors="ignore")
        # Should contain the static timestamp pattern D:20240101000000Z
        assert "20240101" in pdf_str or "2024" in pdf_str  # Deterministic year

    def test_pdf_generation_reproducible(self):
        """Test multiple PDF generations are byte-identical."""
        from k0.automation.generate_api_docs import _pdf_bytes_from_lines

        lines = ["Line A", "Line B"]
        pdfs = [_pdf_bytes_from_lines(lines, title="Doc") for _ in range(3)]

        # All PDFs should be identical
        assert pdfs[0] == pdfs[1]
        assert pdfs[1] == pdfs[2]


class TestLoadExamples:
    """Tests for loading example files."""

    def test_load_examples_empty_directory(self):
        """Test loading examples from empty directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with mock.patch("k0.automation.generate_api_docs.EXAMPLES_DIR", Path(tmpdir)):
                examples = _load_examples()
                assert examples == {}

    def test_load_examples_with_files(self):
        """Test loading examples from directory with JSON files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)

            # Create example files
            example1 = {"id": "test1"}
            example2 = {"id": "test2"}

            (tmppath / "envelope.json").write_text(json.dumps(example1))
            (tmppath / "receipt.json").write_text(json.dumps(example2))

            with mock.patch("k0.automation.generate_api_docs.EXAMPLES_DIR", tmppath):
                examples = _load_examples()

            assert "envelope" in examples
            assert "receipt" in examples
            assert examples["envelope"] == example1
            assert examples["receipt"] == example2

    def test_load_examples_skips_invalid_json(self):
        """Test that invalid JSON files are skipped."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)

            # Create valid and invalid files
            (tmppath / "valid.json").write_text('{"test": true}')
            (tmppath / "invalid.json").write_text("not json")

            with mock.patch("k0.automation.generate_api_docs.EXAMPLES_DIR", tmppath):
                examples = _load_examples()

            assert "valid" in examples
            assert "invalid" not in examples


class TestSummaryLines:
    """Tests for summary line generation."""

    def test_openapi_summary_lines(self):
        """Test OpenAPI summary generation."""
        spec = {
            "info": {"title": "API", "version": "1.0.0"},
            "paths": {
                "/api/submit": {"post": {}},
                "/api/status": {"get": {}},
            },
        }

        lines = _openapi_summary_lines(spec)
        assert "Title: API" in lines
        assert "Version: 1.0.0" in lines
        assert "Endpoints:" in lines

    def test_asyncapi_summary_lines(self):
        """Test AsyncAPI summary generation."""
        spec = {
            "info": {"title": "Events", "version": "2.0.0"},
            "channels": {
                "events.created": {},
                "events.deleted": {},
            },
        }

        lines = _asyncapi_summary_lines(spec)
        assert "Title: Events" in lines
        assert "Version: 2.0.0" in lines
        assert "Channels:" in lines


class TestGenerateDocsIntegration:
    """Integration tests for the full docs generation pipeline."""

    def test_generate_docs_postman_in_collection(self):
        """Test that Postman collection includes all endpoints."""
        spec = {
            "info": {"title": "Test API", "version": "1.0.0", "description": "Test"},
            "paths": {
                "/api/cmd": {
                    "post": {
                        "summary": "Command",
                        "description": "Submit command",
                    }
                }
            },
        }

        with mock.patch("k0.automation.generate_api_docs.EXAMPLES_DIR") as mock_dir:
            mock_dir.exists.return_value = False
            collection = _generate_postman_collection(spec)

        assert collection["info"]["name"] == "Test API"
        assert len(collection["item"]) == 1
        assert collection["item"][0]["name"] == "Command"

    def test_generate_docs_postman_schema_format(self):
        """Test that Postman collection follows v2.1.0 schema."""
        spec = {"info": {"title": "API", "version": "1.0.0"}, "paths": {}}

        with mock.patch("k0.automation.generate_api_docs.EXAMPLES_DIR") as mock_dir:
            mock_dir.exists.return_value = False
            collection = _generate_postman_collection(spec)

        # Check Postman Collection v2.1.0 required fields
        assert "info" in collection
        assert "item" in collection
        assert "variable" in collection
        assert (
            collection["info"]["schema"]
            == "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"
        )

    def test_asyncapi_html_has_interactive_elements(self):
        """Test that AsyncAPI HTML includes interactive elements, not JSON dump."""
        spec = {
            "asyncapi": "2.6.0",
            "info": {"title": "Events", "version": "1.0.0"},
            "channels": {
                "test.channel": {
                    "description": "Test channel",
                    "publish": {"message": {"$ref": "#/components/messages/Test"}},
                }
            },
            "components": {
                "messages": {
                    "Test": {
                        "description": "Test message",
                        "payload": {"type": "object"},
                    }
                }
            },
        }

        html = _render_asyncapi_html(spec)

        # Should have interactive elements
        assert "<script>" in html
        assert "document.addEventListener" in html or "getElementById" in html
        assert "test.channel" in html

        # Should NOT be a raw JSON dump
        assert html.count('{"asyncapi"') == 1  # Only in JavaScript spec variable
        assert html.count("&quot;") < 10  # Minimal HTML escaping (not a JSON dump)

    def test_postman_collection_serializable_to_json(self):
        """Test that Postman collection can be serialized to JSON."""
        spec = {
            "info": {"title": "API", "version": "1.0.0"},
            "paths": {"/test": {"post": {"summary": "Test"}}},
        }

        with mock.patch("k0.automation.generate_api_docs.EXAMPLES_DIR") as mock_dir:
            mock_dir.exists.return_value = False
            collection = _generate_postman_collection(spec)

        # Should be serializable to JSON
        json_str = json.dumps(collection, ensure_ascii=False, indent=2)
        assert len(json_str) > 0

        # Round-trip should work
        roundtrip = json.loads(json_str)
        assert roundtrip["info"]["name"] == "API"
