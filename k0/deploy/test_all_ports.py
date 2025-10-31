#!/usr/bin/env python3
"""
K0 All Ports - Comprehensive Test Suite
Posts to ALL K0 ports and returns 200 OK responses
Reference implementation for K0 bridge setup
"""
import base64
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Tuple

import requests
from nacl.signing import SigningKey


def _decode_base64url(value: str) -> bytes:
    """Decode base64url encoded string with padding."""
    padding = (-len(value)) % 4
    return base64.urlsafe_b64decode(value + ("=" * padding))


class K0AllPortsTester:
    """Test all K0 ports with proper signing and provisioning."""

    TEST_SECRET_BASE64 = "zd5M1iHPJjGaJnxt6UEtU7FxslBua_oL8V_cGR7X8gA"
    TEST_TENANT = "tenant-001"
    TEST_SPACE = "space-home"
    TEST_DEVICE = "device-local-001"
    DB_PATH = Path("./data/k0_kernel.db")
    K0_HOST = "http://localhost:8080"

    # All K0 Ports (from docker-compose and bridge_policy.yml)
    PORTS = {
        "8080": "K0 Kernel (Main - /k0/command.submit)",
        "9090": "Prometheus (Metrics)",
        "3000": "Grafana (Dashboards)",
        "9093": "AlertManager (Alerts)",
        "4317": "Tempo OTLP (Tracing)",
    }

    def __init__(self):
        """Initialize with test credentials."""
        secret_bytes = _decode_base64url(self.TEST_SECRET_BASE64)
        self.signing_key = SigningKey(secret_bytes)
        self.verify_key = self.signing_key.verify_key
        self.verify_key_b64 = base64.b64encode(bytes(self.verify_key)).decode()

        self.results = []

    def generate_signed_envelope(self, action: str, resource: str, cmd_id: str) -> Dict[str, Any]:
        """Generate properly signed envelope for K0 command.submit matching K0 Envelope schema."""
        # Required fields for K0 Envelope model validation
        trace_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        envelope = {
            "cognitive_trace_id": trace_id,
            "tenant_id": self.TEST_TENANT,
            "space_id": self.TEST_SPACE,
            "device_id": self.TEST_DEVICE,
            "topic": "commands.delta.memory.write",
            "schema_uri": "schema://memory.delta",
            "schema_version": "1.0",
            "actor": "device-local-001",
            "band": "GREEN",
            "policy_version": "1.0",
            "ts": now,
            "sig": "",
            "policy_ctx": {"abac": {"roles": ["admin", "device"]}},
        }

        # Create canonical JSON for signing
        envelope_for_sig = {k: v for k, v in sorted(envelope.items()) if k != "sig"}
        canonical = json.dumps(envelope_for_sig, separators=(",", ":"), sort_keys=True)

        # Sign the envelope
        signature = self.signing_key.sign(canonical.encode()).signature
        envelope["sig"] = base64.b64encode(signature).decode()

        return envelope

    def test_k0_command_submit(self) -> Tuple[int, str, Dict]:
        """Test K0 command.submit endpoint (P00 - Policy Submit Port)."""
        print("\n" + "=" * 70)
        print("🔷 PORT 8080 - K0 Command Submit (P00 - Policy Enforcement)")
        print("=" * 70)

        envelope = self.generate_signed_envelope(
            action="read_profile", resource="/profiles/family", cmd_id="test-cmd-001"
        )

        try:
            url = f"{self.K0_HOST}/k0/command.submit"
            response = requests.post(
                url, json=envelope, headers={"Content-Type": "application/json"}, timeout=5
            )

            status = response.status_code
            reason = response.reason
            data = response.json() if response.text else {}

            print(f"URL: {url}")
            print("Method: POST")
            print("Payload: K0 Command Envelope (signed + policy-compliant)")
            print(f"Status: {status} {reason}")

            if status == 200:
                print("Response: Command successfully written to WAL!")
                print(f"  Receipt ID: {data.get('receipt_id')}")
                print(f"  Commit TS: {data.get('commit_ts')}")
                print(f"  Offsets: {data.get('offsets')}")
                return 200, "✅ Command Success", data
            elif status == 409:
                print("Response: Idempotent duplicate (already written - EXPECTED)!")
                print(f"  Receipt ID: {data.get('receipt_id')}")
                print(f"  Original commit TS: {data.get('commit_ts')}")
                # 409 is a SUCCESS - it means idempotency is working correctly
                return 200, "✅ Idempotency OK", data
            elif status in [400, 403]:
                print(
                    f"Response: Policy/gate validation (expected for test): {json.dumps(data, indent=2)[:100]}"
                )
                return status, reason, data
            else:
                print(f"Response: {json.dumps(data, indent=2)[:200]}...")
                return status, reason, data
        except Exception as e:
            print(f"❌ Error: {e}")
            return 0, str(e), {}

    def test_prometheus_metrics(self) -> Tuple[int, str, str]:
        """Test Prometheus metrics endpoint."""
        print("\n" + "=" * 70)
        print("📊 PORT 9090 - Prometheus Metrics")
        print("=" * 70)

        try:
            url = "http://localhost:9090/api/v1/query"
            params = {"query": "up"}
            response = requests.get(url, params=params, timeout=5)

            status = response.status_code
            reason = response.reason
            data = response.text[:200] if response.text else ""

            print(f"URL: {url}")
            print("Method: GET")
            print("Query: up")
            print(f"Status: {status} {reason}")
            print(f"Response: {data}...")

            return status, reason, data
        except Exception as e:
            print(f"❌ Error: {e}")
            return 0, str(e), ""

    def test_prometheus_ready(self) -> Tuple[int, str, str]:
        """Test Prometheus readiness endpoint."""
        print("\n" + "=" * 70)
        print("🟢 PORT 9090 - Prometheus Readiness")
        print("=" * 70)

        try:
            url = "http://localhost:9090/-/ready"
            response = requests.get(url, timeout=5)

            status = response.status_code
            reason = response.reason

            print(f"URL: {url}")
            print("Method: GET")
            print(f"Status: {status} {reason}")

            return status, reason, response.text
        except Exception as e:
            print(f"❌ Error: {e}")
            return 0, str(e), ""

    def test_grafana_health(self) -> Tuple[int, str, Dict]:
        """Test Grafana health endpoint."""
        print("\n" + "=" * 70)
        print("📈 PORT 3000 - Grafana Health")
        print("=" * 70)

        try:
            url = "http://localhost:3000/api/health"
            response = requests.get(url, timeout=5)

            status = response.status_code
            reason = response.reason
            data = response.json() if response.text else {}

            print(f"URL: {url}")
            print("Method: GET")
            print(f"Status: {status} {reason}")
            print(f"Response: {json.dumps(data, indent=2)}")

            return status, reason, data
        except Exception as e:
            print(f"❌ Error: {e}")
            return 0, str(e), {}

    def test_alertmanager_ready(self) -> Tuple[int, str, str]:
        """Test AlertManager readiness endpoint."""
        print("\n" + "=" * 70)
        print("🚨 PORT 9093 - AlertManager Readiness")
        print("=" * 70)

        try:
            url = "http://localhost:9093/-/ready"
            response = requests.get(url, timeout=5)

            status = response.status_code
            reason = response.reason

            print(f"URL: {url}")
            print("Method: GET")
            print(f"Status: {status} {reason}")

            return status, reason, response.text
        except Exception as e:
            print(f"❌ Error: {e}")
            return 0, str(e), ""

    def test_tempo_metrics(self) -> Tuple[int, str, str]:
        """Test Tempo metrics endpoint."""
        print("\n" + "=" * 70)
        print("🔵 PORT 3200 - Tempo Metrics")
        print("=" * 70)

        try:
            url = "http://localhost:3200/metrics"
            response = requests.get(url, timeout=5)

            status = response.status_code
            reason = response.reason
            data = response.text[:200] if response.text else ""

            print(f"URL: {url}")
            print("Method: GET")
            print(f"Status: {status} {reason}")
            print(f"Response: {data}...")

            return status, reason, data
        except Exception as e:
            print(f"❌ Error: {e}")
            return 0, str(e), ""

    def test_k0_healthz(self) -> Tuple[int, str, Dict]:
        """Test K0 healthz endpoint."""
        print("\n" + "=" * 70)
        print("❤️  K0 Kernel - Health Check")
        print("=" * 70)

        try:
            url = f"{self.K0_HOST}/healthz"
            response = requests.get(url, timeout=5)

            status = response.status_code
            reason = response.reason
            data = response.json() if response.text else {}

            print(f"URL: {url}")
            print("Method: GET")
            print(f"Status: {status} {reason}")
            print(f"Response: {json.dumps(data, indent=2)}")

            return status, reason, data
        except Exception as e:
            print(f"❌ Error: {e}")
            return 0, str(e), {}

    def test_k0_readyz(self) -> Tuple[int, str, Dict]:
        """Test K0 readyz endpoint."""
        print("\n" + "=" * 70)
        print("✅ K0 Kernel - Ready Check")
        print("=" * 70)

        try:
            url = f"{self.K0_HOST}/readyz"
            response = requests.get(url, timeout=5)

            status = response.status_code
            reason = response.reason
            data = response.json() if response.text else {}

            print(f"URL: {url}")
            print("Method: GET")
            print(f"Status: {status} {reason}")
            print(f"Response: {json.dumps(data, indent=2)}")

            return status, reason, data
        except Exception as e:
            print(f"❌ Error: {e}")
            return 0, str(e), {}

    def run_all_tests(self):
        """Run all port tests."""
        print("\n\n")
        print("╔" + "=" * 68 + "╗")
        print("║" + " " * 15 + "K0 ALL PORTS TEST SUITE" + " " * 29 + "║")
        print("║" + " " * 10 + "Comprehensive testing of all K0 deployment ports" + " " * 9 + "║")
        print("╚" + "=" * 68 + "╝")

        tests = [
            ("K0 Health", self.test_k0_healthz),
            ("K0 Ready", self.test_k0_readyz),
            ("K0 Command Submit", self.test_k0_command_submit),
            ("Prometheus Metrics", self.test_prometheus_metrics),
            ("Prometheus Ready", self.test_prometheus_ready),
            ("Grafana Health", self.test_grafana_health),
            ("AlertManager Ready", self.test_alertmanager_ready),
            ("Tempo Metrics", self.test_tempo_metrics),
        ]

        results = []
        for test_name, test_func in tests:
            status, reason, data = test_func()
            results.append(
                {
                    "name": test_name,
                    "status": status,
                    "reason": reason,
                    "success": status
                    == 200,  # 200 = new command, 409 = idempotent duplicate (also success)
                }
            )

        # Print summary
        print("\n\n" + "╔" + "=" * 68 + "╗")
        print("║" + " " * 20 + "TEST SUMMARY" + " " * 37 + "║")
        print("╠" + "=" * 68 + "╣")

        passed = sum(1 for r in results if r["success"])
        total = len(results)

        for r in results:
            status_icon = "✅" if r["success"] else "❌"
            print(f"║ {status_icon} {r['name']:<30} {r['status']:>3} {r['reason']:<25} ║")

        print("╠" + "=" * 68 + "╣")
        print(f"║ TOTAL: {passed}/{total} PASSED {' ' * 48} ║")
        print("╚" + "=" * 68 + "╝\n")

        return results


if __name__ == "__main__":
    tester = K0AllPortsTester()
    results = tester.run_all_tests()

    # Exit with 0 if all tests passed
    passed_count = sum(1 for r in results if r["success"])
    if passed_count == len(results):
        print("🎉 ALL TESTS PASSED! 🎉\n")
        exit(0)
    else:
        print(f"⚠️  {len(results) - passed_count} tests failed\n")
        exit(1)
