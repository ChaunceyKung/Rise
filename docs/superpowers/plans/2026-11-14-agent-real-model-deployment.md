# 场景三真模型部署后端 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 场景三两种驱动并存。`--agent-backend vllm` 时部署轮次里智能体位与对手位都经远端 vLLM 由纯基座 `Qwen3.8-Flash-Next` 说话;缺省 `canned` 时智能体位拼指导语、对手位按情境剧本回复(没带剧本念全局台词)。目标是在 171 上把真模型部署跑通一次。

**Architecture:** 组合根(`factory`)造一个"部署服务上下文工厂",经 `make_start_round_handler` 的可选参数注入轮次处理器;轮次在写 `pending`、输入检查通过之后进入它,上下文起一个带轮次身份、只挂基座的 vLLM 服务,交出智能体位后端工厂,并把同一服务上的对手后端装到共用运行时的部署对手开关上;处理器返回或抛出时退出,停服务放租约。智能体位后端外面由组合根套一层异常转换,`mindagent` 只认 `simple_actio` 里新增的四种后端失败异常,不导入 `compute` 与 `factory`。

**Tech Stack:** Python 3.14、pytest、uv(`uv run --offline --extra dev`)、ruff;既有的 `compute.service.serve`、`factory.vllm_policy.VllmPolicy`、`factory.opponents.post_chat`。

**Spec:** `docs/superpowers/specs/2026-11-14-agent-real-model-deployment-design.md`;权威设计在 `docs/design/`(00、20、50、60、90 篇)。两者冲突以 `docs/design/` 为准。

## Global Constraints

- 缺省 `--agent-backend canned`:不加开关、情境没带剧本时,装配、运行时时限、轮次产物、部署对手的行为与今天逐字节相同。现有测试只改 Task 6 点名的两条(它们钉住的正是"部署会话不读剧本",D11 有意改变它),其余一条不改就通过。
- 罐头模式下智能体位仍是 `CannedGuidedBackend` 的指导语拼接,不读剧本。
- `mindagent` 只导入 `controlplane`、`simple_actio`、`inference_bridge`、`simulator`(`docs/design/tools/check_consistency.py` 的 `ALLOWED_DEPS`);不导入 `compute`、`factory`。
- `simple_actio` 只导入 `simulator`。
- vLLM 服务只挂基座:`VllmServeConfig.adapters == ()`,模型名 `compute.vllm_service.BASE_MODEL_NAME`;`checkpoint_ref` 不参与选择。
- 远端端口不等于 `factory.eval_config.DEFAULT_SERVE_PORT`(18081);本计划取 18083。
- 时限:智能体位单次 HTTP = `budget.policy_s`(120);部署对手位单次 HTTP = `budget.opponent_s`(60);服务端等智能体位一次提交 = `budget.interact_turn_s`(与训练位等提交同一推法,拉起缺省 206、8787 为 8183);部署流每轮 = `max(等智能体位提交, budget.backend_s)`。
- 异常与失败原因的文字只含类名、作业 id、槽位,不含密钥、远端地址、响应体。
- 测试命令一律 `PYTHONDONTWRITEBYTECODE=1 uv run --offline --extra dev pytest ...`;每个任务结束前跑 `uv run --offline --extra dev ruff check` 覆盖改过的文件。
- 提交信息用中文,格式 `feat(<包>): ...` / `fix(<包>): ...` / `docs(design): ...`,与仓库现有提交一致。

## 本计划不做(留给以后,设计里已写)

只为"跑通一次"做必需的部分。下面这些在 `docs/design/` 里标 [计划中],本计划不施工,落地文档时仍保持 [计划中]:

- 轮次产物的 `deployment_backend` 与换后端的比较规则(50 篇 MA-48、MA-I18),以及 `agent_rsi` 的可选锚定字段(60 篇)。真机验证用一棵新树,碰不到;真机验收不核对 `deployment_backend`,60 篇这一行保持 [计划中]。
- 回复为空的有界重跑、验证段里智能体位失败的延后与 T3、停不掉的服务点名作业(50 篇第 8 章对应行)。本计划里它们按现行去向走:回复为空不重跑、轮次 T3;验证段的智能体位异常原样上抛;`ServeStopError` 按 `DeferredError` 延后。这几行在 `docs/design/` 里保持 [计划中],真机验收不核对它们。
- 确定性 `ComputeError` 不在此列:它不转换就会让守护进程带回溯退出,真机第一次跑就可能撞上,所以放进 Task 4。
- 验证段改回罐头后端省调用。本计划里验证段照设计也用真模型。

## Review Focus

