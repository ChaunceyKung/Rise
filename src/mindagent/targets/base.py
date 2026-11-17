"""演化对象(EvolutionTarget)协议与 Delta 基础类型(V3 §4.2;施工规划 M3)。

硬纪律:`apply_candidate` 只产生**可恢复的副本视图**(新的元组/新的对象),
绝不写 skill_library、记忆库或任何正式库——正式写入仍走提案→验证→门②
收录(proposals→verify→admit)。快照带摘要,使"对象版本→行为结果"可追溯。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from mindagent.errors import MindAgentDataError


@dataclass(frozen=True)
class Delta:
    target_kind: str  # 'skill' | 'experience' | 'policy'
    payload: dict     # 目标对象自校验的完整定义(替换或新增,按 id)
    origin: str       # 生成来源标识(如 'rule_template.v1')

    def __post_init__(self):
        if self.target_kind not in ("skill", "experience", "policy"):
            raise MindAgentDataError(f"未知演化对象类别 {self.target_kind}")
        if not isinstance(self.payload, dict) or not self.payload:
            raise MindAgentDataError("Delta.payload 必须是非空字典(完整对象定义)")


@dataclass(frozen=True)
class Snapshot:
    target_kind: str
    items: tuple  # 序列化后的对象元组(排序稳定)
    digest: str

    def count(self) -> int:
        return len(self.items)


@dataclass(frozen=True)
class ValidationResult:
    valid: bool
    reason: str | None = None


@dataclass(frozen=True)
class AppliedCandidate:
    """一次受控应用的结果:新视图 + 变更说明;不落任何正式库。"""

    target_kind: str
    view: tuple            # 应用后的对象元组(如新的 skills)
    changed_ids: tuple[str, ...]
    notes: dict = field(default_factory=dict)


@runtime_checkable
class EvolutionTarget(Protocol):
    kind: str

    def snapshot(self) -> Snapshot: ...
    def validate_delta(self, delta: Delta) -> ValidationResult: ...
    def apply_candidate(self, delta: Delta) -> AppliedCandidate: ...
