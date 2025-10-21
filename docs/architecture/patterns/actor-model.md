# Actor Model - K1 Implementation Guide

## Overview

The Actor Model (Hewitt 1973) is the foundation for K1's agent isolation and communication patterns. Every agent is an isolated actor with private state and message-passing communication.

## Core Principles

1. **Isolation**: Each agent has private state, no shared memory
2. **Message-passing**: Communication only through mailboxes (asyncio.Queue)
3. **Concurrency**: Agents process messages asynchronously
4. **Supervision**: Supervisor monitors agent health at 1Hz

## K1 Implementation

### Agent Structure

```python
from asyncio import Queue
from dataclasses import dataclass
from enum import Enum

class AgentState(Enum):
    PENDING = "PENDING"
    WARMING = "WARMING"
    ACTIVE = "ACTIVE"
    IDLE = "IDLE"
    DRAINING = "DRAINING"
    TERMINATED = "TERMINATED"

@dataclass
class Agent:
    """Actor Model implementation for K1 agents"""
    agent_id: str
    state: AgentState
    mailbox: Queue  # Private message queue
    capabilities: list[str]
    memory_mb: int
    _private_state: dict  # No external access

    async def receive_message(self, msg: Message):
        """Process messages from mailbox"""
        await self.mailbox.put(msg)

    async def process_messages(self):
        """Main actor loop"""
        while self.state != AgentState.TERMINATED:
            msg = await self.mailbox.get()
            await self._handle_message(msg)
```

### Message Structure

```python
@dataclass
class Message:
    """Actor Model message"""
    msg_id: str
    sender: str
    receiver: str
    payload: Any
    trace_id: str  # cognitive_trace_id for observability
    timestamp_ms: int
```

### Supervisor Pattern

```python
class Supervisor:
    """Supervisor monitors agent health"""
    def __init__(self):
        self.agents: dict[str, Agent] = {}
        self.check_interval_ms = 1000  # 1Hz
        self.blacklist: dict[str, int] = {}  # agent_id → crash_count

    async def monitor(self):
        """Monitor agents every 1Hz"""
        while True:
            for agent_id, agent in self.agents.items():
                if not await self._health_check(agent):
                    await self._handle_crash(agent_id)

            await asyncio.sleep(self.check_interval_ms / 1000)

    async def _handle_crash(self, agent_id: str):
        """Handle agent crash with blacklist enforcement"""
        self.blacklist[agent_id] = self.blacklist.get(agent_id, 0) + 1

        if self.blacklist[agent_id] >= 3:
            logger.warning(f"Agent {agent_id} blacklisted after 3 crashes")
            # Don't rehire this agent for 3600s
```

## Message-Passing Patterns

### 1. Point-to-Point

```python
async def send_message(sender: Agent, receiver: Agent, payload: dict):
    """Direct message from sender to receiver"""
    msg = Message(
        msg_id=generate_id(),
        sender=sender.agent_id,
        receiver=receiver.agent_id,
        payload=payload,
        trace_id=current_trace_id(),
        timestamp_ms=current_time_ms()
    )
    await receiver.mailbox.put(msg)
```

### 2. Broadcast

```python
async def broadcast(sender: Agent, receivers: list[Agent], payload: dict):
    """Broadcast message to multiple agents"""
    tasks = [
        send_message(sender, receiver, payload)
        for receiver in receivers
    ]
    await asyncio.gather(*tasks)
```

### 3. Request-Reply

```python
async def request_reply(sender: Agent, receiver: Agent, request: dict) -> dict:
    """Request-reply pattern with timeout"""
    reply_queue = asyncio.Queue()

    msg = Message(
        msg_id=generate_id(),
        sender=sender.agent_id,
        receiver=receiver.agent_id,
        payload={"request": request, "reply_to": reply_queue},
        trace_id=current_trace_id(),
        timestamp_ms=current_time_ms()
    )

    await receiver.mailbox.put(msg)

    try:
        reply = await asyncio.wait_for(reply_queue.get(), timeout=5.0)
        return reply
    except asyncio.TimeoutError:
        raise TimeoutError(f"No reply from {receiver.agent_id} after 5s")
```

## Performance Considerations

- **Mailbox size**: Max 50 messages per agent (backpressure watermark)
- **Message processing**: <10ms per message (P95 target)
- **Supervisor checks**: 1Hz (1000ms interval)
- **Memory per agent**: <50MB

## Testing with WARD

```python
from ward import test, fixture

@fixture
async def agent():
    """Agent fixture with proper cleanup"""
    a = Agent(
        agent_id="test-agent",
        state=AgentState.PENDING,
        mailbox=asyncio.Queue(maxsize=50),
        capabilities=["TOOL_CALL"],
        memory_mb=10,
        _private_state={}
    )
    yield a
    # Cleanup
    a.state = AgentState.TERMINATED

@test("agent processes messages from mailbox")
async def _(agent=agent):
    """Test Actor Model message processing"""
    msg = Message(
        msg_id="msg-1",
        sender="sender-agent",
        receiver=agent.agent_id,
        payload={"action": "test"},
        trace_id="trace-123",
        timestamp_ms=current_time_ms()
    )

    await agent.receive_message(msg)

    assert agent.mailbox.qsize() == 1
    received = await agent.mailbox.get()
    assert received.msg_id == "msg-1"
```

## Common Pitfalls

❌ **Don't**: Share state between agents
```python
# BAD - shared mutable state
shared_cache = {}
agent1.cache = shared_cache
agent2.cache = shared_cache  # Violates Actor Model!
```

✅ **Do**: Use message-passing
```python
# GOOD - message-passing for coordination
await agent1.send_message(agent2, {"action": "cache_update", "data": value})
```

❌ **Don't**: Block the actor loop
```python
# BAD - blocking I/O
def handle_message(self, msg):
    time.sleep(1)  # Blocks entire agent!
```

✅ **Do**: Use async I/O
```python
# GOOD - async I/O
async def handle_message(self, msg):
    await asyncio.sleep(0)  # Yields control
```

## References

- **Research**: Hewitt, C. (1973). "A Universal Modular Actor Formalism for Artificial Intelligence"
- **K1 Diagram**: `architecture_diagrams/k1_agent_lifecycle_fsm.mmd`
- **Module**: `k1/agent_fabric/` (Layer 1 - Core Kernel)
- **Specifications**: `docs/whiteboard.md` (lines 100-250)
- **Related ADRs**: (to be created)

## See Also

- **Supervisor Pattern**: For agent health monitoring
- **MPST Protocols**: For structured agent interactions
- **Saga Pattern**: For distributed agent coordination