- 同一端点同一配置连续跑多轮:每轮的 `serve-*` 作业名不同(带轮次 id),第 9 轮不撞尝试序号上限 → Task 4 的 `test_two_rounds_get_distinct_serve_job_ids`。
- 输入缺失、已终态、被取代时不起服务、不取租约 → Task 5 的 `test_no_service_is_started_when_inputs_are_missing` 与 `test_no_service_for_a_terminal_round`。
- 罐头模式下情境带了剧本:对手位按剧本循环回复,绑定没写 `driver: scripted` 也一样;智能体位仍拼指导语 → Task 6 的 `test_a_canned_deployment_opponent_follows_the_scenario_script`。
- `vllm` 模式下情境带了剧本:对手位由模型说话,剧本不生效;显式 `driver: scripted` 仍念剧本 → Task 7 的 `test_the_model_switch_overrides_the_script_but_not_an_explicit_scripted_driver`。
- 部署对手位的模型调用超时:服务端照旧归 `role_backend_timeout`,驱动器回滚重跑,不让守护进程带回溯退出 → Task 7 的 `test_a_slow_model_opponent_is_a_transient_attempt`。

---

## File Structure

| 文件 | 动作 | 职责 |
|---|---|---|
| `src/simple_actio/backend_errors.py` | 新建 | 四种智能体位后端失败异常(`simple_actio` 层,`mindagent` 认它们) |
| `src/factory/agent_backend.py` | 新建 | 智能体位转换后端;部署服务上下文工厂 `make_deployment_service` |
| `src/factory/cli.py` | 改 | `--agent-backend` 选项 |
| `src/factory/wire.py` | 改 | `FactoryOptions.agent_backend`、组合规则、`deploy_turn_timeout_s` 加参数、装配时造上下文工厂放进 `BuildContext` |
| `src/factory/handlers.py` | 改 | `_agent` 把上下文工厂与流 deadline 传给轮次处理器 |
| `src/factory/agent.py` | 改 | `_backends` 部署会话的剧本优先;`AgentRuntime.bind_deployment_opponents` |
| `src/factory/memory_budget.py` | 改 | `deploy_turn_s` 文档串去掉"罐头";新增 `agent_deploy_turn_s`、`agent_deploy_per_turn_s` |
| `src/mindagent/deployment.py` | 改 | 驱动器把四种后端失败异常归成一次失败尝试 |
| `src/mindagent/rounds.py` | 改 | `deployment_service` 参数与进入点 |
| `docs/design/00、20、50、90` 篇 | 改 | 落地的条目从 [计划中] 改成 [已落地](Task 8) |
| `tests/test_simple_actio_backend_errors.py`、`tests/test_factory_agent_backend.py` | 新建 | 对应新模块 |

---

### Task 1: 智能体位后端失败异常与转换后端

**Files:**
- Create: `src/simple_actio/backend_errors.py`
- Create: `src/factory/agent_backend.py`(本任务只放转换后端)
- Test: `tests/test_simple_actio_backend_errors.py`、`tests/test_factory_agent_backend.py`

**Interfaces:**
- Produces:
  - `simple_actio.backend_errors`:`class AgentBackendError(Exception)` 基类,带类属性 `reason: str` 与 `transient: bool`;四个子类与取值:`AgentBackendTimeout`(`"role_backend_timeout"`, True)、`AgentBackendUnavailable`(`"role_backend_unavailable"`, True)、`AgentBackendRejected`(`"role_backend_rejected"`, False)、`AgentBackendMalformed`(`"role_backend_failure"`, False)。
  - `factory.agent_backend.TranslatingAgentBackend(backend)`:有 `respond_guided(persona, scenario, history, speaker_slot, guidance) -> tuple[str, str | None]`;捕获 `factory.opponents` 的 `OpponentTimeoutError`、`OpponentUnavailableError`、`OpponentRejectedError`、其余 `OpponentApiError`,依次改抛上面四个子类,文字只含槽位与原异常类名,`from None` 不链原异常。

- [ ] **Step 1: 写失败的测试**

```python
# tests/test_simple_actio_backend_errors.py
from simple_actio.backend_errors import (AgentBackendError, AgentBackendMalformed, AgentBackendRejected,
                                         AgentBackendTimeout, AgentBackendUnavailable)

def test_each_agent_backend_error_carries_its_termination_reason_and_transience():
    assert [(c.reason, c.transient) for c in (AgentBackendTimeout, AgentBackendUnavailable,
                                              AgentBackendRejected, AgentBackendMalformed)] == [
        ("role_backend_timeout", True), ("role_backend_unavailable", True),
        ("role_backend_rejected", False), ("role_backend_failure", False)]
    assert all(issubclass(c, AgentBackendError) for c in (AgentBackendTimeout, AgentBackendMalformed))
```

```python
# tests/test_factory_agent_backend.py
import pytest
from factory.agent_backend import TranslatingAgentBackend
from factory.opponents import (OpponentApiError, OpponentRejectedError, OpponentTimeoutError,
                               OpponentUnavailableError)
from simple_actio.backend_errors import (AgentBackendMalformed, AgentBackendRejected, AgentBackendTimeout,
                                         AgentBackendUnavailable)

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
```

