# P03 R4 KG Consolidation — Phase Discovery & Enhancement Plan

> **Epic 5.5 Discovery**: Full audit of the R4 Knowledge Graph Consolidation phase —
> entity extraction, disambiguation, alias detection, ambiguous resolution, confidence routing,
> adaptive merge thresholds, entity merging with cascade/undo, Hebbian co-occurrence learning,
> Granger causality inference, adaptive causality thresholds, causal edge feedback/staleness,
> subtype classification, social relationship extraction, and 9 edge enrichment algorithms
> (semantic similarity, temporal proximity, contextual, emotion similarity, intent similarity,
> transitive closure, Bayesian causal, weight normalization, fusion). Covers code, contracts,
> algorithms, data flow, storage, observability, tests, dependencies, performance, gaps,
> and enhancement proposals.

---

## 0. Discovery Metadata

| Field | Value |
| ----- | ----- |
| Pipeline ID | P03 |
| Module Scope | consolidation.entity_extractor, consolidation.entity_disambiguator, consolidation.alias_detector, consolidation.ambiguous_resolver, consolidation.confidence_router, consolidation.merge_threshold_learner, consolidation.entity_merger, consolidation.hebbian_learner, consolidation.granger_causality, consolidation.causality_thresholds, consolidation.edge_demotion, consolidation.subtype_classifier, consolidation.observation_context, consolidation.edge_enrichers.semantic_similarity, consolidation.edge_enrichers.temporal_proximity, consolidation.edge_enrichers.contextual, consolidation.edge_enrichers.emotion_similarity, consolidation.edge_enrichers.intent_similarity, consolidation.edge_enrichers.transitive_closure, consolidation.edge_enrichers.bayesian_causal, consolidation.edge_enrichers.weight_normalization, consolidation.edge_enrichers.fusion, pipelines.p03.phases.r4_kg_consolidator, pipelines.p03.phases.r4_config |
| Discovery Date | 2026-03-03 |
| Milestone Target | M5 |
| Governing ADRs | ADR-K010 (P03 consolidation architecture), ADR-K003-v2 (pgvector migration / FAISS elimination), ADR-K010.9 (capability-based security) |
| Related Dossier | `docs/pipelines/P03_consolidation_dossier_v2.md` |
| Author | copilot-claude |
| Status | DRAFT |

---

## 1. Current State Audit

### 1.1 Code Inventory

| # | File (relative path) | Lines | Status | Last Modified | Purpose |
| - | -------------------- | ----- | ------ | ------------- | ------- |
| 1 | k0/pipelines/p03/phases/r4_kg_consolidator.py | 3512 | MOD | 2026-01-20 | Orchestrates all R4 sub-steps: entity extraction, clustering, disambiguation, alias detection, confidence routing, entity processing, Hebbian relationship discovery, Granger causal inference, social extraction, edge enrichment, and envelope population |
| 2 | k0/pipelines/p03/phases/r4_config.py | 224 | NEW | 2026-01-15 | Defines EdgeEnrichmentConfig master dataclass with 9 per-algorithm sub-configs (semantic, temporal, contextual, emotion, intent, transitive, Bayesian, weight normalization, fusion) and global limits |
| 3 | k0/modules/consolidation/algorithms/entity_extractor.py | 1103 | MOD | 2026-01-10 | Implements UltraBERTEntityExtractor: NER head filtering (TRUSTED/REJECTED/VALIDATED families), label-to-KGEntityType mapping, garbage word filtering, filter_and_normalize() consolidation |
| 4 | k0/modules/consolidation/algorithms/entity_disambiguator.py | 803 | MOD | 2026-01-08 | Implements EntityDisambiguator: per-type embedding/string weight matrix, semantic opposition detection (embedding_sim > 0.90 + string_sim < 0.40 = opposition), rapidfuzz string similarity |
| 5 | k0/modules/consolidation/algorithms/alias_detector.py | 739 | MOD | 2026-01-08 | Implements AliasDetector: 4-signal scoring (string 0.25, embedding 0.30, nickname 0.25, co-occurrence 0.20), FirstNameDatabase with 80+ nickname mappings, 7 AliasType variants |
| 6 | k0/modules/consolidation/algorithms/ambiguous_resolver.py | 623 | MOD | 2026-01-08 | Implements AmbiguousEntityResolver: 5-priority context hierarchy (recency 0.35, co-occurring 0.30, location 0.20, temporal 0.10, frequency 0.05), close-race penalty, 3-tier outcome routing |
| 7 | k0/modules/consolidation/algorithms/confidence_router.py | 536 | MOD | 2026-01-08 | Implements ConfidenceRouter: AUTO (>=0.85) / FLAG (0.60-0.85) / GAP (<0.60) bands, gap emission to st_learning_queue via outbox pattern, gap batching (50/batch, TTL 24h) |
| 8 | k0/modules/consolidation/algorithms/merge_threshold_learner.py | 461 | MOD | 2026-01-03 | Implements AdaptiveMergeThresholds: per-entity-type thresholds (FAMILY_MEMBER=0.90, CONCEPT=0.65), learning from FP/FN feedback (+0.02/-0.02), clamped bounds, st_learned_weights persistence |
| 9 | k0/modules/consolidation/algorithms/entity_merger.py | 934 | MOD | 2026-01-03 | Implements EntityMerger: 6-step merge (validate, select primary, merge attrs, cascade, archive, log), cascade across 7 tables (st_kg_edges, st_hipp_events, st_epi, st_sem, st_social, st_procedural, st_vec), full undo via snapshots |
| 10 | k0/modules/consolidation/algorithms/hebbian_learner.py | 604 | MOD | 2026-01-03 | Implements HebbianLearner: Hebbian learning (learning_rate=0.1, soft saturation), anti-Hebbian decay (rate=0.15, 4 signal types), exponential decay (rate=0.01/day), 3 RelationTypes (INTERACTS_WITH, FREQUENTS, DISCUSSES) |
| 11 | k0/modules/consolidation/algorithms/granger_causality.py | 403 | MOD | 2026-01-03 | Implements GrangerCausalityInference: simplified Granger using temporal precedence ratio, CausalEdge creation with min 5 observations, 60-min temporal window, 1-min simultaneous threshold |
| 12 | k0/modules/consolidation/algorithms/causality_thresholds.py | 376 | MOD | 2026-01-03 | Implements AdaptiveCausalityThresholds + CausalCategoryClassifier: 4-tier stake-based thresholds (Health=0.85, Financial=0.80, Social=0.70, Preference=0.65), keyword-based category classification |
| 13 | k0/modules/consolidation/algorithms/edge_demotion.py | 564 | MOD | 2026-01-03 | Implements CausalEdgeFeedbackProcessor (accuracy-based boost/lower/demote) + CausalEdgeStalenessChecker (90-day archive), 4-tier accuracy thresholds (>90% boost, 70-90% maintain, 50-70% lower, <50% demote to CORRELATED) |
| 14 | k0/modules/consolidation/algorithms/subtype_classifier.py | 1218 | NEW | 2026-01-15 | Implements GAP-005 SubtypeClassifier: PatternSubtype (30 subtypes for st_sem), EntitySubtype (30 subtypes for st_kg_dom), keyword-based classification with hierarchical matching |
| 15 | k0/modules/consolidation/algorithms/observation_context.py | 365 | MOD | 2026-01-10 | Defines ObservationContext dataclass: temporal, emotional, salience, modality, physical, and social context snapshot for memory observations flowing through P03 |
| 16 | k0/modules/consolidation/algorithms/edge_enrichers/semantic_similarity.py | 314 | NEW | 2026-01-15 | Implements SemanticSimilarityEnricher (GAP-007 Epic 3.1): cosine similarity between entity embeddings, k_neighbors=10, threshold=0.75, SIMILAR_TO edges |
| 17 | k0/modules/consolidation/algorithms/edge_enrichers/temporal_proximity.py | 194 | NEW | 2026-01-15 | Implements TemporalProximityEnricher (GAP-007 Epic 3.2): exponential decay weighting within 5-min window (tau=60s), TEMPORALLY_ASSOCIATED edges |
| 18 | k0/modules/consolidation/algorithms/edge_enrichers/contextual.py | 187 | NEW | 2026-01-15 | Implements ContextualEdgeEnricher (GAP-007 Epic 3.3): weighted Jaccard over location_type, social_context, time_of_day_bucket, sentiment_label, ingress_category features, CONTEXTUALLY_RELATED edges |
| 19 | k0/modules/consolidation/algorithms/edge_enrichers/emotion_similarity.py | 214 | NEW | 2026-01-15 | Implements EmotionSimilarityEnricher (GAP-007 Epic 3.3): emotion vector similarity with arousal weighting (0.3), EMOTIONALLY_RELATED edges |
| 20 | k0/modules/consolidation/algorithms/edge_enrichers/intent_similarity.py | 253 | NEW | 2026-01-15 | Implements IntentSimilarityEnricher (GAP-007 Epic 3.3): complementary intent matching (seek_advice <-> express_feeling, etc.), INTENT_RELATED edges |
| 21 | k0/modules/consolidation/algorithms/edge_enrichers/transitive_closure.py | 197 | NEW | 2026-01-15 | Implements TransitiveClosureEnricher (GAP-007 Epic 3.4): 2-hop path inference with attenuation_factor=0.7, noisy-or confidence fusion, INFERRED_RELATED edges |
| 22 | k0/modules/consolidation/algorithms/edge_enrichers/bayesian_causal.py | 180 | NEW | 2026-01-15 | Implements BayesianCausalEnricher (GAP-007 Epic 3.5): Bayesian posterior update from temporal precedence, prior_strength=0.1, posterior_threshold=0.6, CAUSES edges |
| 23 | k0/modules/consolidation/algorithms/edge_enrichers/weight_normalization.py | 126 | NEW | 2026-01-15 | Implements EdgeWeightNormalizer (GAP-007 Epic 3.6): softmax/sum_to_one/cap strategies to prevent hub dominance, per-entity normalization |
| 24 | k0/modules/consolidation/algorithms/edge_enrichers/fusion.py | 79 | NEW | 2026-01-15 | Implements shared fusion utilities: canonical_edge_key, weighted_sum, noisy-or confidence fusion, EdgeSignal/EdgeFusionConfig dataclasses |
| 25 | tests/k0/pipelines/p03/test_r4_kg_consolidator.py | 674 | MOD | 2026-01-20 | Tests R4KGConsolidator orchestrator: full phase execution, entity extraction, disambiguation, edge discovery, causal inference, social extraction, envelope population |
| 26 | tests/k0/pipelines/p03/test_r4_entity_extractor.py | 598 | MOD | 2026-01-10 | Tests UltraBERTEntityExtractor: NER head filtering, label mapping, garbage filtering, normalization, multi-head dedup |
| 27 | tests/k0/pipelines/p03/test_r4_disambiguator.py | 519 | MOD | 2026-01-08 | Tests EntityDisambiguator: per-type weights, semantic opposition detection, merge decisions, rapidfuzz integration |
| 28 | tests/k0/pipelines/p03/test_r4_ambiguous_resolver.py | 563 | MOD | 2026-01-08 | Tests AmbiguousEntityResolver: 5-priority context hierarchy, close-race penalty, 3-tier outcome routing |
| 29 | tests/k0/pipelines/p03/test_r4_confidence_router.py | 515 | MOD | 2026-01-08 | Tests ConfidenceRouter: AUTO/FLAG/GAP band routing, gap payload generation, outbox entry creation |
| 30 | tests/k0/pipelines/p03/test_r4_merge_thresholds.py | 329 | MOD | 2026-01-03 | Tests AdaptiveMergeThresholds: per-type thresholds, feedback learning, bounds clamping, persistence |
| 31 | tests/k0/pipelines/p03/test_r4_entity_merger.py | 531 | MOD | 2026-01-03 | Tests EntityMerger: 6-step merge, 7-table cascade, undo via snapshots, archival status |
| 32 | tests/k0/pipelines/p03/test_r4_granger_causality.py | 643 | MOD | 2026-01-03 | Tests GrangerCausalityInference: temporal precedence, min observations, causal edge creation, simultaneous handling |
| 33 | tests/k0/pipelines/p03/test_r4_causality_thresholds.py | 439 | MOD | 2026-01-03 | Tests AdaptiveCausalityThresholds + CausalCategoryClassifier: 4-tier thresholds, keyword classification, learning |
| 34 | tests/k0/pipelines/p03/test_r4_edge_demotion.py | 621 | MOD | 2026-01-03 | Tests CausalEdgeFeedbackProcessor + CausalEdgeStalenessChecker: accuracy thresholds, boost/demote actions, staleness archive |
| 35 | tests/k0/pipelines/p03/test_r4_integration.py | 915 | MOD | 2026-01-20 | Tests R4 integration: end-to-end entity+edge pipeline, enrichment wiring, social extraction, causal inference flow |
| 36 | tests/k0/modules/consolidation/algorithms/edge_enrichers/test_semantic_similarity.py | 206 | NEW | 2026-01-15 | Tests SemanticSimilarityEnricher: cosine similarity, threshold filtering, new/update edge creation |
| 37 | tests/k0/modules/consolidation/algorithms/edge_enrichers/test_temporal_proximity.py | 94 | NEW | 2026-01-15 | Tests TemporalProximityEnricher: window filtering, exponential decay weighting, edge creation |
| 38 | tests/k0/modules/consolidation/algorithms/edge_enrichers/test_contextual.py | 78 | NEW | 2026-01-15 | Tests ContextualEdgeEnricher: weighted Jaccard, feature map construction, edge creation |
| 39 | tests/k0/modules/consolidation/algorithms/edge_enrichers/test_emotion_similarity.py | 61 | NEW | 2026-01-15 | Tests EmotionSimilarityEnricher: emotion vector similarity, arousal weighting |
| 40 | tests/k0/modules/consolidation/algorithms/edge_enrichers/test_intent_similarity.py | 79 | NEW | 2026-01-15 | Tests IntentSimilarityEnricher: complementary intent matching, profile construction |
| 41 | tests/k0/modules/consolidation/algorithms/edge_enrichers/test_transitive_closure.py | 130 | NEW | 2026-01-15 | Tests TransitiveClosureEnricher: 2-hop inference, attenuation, confidence fusion |
| 42 | tests/k0/modules/consolidation/algorithms/edge_enrichers/test_bayesian_causal.py | 211 | NEW | 2026-01-15 | Tests BayesianCausalEnricher: posterior update, temporal precedence, threshold filtering |
| 43 | tests/k0/modules/consolidation/algorithms/edge_enrichers/test_weight_normalization.py | 224 | NEW | 2026-01-15 | Tests EdgeWeightNormalizer: softmax, sum_to_one, cap strategies, hub dominance prevention |

### 1.2 Contract Inventory

| # | Contract File | Version | Status | Lines | Governs |
| - | ------------- | ------- | ------ | ----- | ------- |
| 1 | k0/contracts/modules/consolidation.entity_extractor.v1.yaml | v1 | active | 51 | module:consolidation.entity_extractor |
| 2 | k0/contracts/modules/consolidation.hebbian_learner.v1.yaml | v1 | active | 44 | module:consolidation.hebbian_learner |
| 3 | k0/contracts/modules/consolidation.causal_inference.v1.yaml | v1 | active | 51 | module:consolidation.causal_inference |
| 4 | k0/contracts/modules/consolidation.relationship_builder.v1.yaml | v1 | active | 58 | module:consolidation.relationship_builder |
| 5 | k0/contracts/pipelines/p03_consolidation.v1.yaml | v1 | active | 397 | pipeline:P03_CONSOLIDATION (R0-R8 stages incl. R4) |
| 6 | k0/contracts/capabilities/consolidation.v1.yaml | v1 | active | N/A | capability:consolidation (syscall ACL for all R-phases) |

### 1.3 Config Inventory

#### 1.3.1 YAML Config Keys

| Config File | Version | Key (dot-path) | Value | Type | Default | Required | Notes |
| ----------- | ------- | --------------- | ----- | ---- | ------- | -------- | ----- |
| k0/contracts/modules/consolidation.entity_extractor.v1.yaml | v1 | latency_budget_ms | N/A | int | N/A | yes | R4 entity extraction latency target |
| k0/contracts/modules/consolidation.hebbian_learner.v1.yaml | v1 | latency_budget_ms | N/A | int | N/A | yes | R4 Hebbian learning latency target |
| k0/contracts/modules/consolidation.causal_inference.v1.yaml | v1 | latency_budget_ms | N/A | int | N/A | yes | R4 Granger causality latency target |

#### 1.3.2 Environment Variables

| Variable | Type | Default | Required | Used By | Purpose |
| -------- | ---- | ------- | -------- | ------- | ------- |
| K0_DB_URL | url | NONE | yes | k0/db/engine.py (shared) | PostgreSQL connection string used by R4 for st_kg_dom, st_kg_edges, st_social, st_learning_queue, st_learned_weights, st_entity_merges, st_cooccurrence queries |

> **Note**: R4 does not read any R4-specific environment variables. All configuration comes from R4Config dataclass defaults and EdgeEnrichmentConfig sub-configs. Database connectivity is inherited from the shared K0 engine.

#### 1.3.3 Feature Flags

| Flag Name | Source | Default | Scope | Controls | Rollback Behavior |
| --------- | ------ | ------- | ----- | -------- | ----------------- |
| enable_causal_inference | R4Config | true | global | Enables GrangerCausalityInference for temporal causal edge creation | Safe -- next cycle skips causal step, edges from prior cycles persist |
| enable_adaptive_thresholds | R4Config | true | global | Enables AdaptiveCausalityThresholds per-category threshold lookup | Safe -- falls back to config.granger_precedence_threshold (0.60) |
| emit_gaps_on_low_confidence | R4Config | true | global | Enables gap emission to st_learning_queue for FLAG/GAP band entities | Safe -- entities still processed at current confidence without gap |
| enable_hebbian_adaptive_rates | R4Config | true | global | Enables HebbianLearner adaptive weight computation for edge weights | Safe -- falls back to static formula (base + increment * count) |
| enable_causality_thresholds | R4Config | true | global | Enables per-category thresholds (Health=0.85, Financial=0.80, etc.) | Safe -- uses single global threshold |
| enable_edge_feedback | R4Config | true | global | Enables CausalEdgeFeedbackProcessor for accuracy-based edge adjustments | Safe -- edges retain current confidence without feedback loop |
| enable_temporal_edges | R4Config | true | global | Enables FOLLOWS/PRECEDES edge creation below CAUSES threshold | Safe -- only CAUSES edges created |
| enable_alias_detection | R4Config | true | global | Enables AliasDetector for nickname/spelling variant merging | Safe -- clusters remain unmerged, more entities created |
| enable_entity_matching | R4Config | true | global | Enables st_kg_dom lookup for existing entity REINFORCE vs CREATE | Safe -- all entities created new (duplicates may occur) |
| edge_enrichment.*.enabled | EdgeEnrichmentConfig sub-configs | true (all) | per-algorithm | Individual enable/disable for each of 9 edge enrichment algorithms | Safe -- each enricher skipped independently, no cascade effects |

#### 1.3.4 Constants & Magic Numbers

| Constant | Location (file:line) | Value | Type | Rationale | Externalize? |
| -------- | -------------------- | ----- | ---- | --------- | ------------ |
| P03_DISAMBIGUATION_THRESHOLD | entity_disambiguator.py:17 | 0.85 | float | Minimum combined similarity for entity merge; high to avoid false merges | yes -- per-type thresholds already differ |
| P03_OPPOSITION_EMBEDDING_SIM_THRESHOLD | entity_disambiguator.py:22 | 0.90 | float | Embedding similarity above which to check for semantic opposition (antonyms) | no -- conservative intentional |
| ALIAS_DETECTION_THRESHOLD | alias_detector.py:18 | 0.70 | float | Combined alias score threshold; 0.70 allows reasonable alias detection | yes |
| NICKNAME_MATCH_SCORE | alias_detector.py:21 | 0.95 | float | Score assigned to database nickname matches (Bob=Robert); near-certain | no -- database match is authoritative |
| Signal weights (STRING/EMBEDDING/NICKNAME/CO_OCC) | alias_detector.py:24-27 | 0.25/0.30/0.25/0.20 | float | Multi-signal weighting for alias scoring; embedding slightly dominant | yes |
| AUTO_RESOLVE_THRESHOLD | ambiguous_resolver.py:16 | 0.85 | float | Above this confidence, auto-resolve without human review | yes -- matches disambiguator threshold |
| FLAG_THRESHOLD | ambiguous_resolver.py:17 | 0.60 | float | Below this, emit gap for human resolution | yes |
| RECENCY_BOOST | ambiguous_resolver.py:20 | 0.35 | float | Highest priority boost; recent entities strongly preferred | maybe -- empirical tuning needed |
| CO_OCCURRING_BOOST | ambiguous_resolver.py:21 | 0.30 | float | Entities appearing in same session get significant boost | maybe |
| STALENESS_DAYS | edge_demotion.py:49 | 90 | int | Days before edge marked stale and archived | yes -- too aggressive for seasonal patterns |
| MIN_FEEDBACK_SAMPLES | edge_demotion.py:50 | 5 | int | Minimum feedback records before confidence adjustment | no -- statistical minimum |
| ACCURACY_BOOST_THRESHOLD | edge_demotion.py:41 | 0.90 | float | Above 90% accuracy: boost edge confidence | no -- well-established threshold |
| ACCURACY_DEMOTE_THRESHOLD | edge_demotion.py:43 | 0.50 | float | Below 50% accuracy: demote edge from CAUSAL to CORRELATED | no -- coin-flip threshold |
| learning_rate | hebbian_learner.py:58 | 0.1 | float | Hebbian positive learning rate per co-occurrence | yes -- Dossier spec but may need tuning |
| anti_learning_rate | hebbian_learner.py:63 | 0.15 | float | Anti-Hebbian penalty rate; faster than positive to correct errors quickly | yes |
| prune_threshold | hebbian_learner.py:64 | 0.05 | float | Below this weight, edge marked for archive | yes |
| min_observations (Granger) | granger_causality.py:54 | 5 | int | Minimum co-occurrence observations for causal inference | yes -- new pairs always use undirected edges |
| causality_threshold | granger_causality.py:55 | 0.75 | float | Precedence ratio threshold for CAUSES edge; Dossier spec | yes |
| granger_min_observations (R4Config) | r4_kg_consolidator.py:52 | 1 | int | R4Config override: min observations for Granger (lowered from 5 for testing) | CRITICAL -- must raise for production |
| granger_precedence_threshold (R4Config) | r4_kg_consolidator.py:53 | 0.60 | float | R4Config override: precedence threshold (lowered from 0.75 for testing) | CRITICAL -- must raise for production |
| max_total_new_edges_per_cycle | r4_config.py:131 | 100 | int | Global cap on new enrichment edges per cycle | yes -- capacity planning dependent |
| max_total_updates_per_cycle | r4_config.py:132 | 500 | int | Global cap on enrichment edge updates per cycle | yes -- capacity planning dependent |
| min_entity_priority | r4_kg_consolidator.py:58 | 0.65 | float | Minimum NER confidence to accept entity extraction | yes |
| semantic similarity threshold | r4_config.py:47 | 0.75 | float | Cosine similarity threshold for SIMILAR_TO edges | yes |
| temporal window_ms | r4_config.py:65 | 300000 | int | 5-minute temporal proximity window for co-occurrence | yes |
| tau_ms | r4_config.py:66 | 60000 | int | 1-minute exponential decay constant for temporal weighting | yes |
| transitive attenuation_factor | r4_config.py:80 | 0.7 | float | Path attenuation for 2-hop transitive closure inference | no -- well-established decay |
| bayesian prior_strength | r4_config.py:89 | 0.1 | float | Weak prior for Bayesian causal inference (uninformative) | no -- standard weak prior |
| bayesian posterior_threshold | r4_config.py:91 | 0.6 | float | Posterior threshold for causal edge creation | yes |

---

## 2. API Surface Map

### 2.1 Public Entry Points

