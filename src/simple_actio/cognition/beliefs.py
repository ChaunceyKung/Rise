"""信念模块:带置信度与证据的信念表示(V4 A2;BDI/ToM,三层规划 §8 I2)。"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Belief:
    statement: str
    confidence: float  # [0,1];Outer 的估计必备,Inner 可默认 1.0
    evidence: tuple[str, ...] = ()

    def __post_init__(self):
        if not isinstance(self.statement, str) or not self.statement:
            raise ValueError("statement 必须是非空字符串")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence 必须在 [0,1],得到 {self.confidence}")
        if not all(isinstance(e, str) and e for e in self.evidence):
            raise ValueError("evidence 必须是非空字符串元组")


def strongest(beliefs: tuple[Belief, ...], *, limit: int = 3) -> tuple[Belief, ...]:
    """按置信度降序取前 N(稳定排序:同置信按语句序)。"""
    ranked = sorted(beliefs, key=lambda b: (-b.confidence, b.statement))
    return tuple(ranked[:limit])


def to_strings(beliefs: tuple[Belief, ...]) -> tuple[str, ...]:
    """映射进 CognitiveState.beliefs(tuple[str])的形态。"""
    return tuple(b.statement for b in beliefs)
