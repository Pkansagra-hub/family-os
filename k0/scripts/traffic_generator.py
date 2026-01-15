#!/usr/bin/env python3
"""
Traffic Generator for Staging Burn-in (Issue 9.4.1)

Generates representative traffic patterns for v1.0.0-rc staging validation.

Usage:
    python scripts/traffic_generator.py \
        --endpoint http://staging.k0.local \
        --rate 100 \
        --duration 4h \
        --scenario baseline

Scenarios:
    baseline: Steady command submission at specified rate
    burst: 2x rate with periodic spikes
    mixed: Commands (60%), queries (30%), SSE (10%)
    sustained: Long-running soak test
    comprehensive: Tests ALL endpoints (commands, queries, SSE, health, metrics, drivers)

Prerequisite for local stacks:
    python scripts/bootstrap_local_kernel.py

Requirements:
    pip install httpx asyncio pydantic
"""

import argparse
import asyncio
import hashlib
import json
import logging
import os
import random
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urljoin

import asyncpg
import httpx
from pydantic import BaseModel, HttpUrl

from k0.local.dev_profile import default_profile, signing_key_for
from k0.security import canonical_envelope, canonical_json
from k0.security.crypto import encode_base64url

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='{"timestamp": "%(asctime)s", "level": "%(levelname)s", "message": "%(message)s"}',
)
logger = logging.getLogger(__name__)


# ============================================================================
# Outbox Cleaner
# ============================================================================


async def clear_outbox_backlog(
    db_url: str = "postgresql://k0_user:k0_password@localhost:5432/k0_kernel",
) -> dict:
    """
    Clear outbox and DLQ backlog before starting traffic.

    Returns:
        dict with 'outbox_cleared' and 'dlq_cleared' counts
    """
    if db_url is None:
        db_url = os.getenv(
            "K0_DATABASE_URL",
            "postgresql://k0_user:k0_password@localhost:5432/k0_kernel",
        )

    logger.info("=" * 60)
    logger.info("CLEARING OUTBOX BACKLOG")
    logger.info("=" * 60)

    try:
        conn = await asyncpg.connect(db_url)

        # Get outbox stats before clearing
        row = await conn.fetchrow("SELECT COUNT(*) as total FROM st_outbox")
        outbox_before = row["total"]

        row = await conn.fetchrow(
            "SELECT COUNT(*) as pending FROM st_outbox WHERE state != 'completed'"
        )
        outbox_pending = row["pending"]

        row = await conn.fetchrow("SELECT COUNT(*) as total FROM st_dlq")
        dlq_before = row["total"]

        logger.info("Current state:")
        logger.info(f"   Outbox total: {outbox_before}")
        logger.info(f"   Outbox pending: {outbox_pending}")
        logger.info(f"   DLQ total: {dlq_before}")

        # Clear outbox
        result = await conn.execute("DELETE FROM st_outbox")
        outbox_cleared = int(result.split()[-1]) if result else 0
        logger.info(f"Cleared {outbox_cleared} entries from st_outbox")

        # Clear DLQ
        result = await conn.execute("DELETE FROM st_dlq")
        dlq_cleared = int(result.split()[-1]) if result else 0
        logger.info(f"Cleared {dlq_cleared} entries from st_dlq")

        # Vacuum tables (PostgreSQL requires table name)
        logger.info("Running VACUUM to reclaim space...")
        await conn.execute("VACUUM st_outbox")
        await conn.execute("VACUUM st_dlq")
        logger.info("VACUUM completed")

        await conn.close()

        logger.info("=" * 60)
        logger.info("OUTBOX CLEANUP COMPLETE")
        logger.info("=" * 60)
        logger.info("")

        return {
            "outbox_cleared": outbox_cleared,
            "dlq_cleared": dlq_cleared,
            "outbox_before": outbox_before,
            "dlq_before": dlq_before,
        }

    except Exception as e:
        logger.error(f"Failed to clear outbox: {e}")
        raise


# ============================================================================
# Configuration Models
# ============================================================================


