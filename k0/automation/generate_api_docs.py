"""API documentation generator for OpenAPI and AsyncAPI specifications.

This automation script generates human-readable documentation from contract
specifications in both HTML and PDF formats using:
- ReDoc for OpenAPI rendering
- AsyncAPI generator for event schema documentation
- WeasyPrint for PDF conversion with reproducible timestamps

Usage:
    python -m k0.automation.generate_api_docs
    python -m k0.automation.generate_api_docs --output-dir <path>

Outputs:
    - docs/api/openapi.html    (interactive OpenAPI docs)
    - docs/api/openapi.pdf     (printable OpenAPI docs)
    - docs/api/asyncapi.html   (event schema docs)
    - docs/api/asyncapi.pdf    (printable event schema docs)

Exit Codes:
    0 - Documentation generated successfully
    1 - Generation failed (missing deps, invalid schemas, etc.)
"""

from __future__ import annotations

import argparse
import importlib
import io
import json
import textwrap
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Sequence, cast

import yaml

STATIC_DOC_TIMESTAMP = datetime(2024, 1, 1, tzinfo=timezone.utc)
STATIC_DOC_TIMESTAMP_LITERAL = "D:20240101000000Z"

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS_DIR = REPO_ROOT / "k0" / "contracts"
OPENAPI_PATH = CONTRACTS_DIR / "openapi.k0.yaml"
ASYNCAPI_PATH = CONTRACTS_DIR / "asyncapi.events.yaml"
OUTPUT_DIR = REPO_ROOT / "docs" / "api"
OPENAPI_HTML_PATH = OUTPUT_DIR / "openapi.html"
ASYNCAPI_HTML_PATH = OUTPUT_DIR / "asyncapi.html"
OPENAPI_PDF_PATH = OUTPUT_DIR / "openapi.pdf"
ASYNCAPI_PDF_PATH = OUTPUT_DIR / "asyncapi.pdf"

REDOC_CDN = "https://cdn.redoc.ly/redoc/latest/bundles/redoc.standalone.js"


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
    pretty_json = json.dumps(spec, ensure_ascii=False, indent=2)
    escaped = (
        pretty_json.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '  <meta charset="utf-8" />\n'
        "  <title>K0 AsyncAPI Reference</title>\n"
        "  <style>body{font-family:monospace;background:#0f172a;color:#e2e8f0;padding:1.5rem;}"
        "pre{white-space:pre-wrap;word-break:break-word;}h1{font-size:1.6rem;margin-bottom:1rem;}</style>\n"
        "</head>\n"
        "<body>\n"
        "  <h1>K0 AsyncAPI Specification</h1>\n"
        "  <pre>" + escaped + "</pre>\n"
        "</body>\n"
        "</html>\n"
    )


def _load_fpdf_class() -> Any:
    try:
        module = importlib.import_module("fpdf")
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "fpdf2 dependency is required. Install via requirements.txt"
        ) from exc
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
                raise RuntimeError(
                    f"Failed to render PDF segment: {segment!r}"
                ) from exc
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
            method_map = cast(dict[str, Any], methods)
            for method in sorted(method_map.keys()):
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


def _write_text(path: Path, content: str) -> bool:
    if path.exists() and path.read_text(encoding="utf-8") == content:
        return False
    path.write_text(content, encoding="utf-8")
    return True


def _write_bytes(path: Path, payload: bytes) -> bool:
    if path.exists() and path.read_bytes() == payload:
        return False
    path.write_bytes(payload)
    return True


def generate_docs(check: bool = False) -> bool:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    openapi_spec = _load_yaml(OPENAPI_PATH)
    asyncapi_spec = _load_yaml(ASYNCAPI_PATH)

    changes = False

    openapi_html = _render_openapi_html(openapi_spec)
    asyncapi_html = _render_asyncapi_html(asyncapi_spec)
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


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate HTML/PDF documentation from OpenAPI and AsyncAPI specs"
    )
    parser.add_argument(
        "--check", action="store_true", help="Only verify outputs are up to date"
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
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


if __name__ == "__main__":
    raise SystemExit(main())
