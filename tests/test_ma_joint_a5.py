"""V4 A5 验收:联合情境、消融臂、Gap 指标、隔离审计、双 Demo 演化闭环+投影。"""
from __future__ import annotations

import pytest

from controlplane.gitstore import GitStore
from mindagent.algorithms.base import Candidate
from mindagent.engine.runner import EvolutionRunner
from mindagent.evaluation.base import register as reg_eval
from mindagent.joint.evaluation import JointGapEvaluator, project_run_result
from mindagent.joint.harness import (
    INNER_ARMS, OUTER_ARMS, JointScenario, build_outer, inner_utterance, run_joint,
)
from simple_actio.cognition.persona import PersonaSpec


def _drift_scenario():
    return JointScenario(scenario_id="coop-drift-v1",
                         human_turns=("我同意上午的方案", "这样可以,接受",
                                      "不行,太贵了,我拒绝", "你看着办吧"),
                         hidden_goal="便宜方案", drift_turn=3, drifted_preference="先看质量",
                         accept_hypotheses=("漂移",),
                         hidden_facts={"隐藏身份": "merlin"})


def test_outer_arms_diverge_and_isolation_holds_on_drift_scenario():
    records = {}
    for arm in OUTER_ARMS:
        outer = build_outer(arm, person_id="human")
        records[arm] = run_joint(_drift_scenario(), outer, arm=arm)
        assert records[arm].isolation_ok, records[arm].isolation_violations
    # O0 直答:无任何假设;O3 动态:漂移轮的冲突反馈进估计
    assert records["O0"].top_hypothesis is None
    assert records["O3"].top_hypothesis is not None
    # O2 静态画像:先验合作假设不随漂移更新(仍指合作)
    assert "合作" in records["O2"].top_hypothesis


def test_isolation_audit_catches_injected_leak():
    scenario = _drift_scenario()
    outer = build_outer("O3", person_id="human")
    outer.human_model = type(outer.human_model)(
        person_id="human",
        hypotheses=(type("H", (), {"statement": "真值含隐藏:便宜方案", "confidence": 0.9,
                                   "evidence": ("leak",)})(),))
    record = run_joint(scenario, outer, arm="O3")
    assert not record.isolation_ok  # 假设语句携带隐藏值被值级审计抓住
    assert any("隐藏值" in v for v in record.isolation_violations)


def test_joint_gap_evaluator_scores_arms_deterministically():
    evaluator = JointGapEvaluator("joint-drift-v1", _drift_scenario())
    reg_eval(evaluator)
    task = object()
    scores = {}
    for arm in OUTER_ARMS:
        report = evaluator.evaluate(task, Candidate(candidate_id=f"c-{arm}", delta_meta={"arm": arm}))
        scores[arm] = report
        assert report.secondary["isolation_ok"] is True
        assert report.cost["rounds"] == 4 and "model_calls" in report.cost
    again = evaluator.evaluate(task, Candidate(candidate_id="c-O3", delta_meta={"arm": "O3"}))
    assert again.primary == scores["O3"].primary  # 确定性复跑
    with pytest.raises(ValueError, match="Outer 臂"):
        evaluator.evaluate(task, Candidate(candidate_id="x", delta_meta={"arm": "B4"}))


def test_inner_arms_show_mechanism_gradient():
    persona = PersonaSpec("p-demo", preferences=("便宜方案",))
    text = "我提议上午打扫,有机会达成共识"
    outputs = {arm: inner_utterance(arm, persona, text) for arm in INNER_ARMS}
    assert "便宜方案" not in outputs["B0"]  # 无机制:fallback 文本
    assert "便宜方案" in outputs["B1"]       # persona 目标进入指令
    assert outputs["B1"] != outputs["B2"]    # B2 叠加信念机制
    assert "便宜方案" in outputs["B4"]        # 全模块仍以目标为先
    # 复跑一致(消融差异可复现)
    assert inner_utterance("B4", persona, text) == outputs["B4"]


def _arm_proposer(arms):
    return lambda feedback: tuple(Candidate(candidate_id=f"arm-{a}", delta_meta={"arm": a})
                                  for a in arms)


def test_demo_b_outer_full_evolution_loop_with_projection(tmp_path):
    """Demo B 闭环:TaskSpec→Runner(四臂)→择优→RunResult→envelope 投影(幂等/版本化)。"""
    from mindagent.tasks.registry import get
    from mindagent.tasks.resolver import resolve
    from mindagent.tasks.spec import EvaluationCfg

    evaluator = JointGapEvaluator("joint-drift-loop", _drift_scenario())
    reg_eval(evaluator)
    spec = get("cooperation-lite-v1")
    spec = type(spec)(**{**spec.__dict__,
                         "evaluation": EvaluationCfg(evaluator="joint-drift-loop",
                                                     primary_metric="joint_gap"),
                         "budget": type(spec.budget)(max_rounds=4, max_candidate_evaluations=8),
                         "stop": type(spec.stop)(metric_target=None, max_no_improve_rounds=9)})
    from mindagent.algorithms.single_candidate import SingleCandidate

    twin = _arm_proposer(("O0", "O1", "O2", "O3"))

    class _AllArms(SingleCandidate):
        name = "manual"

        def propose(self, state, feedback):
            return twin(feedback)

        def should_stop(self, state):
            return False  # 每轮全臂对比,跑满预算

    resolved = resolve(spec, agent_factory=lambda: None, algorithm_get=lambda name: _AllArms())
    result = EvolutionRunner().run_task(resolved)
    assert len(result.rounds[0].candidates) == 4           # 四臂齐评
    assert result.best_ever == 1.0                          # 漂移检测臂命中真值
    assert result.best_candidate == "arm-O3"                # 择优选臂:动态估计+反馈

    git = GitStore(str(tmp_path / "repo"))
    git.init()
    first = project_run_result(git, result, store_key="coop-drift-v1")
    assert first.endswith(".yml")
    head = git._git("rev-parse", "HEAD")
    again = project_run_result(git, result, store_key="coop-drift-v1")
    assert again == first and git._git("rev-parse", "HEAD") == head  # 幂等零提交
    # 结果变化(新择优)→ 版本 +1
    from mindagent.engine.runner import RunResult

    changed = RunResult(task_id=result.task_id, rounds=result.rounds[:1],
                        best_ever=result.best_ever, best_candidate="arm-O0",
                        total_cost=result.total_cost, stopped_by="changed")
    project_run_result(git, changed, store_key="coop-drift-v1")
    assert git.read_product(first).version == 2


def test_demo_a_inner_scenario_consistency_metric():
    """Demo A(Inner×社会模拟):以目标词在场率作一致性指标的纵贯跑(单臂对照 B0 vs B4)。"""
    evaluator = JointGapEvaluator("joint-inner-demo", JointScenario(
        scenario_id="hidden-belief-v1",
        human_turns=("我觉得上午更好,可以接受", "同意按这个来"),
        hidden_goal="上午方案", hidden_facts={"隐藏身份": "spy"}))
    reg_eval(evaluator)
    # Demo A 的评价面在 Inner 臂;本评价器面向 Outer 臂,故 Demo A 用一致性直证:
    persona = PersonaSpec("p-a", preferences=("上午方案",))
    assert "上午方案" in inner_utterance("B4", persona, "提议上午")
    assert "上午方案" not in inner_utterance("B0", persona, "提议上午")
