Read [](file:///d%3A/familyos/docs/plans/GAP_001_MILESTONE_4_FAISS_UNION_INDEX.md#1-1), lines 1 to 200

Read [](file:///d%3A/familyos/docs/architecture/gaps/GAP_001_CROSS_LAYER_VECTOR_LINKING.md#1-1), lines 1 to 200

Summarized conversation historyLet me continue reading both files to get the complete picture:

Read [](file:///d%3A/familyos/docs/plans/GAP_001_MILESTONE_4_FAISS_UNION_INDEX.md#201-201), lines 201 to 500

Read [](file:///d%3A/familyos/docs/plans/GAP_001_MILESTONE_4_FAISS_UNION_INDEX.md#501-501), lines 501 to 885

Now let me read the M3 code files we created to understand the existing patterns:

Read [](file:///d%3A/familyos/k0/modules/consolidation/truth_writer/text_vector_coordinator.py#1-1), lines 1 to 100

Read [](file:///d%3A/familyos/k0/modules/consolidation/truth_writer/embedding_generator.py#1-1), lines 1 to 100

Read [](file:///d%3A/familyos/k0/modules/embedding)

Let me check the existing faiss_indexer.py for patterns and also look at the p08 pipeline structure:

Read [](file:///d%3A/familyos/k0/modules/embedding/faiss_indexer.py#1-1), lines 1 to 150

Read [](file:///d%3A/familyos/k0/pipelines/p08)

Let me check what pipelines exist and see if p08 directory needs to be created:

Read [](file:///d%3A/familyos/k0/pipelines)

Read [](file:///d%3A/familyos/k0/modules/embedding/faiss_indexer.py#151-151), lines 151 to 291

Now I understand the structure. The p08 pipeline doesn't have its own folder - the modules are in embedding. Now let me set up the todo list and start implementing Milestone 4:

Created 7 todos

Let me start implementing Issue 4.1 - the UnionIndexMetadata data model:

Created [](file:///d%3A/familyos/k0/modules/embedding/union_index_metadata.py)

Starting: *Create UnionIndexBuilder service (4.2)* (2/7)

Now let me create Issue 4.2 - UnionIndexBuilder service:

Created [](file:///d%3A/familyos/k0/modules/embedding/union_index_builder.py)

The linter errors are false positives - the imports are used inside functions (like `time.time()`) and in type hints. Let me update the todo and continue with the UnionIndexSearcher (Issue 4.3):

Starting: *Create UnionIndexSearcher service (4.3)* (3/7)

Created [](file:///d%3A/familyos/k0/modules/embedding/union_index_searcher.py)

The file was created correctly - that lint error is a false positive related to docstring parsing. Now let me create Issue 4.4 - UnionIndexManager:

Starting: *Create UnionIndexManager lifecycle (4.4)* (4/7)

Created [](file:///d%3A/familyos/k0/modules/embedding/union_index_manager.py)

The linter is being overly strict - the imports are local to functions and are used by faiss calls like `faiss.write_index()`. Now let me create Issue 4.5 - the P08 rebuild job:

Starting: *Create P08 union_index_rebuild_job (4.5)* (5/7)

Created [](file:///d%3A/familyos/k0/modules/embedding/union_index_rebuild_job.py)

The file was created successfully. Now let me check the syscalls.py file to see how to register the new syscalls for Issue 4.6:

Searched for text `async def faiss_` (`**/k0/kernel/syscalls.py`), 4 results

Read [](file:///d%3A/familyos/k0/kernel/syscalls.py#1-1), lines 1 to 100

Let me read the existing faiss_search syscall to understand the pattern, and then find where to add the new syscalls:

Read [](file:///d%3A/familyos/k0/kernel/syscalls.py#1995-1995), lines 1995 to 2160

Now let me find the end of the syscalls class to add the new union_index syscalls:

Read [](file:///d%3A/familyos/k0/kernel/syscalls.py#3400-3400), lines 3400 to 3498

Now I'll add the new union_index syscalls. Let me add them after the faiss_remove_batch function:

Read [](file:///d%3A/familyos/k0/kernel/syscalls.py#2150-2150), lines 2150 to 2250

Good - I can see the pattern. I'll add the new syscalls after the faiss_remove_batch function (around line 2196) and before the Phase 3 Backfill Syscalls section. Let me add the union_index syscalls:

Using "Replace String in File"


```

```


Starting: *Create unit tests for UnionIndex (4.7)* (7/7)

Now let me create the unit tests for Issue 4.7. First let me check what test directory structure exists:

Read [](file:///d%3A/familyos/tests/k0/modules)

Read [](file:///d%3A/familyos/tests/k0/modules/embedding)

Let me check the existing test pattern for the embedding module:

Read [](file:///d%3A/familyos/tests/k0/modules/embedding/test_faiss_indexer.py#1-1), lines 1 to 80

Now I'll create comprehensive unit tests for all the union index components:

Created [](file:///d%3A/familyos/tests/k0/modules/embedding/test_union_index.py)

The file was created successfully. Now let me run the tests to verify everything works:

Discovering tests...

Let me try running pytest directly to see if there are any import errors:

Ran terminal command: python -m pytest tests/k0/modules/embedding/test_union_index.py -v --tb=short 2>&1 | Select-Object -First 100

35 of 37 tests pass. Let me fix the 2 failing tests - one is a mock issue and one is a Windows path separator issue:

Using "Replace String in File"


```

```
Now let me fix the Windows path separator issue in the singleton test:

Using "Replace String in File"


```

```
Now let me run the tests again to verify all pass:

Ran terminal command: python -m pytest tests/k0/modules/embedding/test_union_index.py -v --tb=short 2>&1 | Select-Object -First 60

All 37 tests pass. Let me also run the full embedding module tests to make sure nothing is broken:

Ran terminal command: python -m pytest tests/k0/modules/embedding/ -v --tb=short 2>&1 | Select-Object -Last 30

Completed: *Create unit tests for UnionIndex (4.7)* (7/7)

Now let me verify there are no errors with our new files by checking for lint/compile errors:

Checked [](file:///d%3A/familyos/k0/modules/embedding), 10 problems found

These are mostly type annotation warnings from the linter, not actual compile errors. The tests pass which is the important part. Let me fix the type hints to be more correct:

Read [](file:///d%3A/familyos/k0/modules/embedding/union_index_rebuild_job.py#1-1), lines 1 to 30

Using "Replace String in File"


```

```


Read [](file:///d%3A/familyos/k0/modules/embedding/union_index_rebuild_job.py#170-170), lines 170 to 200

Using "Replace String in File"


```

```


Read [](file:///d%3A/familyos/k0/modules/embedding/union_index_rebuild_job.py#240-240), lines 240 to 267

Using "Replace String in File"


```

```
Now let me run a quick verification to confirm all tests still pass:

Ran terminal command: python -m pytest tests/k0/modules/embedding/test_union_index.py -v --tb=short 2>&1 | Select-Object -Last 10

All 37 tests pass. Let me also run the syscalls tests to verify our new union_index syscalls don't break anything:

Ran terminal command: python -m pytest tests/k0/kernel/test_syscalls.py -v --tb=short -k "faiss or union" 2>&1 | Select-Object -Last 30

The test file doesn't have specific tests for the new syscalls yet. Let me run all syscalls tests to ensure we haven't broken anything:

Ran terminal command: python -m pytest tests/k0/kernel/test_syscalls.py -v --tb=short 2>&1 | Select-Object -Last 20

All syscalls tests pass. Now let me provide a summary of what was completed for Milestone 4:

**Milestone 4: P08 FAISS Union Index — COMPLETE**

## Summary

I've successfully implemented all 7 issues for GAP-001 Milestone 4:

### Files Created

| File | Issue | Description |
|------|-------|-------------|
| union_index_metadata.py | 4.1 | Data model for tracking layer + record_id per vector |
| union_index_builder.py | 4.2 | Queries all 6 truth layers, builds FAISS IndexFlatIP |
| union_index_searcher.py | 4.3 | Cross-layer search with layer/tenant/space filtering |
| union_index_manager.py | 4.4 | Lifecycle: build, persist, load, scheduled rebuild |
| union_index_rebuild_job.py | 4.5 | P08 job that rebuilds index every 6 hours |
| test_union_index.py | 4.7 | 37 unit tests for all components |

### Files Modified

| File | Issue | Changes |
|------|-------|---------|
| syscalls.py | 4.6 | Added `union_index_search`, `union_index_rebuild`, `union_index_stats` syscalls |

### Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    FAISS UNION INDEX                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   st_epi ──────┐                                                 │
│   st_sem ──────┤                                                 │
│   st_procedural┼──▶ UnionIndexBuilder ──▶ FAISS IndexFlatIP(768) │
│   st_social ───┤                               │                 │
│   st_prospective                               ▼                 │
│   st_kg_dom ───┘                      ┌─────────────────┐        │
│                                       │ UnionIndexMetadata│      │
│                                       │ (layer, id, etc) │        │
│                                       └─────────────────┘        │
│                                                                  │
│   Query: UnionIndexSearcher.search(query_vec, k=20)              │
│   → Returns: [(layer, record_id, score), ...]                    │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Key Features

1. **UnionIndexMetadata**: Tracks source layer + record_id for each vector, supports JSON serialization for persistence
2. **UnionIndexBuilder**: Queries all 6 truth layers for `embedding_vector IS NOT NULL`, handles BYTEA→numpy conversion
3. **UnionIndexSearcher**: Cosine similarity via normalized inner product, supports layer/tenant/space filtering
4. **UnionIndexManager**: Singleton pattern, 6-hour rebuild interval, disk persistence
5. **Syscalls**: `union_index_search`, `union_index_rebuild`, `union_index_stats` (all require `faiss.read` or `faiss.write`)

### Test Results

- **37 tests pass** in test_union_index.py
- **32 syscalls tests pass** (no regressions)

### Next Milestone

Per GAP-001, proceed to:
- **Milestone 5: P01 Context Expander** — Entity graph traversal for rich LLM context

Made changes.
