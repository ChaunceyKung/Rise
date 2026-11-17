"""ActionExecutor:把抽象意图落成执行(V4 A1 规划的第三补充接口)。

两种实现:指导语注入(经 ModeDirectiveBackend,现有缝隙)与环境动作
(记录式,V1 无真实环境)。executor 只执行,不做认知(边界同 Harness)。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from simple_actio.core.intent import ActionIntent


@dataclass(frozen=True)
class ExecutionOutcome:
    kind: str            # guidance | env_action
    delivered: bool
    detail: str = ""


@runtime_checkable
class ActionExecutor(Protocol):
    def execute(self, intent: ActionIntent, context: dict) -> ExecutionOutcome: ...


class GuidanceExecutor:
    """实现 1:意图携带的 directives 注入指导语管线(经 ModeDirectiveBackend)。"""

    def __init__(self, backend):
        self._backend = backend

    def execute(self, intent, context):
        directives = tuple(intent.parameters.get("directives", ()))
        self._backend.set_directive(directives)
        return ExecutionOutcome(kind="guidance", delivered=bool(directives),
                                detail=f"{len(directives)} 条指令已注入")


class EnvironmentActionExecutor:
    """实现 2:环境动作(推进世界时间的 action 型意图)。V1 记录式交付。"""

    def execute(self, intent, context):
        if intent.action_type != "action":
            raise ValueError(f"环境执行器只处理 action 型意图,得到 {intent.action_type}")
        log = context.setdefault("env_action_log", []) if isinstance(context, dict) else None
        if log is not None:
            log.append({"action_type": intent.action_type,
                        "parameters": dict(intent.parameters), "skill_ref": intent.skill_ref})
        return ExecutionOutcome(kind="env_action", delivered=True,
                                detail=f"环境动作已记录:{sorted(intent.parameters)}")