| # | Function / Method | File:Line | Signature (params -> return) | Caller(s) | Notes |
| - | ----------------- | --------- | ---------------------------- | ---------- | ----- |
| 1 | R4KGConsolidator.run() | r4_kg_consolidator.py:678 | (envelope: P03BatchEnvelope, ctx: P03RunnerContext) -> P03PhaseResult | P03Runner.execute_phase() | Main entry point; 10-step orchestration (extract, cluster, disambiguate, alias detect, resolve, confidence route, process entities, discover relationships, causal inference, social extraction, edge enrichment, populate outputs) |
| 2 | R4KGConsolidator.should_skip() | r4_kg_consolidator.py:439 | (envelope: P03BatchEnvelope) -> bool | R4KGConsolidator.run() | Skip check: no events, all KG-processed, or no content_text |
| 3 | R4KGConsolidator.idempotency_key() | r4_kg_consolidator.py:466 | (envelope: P03BatchEnvelope) -> str | P03Runner (dedup) | Returns cycle_id + space_id hash for idempotent re-execution |
| 4 | R4KGConsolidator.phase_id | r4_kg_consolidator.py:435 | property -> P03PhaseId | P03Runner | Returns P03PhaseId.R4_KG_CONSOLIDATION |
| 5 | UltraBERTEntityExtractor.filter_and_normalize() | entity_extractor.py:481 | (raw_entities: List[dict], source_text: str, source_head: str, min_confidence: float) -> List[ExtractedEntity] | r4_kg_consolidator._extract_entities() | Consolidated entity filtering/normalization from EFC-004 |
| 6 | UltraBERTEntityExtractor.extract_from_ultrabert() | entity_extractor.py:670 | (result: UltraBERTResult) -> List[ExtractedEntity] | Direct extraction path | Extract entities from UltraBERT result object |
| 7 | UltraBERTEntityExtractor.extract_from_full_result() | entity_extractor.py:735 | (full_result: dict) -> List[ExtractedEntity] | Alternate extraction path | Extract from raw dict-style UltraBERT output |
| 8 | UltraBERTEntityExtractor.normalize_name() | entity_extractor.py:1118 | (name: str) -> str | filter_and_normalize() internal | Possessive strip, whitespace collapse, nickname-to-canonical normalization |
| 9 | EntityDisambiguator.compute_similarity() | entity_disambiguator.py:644 | (entity_a: ExtractedEntity, entity_b: ExtractedEntity, entity_type: str) -> DisambiguationBreakdown | r4_kg_consolidator._resolve_entities() | Per-type weighted embedding + string similarity with opposition detection |
| 10 | EntityDisambiguator.fuzzy_string_match() | entity_disambiguator.py:722 | (name_a: str, name_b: str) -> float | compute_similarity() | rapidfuzz token_sort_ratio + partial_ratio fusion |
| 11 | EntityDisambiguator.should_merge() | entity_disambiguator.py:798 | (breakdown: DisambiguationBreakdown) -> bool | r4_kg_consolidator._resolve_entities() | Combined score >= threshold (default 0.85) check |
| 12 | EntityDisambiguator.load_from_database() | entity_disambiguator.py:880 | (db_conn: AsyncDBConnection) -> None | _initialize_components() | Loads learned per-type weights from st_learned_weights |
| 13 | SemanticOppositionDetector.detect_opposition() | entity_disambiguator.py:259 | (embedding_sim: float, string_sim: float) -> OppositionAnalysis | compute_similarity() | Detects semantic opposition: embedding_sim > 0.90 AND string_sim < 0.40 |
| 14 | AliasDetector.detect() | alias_detector.py:644 | (entities: List[EntityInfo]) -> List[AliasCandidate] | r4_kg_consolidator._detect_aliases() | Multi-signal alias detection (string, embedding, nickname, co-occurrence) |
| 15 | AliasScorer.compute_combined_score() | alias_detector.py:582 | (entity_a: EntityInfo, entity_b: EntityInfo) -> AliasCandidate | AliasDetector._evaluate_pair() | 4-signal weighted scoring (str=0.25, emb=0.30, nick=0.25, co_occ=0.20) |
| 16 | AliasScorer.compute_string_similarity() | alias_detector.py:469 | (name_a: str, name_b: str) -> float | compute_combined_score() | Levenshtein + token_sort_ratio fusion |
| 17 | AliasScorer.compute_embedding_similarity() | alias_detector.py:496 | (emb_a: List[float], emb_b: List[float]) -> float | compute_combined_score() | Cosine similarity between entity embeddings |
| 18 | AliasScorer.check_nickname_match() | alias_detector.py:527 | (name_a: str, name_b: str) -> float | compute_combined_score() | FirstNameDatabase lookup (80+ mappings); returns 0.95 on match |
| 19 | AliasScorer.compute_co_occurrence_score() | alias_detector.py:545 | (entity_a: EntityInfo, entity_b: EntityInfo) -> float | compute_combined_score() | Session-based co-occurrence overlap score |
| 20 | FirstNameDatabase.are_aliases() | alias_detector.py:227 | (name_a: str, name_b: str) -> bool | check_nickname_match() | 80+ nickname mappings (Bob=Robert, Mom=Mother, etc.) |
| 21 | FamilyRoleDatabase.are_aliases() | alias_detector.py:329 | (name_a: str, name_b: str) -> bool | check_nickname_match() | Family role alias mappings (Mom/Mother/Mama, Dad/Father/Papa) |
| 22 | AmbiguousEntityResolver.resolve() | ambiguous_resolver.py:414 | (mention: str, candidates: List[CandidateEntity], event_context: EventContext) -> ResolutionResult | r4_kg_consolidator._resolve_entities() | 5-priority context hierarchy resolution with close-race penalty |
| 23 | AmbiguousEntityResolver._score_candidate() | ambiguous_resolver.py:530 | (candidate: CandidateEntity, event_context: EventContext) -> ResolutionBreakdown | resolve() | Computes 5-priority weighted score per candidate |
| 24 | AmbiguousEntityResolver.emit_gap_to_p06() | ambiguous_resolver.py:642 | (mention: str, candidates: List[CandidateEntity], context: EventContext) -> GapPayload | resolve() on GAP outcome | Creates st_learning_queue entry for P06 resolution |
| 25 | ConfidenceRouter.route() | confidence_router.py:381 | (entity_id: str, confidence: float, candidates: List[str]) -> RoutingResult | r4_kg_consolidator._resolve_entities() | AUTO/FLAG/GAP band classification + gap payload generation |
| 26 | ConfidenceRouter.determine_band() | confidence_router.py:464 | (confidence: float) -> ConfidenceBand | route() | AUTO>=0.85, FLAG>=0.60, GAP<0.60 |
| 27 | ConfidenceRouter.emit_gap() | confidence_router.py:481 | (entity_id: str, gap_type: GapType, context: dict) -> OutboxEntry | route() on GAP band | Creates outbox entry for st_learning_queue write |
| 28 | ConfidenceRouter.emit_batch() | confidence_router.py:571 | (entries: List[OutboxEntry]) -> int | r4_kg_consolidator on cycle end | Batch gap emission (50/batch, TTL 24h) |
| 29 | AdaptiveMergeThresholds.should_merge() | merge_threshold_learner.py:315 | (entity_type: str, similarity: float) -> MergeDecision | r4_kg_consolidator._process_entity_clusters() | Per-type threshold comparison with learning bounds |
| 30 | AdaptiveMergeThresholds.get_threshold() | merge_threshold_learner.py:285 | (entity_type: str) -> float | should_merge() | Returns learned or default threshold for entity type |
| 31 | AdaptiveMergeThresholds.adjust_threshold() | merge_threshold_learner.py:363 | (entity_type: str, signal: str) -> ThresholdAdjustment | P06 feedback loop | FP=+0.02, FN=-0.02 adjustment with clamping |
| 32 | AdaptiveMergeThresholds.persist_threshold() | merge_threshold_learner.py:424 | (entity_type: str, db_conn: AsyncDBConnection) -> None | adjust_threshold() | Writes to st_learned_weights |
| 33 | AdaptiveMergeThresholds.load_from_database() | merge_threshold_learner.py:503 | (db_conn: AsyncDBConnection) -> None | _initialize_components() | Loads learned thresholds from st_learned_weights |
| 34 | EntityMerger.merge_entities() | entity_merger.py:358 | (primary: EntitySnapshot, secondary: EntitySnapshot, conn: AsyncDBConnection) -> MergeResult | Future P06 gap resolution | 6-step atomic merge with 7-table cascade and undo snapshot |
| 35 | EntityMerger._validate_merge() | entity_merger.py:491 | (primary: EntitySnapshot, secondary: EntitySnapshot) -> None | merge_entities() | Pre-merge validation: same type, not already merged, different IDs |
| 36 | EntityMerger._select_primary() | entity_merger.py:545 | (a: EntitySnapshot, b: EntitySnapshot) -> Tuple[EntitySnapshot, EntitySnapshot] | merge_entities() | Higher observation_count wins; tie-break by first_mentioned |
| 37 | EntityMerger._merge_attributes() | entity_merger.py:590 | (primary: EntitySnapshot, secondary: EntitySnapshot) -> dict | merge_entities() | Merge aliases, combine observation_counts, keep higher confidence |
| 38 | EntityMerger._cascade_update_references() | entity_merger.py:628 | (primary_id: str, secondary_id: str, conn: AsyncDBConnection) -> CascadeCounts | merge_entities() | Updates references across 7 tables (st_kg_edges, st_hipp_events, st_epi, st_sem, st_social, st_procedural, st_vec) |
| 39 | EntityMerger.reverse_merge() | entity_merger.py:831 | (merge_id: str, conn: AsyncDBConnection) -> MergeResult | P06 undo path | Full undo via stored snapshots |
| 40 | EntityMerger.get_merge_history() | entity_merger.py:1040 | (entity_id: str, conn: AsyncDBConnection) -> List[MergeResult] | P06 audit | Retrieves merge chain for entity |
| 41 | HebbianLearner.compute_initial_weight() | hebbian_learner.py:478 | (importance: float) -> float | r4_kg_consolidator._discover_relationships() | Initial edge weight = base_weight + learning_rate * importance |
| 42 | HebbianLearner.update_edge_weight() | hebbian_learner.py:430 | (current_weight: float, current_count: int, event_importance: float) -> Tuple[float, int] | r4_kg_consolidator._discover_relationships() | Adaptive Hebbian: w_new = w_old + lr *(1 - w_old)* importance; soft saturation |
| 43 | HebbianLearner.extract_cooccurrences() | hebbian_learner.py:344 | (entities: List[ParsedEntity], event_id: str) -> List[CoOccurrence] | r4_kg_consolidator._discover_relationships() | Generates all pairwise co-occurrences within event |
| 44 | HebbianLearner.apply_decay() | hebbian_learner.py:497 | (weight: float, days_since_last: float) -> float | r4_kg_consolidator._discover_relationships() | Exponential decay: w *exp(-decay_rate* days); prune below 0.05 |
| 45 | HebbianLearner.apply_anti_decay() | hebbian_learner.py:554 | (weight: float, signal: AntiHebbianSignal) -> float | Future P06 feedback | Anti-Hebbian penalty: w - anti_rate * correction_multiplier; 4 signal types |
| 46 | HebbianLearner.process_batch() | hebbian_learner.py:639 | (batch: List[CoOccurrence]) -> List[EdgeUpdate] | Batch processing path | Process multiple co-occurrences in single pass |
| 47 | GrangerCausalityInference.compute_temporal_precedence() | granger_causality.py:223 | (entity_a: str, entity_b: str, observations: List[Tuple[int,int]]) -> TemporalPrecedenceStats | r4_kg_consolidator._infer_causal_relationships() | Precedence ratio = a_before_b / (a_before_b + b_before_a); simultaneous if |delta| < 1min |
| 48 | GrangerCausalityInference.infer_causal_direction() | granger_causality.py:284 | (stats: TemporalPrecedenceStats, threshold: float) -> Optional[CausalEdge] | _infer_causal_relationships() | CAUSES if ratio >= threshold; None if insufficient observations |
| 49 | GrangerCausalityInference.analyze_cooccurrence_pairs() | granger_causality.py:359 | (pairs: List[Tuple[str,str]], observations: Dict) -> List[CausalEdge] | Batch analysis path | Analyzes multiple entity pairs in single pass |
| 50 | GrangerCausalityInference.persist_causal_edges() | granger_causality.py:406 | (edges: List[CausalEdge], conn: AsyncDBConnection) -> int | Future persistence path | Writes causal edges to st_kg_edges |
| 51 | CausalCategoryClassifier.classify() | causality_thresholds.py:191 | (source_name: str, target_name: str, rel_type: str) -> CausalityCategory | r4_kg_consolidator._infer_causal_relationships() | Keyword-based: Health (medical, doctor, exercise), Financial (salary, budget, payment), Social (family, friend, call), Preference (default) |
| 52 | AdaptiveCausalityThresholds.get_threshold() | causality_thresholds.py:286 | (category: CausalityCategory) -> float | r4_kg_consolidator._infer_causal_relationships() | Health=0.85, Financial=0.80, Social=0.70, Preference=0.65 |
| 53 | AdaptiveCausalityThresholds.should_create_causal_edge() | causality_thresholds.py:307 | (category: CausalityCategory, precedence_ratio: float) -> bool | _infer_causal_relationships() | ratio >= get_threshold(category) |
| 54 | AdaptiveCausalityThresholds.adjust_threshold() | causality_thresholds.py:356 | (category: CausalityCategory, signal: str) -> float | P06 feedback | wrong_prediction=+0.02, user_rejects=+0.03, missed_causation=-0.02 |
| 55 | AdaptiveCausalityThresholds.load_from_database() | causality_thresholds.py:430 | (db_conn: AsyncDBConnection) -> None | _initialize_components() | Loads learned per-category thresholds |
| 56 | CausalEdgeFeedbackProcessor.process_feedback() | edge_demotion.py:229 | (edge_id: str, db_conn: DatabaseConnection) -> DemotionResult | Future P06 feedback loop | Accuracy-based: >90% boost +0.05, 70-90% maintain, 50-70% lower -0.10, <50% demote to CORRELATED |
| 57 | CausalEdgeFeedbackProcessor.compute_accuracy() | edge_demotion.py:310 | (edge_id: str, db_conn: DatabaseConnection) -> float | process_feedback() | correct_predictions / total_feedback_count |
| 58 | CausalEdgeStalenessChecker.check_staleness() | edge_demotion.py:546 | (edge_id: str, db_conn: DatabaseConnection) -> DemotionResult | Future P06 maintenance | 90-day staleness archive for unused edges |
| 59 | CausalEdgeStalenessChecker.archive_stale_edges() | edge_demotion.py:576 | (db_conn: DatabaseConnection) -> int | Batch maintenance | Archives all edges not seen in 90 days |
| 60 | SubtypeClassifier.classify_pattern() | subtype_classifier.py:1287 | (input: PatternClassificationInput) -> Optional[str] | R4 semantic pattern classification | GAP-005: 30 pattern subtypes via keyword matching |
| 61 | SubtypeClassifier.classify_entity() | subtype_classifier.py:1314 | (input: EntityClassificationInput) -> Optional[str] | r4_kg_consolidator._build_entity_clusters() | GAP-005: 30 entity subtypes via keyword + type hierarchical matching |
| 62 | PatternSubtypeClassifier.classify() | subtype_classifier.py:967 | (input: PatternClassificationInput) -> Optional[str] | SubtypeClassifier.classify_pattern() | Keyword database lookup for pattern subtypes |
| 63 | EntitySubtypeClassifier.classify() | subtype_classifier.py:1134 | (input: EntityClassificationInput) -> Optional[str] | SubtypeClassifier.classify_entity() | Keyword database lookup for entity subtypes |
| 64 | ObservationContext.from_event() | observation_context.py:142 | (event: P03EventState, entity_id: str) -> ObservationContext | r4_kg_consolidator._build_entity_context_map() | Creates context snapshot from event fields |
| 65 | ObservationContext.from_timestamp() | observation_context.py:198 | (timestamp_ms: int) -> ObservationContext | Lightweight construction | Creates minimal context with just timestamp |
| 66 | ObservationContext.to_dict() | observation_context.py:268 | () -> Dict[str, Any] | Serialization | Full dict representation of context snapshot |
| 67 | ObservationContext.to_db_row() | observation_context.py:277 | () -> Dict[str, Any] | DB persistence | DB-compatible dict representation |
| 68 | SemanticSimilarityEnricher.enrich() | edge_enrichers/semantic_similarity.py:~120 | (entities, entity_contexts, existing_edges, tenant_id, space_id) -> Tuple[List[KGEdge], List[KGEdgeUpdate]] | r4_kg_consolidator.run() | Cosine similarity between entity embeddings -> SIMILAR_TO edges |
| 69 | TemporalProximityEnricher.enrich() | edge_enrichers/temporal_proximity.py:~80 | (entity_contexts, existing_edges) -> Tuple[List[KGEdge], List[KGEdgeUpdate]] | r4_kg_consolidator.run() | Temporal co-occurrence within 5-min window -> TEMPORALLY_ASSOCIATED edges |
| 70 | ContextualEdgeEnricher.enrich() | edge_enrichers/contextual.py:~70 | (entity_contexts, existing_edges) -> Tuple[List[KGEdge], List[KGEdgeUpdate]] | r4_kg_consolidator.run() | Weighted Jaccard over context features -> CONTEXTUALLY_RELATED edges |
| 71 | EmotionSimilarityEnricher.enrich() | edge_enrichers/emotion_similarity.py:~80 | (entity_contexts, existing_edges) -> Tuple[List[KGEdge], List[KGEdgeUpdate]] | r4_kg_consolidator.run() | Emotion vector similarity -> EMOTIONALLY_RELATED edges |
| 72 | IntentSimilarityEnricher.enrich() | edge_enrichers/intent_similarity.py:~90 | (entity_contexts, existing_edges) -> Tuple[List[KGEdge], List[KGEdgeUpdate]] | r4_kg_consolidator.run() | Complementary intent matching -> INTENT_RELATED edges |
| 73 | TransitiveClosureEnricher.enrich() | edge_enrichers/transitive_closure.py:~80 | (batch_entities, existing_edges) -> Tuple[List[KGEdge], List[KGEdgeUpdate]] | r4_kg_consolidator.run() | 2-hop path inference with attenuation -> INFERRED_RELATED edges |
| 74 | BayesianCausalEnricher.enrich() | edge_enrichers/bayesian_causal.py:~70 | (entity_contexts, existing_edges) -> Tuple[List[KGEdge], List[KGEdgeUpdate]] | r4_kg_consolidator.run() | Bayesian posterior from temporal precedence -> CAUSES edges |
| 75 | EdgeWeightNormalizer.normalize() | edge_enrichers/weight_normalization.py:~50 | (new_edges, updates, existing_edges) -> List[KGEdgeUpdate] | r4_kg_consolidator.run() | Per-entity softmax/sum_to_one/cap normalization to prevent hub dominance |
| 76 | create_r4_phase() | r4_kg_consolidator.py:3501 | (config: Optional[R4Config]) -> R4KGConsolidator | P03Runner | Factory function |

**Total Public API Surface: 76 methods across 24 files**

### 2.2 Internal Methods (Phase Wrapper — r4_kg_consolidator.py)

| # | Method | Line | Purpose | Key Logic |
| - | ------ | ---- | ------- | --------- |
| 1 | _initialize_components() | 478 | Lazy-init all 20+ algorithm components | Reads ctx.syscalls; creates extractor, disambiguator, resolver, router, thresholds, merger, alias, hebbian, granger, category classifier, causality thresholds, feedback processor, staleness checker, + 8 edge enrichers |
| 2 | _load_resolved_gaps() | 611 | Load resolved gaps from st_learning_queue | Queries RESOLVED status entries via get_pool(); caches entity_id -> resolved_value for canonical name override |
| 3 | _extract_entities() | 1099 | Extract entities from NER JSON | Parses ner_entities_json per head; family-span dedup (ner_family takes priority over ner_general for overlapping spans); calls filter_and_normalize(); returns (all_entities, event_entity_map, event_relations_map) |
| 4 | _build_entity_clusters() | 1338 | Group entities into clusters | Groups by type:normalized_name; selects canonical name (frequency + proper case + longest); applies resolved gap override; classifies entity_subtype via GAP-005; computes temporal fields |
| 5 | _select_canonical_name() | 1302 | Select best canonical name for cluster | Scoring: frequency (most common) > proper case > longest variant; resolved gap override takes priority |
| 6 | _detect_aliases() | 1461 | Detect and merge alias clusters (GAP-004) | Calls AliasDetector.detect(); merges secondary into primary cluster; updates mentions, event_ids, confidence |
| 7 | _resolve_entities() | 1589 | Multi-signal disambiguation | Queries st_kg_dom for fuzzy candidates; calls AmbiguousEntityResolver; routes via 3-tier outcome (AUTO/FLAG/GAP); emits gaps for low confidence |
| 8 | _process_entity_clusters() | 1823 | Create/update KG entities | Queries existing entities; REINFORCE (UPDATE) if exists, CREATE if new; uses AdaptiveMergeThresholds for merge decisions |
| 9 | _discover_relationships() | 1936 | Hebbian co-occurrence edges | Loads existing edges from st_kg_edges; counts co-occurrences per event; uses HebbianLearner for adaptive weights; infers edge type from UltraBERT relations (M10.3); UPDATE existing or CREATE new edges |
| 10 | _generate_synthetic_causes_edges() | 2158 | Generate synthetic CAUSES from high co-occurrence | observation_count >= 3, confidence >= 0.5, 10% penalty applied to distinguish from Granger-derived edges |
| 11 | _infer_causal_relationships() | 2200 | Granger causality inference | Builds timestamp pairs from cluster observations; computes precedence ratio via GrangerCausalityInference; applies per-category thresholds; creates CAUSES/FOLLOWS/PRECEDES edges |
| 12 | _infer_edge_type_from_relations() | 2504 | UltraBERT relation to KG edge type | ULTRABERT_TO_TYPE priority map: FAMILY=4 > FRIEND=3 > COLLEAGUE=2 > ACQUAINTANCE=1; highest priority wins |
| 13 | _infer_edge_subtype_from_relations() | 2547 | UltraBERT relation to KG edge subtype | ULTRABERT_TO_SUBTYPE mapping: parent_of -> PARENT, spouse_of -> SPOUSE, etc. |
| 14 | _max_event_timestamp() | 2577 | Get latest timestamp from cluster observations | Returns max timestamp_ms across all event_ids in cluster; used for edge last_observed_at |
| 15 | _extract_social_relationships() | 2588 | Social relationship extraction | Parses UltraBERT relations, sentiment, emotions per event; aggregates by (self, participant) pair; derives relationship_type/subtype from UltraBERT (primary) or context (fallback); computes emotional_valence, dominant_emotion, emotional_role, relationship_phase |
| 16 | _derive_relationship_type() | 2918 | Derive social relationship type | ULTRABERT_TO_TYPE priority (FAMILY > FRIEND > COLLEAGUE > ACQUAINTANCE); social_context fallback |
| 17 | _derive_relationship_subtype() | 2975 | Derive social relationship subtype | ULTRABERT_TO_SUBTYPE (12 subtypes); kinship name inference; social_context fallback |
| 18 | _infer_emotional_role() | 3027 | Infer emotional role in relationship | ROLE_EMOTIONS mapping: 6 roles (SUPPORTER, DEPENDENT, MUTUAL_SUPPORT, ANTAGONIST, NEUTRAL, CARETAKER) from emotion distribution |
| 19 | _infer_relationship_phase() | 3051 | Infer relationship lifecycle phase | interaction_count <= 2 -> FORMING; trend > 0.2 -> DEEPENING; trend < -0.2 -> COOLING; else STABLE |
| 20 | _infer_modalities() | 3083 | Infer communication modalities | Derives from social_context and activity_type: in_person, phone, text, video, etc. |
| 21 | _infer_relationship_subtype() | 3112 | Refined subtype inference | Context-based refinement of relationship subtype from social signals |
| 22 | _populate_phase_outputs() | 3147 | Write outputs to envelope | Converts KGUpdate/CausalEdge/SocialRelationship to envelope.phases.r4_* lists; emits decision metrics (CREATE/REINFORCE) via metrics_registry |
| 23 | _build_enrichment_entities() | 3326 | Convert KGUpdates to KGEntity list | Transforms CREATE/UPDATE entity updates into KGEntity objects for enricher consumption |
| 24 | _build_entity_context_map() | 1279 | Map clusters to ObservationContext | Epic 2.3: creates entity_id -> List[ObservationContext] for enrichment algorithms |
| 25 | _update_episode_entity_ids() | 3360 | Align episode entity_ids with KG | Replaces raw entity names in R2 episodes with resolved cluster IDs (cluster_PERSON_emma) for CPN matching |
| 26 | _emit_canonical_name_updates() | 3446 | Update canonical names from resolved gaps | Emits UPDATE operations for resolved gaps not in current cycle so st_kg_dom.canonical_name gets updated via R7 |
| 27 | _get_skip_reason() | 1084 | Determine skip reason for logging | Returns descriptive string: "no events", "all KG-processed", "no content_text" |

**Total Internal Methods: 27 methods in r4_kg_consolidator.py (3512 lines)**

### 2.3 Data Classes (r4_kg_consolidator.py)

| # | Class | Line | Fields | Purpose |
| - | ----- | ---- | ------ | ------- |
| 1 | R4Config | 120 | 15+ dataclass fields (granger_min_observations, granger_precedence_threshold, min_entity_priority, enable_causal_inference, enable_adaptive_thresholds, emit_gaps_on_low_confidence, enable_hebbian_adaptive_rates, enable_causality_thresholds, enable_edge_feedback, enable_temporal_edges, enable_alias_detection, enable_entity_matching, temporal_follows_threshold, temporal_precedes_threshold, edge_enrichment) | Phase configuration with feature flags and thresholds |
| 2 | R4PhaseStats | 183 | 50+ fields across 12 categories | Comprehensive phase execution statistics; to_dict() at line 255 |
| 3 | KGUpdateType | 294 | CREATE_ENTITY, UPDATE_ENTITY, CREATE_EDGE, UPDATE_EDGE (Enum) | Classifies entity/edge CRUD operations |
| 4 | KGUpdate | 304 | update_type, entity_id, data, kg_type, edge_id, source_entity_id, target_entity_id | Generic CRUD operation container for entities and edges |
| 5 | EntityCluster | 339 | cluster_id, entity_type, canonical_name, mentions, event_ids, observation_ids, confidence, entity_subtype, first_mentioned, last_observed, resolved_entity_id | Represents a grouped entity with all mentions and metadata |

