"""Starling boundary adapter.

The implementation is intentionally useful without the optional Starling
wheel: it provides a deterministic in-memory port for offline tests and an
injected-facade path for an embedded or sidecar owner.  No Starling module is
imported at module load time.
"""
from __future__ import annotations

import hashlib
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Callable

from actio.contracts.json import ContractError, canonical, digest
from actio.contracts.memory import (
    MemoryContext, MemoryErrorCode, MemoryHealth, MemoryMode, MemoryObservation,
    MemoryReceipt, MemoryScope, ProjectionState, StarlingMemoryPort,
)

ADAPTER_NAME = "starling"
ADAPTER_VERSION = "actio-starling-adapter/0.1"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _error_code(error: BaseException) -> str:
    name = type(error).__name__.lower()
    message = str(error).lower()
    for marker, code in (("unready", MemoryErrorCode.UNREADY), ("llm", MemoryErrorCode.LLM_NOT_CONFIGURED),
                         ("extract", MemoryErrorCode.EXTRACTION_FAILED), ("locked", MemoryErrorCode.DB_LOCKED),
                         ("timeout", MemoryErrorCode.TIMEOUT), ("crash", MemoryErrorCode.SIDECAR_CRASH),
                         ("secret", MemoryErrorCode.PAYLOAD_SECRET), ("policy", MemoryErrorCode.POLICY_DENIED)):
        if marker in name or marker in message:
            return code.value
    return MemoryErrorCode.UNKNOWN.value


