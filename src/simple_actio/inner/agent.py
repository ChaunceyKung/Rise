"""Inner/Outer 的公共骨架:机制策略 + MindState 维护 + 经指导语装饰器驱动的实例。

复用原则:模式 agent 只包装 SimpleActioInstance——话语/记忆/技能/轨迹全部来自
底座;模式的全部影响经 ModeDirectiveBackend 注入的指导语发生,因此
"收益是否只来自路由变化"可以直接从指令与激活轨迹审计(V3 §11 验证要求)。
"""
from __future__ import annotations

from typing import Callable

from simple_actio.core.observation import PerceivedObservation
from simple_actio.core.policy import CombinedPolicy
from simple_actio.core.state import MindState


class ModeAgent:
    """单模式运行体。子类给 build_directive;simulate_step/decide_for_human 都走它。"""

    def __init__(self, instance, policy: CombinedPolicy, *, subject: str,
                 state_transition: Callable[[MindState, PerceivedObservation, str], MindState] | None = None):
        self._instance = instance
        self.policy = policy
        self.state = MindState(subject=subject)
        self._transition = state_transition or self._default_transition

    @staticmethod
    def _default_transition(state: MindState, observation: PerceivedObservation, utterance: str) -> MindState:
        added = (f"{observation.speaker} 说过:{observation.utterance[:40]}",)
        return state.advanced(added_beliefs=added, last_action=utterance[:40] or None)

    def _step(self, observation: PerceivedObservation, persona, scenario, history, speaker_slot):
        directive = self.policy.decide(self.state, observation)
        self._instance.backend.set_directive(directive.instructions)
        utterance, inner_thought, trace = self._instance.respond(persona, scenario, history, speaker_slot)
        self.state = self._transition(self.state, observation, utterance)
        from simple_actio.core.action import Decision

        return Decision(mode=self.mode, utterance=utterance, inner_thought=inner_thought,
                        directive=directive.instructions, mechanisms=directive.mechanisms, trace=trace)

    mode: str = "inner"

    def simulate_step(self, observation: PerceivedObservation, persona, scenario, history, speaker_slot):
        """Inner 上层接口(V3 §2.4):这个人下一步会怎么做。"""
        return self._step(observation, persona, scenario, history, speaker_slot)
