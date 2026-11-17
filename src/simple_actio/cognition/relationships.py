"""Relationship 插件位(V4 A4,Q3:数据模型 + no-op;中期尺度,归 mid_term 语义)。"""
from __future__ import annotations

from dataclasses import dataclass

STANCES = ("cold", "neutral", "cooperative", "close")


@dataclass(frozen=True)
class RelationshipView:
    other: str
    stance: str = "neutral"
    trust: int = 0  # -2..2

    def __post_init__(self):
        if not isinstance(self.other, str) or not self.other:
            raise ValueError("other 必须是非空字符串")
        if self.stance not in STANCES:
            raise ValueError(f"stance 必须是 {STANCES}")
        if self.trust not in (-2, -1, 0, 1, 2):
            raise ValueError("trust 必须在 -2..2")


class NoopRelationshipDynamics:
    def update(self, view: RelationshipView, observation, *, action: str | None = None):
        return view, None
