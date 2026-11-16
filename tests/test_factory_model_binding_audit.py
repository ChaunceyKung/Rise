"""模型版本绑定审计(施工规划 M4 验收)。"""
from __future__ import annotations

import pytest

from factory.model_binding import ModelBindingMismatch, audit_model_binding, ref_fingerprint, verify_model_binding


def test_unverified_when_no_ref_is_declared():
    audit = audit_model_binding("zengen-v1", None)
    assert audit.verdict == "unverified" and audit.configured_ref is None
    assert verify_model_binding("zengen-v1", None).verdict == "unverified"  # 不阻塞


def test_mismatch_when_ref_declared_but_base_is_served():
    """现行部署路径的真实缺口:声明了晋级权重,服务只挂基座。"""
    ref = "checkpoints/zengen-v2@abc123"  # 指纹层对 BigRef/字符串一视同仁(str 收敛)
    audit = audit_model_binding("zengen-v1", ref)
    assert audit.verdict == "mismatch"
    assert "只挂基座" in audit.detail
    with pytest.raises(ModelBindingMismatch, match="基座"):
        verify_model_binding("zengen-v1", ref)


def test_match_and_mismatch_by_fingerprint():
    from controlplane.envelope import BigRef  # noqa: F401  (BigRef 同样经 str() 收敛指纹)
    ref = "checkpoints/zengen-v2@deadbeef"
    fp = ref_fingerprint(ref)
    assert audit_model_binding("m", ref, requested_model="served",
                               loaded_fingerprint=fp).verdict == "match"
    with pytest.raises(ModelBindingMismatch):
        verify_model_binding("m", ref, requested_model="served", loaded_fingerprint="0" * 64)
    # 挂了适配器时按指纹判
    adapters_audit = audit_model_binding("m", ref, served_adapters=("a1",), loaded_fingerprint=fp)
    assert adapters_audit.verdict == "match"


def test_audit_is_serializable_for_run_records():
    wire = audit_model_binding("m", None).to_wire()
    assert set(wire) == {"model_id", "configured_ref", "requested_model",
                         "loaded_fingerprint", "verdict", "detail"}
