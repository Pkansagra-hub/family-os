"""
Specialist Agents - Tier 2 On-Demand Dynamic Creation.

Specialist agents handle domain-specific queries with deep knowledge:
  - HealthcareAgent: PT schedules, medications, recovery tracking
  - FinanceAgent: Budgets, expenses, savings goals
  - ResearcherAgent: Information lookup, factual questions

All specialists:
  - Inherit from AgentBase
  - Use Prompt Registry for system prompts
  - Query User KG for personalization
  - Call MCP tools for data (mock for POC)
  - Synthesize responses using Groq LLM
  - Return to Concierge for user delivery

References:
  - docs/whiteboard/chat_experience.md - Specialist agent patterns
  - Epic 4.3 - Specialist agent implementation
"""

from l3_execution.agents.specialists.finance_agent import FinanceAgent
from l3_execution.agents.specialists.healthcare_agent import HealthcareAgent
from l3_execution.agents.specialists.researcher_agent import ResearcherAgent

__all__ = ["HealthcareAgent", "FinanceAgent", "ResearcherAgent"]
