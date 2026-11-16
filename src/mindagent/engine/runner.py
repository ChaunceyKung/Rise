"""Evolution Runner:一次任务的编排主循环(初始化→propose→evaluate→update→停止)。

runner 只编排与记账,不含任何能力语义;候选内容、指标、模式全部经
ResolvedTask 注入。轮记录可经 sink 外发(M6 接 ControlPlane 产物),轮内
canonical 摘要复用 simple_actio.core 的受限 JSON 实现。预算纪律:
候选评估次数与轮数都有硬上限;成本缺失键不补零(V3 §5.2)。
"""
from __future__ import annotations

from dataclasses import dataclass, field

import hashlib
import json

from mindagent.errors import MindAgentDataError


def _merge_cost(total: dict, extra: dict) -> None:
    for key, value in extra.items():
        total[key] = total.get(key, 0) + value


@dataclass(frozen=True)
class RoundRecord:
    task_id: str
    round_no: int
    candidates: tuple  # (candidate_id, primary, secondary) 按评估序
    best_primary: float | None
    cost: dict
    stop_reason: str | None = None

    def to_wire(self) -> dict:
        return {"task_id": self.task_id, "round_no": self.round_no,
                "candidates": [{"id": c[0], "primary": c[1], "secondary": c[2]} for c in self.candidates],
                "best_primary": self.best_primary, "cost": dict(self.cost), "stop_reason": self.stop_reason}

    def wire_digest(self) -> str:
        # 运行记录是 Rise 原生产物:primary 是浮点指标,受限 JSON 纪律(actio 合同)
        # 不适用;用标准 JSON 的稳定序列化做摘要。
        return hashlib.sha256(json.dumps(self.to_wire(), sort_keys=True,
                                         ensure_ascii=False, allow_nan=False).encode()).hexdigest()


@dataclass(frozen=True)
class RunResult:
    task_id: str
    rounds: tuple[RoundRecord, ...]
    best_ever: float | None
    best_candidate: str | None
    total_cost: dict = field(default_factory=dict)
    stopped_by: str = ""

    def to_wire(self) -> dict:
        return {"task_id": self.task_id, "rounds": [r.to_wire() for r in self.rounds],
                "best_ever": self.best_ever, "best_candidate": self.best_candidate,
                "total_cost": dict(self.total_cost), "stopped_by": self.stopped_by}


class EvolutionRunner:
    def __init__(self, *, sink=None):
        self._sink = sink  # callable(task_id, RoundRecord) -> None;M6 接调和循环

    def run_task(self, resolved, *, agent=None) -> RunResult:
        spec = resolved.spec
        algorithm, evaluator = resolved.algorithm, resolved.evaluator
        state = algorithm.initialize(spec, spec.budget)
        feedback = None
        records: list[RoundRecord] = []
        total_cost: dict = {}
        evaluations_used = 0
        best_ever: float | None = None
        best_candidate: str | None = None
        no_improve = 0
        stopped_by = ""
        for round_no in range(1, spec.budget.max_rounds + 1):
            candidates = algorithm.propose(state, feedback)
            if not candidates:
                stopped_by = "no_candidates"
                break
            room = spec.budget.max_candidate_evaluations - evaluations_used
            if room <= 0:
                stopped_by = "budget_exhausted"
                break
            batch = candidates[:room]
            scored = []
            for candidate in batch:
                report = evaluator.evaluate(spec, candidate, agent)
                _merge_cost(total_cost, report.cost)
                evaluations_used += 1
                scored.append((candidate.candidate_id, report))
            state = algorithm.update(state, [r for _, r in scored])
            round_best = max(r.primary for _, r in scored)
            round_best_id = max(scored, key=lambda pair: pair[1].primary)[0]
            improved = best_ever is None or round_best > best_ever
            if improved:
                best_ever, best_candidate, no_improve = round_best, round_best_id, 0
            else:
                no_improve += 1
            record = RoundRecord(task_id=spec.task_id, round_no=round_no,
                                 candidates=tuple((cid, r.primary, dict(r.secondary)) for cid, r in scored),
                                 best_primary=round_best, cost=dict(total_cost))
            records.append(record)
            if self._sink is not None:
                self._sink(spec.task_id, record)
            feedback = scored
            if spec.stop.metric_target is not None and best_ever >= spec.stop.metric_target:
                stopped_by = "metric_target"
                break
            if no_improve >= spec.stop.max_no_improve_rounds:
                stopped_by = "max_no_improve"
                break
            if algorithm.should_stop(state):
                stopped_by = "algorithm_stop"
                break
        else:
            stopped_by = stopped_by or "max_rounds"
        if not records:
            raise MindAgentDataError(f"任务 {spec.task_id} 一轮都没跑:{stopped_by}")
        last = RoundRecord(**{**records[-1].__dict__, "stop_reason": stopped_by})
        records[-1] = last
        return RunResult(task_id=spec.task_id, rounds=tuple(records), best_ever=best_ever,
                         best_candidate=best_candidate, total_cost=total_cost, stopped_by=stopped_by)
