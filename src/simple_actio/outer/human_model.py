"""HumanModel:AI 对人的结构化估计(V4 A3;三层规划 §9/§5.4,Survey ToM-SWE)。

四分离纪律:事实(facts,观察可直接确认)/假设(hypotheses,推断)/
置信度(confidence∈[0,1])/证据来源(evidence refs,可回查)。
估计与真值类型隔离:HumanModel 永不冒充 CognitiveState(红线 3)。
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Hypothesis:
    statement: str
    confidence: float
    evidence: tuple[str, ...] = ()

    def __post_init__(self):
        if not isinstance(self.statement, str) or not self.statement:
            raise ValueError("statement 必须是非空字符串")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence 必须在 [0,1],得到 {self.confidence}")
        if not all(isinstance(e, str) and e for e in self.evidence):
            raise ValueError("evidence 必须是非空字符串元组")


@dataclass(frozen=True)
class HumanModel:
    person_id: str
    facts: tuple[str, ...] = ()
    hypotheses: tuple[Hypothesis, ...] = ()
    last_updated_turn: int = -1

    def __post_init__(self):
        if not isinstance(self.person_id, str) or not self.person_id:
            raise ValueError("person_id 必须是非空字符串")
        if not all(isinstance(f, str) and f for f in self.facts):
            raise ValueError("facts 必须是非空字符串元组")

    def top(self, *, limit: int = 2) -> tuple[Hypothesis, ...]:
        """按置信度降序(稳定:同置信按语句序)。"""
        return tuple(sorted(self.hypotheses, key=lambda h: (-h.confidence, h.statement))[:limit])

    def uncertainty(self) -> float:
        """1 - 最高置信;无任何假设时为 1.0(完全未知)。"""
        best = max((h.confidence for h in self.hypotheses), default=0.0)
        return 1.0 - best

    def to_wire(self) -> dict:
        return {"person_id": self.person_id, "facts": list(self.facts),
                "hypotheses": [{"statement": h.statement, "confidence": h.confidence,
                                "evidence": list(h.evidence)} for h in self.hypotheses],
                "last_updated_turn": self.last_updated_turn}

    @classmethod
    def from_wire(cls, value: dict) -> "HumanModel":
        expected = {"person_id", "facts", "hypotheses", "last_updated_turn"}
        if not isinstance(value, dict) or set(value) != expected:
            raise ValueError("HumanModel wire 字段不匹配")
        return cls(person_id=value["person_id"], facts=tuple(value["facts"]),
                   hypotheses=tuple(Hypothesis(statement=h["statement"], confidence=h["confidence"],
                                               evidence=tuple(h["evidence"]))
                                    for h in value["hypotheses"]),
                   last_updated_turn=value["last_updated_turn"])
