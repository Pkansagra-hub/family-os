"""
Agent Composition Pattern (ADR-0086d)

Purpose:
    Compose dynamic agents from three components: Prompt (Jinja2 template) +
    Tools (capability-filtered) + Persona (personality traits). Provides secure
    composition with prompt injection protection and token validation.

Architecture:
    - CompositionEngine class (~400 lines implementation)
    - Composition: Prompt + Tools + Persona
    - Capability-based tool filtering (758 tools available)
    - Security: 10+ prompt injection patterns, token validation

Performance Targets:
    - Composition (cached): <5ms P95
    - Composition (uncached): <30ms P95
    - Tool filtering: <10ms

Key Components:
    1. CompositionEngine (orchestrator)
    2. PromptResolver (fetch from prompt library)
    3. ToolFilter (capability-based selection)
    4. PersonaInjector (trait formatting)
    5. SecurityValidator (injection detection)

Related ADRs:
    - ADR-0086: Dynamic Agent Creation Subsystem (parent)
    - ADR-0086a: Agent Factory (composition consumer)
    - ADR-0086e: Prompt Directory (prompt source)
    - ADR-0010: Capability Security (tool filtering)

Research Foundation:
    - Prompt Engineering (OpenAI 2023)
    - Capability-Based Security (Dennis & Van Horn 1966)

Implementation Status: STUB (M1 - 3 days planned)
"""

from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from enum import Enum


class Capability(Enum):
    """Agent capability types."""
    TOOL_CALL = "TOOL_CALL"
    MEMORY_READ = "MEMORY_READ"
    MEMORY_WRITE = "MEMORY_WRITE"
    MODEL_CALL = "MODEL_CALL"
    NETWORK_ACCESS = "NETWORK_ACCESS"


@dataclass
class PromptComponent:
    """Prompt template component.
    
    Attributes:
        template_id: Prompt template identifier
        template_content: Jinja2 template content
        version: Template version (semantic versioning)
        max_tokens: Maximum token count for prompt
    """
    template_id: str
    template_content: str
    version: str
    max_tokens: int


@dataclass
class ToolComponent:
    """Tool component with capability filter.
    
    Attributes:
        tool_ids: List of allowed tool IDs
        capabilities: Required capabilities for tools
        total_tools: Total number of tools (758 available)
        filtered_count: Number of tools after filtering
    """
    tool_ids: List[str]
    capabilities: List[Capability]
    total_tools: int = 758
    filtered_count: int = 0


@dataclass
class PersonaComponent:
    """Persona/personality traits component.
    
    Attributes:
        traits: Dictionary of personality traits
        response_style: Response style (concise/detailed/empathetic)
        domain_expertise: Domain knowledge areas
    """
    traits: Dict[str, Any]
    response_style: str
    domain_expertise: List[str]


@dataclass
class ComposedAgent:
    """Fully composed agent ready for spawning.
    
    Attributes:
        agent_type: Type of agent
        prompt: Resolved prompt component
        tools: Filtered tool component
        persona: Persona component
        composition_hash: SHA-256 hash of composition
        token_count: Total token count (prompt + persona)
        security_validated: Whether injection patterns checked
    """
    agent_type: str
    prompt: PromptComponent
    tools: ToolComponent
    persona: PersonaComponent
    composition_hash: str
    token_count: int
    security_validated: bool


