"""智能体位后端:转换后端,以及部署服务上下文工厂。

serve 是注入的替身(不连 SSH、不起 vLLM);两角色共用同一个服务的那条对着本机 http.server 桩测。"""
from __future__ import annotations

import hashlib
import json
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import pytest
from compute_fixtures import fake_endpoint

from compute.errors import ComputeBusyError, ComputeError
from compute.service import ServiceHandle
from compute.vllm_service import BASE_MODEL_NAME, build_serve_job
from controlplane.envelope import BigRef
from factory.agent_backend import (
    AGENT_SERVE_PORT, TranslatingAgentBackend, make_deployment_service,
)
from factory.opponents import (OpponentApiError, OpponentRejectedError, OpponentTimeoutError,
                               OpponentUnavailableError)
from factory.vllm_policy import VllmPolicy
from simple_actio.backend_errors import (AgentBackendMalformed, AgentBackendRejected, AgentBackendTimeout,
                                         AgentBackendUnavailable)
from simple_actio.errors import SimpleActioDataError
from simulator.datamodel import Persona, RoleBinding, RoleSlot, Scenario

KEY = "deploy-key-must-not-leak"
C = SimpleNamespace(alias="gpu-1")
EP = fake_endpoint()
BINDING_USER = RoleBinding("user", "p-user", "frozen_reference", model_ref="zengen-v1")


def _persona():
    return Persona(id="p", traits=["急躁"], motivation="想让对方道歉", speech_style="短句", values=["公平"])


def _scenario():
    return Scenario("s1", "合租屋里水电费分摊", [RoleSlot("agent", "室友甲"), RoleSlot("user", "室友乙")],
                    "谁该多付", ["不人身攻击"], "training")


def _digest(spec):
    """与 compute.service._pick_attempt 同一个算法:作业名由 argv、env、secret_env 决定。"""
    return hashlib.sha256(
        json.dumps({"argv": list(spec.argv), "env": dict(spec.env), "secret_env": spec.secret_env},
                   sort_keys=True).encode("utf-8")
    ).hexdigest()[:12]


# ---------------- 转换后端 ----------------

class _Raises:
    def __init__(self, exc): self.exc = exc
    def respond_guided(self, *a): raise self.exc


@pytest.mark.parametrize("raised, expected", [
    (OpponentTimeoutError("t http://10.0.0.1"), AgentBackendTimeout),
    (OpponentUnavailableError("u"), AgentBackendUnavailable),
    (OpponentRejectedError("r"), AgentBackendRejected),
    (OpponentApiError("empty reply"), AgentBackendMalformed),
])
def test_opponent_api_errors_become_agent_backend_errors(raised, expected):
    with pytest.raises(expected) as info:
        TranslatingAgentBackend(_Raises(raised)).respond_guided(None, None, [], "agent", ())
    assert "10.0.0.1" not in str(info.value) and info.value.__cause__ is None


def test_a_good_reply_passes_through_untouched():
    class Ok:
        def respond_guided(self, *a): return ("hi", None)
    assert TranslatingAgentBackend(Ok()).respond_guided(None, None, [], "agent", ()) == ("hi", None)


# ---------------- 假 serve ----------------

class FakeServe:
    """照 compute.service.serve 的签名:调用时就造作业规格(与真 serve 一样),进入时产出指向 handle 的上下文。
    进出记进 trace;enter_raises 非空时进入就抛(租约被占、服务起不来)。"""

    def __init__(self, handle=None, *, enter_raises=None):
        self.handle = handle or ServiceHandle("serve-x-a1", "http://127.0.0.1:1", KEY, (BASE_MODEL_NAME,))
        self.enter_raises = enter_raises
        self.trace = []
        self.calls = []
        self.cfg = None
        self.spec = None
        self.build_job = None
        self.tunnel_factory = None
        self.probe = None

    def __call__(self, client, cfg, *, build_job, tunnel_factory, probe):
        self.calls.append((client, cfg, {"build_job": build_job, "tunnel_factory": tunnel_factory, "probe": probe}))
        self.cfg = cfg
        self.build_job, self.tunnel_factory, self.probe = build_job, tunnel_factory, probe
        self.spec = build_job(cfg)
        return self._context()

    @contextmanager
    def _context(self):
        self.trace.append("enter")
        if self.enter_raises is not None:
            raise self.enter_raises
        try:
            yield self.handle
        finally:
            self.trace.append("exit")

    @property
    def exited(self):
        return self.trace[-1:] == ["exit"]


