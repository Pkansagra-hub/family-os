"""
k1.tools.family -- Production foundation for K1-native ("family") tool services.

This package houses the generalized primitives that every kernel-inbuilt
family tool app (Calendar, Health, Finance, IoT, ...) builds on.  All code
here is K1-resident: it must not import from ``bridge.*`` and must not
depend on K0 services at construction time (K1-hot / K0-optional pivot --
see KERNEL_BOOTUP_PLAN.md milestone M15 R-1..R-8).

Layers
------
* ``base``         -- ``BaseEntity`` (immutable persisted records) and
                      ``WriteContext`` (per-call user/session/policy frame).
* ``definition``   -- ``ToolDefinition`` + ``ActionSpec`` + ``FieldSpec``
                      + ``LLMHints`` + ``SSESpec`` (the declarative manifest
                      that drives Fabric registration, ACL evaluation, and
                      LLM tool-name resolution).
* ``ports``        -- Protocol definitions consumed by ``EventEmitter``,
                      ``NativeToolProvider``, and tests
                      (``IToolService``, ``IToolRegistryReader``,
                      ``ISsePublisher``, ``ISyncOutbox``).
* ``policy``       -- ``VisibilityPolicy`` and the default safety-band
                      gating rules for read/write/delete actions.
* ``acl``          -- ``filter_rows`` row-level ACL evaluator.
* ``events``       -- ``EventEmitter`` (envelope construction + best-effort
                      SSE publish + best-effort K0 sync outbox enqueue).

References
----------
* docs/plans/KERNEL_BOOTUP_PLAN.md §E15.0.1 -- BaseEntity / WriteContext
* docs/plans/KERNEL_BOOTUP_PLAN.md §E15.0.2 -- ToolDefinition
* docs/plans/KERNEL_BOOTUP_PLAN.md §E15.0.3 -- VisibilityPolicy + ACL
* docs/plans/KERNEL_BOOTUP_PLAN.md §E15.0.4 -- EventEmitter
"""

from k1.tools.family.acl import filter_rows
from k1.tools.family.base import (
    BaseEntity,
    Face,
    Role,
    SourceKind,
    Visibility,
    WriteContext,
    role_satisfies,
)
from k1.tools.family.base_service import BaseToolService
from k1.tools.family.bootstrap import FamilyToolsBundle, bootstrap_family_tools
from k1.tools.family.definition import (
    ActionKind,
    ActionSpec,
    Band,
    FieldSpec,
    LLMHints,
    SSESpec,
    ToolDefinition,
)
from k1.tools.family.events import EventEmitter
from k1.tools.family.idem import IdempotencyStore
from k1.tools.family.manifest import llm_tool_specs, openapi_paths, ui_manifest
from k1.tools.family.policy import VisibilityPolicy, default_policy
from k1.tools.family.ports import (
    IPolicyEvaluator,
    ISsePublisher,
    ISyncOutbox,
    IToolRegistryReader,
    IToolService,
)
from k1.tools.family.registry import ToolRegistry
from k1.tools.family.routes import build_router
from k1.tools.family.sse_adapters import (
    BusSsePublisher,
    LoggingSsePublisher,
    NullSsePublisher,
)
from k1.tools.family.storage import DEFAULT_DB_PATH, K1FamilyStore

__all__ = [
    # base
    "BaseEntity",
    "Face",
    "Role",
    "SourceKind",
    "Visibility",
    "WriteContext",
    "role_satisfies",
    # definition
    "ActionKind",
    "ActionSpec",
    "Band",
    "FieldSpec",
    "LLMHints",
    "SSESpec",
    "ToolDefinition",
    # policy / acl
    "VisibilityPolicy",
    "default_policy",
    "filter_rows",
    # events
    "EventEmitter",
    # ports
    "IPolicyEvaluator",
    "ISsePublisher",
    "ISyncOutbox",
    "IToolRegistryReader",
    "IToolService",
    # service backbone
    "BaseToolService",
    "IdempotencyStore",
    # registry / storage / manifest / routes
    "ToolRegistry",
    "K1FamilyStore",
    "DEFAULT_DB_PATH",
    "llm_tool_specs",
    "openapi_paths",
    "ui_manifest",
    "build_router",
    # sse adapters
    "BusSsePublisher",
    "LoggingSsePublisher",
    "NullSsePublisher",
    # bootstrap
    "FamilyToolsBundle",
    "bootstrap_family_tools",
]
