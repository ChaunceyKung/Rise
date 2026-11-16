"""任务注册表:内置两个 Demo 规格(施工规划 M2,Q2:先 Python 构造,M6 再接 YAML 产物)。"""
from __future__ import annotations

from mindagent.errors import MindAgentDataError
from mindagent.evolution import EvolutionPlan
from mindagent.tasks.spec import (
    AgentBinding, BudgetCfg, Capability, EvaluationCfg, EvolutionTaskSpec, FeedbackCfg, StopCfg, Workload,
)

_REGISTRY: dict[str, EvolutionTaskSpec] = {}


def register(spec: EvolutionTaskSpec) -> EvolutionTaskSpec:
    if spec.task_id in _REGISTRY and _REGISTRY[spec.task_id] != spec:
        raise MindAgentDataError(f"任务 {spec.task_id} 已注册且规格不同")
    _REGISTRY[spec.task_id] = spec
    return spec


def get(task_id: str) -> EvolutionTaskSpec:
    if task_id not in _REGISTRY:
        raise MindAgentDataError(f"未知演化任务 {task_id};已注册: {sorted(_REGISTRY)}")
    return _REGISTRY[task_id]


def all_tasks() -> tuple[EvolutionTaskSpec, ...]:
    return tuple(_REGISTRY.values())


def _builtin() -> None:
    register(EvolutionTaskSpec(
        task_id="tom-sim-lite-v1", task_version=1,
        agent=AgentBinding(model_ref="zengen-baseline", actio_mode="inner", profile_ref="persona-pool-v1"),
        capability=Capability(family="mentalizing", objectives=("belief_inference", "intention_inference")),
        workload=Workload(environment="social_simulator", suites=("hidden-belief-train-v1", "hidden-belief-val-v1")),
        evolution=EvolutionPlan(target="scaffold", algorithm="manual", goal="oracle:scheduling"),
        feedback=FeedbackCfg(analyzer="mental_state_errors_v1"),
        evaluation=EvaluationCfg(evaluator="scripted_belief_v1", primary_metric="belief_accuracy",
                                 secondary_metrics=("intention_accuracy",)),
        budget=BudgetCfg(max_rounds=3, max_candidate_evaluations=6),
        stop=StopCfg(metric_target=None, max_no_improve_rounds=2),
    ))
    register(EvolutionTaskSpec(
        task_id="cooperation-lite-v1", task_version=1,
        agent=AgentBinding(model_ref="zengen-baseline", actio_mode="outer"),
        capability=Capability(family="strategic_interaction", objectives=("cooperative_gain",)),
        workload=Workload(environment="social_simulator", suites=("coop-train-v1", "coop-holdout-v1")),
        evolution=EvolutionPlan(target="skill", algorithm="manual", goal="oracle:trading"),
        feedback=FeedbackCfg(analyzer="outcome_gap_v1"),
        evaluation=EvaluationCfg(evaluator="scripted_coop_v1", primary_metric="cooperation_gain"),
        budget=BudgetCfg(max_rounds=2, max_candidate_evaluations=4),
        stop=StopCfg(metric_target=None, max_no_improve_rounds=1),
    ))


_builtin()
