• Build agentic AI systems: Design and implement tool-calling agents that combine retrieval, structured reasoning, and secure action execution (function calling, change orchestration, policy enforcement) following MCP protocol. Engineer robust guardrails for safety, compliance, and least-privilege access.

This is pretty much what I've been doing day-to-day at AT&T for the past year and a half. I own the pan-company agentic platform we built on LangGraph Studio — it's running 500+ production workflows across 80+ teams right now. The whole thing is basically an agent lifecycle system: teams come in, define their workflow as a LangGraph graph (tool-calling nodes, retrieval nodes, reasoning chains), register it against our capability registry, and deploy. We took onboarding from weeks down to minutes.

The guardrails piece was something I pushed hard on early. We built safety agents that sit in front of every deployment — they scan the incoming graph and enforce schema compliance, tool whitelists, and scoped access before anything goes live. Each agent gets a capability token that only grants access to what its workflow actually needs. No ambient authority, no privilege creep across tenants.

On the side, I've been building FamilyOS — a dual-kernel cognitive OS where I took this even further. Every agent action goes through YAML-defined capability contracts enforced at the kernel syscall layer, with formal ADR-driven governance. Overkill for a personal project? Maybe. But it's where I pressure-test ideas before bringing them to work.

• Productionize LLMs: Build evaluation framework for open-source and foundational LLMs; implement retrieval pipelines, prompt synthesis, response validation, and self-correction loops tailored to production operations.

I've done this twice now at very different scales — once at Microsoft AI Co-Innovation Labs working with external clients, and now at AT&T where I'm responsible for the eval infrastructure behind 500+ workflows.

At AT&T, I built out our Arize AI integration across the entire platform. Every workflow gets full instrumentation: traces, latency, token usage, quality metrics (BLEU, ROUGE, BERTScore, human feedback loops), drift detection. We run continuous A/B testing so teams can actually compare model providers and prompt strategies against cost and quality — not just vibes. I also built the response validation layer: structured output schemas, self-correction loops that re-prompt on schema violations or low confidence, and deterministic fallbacks when the LLM just isn't getting it right.

At Microsoft, it was more client-facing. I co-developed 14 end-to-end AI POCs in 12 months with Fortune 500 companies, walking each one from "we have this idea" through prompt synthesis, retrieval pipeline design, and production deployment on Azure OpenAI and Semantic Kernel.

I also fine-tuned and shipped a 13-head multitask encoder (UltraBERT v4, 149M params) as part of FamilyOS — sub-25ms P95, 98% inter-head accuracy across 13 NLU tasks. It's on PyPI if you want to look at it (familyos-ultrabert v4.0.7).

• Integrate with runtime ecosystems: Connect agents to observability, incident management, and deployment systems to enable automated diagnostics, runbook execution, remediation, and post-incident summarization with full traceability.

The platform I built at AT&T basically is the runtime ecosystem for 80+ teams. I don't just connect to observability — I own the observability layer.

Arize AI is the backbone. Every one of those 500+ workflows has distributed tracing, latency breakdowns, token accounting, quality scoring, and drift detection. When something goes wrong, you can trace from request to outcome in a single pane.

On the deployment side, we built automated pipelines with compliance checks baked in. Every deployment gets a standardized contract — it's auditable, reproducible, and rollback-ready. The safety agents I mentioned earlier do pre-deployment scanning, catching misconfigurations and policy violations before anything touches production. It's not glamorous work, but it's the kind of thing that keeps you sleeping at night when 80 teams are shipping independently.

• Collaborate directly with users: Partner with production engineers, and application teams to translate production pain points into agentic AI roadmaps; define objective functions linked to reliability, risk reduction, and cost; and deliver auditable, business-aligned outcomes.

This is honestly the part I enjoy most. At AT&T, my "users" are 80+ internal teams that all want different things. I work directly with each team to translate their workflow requirements into structured LangGraph deployments with clear SLOs — what's your latency budget, what's your cost ceiling, what quality bar are you holding yourself to. Then we build to that.

I also built the self-serve onboarding system that cut manual intervention by 80%. Before that, every team needed hand-holding from my platform team. Now they define, deploy, and monitor their own workflows. That freed us up to focus on the hard problems instead of being a bottleneck.

At Microsoft Labs, it was similar but external. I ran week-long residencies where I'd sit with a client's engineering team, co-build a POC, train them on the patterns, and hand off something they could actually take to production. Did that across six Microsoft AI Lab sites globally — Redmond, Munich, Shanghai, Singapore. Every team had different maturity levels and constraints, so you learn to adapt fast.

• Safety, reliability, and governance: Build validator models, adversarial prompts, and policy checks into the stack; enforce deterministic fallbacks, circuit breakers, and rollback strategies; instrument continuous evaluations for usefulness, correctness, and risk.

I'll be direct: most teams bolt safety on after the fact. I build it into the foundation.

At AT&T, nothing reaches production without passing our safety agents. They scan every incoming LangGraph graph — tool permissions, data access scopes, schema compliance. If it fails, it doesn't deploy. Period. We also run continuous evaluation pipelines that score every workflow execution for usefulness, correctness, and risk. It's not a checkbox exercise; the numbers actually drive decisions about what stays in production.

In FamilyOS, I went deeper. Full capability-based security at the kernel layer — every syscall gated by capability tokens, circuit breakers for cascade failure protection, dead letter queues for audit trails, and a custom Rust message bus that enforces zero-copy isolation between agents. I also built governance scanners that validate ADR-to-code consistency, contract cross-references, and pipeline wiring integrity across both kernels. If the code drifts from the documented architecture, the scanner catches it before merge.

And I don't just write the safety code — I break it. We ran 5,000+ integration tests with chaos engineering: fault injection, network partitions, resource exhaustion. That's how you actually know your fallbacks work.

