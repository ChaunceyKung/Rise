"""Outer 机制:交互对象估计(human_model)与任务目标驱动的策略选择。

advisor 是"Outer 调 Inner 做对手预测"的接缝(V3 §2.3):可注入一个
callable(observation) -> str 的预测器(通常包一个 Inner agent);None 时跳过。
"""
from __future__ import annotations

from dataclasses import dataclass
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
            instructions.append(f"对手行为预测(仅参考,决策是你自己的):{self.advisor(observation)[:60]}")
        return tuple(instructions)
