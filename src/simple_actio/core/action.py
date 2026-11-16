"""模式化决策与三元组映射:Decision 是新模式的上层输出,respond() 三元组保持冻结(V3 §10)。"""
from __future__ import annotations

from dataclasses import dataclass

MODES = ("inner", "outer")


@dataclass(frozen=True)
class Decision:
    mode: str
    utterance: str
    inner_thought: str | None
    directive: tuple[str, ...]
    mechanisms: tuple[str, ...]
    trace: dict  # 仍是 simple_actio.trace.v2,由底层实例产出,Decision 只携带

    def __post_init__(self):
        if self.mode not in MODES:
            raise ValueError(f"未知模式 {self.mode};可选 {MODES}")
        if not isinstance(self.utterance, str) or not self.utterance:
            raise ValueError("utterance 必须是非空字符串")
        if not self.directive:
            raise ValueError("Decision 必须携带触发的指导语指令(演化收益非路由变化的证据链)")

    def to_respond_triple(self) -> tuple[str, str | None, dict]:
        """映射回 SimpleActio/SocialSimulator 的 (utterance, inner_thought, trace) 三元组。"""
        return self.utterance, self.inner_thought, self.trace
