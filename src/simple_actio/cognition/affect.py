"""Affect 插件位(V4 A4,Q3:数据模型 + no-op;真实 Appraisal 机制等实验假设)。"""
from __future__ import annotations

from dataclasses import dataclass

VALENCES = ("positive", "neutral", "negative")
AROUSALS = ("low", "moderate", "high")


@dataclass(frozen=True)
class AffectState:
    valence: str = "neutral"
    arousal: str = "low"

    def __post_init__(self):
        if self.valence not in VALENCES:
            raise ValueError(f"valence 必须是 {VALENCES}")
        if self.arousal not in AROUSALS:
            raise ValueError(f"arousal 必须是 {AROUSALS}")


class NoopAffectDynamics:
    """插件位:恒等更新(A4 不实现 Appraisal;接口与 Dynamics 族一致)。"""

    def update(self, affect: AffectState, observation, *, action: str | None = None):
        return affect, None
