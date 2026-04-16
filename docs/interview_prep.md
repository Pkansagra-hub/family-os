# AI/ML Interview Preparation Guide

**Mapped to FamilyOS project (K0, K1, Bridge, POC)**

---

## Area 1: AI Technology & Core ML Skills

### 1.1 Training & Evaluation

#### Topic 1: Pre-training vs Post-training
- **Pre-training**: Self-supervised on massive corpus (next token prediction for LLMs, masked language modeling for BERT). Learns general representations. Requires massive compute (thousands of GPUs, weeks/months).
- **Post-training**: Umbrella term for everything after pre-training — SFT, RLHF, DPO, distillation, quantization. Aligns model to task/user intent with orders of magnitude less compute.
- **Key distinction**: Pre-training = capability acquisition. Post-training = capability alignment and refinement.
- **FamilyOS**: UltraBERT is a post-trained model — fine-tuned from a BERT base for family-domain NER, sentiment, safety, and embeddings. Replaced 9 separate pre-trained models into 1 unified model (4.6GB → 500MB).

#### Topic 2: SFT (Supervised Fine-Tuning)
- **What**: Train model on (input, desired_output) pairs with standard cross-entropy loss. The most direct way to teach a model a new task or format.
- **Data format**: Instruction-response pairs (chat format), or task-specific labeled data (NER tags, sentiment labels).
- **Common pitfalls**: Catastrophic forgetting (model loses pre-trained knowledge), overfitting on small datasets, distribution mismatch between SFT data and real usage.
- **Best practices**: Learning rate 1e-5 to 5e-5 (lower than pre-training), cosine schedule with warmup, mix in some pre-training data to prevent forgetting.
- **FamilyOS**: UltraBERT SFT on family-domain data — NER labels (~15 family-domain entity types), sentiment (positive/negative/neutral with clinical safety), temporal entity extraction. Training data: 565K events from R1 dataset.

#### Topic 3: PEFT / LoRA / QLoRA
- **PEFT (Parameter-Efficient Fine-Tuning)**: Only update a small subset of parameters. Types: adapters, prefix tuning, LoRA.
- **LoRA (Low-Rank Adaptation)**: Decompose weight update ΔW = BA where B ∈ R^(d×r), A ∈ R^(r×k), r << min(d,k). Typically r=8-64. Only train A, B matrices. Merge at inference: W' = W + BA (zero latency overhead).
- **QLoRA**: Quantize base model to 4-bit (NF4 data type), apply LoRA adapters in fp16/bf16. Enables fine-tuning 65B models on single 48GB GPU.
- **When to use**: Limited compute, domain adaptation, multi-task (swap LoRA adapters per task), rapid iteration.
- **FamilyOS**: UltraBERT could use LoRA for domain-specific adaptation (e.g., medical family events vs daily routine) without retraining full model. K0 feature flags support per-module tier selection enabling A/B testing of LoRA variants.

#### Topic 4: RLHF (Reinforcement Learning from Human Feedback)
- **3-step pipeline**:
  1. **SFT**: Fine-tune base model on demonstrations
  2. **Reward Model (RM)**: Train on human preference pairs (chosen vs rejected). Bradley-Terry model: P(y1 > y2) = σ(r(y1) - r(y2))
  3. **PPO optimization**: RL policy optimization maximizing reward while staying close to SFT model (KL penalty)
- **DPO (Direct Preference Optimization)**: Skips reward model. Directly optimizes policy from preference pairs. Loss: -log σ(β(log π(y_w)/π_ref(y_w) - log π(y_l)/π_ref(y_l))). Simpler, more stable, lower compute.
- **Key challenge**: Reward hacking — model exploits reward model weaknesses. Mitigate with KL constraint, reward model ensembles, iterative RLHF.
- **FamilyOS**: Learning Loop System 2 IS the feedback collection infrastructure for RLHF-style improvement:
  - Signal weights: correction=0.85, validation=0.90, reformulate=0.65, abandonment=0.70, hedging=0.50
  - Feedback Envelope Builder → Bridge → K0 P05 pipeline
  - Could directly feed DPO training: (user_query, good_response, bad_response_that_got_corrected)

#### Topic 5: Optimizers & Learning Rates
- **Adam**: Adaptive learning rates per parameter. Maintains 1st moment (mean) and 2nd moment (variance) of gradients. Default: lr=1e-3, β1=0.9, β2=0.999, ε=1e-8.
- **AdamW**: Decoupled weight decay (not L2 regularization). Standard for transformer training. Weight decay 0.01-0.1.
- **Learning rate schedules**:
  - Linear warmup (1-10% of steps) → cosine decay to 0
  - Constant with warmup
  - WSD (Warmup-Stable-Decay): warmup → constant → decay (popular for LLM pre-training)
- **Key insight**: LR too high → divergence. LR too low → slow convergence/stuck in local minima. Warmup prevents early instability.
- **FamilyOS**: K0 ModelRegistry manages model lifecycle. Understanding optimizer config matters for when UltraBERT needs retraining or fine-tuning on new family data.

