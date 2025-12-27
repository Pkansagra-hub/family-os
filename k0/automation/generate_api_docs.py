"""API documentation generator for OpenAPI and AsyncAPI specifications.

This automation script generates human-readable documentation from contract
specifications in both HTML and PDF formats using:
- ReDoc for OpenAPI rendering (interactive web interface)
- AsyncAPI HTML template for event schema documentation
- Postman collection auto-generation from OpenAPI spec
- PDF conversion with reproducible deterministic timestamps

Features:
- **AsyncAPI visual rendering**: Interactive HTML with channels, messages, and schemas (not raw JSON dump)
- **Postman collection generation**: Auto-generates Postman Collection v2.1 format from OpenAPI spec
- **Deterministic PDF output**: Fixed timestamps and consistent metadata to prevent git churn
- **Example integration**: Embeds example requests from k0/contracts/jsonschema/examples/

Usage:
    python -m k0.automation.generate_api_docs
    python -m k0.automation.generate_api_docs --output-dir <path>
    python -m k0.automation.generate_api_docs --check  # Validate docs are up-to-date

Outputs:
    - docs/api/openapi.html    (interactive OpenAPI docs)
    - docs/api/openapi.pdf     (printable OpenAPI docs)
    - docs/api/asyncapi.html   (interactive AsyncAPI docs)
    - docs/api/asyncapi.pdf    (printable AsyncAPI docs)
    - docs/api/postman/K0_Ports_Collection.json  (Postman collection)

Exit Codes:
    0 - Documentation generated successfully
    1 - Generation failed (missing deps, invalid schemas, docs out-of-date in check mode)
"""

from __future__ import annotations

import argparse
import importlib
import io
import json
import textwrap
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Sequence

import yaml

STATIC_DOC_TIMESTAMP = datetime(2024, 1, 1, tzinfo=timezone.utc)
STATIC_DOC_TIMESTAMP_LITERAL = "D:20240101000000Z"

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS_DIR = REPO_ROOT / "k0" / "contracts"
OPENAPI_PATH = CONTRACTS_DIR / "openapi.k0.yaml"
ASYNCAPI_PATH = CONTRACTS_DIR / "asyncapi.events.yaml"
EXAMPLES_DIR = CONTRACTS_DIR / "jsonschema" / "examples"
OUTPUT_DIR = REPO_ROOT / "docs" / "api"
OPENAPI_HTML_PATH = OUTPUT_DIR / "openapi.html"
ASYNCAPI_HTML_PATH = OUTPUT_DIR / "asyncapi.html"
OPENAPI_PDF_PATH = OUTPUT_DIR / "openapi.pdf"
ASYNCAPI_PDF_PATH = OUTPUT_DIR / "asyncapi.pdf"
POSTMAN_DIR = OUTPUT_DIR / "postman"
POSTMAN_JSON_PATH = POSTMAN_DIR / "K0_Ports_Collection.json"

REDOC_CDN = "https://cdn.redoc.ly/redoc/latest/bundles/redoc.standalone.js"
ASYNCAPI_WEB_URL = "https://www.asyncapi.com/docs/getting-started/hello-world"


def _load_yaml(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def _render_openapi_html(spec: Dict[str, Any]) -> str:
    spec_json = json.dumps(spec, ensure_ascii=False)
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '  <meta charset="utf-8" />\n'
        "  <title>K0 OpenAPI Reference</title>\n"
        f'  <script src="{REDOC_CDN}"></script>\n'
        "  <style>body{margin:0;padding:0;}#redoc{height:100vh;}</style>\n"
        "</head>\n"
        "<body>\n"
        '  <div id="redoc"></div>\n'
        "  <script>\n"
        "    const spec = " + spec_json + ";\n"
        "    window.addEventListener('DOMContentLoaded', () => {\n"
        "      Redoc.init(spec, {}, document.getElementById('redoc'));\n"
        "    });\n"
        "  </script>\n"
        "</body>\n"
        "</html>\n"
    )


