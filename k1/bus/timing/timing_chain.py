"""
k1.bus.timing.timing_chain -- Deadline-agnostic ordering enforcement.

The TimingChain sits between LocalBus's envelope stamping and handler
dispatch.  It enforces two ordering constraints based on DeliveryMode:

    1. **Causal ordering** (parent_id):
       An envelope with parent_id=X is held until envelope X has been
       delivered.  This creates a causal chain: parent completes before
       child dispatches.  Works across topics.

    2. **Sequence gap buffering** (per-topic sequence):
       If we see sequence 7 but haven't seen 6 yet, buffer 7 and wait.
       When 6 arrives, deliver 6 then 7 in order.  Prevents reordering
       within a single topic stream.

Both constraints apply ONLY to STRICT topics.  RELAXED topics get
monitoring (log reorders) but immediate delivery.  BEST_EFFORT topics
bypass the chain entirely.

Timeout:
    Buffered envelopes are released after a configurable timeout to
    prevent permanent blocking.  Default: 5000ms.  This is NOT a
    deadline -- it's a safety net for lost envelopes.

Memory safety:
    The gap buffer and causal buffer are both bounded.  If a buffer
    exceeds its limit, oldest entries are force-released with a warning.
    Default buffer limit: 10000 entries per topic (gap) / 50000 global (causal).

Thread safety:
    TimingChain is called from LocalBus._dispatch which runs outside
    the RWLock.  The chain has its own fine-grained locks:
    - Per-topic lock for sequence gap buffers (zero cross-topic contention)
    - Global lock for causal tracking (parent_id lookup is cross-topic)

Architecture:
    +-----------+     +----------------+     +------------+
    | LocalBus  | --> | TimingChain    | --> | Handlers   |
    | (stamped) |     | .process(env)  |     | (ordered)  |
    +-----------+     +----------------+     +------------+
                       | TimingConfig   |
                       | CausalTracker  |
                       | GapBuffer      |
                       +----------------+
"""

from __future__ import annotations

import logging
import threading
import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Callable, Optional

from k1.bus.envelope import DeliveryMode, Envelope
from k1.bus.timing.timing_config import TimingConfig

logger = logging.getLogger(__name__)

# Type alias for the dispatch callback
DispatchFn = Callable[[Envelope], None]


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------


@dataclass
class TimingStats:
    """Observable timing chain statistics."""

    envelopes_processed: int = 0
    delivered_immediate: int = 0
    buffered_causal: int = 0
    buffered_gap: int = 0
    released_causal: int = 0
    released_gap: int = 0
    released_timeout: int = 0
    reorders_detected: int = 0
    dropped_best_effort: int = 0

    def snapshot(self) -> dict[str, int]:
        return {
            "envelopes_processed": self.envelopes_processed,
            "delivered_immediate": self.delivered_immediate,
            "buffered_causal": self.buffered_causal,
            "buffered_gap": self.buffered_gap,
            "released_causal": self.released_causal,
            "released_gap": self.released_gap,
            "released_timeout": self.released_timeout,
            "reorders_detected": self.reorders_detected,
            "dropped_best_effort": self.dropped_best_effort,
        }


# ---------------------------------------------------------------------------
# Buffered envelope wrapper (tracks buffer entry time)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _BufferedEnvelope:
    """Envelope waiting in a buffer with entry timestamp."""

    __slots__ = ("envelope", "buffered_at_ns")
    envelope: Envelope
    buffered_at_ns: int


# ---------------------------------------------------------------------------
# Causal Tracker -- enforces parent_id ordering across all topics
# ---------------------------------------------------------------------------


