"""
Mock Command Port - Receives writer agent commands and stores them

This is the backend storage layer that:
- Receives WriterCommands from writer agents
- Validates and deserializes them
- Stores them in backend (in-memory for PoC, can be switched to K0/DB)
- Makes them queryable via Query Port

Architecture:
- Writers → WriterCommandPort → (batched) → BatchClient → Mock Command Port
- Mock Command Port → BackendStorage
- Other agents → Query Port → Backend Storage
"""

import asyncio
import json
import time
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class StoredDelta:
    """A delta stored in backend."""

    delta_id: str
    delta_type: str  # "episodic", "prospective", "learning", "semantic"
    content: Dict[str, Any]
    timestamp: int
    trace_id: str
    writer_type: str  # "memory", "learning", "semantic"
    confidence: float
    created_at: Optional[int] = None  # When stored

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = int(time.time() * 1000)

    def to_dict(self) -> dict:
        """Convert to dict for JSON serialization."""
        return asdict(self)


class BackendStorage:
    """
    In-memory backend storage for deltas.

    Stores deltas by type for efficient querying.
    In production, this would be replaced with K0/database.

    Storage structure:
    {
        "episodic": [StoredDelta, ...],
        "prospective": [StoredDelta, ...],
        "learning": [StoredDelta, ...],
        "semantic": [StoredDelta, ...]
    }
    """

    def __init__(self):
        """Initialize backend storage."""
        self.deltas: Dict[str, List[StoredDelta]] = {
            "episodic": [],
            "prospective": [],
            "learning": [],
            "semantic": [],
        }
        self.lock = asyncio.Lock()
        self.delta_count = 0
        self.total_bytes = 0

    async def store_delta(self, delta: StoredDelta) -> bool:
        """
        Store a single delta.

        Args:
            delta: Delta to store

        Returns:
            True if stored successfully
        """
        try:
            async with self.lock:
                if delta.delta_type not in self.deltas:
                    self.deltas[delta.delta_type] = []

                self.deltas[delta.delta_type].append(delta)
                self.delta_count += 1

                # Track storage size
                delta_json = json.dumps(delta.to_dict())
                self.total_bytes += len(delta_json.encode())

                logger.debug(
                    "delta_stored",
                    delta_id=delta.delta_id,
                    delta_type=delta.delta_type,
                    writer_type=delta.writer_type,
                    confidence=delta.confidence,
                )
                return True

        except Exception as e:
            logger.error("delta_storage_error", delta_id=delta.delta_id, error=str(e))
            return False

    async def query_deltas(
        self,
        delta_type: Optional[str] = None,
        writer_type: Optional[str] = None,
        min_confidence: float = 0.0,
        limit: int = 100,
        offset: int = 0,
    ) -> List[StoredDelta]:
        """
        Query deltas from storage.

        Args:
            delta_type: Filter by delta type (episodic, prospective, learning, semantic)
            writer_type: Filter by writer type (memory, learning, semantic)
            min_confidence: Minimum confidence threshold
            limit: Max results to return
            offset: Offset for pagination

        Returns:
            List of matching StoredDeltas
        """
        try:
            async with self.lock:
                results = []

                # Get deltas to search
                if delta_type and delta_type in self.deltas:
                    search_types = [delta_type]
                else:
                    search_types = list(self.deltas.keys())

                # Filter and collect
                for dt in search_types:
                    for delta in self.deltas[dt]:
                        # Apply filters
                        if writer_type and delta.writer_type != writer_type:
                            continue
                        if delta.confidence < min_confidence:
                            continue

                        results.append(delta)

                # Sort by timestamp descending (newest first)
                results.sort(key=lambda d: d.timestamp, reverse=True)

                # Apply pagination
                return results[offset : offset + limit]

        except Exception as e:
            logger.error("delta_query_error", error=str(e))
            return []

    async def clear(self):
        """Clear all stored deltas (for testing)."""
        async with self.lock:
            self.deltas = {
                "episodic": [],
                "prospective": [],
                "learning": [],
                "semantic": [],
            }
            self.delta_count = 0
            self.total_bytes = 0

    def get_stats(self) -> Dict[str, Any]:
        """Get storage statistics."""
        return {
            "total_deltas": self.delta_count,
            "total_bytes": self.total_bytes,
            "by_type": {dt: len(deltas) for dt, deltas in self.deltas.items()},
        }