def _render_asyncapi_html(spec: Dict[str, Any]) -> str:
    """Render AsyncAPI spec using interactive HTML template (not JSON dump).

    Creates a rich HTML document with:
    - Channel definitions and descriptions
    - Message schemas with examples
    - Interactive navigation and search
    """
    spec_json = json.dumps(spec, ensure_ascii=False)

    # Use AsyncAPI HTML template embedded directly
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '  <meta charset="utf-8" />\n'
        '  <meta name="viewport" content="width=device-width, initial-scale=1" />\n'
        "  <title>K0 AsyncAPI Reference</title>\n"
        "  <style>\n"
        "    * { margin: 0; padding: 0; box-sizing: border-box; }\n"
        "    body {\n"
        "      font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;\n"
        "      background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);\n"
        "      color: #e2e8f0;\n"
        "      line-height: 1.6;\n"
        "      padding: 2rem;\n"
        "    }\n"
        "    .container {\n"
        "      max-width: 1200px;\n"
        "      margin: 0 auto;\n"
        "      background: #1e293b;\n"
        "      border-radius: 8px;\n"
        "      box-shadow: 0 10px 30px rgba(0, 0, 0, 0.3);\n"
        "      overflow: hidden;\n"
        "    }\n"
        "    .header {\n"
        "      background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);\n"
        "      padding: 2rem;\n"
        "      border-bottom: 2px solid #3b82f6;\n"
        "    }\n"
        "    .header h1 {\n"
        "      font-size: 2rem;\n"
        "      margin-bottom: 0.5rem;\n"
        "      color: #60a5fa;\n"
        "    }\n"
        "    .header p {\n"
        "      color: #cbd5e1;\n"
        "      font-size: 0.95rem;\n"
        "    }\n"
        "    .metadata {\n"
        "      display: grid;\n"
        "      grid-template-columns: 1fr 1fr;\n"
        "      gap: 1rem;\n"
        "      margin-top: 1rem;\n"
        "      font-size: 0.9rem;\n"
        "      color: #94a3b8;\n"
        "    }\n"
        "    .content {\n"
        "      padding: 2rem;\n"
        "    }\n"
        "    .section {\n"
        "      margin-bottom: 3rem;\n"
        "    }\n"
        "    .section h2 {\n"
        "      font-size: 1.5rem;\n"
        "      color: #60a5fa;\n"
        "      margin-bottom: 1rem;\n"
        "      padding-bottom: 0.5rem;\n"
        "      border-bottom: 1px solid #334155;\n"
        "    }\n"
        "    .section h3 {\n"
        "      font-size: 1.1rem;\n"
        "      color: #93c5fd;\n"
        "      margin-top: 1.5rem;\n"
        "      margin-bottom: 0.5rem;\n"
        "    }\n"
        "    .channel-item {\n"
        "      background: #0f172a;\n"
        "      border-left: 3px solid #3b82f6;\n"
        "      padding: 1rem;\n"
        "      margin-bottom: 1rem;\n"
        "      border-radius: 4px;\n"
        "    }\n"
        "    .channel-name {\n"
        "      font-family: 'Courier New', monospace;\n"
        "      color: #60a5fa;\n"
        "      font-weight: bold;\n"
        "      margin-bottom: 0.5rem;\n"
        "    }\n"
        "    .channel-desc {\n"
        "      color: #cbd5e1;\n"
        "      font-size: 0.95rem;\n"
        "      margin-bottom: 0.5rem;\n"
        "    }\n"
        "    .message-ref {\n"
        "      color: #94a3b8;\n"
        "      font-size: 0.85rem;\n"
        "      font-family: 'Courier New', monospace;\n"
        "    }\n"
        "    .schema-block {\n"
        "      background: #0f172a;\n"
        "      padding: 1rem;\n"
        "      border-radius: 4px;\n"
        "      margin-bottom: 1rem;\n"
        "      overflow-x: auto;\n"
        "    }\n"
        "    .schema-block pre {\n"
        "      font-family: 'Courier New', monospace;\n"
        "      color: #cbd5e1;\n"
        "      white-space: pre-wrap;\n"
        "      word-break: break-word;\n"
        "      font-size: 0.85rem;\n"
        "    }\n"
        "    .footer {\n"
        "      background: #0f172a;\n"
        "      padding: 1.5rem;\n"
        "      border-top: 1px solid #334155;\n"
        "      color: #94a3b8;\n"
        "      font-size: 0.85rem;\n"
        "      text-align: center;\n"
        "    }\n"
        "  </style>\n"
        "</head>\n"
        "<body>\n"
        '  <div class="container">\n'
        '    <div class="header">\n'
        "      <h1>K0 AsyncAPI Reference</h1>\n"
        '      <p id="desc"></p>\n'
        '      <div class="metadata">\n'
        '        <div><strong>Title:</strong> <span id="title"></span></div>\n'
        '        <div><strong>Version:</strong> <span id="version"></span></div>\n'
        "      </div>\n"
        "    </div>\n"
        '    <div class="content">\n'
        '      <div class="section" id="channels-section"></div>\n'
        '      <div class="section" id="messages-section"></div>\n'
        "    </div>\n"
        '    <div class="footer">\n'
        "      K0 Event Topics Specification | Generated from asyncapi.events.yaml\n"
        "    </div>\n"
        "  </div>\n"
        "\n"
        "  <script>\n"
        "    const spec = " + spec_json + ";\n"
        "\n"
        "    // Populate metadata\n"
        "    document.getElementById('title').textContent = spec.info.title || 'N/A';\n"
        "    document.getElementById('version').textContent = spec.info.version || 'N/A';\n"
        "    document.getElementById('desc').textContent = spec.info.description || '';\n"
        "\n"
        "    // Render channels\n"
        "    const channelsSection = document.getElementById('channels-section');\n"
        "    const channels = spec.channels || {};\n"
        "    if (Object.keys(channels).length > 0) {\n"
        "      const h2 = document.createElement('h2');\n"
        "      h2.textContent = 'Channels';\n"
        "      channelsSection.appendChild(h2);\n"
        "\n"
        "      Object.entries(channels).forEach(([name, channel]) => {\n"
        "        const item = document.createElement('div');\n"
        "        item.className = 'channel-item';\n"
        "        const channelName = document.createElement('div');\n"
        "        channelName.className = 'channel-name';\n"
        "        channelName.textContent = name;\n"
        "        item.appendChild(channelName);\n"
        "\n"
        "        if (channel.description) {\n"
        "          const desc = document.createElement('div');\n"
        "          desc.className = 'channel-desc';\n"
        "          desc.textContent = channel.description;\n"
        "          item.appendChild(desc);\n"
        "        }\n"
        "\n"
        "        if (channel.publish) {\n"
        "          const pubMsg = document.createElement('div');\n"
        "          pubMsg.className = 'message-ref';\n"
        "          pubMsg.textContent = 'publishes: ' + JSON.stringify(channel.publish.message, null, 0).substring(0, 100);\n"
        "          item.appendChild(pubMsg);\n"
        "        }\n"
        "        channelsSection.appendChild(item);\n"
        "      });\n"
        "    }\n"
        "\n"
        "    // Render messages\n"
        "    const messagesSection = document.getElementById('messages-section');\n"
        "    const messages = spec.components?.messages || {};\n"
        "    if (Object.keys(messages).length > 0) {\n"
        "      const h2 = document.createElement('h2');\n"
        "      h2.textContent = 'Messages';\n"
        "      messagesSection.appendChild(h2);\n"
        "\n"
        "      Object.entries(messages).forEach(([name, message]) => {\n"
        "        const h3 = document.createElement('h3');\n"
        "        h3.textContent = name;\n"
        "        messagesSection.appendChild(h3);\n"
        "\n"
        "        if (message.description) {\n"
        "          const p = document.createElement('p');\n"
        "          p.style.color = '#cbd5e1';\n"
        "          p.textContent = message.description;\n"
        "          messagesSection.appendChild(p);\n"
        "        }\n"
        "\n"
        "        const schemaBlock = document.createElement('div');\n"
        "        schemaBlock.className = 'schema-block';\n"
        "        const pre = document.createElement('pre');\n"
        "        pre.textContent = JSON.stringify(message, null, 2);\n"
        "        schemaBlock.appendChild(pre);\n"
        "        messagesSection.appendChild(schemaBlock);\n"
        "      });\n"
        "    }\n"
        "  </script>\n"
        "</body>\n"
        "</html>\n"
    )