#### Topic 6: Loss Functions
- **Cross-entropy**: Standard classification loss. -Σ y_i log(p_i). Used for NER, sentiment, safety classification.
- **Contrastive loss**: Pull similar pairs together, push dissimilar apart. L = (1-y)·D² + y·max(0, margin-D)².
- **Triplet loss**: L = max(0, d(anchor,positive) - d(anchor,negative) + margin). Requires hard negative mining.
- **InfoNCE**: Contrastive loss over batch. L = -log(exp(sim(q,k+)/τ) / Σ exp(sim(q,ki)/τ)). Used in CLIP, SimCLR.
- **Cosine embedding loss**: Directly optimizes cosine similarity.
- **FamilyOS**: UltraBERT embeddings are L2-normalized (unit vectors) → cosine similarity = dot product (IndexFlatIP in FAISS). Training likely used contrastive or triplet loss for embedding quality. POC benchmark: STS mean=0.9307, but negation similarity=0.9549 (poor) — reveals loss function didn't capture semantic opposition.

#### Topic 7: Evaluation Metrics
- **Retrieval metrics**:
  - **MRR (Mean Reciprocal Rank)**: 1/rank of first relevant result, averaged. MRR=1.0 means always rank 1.
  - **nDCG (Normalized DCG)**: Accounts for graded relevance and position. DCG = Σ rel_i / log2(i+1).
  - **Recall@K**: Fraction of relevant items in top-K. Recall@1 is hardest.
- **Classification metrics**: Precision, Recall, F1 (harmonic mean), Cohen's Kappa.
- **Generation metrics**: Perplexity (lower=better, exp of avg cross-entropy), BLEU, ROUGE, BERTScore.
- **FamilyOS POC results**:
  - Episode retrieval: MRR=0.7770, nDCG=0.7745 (v4 pipeline, 49 human queries)
  - Recall@1/100=1.0 (but benchmark diagnostic revealed distractors too easy)
  - Paraphrase F1=0.8333
  - STS mean=0.9307 ± 0.0255
  - Threshold tuning: optimal=0.85, F1=0.889
  - Domain transfer: medical=0.916, legal=0.937, tech=0.865, business=0.816

---

### 1.2 ML Workflows & Debugging

#### Topic 8: ML Pipeline Orchestration (XManager, Vertex, etc.)
- **XManager**: Google's experiment management — defines experiments as computational graphs, manages hyperparameter sweeps, tracks runs.
- **Vertex AI Pipelines**: Kubeflow-based, YAML/Python SDK, artifact tracking, model registry.
- **MLflow**: Open-source experiment tracking, model registry, deployment.
- **Key concepts**: Reproducibility (config versioning), artifact lineage, hyperparameter search (grid, random, Bayesian), distributed training coordination.
- **FamilyOS parallel**: K0 PipelineRunner is a DAG-based execution engine:
  - YAML pipeline specs define stages and dependencies
  - Topological sort for execution order
  - Parallel execution grouping for independent modules
  - Per-stage configuration overrides
  - ModuleRegistry: dynamic module lookup + contract validation
  - P02 pipeline orchestrates 16+ modules in DAG order

#### Topic 9: Debugging Model Issues
- **Overfitting**: Train loss drops, val loss increases. Fix: more data, regularization, early stopping, dropout, data augmentation.
- **Underfitting**: Both losses high. Fix: larger model, more features, less regularization, longer training.
- **Data leakage**: Test performance unrealistically high. Check: temporal leakage, feature leakage, train/test overlap.
- **Gradient issues**: Vanishing (deep networks, sigmoid), exploding (large LR, no clipping). Fix: gradient clipping, residual connections, layer norm.
- **Distribution shift**: Model works on benchmark, fails in production. Fix: representative eval sets, hard negatives, domain-specific test splits.
- **FamilyOS**: POC benchmark diagnostic (`benchmark_diagnostic.py`) caught critical issues:
  - Distractors were topically unrelated → inflated Recall@1 to 1.0 (impossible in practice)
  - Proposed same-domain hard negatives for realistic testing
  - Detected zero variance in results → test didn't reflect real-world difficulty
  - Negation blindness: "I love X" ≈ "I hate X" (sim=0.9549) — known embedding model limitation
  - Semantic role reversal: "A chased B" ≈ "B chased A" (sim=0.9896) — architectural limitation

#### Topic 10: Debugging Infrastructure Issues
- **GPU OOM**: Reduce batch size, gradient accumulation, mixed precision (fp16/bf16), gradient checkpointing, model parallelism.
- **Training hangs**: NCCL deadlocks (distributed training), data loader bottleneck, I/O stall. Debug: NCCL_DEBUG=INFO, profiler.
- **Slow training**: Profile with PyTorch Profiler or TF Profiler. Common: data loading (num_workers), CPU-GPU transfer, inefficient ops.
- **Inference issues**: Memory leak (KV cache growth), latency spike (batch size), throughput collapse (head-of-line blocking).
- **FamilyOS**: K0 ModelRegistry handles these:
  - Lazy loading (models on first use, not startup)
  - GPU/CPU fallback on OOM (device_preference: cuda → cpu)
  - Memory budgets per tier: ultrabert=600MB, spacy=100MB
  - Timeout enforcement: 60s model load, 30ms inference P95
  - K1 Model Hub: circuit breaker per provider, rate limiting at 80% headroom

