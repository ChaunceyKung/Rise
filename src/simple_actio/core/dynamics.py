"""CognitiveDynamics 协议与 StateDelta(V4 A1;三层规划 §8/§10)。

状态更新必须留下"哪些字段、因何来源、凭何证据"的轨迹——这使
Inner 的行为一致性可审计,也让 MindAgent 未来演化 Dynamics 组件时有
可验证的对象(§1.3 对账)。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from simple_actio.core.observation import PerceivedObservation
from simple_actio.core.state import CognitiveState

TIME_SCALES = ("long", "mid", "short")


@dataclass(frozen=True)
class StateDelta:
    """一次状态更新的结构化记录:受影响字段 + 来源 + 证据。"""

    fields: tuple[str, ...]
    source: str                      # 如 'observation:bob 说过:...' 的机制名
    evidence: dict = field(default_factory=dict)
    time_scale: str = "mid"          # long/mid/short(三层规划 §3 三时间尺度)

    def __post_init__(self):
        if not self.fields or not all(isinstance(f, str) and f for f in self.fields):
            raise ValueError("fields 必须是非空字符串元组")
        if self.time_scale not in TIME_SCALES:
            raise ValueError(f"time_scale 必须是 {TIME_SCALES}")


@runtime_checkable
class CognitiveDynamics(Protocol):
    """(状态, 观察[, 已执行行动]) → (新状态, 状态差)。不落任何库;每步可独立重放。"""

    def update(self, state: CognitiveState, observation: PerceivedObservation,
               *, action: str | None = None) -> tuple[CognitiveState, StateDelta]: ...


class RuleDynamics:
    """规则首版:把对方发言记为信念(mid),行动记为 last_action。

    M1 ModeAgent._default_transition 的协议化等价物;情绪/关系更新
    (short/long 尺度)是 A4 的插件位。
    """

    def update(self, state, observation, *, action=None):
        belief = f"{observation.speaker} 说过:{observation.utterance[:40]}"
        after = state.advanced(added_beliefs=(belief,), last_action=action)
        return after, StateDelta(fields=("beliefs",), source="rule_observation",
                                 evidence={"speaker": observation.speaker,
                                           "utterance_prefix": observation.utterance[:20]},
                                 time_scale="mid")