- [ ] **Step 2: 跑测试确认失败**

Run: `PYTHONDONTWRITEBYTECODE=1 uv run --offline --extra dev pytest tests/test_simple_actio_backend_errors.py tests/test_factory_agent_backend.py -q`
Expected: FAIL,`ModuleNotFoundError: No module named 'simple_actio.backend_errors'`

- [ ] **Step 3: 实现两个模块**

`backend_errors.py` 只定义上面五个类;`TranslatingAgentBackend.respond_guided` 先按子类顺序 `except`(三个子类在前,`OpponentApiError` 最后)。文字形如 `f"agent backend failed for slot {speaker_slot!r}: {type(exc).__name__}"`,`raise ... from None`。

- [ ] **Step 4: 跑测试确认通过**

Run: 同 Step 2。Expected: PASS(5 passed)

- [ ] **Step 5: 提交**

```bash
git add src/simple_actio/backend_errors.py src/factory/agent_backend.py tests/test_simple_actio_backend_errors.py tests/test_factory_agent_backend.py
git commit -m "feat(simple_actio): 智能体位后端的四种失败异常,组合根的转换后端"
```

---

### Task 2: 部署驱动器把智能体位后端失败归成一次失败尝试

**Files:**
- Modify: `src/mindagent/deployment.py`(`_attempt`,`instance.respond` 那段 `try`,约 316-323 行)
- Test: `tests/test_ma_deployment.py`

**Interfaces:**
- Consumes: Task 1 的 `simple_actio.backend_errors.AgentBackendError`(读 `reason`、`transient`)。
- Produces: 部署 episode 的终止原因多出四种来源;`role_backend_timeout`、`role_backend_unavailable` 已在 `TRANSIENT_REASONS`,回滚重跑;`role_backend_rejected` 不重跑;`role_backend_failure` 不重跑(回复为空的有界重跑不在本计划)。

- [ ] **Step 1: 写失败的测试**

在 `tests/test_ma_deployment.py` 加一个后端替身 `_AgentRaises(exc)`(`respond_guided` 抛 `exc`),用该文件现有的驱动器夹具跑一条 episode:

```python
def test_an_agent_backend_timeout_is_a_transient_attempt_and_the_world_is_rolled_back(...):
    # 第一次尝试抛 AgentBackendTimeout,第二次正常
    ...
    assert [a["reason"] for a in failed_attempts] == ["role_backend_timeout"]
    assert len(episodes) == 1                 # 第二次尝试成功
    assert client.aborted                     # 失败的那次先 abort 了会话

def test_an_agent_backend_rejection_fails_the_episode_without_retry(...):
    with pytest.raises(DeploymentFailedError) as info:
        ...
    assert (info.value.reason, info.value.transient, info.value.attempts) == ("role_backend_rejected", False, 1)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `PYTHONDONTWRITEBYTECODE=1 uv run --offline --extra dev pytest tests/test_ma_deployment.py -q -k agent_backend`
Expected: FAIL,`AgentBackendTimeout` 原样穿出

- [ ] **Step 3: 在 `_attempt` 的 `except MemoryFailureError` 旁边加 `except AgentBackendError as exc: raise _AttemptFailed(exc.reason, type(exc).__name__, exc.transient) from None`**

- [ ] **Step 4: 跑 `tests/test_ma_deployment.py tests/test_ma_deployment_starling.py tests/test_interact_parity.py` 全部通过**

- [ ] **Step 5: 提交** `feat(mindagent): 部署驱动器把智能体位后端失败归成一次失败尝试`

---

### Task 3: 开关、组合规则与运行时等提交时限

**Files:**
- Modify: `src/factory/cli.py:45-56`、`:109-112`;`src/factory/wire.py`(`FactoryOptions`、`assemble` 校验段、`deploy_turn_timeout_s`、`_runtime_timeouts`);`src/factory/memory_budget.py`
- Test: `tests/test_factory_wire.py`、`tests/test_factory_memory_wiring.py`、`tests/test_factory_cli.py`、`tests/test_factory_memory_budget.py`

**Interfaces:**
- Produces:
  - `factory.wire.AGENT_BACKENDS = ("canned", "vllm")`;`FactoryOptions.agent_backend: str = "canned"`。
  - `deploy_turn_timeout_s(*, interact: bool, starling: bool, agent_backend: str = "canned", budget=None) -> float | None`:`agent_backend == "vllm"` 时返回 `budget.agent_deploy_turn_s`,与 `interact` 同开取较大值;否则与今天一致。
  - `MemoryTimeBudget.agent_deploy_turn_s`(只读属性,= `interact_turn_s`)与 `agent_deploy_per_turn_s`(= `max(interact_turn_s, backend_s)`)。
- Consumes: 无。

- [ ] **Step 1: 写失败的测试**

```python
# tests/test_factory_memory_wiring.py
def test_the_vllm_agent_backend_waits_as_long_as_a_training_turn():
    assert deploy_turn_timeout_s(interact=False, starling=True, agent_backend="vllm") == 150.0
    assert deploy_turn_timeout_s(interact=False, starling=True, agent_backend="canned") == 40.0