@pytest.fixture
def fake_serve():
    return FakeServe()


def _open(serve, *, client=C, endpoint=EP, agent_timeout_s=120, opponent_timeout_s=60, **kw):
    return make_deployment_service(
        client=client, endpoint=endpoint, agent_timeout_s=agent_timeout_s,
        opponent_timeout_s=opponent_timeout_s, serve=serve, **kw,
    )


# ---------------- 服务配置 ----------------

def test_the_service_serves_only_the_base_on_its_own_port(fake_serve):
    with _open(fake_serve)("agent-round-m"):
        pass
    cfg = fake_serve.cfg
    assert (cfg.adapters, cfg.remote_port, cfg.model_path) == ((), 18083, EP.base_model_path)
    assert AGENT_SERVE_PORT == 18083
    assert fake_serve.calls[0][0] is C


def test_the_default_build_job_is_the_serve_job_with_the_round_in_its_env(fake_serve):
    with _open(fake_serve)("agent-round-m"):
        pass
    plain = build_serve_job(fake_serve.cfg)
    assert fake_serve.spec.argv == plain.argv
    assert dict(fake_serve.spec.env) == {**plain.env, "RISE_AGENT_ROUND": "agent-round-m"}
    assert fake_serve.spec.secret_env == plain.secret_env


def test_two_rounds_get_distinct_serve_job_ids():
    fake = FakeServe()
    make = _open(fake)
    specs = []
    for round_id in ("agent-round-a", "agent-round-b"):
        with make(round_id):
            specs.append(fake.spec)
    envs = [dict(spec.env) for spec in specs]
    assert envs[0]["RISE_AGENT_ROUND"] == "agent-round-a" and envs[1]["RISE_AGENT_ROUND"] == "agent-round-b"
    assert envs[0]["NCCL_NVLS_ENABLE"] == "0"                 # 原有 env 一项不丢
    assert _digest(specs[0]) != _digest(specs[1])             # 于是每轮的作业名不同,不占同一个尝试序号


def test_the_default_tunnel_goes_through_the_clients_ssh_alias_and_the_agent_port(monkeypatch):
    opened = []

    class RecordingTunnel:
        def __init__(self, alias, *, remote_port):
            opened.append((alias, remote_port))

    monkeypatch.setattr("compute.tunnel.SshTunnel", RecordingTunnel)   # 不起真的 ssh
    fake = FakeServe()
    with _open(fake, client=SimpleNamespace(alias="gpu-7"))("r"):
        pass
    assert opened == []                        # 工厂此刻还没被调用
    fake.tunnel_factory()
    assert opened == [("gpu-7", 18083)]


def test_the_default_serve_is_taken_lazily_from_the_compute_layer(monkeypatch):
    fake = FakeServe()
    monkeypatch.setattr("compute.service.serve", fake)     # 缺省值在进入时才取,不在造工厂时绑定
    with make_deployment_service(client=C, endpoint=EP, agent_timeout_s=120, opponent_timeout_s=60)("r") as svc:
        assert isinstance(svc.backend_factory("m", None), TranslatingAgentBackend)
    assert fake.trace == ["enter", "exit"]


def test_a_client_without_an_ssh_alias_is_a_data_error_before_serving():
    fake = FakeServe()
    with pytest.raises(SimpleActioDataError, match="deployment service unusable: ComputeError"):
        with _open(fake, client=SimpleNamespace())("r"):
            pass
    assert fake.calls == []                     # 没进 serve:不占租约


def test_an_injected_tunnel_factory_and_probe_are_passed_through(fake_serve):
    tunnel, probe = (lambda: None), (lambda url, key: True)
    with _open(fake_serve, tunnel_factory=tunnel, probe=probe)("r"):
        pass
    (_, _, kw), = fake_serve.calls
    assert kw["tunnel_factory"] is tunnel and kw["probe"] is probe


# ---------------- 两个角色位的后端 ----------------

def test_backend_factory_ignores_the_checkpoint_and_translates_errors(fake_serve):
    ref = BigRef("roll://ckpt/t1", "a" * 64, 0)
    with _open(fake_serve)("r") as svc:
        b = svc.backend_factory("zengen-v2", ref)          # model_id 与 checkpoint_ref 都不参与选权重
    assert isinstance(b, TranslatingAgentBackend)
    assert isinstance(b.backend, VllmPolicy) and b.backend._model == BASE_MODEL_NAME
    assert b.backend._timeout == 120


