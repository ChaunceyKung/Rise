"""resolver 解析闭包与缺件报错(施工规划 M2)。"""
from __future__ import annotations

import pytest

from mindagent.errors import MindAgentDataError
from mindagent.tasks.registry import get
from mindagent.tasks.resolver import candidate_source, resolve
from test_ma_task_spec import _spec


def test_resolve_wires_algorithm_evaluator_and_mode():
    resolved = resolve(get("tom-sim-lite-v1"), agent_factory=lambda: "agent")
    assert resolved.algorithm.name == "manual"
    assert resolved.evaluator.name == "scripted_belief_v1"
    assert resolved.agent_factory() == "agent"
    assert resolved.task_id == "tom-sim-lite-v1"


def test_resolve_reports_unknown_plugins_by_name():
    spec = _spec(evaluation=None)  # 占位,下面换成未知评价器名
    from mindagent.tasks.spec import EvaluationCfg

    spec = _spec(evaluation=EvaluationCfg(evaluator="ghost", primary_metric="m"))
    with pytest.raises(MindAgentDataError, match="ghost"):
        resolve(spec, agent_factory=lambda: None)
    from mindagent.evolution import EvolutionPlan

    with pytest.raises(MindAgentDataError, match="gateway"):
        resolve(_spec(evolution=EvolutionPlan(target="scaffold", algorithm="gateway")), agent_factory=lambda: None)


def test_candidate_source_routes_by_target_and_absorbs_dispatch():
    scaffold = candidate_source(get("tom-sim-lite-v1"))
    proposals = scaffold()
    assert [p["name"] for p in proposals] == ["B0", "C1"]  # Actio 冻结候选(P3 dispatch 吸收)
    skill = candidate_source(get("cooperation-lite-v1"))
    assert skill() == []  # 无 findings 时 skill 路径产出空草案列表
    from mindagent.evolution import EvolutionPlan

    with pytest.raises(MindAgentDataError, match="P6a"):
        candidate_source(_spec(evolution=EvolutionPlan(target="memory")))


def test_resolve_requires_a_spec_and_a_factory():
    with pytest.raises(MindAgentDataError, match="EvolutionTaskSpec"):
        resolve("not-a-spec", agent_factory=lambda: None)
