"""Outer 模式运行体:decide_for_human(V3 §2.4)——面对这个人,智能体该怎么做。

V4 A3:注入 estimator(独立估计组件)+ decision(HumanAwareDecisionPolicy)
后走"估计→意图→澄清/行动"新路径,StepResult 携带 DecisionRecord(引用可回查);
两参数缺省时保持 M1 的机制叠加路径,旧调用零破坏。
"""
from __future__ import annotations

from simple_actio.core.record import DecisionRecord
from simple_actio.inner.agent import ModeAgent
from simple_actio.outer.human_model import HumanModel
from simple_actio.outer.state_estimator import HumanStateEstimator


class OuterAgent(ModeAgent):
    mode = "outer"

    def __init__(self, *args, estimator: HumanStateEstimator | None = None,
                 decision=None, person_id: str | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.estimator = estimator
        self.decision = decision
        pid = person_id or (self.state.subject if self.state.subject != "assistant" else "counterpart")
        self.human_model = HumanModel(person_id=pid)

    def decide_for_human(self, observation, persona, scenario, history, speaker_slot):
        if self.estimator is None or self.decision is None:
            return self._step(observation, persona, scenario, history, speaker_slot)
        return self._decide_with_model(observation, persona, scenario, history, speaker_slot)

    def _decide_with_model(self, observation, persona, scenario, history, speaker_slot):
        from simple_actio.core.intent import StepResult
        from simple_actio.core.trace import CognitiveTrace

        self.human_model = self.estimator.update(self.human_model, observation,
                                                 turn=self.state.turn + 1)
        intent = self.decision.decide(self.human_model, observation)
        directives = tuple(intent.parameters.get("directives", ()))
        self._instance.backend.set_directive(directives)
        utterance, inner_thought, trace = self._instance.respond(persona, scenario, history, speaker_slot)
        selected = intent.parameters.get("kind", "act")
        top = self.human_model.top(limit=1)
        record = DecisionRecord(
            selected=selected,
            goal_refs=tuple(self.decision.objectives),
            belief_refs=((top[0].statement,) if top else ()) + tuple(self.state.beliefs[:2]),
            skill_ref=intent.skill_ref,
            alternatives_considered=("clarify", "act"),
            evidence_level="structurally_derived",
            summary=intent.parameters.get("reason") or "按人物估计选择行动",
        )
        self.state, delta = self._dynamics.update(self.state, observation, action=utterance)
        self.last_trace = CognitiveTrace(mode=self.mode, turn=self.state.turn,
                                         action_type=intent.action_type,
                                         directives=directives,
                                         mechanisms=(selected,),
                                         state_delta=(delta,),
                                         rationale=record.to_wire())
        return StepResult(mode=self.mode, utterance=utterance, inner_thought=inner_thought,
                          directive=directives, mechanisms=(selected,), trace=trace,
                          state_delta=(delta,), rationale_summary=record.to_wire())
