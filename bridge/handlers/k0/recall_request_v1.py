"""Hand-written K0 consumer impl for the ``recall.request.v1`` contract.

The generated module
:mod:`bridge._generated.k0.handlers.recall_request_v1` defines a
``register_handlers(runtime, impl=...)`` entry-point. This module
provides the concrete ``impl`` callable that takes the validated
:class:`bridge._generated.k0.models.recall_request_v1.RecallRequestV1`
payload, runs it through :class:`k0.query.service.QueryAggregator`,
and returns a JSON-serialisable dict shaped as
:class:`bridge._generated.k0.models.recall_response_v1.RecallResponseV1`.

Keeping the impl outside the generated tree means regeneration never
overwrites business logic. Per the MS-3c contract design, this wiring
is the only line that knows about both K0 internals and the bridge
contract — it sits at the boundary by design.

Note: this is the *bridge* recall path. The legacy
``POST /k0/query.recall`` route in :mod:`k0.ports.query` retains its
QoS/policy enforcement for non-bridge callers; the bridge surface here
relies on the bridge envelope layer for those concerns.
"""

from __future__ import annotations

import logging
import time
from types import SimpleNamespace
from typing import Any

from bridge._generated.k0.handlers.recall_request_v1 import register_handlers as _register_generated
from bridge._generated.k0.models.recall_request_v1 import RecallRequestV1
from bridge._generated.k0.models.recall_response_v1 import RecallResponseV1
from bridge.runtime import BridgeRuntime
from k0.query.service import QueryAggregator

_log = logging.getLogger("bridge.k0.handlers.recall_request_v1")


def _selector_to_namespace(s: Any) -> SimpleNamespace:
    """Translate a generated ``RecallSelector`` into the structural
    ``SelectorLike`` shape expected by :class:`QueryAggregator`.

    The generated model declares ``cursor`` / ``after`` as strings while
    QueryAggregator's drivers expect ``int | None`` for cursors. We
    coerce when the value is a digit string and otherwise drop it (the
    drivers treat ``None`` as "unbounded").
    """

    def _maybe_int(v: Any) -> int | None:
        if v is None:
            return None
        if isinstance(v, int):
            return v
        if isinstance(v, str) and v.isdigit():
            return int(v)
        return None

    return SimpleNamespace(
        type=s.type.value if s.type is not None else None,
        topic=s.topic,
        limit=int(s.limit) if s.limit is not None else None,
        cursor=_maybe_int(s.cursor),
        after=_maybe_int(s.after),
        tenant_id=None,
        space_id=None,
        query=s.query,
    )


def _bundles_to_hits(
    bundles: list[Any], *, max_results: int
) -> tuple[list[dict[str, Any]], int, bool]:
    """Flatten driver bundles into ``RecallHit`` dicts.

    Returns ``(hits, total, truncated)`` where ``total`` is the total
    item count across all bundles before truncation.
    """
    hits: list[dict[str, Any]] = []
    total = 0
    for bundle in bundles:
        selector_type = None
        sel = bundle.selector
        if isinstance(sel, dict):
            selector_type = sel.get("type")
        else:  # pragma: no cover - defensive
            selector_type = getattr(sel, "type", None)

        source = bundle.driver
        meta_source = bundle.metadata.get("source") if bundle.metadata else None
        if meta_source:
            source = str(meta_source)

        for item in bundle.items:
            total += 1
            atom_id = (
                item.get("payload_sha256")
                or item.get("atom_id")
                or item.get("id")
                or f"{source}:{item.get('wal_pos', total)}"
            )
            score_raw = item.get("score")
            if isinstance(score_raw, (int, float)):
                score = max(0.0, min(1.0, float(score_raw)))
            else:
                score = 1.0
            hit: dict[str, Any] = {
                "atom_id": str(atom_id),
                "content": dict(item) if isinstance(item, dict) else {"value": item},
                "score": score,
                "source": str(source),
            }
            if selector_type:
                hit["selector_type"] = str(selector_type)
            cursor = bundle.next_cursor
            if cursor is not None:
                hit["cursor"] = str(cursor)
            hits.append(hit)

    truncated = False
    if max_results > 0 and len(hits) > max_results:
        hits = hits[:max_results]
        truncated = True
    return hits, total, truncated


async def handle_recall_request_v1(payload: RecallRequestV1) -> dict[str, Any]:
    """Run a validated recall request through K0's query aggregator."""
    _log.info(
        "k0.recall_request_v1.received",
        extra={
            "topic": "recall.request.v1",
            "selectors": len(payload.selectors),
            "space_id": payload.space_id,
            "trace_id": payload.trace_id,
        },
    )

    selectors = [_selector_to_namespace(s) for s in payload.selectors]
    aggregator = QueryAggregator()

    started_ns = time.monotonic_ns()
    execution = await aggregator.execute(
        selectors,  # type: ignore[arg-type]
        space_id=payload.space_id,
        tenant_id=payload.tenant_id,
        time_budget_ms=int(payload.max_latency_ms),
        top_k_budget=int(payload.max_results),
    )
    elapsed_ms = (time.monotonic_ns() - started_ns) / 1_000_000

    hits, total, truncated = _bundles_to_hits(
        execution.bundles, max_results=int(payload.max_results)
    )
    if execution.exhausted_time_budget:
        truncated = True

    response = RecallResponseV1(
        hits=hits,  # type: ignore[arg-type]
        total=total,
        latency_ms=int(max(execution.elapsed_ms, elapsed_ms)),
        truncated=truncated,
        trace_id=payload.trace_id,
    )
    return response.model_dump(mode="json", by_alias=True)


def install(runtime: BridgeRuntime) -> None:
    """Register the K0-side handler on ``runtime``."""
    _register_generated(runtime, impl=handle_recall_request_v1)
