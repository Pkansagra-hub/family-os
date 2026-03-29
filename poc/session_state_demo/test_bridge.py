"""Quick test of SessionLLMBridge without LLM."""

import os
import tempfile

from poc.session_state_demo.bridge import SessionLLMBridge

# Use temp directory
db_path = os.path.join(tempfile.gettempdir(), "demo_test.db")

# Create bridge
bridge = SessionLLMBridge(session_id="test-001", db_path=db_path)

# Start session
success, msg = bridge.start()
print(f"Start: {success} - {msg}")

# Record user turn (buffers)
changes = bridge.record_user_turn("Hello, I am planning a trip to Japan")
print(f"User turn recorded: {len(changes)} changes")
for c in changes:
    print(f"  {c.section}.{c.operation}: {c.description}")

# Build context (before assistant response)
ctx = bridge.build_llm_context()
print(f"Context built: {len(ctx['messages'])} messages in history")
print(f"System prompt length: {len(ctx['system_prompt'])} chars")

# Record assistant turn (writes complete turn to history)
changes = bridge.record_assistant_turn(
    "That sounds exciting! Japan is beautiful.", duration_ms=150, token_count=50
)
print(f"Assistant turn recorded: {len(changes)} changes")
for c in changes:
    print(f"  {c.section}.{c.operation}: {c.description}")

# Get snapshot
snap = bridge.get_snapshot()
print(f"Snapshot: {snap['total_size_bytes']} bytes, turn #{snap['turn_number']}")

# Checkpoint
success, msg, bytes_saved = bridge.checkpoint()
print(f"Checkpoint: {success} - {msg} ({bytes_saved} bytes)")

# Stop
success, msg = bridge.stop()
print(f"Stop: {success} - {msg}")

print("\nTest passed!")
