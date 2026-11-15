"""D1 桥测试:Rise 记忆后端包成 Actio 投影栈(方案 §5.3,对应 T-A-07 的桥半边)。"""
from __future__ import annotations

import hashlib

from actio.contracts.memory import MemoryMode, MemoryObservation, MemoryScope, MemorySource, ProjectionState
from factory.memory_actio_bridge import ActioMemoryFacade, actio_projection
from simple_actio.memory import TupleMemory


def observation(text="hello", *, source_key="s/0/assistant.final/v1"):
    source = MemorySource("run-1", "s", 0, "assistant.final", "v1",
                          hashlib.sha256(b"raw").hexdigest(), "2026-11-15T00:00:00Z", "assistant_final")
    scope = MemoryScope("synthetic", "main", "private", "assistant", "alice")
    return MemoryObservation(source, scope, text, "alice"), source_key


def test_facade_projects_into_the_rise_memory_and_reads_back():
    memory = TupleMemory(()).world("alice")
    facade = ActioMemoryFacade(memory)
    item, key = observation()
    assert facade.remember(item.text, holder="alice", source_key=key) == {"outcome": "ok"}
    result = facade.query("hello", k=4)
    assert [e["text"] for e in result["entries"]] == ["unspecified: hello"]
    miss = facade.query("不存在的话题", k=4)
    assert miss["abstained"] is True


def test_actio_projection_round_trips_through_the_rise_backend():
    port = actio_projection(TupleMemory(()).world("alice"), mode="shadow")
    item, key = observation()
    receipt = port.project(item, idempotency_key=key)
    assert receipt.state is ProjectionState.COMMITTED
    again = port.project(item, idempotency_key=key)  # 同键同文 → duplicate(幂等)
    assert again.state is ProjectionState.DUPLICATE
    context = port.retrieve(item.scope, query="hello", intent="recall", perspective=None, goal=None, k=4,
                            as_of=None, mode=MemoryMode.SHADOW)
    # adapter 把命中放 sections,text 供上下文拼装
    assert any("hello" in s["text"] for s in context.sections)
    assert context.abstained is False
