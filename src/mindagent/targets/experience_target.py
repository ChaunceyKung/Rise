"""Experience 演化对象:吸收原方案 P6a 的经验/记忆增量线(施工规划 M3)。

Delta.payload 是 ReasoningExperience 定义字典(自校验);记忆增量(memory
projection)的写路径归 factory 的 D1 桥(经 actio_projection),M5 Demo 接线;
本对象只管非参数的经验库副本视图。
"""
from __future__ import annotations

from mindagent.errors import MindAgentDataError
from mindagent.targets.base import AppliedCandidate, Delta
from simple_actio.experience import ReasoningExperience


def _serialize(experiences) -> tuple:
    return tuple(sorted((e.to_dict() for e in experiences), key=lambda d: d["id"]))


class ExperienceTarget:
    kind = "experience"

    def __init__(self, experiences: tuple[ReasoningExperience, ...] = ()):
        self._experiences = tuple(experiences)

    @property
    def experiences(self) -> tuple[ReasoningExperience, ...]:
        return self._experiences

    def snapshot(self):
        from mindagent.targets.base import Snapshot
        from simple_actio.core.state import digest as _digest

        items = _serialize(self._experiences)
        return Snapshot(target_kind=self.kind, items=items, digest=_digest({"kind": self.kind, "items": list(items)}))

    def validate_delta(self, delta: Delta):
        from mindagent.targets.base import ValidationResult

        if delta.target_kind != self.kind:
            return ValidationResult(False, f"对象类别不匹配:{delta.target_kind}")
        try:
            ReasoningExperience.from_dict(delta.payload)
        except Exception as error:
            return ValidationResult(False, f"experience 定义被拒:{error}")
        return ValidationResult(True, None)

    def apply_candidate(self, delta: Delta) -> "AppliedCandidate":
        result = self.validate_delta(delta)
        if not result.valid:
            raise MindAgentDataError(f"未验证的 Delta 不可应用:{result.reason}")
        incoming = ReasoningExperience.from_dict(delta.payload)
        merged = tuple(e for e in self._experiences if e.id != incoming.id) + (incoming,)
        return AppliedCandidate(target_kind=self.kind, view=tuple(merged),
                                changed_ids=(incoming.id,), notes={"operation": "replace-or-add"})


def from_findings(findings) -> tuple[Delta, ...]:
    """行为发现 → 经验草案(规则模板:每条发现一条"先处理该信号"的回退经验)。"""
    deltas = []
    for finding in findings:
        payload = {
            "id": f"exp-candidate-{finding.signal}", "version": 1,
            "pattern": finding.pattern,
            "applies_when": {"signal": finding.signal},
            "tiers": {"primary": {"when": {"signal": finding.signal}, "instructions": [f"遇到{finding.signal}先处理该信号"]},
                      "secondary": {"when": {"signal": "first_turn"}, "instructions": ["开场先澄清目标"]},
                      "fallback": {"when": None, "instructions": ["按默认策略回应"]}},
        }
        deltas.append(Delta(target_kind="experience", payload=payload, origin="rule_template.v1"))
    return tuple(deltas)
