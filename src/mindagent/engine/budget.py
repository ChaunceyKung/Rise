"""EvolutionCost 聚合与固定预算收益曲线(V3 §5.2 Joint B;施工规划 M4)。

纪律:
* 未知成本**缺失表示,不填 0**——键只在至少一方真正测到时才存在;
* Ledger 侧:attempt 的 trusted usage calls/input/output tokens(提交先于
  发送的账目纪律由 actio Ledger 保证);
* Rise 侧:调用方注入只读成本记录(bridge/部署日志),形状 {key: int};
* 效率比只在**显式给定成本基**(如 model_calls)时计算,收益/成本/比值
  三列齐报,不允许只报一个虚高比值。
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EvolutionCost:
    """已测成本的冻结视图;fields 之外一律视为未测。"""

    fields: dict

    @classmethod
    def empty(cls) -> "EvolutionCost":
        return cls({})

    @classmethod
    def of(cls, measured: dict | None) -> "EvolutionCost":
        return cls({k: int(v) for k, v in (measured or {}).items() if isinstance(v, (int, float))})

    def value(self, key: str) -> int | None:
        return self.fields.get(key)

    def plus(self, other: "EvolutionCost") -> "EvolutionCost":
        merged = dict(self.fields)
        for key, value in other.fields.items():
            merged[key] = merged.get(key, 0) + value
        return EvolutionCost(merged)

    def to_wire(self) -> dict:
        return dict(self.fields)


def cost_from_ledger(snapshot: dict) -> EvolutionCost:
    """actio Ledger.snapshot() → EvolutionCost(缺失键不出现,不补零)。"""
    totals = snapshot.get("totals") or {}
    measured = {}
    for source, target in (("calls", "model_calls"), ("input_tokens", "input_tokens"),
                           ("output_tokens", "output_tokens"), ("cost_minor", "cost_minor")):
        value = totals.get(source)
        if value is not None:
            measured[target] = value
    return EvolutionCost.of(measured)


@dataclass(frozen=True)
class CurveRow:
    round_no: int
    best_primary: float | None
    cumulative: dict          # 到本轮的累计已测成本
    efficiency: float | None  # best / cumulative[basis];未给基或基未测 → None

    def to_wire(self) -> dict:
        return {"round": self.round_no, "best_primary": self.best_primary,
                "cumulative_cost": dict(self.cumulative), "efficiency": self.efficiency}


def gain_curve(rounds, *, costs: "EvolutionCost | None" = None, basis: str | None = None) -> tuple[CurveRow, ...]:
    """轮记录 → 固定预算收益曲线。

    rounds: 带 round_no 与 best_primary 的记录(RoundRecord 即可);
    costs: 轮外聚合成本(如 Ledger 账);轮内成本已在记录的 cost 字段时,
    两者按"轮内累计 ∪ 轮外增量"相加——调用方保证不重复计。
    """
    external = costs or EvolutionCost.empty()
    rows = []
    running = EvolutionCost.empty()
    for record in rounds:
        running = running.plus(EvolutionCost.of(record.cost if isinstance(record.cost, dict) else None))
        total = running.plus(external)
        basis_value = total.value(basis) if basis else None
        efficiency = None
        if basis_value and record.best_primary is not None:
            efficiency = record.best_primary / basis_value
        rows.append(CurveRow(round_no=record.round_no, best_primary=record.best_primary,
                             cumulative=total.to_wire(), efficiency=efficiency))
    return tuple(rows)
