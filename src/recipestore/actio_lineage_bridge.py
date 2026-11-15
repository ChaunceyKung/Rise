"""D2 桥:actio 谱系终态单向投影为控制面 envelope 产物(方案 §3.2 D2)。

规则(与调和循环的幂等纪律一致):
* 方向单一:SQLite 谱系(权威)→ git envelope 树(协作面);反向不存在;
* 幂等:同一份 sealed 谱系重复投影是 no-op(不产生新 git 提交);
* 版本化:谱系变化投影为同 id 的 version+1 产物,历史产物保留可审。

本模块只 import actio.contracts(sealed 数据互op),不碰 actio 内部实现——
保持 recipestore 与 actio 的依赖面最窄(见 tests/test_actio_boundaries)。
"""
from __future__ import annotations

from datetime import UTC, datetime

from actio.contracts.json import digest, unseal
from controlplane.envelope import Envelope, OwnerRef
from controlplane.gitstore import GitStore

LINEAGE_TYPE = "actio.candidate_lineage"
LINEAGE_DIR = "actio/lineage"
SCHEMA_VERSION = 1


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _path(store_id: str) -> str:
    return f"{LINEAGE_DIR}/{store_id}.yml"


def project_lineage(git: GitStore, sealed: dict) -> str:
    """把一份 sealed 候选谱系投影进 envelope 树;返回产物相对路径。"""
    body = unseal(sealed)
    lineage_hash = digest(sealed)
    store_id = body["store"]
    path = _path(store_id)
    version = 1
    if git.exists(path):
        existing = git.read_product(path)
        if existing.payload.get("lineage_hash") == lineage_hash:
            return path  # 幂等:谱系未变,不产生新提交
        version = existing.version + 1
    env = Envelope(
        id=f"actio-lineage-{store_id[:12]}",
        type=LINEAGE_TYPE,
        version=version,
        created_at=_now(),
        created_by=OwnerRef(),
        status="final",
        schema_version=SCHEMA_VERSION,
        payload={"lineage_hash": lineage_hash, "sealed": sealed},
    )
    git.write_product(path, env, f"actio: project candidate lineage v{version} ({lineage_hash[:12]})")
    return path
