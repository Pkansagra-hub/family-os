"""Unit tests for :mod:`k0.sse.replay_buffer` (MS-3d Epic 3d.3)."""

from __future__ import annotations

import threading
import time

import pytest

from k0.sse.replay_buffer import ReplayGapError, SSEReplayBuffer


@pytest.fixture
def buf() -> SSEReplayBuffer:
    b = SSEReplayBuffer.from_path(":memory:", retention_s=3600)
    yield b
    b.close()


def test_append_returns_seq_and_was_new_true(buf: SSEReplayBuffer) -> None:
    seq, was_new = buf.append(
        topic="curiosity.intent.v1",
        envelope_id="01HZ-A",
        payload={"envelope_id": "01HZ-A", "n": 1},
    )
    assert seq >= 1
    assert was_new is True


def test_append_idempotent_on_duplicate_envelope_id(buf: SSEReplayBuffer) -> None:
    seq1, new1 = buf.append(
        topic="t",
        envelope_id="01HZ-DUP",
        payload={"envelope_id": "01HZ-DUP", "v": 1},
    )
    seq2, new2 = buf.append(
        topic="t",
        envelope_id="01HZ-DUP",
        payload={"envelope_id": "01HZ-DUP", "v": "ignored"},
    )
    assert new1 is True
    assert new2 is False
    assert seq1 == seq2
    assert buf.depth("t") == 1


def test_replay_after_none_yields_empty(buf: SSEReplayBuffer) -> None:
    buf.append(topic="t", envelope_id="A", payload={"envelope_id": "A"})
    assert list(buf.replay_after(topic="t", cursor=None)) == []


def test_replay_after_empty_string_yields_all(buf: SSEReplayBuffer) -> None:
    for i, env in enumerate(["A", "B", "C"]):
        buf.append(topic="t", envelope_id=env, payload={"envelope_id": env, "i": i})
    rows = list(buf.replay_after(topic="t", cursor=""))
    assert [r.envelope_id for r in rows] == ["A", "B", "C"]


def test_replay_after_cursor_yields_strictly_newer(buf: SSEReplayBuffer) -> None:
    for env in ["A", "B", "C", "D"]:
        buf.append(topic="t", envelope_id=env, payload={"envelope_id": env})
    rows = list(buf.replay_after(topic="t", cursor="B"))
    assert [r.envelope_id for r in rows] == ["C", "D"]


def test_replay_after_cursor_topic_isolation(buf: SSEReplayBuffer) -> None:
    buf.append(topic="t1", envelope_id="A", payload={"envelope_id": "A"})
    buf.append(topic="t2", envelope_id="B", payload={"envelope_id": "B"})
    rows = list(buf.replay_after(topic="t1", cursor=""))
    assert [r.envelope_id for r in rows] == ["A"]


def test_replay_after_unknown_cursor_raises_replay_gap(buf: SSEReplayBuffer) -> None:
    buf.append(topic="t", envelope_id="REAL", payload={"envelope_id": "REAL"})
    with pytest.raises(ReplayGapError) as exc:
        list(buf.replay_after(topic="t", cursor="GHOST"))
    assert exc.value.topic == "t"
    assert exc.value.cursor == "GHOST"


def test_evict_expired_removes_old_rows(buf: SSEReplayBuffer) -> None:
    now = time.time()
    buf.append(
        topic="t",
        envelope_id="OLD",
        payload={"envelope_id": "OLD"},
        created_at=now - 7200,  # 2h old, retention is 1h
    )
    buf.append(
        topic="t",
        envelope_id="FRESH",
        payload={"envelope_id": "FRESH"},
        created_at=now - 60,
    )
    evicted = buf.evict_expired(now=now)
    assert evicted == 1
    rows = list(buf.replay_after(topic="t", cursor=""))
    assert [r.envelope_id for r in rows] == ["FRESH"]


def test_latest_envelope_id_tracks_max_seq(buf: SSEReplayBuffer) -> None:
    assert buf.latest_envelope_id("t") is None
    for env in ["A", "B", "C"]:
        buf.append(topic="t", envelope_id=env, payload={"envelope_id": env})
    assert buf.latest_envelope_id("t") == "C"


def test_concurrent_append_thread_safe() -> None:
    """N threads append to the same buffer; no row loss, no torn writes."""
    buf = SSEReplayBuffer.from_path(":memory:")
    n_threads = 8
    per_thread = 50
    errors: list[BaseException] = []

    def worker(tid: int) -> None:
        try:
            for i in range(per_thread):
                buf.append(
                    topic="t",
                    envelope_id=f"T{tid}-{i:03d}",
                    payload={"envelope_id": f"T{tid}-{i:03d}", "tid": tid},
                )
        except BaseException as exc:  # pragma: no cover - debug aid
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(t,)) for t in range(n_threads)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    assert not errors
    assert buf.depth("t") == n_threads * per_thread
    rows = list(buf.replay_after(topic="t", cursor=""))
    seqs = [r.seq for r in rows]
    assert seqs == sorted(seqs)
    assert len(set(seqs)) == len(seqs)
    buf.close()