### 2.4 Data Classes (Algorithm Files)

| # | Class | File:Line | Fields | Purpose |
| - | ----- | --------- | ------ | ------- |
| 1 | KGEntityType | entity_extractor.py:57 | FAMILY_MEMBER, PERSON, CONCEPT, PLACE, LOCATION, ORGANIZATION, EVENT, TEMPORAL, THING (Enum) | Entity type taxonomy |
| 2 | UltraBERTEntity | entity_extractor.py:75 | text, label, score, start, end, source_head | Raw NER entity from UltraBERT output |
| 3 | ExtractedEntity | entity_extractor.py:94 | entity_id, text, normalized_text, kg_type, priority, source_head, span_start, span_end | Normalized entity ready for clustering |
| 4 | EntityExtractionMetrics | entity_extractor.py:127 | by_source_head, by_kg_type, duplicates_removed, total_extracted, processing_time_ms | Extraction statistics |
| 5 | OppositionAnalysis | entity_disambiguator.py:101 | is_opposition, embedding_sim, string_sim, explanation | Semantic opposition detection result |
| 6 | DisambiguationWeights | entity_disambiguator.py:126 | embedding_weight, string_weight (frozen dataclass, must sum to 1.0) | Per-type weight pair |
| 7 | DisambiguationBreakdown | entity_disambiguator.py:156 | entity_a, entity_b, embedding_sim, string_sim, combined_score, weights, opposition, should_merge | Full disambiguation decision audit |
| 8 | DisambiguationMetrics | entity_disambiguator.py:185 | total_comparisons, merges, rejections, oppositions_detected, algorithm_wins | Disambiguation statistics |
| 9 | AliasType | alias_detector.py:80 | NICKNAME, SPELLING_VARIANT, ABBREVIATION, FAMILY_ROLE, CULTURAL, PHONETIC, UNKNOWN (Enum) | 7 alias classification types |
| 10 | FirstNameDatabase | alias_detector.py:97 | _aliases: Dict (80+ nickname mappings: Bob=Robert, Mom=Mother, etc.) | English nickname database |
| 11 | FamilyRoleDatabase | alias_detector.py:280 | _aliases: Dict (family role mappings: Mom/Mother/Mama, Dad/Father/Papa) | Family-specific role aliases |
| 12 | AliasCandidate | alias_detector.py:355 | entity_a, entity_b, combined_score, string_score, embedding_score, nickname_score, co_occurrence_score, alias_type | Full alias detection audit |
| 13 | EntityInfo | alias_detector.py:409 | entity_id, name, embedding, event_ids, entity_type | Input entity for alias detection |
| 14 | AliasDetectionMetrics | alias_detector.py:430 | pairs_compared, candidates_found, nickname_matches, total_duration_ms | Alias detection statistics |
| 15 | ResolutionOutcome | ambiguous_resolver.py:77 | AUTO_RESOLVED, RESOLVED_FLAGGED, GAP_EMITTED (Enum) | 3-tier resolution outcome |
| 16 | CandidateEntity | ambiguous_resolver.py:97 | entity_id, canonical_name, entity_type, confidence, last_seen_ms, session_ids, location_names, observation_count | Disambiguation candidate |
| 17 | EventContext | ambiguous_resolver.py:133 | event_id, session_id, timestamp_ms, location_name, co_occurring_entities, actor_id | Current event context for scoring |
| 18 | ResolutionBreakdown | ambiguous_resolver.py:168 | candidate_id, base_score, recency_boost, co_occurring_boost, location_boost, temporal_boost, frequency_boost, total_score | Per-candidate scoring audit |
| 19 | ResolutionResult | ambiguous_resolver.py:216 | mention, outcome, resolved_entity_id, confidence, breakdown, gap_payload | Final resolution decision |
| 20 | ResolutionMetrics | ambiguous_resolver.py:251 | total_resolutions, auto_resolved, flagged, gaps_emitted, boost_usage | Resolution statistics |
| 21 | ConfidenceBand | confidence_router.py:70 | AUTO, FLAG, GAP (Enum) | 3-band confidence classification |
| 22 | GapType | confidence_router.py:84 | AMBIGUOUS_ENTITY, ENTITY_FLAGGED, LOW_CONFIDENCE (Enum) | Gap classification for P06 |
| 23 | GapPayload | confidence_router.py:106 | gap_id, gap_type, entity_id, mention, candidates, context_json, priority, ttl_hours | P06 gap payload |
| 24 | OutboxEntry | confidence_router.py:158 | entry_id, table_name, payload_json, status, created_at, ttl_ms | Outbox pattern entry for gap emission |
| 25 | RoutingResult | confidence_router.py:193 | entity_id, band, confidence, gap_payload | Routing decision container |
| 26 | RouterMetrics | confidence_router.py:224 | total_routed, by_band, avg_confidence, gap_count | Routing statistics |
| 27 | ThresholdBounds | merge_threshold_learner.py:65 | min_threshold, max_threshold, default_threshold | Per-type threshold constraints |
| 28 | ThresholdAdjustment | merge_threshold_learner.py:84 | entity_type, old_threshold, new_threshold, signal, clamped | Adjustment audit record |
| 29 | MergeDecision | merge_threshold_learner.py:113 | should_merge, entity_type, similarity, threshold, margin | Merge decision container |
| 30 | ThresholdMetrics | merge_threshold_learner.py:139 | decisions_made, merges_approved, merges_rejected, adjustments | Threshold learning statistics |
| 31 | MergeStatus | entity_merger.py:74 | PENDING, COMPLETED, REVERSED, FAILED (Enum) | Merge lifecycle state |
| 32 | ArchivalStatus | entity_merger.py:83 | ACTIVE, ARCHIVED, MERGED (Enum) | Entity archival state |
| 33 | EntitySnapshot | entity_merger.py:98 | entity_id, canonical_name, entity_type, aliases_json, observation_count, confidence, metadata | Pre-merge snapshot for undo |
| 34 | CascadeCounts | entity_merger.py:144 | edges_updated, events_updated, episodes_updated, semantic_updated, social_updated, procedural_updated, vec_updated | 7-table cascade statistics |
| 35 | MergeResult | entity_merger.py:203 | merge_id, primary_id, secondary_id, status, cascade_counts, primary_snapshot, secondary_snapshot, merged_at | Complete merge audit record |
| 36 | MergerMetrics | entity_merger.py:235 | merges_completed, merges_reversed, cascade_total, by_table | Merger statistics |
| 37 | HebbianConfig | hebbian_learner.py:41 | learning_rate, anti_learning_rate, decay_rate, prune_threshold, max_weight, base_weight | Hebbian learning hyperparameters |
| 38 | RelationType | hebbian_learner.py:87 | INTERACTS_WITH, FREQUENTS, DISCUSSES (Enum) | 3 co-occurrence relationship types |
| 39 | AntiHebbianSignal | hebbian_learner.py:102 | MERGE_REJECTED, WRONG, EXCLUSION, CONTRADICTION (Enum) | 4 anti-Hebbian signal types |
| 40 | KGEdge | hebbian_learner.py:129 | edge_id, source_entity_id, target_entity_id, relation_type, weight, confidence, observation_count | Edge data structure |
| 41 | EdgeUpdate | hebbian_learner.py:156 | edge_id, old_weight, new_weight, old_count, new_count, decay_applied | Edge update audit record |
| 42 | CoOccurrence | hebbian_learner.py:178 | entity_a_id, entity_b_id, event_id, importance | Pairwise co-occurrence observation |
| 43 | ParsedEntity | hebbian_learner.py:228 | entity_id, entity_type, canonical_name, event_id | Simplified entity for Hebbian processing |
| 44 | CausalityConfig | granger_causality.py:43 | min_observations, causality_threshold, temporal_window_ms, simultaneous_threshold_ms | Granger inference parameters |
| 45 | CausalEdge | granger_causality.py:83 | edge_id, source_entity_id, target_entity_id, relation_type, confidence, category, precedence_ratio | Causal edge with statistical evidence |
| 46 | TemporalPrecedenceStats | granger_causality.py:99 | a_before_b, b_before_a, simultaneous, total, ratio, direction | Temporal precedence statistics |
| 47 | CausalityCategory | causality_thresholds.py:38 | HEALTH, FINANCIAL, SOCIAL, PREFERENCE (Enum) | 4-tier stake-based categories |
| 48 | CategoryThresholdBounds | causality_thresholds.py:48 | min_threshold, max_threshold, default_threshold, category | Per-category threshold constraints |
| 49 | EdgeStatus | edge_demotion.py:62 | ACTIVE, DEMOTED, ARCHIVED, CORRELATED (Enum) | Edge lifecycle state |
| 50 | DemotionAction | edge_demotion.py:71 | BOOST, MAINTAIN, LOWER, DEMOTE, ARCHIVE (Enum) | Feedback-driven action types |
| 51 | DemotionResult | edge_demotion.py:87 | edge_id, action, old_confidence, new_confidence, old_status, new_status | Feedback processing audit |
| 52 | FeedbackRecord | edge_demotion.py:106 | feedback_id, edge_id, is_correct, feedback_source, created_at | Individual feedback entry |
| 53 | PatternSubtype | subtype_classifier.py:40 | 30 enum values for semantic pattern subtypes (DAILY_ROUTINE, FAMILY_INTERACTION, HEALTH_UPDATE, etc.) | Pattern classification taxonomy |
| 54 | EntitySubtype | subtype_classifier.py:117 | 30 enum values for entity subtypes (SPOUSE, PARENT, CHILD, SIBLING, GRANDPARENT, etc.) | Entity classification taxonomy |
| 55 | KeywordDatabase | subtype_classifier.py:191 | _keywords: Dict[str, List[str]] (keyword -> subtype mappings) | Hierarchical keyword lookup database |
| 56 | ObservationContext | observation_context.py:33 | observed_at, event_id, entity_id, temporal fields (time_of_day_bucket, day_of_week), emotional fields (dominant_emotions_json, affect_arousal, sentiment_label), salience fields, modality fields, physical fields (location_type, location_name), social fields (social_context, intent) | Full observation context snapshot |

---

## 3. Algorithm Inventory

### 3.1 Entity Resolution Pipeline

| Step | Algorithm | Class (File:Line) | Complexity | Key Parameters | Output |
| ---- | --------- | ------------------ | ---------- | -------------- | ------ |
| 1 | NER Extraction | UltraBERTEntityExtractor (entity_extractor.py:138) | O(e) per event | min_confidence=0.65, TRUSTED/REJECTED/VALIDATED NER families | ExtractedEntity[] with kg_type, normalized_text, priority |
| 2 | Entity Clustering | _build_entity_clusters (r4_kg_consolidator.py:1338) | O(e) | type:name grouping | EntityCluster[] with canonical_name, mentions, observation_ids |
| 3 | Alias Detection | AliasDetector (alias_detector.py:614) | O(n^2) pairwise within type | threshold=0.70, 4-signal weights (str=0.25, emb=0.30, nick=0.25, co=0.20) | Merged clusters + AliasCandidate audit |
| 4 | Disambiguation | EntityDisambiguator (entity_disambiguator.py:543) | O(n*m) candidates per entity | per-type weights (PERSON=0.50/0.50, FAMILY=0.30/0.70, CONCEPT=0.85/0.15), opposition penalty=0.25 | DisambiguationBreakdown with merged/rejected decisions |
| 5 | Ambiguous Resolution | AmbiguousEntityResolver (ambiguous_resolver.py:365) | O(c) per mention | 5-priority boosts (recency=0.35, co_occ=0.30, loc=0.20, temporal=0.10, freq=0.05), close_race_penalty=0.10 | ResolutionResult with AUTO/FLAG/GAP outcome |
| 6 | Confidence Routing | ConfidenceRouter (confidence_router.py:330) | O(1) | AUTO>=0.85, FLAG>=0.60, GAP<0.60 | ConfidenceBand + optional GapPayload for st_learning_queue |
| 7 | Merge Threshold Check | AdaptiveMergeThresholds (merge_threshold_learner.py:214) | O(1) lookup | per-type bounds (FAMILY_MEMBER: 0.85-0.98 default 0.90, CONCEPT: 0.55-0.75 default 0.65), learning rates FP=+0.02/FN=-0.02 | MergeDecision (should_merge, threshold, score) |
| 8 | Entity Create/Update | _process_entity_clusters (r4_kg_consolidator.py:1823) | O(n + DB) | entity_matching enabled, st_kg_dom lookup | KGUpdate[] (CREATE_ENTITY or UPDATE_ENTITY) |

#### 3.1.1 Entity Resolution Formulas

**Disambiguation Combined Score:**

```
combined_score = embedding_weight * embedding_sim + string_weight * string_sim
if opposition_detected:
    combined_score *= (1.0 - opposition_penalty)  # penalty = 0.25
```

Weight matrix (entity_disambiguator.py:543):

- PERSON: embedding=0.50, string=0.50
- FAMILY_MEMBER: embedding=0.30, string=0.70 (names matter more)
- CONCEPT: embedding=0.85, string=0.15 (semantics matter more)
- PLACE: embedding=0.40, string=0.60
- LOCATION: embedding=0.40, string=0.60
- ORGANIZATION: embedding=0.45, string=0.55
- EVENT: embedding=0.50, string=0.50
- default: embedding=0.50, string=0.50

**Alias Detection Combined Score:**

```
alias_score = (STRING_WEIGHT * string_sim
             + EMBEDDING_WEIGHT * embedding_sim
             + NICKNAME_WEIGHT * nickname_score
             + CO_OCCURRENCE_WEIGHT * co_occurrence_score)
# Weights: 0.25, 0.30, 0.25, 0.20 (alias_detector.py:24-27)
# Threshold: 0.70 (alias_detector.py:18)
```

**Ambiguous Resolution 5-Priority Scoring:**

```
total_score = base_confidence
            + recency_boost    * 0.35  # most recent entity strongly preferred
            + co_occurring_boost * 0.30  # same session entity boost
            + location_boost   * 0.20  # same location entity boost
            + temporal_boost   * 0.10  # close timestamp entity boost
            + frequency_boost  * 0.05  # high observation count boost

if |top_score - second_score| < close_race_threshold:
    total_score -= close_race_penalty  # 0.10 penalty
```

**Confidence Routing Decision Tree:**

```
confidence >= 0.85 → AUTO  (auto-resolve, no gap)
0.60 <= confidence < 0.85 → FLAG  (resolve with flag for review)
confidence < 0.60 → GAP  (emit to st_learning_queue for P06)
```

**Adaptive Merge Threshold Learning:**

```
on MERGE_REJECTED (FP):  threshold += 0.02 (raise bar)
on SPLIT_REQUEST:        threshold += 0.03 (raise bar more)
on MISSED_MERGE (FN):    threshold -= 0.02 (lower bar)
on MERGE_CONFIRMED:      no change
threshold = clamp(threshold, type_bounds.min, type_bounds.max)
```

### 3.2 Edge Discovery Pipeline

| Step | Algorithm | Class (File:Line) | Complexity | Key Parameters | Output |
| ---- | --------- | ------------------ | ---------- | -------------- | ------ |
| 1 | Hebbian Co-occurrence | HebbianLearner (hebbian_learner.py:296) | O(p) pairs per event | learning_rate=0.1, decay_rate=0.01/day, max_weight=1.0, min_weight=0.01 | EdgeUpdate[] with adaptive weights |
| 2 | Anti-Hebbian Decay | HebbianLearner (hebbian_learner.py:554) | O(1) per signal | anti_rate=0.15, correction_multiplier=1.3, 4 signal types (MERGE_REJECTED, WRONG, EXCLUSION, CONTRADICTION) | Penalized weights, prune candidates below 0.05 |
| 3 | UltraBERT Edge Type Inference | _infer_edge_type_from_relations (r4_kg_consolidator.py:2504) | O(r) relations | ULTRABERT_TO_TYPE priority map (FAMILY=4 > FRIEND=3 > COLLEAGUE=2 > ACQUAINTANCE=1) | Inferred relation_type (FAMILY/FRIEND/COLLEAGUE/RELATED_TO) |
| 4 | Edge Create/Update | _discover_relationships (r4_kg_consolidator.py:1936) | O(p + DB) | min_co_occurrence=1, existing edge lookup from st_kg_edges | KGUpdate[] (CREATE_EDGE or UPDATE_EDGE with observation_count) |

#### 3.2.1 Hebbian Learning Formulas

**Initial Weight (new edge):**

```
initial_weight = base_weight + learning_rate * importance
# base_weight = 0.1, learning_rate = 0.1
# Example: importance=0.8 → weight = 0.1 + 0.1 * 0.8 = 0.18
```

**Weight Update (existing edge):**

```
w_new = w_old + learning_rate * (1.0 - w_old) * importance
# Soft saturation: as w_old → 1.0, updates shrink toward 0
# Example: w=0.5, importance=0.8 → w_new = 0.5 + 0.1 * 0.5 * 0.8 = 0.54
```

**Exponential Decay (time-based):**

```
w_decayed = w * exp(-decay_rate * days_since_last)
# decay_rate = 0.01/day
# 30 days: w * 0.74; 90 days: w * 0.41; 365 days: w * 0.03
if w_decayed < prune_threshold (0.05):
    mark for archive
```

**Anti-Hebbian Penalty:**

```
w_penalized = w - anti_rate * correction_multiplier
# anti_rate = 0.15, correction_multiplier = 1.3 for CONTRADICTION
# Signal types: MERGE_REJECTED (1.0x), WRONG (1.0x), EXCLUSION (1.0x), CONTRADICTION (1.3x)
```

### 3.3 Causal Inference Pipeline

| Step | Algorithm | Class (File:Line) | Complexity | Key Parameters | Output |
| ---- | --------- | ------------------ | ---------- | -------------- | ------ |
| 1 | Temporal Precedence | GrangerCausalityInference (granger_causality.py:195) | O(t^2) timestamp pairs | min_observations=5 (config=1), temporal_window=60min, simultaneous_threshold=1min | TemporalPrecedenceStats (a_before_b, b_before_a, simultaneous, ratio) |
| 2 | Category Classification | CausalCategoryClassifier (causality_thresholds.py:181) | O(k) keywords | 4 categories with 20 keywords each (Health, Financial, Social, Preference) | CausalityCategory |
| 3 | Adaptive Thresholds | AdaptiveCausalityThresholds (causality_thresholds.py:236) | O(1) | Health=0.85, Financial=0.80, Social=0.70, Preference=0.65 | Threshold for CAUSES edge creation |
| 4 | Edge Type Assignment | _infer_causal_relationships (r4_kg_consolidator.py:2200) | O(1) per edge | CAUSES if ratio >= threshold, FOLLOWS if 0.60-threshold, PRECEDES if ratio <= 0.40 | CausalEdge with relation_type and confidence |
| 5 | Synthetic CAUSES | _generate_synthetic_causes_edges (r4_kg_consolidator.py:2158) | O(e) edges | observation_count >= 3, confidence >= 0.5, 10% penalty | CausalEdge[] from high-confidence co-occurrence |
| 6 | Feedback Adjustment | CausalEdgeFeedbackProcessor (edge_demotion.py:180) | O(f) feedback records | >90% boost +0.05, 70-90% maintain, 50-70% lower -0.10, <50% demote to CORRELATED | DemotionResult (action, old/new confidence) |
| 7 | Staleness Check | CausalEdgeStalenessChecker (edge_demotion.py:527) | O(1) per edge | 90-day window, min 5 feedback samples | DemotionResult (ARCHIVE if stale) |

#### 3.3.1 Granger Causality Formulas

**Temporal Precedence Ratio:**

```
for each observation pair (ts_a, ts_b):
    delta = ts_a - ts_b
    if |delta| < simultaneous_threshold_ms (60000):  # 1 min
        simultaneous += 1
    elif delta < 0:  # A before B
        a_before_b += 1
    else:  # B before A
        b_before_a += 1

ratio = a_before_b / (a_before_b + b_before_a)  # [0, 1]
# ratio > 0.5 → A tends to precede B
# ratio < 0.5 → B tends to precede A
```

**Edge Type Assignment:**

```
if total_observations < min_observations (5 prod, 1 test):
    skip pair (insufficient data)
elif ratio >= category_threshold:
    CAUSES edge (A → B)
elif ratio >= temporal_follows_threshold (0.60):
    FOLLOWS edge (A → B, weaker)
elif ratio <= 1.0 - temporal_follows_threshold (0.40):
    PRECEDES edge (B → A)
else:
    no causal edge (ambiguous)
```

**Synthetic CAUSES Generation:**

```
for each co-occurrence edge with:
    observation_count >= 3 AND confidence >= 0.5
    AND no Granger-derived edge exists for same pair:

    synthetic_confidence = confidence * 0.90  # 10% penalty
    create CAUSES edge with source_algorithm="synthetic"
```

**Feedback-Driven Confidence Adjustment:**

```
accuracy = correct_predictions / total_feedback_count
if accuracy > 0.90:   confidence += 0.05   (BOOST)
elif accuracy > 0.70: no change             (MAINTAIN)
elif accuracy > 0.50: confidence -= 0.10   (LOWER)
else:                  demote to CORRELATED  (DEMOTE)
confidence = clamp(confidence, 0.0, 1.0)
```

### 3.4 Edge Enrichment Pipeline (GAP-007)

| # | Algorithm | Class (File:Line) | Edge Type | Complexity | Key Parameters | Signal Source |
| - | --------- | ------------------ | --------- | ---------- | -------------- | ------------- |
| 1 | Semantic Similarity | SemanticSimilarityEnricher (semantic_similarity.py:~80) | SIMILAR_TO | O(n^2) entity pairs | k=10, threshold=0.75, max_edges=5/entity | Entity embeddings (pgvector) |
| 2 | Temporal Proximity | TemporalProximityEnricher (temporal_proximity.py:~70) | TEMPORALLY_ASSOCIATED | O(n^2) entity pairs | window=5min, tau=1min, min_weight=0.1, max_edges=10/entity | ObservationContext.observed_at timestamps |
| 3 | Contextual | ContextualEdgeEnricher (contextual.py:~60) | CONTEXTUALLY_RELATED | O(n^2) entity pairs | threshold=0.5, max_edges=5/entity, 5 feature weights | ObservationContext features (location, social, time, sentiment, ingress) |
| 4 | Emotion Similarity | EmotionSimilarityEnricher (emotion_similarity.py:~70) | EMOTIONALLY_RELATED | O(n^2) entity pairs | threshold=0.6, arousal_weight=0.3, max_edges=5/entity | ObservationContext.dominant_emotions_json, affect_arousal |
| 5 | Intent Similarity | IntentSimilarityEnricher (intent_similarity.py:~80) | INTENT_RELATED | O(n^2) entity pairs | threshold=0.5, max_edges=5/entity, 7 complementary intent pairs | ObservationContext.intent (UltraBERT 7-class) |
| 6 | Transitive Closure | TransitiveClosureEnricher (transitive_closure.py:~70) | INFERRED_RELATED | O(n*d^2) d=degree | max_hops=2, attenuation=0.7, min_confidence=0.3, max_edges=3/entity | Existing edge graph topology |
| 7 | Bayesian Causal | BayesianCausalEnricher (bayesian_causal.py:~60) | CAUSES | O(n^2) entity pairs | prior=0.1, min_evidence=3, posterior_threshold=0.6 | ObservationContext.observed_at temporal precedence |
| 8 | Weight Normalization | EdgeWeightNormalizer (weight_normalization.py:~40) | N/A (updates) | O(e) edges per entity | strategy=softmax, max_weight=1.0, min_weight=0.01 | All enriched edges (new + updates + existing) |
| 9 | Fusion Utilities | fusion.py functions | N/A | O(s) signals | weighted_sum or mean for weights, noisy-or or mean for confidence | EdgeSignal from all algorithms |

#### 3.4.1 Enrichment Formulas

**Semantic Similarity (cosine):**

```
sim(a, b) = dot(emb_a, emb_b) / (norm(emb_a) * norm(emb_b))
if sim >= threshold (0.75):
    create SIMILAR_TO edge with weight = sim, confidence = sim
```

**Temporal Proximity (exponential decay):**

```
for each entity pair (a, b):
    time_delta_ms = |observed_at_a - observed_at_b|
    if time_delta_ms <= window_ms (300000):  # 5 min
        weight = exp(-time_delta_ms / tau_ms)  # tau = 60000 (1 min)
        if weight >= min_weight (0.1):
            create TEMPORALLY_ASSOCIATED edge
```

**Contextual (weighted Jaccard):**

