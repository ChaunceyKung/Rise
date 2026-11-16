"""脚本化内置评价器:M2 纵贯 Demo 用,分数取候选 delta_meta['score_hint']。"""
from __future__ import annotations

from mindagent.evaluation.base import CandidateEvaluation


class ScriptedEvaluator:
    def __init__(self, name: str, default: float):
        self.name = name
        self._default = default

    def evaluate(self, task, candidate, agent=None) -> CandidateEvaluation:
        hint = candidate.delta_meta.get("score_hint", self._default)
        return CandidateEvaluation(candidate_id=candidate.candidate_id, primary=float(hint),
                                   cost={"model_calls": 0})  # 脚本路径零模型调用;真实成本 M3 接 Ledger


def _builtin() -> None:
    from mindagent.evaluation.base import register

    register(ScriptedEvaluator("scripted_belief_v1", default=0.5))
    register(ScriptedEvaluator("scripted_coop_v1", default=0.4))


_builtin()
