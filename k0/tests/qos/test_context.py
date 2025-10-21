from __future__ import annotations

from ward import raises, test  # type: ignore[attr-defined]

from k0.qos import QoSBudgetError, QoSContext, Scheduler


@test("qos context tightening clamps budgets but never expands them")
def _() -> None:
    context = QoSContext(scheduler=Scheduler(), fanout_budget=5, top_k_budget=8)
    context.tighten(fanout=3)
    assert context.fanout_budget == 3
    context.tighten(fanout=6)
    assert context.fanout_budget == 3
    context.tighten(top_k=4)
    assert context.top_k_budget == 4
    context.tighten(top_k=10)
    assert context.top_k_budget == 4
    with raises(ValueError):
        context.tighten(fanout=-1)


@test("qos context enforces budget consumption and raises on exhaustion")
def _() -> None:
    context = QoSContext(scheduler=Scheduler(), fanout_budget=2, top_k_budget=3)
    context.consume_fanout()
    assert context.fanout_budget == 1
    context.consume_top_k(2)
    assert context.top_k_budget == 1
    with raises(QoSBudgetError):
        context.consume_fanout(5)
    with raises(ValueError):
        context.consume_top_k(-1)


@test("qos context delegates acquisition to scheduler and returns a token")
def _() -> None:
    scheduler = Scheduler()
    context = QoSContext(scheduler=scheduler, fanout_budget=1, top_k_budget=1)
    token = context.acquire(band="GREEN", port="command", cost=2)
    assert scheduler.active_tokens("command") == 2
    token.release()
    assert scheduler.active_tokens("command") == 0
