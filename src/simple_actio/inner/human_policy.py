"""Inner Actio:模拟人的行为与决策(V3 §2.2)。首批两机制(Q1):goal-driven + belief-driven。"""
from __future__ import annotations

from dataclasses import dataclass

from simple_actio.core.observation import PerceivedObservation
from simple_actio.core.state import MindState


@dataclass(frozen=True)
class GoalDriven:
    """显式目标驱动:目标未满足且观察出现机会时,给出朝向目标的指令。"""

    goals: tuple[str, ...]
    name: str = "goal_driven"

    def apply(self, state: MindState, observation: PerceivedObservation) -> tuple[str, ...] | None:
        active = state.goals or self.goals
        if not active:
            return None
        opportunity = any("机会" in str(v) or "提议" in str(v) for v in observation.visible_facts.values())
        if not opportunity and "提议" not in observation.utterance:
            return None
        return tuple(f"朝着你的目标行动:{goal}" for goal in active[:2])


@dataclass(frozen=True)
class BeliefDriven:
    """信念驱动:只依据自己相信的信息行动;与信念冲突的观察要显式存疑。"""

    beliefs: tuple[str, ...]
    name: str = "belief_driven"

    def apply(self, state: MindState, observation: PerceivedObservation) -> tuple[str, ...] | None:
        held = state.beliefs or self.beliefs
        if not held:
            return None
        return tuple(f"只依据你的信念行动:{belief}" for belief in held[:2])
