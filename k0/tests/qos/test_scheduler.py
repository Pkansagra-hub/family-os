from __future__ import annotations

from ward import raises, test  # type: ignore[attr-defined]

from k0.qos import Scheduler, SchedulerCapacityError, SchedulerProfile


@test("scheduler enforces per-port capacity and returns tokens")
def _() -> None:
    scheduler = Scheduler(
        SchedulerProfile(
            name="test",
            description="test profile",
            port_limits={"command": 2},
            default_port_limit=2,
        )
    )
    token_a = scheduler.acquire(band="GREEN", port="command", cost=1)
    token_b = scheduler.acquire(band="GREEN", port="command", cost=1)
    assert scheduler.active_tokens("command") == 2
    with raises(SchedulerCapacityError):
        scheduler.acquire(band="GREEN", port="command", cost=1)
    token_a.release()
    assert scheduler.active_tokens("command") == 1
    token_b.release()
    assert scheduler.active_tokens("command") == 0


@test("scheduler tighten applies new limits to active tokens")
def _() -> None:
    scheduler = Scheduler(
        SchedulerProfile(
            name="test",
            description="test profile",
            port_limits={"command": 4},
            default_port_limit=4,
        )
    )
    tokens = [scheduler.acquire(band="GREEN", port="command", cost=1) for _ in range(4)]
    scheduler.tighten(
        SchedulerProfile(
            name="hardened",
            description="tightened",
            port_limits={"command": 2},
            default_port_limit=2,
        )
    )
    assert scheduler.profile.port_limits["command"] == 2
    assert scheduler.active_tokens("command") == 2
    with raises(SchedulerCapacityError):
        scheduler.acquire(band="GREEN", port="command", cost=1)
    for handle in tokens:
        handle.release()
    assert scheduler.active_tokens("command") == 0
