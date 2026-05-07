"""Google Calendar IFL MCP server (MS-5 PR#4).

Run as::

    python -m bridge.ifl.adapters.google_calendar.server

This is the *real* fastmcp server that satisfies the
``ifl.google_calendar.events.list.v1`` IFL contract. It exposes a
single tool, ``events_list``, whose request/response shape mirrors
the JSON Schemas under ``bridge/contracts/schemas/``.

Two modes of operation, selected at process start:

* **Production**: ``BRIDGE_GCAL_OAUTH_REFRESH_TOKEN``,
  ``BRIDGE_GCAL_OAUTH_CLIENT_ID``, and
  ``BRIDGE_GCAL_OAUTH_CLIENT_SECRET`` must all be set. The server
  exchanges the refresh token for an access token via
  :mod:`bridge.ifl.adapters.google_calendar.oauth` and then calls
  ``GET https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events``
  for each tool invocation.

* **Fixture**: ``BRIDGE_GCAL_FIXTURE_PATH`` points at a JSON file
  whose top level matches the response schema (``events`` array
  + optional ``next_page_token``). Used by contract tests and by
  the MS-5 exit round-trip test so they run without any network
  access. When set, OAuth env vars are ignored.

The server is intentionally tiny — production hardening
(pagination, rate limiting, retry, mTLS) lands in MS-8.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any


def _load_fixture(path: str) -> dict[str, Any]:
    fixture_path = Path(path)
    if not fixture_path.exists():
        raise FileNotFoundError(f"BRIDGE_GCAL_FIXTURE_PATH points at missing file: {path}")
    body = json.loads(fixture_path.read_text(encoding="utf-8"))
    if not isinstance(body, dict) or "events" not in body:
        raise ValueError("GCal fixture must be a JSON object with an 'events' key")
    return body


def _real_events_list(
    *,
    account_id: str,
    calendar_id: str,
    time_min: str,
    time_max: str,
    max_results: int,
    single_events: bool,
) -> dict[str, Any]:
    """Production path: exchange refresh token + call Google
    Calendar API. Imported lazily so fixture mode does not require
    httpx at module import time."""
    import httpx  # local import for fixture-only test runs

    from bridge.ifl.adapters.google_calendar.oauth import (
        exchange_refresh_token,
    )

    refresh = os.environ["BRIDGE_GCAL_OAUTH_REFRESH_TOKEN"]
    client_id = os.environ["BRIDGE_GCAL_OAUTH_CLIENT_ID"]
    client_secret = os.environ["BRIDGE_GCAL_OAUTH_CLIENT_SECRET"]
    token = exchange_refresh_token(
        refresh_token=refresh,
        client_id=client_id,
        client_secret=client_secret,
    )
    url = f"https://www.googleapis.com/calendar/v3/calendars/" f"{calendar_id}/events"
    params = {
        "timeMin": time_min,
        "timeMax": time_max,
        "maxResults": str(max_results),
        "singleEvents": "true" if single_events else "false",
    }
    headers = {"Authorization": f"{token.token_type} {token.access_token}"}
    response = httpx.get(url, params=params, headers=headers, timeout=10.0)
    response.raise_for_status()
    raw = response.json()
    return _normalize_google_response(raw)


def _normalize_google_response(raw: dict[str, Any]) -> dict[str, Any]:
    """Convert a Google Calendar v3 ``events.list`` response shape
    into the response shape declared by our IFL response schema.

    Only the minimal subset called out in the schema is preserved
    so unknown fields can never leak through to K0.
    """
    events_out: list[dict[str, Any]] = []
    for item in raw.get("items", []):
        if not isinstance(item, dict):
            continue
        ev: dict[str, Any] = {
            "id": str(item.get("id", "")),
            "summary": str(item.get("summary", "")),
            "start": _normalize_event_time(item.get("start") or {}),
            "end": _normalize_event_time(item.get("end") or {}),
        }
        if "description" in item:
            ev["description"] = str(item["description"])
        if "location" in item:
            ev["location"] = str(item["location"])
        if "status" in item and item["status"] in {
            "confirmed",
            "tentative",
            "cancelled",
        }:
            ev["status"] = item["status"]
        if "htmlLink" in item:
            ev["html_link"] = str(item["htmlLink"])
        events_out.append(ev)
    out: dict[str, Any] = {"events": events_out}
    if raw.get("nextPageToken"):
        out["next_page_token"] = str(raw["nextPageToken"])
    return out


def _normalize_event_time(raw: dict[str, Any]) -> dict[str, Any]:
    """Map Google's ``start``/``end`` shape (``date``, ``dateTime``,
    ``timeZone``) to our schema's snake_case shape."""
    out: dict[str, Any] = {}
    if "date" in raw:
        out["date"] = str(raw["date"])
    if "dateTime" in raw:
        out["date_time"] = str(raw["dateTime"])
    if "timeZone" in raw:
        out["time_zone"] = str(raw["timeZone"])
    return out


def events_list_handler(arguments: dict[str, Any]) -> dict[str, Any]:
    """Pure-Python entry point for the ``events_list`` tool.

    Exposed at module level so tests can call it directly without
    spinning up the full fastmcp transport. The fastmcp server below
    just delegates to this function.
    """
    account_id = str(arguments.get("account_id") or "")
    if not account_id:
        raise ValueError("account_id is required")
    calendar_id = str(arguments.get("calendar_id") or "primary")
    time_min = str(arguments.get("time_min") or "")
    time_max = str(arguments.get("time_max") or "")
    if not time_min or not time_max:
        raise ValueError("time_min and time_max are required")
    max_results = int(arguments.get("max_results") or 50)
    single_events = bool(arguments.get("single_events", True))

    fixture_path = os.environ.get("BRIDGE_GCAL_FIXTURE_PATH")
    if fixture_path:
        return _load_fixture(fixture_path)
    return _real_events_list(
        account_id=account_id,
        calendar_id=calendar_id,
        time_min=time_min,
        time_max=time_max,
        max_results=max_results,
        single_events=single_events,
    )


def _build_server() -> Any:
    """Build the fastmcp server with the ``events_list`` tool wired."""
    from fastmcp import FastMCP

    mcp = FastMCP("family-os-google-calendar")

    @mcp.tool(name="events_list")
    def events_list(
        account_id: str,
        time_min: str,
        time_max: str,
        calendar_id: str = "primary",
        max_results: int = 50,
        single_events: bool = True,
    ) -> dict[str, Any]:
        """List Google Calendar events in [time_min, time_max)."""
        return events_list_handler(
            {
                "account_id": account_id,
                "calendar_id": calendar_id,
                "time_min": time_min,
                "time_max": time_max,
                "max_results": max_results,
                "single_events": single_events,
            }
        )

    return mcp


def main() -> int:
    server = _build_server()
    server.run()  # stdio transport by default
    return 0


if __name__ == "__main__":
    sys.exit(main())
