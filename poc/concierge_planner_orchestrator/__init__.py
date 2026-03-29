"""
Concierge -> Planner -> Orchestrator POC
=========================================

Proof of concept demonstrating the 3-tier execution philosophy:
  1. Concierge (LLM): Receives user request, classifies complexity, routes
  2. Planner (LLM): Discovers capabilities, builds CommittedPlan (DAG)
  3. Orchestrator (NO LLM): Blind DAG executor via Fabric

Uses real Google Gemini LLM via SimpleLLMClient.
Uses real Fabric with registered tool contracts.
"""