# tests/test_factory_memory_budget.py
def test_agent_deploy_layers_follow_the_training_turn():
    b = BASE_LAYERS
    assert b.agent_deploy_turn_s == b.interact_turn_s == 150.0
    assert b.agent_deploy_per_turn_s == max(b.interact_turn_s, b.backend_s)

# tests/test_factory_wire.py:四条拒绝与一条通过(用该文件现有的 store 夹具与 Starling 记忆替身)
@pytest.mark.parametrize("opts, match", [
    (dict(agent_backend="gpu"), r"agent backend must be one of"),
    (dict(agent_backend="vllm", switches=()), r"--agent-backend vllm needs --enable agent"),
    (dict(agent_backend="vllm", switches=("agent",), interact=True), r"cannot be combined with --interact"),
])
def test_agent_backend_combinations_are_rejected_at_assembly(store, opts, match): ...

def test_agent_backend_vllm_with_stand_in_memory_is_rejected(store): ...   # 不设 RISE_MEMORY_CONFIG
    # match r"--agent-backend vllm needs the Starling memory service"

def test_endpoint_is_allowed_with_agent_backend_vllm(store): ...           # 不再报 "--endpoint only makes sense"

def test_the_shared_runtime_waits_for_the_agent_turn_under_vllm(store_with_starling): ...
    # assemble 后 assembly 里运行时的 _timeout == budget.agent_deploy_turn_s
```

`tests/test_factory_cli.py`:`--agent-backend vllm` 解析进 `FactoryOptions.agent_backend`;缺省 `"canned"`。

- [ ] **Step 2: 跑测试确认失败**(`AttributeError: agent_backend` / `TypeError: unexpected keyword`)

- [ ] **Step 3: 实现**

- `cli.py`:`p.add_argument("--agent-backend", choices=AGENT_BACKENDS, default="canned", help=...)`;`--endpoint` 的 help 补"或 --agent-backend vllm";传给 `FactoryOptions`。
- `wire.py` 校验段(紧跟 `--interact` 与 `--executor roll` 的互斥之后),错误文字照下面写:
  - `f"agent backend must be one of {list(AGENT_BACKENDS)}, got {options.agent_backend!r}"`
  - `"--agent-backend vllm needs --enable agent: it replaces the deployment round's backend"`
  - `"--agent-backend vllm cannot be combined with --interact: both hold the whole-host GPU lease"`
  - `--endpoint` 那条改成 `executor == "roll" or interact or agent_backend == "vllm"` 时允许。
- 记忆替身的拒绝放在 `memory_wiring(...)` 之后:`memory is None or memory.backend != "starling"` 时抛 `"--agent-backend vllm needs the Starling memory service (set RISE_MEMORY_CONFIG); the stand-in memory has no deployment time budget"`。
- `_runtime_timeouts` 把 `options.agent_backend` 传给 `deploy_turn_timeout_s`。
- `memory_budget.py`:`deploy_turn_s` 那行文档串改成"一轮记忆(罐头智能体位;真模型见 `agent_deploy_turn_s`)";两个属性按 Interfaces 定义;`violations()` 不变(两层由已校验的层直接导出)。

- [ ] **Step 4: 跑 `tests/test_factory_wire.py tests/test_factory_memory_wiring.py tests/test_factory_cli.py tests/test_factory_memory_budget.py tests/test_factory_wire_someval.py` 全部通过**

- [ ] **Step 5: 提交** `feat(factory): --agent-backend 开关、组合规则与真模型部署的等提交时限`

---

### Task 4: 部署服务上下文工厂

**Files:**
- Modify: `src/factory/agent_backend.py`
- Test: `tests/test_factory_agent_backend.py`

**Interfaces:**
- Consumes: Task 1 的 `TranslatingAgentBackend`;`compute.service.serve`、`compute.vllm_service.VllmServeConfig`/`build_serve_job`/`BASE_MODEL_NAME`;`factory.vllm_policy.VllmPolicy`;`compute.tunnel.tunnel_factory_for`、`http_probe`。
- Produces:
  - `AGENT_SERVE_PORT = 18083`。
  - `DeploymentService`(dataclass):`backend_factory: Callable[[str, BigRef | None], object]`、`opponent_factory: Callable[[RoleBinding, Scenario], ModelBackend]`。
  - `make_deployment_service(*, client, endpoint, agent_timeout_s: float, opponent_timeout_s: float, serve=None, build_job=build_serve_job, tunnel_factory=None, probe=http_probe) -> Callable[[str], AbstractContextManager[DeploymentService]]`:进入时的确定性 `ComputeError`(不是 `DeferredError` 子类,例如显存或卡数预检、`VllmServeConfig` 校验失败)改抛 `simple_actio.errors.SimpleActioDataError(f"deployment service unusable: {type(exc).__name__}")`,轮次经 `rounds.py` 现有的 `except (MindAgentDataError, SimpleActioDataError)` 判 T3;`DeferredError` 子类原样上抛。返回的 `open(round_id)` 起服务;作业规格的 `env` 多一项 `RISE_AGENT_ROUND=<round_id>`(进作业 digest,于是每轮作业名不同);`backend_factory(model_id, ckpt)` 每次返回 `TranslatingAgentBackend(VllmPolicy(handle, BASE_MODEL_NAME, timeout_s=agent_timeout_s))`;`opponent_factory(binding, scenario)` 每次返回 `VllmPolicy(handle, BASE_MODEL_NAME, timeout_s=opponent_timeout_s)`,忽略 `binding.model_ref`。

- [ ] **Step 1: 写失败的测试**(注入一个记录参数的 `serve` 替身,yield 一个 `ServiceHandle("serve-x-a1", "http://127.0.0.1:1", KEY, (BASE_MODEL_NAME,))`)

```python
def test_the_service_serves_only_the_base_on_its_own_port(fake_serve):
    with make_deployment_service(client=C, endpoint=EP, agent_timeout_s=120, opponent_timeout_s=60,
                                 serve=fake_serve)("agent-round-m") as svc:
        pass
    cfg = fake_serve.cfg
    assert (cfg.adapters, cfg.remote_port, cfg.model_path) == ((), 18083, EP.base_model_path)

