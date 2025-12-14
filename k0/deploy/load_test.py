"""
K0 Kernel Load Testing Script
Generates traffic on the command port to measure throughput and latency.

Usage:
    python k0/load_test.py --duration 60 --concurrency 10 --target http://localhost:8080
"""

import argparse
import asyncio
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiohttp
from nacl.signing import SigningKey

# Add project root to Python path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from k0.security import canonical_json, hash_payload
from k0.security.crypto import encode_base64url

# Configuration
DB_PATH = project_root / "k0" / "deploy" / "data" / "k0_kernel.db"
TENANT_ID = "tenant-test"
SPACE_ID = "space-home"
DEVICE_ID = "device-test-1"
SCHEMA_URI = "schema://memory.delta"
SCHEMA_VERSION = "1.0"


@dataclass
class LoadTestStats:
    """Track load test statistics."""

    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    total_latency: float = 0.0
    min_latency: float = float("inf")
    max_latency: float = 0.0
    start_time: float = 0.0
    end_time: float = 0.0

    @property
    def duration(self) -> float:
        """Total test duration in seconds."""
        return self.end_time - self.start_time

    @property
    def avg_latency(self) -> float:
        """Average latency in milliseconds."""
        if self.successful_requests == 0:
            return 0.0
        return (self.total_latency / self.successful_requests) * 1000

    @property
    def throughput(self) -> float:
        """Requests per second."""
        if self.duration == 0:
            return 0.0
        return self.total_requests / self.duration

    @property
    def success_rate(self) -> float:
        """Success rate as percentage."""
        if self.total_requests == 0:
            return 0.0
        return (self.successful_requests / self.total_requests) * 100


