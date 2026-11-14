"""智能体位模型后端的失败异常。

mindagent 接住这四种异常,按 reason 归到终止原因、按 transient 区分瞬态与确定性失败。
simple_actio 只许导入 simulator,所以由组合根(factory.agent_backend)把 HTTP 层的异常转成这里的四种。"""
from __future__ import annotations


class AgentBackendError(Exception):
    """智能体位模型后端失败的基类。reason 是终止原因,transient 为真表示可重试。"""

    reason: str = "role_backend_failure"
    transient: bool = False


class AgentBackendTimeout(AgentBackendError):
    reason = "role_backend_timeout"
    transient = True


class AgentBackendUnavailable(AgentBackendError):
    reason = "role_backend_unavailable"
    transient = True


class AgentBackendRejected(AgentBackendError):
    reason = "role_backend_rejected"
    transient = False


class AgentBackendMalformed(AgentBackendError):
    reason = "role_backend_failure"
    transient = False
