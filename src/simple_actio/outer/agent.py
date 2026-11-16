"""Outer 模式运行体:decide_for_human(V3 §2.4)——面对这个人,智能体该怎么做。"""
from __future__ import annotations

from simple_actio.inner.agent import ModeAgent


class OuterAgent(ModeAgent):
    mode = "outer"

    def decide_for_human(self, observation, persona, scenario, history, speaker_slot):
        return self._step(observation, persona, scenario, history, speaker_slot)
