"""行为策略协议:机制(mechanism)可组合,输出指导语指令(V3 §2.2 首批两机制)。

策略不直接生成话语——它产出 PolicyDirective(指导语指令列表 + 触发说明),
由 ModeDirectiveBackend 注入现有 SimpleActio 指导语管线;话语仍由模型后端生成。
这是"一套核心、两种模式"的落点:Inner/Outer 只是机制组合不同。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from simple_actio.core.observation import PerceivedObservation
from simple_actio.core.state import MindState


@dataclass(frozen=True)
class PolicyDirective:
    instructions: tuple[str, ...]
    mechanisms: tuple[str, ...]

    def __post_init__(self):
        if not self.instructions or not all(isinstance(x, str) and x for x in self.instructions):
            raise ValueError("指导语指令必须是非空字符串列表")
        if not self.mechanisms:
            raise ValueError("至少声明一个触发机制")


@runtime_checkable
class ModeMechanism(Protocol):
    """一个可组合的行为机制:给出本步的指导语;不适用时返回 None。"""

    name: str

    def apply(self, state: MindState, observation: PerceivedObservation) -> tuple[str, ...] | None: ...


@dataclass(frozen=True)
class CombinedPolicy:
    """按声明顺序叠加机制;至少一个机制命中,否则返回保守指令。"""

    mechanisms: tuple[ModeMechanism, ...]

    def __post_init__(self):
        if not self.mechanisms:
            raise ValueError("策略至少要有一个机制")

    def decide(self, state: MindState, observation: PerceivedObservation) -> PolicyDirective:
        instructions: list[str] = []
        fired: list[str] = []
        for mechanism in self.mechanisms:
            produced = mechanism.apply(state, observation)
            if produced:
                fired.append(mechanism.name)
                instructions.extend(produced)
        if not fired:
            return PolicyDirective(instructions=("维持当前目标,按已知信息谨慎回应",), mechanisms=("fallback",))
        return PolicyDirective(instructions=tuple(instructions), mechanisms=tuple(fired))
