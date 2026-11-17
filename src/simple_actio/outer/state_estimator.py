"""HumanStateEstimator:从观察更新对人的估计(V4 A3;ToM-SWE 式独立组件,规则首版)。

协议独立于决策策略——"估计是否准确"可以脱离"决策是否有效"单独评测
(Survey §3.4 三能力分评的第一块)。
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from simple_actio.core.observation import PerceivedObservation
from simple_actio.outer.human_model import Hypothesis, HumanModel

AGREE_MARKERS = ("同意", "可以", "接受", "好")
CONFLICT_MARKERS = ("不行", "拒绝", "反对", "太贵")
PROPOSAL_MARKERS = ("提议", "方案")


@runtime_checkable
class HumanStateEstimator(Protocol):
    def update(self, model: HumanModel, observation: PerceivedObservation, *, turn: int) -> HumanModel: ...


class RuleEstimator:
    """规则首版:一致词→合作假设置信递增(单调,封顶);冲突词→保留假设(独立);
    提案词→事实(facts,观察可直接确认)。证据 ref 形如 turn{t}:{speaker}:{前缀}。"""

    CAP = 0.9
    STEP = 0.2
    INITIAL = 0.5

    def update(self, model, observation, *, turn):
        text = observation.utterance
        ref = f"turn{turn}:{observation.speaker}:{text[:20]}"
        facts = list(model.facts)
        if any(m in text for m in PROPOSAL_MARKERS):
            fact = f"{observation.speaker} 提出过方案:{text[:30]}"
            if fact not in facts:
                facts.append(fact)

        hypotheses = {h.statement: h for h in model.hypotheses}
        if any(m in text for m in AGREE_MARKERS):
            self._boost(hypotheses, "对方倾向于合作", ref)
        if any(m in text for m in CONFLICT_MARKERS):
            self._boost(hypotheses, "对方对当前方案持保留", ref, initial=0.6)
        return HumanModel(person_id=model.person_id, facts=tuple(facts),
                          hypotheses=tuple(hypotheses.values()), last_updated_turn=turn)

    def _boost(self, hypotheses, statement, ref, *, initial=None):
        base = initial if initial is not None else self.INITIAL
        old = hypotheses.get(statement)
        if old is None:
            hypotheses[statement] = Hypothesis(statement, base, (ref,))
        else:
            confidence = min(self.CAP, old.confidence + self.STEP)  # 单调递增,封顶
            evidence = old.evidence + (ref,) if ref not in old.evidence else old.evidence
            hypotheses[statement] = Hypothesis(statement, confidence, evidence)
