"""智能体位后端的转换后端。

组合根给智能体位的模型后端外面套一层本模块的转换后端:接住 factory.opponents 的 HTTP 层异常,
改抛 simple_actio.backend_errors 的四种异常(simple_actio 不许导入 factory)。
异常文字只含槽位与原异常类名,不带原异常的文字(原文可能含端点地址),也不链原异常。"""
from __future__ import annotations

from simple_actio.backend_errors import (
    AgentBackendMalformed, AgentBackendRejected, AgentBackendTimeout, AgentBackendUnavailable,
)

from .opponents import (
    OpponentApiError, OpponentRejectedError, OpponentTimeoutError, OpponentUnavailableError,
)


class TranslatingAgentBackend:
    """包一个带 respond_guided 的后端,把 OpponentApiError 一族改抛成 AgentBackendError 一族。"""

    def __init__(self, backend: object) -> None:
        self.backend = backend

    def respond_guided(
        self, persona, scenario, history, speaker_slot: str, guidance,
    ) -> tuple[str, str | None]:
        try:
            return self.backend.respond_guided(persona, scenario, history, speaker_slot, guidance)
        except OpponentTimeoutError as exc:
            raise AgentBackendTimeout(self._message(speaker_slot, exc)) from None
        except OpponentUnavailableError as exc:
            raise AgentBackendUnavailable(self._message(speaker_slot, exc)) from None
        except OpponentRejectedError as exc:
            raise AgentBackendRejected(self._message(speaker_slot, exc)) from None
        except OpponentApiError as exc:
            raise AgentBackendMalformed(self._message(speaker_slot, exc)) from None

    @staticmethod
    def _message(speaker_slot: str, exc: Exception) -> str:
        return f"agent backend failed for slot {speaker_slot!r}: {type(exc).__name__}"
