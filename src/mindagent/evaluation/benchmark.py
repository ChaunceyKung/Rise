"""Benchmark 接入留缝(V4 A6,Q2:不引入外部依赖)。

PersonaMem/RealPref 等外部基准按此协议接入:实现方自己拉数据/跑题,
返回 [0,1] 的 primary;适配器只管注册与命名。不装任何数据集依赖。
"""
from __future__ import annotations

from typing import Callable, Protocol, runtime_checkable

from mindagent.errors import MindAgentDataError
from mindagent.evaluation.base import CandidateEvaluation


@runtime_checkable
class BenchmarkAdapter(Protocol):
    benchmark: str  # 如 "personamem-v1"

    def evaluate(self, task, candidate, agent=None) -> CandidateEvaluation: ...


class NamedBenchmarkAdapter:
    """把 (基准名, 评分函数) 包成注册表可用的评价器。

    score_fn(task, candidate, agent) -> float ∈ [0,1];未归一/缺失显式拒。
    """

    def __init__(self, benchmark: str, score_fn: Callable):
        if not benchmark or not callable(score_fn):
            raise MindAgentDataError("benchmark 名与评分函数都不可为空")
        self.benchmark = benchmark
        self.name = f"benchmark:{benchmark}"
        self._score = score_fn

    def evaluate(self, task, candidate, agent=None) -> CandidateEvaluation:
        score = self._score(task, candidate, agent)
        if score is None:
            raise MindAgentDataError(f"基准 {self.benchmark} 缺失得分;不冒充 0")
        if not 0.0 <= score <= 1.0:
            raise MindAgentDataError(f"基准 {self.benchmark} 得分 {score} 未归一到 [0,1]")
        return CandidateEvaluation(candidate_id=candidate.candidate_id, primary=float(score),
                                   secondary={"benchmark": self.benchmark}, cost={})