def build_envelope(
    signing_key: SigningKey, actor_id: str, device_id: str
) -> tuple[dict[str, Any], str]:
    """Build and sign an envelope for submission.

    Returns:
        Tuple of (envelope_dict, signature_b64)
    """
    # Build body
    body = {
        "operation": "UPSERT",
        "payload": {
            "value": int(time.time() * 1000) % 10000,  # Random-ish value
            "text": f"Load test payload from {actor_id}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    }

    # Canonicalize body
    body_json = canonical_json(body)
    body_bytes = body_json.encode("utf-8")
    payload_hash = hash_payload(body_bytes)

    # Build envelope
    trace_id = str(uuid.uuid4())
    timestamp_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    envelope = {
        "cognitive_trace_id": trace_id,
        "tenant_id": TENANT_ID,
        "space_id": SPACE_ID,
        "topic": "memory.delta",
        "schema_uri": SCHEMA_URI,
        "schema_version": SCHEMA_VERSION,
        "actor": actor_id,
        "device_id": device_id,
        "band": "GREEN",
        "policy_version": "2025-09-28",
        "ts": timestamp_iso,
        "payload_sha256": payload_hash,
        "sig_alg": "Ed25519SHA512",
        "sig_kid": f"{device_id}#1",
        "body": body,
        "policy": {"abac": {"roles": ["guest"]}},
    }

    # Compute envelope_sha256
    from k0.security import canonical_envelope, compute_envelope_sha256

    envelope_sha256 = compute_envelope_sha256(envelope)
    envelope["envelope_sha256"] = envelope_sha256

    # Sign envelope
    message = canonical_envelope(envelope)
    signature = encode_base64url(signing_key.sign(message).signature)

    return envelope, signature


async def submit_envelope(
    session: aiohttp.ClientSession,
    envelope: dict[str, Any],
    signature: str,
    base_url: str,
) -> tuple[bool, float, str]:
    """Submit an envelope and measure latency.

    Returns:
        Tuple of (success, latency_seconds, response_text)
    """
    request_payload = dict(envelope)
    request_payload["sig"] = signature

    url = f"{base_url}/k0/command.submit"
    start_time = time.perf_counter()

    try:
        async with session.post(
            url,
            json=request_payload,
            timeout=aiohttp.ClientTimeout(total=10),
        ) as response:
            latency = time.perf_counter() - start_time
            text = await response.text()

            if response.status == 200:
                return True, latency, text
            else:
                return False, latency, f"HTTP {response.status}: {text}"
    except asyncio.TimeoutError:
        latency = time.perf_counter() - start_time
        return False, latency, "Request timeout"
    except Exception as e:
        latency = time.perf_counter() - start_time
        return False, latency, f"Error: {str(e)}"


async def load_test_worker(
    worker_id: int,
    session: aiohttp.ClientSession,
    signing_key: SigningKey,
    base_url: str,
    duration: int,
    stats: LoadTestStats,
) -> None:
    """Worker coroutine that submits envelopes continuously.

    Args:
        worker_id: Unique worker identifier
        session: aiohttp client session
        signing_key: Signing key for envelope creation
        base_url: Base URL of kernel
        duration: Total test duration in seconds
        stats: Shared statistics object
    """
    device_id = f"load-test-device-{worker_id}"
    actor_id = f"load-test-actor-{worker_id}"
    start_time = time.time()

    while time.time() - start_time < duration:
        # Build and sign envelope
        envelope, signature = build_envelope(signing_key, actor_id, device_id)

        # Submit envelope
        success, latency, response = await submit_envelope(session, envelope, signature, base_url)

        # Update stats
        stats.total_requests += 1
        stats.total_latency += latency

        if latency < stats.min_latency:
            stats.min_latency = latency

        if latency > stats.max_latency:
            stats.max_latency = latency

        if success:
            stats.successful_requests += 1
        else:
            stats.failed_requests += 1
            if stats.total_requests <= 5:  # Print first few errors
                print(f"  [Worker {worker_id}] Error: {response}")


async def run_load_test(
    base_url: str, duration: int, concurrency: int, signing_key: SigningKey
) -> LoadTestStats:
    """Run the load test with specified parameters.

    Args:
        base_url: Base URL of kernel (e.g., http://localhost:8080)
        duration: Test duration in seconds
        concurrency: Number of concurrent workers
        signing_key: Signing key for envelopes

    Returns:
        LoadTestStats with results
    """
    stats = LoadTestStats()
    stats.start_time = time.time()

    print(f"\n{'=' * 70}")
    print("K0 Kernel Load Test")
    print(f"{'=' * 70}")
    print(f"Target: {base_url}")
    print(f"Duration: {duration}s")
    print(f"Concurrency: {concurrency} workers")
    print(f"Start time: {datetime.now().isoformat()}")
    print(f"{'=' * 70}\n")

    # Create aiohttp session
    async with aiohttp.ClientSession() as session:
        # Create worker tasks
        workers = [
            load_test_worker(i, session, signing_key, base_url, duration, stats)
            for i in range(concurrency)
        ]

        # Run workers concurrently
        await asyncio.gather(*workers)

    stats.end_time = time.time()

    return stats


def print_results(stats: LoadTestStats) -> None:
    """Print load test results.

    Args:
        stats: LoadTestStats with results
    """
    print(f"\n{'=' * 70}")
    print("Load Test Results")
    print(f"{'=' * 70}")
    print(f"Test Duration: {stats.duration:.2f}s")
    print("\nRequest Statistics:")
    print(f"  Total Requests: {stats.total_requests}")
    print(f"  Successful: {stats.successful_requests}")
    print(f"  Failed: {stats.failed_requests}")
    print(f"  Success Rate: {stats.success_rate:.1f}%")
    print("\nThroughput:")
    print(f"  Requests/sec: {stats.throughput:.2f}")
    print(f"  Requests/min: {stats.throughput * 60:.0f}")
    print("\nLatency (milliseconds):")
    print(f"  Average: {stats.avg_latency:.2f}ms")
    print(f"  Min: {stats.min_latency * 1000:.2f}ms")
    print(f"  Max: {stats.max_latency * 1000:.2f}ms")
    print(f"\nEnd time: {datetime.now().isoformat()}")
    print(f"{'=' * 70}\n")


def _get_or_create_persistent_key() -> SigningKey:
    """Load persistent test signing key from file."""
    import base64

    key_file = project_root / "k0" / "deploy" / "data" / "test_device_key.b64"

    if key_file.exists():
        # Load existing key
        key_b64 = key_file.read_text().strip()
        padding = "=" * (-len(key_b64) % 4)
        key_bytes = base64.urlsafe_b64decode(f"{key_b64}{padding}".encode("ascii"))
        signing_key = SigningKey(key_bytes)
        print("✓ Loaded persistent Ed25519 signing key")
        return signing_key
    else:
        # Generate new key and save it
        signing_key = SigningKey.generate()
        key_b64 = encode_base64url(bytes(signing_key))
        key_file.parent.mkdir(parents=True, exist_ok=True)
        key_file.write_text(key_b64)
        print("✓ Generated new persistent Ed25519 signing key")
        return signing_key


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="K0 Kernel Load Testing Script",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Test with default settings (30s, 5 concurrent workers)
  python k0/load_test.py

  # Test for 60 seconds with 20 concurrent workers
  python k0/load_test.py --duration 60 --concurrency 20

  # Test against custom endpoint
  python k0/load_test.py --target http://k0-kernel.example.com:8080
        """,
    )

    parser.add_argument(
        "--duration",
        type=int,
        default=30,
        help="Test duration in seconds (default: 30)",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=5,
        help="Number of concurrent workers (default: 5)",
    )
    parser.add_argument(
        "--target",
        type=str,
        default="http://localhost:8080",
        help="Target kernel base URL (default: http://localhost:8080)",
    )

    args = parser.parse_args()

    # Validate arguments
    if args.duration <= 0:
        print("❌ Duration must be positive")
        sys.exit(1)

    if args.concurrency <= 0:
        print("❌ Concurrency must be positive")
        sys.exit(1)

    # Load signing key
    signing_key = _get_or_create_persistent_key()

    # Run load test
    try:
        stats = asyncio.run(
            run_load_test(args.target, args.duration, args.concurrency, signing_key)
        )
        print_results(stats)
    except KeyboardInterrupt:
        print("\n\n⚠️  Load test interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Load test failed: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
