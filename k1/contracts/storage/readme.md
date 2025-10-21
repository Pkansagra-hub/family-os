# Storage Contracts

**Source ADRs:** ADR-0011, ADR-0011a-d

## Overview

This directory contains contracts for K0 storage architecture, including FTS (Full-Text Search), Vector, and Knowledge Graph stores with unified query interfaces.

## Research Foundation

- **Information Retrieval:** BM25 ranking algorithm
- **Vector Search:** HNSW (Hierarchical Navigable Small World) graphs
- **Knowledge Graphs:** RDF triples, SPARQL-like queries

## Contracts Included

### 1. Multi-Store Architecture Contract (`multi_store.yaml`)
- **Source:** ADR-0011a
- FTS store (SQLite FTS5)
- Vector store (FAISS)
- Knowledge Graph store (SQLite)

### 2. Unified Query Interface Contract (`unified_query.yaml`)
- **Source:** ADR-0011b
- RecallQuery format
- Multi-store retrieval
- Result fusion (MMR algorithm)

### 3. Indexing Contract (`indexing.yaml`)
- **Source:** ADR-0011c
- Indexing pipeline
- Batch indexing
- Index maintenance

### 4. Query Performance Contract (`query_performance.yaml`)
- **Source:** ADR-0011d
- Latency budgets per store
- Caching strategies
- Query optimization

## Multi-Store Architecture

**Source:** ADR-0011a

```yaml
multi_store_architecture:
  fts_store:
    description: Full-text search for keyword queries
    implementation: SQLite FTS5
    algorithm: BM25
    index_type: inverted_index
    use_cases:
      - Keyword search
      - Phrase matching
      - Prefix queries
    latency_target_p95_ms: 50

  vector_store:
    description: Semantic search via embeddings
    implementation: FAISS (Facebook AI Similarity Search)
    algorithm: HNSW (Hierarchical Navigable Small World)
    index_type: approximate_nearest_neighbor
    embedding_model: text-embedding-3-small (1536 dims)
    use_cases:
      - Semantic similarity
      - Contextual retrieval
      - Fuzzy matching
    latency_target_p95_ms: 30

  knowledge_graph_store:
    description: Structured relationships and entities
    implementation: SQLite (triple store)
    algorithm: graph_traversal
    index_type: btree_on_subject_predicate_object
    schema: RDF-like triples (subject, predicate, object)
    use_cases:
      - Entity relationships
      - Graph queries
      - Constraint checking
    latency_target_p95_ms: 40

storage_layer:
  backend: RocksDB
  compression: LZ4
  write_buffer_mb: 64
  block_cache_mb: 128
  bloom_filters: enabled
```

## Unified Query Interface

**Source:** ADR-0011b

```yaml
recall_query:
  format:
    query: string
    filters:
      session_id: string | null
      timestamp_range: [start, end] | null
      tags: [string] | null
      privacy_band: GREEN | AMBER | RED | null

    retrieval_config:
      stores: [fts, vector, kg]
      max_results_per_store: 10
      fusion_algorithm: mmr | reciprocal_rank_fusion
      diversity_lambda: 0.5

    cognitive_enhancements:
      apply_recency_bias: boolean
      apply_affect_weighting: boolean
      apply_confidence_filtering: boolean

multi_store_retrieval:
  parallel_execution:
    - Query FTS store (BM25)
    - Query Vector store (HNSW)
    - Query KG store (SPARQL-like)
    - Wait for all results (timeout: 100ms)

  result_fusion:
    algorithm: mmr (Maximal Marginal Relevance)

    mmr_formula: |
      MMR = λ * Sim(q, d) - (1 - λ) * max(Sim(d, d_i))
      where:
        q = query
        d = candidate document
        d_i = already selected documents
        λ = diversity parameter (0.5 default)

    fusion_steps:
      1. Collect results from all stores
      2. Normalize scores (0.0-1.0)
      3. Apply MMR to balance relevance and diversity
      4. Re-rank by fused score
      5. Return top-k results

  cognitive_enhancements:
    recency_bias:
      enabled: apply_recency_bias == true
      formula: |
        boosted_score = base_score * (1 + recency_weight * e^(-decay * age_hours))
      recency_weight: 0.2
      decay: 0.1

    affect_weighting:
      enabled: apply_affect_weighting == true
      formula: |
        boosted_score = base_score * (1 + affect_weight * affect_score)
      affect_weight: 0.3
      affect_score: extracted from content sentiment

    confidence_filtering:
      enabled: apply_confidence_filtering == true
      threshold: 0.7
      action: filter_out_low_confidence_results
```

