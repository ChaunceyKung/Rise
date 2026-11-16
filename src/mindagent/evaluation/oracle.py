"""oracle 评价 adapter:episode 闭包注入,指标复用 P3 的 measure(V3 M3)。

episode_fn(task, candidate, agent) -> (contract, actions) 是环境接缝:
M3 的确定性测试注入固定 episode;M5 Demo 接 SocialSimulator。
"""
from __future__ import annotations

from mindagent.evaluation.base import CandidateEvaluation
from mindagent.evolution import measure


class OracleEvaluator:
    def __init__(self, name: str, family: str, episode_fn):
        self.name = name
        self._family = family
        self._episode = episode_fn

    def evaluate(self, task, candidate, agent=None) -> CandidateEvaluation:
        contract, actions = self._episode(task, candidate, agent)
        if contract.get("family") != self._family:
            raise ValueError(f"episode 合同 family={contract.get('family')!r} 与评价器 {self._family!r} 不符")
        report = measure(f"oracle:{self._family}", contract, actions)
        regret = report.get("omniscient_regret")
        # 遗憾 → [0,1] 收益:达成即 1.0;全遗憾为 0.0;缺 joint(None)按 0 计并标注
        primary = 1.0 if regret == 0 else (0.0 if regret is None else max(0.0, 1.0 - regret / 10.0))
        return CandidateEvaluation(candidate_id=candidate.candidate_id, primary=primary,
                                   secondary={"joint": report.get("joint_achieved"),
                                              "regret": regret},
                                   cost={})  # 真实模型调用成本由 episode_fn 侧记账(M4 接 Ledger)
