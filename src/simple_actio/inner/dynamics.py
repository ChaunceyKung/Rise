"""事件驱动的简化 Dynamics(V4 A2;三层规划 §8 I6)。

在 RuleDynamics(信念记录)之上:一致关键词 → 目标状态推进(mid);
冲突关键词 → 短期情绪提示(short)。情绪/关系的完整机制是 A4 插件位。
"""
from __future__ import annotations

from simple_actio.core.dynamics import StateDelta
from simple_actio.core.observation import PerceivedObservation
from simple_actio.core.state import CognitiveState

AGREE_MARKERS = ("同意", "达成", "可以", "接受")
CONFLICT_MARKERS = ("不行", "拒绝", "反对", "太贵")


class EventDynamics:
    """规则首版的事件驱动状态更新;每步一个 StateDelta,fields 汇总本步变化。"""

    def update(self, state: CognitiveState, observation: PerceivedObservation,
               *, action: str | None = None):
        text = observation.utterance
        belief = f"{observation.speaker} 说过:{text[:40]}"
        fields = ["beliefs"]
        mid = dict(state.mid_term)
        short = dict(state.short_term)

        goal_status = dict(mid.get("goal_status", {}))
        if any(marker in text for marker in AGREE_MARKERS):
            for goal in state.goals:
                if goal_status.get(goal, "active") == "active":  # 仅 active → satisfied
                    goal_status[goal] = "satisfied"
            if state.goals:
                fields.append("mid_term.goal_status")
        if any(marker in text for marker in CONFLICT_MARKERS):
            short["affect_hint"] = "tension"
            fields.append("short_term.affect_hint")

        mid["goal_status"] = goal_status
        after = CognitiveState(subject=state.subject, turn=state.turn + 1,
                               goals=state.goals, beliefs=state.beliefs + (belief,),
                               uncertainty=state.uncertainty, last_action=action,
                               frozen_extra=state.frozen_extra, long_term=state.long_term,
                               mid_term=mid, short_term=short)
        scales = "short" if "short_term.affect_hint" in fields else "mid"
        return after, StateDelta(fields=tuple(fields), source="event_dynamics",
                                 evidence={"speaker": observation.speaker,
                                           "utterance_prefix": text[:20],
                                           "markers": [m for m in AGREE_MARKERS + CONFLICT_MARKERS if m in text]},
                                 time_scale=scales)
