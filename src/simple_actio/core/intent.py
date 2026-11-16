"""ActionIntent 与 StepResult(V4 A1;三层规划 §10 + Shachi 的 Tool-Call/Action 区分)。

ActionIntent 是待执行的行动意图:action_type('utterance'|'tool_call'|'action')。
time_semantics 落 Shachi 的区分——tool_call 不推进环境时间,action 提交给环境
并可能推进世界状态;utterance 是对话层的行动子类。
StepResult 是 Decision 的超集:补 state_delta(状态差)与 rationale_summary
(结构化决策依据;与 LLM 文字解释分离,红线 5)。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from simple_actio.core.action import Decision

ACTION_TYPES = ("utterance", "tool_call", "action")


@dataclass(frozen=True)
class ActionIntent:
    action_type: str
    parameters: dict = field(default_factory=dict)
    skill_ref: str | None = None
    time_semantics: str | None = None  # 缺省按 action_type 派生;显式给错即拒

    def __post_init__(self):
        if self.action_type not in ACTION_TYPES:
            raise ValueError(f"action_type 必须是 {ACTION_TYPES}")
        expected = {"tool_call": "tool_call", "action": "action"}.get(self.action_type, "utterance")
        if self.time_semantics is None:
            object.__setattr__(self, "time_semantics", expected)
        elif self.time_semantics != expected:
            raise ValueError(f"{self.action_type} 的时间语义应为 {expected},得到 {self.time_semantics}")

    def to_wire(self) -> dict:
        return {"action_type": self.action_type, "parameters": dict(self.parameters),
                "skill_ref": self.skill_ref, "time_semantics": self.time_semantics}


@dataclass(frozen=True)
class StepResult(Decision):
    """一次 step 的完整结果:Decision 的全部字段 + 状态差 + 结构化依据。"""

    state_delta: tuple = ()            # tuple[StateDelta, ...](A1 起由 dynamics 产出)
    rationale_summary: dict | None = None  # DecisionRecord 的薄版;A3 升全量字段

    def to_wire(self) -> dict:
        wire = {"mode": self.mode, "utterance": self.utterance, "inner_thought": self.inner_thought,
                "directive": list(self.directive), "mechanisms": list(self.mechanisms),
                "state_delta": [{"fields": list(d.fields), "source": d.source,
                                 "time_scale": d.time_scale} for d in self.state_delta],
                "rationale_summary": self.rationale_summary}
        return wire
