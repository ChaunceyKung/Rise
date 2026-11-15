"""actio 持久层与谱系的测试(方案 §5.3 T-R 用例族的核心子集)。

SQLite 是演化的权威面(D2):Store(执行域)与 candidate/evaluation 谱系同库
同事务;envelope 桥(P4b)只做终态单向投影。测试用显式 ports 桩绕开
interfaces/wiring(未移植,属 episode 编排域)。
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from actio.adapters.persistence import database
import json

from actio.contracts.json import ContractError, digest, unseal
from actio.domain.candidate import baseline, candidate, decide
from actio.application.candidate_store import state as candidate_state
from actio.interfaces.store import Store

SPEC = {"version": 1, "persona": "SYNTHETIC_PERSONA_A", "persona_source": "synthetic-inline-v1",
        "persona_hash": digest("SYNTHETIC_PERSONA_A"), "prompt_version": "fixture-v1",
        "pins": {"profile": "test"}, "memory_shares": [["assistant", "social"]]}


class _StubPorts:
    """episode 编排端口桩:本测试族只走持久域,process_birth 给确定性指纹。"""

    class process_identity:
        @staticmethod
        def process_birth(pid):
            return 0

        @staticmethod
        def reap_named_job(name):
            return {"name": name, "alive": False}


def _store(tmp_path: Path, *, lineage: bool = True) -> Store:
    return Store(tmp_path / "store.sqlite", create=True, lineage=lineage, ports=_StubPorts())


# ---------------- T-R-01:迁移链 legacy(0)→2→3/4 ----------------

def _legacy_db(path: Path):
    db = sqlite3.connect(path, isolation_level=None)
    db.executescript((Path(database.__file__).parent / "legacy_schema.sql").read_text(encoding="utf-8"))
    db.execute("INSERT INTO meta VALUES('store','legacy-synthetic')")
    db.execute("INSERT INTO agent VALUES('OLD','original-pin','original-spec')")
    db.execute("INSERT INTO run VALUES('legacy','key','old-input-hash','{}',1,'execution_complete',"
               "'success','complete',NULL,0,123,'birth',1)")
    db.commit()
    db.close()
    return path


def _inspect(path):
    db = sqlite3.connect(path)
    try:
        return database.inspect(db)
    finally:
        db.close()


def test_schema_versions_and_lineage_migration_chain(tmp_path):
    legacy = _legacy_db(tmp_path / "legacy.sqlite")
    assert _inspect(legacy) == 0
    database.migrate_copy(legacy, tmp_path / "modern.sqlite")
    assert _inspect(tmp_path / "modern.sqlite") == 2, "migrate_copy 应升到执行域 schema v2"
    database.migrate_lineage_copy(tmp_path / "modern.sqlite", tmp_path / "lineage.sqlite")
    assert _inspect(tmp_path / "lineage.sqlite") in (3, 4)
    # 老数据必须原样保留
    db = sqlite3.connect(tmp_path / "lineage.sqlite")
    try:
        assert db.execute("SELECT spec FROM agent WHERE id='OLD'").fetchone()[0] == "original-spec"
    finally:
        db.close()


# ---------------- Store 生命周期与不可变纪律 ----------------

def test_store_run_lifecycle_and_spec_immutability(tmp_path):
    s = _store(tmp_path)
    try:
        s.agent("A", SPEC)
        assert s.agent("A")["spec"] == SPEC
        with pytest.raises(ContractError):
            s.agent("A", {**SPEC, "persona": "changed"})  # spec 不可变
        run, fresh = s.begin("key-1", {"scenario": "assistant", "agents": {}})
        assert fresh and run["id"]
        same, fresh2 = s.begin("key-1", {"scenario": "assistant", "agents": {}})
        assert not fresh2 and same["id"] == run["id"]  # 幂等
        with pytest.raises(ContractError):
            s.begin("key-1", {"different": True})  # key 冲突
    finally:
        s.close()


# ---------------- T-R-06:candidate 谱系 register→bind→decide→export ----------------

def test_candidate_lineage_round_trip_exports_sealed_projection(tmp_path):
    s = _store(tmp_path)
    try:
        child = candidate()
        decision = decide(static_valid=True, complete=True, evidence_kind="local_fixture",  # store 纪律:注册候选不吃 policy_fixture 决策
                          diagnostics={}, synthetic_gain=None)
        run, _ = s.begin("camp-1", {"scenario": "assistant", "agents": {}})
        s.candidate(baseline())
        cid = s.candidate(child)
        assert candidate_state(s, cid) == "validated"
        from actio.domain.candidate import POLICY_HASH

        binding = {"policy_hash": POLICY_HASH, "candidate_hashes": [cid], "run": run["id"], "campaign": "camp-1"}
        s.bind_candidate(cid, binding)
        s.decide_candidate(cid, decision)
        exported = s.candidate_lineage()
        body = unseal(exported)
        # 投影形状:tables.candidate 按 id 序全量封存
        proposals = [json.loads(row["proposal"]) for row in body["tables"]["candidate"]]
        assert sorted(p["name"] for p in proposals) == ["B0", "C1"]
        assert body["schema"] == "candidate-lineage.v1"
        # sealed 投影确定性:重复导出逐字节一致
        assert digest(s.candidate_lineage()) == digest(exported)
        # 决策后不可再绑定(评估中的候选不可被抢占)
        with pytest.raises(ContractError):
            s.bind_candidate(cid, {**binding, "campaign": "camp-2"})
    finally:
        s.close()
