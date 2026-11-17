"""V4 A3 验收:HumanModel 四分离、RuleEstimator 单调更新、澄清/行动双路径、
DecisionRecord 引用可回查。"""
from __future__ import annotations

import pytest

from simulator.datamodel import Persona, RoleSlot, Scenario, TurnRecord
from simple_actio.adapters.legacy import ModeDirectiveBackend
from simple_actio.core.observation import PerceivedObservation
from simple_actio.core.policy import CombinedPolicy
from simple_actio.core.record import DecisionRecord
from simple_actio.instance import instantiate
from simple_actio.inner.human_policy import GoalDriven
from simple_actio.memory import TupleMemory
from simple_actio.outer.agent import OuterAgent
from simple_actio.outer.decision_policy import ClarificationPolicy, HumanAwareDecisionPolicy
from simple_actio.outer.human_model import Hypothesis, HumanModel
from simple_actio.outer.state_estimator import RuleEstimator


def _obs(text, visible=()):
    return PerceivedObservation.from_world({"公开": "x", "隐藏": "h"}, set(visible),
                                           speaker="bob", utterance=text)


def test_human_model_wire_top_and_uncertainty():
    model = HumanModel(person_id="bob", facts=("bob 提出过方案:morning",),
                       hypotheses=(Hypothesis("对方倾向于合作", 0.9, ("turn1:bob:同意",)),
                                   Hypothesis("对方偏好上午", 0.6, ("turn0:bob:上午",))))
    again = HumanModel.from_wire(model.to_wire())
    assert again == model
    assert model.top(limit=1)[0].statement == "对方倾向于合作"
    assert model.uncertainty() == pytest.approx(0.1)
    assert HumanModel(person_id="x").uncertainty() == 1.0  # 完全未知
    with pytest.raises(ValueError):
        Hypothesis("x", 1.5)


def test_rule_estimator_is_monotonic_and_kinds_facts_from_hypotheses():
    est = RuleEstimator()
    model = HumanModel(person_id="bob")
    first = est.update(model, _obs("我同意上午的方案"), turn=1)
    assert first.hypotheses[0].statement == "对方倾向于合作"
    assert first.hypotheses[0].confidence == pytest.approx(0.5)
    second = est.update(first, _obs("这样可以,接受"), turn=2)
    boosted = [h for h in second.hypotheses if h.statement == "对方倾向于合作"][0]
    assert boosted.confidence == pytest.approx(0.7)  # 单调递增
    assert boosted.evidence[-1].startswith("turn2:bob:")
    third = est.update(second, _obs("我提议另一个方案"), turn=3)
    assert any(f.startswith("bob 提出过方案") for f in third.facts)  # 提案→事实
    reserved = [h for h in third.hypotheses if h.statement == "对方对当前方案持保留"]
    assert not reserved  # 无冲突词不产生保留假设


def test_clarification_and_act_paths_by_uncertainty():
    policy = HumanAwareDecisionPolicy(objectives=("完成清理",))
    blank = policy.decide(HumanModel(person_id="b"), _obs("嗯"))
    assert blank.parameters["kind"] == "clarify" and blank.skill_ref == "clarification-v1"
    confident = HumanModel(person_id="b", hypotheses=(Hypothesis("对方倾向于合作", 0.9),))
    acting = policy.decide(confident, _obs("那我们开工吧"))
    assert acting.parameters["kind"] == "act"
    assert acting.parameters["top_hypothesis"] == "对方倾向于合作"
    assert any(d.startswith("以任务目标为先") for d in acting.parameters["directives"])
    # 阈值可调:高阈值下,中等不确定(0.9)不再触发澄清;空模型(不确定=1.0)仍会
    strict = HumanAwareDecisionPolicy(objectives=("x",), clarify=ClarificationPolicy(threshold=0.95))
    mid = HumanModel(person_id="b", hypotheses=(Hypothesis("对方倾向于合作", 0.1),))
    assert strict.decide(mid, _obs("嗯")).parameters["kind"] == "act"
    assert strict.decide(HumanModel(person_id="b"), _obs("嗯")).parameters["kind"] == "clarify"


def test_decision_record_validates_references_and_levels():
    with pytest.raises(ValueError, match="alternatives"):
        DecisionRecord(selected="act", alternatives_considered=("clarify",))  # act 不在备选
    with pytest.raises(ValueError):
        DecisionRecord(selected="act", alternatives_considered=("act",), evidence_level="guessed")
    record = DecisionRecord(selected="clarify", goal_refs=("理解意图",),
                            belief_refs=("对方倾向于合作",), skill_ref="clarification-v1",
                            alternatives_considered=("clarify", "act"))
    wire = record.to_wire()
    assert wire["evidence_level"] == "structurally_derived" and wire["selected"] == "clarify"


class _Echo:
    def respond_guided(self, persona, scenario, history, speaker_slot, guidance):
        return ("|".join(guidance) or "plain", None)


def _outer():
    instance = instantiate(ModeDirectiveBackend(_Echo()), skills=[],
                           memory=TupleMemory(()).world("assistant"),
                           library_version={"skill": "0", "memory": "0"}, profile=None,
                           episode_id="ep", holder="assistant")
    return OuterAgent(instance, CombinedPolicy((GoalDriven(goals=("完成清理",)),)),
                      subject="assistant", estimator=RuleEstimator(),
                      decision=HumanAwareDecisionPolicy(objectives=("完成清理",)),
                      person_id="bob")


def _step(agent, text):
    return agent.decide_for_human(_obs(text), Persona("p", ["t"], "m", "s", ["v"]),
                                  Scenario("s", "b", [RoleSlot("a", "a")], "c", ["n"], "training"),
                                  [TurnRecord(0, "b", text)], "a")


def test_outer_agent_e2e_uncertain_first_then_confident_act():
    agent = _outer()
    first = _step(agent, "嗯……")  # 无信号 → 完全未知 → 澄清
    assert first.mechanisms == ("clarify",)
    record = first.rationale_summary
    assert record["selected"] == "clarify" and record["alternatives_considered"] == ["clarify", "act"]
    assert agent.last_trace.rationale == record
    # 证据链两轮后转向行动,引用可回查
    _step(agent, "我同意上午的方案")
    _step(agent, "这样可以,接受")
    acting = _step(agent, "那就开工吧")
    assert acting.mechanisms == ("act",)
    top_statement = agent.human_model.top(limit=1)[0].statement
    assert acting.rationale_summary["belief_refs"][0] == top_statement  # 引用回查到估计
    assert top_statement == "对方倾向于合作"
    assert agent.human_model.top(limit=1)[0].confidence == pytest.approx(0.7)  # 两次提升 0.5→0.7;封顶 0.9 未及
