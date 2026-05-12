"""Journey 5 — Write + observe metrics, then recall is admitted.

Story: A user writes a memory, then the bridge forwards a metrics
snapshot via ``POST /k0/obs.emit``, and finally a recall is issued
against the same space. All three surfaces respond cleanly:

* ``command.submit`` -> 200 with receipt
* ``obs.emit``       -> 204 No Content
* ``query.recall``   -> 200 with ``policy.decision == "ADMIT"``

This is the closest journey we can ship to a "user → write → observe →
read-back" loop without depending on the SSE or admin-pipeline routes
(deferred). It pins the *three* user-facing K0 verbs that the K1 bridge
actually exercises in production today.
"""

from __future__ import annotations

import uuid

import pytest

from tests.integration.harness.family_layout import (
    DeviceSpec,
    FamilyLayout,
    PersonSpec,
)
from tests.integration.harness.k0_observer import latest_receipt_for_device
from tests.integration.harness.k0_query_client import (
    obs_emit_metrics,
    query_recall,
)
from tests.integration.harness.live_system import LiveSystem

_METRICS_SNAPSHOT = (
    "# HELP k1_journey_write_total writes from journey 5\n"
    "# TYPE k1_journey_write_total counter\n"
    "k1_journey_write_total 1\n"
)


def _hex(n: int = 8) -> str:
    return uuid.uuid4().hex[:n]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_journey_write_observe_recall_round_trip() -> None:
    fam = FamilyLayout(
        family_id=f"fam-obs-{_hex()}",
        people=(
            PersonSpec(
                person_id=f"user-{_hex()}",
                role="single",
                devices=(DeviceSpec(device_id=f"dev-{_hex()}", label="phone"),),
            ),
        ),
    )
    dev_id = fam.people[0].devices[0].device_id

    async with LiveSystem(family=fam) as live:
        k1 = live.k1s[0]
        k0_base = k1.k0_base_url

        # 1) Write
        write = await k1.publish_memory_write_v1_native(
            text="Booked the dentist for next Tuesday at 3pm.",
            topics=["health", "calendar"],
        )
        assert write["http_status"] == 200, write
        assert "receipt_id" in write["body"], write["body"]

        receipt = latest_receipt_for_device(dev_id)
        assert receipt is not None
        assert receipt["space_id"] == fam.family_id

        # 2) Observe (metrics snapshot)
        obs = await obs_emit_metrics(
            k0_base_url=k0_base,
            snapshot=_METRICS_SNAPSHOT,
            source="journey5_test",
        )
        assert obs["http_status"] == 204, obs
        assert obs["body"] == {}

        # 3) Recall
        recall = await query_recall(
            k0_base_url=k0_base,
            tenant_id=fam.family_id,
            space_id=fam.family_id,
            selectors=[{"type": "semantic", "topic": "health", "limit": 5}],
        )
        assert recall["http_status"] == 200, recall
        assert recall["body"]["trace"]["policy"]["decision"] == "ADMIT"
        assert "bundle" in recall["body"]
        assert "selectors" in recall["body"]["bundle"]