```
features = [location_type, social_context, time_of_day_bucket, sentiment_label, ingress_category]
jaccard_score = sum(w_i * overlap(feature_i_a, feature_i_b)) / sum(w_i)
if jaccard_score >= threshold (0.5):
    create CONTEXTUALLY_RELATED edge
```

**Emotion Similarity:**

```
emotion_sim = cosine_sim(emotion_vector_a, emotion_vector_b)
arousal_factor = 1.0 + arousal_weight * avg(arousal_a, arousal_b)
adjusted_sim = emotion_sim * arousal_factor
if adjusted_sim >= threshold (0.6):
    create EMOTIONALLY_RELATED edge
```

**Intent Complementary Matching:**

```
complementary_pairs = {
    "seek_advice": "express_feeling",
    "share_news": "acknowledge",
    "request_help": "offer_help",
    "complain": "sympathize",
    "plan": "agree",
    "reminisce": "reminisce",
    "inform": "acknowledge"
}
if (intent_a, intent_b) in complementary_pairs:
    create INTENT_RELATED edge with confidence based on intent match strength
```

**Transitive Closure (2-hop):**

```
for entity A:
    for neighbor B of A (1-hop):
        for neighbor C of B (2-hop, C != A):
            inferred_confidence = confidence(A->B) * confidence(B->C) * attenuation_factor
            # attenuation_factor = 0.7; noisy-or fusion if multiple paths
            if inferred_confidence >= min_confidence (0.3):
                create INFERRED_RELATED edge (A -> C)
```

**Bayesian Causal (posterior update):**

```
prior = prior_strength (0.1)  # weak prior
for each evidence pair (a_before_b):
    likelihood = temporal_precedence_count / total_observations
    posterior = (prior * likelihood) / normalizer  # simplified Bayes
if posterior >= posterior_threshold (0.6) AND evidence_count >= min_evidence (3):
    create CAUSES edge with confidence = posterior
```

**Weight Normalization (softmax per entity):**

```
for each entity:
    edges = all outgoing edges for entity
    weights = [edge.weight for edge in edges]
    normalized = exp(w_i) / sum(exp(w_j))  # softmax
    # Also: sum_to_one (w_i / sum(w_j)) or cap (min(w_i, max_weight))
```

### 3.5 Social Extraction Pipeline

| Step | Algorithm | Method (File:Line) | Complexity | Key Parameters | Output |
| ---- | --------- | ------------------- | ---------- | -------------- | ------ |
| 1 | UltraBERT Relation Parsing | _extract_social_relationships (r4_kg_consolidator.py:2588) | O(e*p) events*people | extracted_relations_json from P02, 15 UltraBERT relation types | Per-pair aggregated relation counts |
| 2 | Relationship Type Derivation | _derive_relationship_type (r4_kg_consolidator.py:2918) | O(r) relations | ULTRABERT_TO_TYPE priority (FAMILY > FRIEND > COLLEAGUE > ACQUAINTANCE), social_context fallback | FAMILY/FRIEND/COLLEAGUE/ACQUAINTANCE |
| 3 | Subtype Derivation | _derive_relationship_subtype (r4_kg_consolidator.py:2975) | O(r) relations | ULTRABERT_TO_SUBTYPE (12 subtypes), kinship name inference, social_context fallback | SPOUSE/PARENT/CHILD/SIBLING/COWORKER/etc. |
| 4 | Emotional Analysis | sentiment/emotion aggregation (r4_kg_consolidator.py:~2800) | O(s) sentiments | SENTIMENT_VALENCE mapping (-1.0 to +1.0), emotion aggregation, ROLE_EMOTIONS (6 roles) | emotional_valence_avg/trend, dominant_emotion, emotional_role |
| 5 | Relationship Phase | _infer_relationship_phase (r4_kg_consolidator.py:3051) | O(1) | interaction_count <= 2 -> FORMING, trend > 0.2 -> DEEPENING, trend < -0.2 -> COOLING, else STABLE | FORMING/STABLE/DEEPENING/COOLING |
| 6 | Confidence Scoring | base + observation + UltraBERT (r4_kg_consolidator.py:~2880) | O(1) | base=0.5, obs_boost=min(0.3, count*0.05), ultrabert_boost=0.15 | Confidence 0.50-0.95 |

#### 3.5.1 Social Extraction Formulas

**Emotional Valence Mapping:**

```
SENTIMENT_VALENCE = {
    "very_positive": +1.0, "positive": +0.6, "slightly_positive": +0.3,
    "neutral": 0.0,
    "slightly_negative": -0.3, "negative": -0.6, "very_negative": -1.0
}
emotional_valence_avg = mean(SENTIMENT_VALENCE[s] for s in sentiments)
```

**Emotional Role Classification:**

```
ROLE_EMOTIONS = {
    "SUPPORTER": ["joy", "gratitude", "pride"],
    "DEPENDENT": ["sadness", "fear", "anxiety"],
    "MUTUAL_SUPPORT": ["joy", "gratitude", "love"],
    "ANTAGONIST": ["anger", "contempt", "disgust"],
    "NEUTRAL": ["neutral", "surprise"],
    "CARETAKER": ["concern", "worry", "compassion"]
}
emotional_role = argmax(sum(emotions[e] for e in role_emotions) for role in ROLE_EMOTIONS)
```

**Social Confidence Scoring:**

```
base_confidence = 0.50
observation_boost = min(0.30, interaction_count * 0.05)
ultrabert_boost = 0.15 if has_ultrabert_relation else 0.00
confidence = min(0.95, base_confidence + observation_boost + ultrabert_boost)
# 1 interaction: 0.55-0.70; 6+ interactions: 0.80-0.95
```

### 3.6 MW v2 Signal Gaps (from Epic 5.5 Skeleton)

These MW v2 signals are available from P02 but NOT yet consumed by R4:

| MW v2 Signal | Current Use in R4 | Gap | Enhancement Opportunity |
| ------------ | ----------------- | --- | ----------------------- |
| participant_relationships | Partially used via extracted_relations_json | Only UltraBERT extracted relations, no MW relationship type context | Use MW relationship metadata for richer relationship edge typing |
| social_intimacy_level | NOT used in R4 | Edge weight does not consider intimacy | Weight social edges by intimacy level; boost FAMILY edges for high-intimacy |
| identity_relevance | NOT used | Self-referential entities not distinguished | Boost merge confidence for self-referential entities; reduce false splits |
| narrative_thread_id | NOT used | Co-occurrence window is time-based only | Same narrative thread = stronger co-occurrence signal (beyond temporal proximity) |
| elaboration_depth | NOT used | Entity confidence does not consider context richness | Higher elaboration = higher extraction confidence; reduce false positives for shallow mentions |

---

## 4. Data Flow & I/O Map

### 4.1 Pipeline Stage Map

R4 is a single phase within P03 with 10 internal steps executed sequentially:

| Stage Order | Stage ID | Module | Input | Output | Side Effects | Error Handling | Retry Policy |
| ----------- | -------- | ------ | ----- | ------ | ------------ | -------------- | ------------ |
| 1 | extract_entities | entity_extractor + r4_kg_consolidator._extract_entities | P03EventState.ner_entities_json, extracted_relations_json | all_entities[], event_entity_map, event_relations_map | Stats: entities_extracted, entities_by_type | Non-fatal: malformed JSON skipped per event | N/A (inline) |
| 2 | build_clusters | r4_kg_consolidator._build_entity_clusters | all_entities + event_entity_map + events | EntityCluster[] | Stats: resolved_gaps_applied; DB READ: st_learning_queue for resolved gaps | Non-fatal: DB errors logged, continues without resolved gaps | N/A |
| 2.5 | detect_aliases | alias_detector + r4_kg_consolidator._detect_aliases | EntityCluster[] | Merged clusters + AliasCandidate[] | Stats: alias_pairs_compared, alias_candidates_detected, alias_merges_performed | Non-fatal: alias detection failure returns original clusters | N/A |
| 3 | resolve_entities | ambiguous_resolver + confidence_router + r4_kg_consolidator._resolve_entities | EntityCluster[] + events | resolved_clusters[] + GapCandidate[] | Stats: auto_resolved, flagged_for_review, gaps_emitted; DB READ: st_kg_dom (fuzzy candidate query) | Non-fatal: DB errors fall back to cluster confidence routing | N/A |
| 3.5 | build_entity_context_map | r4_kg_consolidator._build_entity_context_map | events + event_entity_map + resolved_clusters | entity_contexts: Dict[str, List[ObservationContext]] | None | Non-fatal: missing context data defaults to empty list | N/A |
| 4 | process_entity_clusters | r4_kg_consolidator._process_entity_clusters | resolved_clusters + tenant/space | KGUpdate[] (CREATE/UPDATE ENTITY) | Stats: new_entities_created, existing_entities_updated; DB READ: st_kg_dom (entities_lookup) | Non-fatal: DB errors fall back to CREATE all | N/A |
| 5 | discover_relationships | hebbian_learner + r4_kg_consolidator._discover_relationships | resolved_clusters + event_entity_map + event_relations_map | KGUpdate[] (CREATE/UPDATE EDGE) | Stats: co_occurrence_pairs, new_edges_created, existing_edges_updated, hebbian_edges_strengthened; DB READ: st_kg_edges (edges_lookup) | Non-fatal: DB errors fall back to CREATE all | N/A |
| 5.5 | extract_social | r4_kg_consolidator._extract_social_relationships | events + resolved_clusters | SocialRelationship[] | Stats: social_relationships_extracted, social_relationships_by_type | Non-fatal: JSON parse errors skipped per event | N/A |
| 6 | infer_causal | granger_causality + causality_thresholds + r4_kg_consolidator._infer_causal_relationships | edge_updates + resolved_clusters + timestamps | CausalEdge[] | Stats: causal_edges_created, causal_pairs_analyzed, causal_edges_by_category | Non-fatal: insufficient observations skipped per pair | N/A |
| 7 | edge_enrichment | 7 enrichers + weight_normalizer | entity_contexts + existing_edges | enrichment_new_edges[] + enrichment_updated_edges[] | Stats: enrichment_new_edges, enrichment_updated_edges, enrichment_edges_by_algorithm; DB READ: kg_edges_lookup | Non-fatal: per-enricher exceptions caught, others continue | N/A |
| 8 | populate_outputs | r4_kg_consolidator._populate_phase_outputs | all outputs from steps 1-7 | envelope.phases.r4_* populated | Emits decision metrics (CREATE/REINFORCE) via metrics_registry | N/A | N/A |

### 4.2 Input Schema (P03EventState fields consumed by R4)

| # | Field | Type | Required | Nullable | Source | Purpose |
| - | ----- | ---- | -------- | -------- | ------ | ------- |
| 1 | event_id | str | yes | no | P03 envelope | Unique event identifier for entity-event mapping |
| 2 | ner_entities_json | str (JSON) | yes | yes | P02 UltraBERT NER | Pre-computed NER entities: {"ner_family": {"entities": [...]}, "ner_general": {"entities": [...]}} |
| 3 | extracted_relations_json | str (JSON) | no | yes | P02 UltraBERT RE | Pre-computed relation types: ["parent_of", "friend_of", ...] |
| 4 | content_text | str | no | yes | P02 preprocessing | Original text for entity extraction context |
| 5 | timestamp | int | no | yes | P02 temporal resolution | Event timestamp (ms) for temporal precedence, Granger causality |
| 6 | session_id | str | no | yes | Ingress | Session ID for co-occurrence context in disambiguation |
| 7 | actor_id | str | no | yes | Ingress | User/actor ID for social relationship extraction (SELF actor) |
| 8 | sentiment | str | no | yes | P02 MW/UltraBERT | Sentiment label (very_negative to very_positive) for social emotional_valence |
| 9 | sentiment_confidence | float | no | yes | P02 MW/UltraBERT | Sentiment confidence for weighted averaging |
| 10 | emotions_json | str (JSON) | no | yes | P02 MW affect | Emotion labels for social emotional_role and emotion similarity enrichment |
| 11 | participants_json | str (JSON) | no | yes | P02 social extraction | Participant IDs for social relationship extraction |
| 12 | entities_json | str (JSON) | no | yes | P02 NER | Entity list for person extraction in social relationships |
| 13 | social_context | str | no | yes | P02 social extraction | Social setting (nuclear_family, work, friends, solo) for context enrichment |
| 14 | activity_type_ultrabert | str | no | yes | P02 UltraBERT 12-class | Activity classification for social relationship context |
| 15 | location_name | str | no | yes | P02 spatial resolution | Location for social relationship location_pattern |
| 16 | social_intimacy | str | no | yes | P02 social module | Intimacy level for social relationship intimacy_level |
| 17 | created_at | int | no | yes | Ingress | Event creation timestamp for social sentiment trajectory |
| 18 | num_participants | int | no | yes | P02 social extraction | Participant count (0 = solo, skip social extraction) |
| 19 | tenant_id | str | yes | no | P03 envelope context | Tenant isolation for all DB queries |

### 4.3 Output Schema (envelope.phases.r4_* fields)

| # | Field | Type | Nullable | Produced By | Consumed By | Description |
| - | ----- | ---- | -------- | ----------- | ----------- | ----------- |
| 1 | r4_new_entities | List[KGEntity] | no | _process_entity_clusters (CREATE) | R7 truth writer -> st_kg_dom INSERT | New KG entities with entity_id, canonical_name, type, subtype, aliases, confidence |
| 2 | r4_updated_entities | List[KGEntityUpdate] | no | _process_entity_clusters (UPDATE) +_emit_canonical_name_updates | R7 truth writer -> st_kg_dom UPDATE | Entity reinforcements: observation_count increment, new aliases, canonical_name updates |
| 3 | r4_new_edges | List[KGEdge] | no | _discover_relationships (CREATE) + _infer_causal (CausalEdge) + enrichment_new_edges | R7 truth writer -> st_kg_edges INSERT | New KG edges: co-occurrence, causal, enrichment edges with relation_type, weight, confidence |
| 4 | r4_updated_edges | List[KGEdgeUpdate] | no | _discover_relationships (UPDATE) + enrichment_updated_edges + weight normalization | R7 truth writer -> st_kg_edges UPDATE | Edge reinforcements: observation_count increment, weight/confidence deltas |
| 5 | r4_gap_candidates | List[GapCandidate] | no | _resolve_entities (GAP_EMITTED/FLAG) | R7 truth writer -> st_learning_queue INSERT | Gap candidates for P06 resolution: AMBIGUOUS_ENTITY, ENTITY_FLAGGED |
| 6 | r4_social_entities | List[SocialRelationship] | no | _extract_social_relationships | R6 truth writer -> st_social INSERT/UPDATE | Social relationships with type, subtype, emotional analysis, phase |

### 4.4 Data Transformation Map

| # | Source Field(s) | Transformation | Target Field | Lossy? | Reversible? | Notes |
| - | --------------- | -------------- | ------------ | ------ | ----------- | ----- |
| 1 | ner_entities_json | JSON parse -> head-based filtering -> filter_and_normalize() | ExtractedEntity[] | yes | no | NER JSON -> typed entity objects; family-span dedup loses general entities that overlap |
| 2 | ExtractedEntity[] | Group by type:normalized_name -> canonical_name selection -> subtype classification | EntityCluster[] | yes | no | Multiple mentions collapsed to single cluster; possessives stripped |
| 3 | EntityCluster[] | 4-signal alias scoring -> cluster merging | Merged EntityCluster[] | yes | no | Alias clusters absorbed into primary; secondary cluster removed |
| 4 | EntityCluster + st_kg_dom candidates | 5-priority context scoring -> AUTO/FLAG/GAP routing | Resolved EntityCluster[] + GapCandidate[] | no | yes | Routing decision is deterministic from same inputs |
| 5 | Resolved clusters + event_entity_map | Co-occurrence counting -> HebbianLearner adaptive weighting | KGUpdate (edges) | yes | no | Multiple events per pair collapsed to single weight |
| 6 | Edge updates + timestamps | Temporal precedence ratio -> category threshold comparison | CausalEdge[] | yes | no | Timestamp pairs collapsed to single ratio; category keywords are lossy |
| 7 | Events + resolved_clusters | UltraBERT relation parsing + sentiment/emotion aggregation | SocialRelationship[] | yes | no | Per-event data aggregated to per-pair relationship |
| 8 | Entity contexts per enricher | Algorithm-specific similarity -> edge creation | Enrichment KGEdge[] | yes | no | Raw signals (embeddings, timestamps, contexts) reduced to scalar weight/confidence |

### 4.5 Error Outputs

| # | Error Code / Type | Condition | Handling | Downstream Impact | Recoverable? |
| - | ----------------- | --------- | -------- | ----------------- | ------------ |
| 1 | P03Error (R4_KG_ERROR) | Any unhandled exception in run() | Catch all -> P03PhaseResult.fail(recoverable=True) | Phase marked failed; R5-R8 may still proceed with partial data | yes -- retry on next cycle |
| 2 | JSONDecodeError | Malformed ner_entities_json or extracted_relations_json | Skip per event, continue | Individual event entities lost; other events unaffected | yes -- data correction fixes source |
| 3 | DB connection failure | st_kg_dom, st_kg_edges, st_learning_queue unavailable | Log warning, continue without DB lookup | Entities all created new (potential duplicates); edges all created new; no resolved gaps | yes -- transient |
| 4 | kg_candidates_fuzzy_query failure | st_kg_dom fuzzy query errors | Log warning, fall back to cluster confidence routing | Ambiguous entities may not be properly resolved | yes -- next cycle will retry |
| 5 | kg_edges_lookup failure | st_kg_edges lookup errors | Log warning, create all edges as new | Duplicate edges until R7 ON CONFLICT resolves | yes -- transient |

---

## 5. Storage & Persistence

### 5.1 Tables Touched

| # | Table | Operation | Key Columns Used | Access Pattern | Index Used | Estimated Row Count |
| - | ----- | --------- | ---------------- | -------------- | ---------- | ------------------- |
| 1 | st_kg_dom | R | entity_id, entity_type, canonical_name, tenant_id, space_id | range (fuzzy name match by type+name), range (entities_lookup by tenant+space) | ix_st_kg_dom_tenant_space, ix_st_kg_dom_type_name | ~10K-100K |
| 2 | st_kg_edges | R | edge_id, source_entity_id, target_entity_id, tenant_id, space_id | range (edges_lookup by tenant+space) | ix_st_kg_edges_tenant_space | ~50K-500K |
| 3 | st_learning_queue | R | entity_id, status, resolution_data_json | range (status='RESOLVED' scan) | ix_st_learning_queue_status | ~1K-10K |
| 4 | st_kg_dom | W (via R7) | entity_id, canonical_name, entity_type, entity_subtype, aliases_json, observation_count, confidence_score, first_mentioned_event_id, last_observed_at | point (INSERT/UPDATE by entity_id) | PK | ~10K-100K |
| 5 | st_kg_edges | W (via R7) | edge_id, source_entity_id, target_entity_id, relationship_type, relation_subtype, weight, confidence, observation_count, source_algorithm, evidence_event_ids, last_observed_at | point (INSERT/UPDATE by edge_id) | PK | ~50K-500K |
| 6 | st_social | W (via R6) | relationship_id, actor_a_id, actor_b_id, relationship_type, relationship_subtype, intimacy_level, emotional_valence_avg, dominant_emotion, interaction_count | point (INSERT/UPDATE by relationship_id) | PK | ~1K-10K |
| 7 | st_learning_queue | W (via R7) | gap_id, gap_type, entity_id, context_json, candidate_values, priority | point (INSERT by gap_id) | PK | ~1K-10K |
| 8 | st_learned_weights | RW | entity_type, metric_name, value | point (by entity_type + metric_name) | PK | ~100 |
| 9 | st_entity_merges | W (via EntityMerger) | merge_id, primary_entity_id, secondary_entity_id, merge_cascade_id, status | point (INSERT by merge_id) | PK | ~100-1K |

> **Note**: R4 itself only READs from the database (st_kg_dom, st_kg_edges, st_learning_queue). All WRITEs
> are deferred to R6 (social) and R7 (truth writer) which consume envelope.phases.r4_* outputs.
> EntityMerger writes directly but is currently only invoked from P06 gap resolution, not R4's main path.

### 5.2 Query Patterns

| # | Query Purpose | SQL Pattern | Frequency | Expected Latency | Index Coverage | Notes |
| - | ------------- | ----------- | --------- | ---------------- | -------------- | ----- |
| 1 | Load resolved gaps | SELECT entity_id, resolution_data_json FROM st_learning_queue WHERE status='RESOLVED' AND resolution_data_json IS NOT NULL | once per cycle | < 50ms | partial (status index) | Could benefit from composite (status, entity_id) index |
| 2 | Fuzzy entity candidate query | kg_candidates_fuzzy_query(tenant, space, type, name_pattern, limit=10) | per entity cluster | < 20ms each | full (type + name index) | Pattern matching varies by implementation |
| 3 | Existing entities lookup | kg_entities_lookup(tenant, space) | once per cycle | < 100ms | full (tenant + space) | Returns all entities for tenant+space; O(n) memory |
| 4 | Existing edges lookup | kg_edges_lookup(tenant, space) | once per cycle (+ once for enrichment) | < 200ms | full (tenant + space) | Returns all edges for tenant+space; O(e) memory; called twice (relationships + enrichment) |
| 5 | Embedding resolution (semantic enricher) | syscalls.resolve_embeddings(entity_ids) | once per cycle if semantic enricher enabled | < 200ms | varies by implementation | Fetches stored embeddings for cosine similarity |

### 5.3 Storage Gaps

| # | Gap | Current State | Required State | Migration Needed? | Priority |
| - | --- | ------------- | -------------- | ----------------- | -------- |
| 1 | kg_edges_lookup called twice per cycle | Two separate full-table reads: once for relationship discovery, once for enrichment | Single read cached for both uses | no (code-only optimization) | P2 |
| 2 | kg_entities_lookup loads all entities | Loads all entities for tenant+space into memory | Filtered query by entity_type or name prefix | no (syscall signature change) | P3 |
| 3 | No composite index on st_learning_queue (status, entity_id) | Separate status index | Composite for resolved gap query | yes | P3 |
| 4 | st_entity_merges lacks cascade tracking index | PK only on merge_id | Index on merge_cascade_id for undo lookups | yes | P2 |

---

## 6. Event Bus & Topics

### 6.1 Topics Consumed

| # | Topic | Producer | Consumer | Ordering | Idempotency Key |
| - | ----- | -------- | -------- | -------- | --------------- |
| 1 | P03 batch envelope (internal) | P03Runner (after R3) | R4KGConsolidator.run() | ordered (sequential R-phase execution) | cycle_id + space_id (envelope-level) |

> **Note**: R4 does not directly consume any event bus topics. It receives a P03BatchEnvelope
> from the P03Runner's sequential phase execution (R0 -> R1 -> R2 -> R3 -> **R4** -> R5 -> ...).
> The envelope carries all events and prior phase outputs.

### 6.2 Topics Produced

| # | Topic | Schema | Consumer | Trigger Condition | Notes |
| - | ----- | ------ | -------- | ----------------- | ----- |
| 1 | Decision metrics (CREATE/REINFORCE) | metrics_registry.emit_decision() | Observability / Grafana | Every entity/edge CREATE or UPDATE | Emits target_layer (st_kg_dom/st_kg_edges), decision_type, confidence |

> **Note**: R4 does not publish to event bus topics. All outputs are written to envelope.phases.r4_*
> lists which are consumed by downstream R-phases (R5, R6, R7) within the same pipeline run.
> Gap candidates in r4_gap_candidates are written to st_learning_queue by R7.

### 6.3 Event Flow Diagram

```
P03EventState[]
       |
       v
[1. Extract Entities] -- ner_entities_json, extracted_relations_json
       |
       v
[2. Build Clusters] -- st_learning_queue (resolved gaps READ)
       |
       v
[2.5 Detect Aliases] -- AliasDetector 4-signal scoring
       |
       v
[3. Resolve Entities] -- st_kg_dom (fuzzy candidate READ) + AmbiguousEntityResolver + ConfidenceRouter
       |                              |
       v                              v
  resolved_clusters[]           GapCandidate[] -> r4_gap_candidates -> R7 -> st_learning_queue
       |
       +---> [4. Process Entities] -- st_kg_dom (entities_lookup READ)
       |            |
       |            v
       |     KGUpdate[] (CREATE/UPDATE ENTITY) -> r4_new_entities + r4_updated_entities -> R7 -> st_kg_dom
       |
       +---> [5. Discover Relationships] -- st_kg_edges (edges_lookup READ) + HebbianLearner
       |            |
       |            v
       |     KGUpdate[] (CREATE/UPDATE EDGE) -> r4_new_edges + r4_updated_edges -> R7 -> st_kg_edges
       |
       +---> [5.5 Extract Social] -- UltraBERT relations + sentiment + emotions
       |            |
       |            v
       |     SocialRelationship[] -> r4_social_entities -> R6 -> st_social
       |
       +---> [6. Infer Causal] -- GrangerCausality + CategoryClassifier + AdaptiveThresholds
       |            |
       |            v
       |     CausalEdge[] -> r4_new_edges (appended) -> R7 -> st_kg_edges
       |
       +---> [7. Edge Enrichment] -- 7 enrichers + weight normalizer + st_kg_edges (READ)
                    |
                    v
              enrichment_new_edges[] + enrichment_updated_edges[] -> r4_new_edges + r4_updated_edges (appended)
```

