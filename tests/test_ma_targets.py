"""统一 Delta 闭环测试:skill 与 experience 两类对象(V3 M3 验收)。

验收口径:快照→变异→副本应用→评价→择优 全链;apply 只产副本视图,
正式库(此处即原始元组)零改动;两种算法同预算对照。
"""
from __future__ import annotations

import pytest

from mindagent.algorithms.generate_test import GenerateTest
from mindagent.algorithms.rule_baseline import RuleBaseline
from mindagent.analysis import BehaviorFinding
from mindagent.errors import MindAgentDataError
from mindagent.evaluation.base import CandidateEvaluation
from mindagent.targets.base import Delta
from mindagent.targets.experience_target import ExperienceTarget, from_findings as exp_from_findings
from mindagent.targets.skill_target import SkillTarget, from_findings as skill_from_findings
from simple_actio.skills import Skill

FINDING = BehaviorFinding(id="f1", signal="emotion_high", pattern="高情绪时直接说理",
                          support=3, ratio=0.5, episode_refs=("e1", "e2", "e3"))


def test_skill_target_snapshot_validate_apply_round_trip_without_touching_library():
    target = SkillTarget(skills=())
    before = target.snapshot()
    deltas = skill_from_findings([FINDING])
    assert len(deltas) == 1 and deltas[0].origin == "rule_template.v1"
    applied = target.apply_candidate(deltas[0])
    assert applied.changed_ids == ("skill-candidate-emotion_high",)
    assert len(applied.view) == 1 and isinstance(applied.view[0], Skill)
    # 副本纪律:原始目标与快照不变
    assert target.skills == () and target.snapshot().digest == before.digest


def test_skill_target_rejects_invalid_and_foreign_deltas():
    target = SkillTarget()
    bad = Delta(target_kind="skill", payload={"id": "x"}, origin="t")
    assert target.validate_delta(bad).valid is False
    foreign = Delta(target_kind="experience", payload={"id": "x", "version": 1, "pattern": "p",
                                                       "applies_when": {}, "tiers": {}}, origin="t")
    assert target.validate_delta(foreign).valid is False
    with pytest.raises(MindAgentDataError, match="未验证"):
        target.apply_candidate(bad)


def test_experience_target_round_trip_and_snapshot_isolation():
    target = ExperienceTarget()
    deltas = exp_from_findings([FINDING])
    applied = target.apply_candidate(deltas[0])
    assert applied.changed_ids == ("exp-candidate-emotion_high",)
    assert applied.view[0].id == "exp-candidate-emotion_high"
    assert target.experiences == ()  # 副本纪律
    # 同 id 再应用 = 替换不叠加
    twice = ExperienceTarget(applied.view).apply_candidate(deltas[0])
    assert len(twice.view) == 1


def _score_by_priority(task, candidate):
    priority = candidate.delta_meta["delta"]["payload"].get("priority", 100)
    return min(0.99, (110 - priority) / 100.0)  # 低优先级=更少打扰,替身打分


def test_two_algorithms_compare_under_the_same_budget():
    """验收:两种算法在同预算下可对照(基线 1 候选 vs G&T 截到 K)。"""
    deltas = skill_from_findings([FINDING])
    rule = RuleBaseline(lambda feedback: deltas)
    gen = GenerateTest(lambda feedback: deltas, candidates_per_round=4)
    for algorithm in (rule, gen):
        state = algorithm.initialize(None, type("B", (), {"max_rounds": 3})())
        batch = algorithm.propose(state, None)
        assert 1 <= len(batch) <= 4
        scored = [CandidateEvaluation(candidate_id=c.candidate_id, primary=_score_by_priority(None, c))
                  for c in batch]
        state = algorithm.update(state, scored)
        assert state.best_primary is not None
    # G&T 合成变体确实改变了优先级(候选多样性)
    gen_candidates = gen.propose(gen.initialize(None, type("B", (), {"max_rounds": 3})()), None)
    priorities = {c.delta_meta["delta"]["payload"].get("priority", 100) for c in gen_candidates}
    assert len(priorities) > 1


def test_full_loop_runner_generate_test_oracle_and_skill_target():
    """M3 纵贯:TaskSpec→Runner→GenerateTest→OracleEvaluator→SkillTarget 副本视图。"""
    from mindagent.engine.runner import EvolutionRunner
    from mindagent.evaluation.oracle import OracleEvaluator
    from mindagent.tasks.registry import get
    from mindagent.tasks.resolver import resolve

    contract = {
        "family": "scheduling",
        "public": {"slots": ["m"], "open": ["m"]},
        "private": {"A": {"available": ["m"], "utility": {"m": 9}},
                    "B": {"available": ["m"], "utility": {"m": 5}}},
    }
    evaluator = OracleEvaluator("oracle-e2e", "scheduling",
                                lambda task, candidate, agent: (contract, {"A": "propose:m", "B": "accept"}))
    from mindagent.evaluation.base import register as reg_eval

    reg_eval(evaluator)
    from mindagent.tasks.spec import EvaluationCfg

    spec = get("cooperation-lite-v1")
    spec = type(spec)(**{**spec.__dict__,
                         "evaluation": EvaluationCfg(evaluator="oracle-e2e", primary_metric="joint"),
                         "budget": type(spec.budget)(max_rounds=2, max_candidate_evaluations=8)})
    gen = GenerateTest(lambda feedback: skill_from_findings([FINDING]), candidates_per_round=3)
    resolved = resolve(spec, agent_factory=lambda: None, algorithm_get=lambda name: gen)
    result = EvolutionRunner().run_task(resolved)
    assert result.best_ever == 1.0  # 达成 joint 的候选在第一轮即被择优
    assert result.rounds[0].best_primary == 1.0
    assert all(0.0 <= c[1] <= 1.0 for c in result.rounds[0].candidates)