def test_two_rounds_get_distinct_serve_job_ids(fake_serve):
    # 用真的 build_serve_job 包一层,记下两次的 JobSpec.env
    ...
    assert envs[0]["RISE_AGENT_ROUND"] == "agent-round-a" and envs[1]["RISE_AGENT_ROUND"] == "agent-round-b"
    assert _digest(specs[0]) != _digest(specs[1])          # compute.service._pick_attempt 的同一算法

def test_backend_factory_ignores_the_checkpoint_and_translates_errors(fake_serve):
    with make_deployment_service(...)("r") as svc:
        b = svc.backend_factory("zengen-v2", SOME_REF)
    assert isinstance(b, TranslatingAgentBackend) and b.backend._model == BASE_MODEL_NAME

def test_opponents_speak_through_the_base_whatever_their_model_ref(fake_serve):
    with make_deployment_service(...)("r") as svc:
        o = svc.opponent_factory(RoleBinding("user", "p", "frozen_reference", model_ref="zengen-v1"), SCEN)
    assert o._model == BASE_MODEL_NAME

def test_a_busy_lease_propagates_as_deferred(fake_serve_busy):
    with pytest.raises(ComputeBusyError):
        with make_deployment_service(..., serve=fake_serve_busy)("r"): pass

def test_a_deterministic_compute_error_on_entry_is_a_data_error(fake_serve_raises):
    # fake_serve_raises 进入时抛 ComputeError("not enough GPUs")
    with pytest.raises(SimpleActioDataError, match="deployment service unusable: ComputeError"):
        with make_deployment_service(..., serve=fake_serve_raises)("r"): pass

def test_both_roles_hit_the_same_service(stub_vllm):
    # stub_vllm:本机 HTTP 替身,记下每次 POST 的 model 与 system 消息;fake_serve 交出指向它的 ServiceHandle
    with make_deployment_service(..., serve=serve_to(stub_vllm))("r") as svc:
        svc.backend_factory("m", None).respond_guided(P, SCEN, [], "agent", ("先回应情绪",))
        svc.opponent_factory(BINDING_USER, SCEN).respond(P, SCEN, [], "user")
    assert [r.model for r in stub_vllm.requests] == [BASE_MODEL_NAME, BASE_MODEL_NAME]
    assert "先回应情绪" in stub_vllm.requests[0].system and "先回应情绪" not in stub_vllm.requests[1].system
    assert fake_serve.exited                                  # 退出上下文就停服务
