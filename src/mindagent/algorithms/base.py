"""演化算法协议与注册表(V3 §5.3;M2 只带最简实现,其余 M3 落)。

四独立维度(V3 §4.4):能力由 spec 定,对象由 target 定,算法只管搜索,
评估器只判改善。算法不写正式对象——apply 只发生在可恢复副本上(M3 target)。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from mindagent.errors import MindAgentDataError


@dataclass(frozen=True)
class Candidate:
    """一轮的一个候选:对演化对象的一次提议变更(内容对 runner 不透明)。"""

    candidate_id: str
    delta_meta: dict = field(default_factory=dict)


@dataclass(frozen=True)
class SearchState:
    """算法跨轮状态(可序列化快照;具体字段由算法自定)。"""

    algorithm: str
    round_no: int = 0
    best_candidate: str | None = None
    best_primary: float | None = None
    notes: dict = field(default_factory=dict)


@runtime_checkable
class EvolutionAlgorithm(Protocol):
    name: str

    def initialize(self, task, budget) -> SearchState: ...
    def propose(self, state, feedback) -> tuple[Candidate, ...]: ...
    def update(self, state, evaluations) -> SearchState: ...
    def should_stop(self, state) -> bool: ...


_REGISTRY: dict[str, EvolutionAlgorithm] = {}


def register(algorithm: EvolutionAlgorithm) -> None:
    _REGISTRY[algorithm.name] = algorithm


def get(name: str) -> EvolutionAlgorithm:
    if name not in _REGISTRY:
        raise MindAgentDataError(f"未知演化算法 {name};已注册: {sorted(_REGISTRY)}")
    return _REGISTRY[name]