class StarlingMemoryAdapter(StarlingMemoryPort):
    """A serialized owner boundary around an optional public facade.

    ``facade`` is deliberately duck-typed so tests can inject a fake public
    facade or sidecar client without importing Starling. With no facade, the
    adapter is a deterministic stub and reports the ``stub`` capability.
    """

    def __init__(self, *, mode: str | MemoryMode = MemoryMode.SHADOW,
                 facade: Any | None = None, enabled: bool = True,
                 allow_source_kinds: set[str] | None = None,
                 now: Callable[[], str] = _utc_now,
                 adapter_version: str = ADAPTER_VERSION):
        try:
            self.mode = MemoryMode(mode)
        except ValueError as exc:
            raise ContractError(f"unknown memory mode: {mode}") from exc
        self._enabled = bool(enabled) and self.mode != MemoryMode.OFF
        self._facade = facade
        self._allow_source_kinds = allow_source_kinds or {"assistant_final"}
        self._now = now
        self._version = adapter_version
        self._closed = False
        self._last_error: str | None = None
        self._items: dict[str, tuple[MemoryObservation, MemoryReceipt]] = {}
        self._keys: dict[str, tuple[str, MemoryReceipt]] = {}
        self._deleted: set[str] = set()

    def health(self) -> MemoryHealth:
        if self._closed:
            return MemoryHealth("unready", missing=("closed",), last_error_code=self._last_error)
        if not self._enabled:
            return MemoryHealth("disabled", capabilities=frozenset(), last_error_code=self._last_error)
        if self._facade is not None and hasattr(self._facade, "health"):
            try:
                value = self._facade.health()
                if isinstance(value, MemoryHealth):
                    return value
                if isinstance(value, dict):
                    return MemoryHealth(status=value.get("status", "degraded"), capabilities=frozenset(value.get("capabilities", ())), missing=tuple(value.get("missing", ())), writer_queue_depth=int(value.get("writer_queue_depth", 0)), last_error_code=value.get("last_error_code"))
            except Exception as exc:  # diagnostics are returned, never raised by health
                self._last_error = _error_code(exc)
                return MemoryHealth("degraded", missing=("facade",), last_error_code=self._last_error)
        return MemoryHealth("ready", capabilities=frozenset({"project", "query", "working_set", "tick", "forget", "stub"}), last_error_code=self._last_error)

    def _receipt(self, item: MemoryObservation, state: ProjectionState, *, operation_id: str | None = None, **kwargs) -> MemoryReceipt:
        return MemoryReceipt(adapter=ADAPTER_NAME, adapter_version=self._version,
                             operation_id=operation_id or uuid.uuid4().hex, source_key=item.source_key,
                             state=state, tenant_id=item.scope.tenant_id, started_at=self._now(),
                             finished_at=self._now(), **kwargs)

    def project(self, item: MemoryObservation, *, idempotency_key: str) -> MemoryReceipt:
        if idempotency_key != item.source_key:
            raise ContractError("idempotency key must equal source key")
        if item.source.source_kind not in self._allow_source_kinds:
            return self._receipt(item, ProjectionState.REJECTED, error_code=MemoryErrorCode.POLICY_DENIED.value, error_detail="source kind is disabled")
        if item.scope.agent != item.holder:
            return self._receipt(item, ProjectionState.REJECTED, error_code=MemoryErrorCode.POLICY_DENIED.value, error_detail="holder must be the scoped agent")
        if item.source.replay_of:
            return self._receipt(item, ProjectionState.REJECTED, error_code=MemoryErrorCode.REPLAY_FORBIDDEN.value, error_detail="replay projection requires explicit experimental policy")
        payload_hash = item.payload_hash
        old = self._keys.get(idempotency_key)
        if old:
            old_hash, old_receipt = old
            if old_hash != payload_hash:
                return self._receipt(item, ProjectionState.REJECTED, error_code=MemoryErrorCode.SOURCE_CONFLICT.value, error_detail="source key already has a different payload hash")
            return MemoryReceipt.from_wire({**old_receipt.to_wire(), "state": ProjectionState.DUPLICATE.value, "idempotent": True, "finished_at": self._now()})
        if not self._enabled:
            return self._receipt(item, ProjectionState.DEGRADED, error_code=MemoryErrorCode.DISABLED.value, error_detail="memory mode is off")
        if self._closed:
            return self._receipt(item, ProjectionState.DEGRADED, error_code=MemoryErrorCode.UNREADY.value, error_detail="adapter is closed")
        try:
            if self._facade is not None:
                result = self._facade.remember(item.text or "", holder=item.holder, interlocutor=item.interlocutor, now=item.source.observed_at, source_key=item.source_key, source_hash=item.source.source_hash, tenant_id=item.scope.tenant_id)
                if isinstance(result, dict) and result.get("outcome") in ("extraction_failed", "failed"):
                    raise RuntimeError("extraction_failed")
                engram = str(result.get("engram_ref") or result.get("id") or idempotency_key) if isinstance(result, dict) else idempotency_key
                statements = tuple(str(x) for x in (result.get("statement_ids", ()) if isinstance(result, dict) else ()))
            else:
                engram = "engram:" + hashlib.sha256((item.scope.tenant_id + idempotency_key).encode()).hexdigest()[:24]
                statements = ("statement:" + hashlib.sha256(item.source.source_hash.encode()).hexdigest()[:24],)
            receipt = self._receipt(item, ProjectionState.COMMITTED, engram_ref=engram, statement_ids=statements)
            self._items[idempotency_key] = (item, receipt)
            self._keys[idempotency_key] = (payload_hash, receipt)
            return receipt
        except Exception as exc:
            code = _error_code(exc)
            self._last_error = code
            state = ProjectionState.REJECTED if code == MemoryErrorCode.POLICY_DENIED.value else ProjectionState.DEGRADED
            return self._receipt(item, state, error_code=code, error_detail=str(exc)[:512])

    def _context(self, scope: MemoryScope, *, query: str, intent: str, mode: str | MemoryMode, k: int, as_of: str | None, entries: list[tuple[MemoryObservation, MemoryReceipt]], operation: str) -> MemoryContext:
        selected = [(item, receipt) for item, receipt in entries if item.scope.tenant_id == scope.tenant_id and item.scope.agent == scope.agent and item.source.source_key not in self._deleted][:max(0, k)]
        abstained = not selected
        reason = "no matching memory" if abstained else None
        text = "" if abstained else "\n".join(item.text or "" for item, _ in selected)
        source_keys = [item.source_key for item, _ in selected]
        body = {"operation": operation, "query": query, "intent": intent, "mode": MemoryMode(mode).value, "as_of": as_of or self._now(), "source_keys": source_keys, "text": text, "abstained": abstained, "abstention_reason": reason}
        context_hash = digest(body)
        receipt = MemoryReceipt(adapter=ADAPTER_NAME, adapter_version=self._version, operation_id=uuid.uuid4().hex, source_key=source_keys[0] if source_keys else "context", state=ProjectionState.ABSTAINED if abstained else ProjectionState.COMMITTED, tenant_id=scope.tenant_id, context_hash=context_hash, as_of=body["as_of"], retrieval_receipt={"query_id": body["operation"] + ":" + context_hash[:16], "source_keys": source_keys, "candidate_count": len(selected), "abstained": abstained, "abstention_reason": reason}, started_at=self._now(), finished_at=self._now(), error_code=MemoryErrorCode.ABSTAINED.value if abstained else None, error_detail=reason)
        return MemoryContext(text=text, context_hash=context_hash, abstained=abstained, abstention_reason=reason, receipt=receipt, sections=tuple({"source_key": item.source_key, "text": item.text or "", "source_hash": item.source.source_hash} for item, _ in selected))

    def retrieve(self, scope: MemoryScope, *, query: str, intent: str, perspective: str | None = None, goal: str | None = None, k: int = 8, as_of: str | None = None, mode: str | MemoryMode = MemoryMode.SHADOW) -> MemoryContext:
        if type(query) is not str or not query: raise ContractError("memory query required")
        if type(k) is not int or not 1 <= k <= 32: raise ContractError("memory query k out of range")
        mode = MemoryMode(mode)
        if mode == MemoryMode.OFF or not self._enabled:
            dummy = MemoryObservation.__new__(MemoryObservation)
            # Construct a receipt without manufacturing a source observation.
            receipt = MemoryReceipt(adapter=ADAPTER_NAME, adapter_version=self._version, operation_id=uuid.uuid4().hex, source_key="context", state=ProjectionState.DEGRADED, tenant_id=scope.tenant_id, error_code=MemoryErrorCode.DISABLED.value, error_detail="memory mode is off", as_of=as_of or self._now())
            return MemoryContext(text="", context_hash=digest({"disabled": True, "as_of": receipt.as_of}), abstained=True, abstention_reason="memory disabled", receipt=receipt)
        if self._facade is not None and hasattr(self._facade, "query"):
            try:
                raw = self._facade.query(query, intent=intent, perspective=perspective, goal=goal, k=k, now=as_of or self._now())
                entries = raw.get("entries", ()) if isinstance(raw, dict) else ()
                text = raw.get("context_pack", raw.get("text", "")) if isinstance(raw, dict) else str(raw)
                abstained = bool(raw.get("abstained", False)) if isinstance(raw, dict) else not bool(text)
                reason = raw.get("abstention_reason") if isinstance(raw, dict) else ("no matching memory" if abstained else None)
                body = {"query": query, "intent": intent, "text": text, "as_of": as_of or self._now(), "abstained": abstained}
                ch = digest(body)
                receipt = MemoryReceipt(adapter=ADAPTER_NAME, adapter_version=self._version, operation_id=uuid.uuid4().hex, source_key="context", state=ProjectionState.ABSTAINED if abstained else ProjectionState.COMMITTED, tenant_id=scope.tenant_id, context_hash=ch, as_of=body["as_of"], retrieval_receipt=raw.get("receipt", raw) if isinstance(raw, dict) else {"abstained": abstained}, error_code=MemoryErrorCode.ABSTAINED.value if abstained else None, error_detail=reason)
                return MemoryContext(text=text, context_hash=ch, abstained=abstained, abstention_reason=reason, receipt=receipt, sections=tuple(entries) if isinstance(entries, list) else ())
            except Exception as exc:
                code = _error_code(exc); self._last_error = code
                receipt = MemoryReceipt(adapter=ADAPTER_NAME, adapter_version=self._version, operation_id=uuid.uuid4().hex, source_key="context", state=ProjectionState.DEGRADED, tenant_id=scope.tenant_id, as_of=as_of or self._now(), error_code=code, error_detail=str(exc)[:512])
                return MemoryContext(text="", context_hash=digest({"error": code}), abstained=True, abstention_reason=code, receipt=receipt)
        return self._context(scope, query=query, intent=intent, mode=mode, k=k, as_of=as_of, entries=list(self._items.values()), operation="query")

    def working_set(self, scope: MemoryScope, *, interlocutor: str, goal: str | None = None, token_budget: int = 2000, as_of: str | None = None, mode: str | MemoryMode = MemoryMode.SHADOW) -> MemoryContext:
        if type(token_budget) is not int or token_budget <= 0: raise ContractError("token budget must be positive")
        return self.retrieve(scope, query=goal or "working set", intent="WORKING_SET", perspective="first_person", goal=goal, k=min(32, max(1, token_budget // 256)), as_of=as_of, mode=mode)

    def tick(self, *, now: str, deadline_ms: int) -> dict[str, Any]:
        if not isinstance(now, str) or not now.endswith("Z"): raise ContractError("tick now must be UTC ISO8601")
        if type(deadline_ms) is not int or deadline_ms <= 0: raise ContractError("tick deadline must be positive")
        started = time.perf_counter()
        status = self.health().status
        return {"status": status, "now": now, "deadline_ms": deadline_ms, "stages": [], "stage_timings_ms": {}, "elapsed_ms": int((time.perf_counter() - started) * 1000), "health": self.health().to_wire()}

    def forget(self, scope: MemoryScope, statement_ids: list[str], *, now: str) -> MemoryReceipt:
        if not isinstance(now, str) or not now.endswith("Z"): raise ContractError("forget now must be UTC ISO8601")
        for key, (item, receipt) in self._items.items():
            if item.scope.tenant_id == scope.tenant_id and any(s in receipt.statement_ids for s in statement_ids): self._deleted.add(key)
        return MemoryReceipt(adapter=ADAPTER_NAME, adapter_version=self._version, operation_id=uuid.uuid4().hex, source_key="forget", state=ProjectionState.COMMITTED, tenant_id=scope.tenant_id, finished_at=now)

    def close(self, *, drain: bool = True) -> None:
        self._closed = True


StubStarlingMemoryPort = StarlingMemoryAdapter