---

## 7. Observability

### 7.1 Structured Logging

#### 7.1.1 INFO-Level Logs (Phase Lifecycle & Summaries)

| # | Log Level | File:Line | Message Pattern | Extra Fields | Frequency | Purpose |
| - | --------- | --------- | --------------- | ------------ | --------- | ------- |
| 1 | INFO | r4_kg_consolidator.py:710 | "R4: Starting knowledge graph consolidation phase" | cycle_id, tenant_id, space_id, event_count | once per cycle | Phase start marker |
| 2 | INFO | r4_kg_consolidator.py:727 | "R4: Processing {n} events for KG consolidation" | event_count, has_ner_data_count | once per cycle | Event inventory |
| 3 | INFO | r4_kg_consolidator.py:670 | "R4: Loaded {n} resolved gaps from st_learning_queue" | count | once per cycle | Resolved gap cache status |
| 4 | INFO | r4_kg_consolidator.py:1206 | "R4: Entity extraction complete" | entities_extracted, entities_by_type, duration_ms | once per cycle | Extraction summary |
| 5 | INFO | r4_kg_consolidator.py:1576 | "R4: Alias detection complete" | pairs_compared, candidates_detected, nickname_matches, merges_performed, duration_ms | once per cycle | Alias detection summary |
| 6 | INFO | r4_kg_consolidator.py:2384 | "R4 AUDIT: Relation type distribution" | CAUSES count, FOLLOWS count, PRECEDES count | once per cycle | Causal edge type audit |
| 7 | INFO | r4_kg_consolidator.py:2394 | "R4 AUDIT: Processing stats" | min_observations_threshold, precedence_threshold | once per cycle | Granger threshold audit |
| 8 | INFO | r4_kg_consolidator.py:2414 | "R4 AUDIT: Category distribution" | category_counts dict (Health/Financial/Social/Preference) | once per cycle | Causal category audit |
| 9 | INFO | r4_kg_consolidator.py:2417 | "R4 AUDIT: Threshold usage" | thresholds_used dict per category | once per cycle | Per-category threshold values used |
| 10 | INFO | r4_kg_consolidator.py:2425 | "R4 AUDIT: Sample causal edges" | first 3 edges (source, type, target, confidence) | once per cycle | Causal edge sample for debugging |
| 11 | INFO | r4_kg_consolidator.py:2433 | "R4: Added {n} synthetic CAUSES edges" | count | once per cycle | Synthetic edge generation summary |
| 12 | INFO | r4_kg_consolidator.py:2911 | "R4: Social extraction complete" | relationship_count, event_count, relationships_by_type | once per cycle | Social extraction summary |
| 13 | INFO | r4_kg_consolidator.py:3180 | "R4: Phase outputs populated" | new_entities, updated_entities, new_edges, updated_edges, causal_edges, social_entities, gap_candidates | once per cycle | Output population summary |
| 14 | INFO | r4_kg_consolidator.py:3403 | "R4: Episode entity_ids updated" | episodes_updated, mappings_applied | once per cycle | Episode alignment summary |
| 15 | INFO | r4_kg_consolidator.py:3408 | "R4: Sample mappings" | first 5 entity_name -> cluster_id mappings | once per cycle | Episode alignment sample |
| 16 | INFO | r4_kg_consolidator.py:3442 | "R4: Canonical name updates emitted" | updates_emitted | once per cycle | Resolved gap update summary |
| 17 | INFO | r4_kg_consolidator.py:3492 | "R4: Emitted {n} canonical_name updates for resolved gaps" | updates_emitted | once per cycle | Resolved gap emission count |
| 18 | INFO | r4_kg_consolidator.py:1020 | "R4: Knowledge graph consolidation complete" | cycle_id, entities_extracted, new_entities, updated_entities, new_edges, updated_edges, causal_edges, social_relationships, gaps_emitted, enrichment_new, enrichment_updated, duration_ms | once per cycle | Phase completion summary (comprehensive) |

#### 7.1.2 DEBUG-Level Logs (Per-Entity/Edge Decision Traces)

| # | Log Level | File:Line | Message Pattern | Extra Fields | Frequency | Purpose |
| - | --------- | --------- | --------------- | ------------ | --------- | ------- |
| 1 | DEBUG | r4_kg_consolidator.py:631 | "R4: No syscalls available, skipping resolved gaps lookup" | none | conditional | Missing syscalls guard |
| 2 | DEBUG | r4_kg_consolidator.py:637 | "R4: No connection pool available" | none | conditional | Missing DB pool guard |
| 3 | DEBUG | r4_kg_consolidator.py:664 | "R4: Resolved gap loaded" | entity_id, resolved_value | per resolved gap | Gap cache population trace |
| 4 | DEBUG | r4_kg_consolidator.py:1175 | "R4: Family spans collected for dedup" | family_spans list | per event with family NER | Family-span dedup trace |
| 5 | DEBUG | r4_kg_consolidator.py:1410 | "R4: Applied resolved gap to cluster" | cluster_id, old_name, new_name | per resolved cluster | Gap application trace |
| 6 | DEBUG | r4_kg_consolidator.py:1423 | "Using resolved canonical name for {cluster_id}: {name}" | cluster_id, canonical_name | per resolved cluster | Canonical name override trace |
| 7 | DEBUG | r4_kg_consolidator.py:1563 | "R4: Alias merge performed" | primary_cluster, secondary_cluster, score | per alias merge | Alias merge decision trace |
| 8 | DEBUG | r4_kg_consolidator.py:1683 | "R4: Fuzzy candidates found" | entity_name, candidate_count, top_score | per entity cluster | Disambiguation candidate trace |
| 9 | DEBUG | r4_kg_consolidator.py:1724 | "R4: AUTO_RESOLVED" | entity_name, entity_id, confidence, breakdown_scores | per auto-resolved entity | High-confidence resolution trace |
| 10 | DEBUG | r4_kg_consolidator.py:1749 | "R4: RESOLVED_FLAGGED" | entity_name, entity_id, confidence, flag_reason | per flagged entity | Medium-confidence resolution trace |
| 11 | DEBUG | r4_kg_consolidator.py:1776 | "R4: GAP_EMITTED" | entity_name, gap_type, candidate_count | per gap emission | Low-confidence gap trace |
| 12 | DEBUG | r4_kg_consolidator.py:1857 | "R4: Loaded {n} existing entities for matching" | entity_count | once per cycle | Existing entity cache size |
| 13 | DEBUG | r4_kg_consolidator.py:1889 | "R4: REINFORCE existing entity" | entity_id, canonical_name, old_count, new_count | per existing entity | Entity reinforcement trace |
| 14 | DEBUG | r4_kg_consolidator.py:1980 | "R4: Loaded {n} existing edges for update detection" | edge_count | once per cycle | Existing edge cache size |
| 15 | DEBUG | r4_kg_consolidator.py:2050 | "R4: Co-occurrence pair detected" | entity_a, entity_b, event_id | per co-occurrence pair | Hebbian pair detection trace |
| 16 | DEBUG | r4_kg_consolidator.py:2123 | "R4: Updating edge observation_count" | edge_id, old_count, new_count, old_weight, new_weight | per existing edge update | Edge reinforcement trace |
| 17 | DEBUG | r4_kg_consolidator.py:2197 | "R4: Generated {n} synthetic CAUSES edges" | count | once per cycle | Synthetic edge generation trace |
| 18 | DEBUG | r4_kg_consolidator.py:3250 | "R4: Enrichment results" | algorithm_name, new_edges, updated_edges | per enricher | Per-enricher output trace |
| 19 | DEBUG | r4_kg_consolidator.py:3438 | "R4: Checking resolved gap for canonical update" | entity_id, current_name, resolved_name | per resolved gap | Canonical update check trace |
| 20 | DEBUG | r4_kg_consolidator.py:3489 | "R4: Emitting canonical_name update" | entity_id, canonical_name | per canonical update | Canonical name emission trace |

#### 7.1.3 WARNING-Level Logs (Non-Fatal Errors)

| # | Log Level | File:Line | Message Pattern | Extra Fields | Frequency | Purpose |
| - | --------- | --------- | --------------- | ------------ | --------- | ------- |
| 1 | WARNING | r4_kg_consolidator.py:668 | "R4: Failed to parse resolution_data for {entity_id}" | entity_id, error | per malformed gap | Non-fatal gap parse error |
| 2 | WARNING | r4_kg_consolidator.py:675 | "R4: Failed to load resolved gaps: {e}" | error | once per cycle on DB failure | Non-fatal DB connection error |
| 3 | WARNING | r4_kg_consolidator.py:821 | "R4: enrichment edge lookup failed" | error | once per cycle on DB failure | Non-fatal enrichment DB error |
| 4 | WARNING | r4_kg_consolidator.py:1687 | "R4: Fuzzy query failed for entity" | entity_name, error | per entity on query failure | Non-fatal disambiguation DB error |
| 5 | WARNING | r4_kg_consolidator.py:1859 | "R4: Failed to load existing entities: {e}, will create new" | error | once per cycle on DB failure | Non-fatal entity lookup error (fallback: CREATE all) |
| 6 | WARNING | r4_kg_consolidator.py:1982 | "R4: Failed to load existing edges: {e}, will create new edges" | error | once per cycle on DB failure | Non-fatal edge lookup error (fallback: CREATE all) |

#### 7.1.4 EXCEPTION-Level Logs (Phase Failures)

| # | Log Level | File:Line | Message Pattern | Extra Fields | Frequency | Purpose |
| - | --------- | --------- | --------------- | ------------ | --------- | ------- |
| 1 | EXCEPTION | r4_kg_consolidator.py:1061 | "R4: Knowledge graph consolidation failed" | cycle_id, error, duration_ms, stack_trace | on unhandled exception | Phase failure; returns P03PhaseResult.fail(recoverable=True) |

**Total Logging Points: 45 (18 INFO + 20 DEBUG + 6 WARNING + 1 EXCEPTION)**

### 7.2 Stats Tracking (self._stats mutations)

R4PhaseStats is mutated at 40+ locations throughout r4_kg_consolidator.py:

| # | File:Line | Stats Field(s) Mutated | Trigger |
| - | --------- | ---------------------- | ------- |
| 1 | 721 | _stats = R4PhaseStats() | Phase start (reset) |
| 2 | 752 | extraction_duration_ms | Entity extraction complete |
| 3 | 768 | disambiguation_duration_ms | Disambiguation complete |
| 4 | 802 | edge_discovery_duration_ms | Edge discovery complete |
| 5 | 950 | enrichment_duration_ms | Enrichment complete |
| 6 | 951-963 | enrichment_new_edges, enrichment_updated_edges, enrichment_edges_by_algorithm, enrichment_updates_by_algorithm | Per-enricher results aggregation |
| 7 | 971-977 | social_extraction_duration_ms, social_relationships_extracted, social_relationships_by_type | Social extraction complete |
| 8 | 991 | causal_inference_duration_ms | Causal inference complete |
| 9 | 1017-1018 | total_duration_ms, events_processed | Phase complete |
| 10 | 1269-1273 | entities_extracted, entities_by_type | Per-type entity extraction |
| 11 | 1422 | resolved_gaps_applied | Per resolved gap application |
| 12 | 1511-1513 | alias_pairs_compared, alias_candidates_detected, alias_nickname_matches | Alias detection results |
| 13 | 1561 | alias_merges_performed | Per alias merge |
| 14 | 1574 | alias_detection_duration_ms | Alias detection complete |
| 15 | 1715 | disambiguation_attempts | Per disambiguation attempt |
| 16 | 1721-1722 | auto_resolved, disambiguation_successes | Per auto-resolution |
| 17 | 1733-1734 | flagged_for_review, disambiguation_successes | Per flagged resolution |
| 18 | 1756-1758 | gaps_emitted, ambiguous_mentions, disambiguation_failures | Per gap emission |
| 19 | 1788 | auto_resolved | Per inline auto-resolution |
| 20 | 1792 | flagged_for_review | Per inline flagged resolution |
| 21 | 1807-1808 | gaps_emitted, ambiguous_mentions | Per inline gap emission |
| 22 | 1872 | existing_entities_updated | Per entity reinforcement |
| 23 | 1895 | new_entities_created | Per new entity creation |
| 24 | 1915 | new_entities_created | Per new entity (no DB match path) |
| 25 | 2037 | co_occurrence_pairs | Hebbian pair count |
| 26 | 2073 | hebbian_edges_strengthened | Per Hebbian strengthen |
| 27 | 2075 | hebbian_edges_weakened | Per Hebbian weaken |
| 28 | 2108 | existing_edges_updated | Per existing edge update |
| 29 | 2130 | new_edges_created | Per new edge creation |
| 30 | 2375-2378 | causal_edges_created, causal_edges_by_category | Per causal edge creation |
| 31 | 2381 | causal_pairs_analyzed | Causal analysis complete |
| 32 | 3493 | resolved_gaps_applied | Per canonical name update emission |

### 7.2 Metrics

| # | Metric Name | Type | Labels | Emitted By | Purpose |
| - | ----------- | ---- | ------ | ---------- | ------- |
| 1 | decision_metrics (CREATE) | counter | tenant_id, target_layer=st_kg_dom | _populate_phase_outputs via metrics_registry | Track entity creation decisions |
| 2 | decision_metrics (REINFORCE) | counter | tenant_id, target_layer=st_kg_dom | _populate_phase_outputs via metrics_registry | Track entity reinforcement decisions |
| 3 | decision_metrics (CREATE) | counter | tenant_id, target_layer=st_kg_edges | _populate_phase_outputs via metrics_registry | Track edge creation decisions |
| 4 | decision_metrics (REINFORCE) | counter | tenant_id, target_layer=st_kg_edges | _populate_phase_outputs via metrics_registry | Track edge reinforcement decisions |

### 7.3 Phase Stats (R4PhaseStats)

R4PhaseStats tracks ~50+ fields across these categories:

| Category | Fields | Purpose |
| -------- | ------ | ------- |
| Extraction | entities_extracted, entities_by_type | NER entity extraction counts |
| Disambiguation | disambiguation_attempts, disambiguation_successes, disambiguation_failures, ambiguous_mentions | Entity resolution tracking |
| Resolution | auto_resolved, flagged_for_review, gaps_emitted, resolved_gaps_applied | Confidence routing outcomes |
| Co-occurrence | co_occurrence_pairs | Hebbian edge discovery |
| Edge Creation | new_edges_created, existing_edges_updated | Edge create/update counts |
| Hebbian | hebbian_edges_strengthened, hebbian_edges_weakened | Adaptive learning tracking |
| Causal | causal_edges_created, causal_pairs_analyzed, causal_edges_by_category | Granger inference outcomes |
| Feedback | edges_boosted, edges_demoted | Edge confidence adjustments |
| Social | social_relationships_extracted, social_relationships_by_type | Social extraction |
| Alias | alias_pairs_compared, alias_candidates_detected, alias_nickname_matches, alias_merges_performed, alias_detection_duration_ms | Alias detection |
| Enrichment | enrichment_new_edges, enrichment_updated_edges, enrichment_edges_by_algorithm, enrichment_updates_by_algorithm, enrichment_duration_ms | GAP-007 enrichment |
| Timing | total_duration_ms, extraction_duration_ms, disambiguation_duration_ms, edge_discovery_duration_ms, social_extraction_duration_ms, causal_inference_duration_ms | Per-step latency |
| Entity Processing | new_entities_created, existing_entities_updated, entities_merged | Entity CRUD counts |

### 7.4 Observability Gaps

| # | Gap | Current State | Required State | Priority |
| - | --- | ------------- | -------------- | -------- |
| 1 | No per-enricher latency tracking | enrichment_duration_ms is aggregate for all 7+1 enrichers | Per-enricher duration fields in R4PhaseStats | P2 |
| 2 | No histogram for entity cluster sizes | Only total counts | Distribution of cluster.observation_count for quality monitoring | P3 |
| 3 | No tracing spans for R4 sub-steps | Structured logs only | OpenTelemetry spans for each of 10 stages for distributed tracing | P2 |
| 4 | Decision metrics not emitted for gap candidates | Only CREATE/REINFORCE tracked | Add GAP_EMITTED decision metric for monitoring gap pipeline health | P2 |

---

## 8. Test Coverage Audit

### 8.1 Existing Tests

| # | Test File | Lines | Test Count | Type | Coverage Target | Pass / Fail | Notes |
| - | --------- | ----- | ---------- | ---- | --------------- | ----------- | ----- |
| 1 | tests/k0/pipelines/p03/test_r4_kg_consolidator.py | 674 | 56 | integration | R4KGConsolidator.run(), full phase execution | PASS | Uses mocked syscalls; covers 10-step pipeline, entity extraction, clustering, disambiguation, social extraction |
| 2 | tests/k0/pipelines/p03/test_r4_entity_extractor.py | 598 | 38 | unit | entity_extractor.filter_and_normalize(), NER family filtering | PASS | Covers TRUSTED/REJECTED/VALIDATED families, head-based priority, span dedup |
| 3 | tests/k0/pipelines/p03/test_r4_disambiguator.py | 519 | 54 | unit | entity_disambiguator.EntityDisambiguator | PASS | Per-type weight testing (PERSON, FAMILY, CONCEPT), semantic opposition detection |
| 4 | tests/k0/pipelines/p03/test_r4_ambiguous_resolver.py | 563 | 25 | unit | ambiguous_resolver.AmbiguousEntityResolver | PASS | 5-priority boost scoring, close_race penalty, threshold routing |
| 5 | tests/k0/pipelines/p03/test_r4_confidence_router.py | 515 | 33 | unit | confidence_router.EntityConfidenceRouter | PASS | AUTO/FLAG/GAP routing, gap batching (50/batch, TTL 24h), outbox pattern |
| 6 | tests/k0/pipelines/p03/test_r4_merge_thresholds.py | 329 | 37 | unit | merge_threshold_learner.AdaptiveMergeThresholds | PASS | Per-type thresholds, learning FP/FN feedback, bounds clamping |
| 7 | tests/k0/pipelines/p03/test_r4_entity_merger.py | 531 | 23 | unit | entity_merger.EntityMerger | PASS | 6-step merge, 7-table cascade, undo via snapshots, MergeStatus transitions |
| 8 | tests/k0/pipelines/p03/test_r4_granger_causality.py | 643 | 29 | unit | granger_causality.GrangerCausalityInference | PASS | Temporal precedence ratio, min_observations guard, causality_threshold |
| 9 | tests/k0/pipelines/p03/test_r4_causality_thresholds.py | 439 | 45 | unit | causality_thresholds.CategoryAwareCausalityThresholds | PASS | 4-tier category classification (Health/Financial/Social/Preference), keyword matching |
| 10 | tests/k0/pipelines/p03/test_r4_edge_demotion.py | 621 | 24 | unit | edge_demotion.CausalEdgeFeedbackProcessor, CausalEdgeStalenessChecker | PASS | Feedback tiers (boost/maintain/lower/demote), 90-day staleness archival |
| 11 | tests/k0/pipelines/p03/test_r4_integration.py | 915 | 26 | integration | Full R4 phase with multi-event batches | PASS | End-to-end: entities+edges+social+causal+enrichment through R4KGConsolidator |
| 12 | tests/k0/modules/consolidation/algorithms/edge_enrichers/test_semantic_similarity.py | 206 | 7 | unit | SemanticSimilarityEnricher | PASS | Threshold, max_edges, self-edge skip, canonical ordering |
| 13 | tests/k0/modules/consolidation/algorithms/edge_enrichers/test_temporal_proximity.py | 94 | 6 | unit | TemporalProximityEnricher | PASS | Window, min_weight, existing edge update |
| 14 | tests/k0/modules/consolidation/algorithms/edge_enrichers/test_contextual.py | 78 | 5 | unit | ContextualEnricher | PASS | Weighted Jaccard, 5 context features |
| 15 | tests/k0/modules/consolidation/algorithms/edge_enrichers/test_emotion_similarity.py | 61 | 4 | unit | EmotionSimilarityEnricher | PASS | Emotion vector cosine, arousal weighting |
| 16 | tests/k0/modules/consolidation/algorithms/edge_enrichers/test_intent_similarity.py | 79 | 5 | unit | IntentSimilarityEnricher | PASS | Complementary intent pairs, INTENT_RELATED edges |
| 17 | tests/k0/modules/consolidation/algorithms/edge_enrichers/test_transitive_closure.py | 130 | 4 | unit | TransitiveClosureEnricher | PASS | 2-hop paths, attenuation factor, noisy-or fusion |
| 18 | tests/k0/modules/consolidation/algorithms/edge_enrichers/test_bayesian_causal.py | 211 | 9 | unit | BayesianCausalEnricher | PASS | Bayesian posterior, prior=0.1, threshold, evidence fusion |
| 19 | tests/k0/modules/consolidation/algorithms/edge_enrichers/test_weight_normalization.py | 224 | 10 | unit | EdgeWeightNormalizer | PASS | softmax/sum_to_one/cap strategies, per-entity normalization |

**Total: 19 test files, 8,430 lines, 441 tests**

### 8.1.1 Per-File Test Class Breakdown

#### test_r4_kg_consolidator.py (56 tests, 674 lines)

| Class | Line | Test Count | Covers |
| ----- | ---- | ---------- | ------ |
| TestR4Config | 96 | 2 | Default and custom config values |
| TestR4PhaseStats | 132 | 2 | Default stats, to_dict serialization |
| TestKGUpdate | 166 | 2 | CREATE_ENTITY and CREATE_EDGE update creation |
| TestEntityCluster | 206 | 1 | Cluster creation with all fields |
| TestR4KGConsolidatorLifecycle | 233 | 4 | phase_id, idempotency_key, factory functions |
| TestR4SkipConditions | 269 | 4 | Skip on empty events, all processed, no content, valid events |
| TestHebbianCoOccurrence | 318 | 3 | Confidence formula min/max/progression |
| TestR4PhaseExecution | 367 | 3 | Full phase execution with mocked syscalls |
| TestR4IntegrationWithAlgorithms | 450 | 3 | Confidence router, merge thresholds, entity merger dependencies |
| TestR4PhaseOutputs | 477 | 4 | KG entity/edge creation, edge updates, gap candidates |
| TestEdgeTypeInference | 583 | 12 | FAMILY/FRIEND/COLLEAGUE type inference, priority ordering, mixed relations |
| TestEntityPriorityThreshold | 740 | 2 | Min entity priority default and custom |
| TestCanonicalNameSelection | 759 | 7 | Single/empty/common/proper_case/longer/frequency/real_world canonical name selection |
| TestTemporalEdgeTypes | 814 | 7 | Temporal edge config defaults, custom settings, threshold symmetry/bounds |

#### test_r4_entity_extractor.py (38 tests, 598 lines)

| Class | Line | Test Count | Covers |
| ----- | ---- | ---------- | ------ |
| TestLabelMapping | 82 | 8 | NER family kinship, general person, temporal date/time, org, GPE, unknown, family event mapping |
| TestThreeHeadMerging | 197 | 4 | Three-head merge, empty/none/partial head handling |
| TestNicknameNormalization | 266 | 6 | wifey->wife, kiddo->child, hubby->husband, mom->mother, punctuation removal, space collapse |
| TestDeduplication | 341 | 4 | Highest priority kept, normalized text dedup, different types dedup, metrics tracking |
| TestJsonSerialization | 426 | 2 | to_entities_json format and empty handling |
| TestMetricsTracking | 470 | 4 | Metrics by source head, by KG type, reset, processing time |
| TestDatabaseIntegration | 543 | 2 | Database-backed extraction tests |
| TestFactoryFunction | 581 | 2 | Factory returns instance, returns new instance |
| TestExtractedEntityDataclass | 601 | 1 | to_dict serialization |
| TestFullResultExtraction | 634 | 2 | Dict-style and object-style full result extraction |
| TestUniversalGarbageFiltering | 689 | 4 | Garbage words filtered from ner_general, temporal, trusted ner_family, common verbs |

#### test_r4_disambiguator.py (54 tests, 519 lines)

| Class | Line | Test Count | Covers |
| ----- | ---- | ---------- | ------ |
| TestDisambiguationWeights | 36 | 5 | Valid weights, sum validation, negative rejection, to_dict, frozen |
| TestDefaultWeightMatrix | 73 | 9 | PERSON, FAMILY_MEMBER, CONCEPT, PLACE, LOCATION, ORGANIZATION, EVENT, unknown type, case-insensitive |
| TestFuzzyStringMatch | 146 | 8 | Exact, case-insensitive, typo, reorder, partial, empty, algorithm tracking, abbreviation |
| TestCosineSimilarity | 208 | 5 | Identical, orthogonal, opposite, zero vector, numpy arrays |
| TestCombinedScore | 257 | 3 | Weighted score, concept embedding-heavy, family member balanced |
| TestShouldMerge | 339 | 4 | Above threshold, below threshold, custom threshold, metrics tracking |
| TestThreshold | 418 | 3 | Default, set, invalid rejection |
| TestLearnedWeights | 448 | 4 | Override, preserve others, set weights, get all weights |
| TestLoadFromDatabase | 499 | 3 | Database loading tests |
| TestFactory | 561 | 2 | Factory default and with params |
| TestUtilityFunctions | 586 | 5 | Clamp below/above/in-range, normalize weights, normalize zero |
| TestDisambiguationBreakdown | 621 | 1 | Breakdown to_dict serialization |
| TestMetrics | 649 | 2 | Metrics reset, algorithm wins tracking |

