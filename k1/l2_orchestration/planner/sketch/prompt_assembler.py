"""
Prompt Assembler - Multi-Component Prompt Construction

**ADR Reference:** ADR-0007a (Sketch Stage LLM Prompt Engineering)
**Component:** Sketch Stage → Prompt Assembly

**Purpose:**
Assemble complete LLM prompt from 5 components:
1. System prompt (role definition, constraints)
2. Few-shot examples (5-10 examples, pattern-matched)
3. Output format spec (JSON schema)
4. Available tools (filtered by agent capabilities)
5. Context summary (SessionState compression)

**Token Budget Control:**
- System prompt: 150 tokens (static)
- Few-shot examples: 1,200 tokens (5 examples @ 240 tokens each)
- Output format: 200 tokens (static)
- Available tools: 800 tokens (20 tools @ 40 tokens each, filtered/ranked)
- Context summary: 500 tokens (compressed SessionState)
- Total: 2,850 tokens (fits in 4K context window with 800 token response)

**Design Pattern:**
Builder pattern for prompt assembly with dynamic component selection.
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Set


@dataclass
class PromptComponents:
    """
    Container for all prompt components.

    **ADR Reference:** ADR-0007a (Component 1-5 specifications)
    """

    system_prompt: str
    few_shot_examples: List[Dict[str, Any]]
    output_format_spec: str
    available_tools: List[Dict[str, str]]
    context_summary: str
    user_request: str


class PromptAssembler:
    """
    Assembles multi-component prompts for sketch generation.

    **ADR Reference:** ADR-0007a (Prompt Assembly Algorithm)
    **Related:** ADR-0001b (Model Hub integration for LLM calls)

    **Usage:**
    ```python
    assembler = PromptAssembler(tool_registry, prompt_config)
    components = await assembler.assemble_prompt(
        user_request="Find Italian restaurants",
        session_state=session,
        agent_capabilities={"search_api", "maps_api"}
    )
    prompt_text = assembler.format_for_openai(components)
    ```

    **Performance:** <5ms to assemble prompt (all in-memory operations)
    """

    def __init__(self, tool_registry, prompt_config):
        """
        Initialize prompt assembler.

        Args:
            tool_registry: Tool registry for filtering available tools
            prompt_config: Configuration (max_examples, max_tools, etc.)
        """
        self.tool_registry = tool_registry
        self.config = prompt_config

    async def assemble_prompt(
        self,
        user_request: str,
        session_state,  # SessionState object
        agent_capabilities: Set[str],
    ) -> PromptComponents:
        """
        Assemble all prompt components.

        **ADR Reference:** ADR-0007a (Component 1-5 specifications)

        Args:
            user_request: User's natural language request
            session_state: SessionState with beliefs, history, preferences
            agent_capabilities: Set of tool IDs agent has access to

        Returns:
            PromptComponents with all 5 components assembled

        **Token Budget:**
        - System: 150 tokens
        - Examples: 1,200 tokens (5 examples)
        - Format: 200 tokens
        - Tools: 800 tokens (20 tools)
        - Context: 500 tokens (compressed)
        - Total: 2,850 tokens

        **Performance:** <5ms (in-memory operations)
        """
        # Component 1: System prompt (static, 150 tokens)
        # ADR-0007a Component 1: Role definition and constraints
        system_prompt = self._get_system_prompt()

        # Component 2: Few-shot examples (dynamic, 1,200 tokens)
        # ADR-0007a Component 2: Pattern-matched examples
        few_shot_examples = self._select_few_shot_examples(
            user_request=user_request,
            max_examples=self.config.max_few_shot_examples,  # Default: 5
        )

        # Component 3: Output format spec (static, 200 tokens)
        # ADR-0007a Component 3: JSON schema definition
        output_format_spec = self._get_output_format_spec()

        # Component 4: Available tools (dynamic, 800 tokens)
        # ADR-0007a Component 4: Filtered and ranked tool list
        available_tools = await self._filter_available_tools(
            agent_capabilities=agent_capabilities,
            user_request=user_request,
            max_tools=self.config.max_available_tools,  # Default: 20
        )

        # Component 5: Context summary (dynamic, 500 tokens)
        # ADR-0007a Component 5: Compressed SessionState
        context_summary = self._compress_context_summary(
            session_state=session_state,
            max_tokens=self.config.max_tokens_context,  # Default: 500
        )

        return PromptComponents(
            system_prompt=system_prompt,
            few_shot_examples=few_shot_examples,
            output_format_spec=output_format_spec,
            available_tools=available_tools,
            context_summary=context_summary,
            user_request=user_request,
        )

    def _get_system_prompt(self) -> str:
        """
        Get static system prompt.

        **ADR Reference:** ADR-0007a Component 1 (System Prompt)
        **Token Budget:** 150 tokens

        Returns:
            System prompt with role definition and constraints
        """
        return """You are a task planning assistant for the K1 Intelligence family AI system.

