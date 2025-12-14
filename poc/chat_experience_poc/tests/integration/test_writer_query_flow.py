"""
Integration test: Writer → MockCommandPort → BackendStorage → QueryPort

Shows complete flow:
1. Writers send WriterCommands
2. MockCommandPort receives and stores
3. QueryPort queries what was stored
4. Other agents can access the data
"""

import pytest
from l5_infrastructure.k0_bridge import BackendStorage, MockCommandPort, QueryPort


class TestWriterToQueryFlow:
    """Test complete writer→storage→query flow."""

    @pytest.fixture
    def setup(self):
        """Setup backend, command port, and query port."""
        backend = BackendStorage()
        command_port = MockCommandPort(backend)
        query_port = QueryPort(backend)
        return backend, command_port, query_port

    @pytest.mark.asyncio
    async def test_episodic_memory_write_and_read(self, setup):
        """Test writing episodic memory and querying it."""
        backend, command_port, query_port = setup

        # Simulate writer sending episodic memory command
        command = {
            "command_id": "cmd_001",
            "writer_type": "memory",
            "delta_type": "episodic",
            "content": {
                "writer_type": "memory",
                "data": {
                    "what": "User asked about weather",
                    "who": ["user", "agent"],
                    "when": "2024-11-05T10:30:00Z",
                    "where": "chat session",
                    "emotion": "neutral",
                    "importance": 5,
                },
                "confidence": 0.95,
            },
            "timestamp": 1730800200000,
            "trace_id": "trace_001",
        }

        # Send command to mock port
        result = await command_port.receive_command(command)
        assert result is True

        # Query episodic memories
        memories = await query_port.query_episodic_memories(min_confidence=0.9)
        assert len(memories) == 1
        assert memories[0]["memory"]["what"] == "User asked about weather"
        assert memories[0]["memory"]["emotion"] == "neutral"

    @pytest.mark.asyncio
    async def test_prospective_memory_write_and_read(self, setup):
        """Test writing prospective memory and querying it."""
        backend, command_port, query_port = setup

        # Writer sends prospective memory
        command = {
            "command_id": "cmd_002",
            "writer_type": "memory",
            "delta_type": "prospective",
            "content": {
                "writer_type": "memory",
                "data": {
                    "trigger": "Tomorrow 9 AM",
                    "goal": "Remind user about team meeting",
                    "deadline": "2024-11-06T09:00:00Z",
                    "context": "Weekly sync with product team",
                    "agent_notes": "Send reminder 10 mins before",
                },
                "confidence": 0.88,
            },
            "timestamp": 1730800300000,
            "trace_id": "trace_002",
        }

        result = await command_port.receive_command(command)
        assert result is True

        # Query prospective memories
        memories = await query_port.query_prospective_memories(min_confidence=0.8)
        assert len(memories) == 1
        assert memories[0]["memory"]["trigger"] == "Tomorrow 9 AM"
        assert memories[0]["memory"]["deadline"] == "2024-11-06T09:00:00Z"

    @pytest.mark.asyncio
    async def test_learning_signal_write_and_read(self, setup):
        """Test writing learning signal and querying it."""
        backend, command_port, query_port = setup

        # Learning extractor sends signal
        command = {
            "command_id": "cmd_003",
            "writer_type": "learning",
            "delta_type": "learning",
            "content": {
                "writer_type": "learning",
                "data": {
                    "signal_type": "feedback",
                    "signal_data": {
                        "feedback_text": "That recommendation was perfect",
                        "feedback_sentiment": "positive",
                        "agent_action": "Recommended book",
                        "metric": "user_satisfaction",
                        "metric_value": 0.95,
                    },
                    "valence": "positive",
                    "context": "User appreciated book recommendation",
                },
                "confidence": 0.92,
            },
            "timestamp": 1730800400000,
            "trace_id": "trace_003",
        }

        result = await command_port.receive_command(command)
        assert result is True

        # Query learning signals
        signals = await query_port.query_learning_signals(min_confidence=0.9)
        assert len(signals) == 1
        assert signals[0]["signal"]["signal_type"] == "feedback"
        assert signals[0]["signal"]["valence"] == "positive"

    @pytest.mark.asyncio
    async def test_semantic_extraction_write_and_read(self, setup):
        """Test writing semantic extraction and querying it."""
        backend, command_port, query_port = setup

        # Semantic enricher sends extraction
        command = {
            "command_id": "cmd_004",
            "writer_type": "semantic",
            "delta_type": "semantic",
            "content": {
                "writer_type": "semantic",
                "data": {
                    "entities": [
                        {
                            "name": "Alice",
                            "type": "person",
                            "description": "Best friend from college",
                            "importance": 9,
                        }
                    ],
                    "relationships": [
                        {
                            "from_entity": "User",
                            "relationship_type": "knows",
                            "to_entity": "Alice",
                            "strength": 9,
                        }
                    ],
                    "topics": ["friendship", "college", "life"],
                    "emotional_valence": "positive",
                    "semantic_tags": ["important_person", "personal"],
                },
                "confidence": 0.90,
            },
            "timestamp": 1730800500000,
            "trace_id": "trace_004",
        }

        result = await command_port.receive_command(command)
        assert result is True

        # Query semantic extractions
        extractions = await query_port.query_semantic_extractions(min_confidence=0.85)
        assert len(extractions) == 1
        assert len(extractions[0]["entities"]) == 1
        assert extractions[0]["entities"][0]["name"] == "Alice"

    @pytest.mark.asyncio
    async def test_batch_write_from_mock_port(self, setup):
        """Test batch write through mock command port."""
        backend, command_port, query_port = setup

        # Simulate BatchClient sending batch
        batch_deltas = [
            {
                "delta_id": "d1",
                "delta_type": "episodic",
                "content": {
                    "writer_type": "memory",
                    "data": {"what": "Event 1"},
                    "confidence": 0.85,
                },
                "timestamp": 1730800600000,
            },
            {
                "delta_id": "d2",
                "delta_type": "episodic",
                "content": {
                    "writer_type": "memory",
                    "data": {"what": "Event 2"},
                    "confidence": 0.90,
                },
                "timestamp": 1730800700000,
            },
        ]

        # Receive batch
        result = await command_port.receive_batch(
            batch_id="batch_001",
            delta_type="episodic",
            deltas=batch_deltas,
            trace_id="trace_batch",
        )
        assert result is True

        # Query all episodic memories
        memories = await query_port.query_episodic_memories(limit=100)
        assert len(memories) == 2

    @pytest.mark.asyncio
    async def test_query_by_trace_id(self, setup):
        """Test querying deltas by trace_id."""
        backend, command_port, query_port = setup

        # Send commands with specific trace_id
        trace_id = "trace_correlation_123"

        for i in range(3):
            command = {
                "command_id": f"cmd_{i}",
                "writer_type": "memory",
                "delta_type": "episodic",
                "content": {
                    "writer_type": "memory",
                    "data": {"what": f"Event {i}"},
                    "confidence": 0.80 + (i * 0.05),
                },
                "timestamp": 1730800600000 + (i * 100000),
                "trace_id": trace_id,
            }
            await command_port.receive_command(command)

        # Query by trace_id
        deltas = await query_port.query_by_trace_id(trace_id)
        assert len(deltas) == 3

    @pytest.mark.asyncio
    async def test_confidence_filtering(self, setup):
        """Test querying with confidence threshold."""
        backend, command_port, query_port = setup

        # Send commands with varying confidence
        commands = [
            {
                "command_id": "c1",
                "writer_type": "memory",
                "delta_type": "episodic",
                "content": {"writer_type": "memory", "data": {}, "confidence": 0.5},
                "timestamp": 1730800600000,
                "trace_id": "t1",
            },
            {
                "command_id": "c2",
                "writer_type": "memory",
                "delta_type": "episodic",
                "content": {"writer_type": "memory", "data": {}, "confidence": 0.75},
                "timestamp": 1730800700000,
                "trace_id": "t2",
            },
            {
                "command_id": "c3",
                "writer_type": "memory",
                "delta_type": "episodic",
                "content": {"writer_type": "memory", "data": {}, "confidence": 0.95},
                "timestamp": 1730800800000,
                "trace_id": "t3",
            },
        ]

        for cmd in commands:
            await command_port.receive_command(cmd)

        # Query with high confidence threshold
        results = await query_port.query_episodic_memories(min_confidence=0.8)
        assert len(results) == 1  # Only 0.95 confidence

        # Query with lower threshold
        results = await query_port.query_episodic_memories(min_confidence=0.7)
        assert len(results) == 2  # 0.75 and 0.95

    @pytest.mark.asyncio
    async def test_stats_tracking(self, setup):
        """Test stats are properly tracked."""
        backend, command_port, query_port = setup

        # Send some commands
        for i in range(5):
            command = {
                "command_id": f"cmd_{i}",
                "writer_type": "memory",
                "delta_type": "episodic",
                "content": {"writer_type": "memory", "data": {}, "confidence": 0.85},
                "timestamp": 1730800600000 + (i * 1000),
                "trace_id": f"t_{i}",
            }
            await command_port.receive_command(command)

        # Execute some queries
        await query_port.query_episodic_memories(limit=100)
        await query_port.query_episodic_memories(limit=100)

        # Check command port stats
        cmd_stats = command_port.get_stats()
        assert cmd_stats["commands_received"] == 5
        assert cmd_stats["commands_failed"] == 0

        # Check query port stats
        query_stats = query_port.get_stats()
        assert query_stats["queries_executed"] == 2
        assert query_stats["total_results_returned"] == 10  # 5 results * 2 queries


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
