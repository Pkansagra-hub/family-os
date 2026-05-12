"""Journey 1 — First-time user onboarding.

Story: A new user sets up FamilyOS for the first time. A K1 process
spawns, a device is provisioned in K0's ``st_devices`` ledger, the very
first ``memory.write`` envelope commits, and an immediate recall query
is admitted by policy. This is the *minimum viable round-trip* every
real install must satisfy.

Asserts (in order):
1. K1 process is alive after spawn.
2. ``healthz`` and ``readyz`` are green on K0.
3. The first ``memory.write`` returns ``HTTP 200`` with a ``receipt_id``,
   ``commit_ts``, and a non-zero ``wal_pos`` offset.
4. ``st_receipts`` immediately reflects the write (tenant/space/device
   match what we provisioned).
5. A follow-up ``query.recall`` against the same ``(tenant, space)`` is
   admitted (``trace.policy.decision == "ADMIT"``) and returns a
   well-formed bundle (no 4xx/5xx).
"""

from __future__ import annotations

import uuid

import pytest

from tests.integration.harness.family_layout import (
    DeviceSpec,
    FamilyLayout,
    PersonSpec,
)
from tests.integration.harness.k0_observer import (
    count_receipts,
    latest_receipt_for_device,
)
from tests.integration.harness.k0_query_client import query_recall
from tests.integration.harness.live_system import LiveSystem


def _hex(n: int = 8) -> str:
    return uuid.uuid4().hex[:n]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_journey_first_time_user_onboarding() -> None:
    fam = FamilyLayout(
        family_id=f"fam-onboard-{_hex()}",
        people=(
            PersonSpec(
                person_id=f"user-{_hex()}",
                role="single",
                devices=(DeviceSpec(device_id=f"dev-{_hex()}", label="phone"),),
            ),
        ),
    )
    dev_id = fam.people[0].devices[0].device_id
    baseline = count_receipts(tenant_id=fam.family_id, space_id=fam.family_id)

    async with LiveSystem(family=fam) as live:
        # 1) K1 alive
        assert len(live.k1s) == 1
        k1 = live.k1s[0]
        assert k1.is_alive, "K1 process did not stay alive after spawn"

        # 2) K0 health
        assert live.k0 is not None
        assert live.k0.healthz()["status"] == "ok"
        assert live.k0.readyz() == 200

        # 3) First write commits
        result = await k1.publish_memory_write_v1_native(
            text="My first memory in FamilyOS!",
            topics=["onboarding", "integration"],
        )
        assert result["http_status"] == 200, result
        receipt_body = result["body"]
        assert "receipt_id" in receipt_body, receipt_body
        assert "commit_ts" in receipt_body, receipt_body
        offsets = receipt_body.get("offsets") or {}
        assert any(int(v) > 0 for v in offsets.values()), offsets

        # 4) Receipt immediately visible in ledger
        receipt = latest_receipt_for_device(dev_id)
        assert receipt is not None, dev_id
        assert receipt["tenant_id"] == fam.family_id
        assert receipt["space_id"] == fam.family_id
        assert receipt["device_id"] == dev_id

        # 5) Recall is admitted
        recall = await query_recall(
            k0_base_url=k1.k0_base_url,
            tenant_id=fam.family_id,
            space_id=fam.family_id,
            selectors=[{"type": "semantic", "topic": "onboarding", "limit": 5}],
        )
        assert recall["http_status"] == 200, recall
        assert recall["body"]["trace"]["policy"]["decision"] == "ADMIT"
        assert "bundle" in recall["body"]

    # Receipt count grew by exactly 1.
    after = count_receipts(tenant_id=fam.family_id, space_id=fam.family_id)
    assert after - baseline == 1, (baseline, after)