---

### 1.3 Serving Architecture

#### Topic 11: Serving Stacks
- **vLLM**: PagedAttention (KV cache as virtual memory pages), continuous batching, prefix caching. Industry standard for LLM serving.
- **TensorRT-LLM**: NVIDIA optimized. In-flight batching, FP8 quantization, multi-GPU tensor parallelism.
- **TGI (Text Generation Inference)**: HuggingFace. Flash Attention, continuous batching, watermarking.
- **Triton Inference Server**: Multi-framework (TF, PyTorch, ONNX, TRT). Dynamic batching, model ensembles, concurrent model execution.
- **ONNX Runtime**: Cross-platform inference optimization. Graph optimization, quantization, execution providers.
- **FamilyOS**: K1 Model Hub supports 5 Day-1 providers: OpenAI, Anthropic, Google, vLLM, Ollama. Plugin architecture (`IModelHubPort`) means any new serving stack can be added. 9-step request pipeline: validate → budget → priority → route → select → cache → normalize → dispatch → post-process.

#### Topic 12: Request Flow & KV Cache
- **Prefill phase**: Process full prompt, generate KV cache entries for all input tokens. Compute-bound. Latency = f(prompt_length).
- **Decode phase**: Autoregressive generation, 1 token at a time, KV cache lookup for past tokens. Memory-bound. Latency = f(output_length).
- **Continuous batching**: New requests join mid-batch (vs static batching where all start/end together). Improves GPU utilization 2-10x.
- **PagedAttention (vLLM)**: KV cache stored in non-contiguous blocks (like OS virtual memory). Eliminates memory fragmentation. Enables sharing (prefix caching, beam search).
- **Speculative decoding**: Small draft model generates K tokens, large model verifies in parallel. Reduces latency without quality loss.
- **FamilyOS KV cache design**: K1 cache module implements 3-tier system:
  - HOT: Active inference (<1ms), thermal-optimized
  - WARM: Recent (<5ms), compressed
  - COLD: Evicted (<50ms reactivation)
  - Adaptive sizing based on workload (ADR-0060a)
  - Thermal-aware placement: NPU→GPU→CPU→Remote
  - Global budget: 512MB

#### Topic 13: GenAI Security
- **Prompt injection**: User input manipulates system prompt. Types: direct ("ignore previous instructions"), indirect (data contains instructions).
- **Jailbreaking**: Bypassing safety filters. Types: role-play, multi-turn escalation, encoding tricks.
- **Guardrails**: Input/output filtering, content classification, safety classifiers, structured output enforcement.
- **Data poisoning**: Malicious training data → backdoor triggers.
- **Model extraction**: API queries to reconstruct model weights.
- **FamilyOS multi-layer security**:
  - K0 Gate: 10-step validation (signature, schema, replay detection, Ed25519 verification)
  - K0 Policy: 6-phase PEP (device posture, band blocking, capability checks, ABAC)
  - K1 SafetyWatchAgent: URGENT priority (<5ms), clinical_safety_risk heads, safety_familyos_band
  - Privacy bands: GREEN→YELLOW→ORANGE→RED with escalating encryption/isolation
  - UltraBERT safety heads: 96.2% safety accuracy
  - PII detection in Memory Writer (ADR-0035), E2EE (ADR-0036)

#### Topic 14: Tool Use / Function Calling
- **MCP (Model Context Protocol)**: Anthropic's standard for LLM↔tool communication. Server-client architecture, tool discovery, typed parameters.
- **Function calling**: LLM outputs structured JSON specifying function name + args. Runtime executes and returns result. Key: schema definition, error handling, parallel calls.
- **ReAct pattern**: Reason → Act → Observe loop. LLM decides which tool, executes, observes result, reasons about next step.
- **Agent tool execution**: Orchestrator manages tool selection, execution, result aggregation, error recovery.
- **FamilyOS**: K1 Fabric is a full tool execution engine:
  - 6 provider types: MCP (stdio/SSE), WASM (sandboxed), Bridge (K0), Agent (LLM), Workflow (DAG), Concierge
  - Tool batching (ADR-0078): parallel execution of independent calls, DAG dependency tracking
  - Circuit breaker per provider (MH-05)
  - Auto-discovery from `tools/mcp_servers/` and `tools/wasm_modules/`
  - Contract validation (YAML schema)
  - Capability security: least-privilege per tool

---

## Area 2: AI Application & Strategic Mindset

### 2.1 User Pain Points

