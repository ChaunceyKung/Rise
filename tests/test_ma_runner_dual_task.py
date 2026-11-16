"""同模型双任务独立运行 + runner 记账/停止规则(施工规划 M2 验收)。

确定性替身:评价器按候选 id 的轮号给分,无模型调用;同模型(model_ref)
的两个任务先后跑,产物按 task_id+round 寻址互不串扰。
"""
from __future__ import annotations

import re

from mindagent.algorithms.base import Candidate
from mindagent.engine.runner import EvolutionRunner
from mindagent.evaluation.base import CandidateEvaluation
from mindagent.tasks.registry import get
from mindagent.tasks.resolver import resolve
from mindagent.tasks.spec import EvaluationCfg

# noqa 注释集中在文件头;此导入在替身注册前

_ROUND = re.compile(r"r(\d+)")


class _Improving:
    """按轮号线性给分的替身评价器:0.40 + 0.15*轮号。"""

    name = "improving_v1"

    def evaluate(self, task, candidate, agent=None):
        round_no = int(_ROUND.search(candidate.candidate_id).group(1))
        return CandidateEvaluation(candidate_id=candidate.candidate_id,
                                   primary=min(0.95, 0.40 + 0.15 * round_no),
                                   secondary={"round": round_no}, cost={"model_calls": 1})


class _Flat:
    name = "flat_v1"

    def evaluate(self, task, candidate, agent=None):
        return CandidateEvaluation(candidate_id=candidate.candidate_id, primary=0.5, cost={})


# 替身按名注入注册表(spec.evaluation.evaluator 用名寻址)
from mindagent.evaluation.base import register as _reg_eval  # noqa: E402

_reg_eval(_Improving())
_reg_eval(_Flat())


class _TwinCandidates:
    """每轮两个候选:用于压预算上限(2+1=3 次评估后耗尽)。"""

    name = "twin_v1"

    def initialize(self, task, budget):
        from mindagent.algorithms.base import SearchState
        return SearchState(algorithm=self.name, notes={"max_rounds": budget.max_rounds})

    def propose(self, state, feedback):
        n = state.round_no + 1
        return (Candidate(candidate_id=f"twin-r{n}-c1"), Candidate(candidate_id=f"twin-r{n}-c2"))

    def update(self, state, evaluations):
        from mindagent.algorithms.base import SearchState
        best = max(evaluations, key=lambda e: e.primary)
        return SearchState(algorithm=self.name, round_no=state.round_no + 1,
                           best_candidate=best.candidate_id, best_primary=best.primary,
                           notes={**state.notes, "last_improved": True})

    def should_stop(self, state):
        return False


from mindagent.algorithms.base import register as _reg_alg  # noqa: E402

_reg_alg(_TwinCandidates())


def _resolve(task_id, evaluator_name):
    spec = get(task_id)
    spec = type(spec)(**{**spec.__dict__, "evaluation": EvaluationCfg(
        evaluator=evaluator_name, primary_metric=spec.evaluation.primary_metric)})
    return resolve(spec, agent_factory=lambda: "same-model-agent")


def test_two_tasks_on_the_same_model_run_independently():
    sink = []
    runner = EvolutionRunner(sink=lambda task_id, rec: sink.append((task_id, rec.round_no)))
    tom = runner.run_task(_resolve("tom-sim-lite-v1", "improving_v1"))
    coop = runner.run_task(_resolve("cooperation-lite-v1", "flat_v1"))
    # 同一 model_ref、两个任务,各自 >=2 轮,记录按 task_id 完全隔离
    assert len(tom.rounds) >= 2 and len(coop.rounds) >= 2
    assert {t for t, _ in sink} == {"tom-sim-lite-v1", "cooperation-lite-v1"}
    assert all(t == "tom-sim-lite-v1" for t, _ in sink[:len(tom.rounds)])
    # 改善任务到预算上限且 best 在升;平台任务按 max_no_improve 停
    assert tom.stopped_by == "max_rounds"
    assert tom.best_ever == max(r.best_primary for r in tom.rounds)
    assert coop.stopped_by == "max_no_improve"
    # 成本只累计测到的键(缺失不补零)
    assert tom.total_cost == {"model_calls": len(tom.rounds)}
    assert coop.total_cost == {}


def test_metric_target_stops_early_and_records_reason_on_last_round():
    spec = get("tom-sim-lite-v1")
    spec = type(spec)(**{**spec.__dict__, "stop": type(spec.stop)(metric_target=0.55, max_no_improve_rounds=9),
                         "budget": type(spec.budget)(max_rounds=5, max_candidate_evaluations=10),
                         "evaluation": EvaluationCfg(evaluator="improving_v1",
                                                     primary_metric=spec.evaluation.primary_metric)})
    resolved = resolve(spec, agent_factory=lambda: None)
    result = EvolutionRunner().run_task(resolved)
    assert result.stopped_by == "metric_target"
    assert len(result.rounds) < 5
    assert result.rounds[-1].stop_reason == "metric_target"
    assert result.best_ever >= 0.55


def test_budget_exhaustion_is_guarded_before_evaluation():
    spec = get("cooperation-lite-v1")
    spec = type(spec)(**{**spec.__dict__, "budget": type(spec.budget)(max_rounds=5, max_candidate_evaluations=3),
                         "evaluation": EvaluationCfg(evaluator="improving_v1",
                                                     primary_metric=spec.evaluation.primary_metric),
                         "stop": type(spec.stop)(metric_target=None, max_no_improve_rounds=9)})
    # twin 算法经 algorithm_get 注入:EvolutionPlan 的算法词表是 P3 冻结件,不为测试放宽
    resolved = resolve(spec, agent_factory=lambda: None, algorithm_get=lambda name: _TwinCandidates())
    result = EvolutionRunner().run_task(resolved)
    assert result.stopped_by == "budget_exhausted"
    assert sum(len(r.candidates) for r in result.rounds) == 3  # 2 + 1(截断后)即耗尽


def test_round_records_have_stable_wire_digests():
    resolved = _resolve("tom-sim-lite-v1", "improving_v1")
    result = EvolutionRunner().run_task(resolved)
    first = result.rounds[0]
    assert first.wire_digest() == first.wire_digest()
    assert result.to_wire()["task_id"] == "tom-sim-lite-v1"
    assert set(result.rounds[0].to_wire()) == {"task_id", "round_no", "candidates", "best_primary", "cost", "stop_reason"}
