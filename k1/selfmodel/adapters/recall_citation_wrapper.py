"""Adapter: wrap a concierge ``recall_fn`` so its results become a CitationPack.

Replaces ``ToolContext.recall_fn`` at session bootstrap (M5 P3.5).
The wrapper is **back-compat-friendly**:

* Default mode (``mode="pack"``): returns a list with a single dict
  ``{"citation_pack": {...}, "memories": [...]}`` so that the
  ``recall_memory`` tool ("data": {"memories": result, "count": ...})
  surfaces ``CitationPack`` to the LLM **and** still works for any
  callsite that just wanted the raw rows.
* ``mode="passthrough"``: identity wrapper — used by tests and any
  legacy caller that explicitly requests the unwrapped behaviour.

The wrapper preserves the exact ``recall_fn`` signature
``(query: str, memory_types: list[str], max_results: int) -> list[dict]``
and supports both sync and async inner functions.
"""

from __future__ import annotations

import inspect as _inspect
import logging
from collections.abc import Callable, Sequence
from typing import Any, Literal

from k1.selfmodel.service.citation_builder import CitationPackBuilder

__all__ = ["RecallCitationWrapper"]

logger = logging.getLogger(__name__)

WrapperMode = Literal["pack", "passthrough"]


class RecallCitationWrapper:
    """Wrap a concierge recall callback so the LLM sees a CitationPack."""

    __slots__ = ("_inner", "_actor_id", "_builder", "_mode")

    def __init__(
        self,
        *,
        inner: Callable[..., Any],
        actor_id: str,
        builder: CitationPackBuilder | None = None,
        mode: WrapperMode = "pack",
    ) -> None:
        if inner is None or not callable(inner):
            raise ValueError("inner recall_fn must be callable")
        if not actor_id or not isinstance(actor_id, str):
            raise ValueError("actor_id must be a non-empty string")
        if mode not in ("pack", "passthrough"):
            raise ValueError(f"mode must be 'pack' or 'passthrough', got {mode!r}")
        self._inner = inner
        self._actor_id = actor_id
        self._builder = builder or CitationPackBuilder()
        self._mode = mode

    # ------------------------------------------------------------------
    # Callable surface — matches recall_fn signature exactly.
    # ------------------------------------------------------------------
    def __call__(
        self,
        query: str,
        memory_types: Sequence[str],
        max_results: int,
    ) -> Any:
        result = self._inner(query, memory_types, max_results)
        if _inspect.isawaitable(result):
            return self._await_and_wrap(result)
        return self._wrap(result)

    async def _await_and_wrap(self, awaitable):
        rows = await awaitable
        return self._wrap(rows)

    # ------------------------------------------------------------------
    # Wrapping
    # ------------------------------------------------------------------
    def _wrap(self, rows: Any) -> Any:
        rows = rows or []
        if not isinstance(rows, list):
            try:
                rows = list(rows)
            except TypeError:
                logger.warning(
                    "RecallCitationWrapper  inner returned non-iterable %r; coercing to []",
                    type(rows).__name__,
                )
                rows = []

        if self._mode == "passthrough":
            return rows

        try:
            pack = self._builder.wrap(self._actor_id, rows)
        except Exception:
            logger.exception("RecallCitationWrapper  builder failed; falling back to passthrough")
            return rows

        # Compose the response so concierge's recall_memory tool can
        # serialize it AND back-compat callers still find the raw rows.
        return [
            {
                "citation_pack": _pack_to_dict(pack),
                "memories": rows,
            }
        ]


def _pack_to_dict(pack) -> dict[str, Any]:
    """Render a CitationPack as a JSON-serialisable dict."""
    return {
        "actor_id": pack.actor_id,
        "composed_at_ms": pack.composed_at_ms,
        "citations": [
            {
                "citation_id": c.citation_id,
                "source_layer": c.source_layer,
                "projection_revision": c.projection_revision,
                "freshness": c.freshness,
                "content_excerpt": c.content_excerpt,
                "confidence": c.confidence,
                "payload": dict(c.payload),
            }
            for c in pack.citations
        ],
    }
