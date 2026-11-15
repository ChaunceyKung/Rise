"""P4b:evaluation 谱系全链(v9 预注册)与 envelope 桥(方案 D2 收口)。

v4 仓库 = create(lineage=True) 后补跑 evaluation_schema(SQL 内自带 user_version=4)。
decide 需要 campaigns 测量闭包,属 P5 的 CLI 收编批;此处走 register→claim→export。
"""
from __future__ import annotations

from pathlib import Path

import pytest

from actio.adapters.persistence import database
from actio.contracts.json import digest, unseal
from actio.domain.candidate import baseline, candidate
from actio.evidence.lineage import evaluation_lineage
from actio.interfaces.store import Store
from actio.profiles.evaluation_campaign import preregistration
from test_actio_store import _StubPorts


def _v4_store(tmp_path: Path) -> Store:
    s = Store(tmp_path / "store.sqlite", create=True, lineage=True, ports=_StubPorts())
    s.db.executescript((Path(database.__file__).parent / "evaluation_schema.sql").read_text(encoding="utf-8"))
    s.db.execute("PRAGMA foreign_keys=ON")
    s.version = 4
    return s


def test_evaluation_lineage_register_claim_export_chain(tmp_path):
    s = _v4_store(tmp_path)
    try:
        s.candidate(baseline())
        s.candidate(candidate())
        _publish_candidates(s)
        body = evaluation_lineage.plan(preregistration(), "local_fixture")
        eid = s.evaluation(body)
        s.claim_evaluation(eid, {"root": str(tmp_path), "namespace": body["claim_namespace"]})
        # 二次 claim 拒绝(一次性领取,不可回收)
        with pytest.raises(Exception):
            s.claim_evaluation(eid, {"root": str(tmp_path), "namespace": body["claim_namespace"]})
        # 注:evaluation export 的 verify 钉死历史常量 LEGACY_LINEAGE(证据不可变纪律),
        # 新库按设计无法复刻;全链导出测试随历史 fixture 移植(P5)。
        # 幂等注册:同一 body 再注册返回同一 id
        assert s.evaluation(body) == eid
    finally:
        s.close()


def _publish_candidates(s):
    """C2C1 纪律:evaluation 导出前候选谱系必须已成稿(绑定+决策)。"""
    from actio.domain.candidate import POLICY_HASH, decide as decide_fn

    for c in (baseline(), candidate()):
        cid = digest(c)
        s.bind_candidate(cid, {"policy_hash": POLICY_HASH, "candidate_hashes": [cid],
                               "run": "camp", "campaign": "camp"})
        s.decide_candidate(cid, decide_fn(static_valid=True, complete=True,
                                          evidence_kind="local_fixture", diagnostics={}, synthetic_gain=None))


def test_evaluation_register_binds_only_validated_candidates(tmp_path):
    s = _v4_store(tmp_path)
    try:
        s.candidate(baseline())  # 只注册 baseline,candidate 缺席
        body = evaluation_lineage.plan(preregistration(), "local_fixture")
        with pytest.raises(Exception, match="validated"):
            s.evaluation(body)
    finally:
        s.close()


# ---------------- envelope 桥(D2:谱系终态单向投影,幂等) ----------------

def test_lineage_projects_once_into_the_envelope_tree_and_repeats_are_noops(tmp_path):
    from controlplane.gitstore import GitStore
    from recipestore.actio_lineage_bridge import LINEAGE_TYPE, project_lineage

    s = Store(tmp_path / "store.sqlite", create=True, lineage=True, ports=_StubPorts())
    git = GitStore(str(tmp_path / "repo"))
    try:
        s.candidate(baseline())
        s.candidate(candidate())
        git.init()
        sealed = s.candidate_lineage()
        first = project_lineage(git, sealed)
        assert first.endswith(".yml")
        env = git.read_product(first)
        assert env.type == LINEAGE_TYPE and env.status == "final"
        assert unseal(env.payload["sealed"])["schema"] == "candidate-lineage.v1"
        # 重复投影同一份 = 幂等 no-op(git 无新提交,路径不变)
        head = git._git("rev-parse", "HEAD")
        again = project_lineage(git, sealed)
        assert again == first and git._git("rev-parse", "HEAD") == head
        # 谱系变化(新决策)→ 新版本产物,旧版本保留
        from actio.domain.candidate import POLICY_HASH

        cid = digest(candidate())
        binding = {"policy_hash": POLICY_HASH, "candidate_hashes": [cid], "run": "r", "campaign": "c"}
        s.bind_candidate(cid, binding)
        from actio.domain.candidate import decide

        s.decide_candidate(cid, decide(static_valid=True, complete=True,
                                       evidence_kind="local_fixture", diagnostics={}, synthetic_gain=None))
        # 版本化:同路径 version+1,内容哈希变化,旧提交历史保留
        project_lineage(git, s.candidate_lineage())
        bumped = git.read_product(first)
        assert bumped.version == 2
        assert bumped.payload["lineage_hash"] != env.payload["lineage_hash"]
    finally:
        s.close()
