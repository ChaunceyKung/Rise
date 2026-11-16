"""ActioAgent 协议(V4 A1;三层规划 §10 的四个核心抽象之一)。

统一 Inner/Outer 两模式的运行入口:step() 一轮认知,snapshot/restore
走受限 JSON(经 core.state 的 wire 规则),close 释放。
SimpleActioInstance 的 respond()/三元组保持冻结——协议适配在
adapters.protocol_agent(M1 ModeAgent → ActioAgent)。
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from simple_actio.core.observation import PerceivedObservation
from simple_actio.core.state import CognitiveState


@runtime_checkable
class ActioAgent(Protocol):
    mode: str

    def step(self, observation: PerceivedObservation, persona, scenario, history, speaker_slot): ...
    def snapshot(self) -> dict: ...
    def restore(self, snapshot: dict) -> None: ...
    def close(self) -> None: ...


def snapshot_state(state: CognitiveState) -> dict:
    """通用状态快照:受限 JSON wire(可 seal,digest 稳定)。"""
    return state.to_wire()


def restore_state(snapshot: dict) -> CognitiveState:
    return CognitiveState.from_wire(snapshot)
