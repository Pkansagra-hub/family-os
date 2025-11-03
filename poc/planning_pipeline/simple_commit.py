"""
Simple Commit Handler for POC (M8 Epic 8.2)

Lightweight commit mechanism for storing aggregated plans
without full K0 WAL integration. For production, this would
be replaced with proper FlatBuffers serialization and K0 WAL.

Part of M8 Epic 8.2: Commit to K0 WAL (POC Version)
"""

import json
import logging
import time
import uuid
from pathlib import Path
from typing import Dict, Optional

from plan_aggregator import AggregatedPlan

logger = logging.getLogger(__name__)


class SimpleCommitHandler:
    """
    Simple commit handler for POC testing.

    Stores aggregated plans as JSON files in a temp directory.
    In production, this would be replaced with:
    - FlatBuffers serialization
    - K0 WAL persistence
    - Proper durability guarantees

    For now, this is sufficient for testing the DAG orchestrator flow.
    """

    def __init__(self, storage_dir: str = "poc_commits"):
        """
        Initialize commit handler.

        Args:
            storage_dir: Directory for storing committed plans
        """
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"SimpleCommitHandler initialized: storage={storage_dir}")

    def commit(self, aggregated_plan: AggregatedPlan) -> str:
        """
        Commit aggregated plan to storage.

        Args:
            aggregated_plan: AggregatedPlan to commit

        Returns:
            flow_id: Unique identifier for committed plan
        """
        flow_id = aggregated_plan.flow_id

        # Convert to dictionary
        plan_dict = aggregated_plan.to_dict()

        # Add commit metadata
        plan_dict["committed_at"] = time.time()
        plan_dict["commit_version"] = "poc_v1"

        # Write to file
        filename = f"{flow_id}.json"
        filepath = self.storage_dir / filename

        try:
            with open(filepath, "w") as f:
                json.dump(plan_dict, f, indent=2, default=str)

            logger.info(f"Plan committed: {flow_id} → {filepath}")

            return flow_id

        except Exception as e:
            logger.error(f"Failed to commit plan {flow_id}: {e}")
            raise

    def retrieve(self, flow_id: str) -> Optional[Dict]:
        """
        Retrieve committed plan by flow_id.

        Args:
            flow_id: Flow identifier

        Returns:
            Plan dictionary or None if not found
        """
        filename = f"{flow_id}.json"
        filepath = self.storage_dir / filename

        if not filepath.exists():
            logger.warning(f"Plan not found: {flow_id}")
            return None

        try:
            with open(filepath, "r") as f:
                plan_dict = json.load(f)

            logger.info(f"Plan retrieved: {flow_id}")
            return plan_dict

        except Exception as e:
            logger.error(f"Failed to retrieve plan {flow_id}: {e}")
            return None

    def list_commits(self) -> list[str]:
        """
        List all committed flow IDs.

        Returns:
            List of flow_id strings
        """
        flow_ids = []

        for filepath in self.storage_dir.glob("*.json"):
            flow_id = filepath.stem
            flow_ids.append(flow_id)

        return sorted(flow_ids)

    def get_commit_summary(self, flow_id: str) -> Optional[str]:
        """
        Get human-readable summary of committed plan.

        Args:
            flow_id: Flow identifier

        Returns:
            Summary string or None if not found
        """
        plan_dict = self.retrieve(flow_id)

        if not plan_dict:
            return None

        lines = []
        lines.append("=" * 60)
        lines.append(f"COMMITTED PLAN: {flow_id}")
        lines.append("=" * 60)
        lines.append(f"Intent: {plan_dict.get('intent', 'unknown')}")
        lines.append(f"Status: {plan_dict.get('status', 'unknown')}")
        lines.append(f"Total Latency: {plan_dict.get('total_latency_ms', 0):.0f}ms")
        lines.append("")

        successful = plan_dict.get("successful_steps", [])
        failed = plan_dict.get("failed_steps", [])
        blocked = plan_dict.get("blocked_steps", [])

        lines.append(f"Successful Steps: {len(successful)}")
        lines.append(f"Failed Steps: {len(failed)}")
        lines.append(f"Blocked Steps: {len(blocked)}")
        lines.append("")

        agents = plan_dict.get("agents_used", [])
        lines.append(f"Agents Used: {', '.join(agents)}")
        lines.append("=" * 60)

        return "\n".join(lines)

    def clear_all(self):
        """Clear all committed plans (useful for testing)"""
        for filepath in self.storage_dir.glob("*.json"):
            filepath.unlink()

        logger.info("All commits cleared")


def generate_flow_id(intent: str = "flow") -> str:
    """
    Generate unique flow ID.

    Args:
        intent: Intent description for readability

    Returns:
        Unique flow_id string
    """
    # Create readable flow ID: intent_timestamp_uuid
    timestamp = int(time.time())
    short_uuid = str(uuid.uuid4())[:8]

    # Clean intent for filename
    clean_intent = intent.lower().replace(" ", "_")[:20]

    return f"{clean_intent}_{timestamp}_{short_uuid}"


# Example usage
if __name__ == "__main__":
    from plan_aggregator import AggregatedPlan

    print("\n" + "=" * 60)
    print("SIMPLE COMMIT HANDLER TEST")
    print("=" * 60)

    # Create commit handler
    handler = SimpleCommitHandler(storage_dir="poc_commits_test")

    # Create sample aggregated plan
    flow_id = generate_flow_id("test_booking")

    sample_plan = AggregatedPlan(
        flow_id=flow_id,
        intent="Book dinner and notify family",
        status="completed",
        total_latency_ms=1250.0,
        agents_used=["booking_agent", "messenger_agent"],
    )

    # Commit plan
    print(f"\nCommitting plan: {flow_id}")
    committed_id = handler.commit(sample_plan)
    print(f"✅ Plan committed: {committed_id}")

    # Retrieve plan
    print(f"\nRetrieving plan: {flow_id}")
    retrieved = handler.retrieve(flow_id)
    if retrieved:
        print("✅ Plan retrieved")
        print(f"   Status: {retrieved['status']}")
        print(f"   Intent: {retrieved['intent']}")
        print(f"   Latency: {retrieved['total_latency_ms']}ms")

    # Get summary
    print("\nCommit Summary:")
    summary = handler.get_commit_summary(flow_id)
    print(summary)

    # List all commits
    print("\nAll Commits:")
    commits = handler.list_commits()
    for commit_id in commits:
        print(f"  - {commit_id}")

    # Clean up test
    handler.clear_all()
    print("\n✅ Test complete (cleaned up)")
