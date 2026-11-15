import hashlib
import unittest

from actio.contracts.memory import ContractError, MemoryObservation, MemoryReceipt, MemoryScope, MemorySource, MemoryMode, ProjectionState
from actio.adapters.memory.starling import StarlingMemoryAdapter
from actio.profiles.starling_memory import freeze_context, validate_memory_profile, validate_context_admission


def observation(text="hello", *, replay_of=None):
    source = MemorySource("run-1", "stream-1", 0, "assistant.final", "v1", hashlib.sha256(b"raw").hexdigest(), "2026-10-27T00:00:00Z", "assistant_final", replay_of=replay_of)
    scope = MemoryScope("synthetic", "main", "private", "assistant", "alice")
    return MemoryObservation(source, scope, text, "alice")


class StarlingContracts(unittest.TestCase):
    def test_source_hash_idempotency_and_wire(self):
        adapter = StarlingMemoryAdapter(mode="shadow")
        first = adapter.project(observation(), idempotency_key="stream-1/0/assistant.final/v1")
        again = adapter.project(observation(), idempotency_key="stream-1/0/assistant.final/v1")
        self.assertEqual(first.state, ProjectionState.COMMITTED)
        self.assertEqual(again.state, ProjectionState.DUPLICATE)
        self.assertTrue(again.idempotent)
        self.assertEqual(MemoryReceipt.from_wire(first.to_wire()), first)

    def test_secret_and_size_limits(self):
        with self.assertRaises(ContractError): observation("api_key=secret")
        with self.assertRaises(ContractError): observation("x" * 16385)

    def test_disabled_and_context_freeze(self):
        adapter = StarlingMemoryAdapter(mode=MemoryMode.OFF)
        receipt = adapter.project(observation(), idempotency_key="stream-1/0/assistant.final/v1")
        self.assertEqual(receipt.state, ProjectionState.DEGRADED)
        ctx = adapter.retrieve(observation().scope, query="x", intent="FACT_LOOKUP", k=2, as_of="2026-10-27T00:00:00Z", mode="off")
        self.assertTrue(ctx.abstained)
        self.assertEqual(validate_memory_profile({"mode": "off"}).mode, MemoryMode.OFF)
        with self.assertRaises(ValueError): validate_memory_profile({"mode": "live_context"})

    def test_frozen_context_and_replay_policy(self):
        adapter = StarlingMemoryAdapter(mode="shadow")
        adapter.project(observation(), idempotency_key="stream-1/0/assistant.final/v1")
        ctx = adapter.retrieve(observation().scope, query="x", intent="FACT_LOOKUP", k=2, as_of="2026-10-27T00:00:00Z", mode="shadow")
        frozen = freeze_context(ctx, as_of="2026-10-27T00:00:00Z")
        self.assertEqual(frozen["memory"]["mode"], "frozen_context")
        validate_context_admission(validate_memory_profile({"mode": "frozen_context", "freeze": True}, purpose="candidate"), purpose="candidate", context=ctx)
        with self.assertRaises(ContractError): observation(replay_of="run-0")