```

- [ ] **Step 2: 跑测试确认失败**(`ImportError: cannot import name 'make_deployment_service'`)

- [ ] **Step 3: 实现**:`build_job` 外包一层,在返回的 `JobSpec` 的 `env` 里并入 `RISE_AGENT_ROUND`(`dataclasses.replace`);`tunnel_factory` 缺省 `tunnel_factory_for(client, AGENT_SERVE_PORT)`;`serve` 缺省在调用时才取 `compute.service.serve`(测试可替换)。

- [ ] **Step 4: 跑 `tests/test_factory_agent_backend.py` 通过**

- [ ] **Step 5: 提交** `feat(factory): 部署服务上下文工厂,作业身份带轮次 id`

---

### Task 5: 轮次处理器进入部署服务上下文

**Files:**
- Modify: `src/mindagent/rounds.py`(`make_start_round_handler` 签名、`_handle`、`_run`)
- Test: `tests/test_ma_rounds.py`

**Interfaces:**
- Consumes: 一个满足 Task 4 `open(round_id)` 形状的上下文管理器工厂;`mindagent` 只把它当 `Callable[[str], AbstractContextManager]` 用,对交出的对象只读 `backend_factory` 一个属性(鸭子类型,不导入 `factory`)。
- Produces:`make_start_round_handler(..., deployment_service: Callable[[str], AbstractContextManager] | None = None)`。`None` 时行为与今天逐字节相同。非 `None` 时:`_check_inputs` 通过之后、`_run` 之前进入 `deployment_service(env.id)`;`_run` 里部署与验证用它交出的 `backend_factory`,不用参数里的 `backend_factory`;退出上下文在 `_run` 返回或抛出之后。

- [ ] **Step 1: 写失败的测试**(`_handler` 加 `deployment_service=` 透传;替身工厂记录进入次数与 `round_id`,交出 `SimpleNamespace(backend_factory=...)`)

```python
def test_the_round_runs_inside_the_deployment_service(store, mem):
    svc = _FakeService()
    env = _start(store, _handler(mem=mem, deployment_service=svc))
    assert env.status == "executed" and svc.entered == ["agent-round-zengen-v1"] and svc.exited == 1
    assert svc.backend_calls                         # 部署用的是上下文交出的后端工厂

def test_no_service_is_started_when_inputs_are_missing(store, mem):
    store.delete(scenario_file("s1"))                # 按该文件现有删情境的写法
    svc = _FakeService()
    env = _start(store, _handler(mem=mem, deployment_service=svc))
    assert env.status == "failed" and svc.entered == []

def test_no_service_for_a_terminal_round(store, mem):
    svc = _FakeService()
    _start(store, _handler(mem=mem))                 # 先跑成 executed
    _start(store, _handler(mem=mem, deployment_service=svc))
    assert svc.entered == []

def test_a_deferred_service_leaves_the_round_pending(store, mem):
    with pytest.raises(DeferredError):
        _start(store, _handler(mem=mem, deployment_service=_FakeService(enter_raises=DeferredError("busy"))))
    assert store.read_product(agent_round_file("zengen-v1")).status == "pending"

def test_the_service_is_exited_when_the_run_fails(store, mem):
    svc = _FakeService()
    factory = _Factory(fail_first_n=99)                      # 部署每次尝试都失败、瞬态
    with pytest.raises(DeploymentFailedError):
        _start(store, _handler(mem=mem, factory=factory, deployment_service=svc))
    assert svc.exited == 1                                  # 失败也退出上下文、停服务
    assert not _world_lock_held(mem, "s1")                  # 世界锁已放

def test_a_deferred_exit_after_success_leaves_the_round_committed(store, mem):
    svc = _FakeService(exit_raises=DeferredError("stop retry"))
    with pytest.raises(DeferredError):
        _start(store, _handler(mem=mem, deployment_service=svc))
    env = store.read_product(agent_round_file("zengen-v1"))
    assert env.status == "executed" and not _world_lock_held(mem, "s1")   # 终态已写,下一 tick 见终态即返回
```

`_Factory(fail_first_n=)`、`_world_lock_held` 若该文件没有,按该文件已有替身的写法加。

- [ ] **Step 2: 跑测试确认失败**(`unexpected keyword argument 'deployment_service'`)

- [ ] **Step 3: 实现**:`_handle` 里把 `_check_inputs(...); _run(...)` 改成先 `_check_inputs`,再 `with (deployment_service(env.id) if deployment_service else nullcontext()) as svc:` 包 `_run`,`_run` 收一个 `backend_factory` 参数(`svc.backend_factory if svc else backend_factory`)。`make_instance` 与 `instance_with` 改用这个参数。

- [ ] **Step 4: 跑 `tests/test_ma_rounds.py tests/test_ma_verify.py` 全部通过**

- [ ] **Step 5: 提交** `feat(mindagent): 轮次在输入检查之后进入注入的部署服务上下文`

---

### Task 6: 罐头模式下部署对手位按情境剧本回复

**Files:**
- Modify: `src/factory/agent.py`(`AgentRuntime._backends`,部署会话选底座的那段,约 346-354 行)
- Test: `tests/test_factory_handlers.py`

**Interfaces:**
- Consumes: `Scenario.opponent_script: dict[str, list[str]]`(已有)。
- Produces: 部署会话(`run_id is None`)的对手位底座判定:绑定显式 `driver: scripted` → 剧本(没有取全局台词),`loop=True`;否则情境给该槽位带了非空剧本 → `ScriptedBackend({slot: 剧本}, loop=True)`;否则 → 今天的 `ScriptedBackend({slot: list(self._lines)})`(不循环)。训练会话不变。Task 7 在这张判定的第二行之前插入模型开关。

- [ ] **Step 1: 写失败的测试**(沿用 :641 起的 `_slot_info`、`_two_slots`、`_says` 与 `FileTupleStore` 部署夹具)

```python
def test_a_canned_deployment_opponent_follows_the_scenario_script(store, tmp_path):
    runtime, deploy = _deploy_runtime(store, tmp_path)          # 与 :652 同一写法,全局台词 ("嗯",)
    runtime.register_deployment_episode("deploy-m-s1-1", "agent-round-m")
    res = runtime._backends(_slot_info(_scenario_with({"b": ["一", "二"]}), _two_slots(),
                                       episode_id="deploy-m-s1-1"))
    assert _says(res.backends["b"], "b", 3) == ["一", "二", "一"]   # 绑定没写 driver: scripted
    res.close()

