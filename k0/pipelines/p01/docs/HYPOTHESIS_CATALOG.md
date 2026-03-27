# Episode Embedding Hypothesis Catalog

## The Core Question (Revised)

**Engineering question (narrow):** How do we fix the embedding_text bug so episodes
are retrievable?

**Research question (deep):** What IS an episode as a mathematical object, and what
representation naturally preserves its structure for retrieval?

The SOTA catalog (Categories 1-5) answers the engineering question by applying
existing algorithms. Category 6 attempts the research question from first principles.

---

## Category 1: Text Construction (Build Better Text, Then Embed)

These approaches construct a richer text from source events, then embed it with UltraBERT.

### H1.1 — Extractive Summarization: TextRank

**Idea:** Apply TextRank (PageRank on sentence similarity graph) to select the
top-K most representative sentences from source event texts.

**How it works:**

1. Build a graph where each event text is a node
2. Edge weights = cosine similarity between event embeddings (already have them)
3. Run PageRank to find the most "central" sentences
4. Concatenate top-K sentences as embedding_text

**Strengths:**

- Already partially implemented in codebase (textrank.py exists)
- Uses existing UltraBERT embeddings as similarity signal
- No new dependencies
- Deterministic, reproducible
- Preserves actual event language (extractive, not abstractive)

**Weaknesses:**

- Selects representative sentences, not diverse ones
- A 45-event episode selecting top-5 still loses 89% of content
- Central sentences may cluster around dominant theme, miss rare details
- "dentist appointment" might be in a non-central event

**Token budget:** ~500 tokens (UltraBERT limit) = ~5 sentences max

**Verdict:** Baseline improvement. Better than metadata label. Still lossy for rare concepts.

---

### H1.2 — Extractive Summarization: MMR (Maximal Marginal Relevance)

**Idea:** Select sentences that are both relevant (close to centroid) AND diverse
(far from already-selected sentences). Balances coverage vs representativeness.

**How it works:**

1. Compute episode centroid (mean of all event embeddings)
2. Greedily select sentences:
   - Score = lambda *sim(sentence, centroid) - (1-lambda)* max_sim(sentence, selected)
   - lambda=0.5 balances relevance and diversity
3. Select top-K by MMR score

**Strengths:**

- Explicitly optimizes for DIVERSITY — captures dentist AND birthday AND therapy
- Uses existing embeddings, no new models
- Well-studied algorithm (Carbonell & Goldstein, 1998)
- Tunable lambda parameter

**Weaknesses:**

- Still limited to K sentences by UltraBERT token budget
- Greedy selection, not globally optimal
- Diversity might include low-information sentences

**Token budget:** ~5 sentences covering diverse topics

**Verdict:** Strong candidate. Diversity is exactly what we need for retrieval.

---

### H1.3 — Keyphrase Extraction + Template Expansion

**Idea:** Extract key phrases from ALL events, then build embedding text from
structured keyphrases rather than selecting whole sentences.

**How it works:**

1. For each event text, extract keyphrases using:
   - TF-IDF over the episode's event corpus
   - RAKE (Rapid Automatic Keyword Extraction) — statistical, no model needed
   - Or: noun chunks from simple regex/POS patterns
2. Rank keyphrases by TF-IDF score across the episode
3. Build text: "{temporal} episode about {keyphrase1}, {keyphrase2}, ... at {location} with {participants}"

**Example output:**

```text
Thursday afternoon episode about dentist appointment, Maya's fear of loud tools,
Dad's therapy progress, birthday guest list, daycare drop-off, bedtime courage,
cloud night light at Home Kitchen with Dad, Maya, Panda
```

**Strengths:**

- Captures EVERY concept mentioned, not just top-K sentences
- Compact: keyphrases are information-dense
- Can fit 20-30 keyphrases in 500 tokens (vs 5 sentences)
- Query "dentist" directly matches keyphrase "dentist appointment"
- No new model, pure statistical extraction

**Weaknesses:**

- Loses narrative structure and context
- "Maya's fear" might be extracted as "fear" and "Maya" separately
- Quality depends on keyphrase extraction quality
- Compound concepts ("Maya wanted to know if dentists use loud tools") become fragmented

**Token budget:** ~30 keyphrases = ~150 tokens, leaving room for context

**Verdict:** High recall for keyword queries. Weak for natural language queries.

---

### H1.4 — Hierarchical Concatenation with Deduplication

**Idea:** Concatenate ALL event texts, deduplicate redundant content,
then truncate intelligently to fit UltraBERT's token budget.

**How it works:**

1. Collect all event texts chronologically
2. Deduplicate: remove sentences with >0.9 cosine similarity to earlier ones
3. Compress: remove filler phrases, normalize whitespace
4. If over token budget: apply TextRank to select from deduplicated set
5. Prefix with temporal+location context

**Strengths:**

- Maximum information retention before any selection
- Deduplication removes redundancy (many events repeat context)
- Chronological order preserves narrative
- Falls back to TextRank only when necessary

**Weaknesses:**

- For 45-event episodes, even after dedup, text may be 3000+ chars
- UltraBERT 512-token limit forces truncation anyway
- Dedup threshold tuning affects output quality

**Token budget:** Fill entire 512-token budget with deduplicated content

**Verdict:** Good for small episodes (2-5 events). Still needs selection for large ones.

---

### H1.5 — Topic-Segment Summarization

**Idea:** Cluster events within an episode into sub-topics first,
then select one representative sentence per topic cluster.

**How it works:**

1. Cluster event embeddings within the episode (mini k-means, k=sqrt(N))
2. Each cluster = one "topic" within the episode
3. For each topic cluster, select the event closest to cluster centroid
4. Concatenate one representative per topic

**Example (45-event episode with 7 topics):**

- Topic 1 (morning routine): "The kitchen lights and coffee maker started on schedule..."
- Topic 2 (dentist anxiety): "Maya wanted to know if dentists use loud tools like thunder"
- Topic 3 (therapy progress): "Dad's knee therapy showed real improvement today..."
- Topic 4 (birthday planning): "getting the birthday guest list out of my head and onto paper"
- ... etc

**Strengths:**

- Each topic guaranteed to have representation
- "dentist" topic will have a representative even if it's only 2 events
- Number of representatives scales with topic diversity, not episode size
- Uses existing embeddings for clustering

**Weaknesses:**

- Choosing K (number of topics) is arbitrary
- Small topics (1-2 events) might be noise or might be critical
- Extra clustering step adds complexity
- Representative sentence might not be the most searchable one

**Token budget:** sqrt(45)=7 topics, 7 sentences, ~350 tokens

**Verdict:** Best balance of coverage and compactness for large episodes.
Ensures minority topics (like "dentist") are not drowned out.

---

### H1.6 — Entity-Centric Text Construction

**Idea:** Build embedding text organized around ENTITIES (people, places, activities)
rather than chronological narrative.

**How it works:**

1. Extract all entities from NER data across events (already computed by M08)
2. For each entity, collect all event texts that mention it
3. For each entity, select the most informative mention (longest or most unique)
4. Build: "Episode involving {entity1}: {best mention}. {entity2}: {best mention}..."

**Example:**

```text
Episode involving Maya: wanted to know if dentists use loud tools like thunder.
Dad: therapy progress and recovery. Birthday: getting guest list onto paper.
Panda: breakfast felt easier today. K1: keep today centered on dentist appointment.
At Home Kitchen, Thursday afternoon.
```

**Strengths:**

- Directly searchable by entity name
- Each entity has its own context snippet
- Query "Maya dentist" matches both entity and mention
- Leverages existing NER pipeline output

**Weaknesses:**

- Events that don't mention specific entities get lost
- Entity extraction quality affects everything
- May produce awkward text that UltraBERT encodes poorly
- "person_dad" vs "Dad" entity resolution needed

**Token budget:** ~10 entities * ~50 chars = ~500 chars = ~125 tokens

**Verdict:** Excellent for entity-centric queries. Poor for thematic queries.

---

## Category 2: Embedding-Level Approaches (Skip Text, Work in Vector Space)

These approaches manipulate embeddings directly without constructing new text.

### H2.1 — Weighted Mean Pooling of Event Embeddings

**Idea:** Instead of embedding a text, compute the episode embedding as a
weighted average of all member event embeddings.

**How it works:**

1. Collect all 768-dim event embeddings (already in st_vec)
2. Assign weights based on:
   - Importance score (from R1)
   - Emotional intensity (high-emotion events are more memorable)
   - Information density (longer, more unique texts get higher weight)
   - Recency (more recent events weighted higher? or equal?)
3. Episode embedding = weighted_sum(event_embeddings) / sum(weights)
4. Store as embedding_vector directly (skip embedding_text generation)

**Strengths:**

- Uses ALL event information (zero loss)
- No token budget limitation
- Every event contributes to the vector
- "dentist" events pull the centroid toward dentist-related vector space
- Extremely fast (just matrix ops)
- Already partially implemented (CentroidCalculator exists)

**Weaknesses:**

- Mean pooling dilutes signal: 2 dentist events in 45 total = 4.4% weight
- Query "dentist appointment" has limited cosine sim to a centroid that's 95.6% other stuff
- Curse of averaging: everything becomes "generic episode"
- No embedding_text for human inspection or debugging
- Loses narrative/sequential information

**Verdict:** Simple but fundamentally limited by averaging dilution.
45-event episode centroid is too generic for specific queries.

---

### H2.2 — Multi-Vector Episode Representation (ColBERT-Style)

**Idea:** Don't compress to 1 vector. Store ALL event embeddings as the
episode representation. At query time, compute max-sim (late interaction).

**How it works:**

1. Episode representation = set of all N event embeddings (N=2..45)
2. Query embedding = single 768-dim vector from query text
3. Similarity = max(cosine_sim(query, event_i)) for all events in episode
4. "Best matching event" determines episode relevance

**Retrieval:** Query "dentist appointment" → compare against ALL 45 event vectors
→ find the event about dentist → score = 0.92 → episode ranks high

**Strengths:**

- ZERO information loss
- Every event is directly searchable
- No summarization needed at all
- "dentist" query matches the dentist event with full similarity
- This is what ColBERT does and it works extremely well

**Weaknesses:**

- Storage: 45 events *768 dims* 4 bytes = 138KB per episode (vs 3KB for 1 vector)
- Query time: must compare against N vectors per episode, not 1
- FAISS index structure changes (flat index per event, then group by episode)
- Doesn't fit current st_epi.embedding_vector (single BYTEA column)
- Schema change required

**Storage model options:**

- A: Keep event vectors in st_vec, query there, group by episode_id from st_hipp_events
- B: New table st_epi_vectors (episode_id, event_id, vector) — denormalized
- C: Keep as-is, just search st_vec + join to st_hipp_events + join to st_epi

**Verdict:** Theoretically optimal. The "right" answer if we can handle storage/query.
Option A (search st_vec, group by episode) needs NO schema change.

---

### H2.3 — Centroid + Satellite Vectors

**Idea:** Store the centroid (mean) plus K "satellite" vectors that capture
the most distant/unique topics within the episode.

**How it works:**

1. Compute episode centroid (mean of all event embeddings)
2. Find the K events with LOWEST cosine similarity to the centroid (most unique)
3. Store: centroid + K satellite vectors
4. Query similarity = max(sim(query, centroid), sim(query, sat_1), ..., sim(query, sat_K))

**Example (K=3):**

- Centroid: captures the "average" episode about routine, kitchen, family
- Satellite 1: the dentist anxiety event (most distant from routine centroid)
- Satellite 2: the birthday planning event
- Satellite 3: the therapy progress event

**Strengths:**

- Captures both the mainstream (centroid) and the outliers (satellites)
- K=3 means only 4 vectors per episode (centroid + 3 satellites) = 12KB
- Query "dentist" matches satellite 1 with high similarity
- Already have centroid_metadata_json that could store satellite IDs
- Secondary centroid selector already exists (SecondaryCentroidSelector)

**Weaknesses:**

- K is a fixed parameter — might miss the 4th unique topic
- Still lossy compared to full multi-vector (H2.2)
- Need to decide K heuristically
- Schema needs array or extra rows for satellite vectors

**Verdict:** Practical middle ground between single-vector and full multi-vector.
Addresses the dilution problem with bounded storage cost.

---

### H2.4 — IDF-Weighted Embedding Pooling

**Idea:** Weight each event embedding by how "unusual" it is within the episode.
Rare/unique events get higher weight, common/routine events get lower weight.

**How it works:**

1. For each event embedding, compute its cosine distance to the centroid
2. Events far from centroid = more unique = higher IDF-like weight
3. Normalize weights to sum to 1
4. Episode embedding = weighted_sum(event_embeddings, weights=idf_weights)

**Intuition:** The dentist event is unusual in a routine-heavy episode, so it gets
a higher weight. The centroid shifts toward unique content.

**Strengths:**

- Single vector output (fits current schema)
- Pulls centroid toward unique/rare events
- No text manipulation needed
- Fast computation

**Weaknesses:**

- Still produces a single vector — dilution is reduced but not eliminated
- If 2 unique topics exist, they average out
- Pulls toward ALL outliers, not necessarily the important ones
- "Unique" != "important" — a corrupted/noisy event is also unique

**Verdict:** Marginal improvement over plain mean pooling. Same fundamental limit.

---

## Category 3: Retrieval Architecture (Change How We Search, Not What We Store)

### H3.1 — Event-Level Search with Episode Grouping

**Idea:** Don't search episodes at all. Search EVENTS, then group results by episode.

**How it works:**

1. Query "dentist appointment" → embed query → search st_vec (event-level FAISS)
2. Get top-50 matching events
3. For each event, look up its episode_id from st_hipp_events or st_epi.source_events_json
4. Group events by episode_id
5. Episode score = max(event_scores) or sum(event_scores) within group
6. Return ranked episodes with their matching events highlighted

**Strengths:**

- Uses EXISTING event embeddings (already good quality)
- NO changes to episode embedding generation
- NO schema changes
- Every event is directly searchable — zero information loss
- Can be implemented as a query-time aggregation layer
- Matching events provide explainability ("this episode matched because of THIS event")

**Weaknesses:**

- Requires join: st_vec → st_hipp_events → st_epi
- Top-50 events might come from many episodes (scattered results)
- Need event_id → episode_id mapping (exists in source_events_json but reversed)
- Episode metadata (who/where/when) is separate from event-level results
- Two-phase retrieval is slower than single FAISS lookup

**Schema requirement:** Add episode_id column to st_hipp_events (or use existing
consolidation_cycle_id + source_events_json reverse index)

**Verdict:** Highest bang-for-buck. Works TODAY with existing data.
The 600 events already have good embeddings in st_vec.

---

### H3.2 — Dual-Index Search (Episode + Event)

**Idea:** Maintain two FAISS indexes. Search both, merge results.

**How it works:**

1. Index A: Episode-level embeddings (88 vectors, fast)
2. Index B: Event-level embeddings (600 vectors, still fast)
3. Query → search both indexes in parallel
4. Merge: union of episodes found in A + episodes from events found in B
5. Re-rank merged set by combined score

**Strengths:**

- Episode-level index catches high-level queries ("family routine on Thursday")
- Event-level index catches specific queries ("dentist appointment")
- Both indexes already exist (st_epi.embedding_vector, st_vec)
- Parallel search adds minimal latency

**Weaknesses:**

- Merge/dedup logic needed
- Score normalization between indexes
- Maintaining two indexes

**Verdict:** Practical evolution of H3.1 that also keeps episode-level search working.

---

### H3.3 — Inverted Keyphrase Index (Sparse Retrieval)

