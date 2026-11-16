# Actio 正式件:合并自 Actio-RSI-infra 的 building block 与权威面

| 项 | 内容 |
|---|---|
| 一句话 | 把 Actio-RSI-infra 的合同层、DSH 预算制网关、CAS 记忆与 SQLite 权威面并进本仓,作为被演化的正式件 |
| 状态 | [已落地]:P0–P5 六道门禁全绿,actio 相关 87 个用例;跨仓 golden(canonical/seal/B0/C1/POLICY)两仓一致;episode 编排域(wiring/RuntimePort/TransportPort 主体/CLI)按 docs/merge/porting-map.md 有据未迁 |
| 所在层 | 共享基础设施 |
| 代码位置 | `src/actio`(contracts/harness/adapters/profiles/domain/evidence/tasks/measurement/resources);消费面 `src/mindagent/evolution.py`、`src/factory/memory_actio_bridge.py`、`src/recipestore/actio_lineage_bridge.py` |
| 基线提交 | `b826440`(上游);源仓快照 `ChaunceyKung/Actio-RSI-infra@a718e7f`,合并账在 `docs/merge/` |
| 依赖 | Python 标准库;DSH 闭包仅在可选 extra `actio`(deepseek-harness-sdk/runtime-bin、mcp),缺省环境可导入、运行时显式报缺 |
| 被依赖 | MindAgent(演化三元组)、RecipeStore(谱系 envelope 桥,仅经 `actio.contracts`)、factory(D1 记忆桥);消费方白名单由 `tests/test_actio_boundaries.py` 强制 |
| 对应实施计划 | `docs/merge/plan.md` P1–P5(行动方案);移植逐笔账 `docs/merge/porting-map.md` |

> 状态:[已落地]。本文回答"Actio 合进 Rise 之后,系统长什么样"。
> 依据:`docs/merge/plan.md`(合并行动方案)、`docs/merge/porting-map.md`(逐笔移植账)、
> `docs/merge/BASELINE.md`(门禁记录)。源仓快照:`ChaunceyKung/Actio-RSI-infra@a718e7f`。

## 1. 两包共存(方案 Q1 的最终裁定)

P1 计划曾设想"`simple_actio` 改名为 `actio`、SimpleActio 让位正式件"。P2 的布局
决策改变了结论:**移植件一律保留上游包路径**(`actio.*`,零 import 改写、可整体
回移、node 侧 spawnSync 点路径不变),因此 `actio` 名字已被正式件占用,SimpleActio
保留原名。二者是**互补而非替换**:

| 包 | 角色 | 关系 |
|---|---|---|
| `simple_actio` | Rise 原生的轻量智能体运行时(技能路由/记忆/经验/激活轨迹),服务仿真与训练位 | 经 `factory/memory_actio_bridge`(D1 桥)把记忆后端借给 Actio 投影栈 |
| `actio` | 正式 Actio building block:合同层、DSH harness(预算制网关)、CAS 记忆+outbox、SQLite 权威面、候选/评估谱系、测量 oracle | 被 `mindagent`(演化)与 `recipestore`(存储桥)消费;`factory` 装配 |

改名不再执行;若未来 upstream 采纳合并,Q1 重新开题。

## 2. 三个消费面(与 docs/merge/plan.md 的目标架构图一致)

1. **Actio(被演化对象)**:`actio.harness.GatewayRuntime`——预算制单发/有限发网关
   (冻结 v5 合同:plan∈{compatible,conflict}、每 seat 一生一次 attempt、≤2×plan 次调用)。
   **不是逐轮对话 backend**;对话仍走 canned/vllm。
2. **MindAgent(演化 infra)**:`mindagent/evolution.py` 三元组(target/algorithm/goal)。
   scaffold→Actio 冻结候选+decide 准入;skill→既有提案闭环;memory→P6a 预留。
   目标接 `actio.measurement.oracle`(有限域指标);gateway 提案器为 V2 接缝。
3. **RecipeStore(存储与数据管理)**:SQLite 为权威面(Store/迁移/双谱系/outbox);
   `recipestore/actio_lineage_bridge.py` 把 sealed 谱系终态**单向幂等投影**为
   envelope 产物(D2);git 树仍是协作/审核面。

## 3. 依赖纪律(由测试强制)

- `actio` 内部沿用上游分层(contracts←domain←…,pins 哈希 actio 包内树);
- `actio` 的消费方仅 {`factory`, `mindagent`, `recipestore(仅 contracts)`}
  (`tests/test_actio_boundaries.py` + `tests/test_rs_flow.py`);
- 跨仓字节兼容由 golden 锁定:canonical/digest/seal 向量、B0/C1/POLICY 摘要
  (`tests/test_actio_contracts.py`、`tests/test_ma_evolution.py`)。

## 4. CLI 裁定(D8 收尾)

上游 `actio` CLI(run/pilot/suite/candidate…)整体属 **episode 编排域**
(Store+wiring,未移植、也无需移植)——Rise 的消费全部程序化:
`mindagent.evolution` / `factory.memory_actio_bridge` / `recipestore.actio_lineage_bridge`。
不新增 CLI 命令;TypeScript `rise` 审核命令行不涉改动。

## 5. 已知边界与后续

- evaluation export 的 verify 钉死历史常量 `LEGACY_LINEAGE`(证据不可变纪律),
  新库不可复刻——历史 fixture 移植前无全链导出测试;
- `memory` 演化目标与 gateway 提案器:方案 P6a/V2;
- Windows 环境的 Actio 纪律:`owned_root` 80 字符上限(短根)、`runs` 需短绝对路径
  (源仓已配 `D:/A_t`)。

## 6. 内外模式(V3,施工中)

`refactor/actio-mindagent-v3` 分支按 V3 规划(docs/superpowers/specs/2026-11-16-rise-actio-mindagent-arch-v3.md)
在 `simple_actio/{core,inner,outer}` 增设双模式层:**只包装、不改动**现有运行时——
模式经 `GuidedBackend` 装饰器(`adapters/legacy.ModeDirectiveBackend`)注入指导语,
`respond()/instantiate()` 签名零改动,`src/actio` 基础设施包不参与分层。
施工分期与验收见 docs/superpowers/plans/2026-11-16-actio-mindagent-v3-construction.md。
