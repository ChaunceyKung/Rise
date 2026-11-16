"""PersonaSpec → CognitiveState 初始状态(V4 A2;三层规划 §11.2 缺口 A 的解)。

稳定参数落 long_term(traits/preferences/capacities);情境初值
(初始信念/目标)由调用方给,不藏在 persona 里——CAPS 的"稳定层"与
"情境条件化"分离在这里兑现。
"""
from __future__ import annotations

from simple_actio.cognition.beliefs import Belief
from simple_actio.cognition.goals import Goal
from simple_actio.cognition.persona import PersonaSpec
from simple_actio.core.state import CognitiveState


def initialize_state(persona: PersonaSpec, subject: str, *,
                     goals: tuple[Goal, ...] = (),
                     beliefs: tuple[Belief, ...] = ()) -> CognitiveState:
    return CognitiveState(
        subject=subject,
        goals=tuple(g.description for g in goals if g.status == "active"),
        beliefs=tuple(b.statement for b in beliefs),
        long_term={"persona_id": persona.persona_id, "persona_version": persona.version,
                   "traits": persona.traits, "preferences": list(persona.preferences),
                   "capacities": list(persona.capacities)},
        mid_term={"goal_status": {g.description: g.status for g in goals}},
    )