@pytest.mark.parametrize("script", [None, {}, {"b": []}, {"c": ["别人的"]}])
def test_a_canned_deployment_opponent_without_its_script_keeps_the_global_lines(store, tmp_path, script):
    ...
    assert _says(res.backends["b"], "b", 1) == ["嗯"]

def test_training_sessions_still_ignore_the_scenario_script_without_a_scripted_driver(store): ...
    # 登记给训练 run 的会话、绑定未写 driver:仍交给对手工厂,不念剧本
```

**改写两条旧测试**(它们钉住的是"部署会话不读剧本",D11 有意改变它;只改断言,不删):
- `test_without_a_factory_every_opponent_is_the_same_unlooped_scripted_backend_as_before`(`tests/test_factory_handlers.py:356`):情境带 `{"b": ["剧本"]}`,改为断言 `b` 循环念 `["剧本", "剧本", "剧本"]`、`c`(情境没给它剧本)仍念 `["全局甲", "全局乙", "(无更多发言)"]`;测试名改成 `..._unless_the_scenario_scripts_the_slot`。
- `test_with_the_factory_set_an_unregistered_session_never_judges_its_bindings`(`:430`):保留"不判绑定、不调工厂"的断言,把台词断言改为 `b` 循环念剧本 `["剧本", "剧本", "剧本"]`,注释"剧本也不生效"删掉。

- [ ] **Step 2: 跑 `pytest tests/test_factory_handlers.py -q -k "scenario_script or global_lines"`,第一条 FAIL(念的是全局台词 "嗯")**

- [ ] **Step 3: 在 `_backends` 部署会话分支按 Produces 的三行判定改写**:剧本取 `scenario.opponent_script.get(slot)`,空列表视为没有。

- [ ] **Step 4: 跑 `tests/test_factory_handlers.py tests/test_factory_training_worlds.py tests/test_factory_interact_wire.py` 全部通过**

- [ ] **Step 5: 提交** `feat(factory): 罐头模式下部署对手位按情境剧本回复`

---

### Task 7: 部署对手的模型开关与组合根接线

**Files:**
- Modify: `src/factory/agent.py`(`AgentRuntime`:新增部署对手开关;`_backends` 在 Task 6 的判定里插入模型那一行)
- Modify: `src/factory/wire.py`(`BuildContext.deployment_service`;`assemble` 在 `agent_backend == "vllm"` 时造上下文工厂)
- Modify: `src/factory/handlers.py`(`_agent` 透传,流 deadline 用 `agent_deploy_per_turn_s`)
- Test: `tests/test_factory_handlers.py`、`tests/test_factory_wire.py`

**Interfaces:**
- Consumes: Task 3 的 `AGENT_BACKENDS`、`agent_deploy_per_turn_s`;Task 4 的 `make_deployment_service`、`DeploymentService.opponent_factory`;Task 5 的 `make_start_round_handler(deployment_service=)`;Task 6 的部署对手判定。
- Produces:
  - `AgentRuntime.bind_deployment_opponents(factory: Callable[[RoleBinding, Scenario], ModelBackend]) -> AbstractContextManager[None]`:进入时装上,退出时卸下(线程安全,与 `_routes_lock` 同一把锁)。
  - `_backends` 对**部署会话**:在 Task 6 判定的第一行(显式 `driver: scripted`)之后插入一行:开关装着 → `factory(binding, scenario)`,剧本不生效。外面照旧包 `memory_role_backend(..., memory=deploy.open(...))`。训练会话不变。
  - 组合根:`BuildContext.deployment_service` 是一个包装后的工厂:进入 `make_deployment_service(...)(round_id)` 之后再进入 `runtime.bind_deployment_opponents(svc.opponent_factory)`,两者用同一个 `ExitStack`。

- [ ] **Step 1: 写失败的测试**

```python
# tests/test_factory_handlers.py(沿用 :646 那组部署会话测试的夹具)
def test_a_registered_deployment_session_uses_the_bound_opponent_factory(store, tmp_path):
    runtime.register_deployment_episode("deploy-m-s1-1", "agent-round-m")
    with runtime.bind_deployment_opponents(lambda b, s: _Echo("model says")):
        res = runtime._backends(_info("deploy-m-s1-1"))
    assert _speak(res, "user") == "model says"