#### Topic 15: Identifying User Pain Points
- **Signal types**: Explicit (complaints, low ratings, support tickets) vs Implicit (abandonment, reformulation, correction, hesitation).
- **Behavioral analysis**: Session-level patterns — user retries, topic changes, hedging language indicate confusion or failure.
- **Measurement**: Task completion rate, time-to-completion, user satisfaction (CSAT), Net Promoter Score.
- **Prioritization framework**: Impact × Frequency × Feasibility.
- **FamilyOS**: Concierge classifies 11 meta-intents that directly surface pain:
  - `correction` (weight 0.85): User correcting AI → AI was wrong
  - `abandonment` (weight 0.70): User gave up → task too hard or broken
  - `hedging` (weight 0.50): User uncertain → AI wasn't clear
  - `reformulation` (weight 0.65): User rephrasing → AI didn't understand
  - `retry`: User asking again → first attempt failed
  - `ambiguous_query`: User input unclear → needs clarification
  - These signals feed directly into Learning Loop System 2 for model refinement

#### Topic 16: Latency vs Quality Tradeoffs
- **When small models win**: Classification, routing, intent detection, structured extraction — where speed matters more than generation quality.
- **When large models win**: Complex reasoning, multi-step planning, creative generation, nuanced safety decisions.
- **Cascade pattern**: Fast small model handles easy cases; only escalate to large model for hard cases. Saves 60-80% compute.
- **Distillation**: Train small model to mimic large model outputs. Retains most quality at fraction of latency/cost.
- **FamilyOS implements this**:
  - K0 ML tier cascade: RULE_BASED(<10ms) → SPACY_SMALL(~15ms) → TRANSFORMER(~70ms) → ULTRABERT(~30ms GPU)
  - K1 complexity routing: LOW(direct Fabric) → MEDIUM(1-2 Fabric calls) → HIGH(Planner DAG)
  - Feature flags: per-module enabled_tier + fallback_tier + rollout_percentage
  - Auto-fallback on repeated failures (Gap 36)
  - Model Hub budget: $5/day default, hard rejection on exceed

#### Topic 17: Error Recovery & Graceful Degradation
- **Graceful degradation**: Provide reduced but functional experience when components fail. Never crash silently.
- **Circuit breaker pattern**: CLOSED→OPEN (on N failures)→HALF_OPEN (probe)→CLOSED. Prevents cascade failures.
- **Retry strategies**: Exponential backoff with jitter. Max retries. Idempotency keys for safe retries.
- **HIL (Human-in-Loop)**: Escalate to user when AI confidence is low. Better than wrong answer.
- **FamilyOS implements all of these**:
  - Orchestrator: max 2 retries (ORCH-06), cascading failure (ORCH-07), saga recovery
  - Planner: HITL escalation on constraint failure, max 45s planning time
  - Model Hub: circuit breaker per provider (MH-05), fallback chains (MH-06)
  - K0 Outbox: exponential backoff (2^n), DLQ for permanent failures
  - K1 SessionState: HOT→WARM→COLD tier fallback, budget rejection over OOM
  - Concierge: 11-state FSM with recovery transitions

---

### 2.2 Product Strategy & Architecture

#### Topic 18: System Architecture for Evolving Agents
- **Key challenges**: Adding capabilities without breaking existing ones, versioning agent behavior, managing state across turns, tool discovery.
- **Plugin architecture**: New capabilities as modules, not core changes. Contract-based integration.
- **Agent lifecycle**: Spawn → execute → terminate with resource cleanup. Prevent zombie agents.
- **State management**: Conversation state vs persistent memory vs ephemeral working memory.
- **FamilyOS**: K1 is a textbook evolving agent architecture:
  - 7 strict layers (L0-L6) with defined invariants — changes in one layer don't break others
  - Agent lifecycle FSM: PENDING→WARMING→ACTIVE→IDLE→DRAINING→TERMINATED (ADR-0005)
  - Module system: `modules/<domain>/module.yaml` + tools + agents — fully pluggable
  - Agent Registry: 58+ agent types, O(1) lookup, Factory pattern instantiation
  - Tool auto-discovery: new MCP servers or WASM modules automatically registered
  - SessionState: 96KB budget with 3-tier memory (HOT/WARM/COLD) — bounded, predictable

#### Topic 19: ML Developer Experience
- **API design**: Clear contracts, consistent errors, discoverable capabilities, good defaults.
- **Tooling**: Model registry, experiment tracking, evaluation frameworks, deployment automation.
- **Observability**: Developers need to see what the model is doing — traces, metrics, logs.
- **FamilyOS**:
  - K0 Fabric: capability-based request/reply with typed contracts
  - YAML-defined pipelines and module contracts — self-documenting
  - 5 Grafana dashboards + 18 SLO alerts + OpenTelemetry tracing
  - `IModelHubPort`: single gateway with `execute`, `stream_execute`, `discover_capabilities`, `health`
  - trace_id required on ALL requests (MH-03) — full audit trail

