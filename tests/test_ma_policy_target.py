"""V4 A6 验收:policy 演化对象(CAPS 机制权重)的 Delta 闭环与 Runner 纵贯。"""
from __future__ import annotations

import pytest

from mindagent.algorithms.base import Candidate
from mindagent.analysis import BehaviorFinding
from mindagent.engine.runner import EvolutionRunner
from mindagent.errors import MindAgentDataError
from mindagent.evaluation.benchmark import NamedBenchmarkAdapter
from mindagent.evaluation.base import register as reg_eval
from mindagent.tasks.registry import get
from mindagent.tasks.resolver import resolve
from mindagent.tasks.spec import EvaluationCfg
from mindagent.targets.base import Delta
from mindagent.targets.policy_target import PolicyTarget, from_findings
from simple_actio.cognition.persona import PersonaSpec

BASE = PersonaSpec("p-demo", traits={"risk": "averse"},
                   situation_mechanisms={"negotiation": {"goal_driven": 1}})
FINDING = BehaviorFinding(id="f1", signal="emotion_high", pattern="高情绪时直接说理",
                          support=3, ratio=0.5, episode_refs=("e1", "e2", "e3"))


def test_policy_target_delta_round_trip_isolated():
    target = PolicyTarget(BASE)
    before = target.snapshot()
    deltas = from_findings([FINDING], BASE)
    assert len(deltas) == 1 and deltas[0].origin == "signal_weight_v1"
    applied = target.apply_candidate(deltas[0])
    new_spec = applied.view[0]
    assert new_spec.situation_mechanisms["negotiation"] == {"goal_driven": 1, "belief_driven": 2}
    assert new_spec.version == BASE.version + 1
    assert target.persona is BASE and target.snapshot().digest == before.digest  # 副本纪律


def test_policy_target_rejects_foreign_and_identity_changes():
    target = PolicyTarget(BASE)
    foreign = Delta(target_kind="skill", payload={"id": "x"}, origin="t")
    assert target.validate_delta(foreign).valid is False
    bad_id = Delta(target_kind="policy",
                   payload={**BASE.to_wire(), "persona_id": "other"}, origin="t")
    assert "persona_id" in target.validate_delta(bad_id).reason
    with pytest.raises(MindAgentDataError, match="未验证"):
        target.apply_candidate(bad_id)


def test_policy_candidates_complete_an_evolution_loop_via_runner():
    """A6 验收:policy 候选经 TaskSpec→Runner→择优 完成演化闭环。"""
    deltas = from_findings([FINDING], BASE)
    # 评分:belief_driven 权重越高越好(规则替身;真实接 JointGapEvaluator/benchmark)
    adapter = NamedBenchmarkAdapter("caps-weight-demo",
                                    lambda task, candidate, agent=None:
                                    candidate.delta_meta["delta"]["payload"]
                                    ["situation_mechanisms"]["negotiation"]
                                    .get("belief_driven", 0) / 5.0)
    reg_eval(adapter)
    spec = get("tom-sim-lite-v1")
    spec = type(spec)(**{**spec.__dict__,
                         "evaluation": EvaluationCfg(evaluator="benchmark:caps-weight-demo",
                                                     primary_metric="caps_weight"),
                         "budget": type(spec.budget)(max_rounds=2, max_candidate_evaluations=4),
                         "stop": type(spec.stop)(metric_target=None, max_no_improve_rounds=9)})
    from dataclasses import asdict

    arms = tuple(Candidate(candidate_id=f"policy-{i}", delta_meta={"delta": asdict(d)})
                 for i, d in enumerate(deltas))
    arms += (Candidate(candidate_id="policy-base", delta_meta={
        "delta": asdict(Delta(target_kind="policy", payload=BASE.to_wire(), origin="baseline"))}),)

    from mindagent.algorithms.single_candidate import SingleCandidate

    class _AllArms(SingleCandidate):
        name = "manual"

        def propose(self, state, feedback):
            return arms

        def should_stop(self, state):
            return False

    resolved = resolve(spec, agent_factory=lambda: None, algorithm_get=lambda name: _AllArms())
    result = EvolutionRunner().run_task(resolved)
    assert result.best_candidate == "policy-0"          # 权重提升臂胜出
    assert result.best_ever == 2 / 5                    # belief_driven=2
    assert result.stopped_by in ("max_rounds", "budget_exhausted")


def test_named_benchmark_adapter_validates_scores():
    ok = NamedBenchmarkAdapter("x", lambda t, c, a=None: 0.7)
    assert ok.evaluate(None, Candidate(candidate_id="c")).primary == 0.7
    with pytest.raises(MindAgentDataError, match="缺失"):
        NamedBenchmarkAdapter("x", lambda t, c, a=None: None).evaluate(None, Candidate(candidate_id="c"))
    with pytest.raises(MindAgentDataError, match="归一"):
        NamedBenchmarkAdapter("x", lambda t, c, a=None: 7.5).evaluate(None, Candidate(candidate_id="c"))
    with pytest.raises(MindAgentDataError):
        NamedBenchmarkAdapter("", lambda t, c: 0.5)
