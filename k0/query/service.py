"""Query execution primitives for the query recall port."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, Sequence

from k0.query.common import DriverContext
from k0.query.drivers import DriverRegistry, build_default_registry

DEFAULT_SELECTOR_LIMIT = 8
MAX_SELECTOR_LIMIT = 256

__all__ = [
    "DEFAULT_SELECTOR_LIMIT",
    "MAX_SELECTOR_LIMIT",
    "QueryExecutionResult",
    "QueryAggregator",
]


class SelectorLike(Protocol):
    """Structural protocol describing the selector fields consumed by the executor."""

    topic: str | None
    limit: int | None
    cursor: int | None
    tenant_id: str | None
    space_id: str | None

    # Optional attributes that callers may provide; defaults handled via ``getattr``.
    type: str | None
    after: int | None


@dataclass(slots=True)
class SelectorBundle:
    """Envelope describing the results for a single selector."""

    index: int
    driver: str
    selector: Mapping[str, Any]
    items: list[dict[str, Any]]
    next_cursor: int | None
    latency_ms: float
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        selector_payload: dict[str, Any] = {
            key: value for key, value in self.selector.items() if value is not None
        }
        selector_payload["index"] = self.index
        selector_payload["driver"] = self.driver

        payload: dict[str, Any] = {
            "selector": selector_payload,
            "items": self.items,
            "next_cursor": self.next_cursor,
            "latency_ms": round(self.latency_ms, 3),
        }
        if self.metadata:
            payload["metadata"] = dict(self.metadata)
        return payload


@dataclass(slots=True)
class QueryExecutionResult:
    """Aggregate result produced by ``QueryAggregator``."""

    bundles: list[SelectorBundle]
    elapsed_ms: float
    consumed_top_k: int
    processed_selectors: int
    exhausted_time_budget: bool
    trace_nodes: list[dict[str, Any]] = field(default_factory=list)

    def bundle_payload(self) -> dict[str, Any]:
        return {"selectors": [bundle.as_dict() for bundle in self.bundles]}


class QueryAggregator:
    """Coordinate query drivers while respecting QoS budgets."""

    def __init__(
        self,
        *,
        registry: DriverRegistry | None = None,
        default_limit: int = DEFAULT_SELECTOR_LIMIT,
        max_limit: int = MAX_SELECTOR_LIMIT,
    ) -> None:
        if default_limit <= 0:
            msg = "default_limit must be positive"
            raise ValueError(msg)
        if max_limit < default_limit:
            msg = "max_limit must be greater than or equal to default_limit"
            raise ValueError(msg)
        self._default_limit = default_limit
        self._max_limit = max_limit
        self._registry = registry or build_default_registry(
            default_limit=default_limit,
            max_limit=max_limit,
        )

    def execute(
        self,
        selectors: Sequence[SelectorLike],
        *,
        space_id: str,
        tenant_id: str | None,
        time_budget_ms: int,
        top_k_budget: int,
    ) -> QueryExecutionResult:
        if time_budget_ms <= 0:
            return QueryExecutionResult(
                bundles=[],
                elapsed_ms=0.0,
                consumed_top_k=0,
                processed_selectors=0,
                exhausted_time_budget=True,
            )

        remaining_top_k = max(0, int(top_k_budget))
        total_elapsed_ms = 0.0
        consumed_top_k = 0
        processed_selectors = 0
        exhausted_time_budget = False
        bundles: list[SelectorBundle] = []
        trace_nodes: list[dict[str, Any]] = []

        if not selectors:
            return QueryExecutionResult(
                bundles=bundles,
                elapsed_ms=total_elapsed_ms,
                consumed_top_k=consumed_top_k,
                processed_selectors=processed_selectors,
                exhausted_time_budget=exhausted_time_budget,
                trace_nodes=trace_nodes,
            )

        for index, selector in enumerate(selectors):
            if remaining_top_k <= 0:
                trace_nodes.append(
                    {
                        "stage": "query.driver.skipped",
                        "selector_index": index,
                        "latency_ms": 0.0,
                        "items": 0,
                        "status": "top_k_exhausted",
                    }
                )
                break

            allowed_limit = self._resolve_limit(selector.limit, remaining_top_k)
            driver = self._registry.resolve(selector)
            context = DriverContext(
                space_id=space_id,
                tenant_id=tenant_id,
                selector_index=index,
                allowed_limit=allowed_limit,
                remaining_top_k=remaining_top_k,
                time_budget_ms=time_budget_ms,
                elapsed_ms=total_elapsed_ms,
            )

            execution = driver.execute(selector, context)
            bundle_metadata = dict(execution.metadata)
            bundle_metadata.setdefault("driver", execution.driver)

            bundles.append(
                SelectorBundle(
                    index=index,
                    driver=execution.driver,
                    selector=execution.selector,
                    items=execution.items,
                    next_cursor=execution.next_cursor,
                    latency_ms=execution.latency_ms,
                    metadata=bundle_metadata,
                )
            )

            trace_nodes.append(
                {
                    "stage": f"query.driver.{execution.driver}",
                    "selector_index": index,
                    "latency_ms": execution.latency_ms,
                    "items": len(execution.items),
                    "status": bundle_metadata.get("status", "ok"),
                }
            )

            consumed_top_k += execution.consumed_top_k
            remaining_top_k = max(0, remaining_top_k - execution.consumed_top_k)
            total_elapsed_ms += execution.latency_ms
            processed_selectors += 1

            exhausted_time_budget = execution.exhausted_time_budget or total_elapsed_ms >= time_budget_ms

            if exhausted_time_budget:
                break

            if remaining_top_k <= 0:
                break

        return QueryExecutionResult(
            bundles=bundles,
            elapsed_ms=total_elapsed_ms,
            consumed_top_k=consumed_top_k,
            processed_selectors=processed_selectors,
            exhausted_time_budget=exhausted_time_budget,
            trace_nodes=trace_nodes,
        )

    def _resolve_limit(self, requested: int | None, remaining_top_k: int) -> int:
        if remaining_top_k <= 0:
            return 0

        limit = requested if requested and requested > 0 else self._default_limit
        limit = min(int(limit), self._max_limit)

        if limit <= 0:
            return 0

        return max(1, min(limit, remaining_top_k))

