from dataclasses import dataclass
from typing import Any

import pytest


@dataclass
class _FakeResult:
    sentiment: str = "very_positive"
    emotions: list[str] = None  # type: ignore[assignment]
    safety: str = "GREEN"
    intent: str = "share_news"
    ingress: str = "CELEBRATION"
    entities: list[dict[str, Any]] = None  # type: ignore[assignment]
    general_entities: list[dict[str, Any]] = None  # type: ignore[assignment]
    temporal: list[dict[str, Any]] = None  # type: ignore[assignment]
    embedding: list[float] = None  # type: ignore[assignment]
    latency_ms: float = 12.34

    sentiment_confidence: float = 0.9
    ingress_confidence: float = 0.8
    intent_confidence: float = 0.85

    def __post_init__(self) -> None:
        if self.emotions is None:
            self.emotions = ["joy", "excitement", "togetherness"]
        if self.entities is None:
            self.entities = [
                {"text": "grandmother", "label": "KINSHIP", "start": 3, "end": 14},
                {"text": "family reunion", "label": "FAMILY_EVENT", "start": 50, "end": 63},
            ]
        if self.general_entities is None:
            self.general_entities = []
        if self.temporal is None:
            self.temporal = [
                {"text": "yesterday", "label": "DATE_REL", "start": 20, "end": 29},
                {"text": "next Sunday", "label": "DATE_REL", "start": 70, "end": 80},
            ]
        if self.embedding is None:
            self.embedding = [0.0] * 768


class _FakeClient:
    def __init__(self) -> None:
        self.analyze_calls = 0

    def analyze(self, text: str, capabilities: list[str] | None = None) -> _FakeResult:
        self.analyze_calls += 1
        return _FakeResult()


@pytest.mark.parametrize("single_pass_env", ["1", "true", "False"])
def test_ultrabert_adapter_single_pass_reuses_one_forward_pass(monkeypatch, single_pass_env):
    """If single-pass is enabled, multiple adapter calls should reuse one analyze() call."""

    # Import here so monkeypatching env takes effect before module loads config.
    monkeypatch.setenv("K0_ULTRABERT_SINGLE_PASS", single_pass_env)

    from k0.runtime import ultrabert_adapter

    # Ensure clean cache between parameter runs
    ultrabert_adapter.reset_analysis_cache()

    fake_client = _FakeClient()

    monkeypatch.setattr(ultrabert_adapter, "get_ultrabert_client", lambda: fake_client)

    text = "My grandmother called yesterday to remind me about the family reunion next Sunday. I am so excited!"

    _ = ultrabert_adapter.analyze_affect(text)
    _ = ultrabert_adapter.extract_entities(text)
    _ = ultrabert_adapter.classify_activity(text)

    # Only enforced when single-pass is enabled
    enabled = single_pass_env not in {"0", "false", "False"}
    if enabled:
        assert fake_client.analyze_calls == 1
    else:
        assert fake_client.analyze_calls >= 2


def test_ultrabert_adapter_single_pass_cache_miss_on_different_text(monkeypatch):
    monkeypatch.setenv("K0_ULTRABERT_SINGLE_PASS", "1")

    from k0.runtime import ultrabert_adapter

    ultrabert_adapter.reset_analysis_cache()

    fake_client = _FakeClient()
    monkeypatch.setattr(ultrabert_adapter, "get_ultrabert_client", lambda: fake_client)

    t1 = "hello world"
    t2 = "hello world!"  # different key

    ultrabert_adapter.analyze_affect(t1)
    ultrabert_adapter.extract_entities(t2)

    assert fake_client.analyze_calls == 2
