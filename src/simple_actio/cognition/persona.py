"""PersonaSpec:稳定个体参数 + 情境条件化机制权重(V4 A2;CAPS,三层规划 §3/§8)。

只放长期稳定的东西(traits/preferences/capacities);随情境变化的
信念/目标/情绪在 CognitiveState(三时间尺度)。situation_mechanisms 是
CAPS 的工程化:situation → 机制权重,决定该情境下哪些行为机制优先。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from simple_actio.core.state import _check


@dataclass(frozen=True)
class PersonaSpec:
    persona_id: str
    version: int = 1
    traits: dict = field(default_factory=dict)            # {"openness": "high", ...}
    preferences: tuple[str, ...] = ()
    capacities: tuple[str, ...] = ()
    situation_mechanisms: dict = field(default_factory=dict)  # {"conflict": {"belief_driven": 2}}

    def __post_init__(self):
        if not isinstance(self.persona_id, str) or not self.persona_id:
            raise ValueError("persona_id 必须是非空字符串")
        if type(self.version) is not int or self.version < 1:
            raise ValueError("version 必须是 >=1 的整数")
        for name, value in (("traits", self.traits), ("situation_mechanisms", self.situation_mechanisms)):
            _check(value)
            object.__setattr__(self, name, dict(value))
        for name in ("preferences", "capacities"):
            v = getattr(self, name)
            if not isinstance(v, tuple) or not all(isinstance(x, str) and x for x in v):
                raise ValueError(f"{name} 必须是非空字符串元组")
        for situation, weights in self.situation_mechanisms.items():
            if not isinstance(weights, dict) or not all(isinstance(k, str) and isinstance(w, int) for k, w in weights.items()):
                raise ValueError(f"situation_mechanisms[{situation!r}] 必须是 {机制名: 整数权重}")

    def mechanism_weights(self, situation: str | None) -> dict:
        """给定情境的机制权重;未声明时为空(等权,按传入序)。"""
        return dict(self.situation_mechanisms.get(situation or "", {}))

    def to_wire(self) -> dict:
        return {"persona_id": self.persona_id, "version": self.version,
                "traits": self.traits, "preferences": list(self.preferences),
                "capacities": list(self.capacities),
                "situation_mechanisms": self.situation_mechanisms}

    @classmethod
    def from_wire(cls, value: dict) -> "PersonaSpec":
        expected = {"persona_id", "version", "traits", "preferences", "capacities", "situation_mechanisms"}
        if not isinstance(value, dict) or set(value) != expected:
            raise ValueError("PersonaSpec wire 字段不匹配")
        return cls(persona_id=value["persona_id"], version=value["version"], traits=value["traits"],
                   preferences=tuple(value["preferences"]), capacities=tuple(value["capacities"]),
                   situation_mechanisms=value["situation_mechanisms"])
