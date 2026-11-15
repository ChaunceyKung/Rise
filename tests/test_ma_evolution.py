"""MindAgent 演化三元组的测试(方案 §5.3 T-M 用例族)。

golden 摘要(B0/C1/POLICY)在两仓各自解释器下生成并比对一致后固化于此——
它们锁的是 Actio 冻结候选语义在 Rise 侧零漂移。
"""
from __future__ import annotations

import pytest

from actio.contracts.json import digest
from mindagent.errors import MindAgentDataError
from mindagent.evolution import (
    admit_scaffold,
    dispatch,
    gain_signature,
    measure,
    plan_from_switches,
)

SCHEDULING = {
    "family": "scheduling",
    "public": {"slots": ["morning", "afternoon"], "open": ["morning"]},
    "private": {
        "A": {"available": ["morning"], "utility": {"morning": 8, "afternoon": 2}},
        "B": {"available": ["morning"], "utility": {"morning": 6, "afternoon": 1}},
    },
}


# ---------------- T-M-01:准入状态机逐分支 ----------------

@pytest.mark.parametrize(("kwargs", "expected_state"), [
    (dict(static_valid=False, complete=True, evidence_kind="policy_fixture", diagnostics={}), "reject"),
    (dict(static_valid=True, complete=False, evidence_kind="policy_fixture", diagnostics={}), "infrastructure_failure"),
    (dict(static_valid=True, complete=True, evidence_kind="local_fixture", diagnostics={}), "insufficient_evidence"),
    (dict(static_valid=True, complete=True, evidence_kind="policy_fixture",
          diagnostics={"hard_failure": True}, synthetic_gain=None), "reject"),
    (dict(static_valid=True, complete=True, evidence_kind="policy_fixture",
          diagnostics={}, synthetic_gain=None), "insufficient_evidence"),
    (dict(static_valid=True, complete=True, evidence_kind="policy_fixture",
          diagnostics={}, synthetic_gain=0), "insufficient_evidence"),
    (dict(static_valid=True, complete=True, evidence_kind="policy_fixture",
          diagnostics={}, synthetic_gain=-1), "reject"),
    (dict(static_valid=True, complete=True, evidence_kind="policy_fixture",
          diagnostics={}, synthetic_gain=1), "pass"),
])
def test_decide_state_machine_covers_every_branch(kwargs, expected_state):
    from actio.domain.candidate import decide, validate_decision

    decision = decide(**kwargs)
    assert decision["state"] == expected_state
    assert decision["eligible_for_activation"] is False  # T-M-05:无激活路径
    assert validate_decision(decision) == decision  # 决策可独立重算


def test_production_activation_is_frozen_off():
    from actio.domain.candidate import POLICY

    assert POLICY["production_activation"] is False
    assert digest(POLICY) == "b8dea96749e43496d38bb9083b220c634898b9e834909ce0aeeae370b816469b"


# ---------------- T-M-04:B0/C1 golden(跨仓字节一致) ----------------

def test_b0_c1_frozen_fixtures_match_the_actio_repository_golden():
    from actio.domain.candidate import baseline, candidate

    assert digest(baseline()) == "84e9ab99465ada9c47cc17334c305a5f493524f042a218d4be4732c054462fe5"
    assert digest(candidate()) == "e381eb3dd58494dde035b7c301331bdc3f5cde8af18c644bf6e7301087a130b2"


# ---------------- T-M-02:演化对象分派 ----------------

def test_plan_rejects_memory_target_and_gateway_algorithm_for_v1():
    with pytest.raises(MindAgentDataError, match="P6a"):
        plan_from_switches("memory")
    with pytest.raises(MindAgentDataError, match="V2"):
        plan_from_switches("scaffold", goal="oracle:scheduling").__class__(target="scaffold", algorithm="gateway")


def test_dispatch_routes_scaffold_to_actio_candidates_and_skill_to_proposals():
    scaffold_plan = plan_from_switches("scaffold")
    out = dispatch(scaffold_plan, findings=[])
    assert out["seat"] == "prompt_scaffold"
    assert [p["name"] for p in out["proposals"]] == ["B0", "C1"]
    assert all(v["valid"] is False for v in (validate_for(r) for r in out["rejected_fixtures"]))

    from mindagent.analysis import BehaviorFinding
    from mindagent.evolution import EvolutionPlan

    finding = BehaviorFinding(id="f1", signal="emotion_high", pattern="高情绪时直接说理",
                              support=3, ratio=0.5, episode_refs=("e1", "e2", "e3"))
    out2 = dispatch(EvolutionPlan(target="skill"), findings=[finding])
    assert out2["seat"] == "skill_library"
    assert out2["drafts"][0].increments[0]["kind"] == "skill"


def validate_for(rejected):
    from actio.domain.candidate import validate_proposal

    return validate_proposal(rejected)


# ---------------- T-M-03:演化目标接线 ----------------

def test_measure_oracle_scheduling_and_gain_signature():
    report = measure("oracle:scheduling", SCHEDULING, {"A": "propose:morning", "B": "accept"})
    assert report["joint_achieved"] is True
    assert report["utilities"] == {"A": 8, "B": 6}
    assert report["omniscient_regret"] == 0
    assert gain_signature("oracle:scheduling", report) == 0.0
    # 拒绝达成 = 全遗憾(regret=bound);只有格式不完备才没有 regret(insufficient)
    declined = measure("oracle:scheduling", SCHEDULING, {"A": "propose:morning", "B": "decline"})
    assert declined["joint_achieved"] is False
    assert declined["omniscient_regret"] == 14
    assert gain_signature("oracle:scheduling", declined) == -14.0
    malformed = measure("oracle:scheduling", SCHEDULING, {"A": "propose:morning"})  # B 缺席
    assert malformed["format"]["B"] is None
    assert gain_signature("oracle:scheduling", malformed) is None


def test_measure_refuses_family_and_goal_mismatch():
    with pytest.raises(MindAgentDataError, match="不符"):
        measure("oracle:trading", SCHEDULING, {"A": "x", "B": "accept"})


def test_admit_scaffold_passes_clean_candidate_with_positive_gain():
    from actio.domain.candidate import candidate

    from actio.domain.candidate import baseline

    decision = admit_scaffold(candidate(), complete=True, evidence_kind="policy_fixture",
                              diagnostics={}, gain=1.0, parent=baseline())
    assert decision["state"] == "pass"
    assert decision["reason"] == "synthetic_positive_branch_only"
