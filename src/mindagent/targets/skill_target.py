"""Skill 演化对象:包装现有提案闭环,不重写生成器(施工规划 M3)。

Delta.payload 就是 skill 定义字典(Skill.from_dict 自校验);
from_findings 把 proposals.propose 的 skill 增量翻译成 Delta。
"""
from __future__ import annotations

from mindagent.errors import MindAgentDataError
from mindagent.targets.base import AppliedCandidate, Delta
from simple_actio.skills import Skill


def _serialize(skills: tuple[Skill, ...]) -> tuple:
    return tuple(sorted((s.to_dict() for s in skills), key=lambda d: (d["id"], d.get("version", 0))))


class SkillTarget:
    kind = "skill"

    def __init__(self, skills: tuple[Skill, ...] = ()):
        self._skills = tuple(skills)

    @property
    def skills(self) -> tuple[Skill, ...]:
        return self._skills

    def snapshot(self):
        from mindagent.targets.base import Snapshot

        items = _serialize(self._skills)
        from simple_actio.core.state import digest as _digest

        return Snapshot(target_kind=self.kind, items=items, digest=_digest({"kind": self.kind, "items": list(items)}))

    def validate_delta(self, delta: Delta):
        from mindagent.targets.base import ValidationResult

        if delta.target_kind != self.kind:
            return ValidationResult(False, f"对象类别不匹配:{delta.target_kind}")
        try:
            Skill.from_dict(delta.payload)
        except Exception as error:  # Skill 自校验的任何拒绝都收敛为 ValidationResult
            return ValidationResult(False, f"skill 定义被拒:{error}")
        return ValidationResult(True, None)

    def apply_candidate(self, delta: Delta) -> AppliedCandidate:
        result = self.validate_delta(delta)
        if not result.valid:
            raise MindAgentDataError(f"未验证的 Delta 不可应用:{result.reason}")
        incoming = Skill.from_dict(delta.payload)
        merged = tuple(s for s in self._skills if s.id != incoming.id) + (incoming,)
        return AppliedCandidate(target_kind=self.kind, view=tuple(merged),
                                changed_ids=(incoming.id,), notes={"operation": "replace-or-add"})


def from_findings(findings, *, bridge=None) -> tuple[Delta, ...]:
    """现有提案闭环 → Skill Delta(生成器零重写;bridge 语义同 proposals.propose)。"""
    from mindagent.proposals import propose

    drafts = propose(findings, bridge=bridge)
    deltas = []
    for draft in drafts:
        for increment in draft.increments:
            if increment["kind"] == "skill":
                deltas.append(Delta(target_kind="skill", payload=dict(increment["definition"]),
                                    origin=draft.generator))
    return tuple(deltas)
