"""V4 A1 验收:六数据模型的 wire/seal、三时间尺度、ActionIntent 语义、
Dynamics 差分、ActioAgent 协议与快照恢复(施工规划 A1 验收口径)。"""
from __future__ import annotations

import pytest

from simple_actio.core.agent import ActioAgent, restore_state, snapshot_state
from simple_actio.core.dynamics import RuleDynamics, StateDelta
from simple_actio.core.intent import ActionIntent, StepResult
from simple_actio.core.observation import Observation, PerceivedObservation
from simple_actio.core.state import CognitiveState, MindState, digest
from simple_actio.inner.agent import ModeAgent
from simple_actio.adapters.legacy import ModeDirectiveBackend
from simple_actio.core.policy import CombinedPolicy
from simple_actio.inner.human_policy import GoalDriven
from simple_actio.instance import instantiate
from simple_actio.memory import TupleMemory
from simulator.datamodel import Persona, RoleSlot, Scenario, TurnRecord


def test_cognitive_state_three_timescales_wire_and_seal():
    state = CognitiveState(subject="alice", goals=("达成共识",),
                           long_term={"traits": {"openness": "high"}},
                           mid_term={"relationships": {"bob": "cooperative"}},
                           short_term={"affect": {"valence": "neutral"}})
    again = CognitiveState.from_wire(state.to_wire())
    assert again == state
    assert digest(state.to_wire()) == digest(state.to_wire())
    # 旧 wire(无三尺度键)仍可读——向后兼容
    legacy_wire = {"subject": "a", "turn": 1, "goals": [], "beliefs": ["x"],
                   "uncertainty": [], "last_action": None, "extra": {}}
    restored = CognitiveState.from_wire(legacy_wire)
    assert restored.long_term == {} and restored.mid_term == {} and restored.short_term == {}
    # 别名与旧构造零破坏
    assert MindState is CognitiveState
    old_style = MindState(subject="a", goals=("g",), beliefs=("b",))
    assert old_style.short_term == {}


def test_observation_formal_fields_superset_and_alias():
    obs = Observation.from_world({"公开": 1, "隐藏": 2}, {"公开"}, speaker="bob",
                                 utterance="hi", actor_id="alice", episode_id="ep1",
                                 turn_id=3, task_context={"task": "coop"})
    assert obs.actor_id == "alice" and obs.episode_id == "ep1" and obs.turn_id == 3
    assert obs.task_context == {"task": "coop"}
    wire = obs.to_wire()
    assert wire["hidden_count"] == 1 and wire["visible_facts"] == {"公开": 1}
    # 旧构造(不带形式字段)零破坏
    legacy = PerceivedObservation.from_world({"a": 1}, set(), speaker="b", utterance="x")
    assert legacy.actor_id == "b" and legacy.task_context == {}
    assert Observation is PerceivedObservation


def test_action_intent_time_semantics_follows_shachi():
    assert ActionIntent(action_type="utterance", parameters={"text": "好"}).time_semantics == "utterance"
    tool = ActionIntent(action_type="tool_call", parameters={"tool": "search"}, skill_ref="s1")
    assert tool.time_semantics == "tool_call"  # 不推进环境时间
    assert ActionIntent(action_type="action", parameters={"move": "left"}).time_semantics == "action"
    assert ActionIntent(action_type="action", parameters={}).time_semantics == "action"  # 缺省派生
    with pytest.raises(ValueError):
        ActionIntent(action_type="utterance", time_semantics="action")  # 显式错配被拒
    with pytest.raises(ValueError):
        ActionIntent(action_type="fly")


def test_step_result_is_decision_superset_with_delta_and_rationale():
    delta = StateDelta(fields=("beliefs",), source="rule_observation", evidence={"speaker": "b"})
    result = StepResult(mode="inner", utterance="好", inner_thought=None,
                        directive=("d",), mechanisms=("goal_driven",), trace={"schema": "simple_actio.trace.v2"},
                        state_delta=(delta,), rationale_summary={"evidence_level": "structurally_derived"})
    wire = result.to_wire()
    assert wire["state_delta"][0]["fields"] == ["beliefs"]
    assert wire["rationale_summary"]["evidence_level"] == "structurally_derived"
    # 旧 Decision 构造仍可用(无 delta 默认空)
    from simple_actio.core.action import Decision

    plain = Decision(mode="outer", utterance="u", inner_thought=None,
                     directive=("d",), mechanisms=("m",), trace={})
    assert plain.to_respond_triple()[0] == "u"


def test_rule_dynamics_emits_evidence_bearing_delta():
    state = CognitiveState(subject="a")
    obs = PerceivedObservation.from_world({}, set(), speaker="bob", utterance="上午可以")
    after, delta = RuleDynamics().update(state, obs, action="提议上午")
    assert after.beliefs[0].startswith("bob 说过:")
    assert after.last_action == "提议上午"
    assert delta.fields == ("beliefs",) and delta.time_scale == "mid"
    assert delta.evidence["speaker"] == "bob"


class _Echo:
    def respond_guided(self, persona, scenario, history, speaker_slot, guidance):
        return ("|".join(guidance) or "plain", None)


def _agent():
    instance = instantiate(ModeDirectiveBackend(_Echo()), skills=[],
                           memory=TupleMemory(()).world("pa"),
                           library_version={"skill": "0", "memory": "0"}, profile=None,
                           episode_id="ep", holder="pa")
    return ModeAgent(instance, CombinedPolicy((GoalDriven(goals=("达成共识",)),)), subject="alice")


def test_actio_agent_protocol_step_snapshot_restore_round_trip():
    agent = _agent()
    assert isinstance(agent, ActioAgent)
    obs = PerceivedObservation.from_world({"公开提议": "m"}, {"公开提议"}, speaker="b", utterance="提议上午")
    persona = Persona("p", ["t"], "m", "s", ["v"])
    scenario = Scenario("s", "bg", [RoleSlot("a", "a")], "c", ["n"], "training")
    history = [TurnRecord(0, "b", "你们怎么看?")]
    first = agent.step(obs, persona, scenario, history, "a")
    assert first.state_delta and first.state_delta[0].fields == ("beliefs",)
    assert agent.last_trace.to_wire()["schema"] == "simple_actio.cognitive-trace.v1"
    # 快照 → 恢复 → 状态可续
    snap = agent.snapshot()
    agent.state = CognitiveState(subject="alice", turn=99)  # 篡改后恢复
    agent.restore(snap)
    assert agent.state.turn == 1 and agent.state.beliefs
    with pytest.raises(ValueError, match="不匹配"):
        agent.restore({"mode": "outer", "subject": "alice", "state": snap["state"]})
    # 通用快照工具与 digest 稳定性
    assert snapshot_state(agent.state) == snap["state"]
    assert restore_state(snap["state"]) == agent.state
    # snapshot 的受限 JSON 可 seal(摘要稳定)
    assert digest(snap["state"]) == digest(snap["state"])


def test_cognitive_trace_records_audit_chain():
    agent = _agent()
    obs = PerceivedObservation.from_world({}, set(), speaker="b", utterance="我提议上午,有机会达成共识")
    agent.step(obs, Persona("p", ["t"], "m", "s", ["v"]),
               Scenario("s", "b", [RoleSlot("a", "a")], "c", ["n"], "training"),
               [TurnRecord(0, "b", "hi")], "a")
    wire = agent.last_trace.to_wire()
    assert wire["mechanisms"] == ["goal_driven"]
    assert wire["rationale"]["evidence_level"] == "structurally_derived"
    assert wire["state_delta"][0]["source"] == "rule_observation"
