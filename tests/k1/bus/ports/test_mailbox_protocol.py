"""
Tests for k1.bus.ports.mailbox -- IMailbox, IMailboxRouter, MailboxConfig, errors.

Coverage targets:
    - MailboxConfig validation (positive capacity, defaults)
    - MailboxConfig frozen
    - BackpressureError attributes and message
    - UnknownActorError attributes and message
    - IMailbox structural subtyping
    - IMailboxRouter structural subtyping
    - Non-conforming classes fail isinstance checks
"""

from typing import Optional

import pytest

from k1.bus.envelope import Envelope
from k1.bus.ports.mailbox import (
    BackpressureError,
    IMailbox,
    IMailboxRouter,
    MailboxConfig,
    UnknownActorError,
)

# ===================================================================
# MailboxConfig
# ===================================================================


class TestMailboxConfig:
    """MailboxConfig frozen dataclass tests."""

    def test_defaults(self) -> None:
        config = MailboxConfig()
        assert config.capacity == 256
        assert config.priority_wfq is True

    def test_custom_values(self) -> None:
        config = MailboxConfig(capacity=1024, priority_wfq=False)
        assert config.capacity == 1024
        assert config.priority_wfq is False

    def test_frozen(self) -> None:
        config = MailboxConfig()
        with pytest.raises(AttributeError):
            config.capacity = 512  # type: ignore[misc]

    def test_zero_capacity_rejected(self) -> None:
        with pytest.raises(ValueError, match="capacity must be > 0"):
            MailboxConfig(capacity=0)

    def test_negative_capacity_rejected(self) -> None:
        with pytest.raises(ValueError, match="capacity must be > 0"):
            MailboxConfig(capacity=-1)

    def test_capacity_one_accepted(self) -> None:
        config = MailboxConfig(capacity=1)
        assert config.capacity == 1


# ===================================================================
# Error types
# ===================================================================


class TestBackpressureError:
    """BackpressureError exception tests."""

    def test_attributes(self) -> None:
        err = BackpressureError(actor_id="agent-1", capacity=256)
        assert err.actor_id == "agent-1"
        assert err.capacity == 256

    def test_message(self) -> None:
        err = BackpressureError(actor_id="agent-1", capacity=256)
        assert "agent-1" in str(err)
        assert "256" in str(err)

    def test_is_exception(self) -> None:
        err = BackpressureError(actor_id="x", capacity=1)
        assert isinstance(err, Exception)


class TestUnknownActorError:
    """UnknownActorError exception tests."""

    def test_attributes(self) -> None:
        err = UnknownActorError(actor_id="agent-99")
        assert err.actor_id == "agent-99"

    def test_message(self) -> None:
        err = UnknownActorError(actor_id="agent-99")
        assert "agent-99" in str(err)

    def test_is_exception(self) -> None:
        err = UnknownActorError(actor_id="x")
        assert isinstance(err, Exception)


# ===================================================================
# IMailbox Protocol structural subtyping
# ===================================================================


class _ConformingMailbox:
    """Minimal class satisfying IMailbox protocol."""

    def receive(self, timeout_ms: int = 0) -> Optional[Envelope]:
        return None

    def pending(self) -> int:
        return 0


class _NonConformingMailbox:
    """Missing pending() method."""

    def receive(self, timeout_ms: int = 0) -> Optional[Envelope]:
        return None


class TestIMailboxProtocol:
    """IMailbox structural subtyping tests."""

    def test_conforming_is_instance(self) -> None:
        mailbox = _ConformingMailbox()
        assert isinstance(mailbox, IMailbox)

    def test_non_conforming_is_not_instance(self) -> None:
        mailbox = _NonConformingMailbox()
        assert not isinstance(mailbox, IMailbox)

    def test_receive_returns_none_when_empty(self) -> None:
        mailbox = _ConformingMailbox()
        assert mailbox.receive() is None

    def test_pending_returns_int(self) -> None:
        mailbox = _ConformingMailbox()
        assert mailbox.pending() == 0


# ===================================================================
# IMailboxRouter Protocol structural subtyping
# ===================================================================


class _ConformingRouter:
    """Minimal class satisfying IMailboxRouter protocol."""

    def deliver(self, actor_id: str, envelope: Envelope) -> None:
        pass

    def register(self, actor_id: str, config: Optional[MailboxConfig] = None) -> IMailbox:
        return _ConformingMailbox()

    def unregister(self, actor_id: str) -> bool:
        return True

    def registered_actors(self) -> list[str]:
        return []

    def close(self) -> None:
        pass

    @property
    def is_closed(self) -> bool:
        return False


class _NonConformingRouter:
    """Missing registered_actors."""

    def deliver(self, actor_id: str, envelope: Envelope) -> None:
        pass

    def register(self, actor_id: str, config: Optional[MailboxConfig] = None) -> IMailbox:
        return _ConformingMailbox()

    def unregister(self, actor_id: str) -> bool:
        return True


class TestIMailboxRouterProtocol:
    """IMailboxRouter structural subtyping tests."""

    def test_conforming_is_instance(self) -> None:
        router = _ConformingRouter()
        assert isinstance(router, IMailboxRouter)

    def test_non_conforming_is_not_instance(self) -> None:
        router = _NonConformingRouter()
        assert not isinstance(router, IMailboxRouter)

    def test_register_returns_mailbox(self) -> None:
        router = _ConformingRouter()
        mailbox = router.register("agent-1")
        assert isinstance(mailbox, IMailbox)

    def test_unregister_returns_bool(self) -> None:
        router = _ConformingRouter()
        assert router.unregister("agent-1") is True

    def test_registered_actors_returns_list(self) -> None:
        router = _ConformingRouter()
        assert router.registered_actors() == []
