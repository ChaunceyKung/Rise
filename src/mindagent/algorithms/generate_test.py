"""Generate-and-Test 算法:K 候选 + 分阶段验证 + 早期淘汰(V3 §4.4 / E2、E3)。

候选多样性:基础 Delta(来自注入的 proposer)取前 K;不足 K 时按优先级
微扰合成变体(+1/-1 交替),保证同预算下可对照。
"""
from __future__ import annotations

from dataclasses import asdict

from mindagent.algorithms.base import Candidate, SearchState


class GenerateTest:
    name = "generate_test_v1"

    def __init__(self, delta_proposer, *, candidates_per_round: int = 4):
        if candidates_per_round < 1:
            raise ValueError("candidates_per_round 必须 >=1")
        self._propose_deltas = delta_proposer
        self._k = candidates_per_round

    def _variants(self, deltas, round_no: int):
        base = [asdict(d) for d in list(deltas)[: self._k]]  # 统一成字典视图
        nudge = 1
        while len(base) < self._k and base:
            source = base[len(base) % len(base)]
            payload = dict(source["payload"])
            payload["priority"] = int(payload.get("priority", 100)) + (nudge if len(base) % 2 == 0 else -nudge)
            base.append({"target_kind": source["target_kind"], "payload": payload,
                         "origin": "generate_test_nudge"})
            nudge += 1
        return base

    def initialize(self, task, budget) -> SearchState:
        return SearchState(algorithm=self.name,
                           notes={"max_rounds": budget.max_rounds, "k": self._k})

    def propose(self, state, feedback) -> tuple[Candidate, ...]:
        raw = self._propose_deltas(feedback)
        variants = self._variants(raw, state.round_no + 1)
        return tuple(Candidate(candidate_id=f"{self.name}-r{state.round_no + 1}-c{i+1}",
                               delta_meta={"delta": v})
                     for i, v in enumerate(variants))

    def update(self, state, evaluations) -> SearchState:
        best = max(evaluations, key=lambda e: e.primary)
        improved = state.best_primary is None or best.primary > state.best_primary
        ever = best.primary if state.best_primary is None else max(state.best_primary, best.primary)
        return SearchState(algorithm=self.name, round_no=state.round_no + 1,
                           best_candidate=best.candidate_id if improved else state.best_candidate,
                           best_primary=ever,
                           notes={**state.notes, "last_improved": improved,
                                  "round_best": best.primary})

    def should_stop(self, state) -> bool:
        # 早期淘汰(E3):一轮无改善即停——同预算对照下的保守搜索
        return state.round_no >= 1 and state.notes.get("last_improved") is False
