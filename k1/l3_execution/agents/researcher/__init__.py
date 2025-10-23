"""
K1 Layer 3 Execution — agents/researcher/ (🤖 AI Agent)

PURPOSE:
========
AI Agent for knowledge synthesis & retrieval (<3000ms P95).
Uses LLM for multi-store RAG (Retrieval-Augmented Generation) with fact-checking.

RESPONSIBILITIES:
=================
1. Knowledge Retrieval: Multi-store query (episodic, semantic, procedural, KG)
2. Synthesis: Fuse results from multiple sources, generate coherent response
3. Fact-Checking: Validate retrieved information, confidence scoring

PRIMARY ADRs:
=============
- ADR-0005e: Agent Personalities (Researcher: 3000ms budget)
  * Researcher is AI agent with 3000ms response time budget
  * Knowledge synthesis with multi-store RAG
  * Model: GPT-4o-mini or Claude-3-Haiku (local/remote)
  * Capabilities: TOOL_CALL, MEMORY_READ, MODEL_CALL, NETWORK_ACCESS

- ADR-0001b: Model Hub Integration (Researcher uses Model Hub)
  * Researcher calls Model Hub for LLM inference
  * Placement preference: GPU → Remote (quality over latency)
  * Fallback cascade: gemma-2-9b (local GPU) → claude-3-haiku (remote)

- ADR-0001: K0 Integration (multi-store retrieval)
  * Researcher queries K0 memory stores: episodic, semantic, procedural, KG
  * RAG pipeline: retrieve → rerank → synthesize
  * Fact-checking via source attribution

RELATED ADRs:
=============
- ADR-0024: Performance Budgets (Researcher <3000ms)
- ADR-0027: Model Placement (local-first, fallback remote)
- ADR-0031: Cost Tracking (Researcher token usage)

RESEARCHER RESPONSIBILITIES:
=============================
**1. Multi-Store Knowledge Retrieval:**
- **Episodic Memory:** User conversation history, SessionState turns
- **Semantic Memory:** Long-term facts, user preferences, domain knowledge
- **Procedural Memory:** How-to knowledge, workflows, recipes
- **Knowledge Graph:** Entity relationships, linked data

**Example Multi-Store Query:**
```
User: "What did I say about my favorite restaurants last week?"
Researcher:
  1. Query episodic memory: Last 7 days, keyword="restaurant"
  2. Query KG: User → has_preference → Restaurant entities
  3. Query semantic: User preferences for cuisine types
  4. Synthesize: "Last Tuesday you mentioned loving the Italian place downtown..."
```

**2. Knowledge Synthesis (RAG Pipeline):**
```python
async def synthesize_knowledge(self, query: str) -> SynthesisResult:
    \"\"\"Retrieve + synthesize knowledge (<3000ms).\"\"\"
    # 1. Multi-store retrieval
    episodic_results = await self.k0_client.query_episodic(query)
    semantic_results = await self.k0_client.query_semantic(query)
    procedural_results = await self.k0_client.query_procedural(query)
    kg_results = await self.k0_client.query_kg(query)

    # 2. Rerank by relevance
    all_results = episodic_results + semantic_results + procedural_results + kg_results
    ranked_results = await self.rerank(query, all_results)
    top_k = ranked_results[:5]  # Top 5 results

    # 3. Build synthesis prompt
    context = "\\n\\n".join([f"Source {i+1}: {r.content}" for i, r in enumerate(top_k)])

    system_prompt = self.personality.format_personality_prompt()
    user_prompt = f\"\"\"Synthesize a coherent answer from these sources:

Query: {query}

Context:
{context}

Requirements:
- Fuse information from multiple sources
- Cite sources with [Source N] attribution
- Provide confidence scores
- Flag contradictions or uncertainties
\"\"\"

    # 4. Call Model Hub for synthesis
    model_request = ModelRequest(
        model="gemma-2-9b",  # 9B model for synthesis
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.5,  # Balance creativity + consistency
        max_tokens=800  # Longer synthesis response
    )

    response = await self.model_hub.inference(model_request)

    # 5. Parse synthesis result
    return SynthesisResult(
        answer=response.content,
        sources=top_k,
        confidence=self.calculate_confidence(response, top_k)
    )
```

**3. Fact-Checking & Confidence Scoring:**
- **Source Attribution:** Every claim linked to source
- **Contradiction Detection:** Flag conflicting information from different sources
- **Confidence Scoring:** 0.0-1.0 based on source agreement, recency, authority
- **Uncertainty Handling:** Explicit "I don't know" when confidence <0.5

RESEARCHER ARCHITECTURE:
=========================
**Model Configuration:**
```yaml
agent_type: "researcher"
category: "ai_agent"
layer: 3

personality:
  response_time_budget_ms: 3000
  reasoning_style: "knowledge_synthesis"
  description: "Knowledge synthesis, RAG, multi-store retrieval"

model_hub:
  primary_model: "gemma-2-9b"  # 9B model for synthesis
  fallback_model: "claude-3-haiku"  # Remote fallback (better synthesis)
  placement_preference: ["GPU", "Remote"]  # Quality over latency

capabilities:
  - TOOL_CALL  # Can call K0 retrieval APIs
  - MEMORY_READ  # Can read SessionState
  - MODEL_CALL  # Can call Model Hub
  - NETWORK_ACCESS  # Can query external APIs (if needed)

performance_targets:
  inference_latency_ms: 3000  # P95
  synthesis_quality: 0.85  # Human evaluation
  retrieval_recall: 0.90  # Multi-store coverage
```

**RAG Pipeline Stages:**
1. **Retrieve:** Multi-store query (100-500ms)
2. **Rerank:** Relevance scoring (50-100ms)
3. **Synthesize:** LLM inference (1000-2000ms)
4. **Fact-Check:** Confidence scoring (100-200ms)
5. **Total:** <3000ms P95

PERFORMANCE METRICS:
====================
- Knowledge retrieval: <3000ms P95 (full RAG pipeline)
- Synthesis quality: >85% (human evaluation)
- Model: gemma-2-9b (local GPU) or claude-3-haiku (remote)
- Fallback latency: <2000ms (remote claude-3-haiku)
- Token usage: ~1500 tokens/request (system + user + context + response)
- Retrieval recall: >90% (multi-store coverage)

INTEGRATION POINTS:
===================
**Layer 2 → Layer 3 (Task Assignment):**
```python
from k1.l3_execution.agents.researcher import ResearcherAgent

researcher = ResearcherAgent(config)
synthesis_result = await researcher.synthesize_knowledge(
    query="What are my favorite restaurants?"
)
# Returns: SynthesisResult(answer="...", sources=[...], confidence=0.92)
```

**Layer 3 → K0 (Multi-Store Retrieval):**
```python
# Researcher queries K0 memory stores
from k0.query import K0QueryClient

k0_client = K0QueryClient()
episodic_results = await k0_client.query_episodic(
    query="restaurants",
    time_range=(now - 7*24*3600, now),  # Last 7 days
    limit=10
)
```

**Layer 3 → Layer 4 (Model Hub):**
```python
# Researcher calls Model Hub for synthesis
from k1.l3_execution.model_hub import ModelHub

model_hub = ModelHub()
response = await model_hub.inference(model_request)
```

TESTING:
========
See tests/l3_execution/agents/test_researcher.py (ADR-0004d):
- Knowledge retrieval (<3000ms P95)
- Synthesis quality (>85% human evaluation)
- Multi-store coverage (>90% recall)
- Fact-checking (source attribution, confidence)
- Model placement (GPU → Remote fallback)
- Token usage tracking
- RAG pipeline stages (retrieve, rerank, synthesize)

OBSERVABILITY:
==============
Prometheus Metrics (ADR-0029):
- layer3_researcher_inference_latency_ms{model}
- layer3_researcher_synthesis_quality{metric="human_eval|confidence"}
- layer3_researcher_token_usage{model}
- layer3_researcher_retrieval_latency_ms{store_type}
- layer3_researcher_retrieval_recall{store_type}

Structured Logs:
```python
logger.info(
    "knowledge_synthesized",
    agent_id=agent_id,
    query=query,
    synthesis_confidence=confidence,
    source_count=len(sources),
    latency_ms=latency,
    model="gemma-2-9b",
    accelerator="GPU",
    trace_id=trace_id
)
```

RESEARCH FOUNDATIONS:
=====================
- RAG (Lewis et al. 2020) — Retrieval-Augmented Generation
- Multi-store memory (Tulving 1972) — Episodic, semantic, procedural
- Knowledge graphs (Singhal 2012) — Entity relationships, linked data
- Fact-checking (Thorne et al. 2018) — FEVER dataset, source attribution

AUTHOR: K1 Intelligence Module
VERSION: 1.0.0
LAST UPDATED: October 2025
"""