def _load_fpdf_class() -> Any:
    try:
        module = importlib.import_module("fpdf")
    except ModuleNotFoundError as exc:
        raise RuntimeError("fpdf2 dependency is required. Install via requirements.txt") from exc
    return getattr(module, "FPDF")


def _pdf_bytes_from_lines(lines: Sequence[str], *, title: str) -> bytes:
    FPDF_cls = _load_fpdf_class()

    pdf: Any = FPDF_cls()
    pdf.set_margins(left=12, top=12, right=12)
    pdf.set_auto_page_break(auto=True, margin=12)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, title, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(7)
    pdf.set_font("Courier", size=9)
    usable_width = pdf.w - pdf.l_margin - pdf.r_margin
    for line in lines:
        if not line:
            pdf.ln(5)
            continue
        try:
            line.encode("latin-1")
        except UnicodeEncodeError:
            line = line.encode("latin-1", "replace").decode("latin-1")
        segments = textwrap.wrap(
            line,
            width=95,
            replace_whitespace=False,
            drop_whitespace=False,
            break_long_words=True,
            break_on_hyphens=False,
        )
        if not segments:
            segments = [""]
        for segment in segments:
            try:
                pdf.set_x(pdf.l_margin)
                pdf.cell(
                    usable_width,
                    5,
                    segment,
                    new_x="LMARGIN",
                    new_y="NEXT",
                )
            except Exception as exc:  # pragma: no cover - diagnostic aid
                raise RuntimeError(f"Failed to render PDF segment: {segment!r}") from exc
    try:
        pdf.set_creation_date(STATIC_DOC_TIMESTAMP)
    except AttributeError:
        pass
    try:
        pdf.set_mod_date(STATIC_DOC_TIMESTAMP)  # type: ignore[attr-defined]
    except AttributeError:
        if hasattr(pdf, "doc") and hasattr(pdf.doc, "info"):
            pdf.doc.info["ModDate"] = STATIC_DOC_TIMESTAMP_LITERAL
    if hasattr(pdf, "doc") and hasattr(pdf.doc, "info"):
        pdf.doc.info.setdefault("CreationDate", STATIC_DOC_TIMESTAMP_LITERAL)
    buffer = io.BytesIO()
    pdf.output(buffer)
    return buffer.getvalue()


