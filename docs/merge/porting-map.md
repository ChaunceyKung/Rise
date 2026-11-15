# 移植对照表（porting-map）

> 记录 Actio-RSI-infra → Rise 每一笔移植:源文件 → 目标文件 → 快照 commit → 偏差。
> 纪律:不悄悄丢弃、不悄悄改写;任何偏差必须在此留一行理由。源仓参照
> `ChaunceyKung/Actio-RSI-infra`,快照基线 `a718e7f`(P0 基线,见 BASELINE.md)。

## P1:合同层(方案 A1)

| 源(Actio-RSI-infra) | 目标(Rise) | 偏差 |
|---|---|---|
| `src/actio/contracts/json.py` | `src/actio/contracts/json.py` | 无(逐字节) |
| `src/actio/contracts/hashing.py` | `src/actio/contracts/hashing.py` | 无 |
| `src/actio/contracts/wire.py` | `src/actio/contracts/wire.py` | 无 |
| `src/actio/contracts/endpoint.py` | `src/actio/contracts/endpoint.py` | 无 |
| `src/actio/contracts/transport.py` | `src/actio/contracts/transport.py` | 无 |
| `src/actio/contracts/ports.py` | `src/actio/contracts/ports.py` | 无 |
| `src/actio/contracts/memory.py` | `src/actio/contracts/memory.py` | 无(F401 死导入 Mapping 保留,pyproject 窄豁免) |
| `src/actio/contracts/versions.py` | `src/actio/contracts/versions.py` | 追加 `CONTRACTS_VERSION = 'actio-contracts.1'`(D7) |

**延后项(有消费方时再迁)**:

| 源 | 理由 | 归入阶段 |
|---|---|---|
| `contracts/environment.py`(75 行) | 消费方只有 `adapters/environment/*`(方案 A18 不迁域) | 环境域立项时 |
| `contracts/scenarios.py`(UNSET 哨兵) | 消费方 `application/scenarios`、`interfaces/cli/run` | P3/factory 接线时 |

**测试移植注记(修正方案 §5.2 两行)**:Actio 的 `tests/test_contract.py` 与
`tests/test_schema.py` 并非合同层单测,而是走 Store/Facts/RuntimePort 的全栈
集成测试(分别归 P2/P4),P1 以新写用例族 `tests/test_actio_contracts.py`
(T-C-01/03,golden 向量跨仓字节兼容)与 `tests/test_actio_boundaries.py`
(T-C-02 纯度 + 双向隔离)替代;全栈契约测试在 P2/P4 随 Store 一起移植。

## 环境备忘

- golden 向量生成命令(Actio 仓,`.local/phase1-env` 解释器):
  `python -c "from actio.contracts.json import canonical, digest, seal; ..."`
- Rise 侧跑测试统一加 `--basetemp=<工作区>/.pytest-tmp-*`(见 BASELINE.md §1)。

## P2:harness 闭包与预算制网关(方案 A2/A3/A9/A13/A4 前半)

**布局决策修正**:移植件一律保留上游包路径(`actio.adapters.*/profiles/domain/evidence/interfaces/tasks/resources/measurement`),
零 import 改写、node 侧 spawnSync 的点路径(`actio.interfaces.ipc.budget`、`actio.interfaces.workers.*`)原样生效;
**新写的组合代码才进新包** `actio/harness`(identity/gateway)。原方案的 `src/actio/harness/` 整体收纳方案作废。

| 内容 | 来源 | 偏差 |
|---|---|---|
| adapters/{filesystem,runtime(supervisor/host/mcp_server),transport(fixture/responses/plugins/fixtures),persistence(ledger),memory(starling)} | 逐字节 | 无 |
| profiles 全包 + domain + evidence/audit + tasks 全家 + measurement + resources + interfaces/{ipc,workers} | 逐字节 | 无(比方案预估多迁 tasks/measurement/resources:profiles 谓词的惰性闭包) |
| `actio/harness/identity.py` | 新写(源自 runtime.py:20-50 的 store-free 段) | PACKAGE 指向 src/actio(D7:Rise 侧包改动不扰动 pins);registry 惰性化 |
| `actio/harness/gateway.py` GatewayRuntime | **新组合**(三刀的 store-free 半边) | native_usage 从 host.jsonl 直取(替代 Facts/occurrence);campaign v8/v9/v10 分支与 suite 审计随 P3/P4 |
| TransportPort/RuntimePort 主体 | 未迁 | Store 编排半边(fence/intent/op_update/Facts)随 P3/P4;gateway 分支语义已由 GatewayRuntime 承接 |
| `interfaces/cli`、application/*、adapters/{runtime(facts/runtime/evaluator/cleanup),environment,persistence(store/database)} | 未迁 | P3/P4 |

**范围修正(对方案 §4 P2)**:
1. gateway 合同是冻结合同(plan∈{compatible,conflict},上限 2×len(plan) 次调用)——**不适合逐轮对话 backend**;
   DSH 通道定位为"预算制单发/有限发",消费者是 P3 MindAgent 演化步骤。`--agent-backend dsh` 挂进
   factory 对手位的原验收作废,改为 P3 演化管线的 GatewayRuntime 消费(T-A-01 e2e 已在测试中闭环)。
2. D1 桥(Rise starling 会话 ↔ StarlingMemoryPort facade)与 factory 接线 → P3 开工(P2 已备齐
   adapter 与 contracts)。CAS Memory/outbox 投影依赖 Store → P4。
3. Actio 基线 12 条 gateway"环境性失败"已根因(**owned_root 80 字符路径上限**,本机仓库前缀过长)并在
   源仓以 `runs = "D:/A_t"` 修复复绿;Rise 侧 e2e 用预解析短根 + 跳过长环境。

## P3:MindAgent 演化 infra(方案 A5/A6/A7 的接线)

| 内容 | 来源 | 说明 |
|---|---|---|
| `mindagent/evolution.py` | **新写** | 演化三元组(D6):plan/measure/gain_signature/admit_scaffold/dispatch;candidate 域与 oracle 在 P2 已随闭包进仓,此处只做接线 |
| `factory/memory_actio_bridge.py` | **新写** | D1 桥:MemoryBackend→Actio 鸭子 facade→StarlingMemoryAdapter shadow 投影栈;Rise 消费方零改动 |
| B0/C1/POLICY golden | 两仓解释器各跑一遍比对一致后固化进测试 | 跨仓字节互通的证据 |
| SOURCE 真缺陷修复 | 延后至 P4 | test_evaluation_candidate_runtime 属全栈测试,随 Store 一起移植时修 |
| GatewayRuntime 消费(演化步骤用) | P4 接 | P3 只留 V2 接缝(plan_from_switches 拒绝 gateway 并注明) |

边界开闸记录:actio 消费方 = {factory, mindagent}(test_actio_boundaries 强制)。
