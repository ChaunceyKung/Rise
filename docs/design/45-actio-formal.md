# 45 · Actio 正式件:合并后的形态(P0–P5 记录)

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

## 2. 三个消费面(与 §3.1 架构图一致)

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