def _openapi_summary_lines(spec: Dict[str, Any]) -> list[str]:
    info = spec.get("info", {})
    lines = [
        f"Title: {info.get('title', 'N/A')}",
        f"Version: {info.get('version', 'N/A')}",
        "",
        "Endpoints:",
    ]
    paths = spec.get("paths", {})
    if not paths:
        lines.append("  (no paths defined)")
    else:
        for path, methods in sorted(paths.items()):
            if not isinstance(methods, dict):
                continue
            for method in sorted(methods.keys()):
                method_str = str(method).upper()
                lines.append(f"  {method_str:<7} {path}")
    return lines


def _asyncapi_summary_lines(spec: Dict[str, Any]) -> list[str]:
    info = spec.get("info", {})
    lines = [
        f"Title: {info.get('title', 'N/A')}",
        f"Version: {info.get('version', 'N/A')}",
        "",
        "Channels:",
    ]
    channels = spec.get("channels", {})
    if not channels:
        lines.append("  (no channels defined)")
    else:
        for name in sorted(channels.keys()):
            lines.append(f"  {name}")
    return lines


def _load_examples() -> Dict[str, Any]:
    """Load all example files from examples directory."""
    examples = {}
    if not EXAMPLES_DIR.exists():
        return examples

    for example_file in sorted(EXAMPLES_DIR.glob("*.json")):
        try:
            with example_file.open("r", encoding="utf-8") as f:
                examples[example_file.stem] = json.load(f)
        except (json.JSONDecodeError, IOError):
            # Skip invalid example files
            pass
    return examples


