"""
FlatBuffers-generated code for Proposal (auto-generated from proposal.fbs)

This is a simplified Python implementation of the FlatBuffers schema.
In production, use: flatc --python -o . proposal.fbs
"""

import struct
from typing import List


class ProposalBuilder:
    """Builder for creating Proposal FlatBuffers"""

    def __init__(self):
        self.bytes_array = bytearray()
        self.finished = False

    def add_agent_id(self, agent_id: str) -> int:
        """Add agent_id string and return offset"""
        if isinstance(agent_id, str):
            agent_id = agent_id.encode("utf-8")
        return self._add_string(agent_id)

    def add_task_id(self, task_id: str) -> int:
        """Add task_id string and return offset"""
        if isinstance(task_id, str):
            task_id = task_id.encode("utf-8")
        return self._add_string(task_id)

    def add_strategy(self, strategy: str) -> int:
        """Add strategy string and return offset"""
        if isinstance(strategy, str):
            strategy = strategy.encode("utf-8")
        return self._add_string(strategy)

    def add_reasoning(self, reasoning: str) -> int:
        """Add reasoning string and return offset"""
        if isinstance(reasoning, str):
            reasoning = reasoning.encode("utf-8")
        return self._add_string(reasoning)

    def _add_string(self, data: bytes) -> int:
        """Add byte string and return offset"""
        offset = len(self.bytes_array)
        length = len(data)
        # Store length + data
        self.bytes_array.extend(struct.pack("<I", length))
        self.bytes_array.extend(data)
        return offset

    def build(
        self,
        agent_id: str,
        task_id: str,
        estimated_latency_ms: int,
        estimated_cost: float,
        confidence: float,
        strategy: str,
        tools_required: List[str],
        reasoning: str,
        submission_time_ms: float,
    ) -> bytes:
        """Build proposal into bytes"""
        # Create a simple binary format (not full FlatBuffers but similar efficiency)
        buffer = bytearray()

        # Header: magic + version
        buffer.extend(b"PROP")  # Magic number
        buffer.extend(struct.pack("<B", 1))  # Version

        # Strings (with length prefix for variable-length data)
        for s in [agent_id, task_id, strategy, reasoning]:
            s_bytes = s.encode("utf-8") if isinstance(s, str) else s
            buffer.extend(struct.pack("<H", len(s_bytes)))
            buffer.extend(s_bytes)

        # Numbers (fixed-size, fast access)
        buffer.extend(struct.pack("<I", estimated_latency_ms))  # uint32
        buffer.extend(struct.pack("<f", estimated_cost))  # float
        buffer.extend(struct.pack("<f", confidence))  # float
        buffer.extend(struct.pack("<d", submission_time_ms))  # double

        # Tools array
        buffer.extend(struct.pack("<H", len(tools_required)))
        for tool in tools_required:
            tool_bytes = tool.encode("utf-8") if isinstance(tool, str) else tool
            buffer.extend(struct.pack("<H", len(tool_bytes)))
            buffer.extend(tool_bytes)

        return bytes(buffer)


class ProposalReader:
    """Reader for deserializing Proposal FlatBuffers"""

    def __init__(self, data: bytes):
        self.data = data
        self.pos = 0

    def read_proposal(self) -> dict:
        """Deserialize proposal from bytes"""
        # Check magic and version
        magic = self.data[self.pos : self.pos + 4]
        if magic != b"PROP":
            raise ValueError("Invalid proposal format")
        self.pos += 4

        version = struct.unpack("<B", self.data[self.pos : self.pos + 1])[0]
        self.pos += 1

        if version != 1:
            raise ValueError(f"Unsupported version: {version}")

        # Read strings
        agent_id = self._read_string()
        task_id = self._read_string()
        strategy = self._read_string()
        reasoning = self._read_string()

        # Read numbers
        estimated_latency_ms = struct.unpack("<I", self.data[self.pos : self.pos + 4])[0]
        self.pos += 4

        estimated_cost = struct.unpack("<f", self.data[self.pos : self.pos + 4])[0]
        self.pos += 4

        confidence = struct.unpack("<f", self.data[self.pos : self.pos + 4])[0]
        self.pos += 4

        submission_time_ms = struct.unpack("<d", self.data[self.pos : self.pos + 8])[0]
        self.pos += 8

        # Read tools array
        tools_count = struct.unpack("<H", self.data[self.pos : self.pos + 2])[0]
        self.pos += 2

        tools_required = []
        for _ in range(tools_count):
            tools_required.append(self._read_string())

        return {
            "agent_id": agent_id,
            "task_id": task_id,
            "estimated_latency_ms": estimated_latency_ms,
            "estimated_cost": estimated_cost,
            "confidence": confidence,
            "strategy": strategy,
            "tools_required": tools_required,
            "reasoning": reasoning,
            "submission_time_ms": submission_time_ms,
        }

    def _read_string(self) -> str:
        """Read variable-length string"""
        length = struct.unpack("<H", self.data[self.pos : self.pos + 2])[0]
        self.pos += 2

        s_bytes = self.data[self.pos : self.pos + length]
        self.pos += length

        return s_bytes.decode("utf-8")