#### test_r4_ambiguous_resolver.py (25 tests, 563 lines)

| Class | Line | Test Count | Covers |
| ----- | ---- | ---------- | ------ |
| TestConfiguration | 151 | 5 | Default thresholds, custom thresholds, invalid validation, factory, factory with config |
| TestEdgeCases | 187 | 2 | No candidates returns GAP, single candidate auto-resolves |
| TestPriorityHierarchy | 224 | 5 | P1 recency, P2 co-occurring, P3 location, P4 temporal, P5 frequency boosts |
| TestConfidenceBands | 363 | 3 | Auto-resolved above, flagged middle, gap below threshold |
| TestCloseRacePenalty | 455 | 2 | Penalty applied when gap small, no penalty when gap large |
| TestMetrics | 523 | 3 | Increment on resolution, outcome counts, boost usage tracking |
| TestAsyncOperations | 572 | 2 | Async operation tests |
| TestDataClasses | 639 | 3 | CandidateEntity, EventContext, ResolutionResult to_dict |

#### test_r4_confidence_router.py (33 tests, 515 lines)

| Class | Line | Test Count | Covers |
| ----- | ---- | ---------- | ------ |
| TestConfiguration | 102 | 5 | Default thresholds, custom thresholds, invalid validation, factory, factory with config |
| TestBandDetermination | 138 | 6 | AUTO at/above threshold, FLAG at/between, GAP below/at zero |
| TestRouting | 177 | 5 | Auto no gap, flag no gap, gap generates payload, truncates candidates, serialization |
| TestGapEmission | 288 | 4 | Gap emission tests with outbox pattern |
| TestBatchEmission | 377 | 4 | Batch emission (50/batch, TTL 24h) tests |
| TestMetrics | 477 | 4 | Increment on route, band counts, distribution, avg confidence |
| TestQuickBand | 552 | 3 | Quick band auto/flag/gap |
| TestGapPayloadSerialization | 576 | 2 | to_dict and from_dict |
| TestThresholdsGetter | 624 | 2 | Get band thresholds, custom thresholds returned |

#### test_r4_merge_thresholds.py (37 tests, 329 lines)

| Class | Line | Test Count | Covers |
| ----- | ---- | ---------- | ------ |
| TestDefaultThresholds | 65 | 11 | FAMILY_MEMBER, PERSON, CONCEPT, PLACE, LOCATION, ORGANIZATION, THING/OBJECT, EVENT, TEMPORAL, unknown, another unknown |
| TestShouldMerge | 128 | 6 | Above/below/exact threshold, family strict, concept lenient, margin calculation |
| TestThresholdAdjustment | 177 | 8 | Rejected raises, split raises more, missed lowers, confirmed no change, clamped max/min, string signal, internal state update |
| TestLearnedOverrides | 253 | 2 | Override applied, non-overridden uses default |
| TestPersistence | 272 | 2 | Persist and load from database |
| TestFactory | 328 | 1 | Factory function |
| TestThresholdBoundsDataclass | 344 | 2 | Bounds creation, default structure |
| TestMergeDecisionDataclass | 386 | 1 | to_dict serialization |
| TestMetrics | 406 | 2 | Initialized, updated on decision |

#### test_r4_entity_merger.py (23 tests, 531 lines)

| Class | Line | Test Count | Covers |
| ----- | ---- | ---------- | ------ |
| TestMergeValidation | 117 | 4 | Validation: same type, different IDs, not already merged, type mismatch rejection |
| TestPrimarySelection | 209 | 3 | Higher observation wins, tie-break by first_mentioned, equal defaults |
| TestCascadeUpdates | 274 | 4 | 7-table cascade update tests |
| TestArchival | 366 | 2 | Secondary entity archival status |
| TestAuditLogging | 393 | 2 | Merge audit log creation, st_entity_merges INSERT |
| TestReverseMerge | 421 | 3 | Full undo, snapshot restoration, cascade reversal |
| TestMergeHistory | 501 | 1 | Entity merge chain retrieval |
| TestFactory | 533 | 1 | Factory function |
| TestDataClasses | 547 | 5 | EntitySnapshot to_dict/from_dict, CascadeCounts total/to_dict, MergeResult to_dict |
| TestMetrics | 627 | 1 | Merger metrics tracking |

#### test_r4_granger_causality.py (29 tests, 643 lines)

| Class | Line | Test Count | Covers |
| ----- | ---- | ---------- | ------ |
| TestComputeTemporalPrecedence | 134 | 5 | A before B, B before A, simultaneous, mixed, empty observations |
| TestInferCausalDirection | 259 | 6 | No observations, strong precedence, weak precedence, reverse direction, exactly at threshold, custom config |
| TestPersistCausalEdges | 416 | 4 | Causal edge persistence tests |
| TestAnalyzeCooccurrencePairs | 536 | 3 | Batch pair analysis tests |
| TestCausalityConfigValidation | 636 | 6 | Valid config, invalid min_observations, threshold low/high, temporal window, simultaneous threshold |
| TestUtilityFunctions | 685 | 3 | ULID uniqueness/format, now_ms |
| TestCausalPatternExamples | 717 | 3 | Real-world: alarm->wakeup, coffee->work, rain-stayhome (no causality) |

#### test_r4_causality_thresholds.py (45 tests, 439 lines)

| Class | Line | Test Count | Covers |
| ----- | ---- | ---------- | ------ |
| TestCausalCategoryClassifier | 102 | 12 | Health (medical/doctor/exercise), Financial (budget/spending/payment), Social (family/call), Preference default/generic, priority Health>Social, Financial>Social |
| TestThresholdDefaults | 186 | 5 | Health=0.85, Financial=0.80, Social=0.70, Preference=0.65, get_all |
| TestShouldCreateCausalEdge | 226 | 5 | Above/below/exactly at threshold, Social lower, Preference lowest |
| TestAdjustThreshold | 303 | 5 | Wrong prediction, user rejects, missed causation, confirmed no change, unknown signal |
| TestThresholdClamping | 368 | 3 | Clamped max, clamped min, preference clamped to bounds |
| TestPersistAndLoad | 416 | 3 | Persist and load from database tests |
| TestLearnedThresholdOverride | 475 | 2 | Learned overrides default, adjustment stores learned |
| TestCategoryThresholdBounds | 499 | 3 | Valid bounds, invalid min>max, invalid default outside |
| TestUtilityFunctions | 525 | 3 | ULID uniqueness/format, now_ms |
| TestCategoryKeywords | 554 | 3 | Health/Financial/Social keywords exist |

#### test_r4_edge_demotion.py (24 tests, 621 lines)

| Class | Line | Test Count | Covers |
| ----- | ---- | ---------- | ------ |
| TestAccuracyBasedActions | 251 | 4 | >90% boost, 70-90% maintain, 50-70% lower, <50% demote to CORRELATED |
| TestFeedbackRecording | 412 | 2 | Feedback record creation and storage |
| TestAccuracyComputation | 452 | 3 | Accuracy calculation from feedback records |
| TestStalenessChecking | 513 | 3 | 90-day staleness detection and archival |
| TestEdgeNotFound | 583 | 1 | Missing edge handling |
| TestConfidenceClamping | 609 | 2 | Confidence clamped to 0.0-1.0 range |
| TestUtilityFunctions | 668 | 3 | ULID uniqueness/format, now_ms |
| TestConfigurationConstants | 697 | 3 | Accuracy thresholds, adjustment amounts, staleness days |
| TestDemotionResult | 722 | 1 | Result dataclass fields |
| TestEdgeStatus | 755 | 1 | EdgeStatus enum values |
| TestDemotionAction | 771 | 1 | DemotionAction enum values |

#### test_r4_integration.py (26 tests, 915 lines)

| Class | Line | Test Count | Covers |
| ----- | ---- | ---------- | ------ |
| TestEntityExtractionToResolutionPipeline | 173 | 3 | Extractor produces entities, disambiguation output flows, full extraction-to-resolution chain |
| TestResolutionToGapEmissionPipeline | 325 | 3 | High confidence auto-resolves, medium confidence flags, low confidence emits gap |
| TestClusteringToEdgeCreationPipeline | 442 | 3 | Co-occurring entities create edge, Hebbian with merge threshold, phase discovers edges from clusters |
| TestEdgeToGrangerCausalityPipeline | 600 | 4 | Granger infers direction, with category thresholds, phase creates causal edges, from update edges |
| TestCausalEdgeToFeedbackPipeline | 797 | 4 | Wrong prediction adjusts, correct lowers, staleness checker init, different thresholds |
| TestR4PhaseEndToEnd | 876 | 4 | Full end-to-end multi-event phase execution |
| TestStatsTrackingIntegration | 983 | 3 | Stats tracking across full execution |
| TestErrorHandlingIntegration | 1052 | 2 | Error handling and recovery integration |

#### Edge Enricher Tests (50 tests, 1,083 lines across 8 files)

| File | Tests | Lines | Covers |
| ---- | ----- | ----- | ------ |
| test_semantic_similarity.py | 7 | 206 | Threshold, max_edges, self-edge skip, canonical ordering, new/update edge creation |
| test_temporal_proximity.py | 6 | 94 | Window filtering, min_weight, exponential decay, existing edge update |
| test_contextual.py | 5 | 78 | Weighted Jaccard, 5 context features, threshold, new edge creation |
| test_emotion_similarity.py | 4 | 61 | Emotion vector cosine, arousal weighting, threshold, edge creation |
| test_intent_similarity.py | 5 | 79 | Complementary intent pairs, INTENT_RELATED edges, profile construction |
| test_transitive_closure.py | 4 | 130 | 2-hop paths, attenuation factor, noisy-or fusion, max_edges |
| test_bayesian_causal.py | 9 | 211 | Bayesian posterior, prior=0.1, threshold, evidence fusion, temporal precedence |
| test_weight_normalization.py | 10 | 224 | softmax/sum_to_one/cap strategies, per-entity normalization, hub prevention |

### 8.2 Coverage Gaps

| # | Gap | What's Untested | Risk Level | Proposed Test | Test Type |
| - | --- | --------------- | ---------- | ------------- | --------- |
| 1 | No alias_detector test file | AliasDetector 4-signal scoring, FirstNameDatabase, AliasType classification | P1 | test_r4_alias_detector.py: test_string_signal, test_embedding_signal, test_nickname_signal, test_co_occurrence_signal, test_threshold_routing | unit |
| 2 | No subtype_classifier test file | PatternSubtype/EntitySubtype keyword-based classification (30+ subtypes) | P2 | test_r4_subtype_classifier.py: test_pattern_subtypes, test_entity_subtypes, test_unknown_fallback | unit |
| 3 | No observation_context test file | ObservationContext construction from events | P2 | test_r4_observation_context.py: test_context_build, test_missing_fields_defaults | unit |
| 4 | No concurrent batch test | Two R4 cycles processing overlapping entity sets | P1 | test_r4_concurrent_batches: run 2 parallel R4 cycles, assert no entity_id collision | integration |
| 5 | No DB failure recovery test | Full R4 behavior when st_kg_dom/st_kg_edges are unreachable | P1 | test_r4_db_unavailable: mock syscalls raising, assert phase completes with all CREATE | integration |
| 6 | No large batch stress test | R4 with >1000 entities across >100 events | P2 | test_r4_large_batch: 100 events, 1000+ entities, measure latency and memory | performance |
| 7 | Edge enricher fusion scoring untested end-to-end | Multiple enrichers producing overlapping edges -> fusion.py weighted_sum/noisy_or | P1 | test_r4_enrichment_fusion: 3+ enrichers produce same edge pair, verify fusion correctness | integration |
| 8 | Social relationship phase transitions | FORMING->STABLE->DEEPENING->COOLING lifecycle across multiple cycles | P2 | test_r4_social_phase_lifecycle: simulate 5 cycles with varying sentiment, verify phase transitions | integration |
| 9 | Granger causality with production thresholds | Tests use min_observations=1 (override), production uses 5 | P0 | test_r4_granger_production_thresholds: use default config, verify pairs with <5 observations are skipped | unit |

### 8.3 Test Infrastructure Needs

| # | Need | Current State | Required State | Blocking Epic? |
| - | ---- | ------------- | -------------- | -------------- |
| 1 | Shared R4 test fixtures for entity/edge data | Each test file creates own entity/edge objects inline | Shared conftest.py with factory fixtures (make_entity, make_edge, make_cluster) | no |
| 2 | Mock syscalls fixture with configurable failure modes | Tests use ad-hoc AsyncMock setups | Shared MockSyscalls class with DB failure injection | no |
| 3 | Production-config test profile | Tests use R4Config with granger_min_observations=1 | Separate test config (testing) vs production config profile | Epic 5.5 |

---

## 9. Dependency Map

### 9.1 Upstream (what R4 needs)

| # | Dependency | Type | Status | Owner Milestone | Gap if Missing |
| - | ---------- | ---- | ------ | --------------- | -------------- |
| 1 | P02 NER entities (ner_entities_json) | pipeline output | ready | M3 | No entities to extract; R4 produces empty results |
| 2 | P02 UltraBERT relations (extracted_relations_json) | pipeline output | ready | M3 | No relation types for Hebbian learner; edges lack typed relations |
| 3 | P02 sentiment/emotion (sentiment, emotions_json) | pipeline output | ready | M3 | Social emotional_valence defaults to neutral; no emotion enrichment |
| 4 | P02 social context (participants_json, social_context, social_intimacy) | pipeline output | ready | M3 | No social relationship extraction; r4_social_entities always empty |
| 5 | P02 temporal resolution (timestamp) | pipeline output | ready | M3 | Granger causality cannot compute temporal precedence; causal edges skipped |
| 6 | kg_candidates_fuzzy_query syscall | syscall | ready | M4 | Entity disambiguation falls back to confidence routing (no DB candidate matching) |
| 7 | kg_entities_lookup syscall | syscall | ready | M4 | All entities created as new (potential duplicates until R7 ON CONFLICT) |
| 8 | kg_edges_lookup syscall | syscall | ready | M4 | All edges created as new (potential duplicates until R7 ON CONFLICT) |
| 9 | get_pool syscall | syscall | ready | M4 | Cannot query st_learning_queue for resolved gaps |
| 10 | st_kg_dom table | table | ready | M4 | Entity storage not available |
| 11 | st_kg_edges table | table | ready | M4 | Edge storage not available |
| 12 | st_learning_queue table | table | ready | M4 | Gap pipeline disabled |
| 13 | st_social table | table | ready | M4 | Social relationship storage not available |
| 14 | metrics_registry | service | ready | M4 | Decision metrics not emitted (non-blocking) |
| 15 | rapidfuzz library | library | ready | M3 | String similarity in alias_detector and entity_disambiguator unavailable |
| 16 | numpy library | library | ready | M3 | Embedding operations in alias_detector, disambiguator unavailable |
| 17 | R0-R3 phase outputs (batch selection, scoring, episodes, dedup) | pipeline output | ready | M5 | R4 receives events from P03EventState but prior phase enrichments missing |
| 18 | R7 truth writer | pipeline phase | ready | M5 | r4_* outputs not written to database |

### 9.2 Downstream (what depends on R4)

| # | Dependent | Type | How Used | Impact if Changed | Owner Milestone |
| - | --------- | ---- | -------- | ----------------- | --------------- |
| 1 | R5 scoring/ranking | pipeline | Consumes r4_new_entities, r4_updated_entities for scoring | Entity schema change breaks R5 scoring | M5 |
| 2 | R6 social writer | pipeline | Consumes r4_social_entities for st_social writes | SocialRelationship schema change breaks R6 | M5 |
| 3 | R7 truth writer | pipeline | Consumes r4_new_entities, r4_updated_entities, r4_new_edges, r4_updated_edges, r4_gap_candidates for DB writes | Any r4_* output schema change breaks R7 | M5 |
| 4 | P06 gap resolution pipeline | pipeline | Consumes st_learning_queue gap entries produced by R4 via R7 | GapCandidate schema change breaks P06 | M6+ |
| 5 | R2 episode alignment | pipeline | R4._update_episode_entity_ids writes cluster entity_ids back to episode phase outputs | Episode entity_id format change breaks R2 alignment | M5 |

### 9.3 External Dependencies

| # | Dependency | Version | Purpose | License | Pinned? | Upgrade Risk |
| - | ---------- | ------- | ------- | ------- | ------- | ------------ |
| 1 | rapidfuzz | >=3.0 | String similarity (Levenshtein, token_sort_ratio, partial_ratio) for alias detection and entity disambiguation | MIT | no (range) | low |
| 2 | numpy | >=1.24 | Embedding vector operations (cosine similarity) in alias_detector, entity_disambiguator | BSD-3-Clause | no (range) | low |
| 3 | asyncpg | >=0.29 | Async PostgreSQL connection pool (get_pool -> st_learning_queue direct query) | Apache-2.0 | no (range) | low |

---

## 10. Performance Baseline

### 10.1 Current Benchmarks

> **No formal R4-specific benchmarks exist.** Performance is inferred from test execution times and code analysis.

| # | Operation | Dataset Size | p50 (est.) | p95 (est.) | Throughput (est.) | Memory Peak (est.) | Notes |
| - | --------- | ------------ | ---------- | ---------- | ----------------- | ------------------ | ----- |
| 1 | Full R4 phase (10 steps) | 20 events, ~100 entities | ~200ms | ~500ms | ~5 cycles/s | ~50MB | Estimate from integration tests; dominated by DB queries |
| 2 | Entity extraction (step 1) | 20 events | ~5ms | ~10ms | N/A | ~5MB | JSON parsing + filtering; CPU-bound |
| 3 | Entity disambiguation (step 3) | 50 clusters | ~50ms | ~200ms | N/A | ~10MB | Per-cluster DB fuzzy query dominates |
| 4 | Edge enrichment (step 7) | 50 entities, 100 edges | ~100ms | ~300ms | N/A | ~20MB | Sequential 7 enrichers + normalizer |
| 5 | Granger causality (step 6) | 20 edge pairs | ~10ms | ~30ms | N/A | ~5MB | O(n^2) pairs but small n typical |
| 6 | Alias detection (step 2.5) | 50 clusters, ~10 types | ~20ms | ~60ms | N/A | ~10MB | O(n^2) pairwise within each type; dominated by embedding lookups |
| 7 | Social extraction (step 5.5) | 20 events, ~5 PERSON entities | ~10ms | ~30ms | N/A | ~5MB | O(e*p) events*people; JSON parsing + aggregation |
| 8 | Cluster building (step 2) | 100 entities | ~2ms | ~5ms | N/A | ~5MB | O(e) grouping; in-memory only; resolved gap DB read adds ~50ms |
| 9 | Output population (step 8) | 50 entities, 100 edges, 10 social | ~5ms | ~15ms | N/A | ~10MB | Envelope assembly + decision metric emission |

### 10.2 Algorithm Complexity Analysis

| # | Algorithm | Time Complexity | Space Complexity | Scaling Factor | Growth Pattern | Critical Threshold |
| - | --------- | --------------- | ---------------- | -------------- | -------------- | ------------------ |
| 1 | Entity Extraction (JSON parse + filter) | O(E * N) | O(E * N) | E=events, N=avg entities/event | Linear | 1000 events * 50 entities = 50K ops |
| 2 | Entity Clustering (type:name grouping) | O(N_total) | O(N_total) | N_total = total extracted entities | Linear | Unbounded; hash map growth |
| 3 | Alias Detection (pairwise per type) | O(sum(n_t^2)) | O(n_t * 4_signals) | n_t = entities per type | Quadratic per type | PERSON type with 100+ entities = 10K pair comparisons |
| 4 | Entity Disambiguation (DB + scoring) | O(C * DB_RTT) | O(C * K) | C=clusters, K=candidates/cluster (max 10) | Linear in C * DB latency | 100 clusters * 20ms/query = 2000ms (bottleneck) |
| 5 | Ambiguous Resolution (5-priority scoring) | O(C * M) | O(C) | C=clusters, M=mentions/cluster | Linear | Not a bottleneck |
| 6 | Hebbian Learning (pair enumeration) | O(sum(E_i^2)) | O(P) | E_i=entities per event, P=unique pairs | Quadratic per event | Events with 20+ entities = 400 pairs/event |
| 7 | Granger Causality (all-pairs temporal) | O(P * T^2) | O(P) | P=edge pairs, T=timestamps/pair | Quadratic in observations | 100 pairs * 100 obs = 1M comparisons |
| 8 | Semantic Similarity Enricher | O(N^2) | O(N * D) | N=entities, D=embedding dim | Quadratic | 100 entities = 10K cosine comparisons |
| 9 | Temporal Proximity Enricher | O(N^2) | O(N) | N=entities with timestamps | Quadratic | 100 entities = 10K timestamp comparisons |
| 10 | Contextual/Emotion/Intent Enrichers | O(N^2) each | O(N) each | N=entities with context | Quadratic | Same as above; 3 enrichers * 10K = 30K |
| 11 | Transitive Closure | O(N * D^2) | O(N * D) | N=entities, D=avg degree | Cubic worst case | High-degree hub entities (D>20) explode |
| 12 | Weight Normalization (softmax) | O(E_out) per entity | O(E_out) | E_out=outgoing edges/entity | Linear per entity | Hub entities with 100+ edges |
| 13 | Social Extraction (relation parsing) | O(E * P) | O(P^2) | E=events, P=unique PERSON pairs | Linear in events | Not a bottleneck |

### 10.3 Per-Step Latency Budget (20-event baseline)

| Step | Operation | Contract Latency | Est. CPU (ms) | Est. DB (ms) | Est. Total (ms) | % of Budget | File:Line |
| ---- | --------- | ---------------- | ------------- | ------------ | --------------- | ----------- | --------- |
| 1 | Extract entities | 150ms (entity_extractor.v1) | 5 | 0 | 5 | 1% | r4_kg_consolidator.py:1099 |
| 2 | Build clusters | N/A | 2 | 50 | 52 | 10.4% | r4_kg_consolidator.py:1338 |
| 2.5 | Detect aliases | N/A | 20 | 0 | 20 | 4% | r4_kg_consolidator.py:1461 |
| 3 | Resolve entities | N/A | 10 | 100 | 110 | 22% | r4_kg_consolidator.py:1589 |
| 3.5 | Build context map | N/A | 3 | 0 | 3 | 0.6% | r4_kg_consolidator.py:1279 |
| 4 | Process entity clusters | N/A | 5 | 50 | 55 | 11% | r4_kg_consolidator.py:1823 |
| 5 | Discover relationships | 100ms (hebbian_learner.v1) | 10 | 50 | 60 | 12% | r4_kg_consolidator.py:1936 |
| 5.5 | Extract social | 100ms (relationship_builder.v1) | 10 | 0 | 10 | 2% | r4_kg_consolidator.py:2588 |
| 6 | Infer causal | 200ms (causal_inference.v1) | 10 | 0 | 10 | 2% | r4_kg_consolidator.py:2200 |
| 7 | Edge enrichment (7 sequential) | N/A | 100 | 100 | 200 | 40% | r4_kg_consolidator.py:~800 |
| 8 | Populate outputs | N/A | 5 | 0 | 5 | 1% | r4_kg_consolidator.py:3147 |
| **TOTAL** | | | **180** | **350** | **530** | **106%** | Over 500ms p95 target |

> **Analysis**: DB operations dominate at 66% of total latency. The largest single contributors are:
>
> 1. Entity resolution (step 3): 100ms DB from per-cluster fuzzy queries (batchable)
> 2. Edge enrichment (step 7): 100ms DB from kg_edges_lookup + 100ms CPU from 7 sequential enrichers (parallelizable)
> 3. Entity cluster processing (step 4): 50ms DB from kg_entities_lookup full scan (filterable)

### 10.4 Contract Latency Cross-Reference

| Contract | Declared Latency | Step | Actual Step Estimate | Delta | Notes |
| -------- | ---------------- | ---- | -------------------- | ----- | ----- |
| entity_extractor.v1 | 150ms p95 | 1 | 10ms | -140ms | Contract is conservative; extraction is pure JSON parse, no model inference in R4 |
| hebbian_learner.v1 | 100ms p95 | 5 | 60ms | -40ms | Within budget; DB lookup dominates |
| causal_inference.v1 | 200ms p95 | 6 | 30ms | -170ms | Contract is conservative; Granger is CPU-only with small datasets |
| relationship_builder.v1 | 100ms p95 | 5.5 | 30ms | -70ms | Within budget; CPU-only JSON parsing |
| **R4 total (sum of contracts)** | **550ms** | all | **530ms** | **-20ms** | Barely within contract sum; enrichment not covered by any contract |

