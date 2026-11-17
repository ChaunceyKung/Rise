"""HumanBehaviorModel:Inner 侧行为预测(V4 A4;Survey Simulation-Assisted 基础)。

Outer 可经它做反事实推演,但预测不是真值——上层须报告预测误差(红线)。
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from simple_actio.core.observation import PerceivedObservation
from simple_actio.core.state import CognitiveState


@runtime_checkable
class HumanBehaviorModel(Protocol):
    def predict(self, state: CognitiveState, observation: PerceivedObservation,
                *, horizon: int = 1) -> tuple[str, ...]: ...


class RuleBehaviorModel:
    """规则首版:由目标/信念/短期情绪出候选行为文本(确定性)。"""

    def predict(self, state, observation, *, horizon: int = 1):
        candidates: list[str] = []
        for goal in state.goals[:2]:
            candidates.append(f"朝目标推进:{goal}")
        if state.short_term.get("affect_hint") == "tension":
            candidates.append("表达顾虑并要求调整")
        if any("偏好" in b for b in state.beliefs):
            candidates.append("按已表达偏好行动")
        if not candidates:
            candidates.append("保持观望并询问进展")
        return tuple(dict.fromkeys(candidates))[: max(1, horizon)]


class InnerPredictor:
    """把(状态提供者, 行为模型)桥成 advisor 可用的预测器。

    state_provider: () -> CognitiveState(通常闭包一个 Inner agent 的当前状态)。
    """

    def __init__(self, state_provider, model: HumanBehaviorModel | None = None):
        self._state = state_provider
        self._model = model or RuleBehaviorModel()

    def predict(self, state, observation, *, horizon: int = 1):
        return self._model.predict(self._state(), observation, horizon=horizon)

    def first_line(self, observation) -> str:
        return self.predict(None, observation, horizon=1)[0]
