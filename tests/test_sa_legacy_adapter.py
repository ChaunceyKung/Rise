"""legacy 适配层:Decision ↔ 三元组、ModeDirectiveBackend 的兼容语义。"""
from __future__ import annotations

from simulator.datamodel import Persona, RoleSlot, Scenario, TurnRecord
from simple_actio.adapters.legacy import ModeDirectiveBackend, triple_of
from simple_actio.core.action import Decision
from simple_actio.core.observation import PerceivedObservation
from simple_actio.core.policy import CombinedPolicy
from simple_actio.instance import instantiate
from simple_actio.inner.agent import ModeAgent
from simple_actio.inner.human_policy import GoalDriven
from simple_actio.memory import TupleMemory


class Fixed:
    def respond_guided(self, persona, scenario, history, speaker_slot, guidance):
        return ("回声", "内心")


def test_wrapped_backend_passes_through_and_prepends():
    wrapped = ModeDirectiveBackend(Fixed())
    assert wrapped.respond_guided(None, None, [], "a", ["基础"]) == ("回声", "内心")
    wrapped.set_directive(("策略指令",))
    reply = wrapped.respond_guided(None, None, [], "a", ["基础"])
    assert reply == ("回声", "内心")  # 装饰器不改后端输出形状
    assert wrapped.injected == [(), ("策略指令",)]


def test_respond_triple_of_a_mode_decision_via_full_instance():
    instance = instantiate(ModeDirectiveBackend(Fixed()), skills=[], memory=TupleMemory(()).world("pa"),
                           library_version={"skill": "0", "memory": "0"}, profile=None,
                           episode_id="ep", holder="pa")
    agent = ModeAgent(instance, CombinedPolicy((GoalDriven(goals=("g",)),)), subject="a")
    obs = PerceivedObservation.from_world({"公开提议": "x"}, set(), speaker="b", utterance="提议")
    decision = agent.simulate_step(obs, Persona("p", ["t"], "m", "s", ["v"]),
                                   Scenario("s", "b", [RoleSlot("a", "a")], "c", ["n"], "training"),
                                   [TurnRecord(0, "b", "hi")], "a")
    utterance, thought, trace = triple_of(decision)
    assert (utterance, thought) == ("回声", "内心")
    assert set(trace)  # trace.v2 结构由底座产出并原样携带
    with_trace = Decision(mode="outer", utterance="u", inner_thought="t",
                          directive=("d",), mechanisms=("m",), trace=trace)
    assert with_trace.to_respond_triple()[2] is trace