class TrafficConfig(BaseModel):
    """Traffic generation configuration."""

    endpoint: HttpUrl
    rate: int  # Requests per second
    duration_seconds: int
    scenario: str
    command_ratio: float = 0.6
    query_ratio: float = 0.3
    sse_ratio: float = 0.1
    output_dir: Path = Path("artifacts/traffic")
    test_all_endpoints: bool = False  # Enable comprehensive endpoint testing


@dataclass
class TrafficMetrics:
    """Traffic generation metrics."""

    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    total_latency_ms: float = 0.0
    min_latency_ms: float = float("inf")
    max_latency_ms: float = 0.0
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None

    # Per-endpoint metrics
    endpoint_requests: dict[str, int] = field(default_factory=dict)
    endpoint_successes: dict[str, int] = field(default_factory=dict)
    endpoint_failures: dict[str, int] = field(default_factory=dict)


# ============================================================================
# Traffic Generator
# ============================================================================


class TrafficGenerator:
    """Generates traffic patterns for staging burn-in."""

    def __init__(self, config: TrafficConfig):
        self.config = config
        self.metrics = TrafficMetrics()
        self.client: Optional[httpx.AsyncClient] = None
        self.running = False
        self.profile = default_profile()
        self.signing_key = signing_key_for(self.profile)

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    async def start(self):
        """Start traffic generation."""
        logger.info(
            f"Starting traffic generator: scenario={self.config.scenario}, rate={self.config.rate} req/s, duration={self.config.duration_seconds}s"
        )

        self.metrics.start_time = self._now()
        self.running = True

        # Create HTTP client
        client = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0),
            limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
        )
        self.client = client

        try:
            # Select scenario
            if self.config.scenario == "baseline":
                await self._run_baseline()
            elif self.config.scenario == "burst":
                await self._run_burst()
            elif self.config.scenario == "mixed":
                await self._run_mixed()
            elif self.config.scenario == "sustained":
                await self._run_sustained()
            elif self.config.scenario == "comprehensive":
                await self._run_comprehensive()
            else:
                raise ValueError(f"Unknown scenario: {self.config.scenario}")

        finally:
            self.metrics.end_time = self._now()
            await client.aclose()
            self.client = None
            self.running = False
            self._report_metrics()

    async def _run_baseline(self):
        """Baseline traffic: steady rate."""
        end_time = self._now() + timedelta(seconds=self.config.duration_seconds)
        interval = 1.0 / self.config.rate  # Seconds between requests

        while self._now() < end_time and self.running:
            request_start = time.time()

            # Submit command
            await self._submit_command()

            # Calculate sleep time to maintain rate
            elapsed = time.time() - request_start
            sleep_time = max(0, interval - elapsed)
            await asyncio.sleep(sleep_time)

            # Log progress every 100 requests
            if self.metrics.total_requests % 100 == 0:
                self._log_progress()

    async def _run_burst(self):
        """Burst traffic: 2x rate with periodic spikes."""
        end_time = self._now() + timedelta(seconds=self.config.duration_seconds)
        base_rate = self.config.rate
        burst_rate = self.config.rate * 2
        burst_duration = 60  # 1 minute bursts
        quiet_duration = 300  # 5 minute quiet periods

        while self._now() < end_time and self.running:
            # Burst period
            logger.info(f"Starting burst period: {burst_rate} req/s for {burst_duration}s")
            await self._generate_traffic(burst_rate, burst_duration)

            # Quiet period
            if self._now() < end_time:
                logger.info(f"Starting quiet period: {base_rate} req/s for {quiet_duration}s")
                await self._generate_traffic(base_rate, quiet_duration)

    async def _run_mixed(self):
        """Mixed workload: commands, queries, SSE subscriptions."""
        end_time = self._now() + timedelta(seconds=self.config.duration_seconds)
        interval = 1.0 / self.config.rate

        while self._now() < end_time and self.running:
            request_start = time.time()

            # Choose request type based on ratios
            rand = random.random()
            if rand < self.config.command_ratio:
                await self._submit_command()
            elif rand < self.config.command_ratio + self.config.query_ratio:
                await self._submit_query()
            else:
                await self._subscribe_sse()

            # Maintain rate
            elapsed = time.time() - request_start
            sleep_time = max(0, interval - elapsed)
            await asyncio.sleep(sleep_time)

            if self.metrics.total_requests % 100 == 0:
                self._log_progress()

    async def _run_sustained(self):
        """Sustained load: long-running soak test."""
        # Same as baseline but logs more frequently
        end_time = self._now() + timedelta(seconds=self.config.duration_seconds)
        interval = 1.0 / self.config.rate

        while self._now() < end_time and self.running:
            request_start = time.time()
            await self._submit_command()

            elapsed = time.time() - request_start
            sleep_time = max(0, interval - elapsed)
            await asyncio.sleep(sleep_time)

            # Log every 500 requests for soak test
            if self.metrics.total_requests % 500 == 0:
                self._log_progress()
                self._check_memory_leak()

    async def _generate_traffic(self, rate: int, duration: int):
        """Generate traffic at specified rate for duration."""
        end_time = self._now() + timedelta(seconds=duration)
        interval = 1.0 / rate

        while self._now() < end_time and self.running:
            request_start = time.time()
            await self._submit_command()

            elapsed = time.time() - request_start
            sleep_time = max(0, interval - elapsed)
            await asyncio.sleep(sleep_time)

    # ========================================================================
    # Request Methods
    # ========================================================================

    async def _submit_command(self):
        """Submit a command envelope compliant with the Minimal Gate."""
        envelope = self._build_command_envelope(self.metrics.total_requests)
        await self._make_request("POST", "/k0/command.submit", json=envelope)

    def _build_command_envelope(self, sequence: int) -> dict[str, Any]:
        profile = self.profile
        trace_id = str(uuid.uuid4())
        observed_at = self._now().isoformat(timespec="milliseconds").replace("+00:00", "Z")

        # REAL memory store operation that persists to database
        # This triggers: UoW commit → WAL fsync → Outbox population → Replay → SSE delivery
        memory_id = f"mem_{sequence}_{uuid.uuid4().hex[:8]}"
        body: dict[str, Any] = {
            "operation": "memory.store",  # Changed from UPSERT to trigger actual persistence
            "memory_id": memory_id,
            "content": {
                "type": "episodic",
                "title": f"Burn-in Test Memory #{sequence}",
                "body": f"This is a test memory created during burn-in testing at {observed_at}",
                "tags": ["burn-in", "test", f"seq-{sequence}"],
                "metadata": {
                    "sequence": sequence,
                    "trace_id": trace_id,
                    "source": "traffic_generator",
                },
            },
            "embedding": [random.random() for _ in range(384)],  # Fake embedding for vector search
        }

        body_json = canonical_json(body)
        body_bytes = body_json.encode("utf-8")
        payload_sha256 = hashlib.sha256(body_bytes).hexdigest()

        envelope: dict[str, Any] = {
            "cognitive_trace_id": trace_id,
            "tenant_id": profile.tenant_id,
            "space_id": profile.space_id,
            "device_id": profile.device_id,
            "topic": profile.topic,
            "schema_uri": profile.schema_uri,
            "schema_version": profile.schema_version,
            "actor": profile.actor,
            "band": "GREEN",
            "policy_version": profile.policy_version,
            "ts": observed_at,
            "payload_sha256": payload_sha256,
            "payload_bytes": len(body_bytes),
            "policy": {
                "abac": {
                    "roles": ["coordinator"],
                }
            },
            "policy_ctx": {
                "source": "traffic_generator",
                "sequence": sequence,
            },
        }

        message = canonical_envelope(envelope)
        signature = encode_base64url(self.signing_key.sign(message).signature)
        envelope["sig"] = signature
        envelope["body"] = body
        return envelope

    async def _submit_query(self):
        """Submit a query recall request for stored memories."""
        payload: dict[str, Any] = {
            "selectors": [
                {
                    "type": "episodic",
                    "topic": self.profile.topic,  # Query our own topic where we stored memories
                    "tags": ["burn-in"],  # Filter for burn-in test memories
                    "limit": 50,  # Return up to 50 memories
                }
            ],
            "space_id": self.profile.space_id,
            "tenant_id": self.profile.tenant_id,
        }
        await self._make_request("POST", "/k0/query.recall", json=payload)

    async def _subscribe_sse(self):
        """Subscribe to SSE (simplified - just test endpoint)."""
        # Note: Real SSE would require long-lived connection
        # This just tests the subscribe endpoint
        headers = {
            "X-SSE-Subscriber": f"traffic-gen-{uuid.uuid4().hex[:12]}",
            "X-SSE-Roles": "coordinator",
        }
        await self._make_request(
            "GET",
            "/k0/sse.subscribe",
            params={
                "topics": "test.*",
                "space_id": self.profile.space_id,
                "tenant_id": self.profile.tenant_id,
            },
            headers=headers,
        )

    async def _test_health_endpoints(self):
        """Test all health and observability endpoints."""
        # Liveness probe
        await self._make_request("GET", "/healthz")

        # Readiness probe
        await self._make_request("GET", "/readyz")

        # Metrics endpoint
        await self._make_request("GET", "/metrics")

    async def _test_sse_ack(self):
        """Test SSE acknowledgment endpoint."""
        ack_payload: dict[str, Any] = {
            "subscriber_id": "traffic_gen_subscriber",
            "tenant_id": self.profile.tenant_id,
            "space_id": self.profile.space_id,
            "topic": self.profile.topic,
            "offset": 0,
            "ack_ts": self._now().isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        }
        await self._make_request("POST", "/k0/sse.ack", json=ack_payload)

    async def _test_driver_handshake(self):
        """Test driver handshake endpoint."""
        handshake_payload: dict[str, Any] = {
            "alias": "traffic-gen",  # Use consistent pre-registered alias
            "transport": "http",
            "endpoint": "http://localhost:9000",
            "capabilities": ["memory.query"],
        }
        await self._make_request("POST", "/k0/driver.handshake", json=handshake_payload)

    async def _run_comprehensive(self):
        """Comprehensive test: exercises ALL implemented endpoints."""
        end_time = self._now() + timedelta(seconds=self.config.duration_seconds)
        interval = 1.0 / self.config.rate

        endpoint_cycle = [
            self._submit_command,  # Command port
            self._submit_query,  # Query port
            self._subscribe_sse,  # SSE subscribe
            self._test_sse_ack,  # SSE ack
            self._test_health_endpoints,  # Observability (health, readiness, metrics)
            self._test_driver_handshake,  # Driver handshake
        ]

        cycle_index = 0

        while self._now() < end_time and self.running:
            request_start = time.time()

            # Execute next endpoint in cycle
            endpoint_func = endpoint_cycle[cycle_index % len(endpoint_cycle)]
            await endpoint_func()
            cycle_index += 1

            # Maintain rate
            elapsed = time.time() - request_start
            sleep_time = max(0, interval - elapsed)
            await asyncio.sleep(sleep_time)

            if self.metrics.total_requests % 100 == 0:
                self._log_progress()
                self._log_endpoint_breakdown()

    async def _make_request(
        self,
        method: str,
        path: str,
        *,
        json: Any | None = None,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        data: Any | None = None,
    ) -> None:
        """Make HTTP request and record metrics."""
        base_url = str(self.config.endpoint).rstrip("/")
        url = urljoin(base_url + "/", path.lstrip("/"))
        start_time = time.time()

        # Track per-endpoint metrics
        endpoint_key = f"{method} {path}"
        self.metrics.endpoint_requests[endpoint_key] = (
            self.metrics.endpoint_requests.get(endpoint_key, 0) + 1
        )

        try:
            client = self.client
            if client is None:
                raise RuntimeError("HTTP client has not been initialised")

            response = await client.request(
                method,
                url,
                json=json,
                params=params,
                headers=headers,
                data=data,
            )
            latency_ms = (time.time() - start_time) * 1000

            self.metrics.total_requests += 1

            if response.status_code < 400:
                self.metrics.successful_requests += 1
                self.metrics.endpoint_successes[endpoint_key] = (
                    self.metrics.endpoint_successes.get(endpoint_key, 0) + 1
                )
            else:
                self.metrics.failed_requests += 1
                self.metrics.endpoint_failures[endpoint_key] = (
                    self.metrics.endpoint_failures.get(endpoint_key, 0) + 1
                )
                details: str | dict[str, Any]
                try:
                    details = response.json()
                except ValueError:
                    details = response.text
                logger.warning(
                    "Request failed: %s %s -> %s | details=%s",
                    method,
                    path,
                    response.status_code,
                    details,
                )

            # Update latency metrics
            self.metrics.total_latency_ms += latency_ms
            self.metrics.min_latency_ms = min(self.metrics.min_latency_ms, latency_ms)
            self.metrics.max_latency_ms = max(self.metrics.max_latency_ms, latency_ms)

        except Exception as e:
            self.metrics.total_requests += 1
            self.metrics.failed_requests += 1
            self.metrics.endpoint_failures[endpoint_key] = (
                self.metrics.endpoint_failures.get(endpoint_key, 0) + 1
            )
            logger.error(f"Request exception: {method} {path} -> {e}")

    # ========================================================================
    # Monitoring & Reporting
    # ========================================================================

    def _log_progress(self):
        """Log current progress."""
        if self.metrics.total_requests == 0:
            return

        avg_latency = self.metrics.total_latency_ms / self.metrics.total_requests
        error_rate = (self.metrics.failed_requests / self.metrics.total_requests) * 100

        logger.info(
            f"Progress: {self.metrics.total_requests} requests, "
            f"{self.metrics.successful_requests} success, "
            f"{self.metrics.failed_requests} failed ({error_rate:.2f}%), "
            f"avg latency {avg_latency:.2f}ms"
        )

    def _log_endpoint_breakdown(self):
        """Log per-endpoint metrics breakdown."""
        if not self.metrics.endpoint_requests:
            return

        logger.info("Endpoint breakdown:")
        for endpoint, count in sorted(
            self.metrics.endpoint_requests.items(), key=lambda x: x[1], reverse=True
        ):
            successes = self.metrics.endpoint_successes.get(endpoint, 0)
            failures = self.metrics.endpoint_failures.get(endpoint, 0)
            success_rate = (successes / count * 100) if count > 0 else 0.0
            logger.info(
                f"  {endpoint}: {count} requests, "
                f"{successes} success ({success_rate:.1f}%), "
                f"{failures} failed"
            )

    def _check_memory_leak(self):
        """Check for memory leaks (placeholder - requires prometheus client)."""
        # TODO: Query Prometheus for memory metrics
        # memory_url = f"{self.config.endpoint}:9090/api/v1/query"
        # query = "k0_kernel_memory_bytes"
        pass

    def _report_metrics(self):
        """Generate final metrics report."""
        if self.metrics.total_requests == 0:
            logger.warning("No requests completed")
            return

        start_time = self.metrics.start_time
        end_time = self.metrics.end_time
        if start_time is None or end_time is None:
            duration = 0.0
        else:
            duration = (end_time - start_time).total_seconds()
        avg_latency = self.metrics.total_latency_ms / self.metrics.total_requests
        error_rate = (self.metrics.failed_requests / self.metrics.total_requests) * 100
        throughput = self.metrics.total_requests / duration if duration > 0 else float("inf")

        # Build endpoint breakdown
        endpoint_breakdown = {}
        for endpoint, count in self.metrics.endpoint_requests.items():
            successes = self.metrics.endpoint_successes.get(endpoint, 0)
            failures = self.metrics.endpoint_failures.get(endpoint, 0)
            success_rate = (successes / count * 100) if count > 0 else 0.0
            endpoint_breakdown[endpoint] = {
                "total_requests": count,
                "successful": successes,
                "failed": failures,
                "success_rate_percent": success_rate,
            }

        report: dict[str, Any] = {
            "scenario": self.config.scenario,
            "duration_seconds": duration,
            "total_requests": self.metrics.total_requests,
            "successful_requests": self.metrics.successful_requests,
            "failed_requests": self.metrics.failed_requests,
            "error_rate_percent": error_rate,
            "throughput_req_per_sec": throughput,
            "latency_ms": {
                "avg": avg_latency,
                "min": self.metrics.min_latency_ms,
                "max": self.metrics.max_latency_ms,
            },
            "endpoint_breakdown": endpoint_breakdown,
            "start_time": start_time.isoformat() if start_time else None,
            "end_time": end_time.isoformat() if end_time else None,
        }

        logger.info(f"Traffic generation complete: {json.dumps(report, indent=2)}")

        # Save report
        self.config.output_dir.mkdir(parents=True, exist_ok=True)
        report_file = (
            self.config.output_dir
            / f"traffic_report_{self.config.scenario}_{int(time.time())}.json"
        )
        with open(report_file, "w") as f:
            json.dump(report, f, indent=2)
        logger.info(f"Report saved to: {report_file}")