Your role:
- Analyze user requests and generate structured multi-step plans
- Output ONLY valid JSON (no explanations, no markdown code blocks)
- Use ONLY tools from the provided Available Tools list
- Estimate plan complexity (simple, moderate, complex)

Constraints:
- Maximum 10 steps per plan
- Each step must specify: action, tool, parameters, dependencies
- Dependencies use step indices (e.g., step 2 depends on step 0)
- Do NOT invent tools not in the Available Tools list

Output format: JSON object with fields: intent, steps, complexity"""

    def _select_few_shot_examples(
        self, user_request: str, max_examples: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Select relevant few-shot examples via pattern matching.

        **ADR Reference:** ADR-0007a Component 2 (Few-Shot Examples)
        **Token Budget:** 1,200 tokens (5 examples @ 240 tokens each)

        **Selection Strategy:**
        1. Always include 3 core examples (simple, moderate, complex)
        2. Add 2 dynamic examples based on keyword matching

        Args:
            user_request: User's request for pattern matching
            max_examples: Maximum number of examples to include

        Returns:
            List of example dicts (user_request, output)
        """
        # TODO: Implement pattern matching logic
        # For now, return core examples
        return self._get_core_examples()[:max_examples]

    def _get_core_examples(self) -> List[Dict[str, Any]]:
        """
        Get core few-shot examples (simple, moderate, complex).

        **ADR Reference:** ADR-0007a Appendix (Few-Shot Example Library)
        """
        # TODO: Load from example library
        return []

    def _get_output_format_spec(self) -> str:
        """
        Get static output format specification.

        **ADR Reference:** ADR-0007a Component 3 (Output Format Specification)
        **Token Budget:** 200 tokens

        Returns:
            JSON schema specification
        """
        return """Output Format (JSON Schema):
{
  "intent": "INFO_LOOKUP" | "MULTI_STEP_PLANNING" | "TOOL_EXECUTION" | "CLARIFICATION_NEEDED",
  "steps": [
    {
      "step_id": 0,
      "action": "Human-readable step description",
      "tool": "Tool ID from Available Tools list",
      "parameters": { ... },
      "dependencies": [step_id, ...]
    }
  ],
  "complexity": "simple" | "moderate" | "complex"
}"""

    async def _filter_available_tools(
        self, agent_capabilities: Set[str], user_request: str, max_tools: int = 20
    ) -> List[Dict[str, str]]:
        """
        Filter and rank available tools.

        **ADR Reference:** ADR-0007a Component 4 (Available Tools Listing)
        **Token Budget:** 800 tokens (20 tools @ 40 tokens each)

        **Filtering Strategy:**
        1. Filter by agent capabilities (agent has access to tool)
        2. Rank by relevance to user request (keyword matching)
        3. Limit to top-K (max_tools)

        Args:
            agent_capabilities: Set of tool IDs agent can use
            user_request: User request for relevance ranking
            max_tools: Maximum number of tools to include

        Returns:
            List of tool dicts (id, name, description)
        """
        # TODO: Implement tool filtering and ranking
        return []

    def _compress_context_summary(self, session_state, max_tokens: int = 500) -> str:
        """
        Compress SessionState into concise context summary.

        **ADR Reference:** ADR-0007a Component 5 (Context Summary Integration)
        **Token Budget:** 500 tokens (compressed)

        **Priority:**
        1. User preferences (HIGH) - always include
        2. Recent turns (MEDIUM) - last 2-3 turns
        3. Metadata (LOW) - location, etc.

        **Compression:**
        - Extract key preferences from beliefs section
        - Summarize last 2-3 turns from history
        - Truncate to 500 tokens if needed

        Args:
            session_state: SessionState with beliefs, history
            max_tokens: Maximum tokens for context

        Returns:
            Compressed context string
        """
        # TODO: Implement context compression
        return ""

    def format_for_openai(self, components: PromptComponents) -> List[Dict[str, str]]:
        """
        Format components for OpenAI API.

        **ADR Reference:** ADR-0007a (Prompt Formatting for Different LLM APIs)

        Args:
            components: Assembled prompt components

        Returns:
            List of message dicts for OpenAI chat completion
        """
        # TODO: Implement OpenAI message formatting
        return []

    def format_for_gemini(self, components: PromptComponents) -> str:
        """
        Format components for Gemini API.

        **ADR Reference:** ADR-0007a (Prompt Formatting for Different LLM APIs)

        Args:
            components: Assembled prompt components

        Returns:
            Single prompt string for Gemini API
        """
        # TODO: Implement Gemini prompt formatting
        return ""
