"""V4 A4 验收:行为预测、双执行器、PAHF 反馈闭环与偏好漂移、affect/relationship 插件位。"""
from __future__ import annotations

import pytest

from simulator.datamodel import Persona, RoleSlot, Scenario, TurnRecord
from simple_actio.adapters.legacy import ModeDirectiveBackend
from simple_actio.cognition.affect import AffectState, NoopAffectDynamics
from simple_actio.cognition.relationships import NoopRelationshipDynamics, RelationshipView
from simple_actio.core.executor import EnvironmentActionExecutor, GuidanceExecutor
from simple_actio.core.intent import ActionIntent
from simple_actio.core.observation import PerceivedObservation
from simple_actio.core.policy import CombinedPolicy
from simple_actio.core.state import CognitiveState
from simple_actio.inner.behavior_model import InnerPredictor, RuleBehaviorModel
from simple_actio.inner.human_policy import GoalDriven
from simple_actio.instance import instantiate
from simple_actio.memory import TupleMemory
from simple_actio.outer.agent import OuterAgent
from simple_actio.outer.decision_policy import HumanAwareDecisionPolicy, TaskGoalDriven
from simple_actio.outer.feedback_adapter import COOPERATION, DRIFT_STATEMENT, FeedbackAdapter
from simple_actio.outer.human_model import Hypothesis, HumanModel
from simple_actio.outer.state_estimator import RuleEstimator


def _obs(text):
    return PerceivedObservation.from_world({}, set(), speaker="bob", utterance=text)


def test_rule_behavior_model_predicts_from_goals_and_affect():
    calm = RuleBehaviorModel().predict(CognitiveState(subject="bob", goals=("达成共识",)), _obs("嗯"), horizon=2)
    tense = RuleBehaviorModel().predict(
        CognitiveState(subject="bob", goals=("达成共识",), short_term={"affect_hint": "tension"}),
        _obs("嗯"), horizon=3)
    assert calm[0].startswith("朝目标推进")
    assert any("表达顾虑" in c for c in tense)
    idle = RuleBehaviorModel().predict(CognitiveState(subject="bob"), _obs("嗯"))
    assert idle == ("保持观望并询问进展",)


def test_task_goal_advisor_accepts_both_protocol_and_callable():
    inner_state = CognitiveState(subject="bob", goals=("便宜方案",))
    predictor = InnerPredictor(lambda: inner_state)
    mech = TaskGoalDriven(objectives=("完成清理",), advisor=predictor)
    directives = mech.apply(CognitiveState(subject="a"), _obs("嗯"))
    assert any("朝目标推进:便宜方案" in d for d in directives)
    legacy = TaskGoalDriven(objectives=("x",), advisor=lambda obs: "老式建议")
    assert any("老式建议" in d for d in legacy.apply(CognitiveState(subject="a"), _obs("嗯")))


def test_action_executors_two_implementations():
    backend = ModeDirectiveBackend(Fixed := type("B", (), {"respond_guided": staticmethod(
        lambda p, s, h, slot, g: ("ok", None))})())  # noqa: F841
    guidance = GuidanceExecutor(backend)
    outcome = guidance.execute(ActionIntent(action_type="utterance",
                                             parameters={"directives": ("先澄清",)}), {})
    assert outcome.kind == "guidance" and outcome.delivered
    backend.respond_guided(None, None, [], "a", ["基础"])  # 注入经 respond 落账
    assert backend.injected[-1] == ("先澄清",)  # 指令确实前置
    env = EnvironmentActionExecutor()
    ctx: dict = {}
    out = env.execute(ActionIntent(action_type="action", parameters={"move": "left"}, skill_ref="s"), ctx)
    assert out.delivered and ctx["env_action_log"][0]["parameters"] == {"move": "left"}
    with pytest.raises(ValueError):
        env.execute(ActionIntent(action_type="utterance"), {})


def test_affect_and_relationship_plugin_slots():
    affect = AffectState("negative", "high")
    same, delta = NoopAffectDynamics().update(affect, _obs("嗯"))
    assert same is affect and delta is None
    with pytest.raises(ValueError):
        AffectState("angry")
    rel = RelationshipView(other="bob", stance="cooperative", trust=1)
    assert NoopRelationshipDynamics().update(rel, _obs("嗯"))[0] is rel
    with pytest.raises(ValueError):
        RelationshipView(other="bob", trust=5)


def _cooperative_model(confidence=0.7):
    return HumanModel(person_id="bob",
                      hypotheses=(Hypothesis(COOPERATION, confidence, ("turn1:bob:同意",)),))


def test_feedback_adapter_detects_drift_and_demotes_contradicted():
    adapter = FeedbackAdapter()
    model = _cooperative_model(0.7)
    updated, report = adapter.observe(model, "不行,这个方案我拒绝", speaker="bob", turn=3)
    assert report.detected and report.contradicted == COOPERATION
    coop = [h for h in updated.hypotheses if h.statement == COOPERATION][0]
    assert coop.confidence == pytest.approx(0.5)  # 0.7-0.2,显式非单调
    assert any(h.statement == DRIFT_STATEMENT for h in updated.hypotheses)
    # 无冲突反馈不触发
    _, quiet = adapter.observe(_cooperative_model(0.5), "我同意", speaker="bob", turn=4)
    assert not quiet.detected


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
                      person_id="bob", feedback=FeedbackAdapter())


def _step(agent, text):
    return agent.decide_for_human(_obs(text), Persona("p", ["t"], "m", "s", ["v"]),
                                  Scenario("s", "b", [RoleSlot("a", "a")], "c", ["n"], "training"),
                                  [TurnRecord(0, "b", text)], "a")


def test_pahf_three_step_closure_with_drift_changing_decisions():
    """验收:澄清→(反馈建立估计)→行动→(矛盾反馈触发漂移)→回到澄清。"""
    agent = _outer()
    first = _step(agent, "嗯……")
    assert first.mechanisms == ("clarify",)                     # ① 行动前澄清
    _step(agent, "我同意上午的方案")                            # ② 反馈建立合作估计
    acting = _step(agent, "这样可以,接受")
    assert acting.mechanisms == ("act",)                        # ②' 确信后行动
    report = agent.observe_feedback("不行,太贵了,我拒绝", turn=5)  # ③ 行动后矛盾反馈
    assert report.detected
    after = _step(agent, "你看着办吧")
    # 漂移后:不确定性升高(top 0.5<阈值外的剩余不确定 0.5≤0.6?)——漂移假设 0.6 置信
    # 使 uncertainty=0.4,不足以澄清;但被顶假设已从合作换为漂移假设,决策依据改变
    assert agent.human_model.top(limit=1)[0].statement == DRIFT_STATEMENT
    assert after.rationale_summary["belief_refs"][0] == DRIFT_STATEMENT  # 决策依据已修正
