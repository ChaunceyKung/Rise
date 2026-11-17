"""Inner–Outer 联合实验框架(V4 A5;Survey Gap1/三层规划实验 3,吸收 V3-M5)。

统一情境:隐藏真值(目标/偏好,可漂移)属 Inner 扮演的人;Outer 只经
PerceivedObservation(可见键白名单)决策。状态隔离审计在类型层过滤之外
再加值级扫描:隐藏字符串不得出现在 Outer 的任何 wire 里。

消融臂:Inner B0–B4(机制递增)/Outer O0–O3(直答→静态画像→显式估计→
动态估计+反馈)。臂组合经 candidate.delta_meta['arm'] 进 M3 评价器,
M6/A6 再登记为 evolution_tasks 产物(本文件 docstring 记录映射)。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from simple_actio.adapters.legacy import ModeDirectiveBackend
from simple_actio.core.observation import PerceivedObservation
from simple_actio.core.policy import CombinedPolicy
from simple_actio.inner.agent import ModeAgent
from simple_actio.inner.dynamics import EventDynamics
from simple_actio.inner.human_policy import BeliefDriven, GoalDriven
from simple_actio.inner.state_initializer import initialize_state
from simple_actio.cognition.goals import Goal
from simple_actio.cognition.persona import PersonaSpec
from simple_actio.instance import instantiate
from simple_actio.memory import TupleMemory
from simple_actio.outer.agent import OuterAgent
from simple_actio.outer.decision_policy import ClarificationPolicy, HumanAwareDecisionPolicy
from simple_actio.outer.state_estimator import RuleEstimator

LV = {"skill": "0", "memory": "0"}


@dataclass(frozen=True)
class JointScenario:
    scenario_id: str
    human_turns: tuple[str, ...]           # Inner 扮演的人每轮的(外显)发言
    hidden_goal: str                       # 隐藏真值:目标/偏好
    drift_turn: int | None = None          # 偏好漂移发生的轮(1 起);None 无漂移
    drifted_preference: str | None = None  # 漂移后的真值
    visible: frozenset[str] = frozenset({"公开信息"})
    accept_hypotheses: tuple[str, ...] = ()  # 视为与真值兼容的假设关键词(如"漂移")
    hidden_facts: dict = field(default_factory=dict)  # 隐藏字段(值进入隔离审计)

    def ground_truth(self, turn: int) -> str:
        if self.drift_turn is not None and turn >= self.drift_turn and self.drifted_preference:
            return self.drifted_preference
        return self.hidden_goal


class _Echo:
    def __init__(self):
        self.calls = []

    def respond_guided(self, persona, scenario, history, speaker_slot, guidance):
        self.calls.append(list(guidance))
        return ("|".join(guidance) or "plain", None)


def _instance(subject):
    echo = _Echo()
    instance = instantiate(ModeDirectiveBackend(echo), skills=[], memory=TupleMemory(()).world(subject),
                           library_version=LV, profile=None, episode_id="ep", holder=subject)
    return instance, echo


# ---------------- Inner 消融臂:B0 无机制 → B4 全模块 ----------------

INNER_ARMS = ("B0", "B1", "B2", "B4")  # B3(记忆)由实例底座隐式提供,臂面等价 B2+memory,文档记录


def build_inner(arm: str, persona: PersonaSpec, subject="human"):
    instance, _ = _instance(subject)
    goal = Goal(persona.preferences[0] if persona.preferences else "维持现状", 1)
    if arm == "B0":
        policy = CombinedPolicy((GoalDriven(goals=()),))  # 空目标:机制永不命中→fallback
        state = None
    elif arm == "B1":
        policy = CombinedPolicy((GoalDriven(goals=(goal.description,)),))
        state = None
    else:  # B2/B4:persona 状态初始化 + 信念机制(B4 再加事件动力学)
        policy = CombinedPolicy((GoalDriven(goals=(goal.description,)),
                                 BeliefDriven(beliefs=("先确认对方意图",))))
        state = initialize_state(persona, subject, goals=(goal,))
    agent = ModeAgent(instance, policy, subject=subject,
                      dynamics=EventDynamics() if arm == "B4" else None,
                      initial_state=state)
    return agent


# ---------------- Outer 消融臂:O0 直答 → O3 动态估计+反馈 ----------------

OUTER_ARMS = ("O0", "O1", "O2", "O3")


def build_outer(arm: str, objectives=("完成清理",), person_id="human"):
    instance, _ = _instance("assistant")
    if arm in ("O0", "O1"):
        # O0/O1:无估计器——O1 带静态画像假设(先验合作,永不更新)
        policy = CombinedPolicy((GoalDriven(goals=objectives),))
        return OuterAgent(instance, policy, subject="assistant", person_id=person_id)
    from simple_actio.outer.feedback_adapter import FeedbackAdapter

    estimator = RuleEstimator()
    decision = HumanAwareDecisionPolicy(objectives=objectives,
                                        clarify=ClarificationPolicy(threshold=0.6))
    agent = OuterAgent(instance, CombinedPolicy((GoalDriven(goals=objectives),)),
                       subject="assistant", estimator=estimator if arm == "O3" else None,
                       decision=decision if arm == "O3" else None, person_id=person_id,
                       feedback=FeedbackAdapter() if arm == "O3" else None)
    if arm == "O2":  # 静态画像:预置先验假设,不再随交互更新(estimator 不接)
        agent.human_model = type(agent.human_model)(
            person_id=person_id,
            hypotheses=(type("H", (), {"statement": "对方倾向于合作", "confidence": 0.8,
                                       "evidence": ("prior",)})(),))
    return agent


# ---------------- 联合会话与隔离审计 ----------------

@dataclass(frozen=True)
class JointRecord:
    scenario_id: str
    arm: str
    decisions: tuple          # 每轮 Outer mechanisms/rationale 摘要
    top_hypothesis: str | None
    isolation_ok: bool
    isolation_violations: tuple[str, ...] = ()


def run_joint(scenario: JointScenario, outer: OuterAgent, *, arm: str,
              inner_persona: PersonaSpec | None = None, inner_arm: str | None = None) -> JointRecord:
    from simulator.datamodel import Persona, RoleSlot, Scenario, TurnRecord

    hidden_values = [scenario.hidden_goal, scenario.drifted_preference or "",
                     *scenario.hidden_facts.values()]
    sim_persona = Persona("p", ["t"], "m", "s", ["v"])
    sim_scenario = Scenario("s", "b", [RoleSlot("a", "a")], "c", ["n"], "training")
    decisions = []
    violations = []

    for turn, utterance in enumerate(scenario.human_turns, start=1):
        world = {"公开信息": utterance[:24], **scenario.hidden_facts}
        obs = PerceivedObservation.from_world(world, scenario.visible,
                                              speaker="human", utterance=utterance,
                                              turn_id=turn)
        # Outer 只拿可见;隔离审计:隐藏值不得出现在 Outer 全部状态 wire
        outer_wire = str(outer.state.to_wire()) + str(outer.human_model.to_wire())
        for secret in filter(None, hidden_values):
            if secret in outer_wire:
                violations.append(f"turn{turn}:wire 含隐藏值 {secret[:12]}…")
        result = outer.decide_for_human(obs, sim_persona, sim_scenario,
                                        [TurnRecord(0, "human", utterance)], "a")
        decisions.append({"mechanisms": list(result.mechanisms),
                          "rationale": result.rationale_summary})
        if outer.feedback is not None:  # O3:行动后反馈闭环
            outer.observe_feedback(utterance, turn=turn)

    top = outer.human_model.top(limit=1)
    return JointRecord(scenario_id=scenario.scenario_id, arm=arm, decisions=tuple(decisions),
                       top_hypothesis=top[0].statement if top else None,
                       isolation_ok=not violations, isolation_violations=tuple(violations))


def inner_utterance(arm: str, persona: PersonaSpec, text: str) -> str:
    """Demo A 用:给定机制臂,Inner 对观察的产物(确定性 Echo 拼接指令)。"""
    agent = build_inner(arm, persona)
    obs = PerceivedObservation.from_world({"公开信息": "x"}, {"公开信息"}, speaker="对方", utterance=text)
    from simulator.datamodel import Persona as P, RoleSlot, Scenario, TurnRecord

    result = agent.simulate_step(obs, P("p", ["t"], "m", "s", ["v"]),
                                 Scenario("s", "b", [RoleSlot("a", "a")], "c", ["n"], "training"),
                                 [TurnRecord(0, "对方", text)], "a")
    return result.utterance