def test_backend_factory_gives_a_fresh_backend_each_call(fake_serve):
    with _open(fake_serve)("r") as svc:
        assert svc.backend_factory("m", None) is not svc.backend_factory("m", None)


def test_opponents_speak_through_the_base_whatever_their_model_ref(fake_serve):
    with _open(fake_serve)("r") as svc:
        o = svc.opponent_factory(BINDING_USER, _scenario())
    assert isinstance(o, VllmPolicy) and o._model == BASE_MODEL_NAME
    assert o._timeout == 60


# ---------------- 进入服务的失败 ----------------

def test_a_busy_lease_propagates_as_deferred():
    busy = FakeServe(enter_raises=ComputeBusyError("the GPU lease is held by job serve-other-a1"))
    with pytest.raises(ComputeBusyError):
        with _open(busy)("r"):
            pytest.fail("the body must not run when the service did not come up")


def test_a_deterministic_compute_error_on_entry_is_a_data_error():
    broken = FakeServe(enter_raises=ComputeError("not enough GPUs"))
    with pytest.raises(SimpleActioDataError, match="deployment service unusable: ComputeError"):
        with _open(broken)("r"):
            pytest.fail("the body must not run when the service did not come up")
    assert broken.trace == ["enter"]           # 没到收尾那一步


def test_a_bad_endpoint_is_a_data_error_before_the_service_is_even_asked():
    # 真 ComputeEndpoint 自己就拦相对路径;这里绕过它,让 VllmServeConfig 的校验失败
    fake = FakeServe()
    bad = SimpleNamespace(endpoint_id="gpu-1", base_model_path="relative/path")
    with pytest.raises(SimpleActioDataError, match="deployment service unusable: ComputeError"):
        with _open(fake, endpoint=bad)("r"):
            pass
    assert fake.trace == [] and fake.calls == []      # VllmServeConfig 校验失败:不占租约


def test_a_compute_error_from_the_body_is_not_blamed_on_the_service(fake_serve):
    with pytest.raises(ComputeError, match="boom"):
        with _open(fake_serve)("r"):
            raise ComputeError("boom")
    assert fake_serve.trace == ["enter", "exit"]      # 服务照旧停掉,异常照旧是调用方自己的


@pytest.mark.parametrize("round_id", ["", None])
def test_a_round_id_is_required_so_every_round_gets_its_own_job(round_id):
    fake = FakeServe()
    with pytest.raises(SimpleActioDataError, match="round_id"):
        _open(fake)(round_id)
    assert fake.calls == []


# ---------------- 本机 http.server 桩:两个角色共用同一个服务 ----------------

class _Stub:
    """记下每次 POST 的 model、system 与认证头;一律回一句可用的话。"""

    def __init__(self):
        self.requests = []
        stub = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802
                length = int(self.headers.get("Content-Length", "0"))
                body = json.loads(self.rfile.read(length))
                stub.requests.append({
                    "model": body["model"],
                    "system": body["messages"][0]["content"],
                    "authorization": self.headers.get("Authorization"),
                })
                payload = json.dumps({"choices": [{"message": {"role": "assistant", "content": "好吧"}}]}).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def stub(monkeypatch):
    monkeypatch.setenv("NO_PROXY", "127.0.0.1")   # 本机若配了代理,别让桩的请求绕出去
    monkeypatch.setenv("no_proxy", "127.0.0.1")
    s = _Stub()
    yield s
    s.close()


def test_both_roles_hit_the_same_service(stub):
    handle = ServiceHandle("serve-x-a1", stub.url, KEY, (BASE_MODEL_NAME,))
    fake = FakeServe(handle)
    with _open(fake)("r") as svc:
        assert KEY not in repr(svc)                         # 交出去的只有工厂,不含服务密钥
        svc.backend_factory("m", None).respond_guided(_persona(), _scenario(), [], "agent", ("先回应情绪",))
        svc.opponent_factory(BINDING_USER, _scenario()).respond(_persona(), _scenario(), [], "user")
    assert [r["model"] for r in stub.requests] == [BASE_MODEL_NAME, BASE_MODEL_NAME]
    assert "先回应情绪" in stub.requests[0]["system"]
    assert "先回应情绪" not in stub.requests[1]["system"]
    assert fake.exited                                      # 退出上下文就停服务
    assert {r["authorization"] for r in stub.requests} == {f"Bearer {KEY}"}