class _CausalTracker:
    """
    Tracks delivered envelope_ids and buffers children waiting for parents.

    When envelope X is delivered, any children buffered waiting for
    parent_id=X are released.  This cascades: if releasing child Y
    causes grandchild Z to become ready, Z is released too.

    Thread-safe via a single lock (causal relationships are cross-topic).
    """

    __slots__ = ("_delivered", "_waiting", "_lock", "_max_buffer")

    def __init__(self, max_buffer: int = 50_000) -> None:
        # Set of delivered envelope_ids
        self._delivered: set[int] = set()
        # parent_id -> list of children waiting
        self._waiting: dict[int, list[_BufferedEnvelope]] = defaultdict(list)
        self._lock = threading.Lock()
        self._max_buffer = max_buffer

    def is_parent_delivered(self, parent_id: int) -> bool:
        """Check if a parent envelope has been delivered (or is root)."""
        if parent_id == 0:
            return True  # Root envelope, no parent
        with self._lock:
            return parent_id in self._delivered

    def mark_delivered(self, envelope_id: int) -> list[_BufferedEnvelope]:
        """
        Mark an envelope as delivered and return any children that
        were waiting for it.

        Returns:
            List of buffered children now ready for delivery.
            May cascade: if child C was waiting for parent P, and
            marking P releases C, this returns [C].  Caller should
            then mark C as delivered and check for grandchildren.
        """
        with self._lock:
            self._delivered.add(envelope_id)
            children = self._waiting.pop(envelope_id, [])
            return children

    def buffer_child(self, parent_id: int, buffered: _BufferedEnvelope) -> None:
        """Buffer a child envelope waiting for its parent to be delivered."""
        with self._lock:
            waiters = self._waiting[parent_id]
            waiters.append(buffered)

            # Safety: bound the total buffer size
            total = sum(len(v) for v in self._waiting.values())
            if total > self._max_buffer:
                self._force_release_oldest()

    def get_timed_out(self, timeout_ns: int, now_ns: int) -> list[_BufferedEnvelope]:
        """
        Find and remove buffered envelopes that have exceeded the timeout.

        Args:
            timeout_ns: Timeout in nanoseconds.
            now_ns:     Current monotonic time in nanoseconds.

        Returns:
            List of timed-out buffered envelopes, removed from the buffer.
        """
        cutoff = now_ns - timeout_ns
        timed_out: list[_BufferedEnvelope] = []

        with self._lock:
            empty_parents: list[int] = []
            for parent_id, waiters in self._waiting.items():
                released: list[_BufferedEnvelope] = []
                remaining: list[_BufferedEnvelope] = []
                for be in waiters:
                    if be.buffered_at_ns <= cutoff:
                        released.append(be)
                    else:
                        remaining.append(be)
                if released:
                    timed_out.extend(released)
                    if remaining:
                        self._waiting[parent_id] = remaining
                    else:
                        empty_parents.append(parent_id)
            for pid in empty_parents:
                del self._waiting[pid]

        return timed_out

    @property
    def pending_count(self) -> int:
        """Total number of envelopes buffered waiting for parents."""
        with self._lock:
            return sum(len(v) for v in self._waiting.values())

    def _force_release_oldest(self) -> None:
        """Emergency release: drop oldest 10% when buffer overflows."""
        all_buffered: list[tuple[int, _BufferedEnvelope]] = []
        for parent_id, waiters in self._waiting.items():
            for be in waiters:
                all_buffered.append((parent_id, be))

        all_buffered.sort(key=lambda x: x[1].buffered_at_ns)
        release_count = max(1, len(all_buffered) // 10)

        released_parents: set[int] = set()
        for i in range(release_count):
            parent_id, be = all_buffered[i]
            released_parents.add(parent_id)

        # Rebuild waiting without released entries
        for parent_id in released_parents:
            waiters = self._waiting.get(parent_id, [])
            cutoff_time = all_buffered[release_count - 1][1].buffered_at_ns
            self._waiting[parent_id] = [be for be in waiters if be.buffered_at_ns > cutoff_time]
            if not self._waiting[parent_id]:
                del self._waiting[parent_id]

        logger.warning(
            "CausalTracker: force-released ~%d entries (buffer overflow, max=%d)",
            release_count,
            self._max_buffer,
        )


# ---------------------------------------------------------------------------
# Gap Buffer -- per-topic sequence gap detection and buffering
# ---------------------------------------------------------------------------


class _GapBuffer:
    """
    Per-topic sequence gap buffer.

    Maintains expected next sequence per topic.  If an envelope arrives
    with sequence > expected, it's buffered until the gap is filled.

    Thread-safe: per-topic locks (zero cross-topic contention).
    """

    __slots__ = (
        "_expected",
        "_buffers",
        "_locks",
        "_global_lock",
        "_max_per_topic",
    )

    def __init__(self, max_per_topic: int = 10_000) -> None:
        self._expected: dict[str, int] = {}  # topic -> next expected seq
        self._buffers: dict[str, dict[int, _BufferedEnvelope]] = {}  # topic -> {seq: be}
        self._locks: dict[str, threading.Lock] = {}
        self._global_lock = threading.Lock()
        self._max_per_topic = max_per_topic

    def check_and_buffer(self, envelope: Envelope, now_ns: int) -> tuple[bool, list[Envelope]]:
        """
        Check if an envelope is in-sequence or needs buffering.

        Args:
            envelope: The stamped envelope to check.
            now_ns:   Current monotonic time in nanoseconds.

        Returns:
            (is_ready, release_list):
                is_ready=True means this envelope should be delivered now.
                release_list contains any previously-buffered envelopes that
                can now be released (gap filled).  They are in sequence order.
        """
        topic = envelope.topic
        seq = envelope.sequence
        lock = self._get_lock(topic)

        with lock:
            expected = self._expected.get(topic, 1)

            if seq == expected:
                # In-sequence: deliver and check if buffered successors can release
                self._expected[topic] = expected + 1
                release = self._release_successors(topic)
                return True, release

            if seq < expected:
                # Duplicate or old: deliver anyway (idempotent handlers)
                return True, []

            # Gap detected: seq > expected, buffer this envelope
            buf = self._buffers.get(topic)
            if buf is None:
                buf = {}
                self._buffers[topic] = buf

            buf[seq] = _BufferedEnvelope(envelope=envelope, buffered_at_ns=now_ns)

            # Safety: bound per-topic buffer
            if len(buf) > self._max_per_topic:
                self._force_release_oldest_topic(topic)

            return False, []

    def get_timed_out(self, topic: str, timeout_ns: int, now_ns: int) -> list[Envelope]:
        """
        Find and remove timed-out buffered envelopes for a topic.

        Returns them in sequence order.
        """
        cutoff = now_ns - timeout_ns
        lock = self._get_lock(topic)
        released: list[Envelope] = []

        with lock:
            buf = self._buffers.get(topic)
            if not buf:
                return released

            timed_out_seqs = [seq for seq, be in buf.items() if be.buffered_at_ns <= cutoff]
            for seq in sorted(timed_out_seqs):
                be = buf.pop(seq)
                released.append(be.envelope)

            # Advance expected past the gap
            if released:
                max_released_seq = max(e.sequence for e in released)
                expected = self._expected.get(topic, 1)
                if max_released_seq >= expected:
                    self._expected[topic] = max_released_seq + 1
                    # Also release any buffered successors
                    successors = self._release_successors(topic)
                    released.extend(successors)

            if buf is not None and not buf:
                del self._buffers[topic]

        return released

    def get_all_timed_out(self, timeout_ns: int, now_ns: int) -> list[Envelope]:
        """Find and remove timed-out envelopes across ALL topics."""
        # Snapshot topics to avoid lock ordering issues
        topics = list(self._buffers.keys())
        result: list[Envelope] = []
        for topic in topics:
            result.extend(self.get_timed_out(topic, timeout_ns, now_ns))
        return result

    @property
    def total_buffered(self) -> int:
        """Total envelopes buffered across all topics."""
        return sum(len(b) for b in self._buffers.values())

    def pending_for_topic(self, topic: str) -> int:
        """Number of envelopes buffered for a specific topic."""
        buf = self._buffers.get(topic)
        return len(buf) if buf else 0

    def expected_sequence(self, topic: str) -> int:
        """Next expected sequence for a topic (1 if never seen)."""
        return self._expected.get(topic, 1)

    def _release_successors(self, topic: str) -> list[Envelope]:
        """Release consecutive buffered envelopes starting from expected."""
        buf = self._buffers.get(topic)
        if not buf:
            return []

        released: list[Envelope] = []
        expected = self._expected.get(topic, 1)

        while expected in buf:
            be = buf.pop(expected)
            released.append(be.envelope)
            expected += 1

        self._expected[topic] = expected

        if not buf and topic in self._buffers:
            del self._buffers[topic]

        return released

    def _force_release_oldest_topic(self, topic: str) -> None:
        """Emergency release: drop oldest 10% for a topic."""
        buf = self._buffers.get(topic)
        if not buf:
            return

        sorted_seqs = sorted(buf.keys())
        release_count = max(1, len(sorted_seqs) // 10)
        for seq in sorted_seqs[:release_count]:
            del buf[seq]

        # Advance expected
        if sorted_seqs[release_count:]:
            self._expected[topic] = sorted_seqs[release_count]

        logger.warning(
            "GapBuffer: force-released %d entries for topic %s (max=%d)",
            release_count,
            topic,
            self._max_per_topic,
        )

    def _get_lock(self, topic: str) -> threading.Lock:
        """Get or create per-topic lock. Double-checked locking."""
        lock = self._locks.get(topic)
        if lock is not None:
            return lock
        with self._global_lock:
            lock = self._locks.get(topic)
            if lock is None:
                lock = threading.Lock()
                self._locks[topic] = lock
            return lock


# ---------------------------------------------------------------------------
# TimingChain -- the orchestrator of ordering enforcement
# ---------------------------------------------------------------------------


class TimingChain:
    """
    Deadline-agnostic ordering enforcement for the K1 bus.

    The TimingChain sits between LocalBus envelope stamping and handler
    dispatch.  For each envelope, it:

        1. Resolves delivery mode via TimingConfig
        2. For BEST_EFFORT: deliver immediately, no tracking
        3. For RELAXED: deliver immediately, log if out of order
        4. For STRICT:
           a. Check causal ordering (parent_id delivered?)
              - Yes: proceed to sequence check
              - No: buffer until parent delivered
           b. Check sequence ordering (is this the next expected seq?)
              - Yes: deliver, then release any buffered successors
              - No: buffer until gap filled or timeout

    Timeout sweep:
        Call sweep() periodically (e.g., every 1s) to release buffered
        envelopes that have exceeded the timeout.  This prevents permanent
        blocking from lost envelopes.

    Usage::

        config = TimingConfig(rules={...})
        chain = TimingChain(config=config)

        # In LocalBus.publish, after stamping:
        chain.process(stamped_envelope, dispatch_fn)

        # Periodic sweep (in a background thread or ticker):
        chain.sweep(dispatch_fn)
    """

    __slots__ = (
        "_config",
        "_causal",
        "_gap",
        "_stats",
        "_timeout_ns",
        "_last_sweep_ns",
    )

    def __init__(
        self,
        config: Optional[TimingConfig] = None,
        timeout_ms: int = 5000,
        causal_buffer_limit: int = 50_000,
        gap_buffer_limit: int = 10_000,
    ) -> None:
        """
        Create a TimingChain.

        Args:
            config:              TimingConfig for prefix -> mode resolution.
                                 None = default config (everything RELAXED).
            timeout_ms:          Timeout for buffered envelopes in milliseconds.
                                 After this, buffered envelopes are force-released.
                                 NOT a deadline -- a safety net for lost messages.
            causal_buffer_limit: Max envelopes in the causal buffer before
                                 emergency release.
            gap_buffer_limit:    Max envelopes per topic in the gap buffer
                                 before emergency release.
        """
        self._config = config or TimingConfig()
        self._causal = _CausalTracker(max_buffer=causal_buffer_limit)
        self._gap = _GapBuffer(max_per_topic=gap_buffer_limit)
        self._stats = TimingStats()
        self._timeout_ns = timeout_ms * 1_000_000
        self._last_sweep_ns = time.monotonic_ns()

    def process(self, envelope: Envelope, dispatch: DispatchFn) -> None:
        """
        Process an envelope through the timing chain.

        Depending on delivery mode, the envelope may be:
            - Delivered immediately (BEST_EFFORT, RELAXED, or in-order STRICT)
            - Buffered for causal ordering (STRICT, parent not yet delivered)
            - Buffered for sequence gap fill (STRICT, gap detected)

        Args:
            envelope: Bus-stamped envelope (has envelope_id, sequence, created_ns).
            dispatch: Callback to invoke for delivery (typically LocalBus._dispatch_single).
        """
        self._stats.envelopes_processed += 1
        mode = self._config.resolve(envelope.topic)

        if mode == DeliveryMode.BEST_EFFORT:
            self._deliver(envelope, dispatch)
            self._stats.delivered_immediate += 1
            return

        if mode == DeliveryMode.RELAXED:
            self._process_relaxed(envelope, dispatch)
            return

        # STRICT mode: full ordering enforcement
        self._process_strict(envelope, dispatch)

    def sweep(self, dispatch: DispatchFn) -> int:
        """
        Release timed-out buffered envelopes.

        Call this periodically (e.g., every 1s).  Returns the number
        of envelopes released.

        Args:
            dispatch: Callback for delivering released envelopes.

        Returns:
            Number of envelopes force-released due to timeout.
        """
        now_ns = time.monotonic_ns()
        released_count = 0

        # Sweep causal buffer
        causal_timed_out = self._causal.get_timed_out(self._timeout_ns, now_ns)
        for be in causal_timed_out:
            self._deliver(be.envelope, dispatch)
            self._causal.mark_delivered(be.envelope.envelope_id)
            released_count += 1
            self._stats.released_timeout += 1

        # Sweep gap buffer
        gap_timed_out = self._gap.get_all_timed_out(self._timeout_ns, now_ns)
        for env in gap_timed_out:
            self._deliver(env, dispatch)
            self._causal.mark_delivered(env.envelope_id)
            released_count += 1
            self._stats.released_timeout += 1

        if released_count > 0:
            logger.info("TimingChain.sweep: released %d timed-out envelopes", released_count)

        self._last_sweep_ns = now_ns
        return released_count

    # ------------------------------------------------------------------
    # Internal: mode-specific processing
    # ------------------------------------------------------------------

    def _process_relaxed(self, envelope: Envelope, dispatch: DispatchFn) -> None:
        """RELAXED: deliver immediately, log reordering."""
        now_ns = time.monotonic_ns()
        expected = self._gap.expected_sequence(envelope.topic)

        if envelope.sequence < expected:
            self._stats.reorders_detected += 1
            logger.debug(
                "TimingChain RELAXED reorder: topic=%s seq=%d expected=%d",
                envelope.topic,
                envelope.sequence,
                expected,
            )

        # Deliver immediately regardless
        self._deliver(envelope, dispatch)
        self._stats.delivered_immediate += 1

        # Still update expected sequence for tracking
        if envelope.sequence >= expected:
            # Use check_and_buffer to update state, but ignore buffering
            # (RELAXED never buffers, just tracks)
            self._gap.check_and_buffer(envelope, now_ns)

    def _process_strict(self, envelope: Envelope, dispatch: DispatchFn) -> None:
        """STRICT: enforce causal + sequence ordering."""
        now_ns = time.monotonic_ns()

        # Step 1: Causal check (parent must be delivered first)
        if not self._causal.is_parent_delivered(envelope.parent_id):
            self._causal.buffer_child(
                envelope.parent_id,
                _BufferedEnvelope(envelope=envelope, buffered_at_ns=now_ns),
            )
            self._stats.buffered_causal += 1
            return

        # Step 2: Sequence gap check
        is_ready, released = self._gap.check_and_buffer(envelope, now_ns)

        if is_ready:
            # In-sequence: deliver this envelope
            self._deliver(envelope, dispatch)

            # Deliver any released successors (gap filled)
            for rel in released:
                self._deliver(rel, dispatch)
                self._stats.released_gap += 1

            # Check if delivering this envelope releases causal children
            self._cascade_causal(envelope.envelope_id, dispatch)
            for rel in released:
                self._cascade_causal(rel.envelope_id, dispatch)
        else:
            self._stats.buffered_gap += 1

    def _cascade_causal(self, envelope_id: int, dispatch: DispatchFn) -> None:
        """
        After delivering an envelope, check if any children were
        waiting for it as their causal parent.  Cascade recursively.
        """
        children = self._causal.mark_delivered(envelope_id)
        for child_be in children:
            child = child_be.envelope
            self._stats.released_causal += 1

            # The child still needs sequence check
            now_ns = time.monotonic_ns()
            is_ready, released = self._gap.check_and_buffer(child, now_ns)

            if is_ready:
                self._deliver(child, dispatch)
                for rel in released:
                    self._deliver(rel, dispatch)
                    self._stats.released_gap += 1
                # Cascade further
                self._cascade_causal(child.envelope_id, dispatch)
                for rel in released:
                    self._cascade_causal(rel.envelope_id, dispatch)
            else:
                self._stats.buffered_gap += 1

    def _deliver(self, envelope: Envelope, dispatch: DispatchFn) -> None:
        """Deliver an envelope via the dispatch callback."""
        dispatch(envelope)

    # ------------------------------------------------------------------
    # Observability
    # ------------------------------------------------------------------

    @property
    def stats(self) -> TimingStats:
        """Access timing chain statistics."""
        return self._stats

    @property
    def config(self) -> TimingConfig:
        """Access the timing configuration."""
        return self._config

    @property
    def causal_pending(self) -> int:
        """Number of envelopes waiting for causal parents."""
        return self._causal.pending_count

    @property
    def gap_pending(self) -> int:
        """Total envelopes buffered across all topic gap buffers."""
        return self._gap.total_buffered

    @property
    def timeout_ms(self) -> int:
        """Configured timeout in milliseconds."""
        return self._timeout_ns // 1_000_000

    def gap_pending_for_topic(self, topic: str) -> int:
        """Number of envelopes buffered for a specific topic's gap."""
        return self._gap.pending_for_topic(topic)

    def __repr__(self) -> str:
        return (
            f"TimingChain(causal_pending={self.causal_pending}, "
            f"gap_pending={self.gap_pending}, "
            f"timeout_ms={self.timeout_ms})"
        )
