"""
tests.fixtures.capabilities.web_capabilities -- Web Search & Fetch via DuckDuckGo + httpx.

Adds real web capabilities to the Concierge's tool fabric:

Capabilities:
    tool.execute.web_search -- Search the web for information, news, local
    businesses, recipes, answers, etc.
    tool.execute.web_fetch  -- Fetch a URL and extract readable text content
    from the page. Used to read actual page content after web_search returns
    links.

Handler contract matches demo_capabilities:
    async (params: dict) -> dict with keys: success, data, artifact_type, duration_ms
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any

logger = logging.getLogger(__name__)

# =========================================================================
# Capability definitions
# =========================================================================

WEB_CAPABILITIES: list[dict[str, Any]] = [
    {
        "name": "tool.execute.web_search",
        "description": (
            "Search the web using DuckDuckGo. Find information, news, "
            "local businesses, restaurants, services, recipes, answers "
            "to questions, product reviews, directions, and anything "
            "else available on the internet. Returns titles, URLs, and "
            "short snippets. To read full page content, follow up with "
            "web_fetch on the best URLs."
        ),
        "required_inputs": ["query"],
        "optional_inputs": ["max_results", "region"],
        "has_side_effects": False,
        "estimated_cost": "free",
        "domain": "search",
    },
    {
        "name": "tool.execute.web_fetch",
        "description": (
            "Fetch a web page by URL and extract its readable text content. "
            "Use AFTER web_search to read the actual content of promising "
            "pages. Returns the page title and extracted text (truncated "
            "to max_chars). Ideal for getting restaurant menus, article "
            "details, business info, reviews, recipes, etc."
        ),
        "required_inputs": ["url"],
        "optional_inputs": ["max_chars"],
        "has_side_effects": False,
        "estimated_cost": "free",
        "domain": "search",
    },
]


# =========================================================================
# Real handler -- calls DuckDuckGo search API
# =========================================================================


async def web_search_handler(params: dict[str, Any]) -> dict[str, Any]:
    """Search the web via DuckDuckGo.

    Args:
        params: Must contain 'query'. Optional: 'max_results' (default 5),
                'region' (default 'us-en').

    Returns:
        Standard capability result dict with search results in 'data'.
    """
    query = params.get("query", "")
    if not query:
        return {
            "success": False,
            "error": "Missing required parameter: query",
            "data": None,
            "artifact_type": None,
            "duration_ms": 0,
        }

    max_results = min(params.get("max_results", 5), 10)  # Cap at 10
    region = params.get("region", "us-en")

    start = time.monotonic()
    try:
        from ddgs import DDGS

        raw_results = DDGS().text(query, region=region, max_results=max_results)

        results = []
        for r in raw_results:
            results.append(
                {
                    "title": r.get("title", ""),
                    "url": r.get("href", ""),
                    "snippet": r.get("body", ""),
                }
            )

        duration_ms = int((time.monotonic() - start) * 1000)
        logger.info(
            "web_search: query=%s results=%d duration=%dms",
            query[:60],
            len(results),
            duration_ms,
        )

        return {
            "success": True,
            "data": {
                "query": query,
                "results": results,
                "result_count": len(results),
            },
            "artifact_type": None,
            "duration_ms": duration_ms,
        }

    except Exception as e:
        duration_ms = int((time.monotonic() - start) * 1000)
        logger.error("web_search failed: %s", e, exc_info=True)
        return {
            "success": False,
            "error": f"Search failed: {e}",
            "data": None,
            "artifact_type": None,
            "duration_ms": duration_ms,
        }


# =========================================================================
# HTML text extraction (lightweight, no extra dependency)
# =========================================================================

# Tags whose entire content should be removed (not just the tags)
_STRIP_TAGS = re.compile(
    r"<\s*(script|style|noscript|svg|head|iframe|nav|header|footer|aside)[^>]*>.*?</\s*\1\s*>",
    re.DOTALL | re.IGNORECASE,
)
_HTML_TAG = re.compile(r"<[^>]+>")
_MULTI_SPACE = re.compile(r"[ \t]+")
_MULTI_NEWLINE = re.compile(r"\n{3,}")


def _extract_text_from_html(html: str) -> tuple[str, str]:
    """Extract readable text from raw HTML. Returns (title, body_text)."""
    import html as html_mod

    # Extract <title>
    title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.DOTALL | re.IGNORECASE)
    title = title_match.group(1).strip() if title_match else ""
    title = html_mod.unescape(_HTML_TAG.sub("", title))

    # Remove non-content tags entirely
    text = _STRIP_TAGS.sub(" ", html)
    # Strip remaining HTML tags
    text = _HTML_TAG.sub(" ", text)
    # Decode all HTML entities
    text = html_mod.unescape(text)
    # Normalize whitespace
    text = _MULTI_SPACE.sub(" ", text)
    text = _MULTI_NEWLINE.sub("\n\n", text)
    # Collapse lines
    lines = [ln.strip() for ln in text.splitlines()]
    text = "\n".join(ln for ln in lines if ln)

    return title, text


# =========================================================================
# web_fetch handler -- fetch a URL and extract readable text
# =========================================================================

# Safety: only allow http/https URLs
_ALLOWED_SCHEMES = {"http", "https"}
_FETCH_TIMEOUT = 10  # seconds
_DEFAULT_MAX_CHARS = 6000
_ABSOLUTE_MAX_CHARS = 12000


async def web_fetch_handler(params: dict[str, Any]) -> dict[str, Any]:
    """Fetch a web page and extract readable text content.

    Args:
        params: Must contain 'url'. Optional: 'max_chars' (default 6000).

    Returns:
        Standard capability result dict with page title and text in 'data'.
    """
    url = params.get("url", "").strip()
    if not url:
        return {
            "success": False,
            "error": "Missing required parameter: url",
            "data": None,
            "artifact_type": None,
            "duration_ms": 0,
        }

    # Validate URL scheme to prevent SSRF
    from urllib.parse import urlparse

    parsed = urlparse(url)
    if parsed.scheme not in _ALLOWED_SCHEMES:
        return {
            "success": False,
            "error": f"URL scheme '{parsed.scheme}' not allowed. Use http or https.",
            "data": None,
            "artifact_type": None,
            "duration_ms": 0,
        }
    # Block private/internal IPs
    hostname = parsed.hostname or ""
    if (
        hostname in ("localhost", "127.0.0.1", "0.0.0.0", "::1")
        or hostname.startswith("192.168.")
        or hostname.startswith("10.")
        or hostname.startswith("172.")
    ):
        return {
            "success": False,
            "error": "Fetching internal/private URLs is not allowed.",
            "data": None,
            "artifact_type": None,
            "duration_ms": 0,
        }

    max_chars = min(params.get("max_chars", _DEFAULT_MAX_CHARS), _ABSOLUTE_MAX_CHARS)

    start = time.monotonic()
    try:
        import httpx

        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=_FETCH_TIMEOUT,
            headers={
                "User-Agent": ("Mozilla/5.0 (compatible; FamilyOS/1.0; +https://familyos.ai)"),
                "Accept": "text/html,application/xhtml+xml,*/*",
            },
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()

        content_type = resp.headers.get("content-type", "")
        if "text/html" not in content_type and "application/xhtml" not in content_type:
            # Not HTML -- return raw text truncated
            raw_text = resp.text[:max_chars]
            duration_ms = int((time.monotonic() - start) * 1000)
            return {
                "success": True,
                "data": {
                    "url": url,
                    "title": "",
                    "content": raw_text,
                    "content_length": len(raw_text),
                    "truncated": len(resp.text) > max_chars,
                    "content_type": content_type,
                },
                "artifact_type": None,
                "duration_ms": duration_ms,
            }

        title, body_text = _extract_text_from_html(resp.text)
        truncated = len(body_text) > max_chars
        body_text = body_text[:max_chars]

        duration_ms = int((time.monotonic() - start) * 1000)
        logger.info(
            "web_fetch: url=%s title=%s chars=%d truncated=%s duration=%dms",
            url[:80],
            title[:40],
            len(body_text),
            truncated,
            duration_ms,
        )

        return {
            "success": True,
            "data": {
                "url": url,
                "title": title,
                "content": body_text,
                "content_length": len(body_text),
                "truncated": truncated,
                "content_type": "text/html",
            },
            "artifact_type": None,
            "duration_ms": duration_ms,
        }

    except Exception as e:
        duration_ms = int((time.monotonic() - start) * 1000)
        logger.error("web_fetch failed: url=%s err=%s", url[:80], e, exc_info=True)
        return {
            "success": False,
            "error": f"Fetch failed: {e}",
            "data": None,
            "artifact_type": None,
            "duration_ms": duration_ms,
        }


# =========================================================================
# Handler map
# =========================================================================

WEB_HANDLERS: dict[str, Any] = {
    "tool.execute.web_search": web_search_handler,
    "tool.execute.web_fetch": web_fetch_handler,
}


# =========================================================================
# Registration helper
# =========================================================================


def register_web_capabilities(registry: Any) -> int:
    """Register web search capabilities into an existing CapabilityRegistry.

    Args:
        registry: CapabilityRegistry instance with .register(cap, handler) method.

    Returns:
        Number of capabilities registered.
    """
    count = 0
    for cap in WEB_CAPABILITIES:
        name = cap["name"]
        handler = WEB_HANDLERS.get(name)
        if handler:
            registry.register(cap, handler)
            count += 1
            logger.info("Registered web capability: %s", name)
    return count
