"""diag 评价 adapter:包装 recipestore.compute_gain(V3 M3)。

gain_fn(task, candidate) -> float | None 由调用方注入(内部自行组装
GitStore/run 维度);未归一到 [0,1] 的增益显式拒绝,不静默夹逼。
"""
from __future__ import annotations

from mindagent.errors import MindAgentDataError
from mindagent.evaluation.base import CandidateEvaluation


class DiagGainEvaluator:
    def __init__(self, name: str, gain_fn):
        self.name = name
        self._gain = gain_fn

    def evaluate(self, task, candidate, agent=None) -> CandidateEvaluation:
        gain = self._gain(task, candidate)
        if gain is None:
            raise MindAgentDataError("diag 增益缺失(基线报告不在或不可比);缺失不冒充 0")
        if not 0.0 <= gain <= 1.0:
            raise MindAgentDataError(f"diag 增益 {gain} 未归一到 [0,1];请先定义归一化再入评价")
        return CandidateEvaluation(candidate_id=candidate.candidate_id, primary=gain, cost={})
