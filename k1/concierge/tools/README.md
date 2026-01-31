# K1 Concierge Tools Module (Layer 2: Orchestration - Tool Management)

## Overview

The `concierge/tools/` module implements the tool registry and tool call management for the ConciergeAgent. This module provides centralized tool discovery, capability matching, schema validation, and tool call orchestration to support the ConciergeAgent's routing decisions and task execution.

## Purpose

- **Tool Registry**: Centralized repository of all available tools with metadata (schemas, costs, capabilities)
- **Capability Matching**: Match agent capabilities to available tools based on security and privacy requirements
- **Schema Validation**: Validate tool inputs and outputs against defined schemas
- **Tool Call Orchestration**: Manage tool calls to Orchestrator with proper batching and error handling
- **Prompt Registry Integration**: Match planning steps to appropriate prompt templates

## Architecture

### Core Components

- **`tool_registry.py`**: Centralized tool registry with metadata lookup
- **`capability_matcher.py`**: Match agent capabilities to tool requirements
- **`schema_validator.py`**: JSON schema validation for tool inputs/outputs
- **`tool_call_orchestrator.py`**: Manage tool calls to K1 Orchestrator with batching
- **`prompt_matcher.py`**: Match planning descriptions to prompt templates

### Tool Registry Structure

```python
@dataclass
class ToolSpec:
    """Complete tool specification with metadata"""
    id: str                             # Unique tool ID (e.g., "query_k0_finance")
    name: str                           # Human-readable name
    description: str                    # Tool description
    schema_in: Dict[str, Any]           # Input schema (JSON Schema)
    schema_out: Dict[str, Any]          # Output schema (JSON Schema)
    latency_hint_ms: int               # Expected latency (P95)
    cost_hint_usd: float               # Expected cost per call
    band_required: str                 # Privacy band (GREEN|AMBER|RED)
    caps_required: Set[str]            # Required capabilities
    category: str                      # Tool category (search, finance, booking)
    version: str                       # Tool version for compatibility
```

## Key ADRs

- **ADR-0007b**: Expand Stage Tool/Prompt Registry Integration - Registry-based planning expansion
- **ADR-0094**: Add query_k0_finance tool to POC Tool Registry - Tool registry extension pattern
- **ADR-0078**: Tool Call Batching Pipeline - Parallel tool execution via orchestrator
- **ADR-0010**: Capability-Based Security - Capability validation for tool access
- **ADR-0034**: MCP Protocol for Tool Integration - Tool execution protocol
- **ADR-0033a**: MCP Sandbox Strategy - Tool execution environment

## Tool Categories

### Finance Tools
- **query_k0_finance**: Retrieve episodic financial transactions
  - Parameters: user_id, query, month (optional)
  - Returns: transaction_count, current_month_total, category_spending[], recent_transactions[], budget_utilization

### Search Tools
- **web_search**: General web search capabilities
- **parse_html**: HTML content parsing and extraction
- **summarize_results**: Result summarization

### Communication Tools
- **send_message**: Send messages through various channels
- **schedule_meeting**: Calendar and meeting coordination
- **contact_lookup**: Contact information retrieval

### Data Tools
- **get_financial_context**: Financial context and budget information
- **user_kg_query**: Knowledge graph queries for user data
- **memory_retrieval**: Episodic and semantic memory access

## Interfaces

### ToolRegistry Interface

```python
class ToolRegistry:
    """Centralized tool registry with O(1) lookup"""

    def get_tool(self, tool_id: str) -> ToolSpec:
        """Get tool specification by ID"""

    def get_tools_by_category(self, category: str) -> List[ToolSpec]:
        """Get all tools in a category"""

    def get_tools_by_capability(self, capability: str) -> List[ToolSpec]:
        """Get tools requiring specific capability"""

    def validate_tool_call(self, tool_id: str, parameters: Dict) -> ValidationResult:
        """Validate tool call parameters against schema"""
```

### CapabilityMatcher Interface

```python
class CapabilityMatcher:
    """Match agent capabilities to tool requirements"""

    def can_agent_use_tool(self, agent_caps: Set[str], tool_spec: ToolSpec) -> bool:
        """Check if agent has required capabilities for tool"""

    def get_available_tools_for_agent(self, agent_caps: Set[str]) -> List[ToolSpec]:
        """Get tools agent can access"""

    def validate_privacy_band(self, agent_band: str, tool_band: str) -> bool:
        """Validate privacy band compatibility"""
```

### ToolCallOrchestrator Interface

```python
class ToolCallOrchestrator:
    """Manage tool calls to K1 Orchestrator"""

    async def call_single_tool(self, tool_call: ToolCall) -> ToolResult:
        """Execute single tool call via orchestrator"""

    async def call_batch_tools(self, tool_calls: List[ToolCall]) -> List[ToolResult]:
        """Execute batch of tool calls with parallelization"""

    async def handle_tool_error(self, error: ToolError, retry_strategy: RetryStrategy) -> ToolResult:
        """Handle tool execution errors with retry logic"""
```

## Performance Characteristics

- **Registry Lookup**: <1ms P95 for tool metadata retrieval
- **Schema Validation**: <5ms P95 for input/output validation
- **Capability Matching**: <2ms P95 for agent-tool compatibility checks
- **Tool Call Latency**: <3000ms P95 (via orchestrator batching)
- **Batch Efficiency**: 2-3x speedup for parallel tool execution

## Security & Privacy

Following ADR-0010 (Capability-Based Security):

- **Capability Validation**: Tools require specific capabilities for access
- **Privacy Band Enforcement**: Tools respect GREEN/AMBER/RED privacy bands
- **Input Sanitization**: All tool parameters validated against schemas
- **Audit Trail**: Tool calls logged with agent context and session ID
- **Access Control**: Registry enforces tool availability based on agent permissions

## Schema Validation

Following ADR-0007b (Registry Integration):

- **Input Schema Validation**: JSON Schema validation for tool parameters
- **Output Schema Validation**: Ensure tool responses match expected format
- **Version Compatibility**: Schema versioning for breaking changes
- **Fallback Handling**: Graceful handling of unknown or invalid schemas

## Tool Call Batching

Following ADR-0078 (Tool Call Batching):

- **Dependency Resolution**: Identify independent vs dependent tool calls
- **Parallel Execution**: Execute independent tools concurrently
- **Result Aggregation**: Combine results from batched executions
- **Error Isolation**: Failures in one tool don't affect others in batch

## Testing

- **Unit Tests**: Isolated registry operations and schema validation
- **Integration Tests**: End-to-end tool call routing through concierge
- **Security Tests**: Capability enforcement and privacy band validation
- **Performance Tests**: Registry lookup latency and batching efficiency
- **Schema Tests**: Tool parameter validation and error handling

## Dependencies

- `k1.orchestrator`: Target for tool call execution
- `k1.bus`: Event publishing for tool call observability
- `k1.telemetry`: Performance monitoring and metrics
- `k1.security`: Capability and privacy band enforcement
- `k1.contracts`: Schema definitions and validation

## Development Notes

- Tool registry is the single source of truth for available tools
- Schema validation prevents malformed tool calls
- Capability matching ensures security boundaries
- Tool call batching improves performance for multi-tool tasks
- Registry updates require schema validation and capability review
- All tool calls go through Orchestrator (not direct execution)
- Privacy bands prevent data leakage across security boundaries
