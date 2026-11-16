"""EvolutionTaskSpec 校验矩阵(施工规划 M2)。"""
from __future__ import annotations

import pytest

from mindagent.errors import MindAgentDataError
from mindagent.evolution import EvolutionPlan
from mindagent.tasks.registry import all_tasks, get, register
from mindagent.tasks.spec import (
    AgentBinding, BudgetCfg, Capability, EvaluationCfg, EvolutionTaskSpec, FeedbackCfg, StopCfg, Workload,
)


def _spec(**over):
    base = dict(
        task_id="unit-task-v1", task_version=1,
        agent=AgentBinding(model_ref="m1", actio_mode="inner"),
        capability=Capability(family="mentalizing", objectives=("belief_inference",)),
        workload=Workload(environment="social_simulator", suites=("s-train", "s-val")),
        evolution=EvolutionPlan(target="scaffold", algorithm="manual", goal="oracle:scheduling"),
        feedback=FeedbackCfg(analyzer="a1"),
        evaluation=EvaluationCfg(evaluator="scripted_belief_v1", primary_metric="belief_accuracy"),
        budget=BudgetCfg(max_rounds=2, max_candidate_evaluations=4),
        stop=StopCfg(metric_target=None, max_no_improve_rounds=1),
    )
    base.update(over)
    return EvolutionTaskSpec(**base)


def test_valid_spec_passes_and_is_frozen():
    spec = _spec()
    assert spec.evolution.target == "scaffold"
    assert spec.agent.actio_mode in ("inner", "outer")


def _bad(kind):
    """非法件延迟构造:参数化收集期不触发校验。"""
    return {
        "agent_blank": lambda: AgentBinding(model_ref="", actio_mode="inner"),
        "agent_mode": lambda: AgentBinding(model_ref="m", actio_mode="both"),
        "family": lambda: Capability(family="", objectives=("x",)),
        "suites": lambda: Workload(environment="e", suites=()),
        "rounds": lambda: BudgetCfg(max_rounds=0, max_candidate_evaluations=1),
            "target": lambda: StopCfg(metric_target=1.5, max_no_improve_rounds=1),
    }[kind]


@pytest.mark.parametrize(("kind", "over", "match"), [
    ("agent_blank", "agent", "model_ref"),
    ("agent_mode", "agent", "actio_mode"),
    ("family", "capability", "能力族"),
    ("suites", "workload", "套件"),
    ("rounds", "budget", "max_rounds"),
    ("target", "stop", "metric_target"),
])
def test_invalid_specs_are_rejected_with_named_reasons(kind, over, match):
    with pytest.raises(MindAgentDataError, match=match):
        EvolutionTaskSpec(**{**_spec().__dict__, over: _bad(kind)()})


def test_memory_target_and_bad_task_id_are_rejected():
    with pytest.raises(MindAgentDataError, match="P6a"):
        _spec(evolution=EvolutionPlan(target="memory"))
    with pytest.raises(MindAgentDataError, match="task_id"):
        _spec(task_id="bad id!")


def test_registry_serves_builtins_and_rejects_conflicts():
    assert {t.task_id for t in all_tasks()} >= {"tom-sim-lite-v1", "cooperation-lite-v1"}
    inner = get("tom-sim-lite-v1")
    assert inner.agent.actio_mode == "inner" and get("cooperation-lite-v1").agent.actio_mode == "outer"
    register(inner)  # 幂等:同规格重复注册 OK
    with pytest.raises(MindAgentDataError, match="规格不同"):
        register(_spec(task_id="tom-sim-lite-v1", task_version=2))
    with pytest.raises(MindAgentDataError, match="未知演化任务"):
        get("nope")
