"""Outer 机制:交互对象估计(human_model)与任务目标驱动的策略选择。

advisor 是"Outer 调 Inner 做对手预测"的接缝(V3 §2.3):可注入一个
callable(observation) -> str 的预测器(通常包一个 Inner agent);None 时跳过。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from simple_actio.core.observation import PerceivedObservation
from simple_actio.core.state import MindState


@dataclass(frozen=True)
class HumanModeling:
    """对交互对象的估计:把观察到的言行整理为对当前状态的判断,并驱动策略选择。"""

    hypotheses: tuple[str, ...]  # 对交互对象状态的先验假设(如"对方偏好合作")
    name: str = "human_modeling"

    def apply(self, state: MindState, observation: PerceivedObservation) -> tuple[str, ...] | None:
        if not self.hypotheses and not state.beliefs:
            return None
        cues = [observation.utterance[:30]] + [str(v)[:30] for v in observation.visible_facts.values()]
        return (f"依据可观察线索更新对对方的估计:{';'.join(cues[:2])}",
                "选择对当前估计最稳健的策略,不押注单一假设")


@dataclass(frozen=True)
class TaskGoalDriven:
    """AI 自身(非模拟人物)的任务目标驱动。"""

    objectives: tuple[str, ...]
    advisor: Callable[[PerceivedObservation], str] | None = None
    name: str = "task_goal"

    def apply(self, state: MindState, observation: PerceivedObservation) -> tuple[str, ...] | None:
        if not self.objectives:
            return None
        instructions = [f"以任务目标为先:{obj}" for obj in self.objectives[:2]]
        if self.advisor is not None:
            instructions.append(f"对手行为预测(仅参考,决策是你自己的):{self._advice(observation)[:60]}")
        return tuple(instructions)

    def _advice(self, observation) -> str:
        if hasattr(self.advisor, "predict"):  # HumanBehaviorModel 协议
            return self.advisor.predict(None, observation, horizon=1)[0]
        return self.advisor(observation)  # 旧 callable 形态


@dataclass(frozen=True)
class ClarificationPolicy:
    """PAHF 行动前澄清的最小版:人物状态不确定时,先澄清再行动。"""

    threshold: float = 0.6  # uncertainty > threshold → 澄清

    def intent(self, model, objectives):
        from simple_actio.core.intent import ActionIntent

        need = model.uncertainty() > self.threshold or not model.hypotheses
        if not need:
            return None
        return ActionIntent(action_type="utterance",
                            parameters={"kind": "clarify",
                                        "question": "当前目标还不明确,先确认你的意图再行动",
                                        "reason": "human_state_uncertain",
                                        "directives": ("先澄清对方意图,再选择行动策略",)},
                            skill_ref="clarification-v1")


@dataclass(frozen=True)
class HumanAwareDecisionPolicy:
    """读 HumanModel 出 ActionIntent(V4 A3):不确定先澄清,确信则按估计行动。"""

    objectives: tuple[str, ...] = ()
    clarify: ClarificationPolicy = field(default_factory=ClarificationPolicy)

    def decide(self, model, observation):
        from simple_actio.core.intent import ActionIntent

        clarifying = self.clarify.intent(model, self.objectives)
        if clarifying is not None:
            return clarifying
        top = model.top(limit=1)
        best = top[0] if top else None
        directives = tuple(f"以任务目标为先:{o}" for o in self.objectives[:2])
        if best is not None:
            directives = directives + (f"依据对对方的估计选择稳健策略:{best.statement}",)
        return ActionIntent(action_type="utterance",
                            parameters={"kind": "act",
                                        "top_hypothesis": best.statement if best else None,
                                        "confidence": best.confidence if best else None,
                                        "directives": directives},
                            skill_ref="human-aware-v1")
