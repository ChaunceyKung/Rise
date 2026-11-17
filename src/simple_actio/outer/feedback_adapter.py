"""FeedbackAdapter:行动后反馈 → HumanModel 修正 + 偏好漂移检测(V4 A4;PAHF 闭环)。

漂移判据:反馈含冲突标记,而当前 top 假设是高置信合作倾向(≥阈值)。
处置(显式、可审计):被顶假设降 0.2(下限 0.3),并新增"偏好可能已漂移"
假设(0.6)——同标记更新仍单调;矛盾证据允许非单调,且写入 DriftReport。
"""
from __future__ import annotations

from dataclasses import dataclass

from simple_actio.outer.human_model import Hypothesis, HumanModel
from simple_actio.outer.state_estimator import CONFLICT_MARKERS, RuleEstimator

COOPERATION = "对方倾向于合作"
DRIFT_STATEMENT = "偏好可能已漂移"


@dataclass(frozen=True)
class DriftReport:
    detected: bool
    contradicted: str | None = None
    action_taken: str = ""
    turn: int = -1

    def to_wire(self) -> dict:
        return {"detected": self.detected, "contradicted": self.contradicted,
                "action_taken": self.action_taken, "turn": self.turn}


class FeedbackAdapter:
    def __init__(self, estimator: RuleEstimator | None = None, *, drift_threshold: float = 0.7):
        self._estimator = estimator or RuleEstimator()
        self._threshold = drift_threshold

    def observe(self, model: HumanModel, feedback_text: str, *, speaker: str, turn: int,
                outcome_hint: str | None = None) -> tuple[HumanModel, DriftReport]:
        from simple_actio.core.observation import PerceivedObservation

        obs = PerceivedObservation.from_world({}, set(), speaker=speaker, utterance=feedback_text)
        updated = self._estimator.update(model, obs, turn=turn)

        top = updated.top(limit=1)
        conflict = any(m in feedback_text for m in CONFLICT_MARKERS)
        if conflict and top and top[0].statement == COOPERATION and top[0].confidence >= self._threshold:
            hypotheses = []
            for h in updated.hypotheses:
                if h.statement == COOPERATION:
                    lowered = max(0.3, h.confidence - 0.2)  # 矛盾证据:显式非单调
                    hypotheses.append(Hypothesis(h.statement, lowered,
                                                 h.evidence + (f"drift@turn{turn}",)))
                else:
                    hypotheses.append(h)
            drift = Hypothesis(DRIFT_STATEMENT, 0.6, (f"feedback@turn{turn}:{feedback_text[:20]}",))
            hypotheses.append(drift)
            updated = HumanModel(person_id=updated.person_id, facts=updated.facts,
                                 hypotheses=tuple(hypotheses), last_updated_turn=turn)
            return updated, DriftReport(detected=True, contradicted=COOPERATION,
                                        action_taken=f"降置信至 {lowered:.1f} 并登记漂移假设",
                                        turn=turn)
        del outcome_hint
        return updated, DriftReport(detected=False, turn=turn)
