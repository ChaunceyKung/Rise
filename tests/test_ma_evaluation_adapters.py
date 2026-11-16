"""evaluation 真 adapter 测试:oracle(接 P3 measure)与 diag(归一纪律)。"""
from __future__ import annotations

import pytest

from mindagent.algorithms.base import Candidate
from mindagent.errors import MindAgentDataError
from mindagent.evaluation.diag import DiagGainEvaluator
from mindagent.evaluation.oracle import OracleEvaluator

SCHEDULING = {
    "family": "scheduling",
    "public": {"slots": ["morning", "afternoon"], "open": ["morning"]},
    "private": {
        "A": {"available": ["morning"], "utility": {"morning": 8, "afternoon": 2}},
        "B": {"available": ["morning"], "utility": {"morning": 6, "afternoon": 1}},
    },
}


def _candidate(cid="c1"):
    return Candidate(candidate_id=cid)


def test_oracle_evaluator_rewards_agreement_and_marks_missing_joint():
    hit = OracleEvaluator("oracle-sched", "scheduling",
                          lambda task, candidate, agent: (SCHEDULING, {"A": "propose:morning", "B": "accept"}))
    report = hit.evaluate(None, _candidate())
    assert report.primary == 1.0 and report.secondary["joint"] is True and report.secondary["regret"] == 0

    def _unseen(task, candidate, agent):
        return SCHEDULING, {"A": "propose:morning", "B": "never-said"}

    malformed = OracleEvaluator("oracle-sched", "scheduling", _unseen)
    missing = malformed.evaluate(None, _candidate())
    assert missing.primary == 0.0 and missing.secondary["regret"] is None  # 缺 joint 显式可见


def test_oracle_evaluator_refuses_family_mismatch():
    trader = OracleEvaluator("oracle-trade", "trading", lambda t, c, a: (SCHEDULING, {}))
    with pytest.raises(ValueError, match="不符"):
        trader.evaluate(None, _candidate())


def test_diag_evaluator_passes_normalized_gain_and_refuses_rest():
    ok = DiagGainEvaluator("diag-ok", lambda t, c: 0.42)
    assert ok.evaluate(None, _candidate()).primary == 0.42
    with pytest.raises(MindAgentDataError, match="缺失"):
        DiagGainEvaluator("diag-missing", lambda t, c: None).evaluate(None, _candidate())
    with pytest.raises(MindAgentDataError, match="归一"):
        DiagGainEvaluator("diag-raw", lambda t, c: 7.5).evaluate(None, _candidate())
