"""Inner Actio:模拟人的行为与决策(V3 §2.2)。首批两机制(Q1):goal-driven + belief-driven。"""
from __future__ import annotations

from dataclasses import dataclass

from simple_actio.core.observation import PerceivedObservation
from simple_actio.core.state import MindState


@dataclass(frozen=True)
class GoalDriven:
    """显式目标驱动:目标未满足且观察出现机会时,给出朝向目标的指令。"""

    goals: tuple[str, ...]
    name: str = "goal_driven"

    def apply(self, state: MindState, observation: PerceivedObservation) -> tuple[str, ...] | None:
        active = state.goals or self.goals
        if not active:
            return None
        opportunity = any("机会" in str(v) or "提议" in str(v) for v in observation.visible_facts.values())
        if not opportunity and "提议" not in observation.utterance:
            return None
        return tuple(f"朝着你的目标行动:{goal}" for goal in active[:2])


@dataclass(frozen=True)
class BeliefDriven:
    """信念驱动:只依据自己相信的信息行动;与信念冲突的观察要显式存疑。"""

    beliefs: tuple[str, ...]
    name: str = "belief_driven"

    def apply(self, state: MindState, observation: PerceivedObservation) -> tuple[str, ...] | None:
        held = state.beliefs or self.beliefs
        if not held:
            return None
        return tuple(f"只依据你的信念行动:{belief}" for belief in held[:2])


def policy_for(persona, mechanisms, *, situation: str | None = None):
    """按 PersonaSpec 的情境机制权重排序机制(CAPS):权重高者先叠加。

    未声明权重的机制按传入序跟在已声明者之后;等权时稳定(传入序)。
    """
    from simple_actio.core.policy import CombinedPolicy

    weights = persona.mechanism_weights(situation)
    declared = sorted((m for m in mechanisms if m.name in weights),
                      key=lambda m: (-weights[m.name], m.name))
    rest = tuple(m for m in mechanisms if m.name not in weights)
    return CombinedPolicy(tuple(declared) + rest)


def persona_diff(persona, observed_behaviors, *, situation: str | None = None):
    """校准钩子(Q1 规则版,TinyTroupe 思想):声明权重 vs 实际触发机制的一致性。

    observed_behaviors: [{"mechanisms": [...], "situation": str?}, ...]
    一致 = 该行为的首个触发机制是 persona 在该情境声明的最高权重机制。
    """
    consistent = inconsistent = 0
    examples = []
    weights = persona.mechanism_weights(situation)
    for behavior in observed_behaviors:
        fired = behavior.get("mechanisms", ())
        if not fired:
            continue
        beh_situation = behavior.get("situation") or situation
        beh_weights = persona.mechanism_weights(beh_situation)
        if beh_weights:
            top = sorted(beh_weights, key=lambda k: (-beh_weights[k], k))[0]
            ok = fired[0] == top
        else:
            ok = True  # persona 未声明该情境:无冲突证据
        if ok:
            consistent += 1
        else:
            inconsistent += 1
            examples.append({"expected_top": top if beh_weights else None, "fired": fired[0]})
    return {"persona_id": persona.persona_id, "situation": situation,
            "consistent": consistent, "inconsistent": inconsistent,
            "examples": examples, "declared_weights": weights}