#### Topic 20: Multi-Model Orchestration
- **Model routing**: Route requests to different models based on task type, complexity, cost, latency requirements.
- **Fallback chains**: Primary model → secondary → tertiary. Each with circuit breaker.
- **Cost management**: Per-model pricing awareness, daily/monthly budgets, cost-per-query tracking.
- **Model selection**: Weighted scoring across latency, quality, cost, availability.
- **FamilyOS Model Hub (18 invariants)**:
  - 9-step pipeline: validate → budget check → priority → capability routing → model selection → cache → normalize → dispatch → post-process
  - 5-step capability routing with filtering (MH-06, MH-18)
  - Weighted priority scoring for model selection (MH-13)
  - $5/day budget with hard rejection (MH-04, MH-08)
  - 5min cache TTL with LRU (MH-09)
  - Per-provider circuit breakers (MH-05)
  - Streaming via async generators (MH-10)
  - Full cost tracking from manifest (MH-07, MH-11)

#### Topic 21: Edge vs Cloud Tradeoffs
- **Edge advantages**: Low latency, offline capability, privacy (data stays on device), cost (no API calls).
- **Cloud advantages**: Larger models, more compute, centralized state, easier updates, shared learning.
- **Hybrid pattern**: Edge for real-time + privacy-sensitive. Cloud for complex reasoning + persistent memory.
- **FamilyOS is a hybrid system**:
  - K1 (edge): SQLite local storage, works offline, 96KB SessionState cap (device memory constraints)
  - K0 (cloud): PostgreSQL, vector search, full episodic memory, learning pipelines
  - Bridge: handles disconnect gracefully, local command queue, health checker, SSE with reconnect
  - KV cache thermal-aware placement: NPU→GPU→CPU→Remote (adapts to device capability)

---

## Area 3: AI Innovation & Industry Awareness

#### Topic 22: vLLM Deep Dive
- **PagedAttention**: KV cache stored in fixed-size blocks (pages). Virtual-to-physical page mapping. Reduces memory waste from 60-80% to <4%.
- **Continuous batching**: Iteration-level scheduling. New requests join after each decode step. Maximizes GPU utilization.
- **Prefix caching**: Share KV cache for common prefixes (system prompts). Automatic prefix detection.
- **Chunked prefill**: Split long prompts into chunks, interleave with decode steps. Reduces time-to-first-token for concurrent requests.
- **Quantization support**: AWQ, GPTQ, FP8, INT8. Trade quality for throughput.
- **Why it matters**: Open-source, production-grade, 14x-24x throughput over naive serving. Google should understand this competitive landscape.

#### Topic 23: Open-Source Model Ecosystem
- **Llama 3/4 (Meta)**: 8B-405B params, strong reasoning, open weights, commercial license.
- **Mixtral/Mistral (Mistral AI)**: MoE architecture (8 experts, 2 active), efficient inference, strong multilingual.
- **Gemma (Google)**: 2B-27B, optimized for on-device, Keras integration.
- **Phi (Microsoft)**: 1.3B-14B, strong for size, "textbook quality" training data.
- **DeepSeek**: R1 (reasoning), V3 (MoE 671B, 37B active). Open weights, competitive with frontier.
- **Trends**: Smaller models getting better (scaling laws for data quality), MoE for efficiency, specialization via fine-tuning.

#### Topic 24: Agent Frameworks
- **LangGraph**: Graph-based agent orchestration, state management, human-in-loop, streaming.
- **CrewAI**: Multi-agent collaboration, role-based agents, task delegation.
- **AutoGen (Microsoft)**: Conversable agents, group chat, code execution.
- **MCP (Anthropic)**: Tool protocol standard — server/client, tool discovery, typed schemas.
- **FamilyOS K1 as an agent framework** — comparisons:
  - vs LangGraph: K1 has stricter layering (16 orchestrator invariants), formal DAG with saga recovery
  - vs CrewAI: K1 has 58+ agent types with lifecycle FSM, WFQ scheduling (not just round-robin)
  - vs AutoGen: K1 separates planning (L3) from execution (L2) from tools (L2.5) — cleaner separation
  - K1 natively supports MCP (stdio + SSE) + WASM + Bridge providers

#### Topic 25: RAG vs Fine-Tuning vs Long Context
- **RAG**: External knowledge retrieval → context injection. Best for: factual recall, up-to-date info, domain knowledge, citation needed.
- **Fine-tuning**: Modify model weights. Best for: format/style, domain terminology, consistent behavior, task specialization.
- **Long context**: Models with 128K-1M token windows. Best for: document QA, code understanding, multi-document synthesis.
- **Decision framework**:
  - Need facts → RAG
  - Need behavior/style → Fine-tune
  - Need to reason over large documents → Long context
  - Often combine: fine-tuned model + RAG for best results
- **FamilyOS**: Implements production RAG:
  - 2-stage retrieval: semantic (3-path RRF: IDF centroids + event-level + DiagMahalanobis) → structural fusion (social, spatial, temporal, affective axes)
  - MRR=0.777 on human-annotated benchmark
  - FAISS IndexFlatIP for dense retrieval, FTS5+BM25 for keyword
  - Key insight: IDF-weighted centroids > text-embeddings universally; BM25 complement rejected (redundant with UltraBERT)

