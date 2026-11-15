"""D1 桥:Rise 记忆后端 ↔ Actio StarlingMemoryPort 协议(方案 §3.2 D1)。

Actio 的 StarlingMemoryAdapter 预留了鸭子 facade 注入点(remember/query/health,
字典进字典出);本桥把 Rise 的 MemoryBackend(TupleMemory 替身或 StarlingMemory
线上实现)包成该 facade,使 Actio 的投影/收据/幂等栈原样复用,而 Rise 侧
memory_starling.py 与全部既有消费方零改动。

命名空间映射(v1,显式且不可逆推):
    Actio MemoryScope(project=synthetic, branch=main, visibility=private,
                      environment∈{assistant,social}, agent=holder)
    ↔ Rise 的 (world, holder) 记忆视图。
"""
from __future__ import annotations

from typing import Any

from simple_actio.memory_port import MemoryBackend, MemoryEvent


class ActioMemoryFacade:
    """把 MemoryBackend 包成 Actio adapter 的鸭子 facade。

    只承接 project(写)方向与 query(读)方向的最小语义:
    RememberOutcome.stored → {'outcome': 'ok'};failed → {'outcome': 'failed'};
    recall 命中 → {'entries': [...]};miss → {'entries': [], 'abstained': True}。
    冲突(MemoryEventConflict)显式翻译成 source_conflict,让 Actio 侧收据
    走 REJECTED 而不是反复重试成 needs_reconcile。
    """

    def __init__(self, memory: MemoryBackend):
        self._memory = memory

    def health(self) -> dict:
        return {"status": "ready"}

    def remember(self, text: str, *, holder: str, interlocutor: str | None = None, now: str | None = None,
                 source_key: str = "", source_hash: str = "", tenant_id: str = "") -> dict:
        del now, source_hash, tenant_id  # Rise 端口不收时钟;时间语义由会话层拥有
        try:
            # Rise 端口要求非空 interlocutor;Actio 允许 None,此处显式翻译
            outcome = self._memory.remember(MemoryEvent(key=source_key or f"{holder}#actio", text=text,
                                                         interlocutor=interlocutor or "unspecified"))
        except Exception:
            return {"outcome": "failed"}
        if outcome.failed:
            return {"outcome": "failed", "category": outcome.category}
        return {"outcome": "ok"}

    def query(self, query: str, *, intent: str = "", perspective: str | None = None, goal: str | None = None,
              k: int = 8, now: str | None = None) -> dict:
        del intent, perspective, goal, now
        hits = self._memory.recall(query, limit=k)
        if not hits:
            return {"entries": [], "abstained": True, "abstention_reason": "no_recall_hits"}
        return {"entries": [{"id": hit.id, "text": hit.text} for hit in hits]}


def actio_projection(memory: MemoryBackend, *, mode: str = "shadow") -> Any:
    """装配:Rise 记忆后端 → StarlingMemoryPort 实现(shadow 投影栈)。"""
    from actio.adapters.memory.starling import StarlingMemoryAdapter

    return StarlingMemoryAdapter(mode=mode, facade=ActioMemoryFacade(memory))
