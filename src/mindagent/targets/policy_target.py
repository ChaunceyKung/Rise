"""Policy 演化对象:CAPS 机制配置(机制权重)作为可演化对象(V4 A6)。

三层规划"MindAgent 演化 Skill/Policy/Dynamics"的最后一块:Delta.payload
是完整的 PersonaSpec wire 字典(机制权重表在其 situation_mechanisms);
apply 只产新 PersonaSpec 视图,正式生效仍需门②收录(与 skill/experience
同纪律)。from_findings 把行为发现翻成机制权重草案(规则首版)。
"""
from __future__ import annotations

from mindagent.errors import MindAgentDataError
from mindagent.targets.base import Delta
from simple_actio.cognition.persona import PersonaSpec

# 信号 → 建议提升的机制(规则首版;来源 Survey/TinyTroupe 的"缺陷驱动调权"思想)
SIGNAL_MECHANISMS = {
    "emotion_high": "belief_driven",    # 情绪信号 → 信念机制优先
    "no_new_information": "goal_driven",  # 无新信息 → 目标机制优先
}


class PolicyTarget:
    kind = "policy"

    def __init__(self, persona: PersonaSpec):
        self._persona = persona

    @property
    def persona(self) -> PersonaSpec:
        return self._persona

    def snapshot(self):
        from mindagent.targets.base import Snapshot
        from simple_actio.core.state import digest as _digest

        items = (self._persona.to_wire(),)
        return Snapshot(target_kind=self.kind, items=items, digest=_digest({"kind": self.kind, "items": list(items)}))

    def validate_delta(self, delta: Delta):
        from mindagent.targets.base import ValidationResult

        if delta.target_kind != self.kind:
            return ValidationResult(False, f"对象类别不匹配:{delta.target_kind}")
        try:
            candidate = PersonaSpec.from_wire(delta.payload)
        except Exception as error:
            return ValidationResult(False, f"persona 定义被拒:{error}")
        if candidate.persona_id != self._persona.persona_id:
            return ValidationResult(False, "演化不改 persona_id(同一身份的配置演化)")
        return ValidationResult(True, None)

    def apply_candidate(self, delta: Delta):
        from mindagent.targets.base import AppliedCandidate

        result = self.validate_delta(delta)
        if not result.valid:
            raise MindAgentDataError(f"未验证的 Delta 不可应用:{result.reason}")
        incoming = PersonaSpec.from_wire(delta.payload)
        return AppliedCandidate(target_kind=self.kind, view=(incoming,),
                                 changed_ids=(incoming.persona_id,),
                                 notes={"operation": "replace-policy",
                                        "weights": incoming.situation_mechanisms})


def from_findings(findings, base: PersonaSpec, *, situation: str = "negotiation") -> tuple[Delta, ...]:
    """行为发现 → 机制权重草案:命中信号的机制在给定情境 +2(叠加封顶 5)。"""
    deltas = []
    bumped: dict[str, int] = dict(base.situation_mechanisms.get(situation, {}))
    touched = False
    for finding in findings:
        mechanism = SIGNAL_MECHANISMS.get(finding.signal)
        if mechanism is None:
            continue
        bumped[mechanism] = min(5, bumped.get(mechanism, 0) + 2)
        touched = True
    if not touched:
        return ()
    payload = {**base.to_wire(), "version": base.version + 1,
               "situation_mechanisms": {**base.situation_mechanisms, situation: bumped}}
    deltas.append(Delta(target_kind="policy", payload=payload, origin="signal_weight_v1"))
    return tuple(deltas)
