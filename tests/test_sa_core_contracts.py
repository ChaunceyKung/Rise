"""core 层契约测试 + 双模式子包的依赖边界(V3 M1)。"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

from simple_actio.core.action import Decision
from simple_actio.core.observation import PerceivedObservation
from simple_actio.core.policy import CombinedPolicy
from simple_actio.core.state import MindState, digest

SRC = Path(__file__).resolve().parents[1] / "src"


def test_state_wire_round_trip_and_digest_are_stable():
    state = MindState(subject="alice", turn=2, goals=("达成共识",), beliefs=("对方偏好上午",),
                      last_action="propose:morning")
    again = MindState.from_wire(state.to_wire())
    assert again == state
    assert digest(state.to_wire()) == digest(state.to_wire())
    with pytest.raises(ValueError):
        MindState(subject="", ) if False else MindState(subject="a", goals=("ok",), beliefs=("b", 1.5))


def test_state_rejects_floats_and_unsafe_ints():
    with pytest.raises(ValueError):
        MindState(subject="a", frozen_extra={"bad": 1.5})
    with pytest.raises(ValueError):
        MindState(subject="a", frozen_extra={"bad": 2 ** 53})


def test_observation_strips_hidden_facts_and_counts_them():
    world = {"公开提议": "morning", "隐藏身份": "merlin", "双方血量": 3}
    obs = PerceivedObservation.from_world(world, {"公开提议"}, speaker="bob", utterance="我提议上午")
    assert obs.visible_facts == {"公开提议": "morning"}
    assert obs.hidden_count == 2  # 隐藏内容不进对象,只有计数
    with pytest.raises(KeyError):
        obs.fact("隐藏身份")
    with pytest.raises(ValueError):
        PerceivedObservation.from_world(world, {"不存在的键"}, speaker="b", utterance="x")


def test_decision_triple_mapping_keeps_trace_verbatim():
    trace = {"schema": "simple_actio.trace.v2"}
    decision = Decision(mode="inner", utterance="好", inner_thought=None,
                        directive=("朝着你的目标行动:达成共识",), mechanisms=("goal_driven",), trace=trace)
    assert decision.to_respond_triple() == ("好", None, trace)
    with pytest.raises(ValueError):
        Decision(mode="both", utterance="x", inner_thought=None, directive=("d",), mechanisms=("m",), trace={})
    with pytest.raises(ValueError):
        Decision(mode="inner", utterance="x", inner_thought=None, directive=(), mechanisms=("m",), trace={})


def test_combined_policy_fires_mechanisms_in_order_and_falls_back():
    from simple_actio.inner.human_policy import BeliefDriven, GoalDriven

    obs = PerceivedObservation.from_world({"公开提议": "morning"}, set(), speaker="b", utterance="提议上午?")
    state = MindState(subject="a", goals=("达成共识",), beliefs=("对方偏好上午",))
    policy = CombinedPolicy((GoalDriven(goals=()), BeliefDriven(beliefs=())))
    directive = policy.decide(state, obs)
    assert directive.mechanisms == ("goal_driven", "belief_driven")
    assert directive.instructions[0].startswith("朝着你的目标行动")
    quiet = CombinedPolicy((GoalDriven(goals=()), BeliefDriven(beliefs=())))
    empty = MindState(subject="a")
    assert quiet.decide(empty, PerceivedObservation.from_world({}, set(), speaker="b", utterance="嗯")
                        ).mechanisms == ("fallback",)


def test_dual_mode_subpackages_depend_on_nothing_upward():
    """core/inner/outer/adapters 禁依赖 mindagent/factory/actio/simulator(施工规划 §3 红线 4)。"""
    forbidden = {"mindagent", "factory", "actio", "simulator", "controlplane"}
    offenders = []
    for sub in ("core", "inner", "outer", "adapters"):
        for path in sorted((SRC / "simple_actio" / sub).glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                names = [a.name for a in node.names] if isinstance(node, ast.Import) else \
                        [node.module or ""] if isinstance(node, ast.ImportFrom) else []
                for name in names:
                    if name.split(".")[0] in forbidden:
                        offenders.append(f"{path.name}:{name}")
    assert offenders == [], f"双模式子包越界依赖: {offenders}"
    assert "simple_actio" in sys.modules  # sanity:包已加载
