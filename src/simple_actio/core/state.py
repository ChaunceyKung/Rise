"""共享心智状态:受限 JSON 可序列化、可摘要、不可变。

受限规则仿 actio.contracts.json(安全整数、无浮点、UTF-8 字符串、字典键为字符串),
但本包零跨包依赖,自行实现最小闭包。数值能力与成本指标**不放这里**
(V3 §10:那些进 Evaluation/Cost 产物,不进心智状态)。
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field


def _check(value) -> None:
    if value is None or type(value) is bool:
        return
    if type(value) is int and abs(value) <= 9007199254740991:
        return
    if type(value) is str:
        value.encode("utf-8")  # 拒绝孤代理
        return
    if type(value) is list:
        for item in value:
            _check(item)
        return
    if type(value) is dict and all(type(k) is str for k in value):
        for k, v in value.items():
            _check(k)
            _check(v)
        return
    raise ValueError("受限 JSON 只接受安全整数/字符串/布尔/None/列表/字符串键字典")


def canonical(value: dict) -> str:
    _check(value)
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"))


def digest(value: dict) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


@dataclass(frozen=True)
class MindState:
    """一次交互中的个体心智状态(Inner 的是人物自身状态,Outer 的是对交互对象的估计)。

    机制字段按 V3 首批两机制裁剪(Q1):goal+belief;emotion/history 随 M5 需要。
    """

    subject: str
    turn: int = 0
    goals: tuple[str, ...] = ()
    beliefs: tuple[str, ...] = ()
    uncertainty: tuple[str, ...] = ()  # Outer 专用:估计的不确定项
    last_action: str | None = None
    frozen_extra: dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.subject or not isinstance(self.subject, str):
            raise ValueError("subject 必须是非空字符串")
        for name in ("goals", "beliefs", "uncertainty"):
            value = getattr(self, name)
            if not isinstance(value, tuple) or not all(isinstance(x, str) and x for x in value):
                raise ValueError(f"{name} 必须是非空字符串元组")
        _check(self.frozen_extra)
        object.__setattr__(self, "frozen_extra", dict(self.frozen_extra))

    # ---- 受限 JSON 往返(可 seal 的前提) ----

    def to_wire(self) -> dict:
        return {
            "subject": self.subject, "turn": self.turn,
            "goals": list(self.goals), "beliefs": list(self.beliefs),
            "uncertainty": list(self.uncertainty), "last_action": self.last_action,
            "extra": self.frozen_extra,
        }

    @classmethod
    def from_wire(cls, value: dict) -> "MindState":
        expected = {"subject", "turn", "goals", "beliefs", "uncertainty", "last_action", "extra"}
        if not isinstance(value, dict) or set(value) != expected:
            raise ValueError("MindState wire 字段不匹配")
        return cls(subject=value["subject"], turn=value["turn"], goals=tuple(value["goals"]),
                   beliefs=tuple(value["beliefs"]), uncertainty=tuple(value["uncertainty"]),
                   last_action=value["last_action"], frozen_extra=value["extra"])

    def state_digest(self) -> str:
        return digest(self.to_wire())

    # ---- 演化算子(返回新状态,不就地改) ----

    def advanced(self, *, turn_delta: int = 1, added_beliefs: tuple[str, ...] = (),
                 dropped_beliefs: tuple[str, ...] = (), last_action: str | None = None) -> "MindState":
        keep = [b for b in self.beliefs if b not in dropped_beliefs]
        merged = keep + [b for b in added_beliefs if b not in keep]
        return MindState(subject=self.subject, turn=self.turn + turn_delta, goals=self.goals,
                         beliefs=tuple(merged), uncertainty=self.uncertainty,
                         last_action=last_action if last_action is not None else self.last_action,
                         frozen_extra=self.frozen_extra)
