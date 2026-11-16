"""目标模块:优先级与状态(V4 A2;BDI/TPB,三层规划 §8 I3)。"""
from __future__ import annotations

from dataclasses import dataclass

GOAL_STATUS = ("active", "satisfied", "dropped")


@dataclass(frozen=True)
class Goal:
    description: str
    priority: int = 3  # 1(最高)..5
    status: str = "active"

    def __post_init__(self):
        if not isinstance(self.description, str) or not self.description:
            raise ValueError("description 必须是非空字符串")
        if type(self.priority) is not int or not 1 <= self.priority <= 5:
            raise ValueError("priority 必须是 1..5 的整数")
        if self.status not in GOAL_STATUS:
            raise ValueError(f"status 必须是 {GOAL_STATUS}")


def active_goals(goals: tuple[Goal, ...]) -> tuple[Goal, ...]:
    """活跃目标按优先级升序(稳定:同优先按描述序)。"""
    return tuple(sorted((g for g in goals if g.status == "active"),
                        key=lambda g: (g.priority, g.description)))


def to_strings(goals: tuple[Goal, ...]) -> tuple[str, ...]:
    return tuple(g.description for g in active_goals(goals))
