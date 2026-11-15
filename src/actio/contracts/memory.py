"""Stable, dependency-free contracts for the optional Starling projection."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Literal, Protocol, Mapping

import json


class ContractError(ValueError):
    """Contract-local error keeps the lowest layer dependency free."""


def canonical(value):
    if value is None or type(value) in (bool, int, str):
        if type(value) is int and abs(value) > 9007199254740991:
            raise ContractError("unsafe integer")
        if type(value) is str:
            value.encode("utf-8")
    elif type(value) is list:
        for item in value: canonical(item)
    elif type(value) is dict and all(type(k) is str for k in value):
        for key, item in value.items(): key.encode("utf-8"); canonical(item)
    else:
        raise ContractError("restricted JSON required")
    if type(value) is dict:
        return "{" + ",".join(json.dumps(k, ensure_ascii=False) + ":" + canonical(value[k]) for k in sorted(value, key=lambda k: k.encode("utf-16be"))) + "}"
    if type(value) is list:
        return "[" + ",".join(canonical(x) for x in value) + "]"
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()

MAX_PAYLOAD_BYTES = 16 * 1024

class MemoryMode(str, Enum):
    OFF = "off"
    SHADOW = "shadow"
    FROZEN_CONTEXT = "frozen_context"
    LIVE_CONTEXT = "live_context"

class ProjectionState(str, Enum):
    QUEUED = "queued"; IN_FLIGHT = "in_flight"; COMMITTED = "committed"; DUPLICATE = "duplicate"
    ABSTAINED = "abstained"; DEGRADED = "degraded"; REJECTED = "rejected"; NEEDS_RECONCILE = "needs_reconcile"

class MemoryErrorCode(str, Enum):
    DISABLED = "disabled"; UNREADY = "unready"; LLM_NOT_CONFIGURED = "llm_not_configured"
    EXTRACTION_FAILED = "extraction_failed"; DB_LOCKED = "db_locked"; TIMEOUT = "timeout"
    SIDECAR_CRASH = "sidecar_crash"; POLICY_DENIED = "policy_denied"; PAYLOAD_SECRET = "payload_secret"
    PAYLOAD_TOO_LARGE = "payload_too_large"; SOURCE_CONFLICT = "source_conflict"; DUPLICATE = "duplicate"
    REPLAY_FORBIDDEN = "replay_forbidden"; INVALID_MODE = "invalid_mode"; ABSTAINED = "abstained"
    PROTOCOL_ERROR = "protocol_error"; UNKNOWN = "unknown"

MemoryModeValue = Literal["off", "shadow", "frozen_context", "live_context"]
SourceKind = Literal["assistant_final", "tool_observation", "world_effect"]
PrivacyClass = Literal["public", "internal", "personal", "sensitive"]
PayloadPolicy = Literal["text", "metadata_only", "redacted"]

def _required_string(value: Any, name: str) -> str:
    if type(value) is not str or not value:
        raise ContractError(f"{name} must be a non-empty string")
    value.encode("utf-8")
    return value

def tenant_digest(project: str, branch: str, visibility: str, environment: str) -> str:
    for name, value in (("project", project), ("branch", branch), ("visibility", visibility), ("environment", environment)):
        _required_string(value, name)
    body = canonical({"project": project, "branch": branch, "visibility": visibility, "environment": environment})
    return "actio:" + hashlib.sha256(body.encode()).hexdigest()

@dataclass(frozen=True)
class MemoryScope:
    project: str; branch: str; visibility: str; environment: Literal["assistant", "social"]; agent: str
    target: str | None = None; tenant_id: str = ""
    def __post_init__(self):
        for name in ("project", "branch", "visibility", "agent"): _required_string(getattr(self, name), name)
        if self.environment not in ("assistant", "social"): raise ContractError("memory environment must be assistant or social")
        if self.target is not None: _required_string(self.target, "target")
        expected = tenant_digest(self.project, self.branch, self.visibility, self.environment)
        if self.tenant_id and self.tenant_id != expected: raise ContractError("tenant_id does not match canonical namespace")
        object.__setattr__(self, "tenant_id", expected)
    def to_wire(self):
        return {"project": self.project, "branch": self.branch, "visibility": self.visibility, "environment": self.environment, "agent": self.agent, "target": self.target, "tenant_id": self.tenant_id}
    @classmethod
    def from_wire(cls, value):
        if type(value) is not dict or set(value) != {"project", "branch", "visibility", "environment", "agent", "target", "tenant_id"}: raise ContractError("memory scope fields mismatch")
        return cls(**value)

@dataclass(frozen=True)
class MemorySource:
    run_id: str; stream_id: str; seq: int; slot: str; mapper: str; source_hash: str; observed_at: str
    source_kind: SourceKind; replay_of: str | None = None; privacy_class: PrivacyClass = "internal"
    def __post_init__(self):
        for name in ("run_id", "stream_id", "slot", "mapper", "source_hash", "observed_at"): _required_string(getattr(self, name), name)
        if type(self.seq) is not int or self.seq < 0: raise ContractError("source seq must be a non-negative integer")
        if len(self.source_hash) != 64 or not re.fullmatch(r"[0-9a-f]{64}", self.source_hash): raise ContractError("source_hash must be a lowercase sha256")
        if self.source_kind not in ("assistant_final", "tool_observation", "world_effect"): raise ContractError("unknown memory source kind")
        if self.privacy_class not in ("public", "internal", "personal", "sensitive"): raise ContractError("unknown privacy class")
        if self.replay_of is not None: _required_string(self.replay_of, "replay_of")
    @property
    def source_key(self): return f"{self.stream_id}/{self.seq}/{self.slot}/{self.mapper}"
    def to_wire(self):
        return {"run_id": self.run_id, "stream_id": self.stream_id, "seq": self.seq, "slot": self.slot, "mapper": self.mapper, "source_hash": self.source_hash, "observed_at": self.observed_at, "source_kind": self.source_kind, "replay_of": self.replay_of, "privacy_class": self.privacy_class}
    @classmethod
    def from_wire(cls, value):
        fields = {"run_id", "stream_id", "seq", "slot", "mapper", "source_hash", "observed_at", "source_kind", "replay_of", "privacy_class"}
        if type(value) is not dict or set(value) != fields: raise ContractError("memory source fields mismatch")
        return cls(**value)

_SECRET_PATTERNS = (re.compile(r"(?i)(?:api[_ -]?key|token|password|secret)\s*[:=]"), re.compile(r"(?i)gm_private_full_log"), re.compile(r"(?i)(?:authorization\s*:\s*bearer|x-api-key)"), re.compile(r"(?i)\bstderr\b"))
def scan_payload_secret(text: str) -> bool: return any(p.search(text) for p in _SECRET_PATTERNS)

@dataclass(frozen=True)
class MemoryObservation:
    source: MemorySource; scope: MemoryScope; text: str | None; holder: str; interlocutor: str | None = None
    event_time_start: str | None = None; event_time_end: str | None = None; payload_policy: PayloadPolicy = "text"
    def __post_init__(self):
        _required_string(self.holder, "holder")
        if self.interlocutor is not None: _required_string(self.interlocutor, "interlocutor")
        if self.payload_policy not in ("text", "metadata_only", "redacted"): raise ContractError("unknown payload policy")
        if self.payload_policy == "metadata_only" and self.text is not None: raise ContractError("metadata_only observations cannot carry text")
        if self.text is not None:
            if type(self.text) is not str: raise ContractError("memory text must be a string")
            if len(self.text.encode("utf-8")) > MAX_PAYLOAD_BYTES: raise ContractError("memory payload exceeds 16 KiB")
            if scan_payload_secret(self.text): raise ContractError("memory payload contains a prohibited secret/private marker")
        if self.source.replay_of and self.payload_policy == "text": raise ContractError("replay source requires explicit metadata-only policy")
    @property
    def source_key(self): return self.source.source_key
    def payload(self):
        value = {"source": self.source.to_wire(), "scope": self.scope.to_wire(), "holder": self.holder, "interlocutor": self.interlocutor, "event_time_start": self.event_time_start, "event_time_end": self.event_time_end, "payload_policy": self.payload_policy, "text": self.text if self.payload_policy == "text" else None}
        if len(canonical(value).encode()) > MAX_PAYLOAD_BYTES: raise ContractError("canonical memory payload exceeds 16 KiB")
        return value
    @property
    def payload_hash(self): return digest(self.payload())
    def to_wire(self): return self.payload()
    @classmethod
    def from_wire(cls, value):
        fields = {"source", "scope", "holder", "interlocutor", "event_time_start", "event_time_end", "payload_policy", "text"}
        if type(value) is not dict or set(value) != fields: raise ContractError("memory observation fields mismatch")
        return cls(source=MemorySource.from_wire(value["source"]), scope=MemoryScope.from_wire(value["scope"]), holder=value["holder"], interlocutor=value["interlocutor"], event_time_start=value["event_time_start"], event_time_end=value["event_time_end"], payload_policy=value["payload_policy"], text=value["text"])

@dataclass(frozen=True)
class MemoryReceipt:
    adapter: str; adapter_version: str; operation_id: str; source_key: str; state: ProjectionState; tenant_id: str
    engram_ref: str | None = None; statement_ids: tuple[str, ...] = (); context_hash: str | None = None
    retrieval_receipt: dict[str, Any] | None = None; as_of: str | None = None; error_code: str | None = None
    error_detail: str | None = None; idempotent: bool = False; started_at: str | None = None; finished_at: str | None = None
    def __post_init__(self):
        for name in ("adapter", "adapter_version", "operation_id", "source_key", "tenant_id"): _required_string(getattr(self, name), name)
        object.__setattr__(self, "state", ProjectionState(self.state.value if isinstance(self.state, ProjectionState) else self.state))
        if any(type(x) is not str or not x for x in self.statement_ids): raise ContractError("statement_ids must contain strings")
    def to_wire(self):
        value = self.__dict__.copy(); value["state"] = self.state.value; value["statement_ids"] = list(self.statement_ids); return value
    @classmethod
    def from_wire(cls, value):
        if type(value) is not dict: raise ContractError("memory receipt object required")
        fields = {"adapter", "adapter_version", "operation_id", "source_key", "state", "tenant_id", "engram_ref", "statement_ids", "context_hash", "retrieval_receipt", "as_of", "error_code", "error_detail", "idempotent", "started_at", "finished_at"}
        if set(value) != fields: raise ContractError("memory receipt fields mismatch")
        return cls(**{**value, "statement_ids": tuple(value["statement_ids"])})

@dataclass(frozen=True)
class MemoryContext:
    text: str; context_hash: str; abstained: bool; abstention_reason: str | None; receipt: MemoryReceipt; sections: tuple[dict[str, Any], ...] = ()
    def __post_init__(self):
        if type(self.text) is not str or type(self.context_hash) is not str: raise ContractError("memory context text/hash required")
        if type(self.abstained) is not bool: raise ContractError("memory context abstained must be boolean")
        if self.abstained and not self.abstention_reason: raise ContractError("abstained context requires a reason")
        if not self.abstained and self.abstention_reason is not None: raise ContractError("non-abstained context cannot carry abstention reason")
    def to_wire(self): return {"text": self.text, "context_hash": self.context_hash, "abstained": self.abstained, "abstention_reason": self.abstention_reason, "receipt": self.receipt.to_wire(), "sections": list(self.sections)}
    @classmethod
    def from_wire(cls, value): return cls(text=value["text"], context_hash=value["context_hash"], abstained=value["abstained"], abstention_reason=value["abstention_reason"], receipt=MemoryReceipt.from_wire(value["receipt"]), sections=tuple(value.get("sections", ())))

@dataclass(frozen=True)
class MemoryHealth:
    status: Literal["ready", "degraded", "unready", "disabled"]; capabilities: frozenset[str] = frozenset(); missing: tuple[str, ...] = (); writer_queue_depth: int = 0; last_error_code: str | None = None
    def __post_init__(self):
        if self.status not in ("ready", "degraded", "unready", "disabled"): raise ContractError("unknown memory health status")
        if type(self.writer_queue_depth) is not int or self.writer_queue_depth < 0: raise ContractError("writer queue depth must be non-negative")
    def to_wire(self): return {"status": self.status, "capabilities": sorted(self.capabilities), "missing": list(self.missing), "writer_queue_depth": self.writer_queue_depth, "last_error_code": self.last_error_code}

class StarlingMemoryPort(Protocol):
    def health(self) -> MemoryHealth: ...
    def project(self, item: MemoryObservation, *, idempotency_key: str) -> MemoryReceipt: ...
    def retrieve(self, scope: MemoryScope, *, query: str, intent: str, perspective: str | None, goal: str | None, k: int, as_of: str | None, mode: MemoryModeValue) -> MemoryContext: ...
    def working_set(self, scope: MemoryScope, *, interlocutor: str, goal: str | None, token_budget: int, as_of: str | None, mode: MemoryModeValue) -> MemoryContext: ...
    def tick(self, *, now: str, deadline_ms: int) -> dict[str, Any]: ...
    def forget(self, scope: MemoryScope, statement_ids: list[str], *, now: str) -> MemoryReceipt: ...
    def close(self, *, drain: bool = True) -> None: ...
