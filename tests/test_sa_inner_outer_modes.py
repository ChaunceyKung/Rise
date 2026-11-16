"""双模式最小行为路径:同一底座以 inner/outer 各跑一条 scripted 对话(V3 M1 验收)。"""
from __future__ import annotations

from simulator.datamodel import Persona, RoleSlot, Scenario, TurnRecord
from simple_actio.adapters.legacy import ModeDirectiveBackend, triple_of
from simple_actio.core.observation import PerceivedObservation
from simple_actio.core.policy import CombinedPolicy
from simple_actio.instance import instantiate
from simple_actio.inner.agent import ModeAgent
from simple_actio.inner.human_policy import BeliefDriven, GoalDriven
from simple_actio.memory import TupleMemory
from simple_actio.outer.agent import OuterAgent
from simple_actio.outer.decision_policy import HumanModeling, TaskGoalDriven

LV = {"skill": "0", "memory": "0"}


class EchoGuidance:
    """罐头后端:把指导语拼进话语——模式指令是否生效,从输出直接可见。"""

    def __init__(self):
        self.calls = []

    def respond_guided(self, persona, scenario, history, speaker_slot, guidance):
        self.calls.append(list(guidance))
        return ("|".join(guidance) or "plain", None)


def _persona():
    return Persona("pa", ["t"], "m", "s", ["v"])


def _scenario():
    return Scenario("s1", "bg", [RoleSlot("a", "a"), RoleSlot("b", "b")], "c", ["n"], "training")


def _instance(backend, *, wrap=True):
    """模式 agent 的底座:backend 一律经 ModeDirectiveBackend 包装(设计缝隙)。"""
    inner = ModeDirectiveBackend(backend) if wrap else backend
    return instantiate(inner, skills=[], memory=TupleMemory(()).world("pa"),
                       library_version=LV, profile=None, episode_id="ep", holder="pa")


def _obs(utterance="我提议上午打扫,有机会达成共识", visible=("公开提议",)):
    world = {"公开提议": "morning", "隐藏身份": "merlin"}
    return PerceivedObservation.from_world(world, set(visible), speaker="b", utterance=utterance)


def test_inner_mode_personas_produce_observable_differences():
    """验收:不同 Persona 的行为具有可观测差异(经指导语注入,非路由变化)。"""
    ambitious = ModeAgent(_instance(EchoGuidance()),
                          CombinedPolicy((GoalDriven(goals=("尽快达成共识",)),)),
                          subject="alice")
    cautious = ModeAgent(_instance(EchoGuidance()),
                         CombinedPolicy((BeliefDriven(beliefs=("对方可能另有安排",)),)),
                         subject="bob")
    history = [TurnRecord(0, "b", "你们觉得上午如何?")]
    d1 = ambitious.simulate_step(_obs(), _persona(), _scenario(), history, "a")
    d2 = cautious.simulate_step(_obs(), _persona(), _scenario(), history, "a")
    assert d1.mechanisms == ("goal_driven",) and d2.mechanisms == ("belief_driven",)
    assert "尽快达成共识" in d1.utterance and "对方可能另有安排" in d2.utterance
    assert d1.utterance != d2.utterance
    # 心智状态随交互更新(V3 Demo A 验证要求)
    assert ambitious.state.beliefs and ambitious.state.beliefs[0].startswith("b 说过:")
    assert ambitious.state.turn == 1


def test_outer_mode_decides_for_human_and_may_consult_an_inner_advisor():
    advisor_calls = []

    def advisor(observation):
        advisor_calls.append(observation.speaker)
        return "对方大概率接受上午方案"

    agent = OuterAgent(_instance(EchoGuidance()),
                       CombinedPolicy((HumanModeling(hypotheses=("对方偏好合作",)),
                                       TaskGoalDriven(objectives=("最小成本完成清理",), advisor=advisor))),
                       subject="assistant")
    decision = agent.decide_for_human(_obs(), _persona(), _scenario(), [TurnRecord(0, "b", "上午?")], "a")
    assert decision.mode == "outer"
    assert "任务目标" in decision.utterance and "对手行为预测" in decision.utterance
    assert advisor_calls == ["b"]
    # 三元组映射:trace 原样(simple_actio.trace.v2 冻结)
    utterance, thought, trace = triple_of(decision)
    assert utterance == decision.utterance and trace is decision.trace
    assert trace["schema"]


def test_directive_injection_is_auditable_and_mode_scoped():
    """指令注入留痕:演化收益可溯源到具体机制指令(V3 §11 反路由变化证据)。"""
    echo = EchoGuidance()
    instance = _instance(echo)
    agent = ModeAgent(instance, CombinedPolicy((GoalDriven(goals=("达成共识",)),)), subject="a")
    agent.simulate_step(_obs(), _persona(), _scenario(), [TurnRecord(0, "b", "hi")], "a")
    backend = instance.backend
    assert backend.injected and backend.injected[0][0].startswith("朝着你的目标行动")
    assert echo.calls[0][0] == backend.injected[0][0]  # 注入确实位于指导语头部
