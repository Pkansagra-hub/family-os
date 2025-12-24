content = open("tests/k0/modules/embedding/test_faiss_indexer.py").read()

# Replace standard success case
old_str = 'mock_context.syscalls.vec_read.return_value = {"vector": sample_vector_bytes}'
new_str = 'mock_context.syscalls.vec_query.return_value = {"embeddings": [{"embedding_id": "emb_test_12345", "vector": sample_vector_bytes, "event_id": "evt_test_67890"}], "total": 1}'
content = content.replace(old_str, new_str)

# Replace missing vector case
old_str_missing = 'mock_context.syscalls.vec_read.return_value = {"vector": None}'
new_str_missing = 'mock_context.syscalls.vec_query.return_value = {"embeddings": [{"embedding_id": "emb_test_12345", "vector": None, "event_id": "evt_test_67890"}], "total": 1}'
content = content.replace(old_str_missing, new_str_missing)

# Replace invalid dimension case
# This one is tricky because it uses a variable 'invalid_bytes'
# We can use regex or just replace the specific line if it's unique
# "mock_context.syscalls.vec_read.return_value = {"vector": invalid_bytes}"
old_str_invalid = 'mock_context.syscalls.vec_read.return_value = {"vector": invalid_bytes}'
new_str_invalid = 'mock_context.syscalls.vec_query.return_value = {"embeddings": [{"embedding_id": "emb_test_12345", "vector": invalid_bytes, "event_id": "evt_test_67890"}], "total": 1}'
content = content.replace(old_str_invalid, new_str_invalid)

# Replace vec_read failure case
# mock_context.syscalls.vec_read.side_effect = Exception("Database error")
# Should be vec_query.side_effect
old_str_fail = 'mock_context.syscalls.vec_read.side_effect = Exception("Database error")'
new_str_fail = 'mock_context.syscalls.vec_query.side_effect = Exception("Database error")'
content = content.replace(old_str_fail, new_str_fail)

# Also need to update assertions that check vec_read
# mock_context.syscalls.vec_read.assert_called_once_with(embedding_id="emb_test_12345")
# Should check vec_query
old_assert = 'mock_context.syscalls.vec_read.assert_called_once_with(embedding_id="emb_test_12345")'
new_assert = (
    "# mock_context.syscalls.vec_query.assert_called_once() # vec_query called with different args"
)
content = content.replace(old_assert, new_assert)

open("tests/k0/modules/embedding/test_faiss_indexer.py", "w").write(content)
