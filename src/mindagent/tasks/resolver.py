"""Task 解析:把冻结规格装配成可执行依赖(算法/评价器/模式工厂/候选来源)。

吸收 P3 `evolution.dispatch` 的对象分派语义:scaffold 的候选来源就是
Actio 冻结候选集合;skill 走现有提案闭环(bridge 可空)。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from mindagent import algorithms, evaluation
from mindagent.errors import MindAgentDataError
from mindagent.evolution import dispatch
from mindagent.tasks.spec import EvolutionTaskSpec

AgentFactory = Callable[[], object]  # M1 的 ModeAgent 工厂;由 factory 组合根注入


@dataclass(frozen=True)
class ResolvedTask:
    spec: EvolutionTaskSpec
    algorithm: algorithms.base.EvolutionAlgorithm
    evaluator: evaluation.base.CapabilityEvaluator
    agent_factory: AgentFactory
    candidate_source: Callable[[], list]

    @property
    def task_id(self) -> str:
        return self.spec.task_id


def candidate_source(spec: EvolutionTaskSpec, *, bridge=None) -> Callable[[], list]:
    """按 target 给出候选内容来源(dispatch 的 M2 形态;M3 的 Target 适配器接管)。"""
    if spec.evolution.target == "scaffold":
        def source() -> list:
            out = dispatch(spec.evolution, findings=[])
            return out["proposals"]
        return source
    if spec.evolution.target == "skill":
        def source() -> list:
            out = dispatch(spec.evolution, findings=[], bridge=bridge)
            return list(out["drafts"])
        return source
    raise MindAgentDataError(f"target {spec.evolution.target} 的候选来源未定义(P6a)")


def resolve(spec: EvolutionTaskSpec, *, agent_factory: AgentFactory,
            algorithm_get=algorithms.base.get, evaluator_get=evaluation.base.get) -> ResolvedTask:
    if not isinstance(spec, EvolutionTaskSpec):
        raise MindAgentDataError("resolve 需要 EvolutionTaskSpec")
    algorithm = algorithm_get(spec.evolution.algorithm)
    evaluator = evaluator_get(spec.evaluation.evaluator)
    return ResolvedTask(spec=spec, algorithm=algorithm, evaluator=evaluator,
                        agent_factory=agent_factory, candidate_source=candidate_source(spec))
