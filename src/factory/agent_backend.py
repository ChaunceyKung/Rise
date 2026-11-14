"""智能体位后端的转换后端,以及部署服务上下文工厂。

组合根给智能体位的模型后端外面套一层本模块的转换后端:接住 factory.opponents 的 HTTP 层异常,
改抛 simple_actio.backend_errors 的四种异常(simple_actio 不许导入 factory)。
异常文字只含槽位与原异常类名,不带原异常的文字(原文可能含端点地址),也不链原异常。

make_deployment_service 是 `--agent-backend vllm` 时的部署服务上下文(设计 50 篇第 8 章、90 篇的装配表):
一个部署轮次起一个只挂基座的 vLLM 服务,智能体位与对手位共用。本模块不导入 mindagent;
上下文只被 mindagent.rounds 当成一个普通上下文管理器用。
"""
from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager, ExitStack, contextmanager
from dataclasses import dataclass, replace

from compute import service as compute_service
from compute.client import JobSpec
from compute.endpoint import ComputeEndpoint
from compute.errors import ComputeError
from compute.service import ServiceHandle
from compute.tunnel import http_probe, tunnel_factory_for
from compute.vllm_service import BASE_MODEL_NAME, VllmServeConfig, build_serve_job
from controlplane.envelope import BigRef
from factory.opponents import require_timeout
from factory.vllm_policy import VllmPolicy
from simple_actio.backend_errors import (
    AgentBackendMalformed, AgentBackendRejected, AgentBackendTimeout, AgentBackendUnavailable,
)
from simple_actio.errors import SimpleActioDataError
from simulator.backends import ModelBackend
from simulator.datamodel import RoleBinding, Scenario

from .opponents import (
    OpponentApiError, OpponentRejectedError, OpponentTimeoutError, OpponentUnavailableError,
)

# 部署服务的远端端口。固定值,且不等于 DEFAULT_SERVE_PORT(18081,--interact 与 --evaluator someval 都用它)
AGENT_SERVE_PORT = 18083


class TranslatingAgentBackend:
    """包一个带 respond_guided 的后端,把 OpponentApiError 一族改抛成 AgentBackendError 一族。"""

    def __init__(self, backend: object) -> None:
        self.backend = backend

    def respond_guided(
        self, persona, scenario, history, speaker_slot: str, guidance,
    ) -> tuple[str, str | None]:
        try:
            return self.backend.respond_guided(persona, scenario, history, speaker_slot, guidance)
        except OpponentTimeoutError as exc:
            raise AgentBackendTimeout(self._message(speaker_slot, exc)) from None
        except OpponentUnavailableError as exc:
            raise AgentBackendUnavailable(self._message(speaker_slot, exc)) from None
        except OpponentRejectedError as exc:
            raise AgentBackendRejected(self._message(speaker_slot, exc)) from None
        except OpponentApiError as exc:
            raise AgentBackendMalformed(self._message(speaker_slot, exc)) from None

    @staticmethod
    def _message(speaker_slot: str, exc: Exception) -> str:
        return f"agent backend failed for slot {speaker_slot!r}: {type(exc).__name__}"


@dataclass(frozen=True)
class DeploymentService:
    """一个部署轮次里活着的服务所交出的两样东西。绑定到本轮那个服务与它现生成的密钥,轮次结束即失效。"""

    # 轮次处理器要的 backend_factory(model_id, checkpoint_ref);每次调用返回一个新的转换后端。
    # 两个参数都不参与选权重(设计 MA-46:部署服务只挂基座)
    backend_factory: Callable[[str, BigRef | None], object]
    # AgentRuntime(opponent_backend_factory=...);每次调用返回一个新的、绑到基座的后端
    opponent_factory: Callable[[RoleBinding, Scenario], ModelBackend]