# ============================================================================
# CLI
# ============================================================================


def parse_duration(duration_str: str) -> int:
    """Parse duration string (e.g., '4h', '30m', '3600s') to seconds."""
    if duration_str.endswith("h"):
        return int(duration_str[:-1]) * 3600
    elif duration_str.endswith("m"):
        return int(duration_str[:-1]) * 60
    elif duration_str.endswith("s"):
        return int(duration_str[:-1])
    else:
        return int(duration_str)  # Assume seconds


def main():
    parser = argparse.ArgumentParser(description="Traffic Generator for Staging Burn-in")
    parser.add_argument(
        "--endpoint",
        required=True,
        help="K0 endpoint URL (e.g., http://staging.k0.local)",
    )
    parser.add_argument("--rate", type=int, required=True, help="Requests per second")
    parser.add_argument("--duration", required=True, help="Duration (e.g., 4h, 30m, 3600s)")
    parser.add_argument(
        "--scenario",
        choices=["baseline", "burst", "mixed", "sustained", "comprehensive"],
        required=True,
        help="Traffic scenario",
    )
    parser.add_argument(
        "--command-ratio",
        type=float,
        default=0.6,
        help="Command ratio for mixed scenario",
    )
    parser.add_argument(
        "--query-ratio", type=float, default=0.3, help="Query ratio for mixed scenario"
    )
    parser.add_argument("--sse-ratio", type=float, default=0.1, help="SSE ratio for mixed scenario")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("artifacts/traffic"),
        help="Output directory",
    )
    parser.add_argument(
        "--clear-outbox",
        action="store_true",
        help="Clear outbox and DLQ backlog before starting traffic",
    )
    parser.add_argument(
        "--db-path",
        type=str,
        default="/data/k0_runtime.sqlite3",
        help="Path to SQLite database (default: /data/k0_runtime.sqlite3)",
    )

    args = parser.parse_args()

    # Clear outbox if requested
    if args.clear_outbox:
        try:
            logger.info("")
            logger.info("⏳ Clearing outbox backlog before starting traffic...")
            result = clear_outbox_backlog(args.db_path)
            logger.info(f"✅ Outbox cleared: {result['outbox_cleared']} entries")
            logger.info(f"✅ DLQ cleared: {result['dlq_cleared']} entries")
            logger.info("")
            logger.info("⏳ Waiting 5 seconds for system to stabilize...")
            time.sleep(5)
            logger.info("")
        except Exception as e:
            logger.error(f"❌ Failed to clear outbox: {e}")
            logger.error("Proceeding with traffic generation anyway...")
            logger.error("")

    config = TrafficConfig(
        endpoint=args.endpoint,
        rate=args.rate,
        duration_seconds=parse_duration(args.duration),
        scenario=args.scenario,
        command_ratio=args.command_ratio,
        query_ratio=args.query_ratio,
        sse_ratio=args.sse_ratio,
        output_dir=args.output_dir,
    )

    generator = TrafficGenerator(config)

    try:
        asyncio.run(generator.start())
    except KeyboardInterrupt:
        logger.info("Traffic generation interrupted by user")
        generator.running = False


if __name__ == "__main__":
    main()
