from simple_actio.backend_errors import (AgentBackendError, AgentBackendMalformed, AgentBackendRejected,
                                         AgentBackendTimeout, AgentBackendUnavailable)


def test_each_agent_backend_error_carries_its_termination_reason_and_transience():
    assert [(c.reason, c.transient) for c in (AgentBackendTimeout, AgentBackendUnavailable,
                                              AgentBackendRejected, AgentBackendMalformed)] == [
        ("role_backend_timeout", True), ("role_backend_unavailable", True),
        ("role_backend_rejected", False), ("role_backend_failure", False)]
    assert all(issubclass(c, AgentBackendError) for c in (AgentBackendTimeout, AgentBackendMalformed))
