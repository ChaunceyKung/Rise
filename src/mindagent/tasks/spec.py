"""Evolution Task 六问全量表达(V3 §3.2;施工规划 M2)。

`EvolutionPlan`(P3 的 target/algorithm/goal 三元组)是本规格的**冻结核**:
六问中的"改什么/怎么改/何为改善"由它回答并沿用其校验;本模块补齐
"什么能力/哪个 agent 哪种模式/在哪评/预算/停止条件"。
"""
from __future__ import annotations

from dataclasses import dataclass

from mindagent.errors import MindAgentDataError
from mindagent.evolution import EvolutionPlan

MODES = ("inner", "outer")


@dataclass(frozen=True)
class AgentBinding:
    model_ref: str
    actio_mode: str
    profile_ref: str | None = None

    def __post_init__(self):
        if not isinstance(self.model_ref, str) or not self.model_ref:
            raise MindAgentDataError("model_ref 必须是非空字符串")
        if self.actio_mode not in MODES:
            raise MindAgentDataError(f"actio_mode 必须是 {MODES}")


@dataclass(frozen=True)
class Capability:
    family: str
    objectives: tuple[str, ...]

    def __post_init__(self):
        if not self.family or not self.objectives:
            raise MindAgentDataError("能力族与目标都不可为空")


@dataclass(frozen=True)
class Workload:
    environment: str
    suites: tuple[str, ...]  # 有序:train, validation, test 按名引用,M3 起解析

    def __post_init__(self):
        if not self.environment or not self.suites:
            raise MindAgentDataError("环境与评价套件都不可为空")


@dataclass(frozen=True)
class FeedbackCfg:
    analyzer: str


@dataclass(frozen=True)
class EvaluationCfg:
    evaluator: str  # evaluation 注册表中的名字
    primary_metric: str
    secondary_metrics: tuple[str, ...] = ()


@dataclass(frozen=True)
class BudgetCfg:
    max_rounds: int
    max_candidate_evaluations: int

    def __post_init__(self):
        if type(self.max_rounds) is not int or self.max_rounds < 1:
            raise MindAgentDataError("max_rounds 必须是 >=1 的整数")
        if type(self.max_candidate_evaluations) is not int or self.max_candidate_evaluations < 1:
            raise MindAgentDataError("max_candidate_evaluations 必须是 >=1 的整数")


@dataclass(frozen=True)
class StopCfg:
    metric_target: float | None
    max_no_improve_rounds: int

    def __post_init__(self):
        if self.metric_target is not None and not 0.0 <= self.metric_target <= 1.0:
            raise MindAgentDataError("metric_target 若给,必须在 [0,1]")
        if type(self.max_no_improve_rounds) is not int or self.max_no_improve_rounds < 1:
            raise MindAgentDataError("max_no_improve_rounds 必须是 >=1 的整数")


@dataclass(frozen=True)
class EvolutionTaskSpec:
    """一份演化任务的完整冻结配置;字段闭包校验一次通过后不可变。"""

    task_id: str
    task_version: int
    agent: AgentBinding
    capability: Capability
    workload: Workload
    evolution: EvolutionPlan
    feedback: FeedbackCfg
    evaluation: EvaluationCfg
    budget: BudgetCfg
    stop: StopCfg

    def __post_init__(self):
        if not isinstance(self.task_id, str) or not self.task_id.replace("-", "").replace("_", "").isalnum():
            raise MindAgentDataError("task_id 只允许字母数字与 -_")
        if type(self.task_version) is not int or self.task_version < 1:
            raise MindAgentDataError("task_version 必须是 >=1 的整数")
        if not isinstance(self.evolution, EvolutionPlan):
            raise MindAgentDataError("evolution 必须是 EvolutionPlan(冻结核)")
        # 交叉校验:目标的算法/对象由三元组约束;评价器与分析器在 resolve 期查注册表
        # 注意:评估预算允许小于轮数——多候选算法会提前耗尽,由 runner 的
        # budget_exhausted 把守(不是规格错误)。
        if self.evolution.goal.startswith("oracle:") and not self.workload.environment:
            raise MindAgentDataError("oracle 目标需要环境")
