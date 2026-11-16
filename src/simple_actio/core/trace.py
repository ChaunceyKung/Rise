"""CognitiveTrace:认知层旁路轨迹(V4 A1;三层规划 §11.2 缺口 D)。

与 simple_actio.trace.v2(激活/路由轨迹,冻结)分离:这里记录的是
状态差异、行动意图与结构化依据引用,供审计"状态如何更新、决策依据什么"。
不落任何库;产物化由调用方(ControlPlane/MindAgent)带走。
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class CognitiveTrace:
    mode: str
    turn: int
    action_type: str
    directives: tuple[str, ...] = ()
    mechanisms: tuple[str, ...] = ()
    state_delta: tuple = ()          # tuple[StateDelta 字段摘要]
    rationale: dict | None = None    # DecisionRecord 的薄版(A3 升全量)
    extra: dict = field(default_factory=dict)

    def to_wire(self) -> dict:
        return {"schema": "simple_actio.cognitive-trace.v1", "mode": self.mode, "turn": self.turn,
                "action_type": self.action_type, "directives": list(self.directives),
                "mechanisms": list(self.mechanisms),
                "state_delta": [{"fields": list(d.fields), "source": d.source,
                                 "time_scale": d.time_scale} for d in self.state_delta],
                "rationale": self.rationale, "extra": dict(self.extra)}