#### Topic 26: Multimodal AI Trends
- **Vision-Language Models**: GPT-4V, Gemini, LLaVA. Image understanding, document parsing, visual reasoning.
- **Speech/Audio**: Whisper, USM, AudioPaLM. Real-time transcription, voice agents.
- **Structured output**: JSON mode, function calling, constrained decoding. Critical for agent reliability.
- **Video understanding**: Long video comprehension, temporal reasoning.
- **FamilyOS**: Designed for multimodal:
  - L0 External Interfaces: Web, Mobile, Voice transport
  - Voice barge-in protocol (ADR-0058) with <100ms intent classification target
  - Multi-modal input ports in Concierge
  - Structured output enforcement in Orchestrator (ORCH-15: output schema validation)

#### Topic 27: Google-Specific Opportunities
- **Gemini**: Multimodal native, long context (1M+ tokens), strong on reasoning/coding.
- **TPUs**: Custom ML accelerators. v5e for inference, v5p for training. Cost-effective for large-scale serving.
- **Vertex AI**: Managed ML platform — training, serving, evaluation, model garden, RAG API.
- **Search + AI integration**: Grounding with Google Search, knowledge graph integration.
- **Strategic framing for FamilyOS**:
  - K1 Model Hub plugin architecture → Gemini as Day-1 provider
  - Edge deployment → Gemma on-device (Pixel, Android)
  - K0 PostgreSQL → could leverage Spanner/BigTable for scale
  - Retrieval pipeline → Vertex AI RAG API compatibility
  - Privacy bands → align with Google's Responsible AI principles

---

## Area 4: Data-Oriented Mindset

### 4.1 Data Collection & Sourcing

#### Topic 28: Initial Datasets for Fine-Tuning
- **Sourcing strategies**: Public datasets (HuggingFace), synthetic generation (LLM-generated), human annotation, production logs (with consent).
- **Size guidelines**: Classification ~1K-10K examples per class. NER ~5K-50K annotated sentences. Generation ~10K-100K examples.
- **Quality > quantity**: Clean, representative, balanced data beats massive noisy data.
- **Annotation workflows**: Guidelines → pilot annotation → inter-annotator agreement → iterate → full annotation.
- **FamilyOS data**:
  - R1 dataset: 565K events with NER labels, sentiment, emotion, salience, location, participants
  - 88 episodes, ~529 events (episodic memory benchmark)
  - 49 human-annotated queries (retrieval benchmark)
  - 22 realistic Fabric contracts (tools, agents, prompts)
  - 15 family-domain entity types for NER
  - Multi-label emotions: up to 15+ per event

#### Topic 29: RAG Data Pipelines
- **Chunking strategies**: Fixed-size, sentence-based, semantic (embedding similarity), recursive (hierarchical).
- **Embedding**: Model selection (sentence-transformers, OpenAI, Cohere), dimension tradeoffs (384 vs 768 vs 1536).
- **Indexing**: FAISS (flat, IVF, HNSW), pgvector, Pinecone, Weaviate, Qdrant.
- **Retrieval optimization**: Hybrid search (dense + sparse), re-ranking (cross-encoder), query expansion.
- **FamilyOS RAG pipeline**:
  - K0 pipelines: P02 (episodic write), P03 (indexing), P08 (embedding)
  - FAISS IndexFlatIP for dense retrieval (cosine via L2-normalized vectors)
  - FTS5 + BM25 for sparse retrieval
  - 3-path RRF fusion: IDF centroids (weight 1.0) + event-level weighted_max (weight 5.0) + DiagMahalanobis (weight 1.0), k=60
  - 2nd layer: structural fusion with axis weights: spatial=0.620, social=0.331, temporal=0.025, affective=0.025
  - Formula: (1-γ)*semantic + γ*structural, γ=0.35

#### Topic 30: Synthetic Data Generation
- **Techniques**: LLM paraphrasing, back-translation, template filling, style transfer, distillation-based generation.
- **Quality control**: Human spot-checking, automated filtering (perplexity, deduplication, consistency checks).
- **Risks**: Model collapse (training on own outputs), lack of diversity, amplifying biases.
- **FamilyOS**:
  - POC text augmentation: templates for short-text semantic enrichment
  - Instruction prefixes: "query:" / "document:" for embedding quality
  - Benchmark diagnostic identified need for synthetic hard negatives (same-domain distractors)
  - Text normalization: lowercase + whitespace cleanup (zero-cost improvement)

---

### 4.2 Data Quality

#### Topic 31: Inter-Annotator Agreement
- **Cohen's Kappa (2 annotators)**: κ = (p_o - p_e) / (1 - p_e). Where p_o = observed agreement, p_e = expected by chance.
  - κ > 0.8: almost perfect. 0.6-0.8: substantial. 0.4-0.6: moderate. <0.4: poor.
