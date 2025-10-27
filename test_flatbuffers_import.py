import os
import sys

# Add contracts path
contracts_path = os.path.abspath("k1/contracts/flatbuffers/layer5_infrastructure")
print(f"Adding to sys.path: {contracts_path}")
print(f"Path exists: {os.path.exists(contracts_path)}")

sys.path.insert(0, contracts_path)

# Try import
try:
    from k1.actor_fabric import MessageEnvelope, MessagePriority

    print("✅ SUCCESS: FlatBuffers types imported!")
    print(f"MessageEnvelope: {MessageEnvelope.MessageEnvelope}")
    print(f"MessagePriority: {MessagePriority.MessagePriority}")
except ImportError as e:
    print(f"❌ FAILED: {e}")
    print("\nChecking directory structure:")
    import os

    for root, dirs, files in os.walk(contracts_path):
        level = root.replace(contracts_path, "").count(os.sep)
        indent = " " * 2 * level
        print(f"{indent}{os.path.basename(root)}/")
        subindent = " " * 2 * (level + 1)
        for file in files:
            print(f"{subindent}{file}")
