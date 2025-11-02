"""
Agent Spawn Wrapper - Dynamic agent factory for circular hub-and-spoke model

Creates agents on-demand:
1. Check if prompt template exists
2. If not, generate with LLM
3. Spawn agent with assigned tools
4. Return to circular orchestrator
"""

import asyncio
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from agent_base import Agent, AgentContext, AgentResponse

logger = logging.getLogger(__name__)


class AgentSpawnWrapper:
    """
    Factory for spawning domain-specific agents.

    Responsibilities:
    1. Manage prompt templates (agents/templates/)
    2. Generate prompts dynamically if not found
    3. Instantiate agents with tools
    4. Cache generated prompts
    """

    def __init__(
        self, llm_provider, templates_dir: str = "agents/templates", cache_dir: str = "agents/cache"
    ):
        """
        Initialize agent spawn wrapper.

        Args:
            llm_provider: LLM provider for generating prompts
            templates_dir: Directory for prompt templates
            cache_dir: Directory for caching generated prompts
        """
        self.llm_provider = llm_provider
        self.templates_dir = Path(templates_dir)
        self.cache_dir = Path(cache_dir)
        self.agent_registry: Dict[str, type] = {}
        self.loaded_templates: Dict[str, str] = {}
        self.generated_prompts_cache: Dict[str, str] = {}

        # Create directories if they don't exist
        self.templates_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"AgentSpawnWrapper initialized: templates={templates_dir}, cache={cache_dir}")

    def register_agent_class(self, agent_type: str, agent_class: type):
        """
        Register a custom agent class for a specific type.

        Args:
            agent_type: Type identifier (e.g., "travel_agent")
            agent_class: Python class for this agent type
        """
        self.agent_registry[agent_type] = agent_class
        logger.info(f"Registered agent class: {agent_type} → {agent_class.__name__}")

    def load_template(self, agent_type: str) -> Optional[str]:
        """
        Load prompt template for agent type.

        Priority:
        1. Check loaded cache
        2. Check file system (agents/templates/{agent_type}.prompt)
        3. Check cache directory (agents/cache/{agent_type}.prompt)
        4. Return None (will be generated)

        Args:
            agent_type: Type of agent (e.g., "travel_agent")

        Returns:
            Prompt template string or None
        """
        # Check in-memory cache
        if agent_type in self.loaded_templates:
            logger.debug(f"Template loaded from cache: {agent_type}")
            return self.loaded_templates[agent_type]

        # Check file system
        template_file = self.templates_dir / f"{agent_type}.prompt"
        if template_file.exists():
            prompt = template_file.read_text()
            self.loaded_templates[agent_type] = prompt
            logger.info(f"Loaded template from file: {agent_type}")
            return prompt

        # Check generated cache
        cache_file = self.cache_dir / f"{agent_type}.prompt"
        if cache_file.exists():
            prompt = cache_file.read_text()
            self.loaded_templates[agent_type] = prompt
            logger.info(f"Loaded template from cache: {agent_type}")
            return prompt

        logger.warning(f"Template not found for {agent_type} - will generate with LLM")
        return None

    async def generate_prompt(self, agent_type: str, context: Dict[str, Any]) -> str:
        """
        Generate prompt dynamically using LLM.

        Args:
            agent_type: Type of agent to generate prompt for
            context: Context about what the agent needs to do

        Returns:
            Generated prompt template
        """
        # Check if already generated and cached
        if agent_type in self.generated_prompts_cache:
            logger.debug(f"Using cached generated prompt: {agent_type}")
            return self.generated_prompts_cache[agent_type]

        logger.info(f"Generating prompt with LLM for {agent_type}")

        generation_prompt = f"""Generate a specialized agent prompt for a {agent_type}.

Context:
- Agent Type: {agent_type}
- Required Tools: {context.get('required_tools', [])}
- Required Data: {context.get('required_data', [])}
- Domain: {context.get('domain', 'general')}

The prompt should:
1. Define the agent's role and responsibilities
2. Explain what data it needs to collect
3. Show how to ask for clarification when needed
4. Include examples of good agent behavior
5. Specify what tools the agent can use
6. Show how to structure the final response

Generate a detailed prompt template that other specialized agents can follow:"""

        try:
            generated = await asyncio.to_thread(
                self.llm_provider.call_llm,
                prompt=generation_prompt,
                max_tokens=500,
                system_message="You are an expert prompt engineer. Generate high-quality agent prompts.",
            )

            # Cache the generated prompt
            self.generated_prompts_cache[agent_type] = generated

            # Save to file for future use
            cache_file = self.cache_dir / f"{agent_type}.prompt"
            cache_file.write_text(generated)
            logger.info(f"Generated and cached prompt for {agent_type}")

            return generated

        except Exception as e:
            logger.error(f"Failed to generate prompt for {agent_type}: {e}")
            raise

    async def spawn_agent(
        self,
        agent_type: str,
        user_input: str,
        tools: Dict[str, Any],
        user_id: str = "user",
        user_profile: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> Agent:
        """
        Spawn an agent instance.

        Flow:
        1. Look for existing agent class in registry
        2. Load prompt template (or generate if not found)
        3. Create agent instance
        4. Bind tools
        5. Return ready-to-execute agent

        Args:
            agent_type: Type of agent (e.g., "travel_agent")
            user_input: User's original input
            tools: Dict of tools available to agent
            user_id: User ID
            user_profile: User preferences/history
            **kwargs: Additional context

        Returns:
            Instantiated Agent ready to execute
        """
        logger.info(f"Spawning agent: {agent_type}")

        # Generate unique agent ID
        agent_id = f"{agent_type}_{len(kwargs.get('agent_instances', []))}_{int(__import__('time').time() * 1000)}"

        # Load or generate prompt
        prompt = self.load_template(agent_type)
        if not prompt:
            logger.info(f"Generating prompt for {agent_type}")
            context = {
                "required_tools": list(tools.keys()),
                "required_data": kwargs.get("required_data", []),
                "domain": agent_type.split("_")[0],  # e.g., "travel" from "travel_agent"
            }
            prompt = await self.generate_prompt(agent_type, context)

        # Get agent class from registry or use generic
        agent_class = self.agent_registry.get(agent_type, GenericAgent)

        # Create agent instance
        agent = agent_class(agent_id, agent_type, self.llm_provider)
        agent.set_prompt_template(prompt)

        # Create execution context
        agent.context = AgentContext(
            agent_id=agent_id,
            agent_type=agent_type,
            user_input=user_input,
            user_id=user_id,
            tools=tools,
            user_profile=user_profile or {},
            conversation_history=kwargs.get("conversation_history", []),
            clarification_history=kwargs.get("clarification_history", []),
            metadata=kwargs,
        )

        logger.info(f"Agent spawned: {agent_id} (type={agent_type})")
        return agent


class GenericAgent(Agent):
    """
    Generic agent that works with any prompt template.
    Used as fallback when specialized agent class not registered.
    """

    async def execute(self, context: AgentContext) -> AgentResponse:
        """Execute using LLM and prompt template."""
        import time

        start = time.perf_counter()

        self.context = context

        # Build execution prompt
        exec_prompt = f"""{self.prompt_template}

Current Time: {self.get_time_context()}
User Input: {context.user_input}

Conversation History:
{self.get_conversation_context()}

Available Tools: {list(context.tools.keys())}

Execute the task and respond with:
1. What you understand about the request
2. What data you have
3. What data you need from the user (if any)
4. Your response

Format as JSON:
{{
  "understanding": "...",
  "have_data": [...],
  "need_data": [...],
  "clarification_question": "..." or null,
  "response": "...",
  "tools_used": [...]
}}
"""

        try:
            result = await asyncio.to_thread(
                self.llm_provider.call_llm,
                prompt=exec_prompt,
                max_tokens=300,
                system_message=f"You are a {self.agent_type}. Be thorough and ask for missing information.",
            )

            # Parse result
            import json

            try:
                parsed = json.loads(result)
            except Exception:
                parsed = {
                    "understanding": result,
                    "have_data": [],
                    "need_data": [],
                    "clarification_question": None,
                    "response": result,
                    "tools_used": [],
                }

            latency_ms = (time.perf_counter() - start) * 1000

            # Determine status
            status = "needs_clarification" if parsed.get("clarification_question") else "completed"

            return AgentResponse(
                agent_id=self.agent_id,
                agent_type=self.agent_type,
                status=status,
                result=parsed,
                clarification_question=parsed.get("clarification_question"),
                required_data=parsed.get("need_data", []),
                tools_used=parsed.get("tools_used", []),
                latency_ms=latency_ms,
            )

        except Exception as e:
            logger.error(f"Agent execution failed: {e}")
            return AgentResponse(
                agent_id=self.agent_id,
                agent_type=self.agent_type,
                status="error",
                error=str(e),
                latency_ms=(time.perf_counter() - start) * 1000,
            )

    def get_required_tools(self) -> List[str]:
        """Generic agent can use any tools."""
        return ["*"]
