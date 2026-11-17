"""DecisionRecord:结构化决策依据(V4 A3;三层规划 §10.3 Rationale≠Rationality)。

记录系统**实际使用**的目标/信念/技能引用与备选——与 LLM 生成的文字
解释分离;evidence_level 区分结构推导与模型生成(红线 5)。
"""
from __future__ import annotations

from dataclasses import dataclass

EVIDENCE_LEVELS = ("structurally_derived", "model_generated")


@dataclass(frozen=True)
class DecisionRecord:
    selected: str                              # 如 'clarify' / 'act'
    goal_refs: tuple[str, ...] = ()
    belief_refs: tuple[str, ...] = ()          # CognitiveState.beliefs / HumanModel 假设语句
    skill_ref: str | None = None
    alternatives_considered: tuple[str, ...] = ()
    evidence_level: str = "structurally_derived"
    summary: str = ""

    def __post_init__(self):
        if not isinstance(self.selected, str) or not self.selected:
            raise ValueError("selected 必须是非空字符串")
        if self.evidence_level not in EVIDENCE_LEVELS:
            raise ValueError(f"evidence_level 必须是 {EVIDENCE_LEVELS}")
        if not self.alternatives_considered or self.selected not in self.alternatives_considered:
            raise ValueError("selected 必须在 alternatives_considered 中")

    def to_wire(self) -> dict:
        return {"selected": self.selected, "goal_refs": list(self.goal_refs),
                "belief_refs": list(self.belief_refs), "skill_ref": self.skill_ref,
                "alternatives_considered": list(self.alternatives_considered),
                "evidence_level": self.evidence_level, "summary": self.summary}
