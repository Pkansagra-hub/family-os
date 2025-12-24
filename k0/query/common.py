"""Common data structures for the query driver SPI."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Mapping, MutableMapping, Protocol, Sequence


@dataclass(slots=True)
class DriverContext:
    """Execution context passed to every query driver."""

    space_id: str
    tenant_id: str | None
    selector_index: int
    allowed_limit: int
    remaining_top_k: int
    time_budget_ms: int
    elapsed_ms: float


@dataclass(slots=True)
class DriverExecution:
    """Result returned by a query driver."""

    driver: str
    selector_index: int
    selector: Mapping[str, Any]
    items: list[dict[str, Any]] = field(default_factory=list)
    next_cursor: int | None = None
    latency_ms: float = 0.0
    consumed_top_k: int = 0
    exhausted_time_budget: bool = False
    metadata: MutableMapping[str, Any] = field(default_factory=dict)


class QueryDriver(Protocol):
    """Protocol implemented by all query recall drivers."""

    name: str

    def supports(self, selector: Any) -> bool:  # pragma: no cover - protocol stub
        """Return ``True`` when the driver can service the selector."""

    def execute(
        self, selector: Any, context: DriverContext
    ) -> Awaitable[DriverExecution]:  # pragma: no cover - protocol stub
        """Execute a recall for the selector and return a :class:`DriverExecution`."""
        ...


SelectorSequence = Sequence[Any]
