"""
k1.bus.middleware.default_registry -- DEFAULT_TOPIC_REGISTRY singleton.

Lazy-initialised :class:`TopicRegistry` pre-populated with every
top-level ``k1.*`` topic prefix used in production.  Wired into
:func:`BusFactory.create_local_ordered` by default (M7.3 / B07) so the
:class:`TopicValidationMiddleware` can flag misrouted or typo'd topics
in development without operators having to opt in.

Validation mode is soft: unknown topics emit a ``WARNING`` log but are
still delivered.  Schema validators are not registered here -- callers
that want strict per-payload validation must build their own registry.

The list of prefixes is intentionally permissive: registering broad
``k1.<subsystem>.`` prefixes covers the dynamic-topic patterns
(``k1.agent.{id}.delta.v1``, ``k1.session.{sid}.turn.completed.v1``,
etc.) without introducing import dependencies on every K1 subsystem.
"""

from __future__ import annotations

from threading import Lock

from k1.bus.middleware.topic_validation import TopicRegistry

__all__ = ["get_default_registry"]


# Top-level k1.* prefixes covering every production subsystem and
# development/test topic family.  Sorted for readability.
_DEFAULT_PREFIXES: tuple[str, ...] = (
    # Core subsystems
    "k1.affect.",
    "k1.agent.",
    "k1.bench.",  # benchmark suites (round-trip, perf)
    "k1.capability.",
    "k1.capsule.",
    "k1.concierge.",
    "k1.constitution.",
    "k1.dag.",
    "k1.dead_letter.",
    "k1.delta.",
    "k1.fabric.",
    "k1.feedback.",
    "k1.hil.",
    "k1.hipp.",
    "k1.hitl.",
    "k1.identity.",
    "k1.intent.",
    "k1.internal.",
    "k1.kernel.",
    "k1.mcp.",
    "k1.memory.",
    "k1.metric.",
    "k1.mw.",  # memory_writer pipeline
    "k1.observability.",
    "k1.orchestration.",
    "k1.phase1.",
    "k1.plan.",
    "k1.planner.",
    "k1.policy.",
    "k1.proactive.",
    "k1.response.",
    "k1.risk.",
    "k1.selfmodel.",
    "k1.session.",
    "k1.task.",
    "k1.test.",  # synthetic test topics (silences warnings in unit tests)
    "k1.tool.",
    "k1.ui.",
    "k1.warmup.",  # benchmark warmup
    "k1.weave.",
)


_registry: TopicRegistry | None = None
_lock = Lock()


def get_default_registry() -> TopicRegistry:
    """Return the lazy-initialised default :class:`TopicRegistry`.

    Thread-safe; idempotent.  All callers share a single registry
    instance so registrations made by tests/extensions persist for the
    process lifetime.
    """
    global _registry
    if _registry is not None:
        return _registry
    with _lock:
        if _registry is None:
            r = TopicRegistry()
            for prefix in _DEFAULT_PREFIXES:
                r.register_prefix(prefix)
            _registry = r
        return _registry