class CompositionEngine:
    """Agent composition engine.
    
    Responsibilities:
        - Fetch prompt from prompt library (Jinja2 templates)
        - Filter tools based on capabilities (758 tools → allowed subset)
        - Inject persona traits into prompt
        - Validate security (prompt injection detection)
        - Calculate token counts
        - Cache compositions for reuse
    
    Thread Safety: Thread-safe with caching
    Performance: <5ms cached, <30ms uncached
    
    Example:
        engine = CompositionEngine()
        composed = await engine.compose(
            agent_type="health_specialist",
            capabilities=[Capability.TOOL_CALL, Capability.MEMORY_READ],
            persona_traits={"response_style": "empathetic"}
        )
        print(f"Token count: {composed.token_count}")
    """
    
    # Security patterns for prompt injection detection
    INJECTION_PATTERNS = [
        r"ignore previous instructions",
        r"disregard all above",
        r"reveal your prompt",
        r"show system prompt",
        r"bypass safety",
        r"override restrictions",
        r"act as if you are",
        r"pretend to be",
        r"jailbreak",
        r"developer mode",
    ]
    
    def __init__(self):
        """Initialize CompositionEngine with caching."""
        # Composition cache (agent_type -> ComposedAgent)
        self._composition_cache: Dict[str, ComposedAgent] = {}
        
        # Tool registry (tool_id -> tool metadata)
        self._tool_registry: Dict[str, Any] = {}
        
        # Prompt library client
        self._prompt_library: Optional[Any] = None
    
    async def compose(
        self,
        agent_type: str,
        capabilities: List[Capability],
        persona_traits: Optional[Dict[str, Any]] = None
    ) -> ComposedAgent:
        """Compose agent from prompt + tools + persona.
        
        Process:
            1. Check composition cache (keyed by agent_type + capabilities)
            2. Fetch prompt template from prompt library
            3. Filter tools by capabilities (758 → allowed subset)
            4. Inject persona traits into prompt
            5. Validate security (prompt injection patterns)
            6. Calculate token count (1 token ≈ 4 chars)
            7. Create composition hash (SHA-256)
            8. Cache composition
        
        Args:
            agent_type: Type of agent to compose (e.g., "health_specialist")
            capabilities: List of required capabilities
            persona_traits: Optional personality traits
        
        Returns:
            ComposedAgent ready for spawning
        
        Raises:
            PromptNotFoundError: Prompt template not found
            SecurityValidationError: Prompt injection detected
            TokenLimitExceededError: Token count exceeds limit
        
        Performance: <5ms cached, <30ms uncached
        """
        # TODO: Implement composition logic
        # 1. Check cache
        # 2. Fetch prompt (call PromptLibrary)
        # 3. Filter tools (capability-based)
        # 4. Inject persona
        # 5. Validate security
        # 6. Calculate tokens
        # 7. Hash composition
        # 8. Cache result
        raise NotImplementedError("Agent composition not yet implemented (M1)")
    
    def _filter_tools_by_capabilities(
        self,
        capabilities: List[Capability]
    ) -> List[str]:
        """Filter tools based on agent capabilities.
        
        Args:
            capabilities: List of agent capabilities
        
        Returns:
            List of allowed tool IDs
        
        Example:
            Input: [Capability.TOOL_CALL, Capability.MEMORY_READ]
            Output: ["get_health_metrics", "search_memory", "recall_fact"]
            (subset of 758 total tools)
        
        Performance: <10ms
        """
        # TODO: Implement capability-based filtering
        # 1. Load tool registry
        # 2. Filter by capabilities
        # 3. Return allowed tool IDs
        raise NotImplementedError("Tool filtering not yet implemented (M1)")
    
    def _detect_prompt_injection(self, prompt: str) -> bool:
        """Detect prompt injection attempts.
        
        Args:
            prompt: Prompt content to validate
        
        Returns:
            True if injection detected, False otherwise
        
        Patterns: 10+ injection patterns (INJECTION_PATTERNS)
        """
        # TODO: Implement injection detection
        # 1. Check each pattern
        # 2. Return True if any match
        raise NotImplementedError("Injection detection not yet implemented (M1)")
    
    def _calculate_token_count(self, text: str) -> int:
        """Calculate token count for text.
        
        Args:
            text: Text to tokenize
        
        Returns:
            Estimated token count (1 token ≈ 4 chars)
        
        Note: Uses simple heuristic. Actual tokenization depends on model.
        """
        return len(text) // 4


# TODO: Implement supporting classes and functions
# - PromptNotFoundError, SecurityValidationError, TokenLimitExceededError
# - Integration with PromptLibrary (ADR-0086e)
# - Integration with ToolRegistry (ADR-0033)
# - Composition caching with LRU eviction
# - SHA-256 hashing for composition fingerprinting
# - Metrics emission (composition_latency_ms, tool_filter_latency_ms)
# - WARD test cases (5 test cases planned)