- **Fleiss' Kappa (3+ annotators)**: Extension of Cohen's for multiple raters. Same interpretation scale.
- **Krippendorff's Alpha**: Handles missing data, ordinal/interval scales, any number of raters. Most general.
- **For RLHF specifically**: Preference agreement rates. Typical target: >70% pairwise agreement. Low agreement → noisy reward model → reward hacking.
- **FamilyOS**: Learning Loop System 2 collects feedback signals. For RLHF data quality:
  - Need annotator agreement on which responses deserve correction (signal weight 0.85)
  - Validation signals (0.90) are clearest — user explicitly confirms good response
  - Hedging (0.50) is noisiest — requires multiple annotators to determine if it indicates real failure

#### Topic 32: Handling Data Quality Issues
- **Label noise**: Mislabeled training data. Detection: confident learning (find examples where model disagrees with label). Fix: re-annotate, down-weight noisy samples.
- **Class imbalance**: Rare classes under-represented. Fix: oversampling (SMOTE), class weights, focal loss, stratified sampling.
- **Data drift**: Production data diverges from training data. Detection: feature distribution monitoring, prediction confidence tracking. Fix: continuous retraining, data flywheels.
- **Missing data**: Handle with imputation, indicator features, or model architectures that handle missing values.
- **FamilyOS data quality practices**:
  - POC audit (`_st_epi_audit.py`): column-level NULL tracking, schema completeness checks (30+ columns)
  - Sentiment label backfill: positive/negative/neutral thresholds
  - Duration bucket validation: <1min to >24h (Event Segmentation Theory: 5min-4h optimal)
  - Events/episode distribution analysis (Working Memory Capacity: 3-20 events ideal)
  - Embedding availability validation (768-dim vectors stored)

#### Topic 33: Hard Negatives Mining
- **Why**: Easy negatives give inflated metrics. Model learns to distinguish apples from oranges, not apples from similar-looking apples.
- **Techniques**:
  - **In-batch negatives**: Other examples in same batch (simple, effective at scale).
  - **BM25 negatives**: Keyword-similar but semantically different (good for retrieval).
  - **Model-based negatives**: Top-K retrieval misses that are close but wrong.
  - **Adversarial negatives**: Manually crafted confusing examples.
- **FamilyOS insight**: POC benchmark diagnostic identified this exact problem:
  - Distractors were topically unrelated (family events vs random Wikipedia) → Recall@1=1.0
  - Proposed fix: same-domain distractors (similar family events about different family members)
  - UltraBERT negation blindness: "I love X" ≈ "I hate X" → need explicit negation-aware negatives
  - Zero variance in metrics = benchmark not discriminating = need harder test set

#### Topic 34: Deduplication
- **Exact dedup**: Hash-based (SHA-256, MD5). Fast but misses near-duplicates.
- **Near-dedup**:
  - **SimHash**: Locality-sensitive hash for cosine similarity. Compare Hamming distance of hash bits.
  - **MinHash + LSH**: Jaccard similarity approximation. Hash shingles, band-and-row LSH for candidate pairs.
  - **Embedding-based**: Cosine similarity threshold on dense vectors.
- **Why it matters**: Duplicate training data → memorization → poor generalization. Duplicate retrieval results → wasted context window.
- **FamilyOS**: K0 Module M01 `pattern_separate` implements:
  - SimHash fingerprinting for near-duplicate detection
  - MinHash LSH for scalable deduplication
  - Applied in P03 consolidation pipeline (R3 phase)
  - K0 idempotency: BLAKE3/HMAC-SHA256 keys for exact-duplicate detection at ingestion

---

### 4.3 Data Flywheels

#### Topic 35: User Interaction → Model Improvement Loops
- **Data flywheel concept**: User interactions generate data → data improves model → better model attracts users → more data. Virtuous cycle.
- **Implementation**: Log interactions (with consent) → extract training signals → filter/clean → retrain/fine-tune → deploy → measure improvement.
- **Key challenge**: Cold start (no data yet), quality filtering (most interactions are boring), privacy (PII removal).
- **FamilyOS Learning Loop**:
  - **System 1 (Gap Resolution)**: K0 detects knowledge gap → Bridge SSE → K1 Curiosity Agent → asks user → answer flows back to K0 P02. Active learning cycle.
  - **System 2 (Model Refinement)**: K1 detects behavioral signals → Feedback Envelope → Bridge → K0 P05. Passive learning from usage.
  - Storage tables: `st_learning_gaps` (attention scores), `st_signal_events` (patterns), `st_learning_feedback` (aggregation), `st_hypothesis_bank` (proposals)

