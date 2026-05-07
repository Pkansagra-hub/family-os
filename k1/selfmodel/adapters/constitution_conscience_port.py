"""Default ``IConsciencePort`` adapter (M10.E1.I2).

Resolves the actor's conscience digest by:

1. Looking up the actor's role via a caller-supplied function.
2. Reading the active constitution body via a caller-supplied
   function (typically wired to ``ConstitutionService.get_active``).
3. Calling :func:`get_conscience_bucket` and packaging the result
   as a :class:`ConscienceDigest`.

The adapter is deliberately stateless and dependency-free apart from
the two injected callables. It does NOT cache -- the constitution
service already caches its own reads.
"""

from __future__ import annotations

from typing import Callable, Mapping

from k1.selfmodel.contracts.conscience import ConscienceDigest
from k1.selfmodel.contracts.constitution_body import get_conscience_bucket
from k1.selfmodel.ports.conscience import IConsciencePort

__all__ = ["ConstitutionConsciencePort"]


# Type aliases -- callers wire these to whatever lives in their graph.
RoleResolverFn = Callable[[str], str]  # actor_id -> role
ConstitutionBodyFn = Callable[[], Mapping[str, object]]  # () -> active body


class ConstitutionConsciencePort(IConsciencePort):
    """Default adapter: derive ``ConscienceDigest`` from the active constitution."""

    __slots__ = ("_role_for_actor", "_load_body")

    def __init__(
        self,
        *,
        role_for_actor: RoleResolverFn,
        load_constitution_body: ConstitutionBodyFn,
    ) -> None:
        if role_for_actor is None:
            raise ValueError("role_for_actor is required")
        if load_constitution_body is None:
            raise ValueError("load_constitution_body is required")
        self._role_for_actor = role_for_actor
        self._load_body = load_constitution_body

    # ------------------------------------------------------------------
    def get_digest(
        self,
        actor_id: str,
        *,
        T_ms: int,  # noqa: ARG002 -- reserved for future TTL caching
        device_id: str | None = None,  # noqa: ARG002 -- reserved for per-device overrides
    ) -> ConscienceDigest:
        if not isinstance(actor_id, str) or not actor_id:
            return ConscienceDigest()
        role = self._role_for_actor(actor_id) or "member"
        body = self._load_body() or {}
        bucket = get_conscience_bucket(body, role=role)
        return ConscienceDigest(
            forbidden_acts=bucket.forbidden,
            must_ask_acts=bucket.must_ask,
            soft_warn_acts=bucket.soft_warn,  # M14.E1.I1
            risk_overrides=dict(bucket.risk_overrides),
            protections=(),
            tier_floor=dict(bucket.tier_floor),
        )
