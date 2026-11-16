"""EvolutionCost 聚合与账目对账(施工规划 M4 验收)。"""
from __future__ import annotations

import json
import uuid
from pathlib import Path

from actio.adapters.filesystem.common import canonical
from actio.adapters.persistence.ledger import Ledger
from actio.profiles.gateway_base import template
from mindagent.engine.budget import EvolutionCost, cost_from_ledger, gain_curve


def _settle_one(tmp_path: Path, *, inp: int = 120, out: int = 48) -> dict:
    """真 Ledger 上落一笔 settled 账,返回 snapshot(走 Ledger 真账目路径)。"""
    endpoint = "http://127.0.0.1:8931/v1"
    config = template("gpt-5.6", "tokenkey_rehearsal", endpoint)
    config["plan"] = ["compatible"]
    config["authority"] = {"id": uuid.uuid4().hex, "root": str(tmp_path / "authority")}
    ledger = Ledger(tmp_path / "budget.sqlite", config=config, campaign="m4")
    try:
        usage = {"input_tokens": inp, "output_tokens": out, "calls": 1,
                 "raw": {"prompt_tokens": inp, "completion_tokens": out, "total_tokens": inp + out},
                 "native": {"inputTokens": inp, "outputTokens": out, "totalTokens": inp + out}, "cost_minor": None}
        attempt = {"id": "op-1", "scope": {}, "state": "settled", "request": None, "binding": None,
                   "reservation": None, "response": {"status": 200}, "usage": usage,
                   "native_usage": json.dumps(usage["native"]), "reason": None}
        ledger.db.execute("INSERT INTO attempt VALUES(?,?)", ("op-1", canonical(attempt)))
        ledger.db.execute("INSERT INTO registration VALUES(?,?)", ("r:A", canonical({"id": "r:A", "run": "r"})))
        return ledger.snapshot()
    finally:
        ledger.close()


def test_cost_from_ledger_reads_measured_keys_and_omits_the_rest(tmp_path):
    snapshot = _settle_one(tmp_path)
    cost = cost_from_ledger(snapshot)
    assert cost.value("model_calls") == 1
    assert cost.value("input_tokens") == 120 and cost.value("output_tokens") == 48
    # 未测的键不存在而非 0(如 wall_time_ms/gpu_seconds 根本不出现)
    assert cost.value("wall_time_ms") is None and "wall_time_ms" not in cost.to_wire()


def test_ledger_reconciliation_matches_runner_accumulation(tmp_path):
    """验收:runner 侧累计成本与 Ledger 账目对账一致(键键相等)。"""
    from mindagent.engine.runner import RoundRecord

    ledger_cost = cost_from_ledger(_settle_one(tmp_path))
    rounds = [RoundRecord(task_id="t", round_no=1, candidates=(("c1", 0.8, {}),),
                          best_primary=0.8, cost={"model_calls": 1, "input_tokens": 120, "output_tokens": 48})]
    rows = gain_curve(rounds, basis="model_calls")
    assert rows[0].cumulative == ledger_cost.to_wire()
    assert rows[0].efficiency == 0.8  # 三列齐报:收益/成本/比值都有
    # 无基或基未测 → efficiency 缺失(None),不造虚高比值
    assert gain_curve(rounds)[0].efficiency is None
    assert gain_curve(rounds, basis="gpu_seconds")[0].efficiency is None


def test_cost_plus_only_unions_measured_keys():
    a = EvolutionCost.of({"model_calls": 2, "input_tokens": 10})
    b = EvolutionCost.of({"model_calls": 1, "gpu_seconds": 3})
    merged = a.plus(b)
    assert merged.to_wire() == {"model_calls": 3, "input_tokens": 10, "gpu_seconds": 3}
    assert EvolutionCost.empty().to_wire() == {}
    assert EvolutionCost.of(None).to_wire() == {}
    assert EvolutionCost.of({"calls": 1.5}).value("calls") == 1  # 数值收敛为 int,非数值丢弃