## Indexing Pipeline

**Source:** ADR-0011c

```yaml
indexing_pipeline:
  input:
    content: string
    metadata:
      session_id: string
      timestamp: iso8601
      tags: [string]
      privacy_band: GREEN | AMBER | RED
      author: user | agent

  pipeline_stages:
    1_preprocessing:
      - Tokenization
      - Lowercasing
      - Stop word removal (for FTS only)
      - Lemmatization (optional)

    2_embedding:
      model: text-embedding-3-small
      dimensions: 1536
      latency_target_ms: 50
      batch_size: 32

    3_entity_extraction:
      method: NER (Named Entity Recognition)
      entities: [PERSON, ORG, LOC, DATE, EVENT]
      confidence_threshold: 0.8

    4_triple_extraction:
      method: relation_extraction
      schema: (subject, predicate, object)
      confidence_threshold: 0.7

    5_indexing:
      fts_index:
        - Insert into FTS5 virtual table
        - Update inverted index
        - Latency: <10ms

      vector_index:
        - Add embedding to FAISS index
        - Update HNSW graph
        - Latency: <20ms

      kg_index:
        - Insert triples into triple store
        - Update entity-relationship indexes
        - Latency: <15ms

  batch_indexing:
    enabled: true
    batch_size: 100
    flush_interval_ms: 1000

  async_indexing:
    enabled: true
    queue: AsyncIndexQueue
    workers: 4
    backpressure: drop_oldest_if_queue_full
```

## Query Performance

**Source:** ADR-0011d

```yaml
query_performance:
  latency_budgets:
    fts_query_p95_ms: 50
    vector_query_p95_ms: 30
    kg_query_p95_ms: 40
    fusion_overhead_ms: 20
    total_recall_p95_ms: 100

  caching:
    query_result_cache:
      enabled: true
      ttl: 300s (5 minutes)
      max_size: 10000 entries
      eviction_policy: LRU
      hit_rate_target: 50%

    embedding_cache:
      enabled: true
      ttl: 3600s (1 hour)
      max_size: 10000 embeddings
      eviction_policy: LRU

  query_optimization:
    fts:
      - Use FTS5 prefix queries for fast starts
      - Limit results per query (default 10)
      - Use bm25() function for ranking

    vector:
      - Use HNSW for approximate search (vs brute force)
      - Set nprobe = sqrt(num_vectors) for accuracy/speed tradeoff
      - Pre-filter by metadata when possible

    kg:
      - Use indexes on subject, predicate, object
      - Limit graph traversal depth (max 3 hops)
      - Cache frequent entity lookups

  query_planning:
    - Estimate selectivity per store
    - Execute most selective query first
    - Cancel slow queries after timeout
    - Fallback to partial results if timeout
```

## Storage Tiers (Device-Specific)

```yaml
storage_tiers:
  HOT:
    description: In-memory cache for recent data
    storage: RAM
    capacity_mb: 128
    latency_p95_ms: 1
    eviction: LRU

  WARM:
    description: SSD for active sessions
    storage: SSD (RocksDB)
    capacity_gb: 10
    latency_p95_ms: 10
    eviction: LRU + TTL (7 days)

  COLD:
    description: HDD for archival
    storage: HDD or cloud storage
    capacity_gb: 100
    latency_p95_ms: 100
    eviction: TTL (90 days)
```

## Performance Requirements

```yaml
performance:
  read_latency_p95_ms: 100
  write_latency_p95_ms: 50
  indexing_throughput_docs_per_sec: 1000
  query_throughput_qps: 500

  storage_capacity:
    per_session_mb: 10
    max_sessions: 1000
    total_capacity_gb: 10
```

## Observability

```yaml
observability:
  metrics:
    - recall_query_latency_ms{store, percentile}
    - recall_query_total{store, outcome}
    - indexing_latency_ms{stage, percentile}
    - indexing_throughput{docs_per_sec}
    - cache_hit_rate{cache_type}
    - storage_usage_bytes{tier}

  alerts:
    - RecallQuerySlow: p95 > 100ms for 5 min
    - IndexingBacklog: queue_size > 1000
    - CacheHitRateLow: hit_rate < 30% for 10 min
    - StorageCapacityHigh: usage > 80%
```

## Related Contracts

- K0 Bridge: `../k0_bridge/`
- SessionState: `../sessionstate/`
- FlatBuffers: `../flatbuffers/`

---

**Last Updated:** 2025-10-13
