"""可感知观察:把"模拟器客观状态 ≠ 人物已知状态"落成类型约束(V3 §2.2)。

构造时按可见键白名单过滤原始世界状态;被剥离的字段只留下计数,内容不进入对象——
隐藏状态的泄漏在构造点就被挡住,不依赖调用方自觉。
"""
from __future__ import annotations

from dataclasses import dataclass

from simple_actio.core.state import _check


@dataclass(frozen=True)
class PerceivedObservation:
    speaker: str
    utterance: str
    visible_facts: dict
    hidden_count: int  # 被剥离的不可观察字段数,只计数不留内容

    def __post_init__(self):
        if not isinstance(self.speaker, str) or not self.speaker:
            raise ValueError("speaker 必须是非空字符串")
        if not isinstance(self.utterance, str):
            raise ValueError("utterance 必须是字符串")
        _check(self.visible_facts)
        object.__setattr__(self, "visible_facts", dict(self.visible_facts))

    @classmethod
    def from_world(cls, raw: dict, visible: frozenset[str] | set[str], *, speaker: str, utterance: str) -> "PerceivedObservation":
        """raw 是模拟器的客观状态;visible 是该角色被允许看到的键集合。"""
        if not isinstance(raw, dict):
            raise ValueError("世界状态必须是字典")
        unknown = [k for k in visible if k not in raw]
        if unknown:
            raise ValueError(f"可见键在世界状态中不存在: {sorted(unknown)}")
        kept = {k: raw[k] for k in sorted(visible)}
        return cls(speaker=speaker, utterance=utterance, visible_facts=kept,
                   hidden_count=len(raw) - len(kept))

    def fact(self, key: str):
        if key not in self.visible_facts:
            raise KeyError(f"不可观察字段被拒绝访问: {key}")
        return self.visible_facts[key]
