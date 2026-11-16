"""能力评价协议与注册表(V3 §4.2;M2 带协议+脚本化内置,M3 接 oracle/diag 真实现)。

成本纪律(V3 §5.2):不知道的量**缺失表示,不填 0**;EvaluationReport.cost 只含
实际测到的键,runner 汇总时跳过缺失。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from mindagent.errors import MindAgentDataError


@dataclass(frozen=True)
class CandidateEvaluation:
    candidate_id: str
    primary: float
    secondary: dict = field(default_factory=dict)
    cost: dict = field(default_factory=dict)  # 例: {"model_calls": 1, "input_tokens": 128};未知则缺

    def __post_init__(self):
        if not 0.0 <= self.primary <= 1.0:
            raise MindAgentDataError("primary 指标按约定归一到 [0,1]")


@runtime_checkable
class CapabilityEvaluator(Protocol):
    name: str

    def evaluate(self, task, candidate, agent=None) -> CandidateEvaluation: ...


_REGISTRY: dict[str, CapabilityEvaluator] = {}


def register(evaluator: CapabilityEvaluator) -> None:
    _REGISTRY[evaluator.name] = evaluator


def get(name: str) -> CapabilityEvaluator:
    if name not in _REGISTRY:
        raise MindAgentDataError(f"未知评价器 {name};已注册: {sorted(_REGISTRY)}")
    return _REGISTRY[name]
