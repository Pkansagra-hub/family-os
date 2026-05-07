"""Google Calendar IFL MCP adapter (MS-5 PR#4).

This package ships the *real* MCP server for the
``ifl.google_calendar.events.list.v1`` IFL contract:

* :mod:`bridge.ifl.adapters.google_calendar.server` — fastmcp server
  exposing the ``events_list`` tool. Production mode talks to the
  Google Calendar REST API via httpx using an OAuth refresh token
  fetched from the bridge credential vault at ``mcp/initialize``
  time. Test mode replays a recorded fixture file referenced via
  ``BRIDGE_GCAL_FIXTURE_PATH`` so contract tests run hermetically
  without network access.

* :mod:`bridge.ifl.adapters.google_calendar.oauth` — minimal helper
  that exchanges a refresh token for an access token. Real RFC 6749
  §6 flow against ``https://oauth2.googleapis.com/token``.

* :mod:`bridge.ifl.adapters.google_calendar.consent` — append-only
  consent ledger. Records (account_id, scope, granted_at,
  granted_by) tuples so K1 can prove the user authorized the
  read scope before adapter start.

K1 ↔ K0 fan-out:
    The adapter is launched per-account (``mcp.multi_instance: true``,
    ``adapter_id_pattern: google_calendar_<account_id>``). Once a tool
    call returns, K0 normalizes the response into ``MemoryAtom`` rows
    and drives the existing P02 write-ingest pipeline via the bus
    (no new K0 HTTP route — locked decision #7).
"""

from __future__ import annotations

__all__ = (
    "ADAPTER_ID_PREFIX",
    "TOOL_NAME",
)

#: Canonical adapter-id prefix; full id is ``f"{PREFIX}{account_id}"``.
ADAPTER_ID_PREFIX = "google_calendar_"

#: Single tool exposed by the server.
TOOL_NAME = "events_list"
