"""联合实验的 Gap 指标评价器与 RunResult 版本化投影(V4 A5)。

指标(Survey §3.4 三能力分评):state_accuracy(推断对不对)/
adaptation_latency(漂移后几轮跟上)/task_utility(最终决策是否贴真值)/
cost(轮数)。缺失不补零。投影规则与 recipestore.actio_lineage_bridge 同源:
幂等(同哈希零提交)、版本化(变化→version+1)。
"""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

from mindagent.evaluation.base import CandidateEvaluation
from mindagent.joint.harness import OUTER_ARMS, JointScenario, build_outer, run_joint


class JointGapEvaluator:
    """按 candidate.delta_meta['arm'] 组装 Outer 臂并跑联合情境,出 Gap 指标。"""

    def __init__(self, name: str, scenario: JointScenario, *, objectives=("完成清理",)):
        self.name = name
        self._scenario = scenario
        self._objectives = objectives

    def evaluate(self, task, candidate, agent=None) -> CandidateEvaluation:
        arm = candidate.delta_meta.get("arm")
        if arm not in OUTER_ARMS:
            raise ValueError(f"联合评价器只吃 Outer 臂 {OUTER_ARMS},得到 {arm!r}")
        outer = build_outer(arm, objectives=self._objectives, person_id="human")
        record = run_joint(self._scenario, outer, arm=arm)
        if not record.isolation_ok:
            raise AssertionError(f"隔离审计失败:{record.isolation_violations}")

        sc = self._scenario
        final_truth = sc.ground_truth(len(sc.human_turns))
        top = record.top_hypothesis
        state_accuracy = 0.0
        if top is not None:
            state_accuracy = 1.0 if _compatible(top, final_truth, sc.accept_hypotheses) else 0.0

        latency = None
        if sc.drift_turn is not None and arm == "O3":
            for turn, decision in enumerate(record.decisions, start=1):
                if turn >= sc.drift_turn and _reflects(decision, sc.drifted_preference):
                    latency = turn - sc.drift_turn
                    break

        utility = 1.0 if (top is not None and _compatible(top, final_truth, sc.accept_hypotheses)) else 0.0
        primary = round((state_accuracy + utility) / 2, 4)  # 主指标∈[0,1]
        secondary = {"state_accuracy": state_accuracy, "task_utility": utility,
                     "adaptation_latency": latency, "isolation_ok": record.isolation_ok}
        cost = {"model_calls": 0, "rounds": len(sc.human_turns)}  # scripted 后端零模型调用
        return CandidateEvaluation(candidate_id=candidate.candidate_id, primary=primary,
                                   secondary=secondary, cost=cost)


def _compatible(hypothesis: str, truth: str, accept=()) -> bool:
    key = truth[:4]
    return (key in hypothesis or hypothesis in truth or truth == hypothesis
            or any(word in hypothesis for word in accept))


def _reflects(decision: dict, preference: str | None) -> bool:
    rationale = decision.get("rationale") or {}
    refs = rationale.get("belief_refs", ())
    return any(preference and preference[:4] in ref for ref in refs)


# ---------------- RunResult → envelope 投影(与 D2 桥同规则) ----------------

RUN_TYPE = "actio.evolution_run"
RUN_DIR = "actio/runs"


def project_run_result(git, result, *, store_key: str = "joint-demo") -> str:
    from controlplane.envelope import Envelope, OwnerRef

    wire = result.to_wire()
    wire_hash = hashlib.sha256(json.dumps(wire, sort_keys=True, ensure_ascii=False,
                                          allow_nan=False).encode()).hexdigest()
    path = f"{RUN_DIR}/{store_key}.yml"
    version = 1
    if git.exists(path):
        existing = git.read_product(path)
        if existing.payload.get("run_hash") == wire_hash:
            return path  # 幂等:结果未变零提交
        version = existing.version + 1
    env = Envelope(id=f"actio-run-{store_key[:12]}", type=RUN_TYPE, version=version,
                   created_at=datetime.now(UTC).isoformat(timespec="seconds"),
                   created_by=OwnerRef(), status="final", schema_version=1,
                   payload={"run_hash": wire_hash, "result": wire})
    git.write_product(path, env, f"actio: project joint run v{version} ({wire_hash[:12]})")
    return path
