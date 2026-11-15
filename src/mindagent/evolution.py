"""演化三元组(target/algorithm/goal):MindAgent 配置化演化的接线层(方案 D6)。

Actio 带来的是"严格准入的演化件":候选提案/决策状态机(actio.domain.candidate)、
独立测量 oracle(actio.measurement.oracle)、预算制网关(actio.harness)。
Rise 已有的是技能提案闭环(mindagent.proposals → 验证 → 门②收录)。
本模块把两者按三元组组织起来,供 factory 开关装配:

* EvolutionTarget  —— 演化对象:scaffold(prompt_scaffold 变异位,Actio 式准入) |
  skill(现有提案闭环)| memory(P6a 预留,V1 显式拒绝不谎报)
* EvolutionAlgorithm —— manual(V1:人工/fixture 提案 + decide 准入)|
  gateway(V2 预留:GatewayRuntime 预算制提案,只定义接缝不实现)
* EvolutionGoal —— oracle:scheduling | oracle:trading(有限域指标族)|
  diag:gain(诊断增益,委托 recipestore.gain)

纪律沿用 Actio POLICY:production_activation 恒 False;准入不通过就没有激活路径。
"""
from __future__ import annotations

from dataclasses import dataclass

from actio.domain import candidate as scaffold
from actio.measurement import oracle
from mindagent.errors import MindAgentDataError

TARGETS = ("scaffold", "skill", "memory")
ALGORITHMS = ("manual", "gateway")
GOALS = ("oracle:scheduling", "oracle:trading", "diag:gain")

SCAFFOLD_MUTATION_SEAT = "prompt_scaffold"
SKILL_MUTATION_SEAT = "skill_library"
MEMORY_MUTATION_SEAT = "memory_store"


@dataclass(frozen=True)
class EvolutionPlan:
    """一轮演化的冻结配置;factory 开关解析后不可变。"""

    target: str
    algorithm: str = "manual"
    goal: str = "oracle:scheduling"

    def __post_init__(self):
        if self.target not in TARGETS:
            raise MindAgentDataError(f"未知演化对象 {self.target};可选 {TARGETS}")
        if self.algorithm not in ALGORITHMS:
            raise MindAgentDataError(f"未知演化算法 {self.algorithm};可选 {ALGORITHMS}")
        if self.goal not in GOALS:
            raise MindAgentDataError(f"未知演化目标 {self.goal};可选 {GOALS}")
        if self.target == "memory":
            raise MindAgentDataError("memory 增量生成器按方案 P6a 预留;V1 不接受该 target")
        if self.algorithm == "gateway":
            raise MindAgentDataError("gateway 提案器是 V2 接缝;V1 只有人工/fixture 提案 + decide 准入")

    @property
    def mutation_seat(self) -> str:
        return {"scaffold": SCAFFOLD_MUTATION_SEAT, "skill": SKILL_MUTATION_SEAT, "memory": MEMORY_MUTATION_SEAT}[self.target]


def plan_from_switches(target: str | None, *, goal: str | None = None) -> EvolutionPlan:
    """factory 开关 → 冻结计划;未配置时默认 scaffold:manual:oracle:scheduling。"""
    return EvolutionPlan(target=target or "scaffold", algorithm="manual", goal=goal or "oracle:scheduling")


# ---------------- 演化目标:独立测量 ----------------

def measure(goal: str, contract: dict, actions: dict) -> dict:
    """按 goal 调用对应测量器;oracle 族是有限域独立指标,diag:gain 委托 recipestore。"""
    if goal in ("oracle:scheduling", "oracle:trading"):
        if contract.get("family") != goal.split(":", 1)[1]:
            raise MindAgentDataError(f"合同 family={contract.get('family')!r} 与目标 {goal} 不符")
        return oracle.evaluate(contract, actions)
    # diag:gain 委托 recipestore(需要 GitStore 与 run 维度,调用方组装后传入)
    raise MindAgentDataError("diag:gain 走 recipestore.compute_gain(store, run_id, dimension),不经本函数")


def gain_signature(goal: str, report: dict) -> float | None:
    """从测量报告提取可比增益(演化决策的输入);oracle 族用 omniscient_regret 的负数,
    diag:gain 用增益本身。无 joint 结果时返回 None(insufficient evidence)。"""
    if goal.startswith("oracle:"):
        regret = report.get("omniscient_regret")
        return None if regret is None else -float(regret)
    return report.get("gain")


# ---------------- 演化对象:scaffold 准入链(Actio 式) ----------------

def admit_scaffold(proposal_value: dict, *, complete: bool, evidence_kind: str,
                   diagnostics: dict, gain: float | None, parent: dict | None = None) -> dict:
    """scaffold 目标的完整准入链:静态校验 → decide;产出 candidate-decision.v1。

    校验非根提案时必须给出 parent(C1 的父是 B0,上游语义)。production_activation
    恒 False 由 POLICY 保证(T-M-05);这里不再提供激活分支。
    """
    static = scaffold.validate_proposal(proposal_value, parent)
    return scaffold.decide(static_valid=static["valid"], complete=complete,
                           evidence_kind=evidence_kind, diagnostics=diagnostics, synthetic_gain=gain)


# ---------------- 演化对象分派 ----------------

def dispatch(plan: EvolutionPlan, findings, bridge=None):
    """按 target 分派到对应提案器;scaffold 走 Actio 冻结 fixture 集合,
    skill 走现有闭环(规则模板或桥接);memory 见 P6a。"""
    if plan.target == "scaffold":
        return {"seat": plan.mutation_seat, "proposals": [scaffold.baseline(), scaffold.candidate()],
                "rejected_fixtures": scaffold.rejected_fixtures()}
    from mindagent.proposals import propose

    drafts = propose(findings, bridge=bridge)
    return {"seat": plan.mutation_seat, "drafts": drafts}
