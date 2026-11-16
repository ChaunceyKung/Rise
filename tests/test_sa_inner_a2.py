"""V4 A2 验收:PersonaSpec/机制/初始化/事件 Dynamics/校准钩子/信息隔离。"""
from __future__ import annotations

import pytest

from simulator.datamodel import Persona, RoleSlot, Scenario, TurnRecord
from simple_actio.adapters.legacy import ModeDirectiveBackend
from simple_actio.cognition.beliefs import Belief, strongest, to_strings as beliefs_to_strings
from simple_actio.cognition.goals import Goal, active_goals
from simple_actio.cognition.persona import PersonaSpec
from simple_actio.core.observation import PerceivedObservation
from simple_actio.instance import instantiate
from simple_actio.inner.agent import ModeAgent
from simple_actio.inner.dynamics import EventDynamics
from simple_actio.inner.human_policy import BeliefDriven, GoalDriven, persona_diff, policy_for
from simple_actio.inner.state_initializer import initialize_state
from simple_actio.memory import TupleMemory


def _spec(pid="p-cautious", weights=None):
    return PersonaSpec(pid, traits={"risk": "averse"}, preferences=("先澄清",),
                       capacities=("scheduling",),
                       situation_mechanisms=weights or {"negotiation": {"belief_driven": 3}})


def test_persona_spec_wire_round_trip_and_validation():
    spec = _spec()
    again = PersonaSpec.from_wire(spec.to_wire())
    assert again == spec
    assert spec.mechanism_weights("negotiation") == {"belief_driven": 3}
    assert spec.mechanism_weights("unknown") == {}
    with pytest.raises(ValueError):
        PersonaSpec("")
    with pytest.raises(ValueError):
        PersonaSpec("x", situation_mechanisms={"s": {"m": 1.5}})


def test_initialize_state_puts_stable_params_in_long_term():
    state = initialize_state(_spec(), "alice", goals=(Goal("达成共识", 1), Goal("放弃项", 5, "dropped")),
                             beliefs=(Belief("对方偏好上午", 0.8, ("开场白",)),))
    assert state.long_term["persona_id"] == "p-cautious" and state.long_term["traits"] == {"risk": "averse"}
    assert state.goals == ("达成共识",)  # dropped 不进 goals
    assert state.mid_term["goal_status"]["放弃项"] == "dropped"
    assert state.beliefs == ("对方偏好上午",)


def test_goal_and_belief_helpers_order_and_validate():
    ranked = active_goals((Goal("b", 2), Goal("a", 1), Goal("c", 2, "satisfied")))
    assert [g.description for g in ranked] == ["a", "b"]
    top = strongest((Belief("x", 0.4), Belief("y", 0.9), Belief("z", 0.9)))
    assert [b.statement for b in top[:2]] == ["y", "z"]  # 同置信按语句序
    with pytest.raises(ValueError):
        Belief("x", 1.5)
    with pytest.raises(ValueError):
        Goal("x", 0)
    assert beliefs_to_strings((Belief("s", 1.0),)) == ("s",)


def test_event_dynamics_updates_goal_status_and_affect_with_evidence():
    dyn = EventDynamics()
    state = initialize_state(_spec(), "alice", goals=(Goal("达成共识", 1),))
    agree_obs = PerceivedObservation.from_world({}, set(), speaker="bob", utterance="我同意上午的方案")
    after, delta = dyn.update(state, agree_obs, action="提议")
    assert after.mid_term["goal_status"]["达成共识"] == "satisfied"
    assert "mid_term.goal_status" in delta.fields and delta.time_scale == "mid"
    assert "同意" in delta.evidence["markers"]
    conflict = PerceivedObservation.from_world({}, set(), speaker="bob", utterance="不行,太贵了")
    after2, delta2 = dyn.update(after, conflict)
    assert after2.short_term["affect_hint"] == "tension"
    assert delta2.time_scale == "short" and "short_term.affect_hint" in delta2.fields


class _Echo:
    def respond_guided(self, persona, scenario, history, speaker_slot, guidance):
        return ("|".join(guidance) or "plain", None)


def _agent(spec, subject):
    instance = instantiate(ModeDirectiveBackend(_Echo()), skills=[],
                           memory=TupleMemory(()).world(subject),
                           library_version={"skill": "0", "memory": "0"}, profile=None,
                           episode_id="ep", holder=subject)
    policy = policy_for(spec, (GoalDriven(goals=("达成共识",)), BeliefDriven(beliefs=("对方偏好上午",))),
                        situation="negotiation")
    return ModeAgent(instance, policy, subject=subject, dynamics=EventDynamics(),
                     initial_state=initialize_state(spec, subject, goals=(Goal("达成共识", 1),)))


def _obs(text="我提议上午,有机会达成共识"):
    return PerceivedObservation.from_world({"公开提议": "m", "隐藏身份": "x"}, {"公开提议"},
                                           speaker="b", utterance=text)


def _run(agent):
    return agent.step(_obs(), Persona("p", ["t"], "m", "s", ["v"]),
                      Scenario("s", "b", [RoleSlot("a", "a")], "c", ["n"], "training"),
                      [TurnRecord(0, "b", "上午?")], "a")


def test_two_personas_diverge_stably_and_replay_is_identical():
    believer = _agent(_spec("p-believer", {"negotiation": {"belief_driven": 3}}), "alice")
    goaler = _agent(_spec("p-goaler", {"negotiation": {"goal_driven": 3}}), "alice")
    d1, d2 = _run(believer), _run(goaler)
    assert d1.mechanisms[0] == "belief_driven" and d2.mechanisms[0] == "goal_driven"
    assert d1.utterance != d2.utterance
    # 复跑一致(稳定可测):全新 agent 重跑逐字节相同
    assert _run(_agent(_spec("p-believer", {"negotiation": {"belief_driven": 3}}), "alice")).utterance == d1.utterance
    # 机制经 CAPS 权重确实改变了叠加顺序
    assert believer.policy.mechanisms[0].name == "belief_driven"


def test_hidden_facts_never_reach_state_information_isolation():
    agent = _agent(_spec(), "alice")
    result = _run(agent)
    wire = agent.state.to_wire()
    joined = str(wire)
    assert "隐藏身份" not in joined and "merlin" not in joined  # 隐藏字段未进任何状态
    assert agent.state.beliefs[0].startswith("b 说过:")
    assert result.state_delta[0].evidence["speaker"] == "b"


def test_persona_diff_counts_consistency_against_declared_weights():
    spec = _spec()
    report = persona_diff(spec, (
        {"mechanisms": ["belief_driven", "goal_driven"], "situation": "negotiation"},
        {"mechanisms": ["goal_driven"], "situation": "negotiation"},   # 与声明冲突
        {"mechanisms": ["goal_driven"], "situation": "casual"},        # 未声明情境:无冲突证据
    ), situation="negotiation")
    assert report["consistent"] == 2 and report["inconsistent"] == 1
    assert report["examples"][0]["expected_top"] == "belief_driven"
