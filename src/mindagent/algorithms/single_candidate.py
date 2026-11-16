"""Single Candidate(V3 §4.4 基础算法):每轮恰好一个候选,首轮无改善即停。"""
from __future__ import annotations

from mindagent.algorithms.base import Candidate, SearchState


class SingleCandidate:
    name = "single_candidate_v1"

    def initialize(self, task, budget) -> SearchState:
        return SearchState(algorithm=self.name, notes={"max_rounds": budget.max_rounds})

    def propose(self, state, feedback) -> tuple[Candidate, ...]:
        return (Candidate(candidate_id=f"{state.algorithm}-r{state.round_no + 1}-c1"),)

    def update(self, state, evaluations) -> SearchState:
        round_best = max(evaluations, key=lambda e: e.primary)
        improved = state.best_primary is None or round_best.primary > state.best_primary
        ever = round_best.primary if state.best_primary is None else max(state.best_primary, round_best.primary)
        return SearchState(algorithm=self.name, round_no=state.round_no + 1,
                           best_candidate=round_best.candidate_id if improved else state.best_candidate,
                           best_primary=ever,
                           notes={**state.notes, "last_improved": improved})

    def should_stop(self, state) -> bool:
        return state.round_no >= 1 and state.notes.get("last_improved") is False
