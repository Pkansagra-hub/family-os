"""
K1 POC -- Tool Schema Catalog & Dispatcher
============================================

M04: Tool Schema Catalog for the Concierge POC.

Re-exports:
  schemas:       FRONT_TOOL_SCHEMAS, BACK_TOOL_SCHEMAS, individual schemas
  back tiers:    BACK_TIER_ALLOWLISTS
  result:        ToolResult, tool_result_to_message
  parallelism:   PARALLEL_SAFE_GROUPS, ALWAYS_SEQUENTIAL, can_parallelize, partition_calls
  impl:          ToolContext, TOOL_REGISTRY, execute_tool
  dispatcher:    ToolDispatcher, create_front_dispatcher, create_back_dispatcher
"""

from __future__ import annotations

# -- Dispatcher --
from poc.k1_poc.tools.dispatcher import (
    ToolDispatcher,
    create_back_dispatcher,
    create_front_dispatcher,
)

# -- Implementations --
from poc.k1_poc.tools.implementations import TOOL_REGISTRY, ToolContext, execute_tool

# -- Parallelism --
from poc.k1_poc.tools.parallelism import (
    ALWAYS_SEQUENTIAL,
    PARALLEL_SAFE_GROUPS,
    can_parallelize,
    partition_calls,
)

# -- Result protocol --
from poc.k1_poc.tools.result_protocol import ToolResult, tool_result_to_message

# -- Back schemas --
from poc.k1_poc.tools.schemas_back import (
    BACK_TIER_ALLOWLISTS,
    BACK_TOOL_SCHEMAS,
    DISCOVER_CAPABILITIES_SCHEMA,
    EXECUTE_WORKFLOW_SCHEMA,
    INVOKE_CAPABILITY_SCHEMA,
    SPAWN_VIA_FABRIC_SCHEMA,
    SUBMIT_RESULT_SCHEMA,
)

# -- Front schemas --
from poc.k1_poc.tools.schemas_front import (
    DISPATCH_TASK_SCHEMA,
    FRONT_TOOL_SCHEMAS,
    PROMOTE_BELIEF_SCHEMA,
    RECALL_MEMORY_SCHEMA,
    REFINE_AFFECT_SCHEMA,
    SUMMARIZE_CONTEXT_SCHEMA,
    UPDATE_BELIEFS_SCHEMA,
    UPDATE_CLARIFICATIONS_SCHEMA,
    UPDATE_NARRATIVE_SCHEMA,
    UPDATE_SCOREBOARD_SCHEMA,
)

__all__ = [
    # Front schemas
    "FRONT_TOOL_SCHEMAS",
    "UPDATE_BELIEFS_SCHEMA",
    "UPDATE_SCOREBOARD_SCHEMA",
    "UPDATE_CLARIFICATIONS_SCHEMA",
    "UPDATE_NARRATIVE_SCHEMA",
    "REFINE_AFFECT_SCHEMA",
    "PROMOTE_BELIEF_SCHEMA",
    "RECALL_MEMORY_SCHEMA",
    "SUMMARIZE_CONTEXT_SCHEMA",
    "DISPATCH_TASK_SCHEMA",
    # Back schemas
    "BACK_TOOL_SCHEMAS",
    "BACK_TIER_ALLOWLISTS",
    "DISCOVER_CAPABILITIES_SCHEMA",
    "INVOKE_CAPABILITY_SCHEMA",
    "SPAWN_VIA_FABRIC_SCHEMA",
    "EXECUTE_WORKFLOW_SCHEMA",
    "SUBMIT_RESULT_SCHEMA",
    # Result protocol
    "ToolResult",
    "tool_result_to_message",
    # Parallelism
    "PARALLEL_SAFE_GROUPS",
    "ALWAYS_SEQUENTIAL",
    "can_parallelize",
    "partition_calls",
    # Implementations
    "ToolContext",
    "TOOL_REGISTRY",
    "execute_tool",
    # Dispatcher
    "ToolDispatcher",
    "create_front_dispatcher",
    "create_back_dispatcher",
]
