"""新双模式与旧运行时的互操作层。

ModeDirectiveBackend 是唯一接缝:包装任意 GuidedBackend,把模式策略产出的指令
前置到指导语;SimpleActioInstance 与其全部既有路径零改动。triple_of 把
Decision 映射回 SocialSimulator 消费的 (utterance, inner_thought, trace)。
"""
from __future__ import annotations

from simple_actio.core.action import Decision


class ModeDirectiveBackend:
    """GuidedBackend 装饰器:每次调用前由模式 agent set_directive,指令注入指导语头部。"""

    def __init__(self, inner_backend):
        self._inner = inner_backend
        self._directive: tuple[str, ...] = ()
        self.injected: list[tuple[str, ...]] = []  # 审计:每步实际注入的指令(收益溯源)

    def set_directive(self, instructions: tuple[str, ...]) -> None:
        self._directive = tuple(instructions)

    def respond_guided(self, persona, scenario, history, speaker_slot, guidance):
        merged = tuple(self._directive) + tuple(guidance)
        self.injected.append(tuple(self._directive))
        return self._inner.respond_guided(persona, scenario, history, speaker_slot, list(merged))


def triple_of(decision: Decision) -> tuple[str, str | None, dict]:
    """Decision → 旧三元组;trace 原样携带(simple_actio.trace.v2 冻结,V3 §10)。"""
    return decision.to_respond_triple()
