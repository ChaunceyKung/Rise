"""Inner/Outer 的公共骨架:机制策略 + MindState 维护 + 经指导语装饰器驱动的实例。

复用原则:模式 agent 只包装 SimpleActioInstance——话语/记忆/技能/轨迹全部来自
底座;模式的全部影响经 ModeDirectiveBackend 注入的指导语发生,因此
"收益是否只来自路由变化"可以直接从指令与激活轨迹审计(V3 §11 验证要求)。
"""
from __future__ import annotations


from simple_actio.core.dynamics import CognitiveDynamics, RuleDynamics, StateDelta
from simple_actio.core.intent import StepResult
from simple_actio.core.observation import PerceivedObservation
from simple_actio.core.policy import CombinedPolicy
from simple_actio.core.state import CognitiveState
from simple_actio.core.trace import CognitiveTrace


class ModeAgent:
    """单模式运行体,实现 ActioAgent 协议(V4 A1)。

    状态更新经 CognitiveDynamics(默认 RuleDynamics;旧 callable 形态自动包装),
    每步产出 StepResult(带 StateDelta 与结构化依据)与 CognitiveTrace 旁路。
    """

    def __init__(self, instance, policy: CombinedPolicy, *, subject: str,
                 state_transition=None, dynamics: CognitiveDynamics | None = None):
        self._instance = instance
        self.policy = policy
        self.state = CognitiveState(subject=subject)
        self._dynamics = dynamics or self._wrap(state_transition) if state_transition else RuleDynamics()
        self.last_trace: CognitiveTrace | None = None

    @staticmethod
    def _wrap(transition):
        class _CallableDynamics:
            def update(self, state, observation, *, action=None):
                after = transition(state, observation, action or "")
                return after, StateDelta(fields=("beliefs", "last_action"), source="callable_transition",
                                         evidence={}, time_scale="mid")
        return _CallableDynamics()

    def _step(self, observation: PerceivedObservation, persona, scenario, history, speaker_slot):
        directive = self.policy.decide(self.state, observation)
        self._instance.backend.set_directive(directive.instructions)
        utterance, inner_thought, trace = self._instance.respond(persona, scenario, history, speaker_slot)
        self.state, delta = self._dynamics.update(self.state, observation, action=utterance)
        self.last_trace = CognitiveTrace(mode=self.mode, turn=self.state.turn,
                                         action_type="utterance",
                                         directives=directive.instructions,
                                         mechanisms=directive.mechanisms,
                                         state_delta=(delta,),
                                         rationale={"mechanisms": list(directive.mechanisms),
                                                    "evidence_level": "structurally_derived"})
        return StepResult(mode=self.mode, utterance=utterance, inner_thought=inner_thought,
                          directive=directive.instructions, mechanisms=directive.mechanisms, trace=trace,
                          state_delta=(delta,),
                          rationale_summary={"mechanisms": list(directive.mechanisms),
                                             "evidence_level": "structurally_derived"})

    mode: str = "inner"

    # ---- ActioAgent 协议(V4 A1) ----

    def step(self, observation, persona, scenario, history, speaker_slot):
        return self._step(observation, persona, scenario, history, speaker_slot)

    def snapshot(self) -> dict:
        return {"mode": self.mode, "subject": self.state.subject, "state": self.state.to_wire()}

    def restore(self, snapshot: dict) -> None:
        if snapshot.get("mode") != self.mode or snapshot.get("subject") != self.state.subject:
            raise ValueError(f"快照不匹配:{snapshot.get('mode')}/{snapshot.get('subject')}")
        self.state = CognitiveState.from_wire(snapshot["state"])

    def close(self) -> None:
        self._instance = None  # 底座实例归调用方管理;此处只解引用

    # ---- 语义入口(保留) ----

    def simulate_step(self, observation: PerceivedObservation, persona, scenario, history, speaker_slot):
        """Inner 上层接口(V3 §2.4):这个人下一步会怎么做。"""
        return self._step(observation, persona, scenario, history, speaker_slot)
