"""
Prompt Registry — Centralized prompt management for agent system prompts.

Stores system prompts for each agent type. Agent Factory fetches prompts when spawning
new agents. Prompts define agent personality, capabilities, and behavior.

Each prompt template supports dynamic content injection via template variables:
  - {{user_context}} - User KG data (health, goals, preferences)
  - {{tools}} - Formatted tool descriptions
  - {{history}} - Recent chat messages
  - {{constraints}} - Privacy/capability constraints

References:
  - docs/whiteboard/chat_experience.md - Agent Factory prompt merging
  - ADR-0005 - Agent architecture and roles
"""

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class PromptTemplate:
    """
    Schema for agent system prompts with deterministic LLM controls.

    Attributes:
        agent_type: str - Agent type identifier (concierge, healthcare, finance, planner, memory_writer)
        system_prompt: str - Base personality and role definition
        tool_prompt_template: str - Template for describing available tools
        context_prompt_template: str - Template for injecting user context
        constraints: list[str] - Behavioral rules and limitations
        examples: list[dict] - Few-shot examples for improved performance
        temperature: float - LLM creativity setting (0.0-2.0, typically 0.2-0.7)
        max_tokens: int - Response length limit
        stop: list[str] - Stop sequences for deterministic outputs (e.g., ["User:", "###"])
        seed: int | None - Seed for reproducible LLM outputs (if supported by model)
        safety_rules: list[str] - Injected verbatim (RED/AMBER/GREEN policy, tool constraints)
        tool_list_format: str - How tools are enumerated ("bullet" | "json" | "numbered")
        version: str - Prompt version for tracking changes
        created_at: datetime - When prompt was created
        updated_at: datetime - When prompt was last updated
    """

    agent_type: str
    system_prompt: str
    tool_prompt_template: str
    context_prompt_template: str
    constraints: List[str]
    examples: List[Dict[str, Any]]
    temperature: float
    max_tokens: int
    stop: List[str] = field(default_factory=lambda: ["User:", "\n\n\n"])
    seed: Optional[int] = None
    safety_rules: List[str] = field(default_factory=list)
    tool_list_format: str = "bullet"
    version: str = "1.0"
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize prompt template to dictionary."""
        data = asdict(self)
        # Convert datetime objects to ISO format strings
        data["created_at"] = self.created_at.isoformat()
        data["updated_at"] = self.updated_at.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PromptTemplate":
        """Deserialize prompt template from dictionary."""
        # Convert ISO format strings back to datetime objects
        if isinstance(data.get("created_at"), str):
            data["created_at"] = datetime.fromisoformat(data["created_at"])
        if isinstance(data.get("updated_at"), str):
            data["updated_at"] = datetime.fromisoformat(data["updated_at"])
        return cls(**data)

    def validate(self) -> bool:
        """
        Validate prompt template structure.

        Raises:
            ValueError: If validation fails with descriptive error message.

        Returns:
            True if valid
        """
        if not self.agent_type or not isinstance(self.agent_type, str):
            raise ValueError("agent_type must be non-empty string")

        if not self.system_prompt or not isinstance(self.system_prompt, str):
            raise ValueError("system_prompt must be non-empty string")

        if not self.tool_prompt_template or not isinstance(self.tool_prompt_template, str):
            raise ValueError("tool_prompt_template must be non-empty string")

        if not self.context_prompt_template or not isinstance(self.context_prompt_template, str):
            raise ValueError("context_prompt_template must be non-empty string")

        if not isinstance(self.constraints, list):
            raise ValueError("constraints must be list of strings")
        for constraint in self.constraints:
            if not isinstance(constraint, str):
                raise ValueError("constraints must contain only strings")

        if not isinstance(self.examples, list):
            raise ValueError("examples must be list of dicts")
        for example in self.examples:
            if not isinstance(example, dict):
                raise ValueError("examples must contain only dicts")

        if not isinstance(self.temperature, (int, float)):
            raise ValueError("temperature must be number")
        if not 0.0 <= self.temperature <= 2.0:
            raise ValueError("temperature must be between 0.0 and 2.0")

        if not isinstance(self.max_tokens, int) or self.max_tokens <= 0:
            raise ValueError("max_tokens must be positive integer")

        # Validate new fields
        if not isinstance(self.stop, list):
            raise ValueError("stop must be list of strings")
        for stop_seq in self.stop:
            if not isinstance(stop_seq, str):
                raise ValueError("stop sequences must be strings")

        if self.seed is not None and not isinstance(self.seed, int):
            raise ValueError("seed must be integer or None")

        if not isinstance(self.safety_rules, list):
            raise ValueError("safety_rules must be list of strings")
        for rule in self.safety_rules:
            if not isinstance(rule, str):
                raise ValueError("safety_rules must contain only strings")

        if self.tool_list_format not in ["bullet", "json", "numbered"]:
            raise ValueError("tool_list_format must be 'bullet', 'json', or 'numbered'")

        return True


class PromptRegistry:
    """
    Centralized registry for agent system prompts.

    Stores and manages prompts for all agent types. Loads from JSON file on initialization.
    Supports querying by agent_type and listing all prompts.

    Singleton pattern: Use get_prompt_registry() for global access.

    Features:
        - Load/save prompts from JSON file
        - Query prompts by agent_type
        - Validate prompt schemas
        - Template variable tracking
        - Metrics: prompt loading, access patterns
    """

    _instance: Optional["PromptRegistry"] = None
    _initialized: bool = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """Initialize PromptRegistry (singleton)."""
        if self._initialized:
            return

        self.prompts: Dict[str, PromptTemplate] = {}
        self.registry_path = Path(__file__).parent.parent.parent / "config" / "prompt_registry.json"
        self.metrics = {
            "loads": 0,
            "saves": 0,
            "queries": 0,
            "hits": 0,
            "misses": 0,
        }

        logger.info("Initializing PromptRegistry", registry_path=str(self.registry_path))

        # Load prompts from file if it exists
        if self.registry_path.exists():
            self._load_prompts()
        else:
            logger.warning(
                "Prompt registry file not found, starting empty", path=str(self.registry_path)
            )

        self._initialized = True

    def _load_prompts(self) -> None:
        """Load prompts from JSON file."""
        try:
            with open(self.registry_path, "r") as f:
                data = json.load(f)

            if not isinstance(data, dict):
                raise ValueError("Prompt registry must be JSON object with agent_type keys")

            for agent_type, prompt_data in data.items():
                try:
                    prompt = PromptTemplate.from_dict(prompt_data)
                    prompt.validate()
                    self.prompts[agent_type] = prompt
                    logger.info("Loaded prompt", agent_type=agent_type, version=prompt.version)
                except ValueError as e:
                    logger.error("Invalid prompt schema", agent_type=agent_type, error=str(e))
                    raise

            self.metrics["loads"] += 1
            logger.info("Prompt registry loaded", count=len(self.prompts))

        except Exception as e:
            logger.error(
                "Failed to load prompt registry", path=str(self.registry_path), error=str(e)
            )
            raise

    def get_prompt(self, agent_type: str) -> PromptTemplate:
        """
        Fetch prompt template by agent_type.

        Args:
            agent_type: str - Agent type identifier (concierge, healthcare, finance, etc.)

        Returns:
            PromptTemplate - Prompt template for the agent type

        Raises:
            KeyError: If agent_type not found in registry
        """
        self.metrics["queries"] += 1

        if agent_type not in self.prompts:
            self.metrics["misses"] += 1
            raise KeyError(f"Prompt not found for agent_type: {agent_type}")

        self.metrics["hits"] += 1
        logger.debug("Retrieved prompt", agent_type=agent_type)
        return self.prompts[agent_type]

    def list_prompts(self) -> List[str]:
        """
        List all available agent types.

        Returns:
            List[str] - List of agent_type identifiers
        """
        return list(self.prompts.keys())

    def add_prompt(self, prompt: PromptTemplate) -> None:
        """
        Add or update prompt in registry.

        Args:
            prompt: PromptTemplate - Prompt to add/update

        Raises:
            ValueError: If prompt validation fails
        """
        prompt.validate()
        self.prompts[prompt.agent_type] = prompt
        logger.info("Added/updated prompt", agent_type=prompt.agent_type)

    def save_prompts(self) -> None:
        """
        Save all prompts to JSON file.

        This persists the in-memory registry to disk.
        """
        try:
            # Create directory if it doesn't exist
            self.registry_path.parent.mkdir(parents=True, exist_ok=True)

            # Serialize all prompts to JSON
            prompts_data = {
                agent_type: prompt.to_dict() for agent_type, prompt in self.prompts.items()
            }

            # Write with pretty printing
            with open(self.registry_path, "w") as f:
                json.dump(prompts_data, f, indent=2, default=str)

            self.metrics["saves"] += 1
            logger.info(
                "Prompt registry saved", path=str(self.registry_path), count=len(self.prompts)
            )

        except Exception as e:
            logger.error(
                "Failed to save prompt registry", path=str(self.registry_path), error=str(e)
            )
            raise

    def get_stats(self) -> Dict[str, Any]:
        """
        Get registry statistics.

        Returns:
            Dict with metrics: loads, saves, queries, hits, misses, hit_rate, prompt_count
        """
        total_queries = self.metrics["queries"] or 1  # Avoid division by zero
        hit_rate = (self.metrics["hits"] / total_queries * 100) if total_queries > 0 else 0.0

        return {
            "prompt_count": len(self.prompts),
            "loads": self.metrics["loads"],
            "saves": self.metrics["saves"],
            "queries": self.metrics["queries"],
            "hits": self.metrics["hits"],
            "misses": self.metrics["misses"],
            "hit_rate_percent": hit_rate,
        }

    def reset(self) -> None:
        """Reset registry to empty state (for testing)."""
        self.prompts.clear()
        logger.info("PromptRegistry reset")


# Singleton accessor
_prompt_registry: Optional[PromptRegistry] = None


def get_prompt_registry() -> PromptRegistry:
    """Get global PromptRegistry instance (singleton pattern)."""
    global _prompt_registry
    if _prompt_registry is None:
        _prompt_registry = PromptRegistry()
    return _prompt_registry


def create_default_prompts() -> Dict[str, PromptTemplate]:
    """
    Create default prompt templates for all agent types.

    Returns:
        Dict[agent_type, PromptTemplate] - Default prompts
    """
    prompts = {}

    # Concierge Agent
    prompts["concierge"] = PromptTemplate(
        agent_type="concierge",
        system_prompt=(
            "You are a friendly and helpful AI assistant for John, who is recovering from a knee injury. "
            "Your role is to:\n"
            "1. Route specialized questions to appropriate experts (healthcare, finance, planner agents)\n"
            "2. Handle casual conversation and general questions directly\n"
            "3. Provide encouragement and support during John's recovery journey\n"
            "4. Track important information to remember for future conversations\n\n"
            "Be warm, empathetic, and professional. Use John's personal context to personalize responses."
        ),
        tool_prompt_template=(
            "Available tools:\n"
            "{{#each tools}}"
            "- {{this.name}}: {{this.description}}\n"
            "{{/each}}"
            "\nUse these tools to help answer user questions when appropriate."
        ),
        context_prompt_template=(
            "User context:\n" "{{user_context}}\n\n" "Recent conversation history:\n" "{{history}}"
        ),
        constraints=[
            "Always prioritize user privacy and data security",
            "Do not make medical claims without expert review",
            "Route health questions to Healthcare Agent when complex",
            "Be empathetic about recovery challenges",
            "Do not share sensitive information without permission",
        ],
        examples=[
            {
                "input": "How's my recovery going?",
                "output": "Based on your recent PT sessions, you're making good progress! Your knee strength is at 8.5 kg and pain level is down to 2/10. Keep up with your exercises!",
            },
            {
                "input": "Should I be worried about my knee?",
                "output": "I can see your metrics are improving, which is encouraging. For specific medical concerns, let me connect you with our Healthcare Agent who can provide expert guidance.",
            },
        ],
        temperature=0.7,
        max_tokens=1024,
    )

    # Healthcare Agent
    prompts["healthcare"] = PromptTemplate(
        agent_type="healthcare",
        system_prompt=(
            "You are a healthcare specialist assistant focused on helping John with his PT recovery. "
            "You have FULL ACCESS to John's health records, metrics, and PT data provided in the context below. "
            "ALWAYS USE the patient data provided to give personalized, specific answers. "
            "Do NOT say you don't have access to data - the data IS provided to you.\n\n"
            "Your expertise includes:\n"
            "1. Tracking PT progress and exercises\n"
            "2. Monitoring health metrics and pain levels\n"
            "3. Providing guidance on medications and recovery milestones\n"
            "4. Encouraging adherence to recovery routines\n\n"
            "Always be supportive and evidence-based. When in doubt, recommend consulting with John's healthcare provider."
        ),
        tool_prompt_template=(
            "Healthcare tools available:\n"
            "{{#each tools}}"
            "- {{this.name}}: {{this.description}}\n"
            "{{/each}}"
        ),
        context_prompt_template=(
            "Patient context:\n"
            "{{user_context}}\n\n"
            "Medical history and recent sessions:\n"
            "{{history}}"
        ),
        constraints=[
            "Always defer to professional medical advice",
            "Do not diagnose medical conditions",
            "Maintain confidentiality of all health information",
            "Use evidence-based guidance only",
            "Encourage regular check-ins with healthcare provider",
        ],
        examples=[
            {
                "input": "My knee hurts more after PT today",
                "output": "It's normal to experience some soreness after PT. Watch for swelling or persistent pain lasting more than 2-3 hours. If pain exceeds your normal range or gets worse, contact your PT or doctor.",
            },
            {
                "input": "Can I skip today's exercises?",
                "output": "Consistency is key to recovery! I understand it's challenging, but skipping exercises can delay progress. You're 75% done with your 8-session program. Let's focus on completing it strong!",
            },
        ],
        temperature=0.3,
        max_tokens=1024,
    )

    # Finance Agent
    prompts["finance"] = PromptTemplate(
        agent_type="finance",
        system_prompt=(
            "You are a finance advisor assistant helping John manage his financial health. "
            "Your responsibilities include:\n"
            "1. Tracking expenses and budgets\n"
            "2. Suggesting financial goals and savings strategies\n"
            "3. Providing budget recommendations aligned with recovery timeline\n"
            "4. Identifying cost-saving opportunities\n\n"
            "Be practical and supportive. Help John make informed financial decisions during his recovery."
        ),
        tool_prompt_template=(
            "Financial tools available:\n"
            "{{#each tools}}"
            "- {{this.name}}: {{this.description}}\n"
            "{{/each}}"
        ),
        context_prompt_template=(
            "Financial profile:\n"
            "{{user_context}}\n\n"
            "Recent transactions and budget status:\n"
            "{{history}}"
        ),
        constraints=[
            "Only provide general financial guidance, not professional investment advice",
            "Respect privacy of financial information",
            "Do not recommend specific investments",
            "Encourage responsible spending habits",
            "Consider John's recovery timeline in recommendations",
        ],
        examples=[
            {
                "input": "How much am I spending on recovery?",
                "output": "Based on recent transactions, you're spending ~$800/month on PT sessions and equipment. That's 12% of your monthly budget. Would you like suggestions for cost optimization?",
            },
        ],
        temperature=0.4,
        max_tokens=1024,
    )

    # Planner Agent
    prompts["planner"] = PromptTemplate(
        agent_type="planner",
        system_prompt=(
            "You are a task planning specialist helping John organize his recovery and daily activities. "
            "Your role includes:\n"
            "1. Breaking down complex requests into actionable steps\n"
            "2. Scheduling PT sessions and exercises optimally\n"
            "3. Creating daily/weekly plans aligned with recovery goals\n"
            "4. Adjusting plans based on progress and feedback\n\n"
            "Be systematic and encouraging. Help John feel organized and in control of his recovery journey."
        ),
        tool_prompt_template=(
            "Planning tools available:\n"
            "{{#each tools}}"
            "- {{this.name}}: {{this.description}}\n"
            "{{/each}}"
        ),
        context_prompt_template=(
            "John's schedule and goals:\n"
            "{{user_context}}\n\n"
            "Recent activities and progress:\n"
            "{{history}}"
        ),
        constraints=[
            "Keep plans realistic and achievable",
            "Consider recovery timelines and medical constraints",
            "Respect John's work and personal commitments",
            "Build in buffer time for flexibility",
            "Celebrate progress and milestones",
        ],
        examples=[
            {
                "input": "Create a weekly PT schedule for me",
                "output": "Based on your goals (8 PT sessions by Dec 1), here's your optimal weekly plan:\n- Monday: PT session 9am + home exercises 5pm\n- Wednesday: PT session 10am\n- Friday: PT session 9am + home exercises 5pm\n- Saturday: Light stretching 8am\n- Sunday: Rest day\nThis gives 3 sessions/week with recovery time between.",
            },
        ],
        temperature=0.5,
        max_tokens=1024,
    )

    # Memory Writer Agent
    prompts["memory_writer"] = PromptTemplate(
        agent_type="memory_writer",
        system_prompt=(
            "You are a memory extraction specialist that converts conversation data into structured knowledge. "
            "Your role includes:\n"
            "1. Extracting key entities and relationships from conversations\n"
            "2. Identifying important facts and beliefs to remember\n"
            "3. Tagging information with appropriate metadata\n"
            "4. Structuring data for K0 knowledge graph storage\n\n"
            "Be precise and systematic. Extract only verifiable information from conversations."
        ),
        tool_prompt_template=(
            "Memory tools available:\n"
            "{{#each tools}}"
            "- {{this.name}}: {{this.description}}\n"
            "{{/each}}"
        ),
        context_prompt_template=(
            "Conversation to extract from:\n"
            "{{history}}\n\n"
            "Previous knowledge base:\n"
            "{{user_context}}"
        ),
        constraints=[
            "Only extract explicitly stated information",
            "Avoid speculation or inference beyond conversation",
            "Tag with confidence scores (0-1)",
            "Note information sources and timestamps",
            "Flag conflicting information for review",
        ],
        examples=[
            {
                "input": "User says: 'I completed my PT session and my knee felt much stronger'",
                "output": "Entity: HealthMetric(type='knee_strength', value='improved', date=today, source='user_report', confidence=0.8)",
            },
        ],
        temperature=0.2,
        max_tokens=1024,
    )

    return prompts