**Idea:** Build a BM25-style inverted index over episode keyphrases.
Use sparse retrieval for keyword matching, dense retrieval for semantic matching.

**How it works:**

1. Extract keyphrases from all events in each episode
2. Build inverted index: keyphrase → [episode_ids]
3. Query "dentist appointment":
   - BM25 search: finds episodes with "dentist" and "appointment" keyphrases
   - Vector search: finds semantically similar episodes
   - Combine scores: hybrid_score = alpha *bm25 + (1-alpha)* cosine_sim

**Strengths:**

- Exact keyword matching (BM25) catches what vector search misses
- "dentist" is an exact match, guaranteed retrieval
- Sparse index is tiny and fast
- Well-established hybrid retrieval pattern

**Weaknesses:**

- Requires keyphrase extraction pipeline
- BM25 index needs maintenance (rebuild on new episodes)
- Keyword queries work great, paraphrase queries don't
- Two retrieval systems to maintain

**Verdict:** Excellent complement to any vector-based approach.
Keyword matching is the most reliable way to find "dentist" in an episode about dentists.

---

## Category 4: Composite / Hybrid Approaches

### H4.1 — MMR Text + Event-Level Fallback (H1.2 + H3.1)

**Idea:** Generate better episode embeddings with MMR AND provide event-level
search as a fallback for specific queries.

**Implementation:**

1. Fix episode embedding_text using MMR-selected sentences (H1.2)
2. Add event-level search path (H3.1) as complementary retrieval
3. Query → search both → merge → re-rank

**Why this combination:**

- MMR captures diverse episode themes in the episode embedding
- Event-level search catches anything MMR missed
- Each covers the other's weakness

---

### H4.2 — Topic-Segment Text + Keyphrase Index (H1.5 + H3.3)

**Idea:** Episode embedding from topic representatives + sparse keyphrase index.

**Implementation:**

1. Cluster events into topics, select representative per topic (H1.5)
2. Build embedding from topic representatives
3. Also extract keyphrases from ALL events
4. Build BM25 keyphrase index for exact-match retrieval
5. Query → hybrid retrieval (vector + BM25)

**Why this combination:**

- Topic representatives ensure all themes are in the embedding
- Keyphrase index ensures every specific term is findable
- Dense + sparse covers semantic + lexical queries

---

### H4.3 — Centroid+Satellites + Event Passthrough (H2.3 + H3.1)

**Idea:** Multi-vector episode representation + event-level search.

**Implementation:**

1. Store centroid + K satellite vectors per episode (H2.3)
2. At query time, also search event-level vectors (H3.1)
3. Episode score = max(centroid_sim, satellite_sims, event_sims)

**Why this combination:**

- Satellites capture outlier topics without full multi-vector cost
- Event passthrough catches anything satellites missed
- Bounded storage with unbounded recall

---

## Category 5: SOTA / Advanced Techniques

These are state-of-the-art methods from modern information retrieval and representation
learning research. All are LLM-free — they use encoder models, statistical methods,
or small trainable components on top of frozen embeddings.

### H5.1 — Cross-Encoder Re-ranking (Nogueira et al., 2019)

**Idea:** After initial retrieval (any method), re-rank top-K candidates using a
cross-encoder that jointly attends to query + document text. Cross-encoders are
NOT LLMs — they are BERT-class models used as classifiers.

**How it works:**

1. Stage 1: Fast retrieval (FAISS bi-encoder search) returns top-50 candidates
2. Stage 2: For each candidate, feed [CLS] query [SEP] episode_text [SEP] into
   a cross-encoder (e.g., UltraBERT in cross-encoder mode or ms-marco-MiniLM)
3. Cross-encoder outputs a relevance score (single float)
4. Re-rank top-50 by cross-encoder score, return top-10

**Why this is SOTA:**

- Cross-encoders consistently outperform bi-encoders by 5-15% nDCG
- They see query AND document simultaneously (full attention, not cosine similarity)
- Used in every production search system (Google, Bing, Elasticsearch)
- ms-marco-MiniLM-L-6-v2 runs in ~2ms per pair (CPU)

**Strengths:**

- Massive quality boost on top of ANY Stage 1 retriever
- Works with existing episode text (even the broken metadata labels get re-scored)
- Small models (22M-66M params) — NOT LLMs
- Can use UltraBERT itself if fine-tuned, or off-the-shelf cross-encoders
- Composable: bolts onto H1.x, H2.x, H3.x, H4.x

**Weaknesses:**