• Scale and performance: Optimize cost and latency via prompt engineering, context management, caching, model routing, and distillation; leverage batching, streaming, and parallel tool-calls to meet stringent SLOs under real-world load.

Two layers: the platform layer at AT&T where 500+ workflows run concurrently, and the inference layer in FamilyOS where I control every millisecond.

At AT&T, our eval framework lets teams A/B test model providers and prompt strategies against real cost and quality numbers. Teams use it to decide when GPT-4 is worth the spend vs. a cheaper model vs. a fine-tuned one. That's a live decision that happens on every workflow.

FamilyOS is where I got to build the performance stack from scratch. The model selection layer is capability-based — callers express intent ("fast", "smart", "cheap") not model names. A routing table maps (capability, actor) pairs to the right model. When a new model drops, I update one table, zero caller changes. The orchestrator does tier-based routing: LOW tasks go straight to the back actor, MEDIUM tasks get a TaskEnvelope with budget constraints, HIGH tasks get the full planner with token budgets. Each tier has explicit fabric budgets and planner token limits.

For parallel tool-calls specifically, I built a parallelism rule engine. Tools are classified into groups — cognitive tools (update_beliefs, update_scoreboard, refine_affect) run in parallel since they write to independent session state sections. Control tools (dispatch_task, submit_result) are always sequential — one call, end of iteration. Read tools are parallel-safe with anything. The ToolDispatcher enforces this with a 6-step validation pipeline: allowlist check, budget check, schema validation, safety band check, dispatch, then record. It's not just "parallel tools" as a concept — it's formalized rules about which specific tools can batch together and why.

The DynamicPromptBuilder handles context management — it assembles per-mode prompts with only the session state sections that mode actually needs (full, slim, or skip per section), mode-specific tool allowlists, and affect-adjusted iteration limits. A STANDARD turn reads full beliefs and scoreboard; a PRESENT turn skips most of it and just injects the task result. That's how I keep token costs down without losing context where it matters.

Circuit breakers handle degradation: if the planner trips, HIGH degrades to MEDIUM. If the orchestrator trips, MEDIUM degrades to LOW. If fabric trips, you get a canned response. The user never sees the degradation — the FSM receives the same result events regardless of which tier actually executed.

• Build a RAG pipeline: Curate domain-knowledge; build data-quality validation framework; establish feedback loops and milestone framework maintain knowledge freshness.

FamilyOS is basically a purpose-built RAG system with a cognitive shell on top. The whole point is that a family AI needs to remember everything across conversations — medical details, financial context, relationship dynamics, kids' school stuff — and surface the right context at the right time without stuffing it all into a prompt.

The K0 memory kernel handles storage: vector (pgvector/FAISS) for semantic search, relational (PostgreSQL) for structured family data, and knowledge graph for relational queries like "who is Dad's cardiologist" or "what medications does Grandma take." The retrieval layer combines dense embedding search with sparse retrieval (BM25, SPLADE) and graph traversal, with learned re-ranking and fusion strategies (RRF, ColBERT-v2) on top.

But the part I'm most proud of is the domain-aware safety layer built into retrieval. When the conversation enters a health domain, specific rules get injected: never diagnose, never interpret lab results, offer to find providers. Finance domain: exact amounts only, never round, require confirmation above $500, never auto-approve recurring charges. Children domain: route all actions through parent profile, filter age-inappropriate content. Elder care: simpler language, short sentences, max 3 options, confirm understanding. Legal: never provide legal advice, period. Six domains total, each with a safety floor classification (GREEN/AMBER/RED). These rules are cumulative with the mode's existing safety band — they add constraints, they don't replace.

For knowledge freshness, the memory kernel runs consolidation pipelines — episodic-to-semantic promotion, decay curves, deduplication. There's a delta system with a session delta writer, snapshot reader, and overflow handling that tracks what changed in each conversation and feeds it back into the memory stores. A ledger system (write-ahead log with projections and recovery) ensures nothing gets lost if the system crashes mid-write.

The K1 side has a recall_memory tool that agents call during the ReAct loop to pull context on demand. The DynamicPromptBuilder injects family context (active member, family relationships) into the prompt via scenario templates, and async results from background tasks get woven in naturally — the agent says "oh, about that thing you asked earlier" instead of dumping a result block.

At Microsoft Labs, I designed RAG solutions for 14 clients on Azure Cognitive Services and Azure OpenAI — each with different domain knowledge requirements and quality validation needs. But FamilyOS is where I got to build the full stack end-to-end with no compromises.

• Raise the bar: Drive design reviews, experiment rigor, and high-quality engineering practices; mentor peers on agent architectures, evaluation methodologies, and safe deployment patterns

I'm on AT&T's core architecture team for the agentic platform. Every significant design decision goes through formal review — ADR-driven, contract-first, traceable from decision to implementation. I'm the one who established that standard, and it's what 80+ teams follow now for deployment contracts, compliance checks, and evaluation frameworks.

On the people side, I mentored and onboarded 4 engineers onto the platform team. I currently lead 6 engineers. It's a small team relative to the surface area we cover, so everyone has to be operating at a high level — which means I spend real time on code reviews, architecture walkthroughs, and making sure people understand the "why" behind our patterns, not just the "what."

At Microsoft Labs, I trained client engineering teams during week-long residencies. The goal wasn't just delivering a POC — it was making sure their engineers walked away with the agent architectures, eval methodologies, and deployment patterns to build the next thing on their own.

In FamilyOS, I built automated governance scanners that enforce code-to-documentation consistency. If you push code that drifts from the accepted architecture, the scanner blocks it. I hold myself to the same standard I'd hold anyone else.
