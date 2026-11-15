"""Actio-owned outbox and bounded projection saga for Starling memory."""
from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass
from typing import Any

from actio.contracts.json import ContractError, canonical
from actio.contracts.memory import MemoryObservation, MemoryReceipt, ProjectionState, StarlingMemoryPort

MAX_ATTEMPTS = 3
LEASE_SECONDS = 30


@dataclass(frozen=True)
class ProjectionStats:
    queued: int = 0
    in_flight: int = 0
    committed: int = 0
    duplicate: int = 0
    degraded: int = 0
    rejected: int = 0
    needs_reconcile: int = 0
    abstained: int = 0


def _now(now: int | None = None) -> int:
    return int(time.time()) if now is None else int(now)


def enqueue(store: Any, observation: MemoryObservation, *, certified: bool = True, now: int | None = None) -> dict[str, Any]:
    """Insert one certified observation in the same Store transaction as its effect."""
    if not certified:
        raise ContractError("memory source must be certified by Facts before enqueue")
    payload = canonical(observation.to_wire())
    payload_hash = observation.payload_hash
    timestamp = _now(now)
    with store.tx():
        old = store.row("SELECT * FROM memory_outbox WHERE source_key=?", (observation.source_key,))
        if old:
            if old["payload_hash"] != payload_hash or old["source_hash"] != observation.source.source_hash:
                raise ContractError("memory source key conflict: payload hash differs")
            return old
        row_id = uuid.uuid4().hex
        store.db.execute("INSERT INTO memory_outbox(id,source_key,run,namespace,source_hash,payload,payload_hash,state,attempts,lease_until,receipt,error,created,updated) VALUES(?,?,?,?,?,?,?,'queued',0,NULL,NULL,NULL,?,?)",
                         (row_id, observation.source_key, observation.source.run_id, canonical(observation.scope.to_wire()), observation.source.source_hash, payload, payload_hash, timestamp, timestamp))
    return store.row("SELECT * FROM memory_outbox WHERE id=?", (row_id,))


def enqueue_outbox(store: Any, observation: MemoryObservation, **kwargs) -> dict[str, Any]:
    return enqueue(store, observation, **kwargs)


def claim(store: Any, *, now: int | None = None, lease_seconds: int = LEASE_SECONDS, max_attempts: int = MAX_ATTEMPTS) -> dict[str, Any] | None:
    now = _now(now)
    if lease_seconds <= 0 or max_attempts <= 0:
        raise ContractError("lease and retry bounds must be positive")
    with store.tx():
        row = store.row("SELECT * FROM memory_outbox WHERE (state='queued' OR (state='in_flight' AND lease_until<?)) AND attempts<? ORDER BY created,id LIMIT 1", (now, max_attempts))
        if not row:
            return None
        store.db.execute("UPDATE memory_outbox SET state='in_flight',attempts=attempts+1,lease_until=?,updated=?,error=NULL WHERE id=? AND (state='queued' OR (state='in_flight' AND lease_until<?))", (now + lease_seconds, now, row["id"], now))
        return store.row("SELECT * FROM memory_outbox WHERE id=?", (row["id"],))


def _state_for_receipt(receipt: MemoryReceipt) -> str:
    return receipt.state.value


def _write_result(store: Any, row_id: str, receipt: MemoryReceipt, *, now: int) -> dict[str, Any]:
    with store.tx():
        store.db.execute("UPDATE memory_outbox SET state=?,receipt=?,error=NULL,lease_until=NULL,updated=? WHERE id=? AND state='in_flight'", (_state_for_receipt(receipt), json.dumps(receipt.to_wire(), ensure_ascii=False, separators=(",", ":")), now, row_id))
    return store.row("SELECT * FROM memory_outbox WHERE id=?", (row_id,))


def project_one(store: Any, port: StarlingMemoryPort, *, now: int | None = None, lease_seconds: int = LEASE_SECONDS, max_attempts: int = MAX_ATTEMPTS) -> dict[str, Any] | None:
    claimed = claim(store, now=now, lease_seconds=lease_seconds, max_attempts=max_attempts)
    if not claimed:
        return None
    timestamp = _now(now)
    try:
        observation = MemoryObservation.from_wire(json.loads(claimed["payload"]))
        receipt = port.project(observation, idempotency_key=claimed["source_key"])
        return _write_result(store, claimed["id"], receipt, now=timestamp)
    except Exception as exc:
        # A failed Actio receipt write is reconciled separately; this path only
        # records an adapter/client failure and is bounded by max_attempts.
        detail = str(exc)[:512]
        state = "needs_reconcile" if claimed["attempts"] >= max_attempts else "queued"
        with store.tx():
            store.db.execute("UPDATE memory_outbox SET state=?,error=?,lease_until=NULL,updated=? WHERE id=? AND state='in_flight'", (state, detail, timestamp, claimed["id"]))
        return store.row("SELECT * FROM memory_outbox WHERE id=?", (claimed["id"],))


def reconcile(store: Any, port: StarlingMemoryPort, outbox_id: str | None = None, *, now: int | None = None) -> dict[str, Any] | None:
    """Retry the exact source key through the adapter's idempotency gate."""
    if outbox_id in (None, "all"):
        row = store.row("SELECT * FROM memory_outbox WHERE state IN ('needs_reconcile','in_flight') ORDER BY updated,id LIMIT 1")
    else:
        row = store.row("SELECT * FROM memory_outbox WHERE id=?", (outbox_id,))
    if not row:
        return None
    with store.tx():
        store.db.execute("UPDATE memory_outbox SET state='in_flight',lease_until=?,updated=? WHERE id=?", (_now(now) + LEASE_SECONDS, _now(now), row["id"]))
    try:
        observation = MemoryObservation.from_wire(json.loads(row["payload"]))
        receipt = port.project(observation, idempotency_key=row["source_key"])
        return _write_result(store, row["id"], receipt, now=_now(now))
    except Exception as exc:
        with store.tx():
            store.db.execute("UPDATE memory_outbox SET state='needs_reconcile',error=?,lease_until=NULL,updated=? WHERE id=?", (str(exc)[:512], _now(now), row["id"]))
        return store.row("SELECT * FROM memory_outbox WHERE id=?", (row["id"],))


def stats(store: Any) -> ProjectionStats:
    values = {row["state"]: int(row["n"]) for row in store.rows("SELECT state,COUNT(*) n FROM memory_outbox GROUP BY state")}
    return ProjectionStats(**{field: values.get(field, 0) for field in ProjectionStats.__dataclass_fields__})


class MemoryProjection:
    def __init__(self, store: Any, port: StarlingMemoryPort, *, lease_seconds: int = LEASE_SECONDS, max_attempts: int = MAX_ATTEMPTS):
        self.store, self.port = store, port
        self.lease_seconds, self.max_attempts = lease_seconds, max_attempts
    def enqueue(self, observation: MemoryObservation, *, certified: bool = True, now: int | None = None): return enqueue(self.store, observation, certified=certified, now=now)
    def claim(self, *, now: int | None = None): return claim(self.store, now=now, lease_seconds=self.lease_seconds, max_attempts=self.max_attempts)
    def project_one(self, *, now: int | None = None): return project_one(self.store, self.port, now=now, lease_seconds=self.lease_seconds, max_attempts=self.max_attempts)
    def reconcile(self, outbox_id: str | None = None, *, now: int | None = None): return reconcile(self.store, self.port, outbox_id, now=now)
    def stats(self): return stats(self.store)