def test_the_model_switch_overrides_the_script_but_not_an_explicit_scripted_driver(...): ...
    # 情境带剧本 {"b": ["一"]}:未写 driver 的 b 由模型说话;同一情境里写了 driver: scripted 的 c 念剧本
def test_a_slow_model_opponent_is_a_transient_attempt(...): ...
    # 开关装一个抛 OpponentTimeoutError 的工厂,经真实 loopback 跑一条部署会话:终止原因 role_backend_timeout
def test_training_sessions_ignore_the_deployment_switch(...): ...

# tests/test_factory_wire.py
def test_vllm_agent_backend_wires_the_service_into_the_round_handler(store_with_starling, monkeypatch):
    # monkeypatch factory.agent_backend.make_deployment_service 为记录替身;assemble 后取出处理器构造参数
    assert ctx.deployment_service is not None
def test_canned_agent_backend_wires_nothing(store_with_starling): ...              # deployment_service 是 None
```

- [ ] **Step 2: 跑测试确认失败**

- [ ] **Step 3: 实现**:`assemble` 在造 `BuildContext` 之前,`agent_backend == "vllm"` 时与 `--interact` 同一写法选端点、读主机映射、造 `ComputeClient`(`factory.compute_config` 的 `select_endpoint`、`read_endpoints_config`、`read_host_map`、`build_compute_client`),超时取 `budget.policy_s` 与 `budget.opponent_s`。`_agent` 里 `vllm` 时 `stream_deadline_s = config.max_turns * budget.agent_deploy_per_turn_s`。

- [ ] **Step 4: 全量回归**

Run: `PYTHONDONTWRITEBYTECODE=1 uv run --offline --extra dev pytest -q -x -p no:cacheprovider`
Expected: 全部通过(与提交 `50e5a08` 时的通过数相比只增不减)。再跑 `uv run --offline --extra dev ruff check src tests` 干净。

- [ ] **Step 5: 提交** `feat(factory): 部署会话对手位由服务上的基座说话,--agent-backend vllm 接进闭环`

---

### Task 8: 设计文档状态与真机验证

**Files:**
- Modify: `docs/design/00-overview.md`、`20-socialsimulator.md`、`50-mindagent.md`、`90-factory-and-cli.md`、`_shared/context-block.md`
- 真机:171(`gpu-171`),新树 `~/rise-verify/s3-real`,新记忆根

- [ ] **Step 1: 把本计划落地的条目从 [计划中] 改成 [已落地]**("本计划不做"一节列的条目保持 [计划中]);50、90、20 篇头部"对应实施计划"一行补"场景三真模型部署:任务 1 至 8",实际名字(`AGENT_SERVE_PORT = 18083`、`TranslatingAgentBackend`、`bind_deployment_opponents`、四个异常类名、`RISE_AGENT_ROUND`)写进文档。跑 `python3 docs/design/tools/sync_docs.py`、`check_docs.py`、`check_consistency.py`,0 错误。

- [ ] **Step 2: 提交** `docs(design): 场景三真模型部署后端落地`

- [ ] **Step 3: 真机前检查**:171 上 `nvidia-smi` 无计算进程、`gpu.lease` 空、`forge-gpu-171` 容器里 `nvidia-smi -L` 列出 8 张卡;看板服务 `info()` 的提交与钉住的一致。任一不满足就停下报告,不抢卡。

- [ ] **Step 4: 建新树与新记忆根**:新树里有一个 effective 的晋级模型、`agent.yaml` 的三个情境、`memory_config` 指向一个从没用过的记忆根(Starling 外部模式连本机 8787)。

- [ ] **Step 5: 跑一个部署轮次**

Run: `factory reconcile ~/rise-verify/s3-real --once --enable agent --agent-backend vllm --endpoint gpu-171`
Expected: 轮次产物 `executed`(或带提案停在等门②);三条 episode 里智能体位与对手位的话语都不是三句台词,也不是"指导语|plain"拼接;171 的租约放掉、没有残留 `serve-*` 计算进程。零发现、零提案也算通过(设计第 1 节第 4 条)。

- [ ] **Step 6: 记录结果**:把耗时、每条 episode 的信号与 findings、部署对手位单次 HTTP 的实测耗时写进 50 篇未核实项与 00 篇风险表第 38 项;提交 `docs(design): 场景三真模型部署的真机结果`。
