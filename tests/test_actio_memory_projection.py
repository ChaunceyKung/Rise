import hashlib
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from actio.adapters.memory.starling import StarlingMemoryAdapter
from actio.adapters.persistence.store import Connection
from actio.application.memory_projection import enqueue, project_one, reconcile, stats
from actio.contracts.memory import MemoryObservation, MemoryScope, MemorySource


def make_observation():
    source = MemorySource("run", "stream", 1, "assistant.final", "v1", hashlib.sha256(b"raw").hexdigest(), "2026-10-27T00:00:00Z", "assistant_final")
    return MemoryObservation(source, MemoryScope("synthetic", "main", "private", "assistant", "alice"), "certified", "alice")


class MemoryProjection(unittest.TestCase):
    def test_outbox_project_and_duplicate(self):
        with TemporaryDirectory() as directory:
            store = Connection(Path(directory) / "store.sqlite", create=True)
            with store.tx():
                store.db.execute("INSERT INTO run(id,request_key,input_hash,input,epoch,state,task,trajectory,owner_pid,owner_birth,created) VALUES('run','request','hash','{}',1,'execution_complete','success','complete',1,'birth',1)")
            item = make_observation()
            queued = enqueue(store, item, certified=True, now=100)
            self.assertEqual(queued["state"], "queued")
            result = project_one(store, StarlingMemoryAdapter(mode="shadow"), now=100)
            self.assertEqual(result["state"], "committed")
            self.assertEqual(stats(store).committed, 1)
            # A second outbox insertion is idempotent and cannot create a new row.
            again = enqueue(store, item, certified=True, now=101)
            self.assertEqual(again["id"], queued["id"])
            store.close()

    def test_conflicting_source_is_rejected(self):
        with TemporaryDirectory() as directory:
            store = Connection(Path(directory) / "store.sqlite", create=True)
            with store.tx():
                store.db.execute("INSERT INTO run(id,request_key,input_hash,input,epoch,state,task,trajectory,owner_pid,owner_birth,created) VALUES('run','request','hash','{}',1,'execution_complete','success','complete',1,'birth',1)")
            item = make_observation()
            enqueue(store, item, certified=True)
            other = MemoryObservation(item.source, item.scope, "changed", item.holder)
            with self.assertRaisesRegex(ValueError, "source key conflict"):
                enqueue(store, other, certified=True)
            store.close()