def make_deployment_service(
    *,
    client,
    endpoint: ComputeEndpoint,
    agent_timeout_s: float,
    opponent_timeout_s: float,
    serve=None,
    build_job: Callable[[VllmServeConfig], JobSpec] = build_serve_job,
    tunnel_factory: Callable[[], object] | None = None,
    probe: Callable[[str, str], bool] = http_probe,
) -> Callable[[str], AbstractContextManager[DeploymentService]]:
    """造部署服务上下文的工厂:返回的 open(round_id) 起一个只挂基座的服务,产出 DeploymentService。

    进入时经 compute.service.serve 取整机 GPU 租约、起作业、开隧道、等就绪;退出时关隧道、停服务、放租约。
    进入时的确定性失败(不是 DeferredError 子类,如显存或卡数预检不通过、VllmServeConfig 校验失败)改抛
    SimpleActioDataError,轮次处理器按 T3 判失败,原因只写异常类名;DeferredError 子类(租约被占、起不来)
    原样上抛,轮次留 pending、守护进程退避后重入。体内抛的 ComputeError 是调用方自己的,不在这里归类。

    作业规格的 env 多一项 RISE_AGENT_ROUND=<round_id>:它进作业 digest,于是每轮作业名不同。
    serve、build_job、tunnel_factory、probe 可注入,测试里不连 SSH、不起 vLLM。"""
    agent_timeout = require_timeout(agent_timeout_s)
    opponent_timeout = require_timeout(opponent_timeout_s)

    def build_round_job(round_id: str) -> Callable[[VllmServeConfig], JobSpec]:
        # 多一项 RISE_AGENT_ROUND:并进作业 digest,于是同一配置每轮作业名不同。
        # 否则旧轮次占着 MAX_ATTEMPTS 个尝试序号,第 9 轮起只会无限延后
        def build(c: VllmServeConfig) -> JobSpec:
            spec = build_job(c)
            return replace(spec, env={**spec.env, "RISE_AGENT_ROUND": round_id})
        return build

    def open(round_id: str) -> AbstractContextManager[DeploymentService]:
        if not isinstance(round_id, str) or not round_id:
            # 空 id 会让每轮并成同一个作业名,正是这一层要防的事;归 T3 而不是打崩守护进程
            raise SimpleActioDataError(f"deployment service unusable: round_id must be a non-empty str, "
                                       f"got {round_id!r}")
        return _open_service(
            client=client, base_model_path=endpoint.base_model_path,
            round_build_job=build_round_job(round_id),
            serve=serve, tunnel_factory=tunnel_factory, probe=probe,
            agent_timeout=agent_timeout, opponent_timeout=opponent_timeout,
        )

    return open


@contextmanager
def _open_service(*, client, base_model_path, round_build_job, serve, tunnel_factory, probe,
                  agent_timeout, opponent_timeout):
    """起服务并在体内交出两个工厂。确定性 ComputeError 只在进入这一段时改判,体内抛的照旧上抛。

    配置与默认隧道工厂都在这里现做,不在造工厂时就做:坏了是这一轮的事(T3),不是整个装配的事。"""
    try:
        cfg = VllmServeConfig(model_path=base_model_path, adapters=(), remote_port=AGENT_SERVE_PORT)
        factory = tunnel_factory if tunnel_factory is not None else tunnel_factory_for(client, cfg.remote_port)
    except ComputeError as exc:          # 配置校验失败、客户端不带 ssh 别名:都没占租约、没起作业
        raise SimpleActioDataError(f"deployment service unusable: {type(exc).__name__}") from None
    starter = serve if serve is not None else compute_service.serve   # 缺省在调用时才取,测试可替换
    with ExitStack() as stack:
        try:
            handle = stack.enter_context(starter(
                client, cfg, build_job=round_build_job, tunnel_factory=factory, probe=probe,
            ))
        except ComputeError as exc:                    # DeferredError 不是 ComputeError 的子类,会原样上抛
            raise SimpleActioDataError(f"deployment service unusable: {type(exc).__name__}") from None
        yield DeploymentService(
            backend_factory=_make_agent_backend_factory(handle, agent_timeout),
            opponent_factory=_make_opponent_factory(handle, opponent_timeout),
        )


def _make_agent_backend_factory(
    handle: ServiceHandle, timeout_s: float,
) -> Callable[[str, BigRef | None], object]:
    """智能体位的后端工厂:忽略 model_id 与 checkpoint_ref,每次返回绑到基座的新后端。
    外面套转换后端:simple_actio 认不得 factory.opponents 的异常。"""

    def make(model_id: str, checkpoint_ref: BigRef | None) -> object:
        return TranslatingAgentBackend(VllmPolicy(handle, BASE_MODEL_NAME, timeout_s=timeout_s))

    return make


def _make_opponent_factory(
    handle: ServiceHandle, timeout_s: float,
) -> Callable[[RoleBinding, Scenario], ModelBackend]:
    """对手位的工厂:忽略 binding.model_ref,一律由同一个服务的基座说话(本轮只挂基座,没有适配器可挑)。"""

    def make(binding: RoleBinding, scenario: Scenario) -> ModelBackend:
        return VllmPolicy(handle, BASE_MODEL_NAME, timeout_s=timeout_s)

    return make
