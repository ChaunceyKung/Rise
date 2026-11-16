"""模型版本绑定审计(V3 §5.4 现实依赖;施工规划 M4)。

现状:`_make_agent_backend_factory` 忽略 checkpoint_ref,服务始终加载基座
(BASE_MODEL_NAME)。跨模型版本的收益比较因此不可信——本模块把"配置的模型
版本"与"后端实际加载权重"的核对显式化:

* verdict=match:指纹一致(服务侧可给指纹时);
* verdict=mismatch:声明了 checkpoint_ref 但服务只挂基座/指纹不符——
  可重入失败(transient),修好权重再来,不静默降级;
* verdict=unverified:未声明 ref(纯基座自证),记录在案但不阻塞。

审计记录产物化由调用方(rounds/runner)带走;此处只做判定与异常。
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256

from compute.vllm_service import BASE_MODEL_NAME


class ModelBindingMismatch(Exception):
    """可重入的绑定失败:配置声明了晋级权重,后端没有按声明加载。"""

    transient = True


@dataclass(frozen=True)
class ModelBindingAudit:
    model_id: str
    configured_ref: str | None
    requested_model: str
    loaded_fingerprint: str | None
    verdict: str  # match | mismatch | unverified
    detail: str

    def to_wire(self) -> dict:
        return {"model_id": self.model_id, "configured_ref": self.configured_ref,
                "requested_model": self.requested_model, "loaded_fingerprint": self.loaded_fingerprint,
                "verdict": self.verdict, "detail": self.detail}


def ref_fingerprint(checkpoint_ref) -> str | None:
    """声明侧指纹:BigRef/字符串都收敛为稳定摘要;None 保持 None。"""
    if checkpoint_ref is None:
        return None
    text = getattr(checkpoint_ref, "uri", None) or str(checkpoint_ref)
    return sha256(text.encode()).hexdigest()


def audit_model_binding(model_id: str, checkpoint_ref, *, requested_model: str = BASE_MODEL_NAME,
                        loaded_fingerprint: str | None = None,
                        served_adapters: tuple = ()) -> ModelBindingAudit:
    configured = ref_fingerprint(checkpoint_ref)
    if checkpoint_ref is None:
        return ModelBindingAudit(model_id, None, requested_model, loaded_fingerprint,
                                 "unverified", "未声明 checkpoint_ref;按基座自证记录在案")
    if served_adapters:
        return ModelBindingAudit(model_id, configured, requested_model, loaded_fingerprint,
                                 "match" if configured == loaded_fingerprint else "mismatch",
                                 f"服务挂了 {len(served_adapters)} 个适配器;指纹{'一致' if configured == loaded_fingerprint else '不符'}")
    # 现行部署路径:无适配器、requested=基座 → 与任何晋级声明都不符
    if requested_model == BASE_MODEL_NAME and loaded_fingerprint is None:
        return ModelBindingAudit(model_id, configured, requested_model, None, "mismatch",
                                 "声明了 checkpoint_ref,但部署服务只挂基座且未给权重指纹")
    verdict = "match" if configured == loaded_fingerprint else "mismatch"
    return ModelBindingAudit(model_id, configured, requested_model, loaded_fingerprint, verdict,
                             "指纹核对" + ("一致" if verdict == "match" else "不符"))


def verify_model_binding(model_id: str, checkpoint_ref, **kwargs) -> ModelBindingAudit:
    """审计 + 强制:mismatch 抛可重入失败;match/unverified 返回记录。"""
    audit = audit_model_binding(model_id, checkpoint_ref, **kwargs)
    if audit.verdict == "mismatch":
        raise ModelBindingMismatch(audit.detail)
    return audit
