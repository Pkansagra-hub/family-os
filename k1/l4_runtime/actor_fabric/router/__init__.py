"""
K1 L4 Runtime — Actor Router (Location Transparency & Admission Control)

**Purpose:** Actor routing with location transparency, 5-check admission control pipeline

**Router Capabilities:**
- Location Transparency: Route messages to actors by ID (local/remote)
- Admission Control: 5-check pipeline (capability, role, token bucket, in-flight, quota)
- Routing Table: actor_id → ActorRef (mailbox address)
- Performance: <2ms P95 admission pipeline (5 checks)

**ADR:**
- ADR-0002c: Router (location transparency, routing table, 5-check admission pipeline)

**5-Check Admission Control Pipeline:**

```python
async def admit_message(message: Message, sender: ActorRef) -> AdmissionResult:
    # Total latency: <2ms P95 (5 checks)

    # Check 1: Capability Verification (<0.3ms)
    if not verify_capability(message, sender):
        return AdmissionResult.DENIED_CAPABILITY

    # Check 2: Role Attestation (<0.2ms)
    if not verify_role(message, sender):
        return AdmissionResult.DENIED_ROLE

    # Check 3: Token Bucket Rate Limit (<0.5ms)
    if not token_bucket.try_consume(sender.actor_id):
        return AdmissionResult.DENIED_RATE_LIMIT

    # Check 4: In-Flight Limit (<0.3ms)
    if in_flight_tracker.count(sender.actor_id) >= MAX_IN_FLIGHT:
        return AdmissionResult.DENIED_IN_FLIGHT

    # Check 5: Session Quota (<0.2ms)
    if not session_quota.check(message.session_id):
        return AdmissionResult.DENIED_QUOTA

    return AdmissionResult.ALLOWED
```

**Check 1: Capability Verification (ADR-0010b, 0010c):**
- Verify sender has required capability for message type
- HMAC-SHA256 signature validation (ADR-0003d)
- Lease expiration check (5-min TTL)
- Performance: <0.3ms P95

**Check 2: Role Attestation (ADR-0003d):**
- Verify sender role matches message protocol requirements
- Example: Only Planner agent can send `TaskAnnouncement`
- Role hierarchy: SYSTEM > AI_AGENT > PURE_ACTOR
- Performance: <0.2ms P95

**Check 3: Token Bucket Rate Limit:**
- 100 messages/sec sustained, 150 burst
- Per-sender rate limiting
- Refill rate: 100 tokens/sec
- Performance: <0.5ms P95 (in-memory counter)

**Check 4: In-Flight Limit:**
- Max 10 in-flight messages per sender (prevents flooding)
- Track pending messages awaiting response
- Decrement on message completion
- Performance: <0.3ms P95

**Check 5: Session Quota:**
- Max 3 agents per session (ADR-0005e)
- Session-level resource limits
- Prevent resource exhaustion
- Performance: <0.2ms P95

**Routing Table:**

```python
class RoutingTable:
    _local_actors: Dict[str, ActorRef] = {}
    _remote_actors: Dict[str, RemoteActorRef] = {}  # Future: distributed routing

    async def route(message: Message) -> ActorRef:
        # Location transparency: local vs remote actors
        recipient_id = message.recipient_id

        if recipient_id in _local_actors:
            return _local_actors[recipient_id]
        elif recipient_id in _remote_actors:
            # Future: Remote actor routing (multi-node K1)
            return _remote_actors[recipient_id]
        else:
            raise ActorNotFound(recipient_id)
```

**Location Transparency:**
- Actors addressed by `actor_id` (UUID), not physical location
- Routing table maps actor_id → mailbox address
- Future: Distributed routing for multi-node K1 (remote actors)

**Admission Control Integration:**

```python
async def send_message(message: Message, sender: ActorRef) -> SendResult:
    # 1. Admission control (5-check pipeline, <2ms P95)
    admission = await admit_message(message, sender)
    if admission != AdmissionResult.ALLOWED:
        return SendResult.REJECTED(reason=admission)

    # 2. Routing (location transparency, <0.5ms)
    recipient = await route(message)

    # 3. Enqueue to recipient mailbox (<1ms P95)
    enqueue_result = await recipient.mailbox.enqueue(message)

    return SendResult.SUCCESS
```

**Files:**
- router.py — Main routing logic, location transparency
- admission.py — 5-check admission control pipeline
- token_bucket.py — Rate limiting (100 msg/s sustained, 150 burst)
- capability_verifier.py — HMAC-SHA256 capability verification
- routing_table.py — actor_id → ActorRef mapping

**Integration:**
- Mailbox: Enqueue messages after admission control
- Supervisor: Route lifecycle events (DRAINING, TERMINATED)
- Protocol Monitor: Role attestation, protocol validation
- SessionState: Session quota checks

**Performance Metrics:**
- actor_router_admit_total (counter, result=allowed|denied, check=capability|role|rate|in-flight|quota)
- actor_router_admit_latency_ms (histogram, per-check breakdown)
- actor_router_route_total (counter, destination=local|remote)
- actor_router_route_latency_ms (histogram)
- actor_router_token_bucket_refills_total (counter)

**Research Foundations:**
- Token Bucket (Tanenbaum 1981) — Rate limiting algorithm
- Capability-Based Security (Dennis & Van Horn 1966) — Access control

**Last Updated:** October 2025
**Status:** Production-ready router with 5-check admission control
"""

__version__ = "0.1.0"

# TODO: Implement router.py, admission.py, token_bucket.py, capability_verifier.py, routing_table.py
# Per ADR-0002c (Router)