#### Topic 36: Measuring Flywheel Effectiveness
- **Online metrics**: User satisfaction trends, task completion rate over time, correction rate decrease, engagement increase.
- **A/B testing**: Compare model versions with controlled traffic splits. Statistical significance (p<0.05), minimum detectable effect.
- **Offline evaluation**: Benchmark regression testing — new model must beat old on held-out test set.
- **Leading indicators**: Data volume growth, annotation throughput, time-to-deploy new model version.
- **FamilyOS**:
  - K0 feature flags: per-module A/B testing with rollout_percentage + consistent hashing
  - Auto-fallback on max_failures_before_fallback
  - 5 Grafana dashboards: kernel overview, command latency, query latency, SSE health, replay throughput
  - 18 SLO-based Prometheus alerts with warning/critical pairs
  - P50/P95/P99 latency tracking across all components

#### Topic 37: Feedback Signals
- **Implicit signals**: Click-through rate, dwell time, abandonment, reformulation, scroll depth, task completion.
- **Explicit signals**: Thumbs up/down, star ratings, text feedback, corrections.
- **Signal quality hierarchy**: Explicit > behavioral > inferred. But explicit is sparse — need to combine.
- **Conversion to training data**: Positive examples from validated responses, negative from corrections/abandonments, preference pairs from comparisons.
- **FamilyOS signal framework**:
  - Weighted behavioral signals: correction=0.85, validation=0.90, reformulate=0.65, abandonment=0.70, hedging=0.50
  - Concierge meta-intent classification detects these in real-time
  - Feedback Envelope Builder packages signals with correlation IDs
  - K0 P05 pipeline aggregates signals for model refinement
  - `st_signal_events` stores patterns, `st_hypothesis_bank` stores improvement proposals

#### Topic 38: Continuous Evaluation & Drift Detection
- **Concept drift**: P(Y|X) changes — same inputs should produce different outputs (e.g., user preferences evolve).
- **Data drift**: P(X) changes — input distribution shifts (e.g., new topics, new users, seasonal patterns).
- **Detection methods**: KL divergence on feature distributions, prediction confidence monitoring, population stability index (PSI), reference window comparison.
- **Response**: Automated retraining triggers, human review for large shifts, rollback capability.
- **FamilyOS continuous evaluation**:
  - K0 observability: 3 pillars (Prometheus metrics, OpenTelemetry tracing, structured logging)
  - SLO-driven monitoring: P50/P95/P99 per endpoint
  - Command latency P95 <150ms, Query P95 <200ms, SSE P95 <50ms
  - K0 Ward test suite: deterministic dashboard/alert verification
  - Replay throughput monitoring for regression detection
  - ML tier metrics: per-module accuracy tracking, A/B comparison
  - Auto-fallback: if UltraBERT accuracy drops → fallback to RULE_BASED tier

---

## Quick Reference: FamilyOS Architecture for Interview Answers

### When asked about system design:
> "I built a dual-kernel architecture: K0 (memory/persistence) and K1 (conversation/intelligence), connected by a Bridge with offline-aware transport. K1 is a 7-layer cognitive stack with strict invariants — 16 for orchestration, 12 for planning, 18 for model hub."

### When asked about ML serving:
> "Our Model Hub implements a 9-step request pipeline with multi-provider support (OpenAI, Anthropic, Google, vLLM, Ollama), per-provider circuit breakers, $5/day budget enforcement, 5-minute LRU cache, and priority-weighted model selection with fallback chains."

### When asked about RAG:
> "We built a 2-stage retrieval pipeline: Layer 1 uses 3-path Reciprocal Rank Fusion (IDF-weighted centroids, event-level search with weighted_max, and optional DiagMahalanobis). Layer 2 applies structural fusion across 4 axes (spatial 62%, social 33%, temporal 2.5%, affective 2.5%). Achieved MRR=0.777 on 49 human-annotated queries."

### When asked about data quality:
> "We discovered our initial benchmarks were too easy — Recall@1 hit 1.0 which is statistically impossible. Diagnostic analysis revealed distractors were topically unrelated. We proposed same-domain hard negatives. Also found UltraBERT's negation blindness (similarity 0.95 for 'I love X' vs 'I hate X') which we handle at the application layer with metadata tagging."

### When asked about data flywheels:
> "We have a dual-system learning loop: System 1 actively detects knowledge gaps and asks users to fill them (active learning). System 2 passively collects behavioral signals — corrections (weight 0.85), validations (0.90), abandonments (0.70) — and feeds them into a hypothesis bank for model refinement. Feature flags enable per-module A/B testing with auto-fallback."

### When asked about agent architecture:
> "K1 implements a strict 7-layer architecture: Concierge (user-facing FSM with 11 meta-intents) → Orchestrator (blind DAG executor, zero LLM) → Capability Fabric (6 provider types including MCP) → Planner (4-stage LLM pipeline: sketch→expand→validate→commit) → Agents (6-state lifecycle FSM, 58+ types) → SessionState (96KB 3-tier memory) → K0 Bridge."

### When asked about security:
> "Multi-layer: Ed25519 signature verification at ingestion, 10-step gate validation, 6-phase policy enforcement with privacy bands (GREEN→RED), capability-based least-privilege, SafetyWatchAgent with <5ms URGENT priority, PII detection, E2EE for sensitive data, and CRDT conflict resolution for multi-device sync."