### 10.5 Known Bottlenecks

| # | Bottleneck | Location (File:Line) | Cause | Measured Impact | Proposed Fix | Priority |
| - | ---------- | -------------------- | ----- | --------------- | ------------ | -------- |
| 1 | Sequential edge enrichers | r4_kg_consolidator.py:~800 | 7 enrichers + normalizer run in sequence; each loops over all entities | Adds ~100ms per enricher = ~700ms total for large batches | Parallelize independent enrichers (BayesianCausal, Contextual, Emotion, Intent, Semantic, Temporal are independent) | P1 |
| 2 | kg_edges_lookup called twice | r4_kg_consolidator.py:819 + enrichment block | Two separate full-table reads of st_kg_edges per cycle | Double read latency (~200ms * 2 = ~400ms for large KG) | Cache first read and reuse for enrichment | P2 |
| 3 | kg_entities_lookup loads all entities | r4_kg_consolidator.py:1856 | Loads every entity for tenant+space into memory | Memory O(n) where n = total entities; unbounded for large tenants | Filter by entity_type or name prefix at query level | P3 |
| 4 | Per-cluster fuzzy query | r4_kg_consolidator.py:1657 | Each entity cluster issues a separate DB roundtrip for disambiguation | O(c) DB queries where c = cluster count; ~50ms * c; 100 clusters = 5000ms | Batch fuzzy queries or pre-fetch candidate set | P2 |
| 5 | Granger O(n^2) pair enumeration | granger_causality.py:~150 | All-pairs comparison for temporal precedence | Quadratic in edge count; 100 edges = 10K pairs; 500 edges = 250K pairs | Pre-filter by temporal proximity before enumeration | P3 |
| 6 | Alias detection O(n^2) per type | alias_detector.py:~614 | Pairwise comparison within each entity type group | 50 PERSON entities = 1225 pairs * 4 signals = 4900 signal evaluations | Skip pairs with <0.3 string similarity (fast pre-filter) | P3 |
| 7 | Transitive closure quadratic per entity | transitive_closure.py:~70 | 2-hop neighbor enumeration for high-degree entities | Hub entity with degree 30 = 900 2-hop paths | Limit degree to max_degree=20 before enumeration | P3 |

### 10.6 Scaling Projections

| Scenario | Events | Est. Entities | Est. Edges | Est. R4 Latency | Est. Memory | Feasible? |
| -------- | ------ | ------------- | ---------- | --------------- | ----------- | --------- |
| Small family (dev) | 20 | 50-100 | 100-200 | ~500ms | ~50MB | yes |
| Medium family (typical) | 100 | 200-500 | 500-1K | ~2000ms | ~100MB | yes (with enricher parallelization) |
| Large family (power user) | 500 | 1K-2K | 2K-5K | ~8000ms | ~256MB | marginal (needs batched fuzzy queries) |
| Extended family (max) | 1000 | 5K-10K | 10K-50K | ~30s+ | ~1GB+ | no (needs pagination, streaming enrichment) |

> **Scaling wall**: At ~500 entities, the O(n^2) enrichers become the bottleneck (250K pair comparisons).
> At ~1000 entities, per-cluster DB queries become the bottleneck (1000 * 20ms = 20s).
> **Required for production**: Batch fuzzy queries (P2), enricher parallelization (P1), entity pre-filtering (P3).

### 10.7 Performance Targets

| # | Operation | Target p95 | Target Throughput | Target Memory | Acceptance Criteria |
| - | --------- | ---------- | ----------------- | ------------- | ------------------- |
| 1 | Full R4 phase (20 events) | < 500ms | > 2 cycles/s | < 100MB | Integration test with 20 events completes within budget |
| 2 | Full R4 phase (100 events) | < 2000ms | > 0.5 cycles/s | < 256MB | Stress test with 100 events completes within budget |
| 3 | Edge enrichment (parallel) | < 200ms | N/A | < 50MB | After parallelization, 7 enrichers complete within single enricher's time |
| 4 | Entity disambiguation | < 100ms total | N/A | < 20MB | Batch fuzzy query reduces per-cluster roundtrips to single batch query |
| 5 | Full R4 phase (500 events) | < 5000ms | > 0.2 cycles/s | < 512MB | Stress test with batched queries and parallel enrichers |
| 6 | Alias detection (100 entities/type) | < 100ms | N/A | < 20MB | Pre-filter reduces pair count by 80%+ |

---

## 11. Gap Analysis & Enhancement Register

### 11.1 Functional Gaps

| # | Gap ID | Gap Description | Current State | Desired State | Severity | Proposed Fix | Related ADR |
| - | ------ | --------------- | ------------- | ------------- | -------- | ------------ | ----------- |
| 1 | FG-001 | Granger causality uses testing overrides in default config | R4Config: granger_min_observations=1, granger_precedence_threshold=0.60 (vs algorithm defaults 5/0.75) | Production config with min_observations=5, threshold=0.75; separate test profile | P0 | Create R4ProductionConfig and R4TestConfig; R4Config inherits from production by default | none |
| 2 | FG-002 | AliasDetector uses string-only similarity for nicknames | FirstNameDatabase has 80+ hardcoded nickname mappings; no semantic alias detection | Semantic alias detection using embeddings (e.g., "Bob" and "Robert" via embedding proximity) | P2 | Add embedding signal to alias scoring (5th signal with configurable weight) | none |
| 3 | FG-003 | P06 gap resolution pipeline may not exist | ConfidenceRouter emits gap candidates to st_learning_queue but P06 is not implemented | P06 consumes st_learning_queue gaps and resolves via human-in-the-loop or automated rules | P1 | P06 implementation (separate epic); R4 can operate without it (gaps accumulate) | none |
| 4 | FG-004 | 90-day staleness check too aggressive for seasonal patterns | CausalEdgeStalenessChecker archives edges not seen in 90 days | Configurable staleness per category (Health=90d, Social=180d, Seasonal=365d) | P2 | Add per-category staleness_days to CausalEdgeStalenessConfig | none |
| 5 | FG-005 | Social extraction lacks multi-cycle aggregation | Each cycle extracts social relationships independently; no cross-cycle relationship history | Social relationships accumulate across cycles with proper merge semantics | P2 | R6 social writer should UPSERT with aggregation logic (observation_count, sentiment averaging) | none |
| 6 | FG-006 | Edge weight normalizer ignores enricher ordering effects | Normalizer runs last but enricher output order affects intermediate weights | Order-independent normalization or explicit enricher priority | P3 | Document enricher ordering contract; or apply normalization per-enricher then final fusion | none |
| 7 | FG-007 | No entity deduplication across tenants | Entity resolution is tenant-scoped; same real-world entity in different tenants creates duplicates | Cross-tenant entity linking for shared family members | P3 | Cross-tenant merge via global entity registry (future milestone) | none |
| 8 | FG-008 | MW v2 social_intimacy_level not used for edge weighting | R4 receives social_intimacy from P02 but only stores it on SocialRelationship; not used in Hebbian/enrichment edge weights | High-intimacy FAMILY edges should be boosted; low-intimacy should be dampened | P2 | Integrate intimacy level into HebbianLearner importance factor and contextual enricher | none |
| 9 | FG-009 | MW v2 narrative_thread_id not used for co-occurrence | R4 co-occurrence is purely temporal (same batch); events in same narrative thread are not distinguished from unrelated events | Same narrative thread = stronger co-occurrence signal; different threads within same batch should be separated | P2 | Add narrative_thread_id to co-occurrence grouping in step 5 (Hebbian learning) | none |
| 10 | FG-010 | MW v2 identity_relevance not used for merge confidence | Self-referential entities (identity_relevance > 0.8) have same merge logic as third-party entities | Self-referential entities should have boosted merge confidence; splitting self-identity is high-cost error | P2 | Boost disambiguation confidence by identity_relevance * 0.15 in AmbiguousEntityResolver | none |
| 11 | FG-011 | MW v2 elaboration_depth not used for extraction confidence | Shallow mentions (elaboration_depth < 0.3) get same confidence as deeply discussed entities | High elaboration_depth should boost NER confidence; low should reduce it to prevent false positives | P3 | Scale entity extraction confidence by elaboration_depth factor in_extract_entities | none |

### 11.2 Contract Gaps

| # | Contract | Section / Field | Gap Detail | Current Contract Content | Required Addition | Impact | Fix |
| - | -------- | --------------- | ---------- | ------------------------ | ----------------- | ------ | --- |
| 1 | consolidation.entity_extractor.v1.yaml | output_schema | Missing alias_candidates output field | output: entities (List[ExtractedEntity]) only | Add alias_candidates: List[AliasCandidate] with fields: primary_name, secondary_name, alias_score, alias_type, signals_used | Alias detection results not captured in contract | Add field to YAML output_schema |
| 2 | consolidation.hebbian_learner.v1.yaml | config | Missing anti_hebbian_rate and decay_rate config fields | config: temporal_window=3600, learning_rate=0.01, decay_factor=0.995, max_edges_per_event=50 | Add anti_hebbian_rate: 0.15, decay_rate: 0.01 (per day), prune_threshold: 0.05, correction_multiplier: 1.3 | Contract does not reflect 4 configurable anti-Hebbian parameters used in code | Add 4 fields to config section |
| 3 | consolidation.causal_inference.v1.yaml | input_schema | Missing category_thresholds input | input: edge_pairs (List[EdgePair]), timestamps (Dict) | Add category_thresholds: Dict[CausalityCategory, float] with Health=0.85, Financial=0.80, Social=0.70, Preference=0.65 | Contract does not reflect 4-tier category system used in code | Add dict field to input_schema |
| 4 | consolidation.causal_inference.v1.yaml | failure_modes | Missing CATEGORY_UNKNOWN failure mode | failure_modes: INSUFFICIENT_DATA, GRANGER_TEST_FAILED, SPURIOUS_CORRELATION | Add CATEGORY_UNKNOWN: entity text matches no category keywords -> default to Social threshold (0.70) | Undocumented fallback behavior when category classification fails | Add failure mode |
| 5 | consolidation.relationship_builder.v1.yaml | output_schema | Missing social_relationships output field | output: relationships (List[Relationship]) | Add social_relationships: List[SocialRelationship] with 15 fields (type, subtype, emotional_valence_avg/trend, dominant_emotion, emotional_role, interaction_count, intimacy_level, relationship_phase, modalities, location_pattern, confidence) | Social extraction not documented in relationship contract | Add field to YAML output_schema |
| 6 | consolidation.relationship_builder.v1.yaml | config | Missing 6 social extraction config fields | config: edge_confidence_threshold=0.5, max_edges_per_entity=50 | Add sentiment_valence_map (7 labels), role_emotions (6 roles), phase_thresholds (forming<=2, deepening>0.2, cooling<-0.2), confidence_base=0.5, observation_boost_rate=0.05, ultrabert_boost=0.15 | Code has 6 social config parameters not in contract | Add 6 fields to config section |
| 7 | p03_consolidation.v1.yaml | stages.r4 | No mention of edge enrichment (GAP-007) | r4 stage: entity_extraction, edge_discovery, causal_inference | Add enrichment sub-stage with 9 enricher references: SemanticSimilarity, TemporalProximity, Contextual, EmotionSimilarity, IntentSimilarity, TransitiveClosure, BayesianCausal, WeightNormalization, fusion utilities | Enrichment step not reflected in pipeline contract | Add enrichment sub-stage to r4 definition |
| 8 | p03_consolidation.v1.yaml | stages.r4 | No mention of social extraction sub-step | r4 stage definition lists entity + edge + causal only | Add social_extraction sub-stage referencing relationship_builder contract | Social extraction step missing from pipeline definition | Add social sub-stage |
| 9 | consolidation.v1.yaml (capabilities) | capabilities | Missing union_index_search capability for semantic enricher | capabilities: [cap:kg:read, cap:kg:write, cap:metrics:write] | Add cap:vec:search for SemanticSimilarityEnricher's resolve_embeddings call | Capability not declared; syscall enforcement gap | Add capability to ACL |
| 10 | consolidation.v1.yaml (capabilities) | capabilities | Missing cap:db:direct for st_learning_queue raw query | capabilities list | Add cap:db:direct for get_pool().acquire() -> st_learning_queue SELECT | R4 bypasses syscall layer for gap resolution loading; capability not declared | Add capability or migrate to syscall |

### 11.3 Architecture Gaps

| # | Area | Gap | ADR Needed? | Impact | Proposed Resolution | Blocking Epic |
| - | ---- | --- | ----------- | ------ | ------------------- | ------------- |
| 1 | Entity resolution | No standard protocol for entity merge conflict resolution across concurrent cycles | yes | Two cycles may attempt to merge same entity pair, causing cascade conflicts | ADR for optimistic locking or merge queue with conflict detection | 5.5.4 |
| 2 | Edge enrichment | No enricher plugin protocol; enrichers are hardcoded in R4 | yes | Adding new enrichers requires modifying R4KGConsolidator class directly | ADR for enricher registry/plugin protocol with dynamic discovery | future |
| 3 | Social extraction | Social relationship model is embedded in R4 rather than being a separate module | update | Tight coupling makes social extraction hard to reuse outside P03 | Extract social relationship extraction to k0/modules/consolidation/algorithms/social_extractor.py | future |
| 4 | Gap pipeline | No feedback loop from P06 resolution back to R4 confidence tuning | yes | R4 disambiguation thresholds cannot learn from gap resolution outcomes | ADR for gap resolution feedback protocol (P06 -> R4 threshold adjustment) | future |
| 5 | Config management | R4Config testing overrides baked into default config | no | Production deployments may accidentally use testing thresholds | Separate R4Config into base + environment overlay (test/staging/prod) | 5.5.1 |
| 6 | Enricher ordering | No formal contract for enricher execution order or dependency graph | no | TransitiveClosure depends on prior enrichers but this is implicit, not enforced | Document enricher DAG; enforce in code that TransitiveClosure runs after independent enrichers | 5.5.2 |
| 7 | MW v2 signal integration | 5 MW v2 signals available but not consumed by R4 (see Section 3.6) | yes | Missed opportunity for richer entity resolution and edge weighting | ADR for MW v2 signal integration plan; phased adoption per signal | future |

### 11.4 Known Issues (from Epic 5.5 Skeleton)

These 6 known issues were identified in the M5 implementation skeleton:

| # | Issue ID | Description | Source Location | Impact | Related Gap |
| - | -------- | ----------- | --------------- | ------ | ----------- |
| 1 | KI-001 | Sequential enrichers block main R4 pipeline | r4_kg_consolidator.py:~800 | 40% of R4 latency in enrichment step | FG-006, Bottleneck #1 |
| 2 | KI-002 | Granger min_observations too low in default config | r4_config.py (granger_min_observations=1) | Spurious causal edges in production | FG-001, R-001 |
| 3 | KI-003 | Alias detection is string-only (no embeddings) | alias_detector.py (4 signals, no embedding signal) | Misses semantic aliases ("Bob"/"Robert" via embedding) | FG-002 |
| 4 | KI-004 | Weight normalizer ordering-dependent | weight_normalization.py (runs after all enrichers) | Results vary if enricher order changes | FG-006 |
| 5 | KI-005 | P06 gap pipeline not implemented | st_learning_queue gaps accumulate | Unbounded gap queue growth; no resolution loop | FG-003, R-003 |
| 6 | KI-006 | Staleness window not category-aware | edge_demotion.py (90 days for all) | Seasonal/annual patterns falsely archived | FG-004 |

---

## 12. Security & Privacy Audit

### 12.1 Data Classification

| # | Field / Column | Classification | Handling | Retention Policy | Notes |
| - | -------------- | -------------- | -------- | ---------------- | ----- |
| 1 | st_kg_dom.canonical_name | PII | plain | until tenant deletion | Entity names derived from user text (person names, family member names) |
| 2 | st_kg_dom.aliases_json | PII | plain | until tenant deletion | Alias list includes nicknames and name variants |
| 3 | st_kg_edges.evidence_event_ids | internal | plain | until tenant deletion | References to source events; allows reconstruction of relationship context |
| 4 | st_social.actor_a_id / actor_b_id | PII | plain | until tenant deletion | Identifies real people in social relationships |
| 5 | st_social.emotional_valence_avg | confidential | plain | until tenant deletion | Aggregated emotional state about relationships; psychologically sensitive |
| 6 | st_social.dominant_emotion | confidential | plain | until tenant deletion | Dominant emotion in a relationship; psychologically sensitive |
| 7 | st_learning_queue.context_json | PII | plain | until gap resolution or TTL expiry | Contains entity context including names, locations, event references |
| 8 | st_entity_merges.merge_cascade_id | internal | plain | indefinite | Merge audit trail; no PII directly |
| 9 | tenant_id | internal | plain | indefinite | Tenant isolation key; not PII itself |
| 10 | R4PhaseStats (all fields) | internal | plain | session-scoped (not persisted) | Aggregate counts only; no PII |

### 12.2 Capability Boundaries

| # | Operation | Required Capability | Enforced? | Enforcement Location | Gap | Risk Level | Remediation |
| - | --------- | ------------------- | --------- | -------------------- | --- | ---------- | ----------- |
| 1 | kg_candidates_fuzzy_query | cap:kg:read | partial | syscalls layer (not R4 code) | R4 does not verify capability before calling; relies on syscall enforcement | low | Acceptable: syscall layer is the intended enforcement point |
| 2 | kg_entities_lookup | cap:kg:read | partial | syscalls layer | Same as above | low | Acceptable |
| 3 | kg_edges_lookup | cap:kg:read | partial | syscalls layer | Same as above | low | Acceptable |
| 4 | get_pool (direct SQL) | cap:db:direct | **no** | N/A | R4 uses raw pool.acquire() for st_learning_queue query (r4_kg_consolidator.py:637); bypasses syscall capability layer entirely | **medium** | Migrate to syscall: create kg_learning_queue_resolved() syscall |
| 5 | metrics_registry.emit_decision | cap:metrics:write | **no** | N/A | No capability check on metrics emission (r4_kg_consolidator.py:3180) | low | Non-sensitive; metrics are aggregate only |
| 6 | union_index_search (semantic enricher) | cap:vec:search | partial | syscalls layer | Capability declared in consolidation.v1.yaml but not verified at R4 level | low | Acceptable: syscall enforcement |
| 7 | resolve_embeddings (semantic enricher) | cap:vec:read | **no** | N/A | Semantic enricher calls resolve_embeddings but capability not declared | **medium** | Add cap:vec:read to consolidation.v1.yaml |

### 12.3 Input Validation & Sanitization

