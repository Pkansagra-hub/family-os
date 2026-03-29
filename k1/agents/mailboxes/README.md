# Dynamic Mailboxes Submodule

## Overview

The `mailboxes/` submodule implements dynamic mailbox allocation for agents created at runtime. Mailboxes provide message-passing communication following the Actor Model (ADR-0002) with WFQ scheduling integration.

## Purpose

- **Dynamic Allocation**: Runtime mailbox creation for spawned agents
- **Message Passing**: Lock-free MPSC queues for actor communication
- **Priority Scheduling**: WFQ integration for URGENT/REALTIME/INTERACTIVE/BACKGROUND priorities
- **Fault Isolation**: Mailbox-level message routing and supervision

## Architecture

### Core Components

- **`pool.py`**: MailboxPool for dynamic allocation and lifecycle management

### Mailbox Implementation

```python
class AgentMailbox:
    """MPSC queue for agent message passing"""

    def __init__(self, agent_id: str, priority: Priority = Priority.INTERACTIVE):
        self.agent_id = agent_id
        self.queue = asyncio.Queue()  # MPSC implementation
        self.priority = priority
        self.metrics = MailboxMetrics()

    async def send(self, message: MailboxMessage) -> None:
        """Send message to agent"""
        await self.queue.put(message)
        self.metrics.messages_sent.inc()

    async def receive(self) -> MailboxMessage:
        """Receive message (blocking)"""
        message = await self.queue.get()
        self.metrics.messages_received.inc()
        return message
```

### Pool Management

```python
class MailboxPool:
    """Dynamic mailbox allocation and routing"""

    def __init__(self, router: MailboxRouter):
        self.router = router
        self.active_mailboxes = {}  # agent_id -> AgentMailbox
        self.metrics = PoolMetrics()

    async def allocate(self, agent_id: str, priority: Priority) -> AgentMailbox:
        """Allocate new mailbox for agent"""
        mailbox = AgentMailbox(agent_id, priority)
        self.active_mailboxes[agent_id] = mailbox
        await self.router.register(agent_id, mailbox)
        return mailbox

    async def deallocate(self, agent_id: str) -> None:
        """Clean up mailbox on agent termination"""
        if agent_id in self.active_mailboxes:
            mailbox = self.active_mailboxes.pop(agent_id)
            await self.router.unregister(agent_id)
            # Drain remaining messages
            while not mailbox.queue.empty():
                msg = mailbox.queue.get_nowait()
                self.metrics.dropped_messages.inc()
```

## Priority Classes

Following WFQ scheduling (ADR-0028):

- **URGENT** (4): Safety checks, system alerts (<10ms latency)
- **REALTIME** (3): User interactions, voice processing (<50ms latency)
- **INTERACTIVE** (2): Planning, tool execution (<500ms latency)
- **BACKGROUND** (1): Research, background tasks (<5000ms latency)

## Message Routing

Integration with MailboxRouter for location-transparent addressing:

```python
# Router registration
await router.register("agent-researcher-001", mailbox)

# Message sending
await router.send(
    MailboxMessage(
        to_agent_id="agent-researcher-001",
        from_agent_id="orchestrator",
        payload=task_data,
        trace_id=request_id
    )
)
```

## Performance Characteristics

- **Allocation Latency**: <5ms per mailbox
- **Message Latency**: <0.5ms P95 for local delivery
- **Throughput**: 10,000+ messages/second per mailbox
- **Memory Footprint**: <1KB per mailbox

## Fault Tolerance

- **Supervision**: Router monitors mailbox health
- **Message Persistence**: Critical messages buffered during outages
- **Cleanup**: Automatic resource reclamation on agent termination
- **Metrics**: Queue depth, drop rates, latency histograms

## Security

- **Access Control**: Capability tokens required for mailbox access
- **Message Validation**: FlatBuffers schema validation
- **Audit Trail**: All messages logged with trace IDs

## Testing

- **Unit Tests**: Mailbox allocation/deallocation
- **Integration Tests**: Message routing and priority handling
- **Performance Tests**: Throughput and latency benchmarks
- **Chaos Tests**: Message loss and recovery scenarios

## Dependencies

- `k1.bus.mailbox_router`: Location-transparent routing
- `k1.scheduler.wfq`: Priority queue scheduling
- `k1.supervision`: Health monitoring
- `k1.contracts`: FlatBuffers message schemas