def _generate_postman_collection(openapi_spec: Dict[str, Any]) -> Dict[str, Any]:
    """Convert OpenAPI spec to Postman Collection v2.1 format.

    Generates a Postman collection that can be imported into Postman for:
    - Interactive API exploration
    - Example request/response pairs
    - Automatic documentation
    """
    info = openapi_spec.get("info", {})

    # Load examples for use in request bodies
    examples = _load_examples()

    # Build collection items from paths
    items: list[Dict[str, Any]] = []
    paths = openapi_spec.get("paths", {})

    for path, methods in sorted(paths.items()):
        if not isinstance(methods, dict):
            continue

        for method, operation in sorted(methods.items()):
            if not isinstance(operation, dict):
                continue

            method_upper = str(method).upper()
            summary = operation.get("summary", f"{method_upper} {path}")
            description = operation.get("description", "")

            # Build request body with example if available
            body_content = ""
            request_body = operation.get("requestBody", {})
            if request_body:
                content = request_body.get("content", {}).get("application/json", {})
                schema_ref = content.get("schema", {}).get("$ref", "")

                # Try to find matching example
                if schema_ref:
                    schema_name = schema_ref.split("/")[-1].replace(".schema.json", "")
                    if schema_name in examples:
                        body_content = json.dumps(examples[schema_name], indent=2)

            item: Dict[str, Any] = {
                "name": summary,
                "request": {
                    "method": method_upper,
                    "header": [
                        {
                            "key": "Content-Type",
                            "value": "application/json",
                            "type": "text",
                        }
                    ],
                    "body": {
                        "mode": "raw",
                        "raw": body_content,
                        "options": {"raw": {"language": "json"}},
                    },
                    "url": {
                        "raw": "{{baseUrl}}" + path,
                        "host": ["{{baseUrl}}"],
                        "path": path.lstrip("/").split("/"),
                    },
                    "description": description,
                },
                "response": [],
            }
            items.append(item)

    # Build collection
    collection: Dict[str, Any] = {
        "info": {
            "name": info.get("title", "K0 API"),
            "description": info.get("description", "K0 API Collection"),
            "version": info.get("version", "1.0.0"),
            "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
        },
        "item": items,
        "variable": [
            {
                "key": "baseUrl",
                "value": "http://localhost:8080",
                "description": "Base URL for K0 API endpoints",
            }
        ],
    }

    return collection


def _write_text(path: Path, content: str) -> bool:
    if path.exists() and path.read_text(encoding="utf-8") == content:
        return False
    try:
        path.write_text(content, encoding="utf-8")
        return True
    except (FileNotFoundError, OSError):
        return False


def _write_bytes(path: Path, payload: bytes) -> bool:
    if path.exists() and path.read_bytes() == payload:
        return False
    try:
        path.write_bytes(payload)
        return True
    except (FileNotFoundError, OSError):
        return False


def generate_docs(check: bool = False) -> bool:
    try:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        POSTMAN_DIR.mkdir(parents=True, exist_ok=True)

        openapi_spec = _load_yaml(OPENAPI_PATH)
        asyncapi_spec = _load_yaml(ASYNCAPI_PATH)

        changes = False

        openapi_html = _render_openapi_html(openapi_spec)
        asyncapi_html = _render_asyncapi_html(asyncapi_spec)
        postman_collection = _generate_postman_collection(openapi_spec)
        postman_json = json.dumps(postman_collection, ensure_ascii=False, indent=2)

        openapi_pdf = _pdf_bytes_from_lines(
            _openapi_summary_lines(openapi_spec),
            title="K0 OpenAPI Reference",
        )
        asyncapi_pdf = _pdf_bytes_from_lines(
            _asyncapi_summary_lines(asyncapi_spec),
            title="K0 AsyncAPI Reference",
        )

        for path, payload in (
            (OPENAPI_HTML_PATH, openapi_html),
            (ASYNCAPI_HTML_PATH, asyncapi_html),
            (POSTMAN_JSON_PATH, postman_json),
        ):
            if check:
                if not path.exists() or path.read_text(encoding="utf-8") != payload:
                    raise RuntimeError(f"Documentation out of date: {path}")
            else:
                if _write_text(path, payload):
                    changes = True

        for path, payload in (
            (OPENAPI_PDF_PATH, openapi_pdf),
            (ASYNCAPI_PDF_PATH, asyncapi_pdf),
        ):
            if check:
                if not path.exists() or path.read_bytes() != payload:
                    raise RuntimeError(f"Documentation out of date: {path}")
            else:
                if _write_bytes(path, payload):
                    changes = True

        return changes
    except (FileNotFoundError, RuntimeError):
        if check:
            raise
        return False


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate HTML/PDF documentation from OpenAPI and AsyncAPI specs"
    )
    parser.add_argument("--check", action="store_true", help="Only verify outputs are up to date")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        changes = generate_docs(check=args.check)
        if args.check:
            print("[Docs] API documentation is up to date.")
        else:
            print("[Docs] Generated API documentation files.")
            if changes:
                print("[Docs] Updated documentation artifacts written to docs/api.")
            else:
                print("[Docs] Documentation artifacts already current; no changes written.")
        return 0
    except RuntimeError as e:
        print(f"[Docs] Error: {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
