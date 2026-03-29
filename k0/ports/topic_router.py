"""Topic-aware outbox routing for the command port.

Replaces the hardcoded DEFAULT_OUTBOX_DRIVER = "st_epi" with a routing table
that resolves command topics to the correct outbox driver, bus topic, and pipeline.

Contract: k0/contracts/taxonomies/outbox_routing.yaml
Milestone: M2 Epic 2.9
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path
from typing import Sequence

import yaml

logger = logging.getLogger(__name__)

# -- Default contract file path ------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_ROUTING_YAML = _REPO_ROOT / "k0" / "contracts" / "taxonomies" / "outbox_routing.yaml"


class UnknownTopicError(Exception):
    """Raised when a command topic has no matching route."""

    def __init__(self, topic: str) -> None:
        self.topic = topic
        super().__init__(f"No route for command topic: {topic}")


@dataclass(slots=True, frozen=True)
class RouteResult:
    """Resolved route for a command topic."""

    outbox_driver: str
    bus_topic: str
    pipeline: str | None
    priority: str
    inline_body_limit: int


class TopicRouter:
    """Resolves command topics to outbox routes using outbox_routing.yaml.

    Loaded once at startup. Resolution: exact match first, then glob, then reject.
    Thread-safe after construction (all state is immutable after __init__).
    """

    def __init__(
        self,
        *,
        routing_yaml_path: Path | None = None,
    ) -> None:
        self._routing_yaml = routing_yaml_path or _DEFAULT_ROUTING_YAML

        raw = yaml.safe_load(self._routing_yaml.read_text(encoding="utf-8"))
        config = raw["outbox_routing"]

        self._default_inline_body_limit: int = config.get("default_inline_body_limit", 4096)

        # Parse routes
        self._exact_routes: dict[str, RouteResult] = {}
        self._glob_routes: list[tuple[str, RouteResult]] = []

        for entry in config.get("routes", []):
            route = RouteResult(
                outbox_driver=entry["outbox_driver"],
                bus_topic=entry["bus_topic"],
                pipeline=entry.get("pipeline"),
                priority=entry.get("priority", "NORMAL"),
                inline_body_limit=entry.get("inline_body_limit", self._default_inline_body_limit),
            )

            match_type = entry.get("match_type", "exact")
            pattern = entry["pattern"]

            if match_type == "exact":
                self._exact_routes[pattern] = route
            else:
                self._glob_routes.append((pattern, route))

        # Parse priority levels for numeric ordering
        self._priority_numeric: dict[str, int] = {}
        for name, level in config.get("priority_levels", {}).items():
            if isinstance(level, dict):
                self._priority_numeric[name] = level.get("numeric", 99)

        logger.info(
            "TopicRouter loaded: %d exact routes, %d glob routes",
            len(self._exact_routes),
            len(self._glob_routes),
        )

    def resolve(self, topic: str) -> RouteResult:
        """Resolve a command topic to its outbox route.

        Resolution order:
        1. Exact match on pattern
        2. Glob match (fnmatch style)
        3. Raise UnknownTopicError

        Args:
            topic: Command topic string (e.g. "memory.write", "ifl.health.fitbit.hr")

        Returns:
            RouteResult with outbox_driver, bus_topic, pipeline, priority

        Raises:
            UnknownTopicError: No matching route found
        """
        # Exact match first
        route = self._exact_routes.get(topic)
        if route is not None:
            return route

        # Glob match
        for pattern, route in self._glob_routes:
            if fnmatch(topic, pattern):
                return route

        raise UnknownTopicError(topic)

    def resolve_or_none(self, topic: str) -> RouteResult | None:
        """Like resolve() but returns None instead of raising on unknown topic."""
        try:
            return self.resolve(topic)
        except UnknownTopicError:
            return None

    def known_routes(self) -> Sequence[str]:
        """Return list of all registered exact route patterns."""
        return list(self._exact_routes.keys())

    def priority_numeric(self, priority_name: str) -> int:
        """Convert priority name to numeric value (lower = higher priority)."""
        return self._priority_numeric.get(priority_name, 99)
