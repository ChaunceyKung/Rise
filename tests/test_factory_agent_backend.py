import pytest
from factory.agent_backend import TranslatingAgentBackend
from factory.opponents import (OpponentApiError, OpponentRejectedError, OpponentTimeoutError,
                               OpponentUnavailableError)
from simple_actio.backend_errors import (AgentBackendMalformed, AgentBackendRejected, AgentBackendTimeout,
                                         AgentBackendUnavailable)


class _Raises:
    def __init__(self, exc): self.exc = exc
    def respond_guided(self, *a): raise self.exc


@pytest.mark.parametrize("raised, expected", [
    (OpponentTimeoutError("t http://10.0.0.1"), AgentBackendTimeout),
    (OpponentUnavailableError("u"), AgentBackendUnavailable),
    (OpponentRejectedError("r"), AgentBackendRejected),
    (OpponentApiError("empty reply"), AgentBackendMalformed),
])
def test_opponent_api_errors_become_agent_backend_errors(raised, expected):
    with pytest.raises(expected) as info:
        TranslatingAgentBackend(_Raises(raised)).respond_guided(None, None, [], "agent", ())
    assert "10.0.0.1" not in str(info.value) and info.value.__cause__ is None


def test_a_good_reply_passes_through_untouched():
    class Ok:
        def respond_guided(self, *a): return ("hi", None)
    assert TranslatingAgentBackend(Ok()).respond_guided(None, None, [], "agent", ()) == ("hi", None)
