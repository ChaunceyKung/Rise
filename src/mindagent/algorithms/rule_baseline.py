"""Rule Baseline 算法:每轮从 findings 经规则模板产 Delta,单轮基线即停(V3 §4.4)。"""
from __future__ import annotations

from dataclasses import asdict

from mindagent.algorithms.base import Candidate, SearchState


class RuleBaseline:
    """确定性基线:候选 = 目标对象翻译层产出的规则 Delta,一个不多。"""

    name = "rule_baseline_v1"

    def __init__(self, delta_proposer):
        self._propose_deltas = delta_proposer  # callable(feedback) -> tuple[Delta, ...]

    def initialize(self, task, budget) -> SearchState:
        return SearchState(algorithm=self.name, notes={"max_rounds": budget.max_rounds})

    def propose(self, state, feedback) -> tuple[Candidate, ...]:
        if state.round_no >= 1:
            return ()  # 基线只跑一轮
        return tuple(Candidate(candidate_id=f"{self.name}-r1-{i+1}",
                               delta_meta={"delta": asdict(delta)})
                     for i, delta in enumerate(self._propose_deltas(feedback)))

    def update(self, state, evaluations) -> SearchState:
        best = max(evaluations, key=lambda e: e.primary)
        improved = state.best_primary is None or best.primary > state.best_primary
        ever = best.primary if state.best_primary is None else max(state.best_primary, best.primary)
        return SearchState(algorithm=self.name, round_no=state.round_no + 1,
                           best_candidate=best.candidate_id if improved else state.best_candidate,
                           best_primary=ever, notes={**state.notes, "last_improved": improved})

    def should_stop(self, state) -> bool:
        return state.round_no >= 1