class MockCommandPort:
    """
    Mock Command Port - Receives writer commands and stores them.

    In real K0, this would be an HTTP endpoint receiving WriterCommands.
    For PoC, it's an in-memory service that writers call directly.

    Flow:
    1. Writer calls command_port.send_command(WriterCommand)
    2. BatchClient batches commands/deltas
    3. BatchClient.flush() → HTTP POST to MockCommandPort
    4. MockCommandPort receives batch → stores to BackendStorage
    5. Query Port reads from BackendStorage
    """

    def __init__(self, backend: BackendStorage):
        """Initialize mock command port."""
        self.backend = backend
        self.commands_received = 0
        self.commands_failed = 0
        self.lock = asyncio.Lock()

    async def receive_batch(
        self,
        batch_id: str,
        delta_type: str,
        deltas: List[Dict[str, Any]],
        trace_id: str,
    ) -> bool:
        """
        Receive and process a batch of deltas from BatchClient.

        Args:
            batch_id: Batch identifier
            delta_type: Type of deltas in batch
            deltas: List of delta dicts
            trace_id: Trace ID for correlation

        Returns:
            True if batch stored successfully
        """
        try:
            async with self.lock:
                stored_count = 0

                for delta_dict in deltas:
                    # Extract writer metadata from delta content
                    content = delta_dict.get("content", {})
                    writer_type = str(content.get("writer_type", "unknown"))
                    confidence = float(content.get("confidence", 0.8))
                    actual_data = content.get("data", {})

                    # Create StoredDelta with type conversions
                    stored_delta = StoredDelta(
                        delta_id=str(delta_dict.get("delta_id", "")),
                        delta_type=delta_type,
                        content=actual_data,
                        timestamp=int(delta_dict.get("timestamp", int(time.time() * 1000))),
                        trace_id=trace_id,
                        writer_type=writer_type,
                        confidence=confidence,  # Use content confidence, not wrapper confidence
                    )

                    # Store it
                    result = await self.backend.store_delta(stored_delta)
                    if result:
                        stored_count += 1
                    else:
                        self.commands_failed += 1

                self.commands_received += len(deltas)

                logger.info(
                    "batch_received",
                    batch_id=batch_id,
                    delta_type=delta_type,
                    count=len(deltas),
                    stored=stored_count,
                    trace_id=trace_id,
                )

                return stored_count == len(deltas)

        except Exception as e:
            logger.error("command_port_batch_error", batch_id=batch_id, error=str(e))
            self.commands_failed += len(deltas)
            return False

    async def receive_command(self, command_dict: Dict[str, Any]) -> bool:
        """
        Receive a single WriterCommand (for direct testing).

        Args:
            command_dict: WriterCommand as dict

        Returns:
            True if stored successfully
        """
        try:
            # Extract actual data and metadata from content wrapper
            content = command_dict.get("content", {})
            writer_type = str(content.get("writer_type", "unknown"))
            confidence = float(content.get("confidence", 0.8))
            actual_data = content.get("data", {})

            stored_delta = StoredDelta(
                delta_id=str(command_dict.get("command_id", "")),
                delta_type=str(command_dict.get("delta_type", "")),
                content=actual_data,  # Store only the data, not the wrapper
                timestamp=int(command_dict.get("timestamp", int(time.time() * 1000))),
                trace_id=str(command_dict.get("trace_id", "")),
                writer_type=writer_type,
                confidence=confidence,
            )

            result = await self.backend.store_delta(stored_delta)
            if result:
                self.commands_received += 1
            else:
                self.commands_failed += 1

            return result

        except Exception as e:
            logger.error(
                "command_port_error",
                command_id=command_dict.get("command_id"),
                error=str(e),
            )
            self.commands_failed += 1
            return False

    def get_stats(self) -> Dict[str, Any]:
        """Get command port statistics."""
        return {
            "commands_received": self.commands_received,
            "commands_failed": self.commands_failed,
            "backend_stats": self.backend.get_stats(),
        }