- Requires episode text (not useful for vector-only approaches)
- Latency: 50 candidates * 2ms = 100ms re-ranking pass
- Quality depends on Stage 1 recall (re-ranker can't find what retriever missed)
- Off-the-shelf cross-encoders are trained on web queries, not family episodic memory

**Verdict:** Essential component in any production retrieval pipeline. Should be
the last stage regardless of which hypothesis generates the candidates.

---

### H5.2 — Learned Sparse Representations (SPLADE, Formal et al., 2021)

**Idea:** Use the MLM (masked language model) head of a BERT-class encoder to produce
sparse vocabulary-sized vectors. Each dimension represents a token's importance.
This gives TERM EXPANSION — "dentist" activates "dental", "teeth", "appointment" too.

**How it works:**

1. Feed episode text through UltraBERT (or a SPLADE-trained model)
2. Take the MLM logits over vocabulary (30K dimensions)
3. Apply log(1 + ReLU(logits)) to get sparse positive weights
4. Result: a sparse vector where non-zero entries = activated vocabulary terms
5. At query time, same process for query text
6. Similarity = dot product of sparse vectors (like BM25 but learned)

**Why this is SOTA:**

- SPLADE-v2 matches or beats ColBERT on MS MARCO while being much faster
- Bridges the lexical-semantic gap that pure dense retrieval misses
- Term expansion catches synonyms that BM25 cannot
- "dentist" query activates "dental", "teeth", "orthodontist" in the sparse vector

**Strengths:**

- Best of both worlds: semantic understanding + lexical precision
- Naturally handles exact-match AND paraphrase queries
- Sparse vectors are compact and fast (inverted index compatible)
- No separate keyphrase extraction needed — the model learns what terms matter
- Pretrained SPLADE models exist (naver/splade-cocondenser-ensembledistil)

**Weaknesses:**

- Requires a SPLADE-trained encoder (UltraBERT may not have been SPLADE-trained)
- 30K-dim sparse vectors need inverted index storage (not FAISS)
- Off-the-shelf SPLADE models are English web-trained
- Need to generate sparse vectors for all episodes + events

**Practical path:** Use a pretrained SPLADE model alongside UltraBERT (two encoders).
Or: extract UltraBERT MLM logits directly if the model retains its MLM head.

**Verdict:** If the MLM head is available, this is the strongest sparse retrieval
approach — strictly better than H3.3 (BM25) because it handles synonyms.

---

### H5.3 — Attention-Based Set Pooling (Set Transformer, Lee et al., 2019)

**Idea:** Replace naive mean/weighted pooling with a learned attention mechanism
that operates over the SET of event embeddings. The model learns WHICH events
matter most for producing a good episode representation.

**How it works:**

1. Input: N event embeddings (each 768-dim) — unordered set
2. Architecture: small Set Transformer (2-4 layers, ~500K params)
   - Inducing points: K learned "query" vectors attend to all events
   - Multi-head attention over event embeddings
   - Output: single 768-dim episode embedding
3. Training signal: contrastive loss — episode embedding should be close to
   its member events and far from other episodes' events
4. Frozen UltraBERT embeddings as input — only the pooling head is trained

**Why this is SOTA:**

- Set Transformer is the standard architecture for set-to-vector problems
- Permutation invariant (event order doesn't matter)
- Learns data-dependent weighting (vs fixed IDF weights in H2.4)
- Used in point cloud processing, molecule property prediction, etc.

**Strengths:**

- Learns to preserve rare/important signals (dentist event gets high attention)
- Tiny model (~500K params, trains in minutes on CPU)
- Frozen UltraBERT — no need to retrain the encoder
- Output is a single 768-dim vector (fits current schema perfectly)
- Handles variable-size input sets (2-45 events)

**Weaknesses:**

- Requires training data: (episode, positive_query, negative_query) triples
- Cold start: need enough episodes to train meaningfully (~500+)
- At 88 episodes, may overfit — need data augmentation
- Adds a model artifact to deploy and version
- Training loop complexity

**Data augmentation for cold start:**

- Positive queries: sample random event text from the episode
- Negative queries: sample event text from OTHER episodes
- Can generate thousands of training triples from 88 episodes

**Verdict:** Theoretically superior to any fixed pooling scheme. Needs enough
training data. Best suited as a Tier 3 research item that pays off at scale.

---

### H5.4 — Reciprocal Rank Fusion (RRF, Cormack et al., 2009)

**Idea:** Instead of building one perfect retriever, combine multiple imperfect
retrievers using RRF — a score-agnostic fusion formula that only uses RANK positions.
This is how Elasticsearch 8.x hybrid search works in production.

**How it works:**

1. Run N retrievers independently:
   - Retriever A: FAISS dense search on episode embeddings
   - Retriever B: FAISS dense search on event embeddings (grouped by episode)
   - Retriever C: BM25 sparse search on episode keyphrases
2. Each retriever returns a ranked list of episodes
3. RRF score for episode d:

   ```
   RRF(d) = SUM( 1 / (k + rank_i(d)) ) for each retriever i
   ```

   where k=60 (standard constant)
4. Final ranking: sort by RRF score

**Example:**

| Episode | Dense Rank | Event Rank | BM25 Rank | RRF Score |
|---------|-----------|-----------|----------|-----------|
| Ep_37 (dentist) | 45 | 1 | 2 | 1/61 + 1/61 + 1/62 = 0.049 |
| Ep_12 (routine) | 1 | 30 | 50 | 1/61 + 1/90 + 1/110 = 0.036 |

→ Dentist episode wins because it ranked #1 in event search AND #2 in BM25,
  despite being #45 in episode-level dense search.

**Why this is SOTA:**

- RRF is the default fusion method in Elasticsearch, Vespa, Weaviate
- Outperforms learned fusion (LambdaMART) on most benchmarks
- Score-agnostic: works even when retriever scores are not comparable
- Zero tuning needed (k=60 is near-universal)

**Strengths:**

- Combines ANY set of retrievers — no assumptions about score distribution
- Robust to individual retriever failures
- No training, no parameters to tune (k=60)
- Simple formula, 10 lines of code
- Best-in-class at combining dense + sparse + event-level signals

**Weaknesses:**

- Only as good as the union of its retrievers' recall
- Needs multiple retrievers to exist first (combines H1-H4 approaches)
- Slight latency overhead from running multiple searches
- Doesn't help if ALL retrievers miss the document

**Verdict:** Not a representation technique — it's the FUSION LAYER that ties
everything together. Any multi-retriever solution (H4.x) should use RRF
instead of ad-hoc score merging.

---

### H5.5 — Contrastive Episode Projection Head

**Idea:** Train a small MLP that projects the naive centroid embedding into a
space where episode embeddings are close to ALL their member event embeddings,
not just the average. Uses contrastive learning (InfoNCE loss).

**How it works:**

1. Input: episode centroid (mean of event embeddings), 768-dim
2. Model: 2-layer MLP (768 → 768 → 768) with residual connection
3. Training:
   - Positive pairs: (projected_centroid, any_member_event_embedding)
   - Negative pairs: (projected_centroid, events_from_other_episodes)
   - Loss: InfoNCE / NT-Xent (contrastive loss)
4. The MLP learns to "spread" the centroid toward ALL member events
   instead of collapsing to the average

**Why this is SOTA:**

- Contrastive learning (SimCLR, MoCo, CLIP) is the dominant paradigm
  for learning good representations from paired data
- InfoNCE is theoretically grounded (maximizes mutual information)
- Projection heads are standard in self-supervised learning

**Strengths:**

- Tiny model: 2-layer MLP = ~1.2M params, trains in seconds
- Output is a single 768-dim vector (fits current schema)
- Frozen UltraBERT — only MLP weights are trained
- Directly optimizes for the retrieval objective
- Unlike Set Transformer (H5.3), input is a SINGLE vector (centroid)
  so inference is trivial

**Weaknesses:**

- Limited by what the centroid can encode — if information is destroyed
  by averaging, the MLP can't recover it
- Needs training data (same cold start as H5.3)
- May not generalize to unseen query patterns
- Subtle hyperparameter sensitivity (temperature, learning rate)

**Key insight:** The MLP can't create information that averaging destroyed.
If 45 events average to a blob, the MLP can re-shape but not split the blob.
This makes H5.5 theoretically weaker than H5.3 (which sees all events).

**Verdict:** Cheap and fast to train. Moderate improvement over naive centroid.
Best as a quick win that runs alongside event-level search (H3.1).

---

### H5.6 — Graph-Augmented Retrieval (PersonalizedPageRank)

**Idea:** Use the existing knowledge graph (st_kg_edges, st_kg_dom) as a retrieval
structure. Query entities propagate relevance through the graph to find episodes
connected by entity co-occurrence, not just embedding similarity.

**How it works:**

1. Build a heterogeneous graph:
   - Nodes: episodes (88), events (600), entities (from st_kg_dom), locations, people
   - Edges: episode→event (membership), event→entity (NER), entity→entity (st_kg_edges)
2. Query "Maya dentist":
   - Find entity nodes matching "Maya" and "dentist"
   - Run Personalized PageRank (PPR) seeded from those nodes
   - PPR propagates relevance: Maya → events mentioning Maya → episodes containing those events
   - Also: dentist → events about dentist → episodes
3. Episode score = PPR score (how much relevance flowed to it)

**Why this is SOTA:**

- Graph retrieval is the foundation of Google Knowledge Graph, Neo4j vector search
- PPR is used in PinSage (Pinterest), GraphSAGE, and production recommendation systems
- Handles multi-hop reasoning: "Maya" + "dentist" → "episode where Maya went to dentist"
- Combines structural (graph) and semantic (embedding) signals

**Strengths:**

- Leverages existing KG data (74 edges, 12 domains already in st_kg_edges/st_kg_dom)
- Multi-hop: finds episodes connected THROUGH entities, not just by text similarity
- Handles entity disambiguation naturally (graph structure resolves "Maya")
- No new embeddings needed — purely structural retrieval
- Complementary to ALL other approaches

**Weaknesses:**

- KG coverage: only 74 edges/12 domains currently — sparse graph
- Graph construction and indexing overhead
- PPR is iterative (convergence time for large graphs)
- Needs entity linking: query "dentist" → which node in the graph?
- If entities aren't in the graph, PPR can't find them

**Practical requirement:** Needs richer KG population. Current 74 edges are too sparse
for meaningful PPR propagation. As P03 runs more cycles and KG grows, this becomes viable.

**Verdict:** High potential at scale with a rich KG. Currently limited by KG sparsity.
Best as a long-term investment that compounds as more data flows through P03.

---

### H5.7 — Product Quantization Multi-Vector (ColBERTv2, Santhanam et al., 2022)

**Idea:** Make full multi-vector representation (H2.2) practical by compressing
each event embedding using residual product quantization. Reduces storage by 20-50x
while maintaining 95%+ retrieval quality.

**How it works:**

1. Train a product quantizer on the event embedding corpus:
   - Cluster centroids: 768 dims / 96 sub-vectors * 256 centroids each
   - Each 768-dim vector → 96 bytes (centroid IDs)
2. For each event, store residual-compressed code instead of full float32 vector
3. At query time:
   - Compute query embedding (full 768-dim)
   - Approximate cosine similarity using quantized codes (lookup table)
   - PLAID: cluster pruning + centroid interaction for speed

**Storage comparison (45-event episode):**

| Method | Storage per episode |
|--------|-------------------|
| Single vector (current) | 3,072 bytes |
| Full multi-vector (H2.2) | 138,240 bytes |
| PQ multi-vector (H5.7) | ~4,320 bytes |

**Why this is SOTA:**

- ColBERTv2 is the top-performing retrieval model on BEIR benchmark
- PLAID engine searches 100M+ passages in <50ms
- Used by Stanford, Vespa, RAGatouille in production

**Strengths:**

- Gets the quality of full multi-vector at 1.4x the storage of single-vector
- Every event searchable at near-full quality
- Well-understood compression theory
- Existing libraries: colbert-ai, RAGatouille (Python)
- Can be applied retroactively to existing st_vec embeddings

**Weaknesses:**

- PQ training needs a corpus (600 vectors is borderline — 10K+ ideal)
- Compression introduces ~2-5% quality loss
- Additional dependency (colbert-ai or custom PQ implementation)
- PLAID engine is complex to implement from scratch
- Quantizer must be retrained as embedding distribution shifts

**Verdict:** The right answer for multi-vector at scale (10K+ episodes).
Overkill at 88 episodes — straight H2.2 is fine at this scale.

---

### H5.8 — Variational Autoencoder Episode Compression

**Idea:** Train a small VAE where the encoder compresses N event embeddings into
a single latent vector, and the decoder reconstructs all N. The bottleneck learns
a maximally-informative episode representation.

**How it works:**

1. Encoder: Set of N event embeddings (768-dim each) → single 768-dim latent z
   - Architecture: mean pooling + 2-layer MLP + reparameterization trick
2. Decoder: latent z → reconstructed set of N embeddings
   - Architecture: z → MLP → N reconstructed 768-dim vectors
3. Loss: reconstruction_loss + KL_divergence
   - Reconstruction: MSE between original and reconstructed event embeddings
   - KL: regularizes latent space (prevents memorization)
4. The latent z IS the episode embedding — it must encode enough info to
   reconstruct all events

**Why this is SOTA:**

- VAEs are the standard for learning compressed representations
- Information-theoretic guarantee: z must contain all recoverable information
- Used in molecular generation, image compression, and text representation

**Strengths:**

- Theoretically optimal compression: z preserves maximum information
- Single vector output (fits current schema)
- Decoder is only needed during training — inference is just the encoder
- Forces the embedding to "remember" rare events (they contribute to recon loss)
- The dentist event's reconstruction loss pushes z toward dentist-related space

**Weaknesses:**

- Variable-size input (2-45 events) complicates architecture
- Reconstruction target is N vectors, but N varies per episode
- 88 episodes = very limited training data (need augmentation)
- Mode collapse risk: VAE may learn to ignore minority events
- Training stability is notoriously finicky for VAEs
- Adds model training/deployment complexity

**Practical variant (Deterministic AE):** Drop the variational part. Just train
encoder + decoder with MSE loss. Simpler, stabler, still information-preserving.

**Verdict:** Elegant but impractical at current scale (88 episodes).
Needs 1000+ episodes for stable training. File under Tier 4 / Future.

---

### H5.9 — Chunked Passage Retrieval (DPR-Style, Karpukhin et al., 2020)

**Idea:** Instead of treating each event as an atomic unit, re-chunk all episode
content into fixed-size overlapping passages (~100 tokens each), embed each passage,
and search at the passage level.

**How it works:**

1. For each episode, concatenate all source event texts chronologically
2. Split into overlapping passages:
   - Window: 100 tokens, stride: 50 tokens (50% overlap)
   - A 45-event episode (~2500 tokens) → ~49 passages
3. Embed each passage with UltraBERT
4. At query time: search all passages, group by episode

**Why this is SOTA:**

- DPR (Dense Passage Retrieval) is the backbone of Wikipedia-scale open-domain QA
- Fixed-size chunks ensure each passage fits within encoder token limits
- Overlapping windows prevent information from being split across chunk boundaries
- Used by Meta AI (RAG), Google (REALM), Microsoft (DPR+)

**Strengths:**

- Passages are more semantically coherent than individual events
- Overlapping windows capture cross-event context (e.g., "Maya asked about dentist
  tools" spans from event 12 to event 13)
- Fixed-size chunks work perfectly with UltraBERT's 512-token window
- Can reuse FAISS infrastructure — passages are just more vectors

**Weaknesses:**

- More vectors than event-level search: 49 passages vs 45 events for large episodes
- Redundancy from overlapping windows
- Loses event boundaries (passage might mix unrelated events)
- Need to store passage texts + embeddings (new table or extend st_vec)
- Re-chunking is a batch operation on all episodes

**Comparison to H3.1 (Event-Level Search):**

| Aspect | H3.1 Events | H5.9 Passages |
|--------|------------|--------------|
| Unit size | Variable (1 sentence - 200 words) | Fixed (100 tokens) |
| Cross-boundary | No (event boundaries are hard) | Yes (overlapping windows) |
| Vector count | = event count | ~1.2x event count |
| Context richness | Single event | May span 2-3 events |

**Verdict:** Better context boundaries than event-level search, at the cost of
slightly more vectors. Most beneficial when events are very short (1-2 sentences)
and lack standalone context.

---

### H5.10 — Hierarchical Navigable Small World + Episode Clusters (HNSW Tiered)

**Idea:** Instead of flat FAISS search, build a tiered HNSW index where episodes
form natural clusters. Query navigates the graph from coarse (episode clusters)
to fine (individual events within the best episode cluster).

**How it works:**

1. Layer 0 (coarse): Episode centroids in HNSW graph (88 nodes)
2. Layer 1 (fine): For each episode node, link to its member event embeddings
3. Query traversal:
   - Enter HNSW at Layer 0, find top-5 nearest episode centroids
   - For those 5 episodes, descend to Layer 1 and search their event vectors
   - Re-rank by best event match within top episodes
4. Early termination: if Layer 0 match is very strong (cosine > 0.9), skip Layer 1

**Why this is SOTA:**

- HNSW (Malkov & Yashunin, 2018) is the dominant ANN index in production
- Tiered/hierarchical search is how Pinecone, Milvus, Qdrant do filtered retrieval
- Combines the speed of episode-level search with the recall of event-level search

**Strengths:**

- Logarithmic query time even as data grows
- Natural two-phase search: coarse episode → fine event
- HNSW graph construction is well-supported (hnswlib, FAISS HNSW)
- Cache-friendly memory access pattern
- Scales to millions of events with bounded latency

**Weaknesses:**

- Index construction is more complex than flat FAISS
- Graph maintenance on insert/delete (new episodes, new events)
- Tuning M (connections per node) and efSearch (beam width) parameters
- Overkill at 88 episodes / 600 events — flat search is already sub-ms

**Verdict:** Essential at scale (10K+ episodes). Unnecessary at current scale.
Important to design the index abstraction now so we can swap flat → HNSW later.

---

## Comparison Matrix

| Hypothesis | Info Retention | Query Types | Schema Change | New Dependencies | Complexity |
|-----------|---------------|------------|--------------|-----------------|------------|
| H1.1 TextRank | ~30% (5 sentences) | Semantic | None | None | Low |
| H1.2 MMR | ~35% (5 diverse) | Semantic | None | None | Low |
| H1.3 Keyphrases | ~60% (terms only) | Keyword | None | RAKE or TF-IDF | Low |
| H1.4 Concat+Dedup | ~40% (token limit) | Semantic | None | None | Low |
| H1.5 Topic-Segment | ~45% (1 per topic) | Semantic+Diverse | None | None | Medium |
| H1.6 Entity-Centric | ~50% (entity focused) | Entity queries | None | None | Medium |
| H2.1 Weighted Mean | 100% (vector space) | Broad semantic | None | None | Low |
| H2.2 Multi-Vector | 100% (all vectors) | All types | Yes (new table) | None | High |
| H2.3 Centroid+Sats | ~90% (centroid+outliers) | Semantic+Outlier | Yes (array col) | None | Medium |
| H2.4 IDF Pooling | 100% (vector space) | Broad semantic | None | None | Low |
| H3.1 Event Search | 100% (event-level) | All types | None | Join logic | Medium |
| H3.2 Dual Index | 100% (both levels) | All types | None | Merge logic | Medium |
| H3.3 Keyphrase BM25 | ~70% (terms) | Keyword+Hybrid | New index | BM25 lib | Medium |
| H4.1 MMR+Events | 100% (combined) | All types | None | Join logic | Medium |
| H4.2 Topics+BM25 | 100% (combined) | All types | New index | BM25 lib | High |
| H4.3 Sats+Events | 100% (combined) | All types | Array col | Join logic | High |
| H5.1 Cross-Encoder | N/A (re-ranker) | All types | None | Cross-encoder model | Medium |
| H5.2 SPLADE | ~80% (term expansion) | Lexical+Semantic | Inverted index | SPLADE model | High |
| H5.3 Set Transformer | 100% (learned pool) | All types | None | Training loop | High |
| H5.4 RRF Fusion | N/A (fusion layer) | All types | None | None (10 LOC) | Low |
| H5.5 Contrastive MLP | 100% (vector space) | Broad semantic | None | Training loop | Medium |
| H5.6 Graph PPR | 100% (structural) | Entity+Multi-hop | None | Graph lib | High |
| H5.7 PQ Multi-Vector | ~97% (compressed) | All types | PQ codebook | colbert-ai | High |
| H5.8 VAE Compress | ~95% (learned) | All types | None | Training loop | Very High |
| H5.9 DPR Passages | 100% (passage-level) | All types | New passage table | None | Medium |
| H5.10 HNSW Tiered | 100% (tiered index) | All types | HNSW index | hnswlib | Medium |

---

## Key Insight: The Fundamental Tradeoff

There are really THREE orthogonal axes:

**Axis 1: How do we represent the episode for embedding?**

- Single text → single vector (H1.x approaches)
- Single composite vector from multiple embeddings (H2.1, H2.4)
- Learned compressed vector (H5.3 Set Transformer, H5.5 Contrastive, H5.8 VAE)
- Multiple vectors per episode (H2.2, H2.3, H5.7 PQ)

**Axis 2: At what level do we search?**

- Episode-level only (current, broken)
- Event-level with episode grouping (H3.1)
- Passage-level with episode grouping (H5.9 DPR)
- Both levels merged (H3.2, H4.x)
- Graph-structural traversal (H5.6 PPR)

**Axis 3: How do we combine and refine results?**

- Single retriever, raw scores (current)
- Multi-retriever fusion — RRF (H5.4)
- Re-ranking — Cross-encoder (H5.1)
- Hybrid dense+sparse — SPLADE (H5.2) or BM25 (H3.3)

The BEST solution spans all three axes:

- Better episode representation (so episode-level search works for broad queries)
- Event-level passthrough (so specific queries like "dentist" always find the event)
- Multi-retriever fusion + re-ranking (so combined results beat any single retriever)

---

## Preliminary Ranking (For Discussion)

### Tier 1 — Implement First (High Impact, Low Risk)

1. **H3.1 Event-Level Search** — Zero changes to episode generation. Search events,
   group by episode. Works with existing data. Solves the "dentist" problem immediately.

2. **H1.2 MMR Extraction** — Fix episode embedding_text to use diverse sentence selection.
   Small change to EpisodicTextGenerator. Improves episode-level search quality.

3. **H5.4 RRF Fusion** — 10 lines of code to combine any set of retrievers.
   Should be the default fusion method as soon as we have 2+ retrieval paths.

### Tier 2 — Implement Next (High Impact, Medium Effort)

1. **H1.5 Topic-Segment** — Better than MMR for large episodes. Guarantees minority
   topic representation.

2. **H3.3 Keyphrase BM25** — Sparse retrieval complement. Exact keyword matching
   catches what vector search misses.

3. **H5.1 Cross-Encoder Re-ranking** — Bolts onto any retriever. 5-15% nDCG boost
   for 100ms latency cost. Small model, not an LLM.

### Tier 3 — Research (High Impact, High Effort)

1. **H2.3 Centroid+Satellites** — Multi-vector with bounded storage. Needs schema work.

2. **H4.1 MMR+Events** — Full hybrid approach combining Tier 1 solutions.

3. **H5.2 SPLADE** — Learned sparse retrieval. Strictly better than BM25 if we
   can source a pretrained SPLADE encoder.

4. **H5.9 DPR Passages** — Better context boundaries than event-level search.
   Worth testing if events are too short for standalone semantic meaning.

### Tier 4 — Future (Scale-Dependent)

1. **H2.2 Full Multi-Vector** — Theoretically optimal but needs architecture changes.

2. **H5.3 Set Transformer** — Learned attention pooling. Needs 500+ episodes for training.
   Best payoff at scale when fixed pooling strategies hit their ceiling.

3. **H5.5 Contrastive MLP** — Quick-to-train projection head. Moderate improvement
   over naive centroid. Needs training data.

4. **H5.6 Graph PPR** — Graph-augmented retrieval. Compounds as KG grows.
   Currently limited by 74 edges. High potential at 10K+ edges.

5. **H5.7 PQ Multi-Vector** — ColBERTv2-style compression. Makes H2.2 practical
   at 10K+ episodes where raw multi-vector storage is prohibitive.

6. **H5.8 VAE Compression** — Information-theoretically optimal but needs 1000+
   episodes for stable training. Elegant long-term solution.

7. **H5.10 HNSW Tiered** — Essential index structure at scale. Unnecessary at 88
   episodes. Design the abstraction now, swap implementation later.

---

## Open Questions for Discussion

1. **What query patterns matter most?**
   - Exact entity ("Maya's dentist") → H3.3 or H3.1
   - Thematic ("anxiety moments") → H1.2 or H1.5
   - Temporal ("what happened Thursday afternoon") → current metadata is fine
   - Cross-episode ("all dentist visits") → H3.1 essential

2. **What is the acceptable latency budget for retrieval?**
   - Sub-100ms → single FAISS lookup (episode-level only)
   - Sub-500ms → event search + grouping (H3.1)
   - Sub-1s → hybrid (H4.x)

3. **How many episodes will exist at scale?**
   - 88 now. 1000 in a year? 10000?
   - At 10K episodes with 50 events each = 500K event vectors
   - Event-level search at 500K is still fast with FAISS

4. **Should embedding_text remain human-readable?**
   - If yes: H1.x approaches (text-based)
   - If no: H2.x approaches (vector-only) are fine

5. **Do we need to re-embed existing 88 episodes?**
   - Yes if we change embedding_text generation (H1.x)
   - No if we add event-level search (H3.1)
   - Both if we do H4.1

---

## Next Steps

1. Discuss hypotheses — which combinations make sense for our architecture
2. Build benchmark harness — 10 test queries against the 600-event dataset
3. Prototype top candidates
4. Measure retrieval quality (MRR, Recall@K, nDCG)

---

---

## Category 6: Original Research — First-Principles Episode Representation

> **This is not applying known algorithms. This is asking: what IS an episode
> mathematically, and what representation theory naturally follows from its structure?**

---

### Step 0 — Constraint Inventory: What Is an Event, Really?

Before designing any representation, we must enumerate every natural dimension
of an event. Each dimension is a **constraint** that the ideal representation must
respect. Flattening all of these into a single 768-dim dense vector destroys most
of this structure.

**Dimension taxonomy of a single event:**

| Axis | Type | Examples | Current storage |
|------|------|---------|----------------|
| **WHO** | Set of entities | {Maya, Dad, Panda} | NER in event_body |
| **WHAT** | Activity / verb phrase | dentist appointment, therapy session | activity_type, intent |
| **WHERE** | Spatial location | Home Kitchen, clinic | place_id, location |
| **WHEN** | Timestamp + duration | Thursday 3pm, 45 min | conversation_anchor_ms, event_time_utc |
| **WHAT OBJECT** | Physical objects | cloud night light, coffee maker | NER object entities |
| **EMOTIONAL STATE** | Valence + arousal | anxiety (neg, high), relief (pos, low) | emotional_intensity |
| **NOVELTY** | Deviation from routine | 0.0 = totally routine, 1.0 = unprecedented | distance from centroid |
| **IMPORTANCE** | Salience weight | R1 score | importance_score |
| **CAUSAL ROLE** | Cause / effect / context | Maya anxious BECAUSE of dentist | implicit — not stored |
| **SEMANTIC CONTENT** | Dense embedding | 768-dim UltraBERT vector | st_vec |
| **NARRATIVE ROLE** | Story function | setup, conflict, resolution, reflection | implicit — not stored |

**Key observation:** These axes are NOT all semantic. They live in different spaces:

- WHO is a SET (discrete, unordered)
- WHEN is a 1D ordered timeline (metric space)
- WHERE is a categorical + hierarchy (or lat/lon)
- EMOTIONAL STATE is a 2D continuous space (valence × arousal)
- SEMANTIC CONTENT is a 768-dim vector space
- CAUSAL ROLE is a graph structure
- NARRATIVE ROLE is a sequence position

Flattening these into one vector is a category error. It's like measuring the
temperature of a symphony — technically possible but meaningless.

**Episode = a cluster of N events across all these dimensions simultaneously.**

The cluster has:

- A **center** in each dimension (mean WHO, mean WHERE, etc.)
- A **spread** in each dimension (variance — how diverse were the participants? the emotions?)
- A **shape** — are the events tightly clustered (mono-topic) or spread out (multi-topic)?
- A **trajectory** — how did the episode evolve over time along each axis?

---

### H6.1 — Episode as a Multi-Axis Structured Object (Not a Vector)

**Core idea:** Abandon the assumption that an episode must be a vector.
Instead, represent it as a structured object:

```
Episode {
    # WHO axis
    participant_weights: Dict[entity_id -> float]  # how often each person appeared

    # WHERE axis
    location_distribution: Dict[place_id -> float]  # time spent at each location

    # WHEN axis
    temporal_span: (t_start_ms, t_end_ms)
    temporal_density: float  # events per hour — how intense was the episode?

    # WHAT axis
    activity_histogram: Dict[activity_type -> count]  # what kinds of things happened

    # EMOTIONAL axis
    emotional_trajectory: List[(t, valence, arousal)]  # emotion over time
    emotional_range: float  # how much did emotion vary?

    # SEMANTIC axis (the only vector part)
    semantic_centroid: Vector[768]  # mean of event embeddings
    semantic_spread: float  # mean distance from centroid — topic diversity

    # NOVELTY axis
    novelty_profile: List[float]  # per-event novelty scores
    peak_novelty: float  # the most unusual thing that happened

    # NARRATIVE axis
    scene_count: int  # number of scene segments (from scene segmenter)
    scene_transitions: List[t]  # when did the narrative shift?
}
```

**Retrieval with this structure:**

Query: "Maya dentist anxiety" decomposes as:

- WHO: {Maya} → match participant_weights["Maya"] > 0
- WHAT: {dentist} → match activity_histogram["medical_appointment"] > 0
- EMOTIONAL: {anxiety} → match episodes where emotional_trajectory has high arousal + negative valence
- SEMANTIC: embed "dentist anxiety" → match semantic_centroid with some similarity

Episode score = weighted combination of per-axis scores.

**Why this is novel:**

- Current approach: project everything to R^768 and hope cosine similarity works
- This approach: match each query dimension to the corresponding structural axis
- Multi-axis matching is STRICTLY MORE EXPRESSIVE than single-vector cosine similarity
- A structural object cannot drift into "generic" the way centroid averaging does

**The open mathematical question:**

How do we combine per-axis scores into a single ranking? Options:

- Product: score = PRODUCT(axis_scores) — all axes must match (AND logic)
- Sum: score = SUM(w_i * axis_scores_i) — any axis can contribute (OR logic)
- Min: score = MIN(axis_scores) — weakest link determines relevance
- Learned combiner: small regression trained on feedback

**Research task:** Design the per-axis similarity functions and the combiner.

---

### H6.2 — Episode as a Probability Distribution in Semantic Space

**Core idea:** An episode is NOT a point in embedding space. It is a probability
distribution over embedding space. Events are i.i.d. samples from this distribution.

Formally:

$$\text{Episode} \sim \mathcal{N}(\mu_e, \Sigma_e)$$

where:

- $\mu_e \in \mathbb{R}^{768}$ = mean of event embeddings (the centroid we already have)
- $\Sigma_e \in \mathbb{R}^{768 \times 768}$ = covariance matrix of event embeddings

**Retrieval:** Instead of cosine similarity between query vector and episode centroid,
compute the **Mahalanobis distance** between query and episode distribution:

$$d(q, e) = (q - \mu_e)^T \Sigma_e^{-1} (q - \mu_e)$$

**Why this is dramatically better than cosine similarity:**

Consider a 2D toy example:

```
Episode A: events scatter along axis 1 (dentist, teeth, fear, loud tools)
           μ_A = [0.5, 0.5],  Σ_A = [[0.8, 0], [0, 0.1]]

Episode B: events scatter along axis 2 (routine, kitchen, morning, coffee)
           μ_B = [0.5, 0.5],  Σ_B = [[0.1, 0], [0, 0.8]]
```

Both episodes have the SAME centroid! Cosine similarity cannot distinguish them.
Mahalanobis distance distinguishes them perfectly because the covariance encodes
the DIRECTION of topic spread.

**Query "dentist appointment" = q = [0.9, 0.1]:**

- Mahalanobis to Episode A: small (q is within Episode A's spread on axis 1)
- Mahalanobis to Episode B: large (q is outside Episode B's spread)

**The information-theoretic version:**

Use KL divergence instead:

$$D_{KL}(q || e) = \frac{1}{2}\left[ \log\frac{|\Sigma_e|}{|\Sigma_q|} + \text{tr}(\Sigma_e^{-1}\Sigma_q) + (\mu_e-\mu_q)^T\Sigma_e^{-1}(\mu_e-\mu_q) - k \right]$$

This is the proper information-theoretic distance between two Gaussian distributions.

**Practical challenge:** $\Sigma_e \in \mathbb{R}^{768 \times 768}$ has 295K entries.
For 88 episodes, that's 26M floats = ~100MB. Feasible.
For 10K episodes: ~11GB. Needs diagonal approximation.

**Diagonal approximation (practical variant):**
$\Sigma_e \approx \text{diag}(\sigma_1^2, ..., \sigma_{768}^2)$
Per-dimension variance. Reduces from 768² to 768 floats per episode.
This is called a **diagonal Gaussian** and is standard in probabilistic retrieval.

**What this recovers that centroid loses:**

The variance $\sigma_j^2$ in dimension $j$ tells us how much the episode "spread"
along that semantic direction. A high $\sigma_j$ means "this episode touched
diverse things in direction $j$." The inverse covariance in Mahalanobis distance
AMPLIFIES query components that align with the episode's spread directions.

Dentist episode: high variance in the "medical" semantic direction.
Query "dentist": high activation in "medical" direction.
Mahalanobis: correctly amplifies the match.

---

### H6.3 — Episode as a Convex Region (Membership Query, Not Similarity Query)

**Core idea:** Flip the retrieval problem. Instead of asking "how similar is this
episode to the query?", ask "does the episode CONTAIN the query concept?"

Formally: an episode is the convex hull of its event embeddings:

$$\text{Episode}_e = \text{conv}\{v_1, v_2, ..., v_N\}$$

where $v_i$ are the event embedding vectors.

**Retrieval:** Given query embedding $q$, an episode is relevant if $q$ is
(approximately) inside or near the convex hull:

$$\text{relevance}(q, e) = -\min_{\lambda: \sum \lambda_i = 1, \lambda_i \geq 0} \left\| q - \sum_i \lambda_i v_i \right\|^2$$

This is the distance from $q$ to the convex hull of the events.

**Why this is fundamentally different:**

- Centroid approach: episode = single point. Similarity = distance to that point.
- Convex hull approach: episode = REGION. Relevance = whether query falls inside.

The dentist event stretches the convex hull toward "dental/medical" space.
Any query near that vertex of the hull has near-zero distance — it "belongs to" the episode.

**Mathematical property:**

The convex hull is the SMALLEST CONVEX SET that contains all events.
Any concept that is a "convex combination" of concepts present in the episode
is inside the hull. This is the formal statement of "reachable by interpolation."

**Practical computation:**

For high-dimensional spaces (768-dim), exact convex hull is infeasible (curse of
dimensionality — a 768-simplex). Practical approximations:

1. **Approximate by ball**: distance from query to nearest event embedding (H3.1 variant)
2. **Approximate by ellipsoid**: Mahalanobis distance (H6.2 — same thing geometrically)
3. **Approximate by K supporting hyperplanes**: find K extreme events and use their
   halfspaces as the approximation. Extreme events = those farthest from centroid.

**Key insight from geometry:**

The "extreme events" (those farthest from the centroid in each direction) are the
VERTICES of the convex hull approximation. These are exactly the events that are
most unlike the average — the dentist event, the birthday planning event, etc.
This gives a geometric justification for H2.3 (Centroid+Satellites):
satellites ARE the convex hull vertices.

**Research task:**
Can we formally characterize what "K extreme events" captures in terms of
approximation quality to the true convex hull?

---

### H6.4 — Episode Variance as First-Class Signal (PCA over Event Cluster)

**Core idea:** The VARIANCE of the event cluster tells us more about the episode
than the MEAN. Run PCA over the N × 768 event embedding matrix.

Let $V \in \mathbb{R}^{N \times 768}$ be the matrix of event embeddings.
Center it: $\tilde{V} = V - \bar{v}$ (subtract centroid).
SVD: $\tilde{V} = U \Sigma W^T$

The principal components $W = [w_1, w_2, ..., w_K]$ are the main axes of variation
within the episode. The singular values $\sigma_1 \geq \sigma_2 \geq ...$ tell us
how much variance each axis explains.

**Episode representation:**

$$\text{Episode} = [\bar{v}, w_1, w_2, ..., w_K, \sigma_1, ..., \sigma_K]$$

where $K = $ number of meaningful components (e.g., K = min(N-1, 5)).

**Retrieval:**

$$\text{relevance}(q, e) = \cos(q, \bar{v}) + \sum_{k=1}^{K} \sigma_k \cdot (q \cdot w_k)^2$$

The first term: similarity to the centroid (standard).
The second term: the query's projection onto each principal axis, weighted by how
much variance that axis explains. This AMPLIFIES queries that align with the
episode's directions of variation.

**What PCA reveals:**

For a 45-event episode about routine with one dentist sub-topic:

- $w_1$ = first PC = direction of most variation = the "routine vs. other" axis
- $w_2$ = second PC = "morning vs. afternoon" sub-axis
- $w_3$ = third PC = "medical vs. domestic" axis (the dentist direction!)
- $\sigma_3$ is small (few events on this axis) but $q_{\text{dentist}} \cdot w_3$
  is large → the dentist query gets amplified

**Why this is novel and theoretically grounded:**

- Mean pooling discards all variance information
- PCA retains the structure of the variance
- A query that aligns with a MINOR principal component (small $\sigma_k$) is
  retrieving an unusual/rare concept — but the formula still finds it because
  $(q \cdot w_k)^2$ can be large even when $\sigma_k$ is small
- Information-theoretically: the PCs are orthogonal bases for the episode's
  "topic space" — they are the NATURAL coordinate system for the episode

**Practical representation:**

K=5 components: episode stored as 6 vectors of dim 768 = 4608 floats = ~18KB.
At 10K episodes: ~180MB. Manageable.

**Open question:**

What is the right weighting formula? Options:

1. Weighted by $\sigma_k$: gives more weight to dominant themes
2. Uniform over all K PCs: treats all themes equally regardless of size
3. Inversely weighted by $\sigma_k$: emphasizes rare themes (detective mode)
4. Weighted by $\sigma_k / (1 + \sigma_k)$: soft weighting, doesn't let one theme dominate

Option 3 (inverse weighting) is particularly interesting: it says "an unusual thing
in this episode is MORE SIGNIFICANT than the dominant theme." This is arguably
the right memory model for episodic recall.

---

### H6.5 — Causal-Temporal Graph as Episode Structure

**Core idea:** Events in an episode are not an unordered set — they have
temporal ordering AND causal relationships. A representation that ignores
causality loses the most important structural information.

**Episode = DAG (Directed Acyclic Graph):**

Nodes: events
Edges:

- Temporal edges: $e_i \rightarrow e_j$ if $t_i < t_j$ (happened before)
- Causal edges: $e_i \rightarrow e_j$ if $e_i$ caused or motivated $e_j$
  (inferred by: $e_j$ has high semantic similarity to $e_i$ AND follows it shortly)
- Participatory edges: events sharing the same participant are linked
- Spatial edges: events at the same location are linked

**Episode representation from graph structure:**

Option A — Graph embedding (node2vec / DeepWalk):
Run node2vec on the episode DAG to produce a single graph embedding.

Option B — Structural descriptor:

- Number of causal chains (linear sequences of causally linked events)
- Number of parallel threads (simultaneous activities)
- Graph density (how connected are events?)
- Betweenness centrality: the most "central" event in causal flow
- The central event is the most important event to represent

Option C — Attention over graph:
Apply graph attention network (GAT) over the episode DAG.
Each event attends to its causal predecessors.
The final node state encodes "this event in context of everything that led to it."

**Why causality matters for retrieval:**

Query "why was Maya anxious?" is a CAUSAL query. It should find the episode where:
dentist-appointment-scheduled → Maya-asked-about-tools → Maya-expressed-fear → Dad-reassured

These four events form a causal chain. The episode embedding must preserve this chain.

**Practical causal inference (no LLM):**

Causal edges can be approximated statistically:

1. Event $e_j$ follows $e_i$ within Δt < 30 minutes
2. Cosine similarity sim($e_i$, $e_j$) > 0.7 (same topic continues)
3. Emotion changes: $e_j$ has significantly different valence from $e_i$
   → something happened between them (likely causal)

**Research task:** Define a formal causal edge detection criterion using only
temporal distance, semantic similarity, and emotional change — no LLM.

---

### H6.6 — Semantic Entropy as Episode Fingerprint

**Core idea:** The ENTROPY of an episode's event distribution characterizes
its "identity" better than its mean. Two fundamentally different measures:

**1. Intra-episode semantic entropy:**

$$H_e = -\sum_{i} p_i \log p_i$$

where $p_i$ is the "probability" (relative importance weight) of event $i$ in
the episode, computed from pairwise similarities:

$$p_i \propto \exp(-\frac{1}{N}\sum_{j \neq i} \cos(v_i, v_j))$$

High entropy = diverse episode (many different things happened).
Low entropy = mono-topic episode (same thing repeated).

**Entropy as a retrieval filter:**

Query "unusual thing that happened" → filter for high-entropy episodes.
Query "Maya's morning routine" → filter for low-entropy episodes.

Entropy is a ZERO-COST discriminator on top of any retrieval method.

**2. Per-dimension entropy (KL from background):**

For each semantic dimension $j$ from 1 to 768:
$$\text{surprise}_j(e) = \text{KL}(P_{e,j} || P_{\text{background},j})$$

where $P_{e,j}$ is the distribution of event activations on dimension $j$
within the episode, and $P_{\text{background},j}$ is the population-level distribution
across ALL episodes.

This measures: "In dimension $j$, how unusual is this episode compared to average?"

High $\text{surprise}_j$ on dimension $j$ = episode is distinctive on that topic.
The set of high-surprise dimensions is the episode's "fingerprint."

**Episode fingerprint:** the top-K dimensions with highest surprise = the K ways
this episode is unusual compared to the background.

**Retrieval:** Query is relevant to episode if the query has high activation on
any of the episode's high-surprise dimensions.

**Why this is novel:**

- TF-IDF does this for words. We're doing it for semantic dimensions.
- "IDF" for semantic dimensions = how common is activity on this semantic direction
  across all episodes? Rare directions are more distinctive.
- This is a principled, information-theoretic approach to "what makes this episode unique."

---

### Synthesis: The Unified Scoring Function

From the constraint analysis and the six hypotheses above, the ideal episode
representation is a structured object with three components, combined into one
retrieval kernel:

$$\text{score}(q, e) = \underbrace{\alpha \cos(q, \mu_e)}_{\text{Term 1: Centroid}} + \underbrace{\beta \sum_k \sigma_k (q \cdot w_k)^2}_{\text{Term 2: Satellite}} + \underbrace{\gamma \sum_{\text{axis}} \text{axis\_score}(q, A_e)}_{\text{Term 3: Structural}}$$

---

### Term 1 — The Centroid Signal: $\alpha \cos(q, \mu_e)$

```
q    = query embedding (768-dim)
μ_e  = episode centroid (mean of all event embeddings)
α    = weight for broad/thematic queries
```

What it captures: "What is this episode generally about?"

Works for: "family morning routine", "birthday planning"
Fails for: "dentist" — diluted by 43 other events

---

### Term 2 — The Satellite Signal: $\beta \sum_k \sigma_k (q \cdot w_k)^2$

```
w_k  = K satellite vectors — the outlier/salient events
σ_k  = salience weight of satellite k
β    = weight for specific/memorable queries
```

$(q \cdot w_k)^2$ = how much the query "activates" satellite $k$ (squared projection).

Works for: "Maya scared", "dentist visit", "therapy breakthrough"
Fails for: "family routine" — routine events are never satellites

**Explicit $\sigma_k$ formula:**

$$\sigma_k = \lambda_1 \cdot \text{affect}_k + \lambda_2 \cdot \text{novelty}_k + \lambda_3 \cdot \text{importance}_k$$

```python
affect_k     = event.affective_intensity          # 0→1, from SessionState / R2
novelty_k    = 1 - cosine(w_k, mu_e)             # distance from centroid
importance_k = event.importance_score             # from R1 scorer

# novelty_k IS the satellite selector from H2.3
# High novelty = far from centroid = vertex of convex hull (H6.3)
# High affect  = emotionally salient = hippocampally encoded strongly
# High importance = explicitly marked by R1 as signal-bearing
```

**Geometric interpretation (from H6.3):** The satellites are the vertices of the
convex hull of the event embedding cloud. The squared projection $(q \cdot w_k)^2$
measures how far the query extends along each hull vertex direction.
If the query lives near a hull vertex, it "belongs to" the episode in that region.

---

### Term 3 — The Structural Signal: $\gamma \sum_{\text{axis}} \text{axis\_score}(q, A_e)$

$$\text{axis\_score}(q, A_e) = \sum_{\text{axis} \in \Omega} \omega_{\text{axis}} \cdot s_{\text{axis}}(q, A_e)$$

```python
def axis_score(query_context, episode_axes):
    scores = {
        "temporal":  temporal_overlap(query_context.time_ref, episode_axes.time_window),
        "social":    jaccard(query_context.entities, episode_axes.participants),
        "spatial":   location_match(query_context.place, episode_axes.place_id),
        "affective": 1 - abs(query_context.valence - episode_axes.mean_valence),
        "narrative": 1.0 if query_context.thread == episode_axes.thread_id else 0.0,
    }
    # affective + social are dominant — they are the most discriminative axes
    weights = {"temporal": 0.15, "social": 0.25, "spatial": 0.10,
               "affective": 0.30, "narrative": 0.20}
    return sum(weights[ax] * s for ax, s in scores.items())
```

Works for: "Thursday morning", "when Maya was with Dad", "at the clinic"

**Neuroscience grounding — Context Reinstatement:**

Term 3 IS the computational implementation of **context reinstatement** — the
mechanism by which the hippocampus retrieves episodic memories. In human memory,
a recall cue is most effective when it reinstates the encoding context:
the same location, emotional state, and social context as when the memory was formed.
The $\text{axis\_score}$ function is context reinstatement in math.

---

### The Critical Property: Orthogonal Failure Modes

Each term has an independent failure mode. The terms literally cover each other's
blind spots:

| Query | Term 1 (Centroid) | Term 2 (Satellite) | Term 3 (Structural) | Combined |
|-------|-------------------|---------------------|----------------------|----------|
| "Maya's dentist fear" | WEAK — 4% of episode | STRONG — dentist is a satellite | MEDIUM — social(Maya) + affective(fear) | STRONG |
| "Thursday morning routine" | STRONG — centroid IS routine | WEAK — routine events are not satellites | STRONG — temporal axis | STRONG |
| "when Dad had therapy" | MEDIUM — therapy event exists | MEDIUM — if therapy was unusual | STRONG — social(Dad) + activity | STRONG |
| "the time Maya cried" | WEAK — one event in cluster | STRONG — high affect satellite | STRONG — affective axis | STRONG |

**Formal statement:** The union of the three terms' coverage is the full event
space of the episode. A query that cannot be found by any single term alone
will be found by the combination, provided the query maps to at least one
non-zero term.

---

### Adaptive Weights: Query-Type Routing Inside the Scoring Function

The weights $\alpha$, $\beta$, $\gamma$ should not be fixed. They should shift
based on the detected type of the incoming query. This is **soft query routing**
inside the scoring function — no if/else at the retrieval architecture level.

```python
def adaptive_weights(query_context: QueryContext) -> tuple[float, float, float]:
    """
    Returns (alpha, beta, gamma) based on query signal profile.
    All weights sum to 1.0.
    """
    has_entity   = len(query_context.entities) > 0
    has_emotion  = query_context.affective_intensity > 0.5
    has_temporal = query_context.time_reference is not None
    is_specific  = query_context.specificity_score > 0.7  # short, noun-heavy query

    if is_specific and has_entity:
        # "Maya's dentist" — satellite term dominates
        return 0.2, 0.6, 0.2

    elif has_emotion and has_entity:
        # "when Maya was scared" — satellite + structural
        return 0.1, 0.5, 0.4

    elif has_temporal:
        # "last Thursday morning" — structural term dominates
        return 0.3, 0.1, 0.6

    elif has_emotion and not has_entity:
        # "the anxious time" — satellite (affect satellite) + some centroid
        return 0.2, 0.5, 0.3

    else:
        # "family routine", "our morning" — centroid dominates
        return 0.6, 0.2, 0.2
```

**Note on learning these weights:** The fixed values above are an initial prior.
As the system accumulates retrieval feedback (which episodes the user actually
selects), the weights per query-type can be updated via simple logistic regression
or Bayesian update. No LLM required — just a 5×3 weight matrix.

---

### Architecture: The Formula AS a System

```
                    ┌─────────────────────────────────┐
                    │         QUERY q                  │
                    │  (embedding + structured context) │
                    └──────────┬──────────────────────┘
                               │
                    ┌──────────▼──────────┐
                    │  adaptive_weights() │
                    │  → (α, β, γ)        │
                    └──────────┬──────────┘
                               │
              ┌────────────────┼────────────────┐
              ▼                ▼                 ▼
      α·cos(q, μ_e)    β·Σ σ_k(q·w_k)²   γ·axis_score(q, A_e)
              │                │                 │
        CENTROID           SATELLITE          STRUCTURAL
        H6.4 / H2.1        H2.3 / H6.3        H6.1 axes
        (PCA mean)         (convex hull verts) (context reinstatement)
              │                │                 │
              └────────────────┼─────────────────┘
                               │
                          score(q, e)
                               │
                        RRF fusion (H5.4)
                        across all episodes
                               │
                    cross-encoder re-rank (H5.1)
                               │
                         TOP-K EPISODES
                         + matched term explanation
                           (WHY this episode was retrieved)
```

**Interpretability dividend:** Because the three terms are independent, we can
explain every retrieval:

```
"Episode 37 matched your query because:
  - Satellite: dentist_visit event (novelty=0.87, affect=0.72) matched strongly
  - Social axis: Maya is a participant (jaccard=1.0)
  - Centroid: weak match (0.31) — episode is mostly about routine"
```

No black box. Every retrieval is fully auditable.

---

### H6.7 — The Query Understanding Layer (K1 as Query Parser)

**The one open problem in the unified formula:**

Term 3 requires structured `query_context` — entities, affect, time reference,
location. But the user query arrives as natural language:
*"remember when Maya was scared about something at the doctor?"*

We need to decompose this into:

```python
QueryContext(
    embedding       = ultrabert.encode(query_text),   # Term 1 + 2
    entities        = ["Maya"],                        # Term 3: social axis
    affective       = AffectVector(valence=-0.7, arousal=0.8),  # Term 3: affective
    location_type   = "medical_setting",               # Term 3: spatial axis
    time_reference  = None,                            # Term 3: temporal (unknown)
    specificity     = 0.75,                            # weight routing
    thread_id       = None,                            # narrative axis
)
```

**This is the query understanding layer — and it maps directly to K1.**

K1's role in retrieval:

```
User natural language query
        │
   K1 Planner / Concierge
        │ (entity extraction, affect detection, temporal parsing)
        ▼
   QueryContext (structured)
        │
   unified_score(q, episodes)
        │
   ranked episodes with explanations
        │
   K1 response generation (no LLM — template from episode structure)
```

**K1 IS the query understanding layer.** The retrieval formula is the kernel.
They are two halves of the same system — the point where K1 architecture and
K0 memory architecture meet.

**Query decomposition without LLM:**

- **Entity extraction**: already done by M08 NER pipeline — apply same pipeline to query text
- **Affect detection**: embed query, measure cosine similarity to valence/arousal prototype vectors
- **Temporal parsing**: regex + rule-based ("last Thursday", "yesterday", "this morning")
- **Specificity score**: noun phrase density (high nouns = specific) vs. verb density (high verbs = abstract)
- **Location type**: match against known location taxonomy (home, medical, school, etc.)

All of these are deterministic rule-based or embedding-based. Zero LLM dependency.

---

### Open Research Questions (Ranked by Urgency)

**Q1 — Satellite selection criterion:**
How many satellites K? What threshold novelty_k makes an event a satellite?
Candidate answer: retain events where novelty_k > mean(novelty) + 1.5*std(novelty).
This is a statistical outlier test on the episode's own distribution.

**Q2 — Weight learning:**
Are $\lambda_1, \lambda_2, \lambda_3$ (salience weights) and $\omega_{\text{axis}}$ (axis weights)
universal, or do they vary by episode type? A routine-heavy episode and a
crisis-episode may have different salience structures.

**Q3 — Mahalanobis vs. PCA equivalence:**
Claim: the PCA formulation in H6.4 and Mahalanobis distance in H6.2 are
equivalent when using the full covariance, but diverge under diagonal approximation.
The diagonal approximation (per-dimension variance only, no cross-correlations)
loses the off-diagonal information — it cannot capture "this episode is about
dentists AND fear together." Verifying this divergence and quantifying the cost
of diagonal approximation is a concrete research task.

**Q4 — Convex hull geometry:**
The convex hull vertices (H6.3) and the statistical outliers (satellites in H2.3)
should be the same events. Is this true? Formally: are the events farthest from
the centroid always vertices of the convex hull?
Answer: Yes in Euclidean space. In cosine space (normalized vectors on a sphere),
the geometry changes — the "hull" becomes a spherical cap. The satellite selection
criterion may need to use angular distance, not Euclidean distance.

**Q5 — Causal edge detection (H6.5 formalization):**
Define the causal edge criterion purely from observables:
$$\text{causal}(e_i, e_j) = \mathbb{1}[\Delta t_{ij} < \tau] \cdot \mathbb{1}[\cos(v_i, v_j) > \theta] \cdot \mathbb{1}[|\text{valence}_j - \text{valence}_i| > \delta]$$
What are the right values of $\tau$ (time window), $\theta$ (semantic continuity),
$\delta$ (emotional shift)? This requires empirical calibration on the 600-event dataset.

**Q6 — The entropy fingerprint as a pre-filter:**
H6.6's semantic entropy $H_e$ is a single scalar per episode.
Can it serve as a query-type router? Low entropy episodes respond best to Term 1
(centroid). High entropy episodes respond best to Term 2 (satellites).
$$\text{effective}\_\alpha = \alpha \cdot e^{-\lambda H_e}, \quad \text{effective}\_\beta = \beta \cdot (1 - e^{-\lambda H_e})$$
As entropy increases, weight shifts automatically from centroid to satellite term.
This is entropy-driven adaptive weighting — no need for explicit query-type detection.

---

---

# Part II: Research Execution Plan

## Q1 — Satellite Selection Criterion (5 Options)

**The question:** How many satellites K, and what novelty threshold?

**Option 1.1 — Statistical Outlier Test**

```python
threshold = mean(novelty_k) + 1.5 * std(novelty_k)
satellites = [e for e in events if novelty_e > threshold]
K = dynamic (varies per episode)
```

Self-calibrating per episode, statistically grounded. Risk: high-variance episodes
get too many satellites, low-variance episodes get zero.

**Option 1.2 — Fixed-K Top Outliers**

```python
K = 3  # fixed
satellites = top_K_by_novelty(events, K=3)
```

Bounded storage, predictable. Risk: K=3 wrong for 2-event vs 45-event episodes.
Ablate K in {1,2,3,5,7} against retrieval MRR.

**Option 1.3 — Elbow Detection on Novelty Distribution**

```python
sorted_novelty = sorted([novelty_k for k in events], reverse=True)
K = elbow_point(sorted_novelty)  # find the "knee" in the curve
```

Data-driven K per episode, finds natural gap in novelty distribution.
Noisy on small episodes (2-5 events). Implementation: `kneed` KneeLocator.

**Option 1.4 — Coverage-Based Selection (Until Variance Explained)**

```python
target_coverage = 0.90
satellites = []
while explained < target_coverage:
    next_satellite = max(remaining, key=novelty)
    satellites.append(next_satellite)
    explained = recompute_coverage(centroid, satellites)
```

Guarantees semantic coverage. Links directly to Q3 — coverage IS variance explained.

**Option 1.5 — Affective-Gated Novelty (FamilyOS-Specific)**

```python
satellite_score = novelty_k * affective_intensity_k
threshold = mean(satellite_score) + 1.0 * std(satellite_score)
satellites = [e for e in events if satellite_score_e > threshold]
```

Aligns with hippocampal memory — emotionally salient events ARE better remembered.
Neuroscience basis: amygdala-hippocampus interaction gates episodic encoding.
**This is the FamilyOS moat option — pure IR systems cannot do this.**

---

## Q2 — Weight Learning (lambda and omega universality)

**The question:** Are salience weights universal or episode-type specific?

**Option 2.1 — Manual Stratification by Episode Type**

```python
episode_types = {
    "routine":   {"lam_affect": 0.2, "lam_novelty": 0.5, "lam_importance": 0.3},
    "crisis":    {"lam_affect": 0.6, "lam_novelty": 0.2, "lam_importance": 0.2},
    "milestone": {"lam_affect": 0.4, "lam_novelty": 0.3, "lam_importance": 0.3},
    "medical":   {"lam_affect": 0.5, "lam_novelty": 0.3, "lam_importance": 0.2},
}
```

Interpretable, domain-knowledge-driven. Needs episode type classifier.

**Option 2.2 — Grid Search on 600-Event Benchmark**

Construct 50 test queries with known ground truth episodes. Grid search over weight space.
Start with 20 queries x 3 weight dimensions = manageable grid.

**Option 2.3 — Entropy-Driven Weight Adaptation (Connects Q2 to Q6)**

```python
lam_affect  = base_affect  * (1 + H_e)
lam_novelty = base_novelty * exp(-H_e)
lam_import  = 1 - lam_affect - lam_novelty
```

Continuous, no type labels needed. Assumes entropy correlates with crisis/routine.

**Option 2.4 — Meta-Learning (MAML-Style) Per Episode Type**

```python
features = [episode.mean_affect, episode.event_count, episode.H_e,
            episode.participant_count, episode.time_span_hours]
weight_predictor = MLP(input=5, hidden=16, output=3)  # predicts lambdas
```

Fully adaptive. 88 episodes x 10 queries = 880 training pairs (borderline).

**Option 2.5 — Bayesian Prior + Online Update**

```python
prior = {"lam_affect": 0.33, "lam_novelty": 0.33, "lam_import": 0.33}

def update_weights(episode_id, query, was_relevant: bool):
    contribution = decompose_score(query, episode_id)
    return bayes_update(prior, contribution, was_relevant)
```

Improves with usage, personalizes to each family's query patterns.
**This is the long-term right answer** — FamilyOS learns each family's memory
retrieval style.

---

## Q3 — Mahalanobis vs PCA Equivalence

**The question:** Does diagonal approximation lose "dentist AND fear together"?

**Option 3.1 — Direct Empirical Divergence Measurement**

Compute full Mahalanobis, diagonal Mahalanobis, and PCA distance for all episode
pairs. Measure Spearman rho. If rho < 0.9, divergence is significant.

**Option 3.2 — Synthetic "Joint Signal" Episode**

Build a synthetic episode where "dentist" AND "fear" only co-occur. Diagonal cannot
distinguish "dentist-only" from "dentist+fear" (ignores off-diagonal). Full Mahalanobis
can. Controlled experiment isolating the co-occurrence effect.

**Option 3.3 — Off-Diagonal Energy Ratio**

```python
Sigma = covariance_matrix(event_embeddings)  # 768x768
diagonal_energy     = sum(diag(Sigma))
off_diagonal_energy = frobenius_norm(Sigma) - diagonal_energy
ratio = off_diagonal_energy / frobenius_norm(Sigma)
# If ratio > 0.1, diagonal approximation loses >10% of signal
```

Single number answering the question. Use `LedoitWolf` shrinkage for regularization.

**Option 3.4 — Kernel Approximation Study**

Nystrom approximation with RBF kernel bypasses covariance estimation entirely.
Compare retrieval quality: diagonal vs Nystrom vs full kernel.

**Option 3.5 — Sparse Precision Matrix (Graphical LASSO)**

```python
from sklearn.covariance import GraphicalLassoCV
model = GraphicalLassoCV().fit(event_embeddings)
precision_matrix = model.precision_  # sparse Sigma^{-1}
```

Best of both worlds — sparse but captures real co-occurrences.
Need PCA reduction to 50-100 dims first (600 samples << 768 features).

---

## Q4 — Convex Hull Geometry in Cosine Space

**The question:** Do statistical outliers = convex hull vertices on the sphere?

**Option 4.1 — Direct Geometric Verification (PCA-3D)**

PCA reduce to 3D, compute ConvexHull, compare vertices to distance outliers.
Measure overlap percentage on 5 diverse episodes.

**Option 4.2 — Angular vs Euclidean Distance Comparison**

```python
euclidean_outliers = rank_by_euclidean_distance_from_centroid(events)
angular_outliers   = rank_by_angular_distance_from_centroid(events)
rank_correlation = spearman(euclidean_outliers, angular_outliers)
```

If rho < 0.85, the two metrics select DIFFERENT satellites. Quantifies the spherical
geometry effect directly.

**Option 4.3 — Spherical Cap Analysis**

```python
spherical_extremity = lambda e: min(cosine_sim(e, other) for other in events)
```

Geometrically correct for cosine space. O(N^2) per episode.

**Option 4.4 — Minimum Enclosing Ball vs Convex Hull**

MEB surface points = events near the boundary = farthest from center = distance outliers.
Proves satellite selection has MEB geometric interpretation.

**Option 4.5 — Empirical Retrieval Comparison**

Skip the theory. Test 3 conditions against retrieval quality:
A) satellites = hull vertices (in PCA-50 space)
B) satellites = distance outliers (Euclidean)
C) satellites = angular outliers (cosine)
Whichever wins IS the correct selection criterion for FamilyOS.

---

## Q5 — Causal Edge Detection

**The formula:**
$$\text{causal}(e_i, e_j) = \mathbb{1}[\Delta t_{ij} < \tau] \cdot \mathbb{1}[\cos(v_i, v_j) > \theta] \cdot \mathbb{1}[|\text{valence}_j - \text{valence}_i| > \delta]$$

**Option 5.1 — Empirical Calibration (Manual Annotation)**

Label 50 event pairs as causal/not-causal. Grid search tau in {5,10,15,30,60} min,
theta in {0.5,0.6,0.7,0.8,0.9}, delta in {0.1,0.2,0.3,0.4,0.5} to maximize F1.

**Option 5.2 — Domain Prior Initialization**

From neuroscience literature:

- tau = 15 min (working memory consolidation window)
- theta = 0.65 (semantic coherence for causation, Trabasso & van den Broek 1985)
- delta = 0.25 (perceptible affective shift in affective computing literature)
Then fine-tune on data.

**Option 5.3 — Soft Scoring (No Hard Thresholds)**

```python
def causal_score(e_i, e_j):
    temporal  = exp(-dt_ij / tau)                    # exponential decay
    semantic  = cos(v_i, v_j)                        # soft, no threshold
    affective = tanh(abs(valence_j - valence_i) / delta)  # soft sigmoid
    return temporal * semantic * affective
```

Differentiable, learnable, robust to calibration errors.

**Option 5.4 — Granger Causality on Valence Time Series**

Use `statsmodels.tsa.stattools.grangercausalitytests` on per-episode valence series.
Needs 5+ events minimum. Best for detecting emotional contagion patterns.

**Option 5.5 — K1-Assisted Causal Annotation + Distillation**

K1 labels all candidate pairs (dt < 30min) on the 600-event dataset (~200 pairs).
Then calibrate tau, theta, delta against K1's labels.
Fastest path to calibrated causal detection.

---

## Q6 — Entropy Fingerprint as Pre-Filter

**The formula:**
$$\alpha_{\text{eff}} = \alpha \cdot e^{-\lambda H_e}, \quad \beta_{\text{eff}} = \beta \cdot (1 - e^{-\lambda H_e})$$

**Option 6.1 — Empirical lambda Calibration**

Compute H_e for all 88 episodes. Plot distribution. Find lambda that best separates
episode types. Runnable TODAY with zero labeling.

**Option 6.2 — Per-Axis Entropy Decomposition**

```python
H_semantic = entropy(event_topic_distribution)
H_affect   = entropy(event_valence_distribution)
H_social   = entropy(event_participant_distribution)
```

Captures "routine semantics but crisis affect" correctly. Richer than scalar H_e.

**Option 6.3 — Entropy Fingerprint Clustering**

```python
fingerprints = [(H_sem, H_aff, H_soc) for ep in episodes]
clusters = KMeans(n_clusters=4).fit(fingerprints)
# Cluster 0: low/low → routine → alpha-dominant
# Cluster 1: low/high → emotional routine → beta+gamma
# Cluster 2: high/high → crisis → beta-dominant
# Cluster 3: high/low → planning → alpha+gamma
```

Discovers episode types from data. **Answers Q2 simultaneously.**

**Option 6.4 — Entropy Rate vs Static Entropy**

```python
H_static = semantic_entropy(episode)           # distribution of topics
H_rate   = conditional_entropy(episode)        # topic transition speed
```

H_rate captures NARRATIVE COHERENCE that static entropy misses. A crisis episode
has high H_static but low H_rate (each event follows from previous). A scattered
episode has high both. Connects to Event Segmentation Theory.

**Option 6.5 — Mutual Information Validation**

```python
MI = mutual_information(entropies, winning_terms)
# If MI > 0.3 bits, entropy-driven routing is justified
```

**Validation gate** — run before implementing entropy-adaptive weights.

---

---

# Part III: Master Research Inventory

Every research item across all 6 categories, why it is required, what it depends on,
and when it can be executed.

---

## Tier 0 — Foundational (Must Be Done Before Anything Else)

| ID | Research Item | Why Required | Source | Dependencies | Data Needed |
|----|--------------|-------------|--------|-------------|-------------|
| R0.1 | **Build benchmark query set** | Every evaluation metric (MRR, Recall@K, nDCG) needs ground truth query-episode pairs. Without this, no hypothesis can be empirically validated. | All categories | None | 50 queries + correct episode labels, manually constructed from 600 events |
| R0.2 | **Fix embedding_text bug** | Current episode embeddings use metadata labels (148 chars) not content (5020 chars). All episode-level retrieval experiments are meaningless until this is fixed. The bug: `_generate_summary()` short-circuits on `record_data["episode_summary"]`. | Bug identified in root cause analysis | None | Code change to EpisodicTextGenerator |
| R0.3 | **Extract episode structural metadata** | Term 3 (structural signal) needs per-episode participant sets, time windows, place_ids, affective means. Must be materialized from st_hipp_events before any axis_score computation. | H6.1, H6.7, Term 3 | R0.2 | SQL aggregation from st_hipp_events + st_epi |
| R0.4 | **Compute event-level novelty scores** | Satellite selection (all Q1 options) needs per-event novelty = 1 - cosine(event, centroid). Must be precomputed for the full 600-event corpus. | H2.3, Q1 all options | Event embeddings in st_vec | 600 event embeddings + 88 centroids |

---

## Tier 1 — Computations Needing No Labels (Week 1)

| ID | Research Item | Why Required | Source | Dependencies | Data Needed |
|----|--------------|-------------|--------|-------------|-------------|
| R1.1 | **Q1.1: Statistical outlier threshold** | Determines how many satellites each episode gets. Measures mean K per episode and distribution shape. If K=0 for some episodes or K>15 for others, this option is infeasible. | Q1 Option 1.1 | R0.4 | 600 event novelty scores |
| R1.2 | **Q1.3: Novelty elbow detection** | Alternative to fixed threshold — finds natural gap in novelty distribution per episode. Check if elbow EXISTS in small episodes (2-5 events). | Q1 Option 1.3 | R0.4 | Novelty scores per episode |
| R1.3 | **Q3.3: Off-diagonal energy ratio** | Single number answering "does diagonal approximation lose meaningful signal?" If ratio < 0.1, diagonal is fine and we save 768x storage. If > 0.3, full covariance is essential. | Q3 Option 3.3 | Event embeddings | 600 x 768 embedding matrix |
| R1.4 | **Q4.2: Angular vs Euclidean outlier rank correlation** | Determines whether satellite selection must use angular distance (cosine-aware) or Euclidean is sufficient. If Spearman rho > 0.95, doesn't matter. If < 0.85, angular is mandatory. | Q4 Option 4.2 | R0.4 | 600 event embeddings |
| R1.5 | **Q6.1: Entropy distribution across 88 episodes** | Fundamental descriptor of our episode corpus. Does entropy stratify episode types naturally? Is the distribution bimodal (routine vs crisis) or uniform? Determines if entropy-driven routing is viable. | Q6 Option 6.1 | Event embeddings | 88 episodes x their event sets |
| R1.6 | **Q6.2: Per-axis entropy decomposition** | Computes H_semantic, H_affect, H_social for each episode. Determines if axes are independently informative (social-diverse but semantically-monotone episodes exist?). | Q6 Option 6.2 | R0.3 | Episode metadata + embeddings |
| R1.7 | **Q6.4: Entropy rate computation** | Measures topic transition speed per episode. Distinguishes "coherent crisis" (high H_static, low H_rate) from "scattered mess" (high both). Connects to narrative structure. | Q6 Option 6.4 | Event embeddings + timestamps | Chronologically ordered event embeddings |
| R1.8 | **H1.2: MMR extraction prototype** | Implement MMR sentence selection on 5 sample episodes. Compare output quality to current metadata label. Measures information retention and diversity. | H1.2 | Event texts | 5 episodes x their event texts |
| R1.9 | **H1.5: Topic-segment clustering prototype** | Run mini k-means on event embeddings within episodes. How many natural topics exist in a 45-event episode? Is sqrt(N) a good heuristic for K? | H1.5 | Event embeddings | 5 diverse episodes |
| R1.10 | **H6.4: PCA over episode event clusters** | Compute principal components for 5 episodes. How many PCs explain 90% variance? Are minor PCs meaningful (do they correspond to real sub-topics like "dentist")? | H6.4 | Event embeddings | 5 diverse episodes |
| R1.11 | **H2.1: Centroid quality measurement** | For each episode, measure mean cosine similarity of centroid to each member event. This is the "dilution score." If mean < 0.5 for large episodes, centroid is useless for retrieval. | H2.1 | Event embeddings | All 88 episodes |
| R1.12 | **H6.2: Diagonal Gaussian prototype** | For each episode, compute per-dimension variance. Use Mahalanobis distance to rank episodes for test queries. Compare to plain cosine baseline. | H6.2 | Event embeddings | All 88 episodes + manual queries |
| R1.13 | **H3.1: Event-level search prototype** | Query st_vec directly with test query embeddings. Group results by episode. Measure if "dentist" query finds the right episode at event level even though episode centroid fails. | H3.1 | Event embeddings in st_vec | Test queries |
| R1.14 | **H1.3: Keyphrase extraction test** | Run TF-IDF or RAKE on event texts within an episode. How many unique keyphrases per episode? Do they capture "dentist", "therapy", "birthday"? | H1.3 | Event texts | 5 episodes |
| R1.15 | **UltraBERT token budget measurement** | Empirically measure how many event-text tokens fit in UltraBERT's 512-token window. Determines the ceiling for ALL Category 1 approaches. | All H1.x | UltraBERT model | 10 sample event texts of varying length |

---

## Tier 2 — Requires Benchmark / Annotation (Week 2)

| ID | Research Item | Why Required | Source | Dependencies | Data Needed |
|----|--------------|-------------|--------|-------------|-------------|
| R2.1 | **Q2.2: Grid search over weight space** | Finds optimal alpha, beta, gamma and lambda weights empirically. The unified scoring function cannot be tuned without this. | Q2 Option 2.2 | R0.1 (benchmark queries) | 50 queries x episode labels |
| R2.2 | **Q5.1: Causal edge calibration** | Determines tau, theta, delta for the causal edge formula. Without calibrated thresholds, H6.5 causal graphs are arbitrary. | Q5 Option 5.1 | 50 labeled event pairs | Manual causal annotation |
| R2.3 | **Q5.5: K1-assisted causal labeling** | Alternative to manual annotation — K1 labels candidate causal pairs. Faster, more scalable, but needs human spot-check. | Q5 Option 5.5 | K1 query pipeline | 600 events, ~200 candidate pairs |
| R2.4 | **Q4.5: Empirical hull vs outlier retrieval comparison** | Directly tests whether hull vertices, Euclidean outliers, or angular outliers produce better satellite-based retrieval. | Q4 Option 4.5 | R0.1 + R0.4 | Benchmark queries + satellite sets |
| R2.5 | **Q6.5: Mutual information validation** | Tests whether H_e actually predicts which retrieval term wins. If MI < 0.1, entropy routing is a waste. If MI > 0.3, it's validated. Validation gate for Q6 formula. | Q6 Option 6.5 | R0.1 + R1.5 | Benchmark queries + episode entropies |
| R2.6 | **H5.4: RRF fusion implementation** | 10 lines of code but needs multiple retrieval paths to exist first. Tests whether combining centroid + event + keyphrase search via RRF outperforms any single retriever. | H5.4 | R1.8 + R1.13 | Multiple retriever outputs |
| R2.7 | **Unified scoring function end-to-end test** | Wire up all three terms (centroid, satellite, structural) on 88 episodes. Evaluate against benchmark queries. This is the FIRST full test of the research formula. | Synthesis | R0.1 + R0.3 + R0.4 + R1.1 | Everything |
| R2.8 | **Adaptive weight routing test** | Categorize benchmark queries by type (entity, temporal, emotional, broad). Test if adaptive alpha/beta/gamma outperforms fixed weights. | Adaptive weights section | R2.1 + R2.7 | Categorized queries |
| R2.9 | **H1.6: Entity-centric text construction** | Build entity-organized embedding text for 5 episodes. Requires NER output from M08 already in st_hipp_events. Test entity-query retrieval quality. | H1.6 | NER data in events | 5 episodes |
| R2.10 | **H3.3: BM25 keyphrase index prototype** | Build inverted index over episode keyphrases. Test exact keyword retrieval ("dentist") vs dense vector retrieval. Measures the lexical-semantic gap. | H3.3 | R1.14 (keyphrases) | Keyphrases + benchmark queries |
| R2.11 | **H5.1: Cross-encoder re-ranking test** | Run ms-marco-MiniLM-L-6-v2 cross-encoder on top-50 candidates from any retriever. Measure nDCG lift. Determines if re-ranking justifies the latency cost. | H5.1 | Any retriever output | Candidate lists + queries |

---

## Tier 3 — Deeper Research (Week 3-4)

| ID | Research Item | Why Required | Source | Dependencies | Data Needed |
|----|--------------|-------------|--------|-------------|-------------|
| R3.1 | **Q3.1: Full Mahalanobis vs diagonal Spearman rho** | Quantifies exact retrieval quality loss from diagonal approximation. If rho > 0.95, diagonal is safe. If < 0.85, we need sparse precision (Q3.5). | Q3 Option 3.1 | R1.3 (energy ratio first) | Full covariance matrices |
| R3.2 | **Q3.5: Sparse precision via Graphical LASSO** | If off-diagonal matters (R1.3), this finds WHICH cross-dimensions matter. "Dentist-fear" co-occurrence becomes a non-zero off-diagonal entry. Best of both worlds. | Q3 Option 3.5 | R3.1 confirmation | PCA-50 event embeddings |
| R3.3 | **Q1.5: Affective-gated satellite selection** | Test novelty * affective_intensity product as satellite criterion. Compare to pure novelty (R1.1). If it improves retrieval on emotional queries, this is the FamilyOS differentiator. | Q1 Option 1.5 | R0.1 + R0.4 | Affective scores from events |
| R3.4 | **Q5.3: Soft causal scoring implementation** | Replace hard thresholds with differentiable exponential/tanh functions. Compare retrieval quality of causal-graph-augmented episodes vs non-augmented. | Q5 Option 5.3 | R2.2 or R2.3 | Calibrated tau, theta, delta |
| R3.5 | **Q6.3: Entropy fingerprint clustering** | K-means on (H_sem, H_aff, H_soc) space. Discovers episode typology from data. Each cluster gets its own optimal weights. Answers Q2 without manual labeling. | Q6 Option 6.3 | R1.5 + R1.6 | Per-axis entropies |
| R3.6 | **H2.3: Centroid+Satellite storage prototype** | Implement satellite storage in centroid_metadata_json or new columns. Test max-sim(query, centroid, satellites) retrieval. Measures storage cost vs quality gain. | H2.3 | R1.1 or R3.3 | Satellite vectors per episode |
| R3.7 | **H6.3: Convex hull membership distance** | For PCA-50 reduced embeddings, compute distance from query to episode convex hull. Compare to centroid cosine and Mahalanobis. Is hull-distance strictly better? | H6.3 | PCA reduction | Reduced embeddings + queries |
| R3.8 | **H1.4: Deduplication effectiveness** | How much redundancy exists in episode event texts? Measure cosine similarity distribution of consecutive events. If >30% have sim > 0.9, dedup is essential preprocessing for all H1.x methods. | H1.4 | Event embeddings | All events per episode |
| R3.9 | **H5.2: UltraBERT MLM head probe** | Check if UltraBERT retains its MLM head. If yes, extract MLM logits for SPLADE-like sparse representations without any new model. If no, need separate SPLADE model. | H5.2 | UltraBERT model | Model inspection |
| R3.10 | **H6.7: Query decomposition pipeline test** | Run M08 NER + temporal regex + affect prototype matching on 50 benchmark queries. Measure extraction accuracy. This validates the K1 query understanding layer. | H6.7 | R0.1 | Benchmark queries |
| R3.11 | **H4.1: MMR + Event search hybrid** | Combine H1.2 (better episode embedding via MMR) with H3.1 (event-level fallback). Use RRF (H5.4) to fuse. This is the first full composite hypothesis test. | H4.1 | R1.8 + R1.13 + R2.6 | Multiple retriever outputs |

---

## Tier 4 — Scale-Dependent (Month 2+)

| ID | Research Item | Why Required | Source | Dependencies | Data Needed |
|----|--------------|-------------|--------|-------------|-------------|
| R4.1 | **Q2.5: Bayesian online weight update** | Implements personalized weight learning from user feedback. Makes the system adapt to each family's retrieval style over time. | Q2 Option 2.5 | R2.7 (unified scoring running) | Real user feedback signal |
| R4.2 | **H5.3: Set Transformer training** | Train learned attention pooling over event embeddings. Needs 500+ episodes. Best payoff at scale when fixed pooling hits ceiling. | H5.3 | 500+ episodes | Contrastive training triples |
| R4.3 | **H5.5: Contrastive MLP training** | Train 2-layer MLP to project centroid toward all member events. Quick to train. Moderate improvement over naive centroid. | H5.5 | 500+ episodes | Contrastive training triples |
| R4.4 | **H5.7: Product Quantization for multi-vector** | Compress event embeddings to make H2.2 practical at scale. At 10K episodes * 50 events = 500K vectors, PQ reduces storage 20-50x. | H5.7 | 10K+ episodes | Large embedding corpus |
| R4.5 | **H5.6: Graph PPR on enriched KG** | PersonalizedPageRank over entity graph. Currently 74 edges (too sparse). At 1K+ edges, PPR propagation becomes meaningful. | H5.6 | Richer KG | st_kg_edges with 500+ edges |
| R4.6 | **H5.8: VAE episode compression** | Train autoencoder to compress N event embeddings into 1 latent. Information-theoretically optimal but needs 1000+ episodes. | H5.8 | 1000+ episodes | Large corpus |
| R4.7 | **H5.10: HNSW tiered index** | At 10K+ episodes, flat FAISS scan is too slow. Design the HNSW abstraction now. Swap implementation later. | H5.10 | 10K+ episodes | Scale test data |
| R4.8 | **H5.9: DPR passage re-chunking** | Re-chunk episode content into overlapping 100-token passages. Useful if events are very short and lack standalone semantic context. | H5.9 | R3.8 (dedup analysis) | Episode texts |
| R4.9 | **Q2.4: Meta-learning weight predictor** | Train MLP that predicts optimal (alpha, beta, gamma) from episode statistics. Needs training data from R2.1 and R2.7 accumulated over time. | Q2 Option 2.4 | R2.7 running for months | Thousands of (query, episode, relevance) triples |
| R4.10 | **H6.5: Full causal graph construction** | Build causal DAGs for all episodes using calibrated parameters from R2.2/R3.4. Enable causal queries ("why was Maya anxious?"). | H6.5 | R3.4 (soft scoring) | Calibrated causal parameters |

---

## Cross-Cutting Research Items

| ID | Research Item | Why Required | Source | Cuts Across |
|----|--------------|-------------|--------|-------------|
| RX.1 | **Dimensionality reduction study** | Many methods need PCA-reduced embeddings (Q3.5, Q4.1, H6.3). What is the right reduced dimensionality? 50? 100? Measure variance retained at each level. | Multiple | Q3, Q4, H6.3, H6.4 |
| RX.2 | **UltraBERT embedding quality audit** | Are current 768-dim embeddings high quality for family episodic text? Measure intra-topic cohesion and inter-topic separation. If embeddings are noisy, ALL approaches degrade. | Foundation | All categories |
| RX.3 | **Retrieval evaluation framework** | Standardize metrics (MRR, Recall@5, Recall@10, nDCG@10). Build a reusable harness that any hypothesis can plug into. Without this, comparisons are ad-hoc. | Foundation | All evaluations |
| RX.4 | **Query type taxonomy** | Classify queries into: entity, temporal, emotional, broad, causal, cross-episode. Each type has a different expected best retrieval path. The adaptive weights table depends on this taxonomy. | H6.7, Adaptive weights | Term 3, Q2 |
| RX.5 | **Episode size distribution analysis** | How many events per episode (min, max, median, distribution)? Small episodes (2-3 events) need different strategies than large ones (30-45). Some hypotheses only work for large episodes (H1.5 topic segment, H6.4 PCA). | All | H1.5, H6.4, Q1 |
| RX.6 | **Re-embedding cost model** | Any H1.x change requires re-embedding all episodes. What is the wall-clock cost? If re-embedding 88 episodes takes 5 minutes, iterating is cheap. If 2 hours, we need batch strategies. | All H1.x, H6.2 | All text-change approaches |
| RX.7 | **Latency budget profiling** | Measure current retrieval latency (FAISS lookup, DB query, embedding generation). Sets the ceiling for multi-stage approaches (H5.1 re-ranking adds ~100ms, RRF adds ~50ms). | H5.1, H5.4, H4.x | All composite approaches |

---

## Research Dependency Graph

```
R0.1 (benchmark queries)
  ├── R2.1 (grid search)
  ├── R2.4 (hull vs outlier retrieval)
  ├── R2.5 (MI validation)
  ├── R2.7 (unified scoring test)
  │     ├── R2.8 (adaptive weights)
  │     ├── R4.1 (Bayesian update)
  │     └── R4.9 (meta-learning)
  ├── R2.11 (cross-encoder test)
  └── R3.10 (query decomposition)

R0.2 (fix embedding_text bug)
  ├── R0.3 (structural metadata)
  │     ├── R1.6 (per-axis entropy)
  │     │     ├── R3.5 (entropy clustering)
  │     │     └── Q6.3 (episode type discovery)
  │     └── R2.7 (unified scoring)
  └── All H1.x text experiments

R0.4 (event novelty scores)
  ├── R1.1 (outlier threshold)
  ├── R1.2 (elbow detection)
  ├── R3.3 (affective-gated satellites)
  └── R3.6 (satellite storage)

R1.3 (off-diagonal energy)
  ├── if > 0.1 → R3.1 (full Mahalanobis)
  │                 └── R3.2 (Graphical LASSO)
  └── if < 0.1 → diagonal is sufficient, skip R3.1/R3.2

R1.5 (entropy distribution)
  ├── R1.7 (entropy rate)
  ├── R2.5 (MI validation)
  └── R3.5 (entropy clustering)

R1.8 (MMR prototype) + R1.13 (event search)
  └── R2.6 (RRF fusion)
        └── R3.11 (full hybrid H4.1)
```

---

## Execution Timeline Summary

**WEEK 1 — Zero-label computations (15 items, all from existing data):**

R0.4, R1.1, R1.2, R1.3, R1.4, R1.5, R1.6, R1.7, R1.8, R1.9,
R1.10, R1.11, R1.12, R1.13, R1.14, R1.15, RX.1, RX.2, RX.5

**WEEK 2 — Build benchmark + first evaluations (11 items):**

R0.1, R0.2, R0.3, R2.1, R2.6, R2.7, R2.8, R2.9, R2.10, R2.11, RX.3

**WEEK 3-4 — Deeper research + validation (11 items):**

R2.2/R2.3, R2.4, R2.5, R3.1, R3.3, R3.5, R3.6, R3.7, R3.8, R3.10, R3.11

**MONTH 2+ — Scale-dependent (10 items, need more data):**

R4.1 through R4.10

---

---

# Part IV: Missing Research Items (UltraBERT-Only Constraint Audit)

After full re-read of the catalog + code inspection of the actual UltraBERT adapter
and episode embedding pipeline, the following gaps were identified.

---

## UltraBERT Hard Constraints (From Code)

```python
# k0/runtime/ultrabert_adapter.py
def get_embedding(text: str) -> list[float] | None:
    """768-dimensional embedding vector"""
    return client.get_embedding(text)

# k0/modules/consolidation/algorithms/embedding_text_generator.py
MAX_TEXT_LENGTH = 2000  # chars ~ 500 tokens (base class)

# k0/modules/consolidation/truth_writer/embedding_generator.py
MODEL_ID = "ultrabert-v2.1.0"
DIMENSION = 768
MAX_TEXT_LENGTH = 2000  # truncates before embedding

# k0/modules/consolidation/reconciliation/hooks/centroid_recompute.py
# For st_epi: computes weighted centroid of member event embeddings
# Does NOT re-embed from text — vector-space operation only
```

**Critical fact:** Episode embeddings are NOT generated by embedding text.
They are computed as weighted centroids of event embeddings via CentroidCalculator.
The `embedding_text` field exists for human readability and debugging but is NOT
what gets embedded into st_vec for episodes.

This means:

- **All Category 1 (H1.x) text construction approaches** would need a NEW code path
  that embeds the constructed text via `get_embedding(text)` and stores THAT as the
  episode vector, INSTEAD of using the centroid
- The current path: events -> CentroidCalculator.compute_centroid() -> st_vec
- The proposed path: events -> text_generator -> get_embedding(text) -> st_vec
- Research must determine which path produces better retrieval

---

## Additional Research Items

| ID | Research Item | Why Required | Source | Dependencies |
|----|--------------|-------------|--------|-------------|
| R0.5 | **Centroid vs text-embed episode vector** | The current pipeline uses CentroidCalculator (weighted mean of event vectors) to produce the episode embedding. H1.x approaches would instead produce a text and embed it. We must empirically test: does centroid or text-embed produce better retrieval? This is the FORK POINT for the entire research — it determines whether we invest in text construction (H1.x) or vector-space methods (H2.x/H6.x). | centroid_recompute.py + EpisodicTextGenerator | R0.1, R0.2 |
| R0.6 | **UltraBERT normalization behavior** | Does `client.get_embedding(text)` return L2-normalized vectors? CentroidCalculator has a `normalize` flag. If UltraBERT returns normalized vectors and centroid re-normalizes, that's correct. If UltraBERT returns unnormalized vectors and we normalize the centroid but not the events, cosine distances are distorted. Must verify empirically. | ultrabert_adapter.py | UltraBERT model |
| R1.16 | **Centroid dilution quantification** | For each of the 88 episodes, compute: (a) mean cosine(centroid, member_events), (b) mean cosine(centroid, NON-member_events), (c) the ratio (a)/(b). If ratio < 1.5, the centroid is barely more similar to its own events than to random events — centroid is useless for retrieval. This is the quantitative death certificate for naive centroid. | H2.1 analysis | R0.4 |
| R1.17 | **Episode size vs centroid quality** | Plot centroid dilution (R1.16) against episode event count. Hypothesis: centroid quality degrades with episode size. If true, small episodes (2-5 events) work fine with centroid, large episodes (20-45 events) need satellites/multi-vector. This determines whether the solution needs to be adaptive by episode size. | R1.16 extension | R1.16 |
| R1.18 | **UltraBERT 2000-char capacity test** | Feed texts of 500, 1000, 1500, 2000 chars to `get_embedding()`. Measure: (a) does it silently truncate internally? (b) does embedding quality degrade past 512 tokens? (c) what is the EFFECTIVE token limit? The 2000-char MAX_TEXT_LENGTH assumes ~4 chars/token, but UltraBERT's actual tokenizer may differ. | All H1.x approaches | UltraBERT model |
| R3.12 | **UltraBERT cross-encoder capability** | H5.1 proposed using ms-marco-MiniLM-L-6-v2 as cross-encoder. But we are UltraBERT-only. Test: can UltraBERT be used in cross-encoder mode? Feed `[CLS] query [SEP] episode_text [SEP]` and extract the [CLS] logit as a relevance score. If UltraBERT has an NSP or NLI head, it CAN cross-encode. The adapter already exposes `nli` capability. | H5.1 constraint reconciliation | UltraBERT model |
| R3.13 | **UltraBERT MLM head for SPLADE** | H5.2 (SPLADE) requires MLM logits. UltraBERT docstring lists 12 capabilities but MLM is not among them. Check: does the underlying model retain its MLM head? If `client.analyze()` or the raw model exposes MLM logits, we can build SPLADE-like sparse representations WITHOUT a second model. If not, H5.2 is eliminated. | H5.2 constraint reconciliation | UltraBERT model |
| R3.14 | **NLI-based re-ranking via UltraBERT** | UltraBERT has an `nli` capability (Natural Language Inference). NLI can be repurposed for re-ranking: premise="episode_text", hypothesis="query" → entailment score = relevance. This is a UltraBERT-native alternative to H5.1 cross-encoder re-ranking. Test: does NLI entailment score correlate with retrieval relevance? | H5.1 alternative | UltraBERT model |

---

## Hypothesis Eliminations (UltraBERT-Only Filter)

After auditing against the UltraBERT-only constraint:

| Hypothesis | Status | Reason |
|-----------|--------|--------|
| H5.1 Cross-Encoder (ms-marco-MiniLM) | **BLOCKED** — needs R3.12 | Proposed model is not UltraBERT. Must test if UltraBERT NLI head can substitute. If R3.12 fails AND R3.14 fails, H5.1 is eliminated. |
| H5.2 SPLADE (naver/splade-cocondenser) | **BLOCKED** — needs R3.13 | Proposed model is not UltraBERT. Must check if UltraBERT has MLM head. If R3.13 fails, H5.2 is eliminated entirely. |
| H5.3 Set Transformer | **OK** — uses frozen UltraBERT embeddings as input | No new encoder model. The Set Transformer is a tiny pooling head on top. |
| H5.5 Contrastive MLP | **OK** — uses frozen UltraBERT embeddings as input | No new encoder model. |
| H5.6 Graph PPR | **OK** — no embedding model involved | Pure graph structure. |
| H5.7 PQ Multi-Vector | **OK** — compresses existing UltraBERT embeddings | No new encoder model. |
| H5.8 VAE | **OK** — operates on frozen UltraBERT embeddings | No new encoder model. |
| H5.9 DPR Passages | **OK if** text is embedded via UltraBERT `get_embedding()` | Must use UltraBERT, not a DPR-specific encoder. |
| H5.10 HNSW | **OK** — index structure, not an encoder | No model involved. |

---

---

# Part V: The Final Answer — Episode Embedding Architecture

> How do we generate episode embeddings, how do we store them,
> and how do we retrieve from them — using UltraBERT only?

---

## The Current Broken Pipeline

```
Events (N=2..45)
    │
    ├── event texts → UltraBERT.get_embedding(text) → 768-dim event vectors
    │                                                     stored in st_vec
    │
    └── CentroidCalculator.compute_centroid(event_vectors, weights)
            │
            └── weighted mean → single 768-dim episode centroid
                                   stored in st_vec via embedding_id

    EpisodicTextGenerator._generate_summary()
            │
            └── SHORT-CIRCUITS on record_data["episode_summary"]
                which is cluster.title = "Routine with Maya, Panda at Home Kitchen"
                → 148 chars of metadata labels
                → stored as embedding_text (for humans only, NOT embedded)
```

**What is broken:**

1. Episode vector = naive weighted centroid → dilutes all signal for large episodes
2. embedding_text = metadata label → useless for debugging/auditing
3. No satellite vectors → outlier events invisible to episode-level search
4. No structural metadata → temporal/social/spatial queries impossible
5. No event-level search path → all retrieval goes through diluted centroid

---

## The Target Architecture (3-Layer Approach)

### Layer 1: The Episode Vector (stored in st_vec, linked by embedding_id)

**Generation method — adaptive by episode size:**

```python
def generate_episode_embedding(episode_events, event_embeddings):
    N = len(episode_events)

    if N <= 5:
        # Small episode: centroid is fine, minimal dilution
        # Use importance-weighted centroid (existing CentroidCalculator)
        return weighted_centroid(event_embeddings, strategy="importance")

    else:
        # Large episode: centroid dilutes signal
        # Use MMR-selected diverse text → embed with UltraBERT
        texts = [e.body for e in episode_events]
        mmr_texts = mmr_select(texts, event_embeddings, k=min(7, N), lambda_=0.5)
        embedding_text = build_episode_text(
            temporal_context=episode.temporal_context,
            mmr_sentences=mmr_texts,
            participants=episode.participants,
            location=episode.location,
        )
        # Embed with UltraBERT — this IS the episode vector
        return ultrabert.get_embedding(embedding_text)  # 768-dim
```

**Why this fork:**

- Small episodes (2-5 events): centroid retains 40-100% per-event weight. Dilution is
  manageable. Centroid is the mathematically optimal summary.
- Large episodes (20-45 events): centroid retains 2-5% per-event weight. Signal destroyed.
  MMR text selection preserves diverse topics in the 2000-char budget, then UltraBERT
  embeds that diverse text into a single vector that captures ALL major themes.

**The 2000-char budget with MMR:**

- 7 MMR-selected sentences x ~250 chars each = ~1750 chars
- Plus temporal/location/participant prefix = ~200 chars
- Total: ~1950 chars — fits the MAX_TEXT_LENGTH = 2000 limit
- Each sentence selected for DIVERSITY — "dentist" gets a slot even if it's 1 of 45 events

**Key:** The embedding_text is now BOTH the debugging artifact AND the source for
the episode vector. One text, one embedding, one truth.

---

### Layer 2: Satellite Vectors (stored in centroid_metadata_json or new columns)

```python
def compute_satellites(episode_events, event_embeddings, centroid):
    # Compute per-event salience score
    for i, event in enumerate(episode_events):
        novelty_i = 1 - cosine_similarity(event_embeddings[i], centroid)
        affect_i  = event.affective_intensity  # from M04
        importance_i = event.importance_score   # from R1

        salience_i = (0.33 * affect_i + 0.34 * novelty_i + 0.33 * importance_i)
        event.salience = salience_i

    # Select satellites: events with salience > mean + 1.0 * std
    mean_s = mean([e.salience for e in episode_events])
    std_s  = std([e.salience for e in episode_events])
    threshold = mean_s + 1.0 * std_s

    satellites = [e for e in episode_events if e.salience > threshold]

    # Cap at K=5 to bound storage
    satellites = sorted(satellites, key=lambda e: e.salience, reverse=True)[:5]

    return [
        {
            "event_id": s.event_id,
            "embedding_id": s.embedding_id,  # reference to st_vec
            "salience": s.salience,
            "novelty": s.novelty,
            "affect": s.affective_intensity,
        }
        for s in satellites
    ]
```

**Storage:** In `centroid_metadata_json` (already exists on st_epi):

```json
{
    "satellites": [
        {"event_id": "evt_123", "embedding_id": "emb_456", "salience": 0.87},
        {"event_id": "evt_789", "embedding_id": "emb_012", "salience": 0.74}
    ],
    "satellite_count": 2,
    "entropy_fingerprint": {"H_semantic": 2.3, "H_affect": 1.1, "H_social": 0.8}
}
```

**No schema change required.** centroid_metadata_json is an existing TEXT column.
Satellite embedding_ids reference existing rows in st_vec (event embeddings).

---

### Layer 3: Structural Metadata (already exists in st_epi columns)

These columns already exist in the st_epi schema (migration 0027 + subsequent):

| Field | Column | Usage in Term 3 |
|-------|--------|-----------------|
| WHO | participants_json, participant_count | Jaccard similarity with query entities |
| WHERE | primary_location, location_type | Exact/fuzzy match with query place |
| WHEN | start_time_utc, end_time_utc, temporal_bucket, day_of_week | Temporal overlap |
| WHAT | episode_type, activity_type | Activity type match |
| AFFECT | (needs aggregation at write time) | Mean valence comparison |

**One new column needed:** `mean_valence` (REAL, nullable) — the average affective
valence of all member events. Computed at episode creation time from M04 affect scores.
Everything else is already stored.

---

## Retrieval: The Unified Scoring Function (UltraBERT-Native)

```python
async def retrieve_episodes(query_text: str, top_k: int = 10):
    # Step 1: Embed query with UltraBERT (same model as all stored vectors)
    q = ultrabert.get_embedding(query_text)  # 768-dim

    # Step 2: Extract query structure (no LLM — deterministic pipeline)
    query_ctx = extract_query_context(query_text)
    #   entities:  M08 NER pipeline applied to query
    #   affect:    ultrabert.analyze(query_text).valence
    #   temporal:  regex temporal parser
    #   location:  keyword match against location taxonomy

    # Step 3: Compute adaptive weights
    alpha, beta, gamma = adaptive_weights(query_ctx)

    # Step 4: Score all episodes
    scores = {}
    for episode in all_episodes:
        # Term 1: Centroid similarity
        t1 = alpha * cosine_similarity(q, episode.embedding_vector)

        # Term 2: Satellite similarity (max-sim over satellites)
        t2 = 0.0
        if episode.satellites:
            for sat in episode.satellites:
                sat_vec = load_vector(sat["embedding_id"])  # from st_vec
                sim = cosine_similarity(q, sat_vec)
                t2 = max(t2, sat["salience"] * sim)
            t2 *= beta

        # Term 3: Structural axis matching
        t3 = gamma * axis_score(query_ctx, episode)

        scores[episode.episode_id] = t1 + t2 + t3

    # Step 5: Event-level fallback (H3.1 — always runs)
    event_results = faiss_search(q, st_vec_index, top_k=50)
    for event_id, event_score in event_results:
        episode_id = event_to_episode_map[event_id]
        # Boost episode score if any member event matched strongly
        scores[episode_id] = max(scores.get(episode_id, 0), event_score * 0.9)

    # Step 6: RRF fusion of episode-level and event-level rankings (H5.4)
    episode_rank = rank_by_score(scores)
    event_rank   = rank_episodes_by_best_event(event_results)
    final_scores = rrf_fuse([episode_rank, event_rank], k=60)

    # Step 7: Re-rank top-20 with UltraBERT NLI (R3.14 — if validated)
    # UltraBERT.analyze(premise=episode_text, hypothesis=query) → entailment score
    # This is UltraBERT-native, no external model

    return sorted(final_scores, reverse=True)[:top_k]
```

---

## What Gets Stored Per Episode (Final Schema)

| What | Where | Size | New? |
|------|-------|------|------|
| Episode embedding vector | st_vec (via embedding_id) | 768 x 4 = 3KB | No (existing) |
| Episode embedding_text | st_epi.episode_summary | up to 2000 chars | No (existing, just fix content) |
| Satellite references | st_epi.centroid_metadata_json | ~500 chars JSON | No (existing column, new content) |
| Entropy fingerprint | st_epi.centroid_metadata_json | ~100 chars JSON | No (existing column, new content) |
| Structural metadata | st_epi columns | Already stored | No |
| Mean valence | st_epi (new column) | 4 bytes REAL | **Yes — 1 new column** |
| Event vectors | st_vec (existing) | 768 x 4 x N per episode | No (already stored) |
| Event→episode mapping | st_hipp_events.consolidation_cycle_id + st_epi.source_events_json | Existing | No |

**Total new storage per episode:** ~600 chars in centroid_metadata_json + 4 bytes mean_valence.
**Total new schema changes:** 1 column (mean_valence REAL nullable on st_epi).

---

## Summary: What We Use

| Component | Model / Tool | Status |
|-----------|-------------|--------|
| Event embedding | UltraBERT `get_embedding()` | Existing, working |
| Episode embedding (small) | CentroidCalculator weighted mean | Existing, keep |
| Episode embedding (large) | MMR text → UltraBERT `get_embedding()` | **New code path** |
| Satellite selection | Statistical salience threshold | **New algorithm** |
| Satellite storage | centroid_metadata_json (event_id + embedding_id refs) | Existing column, **new content** |
| Structural matching | st_epi existing columns + axis_score() | **New scoring function** |
| Event-level search | FAISS over st_vec + episode grouping | **New retrieval path** |
| Fusion | RRF (10 lines of code) | **New** |
| Re-ranking | UltraBERT NLI head (if R3.14 validates) | **New, UltraBERT-native** |
| Query understanding | M08 NER + regex + UltraBERT affect on query | **New composition** |

**Models used: UltraBERT only. Zero external models.**

---

## Eliminated Approaches (UltraBERT-Only Constraint)

| Approach | Why Eliminated | Replacement |
|----------|---------------|-------------|
| H5.1 Cross-Encoder (ms-marco-MiniLM) | Not UltraBERT | R3.14: UltraBERT NLI re-ranking |
| H5.2 SPLADE (naver/splade-cocondenser) | Not UltraBERT | H3.3: Statistical BM25 keyphrase index (no model needed) |
| H5.3 Set Transformer | Needs 500+ episodes (have 88) | Deferred to Tier 4 |
| H5.5 Contrastive MLP | Needs 500+ episodes | Deferred to Tier 4 |
| H5.8 VAE | Needs 1000+ episodes | Deferred to Tier 4 |
| Any approach requiring a second embedding model | Violates constraint | Use UltraBERT get_embedding() for all embedding needs |

---

## Research Items Added by This Audit

| ID | Added To Tier | Description |
|----|-------------|-------------|
| R0.5 | Tier 0 | Centroid vs text-embed retrieval comparison |
| R0.6 | Tier 0 | UltraBERT normalization verification |
| R1.16 | Tier 1 | Centroid dilution quantification (death certificate) |
| R1.17 | Tier 1 | Episode size vs centroid quality correlation |
| R1.18 | Tier 1 | UltraBERT effective token capacity measurement |
| R3.12 | Tier 3 | UltraBERT cross-encoder capability test |
| R3.13 | Tier 3 | UltraBERT MLM head probe for SPLADE |
| R3.14 | Tier 3 | UltraBERT NLI-based re-ranking validation |

**Updated totals: 67 research items (was 59 + 8 new = 67)**

---