| # | Input Source | Validation Applied | Sanitization Applied | Injection Risk | Max Input Size | Boundary Check | Notes |
| - | ----------- | ------------------ | -------------------- | -------------- | -------------- | -------------- | ----- |
| 1 | ner_entities_json (bus message) | JSON parse, type check (dict), key existence check | none | low | unbounded | no max entity count enforced (R4Config.max_entities_per_event not checked) | Parameterized queries prevent SQL injection; malformed JSON skipped |
| 2 | extracted_relations_json (bus message) | JSON parse, type check (list) | none | low | unbounded | no max relations enforced | List of strings; no DB interpolation |
| 3 | entity names from NER | Possessive stripping ('s), whitespace normalization | strip(), possessive removal | low | unbounded string length | no max name length enforced | Names used in parameterized fuzzy queries; very long names could slow LIKE queries |
| 4 | st_learning_queue.resolution_data_json (DB) | JSON parse | none | none | bounded by DB column | DB enforced | Trusted source (own DB); parameterized reads |
| 5 | st_kg_dom candidates (DB) | Type check on entity_id, canonical_name | none | none | bounded by limit=10 | query-level limit | Trusted source; fuzzy query limited to 10 candidates |
| 6 | tenant_id / space_id (envelope context) | Presence check | none | low | UUID format | no format validation | Used in parameterized queries; should validate UUID format |
| 7 | participants_json (bus message) | JSON parse, type check | none | low | unbounded | no max participants enforced | Social extraction iterates all participants; 100+ could cause O(n^2) pair explosion |
| 8 | emotions_json (bus message) | JSON parse | none | low | unbounded | no validation of emotion labels | Invalid emotion labels silently ignored in ROLE_EMOTIONS matching |

### 12.4 Audit Trail

| # | Action | Audit Mechanism | Completeness | Gap |
| - | ------ | --------------- | ------------ | --- |
| 1 | Entity creation (CREATE_ENTITY) | metrics_registry.emit_decision + r4_new_entities list | complete | No persistent audit log; metrics are transient |
| 2 | Entity update (UPDATE_ENTITY) | metrics_registry.emit_decision + r4_updated_entities list | complete | Same as above |
| 3 | Edge creation (CREATE_EDGE) | metrics_registry.emit_decision + r4_new_edges list | complete | Same |
| 4 | Edge reinforcement (UPDATE_EDGE) | metrics_registry.emit_decision + r4_updated_edges list | complete | Same |
| 5 | Gap emission | r4_gap_candidates list + DEBUG log | partial | No aggregate gap audit log; individual DEBUG logs only |
| 6 | Alias merge | stats.alias_merges_performed + DEBUG log | partial | No persistent merge audit; alias merge decisions lost after cycle |
| 7 | Entity merge (EntityMerger) | st_entity_merges table | **complete** | Has persistent audit with cascade tracking |
| 8 | Causal edge demotion | DemotionResult logged | partial | No persistent demotion history; result only logged at DEBUG level |
| 9 | Social relationship extraction | stats.social_relationships_extracted + INFO log | partial | No per-relationship audit trail; only aggregate count |

---

## 13. Enhancement Proposals

### 13.1 Proposed Epics

| Epic ID | Title | Scope Summary | Estimated Files | Priority | Dependencies | Issue Count |
| ------- | ----- | ------------- | --------------- | -------- | ------------ | ----------- |
| 5.5.1 | R4 Config Production Hardening | Separate testing overrides from production config; create environment-aware R4Config | 2 MOD, 1 NEW | P0 | none | 3 |
| 5.5.2 | R4 Edge Enricher Parallelization | Parallelize 6 independent enrichers to reduce enrichment latency | 2 MOD | P1 | none | 2 |
| 5.5.3 | R4 Alias Detection Enhancement | Add embedding-based alias signal and expand nickname database | 1 MOD, 1 NEW | P2 | none | 4 |
| 5.5.4 | R4 Contract Alignment | Update 6 YAML contracts to reflect current R4 implementation | 6 MOD | P1 | none | 10 |
| 5.5.5 | R4 Test Gap Closure | Add missing test files for alias_detector, subtype_classifier, observation_context, and production-config Granger | 4 NEW, 1 MOD | P0 | 5.5.1 | 5 |

### 13.2 Epic Detail

---

#### Epic 5.5.1 -- R4 Config Production Hardening

**Summary**: Separate R4Config into production defaults and testing overrides to prevent accidental use of relaxed thresholds in production.

**Problem**: R4Config defaults include granger_min_observations=1 and granger_precedence_threshold=0.60, which are testing overrides far below the algorithm's intended production values (5 and 0.75 respectively).

**Solution**: Create R4ProductionConfig with safe defaults and R4TestConfig that inherits with relaxed overrides; R4Config becomes alias for production.

##### Issues Breakdown

| Issue # | Title | Scope | Estimate | Depends On | Acceptance Criteria |
| ------- | ----- | ----- | -------- | ---------- | ------------------- |
| 5.5.1.1 | Create R4ProductionConfig | Add R4ProductionConfig with min_observations=5, threshold=0.75 | S | none | R4Config() returns production defaults |
| 5.5.1.2 | Create R4TestConfig | Add R4TestConfig inheriting from R4ProductionConfig with relaxed values | S | 5.5.1.1 | Tests pass with R4TestConfig; production never uses relaxed values |
| 5.5.1.3 | Update test files to use R4TestConfig | Replace R4Config() with R4TestConfig() in all R4 test files | S | 5.5.1.2 | All 441 tests pass; no R4Config instances in test code |

---

#### Epic 5.5.2 -- R4 Edge Enricher Parallelization

**Summary**: Run 6 independent edge enrichers concurrently using asyncio.gather to reduce enrichment step latency.

**Problem**: 7 enrichers run sequentially (~100ms each = ~700ms total) even though BayesianCausal, Contextual, Emotion, Intent, Semantic, Temporal are fully independent.

**Solution**: Use asyncio.gather for the 6 independent enrichers, then run TransitiveClosure (which depends on others' output) last, then normalize.

##### Issues Breakdown

| Issue # | Title | Scope | Estimate | Depends On | Acceptance Criteria |
| ------- | ----- | ----- | -------- | ---------- | ------------------- |
| 5.5.2.1 | Parallelize independent enrichers | Wrap 6 enrichers in asyncio.gather; keep TransitiveClosure sequential after | M | none | Enrichment step p95 < 200ms (down from ~700ms) |
| 5.5.2.2 | Add per-enricher latency stats | Add per-enricher duration fields to R4PhaseStats | S | 5.5.2.1 | Each enricher's duration visible in phase stats |

---

#### Epic 5.5.3 -- R4 Alias Detection Enhancement

**Summary**: Add embedding-based semantic alias signal and expand the nickname database for multilingual support.

**Problem**: AliasDetector uses 4 signals (string similarity, embedding similarity, nickname match, co-occurrence) but the nickname signal relies on a hardcoded FirstNameDatabase with ~80 English-only mappings. Semantic aliases like "Bob"/"Robert" or "Liz"/"Elizabeth" work via nicknames but "Bobby"/"Robert" requires string similarity which may be too weak. Non-English names are not covered at all.

**Solution**: (1) Add a 5th embedding-based signal that captures semantic name similarity beyond string overlap. (2) Expand FirstNameDatabase to support multilingual nickname families (Spanish, Hindi, Arabic, Chinese romanizations). (3) Make signal weights configurable via R4Config.

**Files Affected**:

- MOD: k0/modules/consolidation/algorithms/alias_detector.py (add 5th signal, update score fusion)
- NEW: k0/modules/consolidation/algorithms/multilingual_nicknames.py (locale-aware nickname database)
- MOD: k0/pipelines/p03/phases/r4_config.py (add alias_signal_weights config)

##### 5.5.3 Issues Breakdown

| Issue # | Title | Scope | Estimate | Depends On | Acceptance Criteria |
| ------- | ----- | ----- | -------- | ---------- | ------------------- |
| 5.5.3.1 | Add 5th embedding-proximity signal to AliasDetector | Add semantic_proximity_score using entity embedding cosine similarity as 5th signal; update SIGNAL_WEIGHTS to 5-signal tuple (str=0.20, emb=0.25, nick=0.20, co=0.15, sem_prox=0.20) | M | none | AliasDetector.score_alias() computes 5 signals; weights sum to 1.0; existing tests pass with updated weights |
| 5.5.3.2 | Create multilingual_nicknames.py | Implement locale-aware NicknameDatabase with families for English (80+), Spanish (40+), Hindi (30+), Arabic (20+), Chinese romanization (20+); factory method by locale | M | none | NicknameDatabase.lookup("Roberto", locale="es") returns "Robert" family; English coverage unchanged |
| 5.5.3.3 | Make alias signal weights configurable | Add alias_signal_weights: Dict[str, float] to R4Config with production defaults (5-signal); AliasDetector reads from config | S | 5.5.3.1 | R4Config().alias_signal_weights returns 5-weight dict summing to 1.0 |
| 5.5.3.4 | Update contract for alias detection changes | Update consolidation.entity_extractor.v1.yaml output_schema to include alias_candidates with 5-signal breakdown | S | 5.5.3.1 | Contract reflects 5 signals and configurable weights |

---

#### Epic 5.5.4 -- R4 Contract Alignment

**Summary**: Update 6 YAML contracts and 1 capabilities ACL to accurately reflect the current R4 implementation, closing all contract gaps identified in Section 11.2.

**Problem**: R4 implementation has evolved beyond what the contracts document. 10 specific contract gaps exist (see Section 11.2): missing output fields, missing config parameters, missing pipeline sub-stages, and missing capability declarations.

**Solution**: Update each contract file to add the missing fields, sections, and declarations. No code changes required -- this is documentation/contract alignment only.

**Files Affected**:

- MOD: k0/contracts/modules/consolidation.entity_extractor.v1.yaml
- MOD: k0/contracts/modules/consolidation.hebbian_learner.v1.yaml
- MOD: k0/contracts/modules/consolidation.causal_inference.v1.yaml
- MOD: k0/contracts/modules/consolidation.relationship_builder.v1.yaml
- MOD: k0/contracts/pipelines/p03_consolidation.v1.yaml
- MOD: k0/contracts/modules/consolidation.v1.yaml

##### 5.5.4 Issues Breakdown

| Issue # | Title | Scope | Estimate | Depends On | Acceptance Criteria |
| ------- | ----- | ----- | -------- | ---------- | ------------------- |
| 5.5.4.1 | Add alias_candidates to entity_extractor contract | Add alias_candidates: List[AliasCandidate] to output_schema with fields: primary_name, secondary_name, alias_score, alias_type, signals_used | S | none | Contract CG-001 closed; schema validates |
| 5.5.4.2 | Add anti-Hebbian config to hebbian_learner contract | Add anti_hebbian_rate: 0.15, decay_rate: 0.01, prune_threshold: 0.05, correction_multiplier: 1.3 to config section | S | none | Contract CG-002 closed; all 4 params documented |
| 5.5.4.3 | Add category_thresholds to causal_inference contract | Add category_thresholds: Dict[CausalityCategory, float] to input_schema; add CATEGORY_UNKNOWN failure mode | S | none | Contract CG-003 and CG-004 closed |
| 5.5.4.4 | Add social_relationships to relationship_builder contract | Add social_relationships: List[SocialRelationship] with 15 fields to output_schema; add 6 social config fields | S | none | Contract CG-005 and CG-006 closed |
| 5.5.4.5 | Add enrichment sub-stage to p03_consolidation contract | Add enrichment sub-stage with 9 enricher references under stages.r4; add social_extraction sub-stage | S | none | Contract CG-007 and CG-008 closed |
| 5.5.4.6 | Add missing capabilities to consolidation ACL | Add cap:vec:search, cap:vec:read, cap:db:direct (or migrate to syscall) to consolidation.v1.yaml | S | none | Contract CG-009 and CG-010 closed |
| 5.5.4.7 | Add R4 output schema to p03_consolidation contract | Document r4_new_entities, r4_updated_entities, r4_new_edges, r4_updated_edges, r4_gap_candidates, r4_social_entities schemas in p03_consolidation.v1.yaml | S | none | All 6 r4_* output fields documented with types |
| 5.5.4.8 | Add enricher I/O schemas | Create enricher contract section documenting 9 enricher input/output schemas (entity_contexts -> EdgeSignal[]) | M | none | Each enricher's I/O documented with edge types and threshold configs |
| 5.5.4.9 | Add R4PhaseStats schema to pipeline contract | Document all R4PhaseStats fields (30+ counters) in p03_consolidation.v1.yaml observability section | S | none | Stats schema in contract matches R4PhaseStats dataclass |
| 5.5.4.10 | Validate contract-code alignment | Write script to compare YAML contract fields against code; add to CI pre-commit | M | 5.5.4.1-5.5.4.9 | Script exits 0 when all contracts match implementation |

---

#### Epic 5.5.5 -- R4 Test Gap Closure

**Summary**: Add test files for untested R4 algorithms and critical production-config scenarios.

**Problem**: alias_detector, subtype_classifier, and observation_context have no dedicated test files. Granger causality is only tested with relaxed thresholds.

**Solution**: Create 4 new test files and add production-threshold Granger tests.

##### Issues Breakdown

| Issue # | Title | Scope | Estimate | Depends On | Acceptance Criteria |
| ------- | ----- | ----- | -------- | ---------- | ------------------- |
| 5.5.5.1 | Create test_r4_alias_detector.py | 4-signal scoring, FirstNameDatabase, AliasType routing | M | none | 15+ tests pass, covering all 4 signals and threshold routing |
| 5.5.5.2 | Create test_r4_subtype_classifier.py | PatternSubtype and EntitySubtype keyword classification | M | none | 10+ tests pass, covering all 30 subtypes |
| 5.5.5.3 | Create test_r4_observation_context.py | ObservationContext construction and defaults | S | none | 5+ tests pass |
| 5.5.5.4 | Add production Granger tests | Test with min_observations=5, threshold=0.75 | S | 5.5.1 | Tests verify pairs with <5 obs are skipped |
| 5.5.5.5 | Add enrichment fusion integration test | Multi-enricher same-pair edge fusion | M | none | Test verifies weighted_sum and noisy_or produce correct merged weights |

---

## 14. Risk Register

| # | Risk ID | Risk | Category | Likelihood | Impact | Risk Score | Mitigation | Owner | Status | Related Gap/Epic |
| - | ------- | ---- | -------- | ---------- | ------ | ---------- | ---------- | ----- | ------ | ---------------- |
| 1 | R-001 | Production uses testing Granger thresholds (min_obs=1, threshold=0.60) creating spurious causal edges | technical | high | high | **critical** | Epic 5.5.1 separates production and testing configs | dev-lead | open | FG-001, KI-002, Epic 5.5.1 |
| 2 | R-002 | Sequential enrichers cause R4 to exceed P03 time budget for large batches (>100 events) | performance | med | med | medium | Epic 5.5.2 parallelizes independent enrichers | dev-lead | open | FG-006, KI-001, Epic 5.5.2, Bottleneck #1 |
| 3 | R-003 | P06 gap resolution pipeline does not exist; st_learning_queue fills unboundedly (est. 10-50 gaps/cycle) | dependency | high | med | high | Implement TTL-based gap expiry (24h already exists); P06 implementation in future milestone | dev-lead | accepted | FG-003, KI-005 |
| 4 | R-004 | Entity merge conflicts across concurrent P03 cycles (two cycles merge same entity pair) | technical | low | high | medium | R7 truth writer uses ON CONFLICT for idempotent writes; formal merge protocol ADR needed | dev-lead | open | AG-001 |
| 5 | R-005 | AliasDetector nickname database covers only English names (~80 mappings) | technical | med | low | low | Expand FirstNameDatabase to support multilingual families; configurable locale | dev-lead | accepted | FG-002, Epic 5.5.3 |
| 6 | R-006 | Social relationship extraction tightly coupled to R4 (~330 lines in r4_kg_consolidator.py:2588-2918); cannot be reused by other pipelines | technical | low | med | low | Refactor to standalone social_extractor module (Epic 5.5 scope or later) | dev-lead | open | AG-003 |
| 7 | R-007 | kg_entities_lookup loads unbounded entity set for large tenants (est. >10K entities for power users); O(n) memory | performance | med | high | high | Add pagination or filtered queries to syscall; monitor memory per cycle | dev-lead | open | Bottleneck #3, SG-002 |
| 8 | R-008 | 6 YAML contracts out of sync with R4 implementation (10 specific gaps identified in Section 11.2) | technical | high | low | medium | Epic 5.5.4 aligns contracts; enforce contract-code sync in CI | dev-lead | open | CG-001 through CG-010, Epic 5.5.4 |
| 9 | R-009 | 5 MW v2 signals available but unconsumed (social_intimacy_level, identity_relevance, narrative_thread_id, elaboration_depth, participant_relationships partial) | technical | med | med | medium | Phased MW v2 integration per signal (see Section 3.6); ADR needed | dev-lead | open | FG-008 through FG-011, AG-007 |
| 10 | R-010 | O(n^2) enricher scaling wall at ~500 entities (250K pair comparisons across 6 enrichers) | performance | low | high | medium | Pre-filter candidate pairs by locality (type, temporal window, session); reduce to O(n * k) where k << n | dev-lead | open | Bottleneck #6, #7 |
| 11 | R-011 | Per-cluster fuzzy DB queries scale linearly with cluster count (100 clusters * 20ms = 2000ms) | performance | med | med | medium | Batch fuzzy queries into single DB roundtrip with multi-name LIKE or trigram index | dev-lead | open | Bottleneck #4 |
| 12 | R-012 | No persistent audit trail for alias merge decisions, gap emissions, or causal edge demotions | compliance | low | med | low | Add audit event emission for entity lifecycle decisions; persist in audit table | dev-lead | open | Section 12.4 gaps |

### 14.1 Risk Heat Map

```
            Low Impact   Med Impact   High Impact
            ---------    ----------   -----------
High Like.  R-005        R-003,R-009  R-001
Med Like.   -            R-002,R-008  R-007,R-011
Low Like.   R-006,R-012  R-004        R-010
```

---

## 15. Open Questions

| # | Question | Context | Blocking? | Related Gap | Answer | Status | Answered By | Date |
| - | -------- | ------- | --------- | ----------- | ------ | ------ | ----------- | ---- |
| 1 | Should R4Config default to production or testing values? | FG-001: current defaults are testing overrides; R-001 risk is critical | yes | FG-001, R-001, Epic 5.5.1 | | open | | |
| 2 | Is P06 gap resolution pipeline planned for M5 or M6? | FG-003: gaps accumulate without P06; R-003 accepted risk | no | FG-003, R-003 | | open | | |
| 3 | Should edge enrichers run in parallel or maintain sequential ordering? | Performance vs. determinism tradeoff; TransitiveClosure depends on prior enrichers | no | FG-006, R-002, Epic 5.5.2 | Parallel for independent enrichers, sequential for TransitiveClosure | answered | discovery analysis | 2025-07-18 |
| 4 | What is the maximum expected entity count per tenant+space? | Affects kg_entities_lookup memory budget; pagination decision; R-007 risk | yes | R-007, SG-002 | | open | | |
| 5 | Should social relationship extraction be a separate module or remain inline in R4? | Architecture gap AG-003: tight coupling vs. reusability; ~330 lines | no | AG-003, R-006 | | open | | |
| 6 | Is 90-day staleness appropriate for all causal edge categories? | FG-004: seasonal patterns (Christmas, birthday) need longer windows (365d?) | no | FG-004, KI-006 | | open | | |
| 7 | Should the semantic enricher use union_index_search or direct pgvector query? | ADR-K003 eliminated FAISS; union_index_search may be a FAISS-era relic; pgvector has native HNSW | yes | CG-009, R-009 | | open | | |
| 8 | What is the expected throughput for R4 at production scale (events per cycle)? | Needed for performance targets; Section 10.6 scaling projections show wall at ~500 entities | no | R-010, Section 10 | | open | | |
| 9 | Should MW v2 signals be consumed individually or as a batch integration? | 5 unconsumed signals (Section 3.6); phased vs. single-epic approach | no | FG-008-011, AG-007, R-009 | | open | | |
| 10 | What merge conflict resolution strategy for concurrent cycles? | AG-001: optimistic locking vs. merge queue; R-004 risk | yes | AG-001, R-004 | | open | | |
| 11 | Should R4 emit structured audit events for entity lifecycle decisions? | Section 12.4 shows 5 partial/missing audit trails; compliance requirement unclear | no | R-012 | | open | | |
| 12 | What is the target locale set for multilingual nickname support? | Epic 5.5.3: English, Spanish, Hindi, Arabic, Chinese proposed; actual user demographic unknown | no | R-005, Epic 5.5.3 | | open | | |

---

## Appendix A: Glossary

| Term | Definition |
| ---- | ---------- |
| KG | Knowledge Graph -- graph structure of entities (nodes) and relationships (edges) representing real-world knowledge |
| NER | Named Entity Recognition -- ML task of identifying entities (person, place, org) in text |
| Hebbian Learning | Learning rule: neurons that fire together wire together; used for co-occurrence edge strengthening (hebbian_learner.py) |
| Anti-Hebbian | Inverse learning signal: weakens edges when counter-evidence appears (contradiction, correction, context mismatch); uses anti_rate=0.15 with correction_multiplier |
| Granger Causality | Statistical test: X Granger-causes Y if X precedes Y and improves Y's prediction; adapted for causal edge inference in R4 (granger_causality.py) |
| HNSW | Hierarchical Navigable Small World -- approximate nearest neighbor index algorithm used by pgvector for vector similarity search |
| Noisy-OR | Probabilistic fusion: P(effect) = 1 - product(1 - P(cause_i)); used for edge weight combination when multiple enrichers produce same edge pair |
| ObservationContext | Epic 2.3 dataclass capturing temporal, emotional, salience, modality, physical, and social context per entity observation; used by all 7 enrichers |
| Softmax | Normalization function: exp(x_i) / sum(exp(x_j)); used for edge weight normalization to prevent hub dominance |
| R4 | Phase 4 (KG Consolidation) of the P03 memory consolidation pipeline; 3512-line orchestrator with 13 algorithms and 9 enrichers |
| R7 | Phase 7 (Truth Writer) of P03; writes R4 outputs (r4_new_entities, r4_updated_entities, r4_new_edges, r4_updated_edges, r4_gap_candidates) to persistent storage |
| R6 | Phase 6 of P03; writes social relationship data (r4_social_entities) to st_social table |
| P06 | Pipeline 06 (Gap Resolution); planned pipeline for resolving ambiguous entity gaps from st_learning_queue; NOT YET IMPLEMENTED |
| GAP-004 | Gap Analysis Protocol item: multi-signal alias merging; implemented in alias_detector.py with 4 signals |
| GAP-007 | Gap Analysis Protocol item: edge enrichment with observation context; implemented in 9 edge_enricher modules |
| UltraBERT | Family-domain fine-tuned BERT model providing NER, relation extraction, sentiment, intent classification; MW v2 demotes UltraBERT to fallback |
| MW | MindWell -- secondary NLP model providing V2 trust-then-fill signals (preferred over UltraBERT when available); 5 signals unconsumed by R4 |
| Trust-then-fill | P02 waterfall pattern: MW v2 (preferred) -> UltraBERT fallback -> VADER/heuristic -> defaults; R4 consumes the resolved output |
| EntityCluster | R4 internal structure grouping same-type, same-name entities across events; canonical_name selected by frequency+length heuristic |
| ConfidenceBand | AUTO (>=0.85), FLAG (>=0.60), GAP (<0.60); determines entity resolution routing in confidence_router.py |
| KGUpdate | Discriminated union type (CREATE_ENTITY, UPDATE_ENTITY, CREATE_EDGE, UPDATE_EDGE) carrying entity/edge mutations to R7 |
| GapCandidate | Payload for st_learning_queue: gap_type (AMBIGUOUS_ENTITY/ENTITY_FLAGGED), entity context, candidate values, priority |
| SocialRelationship | 15-field structure: type, subtype, emotional analysis (valence, trend, emotion, role), interaction metrics, phase, modalities |
| AliasCandidate | 4-signal alias scoring result: primary/secondary names, alias_score, alias_type (NICKNAME/ABBREVIATION/SPELLING_VARIANT), signal breakdown |
| MergeDecision | AdaptiveMergeThresholds output: should_merge boolean, current threshold, combined score; per-type threshold bounds |
| DemotionResult | CausalEdgeFeedbackProcessor output: action (BOOST/MAINTAIN/LOWER/DEMOTE/ARCHIVE), old/new confidence, reason |
| CausalityCategory | 4-tier classification: Health (threshold=0.85), Financial (0.80), Social (0.70), Preference (0.65); keyword-based |

## Appendix B: References

| # | Document | Path / URL | Relevance |
| - | -------- | ---------- | --------- |
| 1 | P03 Consolidation Pipeline Contract | k0/contracts/pipelines/p03_consolidation.v1.yaml (397 lines) | Pipeline stages, phase ordering, R4 position, event schemas |
| 2 | Entity Extractor Contract | k0/contracts/modules/consolidation.entity_extractor.v1.yaml (66 lines) | Entity extraction I/O schema, latency=150ms, failure_modes |
| 3 | Hebbian Learner Contract | k0/contracts/modules/consolidation.hebbian_learner.v1.yaml (59 lines) | Edge discovery learning parameters, NOT idempotent, latency=100ms |
| 4 | Causal Inference Contract | k0/contracts/modules/consolidation.causal_inference.v1.yaml (67 lines) | Granger causality I/O schema, IS idempotent, latency=200ms |
| 5 | Relationship Builder Contract | k0/contracts/modules/consolidation.relationship_builder.v1.yaml (74 lines) | Relationship extraction schema, NOT idempotent, latency=100ms |
| 6 | Consolidation Capabilities ACL | k0/contracts/modules/consolidation.v1.yaml | Capability declarations for R4 syscalls (cap:kg:read, cap:kg:write, cap:metrics:write) |
| 7 | M5 Master Implementation Skeleton | docs/plans/MASTER_IMPLEMENTATION_SKELETON.md (Epic 5.5 at line 5330) | Epic 5.5 scope, algorithm inventory, pipeline flow, I/O contract, signal gaps, 6 known issues |
| 8 | R0 Batch Selector Discovery | docs/pipelines/p03_enhancement_discovery/P03_R0_BATCH_SELECTOR_DISCOVERY.md | Prior phase discovery (batch selection) |
| 9 | R1 Importance Scoring Discovery | docs/pipelines/p03_enhancement_discovery/P03_R1_IMPORTANCE_SCORING_DISCOVERY.md | Prior phase discovery (scoring) |
| 10 | R2 Episodic Integration Discovery | docs/pipelines/p03_enhancement_discovery/P03_R2_EPISODIC_INTEGRATION_DISCOVERY.md | Prior phase discovery (episodes) |
| 11 | R3 Dedup & Decay Discovery | docs/pipelines/p03_enhancement_discovery/P03_R3_DEDUP_DECAY_DISCOVERY.md | Prior phase discovery (dedup/decay) |
| 12 | Discovery Template | docs/pipelines/p03_enhancement_discovery/DISCOVERY_TEMPLATE.md (1191 lines) | Template format reference |
| 13 | ADR-K003 pgvector Migration | docs/architecture/decisions-K0/adr-k003-v2-pgvector-migration.md | FAISS elimination; pgvector HNSW for all vector search; no faiss imports in k0/ |
| 14 | R4 KG Consolidator Source | k0/pipelines/p03/phases/r4_kg_consolidator.py (3512 lines) | Main orchestrator: 35+ methods, 6 classes, 45 log points, 32 stats mutations |
| 15 | R4 Config Source | k0/pipelines/p03/phases/r4_config.py (224 lines) | R4Config dataclass with 20+ configurable parameters |
| 16 | Entity Extractor Source | k0/modules/consolidation/algorithms/entity_extractor.py (1103 lines) | UltraBERTEntityExtractor, ExtractedEntity, NER family filtering |
| 17 | Alias Detector Source | k0/modules/consolidation/algorithms/alias_detector.py (739 lines) | AliasDetector, 4-signal scoring, FirstNameDatabase |
| 18 | Entity Disambiguator Source | k0/modules/consolidation/algorithms/entity_disambiguator.py (803 lines) | EntityDisambiguator, per-type weight matrix, opposition penalty |
| 19 | Hebbian Learner Source | k0/modules/consolidation/algorithms/hebbian_learner.py (604 lines) | HebbianLearner, anti-Hebbian, exponential decay, prune |
| 20 | Granger Causality Source | k0/modules/consolidation/algorithms/granger_causality.py (403 lines) | GrangerCausalityInference, temporal precedence, min_observations |
| 21 | Edge Demotion Source | k0/modules/consolidation/algorithms/edge_demotion.py (564 lines) | CausalEdgeFeedbackProcessor, StalenessChecker, DemotionResult |
| 22 | Subtype Classifier Source | k0/modules/consolidation/algorithms/subtype_classifier.py (1218 lines) | PatternSubtype, EntitySubtype, 30+ keyword-based subtypes |

## Appendix C: Cross-Reference Matrix

### C.1 Gap-to-Epic-to-Risk Traceability

| Gap ID | Description | Epic | Risk ID | Priority |
| ------ | ----------- | ---- | ------- | -------- |
| FG-001 | Testing config as production default | 5.5.1 | R-001 | P0 |
| FG-002 | String-only alias detection | 5.5.3 | R-005 | P2 |
| FG-003 | P06 gap pipeline missing | future | R-003 | P1 |
| FG-004 | 90-day staleness for all categories | future | -- | P2 |
| FG-005 | Social extraction no multi-cycle aggregation | future | R-006 | P2 |
| FG-006 | Enricher ordering dependency | 5.5.2 | R-002 | P3 |
| FG-007 | Cross-tenant entity dedup | future | -- | P3 |
| FG-008 | MW v2 social_intimacy_level unused | future | R-009 | P2 |
| FG-009 | MW v2 narrative_thread_id unused | future | R-009 | P2 |
| FG-010 | MW v2 identity_relevance unused | future | R-009 | P2 |
| FG-011 | MW v2 elaboration_depth unused | future | R-009 | P3 |
| CG-001-010 | 10 contract gaps | 5.5.4 | R-008 | P1 |
| AG-001 | Merge conflict protocol | future | R-004 | yes (ADR) |
| AG-002 | Enricher plugin protocol | future | -- | yes (ADR) |
| AG-003 | Social extraction coupling | future | R-006 | update |
| AG-004 | Gap feedback loop | future | -- | yes (ADR) |
| AG-005 | Config environment overlay | 5.5.1 | R-001 | no |
| AG-006 | Enricher ordering contract | 5.5.2 | R-002 | no |
| AG-007 | MW v2 signal integration | future | R-009 | yes (ADR) |

### C.2 Known Issue-to-Gap-to-Bottleneck Traceability

| Known Issue | Description | Functional Gap | Architecture Gap | Bottleneck # | Epic |
| ----------- | ----------- | -------------- | ---------------- | ------------ | ---- |
| KI-001 | Sequential enrichers | FG-006 | AG-006 | #1 | 5.5.2 |
| KI-002 | Testing Granger defaults | FG-001 | AG-005 | -- | 5.5.1 |
| KI-003 | String-only alias detection | FG-002 | -- | -- | 5.5.3 |
| KI-004 | Normalizer ordering-dependent | FG-006 | AG-006 | -- | 5.5.2 |
| KI-005 | P06 gap pipeline missing | FG-003 | AG-004 | -- | future |
| KI-006 | Staleness not category-aware | FG-004 | -- | -- | future |
